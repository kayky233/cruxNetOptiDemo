"""Switch path distribution heatmap (Figure 1.6).

Computes which switches each job's cross-host flows traverse
(using SimGrid's deterministic hash) and renders a heatmap
showing switch utilization per job, comparing two schedulers.
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .vis_utils import (setup_mpl, SCHEDULER_COLORS, GAIN_COLOR, LOSS_COLOR,
                        save_fig, parse_placement, compute_cross_host_flows,
                        compute_switch_path)
from .vis_data import load_jobs, load_topology


def _compute_job_switch_matrix(jobs_df, topo):
    """Compute per-job switch usage matrix.

    For each job, count how many cross-host flows traverse
    each switch. Returns (job_ids, switch_names, matrix).
    """
    job_ids = sorted(jobs_df["job_id"].unique())
    sw_names = topo.switch_names
    matrix = np.zeros((len(job_ids), len(sw_names)), dtype=float)

    for _, row in jobs_df.iterrows():
        jidx = job_ids.index(int(row["job_id"]))
        placement = parse_placement(row["placement"])
        ranks = int(row["ranks"])

        cross_pairs = compute_cross_host_flows(placement, ranks)
        for src_host, dst_host in cross_pairs:
            paths = compute_switch_path(
                (src_host, dst_host), topo.switch_counts
            )
            sw_offset = 0
            for lvl, sw_idx in enumerate(paths):
                name = f"sw{lvl}_{sw_idx}"
                try:
                    sw_flat = sw_names.index(name)
                    matrix[jidx, sw_flat] += 1.0
                except ValueError:
                    pass
                sw_offset += topo.switches[lvl].count

    return job_ids, sw_names, matrix


def _group_switches_by_level(sw_names, topo):
    """Group switch names by their level prefix."""
    groups = {}
    for name in sw_names:
        lvl = int(name.split("_")[0][2:])  # swL_N -> L
        groups.setdefault(lvl, []).append(name)
    return groups


def plot_path_heatmap(jobs_csv: str,
                      topology_name="three_tier_clos",
                      hosts=8,
                      gpus_per_host=4,
                      baseline="random_same",
                      crux="crux_no_compress",
                      out_dir="results/vis"):
    setup_mpl()
    df = load_jobs(jobs_csv)
    if topology_name and "topology" in df.columns:
        df = df[df["topology"] == topology_name]
    topo = load_topology(topology_name, hosts=hosts, gpus_per_host=gpus_per_host)

    b = df[df["scheduler"] == baseline]
    c = df[df["scheduler"] == crux]

    job_ids_b, sw_names_b, mat_b = _compute_job_switch_matrix(b, topo)
    job_ids_c, sw_names_c, mat_c = _compute_job_switch_matrix(c, topo)

    # Normalize: per-job switch usage / max across both matrices
    mat_combined = np.concatenate([mat_b, mat_c])
    vmax = mat_combined.max() or 1.0

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 5))

    def _draw_switch_heatmap(ax, matrix, job_ids, sw_names, scheduler, topo):
        im = ax.imshow(matrix, aspect="auto", cmap="YlOrRd",
                       vmin=0, vmax=vmax, interpolation="nearest")

        # Annotate
        for i in range(len(job_ids)):
            for j in range(len(sw_names)):
                val = matrix[i, j]
                if val > 0:
                    color = "white" if val > vmax * 0.6 else "black"
                    ax.text(j, i, f"{val:.0f}", ha="center", va="center",
                            fontsize=6, color=color, fontweight="bold")

        # Group switch labels by level
        sw_groups = _group_switches_by_level(sw_names, topo)
        # Build level separator lines
        offset = 0
        for lvl in sorted(sw_groups.keys()):
            cnt = len(sw_groups[lvl])
            if offset > 0:
                ax.axvline(offset - 0.5, color="white", linewidth=2)
            offset += cnt

        ax.set_xticks(range(len(sw_names)))
        ax.set_xticklabels(sw_names, rotation=45, ha="right", fontsize=6)
        ax.set_yticks(range(len(job_ids)))
        ax.set_yticklabels([f"j{jid}" for jid in job_ids], fontsize=7)
        ax.set_title(f"{scheduler}\nSwitch cross-host flow count", fontsize=10)
        ax.set_xlabel("Switches")

        # Add level labels
        offset = 0
        for lvl in sorted(sw_groups.keys()):
            cnt = len(sw_groups[lvl])
            mid = offset + cnt / 2 - 0.5
            ax.text(mid, -1.5, f"L{lvl}", ha="center", fontsize=7,
                    fontweight="bold", color="#CC3311",
                    transform=ax.get_xaxis_transform())
            offset += cnt

    _draw_switch_heatmap(ax1, mat_b, job_ids_b, sw_names_b, baseline, topo)
    _draw_switch_heatmap(ax2, mat_c, job_ids_c, sw_names_c, crux, topo)

    # Colorbar
    cbar = fig.colorbar(ax2.images[0], ax=[ax1, ax2], orientation="horizontal",
                        pad=0.08, shrink=0.6)
    cbar.set_label("Cross-host flow count through switch", fontsize=8)

    fig.suptitle(f"Switch Path Distribution: {baseline} vs {crux}\n"
                 f"Topology: {topo.name} ({hosts}h × {gpus_per_host}GPU)",
                 fontsize=12, y=1.06)
    fig.subplots_adjust(top=0.88, bottom=0.12, wspace=0.3)
    save_fig(fig, out_dir, "path_switch_heatmap")
    plt.close(fig)


if __name__ == "__main__":
    import sys
    plot_path_heatmap(
        jobs_csv=sys.argv[1] if len(sys.argv) > 1
        else "results/simgrid_real_trace_optimize_balanced_jobs.csv",
        out_dir=sys.argv[2] if len(sys.argv) > 2 else "results/vis",
    )
