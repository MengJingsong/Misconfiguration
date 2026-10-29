# SchemaConstants.NAME_LENGTH — verification solution  <!-- file: cases/schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`KeyspaceMetadata.java:68`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/KeyspaceMetadata.java#L68) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the constant bounds only the character length of a keyspace (and index-target column) name, so it can add at most a few dozen bytes per name; it does not bound the number of keyspaces or any memory- or disk-significant structure. |
| Ground | The limit is a per-name string length. Memory and disk grow with the number of keyspaces, tables, sstables and data; a 48-character name versus a 1-character name changes each retained name string by tens of bytes. Nothing in the check relates name length to a budget. |

> **Link rule.** Followed: the declaration (A1) and the if statement (Entry pointer, A3) are permalinks at `cassandra-5.0.9`.

## A. Constraint trace

**A1. The constraint.** `SchemaConstants.NAME_LENGTH`; kind: constant (not a yaml key, `-D` property or JMX value). Declared at [`SchemaConstants.java:75`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/SchemaConstants.java#L75) as `public static final int NAME_LENGTH = 48;`. Its javadoc (SchemaConstants.java:69-74) calls it the longest permissible keyspace or table name and says the older 255-character path limit tied to CASSANDRA-16956 is no longer in effect (the javadoc names that issue; the number is as printed in the source, not otherwise checked). Unit: characters (UTF-16 `String.length()`; names are restricted to word characters, SchemaConstants.java:103-106 `isValidCharsName`, so characters equal bytes in practice). Default: literal 48, no derivation. Not settable at runtime or by configuration; a change needs a source edit and rebuild. Correction to the earlier trace: the table-name check does NOT use this constant; it uses `TABLE_NAME_LENGTH` (SchemaConstants.java:91, used at TableMetadata.java:517), derived from `FILENAME_LENGTH` (SchemaConstants.java:80). `NAME_LENGTH` is used for keyspace names and for custom-index target column names (CreateIndexStatement.java:213-214).

**A2. What it caps.** Neither memory nor disk directly. It caps the length of a keyspace name (and a custom-index target column name). The operand is `keyspaceName.length()`. A keyspace name is also used for the data directory name, so the cap indirectly limits that directory-name length, but not any size.

**A3. Mechanism.** `KeyspaceMetadata.validateKeyspaceName` (KeyspaceMetadata.java:63) first rejects empty or non-word-character names (KeyspaceMetadata.java:65 using SchemaConstants.java:103-106), then runs the check [`KeyspaceMetadata.java:68`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/KeyspaceMetadata.java#L68) `if (keyspaceName.length() > SchemaConstants.NAME_LENGTH)`, which throws via the caller-supplied exception builder (KeyspaceMetadata.java:69-70). Callers: `KeyspaceMetadata.validate()` (KeyspaceMetadata.java:338), `TableMetadata.validate()` (TableMetadata.java:482), and `AlterSchemaStatement.execute` (AlterSchemaStatement.java:116, before `Schema.instance.transform`, line 118). Outcomes: length <= 48 passes silently; length >= 49 throws (an InvalidRequestException for CQL statements via `AlterSchemaStatement::ire`, a ConfigurationException from `validate()`) and the schema change is not applied. Bypass: any path that builds `KeyspaceMetadata` without calling `validate()` or the statement path (for example schema loaded from disk at startup) is not shown to be checked; not verified. No overshoot concept exists since this is a boolean length test.

**A4. Other consumers.** Memory and disk are consumed by the number of keyspaces/tables, their `TableMetadata` objects, per-table memtables, caches, sstables and commit log, none governed by this constant. Name strings themselves are retained in schema objects, directory names and the schema tables.

**A5. Evidence beyond the source.** none (only the source javadoc above).

## B. Verification solution

**B1. Claim under test.** Memory and disk usage do not follow `NAME_LENGTH`: moving keyspace names from 1 character to the 48-character maximum changes retained heap and on-disk size only by an amount proportional to the extra name bytes (tens of bytes per name), negligible beside a control that does bind (memtable space or data volume); and the check rejects exactly lengths above 48.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $LOCAL/c509/`), `cd $LOCAL/c509 && ant jar`. Put a JUnit test (or small main) in the local copy only, e.g. `$LOCAL/c509/test/unit/org/apache/cassandra/schema/NameLengthProbeTest.java`. Run with `ant testsome -Dtest.name=NameLengthProbeTest`. JVM opts: `-Xmx512m`, plus JOL (`org.openjdk.jol:jol-core`, added to the local classpath) for object graph size, or `-javaagent` with an instrumentation sizeof.

**B2b. Knobs.** Keyspace-name length L in {1, 10, 47, 48, 49, 100}; number of keyspaces N in {1, 1000}; control knob: tables per keyspace T in {0, 10}. Set by constructing names programmatically (`"k".repeat(L)`).

**B2c. Workload.** Direct call of `KeyspaceMetadata.validateKeyspaceName(name, ConfigurationException::new)` for each L (limit reached at L=48, passed at L=49). For retained size: build `KeyspaceMetadata.create(name, KeyspaceParams.simple(1))` for N names, with and without T tables, and measure the object graph. Arithmetic: going from L=1 to L=48 adds 47 bytes (Latin-1 compact strings under JDK 11) per retained name copy. [Amendment 2026-10-28: names and N, see B5 items 1 and 2.]

**B2d. Observables and instruments.** (1) Exception or no exception per L, and the message text. (2) Deep retained size of the `KeyspaceMetadata` list via JOL `GraphLayout.parseInstance(list).totalSize()`. Not observable here: real node heap.

**B2e. Procedure.** 1. Build. 2. For each L call validate, record pass/fail. 3. For each (L, N, T) build the list, force GC, record deep size. 4. Repeat three times and compare. 5. Delete the local copy.

**B2f. Predictions.** Pass for L=1..48, ConfigurationException for L=49 and 100. Deep size grows by roughly N x (47 x number of name copies) bytes between L=1 and L=48, a small fraction of the total; adding T=10 tables per keyspace changes deep size by far more than the L change.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| L=49 accepted, or L=48 rejected | Check not as traced; claim about the check wrong |
| Deep size scales with L by more than a few name copies' worth of bytes | Usage follows the knob; claim refuted |
| Deep size changes by tens of bytes per name while the T control moves it by orders more | Usage flat against the constraint while the positive control moves; claim confirmed |
| Control (T) does not move the size, or L=48 never reached | Not confirmed |

**B2h. Controls.** Positive control: T tables per keyspace (known to add retained objects). Same JVM, same GC step before each measurement, same N across L.

### B3. Cluster tier

**B3a. Environment and build.** One node on a local disk of known size (>= 20 GB free), JDK 11, built from the local copy as above (`ant jar`; run `bin/cassandra -f` from the copy). `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` all under `$LOCAL/run`. `-Xms2G -Xmx2G` in jvm11-server.options.

**B3b. Knobs.** Name length L in {1, 48} (and an attempted 49 expecting rejection); keyspaces N = 200; control A: tables per keyspace; control B (a cap known to bind): `memtable_heap_space` set to 64MiB versus 256MiB in cassandra.yaml with the same write load.

**B3c. Workload.** Run 1: create N keyspaces with L=1 names (suffix digits to keep unique; use L=3 where needed to fit N=200, and state the actual length), each with one table `t(id int primary key, v text)`. Run 2: the same with 48-character names. Do the identical writes to each (cqlsh/`cassandra-stress`, 10000 rows x 100-byte values per keyspace). Duration: until flush and compaction idle. Arithmetic: 200 x 10000 x ~100 B = about 200 MB of raw data per run, fits the disk and heap. [Amendment 2026-10-28: arms, client and control B, see B5 items 3 and 5.]

**B3d. Observables and instruments.** Heap after forced GC (`jcmd <pid> GC.run`, `jcmd <pid> GC.heap_info`), `nodetool info` heap, `nodetool tablestats`, `du -sb $LOCAL/run/data`, `ls` of the data directory for name lengths. Not observable directly: per-name string retention (would need a heap dump with `jcmd GC.heap_dump`, optional). [Amendment 2026-10-28: heap and disk readings, see B5 item 4; reading rules, B5 item 6.]

**B3e. Procedure.** 1. Start node with clean dirs. 2. Run 1 creation and load. 3. `nodetool flush`; `jcmd GC.run`; record heap, `du`. 4. Stop node, wipe dirs. 5. Repeat with 48-character names. 6. Try `CREATE KEYSPACE` with 49 characters; record the error. 7. Control B: with 1-character names, run the same load at both memtable_heap_space values and record heap and flush counts. 8. Stop node (`kill`, confirm no leftover `jps`), delete `$LOCAL/run`.

**B3f. Predictions.** Step 6 returns an error mentioning 48 characters. Heap-after-GC and `du` differ between L=1 and L=48 by a margin consistent with N x tens of bytes plus longer directory names (kilobytes in total), i.e. within run-to-run noise of the data volume. Control B: heap and flush behaviour differ clearly between the two memtable_heap_space values.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Heap or disk differs between L=1 and L=48 by more than noise and more than the name-byte arithmetic | Usage follows the constraint; claim refuted |
| Difference is within noise, while control B moves heap/flush clearly | Claim confirmed |
| 49-char keyspace is created | Check not effective as traced; claim wrong |
| Control B shows no movement, or runs are not repeatable | Not confirmed |

**B3h. Controls.** Repeat each run at least twice to measure noise; same load, same JVM flags, same node restart state; positive control is memtable_heap_space (B3b).

**B4. Risks and cleanup.** Disk: keep all node dirs on local disk under `$LOCAL/run`, about 1 GB expected; never on shared storage. Do not build in the shared tree. Stop the node and any `jcmd`/stress processes and check with `jps`/`pgrep -u $USER java`; remove `$LOCAL/c509` and `$LOCAL/run`.

## B5. Stage-4 design audit: amendments (2026-10-28)

Applied before run 1, for reasons that do not depend on any reading. Prediction rows B2f/B3f and conclusions tables B2g/B3g are unchanged; items below fix instruments, name generation and the operational thresholds that B2g/B3g leave as "more than noise".

1. **Size instrument (B2a, B2d).** JOL is not on the build's classpath; the build ships jamm (`lib/jamm-0.4.0.jar`). `ObjectSizes.measureDeep` cannot be the deep sizer: `TableMetadata` and `ColumnMetadata` carry jamm's `@Unmetered`, so it stops at them (found in the table-name case's shakedown; a first unit run of this case that used it was discarded, defect D1). The deep size is a reflective walk of the object graph (identity visited-set; enums, `Class`, `AbstractType` singletons and `Reference`s skipped) that sizes each visited object with jamm's shallow `MemoryMeter.measure`; `ObjectSizes.measureDeep` is printed beside it.
2. **Names (B2b, B2c).** A name is the index written in base 36 (`[0-9a-z]`) left-padded with `k` to exactly L characters. L = 1 can supply only 36 distinct names, so N = 36 at L = 1 and N = 1000 for L >= 2 (L = 2 gives 1296 names). Sizes are compared as bytes per keyspace (deep size / N). L = 49 and 100 are measured too (`KeyspaceMetadata.create` does not validate). Extra check, same path as A3: `TableMetadata.validate()` for a table in a 49-character keyspace must throw (A3 lists it as a caller).
3. **Cluster client and arms (B3b, B3c).** The short arm uses L = 3 names (B3c allows it; 200 names need at least 2 characters), the long arm L = 48; 200 keyspaces, one table `t(id int primary key, v text)` each, 10000 rows x 100-character values per keyspace, written by the build's bundled Python driver (protocol 4, consistency ONE, one client) instead of cqlsh/cassandra-stress. Each arm is run twice (A1, A2 = L 3; B1, B2 = L 48), a fresh data directory each, order A1 B1 A2 B2. A 49-character `CREATE KEYSPACE` is tried at the end of every long-arm run.
4. **Heap and disk readings (B3d).** "Heap after GC" = `jcmd GC.run`, then JMX `HeapMemoryUsage.used`, then `jcmd GC.class_histogram` (it runs its own full GC) whose `Total` bytes line is the second reading; both are taken after `nodetool flush` and a 60 s settle. Disk = `du -sb` of the data directory and of the commit log directory (the latter is preallocated segments, so it only shows file counts).
5. **Control B (B3b, B3e step 7), made exact.** One keyspace `kc3` (3 characters), one table `t`, 3,000,000 rows x 100-byte values (about 300 MB of payload; on-heap row overhead makes the memtable cross both 64 MiB and 256 MiB), `memtable_allocation_type: heap_buffers` (the shipped default, stated), `memtable_heap_space` = 64MiB then 256MiB, same JVM flags. Observables: peak of the JMX gauge `org.apache.cassandra.metrics:type=Table,name=AllMemtablesHeapSize` sampled every 1 s, and the number of `Enqueuing flush of` lines in `system.log` for the run. Control B "moves clearly" means: the 64 MiB peak is at most half the 256 MiB peak and the 64 MiB run has more flushes.
6. **Reading rules (B3g), fixed before any reading.** Name-byte budget = N x (48 - 3) bytes x 50 retained copies = 200 x 45 x 50 = 450 KB. "Within noise" = the difference of the two arms' means (class-histogram `Total`) is no larger than the larger of the budget and the spread between the two repetitions of one arm. Claim refuted by the cluster tier if the difference exceeds both that and 10 % of control B's peak difference. `du` of the data directory "differs" if the arms differ by more than 1 % of the data size.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/schema/KeyspaceMetadata.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/schema/SchemaConstants.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableMetadata.java (lines 476-484, 517-520)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/schema/AlterSchemaStatement.java (lines 108-120)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/schema/CreateIndexStatement.java (lines 205-216)
- grep for NAME_LENGTH and validateKeyspaceName over src/java

## D. Stage-4 feedback

2026-10-28, stage 4 (autonomous session on `pc29`): **unit Confirmed, cluster Confirmed, Effect on the constraint: does not cap; outcome class true negative.** Results: [`results/schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous.md`](../../stage4-runtime-verification/results/schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous.md). Design amended before run 1 by block B5 (dated 2026-10-28; the prediction rows B2f/B3f and tables B2g/B3g were not changed). The traced path held: lengths 1 to 48 pass and 49 and 100 are refused with "Keyspace name must not be more than 48 characters long" in `validateKeyspaceName`, `KeyspaceMetadata.validate()` and `TableMetadata.validate()` (unit) and for a `CREATE KEYSPACE` at the node (cluster, both long arms). Unit: retained size per keyspace rises 32 B from 10 to 48 characters (one string copy; tables of the keyspace share the string), against +8,994 B for ten tables. Cluster (200 keyspaces x 10,000 rows, 3 vs 48 characters, two repetitions): heap after GC differs by +4.2 MB inside a 16.9 MB repetition spread, data directory by +0.1 %; the control `memtable_heap_space` 64MiB vs 256MiB moved peak memtable heap from 89.4 MB to 22.3 MB and flushes from 49 to 110. Caveats: the cluster tier resolves differences only down to about 17 MB, and the +4.2 MB is probably a small real effect of the keyspace name text held in the per-table metric MBean names (the sibling table-name case counted 112 metric MBeans per table and about 4.8 retained copies of the name text; 200 x 112 x 45 x 4.8 is about 4.8 MB), so "tens of bytes per name" holds for the schema objects only (unit tier), not for the node as a whole; the custom-index use of `NAME_LENGTH` (CreateIndexStatement.java:213) and the startup-load bypass (A3) were not run. Defect D1 (the build's `ObjectSizes.measureDeep` stops at `@Unmetered` `TableMetadata`) is recorded in B5 item 1 and in the results file.
