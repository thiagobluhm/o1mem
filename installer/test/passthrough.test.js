/**
 * passthrough.test.js — argv de `o1mem index` / `o1mem query`.
 *
 * O bug: projectArg era montado separado (['--project', slug]). Todo slug
 * POSIX comeca com '-', entao o argparse do Python lia o slug como flag e
 * abortava:
 *
 *   o1mem_rag.py: error: argument --project: expected one argument
 *
 * No Windows o slug comeca com a letra do drive e a forma separada passava,
 * o que escondeu o defeito ate rodar num Mac. A forma colada vale nos dois.
 */
const assert = require('assert');
const { buildPassthroughArgs } = require('../lib/passthrough');

console.log('\n📋 Testando passthrough de index/query\n');

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

const POSIX = '-Users-thiagobluhm-Documents--PESSOAIS-o1mem';
const WIN = 'c--Projetos-O1MEM';

test('slug POSIX vai colado, nunca como valor solto', () => {
  const out = buildPassthroughArgs('/rag.py', 'query', ['texto', '--project', POSIX]);
  assert.ok(out.includes(`--project=${POSIX}`), JSON.stringify(out));
  assert.ok(!out.includes('--project'), 'forma separada reintroduz o bug: ' + JSON.stringify(out));
  assert.ok(!out.includes(POSIX), 'slug solto vira flag pro argparse: ' + JSON.stringify(out));
});

test('slug Windows segue funcionando', () => {
  const out = buildPassthroughArgs('/rag.py', 'query', ['texto', '--project', WIN]);
  assert.deepStrictEqual(out, ['/rag.py', `--project=${WIN}`, 'query', 'texto']);
});

test('--project vem ANTES do subcomando', () => {
  const out = buildPassthroughArgs('/rag.py', 'index', ['--full', '--project', POSIX]);
  assert.ok(out.indexOf(`--project=${POSIX}`) < out.indexOf('index'), JSON.stringify(out));
});

test('flags do usuario sobrevivem, na ordem, depois do subcomando', () => {
  const out = buildPassthroughArgs('/rag.py', 'query', ['assunto', '--project', POSIX, '-k', '5']);
  assert.deepStrictEqual(out, ['/rag.py', `--project=${POSIX}`, 'query', 'assunto', '-k', '5']);
});

test('aceita tambem a forma ja colada que o usuario pode digitar', () => {
  const out = buildPassthroughArgs('/rag.py', 'query', [`--project=${POSIX}`, 'assunto']);
  assert.deepStrictEqual(out, ['/rag.py', `--project=${POSIX}`, 'query', 'assunto']);
});

test('sem --project, nada e inventado', () => {
  assert.deepStrictEqual(buildPassthroughArgs('/rag.py', 'index', ['--full']),
    ['/rag.py', 'index', '--full']);
});

test('--project sem valor no fim nao quebra nem engole o subcomando', () => {
  const out = buildPassthroughArgs('/rag.py', 'query', ['assunto', '--project']);
  assert.ok(out.includes('query'), JSON.stringify(out));
});
