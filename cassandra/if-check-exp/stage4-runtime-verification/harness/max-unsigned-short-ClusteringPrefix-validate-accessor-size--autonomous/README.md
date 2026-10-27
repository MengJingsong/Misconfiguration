# Harness - max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous

Frozen text in `frozen-prediction.txt` (sha256 `363886fb...`; amendments B2i, B3i of 2026-10-26). Written on pc07 (node0); tree `~/s4-b9-cp` (`copy-source.sh` + `ant jar`). Logs: `~/s4-b9-cp-logs/<run>/`. Port slot 6: 127.0.6.1, JMX 7160, native 9042.

| File | Tier | What it does |
|---|---|---|
| `ClusterKeyDriver.java` | unit (B2) | modes `grid` (S x N grid, mixed cells, null/empty/static, ArrayClustering; exact messages), `stream M S` (fresh clusterings, none held), `series S cap` (hold clusterings, heap after full GC every 10,000 to 100,000; cap 0 = all); `STAGE4 check` lines |
| `unit-run.sh [run]` | unit | compiles the driver outside the tree, runs grid (stops if the boundary check fails), stream, series S=1000 x3, S=1, capped; `summary.txt` with EXPECTED lines |
| `writer.py` | cluster | bundled Python driver: `schema`, `schema2`, `write`, `write2`, `probe`, `drop` |
| `cluster-run.py <run> [main\|quick]` | cluster (B3) | life 1 (pools 256 MiB): single and two-ck precheck (stop on mismatch), five arms; life 2 (64 MiB): K=65535 control and the probe (CAS insert, slice delete); data on tmpfs `/dev/shm/s4-b9-cp/node`; `summary.txt` EXPECTED lines, `arms.jsonl`, `samples-*.csv`; node stopped on any exit |
| `selfcheck.py <logs>/run1` | both | re-parses the raw outputs and node logs; 77 parts |
