/**
 * preflight.js — checagens iniciais (python, pip, projetos)
 */
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const paths = require('./paths');

class PreflightError extends Error {
  constructor(msg) {
    super(msg);
    this.name = 'PreflightError';
  }
}

/**
 * Detecta python (python3 ou python), verifica versão >= 3.8
 */
function checkPython() {
  let pythonCmd = 'python3';
  let result = spawnSync(pythonCmd, ['--version'], {
    encoding: 'utf8',
    stdio: ['pipe', 'pipe', 'pipe']
  });

  if (result.error || result.status !== 0) {
    pythonCmd = 'python';
    result = spawnSync(pythonCmd, ['--version'], {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe']
    });
  }

  if (result.error) {
    throw new PreflightError(
      'Python não encontrado no PATH. Instale Python 3.8+ e tente de novo.'
    );
  }

  // Parse version string: "Python 3.9.0" -> 3.9
  const versionMatch = (result.stdout + result.stderr).match(/Python\s+([\d.]+)/);
  if (!versionMatch) {
    throw new PreflightError('Não consegui detectar versão do Python.');
  }

  const version = versionMatch[1];
  const parts = version.split('.').map(Number);
  const major = parts[0];
  const minor = parts[1];

  if (major < 3 || (major === 3 && minor < 8)) {
    throw new PreflightError(
      `Python ${version} é muito antigo. Você precisa de Python 3.8+.`
    );
  }

  return { pythonCmd, version };
}

/**
 * Verifica pip
 */
function checkPip(pythonCmd) {
  const result = spawnSync(pythonCmd, ['-m', 'pip', '--version'], {
    encoding: 'utf8',
    stdio: ['pipe', 'pipe', 'pipe']
  });

  if (result.error || result.status !== 0) {
    throw new PreflightError(
      'pip não encontrado ou não é funcional. Verifique sua instalação do Python.'
    );
  }

  return true;
}

// Verifica ~/.claude/projects/*/memory/ (at least 1 exists)
function checkProjectsDir() {
  const projDir = paths.projectsDir();

  // Verifica se o diretório pai (~/.claude/projects) existe
  try {
    fs.statSync(projDir);
  } catch {
    throw new PreflightError(
      `Não encontrei ${projDir}.\n` +
      'O(1)mem indexa a memória da convenção ~/.claude/projects/*/memory/.\n' +
      'Crie pelo menos um projeto nesse diretório primeiro.\n' +
      '(Dica: rode uma sessão do Claude Code com --project <slug> para criar.)'
    );
  }

  // Lista subpastas de projetos com memory/
  const projects = paths.listProjects();

  if (projects.length === 0) {
    throw new PreflightError(
      'Nenhum projeto com memory/ encontrado em ' + projDir + '.\n' +
      'O(1)mem indexa a memória; sem projetos não há o que indexar.\n' +
      'Crie pelo menos um projeto rodando uma sessão do Claude Code.'
    );
  }

  return projects;
}

/**
 * Full preflight: python + pip + projetos
 * Retorna {pythonCmd, version, projects} ou lança PreflightError
 */
function preflight() {
  let pythonInfo;
  try {
    pythonInfo = checkPython();
  } catch (e) {
    if (e.name === 'PreflightError') throw e;
    throw new PreflightError('Erro ao verificar Python: ' + e.message);
  }

  try {
    checkPip(pythonInfo.pythonCmd);
  } catch (e) {
    if (e.name === 'PreflightError') throw e;
    throw new PreflightError('Erro ao verificar pip: ' + e.message);
  }

  let projects;
  try {
    projects = checkProjectsDir();
  } catch (e) {
    if (e.name === 'PreflightError') throw e;
    throw new PreflightError('Erro ao verificar projetos: ' + e.message);
  }

  return {
    pythonCmd: pythonInfo.pythonCmd,
    version: pythonInfo.version,
    projects
  };
}

module.exports = {
  preflight,
  checkPython,
  checkPip,
  checkProjectsDir,
  PreflightError
};
