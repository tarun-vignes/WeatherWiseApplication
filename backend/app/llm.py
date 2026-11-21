"""Optional LLM support through any OpenAI-compatible chat endpoint.

Every function returns None when no provider is configured or the call fails,
so callers always fall back to the rule-based output.
"""

import json
import logging
from typing import Any

import httpx

from app import config

log = logging.getLogger(__name__)

# provider -> (base_url, default model). Free options: Ollama (local), Groq and Gemini (free tiers).
PROVIDERS: dict[str, tuple[str, str]] = {
    "ollama": ("http://localhost:11434/v1", "llama3.2"),
    "groq": ("https://api.groq.com/openai/v1", "llama-3.1-8b-instant"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash"),
}


def enabled() -> bool:
    if config.LLM_PROVIDER not in PROVIDERS:
        return False
    return config.LLM_PROVIDER == "ollama" or bool(config.LLM_API_KEY)


def status() -> dict[str, Any]:
    if not enabled():
        return {"enabled": False, "provider": "none", "model": None}
    _, default_model = PROVIDERS[config.LLM_PROVIDER]
    return {"enabled": True, "provider": config.LLM_PROVIDER, "model": config.LLM_MODEL or default_model}


async def chat(system: str, user: str, json_mode: bool = False, max_tokens: int = 400) -> str | None:
    if not enabled():
        return None
    base_url, default_model = PROVIDERS[config.LLM_PROVIDER]
    body: dict[str, Any] = {
        "model": config.LLM_MODEL or default_model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {config.LLM_API_KEY or 'ollama'}"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{config.LLM_BASE_URL or base_url}/chat/completions", json=body, headers=headers)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        log.warning("LLM call failed, using rule-based fallback: %s", exc)
        return None


async def chat_json(system: str, user: str) -> dict[str, Any] | None:
    text = await chat(system, user, json_mode=True)
    if text is None:
        return None
    # Some models wrap JSON in markdown fences despite json_mode.
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("LLM returned invalid JSON: %.200s", text)
        return None
    return data if isinstance(data, dict) else None
