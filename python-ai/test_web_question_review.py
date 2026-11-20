from unittest.mock import Mock

from backend import web_question_review as review


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
