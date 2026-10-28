# Harness — diagnostic_event_memory_store_max_size-store-keyhead--autonomous

Written 2026-10-27 on `pc32` (step 1 of stage 4); run from `~/stage4-harness/diag/` against `~/cassandra-run1` (`cassandra-5.0.9`, `ant build-test`), `~/cassandra-run2` (literal `maxSize = 50`) and `~/cassandra-run3` (literal `maxSize = 1000`), both `ant jar`. Logs: `~/stage4-logs/diag/run1/` on the node.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `DiagnosticEventMemoryStoreCapTest.java` | unit (B2) | package `org.apache.cassandra.diag.store`; part 1 size / key range / live weak refs for m in {1,50,200,1000}; part 2 64 KiB payload heap at checkpoints; part 3 8 threads x 20000; part 4 unbounded `ConcurrentSkipListMap` control; method `payloadNoRefList` (supplementary, added after run 1) | `javac` against the clone; first run is the known-answer check (153 PASS) |
| `unit-run.sh <run>` | unit | copies the test into the clone, `ant testsome ... -Dtest.jvm.args=-Xmx1g`, then the upstream `DiagnosticEventMemoryStoreTest` | run 1 |
| `DiagJmx.java` | cluster | JMX client for `org.apache.cassandra.diag:type=DiagnosticEventService`: `enabled`, `enable`, `disable`, `read` (count, keys, operation bytes), `heap`, `drain` (unbounded client-side retainer). Needs Guava on its classpath (defect R-D2) | shakedown on S-50 |
| `cluster-run.py <arm> <run>` | cluster | arms S-50/S-200/S-1000 (small statements), L-50/L-200/L-1000 (256 KiB INSERT), OFF (L without the subscription), Q-50/Q-200/Q-1000/QOFF (256 KiB comment-padded SELECT, supplementary S1). Starts one node from the copy for the literal, JMX 7199, local storage; per checkpoint: `readEvents` count, `jcmd GC.class_histogram` (live) and `GC.heap_info`. S-200 also runs the SchemaEvent class and the retainer control | shakedown (S-50) |
| `chain.sh`, `chain-main.sh` | cluster | arm order: `chain-main.sh` = S-200 S-50 S-1000 L-200 L-50 L-1000 OFF (main run); `chain.sh` = Q-200 Q-50 Q-1000 QOFF (supplement S1) | — |
| `analyze.py <logroot>` | cluster | compares readings with the filed/amended predictions; prints PASS/FAIL and the paired ON-minus-OFF differences | run on the readings |
| `selfcheck.py <logroot>` | both | independent re-parse of the raw `hist-*.txt` files | — |
