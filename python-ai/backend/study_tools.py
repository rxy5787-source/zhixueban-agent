"""Read-only and candidate-producing adapters for the existing study services."""
from __future__ import annotations

from contextlib import contextmanager, closing
import json
from pathlib import Path
import sqlite3
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from . import config, web_practice
from .practice_coverage import Scope
from .practice_quality import source_units, usable_practice_text
from .tool_registry import Contract, ToolContext, ToolFailure, ToolRegistry, ToolSpec

ResourceId = Annotated[str, StringConstraints(pattern=r'^[0-9a-f]{32}$')]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Evidence = Annotated[str, StringConstraints(min_length=1, max_length=4800)]
Choice = Literal['A', 'B', 'C', 'D']


class Empty(Contract):
    pass


class MaterialArgs(Contract):
    fileId: ResourceId


class ParseResult(Contract):
    sections: list[Evidence] = Field(max_length=12)
    limited: bool


class TopicArgs(MaterialArgs):
    goal: ShortText
    topic: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | None = None


class KnowledgePoint(Contract):
    name: ShortText
    summary: Evidence


class PointsResult(Contract):
    points: list[KnowledgePoint] = Field(max_length=4)


class ProgressPoint(Contract):
    point: ShortText
    observations: int = Field(ge=0)
    correct: int = Field(ge=0)
    mastery: float = Field(ge=0, le=1)
    reviewPriority: bool


class ProgressResult(Contract):
    points: list[ProgressPoint] = Field(max_length=12)


class GenerateArgs(TopicArgs):
    count: int = Field(ge=1, le=4)
    difficulty: int = Field(default=0, ge=0, le=3)


class Options(Contract):
    A: ShortText
    B: ShortText
    C: ShortText
    D: ShortText


class Candidate(Contract):
    question: ShortText
    options: Options
    answer: Choice
    knowledgePoint: ShortText
    difficulty: Literal['简单', '中等', '困难']
    explanation: Evidence
    questionConstruction: Literal['source_quantity_template_v1'] | None = None


class CandidatesResult(Contract):
    candidates: list[Candidate] = Field(max_length=4)


class ReviewArgs(MaterialArgs):
    candidates: list[Candidate] = Field(min_length=1, max_length=4)
    topic: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | None = None


class ReviewedCandidate(Candidate):
    evidenceQuote: Evidence
    reviewStatus: Literal['auto_prechecked']
    reviewMethod: Literal['batch_indexed_v1', 'literal_quantity_v1']
    reviewModel: ShortText
    explanationModel: Literal['indexed_source_v1']


class ReviewResult(Contract):
    accepted: list[ReviewedCandidate] = Field(max_length=4)
    rejectedCount: int = Field(ge=0, le=4)


@contextmanager
def _library(context: ToolContext):
    database = context.root.resolve() / 'jobs.sqlite3'
    if not database.is_file() or database.resolve() != database:
        raise ToolFailure('resource_unavailable')
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=3)) as db:
        db.row_factory = sqlite3.Row
        if db.execute('''SELECT 1 FROM web_libraries WHERE id=? AND
                         id NOT IN (SELECT library_id FROM web_deleted_libraries)''',
                      (context.library_id,)).fetchone() is None:
            raise ToolFailure('resource_unavailable')
        yield db


def _sections(context: ToolContext, ident: str) -> dict:
    from multimodal_reader import iter_automatic_sections

    if ident not in context.file_ids:
        raise ToolFailure('resource_unavailable')
    with _library(context) as db:
        row = db.execute('''SELECT f.path FROM files f WHERE f.id=? AND f.owner=? AND EXISTS (
            SELECT 1 FROM web_tasks t JOIN jobs j ON j.id=t.task_id
            JOIN json_each(j.request, '$.fileIds') ids ON ids.value=f.id
            WHERE t.library_id=? AND j.owner=f.owner)
            AND NOT EXISTS (
            SELECT 1 FROM web_removed_items WHERE library_id=? AND kind='source' AND item_id=f.id)''',
                         (ident, context.owner, context.library_id, context.library_id)).fetchone()
    if row is None:
        raise ToolFailure('resource_unavailable')
    uploads = context.root.resolve() / 'uploads'
    path = Path(row['path']).resolve()
    if uploads.resolve() != uploads or path.parent != uploads or not path.is_file():
        raise ToolFailure('resource_unavailable')
    parts = []
    remaining = 4800
    limited = False
    with closing(iter_automatic_sections(path)) as source:
        for section in source:
            if section.get('requiresVisual') or section.get('visualAssisted') or section.get('parsingError'):
                limited = True
                continue
            if section.get('pagesAvailable', 0) > section.get('pagesLimit', 0):
                limited = True
            text = usable_practice_text(section['text']).strip()
            if not text:
                continue
            if len(parts) >= 12 or remaining == 0:
                limited = True
                break
            if len(text) > remaining:
                limited = True
                prefix = text[:remaining]
                boundary = max(prefix.rfind(mark) for mark in ('。', '；', '\n', '!', '?', '？'))
                if boundary >= 0:
                    parts.append(prefix[:boundary + 1].rstrip())
                break
            parts.append(text)
            remaining -= len(text)
    if not parts:
        raise ToolFailure('insufficient_evidence')
    return {'sections': parts, 'limited': limited}


def _material(context, ident, topic=None):
    source = '\n'.join(_sections(context, ident)['sections'])
    if topic:
        scope = Scope(topic, 1, term=topic)
        source = '\n'.join(unit for unit in source_units(source) if scope.match(unit))
    if not source_units(source):
        raise ToolFailure('insufficient_evidence')
    return source


def parse_material(context, args):
    return _sections(context, args.fileId)


def extract_points(context, args):
    from .knowledge_extractor import derive_points

    return {'points': derive_points(_material(context, args.fileId, args.topic), args.goal, lambda *_: None)}


def read_progress(context, args):
    with _library(context) as db:
        rows = db.execute('''SELECT * FROM web_point_progress WHERE library_id=? AND attempts>0
                             ORDER BY mastery, point_key LIMIT 12''', (context.library_id,)).fetchall()
    return {'points': [web_practice.point_view(row) for row in rows]}


def generate_practice(context, args):
    import generate_from_file as generator

    material = _material(context, args.fileId, args.topic)
    generator.OLLAMA_URL = config.OLLAMA_URL
    generator.MODEL_NAME = config.TEXT_MODEL
    requirements = args.goal
    if args.topic:
        requirements += f'\n考查 {args.topic}，在题干或正确选项中保留该考点名称。'
    rows = generator.generate_questions(
        material, question_count=args.count, requirements=requirements, timeout=config.MODEL_TIMEOUT,
        difficulty=args.difficulty, raw_candidates=True, compact_source=True, allow_rule_generation=False)
    return {'candidates': rows}


def review_practice(context, args):
    import automatic_question_validator as validator
    from .web_question_review import validate_questions

    material = _material(context, args.fileId, args.topic)
    validator.OLLAMA_URL = config.OLLAMA_URL
    validator.REVIEW_MODEL = config.TEXT_MODEL
    validator.REVIEW_TIMEOUT = config.MODEL_TIMEOUT
    with _library(context) as db:
        archived = [json.loads(row['payload']) for row in db.execute('''
            SELECT payload FROM web_questions WHERE library_id=?
            ORDER BY saved DESC, question_id LIMIT 24''', (context.library_id,))]
    previous = [{'question': row['prompt'], 'evidenceQuote': row['ai']['evidenceQuote']}
                for row in archived if row.get('prompt') and row.get('ai', {}).get('evidenceQuote')]
    candidates = [row.model_dump(exclude_none=True) for row in args.candidates]
    if args.topic:
        scope = Scope(args.topic, 1, term=args.topic)
        candidates = [row for row in candidates if
                      scope.match(row['question'] + ' ' + row['options'][row['answer']])]
    accepted, _ = validate_questions(candidates, material, previous)
    return {'accepted': accepted, 'rejectedCount': len(args.candidates) - len(accepted)}


def study_registry() -> ToolRegistry:
    from .study_skills import skill_tool

    registry = ToolRegistry()
    for spec in (
        ToolSpec('parse_material', '读取当前任务资料的可用文字。', MaterialArgs, ParseResult,
                 'material:read', 90, parse_material),
        ToolSpec('extract_points', '从已授权资料提取有原文依据的知识点。', TopicArgs, PointsResult,
                 'material:read', 210, extract_points),
        ToolSpec('read_progress', '读取当前知识库实际作答后的掌握估计。', Empty, ProgressResult,
                 'progress:read', 10, read_progress),
        ToolSpec('generate_practice', '从已授权资料生成待审核的单选题。', GenerateArgs, CandidatesResult,
                 'practice:generate', 240, generate_practice),
        ToolSpec('review_practice', '核对候选题的原文依据、答案和重复项。', ReviewArgs, ReviewResult,
                 'practice:review', 240, review_practice),
    ):
        registry.register(spec)
    registry.register(skill_tool())
    return registry
