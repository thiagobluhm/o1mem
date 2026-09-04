#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check-artefatos.py — impede que artefato DERIVADO da memoria entre no repo.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
A regra ja estava escrita em dois lugares (`.gitignore` e o CONTRIBUTING) e
mesmo assim nao valia: `.gitignore` e uma sugestao que `git add -f` atropela, e
prosa em CONTRIBUTING depende de alguem ler. O contrato deste projeto e que
regra nova vai em CODIGO, e este e o codigo.

O que esta em jogo nao e organizacao. O `graph/graph.json` desta maquina foi
gerado a partir da memoria de OUTRO projeto -- carrega titulos, descricoes e o
fio de raciocinio de trabalho de cliente. Este repo e publico. Um `add -f`
distraido, ou um `git add .` num dia em que o .gitignore tenha sido mexido, e o
vazamento acontece de uma vez e para sempre (fica no historico).

Roda em dois momentos, de proposito:
  * no `pre-commit`, onde ainda da para desfazer sem custo;
  * no CI, que e onde nao ha como desfazer, mas tambem nao ha como esquecer.

USO
  python tools/check-artefatos.py            # o que ja esta rastreado no repo
  python tools/check-artefatos.py --staged   # o que esta prestes a ser commitado

EXIT
  0 = limpo   1 = artefato encontrado
"""
import argparse
import os
import re
import subprocess
import sys

# Cada padrao vem com o MOTIVO. Uma lista de regex sem motivo vira lista que
# ninguem ousa mexer, porque ninguem lembra por que cada linha esta ali.
PROIBIDOS = [
    (re.compile(r"(^|/)graph\.json$"),
     "grafo construido a partir da memoria: carrega titulo, descricao e o fio "
     "de raciocinio dos projetos. E derivado -- `o1mem_graph.py build` refaz."),
    (re.compile(r"(^|/)chroma(/|$)|\.sqlite3?$|(^|/)chroma\.sqlite"),
     "indice vetorial: contem os proprios textos da memoria, embedados."),
    (re.compile(r"(^|/)o1mem_dashboard\.html$|(^|/)o1mem_grafo\.html$"),
     "pagina gerada com dados de sessao dentro."),
    (re.compile(r"(^|/)handover-nudge\.log$|(^|/)handover-nudge-state(/|$)|\.log$"),
     "telemetria das suas sessoes: caminhos, nomes de projeto, contagem de tokens."),
    (re.compile(r"(^|/)snapshots?(/|$)|(^|/)SNAPSHOT_.*\.md$"),
     "captura bruta de sessao: perguntas do usuario e comandos rodados, sem "
     "curadoria. Mora em ~/.claude/projects/, nunca num repo."),
    (re.compile(r"(^|/)HANDOVER_.*\.md$"),
     "handover cita cliente, credencial e caminho interno. Mora em "
     "~/.claude/projects/<slug>/handovers/, fora de qualquer repo."),
    (re.compile(r"(^|/)MEMORY(_ARCHIVE)?\.md$"),
     "memoria de projeto real: nao e codigo deste produto."),
]

# Excecao unica e explicita: o gabarito de avaliacao e conteudo CURADO e
# revisado, escrito para ser publico. Nao e artefato gerado.
ISENTOS = (re.compile(r"^rag/eval/"),)


def git(raiz, *args):
    return subprocess.run(["git"] + list(args), cwd=raiz,
                          capture_output=True, text=True).stdout.split("\n")


def verificar(raiz, staged):
    if staged:
        arqs = git(raiz, "diff", "--cached", "--name-only", "--diff-filter=ACMR")
        origem = "prestes a ser commitado"
    else:
        arqs = git(raiz, "ls-files")
        origem = "ja rastreado no repo"

    achados = []
    for a in [x.strip() for x in arqs if x.strip()]:
        norm = a.replace("\\", "/")
        if any(rx.search(norm) for rx in ISENTOS):
            continue
        for rx, motivo in PROIBIDOS:
            if rx.search(norm):
                achados.append((a, motivo))
                break
    return achados, origem


def main(argv=None):
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="Barra artefato derivado da memoria")
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--raiz", default=os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    args = ap.parse_args(argv)

    achados, origem = verificar(os.path.abspath(args.raiz), args.staged)
    if not achados:
        print("artefatos: LIMPO -- nenhum arquivo derivado da memoria %s." % origem)
        return 0

    print("BLOQUEADO -- %d arquivo(s) derivado(s) da memoria, %s:\n"
          % (len(achados), origem))
    for a, motivo in achados:
        print("  %s" % a)
        print("      %s" % motivo)
    print("\nEste repo e PUBLICO. Tire do commit com:")
    print("  git restore --staged <arquivo>")
    print("Se voce acha que a regra esta errada para este arquivo, mude a lista")
    print("em tools/check-artefatos.py -- e nao com `git add -f`, que nao deixa")
    print("rastro de decisao nenhum.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
