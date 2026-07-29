/**
 * index.js — dispara indexação dos projetos escolhidos
 */
const { spawnSync } = require('child_process');
const paths = require('./paths');

/**
 * Indexa um projeto (chamando o CLI Python)
 */
function indexProject(pythonCmd, slug) {
  const ragCli = paths.ragCliPath();
  const result = spawnSync(pythonCmd, [ragCli, '--project', slug, 'index', '--json'], {
    encoding: 'utf8'
  });

  if (result.error) {
    return { slug, error: result.error.message };
  }

  try {
    const json = JSON.parse(result.stdout);
    return { slug, ...json };
  } catch {
    return { slug, error: 'JSON inválido: ' + result.stdout };
  }
}

/**
 * Indexa lista de projetos, retorna resumo
 */
function firstIndex(pythonCmd, projects) {
  console.log('\n📋 Indexando projetos...\n');

  const results = [];
  for (const slug of projects) {
    const res = indexProject(pythonCmd, slug);
    results.push(res);

    if (res.error) {
      console.log(`  ❌ ${slug}: ${res.error}`);
    } else {
      console.log(`  ✅ ${slug}: ${res.chunks_total} chunks (${res.embedded} novos)`);
    }
  }

  const failed = results.filter(r => r.error).length;
  if (failed > 0) {
    console.log(`\n⚠️  ${failed} projeto(s) falharam na indexação.\n`);
  }

  return results;
}

module.exports = {
  indexProject,
  firstIndex
};
