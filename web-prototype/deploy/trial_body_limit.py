"""Bound request bodies before FastAPI parses multipart files, including chunked uploads."""

import asyncio
from tempfile import SpooledTemporaryFile

from starlette.responses import JSONResponse


class RequestBodyLimit:
    def __init__(self, app, limit):
        self.app = app
        self.limit = limit
        self.slots = asyncio.Semaphore(4)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] in {'GET', 'HEAD', 'OPTIONS'}:
            return await self.app(scope, receive, send)
        limit = self.limit if scope['path'] == '/api/generation-tasks' else 128 * 1024
        if scope['path'].startswith('/api/resumable-uploads/') and '/files/' in scope['path']:
            limit = 256 * 1024
        if scope['path'] in {'/trial-access', '/api/account/login', '/api/account/register'}:
            limit = 4096
        length = dict(scope['headers']).get(b'content-length')
        if length is not None and (not length.isdigit() or len(length) > 10 or int(length) > limit):
            return await self.reject(scope, receive, send, 413, '提交内容过大，单次上传总量上限为 25 MiB。')
        if self.slots.locked():
            return await self.reject(scope, receive, send, 429, '当前上传较多，请稍后重试。')
        async with self.slots:
            with SpooledTemporaryFile(max_size=1024 * 1024) as body:
                size = 0
                deadline = asyncio.get_running_loop().time() + (20 * 60 if scope['path'] == '/api/generation-tasks' else 120)
                while True:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        return await self.reject(scope, receive, send, 408, '上传等待超时，请检查网络后重试。')
                    try:
                        message = await asyncio.wait_for(receive(), timeout=min(60, remaining))
                    except TimeoutError:
                        return await self.reject(scope, receive, send, 408, '上传等待超时，请检查网络后重试。')
                    if message['type'] == 'http.disconnect':
                        return await self.reject(scope, receive, send, 499, '上传连接已断开，请检查网络后重试。')
                    chunk = message.get('body', b'')
                    size += len(chunk)
                    if size > limit:
                        return await self.reject(scope, receive, send, 413, '提交内容过大，单次上传总量上限为 25 MiB。')
                    body.write(chunk)
                    if not message.get('more_body', False):
                        break
                body.seek(0)
                delivered = False

                async def replay():
                    nonlocal delivered
                    if delivered:
                        return await receive()
                    chunk = body.read(65536)
                    more = body.tell() < size
                    delivered = not more
                    return {'type': 'http.request', 'body': chunk, 'more_body': more}

                await self.app(scope, replay, send)

    async def reject(self, scope, receive, send, status, detail):
        response = JSONResponse({'detail': detail}, status_code=status, headers={'Cache-Control': 'no-store'})
        await response(scope, receive, send)
