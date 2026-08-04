---
name: lembrar
description: Responde uma pergunta consultando o ACERVO FRIO da memória (handovers antigos, MEMORY_ARCHIVE.md) por busca semântica, sem retomar sessão nenhuma. Use sempre que o usuário perguntar sobre algo passado e a resposta não estiver no contexto — "você lembra do X?", "onde ficou aquilo de Y?", "em que sessão a gente resolveu Z?", "por que decidimos assim?", "/lembrar <assunto>". Existe porque o boot do O(1)mem carrega só o índice quente (MEMORY.md): o frio — o porquê das decisões, as alternativas descartadas — está indexado mas NINGUÉM O CONSULTA sozinho. Sem esta skill, a resposta honesta a "você lembra?" é "não", mesmo com a informação indexada a um comando de distância.
---

Você vai responder uma pergunta sobre o passado do projeto. A informação provavelmente
**existe e está indexada** — só não está no seu contexto, porque o acervo frio nunca entra
no boot. Seu trabalho é fazer o **segundo movimento**: consultar, ler a fonte, e responder.

## O bug que esta skill existe para matar

O usuário pergunta *"você lembra do X?"*. Você olha o contexto, não acha, e responde **"não"**.

A resposta está errada — não por má-fé, mas porque você respondeu com o corpus quente
(`MEMORY.md`, que carrega sozinho) sobre uma pergunta cuja resposta vive no corpus frio
(handovers antigos, `MEMORY_ARCHIVE.md`), que está indexado e a **um comando de distância**.

> **REGRA DURA:** não responda "não lembro" / "não tenho essa informação" sobre o passado
> do projeto **antes de rodar a query**. A ausência no contexto não é evidência de ausência
> no acervo — é só evidência de que o acervo é frio. Se depois da query não houver hit, aí
> sim diga que não achou, e diga **onde** procurou.

## Passo 1 — Resolva o projeto (barato, sem cerimônia)

**Default: o projeto do diretório atual.** O `--project` aceita **parte** do slug, então na
prática o nome da pasta do projeto basta.

| Situação | O que fazer |
|---|---|
| Usuário nomeou (`/lembrar credenciais --p OUTROPROJ`, "lembra do X lá na OUTROPROJ") | Use o nome dado |
| Não nomeou | Use o diretório atual, e **diga qual projeto consultou** ao responder |
| Query não retorna nada | Antes de desistir, liste os projetos e tente o mais provável — ver Passo 4 |

> **Por que isto NÃO é o `/retomar`.** Lá, projeto errado custa uma sessão inteira e passa
> despercebido — por isso aquela skill **pergunta** em vez de chutar. Aqui, projeto errado
> custa 5 segundos e é **óbvio na hora** (os hits vêm sem relação com a pergunta). Risco
> assimétrico, protocolo assimétrico: aqui você chuta o barato e corrige.

## Passo 2 — Rode a query CEDO

```bash
npx @tbluhm82/o1mem query "<a pergunta do usuário>" -k 5
npx @tbluhm82/o1mem query "<pergunta>" --project <slug> -k 5   # projeto explícito
```

Instalação a partir do repo, sem npm — chame o Python direto:

```bash
python <repo>/rag/o1mem_rag.py --project <slug> query "<pergunta>" -k 5
```

Três coisas que mudam o resultado:

- **Use as palavras do usuário**, não as suas. A busca é semântica: reescrever a pergunta em
  vocabulário técnico afasta do jeito que a coisa foi escrita no handover.
- **A primeira query da sessão leva ~45s** (carrega o modelo de embeddings). Dispare-a
  **antes** de ler qualquer arquivo, não depois — e avise o usuário que está buscando, senão
  parece travado.
- **`-k 5`, não `-k 3`.** Aqui você não sabe o que procura; hit 4 respondendo é comum.

## Passo 3 — Leia os hits pelo TIPO

Os hits vêm marcados. Os dois tipos têm papéis diferentes e confundi-los desperdiça a busca:

- **`(handover)` = acervo frio. É A RESPOSTA**, não um índice para outra coisa. Se o trecho
  responde a pergunta, **abra o handover de origem** e responda a partir dele. Não descarte
  um hit por ele não ser `project_*.md`.
- **`(memory)` = corpus quente.** Serve de desempate para decidir qual `project_*.md` abrir.

Sempre **abra a fonte** antes de afirmar. O chunk é um trecho: ele diz que o assunto está
ali, não necessariamente a conclusão inteira. Responder pelo chunk sem abrir o arquivo é
como citar uma frase pelo resultado da busca.

## Passo 4 — Responda. Não despeje.

A entrega é **uma resposta em prosa, com a fonte citada** — não a saída da busca colada.

```
Sim — [resposta direta].
[o porquê, se o handover registrar]

Fonte: HANDOVER_20260712_143000.md (sessão de 12/jul)
```

- **Citar é obrigatório.** Nome do arquivo e data. É o que permite o usuário conferir e o que
  separa "lembrei" de "inventei".
- **Se os hits divergirem** (dois handovers dizendo coisas diferentes), diga isso, com as
  datas — o mais recente costuma ser a decisão que valeu, mas quem decide é o usuário.
- **Se não houver hit útil**, seja específico no fracasso: *"consultei o índice do projeto X
  (N chunks) e não achei nada sobre isso"*. Ofereça o próximo passo real — outro projeto,
  ou reindexar incluindo os handovers (`--handovers DIR`), que é a causa mais comum de
  acervo frio faltando no índice.
- **Índice vazio ou inexistente** (`stats` retorna 0 chunks): não é "não lembro", é "o
  acervo desse projeto nunca foi indexado". Diga assim e ofereça rodar
  `npx @tbluhm82/o1mem index --project <slug>`.

## O que esta skill NÃO é

- **Não retoma sessão.** Não lê modo de retomada, não abre o `RETOMADA`, não propõe próximo
  passo. Pergunta respondida, fim. Se o usuário quer voltar a trabalhar, é `/retomar`.
- **Não escreve memória.** Consulta é leitura. Se algo que emergiu merece virar memória, o
  usuário pede.
- **Não indexa.** Se o índice está velho ou vazio, ela **avisa e oferece** — não roda
  reindexação por conta própria (é lento e o usuário pode estar no meio de outra coisa).
- **Não responde "não lembro" sem ter buscado.** Esse é o bug que ela existe para matar.
