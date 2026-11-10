# Shared-storage restart correction (2026-11-09)

The initial campaign found that a stale incomplete file blocked a retry
because each Docker process used PID 1 in its temporary filename. The
corrected build used unique pending names. It ignored the incomplete file,
recovered committed turn 1 exactly, committed turn 2, and a further fresh
process recovered turn 2 exactly. See the [durability result](../qwen35-return-durable-20261109/README.md).
