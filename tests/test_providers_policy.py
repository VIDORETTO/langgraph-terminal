from __future__ import annotations

from langgraph_terminal.tools.providers import (
    _is_allowed_host,
    _looks_durable_memory,
    _normalize_mcp_tools_payload,
    _parse_duckduckgo_html_results,
)


def test_is_allowed_host_with_allowlist() -> None:
    allowlist = ["api.example.com", "hooks.example.com"]
    assert _is_allowed_host("https://api.example.com/v1/data", allowlist)
    assert not _is_allowed_host("https://evil.example.net/collect", allowlist)


def test_is_allowed_host_without_allowlist() -> None:
    assert _is_allowed_host("https://anywhere.example.org", [])


def test_looks_durable_memory_strict_heuristic() -> None:
    assert _looks_durable_memory("Project deadline is March 31 and we always deploy on Friday.")
    assert not _looks_durable_memory("ok thanks")


def test_parse_duckduckgo_html_results() -> None:
    html = """
    <div class="result">
      <h2 class="result__title">
        <a class="result__a" href="https://example.com/a">Alpha Result</a>
      </h2>
      <a class="result__snippet">Snippet A</a>
    </div>
    <div class="result">
      <h2 class="result__title">
        <a class="result__a" href="https://example.com/b">Beta Result</a>
      </h2>
      <div class="result__snippet">Snippet B</div>
    </div>
    """
    parsed = _parse_duckduckgo_html_results(html, k=5)
    assert parsed == [
        {"title": "Alpha Result", "url": "https://example.com/a", "snippet": "Snippet A"},
        {"title": "Beta Result", "url": "https://example.com/b", "snippet": "Snippet B"},
    ]


def test_normalize_mcp_tools_payload_from_tools_key() -> None:
    payload = {
        "tools": [
            {"name": "search_docs", "description": "Searches docs", "server": "docs"},
            {"name": "ping", "description": "Checks health"},
        ]
    }
    normalized = _normalize_mcp_tools_payload(payload, server_hint="default")
    assert normalized == [
        {"server": "docs", "name": "search_docs", "description": "Searches docs"},
        {"server": "default", "name": "ping", "description": "Checks health"},
    ]


def test_normalize_mcp_tools_payload_from_server_map() -> None:
    payload = {
        "result": {
            "crm": [{"name": "find_customer", "description": "Find by e-mail"}],
            "calendar": [{"name": "create_event"}],
        }
    }
    normalized = _normalize_mcp_tools_payload(payload)
    assert normalized == [
        {"server": "crm", "name": "find_customer", "description": "Find by e-mail"},
        {"server": "calendar", "name": "create_event", "description": ""},
    ]
