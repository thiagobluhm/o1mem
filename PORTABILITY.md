# PORTABILITY — O(1)mem on any runtime

O(1)mem is not Claude Code. It is a thesis about **where state lives**: cheap index loaded always + expensive file loaded on demand + an O(1) ceiling that prevents the index from inflating. This is runtime-agnostic. This page is the **single source of truth** for the mapping — each port's `README` points here instead of repeating.

Read this in other languages: [Português (Brasil)](./docs/PORTABILITY.ptbr.md)

## What a runtime needs

| Capability | For what | Claude Code | Hermes |
|---|---|---|---|
| Read/write file | handover on disk, edit index | `Read` / `Write` | `read_file` / `write_file` |
| Search files | find handover, cross-references | `Grep` / `Glob` | `search_files` (content/files) |
| Ask the user | semantic doubt in chunking | `AskUserQuestion` | `clarify` |
| Delegate to subagent | validate breaks in large file | `Agent` / `Task` | `delegate_task` |
| Run command | `mkdir`, `git`, runtime check | `Bash` | `terminal` |
| Memory that survives reset | breadcrumb between sessions | auto-memory / `MEMORY.md` | `memory` tool / `MEMORY.md` |
| Growth trigger (optional) | remind when handover time | hook `UserPromptSubmit` (sync) | cron watchdog (async) |

## Conventions (translate to your runtime)

| Concept | Claude Code | Hermes |
|---|---|---|
| Clear context command | `/clear` | `/reset` or `/new` |
| Skills directory | `~/.claude/skills/` | `~/AppData/Local/hermes/skills/` |
| Agent root directory | `~/.claude/` | `~/AppData/Local/hermes/` |
| Project context file | `CLAUDE.md` | `AGENTS.md` or `.hermes.md` |
| Past session history | JSONL transcript | `session_search` (FTS5 in SQLite) |
| Invoke skill | `/handover`, `/organizador-mem` | `/skill handover`, `/skill organizador-mem` |

## What does NOT change across runtimes (the core)

- **3 cost layers:** Resume (dies on reset) → Index/memory (loads always, cheap) → Handover-file (loads on demand).
- **O(1) cap:** at most 2 RETOMADAs in the index history; the rest delegate to pointers + 30-day decay.
- **Retomada mode:** `rapida` (does not touch runtime) vs `verificada` (reverifies live state before claiming).
- **Agentic chunking** (organizador-mem): the boundary is decided by an agent that understands semantics, never by blind regex; ask when in doubt.
- **Index compression invariant:** densify prose, never the searchable payload nor the links.

To port to a new runtime: map the 6 capabilities from table 1, translate the conventions from table 2, and keep the core intact. If a capability is missing (e.g., no subagent), degrade — do the step yourself instead of delegating.
