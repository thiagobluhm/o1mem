# PORTABILITY — O(1)mem em qualquer runtime

O O(1)mem não é do Claude Code. É uma tese sobre **onde o estado mora**: índice barato carregado sempre + arquivo caro carregado sob demanda + um teto O(1) que impede o índice de inflar. Isso independe de runtime. Esta página é a **fonte única** do mapeamento — o `README` de cada porta aponta pra cá em vez de repetir.

## O que um runtime precisa ter

| Capacidade | Pra quê | Claude Code | Hermes |
|---|---|---|---|
| Ler/escrever arquivo | handover em disco, editar índice | `Read` / `Write` | `read_file` / `write_file` |
| Buscar em arquivos | achar handover, referências cruzadas | `Grep` / `Glob` | `search_files` (content/files) |
| Perguntar ao usuário | dúvida semântica no chunking | `AskUserQuestion` | `clarify` |
| Delegar a subagente | validar quebras em arquivo grande | `Agent` / `Task` | `delegate_task` |
| Rodar comando | `mkdir`, `git`, verificação de runtime | `Bash` | `terminal` |
| Memória que sobrevive ao reset | breadcrumb entre sessões | auto-memory / `MEMORY.md` | `memory` tool / `MEMORY.md` |
| Gatilho de crescimento (opcional) | lembrar a hora do handover | hook `UserPromptSubmit` (sync) | cron watchdog (async) |

## Convenções (traduza ao seu runtime)

| Conceito | Claude Code | Hermes |
|---|---|---|
| Comando de limpar contexto | `/clear` | `/reset` ou `/new` |
| Dir de skills | `~/.claude/skills/` | `~/AppData/Local/hermes/skills/` |
| Dir raiz do agente | `~/.claude/` | `~/AppData/Local/hermes/` |
| Arquivo de contexto do projeto | `CLAUDE.md` | `AGENTS.md` ou `.hermes.md` |
| Histórico de sessões passadas | transcript JSONL | `session_search` (FTS5 na SQLite) |
| Invocar a skill | `/handover`, `/organizador-mem` | `/skill handover`, `/skill organizador-mem` |

## O que NÃO muda entre runtimes (o núcleo)

- **3 camadas de custo:** Resume (morre no reset) → Índice/memória (carrega sempre, barato) → Handover-arquivo (carrega só quando aberto).
- **Cap O(1):** no máximo 2 RETOMADAs no histórico do índice; o resto delega aos ponteiros. + decay de 30 dias.
- **Modo de retomada:** `rapida` (não toca runtime) vs `verificada` (reverifica o estado vivo antes de afirmar).
- **Chunking agêntico** (organizador-mem): a fronteira é decidida por um agente que entende a semântica, nunca por regex cego; na dúvida, pergunta.
- **Invariante de compressão do índice:** densifique a prosa, nunca o payload buscável nem os links.

Para portar a um runtime novo: mapeie as 6 capacidades da 1ª tabela, traduza as convenções da 2ª, e mantenha o núcleo intacto. Se faltar uma capacidade (ex.: sem subagente), degrade — faça o passo você mesmo em vez de delegar.
