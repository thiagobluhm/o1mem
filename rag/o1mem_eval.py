#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
o1mem_eval.py — quanto do acervo o RAG realmente encontra. Em numero.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
Este produto sabe dizer quanto economiza e nao sabia dizer quanto ACERTA. Sao
duas afirmacoes diferentes, e so a primeira estava medida. O cap e o decay
tiram coisa da memoria quente; a defesa de que isso e seguro e "o que sai
continua alcancavel pelo acervo frio". Essa defesa era uma afirmacao de
arquitetura sem um numero atras. Um cetico ataca exatamente ali, e com razao:
economizar contexto jogando fora o que era preciso nao e economia, e perda com
outro nome.

Entao: hit@k e MRR sobre o acervo REAL, mais a mesma medida com busca
puramente textual, para separar o que o embedding acrescenta do que ja viria
de graca. Sem isso, "temos RAG" e marketing.

DE ONDE VEM O GABARITO (e por que ele e honesto)
------------------------------------------------
Nao ha rotulagem a mao aqui, e tambem nao ha gabarito inventado por um modelo.
O gabarito sai de um texto que ja existe e que o indice NUNCA viu: as chamadas
do `MEMORY.md`.

  `- [Titulo](project_x.md) — a chamada escrita a mao`   ->  query: a chamada
                                                             alvo : project_x

Isso funciona porque `collect_chunks()` PULA o `MEMORY.md` de proposito (ele ja
e carregado no boot; indexa-lo so duplicaria). Ou seja: a pergunta e prosa
humana sobre o fato, escrita noutro momento e noutro registro, e o embedder
nunca a viu. E o teste certo — recuperacao de item conhecido — e nao a
tautologia de perguntar com o proprio texto indexado.

LIMITE, DITO NA CARA
  A chamada e o fato foram escritos pela mesma pessoa, sobre o mesmo assunto,
  entao dividem vocabulario. Isso torna a medida OTIMISTA em relacao a uma
  pergunta feita meses depois, com outras palavras ("aquele problema do
  caminho errado"). O numero e um piso de sanidade do acervo, nao uma promessa
  de desempenho em pergunta livre. Para medir o caso dificil existe o gabarito
  manual (`--gold`), onde a pergunta e escrita de proposito com outras palavras.

USO
  python o1mem_eval.py --project <slug> [--handovers <dir>] [-k 5]
  python o1mem_eval.py --project <slug> --gold meu_gabarito.jsonl
  python o1mem_eval.py --project <slug> --json

  Gabarito manual: JSONL, uma consulta por linha
    {"q": "por que o handover saiu de documentacao?", "expect": "project_o1mem_handovers_fora_do_projeto"}
    {"q": "...", "expect": ["no_a", "no_b"]}      # qualquer um conta como acerto

SAIDA
  hit@1/@3/@5 e MRR para dois motores, em dois escopos.

  Motores:
    fulltext  — BM25 puro sobre os mesmos chunks, sem modelo nenhum
    semantico — o indice vetorial em vigor
  Se o ganho do segundo sobre o primeiro for ~zero, o embedding nao esta
  pagando o proprio custo neste acervo, e isso e uma informacao util.

  Escopos (sao duas perguntas diferentes, e so a primeira defende o cap):
    memoria   — so os fatos destilados. "O fato certo e achavel entre os
                fatos?" E o material que o boot carrega; e aqui que o produto
                precisa acertar.
    tudo      — fatos + acervo frio, que no uso real e a maior parte do corpus.
                A metrica continua ESTRITA: devolver o handover do assunto
                certo conta como erro, porque o alvo declarado e o fato. E um
                piso pessimista de proposito, e nao a experiencia de quem le a
                resposta — leia o numero sabendo disso.
"""
import argparse
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "graph")))

import o1mem_graph as og  # noqa: E402
import o1mem_rag as rag   # noqa: E402

RE_INDEX_LINK = re.compile(r"^\s*[-*]\s*\[([^\]]*)\]\(([^)\s]+\.md)\)\s*(.*)$", re.M)
RE_TOKEN = re.compile(r"[a-zA-Z0-9À-ſ]{3,}")


# --------------------------------------------------------------------------
# gabarito
# --------------------------------------------------------------------------
def _limpa_chamada(texto: str) -> str:
    """Tira a decoracao do indice e deixa so a prosa que descreve o fato."""
    t = re.sub(r"\[\[[^\]]+\]\]", " ", texto)          # wikilinks nao sao pergunta
    t = re.sub(r"[`*_>#]+", " ", t)
    t = re.sub(r"^[\s—\-–:·]+", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def gold_do_indice(root: str) -> list:
    """Gabarito automatico: cada chamada do MEMORY.md vira uma consulta.

    So entram linhas com chamada de verdade (>= 40 caracteres depois de limpa).
    Uma entrada so com o titulo repetiria o nome do arquivo e mediria casamento
    de string, nao recuperacao.
    """
    path = os.path.join(root, "MEMORY.md")
    if not os.path.exists(path):
        return []
    texto = open(path, "r", encoding="utf-8", errors="replace").read()
    fora = {"memory", "memory_archive"}
    out, vistos = [], set()
    for _titulo, alvo, resto in RE_INDEX_LINK.findall(texto):
        no = og.norm(alvo)
        if no in fora or no in vistos:
            continue
        q = _limpa_chamada(resto)
        if len(q) < 40:
            continue
        vistos.add(no)
        out.append({"q": q, "expect": [no], "origem": "indice"})
    return out


def gold_do_arquivo(path: str) -> list:
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for i, linha in enumerate(f, 1):
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            try:
                d = json.loads(linha)
            except ValueError:
                raise SystemExit("ERRO: linha %d de %s nao e JSON valido" % (i, path))
            exp = d.get("expect")
            exp = [exp] if isinstance(exp, str) else list(exp or [])
            if not d.get("q") or not exp:
                raise SystemExit("ERRO: linha %d precisa de 'q' e 'expect'" % i)
            out.append({"q": d["q"], "expect": [og.norm(e) for e in exp],
                        "origem": "manual"})
    return out


# --------------------------------------------------------------------------
# motores
# --------------------------------------------------------------------------
def _tok(s: str) -> list:
    return [t.lower() for t in RE_TOKEN.findall(s)]


class BM25:
    """Baseline textual. Existe para responder 'o embedding esta pagando o custo?'.

    Implementado aqui, e nao importado, porque a comparacao tem de rodar sobre
    EXATAMENTE os mesmos chunks que o indice vetorial recebeu — uma biblioteca
    com tokenizacao propria mediria outro corpus e a diferenca deixaria de ser
    atribuivel ao embedding.
    """

    def __init__(self, chunks, k1=1.5, b=0.75):
        self.ids = [c["id"] for c in chunks]
        self.docs = [_tok(c["text"]) for c in chunks]
        self.k1, self.b = k1, b
        self.n = len(self.docs) or 1
        self.avgdl = sum(len(d) for d in self.docs) / self.n
        self.df = {}
        for d in self.docs:
            for t in set(d):
                self.df[t] = self.df.get(t, 0) + 1
        self.tf = [{} for _ in self.docs]
        for i, d in enumerate(self.docs):
            for t in d:
                self.tf[i][t] = self.tf[i].get(t, 0) + 1

    def search(self, q, k):
        qs = _tok(q)
        scores = []
        for i, tf in enumerate(self.tf):
            dl = len(self.docs[i]) or 1
            s = 0.0
            for t in qs:
                f = tf.get(t)
                if not f:
                    continue
                idf = math.log(1 + (self.n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                s += idf * (f * (self.k1 + 1)) / (
                    f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            if s > 0:
                scores.append((s, self.ids[i]))
        scores.sort(reverse=True)
        return [i for _s, i in scores[:k]]


FRIOS = ("handover", "archive_bullet")


def so_memoria(chunks):
    """Os fatos DESTILADOS, sem o acervo frio."""
    return [c for c in chunks if c["meta"]["kind"] not in FRIOS]


def busca_semantica(col, embed, q, k, apenas_memoria=False):
    vec = embed([q])[0]
    kw = {}
    if apenas_memoria:
        kw["where"] = {"kind": {"$nin": list(FRIOS)}}
    res = col.query(query_embeddings=[vec], n_results=min(k, max(col.count(), 1)),
                    include=["metadatas"], **kw)
    return list(res["ids"][0])


# --------------------------------------------------------------------------
# metricas
# --------------------------------------------------------------------------
def _acerta(chunk_id: str, esperados: list) -> bool:
    """Um chunk conta como acerto se PERTENCE ao documento esperado.

    Handover e fatiado em `<no>::s3`, e o archive em `archive::<sha>`; cobrar o
    id exato do pedaco puniria o motor por achar a secao 2 em vez da 3 do
    documento certo, que para quem le e o mesmo acerto.
    """
    base = chunk_id.split("::")[0]
    return base in esperados or chunk_id in esperados


def avalia(gold, buscar, k):
    ranks = []
    for g in gold:
        ids = buscar(g["q"], max(k, 10))
        pos = next((i + 1 for i, cid in enumerate(ids) if _acerta(cid, g["expect"])), 0)
        ranks.append(pos)
    n = len(ranks) or 1
    return {
        "consultas": len(ranks),
        "hit@1": round(sum(1 for r in ranks if r == 1) / n, 3),
        "hit@3": round(sum(1 for r in ranks if 1 <= r <= 3) / n, 3),
        "hit@5": round(sum(1 for r in ranks if 1 <= r <= 5) / n, 3),
        "mrr@10": round(sum(1.0 / r for r in ranks if r) / n, 3),
        "sem_resposta": sum(1 for r in ranks if r == 0),
        "_ranks": ranks,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main(argv=None):
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="Qualidade de recall do RAG O(1)mem")
    ap.add_argument("--project", help="slug (ou parte dele) do projeto")
    ap.add_argument("--root", help="caminho direto para uma pasta memory/")
    ap.add_argument("--handovers", help="pasta de handovers a incluir no corpus")
    ap.add_argument("--gold", help="gabarito manual (JSONL)")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--model", default=rag.DEFAULT_MODEL)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    slug, root = og.resolve_root(args.project, args.root)
    handovers = args.handovers or os.path.normpath(
        os.path.join(root, os.pardir, "handovers"))

    gold = gold_do_arquivo(args.gold) if args.gold else gold_do_indice(root)
    if not gold:
        raise SystemExit(
            "ERRO: gabarito vazio.\n"
            "       Sem --gold, as consultas saem das chamadas do MEMORY.md\n"
            "       (linhas '- [Titulo](arquivo.md) — chamada'). Nenhuma com\n"
            "       chamada longa o bastante foi encontrada em %s." % root)

    chunks = rag.collect_chunks(root, handovers)
    if not chunks:
        raise SystemExit("ERRO: corpus vazio em %s" % root)

    # o gabarito so pode cobrar o que esta INDEXADO. Um alvo fora do corpus
    # viraria erro do motor, quando o defeito e de indexacao -- duas falhas
    # diferentes que precisam aparecer separadas.
    indexados = {c["id"].split("::")[0] for c in chunks}
    fora = [g for g in gold if not any(e in indexados for e in g["expect"])]
    gold = [g for g in gold if any(e in indexados for e in g["expect"])]
    if not gold:
        raise SystemExit("ERRO: nenhum alvo do gabarito esta no corpus indexado.")

    # DOIS escopos, porque sao duas perguntas diferentes e so uma delas defende
    # o cap:
    #   memoria — corpus so com os fatos destilados. "O fato certo e achavel
    #             entre os fatos?" E a pergunta que o produto precisa responder
    #             bem, porque esse e o material que o boot carrega.
    #   tudo    — fatos + acervo frio, que costuma ser a maior parte do corpus.
    #             A metrica segue estrita: devolver o handover do assunto CERTO
    #             conta como erro, porque o alvo declarado e o fato. E um piso
    #             pessimista de proposito, nao a experiencia de quem le.
    escopos = [("memoria", so_memoria(chunks)), ("tudo", chunks)]

    embed = col = erro_semantico = modelo = None
    try:
        embed, modelo = rag.get_embedder(args.model)
        col = rag.get_collection(slug)
        if col.count() == 0:
            raise RuntimeError("collection vazia -- rode `index` antes")
    except Exception as e:
        # Sem chromadb/sentence-transformers instalados o baseline ainda roda.
        # Reportar o TIPO da excecao, nunca a mensagem: string de conexao e
        # caminho autenticado vazam por dentro de `str(e)`.
        erro_semantico = type(e).__name__
        col = None

    saida = {"projeto": slug, "corpus": len(chunks), "gabarito": len(gold),
             "fora_do_corpus": len(fora), "origem_gabarito": gold[0]["origem"],
             "modelo": modelo, "escopos": {}}

    for nome_escopo, cs in escopos:
        bm = BM25(cs)
        r = {"chunks": len(cs),
             "fulltext": avalia(gold, lambda q, kk: bm.search(q, kk), args.k)}
        if col is not None:
            apenas = (nome_escopo == "memoria")
            r["semantico"] = avalia(
                gold,
                lambda q, kk, _a=apenas: busca_semantica(col, embed, q, kk, _a),
                args.k)
        saida["escopos"][nome_escopo] = r

    if erro_semantico:
        saida["semantico_indisponivel"] = erro_semantico

    if args.json:
        print(json.dumps(saida, ensure_ascii=False, indent=2))
        return 0

    n_mem = len(so_memoria(chunks))
    print("projeto        : %s" % slug)
    print("corpus         : %d chunk(s)  (%d fato(s) destilado(s), %d do acervo frio)"
          % (len(chunks), n_mem, len(chunks) - n_mem))
    print("gabarito       : %d consulta(s) (%s)%s"
          % (len(gold), gold[0]["origem"],
             "  [%d alvo(s) fora do corpus, ignorado(s)]" % len(fora) if fora else ""))
    if modelo:
        print("modelo         : %s" % modelo)

    for nome_escopo, _cs in escopos:
        r = saida["escopos"][nome_escopo]
        print()
        print("escopo %-8s (%d chunk(s))" % (nome_escopo, r["chunks"]))
        print("  %-10s %7s %7s %7s %8s  %s"
              % ("motor", "hit@1", "hit@3", "hit@5", "mrr@10", "sem resposta"))
        for m in ("fulltext", "semantico"):
            if m not in r:
                continue
            v = r[m]
            print("  %-10s %7.3f %7.3f %7.3f %8.3f  %d"
                  % (m, v["hit@1"], v["hit@3"], v["hit@5"], v["mrr@10"],
                     v["sem_resposta"]))
        if "semantico" in r:
            d = r["semantico"]["hit@5"] - r["fulltext"]["hit@5"]
            print("  ganho semantico : %+.3f em hit@5" % d)
            if d <= 0:
                print("  -> o embedding nao paga o proprio custo neste escopo:"
                      " o baseline textual empata ou ganha.")

    if erro_semantico:
        print()
        print("semantico      : indisponivel (%s) -- so o baseline rodou."
              % erro_semantico)
    return 0


if __name__ == "__main__":
    sys.exit(main())
