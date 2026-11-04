# TABLE_NAME_LENGTH — verification solution  <!-- file: cases/table_name_length-validatetablename-name_length--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`TableMetadata.java:517`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableMetadata.java#L517) (`if (name.length() > TABLE_NAME_LENGTH)` in `validateTableName()`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the constant bounds the length of one identifier so that the table's directory name fits the 255-character file-name limit; it does not bound the heap, off-heap or disk volume a node uses. |
| Ground | The checked operand is a single string of at most 222 characters. It limits a file-name length (a filesystem naming limit), not an amount of data. Its worst-case memory and disk effect is a few hundred bytes per table (name copies in schema objects, plus the directory entry), which is not a memory- or disk-significant object. Usage scales with the number of tables, data written, memtable and cache settings, none of which this constant touches. |

> **Link rule.** Declaration and if statement are linked below.

## A. Constraint trace

**A1. The constraint.** `TABLE_NAME_LENGTH`; kind: hard-coded constant (not a yaml key, `-D` property, or runtime-queried value). Declared at [`SchemaConstants.java:91`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/SchemaConstants.java#L91) as `FILENAME_LENGTH - TABLE_UUID_AS_HEX_LENGTH - TABLE_DIRECTORY_NAME_SEPARATOR.length()`. The operands (verified): `FILENAME_LENGTH = 255` (SchemaConstants.java:80, javadoc "Longest acceptable file name"), `TABLE_UUID_AS_HEX_LENGTH = 32` (SchemaConstants.java:85), `TABLE_DIRECTORY_NAME_SEPARATOR = "-"` (db/Directories.java:123, statically imported at SchemaConstants.java:35). Value: 255 - 32 - 1 = 222. Unit: characters of the table name. Not settable by yaml, `-D` or JMX; changing it needs a source edit, rebuild and restart. The earlier trace's A1 is confirmed. Note a related but different constant: `NAME_LENGTH = 48` (SchemaConstants.java:75) is applied to keyspace names (KeyspaceMetadata.java:68) and custom index targets (CreateIndexStatement.java:213), not to table names; grep of the tree found no use of it in `validateTableName()`.

**A2. What it caps.** Neither heap nor off-heap nor disk volume. It caps the number of characters in a table name so that the table's directory name `<name>-<32 hex chars of table id>` (built at TableMetadata.java:638-641) is at most 255 characters, the file-name limit of common filesystems. The quantity compared is `name.length()` (an `int`).

**A3. Mechanism.**
1. `TableMetadata.validate()` (TableMetadata.java:481) calls `validateKeyspaceName` (:483) then `validateTableName()` (:484, checked).
2. `validateTableName()` is declared at TableMetadata.java:512. First, `isValidCharsName(name)` (:514; defined SchemaConstants.java:105, pattern `\w+` at :42) rejects empty or non-word names.
3. The check: [`TableMetadata.java:517`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableMetadata.java#L517) `if (name.length() > TABLE_NAME_LENGTH)`; when true, line 518 calls `except(...)`, which throws a configuration exception (TableMetadata.java:716-719). Table creation then fails; nothing is created. When false, validation continues.
4. Line 520 is an `assert` that the generated directory name length is at most `FILENAME_LENGTH`; it is a consistency check (only active with `-ea`) and cannot fail if line 517 passed, since 222 + 1 + 32 = 255.
5. The CQL path reaches it through `CreateTableStatement` (`table.validate()` at cql3/statements/schema/CreateTableStatement.java:112).
Bypass or overshoot: the check is applied at validation of a `TableMetadata`; whether schema loaded from disk or received from a peer is re-validated on every path is not verified. It does not bound anything except the length of one name.

**A4. Other consumers.** The same memory and disk are used by memtables, sstables, caches, commit log, hints, and per-table metadata and metrics, all governed by other settings. Table name copies exist in `TableMetadata`, `ColumnFamilyStore`, metric and MBean names (not verified line by line); their size scales with table count times name length.

**A5. Evidence beyond the source.** The javadoc at SchemaConstants.java:86-90 states the purpose (name must fit a directory name with id suffix and separator). The javadoc at SchemaConstants.java:70-74 (above `NAME_LENGTH`) mentions an earlier Windows-path limit change, with an issue number I do not cite (not verified). Otherwise none. [Amendment 2026-10-28: verified, it names CASSANDRA-16956; see B5 item 1.]

## B. Verification solution

**B1. Claim under test.** Usage of heap, off-heap and disk does not follow `TABLE_NAME_LENGTH`: a name at the limit (222 characters) compared with a short name adds only a per-table amount proportional to the name length (order of hundreds of bytes), and the limit rejects a 223-character name without any change in node memory or data size. Falsified if raising the name length from short to 222 changes node heap or disk usage by an amount comparable to a binding cap (for example megabytes per table).

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a ~/cassandra-5.0.9/ /local/work/c509/`), never build in the shared tree. `cd /local/work/c509 && ant jar` then a small JUnit test under `test/unit/org/apache/cassandra/schema/` (new file in the copy only) run with `ant testsome -Dtest.name=<Class>`. JVM options: `-ea` (so the assert at TableMetadata.java:520 is live), `-Xmx512m`, plus the jamm agent that the Cassandra build already supplies for `MemoryMeter`.

**B2b. Knobs.** The table name length L, built as a string of `a` repeated: 1, 48, 100, 221, 222, 223, 255. Why: 222 is the limit, 221 and 223 straddle it, 48 shows the keyspace limit does not apply, 255 shows the far side. Set in test code via `TableMetadata.builder("ks", name)` with one partition key column.

**B2c. Workload.** For each L, build `TableMetadata`, call `validate()`. For accepted names, also measure the retained size of the object. Reaching the limit is just L = 222; going past is L = 223. Also build N = 1000 distinct tables of name length L (distinct by a numeric suffix inside the L characters) to scale the per-table cost. [Amendment 2026-10-28: names, N and instrument, see B5 items 2 and 3.]

**B2d. Observables and instruments.** (1) Outcome of `validate()`: returns normally or throws `ConfigurationException` (message from TableMetadata.java:518). (2) `getTableDirectoryName().length()` for accepted names. (3) Retained deep size of the `TableMetadata` via jamm `MemoryMeter.measureDeep`. Not observable: real node heap, which is for the cluster tier.

**B2e. Procedure.** 1. Build the jar. 2. Write the test that loops over L and records the three observables. 3. Run it once with L in the knob list. 4. Repeat measureDeep for N = 1000 tables and divide for per-table cost at L = 1 and L = 222. 5. Positive control: measure the same object after adding 50 columns (size is driven by structure, a quantity that moves memory), and report the delta.

**B2f. Predictions.** L = 1..222 accepted; L = 223 and 255 throw with the message at line 518; no assert failure at any accepted L; directory name length at L = 222 equals 255. Deep size increases with L by about 2 bytes per character per retained copy of the name (Java 11 compact strings may give 1 byte), i.e. the 1 to 222 difference is a small multiple of 221 bytes, far below the delta from adding 50 columns.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| 222 accepted, 223 rejected, directory name 255 at L = 222 | Mechanism works as traced |
| 223 accepted | Trace wrong (limit not at 222) |
| Deep size delta from L = 1 to 222 comparable to or larger than the 50-column delta | Claim refuted: name length drives memory significantly |
| Deep size delta small and proportional to L, 50-column delta much larger | Claim confirmed (usage does not follow the constraint in a significant way; control moved) |
| 50-column control does not move size, or the limit is never reached | Not confirmed; instrument problem |

**B2h. Controls.** Same JVM and flags for all runs; run each measurement after a warm-up and after `System.gc()`; the 50-column case is the positive control; names built from the same character to avoid interning differences.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from the local copy (`ant jar`), data, commitlog, hints and saved_caches under a dedicated local directory (for example `/local/work/node1/`) on local disk of known free space (at least 10 GiB). JVM: `-Xms1g -Xmx1g`, G1. `cassandra.yaml` unchanged except directory paths and `memtable_heap_space` / `memtable_offheap_space` for the control.

**B3b. Knobs.** Table name length L in {8, 222} (two arms), table count N = 500 per arm (separate fresh node data each arm), and a rejected attempt at L = 223. Control knob: `memtable_heap_space` 64MiB versus 256MiB with the same write load. Set by cqlsh DDL and yaml respectively; the constant itself cannot be changed.

**B3c. Workload.** Create N = 500 tables per arm, each with `(id int PRIMARY KEY, v text)`, names of exactly L characters made unique by a 3-digit suffix. Write 1,000 rows of 100 bytes to each table (500,000 rows, about 50 MB payload) with `cqlsh` COPY or a small driver script, then flush. Then attempt `CREATE TABLE` with a 223-character name. Duration: until schema agreement and flush completes (minutes). For the control: one table, 5 GiB of writes with the two memtable settings. [Amendment 2026-10-28: control size and observables, see B5 item 6; arms and client, item 4.]

**B3d. Observables and instruments.** Heap: `jcmd <pid> GC.class_histogram` and `jstat -gc` after a forced `jcmd <pid> GC.run`; used heap after GC. Disk: `du -sb` on the data directory per arm, and `ls` of the table directory names (length). Rejection: the cqlsh error text. Not observable directly: per-table share of heap (inferred from the difference between arms). [Amendment 2026-10-28: heap and disk readings, see B5 item 5; reading rules, item 7.]

**B3e. Procedure.** 1. Build and start node on the arm L = 8. 2. Create the 500 tables, write, flush, `GC.run`, record used heap, `du -sb`. 3. Stop node, wipe data, repeat for L = 222. 4. On the L = 222 node, try `CREATE TABLE` with 223 characters and record error. 5. Control: fresh node, single table, 5 GiB writes with `memtable_heap_space` = 64MiB then 256MiB; sample `jstat -gc` every 5 s; record peak heap after GC. 6. Stop all processes.

**B3f. Predictions.** The 223-character `CREATE TABLE` fails with the message "Table name must not be more than 222 characters long". Heap-after-GC difference between L = 8 and L = 222 arms is small, bounded by roughly 500 tables times a few hundred bytes times a small number of name copies (low hundreds of KiB at most) and well below 1% of the 1 GiB heap. `du -sb` difference between arms is the directory-name bytes plus identical data, so within a small fraction of the data size. In the control, peak heap differs clearly between the two memtable settings.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| 223 rejected with the exact message; L = 8 and L = 222 arms differ by far less than the control difference | Claim confirmed: usage does not follow the constraint |
| Arms differ by an amount comparable to the control difference | Claim refuted: name length significantly drives usage |
| 223 accepted | Mechanism not as traced |
| Control heap does not change between 64MiB and 256MiB, or the cap is never reached | Not confirmed (positive control failed) |

**B3h. Controls.** Identical JVM flags, workload, row data and flush state across arms; the memtable-space run is the positive control showing a cap that binds; repeat each arm twice to see run-to-run noise.

**B4. Risks and cleanup.** Disk: 500 tables x 1,000 rows per arm and 5 GiB control stay on the dedicated local directory; check `df` before each run. No shared storage and no writes to the shared source tree. Leftover processes: after each run `jcmd`/`ps` check that no Cassandra or test JVM remains; kill by pid; delete `/local/work/node1/` and `/local/work/c509/` at the end.

## B5. Stage-4 design audit: amendments (2026-10-28)

Applied before run 1, for reasons that do not depend on any reading. Prediction rows B2f/B3f and conclusions tables B2g/B3g are unchanged; items below fix instruments, name generation and operational thresholds that B2g/B3g leave as "comparable" or "small".

1. **A5 completed.** The javadoc above `NAME_LENGTH` (SchemaConstants.java:70-74) names CASSANDRA-16956; read on 2026-10-28, so "an issue number I do not cite (not verified)" is now verified. All other line citations in A1 to A3 were re-read against `cassandra/cassandra-5.0.9/` and match (517-518, 520, 512, 484, 638, 716, 112; SchemaConstants 75, 80, 85, 91; Directories 123).
2. **Size instrument (B2a, B2d).** `MemoryMeter.measureDeep` / `ObjectSizes.measureDeep` cannot be used: `TableMetadata` and `ColumnMetadata` carry jamm's `@Unmetered`, so both stop at them (shakedown: 1000 tables measured 4 bytes each; defect D1). The deep size is a reflective walk of the object graph (identity visited-set; enums, `Class`, `AbstractType` singletons and `Reference`s skipped) that sizes each visited object with jamm's shallow `MemoryMeter.measure`; `ObjectSizes.measureDeep` is printed beside it. Tables are `TableMetadata.builder("ks", name).addPartitionKeyColumn("k", Int32Type.instance)` (plus `addRegularColumn` x 50 for the control); the test checks `TableMetadataTest`-style assertions are enabled (`-ea` in `ant testsome`) and reports it.
3. **Names (B2b, B2c).** Names for the N-table sizing are the index in base 36 left-padded with `a` to exactly L characters: L = 1 can supply only 36 names, so N = 36 at L = 1 and N = 1000 for L >= 2. Per-table cost = deep size / N. L = 255 is validated only (the builder does not validate).
4. **Cluster client and arms (B3b, B3c).** Tables are created and written by the build's bundled Python driver (protocol 4, consistency ONE, one client). The L = 8 arm names are `t` + 4 characters of padding + 3-digit suffix (8 characters); the L = 222 arm names are 219 `a` + a 3-digit suffix. Each arm is run twice (A1, A2 = L 8; B1, B2 = L 222), fresh data directory each, order A1 B1 A2 B2; the 223-character `CREATE TABLE` is tried at the end of B1 and B2.
5. **Heap and disk readings (B3d).** "Heap after GC" = `jcmd GC.run`, then JMX `HeapMemoryUsage.used`, then `jcmd GC.class_histogram` (it runs its own full GC), `Total` bytes as the second reading; taken after `nodetool flush` and a 60 s settle. Disk = `du -sb` of the data directory, plus the longest table-directory name (`ls`).
6. **Control (B3b, B3e step 5), made exact.** 5 GiB is not needed to cross a 256 MiB memtable pool: 100-byte values carry well over 100 bytes of on-heap row overhead, so 3,000,000 rows (about 300 MB of payload, over 600 MB on heap) cross both 64 MiB and 256 MiB. The control is one keyspace `kc` with one table `t`, 3,000,000 rows x 100-byte values, `memtable_allocation_type: heap_buffers` (the shipped default), `memtable_heap_space` = 64MiB then 256MiB, 1 GiB heap, same flags. Observables: peak of the JMX gauge `org.apache.cassandra.metrics:type=Table,name=AllMemtablesHeapSize` sampled every 1 s (replaces the 5-s `jstat` sampling, which cannot see the pool), and `Enqueuing flush of` lines in `system.log`. "Differs clearly" means the 64 MiB peak is at most half the 256 MiB peak and the 64 MiB run flushes more.
7. **Reading rules (B3g), fixed before any reading.** Name-byte budget = 500 tables x (222 - 8) bytes x 20 retained copies = about 2.1 MB. "Within noise" = the difference of the two arms' means (class-histogram `Total`) is no larger than the larger of the budget and the spread between the two repetitions of one arm. Claim refuted by the cluster tier if the difference exceeds both that and 10 % of the control's peak difference. `du` of the data directory "differs" if the arms differ by more than 1 % of the data size.
8. **Heap size.** B3a's 1 GiB heap is kept; if 500 tables do not fit it (OutOfMemoryError, or heap after GC above 70 % of the heap), that is a runbook defect, not a redesign: the heap is raised for both arms and the control stays at 1 GiB only if it is unaffected.

## C. Sources read

- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/INSTRUCTIONS.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/playbook-autonomous.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/_TEMPLATE-autonomous.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-in/158.md
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableMetadata.java (lines 476-530, 636-642, 714-720)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/schema/SchemaConstants.java (lines 70-112)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java (line 123, via grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/schema/KeyspaceMetadata.java, cql3/statements/schema/CreateIndexStatement.java, cql3/statements/schema/CreateTableStatement.java, schema/TableId.java (grep only)

## D. Stage-4 feedback

2026-10-28, stage 4 (autonomous session on `pc29`): **unit Confirmed (does not cap, for the schema objects it measures), cluster Refuted (caps); outcome class undetermined because the tiers disagree; the cluster tier measured the real node and reads as a false negative of the estimate.** Results: [`results/table_name_length-validatetablename-name_length--autonomous.md`](../../stage4-runtime-verification/results/table_name_length-validatetablename-name_length--autonomous.md). Design amended before run 1 by block B5 (dated 2026-10-28; B2f/B3f and B2g/B3g not changed). The traced check held: 1 to 222 characters pass (directory name 255 at 222), 223 and 255 are refused with "Table name must not be more than 222 characters long", at the unit level and for a `CREATE TABLE` at the node. Unit: retained size of a `TableMetadata` rises 216 B from 2 to 222 characters, against +5,128 B for 50 columns. Cluster (500 tables x 1,000 rows, 8 vs 222 characters, two repetitions each, 1 GiB heap): heap after GC is higher by 60.7 MB (about 121 KB per table; repetition spread 2.3 and 4.9 MB; `byte[]` accounts for all of it) and the data directory by 1.3 %, against 66.7 MB that `memtable_heap_space` 64MiB vs 256MiB moves on the same instruments (peak memtable heap 22.3 MB vs 89.1 MB, flushes 110 vs 49). A supplementary count on a separate node (20 tables) found 112 metric MBeans per table whose names carry the table name (+23,968 characters per table at 222 vs 8), which with about 5 retained copies of that text per table matches the size of the difference. This is the "metric and MBean names (not verified line by line)" consumer that A4 named: the constant does bound a per-table heap cost of order 0.5 KB per name character, small per table but not negligible with hundreds of tables; the prediction in B3f ("low hundreds of KiB at most, below 1 % of heap") assumed about 20 name copies per table and was wrong by about two orders of magnitude. Not traced: the references that hold the copies (no heap dump). The unit design (B2) cannot see this consumer because it builds `TableMetadata` without registering metrics; a unit tier that registers `TableMetrics` for the table would. Defect D1 (the build's `ObjectSizes.measureDeep` stops at `@Unmetered` `TableMetadata`) is recorded in B5 item 2. The Estimate line is left as filed.
