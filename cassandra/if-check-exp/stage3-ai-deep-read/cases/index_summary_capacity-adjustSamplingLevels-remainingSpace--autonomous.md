# index_summary_capacity — verification solution  <!-- file: cases/index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryRedistribution.java:258` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code agent (CLI version not exposed to the agent), 2026-10-21 |
| Estimate | `positive`, with qualifications. Each time a redistribution runs, it sets the total off-heap index-summary size to at most `index_summary_capacity` (via the line-258 branch and `distributeRemainingSpace`). The cap is periodic and best-effort, though. Summaries are built at full size between resizes, and the `max_index_interval` floor can keep usage above a small capacity. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- Name: `index_summary_capacity`. This is a configuration entry. The deprecated old name is `index_summary_capacity_in_mb`.
- Declared at `src/java/org/apache/cassandra/config/Config.java:539-540` (`public volatile DataStorageSpec.LongMebibytesBound index_summary_capacity;`, no default value). The yaml documentation is at `conf/cassandra.yaml:932-939` (key present but empty).
- Unit: MiB (`LongMebibytesBound`).
- Default: `null`, which means "auto". In that case `DatabaseDescriptor.java:867-869` sets `indexSummaryCapacityInMiB = max(1, (int)(Runtime.getRuntime().totalMemory() * 0.05 / 1024 / 1024))`. Note that this is 5% of the heap that is *currently committed* (`totalMemory`), not of `-Xmx`, so set `-Xms` equal to `-Xmx` to make it deterministic. A negative value is rejected (`DatabaseDescriptor.java:871-873`).
- Path from config to the check:
  - `DatabaseDescriptor.getIndexSummaryCapacityInMiB()` (`DatabaseDescriptor.java:3886-3888`).
  - `IndexSummaryManager` constructor calls `setMemoryPoolCapacityInMB(...)` (`IndexSummaryManager.java:103,108`), which sets `memoryPoolBytes = MiB*1024*1024` (`:184-187`).
  - `IndexSummaryManager.redistributeSummaries()` builds `new IndexSummaryRedistribution(transactions, nonRedistributingOffHeapSize, memoryPoolBytes)` (`:248-250`).
  - `IndexSummaryRedistribution.redistributeSummaries()` computes `remainingBytes = memoryPoolBytes - nonRedistributingOffHeapSize` (`IndexSummaryRedistribution.java:138`).
  - That value goes to `adjustSamplingLevels(..., remainingBytes)` as `memoryPoolCapacity` (`:145,163`), where `remainingSpace = memoryPoolCapacity` (`:173`). Each sstable's planned summary size is subtracted inside the loop (`:222,233,239,245,251`).
  - The check is at `:258`: `if (remainingSpace > 0)`.
- How to set it:
  - yaml `index_summary_capacity: <n>MiB` (needs a restart).
  - At runtime through JMX: `org.apache.cassandra.db:type=IndexSummaries`, attribute `MemoryPoolCapacityInMB` (`IndexSummaryManagerMBean.java:25-26`). This takes effect at the next redistribution and does not need a restart.
- Related knobs:
  - `index_summary_resize_interval` (`Config.java:543`, default 60m; null disables). Also settable through JMX `ResizeIntervalInMinutes` (-1 disables).
  - Per-table `min_index_interval` (default 128) and `max_index_interval` (default 2048).
  - Only formats with `IndexSummarySupport` take part (BIG). BIG is the default `selected_format` (`Config.java:373`). BTI has no summary.

**A2. What it caps.**
- Resource: off-heap native memory used by the index summaries of BIG sstables. That memory is `Memory.allocate`, then `MemoryUtil.allocate`, then JNA `Native.malloc` (`io/util/Memory.java:60-65,80-88`, `utils/memory/MemoryUtil.java:81-84`). It is plain libc malloc, so the JVM does not account for it (not in heap, not in NMT, not in the direct-buffer pool).
- Compared quantity: the planned sum of `IndexSummary.getOffHeapSize()` (`= offsetCount*4 + entriesLength`, `IndexSummary.java:259-262`) over all sstables after resampling.
- `remainingSpace` at line 258 is `capacity − nonRedistributingOffHeapSize − Σ planned sizes`. A positive value means pool space is left over, and the code spends it on cancelling planned downsamples.
- A side effect on disk: every resample rewrites the sstable's `Summary.db` (`BigTableReader.java:617-620`). The constraint does not budget that disk use.

**A3. Mechanism.**
1. A scheduled task runs every `index_summary_resize_interval` (`IndexSummaryManager.java:141-147`), or the run is triggered through JMX `redistributeSummaries()` (`IndexSummaryManagerMBean.java:41`). The run is skipped if global compaction is paused (`IndexSummaryManager.java:241-242`).
2. All non-compacting sstables are marked into transactions. The summary sizes of sstables that are already compacting count as `nonRedistributingOffHeapSize` (`:208-236`).
3. SSTables are sorted coldest to hottest by 15-minute read rate (`IndexSummaryRedistribution.java:118-136`).
4. Each sstable gets `idealSpace = remainingSpace * readsPerSec/totalReadsPerSec` (`:183`), which becomes `targetNumEntries` (`:188`). The new sampling level is then clamped to `[ceil(128*min/max), 128]` (`IndexSummaryBuilder.java:299-314`).
   - Zero-read edge case: if every sstable has zero reads, `0.0/0.0 = NaN`, and `Math.round(NaN)=0`. Then `idealSpace=0`, `targetNumEntries=1`, and every sstable is a downsample candidate at the floor level.
5. Each sstable is classified as one of the following, and its planned size is subtracted from `remainingSpace` (`:215-254`):
   - force-resample (`:215-223`)
   - force-upsample (`:224-234`)
   - upsample if target ≥ 1.5× current (`:235-240`)
   - downsample if target < 0.75× current (`:241-246`)
   - keep (`:247-254`), which subtracts the *actual* current size
6. **Line 258.** If `remainingSpace > 0`, `distributeRemainingSpace` (`:327-356`) sorts the downsample candidates by bytes saved, ascending. For each candidate, while `extraSpaceRequired = currentSize − newSpaceUsed ≤ remainingSpace`, it cancels the downsample (the sstable keeps its current level) and subtracts that amount. It stops at the first candidate that does not fit (`:348-351`).
   - If `remainingSpace ≤ 0`, nothing is cancelled. Every planned downsample runs.
7. The resampling itself runs downsamples first, then force-resamples, then upsamples (`:267-292`). Each one goes through `cloneWithNewSummarySamplingLevel`:
   - A downsample derives the new summary in memory from the old one.
   - An upsample or force path rebuilds it from `Index.db` (`BigTableReader.java:602-610`).
   - Either way, `Summary.db` is saved. The old reader's `Memory` is freed when its last ref is released.

Bypasses and overshoots:
- **(a) No check at write time.** New sstables are written at full sampling (`BigTableWriter.java:255`: `BASE_SAMPLING_LEVEL`) with no capacity check. Flushes and compactions between resizes can push usage above the capacity without limit until the next run. If the resize interval is null or -1, the capacity is never applied.
- **(b) Floor.** No summary goes below `ceil(128*min_index_interval/max_index_interval)/128` of full size. If the sum of the floors is greater than the capacity, `remainingSpace` goes negative and usage stays above the capacity (line 258 is false).
- **(c) Unreduced sizes.** The keep branch (`:251`) and the force paths subtract sizes they cannot reduce, so `remainingSpace` can go negative.
- **(d) Compacting sstables.** These are counted but not resized.
- **(e) Transient overlap.** During a resample, the old and new summaries both exist until the old reader is released.

**A4. Other consumers.** Other things use the same native (malloc) memory without being governed by this constraint:
- bloom filters (`bloom_filter_fp_chance`)
- compression metadata offsets
- off-heap memtables (`memtable_offheap_space`)
- the chunk cache and buffer pool (`file_cache_size`)
- key/row caches (off-heap row cache)
- Netty buffers
- BTI partition index structures (not summaries)
- JVM direct buffers, metaspace, and thread stacks

On disk, `Summary.db` files are written alongside every BIG sstable and are rewritten on each resample.

**A5. Evidence beyond the source.**
- `conf/cassandra.yaml:932-939` comment: "this is a best-effort process. In extreme conditions Cassandra may need to use more than this amount of memory."
- `test/unit/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryManagerTest.java` (`testRedistributeSummaries`, `:355-490`) asserts sampling levels for pools of N, N/2 and N/4 single-summary sizes. That is evidence the pool steers the levels.
- CASSANDRA-5519 (index summary downsampling / IndexSummaryManager): https://issues.apache.org/jira/browse/CASSANDRA-5519

## B. Verification solution

**B1. Claim under test.** For BIG sstables, once a redistribution has completed, the total off-heap index-summary size is ≤ `index_summary_capacity`, and it rises and falls with the capacity, provided the capacity exceeds the sum of the sstables' floor-level sizes. In particular, the line-258 branch spends exactly the positive leftover `remainingSpace` on keeping whole summaries at full level. When the capacity is below the floor sum, or before a redistribution runs, usage is *not* capped. That is the predicted, documented overshoot.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 11.0.32.1, Ant 1.10.12.
- Get a local copy of the tree (never touch the shared clone): `git clone /proj/misconfiguration-PG0/git-repos/cassandra-src /tmp/isr-c5 && cd /tmp/isr-c5 && git checkout cassandra-5.0.9`. If the shared tree is not a git repository, use `cp -a` instead.
- Build: `ant -Dno-checkstyle=true build-test`.
- New test file (in the local copy only): `test/unit/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryCapacityProbeTest.java`.
- Run with `ant testsome -Dtest.name=org.apache.cassandra.io.sstable.indexsummary.IndexSummaryCapacityProbeTest`.
- This uses `test/conf/cassandra.yaml` (BIG format by default). Keep `Assume.assumeTrue(IndexSummarySupport.isSupportedBy(DatabaseDescriptor.getSelectedSSTableFormat()))` in the test.

> **Amendment 2026-10-21 (stage-4 audit, R1; environment and instrument only, B2f/B2g unchanged).** On the stage-4 node (`pc12`)
> the local copy is a fresh clone `~/cassandra-is2` at `cassandra-5.0.9` (`b5f2a54210`), built with `ant build-test`; `/tmp/isr-c5`
> is not used. The test is `harness/index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous/IndexSummaryCapacityProbeTest.java`,
> copied into the clone. A test JVM's `System.out` goes through the logger and arrives fragmented, so each `PROBE` line is
> formatted once, printed, and appended whole to the file named by `-Dprobe.out` (lesson of the `:341` run, its R1). The flush
> call is `cfs.forceBlockingFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS)` (5.0.9 API). `ant testsome` runs twice: rep1 is
> the reading, rep2 a repeat (row added in R3).

**B2b. Knobs.**
- The pool value `memoryPoolBytes` is passed to `new IndexSummaryRedistribution(txns, 0, memoryPoolBytes)`. This is exactly where `IndexSummaryManager` hands in `index_summary_capacity` (`IndexSummaryManager.java:248-250`), but here it is in bytes, so the steps can be smaller than a MiB.
- Definitions, measured inside the test:
  - `N = 10` sstables.
  - `S` = the full-level `getOffHeapSize()` of one sstable.
  - `F` = its floor-level size. Measure it after a run with pool = 0; it equals `ceil(avgEntry * entriesAtSamplingLevel(minLevel, maxEntries))`.
- Pool values:
  - **P0** = `N*F/2`: below the floor sum, so line 258 should be false.
  - **P1** = `N*F + (S−F)/2`: line 258 true, but no sstable fits.
  - **P2** = `N*F + 3.5*(S−F)`: line 258 true, 3 sstables fit.
  - **P3** = `N*F + 7.5*(S−F)`: 7 fit.
  - **P4** = `N*S + 1024`: all fit.

**B2c. Workload.**
- Schema: keyspace `ISRProbe` (SimpleStrategy RF 1). Table `SchemaLoader.standardCFMD(ks,"T").minIndexInterval(8).maxIndexInterval(256).caching(CachingParams.CACHE_NOTHING)`, defined as in `IndexSummaryManagerTest.java:97-111`.
- Data: call `cfs.disableAutoCompaction()`, then write 10 sstables. Each holds 10,000 partitions with keys `String.format("%08d", p)` (8 bytes) and a 100-byte value, written with `RowUpdateBuilder(...).clustering("column").add("val", value).build().applyUnsafe()`, followed by `cfs.forceFlush(FlushReason.UNIT_TESTS).get()` after each sstable.
- Arithmetic:
  - Full level: 10,000/8 = 1,250 entries per sstable. Each entry is about 4 (offset) + 8 (key) + 8 (position) = 20 B, so S ≈ 25,000 B.
  - minLevel = ceil(128*8/256) = 4. Floor entries = ceil(4*1250/128) = 40, so F ≈ 800 B and N*F ≈ 8,000 B.
  - Each pool value above therefore lands at a distinct, predictable `k`.
- Before every run:
  1. Reset all summaries to full level by running a redistribution with pool = 10*N*S (mirrors `resetSummaries`, `IndexSummaryManagerTest.java:154-167`) and check every sstable is at level 128.
  2. Set every sstable's read meter to `new RestorableMeter(0.0, 0.0)`, so the zero-read path applies (all are downsample candidates) and the result depends only on line 258.

> **Amendment 2026-10-21 (stage-4 audit, R2; runbook fix derivable from source, B2f/B2g unchanged).** Step 1's reset cannot work
> with the read meters left at zero by the previous pool value: with zero rates the target is 1 entry (`:183-188`), and an
> upsample needs `targetNumEntries >= 1.5 × current` (`:235`), so a large pool only keeps the downsampled levels. As
> `resetSummaries` does (`IndexSummaryManagerTest.java:154-167`, its first two lines), the reset first sets every read meter to
> `new RestorableMeter(100.0, 100.0)`, then runs the large pool, then asserts level 128; step 2 then zeroes the meters.

**B2d. Observables and instruments.**
- **(1) The operand.** Read `remainingSpace` as it stands at line 258. After `adjustSamplingLevels` returns, the field still holds that value, because `distributeRemainingSpace` gets a copy (`:260`). Read it either with reflection (`Field f = IndexSummaryRedistribution.class.getDeclaredField("remainingSpace"); f.setAccessible(true)`) or as `memoryPoolBytes − redistribution.getCompactionInfo().getCompleted()` (`:360`). Use both and assert they are equal.
- **(2) The usage-side quantity.** `T = Σ getIndexSummary().getOffHeapSize()` over the returned readers.
- **(3) Per-sstable levels.** `getIndexSummary().getSamplingLevel()` for each sstable. Count `k` = the number still at 128.
- Not observable here: actual process memory. That is left to the cluster tier.
- Print one line per pool value: `pool, remainingSpace@258, T, k, levels`.

**B2e. Procedure.**
1. Clone and build as in B2a.
2. Write the test. Use `@BeforeClass` with `DatabaseDescriptor.daemonInitialization(); SchemaLoader.prepareServer(); createKeyspace(...)`, create the sstables, and measure S (with all at level 128).
3. Run once with pool = 0 to measure F, then reset.
4. For each of P0..P4:
   1. Reset and zero the read meters.
   2. Run `try (LifecycleTransaction txn = cfs.getTracker().tryModify(sstables, OperationType.UNKNOWN)) { r = new IndexSummaryRedistribution(ImmutableMap.of(cfs.metadata.id, txn), 0, P); out = IndexSummaryManager.redistributeSummaries(r); }`.
   3. Record the observables and log them.
5. Assert the B2f predictions.
6. Run `ant testsome ...` and collect `build/test/output/TEST-...IndexSummaryCapacityProbeTest.xml` and `build/test/logs`.

**B2f. Predictions.**
- `R(P) = P − N*F'`, where `F'` is the planned floor size, `ceil(avgEntrySize*40)`. Within a few bytes of rounding, F' equals the measured F.

| Pool | remainingSpace@258 | branch | k | T |
|---|---|---|---|---|
| P0 = N·F/2 | ≈ −N·F/2 (< 0) | not taken | 0 | ≈ N·F > P0 (floor overshoot) |
| P1 | ≈ (S−F)/2 > 0 | taken, cancels 0 | 0 | ≈ N·F ≤ P1 |
| P2 | ≈ 3.5(S−F) | taken, cancels 3 | 3 | ≈ N·F + 3(S−F) ≤ P2 |
| P3 | ≈ 7.5(S−F) | taken, cancels 7 | 7 | ≈ N·F + 7(S−F) ≤ P3 |
| P4 | ≈ N(S−F)+1024 | taken, cancels all 10 | 10 | = N·S ≤ P4 |

- In general, `k = min(N, floor(R/(S−F)))` and `T ≤ P` whenever `P ≥ N·F`.
- Allowed tolerance: ±1 in k, but only when sstable sizes differ by a few bytes and R lands within that difference of a boundary.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| T ≤ P for P1–P4, k matches `floor(R/(S−F))`, k increases P1<P2<P3<P4 | Claim confirmed: the check limits planned summary size and steers it to the pool |
| T > P for any P ≥ N·F (beyond ~a few bytes rounding) | Claim refuted: the pool does not cap the planned total |
| k = 0 at P2/P3 although remainingSpace@258 > 0 | Line-258 branch not working as traced (refutes mechanism) |
| P0: remainingSpace < 0, k = 0, T ≈ N·F > P0 | Expected floor overshoot (confirms bypass (b), not a refutation) |
| T identical across all P (summaries unchanged) | Redistribution not acting (check txn, read meters, format = BIG); not confirmed |
| Positive control (P4 vs P1) does not move T by ≈ N(S−F) | Workload did not exercise the mechanism; result not confirmed |

> **Amendment 2026-10-21 (stage-4 audit, R3; makes the operand prediction exact, adds rows and the verdict mapping; the B2f table
> is unchanged).** Definitions, all computed in the test before any pool run: `F'` = the planned floor size of one sstable,
> `ceil((S / entries) × entriesAtSamplingLevel(minLevel, maxEntries))` with `minLevel = ceil(128·8/256) = 4` (`:244`,
> `IndexSummaryBuilder.java:294-314`); `F` = the measured floor size after the pool-0 run (may differ from `F'` by an entry,
> because 1,250 entries is not a multiple of 128). Under zero rates every sstable is planned at `F'`, so the operand is predicted
> **exactly**: `R(P) = P − N·F'` (integer arithmetic, `spaceUsed` is a `long`, `:244-245`); `k = R > 0 ? min(N, floor(R/(S−F'))) : 0`;
> `T = k·S + (N−k)·F`. Rows added:
>
> | Observation | Meaning |
> |---|---|
> | The two operand readers (reflection, `memoryPoolBytes − getCompleted()`) disagree for any P | Instrument invalid; **Invalid** |
> | `R` ≠ `P − N·F'` for some P, or `k`/`T` ≠ the formula above (beyond the ±1 tolerance of B2f) while the sign of R still decides the branch | Operand not as traced; **Not confirmed** |
> | rep2 differs from rep1 in any PROBE value | Not deterministic; **Not confirmed** |
>
> **Verdict mapping (fixed before the run).** **Confirmed** = row 1 holds for P1–P4, row 4 holds for P0 (R < 0, branch not taken,
> T = N·F > P0), the positive control moves, both operand readers agree, R = P − N·F' exactly, and rep2 = rep1. **Refuted** = row 2
> or row 3. **Not confirmed** = row 5, row 6 or an added row above. Effect: `caps` if Confirmed (the unit tier sees the planned
> total only, so the P0 floor overshoot is recorded as the expected bypass (b), not as a different effect); `does not cap` if
> Refuted by row 2; otherwise `undetermined`.

**B2h. Controls.**
- **Positive control.** The same sstables at P4 compared with P1 must differ in T by about N·(S−F) ≈ 242 KB. This shows the instrument and workload can see movement.
- **Ablation of line 258.** At P2, compare the observed k=3 with k=0 at P1. Since every sstable is a downsample candidate (zero reads), any sstable kept at 128 can only have come from `distributeRemainingSpace`.
- **Reset check.** All sstables are at level 128 before each run.
- **Same data.** The same data is used for every P, and autocompaction is disabled so the sstable set is stable (`assertEquals(10, liveReaders.size())`).
- **Clean slate.** `nonRedistributingOffHeapSize = 0` and no concurrent compactions (`CompactionManager.instance.active.getCompactions()` is empty).

### B3. Cluster tier

**B3a. Environment and build.**
- One node on loopback 127.0.0.1. Use the local copy `/tmp/isr-c5` and build it with `ant -Dno-checkstyle=true jar`. This produces `bin/cassandra`, `bin/nodetool` and `tools/bin/cassandra-stress`.
- Data, commit log, hints and saved caches go under `/tmp/isr-node/` on local `/` (about 50 GB free; this run needs at most about 10 GB).
- `conf/cassandra.yaml` edits in the copy:
  - `data_file_directories: [/tmp/isr-node/data]`, `commitlog_directory: /tmp/isr-node/commitlog`, `hints_directory: /tmp/isr-node/hints`, `saved_caches_directory: /tmp/isr-node/saved_caches`
  - `index_summary_resize_interval: null` (disables periodic runs, so redistribution happens only when triggered; see B3e)
  - `index_summary_capacity: <knob>MiB`
  - `commitlog_total_space: 4096MiB`
  - `concurrent_compactors: 2`
- `conf/jvm-server.options` / `jvm11-server.options`: `-Xms8G -Xmx8G`.
- Environment: `export CASSANDRA_LIBJEMALLOC=-` disables jemalloc preload (`bin/cassandra:122-160`). That way glibc malloc returns these large mmap-backed blocks (≫ the mmap threshold) to the OS on free, so RSS reflects freed summaries.
- Leave `LOCAL_JMX=yes` (port 7199, localhost only).

> **Amendment 2026-10-21 (stage-4 audit, R4; environment, no design change).** On `pc12` (no LAN interface; loopback only): the
> tree is `~/cassandra-is2` (built with `ant build-test`, which includes `jar` and stress); the node's `conf/` is a copy under
> `~/stage4-is2/conf` (`CASSANDRA_CONF`), and data, commit log, hints, saved caches, cdc_raw and logs are under `~/stage4-is2/`
> (local `/dev/sda3`), not `/tmp/isr-node`; the stress profile and work files are in `~/stage4-is2/`. Ports are moved off the
> defaults (storage 17000, SSL 17001, native 19042, JMX 17199; every `nodetool` call takes `-p 17199`, stress
> `-port native=19042 jmx=17199`), as in the `:341` run. The heap is set by `MAX_HEAP_SIZE=8G HEAP_NEWSIZE=2G` (gives
> `-Xms8G -Xmx8G`; `-XX:+AlwaysPreTouch` is the shipped default). jemalloc is not installed on `pc12`, so
> `CASSANDRA_LIBJEMALLOC=-` is kept but has no effect; `MALLOC_MMAP_THRESHOLD_=131072` is set so glibc's mmap threshold is fixed
> (every block ≥ 128 KiB is mmapped and returned on free) instead of rising dynamically. `ulimit -n 100000` before the start; the
> node is detected only by a `java` process whose arguments name `CassandraDaemon` and this `conf/` path. `key_cache_size: 0MiB`
> is not set (the key cache is on heap and the workload does not read).

**B3b. Knobs.**
- `index_summary_capacity` ∈ {8 MiB, 64 MiB, 512 MiB, 1024 MiB, 4096 MiB}. Why these values:
  - 8 is below the floor sum (overshoot case).
  - 64 is above the floor sum but below one full summary.
  - 512 and 1024 keep about 5 and about 10 sstables respectively.
  - 4096 is above the total.
- Set the capacity at runtime between runs, without a restart, through JMX: `bin/nodetool sjk mx -b org.apache.cassandra.db:type=IndexSummaries -f MemoryPoolCapacityInMB -ms -v <n>`. Alternatively, edit the yaml and restart. The data and summaries persist, but they reload at whatever level `Summary.db` holds.
- One additional run is the auto default (`index_summary_capacity` empty), which should give `floor(0.05*8192) = 409 MiB`. Verify it from the log line "Initializing index summary manager with a memory pool size of N MB" (`IndexSummaryManager.java:105`).

**B3c. Workload.**
- cassandra-stress user profile `/tmp/isr-work/isr.yaml`:
  ```yaml
  keyspace: isr
  keyspace_definition: CREATE KEYSPACE isr WITH replication = {'class':'SimpleStrategy','replication_factor':1};
  table: t
  table_definition: |
    CREATE TABLE t (pk text PRIMARY KEY, v int)
    WITH min_index_interval = 1 AND max_index_interval = 2048
    AND compaction = {'class':'SizeTieredCompactionStrategy','enabled':'false'};
  columnspec:
    - name: pk
      size: fixed(1000)
      population: seq(1..2000000)
    - name: v
      size: fixed(4)
  insert:
    partitions: fixed(1)
    batchtype: UNLOGGED
  queries:
    read:
      cql: SELECT * FROM t WHERE pk = ?
      fields: samerow
  ```
- Load 20 batches. For `i=0..19`, run `tools/bin/cassandra-stress user profile=/tmp/isr-work/isr.yaml "ops(insert=1)" n=100000 -pop seq=$((i*100000+1))..$(((i+1)*100000)) -rate threads=64 -node 127.0.0.1`, then `bin/nodetool flush isr t`. The result is 20 sstables of 100,000 partitions each.
- The workload is write-only, so all read rates are 0. That makes every sstable a downsample candidate, so the line-258 leftover logic decides the outcome.
- Arithmetic:
  - min_index_interval=1 samples every key. An entry is about 1000 (key) + 8 + 4 = 1012 B.
  - S ≈ 100,000 × 1012 ≈ 101.2 MB ≈ 96.5 MiB per sstable, so the total at full level is about 1930 MiB.
  - Floor level = ceil(128·1/2048) = 1, which gives ceil(100,000/128) = 782 entries, so F ≈ 0.79 MB ≈ 0.75 MiB per sstable. ΣF ≈ 15.1 MiB. S−F ≈ 95.8 MiB.
  - Disk: Data.db ≈ 2.1 GB, Index.db ≈ 2.1 GB, Summary.db ≈ 2.0 GB, commit log ≤ 4 GB. That is under 10 GB in total.
- Duration: about 10–20 min to load, then about 1–3 min per capacity value.

> **Amendment 2026-10-21 (stage-4 audit, R5; runbook fix derivable from source, B3f/B3g unchanged).** Remove the line
> `population: seq(1..2000000)` from `pk`. Stress draws a column's value after `setSeed(seed ^ salt)`, and `DistributionSequence`
> returns `start + next % N` (`tools/stress/.../generate/Generator.java:51-55`, `DistributionSequence.java:41-46, 66-69`), so a
> `seq()` population on the key repeats keys: the `:341` run measured 267,461 distinct keys from 300,000 writes (its runbook fix D1).
> Without it the key's identity is the default `uniform(1..100B)` seeded by the partition seed, and the per-batch
> `-pop seq=a..b` gives each write a distinct seed, hence a distinct 1000-character key (`Strings.generate`, ASCII, so 1000 bytes).
> The stress command adds `no-warmup cl=ONE -port native=19042 jmx=17199 -mode native cql3` (R4). The load lifetime's yaml
> capacity is **64 MiB** (the file left it open): with `index_summary_resize_interval: null` no run happens, so the step-4
> baseline is a direct reading of bypass (a) at a set cap. The capacity for each value of step 5 is then set over JMX.

**B3d. Observables and instruments.**
- **(1) Cassandra's own usage figure.** Run `bin/nodetool sjk mx -b org.apache.cassandra.db:type=IndexSummaries -f MemoryPoolSizeInMB -mg` (sum of `getOffHeapSize`, `IndexSummaryManager.java:193-199`). Cross-check it with the per-table "Index summary off heap memory used" in `bin/nodetool tablestats isr.t`.
- **(2) Actual resource.** Read process RSS with `grep VmRSS /proc/$PID/status`. Sample once per second during each redistribution and take a 30 s median before and after. Heap is fixed (`Xms=Xmx`), so changes in RSS come from native memory.
- **(3) Per-sstable intervals.** `bin/nodetool sjk mx -b org.apache.cassandra.db:type=IndexSummaries -f IndexIntervals -mg`: effective interval 1 means full level, 128 means floor.
- **(4) Logs.** `logs/system.log`, lines "Beginning redistribution ... memory pool size {} MiB; current spaced used is {} MiB", "index summaries: downsample: {}, ...", and "Completed resizing ... current approximate memory used: {} MiB" (`IndexSummaryRedistribution.java:115,154,268`).
- **(5) Disk.** `du -sb /tmp/isr-node/data/isr/t-*/*Summary.db`.
- Not observable directly: malloc-level attribution, because JNA malloc is outside NMT. RSS is therefore an aggregate that also includes other native consumers, and only the *delta* across a redistribution is attributed to summaries.
- Fallback if `sjk mx` misbehaves: a 20-line JMX client (`/tmp/isr-work/Jmx.java`) using `JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi"))` with `getAttribute` / `setAttribute` / `invoke("redistributeSummaries")`. Run it with `java Jmx.java ...` (JDK 11 single-file launch).

> **Amendment 2026-10-21 (stage-4 audit, R6; instruments, no prediction removed).**
> 1. **RSS is `RssAnon`** from `/proc/$PID/status` (VmRSS is logged too). VmRSS = RssAnon + RssFile + RssShmem, and under the
>    default `disk_access_mode: mmap_index_only` (`Config.java:122`) `Index.db` is mapped and read during every upsample, so file
>    pages would move VmRSS by up to the 2 GB of `Index.db`; the malloc'd summaries are anonymous memory. A sampler writes
>    RssAnon every 2 s for the whole lifetime.
> 2. **The operand at line 258** is read by a Byteman rule (`harness/…/r258.btm`) on `IndexSummaryRedistribution.adjustSamplingLevels`
>    `AT LINE 258`, which writes `$this.remainingSpace`, `memoryPoolCapacity` and the time to its own file; the agent is given to the
>    node only (`JVM_EXTRA_OPTS=-javaagent:<clone>/build/lib/jars/byteman-4.0.20.jar=script:<rule>`). This is the cluster-tier
>    counterpart of B2d (1).
> 3. **Per-sstable outcomes**: a TRACE file appender for `org.apache.cassandra.io.sstable.indexsummary.IndexSummaryRedistribution`
>    (additivity on, so `system.log` keeps its INFO lines) records "Using leftover space to keep …" (line 343, inside line 341,
>    inside line 258) and "Re-sampling index summary for …" (`:278`). For each run, `keep(isr)` = the count of keep lines naming
>    `isr/t-`.
> 4. **Per-run log windows**: `system.log`, the TRACE file and the Byteman file accumulate over the lifetime; each run is read from
>    the byte offsets taken just before its trigger.
> 5. **`sjk` syntax** is checked in step 1 against the built `nodetool` (set: `sjk mx -b <bean> -ms -f MemoryPoolCapacityInMB -v <n>`;
>    get: `-mg -f <attr>`; invoke: `-mc -op redistributeSummaries`); the JMX client is the fallback if a form fails.

**B3e. Procedure.**
1. Make the directories: `mkdir -p /tmp/isr-node /tmp/isr-work`. Run `df -h /` and record it.
2. Start the node: `CASSANDRA_LIBJEMALLOC=- bin/cassandra -p /tmp/isr-work/pid`. Wait for `bin/nodetool status` to show UN. Record `PID=$(cat /tmp/isr-work/pid)`.
3. Run the load and flushes (B3c). Check `bin/nodetool tablestats isr.t` shows SSTable count 20 and "Index summary off heap memory used" ≈ 2.0 GB.
4. Baseline: wait 60 s. Record MemoryPoolSizeInMB (≈1930 expected, above every capacity under test except 4096), RSS (median over 30 s) and IndexIntervals.
   - This baseline is itself the reading for bypass (a): usage is above the configured capacity before any redistribution.
5. For each C in 4096, 1024, 512, 64, 8, in that order, plus restoring full level in between:
   1. Set the capacity: `sjk mx ... -f MemoryPoolCapacityInMB -ms -v C`.
   2. Trigger the run: `bin/nodetool sjk mx -b org.apache.cassandra.db:type=IndexSummaries -mc -op redistributeSummaries`.
   3. Wait until the "Completed resizing" log line appears.
   4. Wait 30 s, then record MemoryPoolSizeInMB, RSS median, IndexIntervals, log lines and Summary.db bytes.
   5. Restore to full level by setting capacity 8192 and running `redistributeSummaries` again. This upsamples by rebuilding from Index.db. Record the size, which should be ≈1930 again, before the next C.
6. Auto-default run: stop the node (`bin/nodetool drain; kill $PID`). Empty `index_summary_capacity` in the yaml, start the node, confirm the 409 MiB log line, trigger `redistributeSummaries`, and record as in step 5.
7. Positive control: see B3h.
8. Cleanup: see B4.

> **Amendment 2026-10-21 (stage-4 audit, R7; runbook fix derivable from source, B3f/B3g unchanged).** Step 5.5's restore cannot
> work as written: with zero read rates every target is 1 entry (`:183-188`), an upsample needs `targetNumEntries ≥ 1.5 × current`
> (`:235`), so at capacity 8192 the downsampled sstables only take the keep branch (`:247-254`) and stay at their level. The
> restore is instead a forced upsample, as the `:341` run's step 5 did (its fixes D2): (i) `ALTER TABLE isr.t WITH
> min_index_interval = 1 AND max_index_interval = 1` (an ALTER naming only `max_index_interval` is validated against the default
> min 128 and refused); (ii) capacity 8192 and `redistributeSummaries` — every sstable whose effective interval is above 1 is
> force-upsampled to level 128 (`:224-234`); (iii) `ALTER TABLE isr.t WITH min_index_interval = 1 AND max_index_interval = 2048`
> (restores the table; no run is triggered, the interval is null). Record T after (ii) (≈ 1930) and check every `IndexIntervals`
> entry of `isr` is 1. The same restore runs **before step 6's restart**, so the auto-default lifetime starts from full summaries
> (`Summary.db` holds the level, so a restart alone does not restore). Order of the lifetime after the load: baseline (step 4) →
> 4096 → restore → 1024 → restore → 512 → restore → 64 → restore → 8 → restore → negative control (B3h: capacity 64 over JMX,
> no trigger, 300 s) → stop → auto default (step 6). Before each trigger, the median of RssAnon over the 30 s before it is
> `R_before(C)`; after the "Completed resizing" line, 30 s, then five samples 10 s apart give `R_after(C)`.

**B3f. Predictions.**
- For C ≥ ΣF: post-run total ≈ ΣF + k·(S−F), with k = min(20, floor((C − ΣF − ε)/(S−F))), where ε is the system-table summaries (KB-scale).
- The RSS drop from the 1930 MiB baseline ≈ (1930 − total) MiB, within ±15% (other native consumers, malloc slack).

| C (MiB) | k kept full | MemoryPoolSizeInMB after | ≤ C? | RSS change vs baseline |
|---|---|---|---|---|
| 4096 | 20 | ≈ 1930 | yes | ≈ 0 |
| 1024 | 10 | ≈ 15 + 958 ≈ 973 | yes | ≈ −957 MiB |
| 512 | 5 | ≈ 15 + 479 ≈ 494 | yes | ≈ −1436 MiB |
| auto (409) | 4 | ≈ 15 + 383 ≈ 398 | yes | ≈ −1532 MiB |
| 64 | 0 | ≈ 15 | yes | ≈ −1915 MiB |
| 8 | 0 (remainingSpace < 0 at 258) | ≈ 15 | **no**, ≈ 2× C (floor overshoot) | ≈ −1915 MiB |

- Before any redistribution (step 4), usage ≈ 1930 MiB, which is above every C below 4096 (bypass (a)).
- Summary.db bytes on disk follow the same proportions as MemoryPoolSizeInMB.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| After each run, MemoryPoolSizeInMB ≤ C for all C ≥ 64 and ≈ the predicted k-step values; RSS falls by ≈ the same delta | Claim confirmed: the capacity governs actual native summary memory at redistribution |
| MemoryPoolSizeInMB > C (beyond ~1 MiB) after a completed run for some C ≥ 64 | Claim refuted |
| MemoryPoolSizeInMB drops but RSS does not (within 15%) | Accounting follows the cap but actual memory does not; refutes "actual resource" part (check that jemalloc was really disabled: `grep jemalloc /proc/$PID/maps`) |
| C = 8: ≈ 15 MiB > 8 MiB | Expected floor overshoot (bypass (b)); not a refutation |
| Baseline ≈ 1930 MiB > C before any run | Expected bypass (a); confirms the cap is periodic, not admission-time |
| No change for any C, log shows "downsample: 0" | Redistribution not exercised (reads non-zero? format not BIG? compaction paused?); not confirmed |
| Positive control fails to move usage | Workload/instruments invalid; not confirmed |

> **Amendment 2026-10-21 (stage-4 audit, R8; defines the terms, adds the operand prediction, rows and the verdict mapping; the
> B3f table is unchanged).**
> - **Terms.** `S`, `F` from the step-4 baseline: `S` = isr's `tablestats` "Index summary off heap memory used" / 20; `F'` =
>   `ceil((S/100,000) × 782)` (planned floor, `:244`; 782 = `ceil(100,000/128)`); `ΣF'` = 20·F'. The table's k column is the
>   formula `k = min(20, floor((C·2^20 − ΣF' − ε)/(S − F')))` evaluated with these measured values (the table assumes S ≈ 96.5 MiB).
>   "≈ the predicted value" for T = `MemoryPoolSizeInMB` after the run means within 2 MiB of `ΣF + k·(S − F) + ε` (ε = the system
>   tables' summaries, KB-scale). "≤ C" means T ≤ C + 1 MiB (row 2's margin). "RSS falls by ≈ the same delta" means
>   `|(R_before − R_after) − (T_before − T_after)| ≤ max(0.15 × |T_before − T_after|, 64 MiB)` with RssAnon (R6, R7); at 4096
>   (ΔT ≈ 0) this is the 64 MiB band.
> - **Operand (R6 item 2).** `R258 = C·2^20 − ΣF' − ε` within 2 MiB: **negative at C = 8** (branch not taken, `keep(isr)` = 0),
>   **positive at every C ≥ 64**, with `keep(isr)` = k (0 at 64: branch taken, nothing fits).
> - **Rows added.**
>
>   | Observation | Meaning |
>   |---|---|
>   | R258 ≤ 0 with any keep line, or R258 > 0 at C = 8, or R258 ≥ S − F' with `keep(isr)` = 0 | Line 258 not as traced; **Refuted** (mechanism) |
>   | R258 off the prediction by > 2 MiB, or `keep(isr)` ≠ k, while every T row holds | A missed sub-prediction; recorded, does not change the row |
>   | A restore leaves T < 1900 MiB or any isr interval ≠ 1 | The next value does not start from full; **Not confirmed** for that value |
>   | Negative control: T changes by > 1 MiB or RssAnon by > 64 MiB in 300 s with no run | Usage moves without the mechanism; **Not confirmed** |
>   | SSTable count ≠ 20 at any reading, or a compaction other than index summary redistribution, or no `-big-` Summary.db | **Invalid** run |
>   | The auto-default pool line is not 409 MB | Auto row not tested as planned; recorded, the other rows stand |
>
> - **Verdict mapping (fixed before the run).** **Confirmed** = row 1 for C ∈ {4096, 1024, 512, auto, 64}, the C = 8 overshoot row
>   (T ≈ ΣF > 8), the positive control moving, the negative control flat, R258's sign as predicted at every C, and the restores
>   holding. **Refuted** = row 2, or row 3, or the added mechanism row. **Not confirmed** = rows 6–7 or the added restore /
>   negative-control rows. **Invalid** = the added Invalid row. **Effect:** if Confirmed and the baseline (step 4, cap 64, no
>   run) reads ≈ 1930 MiB > 64 and C = 8 overshoots, `caps only on some paths (bypass)` (caps at each redistribution down to the
>   floor; not at write time; not below the floor); `caps` if Confirmed without either bypass reading; `does not cap` if Refuted
>   by row 2 or 3; otherwise `undetermined`.

**B3h. Controls.**
- **Positive control.** On the same 20 sstables, compare C=4096 with C=64. MemoryPoolSizeInMB must move by about 1900 MiB and RSS by about the same amount. This proves the instruments see summary memory.
- **Negative control.** Restore to full level, then set `ResizeIntervalInMinutes` to -1 and do not trigger a run. Leave C=64 for 5 min. Usage must stay ≈1930 MiB and RSS must stay flat. This shows that changes come from the redistribution and not from other activity (such as compaction, which is disabled, or GC).
- **Format check.** `ls /tmp/isr-node/data/isr/t-*/` must show `*-big-*` / `Summary.db` components.
- **Stable sstable set.** SSTable count stays at 20 throughout (`nodetool tablestats`), and `nodetool compactionstats` shows no compaction other than "Index summary redistribution".
- **Zero reads.** No read traffic is run, and the 15-minute read rate in the log trace stays at 0.

**B4. Risks and cleanup.**
- **Shared tree.** Never build in, or add files to, `/proj/.../cassandra-src`. All work is done in `/tmp/isr-c5`, `/tmp/isr-node` and `/tmp/isr-work` on local `/`.
- **Disk.** The unit tier uses under 1 GB (build plus test data in `build/test`). The cluster tier uses under 10 GB. Check `df -h /` before and after.
- **Memory.** The node uses an 8 GB heap plus about 2 GB of summaries, well within 251 GiB.
- **Processes.**
  - After the cluster tier: `bin/nodetool drain; kill $(cat /tmp/isr-work/pid)`, wait, then confirm with `pgrep -f CassandraDaemon` (should be empty) and `pgrep -f cassandra-stress` (should be empty).
  - After the unit tier: check that no `ant` / `junit` JVMs remain (`pgrep -f JUnitTestRunner`).
- **Cleanup.** `rm -rf /tmp/isr-node /tmp/isr-work`. Optionally also remove `/tmp/isr-c5`.
- **Risk: SJK syntax.** The `nodetool sjk mx` option syntax may differ. Use the JMX client fallback (B3d).
- **Risk: upsampling memory.** Restoring to full level (upsampling) rebuilds from Index.db, which is I/O-bound and takes 1–2 min.
- **Risk: deprecated yaml key.** The deprecated `index_summary_capacity_in_mb` key must not be mixed with the new key.

## C. Sources read

- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/playbook-autonomous.md
- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/_TEMPLATE-autonomous.md
- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/README.md (§6.1 only)
- src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryRedistribution.java
- src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryManager.java
- src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryManagerMBean.java
- src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java
- src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummary.java
- src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java (cloneWithNewSummarySamplingLevel)
- src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java
- src/java/org/apache/cassandra/io/sstable/format/SSTableReader.java (read meter)
- src/java/org/apache/cassandra/io/util/Memory.java
- src/java/org/apache/cassandra/utils/memory/MemoryUtil.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- src/java/org/apache/cassandra/schema/TableParams.java
- src/java/org/apache/cassandra/db/compaction/CompactionInfo.java
- conf/cassandra.yaml
- conf/cassandra-env.sh
- bin/cassandra
- build.xml (testsome target)
- test/unit/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryManagerTest.java
- https://issues.apache.org/jira/browse/CASSANDRA-5519

## D. Stage-4 feedback

**2026-10-21 — run 1, both tiers: unit Confirmed (caps); cluster Confirmed — caps only on some paths (bypass).** Results:
[`../../stage4-runtime-verification/results/index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous.md`](../../stage4-runtime-verification/results/index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous.md)
(harness `harness/index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous/`; not committed). The step-0 audit
(Ready after amendments) added R1–R8 above (audit freeze sha256 `fd6885707e04499847f692c40abd7e537db95b34964aec164fb53c0d1b95c1d1`;
both tiers ran on it). No runbook defect in run 1; self-check 109/109; no run 2.

- **Unit (B2).** S = 25,000 B and F = F' = 800 B exactly as B2c. The operand at line 258, read two ways, equals `P − N·F'` to the
  byte for every pool: −4,000 (P0, branch not taken, T = 8,000 > P0: bypass (b)), +12,100 (P1, branch taken, 0 kept), +84,700 (P2,
  3 kept), +181,500 (P3, 7 kept), +243,024 (P4, 10 kept); T = 8,000 · 8,000 · 80,600 · 177,400 · 250,000, every row of B2f; rep2
  identical. B2g row 1 + row 4 → **Confirmed, caps** (planned total).
- **Cluster (B3).** 20 sstables of exactly 100,000 × 1012 B (S = 96.512 MiB, ΣF' = 15.094 MiB). Baseline at a 64 MiB cap with no run:
  1930.24 MiB (bypass (a)). After each run, `MemoryPoolSizeInMB` = 1930.24 / 972.67 / 493.88 / 398.12 (auto, pool line 409 MB) / 15.09 /
  15.09 MiB at C = 4096 / 1024 / 512 / auto / 64 / 8 — k = 20 / 10 / 5 / 4 / 0 / 0, every value of the B3f table; RssAnon fell by
  −0.5 / 957.6 / 1436.6 / 1528.4 / 1910.9 / 1916.7 MiB against ΔT 0 / 957.6 / 1436.4 / 1532.1 / 1915.1 / 1915.1. The Byteman reading of
  `remainingSpace` at line 258 was C·2^20 − ΣF' − 316 B at every C: **−7,439,403 B at C = 8 (branch not taken, floor overshoot to
  15.09 MiB ≈ 1.9 × C)** and +51,280,868 B at C = 64 (branch taken, nothing fits, TRACE 0 keeps). Positive control 1915.1 MiB; negative
  control (cap 64, 300 s, no run) flat to 0.2 MiB RssAnon and 0 MiB T. B3g row 1 + C = 8 row + baseline row → **Confirmed**, Effect
  `caps only on some paths (bypass)`.
- **What this file adds to the `:341` file** (`index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous`,
  Confirmed — caps only on some paths): the operand of line 258 observed directly at both tiers and predicted to the byte, the "taken,
  nothing fits" case (P1, C = 64) told apart from "not taken" (P0, C = 8), runtime capacity changes over JMX in one lifetime, a second
  geometry (1000-byte text keys, 20 equal sstables, min/max 1/2048). **Overlap:** the same constraint, the same zero-read path through
  `distributeRemainingSpace`, the auto default, the floor overshoot and the between-runs bypass — the `:341` run already established
  each; here they are replicated, not new findings.
- **For stage 3 (not applied):** S1 — the runbook as filed could not restore full summaries under zero read rates (cap 8192 cannot
  upsample, `:235`; fixed by R7, a forced upsample); the same fact means (from source, not run as an arm) **raising `index_summary_capacity` never re-grows summaries of
  sstables that are not read** — usage stays at the lower level until reads arrive or the table's intervals change. S2 — B2c's reset
  "mirrors `resetSummaries`" but omitted its read-meter line (R2). S3 — the `seq()` key population (R5) repeats the `:341` defect D1.
  S4 — B3a's VmRSS would have counted the mmapped `Index.db` pages read by every upsample (R6).
