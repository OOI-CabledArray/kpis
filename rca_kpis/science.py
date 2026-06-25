"""C2 Science: per-instrument-week % of zarr data WITHOUT a QARTOD fail flag.

For each instrument that has a zarr (the zarrFile column of sitesDictionary), open
it lazily from S3, read the aggregate <param>_qartod_results variables, slice to the
reporting window, and per ISO week compute the average across parameters of the
fraction of points NOT flagged fail (QARTOD flag 4). Denominator is data *present*
in the zarr (DS-lead definition), so delivery gaps don't lower C2 -- only QC fails do.

Instruments without a zarr are omitted here and render gray (NA) downstream.
Writes reports/<date>/weekly_science.csv (refDes, week, pct_science).
"""

import argparse
import csv
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from functools import partial

import numpy as np
import s3fs
import xarray as xr
from loguru import logger

from rca_kpis.archive_crawler import SITES_CSV, months_back, session

BUCKET = "ooi-data/"
FAIL = 4  # QARTOD flag values: 1 pass, 2 not-evaluated, 3 suspect, 4 fail, 9 missing


def zarr_files():
    """{refDes: zarrFile} for instruments that have a zarr in sitesDictionary."""
    rows = session.get(SITES_CSV, timeout=30).text.splitlines()
    out = {}
    for r in csv.DictReader(rows):
        zf = r["zarrFile"].strip().strip('"')
        if zf and zf.lower() != "none":
            out[r["refDes"]] = zf
    return out


def science_instrument(item, start, end):
    """Per-ISO-week C2 % for one instrument: avg over params of % points not fail-flagged."""
    ref_des, zarr_file = item
    try:
        fs = s3fs.S3FileSystem(anon=True)
        ds = xr.open_zarr(fs.get_mapper(BUCKET + zarr_file), consolidated=True)
        qr = [v for v in ds.data_vars if v.endswith("_qartod_results")]
        if not qr:
            logger.warning(f"{ref_des}: no *_qartod_results vars")
            return ref_des, {}
        sub = ds[qr].sel(time=slice(start, end))  # window first -- lazy, loads only this slice
        if sub.sizes.get("time", 0) == 0:
            return ref_des, {}
        monday = (sub.time - sub.time.dt.weekday * np.timedelta64(1, "D")).dt.floor("D")
        sub = sub.assign_coords(week=monday)
        # per parameter: weekly fraction of points not failed, reduced to one value per week
        # (a param may carry an extra dim e.g. wavelength/bin -- average over it too)
        per_param = []
        for v in qr:
            wk = (sub[v] != FAIL).groupby("week").mean()
            if wk.ndim > 1:
                wk = wk.mean(dim=[d for d in wk.dims if d != "week"])
            per_param.append(wk)
        c2 = (xr.concat(per_param, dim="param").mean("param") * 100).compute()  # avg across params
        weekly = {str(w)[:10]: round(float(v), 1) for w, v in zip(c2.week.values, c2.values)}
        logger.info(f"{ref_des}: {len(weekly)} weeks (qartod)")
        return ref_des, weekly
    except Exception as e:  # missing/odd zarr -> no C2 (gray downstream), don't kill the run
        logger.warning(f"{ref_des}: C2 failed ({type(e).__name__}: {e})")
        return ref_des, {}


def main(start=None, end=None, rundate=None):
    files = zarr_files()
    logger.info(f"C2: scanning QARTOD in {len(files)} zarr datasets over {start}..{end}")
    fn = partial(science_instrument, start=start, end=end)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(fn, files.items()))

    rd_dir = f"reports/{rundate}"
    os.makedirs(rd_dir, exist_ok=True)
    out = f"{rd_dir}/weekly_science.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["refDes", "week", "pct_science"])
        for ref_des, weekly in sorted(results):
            for wk, v in sorted(weekly.items()):
                w.writerow([ref_des, wk, v])
    logger.success(f"wrote {out} ({sum(bool(w) for _, w in results)} instruments with zarr)")


def cli():
    today = date.today()
    p = argparse.ArgumentParser(description="C2 science: QARTOD pass-rate per instrument-week.")
    p.add_argument("--start", default=str(months_back(today, 3)), help="YYYY-MM-DD (default: 3 months ago)")
    p.add_argument("--end", default=str(today), help="YYYY-MM-DD (default: today)")
    p.add_argument("--date", default=str(today), help="run date tag (matches crawl_archive --date)")
    a = p.parse_args()
    main(start=a.start, end=a.end, rundate=a.date)


if __name__ == "__main__":
    cli()
