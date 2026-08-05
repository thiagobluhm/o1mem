/**
 * tui.js — a tela do terminal O(1)mem.
 *
 * Navegação por setas com preview lado a lado, em ANSI puro: readline.emitKeypressEvents
 * + raw mode da stdlib. Sem ink/blessed de propósito — o pacote se vende como
 * zero-dependências no `npm i -g`, e ~40 pacotes transitivos por causa de uma
 * lista navegável seria um preço alto pago pelo usuário final.
 *
 * ANTI-FLICKER (custou uma versão que piscava a cada tecla): a primeira versão
 * fazia `\x1b[2J` e redesenhava com dezenas de writes — o terminal chegava a
 * apresentar a tela vazia entre o apagar e o pintar. Agora cada frame é montado
 * como UMA string e escrito de uma vez, sem apagar nada: o cursor volta para o
 * topo e cada linha termina em `\x1b[K`, que limpa só o resto daquela linha.
 * Nada de `2J` no caminho do render.
 *
 * Só entra em cena quando há TTY. Em pipe/CI o `repl` cai no fluxo linha-a-linha.
 */
const fs = require('fs');
const readline = require('readline');

// Paleta "verde fósforo": monocromática sobre preto, como terminal antigo.
// Sendo mono, o tipo do hit não pode virar cor — vira prefixo textual.
const BG = '\x1b[40m';
const R = '\x1b[0m' + BG; // reset que preserva o fundo preto
const BRIGHT = '\x1b[92m';
const GREEN = '\x1b[32m';
const DIM = '\x1b[2;32m';
const SEL = '\x1b[30;102m'; // preto sobre verde brilhante
const BAR = '\x1b[30;42m'; // barra de topo/rodapé

const KIND_TAG = {
  handover: 'HAND',
  project: 'proj',
  feedback: 'feed',
  user: 'user',
  reference: 'ref ',
  archive_bullet: 'arch'
};

const out = s => process.stdout.write(s);
const hideCursor = () => out('\x1b[?25l');
const showCursor = () => out('\x1b[?25h');
// Tela alternativa: ao sair, o terminal devolve o conteúdo que estava antes,
// em vez de deixar o rastro do app no histórico do shell.
const enterAlt = () => out('\x1b[?1049h');
const leaveAlt = () => out('\x1b[?1049l');

function size() {
  return { cols: process.stdout.columns || 80, rows: process.stdout.rows || 24 };
}

/** Texto puro cortado/preenchido em `width` — o cálculo de largura é feito aqui,
 *  antes de qualquer código de cor entrar na string. */
function cell(s, width) {
  const clean = String(s == null ? '' : s).replace(/\s+/g, ' ');
  if (clean.length > width) return clean.slice(0, Math.max(0, width - 1)) + '…';
  return clean.padEnd(width);
}

function fit(s, width) {
  return cell(s, width);
}

/** Quebra texto em linhas de no máximo `width`, preservando parágrafos. */
function wrap(text, width) {
  const lines = [];
  for (const para of String(text == null ? '' : text).split('\n')) {
    if (!para.trim()) {
      lines.push('');
      continue;
    }
    let line = '';
    for (const word of para.split(/\s+/)) {
      if ((line + ' ' + word).trim().length > width) {
        lines.push(line.trim());
        line = word;
      } else {
        line += ' ' + word;
      }
    }
    if (line.trim()) lines.push(line.trim());
  }
  return lines;
}

/**
 * @param {object} io  { query(text,k), open(hit), project(), setProject(slug), projects() }
 */
function start(io) {
  const state = {
    mode: 'input', // input | list | view
    text: '',
    hits: [],
    sel: 0,
    viewLines: [],
    viewTop: 0,
    viewTitle: '',
    status: 'Digite a pergunta e tecle Enter.',
    busy: false
  };

  function headerLine(cols) {
    const title = ' O(1)mem ';
    const proj = ' ' + io.project() + ' ';
    const fill = Math.max(0, cols - title.length - proj.length);
    return BAR + title + ' '.repeat(fill) + proj + R;
  }

  function footerLines(cols) {
    const help =
      state.mode === 'view'
        ? ' ↑↓ rola · esc volta · q sai '
        : state.mode === 'list'
          ? ' ↑↓ navega · ↵ abre · / busca · p projeto · q sai '
          : ' ↵ busca · esc cancela · q sai (campo vazio) ';
    return [DIM + cell(state.status, cols) + R, BAR + cell(help, cols) + R];
  }

  /** Corpo da tela: campo de busca + lista à esquerda e preview à direita. */
  function bodyLines(cols, height) {
    const listW = Math.max(26, Math.floor(cols * 0.42));
    const prevW = Math.max(10, cols - listW - 3);
    const lines = [];

    lines.push('');
    lines.push(BRIGHT + ' > ' + R + GREEN + cell(state.text + (state.mode === 'input' ? '▏' : ''), cols - 3) + R);
    lines.push('');

    const sel = state.hits[state.sel];
    const preview = sel ? wrap(sel.excerpt, prevW) : [];
    const rows = height - 3;

    for (let i = 0; i < rows; i++) {
      const hit = state.hits[i];
      let left;
      if (!hit) {
        left = R + ' '.repeat(listW);
      } else {
        const tag = KIND_TAG[hit.kind] || '....';
        const label = ` ${hit.score.toFixed(2)} [${tag}] ${hit.source}`;
        left = i === state.sel ? SEL + cell(label, listW) + R : GREEN + cell(label, listW) + R;
      }
      lines.push(left + DIM + ' │ ' + R + GREEN + cell(preview[i] || '', prevW) + R);
    }
    return lines;
  }

  function viewBody(cols, height) {
    const lines = [BRIGHT + cell(state.viewTitle, cols) + R, ''];
    for (let i = 0; i < height - 2; i++) {
      lines.push(GREEN + cell(state.viewLines[state.viewTop + i] || '', cols) + R);
    }
    return lines;
  }

  /** Um único write por frame — é isto que mata o piscar. */
  function render() {
    const { cols, rows } = size();
    const body = state.mode === 'view' ? viewBody(cols, rows - 3) : bodyLines(cols, rows - 3);
    const all = [headerLine(cols), ...body, ...footerLines(cols)];

    let frame = BG + '\x1b[H';
    for (let i = 0; i < rows; i++) {
      frame += (all[i] === undefined ? '' : all[i]) + '\x1b[K';
      if (i < rows - 1) frame += '\r\n';
    }
    out(frame);
  }

  async function runQuery() {
    if (!state.text.trim()) return;
    state.busy = true;
    state.status = 'buscando…';
    render();
    try {
      const r = await io.query(state.text.trim(), 20);
      state.hits = r.hits || [];
      state.sel = 0;
      state.mode = state.hits.length ? 'list' : 'input';
      const t = r.timings || {};
      state.status = state.hits.length
        ? `${state.hits.length} resultados · ${t.embed_s || 0}s embed · ${t.search_s || 0}s busca`
        : 'nenhum resultado';
    } catch (e) {
      state.status = '❌ ' + e.message;
    }
    state.busy = false;
    render();
  }

  function openSelected() {
    const hit = state.hits[state.sel];
    if (!hit) return;
    const p = io.open(hit);
    if (!p) {
      state.status = `arquivo não encontrado: ${hit.source}`;
      return;
    }
    state.viewLines = wrap(fs.readFileSync(p, 'utf8'), size().cols - 2);
    state.viewTop = 0;
    state.viewTitle = ' ' + p;
    state.mode = 'view';
  }

  async function onKey(str, key) {
    if (state.busy) return;
    key = key || {};
    const { rows } = size();

    if (key.ctrl && key.name === 'c') return quit();

    if (state.mode === 'view') {
      if (key.name === 'escape' || key.name === 'q') state.mode = 'list';
      else if (key.name === 'down') state.viewTop = Math.min(state.viewTop + 1, Math.max(0, state.viewLines.length - 1));
      else if (key.name === 'up') state.viewTop = Math.max(0, state.viewTop - 1);
      else if (key.name === 'pagedown') state.viewTop += rows - 6;
      else if (key.name === 'pageup') state.viewTop = Math.max(0, state.viewTop - (rows - 6));
      return render();
    }

    if (state.mode === 'list') {
      if (key.name === 'q') return quit();
      if (key.name === 'down') state.sel = Math.min(state.sel + 1, state.hits.length - 1);
      else if (key.name === 'up') state.sel = Math.max(0, state.sel - 1);
      else if (key.name === 'return') openSelected();
      else if (str === '/') {
        state.mode = 'input';
        state.text = '';
      } else if (str === 'p') return switchProject();
      return render();
    }

    // input
    if (key.name === 'return') return runQuery();
    if (key.name === 'escape') {
      state.text = '';
      if (state.hits.length) state.mode = 'list';
    } else if (key.name === 'backspace') state.text = state.text.slice(0, -1);
    else if (key.name === 'q' && !state.text) return quit();
    else if (str && !key.ctrl && !key.meta && str.length === 1 && str >= ' ') state.text += str;
    render();
  }

  async function switchProject() {
    const slugs = io.projects();
    if (slugs.length < 2) {
      state.status = 'só há um projeto indexado';
      return render();
    }
    const i = (slugs.indexOf(io.project()) + 1) % slugs.length;
    state.status = `trocando para ${slugs[i]} (carrega o modelo de novo)…`;
    state.busy = true;
    render();
    try {
      await io.setProject(slugs[i]);
      state.hits = [];
      state.mode = 'input';
      state.status = `agora em ${io.project()}`;
    } catch (e) {
      state.status = '❌ ' + e.message;
    }
    state.busy = false;
    render();
  }

  let done;
  const finished = new Promise(r => (done = r));

  function quit() {
    if (process.stdin.setRawMode) process.stdin.setRawMode(false);
    process.stdin.pause();
    process.stdin.removeListener('keypress', onKey);
    process.stdout.removeListener('resize', render);
    out('\x1b[0m');
    leaveAlt();
    showCursor();
    done();
  }

  readline.emitKeypressEvents(process.stdin);
  if (process.stdin.setRawMode) process.stdin.setRawMode(true);
  process.stdin.resume();
  process.stdin.on('keypress', onKey);
  process.stdout.on('resize', render);
  enterAlt();
  hideCursor();
  render();

  return finished;
}

module.exports = { start, wrap, fit, cell };
