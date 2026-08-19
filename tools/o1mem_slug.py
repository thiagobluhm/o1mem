#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""o1mem_slug.py — a definicao CANONICA do slug de ~/.claude/projects/.

Por que existe
--------------
Tres componentes derivavam o slug por conta propria (handover.py, o guarda de
roteamento, o hook de nudge) e os tres codificavam o RESULTADO do caso Windows
em vez da regra. No Mac/Linux os tres produziam slug errado, e o sintoma nunca
apontava pra ca: o handover so dizia "nenhum ancestral tem memoria indexada" --
enquanto listava o proprio projeto entre os disponiveis.

A regra do harness e uma so: baixa a letra do drive e troca todo caractere
fora de [A-Za-z0-9] por '-'.

    C:\Projetos\O1MEM              -> c--Projetos-O1MEM
    /Users/t/_PESSOAIS/o1mem       -> -Users-t--PESSOAIS-o1mem

Os dois casos caem da mesma regra: ':' e '\' viram os dois tracos do Windows,
e a '/' inicial vira o traco unico do POSIX.

Compatibilidade com Windows
---------------------------
Esta funcao NAO muda o resultado em nenhum caminho Windows que a versao
anterior ja acertava -- tests/test_slug_for.py compara as duas implementacoes
caractere por caractere sobre caminhos `C:\...`. A unica divergencia
deliberada e em caminho com '_', '.' ou espaco: ali a versao antiga deixava o
caractere passar e produzia um slug que NAO existe em ~/.claude/projects/.
Isso era bug no Windows tambem, so nunca tinha sido notado.

Por que os outros scripts NAO importam daqui
--------------------------------------------
Eles sao instalados standalone, cada um numa pasta propria (handover.py vai
sozinho pra ~/.claude/skills/handover/), entao um import entre pastas quebraria
a instalacao. A copia continua local em cada script -- mas ESTE arquivo e a
fonte de verdade, e tests/test_slug_for.py obriga cada copia a concordar com
ele. Divergiu, o teste quebra.
"""
import os
import re


def slug_for(path):
    """Caminho absoluto -> slug da pasta em ~/.claude/projects/."""
    drive, rest = os.path.splitdrive(os.path.abspath(path))
    return re.sub(r"[^A-Za-z0-9]", "-", drive.lower() + rest)
