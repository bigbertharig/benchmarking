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
    return true;
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

static void destroy(chat & c) {
    if (c.sampler) llama_sampler_free(c.sampler);
    if (c.ctx) llama_free(c.ctx);
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
    const char * device_spec = std::getenv("KV_MODEL_DEVICES");
    const char * split_spec = std::getenv("KV_MODEL_SPLIT");
    if (device_spec && *device_spec) {
        std::stringstream device_stream(device_spec);
        std::string item;
        std::vector<int> indexes;
        while (std::getline(device_stream, item, ',')) indexes.push_back(std::stoi(item));
        std::vector<ggml_backend_dev_t> all_gpus;
        for (size_t i = 0; i < ggml_backend_dev_count(); ++i) {
            auto dev = ggml_backend_dev_get(i);
            if (ggml_backend_dev_type(dev) == GGML_BACKEND_DEVICE_TYPE_GPU) all_gpus.push_back(dev);
        }
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
