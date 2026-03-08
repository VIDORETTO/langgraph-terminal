from __future__ import annotations

from pathlib import Path

from langgraph_terminal.runtime import ApplicationRuntime


def _build_runtime(tmp_path: Path, monkeypatch) -> ApplicationRuntime:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runtime = ApplicationRuntime(
        root_dir=tmp_path,
        config_path=tmp_path / ".terminal_agent" / "config.json",
        plugin_dir=tmp_path / "plugins",
    )
    return runtime


def test_set_model_rejects_empty_value(tmp_path: Path, monkeypatch) -> None:
    runtime = _build_runtime(tmp_path, monkeypatch)
    runtime.config.model = "gpt-4.1-mini"
    called = 0

    def fake_persist() -> None:
        nonlocal called
        called += 1

    runtime._persist_and_rebuild = fake_persist  # type: ignore[method-assign]
    message = runtime.set_model("   ")

    assert message == "Invalid model. Provide a non-empty model name."
    assert runtime.config.model == "gpt-4.1-mini"
    assert called == 0


def test_set_embedding_model_rejects_empty_value(tmp_path: Path, monkeypatch) -> None:
    runtime = _build_runtime(tmp_path, monkeypatch)
    runtime.config.embedding_model = "text-embedding-3-small"
    called = 0

    def fake_persist() -> None:
        nonlocal called
        called += 1

    runtime._persist_and_rebuild = fake_persist  # type: ignore[method-assign]
    message = runtime.set_embedding_model("   ")

    assert message == "Invalid embedding model. Provide a non-empty embedding model name."
    assert runtime.config.embedding_model == "text-embedding-3-small"
    assert called == 0


def test_set_model_updates_and_persists(tmp_path: Path, monkeypatch) -> None:
    runtime = _build_runtime(tmp_path, monkeypatch)
    called = 0

    def fake_persist() -> None:
        nonlocal called
        called += 1

    runtime._persist_and_rebuild = fake_persist  # type: ignore[method-assign]
    message = runtime.set_model("gpt-5-mini")

    assert message == "Model updated to gpt-5-mini."
    assert runtime.config.model == "gpt-5-mini"
    assert called == 1


def test_set_memory_policy_rejects_invalid(tmp_path: Path, monkeypatch) -> None:
    runtime = _build_runtime(tmp_path, monkeypatch)
    message = runtime.set_memory_policy("invalid")
    assert "Invalid memory policy" in message


def test_set_trace_enabled_accepts_on_off(tmp_path: Path, monkeypatch) -> None:
    runtime = _build_runtime(tmp_path, monkeypatch)
    assert runtime.set_trace_enabled("on") == "Trace enabled."
    assert runtime.config.trace_enabled is True
    assert runtime.set_trace_enabled("off") == "Trace disabled."
    assert runtime.config.trace_enabled is False


def test_history_and_retry_without_turns(tmp_path: Path, monkeypatch) -> None:
    runtime = _build_runtime(tmp_path, monkeypatch)
    assert runtime.retry_last_user_message() == "No previous user message to retry."
    assert "No conversation history yet." == runtime.history_text(10)


def test_set_mcp_gateway_rejects_invalid_url(tmp_path: Path, monkeypatch) -> None:
    runtime = _build_runtime(tmp_path, monkeypatch)
    runtime.config.mcp_gateway_url = "http://localhost:8080"
    called = 0

    def fake_persist() -> None:
        nonlocal called
        called += 1

    runtime._persist_and_rebuild = fake_persist  # type: ignore[method-assign]
    message = runtime.set_mcp_gateway("localhost:8080")

    assert "Invalid MCP gateway URL" in message
    assert runtime.config.mcp_gateway_url == "http://localhost:8080"
    assert called == 0


def test_set_mcp_gateway_normalizes_invoke_suffix(tmp_path: Path, monkeypatch) -> None:
    runtime = _build_runtime(tmp_path, monkeypatch)
    called = 0

    def fake_persist() -> None:
        nonlocal called
        called += 1

    runtime._persist_and_rebuild = fake_persist  # type: ignore[method-assign]
    message = runtime.set_mcp_gateway("https://gateway.local/invoke")

    assert message == "MCP gateway updated: https://gateway.local"
    assert runtime.config.mcp_gateway_url == "https://gateway.local"
    assert called == 1
