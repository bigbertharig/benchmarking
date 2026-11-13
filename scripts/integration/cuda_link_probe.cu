// Measure actual pinned-host and GPU-pair copy paths on the live rig.
// Build: nvcc -O2 -std=c++17 cuda_link_probe.cu -o cuda_link_probe
#include <cuda_runtime.h>
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <strings.h>
#include <vector>

static void check(cudaError_t result, const char *where) {
    if (result != cudaSuccess) {
        std::fprintf(stderr, "%s: %s\n", where, cudaGetErrorString(result));
        std::exit(1);
    }
}
struct Card {
    int id;
    void *memory;
    cudaStream_t stream;
};
static void measure(const char *kind, int src, int dst, size_t bytes, int repeats,
                    void *dst_ptr, const void *src_ptr, cudaMemcpyKind copy_kind,
                    cudaStream_t stream, bool peer) {
    check(cudaSetDevice(dst), "set destination device");
    auto copy = [&]() {
        if (peer) return cudaMemcpyPeerAsync(dst_ptr, dst, src_ptr, src, bytes, stream);
        return cudaMemcpyAsync(dst_ptr, src_ptr, bytes, copy_kind, stream);
    };
    check(copy(), "warm copy");
    check(cudaStreamSynchronize(stream), "warm synchronize");
    std::vector<double> times;
    for (int i = 0; i < repeats; ++i) {
        auto start = std::chrono::steady_clock::now();
        check(copy(), "timed copy");
        check(cudaStreamSynchronize(stream), "timed synchronize");
        auto end = std::chrono::steady_clock::now();
        times.push_back(std::chrono::duration<double, std::milli>(end-start).count());
    }
    std::sort(times.begin(), times.end());
    double median = times[times.size()/2];
    std::printf("%s,%d,%d,%zu,%d,%.6f,%.4f\n", kind, src, dst, bytes, repeats,
                median, bytes / (median * 1e6));
}
int main(int argc, char **argv) {
    int count=0; check(cudaGetDeviceCount(&count), "device count");
    if (argc==2 && std::strcmp(argv[1],"--list")==0) {
        std::printf("cuda_id,pci_bus_id,name\n");
        for (int id=0; id<count; ++id) {
            char bus[32]; check(cudaDeviceGetPCIBusId(bus,sizeof(bus),id),"PCI bus");
            cudaDeviceProp prop{}; check(cudaGetDeviceProperties(&prop,id),"device properties");
            std::printf("%d,%s,%s\n",id,bus,prop.name);
        }
        return 0;
    }
    std::vector<int> ids;
    for (int i=1; i<argc; ++i) {
        const std::string wanted=argv[i];
        if (wanted.size()<7) { std::fprintf(stderr, "pass PCI bus IDs\n"); return 2; }
        int found=-1;
        for (int id=0; id<count; ++id) {
            char bus[32]; check(cudaDeviceGetPCIBusId(bus,sizeof(bus),id),"PCI bus");
            std::string observed=bus;
            if (observed.size()>=7 && strcasecmp(observed.c_str()+observed.size()-7,
                                                  wanted.c_str()+wanted.size()-7)==0) {
                found=id; break;
            }
        }
        if (found<0) { std::fprintf(stderr, "PCI bus %s absent from CUDA devices\n",wanted.c_str()); return 2; }
        if (std::find(ids.begin(),ids.end(),found)!=ids.end()) { std::fprintf(stderr,"duplicate PCI bus\n"); return 2; }
        ids.push_back(found);
    }
    if (ids.empty()) { std::fprintf(stderr, "pass detected PCI bus IDs\n"); return 2; }
    constexpr size_t max_bytes = 128u*1024u*1024u;
    std::vector<Card> cards;
    for (int id: ids) {
        if (id<0 || id>=count) { std::fprintf(stderr, "device %d absent\n", id); return 2; }
        cudaDeviceProp prop{};
        check(cudaGetDeviceProperties(&prop,id), "device properties");
        char bus[32]; check(cudaDeviceGetPCIBusId(bus,sizeof(bus),id), "PCI bus");
        std::fprintf(stderr, "DEVICE id=%d name=%s bus=%s total=%zu\n",
                     id,prop.name,bus,prop.totalGlobalMem);
        check(cudaSetDevice(id), "set device");
        Card card{id,nullptr,nullptr};
        check(cudaMalloc(&card.memory,max_bytes), "device allocation");
        check(cudaStreamCreate(&card.stream), "create stream");
        cards.push_back(card);
    }
    void *host=nullptr;
    check(cudaHostAlloc(&host,max_bytes,cudaHostAllocDefault), "pinned host allocation");
    std::memset(host,0,max_bytes);
    std::printf("kind,src,dst,bytes,repeats,median_ms,GBps\n");
    for (size_t bytes: {size_t(64*1024),size_t(1024*1024),
                        size_t(16*1024*1024),max_bytes}) {
        int repeats=bytes>=max_bytes?8:20;
        for (auto &card: cards) {
            measure("h2d",-1,card.id,bytes,repeats,card.memory,host,
                    cudaMemcpyHostToDevice,card.stream,false);
            measure("d2h",card.id,card.id,bytes,repeats,host,card.memory,
                    cudaMemcpyDeviceToHost,card.stream,false);
        }
        for (auto &src: cards) for (auto &dst: cards) {
            if (src.id==dst.id) continue;
            int can=0;
            check(cudaDeviceCanAccessPeer(&can,dst.id,src.id), "peer capability");
            std::fprintf(stderr,"PEER src=%d dst=%d supported=%d\n",src.id,dst.id,can);
            if (can) {
                check(cudaSetDevice(dst.id),"set peer destination");
                auto rc=cudaDeviceEnablePeerAccess(src.id,0);
                if (rc!=cudaSuccess && rc!=cudaErrorPeerAccessAlreadyEnabled) check(rc,"enable peer");
            }
            measure(can?"p2p":"peer_staged",src.id,dst.id,bytes,repeats,
                    dst.memory,src.memory,cudaMemcpyDefault,dst.stream,true);
        }
    }
    check(cudaFreeHost(host),"free pinned host");
    for (auto &card: cards) {
        check(cudaSetDevice(card.id),"set device for free");
        check(cudaStreamDestroy(card.stream),"destroy stream");
        check(cudaFree(card.memory),"free device");
    }
    return 0;
}
