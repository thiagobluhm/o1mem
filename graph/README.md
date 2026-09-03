# `graph` — o grafo de navegação da memória

> **Não entra no caminho do boot.** O `MEMORY.md` continua sendo a entrada
> determinística, lida em O(1). Este módulo serve o *segundo* movimento: quando
> já existe uma pergunta e é preciso atravessar o acervo.

## Por que não é RAG

Porque **no boot não existe query**. O usuário só diz "retomar". Um retrieval
precisaria recuperar algo antes de haver pergunta — e o que ele recuperaria é o
próprio índice. Trocaríamos uma leitura determinística por uma probabilística
que resolve o mesmo problema com chance de errar, mais um vector DB para manter
sincronizado com ~100 arquivos editados à mão.

O grafo não tem esse problema porque **as arestas já existem**: são os
`[[wikilinks]]` que a skill `handover` manda escrever há semanas, mais os links
markdown do índice. Custo de indexação ≈ zero — é um parser, não um embedding.

## Modelo

| | |
|---|---|
| **Nó** | cada `.md` em `memory/` (incluindo `MEMORY.md` e `MEMORY_ARCHIVE.md`) |
| **Aresta `wiki`** | `[[nome]]` — o fio de raciocínio, escrito à mão |
| **Aresta `index`** | `[texto](arquivo.md)` — pertencimento ao índice quente/frio |
| **Aresta tipada** | `[[corrige:nome]]` — **o que** um fato faz com o outro (campo `rel`) |

### Relações tipadas

Um wikilink comum diz que dois fatos se tocam. Ele não diz se o segundo **corrige**
o primeiro, **contradiz** o primeiro ou apenas o menciona — e essa diferença é a que
importa numa memória destilada, onde reescrever um fato quando ele muda é a operação
central. Prefixar o alvo com um verbo declara isso:

```markdown
Este achado [[corrige:project_caminho_errado]] e [[contradiz:feedback_antigo]].
```

Vocabulário **fechado**: `causa`, `corrige`, `contradiz`, `substitui`, `depende`
(+ `causes`, `fixes`, `contradicts`, `supersedes`, `depends`). Um prefixo fora dessa
lista — `[[C:/tmp/x]]` — é tratado como parte do **nome**, nunca como relação
inventada. `[[nome]]` sem verbo continua exatamente como era, com `rel: null`: nada
do que já está escrito muda de significado.

A resolução de alvo é tolerante por desenho: `[[perguntar-antes-de-alterar-codigo]]`
casa com `feedback_perguntar_antes_de_alterar_codigo.md` (hífen ≡ underscore,
caixa livre, prefixo de tipo opcional). Só resolve quando o candidato é **único** —
na dúvida reporta quebrado em vez de inventar aresta. O que não resolve aparece em
`broken`, nunca é descartado em silêncio.

## Backend (CLI)

```bash
python o1mem_graph.py --project meuprojeto build      # grava graph.json
python o1mem_graph.py --project meuprojeto stats      # saúde do acervo
python o1mem_graph.py --project meuprojeto neighbors <nome> -d 2
python o1mem_graph.py --project meuprojeto path <a> <b>
python o1mem_graph.py --project meuprojeto orphans    # existem, mas nada leva até eles
python o1mem_graph.py --project meuprojeto broken
python o1mem_graph.py --project meuprojeto cold --days 30   # candidatos a decay
python o1mem_graph.py --project meuprojeto contradicoes     # afirmações incompatíveis vivas
```

Todo comando aceita `--json` — é assim que um agente consome. `--root <pasta>`
aponta uma `memory/` direta, para projetos sem slug próprio.

Sem dependências externas. Python 3.8+.

### `cold` — o que ele sugere, e o que ele nunca sugere

Candidato a decay = está no índice **quente**, é `project`, passou de N dias e
**nenhum outro fato o cita** (`wiki_in == 0`). Se alguém ainda cita, o assunto
segue vivo mesmo velho.

`feedback` nunca entra: é regra operacional permanente. Ela não envelhece por não
ser tocada — arquivá-la seria justamente arquivar a regra que já foi internalizada
e por isso parou de ser reescrita.

O comando **sugere**; quem move é humano.

### `contradicoes` — o custo de lembrar de duas versões

O modo de falha de uma memória destilada não é esquecer: é lembrar de **duas versões**
do mesmo fato e carregar as duas no boot como se ambas valessem. O `MEMORY.md` é lido
inteiro toda sessão — um fato superado que continua ali não é um arquivo velho parado
num canto, é uma afirmação ativa competindo com a correção dela.

Este comando acha isso cruzando as relações tipadas com o índice quente e as datas.
**Zero LLM**: são as arestas que o humano já escreveu, checadas contra si mesmas.

| Regra | O que acusa |
|---|---|
| `aberta` | `A contradiz B` e **os dois** no índice quente — o boot carrega as duas versões |
| `superado` | `A corrige B` e **B ainda** no índice quente — a versão corrigida segue sendo servida |
| `retroativa` | `A corrige B`, mas B foi escrito **depois** de A — relação invertida ou correção já velha |
| `ciclo` | `A substitui B` e `B substitui A` — as duas se declaram a mais nova, não há ordem |

Sai `1` quando há alguma de severidade **alta** (`aberta`, `superado`, `ciclo`), para
poder virar passo de verificação. Acervo sem nenhuma relação tipada nunca acusa nada.

## UI

```bash
python abrir_grafo.py --project meuprojeto
```

Constrói na hora (sem cache para ficar velho), injeta como `window.__O1MEM_GRAPH__`,
escreve `%TEMP%\o1mem_grafo.html` e abre. Página autocontida — zero CDN.

- **tamanho do nó** = quantas vezes é citado (`deg_in`)
- **arestas do índice ficam desligadas por padrão** — ligadas, tudo pendura no
  `MEMORY.md` e vira um hairball; desligadas, aparece o grafo *real* de raciocínio
- clique navega, busca destaca, chips filtram por tipo, arrasta/zoom na tela

## Teste

```bash
python test_contradicoes_offline.py   # arestas tipadas + validador
node test_ui_smoke.js                 # a UI contra o graph.json real
```

Monta um DOM mínimo e roda a UI contra o `graph.json` real — `node --check` só
pegaria erro de sintaxe, e o que quebra aqui é runtime (seletor que não casa,
nó filtrado virando seleção fantasma). Requer `build` antes.
