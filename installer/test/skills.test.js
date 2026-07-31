/**
 * skills.test.js — copia das SKILL.md empacotadas para .claude/skills/
 * Rodável via: node test/skills.test.js
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const os = require('os');

const { installSkills, bundledSkillNames } = require('../lib/skills');

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

test('bundledSkillNames() acha as 3 skills empacotadas', () => {
  const names = bundledSkillNames();
  assert(names.includes('organizador-mem'));
  assert(names.includes('handover'));
  assert(names.includes('retomar'));
});

test('installSkills() copia SKILL.md pra .claude/skills/<nome>/', () => {
  const targetDir = path.join(os.tmpdir(), 'o1mem-skills-test-' + Date.now());
  fs.mkdirSync(targetDir, { recursive: true });

  const results = installSkills(targetDir);

  assert.strictEqual(results.length, 3);
  for (const r of results) {
    assert.strictEqual(r.status, 'installed');
    assert(fs.existsSync(r.path));
    const content = fs.readFileSync(r.path, 'utf8');
    assert(content.includes('name:'));
  }

  fs.rmSync(targetDir, { recursive: true, force: true });
});

// O bug que este teste tranca: enquanto installSkills copiava só o SKILL.md, o
// pacote instalava a skill `handover` apontando para um handover.py que não
// existia na máquina do usuário. Parecia instalada e quebrava no primeiro uso.
test('installSkills() copia os arquivos IRMAOS da skill (handover.py)', () => {
  const targetDir = path.join(os.tmpdir(), 'o1mem-skills-test-' + Date.now());
  fs.mkdirSync(targetDir, { recursive: true });

  const results = installSkills(targetDir);
  const h = results.find(r => r.name === 'handover');
  assert(h, 'skill handover deveria ter sido instalada');

  const script = path.join(path.dirname(h.path), 'handover.py');
  assert(fs.existsSync(script), 'handover.py deveria ter sido copiado junto');
  const src = fs.readFileSync(script, 'utf8');
  assert(src.includes('def cmd_collect') && src.includes('def cmd_write'),
         'handover.py copiado deveria ter collect e write');

  // e o SKILL.md tem que apontar pro script que de fato foi instalado
  const md = fs.readFileSync(h.path, 'utf8');
  assert(md.includes('handover.py'), 'SKILL.md deveria referenciar handover.py');

  fs.rmSync(targetDir, { recursive: true, force: true });
});

// UPGRADE: quem instalou uma versao que so trazia o SKILL.md caia em
// 'skipped_exists' e o handover.py nunca aterrissava -- o upgrade nao fazia
// nada e a skill seguia quebrada. Agora completa o que falta, sem clobber.
test('installSkills() completa arquivos faltando num install ANTIGO (upgrade)', () => {
  const targetDir = path.join(os.tmpdir(), 'o1mem-skills-test-' + Date.now());
  const hDir = path.join(targetDir, '.claude', 'skills', 'handover');
  fs.mkdirSync(hDir, { recursive: true });
  // simula 0.1.5: SO o SKILL.md, com conteudo antigo customizavel
  fs.writeFileSync(path.join(hDir, 'SKILL.md'), '---\nname: handover\n---\nVERSAO ANTIGA\n');

  const r = installSkills(targetDir).find(x => x.name === 'handover');

  assert.strictEqual(r.status, 'completed_missing', 'deveria completar, nao pular');
  assert(r.files.includes('handover.py'), 'handover.py deveria estar entre os adicionados');
  assert(fs.existsSync(path.join(hDir, 'handover.py')), 'handover.py deveria existir no disco');
  // e o SKILL.md do usuario NAO pode ter sido tocado
  assert(fs.readFileSync(path.join(hDir, 'SKILL.md'), 'utf8').includes('VERSAO ANTIGA'),
         'SKILL.md existente nao deveria ser sobrescrito sem overwrite');

  fs.rmSync(targetDir, { recursive: true, force: true });
});

test('installSkills() não sobrescreve por padrão (status skipped_exists)', () => {
  const targetDir = path.join(os.tmpdir(), 'o1mem-skills-test-' + Date.now());
  fs.mkdirSync(targetDir, { recursive: true });

  installSkills(targetDir);
  const secondRun = installSkills(targetDir);

  assert(secondRun.every(r => r.status === 'skipped_exists'));

  fs.rmSync(targetDir, { recursive: true, force: true });
});

test('installSkills() com overwrite:true sobrescreve', () => {
  const targetDir = path.join(os.tmpdir(), 'o1mem-skills-test-' + Date.now());
  fs.mkdirSync(targetDir, { recursive: true });

  installSkills(targetDir);
  const secondRun = installSkills(targetDir, { overwrite: true });

  assert(secondRun.every(r => r.status === 'installed'));

  fs.rmSync(targetDir, { recursive: true, force: true });
});

console.log('\n📋 Testando skills.js\n');
