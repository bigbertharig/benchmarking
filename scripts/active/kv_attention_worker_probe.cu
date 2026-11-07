// Synthetic one-head attention with five independently resident KV caches.
// This tests placement and transfers, not llama.cpp integration or Q4 kernels.
#include <cuda_fp16.h>
#include <cuda_runtime.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <mutex>
#include <condition_variable>
#include <thread>
#include <vector>

#define CK(x) do { cudaError_t e=(x); if(e!=cudaSuccess) { std::cerr << #x << ": " << cudaGetErrorString(e) << "\n"; std::exit(2); } } while(0)
constexpr int D=128;
constexpr int B=256;

__global__ void init_kv(__half* k, __half* v, int tokens, float marker) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;
    if(i<tokens*D) {
        k[i]=__float2half(float((i/D)%17)/17.0f);
        v[i]=__float2half(marker);
    }
}

__global__ void attention_parts(const __half* k, const __half* v, const float* q,
                                 int tokens, float* maxima, float* sums, float* weighted) {
    __shared__ float score[B];
    __shared__ float tmp[B];
    int t=blockIdx.x*B+threadIdx.x;
    float s=-1.0e30f;
    if(t<tokens) {
        s=0;
        for(int d=0;d<D;d++) s+=__half2float(k[t*D+d])*q[d];
        s*=0.08838834765f; // 1/sqrt(128)
    }
    score[threadIdx.x]=s;
    tmp[threadIdx.x]=s;
    __syncthreads();
    for(int stride=B/2;stride;stride/=2) {
        if(threadIdx.x<stride) tmp[threadIdx.x]=fmaxf(tmp[threadIdx.x],tmp[threadIdx.x+stride]);
        __syncthreads();
    }
    float m=tmp[0];
    float w=t<tokens?expf(s-m):0.0f;
    score[threadIdx.x]=w;
    tmp[threadIdx.x]=w;
    __syncthreads();
    for(int stride=B/2;stride;stride/=2) {
        if(threadIdx.x<stride) tmp[threadIdx.x]+=tmp[threadIdx.x+stride];
        __syncthreads();
    }
    if(threadIdx.x==0) { maxima[blockIdx.x]=m; sums[blockIdx.x]=tmp[0]; }
    if(threadIdx.x<D) {
        float acc=0;
        for(int j=0;j<B;j++) {
            int row=blockIdx.x*B+j;
            if(row<tokens) acc+=score[j]*__half2float(v[row*D+threadIdx.x]);
        }
        weighted[blockIdx.x*D+threadIdx.x]=acc;
    }
}

__global__ void finish_attention(const float* maxima, const float* sums,
                                  const float* weighted, int blocks, float* output) {
    int d=threadIdx.x;
    float m=-1.0e30f;
    for(int b=0;b<blocks;b++) m=fmaxf(m,maxima[b]);
    float denom=0,numer=0;
    for(int b=0;b<blocks;b++) {
        float scale=expf(maxima[b]-m);
        denom+=scale*sums[b];
        numer+=scale*weighted[b*D+d];
    }
    output[d]=numer/denom;
}

struct Worker {
    int gpu;
    void* cache=nullptr;
    void* scratch=nullptr;
    float* q=nullptr;
    float* out=nullptr;
    float* h_out=nullptr;
    cudaStream_t stream=nullptr;
};

int main(int argc,char** argv) {
    if(argc!=4) { std::cerr<<"usage: probe TOKENS CACHE_MIB ITERS\n"; return 64; }
    int tokens=std::atoi(argv[1]), cache_mib=std::atoi(argv[2]), iters=std::atoi(argv[3]);
    if(tokens<1||cache_mib<1||iters<1) return 64;
    const int blocks=(tokens+B-1)/B;
    const size_t kv_bytes=size_t(tokens)*D*2*sizeof(__half);
    if(kv_bytes>size_t(cache_mib)*1048576) { std::cerr<<"cache too small\n"; return 64; }
    CK(cudaSetDevice(0));
    float *d_q0=nullptr,*d_out0=nullptr,*h_q=nullptr;
    CK(cudaMalloc(&d_q0,D*sizeof(float)));
    CK(cudaMalloc(&d_out0,5*D*sizeof(float)));
    CK(cudaHostAlloc(&h_q,D*sizeof(float),cudaHostAllocPortable));
    for(int d=0;d<D;d++) h_q[d]=0.25f;
    CK(cudaMemcpy(d_q0,h_q,D*sizeof(float),cudaMemcpyHostToDevice));
    std::vector<Worker> workers(5);
    for(int i=0;i<5;i++) {
        Worker& w=workers[i];w.gpu=i+1;
        CK(cudaSetDevice(w.gpu));
        CK(cudaStreamCreate(&w.stream));
        CK(cudaMalloc(&w.cache,size_t(cache_mib)*1048576));
        CK(cudaMalloc(&w.scratch,1024ull*1048576));
        CK(cudaMalloc(&w.q,D*sizeof(float)));
        CK(cudaMalloc(&w.out,D*sizeof(float)));
        CK(cudaHostAlloc(&w.h_out,D*sizeof(float),cudaHostAllocPortable));
        auto* k=reinterpret_cast<__half*>(w.cache);
        auto* v=k+size_t(tokens)*D;
        init_kv<<<(size_t(tokens)*D+255)/256,256,0,w.stream>>>(k,v,tokens,float(i+1));
        CK(cudaGetLastError());CK(cudaStreamSynchronize(w.stream));
    }
    std::mutex mu; std::condition_variable start,done; int epoch=0,completed=0;bool stop=false;
    std::vector<std::thread> threads;
    for(int i=0;i<5;i++) threads.emplace_back([&,i] {
        Worker& w=workers[i];CK(cudaSetDevice(w.gpu));int seen=0;
        auto* k=reinterpret_cast<__half*>(w.cache);
        auto* v=k+size_t(tokens)*D;
        char* base=reinterpret_cast<char*>(w.scratch);
        float* maxima=reinterpret_cast<float*>(base);
        float* sums=maxima+blocks;
        float* weighted=sums+blocks;
        while(true) {
            {std::unique_lock<std::mutex> lock(mu);start.wait(lock,[&]{return stop||epoch>seen;});if(stop)return;seen=epoch;}
            CK(cudaMemcpyAsync(w.q,h_q,D*sizeof(float),cudaMemcpyHostToDevice,w.stream));
            attention_parts<<<blocks,B,0,w.stream>>>(k,v,w.q,tokens,maxima,sums,weighted);
            CK(cudaGetLastError());
            finish_attention<<<1,D,0,w.stream>>>(maxima,sums,weighted,blocks,w.out);
            CK(cudaGetLastError());
            CK(cudaMemcpyAsync(w.h_out,w.out,D*sizeof(float),cudaMemcpyDeviceToHost,w.stream));
            CK(cudaStreamSynchronize(w.stream));
            {std::lock_guard<std::mutex> lock(mu);completed++;}done.notify_one();
        }
    });
    std::vector<double> samples;
    for(int step=0;step<iters+2;step++) {
        auto begin=std::chrono::steady_clock::now();
        CK(cudaSetDevice(0));CK(cudaMemcpy(h_q,d_q0,D*sizeof(float),cudaMemcpyDeviceToHost));
        {std::lock_guard<std::mutex> lock(mu);completed=0;epoch++;}start.notify_all();
        {std::unique_lock<std::mutex> lock(mu);done.wait(lock,[&]{return completed==5;});}
        for(int i=0;i<5;i++) CK(cudaMemcpy(d_out0+i*D,workers[i].h_out,D*sizeof(float),cudaMemcpyHostToDevice));
        if(step>=2) samples.push_back(std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count());
    }
    {std::lock_guard<std::mutex> lock(mu);stop=true;}start.notify_all();for(auto& t:threads)t.join();
    std::vector<float> returned(5*D);
    CK(cudaSetDevice(0));
    CK(cudaMemcpy(returned.data(),d_out0,returned.size()*sizeof(float),cudaMemcpyDeviceToHost));
    bool verified=true;
    for(int i=0;i<5;i++) for(int d=0;d<D;d++)
        if(fabsf(returned[i*D+d]-float(i+1))>0.002f) verified=false;
    std::sort(samples.begin(),samples.end());
    std::cout<<"{\"schema\":\"kv-attention-worker-probe/1\",\"tokens\":"<<tokens
             <<",\"cache_mib_per_gpu\":"<<cache_mib<<",\"workspace_mib_per_gpu\":1024"
             <<",\"active_fp16_kv_mib_per_gpu\":"<<double(kv_bytes)/1048576
             <<",\"workers\":5,\"verified\":"<<(verified?"true":"false")
             <<",\"iterations\":"<<iters<<",\"p50_ms\":"<<samples[samples.size()/2]
             <<",\"min_ms\":"<<samples.front()<<",\"max_ms\":"<<samples.back()<<"}\n";
    for(auto& w:workers) {CK(cudaSetDevice(w.gpu));CK(cudaFree(w.out));CK(cudaFree(w.q));CK(cudaFree(w.scratch));CK(cudaFree(w.cache));CK(cudaFreeHost(w.h_out));CK(cudaStreamDestroy(w.stream));}
    CK(cudaSetDevice(0));CK(cudaFree(d_out0));CK(cudaFree(d_q0));CK(cudaFreeHost(h_q));
    return verified?0:3;
}
