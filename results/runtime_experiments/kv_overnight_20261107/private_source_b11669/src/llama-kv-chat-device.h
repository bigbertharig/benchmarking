#pragma once

#include "ggml-backend.h"

#include <stdexcept>

// Private experiment: thread-scoped placement for independent contexts.
extern thread_local int kv_chat_first;
extern thread_local int kv_chat_second;
extern "C" void llama_kv_chat_select(int first, int second);

static ggml_backend_dev_t kv_chat_device_for_layer(int il) {
    if (kv_chat_first < 0) return nullptr;
    const int selected = kv_chat_second >= 0 && il % 2 ? kv_chat_second : kv_chat_first;
    if (selected < 0) throw std::runtime_error("negative KV device index");
    int gpu_index = 0;
    for (size_t i = 0; i < ggml_backend_dev_count(); ++i) {
        auto dev = ggml_backend_dev_get(i);
        if (ggml_backend_dev_type(dev) != GGML_BACKEND_DEVICE_TYPE_GPU) continue;
        if (gpu_index++ == selected) return dev;
    }
    throw std::runtime_error("KV device index not found");
}
