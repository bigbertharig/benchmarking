#!/usr/bin/env python3
"""Make the instrumented moe_one_replay worker selectable for matched GPU traces."""
import argparse
from pathlib import Path

def patch(path: Path) -> None:
    source = path.read_text()
    old = '        chat worker{"worker", "", nullptr, "1"};\n        if (!add_chat(worker, model, vocab, pair_cap)) return 211;'
    new = ('        const char * worker_gpu_env = std::getenv("KV_REPLAY_CHAT_GPU");\n'
           '        const std::string worker_gpu = worker_gpu_env && *worker_gpu_env ? worker_gpu_env : "1";\n'
           '        chat worker{"worker", "", nullptr, worker_gpu.c_str()};\n'
           '        if (!add_chat(worker, model, vocab, pair_cap)) return 211;')
    if source.count(old) != 1:
        raise SystemExit("expected exactly one moe_one_replay worker declaration")
    source = source.replace(old, new, 1)
    old = '            std::fprintf(stderr, "ONE_REPLAY_DONE depth=%d gpu=1 tokens=%d\\n", depth, tokens);'
    new = '            std::fprintf(stderr, "ONE_REPLAY_DONE depth=%d gpu=%s tokens=%d\\n", depth, worker_gpu.c_str(), tokens);'
    if source.count(old) != 1:
        raise SystemExit("expected exactly one moe_one_replay completion marker")
    path.write_text(source.replace(old, new, 1))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    patch(ap.parse_args().source)
