/**
 * skills.js — copia as SKILL.md empacotadas para .claude/skills/ do projeto alvo
 */
const fs = require('fs');
const path = require('path');

const BUNDLED_SKILLS_DIR = path.join(__dirname, '..', 'skills');
const SKILL_NAMES = ['organizador-mem', 'handover', 'retomar', 'lembrar'];

function bundledSkillNames() {
  return SKILL_NAMES.filter(name =>
    fs.existsSync(path.join(BUNDLED_SKILLS_DIR, name, 'SKILL.md'))
  );
}

/**
 * Copia cada skill empacotada para <targetDir>/.claude/skills/<nome>/.
 *
 * Copia TODOS os arquivos da pasta da skill, não só o SKILL.md: a skill
 * `handover` traz `handover.py`, que faz a parte mecânica do protocolo. Enquanto
 * isto copiava só o .md, o pacote instalava uma skill apontando para um script
 * que não existia na máquina do usuário — a skill parecia instalada e quebrava
 * no primeiro uso.
 *
 * Sem `overwrite`, um SKILL.md existente NÃO é tocado (o usuário pode ter
 * customizado). Mas os arquivos irmãos AUSENTES são copiados mesmo assim, e é
 * isso que conserta o caminho de UPGRADE: quem instalou uma versão que só
 * trazia o SKILL.md caía em 'skipped_exists' e o `handover.py` nunca
 * aterrissava — o upgrade não fazia nada e a skill seguia quebrada. Completar o
 * que falta não sobrescreve nada; só preenche o buraco.
 */
function installSkills(targetDir, { overwrite = false } = {}) {
  const destRoot = path.join(targetDir, '.claude', 'skills');
  const results = [];

  for (const name of bundledSkillNames()) {
    const srcDir = path.join(BUNDLED_SKILLS_DIR, name);
    const destDir = path.join(destRoot, name);
    const destFile = path.join(destDir, 'SKILL.md');
    const files = fs.readdirSync(srcDir)
      .filter(f => fs.statSync(path.join(srcDir, f)).isFile());

    const jaExiste = fs.existsSync(destFile);
    if (jaExiste && !overwrite) {
      // completa só o que está FALTANDO — nunca sobrescreve o que já está lá
      fs.mkdirSync(destDir, { recursive: true });
      const added = files.filter(f => !fs.existsSync(path.join(destDir, f)));
      for (const f of added) {
        fs.copyFileSync(path.join(srcDir, f), path.join(destDir, f));
      }
      results.push({
        name, path: destFile, files: added,
        status: added.length ? 'completed_missing' : 'skipped_exists'
      });
      continue;
    }

    fs.mkdirSync(destDir, { recursive: true });
    for (const f of files) {
      fs.copyFileSync(path.join(srcDir, f), path.join(destDir, f));
    }
    results.push({ name, path: destFile, status: 'installed', files });
  }

  return results;
}

module.exports = { installSkills, bundledSkillNames, BUNDLED_SKILLS_DIR };
