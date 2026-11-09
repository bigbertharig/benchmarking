from pathlib import Path

path = Path('/data/bench-staging/kvchat-b11669-src/examples/simple/simple.cpp')
text = path.read_text()
assert '#include <dlfcn.h>' not in text
text = text.replace('#include <algorithm>', '#include <dlfcn.h>\n#include <algorithm>', 1)
old = '''        for (int depth : {16384, 32768, 50000}) {
            const std::string path = std::string(source_dir) + "/worker1_depth" +
'''
new = '''        const char * trace_depth_env = std::getenv("KV_REPLAY_DEPTH");
        const int trace_depth = trace_depth_env && *trace_depth_env ? std::atoi(trace_depth_env) : 0;
        if (trace_depth && trace_depth != 16384 && trace_depth != 32768 && trace_depth != 50000) return 214;
        const bool trace_cuda = std::getenv("KV_TRACE_CUDA") && std::string(std::getenv("KV_TRACE_CUDA")) == "1";
        void * cudart = trace_cuda ? dlopen("libcudart.so.12", RTLD_NOW | RTLD_LOCAL) : nullptr;
        using profiler_fn = int (*)();
        const auto profiler_start = cudart ? reinterpret_cast<profiler_fn>(dlsym(cudart, "cudaProfilerStart")) : nullptr;
        const auto profiler_stop = cudart ? reinterpret_cast<profiler_fn>(dlsym(cudart, "cudaProfilerStop")) : nullptr;
        if (trace_cuda && (!profiler_start || !profiler_stop)) return 215;
        for (int depth : {16384, 32768, 50000}) {
            if (trace_depth && depth != trace_depth) continue;
            const std::string path = std::string(source_dir) + "/worker1_depth" +
'''
assert text.count(old) == 1
text = text.replace(old, new, 1)
old = '''            if (!measured_parallel(vocab, {&worker}, tokens, phase.c_str())) return 213;
            std::fprintf(stderr, "ONE_REPLAY_DONE depth=%d gpu=1 tokens=%d\\n", depth, tokens);
'''
new = '''            if (trace_cuda && profiler_start() != 0) return 216;
            const bool generated = measured_parallel(vocab, {&worker}, tokens, phase.c_str());
            if (trace_cuda && profiler_stop() != 0) return 217;
            if (!generated) return 213;
            std::fprintf(stderr, "ONE_REPLAY_DONE depth=%d gpu=1 tokens=%d\\n", depth, tokens);
'''
assert text.count(old) == 1
text = text.replace(old, new, 1)
path.write_text(text)
