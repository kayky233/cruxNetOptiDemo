"""Communication intensity distribution chart (Figure 1.5).

Shows each job's intensity on a log-scale scatter/bar chart,
colored by model type, with a median dividing line.
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .vis_utils import setup_mpl, MODEL_COLORS, save_fig
from .vis_data import load_jobs


def plot_intensity(jobs_csv: str, scheduler="random_same",
                   topology_name=None, out_dir="results/vis"):
    setup_mpl()
    df = load_jobs(jobs_csv)
    if topology_name and "topology" in df.columns:
        df = df[df["topology"] == topology_name]
    df = df[df["scheduler"] == scheduler].copy()
    df = df.sort_values("intensity")

    fig, ax = plt.subplots(figsize=(10, 4))

    # Color by model
    models = df["model"].unique()
    for model in models:
        mask = df["model"] == model
        ax.scatter(
            df.loc[mask, "job_id"],
            df.loc[mask, "intensity"],
            c=MODEL_COLORS.get(model, "#888888"),
            s=60, zorder=5, edgecolors="white", linewidths=0.5,
            label=model,
        )

    # Median dividing line
    median_intensity = df["intensity"].median()
    ax.axhline(median_intensity, color="#CC3311", linestyle="--", linewidth=1.2,
               label=f"median = {median_intensity/1e9:.1f} G")

    ax.set_yscale("log")
    ax.set_xlabel("Job ID")
    ax.set_ylabel("Intensity (log scale)")
    ax.set_title(f"Job Communication Intensity Distribution ({scheduler})")
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    ax.grid(axis="y", alpha=0.3)

    # Annotate job_id on x-axis
    ax.set_xticks(df["job_id"].unique())
    ax.set_xticklabels(df["job_id"].unique(), fontsize=8)

    fig.tight_layout()
    save_fig(fig, out_dir, "intensity_distribution")
    plt.close(fig)


if __name__ == "__main__":
    import sys
    plot_intensity(
        jobs_csv=sys.argv[1] if len(sys.argv) > 1
        else "results/simgrid_real_trace_optimize_balanced_jobs.csv",
        out_dir=sys.argv[2] if len(sys.argv) > 2 else "results/vis",
    )
