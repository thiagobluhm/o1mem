# @tbluhm82/o1mem — instalador

Por quê um instalador npm?

O Runtime que indexa e busca a memória é Python (skillRag, modelos transformers).
Mas Node é o padrão de instalação portável para ferramentas que cruzam sistemas:
detecta Python, pede chave, instala dependencies, indexa projetos, registra o hook.
Tudo num comando, zero risco de dependências enfiadas manualmente no meio.

## Fluxo

```
npx @tbluhm82/o1mem install
  ✓ Verifica Python ≥ 3.8 + pip
  ✓ Lista projetos em ~/.claude/projects/*/memory/
  ✓ Você escolhe quais indexar (multi-select)
  ✓ Escolhe modo: local (grátis) | aprendizado (chave requerida)
  ✓ Se aprendizado: pede chave (Anthropic | OpenAI), valida formato, grava em ~/.claude/o1mem/.env
  ✓ pip install chromadb + sentence-transformers (~470 MB)
  ✓ Pergunta em qual pasta de projeto instalar as skills, copia
    organizador-mem/handover/retomar para <pasta>/.claude/skills/
  ✓ Indexa cada projeto: "N chunks embedados"
  ✓ Registra hook no ~/.claude/settings.json (merge defensivo)
  ✓ Resumo: mostra o caminho exato de cada skill instalada
  ✓ Resumo: npx @tbluhm82/o1mem status
```

Um comando entrega as 3 partes: as **skills** (`.claude/skills/`), o **hook** de nudge
(`settings.json`) e o **índice semântico** (`~/.claude/o1mem/chroma/`). Não sobrescreve
skill já existente na pasta alvo — se já tem uma, mantém e avisa.

## Modos

| Modo | O que faz | Custo |
|---|---|---|
| **local** (padrão) | Busca semântica pura (embeddings locais) | Grátis |
| **aprendizado** | Semântica + destilação: LLM lê top-3 e cura 1 parágrafo por pergunta | Seus tokens |

Modo local é 100% offline, zero credenciais. Modo aprendizado requer API key (Anthropic ou OpenAI) —
adicionado depois via `npx @tbluhm82/o1mem config`.

## Quick Start (via npm, publicado)

```bash
npm install -g @tbluhm82/o1mem
o1mem install
o1mem status
o1mem query "sua pergunta" --project c--Projetos-meu-projeto
```

O comando instalado chama-se `o1mem` (definido em `bin`), independente do nome do pacote no registry.

## Quick Start (a partir do repo, sem npm)

Clone o repo, instale e use:

```bash
git clone https://github.com/thiagobluhm/skills.git
cd skills/installer
npm link
o1mem status
o1mem query "sua pergunta" --project c--Projetos-meu-projeto
```

## Subcomandos

```bash
npx @tbluhm82/o1mem install              # Setup completo
npx @tbluhm82/o1mem status               # Python ok? Mode? Índices? Daemon?
npx @tbluhm82/o1mem index --project MEUPROJ  # Re-indexa um projeto
npx @tbluhm82/o1mem query "topic" -k 5   # Busca
npx @tbluhm82/o1mem query "topic" --distill  # Idem, + destilação via LLM (se chave existe)
npx @tbluhm82/o1mem config               # Trocar mode/chave
npx @tbluhm82/o1mem uninstall            # Remove hook, opcionalmente apaga dados
```

## Estrutura

```
installer/
  cli.js           # entry point (bin o1mem)
  package.json     # name: @tbluhm82/o1mem, bin: cli.js, zero deps
  lib/
    paths.js       # caminhos centralizados
    prompt.js      # readline helpers (input oculto, confirm, multi-select)
    preflight.js   # verifica Python, pip, projetos
    env.js         # escreve .env (chave) + config.json (mode/provider)
    pip.js         # instala chromadb + sentence-transformers
    hooks.js       # merge defensivo em settings.json
    index.js       # dispara primeira indexação
    skills.js      # copia organizador-mem/handover/retomar para .claude/skills/
  skills/          # cópias empacotadas das SKILL.md (fonte: ../<nome>/SKILL.md)
    organizador-mem/SKILL.md
    handover/SKILL.md
    retomar/SKILL.md
  test/
    hooks.test.js   # fixture: merge preserva hooks pré-existentes
    env.test.js     # fixture: chave nunca aparece em log
    skills.test.js  # fixture: copia, não sobrescreve, overwrite opcional
```

> As `skills/` empacotadas aqui são cópias — a fonte de verdade continua sendo
> `../organizador-mem/SKILL.md`, `../handover/SKILL.md`, `../retomar/SKILL.md` na raiz do
> repo. Ao editar uma skill, sincronize a cópia antes de publicar uma nova versão.

## Segurança

- **Chave jamais é logada:** variável nunca entra em `console.*` nem é impressa.
- **Chave só em ~/.claude/o1mem/.env:** nunca em config.json, nunca no repo.
- **POSIX:** `chmod 600` após escrever.
- **Windows:** aviso que é arquivo do perfil do usuário, não compartilhe.
- **Merge defensivo em settings.json:** se JSON está corrompido, aborta sem tocar. Se hook já existe, não duplica.

## Desenvolvendo

```bash
cd skills/installer
node cli.js status              # sem instalar via npm
node cli.js --help
```

Para testar com fixture isolada:
```bash
export O1MEM_TEST_HOME=/tmp/o1mem-test
node cli.js status
```

## Dependências

Zero em production (readline é nativo do Node). Repo Python (rag/) continua sendo o "runtime" —
installer é só o shell de entrada.
