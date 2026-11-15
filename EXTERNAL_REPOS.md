# External repositories

This index follows outside runtimes and benchmark suites used or investigated
by this repo. It complements the [model library](MODEL_LIBRARY.md), whose
registry tracks model files and sources. Last checked: 2026-11-15.

## Runtimes and placement research

| Upstream | Role | Local source / installed baseline |
|---|---|---|
| [Niko1221/Strata](https://github.com/Niko1221/Strata) | Alternative runtime and memory-placement comparison | Pi source `~/Strata` at `baf16363` (main, one commit after `v0.2.14.1` on 2026-11-15); rig release bundle `/data/bench-staging/strata-v0.2.10` with Control/engine 0.1.56. The source checkout is for review; the rig remains pinned. Start with [Strata memory test plan](STRATA_MEMORY_TEST_PLAN.md) and [placement guide](MODEL_LOADING_AND_CHAT_PLACEMENT.md). |
| [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) | Primary inference baseline | Runtime image/build ownership: [llm_orchestration](https://github.com/bigbertharig/llm_orchestration/blob/main/shared/scripts/llama_runtime/README.md). Each comparison must preserve its image digest and flags. |
| [Helldez/BigMoeOnEdge](https://github.com/Helldez/BigMoeOnEdge) | Expert-placement research reference | Pi checkout `/media/bryan/shared/plans/shoulders/bigmoe-upstream` at `930b2c9` on 2026-11-15; [research gates](EXPERT_TENSOR_SHARDING_RESEARCH.md). |
| [crgregersen/m10dis](https://github.com/crgregersen/m10dis) | Within-expert sharding and peer-transfer research reference | Pi contribution checkout `~/m10dis-pr-work` at `71c69e3` on 2026-11-15; [research gates](EXPERT_TENSOR_SHARDING_RESEARCH.md). |

## Benchmark suite sources

These are cached upstream suites. Their local revisions are snapshots; do not
silently replace them under an existing scored campaign.

| Upstream | Local checkout | HEAD on 2026-11-15 |
|---|---|---|
| [ShishirPatil/gorilla](https://github.com/ShishirPatil/gorilla) (BFCL) | `repos/bfcl` | `cf12f01` |
| [princeton-nlp/SWE-bench](https://github.com/princeton-nlp/SWE-bench) | `repos/swebench` | `fa79f3a` |
| [laude-institute/terminal-bench-2](https://github.com/laude-institute/terminal-bench-2) | `repos/terminal_bench_2` | `53ff2b8` |

## Checking for updates

The source links above are the upstream projects. A local checkout or release
pin is a snapshot, not an automatic update. For a checkout, run
`git -C PATH status --short --branch`, then `git -C PATH fetch origin` and
`git -C PATH log --oneline HEAD..origin/BRANCH` (replace PATH and BRANCH from
the table or the checkout's `git branch -r`). Review release notes and changes
before changing a deployed binary, model recipe, or benchmark baseline. Record
the new source revision and the validation receipt here when adopting it.
