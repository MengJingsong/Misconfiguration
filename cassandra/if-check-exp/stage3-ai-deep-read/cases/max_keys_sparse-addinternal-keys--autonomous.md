# MAX_KEYS_SPARSE — verification solution  <!-- file: cases/max_keys_sparse-addinternal-keys--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`OnDiskIndexBuilder.java:598`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java#L598) (`if (keys.getTokenCount() > MAX_KEYS_SPARSE)` in `MutableDataBlock.addInternal`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the constant is a SPARSE-format validity limit on keys per term; a term over it makes the index build fail, it does not bound how much heap or disk an index uses. The memory-significant bound is a different quantity (`estimatedMemoryUse()` against `maxMemorySize`). |
| Ground | `MAX_KEYS_SPARSE` caps a count of distinct partition tokens per one term of a SPARSE-mode on-disk index (5), and only to reject larger terms (throws, [`OnDiskIndexBuilder.java:598-600`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java#L598-L600)). It never throttles, evicts or truncates; the memory used while the term set is being built (OnDiskIndexBuilder.java:182, 194) is bounded by the separate flush threshold (PerSSTableIndexWriter.java:247, 365-368), and the file size is a function of the data indexed. Total usage therefore scales with the amount of indexed data whatever the value of 5. |

> **Link rule.** Declaration and if statement are linked below; other citations are plain `file:line` in the pinned tree (all under `src/java/org/apache/cassandra/index/sasi/` unless a full path is given). Every line cited was re-opened and checked.

## A. Constraint trace

**A1. The constraint.** `MAX_KEYS_SPARSE`: a hard-coded constant (not a yaml entry, `-D` property, JMX or runtime-queried value). First declared at [`OnDiskIndexBuilder.java:575`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java#L575): `private static final int MAX_KEYS_SPARSE = 5;` in the private nested class `MutableDataBlock` (declared at line 573). Unit: number of distinct partition tokens (keys) a single indexed term maps to. Default 5, a literal with no derivation. Not settable by any means; changing it needs a source edit and rebuild (so "restart" is moot).
Corrections to the earlier trace: the `mode == Mode.SPARSE` test is at line 596 (not 594); the other constants are at lines 127-129 as stated, but note there is a second hard-coded `5` at line 646 (`ptrLength`) that is not tied to `MAX_KEYS_SPARSE` by name. The earlier trace's claim that `getTokenCount()` is returned "from the `tokenCount` field in StaticTokenTreeBuilder.java:101-104" is true for that class, but the builders reaching line 598 in the normal write path are `DynamicTokenTreeBuilder` (see A3), whose `tokenCount` is set at DynamicTokenTreeBuilder.java:103.

**A2. What it caps.** Not heap, off-heap or disk directly. It caps the number of token entries a SPARSE-mode term may have, the quantity compared being `TokenTreeBuilder.getTokenCount()` (TokenTreeBuilder.java:72; AbstractTokenTreeBuilder.java:60-63; DynamicTokenTreeBuilder.java:99-103 sets it to `tokens.size()`, the number of distinct tokens). SPARSE mode stores up to 5 tokens inline in the term block and nothing else per term (`writeTerm(term, keys)`, lines 649-655; `ptrLength` lines 643-649), so the limit is what lets the SPARSE layout stay compact; it bounds the size of one term entry (at most 1 + 8*5 bytes of token data), not the file.

**A3. Mechanism.**
1. SASI indexes are creatable only if `sasi_indexes_enabled: true` (Config.java:606, default false; CreateIndexStatement.java:122-123). SPARSE mode is accepted only for non-literal, non-analyzed columns (SASIIndex.java:175-182).
2. Rows indexed go through `PerSSTableIndexWriter.Index.add` (PerSSTableIndexWriter.java:205-251), which calls `OnDiskIndexBuilder.add` (line 243). `add` stores term -> `DynamicTokenTreeBuilder` in a HashMap and adds the partition token (OnDiskIndexBuilder.java:166-196). Nothing in `add` checks the per-term key count.
3. When `estimatedMemoryUse()` reaches `maxMemorySize` the builder is flushed as a segment (PerSSTableIndexWriter.java:247-250); `maxMemorySize` is 1 GiB for FLUSH and `max_compaction_flush_memory_in_mb` (default 0.15 GiB) otherwise (PerSSTableIndexWriter.java:365-368; conf/IndexMode.java:58-60, 185-194).
4. `OnDiskIndexBuilder.finish(File)` (line 238) -> `finish(Descriptor, File)` builds a sorted term iterator (IntegralSA for SPARSE, since SuffixSA is used only for CONTAINS, lines 253-255) -> `finish(..., TermIterator)` (line 264), which for SPARSE creates `DataBuilderLevel` + `MutableDataBlock` (lines 289-290) and feeds every term to `addTerm` (line 204).
5. `MutableDataBlock.addInternal(term)` (line 594): if `mode == Mode.SPARSE` (line 596) the **if statement** is [`OnDiskIndexBuilder.java:598`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java#L598) `if (keys.getTokenCount() > MAX_KEYS_SPARSE)`.
   - **True (count 6 or more):** throws `IOException("Term - '%s' belongs to more than %d keys in %s mode, which is not allowed.")` (lines 599-600). `finish` catches `IOException` and rethrows `FSWriteError` (lines 316-318); the writer is closed in `finally` (line 322). In the segment path the callable catches `Exception | FSError`, logs "Failed to build index segment" and returns null (PerSSTableIndexWriter.java:268-271), so that segment contributes nothing; in the final merge path the catch at line 326 logs "Failed to flush index" and `tryDelete`s the output file (lines 327-328). The base SSTable is not affected by this code; whether the SSTable is still otherwise written is not verified here.
   - **False (count 0 to 5):** `writeTerm(term, keys)` writes the tokens inline (lines 602, 651-656) and `combinedIndex.add(keys)` (line 612) accumulates them for the block's trailing token tree.
6. Non-SPARSE modes skip the test and write a pointer plus a token tree (lines 606-610), so no per-term key limit applies there.
Bypass or overshoot: counts are per segment. Each flushed segment is built separately (PerSSTableIndexWriter.java:254-275), so a term may be under 5 in every segment yet over 5 when the segments are merged by `CombinedTermIterator` (line 321-323) with a new SPARSE builder, which then fails at line 598 (the token tree built by `CombinedTerm.getTokenTreeBuilder`, CombinedTerm.java:58-61 is a `StaticTokenTreeBuilder`, whose `getTokenCount` is StaticTokenTreeBuilder.java:101-104; that this exact path reaches line 598 for merged terms is inferred, not verified by execution).

**A4. Other consumers.** Heap: the in-memory `terms` HashMap and token trees of every active SASI index builder (OnDiskIndexBuilder.java:148, 166-196), the flush executors (PerSSTableIndexWriter.java:64-72), memtable-side SASI structures, memtables, key and chunk caches, bloom filters, etc. Off-heap/mmap: the opened `OnDiskIndex` files. Disk: the SSTable components, commit log, hints and other index files. None of these is governed by `MAX_KEYS_SPARSE`.

**A5. Evidence beyond the source.** SASI usage warning text referenced from the create-index path (SASIIndex.USAGE_WARNING, CreateIndexStatement.java:203-204). Source tests that build SPARSE indexes directly: test/unit/org/apache/cassandra/index/sasi/disk/OnDiskIndexTest.java:311-313 (`testSparseMode`), 443, 569, 597; whether any existing test asserts the over-5 failure is not verified. Public docs (Cassandra "SASI indexes" documentation, SPARSE mode described as for terms with few keys, e.g. numeric timestamps): not re-fetched in this session, so no link is given. No issue numbers cited.

## B. Verification solution

**B1. Claim under test.** Raising the number of keys per term across the value 5 does not change how much memory or disk the SASI index builder uses per entry: usage (builder `estimatedMemoryUse()`, bytes written) grows linearly with the amount indexed on both sides of 5, and the only effect of crossing 5 in SPARSE mode is that the build of that index fails; usage is bounded instead by the flush threshold, a different cap. Falsified if usage per entry changes shape at 5 in a way that follows the constant, or if crossing 5 truncates or limits growth rather than failing.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Copy the tag to local disk (`rsync -a <tree>/ $WORK/cassandra-5.0.9/`); never build in the shared tree. `cd $WORK/cassandra-5.0.9 && ant jar` (or `ant build-test`). Add one new test class in the copy only: `test/unit/org/apache/cassandra/index/sasi/disk/SparseKeysProbeTest.java`, run with `ant testsome -Dtest.name=org.apache.cassandra.index.sasi.disk.SparseKeysProbeTest`. JVM options: `-Xmx512m`, plus `-XX:+UseSerialGC` so heap deltas are less noisy. Initialise the partitioner with `DatabaseDescriptor.daemonInitialization()` (as OnDiskIndexTest does; not re-checked).

**B2b. Knobs.** (1) K = number of distinct partition keys per indexed term: 1, 4, 5, 6, 7, 50, 1000. Why: 5 is the limit, 4 and 6 straddle it, large K shows scaling. (2) Mode: SPARSE (limit applies) and PREFIX (control, no limit). (3) Number of distinct terms T: 10 000 (fixed), plus a second run with T = 20 000 for the scaling check. All set as test parameters. The constant itself is not changed.

**B2c. Workload.** Directly construct `new OnDiskIndexBuilder(UTF8Type.instance, Int32Type.instance, Mode.SPARSE)` (as OnDiskIndexTest.java:569). For each term i in [0,T) call `builder.add(Int32Type.instance.decompose(i), Murmur3Partitioner.instance.decorateKey(UTF8Type.instance.decompose("k" + j)), position)` for K distinct keys j, using the same K keys for every term so tokens are distinct per term. Arithmetic: per term, count = K, so line 598 compares K > 5; with T*K adds, `estimatedMemoryUse()` increases by (64+48+4) once per term and (60+40+8) per add (OnDiskIndexBuilder.java:182, 194), i.e. predictable linearly in T and K.

**B2d. Observables and instruments.** (a) `builder.estimatedMemoryUse()` after the adds (OnDiskIndexBuilder.java:199-202), the builder's own heap estimate. (b) Whether `builder.finish(File)` returns or throws `FSWriteError` with cause message "belongs to more than 5 keys" (lines 599, 316-318). (c) Index file length in a local temp directory on success. (d) Actual heap: `Runtime.totalMemory()-freeMemory()` after `System.gc()` before/after (coarse; cannot isolate the builder exactly). Cannot be observed directly: the true on-heap size of the builder (only the estimate; the estimate is hard-coded constants, so it validates scaling not accuracy).

**B2e. Procedure.**
1. Build as in B2a in a local copy.
2. For mode in {SPARSE, PREFIX}, for K in the list, T = 10 000: create a fresh builder, run the workload, record (a); call `finish(tmpFile)` in try/catch, record success or the exception message, and (c).
3. Repeat for T = 20 000 at K = 4, 6 (PREFIX only for K = 6).
4. Delete all temp files; confirm the JVM exited.

**B2f. Predictions (before any run).** (a) For both modes, `estimatedMemoryUse()` equals T*116 + T*K*108 for the workload (formula from lines 182 and 194), identical at K = 5 and K = 6 apart from the extra K term: no break at 5. (b) SPARSE: K <= 5 finish succeeds; K >= 6 throws `FSWriteError` caused by the IOException of line 599-600. PREFIX: finish succeeds for every K. (c) File length where finish succeeds grows with T and K, with no relation to the value 5 (PREFIX file at K = 6 or 1000 is larger than at K = 5). (d) Doubling T doubles (a).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| (a) linear in T and K across 5; SPARSE fails at K >= 6 only; PREFIX with same K succeeds and its usage keeps growing | Claim confirmed: constant is a pass/fail validity limit, usage does not follow it |
| SPARSE succeeds at K = 6 or 7 | Mechanism not as traced (e.g. count is not distinct tokens, or tokens collided); recheck token distinctness first, otherwise A3 is wrong |
| (a) or file length stops growing, or is capped, above K = 5 in SPARSE | Claim refuted: the constant bounds usage |
| SPARSE fails but with a different cause (e.g. term too large, partitioner not initialised) | Not confirmed; fix the harness |
| Positive control (B2h) does not move usage | Not confirmed; the harness cannot see usage change |

**B2h. Controls.** Positive control: the flush threshold, which is a cap known to bind. Use `PerSSTableIndexWriter` is heavy, so instead emulate its rule (PerSSTableIndexWriter.java:247): add entries to a PREFIX builder until `estimatedMemoryUse() >= maxMemorySize` with maxMemorySize = 8 MiB, then finish that builder as a segment and start a new one; the number of segments produced must grow in proportion to indexed volume and each builder's estimate stays at or under about 8 MiB plus one add, showing a cap that really bounds memory. Mode control: PREFIX shows the same workload without line 598. K = 1 and 5 show the accept path. Same JVM, same T, same keys for both modes.

### B3. Cluster tier

**B3a. Environment and build.** One node (a second node optional) on a local-disk directory of known size (at least 20 GB free, nothing on shared storage). JDK 11. Copy the tag to local disk, `ant jar`. In the copy's `conf/cassandra.yaml`: `sasi_indexes_enabled: true`, `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` under `$WORK/data`, `num_tokens: 1`, `memtable_allocation_type: heap_buffers`. JVM: `-Xms1G -Xmx1G` in `conf/jvm11-server.options` (or the equivalent heap settings), G1 (default). Start with `bin/cassandra -f` in the background, log to `$WORK/logs`.

**B3b. Knobs.** (1) Keys (partitions) per indexed value K: 5 and 6 (straddle the limit), then 1000. (2) Index mode on the indexed column: `SPARSE` vs `PREFIX` (control; PREFIX allowed on int columns). (3) `max_compaction_flush_memory_in_mb` index option on a SPARSE or PREFIX index for the positive control (e.g. 1 vs 64). Set through `CREATE CUSTOM INDEX ... USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode':'SPARSE'}` (option name in conf/IndexMode.java:58). The constant itself cannot be changed without rebuilding; K is the knob.

**B3c. Workload.** Schema: keyspace `ks` (SimpleStrategy rf 1); `CREATE TABLE ks.t_sparse (id int PRIMARY KEY, v int)`, `ks.t_prefix` the same; an index on `v` in each (SPARSE and PREFIX). Insert N = 60 000 rows with `v = id / K`, so each value of `v` is shared by exactly K partitions (token count K per term). Run for K = 5, K = 6, K = 1000 as separate tables or truncated runs. Use `cqlsh` batches of single-partition inserts or `cassandra-stress` with a fixed seed; then `nodetool flush ks`. Duration: a few minutes per run. Arithmetic: terms = N/K, each with K partition tokens, so at K = 6 every term violates line 598.

**B3d. Observables and instruments.** (1) `system.log` lines "Failed to build index segment" / "Failed to flush index" (PerSSTableIndexWriter.java:270, 327) with the cause message from line 599-600. (2) Disk: `du -sb` of the table directory and `ls -l` of the SASI index component files (`*SI_*.db`) after flush. (3) Heap: `jcmd <pid> GC.heap_info` or JMX `java.lang:type=Memory HeapMemoryUsage` sampled every second during insert and flush, peak after each flush. (4) Behaviour: `SELECT * FROM ks.t_sparse WHERE v = 3` on the failed table, to see whether the index answers (outcome not verified). Cannot be observed: per-builder heap in isolation (only whole-node heap).

**B3e. Procedure.**
1. Build and configure as in B3a; start the node; wait until `nodetool status` shows UN.
2. Create the schema (B3c) with the SPARSE index on `t_sparse` and the PREFIX index on `t_prefix`.
3. Start the heap sampler (script looping `jcmd <pid> GC.heap_info`, output to `$WORK/heap.csv`).
4. For K in {5, 6, 1000}: truncate both tables, insert N rows each with `v = id / K`, `nodetool flush ks`, wait 30 s, record log lines, file sizes, heap peak.
5. For the positive control: recreate the PREFIX index with `max_compaction_flush_memory_in_mb` = 1, insert the K = 6 data, run `nodetool compact ks t_prefix` (compaction source uses the option, PerSSTableIndexWriter.java:365-368) and count `_N` segment files created in the log/dirs; repeat with 64.
6. Stop the sampler, `nodetool drain`, stop the node, `pgrep -f CassandraDaemon` must be empty, then `rm -rf $WORK/data`.

**B3f. Predictions (before any run).** K = 5: both tables get an index file; no error in the log. K = 6 and K = 1000: `t_sparse` logs "belongs to more than 5 keys in SPARSE mode" and has no usable SASI file for that SSTable, `t_prefix` indexes fine and its index file is larger at K = 1000 than at K = 5 for the same N or comparable (depends on token tree sharing; not predicted numerically). Peak heap during flush is similar for `t_sparse` and `t_prefix` at the same N (differences small relative to N-driven changes); it does not step up or down at K = 5 -> 6 beyond what a failed versus succeeded write explains. Positive control: with `max_compaction_flush_memory_in_mb` = 1 the compaction produces more segments than with 64, with the PREFIX index.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| SPARSE fails only for K >= 6 with the line-599 message; PREFIX unaffected; heap peaks track N not K | Claim confirmed: constant is a pass/fail rule, not a resource cap |
| Heap or disk for SPARSE changes shape exactly at K = 6 in a way that is bounded (not a failure) | Claim refuted: usage follows the constant |
| SPARSE succeeds at K = 6 | Mechanism not as traced (SASI flush path differs or tokens collided); recheck A3 |
| Positive control: smaller `max_compaction_flush_memory_in_mb` gives more segments / lower per-segment size | Control works: a real cap is visible with this harness |
| Positive control shows no change | Not confirmed; harness cannot see a known cap, or the compaction path was not exercised |
| No flush happened / limit never reached | Not confirmed |

**B3h. Controls.** PREFIX table with identical data (no line-598 check); K = 5 versus K = 6 with the same N, same heap, same flush point; positive control via the index option; repeat each K twice to see run-to-run heap spread before reading any difference; confirm via log that the SSTable flush itself succeeded so differences are index-related.

**B4. Risks and cleanup.** Unit tier: temp index files in the local `$WORK/tmp` only; delete after each run; no process left once the test JVM exits. Cluster tier: all directories on local disk of known size, N = 60 000 small rows is well under 1 GB; stop the sampler and the node, verify with `pgrep -f CassandraDaemon` and `pgrep -f heap`, remove `$WORK`. Never build or write in the shared source tree. No production data. A failed SASI build can leave a partial index file; deleting `$WORK/data` removes it.

## C. Sources read

- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/INSTRUCTIONS.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/playbook-autonomous.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/_TEMPLATE-autonomous.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-in/99.md
- src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java
- src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java
- src/java/org/apache/cassandra/index/sasi/disk/TokenTreeBuilder.java, AbstractTokenTreeBuilder.java, DynamicTokenTreeBuilder.java, StaticTokenTreeBuilder.java
- src/java/org/apache/cassandra/index/sasi/SASIIndex.java, conf/IndexMode.java, sa/IntegralSA.java, utils/CombinedTerm.java
- src/java/org/apache/cassandra/config/Config.java (line 606), src/java/org/apache/cassandra/cql3/statements/schema/CreateIndexStatement.java
- conf/cassandra.yaml (sasi_indexes_enabled), test/unit/org/apache/cassandra/index/sasi/disk/OnDiskIndexTest.java (grep and excerpt only)

## D. Stage-4 feedback

`none yet`
