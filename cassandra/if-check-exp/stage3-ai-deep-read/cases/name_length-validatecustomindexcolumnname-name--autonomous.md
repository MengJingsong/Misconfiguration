# NAME_LENGTH — verification solution  <!-- file: cases/name_length-validatecustomindexcolumnname-name--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`CreateIndexStatement.java:213`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/schema/CreateIndexStatement.java#L213) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: `NAME_LENGTH` is a 48-character limit on schema identifier text (here a custom-index target column name) checked once at DDL time; it does not bound any memory- or disk-significant object. |
| Ground | The check compares `String.length()` of one identifier with a fixed constant and either throws or passes. It does not size a buffer, cache, file or queue. Node heap and disk usage are governed by data volume and by other settings (memtable, cache, commit log, compaction), not by this name limit. |

> **Link rule.** Followed: the declaration (A1) and the if statement (Entry pointer, A3) are permalinks at tag `cassandra-5.0.9`.

## A. Constraint trace

**A1. The constraint.** `SchemaConstants.NAME_LENGTH`; kind: hard-coded constant (`public static final int`), declared at [`SchemaConstants.java:75`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/SchemaConstants.java#L75) (`= 48`). Unit: characters (`String.length()`). Default: the literal 48, not derived from anything. Its javadoc (`SchemaConstants.java:69-74`) calls it "The longest permissible KS or CF name" and says the old 255-character whole-path concern (Windows) is no longer in effect after CASSANDRA-16956 (this wording is in the source javadoc; the issue itself not otherwise verified). Not settable: no yaml key, no `-D` property, no JMX; changing it needs a source edit and rebuild/restart. Earlier trace verified: declaration line 75 correct; check at `CreateIndexStatement.java:213` inside `validateCustomIndexColumnName` (line 209); error constant `TOO_LONG_CUSTOM_INDEX_TARGET` defined at line 64 and thrown at line 214. Correction/clarification to the earlier trace: in 5.0.9 the constant's live consumers are only the keyspace-name check (`schema/KeyspaceMetadata.java:68`) and this custom-index target check (`CreateIndexStatement.java:213`); table names use `TABLE_NAME_LENGTH` (`TableMetadata.java:517`), not `NAME_LENGTH` (grep of `NAME_LENGTH` over `src/java` shows only these uses plus `FILENAME_LENGTH`/`TABLE_NAME_LENGTH`, which are different constants). So the javadoc's "KS or CF name" is stale for tables.

**A2. What it caps.** Other: the character count of an identifier string (here the index target column name, `target.column.toString()`, `CreateIndexStatement.java:228`). It is not a heap, off-heap or disk quantity. The only indirect link to disk is that the name is validated with `isValidCharsName` (`SchemaConstants.java:107-110`, pattern `\w+` at line 42) so that names are safe in file names; the 48 cap itself is not what keeps file names under the OS limit (that is `FILENAME_LENGTH`, line 80, and `TABLE_NAME_LENGTH`, line 91).

**A3. Mechanism.**
1. `CreateIndexStatement.apply` computes `kind = attrs.isCustom ? CUSTOM : COMPOSITES` (`CreateIndexStatement.java:174`).
2. It calls `validateIndexTarget(table, kind, t)` for each target (line 176; method at line 217).
3. For `kind == CUSTOM` only, it calls `validateCustomIndexColumnName(target.column.toString())` (lines 227-228; a comment at line 226 says the check is to be removed with CASSANDRA-20235, as written in the source, not verified elsewhere).
4. In that method, a name failing `isValidCharsName` throws `INVALID_CHARS_CUSTOM_INDEX_TARGET` (lines 211-212); then the if statement [`CreateIndexStatement.java:213`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/schema/CreateIndexStatement.java#L213) `name.length() > SchemaConstants.NAME_LENGTH` throws `TOO_LONG_CUSTOM_INDEX_TARGET` (line 214), an `InvalidRequestException` via `ire`, rejecting the CREATE INDEX statement.
Outcomes: length <= 48 passes (no allocation or limit applied); length > 48 aborts the DDL with no schema change. Bypass: non-custom (`COMPOSITES`) indexes skip the check entirely (line 227), so the same long column name can be indexed with a plain `CREATE INDEX`; the column itself can exist with a name longer than 48 (no `NAME_LENGTH` check on column names was found in `src/java`, not exhaustively verified for all paths, e.g. CREATE TABLE column-name validation).

**A4. Other consumers.** What really uses heap/disk for an indexed table is unrelated: memtables and their allocator pool (`db/memtable/AbstractAllocatorMemtable.java:59`, heap limit from `memtable_heap_space`, `DatabaseDescriptor.java:586-590`, `AbstractAllocatorMemtable.java:81`), SSTables and index component files, caches. A longer column name only adds bytes to schema metadata and to per-column metadata stored in SSTables (not quantified).

**A5. Evidence beyond the source.** None beyond the in-source comments cited above (CASSANDRA-16956 in the javadoc, CASSANDRA-20235 in the TODO); I did not open the issue tracker. Test coverage: grep of `test/` for `TOO_LONG_CUSTOM_INDEX_TARGET` and "permissible name length" returned no file (checked).

## B. Verification solution

**B1. Claim under test.** Node heap, off-heap and disk usage do not follow `NAME_LENGTH`: the only effect of the limit is accepting or rejecting the DDL at 48 vs 49 characters; indexing and ingesting with a name at 48 and (via a non-custom index) well above 48 costs resource in proportion to data written, not to the limit. Falsified if resource usage shows a step or bound at 48 characters beyond the few bytes of the name itself.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tag to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $WORK/c509/`), never build in the shared tree. `cd $WORK/c509 && ant jar` then a JUnit test run with `ant testsome -Dtest.name=<Class> -Dtest.methods=<m>`. Test source: new class under `test/unit/org/apache/cassandra/cql3/` extending `CQLTester` (exists at `test/unit/org/apache/cassandra/cql3/CQLTester.java`). JVM options: defaults of `ant testsome` plus `-Xmx1g`.

**B2b. Knobs.** The target column-name length L in {1, 47, 48, 49, 64, 200} (the constant itself cannot be varied without a rebuild; an optional second build edits `SchemaConstants.java:75` to 96 to show the boundary moves with the constant). Index kind: custom (`USING 'org.apache.cassandra.index.sasi.SASIIndex'`, SASI is a CUSTOM class per `CreateIndexStatement.java:200-203`) vs plain `CREATE INDEX`.

**B2c. Workload.** For each L: `CREATE TABLE ks.t (k int PRIMARY KEY, <col of length L> text)`, then `CREATE CUSTOM INDEX ... ON ks.t(<col>) USING '...SASIIndex'`, and the same with plain `CREATE INDEX`. Then insert 10 000 rows of a fixed 100-byte value per case. Arithmetic: L=48 is the largest accepted, L=49 the smallest rejected, per `name.length() > 48`.

**B2d. Observables and instruments.** (1) Accept/reject and the error message (JUnit assertion). (2) Heap used before/after the inserts: `Runtime.totalMemory()-freeMemory()` after `System.gc()`, and the memtable `getLiveDataSize()` of the table's memtable (`db/memtable/SkipListMemtable.java:363`) via `getCurrentColumnFamilyStore().getTracker().getView().getCurrentMemtable()`. Cannot be observed directly: per-object retained size of the name string (approximate via the above only).

**B2e. Procedure.** 1. Build as B2a. 2. For each L and index kind run the DDL, record outcome. 3. For accepted cases run the insert workload, `System.gc()`, record heap and live memtable size; repeat three times. 4. Run the positive control (B2h). 5. Delete `$WORK`.

**B2f. Predictions.** Custom index: L<=48 accepted, L>=49 rejected with "is longer than the permissible name length of 48 characters". Plain index: all L accepted (up to the general CQL limits). For accepted cases at equal row count, memtable live size and heap differ only by the extra name bytes (small, roughly proportional to L times a small count of copies), with no step at 48 and no relation to the limit.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Custom L=48 ok, L=49 rejected; plain index accepts 49+ | Mechanism as traced |
| Memtable live size and heap flat (differences only a few bytes per name) across L while the control moves | Claim confirmed: usage does not follow the constraint |
| Usage scales with L beyond a few bytes, or jumps at 48 | Claim refuted |
| Control (memtable size vs row count) does not move, or L=49 not rejected | Not confirmed; rework setup |
| Custom L=49 accepted | Trace wrong (check not reached; verify kind) |

**B2h. Controls.** Positive control: same table at fixed L=10, vary the row count in {1 000, 10 000, 100 000}; live memtable size must grow roughly in proportion, showing the instrument sees usage change where data volume (not the name limit) drives it. Also an unindexed baseline table.

### B2i. Audit amendments, unit tier (stage 4, 2026-10-28)

These apply to B2a-B2h; B2f and B2g are not changed, only given numbers where they say "small", "only the extra name bytes" or "roughly proportional".

1. **SASI is gated by a yaml flag (answers the open question in B3a).** `CreateIndexStatement.java:122-123` rejects a SASI index with "SASI indexes are disabled. Enable in cassandra.yaml to use." unless `sasi_indexes_enabled` is true (`Config.java:606`, default false, `conf/cassandra.yaml:1992`; setter `DatabaseDescriptor.java:4243`). Every arm that creates a SASI index must run with `sasi_indexes_enabled: true`; without it the DDL fails before `validateCustomIndexColumnName` and the check at line 213 is never reached. The SASI usage warning is at `CreateIndexStatement.java:201-205` (not 200-203).
2. **Launcher and paths.** Copy by `copy-source.sh` to local disk (`~/s4-b2/c`), `ant build-test`. The test class is compiled outside the tree and run in a separate JVM per arm through `org.junit.runner.JUnitCore` with the build classpath and the module flags of `conf/jvm11-server.options`, `-Xmx4g`, unit yaml = the tree's `test/conf/cassandra.yaml` with directories on local disk, `sasi_indexes_enabled: true`, `memtable_heap_space: 2048MiB` (no pool flush during an arm). The optional second build with the constant edited to 96 is **not run** (stated here, not silently dropped).
3. **Names.** The column is `c` followed by `x` up to L characters (all `\w`), the table `(k int PRIMARY KEY, <col> text)`, the index is named explicitly (`i_<L>`) so its generated name does not grow with L. L = 200 is longer than any name limit found in `src/java` for columns (grep of `NAME_LENGTH` shows only `KeyspaceMetadata.java:68` and `CreateIndexStatement.java:213`); whether CREATE TABLE accepts a 200-character column name is itself a reading (a rejection there is recorded and that L is dropped for that kind).
4. **Workload and instruments.** Each accepted (L, kind) gets 10,000 rows of a distinct random 100-character hex value (same seed for every L, so the data are identical across L). Readings after the load: memtable bytes owned by the base table `((AbstractAllocatorMemtable) memtable).getAllocator().onHeap().owns()` (`AbstractAllocatorMemtable.java:125, 190`), plain index backing-table `owns()` likewise, `getLiveDataSize()` (`SkipListMemtable.java:363`) as information; then explicit flush of the base table and its backing table, and the recursive byte sum of the base table's directories (this includes a plain index's hidden directory and SASI components); heap after `System.gc()` as information. Three repeats per (L, kind) in one JVM; the median is used. Fresh table per repeat.
5. **Numbers for B2f.** Custom: L = 1, 47, 48 accepted; L = 49, 64, 200 rejected with exactly "Column '<name>' is longer than the permissible name length of 48 characters". Plain: all six L accepted. Across the six plain L: (max - min) / mean of the memtable `owns()` is at most 1 percent, and of the flushed directory bytes at most 1 percent; the same for custom L = 1, 47, 48; |bytes(L=49) - bytes(L=48)| (plain) is at most 1 percent of bytes(L=48) (no step at 48).
6. **Control (B2h) made exact.** Plain index, L = 10, row counts 1,000 / 10,000 / 100,000: the ratio of memtable `owns()` at 10,000 over 1,000, and at 100,000 over 10,000, lies in [7, 13]; the same ratios of flushed directory bytes lie in [5, 13]. Unindexed baseline (L = 10, 10,000 rows): its directory bytes are smaller than the indexed table's (so the instrument sees the index).
7. **Stop condition.** If the boundary arms (item 5, first two lines) fail, stop before the scale arms (B2g last row).

### B3. Cluster tier

**B3a. Environment and build.** One node (second node optional), Linux, JDK 11, built from a local copy (`ant jar`). `cassandra.yaml` overrides: `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` on local disk of known size (>= 5 GB); `memtable_heap_space: 256MiB` (key per `Config.java:187`); `-Xms1g -Xmx1g`. SASI must be allowed to be created (it warns, `CreateIndexStatement.java:200-203`); not verified whether a yaml flag gates SASI in 5.0.9.

**B3b. Knobs.** Column-name length L in {40, 48, 49, 100} and index kind (custom SASI vs plain). Set via CQL DDL with `cqlsh`.

**B3c. Workload.** Per accepted case, a table with the named column; load 2 000 000 rows with `cassandra-stress` user profile or a small driver script (about 100-byte value), then `nodetool flush` and `nodetool compact`. Duration: minutes per case. Arithmetic: dataset about 200 MB raw, well above name bytes, so any name-driven effect would be visible against a data-driven one.

**B3d. Observables and instruments.** Heap: `jcmd <pid> GC.heap_info` and `nodetool info` after a forced GC; off-heap: `nodetool tablestats` ("Memtable off heap memory used", "Space used (live)"); disk: `du -sb` on the table data directory; JMX via `nodetool` only. Sample after load, after flush, after compaction. Cannot be observed: exact retained bytes of the name.

**B3e. Procedure.** 1. Start the node on local disk. 2. For each (L, kind): create keyspace/table/index (record accept/reject), load, flush, compact, record B3d readings. 3. Run the positive control. 4. Stop the node, check no `java` process left, delete data directories.

**B3f. Predictions.** Custom L=49 and L=100 rejected at DDL; L<=48 accepted. For accepted cases at equal data, heap, memtable and on-disk size are the same across L within a margin of the name bytes (not a step at 48); plain index with L=100 behaves the same as L=40.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Rejection at 49 only for custom; usage equal across L at equal data | Claim confirmed |
| Control (rows 0.5M vs 2M, or `memtable_heap_space` 128 vs 256 MiB) moves heap/disk while L does not | Confirms the instrument is sensitive; negative claim stands |
| Usage differs materially with L | Claim refuted |
| Control does not move, or limit never reached | Not confirmed |

**B3h. Controls.** Positive control: same workload with `memtable_heap_space` set to 128MiB vs 512MiB, expecting flush frequency and peak memtable heap to differ, a cap that is known to bind (`DatabaseDescriptor.java:586-590`, `AbstractAllocatorMemtable.java:81`). Baseline: same table without index. Run order randomized; fresh data dir per run.

### B3i. Audit amendments, cluster tier (stage 4, 2026-10-28)

1. **Node.** Local copy `~/s4-b2/c`; data, commit log, hints, saved caches and logs on tmpfs `/dev/shm/s4-b2/node` (the `>= 5 GB` local disk of B3a is not needed: a node holds about 1 GB; "disk bytes" are tmpfs bytes); one node, address 127.0.2.1, JMX 7270; `MAX_HEAP_SIZE=1G` as in B3a, `sasi_indexes_enabled: true` (B2i.1 answers B3a's open question), `memtable_allocation_type: heap_buffers` (the yaml default, so `memtable_heap_space` is the binding pool), `auto_snapshot: false`, `memtable_heap_space` per life (below), `memtable_cleanup_threshold` left at its default.
2. **Arms and lives.** Life A (`memtable_heap_space: 256MiB`, B3a): custom L = 40, 48, 49, 100; plain L = 40, 48, 100; no-index L = 40. Life B (`128MiB`) and life C (`512MiB`): plain L = 48 only (the B3h positive control, three points of the pool knob counting life A). Order inside a life as listed; fresh table and explicitly named index (`i_<arm>`) per arm, dropped after the arm.
3. **Workload.** The build's bundled Python driver, one INSERT per row, 128 requests in flight, 2,000,000 rows of a distinct random 100-character hex value into `(k int PRIMARY KEY, <col> text)`; seeded, the same data in every arm; then `nodetool flush`, `nodetool compact`. If the shakedown shows the driver cannot do 2,000,000 rows of one arm in 12 minutes, N is reduced for all arms (recorded as a runbook defect, no other change). **Amended 2026-10-28, before any cluster reading of run 1:** the first 2,000,000-row arm (discarded, aborted after 2 minutes) ran at about 2,700 rows/s, because the heap memtable costs about 1.4 KB per row and flushed every 85 MiB (60,000 rows at the 256 MiB pool): 12 minutes or more per arm and about 100 minutes for the 8 loaded arms. By this item N is 500,000 for every arm. At that size the 512 MiB pool (first flush at about 170 MiB with the default cleanup threshold, about 115,000 rows) still flushes about 4 times, so every life reaches its pool. Nothing else changes. The rejected arms (custom L = 49, 100) create the table, attempt the index, record the error text, and load nothing.
4. **Observables.** Per arm: DDL accept or reject with the exact text; rows accepted and rejected; recursive byte sum of the table directory (includes the plain index's hidden directory and SASI components) after flush and after compaction; `Enqueuing flush ... Reason: MEMTABLE_LIMIT` lines of `system.log` (count, logged on-heap usage of each); `jcmd <pid> GC.run` then `jcmd <pid> GC.heap_info` used heap, as information; RssAnon sampled every 2 s, as information.
5. **Numbers for B3f.** Custom L = 49 and 100 rejected at DDL with exactly "Column '<name>' is longer than the permissible name length of 48 characters", L = 40 and 48 accepted; plain L = 40, 48, 100 accepted; no row insert fails. Directory bytes after compaction: (max - min) / mean at most 2 percent across plain L = 40, 48, 100, and between custom L = 40 and 48. First `MEMTABLE_LIMIT` flush's logged on-heap usage: (max - min) / mean at most 15 percent across plain L = 40, 48, 100. Control (plain L = 48): ratio of the first logged `MEMTABLE_LIMIT` on-heap usage at 512 MiB over 128 MiB lies in [2.5, 6] (pool ratio 4); the flush count at 128 MiB is greater than at 512 MiB, and the count at 512 MiB is at least 1 (so the pool is reached in every life); directory bytes after compaction at 128 / 256 / 512 MiB agree within 2 percent. No-index L = 40 directory bytes are smaller than plain L = 40.
6. **Cleanup.** Stop the daemon, delete `/dev/shm/s4-b2`, verify with `ps -eo cmd | grep '[C]assandraDaemon'`.

**B4. Risks and cleanup.** Disk: up to a few GB per run on local disk only; never on shared storage or the shared source tree. Processes: stop the Cassandra JVM and any JUnit/stress JVM, verify with `pgrep -f cassandra`. Cleanup: remove `$WORK` and data, commitlog, hints and saved-caches directories. SASI creates experimental-feature warnings; no production data is used.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/schema/CreateIndexStatement.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/schema/SchemaConstants.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/schema/KeyspaceMetadata.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableMetadata.java (grep only)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java and DatabaseDescriptor.java (grep only)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java, SkipListMemtable.java (grep only)
- /users/jason92/cassandra-5.0.9/test (grep only)

## D. Stage-4 feedback

**2026-10-28, stage 4 (results: [`results/name_length-validatecustomindexcolumnname-name--autonomous.md`](../../stage4-runtime-verification/results/name_length-validatecustomindexcolumnname-name--autonomous.md), node `pc32`, run 1 only, self-checked).**

- **Unit tier: Confirmed (B2g rows 1 and 2) - does not cap.** Custom (SASI) L = 1, 47, 48 accepted, 49, 64, 200 rejected 3 of 3 with exactly "Column '<name>' is longer than the permissible name length of 48 characters"; plain index accepted at all six L (a 200-character column name is accepted by CREATE TABLE). At equal data (10,000 x 100 B) memtable `owns()` is the same for every L (6,020,000 B) and directory bytes differ by 0.010 percent (no step at 48: 560 B). Row-count control (1,000 / 10,000 / 100,000 rows) moved `owns()` 10.00x and 10.00x.
- **Cluster tier: Confirmed (B3g rows 1 and 2) - does not cap.** Custom 49 and 100 rejected at DDL with the exact text and no index created; custom 40, 48 and plain 40, 48, 100 took 500,000 rows each with 0 errors. Directory bytes after compaction: plain 170,365,850 / 170,365,253 / 170,363,381 (0.001 percent), custom 174,248,268 / 174,259,086 (0.006 percent). Pool control (plain 48): first pool-flush heap usage 42.8 / 85.3 / 170.6 MiB and 14 / 7 / 3 flushes at `memtable_heap_space` 128 / 256 / 512 MiB, final bytes 0.017 percent apart.
- **Outcome class: true negative.** The estimate stands.
- **Amendments of this audit:** B2i.1 answers the open question of B3a: SASI creation is gated by `sasi_indexes_enabled` (default false; `CreateIndexStatement.java:122-123`, `Config.java:606`), and every custom-index arm needs it set to true; the SASI warning is at lines 201-205. B3i.3 was amended after an aborted 2,000,000-row start (about 2,700 rows/s): N = 500,000 per arm, the pool was still reached in every life.
- **Side findings:** the javadoc of `NAME_LENGTH` ("KS or CF name") is stale for tables; the check is marked for removal in the source (CASSANDRA-20235, TODO at line 226); a plain index on 500,000 rows of 100 B costs 108 MB on top of a 62 MB table, independent of the name.
- **Not run:** the optional rebuild with the constant at 96; heap as evidence (noise of 10 to 15 MB between arms in a 1 GB heap exceeds any effect of a 60-byte name).
