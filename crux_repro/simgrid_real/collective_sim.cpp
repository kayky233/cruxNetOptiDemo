#include <algorithm>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <numeric>
#include <random>
#include <sstream>
#include <string>
#include <vector>

#include "simgrid/s4u.hpp"

namespace sg4 = simgrid::s4u;

struct Options {
  std::string scheduler = "random_same";
  std::string out = "";
  std::string job_out = "";
  std::string workload_csv = "";
  std::string placement_mode = "replay";
  std::string placement_objective = "throughput";
  int hosts = 8;
  int gpus_per_host = 4;
  int jobs = 12;
  int ranks = 8;
  int rounds = 4;
  int seed = 7;
  double gpu_tflops = 200.0;
  double local_gbps = 400.0;
  double nic_gbps = 100.0;
  double core_gbps = 320.0;
};

struct RankPlacement {
  int host = 0;
  int gpu = 0;
};

struct Job {
  int id = 0;
  int ranks = 0;
  double compute_s = 0;
  double tensor_bytes = 0;
  double intensity = 0;
  double start_s = 0;
  std::string model = "synthetic";
  std::vector<RankPlacement> placement;
};

struct JobMetrics {
  std::vector<double> start;
  std::vector<double> finish;
  std::vector<double> comm;
};

static Options parse_args(int argc, char** argv)
{
  Options opt;
  for (int i = 1; i < argc; ++i) {
    std::string k = argv[i];
    auto need_value = [&](const std::string& name) {
      if (i + 1 >= argc)
        throw std::runtime_error("Missing value for " + name);
      return std::string(argv[++i]);
    };
    if (k == "--scheduler")
      opt.scheduler = need_value(k);
    else if (k == "--out")
      opt.out = need_value(k);
    else if (k == "--job-out")
      opt.job_out = need_value(k);
    else if (k == "--workload-csv")
      opt.workload_csv = need_value(k);
    else if (k == "--placement-mode")
      opt.placement_mode = need_value(k);
    else if (k == "--placement-objective")
      opt.placement_objective = need_value(k);
    else if (k == "--hosts")
      opt.hosts = std::stoi(need_value(k));
    else if (k == "--gpus-per-host")
      opt.gpus_per_host = std::stoi(need_value(k));
    else if (k == "--jobs")
      opt.jobs = std::stoi(need_value(k));
    else if (k == "--ranks")
      opt.ranks = std::stoi(need_value(k));
    else if (k == "--rounds")
      opt.rounds = std::stoi(need_value(k));
    else if (k == "--seed")
      opt.seed = std::stoi(need_value(k));
    else if (k == "--local-gbps")
      opt.local_gbps = std::stod(need_value(k));
    else if (k == "--nic-gbps")
      opt.nic_gbps = std::stod(need_value(k));
    else if (k == "--core-gbps")
      opt.core_gbps = std::stod(need_value(k));
    else
      throw std::runtime_error("Unknown argument: " + k);
  }
  return opt;
}

static std::string gpu_name(int host, int gpu)
{
  return "h" + std::to_string(host) + "g" + std::to_string(gpu);
}

static void build_platform(sg4::Engine& engine, const Options& opt)
{
  auto* zone = engine.get_netzone_root()->add_netzone_full("cluster");
  std::vector<std::vector<const sg4::Host*>> gpus(opt.hosts);
  for (int h = 0; h < opt.hosts; ++h) {
    for (int g = 0; g < opt.gpus_per_host; ++g) {
      auto* host = zone->add_host(gpu_name(h, g), opt.gpu_tflops * 1e12)->set_core_count(1);
      gpus[h].push_back(host);
    }
  }

  const sg4::Link* core = zone->add_link("core", opt.core_gbps * 1e9 / 8.0)->set_latency(4e-6);
  std::vector<const sg4::Link*> nic;
  std::vector<const sg4::Link*> local;
  for (int h = 0; h < opt.hosts; ++h) {
    nic.push_back(zone->add_link("nic" + std::to_string(h), opt.nic_gbps * 1e9 / 8.0)->set_latency(2e-6));
    local.push_back(zone->add_link("local" + std::to_string(h), opt.local_gbps * 1e9 / 8.0)->set_latency(1e-6));
  }

  for (int h1 = 0; h1 < opt.hosts; ++h1) {
    for (int g1 = 0; g1 < opt.gpus_per_host; ++g1) {
      for (int h2 = h1; h2 < opt.hosts; ++h2) {
        for (int g2 = 0; g2 < opt.gpus_per_host; ++g2) {
          if (h1 == h2 && g1 >= g2)
            continue;
          if (h1 == h2)
            zone->add_route(gpus[h1][g1], gpus[h2][g2], {local[h1]});
          else
            zone->add_route(gpus[h1][g1], gpus[h2][g2], {nic[h1], core, nic[h2]});
        }
      }
    }
  }
  zone->seal();
}

static std::vector<Job> make_jobs(const Options& opt)
{
  std::mt19937 rng(opt.seed);
  std::uniform_real_distribution<double> hi_compute(0.28, 0.50);
  std::uniform_real_distribution<double> hi_tensor(7.0, 12.0);
  std::uniform_real_distribution<double> lo_compute(1.05, 1.75);
  std::uniform_real_distribution<double> lo_tensor(0.4, 1.6);

  std::vector<Job> jobs;
  for (int j = 0; j < opt.jobs; ++j) {
    const bool high = (j % 3) != 2;
    Job job;
    job.id = j;
    job.ranks = opt.ranks;
    job.compute_s = high ? hi_compute(rng) : lo_compute(rng);
    job.tensor_bytes = (high ? hi_tensor(rng) : lo_tensor(rng)) * 1024.0 * 1024.0 * 1024.0;
    job.intensity = job.tensor_bytes / job.compute_s;
    jobs.push_back(job);
  }
  return jobs;
}

static std::vector<std::string> split(const std::string& text, char delim)
{
  std::vector<std::string> out;
  std::stringstream ss(text);
  std::string item;
  while (std::getline(ss, item, delim)) {
    while (!item.empty() && (item.back() == '\r' || item.back() == '\n' || item.back() == ' '))
      item.pop_back();
    size_t start = 0;
    while (start < item.size() && item[start] == ' ')
      ++start;
    if (start > 0)
      item.erase(0, start);
    out.push_back(item);
  }
  return out;
}

static int column_index(const std::vector<std::string>& header, const std::string& name)
{
  auto it = std::find(header.begin(), header.end(), name);
  if (it == header.end())
    throw std::runtime_error("workload csv is missing column: " + name);
  return static_cast<int>(std::distance(header.begin(), it));
}

static std::vector<Job> read_workload_csv(const Options& opt)
{
  std::ifstream f(opt.workload_csv);
  if (!f)
    throw std::runtime_error("cannot open workload csv: " + opt.workload_csv);

  std::string line;
  if (!std::getline(f, line))
    throw std::runtime_error("empty workload csv: " + opt.workload_csv);
  const auto header = split(line, ',');
  const int c_job_id = column_index(header, "job_id");
  const int c_model = column_index(header, "model");
  const int c_start_s = column_index(header, "start_s");
  const int c_ranks = column_index(header, "ranks");
  const int c_compute_s = column_index(header, "compute_s");
  const int c_tensor_gib = column_index(header, "tensor_gib");
  const int c_hosts = column_index(header, "hosts");

  std::vector<Job> jobs;
  while (std::getline(f, line)) {
    if (line.empty())
      continue;
    const auto cols = split(line, ',');
    if (static_cast<int>(cols.size()) <= std::max({c_job_id, c_model, c_start_s, c_ranks, c_compute_s, c_tensor_gib, c_hosts}))
      throw std::runtime_error("malformed workload csv row: " + line);
    Job job;
    job.id = std::stoi(cols[c_job_id]);
    job.model = cols[c_model];
    job.start_s = std::stod(cols[c_start_s]);
    job.ranks = std::max(2, std::stoi(cols[c_ranks]));
    job.ranks = std::min(job.ranks, opt.hosts * opt.gpus_per_host);
    job.compute_s = std::stod(cols[c_compute_s]);
    job.tensor_bytes = std::stod(cols[c_tensor_gib]) * 1024.0 * 1024.0 * 1024.0;
    job.intensity = job.tensor_bytes / std::max(1e-9, job.compute_s);

    const auto host_tokens = split(cols[c_hosts], ';');
    if (host_tokens.empty())
      throw std::runtime_error("workload row has no hosts: " + line);
    for (int r = 0; r < job.ranks; ++r) {
      const int trace_host = std::stoi(host_tokens[r % host_tokens.size()]);
      const int h = ((trace_host % opt.hosts) + opt.hosts) % opt.hosts;
      const int g = (r / static_cast<int>(host_tokens.size())) % opt.gpus_per_host;
      job.placement.push_back({h, g});
    }
    jobs.push_back(job);
  }
  if (jobs.empty())
    throw std::runtime_error("workload csv produced no jobs: " + opt.workload_csv);
  return jobs;
}

static std::vector<int> job_order(const std::vector<Job>& jobs, bool intensity_first)
{
  std::vector<int> ids(jobs.size());
  std::iota(ids.begin(), ids.end(), 0);
  if (intensity_first) {
    std::sort(ids.begin(), ids.end(), [&](int a, int b) { return jobs[a].intensity > jobs[b].intensity; });
  }
  return ids;
}

static void place_jobs(std::vector<Job>& jobs, const Options& opt)
{
  const int total_gpus = opt.hosts * opt.gpus_per_host;
  const bool crux_place = opt.scheduler == "crux" || opt.scheduler == "crux_no_compress";
  const double gpu_balance_weight = opt.placement_objective == "balanced" ? 3.0 : 0.25;
  std::vector<double> intensities;
  for (const auto& job : jobs)
    intensities.push_back(job.intensity);
  std::sort(intensities.begin(), intensities.end());
  const double high_intensity_threshold = intensities.empty() ? 5.0e9 : intensities[intensities.size() / 2];
  auto order = job_order(jobs, crux_place);
  std::vector<double> host_load(opt.hosts, 0.0);
  std::vector<double> gpu_load(total_gpus, 0.0);
  auto least_loaded_gpu_on_host = [&](int host) {
    int best_gpu = 0;
    double best_load = std::numeric_limits<double>::infinity();
    for (int g = 0; g < opt.gpus_per_host; ++g) {
      const int idx = host * opt.gpus_per_host + g;
      if (gpu_load[idx] < best_load) {
        best_load = gpu_load[idx];
        best_gpu = g;
      }
    }
    return best_gpu;
  };
  for (size_t pos = 0; pos < order.size(); ++pos) {
    Job& job = jobs[order[pos]];
    job.placement.clear();
    std::vector<int> chosen_hosts;
    for (int r = 0; r < job.ranks; ++r) {
      int idx = 0;
      if (crux_place) {
        if (job.intensity >= high_intensity_threshold) {
          const int hosts_needed = std::max(1, static_cast<int>(std::ceil(job.ranks / static_cast<double>(opt.gpus_per_host))));
          if (chosen_hosts.empty()) {
            double best_score = std::numeric_limits<double>::infinity();
            int best_base = 0;
            for (int base = 0; base < opt.hosts; ++base) {
              double score = 0.0;
              for (int k = 0; k < hosts_needed; ++k) {
                const int h = (base + k) % opt.hosts;
                score += host_load[h];
                for (int g = 0; g < opt.gpus_per_host; ++g)
                  score += gpu_balance_weight * gpu_load[h * opt.gpus_per_host + g];
              }
              if (score < best_score) {
                best_score = score;
                best_base = base;
              }
            }
            for (int k = 0; k < hosts_needed; ++k)
              chosen_hosts.push_back((best_base + k) % opt.hosts);
          }
          const int h = chosen_hosts[(r / opt.gpus_per_host) % chosen_hosts.size()];
          const int g = least_loaded_gpu_on_host(h);
          idx = h * opt.gpus_per_host + g;
        } else {
          int h = 0;
          int g = 0;
          double best_score = std::numeric_limits<double>::infinity();
          for (int cand_h = 0; cand_h < opt.hosts; ++cand_h) {
            const int cand_g = least_loaded_gpu_on_host(cand_h);
            const double score = host_load[cand_h] + gpu_balance_weight * gpu_load[cand_h * opt.gpus_per_host + cand_g];
            if (score < best_score) {
              best_score = score;
              h = cand_h;
              g = cand_g;
            }
          }
          idx = h * opt.gpus_per_host + g;
        }
      } else {
        idx = (job.id * 7 + r * 3) % total_gpus;
      }
      job.placement.push_back({idx / opt.gpus_per_host, idx % opt.gpus_per_host});
      host_load[idx / opt.gpus_per_host] += job.intensity / static_cast<double>(std::max(1, job.ranks));
      gpu_load[idx] += job.compute_s + job.tensor_bytes / 1e10;
    }
  }
}

static void validate_options(const Options& opt)
{
  if (opt.placement_mode != "replay" && opt.placement_mode != "optimize")
    throw std::runtime_error("--placement-mode must be replay or optimize");
  if (opt.placement_objective != "throughput" && opt.placement_objective != "balanced")
    throw std::runtime_error("--placement-objective must be throughput or balanced");
  if (opt.workload_csv.empty() && opt.placement_mode == "replay")
    return;
}

static double rate_limit(const Options& opt, const Job& job)
{
  if (opt.scheduler == "random_same" || opt.scheduler == "crux_no_compress")
    return -1.0;
  const double base = opt.nic_gbps * 1e9 / 8.0;
  if (opt.scheduler == "random_intensity")
    return job.intensity > 5.0e9 ? -1.0 : base * 0.65;
  if (opt.scheduler == "crux")
    return job.intensity > 5.0e9 ? -1.0 : base * 0.40;
  return -1.0;
}

static std::string placement_string(const Job& job)
{
  std::ostringstream ss;
  for (size_t i = 0; i < job.placement.size(); ++i) {
    if (i > 0)
      ss << ";";
    ss << job.placement[i].host << ":" << job.placement[i].gpu;
  }
  return ss.str();
}

static void rank_actor(std::shared_ptr<Job> job, std::shared_ptr<JobMetrics> metrics, int rank, int rounds,
                       double gpu_tflops, double send_rate)
{
  const std::string my_mbox = "job" + std::to_string(job->id) + "_rank" + std::to_string(rank);
  const int n = job->ranks;
  const double flops = job->compute_s * gpu_tflops * 1e12;
  const uint64_t chunk = static_cast<uint64_t>(job->tensor_bytes / static_cast<double>(n));

  if (job->start_s > 0)
    sg4::this_actor::sleep_until(job->start_s);

  metrics->start[rank] = sg4::Engine::get_clock();
  for (int round = 0; round < rounds; ++round) {
    sg4::this_actor::execute(flops);
    const double comm_begin = sg4::Engine::get_clock();
    for (int step = 0; step < 2 * (n - 1); ++step) {
      const int next = (rank + 1) % n;
      const std::string next_mbox = "job" + std::to_string(job->id) + "_rank" + std::to_string(next);
      int* received = nullptr;
      auto recv = sg4::Mailbox::by_name(my_mbox)->get_async<int>(&received);
      auto send = sg4::Mailbox::by_name(next_mbox)->put_init(new int(step), chunk);
      if (send_rate > 0)
        send->set_rate(send_rate);
      send->start();
      recv->wait();
      send->wait();
      delete received;
    }
    metrics->comm[rank] += sg4::Engine::get_clock() - comm_begin;
  }
  metrics->finish[rank] = sg4::Engine::get_clock();
}

int main(int argc, char** argv)
{
  try {
    auto opt = parse_args(argc, argv);
    validate_options(opt);
    sg4::Engine engine(&argc, argv);
    build_platform(engine, opt);

    auto jobs = opt.workload_csv.empty() ? make_jobs(opt) : read_workload_csv(opt);
    if (opt.workload_csv.empty() || opt.placement_mode == "optimize")
      place_jobs(jobs, opt);

    std::vector<std::shared_ptr<JobMetrics>> all_metrics;
    for (const auto& job_value : jobs) {
      auto job = std::make_shared<Job>(job_value);
      auto metrics = std::make_shared<JobMetrics>();
      metrics->start.assign(job->ranks, 0.0);
      metrics->finish.assign(job->ranks, 0.0);
      metrics->comm.assign(job->ranks, 0.0);
      all_metrics.push_back(metrics);

      const double cap = rate_limit(opt, *job);
      for (int r = 0; r < job->ranks; ++r) {
        const auto& p = job->placement[r];
        engine.host_by_name(gpu_name(p.host, p.gpu))->add_actor("j" + std::to_string(job->id) + "r" + std::to_string(r),
                                                                rank_actor, job, metrics, r, opt.rounds,
                                                                opt.gpu_tflops, cap);
      }
    }

    engine.run();

    const double makespan = sg4::Engine::get_clock();
    double avg_jct = 0.0;
    double avg_comm = 0.0;
    double useful_compute = 0.0;
    for (size_t i = 0; i < jobs.size(); ++i) {
      const auto& m = *all_metrics[i];
      const double start = *std::min_element(m.start.begin(), m.start.end());
      const double finish = *std::max_element(m.finish.begin(), m.finish.end());
      avg_jct += finish - start;
      avg_comm += *std::max_element(m.comm.begin(), m.comm.end());
      useful_compute += jobs[i].compute_s * opt.rounds * jobs[i].ranks;
    }
    avg_jct /= static_cast<double>(jobs.size());
    avg_comm /= static_cast<double>(jobs.size());
    const double useful_gpu_fraction = useful_compute / (makespan * opt.hosts * opt.gpus_per_host);

    std::ostream* os = &std::cout;
    std::ofstream file;
    if (!opt.out.empty()) {
      file.open(opt.out, std::ios::app);
      os = &file;
      if (file.tellp() == 0)
        *os << "scheduler,workload,placement_mode,placement_objective,makespan_s,avg_jct_s,avg_comm_s,useful_gpu_fraction,jobs,ranks,rounds,hosts,gpus_per_host\n";
    }
    int max_ranks = 0;
    for (const auto& job : jobs)
      max_ranks = std::max(max_ranks, job.ranks);

    *os << std::fixed << std::setprecision(6) << opt.scheduler << ","
        << (opt.workload_csv.empty() ? "synthetic" : "trace") << "," << opt.placement_mode << "," << opt.placement_objective << "," << makespan << "," << avg_jct << ","
        << avg_comm << "," << useful_gpu_fraction << "," << jobs.size() << "," << max_ranks << "," << opt.rounds << ","
        << opt.hosts << "," << opt.gpus_per_host << "\n";

    if (!opt.job_out.empty()) {
      std::ofstream jf(opt.job_out, std::ios::app);
      if (jf.tellp() == 0) {
        jf << "scheduler,workload,placement_mode,placement_objective,job_id,model,ranks,trace_start_s,"
           << "sim_start_s,sim_finish_s,jct_s,comm_s,compute_s,tensor_gib,intensity,placement\n";
      }
      for (size_t i = 0; i < jobs.size(); ++i) {
        const auto& job = jobs[i];
        const auto& m = *all_metrics[i];
        const double start = *std::min_element(m.start.begin(), m.start.end());
        const double finish = *std::max_element(m.finish.begin(), m.finish.end());
        const double comm = *std::max_element(m.comm.begin(), m.comm.end());
        jf << std::fixed << std::setprecision(6) << opt.scheduler << ","
           << (opt.workload_csv.empty() ? "synthetic" : "trace") << "," << opt.placement_mode << ","
           << opt.placement_objective << "," << job.id << "," << job.model << "," << job.ranks << ","
           << job.start_s << "," << start << "," << finish << "," << (finish - start) << "," << comm << ","
           << job.compute_s << "," << (job.tensor_bytes / 1024.0 / 1024.0 / 1024.0) << "," << job.intensity
           << "," << placement_string(job) << "\n";
      }
    }
  } catch (const std::exception& e) {
    std::cerr << "ERROR: " << e.what() << "\n";
    return 1;
  }
  return 0;
}
