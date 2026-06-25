"""Render a delivery-KPI pivot (instruments x weeks) as a heatmap.

Reads kpi_pivot_<metric>_<date>.csv (the instruments-x-weeks percent grid),
drops the mean row, and writes a PNG. Color runs blue (full delivery) to red
(under-delivery); blank cells (no expected delivery -- failed / not in archive)
are gray. Each cell is annotated with its whole-percent value.
"""

import argparse
import os
from datetime import date

import matplotlib
matplotlib.use("Agg")  # headless: render to file, no display needed
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from loguru import logger  # noqa: E402

from rca_kpis.kpi import MEAN_LABEL  # noqa: E402

TITLES = {
    "technical": "C1 Technical availability (delivered / expected)",
    "retention": "C3 Retention (delivered / original expected)",
}


def main(rundate, metric="technical"):
    src = f"reports/{rundate}/kpi_pivot_{metric}.csv"
    out = f"reports/{rundate}/kpi_heatmap_{metric}.png"
    # cells are strings: "" (NA), "100+" (capped/over-delivered), or a whole percent
    grid = pd.read_csv(src, index_col="refDes", dtype=str, keep_default_na=False)
    arr = grid.to_numpy()
    vals = np.full(arr.shape, np.nan)
    capped = np.zeros(arr.shape, bool)
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            c = arr[i, j].strip()
            if c == "100+":
                vals[i, j], capped[i, j] = 100.0, True
            elif c:
                vals[i, j] = float(c)
    data = np.ma.masked_invalid(vals)  # blank cells -> masked

    cmap = plt.get_cmap("RdBu").copy()
    cmap.set_bad("0.8")  # NA cells (no expected delivery) -> gray

    fig, ax = plt.subplots(figsize=(2 + 0.5 * grid.shape[1], 1 + 0.18 * grid.shape[0]))
    im = ax.imshow(data, aspect="auto", cmap=cmap, vmin=0, vmax=100)
    ax.set_xticks(range(grid.shape[1]), grid.columns, rotation=90, fontsize=6)
    ax.set_yticks(range(grid.shape[0]), grid.index, fontsize=6)
    ax.set_xlabel("week (Mon start)")
    ax.set_ylabel("instrument")
    ax.set_title(f"RCA delivery KPI — {TITLES[metric]}\n"
                 "(blue = full, red = under, gray = not expected, gold 100+ = over-delivered/capped)")
    fig.colorbar(im, ax=ax, fraction=0.02, pad=0.01, label="% delivered")
    if grid.index[-1] == MEAN_LABEL:  # separate the summary mean row from instruments
        ax.axhline(grid.shape[0] - 1.5, color="black", linewidth=1.0)

    for i in range(grid.shape[0]):  # annotate each measured cell with its percent
        for j in range(grid.shape[1]):
            if data[i, j] is np.ma.masked:
                continue
            if capped[i, j]:  # over-delivered -> gold flag
                ax.text(j, i, "100+", ha="center", va="center", fontsize=3.5,
                        color="gold", fontweight="bold")
            else:
                v = data[i, j]
                color = "white" if v <= 25 or v >= 75 else "black"  # contrast vs RdBu
                ax.text(j, i, f"{int(v)}", ha="center", va="center", fontsize=4, color=color)

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    logger.success(f"wrote {out} ({grid.shape[0]} instruments x {grid.shape[1]} weeks)")


def cli():
    p = argparse.ArgumentParser(description="Render a delivery-KPI pivot as a heatmap.")
    p.add_argument("--date", default=str(date.today()), help="run date tag (matches compute_kpi --date)")
    p.add_argument("--metric", default="technical", choices=list(TITLES),
                   help="technical (C1) or retention (C3)")
    a = p.parse_args()
    main(a.date, a.metric)


if __name__ == "__main__":
    cli()
