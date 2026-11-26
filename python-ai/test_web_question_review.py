from unittest.mock import Mock
import pytest
from pydantic import ValidationError

from backend import web_question_review as review
from backend.practice_variety import PracticePlan, REPEATED, question_angle
from backend.schemas import JobRequest


def test_short_answer_token_is_flagged_only_when_named_in_the_stem():
    assert review.leaks_answer('在 SQL WHERE 子句中，应使用哪个子句？', 'WHERE')
    assert not review.leaks_answer('要在分组前筛选原始数据行，应使用哪个子句？', 'WHERE')
    assert not review.leaks_answer('请说明 SOMEWHERE 字段的用途。', 'WHERE')


def candidate():
    return {
        'question': '要筛选分组前的数据行，应使用哪个子句？',
        'options': {'A': 'WHERE', 'B': 'HAVING', 'C': 'ORDER BY', 'D': 'GROUP BY'},
        'answer': 'A',
        'knowledgePoint': 'SQL 筛选',
        'difficulty': '简单',
        'explanation': 'WHERE 按条件筛选原始数据行。',
    }


def test_known_duplicate_never_requests_model_review(monkeypatch):
    question = candidate()
    request_reviews = Mock()
    monkeypatch.setattr(review, 'request_reviews', request_reviews)
    passed, rejected = review.validate_questions(
        [question], question['explanation'],
        [{'question': '哪些 SQL 子句会消除记录？', 'evidenceQuote': question['explanation']}],
    )
    assert not passed
    assert '重复考查' in rejected[0]['reasons'][0]
    request_reviews.assert_not_called()


def test_review_prompt_only_sends_one_copy_of_evidence_and_keeps_other_context(monkeypatch):
    question = candidate()
    evidence = question['explanation']
    other = 'HAVING 按条件筛选分组后的聚合结果。'
    response = Mock()
    response.json.return_value = {'message': {'content': '{"reviews":[{"id":1,"answer":"A","issue":"ok"}]}'}}
    post = Mock(return_value=response)
    monkeypatch.setattr(review.requests, 'post', post)
    monkeypatch.setattr(review.validator, 'checked_model_response', Mock())
    review.request_reviews({1: question}, [evidence, other])
    prompt = post.call_args.kwargs['json']['messages'][0]['content']
    assert prompt.count(evidence) == 1
    assert other in prompt
    assert '"answer":"' not in prompt


def test_unproven_candidate_still_needs_independent_matching_answer(monkeypatch):
    question = candidate()
    reviewer = Mock(return_value=[{'id': 1, 'answer': 'B', 'issue': 'ok'}])
    monkeypatch.setattr(review, 'request_reviews', reviewer)
    passed, rejected = review.validate_questions([question], question['explanation'], [])
    reviewer.assert_called_once()
    assert not passed
    assert '独立解答与生成答案不一致' in rejected[0]['reasons']


def test_history_rephrasing_is_filtered_before_review(monkeypatch):
    question = candidate()
    old = {'question': '需要筛选分组前的数据行时，应当使用什么子句？', 'point': 'SQL 筛选',
           'answer': 'WHERE', 'evidence': 'WHERE 从原始记录筛选数据。'}
    reviewer = Mock()
    monkeypatch.setattr(review, 'request_reviews', reviewer)
    passed, rejected = review.validate_questions(
        [question], question['explanation'], [], PracticePlan((old,)),
    )
    assert not passed
    assert rejected[0]['reasons'] == [REPEATED]
    reviewer.assert_not_called()


def test_new_fact_can_reuse_a_weak_point_without_reusing_an_answer(monkeypatch):
    question = candidate()
    old = {'question': '某位同学误将 HAVING 用于检查空值，应如何改正？',
           'point': 'SQL 筛选', 'angle': '错误辨析', 'outcome': '答错',
           'evidence': 'SQL 可以在 WHERE 中使用 IS NULL 筛选空值。', 'answer': 'IS NULL'}
    plan = PracticePlan((old,), ('SQL 筛选',))
    assert '概念理解' in plan.instructions() and '答错' in plan.instructions()
    assert question_angle(old['question']) == '错误辨析'
    assert not plan.duplicate(question, question['explanation'])
    reviewer = Mock(return_value=[{'id': 1, 'answer': 'A', 'issue': 'ok'}])
    monkeypatch.setattr(review, 'request_reviews', reviewer)
    passed, rejected = review.validate_questions([question], question['explanation'], [], plan)
    assert len(passed) == 1
    assert not rejected
    reviewer.assert_called_once()


def test_unique_literal_citation_can_be_repaired_but_still_needs_review(monkeypatch):
    question = candidate()
    question.update(question='要找出备注缺失的记录，应当使用哪一个谓词？')
    question['options']['A'] = 'IS NULL'
    source = question['explanation'] + '\n使用IS NULL筛选空值。'
    reviewer = Mock(return_value=[{'id': 1, 'answer': 'B', 'issue': 'ok'}])
    monkeypatch.setattr(review, 'request_reviews', reviewer)
    passed, rejected = review.validate_questions([question], source, [])
    assert not passed
    assert '独立解答与生成答案不一致' in rejected[0]['reasons'][0]
    assert reviewer.call_args.args[0][1]['explanation'] == '使用IS NULL筛选空值。'


def test_ambiguous_literal_citations_do_not_borrow_another_sources_evidence():
    question = candidate()
    question['options']['A'] = 'DNS cache'
    assert '无法确定' in review.check_citation(question, [
        question['explanation'], 'A DNS cache reuses past results.', 'The DNS cache can expire.',
    ])[1]


def test_exhausted_source_does_not_call_the_model(monkeypatch):
    import generate_from_file as generator

    evidence = candidate()['explanation']
    post = Mock()
    monkeypatch.setattr(generator.requests, 'post', post)
    assert generator.generate_questions(
        evidence, compact_source=True, used_evidence={evidence},
        allow_rule_generation=False, raw_candidates=True,
    ) == []
    post.assert_not_called()


@pytest.mark.parametrize(('stem', 'evidence', 'option'), [
    ('在 WHERE 子句中，若使用 OR 连接两个条件，哪一行会被保留？',
     'WHERE 中用 AND 连接两个条件时，只有同时满足两个条件才会保留。', '仅同时满足'),
    ('DNS 客户端通常用 UDP 发起查询。收到截断响应后应改用 TCP 重试。',
     'DNS 客户端通常用 UDP 发起查询。', 'UDP'),
    ('在 WHERE 子句中，若需筛选出备注字段为‘有效’的记录，应使用哪个条件？',
     '在 WHERE 中筛选有值的备注字段时，要使用 IS NOT NULL。', 'IS NOT NULL'),
])
def test_source_conflicts_do_not_reach_the_model_reviewer(stem, evidence, option, monkeypatch):
    question = candidate()
    question.update(question=stem, explanation=evidence)
    question['options']['A'] = option
    reviewer = Mock()
    monkeypatch.setattr(review, 'request_reviews', reviewer)
    passed, rejected = review.validate_questions([question], evidence, [])
    assert not passed and rejected
    reviewer.assert_not_called()


def test_citation_duplicates_ignore_whitespace_case_and_terminal_punctuation(monkeypatch):
    question = candidate()
    reviewer = Mock()
    monkeypatch.setattr(review, 'request_reviews', reviewer)
    passed, rejected = review.validate_questions([question], question['explanation'], [
        {'question': '不相似的题干', 'evidenceQuote': 'where 按条件筛选原始 数据行'},
    ])
    assert not passed and '重复考查' in rejected[0]['reasons'][0]
    reviewer.assert_not_called()


def test_requested_difficulty_is_normalized_and_conflicts_are_rejected():
    fields = {'fileIds': ['test'], 'libraryName': 'SQL', 'subject': '数据库', 'questionCount': 2}
    assert JobRequest(**fields, requirements='生成中等难度的2道单选题').difficulty == 2
    assert JobRequest(**fields, requirements='出2道选择题，难度：进阶').difficulty == 3
    with pytest.raises(ValidationError, match='只能指定一个难度'):
        JobRequest(**fields, requirements='生成简单题和困难题')
    with pytest.raises(ValidationError, match='与指定难度不一致'):
        JobRequest(**fields, requirements='难度为中等', difficulty=3)
