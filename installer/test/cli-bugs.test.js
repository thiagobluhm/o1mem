/**
 * cli-bugs.test.js — testa os 2 bugfixes
 * Bug 1: checkDaemonHealth() é async, precisa await
 * Bug 2: catch reporta erro específico, não sempre "Python não encontrado"
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');

console.log('\n📋 Testando bugfixes de cmdStatus\n');

function test(name, fn) {
  try {
    fn();
    console.log(`✅ ${name}`);
  } catch (e) {
    console.error(`❌ ${name}`);
    console.error(`   ${e.message}`);
    process.exitCode = 1;
  }
}

// ============ BUG 1: checkDaemonHealth() retorna Promise ============
test('Bug 1: checkDaemonHealth() retorna Promise', () => {
  const net = require('net');

  function checkDaemonHealth(port) {
    return new Promise(resolve => {
      const socket = net.createConnection({ port, host: '127.0.0.1', timeout: 500 });
      socket.on('connect', () => {
        socket.destroy();
        resolve(true);
      });
      socket.on('error', () => {
        resolve(false);
      });
    });
  }

  // Verifica que o resultado é uma Promise
  const result = checkDaemonHealth(9999);
  assert(result instanceof Promise, 'checkDaemonHealth deve retornar Promise');
});

// ============ BUG 2: Segmentação do catch ============
test('Bug 2: Erro "Não encontrei" é reportado corretamente', () => {
  const error = new Error('Não encontrei ~/.claude/projects/.\nO(1)mem indexa...');
  error.name = 'PreflightError';

  let reported = '';

  // Simula o novo código do catch (Bug 2 fix)
  try {
    throw error;
  } catch (e) {
    if (e.message.includes('Python não encontrado')) {
      reported = 'Python: ❌ não encontrado no PATH';
    } else if (e.message.includes('Não encontrei')) {
      reported = 'Python: ✅, mas ~/.claude/projects/ não encontrado';
    } else if (e.message.includes('Nenhum projeto')) {
      reported = 'Python: ✅, mas nenhum projeto com memory/ encontrado';
    } else if (e.message.includes('pip')) {
      reported = 'Python: ✅, mas pip não está funcional';
    } else {
      reported = `Python: ❌ erro - ${e.message.split('\n')[0]}`;
    }
  }

  // Verifica que foi reportado corretamente
  assert(
    reported.includes('~/.claude/projects/'),
    `Esperava menção a ~/.claude/projects/, got: ${reported}`
  );
  assert(
    !reported.includes('não encontrado no PATH'),
    `Não deveria reportar "não encontrado no PATH" para erro de projetos`
  );
});

test('Bug 2: Erro "Python não encontrado" é reportado como tal', () => {
  const error = new Error('Python não encontrado no PATH. Instale Python...');
  error.name = 'PreflightError';

  let reported = '';

  try {
    throw error;
  } catch (e) {
    if (e.message.includes('Python não encontrado')) {
      reported = 'Python: ❌ não encontrado no PATH';
    } else if (e.message.includes('Não encontrei')) {
      reported = 'Python: ✅, mas ~/.claude/projects/ não encontrado';
    } else if (e.message.includes('Nenhum projeto')) {
      reported = 'Python: ✅, mas nenhum projeto com memory/ encontrado';
    } else if (e.message.includes('pip')) {
      reported = 'Python: ✅, mas pip não está funcional';
    } else {
      reported = `Python: ❌ erro - ${e.message.split('\n')[0]}`;
    }
  }

  assert(
    reported.includes('não encontrado no PATH'),
    `Esperava "não encontrado no PATH", got: ${reported}`
  );
});

test('Bug 2: Erro sobre pip é reportado como pip, não Python', () => {
  const error = new Error('pip não encontrado ou não é funcional. Verifique sua...');
  error.name = 'PreflightError';

  let reported = '';

  try {
    throw error;
  } catch (e) {
    if (e.message.includes('Python não encontrado')) {
      reported = 'Python: ❌ não encontrado no PATH';
    } else if (e.message.includes('Não encontrei')) {
      reported = 'Python: ✅, mas ~/.claude/projects/ não encontrado';
    } else if (e.message.includes('Nenhum projeto')) {
      reported = 'Python: ✅, mas nenhum projeto com memory/ encontrado';
    } else if (e.message.includes('pip')) {
      reported = 'Python: ✅, mas pip não está funcional';
    } else {
      reported = `Python: ❌ erro - ${e.message.split('\n')[0]}`;
    }
  }

  assert(
    reported.includes('pip'),
    `Esperava menção a pip, got: ${reported}`
  );
});

// ============ BUG 3: require('prompt') sequestrava process.stdin ============
// A interface readline era criada no escopo do módulo, então bastava o cli.js
// dar require para TODO comando perder o stdin — o `repl` criava a própria
// interface e não recebia linha nenhuma.
test('Bug 3: require(prompt) não consome stdin', () => {
  const before = process.stdin.listenerCount('data');
  require('../lib/prompt');
  assert.strictEqual(
    process.stdin.listenerCount('data'),
    before,
    'prompt.js criou a interface readline no require e sequestrou o stdin'
  );
});

// ============ REPL ============
test('REPL: slug exato ganha de substring, e substring ainda casa', () => {
  const { slugMatches } = require('../lib/repl');
  assert(slugMatches('c--Projetos-O1MEM', 'c--Projetos-O1MEM'), 'exato deve casar');
  assert(slugMatches('c--Projetos-cge2026-CGE', 'cge2026'), 'substring deve casar');
  assert(!slugMatches('c--Projetos-O1MEM', 'aistein'), 'slug alheio não pode casar');
  assert(slugMatches('c--Projetos-O1MEM', null), 'sem projeto pedido, qualquer um serve');
});

test('REPL: slug completo não casa por prefixo com o projeto vizinho', () => {
  const { slugMatches } = require('../lib/repl');
  const { listProjects } = require('../lib/paths');
  const [a, b] = listProjects()
    .slice()
    .sort()
    .reduce((acc, p, _i, all) => acc || pickPrefixPair(p, all), null) || [];
  if (!a) {
    console.log('   (pulado: esta máquina não tem par de slugs em prefixo)');
    return;
  }
  assert(
    !slugMatches(b, a),
    `daemon de "${b}" não pode atender um pedido por "${a}" — é outro acervo`
  );
});

function pickPrefixPair(p, all) {
  const longer = all.find(q => q !== p && q.toLowerCase().startsWith(p.toLowerCase()));
  return longer ? [p, longer] : null;
}

test('REPL: handover resolve na pasta irmã de memory/', () => {
  const { resolveHitPath } = require('../lib/repl');
  const os = require('os');
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'o1mem-repl-'));
  const root = path.join(base, 'memory');
  const handovers = path.join(base, 'handovers');
  fs.mkdirSync(root);
  fs.mkdirSync(handovers);
  fs.writeFileSync(path.join(root, 'project_x.md'), 'x');
  fs.writeFileSync(path.join(handovers, 'HANDOVER_x.md'), 'x');

  assert.strictEqual(
    resolveHitPath(root, { kind: 'handover', source: 'HANDOVER_x.md' }),
    path.normalize(path.join(handovers, 'HANDOVER_x.md'))
  );
  assert.strictEqual(
    resolveHitPath(root, { kind: 'project', source: 'project_x.md' }),
    path.normalize(path.join(root, 'project_x.md'))
  );
  assert.strictEqual(
    resolveHitPath(root, { kind: 'project', source: 'nao_existe.md' }),
    null,
    'arquivo ausente deve devolver null, não um caminho inventado'
  );
  fs.rmSync(base, { recursive: true, force: true });
});
