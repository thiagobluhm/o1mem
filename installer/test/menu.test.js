/**
 * menu.test.js — o menu numerado do terminal.
 *
 * O encadeamento de perguntas só roda em TTY (readline não encadeia `question`
 * sobre pipe), então o que dá para travar em teste é a parte pura: leitura da
 * opção e montagem das listas. É onde moram os erros que doem — opção fora da
 * faixa aceita, "0" confundido com vazio, item numerado fora de ordem.
 */
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

console.log('\n📋 Testando o menu do repl\n');

const cases = [];
function test(name, fn) {
  cases.push([name, fn]);
}

const { parseChoice, projectMenu, actionMenu, listHandovers } = require('../lib/repl');

const plain = s => s.replace(/\x1b\[[0-9;]*m/g, '');

test('parseChoice aceita 0..max e recusa o resto', () => {
  assert.strictEqual(parseChoice('1', 4), 1);
  assert.strictEqual(parseChoice('0', 4), 0, '0 é "sair", não vazio');
  assert.strictEqual(parseChoice('4', 4), 4);
  assert.strictEqual(parseChoice('5', 4), null, 'fora da faixa');
  assert.strictEqual(parseChoice('', 4), null);
  assert.strictEqual(parseChoice('  2  ', 4), 2, 'espaços em volta são do usuário, não erro');
  assert.strictEqual(parseChoice('2a', 4), null);
  assert.strictEqual(parseChoice('-1', 4), null);
  assert.strictEqual(parseChoice(null, 4), null);
});

test('menu de projetos numera de 1 e marca o do diretório atual', () => {
  const slugs = ['proj-a', 'proj-b', 'proj-c'];
  const lines = projectMenu(slugs, 'proj-b').map(plain);
  assert(lines[0].includes('ESCOLHA O PROJETO'));
  assert.strictEqual(lines[1], '  1. proj-a');
  assert.strictEqual(lines[2], '  2. proj-b  (deste diretório)');
  assert.strictEqual(lines[3], '  3. proj-c');
  assert.strictEqual(lines[4], '  0. sair');
});

test('sem projeto detectado, nenhum item vem marcado', () => {
  const lines = projectMenu(['a', 'b'], null).map(plain);
  assert(!lines.join('\n').includes('deste diretório'));
});

test('menu de ações termina em 0 e numera as ações a partir de 1', () => {
  const lines = actionMenu().map(plain);
  assert(lines[0].includes('QUER FAZER O QUE?'));
  assert(lines[1].startsWith('  1. '), `primeira ação mal numerada: ${lines[1]}`);
  assert(lines[lines.length - 1].startsWith('  0. '), 'saída precisa ser a opção 0');
  // toda opção listada tem de ser aceita pelo parser que lê a resposta
  const max = lines.length - 2;
  for (let i = 0; i <= max; i++) {
    assert.strictEqual(parseChoice(String(i), max), i, `opção ${i} listada mas recusada`);
  }
});

test('listHandovers devolve os mais recentes primeiro e ignora não-.md', () => {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'o1mem-menu-'));
  const root = path.join(base, 'memory');
  const hs = path.join(base, 'handovers');
  fs.mkdirSync(root);
  fs.mkdirSync(hs);
  fs.writeFileSync(path.join(hs, 'HANDOVER_velho.md'), 'x');
  fs.writeFileSync(path.join(hs, 'HANDOVER_novo.md'), 'x');
  fs.writeFileSync(path.join(hs, 'nao_e_handover.txt'), 'x');
  const old = new Date(Date.now() - 86400000);
  fs.utimesSync(path.join(hs, 'HANDOVER_velho.md'), old, old);

  const list = listHandovers(root);
  assert.strictEqual(list.length, 2, 'arquivo .txt não deveria entrar');
  assert.strictEqual(list[0].name, 'HANDOVER_novo.md', 'mais recente tem de vir primeiro');
  fs.rmSync(base, { recursive: true, force: true });
});

test('projeto sem pasta de handovers devolve lista vazia, não estoura', () => {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'o1mem-menu2-'));
  const root = path.join(base, 'memory');
  fs.mkdirSync(root);
  assert.deepStrictEqual(listHandovers(root), []);
  fs.rmSync(base, { recursive: true, force: true });
});

(async () => {
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
})();
