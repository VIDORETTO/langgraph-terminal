from __future__ import annotations

import importlib.util
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from langchain_core.tools import BaseTool

from langgraph_terminal.config import AppConfig
from langgraph_terminal.rag.store import OpenAIRAGStore
from langgraph_terminal.tools.contracts import ToolContext, ToolProvider
from langgraph_terminal.tools.providers import (
    HttpApiToolProvider,
    MCPToolProvider,
    RAGToolProvider,
    UtilityToolProvider,
    WebSearchToolProvider,
    WebhookToolProvider,
)


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    description: str
    enabled: bool


class ToolRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ToolProvider] = {}

    def register(self, provider: ToolProvider) -> None:
        self._providers[provider.name] = provider

    def register_defaults(self) -> None:
        self.register(UtilityToolProvider())
        self.register(RAGToolProvider())
        self.register(HttpApiToolProvider())
        self.register(WebhookToolProvider())
        self.register(MCPToolProvider())
        self.register(WebSearchToolProvider())

    def available_provider_names(self) -> list[str]:
        return sorted(self._providers.keys())

    def list_available(self, enabled: list[str]) -> list[ProviderInfo]:
        enabled_set = set(enabled)
        return [
            ProviderInfo(
                name=name,
                description=provider.description,
                enabled=name in enabled_set,
            )
            for name, provider in sorted(self._providers.items(), key=lambda item: item[0])
        ]

    def build_enabled_tools(
        self,
        config: AppConfig,
        rag_store: OpenAIRAGStore | None,
    ) -> list[BaseTool]:
        context = ToolContext(config=config, rag_store=rag_store)
        tools: list[BaseTool] = []
        for name in config.enabled_providers:
            provider = self._providers.get(name)
            if provider is None:
                continue
            tools.extend(provider.build_tools(context))
        return tools

    def load_plugins(self, plugin_dir: Path) -> tuple[list[str], list[str]]:
        loaded: list[str] = []
        errors: list[str] = []
        if not plugin_dir.exists():
            return loaded, errors

        for plugin_path in sorted(plugin_dir.glob("*.py")):
            if plugin_path.name.startswith("_"):
                continue
            try:
                module = _load_module(plugin_path)
                provider = _provider_from_module(module)
                self.register(provider)
                loaded.append(provider.name)
            except Exception as exc:  # noqa: BLE001 - plugin errors should not stop app
                trace = traceback.format_exc(limit=1)
                errors.append(f"{plugin_path.name}: {exc} ({trace.strip()})")
        return loaded, errors


def _load_module(path: Path) -> ModuleType:
    module_name = f"lg_terminal_plugin_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load plugin: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _provider_from_module(module: ModuleType) -> ToolProvider:
    build_fn = getattr(module, "build_provider", None)
    if build_fn is None:
        raise RuntimeError("Plugin must expose build_provider()")
    provider = build_fn()
    if not hasattr(provider, "name") or not hasattr(provider, "description"):
        raise RuntimeError("Plugin provider must define name and description.")
    return provider
