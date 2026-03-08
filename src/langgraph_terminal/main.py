from __future__ import annotations

from langgraph_terminal.runtime import ApplicationRuntime
from langgraph_terminal.tui import TerminalAgentApp


def main() -> None:
    runtime = ApplicationRuntime()
    app = TerminalAgentApp(runtime)
    app.run()


if __name__ == "__main__":
    main()
