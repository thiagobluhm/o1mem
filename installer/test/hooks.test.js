/**
 * hooks.test.js — testa merge defensivo de settings.json
 * Rodável via: node --test test/hooks.test.js (Node 18+)
 * Ou manualmente: node test/hooks.test.js
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const os = require('os');

// Mock de paths.settingsPath() para apontar para fixture
const testDir = path.join(os.tmpdir(), 'o1mem-hooks-test-' + Date.now());
fs.mkdirSync(testDir, { recursive: true });

const settingsFixturePath = path.join(testDir, 'settings.json');

// Sobrescreve paths antes de importar hooks
const Module = require('module');
const originalRequire = Module.prototype.require;
Module.prototype.require = function(id) {
  const mod = originalRequire.apply(this, arguments);
  if (id.includes('paths') && mod.settingsPath) {
    // Override temporário
    mod.settingsPath = () => settingsFixturePath;
  }
  return mod;
};

const hooks = require('../lib/hooks');

function cleanup() {
  try {
    fs.rmSync(testDir, { recursive: true, force: true });
  } catch {}
}

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

// Testes
test('settings.json inexistente → cria do zero com hook', () => {
  // Limpa
  try {
    fs.unlinkSync(settingsFixturePath);
  } catch {}

  // Executa
  const result = hooks.registerHandoverHook();
  assert.strictEqual(result.status, 'registered');
  assert.strictEqual(result.updated, true);

  // Verifica
  const settings = JSON.parse(fs.readFileSync(settingsFixturePath, 'utf8'));
  assert(settings.hooks);
  assert(settings.hooks.UserPromptSubmit);
  assert(settings.hooks.UserPromptSubmit.length > 0);
  assert(hooks.isHandoverHook(settings.hooks.UserPromptSubmit[0]));
});

test('settings com hook pré-existente em PreCompact → preserva, adiciona ao UserPromptSubmit', () => {
  // Fixture: settings com PreCompact hook + UserPromptSubmit vazio
  const existing = {
    permissions: ['file:read'],
    hooks: {
      PreCompact: [
        {
          hooks: [
            { type: 'command', command: 'python other_hook.py', timeout: 30 }
          ]
        }
      ],
      UserPromptSubmit: []
    }
  };
  fs.writeFileSync(settingsFixturePath, JSON.stringify(existing, null, 2), 'utf8');
  const before = fs.readFileSync(settingsFixturePath, 'utf8');

  // Executa
  const result = hooks.registerHandoverHook();
  assert.strictEqual(result.status, 'registered');

  // Verifica
  const settings = JSON.parse(fs.readFileSync(settingsFixturePath, 'utf8'));
  assert.strictEqual(settings.hooks.PreCompact.length, 1);
  assert.strictEqual(settings.hooks.PreCompact[0].hooks[0].command, 'python other_hook.py');
  assert.strictEqual(settings.hooks.UserPromptSubmit.length, 1);
  assert(hooks.isHandoverHook(settings.hooks.UserPromptSubmit[0]));
  assert.strictEqual(settings.permissions[0], 'file:read');
});

test('segundo merge → não duplica hook', () => {
  // Já tem hook de primeiro teste
  const before = JSON.parse(fs.readFileSync(settingsFixturePath, 'utf8'));
  const countBefore = before.hooks.UserPromptSubmit.length;

  // Roda merge de novo
  const result = hooks.registerHandoverHook();
  assert.strictEqual(result.status, 'already_registered');
  assert.strictEqual(result.updated, false);

  // Verifica
  const after = JSON.parse(fs.readFileSync(settingsFixturePath, 'utf8'));
  assert.strictEqual(after.hooks.UserPromptSubmit.length, countBefore);
});

test('settings.json corrompido (JSON inválido) → aborta sem escrever', () => {
  fs.writeFileSync(settingsFixturePath, 'not valid json {]', 'utf8');
  const before = fs.readFileSync(settingsFixturePath, 'utf8');

  // Tenta merge — deve lançar erro
  try {
    hooks.registerHandoverHook();
    throw new Error('deveria ter lançado erro de JSON');
  } catch (e) {
    if (e.message.includes('deveria ter')) throw e;
    assert(e.message.includes('corrompido'));
  }

  // Verifica que arquivo não foi modificado
  const after = fs.readFileSync(settingsFixturePath, 'utf8');
  assert.strictEqual(before, after);
});

test('unregisterHandoverHook() remove só nosso hook, preserva outros', () => {
  // Fixture: 1 handover + 1 outro hook
  const settings = {
    hooks: {
      UserPromptSubmit: [
        {
          hooks: [{ type: 'command', command: 'python handover_nudge.py', timeout: 10 }]
        },
        {
          hooks: [{ type: 'command', command: 'python other.py', timeout: 30 }]
        }
      ]
    }
  };
  fs.writeFileSync(settingsFixturePath, JSON.stringify(settings, null, 2), 'utf8');

  // Executa remove
  const result = hooks.unregisterHandoverHook();
  assert.strictEqual(result.status, 'removed');
  assert.strictEqual(result.updated, true);

  // Verifica
  const after = JSON.parse(fs.readFileSync(settingsFixturePath, 'utf8'));
  assert.strictEqual(after.hooks.UserPromptSubmit.length, 1);
  assert(!hooks.isHandoverHook(after.hooks.UserPromptSubmit[0]));
  assert(after.hooks.UserPromptSubmit[0].hooks[0].command.includes('other.py'));
});

// Roda testes
console.log('\n📋 Testando hooks.js\n');
cleanup();
