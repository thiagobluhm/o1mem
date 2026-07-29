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
