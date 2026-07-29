---
name: organizador-mem
description: Reorganiza um arquivo de contexto grande (AGENTS.md, .hermes.md, README extenso, doc de regras) separando NÚCLEO CONCEITUAL (identidade, princípios sempre-relevantes) de TÓPICOS OPERACIONAIS (leis, regras técnicas, backlogs), que viram documentos próprios referenciados por um mapa. O chunking é feito por um SUBAGENTE que valida a SEMÂNTICA de cada quebra — não é split mecânico por regex/heading. Sempre que houver dúvida sobre se uma quebra faz sentido, PERGUNTA ao usuário antes de aplicar (use a ferramenta `clarify`). Use quando um arquivo de instruções está grande demais (consumo de tokens alto, navegação difícil) e precisa ser fatiado sem perder conteúdo nem contexto.
---

Você vai reorganizar um arquivo de contexto grande (tipicamente `AGENTS.md` ou `.hermes.md`) em **núcleo + documentos satélite**, para reduzir consumo de tokens por leitura e agilizar navegação — **sem perder uma linha de conteúdo e sem quebrar nenhum vínculo semântico**.

## Princípio central: chunking AGÊNTICO, não mecânico

> **Achado do usuário durante a primeira execução desta skill:** um separador mecânico (cortar em cada `##`) funciona quando o arquivo já tem seções bem demarcadas e auto-contidas — mas **não é o método padrão**. Arquivos reais têm seções que se referenciam cruzadamente, subseções que pertencem semanticamente a um tópico diferente do header pai, ou um único `##` que mistura 2+ conceitos que deveriam virar documentos separados.

**Portanto: a fronteira de cada chunk é decidida por um SUBAGENTE que lê e entende o conteúdo — nunca por um script de regex sozinho.** O regex/heading serve só para propor candidatos; quem decide se o candidato é uma unidade semântica coesa é o subagente (use `delegate_task` para subagentes dedicados se o arquivo for muito grande). Quando o subagente tem dúvida (dois candidatos parecem fortemente acoplados, ou uma seção parece pertencer a dois tópicos), **ele não decide sozinho — reporta a dúvida para você perguntar ao usuário** (via ferramenta `clarify` ou pergunta direta). Nunca aplique um split sob incerteza semântica sem confirmação humana.

## Quando usar

- Um arquivo de instruções (`AGENTS.md`, `.hermes.md`, `CLAUDE.md`, README de arquitetura) cresceu a ponto de:
  - Consumir uma fração grande do budget de contexto só para ser lido por inteiro.
  - Misturar identidade do projeto (sempre relevante) com regras técnicas específicas (relevantes só quando a tarefa toca aquele tópico).
  - Ter navegação difícil (usuário/agente precisa rolar centenas de linhas para achar uma regra).
- **Não usar** para arquivos já pequenos/coesos (<300 linhas) — o custo de fragmentar supera o ganho.

## Protocolo (4 fases)

### FASE 1 — Levantamento estrutural (mecânico, rápido)

1. Leia o arquivo inteiro com `read_file` (use `offset`/`limit` para paginar se necessário).
2. Rode `search_files` (target='content') com padrão `^#{1,3} ` para obter o mapa bruto: título + linha de cada seção.
3. Esse mapa é só o **ponto de partida** — candidatos a chunk, não o resultado final.

### FASE 2 — Validação semântica agêntica (o coração da skill)

Para cada candidato de seção (ou grupo de seções vizinhas), você (ou um subagente dedicado via `delegate_task`, se o arquivo for muito grande) responde:

1. **Esta seção é uma unidade conceitual coesa?** (fala de UM assunto, não mistura dois)
2. **Ela referencia fortemente uma seção vizinha?** (ex.: "ver §X" constante, exemplos que dependem de outra seção) — se sim, considerar mesclar num único documento.
3. **É NÚCLEO (sempre relevante, qualquer tarefa) ou TÓPICO (relevante só quando a tarefa toca aquele assunto)?**
   - Núcleo típico: identidade do projeto, princípios inegociáveis, fluxo de trabalho padrão, tabela "o que nunca fazer", referências rápidas.
   - Tópico típico: leis específicas de subsistema, regras técnicas de uma camada, backlogs, débitos técnicos, histórico de incidentes.
4. **Se a resposta a 1 ou 3 não for óbvia → PARE e pergunte ao usuário** (via ferramenta `clarify`, oferecendo as opções concretas: "mesclar com X", "manter separado", "é núcleo ou tópico"). Não resolva a dúvida sozinho advinhando.

Registre o veredito de cada candidato numa tabela mental/rascunho: `[seção] → [núcleo | tópico:nome-do-doc-destino] → [confiança]`.

### FASE 3 — Execução (extração verbatim)

1. Crie a pasta de destino (padrão: `documentacao/regras/` ao lado do arquivo núcleo — use `terminal` com `mkdir -p` se necessário; adaptar se o projeto já tiver convenção própria).
2. Para cada grupo aprovado na Fase 2 como TÓPICO: use `write_file` para criar um arquivo próprio contendo:
   - Header com nome descritivo do tópico (não "seção 7" — o NOME do conceito).
   - Uma linha de proveniência: `> Extraído de <arquivo-origem> §N. Voltar ao índice em <caminho-do-núcleo>.`
   - O conteúdo **verbatim** (zero perda, zero paráfrase) — só reindente headers se necessário (de `##` pai para `#`/`##` no arquivo próprio).
   - Se o conteúdo citava outra seção que também foi extraída (ex.: "ver §14"), **atualize a referência cruzada** para apontar ao novo arquivo (`ver LEI_14_CASCATA_RESPOSTA.md`) — nunca deixe um link morto apontando pra um número de seção que não existe mais.
3. Reescreva o arquivo núcleo com `write_file`:
   - Mantém as seções aprovadas como NÚCLEO, verbatim.
   - No lugar de cada seção extraída, **não** deixa buraco — a referência aparece só uma vez, no **mapa** (não espalhada).
   - Adiciona uma seção `§0` ou `§X — MAPA DE REGRAS EXTERNAS`: uma tabela com **nome do documento + descrição completa do que contém + quando ler** (não é "ver arquivo X", é uma descrição que permite ao leitor decidir SE precisa abrir o arquivo, sem precisar abrir para descobrir).
   - Regra de ouro do mapa: a descrição de cada linha deve ser boa o suficiente para que 80% das vezes o leitor saiba se precisa ou não abrir aquele documento, só de ler a linha.

### FASE 4 — Verificação de integridade (obrigatória antes de considerar concluído)

1. Confirme que **nenhum conteúdo foi perdido** — some linhas dos documentos extraídos + linhas do núcleo final ≈ linhas do arquivo original (mais alguma expansão de headers/proveniência, nunca menos conteúdo substantivo).
2. Rode `search_files` (target='content') no conjunto de arquivos novos por referências cruzadas antigas (`§14`, `§18`, "ver seção X") que possam ter ficado órfãs — corrija.
3. Se havia uma skill/matriz/documento EXTERNO que já referenciava seções do arquivo original por número (ex.: uma skill de conformidade citando "§18.5"), **atualize essas referências também** — não deixe só o núcleo consistente.
4. Reporte ao usuário: lista dos documentos criados + tabela do mapa + confirmação de que a Fase 4 não achou perda/link morto.

## Quando PERGUNTAR ao usuário (não decidir sozinho)

Use a ferramenta `clarify` nestes casos:

- Uma seção parece pertencer a DOIS tópicos igualmente bem (ex.: mistura regra de roteamento com regra de agnosticidade).
- Não está claro se algo é núcleo ou tópico (ex.: uma regra "inegociável" mas muito técnica/específica — inegociável sugere núcleo, técnica sugere tópico).
- O arquivo tem seções duplicadas ou com numeração quebrada (ex.: dois "## 4." diferentes, ou "## 15." aparecendo duas vezes) — isso é sinal de que o arquivo original já cresceu organicamente sem disciplina; pergunte se o usuário quer renumerar/consolidar ou só preservar como está.
- O tamanho de um candidato de tópico é enorme (ex.: >400 linhas) — pergunte se quebra em sub-tópicos ou mantém como 1 arquivo grande (às vezes faz sentido manter unido por ser uma narrativa cronológica/backlog).

## Erros a evitar (lições da primeira execução)

- ❌ **Split mecânico cego por `##`** sem checar se a seção é coesa — pode fragmentar um raciocínio ao meio ou juntar dois assuntos por acidente.
- ❌ **Perder referências cruzadas** — se a seção 18 cita "ver §14-bis" e a 14-bis virou outro arquivo, o texto tem que apontar pro arquivo novo, não pro número morto.
- ❌ **Resumir ao extrair** — a extração é verbatim. Resumir é uma segunda operação (compressão), e se for feita, tem que ser explícita e aprovada — não misturar com o ato de mover o conteúdo.
- ❌ **Esquecer os consumidores externos** — outras skills/docs do projeto podem já citar "AGENTS.md §X" ou "CLAUDE.md §X"; sua reorganização quebra essas referências se você não as atualizar também.

## Compressão de índice-ponteiro (quando a operação é comprimir, não mover)

Comprimir um índice (ex.: `MEMORY.md`, um sumário, uma tabela de mapa) é operação DISTINTA de mover — e tem um invariante próprio. Ao densificar:

- **Densifique a PROSA, nunca o PAYLOAD buscável.** Troque explicação gramatical por sintaxe `Gatilho → Ação`, abrevie datas/rótulos, use flags de status (`❌ morto`, `🚀 publicado`, `✅ fechado`, `⚠️ risco`) para o LLM escanear estado sem ler a frase inteira, e converta regras em imperativos curtos (`NUNCA…`, `SEMPRE…`). Mas o **estado semântico** (o que está pendente, o número, o ID, a data) é o que a IA busca — cortar isso é perda, não compressão.
- **NUNCA drope um link que carrega estrutura.** Se o índice é um ponteiro (cada linha aponta um arquivo que outro processo consulta — ex.: um protocolo de save que verifica "já existe arquivo cobrindo isto?" pelo link), remover o `[texto](arquivo.md)` órfã o arquivo do índice e quebra o invariante. **O link é a URL entre parênteses, não o rótulo:** se o rótulo apenas repete o nome do arquivo (`[x.md](x.md)`), ele é redundante — encurte o rótulo (`[↗](x.md)`) e o link sobrevive intacto. Economize no rótulo, nunca na URL.
- **Preserve 100% dos IDs/labels, datas e estados.** A meta é menos tokens de formatação, não menos fatos.
- **Meça antes/depois** (bytes + contagem de links + IDs) e reporte a taxa real. Se a compressão só rende cortando conteúdo buscável, **pare e diga isso** — comprimir mais não vale o buraco de memória.

## Mapeamento de ferramentas (Claude Code → Hermes)

| Claude Code | Hermes equivalente |
|---|---|
| `Read` | `read_file` |
| `Write` | `write_file` |
| `Grep` | `search_files` (target='content') |
| `Glob` | `search_files` (target='files') |
| `AskUserQuestion` | `clarify` |
| `Agent` / `Task` (subagent) | `delegate_task` |
| `CLAUDE.md` | `AGENTS.md` ou `.hermes.md` |

## Resultado esperado (formato de entrega ao usuário)

```
## Documentos criados
| Arquivo | Extraído de | Linhas |
|---|---|---|

## Núcleo reescrito
<caminho> — de N linhas para M linhas

## Verificação de integridade
- [ ] Conteúdo total preservado (soma bate)
- [ ] Referências cruzadas corrigidas (lista se houve)
- [ ] Consumidores externos atualizados (lista se houve)

## Dúvidas que precisei te perguntar (se houve)
```
