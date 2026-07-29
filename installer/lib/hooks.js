/**
 * hooks.js — merge defensivo do hook de handover_nudge no settings.json
 * CRÍTICO: preserva todos os hooks pré-existentes, nunca sobrescreve ou corrompe
 */
const fs = require('fs');
const paths = require('./paths');

/**
 * Lê settings.json (ou {} se não existir)
 */
function readSettings() {
  const settingsPath = paths.settingsPath();
  try {
    const content = fs.readFileSync(settingsPath, 'utf8');
    return JSON.parse(content);
  } catch (e) {
    // Se arquivo não existe, retorna objeto vazio
    // Se JSON é inválido, lança erro (aborda sem escrever)
    if (e.code === 'ENOENT') {
      return {};
    }
    throw new Error(
      'settings.json está corrompido (JSON inválido): ' + settingsPath + '\n' +
      'Corrija manualmente antes de continuar.'
    );
  }
}

/**
 * Escreve settings.json com indentação
 */
function writeSettings(settings) {
  const settingsPath = paths.settingsPath();
  fs.writeFileSync(
    settingsPath,
    JSON.stringify(settings, null, 2) + '\n',
    'utf8'
  );
}

/**
 * Resolve comando do handover_nudge.py (vendorizado dentro do pacote)
 * Retorna um novo matcher-group no formato esperado
 * @param {string} [pythonCmd] - 'python3' ou 'python', detectado no preflight.
 *   Sem isso (ex: testes), cai em 'python3' — funciona em Mac/Linux; Windows
 *   quase sempre tem os dois via py launcher/alias, mas o installer sempre
 *   passa o valor detectado de verdade.
 */
function buildHandoverHookEntry(pythonCmd) {
  const handoverPath = paths.handoverNudgeScriptPath();
  const cmd = pythonCmd || 'python3';

  return {
    hooks: [
      {
        type: 'command',
        command: `${cmd} "${handoverPath}"`,
        timeout: 10
      }
    ]
  };
}

/**
 * Verifica se uma entrada de hook referencia handover_nudge.py
 */
function isHandoverHook(entry) {
  if (!entry.hooks || !Array.isArray(entry.hooks)) return false;
  return entry.hooks.some(h => {
    if (h.type !== 'command' || !h.command) return false;
    return h.command.includes('handover_nudge.py');
  });
}

/**
 * Registra o hook de handover no settings.json
 * Merge defensivo: preserva todos os demais hooks e configurações
 */
function registerHandoverHook(pythonCmd) {
  const settings = readSettings();

  // Inicializa estrutura se não existir
  if (!settings.hooks) {
    settings.hooks = {};
  }
  if (!settings.hooks.UserPromptSubmit) {
    settings.hooks.UserPromptSubmit = [];
  }

  // Verifica se já existe (evita duplicação)
  const alreadyRegistered = settings.hooks.UserPromptSubmit.some(isHandoverHook);
  if (alreadyRegistered) {
    return { status: 'already_registered', updated: false };
  }

  // Adiciona novo matcher-group
  const newHook = buildHandoverHookEntry(pythonCmd);
  settings.hooks.UserPromptSubmit.push(newHook);

  writeSettings(settings);
  return { status: 'registered', updated: true };
}

/**
 * Remove hook de handover do settings.json (usado por uninstall)
 */
function unregisterHandoverHook() {
  const settings = readSettings();

  if (!settings.hooks || !Array.isArray(settings.hooks.UserPromptSubmit)) {
    return { status: 'not_found', updated: false };
  }

  const before = settings.hooks.UserPromptSubmit.length;
  settings.hooks.UserPromptSubmit = settings.hooks.UserPromptSubmit.filter(
    entry => !isHandoverHook(entry)
  );
  const after = settings.hooks.UserPromptSubmit.length;

  if (before > after) {
    writeSettings(settings);
    return { status: 'removed', updated: true };
  }

  return { status: 'not_found', updated: false };
}

module.exports = {
  readSettings,
  writeSettings,
  registerHandoverHook,
  unregisterHandoverHook,
  isHandoverHook
};
