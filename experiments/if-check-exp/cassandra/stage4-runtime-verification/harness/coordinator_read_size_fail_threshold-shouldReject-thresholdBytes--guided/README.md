# Harness — coordinator_read_size_fail_threshold-shouldReject-thresholdBytes

Instruments for the case's §9 (stage 4), written 2026-10-15 after the step-0 audit froze §9a (`d563a86e…`). Results:
[`../../results/coordinator_read_size_fail_threshold-shouldReject-thresholdBytes.md`](../../results/coordinator_read_size_fail_threshold-shouldReject-thresholdBytes--guided.md).
Copy the folder to the node (`~/stage4-harness-run/crs/`) and compare `md5sum` with the repository before a run. The node's
clone is `~/cassandra-run1` at `b5f2a54` (`cassandra-5.0.9`).

| File | What it is | Checked how |
|---|---|---|
| `CoordinatorReadSizeGuardTest.java` | Unit tier, package `org.apache.cassandra.cql3`, `extends CQLTester` with `requireNetwork()`. White-box loop that mirrors `SelectStatement.process()` (`processPartition()` on a real `ResultSetBuilder`, the replica answer built as the coordinator receives it, rows pulled counted by a `Transformation`, thread-allocated bytes around the loop); client path over protocol 5 (Java driver: `ReadFailureException.getFailuresMap()`); meters; frame `encodedSize`; arms (paging, `count(*)`, switch off, internal query, `system_schema` at 1 B). Prints `STAGE4 check <name> <expected> <actual> ok\|MISMATCH` and `STAGE4 info`. | its known-answer checks (completed counter = 1,008·*n*) |
| `unit-run.sh [harness\|upstream\|all]` | Copies the test into the clone and runs it; `upstream` runs the optional dtest `CoordinatorReadSizeWarningTest`. Output `${STAGE4_LOGROOT:-~/stage4-logs/crs}/unit/`. | — |
| `coord-read.btm` | Byteman, observation only: `guard-fail` at the throw of `SelectStatement.maybeFail` (all keyspaces), `result` at `ResultSetBuilder.build` exit (`ks1.t` only), `coord-alloc` around the 8-argument `SelectStatement.process` (`ks1`), `frame` at `ResultSet$Codec.encode` entry (`ks1.t`). | `TestScript`: no errors (logged by `cluster-run.py`) |
| `CoordAlloc.java`, `Alloc.java`, `read-alloc.btm` | Helpers compiled into a jar on the boot class path (the node runs from the jar); `read-alloc.btm` and `Alloc.java` are the sibling's files unchanged (the replica's `LocalReadRunnable`). | the instrument read writes one line of each kind |
| `Jmx.java` | From `column_index_cache_size`'s harness, plus value types `bool:` and `null:` (a null write restores the limit to unset). | read-back after every set |
| `make-node-yaml.sh` | The tag's yaml plus `read_thresholds_enabled: true`. | the diff stat is logged |
| `send-read.py` | The sibling's client; used only for `probe` and `load`, before any limit is set. | `probe` prints protocol 5 |
| `cluster-run.py <label>` | One node lifetime: instrument checks (stop on failure), warm-up abort (runbook fix after shakedown 1), control, the four values, scenario C, the 1 B window; **one driver `Session` for the whole lifetime** (amendment (2)); `summary.txt` with `EXPECTED:` lines, `readings.csv`, `session.log`, `crs.trace`, `system.log` copy. | shakedown 1 and 2 (not readings) |
