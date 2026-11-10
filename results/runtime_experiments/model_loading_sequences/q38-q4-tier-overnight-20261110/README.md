# Qwen3.8 Q4 tier matrix: interrupted prefill-1024 attempt

The first overnight attempt was stopped after its 64K one-slot GPU0 baseline
spent more than 14 minutes on the initial roughly 16K-token prompt. The engine
was active but warned that forcing `--prefill 1024` with no RAM-backed prompt
lend slots could make long prompts much slower and repeatedly read SSD data.
The prior 15K prompt with automatic prefill took about 226 seconds; those
conditions are not identical, so this is a diagnostic lead, not a measured
speed ratio.

Manager's first stop signal exposed a sequence-runner bug: an interrupted
stage marked `continue_on_failure` was followed by subsequent cases. The
targeted rig process group was then stopped. No complete depth curve or
multi-card result was produced; the model is currently unloaded. The runner
now treats an operator interruption as terminal regardless of the
continue-on-failure flag. The revised manifest uses automatic prefill and
requires a fresh run ID.
