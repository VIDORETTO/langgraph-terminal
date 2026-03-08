from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from langchain_core.tools import BaseTool

from langgraph_terminal.config import AppConfig
from langgraph_terminal.rag.store import OpenAIRAGStore


@dataclass
class ToolContext:
    config: AppConfig
    rag_store: OpenAIRAGStore | None = None


class ToolProvider(Protocol):
    name: str
    description: str

    def build_tools(self, context: ToolContext) -> list[BaseTool]:
        ...
