# Ten-turn return checkpoint growth (2026-11-09)

At 200K occupied context, one 1060 worker completed ten turns using a host
base checkpoint plus ordered outbound/return updates. Every recall passed,
and the final GPU0 reconstruction matched the worker state byte for byte.
Temporary GPU0 rebuild grew from 0.35 to 0.49 s as the update chain grew
from zero to 20 updates. See the [full return-path result](../qwen35-return-delta-20261109/README.md).

The initial run under `qwen35-return-chain10-20261109/` completed only two
turns because the shell runner had not forwarded `KV_RETURN_TURNS` into
Docker. This corrected run uses the forwarded setting and has a separate
terminal receipt.
