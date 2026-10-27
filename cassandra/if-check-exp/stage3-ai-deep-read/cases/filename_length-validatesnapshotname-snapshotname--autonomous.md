# FILENAME_LENGTH — verification solution  <!-- file: cases/filename_length-validatesnapshotname-snapshotname--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`ColumnFamilyStore.java:2185`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L2185) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the check bounds the character length of a snapshot name (a string of at most 255 characters), not the size of the snapshot or any memory or disk quantity. |
| Ground | The operand is `snapshotName.length()`. A snapshot is made of hard links to existing SSTable files plus a manifest and schema file; none of those sizes depends on the length of the snapshot name. The only memory or disk effect of the name is a directory-name component and a few bytes in the in-memory snapshot record, bounded to a few hundred bytes at most. |

## A. Constraint trace

**A1. The constraint.** `SchemaConstants.FILENAME_LENGTH`, a compile-time constant (`public static final int`), first declared at [`SchemaConstants.java:80`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/SchemaConstants.java#L80). Unit: characters of a single file or directory name component. Default: the literal `255`, not derived from anything (its javadoc at `SchemaConstants.java:77-79` says longer names lead to a too-long-file-name error). It is not settable by yaml, `-D` or JMX; changing it needs a code change and rebuild. The same constant bounds `TABLE_NAME_LENGTH` (`SchemaConstants.java:91`, = FILENAME_LENGTH - 32 - separator length) and a table directory-name assertion (`TableMetadata.java:520`).
The earlier trace is correct on these points. One correction/addition: the length check is gated by the JVM property `cassandra.snapshot.validation` (`CassandraRelevantProperties.java:517`, `SNAPSHOT_NAME_VALIDATION`, default string `"false"`), read at call time with `.getBoolean()` (`ColumnFamilyStore.java:2180`). With the default, the length check (and the character-pattern check at `ColumnFamilyStore.java:2200`) is skipped entirely. Because it is read at each call, a test can toggle it in-process (`SnapshotTest.java:65` and `:126` do this with `WithProperties`); for a node it is set with `-D` at startup.

**A2. What it caps.** Nothing memory- or disk-significant. It caps the length of a snapshot name used as a directory name under `<table dir>/snapshots/<name>` (`Directories.java:636-646`). The quantity compared is `snapshotName.length()` (a count of UTF-16 chars) against 255. The purpose is to avoid a filesystem "File name too long" error, not to bound resource use.

**A3. Mechanism.**
1. `snapshotWithoutMemtable(...)` (`ColumnFamilyStore.java:2137`, convenience overload at 2124) calls `validateSnapshotName(snapshotName)` at line 2144, before any link is made.
2. `validateSnapshotName` (`ColumnFamilyStore.java:2168`) first rejects names containing `File.pathSeparator()` (line 2170; `File.pathSeparator()` is declared at `io/util/File.java:62`) and the names `.` and `..` (line 2175). These two checks always run.
3. Line 2180: if `SNAPSHOT_NAME_VALIDATION` is false (default) it returns, so no length check.
4. The check: [`ColumnFamilyStore.java:2185`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L2185) `if (snapshotName.length() > SchemaConstants.FILENAME_LENGTH)` throws `IllegalArgumentException` (lines 2187-2190). A name of exactly 255 passes; 256 fails.
5. Line 2200 then requires the name to match `[a-zA-Z0-9_.+-]+`, else `IllegalArgumentException`.
6. If the check passes, the method links each SSTable into the snapshot directory (`createLinks`, line 2157, hard links, optionally rate limited) and `createSnapshot` (line 2206) writes the manifest and schema file and registers the snapshot with `StorageService.instance.addSnapshot` (line 2230).
Outcomes: pass leads to the normal snapshot; fail aborts before any directory or link is created. Bypass: with validation off (default) a name longer than 255 is not rejected here; it then fails only if the OS rejects the component (typically NAME_MAX 255 bytes on Linux; bytes versus chars differ for non-ASCII, but the pattern check that would exclude non-ASCII is also off). Other entry points that reach the snapshot path without this method were not traced (not verified).

**A4. Other consumers.** Snapshot disk usage is dominated by the hard-linked SSTable files: they cost no extra space until the live SSTable is compacted away, after which the snapshot pins the old files. This is outside any name-length control. Snapshot rate is shaped by `snapshot_links_per_second` (`Config.java:322`, default 0), which limits link creation speed, not size. TTL snapshots (`ttl` parameter in `snapshotWithoutMemtable`, line 2137) and `clearsnapshot` free it.

**A5. Evidence beyond the source.** Existing unit test `test/unit/org/apache/cassandra/db/SnapshotTest.java` (lines 65 and 126 toggle `SNAPSHOT_NAME_VALIDATION`); I did not read it further. Linux NAME_MAX of 255 bytes: `man 3 pathconf` / `limits.h` (general knowledge, not re-checked here). No issue numbers cited.

## B. Verification solution

**B1. Claim under test.** The snapshot-name length limit (255) does not bound snapshot disk or heap use: the on-disk size of a snapshot and the node's heap are independent of snapshot-name length (at 1, 100 and 255 characters), whereas they do grow with the amount of SSTable data snapshotted. The limit changes only whether a name is accepted.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $WORK/cassandra-5.0.9/`), `cd $WORK/cassandra-5.0.9 && ant jar` (or `ant build-test`). Test source: a new test class `test/unit/org/apache/cassandra/db/SnapshotNameLengthTest.java` in the copy, modelled on `SnapshotTest.java` (uses `CQLTester`/`WithProperties`). Run `ant testsome -Dtest.name=SnapshotNameLengthTest`. JVM options: defaults of the test target, plus `-Xmx1g`. Data and commit log under the test's temporary directories on local disk.

**B2b. Knobs.** (1) Snapshot name length L in {1, 100, 255, 256, 300}; 255 and 256 straddle the limit. (2) `cassandra.snapshot.validation` in {false, true}, set with `WithProperties().set(SNAPSHOT_NAME_VALIDATION, ...)`. (3) Amount of data snapshotted (positive control): N rows in {1k, 100k}. Names are `"a"` repeated L times (matches the allowed pattern).

**B2c. Workload.** Create keyspace/table, insert N rows of 100-byte values, flush so SSTables exist, then call `ColumnFamilyStore.snapshotWithoutMemtable(name)` (public, line 2124) for each L and validation setting. Arithmetic: L=256 with validation true must exceed 255 and throw; L=255 must pass.

**B2d. Observables and instruments.** (a) Whether `IllegalArgumentException` is thrown (test assertion). (b) Disk bytes of the snapshot directory excluding hard-link double counting: sum of sizes of the regular files under `<table dir>/snapshots/<name>` (`Files.walk`), and separately `manifest.json` and `schema.cql` sizes. (c) Heap: `Runtime.totalMemory()-freeMemory()` after `System.gc()` before and after, plus the size of the `TableSnapshot` registered in `StorageService` is not directly measurable (not observed). Heap readings are noisy at this granularity; use a heap histogram (`jcmd <pid> GC.class_histogram`) comparing the string/byte[] count growth only as a coarse check.

**B2e. Procedure.**
1. Build as in B2a.
2. For N in {1k, 100k}: create and populate the table, `forceBlockingFlush`.
3. For validation in {false, true}, for L in the list: call `snapshotWithoutMemtable("a".repeat(L))`, catching exceptions; record thrown/not thrown; if created, record the file-size sums from B2d and heap; then `clearSnapshot(name)`.
4. Repeat each cell three times.

**B2f. Predictions.** Validation false: L=1..300 all accepted at the Java level (an L above NAME_MAX may instead fail in the OS with a filesystem error, not from line 2185). Validation true: L<=255 accepted, L=256 and 300 throw `IllegalArgumentException` from line 2187, with no directory created. Snapshot file bytes (links) and manifest/schema sizes at L=1, 100 and 255 are identical for a given N, because the manifest lists SSTable data file names (`ColumnFamilyStore.java:2213` and `:2248`), not the snapshot name. Snapshot bytes at N=100k are larger than at N=1k.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Accept/reject flips exactly at 255/256 with validation true; no flip with false | Mechanism as traced |
| Snapshot bytes and heap flat across L, rise with N | Claim confirmed (negative estimate): usage does not follow the constraint; positive control moved |
| Snapshot bytes or heap grow with L beyond a few hundred bytes | Claim refuted: usage follows the name length |
| Snapshot bytes flat across L and also flat across N | Control did not move; not confirmed |
| L=256 accepted with validation true | Check does not behave as traced; trace wrong |
| No reject at 256 with validation false and no OS error | Consistent with bypass in A3 |

**B2h. Controls.** Positive control: N varied with L fixed, showing the measurement can see disk growth. Validation false versus true isolates the check from other validation. Fixed ASCII names remove encoding effects. Clear each snapshot between runs so they do not accumulate. Same table, same SSTables for all L.

### B3. Cluster tier

**B3a. Environment and build.** One node (second node optional, not needed), JDK 11, built from the local copy as in B2a (`ant jar`, then run `bin/cassandra -f` from the copy). Data, commitlog, hints and saved caches on local disk of known free size (at least 10 GB free); set `data_file_directories`, `commitlog_directory` in a copied `cassandra.yaml`. Add `-Dcassandra.snapshot.validation=true` to `conf/jvm11-server.options` for the validated runs; heap fixed with `-Xms2G -Xmx2G`.

**B3b. Knobs.** (1) Snapshot-name length L in {1, 100, 255, 256}; (2) `cassandra.snapshot.validation` true (restart needed, since set by `-D`); a second run with false for the bypass check; (3) data volume N in {200k, 2M} rows (positive control).

**B3c. Workload.** `cassandra-stress` (or CQL inserts) to write N rows of about 200 bytes into one table, `nodetool flush`, then `nodetool snapshot -t <name> <keyspace>` for each L, with `nodetool clearsnapshot -t <name>` after each. Arithmetic: 2M rows x about 200 B is about 400 MB of data, large enough that a name-dependent term of at most a few hundred bytes is invisible, while a size effect from N is visible.

**B3d. Observables and instruments.** Disk: `du -s --apparent-size` of `<table dir>/snapshots/<name>` plus `du -s` of the whole data directory (hard links count once with `du` run on the whole data dir; run it on the whole directory, not per path); `nodetool listsnapshots` (True size vs size on disk). Heap and off-heap: `nodetool info` heap line, `jcmd <pid> GC.heap_info`, and RSS from `/proc/<pid>/status`, sampled before and after each snapshot, after a settle of 30 s. Exception text via `nodetool snapshot` stderr. Not observable directly: the exact memory held for the snapshot record.

**B3e. Procedure.**
1. Build, configure, start the node with validation true.
2. Load N=200k rows, flush, record baselines (du, heap, RSS).
3. For L in {1, 100, 255, 256}: `nodetool snapshot -t $(printf 'a%.0s' $(seq $L)) ks`; record exit status, listsnapshots, du, heap, RSS; clearsnapshot.
4. Load to N=2M, flush, repeat step 3 with L=100 and 255 only.
5. Stop the node, restart with validation false, run L=256 once and record outcome.
6. Stop the node.

**B3f. Predictions.** With validation true: L<=255 succeed, L=256 fails with "Snapshot name must not be more than 255 characters" (the text at `ColumnFamilyStore.java:2187`), nothing created on disk. Snapshot size on disk and "true size" in listsnapshots are the same for L=1, 100 and 255 at fixed N (apart from at most a few bytes in directory entries); heap and RSS deltas from a snapshot are within sampling noise for all L. At N=2M the snapshot true size is larger than at N=200k. With validation false, L=256 is accepted by Cassandra and may fail only if the filesystem refuses the name.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Reject at 256 only; sizes and heap flat across L; sizes grow with N | Claim confirmed (negative): the constant limits names, not usage; positive control moved |
| Size or heap deltas grow with L (beyond noise and a few hundred bytes) | Claim refuted |
| Sizes flat across L and also across N | Control did not move or snapshot too small; not confirmed |
| L=256 accepted with validation true | Trace wrong |
| L=256 rejected with validation false at line 2185 text | Property default or gating wrong (A1 wrong) |

**B3h. Controls.** Positive control is N (data volume), showing snapshot size responds to something. Same node, same SSTables for all L (no writes or compaction between runs; disable autocompaction with `nodetool disableautocompaction` to keep hard links stable). Same heap settings. Validation false versus true separates the check from OS limits. Warm up with one snapshot before measuring.

**B4. Risks and cleanup.** Disk: 2M rows is a few hundred MB plus snapshots as hard links; keep data on local disk with known space, never on shared storage. Do not build in the shared tree (work in the copy). Long snapshot-name directories must be removed with `nodetool clearsnapshot` or by deleting the node's data directory at the end. Stop the node and any `cassandra-stress` process; verify with `pgrep -fa 'CassandraDaemon|cassandra-stress'` that none remain. Remove the copy and temporary directories afterwards.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java (lines 2120-2290)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/schema/SchemaConstants.java (lines 70-95)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (grep, line 517)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java (lines 618-645)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java (grep, line 322)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableMetadata.java (grep, line 520)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/File.java (grep, line 62)
- /users/jason92/cassandra-5.0.9/test/unit/org/apache/cassandra/db/SnapshotTest.java (grep only, lines 65 and 126)

## D. Stage-4 feedback

`none yet`
