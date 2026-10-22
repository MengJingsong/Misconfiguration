# largestRatio — verification solution  <!-- file: cases/largestRatio-flushLargestMemtable-largestRatio--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java:274` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code (stage-3 autonomous subagent; CLI version not exposed to the session), 2026-10-21 |
| Estimate | `negative`. Line 274, `if (ratio > largestRatio)`, is a running-maximum (argmax) comparison inside `flushLargestMemtable()`. It chooses *which* memtable the cleaner flushes. Its limit-side operand, the local `largestRatio`, starts at the hard-coded `0f` and then holds the best ratio seen so far. It is not a resource budget, and no amount of memory or disk is compared against it as a cap. |
| Ground | Memtable memory is capped elsewhere. The hard cap is `memtable_heap_space` / `memtable_offheap_space`, checked in `MemtablePool.SubPool.tryAllocate` (`MemtablePool.java:156`). The point where flushing starts is `memtable_cleanup_threshold` (`MemtablePool.java:143`). Line 274 only decides which table's memtable is switched once the pool already needs cleaning. Any choice that releases memory keeps usage at or below the pool limit. Even a choice that releases nothing does not let usage grow past the limit: writers block in `SubAllocator.allocate` (`MemtableAllocator.java:186-196`). So the peak memtable footprint should follow `memtable_heap_space` and not the outcome of line 274. The selection affects flush sizes, flush counts and write liveness, not the size of the cap. |

## A. Constraint trace

**A1. The constraint.**
- **Name:** `largestRatio`, a local variable of `AbstractAllocatorMemtable.flushLargestMemtable()`.
- **Kind:** a constant / hard-coded variable. It is initialised to the literal `0f` and then updated in the loop.
- **Declared:** `AbstractAllocatorMemtable.java:251` (`float largestRatio = 0f;`). Updated at `:278` (`largestRatio = ratio;`). Compared at `:274`.
- **Unit:** dimensionless. It is a fraction of the pool limit, because `ratio` is `owns / limit` (`MemtableAllocator.java:290-296`).
- **Default and derivation:** `0f`, hard-coded. It is not derived from configuration.
- **How it can be set:** it cannot be set by yaml, `-D` property or JMX. It can only be changed by editing the source and rebuilding.

The right-hand side of the comparison is normalised by configuration. `ratio = max(ownershipRatioOnHeap, ownershipRatioOffHeap)` (`:273`), where each ratio is `owns / parent.limit` (`MemtableAllocator.java:292`). `parent.limit` comes from these settings:
- `memtable_heap_space`: `Config.java:187`; default heap/4 at `DatabaseDescriptor.java:586-587`; read at `AbstractAllocatorMemtable.java:81`.
- `memtable_offheap_space`: `Config.java:189`; default heap/4 at `DatabaseDescriptor.java:583-584`; read at `:82`.

Both are yaml entries and need a restart: the pool is a `static final` built once at class init (`AbstractAllocatorMemtable.java:59`).

The function only runs as the pool's cleaner (`:84`, `MemtableCleanerThread.java:88`). The cleaner is gated by `memtable_cleanup_threshold`:
- `Config.java:190`.
- Default `1/(1+memtable_flush_writers)` at `DatabaseDescriptor.java:761-763`.
- `memtable_flush_writers` defaults to 2 for one data directory (`DatabaseDescriptor.java:752-755`), so the threshold defaults to 1/3.

These three yaml settings are the constraints that actually bound memory, and a user would tune them. `largestRatio` itself is not one.

**A2. What it caps.** Nothing. The comparison is `ratio > largestRatio`:
- `ratio` is the current table's memtable ownership, including its secondary-index memtables (`:266-271`), as a fraction of the pool limit, whichever of on-heap or off-heap is larger.
- `largestRatio` is the maximum seen so far, starting at 0.

The outcome picks the single active memtable that the cleaner flushes (`:297`, reason `MEMTABLE_LIMIT`). The resource whose release it steers is memtable on-heap or off-heap memory (pool `allocated`). The amount that may be held is bounded by `SubPool.limit`, not by this comparison.

**A3. Mechanism.**
1. **Write path accounting.** Each memtable write calls `SubAllocator.allocate(size, opGroup)` (`MemtableAllocator.java:169-197`). With `heap_buffers`, this happens through `SlabAllocator.allocate` → `onHeap().allocate` (`SlabAllocator.java:89`), and through `markExtraOnHeapUsed` (`AbstractAllocatorMemtable.java:194-197`).
2. **Hard cap.** `SubPool.tryAllocate` (`MemtablePool.java:151-161`) refuses if `allocated + size > limit` (`:156`).
   - If refused and the op group is not blocking, the writer registers on `hasRoom` and waits (`MemtableAllocator.java:186-196`). This is where usage is actually capped.
   - If refused while `opGroup.isBlocking()` (a flush barrier is waiting on this write), the allocation is forced through `allocated(size)` → `adjustAllocated`, which bypasses the limit (`MemtableAllocator.java:179-183`, `MemtablePool.java:163-175`). This is an overshoot path, bounded by the in-flight writes at a barrier.
3. **Cleaning trigger.** After every allocate or acquire, `maybeClean` (`MemtablePool.java:131-135`) checks `used() > nextClean`. Here `nextClean = reclaiming + limit*cleanThreshold` (`:137-147`). If true, it signals the cleaner thread.
4. **Cleaner loop.** `MemtableCleanerThread.Clean.run` (`MemtableCleanerThread.java:71-90`) calls `cleaner.clean()`, which is `flushLargestMemtable` (`AbstractAllocatorMemtable.java:84`). On completion it re-signals only if the result was `true` or an error *and* `pool.needsCleaning()` (`:97-98`).
5. **Target line.** `flushLargestMemtable` (`AbstractAllocatorMemtable.java:249-318`):
   - It iterates `ColumnFamilyStore.activeMemtables()`. That is the *current* memtable of every registered CFS, system keyspaces included (`ColumnFamilyStore.java:1447-1451`). It skips non-allocator memtables (`:260`).
   - It adds index memtables (`:269-271`; `ColumnFamilyStore.java:1454-1458`).
   - At `:274`:
     - **True** (strictly greater than the best so far): that memtable becomes the candidate (`:276-278`).
     - **False:** the earlier candidate stays. Ties go to the first in iteration order, and a ratio of exactly 0 is never chosen.
   - After the loop:
     - If there is a candidate, it logs `Flushing largest ... Used total: on/off, live: on/off, flushing: on/off, this: on/off` (`:293-295`) and calls `signalFlushRequired` → `switchMemtableIfCurrent` (`ColumnFamilyStore.java:1436-1439`). Switching runs `allocator.setDiscarding()` (`AbstractAllocatorMemtable.java:165`), which marks the owned bytes as `reclaiming` and so moves `nextClean` up. The flush ends in `discard()` → `setDiscarded()` → `releaseAll()` (`MemtableAllocator.java:140-155`), which frees pool bytes and signals `hasRoom`.
     - If there is none (every active allocator memtable has ratio 0, for example because all pool bytes belong to memtables already flushing), it returns `false` (`:310-315`). No flush is issued and the cleaner does not re-signal from this result. Memory is still released when the in-progress flushes finish.
6. **Bypasses and overshoot relevant to the cap:**
   - The blocking-op-group overshoot (step 2).
   - Slab region waste: the pool counts requested bytes, while `heap_buffers` allocates 1 MiB regions (`SlabAllocator.java:51, 139`), so the real heap is a little larger than the accounted amount.
   - Allocations larger than `MAX_CLONED_SIZE` (128 KiB) go straight to `ByteBuffer.allocate` but are still accounted (`SlabAllocator.java:89-96`).

   None of these goes through line 274.

**A4. Other consumers.** Other heap users that are not controlled by line 274 (or by the memtable pool):
- the key and row caches (`key_cache_size`, `row_cache_size`), chunk cache / buffer pool (`file_cache_size`, mostly off-heap)
- network buffers and in-flight request payloads
- compaction and flush working memory (partition iterators, writers' buffers)
- the commit log (`commitlog_segment_size`, mmap / direct buffers)
- bloom filters and index summaries (off-heap)
- SAI / secondary indexes that are not allocator memtables
- memtables whose `Memtable` implementation does not extend `AbstractAllocatorMemtable`; these are skipped at `:260`.

All in-tree default memtables do extend it: `SkipListMemtable`, `TrieMemtable`, `ShardedSkipListMemtable`.

**A5. Evidence beyond the source.**
- `conf/cassandra.yaml:792-812`: "Total permitted memory to use for memtables. Cassandra will stop accepting writes when the limit is exceeded until a flush completes, and will trigger a flush based on memtable_cleanup_threshold". `memtable_cleanup_threshold` "defaults to 1 / (memtable_flush_writers + 1)". This places the cap on `memtable_heap_space` and the trigger on the threshold. The comment says nothing about the selection picking anything other than the largest memtable.
- `test/unit/org/apache/cassandra/db/partitions/AtomicBTreePartitionMemtableAccountingTest.java:100, 296`: in-tree precedent for building a pool with `createMemtableAllocatorPoolInternal` and a dummy cleaner.
- No JIRA or git history was relied on. The working tree is not a git checkout.

## B. Verification solution

**B1. Claim under test (negative).**
- With the memtable pool limit `L = memtable_heap_space` held fixed, the peak memtable on-heap footprint stays at or below about `L` and keeps the same `peak/L` ratio, whatever line 274 selects. Changing the selection (skewed vs even multi-table workloads, or a source mutation that changes or disables the selection) does not raise usage above `L`. It only changes flush sizes and counts, or write liveness.
- Positive control: the same workload *does* move the peak when `L` itself changes.

> **Audit amendment R1 (stage 4 step 0, 2026-10-21, before any run).** The "same `peak/L` ratio" part of the claim applies to the *workload-driven* selection under the original code (S-skew vs S-even, W-skew vs W-even, all M-orig). For the source mutants (M-first, M-never) the claim is the ceiling only: peak at or below about `L`. Reason, from the source and not from any reading: M-never issues no `MEMTABLE_LIMIT` flush at all (`:310-315`), so its accounted usage must climb to `L` (as B2f itself predicts), while M-orig peaks near the cleaning point. As filed, B2g's Confirmed row demanded the same `peak/L` (±0.10) for M-orig and M-never, which B2f's own predictions rule out. B2g rows 3–4 are amended to match (below). This amendment governs over the sentence above.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 11.0.32.1, Ant 1.10.12.
- Clone to local disk; never build in the shared tree:
  ```
  git clone /proj/misconfiguration-PG0/git-repos/cassandra-src /tmp/c509-unit
  cd /tmp/c509-unit
  git checkout cassandra-5.0.9 2>/dev/null || true
  rm -f test/unit/org/apache/cassandra/utils/memory/HeapPoolTest.java
  ```
  If the shared tree is not a git repo, use `cp -a` and then delete the untracked `HeapPoolTest.java` from the copy.
- Build: `ant -Dno-checkstyle=true build-test`
- New test source: `/tmp/c509-unit/test/unit/org/apache/cassandra/db/memtable/FlushLargestSelectionTest.java`. It is in the same package, so the package-private `MEMORY_POOL` fields and `flushLargestMemtable()` are accessible (both are `public` anyway). The class `extends CQLTester`.
- JVM options: the defaults from `build.xml` `testsome` (`-ea`, jamm agent, `-Dcassandra.skip_sync=true`). The test heap is whatever `build.xml` sets (≥ 1 GiB). That is enough for `L ≤ 128 MiB`.

**B2b. Knobs.**

| Knob | Values | Why | How set |
|---|---|---|---|
| `memtable_heap_space` (L) | `32MiB`, `128MiB` | Positive control: a 4× change in the real cap | In `/tmp/c509-unit/test/conf/cassandra.yaml`, add a line `memtable_heap_space: 32MiB` before the `memtable:` block. Edit it with `sed -i` between runs. A separate JVM run per value is required because `MEMORY_POOL` is static. |
| `memtable_allocation_type` | `heap_buffers` (test conf default, line 6) | On-heap pool only. The off-heap ratio is 0, so `ratio` = on-heap ratio. | unchanged |
| Selection (line 274 outcome) | S-skew: one hot table. S-even: 4 tables written round-robin. | Forces line 274 to pick very different memtables (one big vs many quarter-size) | workload |
| Source mutant (line 251/274) | **M-orig:** unmodified. **M-first:** replace `:274` condition with `largestMemtable == null && ratio > 0f`, so the first non-empty memtable wins, not the largest. **M-never:** change `:251` to `float largestRatio = Float.MAX_VALUE;`, so `:274` is never true and no memtable is ever selected. | Varies the target check's operand and outcome directly | Edit only in a *second* local clone `/tmp/c509-unit-mut`, rebuild there |

**B2c. Workload.** Table schema: `CREATE TABLE %s (pk int, ck int, v blob, PRIMARY KEY (pk, ck))`, written via `execute("INSERT INTO %s (pk, ck, v) VALUES (?, ?, ?)", ...)` with a 1024-byte random `v`. Accounted ownership per row is about 1.1–1.4 KiB (value plus BTree / row overhead through `markExtraOnHeapUsed`). Disable auto-compaction on the test tables (`disableAutoCompaction()` / `getCurrentColumnFamilyStore().disableAutoCompaction()`).

- **Test U1, selection operand (no cleaner interference):**
  - Create tables T1, T2, T3. Write 1500, 3000 and 4500 rows respectively, about 2 / 4 / 6 MiB. The total of about 12 MiB stays below the cleaning point `L/3`: 10.7 MiB at L=32 is too close, so U1 runs only at **L=128 MiB** (cleaning at 42.7 MiB).
  - Before writing, flush all system and test tables (`StorageService.instance.forceKeyspaceFlush` for `system`, `system_schema`, and the test keyspace, or `Keyspace.all()` → `cfs.forceBlockingFlush(UNIT_TESTS)`) so other memtables are close to zero.
  - Then call `AbstractAllocatorMemtable.flushLargestMemtable().get()` directly.
- **Test U2, zero ratio:** after flushing *every* CFS (`ColumnFamilyStore.all()`), call `flushLargestMemtable().get()` once more.
- **Test U3, cap under selection variants:**
  - 4 writer threads, each inserting 1 KiB rows, 16 MiB × `L/32` of ownership per thread.
  - S-skew: all four threads write T1.
  - S-even: thread i writes Ti.
  - Total written ≈ 2·L, so the pool must reach the cleanup point `L/3` at least 6 times and must flush to continue.
  - Arithmetic: L=32 → 64 MiB written ≈ 50 k rows. L=128 → 256 MiB ≈ 200 k rows.
  - Each insert runs through a `Future` with a 30 s timeout so that M-never cannot hang the JVM.

> **Audit amendment R2 (2026-10-21, before any run).** Exact U3 workload and stop conditions, which the text above leaves open:
> - Both U3 variants create the same four tables T1–T4 (S-skew writes only T1), disable their auto-compaction, and flush every CFS before writing. Row `i` of a thread goes to `pk = (thread × 10⁶ + i) / 100`, `ck = i % 100`, `v` = 1024 random bytes.
> - **Rows per thread = 13,000 × L / 32 MiB** (13,000 at L = 32, 52,000 at L = 128; ≈ 16 MiB × L/32 at ≈ 1.26 KiB per row), so the total is ≈ 2·L of ownership.
> - Each thread inserts through its own single-thread executor and waits up to 30 s per insert. **A thread stops at its first timed-out insert.** "Inserts that timed out" is the number of stopped threads (0–4); the rows each thread completed are recorded too.
> - The sampler window runs from the first insert until every thread has finished or stopped. After the window (M-never only), the test force-flushes T1–T4 to release the blocked writers, so the JVM can end; nothing after the window is a reading.
> - The test also writes its result lines to a file (`-Dprobe.out`), because the test JVM routes `System.out` through a logger (stage-4 harness lesson H1 of `concurrent_writes`).

**B2d. Observables and instruments.**
- U1:
  - for every `cfs` in `ColumnFamilyStore.all()`: `Memtable.getMemoryUsage(cfs.getTracker().getView().getCurrentMemtable())`. Record `ownershipRatioOnHeap` and the index-included sum, which recomputes `ratio` exactly as `:266-273` does.
  - the test's own argmax over those ratios (strict `>`, iteration order of `ColumnFamilyStore.all()`)
  - which CFS's current-memtable identity changed after the call, and its `getLiveSSTables().size()` delta
  - the Future's boolean result
- U2: the Future's boolean result, and that no current memtable identity changed.
- U3:
  - a sampler thread every 5 ms reads `AbstractAllocatorMemtable.MEMORY_POOL.onHeap.used()`, `.getReclaiming()` and `.usedRatio()`. Record `peakUsed` and `peakUsed/L`.
  - flush count per table (`cfs.metric.memtableSwitchCount.getCount()`)
  - `MEMORY_POOL.blockedOnAllocating.getCount()`
  - wall time
  - the number of inserts that timed out

  Print everything as one CSV line per run to stdout (captured in `build/test/output/TEST-*.xml`).
- Not directly observable here:
  - the true JVM heap held by memtables (slab waste, object headers). That is the cluster tier's job.
  - the exact overshoot from the blocking-op-group path. It is bounded by in-flight writes, which here is 4 threads × 1 row.

**B2e. Procedure.**
1. Clone, delete `HeapPoolTest.java`, add `FlushLargestSelectionTest.java` with methods `u1Selection`, `u2ZeroRatio`, `u3CapSkew`, `u3CapEven`.
2. `sed -i '/^memtable:/i memtable_heap_space: 128MiB' test/conf/cassandra.yaml`
3. `ant -Dno-checkstyle=true testsome -Dtest.name=org.apache.cassandra.db.memtable.FlushLargestSelectionTest`
4. Change the value to `32MiB`, keeping the knob line before the `memtable:` block: `sed -i 's/^memtable_heap_space: .*/memtable_heap_space: 32MiB/' test/conf/cassandra.yaml`. Rerun with `-Dtest.methods=u3CapSkew,u3CapEven`.
5. Mutants:
   - `cp -a /tmp/c509-unit /tmp/c509-unit-mut`. Apply M-first to `src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java`, then `ant -Dno-checkstyle=true build-test`.
   - Run `u3CapSkew,u3CapEven` at L=32 and L=128.
   - Revert, apply M-never, rebuild, and run `u3CapSkew` at L=32.
6. Collect CSV lines from `build/test/output/`. Then `rm -rf /tmp/c509-unit /tmp/c509-unit-mut` (after saving outputs elsewhere on local disk).

**B2f. Predictions (stated before any run).**
- **U1 (L=128 MiB, M-orig):**
  - The flushed CFS equals the independently computed argmax, which should be T3 with ratio ≈ 6/128 ≈ 0.045 (±30% for overhead).
  - T1 and T2 keep their current memtables.
  - The Future returns `true`.
- **U2:** the Future returns `false`, and no memtable switches. This is the `ratio > 0f` floor: a ratio of 0 is never selected.
- **U3, M-orig, fixed L:**
  - `peakUsed/L` is in [0.33, 1.0], plus at most 4 rows (≈ 6 KiB) of blocking-path overshoot.
  - |`peak/L`(skew) − `peak/L`(even)| ≤ 0.10.
  - S-even shows more switches in total (about 2–4×) with smaller flushes than S-skew.
- **U3 positive control:** `peakUsed` at L=128 is ≈ 4× (3–5×) `peakUsed` at L=32 for the same selection variant.
- **M-first:**
  - `peakUsed ≤ L` + overshoot, the same bound as M-orig.
  - Switch counts include system or other small tables.
  - `blockedOnAllocating` may be higher, but the cap holds.
- **M-never:**
  - `peakUsed` plateaus at ≤ L + overshoot. It does not grow past L.
  - `blockedOnAllocating` > 0 and inserts time out.
  - The memtable is never switched by `MEMTABLE_LIMIT`.

  That is, disabling line 274's selection costs liveness, not the cap.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| U1 flushed CFS = the test's argmax, and U2 returns `false` | Line 274 behaves as traced: an argmax with a 0 floor, not a limit |
| U1 flushed CFS ≠ argmax | The trace of `:274` is wrong; revisit A3 |
| `peakUsed/L` same (±0.10) for skew/even and for M-orig/M-first/M-never, *and* `peakUsed` scales ≈ 4× from L=32 to L=128 | **Claim confirmed:** usage follows `memtable_heap_space`, not line 274 |
| `peakUsed` exceeds L by more than in-flight overshoot (> L + 1 MiB) under some selection variant, or `peak/L` differs by > 0.10 between selection variants at fixed L | **Claim refuted:** line 274's outcome governs how much memory is held |
| M-never: used grows without bound | **Claim refuted:** the cap depends on the selection |
| Pool never reaches `L/3` (no switches from `MEMTABLE_LIMIT`) | **Not confirmed:** the limit was not reached; enlarge the workload |
| `peakUsed` does not change between L=32 and L=128 | **Not confirmed:** the positive control did not move, so the workload is not exercising the pool |

> **Audit amendment R3 (2026-10-21, before any run).** Rows 3–4 above are read as follows (R1), and three rows are added. This block governs over the table above.
>
> | Observation | Meaning |
> |---|---|
> | *(row 3, amended)* `peakUsed ≤ L + 1 MiB` under every variant (M-orig, M-first, M-never; S-skew, S-even), *and* M-orig `peak/L` the same (±0.10) for S-skew and S-even at each L, *and* M-orig `peakUsed` at L=128 is 3–5× that at L=32 for the same variant | **Claim confirmed:** usage follows `memtable_heap_space`, not line 274 |
> | *(row 4, amended)* `peakUsed > L + 1 MiB` under some variant, or M-orig `peak/L` differs by > 0.10 between S-skew and S-even at the same L | **Claim refuted** |
> | *(added)* U2 returns `true`, or a memtable switches in U2 | The trace of `:274` is wrong (a ratio of 0 was selected); revisit A3 |
> | *(added)* M-never: a test-table memtable switches inside the window, or no insert times out while `peakUsed < L` | **Invalid** arm: another flush path released memory, so the arm did not isolate line 274 |
> | *(added)* every bound holds on the accounted counter, and nothing here can show the real heap | The unit tier speaks only for the pool's accounted bytes (`allocated`); the real-heap gap (B2d) is left to the cluster tier. Recorded with any unit verdict |
>
> **U2 race.** If a system memtable has a ratio > 0 at the moment of the U2 call (a background write between the flush and the call), that attempt is not a reading: the test records the ratios and repeats the flush-all and the call, up to 3 attempts.
>
> **Runbook fix D1 (stage 4 run 1, 2026-10-21; B2f/B2g unchanged).** Three attempts were too few: in the first unit-tier pass every attempt found background writes to `system.compaction_history`, `system.sstable_activity(_v2)` or `system_schema` between the flush and the call, so U2 had no valid attempt. U2 now makes **up to 20 attempts**; each flushes every CFS, waits 1 s, flushes every CFS again, then snapshots and calls. Only an attempt with every ratio 0 at the call is a reading; the first such attempt is the U2 reading. The unit tier restarted from its beginning with this fix (the first pass is kept as attempt 1, not counted).

**B2h. Controls.**
- The independent argmax in U1 rules out the possibility that a different mechanism, rather than `:274`, is choosing the table.
- Flushing system tables first removes their competing ratios.
- Auto-compaction off avoids compaction heap and flush-writer contention.
- `skip_sync` removes commit-log fsync stalls.
- The 4× L change is the positive control for the instrument.
- Each knob value runs in a fresh JVM (static pool).
- Using the same row count per L (scaled) keeps the number of cleaning cycles constant.

### B3. Cluster tier

**B3a. Environment and build.**
- One node on 127.0.0.1. A second node is not needed: the pool is per-JVM.
- Build from a local clone:
  ```
  git clone /proj/misconfiguration-PG0/git-repos/cassandra-src /tmp/c509-node
  cd /tmp/c509-node
  rm -f test/unit/org/apache/cassandra/utils/memory/HeapPoolTest.java
  ant -Dno-checkstyle=true jar
  ```
  The same steps in `/tmp/c509-node-mut` produce the M-never and M-first mutant builds (B2b).
- Data, commitlog, hints and saved caches go under `/tmp/c509-data` on local `/`.
- `conf/jvm-server.options` / `conf/cassandra-env.sh`: `MAX_HEAP_SIZE=4G`, `HEAP_NEWSIZE=800M` (exported in the environment), G1 as shipped in `conf/jvm11-server.options`. Add `-Xlog:gc*:file=/tmp/c509-data/gc.log:time,uptime`.
- `conf/cassandra.yaml` changes:
  ```
  data_file_directories: [/tmp/c509-data/data]
  commitlog_directory: /tmp/c509-data/commitlog
  hints_directory: /tmp/c509-data/hints
  saved_caches_directory: /tmp/c509-data/saved_caches
  memtable_allocation_type: heap_buffers
  memtable_heap_space: <L>
  memtable_offheap_space: 64MiB
  # leave memtable_flush_writers unset (→ 2, threshold 1/3)
  commitlog_total_space: 16384MiB
  auto_snapshot: false
  ```
  `commitlog_total_space` is set high so commit-log pressure never triggers flushes and only `MEMTABLE_LIMIT` does. In `conf/logback.xml`, set the logger `org.apache.cassandra.db.memtable` at `INFO` (the default; the `Flushing largest` line is INFO).

**B3b. Knobs.**

| Knob | Values | Why |
|---|---|---|
| `memtable_heap_space` L | `256MiB`, `1024MiB` | Positive control (a 4× change in the real cap); both well under the 4 GiB heap |
| Selection workload | W-skew: one stress process on `ks1.standard1`. W-even: four concurrent stress processes on `ks1..ks4`, same total thread count. | Line 274 picks one big memtable vs one of four ~equal ones |
| Build | M-orig; optional M-never at L=256 W-skew | Disabling line 274's selection entirely |

> **Audit amendment R4 (2026-10-21, before any run).** The M-never run (L=256, W-skew) is **required**, not optional. Without it the cluster tier never varies line 274's operand or outcome by anything but the workload, so it would not test the constraint the file names. M-first stays unit-tier only.

**B3c. Workload.**
- Write workload:
  ```
  tools/bin/cassandra-stress write n=4000000 cl=ONE -col n=FIXED(1) size=FIXED(1024) -rate threads=64 -schema keyspace=ks1 "replication(strategy=SimpleStrategy,factor=1)" -node 127.0.0.1 -mode native cql3
  ```
  W-even runs four of these in parallel with `n=1000000`, `threads=16`, `keyspace=ks1..ks4`.
- Accounted ownership is about 1.2 KiB/row → ≈ 4.6 GiB per run. With cleaning at L/3 that is ≥ 13 `MEMTABLE_LIMIT` flushes at L=1024 and ≥ 54 at L=256, so the limit is reached many times.
- On disk: ≈ 4.2 GiB per run (random values barely compress), and ≤ 2× that during compaction. Wipe between runs.
- Duration: about 3–10 min per run.

> **Audit amendment R5 (2026-10-21, before any run).** Every stress command adds `no-warmup` and quotes the column options: `... write n=<n> no-warmup cl=ONE -col 'n=FIXED(1)' 'size=FIXED(1024)' ...`. Reasons: (1) stress runs an unthrottled warm-up of up to 50,000 writes per process before measuring (`StressAction.java:105-110`), so W-even's four processes would write about 150,000 more rows than W-skew, which breaks B3h's "same total rows"; (2) unquoted `(` is a `/bin/sh` syntax error when the command goes through a shell (harness defect H2 of `concurrent_writes`). In W-even the four keyspaces are created by one 100-row stress write each before the timed run, so the four timed processes start together without concurrent schema changes.

**B3d. Observables and instruments.**
1. `logs/system.log`, lines `Flushing largest ... Used total: a/b, live: c/d, flushing: e/f, this: g/h`.
   - `a` is `MEMORY_POOL.onHeap.usedRatio()` at selection time. It covers live plus flushing, so it is the pool's real accounted occupancy.
   - `g` is the selected ratio, the value that won at `:274`.
   - Parse with `grep 'Flushing largest' logs/system.log`.
2. Every 1 s:
   - `bin/nodetool sjk mx -b "org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize" -mg -f Value` (global live memtable bytes).
   - `bin/nodetool sjk mx -b "org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation" -mg -f Count`.
3. `jstat -gc <pid> 1000` (old-gen occupancy after mixed collections), plus `gc.log`.
4. At the end:
   - `bin/nodetool tablestats ks1 ks2 ks3 ks4` (memtable switch count, SSTable count)
   - `du -sh /tmp/c509-data/data`
5. stress output: op rate, errors and timeouts.

Not directly observable:
- the pool's `allocated` in bytes (no JMX gauge). It is inferred as `a × L` from the log line, only at selection instants.
- the exact JVM bytes held by memtables. Old gen also holds caches, etc.

> **Audit amendment R6 (2026-10-21, before any run).** Instruments 2–3 are replaced by one JMX client polling every 1 s on one connection, reading the same quantities. Reasons: `jstat` cannot attach to the node, because `conf/jvm-server.options:137` sets `-XX:+PerfDisableSharedMem` (stage-4 defect D3 of `tombstone_failure_threshold`); and `nodetool sjk` starts a JVM per call, so two calls per second cannot keep a 1 s period. Each sample holds: `org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize` `Value`; `org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation` `Count`; `java.lang:type=Memory` `HeapMemoryUsage.used`; `java.lang:type=MemoryPool,name=G1 Old Gen` `Usage.used` and `CollectionUsage.used` (the old gen after the last collection, which is what B3d.3 meant by "old-gen occupancy after mixed collections"). `gc.log` is kept. **Definitions:** "peak `AllMemtablesOnHeapDataSize`" is the maximum 1-s sample from stress start to stress end; "old-gen post-GC baseline" is the median of `CollectionUsage.used` over the same window.
>
> **Runbook fix D2 (stage 4, cluster instrument check before run 1, 2026-10-21; B3f/B3g unchanged).** Under G1 on JDK 11, `G1 Old Gen` `CollectionUsage.used` read 0 throughout a shakedown with young collections, so it cannot carry the old-gen readings. The old gen after each collection is read from `gc.log` instead: (Old regions + Humongous regions after the pause) × 16 MiB (`-XX:G1HeapRegionSize=16m`, `conf/jvm11-server.options:66`), at the pause's timestamp. "Old-gen post-GC baseline" is the median of these values over the stress window, and R8's old-gen sample is the same quantity. The JMX columns stay in the sampler file.

**B3e. Procedure.** For each (L, workload) in {256, 1024} × {W-skew, W-even}, then the optional M-never run:
1. `rm -rf /tmp/c509-data && mkdir -p /tmp/c509-data`. Set L in `conf/cassandra.yaml`.
2. `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M bin/cassandra -p /tmp/c509-data/pid`. Wait for `nodetool status` UN.
3. Start the sampler loop (B3d.2–3) in the background, writing to `/tmp/c509-data/samples.csv`.
4. Run stress (B3c). For W-even, start the 4 processes together.
5. After stress exits, wait 30 s, then capture tablestats, `du`, and copy `logs/system.log`, `gc.log` and `samples.csv` to `/tmp/c509-results/<L>-<workload>/`.
6. Stop the node with `kill $(cat /tmp/c509-data/pid)`, stop the samplers, and check `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` are empty.
7. M-never: repeat with the mutant build at L=256, W-skew, with stress `n=1000000` and `-errors ignore`. Stop after 5 min if stress makes no progress.

> **Audit amendment R7 (2026-10-21, before any run).** Exact stop conditions. Every run: the `Flushing largest` lines are counted from the byte offset of `system.log` at stress start (a fresh log directory per run). M-run (M-never, required by R4): stress is stopped 300 s after it starts whatever its progress, the samplers run until then, and the node is stopped with SIGTERM and, if still alive after 60 s, SIGKILL (B4). Disk guard for a shared host: a run is stopped if free space on `/` falls below 25 GB.

**B3f. Predictions (stated before any run).**
- **M-orig, both L, both workloads:**
  - every `Used total` on-heap value `a` ≤ 1.0 (allowing ≤ 1.02)
  - peak `AllMemtablesOnHeapDataSize` ≤ L
  - median `a` at selection in [0.33, 0.7]
- **Fixed L, W-skew vs W-even:**
  - the median and max of `a` differ by ≤ 0.10, and the peak of `AllMemtablesOnHeapDataSize`/L differs by ≤ 0.10
  - `g` (selected ratio) in W-even is about ¼ of W-skew's (0.08–0.15 vs 0.33–0.6)
  - the `MEMTABLE_LIMIT` flush count in W-even is about 2–4× W-skew's
- **Positive control:** peak `AllMemtablesOnHeapDataSize` at L=1024 is about 4× (3–5×) the value at L=256 for the same workload. Old-gen post-GC baseline is higher by roughly the same absolute amount (≈ 0.5 GiB ± 0.3 GiB).
- **M-never:**
  - no `Flushing largest` lines
  - `AllMemtablesOnHeapDataSize` plateaus at ≈ L (≤ 1.02·L)
  - `BlockedOnAllocation` count rises
  - stress shows timeouts or zero throughput after the plateau
  - no OOM

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| `a` ≤ ~1.0 and peak/L equal (±0.10) across W-skew/W-even, while `g` and flush counts differ as predicted, and peak scales ~4× with L | **Claim confirmed:** usage follows `memtable_heap_space`, not the line-274 selection |
| M-never plateaus at ≈ L with writes blocked | **Confirmed:** line 274 governs liveness, not the cap |
| Peak/L differs by > 0.10 between W-skew and W-even at fixed L, or `a` > 1.05 | **Claim refuted:** the selection outcome affects how much memory is held |
| M-never: `AllMemtablesOnHeapDataSize` grows past 1.05·L, or the node OOMs | **Claim refuted:** the cap depends on line 274 |
| No `Flushing largest` lines in M-orig runs (flushes came from commit log or other reasons) | **Not confirmed:** the limit was not reached through this path; raise `n` or lower L |
| Peak does not move between L=256 and L=1024 | **Not confirmed:** the positive control failed, so the instrument or workload is not exercising the pool |

> **Audit amendment R8 (2026-10-21, before any run).** Rows added for outcomes the table above leaves out:
>
> | Observation | Meaning |
> |---|---|
> | M-never: any `Flushing largest` line, or a `MEMTABLE_LIMIT` switch of `ks1.standard1` during the run | **Invalid** M-never arm: the build is not the mutant, or another path flushed |
> | M-never: `AllMemtablesOnHeapDataSize` plateaus below 0.9·L with writes blocked | **Not confirmed:** the arm did not reach the cap |
> | The counters stay capped (`a` ≤ 1.02, `AllMemtablesOnHeapDataSize` ≤ 1.02·L) but in M-never the old-gen post-GC sample keeps rising after the memtable plateau, ending more than 1.5·L above the M-never run's first post-plateau sample | **Not confirmed:** the counter is capped but the real heap is not |

**B3h. Controls.**
- `commitlog_total_space` raised, `memtable_flush_period` 0 (the default) and `auto_snapshot` off, so `MEMTABLE_LIMIT` is the only flush reason. Verify this in the log: all flushes are preceded by `Flushing largest`, apart from schema / system flushes at startup.
- Same total rows and threads in both workloads.
- Fresh data directory and fresh JVM per run.
- 4 GiB heap ≫ L, so GC pressure does not cap usage first.
- The 4× L change is the positive control.
- The mutant isolates line 274's outcome with everything else equal.

**B4. Risks and cleanup.**
- **Disk:** at most about 10 GiB per cluster run, on local `/` (~50 GB free). Wipe `/tmp/c509-data` between runs. The unit tier writes under the clone's `build/test` (< 2 GiB).
- **Shared storage:** nothing is written to the shared source clone or to `/proj`. All builds are in `/tmp/c509-*`, and results go to `/tmp/c509-results`.
- **Processes:** after every run, `pkill -f CassandraDaemon`, `pkill -f cassandra-stress` and kill the sampler loop. Then verify with `pgrep -fa 'CassandraDaemon|cassandra-stress|sjk'` (no output).
- **M-never can hang writers.** Unit tier: per-insert timeouts. Cluster tier: a 5-min cap and a hard `kill -9` if `nodetool drain` blocks.
- **Final cleanup:** `rm -rf /tmp/c509-unit /tmp/c509-unit-mut /tmp/c509-node /tmp/c509-node-mut /tmp/c509-data` once results are copied.

## C. Sources read

- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/playbook-autonomous.md
- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/_TEMPLATE-autonomous.md
- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/README.md (§6.1 only)
- src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java
- src/java/org/apache/cassandra/utils/memory/MemtablePool.java
- src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java
- src/java/org/apache/cassandra/utils/memory/MemtableCleanerThread.java
- src/java/org/apache/cassandra/utils/memory/SlabAllocator.java (grep)
- src/java/org/apache/cassandra/db/memtable/Memtable.java (MemoryUsage, Owner)
- src/java/org/apache/cassandra/db/ColumnFamilyStore.java:1436-1458 and the FlushReason grep
- src/java/org/apache/cassandra/config/Config.java:185-190, 524
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java:583-594, 752-775, 4055-4062, 4124-4126
- src/java/org/apache/cassandra/metrics/TableMetrics.java:488-525, 1331-1349
- conf/cassandra.yaml:783-825, 883, 899-912, 1147
- test/conf/cassandra.yaml
- test/unit/org/apache/cassandra/db/partitions/AtomicBTreePartitionMemtableAccountingTest.java (grep)
- test/unit/org/apache/cassandra/cql3/CQLTester.java (grep)
- build.xml (testsome target, jvmargs)
- src/java/org/apache/cassandra/tools/NodeTool.java (grep for Sjk)

## D. Stage-4 feedback

**2026-10-22 — run 1 (2026-10-21) closed: unit Refuted — does not cap; cluster Confirmed — does not cap** (no run 2). Results: [`results/largestRatio-flushLargestMemtable-largestRatio--autonomous.md`](../../stage4-runtime-verification/results/largestRatio-flushLargestMemtable-largestRatio--autonomous.md); harness `stage4-runtime-verification/harness/largestRatio-flushLargestMemtable-largestRatio--autonomous/`. Run on `pc07`, shared with another stage-4 session; node on 127.0.0.4 with JMX 7204, clones `~/cassandra-lrt` and `~/cassandra-lrt-mut` (environment deviation; design unchanged). Run 1 used the audit freeze (sha256 `60974bb2…`) plus runbook fixes D1 (unit, `54e8da0e…`) and D2 (cluster, `45a1ce01…`). The estimate is left as filed.

- **Ceiling (holds):** in no variant — original, M-first, M-never — did accounted memtable usage pass `memtable_heap_space`; the ceiling followed the knob (unit 3.35–4.26×, cluster 3.99–4.11×). M-never stops writes at exactly L (unit L − 323 B; cluster 256.0 MiB flat, writes timing out, no OOM). Line 274 governs liveness and flush sizes, not the cap.
- **"Same peak/L" (refuted in the unit tier):** below the cap the selection changes how much is held: at L = 128 MiB the skewed selection peaked at 0.58 L and the even one at 0.42 L (three JVMs agree). At L = 32 MiB, and on the cluster where both workloads ran into the cap (`BlockedOnAllocation` > 0 in every arm), the peaks were equal.
- **Real heap vs accounting (beyond the claim):** M-first at L = 128 MiB kept the pool ≤ L but ran a 1 GiB test JVM out of heap (≈ 0.9 GB of live `byte[]`), most likely 1 MiB slab regions held by ≈ 1000 tiny memtables. A3 step 6's "slab region waste … a little larger" is only small when memtables are large; the selection policy is what keeps them large.
- **For stage 3 (no re-estimate):** (1) the named "constraint" `largestRatio` is a running-maximum accumulator, not a limit; this row of `predicted-negative.md` is better classed as "selection, not a limit check". (2) `memtable_cleanup_threshold` and `memtable_offheap_space` were never varied, so A1's statement that they bound memory is untested here. (3) `AllMemtablesOnHeapDataSize` counts live memtables only and is pinned near L/3 by the cleaner, and the log's `a` is sampled only at selections; a pool-occupancy sampler would make B3f decisive. (4) `BlockedOnAllocation` is a Timer of completed waits, so it cannot show writers blocked forever (B2f/B3f's M-never prediction missed for that reason). (5) B2f's "M-first switches include system tables" missed: after the flush-all, system memtables were empty.
