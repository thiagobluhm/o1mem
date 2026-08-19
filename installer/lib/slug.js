/**
 * slug.js — o slug de ~/.claude/projects/ em JS, e o argv do daemon.
 *
 * Equivalente JS de tools/o1mem_slug.py. A regra do harness e uma so: baixa a
 * letra do drive e troca todo caractere fora de [A-Za-z0-9] por '-'.
 *
 *   C:\Projetos\O1MEM        -> c--Projetos-O1MEM
 *   /Users/t/_PESSOAIS/o1mem -> -Users-t--PESSOAIS-o1mem
 *
 * Os dois casos caem da mesma regra: ':' e '\' viram os dois tracos do
 * Windows, a '/' inicial vira o traco unico do POSIX.
 */

/**
 * A versao anterior (inline no repl) era `dir.replace(/[\\/:]/g, '-')`: nao
 * tocava no '_' nem baixava a letra do drive. Consequencias:
 *
 *  - POSIX: /Users/t/_PESSOAIS/o1mem virava '-Users-t-_PESSOAIS-o1mem', que
 *    nao existe. A deteccao de projeto pelo cwd nunca acertava num caminho com
 *    '_' -- falha macia, caia no menu, entao passava por "sem projeto aqui".
 *  - Windows: process.cwd() devolve 'C:' maiusculo, virando 'C--Projetos-...'
 *    contra a pasta real 'c--Projetos-...'. Mesmo sintoma.
 */
function slugForPath(dir) {
  return dir.replace(/^[A-Za-z]:/, m => m.toLowerCase())
            .replace(/[^A-Za-z0-9]/g, '-');
}

/**
 * argv do daemon. '--project=<slug>' colado, nunca separado: slug POSIX comeca
 * com '-' e o argparse do daemon o leria como flag, matando o processo no
 * startup -- o `repl` nao subia. Em Windows o slug comeca com a letra do
 * drive, entao a forma separada passava e o defeito ficou invisivel.
 */
function buildDaemonArgs(daemonCli, project) {
  const args = [daemonCli];
  if (project) args.push(`--project=${project}`);
  return args;
}

module.exports = { slugForPath, buildDaemonArgs };
