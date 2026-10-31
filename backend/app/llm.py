"""Talks to a local OpenAI-compatible server (llama.cpp's llama-server, Ollama, LM Studio, ...)."""
import os, json, re, urllib.request

URL = os.environ.get("LLM_URL", "http://localhost:8080/v1").rstrip("/")
MODEL = os.environ.get("LLM_MODEL", "local")        # llama-server ignores this; Ollama/LM Studio need the real name
TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "300"))

class LLMError(Exception):
    pass

def complete(system: str, user: str, mock: dict) -> str:
    if os.environ.get("LLM_MOCK") == "1":   # offline testing without a model
        return json.dumps(mock)
    body = {"model": MODEL, "temperature": 0.8, "max_tokens": 900,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(f"{URL}/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            text = json.load(r)["choices"][0]["message"]["content"]
    except Exception as e:
        raise LLMError(f"Local LLM call to {URL} failed: {e}")
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()

def parse_json(text: str, fallback: dict) -> dict:
    try:
        return json.loads(text[text.index("{"): text.rindex("}") + 1])
    except Exception:
        return fallback
