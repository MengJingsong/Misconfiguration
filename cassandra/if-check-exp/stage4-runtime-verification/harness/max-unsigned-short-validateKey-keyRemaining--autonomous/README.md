# Harness - max-unsigned-short-validateKey-keyRemaining--autonomous

Frozen text in `frozen-prediction.txt` (sha256 `b61ddc2e...`; amendments B2i, B3i of 2026-10-26). Written on pc12 (node1); trees `~/s4-b9-vk/u` (unit) and `~/s4-b9-vk/c` (node), both `copy-source.sh` + `ant jar`. Logs: `~/s4-b9-vk-logs/<run>/`. Port slot 5: 127.0.5.1, JMX 7150, Byteman agent 19150, native 9042.

| File | Tier | What it does |
|---|---|---|
| `KeyLenDriver.java` | unit (B2) | modes `bounds` (both validators at 8 lengths, null, Int32 order check), `stream N L` (fresh keys through `Validation.validateKey`, none held), `hold L` (1,000 then 5,000 held), `oom L` (`-Xmx256m`), `control` (`HeapPool` 64 MiB: 1,024 allocations of 65535 B, the 1,025th blocks); `STAGE4 check` lines |
| `unit-run.sh [run]` | unit | compiles the driver outside the tree, runs bounds (stops if the boundary check fails), stream, hold 65535, hold 1, oom, control; `summary.txt` with EXPECTED lines |
| `writer.py` | cluster | bundled Python driver: `schema`, `write <table> <K> <N> <seed>` (8-byte counter + random bytes, 100-byte random value, 32 in flight), `drop` |
| `cluster-run.py <run> [main\|quick\|mid]` | cluster (B3) | life 1 (heap_buffers, pool 256 MiB): boundary precheck, K = 1000 and 65535 at N = 10,000 and 100,000, K = 65536 x 100; life 2 (128 MiB): K = 65535, N = 100,000; Byteman trace of `Validation.validateKey`, `QueryProcessor.validateKey` and every "Key length of" exception with its stack; data on tmpfs `/dev/shm/s4-b9-vk/node`; node stopped on any exit; `summary.txt` EXPECTED lines, `arms.jsonl`, `samples-*.csv`. `quick` and `mid` are shakedowns |
| `selfcheck.py <logs>/run1` | both | re-parses the raw outputs and node logs |
