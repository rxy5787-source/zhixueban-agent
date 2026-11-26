import time
import os
import json
from dataclasses import replace

import pytest

from backend.job_store import Store
from backend import web_practice
from backend.study_tools import ReviewArgs, TopicArgs, GenerateArgs
from backend import study_tools
from backend.tool_registry import Contract, ToolContext, ToolRegistry, ToolSpec
from backend.agent_loop import OllamaModel, run_agent
from backend.agent_journal import AgentJournal, JournalConflict


class Number(Contract):
    value: int


def echo(context, args):
    return {'value': args.value}


def malformed(context, args):
    return {'value': 'PRIVATE_VALUE'}


def failure(context, args):
    raise RuntimeError('PRIVATE_MESSAGE')


def slow(context, args):
    time.sleep(10)
    (context.root / 'unexpected-write').touch()
    return {'value': 1}


@pytest.fixture
def scope(tmp_path):
    store = Store(tmp_path)
    path = tmp_path / 'uploads' / 'source.txt'
    path.write_text('WHERE 按条件筛选原始数据行。', encoding='utf-8')
    ident = store.add_file('web-local', 'source.txt', 'fixture', path.stat().st_size, path)
    job = store.create('web-local', {'fileIds': [ident]})
    with store.db() as db:
        db.executescript("""
            CREATE TABLE web_libraries(id TEXT PRIMARY KEY);
            CREATE TABLE web_deleted_libraries(library_id TEXT PRIMARY KEY);
            CREATE TABLE web_removed_items(library_id TEXT, kind TEXT, item_id TEXT);
            CREATE TABLE web_questions(library_id TEXT, payload TEXT, saved REAL, question_id TEXT);
            CREATE TABLE web_tasks(task_id TEXT, library_id TEXT);
            INSERT INTO web_libraries VALUES ('mine'), ('other');
        """)
        web_practice.init_tables(db)
        db.execute("INSERT INTO web_tasks VALUES (?, 'mine')", (job,))
        db.executemany('INSERT INTO web_point_progress VALUES(?,?,?,?,?,?)', [
            ('mine', 'where', 'WHERE', 0.33, 2, 1),
            ('other', 'hidden', 'PRIVATE_OTHER', 0.01, 3, 0),
        ])
    return ToolContext(tmp_path, 'web-local', 'mine', frozenset({ident}),
                       frozenset({'material:read', 'progress:read', 'practice:generate', 'practice:review'}))


def test_registration_and_strict_validation_before_execution(scope):
    registry = ToolRegistry()
    spec = ToolSpec('echo', 'test', Number, Number, 'granted', 10, echo)
    registry.register(spec)
    with pytest.raises(ValueError):
        registry.register(spec)
    assert registry.catalog(scope) == []
    assert registry.execute(scope, 'echo', {'value': 2}).code == 'tool_not_allowed'
    context = replace(scope, capabilities=frozenset({'granted'}))
    assert registry.catalog(context)[0]['name'] == 'echo'
    for payload in ({'value': '2'}, {'value': True}, {'value': 2, 'owner': 'other'}):
        assert registry.execute(context, 'echo', payload).code == 'invalid_arguments'
    assert registry.execute(context, 'echo', {'value': 2}).data == {'value': 2}


def test_process_returns_safe_faults_and_enforces_timeout(scope):
    registry = ToolRegistry()
    granted = replace(scope, capabilities=frozenset({'test'}))
    for name, handler, timeout in [('bad', malformed, 10), ('error', failure, 10), ('slow', slow, 1)]:
        registry.register(ToolSpec(name, name, Number, Number, 'test', timeout, handler))
    assert registry.execute(granted, 'bad', {'value': 0}).code == 'invalid_output'
    result = registry.execute(granted, 'error', {'value': 0})
    assert result.code == 'tool_failed' and 'PRIVATE' not in result.model_dump_json()
    started = time.monotonic()
    assert registry.execute(granted, 'slow', {'value': 0}).code == 'timeout'
    assert time.monotonic() - started < 6
    assert not (scope.root / 'unexpected-write').exists()
    assert registry.execute(granted, 'slow', {'value': 0}, cancelled=lambda: True).code == 'cancelled'


def test_packagable_study_tools_read_only_scoped_real_data(scope):
    registry = study_tools.study_registry()
    ident = next(iter(scope.file_ids))
    result = registry.execute(scope, 'parse_material', {'fileId': ident})
    assert result.data == {'sections': ['WHERE 按条件筛选原始数据行。'], 'limited': False}
    assert registry.execute(scope, 'parse_material', {'fileId': ident, 'path': 'any.txt'}).code == 'invalid_arguments'
    assert registry.execute(replace(scope, library_id='other'), 'parse_material',
                            {'fileId': ident}).code == 'resource_unavailable'
    assert registry.execute(replace(scope, owner='other'), 'parse_material',
                            {'fileId': ident}).code == 'resource_unavailable'
    assert registry.execute(scope, 'read_progress', {}).data == {
        'points': [{'point': 'WHERE', 'observations': 2, 'correct': 1, 'mastery': .33, 'reviewPriority': True}]}


def test_adapters_call_existing_business_and_keep_scope(scope, monkeypatch):
    from backend import knowledge_extractor, web_question_review
    import generate_from_file

    ident = next(iter(scope.file_ids))
    material = 'WHERE 按条件筛选原始数据行。'
    def derive(text, goal, audit):
        assert text == material and goal == '练习'
        return [{'name': 'WHERE', 'summary': text}]
    monkeypatch.setattr(knowledge_extractor, 'derive_points', derive)
    args = TopicArgs(fileId=ident, goal='练习')
    assert study_tools.extract_points(scope, args)['points'][0]['summary'] == material

    question = {'question': 'WHERE 的用途是什么？', 'answer': 'A', 'knowledgePoint': 'WHERE',
                'difficulty': '简单', 'explanation': material,
                'options': {'A': '按条件筛选原始行', 'B': '排序', 'C': '分组', 'D': '更新'}}
    def generate(text, **options):
        assert text == material and options['allow_rule_generation'] is False
        return [question]
    monkeypatch.setattr(generate_from_file, 'generate_questions', generate)
    args = GenerateArgs(fileId=ident, goal='练习', topic='WHERE', count=1)
    assert study_tools.generate_practice(scope, args) == {'candidates': [question]}

    def review(candidates, text, previous):
        assert candidates == [question] and text == material and previous == []
        return [], [{'reasons': ['test rejection']}]
    monkeypatch.setattr(web_question_review, 'validate_questions', review)
    review_args = ReviewArgs.model_validate({'fileId': ident, 'topic': 'WHERE', 'candidates': [question]})
    assert study_tools.review_practice(scope, review_args) == {'accepted': [], 'rejectedCount': 1}


def test_agent_feedback_and_turn_limit(scope):
    class Model:
        def decide(self, messages, timeout):
            assert timeout > 0
            if len(messages) == 2:
                return {'action': 'call_tool', 'tool': 'read_progress', 'arguments': {}, 'message': ''}
            data = json.loads(messages[-1]['content'])['toolResult']['data']
            assert data['points'][0]['observations'] == 2
            return {'action': 'finish', 'tool': '', 'arguments': {}, 'message': '基于两次观察。'}

    registry = study_tools.study_registry()
    result = run_agent('按我的学情提出复习建议', scope, registry, Model())
    assert result.status == 'proposed_finish'
    assert [event['tool'] for event in result.trace] == ['read_progress']
    assert run_agent('学习建议', scope, registry, Model(), max_turns=1).code == 'turn_limit'
    assert run_agent('学习建议', scope, registry, Model(), cancelled=lambda: True).status == 'cancelled'


def test_skill_catalog_only_advertises_summaries_and_loads_on_demand(scope):
    registry = study_tools.study_registry()
    assert registry.execute(scope, 'load_study_skill', {'name': 'adaptive_practice'}).code == 'tool_not_allowed'
    granted = replace(scope, capabilities=frozenset({'skill:read'}))
    catalog = registry.catalog(granted)
    assert [item['name'] for item in catalog] == ['load_study_skill']
    assert '掌握估计来自已有作答' not in catalog[0]['description']
    result = registry.execute(granted, 'load_study_skill', {'name': 'adaptive_practice'})
    assert result.status == 'ok' and '掌握估计来自已有作答' in result.data['instructions']
    assert len(result.data['version']) == 64
    assert registry.execute(granted, 'load_study_skill', {'name': '../uploads'}).code == 'invalid_arguments'
    assert registry.execute(granted, 'read_progress', {}).code == 'tool_not_allowed'


def test_agent_does_not_dispatch_unknown_tools_or_retry_bad_model_output_forever(scope):
    class Unknown:
        def decide(self, messages, timeout):
            return {'action': 'call_tool', 'tool': 'other_tool', 'arguments': {}, 'message': ''}
    class Invalid:
        def decide(self, messages, timeout):
            return {'action': 'finish', 'tool': 'unexpected'}
    registry = study_tools.study_registry()
    result = run_agent('复习', scope, registry, Unknown(), max_turns=2)
    assert result.code == 'turn_limit' and all(
        event['code'] == 'tool_not_allowed' and event['tool'] is None for event in result.trace)
    result = run_agent('复习', scope, registry, Invalid())
    assert result.code == 'invalid_decision' and len(result.trace) == 2


def test_agent_restart_reuses_tool_result_and_returns_same_terminal_result(scope):
    store = Store(scope.root)
    ident = store.claim()['id']
    scope = replace(scope, job_id=ident)
    registry = study_tools.study_registry()
    journal = AgentJournal(store)

    class InterruptedModel:
        def decide(self, messages, timeout):
            if len(messages) > 2:
                raise KeyboardInterrupt
            return {'action': 'call_tool', 'tool': 'read_progress', 'arguments': {}, 'message': ''}

    ledger = {'journal': journal, 'model_key': 'test:model-v1'}
    with pytest.raises(KeyboardInterrupt):
        run_agent('复习', scope, registry, InterruptedModel(), **ledger)
    store.recover()
    restarted = AgentJournal(Store(scope.root))
    assert not restarted.requeue(ident, 'other-owner')
    assert restarted.requeue(ident, scope.owner)
    assert not restarted.requeue(ident, scope.owner)
    assert store.claim()['id'] == ident
    ledger['journal'] = restarted

    class Finish:
        def decide(self, messages, timeout):
            assert json.loads(messages[-1]['content'])['toolResult']['data']['points'][0]['point'] == 'WHERE'
            return {'action': 'finish', 'tool': '', 'arguments': {}, 'message': '先复习 WHERE。'}

    original = run_agent('复习', scope, registry, Finish(), **ledger)
    assert original.status == 'proposed_finish' and len(original.trace) == 1
    assert run_agent('复习', scope, registry, None, **ledger) == original
    assert run_agent('别的目标', scope, registry, None, **ledger).code == 'incompatible_checkpoint'


def test_agent_journal_fences_off_previous_attempt_and_cancelled_job(scope):
    store = Store(scope.root)
    scope = replace(scope, job_id=store.claim()['id'])
    journal = AgentJournal(store)
    first, _ = journal.begin(scope, '复习', [], 4, 'model-test')
    second, _ = journal.begin(scope, '复习', [], 4, 'model-test')
    assert journal.inactive(first)
    with pytest.raises(JournalConflict, match='inactive_attempt'):
        journal.save(first, {})
    journal.save(second, {'test': 1})
    store.cancel(scope.job_id, scope.owner)
    with pytest.raises(JournalConflict, match='inactive_attempt'):
        journal.save(second, {})
    assert not journal.requeue(scope.job_id, scope.owner)


@pytest.mark.skipif(os.environ.get('ZHIXUE_TEST_LIVE_AGENT') != '1', reason='Requires opt-in local Ollama')
@pytest.mark.parametrize(('goal', 'expected'), [
    ('查看我这个知识库近期真实作答的掌握估计，并告诉我优先复习哪个知识点。无需出题。', 'read_progress'),
    ('请先读我提供的资料，然后用一句话讲清资料里讲到的 WHERE 的作用。无需出题或查看历史成绩。', 'parse_material'),
])
def test_live_qwen_selects_tool_from_learning_goal(scope, goal, expected, monkeypatch):
    if os.environ.get('ZHIXUE_TEST_AGENT_DIAGNOSTIC') == '1':
        import requests

        original_post = requests.Session.post
        def capture(session, *args, **kwargs):
            response = original_post(session, *args, **kwargs)
            payload = response.json()
            # The inputs are generated by this fixture. Never use this on learner data.
            print(json.dumps({'done': payload.get('done'), 'reason': payload.get('done_reason'),
                              'output': payload.get('message', {}).get('content', '')[:1800]},
                             ensure_ascii=False), flush=True)
            return response
        monkeypatch.setattr(requests.Session, 'post', capture)
    registry = study_tools.study_registry()
    result = run_agent(goal, scope, registry, OllamaModel(), max_turns=5, timeout=240)
    print(json.dumps({'status': result.status, 'code': result.code, 'trace': result.trace,
                      'message': result.message}, ensure_ascii=False), flush=True)
    assert result.status == 'proposed_finish'
    assert result.trace[0]['tool'] == expected and result.trace[0]['status'] == 'ok'
    assert 'WHERE' in result.message.upper()
    if expected == 'parse_material':
        assert '筛选' in result.message
