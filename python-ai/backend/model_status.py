"""Report model availability separately from the HTTP service being alive."""
import requests
from . import config


def generation_readiness():
    models = []
    try:
        # Ollama can be responsive while model discovery is still reading local metadata.
        response = requests.get(config.OLLAMA_URL.rsplit('/api/', 1)[0] + '/api/tags', timeout=(3, 20))
        response.raise_for_status()
        models = [item['name'] for item in response.json()['models']]
    except (requests.RequestException, ValueError, KeyError, TypeError):
        issue = '电脑上的模型服务暂不可用，请启动 Ollama 后重试。已上传的资料会保留。'
    else:
        required = config.TEXT_MODEL if ':' in config.TEXT_MODEL else config.TEXT_MODEL + ':latest'
        issue = '' if required in models else f'出题模型 {config.TEXT_MODEL} 不可用。请检查 Ollama 的模型目录和已安装模型；资料已保留，恢复模型后可重试。'
    return {'models': models, 'requiredTextModel': config.TEXT_MODEL,
            'generationReady': not issue, 'generationIssue': issue}


def checked_model_response(response, model):
    # Preserve the actual Ollama error instead of hiding it behind HTTP 404.
    if getattr(response, 'status_code', 200) == 404:
        try:
            detail = response.json().get('error', '')
        except (ValueError, AttributeError):
            detail = ''
        if 'model' in detail.lower() and 'not found' in detail.lower():
            raise RuntimeError(f'出题模型 {model} 不可用，请检查 Ollama 模型目录或安装对应模型后重试')
    response.raise_for_status()
