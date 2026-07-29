/**
 * test_ui_smoke.js — prova que a UI do grafo RENDERIZA, sem abrir navegador.
 *
 * Por que existe: `node --check` só valida sintaxe. O que quebra de verdade aqui
 * é runtime — um seletor que não casa, um `undefined.id`, um nó filtrado virando
 * seleção fantasma, um rótulo não escapado. Este smoke monta um DOM mínimo e um
 * contexto 2D que GRAVA as chamadas, roda a página contra o `graph.json` real e
 * confere que saíram arcos, linhas e rótulos de verdade.
 *
 * USO:  python o1mem_graph.py --project <slug> build   (gera graph.json)
 *       node test_ui_smoke.js
 */
const fs = require('fs');
const path = require('path');

const HERE = __dirname;
const graph = JSON.parse(fs.readFileSync(path.join(HERE, 'graph.json'), 'utf8'));
const html = fs.readFileSync(path.join(HERE, 'index.html'), 'utf8');
const js = html.split('<script>').pop().split('</script>')[0];

// ---- contexto 2D que grava o que foi desenhado ------------------------------
const rec = { arc: 0, moveTo: 0, lineTo: 0, fill: 0, fillText: 0, strokeText: 0, texts: [] };
const ctx2d = new Proxy({}, {
  get(_, k) {
    if (k === 'fillText' || k === 'strokeText')
      return (t) => { rec[k]++; if (k === 'fillText') rec.texts.push(String(t)); };
    if (rec[k] !== undefined) return () => { rec[k]++; };
    return () => {};
  },
  set() { return true; },
});

// ---- DOM mínimo -------------------------------------------------------------
const store = {};
function El(id) {
  const el = {
    id, innerHTML: '', textContent: '', title: '', style: {}, dataset: {},
    checked: true, value: '', offsetWidth: 200, offsetHeight: 40,
    classList: { _c: new Set(), add(c) { this._c.add(c); }, remove(c) { this._c.delete(c); },
                 toggle(c) { this._c.has(c) ? this._c.delete(c) : this._c.add(c); },
                 contains(c) { return this._c.has(c); } },
    setAttribute() {}, getAttribute: () => null, addEventListener() {},
    setPointerCapture() {}, closest: () => null, appendChild() {},
    getContext: () => ctx2d,
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 1200, height: 700 }),
    querySelectorAll: (s) => collect(el.innerHTML, s),
    querySelector: () => null,
  };
  return el;
}
// devolve pseudo-elementos para cada `data-go=` presente no HTML gerado
function collect(htmlStr, sel) {
  if (!/data-go/.test(sel)) return [];
  return [...String(htmlStr).matchAll(/data-go="([^"]+)"/g)].map((m) => ({
    dataset: { go: m[1] }, set onclick(f) {}, addEventListener() {},
  }));
}
const doc = {
  querySelector(sel) {
    const k = sel.replace('#', '');
    return (store[k] = store[k] || El(k));
  },
  querySelectorAll: () => [],
  documentElement: {},
  body: { innerHTML: '' },
};
global.document = doc;
global.window = { __O1MEM_GRAPH__: graph, devicePixelRatio: 2 };
global.getComputedStyle = () => ({ getPropertyValue: () => '#3f8ccc' });
global.requestAnimationFrame = () => 1;   // não roda o loop; chamamos draw() direto
global.cancelAnimationFrame = () => {};
global.addEventListener = () => {};
global.innerWidth = 1400; global.innerHeight = 800;

let failed = 0;
function check(name, cond, extra = '') {
  console.log((cond ? '  OK   ' : '  FALHA') + '  ' + name + (extra ? '  — ' + extra : ''));
  if (!cond) failed++;
}

try {
  eval(js);
} catch (e) {
  console.log('  FALHA  boot() lancou: ' + e.message);
  console.log(e.stack.split('\n').slice(0, 5).join('\n'));
  process.exit(1);
}

console.log(`\ngrafo: ${graph.nodes.length} nos, ${graph.edges.length} arestas\n`);

const nWiki = graph.edges.filter((e) => e.kind === 'wiki').length;
const zero = () => { rec.arc = rec.moveTo = rec.lineTo = rec.fill = rec.fillText = rec.strokeText = 0; };

check('cabecalho com contagem', /\d+<\/b> n[oó]s/.test(store.hdr.innerHTML), store.hdr.innerHTML.replace(/<[^>]+>/g, ''));
check('chips de tipo renderizados', /data-type=/.test(store.chips.innerHTML),
      (store.chips.innerHTML.match(/data-type=/g) || []).length + ' tipos');
check('painel Desenho no HTML', /id="design"/.test(html));
check('8 sliders de desenho/forcas', (html.match(/type="range"/g) || []).length === 8,
      (html.match(/type="range"/g) || []).length);
check('filtro de data presente', /id="d0"/.test(html) && /id="d1"/.test(html));
check('botoes enquadrar/reorganizar', /id="fit"/.test(html) && /id="re"/.test(html));
check('rodape com contagem', /\d+ n[oó]s/.test(store.foot.innerHTML));
check('link para o painel de economia', /o1mem_dashboard\.html/.test(html));

// desenho: zera o gravador e força UM frame, para a contagem ser exata
zero(); draw();
check('nos desenhados no canvas', rec.arc === graph.nodes.length,
      rec.arc + ' arc() vs ' + graph.nodes.length + ' nos');
check('setas desenhadas (a aresta e dirigida)', rec.fill >= nWiki,
      rec.fill + ' fill() para ' + nWiki + ' arestas + ' + graph.nodes.length + ' nos');
check('rotulos com halo (strokeText antes de fillText)',
      rec.strokeText > 0 && rec.strokeText === rec.fillText,
      rec.fillText + ' rotulos');

// com as setas ON cada aresta faz 2 moveTo (linha + ponta); desligando, sobra 1,
// o que mede as DUAS coisas: quantas arestas e que a seta some de verdade.
const withArrows = { fill: rec.fill, moveTo: rec.moveTo };
store.arrows.onchange({ target: { checked: false } });
zero(); draw();
check('arestas do indice ocultas por default', rec.moveTo === nWiki,
      rec.moveTo + ' linhas vs ' + nWiki + ' wiki');
check('toggle de setas remove 1 fill e 1 moveTo por aresta',
      withArrows.fill - rec.fill === nWiki && withArrows.moveTo - rec.moveTo === nWiki,
      (withArrows.fill - rec.fill) + ' fills / ' + (withArrows.moveTo - rec.moveTo) + ' moveTo a menos');
store.arrows.onchange({ target: { checked: true } });

// "esconder nos citados menos de N" precisa realmente esconder
store.s_min.oninput({ target: { value: '3' } });
zero(); draw();
const nAbove = graph.nodes.filter((n) => (n.deg_in || 0) >= 3 || n.type === 'index').length;
check('filtro por peso esconde nos', rec.arc === nAbove,
      rec.arc + ' visiveis com deg_in>=3 (esperado ' + nAbove + ')');

// restaurar padrao volta tudo
store.reset.onclick();
zero(); draw();
check('restaurar padrao devolve todos os nos', rec.arc === graph.nodes.length,
      rec.arc + '/' + graph.nodes.length);

// filtro de data
const ds = graph.nodes.map((n) => Date.parse(n.mtime)).filter(Boolean).sort((a, b) => a - b);
const cut = new Date(ds[Math.floor(ds.length / 2)]).toISOString().slice(0, 10);
store.d0.value = cut; store.d1.value = '';
store.d0.onchange();
zero(); draw();
const nAfter = graph.nodes.filter((n) => Date.parse(n.mtime) >= Date.parse(cut + 'T00:00:00')).length;
check('filtro de data recorta o acervo', rec.arc === nAfter && rec.arc < graph.nodes.length,
      rec.arc + ' nos modificados a partir de ' + cut);
store.dclr.onclick();

// enquadrar nao pode produzir coordenada invalida (view e `let` no eval e nao
// vaza; entao medimos pelo efeito: o frame seguinte tem que sair inteiro)
fit();
zero(); draw();
check('enquadrar mantem o desenho valido', rec.arc === graph.nodes.length && rec.fillText > 0,
      rec.arc + ' nos, ' + rec.fillText + ' rotulos apos enquadrar');

// navegação: selecionar o hub deve popular a sidebar
const hub = graph.nodes.slice().sort((a, b) => b.deg_in - a.deg_in)[0];
select(hub.id);
const info = store.info.innerHTML;
check('sidebar preenchida ao selecionar', /Vizinhos diretos/.test(info));
check('sidebar mostra o arquivo certo', info.includes(hub.file), hub.file);
check('vizinhos clicaveis emitidos', /data-go=/.test(info),
      (info.match(/data-go=/g) || []).length + ' vizinhos');

// busca — pelo caminho real (o handler que a página registrou no input)
store.search.oninput({ target: { value: 'gate' } });
check('busca devolve resultados', /data-go=/.test(store.results.innerHTML),
      (store.results.innerHTML.match(/data-go=/g) || []).length + ' hits para "gate"');

// escaping: nada de < > " crus dentro do texto renderizado
const raw = [info, store.results.innerHTML, store.chips.innerHTML, store.foot.innerHTML].join('');
const inner = [...raw.matchAll(/>([^<>]*)</g)].map((m) => m[1]);
check('conteudo de texto escapado', inner.every((t) => !/["<>]/.test(t)),
      inner.length + ' trechos conferidos');

console.log('\n' + (failed ? `${failed} FALHA(S)` : 'TUDO VERDE'));
process.exit(failed ? 1 : 0);
