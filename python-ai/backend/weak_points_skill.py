"""Read-only weak-point analysis for already-authorized Web practice progress.

This module neither queries a database nor calls an LLM. Authentication, library
ownership checks and loading must be performed by the caller before invocation.
"""
from __future__ import annotations

from math import isfinite
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PointProgress(BaseModel):
    model_config = ConfigDict(extra="ignore")
    point: str = Field(min_length=1, max_length=200)
    observations: int = Field(ge=0)
    correct: int = Field(ge=0)
    mastery: float = Field(ge=0, le=1)

    @field_validator("mastery")
    @classmethod
    def finite_mastery(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("mastery must be finite")
        return value


class WeakPoint(BaseModel):
    knowledge_point: str
    mastery_estimate: float
    observations: int
    correct: int


class WeakPointResult(BaseModel):
    status: Literal["ready", "needs_diagnosis", "no_weak_points"]
    weak_points: list[WeakPoint]
    evidence_count: int
    reason: str


def get_weak_knowledge_points(
    progress: list[dict],
    *,
    min_observations: int = 3,
    threshold: float = 0.45,
    limit: int = 5,
) -> WeakPointResult:
    """Classify Web practice progress without making a model call.

    Uses existing web_practice.point_view() keys:
    point / observations / correct / mastery.
    'needs_diagnosis' also covers sparse evidence; a BKT estimate with fewer
    than min_observations is not presented as a verified weak point.
    """
    if not 1 <= min_observations <= 100:
        raise ValueError("min_observations must be 1..100")
    if not isfinite(threshold) or not 0 < threshold < 1:
        raise ValueError("threshold must be in (0,1)")
    if not 1 <= limit <= 20:
        raise ValueError("limit must be 1..20")
    if not isinstance(progress, list):
        raise ValueError("progress must be a list")

    rows = [PointProgress.model_validate(row) for row in progress]
    for row in rows:
        if row.correct > row.observations:
            raise ValueError("correct cannot exceed observations")

    evidence_count = sum(row.observations for row in rows)
    eligible = [row for row in rows if row.observations >= min_observations]
    weak = sorted((row for row in eligible if row.mastery < threshold),
                  key=lambda row: (row.mastery, -row.observations, row.point))
    if weak:
        return WeakPointResult(
            status="ready",
            weak_points=[
                WeakPoint(knowledge_point=row.point, mastery_estimate=row.mastery,
                          observations=row.observations, correct=row.correct)
                for row in weak[:limit]
            ],
            evidence_count=evidence_count,
            reason="evidence_backed_weak_points",
        )
    if not eligible:
        return WeakPointResult(
            status="needs_diagnosis", weak_points=[], evidence_count=evidence_count,
            reason="no_history" if not rows else "insufficient_observations",
        )
    return WeakPointResult(
        status="no_weak_points", weak_points=[], evidence_count=evidence_count,
        reason="no_point_below_threshold",
    )
