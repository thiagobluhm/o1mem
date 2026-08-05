/**
 * repl.js — terminal de consulta ao acervo do O(1)mem.
 *
 * Existe por medição, não por estética: cada `o1mem query` avulso repaga os ~47s
 * de carga do modelo de embeddings, enquanto a busca em si custa ~0,1s. O daemon
 * (rag/o1mem_rag_daemon.py) já resolvia a parte cara; faltava o que torna a busca
 * usável repetidamente — pagar o modelo uma vez e perguntar à vontade.
 *
 * Zero dependências novas: readline + http da stdlib do Node.
 */
const fs = require('fs');
const path = require('path');
const http = require('http');
const readline = require('readline');
const { spawn, spawnSync } = require('child_process');

const paths = require('./paths');
const { checkPython } = require('./preflight');

const STARTUP_TIMEOUT_MS = 180000; // carga do modelo na 1a subida chega a ~47s

function get(port, urlPath) {
  return new Promise((resolve, reject) => {
    const req = http.get(
      { host: '127.0.0.1', port, path: urlPath, timeout: 60000 },
      res => {
        let body = '';
        res.on('data', c => (body += c));
        res.on('end', () => {
          try {
            resolve({ status: res.statusCode, json: JSON.parse(body) });
          } catch (e) {
            reject(new Error(`resposta inválida do daemon: ${body.slice(0, 200)}`));
          }
        });
      }
    );
    req.on('timeout', () => req.destroy(new Error('timeout')));
    req.on('error', reject);
  });
}

function readDaemonJson() {
  try {
    return JSON.parse(fs.readFileSync(paths.daemonJsonPath(), 'utf8'));
  } catch {
    return null;
  }
}

async function health(port) {
  try {
    const r = await get(port, '/health');
    return r.status === 200 ? r.json : null;
  } catch {
    return null;
  }
}

/** O slug pedido casa o que o daemon serve? Igualdade primeiro, substring depois
 *  — mesma regra do resolve_root em graph/o1mem_graph.py. */
function slugMatches(served, asked) {
  if (!asked) return true;
  const s = (served || '').toLowerCase();
  const a = asked.toLowerCase();
  if (s === a) return true;
  // Um slug completo NUNCA casa por substring com outro: `c--Projetos-O1MEM` é
  // prefixo de `c--Projetos-O1MEM-skills`, e sem esta guarda o REPL reusava
  // silenciosamente o daemon do projeto vizinho — respondendo do acervo errado.
  if (paths.listProjects().some(p => p.toLowerCase() === a)) return false;
  return s.includes(a);
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

/**
 * Descobre o projeto pelo diretório atual: o slug do índice é o caminho com
 * `:` e separadores virando `-`. Sobe pelos pais porque quase nunca se está na
 * raiz — `c:\Projetos\O1MEM\skills\installer` pertence ao projeto de `skills`.
 * Confere contra as pastas que existem de fato; nunca devolve slug deduzido no ar.
 */
function detectProject(cwd) {
  const known = new Set(paths.listProjects());
  let dir = path.resolve(cwd || process.cwd());
  for (;;) {
    const slug = dir.replace(/[\\/:]/g, '-');
    if (known.has(slug)) return slug;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

/** Sem projeto resolvido, listar e deixar escolher — nunca chutar em qual acervo
 *  a pergunta cai. */
function chooseProject(slugs) {
  return new Promise(resolve => {
    console.log('\nNão descobri o projeto por este diretório. Escolha:\n');
    slugs.forEach((s, i) => console.log(`  ${i + 1}. ${s}`));
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question('\nNúmero: ', a => {
      rl.close();
      resolve(slugs[parseInt(a.trim(), 10) - 1] || null);
    });
  });
}

/**
 * Garante um daemon vivo servindo `project`. Reusa o que já está de pé quando o
 * projeto bate; senão derruba e sobe outro (o daemon serve UM projeto, fixado no
 * startup — trocar de projeto custa a carga do modelo de novo).
 */
async function ensureDaemon(project) {
  const info = readDaemonJson();
  if (info && info.port) {
    const h = await health(info.port);
    if (h) {
      if (slugMatches(h.project, project)) return { port: info.port, health: h };
      console.log(`⏳ Daemon serve ${h.project}; reiniciando para ${project}...`);
      try {
        process.kill(info.pid);
      } catch {
        /* já morto */
      }
      for (let i = 0; i < 40 && (await health(info.port)); i++) await sleep(250);
    }
  }

  const { pythonCmd } = checkPython();
  const args = [paths.daemonCliPath()];
  if (project) args.push('--project', project);
  // stderr em pipe, não 'ignore': o daemon morre cedo e com mensagem útil
  // ("'o1mem' e ambiguo", projeto sem índice) — engolir isso vira uma espera
  // de 3 minutos em silêncio para um erro que já era conhecido no segundo 1.
  const child = spawn(pythonCmd, args, { detached: true, stdio: ['ignore', 'ignore', 'pipe'] });
  let stderr = '';
  let died = null;
  child.stderr.on('data', c => (stderr += c));
  child.on('exit', code => {
    if (code !== 0) died = code;
  });

  console.log('⏳ Subindo daemon (carrega o modelo uma vez, ~45s)...');
  const deadline = Date.now() + STARTUP_TIMEOUT_MS;
  while (Date.now() < deadline) {
    await sleep(500);
    const fresh = readDaemonJson();
    if (fresh && fresh.port) {
      const h = await health(fresh.port);
      if (h) {
        child.stderr.destroy();
        child.unref();
        return { port: fresh.port, health: h };
      }
    }
    if (died !== null) {
      throw new Error(
        // o Python já prefixa "ERRO:"; o cli.js prefixa "❌ Erro:" — sem o strip
        // o usuário lê o mesmo prefixo duas vezes
        (stderr.trim().replace(/^ERRO:\s*/, '') || `daemon saiu com código ${died}`) +
          (project ? `\n     (projeto pedido: ${project})` : '')
      );
    }
  }
  throw new Error('daemon não subiu a tempo (veja `o1mem status`)');
}

/** Handover mora na pasta irmã de memory/; memória, na própria. */
function resolveHitPath(root, hit) {
  const candidates =
    hit.kind === 'handover'
      ? [path.join(root, '..', 'handovers', hit.source), path.join(root, hit.source)]
      : [path.join(root, hit.source), path.join(root, '..', 'handovers', hit.source)];
  for (const c of candidates) if (fs.existsSync(c)) return path.normalize(c);
  return null;
}

// Verde só nos ACENTOS, branco no corpo. A primeira versão pintava tudo de
// verde e usava `\x1b[2;32m` (verde atenuado) para metadados, dicas, vizinhos e
// prompts — ou seja, para a maior parte da tela. Sobre fundo translúcido isso
// fica ilegível: o atenuado mistura o verde com o que está atrás da janela.
// Corpo de texto se lê em branco; o verde marca onde olhar.
//
// Só quando há terminal: em pipe as sequências ANSI viram lixo no arquivo.
const color = process.stdout.isTTY
  ? { bright: '\x1b[1;92m', green: '\x1b[97m', dim: '\x1b[38;5;250m', off: '\x1b[0m' }
  : { bright: '', green: '', dim: '', off: '' };

/**
 * Mesmo formato do `o1mem query`: cabeçalho com projeto/modelo/tempos e um
 * bloco por hit. Em fluxo, não em tela cheia — o histórico continua rolando
 * para trás como em qualquer terminal, que é o que se quer de uma busca.
 */
function printResult(r) {
  const c = color;
  console.log(
    `${c.dim}projeto : ${r.project}   modelo: ${r.model}${c.off}\n` +
      `${c.dim}tempos  : ${JSON.stringify(r.timings)}${c.off}\n`
  );
  if (!r.hits.length) {
    console.log('  (nenhum resultado)\n');
    return;
  }
  r.hits.forEach((h, i) => {
    console.log(
      `${c.bright}[${h.score.toFixed(3)}] ${i + 1}. ${h.id || h.source}  (${h.kind})${c.off}`
    );
    console.log(`${c.green}        ${h.excerpt.replace(/\s+/g, ' ').slice(0, 160)}${c.off}`);
    for (const n of h.graph_neighbors || []) {
      console.log(`${c.dim}        ~ ${n.id}${c.off}`);
    }
    console.log('');
  });
}

// ===========================================================================
// Menu. O terminal abre perguntando o projeto e depois o que fazer, em vez de
// um prompt vazio: quem abre o app pelo atalho não vem com um comando na
// cabeça, vem com uma dúvida. Números são o mínimo de digitação possível.
// ===========================================================================

/** Lê uma opção numérica. Devolve null para entrada inválida — quem chama decide
 *  se repete a pergunta ou assume um padrão. */
function parseChoice(input, max) {
  const t = String(input == null ? '' : input).trim();
  if (!/^\d+$/.test(t)) return null;
  const n = parseInt(t, 10);
  return n >= 0 && n <= max ? n : null;
}

/** Monta as linhas do menu de projetos, marcando o do diretório atual. */
function projectMenu(slugs, current) {
  const lines = [`${color.bright}ESCOLHA O PROJETO${color.off}`];
  slugs.forEach((s, i) => {
    const mark = s === current ? `${color.dim}  (deste diretório)${color.off}` : '';
    lines.push(`  ${color.bright}${i + 1}${color.off}. ${s}${mark}`);
  });
  lines.push(`  ${color.bright}0${color.off}. sair`);
  return lines;
}

const ACTIONS = [
  'Buscar no acervo',
  'Ver os handovers mais recentes',
  'Estatísticas do acervo (chunks, data da indexação)',
  'Trocar de projeto'
];

function actionMenu() {
  const lines = [`${color.bright}QUER FAZER O QUE?${color.off}`];
  ACTIONS.forEach((a, i) => lines.push(`  ${color.bright}${i + 1}${color.off}. ${a}`));
  lines.push(`  ${color.bright}0${color.off}. Sair`);
  return lines;
}

/** Handovers do projeto, mais recentes primeiro. */
function listHandovers(root) {
  const dir = path.join(root, '..', 'handovers');
  try {
    return fs
      .readdirSync(dir)
      .filter(f => f.toLowerCase().endsWith('.md'))
      .map(f => ({ name: f, path: path.join(dir, f), mtime: fs.statSync(path.join(dir, f)).mtimeMs }))
      .sort((a, b) => b.mtime - a.mtime);
  } catch {
    return [];
  }
}

async function runRepl(argv) {
  // Aceita `repl --project <slug>` e `repl <slug>`: o alias `mem` do shell só
  // repassa argumentos, e digitar `mem meuprojeto` é o que a mão faz sozinha.
  let project = null;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--project' && i + 1 < argv.length) project = argv[++i];
    else if (!argv[i].startsWith('-') && !project) project = argv[i];
  }

  const slugs = paths.listProjects();
  if (!slugs.length) throw new Error('nenhum projeto com memory/ em ~/.claude/projects');

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const ask = q => new Promise(res => rl.question(q, a => res(a)));
  const c = color;

  console.log(`\n${c.bright}O(1)mem${c.off} ${c.dim}— busca no acervo de memória${c.off}\n`);

  // 1. Projeto. O do diretório atual é só a sugestão do Enter — a escolha é dele.
  if (!project) {
    const detected = detectProject(process.cwd());
    for (;;) {
      console.log(projectMenu(slugs, detected).join('\n'));
      const def = detected ? slugs.indexOf(detected) + 1 : 1;
      const a = await ask(`\n${c.bright}>${c.off} [${def}] `);
      const n = a.trim() === '' ? def : parseChoice(a, slugs.length);
      if (n === null) {
        console.log(`${c.dim}  opção inválida${c.off}\n`);
        continue;
      }
      if (n === 0) {
        rl.close();
        return;
      }
      project = slugs[n - 1];
      break;
    }
  }

  let { port, health: h } = await ensureDaemon(project);
  let root = h.root;
  let k = 8;

  const runQuery = async text => {
    const url = `/query?project=${encodeURIComponent(h.project)}&text=${encodeURIComponent(text)}&k=${k}`;
    const r = await get(port, url);
    if (r.status !== 200) throw new Error(r.json.error || `HTTP ${r.status}`);
    return r.json;
  };

  // A tela cheia navegável continua disponível, agora atrás de --tui.
  if (process.stdin.isTTY && argv.includes('--tui')) {
    rl.close();
    return require('./tui').start({
      project: () => h.project,
      projects: () => slugs,
      query: (text, n) => runQuery(text, n),
      open: hit => resolveHitPath(root, hit),
      setProject: async slug => {
        ({ port, health: h } = await ensureDaemon(slug));
        root = h.root;
      }
    });
  }

  console.log(`\n${c.dim}projeto : ${h.project}   modelo: ${h.model}${c.off}`);

  // 2. Laço do menu de ações.
  for (;;) {
    console.log('\n' + actionMenu().join('\n'));
    const a = await ask(`\n${c.bright}>${c.off} `);
    const n = parseChoice(a, ACTIONS.length);

    if (n === null) {
      console.log(`${c.dim}  opção inválida${c.off}`);
      continue;
    }
    if (n === 0) break;

    try {
      if (n === 1) {
        // Busca: fica no laço até "0", porque uma pergunta puxa a próxima.
        let lastHits = [];
        for (;;) {
          const q = await ask(`\n${c.bright}pergunta${c.off} (0 volta ao menu): `);
          if (q.trim() === '0') break;
          if (!q.trim()) continue;
          const r = await runQuery(q.trim());
          lastHits = r.hits;
          console.log('');
          printResult(r);
          if (lastHits.length) {
            const o = await ask(`${c.dim}abrir qual? (número, ou Enter para nova pergunta)${c.off} `);
            const idx = parseChoice(o, lastHits.length);
            if (idx) {
              const p = resolveHitPath(root, lastHits[idx - 1]);
              if (!p) console.log(`  ${c.dim}arquivo não encontrado${c.off}`);
              else console.log('\n' + fs.readFileSync(p, 'utf8') + `\n${c.dim}  --- ${p}${c.off}`);
            }
          }
        }
      } else if (n === 2) {
        const hs = listHandovers(root);
        if (!hs.length) {
          console.log(`  ${c.dim}nenhum handover neste projeto${c.off}`);
          continue;
        }
        hs.slice(0, 15).forEach((x, i) =>
          console.log(`  ${c.bright}${i + 1}${c.off}. ${x.name} ${c.dim}(${new Date(x.mtime).toISOString().slice(0, 10)})${c.off}`)
        );
        const o = await ask(`\n${c.dim}abrir qual? (Enter volta)${c.off} `);
        const idx = parseChoice(o, Math.min(hs.length, 15));
        if (idx) console.log('\n' + fs.readFileSync(hs[idx - 1].path, 'utf8'));
      } else if (n === 3) {
        const { pythonCmd } = checkPython();
        spawnSync(pythonCmd, [paths.ragCliPath(), '--project', h.project, 'stats'], {
          stdio: 'inherit'
        });
      } else if (n === 4) {
        console.log('');
        console.log(projectMenu(slugs, null).join('\n'));
        const p = await ask(`\n${c.bright}>${c.off} `);
        const idx = parseChoice(p, slugs.length);
        if (idx) {
          ({ port, health: h } = await ensureDaemon(slugs[idx - 1]));
          root = h.root;
          console.log(`  ${c.dim}agora em ${h.project}${c.off}`);
        }
      }
    } catch (e) {
      console.log(`  ❌ ${e.message}`);
    }
  }

  rl.close();
  console.log(`\n${c.dim}Até. (o daemon segue vivo e morre sozinho após 30min ocioso)${c.off}`);
}

module.exports = {
  runRepl,
  ensureDaemon,
  slugMatches,
  resolveHitPath,
  detectProject,
  parseChoice,
  projectMenu,
  actionMenu,
  listHandovers
};
