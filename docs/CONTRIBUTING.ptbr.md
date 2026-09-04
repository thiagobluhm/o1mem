# Contribuindo com o O(1)mem

Obrigado pelo tempo. Este projeto é pequeno, opinativo e testado em trabalho real — as
contribuições são bem-vindas, e cada regra abaixo existe porque um bug correspondente já
foi publicado.

Read this in other languages: [English](../CONTRIBUTING.md)

---

## Quatro regras de base

Não são preferências de estilo. Um PR que quebre uma delas vai receber pedido de mudança.

### 1. Nunca commite dado de memória — este repositório é público

O propósito do O(1)mem é indexar a memória do seu projeto, e essa memória costuma ser
privada. As ferramentas são construídas para que o dado nunca entre no repositório:

- o índice vetorial persiste em `~/.claude/o1mem/chroma/<slug>/`, nunca dentro do worktree;
- `graph/graph.json` é gerado localmente e já está no `.gitignore`, e essa regra
  agora é **executada**, não apenas escrita: ligue o hook do repo uma vez com
  `git config core.hooksPath .githooks` e um commit que carregue artefato
  derivado é recusado. A mesma checagem roda no CI, então `--no-verify` não
  passa;
- o `handover-nudge.log` vive em `~/.claude/`.

O mesmo vale para **screenshots**. Toda imagem em `assets/` precisa ser dado sintético de
exemplo ou estar tarjada. Se um screenshot mostra nomes de nós, arquivos ou identificadores
de cliente reais, ele não entra. Na dúvida, crie um projeto descartável e fotografe aquele.

### 2. O instalador vendoriza cópias próprias — sincronize ou você publica um pacote quebrado

Este é o jeito mais fácil de mandar uma correção para o git e ainda assim deixar todo
usuário do npm quebrado. O pacote publicado (`@tbluhm82/o1mem`) não lê as pastas da raiz;
ele carrega cópias próprias. **Se você mudar um arquivo da esquerda, atualize a cópia da
direita no mesmo commit:**

| Fonte da verdade | Cópia vendorizada dentro do pacote npm |
|---|---|
| `handover/handover.py` | `installer/skills/handover/handover.py` |
| `handover/SKILL.md` | `installer/skills/handover/SKILL.md` |
| `organizador-mem/SKILL.md` | `installer/skills/organizador-mem/SKILL.md` |
| `retomar/SKILL.md` | `installer/skills/retomar/SKILL.md` |
| `rag/o1mem_rag.py`, `o1mem_rag_daemon.py`, `o1mem_distill.py` | `installer/vendor/rag/` |
| `graph/o1mem_graph.py` | `installer/vendor/graph/o1mem_graph.py` |
| `handover-nudge-hook/handover_nudge.py` | `installer/vendor/hook/handover_nudge.py` |

Confira antes de dar push:

```bash
bash tools/check-vendor-sync.sh
```

Ele sai com código diferente de zero e lista cada arquivo que divergiu. A comparação
ignora diferença de CRLF — isso é ruído em checkout no Windows, não divergência.

### 3. Mecânica vai em código, não em prosa

Uma skill é um `SKILL.md` (instruções que o modelo lê) mais, quando aplicável, um `.py` que
faz o trabalho mecânico. A divisa importa: **tudo que precisa acontecer sempre — validação
de caminho, o cap de histórico, decay, exit code, checagem de coerência — vai no Python,
onde é executado.** Instrução em prosa é seguida por aproximação; código é seguido exato.

Na prática: se você quer acrescentar uma regra ao `handover`, acrescente como validação ou
teste em `handover/handover.py`, não como mais um parágrafo no `SKILL.md`. O arquivo da
skill chegou a 182 linhas de correções acumuladas antes desta regra existir; hoje tem ~100,
e as regras que ele perdeu são justamente as que agora são cumpridas.

### 4. Números na documentação são observações, não promessas

Toda porcentagem no README vem de uma sessão medida e está rotulada como tal (`n=1`,
"ordem de grandeza, não promessa"). Se você mudar um número, diga de onde veio a nova
medição. Se acrescentar um, rotule o tamanho da amostra. Não transforme resultado observado
em alegação de marketing — a credibilidade do projeto inteiro depende disso.

---

## Mapa do repositório — onde mexer em quê

| Você quer mudar… | Edite aqui |
|---|---|
| como uma skill se comporta | `handover/`, `organizador-mem/`, `retomar/` (+ a cópia vendorizada) |
| quando o nudge dispara | `handover-nudge-hook/handover_nudge.py` |
| busca semântica / indexação | `rag/o1mem_rag.py` |
| o grafo de wikilinks ou sua UI | `graph/` |
| o painel de economia | `dashboard/` |
| o fluxo de instalação npm | `installer/lib/`, `installer/cli.js` |
| documentação em inglês | `README.md` (canônico) |
| documentação em português | `docs/README.ptbr.md` |

**Não renomeie as pastas das skills.** `handover`, `retomar` e `organizador-mem` são os
nomes que o usuário digita como slash command e os nomes que o instalador escreve em
`.claude/skills/`. São em português, e continuam em português — renomear quebra toda
instalação existente.

---

## Rodando os testes

```bash
# instalador npm (Node >= 16)
cd installer && node --test "test/*.test.js"

# busca semântica — offline, sem rede, sem download de modelo
cd rag && python test_rag_offline.py
cd rag && python test_daemon_offline.py

# smoke da UI do grafo — precisa de um graph.json construído antes
cd graph && python o1mem_graph.py --project <slug> build
cd graph && node test_ui_smoke.js
```

Os testes Python são offline por design: precisam passar numa máquina sem `chromadb`, sem
cache de modelo e sem rede. Se a sua mudança faz um teste exigir rede, a mudança está
errada, não o teste.

As dependências opcionais de runtime (`chromadb`, `sentence-transformers`) são instaladas
só por quem opta pela skill `rag` — nunca as torne obrigatórias para o resto do conjunto.

---

## Pull requests

- **Uma preocupação por PR.** Correção e refatoração no mesmo diff vão receber pedido de
  separação.
- **Conventional commits**: `fix(rag): …`, `feat(graph): …`, `docs: …`. O título diz o que
  mudou; o corpo diz *por quê* — a alternativa descartada costuma ser mais útil que a
  escolhida.
- **Diga o que você verificou.** "Testes passam" serve, se passam. "Deve funcionar" não —
  se você não conseguiu rodar algo, diga qual parte e por quê, em vez de dar a entender que
  foi conferido.
- Se a mudança toca o pacote npm, suba a versão em `installer/package.json`. A publicação é
  feita pelo mantenedor; o bump no PR é o que torna a publicação possível.

---

## Reportando coisas

- **Bug** — use o template de bug report. Inclua seu sistema operacional e as versões de
  Python e Node; um número surpreendente de problemas aqui é encoding de console no Windows
  ou separador de caminho.
- **Seus números de calibragem** — o README pede isso explicitamente, e existe um template
  para eles. Números que **discordam** dos meus valem mais que números que concordam; são
  eles que transformam `n=1` em faixa real.
- **Problema de segurança ou privacidade** (por exemplo, um caminho onde dado de memória
  poderia vazar para dentro de um repo): abra uma issue normal, sem incluir o conteúdo
  sensível em si.

---

## Código de conduta

Seja decente. Presuma boa-fé, critique o trabalho e não a pessoa, e leve discordância para
a substância técnica. Mantenedores podem fechar ou trancar threads que deixem de ser úteis.
