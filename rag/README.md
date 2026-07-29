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
```

Indexação é **incremental por sha**: reindexar sem mudança embeda 0; um arquivo
alterado re-embeda só ele; bullet removido do archive some do índice. `--full`
reconstrói do zero.

## Testes

```
python test_rag_offline.py     # 15 checks, sem baixar modelo
```

A suíte roda com `O1MEM_RAG_FAKE_EMBED=1` (embedder determinístico por hash) e
corpus **100% sintético** — fixture jamais usa memória real, porque o repo é
público. Ela valida chunking, incremental, persistência e o join com o grafo;
a qualidade semântica real só se prova com o modelo de verdade, ao vivo.
