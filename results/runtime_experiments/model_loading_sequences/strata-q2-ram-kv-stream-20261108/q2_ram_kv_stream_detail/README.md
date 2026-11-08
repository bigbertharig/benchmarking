# Strata Q2 RAM-backed KV beyond a 32K resident window

The `strata-q2-ram-kv-stream-20261108` sequence passed on 2026-11-08 with
the rig's installed Strata engine 0.1.56, Qwen3.8 Flash Next Q2, one 3090,
64K configured context, INT8 KV, and `--kv-resident 32768`. The plan required
no download, and the live engine command contained the requested flag. The
engine was launched and stopped cleanly under the Manager lease and host-memory
guard. The ordinary 27B chat profile was restored afterward.

The first request occupied **42,084 prompt tokens**, past the 32K resident
window, and correctly returned `ORCHID`. Its prompt processing took 37.73 s
at 1,115.5 tok/s; 41 generated tokens ran at 62.9 tok/s. A follow-up sent
the history again and correctly returned `ORCHID` in 1.14 s wall time.
Strata reported `cache_n=42,079` and only 38 newly processed prompt tokens
on that follow-up. This demonstrates prefix reuse across a >32K occupied
conversation with RAM-backed KV streaming requested at launch.

GPU0 use was 23,459 MiB just after load, 23,607 MiB after the first request,
and 23,629 MiB after the follow-up. Host `MemAvailable` was 29,862,184 KiB
before launch, 17,881,656 KiB after load, 17,121,840 KiB after the first
request, and 15,937,920 KiB after the follow-up. These whole-system figures
include resident experts and other allocations; they do not isolate the KV
buffer's physical RAM bytes. No direct KV buffer allocation line was retained
by the control-plane receipt. This test has one chat and a repeated ledger
prompt, so it does not establish multiple independent long conversations or
a speed comparison against nonstreamed KV.

Evidence: [`terminal.json`](terminal.json), the saved plan and launch files,
and the two request response JSON files in this directory. The sequence
summary is [`../terminal.json`](../terminal.json).
