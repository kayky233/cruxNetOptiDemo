#pragma once
#include <map>
#include <string>
#include <vector>
#include <cmath>

namespace sg4 = simgrid::s4u;

/// Bandwidth/latency specification for a single link type.
struct LinkParams {
  double bandwidth_bps;   // bytes per second
  double latency_s;
};

/// One level in a switch hierarchy (ToR, aggregation, core, etc.).
struct SwitchLevel {
  int count;
  double uplink_bps;    // bytes/sec per uplink
  double latency_s;
};

/// Describes a multi-node multi-GPU cluster topology.
struct TopologyConfig {
  std::string name;
  int hosts;
  int gpus_per_host;
  double gpu_speed_flops;   // host speed in flops

  // intra-host
  double local_bps;
  double local_lat_s;

  // NIC
  int nics_per_host;
  double nic_bps;
  double nic_lat_s;

  // switch levels (ToR=0, aggregation=1, core=2, ...)
  std::vector<SwitchLevel> switches;
};

// ─── preset factories ───────────────────────────────────────────

inline TopologyConfig make_star(int hosts, int gpus_per_host,
                                double local_gbps, double nic_gbps, double core_gbps)
{
  TopologyConfig c;
  c.name = "star";
  c.hosts = hosts;
  c.gpus_per_host = gpus_per_host;
  c.gpu_speed_flops = 200e12;
  c.local_bps = local_gbps * 1e9 / 8.0;
  c.local_lat_s = 1e-6;
  c.nics_per_host = 1;
  c.nic_bps = nic_gbps * 1e9 / 8.0;
  c.nic_lat_s = 2e-6;
  // single shared core switch
  c.switches = {{1, core_gbps * 1e9 / 8.0, 4e-6}};
  return c;
}

inline TopologyConfig make_fat_tree(int hosts, int gpus_per_host)
{
  TopologyConfig c;
  c.name = "fat_tree";
  c.hosts = hosts;
  c.gpus_per_host = gpus_per_host;
  c.gpu_speed_flops = 200e12;
  c.local_bps = 600e9 / 8.0;
  c.local_lat_s = 1e-6;
  c.nics_per_host = 1;
  c.nic_bps = 100e9 / 8.0;
  c.nic_lat_s = 2e-6;
  // two-level fat-tree: 4 ToR switches + 2 spine switches
  c.switches = {
    {4, 200e9 / 8.0, 3e-6},   // ToR
    {2, 400e9 / 8.0, 5e-6},   // Spine
  };
  return c;
}

inline TopologyConfig make_three_tier_clos(int hosts, int gpus_per_host)
{
  TopologyConfig c;
  c.name = "three_tier_clos";
  c.hosts = hosts;
  c.gpus_per_host = gpus_per_host;
  c.gpu_speed_flops = 200e12;
  c.local_bps = 600e9 / 8.0;
  c.local_lat_s = 1e-6;
  c.nics_per_host = 1;
  c.nic_bps = 100e9 / 8.0;
  c.nic_lat_s = 2e-6;
  // ToR → Aggregation → Spine
  c.switches = {
    {8,  200e9 / 8.0, 3e-6},   // ToR
    {4,  400e9 / 8.0, 5e-6},   // Aggregation
    {2,  800e9 / 8.0, 8e-6},   // Spine/Core
  };
  return c;
}

inline TopologyConfig make_dragonfly(int hosts, int gpus_per_host)
{
  TopologyConfig c;
  c.name = "dragonfly";
  c.hosts = hosts;
  c.gpus_per_host = gpus_per_host;
  c.gpu_speed_flops = 200e12;
  c.local_bps = 600e9 / 8.0;
  c.local_lat_s = 1e-6;
  c.nics_per_host = 1;
  c.nic_bps = 100e9 / 8.0;
  c.nic_lat_s = 2e-6;
  // groups with local switches + global links
  c.switches = {
    {4, 200e9 / 8.0, 3e-6},    // group-local
    {2, 400e9 / 8.0, 8e-6},    // global inter-group
  };
  return c;
}

// ─── 昇腾 Ascend cluster (HCCS + PCIe + RoCE + Leaf-Spine) ─────
// Models a realistic 昇腾 910B/920 training cluster with:
//   - 8 NPU per server, connected via HCCS full-mesh (~400 GB/s per link)
//   - Dual 200G RoCE NIC per server (each NIC serves 4 NPU via PCIe switch)
//   - Leaf-Spine fabric with 2:1 oversubscription

inline TopologyConfig make_ascend_cluster(int hosts=8, int gpus_per_host=8)
{
  TopologyConfig c;
  c.name = "ascend";
  c.hosts = hosts;
  c.gpus_per_host = gpus_per_host;

  // 昇腾 910B: ~256 TFLOPS (FP16), 折算 ~250e12 flops
  c.gpu_speed_flops = 250e12;

  // ── HCCS interconnect (intra-server NPU-to-NPU) ────────────────
  // 昇腾 HCCS: ~56 GB/s per lane, 8 NPU full-mesh effective ~400 GB/s aggregate
  // B/s = GB/s * 1e9
  c.local_bps = 400e9;       // 400 GB/s HCCS aggregate bandwidth
  c.local_lat_s = 0.5e-6;   // ~0.5 μs HCCS latency (on-die/interposer)

  // ── NIC (RoCE) ─────────────────────────────────────────────────
  // Dual-port 200G RoCE NIC per server
  c.nics_per_host = 2;
  c.nic_bps = 200e9 / 8.0;  // 200 Gbps per NIC → 25 GB/s
  c.nic_lat_s = 2e-6;       // ~2 μs NIC + PCIe latency

  // ── Leaf-Spine fabric ──────────────────────────────────────────
  // 8 Leaf (ToR) switches, each connecting 1 server (满配可接 32+)
  // 4 Spine switches
  // Oversubscription ratio: Leaf→Spine 2:1
  // Latency: Leaf ~3μs, Spine ~5μs
  c.switches = {
    {hosts, 400e9 / 8.0, 3e-6},   // Leaf/ToR: 400 Gbps uplink each
    {4,     800e9 / 8.0, 5e-6},   // Spine:    800 Gbps uplink each
  };
  return c;
}

// ─── link-usage tracker ─────────────────────────────────────────

struct LinkUsage {
  double total_bytes = 0.0;
  double peak_active_bytes = 0.0;   // max concurrent bytes in flight
  double peak_time = 0.0;
  double bandwidth_bps = 0.0;
  double utilization() const {
    if (bandwidth_bps <= 0) return 0.0;
    double makespan = sg4::Engine::get_clock();
    if (makespan <= 0) return 0.0;
    return total_bytes / (bandwidth_bps * makespan);
  }
};

inline std::map<std::string, LinkUsage> g_link_usage;

inline void track_link_bytes(int src_host, int dst_host, uint64_t bytes, const TopologyConfig& cfg, int salt = 0) {
  if (src_host == dst_host) {
    g_link_usage["local"+std::to_string(src_host)].total_bytes += bytes;
  } else {
    g_link_usage["nic"+std::to_string(src_host)+"_0"].total_bytes += bytes;
    g_link_usage["nic"+std::to_string(dst_host)+"_0"].total_bytes += bytes;
    for (size_t lvl = 0; lvl < cfg.switches.size(); ++lvl) {
      int idx = (src_host*31 + dst_host*17 + static_cast<int>(lvl)*7 + salt*13) % cfg.switches[lvl].count;
      g_link_usage["sw"+std::to_string(lvl)+"_"+std::to_string(idx)].total_bytes += bytes;
    }
  }
}
