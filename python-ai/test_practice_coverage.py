import pytest

from backend.practice_coverage import Scope, make_scopes, named_topics
from backend.worker import SourceBatch


def batch(ident, text):
    return SourceBatch({'id': ident, 'name': ident + '.txt'}, {}, text, {}, 1)


def test_scope_with_explicit_quota_and_three_sources_does_not_reallocate_missing():
    total, scopes = make_scopes('DNS 2道，SQL 1道，共三道', 5, [])
    assert total == 3
    assert [(scope.label, scope.quota) for scope in scopes] == [('DNS', 2), ('SQL', 1)]
    assert not scopes[1].material(batch('DNS', 'DNS 记录的 TTL 决定资料可缓存的时间。'))
    assert scopes[1].material(batch('mixed', 'DNS 记录有有效期。\nSQL 在分组前使用 WHERE 筛选。')) == 'SQL 在分组前使用 WHERE 筛选。'


def test_each_and_natural_coverage_allocate_per_topic():
    assert named_topics('请用英文出1道单选题，考查WHERE，面向初学者。') == {'WHERE': None}
    assert named_topics('请根据资料生成一道四选一单选题：按部门分组前先排除某些原始记录，应选哪个子句？') == {}
    assert named_topics('请根据资料生成一道四选一单选题：考查 WHERE 的作用。') == {'WHERE': None}
    assert named_topics('DNS 和 SQL 各出一道题') == {'DNS': 1, 'SQL': 1}
    assert named_topics('SQL 的 WHERE 和 HAVING 各出一道题') == {'WHERE': 1, 'HAVING': 1}
    assert named_topics('生成两道单选题。请覆盖 DNS 查询和 SQL 筛选，按原文出题。') == {'DNS': None, 'SQL': None}
    assert named_topics('生成中等难度的2道四选一单选题。请覆盖 DNS 查询和 SQL 筛选，按资料原文出题。') == {
        'DNS': None, 'SQL': None,
    }
    assert named_topics('缓存失效和分组聚合各一道') == {'缓存失效': 1, '分组聚合': 1}


def test_weak_scope_reuses_previous_bkt_label_and_matches_whole_token():
    _, scopes = make_scopes('根据资料优先生成本知识库薄弱知识点的四选一单选题', 1, [], ('DNS',))
    assert scopes == [Scope('DNS', 1, term='DNS')]
    assert not scopes[0].match('ADNS-test')
    assert scopes[0].match('使用DNS发起解析请求。')


def test_defaults_preserve_source_fairness_and_conflicting_total_is_rejected():
    sources = [batch('DNS', 'DNS 的 TTL 决定缓存时间。'), batch('SQL', 'SQL 中的 WHERE 筛选原始行。')]
    _, scopes = make_scopes('生成两道单选题', 2, sources)
    assert [(scope.file_id, scope.quota) for scope in scopes] == [('DNS', 1), ('SQL', 1)]
    with pytest.raises(ValueError, match='总题量'):
        make_scopes('DNS 2道，SQL 1道，共两道', 2, sources)
    with pytest.raises(ValueError, match='至少'):
        make_scopes('覆盖 DNS 和 SQL', 1, sources)


def test_named_topic_does_not_discard_the_learners_original_requirements(tmp_path, monkeypatch):
    import generate_from_file
    from backend.job_store import Store
    from backend.schemas import JobRequest
    from backend.worker import Runner

    store = Store(tmp_path)
    material = tmp_path / 'uploads' / 'source.txt'
    material.write_text('WHERE 按条件筛选原始数据行。\nGROUP BY 按指定字段值对数据行分组。\n'
                        'HAVING 按条件筛选分组后的聚合结果。\nORDER BY 对查询结果进行排序。', encoding='utf-8')
    file_id = store.add_file('learner', 'source.txt', 'test', material.stat().st_size, material)
    requirement = '请用英文出1道单选题，考查WHERE，面向初学者。'
    request = JobRequest(fileIds=[file_id], libraryName='SQL', subject='数据库',
                         questionCount=1, requirements=requirement, requireModelGeneration=True)
    ident = store.create('learner', request.model_dump())
    observed = []
    def generate(*args, **kwargs):
        observed.append(kwargs['requirements'])
        return []
    monkeypatch.setattr(generate_from_file, 'generate_questions', generate)
    Runner(store).run(store.claim())
    assert observed, store.get(ident)
    assert all(requirement in prompt for prompt in observed)
    assert store.get(ident)['state'] == 'failed'  # No candidates must not become a fake success.
