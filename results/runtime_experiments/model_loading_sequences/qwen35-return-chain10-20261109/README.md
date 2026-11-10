# Initial turn-count forwarding check (2026-11-09)

This run passed two turns and exact state reconstruction, but it did not
exercise the intended ten turns. The launcher did not yet forward
`KV_RETURN_TURNS` into Docker. The [corrected ten-turn run](../qwen35-return-chain10-v2-20261109/README.md)
has its own label and terminal receipt; use that result for chain growth.
