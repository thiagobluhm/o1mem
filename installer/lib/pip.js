/**
 * pip.js — instala dependencies (chromadb, sentence-transformers)
 */
const { spawnSync } = require('child_process');
const path = require('path');

/**
 * Instala chromadb e sentence-transformers via pip.
 * Já foi confirmado pelo usuário via prompt.
 */
function installDeps(pythonCmd) {
  const deps = ['chromadb', 'sentence-transformers'];

  console.log('\n⏳ Instalando dependencies (~470 MB — pode levar alguns minutos)...');
  console.log(`   Rodando: ${pythonCmd} -m pip install ${deps.join(' ')}\n`);

  const result = spawnSync(pythonCmd, ['-m', 'pip', 'install', ...deps], {
    stdio: 'inherit'  // mostra output em tempo real
  });

  if (result.status !== 0) {
    throw new Error('pip install falhou');
  }

  console.log('\n✅ Dependencies instaladas.\n');
}

module.exports = {
  installDeps
};
