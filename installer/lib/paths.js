/**
 * paths.js — centraliza todos os caminhos (home dir, claude dir, o1mem dir, etc.)
 * Garante 1 lugar só de verdade. Suporta override via env vars para testes.
 */
const fs = require('fs');
const path = require('path');
const os = require('os');

function homeDir() {
  // Para testes: O1MEM_TEST_HOME permite isolar de ~/.claude real
  return process.env.O1MEM_TEST_HOME || os.homedir();
}

function claudeDir() {
  return path.join(homeDir(), '.claude');
}

function o1memDir() {
  return path.join(claudeDir(), 'o1mem');
}

function projectsDir() {
  return path.join(claudeDir(), 'projects');
}

function envPath() {
  return path.join(o1memDir(), '.env');
}

function configPath() {
  return path.join(o1memDir(), 'config.json');
}

function settingsPath() {
  return path.join(claudeDir(), 'settings.json');
}

function daemonJsonPath() {
  return path.join(o1memDir(), 'daemon.json');
}

function chromaDir() {
  return path.join(o1memDir(), 'chroma');
}

function ragCliPath() {
  // Vendored dentro do pacote (funciona também instalado via npm, sem repo ao lado)
  return path.resolve(path.join(__dirname, '..', 'vendor', 'rag', 'o1mem_rag.py'));
}

function handoverNudgeScriptPath() {
  return path.resolve(path.join(__dirname, '..', 'vendor', 'hook', 'handover_nudge.py'));
}

/**
 * Lê config.json se existir; retorna {mode, provider, installed_at} ou {}
 */
function readConfig() {
  const p = configPath();
  try {
    return JSON.parse(fs.readFileSync(p, 'utf8'));
  } catch {
    return {};
  }
}

/**
 * Lê .env (chave) — parse simples O1MEM_PROVIDER=... O1MEM_API_KEY=...
 * Retorna {provider, apiKey} ou {}
 */
function readEnv() {
  const p = envPath();
  try {
    const content = fs.readFileSync(p, 'utf8');
    const result = {};
    content.split('\n').forEach(line => {
      line = line.trim();
      if (!line || line.startsWith('#')) return;
      const [k, v] = line.split('=', 2);
      if (k === 'O1MEM_PROVIDER') result.provider = v;
      if (k === 'O1MEM_API_KEY') result.apiKey = v;
    });
    return result;
  } catch {
    return {};
  }
}

/**
 * Detecta slugs já indexados = subpastas em ~/.claude/o1mem/chroma/
 */
function indexedProjects() {
  const p = chromaDir();
  try {
    return fs.readdirSync(p).filter(d => {
      return fs.statSync(path.join(p, d)).isDirectory();
    });
  } catch {
    return [];
  }
}

/**
 * Lista slugs de projetos (subpastas de ~/.claude/projects/)
 */
function listProjects() {
  const p = projectsDir();
  try {
    return fs.readdirSync(p).filter(d => {
      const full = path.join(p, d);
      if (!fs.statSync(full).isDirectory()) return false;
      // Verify memory/ subdir exists (same check as preflight)
      try {
        fs.statSync(path.join(full, 'memory'));
        return true;
      } catch {
        return false;
      }
    });
  } catch {
    return [];
  }
}

module.exports = {
  homeDir,
  claudeDir,
  o1memDir,
  projectsDir,
  envPath,
  configPath,
  settingsPath,
  daemonJsonPath,
  chromaDir,
  ragCliPath,
  handoverNudgeScriptPath,
  readConfig,
  readEnv,
  indexedProjects,
  listProjects
};
