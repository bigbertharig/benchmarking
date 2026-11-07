from pathlib import Path
import shutil

source = Path('/mnt/shared/experiments/kv-expert-chat-20261107')
target = Path('/mnt/shared/plans/shoulders/benchmarking/results/runtime_experiments/kv_expert_chat_20261107')
target.mkdir(parents=True, exist_ok=True)
for path in source.iterdir():
    if path.is_file() and path.name != 'README.md':
        shutil.copy2(path, target / path.name)
shutil.copy2(
    '/data/bench-staging/kvchat-b11669-src/examples/simple/simple.cpp',
    target / 'expert_simple.cpp',
)
print(target)
