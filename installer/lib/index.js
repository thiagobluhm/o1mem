/**
 * index.js — dispara indexação dos projetos escolhidos
 */
const { spawnSync } = require('child_process');
const paths = require('./paths');

/**
 * Monta o argv do o1mem_rag.py. Separado de indexProject para poder ser
 * testado sem disparar o Python (ver test/index-args.test.js).
 *
 * Duas amarras que nao sao estilo, sao correcao:
 *
 *  - '--project=<slug>' colado, nunca separado. Slug de POSIX comeca com '-'
 *    ('-Users-...'), e como valor solto o argparse le como flag e aborta. Em
 *    Windows o slug comeca com a letra do drive, entao a forma separada
 *    funcionava por acidente. A forma colada vale nos dois.
 *  - '--json' ANTES do subcomando: ele e argumento global do parser, nao do
 *    'index'. Depois vira "unrecognized arguments" -- em QUALQUER sistema.
 */
function buildIndexArgs(ragCli, slug) {
  return [ragCli, `--project=${slug}`, '--json', 'index'];
}

/**
 * Indexa um projeto (chamando o CLI Python)
 */
function indexProject(pythonCmd, slug) {
  const ragCli = paths.ragCliPath();
  const result = spawnSync(pythonCmd, buildIndexArgs(ragCli, slug), {
    encoding: 'utf8'
  });

  if (result.error) {
    return { slug, error: result.error.message };
  }

  try {
    const json = JSON.parse(result.stdout);
    return { slug, ...json };
  } catch {
    // stderr junto: quando o Python aborta (argparse, traceback) o stdout vem
    // vazio, e so "JSON inválido: " escondia a causa real -- foi o que manteve
    // o bug do '--json' invisivel.
    const detail = (result.stdout || '').trim() || (result.stderr || '').trim() ||
      '(sem saida)';
    return { slug, error: 'JSON inválido: ' + detail };
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
  buildIndexArgs,
  indexProject,
  firstIndex
};
