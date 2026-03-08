"""Example plugin provider.

To enable custom providers:
1. Keep this file under ./plugins
2. Expose build_provider() returning an object with:
   - name: str
   - description: str
   - build_tools(context) -> list[BaseTool]
3. Run /reload in the TUI
"""

from __future__ import annotations

from langchain_core.tools import BaseTool, StructuredTool

from langgraph_terminal.tools.contracts import ToolContext


class ExampleProvider:
    name = "example_plugin"
    description = "Sample provider loaded from plugins directory."

    def build_tools(self, context: ToolContext) -> list[BaseTool]:
        def plugin_healthcheck() -> str:
            return (
                "Example plugin is active. "
                f"Current model: {context.config.model}. "
                f"Enabled providers: {', '.join(context.config.enabled_providers)}"
            )

        return [
            StructuredTool.from_function(
                func=plugin_healthcheck,
                name="plugin_healthcheck",
                description="Simple plugin tool to validate plugin architecture.",
            )
        ]


def build_provider() -> ExampleProvider:
    return ExampleProvider()
