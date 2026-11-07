from pathlib import Path
import sys

root = Path(sys.argv[1])
cache = root / "src/llama-kv-cache.cpp"
text = cache.read_text()
old = '''                const int index = std::atoi(selected);
                if (index < 0 || index >= (int) model.devices.size()) {
                    throw std::runtime_error("invalid LLAMA_KV_DEVICE_INDEX");
                }
                dev = model.devices[index].dev;
'''
new = '''                const int index = std::atoi(selected);
                int gpu_index = 0;
                dev = nullptr;
                for (size_t i = 0; i < ggml_backend_dev_count(); ++i) {
                    auto candidate = ggml_backend_dev_get(i);
                    if (ggml_backend_dev_type(candidate) != GGML_BACKEND_DEVICE_TYPE_GPU) continue;
                    if (gpu_index++ == index) { dev = candidate; break; }
                }
                if (!dev) throw std::runtime_error("invalid LLAMA_KV_DEVICE_INDEX");
'''
assert text.count(old) == 1
cache.write_text(text.replace(old, new, 1))

context = root / "src/llama-context.cpp"
text = context.read_text()
old = '''        // add ACCEL backends (such as BLAS)
'''
new = '''        // Add cache workers even when the model's weights use only one GPU.
        if (std::getenv("LLAMA_KV_DEVICE_INDEX")) {
            for (size_t i = 0; i < ggml_backend_dev_count(); ++i) {
                auto dev = ggml_backend_dev_get(i);
                if (ggml_backend_dev_type(dev) != GGML_BACKEND_DEVICE_TYPE_GPU) continue;
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
        }

        // add ACCEL backends (such as BLAS)
'''
assert text.count(old) == 1
text = text.replace(old, new, 1)
old = '''                const int index = std::atoi(selected);
                if (index >= 0 && index < (int) model.devices.size()) {
                    const auto dev = model.devices[index].dev;
                    for (const auto & backend : backends) {
                        if (ggml_backend_get_device(backend.get()) == dev &&
                            ggml_backend_supports_op(backend.get(), cur)) {
                            ggml_backend_sched_set_tensor_backend(sched.get(), cur, backend.get());
                        }
                    }
                }
'''
new = '''                const int index = std::atoi(selected);
                int gpu_index = 0;
                ggml_backend_dev_t dev = nullptr;
                for (size_t i = 0; i < ggml_backend_dev_count(); ++i) {
                    auto candidate = ggml_backend_dev_get(i);
                    if (ggml_backend_dev_type(candidate) != GGML_BACKEND_DEVICE_TYPE_GPU) continue;
                    if (gpu_index++ == index) { dev = candidate; break; }
                }
                if (dev) {
                    for (const auto & backend : backends) {
                        if (ggml_backend_get_device(backend.get()) == dev &&
                            ggml_backend_supports_op(backend.get(), cur)) {
                            ggml_backend_sched_set_tensor_backend(sched.get(), cur, backend.get());
                        }
                    }
                }
'''
assert text.count(old) == 1
context.write_text(text.replace(old, new, 1))
