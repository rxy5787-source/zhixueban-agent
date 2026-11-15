"""Checks for numbered placeholders and detached multiple-choice options."""

import re
import unicodedata

NUMBER = r'[0-9零〇一二两三四五六七八九十百]+'
OPTION_ROW = re.compile(
    rf'^(?:(?:问题|题目|第)\s*{NUMBER}(?:\s*题)?\s*[:、.]\s*|\(\s*{NUMBER}\s*\)\s*)?'
    r'[A-D]\s*[.、:)]\s*\S'
)
NUMBERED_QUESTION = re.compile(
    rf'^(?:请问\s*)?(?:问题|题目|第)\s*{NUMBER}(?:\s*[小道]?[题问])?\s*'
    r'(?:的\s*)?(?:正确\s*|标准\s*)?(?:答案|选项)(?:\s*(?:是|为|选|应该|[:?])|$)'
)
SUBJECTIVE_COMPARISON = re.compile(
    r'最(?:为)?(?:简单|容易|方便|好(?!处)|快捷|高效|快(?!速排序)|佳)'
)
COMPARISON_CRITERION = re.compile(
    r'时间复杂度|空间复杂度|比较次数|交换次数|步骤数|耗时|用时|存储开销|访问次数|传输时间|响应时间|延迟|吞吐量|时钟周期'
)
CONTEXT_FRAGMENT = re.compile(
    r'^(?:还有(?:一个|个)?原因|另一个原因|这道题|这一题|(?:公式|计算|推导|过程|步骤)太(?:复杂|繁琐|麻烦)[,，])'
)
SOURCE_UNIT = re.compile(r'[^。；;\n]+[。；;]?')
FORMULA_CELL = re.compile(r'[\d\WnN]+')


def is_option_row(text):
    return isinstance(text, str) and bool(
        OPTION_ROW.match(unicodedata.normalize('NFKC', text).strip())
    )


def remove_option_rows(material):
    return '\n'.join(line for line in material.splitlines() if not is_option_row(line))


def usable_practice_text(material):
    return '\n'.join(
        line
        for line in remove_option_rows(material).splitlines()
        if not CONTEXT_FRAGMENT.match(line.strip())
    )


def source_units(material):
    return list(
        dict.fromkeys(
            text
            for match in SOURCE_UNIT.finditer(material)
            if (text := match.group().strip())
            and len(re.sub(r'\W', '', text)) >= 8
            and not text.endswith(('=', '＝', ':', '：', '，', ','))
            and not is_option_row(text)
        )
    )


def split_practice_text(material, limit):
    """Pack complete source units together before sending them to the model."""
    part = []
    length = 0
    for unit in source_units(material):
        if part and length + len(unit) + 1 > limit:
            yield '\n'.join(part)
            part, length = [], 0
        for offset in range(0, len(unit) - limit, limit):
            yield unit[offset : offset + limit]
        unit = unit[((len(unit) - 1) // limit) * limit :]
        part.append(unit)
        length += len(unit) + 1
    if part:
        yield '\n'.join(part)


def looks_like_ocr_table(material):
    lines = [line.strip() for line in material.splitlines() if line.strip()]
    if not lines or not re.match(rf'^表\s*{NUMBER}', lines[0]):
        return False
    cells = lines[1:]

    def is_formula(cell):
        folded = unicodedata.normalize('NFKC', cell).replace('n', '').replace('N', '')
        return (
            bool(FORMULA_CELL.fullmatch(folded))
            and any(char.isdigit() for char in folded)
            and any(char in '=~∼±−^+-' for char in folded)
        )

    return sum(is_formula(cell) for cell in cells) >= 2 and all(
        is_formula(cell) or (len(cell) <= 24 and not re.search(r'[。；！？]', cell))
        for cell in cells
    )


def standalone_issue(stem, evidence):
    if isinstance(stem, str) and NUMBERED_QUESTION.match(
        unicodedata.normalize('NFKC', stem).strip()
    ):
        return '题干只引用原资料的题号，缺少可独立作答的题意'
    if is_option_row(evidence):
        return '只有原资料的选项，缺少支持答案的正文或解析'
    if (
        isinstance(stem, str)
        and SUBJECTIVE_COMPARISON.search(stem)
        and not COMPARISON_CRITERION.search(stem)
    ):
        return '比较题缺少可检验的判断标准'
    if isinstance(evidence, str) and CONTEXT_FRAGMENT.match(evidence.strip()):
        return '依据只是一段脱离上下文的讲解，缺少可独立验证的条件'
    return ''
