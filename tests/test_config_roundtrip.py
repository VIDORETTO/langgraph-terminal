from __future__ import annotations

from pathlib import Path

from langgraph_terminal.config import AppConfig


def test_config_save_and_load_roundtrip(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config = AppConfig(
        openai_api_key="sk-test",
        model="gpt-5-mini",
        embedding_model="text-embedding-3-small",
        reasoning_level="xhigh",
        temperature=0.2,
        rag_index_path=".terminal_agent/rag_index.json",
        enabled_providers=["utility", "rag"],
        mcp_gateway_url="http://localhost:8080",
        webhook_timeout_seconds=15.0,
        max_rag_results=7,
        rag_min_final_score=0.24,
        trace_enabled=True,
        memory_policy="strict",
        tool_http_allowlist=["api.example.com", "hooks.example.com"],
    )
    config.save(config_path)

    loaded = AppConfig.load(config_path)

    assert loaded.openai_api_key == "sk-test"
    assert loaded.model == "gpt-5-mini"
    assert loaded.embedding_model == "text-embedding-3-small"
    assert loaded.reasoning_level == "xhigh"
    assert loaded.temperature == 0.2
    assert loaded.rag_index_path == ".terminal_agent/rag_index.json"
    assert loaded.enabled_providers == ["utility", "rag"]
    assert loaded.mcp_gateway_url == "http://localhost:8080"
    assert loaded.webhook_timeout_seconds == 15.0
    assert loaded.max_rag_results == 7
    assert loaded.rag_min_final_score == 0.24
    assert loaded.trace_enabled is True
    assert loaded.memory_policy == "strict"
    assert loaded.tool_http_allowlist == ["api.example.com", "hooks.example.com"]


def test_default_enabled_providers_include_web_search(tmp_path: Path) -> None:
    loaded = AppConfig.load(tmp_path / "missing-config.json")
    assert "web_search" in loaded.enabled_providers
