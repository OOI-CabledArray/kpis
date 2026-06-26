# kpis

Tools for delivery of KPIs to NSF for the Regional Cabled Array.

KPIs are reported **per instrument per week** (Mon-Sun, labeled by the Monday date) for every
refDes in [`sitesDictionary.csv`](https://github.com/OOI-CabledArray/rca-data-tools/tree/main/rca_data_tools/qaqc/params).
Three NSF metrics, side by side:

- **C1 Technical** (`pct_technical`) — `delivered ÷ expected` from raw-archive file sizes.
  Expected = full intended weekly capacity, shrunk for **failed** (→0) / **reduced** instruments
  after their effective date. "Did the data we currently expect arrive?"
- **C3 Retention** (`pct_retention`) — same numerator ÷ the *full* original capacity (never
  shrunk). "What did we lose overall?" Failed/down-sampled instruments read low.
- **C2 Science** (`pct_science`) — % of present zarr data without a QARTOD fail flag (4),
  gross-range only (**climatology excluded**), avg across parameters. From QC'd zarr, not the
  raw archive. No zarr → gray.

Healthy instruments get C1 == C3 (they diverge only for failed/reduced); C2 is independent — a
QC-quality measure of the data that did arrive.

## Quick start

```bash
crawl_baseline     # occasional: full-capacity baseline  -> config/original_expected.csv
crawl_archive      # C1/C3 delivered side                -> reports/<date>/weekly_delivery.csv
crawl_science      # C2 QARTOD pass-rate from zarr (slow) -> reports/<date>/weekly_science.csv
compute_kpi        # join all three                      -> reports/<date>/kpi.csv + three pivots
plot_kpi --metric technical    # -> reports/<date>/kpi_heatmap_technical.png
plot_kpi --metric retention    #    (also --metric science)
plot_kpi --metric science
```

Every run writes to **`reports/<date>/`** (date defaults to today; `--date` targets a past
run), committed as browsable history. Inputs live in **`config/`** and are undated/hand-editable.

# Example pipeline usage

Report every full week since 2025-10-01 (all three metrics):

```bash
# 0. (once / occasional) build the full-capacity baseline -> config/original_expected.csv
crawl_baseline

# 1. C1/C3 delivered side over the reporting window (37 complete weeks)
crawl_archive --start 2025-10-01

# 2. C2 QARTOD pass-rate from the zarr datasets (slow -- opens S3 zarr per instrument)
crawl_science --start 2025-10-01

# 3. join delivered + baseline/overrides + instrument status + QARTOD -> kpi + 3 pivots
compute_kpi

# 4. heatmaps for each metric -> reports/<date>/kpi_heatmap_<metric>.png
plot_kpi --metric technical
plot_kpi --metric retention
plot_kpi --metric science
```

`--date` defaults to today; pass the same `--date YYYY-MM-DD` to all steps to rebuild a past
run. `crawl_baseline` is independent and only needs re-running occasionally.

## The CLIs

### `crawl_baseline` — full-capacity baseline (C1/C3 denominator)

p95 of **weekly** delivery over a recent window (default 2 yr) → `config/original_expected.csv`
(column `original_p95_weekly_bytes`). Weekly p95 smooths daily bursts and ignores brief
anomalies while reflecting sustained change. Slow; run occasionally.

```bash
crawl_baseline                                      # default: last 2 years
crawl_baseline --start 2024-06-01 --end 2026-06-01  # explicit window
```

### `crawl_archive` — reporting window (delivered side)

Walks `subsite/node/instrument/year/month[/day]/`, sums file sizes from the directory listing →
`reports/<date>/weekly_delivery.csv` (delivered bytes per instrument × complete week; partial
edge weeks excluded).

```bash
crawl_archive                                       # default: last 3 months
crawl_archive --start 2026-03-01 --end 2026-06-01   # explicit window
crawl_archive --date 2026-06-25                     # override the output date tag
```

### `crawl_science` — QARTOD pass-rate from zarr (C2)

Opens each instrument's zarr from S3 (`ooi-data/`) and computes, per ISO week, the
average-across-parameters fraction of points not flagged fail (4), **excluding climatology** →
`reports/<date>/weekly_science.csv`. Slow (one S3 zarr per instrument); no-zarr instruments
omitted. `--decompose` adds a `pct_climatology` column (parses `qartod_executed` per-test).

```bash
crawl_science                                       # default: last 3 months
crawl_science --start 2025-10-01 --date 2026-06-25
crawl_science --decompose                           # also emit pct_climatology
```

### `compute_kpi` — join into C1 + C2 + C3

Joins `weekly_delivery.csv` against the baseline (`original_expected.csv` + `baseline_overrides.csv`)
and `instrument_status.csv`, folding in `weekly_science.csv` if present, → `reports/<date>/`:

- `kpi.csv` — per instrument-week: `delivered_human`, C1 (`c1_expected_human`, `pct_technical`),
  C3 (`c3_expected_human`, `pct_retention`), C2 (`pct_science` [+ `pct_climatology`]).
- `kpi_pivot_{technical,retention,science}.csv` — instruments × weeks, whole-percent (capped at
  100; over-delivery shown `100+`), plus an `ALL_INSTRUMENTS_MEAN` row (unweighted mean of
  per-instrument %). C2 blank (gray) for no-zarr instruments.

```bash
compute_kpi                          # uses today's reports/<date>/ + config/ inputs
compute_kpi --date 2026-06-25
compute_kpi --status config/instrument_status.csv --overrides config/baseline_overrides.csv
```

### `plot_kpi` — heatmap

Renders a pivot → `reports/<date>/kpi_heatmap_<metric>.png`. Blue = full, red = under, gray =
not expected, gold `100+` = over-delivered (capped); each cell annotated with its percent.

```bash
plot_kpi --metric technical
plot_kpi --metric retention
plot_kpi --metric retention --date 2026-06-25
```

## Curated inputs (`config/`)

Three hand-maintained files, layered on the auto baseline; `crawl_baseline` never touches them,
so edits survive a refresh. Edit and re-run `compute_kpi` — no re-crawl.

### `config/instrument_status.csv` — failed/reduced (C1)

Exceptions list — only failed/reduced instruments; everything else defaults to full expected.

| column | meaning |
|---|---|
| `refDes` | instrument reference designator |
| `status` | `failed` or `reduced` |
| `effective_date` | `YYYY-MM-DD`; applies to weeks on/after this date |
| `reduced_weekly` | `reduced` only: new expected per week, human-readable (e.g. `500 MiB`) |

```csv
refDes,status,effective_date,reduced_weekly
CE02SHBP-LJ01D-06-CTDBPN106,failed,2026-04-25,
RS03CCAL-MJ03F-05-BOTPTA301,reduced,2024-09-02,112 MiB
```

`failed` → C1 expected 0 (blank KPI) after the date; `reduced` → C1 expected = `reduced_weekly`.
C3 always uses the full baseline, so the loss still shows under retention.

### `config/baseline_overrides.csv` — baseline corrections (C1 **and** C3)

Replaces the auto baseline for an instrument (both metrics) where the observed p95 is
contaminated/atypical. This is how QA/QC curates the observation-derived baseline; survives refreshes.

| column | meaning |
|---|---|
| `refDes` | instrument reference designator |
| `original_p95_weekly` | corrected full-capacity weekly volume, human-readable (e.g. `33 KiB`) |
| `note` | why it was corrected (free text) |

```csv
refDes,original_p95_weekly,note
CE04OSPS-SF01B-4F-PCO2WA102,33 KiB,auto p95 inflated by 2025 stuck-sensor files; set to typical weekly delivery
```

### `config/exclusions.csv` — grey out an instrument per metric

Sets a cell to blank (gray) for the listed metric(s) — for cases where a number would be
*invalid* rather than just low (e.g. a mis-set QARTOD test, or Navy-diverted delivery).

| column | meaning |
|---|---|
| `refDes` | instrument reference designator |
| `metrics` | space-separated `technical retention science`, or `all` |
| `reason` | why (free text) |

```csv
refDes,metrics,reason
RS01SBPS-SF01A-3C-PARADA101,science,QARTOD gross-range test mis-set in prod (good data, bad test)
CE02SHBP-LJ01D-11-HYDBBA106,all,Navy diversion makes the delivery score invalid
```

This is the unified way to grey cells: use it instead of zeroing a baseline. (`failed` in
`instrument_status.csv` is different — it sets C1 expected to 0 but keeps C3 showing the loss.)

## Automation (GitHub Actions)

- **`weekly-kpi.yml`** — Mondays + on demand. Stateless re-tabulation of the rolling window
  (`crawl_archive` → `compute_kpi` → `plot_kpi` ×2, **C1/C3 only**), then commits `reports/<date>/`.
  Re-tabulating heals weeks as late/backfilled data (e.g. hydrophone `addendum/`) arrives. Reads
  the `config/` inputs from the checkout; local runs produce the identical layout. **C2
  (`crawl_science`) is excluded** — it would OOM a 2-vCPU/7-GB hosted runner; run it out-of-band,
  commit `reports/<date>/weekly_science.csv`, and `compute_kpi` folds it in.
- **`refresh-baseline.yml`** — manual only. Regenerates `config/original_expected.csv`; curated
  overrides are untouched. Slow + shifts the denominator → review the diff.

## Notes

- **Seismometers / low-freq hydrophones aren't in this archive.** OBS (OBSBBA, OBSSPA) and HYDLF
  deliver to the IRIS/EarthScope DMC → empty folders → 0 baseline → blank KPI. Broadband
  hydrophones (HYDBB), HPIES, and D1000 *are* here and tallied — though HYDBB are currently
  greyed via `config/exclusions.csv` (Navy diversion).
- **Non-standard folder names** are mapped in `PATH_OVERRIDES` in `archive_crawler.py` (e.g. the
  D1000 logs under `RASFLA301_D1000`, not `D1000A301`).
