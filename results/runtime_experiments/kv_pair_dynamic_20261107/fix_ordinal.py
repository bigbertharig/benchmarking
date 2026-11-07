from pathlib import Path
import sys

root = Path(sys.argv[1])
cache = root / "src/llama-kv-cache.cpp"
text = cache.read_text()
old = '''    for (uint32_t il = 0; il < n_layer; il++) {
        if (!hparams.has_kv(il)) {
'''
new = '''    uint32_t kv_ordinal = 0;
    for (uint32_t il = 0; il < n_layer; il++) {
        if (!hparams.has_kv(il)) {
'''
assert text.count(old) == 1
text = text.replace(old, new, 1)
old = '''        if (filter && !filter(il)) {
'''
new = '''        const uint32_t cache_ordinal = kv_ordinal++;

        if (filter && !filter(il)) {
'''
assert text.count(old) >= 1
text = text.replace(old, new, 1)
old = 'if (auto selected = kv_chat_device_for_layer(il)) dev = selected;'
new = 'if (auto selected = kv_chat_device_for_layer(cache_ordinal)) dev = selected;'
assert text.count(old) == 1
cache.write_text(text.replace(old, new, 1))

context = root / "src/llama-context.cpp"
text = context.read_text()
old = '''        if (strcmp(name, "kv_fattn") == 0) {
            if (auto dev = kv_chat_device_for_layer(il)) {
'''
new = '''        if (strcmp(name, "kv_fattn") == 0) {
            int cache_ordinal = 0;
            for (int layer = 0; layer < il; ++layer) {
                if (model.hparams.has_kv(layer)) ++cache_ordinal;
            }
            if (auto dev = kv_chat_device_for_layer(cache_ordinal)) {
'''
assert text.count(old) == 1
context.write_text(text.replace(old, new, 1))
