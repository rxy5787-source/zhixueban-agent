"""Bounded cross-task context for evidence-backed Web practice."""
import re
from dataclasses import dataclass

from automatic_question_validator import find_near_duplicate, normalize


EXHAUSTED = '本次资料中没有足够的新证据支持不同的练习题。可补充同一知识点的例子、规则或常见错误后再试。'
REPEATED = '与本知识库近期题目重复考查同一事实或高度相似'

ANGLES = {
    '概念理解': '围绕一个未考过的事实，判断概念的含义或适用条件。',
    '实际应用': '给一个资料能直接解决的小场景，问应该用哪条规则或怎样做。',
    '错误辨析': '给出一个容易混淆的判断或错误做法，问如何纠正或区分。',
}


def question_angle(stem):
    if re.search(r'误用|误以为|误把|误将|错误|错在|纠正|区别|混淆|原以为', stem):
        return '错误辨析'
    if re.search(r'要想|要找|要筛|需要|想要|希望|某同学|某查询|小明|如果|场景|当.+时', stem):
        return '实际应用'
    return '概念理解'


@dataclass(frozen=True)
class PracticePlan:
    recent: tuple = ()
    weak_points: tuple = ()

    @property
    def evidence(self):
        return {item['evidence'] for item in self.recent if item['evidence']}

    def instructions(self):
        if not self.recent:
            return ''
        weak = {normalize(point) for point in self.weak_points}
        relevant = [item for item in self.recent if normalize(item['point']) in weak]
        focus = relevant or self.recent
        last_angle = focus[0]['angle']
        next_angle = next(angle for angle in ANGLES if angle != last_angle and
                          angle not in {item['angle'] for item in focus[:2]})
        records = '\n'.join(
            f"{item['point'][:32]} · 四选一 · {item['angle']} · {item['outcome']}"
            for item in focus[:4]
        )
        labels = f"若继续考查这些薄弱点，沿用已有标签{'、'.join(self.weak_points)}。" if self.weak_points else ''
        return (
            f'近期练习（这些内容已考过）：\n{records}\n'
            f'本轮用新资料编号，优先用「{next_angle}」考查尚未覆盖的事实。{ANGLES[next_angle]}'
            f'{labels}不要再问上一题的结论。若剩余资料无足够依据，请返回空题数组。'
        )

    def duplicate(self, question, quote):
        if quote in self.evidence or find_near_duplicate(question['question'], self.recent):
            return True
        point = normalize(question['knowledgePoint'])
        answer = normalize(question['options'][question['answer']])
        stem = normalize(question['question'])
        pairs = {stem[i:i+2] for i in range(len(stem)-1)}
        for item in self.recent:
            if point != normalize(item['point']) or answer != normalize(item['answer']):
                continue
            old = normalize(item['question'])
            old_pairs = {old[i:i+2] for i in range(len(old)-1)}
            if pairs and old_pairs and len(pairs & old_pairs) / min(len(pairs), len(old_pairs)) >= .67:
                return True
        return False
