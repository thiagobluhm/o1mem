#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
handover.py — a parte MECÂNICA do handover, em código.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
A skill `handover` era 182 linhas de prosa. Prosa é advisory: cada sessão um
modelo relê, reinterpreta e improvisa uma execução diferente — daí os handovers
de 5 minutos, os desvios inventados no meio do caminho e os mesmos bugs
voltando (caminho de script errado, `| tail` mascarando exit code, regra de
cap/decay aplicada "mais ou menos"). Vinte rodadas de correção adicionaram MAIS
prosa e pioraram o problema.

Um handover é quase todo determinístico: coletar estado do git, achar caminhos,
preencher um template fixo, aplicar cap/decay na linha RETOMADA, indexar o RAG.
Só o JULGAMENTO (o porquê, o que falta, o próximo passo) exige um modelo. Este
script leva o mecânico pra código, onde a regra é executada e não interpretada.
É a mesma tese do O(1)mem — não faça o modelo re-derivar o que um script entrega
— aplicada ao único lugar do produto que a violava.

O QUE FICA MECÂNICO AQUI (e portanto não pode mais falhar por improviso)
  * caminhos resolvidos e VALIDADOS (o bug do `rag/` inexistente morre aqui)
  * exit code do RAG checado de verdade (nunca via pipe)
  * coerência modo × caveat: `verificada` EXIGE a seção, `rapida` a PROÍBE
  * cap de 2 linhas `(Anterior ...)` + decay de 30 dias na RETOMADA
  * fim de linha preservado (o repo é CRLF; sobrescrever com LF já mentiu num diff)
  * o handover só pode nascer em ~/.claude/projects/<slug>/handovers/ (trava)

ONDE O HANDOVER MORA
  Sempre `~/.claude/projects/<slug>/handovers/`, ao lado de `memory/` — derivado
  do SLUG, nunca do CWD. Antes era `<raiz-do-projeto>/documentacao`, o que fazia
  o local depender de onde a sessão abriu e punha texto com nome de cliente
  dentro do repo. Ver `handover_dir()` para o porquê inteiro. Pastas legadas são
  LIDAS e relatadas pelo `collect`, nunca escritas; `migrate` as esvazia.

USO
  python handover.py collect [--slug <slug>]
      Imprime o estado num bloco só: git, remotes, caminhos validados,
      handovers existentes, acervo legado pendente e a RETOMADA atual.
      Roda ANTES de redigir.

  python handover.py write --task <slug-da-tarefa> --mode rapida|verificada \\
                           --body <arquivo.md> --breadcrumb <arquivo.txt> [--slug <slug>]
      Monta o handover a partir do template + corpo, grava no local canônico,
      atualiza a RETOMADA (cap+decay) e indexa o RAG. Imprime o que fez.

  python handover.py migrate [--slug <slug>] [--dry-run]
      Move HANDOVER_*.md das pastas legadas para o local canônico. Explícito de
      propósito, nunca sobrescreve.
"""
import argparse
import datetime as _dt
import io
import os
import re
import subprocess
import sys

# O console do Windows abre em cp1252 e explode ao imprimir os emojis que a
# memoria usa (✅/⚠️). Isso derrubava o `collect` inteiro na hora de mostrar a
# RETOMADA -- um erro de TERMINAL matando a coleta. errors='replace': melhor um
# '?' na tela que perder o relatorio.
for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CAP_ANTERIORES = 2      # teto O(1) de linhas "(Anterior ...)"
DECAY_DIAS = 30         # mesmo limiar do Passo 4 da skill — não invente um segundo

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_DIR = os.path.normpath(os.path.expanduser("~/.claude/projects"))

# O projeto vem do CWD, nunca da pasta do script. Instalado em
# ~/.claude/skills/handover/, derivar do __file__ apontaria PROJ_ROOT pra
# ~/.claude -- gravaria o handover no lugar errado. O script tem que rodar
# igual no repo e instalado.


def slug_for(path):
    """C:\\Projetos\\O1MEM -> c--Projetos-O1MEM"""
    drive, rest = os.path.splitdrive(os.path.abspath(path))
    return (drive[:1].lower() + "--" +
            rest.replace("\\", "/").strip("/").replace("/", "-"))


def handover_dir(slug):
    """O UNICO lugar onde um handover pode ser gravado.

    Derivado do SLUG, nunca do CWD. Duas razoes, nessa ordem:

    1. TIRA O PALPITE. O local antigo era `<raiz>/documentacao`, e a raiz vinha
       de subir o CWD ate achar `memory/`. Ou seja: onde o handover morava
       dependia de onde a sessao abriu. Um projeto que guardasse os handovers em
       `backend/documentacao` (caso real) ficava com dois lugares e nenhum certo
       -- o `write` gravava num, o acervo antigo ficava no outro, e o RAG so
       via metade. O slug ja e a chave de `memory/` e da collection do Chroma;
       usar a mesma chave aqui faz o caminho ser CONSEQUENCIA, nao adivinhacao.

    2. NAO VAZA. O caminho antigo caia DENTRO do repo. Nao vazou ate hoje por
       tres acidentes independentes (dois .gitignore diferentes e, num caso, o
       repo por acaso ser uma subpasta) -- nenhum deles desenhado, nenhum deles
       herdado pelo proximo projeto. Handover cita cliente, credencial e caminho
       interno; fora do repo ele nao tem como ser commitado por engano.
    """
    return os.path.join(PROJECTS_DIR, slug, "handovers")


# Locais onde handovers FORAM gravados antes da mudanca. Lidos, nunca escritos:
# um fallback que tambem escreve reconstroi exatamente a ambiguidade que a
# mudanca existe para matar (duas verdades sobre onde mora um handover).
LEGACY_RELS = ("documentacao", "backend/documentacao", "doc", "docs")

# Casa o padrao HANDOVER_*.md mas NAO e handover: e um indice DERIVADO, gerado
# por script a partir dos outros. Migra-lo tira o indice de perto do gerador que
# o escreve, e indexa-lo enche o RAG de titulos repetidos -- ruido que compete
# com o texto real na busca. Excluido por nome, nao por heuristica.
NAO_E_HANDOVER = {"handover_index.md"}


def is_handover_file(fname):
    return (fname.startswith("HANDOVER_") and fname.endswith(".md")
            and fname.lower() not in NAO_E_HANDOVER)


def legacy_handover_dirs(root):
    """Pastas legadas que AINDA contem HANDOVER_*.md. Somente leitura."""
    if not root:
        return []
    out = []
    for rel in LEGACY_RELS:
        d = os.path.join(root, *rel.split("/"))
        if not os.path.isdir(d):
            continue
        try:
            if any(is_handover_file(f) for f in os.listdir(d)):
                out.append(d)
        except OSError:
            pass
    return out


def assert_canonical(dest, slug):
    """Trava de escrita. A regra nova vai em CODIGO, nunca em paragrafo.

    Sem isto, 'deixar de gravar na raiz' seria um habito -- e a primeira excecao
    traria o problema de volta em silencio."""
    canon = os.path.abspath(handover_dir(slug)).rstrip("\\/")
    got = os.path.abspath(dest)
    if os.path.normcase(os.path.dirname(got)) != os.path.normcase(canon):
        die("BUG: handover so pode ser gravado em %s (destino recebido: %s)"
            % (canon, got))


def find_project_root(explicit_slug=None):
    """(raiz, slug) — sobe do CWD ate achar um ancestral com memory/ indexada.

    Amarra a raiz do projeto a pasta de memoria que existe de verdade, em vez
    de adivinhar por profundidade de caminho (o repo aqui e <raiz>/skills, mas
    isso nao vale pra todo projeto).
    """
    cur = os.path.abspath(os.getcwd())
    cands = []
    while True:
        cands.append(cur)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    for c in cands:
        s = slug_for(c)
        if explicit_slug and s != explicit_slug:
            continue
        if os.path.isdir(os.path.join(PROJECTS_DIR, s, "memory")):
            return c, s
    if explicit_slug and os.path.isdir(os.path.join(PROJECTS_DIR, explicit_slug, "memory")):
        return cands[0], explicit_slug        # slug forcado, raiz = cwd
    return None, None


def find_git_root():
    """Acha o repo git: sobe do CWD e, se nao achar, olha UM nivel abaixo.

    O 'abaixo' importa porque o repo nem sempre e a raiz do projeto (aqui e
    <raiz>/skills): rodando da raiz, subir nao encontra nada e o relatorio
    perderia branch/HEAD/remotes sem dizer por que."""
    cur = os.path.abspath(os.getcwd())
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    base = os.path.abspath(os.getcwd())
    try:
        for d in sorted(os.listdir(base)):
            p = os.path.join(base, d)
            if os.path.isdir(p) and os.path.exists(os.path.join(p, ".git")):
                return p
    except OSError:
        pass
    return None


def find_rag(proj_root):
    """Acha o o1mem_rag.py onde ele possa estar.

    Primeiro o `rag_cli` do ~/.claude/o1mem/config.json, que o installer grava:
    numa instalacao via npm o pacote pode estar em qualquer node_modules ou no
    cache do npx, e nenhum caminho relativo acerta. Sem isso a indexacao era
    silenciosamente pulada pra quem instalou pelo pacote."""
    cands = []
    cfg = os.path.expanduser("~/.claude/o1mem/config.json")
    if os.path.exists(cfg):
        try:
            import json
            with io.open(cfg, "r", encoding="utf-8") as f:
                v = json.load(f).get("rag_cli")
            if v:
                cands.append(v)
        except (ValueError, OSError):
            pass
    cands += [
        os.path.join(SCRIPT_DIR, os.pardir, "rag", "o1mem_rag.py"),
        os.path.join(SCRIPT_DIR, "o1mem_rag.py"),
        os.path.join(SCRIPT_DIR, os.pardir, os.pardir, "vendor", "rag", "o1mem_rag.py"),
    ]
    if proj_root:
        cands += [os.path.join(proj_root, "skills", "rag", "o1mem_rag.py"),
                  os.path.join(proj_root, "rag", "o1mem_rag.py")]
    for c in cands:
        c = os.path.normpath(c)
        if os.path.exists(c):
            return c
    return None


# ---------------------------------------------------------------- utilidades
def run(args, cwd=None):
    """Executa e devolve (rc, stdout+stderr). SEM pipe: o rc é o do processo.

    O bug que isto elimina: `cmd | tail -5` devolve o rc do `tail` (0 sempre),
    então uma falha do processo real passa como sucesso.
    """
    try:
        p = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, universal_newlines=True)
        return p.returncode, (p.stdout or "").strip()
    except OSError as e:
        return 127, str(e)


def git(*a):
    return run(["git"] + list(a), cwd=find_git_root() or os.getcwd())


def read_keep_eol(path):
    """Lê preservando o fim de linha real do arquivo. Devolve (texto, eol)."""
    with io.open(path, "r", encoding="utf-8", newline="") as f:
        txt = f.read()
    return txt, ("\r\n" if "\r\n" in txt else "\n")


def write_keep_eol(path, txt):
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(txt)


def die(msg):
    sys.stderr.write("ERRO: %s\n" % msg)
    raise SystemExit(1)


def today():
    return _dt.date.today()


# ------------------------------------------------------------ resolução de caminhos
def resolve(explicit=None):
    """(slug, dict-de-caminhos) — tudo resolvido a partir do CWD e VALIDADO."""
    root, slug = find_project_root(explicit)
    if not slug:
        try:
            disp = "\n       ".join(sorted(
                s for s in os.listdir(PROJECTS_DIR)
                if os.path.isdir(os.path.join(PROJECTS_DIR, s, "memory"))))
        except OSError:
            disp = "(nao consegui listar %s)" % PROJECTS_DIR
        die("nenhum ancestral de %s tem memoria indexada.\n"
            "       Rode de dentro do projeto ou passe --slug. Disponiveis:\n       %s"
            % (os.getcwd(), disp))
    mem_dir = os.path.join(PROJECTS_DIR, slug, "memory")
    memory_md = os.path.join(mem_dir, "MEMORY.md")
    if not os.path.exists(memory_md):
        die("caminho obrigatorio ausente: %s" % memory_md)
    return slug, {"root": root, "mem_dir": mem_dir, "memory_md": memory_md,
                  "doc_dir": handover_dir(slug),
                  "legacy": legacy_handover_dirs(root),
                  "git": find_git_root(), "rag": find_rag(root)}


# --------------------------------------------------------------------- collect
def retomada_block(memory_md):
    """Devolve (linhas_do_bloco, indice_inicio, indice_fim_exclusivo)."""
    txt, _ = read_keep_eol(memory_md)
    lines = txt.splitlines()
    start = next((i for i, l in enumerate(lines) if "**RETOMADA" in l), None)
    if start is None:
        return [], None, None
    end = start
    while end < len(lines) and lines[end].lstrip().startswith(">"):
        end += 1
    return lines[start:end], start, end


def cmd_collect(args):
    slug, P = resolve(args.slug)

    rc_b, branch = git("branch", "--show-current")
    _, head = git("rev-parse", "HEAD")
    _, dirty = git("status", "--short")
    _, log3 = git("log", "--oneline", "-3")
    _, remotes = git("remote")

    print("=" * 68)
    print("HANDOVER collect")
    print("=" * 68)
    print("projeto     : %s" % slug)
    print("raiz projeto: %s" % P["root"])
    print("repo git    : %s" % (P["git"] or "(nenhum .git acima do cwd)"))
    print("handovers   : %s%s" % (P["doc_dir"],
                                  "" if os.path.isdir(P["doc_dir"]) else "  (sera criada)"))
    print("memory      : %s" % P["mem_dir"])
    print("rag         : %s" % (P["rag"] or "AUSENTE -- indexacao sera pulada"))
    print()
    print("branch      : %s" % (branch if rc_b == 0 else "(sem git)"))
    print("HEAD        : %s" % head[:12])
    print("tree        : %s" % ("LIMPA" if not dirty else "SUJA"))
    if dirty:
        for l in dirty.splitlines():
            print("              %s" % l)

    for r in [x for x in remotes.splitlines() if x.strip()]:
        rc, out = run(["git", "ls-remote", r, "refs/heads/" + (branch or "main")])
        if rc != 0:
            print("remote %-8s: INACESSIVEL" % r)
            continue
        sha = out.split()[0] if out.split() else "(vazio)"
        same = "EM SINCRONIA" if sha.startswith(head[:12]) else "DIVERGENTE (falta push?)"
        print("remote %-8s: %s  %s" % (r, sha[:12], same))

    print()
    print("ultimos commits:")
    for l in log3.splitlines():
        print("  %s" % l)

    print()
    if os.path.isdir(P["doc_dir"]):
        hs = sorted((f for f in os.listdir(P["doc_dir"])
                     if is_handover_file(f)), reverse=True)
        print("handovers existentes (3 mais recentes):")
        for f in hs[:3]:
            print("  %s" % f)
        if not hs:
            print("  (nenhum)")

    # Legado: LIDO e RELATADO, nunca escrito. O barulho aqui e proposital --
    # handover em pasta legada esta FORA do corpus indexado, entao o RAG nao o
    # alcanca e a retomada nao sabe que ele existe. Silenciar isso seria repetir
    # o bug do `index` sem --handovers: perda que nao se anuncia.
    if P["legacy"]:
        tot = 0
        print()
        print("!! ACERVO LEGADO FORA DO CORPUS -- estes NAO sao indexados:")
        for d in P["legacy"]:
            n = len([f for f in os.listdir(d) if is_handover_file(f)])
            tot += n
            print("   %-58s %3d handover(s)" % (d, n))
        print("   Migre com:  python %s migrate --slug %s"
              % (os.path.basename(__file__), slug))
        print("   (move %d arquivo(s); nada e sobrescrito)" % tot)

    print()
    blk, _, _ = retomada_block(P["memory_md"])
    print("RETOMADA atual no MEMORY.md:")
    for l in (blk or ["  (nenhuma linha RETOMADA)"]):
        print("  %s" % l[:150])

    ant = [l for l in blk if "(Anterior" in l]
    print()
    print("linhas (Anterior ...): %d   -> cap=%d, decay=%dd aplicados no write"
          % (len(ant), CAP_ANTERIORES, DECAY_DIAS))
    print("=" * 68)
    print("TRAVA DE VALOR (Passo 0): tree %s, remote %s."
          % ("limpa" if not dirty else "suja",
             "sincronizado" if not dirty else "conferir"))
    print("Se nao ha estado pendente, raciocinio caro nem plano nao executado,")
    print("NAO escreva handover -- grave so a memoria.")
    print("=" * 68)
    return 0


# ----------------------------------------------------------------------- write
TEMPLATE = """# HANDOVER — {task} ({data})
> retomada: {mode}

{body}
"""


def check_mode_coherence(mode, body):
    """A regra que a prosa nunca conseguiu garantir, agora executada."""
    has = bool(re.search(r"^##\s*Caveat de estado vivo", body, re.M))
    if mode == "verificada" and not has:
        die("modo 'verificada' EXIGE a secao '## Caveat de estado vivo' no --body.\n"
            "       Se nao ha nada checavel no runtime, o caso e 'rapida'.")
    if mode == "rapida" and has:
        die("modo 'rapida' PROIBE a secao '## Caveat de estado vivo'.\n"
            "       Se voce sentiu necessidade de escreve-la, o caso e 'verificada'.")


def _links(s):
    """Wikilinks na ordem, sem repetir."""
    out = []
    for r in re.findall(r"\[\[([^\]]+)\]\]", s):
        if r not in out:
            out.append(r)
    return out


def _colapsa_anterior(entry_lines):
    """Junta uma entrada '(Anterior ...)' multi-linha numa linha, mantendo links."""
    txt = " ".join(l.lstrip("> ").strip() for l in entry_lines)
    txt = re.sub(r"\s+", " ", txt).strip()
    if len(entry_lines) == 1:
        return "> " + txt
    # Reconstroi o rotulo em vez de confiar no strip: `.strip(" .,;—-")` comia o
    # "- " do prefixo (o '-' esta no conjunto) e o ponto final antes de "Ver".
    m = re.match(r"-?\s*\((Anterior[^)]*)\)\s*(.*)$", txt)
    if not m:
        return "> " + _cut(txt, 170)
    rotulo, resto = m.group(1), m.group(2)
    refs = _links(resto)
    corpo = re.sub(r"\s*Ver\s*(\[\[[^\]]+\]\][,\s]*)+\.?", "", resto).strip(" .,;—-")
    return "> - (%s) %s.%s" % (rotulo, _cut(corpo, 150),
                               (" Ver " + ", ".join("[[%s]]" % r for r in refs) + ".") if refs else "")


def _cut(s, n):
    """Corta em FRONTEIRA DE PALAVRA. Cortar no caractere n gerava linha
    incoerente ('commit b6ddbd5' -> 'com') -- resumo mutilado e pior que curto."""
    if len(s) <= n:
        return s
    corte = s[:n].rsplit(" ", 1)[0].rstrip(" .,;—-")
    return (corte or s[:n]) + "…"


def parse_date(s):
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if not m:
        return None
    try:
        return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def update_retomada(memory_md, new_text):
    """Promove a RETOMADA atual a '(Anterior ...)', insere a nova, aplica cap+decay.

    Devolve lista de strings descrevendo o que mudou (pra imprimir honestamente).
    """
    txt, eol = read_keep_eol(memory_md)
    lines = txt.split(eol)
    blk, start, end = retomada_block(memory_md)
    notas = []

    # Parsing por ENTRADA, nao por linha. Uma entrada "(Anterior ...)" pode
    # ocupar 2+ linhas (continuacao indentada); filtrar linha-a-linha por
    # '(Anterior' jogava a CONTINUACAO no bloco atual e vazava o texto/link de
    # uma entrada velha para dentro da RETOMADA nova.
    ini = next((i for i, l in enumerate(blk) if re.match(r"^>\s*-\s*\(Anterior", l)), len(blk))
    atual = blk[:ini]
    antigos = []
    for l in blk[ini:]:
        if re.match(r"^>\s*-\s*\(Anterior", l):
            antigos.append([l])
        elif antigos:
            antigos[-1].append(l)
    # cada entrada vira UMA linha (o historico e terse por desenho), com os
    # links dela preservados
    antigos = [_colapsa_anterior(e) for e in antigos]

    # a RETOMADA que sai vira uma linha "(Anterior ...)" de UMA linha, terse
    promovida = None
    if atual:
        head = " ".join(l.lstrip("> ").strip() for l in atual)
        d = parse_date(head) or today()
        # TODOS os wikilinks, nao so o primeiro: o invariante do MEMORY.md e
        # "nunca drope um link" -- cada [[x]] e load-bearing pro protocolo de
        # save achar o arquivo que cobre um fato.
        refs = _links(head)
        resumo = re.sub(r"\*\*RETOMADA[^*]*\*\*", "", head)
        resumo = re.sub(r"\[\[[^\]]+\]\]", "", resumo)      # links vao no fim
        resumo = re.sub(r"\s+", " ", resumo).strip(" .,;—-")
        resumo = _cut(resumo, 150)
        promovida = "> - (Anterior %s) %s%s" % (
            d.isoformat(), resumo,
            (" Ver " + ", ".join("[[%s]]" % r for r in refs) + ".") if refs else "")
        notas.append("RETOMADA anterior promovida a '(Anterior %s)' (%d link(s) preservado(s))"
                     % (d.isoformat(), len(refs)))

    hist = ([promovida] if promovida else []) + antigos

    # DECAY: fora quem passou de 30 dias
    vivos = []
    for l in hist:
        d = parse_date(l)
        if d and (today() - d).days > DECAY_DIAS:
            notas.append("decay: dropada '(Anterior %s)' (>%dd)" % (d.isoformat(), DECAY_DIAS))
            continue
        vivos.append(l)

    # CAP: no máximo N
    if len(vivos) > CAP_ANTERIORES:
        for l in vivos[CAP_ANTERIORES:]:
            d = parse_date(l)
            notas.append("cap: dropada '(Anterior %s)' (teto=%d)"
                         % (d.isoformat() if d else "?", CAP_ANTERIORES))
        vivos = vivos[:CAP_ANTERIORES]

    novo = [l if l.startswith(">") else "> " + l
            for l in new_text.strip().split("\n")] + vivos

    if start is None:                       # sem bloco: insere depois do H1
        h1 = next((i for i, l in enumerate(lines) if l.startswith("# ")), -1)
        lines[h1 + 1:h1 + 1] = [""] + novo
        notas.append("bloco RETOMADA criado (nao existia)")
    else:
        lines[start:end] = novo

    write_keep_eol(memory_md, eol.join(lines))
    notas.append("MEMORY.md gravado preservando %s" % ("CRLF" if eol == "\r\n" else "LF"))
    return notas


def cmd_write(args):
    slug, P = resolve(args.slug)

    for f in (args.body, args.breadcrumb):
        if not os.path.exists(f):
            die("arquivo nao encontrado: %s" % f)

    body = io.open(args.body, "r", encoding="utf-8").read().strip()
    breadcrumb = io.open(args.breadcrumb, "r", encoding="utf-8").read().strip()
    if not body or not breadcrumb:
        die("--body e --breadcrumb nao podem estar vazios")

    check_mode_coherence(args.mode, body)

    d = today()
    name = "HANDOVER_%s_%s.md" % (args.task, d.strftime("%Y%m%d"))
    if not os.path.isdir(P["doc_dir"]):
        os.makedirs(P["doc_dir"])
    dest = os.path.join(P["doc_dir"], name)
    assert_canonical(dest, slug)

    write_keep_eol(dest, TEMPLATE.format(
        task=args.task.replace("_", " "), data=d.strftime("%d/%m/%Y"),
        mode=args.mode, body=body).replace("\n", "\r\n"))

    notas = update_retomada(P["memory_md"], breadcrumb)

    print("handover  : %s" % dest)
    print("modo      : %s  (coerencia modo x caveat OK)" % args.mode)
    for n in notas:
        print("memoria   : %s" % n)

    if P["rag"]:
        # --handovers e OBRIGATORIO, nao opcional: o `index` deriva os ids
        # vigentes do que collect_chunks() devolve, entao indexar sem a pasta
        # nao apenas deixa de somar o acervo frio -- ele DELETA os chunks de
        # handover ja indexados (viram to_delete). O frio e justamente o que o
        # cap tira da memoria; sem ele o RAG so reindexa o que ja e O(1).
        rc, out = run([sys.executable, P["rag"], "--project", slug, "index",
                       "--handovers", P["doc_dir"]])
        if rc == 0:
            linha = next((l for l in out.splitlines() if l.startswith("chunks")), out[:120])
            print("rag       : OK  %s" % linha.strip())
        else:
            print("rag       : FALHOU (rc=%d) -- handover e memoria ESTAO gravados" % rc)
            print("            %s" % out.splitlines()[-1][:160] if out else "")
    else:
        print("rag       : pulado (script ausente)")
    return 0


def cmd_migrate(args):
    """Move handovers das pastas legadas para o local canonico.

    EXPLICITO de proposito. Mover arquivo do usuario em silencio dentro de um
    `write` seria pior que o bug: ele descobriria depois, sem saber o que mexeu.
    Nunca sobrescreve -- colisao de nome vira aviso, nao perda.
    """
    slug, P = resolve(args.slug)
    if not P["legacy"]:
        print("nada a migrar: nenhuma pasta legada com HANDOVER_*.md em %s" % P["root"])
        return 0

    if not os.path.isdir(P["doc_dir"]):
        os.makedirs(P["doc_dir"])

    movidos = pulados = 0
    for d in P["legacy"]:
        for f in sorted(os.listdir(d)):
            if not is_handover_file(f):
                continue
            src, dst = os.path.join(d, f), os.path.join(P["doc_dir"], f)
            if os.path.exists(dst):
                print("  PULADO (ja existe no destino): %s" % f)
                pulados += 1
                continue
            assert_canonical(dst, slug)
            if args.dry_run:
                print("  [dry-run] %s -> %s" % (src, dst))
            else:
                os.rename(src, dst)
            movidos += 1

    print("migrados  : %d%s" % (movidos, "  (dry-run, nada foi movido)"
                                if args.dry_run else ""))
    if pulados:
        print("pulados   : %d (nome ja existente -- resolva a mao)" % pulados)
    print("destino   : %s" % P["doc_dir"])
    if not args.dry_run and movidos:
        print("Reindexe:   python <o1mem_rag.py> --project %s index --handovers %s"
              % (slug, P["doc_dir"]))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Parte mecanica do handover")
    sub = ap.add_subparsers(dest="cmd")

    c = sub.add_parser("collect", help="coleta e valida o estado (rode ANTES de redigir)")
    c.add_argument("--slug")
    c.set_defaults(fn=cmd_collect)

    w = sub.add_parser("write", help="grava handover + RETOMADA + indexa RAG")
    w.add_argument("--task", required=True, help="slug curto da tarefa")
    w.add_argument("--mode", required=True, choices=["rapida", "verificada"])
    w.add_argument("--body", required=True, help="arquivo .md com as secoes de julgamento")
    w.add_argument("--breadcrumb", required=True, help="arquivo com o texto da RETOMADA")
    w.add_argument("--slug")
    w.set_defaults(fn=cmd_write)

    m = sub.add_parser("migrate", help="move handovers legados para o local canonico")
    m.add_argument("--slug")
    m.add_argument("--dry-run", action="store_true", help="mostra o que faria, sem mover")
    m.set_defaults(fn=cmd_migrate)

    args = ap.parse_args(argv)
    if not getattr(args, "fn", None):
        ap.print_help()
        return 2
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
