/**
 * index-args.test.js — a linha de comando montada para o o1mem_rag.py
 *
 * Dois defeitos reais, ambos silenciosos (indexProject devolvia
 * "JSON inválido" em vez do erro do argparse):
 *
 *  1. ['--project', slug] quebra em POSIX. Todo slug de ~/.claude/projects/
 *     no Mac/Linux comeca com '-' ('-Users-...'), e o argparse le isso como
 *     outra flag: "argument --project: expected one argument". No Windows o
 *     slug comeca com a letra do drive, entao nunca aparecia.
 *  2. '--json' e argumento GLOBAL do parser, nao do subcomando 'index'.
 *     Depois de 'index' vira "unrecognized arguments" -- em qualquer sistema.
 */
const assert = require('assert');
const indexLib = require('../lib/index');

console.log('\n📋 Testando argv da indexação\n');

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

const POSIX_SLUG = '-Users-thiagobluhm-Documents--PESSOAIS-o1mem';
const WIN_SLUG = 'c--Projetos-O1MEM';

test('slug POSIX nao vira flag solta (usa --project=)', () => {
  const args = indexLib.buildIndexArgs('/rag.py', POSIX_SLUG);
  assert.ok(args.includes(`--project=${POSIX_SLUG}`), JSON.stringify(args));
  assert.ok(!args.includes('--project'), 'forma separada reintroduz o bug: ' + JSON.stringify(args));
});

test('slug Windows continua funcionando pela forma colada', () => {
  const args = indexLib.buildIndexArgs('/rag.py', WIN_SLUG);
  assert.ok(args.includes(`--project=${WIN_SLUG}`), JSON.stringify(args));
});

test('--json vem ANTES do subcomando index', () => {
  const args = indexLib.buildIndexArgs('/rag.py', POSIX_SLUG);
  const iJson = args.indexOf('--json');
  const iCmd = args.indexOf('index');
  assert.ok(iJson !== -1 && iCmd !== -1, JSON.stringify(args));
  assert.ok(iJson < iCmd, '--json e global, tem que preceder o subcomando: ' + JSON.stringify(args));
});

test('script do rag e o primeiro argumento', () => {
  assert.strictEqual(indexLib.buildIndexArgs('/caminho/rag.py', POSIX_SLUG)[0], '/caminho/rag.py');
});
