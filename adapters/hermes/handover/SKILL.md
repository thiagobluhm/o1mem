---
name: handover
description: Prepara a saída LIMPA de uma sessão que inchou com uma TAREFA AINDA NÃO CONCLUÍDA, para um /reset sem perder o fio. Escreve UM documento enxuto e SELETIVO em documentacao/ (só o que git+código+memória NÃO contam - porquê das decisões, estado pendente, próximo passo exato, riscos), atualiza o breadcrumb na memória (linha RETOMADA + 1 project_*) e libera o /reset. O handover declara seu MODO DE RETOMADA - "rapida" (próximo passo não toca runtime - decisão, edição, análise; a retomada confia no escrito e fecha com "PRONTO E OPERANTE!") ou "verificada" (próximo passo MEXE NO RUNTIME - gate contra backend de pé, deploy de diff, env flag, store/processo; o handover inclui "Caveat de estado vivo" e a retomada REVERIFICA o runtime ANTES de afirmar ou agir, porque a memória diz o que era verdade quando foi escrita, não o estado presente). Use para qualquer saída de sessão inacabada. NÃO use se a tarefa está concluída e verificada (aí basta memória).
---

Você vai preparar a **saída limpa** de uma sessão: destilar o estado de uma tarefa inacabada em artefatos duráveis para que uma sessão NOVA retome sem reexplicação. Esta skill tem **um fluxo com dois modos de retomada** — a decisão do modo é interna (Passo 0.5) e fica **gravada no próprio handover**, não na sua memória.

## Princípio central: as 3 camadas têm funções diferentes

| Camada | Carrega quando? | Função |
|---|---|---|
| **Resume** | usuário retoma *esta* conversa | continua tudo — mas morre no `/reset` |
| **Memória** (`MEMORY.md` + `memory/*.md`) | **toda** sessão nova, automático | breadcrumb: fatos duráveis + "onde estamos + próximo passo + `[[link]]`" |
| **Handover** (`documentacao/HANDOVER_*.md`) | só quando alguém o **abre** | arquivo: detalhe profundo que não cabe na memória — inclusive o MODO de retomada |

> **A memória é o ÍNDICE; o handover é o ARQUIVO.** A memória garante que a próxima sessão saiba qual handover abrir. Detalhe mora só no handover. Nunca duplique.

### No ecossistema Hermes

O Hermes tem memória persistente nativa (`memory` tool) e busca FTS5 em sessões passadas (`session_search`). O `MEMORY.md` do projeto **complementa** essa memória — ele é o índice que aponta para handovers, não substitui a memória do Hermes. Se o projeto não tiver um `MEMORY.md`, crie um. Se preferir usar a `memory` tool do Hermes como índice, faça o breadcrumb lá — mas o handover sempre é um arquivo em disco (`documentacao/HANDOVER_*.md`), porque a memória do Hermes é compacta por design e não cabe um handover inteiro nela.

## Segundo princípio: nunca afirme runtime pela memória

O handover diz o que era verdade **quando foi escrito**. O processo pode ter sido morto, reiniciado com código velho, o env pode ter mudado. Por isso existe o modo `verificada` — e por isso a promoção de modo na retomada (Passo 4) é sempre permitida, nunca o rebaixamento.

## Passo 0 — TRAVA DE VALOR (não pule)

Handover **só vale a pena** se a tarefa tem pelo menos UM de:
1. **estado pendente que importa** (algo meio-feito, plano não executado);
2. **raciocínio caro de reconstruir** (investigação, hipóteses, trade-off decidido);
3. **plano de vários passos ainda não executado**.

Se a tarefa está **concluída e verificada** e o fato durável cabe na memória → **NÃO escreva handover**. Grave só a memória (via `memory` tool ou `MEMORY.md`) e diga que basta.

## Passo 0.5 — DECIDA O MODO DE RETOMADA

Pergunte: **o próximo passo da retomada toca o runtime?**

- **NÃO toca** (decisão, edição de código/doc, análise, escrita — algo que a próxima sessão faz "do zero"): modo **`rapida`**. A retomada confia no escrito e não verifica nada.
- **TOCA** (rodar gate contra backend de pé, deployar um diff, conferir env flag, estado de store/cache/processo): modo **`verificada`**. O handover DEVE incluir a seção "Caveat de estado vivo" e a retomada a EXECUTA.

**Na dúvida → `verificada`.** Verificar a mais nunca quebrou nada; confiar cego já quebrou.

O modo escolhido vai na **primeira linha do handover** (ver template). É o artefato que carrega o protocolo — a retomada não depende de lembrar qual decisão foi tomada.

## Passo 1 — Escreva o handover (SELETIVO, não dump)

Arquivo: `documentacao/HANDOVER_<slug-da-tarefa>_<YYYYMMDD>.md`.

Crie o diretório `documentacao/` no cwd do projeto se não existir (use `terminal` com `mkdir -p documentacao/`).

**Regra de ouro:** só entra o que **git + código + memória NÃO contam sozinhos**.
- ❌ NÃO liste "arquivos/funções tocados" como corpo — `git diff` já mostra. Aponte `arquivo:linha` só para achar rápido.
- ❌ NÃO cole blocos de código — aponte a localização.
- ✅ Entra o **porquê**, a **decisão + alternativa descartada**, o **que falta**, o **próximo passo exato**, os **riscos/colaterais**.

Use `write_file` para criar o arquivo do handover.

Template:
```markdown
# HANDOVER — <tarefa> (<data>)
> retomada: rapida | verificada

## Onde paramos
1 parágrafo. O estado atual em linguagem de quem vai retomar.

## Próximo passo EXATO
A PRIMEIRA ação concreta da retomada (comando, arquivo, decisão). Sem ambiguidade.

## Decisões + porquê
As escolhas feitas e a RAZÃO (não o quê — o porquê). Inclua a alternativa descartada e por quê.

## Estado pendente
O que falta, com o critério de "pronto". No modo verificada: gates não rodados, deploy não aplicado, validação ao vivo faltando.

## Riscos / colaterais em backlog
Problemas conhecidos NÃO resolvidos (separados da tarefa principal). Severidade.

## Caveat de estado vivo (SÓ no modo verificada — REVERIFICAR antes de afirmar)
O que a retomada PRECISA conferir no runtime antes de agir: backend de pé? qual PID/porta? o patch está no processo rodando (mtime do arquivo vs. start do processo)? env flags no estado esperado? git diff bate? store/cache limpo? Liste itens concretos e checáveis — a retomada vai EXECUTAR isto.

## Refs — arquivo:linha
Pontos de entrada para achar rápido. NÃO é o diff.
```

> **Coerência modo × caveat:** no modo `verificada`, o "Caveat de estado vivo" é **obrigatório** — se você não consegue listar nada checável, o caso é `rapida`. No modo `rapida`, a seção é **omitida** — se você sentiu necessidade de escrevê-la, o caso é `verificada`. A presença/ausência da seção deve sempre bater com a linha `retomada:`.

## Passo 2 — Breadcrumb na memória (o índice)

O índice pode viver em dois lugares no Hermes — escolha conforme o projeto:

### Opção A: `MEMORY.md` no projeto (recomendado para projetos com handovers frequentes)

1. **Atualize a linha `RETOMADA`** no topo do `MEMORY.md`: estado atual + próximo passo + `[[link-da-memoria]]`. Cada linha (a atual e as `(Anterior ...)`) **carrega a data** no rótulo (`YYYY-MM-DDx`) — é o que o decay lê. Ao promover a atual para o histórico entre parênteses, aplique os **dois critérios de saída, que compõem (sai quem violar QUALQUER um):**
   - **CAP** — mantenha no máximo **2** linhas `(Anterior ...)`; dropa a mais antiga além disso. Limita o pior caso (vários handovers no mesmo dia).
   - **IDADE (decay)** — dropa qualquer `(Anterior ...)` com **mais de 30 dias**, mesmo que caiba no cap. Filtra relevância: projeto que dormiu não deve arrastar breadcrumb velho como se fosse fresco.

   O cap é teto O(1); a idade é filtro de relevância — **um complementa o outro**, não substitui. O histórico completo já vive nos `project_*` listados abaixo (cada linha "Anterior" termina em `Ver [project_*]`, que persiste); a linha `RETOMADA` guarda só o pulo atual + os 2 imediatos como ponte, nunca a cadeia inteira. Deixar acumular re-cria o monólito que a memória existe para evitar. **(30 dias é o MESMO limiar reusado no Passo 4 — não invente um segundo número.)**
2. **Crie/atualize 1 arquivo `project_*`** em `memory/` com o fato durável (decisão + estado + próximo label livre), apontando para o handover e linkando `[[nome]]`.
3. Ajuste a linha-índice no `MEMORY.md`.

### Opção B: `memory` tool do Hermes (recomendado para projetos leves)

Use `memory` tool com `target: "memory"` para salvar o breadcrumb como uma entrada compacta:
- Content: `RETOMADA [YYYY-MM-DD]: <estado atual + próximo passo>. Handover: documentacao/HANDOVER_<slug>_<data>.md. Modo: <rapida|verificada>. Ver [project_*].`
- Mantenha o histórico de RETOMADAs anteriores limitado a 2 entradas (mesma regra de cap + decay de 30 dias).
- O fato durável completo pode virar outra entrada `memory` ou um arquivo `memory/project_*.md`.

O breadcrumb é TERSO — aponta, não repete. O modo NÃO precisa ir no breadcrumb: ele está na primeira linha do handover.

> **Invariante ao editar/comprimir o `MEMORY.md` (índice-ponteiro):** densifique a prosa (sintaxe `Gatilho → Ação`, flags `❌🚀✅⚠️`, imperativos curtos), mas **nunca drope um link nem um estado buscável**. Cada `[texto](arquivo.md)` é load-bearing — o protocolo de save consulta o índice por esses links para achar o arquivo que cobre um fato; órfã-lo quebra a memória. Para economizar, encurte o TEXTO do link (`[↗](arquivo.md)`), não o remova. Preserve 100% dos IDs/labels, datas e pendências. (Regra completa de compressão de índice: skill `organizador-mem` → "Compressão de índice-ponteiro".)

## Passo 3 — Libere o /reset

- Diga ao usuário, explicitamente, que está **seguro dar `/reset`** (ou `/new`) e o que foi gravado (handover + memória + modo de retomada).
- Em uma frase, diga qual será a **primeira ação da retomada**.
- Termine com o **Bloco de fechamento padrão** (abaixo) — ele é OBRIGATÓRIO.

## Bloco de fechamento padrão (SEMPRE — Passo 3 e Passo 4)

Todo fechamento desta skill — tanto ao escrever o handover (saída, Passo 3) quanto ao devolver o fio na retomada (Passo 4) — termina com a assinatura seguida, **SEM EXCEÇÃO**, das duas instruções ao usuário. **Você NÃO executa nenhuma das duas** — só as explica:

> PRONTO E OPERANTE!
>
> **Para limpar a sessão:** você digita `/reset` (ou `/new`). Isso zera o contexto desta conversa — mas o handover e a memória já estão salvos em disco, então nada se perde.
> **Para retomar depois:** abra uma sessão NOVA e peça *"retomar o handover"* (ou rode `/skill handover`). A nova sessão lê a linha `RETOMADA` do `MEMORY.md` (ou da memória do Hermes), abre o handover indicado e segue o modo gravado.

Os dois comandos aparecem **sempre**, mesmo que a conversa já tenha falado deles antes — o fechamento é autocontido. (A assinatura é personalizável, ver nota no Passo 4.)

## Passo 4 — (na retomada, sessão nova) O MODO ESTÁ NO ARQUIVO

Quando voltar (usuário pede "retomar", "voltar para o handover"):

1. Leia a linha `RETOMADA` do `MEMORY.md` (use `read_file`) ou busque na memória do Hermes (use `session_search` se não houver `MEMORY.md`). Abra o `documentacao/HANDOVER_*.md` indicado (ou o mais recente — use `search_files` com padrão `HANDOVER_*.md` para encontrar).
   - **Checagem de dormência (decay, mesmo limiar de 30 dias do Passo 2):** se a data da linha `RETOMADA` tiver **mais de 30 dias**, sinalize que o breadcrumb pode estar dormente — reconfira o estado antes de tratá-lo como "atual" (vale para os dois modos; o `git log`/mtime dos arquivos citados diz se algo mudou desde então).
2. Leia o handover inteiro e **cheque a linha `retomada:`** na primeira linha.
3. **REGRA DE PROMOÇÃO (vale sempre, antes de seguir o modo escrito):** se o próximo passo — como está escrito OU como evoluiu desde a escrita — envolve agir sobre runtime, trate como `verificada` **mesmo que o arquivo diga `rapida`**. Promoção é sempre permitida; rebaixamento nunca (se o arquivo diz `verificada`, a retomada verifica, ponto).

> A **assinatura de fechamento** (`PRONTO E OPERANTE!`) é um toque pessoal e um sinal inequívoco de "terminei o protocolo". Personalize à vontade — inclua seu nome, troque a frase — desde que a retomada sempre feche com a MESMA assinatura, para o sinal ser reconhecível.

**Se `rapida` (e a promoção não se aplica):**
- Devolva o fio conciso: onde paramos + próximo passo exato + pendências.
- **NÃO valide estado vivo** — nada de `netstat`, `git diff`, env, restart, gate.
- Feche com o **Bloco de fechamento padrão** (assinatura + os dois comandos: limpar e retomar).

**Se `verificada` (ou promovida):**
- Leia com atenção o "Caveat de estado vivo" e as "Refs — arquivo:linha".
- **EXECUTE o caveat** — reverifique cada item no runtime (use `terminal` para comandos de verificação): backend de pé? porta/PID? o código rodando TEM o patch (mtime vs. start do processo, ou force restart)? env flags certas? `git diff --stat` bate? store/cache no estado assumido?
- **Reporte o estado verificado** com sinais claros (✅ / ⚠️ / ❌) — o que você ENCONTROU, não o que o handover afirmava. Destaque **divergências** ANTES de propor agir.
- Se há divergência que afeta a integridade (ex.: backend sem o patch antes de um gate), **proponha corrigir primeiro** (restart, setar env, aplicar diff) em vez de seguir cego.
- Só então feche com o **Bloco de fechamento padrão** (assinatura + os dois comandos: limpar e retomar).

## Mapeamento de ferramentas (Claude Code → Hermes)

| Claude Code | Hermes equivalente |
|---|---|
| `Write` | `write_file` |
| `Read` | `read_file` |
| `Grep` | `search_files` (target='content') |
| `Glob` | `search_files` (target='files') |
| `AskUserQuestion` | `clarify` |
| `/clear` | `/reset` ou `/new` |
| `~/.claude/skills/` | `~/AppData/Local/hermes/skills/` |
| `CLAUDE.md` | `AGENTS.md` ou `.hermes.md` |
| `~/.claude/` | `~/AppData/Local/hermes/` |
| Transcript JSONL | `session_search` (FTS5 na SQLite do Hermes) |

## Nudge watchdog (o gatilho do ciclo)

No Claude Code original, um hook `UserPromptSubmit` mede o crescimento da conversa a cada turno e sugere `/handover` ao cruzar um limiar (80k tokens). O Hermes não tem hooks `UserPromptSubmit`, então a adaptação usa um **cron job watchdog** — um script Python que roda a cada 10 minutos, lê o `state.db` do Hermes, e quando o limiar é cruzado produz um aviso factual sugerindo `/skill handover`.

- **Script:** `~/AppData/Local/hermes/scripts/hermes_handover_nudge.py`
- **Config:** `~/AppData/Local/hermes/handover-nudge.config.json` (threshold: 80000, step: 70000)
- **Cron job:** criado via `cronjob` tool com `no_agent=True` (padrão watchdog — stdout vazio = silencioso, stdout não-vazio = delivered)
- **Fail-open absoluto:** qualquer erro sai 0 sem imprimir nada

Diferença vs. Claude Code: o cron é assíncrono (a cada 10 min) e não bloqueia a conversa. A compressão automática nativa do Hermes (`compression.enabled: true`, `threshold: 0.50`) funciona como rede de segurança adicional.

Detalhes técnicos do script (queries do state.db, proxy de tokens, estado por sessão): `../nudge-watchdog/README.md`.

## O que esta skill NÃO é

- Não é dump de conversa — é destilação seletiva.
- Não executa `/reset` nem apaga contexto.
- Não substitui a memória — trabalha com ela (índice + arquivo).
- Não roda para tarefa concluída/verificada — aí é só memória.
- Não confia na memória para afirmar runtime — no modo `verificada` (ou promovido), sempre reverifica.
