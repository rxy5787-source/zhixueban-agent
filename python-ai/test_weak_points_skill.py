"""Pure local tests; no Qwen, database writes or network requests."""
import pytest
from pydantic import ValidationError

from backend.weak_points_skill import get_weak_knowledge_points


def point(name, seen, correct, mastery):
    return {"point": name, "observations": seen, "correct": correct,
            "mastery": mastery, "reviewPriority": mastery < 0.45}


def test_no_history_requests_diagnosis():
    result = get_weak_knowledge_points([])
    assert result.status == "needs_diagnosis"
    assert result.reason == "no_history"
    assert result.weak_points == []


def test_sparse_history_requests_diagnosis_not_guesswork():
    result = get_weak_knowledge_points([point("HAVING", 1, 0, .2)])
    assert result.status == "needs_diagnosis"
    assert result.reason == "insufficient_observations"


def test_returns_sorted_weak_points_with_evidence():
    result = get_weak_knowledge_points([
        point("WHERE", 6, 5, .8),
        point("GROUP BY", 5, 2, .35),
        point("HAVING", 4, 1, .29),
    ])
    assert result.status == "ready"
    assert [p.knowledge_point for p in result.weak_points] == ["HAVING", "GROUP BY"]
    assert result.evidence_count == 15
    assert result.weak_points[0].observations == 4


def test_no_weak_points_not_misreported_as_missing_data():
    result = get_weak_knowledge_points([point("WHERE", 6, 5, .87)])
    assert result.status == "no_weak_points"


def test_excludes_sparse_points_from_weak_list():
    result = get_weak_knowledge_points([
        point("HAVING", 1, 0, .10),
        point("WHERE", 5, 2, .40),
    ])
    assert [p.knowledge_point for p in result.weak_points] == ["WHERE"]


@pytest.mark.parametrize("rows", [
    [point("HAVING", 1, 2, .45)],
    [point("HAVING", -1, 0, .45)],
    [point("HAVING", 3, 1, 1.2)],
    [point("HAVING", 3, 1, float("nan"))],
])
def test_rejects_invalid_evidence(rows):
    with pytest.raises((ValueError, ValidationError)):
        get_weak_knowledge_points(rows)


def test_bad_threshold_rejected():
    with pytest.raises(ValueError):
        get_weak_knowledge_points([], threshold=float("nan"))
