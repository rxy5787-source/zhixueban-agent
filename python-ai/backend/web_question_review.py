"""Blind batch review of candidates against indexed source text for Web tasks."""
import json
import re
import unicodedata
from typing import Literal

import requests
from pydantic import BaseModel, ConfigDict, ValidationError

import automatic_question_validator as validator
from .literal_evidence import review_quantity
from .practice_quality import source_units, standalone_issue


class Review(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')

    id: int
    answer: Literal['A', 'B', 'C', 'D', 'X']
    issue: Literal['ok', 'ambiguous', 'unsupported', 'visual', 'vague']


ISSUES = {
    'ambiguous': '独立解答发现题目存在歧义或多个正确选项',
    'unsupported': '原文无法直接支撑唯一答案',
    'visual': '需要查看未提供的图片或图表才能作答',
    'vague': '题意不明确或选项不能按同一标准比较',
}

NAMED_ENTRY = re.compile(r'^([^：:，。；;]{2,45})[：:]')
GENERIC_ANSWER = re.compile(r'^([\w\u4e00-\u9fff]{2,8})(?:方式|方法|类型|类别)$')
NAMED_OPTION = re.compile(r'(.+?)\s*\(([A-Z][A-Z0-9-]{1,9})\)$')


def leaks_answer(stem, option):
    option = unicodedata.normalize('NFKC', option).strip()
    stem = unicodedata.normalize('NFKC', stem)
    named = NAMED_OPTION.fullmatch(option)
    if named:
        option, alias = named.groups()
        if re.search(rf'(?<![A-Za-z0-9_-]){re.escape(alias)}(?![A-Za-z0-9_-])', stem, re.IGNORECASE):
            return True
    answer = validator.normalize(option)
    min_length = 5 if re.search(r'[\u4e00-\u9fff]', answer) else 8
    return len(answer) >= min_length and answer in validator.normalize(stem)


def resolve_evidence(question, units):
    proposed = question['explanation'].strip()
    if proposed not in units:
        return ''
    # An exact glossary heading can repair a misnumbered citation before blind review.
    point = validator.normalize(question['knowledgePoint'])
    matches = [unit for unit in units if (entry := NAMED_ENTRY.match(unit))
               and validator.normalize(entry[1]) == point]
    return matches[0] if len(matches) == 1 else proposed


def request_reviews(candidates, units):
    # Independently answer using the cited literal evidence, without the proposed answer.
    tasks = [{'id': ident, 'question': q['question'], 'options': q['options'], 'evidence': q['explanation']}
             for ident, q in candidates.items()]
    cited = {task['evidence'] for task in tasks}
    other_source = '\n'.join(unit for unit in units if unit not in cited)
    prompt = (
        '独立检查每题的四个选项。只有本题 evidence 支持唯一答案才用 ok。'
        '其他资料与其他题的引文可以用来发现冲突，不能代替本题 evidence。'
        '多解用 ambiguous，证据不足用 unsupported，依赖图表用 visual，题意或选项无法判定用 vague。'
        '以上四类的 answer 用 X。每题返回一次 id、answer、issue，只输出 JSON。\n'
    )
    if other_source:
        prompt += f'其他资料：\n{other_source}\n'
    prompt += '待答题目：' + json.dumps(tasks, ensure_ascii=False, separators=(',', ':'))
    schema = {'type': 'object', 'properties': {'reviews': {
        'type': 'array', 'minItems': len(tasks), 'maxItems': len(tasks),
        'items': Review.model_json_schema()}}, 'required': ['reviews'], 'additionalProperties': False}
    response = requests.post(validator.OLLAMA_URL, json={
        'model': validator.REVIEW_MODEL, 'messages': [{'role': 'user', 'content': prompt}],
        'format': schema, 'stream': False, 'think': False,
        'options': {'temperature': 0, 'num_ctx': 4096, 'num_predict': 256},
    }, timeout=(10, validator.REVIEW_TIMEOUT))
    validator.checked_model_response(response, validator.REVIEW_MODEL)
    result = response.json()
    if validator.AUDIT:
        validator.AUDIT('batch_review', result)
    rows = json.loads(result['message']['content'])['reviews']
    if not isinstance(rows, list):
        raise ValueError('模型未返回复核列表')
    return rows


def validate_questions(questions, source, previous):
    units = source_units(source)
    errors = {}
    literals = {}
    pending = {}
    evidence = {}
    previous_evidence = {q['evidenceQuote'] for q in previous if 'evidenceQuote' in q}
    for ident, q in enumerate(questions, 1):
        reasons = errors[ident] = validator.check_structure(q)
        if reasons:
            continue
        answer = validator.normalize(q['options'][q['answer']])
        stem = validator.normalize(q['question'])
        generic = GENERIC_ANSWER.fullmatch(answer)
        if leaks_answer(q['question'], q['options'][q['answer']]):
            reasons.append('题干直接包含正确选项，泄露答案')
        elif generic and generic[1] in stem and re.search(r'什么方式|哪种方式|方式是什么|属于哪(?:种|类)', stem):
            reasons.append('正确选项只是复述题干中的类别名称，缺少可区分的考点')
        elif not (quote := resolve_evidence(q, units)):
            reasons.append('出题时缺少可定位的完整原文依据')
        elif issue := standalone_issue(q['question'], quote, list(q['options'].values())):
            reasons.append(issue)
        elif quote in previous_evidence:
            reasons.append('与已保留题目重复考查同一证据或题意')
        elif validator.find_near_duplicate(q['question'], previous):
            reasons.append('与已保留的题目文字高度相似')
        else:
            evidence[ident] = quote
            literal = review_quantity(q, source)
            if literal:
                literals[ident] = literal
                if validator.AUDIT:
                    validator.AUDIT('literal_review', dict(literal, method='literal_quantity_v1'))
            else:
                pending[ident] = dict(q, explanation=quote)

    reviews = {}
    seen = set()
    if pending:
        try:
            for row in request_reviews(pending, units):
                ident = row.get('id') if isinstance(row, dict) else None
                if type(ident) is not int or ident not in pending:
                    continue
                if ident in seen:
                    reviews.pop(ident, None)
                    continue
                seen.add(ident)
                try:
                    reviews[ident] = Review.model_validate(row)
                except ValidationError:
                    continue
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            for ident in pending:
                errors[ident].append(f'批量独立核验失败：{str(exc)[:120]}')

    passed, rejected = [], []
    evidence_used = previous_evidence.copy()
    for ident, q in enumerate(questions, 1):
        reasons = errors[ident]
        quote = ''
        method = 'batch_indexed_v1'
        if not reasons and ident in literals:
            literal = literals[ident]
            method = 'literal_quantity_v1'
            quote = literal['evidenceQuote']
            if literal['selectedAnswers'] != [q['answer']] or quote != evidence[ident]:
                reasons.append('独立核对的数值、答案或原文依据不一致')
        elif not reasons:
            review = reviews.get(ident)
            if not review:
                reasons.append('缺少唯一有效的独立复核记录')
            elif review.issue != 'ok':
                reasons.append(ISSUES[review.issue])
            elif review.answer != q['answer']:
                reasons.append('独立解答与生成答案不一致')
            else:
                quote = evidence[ident]
        if not reasons:
            if quote in evidence_used or validator.find_near_duplicate(q['question'], passed):
                reasons.append('与已保留题目重复考查同一证据或题意')
        if reasons:
            rejected.append({'indexInPart': ident, 'question': q if isinstance(q, dict) else repr(q),
                             'reasons': reasons, 'status': 'rejected_or_needs_review'})
            continue
        evidence_used.add(quote)
        passed.append(dict(q, explanation=quote, evidenceQuote=quote, reviewStatus='auto_prechecked',
                           reviewMethod=method, reviewModel=validator.REVIEW_MODEL if method == 'batch_indexed_v1' else method,
                           explanationModel='indexed_source_v1'))
    return passed, rejected
