"""Data loading and topology configuration.

Reads the CSV files produced by collective_sim.cpp and defines
topology configs matching topology.h presets.
"""

import pandas as pd
from dataclasses import dataclass, field
from typing import List, Optional

# ── topology config (matches simgrid_real/topology.h) ────────────────

@dataclass
class SwitchLevel:
    count: int
    uplink_gbps: float   # Gbps per uplink
    latency_us: float    # microseconds

@dataclass
class TopologyConfig:
    name: str
    hosts: int
    gpus_per_host: int
    local_gbps: float
    nic_gbps: float
    local_lat_us: float = 1.0
    nic_lat_us: float = 2.0
    nics_per_host: int = 1
    switches: List[SwitchLevel] = field(default_factory=list)

    @property
    def switch_counts(self) -> List[int]:
        return [s.count for s in self.switches]

    @property
    def switch_names(self) -> List[str]:
        """Per-level switch names matching collective_sim.cpp: sw0_0, sw1_0, ..."""
        names = []
        for lvl, sw in enumerate(self.switches):
            for idx in range(sw.count):
                names.append(f"sw{lvl}_{idx}")
        return names


def make_star(hosts=8, gpus_per_host=4, local_gbps=400, nic_gbps=100, core_gbps=320):
    return TopologyConfig(
        name="star",
        hosts=hosts, gpus_per_host=gpus_per_host,
        local_gbps=local_gbps, nic_gbps=nic_gbps,
        switches=[SwitchLevel(count=1, uplink_gbps=core_gbps, latency_us=4.0)],
    )


def make_fat_tree(hosts=8, gpus_per_host=4):
    return TopologyConfig(
        name="fat_tree",
        hosts=hosts, gpus_per_host=gpus_per_host,
        local_gbps=600, nic_gbps=100,
        switches=[
            SwitchLevel(count=4, uplink_gbps=200, latency_us=3.0),
            SwitchLevel(count=2, uplink_gbps=400, latency_us=5.0),
        ],
    )


def make_three_tier_clos(hosts=8, gpus_per_host=4):
    return TopologyConfig(
        name="three_tier_clos",
        hosts=hosts, gpus_per_host=gpus_per_host,
        local_gbps=600, nic_gbps=100,
        switches=[
            SwitchLevel(count=8, uplink_gbps=200, latency_us=3.0),
            SwitchLevel(count=4, uplink_gbps=400, latency_us=5.0),
            SwitchLevel(count=2, uplink_gbps=800, latency_us=8.0),
        ],
    )


def make_dragonfly(hosts=8, gpus_per_host=4):
    return TopologyConfig(
        name="dragonfly",
        hosts=hosts, gpus_per_host=gpus_per_host,
        local_gbps=600, nic_gbps=100,
        switches=[
            SwitchLevel(count=4, uplink_gbps=200, latency_us=3.0),
            SwitchLevel(count=2, uplink_gbps=400, latency_us=8.0),
        ],
    )


def make_ascend(hosts=8, gpus_per_host=8):
    return TopologyConfig(
        name="ascend",
        hosts=hosts, gpus_per_host=gpus_per_host,
        local_gbps=400 * 8, nic_gbps=200,
        local_lat_us=0.5, nic_lat_us=2.0,
        nics_per_host=2,
        switches=[
            SwitchLevel(count=hosts, uplink_gbps=400, latency_us=3.0),
            SwitchLevel(count=4, uplink_gbps=800, latency_us=5.0),
        ],
    )


TOPOLOGY_BUILDERS = {
    "star":             make_star,
    "fat_tree":         make_fat_tree,
    "three_tier_clos":  make_three_tier_clos,
    "dragonfly":        make_dragonfly,
    "ascend":           make_ascend,
}


def load_topology(name="three_tier_clos", hosts=8, gpus_per_host=4, **kwargs):
    builder = TOPOLOGY_BUILDERS.get(name)
    if builder is None:
        raise ValueError(f"Unknown topology: {name}. Options: {list(TOPOLOGY_BUILDERS.keys())}")
    return builder(hosts=hosts, gpus_per_host=gpus_per_host, **kwargs)


# ── CSV readers ──────────────────────────────────────────────────────

def load_results(path: str) -> pd.DataFrame:
    """Load scheduler-level results CSV (one row per scheduler)."""
    return pd.read_csv(path)


def load_jobs(path: str) -> pd.DataFrame:
    """Load job-level CSV (one row per job per scheduler)."""
    return pd.read_csv(path)


def load_workload(path: str) -> pd.DataFrame:
    """Load trace workload CSV (job_id, model, ranks, compute_s, tensor_gib, ...)."""
    return pd.read_csv(path)


def load_links(path: str) -> Optional[pd.DataFrame]:
    """Load link-out CSV (link_name, bandwidth_bps, total_bytes, utilization, makespan_s)."""
    try:
        return pd.read_csv(path)
    except FileNotFoundError:
        return None


# ── derived data ─────────────────────────────────────────────────────

def get_scheduler_jobs(jobs_df: pd.DataFrame, scheduler: str) -> pd.DataFrame:
    """Filter jobs DataFrame to a single scheduler."""
    return jobs_df[jobs_df["scheduler"] == scheduler].copy()


def get_baseline_crux(jobs_df: pd.DataFrame,
                       baseline="random_same",
                       crux="crux_no_compress"):
    """Return (baseline_df, crux_df) for the two schedulers of interest."""
    b = jobs_df[jobs_df["scheduler"] == baseline].copy()
    c = jobs_df[jobs_df["scheduler"] == crux].copy()
    return b, c
