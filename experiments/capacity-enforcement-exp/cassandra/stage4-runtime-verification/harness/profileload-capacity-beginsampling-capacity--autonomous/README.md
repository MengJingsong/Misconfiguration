# Harness: profileload-capacity-beginsampling-capacity--autonomous (order o123)

Stage-4 harness, run 1 on `ms0604` (Utah m400, aarch64), 2026-11-24. Node copies under `/mydata/jingsong-cass-s4/o123/harness/`.

| File | Role |
|---|---|
| `MaxSamplerCapacityProbeTest.java` | Unit tier test class, verbatim from case B2c as amended by S4-A5 (`println(String.format(...))`). Copied into the local source copy's `test/unit/org/apache/cassandra/metrics/`. |
| `SamplerCtl.java` | Cluster-tier JMX helper, verbatim from case B3a (single-file `java SamplerCtl.java ...` launch). |
| `run-unit.sh` | B2e: `ant jar build-test`, copy the test, `ant testsome`, extract `RESULT` lines from `build/test/logs/_jdk11/TEST-...log`, process check. Logs every command (`run1/unit-restart/run-unit.log`). |
| `run-cluster.sh` | B3e with S4-A3/S4-A6: start node (2G heap), warm-up stress, baseline histo, `-s 2000` rejection, four arms (C = 256, 1024, 100000, 2000000) of begin / 1M-write stress / drain / flush / M1 / finish + begin(1,1) / M2 / cqlsh TRUNCATE, then stop and leftover check. Logs every command. |
| `analyze.py` | Applies the frozen B2f/B2g (S4-A2) and B3f/B3g (S4-A4) rules to the raw files (test log; per-arm histo, heap-info, stress output, the run log's D/W lines). Output `run1/analysis.txt`. |
| `freeze-pred.txt`, `freeze.sha256` | Frozen text of B2f+B2g+B3f+B3g after the audit and its sha256 (`a219b9ab…`), taken before any reading. |
| `case-as-filed.md` | The case file as stage 3 filed it (sha256 `e2a78b88…`), before the audit's amendments. |
| `md5.txt` | md5 of the harness files as run. |

Instrument checks: the unit test compiled and ran (`tests="3" failures="0" errors="0"`); its first attempt showed the logger defect (D1), fixed by S4-A5.
`SamplerCtl` was checked by the run itself (begin rc 0; `finish` returned 11 entries per arm). `analyze.py` was checked on the shakedown
cluster attempt (`run1/cluster-attempt1/`) against values read by hand from the histo files (counts 256/1024/100000/1000000).
