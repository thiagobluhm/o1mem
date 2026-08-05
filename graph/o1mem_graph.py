#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
o1mem_graph.py — o grafo de NAVEGAÇÃO da memória O(1)mem.

Por que existe
--------------
A memória é lida em O(1) no boot: o `MEMORY.md` é a entrada determinística e
continua sendo. Este módulo NÃO entra no caminho do boot. Ele serve o segundo
movimento — quando já existe uma pergunta e é preciso *atravessar* o acervo
("o que mais toca o gate b222?", "quem ficou órfão?", "qual o caminho entre
este fio e aquele?").

Custo de indexação ≈ zero: as arestas JÁ EXISTEM. São os `[[wikilinks]]`
escritos à mão há semanas, mais os links markdown do índice. Não há embedding,
não há vector DB para sincronizar, não há passo probabilístico — só um parser.

Modelo
------
Nós    : cada arquivo .md em memory/ (índices MEMORY/MEMORY_ARCHIVE incluídos).
Arestas: `[[nome]]`            → aresta "wiki"  (fio de raciocínio, escrito à mão)
         `[texto](arquivo.md)` → aresta "index" (pertencimento ao índice quente/frio)

Resolução de alvo é tolerante por desenho: `[[feedback-overlap-playbooks]]`
casa com `feedback_overlap_playbooks.md`. Hífen/underscore, caixa e sufixo
`.md` são normalizados. O que não casar vira aresta QUEBRADA e é reportado —
não silenciosamente descartado.

USO
---
  python o1mem_graph.py build                 # grava graph.json e imprime o resumo
  python o1mem_graph.py stats                 # saúde do acervo
  python o1mem_graph.py neighbors <nome> -d 2 # navegação sob demanda
  python o1mem_graph.py path <a> <b>          # menor caminho entre dois fios
  python o1mem_graph.py orphans               # fora do índice quente E sem quem cite
  python o1mem_graph.py broken                # wikilinks que não resolvem
  python o1mem_graph.py cold --days 30        # candidatos a decay (frios + fora do fio)

Opções globais:
  --project <slug|substring>   escolhe o projeto (default: o único que existir,
                               ou erro pedindo desambiguação)
  --root <caminho>             aponta uma pasta memory/ diretamente
  --json                       saída em JSON (para consumo por UI/agente)

Sem dependências externas. Python 3.8+.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import deque
from datetime import datetime, timezone

PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
HERE = os.path.dirname(os.path.abspath(__file__))

INDEX_FILES = {"memory", "memory_archive"}  # nós de índice (chave normalizada)

RE_WIKI = re.compile(r"\[\[([^\]\|]+?)(?:\|[^\]]*)?\]\]")
RE_MDLINK = re.compile(r"\[[^\]]*\]\(\s*([^)\s]+?\.md)\s*\)")
RE_FM = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
RE_FENCE = re.compile(r"```.*?```", re.S)
RE_CODE = re.compile(r"`[^`\n]*`")


# --------------------------------------------------------------------------
# leitura
# --------------------------------------------------------------------------
def norm(name: str) -> str:
    """Chave canônica de um nó: sem .md, sem caixa, hífen ≡ underscore.

    Existe porque os wikilinks são escritos à mão e derivam: o mesmo fato
    aparece como `feedback-overlap-playbooks-aquiles` e
    `feedback_overlap_playbooks_aquiles`. Casar os dois é o comportamento
    correto; tratá-los como nós distintos inventaria um órfão que não existe.
    """
    n = os.path.basename(name.strip()).strip()
    if n.lower().endswith(".md"):
        n = n[:-3]
    return n.replace("-", "_").lower()


def parse_frontmatter(text: str) -> dict:
    """Extrai o frontmatter YAML raso do arquivo de memória.

    Parser deliberadamente mínimo (chave: valor + um nível de aninhamento):
    o formato é escrito pela própria skill e nunca usa listas nem âncoras.
    Evita uma dependência de PyYAML por três campos.
    """
    m = RE_FM.match(text)
    if not m:
        return {}
    out, section = {}, None
    for raw in m.group(1).splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indented = raw[:1].isspace()
        line = raw.strip()
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if indented and section is not None:
            out[f"{section}.{k}"] = v
        elif not v:
            section = k
        else:
            out[k] = v
            section = None
    return out


def strip_frontmatter(text: str) -> str:
    m = RE_FM.match(text)
    return text[m.end():] if m else text


def strip_code(text: str) -> str:
    """Remove blocos e trechos de código antes de procurar arestas.

    Sem isto, prosa que FALA sobre a sintaxe — "as arestas são os
    `[[wikilinks]]`" — vira uma aresta para um nó `wikilinks` que nunca
    existiu, e o relatório de quebrados enche de ruído auto-infligido.
    Dentro de crases é menção, não referência.
    """
    return RE_CODE.sub(" ", RE_FENCE.sub(" ", text))


def find_memory_roots() -> list:
    """Todas as pastas memory/ sob ~/.claude/projects/<slug>/."""
    roots = []
    try:
        for slug in sorted(os.listdir(PROJECTS_DIR)):
            p = os.path.join(PROJECTS_DIR, slug, "memory")
            if os.path.isdir(p):
                roots.append((slug, p))
    except OSError:
        pass
    return roots


def freshest_root() -> tuple:
    """O projeto com o `MEMORY.md` mais recente.

    Usado quando alguém precisa de UM grafo sem poder perguntar qual (a página
    irmã gerada pelo outro launcher). Adivinhar é aceitável ali porque o custo
    de errar é um link abrir o projeto errado — no CLI, que é a via principal,
    a ambiguidade continua sendo erro explícito.
    """
    best, best_mt = None, -1
    for slug, path in find_memory_roots():
        try:
            mt = os.path.getmtime(os.path.join(path, "MEMORY.md"))
        except OSError:
            mt = 0
        if mt > best_mt:
            best, best_mt = (slug, path), mt
    return best


def resolve_root(project: str = None, root: str = None) -> tuple:
    if root:
        if not os.path.isdir(root):
            raise SystemExit(f"ERRO: pasta nao encontrada: {root}")
        return (os.path.basename(os.path.dirname(os.path.abspath(root))), root)

    roots = find_memory_roots()
    if not roots:
        raise SystemExit(f"ERRO: nenhuma pasta memory/ sob {PROJECTS_DIR}")
    if project:
        exact = [r for r in roots if r[0].lower() == project.lower()]
        if exact:
            return exact[0]
        hits = [r for r in roots if project.lower() in r[0].lower()]
        if not hits:
            disp = "\n".join("  " + s for s, _ in roots)
            raise SystemExit(f"ERRO: nenhum projeto casa '{project}'. Disponiveis:\n{disp}")
        if len(hits) > 1:
            disp = "\n".join("  " + s for s, _ in hits)
            raise SystemExit(f"ERRO: '{project}' e ambiguo:\n{disp}")
        return hits[0]
    if len(roots) == 1:
        return roots[0]
    disp = "\n".join("  " + s for s, _ in roots)
    raise SystemExit(
        "ERRO: ha mais de um projeto; escolha com --project <slug>.\n" + disp
    )


# --------------------------------------------------------------------------
# construção
# --------------------------------------------------------------------------
def build_graph(root: str, slug: str = "") -> dict:
    """Varre a pasta memory/ e devolve {nodes, edges, broken, meta}."""
    nodes, edges, broken = {}, [], []

    files = sorted(f for f in os.listdir(root) if f.lower().endswith(".md"))
    for fname in files:
        path = os.path.join(root, fname)
        try:
            text = open(path, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        fm = parse_frontmatter(text)
        body = strip_frontmatter(text)
        key = norm(fname)
        st = os.stat(path)

        if key in INDEX_FILES:
            ntype = "index"
        else:
            ntype = fm.get("metadata.type") or fm.get("type") or _type_from_name(key)

        nodes[key] = {
            "id": key,
            "file": fname,
            "label": fm.get("name") or key,
            "type": ntype,
            "description": fm.get("description", ""),
            "bytes": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
            "modified": fm.get("metadata.modified", ""),
            "deg_in": 0,
            "deg_out": 0,
        }

    # segunda passada: arestas (precisa de todos os nós já conhecidos p/ resolver)
    for fname in files:
        src = norm(fname)
        path = os.path.join(root, fname)
        try:
            body = strip_frontmatter(
                open(path, "r", encoding="utf-8", errors="replace").read()
            )
        except OSError:
            continue

        body = strip_code(body)
        found = [(norm(t), t, "wiki") for t in RE_WIKI.findall(body)]
        found += [(norm(t), t, "index") for t in RE_MDLINK.findall(body)]

        seen = set()
        for tgt, raw, kind in found:
            tgt = _resolve(tgt, nodes)
            if tgt == src or (tgt, kind) in seen:
                continue
            seen.add((tgt, kind))
            if tgt in nodes:
                edges.append({"source": src, "target": tgt, "kind": kind})
                nodes[tgt]["deg_in"] += 1
                nodes[src]["deg_out"] += 1
            else:
                broken.append({"source": src, "target_raw": raw, "kind": kind})

    return {
        "meta": {
            "project": slug,
            "root": root,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n_nodes": len(nodes),
            "n_edges": len(edges),
            "n_broken": len(broken),
        },
        "nodes": list(nodes.values()),
        "edges": edges,
        "broken": broken,
    }


def _resolve(key: str, nodes: dict) -> str:
    """Casa um alvo de wikilink contra os nós reais, tolerando o prefixo de tipo.

    `[[perguntar-antes-de-alterar-codigo]]` deve chegar em
    `feedback_perguntar_antes_de_alterar_codigo.md`: quem escreve à mão omite o
    prefixo o tempo todo, e tratar isso como aresta quebrada produziria um
    falso alarme em cima de um link que o humano acertou em substância.
    Só resolve quando o candidato é ÚNICO — na dúvida, prefere reportar
    quebrado a inventar uma aresta errada.
    """
    if key in nodes:
        return key
    hits = [k for t in ("feedback", "project", "user", "reference")
            for k in (f"{t}_{key}",) if k in nodes]
    return hits[0] if len(hits) == 1 else key


def _type_from_name(key: str) -> str:
    for t in ("feedback", "project", "user", "reference"):
        if key.startswith(t):
            return t
    return "other"


# --------------------------------------------------------------------------
# consultas
# --------------------------------------------------------------------------
def adjacency(g: dict, directed: bool = False) -> dict:
    adj = {n["id"]: set() for n in g["nodes"]}
    for e in g["edges"]:
        adj[e["source"]].add(e["target"])
        if not directed:
            adj[e["target"]].add(e["source"])
    return adj


def _node(g: dict, name: str) -> dict:
    key = norm(name)
    by_id = {n["id"]: n for n in g["nodes"]}
    if key in by_id:
        return by_id[key]
    hits = [n for n in g["nodes"] if key in n["id"]]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise SystemExit(f"ERRO: no '{name}' nao encontrado.")
    disp = "\n".join("  " + h["id"] for h in hits[:15])
    raise SystemExit(f"ERRO: '{name}' e ambiguo:\n{disp}")


def neighbors(g: dict, name: str, depth: int = 1) -> list:
    """BFS a partir de um nó — a navegação sob demanda, o caso de uso central."""
    start = _node(g, name)["id"]
    adj = adjacency(g)
    seen = {start: 0}
    q = deque([start])
    while q:
        cur = q.popleft()
        if seen[cur] >= depth:
            continue
        for nxt in sorted(adj.get(cur, ())):
            if nxt not in seen:
                seen[nxt] = seen[cur] + 1
                q.append(nxt)
    by_id = {n["id"]: n for n in g["nodes"]}
    out = [dict(by_id[k], hops=v) for k, v in seen.items() if k != start]
    return sorted(out, key=lambda n: (n["hops"], n["id"]))


def shortest_path(g: dict, a: str, b: str) -> list:
    src, dst = _node(g, a)["id"], _node(g, b)["id"]
    adj = adjacency(g)
    prev = {src: None}
    q = deque([src])
    while q:
        cur = q.popleft()
        if cur == dst:
            break
        for nxt in sorted(adj.get(cur, ())):
            if nxt not in prev:
                prev[nxt] = cur
                q.append(nxt)
    if dst not in prev:
        return []
    path, cur = [], dst
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    return list(reversed(path))


def orphans(g: dict) -> list:
    """Nós que nenhum índice lista E que nenhum fio cita.

    É o vazamento real do acervo: o arquivo existe, custou uma sessão para ser
    escrito, e não há caminho até ele partindo do boot.
    """
    cited = set()
    for e in g["edges"]:
        cited.add(e["target"])
    return sorted(
        (n for n in g["nodes"] if n["type"] != "index" and n["id"] not in cited),
        key=lambda n: n["id"],
    )


def cold_candidates(g: dict, days: int = 30) -> list:
    """Candidatos a decay: no índice QUENTE, antigos, e sem fio vivo puxando.

    Critério deliberadamente conservador — só sugere; quem move é humano.
    `wiki_in` conta citações de outros fatos (não do índice): se alguém ainda
    cita, o assunto continua vivo mesmo velho.

    Só `project` entra. `feedback` é regra operacional permanente: não envelhece
    por não ser tocada — envelhecer uma delas seria arquivar justamente a regra
    que já está internalizada e por isso parou de ser reescrita.
    """
    hot = {e["target"] for e in g["edges"] if e["source"] == "memory" and e["kind"] == "index"}
    archived = {e["target"] for e in g["edges"] if e["source"] == "memory_archive"}
    wiki_in = {}
    for e in g["edges"]:
        if e["kind"] == "wiki":
            wiki_in[e["target"]] = wiki_in.get(e["target"], 0) + 1

    now = datetime.now(timezone.utc)
    out = []
    for n in g["nodes"]:
        if n["id"] not in hot or n["id"] in archived or n["type"] != "project":
            continue
        try:
            ts = datetime.fromisoformat(n["mtime"])
        except ValueError:
            continue
        age = (now - ts).days
        if age >= days and wiki_in.get(n["id"], 0) == 0:
            out.append(dict(n, age_days=age, wiki_in=0))
    return sorted(out, key=lambda n: -n["age_days"])


def stats(g: dict) -> dict:
    by_type, isolated = {}, 0
    for n in g["nodes"]:
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1
        if n["deg_in"] + n["deg_out"] == 0:
            isolated += 1
    adj = adjacency(g)
    seen, comps = set(), []
    for nid in adj:
        if nid in seen:
            continue
        comp, q = 0, deque([nid])
        seen.add(nid)
        while q:
            cur = q.popleft()
            comp += 1
            for nxt in adj[cur]:
                if nxt not in seen:
                    seen.add(nxt)
                    q.append(nxt)
        comps.append(comp)
    top = sorted(g["nodes"], key=lambda n: -n["deg_in"])[:10]
    return {
        "nodes": len(g["nodes"]),
        "edges": len(g["edges"]),
        "broken": len(g["broken"]),
        "by_type": by_type,
        "isolated": isolated,
        "orphans": len(orphans(g)),
        "components": sorted(comps, reverse=True),
        "most_cited": [{"id": n["id"], "deg_in": n["deg_in"]} for n in top if n["deg_in"]],
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _emit(obj, as_json: bool, plain):
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        plain(obj)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Grafo de navegacao da memoria O(1)mem")
    ap.add_argument("--project", help="slug (ou parte dele) do projeto")
    ap.add_argument("--root", help="caminho direto para uma pasta memory/")
    ap.add_argument("--json", action="store_true", help="saida em JSON")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("build", help="grava graph.json")
    p.add_argument("-o", "--out", default=os.path.join(HERE, "graph.json"))
    sub.add_parser("stats", help="saude do acervo")
    p = sub.add_parser("neighbors", help="vizinhanca de um no")
    p.add_argument("name")
    p.add_argument("-d", "--depth", type=int, default=1)
    p = sub.add_parser("path", help="menor caminho entre dois nos")
    p.add_argument("a")
    p.add_argument("b")
    sub.add_parser("orphans", help="nos sem nenhuma entrada")
    sub.add_parser("broken", help="wikilinks que nao resolvem")
    p = sub.add_parser("cold", help="candidatos a decay")
    p.add_argument("--days", type=int, default=30)

    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 0

    slug, root = resolve_root(args.project, args.root)
    g = build_graph(root, slug)

    if args.cmd == "build":
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(g, f, ensure_ascii=False, indent=1)
        m = g["meta"]
        print(f"projeto : {slug}")
        print(f"origem  : {root}")
        print(f"nos     : {m['n_nodes']}")
        print(f"arestas : {m['n_edges']}  (quebradas: {m['n_broken']})")
        print(f"gravado : {args.out}")

    elif args.cmd == "stats":
        s = stats(g)

        def plain(s):
            print(f"projeto      : {slug}")
            print(f"nos          : {s['nodes']}   arestas: {s['edges']}")
            print(f"por tipo     : " + ", ".join(f"{k}={v}" for k, v in sorted(s["by_type"].items())))
            print(f"orfaos       : {s['orphans']}   isolados: {s['isolated']}")
            print(f"quebrados    : {s['broken']}")
            print(f"componentes  : {s['components'][:8]}")
            print("mais citados :")
            for n in s["most_cited"]:
                print(f"  {n['deg_in']:>3}x  {n['id']}")

        _emit(s, args.json, plain)

    elif args.cmd == "neighbors":
        res = neighbors(g, args.name, args.depth)

        def plain(res):
            print(f"{_node(g, args.name)['id']}  ->  {len(res)} no(s) ate {args.depth} salto(s)\n")
            for n in res:
                print(f"  [{n['hops']}] {n['id']}")
                if n["description"]:
                    print(f"        {n['description'][:110]}")

        _emit(res, args.json, plain)

    elif args.cmd == "path":
        res = shortest_path(g, args.a, args.b)
        _emit(res, args.json, lambda r: print(" -> ".join(r) if r else "sem caminho"))

    elif args.cmd == "orphans":
        res = orphans(g)

        def plain(res):
            print(f"{len(res)} orfao(s) — existem, mas nada leva ate eles:\n")
            for n in res:
                print(f"  {n['file']}  ({n['bytes']}b)")

        _emit(res, args.json, plain)

    elif args.cmd == "broken":
        res = g["broken"]

        def plain(res):
            print(f"{len(res)} link(s) que nao resolvem:\n")
            for b in res:
                print(f"  {b['source']}  ->  [[{b['target_raw']}]]")

        _emit(res, args.json, plain)

    elif args.cmd == "cold":
        res = cold_candidates(g, args.days)

        def plain(res):
            print(f"{len(res)} candidato(s) a decay (>= {args.days}d, sem wikilink de entrada):\n")
            for n in res:
                print(f"  {n['age_days']:>4}d  {n['file']}")

        _emit(res, args.json, plain)

    return 0


if __name__ == "__main__":
    sys.exit(main())
