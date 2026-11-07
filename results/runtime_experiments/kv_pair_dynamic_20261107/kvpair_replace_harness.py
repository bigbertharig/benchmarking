from pathlib import Path
import sys

path = Path(sys.argv[1]) / "examples/simple/simple.cpp"
path.write_text(r'''#include "llama.h"
#include "ggml-backend.h"

#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

struct chat {
    const char * prompt;
    const char * expected;
    const char * pair;
    const char * single;
    llama_context * ctx = nullptr;
    llama_sampler * sampler = nullptr;
    std::vector<llama_token> next;
    int steps = 0;
};

static void select_chat(const chat & c) {
    if (c.pair) { setenv("LLAMA_KV_DEVICE_PAIR", c.pair, 1); unsetenv("LLAMA_KV_DEVICE_INDEX"); }
    else { unsetenv("LLAMA_KV_DEVICE_PAIR"); setenv("LLAMA_KV_DEVICE_INDEX", c.single, 1); }
}

static bool add_chat(chat & c, llama_model * model, const llama_vocab * vocab, int ctx_size) {
    select_chat(c);
    auto cp = llama_context_default_params();
    cp.n_ctx = ctx_size;
    cp.n_batch = 64;
    cp.n_ubatch = 8;
    cp.n_seq_max = 1;
    cp.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_ENABLED;
    cp.type_k = GGML_TYPE_Q4_0;
    cp.type_v = GGML_TYPE_Q4_0;
    c.ctx = llama_init_from_model(model, cp);
    if (!c.ctx) return false;
    const std::string prompt(c.prompt);
    int n = -llama_tokenize(vocab, prompt.c_str(), prompt.size(), nullptr, 0, true, true);
    c.next.resize(n);
    if (llama_tokenize(vocab, prompt.c_str(), prompt.size(), c.next.data(), n, true, true) != n) return false;
    c.sampler = llama_sampler_init_greedy();
    std::fprintf(stderr, "ADD_CHAT pair=%s single=%s ctx=%d prompt_tokens=%d\n",
                 c.pair ? c.pair : "-", c.single ? c.single : "-", ctx_size, n);
    return true;
}

static bool decode(chat & c, const llama_vocab * vocab) {
    select_chat(c);
    auto batch = llama_batch_get_one(c.next.data(), c.next.size());
    int rc = llama_decode(c.ctx, batch);
    if (rc) {
        std::fprintf(stderr, "DECODE_FAILED pair=%s single=%s step=%d rc=%d\n",
                     c.pair ? c.pair : "-", c.single ? c.single : "-", c.steps, rc);
        return false;
    }
    llama_token token = llama_sampler_sample(c.sampler, c.ctx, -1);
    char piece[256];
    int len = llama_token_to_piece(vocab, token, piece, sizeof(piece), 0, true);
    if (len < 0) return false;
    const std::string text(piece, len);
    std::printf("CHAT pair=%s single=%s step=%d token=%d text=%s\n",
                c.pair ? c.pair : "-", c.single ? c.single : "-", c.steps, token, text.c_str());
    std::fflush(stdout);
    if (c.steps == 0 && text.find(c.expected) == std::string::npos) return false;
    c.next.assign(1, token);
    ++c.steps;
    return true;
}

int main(int argc, char ** argv) {
    if (argc != 4) {
        std::fprintf(stderr, "usage: llama-simple MODEL.gguf PAIR_CONTEXT SINGLE_CONTEXT\n");
        return 2;
    }
    ggml_backend_load_all();
    auto mp = llama_model_default_params();
    mp.n_gpu_layers = 99;
    mp.split_mode = LLAMA_SPLIT_MODE_NONE;
    mp.main_gpu = 0;
    llama_model * model = llama_model_load_from_file(argv[1], mp);
    if (!model) return 3;
    std::fprintf(stderr, "MODEL_READY one weight load\n");
    const llama_vocab * vocab = llama_model_get_vocab(model);
    chat a{"The capital of France is", "Paris", "1,2", nullptr};
    chat b{"The capital of Japan is", "Tokyo", "3,4", nullptr};
    chat c{"The capital of Spain is", "Madrid", nullptr, "5"};
    const int pair_ctx = std::atoi(argv[2]);
    const int single_ctx = std::atoi(argv[3]);

    if (!add_chat(a, model, vocab, pair_ctx)) return 4;
    if (!decode(a, vocab) || !decode(a, vocab)) return 5;
    std::fprintf(stderr, "PHASE_1_READY first pair continued before adding second\n");

    if (!add_chat(b, model, vocab, pair_ctx)) return 6;
    if (!decode(b, vocab) || !decode(a, vocab) || !decode(b, vocab)) return 7;
    std::fprintf(stderr, "PHASE_2_READY two pairs live; first pair continued\n");

    if (!add_chat(c, model, vocab, single_ctx)) return 8;
    if (!decode(c, vocab) || !decode(a, vocab) || !decode(b, vocab) || !decode(c, vocab)) return 9;
    std::fprintf(stderr, "PHASE_3_READY added single GPU5 chat; earlier pairs continued\n");

    for (chat * item : {&a, &b, &c}) {
        llama_sampler_free(item->sampler);
        llama_free(item->ctx);
    }
    llama_model_free(model);
    return 0;
}
''')
