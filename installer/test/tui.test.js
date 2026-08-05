/**
 * tui.test.js — exercita a tela sem TTY real.
 *
 * Troca process.stdin/stdout por dublês, dispara keypress na mão e inspeciona o
 * texto desenhado. Sem isto a TUI só seria testável com o olho, e regressão de
 * navegação (seta que anda 2, preview do item errado) passaria batido.
 */
const assert = require('assert');
const { EventEmitter } = require('events');

console.log('\n📋 Testando tui.js\n');

// Sequencial de propósito: cada caso troca process.stdout por um dublê, então
// dois casos em voo ao mesmo tempo escrevem no buffer um do outro.
const cases = [];
function test(name, fn) {
  cases.push([name, fn]);
}

async function run() {
  for (const [name, fn] of cases) {
    try {
      await fn();
      console.log(`✅ ${name}`);
    } catch (e) {
      console.error(`❌ ${name}`);
      console.error(`   ${e.message}`);
      process.exitCode = 1;
    }
  }
}

/** Monta a TUI com stdin/stdout dublês e devolve o que foi desenhado. */
function harness(hits) {
  const realIn = process.stdin;
  const realOut = process.stdout;

  const stdin = new EventEmitter();
  stdin.isTTY = true;
  stdin.setRawMode = () => {};
  stdin.resume = () => {};
  stdin.pause = () => {};

  let buf = '';
  const stdout = new EventEmitter();
  stdout.columns = 100;
  stdout.rows = 24;
  stdout.write = s => (buf += s);

  Object.defineProperty(process, 'stdin', { value: stdin, configurable: true });
  Object.defineProperty(process, 'stdout', { value: stdout, configurable: true });

  const tui = require('../lib/tui');
  const opened = [];
  const done = tui.start({
    project: () => 'c--Projetos-DEMO',
    projects: () => ['c--Projetos-DEMO'],
    query: async () => ({ hits, timings: { embed_s: 0.05, search_s: 0.01 } }),
    open: hit => {
      opened.push(hit.source);
      return null; // força o caminho "arquivo não encontrado", sem tocar disco
    },
    setProject: async () => {}
  });

  return {
    done,
    opened,
    key: (str, key) => stdin.emit('keypress', str, key || { name: str }),
    screen: () => buf,
    flush: () => (buf = ''),
    restore: () => {
      Object.defineProperty(process, 'stdin', { value: realIn, configurable: true });
      Object.defineProperty(process, 'stdout', { value: realOut, configurable: true });
    }
  };
}

const HITS = [
  { score: 0.9, source: 'project_alpha.md', kind: 'project', excerpt: 'conteudo alpha' },
  { score: 0.8, source: 'HANDOVER_beta.md', kind: 'handover', excerpt: 'conteudo beta' },
  { score: 0.7, source: 'feedback_gama.md', kind: 'feedback', excerpt: 'conteudo gama' }
];

test('desenha header com o projeto e a ajuda de rodapé', () => {
  const h = harness(HITS);
  try {
    const s = h.screen();
    assert(s.includes('O(1)mem'), 'faltou o título');
    assert(s.includes('c--Projetos-DEMO'), 'faltou o projeto no header');
    assert(s.includes('busca'), 'faltou a ajuda de rodapé');
  } finally {
    h.restore();
  }
});

test('digitar + Enter busca e lista os hits', async () => {
  const h = harness(HITS);
  try {
    'oi'.split('').forEach(c => h.key(c, { name: c }));
    assert(h.screen().includes('oi'), 'texto digitado não apareceu');
    h.key(null, { name: 'return' });
    await new Promise(r => setImmediate(r));
    await new Promise(r => setImmediate(r));
    const s = h.screen();
    assert(s.includes('project_alpha.md'), 'hit 1 não listado');
    assert(s.includes('HANDOVER_beta.md'), 'hit 2 não listado');
    assert(s.includes('3 resultados'), 'status não reportou a contagem');
  } finally {
    h.restore();
  }
});

test('seta para baixo move a seleção de um em um e Enter abre o selecionado', async () => {
  const h = harness(HITS);
  try {
    h.key('x', { name: 'x' });
    h.key(null, { name: 'return' });
    await new Promise(r => setImmediate(r));
    await new Promise(r => setImmediate(r));

    h.key(null, { name: 'down' });
    h.key(null, { name: 'return' });
    assert.deepStrictEqual(h.opened, ['HANDOVER_beta.md'], 'uma seta deve mover exatamente um item');

    h.key(null, { name: 'down' });
    h.key(null, { name: 'return' });
    assert.deepStrictEqual(h.opened, ['HANDOVER_beta.md', 'feedback_gama.md']);

    // não passa do fim da lista
    h.key(null, { name: 'down' });
    h.key(null, { name: 'down' });
    h.key(null, { name: 'return' });
    assert.strictEqual(h.opened[h.opened.length - 1], 'feedback_gama.md', 'seleção passou do fim');
  } finally {
    h.restore();
  }
});

test('q na lista encerra e restaura o cursor', async () => {
  const h = harness(HITS);
  try {
    h.key('x', { name: 'x' });
    h.key(null, { name: 'return' });
    await new Promise(r => setImmediate(r));
    await new Promise(r => setImmediate(r));

    h.flush();
    h.key('q', { name: 'q' });
    await h.done;
    assert(h.screen().includes('\x1b[?25h'), 'saiu sem reexibir o cursor');
  } finally {
    h.restore();
  }
});

run();
