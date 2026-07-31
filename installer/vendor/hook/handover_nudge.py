#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
handover_nudge.py  —  gatilho automatico de /handover (UserPromptSubmit hook)

O que faz
---------
Roda ANTES de cada turno do usuario. Le o transcript da sessao, calcula quanto a
CONVERSA cresceu acima do piso da sessao (total_atual - baseline), e quando esse
crescimento cruza um limiar, injeta uma instrucao no contexto do turno pedindo ao
Claude que OFEREÇA um /handover -- mas so depois de aplicar a TRAVA DE VALOR
(Passo 0 da skill handover). Exploracao descartavel NAO vira handover vazio.

Por que "crescimento" e nao "total"
-----------------------------------
O total inclui system+tools+memoria+skills (~fixos por sessao). O que o handover
economiza e o custo de RE-PAGAR a CONVERSA ao arrastar a sessao. Logo o sinal
util e (total_atual - baseline_da_sessao), nao o total bruto.

Calibragem honesta (n=1)
------------------------
O limiar default (80k) e chute educado de UMA sessao observada. E CONFIGURAVEL
(env var ou arquivo) e cada nudge e LOGADO com o crescimento do momento e o
desfecho (accepted/declined/silenced), pra ajustar com dado em 10-15 sessoes.

Config (precedencia: env > arquivo > default)
  env  CLAUDE_HANDOVER_NUDGE_THRESHOLD   primeiro aviso (tokens)      default 80000
  env  CLAUDE_HANDOVER_NUDGE_STEP        passo p/ reavisar            default 70000
  arquivo  ~/.claude/handover-nudge.config.json  {"threshold":..,"reset_step":..}
  desligar tudo: CLAUDE_HANDOVER_NUDGE_DISABLE=1

Arquivos de estado
  ~/.claude/handover-nudge-state/<session_id>.json   {last_level, silenced}
  ~/.claude/handover-nudge.log                       JSONL, um evento por linha

Fail-open: qualquer erro -> sai 0 sem imprimir nada. Nunca bloqueia o turno.
"""

import sys, os, json, time
import subprocess

try:
    sys.stdout.reconfigure(encoding="utf-8")  # bytes UTF-8 limpos p/ o harness, indep. da codepage do console
except Exception:
    pass

HOME = os.path.expanduser("~")
CLAUDE_DIR = os.path.join(HOME, ".claude")
CONFIG_PATH = os.path.join(CLAUDE_DIR, "handover-nudge.config.json")
STATE_DIR = os.path.join(CLAUDE_DIR, "handover-nudge-state")
LOG_PATH = os.path.join(CLAUDE_DIR, "handover-nudge.log")
O1MEM_DIR = os.path.join(CLAUDE_DIR, "o1mem")
DAEMON_JSON = os.path.join(O1MEM_DIR, "daemon.json")

DEFAULT_THRESHOLD = 80000
DEFAULT_STEP = 70000


def _fwd(p):
    """caminho com barras normais, seguro pra colar na instrucao injetada."""
    return p.replace("\\", "/")


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
    ev = os.environ.get("CLAUDE_HANDOVER_NUDGE_THRESHOLD")
    es = os.environ.get("CLAUDE_HANDOVER_NUDGE_STEP")
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


def usage_total(rec):
    """ocupacao de contexto de um record assistant = input + cache_creation + cache_read."""
    try:
        u = rec.get("message", {}).get("usage")
        if not isinstance(u, dict):
            return None, None
        it = u.get("input_tokens")
        if it is None:
            return None, None
        total = (
            int(it)
            + int(u.get("cache_creation_input_tokens", 0) or 0)
            + int(u.get("cache_read_input_tokens", 0) or 0)
        )
        model = rec.get("message", {}).get("model")
        return total, model
    except Exception:
        return None, None


def _scan_usage(f, baseline, current, model):
    """Varre linhas de um handle já posicionado, atualizando baseline (só na 1a vez)/current/model."""
    for line in f:
        if '"usage"' not in line:
            continue
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        total, m = usage_total(rec)
        if total is None:
            continue
        if baseline is None:
            baseline = total
        current = total
        if m:
            model = m
    return baseline, current, model


def read_baseline_current(transcript_path, cache=None):
    """Le baseline/current/model do transcript.

    Sem `cache`: varre o arquivo inteiro (compat/1a chamada de uma sessao).
    Com `cache` (dict persistido em disco entre turnos, chave "scan"): le só o
    trecho novo desde o último offset — o transcript só CRESCE turno a turno,
    então não há motivo pra reler o que já foi contabilizado. Retorna também
    o cache atualizado (offset/size/baseline/current/model) como 4o valor
    quando `cache` foi passado; None caso contrário (assinatura antiga).
    """
    if cache is None:
        baseline = current = model = None
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                baseline, current, model = _scan_usage(f, None, None, None)
        except Exception:
            return None, None, None
        return baseline, current, model

    try:
        st = os.stat(transcript_path)
        size, mtime = st.st_size, st.st_mtime
    except Exception:
        return None, None, None, cache

    offset = cache.get("offset")
    baseline = cache.get("baseline")
    current = cache.get("current")
    model = cache.get("model")

    # arquivo encolheu/mudou (rotacao, novo transcript no mesmo id) -> reset total.
    if offset is None or size < offset:
        offset, baseline, current, model = 0, None, None, None

    if size == offset and cache.get("mtime") == mtime:
        # nada novo desde a ultima leitura -- devolve o cache tal qual.
        return baseline, current, model, cache

    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            f.seek(offset)
            baseline, current, model = _scan_usage(f, baseline, current, model)
            new_offset = f.tell()
    except Exception:
        return None, None, None, cache

    new_cache = {"offset": new_offset, "size": size, "mtime": mtime,
                 "baseline": baseline, "current": current, "model": model}
    return baseline, current, model, new_cache


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
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(evt, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _should_rag_enrich():
    """Retorna True se RAG enrichment está habilitado (default False)."""
    # Env override first
    if os.environ.get("CLAUDE_HANDOVER_NUDGE_RAG") == "0":
        return False
    # Config file
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                c = json.load(f)
            if "rag_enrichment" in c:
                return bool(c.get("rag_enrichment", False))
    except Exception:
        pass
    return False


def _project_slug_from_transcript(transcript_path):
    """Deriva o slug do projeto a partir do caminho do transcript.

    O transcript vive em ~/.claude/projects/<slug>/<session_id>.jsonl --
    o slug e o nome da pasta-mae, a mesma convencao usada por find_memory_roots().
    """
    try:
        return os.path.basename(os.path.dirname(os.path.abspath(transcript_path)))
    except Exception:
        return None


def _log_miss(reason, latency_ms=0, project_slug=None):
    log_event({
        "ts": int(time.time()),
        "project": project_slug,
        "event": "rag_enrichment",
        "status": "miss",
        "reason": reason,
        "latency_ms": latency_ms,
    })


def _query_daemon(prompt_text, project_slug=None, k=3, timeout_sec=2):
    """Tenta fazer query no daemon via HTTP.

    Retorna (hit: bool, enrichment_text: str)
    - hit=True: daemon respondeu, enrichment_text contém os nós
    - hit=False: daemon não respondeu ou erro, enrichment_text vazio
    Qualquer exceção é engolida (fail-open).
    """
    try:
        if not os.path.exists(DAEMON_JSON):
            _log_miss("no_daemon_json", project_slug=project_slug)
            return False, ""

        with open(DAEMON_JSON, "r", encoding="utf-8") as f:
            daemon_info = json.load(f)
        port = daemon_info.get("port")
        if not port:
            _log_miss("no_port", project_slug=project_slug)
            return False, ""

        # Tenta /health com timeout muito curto pra detectar daemon morto
        try:
            import http.client
            import urllib.parse

            # Prepare query params
            qs_params = {"text": prompt_text, "k": k}
            if project_slug:
                qs_params["project"] = project_slug
            qs = urllib.parse.urlencode(qs_params)

            t0 = time.time()
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout_sec)
            conn.request("GET", f"/query?{qs}")
            resp = conn.getresponse()
            latency_ms = int((time.time() - t0) * 1000)

            if resp.status != 200:
                _log_miss(f"http_{resp.status}", latency_ms, project_slug=project_slug)
                return False, ""

            body = resp.read().decode("utf-8")
            result = json.loads(body)

            # Compõe texto com nomes dos nós + scores
            hits = result.get("hits", [])
            if not hits:
                return True, ""  # hit, mas sem results

            # Extrai nó + score de cada hit (máx 3)
            node_texts = []
            for hit in hits[:3]:
                node = hit.get("node", "")
                score = hit.get("score", 0)
                if node:
                    node_texts.append(f"{node} ({score:.2f})")

            if node_texts:
                enrichment = "Busca semântica local: os fios mais próximos do assunto atual são " + ", ".join(node_texts[:-1]) + (" e " if len(node_texts) > 1 else "") + node_texts[-1] + "."
                log_event({
                    "ts": int(time.time()),
                    "project": project_slug,
                    "event": "rag_enrichment",
                    "status": "hit",
                    "latency_ms": latency_ms,
                    "nodes_count": len(node_texts),
                })
                return True, enrichment
            else:
                log_event({
                    "ts": int(time.time()),
                    "project": project_slug,
                    "event": "rag_enrichment",
                    "status": "hit",
                    "latency_ms": latency_ms,
                    "nodes_count": 0,
                })
                return True, ""
        except Exception:
            _log_miss("exception", project_slug=project_slug)
            return False, ""
    except Exception:
        _log_miss("exception_outer", project_slug=project_slug)
        return False, ""


def _spawn_daemon_detached(project_slug=None):
    """Spawna daemon detached. Fail-open: qualquer erro é engolido.

    Roda o script diretamente (nao "-m o1mem_rag_daemon") porque o daemon nao
    esta instalado como pacote importavel -- ele vive em rag/o1mem_rag_daemon.py,
    irmao desta pasta (hook/) tanto no repo fonte quanto no vendor do installer.
    O proprio daemon insere seu diretorio no sys.path ao rodar como script, entao
    os imports de o1mem_rag/o1mem_graph resolvem sem precisar de "-m".
    """
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        daemon_script = os.path.normpath(os.path.join(here, "..", "rag", "o1mem_rag_daemon.py"))
        if not os.path.isfile(daemon_script):
            return

        cmd = [sys.executable, daemon_script]
        if project_slug:
            cmd += ["--project", project_slug]

        if os.name == "nt":  # Windows
            # subprocess.Popen com DETACHED_PROCESS
            subprocess.Popen(
                cmd,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:  # POSIX
            subprocess.Popen(
                cmd,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        log_event({
            "ts": int(time.time()),
            "event": "rag_enrichment",
            "status": "spawn",
            "latency_ms": 0,
        })
    except Exception:
        # Engolir qualquer erro
        pass


def notify_windows(title, message):
    """Dispara uma notificacao toast nativa do Windows via PowerShell.

    Usa a API Windows.UI.Notifications direto -- nao requer instalar modulo.
    Fail-open: qualquer erro e engolido (nunca afeta o turno).
    """
    try:
        import subprocess
        t = title.replace('"', "'").replace("\n", " ")
        m = message.replace('"', "'").replace("\n", " ")
        ps = (
            '[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null; '
            '$tpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); '
            '$tx = $tpl.GetElementsByTagName("text"); '
            f'$tx.Item(0).AppendChild($tpl.CreateTextNode("{t}")) | Out-Null; '
            f'$tx.Item(1).AppendChild($tpl.CreateTextNode("{m}")) | Out-Null; '
            '$toast = [Windows.UI.Notifications.ToastNotification]::new($tpl); '
            '$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Claude Code"); '
            '$notifier.Show($toast)'
        )
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps],
            timeout=15,
            capture_output=True,
        )
    except Exception:
        pass


def notify_macos(title, message):
    """Dispara uma notificacao nativa do macOS (Notification Center) via osascript.

    Nao precisa instalar nada -- osascript vem no macOS. Fail-open: qualquer
    erro e engolido (nunca afeta o turno).
    """
    try:
        import subprocess
        # AppleScript usa \" pra aspas dentro de string, nao ''. Sem escapar
        # direito, um titulo/mensagem com aspas quebra o script inteiro e a
        # notificacao simplesmente nao aparece -- sem erro visivel no turno.
        t = title.replace('"', '\\"').replace("\n", " ")
        m = message.replace('"', '\\"').replace("\n", " ")
        script = f'display notification "{m}" with title "{t}"'
        subprocess.run(["osascript", "-e", script], timeout=15, capture_output=True)
    except Exception:
        pass


def notify_native(title, message):
    """Escolhe o backend de notificacao nativa pelo SO corrente. Fail-open sempre.

    Linux fica de fora por ora: notify-send precisa de um daemon (notification-
    server) que nem toda distro/sessao tem por padrao -- diferente de
    powershell.exe (Windows) e osascript (macOS), que sempre existem no SO.
    """
    try:
        if sys.platform == "win32":
            notify_windows(title, message)
        elif sys.platform == "darwin":
            notify_macos(title, message)
    except Exception:
        pass


def main():
    if os.environ.get("CLAUDE_HANDOVER_NUDGE_DISABLE") == "1":
        return
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        return
    sid = data.get("session_id") or "unknown"
    transcript = data.get("transcript_path")
    if not transcript or not os.path.exists(transcript):
        return
    slug = _project_slug_from_transcript(transcript)

    event = data.get("hook_event_name") or ""
    state = load_state(sid)
    # cache incremental (offset/size/mtime/baseline/current/model) p/ nao reler
    # o transcript inteiro a cada turno -- so o trecho novo desde a ultima leitura.
    scan_cache = state.get("scan")

    # --- Observador PreCompact (LOG-ONLY, nunca bloqueia, sem stdout) ---
    # Instrumentacao para decidir "com dado" se a ponte bloqueante (PreCompact/auto)
    # vale a pena: registra o tamanho da conversa QUANDO a compactacao disparou e se o
    # usuario ja tinha sido avisado. Se o auto-compact costuma nos pegar ANTES de um
    # nudge aceito, a rede final se justifica; senao, o UserPromptSubmit basta.
    if event == "PreCompact":
        b, c, _, new_scan = read_baseline_current(transcript, scan_cache or {})
        state["scan"] = new_scan
        save_state(sid, state)
        log_event({
            "ts": int(time.time()),
            "session_id": sid,
            "project": slug,
            "event": "precompact_fired",
            "trigger": data.get("trigger"),  # "auto" | "manual"
            "growth": (c - b) if (b is not None and c is not None) else None,
            "total": c,
            "already_nudged_level": int(state.get("last_level", 0) or 0),
            "silenced": bool(state.get("silenced")),
        })
        return  # NUNCA escreve stdout nem bloqueia (exit 0)

    threshold, step = load_config()
    baseline, current, model, new_scan = read_baseline_current(transcript, scan_cache or {})
    state["scan"] = new_scan
    if baseline is None or current is None:
        save_state(sid, state)
        return
    growth = current - baseline
    if growth < threshold:
        save_state(sid, state)
        return

    if state.get("silenced"):
        save_state(sid, state)
        return
    last_level = int(state.get("last_level", 0) or 0)

    # nivel atual cruzado: threshold, threshold+step, threshold+2*step, ...
    idx = (growth - threshold) // step
    level = threshold + idx * step
    if level <= last_level:
        save_state(sid, state)
        return  # ja avisamos neste nivel (ou acima) -> sem repeticao / sem fadiga

    state["last_level"] = level
    save_state(sid, state)

    growth_k = round(growth / 1000)
    total_k = round(current / 1000)
    level_k = round(level / 1000)
    model_disp = model or "o modelo atual"

    state_file = _fwd(os.path.join(STATE_DIR, sid + ".json"))
    log_file = _fwd(LOG_PATH)

    log_event({
        "ts": int(time.time()),
        "session_id": sid,
        "project": slug,
        "event": "nudge_emitted",
        "growth": growth,
        "total": current,
        "baseline": baseline,
        "level": level,
        "threshold": threshold,
        "model": model,
    })

    # Toast nativo (Windows/macOS) -- paridade com o watchdog do Hermes.
    # Alem do texto injetado no contexto, cutuca o usuario fora do terminal.
    proj_display = slug if slug else "Projeto desconhecido"
    notify_native(
        f"Claude Code — {proj_display}",
        f"A conversa cresceu ~{growth_k}k tokens. Considere /handover antes do /clear.",
    )

    # Texto FACTUAL, nao imperativo. A doc oficial de hooks avisa que texto injetado
    # em registro de comando out-of-band ("faça X", "NAO faça Y") dispara as defesas
    # anti-prompt-injection do Claude, que passa a EXIBIR o texto em vez de trata-lo
    # como contexto. Entao aqui so afirmamos FATOS (crescimento, limiar, disciplina do
    # ambiente, e como a mecanica funciona); a decisao de agir fica com o Claude+usuario.
    next_k = round((level + step) / 1000)
    ctx = f"""[Contexto de sessao — informativo; nao e uma mensagem do usuario.]

A conversa desta sessao cresceu ~{growth_k}k tokens acima do piso inicial da sessao (janela total ~{total_k}k tokens, modelo {model_disp}). O limiar configurado para sugerir um handover — {level_k}k de crescimento da conversa — acaba de ser ultrapassado. O proximo aviso, se houver, so ocorre em {next_k}k.

Disciplina de handover deste ambiente: um handover so agrega valor quando ha estado duravel a preservar — tarefa pela metade, raciocinio caro de reconstruir, ou plano de varios passos ainda nao executado. Uma sessao de exploracao descartavel, ou uma tarefa ja concluida e verificada, dispensa handover; nesses casos a memoria basta. Havendo valor, a escolha entre preparar o handover agora, adiar, ou silenciar os avisos do restante da sessao cabe ao usuario.

Mecanica desta sessao, se for util: os avisos ficam silenciados quando o arquivo "{state_file}" contem {{"last_level": {level}, "silenced": true}}; os desfechos de cada aviso sao registrados em "{log_file}"."""

    # Enriquecimento RAG (opcional, fail-open)
    if _should_rag_enrich():
        # Tenta obter contexto do daemon
        try:
            prompt_text = data.get("prompt", "")
            if prompt_text:
                hit, enrichment = _query_daemon(prompt_text, project_slug=slug, k=3, timeout_sec=2)
                if enrichment:
                    ctx += f"\n\n{enrichment}"
                elif not hit:
                    # Miss: spawna daemon pra proximo turno
                    _spawn_daemon_detached(slug)
        except Exception:
            # Qualquer erro → silencioso, ctx segue como estava
            pass

    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": ctx,
        }
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # fail-open absoluto: nunca bloquear o turno do usuario
        pass
