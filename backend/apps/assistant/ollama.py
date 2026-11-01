"""
Talking to the local Ollama server.

Everything that touches that socket lives here, so the rest of F21 can
be tested on a machine that has no model installed.
"""

import json

import httpx
from django.conf import settings

CONNECT_SECONDS = 5
STATUS_SECONDS = 3
EMBED_SECONDS = 120

# A model that was unloaded has to come back into memory before its first
# word, and on a laptop CPU that takes a while.
ANSWER_WAIT_SECONDS = 180

# How long a model stays in memory after a question, so the next one does
# not pay for loading it again.
KEEP_LOADED = "30m"

# Enough room for the notes, the last few turns and a short answer, while
# keeping the memory a small model needs within reach of a laptop.
CONTEXT_TOKENS = 4096
MAX_ANSWER_TOKENS = 450

# Low, because the notes hold the facts and invention is the failure mode.
TEMPERATURE = 0.2


class OllamaUnavailable(Exception):
    """The server is down, the model is missing, or the reply broke off."""


def missing_models():
    """Which configured models are not installed. Raises if Ollama is down."""
    try:
        response = httpx.get(f"{settings.OLLAMA_URL}/api/tags", timeout=STATUS_SECONDS)
        response.raise_for_status()
        installed = {model["name"] for model in response.json()["models"]}
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise OllamaUnavailable(f"Could not reach Ollama ({type(exc).__name__})") from exc

    wanted = [settings.ASSISTANT_CHAT_MODEL, settings.ASSISTANT_EMBED_MODEL]
    return [name for name in wanted if name not in installed and f"{name}:latest" not in installed]


def embed(texts):
    """One vector per text, in order."""
    try:
        response = httpx.post(
            f"{settings.OLLAMA_URL}/api/embed",
            json={"model": settings.ASSISTANT_EMBED_MODEL, "input": texts,
                  "keep_alive": KEEP_LOADED},
            timeout=httpx.Timeout(EMBED_SECONDS, connect=CONNECT_SECONDS),
        )
        response.raise_for_status()
        return response.json()["embeddings"]
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise OllamaUnavailable(f"Could not embed text ({type(exc).__name__})") from exc


def chat(messages):
    """Yields the answer as it is written."""
    body = {
        "model": settings.ASSISTANT_CHAT_MODEL,
        "messages": messages,
        "stream": True,
        "think": False,
        "keep_alive": KEEP_LOADED,
        "options": {
            "num_ctx": CONTEXT_TOKENS,
            "num_predict": MAX_ANSWER_TOKENS,
            "temperature": TEMPERATURE,
        },
    }
    timeout = httpx.Timeout(ANSWER_WAIT_SECONDS, connect=CONNECT_SECONDS)
    try:
        with httpx.stream("POST", f"{settings.OLLAMA_URL}/api/chat",
                          json=body, timeout=timeout) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                reply = json.loads(line)
                if "error" in reply:
                    raise OllamaUnavailable("Ollama stopped partway through an answer")
                text = reply.get("message", {}).get("content")
                if text:
                    yield text
    except (httpx.HTTPError, ValueError) as exc:
        raise OllamaUnavailable(f"Could not get an answer ({type(exc).__name__})") from exc
