---
name: handover
description: Prepara a saída LIMPA de uma sessão que inchou com uma TAREFA AINDA NÃO CONCLUÍDA, para um /clear sem perder o fio. O trabalho mecânico (coletar git, validar caminhos, montar o arquivo, aplicar cap/decay na memória, indexar RAG) é feito por handover.py — você só decide o MODO DE RETOMADA e escreve o julgamento. Modo "rapida" = o próximo passo não toca runtime (a retomada confia no escrito e EXECUTA). Modo "verificada" = o próximo passo MEXE NO RUNTIME (a retomada REVERIFICA antes de afirmar, porque a memória diz o que era verdade quando foi escrita, não o estado presente). Use para qualquer saída de sessão inacabada. NÃO use se a tarefa está concluída e verificada — aí basta memória.
---

Você vai destilar uma tarefa inacabada em artefatos duráveis, para que uma sessão NOVA retome sem reexplicação.

> **LEIA ISTO PRIMEIRO.** Esta skill já foi 182 linhas de prosa. O resultado eram handovers de 5 minutos, com desvios inventados no meio do caminho e os mesmos bugs voltando — porque prosa é *advisory*: cada sessão reinterpreta e improvisa. Vinte rodadas de correção adicionaram mais prosa e pioraram tudo. **O mecânico agora é código (`handover.py`), que EXECUTA a regra em vez de interpretá-la.** Sua parte é pequena e é só julgamento. Não reimplemente à mão o que o script faz; não invente etapas que não estão aqui.

## As 3 camadas (por que existe handover, e não só memória)

| Camada | Carrega quando | Função |
|---|---|---|
| Resume | usuário retoma *esta* conversa | continua tudo — morre no `/clear` |
| Memória (`MEMORY.md` + `memory/*.md`) | **toda** sessão nova, automático | ÍNDICE: onde estamos + próximo passo + `[[link]]` |
| Handover (`~/.claude/projects/<slug>/handovers/HANDOVER_*.md`) | só quando alguém **abre** | ARQUIVO: o detalhe que não cabe no índice |

Detalhe mora só no handover. **Nunca duplique.**

> **Onde o handover mora — e por que não é dentro do projeto.** Sempre em `~/.claude/projects/<slug>/handovers/`, ao lado de `memory/`, derivado do **slug** e nunca do CWD. O `handover.py` **trava** isso; você não escolhe o caminho. Antes era `<raiz>/documentacao`, o que fazia o local depender de onde a sessão abriu (um projeto com handovers em `backend/documentacao` ficou com dois lugares e nenhum certo) e punha texto com nome de cliente dentro do repo. Pastas legadas são **lidas** — o `collect` avisa que existem e que estão fora do corpus indexado — e nunca escritas; `python handover.py migrate` as esvazia.

## O fluxo — 5 passos, nesta ordem

### 0. Pergunte o escopo, antes de tocar em qualquer arquivo

`AskUserQuestion`, uma pergunta, três opções mutuamente exclusivas:

- **A — Handover simples**: só grava handover + memória.
- **B — Handover + commit**: grava e roda `git commit` das mudanças pendentes.
- **C — Handover + commit + push**: B, e depois `git push` do remote/branch atual.

A resposta decide o que o Passo 5 faz. Não assuma — cada saída pode ter escopo diferente.

### 1. `TodoWrite` com estas 4 etapas, antes de qualquer outra coisa
Progresso invisível é o defeito nº 1 desta skill. Marque `in_progress`/`completed` **um por vez, em tempo real** — nunca um lote no fim.

### 2. `python <pasta-desta-skill>/handover.py collect`

> O `handover.py` fica **na mesma pasta deste `SKILL.md`** — normalmente `~/.claude/skills/handover/handover.py` (instalação global) ou `<projeto>/.claude/skills/handover/handover.py` (project-local). Rode **de dentro do projeto**: ele descobre a raiz, o slug da memória, o repo git e o `o1mem_rag.py` a partir do seu CWD.

Devolve num bloco só: git (branch/HEAD/tree/remotes em sincronia), caminhos **já validados**, handovers existentes, a `RETOMADA` atual e a contagem de `(Anterior ...)`. Não colete nada disso à mão.

**TRAVA DE VALOR — decida com o que o `collect` mostrou.** Handover só vale se houver pelo menos UM de: (a) estado pendente que importa, (b) raciocínio caro de reconstruir, (c) plano de vários passos não executado. **Tarefa concluída e verificada → NÃO escreva handover.** Grave só a memória e diga que basta. Não "encontre" trabalho para justificar o arquivo.

### 3. Escreva os dois arquivos de julgamento (esta é a SUA parte)

**`body.md`** — só o que git+código+memória **não** contam sozinhos:

```markdown
## Onde paramos
1 parágrafo: o estado atual, na língua de quem vai retomar.

## Próximo passo EXATO
A PRIMEIRA ação concreta. Sem ambiguidade.

## Decisões + porquê
A RAZÃO, não o quê. Inclua a alternativa descartada e por quê.

## Estado pendente
O que falta, com o critério de "pronto".

## Riscos / colaterais em backlog
Problemas conhecidos NÃO resolvidos, com severidade.

## Caveat de estado vivo (REVERIFICAR antes de afirmar)
SÓ no modo verificada. Itens concretos e checáveis que a retomada vai EXECUTAR:
backend de pé? qual PID/porta? o processo rodando TEM o patch (mtime vs. start)?
env flags? `git diff --stat` bate? store/cache no estado assumido?

## Refs — arquivo:linha
Pontos de entrada para achar rápido. NÃO é o diff.
```

❌ Não liste "arquivos tocados" (o `git diff` já mostra) · ❌ não cole código (aponte `arquivo:linha`) · ✅ o porquê, o que falta, o próximo passo, os riscos.

⚠️ **Anti-segredo, sem exceção:** o handover vai pro disco e normalmente pro git. **Nunca** grave credencial, `.env`, chave, token, URL assinada ou dado pessoal. Se o caveat depende de segredo, referencie só o nome da variável (`AWS_SECRET_ACCESS_KEY está setada?`) ou o local (`ver secrets manager`) — nunca o valor.

**`breadcrumb.txt`** — o texto novo da linha `RETOMADA`: estado + próximo passo + `[[link]]`. TERSO: aponta, não repete. O modo **não** vai aqui (está na 1ª linha do handover).

### 4. `python <pasta-desta-skill>/handover.py write --task <slug> --mode rapida|verificada --body body.md --breadcrumb breadcrumb.txt`

O script grava o handover, promove a `RETOMADA` anterior aplicando **cap=2 + decay=30d**, preserva os `[[links]]` e o fim de linha do arquivo, indexa o RAG **checando o exit code de verdade**, e imprime o que fez. Ele também **recusa** modo incoerente: `verificada` exige a seção de caveat, `rapida` a proíbe. Se ele recusar, o modo está errado — não contorne.

Depois: crie/atualize **1** `project_*.md` em `memory/` com o fato durável apontando pro handover, e ajuste a linha-índice do `MEMORY.md`.

> **Invariante do `MEMORY.md`:** densifique a prosa, mas **nunca drope um `[[link]]`** — cada um é load-bearing pro protocolo de save achar o arquivo que cobre um fato. Para economizar, encurte o TEXTO do link (`[↗](x.md)`), não o remova.

## Passo 5 — Execute o escopo do Passo 0, depois libere o /clear

Se a resposta do Passo 0 foi **B** ou **C**: rode `git add` do que mudou (handover, memória, e o trabalho da sessão) e `git commit` com mensagem que descreve a sessão — confira antes que a mensagem não cite dado sensível (ver [[feedback_nao_citar_cliente_em_mensagem_de_commit_publico]]). Se foi **C**: depois do commit, `git push` do remote/branch em uso. Se **A**: nenhum dos dois.

Diga que é **seguro dar `/clear`**, o que foi gravado (e commitado/pushado, se aplicável), e em uma frase qual será a primeira ação da retomada. Termine com:

> PRONTO E OPERANTE THIAGO!
>
> **Para limpar a sessão:** você digita `/clear`. Zera o contexto desta conversa — o handover e a memória já estão em disco, nada se perde.
> **Para retomar depois:** sessão NOVA, peça *"retomar o handover"*. Ela lê a linha `RETOMADA`, abre o handover indicado e segue o modo gravado.

🔴 **Este bloco é EXCLUSIVO da saída.** Emiti-lo ao *retomar* cria o loop que já queimou 5 sessões: `/clear` → retomar → a retomada reapresenta o handover e manda dar `/clear` de novo, sem uma linha de trabalho ter andado. Se você sentir vontade de assinar ao retomar, é sinal de que **não fez nada**.

## Na RETOMADA (sessão nova) — o modo está no arquivo

`TodoWrite` primeiro, aqui também. Leia a linha `RETOMADA`, abra o handover, leia a linha `retomada:`.

- **Decay:** se a data da `RETOMADA` tem mais de 30 dias, o breadcrumb pode estar dormente — reconfira antes de tratar como atual.
- **PROMOÇÃO (sempre permitida; rebaixamento nunca):** se o próximo passo toca runtime — como escrito OU como evoluiu — trate como `verificada` mesmo que o arquivo diga `rapida`.
- **`verificada`:** execute o caveat item por item (paralelize com subagentes Haiku: `Agent`, `model: "haiku"`, `subagent_type: "general-purpose"`, todos no MESMO bloco). Reporte ✅/⚠️/❌ pelo que **encontrou**, não pelo que o handover afirmava; divergência vem ANTES de propor agir, e se ela afeta integridade, corrija primeiro. **A reconciliação é sua, nunca do subagente.**

> **REGRA DE OURO: EXECUTE, não reapresente.** O produto de uma retomada é **trabalho feito**. Faça tudo do próximo passo que não exige o olho ou a mão do usuário (commit, push, rodar a suíte, aplicar o fix já acordado). Só o que é fisicamente dele volta como pedido — **um**, no fim. Perguntar "posso?" sobre algo que o handover já registrou como decidido é o que trava o ciclo. **Nunca** feche uma retomada com o bloco de fechamento nem com convite a `/clear`.

## O que esta skill NÃO é

Não é dump de conversa (é destilação) · não executa `/clear` · não substitui a memória (é índice + arquivo) · não roda para tarefa concluída · não afirma runtime pela memória · **não reimplementa à mão o que `handover.py` faz.**
