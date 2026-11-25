# Qwen3.8-27B interactive generation profile

The `interactive` registry profile owns reasoning-off generation settings: temperature 0.7, top-p 0.8,
top-k 20, min-p 0, presence penalty 1.5, and repeat penalty 1. These values are published both as
profile inference metadata and llama-server startup arguments. The benchmark `default` profile retains
its previous reasoning-on and temperature-zero settings.

The source evidence is the three-cell Harness experiment recorded in
`llm-harness/docs/research/qwen38_sampler_and_tool_contract_2026-11-24.md`. The profile is a bounded
interactive choice; the trial does not establish universal quality or a model ranking. Future sampler
comparisons belong in Benchmarking's existing runtime-matrix/campaign workflow before profile updates.
Gateway and Harness consume the selected route; Harness no longer sends sampler overrides.

Verification on 2026-11-24 confirmed that all six sampler settings reach the running b11669 server,
and three real Harness requests omitted sampler fields. Qwen completed a four-tool, three-turn audit
in 23.00 seconds. The sampler-boundary answer was correct; the release-failure audit remained incomplete.
Registered model-library, capacity, and test-infrastructure checks passed 49 tests and 48 subtests.
The existing shared-KV capacity test is now registered in the capacity suite.

Private runtime and request-field receipts are in the Pi's
`Desktop/Transfer/coding_resume_20261124/` directory. The source export and all three Pi consumers,
plus the rig's Orchestration projection, carry hash
`2ee8308ce3f544b008814180144fda5b01a2478df4dc4554c16964b1cd5d170f`.
