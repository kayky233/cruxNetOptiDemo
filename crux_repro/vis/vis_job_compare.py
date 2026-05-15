"""Job-level JCT and Comm comparison chart (Figure 1.3).

Grouped bar chart showing per-job JCT and communication time
for two schedulers side by side, with gain/loss annotations.
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .vis_utils import setup_mpl, SCHEDULER_COLORS, GAIN_COLOR, LOSS_COLOR, save_fig
from .vis_data import load_jobs


def plot_job_compare(jobs_csv: str,
                     baseline="random_same",
                     crux="crux_no_compress",
                     out_dir="results/vis"):
    setup_mpl()
    df = load_jobs(jobs_csv)

    b = df[df["scheduler"] == baseline].set_index("job_id")
    c = df[df["scheduler"] == crux].set_index("job_id")
    job_ids = sorted(b.index.unique())

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    x = np.arange(len(job_ids))
    width = 0.35

    # ── JCT subplot ──────────────────────────────────────────────
    jct_b = [b.loc[jid, "jct_s"] for jid in job_ids]
    jct_c = [c.loc[jid, "jct_s"] for jid in job_ids]

    bars1 = ax1.bar(x - width/2, jct_b, width, label=baseline,
                    color=SCHEDULER_COLORS[baseline], edgecolor="white")
    bars2 = ax1.bar(x + width/2, jct_c, width, label=crux,
                    color=SCHEDULER_COLORS[crux], edgecolor="white")

    # Annotate gain/loss
    for i, jid in enumerate(job_ids):
        gain_pct = (jct_b[i] - jct_c[i]) / jct_b[i] * 100 if jct_b[i] > 0 else 0
        color = GAIN_COLOR if gain_pct > 0 else LOSS_COLOR
        sign = "+" if gain_pct < 0 else "-"
        ax1.annotate(f"{sign}{abs(gain_pct):.0f}%",
                     (x[i] + width/2, jct_c[i]),
                     textcoords="offset points", xytext=(0, 4),
                     fontsize=7, ha="center", color=color, fontweight="bold")

    ax1.set_xticks(x)
    ax1.set_xticklabels(job_ids, fontsize=8)
    ax1.set_ylabel("JCT (s)")
    ax1.set_title(f"Per-Job JCT: {baseline} vs {crux}")
    ax1.legend(fontsize=8)
    ax1.grid(axis="y", alpha=0.3)

    # ── Comm subplot ─────────────────────────────────────────────
    comm_b = [b.loc[jid, "comm_s"] for jid in job_ids]
    comm_c = [c.loc[jid, "comm_s"] for jid in job_ids]

    ax2.bar(x - width/2, comm_b, width, label=baseline,
            color=SCHEDULER_COLORS[baseline], edgecolor="white")
    ax2.bar(x + width/2, comm_c, width, label=crux,
            color=SCHEDULER_COLORS[crux], edgecolor="white")

    for i, jid in enumerate(job_ids):
        gain_pct = (comm_b[i] - comm_c[i]) / comm_b[i] * 100 if comm_b[i] > 0 else 0
        color = GAIN_COLOR if gain_pct > 0 else LOSS_COLOR
        sign = "+" if gain_pct < 0 else "-"
        ax2.annotate(f"{sign}{abs(gain_pct):.0f}%",
                     (x[i] + width/2, comm_c[i]),
                     textcoords="offset points", xytext=(0, 4),
                     fontsize=7, ha="center", color=color, fontweight="bold")

    ax2.set_xticks(x)
    ax2.set_xticklabels(job_ids, fontsize=8)
    ax2.set_ylabel("Comm Time (s)")
    ax2.set_title(f"Per-Job Comm: {baseline} vs {crux}")
    ax2.legend(fontsize=8)
    ax2.grid(axis="y", alpha=0.3)

    fig.suptitle(f"{baseline} vs {crux} — Per-Job Comparison", fontsize=13, y=1.03)
    fig.tight_layout(rect=[0, 0.02, 1, 0.94])
    save_fig(fig, out_dir, "job_jct_comm_comparison")
    plt.close(fig)


if __name__ == "__main__":
    import sys
    plot_job_compare(
        jobs_csv=sys.argv[1] if len(sys.argv) > 1
        else "results/simgrid_real_trace_optimize_balanced_jobs.csv",
        out_dir=sys.argv[2] if len(sys.argv) > 2 else "results/vis",
    )
