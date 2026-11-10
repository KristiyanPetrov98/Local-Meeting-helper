"""Private child-process launcher. Token is supplied over stdin, never CLI or logs."""
import asyncio
import json
import socket
import sys
import threading
from pathlib import Path
import uvicorn
from .app import create_app


def abort_owned_children(app):
    # Parent death must stop capture even while HTTP model requests are draining.
    meeting=app.state.meeting
    documents=app.state.documents
    assistance=getattr(app.state,'assistance',None)
    if assistance and assistance.task: assistance.task.cancel()
    screen=getattr(app.state,'screen',None)
    if screen:
        for task in (screen.capture_task,screen.worker,screen.job):
            if task:task.cancel()
        process=screen.native.process
        if process is not None and process.returncode is None:
            try:process.kill()
            except ProcessLookupError:pass
    setup=getattr(app.state,'setup',None)
    if setup:
        if setup.task:setup.task.cancel()
        if setup.process and setup.process.returncode is None:
            try:setup.process.kill()
            except ProcessLookupError:pass
    meeting.stopping=True
    documents.stopped=True
    if documents.task: documents.task.cancel()
    for process in list(meeting.processes)+[documents.process]:
        if process is not None and process.returncode is None:
            try: process.kill()
            except ProcessLookupError: pass


def main():
    config = json.loads(sys.stdin.readline())
    database = Path(config['database'])
    database.parent.mkdir(parents=True, exist_ok=True)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    app = create_app(database, config['token'], origin, config['web_dir'], excluded_pids=[config['desktop_pid']] if config.get('desktop_pid') else [],desktop_capability=config.get('desktop_capability'))
    server = uvicorn.Server(uvicorn.Config(app, log_level='warning', access_log=False, ws_max_size=1024))
    async def serve():
        loop = asyncio.get_running_loop()
        def fail_closed():
            abort_owned_children(app)
            server.should_exit=True
        def watch_parent():
            # Main keeps this private pipe open. EOF means Electron died: fail closed.
            sys.stdin.read(1)
            try: loop.call_soon_threadsafe(fail_closed)
            except RuntimeError: pass
        threading.Thread(target=watch_parent, daemon=True).start()
        task = asyncio.create_task(server.serve(sockets=[sock]))
        while not server.started and not task.done():
            await asyncio.sleep(.02)
        if server.started:
            print(json.dumps({'type':'ready','origin':origin}), flush=True)
        await task
    asyncio.run(serve())

if __name__ == '__main__':
    main()
