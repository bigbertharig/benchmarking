from pathlib import Path
import sys

root = Path(sys.argv[1])
context = root / "src/llama-context.cpp"
text = context.read_text()
old = '''        // Add cache workers even when the model's weights use only one GPU.
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
'''
new = '''        // Add this context's cache worker even when weights use only one GPU.
        if (const char * selected = std::getenv("LLAMA_KV_DEVICE_INDEX")) {
            const int target = std::atoi(selected);
            int gpu_index = 0;
            for (size_t i = 0; i < ggml_backend_dev_count(); ++i) {
                auto dev = ggml_backend_dev_get(i);
                if (ggml_backend_dev_type(dev) != GGML_BACKEND_DEVICE_TYPE_GPU) continue;
                if (gpu_index++ != target) continue;
                bool present = false;
                for (const auto & backend : backends) {
                    present |= ggml_backend_get_device(backend.get()) == dev;
                }
                if (!present) {
                    auto backend = ggml_backend_dev_init(dev, nullptr);
                    if (!backend) throw std::runtime_error("failed to initialize KV GPU backend");
                    backends.emplace_back(backend);
                }
                break;
            }
        }
'''
assert text.count(old) == 1
context.write_text(text.replace(old, new, 1))

simple = root / "examples/simple/simple.cpp"
text = simple.read_text()
text = text.replace('''    if (argc != 2) {
        std::fprintf(stderr, "usage: llama-simple MODEL.gguf\\n");
''', '''    if (argc != 3) {
        std::fprintf(stderr, "usage: llama-simple MODEL.gguf CONTEXT\\n");
''', 1)
old = '''    const std::string prompts[] = {"The capital of France is", "The capital of Japan is"};
    llama_context * contexts[2] = {};
    llama_sampler * samplers[2] = {};
    std::vector<llama_token> batches[2];
'''
new = '''    constexpr int n_chats = 5;
    const std::string prompts[n_chats] = {
        "The capital of France is", "The capital of Japan is",
        "The capital of Germany is", "The capital of Italy is",
        "The capital of Spain is"};
    llama_context * contexts[n_chats] = {};
    llama_sampler * samplers[n_chats] = {};
    std::vector<llama_token> batches[n_chats];
'''
assert text.count(old) == 1
text = text.replace(old, new, 1)
assert text.count('i < 2') == 3
text = text.replace('i < 2', 'i < n_chats')
assert text.count('cp.n_ctx = 4096;') == 1
text = text.replace('cp.n_ctx = 4096;', 'cp.n_ctx = std::atoi(argv[2]);', 1)
simple.write_text(text)
