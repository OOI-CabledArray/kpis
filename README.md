# kpis

Weekly NSF KPI tabulation for the Regional Cabled Array, from the OOI raw data archive.

KPIs are reported **per instrument per week** (Mon–Sun, labeled by the following Monday) for every
refDes in [`sitesDictionary.csv`](https://github.com/OOI-CabledArray/rca-data-tools/tree/main/rca_data_tools/qaqc/params).
Three NSF metrics:

- **C1 Technical** (`pct_technical`) — delivered ÷ expected from raw-archive file sizes.
  Expected = full intended weekly capacity, shrunk for **failed** (→ 0) / **reduced** instruments
  after their effective date. "Did the data we currently expect arrive?"
- **C3 Retention** (`pct_retention`) — same numerator ÷ the *full* original capacity (never
  shrunk). "What fraction of the original instrument complement is still delivering?" Failed or
  down-sampled instruments read low.
- **C2 Science** (`pct_science`) — % of present zarr data without a QARTOD fail flag (4),
  gross-range only (climatology excluded), averaged across parameters. Derived from QC'd zarr,
  not the raw archive. No zarr → gray.

Healthy instruments get C1 == C3; they diverge only for failed/reduced instruments. C2 is
independent — a quality measure of the data that did arrive.

## Scoring assumptions

- **Failed/reduced instruments** — after the effective date, C1 expected is set to 0 (failed) or
  a reduced weekly volume. C3 always uses the full original baseline so the loss is visible in
  retention.
- **Navy-diverted instruments** (HYDBBA, HYDLFA, OBS/OBSSP) — data routes to the IRIS/EarthScope
  DMC, not the OOI archive. Archive delivery is zero by design. C1 and C3 are scored 100%; C2 is
  greyed. See `config/instrument_overrides.csv`.
- **QARTOD unavailable** — instruments without a zarr (cameras, BOTPT, some others) are greyed in
  C2. PARADA sensors are also greyed in C2 because the gross-range test is mis-configured in
  production (good data, bad test).

## Quick start

```bash
crawl_baseline     # occasional: full-capacity baseline   -> config/original_expected.csv
crawl_archive      # C1/C3 delivered side                 -> reports/<date>/weekly_delivery.csv
crawl_science      # C2 QARTOD pass-rate from zarr (slow) -> reports/<date>/weekly_science.csv
compute_kpi        # join all three                       -> reports/<date>/kpi.csv + pivots
plot_kpi --metric technical    # -> reports/<date>/kpi_heatmap_technical.png
plot_kpi --metric retention
plot_kpi --metric science
```

Every run writes to **`reports/<date>/`** (date defaults to today; `--date` targets a past run),
committed as browsable history. Inputs live in **`config/`** and are hand-editable.

## Example pipeline

```bash
# 0. (once / occasional) build the full-capacity baseline
crawl_baseline

# 1. C1/C3 delivered side over the reporting window
crawl_archive --start 2025-10-01

# 2. C2 QARTOD pass-rate from zarr (slow — opens S3 zarr per instrument)
crawl_science --start 2025-10-01

# 3. join delivered + baseline/overrides + instrument status + QARTOD -> kpi + pivots
compute_kpi

# 4. heatmaps
plot_kpi --metric technical
plot_kpi --metric retention
plot_kpi --metric science
```

`--date` defaults to today; pass the same `--date YYYY-MM-DD` to all steps to rebuild a past run.

## The CLIs

### `crawl_baseline` — full-capacity baseline (C1/C3 denominator)

p95 of **weekly** delivery over a recent window (default 2 yr) → `config/original_expected.csv`.
Weekly p95 smooths daily bursts and ignores brief anomalies while reflecting sustained change.
Slow; run occasionally.

```bash
crawl_baseline                                      # default: last 2 years
crawl_baseline --start 2024-06-01 --end 2026-06-01  # explicit window
```

### `crawl_archive` — reporting window (delivered side)

Walks `subsite/node/instrument/year/month[/day]/`, sums file sizes → `reports/<date>/weekly_delivery.csv`
(delivered bytes per instrument × complete week; partial edge weeks excluded).

```bash
crawl_archive                                       # default: last 3 months
crawl_archive --start 2026-03-01 --end 2026-06-01   # explicit window
crawl_archive --date 2026-06-25                     # override the output date tag
```

### `crawl_science` — QARTOD pass-rate from zarr (C2)

Opens each instrument's zarr from S3 (`ooi-data/`) and computes, per week, the
average-across-parameters fraction of points not flagged fail (4), **excluding climatology** →
`reports/<date>/weekly_science.csv`. No-zarr instruments are omitted. `--decompose` adds a
`pct_climatology` column (parses `qartod_executed` per-test; slower).

**Run locally** — this opens dozens of multi-GB S3 zarr stores and will OOM a hosted runner.

```bash
crawl_science                                       # default: last 3 months
crawl_science --start 2025-10-01 --date 2026-06-25
crawl_science --decompose                           # also emit pct_climatology
```

### `compute_kpi` — join into C1 + C2 + C3

Joins `weekly_delivery.csv` against the baseline (`original_expected.csv` + `baseline_overrides.csv`)
and `instrument_status.csv`, applies `instrument_overrides.csv`, folds in `weekly_science.csv` if
present → `reports/<date>/`:

- `kpi.csv` — per instrument-week: `delivered_human`, C1 (`c1_expected_human`, `pct_technical`),
  C3 (`c3_expected_human`, `pct_retention`), C2 (`pct_science` [+ `pct_climatology`]).
- `kpi_pivot_{technical,retention,science}.csv` — instruments × weeks, whole-percent (capped at
  100; over-delivery shown `100+`), plus an `ALL_INSTRUMENTS_MEAN` row. C2 blank for no-zarr instruments.

```bash
compute_kpi                          # uses today's reports/<date>/ + config/ inputs
compute_kpi --date 2026-06-25
compute_kpi --instrument-overrides config/instrument_overrides.csv
```

### `plot_kpi` — heatmap

Renders a pivot → `reports/<date>/kpi_heatmap_<metric>.png`. Blue = full, red = under, gray =
not scored, gold `100+` = over-delivered (capped); each cell annotated with its percent.

```bash
plot_kpi --metric technical
plot_kpi --metric retention
plot_kpi --metric retention --date 2026-06-25
```

## Curated inputs (`config/`)

All four files are hand-maintained and survive a `crawl_baseline` refresh. Edit and re-run
`compute_kpi` — no re-crawl needed.

### `config/instrument_status.csv` — failed/reduced instruments (C1)

Only failed/reduced instruments need entries; everything else defaults to full expected.

| column | meaning |
|---|---|
| `refDes` | instrument reference designator |
| `status` | `failed` or `reduced` |
| `effective_date` | `YYYY-MM-DD`; applies to weeks on/after this date |
| `reduced_weekly` | `reduced` only: new expected per week, human-readable (e.g. `500 MiB`) |

`failed` → C1 expected 0 after the date; `reduced` → C1 expected = `reduced_weekly`.
C3 always uses the full original baseline, so the loss still shows in retention.

### `config/baseline_overrides.csv` — baseline corrections (C1 and C3)

Replaces the auto p95 baseline for instruments where the observed p95 is atypical (anomaly period,
commissioning burst, intentional sampling change). Survives `crawl_baseline` refreshes.

| column | meaning |
|---|---|
| `refDes` | instrument reference designator |
| `original_p95_weekly` | corrected full-capacity weekly volume, human-readable |
| `note` | reason for correction |

### `config/instrument_overrides.csv` — per-metric fixed scores or grey-outs

Each metric column (`pct_technical`, `pct_retention`, `pct_science`) accepts:

| value | effect |
|---|---|
| *(empty)* | compute normally |
| a number (e.g. `100`) | use that fixed score |
| `exclude` | grey out (blank cell) |

C1/C3 fixed scores are skipped during failed weeks (fall back to computed). C2 zarr-derived values
always win over fixed scores when `weekly_science.csv` has an entry for that instrument-week.

| column | meaning |
|---|---|
| `refDes` | instrument reference designator |
| `pct_technical` | C1 override |
| `pct_retention` | C3 override |
| `pct_science` | C2 override |
| `note` | reason |

```csv
refDes,pct_technical,pct_retention,pct_science,note
RS01SBPS-SF01A-3C-PARADA101,,,exclude,QARTOD gross-range test mis-set in prod (good data, bad test)
CE02SHBP-LJ01D-11-HYDBBA106,100,100,exclude,Navy diversion makes the delivery score invalid
```

Use `exclude` when a computed score would be misleading (mis-set QC test, instrument not yet
deployed). Use a fixed score when the true value is known from an external source (EarthScope
delivery, HITL QAQC). Prefer this over zeroing the baseline. (`failed` in `instrument_status.csv`
is different — it sets C1 expected to 0 while C3 continues to show the loss.)

## Automation (GitHub Actions)

- **`weekly-kpi.yml`** — Mondays + on demand. Runs `crawl_archive` → `compute_kpi` →
  `plot_kpi` (C1/C3 only), then commits `reports/<date>/`. Re-tabulating each week heals
  previously incomplete weeks as late/backfilled data arrives. **C2 is excluded** — run
  `crawl_science` out-of-band, commit the resulting `weekly_science.csv`, and `compute_kpi`
  will fold it in on the next run.
- **`refresh-baseline.yml`** — manual only. Regenerates `config/original_expected.csv`.
  Curated overrides are untouched. Slow and shifts the C1/C3 denominator — review the diff.

## Notes

- **EarthScope/Navy-diverted instruments** — OBS (OBSBBA, OBSSPA), HYDLF, and HYDBBA deliver to
  IRIS/EarthScope or are subject to Navy diversion; OOI archive delivery is zero or invalid for
  these. All three groups are scored 100% C1/C3 and greyed in C2 via `instrument_overrides.csv`.
  HPIES and D1000 are in the OOI archive and tallied normally.
- **Non-standard archive paths** — mapped in `PATH_OVERRIDES` in `archive_crawler.py`
  (e.g. D1000 logs under `RASFLA301_D1000`, not `D1000A301`).
