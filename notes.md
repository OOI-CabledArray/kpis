# KPI investigation notes

Instruments flagged for follow-up. These read **low but are NOT failed** — their
`original_p95_weekly_bytes` baseline (the C1/C3 denominator) looks higher than
what they typically deliver, so the % is likely understated by a bad baseline
rather than a real loss. Resolve each by either:

- **correcting the baseline** via a row in `baseline_overrides.csv` (refDes,
  original_p95_weekly, note) if the high value came from a malfunction/anomaly, **or**
- **adding a `reduced` row** to `instrument_status.csv` if it's a genuine sampling
  reduction (then C1 reads ~100% and C3 keeps showing the loss), **or**
- leaving it if the baseline is real capacity and the instrument is genuinely
  under-delivering (a true loss to report).

Snapshot: run 2026-06-25, baseline window 2024-06..2026-06, report weeks
2026-03-02..2026-06-15. `ratio` = baseline ÷ typical (median) weekly delivered.

## Group A — almost certainly anomaly-contaminated baseline (ratio ≫ 10×)

| refDes | baseline/wk | typical/wk | ratio | C3 % | note |
|---|---|---|---|---|---|
| CE04OSPS-SF01B-4F-PCO2WA102 | 28.05 MiB | 32.4 KiB | ~886× | 0.1 | known stuck-sensor period (the old 129 MB/day files) inflated p95 |
| RS01SBPS-SF01A-2D-PHSENA101 | 11.47 MiB | 216.5 KiB | ~54× | 1.8 | same signature — a multi-week burst of oversized files |

→ **DONE:** the entire PCO2W and PHSEN classes (15 instruments) are overridden in
`baseline_overrides.csv` with their **Sept 2025 average weekly delivery** (PCO2W ~32–68 KiB,
PHSEN ~140–225 KiB). After override they read ~92–100% (PCO2WA102 went 0.1% → 94%). A few
low-min weeks are real short outages.

## Group B — moderate inflation, cause unclear (ratio ~2–8×)

| refDes | baseline/wk | typical/wk | ratio | C3 % |
|---|---|---|---|---|
| RS01SBPS-SF01A-4A-NUTNRA101 | 250.51 MiB | 30.5 MiB | ~8.2× | 15.0 |
| CE04OSPS-SF01B-4A-NUTNRA102 | 153.58 MiB | 38.5 MiB | ~4.0× | 25.4 |
| RS03AXPS-SF03A-4A-NUTNRA301 | 105.75 MiB | 60.3 MiB | ~1.8× | 55.6 |
| RS01SBPS-SF01A-3C-PARADA101 | 287 MiB | 70 MiB | ~4.1× | 24.4 |
| RS03AXPS-SF03A-3C-PARADA301 | 280 MiB | 70 MiB | ~4.0× | 25.0 |
| RS03AXPS-SF03A-4F-PCO2WA301 | 68.1 KiB | 31.9 KiB | ~2.1× | 46.6 |
| RS01SBPS-SF01A-4F-PCO2WA101 | 67.61 KiB | 32.2 KiB | ~2.1× | 47.6 |

→ **DONE:** all NUTNR + PARAD baselines overridden in `baseline_overrides.csv` with their
**Sept 2025 average weekly delivery** (NUTNR 64–80 MiB; PARAD ~70 MiB). The auto p95 was
inflated by an earlier high period. After override: PARAD ~98–100%, NUTNR ~66–99%. NUTNRA101/102
sit a bit below Sept levels (a mild real shortfall) — if that dip is an *expected* sampling
change, add a `reduced` row to `instrument_status.csv` so C1 reads ~100% while C3 keeps the loss.

## Group C — cameras: high week-to-week variance (ratio ~2–6×)

| refDes | baseline/wk | typical/wk | ratio | C3 % |
|---|---|---|---|---|
| RS03ASHS-PN03B-06-CAMHDA301 | 4.89 TiB | 842.52 GiB | ~5.9× | 16.5 |
| RS01SUM2-MJ01B-05-CAMDSB103 | 48.86 GiB | 7.29 GiB | ~6.7× | 14.9 |
| RS03INT1-MJ03C-05-CAMDSB303 | 30.02 GiB | 7.05 GiB | ~4.3× | 23.6 |
| RS03AXPS-PC03A-07-CAMDSC302 | 48.53 GiB | 21.66 GiB | ~2.2× | 44.6 |
| CE04OSBP-LV01C-06-CAMDSB106 | 21.62 GiB | 9.31 GiB | ~2.3× | 43.0 |
| RS01SBPS-PC01A-07-CAMDSC102 | 35.73 GiB | 20.67 GiB | ~1.7× | 54.2 |

→ **DONE:** all CAMDS baselines overridden in `baseline_overrides.csv` with their
**Sept 2025 average weekly delivery**. Cameras deliver in bursts so p95-weekly over-stated the
typical week. After override they read mixed (some weeks > Sept, capped to `100+` gold; some
below) — Sept was a low month for several cameras, so revisit the reference basis if a cleaner
~100% is wanted. Pivots cap at 100; over-delivery flagged gold in the heatmap. (CAMHDA301, the
HD camera, was NOT overridden here — still on its auto p95; revisit separately if needed.)

## Already handled (in instrument_status.csv) — for reference

- **failed** (C1 → NA, C3 shows loss): CTDBPN106, OPTAAD106, CAMDSB107, HYDBBA105,
  PHSENA106, ADCPTE101, HPIESA301.
- **reduced** to 112 MiB/wk: BOTPTA301 & BOTPTA303 (after 2024-09-02),
  BOTPTA304 (after 2024-06-24).

## Not flagged here

- Seismic/geodetic (OBS, OBSSP, HYDLF, HPIES, D1000) deliver to IRIS, not this
  archive → 0 baseline → blank KPI (correctly excluded, not a problem to fix).
