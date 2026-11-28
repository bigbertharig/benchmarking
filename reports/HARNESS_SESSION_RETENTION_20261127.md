# Harness session continuity trial ? 2026-11-27

Harness originally supplied only four prior exchanges (12,000 characters) to
each new inference request. This caused corrected facts to disappear after four
later turns, even though the selected models had much larger context windows.
The failure was in chat reconstruction, not evidence of model memory limits.

The baseline used `scripts/integration/harness_session_trial.py`, the
`harness-control/1` API, the Coding role without tools, and one ready model at
a time. Each model completed 22 turns across recent-correction,
outside-window, and explicit-checkpoint cases. Ready roster and served identity
were stable.

| Served model | Context offered | Recent correction | Outside four-turn window | Two checkpoints and final |
| --- | ---: | --- | --- | --- |
| `gpt-oss:20b` | 131,072 | pass | fail | pass / pass / pass |
| `gemma-4:e4b` | 131,072 | pass | fail | pass / pass / pass |
| `gemma-4:12b` | 262,144 | pass | fail | pass / pass / pass |

Harness now reconstructs every completed exchange from the durable parent-run
chain. Before sending the request, it checks the complete conversation against
the selected route's context length and fails explicitly if it cannot fit;
old turns are no longer silently discarded. The same outside-window case
passed live with both models below:

| Served model | Final prior exchanges supplied | Final prompt tokens | Case result | Seven-turn time | Receipt SHA-256 prefix |
| --- | ---: | ---: | --- | ---: | --- |
| `gpt-oss:20b` | 6 | 590 | pass | 30.17 s | `be4d07a355fd` |
| `gemma-4:e4b` | 6 | 861 | pass | 22.49 s | `f8e4d6e29beb` |

This verifies the live handoff across more than four turns on two local models.
It does not test a conversation near the actual context limit. Automatic compaction has since been added with separate conversation and
task-agent pressure thresholds. Gateway Chat and Coding use the conversation
policy; task agents retain a later trigger and can still compact if needed.
A first live Gemma E4B direct-provider trial used a declared 8,192-token
envelope to force compaction without changing rig loading. One summary covered
nine older exchanges, retained the newest exchange, and the final answer
correctly returned owner Nila, codeword `amber-birch-17`, and gate `QA-43`
without the obsolete owner Mara. The run succeeded in 2.75 seconds; its
summary call used 1,820 prompt tokens and 57 completion tokens. Receipt:
`llm-harness/results/context_compaction_live_20261128.json`, SHA-256 prefix
`6761c1635de9`. This is one model and one checkpoint, not repeated-compaction
or true-boundary evidence. Shared-KV chat compaction remains a separate gate
because auxiliary calls mutate its live cache. The raw per-turn run IDs, answers, usage, and roster
snapshots are in ignored Pi receipts
`results/harness_session_trials/20261127/gpt-oss-20b-continuous.json` and
`results/harness_session_trials/20261127/gemma4-e4b-continuous.json`.
