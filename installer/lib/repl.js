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
  return s === a || s.includes(a);
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
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

function printHits(hits) {
  if (!hits.length) {
    console.log('  (nenhum hit)');
    return;
  }
  hits.forEach((h, i) => {
    console.log(`\n  ${i + 1}. [${h.score.toFixed(3)}] (${h.kind}) ${h.source}`);
    console.log('     ' + h.excerpt.replace(/\s+/g, ' ').slice(0, 220));
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

  let { port, health: h } = await ensureDaemon(project);
  let k = 5;
  let lastHits = [];
  let root = h.root;

  console.log(`\n✅ Daemon vivo (porta ${port}) — projeto ${h.project}`);
  console.log('   :projeto <slug>  :abrir <N>  :k <N>  :sair\n');

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const ask = () => rl.setPrompt(`[${h.project}] > `) || rl.prompt();
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
          printHits(lastHits);
          const t = r.json.timings || {};
          console.log(`\n  (${t.embed_s || 0}s embed · ${t.search_s || 0}s busca)`);
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

module.exports = { runRepl, ensureDaemon, slugMatches, resolveHitPath };
