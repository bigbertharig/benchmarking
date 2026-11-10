# Qwen3.8 Q4 one-chat depth launch gate (2026-11-10)

The first 16K/32K/50K depth attempt stopped before launching a probe. The
Manager refused a new GPU0 benchmark lease because the existing frozen Q4
service was already busy without a lease, although the persistent
`qwen38-q4-frozen` claim still covered GPUs 0-5. The model was not stopped
or changed. The sequence terminal and stage receipt record this gate failure.

The follow-up [four-case tier campaign](../../../../campaigns/strata_q4_onechat_tier_overnight_20261110.json)
uses controlled `restart_loaded` stages under the existing persistent claim.
This is a coordination correction, not an inference result.
