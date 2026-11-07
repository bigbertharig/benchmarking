from pathlib import Path
import sys

root = Path(sys.argv[1])
header = root / 'src/llama-kv-chat-device.h'
source = header.read_text()
source = source.replace('#include <cstdio>\n#include <cstdlib>\n', '')
start = source.index('// Private experiment: select one or two CUDA cache workers by layer parity.')
end = source.index('    if (selected < 0)', start)
source = source[:start] + '''// Private experiment: thread-scoped placement for independent contexts.
extern thread_local int kv_chat_first;
extern thread_local int kv_chat_second;
extern "C" void llama_kv_chat_select(int first, int second);

static ggml_backend_dev_t kv_chat_device_for_layer(int il) {
    if (kv_chat_first < 0) return nullptr;
    const int selected = kv_chat_second >= 0 && il % 2 ? kv_chat_second : kv_chat_first;
''' + source[end:]
header.write_text(source)

context = root / 'src/llama-context.cpp'
source = context.read_text()
marker = '//\n// llama_context\n//'
assert marker in source
source = source.replace(marker, '''thread_local int kv_chat_first = -1;
thread_local int kv_chat_second = -1;

extern "C" LLAMA_API void llama_kv_chat_select(int first, int second) {
    kv_chat_first = first;
    kv_chat_second = second;
}

''' + marker, 1)
context.write_text(source)

harness = root / 'examples/simple/simple.cpp'
source = harness.read_text()
source = source.replace('#include <string>\n', '#include <string>\n#include <atomic>\n#include <thread>\n')
old = '''static void select_chat(const chat & c) {
    if (c.pair) {
        setenv("LLAMA_KV_DEVICE_PAIR", c.pair, 1);
        unsetenv("LLAMA_KV_DEVICE_INDEX");
    } else {
        unsetenv("LLAMA_KV_DEVICE_PAIR");
        setenv("LLAMA_KV_DEVICE_INDEX", c.single, 1);
    }
}
'''
new = '''extern "C" void llama_kv_chat_select(int first, int second);

static void select_chat(const chat & c) {
    if (c.pair) {
        int first = -1, second = -1;
        if (std::sscanf(c.pair, "%d,%d", &first, &second) != 2) std::abort();
        llama_kv_chat_select(first, second);
    } else {
        llama_kv_chat_select(std::atoi(c.single), -1);
    }
}
'''
assert old in source
source = source.replace(old, new)
marker = 'static void destroy(chat & c) {'
parallel = '''static bool parallel_bench(const llama_vocab * vocab, const std::vector<chat *> & chats,
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
    std::fprintf(stderr, "PARALLEL phase=%s chats=%zu tokens_each=%d seconds=%.6f aggregate_tps=%.6f ok=%d\\n",
                 phase, chats.size(), tokens, seconds, chats.size() * tokens / seconds, ok.load());
    return ok.load();
}

'''
assert marker in source
source = source.replace(marker, parallel + marker)
old = '''    } else if (std::string(argv[1]) == "depth") {
        const int ten = pair_cap / 10;
        const int ninety = pair_cap * 9 / 10;
        if (!fill(a, ten) || !bench(a, vocab, tokens, "depth10")) return 9;
        if (!fill(a, ninety) || !bench(a, vocab, tokens, "depth90")) return 10;
        if (!bench(local, vocab, tokens, "local_short_after_depth")) return 11;
    } else return 12;
'''
new = '''    } else if (std::string(argv[1]) == "depth") {
        const int ten = pair_cap / 10;
        const int ninety = pair_cap * 9 / 10;
        if (!fill(a, ten) || !bench(a, vocab, tokens, "depth10")) return 9;
        if (!fill(a, ninety) || !bench(a, vocab, tokens, "depth90")) return 10;
        if (!bench(local, vocab, tokens, "local_short_after_depth")) return 11;
    } else if (std::string(argv[1]) == "parallel") {
        if (!add_chat(b, model, vocab, pair_cap) || !decode(b, vocab, true)) return 13;
        if (!add_chat(c, model, vocab, single_cap) || !decode(c, vocab, true)) return 14;
        if (!parallel_bench(vocab, {&local, &a, &b, &c}, tokens, "short")) return 15;
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
'''
assert old in source
source = source.replace(old, new)
harness.write_text(source)
