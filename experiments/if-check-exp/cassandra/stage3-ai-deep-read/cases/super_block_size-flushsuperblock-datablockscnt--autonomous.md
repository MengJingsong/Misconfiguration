# SUPER_BLOCK_SIZE — verification solution  <!-- file: cases/super_block_size-flushsuperblock-datablockscnt--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`OnDiskIndexBuilder.java:497`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java#L497) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the constant only groups 64 data blocks per on-disk super block; the memory the builder holds is bounded by a different limit (the index-flush memory estimate), and the disk footprint of the index is set by the data, not by this constant. |
| Ground | `SUPER_BLOCK_SIZE` is a layout constant, not a cap. The per-super-block token tree it flushes (`superBlockTree`) holds only the keys of terms already resident in the builder's `terms` map, which is bounded elsewhere (`maxMemorySize`, `PerSSTableIndexWriter.java:247`). Changing the value would change only the number of super-block token trees and padding written, not a limit on usage. |

## A. Constraint trace

**A1. The constraint.** `OnDiskIndexBuilder.SUPER_BLOCK_SIZE`; kind: constant (hard-coded `public static final int`). Declared at [`OnDiskIndexBuilder.java:129`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java#L129) (`SUPER_BLOCK_SIZE = 64`), beside `BLOCK_SIZE = 4096` (line 127) and `MAX_TERM_SIZE = 1024` (line 128). Unit: number of regular 4096-byte data blocks per super block. Default: the literal 64, not derived. Not settable by yaml, `-D` or JMX; changing it needs a source edit and rebuild. It is also part of the on-disk format: the reader uses it to locate super blocks (`OnDiskIndex.java:346`, `361`, `368`, `375`). The earlier trace is confirmed on all these points. It is used only in SPARSE mode: `DataBuilderLevel` is created only when `mode == Mode.SPARSE` (`OnDiskIndexBuilder.java:289`).

**A2. What it caps.** Nothing in memory or disk terms. The compared quantity is `dataBlocksCnt` (declared line 474), the number of data blocks flushed since the last super block. It bounds the number of data blocks whose terms' tokens are merged into one `superBlockTree` before that tree is serialized, so in effect the size of one in-heap token tree (see A3) and the grouping of the on-disk layout. It is not a limit on node heap, off-heap or disk.

**A3. Mechanism.**
1. `DataBuilderLevel.add` (line 483) calls `MutableLevel.add` (line 484 calls `super.add`; the parent is at lines 428-441), which flushes the current data block when `hasSpaceFor` fails (line 433-436) and returns a pointer term.
2. If a block was flushed (`ptr != null`, line 485), `dataBlocksCnt++` (line 488) and `flushSuperBlock(false)` runs (line 489).
3. The term's token tree is then added to the in-memory super-block tree (line 491, `superBlockTree.add(term.keys)`); `DynamicTokenTreeBuilder.add` copies tokens into its own `TreeMap` of `LongHashSet` (`DynamicTokenTreeBuilder.java:67-77`).
4. The check is [`OnDiskIndexBuilder.java:497`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java#L497): `if (dataBlocksCnt == SUPER_BLOCK_SIZE || (force && !superBlockTree.isEmpty()))`.
   - True: record the super block offset (line 499), serialize the token tree to the output (line 500), pad to a 4096 boundary (line 501, `alignToBlock` at lines 341-346), reset the counter (line 503), start a new empty `DynamicTokenTreeBuilder` (line 504), which lets the old tree be garbage collected.
   - False: nothing happens; the tree keeps growing.
5. `finalFlush` (lines 507-511) forces the last, possibly partial, super block.
Overshoot/bypass: the tree grows past 64 blocks' worth only transiently by at most one term (the term that triggered the block flush is added after the check, line 491). The token tree size per super block is not capped in bytes: a term with many keys makes it large, and in SPARSE mode a term may have up to `MAX_KEYS_SPARSE` keys (checked at line 596; the constant's value not verified here). Also each `MutableDataBlock` keeps its own `combinedIndex` tree per block in SPARSE mode (lines 583, 638, 666-668), outside this constant.
Where the actual memory limit sits: terms accumulate in `OnDiskIndexBuilder.terms` (line 143, `HashMap`) with an estimate `estimatedBytes` (lines 175-195); `PerSSTableIndexWriter` compares `currentBuilder.estimatedMemoryUse()` with `maxMemorySize` (lines 247-248) and the limit is 1 GiB for flush and the index option `max_compaction_flush_memory_in_mb` for compaction (`PerSSTableIndexWriter.java:365-368`; `IndexMode.java:58-60,186-192`). The `finish` of the builder (lines 224-300) is the stage where `DataBuilderLevel` runs, after the memory-bounded accumulation.

**A4. Other consumers.** The `terms` map and its per-term token trees (lines 143, 175-195) are the dominant heap use of the builder, governed by the flush threshold above, not by this constant. The 4096-byte `DataOutputBufferFixed` per block (line 521-531) and `SequentialWriter` buffer (`WRITER_OPTION` bufferSize BLOCK_SIZE, lines 131-133), the OS page cache for written files, and the final index file size (dependent on data) all use the resource independently.

**A5. Evidence beyond the source.** none (the SASI docs were not consulted).

## B. Verification solution

**B1. Claim under test.** Memory and disk usage of SASI index building do not follow `SUPER_BLOCK_SIZE`: the number of tokens held in one `superBlockTree` scales with the data (keys per block), while its block count tops out at 64; and process heap during an index flush tracks the index-flush memory threshold (`max_compaction_flush_memory_in_mb` / 1 GiB), not the constant.

### B2. Unit tier

> **Amendments to B2 (stage-4 audit, 2026-10-28, before the unit tier ran; claim, prediction rows and conclusions table unchanged).**
> - **U1 (citations).** Checked in `cassandra/cassandra-5.0.9`: the constants (`:127-129`), the check (`:497`), `DataBuilderLevel` (`:469-519`) and the reader's uses (`OnDiskIndex.java:346-375`, the only other references to `SUPER_BLOCK_SIZE` in `src/java`) are as stated. `MAX_KEYS_SPARSE` is 5 (`OnDiskIndexBuilder.java:575`, checked at `:598`; A3 left it unverified). The public entry for the workload is `add(ByteBuffer term, DecoratedKey key, long keyPosition)` (`:165`) then `finish(File)` (`:238`), which builds the suffix array and calls the three-argument `finish`.
> - **U2 (how the constant is varied).** `SUPER_BLOCK_SIZE` is a `static final int` literal, inlined into its two users. The variants are made by compiling `OnDiskIndexBuilder.java` and `OnDiskIndex.java` of a patched copy of the run copy (line 129 changed; the pristine copy is untouched) into overlay class directories placed ahead of the build on the class path (`ov16`, `ov64`, `ov256`); this is a rebuild of the two classes without `ant jar`. The probe prints the value read by reflection from the loaded class and `javap -constants` of each overlay is saved. A second flavour of each overlay (`...p`) adds one print line in the true branch of `flushSuperBlock` (data blocks counted, tokens of the tree, its serialized size, and the live heap after `System.gc()`), as B2d(2) allows; the unpatched `ov64` and the pristine build give a byte-identical index (md5) as the check that the print does not change the output.
> - **U3 (numbers for B2f, derived from the code).** An `Int32Type` term has a constant size of 4 bytes; with one key each a SPARSE data block holds about 270 terms (15 bytes of offset and entry per term, `hasSpaceFor` at `:543-551`, `ptrLength` at `:644-649`), so 200,000 terms flush about 740 data blocks. Super blocks written = floor((data blocks - 1) / constant) + 1 (the last data block is flushed by `finalFlush` and the last, partial super block is forced), about 47 / 12 / 3 for 16 / 64 / 256; the count is read independently from the file tail (the `superBlockOffsets` list that `flushMetadata` writes, after the level index at the position stored in the last 8 bytes). Largest tree: at most constant x (terms per block) + 1 tokens. File size: within 5 percent across 16, 64 and 256. Live heap at the largest super-block flush (after `System.gc()`): within 10 percent across the three constants at fixed N, and larger for larger N.
> - **U4 (controls made concrete).** The positive control of B2e(5) is a sweep of N = 50,000, 200,000 and 400,000 terms at each constant (live heap and file bytes rise with N); the `-Xmx2g` and `-Xmx64m` runs of B2e(5) are also made, as information only (the 64m run may fail with `OutOfMemoryError`; that is not a row of B2g). The PREFIX control uses the same terms with `Mode.PREFIX`.

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $WORK/c509`), `cd $WORK/c509 && ant jar`. Write a JUnit test (or a main class) in `$WORK/c509/test/unit/org/apache/cassandra/index/sasi/disk/` that is a copy, not placed in the shared tree. Run with `ant testsome -Dtest.name=<Class>`; JVM options `-Xmx512m -XX:+UseSerialGC`, optionally `-Xlog:gc`.

**B2b. Knobs.** The constant is final, so vary it by recompiling a local copy: 16, 64 (default), 256 in `OnDiskIndexBuilder.java:129` of the copy (one build each; the reader at `OnDiskIndex.java:346-375` must be built from the same copy). Second knob, workload: number of terms and keys per term (B2c). Third: `Mode.SPARSE` vs `Mode.PREFIX` (PREFIX does not use `DataBuilderLevel`, line 289), as a negative control.

**B2c. Workload.** Build an `OnDiskIndexBuilder` (constructor at line 150) over an `Int32Type` column in SPARSE mode and call `add(term, key, position)` (line 165) for N distinct terms with 1 key each, N = 200,000, so about N * (term plus pointer) / 4096 data blocks; with an int term the block holds on the order of hundreds of terms, giving more than 64 data blocks (arithmetic to be confirmed by counting `blockOffsets` size from the output). Then call `finish(Pair range, File file, TermIterator)` (line 224 signature) writing to a local temp file. Also a variant with 2,000 terms (fewer than 64 blocks) so the check at line 497 is only reached by `force`.

**B2d. Observables and instruments.** (1) Number of super blocks: read from the output index through `OnDiskIndex` (superBlockOffsets are written by `flushMetadata`, lines 513-517); alternatively, count `true` outcomes of line 497 with a debugger breakpoint counter or a patched log line in the local copy. (2) Maximum size of any `superBlockTree`: a temporary patch in the local copy logging `superBlockTree`'s token count when flushed. (3) Heap: `Runtime.totalMemory()-freeMemory()` after `System.gc()` before and after `finish`, and the peak from `-Xlog:gc`. (4) Output file size (`File.length()`). Cannot be observed directly: the per-object heap size of the tree (estimated with the JOL-based numbers in the comments at lines 172-193, or a heap dump in `jmap -histo`).

**B2e. Procedure.** 1. Build with constant 64; run the 200,000-term workload; record super block count, max tree token count, heap peak, file size. 2. Repeat for 2,000 terms. 3. Rebuild with 16 and then 256 and repeat the 200,000-term run. 4. Run PREFIX mode with the same terms as control. 5. Positive control: repeat the 200,000-term run with a larger heap than the data (`-Xmx2g`) and then with a smaller (`-Xmx64m`), to see heap use move with data volume rather than constant. 6. Delete temp files.

**B2f. Predictions.** Super block count is about ceil(dataBlocks / constant) (plus one forced final flush): about 4x more at 16 than at 64, about 4x fewer at 256. Max tree token count is at most roughly (constant x keys per block). File size differs only by alignment padding (each super block ends on a 4096 boundary, line 501), so it varies by a few percent at most. Peak heap differs by much less than the ratio of constants, because the `terms` map is resident throughout; heap tracks N, not the constant.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Super block count scales inversely with the constant, heap peak and file size nearly flat | Claim confirmed: the constant is a layout parameter, not a cap |
| Heap peak falls clearly (about in proportion) when the constant falls, with N fixed | Claim refuted: the constant bounds memory |
| Heap peak and file size rise with N at every constant value | Positive control moved: usage tracks the data |
| Super block count does not change with the constant | Check line 497 not reached as traced (or wrong mode); not confirmed |
| Heap peak not measurable above GC noise at N = 200,000 | Limit not reached or control did not move; enlarge N, not confirmed |

**B2h. Controls.** Fixed random seed and same terms for every build; `System.gc()` before each reading; run each configuration three times; PREFIX mode (no super blocks) as a structural control; confirm the compiled constant by printing `OnDiskIndexBuilder.SUPER_BLOCK_SIZE` in the test.

### B3. Cluster tier

> **Amendments to B3 (stage-4 audit, 2026-10-28, before the cluster tier ran; claim, prediction and conclusions table unchanged).**
> - **C1 (which path the option governs).** `sasi_indexes_enabled` is a yaml key (`Config.java:606`). `PerSSTableIndexWriter.maxMemorySize` returns a fixed 1 GiB for the memtable flush and the index option only for other operations (`:365-369`); the option's default is 15 percent of 1 GiB = 161,061,273 bytes (`IndexMode.java:60`). To keep the flush-path builders small and the compaction path the one measured, the node sets `memtable_heap_space: 256MiB` and `memtable_offheap_space: 256MiB`.
> - **C2 (workload).** `ks.t (id int PRIMARY KEY, v int)`, SPARSE index on `v` with the option; 5,000,000 rows by `cassandra-stress user profile=... -pop seq=1..5000000` with `v` drawn `uniform(1..2000000000)` (almost all distinct; SPARSE allows at most 5 keys per term). After `nodetool flush`, `nodetool compact ks t` is the measured window; heap is read from `-Xlog:gc` (post-collection occupancy) and a 200 ms JMX sample of heap used; segments are the "Flushed index segment" lines in the window. A fresh data directory per arm.
> - **C3 (arms, made explicit).** Base `o64c64` (option 64, constant 64); option arms `o8c64` and `o512c64`; constant arms `o64c16` and `o64c256` (B3e step 3 says "the default option"; the middle value 64 is used so that only the constant differs from the base); control `pfx64` (PREFIX-mode index on `v`, option 64, constant 64). The constants come from overlay class directories placed in the node's own conf directory, which is first on the class path (`cassandra.in.sh:27`); the node's class-load log shows the overlay is the loaded one. These overlays change only line 129 (no print).

**B3a. Environment and build.** One node, JDK 11, built from a local copy (`ant jar`). `cassandra.yaml` with `data_file_directories`, `commitlog_directory`, `saved_caches_directory`, `hints_directory` on local disk of known size (at least 20 GB free), `-Xms2g -Xmx2g` in `conf/jvm11-server.options`, `sasi_indexes_enabled: true` (name of this yaml key not verified; check `Config.java`). Constant changed only by rebuilding the local copy (as in B2b).

**B3b. Knobs.** SASI index option `max_compaction_flush_memory_in_mb` (`IndexMode.java:58`) at 8, 64 (default 15% of 1 GiB per line 60 is about 153 MB, not verified numerically) and 512, as the contrasting real limit; `SUPER_BLOCK_SIZE` at 16, 64, 256 by rebuild. Set the option in `CREATE CUSTOM INDEX ... USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode':'SPARSE','max_compaction_flush_memory_in_mb':'N'}`.

**B3c. Workload.** Table `ks.t (id int PRIMARY KEY, v int)` with the SASI SPARSE index on `v`. Insert 5,000,000 rows with distinct `v` (cassandra-stress or a CQL loop), `nodetool flush`, then `nodetool compact ks t` so the compaction path (`maxMemorySize` at `PerSSTableIndexWriter.java:365-368`) governs. 5 M terms at about 212 bytes estimated each (lines 177-195) is about 1 GB estimated, which exceeds the largest knob values, so the threshold is crossed. Duration: minutes per run.

**B3d. Observables and instruments.** JVM heap used and GC activity via `jstat -gc <pid> 1000` and `nodetool info`; `nodetool tablestats` for index disk size (`SASI` index component sizes, or `du -sb` on the `SI_*` files); index flush log lines "Scheduling index flush to" (`PerSSTableIndexWriter.java:283`); segment count (the `_N` suffix files, line 341-343 area). Not observable: per-super-block tree sizes (only in the B2 patch).

**B3e. Procedure.** 1. Start the node with the 64 build and option 64; load and compact; sample `jstat` for the whole compaction; record peak heap and `SI_` size. 2. Repeat with the option at 8 and 512. 3. Rebuild with constant 16 and 256 and repeat at the default option. 4. `nodetool drain`, stop the node, `rm -rf` the data directories.

**B3f. Predictions.** Peak heap during the compaction index build tracks the option value (smaller option, more segments, lower peak) and is roughly the same across constants 16, 64 and 256 at fixed option. Index size on disk nearly flat across constants (padding only), and changes across the option value only through segment-count overhead.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Peak heap moves with the option (positive control: a known memory cap) and not with the constant | Claim confirmed |
| Peak heap moves with the constant | Claim refuted |
| Heap peak flat across the option too | Limit not reached or control did not move; raise rows, not confirmed |
| Index size differs by more than padding across constants | Unexpected; re-check the build used the same reader/writer |

**B3h. Controls.** Same data and seed; fresh data directory per run; heap fixed; the option knob as positive control; one run with PREFIX mode index (no super blocks) to isolate the constant's contribution.

**B4. Risks and cleanup.** Unit: temp index files on local disk (delete after each run); builds only in the local copy, never in `/users/jason92/cassandra-5.0.9`. Cluster: a 5 M row table and compaction can need several GB of local disk; keep data, commit log and hints on a local volume of known size; check `df` before; stop the node and confirm with `pgrep -f CassandraDaemon` that none is left; remove data directories and the local source copy.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndex.java (grep lines only)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/DynamicTokenTreeBuilder.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/conf/IndexMode.java (grep lines only)

## D. Stage-4 feedback

**2026-10-29, node pc29, results [`results/super_block_size-flushsuperblock-datablockscnt--autonomous.md`](../../stage4-runtime-verification/results/super_block_size-flushsuperblock-datablockscnt--autonomous.md) (not committed by the session that ran it; frozen version `eef62cc3d3b5720cf100e725329416d87d662c779697c266a44b5104a6f18d18`, the file above this section).**

- **Verdict:** unit **Confirmed, does not cap**; cluster **Not confirmed (no matching B3g row)**, effect undetermined. Outcome class **undetermined** (the unit tier says negative, the cluster heap reading does not meet the frozen row; the deterministic cluster observables agree with the unit tier). Unit (overlay classes with the constant at 16 / 64 / 256, 200,000 Int32 terms, 736 data blocks): super blocks 46 / 12 / 3 = floor((736 - 1) / constant) + 1, read from the file tail and from a print in the true branch of line 497; the largest in-heap token tree 4,352 / 17,408 / 69,632 tokens (constant x about 272 terms per block); file bytes within 1.95 percent (21.86 / 21.53 / 21.44 MB), byte-identical between repeats and between the patched, unpatched and pristine classes; the live heap at the largest tree 120.3 / 124.6 / 136.1 MB, rising with N (46 to 52 MB at 50,000 terms, 218 to 241 MB at 400,000); PREFIX mode writes no super blocks; with 2,000 terms only the forced final super block is written. Cluster (5,000,000 SPARSE int rows, compaction of 23 sstables): index segments in the compaction 137 / 18 / 3 for `max_compaction_flush_memory_in_mb` 8 / 64 / 512 and 17 / 18 / 18 for constants 16 / 64 / 256; `SI_t_v.db` 537,376,860 bytes for all three options and 545.6 / 537.4 / 535.4 MB for constants 16 / 64 / 256 (1.9 percent); no failure; the post-collection heap peak 844 / 800 / 1941 MiB for the options and 327 / 800 / 375 MiB for the constants.
- **Corrections to the file:** `MAX_KEYS_SPARSE` is 5 (`OnDiskIndexBuilder.java:575`); the option governs only the compaction and index-build paths (the memtable flush uses a fixed 1 GiB, `PerSSTableIndexWriter.java:365-369`) and its default is 161,061,273 bytes (15 percent of 1 GiB); an Int32 SPARSE data block holds about 270 terms; the number of super blocks is floor((data blocks - 1) / constant) + 1; "at the default option" in B3e step 3 was read as option 64.
- **Missed (recorded, not tuned):** (1) the live heap at the largest super-block flush differs by 13.1 percent over the 16 x range of the constant (U3 said 10 percent); the difference equals the extra tree (about 242 bytes per token), so the constant does bound the transient tree (about 1 MB at 16, 17 MB at 256 in the heap) but not the node; (2) the cluster heap reading: one post-collection peak per arm varies by 300 to 500 MiB between arms of the same option (327 to 1952 MiB at option 64), more than the step from option 8 to 64, so only the 512 MiB option separates (1941 MiB; the median in that window is 76 MiB); the rule written before the tier (constants' range under a quarter of the options' range) fails.
- **For stage 3:** a design that needs the heap to separate a 150 MiB-class cap from the constant should read the builder's own size (for example a heap histogram at the largest segment, or the estimate printed per segment) rather than the process heap; the segment count and the index bytes are the stable observables.
