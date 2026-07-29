#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
abrir_grafo.py — abre o grafo de navegação JÁ PREENCHIDO, sem passo manual.

Mesma razão do `abrir_dashboard.py`: uma página `file://` não lê arquivo local
sozinha (segurança do browser). Este launcher constrói o grafo na hora
(chamando `o1mem_graph.build_graph` — não há cache para ficar velho), injeta o
resultado como `window.__O1MEM_GRAPH__`, escreve um HTML temporário e abre.

As duas páginas do O(1)mem (grafo e painel) são irmãs e se linkam por caminho
RELATIVO, porque as duas vivem no mesmo diretório temporário. Para o link nunca
apontar para o vazio, este launcher **escreve as duas** e abre esta.

USO:
  python abrir_grafo.py                    # projeto único, ou lista se houver mais
  python abrir_grafo.py --project meuprojeto  # escolhe pelo slug (ou parte dele)
  python abrir_grafo.py --root <pasta>     # aponta uma pasta memory/ direta
  python abrir_grafo.py --no-open          # só grava o HTML e imprime o caminho
"""
import argparse
import json
import os
import sys
import tempfile
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from o1mem_graph import build_graph, resolve_root, stats  # noqa: E402

INDEX = os.path.join(HERE, "index.html")
OUT = os.path.join(tempfile.gettempdir(), "o1mem_grafo.html")


def write_page(project=None, root=None):
    """Constrói o grafo e grava a página em %TEMP%. Devolve (caminho, slug, stats)."""
    if not os.path.exists(INDEX):
        raise FileNotFoundError(INDEX)

    slug, memroot = resolve_root(project, root)
    g = build_graph(memroot, slug)

    html = open(INDEX, "r", encoding="utf-8").read()
    inject = "<script>window.__O1MEM_GRAPH__ = %s;</script>\n<script>" % json.dumps(
        g, ensure_ascii=False
    )
    if "<script>" in html:
        html = html.replace("<script>", inject, 1)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    return OUT, slug, stats(g), memroot, g


def write_sibling():
    """Escreve também o painel de economia, para o link entre as duas não pendurar.

    Falha em silêncio de propósito: o grafo é útil sozinho, e a ausência de um
    `handover-nudge.log` não pode impedir de abrir o grafo.
    """
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "dashboard"))
        import abrir_dashboard  # noqa: E402
        return abrir_dashboard.write_page()[0]
    except BaseException:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Abre o grafo de navegacao O(1)mem")
    ap.add_argument("--project", help="slug (ou parte) do projeto")
    ap.add_argument("--root", help="caminho direto para uma pasta memory/")
    ap.add_argument("--no-open", action="store_true", help="nao abre o navegador")
    args = ap.parse_args(argv)

    try:
        out, slug, s, memroot, g = write_page(args.project, args.root)
    except FileNotFoundError as e:
        print(f"ERRO: index.html nao encontrado em {e}")
        return 1

    print(f"projeto     : {slug}")
    print(f"origem      : {memroot}")
    print(f"nos/arestas : {s['nodes']} / {s['edges']}  (wiki: "
          f"{sum(1 for e in g['edges'] if e['kind'] == 'wiki')})")
    print(f"orfaos      : {s['orphans']}   quebrados: {s['broken']}   "
          f"componentes: {len(s['components'])}")

    sib = write_sibling()
    print(f"painel irmao: {sib if sib else '(nao gerado — link ficara inativo)'}")
    print(f"gravado     : {out}")

    if not args.no_open:
        webbrowser.open("file:///" + out.replace("\\", "/"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
