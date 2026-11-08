#!/usr/bin/env python3
"""Recheck the staged Q4 shard bytes and free space before pack creation."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

MODEL = Path('/data/model-hotset/qwen3.8-flash-next-ud-q4_k_xl')
MANIFEST = MODEL / 'bundle_manifest.json'
MIN_FREE = 3 * 1024**3


def main():
    spec = json.loads(MANIFEST.read_text())
    if spec.get('schema') != 'model-bundle/1' or len(spec.get('files', [])) != 4:
        raise RuntimeError('unexpected Q4 bundle manifest')
    checked = []
    for entry in spec['files']:
        path = MODEL / entry['relative_path']
        if not path.is_file() or path.stat().st_size != entry['bytes']:
            raise RuntimeError(f'missing or wrong-size shard: {path}')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != entry['sha256']:
            raise RuntimeError(f'hash mismatch: {path}')
        checked.append({'path': str(path), 'bytes': entry['bytes'], 'sha256': digest.hexdigest()})
        print(f'verified {path.name}', flush=True)
    stats = os.statvfs(MODEL)
    free = stats.f_bavail * stats.f_frsize
    if free < MIN_FREE:
        raise RuntimeError(f'NVMe free space {free} below {MIN_FREE}')
    receipt = {'status': 'passed', 'checked_at': datetime.now(timezone.utc).isoformat(),
               'files': checked, 'nvme_free_bytes': free, 'required_free_bytes': MIN_FREE}
    out = MODEL / 'runtime' / 'q4_stage_preflight.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_suffix('.tmp')
    temp.write_text(json.dumps(receipt, indent=2) + '\n')
    os.replace(temp, out)
    print(out, flush=True)


if __name__ == '__main__':
    main()
