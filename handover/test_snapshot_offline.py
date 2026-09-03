#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Suite OFFLINE da captura automatica (snapshot.py).

Transcript 100% sintetico. O snapshot real e escrito em
~/.claude/projects/<slug>/snapshots/, entao os testes que gravam usam um slug
de fixture (`__fixture_snapshot__`) e o apagam no fim -- nenhum projeto real e
tocado, nem lido.

Testes:
  1. extrai perguntas do usuario, na ordem
  2. ignora ruido injetado (system-reminder, contexto de hook, tool_result)
  3. conta arquivos tocados e comandos rodados
  4. calcula crescimento (ultimo total - primeiro total)
  5. REDACAO: senha em linha de comando e em URL de conexao nao vaza
  6. cap de prompts respeitado, e os RECENTES sao os que sobram
  7. capture() grava no diretorio canonico e sobrescreve a propria sessao
  8. sessao sem escrita/comando nao quebra o render

  python test_snapshot_offline.py
"""
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import snapshot  # noqa: E402

SLUG_FIXTURE = "__fixture_snapshot__"
falhas = []


def check(nome, cond, detalhe=""):
    print(("  OK   " if cond else "  FALHA ") + nome
          + (("  -- " + detalhe) if detalhe and not cond else ""))
    if not cond:
        falhas.append(nome)


def user(texto):
    return {"type": "user", "message": {"role": "user", "content": texto}}


def user_blocos(blocos):
    return {"type": "user", "message": {"role": "user", "content": blocos}}


def assistant(total=None, tools=(), modelo="claude-opus-5"):
    msg = {"role": "assistant", "model": modelo,
           "content": [{"type": "tool_use", "name": n, "input": i} for n, i in tools]}
    if total is not None:
        msg["usage"] = {"input_tokens": total, "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0}
    return {"type": "assistant", "message": msg}


def escrever_transcript(dirpath, sid, records):
    p = os.path.join(dirpath, sid + ".jsonl")
    with io.open(p, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return p


def main():
    tmp = tempfile.mkdtemp(prefix="o1mem_snap_")
    try:
        # ------------------------------------------------ 1, 2, 3, 4
        recs = [
            user("primeira pergunta do usuario"),
            assistant(10000, [("Bash", {"command": "git status"})]),
            user("<system-reminder>ruido do harness</system-reminder>"),
            user("[Contexto de sessao - informativo] nudge do proprio hook"),
            user_blocos([{"type": "tool_result", "content": "saida de ferramenta"}]),
            user("segunda pergunta do usuario"),
            assistant(45000, [("Edit", {"file_path": "/proj/a.py"}),
                              ("Write", {"file_path": "/proj/b.py"}),
                              ("Edit", {"file_path": "/proj/a.py"}),
                              ("Bash", {"command": "python3 teste.py"})]),
        ]
        t = escrever_transcript(tmp, "sessao1", recs)
        d = snapshot.parse_transcript(t)

        check("1. perguntas do usuario extraidas na ordem",
              d["prompts"] == ["primeira pergunta do usuario",
                               "segunda pergunta do usuario"], str(d["prompts"]))
        check("2. ruido injetado e tool_result ignorados", len(d["prompts"]) == 2)
        check("3. arquivos contados com frequencia",
              d["arquivos"] == {"/proj/a.py": 2, "/proj/b.py": 1}, str(d["arquivos"]))
        check("3b. comandos capturados na ordem",
              d["comandos"] == ["git status", "python3 teste.py"], str(d["comandos"]))
        check("4. crescimento = ultimo total - primeiro",
              d["baseline"] == 10000 and d["atual"] == 45000, str(d))
        check("4b. modelo capturado", d["modelo"] == "claude-opus-5")

        # ------------------------------------------------ 5: redacao
        segredo = "s3nh4-muito-secreta"
        recs = [
            user("liga no banco"),
            assistant(1000, [
                ("Bash", {"command": 'psql "postgres://appuser:%s@db.local:5432/prod"' % segredo}),
                ("Bash", {"command": "deploy --token %s --env prod" % segredo}),
            ]),
        ]
        t = escrever_transcript(tmp, "sessao2", recs)
        texto = snapshot.render(snapshot.parse_transcript(t), "x", "sessao2", "teste")
        check("5. senha em URL de conexao nao aparece no snapshot", segredo not in texto,
              "vazou")
        check("5b. senha em flag --token nao aparece", texto.count("<redigido>") >= 2,
              texto)
        check("5c. o comando continua legivel (host preservado)", "db.local" in texto)

        # ------------------------------------------------ 6: cap
        muitos = [user("pergunta numero %d" % i) for i in range(snapshot.MAX_PROMPTS + 10)]
        t = escrever_transcript(tmp, "sessao3", muitos + [assistant(1000)])
        texto = snapshot.render(snapshot.parse_transcript(t), "x", "sessao3", "teste")
        ultima = "pergunta numero %d" % (snapshot.MAX_PROMPTS + 9)
        check("6. cap de prompts aplicado",
              texto.count("- pergunta numero") == snapshot.MAX_PROMPTS,
              str(texto.count("- pergunta numero")))
        check("6b. o que sobra e o fio RECENTE", ultima in texto and "pergunta numero 0" not in texto)

        # ------------------------------------------------ 7: gravacao canonica
        t = escrever_transcript(tmp, "sessao4",
                                [user("oi"), assistant(1000, [("Bash", {"command": "ls"})])])
        dest = snapshot.capture(t, SLUG_FIXTURE, "teste")
        esperado = os.path.join(snapshot.snapshot_dir(SLUG_FIXTURE), "sessao4.md")
        check("7. grava em ~/.claude/projects/<slug>/snapshots/",
              os.path.normcase(dest) == os.path.normcase(esperado), dest)
        primeiro = os.path.getsize(dest)
        dest2 = snapshot.capture(t, SLUG_FIXTURE, "teste")
        arqs = os.listdir(snapshot.snapshot_dir(SLUG_FIXTURE))
        check("7b. recaptura sobrescreve, nao acumula",
              dest2 == dest and len(arqs) == 1 and os.path.getsize(dest) == primeiro,
              str(arqs))
        check("7c. mais_recente() acha o snapshot",
              snapshot.mais_recente(SLUG_FIXTURE) == dest)

        # ------------------------------------------------ 8: sessao vazia
        t = escrever_transcript(tmp, "sessao5", [user("so conversa"), assistant(1000)])
        texto = snapshot.render(snapshot.parse_transcript(t), "x", "sessao5", "teste")
        check("8. sessao sem escrita nem comando renderiza sem quebrar",
              "nenhum arquivo escrito" in texto and "(nenhum)" in texto)
        check("8b. o snapshot se declara materia-prima, nao handover",
              "nao e um handover" in texto.lower() or "isto nao e um handover" in texto.lower())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(os.path.join(snapshot.PROJECTS_DIR, SLUG_FIXTURE), ignore_errors=True)

    print()
    if falhas:
        print("FALHOU: %d" % len(falhas))
        for f in falhas:
            print("  - %s" % f)
        return 1
    print("todos os testes passaram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
