from __future__ import annotations

from langgraph_terminal.reasoning import (
    is_reasoning_level,
    native_reasoning_kwargs,
    normalize_reasoning_level,
)


def test_normalize_reasoning_level() -> None:
    assert normalize_reasoning_level(None) == "medium"
    assert normalize_reasoning_level("invalid") == "medium"
    assert normalize_reasoning_level("HIGH") == "high"


def test_is_reasoning_level() -> None:
    assert is_reasoning_level("low")
    assert is_reasoning_level("XHIGH")
    assert not is_reasoning_level("invalid")


def test_native_reasoning_kwargs() -> None:
    assert native_reasoning_kwargs("gpt-5-mini", "xhigh") == {"reasoning_effort": "high"}
    assert native_reasoning_kwargs("gpt-4.1-mini", "high") == {}
