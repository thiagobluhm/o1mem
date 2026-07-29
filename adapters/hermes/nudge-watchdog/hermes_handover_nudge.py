#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hermes_handover_nudge.py — Adaptacao do handover-nudge-hook para Hermes Agent.

O Hermes nao tem hooks UserPromptSubmit como o Claude Code. Em vez disso,
este script le o banco SQLite do Hermes (state.db) para medir o crescimento
da conversa na sessao ativa. Quando o crescimento cruza um limiar, imprime
um aviso factual sugerindo /skill handover.

Design: padrao watchdog — silencioso quando nao ha nada a reportar (stdout
vazio = nada enviado). So produz saida quando o limiar e cruzado.

Config (precedencia: env > config.json > default):
  env  HERMES_HANDOVER_NUDGE_THRESHOLD   primeiro aviso (tokens)    default 80000
  env  HERMES_HANDOVER_NUDGE_STEP        passo p/ reavisar          default 70000
  env  HERMES_HANDOVER_NUDGE_DISABLE     "1" desliga tudo
  arquivo  ~/AppData/Local/hermes/handover-nudge.config.json

Estado:
  ~/AppData/Local/hermes/handover-nudge-state/<session_id>.json
  ~/AppData/Local/hermes/handover-nudge.log  (JSONL)

Fail-open absoluto: qualquer erro -> sai 0 sem imprimir nada.
"""

import sys, os, json, time, sqlite3

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOME = os.path.expanduser("~")
HERMES_HOME = os.path.join(HOME, "AppData", "Local", "hermes")
DB_PATH = os.path.join(HERMES_HOME, "state.db")
CONFIG_PATH = os.path.join(HERMES_HOME, "handover-nudge.config.json")
STATE_DIR = os.path.join(HERMES_HOME, "handover-nudge-state")
LOG_PATH = os.path.join(HERMES_HOME, "handover-nudge.log")

DEFAULT_THRESHOLD = 80000
DEFAULT_STEP = 70000


def load_config():
    threshold, step = DEFAULT_THRESHOLD, DEFAULT_STEP
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                c = json.load(f)
            threshold = int(c.get("threshold", threshold))
            step = int(c.get("reset_step", step))
    except Exception:
        pass
    ev = os.environ.get("HERMES_HANDOVER_NUDGE_THRESHOLD")
    es = os.environ.get("HERMES_HANDOVER_NUDGE_STEP")
    try:
        if ev:
            threshold = int(ev)
    except Exception:
        pass
    try:
        if es:
            step = int(es)
    except Exception:
        pass
    if threshold <= 0:
        threshold = DEFAULT_THRESHOLD
    if step <= 0:
        step = DEFAULT_STEP
    return threshold, step


def get_active_session():
    """Encontra a sessao ativa mais recente (nao finalizada)."""
    if not os.path.exists(DB_PATH):
        return None, None, None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """SELECT id, input_tokens, cache_read_tokens, cache_write_tokens,
                      output_tokens, model, started_at, ended_at
               FROM sessions
               WHERE ended_at IS NULL
               ORDER BY started_at DESC
               LIMIT 1"""
        ).fetchone()
        if row is None:
            return None, None, None
        sid = row["id"]
        # Total de contexto = input + cache_read + cache_write (o que ocupa a janela)
        total = (row["input_tokens"] or 0) + (row["cache_read_tokens"] or 0) + (row["cache_write_tokens"] or 0)
        model = row["model"] or "modelo atual"
        return sid, total, model
    finally:
        conn.close()


def get_conversation_growth(sid):
    """
    Calcula o crescimento da conversa como proxy de tokens.
    
    O Hermes nem sempre popula token_count nas mensagens, entao usamos um
    fallback em cascata:
      1. Soma de token_count (se disponivel e > 0)
      2. Soma de LENGTH(content) // 4 (proxy: ~4 chars por token)
    
    Isso mede o CRESCIMENTO da conversa — o que o handover economiza ao
    permitir /reset + retomada via handover em vez de arrastar a sessao.
    """
    if not os.path.exists(DB_PATH):
        return None
    conn = sqlite3.connect(DB_PATH)
    try:
        # Tentativa 1: token_count populado
        row = conn.execute(
            """SELECT COALESCE(SUM(token_count), 0) as growth
               FROM messages
               WHERE session_id = ? AND compacted = 0 AND token_count IS NOT NULL""",
            (sid,),
        ).fetchone()
        if row and row[0] and row[0] > 0:
            return row[0]

        # Tentativa 2: proxy por tamanho de conteudo (~4 chars/token)
        # Inclui content + tool_calls + reasoning_content (todas as colunas com texto)
        row = conn.execute(
            """SELECT COALESCE(SUM(
                  LENGTH(COALESCE(content, '')) +
                  LENGTH(COALESCE(tool_calls, '')) +
                  COALESCE(LENGTH(reasoning_content), 0)
               ), 0) as total_chars
               FROM messages
               WHERE session_id = ? AND compacted = 0""",
            (sid,),
        ).fetchone()
        if row and row[0]:
            return row[0] // 4
        return None
    except Exception:
        return None
    finally:
        conn.close()


def load_state(sid):
    path = os.path.join(STATE_DIR, sid + ".json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_level": 0, "silenced": False}


def save_state(sid, state):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(os.path.join(STATE_DIR, sid + ".json"), "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass


def log_event(evt):
    try:
        os.makedirs(HERMES_HOME, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(evt, ensure_ascii=False) + "\n")
    except Exception:
        pass


def notify_windows(title, message):
    """Dispara uma notificacao toast nativa do Windows via PowerShell.

    Nao requer instalacao de modulo (usa a API Windows.UI.Notifications direto).
    Fail-open: qualquer erro e engolido.
    """
    try:
        import subprocess
        # Escapa aspas duplas para o literal PowerShell
        t = title.replace('"', "'").replace("\n", " ")
        m = message.replace('"', "'").replace("\n", " ")
        ps = (
            '[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null; '
            '$tpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); '
            '$tx = $tpl.GetElementsByTagName("text"); '
            f'$tx.Item(0).AppendChild($tpl.CreateTextNode("{t}")) | Out-Null; '
            f'$tx.Item(1).AppendChild($tpl.CreateTextNode("{m}")) | Out-Null; '
            '$toast = [Windows.UI.Notifications.ToastNotification]::new($tpl); '
            '$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Hermes"); '
            '$notifier.Show($toast)'
        )
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps],
            timeout=15,
            capture_output=True,
        )
    except Exception:
        pass


def main():
    if os.environ.get("HERMES_HANDOVER_NUDGE_DISABLE") == "1":
        return

    sid, total, model = get_active_session()
    if sid is None:
        return

    # Medir crescimento da conversa
    growth = get_conversation_growth(sid)
    if growth is None:
        return

    threshold, step = load_config()
    if growth < threshold:
        return

    state = load_state(sid)
    if state.get("silenced"):
        return

    last_level = int(state.get("last_level", 0) or 0)
    idx = (growth - threshold) // step
    level = threshold + idx * step
    if level <= last_level:
        return

    state["last_level"] = level
    save_state(sid, state)

    growth_k = round(growth / 1000)
    level_k = round(level / 1000)
    next_k = round((level + step) / 1000)

    log_event({
        "ts": int(time.time()),
        "session_id": sid,
        "event": "nudge_emitted",
        "growth": growth,
        "total": total,
        "level": level,
        "threshold": threshold,
        "model": model,
    })

    # Texto FACTUAL, nao imperativo — mesma disciplina do hook original
    msg = (
        f"⏰ A conversa desta sessao cresceu ~{growth_k}k tokens. "
        f"O limiar para sugerir um handover ({level_k}k) foi ultrapassado. "
        f"Proximo aviso so em {next_k}k.\n\n"
        f"Disciplina: um handover so agrega valor quando ha estado duravel a preservar "
        f"— tarefa pela metade, raciocinio caro de reconstruir, ou plano de varios passos "
        f"ainda nao executado. Sessao de exploracao descartavel ou tarefa concluida dispensa "
        f"handover; nesses casos a memoria basta.\n\n"
        f"Se for util: rode /skill handover para preparar a saida limpa antes do /reset."
    )

    # Notificacao toast nativa do Windows (canal principal no desktop)
    notify_windows(
        f"Hermes - Hora do /handover? (+{growth_k}k)",
        f"A conversa cresceu ~{growth_k}k tokens (limiar {level_k}k cruzado). "
        f"Se ha estado duravel a preservar, rode /skill handover antes do /reset.",
    )

    print(msg)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
