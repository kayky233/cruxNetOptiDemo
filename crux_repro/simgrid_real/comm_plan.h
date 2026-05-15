#pragma once
#include <cmath>
#include <memory>
#include <string>
#include <vector>
#include "simgrid/s4u.hpp"

namespace sg4 = simgrid::s4u;

/// Abstract base for a collective communication plan.
/// Each plan defines how N ranks exchange a tensor of `tensor_bytes` bytes.
struct CommPlan {
  virtual ~CommPlan() = default;
  virtual std::string name() const = 0;

  /// Execute the collective for one training iteration.
  /// @param job_id      numeric job identifier
  /// @param rank        this rank's index [0, N)
  /// @param n_ranks     total ranks N
  /// @param tensor_bytes total bytes to allreduce
  /// @param send_rate   rate limit (-1 = unlimited)
  /// @param placement   rank → (host, gpu) mapping
  /// @param cfg         topology config (for link tracking)
  virtual void execute(int job_id, int rank, int n_ranks, uint64_t tensor_bytes,
                       double send_rate,
                       const std::vector<std::pair<int,int>>& placement,
                       const struct TopologyConfig& cfg) = 0;
};

// ─── RingPlan (Ring AllReduce) ──────────────────────────────────

struct RingPlan : CommPlan {
  std::string name() const override { return "ring"; }

  void execute(int job_id, int rank, int n_ranks, uint64_t tensor_bytes,
               double send_rate,
               const std::vector<std::pair<int,int>>& placement,
               const TopologyConfig& cfg) override
  {
    const std::string my_mbox = "job"+std::to_string(job_id)+"_rank"+std::to_string(rank);
    const uint64_t chunk = tensor_bytes / n_ranks;
    for (int step = 0; step < 2*(n_ranks-1); ++step) {
      int next = (rank+1)%n_ranks;
      const std::string next_mbox = "job"+std::to_string(job_id)+"_rank"+std::to_string(next);
      int* recvd = nullptr;
      auto recv = sg4::Mailbox::by_name(my_mbox)->get_async<int>(&recvd);
      auto send = sg4::Mailbox::by_name(next_mbox)->put_init(new int(step), chunk);
      if (send_rate > 0) send->set_rate(send_rate);
      send->start(); recv->wait(); send->wait();
      track_link_bytes(placement[rank].first, placement[next].first, chunk, cfg, job_id*97 + step*17 + rank);
      delete recvd;
    }
  }
};

// ─── TreePlan (Reduce + Broadcast) ──────────────────────────────

struct TreePlan : CommPlan {
  int radix = 2;  // tree fan-out
  std::string name() const override { return "tree_r"+std::to_string(radix); }

  void execute(int job_id, int rank, int n_ranks, uint64_t tensor_bytes,
               double send_rate,
               const std::vector<std::pair<int,int>>& placement,
               const TopologyConfig& cfg) override
  {
    const uint64_t chunk = tensor_bytes / n_ranks;
    auto tree_parent = [&](int r, int n) -> int { return (r-1)/radix; };
    auto tree_child_start = [&](int r, int n) -> int { return r*radix+1; };
    auto tree_child_end   = [&](int r, int n) -> int { return std::min(n, (r+1)*radix+1); };

    // reduce phase: leaves → root
    for (int level = 0; level < static_cast<int>(std::ceil(std::log2(n_ranks)/std::log2(radix))); ++level) {
      int parent = tree_parent(rank, n_ranks);
      int c_start = tree_child_start(rank, n_ranks);
      int c_end   = tree_child_end(rank, n_ranks);
      for (int c = c_start; c < c_end; ++c) {
        // receive from child c
        const std::string child_mbox = "job"+std::to_string(job_id)+"_rank"+std::to_string(c)+"_tree";
        int* rcv = nullptr;
        sg4::Mailbox::by_name(child_mbox)->get_async<int>(&rcv)->wait();
        track_link_bytes(placement[c].first, placement[rank].first, chunk, cfg);
        delete rcv;
      }
      if (parent >= 0) {
        // send to parent
        const std::string my_tree_mbox = "job"+std::to_string(job_id)+"_rank"+std::to_string(rank)+"_tree";
        auto s = sg4::Mailbox::by_name(my_tree_mbox)->put_init(new int(level), chunk);
        if (send_rate > 0) s->set_rate(send_rate);
        s->start(); s->wait();
      }
    }
    // barrier between reduce and broadcast
    sg4::this_actor::sleep_for(0);

    // broadcast phase: root → leaves
    for (int level = 0; level < static_cast<int>(std::ceil(std::log2(n_ranks)/std::log2(radix))); ++level) {
      int parent = tree_parent(rank, n_ranks);
      if (parent >= 0) {
        const std::string parent_mbox = "job"+std::to_string(job_id)+"_rank"+std::to_string(parent)+"_bcast";
        int* rcv = nullptr;
        sg4::Mailbox::by_name(parent_mbox)->get_async<int>(&rcv)->wait();
        track_link_bytes(placement[parent].first, placement[rank].first, chunk, cfg);
        delete rcv;
      }
      int c_start = tree_child_start(rank, n_ranks);
      int c_end   = tree_child_end(rank, n_ranks);
      for (int c = c_start; c < c_end; ++c) {
        const std::string my_bcast_mbox = "job"+std::to_string(job_id)+"_rank"+std::to_string(rank)+"_bcast";
        auto s = sg4::Mailbox::by_name(my_bcast_mbox)->put_init(new int(level), chunk);
        if (send_rate > 0) s->set_rate(send_rate);
        s->start(); s->wait();
      }
    }
  }
};

// ─── HierarchicalPlan (intra-node reduce → cross-node → intra-node bcast) ─

struct HierarchicalPlan : CommPlan {
  std::string name() const override { return "hierarchical"; }

  void execute(int job_id, int rank, int n_ranks, uint64_t tensor_bytes,
               double send_rate,
               const std::vector<std::pair<int,int>>& placement,
               const TopologyConfig& cfg) override
  {
    const uint64_t chunk = tensor_bytes / n_ranks;

    // group ranks by host
    std::map<int, std::vector<int>> host_ranks;
    for (int r = 0; r < n_ranks; ++r) host_ranks[placement[r].first].push_back(r);
    // pick one "leader" per host
    std::vector<int> leaders;
    for (auto& kv : host_ranks) leaders.push_back(kv.second[0]);
    int my_leader = leaders[0];
    for (auto& kv : host_ranks)
      for (int r : kv.second) if (r == rank) { my_leader = kv.second[0]; break; }
    bool is_leader = (rank == my_leader);
    int n_hosts = static_cast<int>(host_ranks.size());

    // Phase 1: intra-host ring-reduce → leader
    auto& local_ranks = host_ranks[placement[rank].first];
    int n_local = static_cast<int>(local_ranks.size());
    std::sort(local_ranks.begin(), local_ranks.end());
    int local_pos = -1;
    for (int i = 0; i < n_local; ++i) if (local_ranks[i] == rank) { local_pos = i; break; }
    if (n_local > 1) {
      for (int step = 0; step < n_local-1; ++step) {
        int next_local = local_ranks[(local_pos+1)%n_local];
        const std::string mbox = "job"+std::to_string(job_id)+"_intra_"+std::to_string(next_local);
        if (step == n_local-2 && is_leader) {
          int* rcv = nullptr;
          sg4::Mailbox::by_name(mbox)->get_async<int>(&rcv)->wait();
          track_link_bytes(placement[next_local].first, placement[rank].first, chunk, cfg);
          delete rcv;
        } else {
          auto s = sg4::Mailbox::by_name(mbox)->put_init(new int(step), chunk);
          if (send_rate > 0) s->set_rate(send_rate);
          s->start(); s->wait();
        }
      }
    }

    // Phase 2: cross-host ring among leaders
    if (n_hosts > 1) {
      int leader_pos = -1;
      for (int i = 0; i < n_hosts; ++i) if (leaders[i] == my_leader) { leader_pos = i; break; }
      for (int step = 0; step < n_hosts-1; ++step) {
        int next_leader = leaders[(leader_pos+1)%n_hosts];
        const std::string mbox = "job"+std::to_string(job_id)+"_cross_"+std::to_string(next_leader);
        if (is_leader) {
          int* rcv = nullptr;
          auto recv = sg4::Mailbox::by_name(mbox)->get_async<int>(&rcv);
          auto send = sg4::Mailbox::by_name(mbox)->put_init(new int(step), chunk);
          if (send_rate > 0) send->set_rate(send_rate);
          send->start(); recv->wait(); send->wait();
          track_link_bytes(placement[leaders[leader_pos]].first, placement[next_leader].first, chunk, cfg);
          delete rcv;
        }
      }
    }

    // Phase 3: intra-host broadcast from leader
    if (n_local > 1) {
      if (is_leader) {
        for (int i = 1; i < n_local; ++i) {
          int target = local_ranks[i];
          const std::string mbox = "job"+std::to_string(job_id)+"_bcast_"+std::to_string(target);
          auto s = sg4::Mailbox::by_name(mbox)->put_init(new int(0), chunk);
          if (send_rate > 0) s->set_rate(send_rate);
          s->start(); s->wait();
        }
      } else {
        const std::string mbox = "job"+std::to_string(job_id)+"_bcast_"+std::to_string(rank);
        int* rcv = nullptr;
        sg4::Mailbox::by_name(mbox)->get_async<int>(&rcv)->wait();
        track_link_bytes(placement[my_leader].first, placement[rank].first, chunk, cfg);
        delete rcv;
      }
    }
  }
};

// ─── PipelinePlan (split tensor into K chunks, pipeline) ────────

struct PipelinePlan : CommPlan {
  int pipeline_depth = 4;
  std::string name() const override { return "pipeline_d"+std::to_string(pipeline_depth); }

  void execute(int job_id, int rank, int n_ranks, uint64_t tensor_bytes,
               double send_rate,
               const std::vector<std::pair<int,int>>& placement,
               const TopologyConfig& cfg) override
  {
    const uint64_t chunk = tensor_bytes / n_ranks / pipeline_depth;
    for (int p = 0; p < pipeline_depth + n_ranks - 1; ++p) {
      int step_in_pipe = p - rank;
      if (step_in_pipe >= 0 && step_in_pipe < pipeline_depth) {
        int next = (rank+1)%n_ranks;
        const std::string next_mbox = "job"+std::to_string(job_id)+"_rank"+std::to_string(next)+"_p"+std::to_string(step_in_pipe);
        int* recvd = nullptr;
        auto recv = sg4::Mailbox::by_name("job"+std::to_string(job_id)+"_rank"+std::to_string(rank)+"_p"+std::to_string(step_in_pipe))->get_async<int>(&recvd);
        auto send = sg4::Mailbox::by_name(next_mbox)->put_init(new int(step_in_pipe), chunk);
        if (send_rate > 0) send->set_rate(send_rate);
        send->start(); recv->wait(); send->wait();
        track_link_bytes(placement[rank].first, placement[next].first, chunk, cfg);
        delete recvd;
      }
    }
    // second pass for AllGather half
    for (int p = 0; p < pipeline_depth + n_ranks - 1; ++p) {
      int step_in_pipe = p - rank;
      if (step_in_pipe >= 0 && step_in_pipe < pipeline_depth) {
        int next = (rank+1)%n_ranks;
        const std::string next_mbox = "job"+std::to_string(job_id)+"_rank"+std::to_string(next)+"_ag_p"+std::to_string(step_in_pipe);
        int* recvd = nullptr;
        auto recv = sg4::Mailbox::by_name("job"+std::to_string(job_id)+"_rank"+std::to_string(rank)+"_ag_p"+std::to_string(step_in_pipe))->get_async<int>(&recvd);
        auto send = sg4::Mailbox::by_name(next_mbox)->put_init(new int(step_in_pipe), chunk);
        if (send_rate > 0) send->set_rate(send_rate);
        send->start(); recv->wait(); send->wait();
        track_link_bytes(placement[rank].first, placement[next].first, chunk, cfg);
        delete recvd;
      }
    }
  }
};

// ─── factory ────────────────────────────────────────────────────

inline std::unique_ptr<CommPlan> make_comm_plan(const std::string& name) {
  if (name == "ring")         return std::make_unique<RingPlan>();
  if (name == "tree")         return std::make_unique<TreePlan>();
  if (name == "hierarchical") return std::make_unique<HierarchicalPlan>();
  if (name == "pipeline")     return std::make_unique<PipelinePlan>();
  throw std::runtime_error("Unknown comm plan: "+name);
}
