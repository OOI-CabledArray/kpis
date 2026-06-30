# Notes on decision-making for KPI tabulation

## Baseline overrides applied (→ Sept 2025 avg weekly delivery)

- **PCO2W + PHSEN** (15) — auto p95 anomaly-inflated (e.g. PCO2WA102 0.1%→94%). Now ~92–100%.
- **NUTNR** (3) — now ~66–99%. **open:** NUTNRA101/102 sit below Sept; if intentional, add a
  `reduced` row. APL sometimes doesn't restart NUTNR after profiler failures → intermittent gaps.
- **PARAD** (3) — now ~98–100%.
- **CAMDS** (6) — bursty; Sept was a low month for some, so several weeks read `100+` (capped).
  100+ is expected for bursty instruments; a longer reference window would reduce capping artifacts if desired.
- **BOTPT** (4) — NANO sampling reduced 20→10→1 Hz in 2024 (intentional, network-fault fix).
  Benchmark set to Sept 2025 (301/303/304=112 MiB, 302=714 MiB) → C1 & C3 ~100%, not a loss.

## instrument_status.csv

- **failed**: CTDBPN106, OPTAAD106, CAMDSB107, HYDBBA105, PHSENA106, ADCPTE101, HPIESA301.
- **reduced**: CAMHDA301 (HD camera) → 831.3 GiB/wk.

## Excluded / greyed

Per-metric overrides live in `config/instrument_overrides.csv` (`refDes,pct_technical,pct_retention,pct_science,note`).
- **Broadband hydrophones (HYDBBA 102/103/105/106/302/303)** — C1/C3 scored 100%, C2 greyed; Navy diversion
  makes the archive delivery score invalid.
- **PARAD (101/102/301)** — `science` only greyed; QARTOD gross-range test is mis-set in prod (good
  data, bad test), so C2 is greyed while C1/C3 stay (they deliver ~100%).
- Seismometers / low-freq hydrophones (OBS, OBSSP, HYDLF) → deliver to IRIS, not this archive;
  C1/C3 scored 100%, C2 greyed. HPIES and D1000 ARE tallied (D1000 via RASFLA301_D1000).

## C2 (science / QARTOD)

% of present zarr data without a fail flag (4), gross-range only (climatology excluded), per
week. 59 instruments have QARTOD; overall ~92%.

- **PAR (PARADA101/102/301):** greyed from C2 (config/instrument_overrides.csv) — gross-range fails 100%
  of points at every site (climatology innocent), i.e. good data / bad test. **open / QC team:**
  fix the mis-set PAR gross-range bound in prod, then remove the exclusion.
- Lower readers to glance at: PCO2WA101 (~52%), PHSENA108 (~73%), FLORTD104/301 (~73–77%).
