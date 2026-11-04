# Harness — logs_virtual_table_default_rows-addtobuffer-messagebuffer_size--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 `42b13399…`, see the results file
[§1](../../results/logs_virtual_table_default_rows-addtobuffer-messagebuffer_size--autonomous.md)). Written 2026-10-28 on `pc39`.
Run copies (from `copy-source.sh` of `cassandra/cassandra-5.0.9`): `~/s4-lv` (build A, `ant build-test`) and `~/s4-lvB` (build B: `cp -a` of `~/s4-lv`,
`LogMessagesTable.java:58` changed to `1_000`, `VirtualTableAppender.java` and `CassandraRelevantProperties.java` touched, `ant jar`).
**Trap:** `LOGS_VIRTUAL_TABLE_DEFAULT_ROWS` is a compile-time constant and is inlined into `VirtualTableAppender`; without the `touch`, `ant jar` leaves the
appender at 50,000. Check with `javap -p -c … VirtualTableAppender | grep -E 'sipush|ldc'` (`cluster-run.py` prints it for each run).

| File | Tier | What it does |
|---|---|---|
| `VtableBufferProbe.java` | unit (B2) | package `org.apache.cassandra.db.virtual` (for the package-private `LogMessagesTable(String,int)` and `resolveBufferSize()`); compiled by `unit-run.sh` into `<copy>/build/probe`, not into the repository. Pushes events through `VirtualTableAppender.doAppend` (mode `appender`) or into a `LogMessagesTable` as well (mode `table`); reads `messageBuffer` / `buffer` by reflection; live-instance counts and heap after a full GC through the in-process `DiagnosticCommand` MBean. `STAGE4 …` lines. |
| `unit-run.sh <copy> <out>` | unit | one JVM per cell (`-Xms2g -Xmx2g -XX:+UseSerialGC`): N in 0/1000/49999/50000/50001/120000 at 100 B, N in 50000/120000 at 10 KiB, `max.rows` m in 1000/50000/100000 (and 500) with 120,000 events; output `unit.out`. |
| `lv.btm` | cluster | Byteman, observation only: counts events reaching `addToBuffer`, prints `messageBuffer.size()` and the wall-clock ms on entry/exit of `flushBuffer()`. |
| `make-node.sh on\|off` | cluster (B3a) | node conf under `~/stage4-tmp/lv/node`: tag yaml + local dirs, SerialGC, and (on) the CQLLOG appender uncommented at TRACE and the `org.apache.cassandra` logger at TRACE. |
| `seed.py`, `seed-run.sh` | cluster | seed 40 keyspaces x 25 tables (RF 1) on a stock node, drain, keep the data in `~/stage4-tmp/lv/seed` (took 1,165 s). |
| `readlogs.py` | cluster | counts `system_views.system_logs` rows client-side without paging (paging returns only the first page), split at the flush millisecond. |
| `cluster-run.py <label> A\|B on\|off <max_rows> full\|startup` | cluster (B3e) | one node start: copy of the seed, `-Xms1g -Xmx1g`, Byteman, 5-s sampler (`jcmd GC.class_histogram` for `LoggingEvent` and `LogMessage`, `GC.heap_info`, RSS), table read right after start-up and after the stress phase (`cassandra-stress write n=1500000` + `nodetool flush`), `debug.log` lines before the flush; `readings.txt`. |
| `chain.sh` | both | run 1 as one background job: unit tier, then runs R1 (A, off), R2 (A, on, 100000), R3 (B, on, 100000), R4 (A, on, 1000), two start-up-only repetitions each of R2 and R3. |
| `selfcheck.py <run1 dir>` | both | independent re-parse of the raw run-1 files; copied to `results/<stem>/run1/` with its output. |
