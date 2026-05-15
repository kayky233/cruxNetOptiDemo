"""GPU placement heatmap (Figure 1.2).

Matrix heatmap showing which job occupies each GPU slot.
Side-by-side comparison: random_same vs crux_no_compress.
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .vis_utils import setup_mpl, MODEL_COLORS, save_fig, parse_placement
from .vis_data import load_jobs


def _build_placement_matrix(jobs_df, hosts, gpus_per_host):
    """Build (hosts × gpus_per_host) matrix of job occupancy.

    Returns: matrix with job_id+1 (0 = empty), model_labels matrix, and
    an intensity-sorted list of (job_id, model) for legend.
    """
    matrix = np.zeros((hosts, gpus_per_host), dtype=int)
    model_labels = np.empty((hosts, gpus_per_host), dtype=object)
    model_labels.fill("")

    for _, row in jobs_df.iterrows():
        placement = parse_placement(row["placement"])
        for h, g in placement:
            if 0 <= h < hosts and 0 <= g < gpus_per_host:
                matrix[h, g] = int(row["job_id"]) + 1  # 0 = empty
                model_labels[h, g] = row["model"]

    return matrix, model_labels


def _job_model_map(jobs_df):
    """Return dict job_id→model and list of unique (job_id, model) sorted by job_id."""
    mapping = {}
    for _, row in jobs_df.iterrows():
        mapping[int(row["job_id"])] = row["model"]
    uniques = sorted(set((int(r["job_id"]), r["model"]) for _, r in jobs_df.iterrows()))
    return mapping, uniques


def plot_placement(jobs_csv: str,
                   baseline="random_same",
                   crux="crux_no_compress",
                   hosts=8,
                   gpus_per_host=8,
                   topology_name=None,
                   out_dir="results/vis"):
    setup_mpl()
    df = load_jobs(jobs_csv)
    if topology_name and "topology" in df.columns:
        df = df[df["topology"] == topology_name]

    b = df[df["scheduler"] == baseline]
    c = df[df["scheduler"] == crux]

    mat_b, lbl_b = _build_placement_matrix(b, hosts, gpus_per_host)
    mat_c, lbl_c = _build_placement_matrix(c, hosts, gpus_per_host)
    _, uniques = _job_model_map(df)

    # Color map: map job_id → color by model
    job_colors = {}
    for jid, model in uniques:
        job_colors[jid + 1] = MODEL_COLORS.get(model, "#CCCCCC")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    def _draw_heatmap(ax, matrix, model_labels, scheduler, job_colors):
        """Draw a single heatmap panel."""
        # Build a colored grid manually
        hosts, gpus = matrix.shape
        cell_w, cell_h = 1.0, 1.0

        for h in range(hosts):
            for g in range(gpus):
                jid = matrix[h, g]
                color = job_colors.get(jid, "#EEEEEE")
                rect = plt.Rectangle((g, hosts - 1 - h), cell_w, cell_h,
                                     facecolor=color, edgecolor="white",
                                     linewidth=1.5)
                ax.add_patch(rect)
                if jid > 0:
                    ax.text(
                        g + 0.5, hosts - 1 - h + 0.5,
                        f"j{jid - 1}",
                        ha="center", va="center",
                        fontsize=7, fontweight="bold",
                        color="white",
                    )

        ax.set_xlim(0, gpus)
        ax.set_ylim(0, hosts)
        ax.set_xticks(np.arange(gpus) + 0.5)
        ax.set_xticklabels([f"GPU{g}" for g in range(gpus)], fontsize=8)
        ax.set_yticks(np.arange(hosts) + 0.5)
        ax.set_yticklabels([f"H{h}" for h in range(hosts - 1, -1, -1)], fontsize=8)
        ax.set_title(f"GPU Placement — {scheduler}", fontsize=11)
        ax.set_aspect("equal")

    _draw_heatmap(ax1, mat_b, lbl_b, baseline, job_colors)
    _draw_heatmap(ax2, mat_c, lbl_c, crux, job_colors)

    # Legend below
    legend_labels = [f"j{jid}: {model}" for jid, model in uniques]
    legend_colors = [job_colors[jid + 1] for jid, _ in uniques]
    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=c, edgecolor="white")
               for c in legend_colors]
    fig.legend(handles, legend_labels, loc="lower center", ncol=6, fontsize=7,
               frameon=False)

    fig.suptitle(f"GPU Placement: {baseline} (left) vs {crux} (right)",
                 fontsize=13, y=1.08)
    fig.tight_layout(rect=[0, 0.08, 1, 0.95])
    save_fig(fig, out_dir, "placement_heatmap")
    plt.close(fig)


if __name__ == "__main__":
    import sys
    plot_placement(
        jobs_csv=sys.argv[1] if len(sys.argv) > 1
        else "results/simgrid_real_trace_optimize_balanced_jobs.csv",
        out_dir=sys.argv[2] if len(sys.argv) > 2 else "results/vis",
    )
