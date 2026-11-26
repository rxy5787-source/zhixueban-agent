"""Allowlisted operational events. Private artifacts stay in the owner's Store."""
import json
import logging
import math
import re

LOGGER = logging.getLogger('zhixue.operations')
LOGGER.setLevel(logging.INFO)
if not any(getattr(handler, '_zhixue_operations', False) for handler in LOGGER.handlers):
    handler = logging.StreamHandler()
    handler._zhixue_operations = True
    handler.setFormatter(logging.Formatter('%(message)s'))
    LOGGER.addHandler(handler)
EVENTS = frozenset({'claimed', 'checkpoint', 'model_call', 'archive', 'queue_error',
                    'worker_error', 'request_error', 'constraint_error'})
STATES = frozenset({'queued', 'running', 'succeeded', 'partial', 'failed', 'cancelled', 'interrupted'})
PHASES = frozenset({'preparation', 'parsing', 'ocr', 'knowledge', 'generation',
                    'quality', 'checkpoint', 'other', 'archive'})
ERRORS = frozenset({'internal_error', 'database_error', 'model_timeout',
                   'model_unavailable', 'invalid_input', 'worker_error'})


def event(name, *, job_id=None, request_id=None, state=None, phase=None, elapsed_ms=None, error_code=None):
    """Never accept arbitrary fields, exception objects or source labels."""
    if name not in EVENTS:
        raise ValueError('Unknown operational event')
    row = {'event': name}
    if isinstance(job_id, str) and re.fullmatch(r'[0-9a-f]{32}', job_id):
        row['jobId'] = job_id
    if isinstance(request_id, str) and re.fullmatch(r'[0-9a-f]{32}', request_id):
        row['requestId'] = request_id
    if state in STATES:
        row['state'] = state
    if phase in PHASES:
        row['phase'] = phase
    if type(elapsed_ms) in (int, float) and math.isfinite(elapsed_ms):
        row['elapsedMs'] = max(0, min(round(elapsed_ms), 86_400_000))
    if error_code in ERRORS:
        row['errorCode'] = error_code
    LOGGER.info(json.dumps(row, separators=(',', ':'), sort_keys=True))


def failure(exc):
    import requests
    if isinstance(exc, requests.Timeout):
        return 'model_timeout', '等待本机模型响应超时，可稍后重试。'
    if isinstance(exc, requests.RequestException):
        return 'model_unavailable', '本机模型暂不可用，可稍后重试。'
    return 'worker_error', '处理失败，可稍后重试。'
