#!/usr/bin/env python3
"""Network topology & job placement visualization for SimGrid collective sim.

Reads:
  - job CSV (placement per job per scheduler)
  - link CSV (per-link aggregate utilization)
  - link timeline CSV (per-second per-link bytes, optional)

Generates SVG:
  1. topology_map.svg      — full network topology with GPUs colored by job
  2. link_congestion.svg   — link utilization bar chart (sorted by congestion)
  3. job_paths.svg         — per-job network path trace (Ring AllReduce ring overlay)
  4. gpu_gantt.svg         — GPU occupancy timeline (Gantt per GPU, colored by job)
  5. placement_compare.svg — side-by-side placement comparison (baseline vs target)
"""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ═══════════════════════════════════════════════════════════════
# Data model
# ═══════════════════════════════════════════════════════════════

@dataclass
class SwitchLevel:
    count: int
    uplink_gbps: float
    label: str  # "ToR", "Agg", "Core", "Spine", "Leaf"

@dataclass
class TopoSpec:
    name: str
    hosts: int
    gpus_per_host: int
    nics_per_host: int
    local_gbps: float
    nic_gbps: float
    switch_levels: list[SwitchLevel] = field(default_factory=list)

    @property
    def total_gpus(self) -> int:
        return self.hosts * self.gpus_per_host

    @property
    def total_nics(self) -> int:
        return self.hosts * self.nics_per_host

    @property
    def total_switches(self) -> int:
        return sum(sl.count for sl in self.switch_levels)


def make_topo_spec(name: str, hosts: int, gpus_per_host: int) -> TopoSpec:
    """Mirrors topology.h presets."""
    if name == "star":
        return TopoSpec(name, hosts, gpus_per_host, 1, 400, 100,
                        [SwitchLevel(1, 320, "Core")])
    if name == "fat_tree":
        return TopoSpec(name, hosts, gpus_per_host, 1, 600, 100,
                        [SwitchLevel(4, 200, "ToR"),
                         SwitchLevel(2, 400, "Spine")])
    if name == "three_tier_clos":
        return TopoSpec(name, hosts, gpus_per_host, 1, 600, 100,
                        [SwitchLevel(8, 200, "ToR"),
                         SwitchLevel(4, 400, "Agg"),
                         SwitchLevel(2, 800, "Core")])
    if name == "dragonfly":
        return TopoSpec(name, hosts, gpus_per_host, 1, 600, 100,
                        [SwitchLevel(4, 200, "Group"),
                         SwitchLevel(2, 400, "Global")])
    if name == "ascend":
        return TopoSpec(name, hosts, gpus_per_host, 2, 400, 200,
                        [SwitchLevel(hosts, 400, "Leaf"),
                         SwitchLevel(4, 800, "Spine")])
    # default: generic clos
    return TopoSpec(name, hosts, gpus_per_host, 1, 400, 100,
                    [SwitchLevel(4, 200, "ToR"),
                     SwitchLevel(2, 400, "Core")])


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def f(row: dict[str, str], key: str) -> float:
    return float(row[key])


# ═══════════════════════════════════════════════════════════════
# Layout engine
# ═══════════════════════════════════════════════════════════════

@dataclass
class NodePos:
    x: float; y: float; w: float = 14; h: float = 14
    label: str = ""; kind: str = "gpu"  # gpu, nic, switch

class TopoLayout:
    """Compute 2D positions for all topology nodes."""

    def __init__(self, topo: TopoSpec, width: float = 1200, height: float = 900):
        self.topo = topo
        self.width = width
        self.height = height
        self.margin = 80
        self.gpu_w = 22; self.gpu_h = 14; self.gpu_gap = 3
        self.host_gap = 18
        self.nic_w = 16; self.nic_h = 10
        self.sw_w = 28; self.sw_h = 16
        self.switch_level_gap = 60
        self.nodes: dict[str, NodePos] = {}

        self._layout()

    def gpu_id(self, host: int, gpu: int) -> str:
        return f"h{host}g{gpu}"

    def nic_id(self, host: int, nic_idx: int) -> str:
        return f"nic{host}_{nic_idx}"

    def switch_id(self, level: int, idx: int) -> str:
        return f"sw{level}_{idx}"

    def _layout(self):
        t = self.topo
        usable_w = self.width - 2 * self.margin
        usable_h = self.height - 2 * self.margin

        # GPU layer (bottom)
        host_w = t.gpus_per_host * self.gpu_w + (t.gpus_per_host - 1) * self.gpu_gap
        total_hosts_w = t.hosts * host_w + (t.hosts - 1) * self.host_gap
        host_start_x = self.margin + (usable_w - total_hosts_w) / 2
        gpu_y = self.height - self.margin - self.gpu_h

        for h in range(t.hosts):
            hx = host_start_x + h * (host_w + self.host_gap)
            for g in range(t.gpus_per_host):
                gx = hx + g * (self.gpu_w + self.gpu_gap)
                nid = self.gpu_id(h, g)
                self.nodes[nid] = NodePos(gx, gpu_y, self.gpu_w, self.gpu_h, f"H{h}G{g}", "gpu")

        # NIC layer (above GPUs)
        nic_y = gpu_y - 50
        for h in range(t.hosts):
            host_center = host_start_x + h * (host_w + self.host_gap) + host_w / 2
            for n in range(t.nics_per_host):
                nx = host_center + (n - (t.nics_per_host - 1) / 2) * (self.nic_w + 8)
                nid = self.nic_id(h, n)
                self.nodes[nid] = NodePos(nx, nic_y, self.nic_w, self.nic_h, f"NIC{h}.{n}", "nic")

        # Switch layers (top → bottom = core → ToR)
        total_levels = len(t.switch_levels)
        sw_area_top = self.margin + 40
        sw_area_bottom = nic_y - 70
        sw_area_h = sw_area_bottom - sw_area_top
        level_gap = sw_area_h / max(total_levels, 1)

        for li, sl in enumerate(t.switch_levels):
            ly = sw_area_top + li * level_gap
            sw_area_w = usable_w * 0.8
            sw_start_x = self.margin + (usable_w - sw_area_w) / 2
            sw_gap = sw_area_w / max(sl.count, 1)
            for si in range(sl.count):
                sx = sw_start_x + si * sw_gap + sw_gap / 2 - self.sw_w / 2
                nid = self.switch_id(li, si)
                self.nodes[nid] = NodePos(sx, ly, self.sw_w, self.sw_h,
                                          f"{sl.label}{si}", "switch")

    def node(self, nid: str) -> NodePos:
        return self.nodes.get(nid, NodePos(0, 0))


# ═══════════════════════════════════════════════════════════════
# Route computation (mirrors build_platform in collective_sim.cpp)
# ═══════════════════════════════════════════════════════════════

def compute_route_links(h1: int, g1: int, h2: int, g2: int, topo: TopoSpec) -> list[str]:
    """Return ordered list of link node-ids along the path from (h1,g1) to (h2,g2)."""
    links: list[str] = []
    if h1 == h2:
        links.append(f"local{h1}")
        return links
    nic1 = g1 % topo.nics_per_host
    nic2 = g2 % topo.nics_per_host
    links.append(f"nic{h1}_{nic1}")
    for lvl, sl in enumerate(topo.switch_levels):
        idx = (h1 * 31 + h2 * 17 + lvl * 7) % sl.count
        links.append(f"sw{lvl}_{idx}")
    links.append(f"nic{h2}_{nic2}")
    return links


def compute_ring_paths(placement: list[tuple[int, int]], topo: TopoSpec) -> list[list[str]]:
    """For a Ring AllReduce, return the link list for each rank→next_rank hop."""
    n = len(placement)
    paths: list[list[str]] = []
    for i in range(n):
        h1, g1 = placement[i]
        h2, g2 = placement[(i + 1) % n]
        paths.append(compute_route_links(h1, g1, h2, g2, topo))
    return paths


# ═══════════════════════════════════════════════════════════════
# SVG helpers
# ═══════════════════════════════════════════════════════════════

JOB_COLORS = [
    "#ef4444", "#f59e0b", "#22c55e", "#3b82f6", "#8b5cf6", "#ec4899",
    "#14b8a6", "#f97316", "#06b6d4", "#a855f7", "#84cc16", "#e11d48",
    "#0ea5e9", "#d946ef", "#10b981", "#6366f1",
]

SCHED_COLORS = {
    "random_same": "#64748b",
    "random_intensity": "#0ea5e9",
    "place_only": "#8b5cf6",
    "priority_only": "#f59e0b",
    "crux_no_compress": "#22c55e",
    "crux": "#ef4444",
}


def svg_text(x: float, y: float, text: str, size: int = 11, anchor: str = "start",
             weight: str = "400", fill: str = "#1f2937") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial,Helvetica,sans-serif" '
            f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}">{text}</text>')


def svg_line(x1: float, y1: float, x2: float, y2: float, stroke: str = "#cbd5e1",
             width: float = 1.0, opacity: float = 1.0) -> str:
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-width="{width:.1f}" opacity="{opacity:.2f}"/>')


def svg_rect(x: float, y: float, w: float, h: float, fill: str = "#e5e7eb",
             rx: float = 2, stroke: str = "none", opacity: float = 1.0) -> str:
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'fill="{fill}" rx="{rx:.0f}" stroke="{stroke}" opacity="{opacity:.2f}"/>')


# ═══════════════════════════════════════════════════════════════
# Chart: Topology + Placement map
# ═══════════════════════════════════════════════════════════════

def draw_topology_map(topo: TopoSpec, jobs_placement: dict[int, list[tuple[int, int]]],
                      link_util: dict[str, float], out_path: Path,
                      title: str = "Network Topology & Job Placement"):
    """Full topology diagram with GPUs colored by job assignment."""
    layout = TopoLayout(topo, width=1400, height=950)
    w, h = layout.width, layout.height

    # Assign each GPU a job
    gpu_job: dict[str, int] = {}
    for jid, placement in jobs_placement.items():
        for rank, (host, gpu_idx) in enumerate(placement):
            gid = layout.gpu_id(host, gpu_idx)
            if gid not in gpu_job:
                gpu_job[gid] = jid

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        svg_text(w / 2, 24, title, 16, "middle", "700"),
    ]

    # Draw switch-to-switch links and NIC-to-switch links
    drawn: set[tuple[str, str]] = set()
    max_util = max(link_util.values()) if link_util else 1.0

    def link_width(link_name: str) -> float:
        u = link_util.get(link_name, 0)
        return 0.8 + 5.0 * (u / max_util) if max_util > 0 else 0.8

    def link_color(link_name: str) -> str:
        u = link_util.get(link_name, 0)
        if u > 0.5: return "#ef4444"
        if u > 0.3: return "#f59e0b"
        if u > 0.1: return "#3b82f6"
        return "#cbd5e1"

    def draw_link(a: str, b: str):
        if (a, b) in drawn or (b, a) in drawn:
            return
        drawn.add((a, b))
        na = layout.node(a); nb = layout.node(b)
        if na.x == 0 and na.y == 0: return
        if nb.x == 0 and nb.y == 0: return
        # Find matching link name for utilization
        lw = 1.0; lc = "#cbd5e1"
        for ln in [a, b, a.replace("_", ""), b.replace("_", "")]:
            if ln in link_util:
                lw = link_width(ln); lc = link_color(ln); break
        parts.append(svg_line(na.x + na.w / 2, na.y + na.h / 2,
                               nb.x + nb.w / 2, nb.y + nb.h / 2, lc, lw, 0.6))

    # Draw switch interconnects (core→agg, agg→tor)
    for li in range(len(topo.switch_levels) - 1):
        for si in range(topo.switch_levels[li].count):
            for sj in range(topo.switch_levels[li + 1].count):
                draw_link(layout.switch_id(li, si), layout.switch_id(li + 1, sj))

    # NIC → ToR (first switch level) links
    if topo.switch_levels:
        for h in range(topo.hosts):
            for n in range(topo.nics_per_host):
                for s in range(topo.switch_levels[0].count):
                    draw_link(layout.nic_id(h, n), layout.switch_id(0, s))

    # GPU → NIC links
    for h in range(topo.hosts):
        for g in range(topo.gpus_per_host):
            nic = g % topo.nics_per_host
            draw_link(layout.gpu_id(h, g), layout.nic_id(h, nic))

    # Draw switches
    for li, sl in enumerate(topo.switch_levels):
        for si in range(sl.count):
            nid = layout.switch_id(li, si)
            np = layout.node(nid)
            parts.append(svg_rect(np.x, np.y, np.w, np.h, "#475569", 4))
            parts.append(svg_text(np.x + np.w / 2, np.y + np.h / 2 + 4,
                                  f"{sl.label[:2]}{si}", 8, "middle", "600", "#ffffff"))

    # Draw NICs
    for h in range(topo.hosts):
        for n in range(topo.nics_per_host):
            nid = layout.nic_id(h, n)
            np = layout.node(nid)
            nic_util = link_util.get(f"nic{h}_{n}", 0)
            nic_color = link_color(f"nic{h}_{n}")
            parts.append(svg_rect(np.x, np.y, np.w, np.h, nic_color, 3))
            parts.append(svg_text(np.x + np.w / 2, np.y - 4, f"N{h}", 7, "middle", "400", "#64748b"))

    # Draw GPUs colored by job
    for h in range(topo.hosts):
        for g in range(topo.gpus_per_host):
            gid = layout.gpu_id(h, g)
            np = layout.node(gid)
            jid = gpu_job.get(gid, -1)
            color = JOB_COLORS[jid % len(JOB_COLORS)] if jid >= 0 else "#e5e7eb"
            parts.append(svg_rect(np.x, np.y, np.w, np.h, color, 3, "#334155", 1.0))
            if jid >= 0:
                parts.append(svg_text(np.x + np.w / 2, np.y + np.h / 2 + 4,
                                      str(jid), 7, "middle", "700", "#ffffff"))

    # Host labels
    host_w = topo.gpus_per_host * layout.gpu_w + (topo.gpus_per_host - 1) * layout.gpu_gap
    total_hosts_w = topo.hosts * host_w + (topo.hosts - 1) * layout.host_gap
    host_start_x = layout.margin + (layout.width - 2 * layout.margin - total_hosts_w) / 2
    for h in range(topo.hosts):
        hx = host_start_x + h * (host_w + layout.host_gap) + host_w / 2
        parts.append(svg_text(hx, layout.height - layout.margin + 16, f"H{h}", 10, "middle", "600", "#334155"))

    # Legend
    used_jobs = sorted(set(gpu_job.values()))
    lx = layout.width - 180; ly = 45
    parts.append(svg_text(lx, ly - 5, "Job Legend", 11, "start", "700"))
    for i, jid in enumerate(used_jobs[:12]):
        y = ly + i * 20
        color = JOB_COLORS[jid % len(JOB_COLORS)]
        parts.append(svg_rect(lx, y, 14, 14, color, 2))
        parts.append(svg_text(lx + 20, y + 11, f"Job {jid}", 10))

    # Link congestion legend
    clx = lx; cly = ly + len(used_jobs[:12]) * 20 + 30
    parts.append(svg_text(clx, cly - 5, "Link Util", 11, "start", "700"))
    for i, (label, col) in enumerate([(">50%", "#ef4444"), (">30%", "#f59e0b"), (">10%", "#3b82f6"), ("<10%", "#cbd5e1")]):
        y = cly + i * 18
        parts.append(svg_rect(clx, y, 14, 14, col, 2))
        parts.append(svg_text(clx + 20, y + 11, label, 10))

    parts.append("</svg>")
    out_path.write_text("\n".join(parts), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
# Chart: Link congestion bar chart
# ═══════════════════════════════════════════════════════════════

def draw_link_congestion(link_util: dict[str, float], out_path: Path,
                         title: str = "Link Utilization"):
    """Horizontal bar chart of link utilization, sorted descending."""
    if not link_util:
        return

    sorted_links = sorted(link_util.items(), key=lambda x: -x[1])
    # Group by type
    groups: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for name, util in sorted_links:
        if name.startswith("local"):
            groups["Intra-host (local)"].append((name, util))
        elif name.startswith("nic"):
            groups["NIC"].append((name, util))
        elif name.startswith("sw"):
            lvl = name.split("_")[0]
            groups[f"Switch {lvl}"].append((name, util))

    n_items = sum(len(v) for v in groups.values())
    bar_h = 12; gap = 3; group_gap = 14
    margin_l, margin_r, margin_t, margin_b = 140, 100, 40, 30
    width = 780
    plot_w = width - margin_l - margin_r
    height = margin_t + margin_b + n_items * (bar_h + gap) + len(groups) * group_gap

    max_util = max(u for _, u in sorted_links) if sorted_links else 1.0

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        svg_text(width / 2, 22, title, 15, "middle", "700"),
    ]

    y = margin_t
    for group_name, items in groups.items():
        if not items: continue
        parts.append(svg_text(margin_l, y + 10, group_name, 11, "start", "700", "#475569"))
        y += 6
        for name, util in items:
            bar_w = max(1, util / max_util * plot_w) if max_util > 0 else 0
            if util > 0.5: color = "#ef4444"
            elif util > 0.3: color = "#f59e0b"
            elif util > 0.1: color = "#3b82f6"
            else: color = "#cbd5e1"
            parts.append(svg_rect(margin_l, y, bar_w, bar_h, color, 2))
            parts.append(svg_text(margin_l + bar_w + 6, y + 10, f"{util*100:.1f}%", 9, "start", "500", "#64748b"))
            parts.append(svg_text(margin_l - 8, y + 10, name, 9, "end", "400", "#6b7280"))
            y += bar_h + gap
        y += group_gap

    parts.append("</svg>")
    out_path.write_text("\n".join(parts), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
# Chart: Per-job ring path overlay
# ═══════════════════════════════════════════════════════════════

def draw_job_ring_paths(topo: TopoSpec, jobs_placement: dict[int, list[tuple[int, int]]],
                        out_path: Path, highlight_jobs: Optional[list[int]] = None,
                        title: str = "Job Ring AllReduce Network Paths"):
    """Show the Ring AllReduce ring paths for selected jobs on the topology."""
    if highlight_jobs is None:
        highlight_jobs = list(jobs_placement.keys())[:4]

    n_jobs = len(highlight_jobs)
    cols = min(2, n_jobs)
    rows = math.ceil(n_jobs / cols)

    cell_w, cell_h = 650, 480
    margin = 40
    width = cols * cell_w + margin * 2
    height = rows * cell_h + margin * 2 + 40

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        svg_text(width / 2, 22, title, 16, "middle", "700"),
    ]

    for ji, jid in enumerate(highlight_jobs):
        placement = jobs_placement.get(jid)
        if not placement: continue

        row, col = divmod(ji, cols)
        cx = margin + col * cell_w
        cy = margin + 50 + row * cell_h
        cw, ch = cell_w - 20, cell_h - 30

        job_color = JOB_COLORS[jid % len(JOB_COLORS)]
        parts.append(svg_text(cx + cw / 2, cy - 8, f"Job {jid}  ({len(placement)} ranks)", 13, "middle", "700", job_color))

        # Mini layout: arrange GPUs in a ring
        center_x = cx + cw / 2
        center_y = cy + ch / 2
        radius = min(cw, ch) / 2 - 50
        n = len(placement)

        # Position GPUs in a circle
        gpu_positions: dict[str, tuple[float, float]] = {}
        gpu_size = 18
        for i, (host, gpu_idx) in enumerate(placement):
            angle = 2 * math.pi * i / n - math.pi / 2
            gx = center_x + radius * math.cos(angle)
            gy = center_y + radius * math.sin(angle)
            gid = f"h{host}g{gpu_idx}"
            gpu_positions[gid] = (gx, gy)
            parts.append(svg_rect(gx - gpu_size / 2, gy - gpu_size / 2, gpu_size, gpu_size,
                                   job_color, 4, "#334155"))
            parts.append(svg_text(gx, gy + gpu_size / 2 + 4, f"{host}:{gpu_idx}", 7, "middle", "400", "#475569"))

        # Draw ring edges
        for i in range(n):
            h1, g1 = placement[i]
            h2, g2 = placement[(i + 1) % n]
            gid1 = f"h{h1}g{g1}"
            gid2 = f"h{h2}g{g2}"
            x1, y1 = gpu_positions.get(gid1, (0, 0))
            x2, y2 = gpu_positions.get(gid2, (0, 0))
            # Edge color: red for cross-host, green for same-host
            edge_color = "#ef4444" if h1 != h2 else "#22c55e"
            parts.append(svg_line(x1, y1, x2, y2, edge_color, 1.8, 0.7))

            # Compute route links
            route = compute_route_links(h1, g1, h2, g2, topo)
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2
            link_str = "→".join(route[:3]) + ("…" if len(route) > 3 else "")
            parts.append(svg_text(mid_x + 4, mid_y - 4, link_str, 6, "start", "400", "#94a3b8"))

        # Intra-host count
        intra = sum(1 for i in range(n) if placement[i][0] == placement[(i + 1) % n][0])
        parts.append(svg_text(cx + 10, cy + ch - 8,
                              f"intra-host hops: {intra}/{n}  |  cross-host hops: {n - intra}/{n}",
                              9, "start", "400", "#64748b"))

    parts.append("</svg>")
    out_path.write_text("\n".join(parts), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
# Chart: GPU occupancy Gantt
# ═══════════════════════════════════════════════════════════════

def draw_gpu_gantt(jobs_rows: list[dict[str, str]], topo: TopoSpec, out_path: Path,
                   scheduler: str = "random_same", title: str = "GPU Occupancy Gantt"):
    """Gantt chart: one row per GPU, colored by which job occupies it."""
    # Filter to one scheduler
    sched_rows = [r for r in jobs_rows if r["scheduler"] == scheduler]
    if not sched_rows:
        return

    n_gpus = topo.total_gpus
    bar_h = 10; gap = 2
    margin_l, margin_r, margin_t, margin_b = 90, 100, 50, 30
    width = 1200
    plot_w = width - margin_l - margin_r
    height = margin_t + margin_b + n_gpus * (bar_h + gap) + topo.hosts * 8

    # Find max time
    max_t = max(f(r, "sim_finish_s") for r in sched_rows) * 1.05
    max_t = max(max_t, 1.0)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        svg_text(width / 2, 22, f"{title} ({scheduler})", 15, "middle", "700"),
    ]

    # GPU timeline: for each GPU, show occupancy by job
    gpu_intervals: dict[str, list[tuple[float, float, int]]] = defaultdict(list)
    for r in sched_rows:
        jid = int(r["job_id"])
        placement_str = r.get("placement", r.get("rank_placement", ""))
        start = f(r, "sim_start_s")
        finish = f(r, "sim_finish_s")
        if not placement_str:
            continue
        for part in placement_str.split(";"):
            try:
                host, gpu = part.split(":")
                gid = f"h{host}g{gpu}"
                gpu_intervals[gid].append((start, finish, jid))
            except ValueError:
                pass

    # Layout GPUs in host-major order
    gpu_list: list[str] = []
    for h in range(topo.hosts):
        for g in range(topo.gpus_per_host):
            gpu_list.append(f"h{h}g{g}")

    y = margin_t
    for gi, gid in enumerate(gpu_list):
        # Host separator
        if gi > 0 and gi % topo.gpus_per_host == 0:
            y += 6
        intervals = sorted(gpu_intervals.get(gid, []), key=lambda x: x[0])
        parts.append(svg_text(6, y + bar_h, gid, 7, "start", "400", "#6b7280"))
        for t0, t1, jid in intervals:
            x0 = margin_l + t0 / max_t * plot_w
            x1 = margin_l + t1 / max_t * plot_w
            w = max(1, x1 - x0)
            color = JOB_COLORS[jid % len(JOB_COLORS)]
            parts.append(svg_rect(x0, y, w, bar_h, color, 1))
        y += bar_h + gap

    # Time axis
    for i in range(6):
        t = max_t * i / 5
        x = margin_l + t / max_t * plot_w
        parts.append(svg_text(x, y + 16, f"{t:.0f}s", 9, "middle", "400", "#64748b"))

    # Job legend
    used_jobs = sorted(set(int(r["job_id"]) for r in sched_rows))
    lx = width - 160; ly = 50
    parts.append(svg_text(lx, ly - 5, "Jobs", 10, "start", "700"))
    for i, jid in enumerate(used_jobs[:14]):
        color = JOB_COLORS[jid % len(JOB_COLORS)]
        parts.append(svg_rect(lx, ly + i * 16, 12, 10, color, 2))
        parts.append(svg_text(lx + 18, ly + i * 16 + 9, f"Job {jid}", 8, "start", "400", "#475569"))

    parts.append("</svg>")
    out_path.write_text("\n".join(parts), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
# Chart: Placement comparison (baseline vs target)
# ═══════════════════════════════════════════════════════════════

def draw_placement_compare(jobs_rows: list[dict[str, str]], topo: TopoSpec, out_path: Path,
                           baseline: str = "random_same", target: str = "crux_no_compress",
                           title: str = "Placement Comparison"):
    """Side-by-side GPU placement heatmap: baseline left, target right."""
    by_sched: dict[str, dict[int, list[tuple[int, int]]]] = {}
    for r in jobs_rows:
        sched = r["scheduler"]
        jid = int(r["job_id"])
        placement_str = r.get("placement", "")
        if not placement_str:
            continue
        placement: list[tuple[int, int]] = []
        for part in placement_str.split(";"):
            try:
                host, gpu = part.split(":")
                placement.append((int(host), int(gpu)))
            except ValueError:
                pass
        by_sched.setdefault(sched, {})[jid] = placement

    if baseline not in by_sched or target not in by_sched:
        print(f"  skip placement compare: need {baseline} and {target}")
        return

    base_place = by_sched[baseline]
    tgt_place = by_sched[target]
    all_jobs = sorted(set(base_place.keys()) & set(tgt_place.keys()))

    cell_size = 24; gap = 3
    host_gap = 10
    margin = 60
    label_w = 80
    side_w = label_w + topo.hosts * (topo.gpus_per_host * (cell_size + gap) + host_gap)
    width = margin * 2 + side_w * 2 + 40
    height = margin * 2 + len(all_jobs) * (cell_size + gap + 10)

    def draw_side(placement: dict[int, list[tuple[int, int]]], x_offset: float, sched_name: str):
        parts_local: list[str] = []
        parts_local.append(svg_text(x_offset + side_w / 2, 28, sched_name, 13, "middle", "700",
                                     SCHED_COLORS.get(sched_name, "#333")))
        for ji, jid in enumerate(all_jobs):
            y = margin + 40 + ji * (cell_size + gap + 10)
            parts_local.append(svg_text(x_offset + 4, y + cell_size / 2 + 4, f"Job {jid}", 9, "end", "400", "#64748b"))
            placed = placement.get(jid, [])
            gpu_to_job: dict[tuple[int, int], int] = {}
            for rank, (h, g) in enumerate(placed):
                gpu_to_job[(h, g)] = jid

            for h in range(topo.hosts):
                hx = x_offset + label_w + h * (topo.gpus_per_host * (cell_size + gap) + host_gap)
                for g in range(topo.gpus_per_host):
                    gx = hx + g * (cell_size + gap)
                    used = (h, g) in gpu_to_job
                    color = JOB_COLORS[jid % len(JOB_COLORS)] if used else "#f1f5f9"
                    stroke = "#334155" if used else "#e2e8f0"
                    parts_local.append(svg_rect(gx, y, cell_size, cell_size, color, 2, stroke))
            # Conciseness score: number of distinct hosts used
            distinct_hosts = len(set(h for h, _ in placed)) if placed else 0
            parts_local.append(svg_text(x_offset + side_w - 10, y + cell_size / 2 + 4,
                                        f"{distinct_hosts}h", 8, "end", "400", "#94a3b8"))
        return parts_local

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        svg_text(width / 2, 22, title, 16, "middle", "700"),
    ]

    parts += draw_side(base_place, margin, baseline)
    parts += draw_side(tgt_place, margin + side_w + 40, target)

    # Host label row
    hy = margin + 38
    for h in range(topo.hosts):
        for side_x in [margin, margin + side_w + 40]:
            hx = side_x + label_w + h * (topo.gpus_per_host * (cell_size + gap) + host_gap)
            cx = hx + topo.gpus_per_host * (cell_size + gap) / 2
            parts.append(svg_text(cx, hy, f"H{h}", 7, "middle", "400", "#94a3b8"))

    parts.append("</svg>")
    out_path.write_text("\n".join(parts), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="Network topology & job placement visualization")
    parser.add_argument("--jobs", type=Path, required=True, help="Job CSV (with placement column)")
    parser.add_argument("--links", type=Path, default=None, help="Link aggregate CSV")
    parser.add_argument("--topology", default="three_tier_clos", help="Topology name")
    parser.add_argument("--hosts", type=int, default=8)
    parser.add_argument("--gpus-per-host", type=int, default=4)
    parser.add_argument("--scheduler", default="random_same", help="Scheduler to visualize (for single-sched views)")
    parser.add_argument("--target", default="crux_no_compress")
    parser.add_argument("--baseline", default="random_same")
    parser.add_argument("--out-dir", type=Path, default=Path("results/vis_network"))
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    topo = make_topo_spec(args.topology, args.hosts, args.gpus_per_host)

    rows = read_csv(args.jobs)
    if not rows:
        print("ERROR: empty jobs CSV"); return

    # Parse placements per scheduler
    all_placements: dict[str, dict[int, list[tuple[int, int]]]] = {}
    for r in rows:
        sched = r["scheduler"]
        jid = int(r["job_id"])
        pstr_val = r.get("placement", "")
        if not pstr_val: continue
        placement: list[tuple[int, int]] = []
        for part in pstr_val.split(";"):
            try:
                host, gpu = part.split(":")
                placement.append((int(host), int(gpu)))
            except ValueError: pass
        all_placements.setdefault(sched, {})[jid] = placement

    # Parse link utilization
    link_util: dict[str, float] = {}
    if args.links and args.links.exists():
        lrows = read_csv(args.links)
        for lr in lrows:
            if lr.get("scheduler", args.scheduler) == args.scheduler:
                link_util[lr["link_name"]] = float(lr["utilization"])

    # 1. Topology map for each scheduler
    for sched in all_placements:
        if sched not in [args.baseline, args.target, args.scheduler]:
            continue
        print(f"  Topology map: {sched}")
        draw_topology_map(topo, all_placements[sched], link_util,
                          args.out_dir / f"topology_map_{sched}.svg",
                          f"Topology & Job Placement — {sched}")

    # 2. Link congestion
    if link_util:
        print("  Link congestion")
        draw_link_congestion(link_util, args.out_dir / "link_congestion.svg",
                             f"Link Utilization — {args.scheduler}")

    # 3. Job ring paths for target scheduler
    if args.target in all_placements:
        print(f"  Job ring paths: {args.target}")
        target_jobs = all_placements[args.target]
        # Pick top-4 highest intensity jobs (largest tensor size)
        job_intensity: dict[int, float] = {}
        for r in rows:
            if r["scheduler"] == args.target:
                job_intensity[int(r["job_id"])] = float(r["intensity"])
        highlight = sorted(target_jobs.keys(), key=lambda j: job_intensity.get(j, 0), reverse=True)[:4]
        draw_job_ring_paths(topo, target_jobs, args.out_dir / "job_ring_paths.svg",
                            highlight, f"Job Ring AllReduce Paths — {args.target}")

    # 4. GPU Gantt
    for sched in [args.baseline, args.target]:
        print(f"  GPU Gantt: {sched}")
        draw_gpu_gantt(rows, topo, args.out_dir / f"gpu_gantt_{sched}.svg",
                       sched, f"GPU Occupancy Timeline — {sched}")

    # 5. Placement comparison
    if args.baseline in all_placements and args.target in all_placements:
        print(f"  Placement compare: {args.baseline} vs {args.target}")
        draw_placement_compare(rows, topo, args.out_dir / "placement_compare.svg",
                               args.baseline, args.target,
                               f"GPU Placement: {args.baseline} vs {args.target}")

    print(f"\nVisualizations written to {args.out_dir}")


if __name__ == "__main__":
    main()
