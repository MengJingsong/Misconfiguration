# Partition key size limit (65535 bytes) bounding InMemoryTrie.ApplyState stack — verification solution  <!-- file: cases/partition-key-max-size-descend-data-length--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/tries/InMemoryTrie.java:670` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (Claude Code agent), 2026-10-25 |
| Estimate | `negative`. The line grows an unaccounted, on-heap `int[]` scratch stack. It is not governed by any memory cap. Its size follows key depth, which is bounded only by the 65535-byte key-size limit. |
| Ground | `ApplyState.data` is never counted in `InMemoryTrie.sizeOnHeap()` (`InMemoryTrie.java:974-981`), so it is never charged to the memtable allocator. The charge is `allocator.onHeap().adjust(data.sizeOnHeap() - onHeap)` at `TrieMemtable.java:485`. It is not bounded by `memtable_heap_space`, `memtable_offheap_space` or the trie size threshold (`ALLOCATED_SIZE_THRESHOLD`, `InMemoryTrie.java:58-68`). It is only reached for keys of 128 bytes or more (`TrieMemtable.java:98,483`). Its size is the high-water mark of key depth in that shard (one trie per shard). It is retained until the memtable is discarded. |

## A. Constraint trace

**A1. The constraint.** The target line is not itself a limit. It is a dynamic-growth step: when the descent depth reaches the array length, `data` is doubled (`InMemoryTrie.java:670-671`). The array is declared at `InMemoryTrie.java:577` (`int[] data = new int[16 * 5]`, 80 ints = 320 B, 5 ints per depth level). Three real limits are related to it.
- (a) The maximum partition key size, `FBUtilities.MAX_UNSIGNED_SHORT = 0xFFFF` (`utils/FBUtilities.java:158`), enforced in `cql3/Validation.java:51-55`. Constant, unit bytes, not settable.
- (b) The recursion cutoff `TrieMemtable.MAX_RECURSIVE_KEY_LENGTH = 128` (`db/memtable/TrieMemtable.java:98`). Constant, not settable. Keys of 128 bytes or more take the `ApplyState` path (`TrieMemtable.java:483`, `InMemoryTrie.java:870-880`).
- (c) The trie size threshold `ALLOCATED_SIZE_THRESHOLD` (`InMemoryTrie.java:58-68`). Default `2048*10/11` = 1861 MB. It is read from `CassandraRelevantProperties.MEMTABLE_OVERHEAD_SIZE`, whose key is `cassandra.memtable.row_overhead_size` (`CassandraRelevantProperties.java:356`). It is settable by `-D` at startup and must be within 1..2047. The separate `MEMTABLE_TRIE_SIZE_LIMIT` (`cassandra.trie_size_limit_mb`, line 358) appears unused in `src/java` (grep finds only the declaration).
For the claim tested here, the governing constraint is (a), the only thing bounding `currentDepth`. Memory accounting is through `memtable_heap_space` / `memtable_offheap_space` (`config/Config.java:187-189`) and (c).

**A2. What it caps.** (a) caps key bytes and so trie depth. Depth is the length of the byte-comparable key of the DecoratedKey. For the partitioner token prefix this is roughly 9 bytes plus the key bytes plus a terminator; this estimate is not verified in the source and stage 4 should confirm it. `ApplyState.data` is on-heap, 20 B per depth level, doubling. For D of about 65.5K the array reaches `5*D*2` ints, up to about 2.6 MB (when `currentDepth*5 >= length`, the new length is `currentDepth*5*2`). Resource: heap, per trie shard, outside memtable accounting.

**A3. Mechanism.**
1. `TrieMemtable.MemtableShard.put` (`TrieMemtable.java:458-484`) calls `data.putSingleton(key, update, merge, key.getKeyLength() < 128)`.
2. For short keys this is `putRecursive` (`InMemoryTrie.java:~890`), with no `ApplyState` involvement.
3. For longer keys, `putSingleton` calls `apply(Trie.singleton(...))` (`InMemoryTrie.java:~822-850`). `apply` resets `currentDepth=-1` (`:580-583`, `:827`) and calls `descend` per key byte.
4. `descend` (`:656`) does `++currentDepth` and, if `currentDepth*5 >= data.length`, `data = Arrays.copyOf(data, currentDepth*5*2)` (`:669-671`).
5. `data` is never shrunk. `reset()` only sets the depth to -1. So memory stays at the high-water mark for the life of the trie (the memtable).
6. Accounting: `sizeOnHeap()` (`:974-981`) counts contents, chunk arrays, `allocatedPos` and `EMPTY_SIZE_ON_HEAP`. The latter is `ObjectSizes.measureDeep(empty trie)` taken once in a static initialiser (`:80-86`), so it includes only the initial 80-int array. Growth at `:671` is therefore invisible to `allocator.onHeap()` and to `memtable_heap_space`.
Bypass/overshoot: the array can reach about 2.6 MB per shard trie (shards = `AbstractShardedMemtable` shard count, default from local range splits) without the memtable cap noticing. There is no failure mode at the limit; the 2 GB `SpaceExhaustedException` is unrelated.

**A4. Other consumers.** The trie's own buffers and contents (accounted); the partition BTrees and cells (accounted through `allocator`); `Arrays.copyOf` garbage from the old array (short-lived young garbage); the per-write `BTreePartitionUpdater`.

**A5. Evidence beyond the source.** none. This is the source-only claim. No external documents were used.

## B. Verification solution

**B1. Claim under test.** Memory held by `InMemoryTrie.ApplyState.data` is not bounded by, nor charged to, the memtable cap (`memtable_heap_space` / `memtable_offheap_space` / the trie size threshold). It grows with the maximum key depth (`~20 B x depth`, doubled) irrespective of those knobs. `sizeOnHeap()` stays flat while the real retained size of the trie object grows after a long-key write.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (for example `cp -r ~/cassandra-5.0.9 /tmp/c509` and `cd /tmp/c509`), then `ant jar`. Write a JUnit test (or a `main` class) in the package `org.apache.cassandra.db.tries` in a scratch dir outside the source tree, so it can reach the package-private `applyState`/`data`. Run with the classpath of `build/classes` plus `lib/*`. JVM options: `-Xmx2g -Dcassandra.config=... ` is not needed. Do not use `-Dcassandra.memtable.row_overhead_size` at first.

**B2b. Knobs.**
- Key length L in bytes: 16, 127, 128, 1024, 16384, 65535 (the maximum allowed key). Reasoning: below and above the recursion cutoff of 128, then to the key-size limit.
- Buffer type: `BufferType.ON_HEAP` and `OFF_HEAP`.
- Threshold property `-Dcassandra.memtable.row_overhead_size=1` vs the default, to show the threshold knob does not affect the stack array.
Each is set in the test code (the property by JVM flag; it is read in a static initialiser, so use a separate JVM per value).

**B2c. Workload.** For each L, create a fresh `InMemoryTrie<Object>`. Call `putSingleton(key, value, (e,u)->u)` with one key of L bytes (a `ByteComparable.fixedLength(byte[])` of random bytes) on the non-recursive overload (the 3-arg one, `useRecursive=false`). The depth is L plus the root, so `currentDepth` reaches about L. Expected `data.length`: starts at 80, doubles whenever `5*depth >= length`. Final length is the first value `80*2^k`-style produced by the copy rule `5*d*2` at the last growth, so it is bounded `5*L <= length < 10*L+10`. Then put 1M more distinct 16-byte keys to show the trie's accounted size grows while `data.length` does not.

**B2d. Observables and instruments.**
- `trie.applyState.data.length` (package-private field, direct read).
- `trie.sizeOnHeap()` and `sizeOffHeap()`.
- Retained deep size: `org.github.jamm.MemoryMeter.measureDeep(trie)` (jamm is in `lib/`, with `-javaagent:lib/jamm-*.jar`), or `ObjectSizes.measureDeep(trie.applyState.data)`.
- Cannot observe directly: GC garbage from the old arrays (use `-Xlog:gc` if wanted).

**B2e. Procedure.**
1. Build (`ant jar`) in the local copy.
2. Compile the harness in the same package against `build/classes/main`.
3. For each (L, bufferType): construct the trie. Record `data.length0`, `sizeOnHeap0` and `measureDeep0`. Put the key. Record the same three again.
4. Repeat with the recursive overload (`putRecursive`) as the control.
5. Repeat step 3 for L=65535 under `-Dcassandra.memtable.row_overhead_size=1`.
6. Print a table.

**B2f. Predictions (before any run).**
- L=16 and L=127 (non-recursive overload): `data.length` stays 80 for L<16 (depth*5<80); for L=127 it is about 640-1270 ints.
- L=1024: `data.length` in [5120, 10250] ints (20-41 KB).
- L=65535: `data.length` in [327675, 655370] ints, i.e. about 1.3-2.6 MB.
- `sizeOnHeap()` before/after differs only by the nodes allocated (`allocatedPos` blocks, about one 32-byte block or so per key byte) and never by the `data` growth. Check: the delta of `sizeOnHeap` is within a few blocks per byte of the key for L=65535, while the `data` delta is of the order 1.3 MB or more. If the nodes dominate this comparison, use `measureDeep(data)` against the `sizeOnHeap` delta. The claim concerns only the `data` term, so compute `sizeOnHeap` minus the node bytes.
- The recursive control leaves `data.length` at 80.
- `row_overhead_size=1` leaves `data.length` unchanged.
- The unaccounted amount equals `measureDeep(data) - 320` B (the initial array is already in `EMPTY_SIZE_ON_HEAP`).
What would show the claim wrong: `sizeOnHeap()` increases by at least `measureDeep(data)-320` when `data` grows, or `data.length` is clamped by the knob.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `data.length` grows with L, `sizeOnHeap` has no matching term, threshold knob has no effect | Claim confirmed: the array is unaccounted and unbounded by the memtable cap |
| `sizeOnHeap` delta includes about `4*(newLen-oldLen)` extra bytes | Claim refuted (accounting exists; re-trace) |
| `data.length` shrinks or is capped below `5*L` | Claim refuted |
| `data.length` stays 80 at L=65535 | Wrong path taken (recursive path, or the overload misused); not confirmed |
| Recursive control does not stay at 80 | Harness error; not confirmed |
Positive control: the same workload shown to move accounted usage. 1M distinct short keys raise `allocatedPos`, `sizeOnHeap` and `reachedAllocatedSizeThreshold()` (with `row_overhead_size=1`, i.e. 1 MB, the threshold should flip to true), while `data.length` does not move. This shows the instruments can see a bound that does bind.

**B2h. Controls.** (1) Recursive overload (no ApplyState use). (2) Fresh trie per L (no carry-over). (3) Both buffer types. (4) Short keys with many puts, to separate node growth from stack growth. (5) Repeat each L three times; reading is deterministic.

**B2i. Stage-4 audit amendments (2026-10-25; made before any reading).**
1. *Exact length rule (replaces the ranges in B2f where they differ).* `descend` doubles to `currentDepth*5*2` at the first depth `d` with `5d >= length`, and `length` is always a multiple of 5 starting at 80, so the lengths are exactly `80*2^k` and the final `data.length` is the smallest `80*2^k` with `5*D < 80*2^k`, `D` being the deepest `currentDepth` (for a `fixedLength` key of L bytes, `D = L`). Exact predictions for the 3-argument `putSingleton` (non-recursive): L=15 -> 80; **L=16 -> 160** (B2f's "L=16 ... stays 80" is wrong: it stays 80 only for L<=15); L=127 -> 640; L=128 -> 1280; L=1024 -> 10240; L=16384 -> 163840; L=65535 -> 327680 (1,310,720 B + 16 B header); **L=65536 -> 655360** (2,621,440 B, the "about 2.6 MB" of A2; it needs a depth above 65535, which a database key reaches because the token prefix and terminator add about 10 bytes). Add L=65536 and L=65545 to the L list of B2b. The 1M-short-key control: keys of 16 bytes give `data.length` 160 for the whole run, unchanged by the 1M puts.
2. *Differential accounting check (replaces the soft "within a few blocks" in B2f).* The same single key put through `putRecursive` (run in a thread with a 1 GiB stack, for L up to 16384) builds the same trie nodes without touching `ApplyState`. Prediction: `sizeOnHeap` delta of the apply path equals the recursive path's delta within 5 % (the difference is the accounted part of the stack, predicted 0), while `data` has grown by `4*(len-80)` B (L=1024: 40,960 B; L=65535: 1,310,400 B). Claim refuted if the apply-path delta exceeds the recursive delta by 50 % or more of `4*(len-80)` for any L>=1024. Also record `measureDeep(trie)` before and after with jamm (`ObjectSizes.measureDeep`): it must grow by at least `4*(len-80)`, which shows that the stack is retained and is the unaccounted term.
3. *Depth of a database key.* The unit harness also decorates a random K-byte blob with `Murmur3Partitioner`, counts the bytes of `DecoratedKey.asComparableBytes(Version.OSS50)` and records `D(K)`; B3b and B3i.2 use it. A2's "about 9 bytes plus the key plus a terminator" is checked there.
4. *Side finding recorded (not a change to the claim).* The trie size threshold of C(c) is read from `cassandra.memtable.row_overhead_size` (`InMemoryTrie.java:63`), the same property that `SkipListMemtable.java:75` reads as a byte count. `MEMTABLE_TRIE_SIZE_LIMIT` (`cassandra.trie_size_limit_mb`, `CassandraRelevantProperties.java:358`) has no other reference in `src/`, `test/` or `conf/` (grep, stage-4 audit). Setting it does nothing.
5. *Citations corrected.* The non-recursive path is `putSingleton` at `InMemoryTrie.java:862-881` and `apply` at `:822-850` (`putRecursive` is `:895`, not `~890`); the shard count comes from `AbstractShardedMemtable.java:46,63-65` (not `TrieMemtable.java:660-662`); `ApplyState` is at `:565-577`. B2a: the copy is built with `ant build-test` and classes come from `build/classes/main`; jamm is a jar in `build/lib/jars`.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, Ant, built from a local copy (`/tmp/c509`, `ant jar`). Use `cassandra.yaml` with `memtable: configurations: trie: class_name: TrieMemtable` and a table with `WITH memtable = 'trie'`. Local-disk dirs of known size for data, commitlog, hints and saved_caches (for example `/tmp/node1/...` with at least 10 GB free). JVM: `-Xms2g -Xmx2g` (G1 default), `-XX:+HeapDumpOnOutOfMemoryError` is not needed. Config: `memtable_allocation_type: heap_buffers`, `memtable_heap_space: 64MiB`, `memtable_offheap_space: 0MiB` (default), `commitlog_sync: periodic`, `memtable.shard.count` / table option `shards=1` (so one trie, one `ApplyState`; `TrieMemtable.java:660-662`).

**B3b. Knobs.** Partition key size K in {32, 100, 200, 1000, 16000, 60000} bytes (blob key; 65535 is the limit, `Validation.java:51`). Use K=32/100 below the cutoff as the control. Memtable heap space {64 MiB, 256 MiB}. Set by yaml; table option `shards=1` via `CREATE TABLE ... WITH memtable = {'class': 'TrieMemtable', 'shards': '1'}`.

**B3c. Workload.** cassandra-stress or a small driver script (Python driver `INSERT INTO ks.t (k blob, v int)`) writing 2000 partitions with random K-byte keys and a 1-byte value, one pass per K, on a fresh node/table each time. Total payload about 2000*K bytes (up to 120 MB at K=60000). Memtable data is far below `memtable_heap_space`, so no flush occurs, which isolates the memtable. The deepest key sets the stack size, so even one long key suffices; many keys exercise it repeatedly.

**B3d. Observables and instruments.**
- Heap after full GC: `jcmd <pid> GC.run`, then `jcmd <pid> GC.class_histogram | grep '\[I'`. The `int[]` row total should show a +about 2.6 MB step at K=60000.
- Memtable-accounted size: `nodetool tablestats ks.t` (`Memtable data size`, `Memtable off heap memory used`), or JMX `MemtableOnHeapSize`.
- Optionally a heap dump with `jmap -dump:live,format=b` and an Eclipse MAT query for the `InMemoryTrie$ApplyState` retained size.
- Cannot see directly: the allocator's internal counter other than via those metrics.

**B3e. Procedure.**
1. Build in `/tmp/c509`; start the node with the config; create the keyspace (RF=1) and the table.
2. For each K: reset (drop the table or restart with fresh dirs). Record the baseline `int[]` total and `MemtableOnHeapSize`.
3. Run the workload; do not flush (check `nodetool tablestats` shows the memtable populated).
4. `jcmd GC.run`; record the `int[]` total and `MemtableOnHeapSize`.
5. Run `nodetool flush`; `jcmd GC.run`; record the `int[]` total again (expected to drop after the memtable is discarded).
6. Stop the node (`nodetool drain`, then kill the pid), and verify with `pgrep -f CassandraDaemon`.

**B3f. Predictions.**
- K=32, 100: `int[]` delta from the stack is under 10 KB (recursive path; the stack stays at 320 B).
- K=200: stack about 1-4 KB; K=1000: 20-41 KB; K=16000: 0.3-0.65 MB; K=60000: about 1.2-2.4 MB (order of 20-40 B x K).
- `MemtableOnHeapSize` is about proportional to the data stored (keys and nodes) and shows no jump matching the stack; the unexplained gap `int[]delta - memtable-size-delta-from-nodes` increases with K and equals about the stack size. `memtable_heap_space` 64 vs 256 MiB gives the same stack size.
- After flush the stack array disappears from the histogram (it is retained only while the memtable lives).
What would show the claim wrong: the stack array stays around 320 B at large K (the code path is not exercised), or `MemtableOnHeapSize` rises by the stack size, or the stack size depends on `memtable_heap_space`.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| `int[]` total rises with K above 128 by about the predicted 20-40 B x K; memtable size shows no matching rise; same for both heap-space values | Claim confirmed (unaccounted, not following the cap) |
| Memtable size rises by the same amount | Claim refuted |
| `int[]` total flat at large K | Not confirmed (path not exercised; check that the key was 128 bytes or more and `shards`/the trie memtable is in use) |
| Stack size differs between 64 and 256 MiB | Claim refuted |
Positive control: write the same number of short-key partitions with a larger value payload (for example 100 KB values). Accounted `MemtableOnHeapSize` rises with data, and with `memtable_heap_space` set small (for example 16 MiB) a flush is triggered by the cap (`MEMTABLE_LIMIT`), showing that the cap binds on the accounted structures while the stack is untouched.

**B3h. Controls.** (1) Short-key run (K<128). (2) Fresh node and table per K. (3) `shards=1` so a single stack is measured. (4) Same JVM flags in all runs. (5) Force GC before every read; compare against the baseline taken after startup and an empty table.

**B3i. Stage-4 audit amendments (2026-10-25; made before any reading).**
1. *Table definition (replaces B3b's inline option).* `WITH memtable = {'class': 'TrieMemtable', 'shards': '1'}` is not accepted in 5.0.9: `MemtableParams.get` takes only a configuration key (`schema/MemtableParams.java:111-127`). Define `memtable: configurations: trie: {class_name: TrieMemtable, parameters: {shards: "1"}}` in `cassandra.yaml` and create tables `WITH memtable = 'trie'`. One table per arm in one node (one memtable, one `ApplyState` each), created just before its arm.
2. *Workload arithmetic (replaces B3c).* 2000 partitions of K=60000 are 120 MB, above `memtable_heap_space: 64MiB`, so the memtable would flush by the cap, contradicting "no flush". Use **N=5 partitions per arm** (random K-byte blob keys without 0x00/0xFE bytes, so the byte-comparable length is K plus a fixed prefix; value `int` 1), plus one extra arm of N=1 at K=60000 and K=65535. K list: {32, 100, 127, 128, 200, 1000, 16000, 60000, 65535}; 127 is the last recursive length and 128 the first `ApplyState` length (`TrieMemtable.java:98,483`). Each arm writes under 0.4 MB, so no flush occurs before the explicit one. The control arm K=32 is run first and last in each node to bound drift of the unrelated `int[]` total.
3. *Exact stack predictions (replace B3f's K=200 "1-4 KB").* With `D(K)` from B2i.3 (about K+10): K<=127 -> 80 ints (320 B); K=128 (D about 138) and K=200 (D about 210) -> 1280 ints (5,120 B); K=1000 -> 5120 ints (20,480 B); K=16000 -> 81,920 ints (327,680 B); K=60000 -> 327,680 ints (1,310,720 B); **K=65535 -> 655,360 ints (2,621,440 B)** because D exceeds 65536. Observable: `delta_int = (int[] bytes after the writes) - (int[] bytes before the first write)`, from `jcmd GC.class_histogram` (it runs a full GC), minus the same delta of the K=32 control arm. Prediction: `delta_int - control` is within 25 % of `stack_bytes - 320` for K>=1000, and within the control's spread +- 2 KB for K<=127.
4. *Accounted size observable (replaces B3d's `tablestats`).* `nodetool tablestats` "Memtable data size" is the live data size, not the allocator's charge. Read JMX `org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=<table>,name=MemtableOnHeapDataSize` attribute `Value` (`TableMetrics.java:493`) and `MemtableOffHeapDataSize` before and after the writes. Prediction: the N=1 arms at K=60000 and K=65535 show `delta_int - control >= 1.0 MB` while the `MemtableOnHeapDataSize` delta is at most 0.3 MB; the N=5 arms' delta scales with N (nodes and key copies) while their stack does not (N=1 and N=5 at K=60000 have the same `delta_int` within 10 %). Claim refuted if the `MemtableOnHeapDataSize` delta of an N=1 arm is within 0.2 MB of `delta_int - control`.
5. *Positive control made exact.* Short keys (K=32), 100 KB values, `memtable_heap_space: 16MiB`, `memtable_offheap_space: 16MiB`, writes of 100 KB values until a flush is logged (at most 400 writes, 40 MB). Prediction: a flush of the table is logged with reason `MEMTABLE_LIMIT` when `MemtableOnHeapDataSize` has risen to between 4 MiB and 16 MiB, and the `int[]` delta of that arm stays within the control's spread. This shows the accounted cap binds on the accounted structures.
6. *Heap-space values.* The full K list runs on two node starts, `memtable_heap_space` 64 MiB and 256 MiB; the positive control is a third start (16 MiB). Cleanup (B4): the checks use `ps -eo pid,cmd | grep '[C]assandraDaemon'` and kill by PID because the node is shared with other runs; paths are under `~/s4-pk/` on local disk, not `/tmp`.

**B4. Risks and cleanup.** Disk: keep all node dirs on local disk, `/tmp/node1` of known size (each run writes under 200 MB); the commitlog and sstables are removed by `rm -rf /tmp/node1` after the run. Never build in the shared tree. Stop the node (`nodetool drain`, then kill), then `pgrep -f 'CassandraDaemon|java.*InMemoryTrie'` must be empty. Remove `/tmp/c509`. Heap: `-Xmx2g`, the unit tier needs under 1 GB.

## C. Sources read

- `/users/jason92/writeup-A/playbook-autonomous.md`
- `/users/jason92/writeup-A/_TEMPLATE-autonomous.md`
- `src/java/org/apache/cassandra/db/tries/InMemoryTrie.java`: lines 50-100, 540-730, 800-900, 940-985 and grep results
- `src/java/org/apache/cassandra/db/memtable/TrieMemtable.java`: lines 98, 180-210, 455-495, 660
- `src/java/org/apache/cassandra/config/CassandraRelevantProperties.java`: lines 355-360
- `src/java/org/apache/cassandra/config/Config.java`: lines 186-189, 524 (grep)
- `src/java/org/apache/cassandra/cql3/Validation.java`: lines 51-55 (grep)
- `src/java/org/apache/cassandra/utils/FBUtilities.java`: line 158 (grep)
- `src/java/org/apache/cassandra/db/memtable/AbstractShardedMemtable.java` (grep)

## D. Stage-4 feedback

**2026-10-25, run 1 at both tiers, self-checked, no run 2.** Results: [`results/partition-key-max-size-descend-data-length--autonomous.md`](../../stage4-runtime-verification/results/partition-key-max-size-descend-data-length--autonomous.md). Node `pc12`, JDK 11, local copy of `cassandra-5.0.9` at repository commit `25b4a70`; case file and harness not committed.

- **Verdict:** unit B2g row 1 and cluster B3g row 1, **Confirmed**; **Effect on the constraint: does not cap**; **Outcome class: true negative** (estimate `negative`). The claim held: `ApplyState.data` follows key depth by the rule `80*2^k` ints (327,680 ints = 1.31 MB at depth 65535, 655,360 ints = 2.62 MB at a 65535-byte database key), is not in `sizeOnHeap()` (apply and recursive paths have equal deltas at every L) or in `MemtableOnHeapDataSize` (75.5 KB charge against a 2.62 MB step at K=65535, N=1), and does not depend on `memtable_heap_space` (64 and 256 MiB give identical steps) or `row_overhead_size`. The step leaves with the discarded memtable. Positive control: a 16 MiB heap space flushed 100 KB-value writes by `MEMTABLE_LIMIT` at 5.39 MiB on-heap with the `int[]` total unmoved; 1M short keys flipped the trie threshold at `row_overhead_size=1`.
- **Amendments made at the audit (dated 2026-10-25, B2i and B3i):** exact length rule (L=16 gives 160, not 80; K=200 gives 5,120 B, not 1-4 KB; the "2.6 MB" needs depth above 65535, K=60000 gives 1.31 MB); the inline `memtable = {'class': ..., 'shards': ...}` syntax is not valid in 5.0.9 (use `parameters: {shards: 1}` in the yaml configuration); 2000 partitions of 60 KB would flush a 64 MiB memtable, so N=5 and N=1 arms; the allocator charge is JMX `MemtableOnHeapDataSize`, not `tablestats` "Memtable data size"; citations `putRecursive` is `InMemoryTrie.java:895`, the shard count is `AbstractShardedMemtable.java:46,63-65`.
- **Side finding (A1 (c)):** confirmed. The trie size threshold is read only from `cassandra.memtable.row_overhead_size` (`InMemoryTrie.java:63`, MB, 1..2047); `MEMTABLE_TRIE_SIZE_LIMIT` (`cassandra.trie_size_limit_mb`) has no other reference in `src/`, `test/` or `conf/`, and setting it to 1 left `reachedAllocatedSizeThreshold()` false at 74.95 MB allocated. No change to the claim.
- **Left for stage 3, not applied:** a conclusions row for "reading outside every row" (the generic no-matching-row rule covers it); the claim holds per shard, so with the default shard count (the processor count) the unaccounted total is up to that many times 2.6 MB, which was not run (one shard); the cluster tier reads the total of all `int[]`, not the retained size of `ApplyState` (no heap dump).
- **Gaps:** one analyser check failed through control noise (a 5 KB first-control reading on the 256 MiB node), with identical raw steps on both nodes; shakedowns showed the same numbers before run 1.
