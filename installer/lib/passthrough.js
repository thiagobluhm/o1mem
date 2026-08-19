/**
 * passthrough.js — monta o argv do o1mem_rag.py para os subcomandos que apenas
 * repassam flags do usuario (index, query).
 *
 * Estava inline e duplicado em cmdIndex/cmdQuery. Virou modulo por dois
 * motivos: era o mesmo codigo duas vezes, e inline dentro do cli.js (que
 * executa ao ser carregado) nao dava pra testar sem disparar o CLI inteiro.
 */

/**
 * O argparse do o1mem_rag.py quer os globais ANTES do subcomando:
 *   python o1mem_rag.py --project=<slug> query "texto" -k 5
 * mas o usuario digita na ordem natural (`o1mem query "texto" --project X`),
 * entao `--project` precisa ser reposicionado.
 *
 * O `=` colado nao e estetica: todo slug de ~/.claude/projects/ em POSIX
 * comeca com '-' ('-Users-...'), e como valor separado o argparse le o slug
 * como se fosse outra flag e aborta com "expected one argument". Em Windows o
 * slug comeca com a letra do drive, entao a forma separada funcionava por
 * acidente -- o erro so aparecia no Mac/Linux. A forma colada vale nos dois.
 */
function buildPassthroughArgs(ragCli, subcommand, args) {
  let projectArg = [];
  const otherArgs = [];

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--project' && i + 1 < args.length) {
      projectArg = [`--project=${args[i + 1]}`];
      i++; // pula o valor
    } else if (args[i].startsWith('--project=')) {
      projectArg = [args[i]];
    } else {
      otherArgs.push(args[i]);
    }
  }

  return [ragCli].concat(projectArg, [subcommand], otherArgs);
}

module.exports = { buildPassthroughArgs };
