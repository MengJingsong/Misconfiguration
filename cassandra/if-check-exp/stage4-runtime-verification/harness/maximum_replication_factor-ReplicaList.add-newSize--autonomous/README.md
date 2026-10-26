# Harness — maximum_replication_factor-ReplicaList.add-newSize--autonomous

Stage-4 harness for the autonomous case file (frozen hashes in the results file
[§1](../../results/maximum_replication_factor-ReplicaList.add-newSize--autonomous.md)). Written 2026-10-26 after the step-0 audit and before
any run-1 reading. Run on `pc12`; unit tier in the tree `~/s4-b7-rl` (`copy-source.sh`, `ant build-test`), cluster tier from the tree
`~/s4-b7-rl-node` (`copy-source.sh`, `ant jar`; stress and cqlsh come from it), node data on tmpfs `/dev/shm/s4-b7-rl`, logs in
`~/s4-b7-rl-logs/<run>/`. Port slot 1: loopback 127.0.1.1 (storage 7000, native 9042), JMX 7110. No Byteman.

| File | Tier | What it does |
|---|---|---|
| `ReplicaListGrowthTest.java` | unit (B2) | Package `org.apache.cassandra.locator`. One `@Test`: growth of a `ReplicaList` for N in 1,2,3,4,9,10,100,10_000,1_000_000 from capacity 0 and from capacity N (capacity, reallocations by array identity, bytes by `ObjectSizes` and the JVM's measure), literals of the amended prediction, threshold sweep -1/1/3 (identical readings), guard control (`Guardrails.maximumReplicationFactor.guard(...)` throws above the threshold, not at it, not at -1), builder capacity = RF, heap of 10 retained 1M lists against the instrument. `STAGE4 check <name> ok\|MISMATCH <detail>` lines; first check `instrument-enabled`. |
| `unit-run.sh <run>` | unit | Copies the test into the tree, runs `ant testsome` once, summary with EXPECTED line. |
| `Jmx.java` | cluster | `get` (attribute) and `setrf warn fail` (GuardrailsMBean setter, reads both back). |
| `cluster-run.py run` | cluster (B3e) | One node lifetime (see its docstring): P0 first-trigger DDL control as an ordinary role at threshold 1, then thresholds -1,1,3,-1,1,3 each with a 1M-row stress write and `GC.class_histogram` every 10 s, DDL controls, the 200-keyspace step. |
| `selfcheck.py` | both | Independent re-parse of the raw logs (written after the runs; reads `out.txt`, `hist.csv`, `ddl.csv`, `stress-*.txt`). |

Reading rules (fixed before run 1): retained `Replica[]` bytes of a phase = the `after-stress` sample (the histogram forces a full GC, so it is
live data). Noise = the difference between the two phases at the same threshold; "equal across thresholds" = max-min of the phase means
within 10 percent of their mean, or within 50 KB if the values are below 500 KB. Live heap = the histogram total (not `GC.heap_info`).
