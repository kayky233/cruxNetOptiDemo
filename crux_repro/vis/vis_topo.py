"""Static network topology diagram (Figure 1.4).

Renders a layered network topology using manual coordinates
(no graphviz dependency). Shows hosts, NICs, and switch levels
with bandwidth annotations.
"""

import matplotlib.pyplot as plt
import numpy as np

from .vis_utils import setup_mpl, save_fig
from .vis_data import load_topology


def plot_topology(topology_name="three_tier_clos",
                  hosts=8,
                  gpus_per_host=4,
                  out_dir="results/vis"):
    setup_mpl()
    topo = load_topology(topology_name, hosts=hosts, gpus_per_host=gpus_per_host)

    fig, ax = plt.subplots(figsize=(14, 7))
    ax.set_aspect("equal")
    ax.axis("off")

    # ── Layout coordinates ───────────────────────────────────────
    # Y levels from bottom to top:
    #   level 0: hosts (y=0)
    #   level 1: NICs  (y=1.5)
    #   level 2+: switches (y=2.5, 3.5, 4.5...)
    HOST_Y = 0.0
    NIC_Y = 1.8
    SW_BASE_Y = 3.0
    SW_GAP_Y = 1.5

    x_spacing = 2.0
    host_xs = np.arange(topo.hosts) * x_spacing + 1.0

    # ── Draw hosts ───────────────────────────────────────────────
    host_nodes = []
    for i, x in enumerate(host_xs):
        rect = plt.Rectangle((x - 0.6, HOST_Y - 0.5), 1.2, 2.0,
                             facecolor="#DDDDDD", edgecolor="#333333",
                             linewidth=1.2)
        ax.add_patch(rect)
        ax.text(x, HOST_Y + 0.5, f"H{i}", ha="center", va="center",
                fontsize=8, fontweight="bold")
        # GPU dots
        for g in range(min(topo.gpus_per_host, 4)):
            gx = x - 0.35 + g * 0.23
            gy = HOST_Y - 0.3
            ax.plot(gx, gy, "s", color="#4477AA", markersize=5, zorder=5)
        host_nodes.append((x, HOST_Y + 0.5 * 2))

    # ── Draw NICs ────────────────────────────────────────────────
    nic_nodes = []
    for i, x in enumerate(host_xs):
        ax.plot(x, NIC_Y, "D", color="#DDAA33", markersize=8, zorder=5,
                markeredgecolor="#333", markeredgewidth=0.8)
        ax.text(x, NIC_Y, f"NIC{i}", ha="center", va="bottom",
                fontsize=6, fontweight="bold", color="#885500")
        nic_nodes.append((x, NIC_Y))
        # Host → NIC link
        ax.plot([x, x], [HOST_Y + 0.5, NIC_Y - 0.4],
                color="#999999", linewidth=1.0, zorder=1)

    # ── Draw switches ────────────────────────────────────────────
    sw_levels = topo.switches
    sw_positions = []  # list of (x, y) per switch per level

    for lvl, sw in enumerate(sw_levels):
        ly = SW_BASE_Y + lvl * SW_GAP_Y
        sw_xs = np.linspace(host_xs[0], host_xs[-1], sw.count)
        level_positions = []

        for idx, sx in enumerate(sw_xs):
            ax.plot(sx, ly, "s", color="#CC3311", markersize=10, zorder=5,
                    markeredgecolor="#333", markeredgewidth=0.8)
            ax.text(sx, ly, f"SW{lvl}\n{idx}", ha="center", va="bottom",
                    fontsize=6, fontweight="bold", color="#880000")
            level_positions.append((sx, ly))

            # Annotate bandwidth
            ax.text(sx, ly + 0.5, f"{sw.uplink_gbps:.0f}G",
                    ha="center", fontsize=5, color="#666666")

        sw_positions.append(level_positions)

    # ── Draw NIC → switch connections ────────────────────────────
    if sw_positions:
        # NIC → first switch level
        l0_positions = sw_positions[0]
        for i, (nx, ny) in enumerate(nic_nodes):
            # Connect to nearest switch(es) — use hash-like assignment
            sw_idx = (i * 31 + i * 17) % len(l0_positions)
            sx, sy = l0_positions[sw_idx]
            ax.plot([nx, sx], [ny, sy], color="#AAAAAA", linewidth=0.6,
                    alpha=0.5, zorder=1)

        # Inter-switch connections (upper levels)
        for lvl in range(1, len(sw_positions)):
            lower = sw_positions[lvl - 1]
            upper = sw_positions[lvl]
            for li, (lx, ly_) in enumerate(lower):
                for ui, (ux, uy) in enumerate(upper):
                    # Draw if hash connects them
                    if (li * 7 + ui * 13) % len(upper) == ui % len(upper):
                        ax.plot([lx, ux], [ly_, uy],
                                color="#AAAAAA", linewidth=0.5,
                                alpha=0.3, zorder=1)

    # ── Info box ─────────────────────────────────────────────────
    info_text = (
        f"Topology: {topo.name}\n"
        f"Hosts: {topo.hosts} × {topo.gpus_per_host} GPUs\n"
        f"Local: {topo.local_gbps:.0f} Gbps | NIC: {topo.nic_gbps:.0f} Gbps\n"
        + "\n".join(
            f"SW L{lvl}: ×{sw.count} @ {sw.uplink_gbps:.0f} Gbps ({sw.latency_us:.0f}μs)"
            for lvl, sw in enumerate(sw_levels)
        )
    )
    ax.text(0.02, 0.98, info_text, transform=ax.transAxes,
            fontsize=7, va="top", family="monospace",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#F5F5F5",
                      edgecolor="#CCCCCC", alpha=0.9))

    ax.set_xlim(host_xs[0] - 2, host_xs[-1] + 2)
    ax.set_ylim(HOST_Y - 2, SW_BASE_Y + len(sw_levels) * SW_GAP_Y + 1)
    ax.set_title(f"Network Topology — {topo.name}", fontsize=12, y=1.02)

    fig.tight_layout()
    save_fig(fig, out_dir, "topology_diagram")
    plt.close(fig)


if __name__ == "__main__":
    import sys
    plot_topology(
        topology_name=sys.argv[1] if len(sys.argv) > 1 else "three_tier_clos",
        out_dir=sys.argv[2] if len(sys.argv) > 2 else "results/vis",
    )
