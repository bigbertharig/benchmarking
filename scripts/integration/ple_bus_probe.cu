#include <cuda_runtime.h>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <stdexcept>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

using clock_type = std::chrono::steady_clock;
static void ck(cudaError_t e) { if (e != cudaSuccess) throw std::runtime_error(cudaGetErrorString(e)); }
static double pct(std::vector<double> x, double q) {
    std::sort(x.begin(), x.end()); return x[size_t(q * (x.size()-1))];
}
static uint64_t random64(uint64_t & s) { s ^= s << 13; s ^= s >> 7; s ^= s << 17; return s; }
__global__ static void gather_rows(const uint8_t * src, const uint32_t * positions, uint8_t * out) {
    int t=blockIdx.x*blockDim.x+threadIdx.x;
    if (t<16*90) out[t]=src[positions[t/90]*90+t%90];
}
template <typename F> static std::vector<double> sample(int n, F fn) {
    std::vector<double> us; us.reserve(n);
    for (int i=0; i<n; ++i) {
        auto t=clock_type::now(); fn(i);
        us.push_back(std::chrono::duration<double,std::micro>(clock_type::now()-t).count());
    }
    return us;
}
static void emit(const char * kind, size_t bytes, const std::vector<double> & us, int dev, int bus) {
    double sum=0; for (double x:us) sum+=x;
    std::printf("{\"kind\":\"%s\",\"bytes\":%zu,\"count\":%zu,\"mean_us\":%.3f,\"p50_us\":%.3f,\"p95_us\":%.3f,\"device\":%d,\"bus\":%d}\n",
                kind,bytes,us.size(),sum/us.size(),pct(us,.5),pct(us,.95),dev,bus);
    std::fflush(stdout);
}
int main(int argc, char ** argv) {
    if (argc != 4) { std::fprintf(stderr,"usage: ple_bus_probe GGUF tensor_offset row_count\n"); return 2; }
    const uint64_t offset=std::stoull(argv[2]), rows=std::stoull(argv[3]);
    constexpr size_t row_bytes=90, big=32ull*1024*1024, region=64ull*1024*1024;
    if (rows < region/row_bytes) return 2;
    try {
        int fd=open(argv[1],O_RDONLY|O_DIRECT);
        if (fd<0) { perror("O_DIRECT open"); return 3; }
        void * block=nullptr; if (posix_memalign(&block,4096,4096)) return 4;
        uint64_t seed=0x1122334455667788ull;
        std::vector<uint64_t> offsets;
        for (int i=0;i<1024;++i) offsets.push_back((offset + (random64(seed)%rows)*row_bytes)&~uint64_t(4095));
        auto cold=sample(1024,[&](int i) { if(pread(fd,block,4096,offsets[i])!=4096) throw std::runtime_error("direct pread"); });
        emit("nvme_direct_4k",4096,cold,-1,-1);
        close(fd); free(block);
        fd=open(argv[1],O_RDONLY); if(fd<0) return 3;
        uint8_t row[90];
        for (int i=0;i<1024;++i) if(pread(fd,row,90,offsets[i])!=90) throw std::runtime_error("warm pread");
        auto warm=sample(1024,[&](int i) { if(pread(fd,row,90,offsets[i])!=90) throw std::runtime_error("warm pread"); });
        emit("file_cached_90b",90,warm,-1,-1);
        close(fd);
        int ndev=0; ck(cudaGetDeviceCount(&ndev));
        for (int dev=0;dev<ndev;++dev) {
            ck(cudaSetDevice(dev)); int bus=-1; ck(cudaDeviceGetAttribute(&bus,cudaDevAttrPciBusId,dev));
            uint8_t * gpu=nullptr; ck(cudaMalloc(&gpu,region));
            void * host=nullptr; ck(cudaMallocHost(&host,big));
            std::vector<uint8_t> pageable(big);
            for(size_t part=0;part<2;++part) {
                for(size_t k=0;k<big;++k) {
                    size_t pos=part*big+k;
                    static_cast<uint8_t *>(host)[k]=uint8_t(((pos/row_bytes)*37+(pos%row_bytes)*13)&255);
                }
                ck(cudaMemcpy(gpu+part*big,host,big,cudaMemcpyHostToDevice));
            }
            seed=0xa1b2c3d4e5f60718ull;
            std::vector<size_t> positions;
            for(int i=0;i<1024;++i) positions.push_back((random64(seed)%(region/row_bytes))*row_bytes);
            for(int i=0;i<30;++i) ck(cudaMemcpy(host,gpu+positions[i],row_bytes,cudaMemcpyDeviceToHost));
            auto small=sample(1024,[&](int i) { ck(cudaMemcpy(pageable.data(),gpu+positions[i],row_bytes,cudaMemcpyDeviceToHost)); });
            emit("gpu_sync_pageable_90b",90,small,dev,bus);
            auto pinned=sample(1024,[&](int i) { ck(cudaMemcpy(host,gpu+positions[i],row_bytes,cudaMemcpyDeviceToHost)); });
            emit("gpu_sync_pinned_90b",90,pinned,dev,bus);
            auto fourk=sample(256,[&](int i) { ck(cudaMemcpy(host,gpu+(positions[i]&~size_t(4095)),4096,cudaMemcpyDeviceToHost)); });
            emit("gpu_sync_pinned_4k",4096,fourk,dev,bus);
            uint32_t * dpositions=nullptr; uint8_t * gathered=nullptr;
            ck(cudaMalloc(&dpositions,16*sizeof(uint32_t))); ck(cudaMalloc(&gathered,16*row_bytes));
            uint32_t batch[16];
            auto singles=sample(128,[&](int i) {
                for(int j=0;j<16;++j) ck(cudaMemcpy(static_cast<uint8_t *>(host)+j*row_bytes,
                     gpu+positions[(i*16+j)%1024],row_bytes,cudaMemcpyDeviceToHost));
            });
            emit("gpu_16_sync_rows",16*row_bytes,singles,dev,bus);
            for(int j=0;j<16;++j) batch[j]=uint32_t(positions[j]/row_bytes);
            ck(cudaMemcpy(dpositions,batch,sizeof(batch),cudaMemcpyHostToDevice));
            gather_rows<<<6,256>>>(gpu,dpositions,gathered);
            ck(cudaGetLastError()); ck(cudaDeviceSynchronize());
            auto gathered_us=sample(128,[&](int i) {
                for(int j=0;j<16;++j) batch[j]=uint32_t(positions[(i*16+j)%1024]/row_bytes);
                ck(cudaMemcpy(dpositions,batch,sizeof(batch),cudaMemcpyHostToDevice));
                gather_rows<<<6,256>>>(gpu,dpositions,gathered);
                ck(cudaGetLastError());
                ck(cudaMemcpy(host,gathered,16*row_bytes,cudaMemcpyDeviceToHost));
            });
            emit("gpu_16_gathered_rows",16*row_bytes,gathered_us,dev,bus);
            for(int j=0;j<16;++j) for(size_t k=0;k<row_bytes;++k) {
                size_t pos=positions[(127*16+j)%1024]+k;
                uint8_t want=uint8_t(((pos/row_bytes)*37+(pos%row_bytes)*13)&255);
                if(static_cast<uint8_t *>(host)[j*row_bytes+k]!=want) throw std::runtime_error("gather mismatch");
            }
            ck(cudaFree(dpositions)); ck(cudaFree(gathered));
            auto bulk=sample(16,[&](int i) { ck(cudaMemcpy(host,gpu,big,cudaMemcpyDeviceToHost)); });
            emit("gpu_bulk_d2h_32m",big,bulk,dev,bus);
            auto upload=sample(16,[&](int i) { ck(cudaMemcpy(gpu,host,big,cudaMemcpyHostToDevice)); });
            emit("gpu_bulk_h2d_32m",big,upload,dev,bus);
            auto local=sample(16,[&](int i) { ck(cudaMemcpy(gpu+big,gpu,big,cudaMemcpyDeviceToDevice)); ck(cudaDeviceSynchronize()); });
            emit("gpu_local_d2d_32m",big,local,dev,bus);
            ck(cudaFreeHost(host)); ck(cudaFree(gpu));
        }
        return 0;
    } catch(const std::exception & e) { std::fprintf(stderr,"BUS_PROBE_ERROR %s\n",e.what()); return 1; }
}
