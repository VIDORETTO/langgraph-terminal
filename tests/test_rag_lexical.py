from __future__ import annotations

from langgraph_terminal.rag.store import _compute_lexical_scores


def test_compute_lexical_scores_prioritizes_coverage() -> None:
    query = "alpha beta"
    documents = [
        "alpha beta gamma delta",
        "alpha gamma delta",
        "omega theta",
    ]

    scores = _compute_lexical_scores(query, documents)

    assert scores[0] > scores[1] > scores[2]
