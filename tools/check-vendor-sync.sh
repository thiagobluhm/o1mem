#!/usr/bin/env bash
# Fails if a source file drifted from the copy vendored into the npm package.
#
# The published package (@tbluhm82/o1mem) does not read the top-level folders --
# it carries its own copies under installer/. A fix applied only to the source
# reaches git and still ships broken to every npm user. This catches that before
# it happens.
#
# CRLF differences are noise on Windows checkouts, so the comparison strips
# trailing CR. Run from anywhere: paths resolve against the repo root.
#
# Usage:  bash tools/check-vendor-sync.sh
# Exit :  0 = in sync, 1 = drift found (list printed)

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

# source:vendored_copy
PAIRS="
handover/handover.py:installer/skills/handover/handover.py
handover/snapshot.py:installer/skills/handover/snapshot.py
handover/snapshot.py:installer/vendor/handover/snapshot.py
handover/SKILL.md:installer/skills/handover/SKILL.md
organizador-mem/SKILL.md:installer/skills/organizador-mem/SKILL.md
retomar/SKILL.md:installer/skills/retomar/SKILL.md
rag/o1mem_rag.py:installer/vendor/rag/o1mem_rag.py
rag/o1mem_rag_daemon.py:installer/vendor/rag/o1mem_rag_daemon.py
rag/o1mem_distill.py:installer/vendor/rag/o1mem_distill.py
rag/o1mem_eval.py:installer/vendor/rag/o1mem_eval.py
graph/o1mem_graph.py:installer/vendor/graph/o1mem_graph.py
handover-nudge-hook/handover_nudge.py:installer/vendor/hook/handover_nudge.py
"

drift=0
missing=0
checked=0

for pair in $PAIRS; do
    [ -z "$pair" ] && continue
    src="${pair%%:*}"
    dst="${pair##*:}"
    # Tolera CR caso alguem regrave este arquivo em CRLF no Windows. Sem isto,
    # no Linux o CR entra no VALOR da variavel (IFS nao separa por CR) e o
    # caminho vira "arquivo<CR>": o teste acusa a ausencia de um arquivo que
    # existe, apontando para o lugar errado. Foi assim que a primeira execucao
    # desta CI ficou vermelha.
    src="${src%$'\r'}"
    dst="${dst%$'\r'}"

    if [ ! -f "$src" ]; then
        echo "MISSING SOURCE  $src"
        missing=$((missing + 1))
        continue
    fi
    if [ ! -f "$dst" ]; then
        echo "MISSING VENDOR  $dst  (source exists: $src)"
        missing=$((missing + 1))
        continue
    fi

    checked=$((checked + 1))
    if ! diff -q --strip-trailing-cr "$src" "$dst" >/dev/null 2>&1; then
        echo "DRIFT           $dst"
        echo "                differs from $src"
        drift=$((drift + 1))
    fi
done

echo
if [ "$drift" -eq 0 ] && [ "$missing" -eq 0 ]; then
    echo "vendor sync OK -- $checked file(s) match."
    exit 0
fi

echo "vendor sync FAILED -- $drift drifted, $missing missing, $checked compared."
echo "Copy each source over its vendored counterpart and commit both."
exit 1
