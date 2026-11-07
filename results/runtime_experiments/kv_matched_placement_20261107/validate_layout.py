from pathlib import Path
import json
import re

root = Path(__file__).parent
inventory = json.loads((root / 'inventory.json').read_text())
names = {
    tensor['name']: tensor['bytes']
    for layer in inventory['expert_layers'].values()
    for group in layer.values()
    for tensor in group
}

def inspect(name: str):
    raw = (root / name).read_bytes()
    assert b'\r' not in raw, f'{name}: carriage return in regex file'
    rows = [line.split('\t', 1) for line in raw.decode().splitlines()]
    assert len(rows) == 4
    assert [int(card) for card, _ in rows] == [1, 2, 3, 4]
    patterns = [(int(card), re.compile(pattern)) for card, pattern in rows]
    totals = {card: 0 for card in range(1, 5)}
    counts = {card: 0 for card in range(1, 5)}
    matched_names = set()
    for tensor_name, size in names.items():
        matched = [card for card, pattern in patterns if pattern.fullmatch(tensor_name)]
        assert len(matched) <= 1, (name, tensor_name, matched)
        if not matched:
            continue
        matched_names.add(tensor_name)
        totals[matched[0]] += size
        counts[matched[0]] += 1
    return totals, counts, matched_names

control, control_counts, control_names = inspect('contiguous.tsv')
candidate, candidate_counts, candidate_names = inspect('interleaved_balanced.tsv')
assert control_names == candidate_names
assert control_counts == candidate_counts == {1: 14, 2: 10, 3: 10, 4: 10}
for card in range(1, 5):
    assert abs(candidate[card] - control[card]) < 4 * 1048576
    print(f'CUDA{card}: control={control[card] / 1048576:.2f} MiB '
          f'candidate={candidate[card] / 1048576:.2f} MiB '
          f'tensors={candidate_counts[card]}')
print('validated', len(candidate_names), 'placed expert tensors, LF-only files')
