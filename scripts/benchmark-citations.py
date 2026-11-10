"""Measure actual source-verified citation lookups, using synthetic public text only."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services/api'))
from pm_copilot.document_parser import parse_document
from pm_copilot.store import Store


def measure():
    text = ('Release evidence: Friday. This synthetic line exercises precise source offsets.\n' * 25000)[:1950000]
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / 'benchmark.sqlite3')
        project = store.create('Public benchmark')['projects'][0]['id']
        job = store.upload_document(project, 'evidence.txt', text.encode())
        parsed = parse_document('evidence.txt', text.encode())
        store.commit_parsed(project, job['document_id'], job['revision_id'], parsed)
        chunks = store.revision_chunks(project, job['revision_id'])[-10:]
        start = time.perf_counter(); store.citation(project, chunks[-1]['id']); cold = time.perf_counter() - start
        tracemalloc.start()
        latencies = []
        for i in range(500):
            start = time.perf_counter()
            citation = store.citation(project, chunks[i % len(chunks)]['id'])
            latencies.append((time.perf_counter() - start) * 1000)
            assert citation['quote'] == chunks[i % len(chunks)]['text']
        _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop(); store.close()
        return {'scope': 'CPU SQLite citation validation; synthetic 1.95M-character plain text, last ten chunks',
                'iterations': len(latencies), 'source_characters': len(text), 'cold_ms': cold * 1000,
                'warm_median_ms': statistics.median(latencies), 'warm_p95_ms': sorted(latencies)[474],
                'warm_max_ms': max(latencies), 'warm_peak_allocated_bytes': peak,
                'gpu_or_model_test': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); report = measure()
    args.output.write_text(json.dumps(report, indent=2) + '\n'); print(json.dumps(report))
