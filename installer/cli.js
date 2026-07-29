#!/usr/bin/env node
/**
 * cli.js — o binário o1mem
 * Subcomandos: install | status | index | query | config | uninstall
 */
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const net = require('net');

const paths = require('./lib/paths');
const { preflight, checkPython, PreflightError } = require('./lib/preflight');
const prompt = require('./lib/prompt');
const { installDeps } = require('./lib/pip');
const env = require('./lib/env');
const { registerHandoverHook, unregisterHandoverHook } = require('./lib/hooks');
const indexLib = require('./lib/index');
const { installSkills } = require('./lib/skills');

const { version: PKG_VERSION } = require('./package.json');
const RAG_CLI = paths.ragCliPath();

// Lê comando do argv
const cmd = process.argv[2] || 'status';
const args = process.argv.slice(3);

async function cmdInstall() {
  console.log(`🚀 O(1)mem instalador v${PKG_VERSION}\n`);

  // 1. Preflight
  let prefInfo;
  try {
    console.log('⏳ Checando preflight (Python, pip, projetos)...');
    prefInfo = preflight();
    console.log(`✅ Python ${prefInfo.version} OK`);
    console.log(`✅ pip OK`);
    console.log(`✅ ${prefInfo.projects.length} projeto(s) encontrado(s)\n`);
  } catch (e) {
    if (e.name === 'PreflightError') {
      console.error('❌ ' + e.message);
      process.exit(1);
    }
    throw e;
  }

  // 2. Escolhe projetos
  let projectsToIndex;
  try {
    console.log('Escolha os projetos a indexar:');
    const selected = await prompt.multiSelect(prefInfo.projects, true);
    projectsToIndex = selected.map(i => prefInfo.projects[i]);
    console.log(`Selecionado(s): ${projectsToIndex.join(', ')}\n`);
  } catch (e) {
    console.error('Erro ao selecionar projetos:', e.message);
    process.exit(1);
  }

  // 3. Escolhe modo
  let mode;
  try {
    mode = await prompt.choose(
      'Escolha o modo de busca:',
      [
        'local (grátis, sem chave)',
        'aprendizado (com destilação via LLM, requer chave)'
      ]
    );
    if (mode.startsWith('local')) {
      mode = 'local';
    } else {
      mode = 'aprendizado';
    }
    console.log(`✅ Modo: ${mode}\n`);
  } catch (e) {
    console.error('Erro ao escolher modo:', e.message);
    process.exit(1);
  }

  // 4. Se aprendizado, pede chave
  let provider = null;
  if (mode === 'aprendizado') {
    console.log('Modo aprendizado requer chave de API.');
    console.log('Qual provedor você usa?');
    try {
      provider = await prompt.choose(
        'Provedor:',
        ['Anthropic (Claude)', 'OpenAI (GPT)']
      );
      if (provider.startsWith('Anthropic')) {
        provider = 'anthropic';
      } else {
        provider = 'openai';
      }
      console.log(`✅ Provedor: ${provider}\n`);
    } catch (e) {
      console.error('Erro ao escolher provedor:', e.message);
      process.exit(1);
    }

    // Pede a chave
    let apiKey = '';
    try {
      apiKey = await prompt.askHidden(
        `Cole sua chave de API ${provider} (não será exibida)`
      );
    } catch (e) {
      console.error('Erro ao ler chave:', e.message);
      process.exit(1);
    }

    // Valida
    const valErr = env.validateApiKey(apiKey, provider);
    if (valErr) {
      console.error('❌ ' + valErr);
      process.exit(1);
    }

    // Grava .env
    try {
      env.writeEnv(provider, apiKey);
      env.writeConfig(mode, provider);
    } catch (e) {
      console.error('❌ Erro ao gravar configuração:', e.message);
      process.exit(1);
    }
  } else {
    // Modo local: só grava config
    try {
      env.writeConfig(mode, 'none');
    } catch (e) {
      console.error('❌ Erro ao gravar configuração:', e.message);
      process.exit(1);
    }
  }

  // 5. pip install
  try {
    const agree = await prompt.confirm(
      '\nInstalação vai baixar ~470 MB de modelos (chromadb, sentence-transformers). Continuar?',
      true
    );
    if (!agree) {
      console.log('Abortado. Rode novamente quando estiver pronto.');
      process.exit(0);
    }

    installDeps(prefInfo.pythonCmd);
  } catch (e) {
    console.error('❌ Erro durante pip install:', e.message);
    process.exit(1);
  }

  // 5b. Copia as skills (organizador-mem, handover, retomar) para o projeto
  let skillResults = [];
  try {
    const targetDir = await prompt.ask(
      '\nEm qual pasta de projeto instalar as skills (organizador-mem, handover, retomar)?',
      process.cwd()
    );
    skillResults = installSkills(targetDir);
    console.log('');
    for (const r of skillResults) {
      if (r.status === 'installed') {
        console.log(`✅ skill "${r.name}" → ${r.path}`);
      } else {
        console.log(`ℹ️  skill "${r.name}" já existia, mantida → ${r.path}`);
      }
    }
  } catch (e) {
    console.error('⚠️  Erro ao instalar skills:', e.message);
    console.log('(Você pode copiar manualmente depois — ver installer/skills/.)');
  }

  // 6. First index
  try {
    const results = indexLib.firstIndex(prefInfo.pythonCmd, projectsToIndex);
    const hasError = results.some(r => r.error);
    if (hasError) {
      console.warn('⚠️  Alguns projetos falharam. Veja acima.');
    }
  } catch (e) {
    console.error('❌ Erro durante indexação:', e.message);
    process.exit(1);
  }

  // 7. Registra hook
  try {
    const agree = await prompt.confirm(
      '\nRegistrar hook de nudge no settings.json?',
      true
    );
    if (agree) {
      const result = registerHandoverHook(prefInfo.pythonCmd);
      if (result.status === 'registered') {
        console.log('✅ Hook registrado.');
      } else if (result.status === 'already_registered') {
        console.log('ℹ️  Hook já estava registrado.');
      }
    }
  } catch (e) {
    console.error('⚠️  Erro ao registrar hook:', e.message);
    console.log('(Você pode registrar manualmente depois.)');
  }

  prompt.close();

  // 8. Resumo + status
  console.log('\n' + '='.repeat(50));
  console.log('✅ Instalação concluída!');
  console.log('='.repeat(50));
  if (skillResults.length > 0) {
    console.log('\nSkills instaladas (abra o Claude Code nessa pasta e chame por nome, ou deixe a descrição casar sozinha):');
    for (const r of skillResults) {
      console.log(`  • ${r.name}: ${r.path}`);
    }
  }
  console.log('\nRode para ver o status:\n  npx o1mem status\n');

  // Chama status
  await cmdStatus();
}

async function cmdStatus() {
  console.log('📊 Status O(1)mem\n');

  // Python
  try {
    const { version } = preflight();
    console.log(`Python: ${version} ✅`);
  } catch (e) {
    // Segmenta o erro para mensagem precisa
    if (e.message.includes('Python não encontrado')) {
      console.log('Python: ❌ não encontrado no PATH');
    } else if (e.message.includes('Não encontrei')) {
      console.log('Python: ✅, mas ~/.claude/projects/ não encontrado');
    } else if (e.message.includes('Nenhum projeto')) {
      console.log('Python: ✅, mas nenhum projeto com memory/ encontrado');
    } else if (e.message.includes('pip')) {
      console.log('Python: ✅, mas pip não está funcional');
    } else {
      console.log(`Python: ❌ erro - ${e.message.split('\n')[0]}`);
    }
  }

  // Config
  const config = paths.readConfig();
  if (config.mode) {
    console.log(`Mode: ${config.mode} (${config.provider || 'nenhum provider'})`);
  } else {
    console.log('Mode: não configurado');
  }

  // Índices
  const indexed = paths.indexedProjects();
  if (indexed.length > 0) {
    console.log(`\nProjetos indexados: ${indexed.length}`);
    for (const slug of indexed) {
      const chromaPath = path.join(paths.chromaDir(), slug, 'o1mem_rag_meta.json');
      try {
        const meta = JSON.parse(fs.readFileSync(chromaPath, 'utf8'));
        console.log(`  • ${slug}: ${meta.chunks} chunks`);
      } catch {
        console.log(`  • ${slug}: (não lê meta)`);
      }
    }
  } else {
    console.log('Nenhum índice encontrado.');
  }

  // Daemon
  const daemonPath = paths.daemonJsonPath();
  try {
    const daemon = JSON.parse(fs.readFileSync(daemonPath, 'utf8'));
    // Tenta health via TCP simples
    const isAlive = await checkDaemonHealth(daemon.port);
    console.log(`\nDaemon: ${isAlive ? '✅ vivo' : '⏸️  (pode iniciar ao usar)'} (porta ${daemon.port})`);
  } catch {
    console.log('\nDaemon: não iniciado');
  }

  console.log('');
}

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

function cmdIndex() {
  // Passthrough ao Python CLI
  // O argparse de o1mem_rag.py espera: python script.py [--project X] index [--full] ...
  // Mas o npm passthrough traz args já depois de "index"
  // Solução: busca por --project/-k na lista args e reposiciona antes do cmd

  let projectArg = [];
  let otherArgs = [];
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--project' && i + 1 < args.length) {
      projectArg = [args[i], args[i + 1]];
      i++; // skip next
    } else {
      otherArgs.push(args[i]);
    }
  }

  const pyArgs = [RAG_CLI].concat(projectArg, ['index'], otherArgs);
  const { pythonCmd } = checkPython();
  const result = spawnSync(pythonCmd, pyArgs, { stdio: 'inherit' });
  process.exit(result.status || 0);
}

function cmdQuery() {
  // Passthrough ao Python CLI
  let projectArg = [];
  let otherArgs = [];
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--project' && i + 1 < args.length) {
      projectArg = [args[i], args[i + 1]];
      i++; // skip next
    } else {
      otherArgs.push(args[i]);
    }
  }

  const pyArgs = [RAG_CLI].concat(projectArg, ['query'], otherArgs);
  const { pythonCmd } = checkPython();
  const result = spawnSync(pythonCmd, pyArgs, { stdio: 'inherit' });
  process.exit(result.status || 0);
}

async function cmdConfig() {
  // Reabre modo + chave (só para modo aprendizado)
  console.log('⚙️  Configuração O(1)mem\n');

  const current = paths.readConfig();
  console.log(`Modo atual: ${current.mode || 'não configurado'}`);

  const agree = await prompt.confirm('Reconfigura modo?', false);
  if (!agree) {
    prompt.close();
    return;
  }

  const mode = await prompt.choose(
    'Novo modo:',
    ['local (grátis)', 'aprendizado (com LLM)']
  );
  const newMode = mode.startsWith('local') ? 'local' : 'aprendizado';

  let provider = 'none';
  if (newMode === 'aprendizado') {
    provider = await prompt.choose(
      'Provedor:',
      ['Anthropic', 'OpenAI']
    );
    provider = provider.includes('Anthropic') ? 'anthropic' : 'openai';

    const apiKey = await prompt.askHidden(`Cole sua chave ${provider}:`);
    const valErr = env.validateApiKey(apiKey, provider);
    if (valErr) {
      console.error('❌ ' + valErr);
      prompt.close();
      return;
    }
    env.writeEnv(provider, apiKey);
  }

  env.writeConfig(newMode, provider);
  console.log('✅ Configuração atualizada.');
  prompt.close();
}

async function cmdUninstall() {
  console.log('🗑️  Desinstalar O(1)mem\n');

  const agree = await prompt.confirm(
    'Isso vai remover o hook do settings.json. Continuar?',
    false
  );
  if (!agree) {
    console.log('Abortado.');
    prompt.close();
    return;
  }

  const result = unregisterHandoverHook();
  if (result.updated) {
    console.log('✅ Hook removido do settings.json.');
  } else {
    console.log('ℹ️  Hook não estava registrado.');
  }

  const agreeDelete = await prompt.confirm(
    'Apagar ~/.claude/o1mem/ (índices, config, chave)?',
    false
  );
  if (agreeDelete) {
    const o1memDir = paths.o1memDir();
    try {
      fs.rmSync(o1memDir, { recursive: true, force: true });
      console.log('✅ ' + o1memDir + ' apagado.');
    } catch (e) {
      console.error('❌ Erro ao apagar:', e.message);
    }
  } else {
    console.log(`ℹ️  Deixando dados em ${paths.o1memDir()}.`);
  }

  prompt.close();
}

// Main
(async () => {
  try {
    switch (cmd) {
      case 'install':
        await cmdInstall();
        break;
      case 'status':
        await cmdStatus();
        break;
      case 'index':
        cmdIndex();
        break;
      case 'query':
        cmdQuery();
        break;
      case 'config':
        await cmdConfig();
        break;
      case 'uninstall':
        await cmdUninstall();
        break;
      case '--help':
      case '-h':
        console.log(`
o1mem v${PKG_VERSION} — instalador local da busca semântica O(1)mem

Subcomandos:
  install     Instala dependências, indexa, registra hook
  status      Mostra status: python, mode, índices, daemon
  index       Indexa projeto(s) [--project SLUG] [--full]
  query       Busca [--distill] "texto" [-k NUM]
  config      Reconfigura mode/chave
  uninstall   Remove hook, opcionalmente apaga dados

Exemplos (após 'npm install -g @tbluhm82/o1mem'):
  o1mem install
  o1mem status
  o1mem query "custo do índice" -k 5
`);
        break;
      default:
        console.error(`Comando desconhecido: ${cmd}`);
        process.exit(1);
    }
  } catch (e) {
    console.error('❌ Erro:', e.message);
    if (process.env.DEBUG) {
      console.error(e.stack);
    }
    process.exit(1);
  }
})();
