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
crawl_archive      # the reporting window                -> weekly_delivery_<date>.csv
compute_kpi        # delivered vs expected               -> kpi_<date>.csv + two pivots
plot_kpi --metric technical    # heatmap -> viz/kpi_heatmap_technical_<date>.png
plot_kpi --metric retention    # heatmap -> viz/kpi_heatmap_retention_<date>.png
```

All run-window outputs are tagged with the run date (default: today) so re-runs don't
overwrite earlier results. Pass `--date` to chain steps for the same run on a later day.
The two inputs — `original_expected.csv` and `adjustments.csv` — are **not** dated; they
persist and are hand-editable.

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
listing, and writes `weekly_delivery_<date>.csv`: delivered bytes per instrument × complete
week (Mon-Sun, labeled by the Monday date; partial edge weeks are excluded).

```bash
crawl_archive                                       # default: last 3 months
crawl_archive --start 2026-03-01 --end 2026-06-01   # explicit window
crawl_archive --date 2026-06-25                     # override the output date tag
```

### `compute_kpi` — delivered vs expected (C1 + C3)

Joins `weekly_delivery_<date>.csv` against `original_expected.csv` and `adjustments.csv`,
writing one detailed CSV plus two pivots:

- `kpi_<date>.csv` — one row per instrument-week: `delivered_human`, then C1
  (`c1_expected_human`, `pct_technical`) and C3 (`c3_expected_human`, `pct_retention`).
- `kpi_pivot_technical_<date>.csv` and `kpi_pivot_retention_<date>.csv` — instruments × weeks
  grids of **whole-percent** values, with a final `ALL_INSTRUMENTS_MEAN` row (the unweighted
  mean of per-instrument percentages, so large files don't dominate small ones).

```bash
compute_kpi                          # uses today's weekly_delivery + the two inputs
compute_kpi --date 2026-06-25
compute_kpi --adjustments adjustments.csv --original original_expected.csv
```

### `plot_kpi` — heatmap

Renders a pivot as an instruments × weeks heatmap to `viz/kpi_heatmap_<metric>_<date>.png`.
Blue = full delivery, red = under-delivery, gray = no expected delivery; each cell is
annotated with its whole-percent value.

```bash
plot_kpi --metric technical
plot_kpi --metric retention
plot_kpi --metric retention --date 2026-06-25
```

## The adjustments config (`adjustments.csv`)

An **exceptions list** — only the failed/reduced instruments; everything else defaults to
full expected. Columns:

| column | meaning |
|---|---|
| `refDes` | instrument reference designator |
| `status` | `failed` or `reduced` |
| `effective_date` | `YYYY-MM-DD`; the adjustment applies to weeks on/after this date |
| `reduced_weekly` | for `reduced` only: the new expected per week, human-readable (e.g. `500 MiB`) |

```csv
refDes,status,effective_date,reduced_weekly
CE02SHBP-LJ01D-06-CTDBPN106,failed,2026-04-25,
RS03CCAL-MJ03F-05-BOTPTA301,reduced,2025-08-01,500 MiB
```

`failed` → C1 expected 0 (→ blank KPI, drops out) after the date. `reduced` → C1 expected =
`reduced_weekly` after the date. Before the date, full expected. C3 always uses the full
baseline, so failed/reduced instruments still show their loss under retention. Edit the file
and re-run `compute_kpi` — no re-crawl needed.

## Automation (GitHub Actions)

- **`.github/workflows/weekly-kpi.yml`** — runs Mondays (and on demand). Re-tabulates
  the rolling recent window from scratch (`crawl_archive` → `compute_kpi` → `plot_kpi`),
  then commits the pivots + heatmaps to `reports/<date>/`. Stateless re-tabulation is
  deliberate: recent weeks **heal as late/backfilled data arrives** (e.g. the hydrophone
  `addendum/` Navy data), which a crawl-once-append would miss. It reads the tracked
  `adjustments.csv` + `original_expected.csv` straight from the checkout.
- **`.github/workflows/refresh-baseline.yml`** — **manual only.** Regenerates
  `original_expected.csv` from a fresh multi-year crawl and commits it. It **overwrites
  hand-corrected baselines** (see `notes.md`), so run it deliberately and re-apply
  corrections afterward. Kept off the weekly path because it's slow.

`reports/<date>/` accumulates a browsable weekly history; root-level dated artifacts stay
git-ignored (the ignore rules are anchored to root so the `reports/` copies are tracked).


- **Seismic / geodetic instruments are not in this archive.** OBS, OBSSP, HYDLF, HPIES,
  D1000 deliver to the IRIS/EarthScope DMC and have empty folders here, so they get a 0
  baseline and a blank KPI (not 0%). Broadband hydrophones (HYDBB) *are* in this archive.
