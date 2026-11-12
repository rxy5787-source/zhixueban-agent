"""知学伴：自动试题预筛选（结构 / 去重 / 原文证据 / AI 独立解答）。

可直接由 batch_generate_questions_v2.py 调用。
注意：自动预筛选并非事实正确性的证明；对高风险题型需另建确定性验证。
"""
from __future__ import annotations

import re
REVIEW_TIMEOUT = 600
import unicodedata
from difflib import SequenceMatcher
from typing import Literal

import requests
from backend.model_status import checked_model_response
from backend.practice_quality import standalone_issue
AUDIT = None
from pydantic import BaseModel, ValidationError

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
REVIEW_MODEL = "qwen3:1.7b"  # 可改为已安装的更强文本模型
LETTERS = ("A", "B", "C", "D")
DIFFICULTIES = {"简单", "中等", "困难"}


class IndependentReview(BaseModel):
    """审题模型独立作答；不向它提供生成模型标注的答案。"""
    selectedAnswers: list[Literal["A", "B", "C", "D"]]
    answerableFromSource: bool
    ambiguous: bool
    evidenceQuote: str
    requiresVisual: bool
    reviewMethod: str = 'model'



class ExplanationReview(BaseModel):
    consistent: bool
    supportedBySource: bool
    issues: list[str]


def review_explanation(q: dict, source_text: str) -> ExplanationReview:
    # Separate from independent answering: this request checks the generated explanation.
    prompt = "核对题目解析。逐句检查解析是否与资料、题目选项一致，是否错误归因或引入原文无法支持的断言。只有全部一致且有据才能放行。issues逐条列出问题；没有问题返回[]。只返回JSON。\n资料：\n" + source_text + "\n待核对题目：\n" + __import__('json').dumps(q,ensure_ascii=False)
    response = requests.post(OLLAMA_URL,json={"model":REVIEW_MODEL,"messages":[{"role":"user","content":prompt}],"stream":False,"think":False,"format":ExplanationReview.model_json_schema(),"options":{"temperature":0,"num_ctx":4096,"num_predict":500}},timeout=(10,REVIEW_TIMEOUT))
    checked_model_response(response,REVIEW_MODEL)
    data=response.json()
    if AUDIT: AUDIT("explanation",data)
    return ExplanationReview.model_validate_json(data["message"]["content"])


def normalize(text: object) -> str:
    text = unicodedata.normalize("NFKC", str(text)).casefold()
    return re.sub(r"[^\w\u4e00-\u9fff]", "", text, flags=re.UNICODE)


def check_structure(q: object) -> list[str]:
    errors = []
    if not isinstance(q, dict):
        return ["题目不是JSON对象"]
    if not isinstance(q.get("question"), str) or len(q["question"].strip()) < 6:
        errors.append("题干为空或过短")
    opts = q.get("options")
    if not isinstance(opts, dict) or set(opts) != set(LETTERS):
        errors.append("选项必须恰好包含A/B/C/D")
    else:
        values = [opts[k] for k in LETTERS]
        if any(not isinstance(v, str) or not v.strip() for v in values):
            errors.append("选项存在空值或非文本")
        elif len({normalize(v) for v in values}) != 4:
            errors.append("存在内容相同的选项")
        else:
            from backend.literal_evidence import quantity
            quantities=[quantity(value) for value in values]
            if all(value is not None for value in quantities) and len(set(quantities))!=4:
                errors.append('存在数值与单位含义相同的选项')
    if q.get("answer") not in LETTERS:
        errors.append("标准答案必须是A/B/C/D之一")
    for name in ("explanation", "knowledgePoint"):
        if not isinstance(q.get(name), str) or not q[name].strip():
            errors.append(f"缺少{name}")
    if not isinstance(q.get("difficulty"), str) or q["difficulty"] not in DIFFICULTIES:
        errors.append("难度必须是简单/中等/困难")
    if q.get("difficultyError"):
        errors.append("题目难度不符合本次要求")
    if q.get("mappingError"):
        errors.append("知识点不在本次规范目录中")
    stem = q.get("question", "")
    issue = standalone_issue(stem, q.get('explanation'))
    if issue:
        errors.append(issue)
    if isinstance(stem,str) and normalize(stem)==normalize(q.get('explanation','')):
        errors.append('题干直接复制了解析并泄露答案，不能作为独立练习题')
    if isinstance(stem,str) and re.search(r'哪[一]?句原文|sourceIndex|原文.{0,4}编号',stem):
        errors.append('题目考查内部原文编号，不能作为独立的知识题')
    if isinstance(opts,dict) and any(isinstance(v,str) and re.search(r'原文第.{0,4}[句段]|sourceIndex',v) for v in opts.values()):
        errors.append('选项依赖内部原文编号，不能独立作答')
    if isinstance(stem, str) and re.search(r"如图|下图|图中|图形分|填入问号|上述三句|上述四|根据上文|图示|表中|该图|该表|阴影部分|根据.{0,8}[图表]", stem):
        errors.append("题目依赖缺失的图形或上下文，不能独立作答")
    return errors


def find_near_duplicate(question: str, previous: list[dict]) -> bool:
    stem = normalize(question)
    for old in previous:
        other = normalize(old.get("question", ""))
        if stem and other and (
            stem == other or
            (min(len(stem), len(other)) >= 10 and
             SequenceMatcher(None, stem, other).ratio() >= 0.90)
        ):
            return True
    return False


def independent_review(q: dict, source_text: str) -> IndependentReview:
    """另起一次请求：只给题干与选项，不提供原答案和解析。"""
    from backend.literal_evidence import review_quantity
    literal=review_quantity(q,source_text)
    if literal:
        if AUDIT:AUDIT('literal_review',dict(literal,method='literal_quantity_v1'))
        return IndependentReview(selectedAnswers=literal['selectedAnswers'],evidenceQuote=literal['evidenceQuote'],
                                 answerableFromSource=True,ambiguous=False,requiresVisual=False,reviewMethod='literal_quantity_v1')
    options = "\n".join(f"{k}. {q['options'][k]}" for k in LETTERS)
    prompt = f"""你是严格的试题事实核验助手。仅依据下方资料独立作答。
注意：没有看到原标准答案。不得借助资料之外的常识填补证据。
如果不能从资料确定唯一答案，selectedAnswers返回[]、answerableFromSource=false。
如果多个选项可能正确，返回所有可能正确选项，并设置ambiguous=true。
evidenceQuote必须逐字复制资料中的一段原文，不能改写；找不到就返回空字符串。
资料可能来自OCR。不得补全空白、未填写的公式或答案；仅有标题、坐标标签不等于存在完整事实。
如果作答必须查看未提供的图片、图表、排版位置或几何关系，requiresVisual=true，answerableFromSource=false。
只输出符合JSON schema的对象。

【原始资料】
{source_text}

【题目】
{q['question']}
{options}
"""
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": REVIEW_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": False,
            "format": IndependentReview.model_json_schema(),
            "options": {"temperature": 0, "num_ctx": 4096},
        },
        timeout=(10, REVIEW_TIMEOUT),
    )
    checked_model_response(response,REVIEW_MODEL)
    data = response.json()
    if AUDIT: AUDIT("review", data)
    return IndependentReview.model_validate_json(data["message"]["content"])


def validate_questions(
    questions: list[dict], source_text: str, previous_questions: list[dict] | None = None
) -> tuple[list[dict], list[dict]]:
    """返回(自动初筛通过, 自动淘汰/待处理)；不要求用户逐题人工检查。"""
    passed, rejected = [], []
    previous_questions = previous_questions or []
    for index, q in enumerate(questions, start=1):
        reasons = check_structure(q)
        duplicate_pool=previous_questions+passed
        if not reasons:
            from backend.literal_evidence import review_quantity
            candidate_proof=review_quantity(q,source_text)
            if candidate_proof:
                filtered=[]
                for old in duplicate_pool:
                    old_proof=review_quantity(old,source_text)
                    distinct=(old_proof and old_proof['value']!=candidate_proof['value']
                              and old_proof['evidenceQuote']!=candidate_proof['evidenceQuote']
                              and normalize(old.get('question',''))!=normalize(q['question']))
                    if not distinct:filtered.append(old)
                duplicate_pool=filtered
        if not reasons and find_near_duplicate(q["question"], duplicate_pool):
            reasons.append("与已保留的题目文字高度相似")
        if not reasons and not source_text.strip():
            reasons.append("原始资料为空")
        if not reasons and (len(normalize(q["explanation"]))<8 or q["explanation"].strip() not in source_text):
            reasons.append("解析必须是与答案相关的逐字原文摘录，不接受模型自由扩展断言")
        review = None
        if not reasons:
            try:
                review = independent_review(q, source_text)
            except (requests.RequestException, ValidationError, ValueError, KeyError, TypeError) as e:
                reasons.append(f"AI核验失败：{type(e).__name__}: {str(e)[:120]}")
            else:
                if review.requiresVisual:
                    reasons.append("题目需要查看原图或图表，文字证据不足，不能自动导入")
                if not review.answerableFromSource:
                    reasons.append("模型认为原文无法直接确定答案")
                if review.ambiguous or len(review.selectedAnswers) != 1:
                    reasons.append("模型认为答案不唯一或存在歧义")
                elif review.selectedAnswers[0] != q["answer"]:
                    reasons.append("独立解答与生成答案不一致")
                quote = review.evidenceQuote.strip()
                if len(normalize(quote)) < 8 or quote not in source_text:
                    reasons.append("缺少能够在原文中定位的有效逐字证据")
                if review.reviewMethod=='literal_quantity_v1' and q['explanation'].strip()!=quote:
                    reasons.append('解析引用与独立核对的数量证据不一致')
        if not reasons and review.reviewMethod!='literal_quantity_v1':
            try:
                explanation = review_explanation(q, source_text)
                if not explanation.consistent or not explanation.supportedBySource or explanation.issues:
                    reasons.append("解析存在不一致或缺乏原文依据：" + "; ".join(explanation.issues))
            except (requests.RequestException, ValidationError, ValueError, KeyError, TypeError) as exc:
                reasons.append(f"解析核验失败：{type(exc).__name__}: {str(exc)[:120]}")
        if reasons:
            rejected.append({
                "indexInPart": index,
                "question": q if isinstance(q, dict) else repr(q),
                "reasons": reasons,
                "status": "rejected_or_needs_review",
            })
        else:
            passed.append({
                **q,
                "evidenceQuote": review.evidenceQuote,
                "reviewStatus": "auto_prechecked",
                "reviewModel": review.reviewMethod if review.reviewMethod!='model' else REVIEW_MODEL,
                "explanationModel": review.reviewMethod if review.reviewMethod=='literal_quantity_v1' else REVIEW_MODEL,
                "reviewMethod": review.reviewMethod,
            })
    return passed, rejected
