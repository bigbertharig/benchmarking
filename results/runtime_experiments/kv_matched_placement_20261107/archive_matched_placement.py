from pathlib import Path
import shutil

source = Path('/mnt/shared/experiments/kv-expert-chat-20261107')
target = Path('/mnt/shared/plans/shoulders/benchmarking/results/runtime_experiments/kv_matched_placement_20261107')
target.mkdir(parents=True, exist_ok=True)
labels = ('matched_local_A1_short', 'matched_local_B_short', 'matched_local_A2_short',
          'matched_local_B_depth', 'matched_local_A_depth')
for label in labels:
    for suffix in ('.start', '.finish', '.exit', '.log', '.gpu.csv', '.pcie.txt'):
        path = source / f'{label}{suffix}'
        if path.exists():
            shutil.copy2(path, target / path.name)
root = source / 'matched_placement_20261107'
for name in ('.gitattributes', 'README.md', 'run_matched_placement.sh', 'run_corrected_placement.sh',
             'run_local_placement.sh', 'wait_stage_run.sh', 'stage_model.sh',
             'restore_chat_server.sh', 'postprocess_matched_placement.sh',
             'analyze_matched_placement.py',
             'archive_matched_placement.py', 'balance_layout.py',
             'validate_layout.py',
             'contiguous.tsv', 'interleaved.tsv',
             'interleaved_balanced.tsv', 'inventory.json',
             'campaign.start', 'campaign.finish', 'campaign.exit',
             'corrected.start', 'corrected.finish', 'corrected.exit',
             'corrected.log', 'failed_crlf.log', 'failed_crlf.exit',
             'failed_crlf.campaign.log',
             'stage.start', 'stage.finish', 'stage.exit', 'stage.log',
             'local_campaign.start', 'local_campaign.finish',
             'local_campaign.exit', 'local_campaign.log',
             'postprocess.finish', 'postprocess.log', 'summary.json'):
    path = root / name
    if path.exists():
        shutil.copy2(path, target / name)
path = source / 'matched_placement_20261107.campaign.log'
if path.exists():
    shutil.copy2(path, target / path.name)
for stale_prefix in ('matched_A1_short.', 'matched_B_balanced_short.'):
    for path in target.iterdir():
        if path.is_file() and path.name.startswith(stale_prefix):
            path.unlink()
print(target)
