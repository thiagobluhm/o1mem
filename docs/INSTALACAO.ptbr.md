# Instalando o O(1)mem — guia para quem não é técnico

Este guia assume **zero** conhecimento de terminal. Se você só quer o comando, é
`npx @tbluhm82/o1mem install` — o resto do documento explica cada pergunta que ele faz.

Os comandos estão escritos para **Windows / PowerShell**. No macOS e no Linux são
idênticos: muda só abrir o **Terminal** no lugar do PowerShell.

---

## Antes de começar (5 minutos)

O O(1)mem precisa de dois programas instalados no computador. Se você já usa o Claude
Code, provavelmente já tem o primeiro.

**1. Node.js (versão 16 ou maior)**
Baixe em https://nodejs.org — clique no botão que diz **LTS**, instale clicando
"Avançar" em tudo.

**2. Python (versão 3.8 ou maior)**
Baixe em https://python.org/downloads — **atenção:** na primeira tela do instalador,
marque a caixinha **"Add Python to PATH"** antes de clicar em Install. Se esquecer
disso, o O(1)mem não vai encontrar o Python.

**Para conferir se deu certo:** abra o **PowerShell** (tecla Windows → digite
"powershell" → Enter) e digite os dois comandos abaixo, um de cada vez, apertando Enter:

```powershell
node --version
python --version
```

Se aparecer um número em cada (ex: `v20.11.0` e `Python 3.12.1`), está tudo certo. Se
aparecer "não é reconhecido", reinstale o programa correspondente.

---

## Passo 0 — Ter pelo menos uma memória de projeto

O O(1)mem organiza e busca a memória do Claude Code. Ele **não instala** se não houver
nenhuma memória para trabalhar em cima.

Se você já usou o Claude Code em algum projeto e ele já gravou memória, pule este passo.
Se nunca usou: abra o Claude Code na pasta de um projeto seu, converse um pouco e peça
"guarde isso na memória". Isso cria a pasta que o instalador procura
(`~/.claude/projects/<projeto>/memory/`).

> Se no meio da instalação aparecer *"Nenhum projeto com memory/ encontrado"*, foi só
> isso que faltou — volte aqui e depois rode de novo.

---

## Passo 1 — Rodar o instalador

No PowerShell, digite:

```powershell
npx @tbluhm82/o1mem install
```

Se ele perguntar algo como "Ok to proceed? (y)", digite **y** e Enter.

---

## Passo 2 — Responder as 5 perguntas

O instalador conversa com você. Cada resposta é **digitar algo e apertar Enter**.

### Pergunta 1 — Quais projetos indexar?

Ele lista seus projetos numerados a partir do **0**:

```
  0: c--Projetos-meu-projeto
  1: c--Projetos-outro
Sua escolha:
```

Digite os números separados por vírgula (`0,1`). **Se apertar só Enter, ele escolhe
todos** — que é a opção mais simples.

### Pergunta 2 — Modo de busca?

```
  1: local (grátis, sem chave)
  2: aprendizado (com destilação via LLM, requer chave)
```

Digite **1**. O modo local é gratuito, funciona offline e não pede senha nenhuma. Você
pode mudar depois com `npx @tbluhm82/o1mem config`.

### Pergunta 3 — Baixar ~470 MB?

Digite **y**. São os modelos que fazem a busca por significado funcionar. Essa é a parte
demorada: **de 5 a 15 minutos**, dependendo da internet. É normal a tela ficar cuspindo
texto — deixe rodando, não feche.

### Pergunta 4 — Em qual pasta instalar as skills?

Ele sugere a pasta onde você está, entre colchetes. Aperte **Enter** para aceitar, ou
cole o caminho de outra pasta de projeto (ex: `C:\Projetos\meu-projeto`).

> Aqui vão as três habilidades: `handover`, `retomar` e `organizador-mem`. Se já
> existirem nessa pasta, ele **mantém as suas** e avisa — não sobrescreve nada.

### Pergunta 5 — Registrar o hook?

Digite **y**. É o lembrete automático que avisa quando vale a pena fazer um handover.

Ao final aparece **"✅ Instalação concluída!"** com o caminho de cada skill instalada.

---

## Passo 3 — Conferir

```powershell
npx @tbluhm82/o1mem status
```

Deve mostrar Python OK, o modo (`local`) e os projetos indexados.

---

## Passo 4 — Usar

Abra o Claude Code na pasta onde as skills foram instaladas e digite:

- **`/handover`** — quando a conversa ficou longa e você vai dar `/clear` sem perder o fio
- **`/retomar`** — no dia seguinte, para voltar exatamente de onde parou
- **`/organizador-mem`** — quando um arquivo de instruções (CLAUDE.md) ficou grande demais

---

## Se algo der errado

| O que aparece na tela | O que fazer |
|---|---|
| `Python não encontrado no PATH` | Reinstale o Python marcando **"Add Python to PATH"** |
| `Nenhum projeto com memory/ encontrado` | Volte ao Passo 0 |
| `pip não encontrado` | Reinstale o Python (a instalação veio incompleta) |
| Travou no download dos 470 MB | Espere mais; se falhar, rode `npx @tbluhm82/o1mem install` de novo — ele retoma |

**Desfazer tudo:** `npx @tbluhm82/o1mem uninstall`

---

## Referência rápida dos comandos

```powershell
npx @tbluhm82/o1mem install                 # instalação completa
npx @tbluhm82/o1mem status                  # está tudo funcionando?
npx @tbluhm82/o1mem index --project MEUPROJ # re-indexa um projeto
npx @tbluhm82/o1mem query "sua pergunta"    # busca na memória
npx @tbluhm82/o1mem config                  # trocar modo / chave
npx @tbluhm82/o1mem uninstall               # desinstalar
```

Detalhes técnicos do instalador (modos, segurança da chave, estrutura interna) estão em
[installer/README.md](../installer/README.md).
