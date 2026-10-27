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

`none yet`
