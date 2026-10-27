# OVERFLOW_TRAILER_CAPACITY — verification solution  <!-- file: cases/overflow_trailer_capacity-createoverflowentry-overflowcollisions--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`AbstractTokenTreeBuilder.java:323`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/AbstractTokenTreeBuilder.java#L323) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the constant sizes a fixed on-disk trailer inside a fixed 4096-byte block and is a format-validity assertion (it throws when exceeded), not a limit that keeps node memory or disk bounded as load grows. |
| Ground | The check bounds a layout field (64 bytes of the 4096-byte leaf block, `TokenTreeBuilder.java:33`, `:36`) that is part of every leaf regardless of how many overflow offsets it holds; total index size is set by the number of tokens (blocks of 4096 bytes), and exceeding the limit produces an `AssertionError` at serialization (`AbstractTokenTreeBuilder.java:324`) rather than a throttled or truncated usage. Heap use of the SASI builder is governed by a different mechanism (flush at `maxMemorySize`, `PerSSTableIndexWriter.java:247`). |

> **Link rule.** Declaration (A1) and if statement (Entry pointer, A3) are permalinks at tag `cassandra-5.0.9`.

## A. Constraint trace

**A1. The constraint.** `OVERFLOW_TRAILER_CAPACITY`; kind: compile-time constant (interface field, implicitly `static final`), not a yaml entry, `-D` property or JMX value. First declared at [`TokenTreeBuilder.java:35`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/TokenTreeBuilder.java#L35) as `OVERFLOW_TRAILER_BYTES / OVERFLOW_ENTRY_BYTES`. Unit: number of 8-byte offset slots per leaf block. Default: `OVERFLOW_TRAILER_BYTES = 64` (`TokenTreeBuilder.java:33`) divided by `OVERFLOW_ENTRY_BYTES = Long.BYTES = 8` (`:34`), so 8. The same 64-byte trailer is subtracted in `TOKENS_PER_BLOCK = (BLOCK_BYTES - BLOCK_HEADER_BYTES - OVERFLOW_TRAILER_BYTES) / BLOCK_ENTRY_BYTES` (`:36`) with `BLOCK_BYTES = 4096` (`:29`), `BLOCK_HEADER_BYTES = 64` (`:31`), `BLOCK_ENTRY_BYTES = 2 * Long.BYTES` (`:32`); that gives (4096 - 64 - 64) / 16 = 248 tokens per leaf, so header + entries + trailer fill the block exactly. Not settable at runtime or startup; changing it needs a source edit and rebuild and would change the SASI on-disk token-tree format. The earlier trace (A1 input) checked out against these lines. SASI itself is gated by the yaml key `sasi_indexes_enabled` (default `false`, `Config.java:606`, `conf/cassandra.yaml:1992`), restart required.

**A2. What it caps.** Resource: disk (SASI index file, token-tree leaf trailer); transiently heap, because the offsets are held in a `LongArrayList overflowCollisions` per leaf (`AbstractTokenTreeBuilder.java:256`). Quantity compared: `overflowCollisions.size()`, the count of offsets already written to this leaf's overflow list, against 8 (`:323`).

**A3. Mechanism.**
1. `DynamicLeaf.serializeData` (`DynamicTokenTreeBuilder.java:182-185`) and `StaticTokenTreeBuilder` (`StaticTokenTreeBuilder.java:243`) call `createEntry(token, offsets)` for each token in the leaf (`AbstractTokenTreeBuilder.java:288`).
2. `createEntry` switches on the offset count (`:291-312`): 0 throws; 1 gives a simple or factored entry; 2 gives a packed entry only if both offsets are <= `Integer.MAX_VALUE` and at least one is <= `Short.MAX_VALUE` (`:303-306`), otherwise `createOverflowEntry` (`:309`); 3 or more always go to `createOverflowEntry` (`:311`).
3. `createOverflowEntry` (`:315`) lazily creates the list (`:317-318`), records the start index (`:320`), then for each offset checks [`overflowCollisions.size() == OVERFLOW_TRAILER_CAPACITY`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/AbstractTokenTreeBuilder.java#L323). True: `throw new AssertionError("cannot have more than 8 overflow collisions per leaf")` (`:324`); this is an explicit throw, so it fires with or without `-ea`. False: append the offset (`:326`).
4. The list is written after the entries as the trailer (`serializeOverflowCollisions`, `:272-276`, called from `serialize`, `:278-282`). `serializedSize()` for a single-block tree adds `overflowCollisionCount() * OVERFLOW_ENTRY_BYTES` (`:68-70`); multi-block trees are `numBlocks * BLOCK_BYTES` (`:72`).
- Bypasses/overshoot: the count is per leaf (the list is a field of `Leaf`, `:256`), so a tree may hold more than 8 overflow offsets in total across leaves. The check is `==` and the list only grows by one per iteration, so it cannot be skipped over. Nothing is truncated; the failure is an exception.
- Reachability: the offsets are data-file positions (`OnDiskIndexBuilder.java:185` passes `keyPosition`) keyed by Murmur3 token (`(Long) key.getToken().getTokenValue()`, same line), so more than 2 offsets for one token means two or more distinct partitions with the same token in one sstable, which is a hash collision. Two offsets that are both > `Short.MAX_VALUE` (32767) also overflow, using 2 slots.


The check itself is the if statement at [`AbstractTokenTreeBuilder.java:323`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/AbstractTokenTreeBuilder.java#L323).

**A4. Other consumers.** The same index component also holds the term dictionary and the token tree blocks (`OnDiskIndexBuilder`); SASI builder heap is estimated separately (`OnDiskIndexBuilder.java:148`, `:182`, `:194`, `:199-201`) and bounded by flush at `maxMemorySize` (1 GiB for FLUSH, `max_compaction_flush_memory_in_mb` for compaction, `PerSSTableIndexWriter.java:365-369`, `IndexMode.java:58`, `:186-188`). Memtables, commit log, row cache and the base-table sstables use the same disk/heap outside this constant.

**A5. Evidence beyond the source.** None. (Existing tests in `test/unit/org/apache/cassandra/index/sasi/disk/TokenTreeTest.java`: a grep for "overflow" returned no matches there, so the overflow assertion appears untested in that file; not verified elsewhere.)

## B. Verification solution

**B1. Claim under test.** `OVERFLOW_TRAILER_CAPACITY` does not cap memory or disk use: a leaf block occupies the same fixed 4096 bytes whatever its overflow-slot count from 0 to 8, total index size follows the token count, and exceeding 8 slots in one leaf produces an `AssertionError` instead of a bounded or truncated result. It would be refuted if disk or heap use were shown to track the overflow count or to be clamped at 8 slots without an error.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $WORK/cassandra-5.0.9/`; never build in the shared tree). Add `test/unit/org/apache/cassandra/index/sasi/disk/TokenTreeOverflowCapacityTest.java` (JUnit 4, in the copy). Build: `cd $WORK/cassandra-5.0.9 && ant build-test`; run: `ant testsome -Dtest.name=org.apache.cassandra.index.sasi.disk.TokenTreeOverflowCapacityTest`. Default test JVM options.

**B2b. Knobs.** No setting exists. Varied inputs: (a) number of tokens carrying overflowing offset sets in one leaf, k = 0, 4, 5 (two large offsets = 2 slots each, so 8 slots at k = 4, 10 at k = 5); (b) offsets per single token, n = 8 and 9; (c) leaf layout, 1 leaf vs 2 leaves. Why: 8 is the boundary at `:323`.

**B2c. Workload.** `DynamicTokenTreeBuilder` (`DynamicTokenTreeBuilder.java:48` `add(Long, long)`, then `finish()`, then `write(DataOutputBuffer)` at `AbstractTokenTreeBuilder.java:75`). Offsets larger than 32767 (for example 40000 and 50000 + token index) force overflow with 2 offsets. Cases:
- C1: 4 tokens x 2 large offsets (8 slots, at capacity), plus 20 tokens with 1 offset.
- C2: 5 tokens x 2 large offsets (10 slots).
- C3: 1 token with 8 offsets; C4: 1 token with 9 offsets.
- C5 (positive control for a bound that does bind): 248 tokens vs 249 tokens with one offset each; the 249th token must force a second leaf (`DynamicTokenTreeBuilder.java:109`).
- C6: 600 tokens where ranks 0-3 and 300-303 have 2 large offsets (8 slots in each of two leaves, 16 total; leaf boundaries computed per `DynamicTokenTreeBuilder.java:125-139`, exact boundaries not verified, so check with the leaf count).
- C7: 248 tokens all with 2 small offsets (< 32767), packed, zero slots.
- C8 (heap control): `OnDiskIndexBuilder.estimatedMemoryUse()` (`:199`) after adding 1000 and 10000 distinct terms via `add`.
Arithmetic: single-block size for C1 = 64 + 24 x 16 + 8 x 8 (`:68-70`).

**B2d. Observables and instruments.** Result of `write`: thrown exception or not; bytes written (`DataOutputBuffer.position()`); `serializedSize()` (`:63`) and `numBlocks`; recovered slot count = (`serializedSize()` - 64 - 16 x tokenCount) / 8 for single-block trees; `estimatedMemoryUse()`. The operand `overflowCollisions.size()` is a protected inner field and is not read directly (reflection on `Leaf` is the alternative).

**B2e. Procedure.** 1. Copy and build as in B2a. 2. Write the test running C1-C8, logging each observable. 3. Run `ant testsome ...`. 4. Delete `$WORK`.

**B2f. Predictions (before any run).** C1: no exception, recovered slots 8. C2: `AssertionError` with text "cannot have more than 8 overflow collisions per leaf". C3: passes, 8 slots; C4: `AssertionError`. C5: 248 tokens give one block, 249 give `numBlocks > 1` and a size of `numBlocks * 4096`. C6: no exception (cap is per leaf), each leaf block still 4096 bytes. C7: 0 slots, size = 64 + 248 x 16. Block size is the same 4096 for 0 and 8 slots in multi-block output. C8: estimate grows roughly linearly with terms (about 112 bytes + term length each, per `:182`), unaffected by overflow.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| C2/C4 throw, C1/C3 do not | Mechanism as traced (assertion at the boundary, no truncation) |
| C2/C4 do not throw, size clamped at 8 slots | Claim wrong: the cap would bound usage; A3 wrong |
| Block bytes differ between 0 and 8 slots in multi-block output | Claim wrong: usage tracks overflow |
| Block bytes constant at 4096 while slots vary; size grows only with token count (C5) | Claim confirmed (usage flat while the positive control, token count, moves) |
| C6 throws | Cap is not per leaf; A3 wrong |
| C5 does not add a block at 249, or C8 does not grow | Control did not move: not confirmed |
| Limit never reached (no exception in C2) | Not confirmed; check offsets > 32767 |

**B2h. Controls.** C5 and C8 show size and heap respond to a real driver; C7 vs C1 isolates the overflow path from the packed path; C3/C4 separate "per offset" from "per token" counting.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, Ant, a local copy of the tag (`ant jar` in the copy, not the shared tree). `cassandra.yaml` changes: `sasi_indexes_enabled: true`; `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` on local disk of known size (at least 5 GiB free, checked with `df`); `commitlog_total_space` set small (for example 256MiB) so commit-log growth is visible; heap `-Xms1G -Xmx1G`. Murmur3 is required because SASI casts the token value to `Long` (`OnDiskIndexBuilder.java:185`), so no other partitioner is usable. Collision keys: partitions that share one Murmur3 token must be produced; either (preferred, no node change) derive keys offline by inverting Murmur3 x64-128 h1 for a chosen 16-byte block (technique, not verified here), confirming every pair with `SELECT token(pk) FROM t WHERE pk = ...` in cqlsh; or (fallback, documented as altering the node) patch `Murmur3Partitioner.getToken` in the local copy to reduce the hash, which changes partitioner behavior and must be stated in results.

**B3b. Knobs.** Number of colliding partitions per token g and number of such tokens t sharing one SASI term, so total overflow slots in the one leaf = g x t (for g >= 3). Values: g x t = 8 (2 tokens x 4) and 9 (3 tokens x 3). Also workload size (rows) 10^5 vs 10^6 for the disk reading, and `max_compaction_flush_memory_in_mb` 1 vs 100 on the index (`IndexMode.java:58`) for the heap control.

**B3c. Workload.** Table `ks.t(pk text PRIMARY KEY, v text)`, `CREATE CUSTOM INDEX ON ks.t(v) USING 'org.apache.cassandra.index.sasi.SASIIndex'`. All rows use v = 'x' so one term and one token tree. First insert filler partitions (about 200 KB of data, so later partitions sit past data-file offset 32767), then the colliding groups, then `nodetool flush ks t`. Under 248 distinct tokens the tree is one leaf, so the trailer cap applies to the total g x t. Bulk rows: 10^5 and 10^6 small rows via `cassandra-stress` or CQL batches for the disk reading. Duration: minutes.

**B3d. Observables and instruments.** (1) `system.log` for the "cannot have more than 8 overflow collisions per leaf" error and flush outcome; (2) size of the SASI component files (`ls -l` on `*SI_*.db` in the sstable directory) and `du -sb` of the data directory and commit-log directory, sampled before and after flush, and every 5 s for 2 minutes after a failed flush; (3) heap via `jcmd <pid> GC.heap_info` and `jstat -gc <pid> 1000`; (4) `nodetool tablestats ks.t`. Not observable directly: the in-builder slot count.

**B3e. Procedure.** 1. Copy tree to local disk, `ant jar`. 2. Edit yaml as in B3a, start the node (`bin/cassandra -f` in background, record PID). 3. Create keyspace, table, index. 4. Insert fillers and the g x t = 8 collision set; `nodetool flush ks t`; record logs and file sizes. 5. Truncate; repeat with g x t = 9. 6. Record commit-log directory size over 2 minutes after the failed flush. 7. Repeat step 4 without collisions at 10^5 and 10^6 rows; record SI file sizes. 8. Heap control: with index option `max_compaction_flush_memory_in_mb` 1 then 100, run `nodetool compact ks t` on a multi-sstable table and record peak heap and the number of index segments. 9. `nodetool stopdaemon`/kill the PID, `pgrep -f CassandraDaemon`, delete data directories.

**B3f. Predictions.** g x t = 8: flush succeeds and an SI file exists. g x t = 9: the assertion message from `AbstractTokenTreeBuilder.java:324` appears in the log and no complete SI component for that flush is produced (what happens to the flush and commit-log segments afterwards is not verified and is the thing to observe). SI file size for the clean runs is a multiple of the 4096-byte blocks plus term data, growing with row count, with no dependence on whether the 8 slots are used. The heap control: smaller `max_compaction_flush_memory_in_mb` gives lower peak heap and more segments.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| 9 slots fail with the assertion, 8 succeed, disk/heap otherwise unchanged | Confirms the check is an error boundary, not a usage cap |
| 9 slots succeed with the file clamped | Claim wrong |
| SI size at 8 slots differs from the same index with 0 slots beyond what 8 x 8 bytes explains | Claim wrong: usage follows the constant |
| Failed flush leaves commit-log or memtable usage growing | Shows a consequence of the exception, not a cap; record it |
| SI size scales with rows while slot count is fixed; peak heap moves with `max_compaction_flush_memory_in_mb` (positive control) | Claim confirmed |
| Collisions could not be produced, or heap/size controls did not move | Not confirmed |

**B3h. Controls.** The clean no-collision runs and the 10x rows run are the positive control (disk follows tokens). The `max_compaction_flush_memory_in_mb` run is the known binding cap. Re-check every collision with `token(pk)`; keep v identical so only the slot count differs.

**B4. Risks and cleanup.** Disk: unit tier writes only in memory; cluster tier writes under the local data directories, bounded by the row counts above (keep 10^6 small rows to a few hundred MiB) and a stalled flush may let the commit log grow up to `commitlog_total_space` (the Cassandra process can refuse writes; stop it then). No shared storage. Processes: stop the node (`nodetool stopdaemon`), confirm with `pgrep -f CassandraDaemon`, stop `jstat` loops; delete `$WORK` and all data directories. The patched-partitioner fallback must never be used on the shared tree.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/TokenTreeBuilder.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/AbstractTokenTreeBuilder.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/DynamicTokenTreeBuilder.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/StaticTokenTreeBuilder.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/conf/IndexMode.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java (line 606, by grep)
- /users/jason92/cassandra-5.0.9/conf/cassandra.yaml (line 1992, by grep)
- /users/jason92/cassandra-5.0.9/test/unit/org/apache/cassandra/index/sasi/disk/TokenTreeTest.java (grep only)

## D. Stage-4 feedback

`none yet`
