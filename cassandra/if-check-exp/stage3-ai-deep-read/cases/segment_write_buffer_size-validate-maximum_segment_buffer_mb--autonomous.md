# SAI segment_write_buffer_size upper bound (MAXIMUM_SEGMENT_BUFFER_MB) — verification solution  <!-- file: cases/segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`StorageAttachedIndexOptions.java:41`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java#L41) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code (Agent SDK), 2026-10-27 |
| Estimate | `negative`: the check is a startup sanity ceiling (32768 MiB) on the setting; the operative cap is the configured value (default 1024 MiB), enforced softly, so usage does not follow the hard-coded ceiling. |
| Ground | The ceiling only rejects configs above 32 GiB at startup. Real usage of the SAI segment builders is bounded by the configured value (not by the constant), by flush-when-over-limit (a soft limit that can overshoot), and in practice by node RAM, which is well below the ceiling, so the constant never binds on any realistic node. |

**Type:** non-config (hard-coded constant). The check also reads a yaml entry (`sai_options.segment_write_buffer_size`); the constant rule applies (constant `MAXIMUM_SEGMENT_BUFFER_MB`).

## A. Constraint trace

**A1. The constraint.** `MAXIMUM_SEGMENT_BUFFER_MB`, a hard-coded constant, declared at [`StorageAttachedIndexOptions.java:29`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java#L29) (`public static final int ... = 32768`, MiB; 32 GiB). Not settable (no yaml key, no `-D`, no JMX); a change needs a code edit and rebuild. The other operand, `segment_write_buffer_size`, is a yaml entry (`sai_options.segment_write_buffer_size`, `DataStorageSpec.IntMebibytesBound`, declared line 35, default `DEFAULT_SEGMENT_BUFFER_MB = 1024` at line 26, commented in `conf/cassandra.yaml:1794`; startup-only, needs restart). The `IntMebibytesBound` type itself caps values at `Integer.MAX_VALUE` MiB (`DataStorageSpec.java` ~413). Only the constant is the subject of this case.

**A2. What it caps.** Memory (SAI segment-build buffers during compaction / initial index build). The compared quantity is the configured buffer size in MiB (`segment_write_buffer_size.toMebibytes()`), which is later used as the total limit of the global `NamedMemoryLimiter`. The constant caps the *limit setting*, not measured memory.

**A3. Mechanism.**
1. [`StorageAttachedIndexOptions.java:41`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java#L41) in `validate()` (lines 39-45): if configured MiB > 32768, throws `ConfigurationException(INVALID_BUFFER_SIZE_ERROR)` (line 43), else returns. Note the message says "positive integer" but nothing checks > 0 here.
2. Sole caller: `DatabaseDescriptor.java:1022` (`conf.sai_options.validate()` during `applySimpleConfig`), so it runs once at startup; a throw aborts startup.
3. The value is read via `DatabaseDescriptor.getSAISegmentWriteBufferSpace()` (`DatabaseDescriptor.java:5264-5266`) into `V1OnDiskFormat.SEGMENT_BUILD_MEMORY_LIMIT` (`V1OnDiskFormat.java:126`, bytes) and a static `NamedMemoryLimiter` (`V1OnDiskFormat.java:128`).
4. Use: `SSTableIndexWriter.java:225/235` increments the limiter as terms are added; `shouldFlush` (`SSTableIndexWriter.java:245-248`) flushes a segment when `limiter.usageExceedsLimit()` and the builder has reached `minimumFlushBytes = limit / activeBuilderCount` (`SegmentBuilder.java:149, 213`). The limiter is a tracker only (`NamedMemoryLimiter.java`), so usage can exceed the limit until the next flush check, and only SSTable-based builds (compaction / initial build, `V1OnDiskFormat.java:175-181`) use it; memtable flushes (`MemtableIndexWriter`) do not.
Bypass/overshoot: soft limit overshoots between checks; the memtable-flush path is outside it. No path depends on the 32768 constant after startup.

**A4. Other consumers.** Heap/off-heap used by memtables, memtable SAI indexes, vector graph building, key cache, chunk cache, and the JVM itself; none is limited by this constant.

**A5. Evidence beyond the source.** `conf/cassandra.yaml:1790-1794` (documents the option); `V1OnDiskFormat.java:116-125` comments. No external issues consulted. No test inspected.

## B. Verification solution

**B1. Claim under test.** Actual SAI segment-build memory does not follow the 32768 MiB constant: it follows the configured `segment_write_buffer_size` (and soft-limit behaviour) and never approaches 32 GiB on a realistic node, so the constant is a startup validation only and does not cap memory.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant, local copy of the tag outside the shared tree; `ant jar`; small JUnit/main program on the built classpath (`-Xmx2g`).

**B2b. Knobs.** `segment_write_buffer_size` set on a fresh `StorageAttachedIndexOptions` instance: 1024 MiB (default), 32768 MiB (boundary), 32769 MiB (just over). Set via the public field (`new DataStorageSpec.IntMebibytesBound(n)`). The constant itself cannot be varied; a second arm uses a patched build with `MAXIMUM_SEGMENT_BUFFER_MB = 2048`.

**B2c. Workload.** No data. Call `validate()` for each value; then construct `new NamedMemoryLimiter(n * 1024L * 1024L, "t")` and feed `increment()` with 1 MiB steps up to 2 GiB, checking `usageExceedsLimit()`.

**B2d. Observables and instruments.** Whether `validate()` throws; `limitBytes()`; `usageExceedsLimit()` flip point. Cannot observe real heap here (limiter is only a counter).

**B2e. Procedure.** (1) Build; (2) run the program for each n; (3) repeat with patched constant build; (4) record outcomes.

**B2f. Predictions.** n=1024: no throw. n=32768: no throw (the check is strict `>`). n=32769: throws `ConfigurationException` with `INVALID_BUFFER_SIZE_ERROR`. Patched build (2048): 32768 throws, 2048 passes. The limiter flips at exactly n MiB for every n that passes validation, independent of the constant.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| validate() accepts <= 32768 and rejects 32769; limiter limit equals configured n | Constant is only a startup ceiling; operative limit is the setting (claim confirmed) |
| limiter limit is clamped to 32768 or differs from n | Constant acts on usage (claim refuted) |
| No rejection at 32769 | Check not enforced as read (re-trace) |
| Positive control (see B2h) does not move | Not confirmed |

**B2h. Controls.** Positive control: the patched-constant arm (2048) must change the rejection point from 32769 to 2049, showing the check itself works.

### B3. Cluster tier

n/a: the constant (32 GiB) can only matter on a node able to buffer more than 32 GiB of SAI segment data, which exceeds what a shared test machine offers; and at the boundary the claim reduces to the unit-tier startup behaviour. Alternative (below) measures the actual resource at the configured cap instead, to show usage follows the setting, not the constant.

**B3a. Environment and build.** One node, JDK 11, local build of the tag, heap 4 GiB, off-heap default; table with one SAI index on a text column.

**B3b. Knobs.** `sai_options.segment_write_buffer_size` in cassandra.yaml: 64MiB and 1024MiB (restart between). Also startup with `32769MiB` to see the node refuse to start (check message in `system.log`/stderr).

**B3c. Workload.** Insert ~5 GiB of rows with high-cardinality text values via cassandra-stress or CQL batches, then `nodetool compact` (SSTable-based build path) so the SAI index is rebuilt; also `CREATE INDEX` on a pre-loaded table for the initial build path.

**B3d. Observables and instruments.** JMX/metrics gauges `SegmentBufferSpaceUsedBytes` and `SegmentBufferSpaceLimitBytes` (registered at `V1OnDiskFormat.java:134,137`); process RSS and heap via `jcmd GC.heap_info`, sampled every 1 s; log lines "Flushing index segment ... reachMemoryLimit" (`SSTableIndexWriter.java:249-258`).

**B3e. Procedure.** Start node with 64MiB; load; run compact; sample; stop and verify no process left; repeat with 1024MiB; finally start with 32769MiB and capture the startup error; stop.

**B3f. Predictions.** Limit gauge equals the configured value (64 MiB, 1024 MiB), not 32768 MiB. Used-bytes peak tracks the setting (peak near 64 MiB vs. larger), with modest overshoot. At 32769MiB the node fails to start with `Invalid value for segment_write_buffer_size`.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Limit gauge = setting; peak used scales with setting, far below 32 GiB | Usage follows the setting, not the constant (claim confirmed) |
| Peak used or limit pinned near 32768 MiB regardless of setting | Constant binds (claim refuted) |
| Peak used identical for 64 MiB and 1024 MiB | Limit never reached or workload too small (not confirmed) |
| Positive control: memtable-flush path ignores the setting | Expected; confirms limiter applies only to SSTable builds |

**B3h. Controls.** Same data and heap for both runs; fresh data directory each run; run `nodetool compact` once per run; positive control is the 64 MiB vs 1024 MiB comparison where the known cap (the setting) is expected to move peak usage.

**B4. Risks and cleanup.** Disk: ~10 GiB data dir under a private temp path, deleted afterwards; no shared storage. Stop every Cassandra/stress process (`pgrep -f CassandraDaemon`) and confirm none remains. Do not build in the shared tree.

## C. Sources read

- src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 1015-1025, 5264-5276)
- src/java/org/apache/cassandra/config/DataStorageSpec.java (IntMebibytesBound)
- src/java/org/apache/cassandra/index/sai/disk/v1/V1OnDiskFormat.java
- src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java
- src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.java
- src/java/org/apache/cassandra/index/sai/utils/NamedMemoryLimiter.java
- conf/cassandra.yaml, conf/cassandra_latest.yaml

## D. Stage-4 feedback

`none yet`
