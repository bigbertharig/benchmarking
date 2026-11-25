import json
from pathlib import Path
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def test_endpoint_suite_isolated_real_process(tmp_path):
    import shutil
    root = Path(__file__).parents[1]
    install = tmp_path / 'standalone'; install.mkdir()
    for name in ['run_endpoint_suite.py', 'benchmark_records.py', 'benchmark_file_lock.py']:
        shutil.copy(root / 'scripts/active' / name, install / name)
    paths = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            paths.append(self.path)
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert body['model'] == 'outside-registry'
            self.send_response(200); self.end_headers()
            self.wfile.write(json.dumps({'model': 'outside-registry', 'choices': [{'message': {'content': 'four'}}]}).encode())
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    config = {'schema': 'benchmark-endpoint/1', 'endpoint': f'http://127.0.0.1:{server.server_port}/v1',
              'model': {'id': 'user-model', 'route': 'outside-registry', 'revision': 'test-revision'}}
    dataset = {'schema': 'benchmark-exact-match/1', 'id': 'arithmetic', 'cases': [{'id': 'a', 'prompt': '2+2', 'expected': 'four'}]}
    (install / 'config.json').write_text(json.dumps(config)); (install / 'dataset.json').write_text(json.dumps(dataset))
    env = dict(os.environ, HOME=str(tmp_path / 'fresh-home')); env.pop('PYTHONPATH', None)
    try:
        result = subprocess.run([sys.executable, str(install / 'run_endpoint_suite.py'), '--config', 'config.json', '--dataset', 'dataset.json', '--out', 'receipt.json'], cwd=install, env=env, capture_output=True, text=True)
    finally:
        server.shutdown(); server.server_close(); thread.join()
    assert result.returncode == 0, result.stderr
    receipt = json.loads((install / 'receipt.json').read_text())
    assert receipt['score'] == 1
    assert receipt['model_record']['revision'] == 'test-revision'
    assert receipt['efficiency']['telemetry'] is None
    assert len(receipt['dataset_sha256']) == 64
    assert paths == ['/v1/chat/completions']
