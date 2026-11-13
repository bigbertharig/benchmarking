# Benchmark hardware sessions

The rig's `rig observe` report is the physical hardware source. Benchmarking
reads it once at the start of a model-loading sequence and saves
`session_hardware.json` beside the run's `manifest.json`. The receipt records
host GPU index, UUID, PCI bus, VRAM, link and route, current usage, and role
assignments. Every stage receives its path as `BENCHMARK_SESSION_FILE`.

The snapshot fixes **identity and experimental assignments**. It is not an
availability lease: the rig Manager still owns admission, claims, and loads.
On resume, the runner compares the UUID and PCI bus at every requested index
with the saved receipt. A changed mapping requires a new run ID. A reboot with
the same physical mapping can resume. Other benchmarking probes can read the
same receipt rather than running their own card-number assumptions.

## Select roles in a schema 2 series

```json
{
  "schema": 2,
  "name": "example",
  "hardware_roles": {
    "model_card": {"min_vram_mb": 20000, "prefer": "most_vram"},
    "helper_card": {"min_vram_mb": 6000, "max_vram_mb": 12000,
                    "prefer": "least_vram"}
  },
  "defaults": {"state": "ready", "timeout_s": 1800, "freeze": true},
  "cases": [{
    "id": "probe",
    "gpus": ["{gpu:model_card}", "{gpu:helper_card}"],
    "command": ["python3", "scripts/integration/my_probe.py",
                "--model-host-gpu", "{gpu:model_card}",
                "--helper-uuid", "{uuid:helper_card}"]
  }]
}
```

Run `--check` to see the current resolution without creating receipts. For a
real managed run, `--session-gpus auto` creates a persistent claim covering the
resolved stage cards. The selector matches physical capabilities even when a
card is busy. Set `available_only: true` to select among unclaimed, unleased
cards with less than 1,000 MiB used at scan time. The Manager still checks
live admission. Each role selects one distinct
card. Role order in `hardware_roles` determines priority when selectors overlap.
`name_contains` is available for tests that deliberately compare product models;
prefer VRAM and topology requirements for portable tests.

The runner expands `{gpu:role}` and `{uuid:role}` in stage commands, environment,
output paths, and GPU lists before validating the existing stage contract. Existing
manifests with numeric GPU IDs continue to run; their selected physical identities
are also frozen in the session receipt. The source manifest hash remains the resume
key, so editing selectors requires a fresh run ID.

## Next consumers

The sequence runner is the first consumer. Runtime probes and campaign suites
should read `BENCHMARK_SESSION_FILE` for their physical card identity and save its
path or hash in their own result. They must still verify the actual selected
Docker UUIDs and allocations. A later campaign-runner integration should use the
same receipt schema; its manager-selected cards are resolved after admission and
then appended to that run's receipt. Model knowledge remains in benchmarking's
model registry; executable hardware control remains with the rig and Manager.
