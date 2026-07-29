#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
o1mem_rag.py — a busca SEMANTICA da memoria O(1)mem.

Por que existe
--------------
O grafo (`skills/graph/`) atravessa o acervo por ESTRUTURA: quem cita quem.
Este modulo atravessa por SIGNIFICADO: "qual fio fala disso?" — mesmo quando
ninguem escreveu o wikilink. Os dois se somam na query: a semantica acha o
tema, o grafo traz os vizinhos que o embedding nao ve.

Como o grafo, ele NAO entra no caminho do boot. O `MEMORY.md` continua sendo
a entrada deterministica em O(1). O vetor serve o segundo movimento — e o seu
maior ganho e o acervo FRIO (`MEMORY_ARCHIVE.md`), que o boot nunca carrega.

Dado fora do repo (regra dura)
------------------------------
O indice vetorial carrega o texto integral da memoria de um projeto — que pode
ser privado — e este repo e PUBLICO. Por isso o Chroma persiste em
`~/.claude/o1mem/chroma/<slug>/`, nunca dentro do repo. Nao e gitignore:
o dado simplesmente nunca entra no worktree.

Modelo
------
Default: `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers),
porque a memoria e escrita em pt-BR e os modelos ONNX default do Chroma sao
treinados em ingles. Custo zero de API; roda em CPU. Troque com
`--model` ou env `O1MEM_RAG_MODEL`.

Corpus (por projeto, resolvido como no grafo)
---------------------------------------------
  memory/project_*.md, feedback_*.md,
  user_*.md, reference_*.md      -> 1 arquivo = 1 chunk (fatos atomicos)
  memory/MEMORY_ARCHIVE.md       -> 1 bullet = 1 chunk (o frio; maior ganho)
  HANDOVER_*.md (via --handovers)-> 1 secao `## ` = 1 chunk (opcional)

Incremental por desenho: cada chunk guarda um sha do texto; `index` so
re-embeda o que mudou e remove o que sumiu. `--full` reconstroi do zero.

USO
---
  python o1mem_rag.py index   [--project X] [--full] [--handovers DIR]
  python o1mem_rag.py query "custo do indice e decay" -k 3 [--json] [--no-graph]
  python o1mem_rag.py stats

Dependencias (opt-in, so desta skill): chromadb, sentence-transformers.
O resto do repo continua stdlib-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
GRAPH_DIR = os.path.normpath(os.path.join(HERE, "..", "graph"))
sys.path.insert(0, GRAPH_DIR)

import o1mem_graph as og  # noqa: E402  (resolve_root, norm, frontmatter, grafo)

CHROMA_BASE = os.path.expanduser(os.path.join("~", ".claude", "o1mem", "chroma"))
DEFAULT_MODEL = os.environ.get("O1MEM_RAG_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
COLLECTION = "o1mem"

RE_SECTION = re.compile(r"^##\s+", re.M)


# --------------------------------------------------------------------------
# chunking
# --------------------------------------------------------------------------
def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def collect_chunks(root: str, handovers_dir: str = None) -> list:
    """Varre a pasta memory/ (e opcionalmente handovers) e devolve os chunks.

    Cada chunk: {id, text, meta}. O `id` e estavel entre execucoes para o
    incremental funcionar: nome do no para arquivos de fato, posicao+sha para
    bullets do archive (se o bullet muda, o id muda — e o velho e removido).
    """
    chunks = []

    for fname in sorted(os.listdir(root)):
        if not fname.lower().endswith(".md"):
            continue
        key = og.norm(fname)
        path = os.path.join(root, fname)
        try:
            raw = open(path, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        mtime = os.path.getmtime(path)

        if key == "memory":
            continue  # indice quente: carregado no boot, indexa-lo so duplicaria

        if key == "memory_archive":
            for i, line in enumerate(raw.splitlines()):
                line = line.strip()
                if not line.startswith("- "):
                    continue
                text = line[2:].strip()
                if len(text) < 20:
                    continue
                chunks.append({
                    "id": f"archive::{_sha(text)}",
                    "text": text,
                    "meta": {"source": fname, "node": "memory_archive",
                             "kind": "archive_bullet", "line": i + 1,
                             "mtime": mtime, "sha": _sha(text)},
                })
            continue

        fm = og.parse_frontmatter(raw)
        body = og.strip_frontmatter(raw).strip()
        desc = fm.get("description", "")
        # a description entra no texto embedado: e o resumo curado a mao,
        # e ancora a busca melhor que o corpo sozinho
        text = (desc + "\n\n" + body).strip() if desc else body
        if not text:
            continue
        chunks.append({
            "id": key,
            "text": text,
            "meta": {"source": fname, "node": key,
                     "kind": fm.get("metadata.type") or og._type_from_name(key),
                     "mtime": mtime, "sha": _sha(text)},
        })

    if handovers_dir and os.path.isdir(handovers_dir):
        for fname in sorted(os.listdir(handovers_dir)):
            if not (fname.startswith("HANDOVER_") and fname.lower().endswith(".md")):
                continue
            path = os.path.join(handovers_dir, fname)
            try:
                raw = open(path, "r", encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            mtime = os.path.getmtime(path)
            body = og.strip_frontmatter(raw)
            parts = RE_SECTION.split(body)
            for j, part in enumerate(parts):
                text = part.strip()
                if len(text) < 40:
                    continue
                chunks.append({
                    "id": f"{og.norm(fname)}::s{j}",
                    "text": text[:4000],
                    "meta": {"source": fname, "node": "", "kind": "handover",
                             "section": j, "mtime": mtime, "sha": _sha(text)},
                })

    return chunks


# --------------------------------------------------------------------------
# embedding
# --------------------------------------------------------------------------
def get_embedder(model_name: str):
    """Devolve fn(list[str]) -> list[list[float]].

    `O1MEM_RAG_FAKE_EMBED=1` troca por um embedder deterministico de teste
    (hash -> vetor): a suite offline valida chunking/incremental/persistencia
    sem baixar 470 MB de modelo. NUNCA usar fora de teste — nao ha semantica.
    """
    if os.environ.get("O1MEM_RAG_FAKE_EMBED") == "1":
        def fake(texts):
            out = []
            for t in texts:
                h = hashlib.sha256(t.encode("utf-8")).digest()
                out.append([b / 255.0 for b in h[:32]])
            return out
        return fake, "fake-deterministic"

    # ambiente com TensorFlow+Keras 3 quebra o import do transformers pela
    # rota TF; o backend daqui e sempre torch — desliga a rota antes do import
    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("USE_TORCH", "1")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name)
    return (lambda texts: model.encode(texts, show_progress_bar=False).tolist(),
            model_name)


# --------------------------------------------------------------------------
# persistencia
# --------------------------------------------------------------------------
def get_collection(slug: str):
    import chromadb
    client = chromadb.PersistentClient(path=os.path.join(CHROMA_BASE, slug))
    return client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})


def _meta_path(slug: str) -> str:
    return os.path.join(CHROMA_BASE, slug, "o1mem_rag_meta.json")


def _save_meta(slug: str, model_name: str, n: int):
    meta = {"model": model_name, "chunks": n,
            "indexed_at": datetime.now(timezone.utc).isoformat()}
    with open(_meta_path(slug), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)


def _load_meta(slug: str) -> dict:
    try:
        return json.load(open(_meta_path(slug), "r", encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def index(slug: str, root: str, model_name: str, full: bool = False,
          handovers_dir: str = None) -> dict:
    col = get_collection(slug)
    chunks = collect_chunks(root, handovers_dir)

    if full:
        existing_ids = col.get(include=[])["ids"]
        if existing_ids:
            col.delete(ids=existing_ids)
        stale = {}
    else:
        got = col.get(include=["metadatas"])
        stale = {i: (m or {}).get("sha", "") for i, m in zip(got["ids"], got["metadatas"])}

    current_ids = {c["id"] for c in chunks}
    to_delete = [i for i in stale if i not in current_ids]
    to_embed = [c for c in chunks if stale.get(c["id"]) != c["meta"]["sha"]]

    embed_s = 0.0
    if to_embed:
        embed, model_name = get_embedder(model_name)
        t0 = time.time()
        vecs = embed([c["text"] for c in to_embed])
        embed_s = time.time() - t0
        col.upsert(
            ids=[c["id"] for c in to_embed],
            embeddings=vecs,
            documents=[c["text"] for c in to_embed],
            metadatas=[c["meta"] for c in to_embed],
        )
    if to_delete:
        col.delete(ids=to_delete)

    if not to_embed:
        # nada foi embedado: o modelo em vigor e o da indexacao anterior,
        # nao o argumento cru (que pode ser so o default nao-resolvido)
        model_name = _load_meta(slug).get("model", model_name)
    _save_meta(slug, model_name, len(current_ids))
    return {"project": slug, "chunks_total": len(current_ids),
            "embedded": len(to_embed), "deleted": len(to_delete),
            "unchanged": len(current_ids) - len(to_embed),
            "embed_seconds": round(embed_s, 2), "model": model_name}


def query(slug: str, root: str, text: str, k: int, model_name: str,
          with_graph: bool = True, with_distill: bool = False) -> dict:
    timings = {}
    t0 = time.time()
    embed, model_name = get_embedder(model_name)
    timings["model_load_s"] = round(time.time() - t0, 2)

    t0 = time.time()
    vec = embed([text])[0]
    timings["embed_s"] = round(time.time() - t0, 2)

    col = get_collection(slug)
    t0 = time.time()
    res = col.query(query_embeddings=[vec], n_results=min(k, max(col.count(), 1)),
                    include=["documents", "metadatas", "distances"])
    timings["search_s"] = round(time.time() - t0, 2)

    hits = []
    for i, doc, meta, dist in zip(res["ids"][0], res["documents"][0],
                                  res["metadatas"][0], res["distances"][0]):
        hits.append({"id": i, "score": round(1.0 - dist, 4),
                     "source": meta.get("source", ""), "kind": meta.get("kind", ""),
                     "node": meta.get("node", ""), "excerpt": doc[:300]})

    # o join com o grafo: para cada hit que E um no, os vizinhos estruturais
    # a 1 salto — o fio de raciocinio que a semantica nao enxerga
    if with_graph:
        t0 = time.time()
        g = og.build_graph(root, slug)
        ids = {n["id"] for n in g["nodes"]}
        for h in hits:
            if h["node"] and h["node"] in ids:
                h["graph_neighbors"] = [
                    {"id": n["id"], "description": n["description"][:110]}
                    for n in og.neighbors(g, h["node"], 1)[:5]
                ]
        timings["graph_s"] = round(time.time() - t0, 2)

    result = {"project": slug, "query": text, "model": model_name,
              "hits": hits, "timings": timings}

    # Modo aprendizado: destila top-k em parágrafo via LLM
    if with_distill:
        try:
            t0 = time.time()
            from o1mem_distill import distill
            result["distill"] = distill(text, hits)
            timings["distill_s"] = round(time.time() - t0, 2)
        except Exception as e:
            result["distill_error"] = str(e)

    return result


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Busca semantica da memoria O(1)mem")
    ap.add_argument("--project", help="slug (ou parte dele) do projeto")
    ap.add_argument("--root", help="caminho direto para uma pasta memory/")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--json", action="store_true", help="saida em JSON")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("index", help="(re)indexa a memoria do projeto")
    p.add_argument("--full", action="store_true", help="reconstroi do zero")
    p.add_argument("--handovers", help="pasta de HANDOVER_*.md a incluir")
    p = sub.add_parser("query", help="busca semantica + vizinhos do grafo")
    p.add_argument("text")
    p.add_argument("-k", type=int, default=3)
    p.add_argument("--no-graph", action="store_true", help="sem join com o grafo")
    p.add_argument("--distill", action="store_true", help="destila top-k via LLM (requer modo aprendizado)")
    sub.add_parser("stats", help="estado do indice vetorial")

    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 0

    slug, root = og.resolve_root(args.project, args.root)

    if args.cmd == "index":
        r = index(slug, root, args.model, args.full, args.handovers)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            print(f"projeto   : {r['project']}")
            print(f"chunks    : {r['chunks_total']}  "
                  f"(novos/mudados: {r['embedded']}, intocados: {r['unchanged']}, "
                  f"removidos: {r['deleted']})")
            print(f"embedding : {r['embed_seconds']}s  ({r['model']})")
            print(f"indice    : {os.path.join(CHROMA_BASE, slug)}")

    elif args.cmd == "query":
        r = query(slug, root, args.text, args.k, args.model,
                  with_graph=not args.no_graph, with_distill=args.distill)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            print(f"projeto : {r['project']}   modelo: {r['model']}")
            print(f"tempos  : {r['timings']}\n")
            for h in r["hits"]:
                print(f"[{h['score']:.3f}] {h['id']}  ({h['kind']})")
                print(f"        {h['excerpt'][:160]}")
                for n in h.get("graph_neighbors", []):
                    print(f"        ~ {n['id']}")
                print()
            if "distill" in r:
                print("✨ Destilado:\n" + r["distill"])
            elif "distill_error" in r:
                print(f"⚠️  Erro ao destilar: {r['distill_error']}")

    elif args.cmd == "stats":
        meta = _load_meta(slug)
        try:
            n = get_collection(slug).count()
        except Exception:
            n = 0
        r = {"project": slug, "persist_dir": os.path.join(CHROMA_BASE, slug),
             "chunks_in_collection": n, **meta}
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            for k, v in r.items():
                print(f"{k:>22}: {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
