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
const { spawn } = require('child_process');

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

// Verde fósforo, e só quando há terminal: em pipe as sequências ANSI viram lixo
// no arquivo de saída.
const color = process.stdout.isTTY
  ? { bright: '\x1b[92m', green: '\x1b[32m', dim: '\x1b[2;32m', off: '\x1b[0m' }
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

async function runRepl(argv) {
  // Aceita `repl --project <slug>` e `repl <slug>`: o alias `mem` do shell só
  // repassa argumentos, e digitar `mem cge2026` é o que a mão faz sozinha.
  let project = null;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--project' && i + 1 < argv.length) project = argv[++i];
    else if (!argv[i].startsWith('-') && !project) project = argv[i];
  }

  if (!project) {
    project = detectProject(process.cwd());
    if (project) console.log(`📂 Projeto deste diretório: ${project}`);
    else {
      const slugs = paths.listProjects();
      if (!slugs.length) throw new Error('nenhum projeto com memory/ em ~/.claude/projects');
      project = slugs.length === 1 ? slugs[0] : await chooseProject(slugs);
      if (!project) throw new Error('nenhum projeto escolhido');
    }
  }

  let { port, health: h } = await ensureDaemon(project);
  let k = 5;
  let lastHits = [];
  let root = h.root;

  // O padrão é o fluxo (mesmo layout do `o1mem query`): o histórico rola para
  // trás como em qualquer terminal, e não há frame para piscar. A tela cheia
  // navegável continua disponível em `--tui`.
  if (process.stdin.isTTY && argv.includes('--tui')) {
    return require('./tui').start({
      project: () => h.project,
      projects: () => paths.listProjects(),
      query: async (text, n) => {
        const r = await get(
          port,
          `/query?project=${encodeURIComponent(h.project)}&text=${encodeURIComponent(text)}&k=${n}`
        );
        if (r.status !== 200) throw new Error(r.json.error || `HTTP ${r.status}`);
        return r.json;
      },
      open: hit => resolveHitPath(root, hit),
      setProject: async slug => {
        ({ port, health: h } = await ensureDaemon(slug));
        root = h.root;
      }
    });
  }

  const c = color;
  console.log(`\n${c.bright}O(1)mem${c.off} ${c.dim}— daemon na porta ${port}${c.off}`);
  console.log(`${c.dim}projeto : ${h.project}   modelo: ${h.model}${c.off}`);
  console.log(`${c.dim}comandos: :projeto <slug>  :abrir <N>  :k <N>  :sair${c.off}\n`);

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const ask = () => rl.setPrompt(`${c.bright}[${h.project}]${c.off} > `) || rl.prompt();
  ask();

  rl.on('line', async line => {
    // pausa enquanto processa: sem isto, linhas em rajada (pipe, colar várias
    // de uma vez) disparam handlers concorrentes e o output sai atropelado.
    rl.pause();
    const text = line.trim();
    try {
      if (!text) {
        // nada
      } else if (text === ':sair' || text === ':q') {
        rl.close();
        return;
      } else if (text.startsWith(':projeto')) {
        const slug = text.slice(':projeto'.length).trim();
        if (!slug) {
          console.log(`  projeto atual: ${h.project}`);
        } else {
          ({ port, health: h } = await ensureDaemon(slug));
          root = h.root;
          lastHits = [];
          console.log(`  ✅ agora em ${h.project}`);
        }
      } else if (text.startsWith(':k')) {
        const n = parseInt(text.slice(2).trim(), 10);
        if (n > 0) k = n;
        console.log(`  k = ${k}`);
      } else if (text.startsWith(':abrir')) {
        const n = parseInt(text.slice(':abrir'.length).trim(), 10);
        const hit = lastHits[n - 1];
        if (!hit) {
          console.log('  hit inexistente — rode uma busca antes.');
        } else {
          const p = resolveHitPath(root, hit);
          if (!p) console.log(`  arquivo não encontrado: ${hit.source}`);
          else console.log('\n' + fs.readFileSync(p, 'utf8') + `\n  --- ${p}`);
        }
      } else {
        const url = `/query?project=${encodeURIComponent(h.project)}&text=${encodeURIComponent(text)}&k=${k}`;
        const r = await get(port, url);
        if (r.status !== 200) {
          console.log(`  ❌ ${r.json.error || r.status}`);
        } else {
          lastHits = r.json.hits;
          console.log('');
          printResult(r.json);
        }
      }
    } catch (e) {
      console.log(`  ❌ ${e.message}`);
    }
    ask();
  });

  return new Promise(resolve => rl.on('close', () => {
    console.log('\nAté. (o daemon segue vivo e morre sozinho após 30min ocioso)');
    resolve();
  }));
}

module.exports = { runRepl, ensureDaemon, slugMatches, resolveHitPath, detectProject };
