"""Bounds and validation for the authenticated, loopback-only API."""
import hmac
import re
from fastapi import HTTPException
from starlette.responses import JSONResponse
from .document_parser import MAX_UPLOAD

JSON_BODY_LIMIT = 64 * 1024


def token_matches(value, expected):
    # compare_digest(str, str) rejects non-ASCII input. Invalid credentials must
    # produce a denial, never an exception or a reflected credential.
    return isinstance(value, str) and hmac.compare_digest(value.encode('utf-8'), expected.encode('utf-8'))


class RequestSizeLimit:
    def __init__(self, app): self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        upload = (scope['method'] == 'POST'
                  and re.fullmatch(r'/api/projects/[^/]+/documents', scope['path'])
                  and headers.get(b'content-type', b'').split(b';')[0].strip() == b'application/octet-stream')
        limit = MAX_UPLOAD if upload else JSON_BODY_LIMIT
        try: declared = int(headers.get(b'content-length', b'0'))
        except ValueError: declared = -1
        if declared < 0 or declared > limit:
            return await JSONResponse({'detail': 'Request body exceeds its allowed size'}, status_code=413)(scope, receive, send)
        consumed = 0

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            consumed += len(message.get('body', b''))
            if consumed > limit:
                raise HTTPException(413, 'Request body exceeds its allowed size')
            return message
        await self.app(scope, bounded_receive, send)
