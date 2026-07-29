"""
o1mem_distill.py — destilação LLM dos resultados da busca semântica
(modo aprendizado: top-k semantico → 1 chamada a LLM → parágrafo curado)
"""
import os
import json
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


def read_env():
    """Lê ~/.claude/o1mem/.env (parse simples, sem deps)
    Retorna (provider, api_key) ou (None, None) se não encontrado
    """
    env_path = os.path.expanduser("~/.claude/o1mem/.env")
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            provider = None
            api_key = None
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    if k == "O1MEM_PROVIDER":
                        provider = v.strip()
                    elif k == "O1MEM_API_KEY":
                        api_key = v.strip()
            return provider, api_key
    except (OSError, IOError):
        return None, None


def distill(query_text, hits, provider=None, api_key=None):
    """Chama LLM (Anthropic ou OpenAI) para destilar top-k em parágrafo.

    Args:
        query_text: a pergunta do usuário
        hits: list of {id, score, excerpt, ...} (output de query())
        provider: "anthropic" | "openai" (se None, tenta ler env)
        api_key: chave de API (se None, tenta ler env)

    Returns:
        Parágrafo destilado (str) ou erro claro apontando config
    """
    if not provider or not api_key:
        read_provider, read_key = read_env()
        if not read_provider or not read_key:
            raise ValueError(
                "Modo aprendizado requer chave de API.\n"
                "Configure com: npx o1mem config"
            )
        provider = provider or read_provider
        api_key = api_key or read_key

    # Monta prompt: excerpts dos hits + pergunta
    excerpts = "\n".join([
        f"- [{h['id']} ({h['score']:.2f})]\n  {h['excerpt'][:200]}"
        for h in hits[:3]  # top 3
    ])

    system_prompt = (
        "Você é um assistente que resume resultados de busca de memória "
        "de projetos de IA. Leia os excertos abaixo e responda: "
        "qual é o essencial para responder a pergunta do usuário? "
        "Responda em um parágrafo, sem numeração, direto ao ponto."
    )

    user_prompt = (
        f"Pergunta: {query_text}\n\n"
        f"Excertos relevantes:\n{excerpts}\n\n"
        f"Qual é o essencial para responder?"
    )

    if provider == "anthropic":
        return _call_anthropic(api_key, system_prompt, user_prompt)
    elif provider == "openai":
        return _call_openai(api_key, system_prompt, user_prompt)
    else:
        raise ValueError(f"Provider desconhecido: {provider}")


def _call_anthropic(api_key, system_prompt, user_prompt):
    """Chama Anthropic Messages API (claude-haiku)"""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    payload = {
        "model": "claude-haiku-4-5-20241022",
        "max_tokens": 300,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}]
    }

    try:
        req = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if "content" in body and len(body["content"]) > 0:
                return body["content"][0].get("text", "")
    except (URLError, HTTPError, json.JSONDecodeError, KeyError) as e:
        raise RuntimeError(f"Erro ao chamar Anthropic: {e}")
    return ""


def _call_openai(api_key, system_prompt, user_prompt):
    """Chama OpenAI Chat Completions (gpt-4o-mini)"""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "authorization": f"Bearer {api_key}",
        "content-type": "application/json"
    }
    payload = {
        "model": "gpt-4o-mini",
        "max_tokens": 300,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    }

    try:
        req = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if "choices" in body and len(body["choices"]) > 0:
                return body["choices"][0].get("message", {}).get("content", "")
    except (URLError, HTTPError, json.JSONDecodeError, KeyError) as e:
        raise RuntimeError(f"Erro ao chamar OpenAI: {e}")
    return ""
