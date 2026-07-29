/**
 * env.test.js — verifica que apiKey NUNCA é logada
 * Rodável via: node test/env.test.js
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const os = require('os');

// Mock de paths
const testDir = path.join(os.tmpdir(), 'o1mem-env-test-' + Date.now());
fs.mkdirSync(testDir, { recursive: true });

const Module = require('module');
const originalRequire = Module.prototype.require;
Module.prototype.require = function(id) {
  const mod = originalRequire.apply(this, arguments);
  if (id.includes('paths') && mod.o1memDir) {
    mod.o1memDir = () => testDir;
    mod.envPath = () => path.join(testDir, '.env');
    mod.configPath = () => path.join(testDir, 'config.json');
  }
  return mod;
};

const env = require('../lib/env');

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

// Capture console output
function captureConsole(fn) {
  const logs = [];
  const errors = [];
  const oldLog = console.log;
  const oldError = console.error;

  console.log = (...args) => logs.push(args.join(' '));
  console.error = (...args) => errors.push(args.join(' '));

  try {
    fn();
  } finally {
    console.log = oldLog;
    console.error = oldError;
  }

  return { logs, errors };
}

// Testes
test('writeEnv() grava .env sem logar a chave', () => {
  const apiKey = 'sk-ant-test-secret-12345-abcde';

  const { logs, errors } = captureConsole(() => {
    env.writeEnv('anthropic', apiKey);
  });

  // Verifica que o arquivo foi criado
  const envPath = path.join(testDir, '.env');
  assert(fs.existsSync(envPath));

  // Lê arquivo (deve conter a chave)
  const content = fs.readFileSync(envPath, 'utf8');
  assert(content.includes(apiKey));

  // Verifica que logs/errors NÃO contêm a chave
  const combined = (logs + errors).toLowerCase();
  // Procura por pedaços da chave
  assert(!logs.some(log => log.includes(apiKey)));
  assert(!errors.some(err => err.includes(apiKey)));
  // Verifica que "Chave de API armazenada" foi logado (sem a chave)
  assert(logs.some(log => log.includes('Chave de API')));
});

test('validateApiKey() rejeita Anthropic sem sk-ant-', () => {
  const err = env.validateApiKey('sk-invalid', 'anthropic');
  assert(err !== null);
  assert(err.includes('sk-ant-'));
});

test('validateApiKey() aceita Anthropic com sk-ant-', () => {
  const err = env.validateApiKey('sk-ant-valid', 'anthropic');
  assert(err === null);
});

test('validateApiKey() rejeita OpenAI sem sk-', () => {
  const err = env.validateApiKey('invalid-key', 'openai');
  assert(err !== null);
  assert(err.includes('sk-'));
});

test('validateApiKey() aceita OpenAI com sk-', () => {
  const err = env.validateApiKey('sk-valid', 'openai');
  assert(err === null);
});

test('writeConfig() grava sem chave', () => {
  const configPath = path.join(testDir, 'config.json');
  env.writeConfig('aprendizado', 'anthropic');

  const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  assert.strictEqual(config.mode, 'aprendizado');
  assert.strictEqual(config.provider, 'anthropic');
  assert(config.installed_at);
  // Verifica que NÃO tem chave
  assert(!Object.keys(config).some(k => k.includes('key') || k.includes('Key')));
});

// Roda testes
console.log('\n📋 Testando env.js\n');
try {
  fs.rmSync(testDir, { recursive: true, force: true });
} catch {}
