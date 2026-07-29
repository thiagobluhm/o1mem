/**
 * skills.js — copia as SKILL.md empacotadas para .claude/skills/ do projeto alvo
 */
const fs = require('fs');
const path = require('path');

const BUNDLED_SKILLS_DIR = path.join(__dirname, '..', 'skills');
const SKILL_NAMES = ['organizador-mem', 'handover', 'retomar'];

function bundledSkillNames() {
  return SKILL_NAMES.filter(name =>
    fs.existsSync(path.join(BUNDLED_SKILLS_DIR, name, 'SKILL.md'))
  );
}

/**
 * Copia cada skill empacotada para <targetDir>/.claude/skills/<nome>/SKILL.md.
 * Não sobrescreve por padrão — se já existir, pula e reporta 'skipped'.
 */
function installSkills(targetDir, { overwrite = false } = {}) {
  const destRoot = path.join(targetDir, '.claude', 'skills');
  const results = [];

  for (const name of bundledSkillNames()) {
    const srcFile = path.join(BUNDLED_SKILLS_DIR, name, 'SKILL.md');
    const destDir = path.join(destRoot, name);
    const destFile = path.join(destDir, 'SKILL.md');

    if (fs.existsSync(destFile) && !overwrite) {
      results.push({ name, path: destFile, status: 'skipped_exists' });
      continue;
    }

    fs.mkdirSync(destDir, { recursive: true });
    fs.copyFileSync(srcFile, destFile);
    results.push({ name, path: destFile, status: 'installed' });
  }

  return results;
}

module.exports = { installSkills, bundledSkillNames, BUNDLED_SKILLS_DIR };
