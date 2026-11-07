from pathlib import Path
import sys

path = Path(sys.argv[1]) / 'examples/simple/simple.cpp'
source = path.read_text()
source = source.replace('#include <cstdio>', '#include <chrono>\n#include <cstdio>')
source = source.replace('if (argc != 4) {', 'if (argc != 4 && argc != 5) {')
source = source.replace('const int single_ctx = std::atoi(argv[3]);', 'const int single_ctx = std::atoi(argv[3]);\n    const int bench_tokens = argc == 5 ? std::atoi(argv[4]) : 0;')
marker = '    for (chat * item : {&a, &b, &c}) {\n        llama_sampler_free(item->sampler);'
insert = '''    for (chat * item : {&a, &b, &c}) {
        if (bench_tokens <= 0) break;
        const auto start = std::chrono::steady_clock::now();
        for (int i = 0; i < bench_tokens; ++i) {
            if (!decode(*item, vocab)) return 10;
        }
        const auto end = std::chrono::steady_clock::now();
        const double seconds = std::chrono::duration<double>(end - start).count();
        std::fprintf(stderr, "BENCH pair=%s single=%s tokens=%d seconds=%.6f tps=%.6f\\n",
                     item->pair ? item->pair : "-", item->single ? item->single : "-",
                     bench_tokens, seconds, bench_tokens / seconds);
    }

'''
assert marker in source
source = source.replace(marker, insert + marker)
path.write_text(source)
