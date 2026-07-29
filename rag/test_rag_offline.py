#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Suite OFFLINE da skill rag — roda sem modelo (O1MEM_RAG_FAKE_EMBED=1) e com
corpus 100% SINTETICO: o repo e publico, fixture jamais usa memoria real.

  python test_rag_offline.py
"""
import json
import os
import shutil
import sys
import tempfile

os.environ["O1MEM_RAG_FAKE_EMBED"] = "1"

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import o1mem_rag as rag  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}  {detail}")


def make_corpus(root):
    """Memoria sintetica minima: 2 fatos ligados por wikilink + archive."""
    os.makedirs(root, exist_ok=True)

    def w(name, text):
        with open(os.path.join(root, name), "w", encoding="utf-8") as f:
            f.write(text)

    w("MEMORY.md", "# Index\n- [A](project_alpha_pipeline.md) — pipeline\n")
    w("project_alpha_pipeline.md",
      "---\nname: project_alpha_pipeline\n"
      "description: pipeline de dados alpha com validacao\n"
      "metadata:\n  type: project\n---\n\n"
      "O pipeline alpha valida os dados. Ver [[project_beta_deploy]].\n")
    w("project_beta_deploy.md",
      "---\nname: project_beta_deploy\n"
      "description: deploy do servico beta em staging\n"
      "metadata:\n  type: project\n---\n\n"
      "Deploy do beta depende do [[project_alpha_pipeline]].\n")
    w("MEMORY_ARCHIVE.md",
      "# Frio\n"
      "- fato antigo numero um sobre migracao de banco de dados\n"
      "- fato antigo numero dois sobre rotacao de credenciais\n"
      "- x\n")  # < 20 chars: deve ser ignorado


def main():
    tmp = tempfile.mkdtemp(prefix="o1mem_rag_test_")
    slug = "test_synthetic"
    root = os.path.join(tmp, "memory")
    make_corpus(root)

    # o indice de teste vai para um CHROMA_BASE temporario, nunca no real
    rag.CHROMA_BASE = os.path.join(tmp, "chroma")

    print("== chunking ==")
    chunks = rag.collect_chunks(root)
    ids = {c["id"] for c in chunks}
    check("MEMORY.md fora do corpus", "memory" not in ids)
    check("2 fatos viram 2 chunks",
          {"project_alpha_pipeline", "project_beta_deploy"} <= ids, ids)
    check("archive: 2 bullets validos, curto ignorado",
          sum(1 for c in chunks if c["meta"]["kind"] == "archive_bullet") == 2)
    alpha = next(c for c in chunks if c["id"] == "project_alpha_pipeline")
    check("description entra no texto embedado",
          alpha["text"].startswith("pipeline de dados alpha"))

    print("== index incremental ==")
    r1 = rag.index(slug, root, "fake")
    check("primeira indexacao embeda tudo",
          r1["embedded"] == 4 and r1["chunks_total"] == 4, r1)
    r2 = rag.index(slug, root, "fake")
    check("reindexar sem mudanca embeda 0",
          r2["embedded"] == 0 and r2["unchanged"] == 4, r2)

    # muda 1 arquivo -> so ele re-embeda
    p = os.path.join(root, "project_beta_deploy.md")
    open(p, "a", encoding="utf-8").write("\nLinha nova.\n")
    r3 = rag.index(slug, root, "fake")
    check("mudou 1 arquivo -> embeda 1", r3["embedded"] == 1, r3)

    # remove 1 bullet do archive -> chunk some do indice
    arch = os.path.join(root, "MEMORY_ARCHIVE.md")
    txt = open(arch, encoding="utf-8").read()
    open(arch, "w", encoding="utf-8").write(
        txt.replace("- fato antigo numero dois sobre rotacao de credenciais\n", ""))
    r4 = rag.index(slug, root, "fake")
    check("bullet removido -> deleted 1 e total 3",
          r4["deleted"] == 1 and r4["chunks_total"] == 3, r4)

    print("== query ==")
    # embedder fake: identidade por texto — buscar o TEXTO de um chunk
    # tem que devolver ele mesmo em 1o lugar (distancia 0)
    beta_text = next(c["text"] for c in rag.collect_chunks(root)
                     if c["id"] == "project_beta_deploy")
    q = rag.query(slug, root, beta_text, 2, "fake", with_graph=True)
    check("hit exato em 1o lugar",
          q["hits"] and q["hits"][0]["id"] == "project_beta_deploy",
          [h["id"] for h in q["hits"]])
    check("score do hit exato ~1.0", q["hits"][0]["score"] > 0.999)
    check("join com grafo traz o vizinho estrutural",
          any(n["id"] == "project_alpha_pipeline"
              for n in q["hits"][0].get("graph_neighbors", [])))
    q2 = rag.query(slug, root, beta_text, 2, "fake", with_graph=False)
    check("--no-graph nao poe vizinhos",
          "graph_neighbors" not in q2["hits"][0])
    check("timings presentes p/ decisao da fase 2",
          {"model_load_s", "embed_s", "search_s"} <= set(q["timings"]))

    print("== persistencia/meta ==")
    meta = rag._load_meta(slug)
    check("meta gravada com modelo e contagem",
          meta.get("chunks") == 3 and meta.get("model") == "fake-deterministic", meta)
    check("indice fora do repo (base configuravel respeitada)",
          rag.CHROMA_BASE.startswith(tmp))

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{PASS} ok, {FAIL} fail")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
