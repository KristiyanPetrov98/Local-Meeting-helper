"""Selected-window-only private process transport. No media files or shell commands."""
import asyncio
import json
import os
import sys
from pathlib import Path
from .store import DomainError
ROOT=Path(__file__).resolve().parents[3]

class NativeScreen:
    def __init__(self,excluded_pids=()):
        self.helper=Path(os.environ.get('PM_SCREEN_HELPER',str(ROOT/'services/screen-windows/bin/Release/net10.0-windows10.0.19041.0/win-x64/publish/PmCopilot.Screen.exe')))
        self.excluded_pids=list(excluded_pids);self.process=None

    def diagnostics(self):
        reason='Windows 11 is required for selected-window capture' if sys.platform!='win32' else 'Build the Windows screen helper first' if not self.helper.is_file() else None
        return dict(available=reason is None,reason=reason)

    def config(self,source_id=None):return dict(excluded_pids=[os.getpid(),*self.excluded_pids],source_id=source_id)

    async def windows(self):
        if not self.diagnostics()['available']:return []
        process=await asyncio.create_subprocess_exec(str(self.helper),'--list',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
        try:
            out,_=await asyncio.wait_for(process.communicate(json.dumps(self.config()).encode()+b'\n'),5)
            if process.returncode:raise ValueError()
            return json.loads(out)['windows']
        except (TimeoutError,ValueError,KeyError) as exc:raise DomainError('Selected-window enumeration failed',503) from exc
        finally:
            if process.returncode is None:process.kill();await process.wait()

    async def frames(self,source_id):
        if not self.diagnostics()['available']:raise DomainError(self.diagnostics()['reason'],503)
        self.process=await asyncio.create_subprocess_exec(str(self.helper),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,limit=6*1024*1024,creationflags=0x00004000 if sys.platform=='win32' else 0)
        process=self.process
        try:
            process.stdin.write((json.dumps(self.config(source_id))+'\n').encode());await process.stdin.drain()
            started=False
            while True:
                event=json.loads(await asyncio.wait_for(process.stdout.readline(),10))
                if event.get('type')=='started':started=True
                elif event.get('type')=='frame' and started and event.get('source_id')==source_id:yield event
                else:raise DomainError('Selected window closed, minimized, changed identity, or capture failed',503)
        finally:
            if process.returncode is None:process.kill();await process.wait()
            if self.process is process:self.process=None

    async def close(self):
        if self.process and self.process.returncode is None:self.process.kill();await self.process.wait()
