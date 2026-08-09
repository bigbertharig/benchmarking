# Data Import - GPU Rig Edition

Operational checklist for the local brain model. Derived from `docs/data_import.md`
but trimmed to what runs on the rig and structured as prompt-ready stages.

Canonical source: `docs/data_import.md`. If this file and that one disagree,
the original wins — but this file can diverge on rig-specific workflow.

---

## Pipeline stages

Each stage = one prompt to the brain model. The orchestrator validates output
before advancing to the next stage. If validation fails, the orchestrator
re-prompts with the error (max 2 retries, then flag for human).

```
STAGE 1  Research       read tracker, identify source, report plan
STAGE 2  Download       fetch raw data, report what landed
STAGE 3  Convert        write converter, produce parquet
STAGE 4  Reference      write reference.json with source info + metrics
STAGE 5  Metadata       run generate_metadata.py, verify traps
STAGE 6  QA             validate parquet schema, loc_id, routing keywords
STAGE 7  Package        run package_handoff.py, produce MANIFEST
```

---

## Stage 1: Research

**Goal:** understand the source before touching any data.

**Model reads:**
- The assigned row in `docs/future/future_data_import_tracker.csv`
- The matching detail section in `docs/future/future_data_import.md`

**Model reports:**
- Source name, upstream URL, download method
- License and paid-lane eligibility
- Expected geographic scope and level (admin_0, admin_1, etc.)
- Expected file format (CSV, JSON, API, etc.)
- Any gotchas or blockers noted in the tracker

**Orchestrator validates:**
- Reported license matches tracker CSV
- Geographic level is appropriate for early runs (admin_0 preferred)
- No blockers that would prevent completion

---

## Stage 2: Download

**Goal:** get raw data onto disk.

**Model does:**
- Downloads raw data to `county-map-raw/<source_id>/`
- Reports: file names, total size, row/record count, format

**Orchestrator validates:**
- Files exist on disk
- Size is reasonable (not 0, not unexpectedly huge)
- Format matches what Stage 1 predicted

---

## Stage 3: Convert

**Goal:** produce a canonical parquet from raw data.

**Model reads:**
- An existing converter as pattern (start with `convert_owid_co2.py` for
  simple country-level sources)
- The raw data headers/schema from Stage 2

**Model produces:**
- `convert_<source_id>.py` script
- Runs it, outputs parquet to `county-map-data/global/<category>/<source_id>/`

**Parquet contract:**

| Column | Type | Rule |
|--------|------|------|
| `loc_id` | string | First column. Canonical geo ID (ISO3 for admin_0). Never invented. |
| `year` | int64 | For yearly sources. Integer, not string. |
| `timestamp` | datetime | For temporal sources. Normalized to period start. |
| All metrics | float64 | Use `pd.to_numeric(errors='coerce')`. Never strings. |

**Do NOT include:** country names, state names, FIPS codes, or anything
derivable from loc_id.

**Orchestrator validates:**
- Parquet loads without error
- `loc_id` column present, values match expected format
- All metric columns are float64
- Row count is reasonable
- No duplicate (loc_id, year) pairs

---

## Stage 4: Reference

**Goal:** write the curated source contract.

**Model produces:** `reference.json` in the source directory.

**Structure (must match exactly):**

```json
{
  "source": {
    "source_id": "<id>",
    "source_name": "<Human-Readable Name>",
    "source_url": "<upstream URL>",
    "license": "<license string>",
    "category": "<category>",
    "geographic_level": "<admin_0|admin_1|admin_2|...>",
    "geographic_coverage": "<global|US|regional>",
    "description": "<1-2 sentence description>",
    "keywords": ["<search terms users would type>"],
    "topic_tags": ["<broad topic categories>"]
  },
  "metrics": {
    "<column_name>": {
      "name": "<Human-Readable Name>",
      "unit": "<unit string>",
      "aggregation": "<sum|mean|weighted_avg|max|min|skip>"
    }
  }
}
```

**Keyword rules:**
- Include the obvious terms AND common synonyms/acronyms
- Think about what a user would type: "carbon dioxide" not just "CO2"
- Include both technical and casual terms
- Include the full name AND the abbreviation (CO2/carbon dioxide, GHG/greenhouse gas)

**Orchestrator validates:**
- Valid JSON with `source` and `metrics` top-level keys
- `source.geographic_level` matches the actual data
- `source.source_id` matches the directory name
- Every parquet metric column has a metrics entry
- Keywords include common synonyms (orchestrator runs a gap check)

---

## Stage 5: Metadata

**Goal:** generate metadata.json from the parquet + reference.json.

**Model runs:**
```bash
python build/generate_metadata.py "<absolute path to parquet>"
```

**Trap checks (MUST verify every time):**

| Trap | What to check | How to fix |
|------|---------------|------------|
| geographic_level rewrite | metadata.json `geographic_level` must match reference.json `source.geographic_level` | If mismatched, the generator overwrote it. Manually patch metadata.json. |
| files pointer | metadata.json must have `"files": {"data": {"name": "<parquet filename>"}}` | If missing, cloud mode will 404. Re-run generator or add manually. |
| metric list | metadata.json metrics must match parquet columns (no extra helper/count cols) | Remove any spurious metrics from metadata.json. |

**Orchestrator validates:**
- metadata.json exists
- geographic_level matches reference.json
- files.data.name matches actual parquet filename
- metric count matches parquet column count (minus loc_id/year/timestamp)

---

## Stage 6: QA

**Goal:** verify the source would work in the app.

**Checks:**

| Check | Method | Pass criteria |
|-------|--------|---------------|
| Parquet loads | `pq.read_table(path).schema` | No errors, schema printed |
| loc_id coverage | Count unique loc_ids | Matches expected country/region count |
| loc_id format | Check all loc_ids match pattern | All ISO3 (3-char) for admin_0 |
| No duplicates | Check (loc_id, year) uniqueness | Zero duplicates |
| Metric types | Check all metric cols are double | No string metrics |
| Keyword routing | Check keywords against common search terms | No major gaps |
| Null check | Check for 0s that should be NULL | Suspicious 0-patterns flagged |

**Orchestrator validates:**
- All checks pass
- Any flags are documented in PREP_LOG.md

---

## Stage 7: Package

**Goal:** bundle everything for USB handoff.

**Model runs:**
```bash
python tools/gpu_rig/package_handoff.py \
  --source-id <source_id> \
  --category <category> \
  --out <output_dir>
```

**Output folder:**
```
<source_id>_handoff/
  MANIFEST.json
  data/<data>.parquet
  reference.json
  metadata.json
  convert_<source_id>.py
  PREP_LOG.md
```

**Orchestrator validates:**
- MANIFEST.json exists and is valid JSON
- SHA256 checksums match actual files
- expected_qa fields are populated

---

## loc_id quick reference

| Level | Format | Example |
|-------|--------|---------|
| admin_0 (country) | ISO3 | `USA`, `DEU`, `CHN` |
| admin_1 (state/province) | ISO3-XX | `USA-CA`, `DEU-BY` |
| admin_2 (county/district) | ISO3-XX-NNNNN | `USA-CA-6037` |
| Water body | 3-char code | `XOP` (Pacific), `XOA` (Atlantic) |

For early calibration runs, stick to admin_0 (ISO3 country codes).

---

## Common mistakes

1. **Flat reference.json** — source fields must be nested under `"source": {}`,
   not at the top level.
2. **loc_id last** — put loc_id as the first column, not the last.
3. **Missing synonyms** — "CO2" without "carbon dioxide", "GHG" without
   "greenhouse gas". Always include both.
4. **String metrics** — forgot `pd.to_numeric(errors='coerce')`. Check dtype.
5. **Invented loc_ids** — use canonical geo utilities, never make up codes.
6. **0 instead of NULL** — missing data should be NaN/NULL, not 0.
