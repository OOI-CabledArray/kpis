"""C2 Science: per-instrument-week % of zarr data WITHOUT a QARTOD fail flag.

For each instrument with a zarr (the zarrFile column of sitesDictionary), open it
lazily from S3 and, per ISO week, compute the average across parameters of the
fraction of points NOT flagged fail (QARTOD flag 4).

Fast path (default): read the numeric aggregate `<param>_qartod_results`. Because
OOI's climatology test never emits fail (only suspect/3) and only gross_range emits
4, `aggregate != 4` IS the gross-range (climatology-excluded) pass rate -- with no
per-character parsing of the qartod_executed strings.

--decompose: also emit a `pct_climatology` column by parsing the per-test
`qartod_executed` results (slower; for QC investigation of which test drives a low %).

Denominator is data *present* in the zarr (DS-lead definition), so delivery gaps
don't lower C2 -- only QC fails do. Instruments without a zarr are omitted (gray).
Writes reports/<date>/weekly_science.csv.
"""

import argparse
import csv
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from functools import partial

import numpy as np
import s3fs
import xarray as xr
from loguru import logger

from rca_kpis.archive_crawler import SITES_CSV, months_back, session

BUCKET = "ooi-data/"
FAIL = 4              # QARTOD fail flag (numeric, in _qartod_results)
FAIL_CHAR = "4"       # same, as a character in the _qartod_executed string
CLIMATOLOGY = "climatology_test"


def zarr_files():
    """{refDes: zarrFile} for instruments that have a zarr in sitesDictionary."""
    rows = session.get(SITES_CSV, timeout=30).text.splitlines()
    out = {}
    for r in csv.DictReader(rows):
        zf = r["zarrFile"].strip().strip('"')
        if zf and zf.lower() != "none":
            out[r["refDes"]] = zf
    return out


def _add_week(sub):
    monday = (sub.time - sub.time.dt.weekday * np.timedelta64(1, "D")).dt.floor("D")
    return sub.assign_coords(week=monday)


def _weekly(boolean):
    """Weekly fraction True, reduced to one value per week (avg over any extra dim)."""
    wk = boolean.groupby("week").mean()
    if wk.ndim > 1:
        wk = wk.mean(dim=[d for d in wk.dims if d != "week"])
    return wk


def _fast(ds, start, end):
    """pct_science from the numeric aggregate: agg != 4 == gross-range pass (no strings)."""
    qr = [v for v in ds.data_vars if v.endswith("_qartod_results")]
    if not qr:
        return None
    sub = _add_week(ds[qr].sel(time=slice(start, end)))
    if sub.sizes.get("time", 0) == 0:
        return {}
    parts = [_weekly(sub[v] != FAIL) for v in qr]
    c2 = (xr.concat(parts, "param").mean("param") * 100).compute()
    return {str(w)[:10]: (round(float(v), 1), None) for w, v in zip(c2.week.values, c2.values)}


def _decompose(ds, start, end):
    """gross-range pct_science + climatology pct, from per-test qartod_executed (slower)."""
    exes = [v for v in ds.data_vars if v.endswith("_qartod_executed")]
    if not exes:
        return None
    sub = _add_week(ds[exes].sel(time=slice(start, end)))
    if sub.sizes.get("time", 0) == 0:
        return {}
    sci_parts, clim_parts = [], []
    for v in exes:
        ex = sub[v]
        tests = [t.strip() for t in ex.attrs.get("tests_executed", "").replace(" ", "").split(",")]
        chars = {t: ex.str[i] for i, t in enumerate(tests) if t}
        non_clim = [chars[t] == FAIL_CHAR for t in chars if t != CLIMATOLOGY]
        if non_clim:
            fail = non_clim[0]
            for b in non_clim[1:]:
                fail = fail | b
            sci_parts.append(_weekly(~fail))
        if CLIMATOLOGY in chars:
            clim_parts.append(_weekly(chars[CLIMATOLOGY] != FAIL_CHAR))
    if not sci_parts:
        return {}
    out = {"science": xr.concat(sci_parts, "param").mean("param") * 100}
    if clim_parts:
        out["clim"] = xr.concat(clim_parts, "param").mean("param") * 100
    res = xr.Dataset(out).compute()
    weekly = {}
    for i, w in enumerate(res.week.values):
        clim = round(float(res["clim"].values[i]), 1) if "clim" in res else None
        weekly[str(w)[:10]] = (round(float(res["science"].values[i]), 1), clim)
    return weekly


def science_instrument(item, start, end, decompose=False):
    """Per-ISO-week (pct_science, pct_climatology|None) for one instrument."""
    ref_des, zarr_file = item
    t0 = time.perf_counter()
    try:
        fs = s3fs.S3FileSystem(anon=True)
        ds = xr.open_zarr(fs.get_mapper(BUCKET + zarr_file), consolidated=True)
        weekly = _decompose(ds, start, end) if decompose else _fast(ds, start, end)
        if weekly is None:
            logger.warning(f"{ref_des}: no QARTOD vars")
            return ref_des, {}
        if weekly:
            mean_sci = np.mean([s for s, _ in weekly.values()])
            logger.info(f"{ref_des}: {len(weekly)} wks, sci~{mean_sci:.0f}% [{time.perf_counter() - t0:.0f}s]")
        return ref_des, weekly
    except Exception as e:  # missing/odd zarr -> no C2 (gray), don't kill the run
        logger.warning(f"{ref_des}: C2 failed ({type(e).__name__}: {e})")
        return ref_des, {}


def main(start=None, end=None, rundate=None, decompose=False):
    files = zarr_files()
    logger.info(f"C2: scanning QARTOD in {len(files)} zarr datasets over {start}..{end}"
                f"{' (decompose)' if decompose else ''}")
    fn = partial(science_instrument, start=start, end=end, decompose=decompose)
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(fn, files.items()))
    n = sum(bool(w) for _, w in results)
    logger.info(f"scanned {len(files)} zarr in {time.perf_counter() - t0:.0f}s ({n} with QARTOD)")

    rd_dir = f"reports/{rundate}"
    os.makedirs(rd_dir, exist_ok=True)
    out = f"{rd_dir}/weekly_science.csv"
    header = ["refDes", "week", "pct_science"] + (["pct_climatology"] if decompose else [])
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for ref_des, weekly in sorted(results):
            for wk, (sci, clim) in sorted(weekly.items()):
                w.writerow([ref_des, wk, sci] + ([("" if clim is None else clim)] if decompose else []))
    logger.success(f"wrote {out} ({n} instruments with QARTOD)")


def cli():
    today = date.today()
    p = argparse.ArgumentParser(description="C2 science: QARTOD pass-rate per instrument-week.")
    p.add_argument("--start", default=str(months_back(today, 3)), help="YYYY-MM-DD (default: 3 months ago)")
    p.add_argument("--end", default=str(today), help="YYYY-MM-DD (default: today)")
    p.add_argument("--date", default=str(today), help="run date tag (matches crawl_archive --date)")
    p.add_argument("--decompose", action="store_true",
                   help="also emit pct_climatology (slower: parses qartod_executed per-test)")
    a = p.parse_args()
    main(start=a.start, end=a.end, rundate=a.date, decompose=a.decompose)


if __name__ == "__main__":
    cli()
