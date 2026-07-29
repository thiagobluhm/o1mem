/**
 * test_ui_smoke.js — prova que o painel RENDERIZA, sem abrir navegador.
 *
 * Roda a página contra o SEU `handover-nudge.log` real (ou o demo embutido, se
 * não houver log) e confere o que o olho conferiria: KPIs preenchidos, a barra
 * empilhada somando 100%, uma coluna por sessão, o eixo sem virar mancha de
 * rótulos, a tabela completa e nada de texto não escapado.
 *
 * USO:  node test_ui_smoke.js
 */
const fs = require('fs');
const os = require('os');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
const js = html.split('<script>').pop().split('</script>')[0];

// dados: o log real, se existir
const LOG = path.join(os.homedir(), '.claude', 'handover-nudge.log');
let data = [];
if (fs.existsSync(LOG)) {
  data = fs.readFileSync(LOG, 'utf8').split(/\r?\n/)
    .filter((l) => l.trim()).map((l) => { try { return JSON.parse(l); } catch { return null; } })
    .filter(Boolean);
}
const usingReal = data.length > 0;

// ---- DOM mínimo -------------------------------------------------------------
const store = {};
function El(id) {
  const el = {
    id, innerHTML: '', style: {}, dataset: {}, value: id === 'fx' ? '5.40' : '5',
    clientWidth: 820, offsetWidth: 200, offsetHeight: 40, textContent: '',
    classList: { _h: false, add() {}, remove() {}, toggle() { this._h = !this._h; },
                 contains() { return this._h; } },
    setAttribute() {}, addEventListener() {}, closest: () => null,
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 820, height: 300 }),
    querySelectorAll: (s) => pseudo(el.innerHTML, s),
    querySelector: () => null,
  };
  return el;
}
function pseudo(htmlStr, sel) {
  const key = /\.bar/.test(sel) ? 'data-i' : null;
  if (!key) return [];
  return [...String(htmlStr).matchAll(/data-i="(\d+)"/g)]
    .map((m) => ({ dataset: { i: m[1] }, addEventListener() {} }));
}
global.document = {
  querySelector(sel) { const k = sel.replace('#', ''); return (store[k] = store[k] || El(k)); },
  querySelectorAll: () => [], documentElement: {},
};
global.window = { __O1MEM_DATA__: data };
global.getComputedStyle = () => ({ getPropertyValue: () => '#3f8ccc' });
global.addEventListener = () => {};
global.setTimeout = (f) => f;
global.clearTimeout = () => {};
global.FileReader = function () {};
global.innerWidth = 1400; global.innerHeight = 900;
global.Intl = Intl;

// espelha o demo da pagina, para o caso de nao haver log real
const DEMO_FALLBACK = [
  { ts: 1784744532, session_id: '5cf293ca', growth: 153415, total: 198629, threshold: 80000 },
  { ts: 1784761204, session_id: 'b73bb128', growth: 102314, total: 143745, threshold: 80000 },
  { ts: 1784762757, session_id: 'b73bb128', growth: 150941, total: 192372, threshold: 80000 },
  { ts: 1784700000, session_id: 'a1f4c9d2', growth: 88010, total: 130120, threshold: 80000 },
];

let failed = 0;
const check = (name, cond, extra = '') => {
  console.log((cond ? '  OK   ' : '  FALHA') + '  ' + name + (extra ? '  — ' + extra : ''));
  if (!cond) failed++;
};

try { eval(js); } catch (e) {
  console.log('  FALHA  a pagina lancou: ' + e.message);
  console.log(e.stack.split('\n').slice(0, 5).join('\n'));
  process.exit(1);
}

if (!usingReal) { store.demo.onclick({ preventDefault() {} }); }
// `let SESSIONS` do eval nao vaza para este escopo; declaracoes de funcao vazam.
// Entao recalculo a contagem pelo mesmo caminho que a pagina usou.
const nSes = bySession(normalize(usingReal ? data : DEMO_FALLBACK)).length;
console.log(`\nfonte: ${usingReal ? LOG : 'demo embutido'} · ${data.length || 4} eventos · ${nSes} sessoes\n`);

const content = store.content.innerHTML;
check('KPIs renderizados', (content.match(/class="tile/g) || []).length === 4,
      (content.match(/class="tile/g) || []).length + ' cards');
check('area de upload escondida com dados injetados', !usingReal || store.drop.style.display === 'none');
check('link para o grafo', /o1mem_grafo\.html/.test(html));

// barra empilhada: 2 segmentos, e os flex somam 100
const segs = [...store.split.innerHTML.matchAll(/flex:([\d.]+)/g)].map((m) => +m[1]);
check('barra empilhada com 2 segmentos', segs.length === 2, segs.map((s) => s.toFixed(1) + '%').join(' + '));
check('segmentos somam 100%', Math.abs(segs.reduce((a, b) => a + b, 0) - 100) < 0.01,
      segs.reduce((a, b) => a + b, 0).toFixed(3));
check('sem SVG esticado na barra (texto nao distorce)',
      !/preserveAspectRatio="none"/.test(store.split.innerHTML));
check('legenda presente para as 2 categorias',
      (store.split.innerHTML.match(/class="lgi"/g) || []).length === 2);

// colunas: uma por sessao, e nenhuma rolagem horizontal
const chart = store.chart.innerHTML;
const bars = (chart.match(/class="bar"/g) || []).length;
check('uma coluna por sessao', bars === nSes, bars + '/' + nSes);
const vb = /viewBox="0 0 (\d+(?:\.\d+)?) /.exec(chart);
check('largura do grafico cabe no container (sem scroll)', vb && +vb[1] <= 820,
      vb ? vb[1] + 'px para ' + nSes + ' sessoes' : 'sem viewBox');
const xlbls = (chart.match(/text-anchor="middle"/g) || []).length;
check('eixo x com poucas marcas (nao vira mancha)', xlbls > 0 && xlbls <= 8,
      xlbls + ' rotulos de data');
check('linha de limiar do nudge', !usingReal || /class="thr"/.test(chart));
check('coordenadas finitas', !/NaN|Infinity/.test(chart));

// tabela
const rows = (store.tbl.innerHTML.match(/<tr>/g) || []).length - 1;
check('tabela com todas as sessoes', rows === nSes, rows + ' linhas');

// escaping
const inner = [...[content, store.tbl.innerHTML, store.split.innerHTML].join('')
  .matchAll(/>([^<>]*)</g)].map((m) => m[1]);
check('conteudo de texto escapado', inner.every((t) => !/["<>]/.test(t)),
      inner.length + ' trechos');

console.log('\n' + (failed ? `${failed} FALHA(S)` : 'TUDO VERDE'));
process.exit(failed ? 1 : 0);
