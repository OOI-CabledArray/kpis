"""Prefect flow: weekly RCA KPI pipeline (C1 + C2 + C3).

C1/C3 archive crawl and C2 science crawl run in parallel; compute_kpi
and plots follow sequentially. Results are committed back to the repo.

Requires a GIT_TOKEN env var (GitHub PAT with repo write) — set it as a
Prefect variable or ECS secret in the work pool configuration.
"""

import os
import subprocess
from datetime import date
from typing import Optional

from prefect import flow, task, get_run_logger

from rca_kpis.archive_crawler import main as _crawl_archive, months_back
from rca_kpis.science import main as _crawl_science
from rca_kpis.kpi import main as _compute_kpi
from rca_kpis.viz import main as _plot_kpi


@task(name="crawl-archive")
def crawl_archive_task(rundate, start):
    logger = get_run_logger()
    logger.info(f"crawl_archive: {start} -> {rundate}")
    _crawl_archive(start=start, end=rundate, rundate=rundate)


@task(name="crawl-science", timeout_seconds=5400)  # 90 min ceiling for large zarr runs
def crawl_science_task(rundate, start, workers=None):
    logger = get_run_logger()
    logger.info(f"crawl_science: {start} -> {rundate} (workers={workers or 'auto'})")
    _crawl_science(start=start, end=rundate, rundate=rundate, workers=workers)


@task(name="compute-kpi")
def compute_kpi_task(rundate):
    _compute_kpi(rundate=rundate)


@task(name="plot-kpi")
def plot_kpi_task(metric, rundate):
    _plot_kpi(rundate=rundate, metric=metric)


@task(name="git-commit-push")
def git_commit_push_task(rundate):
    logger = get_run_logger()
    token = os.environ["GIT_TOKEN"]
    remote = "https://x-access-token:{}@github.com/OOI-CabledArray/kpis.git".format(token)

    def run(cmd):
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)
        return result.stdout.strip()

    run("git config user.name 'prefect-bot'")
    run("git config user.email 'prefect-bot@users.noreply.github.com'")
    run(f"git remote set-url origin {remote}")
    run(f"git add reports/{rundate}/")
    status = run("git status --porcelain")
    if not status:
        logger.info("nothing to commit")
        return
    run(f'git commit -m "Weekly KPI {rundate} (Prefect)"')
    run("git push origin main")
    logger.info(f"pushed reports/{rundate}/")


@flow(name="rca-kpis", timeout_seconds=10800)
def kpi_pipeline(science_workers: Optional[int] = None):
    today = date.today()
    rundate = str(today)
    start = str(months_back(today, 3))

    # crawls stay sequential: overlapping them OOM'd 30 GB, and the science
    # crawl alone needs most of the 60 GB task at full worker count
    crawl_archive_task(rundate=rundate, start=start)
    crawl_science_task(rundate=rundate, start=start, workers=science_workers)
    compute_kpi_task(rundate=rundate)
    for m in ("technical", "retention", "science"):
        plot_kpi_task(metric=m, rundate=rundate)
    git_commit_push_task(rundate=rundate)


if __name__ == "__main__":
    kpi_pipeline()
