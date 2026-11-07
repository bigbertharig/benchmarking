from pathlib import Path
import sys

root = Path(sys.argv[1])
header = root / "src/llama-kv-chat-device.h"
header.write_text(r'''#pragma once

#include "ggml-backend.h"

#include <cstdio>
#include <cstdlib>
#include <stdexcept>

// Private experiment: select one or two CUDA cache workers by layer parity.
static ggml_backend_dev_t kv_chat_device_for_layer(int il) {
    int selected = -1;
    if (const char * pair = std::getenv("LLAMA_KV_DEVICE_PAIR")) {
        int first = -1;
        int second = -1;
        if (std::sscanf(pair, "%d,%d", &first, &second) != 2) {
            throw std::runtime_error("invalid LLAMA_KV_DEVICE_PAIR");
        }
        selected = il % 2 ? second : first;
    } else if (const char * single = std::getenv("LLAMA_KV_DEVICE_INDEX")) {
        selected = std::atoi(single);
    } else {
        return nullptr;
    }
    if (selected < 0) throw std::runtime_error("negative KV device index");
    int gpu_index = 0;
    for (size_t i = 0; i < ggml_backend_dev_count(); ++i) {
        auto dev = ggml_backend_dev_get(i);
        if (ggml_backend_dev_type(dev) != GGML_BACKEND_DEVICE_TYPE_GPU) continue;
        if (gpu_index++ == selected) return dev;
    }
    throw std::runtime_error("KV device index not found");
}
''')

cache = root / "src/llama-kv-cache.cpp"
text = cache.read_text()
text = text.replace('#include "llama-kv-cache.h"\n',
                    '#include "llama-kv-cache.h"\n#include "llama-kv-chat-device.h"\n', 1)
old = '''            if (const char * selected = std::getenv("LLAMA_KV_DEVICE_INDEX")) {
                const int index = std::atoi(selected);
                int gpu_index = 0;
                dev = nullptr;
                for (size_t i = 0; i < ggml_backend_dev_count(); ++i) {
                    auto candidate = ggml_backend_dev_get(i);
                    if (ggml_backend_dev_type(candidate) != GGML_BACKEND_DEVICE_TYPE_GPU) continue;
                    if (gpu_index++ == index) { dev = candidate; break; }
                }
                if (!dev) throw std::runtime_error("invalid LLAMA_KV_DEVICE_INDEX");
            }
'''
new = '''            if (auto selected = kv_chat_device_for_layer(il)) dev = selected;
'''
assert text.count(old) == 1
cache.write_text(text.replace(old, new, 1))

context = root / "src/llama-context.cpp"
text = context.read_text()
text = text.replace('#include "llama-context.h"\n',
                    '#include "llama-context.h"\n#include "llama-kv-chat-device.h"\n', 1)
start = text.index('        // Add this context\'s cache worker even when weights use only one GPU.')
end = text.index('        // add ACCEL backends (such as BLAS)', start)
text = text[:start] + '''        // Add the selected cache workers even when weights use only GPU0.
        for (int il = 0; il < 2; ++il) {
            auto dev = kv_chat_device_for_layer(il);
            if (!dev) continue;
            bool present = false;
            for (const auto & backend : backends) {
                present |= ggml_backend_get_device(backend.get()) == dev;
            }
            if (!present) {
                auto backend = ggml_backend_dev_init(dev, nullptr);
                if (!backend) throw std::runtime_error("failed to initialize KV GPU backend");
                backends.emplace_back(backend);
            }
        }

''' + text[end:]
start = text.index('        if (strcmp(name, "kv_fattn") == 0) {')
end = text.index('        // - norm may be automatically assigned', start)
text = text[:start] + '''        if (strcmp(name, "kv_fattn") == 0) {
            if (auto dev = kv_chat_device_for_layer(il)) {
                for (const auto & backend : backends) {
                    if (ggml_backend_get_device(backend.get()) == dev &&
                        ggml_backend_supports_op(backend.get(), cur)) {
                        ggml_backend_sched_set_tensor_backend(sched.get(), cur, backend.get());
                    }
                }
            }
        }

''' + text[end:]
context.write_text(text)
