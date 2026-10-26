# SASI MAX_TERM_SIZE (1024 bytes) in TrieMemIndex.add — verification solution  <!-- file: cases/sasi-max_term_size-TrieMemIndex-add-termSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/index/sasi/memory/TrieMemIndex.java:84` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude (Sonnet 5.5), Claude Code CLI, 2026-10-25 |
| Estimate | `negative`: the constant bounds the size of one indexed term (<= 1023 bytes), not the memory a SASI memtable index uses. Total trie memory scales with distinct terms and, for CONTAINS mode, roughly with the square of term length; it is bounded only by the memtable pool (`memtable_heap_space` / flush), which is a different constraint. |
| Ground | `MAX_TERM_SIZE` is a hard-coded `public static final int` (`OnDiskIndexBuilder.java:128`) that guards the on-disk term format (the same check is repeated on the flush path), and it is applied per term; nothing sums it across terms or sessions. The memtable accounting the index feeds (`SASIIndex.java:320`) triggers flushes via the memtable pool, so the total is capped by the pool, not by this constant. The per-term cap does bound one object, so a narrow positive reading ("no single term exceeds 1 KiB, so no single add costs more than about 1 MiB of trie in CONTAINS mode") holds; the claim tested below is that total usage does not follow the constant. |

## A. Constraint trace

**A1. The constraint.** `OnDiskIndexBuilder.MAX_TERM_SIZE`; kind: compile-time constant. Declared at `src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java:128` (`public static final int MAX_TERM_SIZE = 1024;`). Unit: bytes of one term (`ByteBuffer.remaining()`). Default 1024, a literal, not derived. Not settable by yaml, `-D` or JMX; changing it needs a source edit and rebuild (and a restart). The check is `>=`, so the largest accepted term is 1023 bytes. Related gate: `sasi_indexes_enabled` (`Config.java:606`, default false; `conf/cassandra.yaml:1992`) must be true for SASI indexes to be created; it does not affect the term limit.

**A2. What it caps.** Heap (on-heap memtable index structure) and, on the flush path, the in-memory index builder and the on-disk term size. The quantity compared is `term.remaining()` of one analyzer output token (`TrieMemIndex.java:84`), in bytes, not a running total.

**A3. Mechanism.**
1. A write reaches `SASIIndex`'s indexer; `insertRow` (`SASIIndex.java:297`) calls `ColumnIndex.index` (`ColumnIndex.java:103-106`), then `IndexMemtable.index` (`IndexMemtable.java:45`; amended 2026-10-25, was `:44`), which returns 0 for null/empty values (`:47-48`) and, for a value that fails `TypeUtil.isValid` and cannot be upcast, logs an error and returns 0 (`:50-63`; amended 2026-10-25, was "lines 49-64"), then `index.add` (`IndexMemtable.java:65`).
2. `MemIndex.forColumn` (`MemIndex.java:45-47`) picks `TrieMemIndex` for literal (UTF8/ASCII) columns, `SkipListMemIndex` otherwise. This target is therefore reached only by text columns.
3. `TrieMemIndex` constructor selects `ConcurrentSuffixTrie` for mode CONTAINS (`TrieMemIndex.java:61-63`) and `ConcurrentPrefixTrie` for PREFIX (`:65-67`).
4. `TrieMemIndex.add` (`:74`) runs the analyzer and loops over tokens. For each token, `if (term.remaining() >= OnDiskIndexBuilder.MAX_TERM_SIZE)` (`:84`) logs at info and `continue`s (`:91`): the token is silently skipped, no error to the client, the row write succeeds, and the term is simply not searchable. Otherwise `index.add(getString(term), key)` (`:94`).
5. `ConcurrentTrie.add` (`:116`) creates a `ConcurrentSkipListSet` per new term (`:126` adds `CSLM_OVERHEAD + value.length()`, with `CSLM_OVERHEAD = 128`, `SkipListMemIndex.java:35`), adds the key (`:131`), and adds the size of nodes created in this update, taken from `SizeEstimatingNodeFactory` (`:134-135`, class at `:245`, `measure` at `:266-282` (amended 2026-10-25, was "about `:262-281`"), edge chars counted as 2 bytes each at `:272`; the node factory's `createNode` adds `measure(node)` for every node built in the update, at `:249-254`).
6. The returned estimate goes to `adjustMemtableSize` (`SASIIndex.java:318-321`), which calls `Memtable.markExtraOnHeapUsed` (`AbstractAllocatorMemtable.java:194-197`) so the pool, not this constant, decides when to flush.
7. Same limit repeated at flush: `PerSSTableIndexWriter.java:218` (skip with log) and `OnDiskIndexBuilder.java:167` (error log, return).
Bypass/overshoot: (a) many terms, each under 1 KiB, are unbounded in count. (b) `ConcurrentSuffixTree` stores every suffix of a term, so a 1023-byte term can cost far more than 1023 bytes (see B2f). (c) The check is on bytes of the analyzed token, but trie nodes are measured in chars (2 bytes each in the estimate), so multi-byte UTF-8 changes the ratio. (d) The estimate is only an estimate (comment at `:242-244`; it says it can overestimate); actual retained heap may differ.

**A4. Other consumers.** The memtable data itself (`memtable_heap_space`, `memtable_allocation_type`, `conf/cassandra.yaml:797-825`), the flush-time `OnDiskIndexBuilder` segments bounded by `maxMemorySize` (`PerSSTableIndexWriter.java:201, 247`), row/key/partition caches, bloom filters, compaction and read buffers.

**A5. Evidence beyond the source.** none (design from source only; the SASI experimental warning is at `SASIIndex.java:88`).

## B. Verification solution

**B1. Claim under test.** SASI memtable index memory does not follow `MAX_TERM_SIZE`: (i) the constant only accepts/rejects individual terms (1023 accepted, 1024 rejected), and (ii) accepted terms at the limit in CONTAINS mode cost much more than their byte size, while total node usage is governed by the number of terms and the memtable pool/flush trigger. It is refuted if node memory (or the accounted size) is capped at a value determined by the constant independently of term count and pool settings.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. `rsync -a ~/cassandra-5.0.9/ /localdisk/c509-unit/` (local disk; never build in the shared tree). `cd /localdisk/c509-unit && ant jar` then add test class `test/unit/org/apache/cassandra/index/sasi/memory/TrieMemIndexSizeTest.java` (new file, only in the copy). The test builds a `ColumnIndex` for a `text` column the way `SASIIndexTest` does (a `ColumnFamilyStore` created by `SchemaLoader` with a `CUSTOM` SASI index, `mode` option CONTAINS or PREFIX, `analyzed` false), then calls `ColumnIndex.getCurrentMemtable().index(DecoratedKey, ByteBuffer)` (`IndexMemtable.java:45`) and records the returned long. Run: `ant testsome -Dtest.name=TrieMemIndexSizeTest`. JVM opts: `-Xmx2g -Xms2g`; set `sasi_indexes_enabled: true` in the test yaml copy (`test/conf/cassandra.yaml`).

**B2b. Knobs.** (1) Term length L in bytes (ASCII): 1, 100, 512, 1022, 1023, 1024, 1025, 4096. Straddles the `>=` boundary. (2) Index mode: CONTAINS vs PREFIX (different trie class). (3) Term count N per length: 1, 10, 100. Set in code. (4) Positive control: `SkipListMemIndex` column (an `int` column, same N) to show the size return moves with content.

**B2c. Workload.** Single thread. For each (mode, L, N): create a fresh index memtable, generate N random printable-ASCII terms of exactly L bytes (fixed seed, distinct, a-zA-Z0-9 so first characters diverge), index each under its own `DecoratedKey`, sum the returned sizes. Arithmetic: at L=1023 the CONTAINS estimate is 1 to 5 MB per term (B2f), so N=100 would be 100 to 500 MB of estimate plus the real objects, too much for the 1 GiB JVM that `ant testsome` forks (`build.xml:1512` `maxmemory="1024m"` overrides `-Xmx`). **[Amended 2026-10-25, B5.2]** Sets used: CONTAINS at L=1023: N in {1, 10, 30}; CONTAINS at L=100 and L=512: N in {1, 10, 100}; PREFIX at L in {100, 512, 1023}: N in {1, 10, 100}; every mode at L in {1024, 1025, 4096}: N=10; the JVM is the 1 GiB one `ant testsome` gives (the `-Xmx2g -Xms2g` of B2a is not available through `testsome`).

**B2d. Observables and instruments.** (1) The sum of `IndexMemtable.index` return values (the check's own usage-side number). (2) Whether `search` finds the term (`IndexMemtable.search(Expression)` with an EQ expression built by `new Expression("v", UTF8Type.instance).setOp(Op.EQ).setLower(new Expression.Bound(term, true))`; a non-empty `RangeIterator` means found) [amended 2026-10-25, B5.8: `ColumnIndex.searchMemtable` does not exist; `IndexMemtable.search` is `IndexMemtable.java:68`], to detect silent skip. (3) Retained heap via a `Runtime` used-memory delta after two `System.gc()` calls (the test JVM is the measured one), to compare to the estimate. Not directly observable: per-index retained size is not exposed; the JVM delta includes keys and test overhead.

**B2e. Procedure.**
1. Build as in B2a. 2. For each mode and L with N=1, run and record (returned size, found-by-search, heap delta after GC). 3. Repeat for the N values listed in B2c (amended 2026-10-25, B5.2). 4. Run the L=1024 and 1025 cases and the check logs for `Can't add term of column` (`TrieMemIndex.java:86`). 5. Run the SkipList control. 6. Delete `/localdisk/c509-unit`.

**B2f. Predictions (before any run).** [Amended 2026-10-25 (B5.3) for the per-term brackets and the N values; derivation from `TrieMemIndex.java:116-138, 245-282`.]
- L=1023: returned size > 0, term found. L=1024, 1025, 4096: returned size = 0, term not found, one info log per rejected term. (If L=1023 is rejected or L=1024 accepted, the trace of `>=` is wrong.)
- PREFIX mode: size grows linearly in L. Per term at L=1023 the estimate is between 3.3 KB and 7.5 KB: 128 + (128 + 1023) = 1279 B of set overhead and value length, plus a leaf node of about 2 x 1021 + 64 = 2.1 KB, plus (once first characters start to collide) the recopied remainder of the existing leaf (another about 2 KB) and the re-created parent node (up to 24 B x 62 children + 56 = 1.5 KB). At L=512 the per-term figure is between 0.45 and 0.65 of the L=1023 figure.
- CONTAINS mode: size grows roughly with L squared: every suffix of a term is a separate key whose leaf edge is about its remaining length in chars at 2 bytes each, so the leaf edges alone are about L x L = 1.05 MB at L=1023, and node re-creation and split copies add to it. At L=1023 expect 1.0 to 5 MB per term (the lower bound is the leaf edges alone), at least 150 times the PREFIX figure for the same term. A ratio under 10x would contradict the suffix expansion. At L=512 the per-term figure is between 0.15 and 0.40 of the L=1023 figure (a square law gives 0.25; a linear law would give 0.5).
- Size is linear in N for distinct random terms: the total for N terms is between 0.7 x N and 2 x N times the total for N=1 (later terms cost more than the first because of splits), so no plateau tied to 1024.
- Retained heap delta after GC within a factor of about 2 of the summed estimate (indicative; no conclusions row depends on it).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Size scales with N (no plateau at any N) and CONTAINS at L=1023 >> L bytes | Claim confirmed: accepted-term count and mode, not the constant, drive usage |
| Size per term bounded by about 1 KiB-scale value in CONTAINS mode | Claim refuted: the constant effectively caps usage per term; re-trace the suffix expansion |
| Total size plateaus as N grows for fixed L | Claim refuted (some other bound); investigate |
| L=1023 rejected or L=1024 accepted | Boundary misread; fix A3 step 4 and rerun |
| Usage flat vs the knob while the positive control (SkipList / varied N) moves | Confirmed |
| Limit never reached (no term of 1023 bytes reached the trie, e.g. all analyzed away) or control did not move | Not confirmed; fix the workload |

**B2h. Controls.** Fixed seed and distinct terms (no dedup); `analyzed=false` so the whole value is one token; ASCII only (bytes = chars); fresh memtable per run; GC before each heap reading; the SkipList column as positive control; each (mode, L) run alone in its JVM to avoid heap carry-over.

### B3. Cluster tier

**B3a. Environment and build.** One node suffices. Local copy `/localdisk/c509-node` built with `ant jar`; JDK 11. Data, commitlog, hints, saved_caches under `/localdisk/c509-node/data` (check `df -h` for at least 20 GB free first). `conf/cassandra.yaml`: `sasi_indexes_enabled: true`, `memtable_allocation_type: heap_buffers` (default), `memtable_heap_space: 256MiB`, `memtable_cleanup_threshold` left at default, `commitlog_total_space: 1024MiB`, `num_tokens: 1`, `concurrent_writes: 8`. `jvm11-server.options`: `-Xms2G -Xmx2G`, G1. For the knob that changes the constant, build a second copy `/localdisk/c509-node-256` with `MAX_TERM_SIZE` edited to 256 (`OnDiskIndexBuilder.java:128`) and a third at 4096. [Amended 2026-10-25, B5.5: the constant is inlined by `javac` into `TrieMemIndex`, `PerSSTableIndexWriter` and `OnDiskIndexBuilder`, so each edited copy is edited before its first build (a fresh `copy-source.sh` tree, then `ant jar`), never rebuilt incrementally. The 4096 build may flush: 4096 is below the on-disk format's `Short.MAX_VALUE` (`OnDiskIndexBuilder.java:171`), so no stop before the first flush is needed.] Node data is under `~/s4-tm-data/<label>`, not `/localdisk/...`; `memtable_cleanup_threshold` default is 1/(1+`memtable_flush_writers`) = 1/3 (`DatabaseDescriptor.java:753-763`, flush writers default 2 with one data directory), so a flush is requested when the pool's used bytes exceed `memtable_heap_space`/3 (`MemtablePool.java:125-149`).

**B3b. Knobs.** (1) Constant: 256 / 1024 / 4096 (separate builds). (2) Index mode CONTAINS vs PREFIX. (3) `memtable_heap_space`: 256MiB vs 128MiB (positive control: this one is expected to move flush timing). (4) Term length at the workload: 1023 and 1024 bytes on the 1024 build.

**B3c. Workload.** Keyspace RF=1, table `t(id uuid primary key, v text)`; `CREATE CUSTOM INDEX ON t(v) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode':'CONTAINS','analyzed':'false'}`. A small Python driver inserts rows with random ASCII values of exactly the stated length, one value per row, over native protocol 4. **[Amended 2026-10-25, B5.4]** The row counts of the original text (500 to 1000 CONTAINS rows, 100 000 PREFIX rows) are replaced by a stop condition: load until the table's `MemtableSwitchCount` reaches 3 (three flushes), with a row cap as the 'limit never reached' test. Arithmetic: a flush is requested at 85.3 MiB of used pool (256 MiB / 3); a CONTAINS row of 1023 characters adds 1 to 5 MB of estimate (B2f), so the first flush comes after 17 to 85 rows and three flushes after at most about 260 rows: cap 600 rows. 255 characters on the 256 build add about 1/16 of that per row: cap 6000 rows. 4095 characters on the 4096 build add 16 to 80 MB per row: three flushes after at most about 16 rows, cap 60 rows. PREFIX at 1023 characters adds 3.3 to 7.5 KB of index estimate plus about 1.2 KB of cell and partition data per row, so a flush every 10 000 to 20 000 rows: cap 150 000 rows. The CONTAINS loaders keep one request in flight (the overshoot past the flush trigger is then at most one row's estimate); the PREFIX loader keeps 64. The 1024-character run on the 1024 build and the index-dropped control load the same number of rows as the 1023-character CONTAINS run needed for its third flush. The 1023-character and 1024-character runs end with one read by key and one `LIKE '%<20 characters from the first row>%'` query.

**B3d. Observables and instruments.** `nodetool tablestats ks.t` (Memtable data size, Memtable off heap size), JMX `org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=MemtableOnHeapDataSize` and `MemtableSwitchCount`, `nodetool info` heap, `jcmd <pid> GC.heap_info` and `GC.class_histogram` (counts of `ConcurrentSkipListMap`, `CharArrayNodeDefault`, char arrays), the log for `Can't add term`, flush log lines. Sample every 2 seconds during the workload. Not observable: per-index trie size separately from the memtable's own cells; use the histogram deltas and compare the same workload with the index dropped (control). [Amended 2026-10-25, B5.7] The bytes at each flush are read from the log line `Enqueuing flush of ks.t, Reason: MEMTABLE_LIMIT, Usage: ...` (`ColumnFamilyStore.java:1046-1055`) and from a JMX sampler every 500 ms of `MemtableOnHeapDataSize` (`Value`, which is the memtable allocator's on-heap `owns`, `TableMetrics.java:493-495`) and `MemtableSwitchCount` (`Count`); the `GC.class_histogram` total (live objects, forced GC) is taken before the load and once when the first memtable has reached 60% of the flush trigger, so the live heap is compared with the tracked size while the index memtable is full.

**B3e. Procedure.**
1. Start the 1024 build; confirm `nodetool status`, record baseline heap and the class histogram.
2. Create keyspace, table, CONTAINS index; run the 1023-char workload in steps of 200 rows; after each step record B3d values.
3. Note the step where `MemtableSwitchCount` increments and the on-heap size at that point.
4. Repeat with 1024-char values: expect rejection logs and no growth.
5. Repeat with PREFIX mode (1023-char values, 100 000 rows).
6. Repeat the CONTAINS run on the 256 and 4096 builds with values of 255 and 1023/4095 chars.
7. Control: same CONTAINS workload with the SASI index dropped.
8. Repeat step 2 with `memtable_heap_space: 128MiB`.
9. `nodetool drain`, stop every Cassandra process (`pgrep -f CassandraDaemon` must be empty), delete the data dirs.

**B3f. Predictions (before any run).** [Amended 2026-10-25 (B5.4) for the flush-point numbers; derivation from `MemtablePool.java:125-149`, `DatabaseDescriptor.java:753-763` and B2f.]
- 1024 build, 1023-char CONTAINS, `memtable_heap_space: 256MiB`: the memtable's tracked on-heap size grows by 1 to 5 MB per row (the suffix tree), the used pool crosses 85.3 MiB (256 MiB / 3) after 17 to 85 rows, and each flush is logged with a usage of at least 85.3 MiB and at most 85.3 MiB plus one row's estimate. Three flushes (`MemtableSwitchCount` = 3) happen within 260 rows. The live heap in the class histogram, taken with the first memtable at 60% of the trigger, is within a factor of about 2 of the tracked on-heap size (indicative).
- 1024-char values on the 1024 build (same row count as the run above): no growth in index structures, `Can't add term` info logs equal to the row count, `MemtableSwitchCount` stays 0, tracked on-heap size stays under 2 MiB (about 1.2 KB per row of data), rows are readable by key, and `LIKE '%x%'` finds nothing for those rows.
- PREFIX, 1023 chars: three flushes only after tens of thousands of rows (between 31 000 and 60 000); per-row growth is a few KB; each flush at 85.3 MiB or just above (the PREFIX loader has 64 rows in flight, a few hundred KB).
- 256 build (255-char values) and 4096 build (4095-char values): per-row CONTAINS growth about 1/16 and 16x of the 1023-char/1024-build figure (the L-squared law), so rows per flush are about 16x more (256) and 16x fewer (4096); the bytes at each flush are the same trigger, between 85.3 MiB and 85.3 MiB plus one row's estimate (at most about 100 MiB at 255 chars, at most about 170 MiB at 4095 chars), whatever the constant.
- Dropping the index (same rows): no growth beyond the data, no flush. `memtable_heap_space: 128MiB`: the flush trigger moves to 42.7 MiB (flush usage between 42.7 MiB and 42.7 MiB plus one row's estimate, about half the 256 MiB value for the same workload) and rows per flush halve.
- Peak heap stays under `-Xmx` throughout; no OOM.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Bytes at flush the same across 256/1024/4096 builds (each within one row's estimate of 85.3 MiB) and halved at 128MiB; growth per row varies with term length and mode | Claim confirmed: usage is governed by the pool and workload, not by the constant |
| Memtable on-heap size or heap plateaus at a value set by the constant (e.g. scales with 256 vs 1024 vs 4096 for the same term count) | Claim refuted |
| Rows with 1024-byte terms add index structure | Boundary or trace wrong |
| `memtable_heap_space` change moves the flush point while the constant does not (positive control) | Control works; supports confirmation |
| The flush point does not move when `memtable_heap_space` changes, or three flushes do not happen within the row cap | Control failed or workload too small: not confirmed |
| Heap growth with the index dropped is the same as with it | Index not the cause; workload invalid |

**B3h. Controls.** Index dropped; PREFIX vs CONTAINS; `memtable_heap_space` change as the positive control (the cap known to bind); identical row counts and seeds; GC and settle 30 seconds before each reading; single node so no replication or hint effects.

**B4. Risks and cleanup.** CONTAINS at L=1023 consumes 1 to 5 MB per row: cap rows as in B3c and heap at 2 GB; run on a machine where 2 GB is free. All data, commitlog, hints on `/localdisk` (about 5 GB at most); do not use shared storage or the shared source tree. At the end: `nodetool drain`, kill the daemon, `pgrep -fl "CassandraDaemon|ant"` must show nothing, remove the run data directories (`~/s4-tm-data`).

**B5. Stage-4 audit amendments (2026-10-25, before any reading).**
1. B5.1 Citations (A3, B2a): `IndexMemtable.index` is at `:45` (not `:44`), its null/empty return at `:47-48`, the validation-and-upcast drop at `:50-63` (the write-up's "49-64" is wrong; there is no such 16-line drop); `SizeEstimatingNodeFactory.measure` is `:266-282` (not "about `:262-281`"); the estimate comment is `:242-244`. `SASIIndex.java:318-321` (`adjustMemtableSize`, calling `markExtraOnHeapUsed` at `:320`, called from `insertRow` at `:297` when `isNewData()`, `:313-316`) and `AbstractAllocatorMemtable.java:194-197` were checked and are correct. All other line cites were re-read and are correct.
2. B5.2 B2c: the JVM `ant testsome` forks is 1 GiB (`build.xml:1512`), so the N sets are reduced for CONTAINS at L=1023 (N in {1, 10, 30}); the B2a `-Xmx2g -Xms2g` is not available.
3. B5.3 B2f: per-term brackets derived from the node arithmetic (PREFIX 3.3 to 7.5 KB at L=1023; CONTAINS 1.0 to 5 MB, the write-up's 0.5 to 2 MB had a lower end below the leaf-edge floor of L x L = 1.05 MB); ratio and N rules stated as relations; no conclusions row changed.
4. B5.4 B3c/B3f/B3g: the row counts (500 to 1000 CONTAINS rows, "256 MiB x threshold-share") are replaced by a stop at three memtable switches with row caps, from the cleanup threshold 1/3; bytes at flush are "at least H/3 and at most H/3 plus one row's estimate" (the 4096 build's row is 16 to 80 MB); the B3g rows keep their meaning with that tolerance and "three flushes within the row cap" in place of "2000 rows".
5. B5.5 B3a: the constant is edited before the first build of each tree (inlined by `javac`); the 4096 build may flush.
6. B5.6 Both tiers: the claim is negative, so the positive control is the memtable pool for the cluster tier (`memtable_heap_space` 256 vs 128 MiB moves the flush point, a cap known to bind on the same on-heap memtable accounting that `markExtraOnHeapUsed` feeds) and, in the unit tier, the N dose and the SkipList column (the instrument's size return moves with content); the unit tier has no pool, so its control is Partly (a returned size that moves with N and with the L=1023/1024 step shows the instrument can see the constant's per-term effect).
7. B5.7 B3d instruments: log line and JMX names given in B3d.
8. B5.8 B2d: the search call is `IndexMemtable.search(Expression)`.
9. B5.9 Left for stage 3 (not applied): `OnDiskIndexBuilder.java:171` prints `Short.MAX_VALUE` as the maximum size (upstream inconsistency).


## C. Sources read

- /tmp/wprompt.txt
- ~/writeup-A/playbook-autonomous.md
- ~/writeup-A/_TEMPLATE-autonomous.md
- ~/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/memory/TrieMemIndex.java
- ~/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/memory/IndexMemtable.java
- ~/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/memory/MemIndex.java
- ~/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java
- ~/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java
- ~/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/conf/ColumnIndex.java
- ~/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/SASIIndex.java
- ~/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java
- ~/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java
- ~/cassandra-5.0.9/conf/cassandra.yaml

## D. Stage-4 feedback

Stage-4 run 1, 2026-10-25/26, pc12, unit and cluster tiers, both **Confirmed — does not cap**; outcome class **true negative**. Results: `stage4-runtime-verification/results/sasi-max_term_size-TrieMemIndex-add-termSize--autonomous.md`. Audit amendments B5.1 to B5.9 (dated 2026-10-25, before any reading); sha256 after them and before this section `58c8a4fb005364174c5d495ef4bb2b0e82e95072f23f41e7869e9246f67bf157`.
- Unit: 1023 accepted and 1024, 1025, 4096 rejected in PREFIX and CONTAINS; the returned estimate per term at 1023 is 3.7 KB (PREFIX) and 1.69 MB (CONTAINS, 462x), grows with N with no plateau (CONTAINS N=30: 47.8 MB); real heap about half of the estimate.
- Cluster: the memtable flushes at `memtable_heap_space`/3 (85.3 to 89.0 MiB) with the constant at 256, 1024 and 4096 (478, 57 and 4 rows per flush), at 42.9 MiB with a 128 MiB pool (positive control, 0.498); 1024-char rows add no index structure (174 rows, data size equal to the no-index arm); PREFIX needs about 15,000 rows per flush.
- Corrections to this file: `IndexMemtable.index` is `:45` with the validation drop at `:50-63` (not 49-64); `measure` is `:266-282`; the CONTAINS per-term bracket is 1.0 to 5 MB (observed 1.7 MB); 256 MiB / 3 flush trigger replaces the row counts of B3c; the 256 build had about 8x (not 16x) the rows per flush because the estimate grows with the term length to a power below 2 (unit L=512 over L=1023 is 0.305).
- Not explained: the 4095-char rows on the 4096 build were indexed and flushed (SI files 5.6 to 40.8 MB) but a LIKE query found 0 hits; the live heap there was larger than the tracked size (0.40).
