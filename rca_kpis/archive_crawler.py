"""Crawl the OOI raw data archive and tally delivered file size per instrument.

For each reference designator in sitesDictionary.csv, walk the Apache autoindex
tree (subsite/node/instrument/year/month[/day]/) over a chosen date window,
summing file sizes bucketed into days via the date embedded in each filename.

Outputs a per-instrument summary including the 95th-percentile daily delivery
(a robust "healthy peak" that ignores anomalous days), extrapolated to an
expected monthly volume -- the seed for the human-editable expected config.
"""

import argparse
import csv
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from functools import partial
from urllib.parse import urljoin

import numpy as np
import requests
from bs4 import BeautifulSoup
from humanfriendly import format_size, parse_size
from loguru import logger

ARCHIVE = "https://rawdata.oceanobservatories.org/files/"
SITES_CSV = (
    "https://raw.githubusercontent.com/OOI-CabledArray/rca-data-tools/main/"
    "rca_data_tools/qaqc/params/sitesDictionary.csv"
)
# data date in filename: compact (20240101T) or dashed (2017-01-03T)
DAY = re.compile(r"(\d{4})-?(\d{2})-?(\d{2})T")
SIZE = re.compile(r"\s([\d.]+[KMGT]?)\s*$")  # trailing size token in autoindex row

session = requests.Session()


def listing(url):
    """Return (subdir_hrefs, [(filename, bytes), ...]) for an autoindex page.

    The archive uses a <pre>-style FancyIndex: each <a> is followed by inline
    text ending in the human-readable size (e.g. "... 2026-06-01 23:29  4.5K").
    """
    soup = BeautifulSoup(session.get(url, timeout=30).text, "html.parser")
    dirs, files = [], []
    for link in soup.find_all("a"):
        href = link.get("href", "")
        if href.startswith(("?", "/")):  # sort links and parent dir
            continue
        if href.endswith("/"):
            dirs.append(href)
            continue
        tail = link.next_sibling or ""
        m = SIZE.search(str(tail))
        if m:
            files.append((href, parse_size(m.group(1), binary=True)))
    return dirs, files


# Instruments whose archive folder name doesn't match their refDes instrument code.
# e.g. the D1000 temperature sensor logs under the RAS fluid-sampler port folder.
PATH_OVERRIDES = {
    "RS03INT1-MJ03C-07-D1000A301": "RS03INT1/MJ03C/RASFLA301_D1000/",
}


def base_url(ref_des):
    if ref_des in PATH_OVERRIDES:
        return urljoin(ARCHIVE, PATH_OVERRIDES[ref_des])
    subsite, node, _port, instr = ref_des.split("-")
    return urljoin(ARCHIVE, f"{subsite}/{node}/{instr}/")


def walk(url, daily, start, end):
    """Recurse below a month folder, summing in-range files by day (YYYYMMDD).

    Handles both layouts: files directly in the month folder, and files nested
    one level deeper in day folders (e.g. hydrophones, cameras).
    """
    dirs, files = listing(url)
    for name, nbytes in files:
        m = DAY.search(name)
        if m and start <= (day := "".join(m.groups())) <= end:
            daily[day] += nbytes
    for d in dirs:
        walk(urljoin(url, d), daily, start, end)


def crawl_instrument(ref_des, start, end):
    """Walk one instrument over [start, end]; return daily byte totals.

    start/end are YYYYMMDD strings. Years and months outside the window are
    pruned so we never descend into irrelevant (and large) subtrees.
    """
    t0 = time.perf_counter()
    base = base_url(ref_des)
    daily = defaultdict(int)
    try:
        years, _ = listing(base)
    except requests.RequestException:
        logger.warning(f"{ref_des}: no archive folder at {base}")
        return ref_des, daily
    for year in years:
        y = year.strip("/")
        if not (start[:4] <= y <= end[:4]):
            continue
        months, _ = listing(urljoin(base, year))
        for month in months:
            if start[:6] <= y + month.strip("/") <= end[:6]:
                walk(urljoin(base, year + month), daily, start, end)
    logger.info(f"{ref_des}: {len(daily)} days, {sum(daily.values()):,} bytes "
                f"[{time.perf_counter() - t0:.1f}s]")
    return ref_des, daily


def fetch_ref_des():
    rows = session.get(SITES_CSV, timeout=30).text.splitlines()
    return [r["refDes"] for r in csv.DictReader(rows)]


def months_back(d, n):
    """First of the month n calendar months before date d."""
    m = d.month - n
    return d.replace(year=d.year + (m - 1) // 12, month=(m - 1) % 12 + 1, day=1)


def _iso(yyyymmdd):
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"


def week_of(yyyymmdd):
    """Week-start (Monday) date YYYY-MM-DD for the Mon-Sun week containing a day."""
    d = date.fromisoformat(_iso(yyyymmdd))
    return (d - timedelta(days=d.weekday())).isoformat()


def full_weeks(start, end):
    """Week-start (Monday) dates YYYY-MM-DD for each Mon-Sun week fully inside [start, end].

    Partial edge weeks are excluded -- KPIs report only complete weeks.
    """
    s, e = date.fromisoformat(_iso(start)), date.fromisoformat(_iso(end))
    mon = s + timedelta(days=(7 - s.weekday()) % 7)  # first Monday on/after start
    out = []
    while mon + timedelta(days=6) <= e:
        out.append(mon.isoformat())
        mon += timedelta(days=7)
    return out


def write_weekly(results, weeks, out):
    """Per-instrument x complete-ISO-week delivered bytes (the delivered side of the KPI)."""
    weekset = set(weeks)
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["refDes", "week", "delivered_bytes", "delivered_human"])
        for ref_des, daily in sorted(results):
            by_week = defaultdict(int)
            for day, nbytes in daily.items():
                wk = week_of(day)
                if wk in weekset:
                    by_week[wk] += nbytes
            for wk in weeks:
                d = by_week.get(wk, 0)
                w.writerow([ref_des, wk, d, format_size(d, binary=True)])
    logger.success(f"wrote {out} ({len(results)} instruments x {len(weeks)} weeks)")


def main(start=None, end=None, rundate=None):
    ref_dess = fetch_ref_des()
    start, end = start.replace("-", ""), end.replace("-", "")  # YYYYMMDD
    logger.info(f"crawling {len(ref_dess)} instruments over {start}..{end}")

    crawl = partial(crawl_instrument, start=start, end=end)
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(crawl, ref_dess))
    dt = time.perf_counter() - t0
    logger.info(f"crawled {len(ref_dess)} instruments in {dt:.0f}s ({dt / len(ref_dess):.1f}s each)")

    weeks = full_weeks(start, end)
    logger.info(f"{len(weeks)} complete weeks in window: {weeks[0]}..{weeks[-1]}" if weeks
                else "no complete weeks in window")
    write_weekly(results, weeks, f"weekly_delivery_{rundate}.csv")


def main_baseline(start=None, end=None, out="original_expected.csv"):
    """Per-instrument p95 of WEEKLY delivery over a recent window (full-capacity baseline).

    Uses a recent window (default: last 2 years), not deployment-era data: file
    formats/compression have changed, so old bytes aren't comparable. p95 of
    *weekly* totals (not daily) smooths daily burstiness so a healthy week reads
    ~100%, and -- being the high end -- a brief anomaly (<5% of weeks) is excluded
    while a sustained degradation within the window is still captured.
    """
    ref_dess = fetch_ref_des()
    start, end = start.replace("-", ""), end.replace("-", "")  # YYYYMMDD
    logger.info(f"baseline: p95 weekly over {start}..{end} for {len(ref_dess)} instruments")
    crawl = partial(crawl_instrument, start=start, end=end)
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(crawl, ref_dess))
    dt = time.perf_counter() - t0
    logger.info(f"crawled {len(ref_dess)} instruments in {dt:.0f}s ({dt / len(ref_dess):.1f}s each)")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["refDes", "first_day", "last_day", "weeks_with_data",
                    "original_p95_weekly_bytes", "original_p95_weekly_human"])
        for ref_des, daily in sorted(results):
            if not daily:
                w.writerow([ref_des, "", "", 0, 0, "0 B"])
                continue
            weekly = defaultdict(int)
            for day, nbytes in daily.items():
                weekly[week_of(day)] += nbytes
            p95 = round(np.percentile(list(weekly.values()), 95))
            w.writerow([ref_des, min(daily), max(daily), len(weekly),
                        p95, format_size(p95, binary=True)])
    logger.success(f"wrote {out} ({len(results)} instruments)")


def cli():
    today = date.today()
    p = argparse.ArgumentParser(description="Tally OOI raw-archive delivery per instrument.")
    p.add_argument("--start", default=str(months_back(today, 3)), help="YYYY-MM-DD (default: 3 months ago)")
    p.add_argument("--end", default=str(today), help="YYYY-MM-DD (default: today)")
    p.add_argument("--date", default=str(today), help="run date tag on output files (default: today)")
    a = p.parse_args()
    main(start=a.start, end=a.end, rundate=a.date)


def cli_baseline():
    today = date.today()
    p = argparse.ArgumentParser(
        description="C3 baseline: p95 daily over a recent window -> original_expected.csv."
    )
    p.add_argument("--start", default=str(months_back(today, 24)), help="YYYY-MM-DD (default: 2 years ago)")
    p.add_argument("--end", default=str(today), help="YYYY-MM-DD (default: today)")
    a = p.parse_args()
    main_baseline(start=a.start, end=a.end)


if __name__ == "__main__":
    cli()
