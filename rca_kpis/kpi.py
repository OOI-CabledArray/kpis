"""Compute the delivery KPI: delivered vs. expected, per instrument-week.

Both NSF metrics share one baseline -- original_expected.csv (auto, from
crawl_baseline) with baseline_overrides.csv applied on top (curated corrections
that survive a baseline refresh) -- and differ only in the denominator:

- C1 Technical (pct_technical) -- full capacity, shrunk for failed/reduced
  instruments after their effective date (instrument_status.csv).
- C3 Retention (pct_retention) -- always the full original capacity.

Healthy instruments get C1 == C3; they diverge only for failed/reduced ones.
Expected == 0 (failed, or not in this archive) yields a blank KPI, not 0%.

Outputs:
- kpi_<date>.csv          one row per instrument-week (condensed, both metrics)
- kpi_pivot_<metric>_<date>.csv   instruments x weeks grid of whole-percent
                                  values, plus an unweighted mean-of-percents row.
"""

import argparse
import csv
import os
from datetime import date
from statistics import mean

from humanfriendly import format_size, parse_size
from loguru import logger

MEAN_LABEL = "ALL_INSTRUMENTS_MEAN"


def load_original(path):
    """Per-instrument full-capacity p95 WEEKLY delivery (bytes) from crawl_baseline."""
    if not os.path.exists(path):
        logger.error(f"{path} missing -- run crawl_baseline first")
        return {}
    with open(path) as f:
        return {r["refDes"]: int(r["original_p95_weekly_bytes"]) for r in csv.DictReader(f)}


def load_status(path):
    """Failed/reduced instruments: {refDes: (status, effective_date, reduced_weekly_bytes)}."""
    if not os.path.exists(path):
        logger.warning(f"{path} missing -- no failed/reduced instruments applied (C1 == C3)")
        return {}
    status = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            eff = date.fromisoformat(r["effective_date"].strip())
            reduced = parse_size(r["reduced_weekly"], binary=True) if r.get("reduced_weekly", "").strip() else 0
            status[r["refDes"].strip()] = (r["status"].strip().lower(), eff, reduced)
    return status


def load_overrides(path):
    """Curated baseline corrections {refDes: bytes} applied on top of original_expected.csv.

    Hand-maintained; crawl_baseline never touches it, so corrections survive a refresh.
    """
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return {r["refDes"].strip(): parse_size(r["original_p95_weekly"], binary=True)
                for r in csv.DictReader(f) if r.get("original_p95_weekly", "").strip()}


def load_science(path):
    """C2 from crawl_science (optional): {(refDes, week): (pct_science, pct_climatology)}."""
    if not os.path.exists(path):
        logger.warning(f"{path} missing -- run crawl_science for C2; pct_science will be blank")
        return {}
    with open(path) as f:  # pct_climatology only present with `crawl_science --decompose`
        return {(r["refDes"], r["week"]):
                (float(r["pct_science"]), float(r["pct_climatology"]) if r.get("pct_climatology") else None)
                for r in csv.DictReader(f)}


def week_start(week):  # week label is already the Monday date (YYYY-MM-DD)
    return date.fromisoformat(week)


def group_key(ref_des):
    """Instrument code after the last dash (e.g. CTDBPN106) -- sorting on it
    clusters alike instruments (BOTPTA*, CTDBP*, HYDBB*, ...) together."""
    return ref_des.rsplit("-", 1)[1]


def pct(delivered, expected):
    return round(100 * delivered / expected, 1) if expected > 0 else None  # 0 expected -> NA


def write_pivot(records, instruments, weeks, key, out):
    """instruments x weeks grid of whole-percent `key`, capped at 100 (over-delivery
    shown as '100+'), plus an unweighted mean row computed on the capped values."""
    grid = {(r["refDes"], r["week"]): r[key] for r in records}

    def cell(v):
        if v is None:
            return ""
        return "100+" if v > 100 else round(v)

    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["refDes", *weeks])
        for inst in instruments:
            w.writerow([inst, *(cell(grid[(inst, wk)]) for wk in weeks)])
        avg = []
        for wk in weeks:  # unweighted mean of the capped percentages (file size ignored)
            vals = [min(grid[(i, wk)], 100) for i in instruments if grid[(i, wk)] is not None]
            avg.append(round(mean(vals)) if vals else "")
        w.writerow([MEAN_LABEL, *avg])
    logger.success(f"wrote {out} ({len(instruments)} instruments x {len(weeks)} weeks)")


def main(rundate, original="config/original_expected.csv", status_path="config/instrument_status.csv",
         overrides="config/baseline_overrides.csv"):
    rd_dir = f"reports/{rundate}"
    orig = load_original(original)
    orig.update(load_overrides(overrides))  # curated corrections win over the auto baseline
    status = load_status(status_path)
    science = load_science(f"{rd_dir}/weekly_science.csv")  # C2 (optional)
    with open(f"{rd_dir}/weekly_delivery.csv") as f:
        rows = list(csv.DictReader(f))

    records = []
    for r in rows:
        rd, wk, d = r["refDes"], r["week"], int(r["delivered_bytes"])
        c3 = c1 = orig.get(rd, 0)  # full intended weekly capacity (p95 of weekly delivery)
        if rd in status:
            state, eff, reduced = status[rd]
            if week_start(wk) >= eff:
                c1 = 0 if state == "failed" else reduced
        sci, clim = science.get((rd, wk), (None, None))  # C2: blank where no zarr (gray)
        records.append({
            "refDes": rd, "week": wk,
            "delivered_human": r["delivered_human"],
            "c1_expected_human": format_size(c1, binary=True), "pct_technical": pct(d, c1),
            "c3_expected_human": format_size(c3, binary=True), "pct_retention": pct(d, c3),
            "pct_science": sci, "pct_climatology": clim,  # C2 (gross-range) + decomposition
        })

    records.sort(key=lambda r: (group_key(r["refDes"]), r["refDes"], r["week"]))
    instruments = sorted({r["refDes"] for r in rows}, key=lambda rd: (group_key(rd), rd))
    weeks = list(dict.fromkeys(r["week"] for r in rows))  # chronological as crawled

    out = f"{rd_dir}/kpi.csv"
    cols = ["refDes", "week", "delivered_human",
            "c1_expected_human", "pct_technical", "c3_expected_human", "pct_retention",
            "pct_science", "pct_climatology"]
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(records)
    logger.success(f"wrote {out} ({len(records)} instrument-weeks)")

    write_pivot(records, instruments, weeks, "pct_technical", f"{rd_dir}/kpi_pivot_technical.csv")
    write_pivot(records, instruments, weeks, "pct_retention", f"{rd_dir}/kpi_pivot_retention.csv")
    write_pivot(records, instruments, weeks, "pct_science", f"{rd_dir}/kpi_pivot_science.csv")


def cli():
    p = argparse.ArgumentParser(description="Compute delivery KPI (C1/C3) per instrument-week.")
    p.add_argument("--date", default=str(date.today()), help="run date tag (matches crawl_archive --date)")
    p.add_argument("--original", default="config/original_expected.csv", help="auto baseline from crawl_baseline")
    p.add_argument("--overrides", default="config/baseline_overrides.csv", help="curated baseline corrections")
    p.add_argument("--status", default="config/instrument_status.csv", help="failed/reduced instrument list")
    a = p.parse_args()
    main(a.date, a.original, a.status, a.overrides)


if __name__ == "__main__":
    cli()
