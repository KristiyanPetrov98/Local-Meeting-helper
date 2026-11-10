"""Explicit, bounded target-laptop telemetry. Never generates or saves meeting content."""
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import sys
import time
from .build_identity import source_identity
from .store import DomainError

DURATION_SECONDS = 90 * 60
MAX_SAMPLES = 3000  # 100 minutes at two seconds. An overdue run fails closed.


def summary(values):
    values = sorted(v for v in values if isinstance(v, (int, float)) and math.isfinite(v))
    return {'count': len(values), 'median': statistics.median(values) if values else None,
            'p95': values[max(0, math.ceil(.95 * len(values)) - 1)] if values else None,
            'max': max(values) if values else None}


def resident_mib():
    """This backend only; native/model worker memory is not included."""
    try:
        if sys.platform == 'win32':
            import ctypes
            from ctypes import wintypes
            class Counters(ctypes.Structure):
                _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in
                    ('PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage',
                     'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
            counters = Counters(); counters.cb = ctypes.sizeof(counters)
            kernel = ctypes.WinDLL('kernel32', use_last_error=True); kernel.GetCurrentProcess.restype = wintypes.HANDLE
            psapi = ctypes.WinDLL('psapi', use_last_error=True)
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
            if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb): return None
            return counters.WorkingSetSize / 1024 ** 2
        return int(Path('/proc/self/statm').read_text().split()[1]) * __import__('os').sysconf('SC_PAGE_SIZE') / 1024 ** 2
    except (OSError, ValueError, IndexError): return None


class Qualification:
    def __init__(self, store, meeting, resources, assistance):
        self.store, self.meeting, self.resources, self.assistance = store, meeting, resources, assistance
        self.report = None; self.task = None; self.samples = []

    def status(self):
        return {'phase': self.report['phase'] if self.report else 'idle',
                'elapsed_seconds': round(time.monotonic() - self.started) if self.report and self.task else round(self.report.get('duration_seconds',0)) if self.report else 0,
                'sample_count': len(self.samples), 'required_seconds': DURATION_SECONDS,
                'release_qualified': False}

    def configuration(self):
        return {'audio': self.store.value('audio_options'), 'resources': self.resources.settings.model_dump()}

    async def start(self):
        if self.task: raise DomainError('A qualification recording is already active')
        live = self.store.live(); meeting = self.meeting.status()
        if not live or live['state'] != 'active' or meeting['state'] != 'capturing' or meeting['session_id'] != live['id']:
            raise DomainError('Start a consented session with live transcription first')
        resources = await self.resources.refresh()
        if sys.platform != 'win32' or len(resources['gpus']) != 1 or not all(word in resources['gpus'][0]['name'].lower() for word in ('4080', 'laptop')):
            raise DomainError('Target qualification requires Windows and the RTX 4080 Laptop GPU', 422)
        if self.resources.settings.force_cpu: raise DomainError('Use the GPU generation profile for target qualification', 422)
        digest = await self.assistance.generator.identity()
        self.samples = []; self.started = time.monotonic(); self.last_sample = self.started
        self.session = live['id']; self.project = live['project_id']; self.baseline = dict(meeting['counts'])
        self.first_segment = self.store.db.execute('SELECT COALESCE(MAX(id),0) FROM transcript_segments').fetchone()[0]
        self.last_active_seconds = 0
        self.first_request = self.store.db.execute('SELECT COALESCE(MAX(rowid),0) FROM assistance_requests').fetchone()[0]
        self.report = {'schema': 1, 'kind': 'target_laptop_telemetry', 'phase': 'recording',
                       'started_at': datetime.now(timezone.utc).isoformat(), 'source_digest': source_identity(),
                       'model': self.assistance.generator.model, 'model_digest': digest,
                       'configuration': self.configuration(), 'hardware': resources['gpus'][0],
                       'anomalies': [], 'release_qualified': False,
                       'scope': 'Observed application workload; no quality verdict, no meeting content, backend RSS excludes worker processes.'}
        self._sample(); self.task = asyncio.create_task(self._record())
        return self.status()

    def _sample(self):
        now = time.monotonic(); elapsed = now - self.started
        meeting = self.meeting.status(); resource = self.resources.status()
        def anomaly(code):
            if code not in self.report['anomalies']: self.report['anomalies'].append(code)
        live = self.store.live()
        if live and live['id'] == self.session and live['state'] == 'active' and meeting['state'] == 'capturing' and meeting['session_id'] == self.session:
            self.last_active_seconds = elapsed
        if meeting['session_id'] != self.session: anomaly('capture_session_changed')
        if not live or live['id'] != self.session or live['state'] != 'active' or meeting['state'] != 'capturing':
            if elapsed < DURATION_SECONDS: anomaly('capture_not_continuously_active')
        if self.configuration() != self.report['configuration']: anomaly('configuration_changed')
        if now - self.last_sample > 6: anomaly('telemetry_gap_over_6s')
        self.last_sample = now
        gpus = resource['gpus']; gpu = gpus[0] if len(gpus) == 1 else None
        if (not gpu or gpu['uuid'] != self.report['hardware']['uuid']
                or resource['samples_age_ms'] is None or resource['samples_age_ms'] > 6000): anomaly('gpu_telemetry_missing_or_changed')
        sample = {'seconds': round(elapsed, 2), 'asr_lag_ms': meeting['counts'].get('last_chunk_lag_ms'),
                  'asr_segments': meeting['counts'].get('segments', 0), 'queue_depth': meeting['queue_depth'],
                  'gpu_used_mib': gpu['total_mib'] - gpu['free_mib'] if gpu else None,
                  'backend_rss_mib': resident_mib(), 'resident_model_mib': max([m['size_vram_mib'] for m in resource['resident'] if m['model'] == self.report['model']] or [0])}
        if len(self.samples) >= MAX_SAMPLES: anomaly('sample_capacity_exceeded')
        else: self.samples.append(sample)
        if elapsed >= DURATION_SECONDS: self.report['phase'] = 'awaiting_session_stop'

    async def _record(self):
        try:
            while len(self.samples) < MAX_SAMPLES:
                await asyncio.sleep(2); self._sample()
            self.report['anomalies'].append('sample_capacity_exceeded')
        except asyncio.CancelledError: raise
        except Exception:
            self.report['anomalies'].append('telemetry_failed')

    async def finish(self):
        if not self.report or not self.task: raise DomainError('No active qualification recording')
        live = self.store.live()
        if live and live['id'] == self.session: raise DomainError('Stop the session first so final capture-drop counters are included')
        self._sample(); self.task.cancel(); await asyncio.gather(self.task, return_exceptions=True); self.task = None
        final_meeting = self.meeting.status(); counts = final_meeting['counts']
        delta = {key: counts.get(key, 0) - self.baseline.get(key, 0) for key in
                 ('packets', 'segments', 'local_audible_packets', 'remote_audible_packets', 'gaps', 'dropped_chunks',
                  'asr_errors', 'diarization_errors', 'reconnects', 'native_dropped_packets', 'asr_cpu_fallback')}
        requests = self.store.db.execute('''SELECT status,elapsed_ms,id FROM assistance_requests
            WHERE session_id=? AND rowid>?''', (self.session, self.first_request)).fetchall()
        statuses = dict(Counter(r['status'] for r in requests))
        latency = summary([r['elapsed_ms'] for r in requests if r['status'] == 'completed'])
        languages = dict(self.store.db.execute('SELECT language,COUNT(*) FROM transcript_segments WHERE session_id=? AND id>? GROUP BY language', (self.session,self.first_segment)))
        # Re-verify every saved citation; deleting a document cannot hide a bad reference.
        invalid = 0; citations = 0
        for row in self.store.db.execute('''SELECT body,model_digest FROM generated_responses WHERE request_id IN
            (SELECT id FROM assistance_requests WHERE session_id=? AND rowid>?)''', (self.session, self.first_request)):
            if row['model_digest'] != self.report['model_digest']: self.report['anomalies'].append('model_changed')
            body = json.loads(row['body'])
            for claim in [body['briefing'], *body['supporting_points']]:
                for cid in claim['citation_ids']:
                    citations += 1
                    try: self.store.citation(self.project, cid)
                    except DomainError: invalid += 1
        lag = summary([s['asr_lag_ms'] for s in self.samples]); duration = time.monotonic() - self.started
        if source_identity() != self.report['source_digest']: self.report['anomalies'].append('source_changed')
        no_question_responses = self.store.db.execute('''SELECT COUNT(*) FROM generated_responses g JOIN assistance_requests a ON a.id=g.request_id
            WHERE a.session_id=? AND a.rowid>? AND a.status='no_question' ''',(self.session,self.first_request)).fetchone()[0]
        checks = {'duration_90_minutes': self.last_active_seconds >= DURATION_SECONDS,
                  'continuous_capture_and_telemetry': not self.report['anomalies'],
                  'final_capture_report_received': 'native_dropped_packets' in counts and not final_meeting.get('error'),
                  'no_capture_or_asr_errors': all(delta[k] == 0 for k in ('gaps', 'dropped_chunks', 'asr_errors', 'reconnects', 'native_dropped_packets', 'asr_cpu_fallback')),
                  'both_audio_sources_audible': all(delta[k] > 0 for k in ('local_audible_packets', 'remote_audible_packets')),
                  'bilingual_transcript_observed': all(languages.get(lang, 0) > 0 for lang in ('en', 'bg')),
                  'asr_median_below_5_seconds': lag['count'] > 0 and lag['median'] < 5000,
                  'manual_answers_measured': latency['count'] >= 10 and latency['median'] < 45000 and latency['max'] <= 60000,
                  'no_question_exercised': statuses.get('no_question', 0) >= 5 and no_question_responses == 0,
                  'grounded_citations_verified': citations > 0 and invalid == 0,
                  'gpu_model_residency_observed': any(s['resident_model_mib'] > 0 for s in self.samples),
                  'all_manual_requests_settled': not any(k not in ('completed', 'no_question') for k in statuses)}
        self.report.update(phase='completed', completed_at=datetime.now(timezone.utc).isoformat(), duration_seconds=duration,
                           counts_delta=delta, request_statuses=statuses, languages=languages, asr_lag_ms=lag,
                           manual_latency_ms=latency, gpu_used_mib=summary([s['gpu_used_mib'] for s in self.samples]),
                           backend_rss_mib=summary([s['backend_rss_mib'] for s in self.samples]), samples=self.samples,
                           citation_count=citations, invalid_citations=invalid, checks=checks,
                           telemetry_passed=all(checks.values()), human_accuracy_and_privacy_review='required')
        return self.report

    async def close(self):
        if self.task:
            self.task.cancel(); await asyncio.gather(self.task, return_exceptions=True); self.task = None
            self.report['phase'] = 'cancelled'


def register_qualification_routes(app, qualification, lifecycle_lock):
    @app.get('/api/qualification', response_model=dict)
    async def status(): return qualification.status()

    @app.post('/api/qualification/start', response_model=dict)
    async def start():
        async with lifecycle_lock: return await qualification.start()

    @app.post('/api/qualification/finish', response_model=dict)
    async def finish():
        async with lifecycle_lock: return await qualification.finish()

    @app.post('/api/qualification/cancel', response_model=dict)
    async def cancel():
        async with lifecycle_lock: await qualification.close(); return qualification.status()

    @app.get('/api/qualification/report', response_model=dict)
    async def report():
        if not qualification.report or qualification.report['phase'] != 'completed': raise DomainError('Finish a recording before exporting its report')
        return qualification.report
