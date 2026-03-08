from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage

from langgraph_terminal.graph.agent_service import (
    _append_sources_block,
    _extract_rag_sources,
    _extract_tool_calls,
    _extract_web_sources,
    _strip_inline_sources_sections,
)


def test_extract_tool_calls_from_ai_messages() -> None:
    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "search_knowledge_base", "args": {"query": "x"}, "id": "1", "type": "tool_call"},
                {"name": "search_conversation_memory", "args": {"query": "y"}, "id": "2", "type": "tool_call"},
            ],
        )
    ]
    names = _extract_tool_calls(messages)
    assert names == ["search_knowledge_base", "search_conversation_memory"]


def test_extract_rag_sources_from_tool_messages() -> None:
    messages = [
        ToolMessage(
            name="search_knowledge_base",
            tool_call_id="1",
            content="1. source=C:/docs/a.md chunk_id=a\ncontext: ...\n2. source=C:/docs/b.md chunk_id=b\ncontext: ...",
        )
    ]
    sources = _extract_rag_sources(messages)
    assert sources == ["C:/docs/a.md", "C:/docs/b.md"]


def test_extract_web_sources_from_tool_messages() -> None:
    messages = [
        ToolMessage(
            name="web_search",
            tool_call_id="1",
            content=(
                "Web Search Results (2):\n\n"
                "1. title=Result A\n"
                "url=https://example.com/a\n"
                "snippet=...\n\n"
                "2. title=Result B\n"
                "url=https://example.com/b\n"
                "snippet=..."
            ),
        )
    ]
    sources = _extract_web_sources(messages)
    assert sources == [("Result A", "https://example.com/a"), ("Result B", "https://example.com/b")]


def test_append_sources_block_rag_and_web() -> None:
    body = "Resposta final"
    text = _append_sources_block(
        body,
        ["C:/docs/a.md"],
        [("Site A", "https://example.com/a")],
    )
    assert text.endswith("https://example.com/a")
    assert "\n\nFontes:\n1. C:/docs/a.md\n   C:/docs/a.md\n2. Site A\n   https://example.com/a" in text


def test_strip_inline_sources_sections() -> None:
    text = "Resposta\n\nSources: abc, def"
    cleaned = _strip_inline_sources_sections(text)
    assert cleaned == "Resposta"
