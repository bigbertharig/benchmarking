from pathlib import Path
import sys

path = Path(sys.argv[1]) / 'examples/simple/simple.cpp'
source = path.read_text()
marker = '    if (!add_chat(local, model, vocab, local_cap) || !decode(local, vocab, true)) return 4;'
insert = '''    if (std::string(argv[1]) == "five_parallel" ||
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
'''
assert marker in source
source = source.replace(marker, insert + marker, 1)
path.write_text(source)
