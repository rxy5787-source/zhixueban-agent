from unittest.mock import Mock

from backend import web_question_review as review
from backend.practice_variety import PracticePlan, REPEATED, question_angle


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
