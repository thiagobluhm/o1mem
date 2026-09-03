#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Suite OFFLINE das arestas tipadas e do validador de contradicao.

Corpus 100% sintetico (o repo e publico: fixture jamais toca a memoria real).
Sem dependencia externa — o grafo nao tem nenhuma, e este teste tambem nao.

Testes:
  1. `[[corrige:x]]` vira aresta com rel; `[[x]]` continua rel=None
  2. prefixo desconhecido (`[[C:/tmp/x]]`) NAO vira relacao
  3. regra "aberta"     — contradiz com os dois no indice quente
  4. regra "superado"   — corrige um alvo que segue no indice quente
  5. regra "retroativa" — o alvo e mais novo que quem o corrige
  6. regra "ciclo"      — A substitui B e B substitui A
  7. acervo consistente -> lista vazia
  8. compatibilidade — corpus sem nenhuma relacao nao acusa nada

  python test_contradicoes_offline.py
"""
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import o1mem_graph as og  # noqa: E402

falhas = []


def check(nome, cond, detalhe=""):
    print(("  OK   " if cond else "  FALHA ") + nome + (("  -- " + detalhe) if detalhe and not cond else ""))
    if not cond:
        falhas.append(nome)


def escrever(root, nome, corpo, tipo="project", idade_dias=0):
    path = os.path.join(root, nome)
    with open(path, "w", encoding="utf-8") as f:
        f.write("---\nname: %s\ndescription: fixture\nmetadata:\n  type: %s\n---\n\n%s\n"
                % (nome[:-3], tipo, corpo))
    if idade_dias:
        t = time.time() - idade_dias * 86400
        os.utime(path, (t, t))
    return path


def indice(root, nomes):
    """MEMORY.md = indice QUENTE. So o que esta linkado aqui e carregado no boot."""
    with open(os.path.join(root, "MEMORY.md"), "w", encoding="utf-8") as f:
        f.write("# Memory Index\n\n")
        for n in nomes:
            f.write("- [%s](%s) — fixture\n" % (n[:-3], n))


def build(root):
    return og.build_graph(root, "fixture")


def regras(g):
    return sorted({c["rule"] for c in og.contradictions(g)})


def main():
    tmp = tempfile.mkdtemp(prefix="o1mem_contra_")
    try:
        # ---------------- 1 e 2: parsing das arestas tipadas
        r1 = os.path.join(tmp, "r1")
        os.makedirs(r1)
        escrever(r1, "project_a.md", "Fato A. Isto [[corrige:project_b]] e cita [[project_c]].")
        escrever(r1, "project_b.md", "Fato B. Caminho [[C:/tmp/x]] nao e relacao.")
        escrever(r1, "project_c.md", "Fato C.")
        indice(r1, ["project_a.md"])
        g = build(r1)
        rels = {(e["source"], e["target"]): e.get("rel") for e in g["edges"]}
        check("1. [[corrige:x]] carrega rel='corrige'",
              rels.get(("project_a", "project_b")) == "corrige", str(rels))
        check("1b. [[x]] simples continua rel=None",
              ("project_a", "project_c") in rels
              and rels[("project_a", "project_c")] is None, str(rels))
        check("2. prefixo desconhecido nao vira relacao",
              all(v != "c" for v in rels.values())
              and not any(e.get("rel") for e in g["edges"] if e["source"] == "project_b"),
              str(rels))

        # ---------------- 3: aberta (dois vivos no indice quente)
        r3 = os.path.join(tmp, "r3")
        os.makedirs(r3)
        escrever(r3, "project_novo.md", "Versao nova. [[contradiz:project_velho]].")
        escrever(r3, "project_velho.md", "Versao velha.", idade_dias=10)
        indice(r3, ["project_novo.md", "project_velho.md"])
        check("3. contradiz com ambos no quente -> 'aberta'",
              "aberta" in regras(build(r3)), str(og.contradictions(build(r3))))

        # ---------------- 4: superado (alvo corrigido segue no quente)
        r4 = os.path.join(tmp, "r4")
        os.makedirs(r4)
        escrever(r4, "project_fix.md", "Correcao. [[corrige:project_bug]].")
        escrever(r4, "project_bug.md", "Comportamento antigo.", idade_dias=10)
        indice(r4, ["project_fix.md", "project_bug.md"])
        check("4. corrige alvo ainda quente -> 'superado'",
              "superado" in regras(build(r4)))

        # ---------------- 5: retroativa (alvo mais novo que quem corrige)
        r5 = os.path.join(tmp, "r5")
        os.makedirs(r5)
        escrever(r5, "project_antigo.md", "Correcao velha. [[corrige:project_recente]].",
                 idade_dias=20)
        escrever(r5, "project_recente.md", "Escrito depois.")
        indice(r5, ["project_antigo.md"])   # alvo fora do quente: isola a regra
        check("5. alvo mais novo que a correcao -> 'retroativa'",
              regras(build(r5)) == ["retroativa"], str(regras(build(r5))))

        # ---------------- 6: ciclo
        r6 = os.path.join(tmp, "r6")
        os.makedirs(r6)
        escrever(r6, "project_x.md", "X. [[substitui:project_y]].", idade_dias=1)
        escrever(r6, "project_y.md", "Y. [[substitui:project_x]].", idade_dias=1)
        indice(r6, [])
        check("6. substituicao mutua -> 'ciclo'", "ciclo" in regras(build(r6)))
        check("6b. o par de ciclo e reportado UMA vez",
              len([c for c in og.contradictions(build(r6)) if c["rule"] == "ciclo"]) == 1)

        # ---------------- 7: acervo consistente
        r7 = os.path.join(tmp, "r7")
        os.makedirs(r7)
        escrever(r7, "project_v2.md", "Versao 2. [[substitui:project_v1]].")
        escrever(r7, "project_v1.md", "Versao 1.", idade_dias=30)
        indice(r7, ["project_v2.md"])       # o superado saiu do quente: resolvido
        check("7. correcao aplicada e alvo fora do quente -> nada a acusar",
              og.contradictions(build(r7)) == [], str(og.contradictions(build(r7))))

        # ---------------- 8: compatibilidade com acervo sem relacoes
        r8 = os.path.join(tmp, "r8")
        os.makedirs(r8)
        escrever(r8, "project_p.md", "Fala de [[project_q]] sem tipar nada.")
        escrever(r8, "project_q.md", "Outro fato.")
        indice(r8, ["project_p.md", "project_q.md"])
        g8 = build(r8)
        check("8. corpus sem relacoes tipadas nao acusa contradicao",
              og.contradictions(g8) == [])
        check("8b. as arestas nao tipadas continuam existindo",
              any(e["source"] == "project_p" and e["target"] == "project_q"
                  for e in g8["edges"]))
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
