# Harness — parent_repair_status_cache_size-ActiveRepairService-repairStatusByCmd--autonomous (order o127)

Stage-4 harness, written 2026-11-25 for node `pc82` (x86_64), run data under `/mydata/jingsong-cass-s4/o127/` (synced there
as `harness/` and run from there). To become `cassandra/stage4-runtime-verification/harness/<stem>/` when the coordinator files it.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `case-as-filed.md` | — | the case file as filed (sha256 `5693e351…e58e0`, equal to `_INDEX.md` §4) | `sha256sum` |
| `freeze.sha256`, `freeze-pred.txt` | — | sha256 of the amended file at the last freeze (after S4-A6) and of B2f–B2h + B3f–B3h + the amendments | — |
| `ParentRepairStatusCapTest.java` | unit (B2) | the case's B2a class verbatim | shakedown N=10, m=200: final size 10, present 10 (`run1/unit/shakedown/`) |
| `unit-run.sh`, `unit-all.sh` | unit | copy the class, `ant testsome -Dtest.jvm.args=...` per value; readings from the test log (S4-A2); `unit-all.sh` = shakedown or the B2b sweep (8 JVMs) | shakedown |
| `Drive-as-filed.java` | cluster | the B3a driver verbatim, for reference | — |
| `Drive.java` | cluster (B3) | the B3a driver + S4-A3 (pool-idle fallback wait, `probe`, `pool`, `count` by status); run with Guava on the classpath (S4-A6 / D1) | shakedowns N=100, M=1000 (`run1/cluster/shake*`) |
| `mkconf.py` | cluster | B3a yaml edits (num_tokens 256, allocate_tokens commented, 127.0.0.1, directories under `$RUN`, `repair_state_size: 10`) | printed block in each `session.txt` |
| `cluster-run.sh`, `cluster-all.sh` | cluster | B3e per value: fresh dirs, start with the `-D`, schema, WARN logging, flush + histogram + heap_info (base, after, after+60s), drive, pool idle, probe, count, stop by PID | shakedown 2 |
| `analyze.py` | both | B2g/B3g checks with S4-A4/S4-A5 thresholds, from the raw files | output `run1/analysis.txt` |
| `md5.txt` | — | md5 of the harness files | — |
