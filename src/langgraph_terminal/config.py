from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from langgraph_terminal.reasoning import normalize_reasoning_level

DEFAULT_CONFIG_PATH = Path(".terminal_agent/config.json")
DEFAULT_RAG_INDEX_PATH = Path(".terminal_agent/rag_index.json")
MEMORY_POLICIES = ("strict", "balanced", "off")


def _default_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


def _default_embedding_model() -> str:
    return os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


def _default_reasoning_level() -> str:
    raw = os.getenv("OPENAI_REASONING_LEVEL") or os.getenv("OPENAI_REASONING")
    return normalize_reasoning_level(raw)


def _default_temperature() -> float:
    raw = os.getenv("OPENAI_TEMPERATURE", "0.1")
    try:
        value = float(raw)
    except ValueError:
        return 0.1
    if value < 0 or value > 2:
        return 0.1
    return value


def _default_webhook_timeout_seconds() -> float:
    raw = os.getenv("WEBHOOK_TIMEOUT_SECONDS", "20")
    try:
        value = float(raw)
    except ValueError:
        return 20.0
    if value <= 0:
        return 20.0
    return value


def _default_max_rag_results() -> int:
    raw = os.getenv("MAX_RAG_RESULTS", "4")
    try:
        value = int(raw)
    except ValueError:
        return 4
    if value < 1:
        return 1
    if value > 20:
        return 20
    return value


def _default_rag_min_final_score() -> float:
    raw = os.getenv("RAG_MIN_FINAL_SCORE", "0.18")
    try:
        value = float(raw)
    except ValueError:
        return 0.18
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return value


def _default_trace_enabled() -> bool:
    raw = os.getenv("TRACE_ENABLED", "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _default_memory_policy() -> str:
    raw = os.getenv("MEMORY_POLICY", "balanced").strip().lower()
    if raw in MEMORY_POLICIES:
        return raw
    return "balanced"


def _default_tool_http_allowlist() -> list[str]:
    raw = os.getenv("TOOL_HTTP_ALLOWLIST", "").strip()
    if not raw:
        return []
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _default_mcp_gateway_url() -> str | None:
    raw = os.getenv("MCP_GATEWAY_URL", "").strip()
    return raw or None


def _default_enabled_providers() -> list[str]:
    return ["utility", "rag", "http_api", "webhook", "mcp", "web_search"]


@dataclass
class AppConfig:
    openai_api_key: str | None = None
    model: str = field(default_factory=_default_model)
    embedding_model: str = field(default_factory=_default_embedding_model)
    reasoning_level: str = field(default_factory=_default_reasoning_level)
    temperature: float = field(default_factory=_default_temperature)
    rag_index_path: str = str(DEFAULT_RAG_INDEX_PATH)
    enabled_providers: list[str] = field(default_factory=_default_enabled_providers)
    mcp_gateway_url: str | None = field(default_factory=_default_mcp_gateway_url)
    webhook_timeout_seconds: float = field(default_factory=_default_webhook_timeout_seconds)
    max_rag_results: int = field(default_factory=_default_max_rag_results)
    rag_min_final_score: float = field(default_factory=_default_rag_min_final_score)
    trace_enabled: bool = field(default_factory=_default_trace_enabled)
    memory_policy: str = field(default_factory=_default_memory_policy)
    tool_http_allowlist: list[str] = field(default_factory=_default_tool_http_allowlist)

    @classmethod
    def load(cls, config_path: Path = DEFAULT_CONFIG_PATH) -> "AppConfig":
        if not config_path.exists():
            return cls()

        raw = json.loads(config_path.read_text(encoding="utf-8"))
        return cls(
            openai_api_key=raw.get("openai_api_key"),
            model=raw.get("model", _default_model()),
            embedding_model=raw.get("embedding_model", _default_embedding_model()),
            reasoning_level=normalize_reasoning_level(raw.get("reasoning_level")),
            temperature=float(raw.get("temperature", _default_temperature())),
            rag_index_path=raw.get("rag_index_path", str(DEFAULT_RAG_INDEX_PATH)),
            enabled_providers=list(raw.get("enabled_providers", _default_enabled_providers())),
            mcp_gateway_url=raw.get("mcp_gateway_url", _default_mcp_gateway_url()),
            webhook_timeout_seconds=float(
                raw.get("webhook_timeout_seconds", _default_webhook_timeout_seconds())
            ),
            max_rag_results=int(raw.get("max_rag_results", _default_max_rag_results())),
            rag_min_final_score=float(raw.get("rag_min_final_score", _default_rag_min_final_score())),
            trace_enabled=bool(raw.get("trace_enabled", _default_trace_enabled())),
            memory_policy=str(raw.get("memory_policy", _default_memory_policy())).strip().lower(),
            tool_http_allowlist=list(
                raw.get("tool_http_allowlist", _default_tool_http_allowlist())
            ),
        )

    def save(self, config_path: Path = DEFAULT_CONFIG_PATH) -> None:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "openai_api_key": self.openai_api_key,
            "model": self.model,
            "embedding_model": self.embedding_model,
            "reasoning_level": normalize_reasoning_level(self.reasoning_level),
            "temperature": self.temperature,
            "rag_index_path": self.rag_index_path,
            "enabled_providers": self.enabled_providers,
            "mcp_gateway_url": self.mcp_gateway_url,
            "webhook_timeout_seconds": self.webhook_timeout_seconds,
            "max_rag_results": self.max_rag_results,
            "rag_min_final_score": self.rag_min_final_score,
            "trace_enabled": self.trace_enabled,
            "memory_policy": self.memory_policy,
            "tool_http_allowlist": self.tool_http_allowlist,
        }
        config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def resolved_openai_api_key(self) -> str | None:
        return self.openai_api_key or os.getenv("OPENAI_API_KEY")
