from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from langgraph_terminal.config import AppConfig
from langgraph_terminal.reasoning import (
    build_reasoning_prompt_block,
    describe_reasoning_mode,
    native_reasoning_kwargs,
    normalize_reasoning_level,
)

BASE_SYSTEM_PROMPT = """You are my personal assistant and you help me across many areas of my life, regardless of the topic.
Your role is to support planning, learning, decisions, productivity, personal organization, and practical problem-solving.

Memory and context policy:
- Treat vectorized memory and indexed documents as important context for continuity.
- I will try to keep as much information as possible vectorized to make your work easier.
- Evaluate each user message for durable facts that can help future conversations.
- Durable facts include preferences, profile data, project constraints, decisions, recurring tasks,
  deadlines, environment details, and ongoing goals.
- When a durable fact appears, call save_relevant_memory before your final answer.
- When the user references prior context or related topics, call search_conversation_memory before answering.
- Do not store credentials, secrets, or highly sensitive data.

Knowledge and retrieval policy:
- Always call search_knowledge_base before claiming information is absent from indexed documents.
- If only part of the requested information is found, explicitly say it is partial and list what is missing.
- Do not make categorical statements without retrieval evidence.
- Say when context is missing or uncertain.
- Avoid fabricating details.

Internet/tool policy:
- Use RAG/memory first; call web_search only when local context is missing, insufficient, or stale.
- When necessary for up-to-date or external information, use web_search.
- For MCP tasks, call list_mcp_tools first when server/tool names are unknown, then call invoke_mcp_tool.
- If such tool is unavailable in the current toolset, state that limitation clearly and proceed with best effort.
- Do not put citations in the middle of the answer body.
- Provide one final section titled "Fontes" at the end with all sources used.

Keep answers concise, practical, and actionable."""


@dataclass
class AgentResponse:
    text: str
    tool_calls: list[str]
    rag_hits: int
    memory_hits: int
    error: str | None = None


class AgentService:
    def __init__(self, config: AppConfig, tools: list[BaseTool]) -> None:
        api_key = config.resolved_openai_api_key()
        if not api_key:
            raise ValueError("OpenAI API key is missing.")

        reasoning_level = normalize_reasoning_level(config.reasoning_level)
        reasoning_kwargs = native_reasoning_kwargs(config.model, reasoning_level)
        system_prompt = _build_system_prompt(
            config.model,
            reasoning_level,
            memory_policy=config.memory_policy,
        )

        model = ChatOpenAI(
            model=config.model,
            api_key=api_key,
            temperature=config.temperature,
            **reasoning_kwargs,
        )
        self.tool_count = len(tools)
        self.reasoning_mode = describe_reasoning_mode(config.model, reasoning_level)
        self._graph = create_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
        )

    def ask(
        self,
        user_message: str,
        thread_id: str = "terminal-main",
        history: list[tuple[str, str]] | None = None,
    ) -> AgentResponse:
        _ = thread_id  # kept for compatibility with existing runtime signature
        messages: list[tuple[str, str]] = []
        if history:
            for speaker, content in history:
                role = "assistant" if speaker == "assistant" else "user"
                messages.append((role, content))
        messages.append(("user", user_message))
        result = self._graph.invoke({"messages": messages})
        messages = result.get("messages", [])
        tool_calls = _extract_tool_calls(messages)
        rag_hits = sum(1 for item in tool_calls if item == "search_knowledge_base")
        memory_hits = sum(1 for item in tool_calls if item == "search_conversation_memory")
        rag_sources = _extract_rag_sources(messages)
        web_sources = _extract_web_sources(messages)
        text = _last_ai_text(messages)
        text = _strip_inline_sources_sections(text)
        text = _append_sources_block(text, rag_sources, web_sources)
        return AgentResponse(
            text=text,
            tool_calls=tool_calls,
            rag_hits=rag_hits,
            memory_hits=memory_hits,
        )


def _last_ai_text(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return _coerce_text_content(message.content)
    return "No assistant response was produced."


def _extract_tool_calls(messages: list[BaseMessage]) -> list[str]:
    names: list[str] = []
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls:
            name = str(call.get("name", "")).strip()
            if name:
                names.append(name)
    return names


def _extract_rag_sources(messages: list[BaseMessage]) -> list[str]:
    sources: list[str] = []
    pattern = re.compile(r"source=([^\s]+)")
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        if message.name != "search_knowledge_base":
            continue
        body = _coerce_text_content(message.content)
        for match in pattern.findall(body):
            candidate = match.strip().strip(",.;")
            if candidate and candidate not in sources:
                sources.append(candidate)
    return sources[:8]


def _extract_web_sources(messages: list[BaseMessage]) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    title_pattern = re.compile(r"title=(.*)")
    url_pattern = re.compile(r"url=([^\s]+)")

    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        if message.name != "web_search":
            continue

        body = _coerce_text_content(message.content)
        blocks = re.split(r"\n\s*\n", body)
        for block in blocks:
            title_match = title_pattern.search(block)
            url_match = url_pattern.search(block)
            if not url_match:
                continue
            url = url_match.group(1).strip().strip(",.;")
            if not _looks_like_url(url):
                continue
            if url in seen_urls:
                continue
            title = "Web result"
            if title_match:
                title_candidate = title_match.group(1).strip()
                if title_candidate:
                    title = title_candidate
            seen_urls.add(url)
            results.append((title, url))
            if len(results) >= 8:
                return results
    return results


def _looks_like_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _strip_inline_sources_sections(text: str) -> str:
    cleaned = re.sub(r"\n{0,2}(Sources|Fontes)\s*:\s*.+$", "", text, flags=re.I | re.S)
    return cleaned.strip()


def _append_sources_block(
    text: str,
    rag_sources: list[str],
    web_sources: list[tuple[str, str]],
) -> str:
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()

    for source in rag_sources:
        key = f"rag::{source}"
        if key in seen:
            continue
        seen.add(key)
        entries.append((source, source))
        if len(entries) >= 8:
            break

    if len(entries) < 8:
        for title, url in web_sources:
            key = f"web::{url}"
            if key in seen:
                continue
            seen.add(key)
            entries.append((title, url))
            if len(entries) >= 8:
                break

    if not entries:
        return text.strip()

    lines = [text.strip(), "", "Fontes:"]
    for idx, (label, target) in enumerate(entries, start=1):
        lines.append(f"{idx}. {label}")
        lines.append(f"   {target}")
    return "\n".join(lines).strip()


def _coerce_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        if parts:
            return "\n".join(parts)
    try:
        return json.dumps(content, ensure_ascii=False)
    except TypeError:
        return str(content)


def _build_system_prompt(model_name: str, reasoning_level: str, memory_policy: str = "balanced") -> str:
    reasoning_block = build_reasoning_prompt_block(model_name, reasoning_level)
    if memory_policy == "off":
        memory_block = (
            "Memory policy override:\n"
            "- auto-save memory is disabled\n"
            "- do not call save_relevant_memory unless user explicitly asks"
        )
    elif memory_policy == "strict":
        memory_block = (
            "Memory policy override:\n"
            "- save only explicit, durable long-term facts\n"
            "- skip transient details and uncertain assumptions"
        )
    else:
        memory_block = (
            "Memory policy override:\n"
            "- balanced memory persistence\n"
            "- save durable facts, skip ephemeral details"
        )
    return f"{BASE_SYSTEM_PROMPT}\n\n{memory_block}\n\n{reasoning_block}"
