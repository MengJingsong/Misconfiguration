# Harness — max_value_size-read-maxValueSize

Stage-4 harness for the case's §9 as amended by the step-0 audit (frozen §9 hash in the results file §1). Written 2026-10-13 by the
long-path AI session that first audited the case; that session's repository copy was lost and this folder was restored on
2026-10-14 from the node copy, byte for byte (the md5s every 2026-10-13 run summary printed). Run from a copy on the node,
`~/stage4-harness-run/mvs/`; compare `md5sum`
with this folder before run 1. Logs go to `~/stage4-logs/mvs/<run>/` (`STAGE4_LOGROOT` overrides it for shakedowns).

| File | Tier | What it does |
|---|---|---|
| `MaxValueSizeGuardTest.java` | unit | 9e unit step 1 in one JVM: read-back before any set, an unrecorded warm-up pass at 1 MiB, then at 1, 4, 8 and 256 MiB (set live with `setMaxValueSize`): the check (`readBuffer` at *M*, *M* + 1, 2³¹−1, 2³¹ and the vint 2⁶⁴−1), `readArray`, the clustering site, the fixed-length / limit-0 / skip / sibling controls, and (not at 256 MiB) `Mutation.serializer` and the local read response (`ReadResponse.createSimpleDataResponse` → `makeIterator`, added by the audit), plus the live change 1 → 4 MiB in the 1 MiB pass. *Δ* from `com.sun.management.ThreadMXBean.getThreadAllocatedBytes()`. Prints `STAGE4 check <name> <expected> <actual> ok\|MISMATCH`, fails at the end on any mismatch. Package `org.apache.cassandra.db.marshal`. |
| `make-unit-yaml.sh <label> <value>` | unit | `build/test/mvs-<label>.yaml` = the unit yaml + `max_value_size: <value>` (range controls only). |
| `unit-run.sh [harness\|range\|upstream\|all]` | unit | The harness test, the range controls `range-hi` (2048MiB) and `range-zero` (0MiB), and the upstream `SSTableWriterTest`; one summary line each. Output `<logroot>/unit/`. |
| `make-node-yaml.sh <label> <value\|none>` | cluster | Rebuilds `conf/cassandra.yaml` from the tag with the 9b hold-fixed settings (batch commit-log sync, 10 s read and write timeouts) and the knob. |
| `value-alloc.btm` | cluster | Byteman observation rules at the entry of `ByteArrayAccessor.read(DataInputPlus, int)` and `ByteBufferUtil.read(DataInput, int)` for lengths ≥ 262,144: `alloc class=… length=… thread=… ms=…` to `stage4.byteman.out`. Cassandra classes, so no `boot:`. |
| `send-value.py` | cluster | Bundled driver, protocol 4, 120 s timeout, CL ONE, `FallthroughRetryPolicy` (the default policy retries a `ServerError` on the next host, which on one node surfaces as `NoHostAvailable`): `probe`, `settings`, `insert [--table t] <pk> <bytes>`, `readback [--table t] <pk>`. One `OK`/`ERR <class>` line with JSON. |
| `cluster-run.py` | cluster | Modes `instrument` (TestScript, probe, idle, known-answer rows, settings), `value <1m\|4m\|8m\|default>` (Phase 1: control, writes, scenario C before the flush, flush, A, B, separation), `compaction` (1 MiB), `replay` (4 → 1 → 4 MiB, no wipe between starts), `down`. Each read records the `system.log` bytes and trace lines it added. `EXPECTED:` lines in `summary.txt`, `readings.csv`, `session.log`; stops at a failed instrument, control or set-up check; node stopped and yaml restored on any exit. |
