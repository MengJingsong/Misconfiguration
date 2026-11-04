# Trie iteration path buffer (keyBytes) vs. the 65535-byte key-length limit — verification solution  <!-- file: cases/trie-pathreconstructor-keybytes-addPathBytes-growth--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/tries/TriePathReconstructor.java:41` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI (version not exposed to the agent), 2026-10-25 |
| Estimate | `negative`: line 41 is the grow-check of a per-iterator scratch array; no configured limit caps it, and it is at most a few hundred KB per live iterator, so it bounds no memory- or disk-significant object. |
| Ground | The array is sized by the longest key (path) seen during one trie walk (`TriePathReconstructor.java:28,41-42`). Its only upper bound is indirect: keys are rejected above `FBUtilities.MAX_UNSIGNED_SHORT` = 65535 bytes (a constant, not a knob). That bounds the buffer at roughly 2x the encoded key length, so it is O(100 KB) per iterator and independent of memtable_heap_space, memtable_offheap_space, or any other size knob. The memory a memtable actually uses lives in the InMemoryTrie buffers and cell data, not in this array. |

## A. Constraint trace

**A1. The constraint.** The line itself (`if (newPos > keyBytes.length) keyBytes = Arrays.copyOf(...)`) is not a limit check; it is an unconditional grow-on-demand. There is no configuration entry that constrains it. The nearest real constraint is the constant `FBUtilities.MAX_UNSIGNED_SHORT = 0xFFFF` (`src/java/org/apache/cassandra/utils/FBUtilities.java:158`), enforced for partition keys at `cql3/Validation.java:51` and `cql3/QueryProcessor.java:259`, and for clustering values (each value and the sum) at `db/ClusteringPrefix.java:272-288`. Kind: compile-time constant, unit bytes, value 65535, not settable, no restart relevance. Related but different knob: `memtable_allocation_type` (`conf/cassandra.yaml:825`, default `heap_buffers`), which selects `TrieMemtable.BUFFER_TYPE` (`db/memtable/TrieMemtable.java:94`) for the trie's own storage, not for this array (a plain `byte[]` on heap).

**A2. What it caps.** Nothing in the memory budget. The quantity at line 41 is `keyPos + count` (the path length after appending a node's bytes) compared with `keyBytes.length`. Resource: on-heap scratch, transient, one per `TrieEntriesIterator` / `TrieEntriesWalker` (the only subclasses; `Trie.java:329,435`; `TrieEntriesIterator.java:30`, `TrieEntriesWalker.java:28`).

**A3. Mechanism.**
1. A walk starts with `keyBytes = new byte[32]`, `keyPos = 0` (`TriePathReconstructor.java:28-29`).
2. `Cursor.advanceToContent(receiver)` calls `addPathByte` (`:31-36`, doubles when full) or `addPathBytes` (`:38-45`) for each descent step, and `resetPathLength` (`:47-50`) on ascent.
3. Line 41 tests whether the new length exceeds capacity; line 42 reallocates to `max(newPos+16, 2*length)`. Outcome at the "limit" (capacity): grow, never fail or evict. Capacity never shrinks during the walk; the array is garbage when the iterator is dropped.
4. `mapContent` / `toByteComparable` (`:52-55`) copies `keyBytes[0..keyPos)` per emitted entry, so each entry costs its own key length, again unbounded by any knob (but bounded per key by the 65535 rule on the way in).
Overshoot/bypass: the 65535 check is on the raw key/clustering values; the byte-comparable encoding (`utils/bytecomparable/ByteSource.java:48-64`: zero-escaping, component separators, partition-key + clustering concatenated) can make the path longer than 65535, so path length is not strictly capped by that constant either. The path also contains the partition key plus the clustering, each validated separately, so the practical bound is a small multiple of 65535.

**A4. Other consumers.** The memory that matters for memtables: the InMemoryTrie buffers (`InMemoryTrie.java:88` ctor, `sizeOnHeap()` `:975`, `sizeOffHeap()` `:969`), the cell/partition data, and the memtable allocator pool bounded by `memtable_heap_space` / `memtable_offheap_space` (`conf/cassandra.yaml:797,799`). Flush (`TrieMemtable.java:356,392`) and range reads (`:552`) create the iterators that own the scratch arrays.

**A5. Evidence beyond the source.** none.

## B. Verification solution

**B1. Claim under test.** The `keyBytes` scratch array's size does not follow any memory or disk limit setting: it depends only on the longest key walked (growth to about 2x the maximal encoded key, a few hundred KB at most), and stays flat while the memtable memory knobs and total memtable contents change by orders of magnitude.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Work on a local-disk copy: `rsync -a ~/cassandra-5.0.9/ /local/scratch/c509/ && cd /local/scratch/c509 && ant jar` (never build in the shared tree). Add test `test/unit/org/apache/cassandra/db/tries/PathBufferSizeTest.java` in package `org.apache.cassandra.db.tries` (so the protected `keyBytes` is reachable through a subclass). Run: `ant testsome -Dtest.name=org.apache.cassandra.db.tries.PathBufferSizeTest` [flags verified, B2i.1]. JVM options as defaults of the ant test target; to avoid GC noise use `-Xmx1g`.

**B2b. Knobs.** (1) Key length L of inserted keys: 16, 1 000, 20 000, 65 535, 131 070 bytes (last one exceeds the validated limit, to show the encoding/limit is not a hard stop of the structure). (2) Number of entries N: 1, 1 000, 100 000 with L=16 (a positive control: total content moves, scratch should not). (3) `BufferType`: `ON_HEAP` vs `OFF_HEAP` for the trie (stand-in for `memtable_allocation_type`). Set programmatically in the test.

**B2c. Workload.** Build an `InMemoryTrie<Integer>(BufferType.ON_HEAP)`, `putRecursive(ByteComparable.fixedLength(keyBytes), i, (x, y) -> y)` for N random keys of length L (random bytes, distinct first 8 bytes). Then iterate with a subclass `Probe extends TrieEntriesIterator<Integer, Integer>` whose `mapContent` returns the content and which exposes `keyBytes.length` (read after full iteration). Arithmetic: with a single chain node of up to 28 bytes per `addPathBytes` call, a key of L bytes drives the capacity to at least L; doubling from 32 predicts capacity within [L, 2L+16].

**B2d. Observables and instruments.** (a) `probe.keyBytes.length` after full iteration (the operand). (b) `trie.sizeOnHeap()` and `trie.sizeOffHeap()` (`InMemoryTrie.java:975,969`), the memory that does grow with content (positive control). (c) Allocation by the iteration alone: `com.sun.management.ThreadMXBean.getThreadAllocatedBytes(Thread.currentThread().getId())` before/after iterating. Not observable directly: true heap occupancy of the array (use (a) for size).

**B2e. Procedure.**
1. Write the test with the three loops above; assertions only print the table (no thresholds) so a refutation is visible.
2. `ant testsome -Dtest.name=...PathBufferSizeTest`.
3. Record for each (L, N, BufferType): capacity, sizeOnHeap, sizeOffHeap, allocated bytes during iteration.
4. Delete `/local/scratch/c509` when done.

**B2f. Predictions (before any run).** For N=1000: capacity in [L, 2L+16] for each L (e.g. L=16 gives 32 or 48; L=65 535 gives between 65 535 and 131 086). Capacity is independent of N at fixed L (N=1 vs 100 000 gives the same value). `sizeOnHeap` (or `sizeOffHeap` for OFF_HEAP) grows roughly linearly with N x L, i.e. at L=16, N=100 000 it is orders of magnitude larger than the 32-byte-class scratch. BufferType does not change the capacity. L=131 070 (above 65 535) is walked without failure at this layer, with capacity in [L, 2L+16].

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Capacity tracks L only (within [L, 2L+16]), flat in N and BufferType, while sizeOn/OffHeap grows with N | Claim confirmed: scratch is not tied to memtable memory; usage does not follow any memory knob |
| Capacity grows with N at fixed L | Claim refuted: the buffer accumulates across entries (would contradict `resetPathLength` semantics) |
| Capacity differs between ON_HEAP and OFF_HEAP | Claim refuted: the scratch depends on the allocation-type setting |
| Capacity stays at 32 for all L | Test is not reaching line 41 (path bytes not delivered via `addPathBytes`/`addPathByte`); not confirmed, fix the workload |
| sizeOn/OffHeap does not grow with N (control did not move) | Positive control failed; not confirmed |
| Capacity exceeds 2L+16 by a wide margin at some L | Growth policy differs from the traced one; re-read `:33-45` |

**B2h. Controls.** Positive control: trie size (sizeOn/OffHeap) moves with N x L under the same workload, as it does where a cap (the memtable pool) is known to bind. Repeat each cell 3 times; run a no-op iteration over an empty trie (expect capacity 32). Force `System.gc()` not needed since capacity is read from the live object.

**B2i. Amendments from the stage-4 design audit (dated 2026-10-25, before any harness or run; none depends on a reading).** Every row of B2g, the prediction B2f and the claim B1 are unchanged except where item 4 says so.
1. *Runner (flags checked in `build.xml:1382-1385, 1153`).* The tree is a `copy-source.sh` copy, not an `rsync` of a home directory, and test classes need `ant build-test` once (`testsome` depends on `maybe-build-test`). Command: `ant testsome -Dtest.name=org.apache.cassandra.db.tries.PathBufferSizeTest` (a fully qualified class name; `-Dtest.methods=<m>` optional; `-Dtest.timeout=<ms>`, default 480000). The macro forks a JVM with `maxmemory="1024m"` fixed, which is the `-Xmx1g` of B2a; no other JVM option is needed.
2. *N sweep at a length that grows the array.* At L=16 the path (16 bytes) is below the initial 32, so the array never grows and "independent of N" cannot fail there. N = 1, 1 000, 100 000 is run at L=16 (as filed) **and at L=1 000** (about 100 MB of keys; fits the 1 GiB test JVM). B2g row 2 (capacity grows with N at fixed L) is judged on both.
3. *Wording corrections found by reading the source.* (a) One `addPathBytes` call delivers at most 27 bytes (`chainBlockLength(node) - 1`, `InMemoryReadTrie.java:566-573`; the block is 28 bytes plus a pointer, and the last byte goes to `addPathByte`), not 28. (b) For L=16 the capacity is exactly 32 (the array is not grown), not "32 or 48"; the range [L, 2L+16] still holds. (c) The capacity is data-dependent (the first growth is `newPos+16`, later ones double), so the range is the prediction and no exact value is claimed. (d) A memtable trie holds only the token and partition-key bytes (`DecoratedKey.asComparableBytes`, `DecoratedKey.java:105-113`); clustering values live in the partition's BTree, so A3's "partition key + clustering concatenated" does not apply to `TrieMemtable` and the path there is about 8 + L bytes. Unit tier: the raw key is the whole path.
4. *Positive control (audit group A).* Trie size moving with N x L shows only that content moves, not that a cap binds. Within the unit tier the control is therefore two-sided: the instrument is shown **sensitive** (capacity moves with L from 32 to over 131 000) and **content is shown to move without the array moving** (sizeOn/OffHeap grows with N at fixed L while capacity stays). The known-binding cap control is the cluster tier's `memtable_heap_space` (B3i.5). B2g row 5 keeps its text; the unit tier can reach Confirmed only as a statement about this array in isolation.
5. *Instruments.* `keyBytes` is `protected`; the test class sits in `org.apache.cassandra.db.tries` and reads it through a `TrieEntriesIterator` subclass (`TrieEntriesIterator.java:36` constructor is `protected`, usable from a subclass). Entries iterated are counted and must equal N. After each cell `trie.discardBuffers()` (`InMemoryTrie.java:186`) is called so the OFF_HEAP cells do not accumulate. The three repeats (B2h) are three iterations in the one JVM; the empty-trie iteration is one more cell.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from the local copy (`ant jar` in `/local/scratch/c509`), data/commitlog/hints on local disk of known size (>= 20 GB free, directories under `/local/scratch/c509-data`). JVM: `-Xms2G -Xmx2G` via `conf/jvm11-server.options`, G1. Yaml: `memtable_allocation_type: heap_buffers`, `memtable_heap_space: 256MiB`, and the table uses the trie memtable: `CREATE TABLE ks.t (pk blob, ck blob, v blob, PRIMARY KEY (pk, ck)) WITH memtable = 'trie';` (the `trie` memtable configuration already exists in `conf/cassandra.yaml:783-790` [amended 2026-10-25, B3i.1]).

**B3b. Knobs.** (1) Key size: pk of 16 B vs 60 000 B (under the 65 535 limit); ck 16 B. (2) `memtable_heap_space`: 128MiB vs 512MiB (restart per value). Only (1) is expected to affect the scratch array; (2) is the known-cap positive control (flush frequency and memtable occupancy follow it).

**B3c. Workload.** `cassandra-stress` user profile or a small python/driver loop, writes at CL ONE: Run A: 200 000 rows [amended 2026-10-25, B3i.3: 1 000 000 rows], pk 16 B (~ 20 MB payload with v=64 B). Run B: 2 000 rows of pk 60 000 B (~120 MB of key bytes, enough to cross 128 MiB after overhead). Then force iteration [amended 2026-10-25, B3i.2: scan first, then flush]: `nodetool flush ks t` (flush walks the trie with `entryIterator()`, `TrieMemtable.java:356`) and range scan `SELECT * FROM ks.t` via cqlsh with paging. Duration: about 10 min per run.

**B3d. Observables and instruments.** (a) Heap histogram `jcmd <pid> GC.class_histogram` taken during flush and during the scan, filtering `[B` instances and counting arrays of length 32..300 000 (not directly attributable; use allocation profiling below). (b) [amended 2026-10-25, B3i.6: a Byteman trace is the primary instrument, JFR secondary] JFR: `jcmd <pid> JFR.start settings=profile filename=/local/scratch/c509-data/r.jfr` and inspect `jdk.ObjectAllocationSample` stack traces containing `Arrays.copyOf` under `TriePathReconstructor.addPathBytes`, giving the total bytes allocated at line 42. (c) Memtable occupancy: `nodetool tablestats ks.t` (Memtable data size, Memtable off heap memory used) and `jcmd GC.heap_info`. Cannot be observed directly: the per-iterator array liveness, only its allocation volume via JFR.

**B3e. Procedure.**
1. Start the node with yaml/JVM settings; create keyspace (RF 1) and table.
2. Start JFR. Run Run A; sample `nodetool tablestats` every 10 s; `nodetool flush`; `SELECT *` scan; stop JFR, dump to file; record bytes allocated at `addPathBytes`.
3. Truncate the table, restart with `memtable_heap_space: 512MiB`; repeat. Then repeat for Run B at both heap-space values.
4. Stop the node (`nodetool drain; kill <pid>`), verify `pgrep -f CassandraDaemon` empty, remove data directories.

**B3f. Predictions.** Allocation at `TriePathReconstructor.addPathBytes` per flush/scan is at most about (number of live iterators) x 2 x (encoded key length): Run A, tens to hundreds of bytes per iterator, KB-scale in total; Run B, up to about 120-250 KB per iterator. That is under 0.1% of memtable occupancy (tens to hundreds of MiB) in both runs. It does not change between `memtable_heap_space` 128 vs 512 MiB for the same key size. Memtable occupancy and flush count change with `memtable_heap_space` (control).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Scratch allocation tracks key size only; unchanged across memtable_heap_space; <1% of memtable occupancy; occupancy and flush count move with memtable_heap_space | Claim confirmed: scratch is not governed by the memory limit and is not memory-significant |
| Scratch allocation scales with memtable_heap_space or with row count at fixed key size | Claim refuted |
| Scratch allocation is a large fraction (>10%) of heap or memtable size | Claim refuted: it is memory-significant in practice |
| Memtable occupancy / flush count does not change between 128 and 512 MiB | Positive control failed (cap not reached or not bound); not confirmed, increase write volume |
| No JFR samples at `addPathBytes` | Sampling too coarse; raise the sampling rate or repeat flush more times; not confirmed |

**B3h. Controls.** The known-cap control is `memtable_heap_space` (occupancy follows it). Same table and workload with only the key size changed isolates key length. A baseline JFR on an idle node shows no allocation at the frame. Repeat each run twice.

**B3i. Amendments from the stage-4 design audit (dated 2026-10-25, before any harness or run; none depends on a reading).** B1, the rows of B3g and the prediction B3f are unchanged except where item 8 says so.
1. *Memtable configuration (the writer's unverified item).* The `trie` block already exists in the shipped `conf/cassandra.yaml:783-790` (`memtable: configurations: skiplist, trie (class_name: TrieMemtable), default: inherits skiplist`), so no yaml edit is made. The table uses `WITH memtable = 'trie'` (a string key; `TableAttributes.java:123-124` calls `MemtableParams.get(getString(MEMTABLE))`).
2. *Order of the scan and the flush (B3e step 2).* After `nodetool flush` the table is in sstables (format `big`, which does not use `TriePathReconstructor`), so a `SELECT *` after the flush would not reach line 41. The scan runs **before** the explicit flush, while the memtable still holds data (`TrieMemtable.java:552`, `MemtableUnfilteredPartitionIterator`), and the number of partitions in the memtable is read first (`MemtableColumnsCount`). Then `nodetool flush ks t` (`getFlushSet`, `:356` and again at `:392`).
3. *Workload sizes (B3c).* Run A is **1 000 000 rows** (pk 16 B, ck 16 B, v 64 B) instead of 200 000: the memtable cleanup threshold is `memtable_heap_space / 3` (`memtable_flush_writers` 2, `conf/cassandra.yaml:811, 899`), 42.7 MiB at 128 MiB and 170.7 MiB at 512 MiB, and 200 000 small rows (roughly 60 MB) would cross only the lower one and only once. Run B is 2 000 rows of pk 60 000 B, ck 16 B, v 64 B as filed (about 137 MB of trie, crosses 42.7 MiB about three times at 128 MiB and does not cross 170.7 MiB at 512 MiB, so the scan finds data in the memtable at 512 and the flush is the explicit one). Writes are CL ONE through the Python driver (protocol 5, 256 in flight), a fresh data directory per run.
4. *Per-run settings.* One node on `127.0.41.1`, storage 7011, native 9143, JMX 7211, Byteman agent without listener (rules are loaded at start); `MAX_HEAP_SIZE=2G` (the pair `-Xms2G -Xmx2G` set through the environment instead of editing `jvm11-server.options`; checked in the live command line), G1; `memtable_allocation_type: heap_buffers`, `memtable_heap_space` 128MiB or 512MiB, `partitioner` Murmur3 (default), `num_tokens` default. Data, commit log, hints and saved caches on local disk under `~/s4-tp41-run`. Labels: A128, A512, B128, B512, each run twice (r1, r2) from a fresh data directory, eight node starts.
5. *Known-cap control.* Per run: the number of flush enqueues for `ks.t` in `system.log` and the peak of `MemtableOnHeapDataSize` sampled every 5 s during the write. Expected: both move with `memtable_heap_space` (flush count at 128 MiB above 512 MiB; peak near 42.7 MiB x (1 + a small excess) at 128 MiB and larger at 512 MiB). If neither moves, B3g row 4 applies.
6. *Primary instrument: a Byteman trace (replaces JFR sampling, which can miss 32 to 64 KB allocations).* Rules (agent `-javaagent:build/lib/jars/byteman-4.0.20.jar=listener:false,boot:<jar>,boot:<helper jar>,script:tp.btm`; the rules target Cassandra classes only): at `AT LINE 34` and `AT LINE 42` of `TriePathReconstructor` (the two growth statements) a helper logs `site, identity hash of the receiver, old capacity, requested position` to a file; at `TriePathReconstructor.<init>` exit it counts the reconstructor by class name; at entry of `toByteComparable` it adds the copied length to a counter (the per-entry copy of `:54`, which is **not** the scratch array and is reported separately). New capacity is computed by the helper by the line's own formula (`keyPos*2` at :34; `max(newPos+16, 2*old)` at :42) and each event is a real `Arrays.copyOf` of that size. Per iterator: final capacity = last new capacity for that identity; allocation at the growth lines = the sum of the new capacities (plus `16 + n` header, ignored). Identities are reused after GC: the log carries a sequence number and a flush/scan phase tag set by the driver through a flag file. JFR (`jcmd <pid> JFR.start settings=profile`, then `jfr print --events jdk.ObjectAllocationSample,jdk.ObjectAllocationOutsideTLAB`) is run as a secondary cross-check and is not required for any row; "No JFR samples" in B3g is read as "no Byteman event and no JFR sample".
7. *What is compared.* B3f's "does not change between 128 and 512 MiB" and B3g's "unchanged across `memtable_heap_space`" are read **per iterator** (final capacity and the allocation of one iterator at the growth lines). Totals scale with the number of iterators (more flushes at 128 MiB means more iterators) and are reported but not used to refute. B3g row 2's "scales with row count" is read per iterator too: Run A has 1 000 000 rows and Run B 2 000; the Run A iterators are expected not to grow at all (path about 8 + 16 + 2 = 26 bytes, below 32).
8. *Prediction numbers (derived from the code, before any run).* Run A: no growth event at all, final capacity 32 for every iterator. Run B: path about 8 + 60 000 + 2 = 60 010 bytes, so final capacity in [60 010, 120 036] and, because the path is delivered mostly in 27-byte steps while the capacity doubles from 32 or 70 upward, a value near 65 000 to 120 000; allocation at the growth lines per iterator about 2x the final capacity in total (the doubling chain), i.e. 130 000 to 250 000 bytes, as in B3f. Neither number changes B3f or B3g.
9. *Cleanup and checks (B4).* Check with `ps -eo pid,args | grep '[C]assandraDaemon'` filtered to the tree path, and kill by PID. The "large partition key" warning for 60 000 B keys is not a failure. `ulimit -n 100000` is set in the starting shell.

**B4. Risks and cleanup.** Disk: Run B writes about 120 MB x flushes; data dirs on local disk of known size (>= 20 GB); never use shared storage or the shared source tree. Processes: stop Cassandra, any JFR, cqlsh/stress clients; check with `pgrep -fa 'CassandraDaemon|cassandra-stress|java'`. Cleanup: `rm -rf /local/scratch/c509 /local/scratch/c509-data`. The 60 000 B keys may trigger large-partition-key warnings; expected, not a failure.

## C. Sources read

- ~/writeup-A/playbook-autonomous.md
- ~/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/tries/TriePathReconstructor.java
- src/java/org/apache/cassandra/db/tries/TrieEntriesIterator.java (lines 28-70)
- src/java/org/apache/cassandra/db/tries/Trie.java (grep)
- src/java/org/apache/cassandra/db/tries/InMemoryTrie.java (grep)
- src/java/org/apache/cassandra/db/ClusteringPrefix.java (265-292)
- src/java/org/apache/cassandra/cql3/Validation.java (45-60)
- src/java/org/apache/cassandra/cql3/QueryProcessor.java (grep)
- src/java/org/apache/cassandra/utils/FBUtilities.java (grep)
- src/java/org/apache/cassandra/utils/bytecomparable/ByteSource.java (grep)
- src/java/org/apache/cassandra/db/memtable/TrieMemtable.java (grep)
- src/java/org/apache/cassandra/config/Config.java (grep)
- conf/cassandra.yaml (grep)

## D. Stage-4 feedback

**Stage 4, 2026-10-25 (run 1 on pc12, self-checked, no run 2): Confirmed at both tiers; effect on the constraint: does not cap; outcome class true negative.** Results: [`results/trie-pathreconstructor-keybytes-addPathBytes-growth--autonomous.md`](../../stage4-runtime-verification/results/trie-pathreconstructor-keybytes-addPathBytes-growth--autonomous.md). The estimate stays as filed.
- **Unit (B2g row 1):** capacity 32 / 1 024 / 32 768 / 65 536 / 149 504 for key length 16 / 1 000 / 20 000 / 65 535 / 131 070, identical for ON_HEAP and OFF_HEAP and for N = 1 to 100 000 (at L = 16 and L = 1 000), while the trie size grew from 1.9 KB to 117 MB. All inside [L, 2L+16].
- **Cluster (B3g row 1):** Run A (1 000 000 rows, 16-byte keys): zero growth events in 436 reconstructors. Run B (2 000 rows, 60 000-byte keys): final capacity 65 536 to 74 752, scratch 131 to 149 KB per reconstructor at 128 MiB and 131 KB at 512 MiB, at most 0.35 % of the smallest flushed memtable. The known cap moved: limit flushes at `memtable_heap_space` / 3 (42.7 vs 170.7 MiB), 12 vs 2 to 3 flushes (A) and 2 vs 0 (B).
- **Corrections to the write-up (all in the dated amendments B2i, B3i, 2026-10-25; none changes a prediction row):** the memtable trie holds token + partition key only, not the clustering (A3 said "partition-key + clustering"); one `addPathBytes` call delivers at most 27 bytes, not 28; for L = 16 the capacity is exactly 32; the shipped `conf/cassandra.yaml:783-790` already defines the `trie` memtable configuration; the scan must come before the flush (a post-flush `SELECT *` reads sstables); Run A needs 1 000 000 rows to cross the cleanup threshold (`memtable_heap_space` / 3); a Byteman trace at lines 34 and 42 replaces JFR sampling.
- **Numbers that missed (B3f):** "under 0.1 % of memtable occupancy" held at 512 MiB (0.094 %) and not at 128 MiB (0.34 %), because the memtable at a limit flush is 42.7 MiB; the B3g threshold (1 %) holds. Per-iterator capacity at 128 MiB reached 74 752 vs 65 536 at 512 MiB (trie shape, not heap space).
- **Outside the claim, observed:** `toByteComparable` (line 54) copies each emitted entry's key: 57 MB in total in Run A and 279 to 363 MB in Run B, transient garbage.
