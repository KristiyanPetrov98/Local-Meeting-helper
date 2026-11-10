"""Bounded parser worker on private pipes. No media/document temp files."""
import base64
import json
import os
import sys
from .document_parser import parse_document, ParseError


def main():
    if os.name=='posix':
        import resource
        resource.setrlimit(resource.RLIMIT_CPU,(30,35))
        resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
    message=json.loads(sys.stdin.readline())
    try:
        result=parse_document(message['name'],base64.b64decode(message['content'],validate=True))
        print(json.dumps({'type':'parsed','result':result}),flush=True)
    except ParseError as error:
        print(json.dumps({'type':'error','detail':str(error)}),flush=True)
        return 2
    except Exception:
        print(json.dumps({'type':'error','detail':'Document parser failed within its limits'}),flush=True)
        return 2
    return 0

if __name__=='__main__':raise SystemExit(main())
