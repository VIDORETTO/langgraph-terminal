from __future__ import annotations

from typing import Final

REASONING_LEVELS: Final[tuple[str, str, str, str]] = ("low", "medium", "high", "xhigh")
DEFAULT_REASONING_LEVEL: Final[str] = "medium"


def is_reasoning_level(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in REASONING_LEVELS


def normalize_reasoning_level(value: str | None) -> str:
    if value is None:
        return DEFAULT_REASONING_LEVEL
    lowered = value.strip().lower()
    if lowered in REASONING_LEVELS:
        return lowered
    return DEFAULT_REASONING_LEVEL


def model_supports_native_reasoning(model_name: str) -> bool:
    model = model_name.strip().lower()
    if not model:
        return False
    return model.startswith(("gpt-5", "o1", "o3", "o4"))


def reasoning_level_to_native_effort(level: str) -> str:
    normalized = normalize_reasoning_level(level)
    if normalized == "xhigh":
        return "high"
    return normalized


def native_reasoning_kwargs(model_name: str, level: str) -> dict[str, str]:
    if not model_supports_native_reasoning(model_name):
        return {}
    return {"reasoning_effort": reasoning_level_to_native_effort(level)}


def describe_reasoning_mode(model_name: str, level: str) -> str:
    normalized = normalize_reasoning_level(level)
    if model_supports_native_reasoning(model_name):
        effort = reasoning_level_to_native_effort(normalized)
        if normalized == "xhigh":
            return f"native effort={effort} + prompt boost"
        return f"native effort={effort}"
    return "prompt fallback (legacy model)"


def build_reasoning_prompt_block(model_name: str, level: str) -> str:
    normalized = normalize_reasoning_level(level)
    lines = [
        "Reasoning mode:",
        f"- requested_level: {normalized}",
    ]

    if model_supports_native_reasoning(model_name):
        lines.append(f"- native_reasoning_effort: {reasoning_level_to_native_effort(normalized)}")
    else:
        lines.append(
            "- native_reasoning_effort: unavailable for this model (using prompt-only control)"
        )

    if normalized == "low":
        lines.append("- style: prioritize speed and concise reasoning.")
    elif normalized == "medium":
        lines.append("- style: balanced depth and speed.")
    elif normalized == "high":
        lines.append("- style: deeper analysis, explicit checks, and cautious conclusions.")
    else:
        lines.append(
            "- style: maximum depth; decompose complex tasks, validate assumptions, and"
            " cross-check results before finalizing."
        )

    return "\n".join(lines)
