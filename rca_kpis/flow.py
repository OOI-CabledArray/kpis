"""Prefect flow: weekly RCA KPI pipeline (C1 + C2 + C3).

C1/C3 archive crawl and C2 science crawl run in parallel; compute_kpi
and plots follow sequentially. Results are committed back to the repo.

Requires a GIT_TOKEN env var (GitHub PAT with repo write) — set it as a
Prefect variable or ECS secret in the work pool configuration.
"""

import logging
import os
import subprocess
from contextlib import contextmanager
from datetime import date
from importlib.metadata import distributions

from loguru import logger as loguru_logger
from prefect import flow, task, get_run_logger

from rca_kpis.archive_crawler import main as _crawl_archive, months_back
from rca_kpis.science import main as _crawl_science
from rca_kpis.kpi import main as _compute_kpi
from rca_kpis.viz import main as _plot_kpi

# loguru level names -> stdlib levels (SUCCESS has no stdlib equivalent)
_LEVELS = {"TRACE": 5, "DEBUG": 10, "INFO": 20, "SUCCESS": 20,
           "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


@contextmanager
def loguru_to_prefect():
    """Forward the crawlers' loguru records into the Prefect run logger so
    per-instrument warnings (missing QARTOD, missing archive folder, ...)
    show up in the Prefect UI, not just container stderr."""
    run_logger = get_run_logger()
    sink = loguru_logger.add(
        lambda m: run_logger.log(_LEVELS.get(m.record["level"].name, logging.INFO),
                                 m.record["message"]),
        format="{message}", level="INFO",
    )
    try:
        yield
    finally:
        loguru_logger.remove(sink)


@task(name="crawl-archive")
def crawl_archive_task(rundate, start):
    logger = get_run_logger()
    logger.info(f"crawl_archive: {start} -> {rundate}")
    with loguru_to_prefect():
        _crawl_archive(start=start, end=rundate, rundate=rundate)


@task(name="crawl-science", timeout_seconds=9000)  # 2.5 h ceiling: serial over large zarr
def crawl_science_task(rundate, start):
    logger = get_run_logger()
    logger.info(f"crawl_science: {start} -> {rundate}")
    with loguru_to_prefect():
        _crawl_science(start=start, end=rundate, rundate=rundate)


@task(name="compute-kpi")
def compute_kpi_task(rundate):
    with loguru_to_prefect():
        _compute_kpi(rundate=rundate)


@task(name="plot-kpi")
def plot_kpi_task(metric, rundate):
    with loguru_to_prefect():
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
def kpi_pipeline():
    logger = get_run_logger()
    # log the container's actual package versions -- confirms flox et al. made it
    # into the running image (a missing flox is the #1 cause of C2 OOMs)
    installed = {d.metadata["Name"]: d.version for d in distributions()}
    logger.info(f"Installed packages: {installed}")
    logger.info(f"flox present: {'flox' in installed} | cpu cores: {os.cpu_count()}")

    today = date.today()
    rundate = str(today)
    start = str(months_back(today, 3))

    # C2 crawls instruments serially (no threading): the heavy reductions each
    # need most of the 60 GB task, so concurrency OOMs. Reliable over fast --
    # fine for a weekly batch job. Whole pipeline is sequential.
    crawl_archive_task(rundate=rundate, start=start)
    crawl_science_task(rundate=rundate, start=start)
    compute_kpi_task(rundate=rundate)
    for m in ("technical", "retention", "science"):
        plot_kpi_task(metric=m, rundate=rundate)
    git_commit_push_task(rundate=rundate)


if __name__ == "__main__":
    kpi_pipeline()
