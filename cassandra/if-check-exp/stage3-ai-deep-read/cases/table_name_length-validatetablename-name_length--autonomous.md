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

**A5. Evidence beyond the source.** The javadoc at SchemaConstants.java:86-90 states the purpose (name must fit a directory name with id suffix and separator). The javadoc at SchemaConstants.java:70-74 (above `NAME_LENGTH`) mentions an earlier Windows-path limit change, with an issue number I do not cite (not verified). Otherwise none.

## B. Verification solution

**B1. Claim under test.** Usage of heap, off-heap and disk does not follow `TABLE_NAME_LENGTH`: a name at the limit (222 characters) compared with a short name adds only a per-table amount proportional to the name length (order of hundreds of bytes), and the limit rejects a 223-character name without any change in node memory or data size. Falsified if raising the name length from short to 222 changes node heap or disk usage by an amount comparable to a binding cap (for example megabytes per table).

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a ~/cassandra-5.0.9/ /local/work/c509/`), never build in the shared tree. `cd /local/work/c509 && ant jar` then a small JUnit test under `test/unit/org/apache/cassandra/schema/` (new file in the copy only) run with `ant testsome -Dtest.name=<Class>`. JVM options: `-ea` (so the assert at TableMetadata.java:520 is live), `-Xmx512m`, plus the jamm agent that the Cassandra build already supplies for `MemoryMeter`.

**B2b. Knobs.** The table name length L, built as a string of `a` repeated: 1, 48, 100, 221, 222, 223, 255. Why: 222 is the limit, 221 and 223 straddle it, 48 shows the keyspace limit does not apply, 255 shows the far side. Set in test code via `TableMetadata.builder("ks", name)` with one partition key column.

**B2c. Workload.** For each L, build `TableMetadata`, call `validate()`. For accepted names, also measure the retained size of the object. Reaching the limit is just L = 222; going past is L = 223. Also build N = 1000 distinct tables of name length L (distinct by a numeric suffix inside the L characters) to scale the per-table cost.

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

**B3c. Workload.** Create N = 500 tables per arm, each with `(id int PRIMARY KEY, v text)`, names of exactly L characters made unique by a 3-digit suffix. Write 1,000 rows of 100 bytes to each table (500,000 rows, about 50 MB payload) with `cqlsh` COPY or a small driver script, then flush. Then attempt `CREATE TABLE` with a 223-character name. Duration: until schema agreement and flush completes (minutes). For the control: one table, 5 GiB of writes with the two memtable settings.

**B3d. Observables and instruments.** Heap: `jcmd <pid> GC.class_histogram` and `jstat -gc` after a forced `jcmd <pid> GC.run`; used heap after GC. Disk: `du -sb` on the data directory per arm, and `ls` of the table directory names (length). Rejection: the cqlsh error text. Not observable directly: per-table share of heap (inferred from the difference between arms).

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

`none yet`
