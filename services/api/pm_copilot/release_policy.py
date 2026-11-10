"""Release decisions require matching, measured evidence. Missing evidence blocks release."""
import hashlib
import re

TARGET_CHECKS = {'duration_90_minutes', 'continuous_capture_and_telemetry', 'final_capture_report_received',
                 'no_capture_or_asr_errors', 'both_audio_sources_audible', 'bilingual_transcript_observed',
                 'asr_median_below_5_seconds', 'manual_answers_measured', 'no_question_exercised',
                 'grounded_citations_verified', 'gpu_model_residency_observed', 'all_manual_requests_settled'}
REVIEW_CHECKS = {'clean_windows_install', 'headphones_and_speakers', 'bilingual_accuracy', 'speaker_renaming',
                 'answer_and_screen_relevance', 'risk_indicators', 'sharing_preview', 'no_raw_media_saved',
                 'offline_inference', 'restart_persistence', 'worker_memory_bounded', 'licenses_reviewed',
                 'project_isolation', 'no_question_quality'}


def qualify(source_digest, portable=None, dependencies=None, target=None, windows=None, review=None, installer=None):
    gates = []
    def gate(name, passed, reason): gates.append({'id': name, 'status': 'passed' if passed is True else 'blocked', 'detail': reason})
    def current(evidence): return isinstance(evidence, dict) and evidence.get('source_digest') == source_digest
    portable = portable or {}; dependencies = dependencies or {}; target = target or {}; windows = windows or {}; review = review or {}
    gate('portable_automated_validation', current(portable) and portable.get('status') == 'passed' and
         all(portable.get('checks',{}).get(k) is True for k in ('api', 'unit', 'native', 'types', 'schema', 'build', 'electron', 'frozen_backend', 'portable_soak')),
         'Full portable suites, startup, packaged workflows and sustained fixture integration must pass for this source.')
    gate('dependency_advisories', current(dependencies) and dependencies.get('status') == 'passed',
         'Current npm, Python including Windows pins, and NuGet advisory checks must all pass.')
    gate('target_laptop_measurements', current(target) and target.get('kind') == 'target_laptop_telemetry' and
         target.get('phase') == 'completed' and target.get('telemetry_passed') is True and
         all(target.get('checks', {}).get(k) is True for k in TARGET_CHECKS) and
         type(target.get('duration_seconds')) in (float,int) and target['duration_seconds'] >= 5400 and
         isinstance(target.get('model_digest'),str) and re.fullmatch('[a-fA-F0-9]{64}',target['model_digest']) is not None,
         'Complete the 90-minute Windows RTX 4080 Laptop run with concurrent transcription, Qwen3-VL 8B, real requests and valid citations.')
    artifact_hash = None
    if installer is not None and installer.is_file():
        with installer.open('rb') as stream: artifact_hash = hashlib.file_digest(stream,'sha256').hexdigest()
    gate('windows_installer', current(windows) and windows.get('status') == 'passed' and windows.get('platform') == 'win32' and
         windows.get('full_model_runtime') is True and windows.get('bundled_smoke_passed') is True and
         artifact_hash is not None and artifact_hash == windows.get('installer_sha256'),
         'Build the full Windows runtime and NSIS installer on Windows, run its bundled smoke test, and supply the matching installer file/hash.')
    gate('target_manual_review', current(review) and bool(review.get('reviewer')) and bool(review.get('reviewed_at')) and
         artifact_hash is not None and review.get('installer_sha256') == artifact_hash and
         all(review.get('checks',{}).get(k) is True for k in REVIEW_CHECKS),
         'Record clean-machine installation and real meeting quality/privacy/sharing/offline/license checks against this build. Telemetry alone cannot establish them.')
    return {'schema': 1, 'source_digest': source_digest, 'release_ready': all(g['status']=='passed' for g in gates),
            'gates': gates, 'decision_scope': 'Evidence qualification, not code signing or publication. Operator evidence is an attestation, not an independent audit.'}
