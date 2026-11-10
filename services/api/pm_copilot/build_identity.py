"""Deterministic source identity, shared by packaging and release evidence."""
import hashlib
import json
from pathlib import Path
import sys

IGNORED = {'node_modules', 'dist', 'bin', 'obj', '__pycache__', '.pytest_cache'}


def ordered_sources(files, root):
    # WindowsPath compares case-insensitively. Sort relative strings explicitly
    # so an identical source archive has the same identity on both platforms.
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def source_identity(root=None):
    if getattr(sys, 'frozen', False):
        return json.loads((Path(sys._MEIPASS) / 'build-identity.json').read_text())['source_digest']
    root = Path(root or Path(__file__).resolve().parents[3])
    files = []
    for directory in ('apps', 'services', 'packages', 'scripts', 'packaging', 'tests', '.github'):
        files.extend(p for p in (root / directory).rglob('*') if p.is_file()
                     and not set(p.relative_to(root).parts).intersection(IGNORED))
    files.extend(root / name for name in ('package.json', 'package-lock.json', 'global.json', 'electron-builder.yml',
                                         'tsconfig.json', 'playwright.config.ts', 'vitest.config.mts'))
    digest = hashlib.sha256()
    for path in ordered_sources(files, root):
        digest.update(path.relative_to(root).as_posix().encode() + b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()
