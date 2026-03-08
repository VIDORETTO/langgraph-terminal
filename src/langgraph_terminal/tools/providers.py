from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from langgraph_terminal.rag.store import MEMORY_SOURCE_PREFIX
from langgraph_terminal.tools.contracts import ToolContext


def _truncate(value: str, size: int = 3500) -> str:
    if len(value) <= size:
        return value
    return f"{value[:size]}...[truncated]"


RAG_MAX_CHARS_PER_CHUNK = 1800
RAG_MAX_TOTAL_CONTEXT_CHARS = 12000
_QUERY_STOPWORDS = {
    "a",
    "o",
    "de",
    "da",
    "do",
    "e",
    "em",
    "para",
    "por",
    "the",
    "and",
    "of",
    "to",
    "in",
    "on",
    "is",
}


def _query_variants(query: str) -> list[str]:
    normalized = query.strip()
    if not normalized:
        return []

    tokens = [t for t in re.findall(r"[A-Za-z0-9À-ÿ]{2,}", normalized.lower())]
    no_stop = [t for t in tokens if t not in _QUERY_STOPWORDS]
    ranked = sorted(no_stop, key=lambda item: len(item), reverse=True)
    keyword_focus = " ".join(ranked[:8]).strip()
    compact = " ".join(no_stop).strip()

    variants: list[str] = [normalized]
    if compact and compact != normalized.lower():
        variants.append(compact)
    if keyword_focus and keyword_focus not in variants:
        variants.append(keyword_focus)
    return variants[:3]


def _metadata_float(metadata: dict[str, str] | None, key: str) -> float:
    if not metadata:
        return 0.0
    raw = metadata.get(key)
    if raw is None:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _is_allowed_host(url: str, allowlist: list[str]) -> bool:
    if not allowlist:
        return True
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False
    return host in set(allowlist)


def _strip_html_tags(value: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", value)
    return " ".join(no_tags.split())


def _normalize_search_result_url(raw_url: str) -> str:
    cleaned = raw_url.strip()
    if not cleaned:
        return ""
    parsed = urlparse(cleaned)
    if parsed.path.startswith("/l/"):
        query = parse_qs(parsed.query)
        encoded = query.get("uddg", [])
        if encoded:
            return unquote(encoded[0])
    return cleaned


def _parse_duckduckgo_html_results(html: str, k: int) -> list[dict[str, str]]:
    anchor_pattern = re.compile(
        r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        flags=re.S,
    )
    snippet_pattern = re.compile(
        r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>|'
        r'<div[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>',
        flags=re.S,
    )
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    anchors = list(anchor_pattern.finditer(html))
    for index, anchor in enumerate(anchors):
        url = _normalize_search_result_url(anchor.group(1))
        if not url or url in seen_urls:
            continue

        title = _strip_html_tags(anchor.group(2))
        next_start = anchors[index + 1].start() if index + 1 < len(anchors) else len(html)
        segment = html[anchor.end() : next_start]
        snippet_match = snippet_pattern.search(segment)
        snippet_raw = ""
        if snippet_match:
            snippet_raw = snippet_match.group(1) or snippet_match.group(2) or ""
        snippet = _strip_html_tags(snippet_raw)

        seen_urls.add(url)
        results.append({"title": title or "(untitled)", "url": url, "snippet": snippet})
        if len(results) >= k:
            break

    return results


class UtilityToolProvider:
    name = "utility"
    description = "Utility tools for date, time and diagnostics."

    def build_tools(self, context: ToolContext) -> list[BaseTool]:
        def current_datetime() -> str:
            now = datetime.now(timezone.utc).astimezone()
            return f"Current datetime: {now.isoformat()}"

        def list_enabled_tool_providers() -> str:
            return ", ".join(context.config.enabled_providers)

        return [
            StructuredTool.from_function(
                func=current_datetime,
                name="current_datetime",
                description="Returns current date and time in ISO format.",
            ),
            StructuredTool.from_function(
                func=list_enabled_tool_providers,
                name="list_enabled_tool_providers",
                description="Lists enabled tool provider names.",
            ),
        ]


class HttpRequestInput(BaseModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = Field(
        default="GET", description="HTTP method."
    )
    url: str = Field(description="Target URL.")
    headers: dict[str, str] | None = Field(default=None, description="Optional headers.")
    query_params: dict[str, str] | None = Field(
        default=None, description="Optional query string parameters."
    )
    body: str | None = Field(default=None, description="Optional request body.")


class HttpApiToolProvider:
    name = "http_api"
    description = "Generic HTTP API access for external systems."

    def build_tools(self, context: ToolContext) -> list[BaseTool]:
        def http_api_request(
            method: str = "GET",
            url: str = "",
            headers: dict[str, str] | None = None,
            query_params: dict[str, str] | None = None,
            body: str | None = None,
        ) -> str:
            if not _is_allowed_host(url, context.config.tool_http_allowlist):
                return (
                    f"HTTP request blocked by allowlist policy for URL: {url}. "
                    "Use /http-allowlist to allow this host."
                )
            try:
                timeout = context.config.webhook_timeout_seconds
                request_headers = headers or {}
                request_params = query_params or {}
                with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                    response = client.request(
                        method=method.upper(),
                        url=url,
                        headers=request_headers,
                        params=request_params,
                        content=body.encode("utf-8") if body else None,
                    )
            except Exception as exc:  # noqa: BLE001 - tool should return user-readable errors
                return f"HTTP request failed: {exc}"

            compact_headers = {
                key: value
                for key, value in response.headers.items()
                if key.lower() in {"content-type", "content-length", "x-request-id"}
            }
            payload = _truncate(response.text)
            return (
                f"HTTP {response.status_code}\n"
                f"Headers: {json.dumps(compact_headers)}\n"
                f"Body:\n{payload}"
            )

        return [
            StructuredTool.from_function(
                func=http_api_request,
                name="http_api_request",
                description=(
                    "Performs generic HTTP requests. Use for REST APIs, webhooks or"
                    " external HTTP integrations."
                ),
                args_schema=HttpRequestInput,
            )
        ]


class WebhookInput(BaseModel):
    url: str = Field(description="Webhook URL.")
    event_name: str = Field(default="generic_event", description="Event name.")
    payload: dict[str, Any] | None = Field(default=None, description="Event payload.")
    headers: dict[str, str] | None = Field(default=None, description="Optional headers.")


class WebhookToolProvider:
    name = "webhook"
    description = "Outbound webhook tool."

    def build_tools(self, context: ToolContext) -> list[BaseTool]:
        def send_webhook(
            url: str,
            event_name: str = "generic_event",
            payload: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None,
        ) -> str:
            if not _is_allowed_host(url, context.config.tool_http_allowlist):
                return (
                    f"Webhook blocked by allowlist policy for URL: {url}. "
                    "Use /http-allowlist to allow this host."
                )
            try:
                timeout = context.config.webhook_timeout_seconds
                body = {
                    "event": event_name,
                    "payload": payload or {},
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                }
                request_headers = {"Content-Type": "application/json", **(headers or {})}

                with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                    response = client.post(url, json=body, headers=request_headers)
            except Exception as exc:  # noqa: BLE001 - tool should return user-readable errors
                return f"Webhook request failed: {exc}"

            response_text = _truncate(response.text)
            return (
                f"Webhook delivered with status {response.status_code}.\n"
                f"Response body:\n{response_text}"
            )

        return [
            StructuredTool.from_function(
                func=send_webhook,
                name="send_webhook",
                description=(
                    "Sends event payloads to webhook endpoints. Useful for automations"
                    " and external integrations."
                ),
                args_schema=WebhookInput,
            )
        ]


class MCPInvokeInput(BaseModel):
    server: str = Field(description="MCP server name.")
    tool_name: str = Field(description="MCP tool name to call.")
    arguments: dict[str, Any] | None = Field(default=None, description="Tool arguments.")


class MCPListToolsInput(BaseModel):
    server: str | None = Field(
        default=None,
        description=(
            "Optional MCP server name filter. Leave empty to list tools for all servers"
            " when supported by the gateway."
        ),
    )


class WebSearchInput(BaseModel):
    query: str = Field(description="Search query for up-to-date or external information.")
    k: int = Field(default=5, ge=1, le=10, description="Maximum number of search results.")
    region: str = Field(
        default="wt-wt",
        description="DuckDuckGo region code (for example: wt-wt, us-en, br-pt).",
    )


class MCPToolProvider:
    name = "mcp"
    description = "MCP gateway adapter for future tool ecosystems."

    def build_tools(self, context: ToolContext) -> list[BaseTool]:
        def list_mcp_tools(server: str | None = None) -> str:
            gateway_url = context.config.mcp_gateway_url
            if not gateway_url:
                return (
                    "MCP gateway is not configured. Set it with /mcp <url>."
                    " Expected base URL (without /invoke)."
                )

            base_url = gateway_url.rstrip("/")
            timeout = context.config.webhook_timeout_seconds
            server_value = (server or "").strip() or None
            attempts: list[str] = []

            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.get(
                        f"{base_url}/tools",
                        params={"server": server_value} if server_value else None,
                    )
                    attempts.append(f"GET /tools -> {response.status_code}")
                    tools = _extract_mcp_tools(response, server_value)
                    if tools:
                        return _format_mcp_tools_output(
                            tools,
                            endpoint=f"{base_url}/tools",
                            status_code=response.status_code,
                        )

                    response = client.post(
                        f"{base_url}/tools",
                        json={"server": server_value} if server_value else {},
                    )
                    attempts.append(f"POST /tools -> {response.status_code}")
                    tools = _extract_mcp_tools(response, server_value)
                    if tools:
                        return _format_mcp_tools_output(
                            tools,
                            endpoint=f"{base_url}/tools",
                            status_code=response.status_code,
                        )

                    response = client.post(
                        f"{base_url}/list_tools",
                        json={"server": server_value} if server_value else {},
                    )
                    attempts.append(f"POST /list_tools -> {response.status_code}")
                    tools = _extract_mcp_tools(response, server_value)
                    if tools:
                        return _format_mcp_tools_output(
                            tools,
                            endpoint=f"{base_url}/list_tools",
                            status_code=response.status_code,
                        )
            except Exception as exc:  # noqa: BLE001 - tool should return user-readable errors
                return f"MCP tool discovery failed: {exc}"

            attempts_text = ", ".join(attempts) if attempts else "no attempts"
            return (
                "MCP gateway did not return a recognizable tools list. "
                f"Attempts: {attempts_text}"
            )

        def invoke_mcp_tool(
            server: str,
            tool_name: str,
            arguments: dict[str, Any] | None = None,
        ) -> str:
            gateway_url = context.config.mcp_gateway_url
            if not gateway_url:
                return (
                    "MCP gateway is not configured. Set it with /mcp <url>."
                    " Expected endpoint: <gateway>/invoke"
                )

            endpoint = f"{gateway_url.rstrip('/')}/invoke"
            payload = {"server": server, "tool_name": tool_name, "arguments": arguments or {}}
            timeout = context.config.webhook_timeout_seconds

            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.post(endpoint, json=payload)
            except Exception as exc:  # noqa: BLE001 - tool should return user-readable errors
                return f"MCP request failed: {exc}"

            body_text = _response_as_text(response)

            return (
                f"MCP gateway status: {response.status_code}\n"
                f"Endpoint: {endpoint}\n"
                f"Body:\n{_truncate(body_text)}"
            )

        return [
            StructuredTool.from_function(
                func=list_mcp_tools,
                name="list_mcp_tools",
                description=(
                    "Discovers MCP tools available in the configured gateway."
                    " Use this before invoke_mcp_tool when you do not know"
                    " exact server/tool names."
                ),
                args_schema=MCPListToolsInput,
            ),
            StructuredTool.from_function(
                func=invoke_mcp_tool,
                name="invoke_mcp_tool",
                description=(
                    "Calls tools through an MCP-compatible gateway endpoint."
                    " Call list_mcp_tools first whenever tool names are unknown."
                ),
                args_schema=MCPInvokeInput,
            )
        ]


class WebSearchToolProvider:
    name = "web_search"
    description = "Internet search provider for external and up-to-date information."

    def build_tools(self, context: ToolContext) -> list[BaseTool]:
        def web_search(query: str, k: int = 5, region: str = "wt-wt") -> str:
            normalized_query = query.strip()
            if not normalized_query:
                return "Invalid search query."

            endpoint = "https://html.duckduckgo.com/html/"
            if not _is_allowed_host(endpoint, context.config.tool_http_allowlist):
                return (
                    "Web search blocked by allowlist policy for host: html.duckduckgo.com. "
                    "Use /http-allowlist to allow this host."
                )

            limited_k = max(1, min(k, 10))
            timeout = context.config.webhook_timeout_seconds
            headers = {"User-Agent": "langgraph-terminal-ui/1.0 (+web_search)"}
            params = {"q": normalized_query, "kl": region.strip() or "wt-wt"}

            try:
                with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
                    response = client.get(endpoint, params=params)
            except Exception as exc:  # noqa: BLE001 - tool should return user-readable errors
                return f"Web search request failed: {exc}"

            if response.status_code >= 400:
                return f"Web search failed with HTTP {response.status_code}."

            results = _parse_duckduckgo_html_results(response.text, limited_k)
            if not results:
                return "No web search results found."

            lines = [f"Web Search Results ({len(results)}):"]
            for idx, item in enumerate(results, start=1):
                lines.append(
                    f"{idx}. title={item['title']}\n"
                    f"url={item['url']}\n"
                    f"snippet={item['snippet']}"
                )
            return "\n\n".join(lines)

        return [
            StructuredTool.from_function(
                func=web_search,
                name="web_search",
                description=(
                    "Searches the web using DuckDuckGo HTML results. "
                    "Use when local RAG/memory is insufficient or when up-to-date external facts are needed."
                ),
                args_schema=WebSearchInput,
            )
        ]


class RAGSearchInput(BaseModel):
    query: str = Field(description="Question or search query.")
    k: int = Field(default=4, ge=1, le=10, description="Number of passages to return.")


class MemorySaveInput(BaseModel):
    fact: str = Field(
        description=(
            "One concise, standalone fact to persist for future conversations."
            " Include only useful long-term context."
        )
    )
    topic: str | None = Field(
        default="general",
        description="Topic label to organize memory (for example: profile, project, preference).",
    )
    importance: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Memory importance level.",
    )


class MemorySearchInput(BaseModel):
    query: str = Field(description="What you are trying to remember from past conversations.")
    k: int = Field(default=4, ge=1, le=10, description="Number of memory snippets to return.")


class MemoryListInput(BaseModel):
    limit: int = Field(default=8, ge=1, le=30, description="Maximum memories to list.")


class RAGToolProvider:
    name = "rag"
    description = "RAG retrieval and persistent memory tools backed by OpenAI embeddings."

    def build_tools(self, context: ToolContext) -> list[BaseTool]:
        def search_knowledge_base(query: str, k: int = 4) -> str:
            store = context.rag_store
            if store is None:
                return "RAG index is unavailable. Configure OPENAI key first."

            limited_k = min(k, context.config.max_rag_results)
            variants = _query_variants(query)
            if not variants:
                return "Invalid query."

            merged: dict[str, tuple[Any, float]] = {}
            for variant in variants:
                variant_results = store.search_hybrid(
                    variant,
                    k=max(limited_k * 2, 6),
                    exclude_source_prefix=MEMORY_SOURCE_PREFIX,
                )
                for item in variant_results:
                    metadata = item.metadata or {}
                    chunk_id = metadata.get("chunk_id")
                    dedupe_key = chunk_id or f"{item.source}::{hash(item.content)}"
                    existing = merged.get(dedupe_key)
                    if existing is None or item.score > existing[1]:
                        merged[dedupe_key] = (item, item.score)

            ranked_results = sorted(
                (entry[0] for entry in merged.values()),
                key=lambda result: result.score,
                reverse=True,
            )[:limited_k]

            results = ranked_results
            if not results:
                return "No relevant chunks found in indexed documents."
            top_score = results[0].score
            if top_score < context.config.rag_min_final_score:
                return (
                    "Low-confidence retrieval: indexed documents do not provide enough support for "
                    f"this query (top score {top_score:.3f} < threshold {context.config.rag_min_final_score:.3f})."
                )

            lines: list[str] = []
            consumed_chars = 0
            for idx, item in enumerate(results, start=1):
                metadata = item.metadata or {}
                chunk_id = metadata.get("chunk_id", "unknown")
                vector_score = _metadata_float(metadata, "vector_score")
                lexical_score = _metadata_float(metadata, "lexical_score")
                final_score = _metadata_float(metadata, "final_score") or item.score
                normalized = item.content.strip().replace("\n", " ")
                remaining = RAG_MAX_TOTAL_CONTEXT_CHARS - consumed_chars
                if remaining <= 0:
                    break
                chunk_limit = min(RAG_MAX_CHARS_PER_CHUNK, remaining)
                content = _truncate(normalized, size=chunk_limit)
                consumed_chars += min(len(normalized), chunk_limit)
                lines.append(
                    f"{idx}. source={item.source} chunk_id={chunk_id}\n"
                    f"scores: final={final_score:.3f} vector={vector_score:.3f} lexical={lexical_score:.3f}\n"
                    f"context: {content}"
                )
            if consumed_chars >= RAG_MAX_TOTAL_CONTEXT_CHARS:
                lines.append("[context truncated by global RAG limit]")
            return "\n\n".join(lines)

        def save_relevant_memory(
            fact: str,
            topic: str | None = "general",
            importance: str = "medium",
        ) -> str:
            store = context.rag_store
            if store is None:
                return "Memory store unavailable. Configure OPENAI key first."
            if context.config.memory_policy == "off":
                return "Memory skipped: memory policy is off."

            normalized_fact = fact.strip()
            if len(normalized_fact) < 8:
                return "Memory skipped: fact too short."
            if context.config.memory_policy == "strict" and not _looks_durable_memory(normalized_fact):
                return "Memory skipped: strict policy requires explicit durable context."

            lowered = normalized_fact.lower()
            blocked_markers = ("api key", "token", "password", "senha", "secret")
            if any(marker in lowered for marker in blocked_markers):
                return "Memory skipped: sensitive credential-like content."

            try:
                source = store.add_memory(normalized_fact, topic=topic, importance=importance)
            except Exception as exc:  # noqa: BLE001 - tool should return user-readable errors
                return f"Could not save memory: {exc}"
            return f"Memory saved at {source}"

        def search_conversation_memory(query: str, k: int = 4) -> str:
            store = context.rag_store
            if store is None:
                return "Memory store unavailable. Configure OPENAI key first."

            limited_k = min(k, context.config.max_rag_results)
            results = store.search(
                query,
                k=limited_k,
                source_prefix=MEMORY_SOURCE_PREFIX,
                min_score=0.12,
            )
            if not results:
                return "No relevant memories found."

            lines: list[str] = []
            for idx, item in enumerate(results, start=1):
                metadata = item.metadata or {}
                topic = metadata.get("topic", "general")
                importance = metadata.get("importance", "medium")
                snippet = _truncate(item.content.replace("\n", " "), size=420)
                lines.append(
                    f"{idx}. topic={topic} importance={importance} score={item.score:.3f}\n"
                    f"memory: {snippet}"
                )
            return "\n\n".join(lines)

        def list_recent_memories(limit: int = 8) -> str:
            store = context.rag_store
            if store is None:
                return "Memory store unavailable. Configure OPENAI key first."
            records = store.list_memories(limit=limit)
            if not records:
                return "No memories stored."

            lines: list[str] = []
            for idx, record in enumerate(records, start=1):
                topic = record.metadata.get("topic", "general")
                importance = record.metadata.get("importance", "medium")
                created_at = record.metadata.get("created_at", "unknown")
                snippet = _truncate(record.content.replace("\n", " "), size=280)
                lines.append(
                    f"{idx}. topic={topic} importance={importance} created_at={created_at}\n"
                    f"source={record.source}\n"
                    f"memory: {snippet}"
                )
            return "\n\n".join(lines)

        return [
            StructuredTool.from_function(
                func=search_knowledge_base,
                name="search_knowledge_base",
                description=(
                    "Searches local indexed documents using OpenAI embeddings."
                    " Use this when user asks about uploaded documents."
                ),
                args_schema=RAGSearchInput,
            ),
            StructuredTool.from_function(
                func=save_relevant_memory,
                name="save_relevant_memory",
                description=(
                    "Persist a relevant long-term fact from the conversation."
                    " Use this when user shares durable preferences, profile, goals,"
                    " project constraints, decisions, or recurring context."
                ),
                args_schema=MemorySaveInput,
            ),
            StructuredTool.from_function(
                func=search_conversation_memory,
                name="search_conversation_memory",
                description=(
                    "Searches persistent conversation memories."
                    " Use before answering when user references prior context,"
                    " preferences, plans, or continuity."
                ),
                args_schema=MemorySearchInput,
            ),
            StructuredTool.from_function(
                func=list_recent_memories,
                name="list_recent_memories",
                description="Lists recently stored persistent memories.",
                args_schema=MemoryListInput,
            ),
        ]


def _looks_durable_memory(fact: str) -> bool:
    lowered = fact.strip().lower()
    if len(lowered) < 20:
        return False
    markers = (
        "prefer",
        "always",
        "never",
        "goal",
        "deadline",
        "project",
        "environment",
        "constraint",
        "decided",
        "prefiro",
        "projeto",
        "prazo",
        "meta",
        "restri",
    )
    return any(marker in lowered for marker in markers)


def _response_as_text(response: httpx.Response) -> str:
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type.lower():
        try:
            return json.dumps(response.json(), indent=2, ensure_ascii=False)
        except ValueError:
            return response.text
    return response.text


def _extract_mcp_tools(
    response: httpx.Response,
    server_hint: str | None = None,
) -> list[dict[str, str]]:
    if response.status_code >= 400:
        return []

    payload: Any
    try:
        payload = response.json()
    except ValueError:
        return []
    return _normalize_mcp_tools_payload(payload, server_hint=server_hint)


def _normalize_mcp_tools_payload(
    payload: Any,
    server_hint: str | None = None,
) -> list[dict[str, str]]:
    records = payload
    if isinstance(records, dict):
        for key in ("tools", "result", "data", "items"):
            candidate = records.get(key)
            if candidate is not None:
                records = candidate
                break

    if isinstance(records, dict):
        # Some gateways return {"serverA": [...], "serverB": [...]}.
        merged: list[dict[str, Any]] = []
        for server_name, items in records.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    merged.append({"server": str(server_name), **item})
        records = merged

    if not isinstance(records, list):
        return []

    normalized: list[dict[str, str]] = []
    for item in records:
        if isinstance(item, str):
            name = item.strip()
            if name:
                normalized.append(
                    {
                        "server": server_hint or "unknown",
                        "name": name,
                        "description": "",
                    }
                )
            continue

        if not isinstance(item, dict):
            continue

        name = str(item.get("name", "")).strip()
        if not name:
            continue
        server = str(item.get("server", "")).strip() or (server_hint or "unknown")
        description = str(item.get("description", "")).strip()
        normalized.append({"server": server, "name": name, "description": description})
    return normalized


def _format_mcp_tools_output(
    tools: list[dict[str, str]],
    endpoint: str,
    status_code: int,
) -> str:
    lines = [
        f"MCP tools discovered: {len(tools)}",
        f"Endpoint: {endpoint}",
        f"Status: {status_code}",
    ]
    for idx, tool in enumerate(tools[:30], start=1):
        description = tool.get("description") or "-"
        lines.append(
            f"{idx}. server={tool.get('server', 'unknown')} tool={tool.get('name', 'unknown')}\n"
            f"   description={_truncate(description, size=240)}"
        )
    if len(tools) > 30:
        lines.append(f"... truncated {len(tools) - 30} additional tools")
    return "\n".join(lines)
