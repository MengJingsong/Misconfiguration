# coordinator_read_size_fail_threshold (with local_read_size_fail_threshold, row_index_read_size_fail_threshold) — verification solution  <!-- file: cases/coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:1101`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L1101) (`1101#1`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5), Claude Code at Meta (version string not available), 2026-10-25; Band D triage mode |
| Estimate | `undetermined`. Line 1101 only checks that each `*_read_size_fail_threshold` is at least its warn threshold, at startup. The fail thresholds it guards do abort oversized reads, but the coordinator threshold counts result-set value bytes only after the replica has already serialized the whole page into a heap buffer. So the coordinator cap may bound only one of two page-sized copies. The local threshold aborts during that serialization and should bound both. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** The check at [`DatabaseDescriptor.java:1101`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L1101) is inside
`validateReadThresholds(name, warn, fail)` ([`DatabaseDescriptor.java:1099-1105`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L1099-L1105)). It is
called three times from `applyReadThresholdsValidations` ([`DatabaseDescriptor.java:1091-1097`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L1091-L1097))
for three pairs:
- `coordinator_read_size_{warn,fail}_threshold`
- `local_read_size_{warn,fail}_threshold`
- `row_index_read_size_{warn,fail}_threshold`

`applyReadThresholdsValidations` is called once, from `applySimpleConfig`
([`DatabaseDescriptor.java:785`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L785)). If `fail < warn` (both non-null), it throws `ConfigurationException`
and the node does not start.
- Kind: configuration entries (yaml). Declared at [`Config.java:527-532`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L527-L532), type
  `DataStorageSpec.LongBytesBound` (bytes, accepts `KiB`/`MiB` etc.). All default to `null`,
  which disables them.
- Master switch: `read_thresholds_enabled` ([`Config.java:526`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L526)), default `false`. It is documented
  at `conf/cassandra.yaml:2013-2030`.
- Settable at runtime: `DatabaseDescriptor.setCoordinatorReadSizeFailThreshold`
  ([`DatabaseDescriptor.java:4884-4888`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4884-L4888)), `setLocalReadSizeFailThreshold`
  (`:4908-4912`) and `setRowIndexReadSizeFailThreshold` (`:4932-4936`). These are exposed over JMX as
  `StorageService` attributes `CoordinatorLargeReadAbortThreshold`,
  `LocalReadTooLargeAbortThreshold` and `RowIndexReadSizeAbortThreshold`
  ([`StorageService.java:7300-7350`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L7300-L7350)), and `ReadThresholdsEnabled` ([`StorageService.java:7280`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L7280)).
  The runtime setters do **not** re-run the fail>=warn check, so the check at line 1101 is
  startup-only and can be bypassed.
- A yaml change needs a restart. A JMX change applies to the next query.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** Heap used to materialize one read:
- **Coordinator:** `ResultSetBuilder.size` is the sum of `ByteBuffer.remaining()` over every
  selected value added to the CQL result set of **one page** (`ResultSetBuilder.java:76-83`). It is
  compared with `shouldReject` (`ResultSetBuilder.java:95-98`).
- **Local (replica):** `QuerySizeTracking.sizeInBytes` is the cumulative `unsharedHeapSize()` of
  partition keys, rows, RT markers and deletions streamed out of the local read iterator
  (`ReadCommand.java:663-735`, compare at `:709-721`). For a `BufferCell` this includes the value
  bytes (`BufferCell.java:141-144`).
- **Row index:** the estimated materialized size of one `RowIndexEntry`
  (`RowIndexEntry.java:376-401`).

The check at line 1101 itself compares two limits, not a usage value.

**A3. Mechanism.**
1. Startup: [`DatabaseDescriptor.java:785`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L785) → `:1091-1097` → `:1101` rejects `fail < warn`.
2. Coordinator: `QueryOptions.ReadThresholds.create()` returns the disabled instance unless the
   daemon is initialized and `read_thresholds_enabled` is true ([`QueryOptions.java:276-281`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryOptions.java#L276-L281)).
   `SelectStatement.processPartition` calls `maybeFail` before each partition and before each row
   is added (`SelectStatement.java:1088-1092, 1104, 1132`). `maybeFail`
   ([`SelectStatement.java:1057-1083`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1057-L1083)) throws `ReadSizeAbortException` (reason `READ_SIZE`) once
   `size > threshold`, and marks `CoordinatorReadSizeAborts` and `CoordinatorReadSize`. The overshoot
   is up to one row, by design (comment at [`SelectStatement.java:1127-1131`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1127-L1131)). Each page builds a new
   `ResultSetBuilder` ([`SelectStatement.java:1004`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1004)), so the cap is per page.
3. Local: [`SelectStatement.java:334-335`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L334-L335) calls `query.trackWarnings()` only on the client
   `execute` path. `ReadCommand.executeLocally` wraps the iterator with `withQuerySizeTracking`
   ([`ReadCommand.java:457`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L457)) when `trackWarnings` is set, the keyspace is not a system keyspace, and
   some threshold is non-null ([`ReadCommand.java:657-661`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L657-L661)). On `>= failBytes` it throws
   `LocalReadSizeTooLargeException` ([`ReadCommand.java:715-722`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L715-L722)).
4. Where the copies live: for a local read the iterator is consumed by
   `command.createResponse` ([`StorageProxy.java:2211`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2211)) → `LocalDataResponse.build`. That serializes the
   **whole page** into a `DataOutputBuffer` on heap ([`ReadResponse.java:182-204`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadResponse.java#L182-L204)). The coordinator's
   `ResultSetBuilder` sees the rows only after this buffer has been built and deserialized. So the
   coordinator threshold cannot stop the replica-side buffer, which is bounded only by the page size.
   The local threshold throws during serialization and stops the buffer growing.
5. Bypasses: `read_thresholds_enabled: false` (default); system keyspaces; internal (non-client)
   queries for local tracking; JMX setters skip the line-1101 check.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), A3 (audit statement; no claim changed).** Facts the predictions below depend on, re-read in the pinned clone:
> 1. **Coordinator, exact rule.** `maybeFail` runs at the start of `processPartition` and after `newRow` of each row but **before** that row's values are added (`SelectStatement.java:1088, 1124-1132`); `ResultSetBuilder.size` adds `remaining()` of every selected value ([`ResultSetBuilder.java:76-83`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java#L76-L83)); reject iff `size > T` (`:95-98`). There is no check after a page's last row. With `SELECT *` on `(pk int, ck int, v blob)` and 65,536-byte values a row counts s = 4 + 4 + 65,536 = **65,544 B**. One page of P rows from one partition is refused iff (P − 1)·s > T, and then at the start of row m + 1 with counted size m·s, m = ⌊T/s⌋ + 1 (T = 256 KiB: m = 4, 262,176 B; T = 1 MiB: m = 16, 1,048,704 B; T = 4 MiB: m = 64, 4,194,816 B). A page that is not refused records P·s in `CoordinatorReadSize` (`maybeWarn`, [`SelectStatement.java:1041-1045`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1041-L1045), runs whenever the switch is on, thresholds set or not). Each page builds a new `ResultSetBuilder` (`:1004`).
> 2. **Local, exact rule.** `QuerySizeTracking` is applied below the row filter and the limit counter ([`ReadCommand.java:457`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L457) before `:473, 491`), so it sees exactly the rows the page pulls; it adds `sizeOnHeapOf(partition key)` and the partition deletion, then `unsharedHeapSize()` of each row, h = BTreeRow + BufferCell + `sizeOnHeapOf(value)` > 65,536 ([`BTreeRow.java:532-541`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/BTreeRow.java#L532-L541), [`BufferCell.java:141-144`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/BufferCell.java#L141-L144), [`ObjectSizes.java:155-174`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/ObjectSizes.java#L155-L174)), and throws at the first row where the total b0 + k·h **≥** T ([`ReadCommand.java:709-722`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L709-L722)). With h − 65,536 small, k = T / 65,536 exactly (4, 16, 64 at 256 KiB, 1 MiB, 4 MiB): a page of P rows is refused iff k ≤ P, i.e. **also when P × 65,536 = T** (where the coordinator rule does not refuse). `LocalReadSize` is updated on close with the total at the throw (`:731-736`); the exception message carries it (`attempted to read <X> bytes`). The `LocalReadSizeTooLargeException` is a `RejectException`: `LocalReadRunnable` answers with an empty response plus `LOCAL_READ_SIZE_FAIL` ([`StorageProxy.java:2212-2219`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2212-L2219)), `ReadCallback` turns it into `READ_SIZE` (code 4) and `ReadSizeAbortException` ([`ReadCallback.java:192-198`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/ReadCallback.java#L192-L198), [`WarningsSnapshot.java:113-115`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/thresholds/WarningsSnapshot.java#L113-L115)); `LocalReadSizeAborts` is marked in `CoordinatorWarnings.done()` from the native-transport dispatcher ([`Dispatcher.java:376-441`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Dispatcher.java#L376-L441), [`CoordinatorWarnings.java:94`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/thresholds/CoordinatorWarnings.java#L94)).
> 3. **The master switch** is consulted only on the client path: `QueryOptions.ReadThresholds.create()` ([`QueryOptions.java:276-281`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryOptions.java#L276-L281)) gates `maybeWarn`/`maybeFail` and [`SelectStatement.java:334-335`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L334-L335) (`trackWarnings`). `ReadCommand.shouldTrackSize` (`:656-661`) does **not** read it: a command with `trackWarnings()` set by hand is tracked with the switch off.
> 4. **The replica buffer.** `LocalDataResponse.build` serializes into `new DataOutputBuffer()` (heap, initial 128 B; [`ReadResponse.java:193-204`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadResponse.java#L193-L204), [`BufferedDataOutputStreamPlus.java:70-78`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java#L70-L78)); on overflow by c bytes the capacity becomes max(2·cap, cap + c) below 64 MiB ([`DataOutputBuffer.java:158-183`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L158-L183), [`BufferedDataOutputStreamPlus.java:124-139`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java#L124-L139)), so for serialized length *len* the final capacity *cap* ∈ [len, 2·len + 65,664]; `buffer()` returns a duplicate of that array. The SSTable read allocates each value's array (`ByteBufferUtil.read():449`) on the thread that runs `LocalReadRunnable.runMayThrow` (the iterator is consumed inside `createResponse`, [`StorageProxy.java:2209-2212`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2209-L2212)). Hence a completed page allocates ≥ 2·P·65,536 B on that thread (values + final buffer), and a page refused by the local threshold at row k allocates ≤ k·65,600 (values) + 2·(2·T + 65,664) (all buffer arrays) + small objects < **5·T + 1 MiB** for T ≥ 256 KiB. Neither path reads the coordinator threshold.
> 5. **Metrics resolution.** `CoordinatorReadSize` and `LocalReadSize` are `DecayingEstimatedHistogramReservoir` histograms; `getMax()` returns the bucket offset **≥** the largest value (`DecayingEstimatedHistogramReservoir.java:281-300, 537-550`; offsets ×1.2, [`EstimatedHistogram.java:91-106`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/EstimatedHistogram.java#L91-L106)): bucket(262,176) = 263,210; bucket(1,048,576 … 1,131,752) = 1,131,752; bucket(4,194,304 … 4,866,323) = 4,866,323. A max can be checked only as "equals the bucket of the predicted value" (the filed `coordMax ∈ (T, T + 64 KiB + 1 KiB]` is not resolvable from the histogram; the cluster tier reads the exact size with Byteman).
> 6. **Line 1101** (`validateReadThresholds`) is reached from `applySimpleConfig` (`:785`) through the package-private `applyReadThresholdsValidations(Config)` (`:1091-1097`, `@VisibleForTesting static`): a test outside `org.apache.cassandra.config` must call it by reflection. The message is `<name>_fail_threshold (<fail>) must be greater than or equal to <name>_warn_threshold (<warn>)`. The runtime setters (`:4850-4936`) and the JMX attributes on `StorageService` (`:7274-7350`) do not call it. **Path per arm:** unit arms set thresholds with the `DatabaseDescriptor` setters (runtime path, check skipped); cluster arms set them in `cassandra.yaml` (start-up path, check run and passed because no warn threshold is set); the start-up refusal uses the yaml path.
> 7. **Heap region size.** The shipped `conf/jvm11-server.options:66` sets `-XX:G1HeapRegionSize=16m` (not the 2 MiB ergonomic size B3d assumes); the humongous threshold is half a region.

**A4. Other consumers.** Other heap that is not under these thresholds:
- the replica response buffer described in A3.4, when only the coordinator threshold is set;
- Netty encoding of the result message;
- the driver/native-transport queues (`native_transport_*` limits);
- the memtable, caches and compaction.

**A5. Evidence beyond the source.** CASSANDRA-16850 (cited at `conf/cassandra.yaml:2014`;
https://issues.apache.org/jira/browse/CASSANDRA-16850). Unit test of the line-1101 check:
`test/unit/org/apache/cassandra/config/DatabaseDescriptorTest.java:709-731`. Distributed tests
`test/distributed/org/apache/cassandra/distributed/test/thresholds/CoordinatorReadSizeWarningTest.java`
(sets thresholds through the runtime setters, `:41-44`), `LocalReadSizeWarningTest.java` and
`RowIndexSizeWarningTest.java`.

## B. Verification solution

**B1. Claim under test.** With `read_thresholds_enabled: true` and a fail threshold T:
- (a) `local_read_size_fail_threshold = T` bounds the per-query read heap (replica response buffer
  plus result set) to about T plus one row.
- (b) `coordinator_read_size_fail_threshold = T` bounds the counted result-set size to about T plus
  one row, but **not** the replica response buffer. Node heap per in-flight query therefore still
  follows the page size, not T.

Separately, the line-1101 check only rejects `fail < warn` at startup.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B1 (operational reading for the verdict; the claim is unchanged).** (a) holds at the operand level if every local-arm page that A3-amendment fact 2 says is refused is refused, with the tracked total X ∈ [T, T + h), and the replica's work for that page stays bounded by T and independent of P: no completed response buffer, and per-page allocation < 5·T + 1 MiB (fact 4) at every P. (a) is **refuted** by a page refused late or not at all, X ≥ T + h, or a page-sized replica buffer/allocation under the local threshold. (b) holds if every coordinator-arm page that fact 1 says is refused is refused at counted size m·s (≤ T + one row) **and** the replica response buffer for that page is the same as with no threshold (page-sized, ≥ P·65,536 B). (b) is **refuted** by a refusal missing or late (counted size > T + s), or by a replica buffer that shrinks towards T under the coordinator threshold. "Node heap per in-flight query follows the page size" is read as: the per-query replica buffer and allocation scale with P under C as under N (cluster tier, B3f), corroborated by the aggregate heap. Separately: line 1101 rejects `fail < warn` (and accepts `fail ≥ warn`) at start-up; the runtime setters do not.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant.
- Clone the tag to local disk: `git clone --branch cassandra-5.0.9 --depth 1 <shared-clone> /local/c509`,
  then `cd /local/c509 && ant jar build-test`.
- Test source: `/local/c509/test/unit/org/apache/cassandra/cql3/ReadSizeCapUnitTest.java`. It extends
  `CQLTester` (in-JVM storage plus an in-JVM native server through `requireNetwork()`; no node process).
- Run: `ant testsome -Dtest.name=org.apache.cassandra.cql3.ReadSizeCapUnitTest`. The jamm agent is
  added by `build.xml:1159`. The test JVM uses the build's default heap.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2a.** This host (`environment-advisor.md`): run clone `$W/cassandra-run22` (`W=~/Library/Caches/stage4`, tag `cassandra-5.0.9`, `b5f2a54210`), built with `ant -Dlocal.repository=$W/m2 build-test` (no `--depth 1`, no `ant jar`: `build-test` builds what `testsome` needs). The test is copied to `test/unit/org/apache/cassandra/cql3/ReadSizeCapUnitTest.java` in that clone only and run with `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.cql3.ReadSizeCapUnitTest -Dtest.jvm.args=-Dstage4.out=<file>` (test yaml `test/conf/cassandra.yaml`, not modified; its `read_thresholds_enabled: true` is overridden per combination by the setter). Script `harness/<stem>/unit-run.sh`; the test prints `STAGE4 row …` / `STAGE4 check …` lines.

**B2b. Knobs.** Each is set in the test with the `DatabaseDescriptor` setters, after
`DatabaseDescriptor.setReadThresholdsEnabled(true)`:
- T ∈ {256 KiB, 1 MiB, 4 MiB}, applied to (i) `setCoordinatorReadSizeFailThreshold` only, and
  (ii) `setLocalReadSizeFailThreshold` only.
- Control: no thresholds.
- Page size P ∈ {16, 64} rows.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2b.** Combinations (15), each on its own table:
> - control `N`: switch on, all six thresholds null, P ∈ {16, 64};
> - coordinator arm `C`: switch on, only `coordinator_read_size_fail_threshold` = T, T ∈ {262,144; 1,048,576; 4,194,304} B, P ∈ {16, 64};
> - local arm `L`: switch on, only `local_read_size_fail_threshold` = T, same T and P;
> - switch-off control `OFF` (B2h): switch off, coordinator **and** local fail thresholds = 262,144 B, P = 16.
> Thresholds are set with `DatabaseDescriptor.setReadThresholdsEnabled` / `set*ReadSize{Warn,Fail}Threshold` (runtime path; A3 fact 6) and read back with the getters before the query; after the combination all are reset to null and the switch to on. The default (null) is the control, so T has three values plus the default.

**B2c. Workload.** Table `(pk int, ck int, v blob, PRIMARY KEY (pk, ck))` with one partition
`pk=0` and 128 rows, each `v` = 64 KiB of random bytes, flushed (`flush()`).
- Page bytes = P × 64 KiB: 1 MiB at P=16, 4 MiB at P=64.
- So T=256 KiB is exceeded at both P values, T=1 MiB is at the boundary for P=16, and T=4 MiB is at
  the boundary for P=64.
- Query: `executeNetWithPaging("SELECT * FROM %s WHERE pk = 0", P)`. Iterate all rows and catch
  `com.datastax.driver.core.exceptions.ReadFailureException`.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2c.** All 15 tables are created, filled (128 rows, 65,536 random bytes each, `execute` internal) and flushed **before** any threshold is set, then the driver's schema is allowed to settle (`checkSchemaAgreement`); this keeps the driver's schema refreshes away from a small coordinator threshold (the guided case on this check saw `system_schema` reads refused at a tiny limit). "Page bytes" means P × 65,536. Predicted outcome per combination comes from A3 facts 1–2, not from "page bytes ≤ T": at the boundary P × 65,536 = T the coordinator arm does **not** refuse and the local arm **does**.

**B2d. Observables and instruments.**
- (1) Coordinator operand: `getCurrentColumnFamilyStore().metric.coordinatorReadSize.getSnapshot().getMax()`.
  This is updated with `result.getSize()` on abort (`SelectStatement.java:1069-1073`) and per page
  (`:1044-1045`). Also `metric.coordinatorReadSizeAborts.getCount()`.
- (2) Local operand: `metric.localReadSize` max and `metric.localReadSizeAborts` count
  (`TableMetrics.java:863-864`).
- (3) Replica response buffer, measured directly:
  - Build `ReadCommand cmd = Util.cmd(cfs, 0).withLimit(P).build(); cmd.trackWarnings();`.
  - In `try (ReadExecutionController ec = cmd.executionController(); UnfilteredPartitionIterator it = cmd.executeLocally(ec))`,
    call `ReadResponse r = cmd.createResponse(it, ec.getRepairedDataInfo())`.
  - Record `ObjectSizes.measureDeep(r)`, or the exception thrown.
- Cannot observe: the transient `ResultSet` heap itself. It is inferred from (1).

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2d.** Per combination, after the client query: (1) `CoordinatorReadSize` `getMax()` and `CoordinatorReadSizeAborts` count of the fresh table; (2) `LocalReadSize` `getMax()` and `LocalReadSizeAborts`; client outcome: rows received, and for a `ReadFailureException` its failure map codes. (3) as filed (`respBytes` = `cap` = `ObjectSizes.measureDeep(r)`, which counts the whole backing array), plus `len` = `remaining()` of the response's data buffer (field `DataResponse.data`, read by reflection), and `alloc` = bytes allocated by the test thread across `executeLocally` + `createResponse` (`ThreadMXBean.getThreadAllocatedBytes`; support recorded); on `LocalReadSizeTooLargeException` the X of its message and `alloc`. Before the combinations, a mirror pass with no thresholds reads one page of P = 128 rows from the first table through `executeLocally` and records b0 (key + partition deletion) and each row's h (as the closed `local_read_size_fail_threshold` guided harness does), from which k(T) = min{k : b0 + k·h ≥ T} and X(T) = b0 + k·h are computed.

**B2e. Procedure.**
1. `@BeforeClass`: `requireNetwork()`.
2. For each arm × T × P: reset the thresholds and create a fresh table.
3. Insert, flush, and record metric baselines.
4. Run the paged query and record the outcome (rows returned / exception).
5. Record the metric deltas.
6. Run step (3) of B2d.
7. Print one CSV line per combination to stdout: `arm,T,P,rows,aborted,coordMax,localMax,respBytes`.
8. Also assert the line-1101 behaviour:
   - `DatabaseDescriptor.applyReadThresholdsValidations(conf)` with fail=1KiB, warn=2KiB throws.
   - `DatabaseDescriptor.setCoordinatorReadSizeFailThreshold(1KiB)` after
     `setCoordinatorReadSizeWarnThreshold(2KiB)` does not throw (the bypass).

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2e.** Order: mirror; the 15 combinations in the order N16, N64, C×(T, P), L×(T, P), OFF; then the line-1101 asserts. Step 8's call is made by reflection (A3 fact 6) for each of the three pairs: (fail, warn) = (1 KiB, 2 KiB) throws `ConfigurationException` with the exact message; (2 KiB, 1 KiB) and (1 KiB, 1 KiB) do not throw. The bypass is shown for each pair: warn = 2 KiB then fail = 1 KiB through the setters, no exception, getters read back `1KiB` / `2KiB`. A shakedown at a non-arm value (T = 524,288, P = 32, arms C and L, one table each, system property `stage4.mode=shakedown`) checks the instruments before run 1; it is not a reading.

**B2f. Predictions.**
- Control: no aborts. `respBytes` ≈ P × 64 KiB (≥ 1 MiB at P=16, ≥ 4 MiB at P=64).
- Coordinator arm, page bytes > T: aborted. `coordMax` ∈ (T, T + 64 KiB + 1 KiB]. `respBytes`
  (B2d-3) is unchanged from the control (≈ P × 64 KiB), because the coordinator threshold is not
  consulted there.
- Local arm, page bytes > T: aborted. `localMax` ∈ [T, T + 66 KiB]. Step (3) throws
  `LocalReadSizeTooLargeException` before the buffer exceeds ≈ T + 64 KiB.
- Page bytes ≤ T (for example T=4 MiB, P=16): no abort in either arm.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2f (exact forms; the filed relations are kept where the source supports them).** s = 65,544; m, k, X from A3 facts 1–2 and the mirror; bucket() from fact 5.
> - (u1) Mirror: every h equal, 65,536 < h < 66,560; k(262,144) = 4, k(1,048,576) = 16, k(4,194,304) = 64.
> - (u2) **N** (both P): 128 rows, no exception; `CoordinatorReadSize` max = bucket(P·s) (1,131,752 at P = 16; 4,866,323 at P = 64); `LocalReadSize` max = 0 and both abort counts 0; step 3: `len` = S(P) with P·65,536 ≤ S(P) ≤ P·65,600 + 512, `cap` ∈ [S(P), 2·S(P) + 65,664 + 4,096], `alloc` ≥ 2·P·65,536.
> - (u3) **C**, refused iff (P − 1)·s > T, i.e. (262,144, 16), (262,144, 64), (1,048,576, 64): `ReadFailureException`, 0 rows, failure code 4, `CoordinatorReadSizeAborts` = 1, `CoordinatorReadSize` max = bucket(m·s) (263,210; 263,210; 1,131,752). Not refused, (1,048,576, 16), (4,194,304, 16), (4,194,304, 64): 128 rows, aborts 0, max = bucket(P·s). In every C combination `LocalReadSizeAborts` = 0, and step 3 gives `len` = S(P) of N at the same P (equal), `cap` and `alloc` in the N bands: the coordinator threshold does not change the replica buffer.
> - (u4) **L**, refused iff k(T) ≤ P, i.e. every combination except (4,194,304, 16): `ReadFailureException`, 0 rows, code 4, `LocalReadSizeAborts` = 1, `LocalReadSize` max = bucket(X(T)), `CoordinatorReadSizeAborts` = 0; step 3 throws `LocalReadSizeTooLargeException` with X = X(T) ∈ [T, T + h) and `alloc` < 5·T + 1 MiB (fact 4), the same within 10 % at P = 16 and 64 for the same T. (4,194,304, 16): 128 rows, no abort, `LocalReadSize` max = bucket(b0 + 16·h) = 1,131,752, step 3 completes with `len` = S(16).
> - (u5) **OFF**: 128 rows, no exception, both histograms' max = 0 and both abort counts 0 (switch off: no `maybeWarn`, no `trackWarnings`); step 3 (with `trackWarnings()` set by hand) **throws** with X = X(262,144) (fact 3).
> - (u6) Line 1101: the three (1 KiB, 2 KiB) calls throw with the exact messages, the (2, 1) and (1, 1) calls do not; the three setter bypasses do not throw and read back.

> **Amendment 2026-10-27 (after run 1, authorised by the user) — B2f (u3) and (u4), the replica `len` relation.** This amendment follows run 1's readings. In unit run 1 the clause "step 3 gives `len` = S(P) of N (equal)" of (u3) failed in 4 of 6 C combinations and the clause "step 3 completes with `len` = S(16)" of (u4) failed for L (4,194,304, 16), by a few bytes each, and the tier was Not confirmed (results file §4.2, §5.1). The user (Yang, the advisor) authorised this amendment and a re-run of the whole unit tier on 2026-10-27. **What was known when writing it:** all of run 1's unit readings, including every `len` (N: S(16) = 1,048,787, S(64) = 4,195,098; the differences from N of −1, 0, +11, −7, 0, +13 B in the six C combinations and −2 B for L (4,194,304, 16)), the run-1 self-check's attribution to `SerializationHeader.java:165-168`, and run 1's section D suggestion of a 9·P + 64 B tolerance. That suggestion was not used; the value below is derived from the serializer alone. **Run 1's readings would pass the amended relation** (largest |difference| 2 B at P = 16 against 152 B, 13 B at P = 64 against 536 B); no tolerance that admits any per-row timestamp encoding could have failed them, so the amendment is not a test that run 1 could have failed, and it is stated so here.
> **Derivation of the tolerance δ(P) from the source.** Step 3 measures `len` = the length of `LocalDataResponse.build`'s buffer (`ReadResponse.java:197-203`), written by `UnfilteredPartitionIterators.Serializer.serialize` (`UnfilteredPartitionIterators.java:329-343`: three booleans for one partition) and `UnfilteredRowIteratorSerializer.serialize` (`UnfilteredRowIteratorSerializer.java:91-154`). For two B2c tables and the same P, every byte written is the same except those that encode timestamps or other per-table statistics:
> - the partition key `pk = 0` with its vint length (`UnfilteredRowIteratorSerializer.java:114`), the flags byte (`:137`), the column subset (`SerializationHeader.java:403-405`; the same selection and columns), and the end-of-partition byte (`:153`, `UnfilteredSerializer.java:413-416`) are identical;
> - per row, the flags byte (`UnfilteredSerializer.java:164-186`; the same flags in every table: liveness present, no TTL, no deletion, all columns, no extended flags), the clustering (`ClusteringPrefix.java:455-477`: a header vint that depends only on null/empty values, then `ck` as a fixed 4-byte `Int32Type` value, `AbstractType.java:538-544`, `Int32Type.java:156-159`) and the cell (flags byte, `Cell.java:268-290`; value as a vint length 65,536 plus 65,536 bytes, `AbstractType.java:548-550`) are identical. The cell writes no timestamp because each `INSERT` gives the row liveness and the cell the same `timestamp` (`UpdateParameters.java:126, 172`), so `useRowTimestamp` holds (`Cell.java:274, 292-293`). The on-wire row has no row-size or previous-size fields (they are written only for an SSTable header, `UnfilteredSerializer.java:193-209`);
> - **variable per table:** per row, the liveness timestamp as an unsigned vint of `timestamp − stats.minTimestamp` (`UnfilteredSerializer.java:223-224`, `SerializationHeader.java:165-168`); per partition, the three `EncodingStats` fields as unsigned vints (`EncodingStats.java:272-277`, called at `SerializationHeader.java:393`). Every unsigned vint, including `writeUnsignedVInt32` (`VIntCoding.java:329-332`), takes 1 to 9 bytes (`VIntCoding.java:535-540`: size = (639 − 9·nlz(v|1)) >> 6 ∈ [1, 9]).
> Hence for two such tables at the same P, |len₁ − len₂| ≤ 8·P (one vint per row) + 3·8 (the three header vints): **δ(P) = 8·P + 24 B**, i.e. δ(16) = 152 B, δ(64) = 536 B. A buffer cut towards T loses at least one row, i.e. ≥ 65,536 B ≫ δ(P), so the relation still separates "page-sized as with no threshold" from "shrunk towards T".
> **Amended clauses.** In (u3), "`len` = S(P) of N at the same P (equal)" is replaced by **|`len` − S(P)| ≤ δ(P)**, with S(P) the N `len` at the same P. In (u4), "(4,194,304, 16): … step 3 completes with `len` = S(16)" is replaced by **step 3 completes with |`len` − S(16)| ≤ δ(16)**. Every other clause of (u1)–(u6), including the `cap` and `alloc` bands, is unchanged.
> **Re-run.** The whole unit tier runs again from its beginning (shakedown first, B2e) in a fresh clone `$W/cassandra-run66` (tag `cassandra-5.0.9`, `ant -Dlocal.repository=$W/m2 build-test`), raw logs `$W/logs/coordinator_read_size_fail_threshold-validateReadThresholds/unit-run2/` (shakedown `unit-run2-shakedown/`), with the run-1 harness unchanged (`ReadSizeCapUnitTest.java` already records `len`; only the self-check evaluates the amended relation). B1, the relations that held, B2h and the cluster tier (B3) are unchanged.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Coordinator arm: `coordMax` ≤ T + one row and abort; `respBytes` ≈ control | Claim (b) confirmed: the coordinator cap bounds only the result set |
| Local arm: abort, step (3) throws at ≈ T | Claim (a) confirmed at the operand level |
| Coordinator arm: `coordMax` ≫ T + one row, or no abort when page bytes > T | Mechanism not as traced. Claim refuted |
| Coordinator arm: `respBytes` drops to ≈ T | Claim (b) refuted: the coordinator cap also bounds the replica buffer |
| Local arm: no abort, or `localMax` ≫ T | Claim (a) refuted |
| Control `respBytes` does not scale with P | Positive control failed. Not confirmed |
| Line-1101 assert: fail<warn accepted by `applyReadThresholdsValidations` | Check not as traced |

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2g (rows made exact; the filed rows keep their meaning).** **Confirmed** (claims (a) and (b) at the unit tier): (u1)–(u6) hold. Effect: local threshold caps the replica's read for a page; coordinator threshold caps only the counted result set (bypass: the replica buffer) → `caps only on some paths (bypass)`. **Refuted (b)**: a C combination predicted refused returns rows, or one predicted not refused is refused, or its `CoordinatorReadSize` max ≠ the predicted bucket (counted size not T + at most one row), or step 3 under C gives `len` < S(P) of N (the coordinator threshold reaches the replica buffer). **Refuted (a)**: an L combination predicted refused returns rows, or one predicted not refused is refused, or step 3 completes (a page-sized buffer) where a refusal is predicted, or X ∉ [T, T + h), or `alloc` ≥ 5·T + 1 MiB or differs by more than 10 % between P = 16 and 64. **Refuted (line 1101)**: a (1 KiB, 2 KiB) call does not throw, or (2, 1)/(1, 1) throws; a setter call throws (no bypass). **Not confirmed**: N's `len` does not scale with P (S(64) < 3.9·S(16)), or a band of (u2) fails for N or C without meeting a Refuted row, or a refusal arrives as another exception class/code, or any other deviation from (u1)–(u6) that no row above names. **Invalid**: a read-back differs from the value set; OFF refuses (the switch did not apply); the mirror fails (u1); thread allocation unsupported.

> **Amendment 2026-10-27 (after run 1, authorised by the user) — B2g, the replica-buffer clause of Refuted (b).** This amendment follows run 1's readings (B2f amendment of this date; written knowing all of run 1's unit readings). **What the old wording let through:** the clause "step 3 under C gives `len` < S(P) of N" was met by C (262,144, 16) (`len` 1,048,786 against 1,048,787, −1 B) and C (1,048,576, 64) (4,195,091 against 4,195,098, −7 B), readings that B1 predicts: B1 (b) says the coordinator threshold does **not** bound the replica buffer, and its operational reading (B1 amendment of 2026-10-25) says (b) holds if the buffer "is the same as with no threshold (page-sized, ≥ P·65,536 B)" and is refuted "by a replica buffer that shrinks towards T". A buffer a few bytes shorter than another table's is neither: by the B2f amendment of this date, two tables' pages differ by up to δ(P) = 8·P + 24 B from timestamp encoding alone, whatever the threshold. **Amended wording**, derived from B1's refuting observation: the Refuted (b) replica-buffer clause reads **"or step 3 under C gives `len` < S(P) − δ(P) (shorter than the serializer's per-table variation allows: the coordinator threshold reaches the replica buffer and shrinks it towards T)"**. The other clauses of Refuted (b) (refusal pattern, counted-size bucket) are unchanged. A C `len` > S(P) + δ(P), or an L (4,194,304, 16) `len` outside S(16) ± δ(16), is not what B1 predicts but does not refute it; it falls under the existing "any other deviation from (u1)–(u6)" clause → **Not confirmed**. The Confirmed row reads (u3) and (u4) as amended on this date; Refuted (a), Refuted (line 1101), the other Not confirmed clauses and Invalid are unchanged. Under the amended wording neither run-1 combination above meets Refuted (b); run 1's unit readings would meet the Confirmed row (every other clause held in run 1).

**B2h. Controls.**
- The no-threshold control shows that the operands scale with P.
- Under-threshold combinations show that aborts are caused by T.
- A fresh table per combination rules out leftover data.
- `read_thresholds_enabled=false` with T set must show no abort, confirming the switch.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2h.** The switch-off control is combination OFF with its prediction (u5); N is the positive control for the operands; fresh tables give fresh metrics.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node built from `/local/c509` (`ant jar`), run from `/local/c509` with
  `bin/cassandra -f -R`.
- Data, commitlog, hints and saved_caches go under `/local/c509-data/` on a local disk with ≥ 10 GiB free.
- `conf/jvm11-server.options` / `jvm-server.options`: `-Xms4G -Xmx4G`, G1 (default),
  `-Xlog:gc*,gc+humongous=debug:file=/local/c509-data/gc.log:time,uptime`.
- `cassandra.yaml`:
  - `read_thresholds_enabled: true`
  - `native_transport_max_request_data_in_flight` left at its default
  - `concurrent_reads: 32`
- Client: a Python 3 venv on the same host with `pip install cassandra-driver`.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3a.** This host: one node from `$W/cassandra-run22` on 127.0.0.1 (no `ant` run while it runs), `conf/` copied to `$W/node-vrt/conf` per start with yaml lines replaced (pattern of the closed `max_value_size` autonomous harness), directories `$W/node-vrt/{data,commitlog,hints,saved_caches,cdc_raw}`; logs per start under `$W/logs/coordinator_read_size_fail_threshold-validateReadThresholds/`. `MAX_HEAP_SIZE=4G` (G1, the shipped options), with **`-XX:G1HeapRegionSize=2m`** replacing the shipped 16m in the node's copy of `jvm11-server.options` (B3d-1's humongous reasoning assumes 2 MiB regions; A3 fact 7), and `-Xlog:gc*:file=<start>/gc.log:time,uptimemillis,tags` there (so `cassandra-env.sh` adds no rotating GC log). Held fixed at every start: `num_tokens: 1`, `initial_token: 0`, `read_thresholds_enabled: true`, `concurrent_reads: 32`, `read_request_timeout: 20000ms`, `write_request_timeout: 20000ms` (so a slow 32 MiB page is not a timeout that shortens reads; B3h), `native_transport_max_request_data_in_flight` at its default. Client: the bundled driver `lib/cassandra-driver-internal-only-3.29.0.zip`, protocol 5, `DCAwareRoundRobinPolicy`, `token_metadata_enabled=False`, `schema_metadata_enabled=False`, CL ONE, `FallthroughRetryPolicy`, request timeout 60 s (replaces the pip venv). Instruments added (observation only, loaded on every start): Byteman `vrt.btm` with `Alloc.java` on the boot class path (`read-alloc` per `LocalReadRunnable` on `ks`; `resp-buf len cap` at the exit of `ReadResponse$LocalDataResponse.build` on `ks`, and `resp-buf-abort` at its exception exit; `guard-fail size limit` at the throw of `SelectStatement.maybeFail` on `ks`; `local-abort` with the message of each `LocalReadSizeTooLargeException`); a one-connection JMX sampler (`Sampler.java`, 1 s: heap used, G1 Old Gen used, the four table metrics); `Jmx.java` (copied unchanged from the guided `coordinator_read_size_fail_threshold` harness) for `StorageService` read-backs. Script `harness/<stem>/cluster-run.sh`.

> **Amendment 2026-10-28 (after run 1, authorised by the user) — B3a, this host for the cluster re-run.** This amendment follows run 1's readings (B3f amendment of this date). The re-run uses a fresh clone `$W/cassandra-run74` (tag `cassandra-5.0.9`, `b5f2a54210`, `ant -Dlocal.repository=$W/m2 build-test`, no `ant` while a node runs from it), node directories `$W/node-vrt74/{data,commitlog,hints,saved_caches,cdc_raw}` (Z: `$W/node-vrt74-z`), helper classes in `$W/harness-bin-vrt74`, raw logs under `$W/logs/coordinator_read_size_fail_threshold-validateReadThresholds/` (`cluster-sd2/` shakedown, `cluster-run2/` re-run). The instruments loaded on every start are run 1's plus the observe-only in-flight rules of B3d (6) (`vrt.btm`, helper `InFlight.java` in the boot-class-path jar with `Alloc.java`). Everything else in B3a and its 2026-10-25 amendment is held as in run 1: one node on 127.0.0.1, `MAX_HEAP_SIZE=4G`, G1 with `-XX:G1HeapRegionSize=2m`, own GC log, the yaml lines, the bundled driver and client settings, the sampler and `Jmx.java`.

**B3b. Knobs.** Each arm needs a restart with the yaml set.
- Arm N: no fail thresholds. This is the positive control.
- Arm C: `coordinator_read_size_fail_threshold: 1MiB` only.
- Arm L: `local_read_size_fail_threshold: 1MiB` only.
- Arm L4: `local_read_size_fail_threshold: 4MiB`. Checks that usage moves with T.
- Optional startup check: `coordinator_read_size_warn_threshold: 2MiB` with
  `coordinator_read_size_fail_threshold: 1MiB` must refuse to start (line 1101).
- Page size P ∈ {128, 512} rows in every arm.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3b.** Starts, in order: `load` (arm N's yaml; schema and data, flush, drain), then `N`, `C`, `L`, `L4` on the same data (each a fresh start), then `Z` (the start-up check, run, not optional: `coordinator_read_size_warn_threshold: 2MiB` + `coordinator_read_size_fail_threshold: 1MiB`, on a separate empty directory). Every arm's thresholds are set in the yaml (start-up path through line 1101) and read back through `system_views.settings` and the `StorageService` JMX attributes `ReadThresholdsEnabled`, `CoordinatorLargeReadAbortThreshold`, `LocalReadTooLargeAbortThreshold`. A shakedown `sd` (2 partitions × 256 rows, `local_read_size_fail_threshold: 2MiB` and then `coordinator_read_size_fail_threshold: 2MiB` and no threshold, P = 128, 4 clients, 20 s each) runs before run 1 as a harness check, not a reading.

**B3c. Workload.**
- Keyspace `ks` (SimpleStrategy, RF 1), table `ks.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))`.
- Load 8 partitions × 1024 rows × 64 KiB = 512 MiB, using a driver script with prepared inserts and
  `os.urandom(65536)`. Then run `nodetool flush ks t`.
- Read phase: 16 client threads. Each loops `SELECT * FROM ks.t WHERE pk = ?` (random pk 0-7) with
  `fetch_size = P` and pages through to the end or the error, for 180 s.
- Page bytes: 8 MiB at P=128, 32 MiB at P=512. In-flight heap if uncapped is ≈ 16 × 2 × page
  (response buffer plus result set): ≈ 256 MiB at P=128 and ≈ 1 GiB at P=512. This is well
  inside 4 GiB and clearly above baseline.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3c.** Load: 8 partitions × 1,024 rows × 65,536 `os.urandom` bytes, prepared inserts with 16 concurrent requests, then `nodetool flush ks t` and `nodetool drain` (no commit-log replay at later starts). Read phase: **16 client processes** (one driver session each; 16 threads in one CPython process would be serialized by the interpreter lock while decoding 8–32 MiB pages, so fewer than 16 queries could be in flight), each looping a fresh paged `SELECT * FROM ks.t WHERE pk = ?` (random pk 0–7, `fetch_size` = P) to the end or the first error, for 180 s; per query the client records outcome, rows, pages, error class and message. Arithmetic re-checked against A3 fact 4: a completed page serializes ≈ P·65,560 B into a buffer of capacity up to 2× that (≈ 16 MiB at P = 128, ≈ 32–64 MiB at P = 512), so the filed in-flight estimate is a lower bound; 4 GiB heap, data ≈ 0.55 GB on disk.

> **Runbook fix D1, 2026-10-25 (stage 4, Claude Opus 5.5; after cluster run 1 attempt 1 was stopped; claim, predictions and conclusions unchanged), B3c.** In attempt 1, 3 s into arm N's P = 128 phase the node logged `Unknown exception in client networking … No buffer space available` (macOS ENOBUFS on loopback) and closed two client connections; with one host and no reconnection the two workers then failed every query locally (`NoHostAvailable`, 34,745 times) for the rest of the phase, so the phase did not run 16 concurrent clients as B3c requires. Fix: a worker that gets a client-side error (`ConnectionShutdown`, `NoHostAvailable`, `OperationTimedOut`, `ConnectionException`, `ConnectionBusy`) records it, rebuilds its driver session and goes on; the first request of each worker is jittered by 0–500 ms. The cluster tier restarts from its beginning (load, N, C, L, L4, Z); attempt 1's logs are kept (`cluster-run1.attempt-1`).

**B3d. Observables and instruments.**
- (1) GC log: heap occupancy **after** each young/mixed pause (live in-flight data), and humongous
  region counts before GC. The 32 MiB and 8 MiB buffers are humongous at the 2 MiB region size.
- (2) `jstat -gc <pid> 500` for the whole read phase.
- (3) `nodetool tablestats ks.t`, and JMX table metrics `CoordinatorReadSizeAborts`,
  `LocalReadSizeAborts`, `CoordinatorReadSize` and `LocalReadSize`
  (`bin/nodetool sjk mx -mg -b org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=LocalReadSizeAborts -f Count`).
- (4) Client counts of successes and `ReadFailure` errors.
- Report the median and max of post-GC heap over the steady 60-180 s window, minus the arm's idle
  baseline (60 s of idle measured before reads start).
- Cannot observe: per-query object attribution. It is inferred from humongous counts.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3d.** (1) GC log: per pause, heap after GC (`A->B(C)`, B) and `Humongous regions: a->b` (b, after GC). **Idle baseline:** at the end of the 60 s idle window `jcmd <pid> GC.run` forces a full collection (an idle node makes no young pauses), and its B and b are the arm's baseline. Δ(arm, P) = median B of pauses whose wall time lies in [60 s, 180 s] of the read phase − baseline B; H(arm, P) = median b in that window − baseline b. Gap: B after a young pause also holds old-generation garbage not yet collected, so Δ is an upper bound on live in-flight data. (2) `jstat` cannot attach on this host: replaced by the JMX sampler (record only, no prediction attached). (3) Metrics from the sampler at the start and end of each read phase (counts) and the histograms' `Max`. (4) Client counts. (5) Per query (Byteman): `resp-buf` len/cap (full pages: len ≥ (P − 1)·65,536), `read-alloc` bytes, `guard-fail` size, `local-abort` X. Per-arm statistic: median over the read phase.

> **Amendment 2026-10-28 (after run 1, authorised by the user) — B3d, instrument (6) for the amended aggregate clauses.** This amendment follows run 1's readings (B3f amendment of this date). (1)–(5) are kept and recorded as before; Δ and H from (1) are reported as **observations and decide no row**. **(6) In-flight replica bytes, by event** (observe-only Byteman rules added to `vrt.btm`; helper `InFlight.java`; line formats in its header):
> - a **request** is one `SelectStatement.execute(QueryState, QueryOptions, Dispatcher$RequestTime)` call on `ks` (`SelectStatement.java:280`; reached once per client request from `QueryProcessor.java:276`), from entry to exit or exception exit, on the native-transport request thread; the global count n rises at entry and falls at exit;
> - the request's page command is named at entry of `AbstractReadExecutor.executeAsync` on the request thread (`AbstractReadExecutor.java:178`, field `command` `:68`);
> - the local read runs on a READ-stage thread (B3f amendment item 1), so the buffer is linked to its request by the command object, not the thread: at exit of `ReadResponse$LocalDataResponse.build` (`ReadResponse.java:197-209`) the buffer's `remaining()` and `capacity()` are stashed for the thread, and at exit of `ReadCommand.createResponse` or `createEmptyResponse` (`ReadCommand.java:366-384`), which call it on the same thread inside `LocalReadRunnable.runMayThrow` (`StorageProxy.java:2209-2219`), they are attached to that command; the global held-bytes count **H** grows by the capacity there;
> - at the request's end the buffers of its command are released: the line `inflight-req` prints n and H **just before** its own release (`getAndDecrement`, `getAndAdd`), and cmds, bufs, len, held of the request, `pending` (held records of other requests) and `orphans` (attachments without a built buffer). Since n and H fall only at request ends, the largest n and H over the lines are their exact peaks (no sampling);
> - for each `ks` local read (`LocalReadRunnable.runMayThrow` entry to exit or exception exit, READ-stage thread) the line `inflight-read` prints m (ks local reads in flight, itself included) and **rsum**, the bytes allocated so far by those reads (`ThreadMXBean.getThreadAllocatedBytes`), at its end; rsum only falls when a read ends, so its largest printed value is its peak up to the instants between the per-thread reads.
> Per phase: the lines whose `ms` lies in [t_start − 2 s, returned + 2 s] (as for (5)); statistics max n, max m, max H, max rsum, per request cmds, bufs, len, held, and max pending, max orphans. **Gaps (named):** "held" runs from the buffer's completion to its request's end (reachable at most; garbage left after that is not held); the coordinator's copies of the values in the result set (`ByteBufferUtil.java:444-452`; ≤ T + one row under C by c2, page-sized under N) and Netty's encoding (direct memory) are not counted; rsum is allocation, an upper bound on what an executing read holds, not residency.

> **Runbook fix D2, 2026-10-28 (stage 4, Claude Opus 5.5; found in the cluster re-run's shakedown `cluster-sd2`, before any re-run reading; the clauses and their numbers are unchanged), B3d (6) and B3f amendment item 1.** The shakedown printed max m = 5 with max n = 4 = nc in `sdC` and `sdL` (every other shakedown check held). Re-reading the source: `LocalReadRunnable.runMayThrow` hands its response to the request's callback at `StorageProxy.java:2230` (`handler.response`; failures at `:2236` and in the catch blocks via `handler.onFailure`) and then still runs latency bookkeeping (`:2239-2241`) before it exits, while the request, no longer waiting for it (`ReadCallback.java:227`), may end and its client may start the next request and read. The B3f amendment's bound "at most nc local reads in flight" is derived for a read from its start to the hand-over (a read before hand-over has a request waiting for it); the instrument as written ended the read at the exit of `runMayThrow`, so it counted that tail as well and did not measure the quantity the bound is about. **Fix:** in (6), a local read is in flight from entry of `runMayThrow` to the hand-over: the `inflight-read` line is printed at `AT INVOKE ReadCallback.response` or `AT INVOKE ReadCallback.onFailure` inside `runMayThrow` (exception exit and exit stay as fall-backs, printing only for a read not yet ended); m and rsum are counted over that window. In the B3f amendment item 1, "at most nc local reads on `ks` are in flight" reads "at most nc local reads on `ks` are in flight before their hand-over". The clauses (n4 (i), c4 (i), l4 (i), (iii), L4-3) and every number are unchanged; the bound on rsum is unchanged because a read's allocation up to its hand-over is part of what A3 fact 4 bounds. **Said plainly:** the defect was noticed because of a shakedown value; the fix changes the instrument's window to the one the amendment's derivation describes and changes no bound. The shakedown is repeated with the fixed instrument (`cluster-sd3`) before the re-run.

**B3e. Procedure.**
1. Clone and build as in B3a. Set the yaml for arm N.
2. Start the node and wait for `nodetool status` UN.
3. Create the schema and load the data. Run `nodetool flush`.
4. Restart, so the arm's yaml is in effect and the heap is fresh.
5. Record 60 s idle.
6. Run the read phase with P=128, wait 60 s, then run it with P=512.
7. Collect gc.log, jstat output and metrics.
8. `nodetool stopdaemon`.
9. Repeat steps 4-8 for arms C, L and L4. The data is reused.
10. Run the optional startup check and confirm the `ConfigurationException` text
    `coordinator_read_size_fail_threshold (1MiB) must be greater than or equal to ...` in
    `system.log`.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3e.** As filed, with: wait for `UN` **and** `statusbinary` `running` (fail at once if the process dies); settings read-back right after each start; between the two read phases 60 s idle (no new baseline); after each arm `nodetool drain`, stop, and check no daemon is left. `Z` waits ≤ 120 s for the process to exit. Run 1 stops at the first step that fails (a node that does not start, a read-back that differs) and records it.

> **Amendment 2026-10-28 (after run 1, authorised by the user) — B3e, order and commands of the cluster re-run.** This amendment follows run 1's readings (B3f amendment of this date). The procedure of B3e and its 2026-10-25 amendment is unchanged (load, then N, C, L, L4 each a fresh start on the same data with 60 s idle, forced full GC, P = 128 then 60 s idle then P = 512, drain and stop; then Z). Before it: Byteman `TestScript` on `vrt.btm` (no errors), then the shakedown `sd` of B3b (2 partitions × 256 rows; `sdN`, `sdL` with `local_read_size_fail_threshold: 2MiB`, `sdC` with `coordinator_read_size_fail_threshold: 2MiB`; P = 128, 4 clients, 20 s, idle 10 s) as a harness check, not a reading, and the self-check run end to end on it. Commands (repository harness folder `harness/<stem>/`): `C=$W/cassandra-run74 VRT_NODE=$W/node-vrt74 VRT_HB=$W/harness-bin-vrt74 cluster-run.sh sd2 sd`, then the same with `cluster-run.sh run2 run1` (plan `run1` = the whole tier), each in the background under `caffeinate -ims`.

**B3f. Predictions.** Δ = post-GC heap median above idle.
- Arm N: Δ(P=512) ≥ 3 × Δ(P=128). Δ(P=512) ≥ 400 MiB. Humongous regions in use regularly ≥ 64.
  No aborts.
- Arm C: every query aborts (`CoordinatorReadSizeAborts` grows). Δ stays ≥ 40% of arm N's Δ at
  the same P, and still grows with P (Δ(P=512) ≥ 2 × Δ(P=128)), because the replica buffer is
  still page-sized. This is the core prediction of claim (b).
- Arm L: every query aborts (`LocalReadSizeAborts` grows). Δ ≤ 64 MiB at both P values, and does
  not grow with P. Humongous regions ≈ 0.
- Arm L4: Δ ≤ 128 MiB and ≥ arm L's Δ.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3f (derived per-query forms added; the filed aggregate relations are kept except where the source contradicts them).** s, m, k, bucket() as in the A3 amendment; T = 1,048,576 for C and L, 4,194,304 for L4; h from the unit mirror.
> - **Validity (V):** each arm's read-backs equal its yaml (switch `true`; the one threshold set, others null); the Byteman agent and sampler ran; each read phase completed ≥ 50 queries.
> - **N** (positive control): (n1) no aborts (both meters unchanged, no client `ReadFailure`); (n2) full-page `resp-buf` len median ∈ [P·65,536, P·65,600 + 512] and cap ∈ [len, 2·len + 65,664], so len(512)/len(128) ∈ [3.9, 4.1]; (n3) `read-alloc` median ≥ 2·P·65,536 (16 MiB at 128, 64 MiB at 512); (n4, filed) Δ(512) ≥ 3·Δ(128), Δ(512) ≥ 400 MiB, H(512) ≥ 64 regions.
> - **C**: (c1) every query refused: no client success, every error a `ReadFailure` with code 4 (read size), `CoordinatorReadSizeAborts` increase = number of refused queries ± 16, `LocalReadSizeAborts` unchanged; (c2) every `guard-fail` line has size = 16·s = 1,048,704 and limit 1,048,576 (refused at the start of row 17), `CoordinatorReadSize` max = bucket(1,048,704) = 1,131,752; (c3) full-page `resp-buf` len median within ±1 % of N's at the same P and in N's band, `read-alloc` median ≥ 2·P·65,536 (the replica buffer is page-sized, as with no threshold); (c4, filed) Δ_C ≥ 0.4·Δ_N at the same P, Δ_C(512) ≥ 2·Δ_C(128).
> - **L**: (l1) every query refused: no client success, every error a `ReadFailure` code 4, `LocalReadSizeAborts` increase = refused ± 16, `CoordinatorReadSizeAborts` unchanged; (l2) every `local-abort` X = b0 + 16·h ∈ [T, T + h); `LocalReadSize` max = bucket(X) = 1,131,752; (l3) no full-page `resp-buf` line (every build of a `ks` page ends at the exception exit), `read-alloc` median < 5·T + 1 MiB = 6 MiB at both P, and median(512)/median(128) ∈ [0.8, 1.25] (the same 16 rows are read whatever P); (l4, filed, the humongous clause corrected) Δ_L ≤ 64 MiB at both P and Δ_L(512) ≤ Δ_L(128) + 32 MiB; H_L ≤ 16 regions (at most one buffer of capacity ≥ 1 MiB per in-flight query, ≤ 16 in flight; the filed "≈ 0" is contradicted by fact 4 at 2 MiB regions).
> - **L4**: (L4-1) as (l1) and (l2) with k = 64, X ∈ [4,194,304, 4,194,304 + h), `LocalReadSize` max = 4,866,323; (L4-2) no full-page `resp-buf` line, `read-alloc` median < 5·T + 1 MiB = 21 MiB at both P and greater than L's median at the same P (64 rows and a ≥ 4 MiB buffer against 16 rows and ≤ 2.1 MiB: usage follows T); (L4-3, filed) Δ_L4 ≤ 128 MiB and Δ_L4 ≥ Δ_L at each P.
> - **Z**: exit without `Startup complete` within 120 s, output containing `coordinator_read_size_fail_threshold (1MiB) must be greater than or equal to coordinator_read_size_warn_threshold (2MiB)`.

> **Amendment 2026-10-28 (after run 1, authorised by the user) — B3f, the aggregate clauses n4, c4, l4 and L4-3 (and V).** This amendment follows run 1's readings. In cluster run 1 every per-query clause held and the filed aggregate clauses n4, l4 and L4-3 failed (results §4.2, §5): they bound the median post-GC heap above idle (Δ) and humongous regions after GC (H), and under a flood of refused queries Δ measures GC promotion (under L, an old generation of 1.8–2.2 GiB full of promoted garbage), which depends on client concurrency and GC dynamics, not on the code path. The user (Yang, the advisor) authorised on 2026-10-28 that the aggregate clauses be restated from what the source determines and the whole cluster tier be re-run. **c4 held in run 1** but bounds the same quantity (Δ_C against Δ_N); it is restated with the others because its reference Δ_N is the measure withdrawn here, and leaving it would keep the aggregate part of (b) resting on GC dynamics. This is a change to a clause that passed, made openly.
> **What was known when writing it.** Everything in run 1's results (§4–§5) and section D: the per-query readings (N full-page len medians 8,390,420 / 33,561,508 B and cap 8,392,704 / 33,570,304 B; C len 8,390,292 / 33,561,620 B; `read-alloc` medians N 25.2 / 101.1 MB, C the same, L 3.11 MB, L4 12.6 MB at both P; query counts, e.g. C 112,121 and 32,241, L 633,654 and 641,595), the Δ and H values (N 202 / 217 MiB, C 284 / 695.5, L 1,802 / 2,195, L4 219 / 219; H 7–248 regions), the GC-promotion reading, and the unit re-run. While designing (V) I also read run 1's per-start digest (`digest-v2.txt`) for the counts of `resp-buf` lines (N 25,560 / 4,371 = client pages; C, L, L4 = client queries), which agree with one replica build per page as the source says. No number below is taken from a reading: the concurrency is B3c's 16 client processes, the per-request bands are A3 fact 4 and n2 (frozen 2026-10-25, before any reading), and the empty-response capacity is the source's 128 B.
> **What the source determines about the aggregate.** The in-flight replica heap of the node is the sum, over the `ks` requests in flight, of what each holds; the source fixes both factors.
> 1. *Concurrency, fixed by the client.* Each of the nc = 16 client processes (B3c) has one session and one request outstanding at a time: `Session.execute` returns `execute_async(…).result()` (`cassandra/cluster.py:2677` in `lib/cassandra-driver-internal-only-3.29.0.zip`), `ResultSet.fetch_next_page` waits for its page (`:5224-5225`), and the default profile does not speculate (`:383, 438`). Each client request is one `SelectStatement.execute` (`QueryProcessor.java:276`, `SelectStatement.java:280`) that reads one page (`:541-544`) of one partition: one `SinglePartitionReadCommand`, one read executor (`StorageProxy.java:2105-2133`), which with RF 1 never speculates (`AbstractReadExecutor.java:207-212`) and makes exactly one local read with its own command (`:116-119, 162-166`), which builds exactly one response (`StorageProxy.java:2209-2219`). So at most nc requests and at most nc local reads on `ks` are in flight, unless a client request is abandoned while the node still serves it (client timeout 60 s, B3a). `Stage.READ.maybeExecuteImmediately` runs the read inline only when `takeWorkPermit(false)` succeeds, which needs a queued task (`SEPExecutor.java:188-203, 218-224`); otherwise the read runs on a READ-stage thread — hence instrument (6) links buffer and request by the command object.
> 2. *Bytes held per request.* A completed response buffer stays reachable from its request until `SelectStatement.execute` returns (it is stored by the read callback and read lazily in `processResults`; the result set holds copies of the values, `ByteBufferUtil.java:444-452`, not slices). **N, a full page:** one buffer with len ∈ [P·65,536, P·65,600 + 512] (n2) and capacity cap ∈ [len, 2·len + 65,664] (A3 fact 4), so cap ≤ capmax(P) = 2·(P·65,600 + 512) + 65,664 = **16,860,288 B** at P = 128 and **67,241,088 B** at P = 512. **C:** the same, because the replica serializes the whole page before the coordinator counts a row (A3 fact 4; c3). **L, L4:** the replica refuses during serialization (l3), and because the command tracks warnings (`SelectStatement.java:333-334`) it answers with `createEmptyResponse()` (`StorageProxy.java:2213-2219`, `ReadCommand.java:377-384`), whose build writes two booleans (`UnfilteredPartitionIterators.java:333, 342`) into a fresh 128-byte heap buffer (`DataOutputBuffer.java:57, 94-97`; `BufferedDataOutputStreamPlus.java:70-78`): **len = 2, cap = 128 exactly**. A refused local read allocates < 5·T + 1 MiB (A3 fact 4), so the bytes allocated so far by the ks local reads in flight are < (their number) × (5·T + 1 MiB).
> **Amended clauses** (nc = 16; the shakedown uses nc = 4, T = 2 MiB, P = 128). n, m, H, rsum, cmds, bufs, len, held, pending, orphans as in B3d (6):
> - **V (added; if it fails the instrument did not see what it must → Invalid):** in every read phase the `inflight-req` lines number the server requests — client pages (N) or client queries (C, L, L4), ± 16 —; every line has cmds = 1, bufs = 1 and orphans = 0; max pending ≤ nc.
> - **n4 (replaces the filed Δ/H clause)**, at each P: (i) max n ≤ nc and max m ≤ nc; (ii) every request whose buffer is a full page (len ≥ (P − 1)·65,536) has P·65,536 ≤ len ≤ held ≤ 2·len + 65,664 ≤ capmax(P); (iii) max H ≤ nc·capmax(P) = **269,764,608 B** (P = 128) and **1,075,857,408 B** (P = 512); (iv) max H ≥ P·65,536 (8,388,608 B; 33,554,432 B).
> - **c4 (replaces)**, at each P: (i) as n4 (i); (ii) **every** request (each refused at its first page) holds one full-page buffer: len ∈ [P·65,536, P·65,600 + 512] and len ≤ held ≤ 2·len + 65,664 — at least 8·T at P = 128 and 32·T at P = 512, whatever T; (iii) and (iv) as n4.
> - **l4 (replaces)**, at each P: (i) as n4 (i); (ii) every request holds one buffer with len = 2 and held = 128, so max H ≤ nc·128 = **2,048 B**; (iii) max rsum < nc·(5·T + 1 MiB) = **100,663,296 B** (96 MiB) at both P — a ceiling set by T, not by P.
> - **L4-3 (replaces)**: as l4 with T = 4 MiB: max rsum < **352,321,536 B** (336 MiB). The filed "Δ_L4 ≥ Δ_L" is not restated as an ordering of aggregates: how many reads overlap at an instant is set by client and GC timing, which the source does not fix. The source fixes the ceiling, which moves with T (96 → 336 MiB) and not with P; usage following T stays shown per query by L4-2 (unchanged).
> - **Observations, no verdict weight:** Δ and H of B3d (1) are still computed and reported for every arm and P, and run 1's finding stands that under refused-query floods they measure GC promotion; so is run 1's observation that the `DatabaseDescriptor`/JMX setters accept fail < warn (u6).
> **Would run 1 pass?** Run 1's raw files have no `inflight-req` or `inflight-read` lines, so V and the amended n4, c4, l4, L4-3 **cannot be evaluated** from them (known-answer pass: not evaluable → not Confirmed). Given run 1's per-query readings, the ceilings (iii) of n4/c4 and l4/L4-3 would be met **if** at most 16 requests and reads overlapped, because they are concurrency × per-query bounds that run 1's per-query values satisfied; the parts run 1 never measured, and that the re-run can newly fail, are the concurrency itself (n, m ≤ 16 on the node), one held buffer per request with none outliving it (V), the band for every request rather than the median, the exact 128-byte empty response under L/L4, and the peaks.
> Unchanged: B1, (n1)–(n3), (c1)–(c3), (l1)–(l3), (L4-1), (L4-2), Z, the other validity clauses (read-backs, agent, ≥ 50 queries), and the unit tier (B2).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| N grows with P; C still grows with P with Δ ≥ 40% of N; L flat and small | Claim confirmed: the local cap bounds heap, the coordinator cap does not bound the replica buffer |
| C flat and small like L | Claim (b) refuted: the coordinator cap bounds node heap |
| L grows with P like N | Claim (a) refuted |
| N does not grow with P, or Δ(N) < 100 MiB | Positive control failed. Workload too small. Not confirmed |
| No aborts in C/L | Thresholds not active (check `read_thresholds_enabled`). Not confirmed |
| Optional startup check: node starts | The line-1101 check is not as traced |

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3g (rows made exact and covering each outcome per threshold; the filed rows keep their meaning).**
> | Observation | Meaning |
> |---|---|
> | V; n1–n4; c1–c4; l1–l4; L4-1–L4-3; Z refuses | **Confirmed** (filed row 1): the local cap bounds the replica's per-query heap and follows T; the coordinator cap bounds the counted result set (≤ T + one row) but not the replica buffer, and node heap still follows P under it. Effect: `caps only on some paths (bypass)` (local: caps; coordinator: caps the result set only) |
> | C: c1–c2 hold, but full-page `resp-buf` len under C ≪ N's (towards T), or Δ_C flat and small like L **with** c3 failing | **Refuted (b)** (filed row 2): the coordinator cap also bounds the replica buffer / node heap |
> | C: a query completes, a `guard-fail` size ≠ 1,048,704, or `CoordinatorReadSize` max ≠ 1,131,752 with aborts | **Refuted (b)** (mechanism: the counted size is not capped at T + one row) |
> | C: c1–c3 hold but c4 fails (Δ_C < 0.4·Δ_N, or not ≥ 2× with P) | **Not confirmed (b)**: per-query buffer page-sized, aggregate heap does not show it |
> | L or L4: a query completes, or X ∉ [T, T + h), or a full-page `resp-buf` line, or `read-alloc` ≥ 5·T + 1 MiB or grows with P beyond the band | **Refuted (a)** (filed row 3: the counter stops but the replica's buffer/heap still follows P) |
> | L/L4: l1–l3 / L4-1–L4-2 hold but l4 or L4-3 fails | **Not confirmed (a)**: per-query bounded, aggregate heap not shown |
> | L4-2's "greater than L" fails with both bounded | **Not confirmed (a)**: usage does not follow T |
> | N: an abort, n2–n3 fail, Δ_N(512) < 100 MiB or Δ_N(512) ≤ Δ_N(128) (filed row 4); n4's 3× / 400 MiB / 64-region clauses fail with Δ_N(512) ≥ 100 MiB and growing | positive control failed → **Not confirmed** (both claims); n4 clauses only → **Not confirmed** for the aggregate clauses of (b) |
> | No aborts in C or L with read-backs correct (filed row 5) | **Refuted** for that threshold (it does not fire with the switch on) |
> | A read-back differs, the switch reads `false`, a start fails, or a read phase has < 50 queries | **Invalid** |
> | Z starts (filed row 6) | **Refuted (line 1101)**: the start-up check is not as traced |
> | Any other deviation from B3f that no row above names | **Not confirmed** for the claim it bears on |

> **Amendment 2026-10-28 (after run 1, authorised by the user) — B3g, the rows that named the aggregate clauses.** This amendment follows run 1's readings (B3f amendment of this date). Every row is read with V, n4, c4, l4 and L4-3 as amended on this date; Δ and H decide no row.
> - **Confirmed** (row 1): wording and Effect unchanged.
> - **Refuted (b)**, filed row 2: "or Δ_C flat and small like L **with** c3 failing" is replaced by "**or C requests hold buffers below P·65,536 with c3 failing** (the replica bytes held per in-flight C query shrink towards T)".
> - "C: c1–c3 hold but c4 fails → **Not confirmed (b)**": wording unchanged; it now means per query page-sized, but the node's in-flight replica bytes are not shown to be at most nc page-sized buffers (more than nc in flight, a request outside the band, or H above the ceiling).
> - "L/L4: l1–l3 / L4-1–L4-2 hold but l4 or L4-3 fails → **Not confirmed (a)**": wording unchanged, with the amended clauses.
> - N row: the positive-control condition "Δ_N(512) < 100 MiB or Δ_N(512) ≤ Δ_N(128) (filed row 4)" is replaced by "**n4 (ii) or (iv) fails** (N's in-flight requests do not hold page-sized buffers)" → positive control failed → **Not confirmed** (both claims); "n4's 3× / 400 MiB / 64-region clauses fail with Δ_N(512) ≥ 100 MiB and growing" is replaced by "**n4 (i) or (iii) fails only**" → **Not confirmed** for the aggregate clauses of (b).
> - **Invalid** gains: "**V's in-flight clause fails** (the instrument did not see one held buffer per request)".
> - Every other row is unchanged.

**B3h. Controls.**
- Arm N is the positive control (same workload, usage moves with P).
- The idle baseline per arm, a fresh restart per arm, the same data and the same client load rule
  out drift.
- Error counts per arm show that the aborts, not client failure, shorten the reads.
- Arm L4 vs L shows that usage follows T.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3h.** N is the positive control for every arm (same data, client, instruments). c3 compares C's replica buffer with N's at the same P; `LocalReadSizeAborts` unchanged in C and `CoordinatorReadSizeAborts` unchanged in L/L4 show which check refused; the `guard-fail`/`local-abort` lines are the direct evidence that the disallow branch fired. L4 vs L (per-query and Δ) shows usage follows T.

> **Amendment 2026-10-28 (after run 1, authorised by the user) — B3h, controls for the amended aggregate clauses.** This amendment follows run 1's readings (B3f amendment of this date). N stays the positive control: its requests must hold page-sized buffers (n4 (ii), (iv)) with the same instrument that reads C and L. V shows the instrument saw every request and released every buffer (one buffer per request, request counts equal to client pages or queries, no orphan, no pending growth). n, m ≤ nc shows the aggregate's concurrency is the client's. L's exact 128-byte empty response against C's page-sized buffer, with the same workload and instrument, shows that the measure tells a page-sized from an empty buffer.

**B4. Risks and cleanup.**
- ≈ 1 GiB of data plus commitlog, on local disk only.
- Afterwards:
  - `nodetool stopdaemon`
  - `pgrep -f CassandraDaemon` must return nothing
  - `pgrep -f ReadSizeCapUnitTest` must return nothing
  - `rm -rf /local/c509-data /local/c509`, and deactivate and delete the venv
- Nothing is written into the shared clone.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B4.** This host: ≈ 0.55 GB of data plus commit log on the internal APFS SSD (`$W/node-vrt`, ≥ 20 GiB free required); unit tables in the clone's `build/test`. At the end: node stopped, `ps -eo command | grep '[C]assandraDaemon'` empty, ports free, `rm -rf $W/node-vrt`, the copied test removed from the clone and `git -C $W/cassandra-run22 status` clean (test yaml untouched); the repository root holds no `build/` or log folder.

> **Amendment 2026-10-28 (after run 1, authorised by the user) — B4, clean-up for the cluster re-run.** This amendment follows run 1's readings (B3f amendment of this date). At the end: node stopped, `ps -eo command | grep '[C]assandraDaemon'` empty, ports free, `$W/node-vrt74` and `$W/node-vrt74-z` removed, `$W/harness-bin-vrt74` may stay (compiled helpers only), `git -C $W/cassandra-run74 status` clean, no `cassandra.logdir_IS_UNDEFINED/` folder, nothing under `results/<stem>/run1/` or `run1b-unit/` changed.

## C. Sources read

- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (785, 1091-1105, 4850-4936)
- src/java/org/apache/cassandra/config/Config.java (520-535)
- src/java/org/apache/cassandra/config/DataStorageSpec.java (170-190)
- src/java/org/apache/cassandra/cql3/QueryOptions.java (240-300)
- src/java/org/apache/cassandra/cql3/statements/SelectStatement.java (325-340, 1000-1140)
- src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java (55-105)
- src/java/org/apache/cassandra/db/ReadCommand.java (450-460, 655-735)
- src/java/org/apache/cassandra/db/ReadResponse.java (182-205)
- src/java/org/apache/cassandra/db/rows/BufferCell.java (141-159)
- src/java/org/apache/cassandra/db/rows/BTreeRow.java (532-552)
- src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java (370-405)
- src/java/org/apache/cassandra/service/StorageService.java (7274-7350)
- src/java/org/apache/cassandra/metrics/TableMetrics.java (859-864)
- conf/cassandra.yaml (2013-2030)
- test/unit/org/apache/cassandra/config/DatabaseDescriptorTest.java (709-731)
- test/unit/org/apache/cassandra/cql3/CQLTester.java, test/unit/org/apache/cassandra/ServerTestUtils.java, test/unit/org/apache/cassandra/Util.java (helpers)
- test/distributed/org/apache/cassandra/distributed/test/thresholds/CoordinatorReadSizeWarningTest.java
- build.xml (jamm agent, testsome)
- https://issues.apache.org/jira/browse/CASSANDRA-16850

## D. Stage-4 feedback

**2026-10-25 — stage 4 run 1 (Claude Opus 5.5, advisor's machine), results [`results/coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous.md`](../../stage4-runtime-verification/results/coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous.md).** Frozen after 19 audit amendments (sha256 `4f2657bc…d8ab`), then again after runbook fix D1 (`3ed15193…24c7`; `_INDEX-advisor.md` §2). Uncommitted.
- **Unit: Not confirmed — caps only on some paths (bypass).**
  - Coordinator arm: refused exactly where (P − 1)·65,544 > T, with the counted size m·65,544 (histogram bucket). At P × 65,536 = T it did not refuse.
  - Local arm: refused exactly at the row where 72 + k·65,752 ≥ T, with X = 263,080 / 1,052,104 / 4,208,200. This includes P × 65,536 = T. Replica allocation was 0.74 / 3.11 / 12.6 MB, independent of P.
  - The switch-off control and the line-1101 asserts (three pairs, plus setter bypass) held.
  - Not Confirmed because the frozen "replica `len` under C equals N's" failed by −7 to +13 B in 4 of 6 combinations: per-table vint timestamp deltas, `SerializationHeader.java:165-168`. An L table without a coordinator threshold also differed by −2 B. Two negative differences meet the literal *Refuted (b)* text; the self-check rejected that row, because the step-3 call never reads the coordinator threshold and the buffer stayed page-sized.
- **Cluster: Not confirmed (a) and (b) on the aggregate-heap clauses; every per-query clause held.**
  - Coordinator 1 MiB: 144,362/144,362 queries refused at counted size 1,048,704 B, while the replica built 8,390,292 / 33,561,620 B pages, as with no threshold.
  - Local 1 MiB / 4 MiB: 1,885,357 queries refused at X = 1,052,104 / 4,208,200. No page buffer was completed; 3.1 / 12.6 MB were allocated per query at both page sizes.
  - The start-up check refused warn 2 MiB / fail 1 MiB with the line-1101 message.
  - Failed filed clauses. N: Δ = 202 → 217 MiB (filed ≥ 3× and ≥ 400 MiB), humongous +10 (filed ≥ 64). L: Δ = 1,802 / 2,195 MiB (filed ≤ 64 MiB). L4: Δ = 219 MiB (filed ≤ 128 and ≥ L).
  - L's post-GC heap is promoted garbage from about 3,500 refused queries/s, each allocating a ≈ 1 MiB humongous buffer.
- **Runbook defect D1 (fixed, B3c):** macOS ENOBUFS closed two client connections, and the workers did not reconnect. The cluster tier was restarted.
- **For stage 3:**
  - (1) Exact byte equality between tables is not derivable; use a tolerance of 9·P + 64 B.
  - (2) Post-GC heap is not live in-flight data. The aggregate ceilings and floors depend on client concurrency and GC dynamics, not on the code path; the per-query instruments (replica buffer, replica allocation, exact counted size and X) decide the claim.
  - (3) The shipped options use 16 MiB G1 regions.
  - (4) `read_thresholds_enabled` gates only the client path (`QueryOptions.java:276-281`, `SelectStatement.java:334`); a command tracked by hand is checked with the switch off.
  - (5) Line 1101 is reachable only from `applySimpleConfig`; the `DatabaseDescriptor`/JMX setters accept fail < warn.

**2026-10-27 — stage 4 unit re-run "run 1b" (Claude Opus 5.5, advisor's machine), authorised by the user (Yang, the advisor) on 2026-10-27; results §7 of the same results file.** Re-frozen after the two amendments `Amendment 2026-10-27 (after run 1, authorised by the user)` (B2f (u3)/(u4): |`len` − S(P)| ≤ δ(P) = 8·P + 24 B, from one timestamp vint per row and three `EncodingStats` vints per partition, each 1–9 B; B2g: Refuted (b) replica clause `len` < S(P) − δ(P), since the old text was met by C (262,144, 16) −1 B and C (1,048,576, 64) −7 B in run 1) at sha256 `967d12bf…29ed6` (`_INDEX-advisor.md` §2). Written knowing all of run 1's unit readings, which would pass the amended relations. Whole unit tier re-run in a fresh clone `$W/cassandra-run66`, harness unchanged, shakedown first. Uncommitted.
- **Unit: Confirmed — caps only on some paths (bypass).** Every clause of (u1)–(u6) held: coordinator refusals and counted-size buckets exactly as in run 1; the replica `len` under C within −5 … +14 B of N's (δ = 152 / 536 B); local refusals at X = 263,080 / 1,052,104 / 4,208,200 with 0.74 / 3.11 / 12.6 MB allocated, independent of P; switch-off control and line 1101 as traced. Self-check 111 of 111; known-answer pass on run 1's raw file reproduced run 1's 5 unit failures under the old wording.
- The cluster tier stays closed at its run-1 verdict (Not confirmed — caps only on some paths (bypass); per query, node heap not shown).

**2026-10-28 — stage 4 cluster re-run "run 1b-cluster" (Claude Opus 5.5, advisor's machine), authorised by the user (Yang, the advisor) on 2026-10-28; results §7b of the same results file.** Re-frozen after the seven amendments `Amendment 2026-10-28 (after run 1, authorised by the user)` (B3a, B3d, B3e, B3f, B3g, B3h, B4) at sha256 `c7256799…f91a`, and again after runbook fix D2 (found in the shakedown: the in-flight read window ended at the exit of `runMayThrow`, whose latency tail outlives the hand-over, `StorageProxy.java:2230, 2239-2241`; now ends at the hand-over; no clause or number changed) at `0ab0b5ab…6fa1` (`_INDEX-advisor.md` §2). The post-GC-heap clauses n4, l4, L4-3 (failed in run 1) and c4 (held in run 1, same measure) were restated from the source as in-flight replica bytes by event: ≤ 16 requests and reads in flight (16 synchronous clients; one page = one local read = one response), each N/C request holding one page buffer ≤ 2·len + 65,664 B, each L/L4 request the 128-B empty response, peaks ≤ 16 × per-request bound. Written knowing all of run 1's readings; run 1's raw files have no in-flight lines, so the amended clauses are not evaluable on them. Whole cluster tier re-run in a fresh clone `$W/cassandra-run74`, shakedown first (twice). Uncommitted.
- **Cluster: Confirmed — caps only on some paths (bypass).** Per query as in run 1 (C: 155,383 queries refused at counted 1,048,704 B, replica pages 8.39 / 33.56 MB; L/L4: 1,419,849 refused at X = 1,052,104 / 4,208,200, 3.11 / 12.6 MB per read at both P; Z refused). In flight: at most 16 requests and reads; peak replica buffers 75.5 / 201.4 MB (N) and 134.3 / 369.3 MB (C), up to 16 page buffers, against ceilings 269.8 / 1,075.9 MB; L/L4 128 B per request (peak ≤ 1,408 B); peak in-flight read allocation 49.6 / 49.1 MB (L) and 193.9 / 195.8 MB (L4), below 96 / 336 MiB and the same at both P. Self-check 115 of 115.
- Observations kept: post-GC heap again moved with GC dynamics, not the code path (Δ_N 768 / 804 MiB against run 1's 202 / 217; Δ_L 1.6–2.1 GiB; under run 1's relations c4, which held in run 1, now fails); the setters accept fail < warn.
- **For stage 3:** state an aggregate-heap prediction as concurrency × per-query bytes with an instrument that sees in-flight bytes by event; end a local read's in-flight window at its hand-over, not at the exit of `runMayThrow`.
