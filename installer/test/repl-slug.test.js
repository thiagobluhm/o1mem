/**
 * repl-slug.test.js — o REPL no POSIX.
 *
 * Dois defeitos, ambos so visiveis fora do Windows:
 *
 * 1. detectProject() montava o slug com `dir.replace(/[\\/:]/g, '-')`. Isso
 *    ignora o '_' (e '.', e espaco) e nao baixa a letra do drive. Num Mac,
 *    /Users/t/_PESSOAIS/o1mem virava '-Users-t-_PESSOAIS-o1mem' e nunca batia
 *    com a pasta real '-Users-t--PESSOAIS-o1mem'. Falha macia: cai no menu,
 *    entao a deteccao automatica pelo cwd simplesmente nunca funcionava.
 *
 * 2. O daemon era chamado com ['--project', slug] separado. Slug POSIX comeca
 *    com '-', o argparse do daemon le como flag e ele MORRE no startup -- o
 *    `repl` nao sobe. Essa e dura, nao macia.
 */
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

console.log('\n📋 Testando slug/daemon do REPL\n');

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

const { slugForPath, buildDaemonArgs } = require('../lib/slug');

// ------------------------------------------------------------ a regra
test('POSIX: caminho com "_" gera o slug real do harness', () => {
  assert.strictEqual(
    slugForPath('/Users/t/_PESSOAIS/o1mem'),
    '-Users-t--PESSOAIS-o1mem'
  );
});

test('POSIX: caminho simples continua igual ao que ja saia', () => {
  assert.strictEqual(slugForPath('/Users/t/dev/app'), '-Users-t-dev-app');
});

test('Windows: letra do drive minuscula, como o harness nomeia a pasta', () => {
  assert.strictEqual(slugForPath('C:\\Projetos\\O1MEM'), 'c--Projetos-O1MEM');
});

test('Windows: "_" no caminho tambem vira "-"', () => {
  assert.strictEqual(slugForPath('C:\\Projetos\\meu_app'), 'c--Projetos-meu-app');
});

// ------------------------------------------- deteccao pelo cwd, ponta a ponta
test('detectProject acha o projeto por um cwd POSIX com "_"', () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'o1mem-test-'));
  const slug = '-Users-t--PESSOAIS-o1mem';
  fs.mkdirSync(path.join(home, '.claude', 'projects', slug, 'memory'), { recursive: true });

  const prev = process.env.O1MEM_TEST_HOME;
  process.env.O1MEM_TEST_HOME = home;
  try {
    // require tardio: paths le o env na chamada, mas o modulo pode ter cache
    delete require.cache[require.resolve('../lib/paths')];
    delete require.cache[require.resolve('../lib/repl')];
    const { detectProject } = require('../lib/repl');
    // um subdiretorio, pra exercitar a subida pelos pais
    assert.strictEqual(detectProject('/Users/t/_PESSOAIS/o1mem/installer/lib'), slug);
  } finally {
    if (prev === undefined) delete process.env.O1MEM_TEST_HOME;
    else process.env.O1MEM_TEST_HOME = prev;
    fs.rmSync(home, { recursive: true, force: true });
  }
});

// ------------------------------------------------------ argv do daemon
test('daemon recebe --project colado (senao morre no argparse)', () => {
  const out = buildDaemonArgs('/daemon.py', '-Users-t--PESSOAIS-o1mem');
  assert.deepStrictEqual(out, ['/daemon.py', '--project=-Users-t--PESSOAIS-o1mem']);
  assert.ok(!out.includes('--project'), 'forma separada mata o daemon no POSIX');
});

test('daemon com slug Windows segue igual', () => {
  assert.deepStrictEqual(
    buildDaemonArgs('/daemon.py', 'c--Projetos-O1MEM'),
    ['/daemon.py', '--project=c--Projetos-O1MEM']
  );
});

test('sem projeto, nenhuma flag e inventada', () => {
  assert.deepStrictEqual(buildDaemonArgs('/daemon.py', null), ['/daemon.py']);
});
