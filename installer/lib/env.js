/**
 * env.js — escreve ~/.claude/o1mem/.env (chave) e config.json (modo/provider)
 * CRÍTICO: chave NUNCA é logada, nunca aparece em stdout
 */
const fs = require('fs');
const path = require('path');
const os = require('os');
const paths = require('./paths');

/**
 * Cria diretório ~/.claude/o1mem/ (recursivo)
 */
function ensureO1memDir() {
  const dir = paths.o1memDir();
  fs.mkdirSync(dir, { recursive: true });
}

/**
 * Escreve .env com chave (nunca loga o valor)
 * No Windows: avisa que é arquivo do perfil do usuário
 * Em POSIX: chmod 600
 */
function writeEnv(provider, apiKey) {
  ensureO1memDir();

  const envPath = paths.envPath();
  const content = `O1MEM_PROVIDER=${provider}\nO1MEM_API_KEY=${apiKey}\n`;

  fs.writeFileSync(envPath, content, 'utf8');

  // Permissões
  if (os.platform() === 'win32') {
    console.log(
      '\n⚠️  Aviso Windows: ' + envPath +
      ' é um arquivo do seu perfil de usuário.\n   Não compartilhe, não versione.'
    );
  } else {
    try {
      fs.chmodSync(envPath, 0o600);
    } catch {
      // Ignora se chmod falhar (ex: filesystem que não suporta)
    }
  }

  // Confirma escrita SEM mostrar a chave
  console.log('✅ Chave de API armazenada em ' + envPath);
}

/**
 * Escreve config.json com mode + provider (SEM chave)
 */
function writeConfig(mode, provider) {
  ensureO1memDir();

  const configPath = paths.configPath();
  const config = {
    mode,
    provider,
    installed_at: new Date().toISOString(),
    // Onde o o1mem_rag.py vendorizado ficou. Sem isto, a skill `handover`
    // (handover.py) não tem como achar o RAG numa instalação via npm — o
    // pacote pode estar em qualquer node_modules ou no cache do npx — e a
    // indexação do handover era silenciosamente pulada.
    rag_cli: paths.ragCliPath()
  };

  fs.writeFileSync(configPath, JSON.stringify(config, null, 2) + '\n', 'utf8');
  console.log('✅ Configuração gravada: mode=' + mode + ', provider=' + provider);
}

/**
 * Valida formato de chave: sk-ant-* (Anthropic) ou sk-* (OpenAI)
 */
function validateApiKey(key, provider) {
  if (provider === 'anthropic') {
    if (!key.startsWith('sk-ant-')) {
      return 'Chave Anthropic deve começar com sk-ant-';
    }
  } else if (provider === 'openai') {
    if (!key.startsWith('sk-')) {
      return 'Chave OpenAI deve começar com sk-';
    }
  }
  return null;
}

module.exports = {
  ensureO1memDir,
  writeEnv,
  writeConfig,
  validateApiKey
};
