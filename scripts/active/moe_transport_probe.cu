#include <cuda_runtime.h>
#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <iostream>
#include <mutex>
#include <numeric>
#include <string>
#include <thread>
#include <vector>

#define CK(x) do { cudaError_t e=(x); if(e!=cudaSuccess){std::cerr << #x << ": " << cudaGetErrorString(e) << "\n"; std::exit(2);} } while(0)

__global__ void copy_kernel(const float* in, float* out, int n) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;
    if(i<n) out[i]=in[i];
}
struct Worker {
    int gpu=0;
    cudaStream_t stream=nullptr;
    float* d_in=nullptr;
    float* d_out=nullptr;
    float* h_out=nullptr;
};
int main(int argc,char** argv) {
    if(argc!=5){std::cerr<<"usage: probe WORKERS WIDTH copy|kernel ITERS\n";return 64;}
    int workers=std::atoi(argv[1]), width=std::atoi(argv[2]), iters=std::atoi(argv[4]);
    std::string mode=argv[3];
    if(workers<1||workers>5||width<1||iters<1||(mode!="copy"&&mode!="kernel"))return 64;
    int count=0; CK(cudaGetDeviceCount(&count));
    if(count<workers+1){std::cerr<<"insufficient CUDA devices\n";return 2;}
    size_t bytes=size_t(width)*sizeof(float);
    CK(cudaSetDevice(0));
    cudaStream_t master_stream; CK(cudaStreamCreate(&master_stream));
    float *d_hidden=nullptr,*d_combined=nullptr,*h_master=nullptr,*h_sum=nullptr;
    CK(cudaMalloc((void**)&d_hidden,bytes));
    CK(cudaMalloc((void**)&d_combined,bytes));
    CK(cudaHostAlloc((void**)&h_master,bytes,cudaHostAllocPortable));
    CK(cudaHostAlloc((void**)&h_sum,bytes,cudaHostAllocPortable));
    for(int j=0;j<width;j++)h_master[j]=float(j%17+1);
    CK(cudaMemcpy(d_hidden,h_master,bytes,cudaMemcpyHostToDevice));
    std::vector<Worker> ws(workers);
    std::vector<int> p2p(workers);
    for(int i=0;i<workers;i++){
        CK(cudaSetDevice(0)); CK(cudaDeviceCanAccessPeer(&p2p[i],0,i+1));
        Worker& w=ws[i];w.gpu=i+1;
        CK(cudaSetDevice(w.gpu));
        CK(cudaStreamCreate(&w.stream));
        CK(cudaMalloc((void**)&w.d_in,bytes));
        CK(cudaMalloc((void**)&w.d_out,bytes));
        CK(cudaHostAlloc((void**)&w.h_out,bytes,cudaHostAllocPortable));
    }
    std::mutex mu; std::condition_variable start,done_cv;
    int epoch=0,completed=0; bool stopping=false;
    std::vector<std::thread> threads;
    for(int i=0;i<workers;i++){
        threads.emplace_back([&,i]{
            Worker& w=ws[i];CK(cudaSetDevice(w.gpu));int seen=0;
            while(true){
                {std::unique_lock<std::mutex> lock(mu);
                 start.wait(lock,[&]{return stopping||epoch>seen;});
                 if(stopping)return;
                 seen=epoch;}
                CK(cudaMemcpyAsync(w.d_in,h_master,bytes,cudaMemcpyHostToDevice,w.stream));
                float* source=w.d_in;
                if(mode=="kernel"){
                    copy_kernel<<<(width+255)/256,256,0,w.stream>>>(w.d_in,w.d_out,width);
                    CK(cudaGetLastError());source=w.d_out;
                }
                CK(cudaMemcpyAsync(w.h_out,source,bytes,cudaMemcpyDeviceToHost,w.stream));
                CK(cudaStreamSynchronize(w.stream));
                {std::lock_guard<std::mutex> lock(mu);completed++;}
                done_cv.notify_one();
            }
        });
    }
    std::vector<double> samples;samples.reserve(iters);
    for(int step=0;step<iters+20;step++){
        auto before=std::chrono::steady_clock::now();
        CK(cudaSetDevice(0));
        CK(cudaMemcpyAsync(h_master,d_hidden,bytes,cudaMemcpyDeviceToHost,master_stream));
        CK(cudaStreamSynchronize(master_stream));
        {std::lock_guard<std::mutex> lock(mu);completed=0;epoch++;}
        start.notify_all();
        {std::unique_lock<std::mutex> lock(mu);
         done_cv.wait(lock,[&]{return completed==workers;});}
        for(int j=0;j<width;j++){
            float value=0;
            for(int i=0;i<workers;i++)value+=ws[i].h_out[j];
            h_sum[j]=value;
        }
        CK(cudaMemcpyAsync(d_combined,h_sum,bytes,cudaMemcpyHostToDevice,master_stream));
        CK(cudaStreamSynchronize(master_stream));
        auto after=std::chrono::steady_clock::now();
        if(step>=20)samples.push_back(std::chrono::duration<double,std::micro>(after-before).count());
    }
    CK(cudaSetDevice(0));
    CK(cudaMemcpy(h_master,d_combined,bytes,cudaMemcpyDeviceToHost));
    if(h_master[0]!=float(workers)||h_master[width-1]!=float(workers*((width-1)%17+1))){std::cerr<<"result verification failed\n";return 3;}
    {std::lock_guard<std::mutex> lock(mu);stopping=true;}
    start.notify_all();for(auto& t:threads)t.join();
    double mean=std::accumulate(samples.begin(),samples.end(),0.0)/samples.size();
    std::sort(samples.begin(),samples.end());
    double p50=samples[samples.size()/2],p95=samples[size_t(samples.size()*0.95)];
    std::cout<<"{\"workers\":"<<workers<<",\"width\":"<<width<<",\"bytes_each_way\":"<<bytes
             <<",\"mode\":\""<<mode<<"\",\"iterations\":"<<iters
             <<",\"verified\":true,\"mean_us\":"<<mean<<",\"p50_us\":"<<p50<<",\"p95_us\":"<<p95
             <<",\"gpu0_peer_access\":[";
    for(int i=0;i<workers;i++){if(i)std::cout<<",";std::cout<<p2p[i];}
    std::cout<<"]}\n";
    for(auto& w:ws){CK(cudaSetDevice(w.gpu));CK(cudaFree(w.d_in));CK(cudaFree(w.d_out));CK(cudaFreeHost(w.h_out));CK(cudaStreamDestroy(w.stream));}
    CK(cudaSetDevice(0));CK(cudaFree(d_hidden));CK(cudaFree(d_combined));CK(cudaFreeHost(h_master));CK(cudaFreeHost(h_sum));CK(cudaStreamDestroy(master_stream));
    return 0;
}