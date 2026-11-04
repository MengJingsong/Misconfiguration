# BACKTRACK_INITIAL_SIZE (cursor backtrack array) — verification solution

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/tries/InMemoryReadTrie.java:501` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (Claude Code agent), 2026-10-25 |
| Estimate | `negative`. Line 501 is the doubling check of a per-cursor scratch `int[]`; the constant behind it (`BACKTRACK_INITIAL_SIZE = 16`) is only an initial size, not a cap. The array is bounded by trie depth, not by any limit, and it is not part of memtable accounting. |
| Ground | The only "limit" at this line is the array's current length, and exceeding it makes the array double (line 502), so it never refuses or evicts anything. Its worst-case size is set by the key byte length, itself capped by the 65535-byte key limit (`FBUtilities.MAX_UNSIGNED_SHORT`), so it is at most a few hundred KB per cursor. It is transient on-heap garbage that `memtable_heap_space` / `memtable_offheap_space` never see (`InMemoryTrie.sizeOnHeap()` / `sizeOffHeap()` count only buffers and content arrays). |

## A. Constraint trace

**A1. The constraint.**
- Names: `CursorBacktrackingState.BACKTRACK_INITIAL_SIZE` (`InMemoryReadTrie.java:495`) and `BACKTRACK_INTS_PER_ENTRY` (`:494`).
- Kind: compile-time constants in a private static nested class.
- Declared at `InMemoryReadTrie.java:494-495`.
- Unit: entries (16) and ints per entry (3). The initial array is `new int[16 * 3]` = 48 ints = 192 bytes of data (`:496`).
- Default: hard-coded, no derivation.
- How to set: not settable (no yaml key, no `-D`, no JMX). Changing it needs a source edit and a rebuild.
- The runtime value that line 501 compares is `backtrackDepth * 3` against `backtrack.length`. It is not a configuration entry.
- Related real limits, none declared here:
  - The 64 KiB key limit (`FBUtilities.java:158`, enforced at `QueryProcessor.java:259`).
  - The 2 GB trie size cap (`InMemoryTrie.java:91`, buffers up to 1G, `SpaceExhaustedException`).
  - The memtable limits `memtable_heap_space` and `memtable_offheap_space` (`conf/cassandra.yaml:797-799`), plus `memtable_allocation_type` (`:825`).

**A2. What it caps.**
- Nothing is capped. The array is on-heap, per `MemtableCursor`.
- The quantity compared at `:501` is the `int[]` slot count in use against `backtrack.length`. It decides when to grow, not when to refuse.

**A3. Mechanism.**
- `MemtableCursor` extends `CursorBacktrackingState` (`:540`). Its constructor calls `descendInto(root, -1)` (`:549`).
- `addBacktrack` (`:499`) is called from only two places:
  - `nextValidSparseTransition`, at `:764`, when the order word still has remaining transitions.
  - `maybeAddSplitBacktrack`, at `:750`, when a later non-null sibling exists at a split sub-level.
- Chain nodes add no backtracking (`:772-783`).
- If `backtrackDepth*3 >= backtrack.length` (`:501`), then `backtrack = Arrays.copyOf(..., length*2)` (`:502`). The entry is then written at `:503-506`. The check always succeeds, so there is no rejection path.
- `backtrack()` (`:609-616`) pops one entry per call.
- Growth bound:
  - One entry is live per branching ancestor of the current position that still has unvisited siblings.
  - A sparse node contributes at most 1 entry per depth.
  - A split node contributes up to 3 (one per sub-level), and the 3 split sub-levels are crossed within a single trie depth step (`descendInSplitSublevel`, `:660-691`).
  - `backtrackDepth` is therefore at most about 3 * trie depth, and trie depth equals byte-comparable key length. Doubling reaches a power-of-two multiple of 48 ints.
- Bypass or overshoot:
  - The array never shrinks (no code resets it) and lives as long as the cursor.
  - Doubling can overshoot actual need by up to 2x.

**A4. Other consumers.**
- The trie's real storage is `UnsafeBuffer[] buffers` and `contentArrays` (`InMemoryReadTrie.java:218-219`), which is what `sizeOnHeap` / `sizeOffHeap` report (`InMemoryTrie.java:969-980`).
- `TrieMemtable` charges only `data.sizeOnHeap()` deltas to the allocator (`TrieMemtable.java:477,485`). Cursor scratch arrays are never charged.
- Other consumers on the same heap:
  - The `BTreePartitionData` content objects.
  - Merge and slice cursors (`Trie.mergeDistinct`, `subtrie`, `TrieMemtable.java:148,298,352`), each of which wraps its own cursors.
  - Each concurrent read, scan or flush creates fresh cursors.

**A5. Evidence beyond the source.** none (the in-tree class comment at `InMemoryReadTrie.java:525-539` describes the backtracking design).

## B. Verification solution

**B1. Claim under test.**
- Claim: the cursor backtrack array's size does not follow any configured cap.
- It is driven by trie shape and depth alone (at most about 3 ints per branching level, doubling from 48 ints).
- It is independent of `memtable_heap_space`, `memtable_offheap_space` and the trie's accounted size.
- It stays small relative to the trie data.
- The claim is refuted if the backtrack array length grows with the memtable space limits, or if it is counted in `sizeOnHeap()`.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 11, Ant. Copy the tag to local disk (for example `rsync -a /users/jason92/cassandra-5.0.9/ /tmp/c509/`) and build only there: `cd /tmp/c509 && ant jar`.
- Put the test in package `org.apache.cassandra.db.tries`, for example `test/unit/org/apache/cassandra/db/tries/BacktrackSizeTest.java`. Same package as `InMemoryReadTrie`, so package-private members are visible.
- Run with `ant testsome -Dtest.name=BacktrackSizeTest`. Add `-Dtest.jvm.args="-Xmx512m"` to make heap effects visible.
- The test reads the private `backtrack` field of `CursorBacktrackingState` by reflection (`getDeclaredField("backtrack")` on `MemtableCursor.class.getSuperclass()`, `setAccessible(true)`), and `backtrackDepth` directly.

**B2b. Knobs.**
- Trie shape knob 1, `branching`: how many sibling children are present at each level.
  - Sparse shape: 2-6 children per node.
  - Split shape: 7 or more children per node.
  - Chain shape: 1 child per node, a control with no entries expected.
- Trie shape knob 2, `depth`: key length in bytes, in the values 8, 64, 1024 and 65535 (the key-size maximum).
- Memory-limit knob (the supposed constraint): `BufferType.ON_HEAP` vs `OFF_HEAP`. The unit tier has no yaml, so this is the nearest in-process analogue.
- Where each is set: in the test code, through the `InMemoryTrie(BufferType)` constructor (`InMemoryTrie.java:88`) and the keys inserted. Insert with `putSingleton` or `apply`; use `ByteComparable.fixedLength(byte[])`.

**B2c. Workload.**
- Worst case for backtracking: at every depth `d` in `[0, D)`, the path node has two children, the visited one and a later one. This is a comb: keys `k_d = prefix(d bytes of 0x00) + 0x01`, plus the final key `0x00 * D`.
- Total number of keys is D + 1.
- A depth-first cursor walk that follows the 0x00 branch first then keeps one pending sibling per level, so `backtrackDepth` reaches D at the bottom.
- Expected maximum entries is D (sparse, 1 per level). The split variant uses 7+ siblings arranged to cross sub-levels, giving up to about 3D.
- Arithmetic:
  - For D = 64 the array needs 192 ints (the initial is 48), so doubling occurs twice (48 -> 96 -> 192).
  - For D = 1024 it needs 3072 ints = 12 KiB.
  - For D = 65535, 196605 ints (about 786 KB), rounded up by doubling to 49152 * 4 ints, about 0.8 MB.
- A key of 65535 bytes is the maximum a client can send (`QueryProcessor.java:259`), so this is the upper bound for the partition-key part.

**B2d. Observables and instruments.**
- `backtrack.length` and `backtrackDepth` after a complete cursor walk (`while (c.advance() >= 0)`), recording the maximum over the walk.
- `trie.sizeOnHeap()` and `trie.sizeOffHeap()` (public, `InMemoryTrie.java:969,975`).
- Heap delta, measured by `ObjectSizes.measureDeep(cursor)`.
- Cannot be observed directly: allocation of intermediate arrays (garbage). Count growth events via the sequence of lengths.

**B2e. Procedure.**
1. Build the tree in `/tmp/c509`.
2. For each (shape, D, bufferType), create the trie and insert the comb keys.
3. Create a `trie.cursor()`, record `backtrack.length` (expected 48), then walk to the end tracking `max(backtrackDepth)` and the final `backtrack.length`.
4. Record `trie.sizeOnHeap()` before and after creating and walking the cursor; the difference should be 0.
5. Repeat with ON_HEAP and OFF_HEAP.
6. Control run with a chain-only trie (a single key of length D): expect `backtrackDepth` stays 0 and the length stays 48.
7. Positive control (a cap that binds): in the same JVM, insert keys until `SpaceExhaustedException` or until `reachedAllocatedSizeThreshold` (see `InMemoryTrie`) trips, showing that the trie buffers do have a bound that tracks `allocatedPos`, unlike the backtrack array.

**B2f. Predictions.** (stated before any run)
- Chain-only: `max backtrackDepth` = 0, `backtrack.length` = 48.
- Sparse comb with D = 8: `max backtrackDepth` about 8 (at most 16 by the entry rule), length 48.
- Sparse comb with D = 64: depth about 64, length 192 (after two doublings).
- Sparse comb with D = 1024: about 1024 entries, length 3072 * 2 rounded: 6144 ints at most (the array doubles 48 -> ... -> 3072 or 6144).
- Split comb: `max backtrackDepth` up to about 3D, so about 3x the sparse figure.
- ON_HEAP vs OFF_HEAP: the same `backtrack.length`. `sizeOnHeap()` difference before and after the cursor: 0.
- Relation: `backtrack.length` is at most `2 * 3 * maxEntries`, never related to the buffer size.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `backtrack.length` tracks only shape and depth, same for ON_HEAP and OFF_HEAP; `sizeOnHeap()` unchanged by the cursor | Claim confirmed: the array is not tied to a memory cap and is unaccounted |
| `backtrack.length` changes with the buffer type or with trie byte size at fixed shape | Claim refuted: usage follows the memory configuration |
| `sizeOnHeap()` rises when the cursor grows its array | Claim refuted: the array is accounted |
| Chain-only trie: length stays 48 and depth 0 | Consistent with `:772-783` (no entries for chains) |
| Positive control: trie allocation hits the threshold or `SpaceExhaustedException` while `backtrack.length` stays small | Confirms a binding cap exists elsewhere and this one is not a cap |
| Comb never gets past 48 ints, or the positive control never trips | Not confirmed: the limit was never reached, rerun with larger D or more keys |

**B2h. Controls.**
- The chain-only trie rules out growth without branching.
- ON_HEAP vs OFF_HEAP rules out an effect of the buffer type.
- A fresh cursor vs a reused one confirms the array is per-cursor and never shrinks.
- Run each case twice in fresh JVMs to rule out GC noise in `measureDeep`.

### B2i. Audit amendments (2026-10-25, stage-4 step 0, before the freeze and before any reading)

Audited against `cassandra/cassandra-5.0.9/` (clean; `base.version` 5.0.9). All citations in A and B re-read; they hold (`InMemoryReadTrie.java:494-506, 540, 549, 609-616, 660-691, 750, 764, 772-783`, `InMemoryTrie.java:58-67, 88, 969-980`, `TrieMemtable.java:477, 485, 148, 298, 352`, `FBUtilities.java:158`, `QueryProcessor.java:259`; `InMemoryTrie.java:91` is the comment on the 2 GB limit, the constructor is at :88).

1. **Test class and build.** The class is `org.apache.cassandra.db.tries.BacktrackSizeTest` (the name must end in `Test`); run `ant testsome -Dtest.name=org.apache.cassandra.db.tries.BacktrackSizeTest` in a `copy-source.sh` tree (`~/s4-bt/cassandra`, not `/tmp/c509`). The build is `ant build-test`.
2. **Size measure (defect).** `ObjectSizes.measureDeep(cursor)` (B2d) is invalid: `MemtableCursor` is a non-static inner class, so a deep measure follows `this$0` into the whole trie. The array's size is `16 + 4 * backtrack.length` bytes, with `backtrack.length` and `backtrackDepth` read by reflection on `CursorBacktrackingState`.
3. **Building the combs (defect).** One `putSingleton` per key costs D^2/2 byte steps (2.1e9 at D = 65535). The combs are built by one `InMemoryTrie.apply` of a mutation `Trie` whose cursor generates the comb in O(D) (harness class). The content equals the key set. One arm (sparse, D = 1024) is also built with 1025 `putSingleton` calls and must give the same E and L. Known-answer checks of the generator, before run 1: a plain walk visits exactly as many content nodes as there are keys, and `trie.get` returns content for sample keys.
4. **Exact shapes.** Sparse comb of depth D: keys `0x00^d 0x01` for d = 0..D-1 and the final key `0x00^D`. Split comb: at each spine node (depth d, 0 <= d < D) the children are `0x00` (the spine; at d = D-1 a leaf with content), `0x01`, `0x02`, `0x03`, `0x08`, `0x40`, `0x80` (leaves with content), and the final key is `0x00^D`. Seven children make a split node (`SPARSE_CHILD_COUNT` = 6, `InMemoryReadTrie.java:163`), and the first child has a later sibling at all three sub-levels (top 0 -> 1, mid 0 -> 1, tail 0 -> 1), so 3 entries are added per level. Chain: one key `0x00^D`.
5. **Added arms.**
   (a) Filler: sparse comb D = 64 plus F in {0, 100,000, 1,000,000} random 4-byte keys under the prefix `0x02` (`new Random(7)`), to vary the trie's byte size at a fixed shape (B2g row 2 had no arm for it).
   (b) Fresh vs reused cursor: after a full walk the first cursor keeps its length; a new cursor on the same trie starts at 48.
   (c) Positive control (replaces B2e step 7, which needs a 2 GiB trie): `InMemoryTrie.ALLOCATED_SIZE_THRESHOLD` (`InMemoryTrie.java:58-67`) is a cap that binds on the trie's allocated bytes; it is read once per JVM from the system property `cassandra.memtable.row_overhead_size` in MiB (`CassandraRelevantProperties.java:356`). The harness runs three fresh JVMs with T in {8, 16, 32} MiB (env `STAGE4_THRESHOLD_MIB`, set as a system property in the test class's static initializer before any trie class loads). In each, on an OFF_HEAP trie, `advanceAllocatedPos` to T-1 MiB leaves `reachedAllocatedSizeThreshold()` false, to T MiB makes it true, and `sizeOffHeap()` equals the allocated position; then the sparse D = 1024 comb is added to the same trie. The three JVMs run every other arm too (B2h "twice in fresh JVMs").
6. **Exact predictions (replace the relations in B2f).** E = maximum `backtrackDepth` over the walk, L = final `backtrack.length`. Entry number i is written when `3 * i < L` (`:501`), so L = 48 * 2^k with the smallest k such that E <= 16 * 2^k.

   | Shape | D | E | L (ints) |
   |---|---|---|---|
   | chain | 8, 64, 1024, 65535 | 0 | 48 |
   | sparse | 8 / 64 / 1024 / 65535 | 8 / 64 / 1024 / 65535 | 48 / 192 / 3072 / 196608 |
   | split | 8 / 64 / 1024 / 65535 | 24 / 192 / 3072 / 196605 | 96 / 768 / 12288 / 786432 |
   | sparse D = 64 + filler F = 0, 1e5, 1e6 | 64 | 64 | 192 |
   | sparse D = 1024 built by `putSingleton` | 1024 | 1024 | 3072 |

   A fresh cursor has L = 48 on every trie. Every row is the same for ON_HEAP and OFF_HEAP. `sizeOnHeap()` and `sizeOffHeap()` read before the cursor exists and after the walk are equal (difference 0). The reused cursor keeps its L after the walk. Positive control, per T: `ALLOCATED_SIZE_THRESHOLD` = T * 2^20; flag false at T-1 MiB, true at T MiB; the D = 1024 comb in the same trie still gives L = 3072.
7. **Extra rows for B2g.** (a) Every L and E equals the table, ON_HEAP = OFF_HEAP, L independent of F and of T, sizes unchanged by the cursor, positive-control flags as predicted: **Confirmed, does not cap**. (b) L or E differs from the table but L is still equal for ON_HEAP and OFF_HEAP, independent of F and of T, and the sizes are unchanged: **Confirmed, does not cap**, with the flag "numeric prediction missed". (c) L depends on the buffer type, on F or on T: **Refuted**. (d) The threshold flags do not flip as predicted (control failed): **Not confirmed**. (e) An arm throws or the test cannot run: **Invalid**. (f) Any other reading: **Not confirmed (no matching row)**.

### B3. Cluster tier

**B3a. Environment and build.**
- One node (single-node cluster is enough, since the cursor is per-node and local), JDK 11, built with `cd /tmp/c509 && ant jar` and run from there.
- Local disk of known size for `data_file_directories`, `commitlog_directory`, `hints_directory` and `saved_caches_directory`. Do not use shared storage.
- `conf/cassandra.yaml` changes:
  - `memtable:` `configurations:` `default:` `class_name: TrieMemtable` (see `conf/cassandra.yaml:783-788`) so that the trie memtable is used, or set per table with `memtable = {'class': 'TrieMemtable'}`... (confirm the template at `cassandra.yaml:771-790`).
  - `memtable_allocation_type: offheap_objects` for one run and `heap_buffers` for another (`:825`).
  - `memtable_heap_space: 256MiB` and `memtable_offheap_space: 256MiB` (`:797-799`) for the boundary.
- JVM: `-Xms1g -Xmx1g`, `-XX:+HeapDumpOnOutOfMemoryError` (heap dump to local disk), GC logging with `-Xlog:gc*:file=/tmp/gc.log`.

**B3b. Knobs.**
- `memtable_heap_space`: 64MiB vs 512MiB (a 8x change).
- `memtable_allocation_type`: `heap_buffers` vs `offheap_objects`.
- Workload shape: key length and partition count (below).
- Set through `cassandra.yaml` before start. Both need a restart.

**B3c. Workload.**
- Table: `CREATE TABLE ks.t (pk blob, ck blob, v blob, PRIMARY KEY (pk, ck)) WITH memtable = {'class':'TrieMemtable'}` (use the memtable configuration name as defined in the yaml).
- Writes: 200,000 partitions, `pk` of 1000 bytes (varying early bytes to make branching deep and wide), `ck` of 100 bytes, `v` of 16 bytes. About 250 MB of keys, enough to cross the 64MiB boundary several times.
- A second phase, readers: 16 concurrent clients issue `SELECT * FROM ks.t` range scans (each opens its own merged-cursor stack) for 5 minutes while writes continue, to maximise the number of live cursors.
- Tool: `cassandra-stress` with a user profile, or a short driver script; sizes from the arithmetic above.
- Duration: 10 minutes per configuration.

**B3d. Observables and instruments.**
- Heap histogram of `int[]`: `jcmd <pid> GC.class_histogram`, sampled every 10 s during the scan phase.
- Heap dump at peak (`jcmd <pid> GC.heap_dump /tmp/h.hprof`) to see which `int[]` instances belong to `MemtableCursor` objects (dominator tree in a heap analysis tool).
- Memtable accounting: `nodetool tablestats ks.t` (Memtable data size, off-heap memory used) and the JMX metrics `MemtableOnHeapDataSize` / `MemtableOffHeapDataSize`.
- Process memory: `ps -o rss`, GC log.
- Cannot be observed directly: the individual cursor's `backtrack.length` without a heap dump.

**B3e. Procedure.**
1. Build and start the node with the first configuration.
2. Create the schema and run the write phase.
3. Start the reader phase; sample `jcmd GC.class_histogram | grep '\[I'` every 10 s and `nodetool tablestats`.
4. Take one heap dump at the peak of the scan phase.
5. Stop the load. `nodetool drain`, stop the node, confirm no `java` process remains (`pgrep -f CassandraDaemon`).
6. Wipe the local data directories.
7. Repeat for each knob combination.

**B3f. Predictions.** (stated before any run)
- The `int[]` bytes attributable to `MemtableCursor` stay under about 1 MB per live cursor (65535-byte worst case is about 0.8 MB; here keys are about 1100 bytes, so about 13 KB per cursor at most).
- Total cursor array memory is proportional to the number of live cursors times key depth, with a 16-client scan about 16 * 13 KB * (cursors per scan, maybe 1-3 merged shards) which is well under 5 MB.
- It does not change when `memtable_heap_space` goes from 64MiB to 512MiB.
- Memtable-accounted size (`MemtableOnHeapDataSize`) stays near the configured space limits and triggers flush near them; the unaccounted cursor arrays add on top.
- `heap_buffers` vs `offheap_objects` moves the trie buffers on or off heap but does not change the cursor arrays (always on heap).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Cursor `int[]` total small (< 1% of heap) and equal across the two `memtable_heap_space` values | Claim confirmed: the backtrack array is not bounded by the space config |
| Cursor `int[]` total scales with `memtable_heap_space` or with trie byte size | Claim refuted: usage follows the knob |
| Memtable accounting counts the cursor arrays (they appear in `MemtableOnHeapDataSize` growth with reader count) | Claim refuted |
| Positive control: `MemtableOnHeapDataSize` / flush trigger scales with `memtable_heap_space` under the same write workload (flush at about the limit) | Shows a cap that does bind; needed to confirm the claim |
| The positive control does not move, or no scan phase ran | Not confirmed |

**B3h. Controls.**
- A run with no readers (writes only) shows the baseline `int[]` count.
- Two different `memtable_heap_space` values with the same workload.
- Keys of 20 bytes vs 1100 bytes, to show depth drives size.
- The same run on `SkipListMemtable` (default `memtable:` class) as a contrast, where no trie cursors exist.

### B3i. Audit amendments (2026-10-25, stage-4 step 0, before the freeze and before any reading)

1. **Table syntax (resolves the hedge in B3a/B3c).** `CREATE TABLE ... WITH memtable = 'trie'`. The option is a string key into the yaml's `memtable.configurations` (`TableAttributes.java:124-125` calls `MemtableParams.get(getString(MEMTABLE))`, `MemtableParams.java:107-117`), and the shipped `conf/cassandra.yaml:783-790` already defines `trie` with `class_name: TrieMemtable`. The map form `{'class': 'TrieMemtable'}` is wrong, and no yaml edit is needed for the class. The `memtable_allocation_type` yaml key (`:825`) sets `TrieMemtable.BUFFER_TYPE` once per JVM (`TrieMemtable.java:94`).
2. **Reach (defect in B3c).** A TrieMemtable shard's trie key is `DecoratedKey.asComparableBytes` = the token's bytes, then the key's bytes (`DecoratedKey.java:105-114`). With Murmur3 (`cassandra.yaml:389`) the first 8 bytes are a hash: the trie branches within about 3 bytes and then runs in single-child chains, so a cursor holds at most about 12 entries (under the initial 16), `InMemoryReadTrie.java:502` never executes, and "pk of 1000 bytes, varying early bytes" does not deepen the trie. Backtrack growth needs a partitioner whose token is the key: `ByteOrderedPartitioner` (`partitioner:` at `cassandra.yaml:389`). It has no splitter (`IPartitioner.java:148`), so `ColumnFamilyStore.localRangeSplits` (`:1560`) returns one shard: one trie per table. So: label `m3` runs the filed workload under Murmur3 as the control (prediction: no growth), and the four labels below run under BOP with a comb of partition keys.
3. **Labels and knobs.** `-Xms1g -Xmx1g` as filed; `memtable_cleanup_threshold` is the default 1/3 (`DatabaseDescriptor.java:753-763`, two flush writers).

   | Label | Partitioner | Memtable | `memtable_allocation_type` | Space settings |
   |---|---|---|---|---|
   | hb64 | BOP | trie | heap_buffers | `memtable_heap_space` 64MiB |
   | hb256 | BOP | trie | heap_buffers | 256MiB (the default, 1/4 of the heap) |
   | hb512 | BOP | trie | heap_buffers | 512MiB |
   | oo64 | BOP | trie | offheap_objects | heap 64MiB and `memtable_offheap_space` 64MiB |
   | m3 | Murmur3 | trie | heap_buffers | 256MiB; filed workload (below) |
   | sl | BOP | skiplist (default) | heap_buffers | 256MiB; contrast, no trie cursors expected |

4. **Workload per BOP label.** Table `ks.t (pk blob, ck blob, v blob, PRIMARY KEY (pk, ck)) WITH memtable = 'trie'` (`sl`: no memtable option). (i) Filler: 400,000 partitions, `pk` = 16 random bytes whose first byte is in 0x20..0xEF (`Random(11)`), `ck` 8 bytes, `v` 1000 bytes, written by a Python driver script with up to 256 requests in flight. (ii) Wait until every flush that was enqueued has completed. (iii) The comb: D = 1000: 1001 partitions with `pk` = `0x10^d 0x11` (d = 0..999) and `0x10^1000`, `ck` 8 bytes, `v` 16 bytes (bytes 0x10 and 0x11 avoid the 0x00 escape; the comb does not share a first byte with the filler). (iv) Record accounting. (v) Scan phase of 90 s: 16 client threads loop `SELECT pk FROM ks.t WHERE token(pk) >= token(0x10) AND token(pk) < token(0x12)`, which returns the 1001 comb partitions from the memtable. (vi) Record accounting, run `nodetool flush ks t` (the flush also walks the memtable by cursor, `TrieMemtable.java:352`), record accounting again, stop. `m3` (filed workload): 20,000 partitions with `pk` 1000 random bytes, `ck` 100 bytes, `v` 16 bytes, then 16 threads of `SELECT * FROM ks.t` (page size 1000) for 90 s, flush.
5. **Instruments (replace the heap dump of B3d).** No heap-dump analyser is on the node. Byteman rules (agent `listener:false`; helper class on the boot class path): on `InMemoryReadTrie$CursorBacktrackingState.addBacktrack` `AT LINE 502` (executes only when the array grows) call `BtHelper.grow(oldLength)`; on `InMemoryReadTrie$MemtableCursor.<init>` `AT EXIT` call `BtHelper.cursor()`. The helper keeps a histogram of old lengths and the cursor count and rewrites a stats file every 2 s. This reads the array length of every cursor exactly, instead of sampling. Context only: `jcmd GC.class_histogram` totals of `[I` every 10 s. Accounting: `nodetool sjk mx` on `MemtableOnHeapDataSize` and `MemtableOffHeapDataSize` of `ks.t`, and the usage figure of each `Enqueuing flush` line in `system.log`. Instrument checks before run 1: a known-answer run of the rules on a sparse D = 64 comb in a standalone JVM (the unit test's `main`) must show cursors >= 1, grow events with old lengths 48 and 96 only, once each.
6. **Predictions with numbers (replace B3f's relations).**
   (a) BOP labels hb64, hb256, hb512, oo64: the grow histogram has old lengths in {48, 96, 192, 384, 768, 1536} only, with equal counts N for the six (each growing cursor passes through all of them); no event with old length >= 3072. So the largest array is 3072 ints = 12,304 bytes, and is the same in all four labels. (E is 1000 to 1006: the comb path plus at most 3 entries from a split root; 3072 holds 1024 entries.) N >= 16 (at least the scan threads and the flush grew one each).
   (b) `m3`: zero grow events, with cursor count >= 1000 (scans and flush ran).
   (c) `sl`: cursor count 0, zero grow events.
   (d) Live bytes (inferred, the live count is not observed): at most 17 growing source cursors at a time (16 scan threads, one flush) and, if each holds two cursors, 34 x 12,304 B = 418 KB, under 0.05 % of the 1 GiB heap.
   (e) Accounting: `MemtableOnHeapDataSize` and `MemtableOffHeapDataSize` read before the scan phase and after it are equal (no write in between); this shows the scans add nothing to the accounted size.
   (f) Positive control (a cap that binds): the usage at the first `Enqueuing flush` with reason MEMTABLE_LIMIT scales with `memtable_heap_space`: with S(x) the on-heap usage in MiB for hb<x>, S(256)/S(64) in [3, 5] and S(512)/S(64) in [6, 10] (expected 4 and 8: flush at 1/3 of the space); for oo64 the off-heap usage at its first such flush is in [10, 40] MiB (1/3 of 64 MiB is 21).
7. **Extra rows for B3g.** (a) Rows (a)-(e) of the predictions hold and the control (f) moves: **Confirmed, does not cap**. (b) The largest array differs between labels in step with `memtable_heap_space` (64 < 256 < 512) or with the allocation type: **Refuted**. (c) Accounting changes across the scan phase in step with the number of cursors: **Refuted**. (d) Arrays are all equal across labels but their size differs from 3072 (for example E above 1024): **Confirmed, does not cap**, with the flag "numeric prediction missed". (e) `m3` shows grow events: the reach analysis (item 2) was wrong; BOP rows are judged as in (a)/(d) with the flag "m3 missed". (f) A BOP label has no grow events, or no scan ran, or the control (f) did not move: **Not confirmed** (limit never reached or control failed). (g) The cursor counter is absent or the node died: **Invalid**. (h) Any other reading: **Not confirmed (no matching row)**.
8. **Not run.** The heap dump with dominator tree (item 5). Everything else in B3 runs as amended. Disk: each label writes about 0.5 GB of data and commit log on the local disk (63 GB, 40+ GB free) and is wiped before the next; no 1 GB heap dump. Ports for this run: address 127.0.0.88, storage 7088, native 9088, JMX 7288.

9. **Clarification after the instrument shakedown (2026-10-25, before run 1, before any reading).** A shakedown with a small filler showed a limit-driven flush catching a half-written comb: the flush's two cursors grew to 768 ints only, so the six counts of item 6(a) were unequal. In step (ii) of item 4 the harness therefore runs `nodetool flush ks t` after the wait, so the comb is written into an empty memtable and no flush can start before the scan phase. Predictions and rows are unchanged. (Other shakedown findings, all instrument-only: BOP needs `num_tokens: 1` and no `allocate_tokens_for_local_replication_factor`, because `BytesToken` does not support token allocation; with Murmur3 the node has 40 shards, so `m3` creates many cursors per scan.)

**B4. Risks and cleanup.**
- Disk: up to about 1-2 GB of sstables and commit log on local disk plus the heap dump (about 1 GB each, delete after). Use a local volume of known size.
- Do not build in the shared tree; use `/tmp/c509`.
- Processes: stop Cassandra and stress clients and check with `pgrep -f "CassandraDaemon|stress"`.
- Cleanup: remove `/tmp/c509`, data directories, `/tmp/h.hprof` and logs.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/tries/InMemoryReadTrie.java (lines 1-850)
- src/java/org/apache/cassandra/db/tries/InMemoryTrie.java (lines 70-100, 960-990, grep hits)
- src/java/org/apache/cassandra/db/memtable/TrieMemtable.java (grep hits)
- src/java/org/apache/cassandra/utils/FBUtilities.java (line 158)
- src/java/org/apache/cassandra/cql3/QueryProcessor.java (lines 255-265)
- conf/cassandra.yaml (grep hits)
- test/unit/org/apache/cassandra/db/tries/ (directory listing)

## D. Stage-4 feedback

Stage 4 (autonomous agent), run 1 at both tiers, 2026-10-25. Results: `stage4-runtime-verification/results/BACKTRACK_INITIAL_SIZE-addBacktrack-backtrack--autonomous.md`. Frozen version: sha256 `619b02fa34f0e1b50d80b6e81fe4e746a3d3dc1f78cfe9551e24e85e5bda1c83` (after B2i, B3i and B3i.9; the first freeze `2cf32d77...0725` differs only by B3i.9). The case file is untracked; no commit holds it.

- **Verdict: Confirmed at both tiers, effect `does not cap`, outcome class true negative** (estimate `negative`).
- **Unit:** the array length L follows only the number of branching ancestors on the walked path (E), as 48 x 2^k with E <= 16 x 2^k. Exact figures held in 105 rows (chain 0 / 48; sparse comb D = 8, 64, 1024, 65535: L = 48, 192, 3072, 196608; split comb: E = 3D, L = 96, 768, 12288, 786432), identical for ON_HEAP and OFF_HEAP, for a trie from 5 KB to 77 MB at a fixed shape, and for the size threshold at 8, 16 and 32 MiB; `sizeOnHeap()` is unchanged by a cursor; a reused cursor keeps its length and a new one starts at 48. The positive control (the trie's `ALLOCATED_SIZE_THRESHOLD` flag, false at T-1 MiB and true at T MiB) flipped as predicted.
- **Cluster:** with a ByteOrderedPartitioner comb of depth 1000 the largest cursor array was 3072 ints (12,304 B) at `memtable_heap_space` 64, 256 (default) and 512 MiB and with `offheap_objects`; the six doublings (48 to 1536) occurred an equal number of times (about 10,000 cursors per label); the accounted memtable size did not change across 90 s of scans; the limit-driven flush happened at one third of `memtable_heap_space` (21.3, 85.3, 170.6 MiB). The same workload on the skiplist memtable created no trie cursors; the filed Murmur3 workload created 212,600 cursors and none grew.
- **Amendments made in the audit (stage 3 could learn from them):**
  1. The table option is `WITH memtable = 'trie'` (a configuration key; the default yaml already defines `trie`), not `{'class': 'TrieMemtable'}` (B3i.1).
  2. Under Murmur3 the trie key starts with 8 hash bytes, so the partition-key trie branches within about 3 bytes and the doubling at `:502` cannot run; "varying early bytes of a 1000-byte key" does not deepen it. A cluster test of this line needs ByteOrderedPartitioner (one shard, token = key) (B3i.2).
  3. `ObjectSizes.measureDeep(cursor)` follows the inner class's `this$0` into the whole trie; use `16 + 4 * length` (B2i.2).
  4. Building a depth-65535 comb with one `putSingleton` per key is quadratic; a generated mutation trie applied once is linear (B2i.3).
  5. "Insert until `SpaceExhaustedException`" as a positive control needs a 2 GiB trie; the `row_overhead_size` threshold (`InMemoryTrie.java:58-67`) is a cap on the same bytes that can be exercised at 8 to 32 MiB (B2i.5c).
- **Not changed:** B1, B2f/B2g and B3f/B3g texts as filed (B2i and B3i add the exact numbers and rows). No refuted row.
- **Gaps:** live cursor count at an instant not observed (bound only); the accounting-unchanged reading across scans is weak (no writes in between); no heap dump; no run 2.
- **Cosmetic:** `InMemoryTrie.java:91` is the comment on the 2 GB limit (constructor at :88).

