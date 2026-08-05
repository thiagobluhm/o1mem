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
  const argline = buildArgs({ wt: !!wt, psExe, project: opts.project });

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
  return { created: true, path: lnk };
}

/**
 * Monta a linha de argumentos do atalho. Separada para ser testável: foi aqui
 * que o duplo clique quebrou, e o defeito era invisível fora do Windows real.
 */
function buildArgs({ wt, psExe, project }) {
  const slug = project ? ` ${project}` : '';
  return wt
    ? `-w new --title "O(1)mem" "${psExe}" -NoLogo -NoProfile -Command o1mem repl${slug}`
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

module.exports = { createDesktopShortcut, isWindows, findWindowsTerminal, buildArgs };
