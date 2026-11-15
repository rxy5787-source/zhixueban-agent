"""Deterministic checking of a narrow, explicit conditional quantity statement.

This does not fill blanks or infer answers. It only matches an exact condition
and action present in both question and source, with four distinct scalar options.
All other questions continue through independent model review.
"""

import re
import unicodedata
import hashlib
import random

NUMBER = r'(?:[0-9]{1,3}|[零〇一二两三四五六七八九十]{1,3})'
UNIT = r'(?:分钟|小时|位|个|次|年|月|天|秒|层|字|步|项|种)'
SCALAR = re.compile(rf'^({NUMBER})\s*({UNIT})$')
FACT = re.compile(
    rf'^([^（(：:）)]{{4,}})[（(：:]\s*([^0-9零〇一二两三四五六七八九十）)]*?)({NUMBER})\s*({UNIT})\s*[）)]?[。.]?$'
)


def clean(text):
    return re.sub(r'\W', '', unicodedata.normalize('NFKC', text))


def integer(text):
    if text.isdecimal():
        return int(text)
    digits = dict(zip('零〇一二两三四五六七八九', [0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9]))
    if len(text) == 1:
        return 10 if text == '十' else digits.get(text)
    match = re.fullmatch(r'([一二两三四五六七八九])?十([一二三四五六七八九])?', text)
    if match:
        return digits.get(match[1], 1) * 10 + digits.get(match[2], 0)
    return None


def quantity(text):
    match = SCALAR.fullmatch(unicodedata.normalize('NFKC', text.strip()))
    if not match:
        return None
    number = integer(match[1])
    return (number, match[2]) if number is not None else None


def question_hints(segments):
    hints = []
    for index, line in enumerate(segments):
        match = FACT.fullmatch(unicodedata.normalize('NFKC', line))
        if not match:
            continue
        condition, action, number, unit = match.groups()
        if integer(number) is None or len(clean(condition)) < 4:
            continue
        stem = (
            f'{condition}时，应{action}几{unit}？'
            if action.strip()
            else f'{condition}是多少{unit}？'
        )
        hints.append({'sourceIndex': index, 'questionFocus': stem})
    return hints


def questions_from_facts(segments, points, count, difficulty=0, requirements=''):
    if difficulty not in (0, 1) or not points:
        return []
    hints = question_hints(segments)
    if len(hints) != len(segments):
        return []
    matching = [
        hint
        for hint in hints
        if clean(FACT.fullmatch(unicodedata.normalize('NFKC', segments[hint['sourceIndex']]))[1])
        in clean(requirements)
    ]
    if re.search(r'重点|只考|考查|仅考', requirements) and not matching:
        return []
    if matching:
        hints = matching
    result = []
    for hint in hints:
        line = segments[hint['sourceIndex']]
        match = FACT.fullmatch(unicodedata.normalize('NFKC', line))
        value = integer(match[3])
        unit = match[4]
        point = next((p for p in points if line in p['summary'] or p['summary'] == line), None)
        if value is None or point is None:
            continue
        # Distractors differ only in quantity; none claims another unsupported fact.
        others = []
        for candidate in (value - 1, value + 1, value + 2, value - 2, value + 3):
            if candidate >= 0 and candidate != value and candidate not in others:
                others.append(candidate)
        values = [value] + others[:3]
        random.Random(hashlib.sha256(line.encode('utf-8')).digest()).shuffle(values)
        options = {letter: f'{number}{unit}' for letter, number in zip('ABCD', values)}
        answer = 'ABCD'[values.index(value)]
        result.append(
            {
                'question': hint['questionFocus'],
                'options': options,
                'answer': answer,
                'explanation': line,
                'knowledgePoint': point['name'],
                'difficulty': '简单',
                'questionConstruction': 'source_quantity_template_v1',
                'generationModel': 'source_quantity_template_v1',
            }
        )
        if len(result) >= count:
            break
    return result


def review_quantity(question, source):
    stem = question.get('question', '')
    if re.search(
        r'不|非|错误|例外|至少|至多|最大|最小|以上|以下|如图|下图|图中|图示|图形|表中|该图|该表|阴影',
        stem,
    ):
        return None
    options = question.get('options', {})
    if set(options) != set('ABCD'):
        return None
    quantities = {letter: quantity(options[letter]) for letter in 'ABCD'}
    if any(value is None for value in quantities.values()) or len(set(quantities.values())) != 4:
        return None
    units = {value[1] for value in quantities.values()}
    if len(units) != 1:
        return None
    unit = next(iter(units))
    if not re.search(r'(?:几|多少)\s*' + re.escape(unit), stem):
        return None
    evidence = []
    for line in source.splitlines():
        line = line.strip()
        match = FACT.fullmatch(unicodedata.normalize('NFKC', line))
        if not match:
            continue
        condition, action, number, source_unit = match.groups()
        # Scope must appear literally in the question. No semantic guessing.
        if len(clean(condition)) < 4 or clean(condition) not in clean(stem):
            continue
        if clean(action) and clean(action) not in clean(stem):
            continue
        value = integer(number)
        if source_unit == unit and value is not None:
            evidence.append(((value, unit), line))
    if not evidence or len({value for value, line in evidence}) != 1:
        return None
    value, quote = evidence[0]
    selected = [letter for letter, option in quantities.items() if option == value]
    if len(selected) != 1:
        return None
    return {'selectedAnswers': selected, 'evidenceQuote': quote, 'value': value[0], 'unit': unit}
