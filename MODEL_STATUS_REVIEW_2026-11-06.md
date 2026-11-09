# Model status review — 2026-11-06

Source: `model_registry.json` and the selected rows in `results/model_library_scoreboard.json` generated 2026-11-03. These scores compare the same test IDs but some runs differ in class, context, reasoning setting, or sample count; use the named receipts for a strict head-to-head. Status is a deployment judgment, not a count of finished benchmark rows: **active** means a routine supported option; **candidate** means experimental, specialized, or not yet preferred; **archived** remains reproducible storage. A model can be fully benchmarked and still be a candidate. This review does not change role assignments in `model_roles.json`.

| Candidate before review | Evidence | Decision |
| --- | --- | --- |
| Ornith 1.5 35B-A3B | BBH 92.4% validated, HumanEval+ 85.4% full, strict prompt IFEval 82%; 164.9 tok/s at 8K on 3090; 262K depth passed on two cards | **Promote active** as a fast brain option. Gemma 4 31B still leads on code and IFEval; no default role switch. |
| Qwen3.8 27B | HumanEval+ 90.2% full and strict prompt IFEval 92%, but selected validated BBH 41.6% versus Qwen3.6 27B at 91.6% | Keep candidate; review task/setting behavior before replacing an active brain. |
| Qwen3 Coder Next 80B-A3B | HumanEval+ 89.0% full versus active Coder 30B at 87.8%; MBPP+ both 75.4%; BBH 23.0% versus 81.8%; 162,304-token six-card depth passed | Keep candidate for expert-placement and long-context research. Six-card routine cost is not justified by the measured code gain alone. |
| K2 V2 Instruct 70B | 21 selected smoke tests; BBH 11.9%, strict prompt IFEval 20%, HumanEval+ 72%; five/six-card full-offload loads pass but depth is unvalidated | Keep candidate for controlled retest; cold-storage priority on NVMe. |
| Nex N2.5 Mini | Full code and validated reasoning: HumanEval+ 82.3%, BBH 73.8%; template-specific thinking control | Keep candidate; active brain options score higher. |
| Mellum 2.1 12B-A2.5B | Full code HumanEval+ 83.5%, MBPP+ 72.5%; BBH 45.6%; needs two 1060s | Keep candidate for a specialized code worker comparison. |
| MiniCPM5 2B | Strict prompt IFEval 84% but full code HumanEval+ 0.6%, MBPP+ 1.9% | Keep candidate only for a narrow cheap-worker test. |
| Qwen3.8 Flash Next Q2 | Strata speed and placement experiments; no selected comparable quality suite rows | Keep candidate. |

The existing 22 active models were not demoted in this pass: their roles and availability need a separate replacement decision, and low scores in one suite alone do not invalidate a specialized role. This pass corrects stale candidate notes that still claimed integration phases had not run. The Q2 Strata pack is part of its model bundle, not general benchmark staging: 66,423,878,624 GGUF bytes + 35,469,412,079 pack bytes = **101,893,290,703 bytes** (94.9 GiB) of required files for the tested Strata runtime. The remaining staging bytes are Strata software, archives, and small probes.

## Loading-stage update, 2026-11-08

Qwen3.8 Flash-Next Q2_0 now has a concise `loading_stage` record in `model_registry.json`: `ready_for_benchmark` for its tested Strata recipe, with 8K default context and a 256K single-chat limit supported by near-full-context recall. Detailed bundle, route, and chat experiment receipts remain in the runtime research area. This does not change its candidate deployment status; a small application and harness quality sample is the next step when GPUs are available. See [MODEL_LOADING_GATE.md](MODEL_LOADING_GATE.md) for the loading and context checkpoint.
