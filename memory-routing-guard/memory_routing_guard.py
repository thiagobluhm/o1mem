#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
memory_routing_guard.py — PreToolUse: barra memoria escrita no projeto ERRADO.

Por que existe
--------------
MEMORY.md e project_*.md sao indexados pelo DIRETORIO PRIMARIO da sessao, nao
pelo assunto. Quando a sessao abre num projeto A mas o conteudo escrito fala
de um projeto B (menciona o caminho de B no corpo), a memoria de B fica presa
na pasta de A -- ja aconteceu varias vezes (O(1)mem preso na pasta de outro projeto).

A regra "escrever no projeto do assunto" ja existia como memoria de feedback,
mas depender de o agente lembrar sozinho falhou repetidas vezes. Isto troca
"eu deveria lembrar" por "o harness recusa fisicamente o arquivo errado".

Como decide
-----------
So age em Write/Edit cujo file_path bate com
  .../.claude/projects/<slug>/memory/*.md
Dentro do conteudo (content do Write, new_string do Edit), procura mencoes a
caminho tipo `C:\Projetos\<pasta>...` ou `C:/Projetos/<pasta>...`. Para cada
mencao, deriva o slug esperado com a MESMA transformacao que o harness usa
pra nomear pastas de projeto (`C:\Projetos\O1MEM` -> `c--Projetos-O1MEM`) e
confere contra os slugs que REALMENTE existem em ~/.claude/projects/. Se a
mencao aponta pra um projeto existente DIFERENTE do slug do arquivo sendo
escrito, bloqueia e diz onde escrever.

Generico de proposito: nao tem lista fixa de projetos. Qualquer pasta nova
sob ~/.claude/projects/ entra automaticamente na checagem.

Fail-open: qualquer erro interno libera a escrita (nunca trava o fluxo por
um bug neste guarda).
"""
import json
import os
import re
import sys

HOME = os.path.expanduser("~")
PROJECTS_DIR = os.path.join(HOME, ".claude", "projects")

RE_MEM_PATH = re.compile(
    r"[/\\]\.claude[/\\]projects[/\\]([^/\\]+)[/\\]memory[/\\][^/\\]+\.md$",
    re.IGNORECASE,
)
# Mencao a caminho absoluto, nos dois mundos -- so a raiz do caminho importa:
#   Windows: `C:\Projetos\Foo\bar` ou `C:/Projetos/Foo/bar`   (ramo original)
#   POSIX:   `/Users/t/_PESSOAIS/o1mem/...`                    (acrescentado)
# O ramo Windows fica identico: em POSIX ele nunca casava nada, e o guarda
# passava por "aprovado" sem ter olhado. A alternativa POSIX exige uma letra
# logo apos a barra pra nao morder '/' solto no meio de texto corrido.
RE_PATH_MENTION = re.compile(
    r"([A-Za-z]:[\\/][^\s`\"'()]+"
    r"|/[A-Za-z][^\s`\"'()]*)"
)


def known_slugs():
    try:
        return {d for d in os.listdir(PROJECTS_DIR)
                if os.path.isdir(os.path.join(PROJECTS_DIR, d))}
    except OSError:
        return set()


def slugify(path_head):
    """Mesma convencao do harness. Copia local de tools/o1mem_slug.py.

    Duplicada de proposito: este guarda roda como hook standalone e nao pode
    importar de outra pasta do repo. tests/test_slug_for.py obriga esta copia
    a bater com a canonica.

    A versao anterior so trocava `:` e separadores, deixando o '_' passar --
    entao `/Users/t/_PESSOAIS/x` virava slug com '_' e nunca batia com pasta
    nenhuma. Divergir aqui e silencioso: o guarda nao reconhece o projeto
    mencionado e LIBERA a escrita no lugar errado, que e o que ele existe pra
    impedir. (Em caminho Windows com '_' o defeito era o mesmo.)

    O lowercase do drive e feito na mao, sem splitdrive: o guarda pode rodar
    num SO e ler mencao a caminho do outro, e splitdrive so entende o formato
    do SO em que roda.
    """
    p = path_head.rstrip("\\/")
    if len(p) >= 2 and p[1] == ":":
        p = p[0].lower() + p[1:]
    return re.sub(r"[^A-Za-z0-9]", "-", p)


def target_slug_from_file(file_path):
    m = RE_MEM_PATH.search(file_path.replace("\\", "/") if "/" not in file_path else file_path)
    if not m:
        # tenta tambem com barras normalizadas pros dois lados
        m = RE_MEM_PATH.search(file_path)
    return m.group(1) if m else None


def mentioned_foreign_slug(text, own_slug, slugs):
    for m in RE_PATH_MENTION.finditer(text or ""):
        raw = m.group(1)
        parts = re.split(r"[\\/]", raw)
        # Do mais longo pro mais curto: o prefixo MAIS especifico que bate com
        # um projeto existente e o certo. `.../ss_e_b/curriculos` e projeto
        # proprio -- parar em `.../ss_e_b` mandaria pra pasta errada.
        #
        # A faixa fixa (2,3,4) era medida pra `C:\Projetos\Foo`. Um caminho
        # POSIX de projeto tem mais componentes (e um vazio na frente, da barra
        # inicial), entao nunca alcancava a profundidade certa. Sem teto fixo,
        # projeto aninhado fundo tambem passa a ser encontrado no Windows.
        for depth in range(len(parts), 1, -1):
            # junta com '/' pra nao destruir a barra inicial do POSIX; slugify
            # trata os dois separadores igual de qualquer forma
            head = "/".join(parts[:depth])
            cand = slugify(head)
            if cand in slugs and cand != own_slug:
                return cand, head
    return None, None


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        return

    tool = data.get("tool_name") or ""
    if tool not in ("Write", "Edit"):
        return
    ti = data.get("tool_input") or {}
    file_path = ti.get("file_path") or ""
    own_slug = target_slug_from_file(file_path)
    if not own_slug:
        return  # nao e um arquivo de memoria -- nada a checar

    content = ti.get("content") if tool == "Write" else ti.get("new_string")
    if not content:
        return

    slugs = known_slugs()
    if own_slug not in slugs:
        return  # projeto novo, sem historico pra comparar -- deixa passar

    foreign, head = mentioned_foreign_slug(content, own_slug, slugs)
    if not foreign:
        return

    reason = (
        f"Memoria bloqueada: este arquivo e do projeto '{own_slug}' "
        f"(~/.claude/projects/{own_slug}/memory/), mas o conteudo fala de "
        f"'{head}' (projeto '{foreign}'). Escreva em "
        f"~/.claude/projects/{foreign}/memory/ em vez daqui -- "
        f"a memoria do assunto vai na pasta do assunto, nao na pasta onde a "
        f"sessao abriu."
    )
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # fail-open
