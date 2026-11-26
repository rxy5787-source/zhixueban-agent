"""Build a bounded model view while the journal retains exact tool results."""
import json


def _size(messages):
    return sum(len(message['content'].encode('utf-8')) for message in messages)


def project_messages(messages, limit=28_000):
    """Summarize older completed tool exchanges as structured, recoverable references."""
    if _size(messages) <= limit:
        return messages

    history = messages[2:]
    # Preserve the newest completed tool exchange even if it was followed by a format retry.
    pairs = [index for index in range(len(history) - 1) if history[index]['role'] == 'assistant'
             and history[index + 1]['role'] == 'user']
    discardable = pairs[:-1]
    held = []
    removed = set()
    for index in discardable:
        call = json.loads(history[index]['content'])
        reply = json.loads(history[index + 1]['content'])['toolResult']
        # Review/generation results and guidance are needed for final validation and
        # downstream tool calls. Drop earlier material previews and repeated status reads first.
        if reply['status'] == 'ok' and call['tool'] not in ('parse_material', 'extract_points', 'read_progress'):
            continue
        reference = {'tool': call['tool'], 'status': reply['status'], 'code': reply.get('code')}
        args = call['arguments']
        for key in ('fileId', 'topic'):
            if isinstance(args.get(key), str) and len(args[key]) <= 120:
                reference[key] = args[key]
        held.append(reference)
        removed.update((index, index + 1))
        summary = {'role': 'user', 'content': json.dumps({
            'earlierTools': held,
            'note': '旧版预览已折叠。使用原工具参数重新获取原文或学情；以原工具结果为证据。',
        }, ensure_ascii=False, separators=(',', ':'))}
        visible = messages[:2] + [summary] + [row for pos, row in enumerate(history) if pos not in removed]
        if _size(visible) <= limit:
            return visible
    return None
