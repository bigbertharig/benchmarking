#!/usr/bin/env python3
"""Guarded same-binary Qwen3.8 PLE file-vs-GPU correctness smoke."""
import argparse
import json
import os
import pathlib
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path('/mnt/shared/plans/shoulders/benchmarking')
MODEL_DIR = pathlib.Path('/data/model-hotset/qwen3.8-flash-next-ud-q4_k_xl')
MODEL = MODEL_DIR / 'Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf'
TABLE = MODEL_DIR / 'Qwen3.8-Flash-Next-UD-Q4_K_XL-00002-of-00004.gguf'
BUILD = pathlib.Path('/data/bench-staging/ple-shard-llama-build-20261113')
IMAGE = 'llama-runtime:b11669'
PORT = 18124
NAME = 'q38-ple-model-smoke'

def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def cmd(*args, check=True):
    return subprocess.run(args, text=True, capture_output=True, check=check)

def write(path, data):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    os.replace(tmp, path)

def mem_available_mib():
    for line in pathlib.Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) / 1024
    raise RuntimeError('MemAvailable unavailable')

def gpu_mib():
    text = cmd('nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits').stdout
    return [int(line) for line in text.splitlines()]

def request(path, data=None, timeout=4):
    payload = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(f'http://127.0.0.1:{PORT}{path}', data=payload,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=pathlib.Path, required=True)
    parser.add_argument('--gpu-layers', type=int, default=8)
    args = parser.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    record = {'schema': 'q38-ple-model-smoke/1', 'started_at': stamp(),
              'model': str(MODEL), 'table': str(TABLE), 'build': str(BUILD),
              'gpu_layers': args.gpu_layers, 'modes': {}, 'status': 'running'}
    write(out / 'checkpoint.json', record)
    try:
        if not (MODEL.is_file() and TABLE.is_file() and (BUILD/'llama/bin/llama-server').is_file()
                and (BUILD/'libple_shard_store.so').is_file()):
            raise FileNotFoundError('model, table or isolated build missing')
        from hardware_inventory import scan_cards, require_ids, check_planned_power
        cards = scan_cards()
        require_ids([0, 1, 2, 3, 4, 5], cards)
        check_planned_power([0, 1, 2, 3, 4, 5])
        if any(cards[i]['used_mib'] > 1024 for i in range(6)):
            raise RuntimeError('selected GPU in use')
        if mem_available_mib() < 8192:
            raise RuntimeError('insufficient host headroom before load')
        layout = out / 'layout.json'
        cmd('python3', str(ROOT/'scripts/analysis/inspect_ple_layout.py'),
            '--gguf', str(TABLE), '--gguf-py', '/data/bench-staging/kvchat-q41-tile-src/gguf-py',
            '--output', str(layout))
        tensors = json.loads(layout.read_text())['table_tensors']
        if len(tensors) != 1 or tensors[0]['name'] != 'per_layer_token_embd.weight' or tensors[0]['tensor_type'] != 'IQ4_NL':
            raise RuntimeError('unexpected PLE table tensor')
        offset = tensors[0]['data_offset']
        record['layout'] = tensors[0]
        prompt = 'Explain a B-tree index in one concise sentence.'
        body = {'prompt': prompt, 'n_predict': 16, 'temperature': 0,
                'cache_prompt': False, 'ignore_eos': True, 'stream': False}
        for mode in ('file', 'gpu'):
            stage = {'started_at': stamp(), 'status': 'running',
                     'host_available_mib_before': round(mem_available_mib()),
                     'gpu_mib_before': gpu_mib()}
            record['modes'][mode] = stage
            write(out / 'checkpoint.json', record)
            cmd('docker', 'rm', '-f', NAME, check=False)
            launch = ['docker', 'run', '--detach', '--gpus', 'all', '--network', 'host',
                      '--memory', '28g', '--memory-swap', '28g', '--name', NAME,
                      '-v', f'{MODEL_DIR}:/models:ro',
                      '-v', f'{BUILD}/llama/bin:/opt/llama/bin:ro',
                      '-v', f'{BUILD}/libple_shard_store.so:/ple/libple_shard_store.so:ro',
                      '-e', 'LD_LIBRARY_PATH=/opt/llama/bin']
            if mode == 'gpu':
                launch += ['-e', 'PLE_SHARD_LIB=/ple/libple_shard_store.so',
                           '-e', f'PLE_SHARD_GGUF=/models/{TABLE.name}',
                           '-e', f'PLE_SHARD_OFFSET={offset}',
                           '-e', 'PLE_1060_MIB=5120', '-e', 'PLE_1070_MIB=7168']
            launch += ['--entrypoint', '/opt/llama/bin/llama-server', IMAGE,
                       '--model', f'/models/{MODEL.name}', '--host', '127.0.0.1',
                       '--port', str(PORT), '--ctx-size', '8192', '--batch-size', '64',
                       '--ubatch-size', '64', '--parallel', '1', '--threads', '4',
                       '--threads-batch', '4', '--load-mode', 'mmap',
                       '--split-mode', 'none', '--main-gpu', '0',
                       '--gpu-layers', str(args.gpu_layers), '--slot-prompt-similarity', '0']
            stop = threading.Event()
            guard = {'breached': False, 'lowest_available_mib': mem_available_mib()}
            def monitor():
                while not stop.wait(2):
                    now = mem_available_mib()
                    guard['lowest_available_mib'] = min(guard['lowest_available_mib'], now)
                    if now < 4096:
                        guard['breached'] = True
                        cmd('docker', 'rm', '-f', NAME, check=False)
                        break
            watcher = threading.Thread(target=monitor, daemon=True)
            try:
                stage['container_id'] = cmd(*launch).stdout.strip()[:12]
                watcher.start()
                begin = time.monotonic()
                while time.monotonic() - begin < 600:
                    if guard['breached']:
                        raise RuntimeError('MemAvailable below 4 GiB guard')
                    if cmd('docker', 'inspect', '-f', '{{.State.Running}}', NAME, check=False).stdout.strip() != 'true':
                        raise RuntimeError('llama-server exited before ready')
                    try:
                        if request('/health', timeout=2).get('status') == 'ok':
                            break
                    except Exception:
                        pass
                    time.sleep(2)
                else:
                    raise TimeoutError('model did not become ready in 600 s')
                stage['load_s'] = round(time.monotonic() - begin, 2)
                stage['gpu_mib_ready'] = gpu_mib()
                stage['host_available_mib_ready'] = round(mem_available_mib())
                t0 = time.monotonic()
                response = request('/completion', body, timeout=900)
                stage['request_s'] = round(time.monotonic() - t0, 2)
                stage['content'] = response.get('content')
                stage['tokens_predicted'] = response.get('tokens_predicted')
                stage['timings'] = response.get('timings')
                stage['gpu_mib_after'] = gpu_mib()
                stage['status'] = 'passed' if stage['content'] else 'failed'
            except Exception as exc:
                stage['status'] = 'failed'
                stage['error'] = f'{type(exc).__name__}: {exc}'
            finally:
                stop.set()
                if watcher.is_alive(): watcher.join(timeout=5)
                stage['guard'] = guard
                stage['container_state'] = cmd('docker', 'inspect', '-f', '{{json .State}}', NAME, check=False).stdout.strip()
                (out/f'{mode}.log').write_text(cmd('docker', 'logs', NAME, check=False).stderr)
                cmd('docker', 'rm', '-f', NAME, check=False)
                stage['finished_at'] = stamp()
                write(out/'checkpoint.json', record)
            if stage['status'] != 'passed':
                break
        if all(record['modes'].get(mode, {}).get('status') == 'passed' for mode in ('file', 'gpu')):
            record['same_content'] = record['modes']['file']['content'] == record['modes']['gpu']['content']
            record['status'] = 'passed' if record['same_content'] else 'failed'
        else:
            record['status'] = 'failed'
    except Exception as exc:
        record['status'] = 'failed'
        record['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        record['finished_at'] = stamp()
        write(out/'terminal.json', record)
        print(json.dumps({'status': record['status'], 'output': str(out/'terminal.json'),
                          'same_content': record.get('same_content'), 'error': record.get('error')}), flush=True)
    return 0 if record['status'] == 'passed' else 1

if __name__ == '__main__':
    sys.exit(main())
