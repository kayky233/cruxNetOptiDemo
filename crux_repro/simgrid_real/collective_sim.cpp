#include <algorithm>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <numeric>
#include <random>
#include <sstream>
#include <string>
#include <vector>
#include "simgrid/s4u.hpp"
#include "topology.h"
#include "comm_plan.h"
namespace sg4 = simgrid::s4u;

/* ── Options ────────────────────────────────────────────────── */
struct Options {
  std::string scheduler="random_same",topology="star",comm_plan="ring";
  std::string out,job_out,link_out,link_timeline_out,workload_csv;
  std::string placement_mode="replay",placement_objective="throughput";
  int hosts=8,gpus_per_host=8,jobs=12,ranks=8,rounds=4,seed=7;
  double gpu_tflops=200,local_gbps=400,nic_gbps=100,core_gbps=320;
  double overlap_ratio=0.0;
  double bg_checkpoint_gib=0,bg_inference_mbps=0,bg_dataset_pct=0;
  double perturb_link_gbps=0,perturb_time_s=0,perturb_misplace_pct=0;
  double link_sample_interval_s=1.0;
};

struct RankPlacement{int host=0,gpu=0;};
struct Job{int id=0,ranks=0;double compute_s=0,tensor_bytes=0,intensity=0,start_s=0;std::string model="synthetic";std::vector<RankPlacement> placement;};
struct JobMetrics{std::vector<double> start,finish,comm,compute_wait;};

/* ── Link timeline tracking ─────────────────────────────────── */
struct LinkSample{double time_s=0;uint64_t cumulative_bytes=0;};
static std::map<std::string,std::vector<LinkSample>> g_link_timeline;
static std::mutex g_timeline_mutex;
static double g_link_sample_interval=1.0;
static bool g_link_timeline_enabled=false;

static void sample_links(){
  std::lock_guard<std::mutex> lock(g_timeline_mutex);
  double now=sg4::Engine::get_clock();
  for(auto& kv:g_link_usage){
    LinkSample s; s.time_s=now; s.cumulative_bytes=(uint64_t)kv.second.total_bytes;
    g_link_timeline[kv.first].push_back(s);
  }
}

static void timeline_sampler_actor(){while(true){sg4::this_actor::sleep_for(g_link_sample_interval);sample_links();}}

/* ── CLI parsing ────────────────────────────────────────────── */
static Options parse_args(int argc,char** argv){Options o;
  for(int i=1;i<argc;++i){std::string k=argv[i];auto v=[&]{if(i+1>=argc)throw std::runtime_error("Missing: "+k);return std::string(argv[++i]);};
    if(k=="--scheduler")o.scheduler=v();else if(k=="--topology")o.topology=v();
    else if(k=="--comm-plan")o.comm_plan=v();else if(k=="--out")o.out=v();
    else if(k=="--job-out")o.job_out=v();else if(k=="--link-out")o.link_out=v();
    else if(k=="--link-timeline-out")o.link_timeline_out=v();
    else if(k=="--link-sample-interval")o.link_sample_interval_s=std::stod(v());
    else if(k=="--workload-csv")o.workload_csv=v();
    else if(k=="--placement-mode")o.placement_mode=v();
    else if(k=="--placement-objective")o.placement_objective=v();
    else if(k=="--hosts")o.hosts=std::stoi(v());
    else if(k=="--gpus-per-host")o.gpus_per_host=std::stoi(v());
    else if(k=="--jobs")o.jobs=std::stoi(v());else if(k=="--ranks")o.ranks=std::stoi(v());
    else if(k=="--rounds")o.rounds=std::stoi(v());else if(k=="--seed")o.seed=std::stoi(v());
    else if(k=="--local-gbps")o.local_gbps=std::stod(v());
    else if(k=="--nic-gbps")o.nic_gbps=std::stod(v());
    else if(k=="--core-gbps")o.core_gbps=std::stod(v());
    else if(k=="--overlap-ratio")o.overlap_ratio=std::stod(v());
    else if(k=="--bg-checkpoint-gib")o.bg_checkpoint_gib=std::stod(v());
    else if(k=="--bg-inference-mbps")o.bg_inference_mbps=std::stod(v());
    else if(k=="--bg-dataset-pct")o.bg_dataset_pct=std::stod(v());
    else if(k=="--perturb-link-gbps")o.perturb_link_gbps=std::stod(v());
    else if(k=="--perturb-time-s")o.perturb_time_s=std::stod(v());
    else if(k=="--perturb-misplace-pct")o.perturb_misplace_pct=std::stod(v());
    else throw std::runtime_error("Unknown: "+k);}return o;}

/* ── Topology ───────────────────────────────────────────────── */
static TopologyConfig make_topo(const Options& o){
  if(o.topology=="star")return make_star(o.hosts,o.gpus_per_host,o.local_gbps,o.nic_gbps,o.core_gbps);
  if(o.topology=="fat_tree")return make_fat_tree(o.hosts,o.gpus_per_host);
  if(o.topology=="three_tier_clos")return make_three_tier_clos(o.hosts,o.gpus_per_host);
  if(o.topology=="dragonfly")return make_dragonfly(o.hosts,o.gpus_per_host);
  if(o.topology=="ascend")return make_ascend_cluster(o.hosts,o.gpus_per_host);
  throw std::runtime_error("Unknown topology: "+o.topology);}

static std::string gn(int host,int gpu){return "h"+std::to_string(host)+"g"+std::to_string(gpu);}
static std::string hn(int host){return "h"+std::to_string(host)+"g0";}

static void build_platform(sg4::Engine& engine,const TopologyConfig& cfg){
  auto* root=engine.get_netzone_root()->add_netzone_full("cluster");
  std::vector<std::vector<const sg4::Host*>> gpus(cfg.hosts);
  for(int h=0;h<cfg.hosts;++h)for(int g=0;g<cfg.gpus_per_host;++g)
    gpus[h].push_back(root->add_host(gn(h,g),cfg.gpu_speed_flops)->set_core_count(1));
  std::vector<const sg4::Link*> local,nic;
  for(int h=0;h<cfg.hosts;++h)local.push_back(
    root->add_link("local"+std::to_string(h),cfg.local_bps)->set_latency(cfg.local_lat_s));
  for(int h=0;h<cfg.hosts;++h)for(int n=0;n<cfg.nics_per_host;++n)
    nic.push_back(root->add_link("nic"+std::to_string(h)+"_"+std::to_string(n),cfg.nic_bps)->set_latency(cfg.nic_lat_s));
  std::vector<std::vector<const sg4::Link*>> sw;
  for(size_t lvl=0;lvl<cfg.switches.size();++lvl){sw.push_back({});
    for(int s=0;s<cfg.switches[lvl].count;++s)
      sw.back().push_back(root->add_link("sw"+std::to_string(lvl)+"_"+std::to_string(s),cfg.switches[lvl].uplink_bps)->set_latency(cfg.switches[lvl].latency_s));}
  for(int h1=0;h1<cfg.hosts;++h1)for(int g1=0;g1<cfg.gpus_per_host;++g1)
    for(int h2=h1;h2<cfg.hosts;++h2)for(int g2=0;g2<cfg.gpus_per_host;++g2){
      if(h1==h2&&g1>=g2)continue;
      int nic1_idx=g1%cfg.nics_per_host,nic2_idx=g2%cfg.nics_per_host;
      if(h1==h2){root->add_route(gpus[h1][g1],gpus[h2][g2],{local[h1]});}
      else{std::vector<const sg4::Link*> p;p.push_back(nic[h1*cfg.nics_per_host+nic1_idx]);
        for(size_t lvl=0;lvl<sw.size();++lvl)
          p.push_back(sw[lvl][(h1*31+h2*17+(int)lvl*7)%sw[lvl].size()]);
        p.push_back(nic[h2*cfg.nics_per_host+nic2_idx]);root->add_route(gpus[h1][g1],gpus[h2][g2],p);}}
  g_link_usage.clear();for(auto* l:local){LinkUsage u;u.bandwidth_bps=cfg.local_bps;g_link_usage[l->get_name()]=u;}
  for(auto* l:nic){LinkUsage u;u.bandwidth_bps=cfg.nic_bps;g_link_usage[l->get_name()]=u;}
  for(size_t lvl=0;lvl<sw.size();++lvl)for(auto* l:sw[lvl])
    {LinkUsage u;u.bandwidth_bps=cfg.switches[lvl].uplink_bps;g_link_usage[l->get_name()]=u;}root->seal();}

/* ── Workload generation ────────────────────────────────────── */
static std::vector<Job> make_jobs(const Options& o){
  std::mt19937 rng(o.seed);std::uniform_real_distribution<double> hc(0.28,0.50),ht(7.0,12.0),lc(1.05,1.75),lt(0.4,1.6);
  std::vector<Job> jobs;for(int j=0;j<o.jobs;++j){bool hi=(j%3)!=2;Job jb;jb.id=j;jb.ranks=o.ranks;
    jb.compute_s=hi?hc(rng):lc(rng);jb.tensor_bytes=(hi?ht(rng):lt(rng))*1073741824.0;
    jb.intensity=jb.tensor_bytes/std::max(1e-9,jb.compute_s);jobs.push_back(jb);}return jobs;}

static std::vector<std::string> split(const std::string& t,char d){
  std::vector<std::string> o;std::stringstream ss(t);std::string it;
  while(std::getline(ss,it,d)){while(!it.empty()&&(it.back()=='\r'||it.back()=='\n'||it.back()==' '))it.pop_back();
    size_t s=0;while(s<it.size()&&it[s]==' ')++s;if(s>0)it.erase(0,s);o.push_back(it);}return o;}

static int ci(const std::vector<std::string>& h,const std::string& n){
  auto it=std::find(h.begin(),h.end(),n);if(it==h.end())throw std::runtime_error("csv missing: "+n);
  return (int)std::distance(h.begin(),it);}

static std::vector<Job> read_csv(const Options& o){
  std::ifstream f(o.workload_csv);if(!f)throw std::runtime_error("open: "+o.workload_csv);
  std::string l;if(!std::getline(f,l))throw std::runtime_error("empty");
  auto h=split(l,',');int cj=ci(h,"job_id"),cm=ci(h,"model"),cs=ci(h,"start_s"),cr=ci(h,"ranks"),
    cc=ci(h,"compute_s"),ct=ci(h,"tensor_gib"),ch=ci(h,"hosts");
  std::vector<Job> jobs;while(std::getline(f,l)){if(l.empty())continue;auto cols=split(l,',');
    Job jb;jb.id=std::stoi(cols[cj]);jb.model=cols[cm];jb.start_s=std::stod(cols[cs]);
    jb.ranks=std::max(2,std::min(std::stoi(cols[cr]),o.hosts*o.gpus_per_host));
    jb.compute_s=std::stod(cols[cc]);jb.tensor_bytes=std::stod(cols[ct])*1073741824.0;
    jb.intensity=jb.tensor_bytes/std::max(1e-9,jb.compute_s);
    auto htoks=split(cols[ch],';');for(int r=0;r<jb.ranks;++r){int th=std::stoi(htoks[r%htoks.size()]);
      jb.placement.push_back({((th%o.hosts)+o.hosts)%o.hosts,(r/(int)htoks.size())%o.gpus_per_host});}jobs.push_back(jb);}
  return jobs;}

/* ── Ablation: scheduler predicates ─────────────────────────── */
// Which schedulers use intensity-aware placement?
static bool use_crux_placement(const std::string& s){
  return s=="crux"||s=="crux_no_compress"||s=="place_only";}
// Which schedulers use any priority/rate-limiting?
static bool use_crux_priority(const std::string& s){
  return s=="crux"||s=="random_intensity"||s=="priority_only";}

/* ── Placement ──────────────────────────────────────────────── */
static std::vector<int> jorder(const std::vector<Job>& jobs,bool i1){
  std::vector<int> ids(jobs.size());std::iota(ids.begin(),ids.end(),0);
  if(i1)std::sort(ids.begin(),ids.end(),[&](int a,int b){return jobs[a].intensity>jobs[b].intensity;});
  return ids;}

static void place_jobs(std::vector<Job>& jobs,const Options& o){
  int tg=o.hosts*o.gpus_per_host;bool cp=use_crux_placement(o.scheduler);
  double gbw=o.placement_objective=="balanced"?3.0:0.25;
  std::vector<double> its;for(auto&j:jobs)its.push_back(j.intensity);
  std::sort(its.begin(),its.end());double hth=its.empty()?5e9:its[its.size()/2];
  auto ord=jorder(jobs,cp);std::vector<double> hl(o.hosts,0),gl(tg,0);
  auto llg=[&](int host){int b=0;double bl=1e308;
    for(int g=0;g<o.gpus_per_host;++g){int id=host*o.gpus_per_host+g;if(gl[id]<bl){bl=gl[id];b=g;}}return b;};
  for(size_t p=0;p<ord.size();++p){Job& jb=jobs[ord[p]];jb.placement.clear();
    std::vector<int> ch;for(int r=0;r<jb.ranks;++r){int idx=0;
    if(cp){int nd=std::max(1,(int)std::ceil(jb.ranks/(double)o.gpus_per_host));
      if(ch.empty()){double bs=1e308;int bb=0;
        for(int base=0;base<o.hosts;++base){double sc=0;
          for(int k=0;k<nd;++k){int h2=(base+k)%o.hosts;sc+=hl[h2];
            for(int g=0;g<o.gpus_per_host;++g)sc+=gbw*gl[h2*o.gpus_per_host+g];}
          if(sc<bs){bs=sc;bb=base;}}
        for(int k=0;k<nd;++k)ch.push_back((bb+k)%o.hosts);}
      int h2=ch[(r/o.gpus_per_host)%ch.size()];idx=h2*o.gpus_per_host+llg(h2);}
    else{idx=(jb.id*7+r*3)%tg;}
    jb.placement.push_back({idx/o.gpus_per_host,idx%o.gpus_per_host});
    hl[idx/o.gpus_per_host]+=jb.intensity/std::max(1,jb.ranks);
    gl[idx]+=jb.compute_s+jb.tensor_bytes/1e10;}}}

static double estimate_job_duration(const Job& jb,const Options& o){
  double compute=std::max(0.001,jb.compute_s*o.rounds);
  double nic_bps=std::max(1e9,o.nic_gbps*1e9/8.0);
  double comm=(jb.tensor_bytes*o.rounds*std::max(1,jb.ranks-1))/nic_bps;
  return std::max(compute+comm,compute*1.2);
}

static void schedule_gpu_exclusive(std::vector<Job>& jobs,const Options& o){
  int tg=o.hosts*o.gpus_per_host;
  std::vector<double> gpu_free(tg,0.0);
  auto ids=jorder(jobs,use_crux_priority(o.scheduler)||use_crux_placement(o.scheduler));
  for(int jid:ids){Job& jb=jobs[jid];double start=jb.start_s;
    for(auto&p:jb.placement){int idx=p.host*o.gpus_per_host+p.gpu;
      if(idx>=0&&idx<tg)start=std::max(start,gpu_free[idx]);}
    jb.start_s=start;double finish=start+estimate_job_duration(jb,o);
    for(auto&p:jb.placement){int idx=p.host*o.gpus_per_host+p.gpu;
      if(idx>=0&&idx<tg)gpu_free[idx]=finish;}}}

static void validate(const Options& o){
  if(o.placement_mode!="replay"&&o.placement_mode!="optimize")
    throw std::runtime_error("bad placement_mode");}

/* ── Rate limit ─────────────────────────────────────────────── */
static double rlimit(const Options& o,const Job& job){
  if(!use_crux_priority(o.scheduler))return -1; // unlimited
  if(o.scheduler=="crux_no_compress")return -1;
  double b=o.nic_gbps*1e9/8.0;
  // intensity-based: high-intensity jobs get unlimited, low-intensity get rate-limited
  double median_intensity=5e9; // fallback
  if(job.intensity>median_intensity)return -1;
  if(o.scheduler=="random_intensity")return b*0.65;
  if(o.scheduler=="crux")return b*0.40;
  if(o.scheduler=="priority_only")return b*0.50;
  return -1;
}

static std::string pstr(const Job& job){std::ostringstream ss;
  for(size_t i=0;i<job.placement.size();++i){if(i>0)ss<<";";ss<<job.placement[i].host<<":"<<job.placement[i].gpu;}return ss.str();}

/* ── Background traffic actors ──────────────────────────────── */
static void bg_actor(int hosts,double check_gib,double inf_mbps,int seed){
  std::mt19937 rng(seed);auto* my=sg4::this_actor::get_host();
  while(true){auto now=sg4::Engine::get_clock();
    if(check_gib>0&&fmod(now,60.0)<0.1){int src=rng()%hosts,dst=rng()%hosts;if(src==dst)dst=(src+1)%hosts;
      uint64_t bytes=(uint64_t)(check_gib*1073741824);
      if(auto* dh=sg4::Host::by_name_or_null(hn(dst)))sg4::Comm::sendto(my,dh,bytes);
      g_link_usage["nic"+std::to_string(src)+"_0"].total_bytes+=bytes;
      g_link_usage["nic"+std::to_string(dst)+"_0"].total_bytes+=bytes;}
    if(inf_mbps>0&&fmod(now,0.01)<0.001){int src=rng()%hosts,dst=rng()%hosts;if(src==dst)dst=(src+1)%hosts;
      uint64_t bytes=(uint64_t)(inf_mbps*1e6/8.0*0.01);
      if(auto* dh=sg4::Host::by_name_or_null(hn(dst)))sg4::Comm::sendto(my,dh,bytes);
      g_link_usage["nic"+std::to_string(src)+"_0"].total_bytes+=bytes;
      g_link_usage["nic"+std::to_string(dst)+"_0"].total_bytes+=bytes;}
    sg4::this_actor::sleep_for(0.1);}sg4::this_actor::sleep_for(1e9);}

static void perturb_actor(const Options& o){if(o.perturb_time_s>0){sg4::this_actor::sleep_until(o.perturb_time_s);
    if(o.perturb_link_gbps>0){double bps=o.perturb_link_gbps*1e9/8.0;
      for(auto& kv:g_link_usage)if(kv.first.find("sw")==0)kv.second.bandwidth_bps=bps;}}sg4::this_actor::sleep_for(1e9);}

/* ── Rank actor with overlap support ────────────────────────── */
static void rank_actor(std::shared_ptr<Job> job,std::shared_ptr<JobMetrics> metrics,int rank,
    int rounds,double gpu_tflops,double sr,double overlap_ratio,
    const TopologyConfig& cfg,const std::string& cpn){
  double flops=job->compute_s*gpu_tflops*1e12;
  double non_overlap_flops=flops*(1.0-overlap_ratio);
  double overlap_flops=flops*overlap_ratio;
  auto plan=make_comm_plan(cpn);
  std::vector<std::pair<int,int>> pp;for(auto&p:job->placement)pp.push_back({p.host,p.gpu});
  if(job->start_s>0)sg4::this_actor::sleep_until(job->start_s);
  metrics->start[rank]=sg4::Engine::get_clock();
  for(int r=0;r<rounds;++r){
    // Non-overlappable compute (forward pass)
    double t0=sg4::Engine::get_clock();
    sg4::this_actor::execute(non_overlap_flops);
    double t1=sg4::Engine::get_clock();
    // Start overlappable compute (backward) asynchronously if overlap enabled
    sg4::ExecPtr bg_exec=nullptr;
    if(overlap_ratio>0){bg_exec=sg4::this_actor::exec_init(overlap_flops);bg_exec->start();}
    // Communication (overlaps with backward compute)
    double cb=sg4::Engine::get_clock();
    plan->execute(job->id,rank,job->ranks,(uint64_t)job->tensor_bytes,sr,pp,cfg);
    metrics->comm[rank]+=sg4::Engine::get_clock()-cb;
    // Wait for overlappable compute to finish (if any)
    if(bg_exec){bg_exec->wait();double t2=sg4::Engine::get_clock();
      metrics->compute_wait[rank]+=(t2-t1)-(t2-std::max(t1,cb));}
    else{sg4::this_actor::execute(overlap_flops);}}
  metrics->finish[rank]=sg4::Engine::get_clock();}

int main(int argc,char** argv){try{auto o=parse_args(argc,argv);validate(o);auto topo=make_topo(o);
  if(o.hosts>0)topo.hosts=o.hosts;if(o.gpus_per_host>0)topo.gpus_per_host=o.gpus_per_host;
  sg4::Engine engine(&argc,argv);build_platform(engine,topo);
  auto jobs=o.workload_csv.empty()?make_jobs(o):read_csv(o);
  if(o.workload_csv.empty()||o.placement_mode=="optimize")place_jobs(jobs,o);
  schedule_gpu_exclusive(jobs,o);
  if(o.perturb_misplace_pct>0){std::mt19937 rng(o.seed+999);
    int nm=std::max(1,(int)(jobs.size()*o.perturb_misplace_pct/100.0));
    for(int i=0;i<nm;++i){int jid=rng()%jobs.size();
      for(auto&p:jobs[jid].placement)p.host=(p.host+rng()%o.hosts)%o.hosts;}}
  // Spawn link timeline sampler
  g_link_sample_interval=o.link_sample_interval_s;
  g_link_timeline_enabled=!o.link_timeline_out.empty();
  if(g_link_timeline_enabled){g_link_timeline.clear();
    engine.host_by_name(hn(0))->add_actor("link_sampler",timeline_sampler_actor);}
  // Spawn rank actors
  std::vector<std::shared_ptr<JobMetrics>> am;
  for(auto& jv:jobs){auto jb=std::make_shared<Job>(jv);auto m=std::make_shared<JobMetrics>();
    m->start.assign(jb->ranks,0);m->finish.assign(jb->ranks,0);m->comm.assign(jb->ranks,0);
    m->compute_wait.assign(jb->ranks,0);am.push_back(m);
    double cap=rlimit(o,*jb);
    for(int r=0;r<jb->ranks;++r){auto&p=jb->placement[r];
      engine.host_by_name(gn(p.host,p.gpu))->add_actor("j"+std::to_string(jb->id)+"r"+std::to_string(r),
        rank_actor,jb,m,r,o.rounds,o.gpu_tflops,cap,o.overlap_ratio,std::cref(topo),o.comm_plan);}}
  // Background traffic
  if(o.bg_checkpoint_gib>0||o.bg_inference_mbps>0){for(int h=0;h<o.hosts;++h)
    engine.host_by_name(hn(h))->add_actor("bg"+std::to_string(h),bg_actor,o.hosts,o.bg_checkpoint_gib,o.bg_inference_mbps,o.seed+100+h);}
  if(o.bg_dataset_pct>0){int nh=std::max(1,(int)(o.hosts*o.bg_dataset_pct/100.0));std::mt19937 rng(o.seed+300);
    for(int i=0;i<nh;++i){int src=rng()%o.hosts;for(int d=0;d<o.hosts;++d){if(d==src)continue;uint64_t bytes=10737418240ULL;
      engine.host_by_name(hn(src))->add_actor("ds"+std::to_string(i)+"_"+std::to_string(d),
        [](uint64_t bz,const std::string& dh){sg4::Comm::sendto(sg4::this_actor::get_host(),sg4::Host::by_name_or_null(dh),bz);},bytes,hn(d));}}}
  if(o.perturb_link_gbps>0||o.perturb_time_s>0)engine.host_by_name(hn(0))->add_actor("perturb",perturb_actor,std::cref(o));
  // Run simulation
  engine.run();
  double ms=sg4::Engine::get_clock(),aj=0,ac=0,aw=0,uc=0;
  for(size_t i=0;i<jobs.size();++i){auto&m=*am[i];
    double s=*std::min_element(m.start.begin(),m.start.end()),
           f=*std::max_element(m.finish.begin(),m.finish.end());
    aj+=f-s;ac+=*std::max_element(m.comm.begin(),m.comm.end());
    aw+=*std::max_element(m.compute_wait.begin(),m.compute_wait.end());
    uc+=jobs[i].compute_s*o.rounds*jobs[i].ranks;}
  aj/=jobs.size();ac/=jobs.size();aw/=jobs.size();
  double ugf=uc/(ms*o.hosts*o.gpus_per_host);
  // Write aggregate results
  std::ostream* os=&std::cout;std::ofstream file;
  if(!o.out.empty()){file.open(o.out,std::ios::app);os=&file;
    if(file.tellp()==0)*os<<"scheduler,topology,comm_plan,workload,placement_mode,placement_objective,overlap_ratio,makespan_s,avg_jct_s,avg_comm_s,avg_compute_wait_s,useful_gpu_fraction,jobs,ranks,rounds,hosts,gpus_per_host\n";}
  int mr=0;for(auto&j:jobs)mr=std::max(mr,j.ranks);
  *os<<std::fixed<<std::setprecision(6)<<o.scheduler<<","<<o.topology<<","<<o.comm_plan<<","
     <<(o.workload_csv.empty()?"synthetic":"trace")<<","<<o.placement_mode<<","<<o.placement_objective
     <<","<<o.overlap_ratio<<","<<ms<<","<<aj<<","<<ac<<","<<aw<<","<<ugf<<","
     <<jobs.size()<<","<<mr<<","<<o.rounds<<","<<o.hosts<<","<<o.gpus_per_host<<"\n";
  // Write job-level results
  if(!o.job_out.empty()){std::ofstream jf(o.job_out,std::ios::app);
    if(jf.tellp()==0)jf<<"scheduler,topology,comm_plan,workload,placement_mode,placement_objective,job_id,model,ranks,trace_start_s,sim_start_s,sim_finish_s,jct_s,comm_s,compute_wait_s,compute_s,tensor_gib,intensity,placement\n";
    for(size_t i=0;i<jobs.size();++i){auto&jb=jobs[i];auto&m=*am[i];
      double s=*std::min_element(m.start.begin(),m.start.end()),
             f=*std::max_element(m.finish.begin(),m.finish.end()),
             c=*std::max_element(m.comm.begin(),m.comm.end()),
             w=*std::max_element(m.compute_wait.begin(),m.compute_wait.end());
      jf<<std::fixed<<std::setprecision(6)<<o.scheduler<<","<<o.topology<<","<<o.comm_plan<<","
        <<(o.workload_csv.empty()?"synthetic":"trace")<<","<<o.placement_mode<<","<<o.placement_objective
        <<","<<jb.id<<","<<jb.model<<","<<jb.ranks<<","<<jb.start_s<<","<<s<<","<<f<<","<<(f-s)<<","
        <<c<<","<<w<<","<<jb.compute_s<<","<<(jb.tensor_bytes/1073741824.0)<<","<<jb.intensity<<","<<pstr(jb)<<"\n";}}
  // Write link aggregate utilization
  if(!o.link_out.empty()){std::ofstream lf(o.link_out);
    lf<<"link_name,bandwidth_bps,total_bytes,utilization,makespan_s\n";
    for(auto&kv:g_link_usage)lf<<kv.first<<","<<std::fixed<<std::setprecision(1)<<kv.second.bandwidth_bps<<","
      <<kv.second.total_bytes<<","<<std::setprecision(6)<<kv.second.utilization()<<","<<ms<<"\n";}
  // Write link timeline
  if(g_link_timeline_enabled){
    sample_links(); // final sample
    std::ofstream tf(o.link_timeline_out);
    tf<<"link_name,time_s,cumulative_bytes\n";
    for(auto&kv:g_link_timeline)for(auto&s:kv.second)
      tf<<kv.first<<","<<std::fixed<<std::setprecision(3)<<s.time_s<<","<<s.cumulative_bytes<<"\n";}
  // Print bottleneck links
  std::vector<std::pair<std::string,double>> rk;
  for(auto&kv:g_link_usage)rk.push_back({kv.first,kv.second.utilization()});
  std::sort(rk.begin(),rk.end(),[](auto&a,auto&b){return a.second>b.second;});
  std::cerr<<"Top-5 bottleneck links:\n";
  for(int i=0;i<std::min(5,(int)rk.size());++i)
    std::cerr<<"  "<<rk[i].first<<" util="<<std::fixed<<std::setprecision(4)<<rk[i].second*100<<"%\n";
  std::cerr<<"Experiment: scheduler="<<o.scheduler<<" topology="<<o.topology
           <<" makespan="<<ms<<"s avg_jct="<<aj<<"s ugf="<<ugf<<"\n";}
catch(const std::exception& e){std::cerr<<"ERROR: "<<e.what()<<"\n";return 1;}return 0;}
