# KPI investigation notes

Snapshot: run 2026-06-25, baseline window 2024-06..2026-06, weeks 2026-03-02..2026-06-15.

Many instruments read low because their auto `original_p95_weekly_bytes` baseline was
inflated by an earlier high period (anomaly, commissioning, pre-reduction sampling). Fix in
`baseline_overrides.csv` (correct the baseline), `instrument_status.csv` (failed/reduced), or
leave it (real loss). All items below are resolved unless marked **open**.

## Baseline overrides applied (→ Sept 2025 avg weekly delivery)

- **PCO2W + PHSEN** (15) — auto p95 anomaly-inflated (e.g. PCO2WA102 0.1%→94%). Now ~92–100%.
- **NUTNR** (3) — now ~66–99%. **open:** NUTNRA101/102 sit below Sept; if intentional, add a
  `reduced` row. APL sometimes doesn't restart NUTNR after profiler failures → intermittent gaps.
- **PARAD** (3) — now ~98–100%.
- **CAMDS** (6) — bursty; Sept was a low month for some, so several weeks read `100+` (capped).
  **open:** revisit the reference month if a cleaner ~100% is wanted.
- **BOTPT** (4) — NANO sampling reduced 20→10→1 Hz in 2024 (intentional, network-fault fix).
  Benchmark set to Sept 2025 (301/303/304=112 MiB, 302=714 MiB) → C1 & C3 ~100%, not a loss.

## instrument_status.csv

- **failed**: CTDBPN106, OPTAAD106, CAMDSB107, HYDBBA105, PHSENA106, ADCPTE101, HPIESA301.
- **reduced**: CAMHDA301 (HD camera) → 831.3 GiB/wk.

## Excluded / greyed

Per-metric grey-outs live in `config/exclusions.csv` (`refDes,metrics,reason`).
- **Broadband hydrophones (HYDBBA 102/103/105/106/302/303)** — `all` metrics; Navy diversion
  makes the delivery score invalid.
- **PARAD (101/102/301)** — `science` only; QARTOD gross-range test is mis-set in prod (good
  data, bad test), so C2 is greyed while C1/C3 stay (they deliver ~100%).
- Seismometers / low-freq hydrophones (OBS, OBSSP, HYDLF) → deliver to IRIS, not this archive
  (auto 0 baseline → gray; no config needed). HPIES and D1000 ARE tallied (D1000 via RASFLA301_D1000).

## C2 (science / QARTOD)

% of present zarr data without a fail flag (4), gross-range only (climatology excluded), per
week. 59 instruments have QARTOD; overall ~92%.

- **PAR (PARADA101/102/301):** greyed from C2 (config/exclusions.csv) — gross-range fails 100%
  of points at every site (climatology innocent), i.e. good data / bad test. **open / QC team:**
  fix the mis-set PAR gross-range bound in prod, then remove the exclusion.
- Lower readers to glance at: PCO2WA101 (~52%), PHSENA108 (~73%), FLORTD104/301 (~73–77%).
