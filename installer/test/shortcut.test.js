/**
 * shortcut.test.js — a linha de comando do atalho.
 *
 * Existe por causa de uma falha real: o argumento levava
 * `$host.UI.RawUI.WindowTitle='O(1)mem'; o1mem repl <slug>`, e `;` é separador
 * de comandos DO wt — ele picava a linha e tentava lançar o resto como outro
 * programa, então o duplo clique só cuspia
 * "[error 0x80070002] when launching '\" o1mem repl ...\"'" em loop.
 */
const assert = require('assert');

console.log('\n📋 Testando shortcut.js\n');

const cases = [];
function test(name, fn) {
  cases.push([name, fn]);
}

const { buildArgs } = require('../lib/shortcut');

const PS = 'C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\powershell.exe';

test('linha do wt não contém ";" — o wt o trataria como separador de comando', () => {
  const line = buildArgs({ wt: true, psExe: PS, project: 'c--Projetos-DEMO' });
  assert(!line.includes(';'), `";" reapareceu na linha do wt: ${line}`);
});

test('linha do wt passa o título pelo --title, não por comando de shell', () => {
  const line = buildArgs({ wt: true, psExe: PS, project: 'x' });
  assert(line.includes('--title "O(1)mem"'), 'faltou --title');
  assert(!line.includes('WindowTitle'), 'título voltou a sair por comando de shell');
});

test('-Command do wt vai sem aspas, com os tokens soltos', () => {
  const line = buildArgs({ wt: true, psExe: PS, project: 'c--Projetos-DEMO' });
  assert(
    line.endsWith('-Command o1mem repl c--Projetos-DEMO'),
    `-Command mal formado: ${line}`
  );
});

test('sem wt, o fallback do powershell pode usar ";" (lá ele é do shell)', () => {
  const line = buildArgs({ wt: false, project: 'x' });
  assert(line.includes('-Command "'), 'fallback deveria passar o comando entre aspas');
  assert(line.includes('WindowTitle'), 'fallback é quem precisa setar o título na mão');
});

test('sem projeto, a linha não deixa espaço solto no fim', () => {
  const line = buildArgs({ wt: true, psExe: PS, project: '' });
  assert(line.endsWith('-Command o1mem repl'), `sobrou lixo no fim: "${line}"`);
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
