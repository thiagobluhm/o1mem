# 🔎 rag — a busca semântica da memória

O grafo (`skills/graph/`) atravessa o acervo por **estrutura**: quem cita quem.
Esta skill atravessa por **significado**: *"qual fio fala disso?"* — mesmo quando
ninguém escreveu o wikilink. E as duas se somam: a query devolve os top-k
semânticos **mais os vizinhos estruturais** de cada um, porque a semântica acha
o tema e o grafo traz o fio de raciocínio que o embedding não vê.

## O que ela NÃO é

- **Não toca o boot.** O `MEMORY.md` continua sendo a entrada determinística em
  O(1). O veredito antigo "RAG descartado" era sobre substituir o boot — este
  módulo serve o *segundo movimento* (travessia sob demanda), o mesmo lugar
  onde o grafo já vive.
- **Não é um serviço.** É uma CLI offline, como o grafo. Integração com o hook
  de nudge é fase 2, condicionada à latência medida (`timings` na query existe
  para isso).

## O maior ganho: o acervo FRIO

O `MEMORY_ARCHIVE.md` nunca é carregado no boot — é justamente onde a busca
lexical falha ("em que sessão resolvemos aquilo de credenciais?"). Cada bullet
do archive vira um chunk. O índice quente (`MEMORY.md`) fica **fora** do corpus:
ele já está no contexto de toda sessão; indexá-lo só duplicaria.

| Fonte | Chunking |
|---|---|
| `project_*.md`, `feedback_*.md`, `user_*.md`, `reference_*.md` | 1 arquivo = 1 chunk (fatos atômicos por desenho) |
| `MEMORY_ARCHIVE.md` | 1 bullet = 1 chunk |
| `HANDOVER_*.md` (opcional, `--handovers DIR`) | 1 seção `##` = 1 chunk |

A `description` do frontmatter entra no texto embedado — é o resumo curado à
mão e ancora a busca melhor que o corpo sozinho.

## Dado fora do repo (regra dura)

O índice vetorial carrega o **texto integral** da memória — que pode ser
privada — e este repo é **público**. Por isso o Chroma persiste em
`~/.claude/o1mem/chroma/<slug>/`, nunca dentro do repo. Não é gitignore: o
dado simplesmente nunca entra no worktree.

## Modelo

Default: `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers,
~470 MB com torch CPU, custo zero de API) — a memória é escrita em pt-BR e os
modelos ONNX default do Chroma são treinados em inglês. Troque com `--model`
ou env `O1MEM_RAG_MODEL`.

## Uso

```
pip install chromadb sentence-transformers   # opt-in: só esta skill precisa

python o1mem_rag.py index   --project X [--full] [--handovers DIR]
python o1mem_rag.py query   "custo do indice e decay" -k 3 [--json] [--no-graph]
python o1mem_rag.py stats

python o1mem_eval.py --project X                 # quanto ele ACERTA, em número
python o1mem_eval.py --project X --gold meu.jsonl
```

Indexação é **incremental por sha**: reindexar sem mudança embeda 0; um arquivo
alterado re-embeda só ele; bullet removido do archive some do índice. `--full`
reconstrói do zero.

## Qualidade de recall — o número

Este produto sabia dizer quanto **economiza** e não sabia dizer quanto **acerta**.
São duas afirmações diferentes, e só a primeira estava medida. O cap e o decay tiram
coisa da memória quente; a defesa de que isso é seguro é *"o que sai continua
alcançável pelo acervo frio"* — uma afirmação de arquitetura sem um número atrás.
É exatamente aí que um cético ataca, e com razão: economizar contexto jogando fora o
que era preciso não é economia, é perda com outro nome.

`o1mem_eval.py` mede `hit@k` e `MRR` sobre o acervo **real**, contra um baseline BM25
puro rodando nos **mesmos chunks** — a comparação existe para responder se o embedding
está pagando o próprio custo.

**De onde vem o gabarito.** Sem rotulagem à mão e sem gabarito inventado por um modelo:
as consultas são as **chamadas do `MEMORY.md`**, que o índice nunca viu (`collect_chunks`
pula o `MEMORY.md` de propósito). É recuperação de item conhecido, não a tautologia de
perguntar com o próprio texto indexado. O limite, dito na cara: a chamada e o fato foram
escritos pela mesma pessoa e dividem vocabulário, então a medida é **otimista**. Para o
caso difícil — a pergunta feita meses depois, com outras palavras — existe `--gold`.

**Medido neste acervo** (16 consultas do gabarito manual em `eval/goldset-o1mem.jsonl`,
escritas de propósito sem o vocabulário dos fatos; corpus de 97 chunks, dos quais 18 são
fatos destilados e 79 acervo frio):

| escopo | motor | hit@1 | hit@3 | hit@5 | mrr@10 |
|---|---|---|---|---|---|
| memória | fulltext | 0.312 | 0.438 | 0.562 | 0.429 |
| memória | **semântico** | 0.312 | **0.562** | **0.750** | **0.484** |
| tudo (estrito) | fulltext | 0.188 | 0.312 | 0.375 | 0.297 |
| tudo (estrito) | semântico | 0.062 | 0.062 | 0.250 | 0.140 |

Duas leituras, e as duas importam:

- **No escopo que defende o cap** — só os fatos destilados, que é o material que o boot
  carrega — o embedding ganha do baseline textual: **+0.19 em hit@5**. Ele paga o próprio
  custo.
- **No corpus inteiro ele perde**, e a razão é honesta: 79 dos 97 chunks são handovers, e
  a métrica é estrita — devolver o handover do assunto **certo** conta como erro, porque o
  alvo declarado é o fato. É um piso pessimista de propósito, não a experiência de quem lê
  a resposta. Mas é também o sinal de um problema real: o acervo frio abafa os fatos na
  busca, e nenhuma das duas engenhocas resolve isso sozinha.

Com o gabarito **automático** os dois motores saturam em `hit@5 ≈ 1.000`. Isso não é uma
boa notícia — é a confirmação de que aquele gabarito é fácil demais para discriminar, e
por isso o manual existe.

## Testes

```
python test_rag_offline.py     # 15 checks, sem baixar modelo
python test_eval_offline.py    # a mecânica da medição de recall
```

A suíte roda com `O1MEM_RAG_FAKE_EMBED=1` (embedder determinístico por hash) e
corpus **100% sintético** — fixture jamais usa memória real, porque o repo é
público. Ela valida chunking, incremental, persistência e o join com o grafo;
a qualidade semântica real é medida à parte, com o modelo de verdade, pelo
`o1mem_eval.py` — ver a seção acima. O `test_eval_offline.py` cobre a mecânica
da medição (de onde sai o gabarito, o que conta como acerto, se as métricas
batem contra um ranking conhecido), não a qualidade do modelo: um harness de
avaliação que mede errado é pior que nenhum, porque produz um número com
aparência de evidência.
