# sasi-compaction-flush-memory-ensurecapacity-tmp — verification solution  <!-- file: cases/sasi-compaction-flush-memory-ensurecapacity-tmp--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/utils/LongTimSort.java:821` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code agent, 2026-10-26 |
| Estimate | `negative`: the only limit visible at the target (`tmp` capped at `a.length >>> 1`) is structural, and the knob that really governs the sorted array's size, SASI `max_compaction_flush_memory_in_mb`, is checked against an estimate that does not count the `long[]` that this sort works on. |
| Ground | `PerSSTableIndexWriter.Index.add` (PerSSTableIndexWriter.java:247) compares `OnDiskIndexBuilder.estimatedMemoryUse()` with the limit. That estimate (OnDiskIndexBuilder.java:182, 194) counts only the term map entries (`64+48+len` per distinct term, `60+40+8` per key). The CONTAINS-mode flush then builds `SuffixSA` (OnDiskIndexBuilder.java:255), whose `long[charCount]` suffix array (SuffixSA.java:64) and the TimSort `tmp` buffer (LongTimSort.java:835) are allocated after the check and are never counted. Their size is 8 and up to 4 bytes per *character* of all terms, versus roughly 1 byte per character in the estimate. |

## A. Constraint trace

**A1. The constraint.**
There are two layers.
- *Local guard at the target.* `LongTimSort.ensureCapacity` (LongTimSort.java:820-839) grows the merge buffer `tmp` only when `tmp.length < minCapacity` (line 821). New size is the next power of two above `minCapacity`, capped at `a.length >>> 1` (line 833). It is a constant property of the algorithm (the merge buffer never needs more than half the array). Kind: constant, not settable. The initial size is `min(256, len>>>1)` for large arrays (lines 102, 138-139).
- *The user-facing constraint the cap is nested under.* SASI index option `max_compaction_flush_memory_in_mb`. Declared at IndexMode.java:58 (`INDEX_MAX_FLUSH_MEMORY_OPTION`), parsed at IndexMode.java:186-188 as `1048576L * value` bytes. Default `DEFAULT_MAX_MEM_BYTES = (long)(1073741824 * 0.15)` ≈ 161 MB (IndexMode.java:59-60). Values above 100 GiB are reset to the default (IndexMode.java:190-193). Unit: MiB in the CQL option, bytes internally. Set per index through `CREATE CUSTOM INDEX ... WITH OPTIONS`; fixed at index creation (needs a drop/recreate to change). SASI itself needs `sasi_indexes_enabled: true` (Config.java:606; default false).
- For memtable flushes the limit is the hard-coded 1 GiB (`PerSSTableIndexWriter.maxMemorySize`, PerSSTableIndexWriter.java:365-369); the option applies only to non-FLUSH operations (compaction, index build).

**A2. What it caps.**
Intended: on-heap memory used by an in-progress SASI index segment. The quantity compared is `OnDiskIndexBuilder.estimatedBytes` (OnDiskIndexBuilder.java:148, 201), a running sum of fixed per-term and per-key constants (jol-derived per the comment at line 179). The `tmp` guard itself caps the sort buffer relative to the array length only.

**A3. Mechanism.**
1. Each token goes to `currentBuilder.add` (PerSSTableIndexWriter.java:~236). For a new distinct term, `estimatedBytes += 64+48+term.remaining()` (OnDiskIndexBuilder.java:182); for each key, `+= 60+40+8` (line 194). Terms of 1024 bytes or more are rejected (OnDiskIndexBuilder.java:128, PerSSTableIndexWriter.java:~217).
2. After the add, if `estimatedMemoryUse() >= maxMemorySize` the segment is submitted for a background flush and a fresh builder starts (PerSSTableIndexWriter.java:247-249, 253-).
3. The flush calls `OnDiskIndexBuilder.finish(File)` (OnDiskIndexBuilder.java:245-262). For a UTF8Type/AsciiType column in `Mode.CONTAINS` it builds `SuffixSA`; otherwise `IntegralSA`. `SA.add` accumulates `charCount += term.length()` (SA.java:52).
4. `SuffixSA.SASuffixIterator` allocates `new long[charCount]` (SuffixSA.java:64), one slot per character of every term (all suffixes), and sorts it with `LongTimSort.sort` (SuffixSA.java:84). `CharTerm` also holds a decoded `CharBuffer` (2 bytes/char) per term (SuffixSA.java:41).
5. During merges, `ensureCapacity(len1)` / `ensureCapacity(len2)` (LongTimSort.java:607, 715) allocate `tmp`. Outcomes at line 821: if `tmp` is big enough nothing is allocated; otherwise a fresh `long[newSize]` replaces it (835-836), old one becomes garbage. The sum of live memory is up to `8*n` (suffixes) + `8*min(pow2, n/2)` (tmp) bytes, plus garbage of earlier smaller `tmp` arrays.
6. Bypass/overshoot: none of steps 3-5 is charged against the limit. Also the check happens only after an add, so a segment overshoots by at most one term. A term is at most 1023 chars, so each distinct term contributes up to 1023 suffix slots, while the estimate charges it about `220 + L` bytes.

**A4. Other consumers.**
Memtable and row cache, key cache, chunk cache, compaction buffers, the other SASI concurrent segments (flush executor runs several `finish` calls in parallel, `getExecutor()` in PerSSTableIndexWriter), `OnDiskIndexBuilder` data/pointer-level blocks and the written index file (disk), the `Term` objects held in `SA.terms`.

**A5. Evidence beyond the source.** none (conclusion derived from source only; stage 4 should confirm).

## B. Verification solution

**B1. Claim under test.**
The heap used while building a SASI CONTAINS-mode index segment does not follow `max_compaction_flush_memory_in_mb`: with the option at M MiB, the peak extra heap during `SuffixSA` construction and sort is several times M (about `8n + up to 4n + 2n` bytes for n characters, with n much larger than M/1 byte) even though `estimatedMemoryUse()` stays just under M MiB. Equivalent unit claim: `LongTimSort` allocations scale with `a.length` (tmp up to `4*a.length` bytes), and are independent of the estimate.

### B2. Unit tier

**B2a. Environment and build.**
JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ /local/$USER/c509/`), build there only: `cd /local/$USER/c509 && ant jar` (or `ant build-test`). Put the test source at `/local/$USER/c509/test/unit/org/apache/cassandra/index/sasi/disk/SasiSuffixMemoryTest.java` (in the copy, never the shared tree). Run: `ant testsome -Dtest.name=org.apache.cassandra.index.sasi.disk.SasiSuffixMemoryTest -Dtest.jvm.args="-Xmx6g"`. **[Amended 2026-10-26, B5.6: `ant testsome` is used for the instrument check only; the readings run the same compiled class with `java ... org.junit.runner.JUnitCore` (one JVM per cell, Byteman agent attached), because each cell needs its own heap size and agent and the cells run in parallel.]** JVM options: `-Xmx6g -XX:+UseG1GC`; allocation counting via `com.sun.management.ThreadMXBean#getThreadAllocatedBytes` (enable `isThreadAllocatedMemoryEnabled`).

**B2b. Knobs.**
- Part 1 (the target): array length n in {2^16, 2^20, 2^23} and input shape (random keys, sorted-with-runs, descending); fixed comparator `Long::compare`.
- Part 2 (the constraint): number of distinct terms N and term length L in {16, 256, 1000} characters, with the limit M in {8, 32, 128} MiB used to derive N = floor(M*2^20 / (220 + L)) (one key per term). Set in the test by constructing `OnDiskIndexBuilder(Int32Type/UTF8Type key comparator, UTF8Type, Mode.CONTAINS)` and calling `add` until `estimatedMemoryUse() >= M<<20`, mirroring PerSSTableIndexWriter.java:247. **[Amended 2026-10-26, B5.9: grid reduced for disk (B5.9): L=16 and L=64 with M in {8, 32, 128}; L=256 and L=1000 with M in {8, 32}; each CONTAINS cell has a PREFIX control cell with the same terms; PREFIX also runs at M=128 for L=256 and L=1000.]**

**B2c. Workload.**
Part 1: `long[] a` filled with random values; `LongTimSort.sort(a, Long::compare)`. Part 2: distinct random ASCII terms of length L, each added with a `DecoratedKey` from `Murmur3Partitioner` and position counter; stop at the estimate crossing M; then call `builder.finish(tmpFile)` once on local temp storage (e.g. `/local/$USER/sasi-unit/`). Arithmetic: L=1000, M=32 → N = 33554432/1220 = 27,502 terms, n = charCount = 27.5M, suffix array = 220 MB, tmp up to ≈ 110 MB (n/2 longs max is 13.75M longs = 110 MB), char buffers 55 MB; ≈ 385 MB vs 32 MB limit (≈12x). **[Amended 2026-10-26, B5.9: the index file of a CONTAINS build holds every suffix as its own term with its own token-tree entry, about L/2 + 130 bytes per suffix and so per character (measured per character in the instrument check, L=100: 59,390,100 bytes for 327,700 characters). Disk per cell = N*L*(L/2+130): L=1000, M=32 is 17 GB, M=128 is 69 GB (not run). The cells run on tmpfs one build at a time per JVM; at most 3 JVMs at once; the file is deleted at the end of the cell.]**

**B2d. Observables and instruments.**
- `estimatedMemoryUse()` at stop (the check's own operand).
- `charCount` via reflection on `SA`, or computed as N*L.
- Bytes allocated by the thread across `finish()` and across `LongTimSort.sort` (`getThreadAllocatedBytes` before/after). This is cumulative allocation, so garbage from tmp growth is included; the sum of the geometric tmp sequence is at most about 2x the final tmp. **[Amended 2026-10-26, B5.1: this counter is recorded but not judged. The sort comparator encodes two suffixes per comparison (`SuffixSA.java:84-88`, `CharTerm.getSuffix`), so cumulative allocation is dominated by short-lived comparator garbage, expected to be hundreds to thousands of bytes per character at every L, and says nothing about retained memory. The usage measures are the exact array sizes (Byteman trace of `LongTimSort`: every `tmp` write and every `sort` entry/exit, B5.2) and the peak live heap (full-GC class-histogram total, sampled while `finish()` runs, as an increment over the total taken just before `finish()`).]**
- Peak live size: JFR with `-XX:StartFlightRecording` events `jdk.ObjectAllocationOutsideTLAB` listing every `long[]` size (suffixes and each tmp); the largest `long[]` sizes are exactly suffix array and final tmp. **[Amended 2026-10-26, B5.2: the array sizes come from the Byteman trace (exact, no TLAB threshold); JFR is not used.]**
- Not observable directly: `tmp` field (private, instance not exposed); infer from JFR allocation sizes.

**B2e. Procedure.**
1. Copy tree, build, add test (B2a).
2. Part 1: for each n and shape run sort 3 times, record allocated bytes and JFR `long[]` sizes.
3. Part 2: for each (M, L) build the builder to the estimate crossing, record `estimatedMemoryUse()` and N, charCount; run `finish()`, record allocated bytes and `long[]` sizes.
4. Control run (B2h) with `Mode.PREFIX` and same terms.
5. Delete temp files, verify no java process remains (`pgrep -u $USER java`).

**B2f. Predictions.** (stated before any run)
- Part 1: largest tmp allocation ≤ `8*(n/2)` bytes always (the line-833 cap); for random input it is the smallest power of two above the longest merged run, about `8*n/2` at n=2^23 (≈32 MiB) and ≈ 2 KiB (256 longs) when input is already sorted/ascending (no merge). Total sort allocation for random input between 1x and 2x of that.
- Part 2: `estimatedMemoryUse()` ends in [M MiB, M MiB + 1.3 KiB). The largest `long[]` is `8*charCount` bytes ≈ `8*N*L`. Allocated bytes in `finish()` ≥ `8*N*L` and, for random terms, ≈ `(8 + 4 .. 8 + 8 + 4)*N*L`. Ratio allocated/limit ≈ 7 to 12 for L=1000, ≈ 1 for L=16 (L small: per-term overhead dominates, 220+16). The ratio rises with L, at fixed M. **[Amended 2026-10-26, B5.1: the cumulative-allocation numbers in this bullet are not predictions of the run (see B2d). Predictions that are judged: (a) the first `LongTimSort.sort` call of `finish()` has `a.length` = `charCount` = N*L, so the suffix array is exactly `8*N*L` bytes; (b) the peak live heap increment over `finish()` (histogram total, increment over the total just before `finish()`) is at least `8*N*L` and about `10 to 14` bytes per character (suffix array 8, final tmp 0 to 4, decoded `char[]` 2), plus about 130 bytes per distinct term (the `CharTerm`, its `CharBuffer` and the term list slot): ratio increment/limit about 7 to 12 for L=1000, about 1 to 2 for L=16, rising with L at fixed M.]**
- Control (PREFIX): no `long[]` larger than a few KiB; allocation in finish roughly proportional to N (not N*L) and below ~3x M. **[Amended 2026-10-26, B5.1: read "allocation" as the peak live increment over `finish()`; no `LongTimSort` call at all in PREFIX mode.]**

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Biggest `long[]` ≈ `8*N*L` and peak live increment over `finish()` at least 3x M at L=1000, growing with L at fixed M **[Amended 2026-10-26, B5.1: "total finish allocation" replaced by the peak live increment; "several" made numeric (3x, the PREFIX control's ceiling)]** | Claim confirmed: usage not governed by the knob |
| Peak live increment per M flat across L (stays ≲ 1.5x M), no `long[]` ≈ `8*charCount` **[Amended 2026-10-26, B5.1: "allocation" replaced by the peak live increment]** | Claim refuted: the estimate does follow real usage |
| tmp > `4*a.length` bytes in Part 1 | Cap at line 833 not working; trace wrong |
| tmp ≈ 2 KiB on sorted input but ≈ `4*n` on random input | Positive control: the `tmp` cap/shape binds as traced; the sort buffer scales with array size |
| PREFIX control peak live increment ≲ 3x M and not growing with L **[Amended 2026-10-26, B5.1: "allocation" replaced by the peak live increment]** | Positive control: where the estimate describes the structure it tracks usage |
| Estimate never reached, or finish not executed (e.g. empty terms) | Not confirmed |

**B2h. Controls.**
(a) Same terms in `Mode.PREFIX` (IntegralSA, no suffix array), so the only difference is the SuffixSA path. (b) Vary L at fixed M to separate per-character from per-term cost. (c) Vary n and input shape in Part 1 to show the `a.length>>>1` cap does bind. (d) Repeat each run 3 times after a warm-up; call `System.gc()` before taking baseline allocation. **[Amended 2026-10-26, B5.4: repeats by size. A suffix sort of n characters costs about n*log2(n) comparisons of two allocating suffix encodings, so the cells with n above 20 million run once; the others 3 times. Sizes in B5.4.]**

### B3. Cluster tier

**B3a. Environment and build.**
One node (second optional) built from a local copy on local disk: `cd /local/$USER/c509 && ant jar`; run from `bin/cassandra -f` with data, commitlog, hints, saved_caches under `/local/$USER/node1/` (size known, ≥ 20 GB free checked with `df`). `cassandra.yaml`: `sasi_indexes_enabled: true`, `num_tokens: 1`, `concurrent_compactors: 1`, `compaction_throughput: 0`, `memtable_heap_space: 512MiB`, `memtable_allocation_type: heap_buffers`. JVM (`conf/jvm11-server.options`/`JVM_EXTRA_OPTS`): `-Xms2g -Xmx2g -XX:+UseG1GC -Xlog:gc*:file=/local/$USER/node1/gc.log:time -XX:StartFlightRecording=filename=/local/$USER/node1/rec.jfr,settings=profile`. A separate run with `-Xmx` lowered stepwise (1g, 768m, 512m) is used as an OOM probe. **[Amended 2026-10-26, B5.3: the main arms run with `-Xms8g -Xmx8g` (not 2g: the SASI general pool builds up to 8 segments at once, so M=16 and M=64 do not fit in 2 GiB); the OOM probe uses M=64 at `-Xmx` 2g and lower. JFR is replaced by a Byteman trace of `LongTimSort` (B5.2). Node data on tmpfs (`/dev/shm`) because the node is shared and the local disk is small; the node runs from a copy-source.sh tree.]**

**B3b. Knobs.**
`max_compaction_flush_memory_in_mb` in {4, 16, 64} MiB set at index creation (recreate the index for each value, with a fresh table). Fixed: `mode: 'CONTAINS'`, text column of ~1000-char distinct values. Choice of values: the estimate for 1000-char values is ≈1220 B/term, so M=16 → ~13,750 terms → 13.75M suffix slots (110 MB suffixes + up to 55 MB tmp + 27 MB chars) which fits a 2 GB heap but is ~10x M; M=64 → ~4x larger, still under 2 GB with other loads yet close to a humongous-allocation limit, which makes any overshoot visible as GC/OOM. **[Amended 2026-10-26, B5.9: values are M in {2, 8, 32} MiB plus the default (unset, 153.6 MiB), text column of 200-character distinct values. Reason: the index file is about L/2 + 130 bytes per suffix (B5.9), so with 1000-character values M=16 alone would write about 130 GB; with 200 characters 200,000 rows give about 9 GB of segment files (and the same again for the combined file).]**

**B3c. Workload.**
Schema: `CREATE KEYSPACE k WITH replication={'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE k.t (id bigint PRIMARY KEY, v text); CREATE CUSTOM INDEX t_v ON k.t (v) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode':'CONTAINS','max_compaction_flush_memory_in_mb':'16'};`. Load 200,000 rows with distinct random ASCII `v` of 1000 chars (200 MB of values) via `cassandra-stress` user profile or a small driver script, flushing every ~25,000 rows (`nodetool flush k t`), giving 8 sstables each below the 1 GiB flush limit. Then `nodetool compact k t`: the compaction uses the option (PerSSTableIndexWriter.java:367). Arithmetic: 200,000 terms * 1220 B = 244 MB estimate total, so M=16 gives ≈ 15 segments of ≈13,750 terms; each segment's `finish` makes a 110 MB `long[]`. Duration: load ≈ minutes, compaction ≈ a few minutes. Repeat per M. **[Amended 2026-10-26, B5.9: values are 200 characters (not 1000), `max_compaction_flush_memory_in_mb` takes the values of B3b, and the other arms are: PREFIX at M=8 and M=32 (control), CONTAINS at M=8 with 50-character values (B3h(b)), a table with no index (B3h(c)), and an OOM probe (M=32 at low heap). Load 200,000 rows, flush every 25,000 rows. Terms per segment = ceil(M*2^20 / 420) (420 = 64+48+200+108): M=2: 4,994, M=8: 19,973, M=32: 79,892 (arithmetic corrected the same day, before any reading: 4,993 and 19,972 were rounded wrongly; the counts below do not change); so cuts 40, 10, 2 and segments (cuts + the tail built by `complete()`) 41, 11, 3; default: 0 cuts, 1 segment (the whole 200,000 terms, 84 MB of estimate is under 153.6 MiB).]**

**B3d. Observables and instruments.**
- Heap in use, sampled every 200 ms during compaction: `jstat -gc <pid> 200` (and G1 humongous regions via `-Xlog:gc+heap`), and `jcmd <pid> GC.heap_info`.
- Largest array allocations: JFR `jdk.ObjectAllocationOutsideTLAB` / `jdk.ObjectAllocationSample` filtered for `long[]` (`jfr print --events ObjectAllocationOutsideTLAB rec.jfr`).
- Segment count and flush log lines (`system.log`, "Flushed ... segment"/builder logs), SASI index file sizes on disk (`ls -l .../SI_t_v*`) for the disk side.
- Not directly observable: the estimate's value at flush time (derive from the number of segments); the `tmp` array itself (seen only through JFR sizes).

**B3e. Procedure.**
1. Build and configure as in B3a; start the node; `nodetool status` to confirm.
2. Create schema (M value), load data in batches, `nodetool flush` between batches.
3. Start `jstat -gc` and begin `nodetool compact k t`; wait until done.
4. Dump JFR (`jcmd <pid> JFR.dump filename=...`), stop the node (`nodetool drain; kill`), collect `gc.log`.
5. Repeat for the other M values and the PREFIX control; for the OOM probe, run M=64 with `-Xmx` stepped down.
6. Cleanup (B4).

**B3f. Predictions.**
- Peak heap increment during compaction minus heap before compaction ≈ `suffixes + tmp + chars + estimate-structure` for one segment (parallel segments add up if executor runs several). For L=1000: M=4 → ~35 MB, M=16 → ~145-185 MB, M=64 → ~580-740 MB (about 9x-12x M). **[Amended 2026-10-26, B5.3: the SASI general pool has 8 threads (`PerSSTableIndexWriter.java:63-69`), and the compaction thread submits segments faster than they are sorted, so up to min(8, segments) segments are in flight. The figures above are the single-segment values and a lower bound for the peak; the peak live increment (histogram samples) is between one and min(8, segments) times them. "Live" is the full-GC class-histogram total.]** **[Amended 2026-10-26, B5.9: for 200-character values: one segment is n = terms*200 characters at 10 to 14 bytes: M=2: n=1.0 M, 10-14 MB (5-7x M); M=8: n=4.0 M, 40-56 MB; M=32: n=16.0 M, 160-224 MB; default: n=40 M, 400-560 MB (about 3.8x the 84 MB estimate, no cut). Peak live increment is between one and min(8, segments) times the single-segment figure.]**
- The largest `long[]` in JFR ≈ `8 * 4*1048576*... = 8 * (M*2^20/1220)*1000`: M=4 → ~27 MB, M=16 → ~110 MB, M=64 → ~440 MB. **[Amended 2026-10-26, B5.9: exact value from the Byteman trace (`sort` entry from the compaction): `8*n` bytes with n = terms*200: M=2: 8.0 MB (n=998,800), M=8: 32.0 MB (n=3,994,600), M=32: 127.8 MB (n=15,978,400); default: 320 MB (n=40,000,000). The segment tails are smaller.]**
- Number of segments ≈ 244 MB / M (M=4: ~60, M=16: ~15, M=64: ~4), i.e. the knob does govern segment *count* and thus the order of the size, but the memory per segment is ~10x M. **[Amended 2026-10-26, B5.9: segments (flush lines "Flushed index segment" count the tail too) = 41 (M=2), 11 (M=8), 3 (M=32), 1 (default; the all-in-memory path logs nothing, see the closed sasi-max_compaction case), per B3c.]**
- OOM probe: with M=64 and `-Xmx` ≲ 768m, `Failed to build index segment` or OutOfMemoryError appears although the "limit" is 64 MB. **[Amended 2026-10-26, B5.9: the probe is M=32 with `-Xmx` 512m (single segment 160-224 MB, up to 3 in flight); then 384m if it passed.]**
- PREFIX control: peak increment ≲ 2-3x M. **[Amended 2026-10-26, B5.9: PREFIX at M=8 and M=32; no `long[]` of `8*n`.]**

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Peak heap increment ≈ 9-12x M for CONTAINS, growing linearly in M, and `long[]` of ≈ `8*charCount` **[Amended 2026-10-26, B5.3: read as: peak live increment at least 3x M at M=8 and M=32 [B5.9: values 2/8/32], rising with M (the single-segment 9-12x is a lower bound, segments overlap; samples are coarse), and a `long[]` of exactly `8*charCount`]** | Claim confirmed: the real heap does not follow the limit |
| Peak increment ≲ 1.5x M for CONTAINS | Claim refuted: the estimate follows actual usage |
| PREFIX control increment ≲ 3x M and no large `long[]` | Positive control: same workload where the estimate describes the data; it tracks |
| Segment count falls with larger M, per the 41/11/3/1 prediction (B5.9) | Control: the limit is read and does cause flushes (so a failing cap is not caused by the option being ignored) |
| Index never builds (no compaction output, or option not applied; log shows 1 GiB limit or `above 100GiB` reset) | Not confirmed: reach not achieved |
| Node dies of OutOfMemoryError or a segment fails (`Failed to build index segment`) in a main arm at 8 GiB **[Added 2026-10-26, B5.3]** | Not confirmed for that arm (no reading of the peak); the failure itself shows heap use far above M, recorded as such |
| Heap increment constant across M while the control moves | Claim confirmed in the other direction (neither tracks); investigate |

**B3h. Controls.**
(a) PREFIX-mode index on the same data. (b) Same data with 100-char values (L small) to show the ratio drops (estimate per-term constant dominates). (c) A run with no SASI index but same compaction, to subtract baseline heap. (d) Force a full GC (`jcmd <pid> GC.run`) just before compaction to set a clean baseline. (e) One compactor only so segments are built one at a time per executor config; record the executor's concurrency. **[Amended 2026-10-26, B5.3: `concurrent_compactors: 1` does not serialize segment builds (the SASI general pool is 8 threads). The concurrency is recorded from the Byteman trace (`sort` entry and exit times per thread).]**

**B4. Risks and cleanup.**
Disk: ≈ 200 MB values per run x a few copies plus SASI files; all under `/local/$USER/` (known size, checked with `df`); never use shared storage or the shared source tree. Heap: OOM is an expected, safe outcome for the probe, only for the node's own JVM. Processes: record PIDs; `nodetool drain`, `kill <pid>`, then `pgrep -u $USER -f 'CassandraDaemon|jstat|jcmd'` must be empty; delete `/local/$USER/node1`, `/local/$USER/sasi-unit`, JFR files after copying logs. Do not touch the cluster other than the nodes designated for the run. **[Amended 2026-10-26, B5.9: segment files are about N*L*(L/2+130) bytes per arm: 200,000 rows of 200 characters, about 9 GB of segment files plus about 9 GB for the combined file at the end, on tmpfs (`/dev/shm`, 126 GB, shared; each arm drops its keyspace); unit cells up to 17 GB each, at most 3 JVMs at once.]**

### B5. Step-0 audit amendments (stage 4, 2026-10-26; reasons independent of any reading)

1. **Cumulative allocation is not a usage measure** (B2d, B2f, B2g, B2h). `SuffixSA.java:84-88` calls `CharTerm.getSuffix` twice per comparison and that does `Charsets.UTF_8.encode(value.subSequence(...))`, a new `CharBuffer` view, encoder state and `ByteBuffer` of the suffix length. A sort of n characters makes about n*log2(n) comparisons, so `getThreadAllocatedBytes` over `finish()` is expected to be hundreds to thousands of bytes per character at every L and every M: it would satisfy row 1 for L=16 as well as L=1000 and could not tell the rows apart. The judged quantity becomes the peak live heap increment (and exact array sizes).
2. **Instruments**: a Byteman trace on `LongTimSort` (`sort` entry/exit with thread and `a.length`; every write of `tmp` with `tmp.length` and `a.length`) replaces JFR. The suffix array is the `a` of the `sort` call made from `SASuffixIterator` (its length is `charCount`); the tmp sequence is the exact `ensureCapacity` growth. Live heap: `GC.class_histogram` total (full GC; `jcmd` on the node, the `DiagnosticCommand` MBean inside the unit JVM), sampled about every 2 s, as an increment over the total taken just before `finish()` / compaction.
3. **Concurrency**: see B3f and B3h(e). The cluster peak is not one segment but up to min(8, segments).
4. **Workload sizes.** Unit Part 2: N = floor(M*2^20 / (220+L)) distinct terms; n = N*L characters. M in {8, 32, 128} MiB, L in {16, 256, 1000}: n = 0.6, 2.3, 9.1 M (L=16), 4.5, 18, 72 M (L=256), 6.9, 27.5, 110 M (L=1000). Cells above 20 M characters run once (they cost minutes: 110 M characters is about 3 billion comparisons); the others 3 times. A cell that takes more than 45 minutes is stopped and recorded as not run. Cluster: 200,000 rows of 1000 characters as in B3c (the flush of each 25,000-row memtable also builds a CONTAINS segment, with the 1 GiB flush limit: one segment of 25 M characters per flush, so the load phase is also heavy; the baseline for compaction is taken after the `SASI-Memtable` pool is idle and a full GC).
5. **Positive control.** The negative claim needs a case where the estimate does bind the same resource: the PREFIX arms (IntegralSA, same data, same cap, same segment cuts) and the closed `sasi-max_compaction_flush_memory-PerSSTableIndexWriter-estimatedMemoryUse--autonomous` case (Confirmed, true positive: live bytes ordered by the cap in PREFIX mode). Audit rating: Met.
6. **Runner.** See B2a: `ant testsome` for the instrument check, `JUnitCore` for the readings.
7. **Default arm** (161 MB, `max_compaction_flush_memory_in_mb` unset): not in B3b's value list; 200,000 rows give one cut (132,000 terms, 132 M characters, about 1.9 GiB of arrays, about 25 minutes of sort). It runs as the last cluster arm if time allows; its absence is recorded, not a reason for Not confirmed.
8. Stale text: `IndexMode.java:60` and `:192` say "1G default" but the default is 0.15 GiB (161,061,273 bytes). Left for stage 3.
9. **Disk size of a CONTAINS index** (found by the instrument check, then confirmed from the source: `SuffixSA` feeds every suffix of every term to `OnDiskIndexBuilder` as a term, each with its token-tree entry). About L/2 + 130 bytes per character of input. The stage-3 workload (1000-character values, 16 MiB) writes about 130 GB of segment files; no node here can hold it. Amended: unit grid (B2b), cluster values M in {2, 8, 32} and default, 200-character values (B3b, B3c), predictions recomputed (B3f, B3g); the comparator-garbage and concurrency amendments (B5.1 to B5.4) stand. The first freeze hash written before this amendment (`a85fe3a5...` / `f9e955d3...`) was superseded before any reading; only two small instrument-check runs (M=1 MiB, L=100) and a 4-cell Part 1 check existed.
10. **Load phase of the cluster tier.** The SASI memtable index of a CONTAINS column is counted in the memtable's heap use (about 140 KB per 200-character row in the instrument check), so with `memtable_heap_space: 512MiB` the memtable flushes at `MEMTABLE_LIMIT` about every 1,200 rows, not every 25,000 (B3c). The compaction input is therefore many small sstables (about 160) instead of 8; the compaction output is still one sstable that the SASI writer sees as one stream of 200,000 rows, which is what the segment arithmetic needs. The flush-time segments are far below the 1 GiB flush limit (one segment per flush). The harness still calls `nodetool flush` after every 25,000 rows, and waits until the number of memtable index builds equals the number of sstables before taking the baseline.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/LongTimSort.java (lines 57-160, 600-860)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/sa/SuffixSA.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/sa/SA.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java (parts)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java (parts)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/conf/IndexMode.java (parts)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java (grep of `sasi_indexes_enabled`)

## D. Stage-4 feedback

2026-10-26, stage 4 (results: `stage4-runtime-verification/results/sasi-compaction-flush-memory-ensurecapacity-tmp--autonomous.md`; harness `stage4-runtime-verification/harness/sasi-compaction-flush-memory-ensurecapacity-tmp--autonomous/`; commits: not committed by the stage-4 agent, the orchestrator commits).
- **Unit: Confirmed (B2g row 1) - does not cap.** In every CONTAINS build the sorted array has exactly N*L elements (suffix array `8*N*L` bytes), `tmp` reaches exactly `a.length>>>1` longs for random input and stays at 256 longs (2 KiB) for sorted input; the live heap increment over `finish()` is 1.3 x M at L=16, 3.1-3.5 x M at L=64, 7.7 x M at L=256 and 11.6 x M at L=1000 for the same limit. PREFIX: no sort at all.
- **Cluster: Confirmed (B3g row 1) - does not cap.** 200,000 rows of 200 characters: segment counts 41/11/3 for M=2/8/32 and none for the default, arrays exactly `8*n`; peak live increment 184, 558, 604 and 664 MiB (M=2, 8, 32, default), up to 8 segments at once; PREFIX 1.43 x M; with M=32 a node with a 512 MiB heap died of OutOfMemoryError.
- **Outcome class: true negative** (estimate negative, effect does not cap).
- **Amendments made at the audit (B5.1-B5.10, before any reading):** cumulative allocation replaced by live increment and exact array sizes (the comparator allocates two buffers per comparison); SASI pool of 8 threads (heap 8 GiB, peak = up to min(8, segments) segments); index file about L/2 + 130 bytes per character, so cluster values are 200 characters and M in {2, 8, 32} plus default, the unit grid was reduced; memtable-limit flushes during load; rounding slips (4,994 and 19,973 terms per segment).
- **Notes for stage 3:** the peak increment is not proportional to M in the cluster (it saturates at the pool width); `IndexMode.java:60,:192` say "1G default", the real default is 0.15 GiB.
