/**
 * tui.js — a tela do terminal O(1)mem.
 *
 * Navegação por setas com preview lado a lado, em ANSI puro: readline.emitKeypressEvents
 * + raw mode da stdlib. Sem ink/blessed de propósito — o pacote se vende como
 * zero-dependências no `npm i -g`, e ~40 pacotes transitivos por causa de uma
 * lista navegável seria um preço alto pago pelo usuário final.
 *
 * Só entra em cena quando há TTY. Em pipe/CI o `repl` cai no fluxo linha-a-linha.
 */
const fs = require('fs');
const readline = require('readline');

const C = {
  reset: '\x1b[0m',
  dim: '\x1b[2m',
  bold: '\x1b[1m',
  rev: '\x1b[7m',
  cyan: '\x1b[36m',
  yellow: '\x1b[33m',
  green: '\x1b[32m',
  magenta: '\x1b[35m',
  gray: '\x1b[90m'
};

// Cor por tipo de hit: o acervo frio (handover) é o que a memória quente não tem,
// então merece destaque próprio na varredura visual.
const KIND_COLOR = {
  handover: C.yellow,
  project: C.cyan,
  feedback: C.magenta,
  user: C.green,
  reference: C.green
};

const out = s => process.stdout.write(s);
const clear = () => out('\x1b[2J\x1b[H');
const hideCursor = () => out('\x1b[?25l');
const showCursor = () => out('\x1b[?25h');
const moveTo = (row, col) => out(`\x1b[${row};${col}H`);

function size() {
  return { cols: process.stdout.columns || 80, rows: process.stdout.rows || 24 };
}

/** Corta respeitando a largura da coluna (sem quebrar a moldura). */
function fit(s, width) {
  const clean = (s || '').replace(/\s+/g, ' ');
  return clean.length > width ? clean.slice(0, width - 1) + '…' : clean.padEnd(width);
}

/** Quebra texto em linhas de no máximo `width`, preservando parágrafos. */
function wrap(text, width) {
  const lines = [];
  for (const para of (text || '').split('\n')) {
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
    status: 'Digite a pergunta e tecle Enter.',
    busy: false
  };

  function header() {
    const { cols } = size();
    const title = ' O(1)mem ';
    const proj = ` ${io.project()} `;
    const fill = Math.max(0, cols - title.length - proj.length - 2);
    moveTo(1, 1);
    out(C.rev + C.bold + title + C.reset + C.rev + ' '.repeat(fill) + proj + C.reset);
  }

  function footer() {
    const { cols, rows } = size();
    const help =
      state.mode === 'view'
        ? ' ↑↓ rola · esc volta · q sai '
        : state.mode === 'list'
          ? ' ↑↓ navega · ↵ abre · / nova busca · p projeto · q sai '
          : ' ↵ busca · esc cancela · q sai (campo vazio) ';
    moveTo(rows - 1, 1);
    out(C.dim + fit(state.status, cols) + C.reset);
    moveTo(rows, 1);
    out(C.rev + fit(help, cols) + C.reset);
  }

  function renderInput() {
    const { cols } = size();
    moveTo(3, 1);
    out(C.bold + '> ' + C.reset + fit(state.text + (state.mode === 'input' ? '▏' : ''), cols - 3));
  }

  function renderList() {
    const { cols, rows } = size();
    const listW = Math.max(24, Math.floor(cols * 0.38));
    const prevW = cols - listW - 3;
    const top = 5;
    const height = rows - top - 2;

    for (let i = 0; i < height; i++) {
      const hit = state.hits[i];
      moveTo(top + i, 1);
      if (!hit) {
        out(' '.repeat(listW) + C.gray + ' │ ' + C.reset + ' '.repeat(Math.max(0, prevW)));
        continue;
      }
      const kc = KIND_COLOR[hit.kind] || C.reset;
      const label = `${hit.score.toFixed(2)} ${hit.source}`;
      const line = fit(label, listW);
      out(i === state.sel ? C.rev + line + C.reset : kc + line + C.reset);

      out(C.gray + ' │ ' + C.reset);
      const sel = state.hits[state.sel];
      const preview = sel ? wrap(sel.excerpt, prevW) : [];
      out(fit(preview[i] || '', prevW));
    }
  }

  function renderView() {
    const { cols, rows } = size();
    const height = rows - 5;
    for (let i = 0; i < height; i++) {
      moveTo(4 + i, 1);
      out(fit(state.viewLines[state.viewTop + i] || '', cols));
    }
  }

  function render() {
    clear();
    header();
    if (state.mode === 'view') {
      moveTo(3, 1);
      out(C.bold + fit(state.viewTitle || '', size().cols) + C.reset);
      renderView();
    } else {
      renderInput();
      renderList();
    }
    footer();
  }

  async function runQuery() {
    if (!state.text.trim()) return;
    state.busy = true;
    state.status = 'buscando…';
    render();
    try {
      const r = await io.query(state.text.trim(), 12);
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
    state.viewLines = wrap(fs.readFileSync(p, 'utf8'), size().cols - 1);
    state.viewTop = 0;
    state.viewTitle = p;
    state.mode = 'view';
  }

  async function onKey(str, key) {
    if (state.busy) return;
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
    process.stdin.setRawMode(false);
    process.stdin.pause();
    process.stdin.removeListener('keypress', onKey);
    showCursor();
    clear();
    done();
  }

  readline.emitKeypressEvents(process.stdin);
  process.stdin.setRawMode(true);
  process.stdin.resume();
  process.stdin.on('keypress', onKey);
  process.stdout.on('resize', render);
  hideCursor();
  render();

  return finished;
}

module.exports = { start, wrap, fit };
