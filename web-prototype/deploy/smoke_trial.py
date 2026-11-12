"""Exercise the packaged Web API against an installed local Ollama model."""

import argparse
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import time
from uuid import uuid4

import requests


def require(response, status=200):
    if response.status_code != status:
        raise AssertionError(f'{response.request.method} {response.url}: {response.status_code} {response.text[:600]}')
    return response


def smoke(args):
    base = f'http://127.0.0.1:{args.port}'
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    env = {**os.environ, 'TRIAL_DATA_DIR': str(output / 'data'), 'TRIAL_FRONTEND_DIR': str(args.frontend.resolve()),
           'TRIAL_PUBLIC_ORIGIN': base, 'TRIAL_SECRET': secrets.token_hex(32),
           'AI_WEB_DATA_DIR': str(output / 'local-adapter'), 'PYTHONDONTWRITEBYTECODE': '1',
           'OLLAMA_URL': 'http://127.0.0.1:11434/api/chat', 'AI_TEXT_MODEL': 'qwen3:1.7b',
           'AI_VISION_MODEL': 'qwen3-vl:2b-instruct'}
    with (output / 'uvicorn.log').open('wb') as log:
        server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.web_trial:from_environment', '--factory',
                                   '--host', '127.0.0.1', '--port', str(args.port), '--no-access-log'],
                                  cwd=args.server, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            exercise(base, output, server, args.material)
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


def exercise(base, output, server, material):
    for _ in range(60):
        assert server.poll() is None, (output / 'uvicorn.log').read_text(encoding='utf-8', errors='replace')
        try:
            require(requests.get(base + '/healthz', timeout=1))
            break
        except requests.ConnectionError:
            time.sleep(0.25)
    else:
        raise AssertionError('Trial server did not start')

    first, second = requests.Session(), requests.Session()
    for browser in (first, second):
        browser.headers['Origin'] = base
        assert '知学伴' in require(browser.get(base + '/', timeout=5)).text
    health = require(first.get(base + '/api/health', timeout=12)).json()
    assert health['generationReady'] and 'qwen3:1.7b' in health['models'], health
    print('Compiled Web entry loaded. Text and vision models:', health['models'], flush=True)

    library_id = 'cloud-smoke'
    fields = {'libraryId': library_id, 'libraryName': 'SQL试用验收', 'questionCount': '1',
              'questionType': 'single_choice', 'requirements': '生成1道SQL基础四选一单选题，考查WHERE过滤数据行的作用。'}
    invalid = first.post(base + '/api/generation-tasks', files={'files': ('empty.txt', b'')}, data=fields, timeout=15)
    assert '文件为空' in require(invalid, 422).json()['detail']
    with material.open('rb') as source:
        submitted = require(first.post(base + '/api/generation-tasks', files={'files': ('sql-study.txt', source)},
                                       data=fields, timeout=20), 202).json()
    ident = submitted['taskId']
    path = base + '/api/generation-tasks/' + ident
    assert submitted['status'] == 'queued'
    require(second.get(path, timeout=5), 404)
    print('Real file uploaded. Second session cannot access the task.', flush=True)

    previous_stage = None
    for _ in range(240):
        task = require(first.get(path, timeout=10)).json()
        if task['stage'] != previous_stage:
            print(task['status'], task['stage'], flush=True)
            previous_stage = task['stage']
        if task['status'] not in ('queued', 'running'):
            break
        time.sleep(1.5)
    else:
        raise AssertionError('Real generation did not finish in six minutes')

    store_files = sorted((output / 'data/spaces').glob('*/*.sqlite*'))
    traces = []
    for file in store_files:
        if file.suffix not in ('.db', '.sqlite', '.sqlite3'):
            continue
        with sqlite3.connect(file) as db:
            traces.extend(row[0] for row in db.execute('SELECT phase FROM model_call WHERE job_id=? ORDER BY id', (ident,)))
    print('Ollama call phases recorded:', traces, flush=True)
    assert task['status'] in ('succeeded', 'partial'), task
    assert traces, store_files
    assert task['acceptedQuestionCount'] > 0 and task['savedQuestionCount'] > 0, task
    question = require(first.get(path + '/questions', timeout=5)).json()['questions'][0]
    assert question['prompt'] and len(question['options']) == 4 and question['explanation'] and question['points'], question
    answers = {'sessionId': str(uuid4()), 'answers': [{'questionId': question['id'], 'answer': question['answer']}]}
    report = require(first.post(path + '/practice-sessions', json=answers, timeout=5)).json()
    assert report['correct'] == 1 and report['points'], report
    assert require(first.get(base + '/api/practice-history', timeout=5)).json()['sessions']
    assert not require(second.get(base + '/api/practice-history', timeout=5)).json()['sessions']
    assert library_id in require(first.get(base + '/api/libraries', timeout=5)).text
    assert library_id not in require(second.get(base + '/api/libraries', timeout=5)).text
    print('Real question, automatic archiving, practice, mastery report and visitor isolation passed.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--server', type=Path, required=True)
    parser.add_argument('--frontend', type=Path, required=True)
    parser.add_argument('--material', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8093)
    smoke(parser.parse_args())
