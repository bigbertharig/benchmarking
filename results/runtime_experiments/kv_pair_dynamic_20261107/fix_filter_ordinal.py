from pathlib import Path
import sys

root = Path(sys.argv[1])
cache = root / 'src/llama-kv-cache.cpp'
text = cache.read_text()
old = '''        const uint32_t cache_ordinal = kv_ordinal++;

        if (filter && !filter(il)) {
            LLAMA_LOG_DEBUG("%s: layer %3d: filtered\\n", __func__, il);
            continue;
        }
'''
new = '''        if (filter && !filter(il)) {
            LLAMA_LOG_DEBUG("%s: layer %3d: filtered\\n", __func__, il);
            continue;
        }

        const uint32_t cache_ordinal = kv_ordinal++;
'''
assert text.count(old) == 1
cache.write_text(text.replace(old, new, 1))

context = root / 'src/llama-context.cpp'
text = context.read_text()
old = 'if (model.hparams.has_kv(layer)) ++cache_ordinal;'
new = 'if (model.hparams.has_kv(layer) && !model.hparams.is_recr(layer)) ++cache_ordinal;'
assert text.count(old) == 1
context.write_text(text.replace(old, new, 1))
