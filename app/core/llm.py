"""Cliente Ollama para Qwen3 8B (LLM local en GPU)."""
from __future__ import annotations

from functools import lru_cache
from typing import Iterable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from app.config import settings
from app.utils.logging import get_logger


log = get_logger(__name__)


@lru_cache(maxsize=1)
def get_llm() -> ChatOllama:
    """Singleton del cliente Ollama. Mantiene contexto cargado en VRAM entre llamadas."""
    log.info(
        "Inicializando ChatOllama model=%s host=%s temp=%.2f num_ctx=%d",
        settings.llm_model,
        settings.ollama_host,
        settings.llm_temperature,
        settings.llm_context_tokens,
    )
    return ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_host,
        temperature=settings.llm_temperature,
        top_p=settings.llm_top_p,
        num_predict=settings.llm_max_tokens,
        num_ctx=settings.llm_context_tokens,
    )


def ask(prompt: str, system: str | None = None) -> str:
    """Llamada one-shot: útil para smoke tests."""
    llm = get_llm()
    messages: list = []
    if system:
        messages.append(SystemMessage(content=system))
    messages.append(HumanMessage(content=prompt))
    result = llm.invoke(messages)
    return result.content if isinstance(result.content, str) else str(result.content)


def stream(prompt: str, system: str | None = None) -> Iterable[str]:
    """Streaming token-a-token para la UI."""
    llm = get_llm()
    messages: list = []
    if system:
        messages.append(SystemMessage(content=system))
    messages.append(HumanMessage(content=prompt))
    for chunk in llm.stream(messages):
        if chunk.content:
            yield chunk.content if isinstance(chunk.content, str) else str(chunk.content)
