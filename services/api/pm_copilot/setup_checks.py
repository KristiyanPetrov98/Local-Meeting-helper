"""Offline checks with explicit evidence boundaries; no meeting content in reports."""
import asyncio
import base64
import ctypes
import importlib.metadata
import json
import os
import platform
import shutil
import sqlite3
import sys
from pathlib import Path
from .runtime import command,cwd


def hardware(data_dir):
    memory=None
    if sys.platform=='win32':
        class Memory(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(name,ctypes.c_ulonglong) for name in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
        status=Memory();status.length=ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):memory=status.total
    else:
        try:memory=os.sysconf('SC_PAGE_SIZE')*os.sysconf('SC_PHYS_PAGES')
        except (ValueError,OSError,AttributeError):pass
    return dict(os=platform.system(),release=platform.release(),architecture=platform.machine(),logical_cpus=os.cpu_count(),ram_bytes=memory,disk_free_bytes=shutil.disk_usage(data_dir).free,bundled=bool(getattr(sys,'frozen',False)),python=platform.python_version())


def check(id,label,status,detail,metrics=None):return dict(id=id,label=label,status=status,detail=detail,metrics=metrics or {})


def core_checks(data_dir):
    from .document_parser import parse_document
    from .questions import latest_question
    from .store import Store
    rows=[]
    try:
        with __import__('tempfile').TemporaryFile(dir=data_dir) as file:file.write(b'local write test');file.flush()
        rows.append(check('storage','Local data directory','passed','Created, wrote and removed a temporary non-media file.'))
    except OSError:rows.append(check('storage','Local data directory','failed','The configured data directory is not writable.'))
    store=None
    try:
        store=Store(':memory:');a=store.create('Offline Alpha')['projects'][0]['id'];b=store.create('Offline Beta')['projects'][-1]['id']
        raw=b'The offline release is Friday.';doc=store.upload_document(a,'offline.txt',raw)
        store.commit_parsed(a,doc['document_id'],doc['revision_id'],parse_document('offline.txt',raw))
        hits=store.lexical_candidates(a,'release');citation=store.citation(a,hits[0]['id'])
        assert citation['quote']==raw.decode() and not store.lexical_candidates(b,'release')
        rows.append(check('local_rag','SQLite, parser, search and citations','passed','Real isolated FTS retrieval and source verification passed in an in-memory database.'))
    except Exception:rows.append(check('local_rag','SQLite, parser, search and citations','failed','Offline parser/search/citation check failed.'))
    finally:
        if store:store.close()
    try:
        assert latest_question([dict(id=1,start=0,end=1,text='The build is ready.',speaker_id='remote',source='remote')]) is None
        rows.append(check('question_guard','No-question suppression','passed','A statement produced no question; no model was invoked.'))
    except Exception:rows.append(check('question_guard','No-question suppression','failed','The deterministic suppression check failed.'))
    return rows


async def worker_check(owner,worker,config,timeout=120):
    process=await asyncio.create_subprocess_exec(*command(worker),cwd=cwd(),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,limit=1024*1024)
    owner.process=process
    try:
        output,_=await asyncio.wait_for(process.communicate(json.dumps(config).encode()+b'\n'),timeout)
        if process.returncode:raise ValueError('Worker failed')
        return json.loads(output)
    finally:
        if process.returncode is None:process.kill();await process.wait()
        if owner.process is process:owner.process=None


async def asr_silence(owner,meeting):
    process=await asyncio.create_subprocess_exec(*command('media'),cwd=cwd(),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,limit=1024*1024)
    owner.process=process
    try:
        cfg=dict(mode='asr',model_path=str(meeting.model),device='cpu',language='en',cpu_threads=4)
        process.stdin.write(json.dumps(cfg).encode()+b'\n');await process.stdin.drain()
        if json.loads(await asyncio.wait_for(process.stdout.readline(),120)).get('type')!='ready':raise ValueError()
        process.stdin.write(json.dumps({'pcm':base64.b64encode(bytes(16000*4)).decode()}).encode()+b'\n');await process.stdin.drain()
        result=json.loads(await asyncio.wait_for(process.stdout.readline(),60))
        if result.get('type')!='result':raise ValueError()
        return result
    finally:
        if process.returncode is None:process.kill();await process.wait()
        if owner.process is process:owner.process=None


async def diarization_load(owner,meeting):
    process=await asyncio.create_subprocess_exec(*command('media'),cwd=cwd(),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,limit=1024*1024)
    owner.process=process
    try:
        process.stdin.write(json.dumps(dict(mode='diarization',model_path=str(meeting.diar_model),device='cpu')).encode()+b'\n');await process.stdin.drain()
        if json.loads(await asyncio.wait_for(process.stdout.readline(),120)).get('type')!='ready':raise ValueError('Diarization load failed')
    finally:
        if process.returncode is None:process.kill();await process.wait()
        if owner.process is process:owner.process=None
