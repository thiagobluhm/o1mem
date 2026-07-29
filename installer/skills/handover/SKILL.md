---
name: handover
description: Prepara a saída LIMPA de uma sessão que inchou com uma TAREFA AINDA NÃO CONCLUÍDA, para um /clear sem perder o fio. Escreve UM documento enxuto e SELETIVO em documentacao/ (só o que git+código+memória NÃO contam - porquê das decisões, estado pendente, próximo passo exato, riscos), atualiza o breadcrumb na memória (linha RETOMADA + 1 project_*) e libera o /clear. O handover declara seu MODO DE RETOMADA - "rapida" (próximo passo não toca runtime - decisão, edição, análise; a retomada confia no escrito e EXECUTA o próximo passo) ou "verificada" (próximo passo MEXE NO RUNTIME - gate contra backend de pé, deploy de diff, env flag, store/processo; o handover inclui "Caveat de estado vivo" e a retomada REVERIFICA o runtime ANTES de afirmar ou agir, porque a memória diz o que era verdade quando foi escrita, não o estado presente). Use para qualquer saída de sessão inacabada. NÃO use se a tarefa está concluída e verificada (aí basta memória).
---

Você vai preparar a **saída limpa** de uma sessão: destilar o estado de uma tarefa inacabada em artefatos duráveis para que uma sessão NOVA retome sem reexplicação. Esta skill tem **um fluxo com dois modos de retomada** — a decisão do modo é interna (Passo 0.5) e fica **gravada no próprio handover**, não na sua memória.

## Princípio central: as 3 camadas têm funções diferentes

| Camada | Carrega quando? | Função |
|---|---|---|
| **Resume** | usuário retoma *esta* conversa | continua tudo — mas morre no `/clear` |
| **Memória** (`MEMORY.md` + `memory/*.md`) | **toda** sessão nova, automático | breadcrumb: fatos duráveis + "onde estamos + próximo passo + `[[link]]`" |
| **Handover** (`documentacao/HANDOVER_*.md`) | só quando alguém o **abre** | arquivo: detalhe profundo que não cabe na memória — inclusive o MODO de retomada |

> **A memória é o ÍNDICE; o handover é o ARQUIVO.** A memória garante que a próxima sessão saiba qual handover abrir. Detalhe mora só no handover. Nunca duplique.

## Segundo princípio: nunca afirme runtime pela memória

O handover diz o que era verdade **quando foi escrito**. O processo pode ter sido morto, reiniciado com código velho, o env pode ter mudado. `feedback_verificar_codigo_antes_de_afirmar` e `feedback_teste_atesta_erro_nao_passa` valem aqui. Por isso existe o modo `verificada` — e por isso a promoção de modo na retomada (Passo 4) é sempre permitida, nunca o rebaixamento.

## Terceiro princípio: paralelize o MECÂNICO com subagentes Haiku (não o julgamento)

Escrever e retomar um handover têm, cada um, uma **parte mecânica e independente** (rodar comandos, ler arquivos para achar `arquivo:linha`, coletar evidência de runtime) e uma **parte de julgamento** (decidir o modo, destilar o *porquê*, reconciliar divergências). O mecânico **não precisa do modelo caro**: dispare em paralelo para subagentes **Haiku** (`Agent` com `model: "haiku"`, `subagent_type: "Explore"` para leitura ou `"general-purpose"` para rodar comandos). Uma leva de chamadas `Agent` no MESMO bloco roda concorrente.

| Fica com o AGENTE PRINCIPAL (julgamento — nunca delega) | Vai para subagentes HAIKU (mecânico — paraleliza) |
|---|---|
| Decidir o modo (Passo 0.5) e o valor (Passo 0) | Ler os arquivos citados e devolver os `arquivo:linha` dos refs |
| Destilar decisões, *porquê*, alternativa descartada | **Pré-coletar a evidência do "Caveat de estado vivo"** (git ls-remote, `git diff --stat`, PID/porta, mtime vs. start) |
| Redigir a prosa do handover e o breadcrumb | Regenerar índices derivados (ex.: gerador de índice de handovers) |
| Na retomada: **reconciliar** ✅/⚠️/❌ e decidir agir | Na retomada `verificada`: rodar **cada item do caveat** como uma checagem isolada e devolver o resultado cru |

**Por que Haiku, não o principal:** essas tarefas são "rode isto e me diga o que deu" — sem contexto de sessão. Um Haiku frio as faz bem e barato; gastar o modelo grande nelas é desperdício. **Guarda-corpo:** um subagente **nunca** escreve a prosa do handover, decide o modo, nem reconcilia divergência — ele só **coleta**; quem interpreta é o principal. **Fail-open:** se um subagente falhar/demorar, o principal faz aquele item inline — a paralelização acelera, não é caminho crítico.

## Passo 0 — TRAVA DE VALOR (não pule)

Handover **só vale a pena** se a tarefa tem pelo menos UM de:
1. **estado pendente que importa** (algo meio-feito, plano não executado);
2. **raciocínio caro de reconstruir** (investigação, hipóteses, trade-off decidido);
3. **plano de vários passos ainda não executado**.

Se a tarefa está **concluída e verificada** e o fato durável cabe na memória → **NÃO escreva handover**. Grave só a memória e diga que basta.

## Passo 0.5 — DECIDA O MODO DE RETOMADA

Pergunte: **o próximo passo da retomada toca o runtime?**

- **NÃO toca** (decisão, edição de código/doc, análise, escrita — algo que a próxima sessão faz "do zero"): modo **`rapida`**. A retomada confia no escrito e não verifica nada.
- **TOCA** (rodar gate contra backend de pé, deployar um diff, conferir env flag, estado de store/cache/processo): modo **`verificada`**. O handover DEVE incluir a seção "Caveat de estado vivo" e a retomada a EXECUTA.

**Na dúvida → `verificada`.** Verificar a mais nunca quebrou nada; confiar cego já quebrou.

O modo escolhido vai na **primeira linha do handover** (ver template). É o artefato que carrega o protocolo — a retomada não depende de lembrar qual decisão foi tomada.

## Passo 1 — Escreva o handover (SELETIVO, não dump)

Arquivo: `documentacao/HANDOVER_<slug-da-tarefa>_<YYYYMMDD>.md`.

> **Acelere (3º princípio):** ANTES de redigir, dispare em paralelo os subagentes Haiku que coletam o mecânico — os `arquivo:linha` dos refs e, no modo `verificada`, a evidência do "Caveat de estado vivo". Você redige enquanto eles rodam e cola o que voltou.

**Regra de ouro:** só entra o que **git + código + memória NÃO contam sozinhos**.
- ❌ NÃO liste "arquivos/funções tocados" como corpo — `git diff` já mostra. Aponte `arquivo:linha` só para achar rápido.
- ❌ NÃO cole blocos de código — aponte a localização.
- ✅ Entra o **porquê**, a **decisão + alternativa descartada**, o **que falta**, o **próximo passo exato**, os **riscos/colaterais**.

> ⚠️ **Regra anti-segredo (obrigatória, sem exceção):** o handover é um arquivo em disco, tipicamente versionado — **nunca** persiste segredo, credencial, conteúdo de `.env`, chave de API, token, URL assinada (presigned) ou payload de dado pessoal/sensível. Se o "Caveat de estado vivo" depende de uma credencial, referencie **só o nome seguro da variável** (`AWS_SECRET_ACCESS_KEY está setada?`) ou o local protegido (`ver .env`, `ver secrets manager`) — nunca o valor. Se um comando de coleta (inclusive de subagente) devolver algo que pareça segredo, **não copie para o handover** — resuma o fato ("credencial X confirmada válida") e descarte o valor. Vale também para `documentacao/` fora de handovers: se o repositório não tem `.gitignore` para material privado, avise o usuário antes de escrever.

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

1. **Atualize a linha `RETOMADA`** no topo do `MEMORY.md`: estado atual + próximo passo + `[[link-da-memoria]]`. Cada linha (a atual e as `(Anterior ...)`) **carrega a data** no rótulo (`YYYY-MM-DDx`) — é o que o decay lê. Ao promover a atual para o histórico entre parênteses, aplique os **dois critérios de saída, que compõem (sai quem violar QUALQUER um):**
   - **CAP** — mantenha no máximo **2** linhas `(Anterior ...)`; dropa a mais antiga além disso. Limita o pior caso (vários handovers no mesmo dia).
   - **IDADE (decay)** — dropa qualquer `(Anterior ...)` com **mais de 30 dias**, mesmo que caiba no cap. Filtra relevância: projeto que dormiu não deve arrastar breadcrumb velho como se fosse fresco.

   O cap é teto O(1); a idade é filtro de relevância — **um complementa o outro**, não substitui. O histórico completo já vive nos `project_*` listados abaixo (cada linha "Anterior" termina em `Ver [project_*]`, que persiste); a linha `RETOMADA` guarda só o pulo atual + os 2 imediatos como ponte, nunca a cadeia inteira. Deixar acumular re-cria o monólito que a memória existe para evitar. **(30 dias é o MESMO limiar reusado no Passo 4 — não invente um segundo número.)**
2. **Crie/atualize 1 arquivo `project_*`** em `memory/` com o fato durável (decisão + estado + próximo label livre), apontando para o handover e linkando `[[nome]]`.
3. Ajuste a linha-índice no `MEMORY.md`.

O breadcrumb é TERSO — aponta, não repete. O modo NÃO precisa ir no breadcrumb: ele está na primeira linha do handover.

> **Invariante ao editar/comprimir o `MEMORY.md` (índice-ponteiro):** densifique a prosa (sintaxe `Gatilho → Ação`, flags `❌🚀✅⚠️`, imperativos curtos), mas **nunca drope um link nem um estado buscável**. Cada `[texto](arquivo.md)` é load-bearing — o protocolo de save consulta o índice por esses links para achar o arquivo que cobre um fato; órfã-lo quebra a memória. Para economizar, encurte o TEXTO do link (`[↗](arquivo.md)`), não o remova. Preserve 100% dos IDs/labels, datas e pendências. (Regra completa de compressão de índice: skill `organizador-mem` → "Compressão de índice-ponteiro".)

## Passo 3 — Libere o /clear

- Diga ao usuário, explicitamente, que está **seguro dar `/clear`** e o que foi gravado (handover + memória + modo de retomada).
- Em uma frase, diga qual será a **primeira ação da retomada**.
- Termine com o **Bloco de fechamento padrão** (abaixo) — ele é OBRIGATÓRIO.

## Bloco de fechamento padrão (SÓ na SAÍDA — Passo 3. NUNCA na retomada)

> 🔴 **O LOOP QUE ESTE AVISO EXISTE PARA MATAR.** Este bloco pertence **exclusivamente** à *saída* de sessão. Emiti-lo no fim de uma **retomada** cria um ciclo que já queimou 5 sessões seguidas: o usuário dá `/clear` → pede retomar → a retomada reapresenta o handover, verifica o runtime e **manda dar `/clear` de novo** — sem uma linha de trabalho ter andado. Retomar **não** é reapresentar o handover; é **continuar de onde parou**. Na retomada (Passo 4) o fechamento é o **trabalho executado**, não um convite a limpar a sessão. Se você sentir vontade de assinar a frase de fechamento ao retomar, é sinal de que **não fez nada** — volte e execute o próximo passo.

Ao escrever o handover (saída, Passo 3), o fechamento termina com a assinatura seguida, **SEM EXCEÇÃO**, das duas instruções ao usuário. **Você NÃO executa nenhuma das duas** — só as explica:

> PRONTO E OPERANTE!
>
> **Para limpar a sessão:** você digita `/clear`. Isso zera o contexto desta conversa — mas o handover e a memória já estão salvos em disco, então nada se perde.
> **Para retomar depois:** abra uma sessão NOVA e peça *"retomar o handover"* (ou rode `/handover`). A nova sessão lê a linha `RETOMADA` do `MEMORY.md`, abre o handover indicado e segue o modo gravado.

Os dois comandos aparecem **sempre** na SAÍDA, mesmo que a conversa já tenha falado deles antes — o fechamento é autocontido. **Na retomada, nenhum dos dois aparece.** (A assinatura é personalizável, ver nota no Passo 4.)

## Passo 4 — (na retomada, sessão nova) O MODO ESTÁ NO ARQUIVO

Quando voltar (usuário pede "retomar", "voltar para o handover"):

1. Leia a linha `RETOMADA` do `MEMORY.md` e abra o `documentacao/HANDOVER_*.md` indicado (ou o mais recente).
   - **Checagem de dormência (decay, mesmo limiar de 30 dias do Passo 2):** se a data da linha `RETOMADA` tiver **mais de 30 dias**, sinalize que o breadcrumb pode estar dormente — reconfira o estado antes de tratá-lo como "atual" (vale para os dois modos; o `git log`/mtime dos arquivos citados diz se algo mudou desde então).
2. Leia o handover inteiro e **cheque a linha `retomada:`** na primeira linha.
3. **REGRA DE PROMOÇÃO (vale sempre, antes de seguir o modo escrito):** se o próximo passo — como está escrito OU como evoluiu desde a escrita — envolve agir sobre runtime, trate como `verificada` **mesmo que o arquivo diga `rapida`**. Promoção é sempre permitida; rebaixamento nunca (se o arquivo diz `verificada`, a retomada verifica, ponto).

> A **assinatura de fechamento** (`PRONTO E OPERANTE!`) é um toque pessoal e um sinal inequívoco de "terminei o protocolo" — **na saída**. Personalize à vontade (inclua seu nome, troque a frase), desde que toda SAÍDA feche com a MESMA assinatura, para o sinal ser reconhecível.

> **REGRA DE OURO DA RETOMADA — EXECUTE, não reapresente.** O produto de uma retomada é **trabalho feito**, não um resumo bonito do handover com uma pergunta no fim. Antes de devolver a palavra, faça **tudo do próximo passo que não exige o olho/a mão do usuário** (commit, push, rodar suíte, ler a biblioteca que decide a dúvida, aplicar o fix óbvio já acordado). Só o que é fisicamente dele — clicar na janela, olhar a tela, rotacionar uma chave — volta como pedido, e **um** pedido, no fim. Perguntar "posso?" sobre algo que o handover já registrou como decidido é o que trava o ciclo.
>
> **Nunca** feche uma retomada com o Bloco de fechamento padrão nem com qualquer convite a `/clear` — ver o aviso vermelho naquela seção.

**Se `rapida` (e a promoção não se aplica):**
- Devolva o fio conciso: onde paramos + próximo passo exato + pendências.
- **NÃO valide estado vivo** — nada de `netstat`, `git diff`, env, restart, gate.
- **Execute** o que couber do próximo passo e feche relatando o que ANDOU (sem assinatura, sem `/clear`).

**Se `verificada` (ou promovida):**
- Leia com atenção o "Caveat de estado vivo" e as "Refs — arquivo:linha".
- **EXECUTE o caveat — em paralelo (3º princípio):** dispare cada item como um subagente Haiku isolado no mesmo bloco (ou uma leva de comandos concorrentes) e colete o cru; reverifique cada item no runtime: backend de pé? porta/PID? o código rodando TEM o patch (mtime vs. start do processo, ou force restart)? env flags certas? `git diff --stat` bate? store/cache no estado assumido? **A reconciliação ✅/⚠️/❌ é sua, não do subagente.**
- **Reporte o estado verificado** com sinais claros (✅ / ⚠️ / ❌) — o que você ENCONTROU, não o que o handover afirmava. Destaque **divergências** ANTES de propor agir.
- Se há divergência que afeta a integridade (ex.: backend sem o patch antes de um gate), **corrija primeiro** (restart, setar env, aplicar diff) em vez de seguir cego — e então siga.
- **Execute o próximo passo** até o limite do que não exige a mão dele; feche relatando o que ANDOU e o que sobrou **para ele** (sem assinatura, sem `/clear`).

## O que esta skill NÃO é

- Não é dump de conversa — é destilação seletiva.
- Não executa `/clear` nem apaga contexto.
- Não substitui a memória — trabalha com ela (índice + arquivo).
- Não roda para tarefa concluída/verificada — aí é só memória.
- Não confia na memória para afirmar runtime — no modo `verificada` (ou promovido), sempre reverifica.
