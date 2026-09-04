# kpis

Weekly NSF KPI tabulation for the Regional Cabled Array, from the OOI raw data archive.

KPIs are reported **per instrument per week** (Mon–Sun, labeled by the following Monday) for every
refDes in [`sitesDictionary.csv`](https://github.com/OOI-CabledArray/rca-data-tools/tree/main/rca_data_tools/qaqc/params).
Three NSF metrics — C1 and C3 share the delivered-bytes numerator and differ only in the
denominator, C2 comes from a different source entirely:

- **C1 Technical** (`pct_technical`) — delivered ÷ expected from raw-archive file sizes. After an
  instrument fails or its sampling regimen changes, the baseline expectation is adjusted for that
  instrument's denominator.
- **C3 Retention** (`pct_retention`) — same numerator ÷ the *full* original capacity (never
  adjusted). Failed or down-sampled instruments read low, reflecting the true loss against
  original capacity.
- **C2 Science** (`pct_science`) — % of present zarr data without a QARTOD fail flag, gross-range
  only (climatology excluded), averaged across parameters. Instruments without automated QARTOD
  (cameras, BOTPT, seismic, hydrophones) are excluded from this metric. Derived from QC'd zarr,
  not the raw archive.

For both C1 and C3, instruments subject to Navy diversion are recorded as 100% when there are no
active missing-data reports in Nereus.

## Quick start

```bash
# 0. (once / occasional) build the full-capacity baseline -> config/original_expected.csv
crawl_baseline

# 1. C1/C3 delivered side          -> reports/<date>/weekly_delivery.csv
crawl_archive --start 2025-10-01

# 2. C2 QARTOD pass-rate from zarr -> reports/<date>/weekly_science.csv   (slow, memory-heavy)
crawl_science --start 2025-10-01

# 3. join delivered + baseline/overrides + instrument status + QARTOD
compute_kpi                        # -> reports/<date>/kpi.csv + three pivots

# 4. heatmaps                      -> reports/<date>/kpi_heatmap_<metric>.png
plot_kpi --metric technical
plot_kpi --metric retention
plot_kpi --metric science
```

Every run writes to **`reports/<date>/`**, committed as browsable history. `--date` defaults to
today; pass the same `--date YYYY-MM-DD` to all steps to rebuild a past run. Inputs live in
**`config/`** and are hand-editable.

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

Fast — it only re-joins CSVs, so re-run it freely after editing `config/`.

```bash
compute_kpi                          # uses today's reports/<date>/ + config/ inputs
compute_kpi --date 2026-06-25
compute_kpi --instrument-overrides /tmp/what-if.csv   # score against alternate overrides
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

| file | who maintains it | what it does |
|---|---|---|
| [`original_expected.csv`](#configoriginal_expectedcsv--auto-baseline-do-not-hand-edit) | `crawl_baseline` (auto) | the C1/C3 full-capacity denominator |
| [`baseline_overrides.csv`](#configbaseline_overridescsv--baseline-corrections-c1-and-c3) | hand | corrects that denominator where the auto p95 is atypical |
| [`instrument_status.csv`](#configinstrument_statuscsv--failedreduced-instruments-c1) | hand | shrinks the C1 denominator for failed/reduced instruments |
| [`instrument_overrides.csv`](#configinstrument_overridescsv--per-metric-fixed-scores-or-grey-outs) | hand | fixes or greys out a score per metric |

The three hand-maintained files survive a `crawl_baseline` refresh. Edit and re-run `compute_kpi` —
no re-crawl needed.

### Time windows

The three hand-maintained files are all time-windowed and may hold **several rows per `refDes`**. A
row covers the weeks whose Monday falls in `[start_date, end_date)` — end exclusive. Empty
`start_date` means "from the beginning of time", empty `end_date` "still open".

Two ways to end a row, and they compose:

- **Close it** — set `end_date`. With no successor row the week falls back to the computed default
  (auto p95 baseline, healthy status, no override). Best when a condition simply ended: an
  instrument was repaired, a bad QC test was fixed.
- **Supersede it** — leave `end_date` empty and add a row with a later `start_date`. Of the rows
  covering a week, the one starting latest wins. Best when one value replaces another, since there
  is no pair of dates to keep in sync and therefore no gap to open by accident.

This is how a maintenance cruise splits the record. Old weeks keep scoring under the old
assumption, so already-reported KPIs don't shift retroactively.

```csv
# instrument_status.csv — one row per fact: failed, then repaired on the cruise
refDes,status,start_date,end_date,reduced_weekly,note
CE02SHBP-LJ01D-06-CTDBPN106,failed,2025-12-01,2026-08-20,,replaced on 2026 annual cruise

# instrument_overrides.csv — greyed pre-cruise, computed after the sensor swap
refDes,start_date,end_date,pct_technical,pct_retention,pct_science,note
RS01SBPS-SF01A-3C-PARADA101,,,,,exclude,gross-range test bad on the old sensor
RS01SBPS-SF01A-3C-PARADA101,2026-08-20,,,,,new sensor installed; compute normally
```

Because `start_date` is compared against the week's **Monday**, a row dated `2026-08-20` (a
Thursday) first applies to the week of `2026-08-24`; the partial cruise week still scores under the
old assumption. Date it `2026-08-17` to move the whole transition week across.

> A closed window with no successor reverts to the *computed* value. In the two override files that
> means the auto p95 baseline — which is often the very number the override existed to correct. If
> a correction should stand for all time, leave `end_date` empty.

A date in these files is an **effect** date, not a measurement date. `baseline_overrides.csv` notes
like "Sept 2025 avg weekly delivery" record which window the corrected number was *derived* from;
the correction itself applies to the whole record, so those rows leave both bounds empty. Date a
row only when the instrument's intended capacity actually changed then.

### `config/original_expected.csv` — auto baseline (do not hand-edit)

Generated by `crawl_baseline` and **overwritten** on every refresh — put corrections in
`baseline_overrides.csv` instead, which is applied on top and survives. The only config file that
is not time-windowed: one full-capacity figure per instrument for the whole record.

| column | meaning |
|---|---|
| `refDes` | instrument reference designator |
| `first_day`, `last_day` | `YYYYMMDD` bounds of the data the p95 was computed from |
| `weeks_with_data` | how many complete weeks contributed |
| `original_p95_weekly_bytes` | the denominator itself |
| `original_p95_weekly_human` | same, human-readable (informational) |

### `config/instrument_status.csv` — failed/reduced instruments (C1)

Only failed/reduced instruments need entries; everything else defaults to full expected.

| column | meaning |
|---|---|
| `refDes` | instrument reference designator |
| `status` | `failed` or `reduced` |
| `start_date` | `YYYY-MM-DD`; first day the status applies |
| `end_date` | `YYYY-MM-DD` when it ended (exclusive), or empty if still current |
| `reduced_weekly` | `reduced` only: new expected per week, human-readable (e.g. `500 MiB`) |
| `note` | why — especially why a window was closed |

`failed` → C1 expected 0 for those weeks; `reduced` → C1 expected = `reduced_weekly`. Outside every
window the instrument is healthy at the full baseline, so setting `end_date` is how a repaired or
replaced instrument returns to full expected capacity. C3 always uses the full original baseline,
so the loss still shows in retention.

### `config/baseline_overrides.csv` — baseline corrections (C1 and C3)

Replaces the auto p95 baseline for instruments where the observed p95 is atypical (anomaly period,
commissioning burst, intentional sampling change).

| column | meaning |
|---|---|
| `refDes` | instrument reference designator |
| `start_date` / `end_date` | window this row covers, either may be empty (see [time windows](#time-windows)) |
| `original_p95_weekly` | corrected full-capacity weekly volume, human-readable |
| `note` | reason for correction |

### `config/instrument_overrides.csv` — per-metric fixed scores or grey-outs

| column | meaning |
|---|---|
| `refDes` | instrument reference designator |
| `start_date` / `end_date` | window this row covers, either may be empty (see [time windows](#time-windows)) |
| `pct_technical` | C1 override |
| `pct_retention` | C3 override |
| `pct_science` | C2 override |
| `note` | reason |

Each metric column accepts:

| value | effect |
|---|---|
| *(empty)* | compute normally |
| a number (e.g. `100`) | use that fixed score |
| `exclude` | grey out (blank cell) |

```csv
refDes,start_date,end_date,pct_technical,pct_retention,pct_science,note
CE02SHBP-LJ01D-11-HYDBBA106,,,100,100,exclude,Navy diversion makes the delivery score invalid
```

Leave a metric empty to compute it normally — e.g. `<refDes>,,,,,exclude,<reason>` greys C2 only and
leaves C1/C3 computed, the usual shape for a mis-set QC test.

Use `exclude` when a computed score would be misleading (mis-set QC test, instrument not yet
deployed). Use a fixed score when the true value is known from an external source (EarthScope
delivery, HITL QAQC). Prefer this over zeroing the baseline. (`failed` in `instrument_status.csv`
is different — it sets C1 expected to 0 while C3 continues to show the loss.)

Two precedence rules to know: C1/C3 fixed scores are skipped during failed weeks (they fall back to
computed), and C2 zarr-derived values always win over a fixed `pct_science` when
`weekly_science.csv` has an entry for that instrument-week.

## Automation

- **Prefect deployment** (`prefect.yaml`, flow in `rca_kpis/flow.py`) — **first Monday of the
  month**, 12:00 UTC, on ECS Fargate (16 vCPU / 120 GB; the C2 zarr scan is memory-heavy).
  Runs all three metrics sequentially: `crawl_archive` → `crawl_science` → `compute_kpi` →
  `plot_kpi` ×3, then commits `reports/<date>/` to `main` (needs a `GH_PAT` env var in the
  work pool). Monthly suits quarterly reporting, and re-tabulating still heals earlier weeks
  as late/backfilled data arrives; trigger a one-off run for anything sooner.
  Crawler output (OPTAA skips, missing QARTOD, broken zarr, empty windows, peak RSS) goes to
  the Prefect UI **and** to `reports/<date>/pipeline.log`, committed beside the numbers —
  data status is often why a cell is blank or low.
- **`refresh-baseline.yml`** (GitHub Actions) — manual only. Regenerates
  `config/original_expected.csv`. Curated overrides are untouched. Slow and shifts the
  C1/C3 denominator — review the diff.

## Notes

- **EarthScope/Navy-diverted instruments** — OBS (OBSBBA, OBSSPA), HYDLF, and HYDBBA deliver to
  IRIS/EarthScope or are subject to Navy diversion; OOI archive delivery is zero or invalid for
  these. All three groups are scored 100% C1/C3 and greyed in C2 via `instrument_overrides.csv`.
  HPIES and D1000 are in the OOI archive and tallied normally.
- **Non-standard archive paths** — mapped in `PATH_OVERRIDES` in `archive_crawler.py`
  (e.g. D1000 logs under `RASFLA301_D1000`, not `D1000A301`).
