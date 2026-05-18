"""LLM factory with three back-ends.

  LLM_PROVIDER=openai  → ChatOpenAI(model=$LLM_MODEL, default gpt-4o-mini)
  LLM_PROVIDER=ollama  → ChatOllama(model=$OLLAMA_MODEL, default llama3.2:3b,
                                    base_url=$OLLAMA_BASE_URL or http://ollama:11434)
  LLM_PROVIDER=mock    → Deterministic rule-based stand-in for tests and
                         offline runs. No network, no API key.

The mock provider is also the auto-fallback when LLM_PROVIDER is unset and
OPENAI_API_KEY is missing — so unit tests / CI don't have to know.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MockResponse:
    """Mimics the .content interface of a langchain AIMessage."""

    content: str


class MockChatLLM:
    """Rule-based stub used in tests + when no API key is configured.

    Inspects the prompt for the three task names the agent nodes pass to it
    and produces a short, deterministic markdown rationale plus, in the
    auditor case, a confidence score the regex parser can read back.
    """

    def invoke(self, prompt: str | list[Any]) -> MockResponse:
        text = _coerce_prompt(prompt)
        lower = text.lower()
        if "forensic investigator" in lower:
            return MockResponse(
                content=(
                    "**Forensic Investigator (mock)**\n"
                    "- RAG matches inspected; pattern resembles flash-loan "
                    "imbalance.\n"
                    "- No confirmed historical exemplar with similarity > 0.95.\n"
                )
            )
        if "risk & compliance auditor" in lower or "risk and compliance" in lower:
            # Echo a confidence in a parseable form — the auditor node strips
            # it out via a regex match on `confidence=...`.
            score = _confidence_from_features(lower)
            return MockResponse(
                content=(
                    f"**Risk & Compliance Auditor (mock)**\n"
                    f"- Aggregated evidence; confidence={score:.2f}.\n"
                    f"- Recommendation: {'escalate' if score >= 0.95 else 'monitor'}.\n"
                )
            )
        if "settlement" in lower or "enforcer" in lower:
            return MockResponse(
                content=(
                    "**Settlement & Enforcer (mock)**\n"
                    "- Freeze instruction compiled.\n"
                    "- Audit trail captured.\n"
                )
            )
        return MockResponse(content="(mock LLM: no matching task header)")


def _coerce_prompt(prompt: str | list[Any]) -> str:
    if isinstance(prompt, str):
        return prompt
    parts: list[str] = []
    for item in prompt:
        if isinstance(item, str):
            parts.append(item)
        elif hasattr(item, "content"):
            parts.append(str(item.content))
        else:
            parts.append(str(item))
    return "\n".join(parts)


def _confidence_from_features(text: str) -> float:
    # Tiny heuristic so the mock auditor's confidence reacts to the prompt
    # content: large OFI or vol pushes it over the 0.95 enforcement gate.
    matches = re.findall(r"ofi[^0-9-]*(-?\d+(?:\.\d+)?)", text)
    rvs = re.findall(r"realized_vol[^0-9-]*(-?\d+(?:\.\d+)?)", text)
    score = 0.5
    if matches:
        try:
            score += min(0.45, abs(float(matches[0])) / 20_000.0)
        except ValueError:
            pass
    if rvs:
        try:
            score += min(0.2, float(rvs[0]) * 4.0)
        except ValueError:
            pass
    return max(0.0, min(1.0, score))


def make_chat_llm():
    """Returns an object with `.invoke(prompt)` → `MockResponse`-like object."""
    provider = os.getenv("LLM_PROVIDER", "").lower()

    if not provider:
        provider = "openai" if os.getenv("OPENAI_API_KEY") else "mock"

    if provider == "mock":
        return MockChatLLM()

    if provider == "openai":
        # Imported lazily so `LLM_PROVIDER=mock` works without the package.
        from langchain_openai import ChatOpenAI  # type: ignore

        return ChatOpenAI(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
            timeout=float(os.getenv("LLM_TIMEOUT_S", "30")),
        )

    if provider == "ollama":
        from langchain_ollama import ChatOllama  # type: ignore

        return ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
        )

    raise ValueError(f"unknown LLM_PROVIDER={provider!r}")
