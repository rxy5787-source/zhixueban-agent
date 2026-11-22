"""Plan bounded source and topic coverage before requesting any questions."""
from dataclasses import dataclass
import re
import unicodedata

from .literal_evidence import integer
from .practice_quality import source_units

NUMBER = r'(?:[1-9][0-9]?|十[一二]?|[一二两三四五六七八九])'
TERM = r'(?:[A-Za-z][A-Za-z0-9.+#_-]*(?:\s+BY)?|[\u4e00-\u9fff]{2,20})'
SEPARATOR = r'[、，,;；]|\s*(?:以及|和|与|及)\s*'
CUE = r'覆盖|考查|考察|考核|围绕|考点[:：]|知识点[:：]|针对'
FILE_ONLY = re.compile(r'^(?:这|该|以上|所有|各|上传的|本知识库)?(?:资料|文件|学习资料|薄弱知识点|知识点|考点|练习|重点|内容|同一知识点)')
TOTAL = re.compile(rf'(?:共(?:计)?|合计|总数(?:为)?)\s*({NUMBER})\s*(?:道|题)')
QUANTITY_DIRECTIVE = re.compile(
    r'^(?:请|帮我)?(?:生成|出|给我|做|练)\s*'
    r'(?:(?:入门|基础|简单|中等|适中|普通|提高|进阶|困难|较难)(?:难度)?(?:的)?)?$')


@dataclass(frozen=True)
class Scope:
    label: str
    quota: int
    term: str = ''
    file_id: str = ''

    def match(self, text):
        if not self.term:
            return True
        folded = unicodedata.normalize('NFKC', text).casefold()
        term = self.term.casefold()
        if term.isascii():
            return bool(re.search(r'(?<![a-z0-9])' + re.escape(term) + r'(?![a-z0-9])', folded))
        return term in folded

    def material(self, batch):
        if self.file_id and self.file_id != batch.source['id']:
            return ''
        if not self.term:
            return batch.text
        return '\n'.join(unit for unit in source_units(batch.text) if self.match(unit))


def topic_label(text):
    label = re.sub(r'^(?:请|重点|分别|包含|涉及|关于|的|包括|\s)+', '', text).strip()
    label = re.sub(r'^SQL\s*(?:中的|的)\s*(?=[A-Za-z])', '', label, flags=re.I)
    match = re.match(r'[A-Za-z][A-Za-z0-9.+#_-]*(?:\s+BY)?', label, re.I)
    if match:
        return match.group().strip().upper()
    label = re.sub(r'(?:这两个|两个|这两|等)?(?:知识点|考点|主题)(?:的题目)?$', '', label)
    if re.fullmatch(r'[\u4e00-\u9fff]{2,20}', label) and not FILE_ONLY.match(label):
        return label
    return ''


def named_topics(requirements):
    text = unicodedata.normalize('NFKC', requirements)
    # Quantified allocations have precedence over unweighted coverage instructions.
    shared = re.search(rf'([^。；;:\n]+?)\s*各(?:出|生成)?\s*({NUMBER})\s*(?:道|题)', text)
    if shared:
        clause = re.split(CUE + r'|[,，]', shared[1])[-1]
        labels = [topic_label(item) for item in re.split(SEPARATOR, clause)]
        if len(labels) >= 2 and all(labels):
            return dict.fromkeys(labels, integer(shared[2]))
    allocations = {}
    for match in re.finditer(rf'(?:^|[、，,;；]|以及|和|与)\s*({TERM})\s*(?:出|生成|各)?\s*({NUMBER})\s*(?:道|题)', text):
        if QUANTITY_DIRECTIVE.fullmatch(match[1].strip()):
            continue
        label = topic_label(match[1])
        if label and label not in {'分别', '生成', '请生成', '出题', '请出', '本轮', '总共', '共计', '合计'}:
            allocations[label] = integer(match[2])
    if allocations:
        return allocations
    match = re.search(rf'(?:{CUE})\s*([^，,。；;\n]+)', text)
    if not match:
        return {}
    clause = re.split(r'\s*(?:各(?:出|生成)?|分别出|用原文|出题|并|每个)', match[1], maxsplit=1)[0]
    labels = [topic_label(item) for item in re.split(SEPARATOR, clause)]
    return dict.fromkeys((label for label in labels if label), None)


def make_scopes(requirement, total, batches, weak_points=()):
    explicit = named_topics(requirement)
    if not explicit and weak_points and re.search('薄弱|巩固', requirement):
        explicit = dict.fromkeys(weak_points[:total], None)
    if explicit:
        fixed = all(value is not None for value in explicit.values())
        if fixed:
            count = sum(explicit.values())
            declared = TOTAL.search(unicodedata.normalize('NFKC', requirement))
            if not 1 <= count <= 12 or (declared and integer(declared[1]) != count):
                raise ValueError('各考点题量与总题量不一致，或超出 1–12 道，请调整要求。')
            total = count
        if total < len(explicit):
            raise ValueError('题量少于指定考点数，每个考点至少需要一道。')
        each, extra = divmod(total, len(explicit))
        return total, [Scope(label, count if fixed else each + (i < extra), term=label)
                       for i, (label, count) in enumerate(explicit.items())]
    sources = list({batch.source['id']: batch.source['name'] for batch in batches}.items())
    if len(sources) > 1 and total >= len(sources):
        each, extra = divmod(total, len(sources))
        return total, [Scope(name, each + (i < extra), file_id=ident) for i, (ident, name) in enumerate(sources)]
    return total, [Scope('可用资料', total)]
