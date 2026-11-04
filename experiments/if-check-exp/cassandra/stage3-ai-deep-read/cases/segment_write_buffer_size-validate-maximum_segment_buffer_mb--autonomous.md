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

> **Amendment U1 (2026-10-27, stage-4 audit).** The program is `SaiBufferProbe` (harness folder), compiled against `build/classes/main` of a local clone (`~/cassandra-run4`, stock source, `ant build-test`) and run in **one fresh JVM per yaml value** with `-Dcassandra.config=<yaml>` (`sai_options:` / `segment_write_buffer_size: <n>MiB`), calling the real `DatabaseDescriptor.daemonInitialization()` so the real `applySimpleConfig()` (line 1022: `conf.sai_options.validate()`) runs. Reason: `new StorageAttachedIndexOptions()` plus a stand-alone `new NamedMemoryLimiter(n ...)` (the original B2c) would not test the wiring from the setting to the limit that the claim is about; the probe reads the **real** limiter, `V1OnDiskFormat.SEGMENT_BUILD_MEMORY_LIMITER` (static, built from `DatabaseDescriptor.getSAISegmentWriteBufferSpace()` at class load, `V1OnDiskFormat.java:126-128`). The second arm (patched constant 2048) is a fresh copy `~/cassandra-run5` made with `copy-source.sh`, `StorageAttachedIndexOptions.java:29` changed to 2048, built with `ant jar` (the constant is `public static final int`, used only in this file: `grep` over `src/` and `test/`). Known answer: upstream `StorageAttachedIndexOptionsTest` (it exercises `validate()` at the boundary).

**B2b. Knobs.** `segment_write_buffer_size` set on a fresh `StorageAttachedIndexOptions` instance: 1024 MiB (default), 32768 MiB (boundary), 32769 MiB (just over). Set via the public field (`new DataStorageSpec.IntMebibytesBound(n)`). The constant itself cannot be varied; a second arm uses a patched build with `MAXIMUM_SEGMENT_BUFFER_MB = 2048`.

> **Amendment U2 (2026-10-27).** Values (yaml, stock build): no entry (default 1024) · 1 · 64 · 1024 · 4096 · 32768 · 32769 · 0 (the error text says "positive integer" but nothing tests `> 0`; recorded, not a verdict row). Patched build: 1024 · 2048 · 2049 · 32768. Every value is run twice (drift). The value is set through the yaml, not the public field.

**B2c. Workload.** No data. Call `validate()` for each value; then construct `new NamedMemoryLimiter(n * 1024L * 1024L, "t")` and feed `increment()` with 1 MiB steps up to 2 GiB, checking `usageExceedsLimit()`.

> **Amendment U3 (2026-10-27).** For an accepted value the probe reads `V1OnDiskFormat.SEGMENT_BUILD_MEMORY_LIMIT` and `SEGMENT_BUILD_MEMORY_LIMITER.limitBytes()`, then feeds that real limiter 1 MiB `increment()` steps (up to the configured value + 4 MiB, at most 40,000 steps, not 2 GiB: the flip point is the only reading) and records the first step after which `usageExceedsLimit()` is true.

**B2d. Observables and instruments.** Whether `validate()` throws; `limitBytes()`; `usageExceedsLimit()` flip point. Cannot observe real heap here (limiter is only a counter).

**B2e. Procedure.** (1) Build; (2) run the program for each n; (3) repeat with patched constant build; (4) record outcomes.

**B2f. Predictions.** n=1024: no throw. n=32768: no throw (the check is strict `>`). n=32769: throws `ConfigurationException` with `INVALID_BUFFER_SIZE_ERROR`. Patched build (2048): 32768 throws, 2048 passes. The limiter flips at exactly n MiB for every n that passes validation, independent of the constant.

> **Amendment U4 (2026-10-27), detail fixing an imprecision, no change of claim.** `usageExceedsLimit()` is `currentBytesUsed() > limitBytes` (`NamedMemoryLimiter.java:52-55`, strict), so with 1 MiB steps the flip is at **step n + 1** (usage n MiB is not above the limit), not at n. For n = 0 it is step 1. The thrown message for 32769 is exactly `INVALID_BUFFER_SIZE_ERROR`: `Invalid value for segment_write_buffer_size. Value must be a positive integer less than 32768MiB`. n = 0 is accepted (no `> 0` test). The real limiter's `limitBytes()` equals `n x 1048576` for every accepted n. Patched build: 2049 and 32768 throw, 2048 and 1024 pass.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| validate() accepts <= 32768 and rejects 32769; limiter limit equals configured n | Constant is only a startup ceiling; operative limit is the setting (claim confirmed) |
| limiter limit is clamped to 32768 or differs from n | Constant acts on usage (claim refuted) |
| No rejection at 32769 | Check not enforced as read (re-trace) |
| Positive control (see B2h) does not move | Not confirmed |

**B2h. Controls.** Positive control: the patched-constant arm (2048) must change the rejection point from 32769 to 2049, showing the check itself works.

> **Amendment U5 (2026-10-27, B2g rows added).** (a) "32769 is accepted on the stock build, or 32768 rejected" is **Not confirmed** (the traced check is not what the file says; already the file's "No rejection at 32769" row). (b) "The real limiter's limit differs from n for an accepted value" is **Refuted** (the constant acts on usage). (c) "The patched arm's rejection point does not move to 2049" is **Not confirmed** (the control did not move). (d) The unit tier cannot see heap; it reads only the validation outcome and the limiter's limit. Unit-tier verdict wording: B2f holds and (b), (c) do not occur: **Confirmed** (the constant is a startup ceiling; the operative limit is the setting).

### B3. Cluster tier

n/a: the constant (32 GiB) can only matter on a node able to buffer more than 32 GiB of SAI segment data, which exceeds what a shared test machine offers; and at the boundary the claim reduces to the unit-tier startup behaviour. Alternative (below) measures the actual resource at the configured cap instead, to show usage follows the setting, not the constant.

> **Amendment C1 (2026-10-27, stage-4 audit): the alternative below is the cluster tier and is run.** The constant itself cannot be driven to its limit on `pc32` (251 GiB RAM could hold 32 GiB, but a 32 GiB builder is out of scope for a shared node); the declared reason stands for the constant. What the claim says in B1 (usage follows the setting and stays far below 32 GiB) is measurable at 64 MiB, 256 MiB and 1024 MiB, and the setting is the known-binding condition for the positive control (B3h). The tier is B3a-B3h as written, with the amendments C2-C6 below.

**B3a. Environment and build.** One node, JDK 11, local build of the tag, heap 4 GiB, off-heap default; table with one SAI index on a text column.

> **Amendment C2 (2026-10-27, B3a-B3c made exact).** One node, `~/cassandra-run1` unmodified, `MAX_HEAP_SIZE=4G`, data and logs on local `/` under `~/s4b-sai` (never `/proj`). Table `sai.t (pk bigint PRIMARY KEY, v text)`, STCS with autocompaction disabled; `v` holds 400 random hexadecimal characters (200 random bytes, hex-encoded) per row, 3,200,000 rows, so about 1.28 GB of indexed term bytes. The data is loaded once on a seed node (`MAX_HEAP_SIZE=12G`, `memtable_heap_space` and `memtable_offheap_space` 6144 MiB, as the sibling case found necessary), flushed, `nodetool compact` into **one sstable**, drained and copied; every measured run restores that copy, so each run indexes the same single sstable. The replaced "~5 GiB" is not needed: the builder of a single sstable is what the limiter counts, and a sstable's terms of at least 1.28 GB exceed the largest limit (1024 MiB). Settings: 64MiB, 256MiB, 1024MiB (default), each a fresh node start on the restored data; plus a start with 32769MiB (refusal, empty data directory). The index is built by `CREATE INDEX v_idx ON sai.t (v) USING 'sai'` (the initial build, `SSTableIndexWriter`, `V1OnDiskFormat.java:175-181`) and repeated by `nodetool rebuild_index sai t v_idx`; the compaction path uses the same writer (`tracker.opType() != FLUSH`) and is not separately run.

**B3b. Knobs.** `sai_options.segment_write_buffer_size` in cassandra.yaml: 64MiB and 1024MiB (restart between). Also startup with `32769MiB` to see the node refuse to start (check message in `system.log`/stderr).

**B3c. Workload.** Insert ~5 GiB of rows with high-cardinality text values via cassandra-stress or CQL batches, then `nodetool compact` (SSTable-based build path) so the SAI index is rebuilt; also `CREATE INDEX` on a pre-loaded table for the initial build path.

**B3d. Observables and instruments.** JMX/metrics gauges `SegmentBufferSpaceUsedBytes` and `SegmentBufferSpaceLimitBytes` (registered at `V1OnDiskFormat.java:134,137`); process RSS and heap via `jcmd GC.heap_info`, sampled every 1 s; log lines "Flushing index segment ... reachMemoryLimit" (`SSTableIndexWriter.java:249-258`).

> **Amendment C3 (2026-10-27, B3d made exact).** Gauges `org.apache.cassandra.metrics:type=StorageAttachedIndex,name=SegmentBufferSpaceUsedBytes`, `...SegmentBufferSpaceLimitBytes`, `...ColumnIndexBuildsInProgress` (attribute `Value`) and `java.lang:type=Memory` `HeapMemoryUsage` are read by a Java JMX sampler every 500 ms (`Sampler.java`); process RSS from `/proc/<pid>/status` every second; the debug-log lines `Global limit of <limit> and minimum flush size of <min> exceeded. Current builder usage is ... Global Usage is ...` (`SSTableIndexWriter.java:249-258`) are counted per run. `jcmd GC.heap_info` is replaced by the sampler's `HeapMemoryUsage` (it includes garbage, so it is a support reading only).

**B3e. Procedure.** Start node with 64MiB; load; run compact; sample; stop and verify no process left; repeat with 1024MiB; finally start with 32769MiB and capture the startup error; stop.

**B3f. Predictions.** Limit gauge equals the configured value (64 MiB, 1024 MiB), not 32768 MiB. Used-bytes peak tracks the setting (peak near 64 MiB vs. larger), with modest overshoot. At 32769MiB the node fails to start with `Invalid value for segment_write_buffer_size`.

> **Amendment C4 (2026-10-27, B3f made exact).** Limit gauge = 67,108,864 · 268,435,456 · 1,073,741,824 bytes for 64 · 256 · 1024 MiB, never 34,359,738,368 (32768 MiB). Peak used gauge during a build is at least the limit (the limit is reached, because the sstable's terms exceed 1024 MiB) and at most 1.25 x the limit + 16 MiB (soft overshoot: one term at a time is added between the flush checks, `SSTableIndexWriter.java:219-236`), so peak(64) < peak(256) < peak(1024) and peak(1024) is about 16 times peak(64). The memory-limit flush DEBUG line appears at least once per run. Peak sampled heap is a support reading: heap peak at 1024 is at least that at 64. At 32769MiB the node exits at start with the message above.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Limit gauge = setting; peak used scales with setting, far below 32 GiB | Usage follows the setting, not the constant (claim confirmed) |
| Peak used or limit pinned near 32768 MiB regardless of setting | Constant binds (claim refuted) |
| Peak used identical for 64 MiB and 1024 MiB | Limit never reached or workload too small (not confirmed) |
| Positive control: memtable-flush path ignores the setting | Expected; confirms limiter applies only to SSTable builds |
| *(Amendment C5, 2026-10-27)* The limit gauge equals the setting but the peak used gauge never reaches it at 256 or 1024 (the workload is too small), or 64 reaches it but 1024 does not exceed 256 | Not confirmed (limit never reached for that setting; the workload is enlarged and the tier restarted if this is a runbook defect) |
| *(C5)* 32769MiB starts the node, or 1024 / 256 / 64 fails to start | Not confirmed (the traced check is not what the file says) |
| *(C5)* The memtable-flush row above is informational and **not run** here (`n/a: the claim concerns the SSTable-build path; the flush path is outside the limiter by the source, `V1OnDiskFormat.java:170-185`) | not a verdict row |

**B3h. Controls.** Same data and heap for both runs; fresh data directory each run; run `nodetool compact` once per run; positive control is the 64 MiB vs 1024 MiB comparison where the known cap (the setting) is expected to move peak usage.

> **Amendment C6 (2026-10-27).** Cluster-tier verdict wording: 32769 refused, the limit gauge equals each setting, the peak used gauge follows the setting up to the limit (the positive control moves) and stays more than 30 times below 32768 MiB at the largest setting: **Confirmed - does not cap** (the 32768 constant is not what bounds the builders; the setting is the soft cap). The tier says nothing about a node configured above 1024 MiB.

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

**Stage-4 result (2026-10-28, run on `pc32`, repository `6e6cf92`; results `stage4-runtime-verification/results/segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous.md`).**

- **Verdict:** unit **Refuted on one sub-claim** (row b: "the operative limit is the setting" fails above 2047 MiB) with **effect: does not cap**; cluster **Confirmed - does not cap**. Outcome class: **true negative**. No run 2. The estimate stands as filed. Frozen sha256 `1f130fc135b064d2fabd1cd94961cd29bf38ce043d1f27b18683f374c2eee2ca`.
- **Cluster declared `n/a` but with a runnable alternative:** the alternative was run as the tier (Amendments C1-C6). Unit: a probe per yaml value through the real `DatabaseDescriptor.daemonInitialization()` and the real `V1OnDiskFormat.SEGMENT_BUILD_MEMORY_LIMITER` (U1-U5), plus a build with the constant at 2048.
- **Measured.** 32769 is rejected with `INVALID_BUFFER_SIZE_ERROR` (unit, and a node exits at start); 32768 and below pass; on the patched build 2049 is rejected and 2048 passes (control). The real limiter's limit is n MiB in bytes for n = 0, 1, 64, 1024, but **2,147,483,647 B for n = 2048, 4096, 32768**, because `V1OnDiskFormat.java:126` calls `IntMebibytesBound.toBytes()`, an `int` saturated at `Integer.MAX_VALUE` (`DataStorageSpec.java:263-266, 442-446`); the limiter flips at step limit/MiB + 1 (strict `>`). Cluster (one 1.29 GB sstable, 4 GiB heap, `CREATE INDEX` and `rebuild_index`): limit gauge 64 / 256 / 1024 MiB, peak used 64.0 / 256.0 / 1024.0 MiB (+ about 3 kB), 272 / 68 / 16 memory-limit flush lines; an extra 4096 MiB arm gave a limit gauge of 2,147,483,647 and a peak of 2048.0 MiB.
- **Corrections for stage 3.** (1) The effective ceiling of the builders is 2 GiB - 1 B on every build, below the 32768 MiB constant; B1's "follows the configured value" holds only up to 2047 MiB. (2) B2f's "flips at exactly n MiB" is n + 1 steps (strict `>`). (3) `0` is accepted by `validate()` although the message says "positive". (4) Not run: the memtable-flush row (`n/a`) and the compaction path (same writer as the index build).
