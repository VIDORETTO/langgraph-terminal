from __future__ import annotations

import asyncio
import shlex
from datetime import datetime

from rich.panel import Panel
from rich.text import Text
from rich.markup import escape
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Input, RichLog, Static

from langgraph_terminal.runtime import ApplicationRuntime


class TerminalAgentApp(App[None]):
    TITLE = "LangGraph Terminal UI"
    SUB_TITLE = "LangChain + LangGraph + OpenAI + Extensible Tools"

    CSS = """
    Screen {
        layout: vertical;
    }

    #body {
        height: 1fr;
    }

    #chat {
        width: 3fr;
        border: round #4a7a5f;
        padding: 1 1;
        background: #0f1714;
    }

    #sidebar {
        width: 2fr;
        border: round #7f6a3f;
        padding: 1 1;
        overflow-y: auto;
        background: #1a1711;
    }

    #command {
        margin: 0 1;
        border: round #3f5f7f;
        background: #11151b;
    }

    #command_suggestions {
        margin: 0 1;
        border: round #6a5f3f;
        padding: 0 1;
        background: #15130f;
        color: #d8c89f;
        height: auto;
    }
    """

    COMMAND_HELP = {
        "/help": "show this help",
        "/status": "print runtime status in chat",
        "/providers": "list providers and enabled state",
        "/new": "start new clean chat session",
        "/sessions": "list or switch sessions",
        "/key": "set OpenAI key",
        "/model": "set chat model",
        "/embedding": "set embedding model",
        "/temperature": "set model temperature",
        "/reasoning": "set reasoning effort profile",
        "/timeout": "set webhook/http timeout",
        "/max-rag": "set max chunks returned by RAG tools",
        "/rag-min-score": "set minimum confidence threshold for RAG",
        "/trace": "enable or disable trace capture",
        "/last-trace": "show details from previous turn",
        "/retry": "rerun the last user message",
        "/history": "show recent session turns",
        "/memory-policy": "control auto-memory persistence",
        "/http-allowlist": "restrict tool HTTP destinations",
        "/rag-path": "set persistent vector index path",
        "/mcp": "configure MCP gateway endpoint",
        "/enable": "enable provider",
        "/disable": "disable provider",
        "/add-doc": "index file into local RAG",
        "/debug-doc": "inspect extraction/chunking",
        "/debug-search": "inspect hybrid retrieval scores",
        "/debug-rag-answer": "inspect final hybrid context payload",
        "/list-docs": "show indexed files",
        "/clear-docs": "clear indexed documents",
        "/list-memories": "show stored memories",
        "/clear-memories": "clear stored memories",
        "/reload": "reload registry/plugins and runtime",
        "/quit": "exit app",
    }

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear_chat", "Clear chat"),
        ("ctrl+r", "refresh_status", "Refresh status"),
        ("ctrl+shift+c", "copy_chat_selection", "Copy selection"),
    ]

    def __init__(self, runtime: ApplicationRuntime) -> None:
        super().__init__()
        self.runtime = runtime
        self._command_matches: list[str] = []
        self._command_selection = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            yield RichLog(id="chat", auto_scroll=True, wrap=True, highlight=True)
            yield Static(id="sidebar")
        yield Input(
            id="command",
            placeholder="Type message or command (/help). Example: /key sk-...",
        )
        yield Static("", id="command_suggestions")
        yield Footer()

    def on_mount(self) -> None:
        self._write_system_message("LangGraph Terminal UI ready.", kind="info")
        self._write_system_message(
            "Set your API key with /key sk-... and type /help to see commands.",
            kind="hint",
        )
        self._write_system_message(
            "Select text in chat with mouse and press Ctrl+Shift+C to copy.",
            kind="hint",
        )
        self._suggestions().display = False
        self._refresh_status()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        event.input.value = ""
        self._hide_command_suggestions()
        if not raw:
            return

        if raw.startswith("/"):
            await self._handle_command(raw)
            self._refresh_status()
            return

        self._write_user_message(raw)
        self._write_system_message("Thinking...", kind="hint")
        answer = await asyncio.to_thread(self.runtime.chat, raw)
        self._write_agent_message(answer)
        self._chat().write("[dim]--------------------------------------------------[/dim]")
        self._refresh_status()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "command":
            return
        self._update_command_suggestions(event.value)

    def on_key(self, event: events.Key) -> None:
        if not self._command_matches:
            return
        command_input = self._command_input()
        if not command_input.has_focus:
            return

        if event.key == "down":
            self._command_selection = (self._command_selection + 1) % len(self._command_matches)
            self._apply_selected_command()
            self._render_command_suggestions()
            event.stop()
            event.prevent_default()
            return

        if event.key == "up":
            self._command_selection = (self._command_selection - 1) % len(self._command_matches)
            self._apply_selected_command()
            self._render_command_suggestions()
            event.stop()
            event.prevent_default()
            return

        if event.key == "tab":
            self._apply_selected_command(add_space=True)
            self._hide_command_suggestions()
            event.stop()
            event.prevent_default()
            return

        if event.key == "enter":
            selected = self._command_matches[self._command_selection]
            if command_input.value.strip() != selected:
                self._apply_selected_command(add_space=True)
                self._hide_command_suggestions()
                event.stop()
                event.prevent_default()
            return

        if event.key == "escape":
            self._hide_command_suggestions()
            event.stop()
            event.prevent_default()

    async def _handle_command(self, raw: str) -> None:
        try:
            parts = shlex.split(raw, posix=False)
        except ValueError as exc:
            self._chat().write(f"[red]Invalid command:[/red] {escape(str(exc))}")
            return
        if not parts:
            return

        command = parts[0].lower()

        if command in {"/help", "/h"}:
            self._chat().write(self._help_text())
            return

        if command == "/status":
            self._chat().write(escape(self.runtime.status_text()))
            return

        if command == "/new":
            self.action_clear_chat()
            text = await asyncio.to_thread(self.runtime.new_session)
            self._chat().write(f"[yellow]{escape(text)}[/yellow]")
            return

        if command == "/sessions":
            if len(parts) < 2:
                text = await asyncio.to_thread(self.runtime.sessions_text)
                self._chat().write(escape(text))
                return

            target = raw[len("/sessions") :].strip()
            text = await asyncio.to_thread(self.runtime.switch_session, target)
            self._chat().write(f"[yellow]{escape(text)}[/yellow]")
            if text.startswith("Switched to session"):
                self.action_clear_chat()
                history = await asyncio.to_thread(self.runtime.history_text, 30)
                self._chat().write(escape(history))
            return

        if command == "/providers":
            text = await asyncio.to_thread(self.runtime.list_providers_text)
            self._chat().write(escape(text))
            return

        if command == "/key":
            if len(parts) < 2:
                self._chat().write("[red]Usage:[/red] /key <OPENAI_API_KEY>")
                return
            key = raw[len("/key") :].strip()
            text = await asyncio.to_thread(self.runtime.set_api_key, key)
            self._chat().write(f"[yellow]{escape(text)}[/yellow]")
            return

        if command == "/model":
            if len(parts) < 2:
                self._chat().write("[red]Usage:[/red] /model <model_name>")
                return
            model = raw[len("/model") :].strip()
            text = await asyncio.to_thread(self.runtime.set_model, model)
            self._chat().write(f"[yellow]{escape(text)}[/yellow]")
            return

        if command == "/embedding":
            if len(parts) < 2:
                self._chat().write("[red]Usage:[/red] /embedding <embedding_model>")
                return
            embedding_model = raw[len("/embedding") :].strip()
            text = await asyncio.to_thread(self.runtime.set_embedding_model, embedding_model)
            self._chat().write(f"[yellow]{escape(text)}[/yellow]")
            return

        if command == "/temperature":
            if len(parts) < 2:
                self._chat().write("[red]Usage:[/red] /temperature <0..2>")
                return
            value = raw[len("/temperature") :].strip()
            text = await asyncio.to_thread(self.runtime.set_temperature, value)
            self._chat().write(f"[yellow]{escape(text)}[/yellow]")
            return

        if command == "/reasoning":
            if len(parts) < 2:
                self._chat().write("[red]Usage:[/red] /reasoning <low|medium|high|xhigh>")
                return
            level = raw[len("/reasoning") :].strip()
            text = await asyncio.to_thread(self.runtime.set_reasoning_level, level)
            self._chat().write(f"[yellow]{escape(text)}[/yellow]")
            return

        if command == "/timeout":
            if len(parts) < 2:
                self._chat().write("[red]Usage:[/red] /timeout <seconds>")
                return
            value = raw[len("/timeout") :].strip()
            text = await asyncio.to_thread(self.runtime.set_webhook_timeout_seconds, value)
            self._chat().write(f"[yellow]{escape(text)}[/yellow]")
            return

        if command == "/max-rag":
            if len(parts) < 2:
                self._chat().write("[red]Usage:[/red] /max-rag <1..20>")
                return
            value = raw[len("/max-rag") :].strip()
            text = await asyncio.to_thread(self.runtime.set_max_rag_results, value)
            self._chat().write(f"[yellow]{escape(text)}[/yellow]")
            return

        if command == "/rag-min-score":
            if len(parts) < 2:
                self._chat().write("[red]Usage:[/red] /rag-min-score <0..1>")
                return
            value = raw[len("/rag-min-score") :].strip()
            text = await asyncio.to_thread(self.runtime.set_rag_min_final_score, value)
            self._chat().write(f"[yellow]{escape(text)}[/yellow]")
            return

        if command == "/trace":
            if len(parts) < 2:
                self._chat().write("[red]Usage:[/red] /trace <on|off>")
                return
            value = parts[1]
            text = await asyncio.to_thread(self.runtime.set_trace_enabled, value)
            self._chat().write(f"[yellow]{escape(text)}[/yellow]")
            return

        if command == "/last-trace":
            text = await asyncio.to_thread(self.runtime.last_trace_text)
            self._chat().write(escape(text))
            return

        if command == "/retry":
            self._chat().write("[dim]Retrying last user message...[/dim]")
            text = await asyncio.to_thread(self.runtime.retry_last_user_message)
            self._chat().write(f"[green]Assistant:[/green] {escape(text)}")
            return

        if command == "/history":
            limit = 10
            if len(parts) >= 2:
                try:
                    limit = int(parts[1])
                except ValueError:
                    self._chat().write("[red]Invalid history limit:[/red] expected integer.")
                    return
            text = await asyncio.to_thread(self.runtime.history_text, limit)
            self._chat().write(escape(text))
            return

        if command == "/memory-policy":
            if len(parts) < 2:
                self._chat().write("[red]Usage:[/red] /memory-policy <strict|balanced|off>")
                return
            value = parts[1]
            text = await asyncio.to_thread(self.runtime.set_memory_policy, value)
            self._chat().write(f"[yellow]{escape(text)}[/yellow]")
            return

        if command == "/http-allowlist":
            if len(parts) < 2:
                self._chat().write(
                    "[red]Usage:[/red] /http-allowlist <host1,host2|off>"
                )
                return
            value = raw[len("/http-allowlist") :].strip()
            text = await asyncio.to_thread(self.runtime.set_tool_http_allowlist, value)
            self._chat().write(f"[yellow]{escape(text)}[/yellow]")
            return

        if command == "/rag-path":
            if len(parts) < 2:
                self._chat().write('[red]Usage:[/red] /rag-path "<path_to_index_json>"')
                return
            value = raw[len("/rag-path") :].strip()
            text = await asyncio.to_thread(self.runtime.set_rag_index_path, value)
            self._chat().write(f"[yellow]{escape(text)}[/yellow]")
            return

        if command == "/mcp":
            if len(parts) < 2:
                self._chat().write("[red]Usage:[/red] /mcp <gateway_url|off>")
                return
            value = raw[len("/mcp") :].strip()
            if value.lower() in {"off", "none", "disable"}:
                value = ""
            text = await asyncio.to_thread(self.runtime.set_mcp_gateway, value)
            self._chat().write(f"[yellow]{escape(text)}[/yellow]")
            return

        if command == "/enable":
            if len(parts) < 2:
                self._chat().write("[red]Usage:[/red] /enable <provider_name>")
                return
            name = parts[1]
            text = await asyncio.to_thread(self.runtime.enable_provider, name)
            self._chat().write(f"[yellow]{escape(text)}[/yellow]")
            return

        if command == "/disable":
            if len(parts) < 2:
                self._chat().write("[red]Usage:[/red] /disable <provider_name>")
                return
            name = parts[1]
            text = await asyncio.to_thread(self.runtime.disable_provider, name)
            self._chat().write(f"[yellow]{escape(text)}[/yellow]")
            return

        if command == "/add-doc":
            if len(parts) < 2:
                self._chat().write('[red]Usage:[/red] /add-doc "<path_to_file>"')
                return
            file_path = raw[len("/add-doc") :].strip()
            self._chat().write("[dim]Indexing document...[/dim]")
            text = await asyncio.to_thread(self.runtime.add_document, file_path)
            self._chat().write(f"[yellow]{escape(text)}[/yellow]")
            return

        if command == "/debug-doc":
            if len(parts) < 2:
                self._chat().write('[red]Usage:[/red] /debug-doc "<path_to_file>"')
                return
            file_path = raw[len("/debug-doc") :].strip()
            self._chat().write("[dim]Inspecting document extraction...[/dim]")
            text = await asyncio.to_thread(self.runtime.debug_document, file_path)
            self._chat().write(escape(text))
            return

        if command == "/debug-search":
            if len(parts) < 2:
                self._chat().write('[red]Usage:[/red] /debug-search "<query>" [k]')
                return

            payload = raw[len("/debug-search") :].strip()
            query = payload
            k = 6
            if len(parts) >= 3:
                try:
                    k = int(parts[2])
                except ValueError:
                    self._chat().write("[red]Invalid k:[/red] expected integer.")
                    return
                suffix = parts[2]
                if payload.endswith(suffix):
                    query = payload[: -len(suffix)].strip()

            query = query.strip().strip('"')
            if not query:
                self._chat().write('[red]Usage:[/red] /debug-search "<query>" [k]')
                return

            self._chat().write("[dim]Running debug hybrid search...[/dim]")
            text = await asyncio.to_thread(self.runtime.debug_search, query, k)
            self._chat().write(escape(text))
            return

        if command == "/debug-rag-answer":
            if len(parts) < 2:
                self._chat().write('[red]Usage:[/red] /debug-rag-answer "<query>" [k]')
                return

            payload = raw[len("/debug-rag-answer") :].strip()
            query = payload
            k = 8
            if len(parts) >= 3:
                try:
                    k = int(parts[2])
                except ValueError:
                    self._chat().write("[red]Invalid k:[/red] expected integer.")
                    return
                suffix = parts[2]
                if payload.endswith(suffix):
                    query = payload[: -len(suffix)].strip()

            query = query.strip().strip('"')
            if not query:
                self._chat().write('[red]Usage:[/red] /debug-rag-answer "<query>" [k]')
                return

            self._chat().write("[dim]Building final RAG context preview...[/dim]")
            text = await asyncio.to_thread(self.runtime.debug_rag_answer, query, k)
            self._chat().write(escape(text))
            return

        if command == "/list-docs":
            text = await asyncio.to_thread(self.runtime.list_documents_text)
            self._chat().write(escape(text))
            return

        if command == "/clear-docs":
            text = await asyncio.to_thread(self.runtime.clear_documents)
            self._chat().write(f"[yellow]{escape(text)}[/yellow]")
            return

        if command == "/list-memories":
            text = await asyncio.to_thread(self.runtime.list_memories_text)
            self._chat().write(escape(text))
            return

        if command == "/clear-memories":
            text = await asyncio.to_thread(self.runtime.clear_memories)
            self._chat().write(f"[yellow]{escape(text)}[/yellow]")
            return

        if command == "/reload":
            text = await asyncio.to_thread(self.runtime.reload)
            self._chat().write(f"[yellow]{escape(text)}[/yellow]")
            return

        if command in {"/quit", "/exit"}:
            self.exit()
            return

        self._chat().write(f"[red]Unknown command:[/red] {escape(command)}")

    def action_clear_chat(self) -> None:
        self._chat().clear()
        self._chat().write("[dim]Chat cleared.[/dim]")

    def action_refresh_status(self) -> None:
        self._refresh_status()

    def action_copy_chat_selection(self) -> None:
        selection = self._chat().text_selection
        if selection is None:
            self._write_system_message("No text selected in chat.", kind="error")
            return

        extracted = self._chat().get_selection(selection)
        if not extracted or not extracted[0].strip():
            self._write_system_message("Could not copy the selected text.", kind="error")
            return

        self.copy_to_clipboard(extracted[0])
        self._write_system_message("Selected chat text copied.", kind="info")

    def _refresh_status(self) -> None:
        self.query_one("#sidebar", Static).update(self.runtime.status_text())

    def _chat(self) -> RichLog:
        return self.query_one("#chat", RichLog)

    def _command_input(self) -> Input:
        return self.query_one("#command", Input)

    def _suggestions(self) -> Static:
        return self.query_one("#command_suggestions", Static)

    def _write_user_message(self, text: str) -> None:
        body = Text(text.strip())
        title = Text(f"You  [{self._now()}]", style="bold #7ac7ff")
        panel = Panel(body, title=title, border_style="#2f5f85", padding=(0, 1))
        self._chat().write(panel)

    def _write_agent_message(self, text: str) -> None:
        body = Text(text.strip())
        title = Text(f"Agent  [{self._now()}]", style="bold #7ee39f")
        panel = Panel(body, title=title, border_style="#2f7f54", padding=(0, 1))
        self._chat().write(panel)

    def _write_system_message(self, text: str, kind: str = "info") -> None:
        styles = {
            "info": ("System", "#9fb4d6"),
            "hint": ("Hint", "#c2b88d"),
            "error": ("Error", "#e28a8a"),
        }
        label, color = styles.get(kind, styles["info"])
        title = Text(f"{label}  [{self._now()}]", style=f"bold {color}")
        panel = Panel(Text(text.strip()), title=title, border_style=color, padding=(0, 1))
        self._chat().write(panel)

    def _now(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _help_text(self) -> str:
        return (
            "[bold]Commands[/bold]\n"
            "/help - show this help\n"
            "/new - start a new clean chat session\n"
            "/sessions [id|index] - list sessions or switch to one\n"
            "/key <OPENAI_API_KEY> - set OpenAI key\n"
            "/model <name> - set chat model\n"
            "/embedding <name> - set embedding model\n"
            "/temperature <0..2> - set model temperature\n"
            "/reasoning <low|medium|high|xhigh> - set reasoning effort profile\n"
            "/timeout <seconds> - set webhook/http timeout\n"
            "/max-rag <1..20> - set max chunks returned by RAG tools\n"
            "/rag-min-score <0..1> - set minimum confidence threshold for RAG\n"
            "/trace <on|off> - enable or disable trace capture\n"
            "/last-trace - show details from the previous turn\n"
            "/retry - rerun the last user message\n"
            "/history [n] - show recent session turns\n"
            "/memory-policy <strict|balanced|off> - control auto-memory persistence\n"
            "/http-allowlist <host1,host2|off> - restrict tool HTTP destinations\n"
            '/rag-path "<path>" - set persistent vector index path\n'
            "/mcp <url|off> - configure MCP gateway endpoint\n"
            "/providers - list providers and enabled state\n"
            "/enable <provider> - enable provider\n"
            "/disable <provider> - disable provider\n"
            '/add-doc "<path>" - index file into local RAG\n'
            '/debug-doc "<path>" - inspect extraction/chunking before indexing\n'
            '/debug-search "<query>" [k] - inspect hybrid retrieval scores\n'
            '/debug-rag-answer "<query>" [k] - inspect final hybrid context payload\n'
            "/list-docs - show indexed files\n"
            "/clear-docs - clear indexed documents\n"
            "/list-memories - show stored conversation memories\n"
            "/clear-memories - clear stored conversation memories\n"
            "/reload - reload registry/plugins and runtime\n"
            "/status - print runtime status in chat\n"
            "Ctrl+Shift+C - copy selected chat text\n"
            "/quit - exit app\n"
        )

    def _update_command_suggestions(self, raw_value: str) -> None:
        if not raw_value.startswith("/") or " " in raw_value:
            self._hide_command_suggestions()
            return

        typed = raw_value.lower()
        all_commands = list(self.COMMAND_HELP.keys())
        if typed == "/":
            matches = all_commands
        else:
            matches = [item for item in all_commands if item.startswith(typed)]

        if not matches:
            self._hide_command_suggestions()
            return

        self._command_matches = matches[:12]
        if raw_value in self._command_matches:
            self._command_selection = self._command_matches.index(raw_value)
        else:
            self._command_selection = 0
        self._render_command_suggestions()

    def _render_command_suggestions(self) -> None:
        lines = ["Comandos (/): use setas para navegar, Enter/Tab para completar"]
        for idx, command in enumerate(self._command_matches):
            prefix = "->" if idx == self._command_selection else "  "
            hint = self.COMMAND_HELP.get(command, "")
            lines.append(f"{prefix} {command} - {hint}")
        box = self._suggestions()
        box.update("\n".join(lines))
        box.display = True

    def _hide_command_suggestions(self) -> None:
        self._command_matches = []
        self._command_selection = 0
        box = self._suggestions()
        box.display = False
        box.update("")

    def _apply_selected_command(self, add_space: bool = False) -> None:
        if not self._command_matches:
            return
        command = self._command_matches[self._command_selection]
        value = f"{command} " if add_space else command
        input_widget = self._command_input()
        input_widget.value = value
        input_widget.cursor_position = len(value)
