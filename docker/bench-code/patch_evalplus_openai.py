#!/usr/bin/env python3
"""Make EvalPlus 0.3.1 count an OpenAI null content response as empty code.

The OpenAI chat schema permits message.content=None. EvalPlus's provider passes
that value to its sanitizer, which raises instead of recording an incorrect
answer. Keep the change pinned to the reviewed upstream expression.
"""
from pathlib import Path

import evalplus.provider.openai as provider

source = Path(provider.__file__)
before = "outputs.append(item.message.content)"
after = 'outputs.append(item.message.content or "")'
text = source.read_text(encoding="utf-8")
if text.count(before) != 1 or after in text:
    raise SystemExit(f"unexpected EvalPlus OpenAI provider source: {source}")
source.write_text(text.replace(before, after), encoding="utf-8")
print(f"patched {source}")
