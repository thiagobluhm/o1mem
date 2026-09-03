#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Suite OFFLINE do medidor de recall (o1mem_eval.py).

Testa a MECANICA da medicao, nao a qualidade do modelo: corpus sintetico e
`O1MEM_RAG_FAKE_EMBED=1`, entao nenhum modelo de 470 MB e baixado e nenhuma
memoria real e lida. Um harness de avaliacao que mede errado e pior que nenhum
— ele produz um numero com aparencia de evidencia — entao o que precisa estar
certo aqui e: de onde sai o gabarito, o que conta como acerto, e se as
metricas batem com um ranking conhecido.

Testes:
  1. gabarito automatico sai das chamadas do MEMORY.md
  2. entrada de indice sem chamada (so titulo) NAO vira consulta
  3. MEMORY.md nao esta no corpus indexado -> a pergunta e mesmo "nao vista"
  4. gabarito manual: aceita alvo unico e lista de alternativas
  5. gabarito manual malformado falha ALTO, com a linha
  6. acerto por documento: chunk `no::s3` conta como acerto do no
  7. metricas conferem contra um ranking fabricado (hit@1/3/5 e MRR)
  8. so_memoria() tira handover e archive do corpus
  9. BM25 acha o documento certo num corpus trivial

  python test_eval_offline.py
"""
import os
import shutil
import sys
import tempfile

os.environ["O1MEM_RAG_FAKE_EMBED"] = "1"

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "graph")))
import o1mem_eval as ev  # noqa: E402
import o1mem_rag as rag  # noqa: E402

falhas = []


def check(nome, cond, detalhe=""):
    print(("  OK   " if cond else "  FALHA ") + nome
          + (("  -- " + detalhe) if detalhe and not cond else ""))
    if not cond:
        falhas.append(nome)


def escrever(root, nome, corpo, desc="fixture"):
    with open(os.path.join(root, nome), "w", encoding="utf-8") as f:
        f.write("---\nname: %s\ndescription: %s\nmetadata:\n  type: project\n---\n\n%s\n"
                % (nome[:-3], desc, corpo))


def main():
    tmp = tempfile.mkdtemp(prefix="o1mem_eval_")
    try:
        root = os.path.join(tmp, "memory")
        os.makedirs(root)
        escrever(root, "project_alfa.md", "O alfa trata de compactacao de janela.")
        escrever(root, "project_beta.md", "O beta trata de rotacao de credenciais.")
        escrever(root, "project_gama.md", "O gama trata de empacotamento.")
        with open(os.path.join(root, "MEMORY.md"), "w", encoding="utf-8") as f:
            f.write("# Memory Index\n\n"
                    "- [Alfa](project_alfa.md) — como a janela de contexto e "
                    "compactada quando enche demais\n"
                    "- [Beta](project_beta.md) — a troca periodica de segredos "
                    "entre os ambientes do sistema\n"
                    "- [Gama](project_gama.md) — curto\n")

        # ---------------- 1 e 2
        gold = ev.gold_do_indice(root)
        alvos = sorted(g["expect"][0] for g in gold)
        check("1. gabarito sai das chamadas do MEMORY.md",
              alvos == ["project_alfa", "project_beta"], str(alvos))
        check("1b. a consulta e a chamada, nao o titulo",
              all("Alfa" not in g["q"] and len(g["q"]) > 40 for g in gold), str(gold))
        check("2. entrada sem chamada de verdade nao vira consulta",
              "project_gama" not in alvos)

        # ---------------- 3: a pergunta e mesmo "nao vista" pelo indice
        chunks = rag.collect_chunks(root)
        ids = {c["id"] for c in chunks}
        check("3. MEMORY.md fica FORA do corpus indexado",
              "memory" not in ids and len(ids) == 3, str(ids))

        # ---------------- 4 e 5: gabarito manual
        gpath = os.path.join(tmp, "gold.jsonl")
        with open(gpath, "w", encoding="utf-8") as f:
            f.write('# comentario ignorado\n')
            f.write('{"q": "pergunta um", "expect": "project_alfa"}\n')
            f.write('{"q": "pergunta dois", "expect": ["project_beta", "project_gama"]}\n')
        man = ev.gold_do_arquivo(gpath)
        check("4. gabarito manual aceita alvo unico e lista",
              [len(g["expect"]) for g in man] == [1, 2] and man[0]["origem"] == "manual",
              str(man))

        ruim = os.path.join(tmp, "ruim.jsonl")
        with open(ruim, "w", encoding="utf-8") as f:
            f.write('{"q": "sem alvo"}\n')
        try:
            ev.gold_do_arquivo(ruim)
            check("5. gabarito malformado falha alto", False, "nao levantou")
        except SystemExit as e:
            check("5. gabarito malformado falha alto, citando a linha",
                  "linha 1" in str(e), str(e))

        # ---------------- 6: acerto por documento
        check("6. chunk de secao conta como acerto do documento",
              ev._acerta("handover_x_20260101::s3", ["handover_x_20260101"]))
        check("6b. documento errado nao vira acerto",
              not ev._acerta("handover_y_20260101::s3", ["handover_x_20260101"]))

        # ---------------- 7: metricas contra ranking conhecido
        g4 = [{"q": "a", "expect": ["alvo"]}, {"q": "b", "expect": ["alvo"]},
              {"q": "c", "expect": ["alvo"]}, {"q": "d", "expect": ["alvo"]}]
        planta = {"a": ["alvo"],                                  # rank 1
                  "b": ["x", "y", "alvo"],                        # rank 3
                  "c": ["x", "y", "z", "w", "alvo"],              # rank 5
                  "d": ["x", "y", "z", "w", "v", "u"]}            # nao achou
        m = ev.avalia(g4, lambda q, k: planta[q], 5)
        esperado_mrr = round((1 + 1 / 3.0 + 1 / 5.0) / 4, 3)
        check("7. hit@1 = 1/4", m["hit@1"] == 0.25, str(m))
        check("7b. hit@3 = 2/4", m["hit@3"] == 0.5, str(m))
        check("7c. hit@5 = 3/4", m["hit@5"] == 0.75, str(m))
        check("7d. mrr confere", m["mrr@10"] == esperado_mrr,
              "%s != %s" % (m["mrr@10"], esperado_mrr))
        check("7e. conta as consultas sem resposta", m["sem_resposta"] == 1)

        # ---------------- 8: escopo
        frios = [{"id": "h::s0", "text": "t", "meta": {"kind": "handover"}},
                 {"id": "a::1", "text": "t", "meta": {"kind": "archive_bullet"}},
                 {"id": "project_alfa", "text": "t", "meta": {"kind": "project"}}]
        check("8. so_memoria() remove handover e archive",
              [c["id"] for c in ev.so_memoria(frios)] == ["project_alfa"])

        # ---------------- 9: BM25
        bm = ev.BM25(chunks)
        top = bm.search("rotacao de credenciais entre ambientes", 3)
        check("9. BM25 poe o documento certo em primeiro",
              top and top[0] == "project_beta", str(top))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

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
