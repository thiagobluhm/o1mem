#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
o1mem_rag_daemon.py — servidor HTTP quente para busca semantica.

O hook de nudge chama este daemon (em vez de carregar o modelo todo turno) via
http.client com timeout de 2s e fallback de spawn se o daemon nao existir.
Carrega o modelo UMA vez na inicializacao e mantem um embedder cache no
processo — query subsequent sao ~0.2s em vez de 9.6+0.2s.

Endpoints:
  GET /health          -> {"status":"ok","model":"...","uptime_s":...}
  GET /query?project=<slug>&text=<urlenc>&k=3  -> mesmo shape que o CLI

Disco:
  ~/.claude/o1mem/daemon.json     -> {"port":N,"pid":N,"started_at":"..."}
  (removido ao morrer; env O1MEM_DAEMON_HOME pode override para testes)

Ociosidade:
  30 min sem query (configuravel via O1MEM_DAEMON_IDLE_MIN, em minutos) ->
  exit 0 limpo. Relogio reseta a cada query.

Single-instance:
  Se daemon.json aponta processo vivo (/health ok), novo processo sai 0.
"""
from __future__ import annotations

import argparse
import atexit
import hashlib
import http.server
import json
import os
import signal
import socketserver
import sys
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
GRAPH_DIR = os.path.normpath(os.path.join(HERE, "..", "graph"))
sys.path.insert(0, HERE)
sys.path.insert(0, GRAPH_DIR)

import o1mem_rag as rag  # noqa: E402
import o1mem_graph as og  # noqa: E402

# Env override para testes (nunca tocar ~/.claude/o1mem real durante suite)
DAEMON_HOME = os.path.expanduser(
    os.environ.get("O1MEM_DAEMON_HOME", os.path.join("~", ".claude", "o1mem"))
)
DAEMON_PATH = os.path.join(DAEMON_HOME, "daemon.json")

# Configuracao de ociosidade
DEFAULT_IDLE_MIN = 30
IDLE_MIN = float(os.environ.get("O1MEM_DAEMON_IDLE_MIN", DEFAULT_IDLE_MIN))
IDLE_SEC = IDLE_MIN * 60

# Estado global do daemon
_state = {
    "started_at": time.time(),
    "last_query_ts": time.time(),
    "embedder_cache": {},  # {model_name: (embed_fn, resolved_name)}
    "httpd": None,
    "should_shutdown": False,
    "slug": None,  # Projeto sendo servido
    "root": None,  # Raiz de memory do projeto
}

# Se o env override CHROMA_BASE, respeitar (para testes)
if "O1MEM_CHROMA_BASE" in os.environ:
    rag.CHROMA_BASE = os.environ["O1MEM_CHROMA_BASE"]


def _cached_embedder(model_name: str):
    """Retorna (embed_fn, resolved_name) com cache de processo.

    Chama rag.get_embedder uma unica vez por model_name; reutiliza o
    embedder para todas as queries subsequentes — economiza o custo de
    9.6s de model load por request.
    """
    if model_name not in _state["embedder_cache"]:
        _state["embedder_cache"][model_name] = rag.get_embedder(model_name)
    return _state["embedder_cache"][model_name]


def _query_impl(slug: str, root: str, text: str, k: int, model_name: str,
                with_graph: bool = True) -> dict:
    """Query com embedder cacheado (sem chamar get_embedder).

    Copia a logica de rag.query mas usa _cached_embedder em vez de
    rag.get_embedder, economizando recarregar o modelo a cada request.
    """
    timings = {}
    t0 = time.time()
    embed, resolved_model = _cached_embedder(model_name)
    timings["model_load_s"] = 0.0  # ja carregado no startup

    t0 = time.time()
    vec = embed([text])[0]
    timings["embed_s"] = round(time.time() - t0, 2)

    col = rag.get_collection(slug)
    t0 = time.time()
    res = col.query(query_embeddings=[vec], n_results=min(k, max(col.count(), 1)),
                    include=["documents", "metadatas", "distances"])
    timings["search_s"] = round(time.time() - t0, 2)

    hits = []
    for i, doc, meta, dist in zip(res["ids"][0], res["documents"][0],
                                  res["metadatas"][0], res["distances"][0]):
        hits.append({"id": i, "score": round(1.0 - dist, 4),
                     "source": meta.get("source", ""), "kind": meta.get("kind", ""),
                     "node": meta.get("node", ""), "excerpt": doc[:300]})

    if with_graph:
        t0 = time.time()
        g = og.build_graph(root, slug)
        ids = {n["id"] for n in g["nodes"]}
        for h in hits:
            if h["node"] and h["node"] in ids:
                h["graph_neighbors"] = [
                    {"id": n["id"], "description": n["description"][:110]}
                    for n in og.neighbors(g, h["node"], 1)[:5]
                ]
        timings["graph_s"] = round(time.time() - t0, 2)

    return {"project": slug, "query": text, "model": resolved_model,
            "hits": hits, "timings": timings}


class RequestHandler(http.server.BaseHTTPRequestHandler):
    """Handler para os endpoints do daemon."""

    def log_message(self, format, *args):
        # Silenciar logs padroes do servidor HTTP
        pass

    def do_GET(self):
        """Responde GET requests em /health e /query?..."""
        _state["last_query_ts"] = time.time()
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/health":
                self._health()
            elif path == "/query":
                self._query(parsed)
            else:
                self._error(404, f"Unknown path: {path}")
        except Exception as e:
            try:
                self._error(500, str(e))
            except Exception:
                pass

    def _health(self):
        """GET /health -> {"status":"ok","model":"...","uptime_s":...,"project":...,"root":...}

        `project`/`root` existem porque o daemon serve UM projeto, fixado no
        startup: quem chama precisa saber qual, para reusar o daemon vivo ou
        reiniciá-lo apontando para outro (ver o REPL em installer/lib/repl.js).
        """
        uptime = time.time() - _state["started_at"]
        resp = {
            "status": "ok",
            "model": list(_state["embedder_cache"].keys())[0]
            if _state["embedder_cache"]
            else "unknown",
            "uptime_s": round(uptime, 1),
            "project": _state["slug"],
            "root": _state["root"],
        }
        self._json_response(resp, 200)

    def _query(self, parsed):
        """GET /query?project=<slug>&text=<urlenc>&k=3"""
        qs = parse_qs(parsed.query)
        slug = (qs.get("project", [None])[0] or "").strip()
        text = (qs.get("text", [None])[0] or "").strip()
        k = int(qs.get("k", [3])[0] or 3)
        distill = qs.get("distill", [0])[0]  # ignorado nesta fase

        if not slug or not text:
            self._error(400, "Missing project or text")
            return

        # Daemon serve um projeto específico (determinado no startup via --root/--project)
        # Validar que o slug solicitado é compatível
        if _state["slug"] and slug != _state["slug"]:
            self._error(400, f"Daemon serves project {_state['slug']}, not {slug}")
            return

        model_name = os.environ.get("O1MEM_RAG_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")

        try:
            # query com embedder cacheado
            result = _query_impl(slug, _state["root"], text, k, model_name, with_graph=True)
            self._json_response(result, 200)
        except Exception as e:
            self._error(500, str(e))

    def _json_response(self, data, status):
        """Escreve resposta JSON."""
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status, message):
        """Escreve erro em JSON."""
        self._json_response({"error": message}, status)


def _warm_up(model_name: str):
    """Carrega o embedder no startup (evita latencia no 1o /health)."""
    _cached_embedder(model_name)


def _write_daemon_file(port: int, pid: int):
    """Grava ~/.claude/o1mem/daemon.json"""
    try:
        os.makedirs(DAEMON_HOME, exist_ok=True)
        daemon_info = {
            "port": port,
            "pid": pid,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(DAEMON_PATH, "w", encoding="utf-8") as f:
            json.dump(daemon_info, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: could not write daemon.json: {e}", file=sys.stderr)


def _remove_daemon_file():
    """Remove daemon.json se for do processo atual (nao remover zumbi de outro)."""
    try:
        if not os.path.exists(DAEMON_PATH):
            return
        with open(DAEMON_PATH, "r", encoding="utf-8") as f:
            info = json.load(f)
        if info.get("pid") == os.getpid():
            os.remove(DAEMON_PATH)
    except Exception:
        pass


def _idle_watchdog():
    """Thread que monitora ociosidade e faz shutdown se necessario."""
    import threading

    def watch():
        while not _state["should_shutdown"]:
            time.sleep(5)  # Checar a cada 5s
            idle_time = time.time() - _state["last_query_ts"]
            if idle_time > IDLE_SEC:
                _state["should_shutdown"] = True
                if _state["httpd"]:
                    _state["httpd"].shutdown()
                break

    t = threading.Thread(target=watch, daemon=True)
    t.start()


def check_existing_daemon() -> bool:
    """Verifica se ja existe daemon vivo apontado por daemon.json.

    Return True se existir; False caso contrario (arquivo ausente, stale,
    ou /health falha).
    """
    try:
        if not os.path.exists(DAEMON_PATH):
            return False
        with open(DAEMON_PATH, "r", encoding="utf-8") as f:
            info = json.load(f)
        port = info.get("port")
        if not port:
            return False

        # Tenta bater em /health com timeout curto
        import http.client
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=0.3)
            conn.request("GET", "/health")
            resp = conn.getresponse()
            if resp.status == 200:
                return True  # Daemon existente esta vivo
        except Exception:
            pass
    except Exception:
        pass
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Daemon HTTP para busca semantica O(1)mem")
    ap.add_argument("--project", help="slug do projeto (resolve --root se ausente)")
    ap.add_argument("--root", help="caminho direto para pasta memory/")
    ap.add_argument("--model", default=os.environ.get(
        "O1MEM_RAG_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"))
    args = ap.parse_args(argv)

    # Check single-instance
    if check_existing_daemon():
        # Daemon ja esta vivo -> sai silenciosamente
        return 0

    # Resolve slug/root
    slug, root = og.resolve_root(args.project, args.root)

    # Store no state global para que os handlers tenham acesso
    _state["slug"] = slug
    _state["root"] = root

    # Cria servidor com porta efemera (bind porta 0)
    try:
        server = socketserver.TCPServer(("127.0.0.1", 0), RequestHandler)
        server.allow_reuse_address = True
    except Exception as e:
        print(f"Error: could not bind to 127.0.0.1: {e}", file=sys.stderr)
        return 1

    port = server.server_address[1]
    pid = os.getpid()

    _state["httpd"] = server

    # Warm-up do modelo
    try:
        _warm_up(args.model)
    except Exception as e:
        print(f"Error during warm-up: {e}", file=sys.stderr)
        server.server_close()
        return 1

    # Grava daemon.json
    _write_daemon_file(port, pid)

    # Registra limpeza ao morrer
    atexit.register(_remove_daemon_file)

    def _signal_handler(sig, frame):
        _state["should_shutdown"] = True
        server.shutdown()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # Inicia thread de watchdog de ociosidade
    _idle_watchdog()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        _remove_daemon_file()

    return 0


if __name__ == "__main__":
    sys.exit(main())
