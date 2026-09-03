#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
snapshot.py — a captura AUTOMATICA da sessao. Materia-prima do handover.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
O `handover` deste produto e bom exatamente porque e DESTILADO: alguem julga o
que sobrevive, e o que sobra e curto o bastante para ser carregado toda sessao.
Julgamento nao da para automatizar sem um modelo, e nao e isso que este arquivo
tenta fazer.

O que ele resolve e o buraco ANTES do julgamento: hoje, se a sessao morre sem
alguem rodar `/handover` — o `/clear` impaciente, o auto-compact, a janela
fechada, o nudge ignorado — nao sobra materia-prima nenhuma. O produto inteiro
depende de um gesto humano num momento em que o humano esta cansado, e o custo
de esquecer e total: o estado vai junto.

Entao a divisao aqui e: a CAPTURA e automatica e burra (grava o que aconteceu,
sem interpretar), a DESTILACAO continua humana e cara. Um snapshot nao e um
handover e nao tenta parecer um: ele nao tem o porque, nao tem o proximo passo,
nao entra no `MEMORY.md` e nao e indexado no RAG. Ele so garante que, quando
alguem for destilar — agora ou na sessao seguinte — tenha de onde.

O QUE E CAPTURADO (tudo deterministico, zero LLM)
  * as perguntas que o usuario fez, na ordem  -> o fio da sessao
  * os arquivos escritos/editados             -> onde o trabalho caiu
  * os comandos rodados                       -> o que foi tentado
  * crescimento da conversa e modelo          -> o custo do que se perde

O QUE NAO E CAPTURADO
  Respostas do assistente e conteudo de tool_result. Sao o grosso dos tokens e
  a parte que o proprio transcript ja guarda; copia-los faria do snapshot uma
  segunda conversa inteira em disco — o oposto da tese.

SEGREDO
  O snapshot le comandos de shell, e comando de shell carrega credencial. Ele
  mora em ~/.claude/projects/<slug>/snapshots/ (fora de qualquer repo, mesma
  trava do handover) e passa por `redact()` antes de gravar. A redacao e a
  segunda linha de defesa, nao a primeira.

USO
  python snapshot.py --transcript <caminho.jsonl> [--slug <slug>]
  python snapshot.py --show --slug <slug>         # o snapshot mais recente
"""
import argparse
import datetime as _dt
import io
import json
import os
import re
import sys

PROJECTS_DIR = os.path.normpath(os.path.expanduser("~/.claude/projects"))

MAX_PROMPTS = 40        # caps: o snapshot e materia-prima, nao um segundo log
MAX_ARQUIVOS = 30
MAX_COMANDOS = 25
MAX_CHARS_PROMPT = 240

FERRAMENTAS_ARQUIVO = ("Edit", "Write", "NotebookEdit", "MultiEdit")

# Redacao. Alvos ESTREITOS de proposito: um filtro guloso que apagasse qualquer
# string longa deixaria o snapshot ilegivel e ensinaria a ignora-lo.
_REDACOES = (
    # atribuicao explicita: senha=..., --token X, "api_key": "..."
    (re.compile(r"(?i)\b((?:pass(?:word|wd)?|senha|secret|token|api[_-]?key|"
                r"auth|bearer|credential)\w*)(\s*[:=]\s*|\s+)(\"[^\"]+\"|'[^']+'|\S+)"),
     lambda m: m.group(1) + m.group(2) + "<redigido>"),
    # credencial embutida em URL: postgres://user:senha@host  (o caso conhecido)
    (re.compile(r"([a-zA-Z][\w+.-]*://[^\s:/@]+):([^\s@]+)@"),
     lambda m: m.group(1) + ":<redigido>@"),
)


def redact(texto):
    for rx, sub in _REDACOES:
        texto = rx.sub(sub, texto)
    return texto


def snapshot_dir(slug):
    return os.path.join(PROJECTS_DIR, slug, "snapshots")


def slug_from_transcript(transcript):
    """O transcript vive em ~/.claude/projects/<slug>/<session_id>.jsonl."""
    return os.path.basename(os.path.dirname(os.path.abspath(transcript)))


def _texto_do_conteudo(content):
    """Extrai so o texto que o USUARIO digitou de um record de mensagem."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    partes = []
    for b in content:
        if isinstance(b, dict) and b.get("type") == "text":
            partes.append(b.get("text") or "")
    return "\n".join(partes)


# Contexto injetado por hook e lembrete do harness aparecem como mensagem do
# usuario no transcript, mas nao sao pergunta de ninguem. Sem este corte o
# snapshot vira um espelho dos nossos proprios avisos.
RE_RUIDO = re.compile(r"<(system-reminder|command-name|local-command)", re.I)


def parse_transcript(path):
    prompts, arquivos, comandos = [], {}, []
    baseline = atual = modelo = None

    with io.open(path, "r", encoding="utf-8", errors="replace") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                rec = json.loads(linha)
            except ValueError:
                continue
            if rec.get("isMeta"):
                continue
            msg = rec.get("message")
            if not isinstance(msg, dict):
                continue

            if rec.get("type") == "user" and msg.get("role") == "user":
                t = _texto_do_conteudo(msg.get("content")).strip()
                if t and not RE_RUIDO.search(t) and not t.startswith("[Contexto de sessao"):
                    prompts.append(t)
                continue

            if rec.get("type") != "assistant":
                continue

            u = msg.get("usage")
            if isinstance(u, dict) and u.get("input_tokens") is not None:
                total = (int(u["input_tokens"])
                         + int(u.get("cache_creation_input_tokens", 0) or 0)
                         + int(u.get("cache_read_input_tokens", 0) or 0))
                if baseline is None:
                    baseline = total
                atual = total
                modelo = msg.get("model") or modelo

            for b in (msg.get("content") or []):
                if not isinstance(b, dict) or b.get("type") != "tool_use":
                    continue
                nome, inp = b.get("name"), b.get("input") or {}
                if nome in FERRAMENTAS_ARQUIVO:
                    fp = inp.get("file_path") or inp.get("notebook_path")
                    if fp:
                        arquivos[fp] = arquivos.get(fp, 0) + 1
                elif nome == "Bash":
                    c = (inp.get("command") or "").strip()
                    if c:
                        comandos.append(c)

    return {"prompts": prompts, "arquivos": arquivos, "comandos": comandos,
            "baseline": baseline, "atual": atual, "modelo": modelo}


def _corta(s, n):
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "..."


def render(dados, slug, sid, motivo):
    agora = _dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    b, a = dados["baseline"], dados["atual"]
    cresc = (a - b) if (b is not None and a is not None) else None

    L = ["# SNAPSHOT BRUTO — %s" % slug,
         "> sessao %s · capturado em %s · gatilho: %s" % (sid[:12], agora, motivo),
         ">",
         "> Captura AUTOMATICA e nao julgada. **Isto nao e um handover**: nao tem",
         "> o porque, nao tem proximo passo e nao esta na memoria. E a materia-prima",
         "> para destilar um — rode `/handover` e use este arquivo como fonte.",
         ""]

    if cresc is not None:
        L += ["## Custo da sessao",
              "- conversa cresceu **~%dk tokens** acima do piso (janela ~%dk, modelo %s)"
              % (round(cresc / 1000), round(a / 1000), dados["modelo"] or "?"),
              ""]

    ps = dados["prompts"]
    L.append("## O fio — o que o usuario pediu (%d turno(s))" % len(ps))
    if len(ps) > MAX_PROMPTS:
        L.append("_os %d primeiros omitidos; o fio recente e o que importa para retomar_"
                 % (len(ps) - MAX_PROMPTS))
    for p in (ps[-MAX_PROMPTS:] or ["_(nenhum)_"]):
        L.append("- " + _corta(redact(p), MAX_CHARS_PROMPT))
    L.append("")

    arq = sorted(dados["arquivos"].items(), key=lambda kv: -kv[1])
    L.append("## Onde o trabalho caiu (%d arquivo(s))" % len(arq))
    for fp, n in arq[:MAX_ARQUIVOS]:
        L.append("- `%s` — %dx" % (fp, n))
    if len(arq) > MAX_ARQUIVOS:
        L.append("- _(+%d)_" % (len(arq) - MAX_ARQUIVOS))
    if not arq:
        L.append("_(nenhum arquivo escrito — sessao de leitura/exploracao)_")
    L.append("")

    cmds = dados["comandos"]
    L.append("## Comandos rodados (%d, os %d ultimos)" % (len(cmds), MAX_COMANDOS))
    for c in (cmds[-MAX_COMANDOS:] or ["_(nenhum)_"]):
        L.append("- `%s`" % _corta(redact(c), 160).replace("`", "'"))
    L.append("")
    return "\n".join(L) + "\n"


def capture(transcript, slug=None, motivo="manual"):
    """Escreve o snapshot e devolve o caminho. Idempotente por sessao (sobrescreve).

    Sobrescrever, e nao acumular, e deliberado: o snapshot descreve a sessao
    INTEIRA ate agora, entao a versao nova contem a antiga. Guardar as duas
    seria pagar duas vezes pelo mesmo estado — a coisa que este produto existe
    para nao fazer.
    """
    if not os.path.exists(transcript):
        raise SystemExit("ERRO: transcript nao encontrado: %s" % transcript)
    slug = slug or slug_from_transcript(transcript)
    sid = os.path.splitext(os.path.basename(transcript))[0]
    dados = parse_transcript(transcript)

    dest_dir = snapshot_dir(slug)
    if not os.path.isdir(dest_dir):
        os.makedirs(dest_dir)
    dest = os.path.join(dest_dir, sid + ".md")
    with io.open(dest, "w", encoding="utf-8", newline="") as f:
        f.write(render(dados, slug, sid, motivo).replace("\n", "\r\n"))
    return dest


def mais_recente(slug):
    d = snapshot_dir(slug)
    if not os.path.isdir(d):
        return None
    arqs = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".md")]
    return max(arqs, key=os.path.getmtime) if arqs else None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Captura automatica da sessao")
    ap.add_argument("--transcript", help="caminho do .jsonl da sessao")
    ap.add_argument("--slug", help="forca o projeto (default: pasta-mae do transcript)")
    ap.add_argument("--motivo", default="manual", help="o que disparou a captura")
    ap.add_argument("--show", action="store_true", help="imprime o snapshot mais recente")
    args = ap.parse_args(argv)

    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if args.show:
        if not args.slug:
            raise SystemExit("ERRO: --show exige --slug")
        p = mais_recente(args.slug)
        if not p:
            print("nenhum snapshot para %s" % args.slug)
            return 1
        print("# %s\n" % p)
        sys.stdout.write(io.open(p, encoding="utf-8").read())
        return 0

    if not args.transcript:
        ap.print_help()
        return 2
    print(capture(args.transcript, args.slug, args.motivo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
