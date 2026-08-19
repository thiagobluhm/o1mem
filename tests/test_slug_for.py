# -*- coding: utf-8 -*-
r"""O slug tem que reproduzir EXATAMENTE o que o harness cria em
~/.claude/projects/. Se divergir num unico caractere, nada acha a memoria: o
handover morre com "nenhum ancestral tem memoria indexada" -- listando o
proprio projeto entre os disponiveis -- e o guarda de roteamento deixa passar
escrita no projeto errado.

Este arquivo cobre tres coisas:

1. A REGRA, contra slugs POSIX reais colhidos do disco (macOS).
2. PARIDADE COM WINDOWS: a implementacao nova nao pode mudar o resultado de
   nenhum caminho `C:\...` que a antiga ja acertava. Isso e testado rodando as
   DUAS implementacoes lado a lado -- roda em qualquer SO, porque compara
   funcoes puras, nao o sistema de arquivos.
3. As COPIAS standalone (handover, guarda) batendo com tools/o1mem_slug.py.
"""
import ntpath
import os
import re
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("tools", "handover", "memory-routing-guard"):
    sys.path.insert(0, os.path.join(REPO, sub))

import o1mem_slug            # noqa: E402  fonte de verdade
import handover              # noqa: E402
import memory_routing_guard  # noqa: E402


# ---------------------------------------------------------------- a regra
POSIX_CASES = [
    # (caminho em disco, slug real observado em ~/.claude/projects/)
    ("/Users/thiagobluhm/Documents/_PESSOAIS/o1mem",
     "-Users-thiagobluhm-Documents--PESSOAIS-o1mem"),
    ("/Users/thiagobluhm/Documents/_PESSOAIS/ss_e_b/curriculos",
     "-Users-thiagobluhm-Documents--PESSOAIS-ss-e-b-curriculos"),
    ("/Users/thiagobluhm/Documents/_Clientes/PORTFOLIO/SEINFRA",
     "-Users-thiagobluhm-Documents--Clientes-PORTFOLIO-SEINFRA"),
    ("/Users/thiagobluhm",
     "-Users-thiagobluhm"),
]


@pytest.mark.skipif(os.name == "nt", reason="caminhos POSIX")
@pytest.mark.parametrize("path,expected", POSIX_CASES)
def test_slug_posix(path, expected):
    assert o1mem_slug.slug_for(path) == expected


def test_slug_e_deterministico():
    assert o1mem_slug.slug_for("/a/b") == o1mem_slug.slug_for("/a/b")


# ------------------------------------------------- paridade com o Windows
def _slug_novo_win(p):
    """A regra NOVA aplicada com semantica de Windows, rode onde rodar.

    Usa ntpath de proposito: em producao slug_for() chama os.path.splitdrive,
    que NO WINDOWS e exatamente ntpath.splitdrive. Num Mac, os.path e posixpath
    e nao reconhece `C:` como drive -- simular Windows com ele daria um
    resultado que nao acontece em maquina nenhuma.
    """
    drive, rest = ntpath.splitdrive(p)
    return re.sub(r"[^A-Za-z0-9]", "-", drive.lower() + rest)


def _slug_antigo_win(p):
    """A implementacao ANTERIOR, com a mesma semantica de Windows. Preservada
    so para provar que o Windows nao regride; nao e usada em producao."""
    drive, rest = ntpath.splitdrive(p)
    return (drive[:1].lower() + "--" +
            rest.replace("\\", "/").strip("/").replace("/", "-"))


# Caminhos Windows SEM '_', '.' ou espaco: aqui as duas implementacoes tem que
# concordar. Se divergirem, a mudanca quebrou o Windows.
WIN_IGUAIS = [
    r"C:\Projetos\O1MEM",
    r"C:\Projetos\O1MEM\installer",
    r"D:\dev\app",
    r"C:\Users\thiago\Documents\repo",
    r"C:\a",
]


@pytest.mark.parametrize("path", WIN_IGUAIS)
def test_windows_nao_regride(path):
    """A regra nova produz o MESMO slug que a antiga em caminho Windows.

    Este e o teste que responde "a correcao quebra o Windows?". Roda em
    qualquer SO porque compara funcoes puras com semantica ntpath."""
    assert _slug_novo_win(path) == _slug_antigo_win(path), (
        "mudanca alterou o slug no Windows para %s" % path)


@pytest.mark.parametrize("path,antigo,novo", [
    # '_' era deixado passar e gerava slug que nao existe em ~/.claude/projects/
    (r"C:\Projetos\meu_app", "c--Projetos-meu_app", "c--Projetos-meu-app"),
])
def test_windows_divergencia_deliberada(path, antigo, novo):
    """Unica mudanca de comportamento no Windows -- e e correcao de bug.

    O harness troca '_' por '-' (confirmado nos slugs reais: `ss_e_b` ->
    `ss-e-b`). A versao antiga deixava o '_' intacto, entao no Windows um
    projeto com '_' no caminho tambem nunca era encontrado."""
    assert _slug_antigo_win(path) == antigo
    assert _slug_novo_win(path) == novo


@pytest.mark.skipif(os.name != "nt", reason="so faz sentido rodando no Windows")
def test_slug_windows():
    assert o1mem_slug.slug_for(r"C:\Projetos\O1MEM") == "c--Projetos-O1MEM"


# ------------------------------------------- as copias nao podem divergir
ALL_PATHS = [p for p, _ in POSIX_CASES] + [
    "/a/b", "/a/b/c_d", "/Users/x/meu.projeto", "/Users/x/com espaco",
]


@pytest.mark.parametrize("path", ALL_PATHS)
def test_handover_concorda_com_canonico(path):
    assert handover.slug_for(path) == o1mem_slug.slug_for(path)


@pytest.mark.skipif(os.name == "nt", reason="caminhos POSIX")
@pytest.mark.parametrize("path", ALL_PATHS)
def test_guard_concorda_com_canonico(path):
    """slugify() do guarda recebe a RAIZ mencionada no texto, ja sem barra final.

    Divergir aqui nao da erro visivel: o guarda simplesmente nao reconhece o
    projeto mencionado e LIBERA a escrita no lugar errado -- exatamente o que
    ele existe pra impedir."""
    assert memory_routing_guard.slugify(path) == o1mem_slug.slug_for(path)


def test_guard_preserva_o_caso_windows():
    """O guarda pode rodar num SO e ler mencao a caminho do outro, entao a
    letra de drive tem que ser baixada sem depender de splitdrive."""
    assert memory_routing_guard.slugify(r"C:\Projetos\O1MEM") == "c--Projetos-O1MEM"


# ------------------------------------- o guarda tem que ENXERGAR caminho POSIX
@pytest.mark.parametrize("texto,esperado", [
    ("veja /Users/thiagobluhm/Documents/_PESSOAIS/o1mem/handover",
     "/Users/thiagobluhm/Documents/_PESSOAIS/o1mem/handover"),
    (r"veja C:\Projetos\O1MEM\handover", r"C:\Projetos\O1MEM\handover"),
])
def test_guard_reconhece_mencao_de_caminho(texto, esperado):
    r"""O regex so casava `C:\...`. Num Mac nenhuma mencao era vista, entao o
    guarda passava por 'aprovado' sem ter olhado. O ramo Windows fica intacto."""
    m = memory_routing_guard.RE_PATH_MENTION.search(texto)
    assert m is not None, "nenhuma mencao reconhecida em: " + texto
    assert m.group(1) == esperado


# ------------------------------------------- o guarda tem que BLOQUEAR de fato
OWN = "-Users-thiagobluhm-Documents--PESSOAIS-minven"
FOREIGN = "-Users-thiagobluhm-Documents--PESSOAIS-o1mem"
SLUGS = {OWN, FOREIGN, "-Users-thiagobluhm-Documents--PESSOAIS-ss-e-b-curriculos",
         "c--Projetos-O1MEM"}


def test_guard_pega_projeto_estrangeiro_posix():
    r"""O caso que o guarda existe pra pegar: sessao aberta em minven, texto
    falando de o1mem. A busca so ia ate profundidade 4 (bastava pra
    `C:\Projetos\Foo`, curto demais pra `/Users/t/_PESSOAIS/o1mem`), entao em
    POSIX nunca havia bloqueio."""
    texto = "isso pertence a /Users/thiagobluhm/Documents/_PESSOAIS/o1mem/handover"
    cand, _ = memory_routing_guard.mentioned_foreign_slug(texto, OWN, SLUGS)
    assert cand == FOREIGN


def test_guard_continua_pegando_caminho_windows():
    """O caso que ja funcionava no Windows nao pode ter parado de funcionar."""
    texto = r"isso pertence a C:\Projetos\O1MEM\handover"
    cand, _ = memory_routing_guard.mentioned_foreign_slug(texto, OWN, SLUGS)
    assert cand == "c--Projetos-O1MEM"


def test_guard_prefere_o_projeto_mais_especifico():
    """`.../ss_e_b/curriculos` e projeto proprio; casar so `.../ss_e_b`
    apontaria pra pasta errada."""
    texto = "ver /Users/thiagobluhm/Documents/_PESSOAIS/ss_e_b/curriculos/app"
    cand, _ = memory_routing_guard.mentioned_foreign_slug(texto, OWN, SLUGS)
    assert cand == "-Users-thiagobluhm-Documents--PESSOAIS-ss-e-b-curriculos"


def test_guard_nao_bloqueia_o_proprio_projeto():
    texto = "estou em /Users/thiagobluhm/Documents/_PESSOAIS/minven/src"
    cand, _ = memory_routing_guard.mentioned_foreign_slug(texto, OWN, SLUGS)
    assert cand is None


def test_guard_ignora_caminho_desconhecido():
    """Fail-open: caminho que nao corresponde a projeto nenhum nao vira bloqueio."""
    texto = "veja /usr/local/bin/algo"
    cand, _ = memory_routing_guard.mentioned_foreign_slug(texto, OWN, SLUGS)
    assert cand is None
