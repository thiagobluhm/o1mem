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
 * Eventos em que o hook precisa rodar.
 *
 * `UserPromptSubmit` mede o crescimento da conversa e avisa a hora do handover.
 * `PreCompact` é o momento da PERDA: quando a compactação dispara, o que sai da
 * janela não volta, e é ali que a captura automática da sessão é gravada. O
 * script sempre soube tratar os dois (ele lê `hook_event_name`), mas o
 * installer só registrava o primeiro — então em toda instalação via npm o
 * observador de PreCompact era código morto e a captura nunca acontecia.
 */
const HOOK_EVENTS = ['UserPromptSubmit', 'PreCompact'];

/**
 * Registra o hook de handover no settings.json, nos dois eventos.
 * Merge defensivo: preserva todos os demais hooks e configurações.
 *
 * Idempotente por EVENTO, não pelo conjunto: quem instalou numa versão que só
 * registrava `UserPromptSubmit` ganha o `PreCompact` que falta no próximo
 * install, sem duplicar o que já está lá.
 */
function registerHandoverHook(pythonCmd) {
  const settings = readSettings();

  if (!settings.hooks) {
    settings.hooks = {};
  }

  const added = [];
  for (const event of HOOK_EVENTS) {
    if (!Array.isArray(settings.hooks[event])) {
      settings.hooks[event] = [];
    }
    if (settings.hooks[event].some(isHandoverHook)) {
      continue;
    }
    settings.hooks[event].push(buildHandoverHookEntry(pythonCmd));
    added.push(event);
  }

  if (!added.length) {
    return { status: 'already_registered', updated: false, events: [] };
  }

  writeSettings(settings);
  return { status: 'registered', updated: true, events: added };
}

/**
 * Remove hook de handover do settings.json (usado por uninstall)
 */
function unregisterHandoverHook() {
  const settings = readSettings();

  if (!settings.hooks) {
    return { status: 'not_found', updated: false };
  }

  const removed = [];
  for (const event of HOOK_EVENTS) {
    if (!Array.isArray(settings.hooks[event])) continue;
    const before = settings.hooks[event].length;
    settings.hooks[event] = settings.hooks[event].filter(
      entry => !isHandoverHook(entry)
    );
    if (settings.hooks[event].length < before) removed.push(event);
  }

  if (removed.length) {
    writeSettings(settings);
    return { status: 'removed', updated: true, events: removed };
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
