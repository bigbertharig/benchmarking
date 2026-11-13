#!/usr/bin/env python3
"""Apply the experimental PLE packed-row bridge to an isolated llama.cpp tree."""
import argparse
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--source', type=Path, required=True)
args = ap.parse_args()
path = args.source / 'src/models/qwen4exp.cpp'
code = path.read_text()

def replace_once(old, new):
    global code
    if code.count(old) != 1:
        raise RuntimeError(f'expected one patch anchor, found {code.count(old)}: {old[:70]!r}')
    code = code.replace(old, new)

replace_once('#include <cinttypes>\n', '#include <cinttypes>\n#include <cstdlib>\n#include <dlfcn.h>\n#include <mutex>\n')
replace_once('    ggml_tensor * rows = nullptr;   // I32 [ple_n_heads * n_tokens]\n',
'''    ggml_tensor * rows = nullptr;   // I32 [ple_n_heads * n_tokens]
    ggml_tensor * packed_rows = nullptr; // dynamic packed rows from Pascal VRAM/file tier
''')
old = '''    {
        ggml_tensor * ple = model.per_layer_tok_embd;

        const bool prefetch = model.can_prefetch.count(ple);
        if (prefetch) {
            llama_prefetch_rows(ple, idx.data(), idx.size());
        }
    }

    ggml_backend_tensor_set(rows, idx.data(), 0, idx.size()*ggml_element_size(rows));
'''
new = '''    if (packed_rows) {
        // The plugin stores exact compressed GGUF rows on Pascal cards; the graph still
        // uses ggml_get_rows to dequantize them in the same way as the baseline.
        using init_fn = int (*)(const char *, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t);
        using fetch_fn = int (*)(const int32_t *, size_t, uint8_t *);
        using error_fn = const char * (*)();
        struct bridge {
            void * handle = nullptr;
            fetch_fn fetch = nullptr;
            error_fn error = nullptr;
        };
        static bridge b;
        static std::once_flag init_once;
        std::call_once(init_once, [&] {
            const char * lib = std::getenv("PLE_SHARD_LIB");
            const char * file = std::getenv("PLE_SHARD_GGUF");
            const char * offset_text = std::getenv("PLE_SHARD_OFFSET");
            if (!lib || !file || !offset_text) throw std::runtime_error("missing PLE shard library, GGUF or offset");
            b.handle = dlopen(lib, RTLD_NOW | RTLD_LOCAL);
            if (!b.handle) throw std::runtime_error(std::string("PLE dlopen: ") + dlerror());
            auto init = reinterpret_cast<init_fn>(dlsym(b.handle, "ple_shard_init"));
            b.fetch = reinterpret_cast<fetch_fn>(dlsym(b.handle, "ple_shard_fetch"));
            b.error = reinterpret_cast<error_fn>(dlsym(b.handle, "ple_shard_error"));
            if (!init || !b.fetch || !b.error) throw std::runtime_error("missing PLE shard plugin symbol");
            const auto cap = [](const char * name, uint64_t fallback) {
                const char * value = std::getenv(name);
                return value ? std::stoull(value) : fallback;
            };
            const uint64_t row_bytes = ggml_row_size(model.per_layer_tok_embd->type, model.per_layer_tok_embd->ne[0]);
            if (init(file, model.per_layer_tok_embd->ne[1], row_bytes, std::stoull(offset_text),
                     cap("PLE_1060_MIB", 5120), cap("PLE_1070_MIB", 7168)) != 0) {
                throw std::runtime_error(std::string("PLE shard init: ") + b.error());
            }
        });
        const size_t row_size = ggml_row_size(packed_rows->type, packed_rows->ne[0]);
        std::vector<uint8_t> packed(row_size * idx.size());
        if (b.fetch(idx.data(), idx.size(), packed.data()) != 0) {
            throw std::runtime_error(std::string("PLE shard fetch: ") + b.error());
        }
        ggml_backend_tensor_set(packed_rows, packed.data(), 0, packed.size());
        for (size_t i = 0; i < idx.size(); ++i) idx[i] = (int32_t) i;
    } else {
        ggml_tensor * ple = model.per_layer_tok_embd;
        if (model.can_prefetch.count(ple)) llama_prefetch_rows(ple, idx.data(), idx.size());
    }

    ggml_backend_tensor_set(rows, idx.data(), 0, idx.size()*ggml_element_size(rows));
'''
replace_once(old, new)
old = '''    ple_inp->rows = ggml_new_tensor_1d(ctx0, GGML_TYPE_I32, n_heads * n_tokens);
    ggml_set_input(ple_inp->rows);
    ggml_tensor * rows = ple_inp->rows;
    res->add_input(std::move(ple_inp));

    // gather then flatten the heads: get_rows lays the head dimension out slowest, as the reference does
    ggml_tensor * emb = ggml_get_rows(ctx0, model.per_layer_tok_embd, rows);
'''
new = '''    ple_inp->rows = ggml_new_tensor_1d(ctx0, GGML_TYPE_I32, n_heads * n_tokens);
    ggml_set_input(ple_inp->rows);
    ggml_tensor * rows = ple_inp->rows;
    ggml_tensor * table = model.per_layer_tok_embd;
    if (std::getenv("PLE_SHARD_LIB")) {
        ple_inp->packed_rows = ggml_new_tensor_2d(ctx0, table->type, table->ne[0], n_heads * n_tokens);
        ggml_set_input(ple_inp->packed_rows);
        table = ple_inp->packed_rows;
    }
    res->add_input(std::move(ple_inp));

    // gather then flatten the heads: get_rows lays the head dimension out slowest, as the reference does
    ggml_tensor * emb = ggml_get_rows(ctx0, table, rows);
'''
replace_once(old, new)
path.write_text(code)
print(f'patched {path}')
