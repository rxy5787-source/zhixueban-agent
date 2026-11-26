"""Catalog and on-demand loading for repository-owned teaching strategies."""
import hashlib
import json
from pathlib import Path
import re
from typing import Annotated

from pydantic import StringConstraints

from .tool_registry import Contract, ToolFailure, ToolSpec

ROOT = Path(__file__).resolve().with_name('study_skills')
NAME = re.compile(r'[a-z][a-z_]{0,39}')


class SkillArgs(Contract):
    name: Annotated[str, StringConstraints(pattern=r'^[a-z][a-z_]{0,39}$')]


class SkillResult(Contract):
    name: str
    version: str
    instructions: Annotated[str, StringConstraints(min_length=1, max_length=4000)]


def catalog():
    entries = json.loads((ROOT / 'catalog.json').read_text(encoding='utf-8'))
    if (not isinstance(entries, dict) or not 1 <= len(entries) <= 20
            or any(not NAME.fullmatch(name) or not isinstance(line, str)
                   or not 1 <= len(line) <= 120 or '\n' in line for name, line in entries.items())):
        raise ValueError('Invalid study skill catalog')
    return entries


def load(context, args):
    if args.name not in catalog():
        raise ToolFailure('resource_unavailable')
    path = ROOT / f'{args.name}.md'
    if path.resolve() != path:
        raise ToolFailure('resource_unavailable')
    with path.open('rb') as source:
        raw = source.read(16_001)
    if len(raw) > 16_000:
        raise ValueError('Skill exceeds size limit')
    body = raw.decode('utf-8').strip()
    return {'name': args.name, 'version': hashlib.sha256(raw).hexdigest(), 'instructions': body}


def skill_tool():
    summaries = '；'.join(f'{name}：{summary}' for name, summary in catalog().items())
    return ToolSpec('load_study_skill', '按需读取教学策略。' + summaries,
                    SkillArgs, SkillResult, 'skill:read', 10, load)
