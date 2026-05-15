"""Job Gantt chart (Figure 1.1).

Side-by-side horizontal bar chart showing each job's timeline
(random_same left, crux_no_compress right). Jobs sorted by JCT.
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .vis_utils import setup_mpl, MODEL_COLORS, SCHEDULER_COLORS, save_fig
from .vis_data import load_jobs


def plot_gantt(jobs_csv: str,
               baseline="random_same",
               crux="crux_no_compress",
               out_dir="results/vis"):
    setup_mpl()
    df = load_jobs(jobs_csv)

    b = df[df["scheduler"] == baseline].copy()
    c = df[df["scheduler"] == crux].copy()

    # Sort by JCT ascending (shortest on top)
    b = b.sort_values("jct_s", ascending=True)
    c = c.sort_values("jct_s", ascending=True)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7), sharey=True)

    def _draw_gantt(ax, data, scheduler, label):
        """Draw horizontal bars for one scheduler."""
        jobs = data.reset_index(drop=True)
        makespan = jobs["sim_finish_s"].max()
        bar_height = 0.65

        for i, row in jobs.iterrows():
            color = MODEL_COLORS.get(row["model"], "#888888")
            ax.barh(
                i,
                row["jct_s"],
                bar_height,
                left=row["sim_start_s"],
                color=color,
                edgecolor="white",
                linewidth=0.3,
                alpha=0.9,
            )
            # Label model name inside the bar if it fits
            if row["jct_s"] > makespan * 0.08:
                ax.text(
                    row["sim_start_s"] + row["jct_s"] / 2,
                    i,
                    f"{row['model']} (j{int(row['job_id'])})",
                    ha="center", va="center",
                    fontsize=6, color="white",
                    fontweight="bold",
                )

        # Makespan line
        ax.axvline(makespan, color=SCHEDULER_COLORS.get(scheduler, "#000"),
                   linestyle="--", linewidth=1.2, alpha=0.6)
        ax.text(makespan + 1, len(jobs) - 1, f"makespan={makespan:.1f}s",
                fontsize=7, va="top")

        ax.set_xlabel("Time (s)")
        ax.set_title(f"{scheduler}\nmakespan={makespan:.1f}s", fontsize=10)
        ax.set_yticks(range(len(jobs)))
        ax.set_yticklabels([f"j{int(r['job_id'])}" for _, r in jobs.iterrows()], fontsize=7)
        ax.set_xlim(0, makespan * 1.08)
        ax.grid(axis="x", alpha=0.3)

    _draw_gantt(ax1, b, baseline, baseline)
    _draw_gantt(ax2, c, crux, crux)

    fig.suptitle(f"Job Timeline: {baseline} vs {crux}", fontsize=13, y=1.01)
    fig.tight_layout()
    save_fig(fig, out_dir, "gantt_comparison")
    plt.close(fig)


if __name__ == "__main__":
    import sys
    plot_gantt(
        jobs_csv=sys.argv[1] if len(sys.argv) > 1
        else "results/simgrid_real_trace_optimize_balanced_jobs.csv",
        out_dir=sys.argv[2] if len(sys.argv) > 2 else "results/vis",
    )
