/**
 * shortcut.js — cria o atalho do terminal O(1)mem na área de trabalho (Windows).
 *
 * O que dá "cara de aplicativo" a um programa de terminal não é ele desenhar a
 * própria janela — o Claude Code também roda dentro do terminal do sistema. É o
 * atalho: título, ícone e uma janela que abre já dentro do programa.
 *
 * Em Linux/macOS não faz nada e diz por quê — lá o equivalente é um .desktop ou
 * um app bundle, e ninguém pediu ainda.
 */
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

function isWindows() {
  return process.platform === 'win32';
}

/** PowerShell resolve o Desktop real (que pode estar redirecionado para OneDrive).
 *  O OutputEncoding explícito não é zelo: sem ele "Área de Trabalho" volta em
 *  cp850 e o caminho acentuado nunca existe. */
function desktopDir() {
  const r = spawnSync(
    'powershell',
    [
      '-NoProfile',
      '-Command',
      "[Console]::OutputEncoding=[Text.Encoding]::UTF8; [Environment]::GetFolderPath('Desktop')"
    ],
    { encoding: 'utf8' }
  );
  return (r.stdout || '').trim();
}

/**
 * Cria (ou refaz) o atalho. Retorna {created, path} ou {created:false, reason}.
 */
function createDesktopShortcut(opts = {}) {
  if (!isWindows()) {
    return { created: false, reason: `atalho de área de trabalho só no Windows (aqui: ${process.platform})` };
  }

  const desktop = desktopDir();
  if (!desktop || !fs.existsSync(desktop)) {
    return { created: false, reason: 'não encontrei a pasta da área de trabalho' };
  }

  const lnk = path.join(desktop, 'O(1)mem.lnk');
  const psExe = path.join(
    process.env.SystemRoot || 'C:\\Windows',
    'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe'
  );

  // Windows Terminal quando houver: fonte, cores de 24 bits e título próprio —
  // é a diferença entre "um prompt aberto" e "um app". Senão, powershell puro.
  //
  // ⚠️ `;` é separador de comandos DO wt, não do shell: qualquer ponto-e-vírgula
  // aqui faz ele picar a linha e tentar lançar o resto como outro programa
  // ("[error 0x80070002] when launching ..."). Por isso o título sai por
  // --title (não por $host.UI.RawUI.WindowTitle) e o -Command vai sem aspas,
  // com os tokens soltos — o PowerShell junta os argumentos sozinho.
  const wt = findWindowsTerminal();
  const target = wt || psExe;
  // O perfil carrega a aparência (fundo preto translúcido); a linha só o invoca.
  // Se não deu para escrever o settings.json, a janela abre com o perfil padrão
  // — feio, mas funcionando: aparência nunca deve impedir o atalho de existir.
  const theme = wt ? ensureWtProfile({ psExe }) : { ok: false, reason: 'sem Windows Terminal' };
  const argline = buildArgs({ wt: !!wt, psExe, project: opts.project, profile: theme.ok });

  const ps = `
$s = (New-Object -ComObject WScript.Shell).CreateShortcut(${quote(lnk)})
$s.TargetPath = ${quote(target)}
$s.Arguments = ${quote(argline)}
$s.WorkingDirectory = ${quote(opts.workingDir || process.env.USERPROFILE || '')}
$s.Description = 'Terminal de consulta ao acervo O(1)mem'
$s.IconLocation = ${quote(target + ',0')}
$s.Save()
`;

  const r = spawnSync('powershell', ['-NoProfile', '-Command', ps], { encoding: 'utf8' });
  if (r.status !== 0) {
    return { created: false, reason: (r.stderr || '').trim().split('\n')[0] || 'falha ao criar o atalho' };
  }
  return { created: true, path: lnk, theme };
}

// ===========================================================================
// Tema da janela. O Windows Terminal não aceita opacidade por linha de comando
// — só por perfil no settings.json. Então "fundo preto translúcido" não é uma
// flag no atalho: é um perfil dedicado que o atalho invoca com `-p`.

const WT_PROFILE_NAME = 'O(1)mem';
/** Fixo de propósito: reinstalar tem de ATUALIZAR o perfil, não empilhar cópias. */
const WT_PROFILE_GUID = '{7b1a5e0c-6f2d-4a3b-9c8e-0d1f2a3b4c5d}';

function wtSettingsPath() {
  const local = process.env.LOCALAPPDATA;
  if (!local) return null;
  const p = path.join(
    local, 'Packages', 'Microsoft.WindowsTerminal_8wekyb3d8bbwe', 'LocalState', 'settings.json'
  );
  return fs.existsSync(p) ? p : null;
}

/**
 * O settings.json do Windows Terminal é JSONC — vem com comentários `//` que o
 * JSON.parse rejeita. Removê-los por regex corromperia URLs e caminhos dentro
 * de strings ("C:\\..." e "https://..."), então isto varre caractere a
 * caractere sabendo quando está dentro de uma string.
 */
function stripJsonComments(src) {
  let out = '';
  let inStr = false, esc = false, line = false, block = false;
  for (let i = 0; i < src.length; i++) {
    const ch = src[i], next = src[i + 1];
    if (line) { if (ch === '\n') { line = false; out += ch; } continue; }
    if (block) { if (ch === '*' && next === '/') { block = false; i++; } continue; }
    if (inStr) {
      out += ch;
      if (esc) esc = false;
      else if (ch === '\\') esc = true;
      else if (ch === '"') inStr = false;
      continue;
    }
    if (ch === '"') { inStr = true; out += ch; continue; }
    if (ch === '/' && next === '/') { line = true; i++; continue; }
    if (ch === '/' && next === '*') { block = true; i++; continue; }
    out += ch;
  }
  return out;
}

/** A aparência pedida: preto, 70% translúcido, texto claro. */
function themeProfile(psExe) {
  return {
    guid: WT_PROFILE_GUID,
    name: WT_PROFILE_NAME,
    hidden: false,
    commandline: `"${psExe}" -NoLogo -NoProfile -Command o1mem repl`,
    startingDirectory: '%USERPROFILE%',
    background: '#000000',
    foreground: '#F2F2F2',
    // 90 = quase opaco. Começou em 70 e o texto continuava ruim de ler: o que
    // atravessa o fundo compete com o texto, e translucidez é enfeite, leitura
    // não é. Sem acrílico — o acrílico borra e deixa o papel de parede vazar
    // por trás do texto, foi o que estragou a TUI.
    opacity: 90,
    useAcrylic: false
  };
}

/**
 * Cria ou atualiza o perfil "O(1)mem". Preserva o que o usuário tiver ajustado
 * no perfil (fonte, tamanho) sobrescrevendo só as chaves de aparência que o
 * tema define. Guarda um .bak antes de escrever — este arquivo é do usuário,
 * não nosso.
 */
function ensureWtProfile({ psExe }) {
  const file = wtSettingsPath();
  if (!file) return { ok: false, reason: 'settings.json do Windows Terminal não encontrado' };

  let doc;
  const raw = fs.readFileSync(file, 'utf8');
  try {
    doc = JSON.parse(stripJsonComments(raw));
  } catch (e) {
    return { ok: false, reason: `settings.json não pôde ser lido (${e.message})` };
  }

  const list = Array.isArray(doc.profiles)
    ? doc.profiles
    : (doc.profiles && Array.isArray(doc.profiles.list) ? doc.profiles.list : null);
  if (!list) return { ok: false, reason: 'settings.json sem lista de perfis' };

  const wanted = themeProfile(psExe);
  const i = list.findIndex(p => p && (p.guid === WT_PROFILE_GUID || p.name === WT_PROFILE_NAME));
  const created = i < 0;
  if (created) list.push(wanted);
  else list[i] = Object.assign({}, list[i], wanted);

  try {
    fs.writeFileSync(file + '.o1mem.bak', raw, 'utf8');
    fs.writeFileSync(file, JSON.stringify(doc, null, 4) + '\n', 'utf8');
  } catch (e) {
    return { ok: false, reason: `sem permissão para escrever o settings.json (${e.code || e.message})` };
  }
  return { ok: true, created, profile: WT_PROFILE_NAME, opacity: wanted.opacity, file };
}

/**
 * Monta a linha de argumentos do atalho. Separada para ser testável: foi aqui
 * que o duplo clique quebrou, e o defeito era invisível fora do Windows real.
 */
function buildArgs({ wt, psExe, project, profile }) {
  const slug = project ? ` ${project}` : '';
  // `-p` traz a aparência do perfil; a linha de comando depois dele sobrescreve
  // só o que executar, que é como o slug chega sem perder o tema.
  const p = profile ? ` -p "${WT_PROFILE_NAME}"` : '';
  return wt
    ? `-w new${p} --title "O(1)mem" "${psExe}" -NoLogo -NoProfile -Command o1mem repl${slug}`
    : `-NoLogo -NoProfile -Command "$host.UI.RawUI.WindowTitle='O(1)mem'; o1mem repl${slug}"`;
}

/**
 * Acha o wt.exe. Via `where`, não `fs.existsSync`: o Windows Terminal é
 * distribuído como App Execution Alias, um reparse point que responde EACCES ao
 * stat — existsSync devolve false para um executável que existe e roda.
 */
function findWindowsTerminal() {
  if (!isWindows()) return null;
  const r = spawnSync('where', ['wt.exe'], { encoding: 'utf8' });
  if (r.status !== 0) return null;
  const first = (r.stdout || '').split(/\r?\n/).find(l => l.trim());
  return first ? first.trim() : null;
}

function quote(s) {
  return "'" + String(s).replace(/'/g, "''") + "'";
}

module.exports = {
  createDesktopShortcut, isWindows, findWindowsTerminal, buildArgs,
  ensureWtProfile, stripJsonComments, themeProfile, WT_PROFILE_NAME
};
