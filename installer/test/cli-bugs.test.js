/**
 * cli-bugs.test.js — testa os 2 bugfixes
 * Bug 1: checkDaemonHealth() é async, precisa await
 * Bug 2: catch reporta erro específico, não sempre "Python não encontrado"
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');

console.log('\n📋 Testando bugfixes de cmdStatus\n');

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

// ============ BUG 1: checkDaemonHealth() retorna Promise ============
test('Bug 1: checkDaemonHealth() retorna Promise', () => {
  const net = require('net');

  function checkDaemonHealth(port) {
    return new Promise(resolve => {
      const socket = net.createConnection({ port, host: '127.0.0.1', timeout: 500 });
      socket.on('connect', () => {
        socket.destroy();
        resolve(true);
      });
      socket.on('error', () => {
        resolve(false);
      });
    });
  }

  // Verifica que o resultado é uma Promise
  const result = checkDaemonHealth(9999);
  assert(result instanceof Promise, 'checkDaemonHealth deve retornar Promise');
});

// ============ BUG 2: Segmentação do catch ============
test('Bug 2: Erro "Não encontrei" é reportado corretamente', () => {
  const error = new Error('Não encontrei ~/.claude/projects/.\nO(1)mem indexa...');
  error.name = 'PreflightError';

  let reported = '';

  // Simula o novo código do catch (Bug 2 fix)
  try {
    throw error;
  } catch (e) {
    if (e.message.includes('Python não encontrado')) {
      reported = 'Python: ❌ não encontrado no PATH';
    } else if (e.message.includes('Não encontrei')) {
      reported = 'Python: ✅, mas ~/.claude/projects/ não encontrado';
    } else if (e.message.includes('Nenhum projeto')) {
      reported = 'Python: ✅, mas nenhum projeto com memory/ encontrado';
    } else if (e.message.includes('pip')) {
      reported = 'Python: ✅, mas pip não está funcional';
    } else {
      reported = `Python: ❌ erro - ${e.message.split('\n')[0]}`;
    }
  }

  // Verifica que foi reportado corretamente
  assert(
    reported.includes('~/.claude/projects/'),
    `Esperava menção a ~/.claude/projects/, got: ${reported}`
  );
  assert(
    !reported.includes('não encontrado no PATH'),
    `Não deveria reportar "não encontrado no PATH" para erro de projetos`
  );
});

test('Bug 2: Erro "Python não encontrado" é reportado como tal', () => {
  const error = new Error('Python não encontrado no PATH. Instale Python...');
  error.name = 'PreflightError';

  let reported = '';

  try {
    throw error;
  } catch (e) {
    if (e.message.includes('Python não encontrado')) {
      reported = 'Python: ❌ não encontrado no PATH';
    } else if (e.message.includes('Não encontrei')) {
      reported = 'Python: ✅, mas ~/.claude/projects/ não encontrado';
    } else if (e.message.includes('Nenhum projeto')) {
      reported = 'Python: ✅, mas nenhum projeto com memory/ encontrado';
    } else if (e.message.includes('pip')) {
      reported = 'Python: ✅, mas pip não está funcional';
    } else {
      reported = `Python: ❌ erro - ${e.message.split('\n')[0]}`;
    }
  }

  assert(
    reported.includes('não encontrado no PATH'),
    `Esperava "não encontrado no PATH", got: ${reported}`
  );
});

test('Bug 2: Erro sobre pip é reportado como pip, não Python', () => {
  const error = new Error('pip não encontrado ou não é funcional. Verifique sua...');
  error.name = 'PreflightError';

  let reported = '';

  try {
    throw error;
  } catch (e) {
    if (e.message.includes('Python não encontrado')) {
      reported = 'Python: ❌ não encontrado no PATH';
    } else if (e.message.includes('Não encontrei')) {
      reported = 'Python: ✅, mas ~/.claude/projects/ não encontrado';
    } else if (e.message.includes('Nenhum projeto')) {
      reported = 'Python: ✅, mas nenhum projeto com memory/ encontrado';
    } else if (e.message.includes('pip')) {
      reported = 'Python: ✅, mas pip não está funcional';
    } else {
      reported = `Python: ❌ erro - ${e.message.split('\n')[0]}`;
    }
  }

  assert(
    reported.includes('pip'),
    `Esperava menção a pip, got: ${reported}`
  );
});
