# Harness - max-unsigned-short-validate-key-remaining--autonomous

Frozen text in `frozen-prediction.txt` (sha256 `887a9b35...`; amendments B2i, B3i of 2026-10-26). Written on pc07 (node0); trees `~/s4-b8-uk/u` (unit) and `~/s4-b8-uk/c` (node), both `copy-source.sh` + `ant jar`. Logs: `~/s4-b8-uk-logs/<run>/`. Port slot 7: 127.0.7.1, JMX 7170, native 9042.

| File | Tier | What it does |
|---|---|---|
| `KeyLenDriver.java` | unit (B2) | modes `bounds` (both validateKey methods at 8 lengths, null, UNSET), `stream N L` (fresh keys, none held), `hold L` (1,000 then 5,000 held, heap after full GC); `STAGE4 check` lines |
| `unit-run.sh [run]` | unit | compiles the driver outside the tree, runs bounds (stops if the boundary check fails), stream, hold 65535, hold 1; `summary.txt` with EXPECTED lines |
| `writer.py` | cluster | bundled Python driver: `schema`, `write <table> <K> <N> <seed>` (random keys, 32 in flight), `drop` |
| `cluster-run.py <run> [main\|quick]` | cluster (B3) | life 1 (pools 512 MiB): boundary precheck, K = 16/1024/32768/65535/65536 at N = 10,000, K = 16 at N = 650,000; life 2 (128 MiB): K = 32768; data on tmpfs `/dev/shm/s4-b8-uk/node`; `summary.txt` EXPECTED lines, `arms.jsonl`, `samples-*.csv`; node stopped on any exit |
| `selfcheck.py <logs>/run1` | both | re-parses the raw outputs and node logs; 46 parts |
