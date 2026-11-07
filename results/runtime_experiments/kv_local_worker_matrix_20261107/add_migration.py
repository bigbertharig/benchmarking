from pathlib import Path
import sys

path = Path(sys.argv[1]) / 'examples/simple/simple.cpp'
source = path.read_text()
source = source.replace('int cap) {\n    select_chat(c);', 'int cap, bool fast = false) {\n    select_chat(c);', 1)
source = source.replace('cp.n_batch = 64;\n    cp.n_ubatch = 8;',
                        'cp.n_batch = fast ? 512 : 64;\n    cp.n_ubatch = fast ? 32 : 8;', 1)
source = source.replace('static bool fill(chat & c, int target) {', 'static bool fill(chat & c, int target, int block_size = 64) {', 1)
source = source.replace('std::vector<llama_token> block(64, filler);',
                        'std::vector<llama_token> block(block_size, filler);', 1)
source = source.replace('std::min(64, target - c.used)',
                        'std::min(block_size, target - c.used)', 1)
marker = 'static bool parallel_bench('
insert = '''struct snapshot {
    std::vector<uint8_t> data;
    llama_token next = 0;
    int used = 0;
};

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
    std::fprintf(stderr, "STATE_SAVE name=%s used=%d bytes=%zu seconds=%.3f\\n",
                 c.name, state.used, copied, seconds);
    return true;
}

static bool restore(chat & c, const snapshot & state) {
    select_chat(c);
    const auto start = clock_type::now();
    const size_t copied = llama_state_set_data(c.ctx, state.data.data(), state.data.size());
    if (copied != state.data.size()) {
        std::fprintf(stderr, "STATE_RESTORE_FAILED name=%s read=%zu expected=%zu\\n",
                     c.name, copied, state.data.size());
        return false;
    }
    c.next.assign(1, state.next);
    c.used = state.used;
    const double seconds = std::chrono::duration<double>(clock_type::now() - start).count();
    std::fprintf(stderr, "STATE_RESTORE name=%s used=%d bytes=%zu seconds=%.3f\\n",
                 c.name, c.used, copied, seconds);
    return true;
}

'''
assert marker in source
source = source.replace(marker, insert + marker, 1)
marker = '''    } else if (std::string(argv[1]) == "depth_all") {'''
new_mode = '''    } else if (std::string(argv[1]) == "migrate_depth_all") {
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
'''
assert marker in source
source = source.replace(marker, new_mode + marker, 1)
path.write_text(source)
