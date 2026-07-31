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
# `C:\Projetos\Foo\bar` ou `C:/Projetos/Foo/bar` -- so a raiz do caminho importa
RE_PATH_MENTION = re.compile(r"([A-Za-z]:[\\/][^\s`\"'()]+)")


def known_slugs():
    try:
        return {d for d in os.listdir(PROJECTS_DIR)
                if os.path.isdir(os.path.join(PROJECTS_DIR, d))}
    except OSError:
        return set()


def slugify(path_head):
    """Mesma convencao do harness: letra minuscula, `:` e separadores -> `-`."""
    p = path_head.rstrip("\\/")
    if len(p) >= 2 and p[1] == ":":
        p = p[0].lower() + p[1:]
    p = p.replace(":", "-").replace("\\", "-").replace("/", "-")
    return p


def target_slug_from_file(file_path):
    m = RE_MEM_PATH.search(file_path.replace("\\", "/") if "/" not in file_path else file_path)
    if not m:
        # tenta tambem com barras normalizadas pros dois lados
        m = RE_MEM_PATH.search(file_path)
    return m.group(1) if m else None


def mentioned_foreign_slug(text, own_slug, slugs):
    for m in RE_PATH_MENTION.finditer(text or ""):
        raw = m.group(1)
        # só a raiz de 2-3 componentes basta pra identificar o projeto
        parts = re.split(r"[\\/]", raw)
        for depth in (2, 3, 4):
            if len(parts) < depth:
                break
            head = "\\".join(parts[:depth])
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
