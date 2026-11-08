#include "llama.h"
#include "ggml-backend.h"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <atomic>
#include <thread>
#include <vector>
#include <sstream>
#include <deque>
#include <fstream>

using clock_type = std::chrono::steady_clock;

struct chat {
    const char * name;
    const char * prompt;
    const char * pair;
    const char * single;
    llama_context * ctx = nullptr;
    llama_sampler * sampler = nullptr;
    std::vector<llama_token> next;
    int used = 0;
};

extern "C" void llama_kv_chat_select(int first, int second);

static void select_chat(const chat & c) {
    if (c.pair) {
        int first = -1, second = -1;
        if (std::sscanf(c.pair, "%d,%d", &first, &second) != 2) std::abort();
        llama_kv_chat_select(first, second);
    } else {
        llama_kv_chat_select(std::atoi(c.single), -1);
    }
}

static bool add_chat(chat & c, llama_model * model, const llama_vocab * vocab, int cap, bool fast = false) {
    select_chat(c);
    auto cp = llama_context_default_params();
    cp.n_ctx = cap;
    cp.n_batch = fast ? 512 : 64;
    cp.n_ubatch = fast ? 32 : 8;
    cp.n_seq_max = 1;
    cp.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_ENABLED;
    cp.type_k = GGML_TYPE_Q4_0;
    cp.type_v = GGML_TYPE_Q4_0;
    if (c.single && std::string(c.single) == "-1") cp.offload_kqv = false;
    c.ctx = llama_init_from_model(model, cp);
    if (!c.ctx) return false;
    const std::string prompt(c.prompt);
    const int n = -llama_tokenize(vocab, prompt.c_str(), prompt.size(), nullptr, 0, true, true);
    c.next.resize(n);
    if (llama_tokenize(vocab, prompt.c_str(), prompt.size(), c.next.data(), n, true, true) != n) return false;
    c.sampler = llama_sampler_init_greedy();
    std::fprintf(stderr, "ADD name=%s pair=%s single=%s cap=%d prompt=%d\n",
                 c.name, c.pair ? c.pair : "-", c.single ? c.single : "-", cap, n);
    return true;
}

static bool decode(chat & c, const llama_vocab * vocab, bool report = false) {
    select_chat(c);
    const int count = (int)c.next.size();
    if (llama_decode(c.ctx, llama_batch_get_one(c.next.data(), count))) return false;
    c.used += count;
    const llama_token token = llama_sampler_sample(c.sampler, c.ctx, -1);
    if (report) {
        char piece[256];
        const int len = llama_token_to_piece(vocab, token, piece, sizeof(piece), 0, true);
        std::fprintf(stderr, "FIRST name=%s token=%d text=%.*s\n", c.name, token,
                     std::max(0, len), piece);
    }
    c.next.assign(1, token);
    return true;
}

static bool bench(chat & c, const llama_vocab * vocab, int tokens, const char * phase) {
    const auto start = clock_type::now();
    for (int i = 0; i < tokens; ++i) {
        if (!decode(c, vocab)) return false;
    }
    const double seconds = std::chrono::duration<double>(clock_type::now() - start).count();
    std::fprintf(stderr, "BENCH name=%s phase=%s used=%d tokens=%d seconds=%.6f tps=%.6f\n",
                 c.name, phase, c.used, tokens, seconds, tokens / seconds);
    return true;
}

static bool fill(chat & c, int target, int block_size = 64) {
    select_chat(c);
    const llama_token filler = c.next[0];
    std::vector<llama_token> block(block_size, filler);
    const auto start = clock_type::now();
    int last_report = c.used;
    while (c.used < target) {
        const int count = std::min(block_size, target - c.used);
        if (llama_decode(c.ctx, llama_batch_get_one(block.data(), count))) return false;
        c.used += count;
        if (c.used - last_report >= 8192 || c.used == target) {
            const double seconds = std::chrono::duration<double>(clock_type::now() - start).count();
            std::fprintf(stderr, "FILL_PROGRESS name=%s used=%d target=%d seconds=%.2f\n",
                         c.name, c.used, target, seconds);
            std::fflush(stderr);
            last_report = c.used;
        }
    }
    c.next.assign(1, llama_sampler_sample(c.sampler, c.ctx, -1));
    const double seconds = std::chrono::duration<double>(clock_type::now() - start).count();
    std::fprintf(stderr, "FILL_DONE name=%s target=%d seconds=%.6f tps=%.6f\n",
                 c.name, target, seconds, target / seconds);
    return true;
}

static std::vector<llama_token> tokenize_text(const llama_vocab * vocab,
                                               const std::string & value,
                                               bool add_special) {
    const int n = -llama_tokenize(vocab, value.c_str(), value.size(), nullptr, 0,
                                  add_special, true);
    std::vector<llama_token> tokens(n);
    if (llama_tokenize(vocab, value.c_str(), value.size(), tokens.data(), n,
                       add_special, true) != n) return {};
    return tokens;
}

static bool decode_raw(chat & c, const std::vector<llama_token> & tokens,
                       int target = -1) {
    select_chat(c);
    const int length = target < 0 ? (int)tokens.size() : target;
    if (tokens.empty() || length < 0) return false;
    std::vector<llama_token> block;
    for (int pos = 0; pos < length;) {
        const int count = std::min(512, length - pos);
        block.resize(count);
        for (int j = 0; j < count; ++j) block[j] = tokens[(pos + j) % tokens.size()];
        if (llama_decode(c.ctx, llama_batch_get_one(block.data(), count))) return false;
        c.used += count;
        pos += count;
    }
    return true;
}

static bool recall_answer(chat & c, const llama_vocab * vocab,
                          const char * expected, int depth, int max_tokens) {
    c.next = tokenize_text(vocab,
        "\nWhat was the four-digit code at the beginning? Answer with only the four digits. /no_think"
        "\n<|im_end|>\n<|im_start|>assistant\n<think>\n</think>\n", false);
    if (c.next.empty()) return false;
    std::string answer;
    for (int i = 0; i < max_tokens; ++i) {
        if (!decode(c, vocab)) return false;
        char piece[256];
        const int len = llama_token_to_piece(vocab, c.next[0], piece, sizeof(piece), 0, true);
        if (len > 0) answer.append(piece, len);
        if (llama_vocab_is_eog(vocab, c.next[0])) break;
    }
    const bool evidence = answer.find(expected) != std::string::npos;
    const auto think_end = answer.rfind("</think>");
    const bool final_visible = think_end != std::string::npos ||
                               answer.find("<think>") == std::string::npos;
    const std::string final_text = think_end != std::string::npos
        ? answer.substr(think_end + 8) : final_visible ? answer : "";
    const bool final_pass = final_text.find(expected) != std::string::npos;
    for (char & ch : answer) {
        if (ch == '\n' || ch == '\r') ch = ' ';
    }
    std::fprintf(stderr,
        "RECALL_RESULT name=%s depth=%d expected=%s evidence=%d final_visible=%d final_pass=%d answer=%s\n",
        c.name, depth, expected, evidence, final_visible, final_pass, answer.c_str());
    return final_pass;
}

struct snapshot {
    std::vector<uint8_t> data;
    llama_token next = 0;
    int used = 0;
};

static uint64_t fingerprint(const snapshot & state) {
    uint64_t hash = 1469598103934665603ULL;
    for (uint8_t byte : state.data) hash = (hash ^ byte) * 1099511628211ULL;
    return hash;
}

struct snapshot_header {
    uint64_t magic;
    uint64_t length;
    uint64_t hash;
    int32_t used;
    int32_t next;
};

static bool write_snapshot_file(const std::string & path, const snapshot & state) {
    const std::string pending = path + ".tmp";
    FILE * file = std::fopen(pending.c_str(), "wb");
    if (!file) return false;
    const snapshot_header header{0x4b564348415431ULL, state.data.size(),
                                 fingerprint(state), state.used, state.next};
    bool ok = std::fwrite(&header, sizeof(header), 1, file) == 1 &&
              std::fwrite(state.data.data(), 1, state.data.size(), file) == state.data.size() &&
              std::fflush(file) == 0;
    if (std::fclose(file) != 0) ok = false;
    if (!ok) {
        std::remove(pending.c_str());
        return false;
    }
    if (std::rename(pending.c_str(), path.c_str()) != 0) return false;
    std::fprintf(stderr, "STATE_FILE path=%s bytes=%zu hash=%016llx\n",
                 path.c_str(), state.data.size(), (unsigned long long)header.hash);
    return true;
}

static bool read_snapshot_file(const std::string & path, snapshot & state) {
    FILE * file = std::fopen(path.c_str(), "rb");
    if (!file) return false;
    snapshot_header header{};
    bool ok = std::fread(&header, sizeof(header), 1, file) == 1 &&
              header.magic == 0x4b564348415431ULL &&
              header.length > 0 && header.length <= (uint64_t)8 * 1024 * 1024 * 1024;
    if (ok) {
        state.data.resize(header.length);
        ok = std::fread(state.data.data(), 1, state.data.size(), file) == state.data.size();
    }
    ok = std::fclose(file) == 0 && ok;
    if (ok) ok = fingerprint(state) == header.hash;
    if (!ok) return false;
    state.used = header.used;
    state.next = header.next;
    std::fprintf(stderr, "STATE_FILE_READ path=%s bytes=%zu hash=%016llx\n",
                 path.c_str(), state.data.size(), (unsigned long long)header.hash);
    return true;
}

static bool save(chat & c, snapshot & state) {
    select_chat(c);
    const auto start = clock_type::now();
    state.data.resize(llama_state_get_size(c.ctx));
    const size_t copied = llama_state_get_data(c.ctx, state.data.data(), state.data.size());
    if (copied == 0 || copied > state.data.size()) return false;
    state.data.resize(copied);
    state.next = c.next[0];
    state.used = c.used;
    const double seconds = std::chrono::duration<double>(clock_type::now() - start).count();
    std::fprintf(stderr, "STATE_SAVE name=%s used=%d bytes=%zu seconds=%.3f\n",
                 c.name, state.used, copied, seconds);
    return true;
}

static bool restore(chat & c, const snapshot & state) {
    select_chat(c);
    const auto start = clock_type::now();
    const size_t copied = llama_state_set_data(c.ctx, state.data.data(), state.data.size());
    if (copied != state.data.size()) {
        std::fprintf(stderr, "STATE_RESTORE_FAILED name=%s read=%zu expected=%zu\n",
                     c.name, copied, state.data.size());
        return false;
    }
    c.next.assign(1, state.next);
    c.used = state.used;
    const double seconds = std::chrono::duration<double>(clock_type::now() - start).count();
    std::fprintf(stderr, "STATE_RESTORE name=%s used=%d bytes=%zu seconds=%.3f\n",
                 c.name, c.used, copied, seconds);
    return true;
}

static bool parallel_bench(const llama_vocab * vocab, const std::vector<chat *> & chats,
                           int tokens, const char * phase) {
    std::atomic<int> ready{0};
    std::atomic<bool> go{false};
    std::atomic<bool> ok{true};
    std::vector<std::thread> threads;
    for (chat * item : chats) {
        threads.emplace_back([&, item]() {
            select_chat(*item);
            ready.fetch_add(1);
            while (!go.load()) std::this_thread::yield();
            if (!bench(*item, vocab, tokens, phase)) ok.store(false);
        });
    }
    while (ready.load() != (int)chats.size()) std::this_thread::yield();
    const auto start = clock_type::now();
    go.store(true);
    for (auto & thread : threads) thread.join();
    const double seconds = std::chrono::duration<double>(clock_type::now() - start).count();
    std::fprintf(stderr, "PARALLEL phase=%s chats=%zu tokens_each=%d seconds=%.6f aggregate_tps=%.6f ok=%d\n",
                 phase, chats.size(), tokens, seconds, chats.size() * tokens / seconds, ok.load());
    return ok.load();
}

static bool measured_generation(chat & c, const llama_vocab * vocab,
                                int tokens, const char * phase) {
    std::vector<double> latency_ms;
    latency_ms.reserve(tokens);
    const auto started = clock_type::now();
    for (int i = 0; i < tokens; ++i) {
        const auto step = clock_type::now();
        if (!decode(c, vocab)) return false;
        latency_ms.push_back(1000.0 * std::chrono::duration<double>(clock_type::now()-step).count());
    }
    const double elapsed = std::chrono::duration<double>(clock_type::now()-started).count();
    const double first_ms = latency_ms.front();
    std::sort(latency_ms.begin(), latency_ms.end());
    const double p50 = latency_ms[latency_ms.size()/2];
    const double p95 = latency_ms[std::min(latency_ms.size()-1, (latency_ms.size()*95)/100)];
    std::fprintf(stderr,
                 "GEN_METRIC phase=%s name=%s used=%d tokens=%d seconds=%.6f tps=%.6f first_ms=%.3f p50_ms=%.3f p95_ms=%.3f\n",
                 phase, c.name, c.used, tokens, elapsed, tokens/elapsed, first_ms, p50, p95);
    return true;
}

static bool measured_parallel(const llama_vocab * vocab, const std::vector<chat *> & chats,
                              int tokens, const char * phase) {
    std::atomic<int> ready{0};
    std::atomic<bool> go{false};
    std::atomic<bool> ok{true};
    std::vector<std::thread> threads;
    for (chat * item : chats) {
        threads.emplace_back([&, item]() {
            ready.fetch_add(1);
            while (!go.load()) std::this_thread::yield();
            if (!measured_generation(*item, vocab, tokens, phase)) ok.store(false);
        });
    }
    while (ready.load() != (int)chats.size()) std::this_thread::yield();
    const auto started = clock_type::now();
    go.store(true);
    for (auto & thread : threads) thread.join();
    const double elapsed = std::chrono::duration<double>(clock_type::now()-started).count();
    std::fprintf(stderr, "GEN_AGGREGATE phase=%s chats=%zu tokens_each=%d seconds=%.6f aggregate_tps=%.6f ok=%d\n",
                 phase, chats.size(), tokens, elapsed, chats.size()*tokens/elapsed, ok.load());
    return ok.load();
}

static void destroy(chat & c) {
    if (c.sampler) llama_sampler_free(c.sampler);
    if (c.ctx) llama_free(c.ctx);
}

static bool alternating_turn(chat & c, const llama_vocab * vocab,
                             const std::vector<llama_token> & filler,
                             const char * code, const char * step,
                             int target, int max_tokens, bool continuing) {
    if (continuing) {
        if (c.next.empty() || !decode_raw(c, c.next)) return false;
        const auto next_user = tokenize_text(vocab,
            "\n<|im_start|>user\nHere are more unrelated notes.\n", false);
        if (next_user.empty() || !decode_raw(c, next_user)) return false;
    }
    if (target <= c.used) return false;
    const auto start = clock_type::now();
    const int added = target - c.used;
    if (!decode_raw(c, filler, added)) return false;
    const double fill_seconds = std::chrono::duration<double>(clock_type::now() - start).count();
    std::fprintf(stderr, "TURN_FILL step=%s name=%s used=%d added=%d seconds=%.6f tps=%.6f\n",
                 step, c.name, c.used, added, fill_seconds, added / fill_seconds);
    const auto recall_start = clock_type::now();
    const bool correct = recall_answer(c, vocab, code, target, max_tokens);
    const double recall_seconds = std::chrono::duration<double>(clock_type::now() - recall_start).count();
    std::fprintf(stderr, "TURN_DONE step=%s name=%s used=%d recall_seconds=%.6f correct=%d\n",
                 step, c.name, c.used, recall_seconds, correct);
    return correct;
}

int main(int argc, char ** argv) {
    if (argc != 7) {
        std::fprintf(stderr, "usage: llama-simple matrix|depth MODEL.gguf LOCAL_CAP PAIR_CAP SINGLE_CAP TOKENS\n");
        return 2;
    }
    ggml_backend_load_all();
    auto mp = llama_model_default_params();
    mp.n_gpu_layers = 99;
    mp.split_mode = LLAMA_SPLIT_MODE_NONE;
    mp.main_gpu = 0;
    std::vector<ggml_backend_dev_t> model_devices;
    std::vector<float> model_split(llama_max_devices(), 0.0f);
    std::vector<ggml_backend_dev_t> all_gpus;
    for (size_t i = 0; i < ggml_backend_dev_count(); ++i) {
        auto dev = ggml_backend_dev_get(i);
        if (ggml_backend_dev_type(dev) == GGML_BACKEND_DEVICE_TYPE_GPU) all_gpus.push_back(dev);
    }
    const char * device_spec = std::getenv("KV_MODEL_DEVICES");
    const char * split_spec = std::getenv("KV_MODEL_SPLIT");
    if (device_spec && *device_spec) {
        std::stringstream device_stream(device_spec);
        std::string item;
        std::vector<int> indexes;
        while (std::getline(device_stream, item, ',')) indexes.push_back(std::stoi(item));
        for (int index : indexes) {
            if (index < 0 || (size_t)index >= all_gpus.size()) return 70;
            model_devices.push_back(all_gpus[index]);
        }
        model_devices.push_back(nullptr);
        mp.devices = model_devices.data();
        mp.split_mode = LLAMA_SPLIT_MODE_LAYER;
        if (split_spec && *split_spec) {
            std::stringstream split_stream(split_spec);
            size_t i = 0;
            while (std::getline(split_stream, item, ',')) {
                if (i >= model_split.size()) return 71;
                model_split[i++] = std::stof(item);
            }
            if (i != indexes.size()) return 72;
            mp.tensor_split = model_split.data();
        }
        std::fprintf(stderr, "MODEL_PLACEMENT devices=%s split=%s\n", device_spec,
                     split_spec ? split_spec : "auto");
    }
    std::deque<std::string> override_patterns;
    std::vector<llama_model_tensor_buft_override> overrides;
    const char * override_path = std::getenv("KV_TENSOR_OVERRIDES_FILE");
    if (override_path && *override_path) {
        std::ifstream input(override_path);
        if (!input) {
            std::fprintf(stderr, "OVERRIDE_FILE_OPEN_FAILED path=%s\n", override_path);
            return 90;
        }
        std::string line;
        while (std::getline(input, line)) {
            if (line.empty() || line[0] == '#') continue;
            const size_t tab = line.find('\t');
            if (tab == std::string::npos || tab + 1 == line.size()) return 91;
            const int index = std::stoi(line.substr(0, tab));
            if (index < 0 || (size_t) index >= all_gpus.size()) return 92;
            override_patterns.push_back(line.substr(tab + 1));
            overrides.push_back({override_patterns.back().c_str(),
                                 ggml_backend_dev_buffer_type(all_gpus[index])});
            std::fprintf(stderr, "TENSOR_OVERRIDE gpu=%d pattern=%s\n",
                         index, override_patterns.back().c_str());
        }
        if (overrides.empty()) return 93;
        overrides.push_back({nullptr, nullptr});
        mp.tensor_buft_overrides = overrides.data();
    }
    llama_model * model = llama_model_load_from_file(argv[2], mp);
    if (!model) return 3;
    std::fprintf(stderr, "MODEL_READY one weight load\n");
    const llama_vocab * vocab = llama_model_get_vocab(model);
    chat local{"local", "The capital of France is", nullptr, "0"};
    chat a{"pair12", "The capital of Japan is", "1,2", nullptr};
    chat b{"pair34", "The capital of Germany is", "3,4", nullptr};
    chat c{"single5", "The capital of Spain is", nullptr, "5"};
    const int local_cap = std::atoi(argv[3]);
    const int pair_cap = std::atoi(argv[4]);
    const int single_cap = std::atoi(argv[5]);
    const int tokens = std::atoi(argv[6]);
    if (std::string(argv[1]) == "large_chat_fresh" ||
        std::string(argv[1]) == "one_235k_fresh") {
        const int chat_count = std::string(argv[1]) == "one_235k_fresh" ? 1 : 5;
        if (local_cap < 262144 || pair_cap < 200000 || pair_cap + 256 >= local_cap || tokens < 8)
            return 150;
        const char * names[5] = {"worker1", "worker2", "worker3", "worker4", "worker5"};
        const char * codes[5] = {"4827", "6193", "7358", "2046", "8915"};
        const char * cards[5] = {"1", "2", "3", "4", "5"};
        std::vector<std::string> prompts;
        prompts.reserve(5);
        for (int i = 0; i < 5; ++i)
            prompts.push_back(std::string("<|im_start|>user\nRemember my private four-digit code: ") +
                              codes[i] + ". These are unrelated field notes.\n");
        std::vector<chat> chats;
        chats.reserve(5);
        for (int i = 0; i < chat_count; ++i) {
            chats.push_back({names[i], prompts[i].c_str(), nullptr, cards[i]});
            chat & c = chats.back();
            std::string notes;
            for (int j = 0; j < 300; ++j)
                notes += std::string(names[i]) + " note " + std::to_string(j) +
                         " records item " + std::to_string((j*7919+i*101+17)%100003) +
                         " beside a bridge.\n";
            const auto filler = tokenize_text(vocab, notes, false);
            if (filler.empty() || !add_chat(c, model, vocab, local_cap, true) ||
                !decode_raw(c, c.next)) return 151;
            const auto began = clock_type::now();
            while (c.used < pair_cap) {
                const int next_target = std::min(pair_cap, ((c.used/8192)+1)*8192);
                if (!decode_raw(c, filler, next_target-c.used)) return 152;
                const double elapsed = std::chrono::duration<double>(clock_type::now()-began).count();
                std::fprintf(stderr, "FILL_PROGRESS name=%s used=%d target=%d seconds=%.2f\n",
                             c.name, c.used, pair_cap, elapsed);
                std::fflush(stderr);
            }
            // Decode the pending opening token outside the timed window.
            if (!decode(c, vocab)) return 153;
            std::fprintf(stderr, "CHAT_READY name=%s gpu=%s used=%d cap=%d\n",
                         c.name, c.single, c.used, local_cap);
            if (i == 0 || i == 2 || i == 4) {
                std::vector<chat *> active;
                for (chat & item : chats) active.push_back(&item);
                const std::string phase = "deep_" + std::to_string(active.size()) + "_chats";
                if (!measured_parallel(vocab, active, tokens, phase.c_str())) return 154;
            }
        }
        std::atomic<int> correct{0};
        std::vector<std::thread> checks;
        for (int i = 0; i < chat_count; ++i)
            checks.emplace_back([&, i]() {
                if (recall_answer(chats[i], vocab, codes[i], chats[i].used, 64))
                    correct.fetch_add(1);
            });
        for (auto & thread : checks) thread.join();
        std::fprintf(stderr, "DEEP_INDEPENDENCE correct=%d chats=%d\n", correct.load(), chat_count);
        for (auto & c : chats) destroy(c);
        llama_model_free(model);
        return correct.load() == chat_count ? 0 : 155;
    }
    if (std::string(argv[1]) == "large_chat_latency") {
        const char * state_dir = std::getenv("KV_STATE_DIR");
        if (!state_dir || pair_cap < 262144 || tokens < 8) return 130;
        const char * names[5] = {"worker1", "worker2", "worker3", "worker4", "worker5"};
        const char * codes[5] = {"4827", "6193", "7358", "2046", "8915"};
        const char * cards[5] = {"1", "2", "3", "4", "5"};
        std::vector<chat> chats;
        chats.reserve(5);
        for (int i = 0; i < 5; ++i) {
            chats.push_back({names[i], "", nullptr, cards[i]});
            chat & c = chats.back();
            if (!add_chat(c, model, vocab, pair_cap, true)) return 131;
            snapshot state;
            const std::string path = std::string(state_dir) + "/" + names[i] + "_depth90.bin";
            if (!read_snapshot_file(path, state) || state.used < 200000 ||
                !restore(c, state)) return 132;
            state.data.clear();
            state.data.shrink_to_fit();
            // The saved next token is a prompt token. Decode it once outside
            // the timed window, then time generated single-token steps only.
            if (!decode(c, vocab)) return 133;
            std::fprintf(stderr, "CHAT_READY name=%s gpu=%s used=%d cap=%d\n",
                         c.name, c.single, c.used, pair_cap);
            if (i == 0 || i == 2 || i == 4) {
                std::vector<chat *> active;
                for (chat & item : chats) active.push_back(&item);
                const std::string phase = "deep_" + std::to_string(active.size()) + "_chats";
                if (!measured_parallel(vocab, active, tokens, phase.c_str())) return 134;
            }
        }
        std::atomic<int> correct{0};
        std::vector<std::thread> checks;
        for (int i = 0; i < 5; ++i) {
            checks.emplace_back([&, i]() {
                if (recall_answer(chats[i], vocab, codes[i], chats[i].used, 64))
                    correct.fetch_add(1);
            });
        }
        for (auto & thread : checks) thread.join();
        std::fprintf(stderr, "DEEP_INDEPENDENCE correct=%d chats=5\n", correct.load());
        for (auto & c : chats) destroy(c);
        llama_model_free(model);
        return correct.load() == 5 ? 0 : 135;
    }
    if (std::string(argv[1]) == "two_100k_one_1060") {
        if (local_cap < 102400 || single_cap < 100000 || single_cap + 256 >= local_cap)
            return 140;
        const std::string pa = "<|im_start|>user\nRemember my private four-digit code: 4827. These are my field notes.\n";
        const std::string pb = "<|im_start|>user\nRemember my private four-digit code: 6193. These are my workshop notes.\n";
        chat ca{"A", pa.c_str(), nullptr, "1"};
        chat cb{"B", pb.c_str(), nullptr, "1"};
        auto make_notes = [&](const char * label) {
            std::string notes;
            for (int i = 0; i < 300; ++i)
                notes += std::string(label) + " note " + std::to_string(i) +
                         " records marker " + std::to_string((i*7919+17)%100003) +
                         " beside a bridge.\n";
            return tokenize_text(vocab, notes, false);
        };
        const auto fa = make_notes("A");
        const auto fb = make_notes("B");
        if (fa.empty() || fb.empty()) return 141;
        if (!add_chat(ca, model, vocab, local_cap, true) ||
            !decode_raw(ca, ca.next) ||
            !decode_raw(ca, fa, single_cap-ca.used) ||
            !decode(ca, vocab)) return 142;
        std::fprintf(stderr, "CHAT_READY name=A gpu=1 used=%d cap=%d\n", ca.used, local_cap);
        if (!measured_parallel(vocab, {&ca}, tokens, "one_100k_chat")) return 143;
        if (!add_chat(cb, model, vocab, local_cap, true) ||
            !decode_raw(cb, cb.next) ||
            !decode_raw(cb, fb, single_cap-cb.used) ||
            !decode(cb, vocab)) return 144;
        std::fprintf(stderr, "CHAT_READY name=B gpu=1 used=%d cap=%d\n", cb.used, local_cap);
        if (!measured_parallel(vocab, {&ca, &cb}, tokens, "two_100k_chats_same_1060")) return 145;
        std::atomic<int> correct{0};
        std::thread ta([&]() { if (recall_answer(ca, vocab, "4827", ca.used, 64)) correct.fetch_add(1); });
        std::thread tb([&]() { if (recall_answer(cb, vocab, "6193", cb.used, 64)) correct.fetch_add(1); });
        ta.join(); tb.join();
        std::fprintf(stderr, "TWO_CHAT_INDEPENDENCE correct=%d used_A=%d used_B=%d\n",
                     correct.load(), ca.used, cb.used);
        destroy(cb); destroy(ca); llama_model_free(model);
        return correct.load() == 2 ? 0 : 146;
    }
    if (std::string(argv[1]) == "two_100k_handoff_one_1060") {
        if (local_cap < 102400 || single_cap < 100000 || single_cap + 256 >= local_cap)
            return 160;
        const std::string pa = "<|im_start|>user\nRemember my private four-digit code: 4827. These are my field notes.\n";
        const std::string pb = "<|im_start|>user\nRemember my private four-digit code: 6193. These are my workshop notes.\n";
        chat ca{"A", "", nullptr, "1"};
        chat cb{"B", "", nullptr, "1"};
        auto prepare_and_transfer = [&](chat & target, const std::string & prompt,
                                        const char * label) {
            const std::string notes_label(label);
            std::string notes;
            for (int i = 0; i < 300; ++i)
                notes += notes_label + " note " + std::to_string(i) +
                         " records marker " + std::to_string((i*7919+17)%100003) +
                         " beside a bridge.\n";
            const auto filler = tokenize_text(vocab, notes, false);
            if (filler.empty()) return false;
            chat prep{label, prompt.c_str(), nullptr, "0"};
            const auto prep_start = clock_type::now();
            if (!add_chat(prep, model, vocab, local_cap, true) ||
                !decode_raw(prep, prep.next) ||
                !decode_raw(prep, filler, single_cap-prep.used) ||
                !decode(prep, vocab)) return false;
            const double prep_seconds = std::chrono::duration<double>(clock_type::now()-prep_start).count();
            std::fprintf(stderr, "PREP_METRIC name=%s gpu=0 used=%d seconds=%.6f\n",
                         label, prep.used, prep_seconds);
            snapshot state;
            if (!save(prep, state)) return false;
            destroy(prep);
            if (!add_chat(target, model, vocab, local_cap, true) ||
                !restore(target, state)) return false;
            state.data.clear();
            state.data.shrink_to_fit();
            if (!decode(target, vocab)) return false;
            std::fprintf(stderr, "CHAT_READY name=%s gpu=1 used=%d cap=%d\n",
                         target.name, target.used, local_cap);
            return true;
        };
        if (!prepare_and_transfer(ca, pa, "A")) return 161;
        if (!measured_parallel(vocab, {&ca}, tokens, "one_100k_chat_handoff")) return 162;
        if (!prepare_and_transfer(cb, pb, "B")) return 163;
        if (!measured_parallel(vocab, {&ca, &cb}, tokens,
                               "two_100k_chats_handoff_same_1060")) return 164;
        std::atomic<int> correct{0};
        std::thread ta([&]() { if (recall_answer(ca, vocab, "4827", ca.used, 64)) correct.fetch_add(1); });
        std::thread tb([&]() { if (recall_answer(cb, vocab, "6193", cb.used, 64)) correct.fetch_add(1); });
        ta.join(); tb.join();
        std::fprintf(stderr, "TWO_CHAT_HANDOFF_INDEPENDENCE correct=%d used_A=%d used_B=%d\n",
                     correct.load(), ca.used, cb.used);
        destroy(cb); destroy(ca); llama_model_free(model);
        return correct.load() == 2 ? 0 : 165;
    }
    if (std::string(argv[1]) == "matched_100k_kv_placement") {
        if (local_cap < 102400 || single_cap < 100000 ||
            single_cap + 256 >= local_cap || tokens < 16) return 170;
        const std::string prompt =
            "<|im_start|>user\nRemember my private four-digit code: 4827. These are my field notes.\n";
        std::string notes;
        for (int i = 0; i < 300; ++i)
            notes += "A note " + std::to_string(i) +
                     " records marker " + std::to_string((i*7919+17)%100003) +
                     " beside a bridge.\n";
        const auto filler = tokenize_text(vocab, notes, false);
        if (filler.empty()) return 171;
        chat prep{"prep", prompt.c_str(), nullptr, "0"};
        const auto prep_start = clock_type::now();
        if (!add_chat(prep, model, vocab, local_cap, true) ||
            !decode_raw(prep, prep.next) ||
            !decode_raw(prep, filler, single_cap-prep.used) ||
            !decode(prep, vocab)) return 172;
        const double prep_seconds = std::chrono::duration<double>(clock_type::now()-prep_start).count();
        std::fprintf(stderr, "PREP_METRIC name=matched gpu=0 used=%d seconds=%.6f\n",
                     prep.used, prep_seconds);
        snapshot state;
        if (!save(prep, state)) return 173;
        destroy(prep);
        auto run_placement = [&](const char * name, const char * pair,
                                 const char * single, const char * phase) {
            chat target{name, "", pair, single};
            if (!add_chat(target, model, vocab, local_cap, true) ||
                !restore(target, state) || !decode(target, vocab, true)) return false;
            std::fprintf(stderr, "CHAT_READY name=%s pair=%s single=%s used=%d cap=%d\n",
                         name, pair ? pair : "-", single ? single : "-",
                         target.used, local_cap);
            const bool timed = measured_generation(target, vocab, tokens, phase);
            const bool correct = timed && recall_answer(target, vocab, "4827", target.used, 64);
            std::fprintf(stderr, "PLACEMENT_RESULT name=%s phase=%s correct=%d\n",
                         name, phase, correct);
            destroy(target);
            return correct;
        };
        if (!run_placement("local", nullptr, "0", "matched_100k_local")) return 174;
        if (!run_placement("single", nullptr, "1", "matched_100k_single")) return 175;
        if (!run_placement("pair", "1,2", nullptr, "matched_100k_pair")) return 176;
        if (!run_placement("local_repeat", nullptr, "0", "matched_100k_local_repeat")) return 177;
        std::fprintf(stderr, "MATCHED_PLACEMENT_DONE used=%d tokens=%d placements=4\n",
                     state.used, tokens);
        llama_model_free(model);
        return 0;
    }
    if (std::string(argv[1]) == "varied_concurrent_single" ||
        std::string(argv[1]) == "varied_concurrent_ram") {
        const bool ram = std::string(argv[1]) == "varied_concurrent_ram";
        const std::string pa = "<|im_start|>user\nRemember my private four-digit code: 4827. The following are unrelated field notes.\n";
        const std::string pb = "<|im_start|>user\nRemember my private four-digit code: 6193. The following are unrelated field notes.\n";
        const std::string pc = "<|im_start|>user\nRemember my private four-digit code: 7358. The following are unrelated field notes.\n";
        chat va{"A", pa.c_str(), nullptr, ram ? "-1" : "1"};
        chat vb{"B", pb.c_str(), nullptr, ram ? "-1" : "3"};
        chat vc{"C", pc.c_str(), nullptr, ram ? "-1" : "5"};
        std::string notes;
        for (int i = 0; i < 300; ++i) {
            notes += "Field note " + std::to_string(i) + ": a " +
                (i % 3 == 0 ? "copper lantern" : i % 3 == 1 ? "blue bicycle" : "stone bridge") +
                " was listed beside marker " + std::to_string((i * 7919 + 17) % 100003) + ".\n";
        }
        const auto filler = tokenize_text(vocab, notes, false);
        if (filler.empty()) return 120;
        if (!add_chat(va, model, vocab, local_cap, true) ||
            !decode_raw(va, va.next) || !decode_raw(va, filler, 2048)) return 121;
        if (!add_chat(vb, model, vocab, pair_cap, true) ||
            !decode_raw(vb, vb.next) || !decode_raw(vb, filler, 6144)) return 122;
        if (!decode_raw(va, filler, 6144)) return 123;
        if (!add_chat(vc, model, vocab, single_cap, true) ||
            !decode_raw(vc, vc.next) || !decode_raw(vc, filler, 10240)) return 124;
        if (!decode_raw(va, filler, 8192)) return 125;
        std::fprintf(stderr, "VARIED_DEPTH mode=%s A=%d B=%d C=%d filler_tokens=%zu\n",
                     argv[1], va.used, vb.used, vc.used, filler.size());
        if (!parallel_bench(vocab, {&va, &vb, &vc}, tokens, "varied_concurrent")) return 126;
        std::atomic<int> ready{0};
        std::atomic<bool> go{false};
        bool passes[3] = {false, false, false};
        chat * chats[3] = {&va, &vb, &vc};
        const char * codes[3] = {"4827", "6193", "7358"};
        std::vector<std::thread> threads;
        const auto started = clock_type::now();
        for (int i = 0; i < 3; ++i) {
            threads.emplace_back([&, i]() {
                ready.fetch_add(1);
                while (!go.load()) std::this_thread::yield();
                passes[i] = recall_answer(*chats[i], vocab, codes[i], chats[i]->used, 64);
            });
        }
        while (ready.load() != 3) std::this_thread::yield();
        go.store(true);
        for (auto & thread : threads) thread.join();
        const double elapsed = std::chrono::duration<double>(clock_type::now() - started).count();
        std::fprintf(stderr, "VARIED_CONCURRENT_RECALL mode=%s seconds=%.3f A=%d B=%d C=%d\n",
                     argv[1], elapsed, passes[0], passes[1], passes[2]);
        destroy(vc); destroy(vb); destroy(va); llama_model_free(model);
        return passes[0] && passes[1] && passes[2] ? 0 : 127;
    }
    if (std::string(argv[1]) == "two_ram_chats") {
        chat a{"ram_a", "The capital of Japan is", nullptr, "-1"};
        chat b{"ram_b", "The capital of Germany is", nullptr, "-1"};
        if (!add_chat(a, model, vocab, local_cap) ||
            !decode(a, vocab, true)) return 105;
        if (!add_chat(b, model, vocab, pair_cap) ||
            !decode(b, vocab, true)) return 106;
        if (!parallel_bench(vocab, {&a, &b}, tokens, "two_ram_chats")) return 107;
        destroy(b);
        destroy(a);
        llama_model_free(model);
        return 0;
    }
    if (std::string(argv[1]) == "mixed_ram_gpu_chats") {
        chat gpu1{"gpu1", "The capital of Japan is", nullptr, "1"};
        chat ram{"ram", "The capital of Germany is", nullptr, "-1"};
        chat gpu2{"gpu2", "The capital of Spain is", nullptr, "2"};
        if (!add_chat(gpu1, model, vocab, pair_cap) ||
            !decode(gpu1, vocab, true)) return 100;
        if (!add_chat(ram, model, vocab, local_cap) ||
            !decode(ram, vocab, true)) return 101;
        if (!parallel_bench(vocab, {&gpu1, &ram}, tokens, "gpu1_plus_ram")) return 102;
        if (!add_chat(gpu2, model, vocab, single_cap) ||
            !decode(gpu2, vocab, true)) return 103;
        if (!parallel_bench(vocab, {&gpu1, &ram, &gpu2}, tokens,
                            "gpu1_plus_ram_plus_gpu2")) return 104;
        destroy(gpu2);
        destroy(ram);
        destroy(gpu1);
        llama_model_free(model);
        return 0;
    }
    if (std::string(argv[1]) == "alternate_single" ||
        std::string(argv[1]) == "alternate_pair" ||
        std::string(argv[1]) == "alternate_ram") {
        const std::string mode(argv[1]);
        const bool paired = mode == "alternate_pair";
        const bool ram = mode == "alternate_ram";
        const std::string prefix_a = "<|im_start|>user\nRemember this private four-digit code: 4827. I will ask for it after unrelated notes.\n";
        const std::string prefix_b = "<|im_start|>user\nRemember this private four-digit code: 6193. I will ask for it after unrelated notes.\n";
        const std::string prefix_c = "<|im_start|>user\nRemember this private four-digit code: 7358. I will ask for it after unrelated notes.\n";
        chat a{"A", prefix_a.c_str(), paired ? "1,2" : nullptr, ram ? "-1" : "1"};
        chat b{"B", prefix_b.c_str(), paired ? "3,4" : nullptr, ram ? "-1" : paired ? nullptr : "3"};
        chat c{"C", prefix_c.c_str(), nullptr, ram ? "-1" : "5"};
        const auto filler = tokenize_text(vocab,
            " A quiet field note described a blue bicycle by a river. "
            "The weather was mild and the bridge remained open.\n", false);
        if (filler.empty()) return 110;
        if (!add_chat(a, model, vocab, local_cap, true) ||
            !decode_raw(a, a.next) ||
            !alternating_turn(a, vocab, filler, "4827", "A1", 1024, tokens, false)) return 111;
        if (!add_chat(b, model, vocab, pair_cap, true) ||
            !decode_raw(b, b.next) ||
            !alternating_turn(b, vocab, filler, "6193", "B1", 3072, tokens, false)) return 112;
        if (!alternating_turn(a, vocab, filler, "4827", "A2", 4096, tokens, true)) return 113;
        if (!add_chat(c, model, vocab, single_cap, true) ||
            !decode_raw(c, c.next) ||
            !alternating_turn(c, vocab, filler, "7358", "C1", 6144, tokens, false)) return 114;
        if (!alternating_turn(a, vocab, filler, "4827", "A3", 8192, tokens, true)) return 115;
        if (!recall_answer(b, vocab, "6193", b.used, tokens) ||
            !recall_answer(c, vocab, "7358", c.used, tokens)) return 116;
        std::fprintf(stderr, "ALTERNATING_PASS mode=%s order=A-B-A-C-A final_used=A:%d,B:%d,C:%d\n",
                     mode.c_str(), a.used, b.used, c.used);
        destroy(c);
        destroy(b);
        destroy(a);
        llama_model_free(model);
        return 0;
    }
    if (std::string(argv[1]) == "ram_kv" || std::string(argv[1]) == "ram_depth") {
        chat ram{"ram_kv", "The capital of Japan is", nullptr, "-1"};
        if (!add_chat(ram, model, vocab, local_cap) || !decode(ram, vocab, true)) return 73;
        if (std::string(argv[1]) == "ram_depth") {
            if (!fill(ram, local_cap / 10) ||
                !bench(ram, vocab, tokens, "ram_depth10") ||
                !fill(ram, local_cap * 9 / 10) ||
                !bench(ram, vocab, tokens, "ram_depth90")) return 74;
        } else if (!bench(ram, vocab, tokens, "ram_short")) return 74;
        destroy(ram);
        llama_model_free(model);
        return 0;
    }
    if (std::string(argv[1]) == "two_workers_and_pair") {
        chat w4{"worker4", "The capital of Japan is", nullptr, "4"};
        chat w5{"worker5", "The capital of Germany is", nullptr, "5"};
        chat large{"large_pair45", "The capital of Canada is", "4,5", nullptr};
        if (!add_chat(w4, model, vocab, pair_cap) || !decode(w4, vocab, true) ||
            !add_chat(w5, model, vocab, pair_cap) || !decode(w5, vocab, true)) return 75;
        if (!parallel_bench(vocab, {&w4, &w5}, tokens, "two_workers")) return 76;
        if (!add_chat(large, model, vocab, single_cap) || !decode(large, vocab, true)) return 77;
        if (!parallel_bench(vocab, {&w4, &w5, &large}, tokens, "two_workers_plus_pair")) return 78;
        destroy(large);
        destroy(w5);
        destroy(w4);
        llama_model_free(model);
        return 0;
    }
    if (std::string(argv[1]) == "two_workers_depth") {
        chat w4{"worker4", "The capital of Japan is", nullptr, "4"};
        chat w5{"worker5", "The capital of Germany is", nullptr, "5"};
        chat large{"large_pair45", "The capital of Canada is", "4,5", nullptr};
        if (!add_chat(w4, model, vocab, pair_cap) || !decode(w4, vocab, true) ||
            !add_chat(w5, model, vocab, pair_cap) || !decode(w5, vocab, true) ||
            !add_chat(large, model, vocab, single_cap) || !decode(large, vocab, true)) return 94;
        std::vector<chat *> workers{&w4, &w5, &large};
        for (chat * worker : workers) {
            const int cap = worker == &large ? single_cap : pair_cap;
            if (!fill(*worker, cap / 10)) return 95;
        }
        if (!parallel_bench(vocab, workers, tokens, "depth10")) return 96;
        for (chat * worker : workers) {
            const int cap = worker == &large ? single_cap : pair_cap;
            if (!fill(*worker, cap * 9 / 10)) return 97;
        }
        if (!parallel_bench(vocab, workers, tokens, "depth90")) return 98;
        destroy(large);
        destroy(w5);
        destroy(w4);
        llama_model_free(model);
        return 0;
    }
    if (std::string(argv[1]) == "recall_handoff") {
        const char * state_dir = std::getenv("KV_STATE_DIR");
        if (!state_dir) return 80;
        const char * codes[5] = {"4827", "6193", "7358", "2046", "8915"};
        const char * names[5] = {"worker1", "worker2", "worker3", "worker4", "worker5"};
        const char * cards[5] = {"1", "2", "3", "4", "5"};
        const auto filler = tokenize_text(vocab,
            " A quiet field note described a blue bicycle by a river. "
            "The weather was mild and the bridge remained open.\n", false);
        if (filler.empty()) return 81;
        const int depths[3] = {10, 50, 90};
        for (int i = 0; i < 5; ++i) {
            const std::string prefix = std::string("<|im_start|>user\n") +
                "Remember this private four-digit code: " + codes[i] +
                ". I will ask for it after unrelated notes.\n";
            snapshot checkpoint;
            int resume_depth = -1;
            for (int j = 2; j >= 0; --j) {
                const std::string path = std::string(state_dir) + "/" + names[i] +
                    "_depth" + std::to_string(depths[j]) + ".bin";
                if (read_snapshot_file(path, checkpoint)) {
                    resume_depth = j;
                    break;
                }
            }
            if (resume_depth == 2) {
                std::fprintf(stderr, "RECALL_PREP_REUSE name=%s depth=90\n", names[i]);
                continue;
            }
            chat temp{names[i], prefix.c_str(), nullptr, "0"};
            if (!add_chat(temp, model, vocab, pair_cap, true)) return 82;
            if (resume_depth >= 0) {
                if (!restore(temp, checkpoint)) return 82;
                std::fprintf(stderr, "RECALL_PREP_RESUME name=%s depth=%d\n",
                             names[i], depths[resume_depth]);
            } else if (!decode_raw(temp, temp.next)) return 82;
            checkpoint.data.clear();
            checkpoint.data.shrink_to_fit();
            for (int j = resume_depth + 1; j < 3; ++j) {
                const int depth = depths[j];
                const int target = pair_cap * depth / 100;
                if (target <= temp.used || !decode_raw(temp, filler, target - temp.used)) return 83;
                snapshot state;
                if (!save(temp, state)) return 84;
                const std::string path = std::string(state_dir) + "/" + names[i] +
                    "_depth" + std::to_string(depth) + ".bin";
                if (!write_snapshot_file(path, state)) return 85;
                std::fprintf(stderr, "RECALL_PREP name=%s depth=%d used=%d hash=%016llx\n",
                             names[i], depth, temp.used,
                             (unsigned long long)fingerprint(state));
            }
            destroy(temp);
        }
        chat w1{"worker1", "", nullptr, "1"};
        chat w2{"worker2", "", nullptr, "2"};
        chat w3{"worker3", "", nullptr, "3"};
        chat w4{"worker4", "", nullptr, "4"};
        chat w5{"worker5", "", nullptr, "5"};
        std::vector<chat *> workers{&w1, &w2, &w3, &w4, &w5};
        for (chat * worker : workers) {
            if (!add_chat(*worker, model, vocab, pair_cap)) return 86;
        }
        for (int depth : depths) {
            for (int i = 0; i < 5; ++i) {
                const std::string path = std::string(state_dir) + "/" + names[i] +
                    "_depth" + std::to_string(depth) + ".bin";
                snapshot state;
                if (!read_snapshot_file(path, state) || !restore(*workers[i], state)) return 87;
            }
            std::atomic<bool> ok{true};
            std::vector<std::thread> threads;
            for (int i = 0; i < 5; ++i) {
                threads.emplace_back([&, i, depth]() {
                    if (!recall_answer(*workers[i], vocab, codes[i], depth, tokens)) ok.store(false);
                });
            }
            for (auto & thread : threads) thread.join();
            std::fprintf(stderr, "RECALL_PARALLEL depth=%d chats=5 ok=%d\n", depth, ok.load());
            if (!ok.load()) return 88;
        }
        for (auto it = workers.rbegin(); it != workers.rend(); ++it) destroy(**it);
        llama_model_free(model);
        return 0;
    }
    if (std::string(argv[1]) == "five_distinct_disk") {
        const char * state_dir = std::getenv("KV_STATE_DIR");
        if (!state_dir) return 60;
        chat w1{"worker1", "The capital of Japan is", nullptr, "1"};
        chat w2{"worker2", "The capital of Germany is", nullptr, "2"};
        chat w3{"worker3", "The capital of Italy is", nullptr, "3"};
        chat w4{"worker4", "The capital of Spain is", nullptr, "4"};
        chat w5{"worker5", "The capital of Canada is", nullptr, "5"};
        const std::vector<chat *> workers{&w1, &w2, &w3, &w4, &w5};
        std::vector<uint64_t> hashes;
        for (chat * worker : workers) {
            const std::string path = std::string(state_dir) + "/" + worker->name + ".bin";
            snapshot state;
            if (!read_snapshot_file(path, state)) {
                chat temp{worker->name, worker->prompt, nullptr, "0"};
                if (!add_chat(temp, model, vocab, pair_cap, true) ||
                    !decode(temp, vocab, true) ||
                    !fill(temp, pair_cap * 9 / 10, 512) ||
                    !save(temp, state) ||
                    !write_snapshot_file(path, state)) return 61;
                destroy(temp);
            } else {
                std::fprintf(stderr, "STATE_REUSE name=%s\n", worker->name);
            }
            const uint64_t hash = fingerprint(state);
            std::fprintf(stderr, "SNAPSHOT_ID name=%s hash=%016llx\n",
                         worker->name, (unsigned long long)hash);
            if (std::find(hashes.begin(), hashes.end(), hash) != hashes.end()) return 62;
            hashes.push_back(hash);
        }
        for (chat * worker : workers) {
            const std::string path = std::string(state_dir) + "/" + worker->name + ".bin";
            snapshot state;
            if (!read_snapshot_file(path, state) ||
                !add_chat(*worker, model, vocab, pair_cap) ||
                !restore(*worker, state)) return 63;
        }
        for (int rep = 1; rep <= 3; ++rep) {
            const std::string phase = "five_distinct_depth90_rep" + std::to_string(rep);
            if (!parallel_bench(vocab, workers, tokens, phase.c_str())) return 64;
        }
        for (auto it = workers.rbegin(); it != workers.rend(); ++it) destroy(**it);
        llama_model_free(model);
        return 0;
    }
    if (std::string(argv[1]) == "five_distinct_prefill") {
        chat w1{"worker1", "The capital of Japan is", nullptr, "1"};
        chat w2{"worker2", "The capital of Germany is", nullptr, "2"};
        chat w3{"worker3", "The capital of Italy is", nullptr, "3"};
        chat w4{"worker4", "The capital of Spain is", nullptr, "4"};
        chat w5{"worker5", "The capital of Canada is", nullptr, "5"};
        const std::vector<chat *> workers{&w1, &w2, &w3, &w4, &w5};
        std::vector<snapshot> states(workers.size());
        std::vector<uint64_t> fingerprints;
        for (size_t i = 0; i < workers.size(); ++i) {
            chat temp{workers[i]->name, workers[i]->prompt, nullptr, "0"};
            if (!add_chat(temp, model, vocab, pair_cap, true) ||
                !decode(temp, vocab, true) ||
                !fill(temp, pair_cap / 10, 512) ||
                !save(temp, states[i])) return 50;
            uint64_t hash = 1469598103934665603ULL;
            for (uint8_t byte : states[i].data) {
                hash = (hash ^ byte) * 1099511628211ULL;
            }
            std::fprintf(stderr, "SNAPSHOT_ID name=%s hash=%016llx\n",
                         temp.name, (unsigned long long)hash);
            if (std::find(fingerprints.begin(), fingerprints.end(), hash) != fingerprints.end()) return 51;
            fingerprints.push_back(hash);
            destroy(temp);
        }
        for (size_t i = 0; i < workers.size(); ++i) {
            if (!add_chat(*workers[i], model, vocab, pair_cap) ||
                !restore(*workers[i], states[i])) return 52;
        }
        if (!parallel_bench(vocab, workers, tokens, "five_distinct_depth10")) return 53;
        for (auto it = workers.rbegin(); it != workers.rend(); ++it) destroy(**it);
        llama_model_free(model);
        return 0;
    }
    if (std::string(argv[1]) == "five_parallel" ||
        std::string(argv[1]) == "five_migrate_depth") {
        const bool deep = std::string(argv[1]) == "five_migrate_depth";
        snapshot ten, ninety;
        if (deep) {
            chat temp{"temp_five", "The capital of Japan is", nullptr, "0"};
            if (!add_chat(temp, model, vocab, pair_cap, true) || !decode(temp, vocab, true)) return 40;
            if (!fill(temp, pair_cap / 10, 512) || !save(temp, ten)) return 41;
            if (!fill(temp, pair_cap * 9 / 10, 512) || !save(temp, ninety)) return 42;
            destroy(temp);
        }
        chat w1{"worker1", "The capital of Japan is", nullptr, "1"};
        chat w2{"worker2", "The capital of Germany is", nullptr, "2"};
        chat w3{"worker3", "The capital of Italy is", nullptr, "3"};
        chat w4{"worker4", "The capital of Spain is", nullptr, "4"};
        chat w5{"worker5", "The capital of Canada is", nullptr, "5"};
        if (!deep && (!add_chat(local, model, vocab, local_cap) ||
                      !decode(local, vocab, true))) return 43;
        for (chat * item : {&w1, &w2, &w3, &w4, &w5}) {
            if (!add_chat(*item, model, vocab, pair_cap)) return 44;
            if (deep) {
                if (!restore(*item, ten)) return 45;
            } else if (!decode(*item, vocab, true)) return 46;
        }
        const std::vector<chat *> active = deep
            ? std::vector<chat *>{&w1, &w2, &w3, &w4, &w5}
            : std::vector<chat *>{&local, &w1, &w2, &w3, &w4, &w5};
        if (!parallel_bench(vocab, active, tokens,
                            deep ? "five_depth10" : "five_short")) return 47;
        if (deep) {
            for (chat * item : {&w1, &w2, &w3, &w4, &w5}) {
                if (!restore(*item, ninety)) return 48;
            }
            if (!parallel_bench(vocab, active, tokens, "five_depth90")) return 49;
        }
        for (chat * item : {&w5, &w4, &w3, &w2, &w1}) destroy(*item);
        if (!deep) destroy(local);
        llama_model_free(model);
        return 0;
    }
    if (!add_chat(local, model, vocab, local_cap) || !decode(local, vocab, true)) return 4;
    std::fprintf(stderr, "PHASE_LOCAL_READY\n");
    if (!add_chat(a, model, vocab, pair_cap) || !decode(a, vocab, true)) return 5;
    std::fprintf(stderr, "PHASE_PAIR12_READY\n");
    if (std::string(argv[1]) == "matrix") {
        if (!add_chat(b, model, vocab, pair_cap) || !decode(b, vocab, true)) return 6;
        std::fprintf(stderr, "PHASE_PAIR34_READY\n");
        if (!add_chat(c, model, vocab, single_cap) || !decode(c, vocab, true)) return 7;
        std::fprintf(stderr, "PHASE_SINGLE5_READY\n");
        for (chat * item : {&local, &a, &b, &c}) {
            if (!bench(*item, vocab, tokens, "short")) return 8;
        }
    } else if (std::string(argv[1]) == "depth") {
        const int ten = pair_cap / 10;
        const int ninety = pair_cap * 9 / 10;
        if (!fill(a, ten) || !bench(a, vocab, tokens, "depth10")) return 9;
        if (!fill(a, ninety) || !bench(a, vocab, tokens, "depth90")) return 10;
        if (!bench(local, vocab, tokens, "local_short_after_depth")) return 11;
    } else if (std::string(argv[1]) == "parallel") {
        if (!add_chat(b, model, vocab, pair_cap) || !decode(b, vocab, true)) return 13;
        if (!add_chat(c, model, vocab, single_cap) || !decode(c, vocab, true)) return 14;
        if (!parallel_bench(vocab, {&local, &a, &b, &c}, tokens, "short")) return 15;
    } else if (std::string(argv[1]) == "migrate_depth_all") {
        snapshot pair10, pair90, single10, single90;
        // Build the long histories quickly on GPU0, then move their state.
        destroy(a);
        destroy(local);
        chat temp_pair{"temp_pair", "The capital of Japan is", nullptr, "0"};
        if (!add_chat(temp_pair, model, vocab, pair_cap, true) || !decode(temp_pair, vocab, true)) return 22;
        if (!fill(temp_pair, pair_cap / 10, 512) || !save(temp_pair, pair10)) return 23;
        if (!fill(temp_pair, pair_cap * 9 / 10, 512) || !save(temp_pair, pair90)) return 24;
        destroy(temp_pair);
        chat temp_single{"temp_single", "The capital of Spain is", nullptr, "0"};
        if (!add_chat(temp_single, model, vocab, single_cap, true) || !decode(temp_single, vocab, true)) return 25;
        if (!fill(temp_single, single_cap / 10, 512) || !save(temp_single, single10)) return 26;
        if (!fill(temp_single, single_cap * 9 / 10, 512) || !save(temp_single, single90)) return 27;
        destroy(temp_single);
        local = {"local", "The capital of France is", nullptr, "0"};
        a = {"pair12", "The capital of Japan is", "1,2", nullptr};
        if (!add_chat(local, model, vocab, local_cap) || !decode(local, vocab, true)) return 28;
        if (!add_chat(a, model, vocab, pair_cap) || !add_chat(b, model, vocab, pair_cap) ||
            !add_chat(c, model, vocab, single_cap)) return 29;
        if (!restore(a, pair10) || !restore(b, pair10) || !restore(c, single10)) return 30;
        if (!parallel_bench(vocab, {&local, &a, &b, &c}, tokens, "migrated_depth10")) return 31;
        if (!restore(a, pair90) || !restore(b, pair90) || !restore(c, single90)) return 32;
        if (!parallel_bench(vocab, {&local, &a, &b, &c}, tokens, "migrated_depth90")) return 33;
    } else if (std::string(argv[1]) == "depth_all") {
        if (!add_chat(b, model, vocab, pair_cap) || !decode(b, vocab, true)) return 16;
        if (!add_chat(c, model, vocab, single_cap) || !decode(c, vocab, true)) return 17;
        for (chat * item : {&a, &b, &c}) {
            const int cap = item == &c ? single_cap : pair_cap;
            if (!fill(*item, cap / 10)) return 18;
        }
        if (!parallel_bench(vocab, {&local, &a, &b, &c}, tokens, "depth10")) return 19;
        for (chat * item : {&a, &b, &c}) {
            const int cap = item == &c ? single_cap : pair_cap;
            if (!fill(*item, cap * 9 / 10)) return 20;
        }
        if (!parallel_bench(vocab, {&local, &a, &b, &c}, tokens, "depth90")) return 21;
    } else return 12;
    destroy(c);
    destroy(b);
    destroy(a);
    destroy(local);
    llama_model_free(model);
    return 0;
}
