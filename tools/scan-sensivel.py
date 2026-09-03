#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scan-sensivel.py — porteiro de dado sensivel antes de um commit/push publico.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
Este repo ja vazou nome de cliente uma vez, e o scan que pegou o vazamento foi
feito a mao, de memoria, numa sessao especifica. Isso significa que a protecao
existia enquanto alguem lembrasse dela -- que e o mesmo que nao existir. O
contrato deste projeto e explicito: regra nova vai em CODIGO, nunca em
paragrafo. Este e o codigo.

Ele tambem cobre a superficie que a intuicao esquece: a MENSAGEM de commit vaza
tanto quanto o diff (foi assim da ultima vez -- o commit que corrigia o
vazamento citava o dado no titulo).

REGRA DE OURO: este script NUNCA imprime o valor que procura, nem a linha que
casou. Imprime arquivo, linha e o termo MASCARADO. Um scanner que ecoa o segredo
para provar que o achou reproduz o vazamento no proprio relatorio -- e o
relatorio vai para o transcript da sessao, que fica em disco.

PASSE 1 — deny-list DERIVADA, nao digitada
  Os termos saem dos slugs de projeto em ~/.claude/projects/: os nomes dos
  OUTROS trabalhos desta maquina, que nao podem aparecer num repo publico.
  Derivar em vez de digitar tem tres vantagens: o segredo nunca passa pela linha
  de comando, a lista nao envelhece quando entra projeto novo, e ninguem precisa
  lembrar de atualiza-la.

  O problema de derivar e o ruido: um slug quebrado em pedacos produz tokens que
  sao palavras comuns ("documentos", "cores"), e um scanner que grita em toda
  palavra comum ensina a ignora-lo. Entao ha TRIAGEM automatica, que e a heurica
  que funcionou na revisao a mao: um termo espalhado por muitos arquivos e quase
  certamente vocabulario; um termo que aparece 1 ou 2 vezes num canto e o que
  precisa de olho humano. So o segundo conjunto vira achado.
  (Nao adicione palavra comum a RUIDO so para calar o alarme: varias
  comecam nome de empresa. Reescreva a SUA frase -- foi o que fizemos
  aqui -- e o detector continua afiado.)

PASSE 2 — padroes genericos
  Credencial, token, chave privada, e-mail, caminho absoluto de usuario, IP
  privado. Pega o que a deny-list nao tem como conhecer.

USO
  python tools/scan-sensivel.py                      # arquivos alterados/nao rastreados
  python tools/scan-sensivel.py --todos              # o repo rastreado inteiro
  python tools/scan-sensivel.py --msg mensagem.txt   # tambem a mensagem de commit
  python tools/scan-sensivel.py --arquivos a.md b.py

EXIT
  0 = limpo   1 = ha achado para inspecionar
"""
import argparse
import os
import re
import subprocess
import sys

HOME = os.path.expanduser("~")
PROJECTS = os.path.join(HOME, ".claude", "projects")

# Slugs cujo conteudo E o proprio produto: nao sao segredo.
PROPRIOS = ("o1mem",)

# A marca do proprio autor. Nao e cliente e nao e segredo: esta no LICENSE,
# publicada de proposito. Fica separada de PROPRIOS porque aqui o filtro e por
# TERMO -- descartar o slug inteiro esconderia os outros pedacos dele, que
# podem ser sensiveis.
MARCA = {"aistein"}

# Ruido estrutural do slug e palavras comuns demais para indicar qualquer coisa.
RUIDO = {"projetos", "projeto", "users", "documents", "documentos", "desktop",
         "onedrive", "src", "app", "backend", "frontend", "web", "api", "test",
         "tests", "temp", "tmp", "claude", "code", "repo", "git", "github",
         "main", "dev", "python", "node", "skills", "memory", "docs", "doc",
         "installer", "vendor", "graph", "grafo", "rag", "core", "lib"}

# Um termo espalhado assim e vocabulario, nao identificador vazado.
LIMIAR_ARQUIVOS = 3
LIMIAR_HITS = 10

PADROES = [
    # `pass` como PALAVRA. Sem o \b, "segunda passada: arestas" virava
    # "credencial atribuida" -- e um falso positivo em codigo normal e o que
    # faz um scanner ser desligado.
    ("credencial atribuida",
     re.compile(r"(?i)\b(?:password|passwd|pass|senha|secret|api[_-]?key|token|"
                r"credential|bearer)\b\w*\s*[:=]\s*[\"']?[^\s\"';,)]{6,}")),
    ("credencial em URL",
     re.compile(r"[a-zA-Z][\w+.-]*://[^\s:/@]+:[^\s@]{3,}@")),
    ("chave privada",
     re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("token longo",
     re.compile(r"\b(?:sk|ghp|gho|ghs|xox[baprs]|AKIA)[-_A-Za-z0-9]{16,}")),
    ("e-mail",
     re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")),
    ("caminho absoluto de usuario",
     re.compile(r"(?i)[A-Z]:[\\/]Users[\\/][A-Za-z0-9._-]+"
                r"|/(?:home|Users)/[A-Za-z0-9._-]+")),
    ("IP privado",
     re.compile(r"\b(?:10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+"
                r"|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)\b")),
]

# Isencoes legitimas. Cada uma precisa de motivo -- isencao sem motivo e o mesmo
# que desligar o alarme.
ISENTOS = {
    # placeholder de documentacao e fixture de teste nao sao credencial
    "e-mail": re.compile(r"(?i)(example\.com|seu-email|your-email|noreply|"
                         r"user@host|fulano|db\.local)"),
    "caminho absoluto de usuario": re.compile(
        r"(?i)(<slug>|<usuario>|username|SEU_USUARIO|C:\\Users\\Voce)"),
    "credencial atribuida": re.compile(
        r"(?i)(redigido|redacted|xxx+|placeholder|exemplo|example|"
        r"senha@host|user:senha)"),
    # `api_key = v.strip()` e `token = token or default` sao ATRIBUICOES A
    # CODIGO, nao a um literal -- o valor nem esta ali. Exige RHS sem aspas e
    # com forma de expressao (chamada, atributo ou operador); uma
    # atribuicao a literal em arquivo de ambiente segue sendo achado.
    "credencial atribuida:codigo": re.compile(
        r"[:=]\s*[A-Za-z_][\w.]*\s*(?:\(|\.|\bor\b|\band\b|\bif\b)"),
    # Fixture de teste com chave OBVIAMENTE falsa. O criterio e o marcador
    # explicito no proprio valor -- nao "parece curta demais", que e como uma
    # chave real curta passaria batido.
    "credencial atribuida:fixture": re.compile(
        r"(?i)(fake|dummy|teste?|sample|foo|bar|abc123|123456)"),
    "token longo:fixture": re.compile(
        r"(?i)(fake|dummy|teste?|sample|abc123|123456)"),
    "credencial em URL": re.compile(r"(?i)(user:senha|usuario:senha|"
                                    r"appuser:|example\.com|<redigido>)"),
}

BIN_EXT = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".woff",
           ".woff2", ".ttf", ".pyc", ".jsonl", ".min.js"}


def mascara(t):
    """Primeiro caractere + comprimento. Nunca o valor inteiro."""
    return "%s%s (%d chars)" % (t[:1], "*" * (len(t) - 1), len(t))


def termos_derivados():
    termos = set()
    try:
        slugs = os.listdir(PROJECTS)
    except OSError:
        return termos
    for slug in slugs:
        if any(p in slug.lower() for p in PROPRIOS):
            continue
        if not os.path.isdir(os.path.join(PROJECTS, slug)):
            continue
        for parte in re.split(r"[-_.\s]+", slug):
            p = parte.strip().lower()
            if len(p) >= 3 and p not in RUIDO and p not in MARCA and not p.isdigit():
                termos.add(p)
    return termos


def _git(raiz, *args):
    return subprocess.run(["git"] + list(args), cwd=raiz,
                          capture_output=True, text=True).stdout


def arquivos_alterados(raiz):
    arqs = []
    for linha in _git(raiz, "status", "--porcelain").splitlines():
        caminho = linha[3:].strip().strip('"')
        if caminho.endswith("/"):
            for r, _d, fs in os.walk(os.path.join(raiz, caminho)):
                arqs += [os.path.relpath(os.path.join(r, f), raiz) for f in fs]
        else:
            arqs.append(caminho)
    return arqs


def _legivel(rel):
    if os.path.splitext(rel)[1].lower() in BIN_EXT:
        return False
    norm = rel.replace("\\", "/")
    return "__pycache__" not in norm and not norm.startswith(".git/")


def varre(raiz, arqs, termos, extras=()):
    """extras: [(rotulo, texto)] — para varrer coisa que nao e arquivo do repo,
    como a MENSAGEM de commit, que vaza tanto quanto o diff."""
    fontes = []
    for rel in sorted(set(arqs)):
        if not _legivel(rel):
            continue
        caminho = os.path.join(raiz, rel)
        if not os.path.isfile(caminho):
            continue
        try:
            with open(caminho, "r", encoding="utf-8", errors="replace") as f:
                fontes.append((rel, f.read()))
        except OSError:
            continue
    fontes += list(extras)

    # passe 1 com triagem: primeiro conta, depois decide o que e achado
    espalhamento = {t: [0, set()] for t in termos}
    for rel, txt in fontes:
        baixa = txt.lower()
        for t in termos:
            n = len(re.findall(r"\b%s" % re.escape(t), baixa))
            if n:
                espalhamento[t][0] += n
                espalhamento[t][1].add(rel)

    vocabulario = {t for t, (n, fs) in espalhamento.items()
                   if len(fs) >= LIMIAR_ARQUIVOS or n >= LIMIAR_HITS}
    suspeitos = {t for t, (n, _f) in espalhamento.items()
                 if n and t not in vocabulario}

    achados = []
    for rel, txt in fontes:
        linhas = txt.splitlines()
        for i, linha in enumerate(linhas, 1):
            baixa = linha.lower()
            for t in suspeitos:
                if re.search(r"\b%s" % re.escape(t), baixa):
                    achados.append((rel, i, "P1 nome de projeto", mascara(t)))
            for nome, rx in PADROES:
                m = rx.search(linha)
                if not m:
                    continue
                if any(rx2.search(linha) for chave, rx2 in ISENTOS.items()
                       if chave == nome or chave.startswith(nome + ":")):
                    continue
                achados.append((rel, i, "P2 " + nome, mascara(m.group(0))))
    return achados, espalhamento, vocabulario


def main(argv=None):
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="Scan de dado sensivel pre-push")
    ap.add_argument("--raiz", default=os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--todos", action="store_true",
                    help="varre o repo rastreado inteiro, nao so o alterado")
    ap.add_argument("--msg", help="arquivo com a mensagem de commit a varrer junto")
    ap.add_argument("--arquivos", nargs="*", help="lista explicita")
    args = ap.parse_args(argv)

    raiz = os.path.abspath(args.raiz)
    if args.arquivos:
        arqs = args.arquivos
    elif args.todos:
        arqs = _git(raiz, "ls-files").split()
    else:
        arqs = arquivos_alterados(raiz)

    extras = []
    if args.msg:
        with open(args.msg, "r", encoding="utf-8", errors="replace") as f:
            extras.append(("<mensagem de commit>", f.read()))

    termos = termos_derivados()
    achados, espalhamento, vocabulario = varre(raiz, arqs, termos, extras)

    print("raiz     : %s" % raiz)
    print("fontes   : %d arquivo(s)%s"
          % (len(arqs), " + a mensagem de commit" if extras else ""))
    print("passe 1  : %d termo(s) derivado(s) de %s" % (len(termos), PROJECTS))
    if vocabulario:
        print("           %d classificado(s) como vocabulario comum (>=%d arquivos"
              " ou >=%d hits), nao viram achado:"
              % (len(vocabulario), LIMIAR_ARQUIVOS, LIMIAR_HITS))
        print("           %s" % ", ".join(sorted(mascara(t) for t in vocabulario)))
    print("passe 2  : %d padrao(oes)" % len(PADROES))
    print()

    if not achados:
        print("LIMPO -- nenhum indicador.")
        return 0

    print("%d ACHADO(S) -- valor mascarado de proposito. Inspecione a linha no"
          " editor, nao aqui:" % len(achados))
    atual = None
    for rel, ln, tipo, val in achados:
        if rel != atual:
            print("\n  %s" % rel)
            atual = rel
        print("    linha %-5d %-30s %s" % (ln, tipo, val))
    return 1


if __name__ == "__main__":
    sys.exit(main())
