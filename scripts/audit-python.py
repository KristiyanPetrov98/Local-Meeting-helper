"""Audit every pinned Python lock (including Windows-only pins) against PyPI advisories.

Network failures are incomplete evidence, never a clean result. No models are downloaded.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import urllib.request


def audit(root):
    pins = {}
    for lock in sorted((root / 'services/api').glob('*.lock')):
        for name, version in re.findall(r'^([\w.-]+)==([^\s;\\]+)', lock.read_text(), re.M):
            pins.setdefault((name, version), []).append(str(lock.relative_to(root)))

    def check(pin):
        name, version = pin
        result = {'name': name, 'version': version, 'locks': pins[pin]}
        try:
            with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json', timeout=30) as response:
                data = json.load(response)
            result['vulnerabilities'] = [{k: v.get(k) for k in ('id', 'aliases', 'fixed_in', 'link', 'withdrawn')}
                                         for v in data.get('vulnerabilities', []) if not v.get('withdrawn')]
        except Exception as exc:
            result['error'] = type(exc).__name__
        return result
    with ThreadPoolExecutor(max_workers=8) as pool: packages = list(pool.map(check, sorted(pins)))
    errors = sum('error' in p for p in packages)
    vulnerable = sum(bool(p.get('vulnerabilities')) for p in packages)
    return {'schema': 1, 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
            'source': 'PyPI JSON version API, published advisories only; not a source-code security proof',
            'status': 'incomplete' if errors else 'failed' if vulnerable else 'passed',
            'package_versions': len(packages), 'errors': errors, 'vulnerable_packages': vulnerable, 'packages': packages}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(Path(__file__).resolve().parents[1])
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'packages'}))
    raise SystemExit(0 if report['status'] == 'passed' else 1)
