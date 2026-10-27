# Context capacity matrix results

Manifest: `context-capacity-small-retry-20261027`. Results as of 2026-10-27T20:27:40+00:00.
These are observed loads and 10%/90% recall probes, not automatic library promotions.

| Model | Target | GPUs | Planned ctx | Observed ctx | Load s | Recall | Status |
|---|---|---|---:|---:|---:|---|---|
| `ornith-1.5:9b` | compact | 1 | 24064 | 24064 | 38.6 | pass | passed |
| `ministral-3:3b` | compact | 1 | 56832 | 56832 | 25.1 | pass | passed |
| `devstral-small:24b` | compact | 0 | 115200 | 115200 | 48.2 | pass | passed |

Failed cases remain unpromoted; inspect their individual logs and receipts. A projected trained ceiling that fails to load needs a lower-context follow-up. Fast/slow paired speed tests are a separate step at the same context.
