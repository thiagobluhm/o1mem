#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
abrir_dashboard.py — abre o painel O(1)mem JÁ PREENCHIDO, sem upload manual.

Por que existe: uma página file:// no navegador NÃO lê arquivo local sozinha
(segurança do browser). Então este launcher faz o trabalho: acha os logs de nudge
automaticamente, injeta os dados no HTML como `window.__O1MEM_DATA__`, escreve um
HTML temporário e abre no navegador — já com KPIs e gráfico na tela.

As duas páginas do O(1)mem (painel e grafo) são irmãs e se linkam por caminho
RELATIVO, porque as duas vivem no mesmo diretório temporário. Para o link nunca
apontar para o vazio, este launcher **escreve as duas** e abre esta.

USO:  python abrir_dashboard.py
      python abrir_dashboard.py --no-open     (só grava e imprime o caminho)

Logs lidos (o que existir):
  ~/.claude/handover-nudge.log                     (Claude Code)
  ~/AppData/Local/hermes/handover-nudge.log        (Hermes)
"""
import json
import os
import sys
import tempfile
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "index.html")
OUT = os.path.join(tempfile.gettempdir(), "o1mem_dashboard.html")

LOGS = [
    os.path.expanduser("~/.claude/handover-nudge.log"),
    os.path.expanduser("~/AppData/Local/hermes/handover-nudge.log"),
]


def read_jsonl(path):
    """Lê um .log JSONL; ignora linhas inválidas. Retorna lista de dicts."""
    out = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        pass
    return out


def write_page():
    """Grava o painel preenchido em %TEMP% e devolve (caminho, achados, n_eventos)."""
    if not os.path.exists(INDEX):
        raise FileNotFoundError(INDEX)

    records, achados = [], []
    for p in LOGS:
        if os.path.exists(p):
            r = read_jsonl(p)
            records += r
            achados.append(f"{len(r):>4} eventos  {p}")

    html = open(INDEX, "r", encoding="utf-8").read()
    # injeta os dados ANTES da tag <script> principal (o global precisa existir
    # quando o gancho de auto-carga rodar, no fim do script). O painel abre
    # GLOBAL por padrao (todos os projetos + legado sem tag juntos) -- os
    # chips de projeto (index.html) so restringem se o usuario clicar, nunca
    # pre-selecionam sozinhos.
    if records and "<script>" in html:
        payload = json.dumps(records, ensure_ascii=False)
        html = html.replace(
            "<script>",
            f"<script>window.__O1MEM_DATA__ = {payload};</script>\n<script>",
            1,
        )

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    return OUT, achados, len(records)


def write_sibling():
    """Escreve também a página do grafo, para o link entre as duas não pendurar.

    Falha em silêncio de propósito: o painel é útil sozinho, e um erro ao montar
    o grafo (pasta memory/ ausente, projeto ambíguo) não pode impedir de abrir o
    painel. O link some do fluxo, não a ferramenta.
    """
    try:
        gdir = os.path.join(os.path.dirname(HERE), "graph")
        sys.path.insert(0, gdir)
        import abrir_grafo          # noqa: E402
        import o1mem_graph          # noqa: E402
        # não dá para perguntar qual projeto aqui; usa o de memória mais fresca
        # como DEFAULT selecionado -- mas passando `project=` (não `root=`), que
        # ainda monta as outras collections e liga o seletor da UI. `root=`
        # força modo single-project (sem picker), que era o bug: o grafo irmão
        # do painel abria sempre travado no projeto mais fresco, sem trocar.
        pick = o1mem_graph.freshest_root()
        return abrir_grafo.write_page(project=pick[0] if pick else None)[0]
    except BaseException:
        # BaseException de propósito: resolve_root sinaliza erro com SystemExit,
        # que não é Exception e derrubaria o painel inteiro por uma página irmã.
        return None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        out, achados, n = write_page()
    except FileNotFoundError as e:
        print(f"ERRO: index.html nao encontrado em {e}")
        return 1

    if achados:
        print("Logs encontrados:")
        for a in achados:
            print("  " + a)
        print(f"Total: {n} eventos embutidos.")
    else:
        print("Nenhum log de nudge encontrado — abrindo vazio (modo upload).")
        print("  (procurei em: " + " ; ".join(LOGS) + ")")

    sib = write_sibling()
    print(f"grafo irmao : {sib if sib else '(nao gerado — link ficara inativo)'}")
    print(f"Abrindo: {out}")

    if "--no-open" not in argv:
        webbrowser.open("file:///" + out.replace("\\", "/"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
