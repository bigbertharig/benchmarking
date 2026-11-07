from pathlib import Path
import sys

root = Path(sys.argv[1])
cache = root / "src/llama-kv-cache.cpp"
text = cache.read_text()
text = text.replace("#include <cstring>\n", "#include <cstring>\n#include <cstdlib>\n", 1)
old = """            auto * dev = model.dev_layer(il);
            buft = ggml_backend_dev_buffer_type(dev);
"""
new = """            auto * dev = model.dev_layer(il);
            if (const char * selected = std::getenv("LLAMA_KV_DEVICE_INDEX")) {
                const int index = std::atoi(selected);
                if (index < 0 || index >= (int) model.devices.size()) {
                    throw std::runtime_error("invalid LLAMA_KV_DEVICE_INDEX");
                }
                dev = model.devices[index].dev;
            }
            buft = ggml_backend_dev_buffer_type(dev);
"""
assert text.count(old) == 1
cache.write_text(text.replace(old, new, 1))

graph = root / "src/llama-graph.cpp"
text = graph.read_text()
old = """        ggml_prec_set_acc(cur, GGML_PREC_F32);

        if (v_mla) {
"""
new = """        ggml_prec_set_acc(cur, GGML_PREC_F32);
        cb(cur, "kv_fattn", il);

        if (v_mla) {
"""
assert text.count(old) == 1
graph.write_text(text.replace(old, new, 1))

context = root / "src/llama-context.cpp"
text = context.read_text().replace("#include <cstring>\n", "#include <cstring>\n#include <cstdlib>\n", 1)
old = """        // - norm may be automatically assigned to the backend of the previous layer, increasing data transfer between backends
"""
new = """        if (strcmp(name, "kv_fattn") == 0) {
            if (const char * selected = std::getenv("LLAMA_KV_DEVICE_INDEX")) {
                const int index = std::atoi(selected);
                if (index >= 0 && index < (int) model.devices.size()) {
                    const auto dev = model.devices[index].dev;
                    for (const auto & backend : backends) {
                        if (ggml_backend_get_device(backend.get()) == dev &&
                            ggml_backend_supports_op(backend.get(), cur)) {
                            ggml_backend_sched_set_tensor_backend(sched.get(), cur, backend.get());
                        }
                    }
                }
            }
        }

        // - norm may be automatically assigned to the backend of the previous layer, increasing data transfer between backends
"""
assert text.count(old) == 1
context.write_text(text.replace(old, new, 1))

simple = root / "examples/simple/simple.cpp"
simple.write_text(r'''#include "llama.h"
#include "ggml-backend.h"

#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

int main(int argc, char ** argv) {
    if (argc != 2) {
        std::fprintf(stderr, "usage: llama-simple MODEL.gguf\n");
        return 2;
    }
    ggml_backend_load_all();
    auto mp = llama_model_default_params();
    mp.n_gpu_layers = 99;
    mp.split_mode = LLAMA_SPLIT_MODE_NONE;
    mp.main_gpu = 0;
    llama_model * model = llama_model_load_from_file(argv[1], mp);
    if (!model) return 3;

    const llama_vocab * vocab = llama_model_get_vocab(model);
    const std::string prompts[] = {"The capital of France is", "The capital of Japan is"};
    llama_context * contexts[2] = {};
    llama_sampler * samplers[2] = {};
    std::vector<llama_token> batches[2];
    for (int i = 0; i < 2; ++i) {
        std::string index = std::to_string(i + 1);
        setenv("LLAMA_KV_DEVICE_INDEX", index.c_str(), 1);
        auto cp = llama_context_default_params();
        cp.n_ctx = 4096;
        cp.n_batch = 512;
        cp.n_ubatch = 512;
        cp.n_seq_max = 1;
        cp.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_ENABLED;
        contexts[i] = llama_init_from_model(model, cp);
        if (!contexts[i]) return 4;
        const int n = -llama_tokenize(vocab, prompts[i].c_str(), prompts[i].size(), nullptr, 0, true, true);
        batches[i].resize(n);
        if (llama_tokenize(vocab, prompts[i].c_str(), prompts[i].size(), batches[i].data(), n, true, true) != n) return 5;
        samplers[i] = llama_sampler_init_greedy();
        std::fprintf(stderr, "CHAT %d created KV device %s with %d prompt tokens\n", i, index.c_str(), n);
    }

    for (int step = 0; step < 4; ++step) {
        for (int i = 0; i < 2; ++i) {
            std::string index = std::to_string(i + 1);
            setenv("LLAMA_KV_DEVICE_INDEX", index.c_str(), 1);
            auto batch = llama_batch_get_one(batches[i].data(), batches[i].size());
            const int rc = llama_decode(contexts[i], batch);
            if (rc) {
                std::fprintf(stderr, "CHAT %d decode step %d failed rc=%d\n", i, step, rc);
                return 6;
            }
            llama_token token = llama_sampler_sample(samplers[i], contexts[i], -1);
            char piece[256];
            int len = llama_token_to_piece(vocab, token, piece, sizeof(piece), 0, true);
            if (len < 0) return 7;
            std::printf("CHAT %d step %d token %d text %.*s\n", i, step, token, len, piece);
            std::fflush(stdout);
            batches[i].assign(1, token);
        }
    }
    for (int i = 0; i < 2; ++i) {
        llama_sampler_free(samplers[i]);
        llama_free(contexts[i]);
    }
    llama_model_free(model);
    return 0;
}
''')
