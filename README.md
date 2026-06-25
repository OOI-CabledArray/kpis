# kpis

Tools for delivery of KPIs to NSF for the Regional Cabled Array.

The delivery KPI is `delivered ÷ expected × 100`, **per instrument per week**
(Mon-Sun, labeled by the Monday start date),
computed from file sizes in the [OOI raw data archive](https://rawdata.oceanobservatories.org/files/)
for every reference designator in [`sitesDictionary.csv`](https://github.com/OOI-CabledArray/rca-data-tools/tree/main/rca_data_tools/qaqc/params).

Two NSF metrics are produced side by side. They share one baseline — the full
intended weekly capacity (`original_expected.csv`) — and differ only in the denominator:

- **C1 Technical** (`pct_technical`) — full capacity, shrunk for **failed** (→ 0) and
  **reduced** (→ set by QA/QC based on instrument performance) instruments after their effective date. "Did the data we currently expect arrive?"
- **C3 Retention** (`pct_retention`) — always the full original capacity, never shrunk.
  "What did we lose overall?" A failed or down-sampled instrument reads low here.

Healthy instruments get C1 == C3; they diverge only for failed/reduced ones.

## Quick start

```bash
crawl_baseline     # occasional: full-capacity baseline  -> original_expected.csv
crawl_archive      # the reporting window                -> reports/<date>/weekly_delivery.csv
compute_kpi        # delivered vs expected               -> reports/<date>/kpi.csv + two pivots
plot_kpi --metric technical    # heatmap -> reports/<date>/kpi_heatmap_technical.png
plot_kpi --metric retention    # heatmap -> reports/<date>/kpi_heatmap_retention.png
```

Every run writes all its outputs into a single dated folder, **`reports/<date>/`** (date
defaults to today; pass `--date` to chain steps or target a past run). This is identical
whether run locally or by the GitHub Action, and the folder is committed — so the heatmaps
and CSVs accumulate as a browsable history. The curated inputs — `baseline_overrides.csv`,
`instrument_status.csv`, and the auto `original_expected.csv` — live at the repo root, are
**not** dated, and are hand-editable.

# Example pipeline usage

Report every full week since 2025-10-01 (through today), both metrics:

```bash
# 0. (once / occasional) build the full-capacity baseline -> original_expected.csv
crawl_baseline

# 1. crawl the delivered side over the reporting window (37 complete weeks)
crawl_archive --start 2025-10-01

# 2. join delivered against baseline (+ overrides) + instrument status -> kpi + pivots
compute_kpi

# 3. heatmaps for each metric -> reports/<date>/kpi_heatmap_<metric>.png
plot_kpi --metric technical
plot_kpi --metric retention
```

Steps 1–3 default `--date` to today; to re-run a past report on a later day, pass the same
`--date YYYY-MM-DD` to all three. `crawl_baseline` is independent and only needs re-running
occasionally.

## The CLIs

### `crawl_baseline` — full-capacity baseline (C3 denominator)

Crawls a recent window (default: last 2 years) and writes `original_expected.csv`. The
baseline column is **`original_p95_weekly_bytes`** — the **p95 of weekly delivery** per
instrument, its demonstrated full-rate weekly capacity (the `_human` column is just a
readable mirror).
p95 of *weekly* totals (not daily) smooths daily burstiness, and as the high end it
ignores brief anomalies while still reflecting a sustained change. Slow (walks
hydrophone/camera day trees); run occasionally, not every report.

```bash
crawl_baseline                                      # default: last 2 years
crawl_baseline --start 2024-06-01 --end 2026-06-01  # explicit window
```

`original_expected.csv` is hand-editable — correct any baseline inflated by a malfunction
(e.g. a stuck sensor that dumped oversized files for weeks).

### `crawl_archive` — the reporting window (delivered side)

Walks `subsite/node/instrument/year/month[/day]/`, sums file sizes from the directory
listing, and writes `reports/<date>/weekly_delivery.csv`: delivered bytes per instrument ×
complete week (Mon-Sun, labeled by the Monday date; partial edge weeks are excluded).

```bash
crawl_archive                                       # default: last 3 months
crawl_archive --start 2026-03-01 --end 2026-06-01   # explicit window
crawl_archive --date 2026-06-25                     # override the output date tag
```

### `compute_kpi` — delivered vs expected (C1 + C3)

Joins `reports/<date>/weekly_delivery.csv` against the baseline (`original_expected.csv` with
`baseline_overrides.csv` applied on top) and `instrument_status.csv`, writing one detailed
CSV plus two pivots (all into `reports/<date>/`):

- `kpi.csv` — one row per instrument-week: `delivered_human`, then C1
  (`c1_expected_human`, `pct_technical`) and C3 (`c3_expected_human`, `pct_retention`).
- `kpi_pivot_technical.csv` and `kpi_pivot_retention.csv` — instruments × weeks grids of
  **whole-percent** values (capped at 100; over-delivery shown as `100+`), with a final
  `ALL_INSTRUMENTS_MEAN` row (the unweighted mean of per-instrument percentages, so large
  files don't dominate small ones).

```bash
compute_kpi                          # uses today's weekly_delivery + the curated inputs
compute_kpi --date 2026-06-25
compute_kpi --status instrument_status.csv --overrides baseline_overrides.csv
```

### `plot_kpi` — heatmap

Renders a pivot as an instruments × weeks heatmap to `reports/<date>/kpi_heatmap_<metric>.png`.
Blue = full delivery, red = under-delivery, gray = no expected delivery; each cell is
annotated with its whole-percent value.

```bash
plot_kpi --metric technical
plot_kpi --metric retention
plot_kpi --metric retention --date 2026-06-25
```

## Curated inputs

Two hand-maintained files layer on top of the auto baseline. `crawl_baseline` never touches
either, so curation survives a baseline refresh. Edit and re-run `compute_kpi` — no re-crawl.

### `instrument_status.csv` — failed/reduced (the C1 adjustment)

An **exceptions list** — only the failed/reduced instruments; everything else defaults to
full expected.

| column | meaning |
|---|---|
| `refDes` | instrument reference designator |
| `status` | `failed` or `reduced` |
| `effective_date` | `YYYY-MM-DD`; the adjustment applies to weeks on/after this date |
| `reduced_weekly` | for `reduced` only: the new expected per week, human-readable (e.g. `500 MiB`) |

```csv
refDes,status,effective_date,reduced_weekly
CE02SHBP-LJ01D-06-CTDBPN106,failed,2026-04-25,
RS03CCAL-MJ03F-05-BOTPTA301,reduced,2024-09-02,112 MiB
```

`failed` → C1 expected 0 (→ blank KPI, drops out) after the date. `reduced` → C1 expected =
`reduced_weekly` after the date. Before the date, full expected. C3 always uses the full
baseline, so failed/reduced instruments still show their loss under retention.

### `baseline_overrides.csv` — baseline corrections (C1 **and** C3)

Corrects the auto baseline where the observed p95 is contaminated/atypical (e.g. a stuck
sensor that inflated p95 with oversized files). The override replaces `original_expected.csv`
for that instrument in **both** metrics. Because the expected baseline is observation-derived
(p95 of recent weekly delivery), this file is how QA/QC curates it — and since `crawl_baseline`
never writes here, those corrections persist across baseline refreshes.

| column | meaning |
|---|---|
| `refDes` | instrument reference designator |
| `original_p95_weekly` | corrected full-capacity weekly volume, human-readable (e.g. `33 KiB`) |
| `note` | why it was corrected (free text) |

```csv
refDes,original_p95_weekly,note
CE04OSPS-SF01B-4F-PCO2WA102,33 KiB,auto p95 inflated by 2025 stuck-sensor files; set to typical weekly delivery
```

## Automation (GitHub Actions)

- **`.github/workflows/weekly-kpi.yml`** — runs Mondays (and on demand). Re-tabulates
  the rolling recent window from scratch (`crawl_archive` → `compute_kpi` → `plot_kpi`),
  then commits the whole `reports/<date>/` folder. Stateless re-tabulation is deliberate:
  recent weeks **heal as late/backfilled data arrives** (e.g. the hydrophone `addendum/`
  Navy data), which a crawl-once-append would miss. It reads the tracked
  `instrument_status.csv`, `baseline_overrides.csv`, and `original_expected.csv` from the checkout.
  The CLIs write `reports/<date>/` directly, so a local run produces the identical layout.
- **`.github/workflows/refresh-baseline.yml`** — **manual only.** Regenerates the auto
  `original_expected.csv` from a fresh multi-year crawl and commits it. Curated corrections
  live in `baseline_overrides.csv` (applied on top) and are **not** touched, so they survive;
  still kept off the weekly path because it's slow and shifts the denominator — review the diff.

`reports/<date>/` accumulates a browsable weekly history (CSVs + heatmaps), tracked in git.


- **Seismometers / low-frequency hydrophones are not in this archive.** OBS (OBSBBA,
  OBSSPA) and HYDLF deliver to the IRIS/EarthScope DMC and have empty folders here, so they
  get a 0 baseline and a blank KPI (not 0%). Broadband hydrophones (HYDBB), HPIES, and D1000
  *are* in this archive and tallied normally.
- **Some instruments use a non-standard folder name.** The D1000 temperature sensor logs
  under the RAS fluid-sampler port (`RASFLA301_D1000`), not `D1000A301`. Such cases are
  mapped in `PATH_OVERRIDES` in `archive_crawler.py`.
