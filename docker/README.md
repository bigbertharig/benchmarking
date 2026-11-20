# Evaluation suites

Benchmarking owns the suite contracts, model knowledge, campaign runner, and
result receipts. Run `rig scan` and `rig status` for current hardware and
capacity. A card or port table from an earlier installation is not a placement
rule for the current rig.

## Run a campaign

The declarative runner is `scripts/active/run_campaign.py`; see
[CAMPAIGN_RUNNER.md](CAMPAIGN_RUNNER.md) for manifests, checkpoints, model
identity checks, and resume behavior. For a request of the form “these models
on these suites,” use `scripts/active/submit_campaign_request.py`. The request
compiler accepts active and candidate models and lets the Manager choose
placement unless the manifest explicitly pins GPU IDs. Suite execution is
scripted; it does not require an LLM to watch each step.

Before a campaign, verify `python3 scripts/active/export_model_library.py check`
and run the campaign's `--dry-run`. The controller and rig each need a
Benchmarking checkout or a mounted copy. The submit command accepts explicit
paths for the controller's shared results root, rig's results root, and rig's
Benchmarking checkout. A shared drive is one deployment option.

For live state, use `rig status`, `rig observe`, and the campaign's saved
`status.json`; do not infer placement from a static example table. The
completion waiter in `scripts/integration/wait_for_campaign_completion.py`
reports one terminal result from that status receipt.

## Suites

| Suite | Measures |
| --- | --- |
| [bench-pipeline](bench-pipeline/README.md) | instruction and JSON reliability |
| [bench-code](bench-code/README.md) | code generation |
| [bench-reasoning](bench-reasoning/README.md) | math, reasoning, and reading |
| [bench-knowledge](bench-knowledge/README.md) | factual knowledge |
| [bench-agent](bench-agent/README.md) | tool use and recovery |
| [bench-routing](bench-routing/README.md) | cheapest sufficient execution tier |
| [bench-runtime](bench-runtime/README.md) | stability, latency, context, and telemetry |
| [bench-daedalmap](bench-daedalmap/README.md) | mapping research tasks |
| [bench-dataimport](bench-dataimport/README.md) | data-import understanding |
| [bench-geoimport](bench-geoimport/README.md) | geometry preparation |

Each suite has its own README and output contract. The separate frozen local
image suite is under [../suites/vision](../suites/vision/README.md).
