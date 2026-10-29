# TOKENS_PER_BLOCK — verification solution  <!-- file: cases/tokens_per_block-add-pos--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`AbstractTokenTreeBuilder.java:520`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/AbstractTokenTreeBuilder.java#L520) (`if (pos == TOKENS_PER_BLOCK)` in `InteriorNode.add(Long, InteriorNode, InteriorNode)`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: `TOKENS_PER_BLOCK` is a fixed fan-out of one 4096-byte tree block; it decides how many nodes a SASI token tree is cut into, not how many tokens or bytes the builder may hold. |
| Ground | The constant sizes a node, never a total. The number of tokens held is set by the data added to `DynamicTokenTreeBuilder`'s `TreeMap` (`DynamicTokenTreeBuilder.java:32`), and the in-memory SASI index build is bounded by a different quantity, `OnDiskIndexBuilder.estimatedMemoryUse()` against `maxMemorySize` (`PerSSTableIndexWriter.java:247`, `:365-369`). Changing the constant only re-slices the same tokens into more or fewer blocks (disk bytes scale with the number of blocks, but there is no cap). |

> **Link rule.** Followed: the declaration (A1) and the if statement (Entry pointer, A3) are permalinks at tag `cassandra-5.0.9`; other citations are plain `file:line`. All paths below are under `src/java/org/apache/cassandra/index/sasi/` unless stated.

## A. Constraint trace

**A1. The constraint.** `TOKENS_PER_BLOCK`; kind: compile-time constant (an implicit `public static final int` field of an interface). First declared at [`TokenTreeBuilder.java:36`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/TokenTreeBuilder.java#L36): `(BLOCK_BYTES - BLOCK_HEADER_BYTES - OVERFLOW_TRAILER_BYTES) / BLOCK_ENTRY_BYTES`. Operands, all in `disk/TokenTreeBuilder.java`: `BLOCK_BYTES = 4096` (:30), `BLOCK_HEADER_BYTES = 64` (:31), `BLOCK_ENTRY_BYTES = 2 * Long.BYTES` = 16 (:32), `OVERFLOW_TRAILER_BYTES = 64` (:33). Value: (4096 - 64 - 64) / 16 = 248 tokens per block. Unit: tokens (entries) per on-disk tree block. Not settable by yaml, `-D`, JMX or index option; changing it needs a recompile, and it is baked into the SASI index file layout.

Correction to the earlier trace (the A1 text in the input): it placed the constant operands in `AbstractTokenTreeBuilder.java` lines 30-33 and `MAX_OFFSET` at line 38. They are in `TokenTreeBuilder.java` (the interface), and `MAX_OFFSET = (1L << 47) - 1` is at `TokenTreeBuilder.java:37`; the check on it is at `AbstractTokenTreeBuilder.java:297` (verified). `AbstractTokenTreeBuilder.java:30-33` are not those constants. The rest of the earlier trace (value 248, not tunable, `pos = tokens.size()` at :519, `split()` at :522) holds.

**A2. What it caps.** Nothing at the level of total memory or disk. It caps the number of tokens in one interior node's `tokens` list (`pos == TOKENS_PER_BLOCK`, :519-520), and sizes the initial capacity of two per-node lists (`AbstractTokenTreeBuilder.java:481-482`). Quantity compared: `tokens.size()` of one `InteriorNode`, per node. Each full node maps to one 4096-byte block (`serializedSize()`, :65-73, uses `numBlocks * BLOCK_BYTES` when more than one block).

**A3. Mechanism.**
1. `DynamicTokenTreeBuilder.constructTree()` (`disk/DynamicTokenTreeBuilder.java:101-161`): if `tokenCount <= TOKENS_PER_BLOCK` (:109) the tree is a single leaf (root = leaf). Otherwise it creates an `InteriorNode` root (:118) and walks all tokens, cutting a leaf every `TOKENS_PER_BLOCK` tokens (:127) and calling `rightmostParent.add(leaf)` (:142).
2. `InteriorNode.add(Leaf)` (`AbstractTokenTreeBuilder.java:542-571`): when `position == TOKENS_PER_BLOCK + 1` (:545) the node is full of children, so `split()` (:547) and add to the new rightmost parent; otherwise attach the leaf and append its smallest token (:553-568).
3. `InteriorNode.split()` (:573-593) calls `splitBlock()` (:595-633; `splitPosition = TOKENS_PER_BLOCK - 2`, :597), creates a new root if `parent == null` (:581-588), and calls `parent.add(middleValue, leftChild, sibling)` (:590).
4. The entry check: [`AbstractTokenTreeBuilder.java:520`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/AbstractTokenTreeBuilder.java#L520) `if (pos == TOKENS_PER_BLOCK)` inside `InteriorNode.add(Long, InteriorNode, InteriorNode)` (:517-540). True: `split()` the node and add into the new sibling (:522-523), possibly cascading upward, increasing `numBlocks` (:587, :630). False: insert the token and children at `pos` (:528-538).
5. Outcomes at the limit: never an error and never a rejection; the tree gets one more node (and possibly one more level). There is no path that stops accepting tokens. Only a separate hard limit exists, `MAX_OFFSET` (`TokenTreeBuilder.java:37`), enforced by an `AssertionError` at `AbstractTokenTreeBuilder.java:297-298`; it bounds a data-file offset, not memory or disk.
6. Serialisation: `write()` (:75-102) emits `BLOCK_BYTES` (4096) per node through a single reused `ByteBuffer.allocate(BLOCK_BYTES)` (:77).
Observation on the comparison at :520: since `pos` can only reach `TOKENS_PER_BLOCK` by additions in `add`, and the split moves tokens out, the node never exceeds the constant. This is node-local only.

**A4. Other consumers.** The dominant memory of a SASI index build is not governed by this constant: the `TreeMap<Long, LongSet>` of tokens per term in each `DynamicTokenTreeBuilder` (`disk/DynamicTokenTreeBuilder.java:32`), the `terms` map in `OnDiskIndexBuilder` (:143, :175-178), and the suffix arrays built at `OnDiskIndexBuilder.java:254-257`. The builder's flush trigger is `estimatedMemoryUse()` (:199-202) compared to `maxMemorySize` at `PerSSTableIndexWriter.java:247`, where `maxMemorySize` is 1 GiB (1073741824) for `OperationType.FLUSH` and the index option `max_compaction_flush_memory_in_mb` otherwise (`PerSSTableIndexWriter.java:365-369`; option parsed at `conf/IndexMode.java:58, 186-188`, default 0.15 GiB at :59-60, values above 100 GiB reset to the default at :190-193). Note that the estimate adds a fixed 64 + 48 + term size per new term (`OnDiskIndexBuilder.java:182`) and 60 + 40 + 8 per add (:194, verified as the next line after the `tokens.add`; not re-opened beyond that line): it does not include `TOKENS_PER_BLOCK`. Disk: SASI file size is determined by term count, token count and the block count the constant produces; data files and other SSTable components are independent.

**A5. Evidence beyond the source.** none (no issue or documentation relied on).

## B. Verification solution

**B1. Claim under test.** (Negative) Changing or reaching `TOKENS_PER_BLOCK` does not cap the memory a SASI index build holds or the disk it writes: the builder keeps accepting tokens past the node capacity by splitting nodes, and the resource used tracks the number of tokens/terms added (and `max_compaction_flush_memory_in_mb` for flush control), not the constant. The only thing the constant fixes is the per-node size (one 4096-byte block) and hence the node count `~ tokens / 248`.

### B2. Unit tier

> **Amended 2026-10-28 (stage-4 audit): see B5, which overrides this section where they conflict.**

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $WORK/c509/`), never build in the shared tree. `cd $WORK/c509 && ant jar` (downloads dependencies through Ant/Maven resolver if the cache is empty). Write the driver as a JUnit test or a main class in package `org.apache.cassandra.index.sasi.disk` (so protected members are visible) under `$WORK/c509/test/unit/org/apache/cassandra/index/sasi/disk/TokenTreeCapProbe.java`. Run with `ant testsome -Dtest.name=TokenTreeCapProbe` or with the jar on the classpath. JVM options: `-Xmx512m -XX:+UseSerialGC` and `-Xlog:gc` for the memory run.

**B2b. Knobs.** (1) Number of distinct tokens `N` added to one `DynamicTokenTreeBuilder`: 248 (exactly one block), 249 (one over), 248*10, 248*248, 248*248*4 (forces a second interior level). (2) Constant variant: rebuild a second copy with `TOKENS_PER_BLOCK` forced to a smaller value (e.g. change the line `TokenTreeBuilder.java:36` to `124` and rebuild into a separate directory; this is the only way to vary a compile-time constant, and it makes the output format incompatible, so use the copy for in-process measurement only). (3) Positive control knob: `OnDiskIndexBuilder` term count / term size, whose estimate feeds `maxMemorySize` (`PerSSTableIndexWriter.java:247`).

**B2c. Workload.** Create `new DynamicTokenTreeBuilder()` and call `add(Long token, long keyPosition)` (`DynamicTokenTreeBuilder.java:48`) for `N` ascending tokens, then `finish()` (`AbstractTokenTreeBuilder.java:52-58`), read `getTokenCount()` (:60) and `serializedSize()` (:65), and `write()` into a `DataOutputBuffer`. Arithmetic: for `N <= 248`, one block (`DynamicTokenTreeBuilder.java:109`) with `serializedSize() = 64 + 16*N` plus overflow entries (:67-70); for `N = 249` and above, `numBlocks` grows by about `N/248` leaves plus interior nodes, and `serializedSize() = numBlocks * 4096` (:72). Positive control: build an `OnDiskIndexBuilder` (constructor :150) and call `add(term, key, pos)` (:165) with M distinct terms of 16 bytes; `estimatedMemoryUse()` increases by 64 + 48 + 16 per new term (:182), so M = 1,000,000 gives about 128 MB estimated, which exceeds a 100 MB `maxMemorySize`.

**B2d. Observables and instruments.** (i) `getTokenCount()`, `serializedSize()`, and the length of the serialised bytes; the block count `serializedSize()/4096` via the protected `numBlocks` field (accessible from the same package). (ii) Heap after `System.gc()` via `Runtime.totalMemory()-freeMemory()` or `jcmd <pid> GC.class_histogram` and `-Xlog:gc`, before the build and after holding the builder reachable. (iii) `OnDiskIndexBuilder.estimatedMemoryUse()` for the control. Not directly observable: per-node list capacity (an `ArrayList` internal array); infer from the histogram (`java.lang.Object[]` and `ArrayList` counts).

**B2e. Procedure.**
1. Build the baseline copy and the `TOKENS_PER_BLOCK=124` copy.
2. For each `N`, in a fresh JVM: record heap baseline after `System.gc()`; add `N` tokens; `finish()`; record `getTokenCount()`, `numBlocks`, `serializedSize()`; `System.gc()`; record heap with the builder still referenced; serialise and record bytes written.
3. Repeat in the 124 copy.
4. Control run: `OnDiskIndexBuilder` with M terms, record `estimatedMemoryUse()` and heap, in baseline copy only.
5. Stop all JVMs (`pgrep -f TokenTreeCapProbe` empty).

**B2f. Predictions (before any run).** Baseline: `getTokenCount() == N` for every `N` (no token is dropped or rejected at 248); `numBlocks == 1` at N = 248 and greater than 1 at N = 249; the interior-node `tokens.size()` never exceeds 248 (assert on a walk of `levelIterator()`); `serializedSize()/4096` is approximately `N/248` plus interior levels. In the 124 copy: the same `getTokenCount()`, the block count roughly doubles, serialised bytes grow accordingly (more padding), and the heap held by the `TreeMap` of tokens is within noise of the baseline for the same `N` (the `TreeMap` dominates, B2d). Control: `estimatedMemoryUse()` grows linearly with M and does not depend on `TOKENS_PER_BLOCK`.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `getTokenCount() == N` for all N, nodes capped at 248, blocks grow with N, heap tracks N and not the constant | Claim confirmed: the constant is node fan-out only |
| Tokens dropped, exception, or builder refuses to grow at N > 248 | Claim refuted: the constant caps usage |
| Heap/bytes for the same N differ materially (beyond block padding) between 248 and 124 variants in a way that scales as a limit, not as block count | Constant affects usage; claim refuted for memory (disk effect via block count still not a cap) |
| Heap flat in the constant while `estimatedMemoryUse()` (control) rises with M | Claim confirmed (positive control moved, constant did not) |
| Control `estimatedMemoryUse()` did not move or N never exceeded 248 | Not confirmed; rerun with larger M/N |

**B2h. Controls.** Same `N` and token distribution in both variants; fixed seed; `-Xmx` identical; GC forced before each reading (several samples, take the median); positive control as in B2c; check the 124 build differs only in line 36.

### B3. Cluster tier

> **Amended 2026-10-28 (stage-4 audit): see B5, which overrides this section where they conflict.**

**B3a. Environment and build.** One node, JDK 11, Ant, build from a local copy (`ant jar`, `ant artifacts` not required). Data, commit log and hints directories on local disk of known size (for example a 20 GB partition) set through `data_file_directories`, `commitlog_directory`, `hints_directory` in a copied `cassandra.yaml`; `cassandra.yaml` change: `sasi_indexes_enabled` is not assumed to exist in 5.0.9 (not verified; check the yaml and `Config.java` first and use the default behaviour if absent). JVM: `-Xms1g -Xmx1g` (small heap so growth is visible), `-XX:+UseG1GC`, GC log on. Client: `cqlsh`/`cassandra-stress` from the same tree.

**B3b. Knobs.** (1) Row count with a unique indexed value per row (distinct tokens per term is not needed; many distinct terms is the dominant case): 1M and 4M rows. (2) The SASI index option `max_compaction_flush_memory_in_mb` (`conf/IndexMode.java:58`), e.g. 16 vs 1024, as the positive control that is known to bind. (3) `TOKENS_PER_BLOCK`: only through a rebuilt node (124 variant) for comparison; both builds run the same procedure.

**B3c. Workload.** Table `t(pk bigint primary key, v text)`, `CREATE CUSTOM INDEX ON t(v) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode': 'CONTAINS', 'max_compaction_flush_memory_in_mb': '16'}`. Insert rows whose `v` is the same short constant for all rows (so one term holds N tokens: the case that exercises the tree: 1M tokens ≈ 4033 leaves of 248) and, separately, unique values per row (many terms, few tokens each). Flush with `nodetool flush`, then `nodetool compact` (the compaction path uses the option at `PerSSTableIndexWriter.java:365-369`). Duration: minutes per run. Reachability: 1M tokens in one term gives `1,000,000/248 ≈ 4033` leaf blocks plus interior nodes, so the constant is exercised many times over.

**B3d. Observables and instruments.** (i) Disk: size of `*SI_*.db` SASI component files in the table directory (`du -b`). (ii) Heap: `jcmd <pid> GC.heap_info` and `jstat -gc <pid> 1000` peak; `-Xlog:gc`. (iii) `nodetool tablestats` (index size/off-heap fields). Not directly observable: per-node block counts (derive from file size / 4096). Peak heap during flush/compaction is sampled once a second.

**B3e. Procedure.**
1. Copy tree to local disk, build baseline and 124 variant jars into separate directories; set yaml paths to local disk.
2. Start the node (`bin/cassandra -f` in the background, record PID); create keyspace, table, index.
3. Load the constant-value workload; `nodetool flush`; record SASI file bytes and peak heap; `nodetool compact`; record again.
4. Drop table; repeat for the unique-value workload and for `max_compaction_flush_memory_in_mb` 16 vs 1024 (control).
5. Stop node (`kill <pid>`, verify with `pgrep -f CassandraDaemon`), switch to the 124 variant, repeat 2-4.

**B3f. Predictions.** SASI file bytes for the constant-value workload track `tokens/248` blocks times 4096 in the baseline (roughly 16 bytes per token) and roughly twice that block count in the 124 variant; no run shows a ceiling or an error at any token count. Peak heap during build does not change with the constant for the same data; it falls markedly with `max_compaction_flush_memory_in_mb=16` (more segments flushed during compaction) relative to 1024, the positive control.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| All rows indexed, file size grows with tokens, no plateau, heap peak same in both builds, heap peak differs with `max_compaction_flush_memory_in_mb` | Claim confirmed (usage does not follow `TOKENS_PER_BLOCK`; control moved) |
| Index stops growing / rows missing from query results at some token count related to 248 | Claim refuted |
| Heap peak or disk differ between builds beyond block-count scaling in a limit-like way | Constant influences usage; claim refuted |
| Control (`max_compaction_flush_memory_in_mb`) does not move peak heap, or workload never reaches that limit | Not confirmed; enlarge workload or lower the option |

**B3h. Controls.** Same data, same heap, same GC, node restarted and tables dropped between runs; compare fresh-start measurements; check that rows are queryable (`SELECT count(*) ... WHERE v LIKE ...` with allow filtering as needed) so index completeness is known.

**B4. Risks and cleanup.** Disk: SASI components and SSTables for up to 4M rows are on the local partition only; keep the partition at a known size and delete `data/`, `commitlog/`, `hints/` and `saved_caches/` of the run afterwards. Do not write to `/users/jason92/cassandra-5.0.9` (read only). Processes: stop the node, any cqlsh/stress and probe JVMs; confirm with `pgrep -fl 'CassandraDaemon|TokenTreeCapProbe|cassandra-stress'`. Remove the working copies when finished. Because the 124 variant writes incompatible index files, never point it at data directories used by the baseline.

### B5. Stage-4 audit amendments (2026-10-28)

Made before any reading; they override the text of the sections named where they conflict. None depends on a reading.

1. **B2a (run form).** Plain `java -cp` against `build/classes/main` of a `copy-source.sh` copy (probe in package `org.apache.cassandra.index.sasi.disk`), `-Xmx512m -XX:+UseSerialGC` for the tree runs. The **control run needs `-Xmx2g`**: 1,000,000 distinct 16-byte terms hold roughly 400 MB of builders. The variant is `TokenTreeBuilder.java:36` = `124`, built by `ant jar` in its own directory after touching the four files that inline the constant (`javap -constants` confirms).
2. **B2e (what a reading is).** `numBlocks` is protected in `AbstractTokenTreeBuilder` and is read from the same package; the interior-node bound is checked by walking the tree with `levelIterator()` (or by reflection on `InteriorNode.tokens`); heap by `Runtime` after `System.gc()` taken as the median of 5.
3. **B3a (SASI switch, resolved).** `sasi_indexes_enabled` exists (`Config.java:606`, default `false`, `conf/cassandra.yaml:1992`); the node yaml sets it `true`. JVM `-Xms1g -Xmx1g`.
4. **B3b/B3c (workload size and load path).** 1M / 4M rows is replaced by **500,000 / 1,000,000 rows** of a seed table `sasi.t (pk bigint PRIMARY KEY, c text, u text)` with `c` the constant `'abcdef'` (one term holding every row: 1M tokens = 4,033 leaves of 248) and `u` unique 16-hex-character values (many terms, one token each). SASI indexes `c_idx` and `u_idx` (`CONTAINS` mode, `max_compaction_flush_memory_in_mb` stated per arm) are created on the restored seed (initial index build, operation type `INDEX_BUILD`, so `PerSSTableIndexWriter.java:365-369` uses the option, not the 1 GiB flush figure), one after the other; `nodetool compact` follows the build. The seed is loaded once per row count and restored per arm (unindexed table, one SSTable). The flush path is not run (the memtable index is the same builder; `OperationType.FLUSH` would use a fixed 1 GiB).
5. **B3b/B3h (control).** The control is the stock build, 1,000,000 rows, `c_idx` with `max_compaction_flush_memory_in_mb` 16 against 1024. It *moves* iff the `debug.log` / `system.log` of the 16 arm shows more flushed SASI segment files (`*SI_*_N` temporary segments, counted from the data directory listing during the build and from the log) than the 1024 arm, **and** the peak of the JMX heap-used samples is lower in the 16 arm. Heap peak is reported for every arm; the segment count is the decisive part because a heap peak between garbage collections is noisy.
6. **B3f (prediction, arithmetic).** For the constant workload, `1,000,000 tokens` need `ceil(1e6/248) = 4033` leaves plus interior nodes (about 17 at the first interior level), i.e. about 4,050 blocks of 4,096 B = about 16.6 MB, and about 2 x that in the 124 variant (8,065 leaves); "roughly 16 bytes per token" is read as 16.6 B per token within 10 %. A Byteman ledger is not needed; the block count is `file bytes / 4096` for the token-tree part and is computed from the file listing.
7. **B3g (added rows).** A 124-variant node that cannot read back its own index (`SELECT count(*) ... WHERE c LIKE '%abc%'` different from the seed count) is *Not confirmed* for that arm; the 124 files are format-incompatible and never share a data directory with the stock arm.
8. **Post-freeze correction before run 1 (2026-10-28; claim, predictions and rows unchanged).** Item 4's constant `'abcdef'` in `CONTAINS` mode becomes six suffix terms (`OnDiskIndexBuilder.java:253-257`), each holding every row (6M token entries on a 1 GiB heap), and a unique 16-character value in `CONTAINS` would make 16 suffix terms per row. The constant is therefore the single character `'q'` (one suffix term, 1M tokens: the case's intended workload), `c_idx` stays `CONTAINS`, and `u_idx` is `PREFIX` (one term per row). `LIKE '%q%'` is the verification query. Found by the instrument check on a 20,000-row seed (results file, section 2), whose readings were not used for any prediction.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/TokenTreeBuilder.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/AbstractTokenTreeBuilder.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/DynamicTokenTreeBuilder.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/conf/IndexMode.java
- grep results over /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi for `TOKENS_PER_BLOCK` (uses only in `disk/AbstractTokenTreeBuilder.java`, `disk/DynamicTokenTreeBuilder.java`, `disk/StaticTokenTreeBuilder.java:153`, `disk/TokenTreeBuilder.java:36`)

## D. Stage-4 feedback

**2026-10-28 (stage 4, node `pc39`; results: `stage4-runtime-verification/results/tokens_per_block-add-pos--autonomous.md`).** Unit tier **Confirmed**, cluster tier **Confirmed**, effect **does not cap**; outcome class **true negative** (estimate `negative`).

- Unit (3 repetitions, stock and a `TOKENS_PER_BLOCK = 124` build): `DynamicTokenTreeBuilder` kept every token up to N = 246,016 (3 levels, 999 blocks at 248, 2,003 at 124); no node above the constant (interior <= 246 / 122, leaf <= 248 / 124); `serializedSize` = `numBlocks` x 4,096 = bytes written; retained heap 41.22 MB (stock) against 41.29 MB (124); `OnDiskIndexBuilder.estimatedMemoryUse()` = 236 B per distinct term in both builds (the constant is not in the estimate), retained heap 400 MB at 1M terms; upstream `TokenTreeTest` passes.
- Cluster (SASI, seed + `CREATE CUSTOM INDEX`, 1 GiB heap): one suffix term holding 1,000,000 tokens produced a `c_idx` of 16,609,304 B (16.61 B per token; arithmetic 4,033 leaves + about 17 interior x 4,096 = 16.59 MB), 2.00 x for 2 x rows, 33,325,080 B (2.01 x) in the 124 build; `u_idx` (1M unique terms, PREFIX) 125,853,952 B, byte-identical in both builds; heap peak of the `c` build 572 / 591 MiB; control `max_compaction_flush_memory_in_mb` 16 against 1024: 8 segment files against 1, heap peak 518 against 572 MiB.
- Amendments at the audit (B5.1 to B5.7, 2026-10-28): run form and `-Xmx2g` for the 1M-term control, `sasi_indexes_enabled` (exists, default false), 500,000 / 1,000,000 rows with a seed + `CREATE CUSTOM INDEX` path (the build operation type uses the option, a flush would use a fixed 1 GiB), the control reading (segment count decisive), block-count arithmetic; B5.8 (post-freeze, before run 1, from the instrument check): constant `'q'` and `u_idx` PREFIX, because `CONTAINS` indexes every suffix of a term.
- Findings for stage 3: (1) B3c should say that in `CONTAINS` mode a text value is indexed as all its suffixes (`OnDiskIndexBuilder.java:253-257`), so one-term workloads need a one-character constant and a unique-value index needs `PREFIX`. (2) Heap peak is a weak control reading here (-9.5 % with the 16 MiB option), the temporary-segment count (1 against 8) is the strong one; "falls markedly" in B3f is too strong for the peak. (3) `u_idx` (one token per term) is independent of `TOKENS_PER_BLOCK` byte for byte, the constant only matters for terms with more than one token.
