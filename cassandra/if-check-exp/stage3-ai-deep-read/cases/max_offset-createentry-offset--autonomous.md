# MAX_OFFSET — verification solution  <!-- file: cases/max_offset-createentry-offset--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`AbstractTokenTreeBuilder.java:297`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/AbstractTokenTreeBuilder.java#L297) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: `MAX_OFFSET` is an on-disk format-width ceiling on a file position (48 bits), not a configurable cap, and it bounds no heap, off-heap or disk quantity; the node's disk and memory use are set by other things (data volume, flush and compaction settings). |
| Ground | The constant is a fixed number (2^47 - 1) that guards an encoding. The value checked is a position inside an SSTable file, an input to a serialized field, not an allocation or a growing store. The check only rejects a value that cannot be encoded; it does not limit how much is stored. At the limit (about 128 TiB file position) the node would hit it only if a single SSTable file grew that large; nothing in the check reduces usage below that. |

> **Link rule.** Followed: declaration (A1) and if statement (Entry pointer, A3) are permalinks at `cassandra-5.0.9`.

## A. Constraint trace

**A1. The constraint.** `TokenTreeBuilder.MAX_OFFSET`; kind: constant (interface field, so implicitly `public static final`). Declared at [`TokenTreeBuilder.java:37`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/TokenTreeBuilder.java#L37): `long MAX_OFFSET = (1L << 47) - 1; // 48 bits for (signed) offset`. Unit: bytes (a file position). Value: 2^47 - 1 = 140737488355327, i.e. just under 128 TiB. Default derivation: none; it is a literal shift expression sized by the leaf entry encoding (comment on the same line; the encoding is described at `AbstractTokenTreeBuilder.java:382-384`: middle 32 bits stored in the offset slot, bottom 16 bits in the entry header). Not settable by yaml, `-D`, or JMX; changing it needs a source edit and rebuild and would break the on-disk token-tree format. The only reference points (grep of `src/java/org/apache/cassandra/index/sasi`) are the declaration, the check at lines 297-298, and a comment at line 382. Correction to the earlier trace: the line numbers 37 and 297-298 hold; the claim that the offset is "the position of the partition in the SSTable data file" is true only for some formats (see A2).

**A2. What it caps.** Nothing in memory or disk terms. The quantity compared is `offset`, the `keyPosition` that `PerSSTableIndexWriter` hands to the term's token tree (`PerSSTableIndexWriter.java:108-111`, `:136`, `:243`, then `OnDiskIndexBuilder.java:185`). What that position is depends on the SSTable format: for the BIG format `BigTableWriter.onStartPartition` passes `indexWriter.writer.position()`, the position in the primary index file (`BigTableWriter.java:92`); for the shared writer used by other formats (BTI) it passes `partitionWriter.getInitialPosition()`, the position in the data file (`SortedTableWriter.java:263`). So for BIG it is a position in `Index.db`, and the earlier trace's "data file" statement is wrong for the default format (default format `big` per `conf/cassandra.yaml:1172`, a commented example; the default was not independently verified). Either way the effect is the same: a file position over about 128 TiB cannot be encoded in the 48-bit field. This is a format limit on file size, indirectly on disk, but one far beyond any practical size.

**A3. Mechanism.** In [`AbstractTokenTreeBuilder.java:297`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/AbstractTokenTreeBuilder.java#L297) `if (offset > MAX_OFFSET)`:
1. `Leaf.createEntry(tok, offsets)` is called at serialization time from `DynamicTokenTreeBuilder.java:185` and `StaticTokenTreeBuilder.java:243` (lines 288-291 set up `offsetCount` and the switch).
2. Case 0 offsets throws `AssertionError` (line 292-293). Case 1 reads the single offset (`offsets.toArray()[0]`, line 296) and tests it at line 297.
3. If `offset > MAX_OFFSET`: throws `AssertionError("offset ... cannot be greater than ...")` at line 298. This is a plain `throw`, not a Java `assert`, so it fires without `-ea`. The failure aborts the SASI index segment build for that SSTable.
4. Else if `offset <= Integer.MAX_VALUE` (line 299): `SimpleLeafEntry`; otherwise `FactoredOffsetLeafEntry` (line 302), which splits the offset into the top 32 bits and bottom 16 bits (`:392-411`).
5. Cases with two or more offsets (lines 304-314) never test `MAX_OFFSET`: two offsets each `<= Integer.MAX_VALUE` are packed, anything else goes to `createOverflowEntry`, which stores each offset as a full `long` (`:326-327` region, `buf.putLong` at `:274-276`). So a token with 2 or more colliding offsets bypasses the check entirely, and the check only guards the single-offset path.
Other limit in the same method: more than `OVERFLOW_TRAILER_CAPACITY` (8, from 64/8 at `TokenTreeBuilder.java:32-34`) overflow entries per leaf throws (`AbstractTokenTreeBuilder.java:324-325`). That is a separate constraint.
Reachability gate: SASI indexes can only be created if `sasi_indexes_enabled` is true (`conf/cassandra.yaml:1992`, `Config.java:606`, check at `CreateIndexStatement.java:122`).

**A4. Other consumers.** The same file positions are used without this limit by the SSTable readers; the SSTable data and index files themselves are bounded only by disk and by the compaction and flush settings. Heap and off-heap used while building a SASI index (term and token sets in `OnDiskIndexBuilder`, `OnDiskIndexBuilder.java:191` comment on per-entry set cost) are governed by other mechanisms, not by this constant.

**A5. Evidence beyond the source.** None. (Not verified: any upstream issue that introduced the 48-bit layout.)

## B. Verification solution

**B1. Claim under test.** (Negative estimate.) `MAX_OFFSET` does not cap memory or disk: no workload that stays under about 128 TiB of file position changes how much heap, off-heap or disk the node uses because of this constant, and the only effect of the constant is to make serialization of a single-offset token with `offset > MAX_OFFSET` throw. Refuted if disk or heap use of the SASI build flattens or the build fails at any size below the constant.

### B2. Unit tier

> **Amendments to B2 (stage-4 audit, 2026-10-28, before the unit tier ran; claim, prediction rows and conclusions table unchanged).**
> - **U1 (citations and paths).** Checked against `cassandra/cassandra-5.0.9`: `OVERFLOW_TRAILER_CAPACITY` is declared at `TokenTreeBuilder.java:35` (`:33-34` give 64 and 8; A3 said `:32-34`); its check is at `AbstractTokenTreeBuilder.java:323-324` (A3 said `:324-325`). `startPartition(key, keyPosition, KeyPositionForSASI)` has a third argument in 5.0.9; BIG passes `indexWriter.writer.position()` (`BigTableWriter.java:88-92`), the shared writer passes the data-file position (`SortedTableWriter.java:263`), as A2 says. The source copy is made with `copy-source.sh`, not `rsync` from `/users/jason92`.
> - **U2 (launcher).** The test is a JUnit class compiled with `javac` against the run copy's build and run through `org.junit.runner.JUnitCore` with the java launcher and the JDK 11 module flags of `conf/jvm11-server.options` (the closed harnesses do the same); `ant testsome` is not needed.
> - **U3 (numbers for B2f; all derived from the code, none from a run).** One token, one offset: `write` emits 64 + 16 = 80 bytes for every passing value (a single-block tree is not aligned: `flushBuffer(..., numBlocks != 1)`, `AbstractTokenTreeBuilder.java:94`, `:109`); the entry type (parsed from the written bytes, short at byte 64) is SIMPLE for offsets <= `Integer.MAX_VALUE` and FACTORED above. One token, two offsets with one at `MAX_OFFSET + 1`: OVERFLOW entry, 2 slots, 96 bytes; three offsets: 104 bytes; neither throws (no `MAX_OFFSET` test on the multi-offset path). Added values: `Long.MAX_VALUE` as the single offset (throws, message "offset 9223372036854775807 cannot be greater than 140737488355327") and as one of two offsets (no throw). `createEntry` runs inside `write`, so `serializedSize()` read before `write` omits the overflow trailer; the readings use the bytes written, one fresh builder per write. The serialized-size control of B2h: 1, 248 and 249 tokens with one small offset give 80, 4032 (64 + 248 x 16) and a multi-block size of `numBlocks x 4096`.
> - **U4 (heap reading).** `Runtime` heap before and after is context only; the size readings are the bytes written.

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $LOCAL/c/`), never build in the shared tree. `cd $LOCAL/c && ant jar` (or `ant build-test` for the JUnit route). Test source: a new class under `test/unit/org/apache/cassandra/index/sasi/disk/` modeled on the existing `TokenTreeTest.java` (it exists in that directory). Run with `ant testsome -Dtest.name=<Class> -Dtest.methods=<m>`. JVM options: defaults of the test target.

**B2b. Knobs.** The single-offset value passed to the builder: `MAX_OFFSET - 1`, `MAX_OFFSET`, `MAX_OFFSET + 1`, `Integer.MAX_VALUE`, `Integer.MAX_VALUE + 1`. Set directly in test code; the boundary values test both sides of line 297 and the simple/factored switch at line 299. Second knob: number of offsets per token (1, 2, 3) to show the bypass in A3 step 5.

**B2c. Workload.** One token with the given offset(s) added with `DynamicTokenTreeBuilder.add(Long token, long keyPosition)` (`DynamicTokenTreeBuilder.java:48`), then `finish()` (`AbstractTokenTreeBuilder.java:52`) and `write(DataOutputPlus)` (`:75`) to a `DataOutputBuffer`. The offset is a number, so no file of that size is created; the limit is reached by arithmetic, not by data volume.

**B2d. Observables and instruments.** Whether `write` throws and the exception message; serialized size in bytes of the output buffer; for each case the entry type (read back with `TokenTree` from the written bytes, as `TokenTreeTest` does); heap with `Runtime.totalMemory()-freeMemory()` before and after, only as a context reading. Not observable: any real file of that size.

**B2e. Procedure.** 1) Build. 2) For each knob value construct a fresh builder, add the token, finish, write. 3) Record exception or serialized length and entry type. 4) Repeat with two and three offsets, including one offset at `MAX_OFFSET + 1`. 5) Positive control (see B2h). 6) Delete the local copy.

**B2f. Predictions.** `MAX_OFFSET` and below: no exception; `Integer.MAX_VALUE + 1` through `MAX_OFFSET` serialize as factored entries, `<= Integer.MAX_VALUE` as simple entries. `MAX_OFFSET + 1` with one offset: `AssertionError` with message "offset 140737488355328 cannot be greater than 140737488355327". Two or three offsets, one at `MAX_OFFSET + 1`: no exception (bypass). Serialized length of a one-token tree is the same fixed block size for all passing values, so size does not depend on the constant.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Throw only at `MAX_OFFSET + 1` with one offset, fixed serialized size for all passing values | Mechanism as traced; the constant only rejects unencodable input (claim consistent) |
| No throw at `MAX_OFFSET + 1` with one offset | A3 wrong (claim about the check is wrong) |
| Throw at a value `<= MAX_OFFSET` | A1 or A3 wrong |
| Serialized size or heap grows as the offset approaches the limit | Usage follows the constant (claim refuted) |
| Size flat while the positive control (B2h) moves | Claim confirmed at the unit level |
| Control did not move, or limit never reached | Not confirmed |

**B2h. Controls.** Positive control where a cap binds in the same class family: add more than `OVERFLOW_TRAILER_CAPACITY` (8) offsets-per-leaf overflow entries so the overflow cap (`AbstractTokenTreeBuilder.java:324-325`) throws, showing the harness can detect a cap. Also a size control: serialized length vs number of tokens (grows with `TOKENS_PER_BLOCK` blocks, `TokenTreeBuilder.java:35`) shows what actually drives output size.

### B3. Cluster tier

> **Amendments to B3 (stage-4 audit, 2026-10-28, before the cluster tier ran; claim, prediction and conclusions table unchanged).**
> - **C1 (indexed value size).** `OnDiskIndexBuilder.add` rejects a term of 1024 bytes or more (`MAX_TERM_SIZE`, `OnDiskIndexBuilder.java:167`, logs and skips it), so "1 KiB values" cannot be the indexed column. Table: `ks.t (id bigint PRIMARY KEY, v text, payload blob)`; `v` is a short text (about 10 characters, 100,000 distinct values) carrying the SASI index (default PREFIX mode), `payload` is a 1000-byte blob that carries the data volume.
> - **C2 (sizes and the disk guard).** The three sizes are rows of 1000-byte payload: 1,000,000 (`s1`), 4,000,000 (`s4`), 16,000,000 (`s16`), in that order; the reading is the measured `*-Data.db` bytes, not the label. Each size starts on a fresh data directory with `commitlog_total_space: 1024MiB`. The node has about 47 GB of local disk; a size runs only if free space on `/` at its start is at least 2.2 x its payload + 8 GB (single-sstable compaction holds input and output); a size that fails the guard is recorded as not run (a runbook defect), not shrunk.
> - **C3 (load and compaction).** `cassandra-stress user profile=...` with `-pop seq=1..N`, `nodetool flush ks t`, `nodetool compact ks t` until `tablestats` shows 1 sstable, then the disk readings. Heap: `-Xmx2G`, sampled every 500 ms over JMX and `-Xlog:gc` for post-collection occupancy.
> - **C4 (controls, all on 1,000,000 rows).** `n1`: same table without the index (disk difference isolates the SASI files). `b1`: `sstable: selected_format: bti`, if the node accepts the index with it (otherwise recorded). `h1`: `-Xmx4G` against the `s1` run's `-Xmx2G`. `p1` (positive control for a cap that binds): `commitlog_total_space: 64MiB`, the same burst, `du` of the commit log every second; expected to stop near 64 MiB plus one 32 MiB segment while `data` keeps growing.
> - **C5 (what "heap unrelated" means).** The maximum post-collection heap of `s16` is within a factor 1.5 of that of `s1` while data bytes grow about 16 x; no `AssertionError` containing "cannot be greater than" in `system.log`.

**B3a. Environment and build.** One node, JDK 11, local copy built with `ant jar`. In its `conf/cassandra.yaml`: `sasi_indexes_enabled: true`; data, commitlog, hints, saved caches all on a local disk of known size (for example a dedicated directory on a 50 GiB local volume); `-Xms2G -Xmx2G`.

**B3b. Knobs.** The constant cannot be set. Vary instead what moves the offset: amount of data written into one SSTable (so the index-file position or data-file position grows). Values: 1, 4, 16 GiB of data in the single SSTable (flush plus `nodetool compact`). With a SASI index on a text column. A second run with sstable format `big` and, if it can be configured, `bti` (`conf/cassandra.yaml:1164-1172`), to compare which file the offset tracks (A2).

**B3c. Workload.** `cassandra-stress` or CQL loader writing wide-enough partitions: table with a SASI index (`CREATE CUSTOM INDEX ... USING 'org.apache.cassandra.index.sasi.SASIIndex'`), 1 KiB values. Sizes above; arithmetic: reaching `MAX_OFFSET` needs about 128 TiB in one file, which is about 8000 times the largest run, so the limit is not reachable on the target machine. Duration: until compaction finishes for each size.

**B3d. Observables and instruments.** Disk: `du -sb` of the table directory and of `*-Data.db`, `*-Index.db`, `*SI_*.db` files after each step. Heap: `jcmd <pid> GC.heap_info` and `nodetool info` at fixed intervals. Off-heap: `nodetool tablestats` memtable off-heap. Log: `system.log` for `AssertionError`. Not observable: the actual `offset` value in the builder (only inferred from file positions).

**B3e. Procedure.** 1) Copy, build, configure. 2) Start node; create keyspace, table, SASI index. 3) For each size: write, `nodetool flush`, `nodetool compact`, record disk and heap. 4) Grep the log for `cannot be greater than`. 5) Positive control: repeat the smallest size with `commitlog_total_space: 64MiB` (`cassandra.yaml:883` is the commented default) and a write burst, and watch the commitlog directory plateau. 6) Stop the node (`nodetool drain`, kill, check `pgrep -f CassandraDaemon`), delete data.

**B3f. Predictions.** Index and data file bytes grow roughly linearly with data volume across 1, 4 and 16 GiB; heap stays within the 2 GiB cap and shows no relation to the file position; no `AssertionError` in the log at any size. The positive control commitlog directory stops growing near the configured cap while the data directory keeps growing.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Disk grows with data, heap unrelated, no assertion | Usage does not follow the constant (claim confirmed) |
| Positive-control commitlog plateaus near its cap | The control works, so a flat result elsewhere is meaningful |
| `AssertionError` mentioning offset in log at these sizes | Contradicts A1/A2 arithmetic (claim wrong) |
| Disk or heap plateaus as file size grows with no other cap set | Something caps usage; needs a new trace |
| Control did not plateau, or runs too small to separate | Not confirmed |

**B3h. Controls.** Same table without the SASI index (disk difference isolates SASI files); same load with a different heap size to show heap is set by `-Xmx` and memtable settings, not by position.

**B4. Risks and cleanup.** Disk: 16 GiB data plus compaction headroom, so use a local volume of at least 50 GiB, never shared storage. Commit log and hints on the same local volume. Processes: stop the node and any stress client, then `pgrep -f "CassandraDaemon|cassandra-stress"` must return nothing. Delete the local source copy and data directories. Unit tier writes only to memory and the local build directory.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/TokenTreeBuilder.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/AbstractTokenTreeBuilder.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java (grep only)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java (SASI flag only)
- /users/jason92/cassandra-5.0.9/conf/cassandra.yaml (grep only)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java (grep only)

## D. Stage-4 feedback

**2026-10-29, node pc29, results [`results/max_offset-createentry-offset--autonomous.md`](../../stage4-runtime-verification/results/max_offset-createentry-offset--autonomous.md) (not committed by the session that ran it; frozen version `096191d1a19f07596322a8e2b2923c91c31fa35510a4743754b1adf6fbd0ce76`, the file above this section).**

- **Verdict:** unit **Confirmed, does not cap**; cluster **Confirmed, does not cap**. Outcome class **true negative**. Unit: a one-token tree with one offset is 80 bytes for offsets 1, 2147483647 (SIMPLE), 2147483648, `MAX_OFFSET - 1` and `MAX_OFFSET` (FACTORED); `MAX_OFFSET + 1` and `Long.MAX_VALUE` raise `AssertionError: offset N cannot be greater than 140737488355327`; the same offsets inside a two- or three-offset token raise nothing (OVERFLOW entries of 96 and 104 bytes); size follows the token count (80, 4032, 12288 bytes for 1, 248, 249 tokens) and 9 offsets on one token raise the overflow assertion. Cluster (one node, SASI index on a short text, one sstable after compaction): `Data.db` 1.04 / 4.16 / 16.68 GB and `Index.db` 15.7 / 63.7 / 255.7 MB for 1 / 4 / 16 million rows (x 4.00 and x 4.01 per x 4 rows), no assertion in any of 7 arms, heap bounded by `-Xmx` (post-collection 2028 MiB of 2048, 1945 for the 16 GB arm; 4076 of 4096 with `-Xmx4G`); without the index no SI file and the same `Data.db`; with `sstable: bti` the same SI size (24,981,192 bytes) and `Data.db` within 0.1 percent.
- **Corrections to the file:** the indexed value must be shorter than 1024 bytes (`MAX_TERM_SIZE` rejects 1 KiB terms), so the data volume goes in a separate blob column; `OVERFLOW_TRAILER_CAPACITY` is declared at `TokenTreeBuilder.java:35` (the cap check at `AbstractTokenTreeBuilder.java:323-324`); a one-token tree is 80 bytes, not "a fixed block size"; `bti` needs `storage_compatibility_mode: NONE`.
- **Missed (recorded, not tuned):** (1) the SI file grows less than linearly with the rows (x 2.93, then x 3.62 for x 4 rows) because the indexed text has only 100,000 distinct values; (2) the 64 MiB commit-log control (`p1`) did not hold the commit log near 64 MiB (192 to 288 MiB during the load, 1.0 GB written in 40 s); the 1024 MiB cap did bind in the 16 GB arm (max 1056 MiB, against 640 MiB in the 4 GB arm) and served as the control; (3) the limit cannot be approached on a node: the largest checked quantity was 2.6 x 10^8 (BIG index-file position), 5.5 x 10^5 times below `MAX_OFFSET`.
- **Weaker than it looks:** the cluster tier shows only that nothing changes far below the constant; the only crossing of the boundary is the unit test, which passes offsets directly to the builder; the heap is saturated at `-Xmx` in the 1 and 4 GB arms.
- **For stage 3:** the head of the file (Entry, Ground) says the checked value is a position in an SSTable data file; in BIG it is a position in the primary index file (A2 says so).
