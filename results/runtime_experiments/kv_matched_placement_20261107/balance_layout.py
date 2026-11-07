from __future__ import annotations

import json
import math
import random
from pathlib import Path

root = Path(__file__).parent
data = json.loads((root / 'inventory.json').read_text())
layers = [1, 3, 5, 8, 10, 12, 14, 17, 19, 21, 23, 26, 28, 30, 32, 34, 37, 39, 41, 43, 45, 48]
size = {i: sum(t['bytes'] for values in data['expert_layers'][str(i)].values() for t in values)
        for i in layers}
original = [1] * 7 + [2] * 5 + [3] * 5 + [4] * 5
target = {card: sum(size[layer] for layer, assigned in zip(layers, original) if assigned == card)
          for card in range(1, 5)}
round_robin = [1, 2, 3, 4] * 5 + [1, 1]
rng = random.Random(20261107)

def score(cards: list[int]) -> float:
    totals = {card: sum(size[layer] for layer, assigned in zip(layers, cards)
                        if assigned == card) for card in range(1, 5)}
    deviation = sum(((totals[c] - target[c]) / 1048576) ** 2 for c in target)
    adjacent = sum(cards[i] == cards[i + 1] for i in range(len(cards) - 1))
    # Keep all four cards active in each stretch of eight MoE layers.
    clumping = sum(4 - len(set(cards[i:i + 8])) for i in range(0, 15))
    return deviation + 150 * adjacent + 50 * clumping

best = round_robin[:]
best_score = score(best)
for restart in range(24):
    cards = round_robin[:] if restart == 0 else best[:]
    if restart:
        for _ in range(15):
            i, j = rng.sample(range(len(cards)), 2)
            cards[i], cards[j] = cards[j], cards[i]
    current = score(cards)
    for step in range(30000):
        i, j = rng.sample(range(len(cards)), 2)
        if cards[i] == cards[j]:
            continue
        cards[i], cards[j] = cards[j], cards[i]
        candidate = score(cards)
        temperature = 1000 * (0.005 ** (step / 30000))
        if candidate < current or rng.random() < math.exp((current - candidate) / temperature):
            current = candidate
            if candidate < best_score:
                best, best_score = cards[:], candidate
        else:
            cards[i], cards[j] = cards[j], cards[i]

totals = {card: sum(size[layer] for layer, assigned in zip(layers, best)
                    if assigned == card) for card in range(1, 5)}
assert sorted(best).count(1) == 7
assert all(sorted(best).count(c) == 5 for c in (2, 3, 4))
lines = []
for card in range(1, 5):
    group = [layer for layer, assigned in zip(layers, best) if assigned == card]
    lines.append(f'{card}\tblk[.]({"|".join(map(str, group))})[.]ffn_(up|down)_exps[.]weight\n')
(root / 'interleaved_balanced.tsv').write_bytes(''.join(lines).encode('utf-8'))
print('score', round(best_score, 2))
print('cards', best)
for card in range(1, 5):
    print(card, 'MiB', round(totals[card] / 1048576, 2),
          'target', round(target[card] / 1048576, 2),
          'delta', round((totals[card] - target[card]) / 1048576, 2))
