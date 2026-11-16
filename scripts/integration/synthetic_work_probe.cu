// Model-free CUDA work classes. Build: nvcc -O3 -std=c++17 -arch=sm_61
//   synthetic_work_probe.cu -o synthetic-work-probe
#include <cuda_fp16.h>
#include <cuda_runtime.h>
#include <algorithm>
#include <atomic>
#include <cctype>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <numeric>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using Clock = std::chrono::steady_clock;
static void ck(cudaError_t e) { if (e != cudaSuccess) throw std::runtime_error(cudaGetErrorString(e)); }
static double us(Clock::time_point a, Clock::time_point b) {
    return std::chrono::duration<double, std::micro>(b-a).count();
}
static double pct(std::vector<double> x, double q) {
    std::sort(x.begin(), x.end()); return x[size_t(q*(x.size()-1))];
}
static void emit(const char *kind, const std::string &bus, size_t bytes,
                 const std::vector<double> &values, int count=0, int hits=-1) {
    if (values.empty()) return;
    double mean=std::accumulate(values.begin(),values.end(),0.0)/values.size();
    std::printf("{\"kind\":\"%s\",\"bus\":\"%s\",\"bytes\":%zu,"
                "\"samples\":%zu,\"mean_us\":%.3f,\"p50_us\":%.3f,"
                "\"p95_us\":%.3f,\"item_count\":%d,\"hits\":%d}\n",
                kind,bus.c_str(),bytes,values.size(),mean,pct(values,.5),pct(values,.95),count,hits);
    std::fflush(stdout);
}
static std::string suffix(std::string s) {
    for(char &c:s) c=char(std::tolower(static_cast<unsigned char>(c)));
    return s.size()>7?s.substr(s.size()-7):s;
}
__global__ static void weight_step(const float *w, float *out, int n) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;
    if(i<n) out[i]=w[i]*0.75f+float(i&7)*0.01f;
}
__global__ static void kv_scan(const __half *k,const __half *v,float *out,int tokens) {
    int t=blockIdx.x*blockDim.x+threadIdx.x;
    if(t>=tokens) return;
    float dot=0, val=0;
    for(int j=0;j<128;j++) { dot+=__half2float(k[t*128+j])*0.0078125f;
                              val+=__half2float(v[t*128+j])*0.0078125f; }
    out[t]=dot*val;
}
__global__ static void gather_rows(const uint8_t *table,const uint32_t *rows,
                                   uint8_t *out,int row_count,int row_bytes) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;
    if(i<row_count*row_bytes) out[i]=table[size_t(rows[i/row_bytes])*row_bytes+i%row_bytes];
}
template<class F> static std::vector<double> timed(int warm,int count,F fn) {
    std::vector<double> values; values.reserve(count);
    for(int i=-warm;i<count;i++) {
        auto a=Clock::now(); fn(i); auto b=Clock::now();
        if(i>=0) values.push_back(us(a,b));
    }
    return values;
}
static void weight_probe(const std::string &bus,bool deep) {
    const size_t bytes=size_t(deep?128:32)<<20;
    const int n=int(bytes/sizeof(float)), reps=deep?20:8;
    float *host=nullptr,*gpu=nullptr,*out=nullptr;
    ck(cudaMallocHost(&host,bytes)); ck(cudaMalloc(&gpu,bytes)); ck(cudaMalloc(&out,bytes));
    for(int i=0;i<n;i++) host[i]=float(i%251)/251.0f;
    ck(cudaMemcpy(gpu,host,bytes,cudaMemcpyHostToDevice));
    auto kernel=[&](int) {weight_step<<<(n+255)/256,256>>>(gpu,out,n);
                         ck(cudaGetLastError());ck(cudaDeviceSynchronize());};
    emit("weight_resident",bus,bytes,timed(2,reps,kernel));
    emit("weight_ram_upload",bus,bytes,timed(2,reps,[&](int i){
        ck(cudaMemcpy(gpu,host,bytes,cudaMemcpyHostToDevice));kernel(i);
    }));
    float check=0;ck(cudaMemcpy(&check,out,sizeof(check),cudaMemcpyDeviceToHost));
    if(std::fabs(check)>0.001f) throw std::runtime_error("weight output check");
    ck(cudaFree(out));ck(cudaFree(gpu));ck(cudaFreeHost(host));
}
static void kv_probe(const std::string &bus,bool deep) {
    const int contexts[2]={deep?32768:4096,deep?131072:32768};
    for(int tokens:contexts) {
        size_t each=size_t(tokens)*128*sizeof(__half);
        __half *k=nullptr,*v=nullptr;float *out=nullptr;
        ck(cudaMalloc(&k,each));ck(cudaMalloc(&v,each));ck(cudaMalloc(&out,size_t(tokens)*4));
        ck(cudaMemset(k,0,each));ck(cudaMemset(v,0,each));
        auto fn=[&](int){kv_scan<<<(tokens+127)/128,128>>>(k,v,out,tokens);
                         ck(cudaGetLastError());ck(cudaDeviceSynchronize());};
        emit("kv_scan_one_head",bus,each*2,timed(2,deep?20:8,fn),tokens);
        float check=1;ck(cudaMemcpy(&check,out,sizeof(check),cudaMemcpyDeviceToHost));
        if(check!=0) throw std::runtime_error("KV output check");
        ck(cudaFree(out));ck(cudaFree(v));ck(cudaFree(k));
    }
}
static void lookup_probe(const std::string &bus,bool deep) {
    constexpr int row_bytes=128, row_count=16;
    const size_t bytes=size_t(deep?256:64)<<20;
    uint8_t *table=nullptr,*gathered=nullptr,*host=nullptr;uint32_t *positions=nullptr;
    ck(cudaMalloc(&table,bytes));ck(cudaMalloc(&positions,row_count*4));
    ck(cudaMalloc(&gathered,row_count*row_bytes));ck(cudaMallocHost(&host,row_count*row_bytes));
    ck(cudaMemset(table,37,bytes));
    uint32_t rows[row_count];
    auto fn=[&](int i){
        uint32_t seed=uint32_t(i+100)*747796405u+2891336453u;
        for(int j=0;j<row_count;j++){seed=seed*1664525u+1013904223u;
            rows[j]=seed%uint32_t(bytes/row_bytes);}
        ck(cudaMemcpy(positions,rows,sizeof(rows),cudaMemcpyHostToDevice));
        gather_rows<<<2,1024>>>(table,positions,gathered,row_count,row_bytes);
        ck(cudaGetLastError());
        ck(cudaMemcpy(host,gathered,row_count*row_bytes,cudaMemcpyDeviceToHost));
    };
    emit("lookup_gpu_gather",bus,bytes,timed(3,deep?120:40,fn),row_count);
    for(int j=0;j<row_count*row_bytes;j++) if(host[j]!=37) throw std::runtime_error("lookup output check");
    ck(cudaFreeHost(host));ck(cudaFree(gathered));ck(cudaFree(positions));ck(cudaFree(table));
}
static void host_lookup_probe(bool deep) {
    constexpr int row_bytes=128,row_count=16;
    size_t bytes=size_t(deep?256:64)<<20;
    uint8_t *table=nullptr;ck(cudaMallocHost(&table,bytes));
    std::memset(table,37,bytes);uint8_t result[row_count*row_bytes];
    auto fn=[&](int i){
        uint32_t seed=uint32_t(i+100)*747796405u+2891336453u;
        for(int j=0;j<row_count;j++){seed=seed*1664525u+1013904223u;
            size_t row=seed%uint32_t(bytes/row_bytes);
            std::memcpy(result+j*row_bytes,table+row*row_bytes,row_bytes);}
    };
    emit("lookup_pinned_ram", "host",bytes,timed(3,deep?120:40,fn),row_count);
    for(uint8_t value:result)if(value!=37)throw std::runtime_error("host lookup check");
    ck(cudaFreeHost(table));
}
static void expert_probe(const std::string &bus,bool deep) {
    const int experts=deep?128:32, slots=deep?16:4, calls=deep?240:80;
    const size_t bytes=1u<<20;const int n=int(bytes/sizeof(float));
    float *host=nullptr,*gpu=nullptr,*out=nullptr;
    ck(cudaMallocHost(&host,size_t(experts)*bytes));
    ck(cudaMalloc(&gpu,size_t(slots)*bytes));ck(cudaMalloc(&out,bytes));
    for(int e=0;e<experts;e++) for(int j=0;j<n;j++)host[e*n+j]=float((e+j)%127)/127.0f;
    std::vector<int> resident(slots,-1),age(slots,0);int clock=0,hits=0;
    std::vector<double> hit_times,miss_times,all;all.reserve(calls);int last_expert=-1;
    for(int i=-10;i<calls;i++) {
        // 80% hot routes, 20% broad tail. Deterministic across rigs.
        int expert=(i%5==0)?(std::abs(i*37+11)%experts):(std::abs(i*7+3)%4);
        int slot=-1;for(int s=0;s<slots;s++)if(resident[s]==expert)slot=s;
        bool hit=slot>=0;
        if(!hit){slot=int(std::min_element(age.begin(),age.end())-age.begin());
                 for(int s=0;s<slots;s++)if(resident[s]<0){slot=s;break;}}
        auto a=Clock::now();
        if(!hit) ck(cudaMemcpy(gpu+size_t(slot)*n,host+size_t(expert)*n,bytes,cudaMemcpyHostToDevice));
        weight_step<<<(n+255)/256,256>>>(gpu+size_t(slot)*n,out,n);
        ck(cudaGetLastError());ck(cudaDeviceSynchronize());
        auto b=Clock::now();resident[slot]=expert;age[slot]=++clock;last_expert=expert;
        if(i>=0){double value=us(a,b);all.push_back(value);
            if(hit){hits++;hit_times.push_back(value);}else miss_times.push_back(value);}
    }
    emit("expert_route_80pct_hot",bus,size_t(experts)*bytes,all,slots,hits);
    emit("expert_cache_hit",bus,bytes,hit_times,slots);
    emit("expert_ram_miss",bus,bytes,miss_times,slots);
    float check=0;ck(cudaMemcpy(&check,out,sizeof(check),cudaMemcpyDeviceToHost));
    if(std::fabs(check-float(last_expert%127)/127.0f*0.75f)>1e-5f)
        throw std::runtime_error("expert output check");
    ck(cudaFree(out));ck(cudaFree(gpu));ck(cudaFreeHost(host));
}
static void concurrent_probe(const std::vector<int> &devices,bool deep) {
    if(devices.size()<2) return;
    const size_t bytes=size_t(32)<<20;const int reps=deep?16:4;
    std::vector<std::string> buses(devices.size());
    std::vector<double> solo(devices.size()),seconds(devices.size());
    for(size_t i=0;i<devices.size();i++) {
        ck(cudaSetDevice(devices[i]));char bus[32]={};
        ck(cudaDeviceGetPCIBusId(bus,sizeof(bus),devices[i]));buses[i]=bus;
        void *host=nullptr,*gpu=nullptr;
        ck(cudaMallocHost(&host,bytes));ck(cudaMalloc(&gpu,bytes));
        std::memset(host,17,bytes);
        auto a=Clock::now();
        for(int j=0;j<reps;j++)ck(cudaMemcpy(gpu,host,bytes,cudaMemcpyHostToDevice));
        auto b=Clock::now();solo[i]=std::chrono::duration<double>(b-a).count();
        ck(cudaFree(gpu));ck(cudaFreeHost(host));
    }
    std::vector<std::thread> threads;
    std::atomic<int> ready{0};std::atomic<bool> go{false};
    for(size_t i=0;i<devices.size();i++)threads.emplace_back([&,i]{
        ck(cudaSetDevice(devices[i]));void *host=nullptr,*gpu=nullptr;
        ck(cudaMallocHost(&host,bytes));ck(cudaMalloc(&gpu,bytes));
        std::memset(host,17,bytes);
        ready.fetch_add(1);while(!go.load())std::this_thread::yield();
        auto a=Clock::now();
        for(int j=0;j<reps;j++)ck(cudaMemcpy(gpu,host,bytes,cudaMemcpyHostToDevice));
        auto b=Clock::now();seconds[i]=std::chrono::duration<double>(b-a).count();
        ck(cudaFree(gpu));ck(cudaFreeHost(host));
    });
    while(ready.load()!=int(devices.size()))std::this_thread::yield();
    go.store(true);
    for(auto &thread:threads)thread.join();
    double wall=*std::max_element(seconds.begin(),seconds.end());
    for(size_t i=0;i<devices.size();i++) {
        for(int mode=0;mode<2;mode++) {
            double duration=mode?seconds[i]:solo[i];
            std::printf("{\"kind\":\"%s\",\"bus\":\"%s\",\"bytes\":%zu,"
                        "\"repeats\":%d,\"seconds\":%.6f,\"gbps\":%.3f}\n",
                        mode?"h2d_parallel_device":"h2d_serial_device",buses[i].c_str(),
                        bytes,reps,duration,double(bytes)*reps/duration/1e9);
        }
    }
    std::printf("{\"kind\":\"concurrent_h2d\",\"devices\":%zu,\"bytes\":%zu,"
                "\"repeats\":%d,\"wall_s\":%.6f,\"aggregate_gbps\":%.3f}\n",
                devices.size(),bytes,reps,wall,double(bytes)*reps*devices.size()/wall/1e9);
}
int main(int argc,char **argv) {
    if(argc<3 || (std::strcmp(argv[1],"small") && std::strcmp(argv[1],"deep"))) {
        std::fprintf(stderr,"usage: synthetic-work-probe small|deep PCI_BUS...\n");return 64;
    }
    try {
        bool deep=!std::strcmp(argv[1],"deep");int count=0;ck(cudaGetDeviceCount(&count));
        std::vector<int> selected;
        for(int a=2;a<argc;a++) {
            int found=-1;for(int d=0;d<count;d++){
                char bus[32]={};ck(cudaDeviceGetPCIBusId(bus,sizeof(bus),d));
                if(suffix(bus)==suffix(argv[a])) found=d;
            }
            if(found<0 || std::find(selected.begin(),selected.end(),found)!=selected.end())
                throw std::runtime_error("missing or repeated PCI bus");
            selected.push_back(found);
        }
        for(int d:selected) {
            ck(cudaSetDevice(d));char bus[32]={};ck(cudaDeviceGetPCIBusId(bus,sizeof(bus),d));
            std::fprintf(stderr,"DEVICE cuda=%d bus=%s\n",d,bus);
            weight_probe(bus,deep);kv_probe(bus,deep);lookup_probe(bus,deep);expert_probe(bus,deep);
        }
        host_lookup_probe(deep);
        if(deep) concurrent_probe(selected,deep);
    } catch(const std::exception &e) {std::fprintf(stderr,"ERROR %s\n",e.what());return 2;}
    return 0;
}
