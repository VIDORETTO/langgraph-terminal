from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings

from langgraph_terminal.config import AppConfig, DEFAULT_CONFIG_PATH, MEMORY_POLICIES
from langgraph_terminal.graph import AgentResponse, AgentService
from langgraph_terminal.rag import OpenAIRAGStore
from langgraph_terminal.reasoning import (
    REASONING_LEVELS,
    describe_reasoning_mode,
    is_reasoning_level,
    normalize_reasoning_level,
)
from langgraph_terminal.tools import ToolRegistry


@dataclass
class TurnTrace:
    user_input: str
    response_preview: str
    model: str
    reasoning_level: str
    latency_ms: int
    tool_calls: list[str] = field(default_factory=list)
    rag_hits: int = 0
    memory_hits: int = 0
    error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ApplicationRuntime:
    """Coordinates config, tools, RAG index and LangGraph agent lifecycle."""

    def __init__(
        self,
        root_dir: Path | None = None,
        config_path: Path | None = None,
        plugin_dir: Path | None = None,
    ) -> None:
        load_dotenv(override=False)

        self.root_dir = (root_dir or Path.cwd()).resolve()
        self.config_path = (config_path or (self.root_dir / DEFAULT_CONFIG_PATH)).resolve()
        self.plugin_dir = (plugin_dir or (self.root_dir / "plugins")).resolve()

        self.registry = ToolRegistry()
        self.registry.register_defaults()
        self.loaded_plugins, self.plugin_errors = self.registry.load_plugins(self.plugin_dir)

        self.config = AppConfig.load(self.config_path)
        self._materialize_persistent_config()
        self.rag_store: OpenAIRAGStore | None = None
        self.agent: AgentService | None = None
        self.last_error: str | None = None
        self.last_latency_ms: int | None = None
        self.last_trace: TurnTrace | None = None
        self._sessions: dict[str, list[tuple[str, str]]] = {}
        self._session_order: list[str] = []
        self._session_counter = 0
        self._active_session_id = self._create_session()
        self._trace_path = self.root_dir / ".terminal_agent" / "traces.jsonl"
        self.rebuild_services()

    def rebuild_services(self) -> None:
        self.last_error = None
        self.agent = None
        self.rag_store = None

        api_key = self.config.resolved_openai_api_key()
        if not api_key:
            return

        try:
            rag_index_path = self._resolve_path(self.config.rag_index_path)
            embeddings = OpenAIEmbeddings(
                model=self.config.embedding_model,
                api_key=api_key,
            )
            self.rag_store = OpenAIRAGStore(rag_index_path, embeddings)
            self.rag_store.load()
            tools = self.registry.build_enabled_tools(self.config, self.rag_store)
            self.agent = AgentService(self.config, tools)
        except Exception as exc:  # noqa: BLE001 - runtime should not crash UI
            self.last_error = str(exc)
            self.agent = None

    def chat(self, user_message: str) -> str:
        started = perf_counter()
        if self.agent is None:
            latency_ms = int((perf_counter() - started) * 1000)
            self.last_latency_ms = latency_ms
            if self.last_error:
                answer = f"Runtime error: {self.last_error}"
                self._capture_trace(
                    TurnTrace(
                        user_input=user_message,
                        response_preview=_preview_text(answer),
                        model=self.config.model,
                        reasoning_level=self.config.reasoning_level,
                        latency_ms=latency_ms,
                        error=self.last_error,
                    )
                )
                self._append_history(user_message, answer)
                return answer
            answer = "OpenAI key not configured. Use command /key <OPENAI_API_KEY>."
            self._capture_trace(
                TurnTrace(
                    user_input=user_message,
                    response_preview=_preview_text(answer),
                    model=self.config.model,
                    reasoning_level=self.config.reasoning_level,
                    latency_ms=latency_ms,
                )
            )
            self._append_history(user_message, answer)
            return answer

        response: AgentResponse = self.agent.ask(
            user_message,
            thread_id=self._active_session_id,
            history=self._active_history(),
        )
        latency_ms = int((perf_counter() - started) * 1000)
        self.last_latency_ms = latency_ms
        self._append_history(user_message, response.text)
        self._capture_trace(
            TurnTrace(
                user_input=user_message,
                response_preview=_preview_text(response.text),
                model=self.config.model,
                reasoning_level=self.config.reasoning_level,
                latency_ms=latency_ms,
                tool_calls=response.tool_calls,
                rag_hits=response.rag_hits,
                memory_hits=response.memory_hits,
                error=response.error,
            )
        )
        return response.text

    def set_api_key(self, api_key: str) -> str:
        self.config.openai_api_key = api_key.strip()
        self._persist_and_rebuild()
        return "OpenAI key saved and runtime refreshed."

    def set_model(self, model: str) -> str:
        cleaned = model.strip()
        if not cleaned:
            return "Invalid model. Provide a non-empty model name."

        self.config.model = cleaned
        self._persist_and_rebuild()
        return f"Model updated to {self.config.model}."

    def set_embedding_model(self, model: str) -> str:
        cleaned = model.strip()
        if not cleaned:
            return "Invalid embedding model. Provide a non-empty embedding model name."

        self.config.embedding_model = cleaned
        self._persist_and_rebuild()
        return f"Embedding model updated to {self.config.embedding_model}."

    def set_temperature(self, value: str) -> str:
        try:
            temperature = float(value.strip())
        except ValueError:
            return "Invalid temperature. Use a number between 0 and 2."

        if temperature < 0 or temperature > 2:
            return "Invalid temperature. Use a value between 0 and 2."

        self.config.temperature = round(temperature, 3)
        self._persist_and_rebuild()
        return f"Temperature updated to {self.config.temperature}."

    def set_reasoning_level(self, level: str) -> str:
        requested = level.strip().lower()
        if not is_reasoning_level(requested):
            options = ", ".join(REASONING_LEVELS)
            return f"Invalid reasoning level: {requested}. Use one of: {options}"

        normalized = normalize_reasoning_level(requested)
        self.config.reasoning_level = normalized
        self._persist_and_rebuild()
        mode = describe_reasoning_mode(self.config.model, self.config.reasoning_level)
        return f"Reasoning level updated to {normalized} ({mode})."

    def set_webhook_timeout_seconds(self, value: str) -> str:
        try:
            timeout = float(value.strip())
        except ValueError:
            return "Invalid timeout. Use a number greater than 0."

        if timeout <= 0:
            return "Invalid timeout. Use a number greater than 0."

        self.config.webhook_timeout_seconds = round(timeout, 3)
        self._persist_and_rebuild()
        return f"Webhook timeout updated to {self.config.webhook_timeout_seconds}s."

    def set_max_rag_results(self, value: str) -> str:
        try:
            max_results = int(value.strip())
        except ValueError:
            return "Invalid max-rag. Use an integer between 1 and 20."

        if max_results < 1 or max_results > 20:
            return "Invalid max-rag. Use an integer between 1 and 20."

        self.config.max_rag_results = max_results
        self._persist_and_rebuild()
        return f"Max RAG results updated to {self.config.max_rag_results}."

    def set_rag_min_final_score(self, value: str) -> str:
        try:
            score = float(value.strip())
        except ValueError:
            return "Invalid rag-min-score. Use a number between 0 and 1."

        if score < 0 or score > 1:
            return "Invalid rag-min-score. Use a number between 0 and 1."

        self.config.rag_min_final_score = round(score, 3)
        self._persist_and_rebuild()
        return f"RAG min final score updated to {self.config.rag_min_final_score}."

    def set_trace_enabled(self, raw_value: str) -> str:
        lowered = raw_value.strip().lower()
        if lowered in {"on", "true", "1", "yes"}:
            self.config.trace_enabled = True
        elif lowered in {"off", "false", "0", "no"}:
            self.config.trace_enabled = False
        else:
            return "Invalid trace mode. Use on or off."

        self._persist_and_rebuild()
        return f"Trace {'enabled' if self.config.trace_enabled else 'disabled'}."

    def set_memory_policy(self, value: str) -> str:
        policy = value.strip().lower()
        if policy not in MEMORY_POLICIES:
            options = ", ".join(MEMORY_POLICIES)
            return f"Invalid memory policy. Use one of: {options}"
        self.config.memory_policy = policy
        self._persist_and_rebuild()
        return f"Memory policy updated to {self.config.memory_policy}."

    def set_tool_http_allowlist(self, raw_hosts: str) -> str:
        cleaned = raw_hosts.strip()
        if not cleaned or cleaned.lower() in {"off", "none", "disable"}:
            self.config.tool_http_allowlist = []
            self._persist_and_rebuild()
            return "HTTP allowlist disabled."

        hosts = [item.strip().lower() for item in cleaned.split(",") if item.strip()]
        self.config.tool_http_allowlist = sorted(set(hosts))
        self._persist_and_rebuild()
        return f"HTTP allowlist updated ({len(self.config.tool_http_allowlist)} hosts)."

    def set_rag_index_path(self, raw_path: str) -> str:
        cleaned = raw_path.strip().strip('"')
        if not cleaned:
            return "Invalid rag-path. Provide a non-empty path."

        resolved = self._resolve_path(cleaned)
        if not resolved.parent.exists():
            resolved.parent.mkdir(parents=True, exist_ok=True)

        if resolved.is_absolute():
            try:
                relative = str(resolved.relative_to(self.root_dir))
                self.config.rag_index_path = relative
            except ValueError:
                self.config.rag_index_path = str(resolved)
        else:
            self.config.rag_index_path = cleaned

        self._persist_and_rebuild()
        effective = self._resolve_path(self.config.rag_index_path)
        return f"RAG index path updated to {effective}."

    def set_mcp_gateway(self, gateway_url: str | None) -> str:
        normalized = _normalize_mcp_gateway_url(gateway_url)
        if gateway_url and not normalized:
            return (
                "Invalid MCP gateway URL. Use http(s)://host[:port][/base-path] "
                "or disable with /mcp off."
            )
        self.config.mcp_gateway_url = normalized
        self._persist_and_rebuild()
        if self.config.mcp_gateway_url:
            return f"MCP gateway updated: {self.config.mcp_gateway_url}"
        return "MCP gateway disabled."

    def enable_provider(self, provider_name: str) -> str:
        provider_name = provider_name.strip()
        if provider_name not in self.registry.available_provider_names():
            return f"Unknown provider: {provider_name}"
        if provider_name not in self.config.enabled_providers:
            self.config.enabled_providers.append(provider_name)
            self._persist_and_rebuild()
        return f"Provider enabled: {provider_name}"

    def disable_provider(self, provider_name: str) -> str:
        provider_name = provider_name.strip()
        if provider_name == "utility":
            return "Provider utility cannot be disabled."
        if provider_name in self.config.enabled_providers:
            self.config.enabled_providers.remove(provider_name)
            self._persist_and_rebuild()
        return f"Provider disabled: {provider_name}"

    def list_providers_text(self) -> str:
        lines = ["Available providers:"]
        for info in self.registry.list_available(self.config.enabled_providers):
            prefix = "[x]" if info.enabled else "[ ]"
            lines.append(f"{prefix} {info.name}: {info.description}")
        return "\n".join(lines)

    def add_document(self, file_path: str) -> str:
        if self.rag_store is None:
            self.rebuild_services()
        if self.rag_store is None:
            return "RAG unavailable. Configure OpenAI key first."

        path = self._resolve_path(file_path)
        if not path.exists() or not path.is_file():
            return f"File not found: {path}"

        try:
            chunk_count = self.rag_store.add_document(path)
        except Exception as exc:  # noqa: BLE001 - keep UI resilient
            return f"Could not index document: {exc}"
        return f"Indexed {chunk_count} chunks from {path}."

    def debug_document(self, file_path: str) -> str:
        path = self._resolve_path(file_path)
        if not path.exists() or not path.is_file():
            return f"File not found: {path}"

        try:
            if self.rag_store is not None:
                report = self.rag_store.inspect_document(path)
            else:
                report = OpenAIRAGStore.inspect_document_path(path)
        except Exception as exc:  # noqa: BLE001 - keep UI resilient
            return f"Document debug failed: {exc}"

        lines = [
            "Document Debug",
            f"path: {report.path}",
            f"extension: {report.extension or '(none)'}",
            f"file_size: {report.file_size} bytes",
            f"extracted_chars: {report.extracted_chars}",
            f"chunk_count: {report.chunk_count}",
            f"printable_ratio: {report.printable_ratio:.3f}",
            f"replacement_chars: {report.replacement_chars}",
        ]
        if report.warnings:
            lines.append("warnings:")
            lines.extend(f"- {warning}" for warning in report.warnings)
        if report.sample:
            lines.append("sample:")
            lines.append(report.sample)
        return "\n".join(lines)

    def debug_search(self, query: str, k: int = 6) -> str:
        if self.rag_store is None:
            self.rebuild_services()
        if self.rag_store is None:
            return "RAG unavailable. Configure OpenAI key first."

        cleaned_query = query.strip()
        if not cleaned_query:
            return "Invalid debug-search query."

        limited_k = max(1, min(k, 20))
        try:
            results = self.rag_store.debug_search(
                cleaned_query,
                k=limited_k,
                exclude_source_prefix="memory://",
            )
        except Exception as exc:  # noqa: BLE001 - keep UI resilient
            return f"Debug search failed: {exc}"

        if not results:
            return "No debug search matches found in indexed documents."

        lines = [f"Debug Search Results ({len(results)}):"]
        for idx, item in enumerate(results, start=1):
            metadata = item.metadata or {}
            vector_score = metadata.get("vector_score", "0.000000")
            lexical_score = metadata.get("lexical_score", "0.000000")
            final_score = metadata.get("final_score", f"{item.score:.6f}")
            lines.append(
                f"{idx}. score={item.score:.3f} source={item.source}\n"
                f"   chunk_id={item.chunk_id}\n"
                f"   vector_score={vector_score} lexical_score={lexical_score} final_score={final_score}\n"
                f"   preview={item.content_preview}"
            )
        return "\n\n".join(lines)

    def debug_rag_answer(self, query: str, k: int = 8) -> str:
        if self.rag_store is None:
            self.rebuild_services()
        if self.rag_store is None:
            return "RAG unavailable. Configure OpenAI key first."

        cleaned_query = query.strip()
        if not cleaned_query:
            return "Invalid debug-rag-answer query."

        limited_k = max(1, min(k, 20))
        try:
            results = self.rag_store.search_hybrid(
                cleaned_query,
                k=limited_k,
                exclude_source_prefix="memory://",
            )
        except Exception as exc:  # noqa: BLE001 - keep UI resilient
            return f"Debug RAG answer failed: {exc}"

        if not results:
            return "No matches found for debug-rag-answer."

        lines = [f"Debug RAG Answer Context ({len(results)} chunks):"]
        for idx, item in enumerate(results, start=1):
            metadata = item.metadata or {}
            chunk_id = metadata.get("chunk_id", "unknown")
            vector_score = metadata.get("vector_score", "0.000000")
            lexical_score = metadata.get("lexical_score", "0.000000")
            final_score = metadata.get("final_score", f"{item.score:.6f}")
            snippet = item.content.replace("\n", " ").strip()
            if len(snippet) > 420:
                snippet = f"{snippet[:420]}..."
            lines.append(
                f"{idx}. source={item.source} chunk_id={chunk_id}\n"
                f"   vector_score={vector_score} lexical_score={lexical_score} final_score={final_score}\n"
                f"   context={snippet}"
            )
        return "\n\n".join(lines)

    def list_documents_text(self) -> str:
        if self.rag_store is None:
            return "No RAG store loaded."
        sources = self.rag_store.list_sources(include_memories=False)
        if not sources:
            return "No documents indexed."
        lines = [f"Indexed sources ({len(sources)}):"]
        lines.extend(f"- {source}" for source in sources)
        return "\n".join(lines)

    def clear_documents(self) -> str:
        if self.rag_store is None:
            return "No RAG store loaded."
        self.rag_store.clear_documents()
        return "Document index cleared."

    def list_memories_text(self, limit: int = 20) -> str:
        if self.rag_store is None:
            return "No memory store loaded."
        records = self.rag_store.list_memories(limit=limit)
        if not records:
            return "No conversation memories stored."

        lines = [f"Stored memories ({len(records)} shown):"]
        for record in records:
            metadata = record.metadata
            topic = metadata.get("topic", "general")
            importance = metadata.get("importance", "medium")
            created_at = metadata.get("created_at", "unknown")
            snippet = record.content.replace("\n", " ").strip()
            if len(snippet) > 180:
                snippet = f"{snippet[:180]}..."
            lines.append(
                f"- topic={topic} importance={importance} created_at={created_at}\n"
                f"  source={record.source}\n"
                f"  {snippet}"
            )
        return "\n".join(lines)

    def clear_memories(self) -> str:
        if self.rag_store is None:
            return "No memory store loaded."
        self.rag_store.clear_memories()
        return "Conversation memories cleared."

    def reload(self) -> str:
        self.registry = ToolRegistry()
        self.registry.register_defaults()
        self.loaded_plugins, self.plugin_errors = self.registry.load_plugins(self.plugin_dir)
        self._materialize_persistent_config()
        self.rebuild_services()
        return "Runtime reloaded."

    def retry_last_user_message(self) -> str:
        for speaker, content in reversed(self._active_history()):
            if speaker == "user":
                return self.chat(content)
        return "No previous user message to retry."

    def history_text(self, limit: int = 10) -> str:
        if limit <= 0:
            return "No history requested."
        items = self._active_history()[-limit:]
        if not items:
            return "No conversation history yet."
        lines = [f"Session history [{self._active_session_id}] ({len(items)} turns shown):"]
        for speaker, content in items:
            prefix = "You" if speaker == "user" else "Assistant"
            lines.append(f"- {prefix}: {_preview_text(content, size=220)}")
        return "\n".join(lines)

    def new_session(self) -> str:
        self._active_session_id = self._create_session()
        return f"Started new session: {self._active_session_id}"

    def sessions_text(self) -> str:
        if not self._session_order:
            return "No sessions available."

        lines = ["Sessions:"]
        for idx, session_id in enumerate(self._session_order, start=1):
            marker = "*" if session_id == self._active_session_id else " "
            turns = len(self._sessions.get(session_id, []))
            lines.append(f"{marker} {idx}. {session_id} ({turns} turns)")
        lines.append("Use /sessions <id|index> to switch session.")
        return "\n".join(lines)

    def switch_session(self, selector: str) -> str:
        cleaned = selector.strip()
        if not cleaned:
            return self.sessions_text()

        target_id: str | None = None
        if cleaned.isdigit():
            idx = int(cleaned)
            if idx < 1 or idx > len(self._session_order):
                return "Invalid session index."
            target_id = self._session_order[idx - 1]
        elif cleaned in self._sessions:
            target_id = cleaned
        else:
            return "Session not found."

        self._active_session_id = target_id
        turns = len(self._sessions.get(target_id, []))
        return f"Switched to session {target_id} ({turns} turns)."

    def last_trace_text(self) -> str:
        if self.last_trace is None:
            return "No trace available yet."
        trace = self.last_trace
        lines = [
            "Last Trace",
            f"timestamp: {trace.timestamp}",
            f"latency_ms: {trace.latency_ms}",
            f"model: {trace.model}",
            f"reasoning_level: {trace.reasoning_level}",
            f"tool_calls: {', '.join(trace.tool_calls) if trace.tool_calls else '(none)'}",
            f"rag_hits: {trace.rag_hits}",
            f"memory_hits: {trace.memory_hits}",
        ]
        if trace.error:
            lines.append(f"error: {trace.error}")
        lines.append(f"response_preview: {trace.response_preview}")
        return "\n".join(lines)

    def status_text(self) -> str:
        key_value = self.config.resolved_openai_api_key()
        key_status = _mask_key(key_value) if key_value else "not set"
        total_chunks = self.rag_store.count() if self.rag_store else 0
        document_count = self.rag_store.count_documents() if self.rag_store else 0
        memory_count = self.rag_store.count_memories() if self.rag_store else 0
        tool_count = self.agent.tool_count if self.agent else 0

        lines = [
            "Runtime Status",
            "",
            f"Active session: {self._active_session_id}",
            f"Session count: {len(self._session_order)}",
            f"OpenAI key: {key_status}",
            f"Model: {self.config.model}",
            f"Embedding model: {self.config.embedding_model}",
            f"Temperature: {self.config.temperature}",
            f"Reasoning level: {normalize_reasoning_level(self.config.reasoning_level)}",
            f"Reasoning mode: {describe_reasoning_mode(self.config.model, self.config.reasoning_level)}",
            f"Enabled providers: {', '.join(self.config.enabled_providers)}",
            f"Loaded tool count: {tool_count}",
            f"Indexed documents: {document_count}",
            f"Stored memories: {memory_count}",
            f"Vector chunks (total): {total_chunks}",
            f"RAG index path: {self._resolve_path(self.config.rag_index_path)}",
            f"Webhook timeout: {self.config.webhook_timeout_seconds}s",
            f"Max RAG results: {self.config.max_rag_results}",
            f"RAG min final score: {self.config.rag_min_final_score}",
            f"MCP gateway: {self.config.mcp_gateway_url or 'disabled'}",
            f"Trace enabled: {'yes' if self.config.trace_enabled else 'no'}",
            f"Memory policy: {self.config.memory_policy}",
            f"HTTP allowlist hosts: {len(self.config.tool_http_allowlist)}",
            f"Last latency: {self.last_latency_ms if self.last_latency_ms is not None else 'n/a'}ms",
            f"Persistent config: {self.config_path}",
        ]

        if self.loaded_plugins:
            lines.append(f"Plugins loaded: {', '.join(self.loaded_plugins)}")
        if self.plugin_errors:
            lines.append("Plugin errors:")
            lines.extend(f"- {error}" for error in self.plugin_errors)
        if self.last_error:
            lines.append(f"Runtime error: {self.last_error}")
        return "\n".join(lines)

    def _persist_and_rebuild(self) -> None:
        self.config.save(self.config_path)
        self.rebuild_services()

    def _materialize_persistent_config(self) -> None:
        changed = False
        env_key = os.getenv("OPENAI_API_KEY")
        if env_key and not self.config.openai_api_key:
            self.config.openai_api_key = env_key.strip()
            changed = True

        normalized_reasoning = normalize_reasoning_level(self.config.reasoning_level)
        if normalized_reasoning != self.config.reasoning_level:
            self.config.reasoning_level = normalized_reasoning
            changed = True

        if self.config.max_rag_results < 1:
            self.config.max_rag_results = 1
            changed = True
        elif self.config.max_rag_results > 20:
            self.config.max_rag_results = 20
            changed = True

        if self.config.temperature < 0:
            self.config.temperature = 0.0
            changed = True
        elif self.config.temperature > 2:
            self.config.temperature = 2.0
            changed = True

        if self.config.webhook_timeout_seconds <= 0:
            self.config.webhook_timeout_seconds = 20.0
            changed = True

        if self.config.memory_policy not in MEMORY_POLICIES:
            self.config.memory_policy = "balanced"
            changed = True

        if self.config.rag_min_final_score < 0:
            self.config.rag_min_final_score = 0.0
            changed = True
        elif self.config.rag_min_final_score > 1:
            self.config.rag_min_final_score = 1.0
            changed = True

        normalized_allowlist = sorted(
            {
                str(host).strip().lower()
                for host in self.config.tool_http_allowlist
                if str(host).strip()
            }
        )
        if normalized_allowlist != self.config.tool_http_allowlist:
            self.config.tool_http_allowlist = normalized_allowlist
            changed = True

        normalized_gateway = _normalize_mcp_gateway_url(self.config.mcp_gateway_url)
        if normalized_gateway != self.config.mcp_gateway_url:
            self.config.mcp_gateway_url = normalized_gateway
            changed = True

        if not self.config_path.exists() or changed:
            self.config.save(self.config_path)

    def _resolve_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path.strip().strip('"')).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        return (self.root_dir / candidate).resolve()

    def _append_history(self, user_message: str, assistant_message: str) -> None:
        session = self._sessions.setdefault(self._active_session_id, [])
        session.append(("user", user_message))
        session.append(("assistant", assistant_message))
        if len(session) > 80:
            self._sessions[self._active_session_id] = session[-80:]

    def _active_history(self) -> list[tuple[str, str]]:
        return self._sessions.setdefault(self._active_session_id, [])

    def _create_session(self) -> str:
        self._session_counter += 1
        session_id = f"session-{self._session_counter:03d}"
        self._sessions[session_id] = []
        self._session_order.append(session_id)
        return session_id

    def _capture_trace(self, trace: TurnTrace) -> None:
        self.last_trace = trace
        if not self.config.trace_enabled:
            return
        self._trace_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(trace)
        with self._trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _mask_key(key: str) -> str:
    if len(key) <= 12:
        return "***"
    return f"{key[:6]}...{key[-4:]}"


def _preview_text(value: str, size: int = 260) -> str:
    normalized = value.replace("\n", " ").strip()
    if len(normalized) <= size:
        return normalized
    return f"{normalized[:size]}..."


def _normalize_mcp_gateway_url(raw_url: str | None) -> str | None:
    if raw_url is None:
        return None
    cleaned = raw_url.strip().strip('"')
    if not cleaned:
        return None

    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    base = cleaned.rstrip("/")
    if base.lower().endswith("/invoke"):
        base = base[: -len("/invoke")]
    return base.rstrip("/")
