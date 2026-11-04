<!-- file: cases/max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous.md -->
# MAX_COMPACTING_L0 (LeveledManifest) — verification solution

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/compaction/LeveledManifest.java:306` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-26 |
| Estimate | `negative`. The constant is a trigger threshold on the number of L0 sstables that decides when to run one STCS round in L0. It is not a cap on L0 count, bytes or any heap object. |
| Ground | Crossing 32 only makes `getSTCSInL0CompactionCandidate()` return an STCS candidate (trimmed to `max_threshold` sstables). Nothing blocks flushes or rejects writes when L0 is above 32, and the STCS round can be absent (disabled, no qualifying bucket, or compactor threads busy). L0 file count and bytes therefore grow with the write rate minus compaction throughput, not with 32. The 32 also bounds only the input of one STCS task, not total disk. |

## A. Constraint trace

**A1. The constraint.** `MAX_COMPACTING_L0`; kind: hard-coded constant (`private static final int`), declared at `LeveledManifest.java:62`, value 32 (doc comment at `:58-61`). Unit: number of sstables in L0. No default derivation (literal). Not settable by yaml, `-D` or JMX; changing it needs a source edit and rebuild. Related but separate knobs: `-Dcassandra.disable_stcs_in_l0` (`CassandraRelevantProperties.java:197`, read into `DatabaseDescriptor.java:223`, JMX-settable at runtime via `CompactionManager.setDisableSTCSInL0`, `CompactionManager.java:2353-2357`) and the table option `max_threshold` (default 32, `CompactionParams.java:80`), which is read through `cfs.getMaximumCompactionThreshold()` (`ColumnFamilyStore.java:3086`).

**A2. What it caps.** Nominally the number of L0 sstables allowed before STCS-in-L0 kicks in (resource: disk and file descriptors, indirectly read-path memory such as per-sstable bloom filters/index summaries, which are off-heap/heap per sstable). The quantity compared is `generations.get(0).size()` (`LeveledManifest.java:306`), the count of L0 sstables.

**A3. Mechanism.**
1. `LeveledCompactionStrategy.getNextBackgroundTask` calls `manifest.getCompactionCandidates()` (`LeveledCompactionStrategy.java:137`).
2. `getCompactionCandidates` (`LeveledManifest.java:199`) first calls `getSTCSInL0CompactionCandidate()` (`:243`), with the comments at `:225-241` stating the design: L0 is not blocked, "we don't have that luxury", instead STCS reduces read overhead when L0 falls behind.
3. At `:306` the check is `!getDisableSTCSInL0() && generations.get(0).size() > 32`. If false, returns null (`:316`).
4. If true, `getSSTablesForSTCS` (`:319-329`) takes the uncompacting L0 sstables, buckets them by size (`SizeTieredCompactionStrategy.getBuckets`), and returns `mostInterestingBucket(buckets, min_threshold, max_threshold)`. That bucket is trimmed to `max_threshold` (default 32). It may be empty (`:309`), in which case null is returned.
5. A non-null result is `new CompactionCandidate(mostInteresting, 0, Long.MAX_VALUE)` (`:312`): output stays in L0 and the max sstable size is unlimited, so STCS output in L0 can exceed `sstable_size_in_mb`.
6. Back in `getCompactionCandidates`: higher levels over their size score (> 1.001, `:256`) are served first, and the L0 STCS candidate is returned ahead of them (`:269-271`). Otherwise, if normal L0->L1 candidates are empty, the STCS candidate is returned (`:293-299`).
Outcomes at the limit: count <= 32: no STCS, normal L0->L1 compaction only. Count > 32: one STCS task of up to `max_threshold` sstables is offered, nothing else changes. Bypass/overshoot: flush into L0 is unconditional, so count goes arbitrarily above 32; compaction runs only when a compactor thread is free (`concurrent_compactors`); with `disable_stcs_in_l0=true` the check never fires; an equal-sized-bucket requirement can leave no candidate; STCS output (unbounded size) is itself a large sstable and temporarily doubles disk for its inputs. A second use of the same decision, `getEstimatedTasks` (`:655`), uses `max_threshold`, not `MAX_COMPACTING_L0`, and only affects the reported pending-task estimate.

**A4. Other consumers.** Disk is also used by memtable flushes, commit log, higher-level sstables, compaction temporary outputs (space for in-flight compaction), snapshots, hints; heap by memtables, bloom filters, index summaries; none are governed by this constant. L0 sstables from streaming/repair/bulk load also arrive without this check.

**A5. Evidence beyond the source.** Doc `doc/modules/cassandra/pages/managing/operating/compaction/lcs.adoc:95` (STCS-in-L0 and the `disable_stcs_in_l0` option). Existing test `test/unit/org/apache/cassandra/db/compaction/LeveledCompactionStrategyTest.java:558` (`testDisableSTCSInL0`). Upstream background: CASSANDRA-5371 (STCS in L0, from memory, not re-checked online).

## B. Verification solution

**B1. Claim under test.** The number and total bytes of L0 sstables are not bounded by `MAX_COMPACTING_L0 = 32`: when flush rate exceeds compaction rate, L0 count rises well above 32 (and the only effect of 32 is to trigger STCS compactions of at most `max_threshold` sstables). Falsified if L0 count never exceeds roughly 32 (plus in-flight flushes) however far compaction is throttled.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a ~/cassandra-5.0.9/ /local/c509/`), `cd /local/c509 && ant jar` then run via `ant testsome -Dtest.name=org.apache.cassandra.db.compaction.LeveledCompactionStrategyTest -Dtest.methods=<new method>`. Add the new test method to a copy of that class (package `org.apache.cassandra.db.compaction`, because `LeveledManifest` is package-private), modelled on `testDisableSTCSInL0` (`:558`) and the `lm.getCompactionCandidates()` use at `:907`. Default test JVM options. **[Amended 2026-10-26 (A2, stage-4 audit):** the tree is made by `copy-source.sh` (not `rsync`), the test class is a new file `LeveledManifestL0Test.java` in package `org.apache.cassandra.db.compaction`, run with `ant testsome -Dtest.name=...LeveledManifestL0Test`; `getCompactionCandidates()` is reached through `lcs.manifest` (package-private) and a drain/execute step through `lcs.getNextBackgroundTask(0)`.**]**

**B2b. Knobs.** Number of L0 sstables N in {31, 32, 33, 64, 200}; `DatabaseDescriptor.setDisableSTCSInL0(false|true)`; table `max_threshold` in {32, 8}; all via test code on the CFS (`cfs.setCompactionParameters` / schema with `compaction = {'class':'LeveledCompactionStrategy','max_threshold':...}`). N spans below, at, and above the constant. **[Amended 2026-10-26 (A2):** `max_threshold` is a table option, so two tables are created (`mt32`, `mt8`) with `sstable_size_in_mb=1`, `fanout_size=10`; the flag is `DatabaseDescriptor.setDisableSTCSInL0` and is restored to false after each arm. N is the TOTAL number of L0 sstables including any held one.**]**

**B2c. Workload.** Create N small L0 sstables of similar size (e.g. insert 100 rows of 100 bytes, `Util.flush(cfs)` per sstable, so all land in one STCS bucket). Do not run compaction between flushes (`cfs.disableAutoCompaction()`), then call `getCompactionCandidates()` repeatedly without executing tasks. Arithmetic: 33 sstables > 32 reaches the branch; 64 reaches the branch twice over. **[Amended 2026-10-26 (A1/A2), see the routes in B2f:** three routes are built per N. R0: only the N L0 sstables. R1: additionally 30 non-overlapping sstables of about 1 MiB set to level 1 with `mutateLevelAndReload(1)`, so L1 holds about 3x `maxBytesForLevel(1,10,1 MiB)` = 10 MiB. R2: one of the N L0 sstables is held as compacting (`cfs.getTracker().tryModify(singleton(sstable), OperationType.COMPACTION)`, released by `abort()` after the arm). L0 sstables all overlap each other (same key range, unique keys, random values); L1 sstables use a disjoint key prefix.**]**

**B2d. Observables and instruments.** Operand: `manifest.getLevelSize(0)` (L0 count) and the returned `CompactionCandidate.sstables.size()`, `.level`, `.maxSSTableSize`. Measured in test assertions/prints. Not directly observable: real disk/heap, which is the cluster tier's job.

**B2e. Procedure.** 1) Build. 2) For each (N, disable flag, max_threshold): reset table, create N sstables, `getCompactionCandidates()`, record candidate size and L0 count. 3) Then execute the returned candidate only in a separate step and observe the L0 count afterwards. 4) Positive control (below). **[Amended 2026-10-26 (A2):** step 2 runs for each route, N, flag and table; the "execute" step 3 uses `lcs.getNextBackgroundTask(0)` then `task.execute(ActiveCompactionsTracker.NOOP)` and is run on a fresh arm, not on the arm that was read.**]**

**B2f. Predictions.** *[Amended 2026-10-26 (A1, stage-4 audit, before any reading): the original text said an STCS candidate is returned whenever N is above 32. The source says otherwise: `getSTCSInL0CompactionCandidate()` (`LeveledManifest.java:304-317`) only builds the candidate; `getCompactionCandidates()` returns it only (a) at `:270-271`, when a level 1 to 7 has score above 1.001, or (b) at `:296-299`, when `getCandidatesFor(0)` is empty. With nothing else pending, `getCandidatesFor(0)` (`:495-573`) is non-empty and the normal L0 candidate wins. Original B2f quoted in section D.]* An STCS candidate is the one with `level == 0` and `maxSSTableSize == Long.MAX_VALUE` (`:312`); a normal candidate carries `maxSSTableSize == sstable_size_in_mb` in bytes (`:301`). N is the total L0 count, flag false, `max_threshold` 32 unless stated.

- **R0 (only L0 sstables, nothing held, L1 empty):** at every N in {31, 32, 33, 64, 200} a normal candidate (never STCS): `maxSSTableSize == 1 MiB`, at most 32 sstables; the L0 count is N and unchanged by the read.
- **R1 (L1 at about 3x target, nothing held):** N in {31, 32}: a normal L1 to L2 candidate (`level == 2`, every sstable level 1). N in {33, 64, 200}: an STCS candidate with exactly 32 sstables (8 when `max_threshold` is 8), all level 0. After executing it once (fresh arm) the L0 count is N - 31 (N - 7 with `max_threshold` 8). With the flag true: the L1 to L2 candidate at every N.
- **R2 (one L0 sstable held as compacting, L1 empty):** N = 31 and 32: `null`. N in {33, 64, 200}: an STCS candidate of 32 sstables (8 with `max_threshold` 8), none of them the held one. With the flag true: `null` at every N.
- **Never refused:** 200 flushes with auto compaction disabled leave exactly 200 L0 sstables and throw nothing (no rejection, no eviction).
- **Positive control (R1, flag true, N = 32):** executing the L1 to L2 candidate repeatedly brings L1 bytes to at most 1.001 x `maxBytesForLevel(1,10,1 MiB)`.

**B2g. Readings.** *[Amended 2026-10-26 (A1): rows made route-aware; original quoted in section D.]*

| Observation | Meaning |
|---|---|
| R1 and R2 match B2f (boundary exactly between N=32 and N=33, candidate size `max_threshold`), R0 never returns an STCS candidate, flag true removes it, 200 L0 sstables exist with no rejection, and the positive control brings L1 to target | **Confirmed**: 32 only selects an STCS task of at most `max_threshold` sstables; it does not cap the L0 count; a real cap binds at L1+ |
| L0 count falls to 32 or below without executing any task, or a flush or write is refused or throws above 32 | **Refuted**: something caps L0 |
| An STCS candidate at N <= 32 (flag false) on R1 or R2, or at any N on R0 | **Not confirmed**: the constant or the routes are not as traced; record which |
| No STCS candidate at N >= 33 on R1 or R2 with the flag false | **Not confirmed**: the bucket or trim rule hides the trigger; record why |
| An STCS candidate with the flag true | **Not confirmed**: the flag does not gate the check as traced |
| Candidate size does not follow `max_threshold` (8 vs 32) | **Not confirmed**: the bound is not the table option as traced |
| Positive control: no candidate at L1 3x over target, or L1 does not return to target | **Not confirmed** (control did not move); the file cannot reach Confirmed |
| Limit never reached (fewer than 33 L0 sstables built) or any other combination | **Not confirmed (no matching row)** |

**B2h. Controls.** Flag true vs false at same N; N just below/above 32; max_threshold varied; positive control at higher level: put L1 bytes at 3x `maxBytesForLevel(1, size)` (`LeveledManifest.java:185-190`) and check score > 1.001 branch (`:256`) returns a candidate whose execution drives the level down. **[Amended 2026-10-26 (A1): the positive control is route R1 with the flag true at N=32: the L1 to L2 candidate is executed repeatedly (cap 200 tasks) and L1 bytes after the last task must be at most 1.001 x `maxBytesForLevel(1,10,1 MiB)`; a truncate control brings all level bytes to 0.**]**

### B3. Cluster tier

**B3a. Environment and build.** One node suffices (optionally 2). JDK 11, local copy of tag built with `ant jar`; `cassandra.yaml` with `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` on a local disk of known size (>= 50 GB free; use a dedicated directory, not shared storage). `-Xms/-Xmx 4G`. Keep `concurrent_compactors: 1`. `memtable_flush_writers: 2`. **[Amended 2026-10-26 (A3, stage-4 audit):** `ant build-test` tree from `copy-source.sh`; node on `127.0.4.1` (port slot 4: JMX 7140, native 9042, storage 7000 on that address only); data, commit log, hints and saved caches on a dedicated 12 GiB tmpfs at `/mnt/s4lz` (never `/proj`); `MAX_HEAP_SIZE=2G`, `HEAP_NEWSIZE=400M` (4G of B3a is not needed: no memory claim); `concurrent_compactors: 1` for A, B and C and 4 for D; `memtable_flush_writers: 2`; `auto_snapshot: false`.**]**

**B3b. Knobs.** (1) compaction throughput: `nodetool setcompactionthroughput 1` (throttled) vs `0` (unthrottled) vs `disableautocompaction` on the table; (2) `-Dcassandra.disable_stcs_in_l0=true|false`, or JMX `setDisableSTCSInL0`; (3) table `max_threshold` 32 vs 4. Reason: starve compaction to make flush outrun it, then see whether 32 holds L0. **[Amended 2026-10-26 (A3):** the flag is set at start with `-Dcassandra.disable_stcs_in_l0=true` (run C); throttle is `compaction_throughput` in the yaml plus `nodetool setcompactionthroughput`; `max_threshold` 4 is not run (the unit tier covers that control, B2b).**]**

**B3c. Workload.** *[Amended 2026-10-26 (A4, stage-4 audit, runbook arithmetic only; B3f and B3g keep their claims). The original asked for `n=20000000` (20 GB) with a `nodetool flush` every 5 s and "300 flushes x 10 MB = 3 GB", a table `ks.t` that `cassandra-stress write` cannot fill, and a 5 GB cap in B4: the numbers contradict each other and a flush every 5 s at stress speed makes sstables of hundreds of MB.]* Keyspace `ks`, table `ks.standard1` (`key blob PRIMARY KEY, "C0".."C4" blob`, compression off, `compaction = {'class':'LeveledCompactionStrategy','sstable_size_in_mb':'10','fanout_size':'10'}`), the schema `cassandra-stress` expects. Write `n = 1,500,000` rows of one 1,000-byte column (`-col size=FIXED(1000) n=FIXED(1)`, `-pop seq=1..1500000`, `-rate threads=64 throttle=5000/s`), about 1.56 GB at 5 MB/s in 300 s, while a loop runs `nodetool flush ks standard1` every 2 s: about 150 flushes of about 10 MB, so at least 100 L0 sstables are made when nothing compacts. Duration of the write phase: about 5 minutes per run.

**B3d. Observables and instruments.** *[Amended 2026-10-26 (A3/A5).]* L0 count: the "SSTables in each level: [x, y, ...]" line of `nodetool tablestats ks.standard1` every 20 s (a level over its nominal size is printed `count/limit`, e.g. `150/4`: take the number before the slash), plus the end-of-phase snapshot; per-level bytes from "SSTable bytes in each level"; actual disk: bytes of the files in the table directory every 5 s (`os.listdir`/`getsize`, including a `-Data.db` count) and "Space used (live)"; `nodetool compactionstats` and `nodetool tpstats` (CompactionExecutor active+pending); file descriptors (`/proc/<pid>/fd`) and `RssAnon` (`/proc/<pid>/status`) every 5 s; `df` of the tmpfs. Debug log: `nodetool setlogginglevel org.apache.cassandra.db.compaction.LeveledManifest DEBUG` right after start; the line "L0 is too far behind, performing size-tiering there first" in `debug.log` is written every time `getSTCSInL0CompactionCandidate()` returns a candidate, so it shows that the check was TRUE (count above 32 and a qualifying bucket), not that the candidate was chosen (`:304-317`). Not observable: the candidate itself (unit tier).

**B3e. Procedure.** *[Amended 2026-10-26 (A3/A4).]* For each label: (1) mount the tmpfs, start the node with the label's settings, create the schema, set the debug level; (2) start the sampler, the flush loop and the stress write; (3) at the end of the write take the "lag-end" snapshot; (4) for A, C and D drain: `setcompactionthroughput 0` and `setconcurrentcompactors 4`, wait until three reads 20 s apart show no active or queued CompactionExecutor task and identical file bytes (cap 25 minutes), then take the "settled" snapshot with per-level bytes (the L1+ positive control); for B skip the drain; (5) `TRUNCATE ks.standard1` and take the "truncated" snapshot (instrument control: file bytes about 0); (6) stop the node by PID, check that no daemon is left, unmount nothing until the last label. Labels: **A** throttle 1 MiB/s, 1 compactor, flag false. **B** `nodetool disableautocompaction ks standard1` before the write, flag false. **C** as A with `-Dcassandra.disable_stcs_in_l0=true`. **D** throttle 0 and 4 compactors from the start (positive control), flag false.

**B3f. Predictions.** *[Amended 2026-10-26 (A5, stage-4 audit, before any reading): numbers made explicit and the meaning of the log line corrected (it marks the check being TRUE, not the candidate being chosen; with one compactor the candidate is chosen only on the routes of B2f). Original quoted in section D.]* "Peak L0" is the largest L0 count in the 20-s tablestats samples and the lag-end snapshot.
- **A:** peak L0 at least 100 (3x the constant); file bytes and "Space used (live)" within 15% of the bytes written at lag-end; at least one "L0 is too far behind" debug line, the first not before the L0 count first exceeds 32; no write error.
- **B (no compaction):** L0 count equals the number of flushes (at least 100) at lag-end, file bytes within 15% of the bytes written, no debug line (`getCompactionCandidates()` is never called with auto compaction off).
- **C (flag true):** peak L0 at least 100 and the same disk relation as A, and zero debug lines.
- **D (positive control):** peak L0 below half of A's peak; after the drain L0 is at most 4 sstables.
- **After the drain (A, C, D):** every level from 1 to below the top level holds at most 1.05 x its nominal size (`maxBytesForLevel`: L1 100 MiB, L2 1 GiB), and total live bytes are within 5% of the lag-end value.
- **Instrument control:** after `TRUNCATE` the file bytes are below 1% of the settled bytes.

**B3g. Readings.** *[Amended 2026-10-26 (A5): rows made checkable; original quoted in section D.]*

| Observation | Meaning |
|---|---|
| A, B and C peak L0 at least 100 (above 3x the constant), disk tracks the bytes written, at least one debug line in A and none in C, D peak L0 below half of A's, and the L1+ levels settle at or below 1.05 x nominal in A, C and D | **Confirmed**: the constant does not cap L0; a cap binds at L1+ and compaction speed moves L0 |
| L0 count stays at 40 or below in B (no compaction), or a write is refused | **Refuted**: something else caps L0 (investigate) |
| A and B peak L0 never above 32 | **Not confirmed**: limit never reached |
| L0 above 100 in A, B and C but no debug line in A (the true branch was not observed) | **Not confirmed**: the branch evidence is missing; record why |
| A debug line in C (flag true) | **Not confirmed**: the flag does not gate the check as traced |
| D peak L0 not below half of A's, or the L1+ levels do not settle at their nominal size after the drain, or the truncate control fails | **Not confirmed** (control did not move or instrument failed); the file cannot reach Confirmed |
| Any other combination | **Not confirmed (no matching row)** |

**B3h. Controls.** Flag on/off; compaction disabled vs throttled vs unthrottled; same data volume per run; page cache and other processes unchanged; `max_threshold` 4 to show the STCS task size follows the table option.

**B4. Risks and cleanup.** Disk: cap at ~5 GB written per run, monitor `df` on the local volume, abort if > 70% used. Do not use shared storage; commit log and hints on local disk. Stop `cassandra-stress` and the node (`nodetool drain; kill <pid>`), verify with `ps -ef | grep -i cassandra` and `jps`, delete the data/commitlog/hints dirs and the source copy when finished. Unit tier writes only under the test data dirs of the local copy.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/compaction/LeveledManifest.java (lines 55-90, 180-330, 640-665)
- src/java/org/apache/cassandra/db/compaction/SizeTieredCompactionStrategy.java (mostInterestingBucket)
- src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java (105-150)
- src/java/org/apache/cassandra/db/compaction/CompactionManager.java (2347-2357)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java, CassandraRelevantProperties.java (grep hits)
- src/java/org/apache/cassandra/schema/CompactionParams.java (grep hits)
- test/unit/org/apache/cassandra/db/compaction/LeveledCompactionStrategyTest.java (grep hits)
- doc/modules/cassandra/pages/managing/operating/compaction/lcs.adoc (grep hit)

## D. Stage-4 feedback

**Stage-4 audit amendments, 2026-10-26 (stage-4 agent, before any reading).** Status: audited, no run yet. Results: `stage4-runtime-verification/results/max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous.md`.

- **A1 (B2f, B2g, B2h; changes the prediction, reason independent of any reading).** The original B2f predicted an STCS candidate whenever N is above 32. In the source `getSTCSInL0CompactionCandidate()` only builds the candidate; `getCompactionCandidates()` returns it at `LeveledManifest.java:270-271` (a level 1 to 7 over score 1.001) or at `:296-299` (`getCandidatesFor(0)`, `:495-573`, empty). With only L0 sstables the normal L0 candidate (`maxSSTableSize` = sstable size) is returned. B2f and B2g now have three routes (R0 nothing else, R1 L1 over target, R2 one L0 sstable held as compacting) and an exact boundary at N = 32 / 33.
- **A2 (B2a, B2b, B2c, B2e).** `copy-source.sh` tree, new test class, two tables for `max_threshold`, route construction, execute step on a fresh arm.
- **A3 (B3a, B3b, B3d, B3e).** Node on loopback slot 4 (`127.0.4.1`), 12 GiB tmpfs, heap 2G, flag by `-D`, run labels A to D, drain and truncate steps, L0 count parsed from `tablestats` with the `count/limit` form handled.
- **A4 (B3c).** The workload arithmetic of the original contradicted itself (20 GB with `n=20000000`, 3 GB for 300 flushes, a 5 GB cap, a `ks.t` table stress cannot write, flush every 5 s). Now `ks.standard1`, 1.5 M rows, throttle 5000 rows/s, flush every 2 s, about 150 sstables, about 1.56 GB per run.
- **A5 (B3f, B3g).** Numbers and operational definitions ("peak L0", "low", "settles"); the debug line "L0 is too far behind" marks the check being true, not the candidate being chosen (the original B3d said "marks STCS firing"); the row "In run B, usage flat while control (D) moves" was not a checkable observation and is removed.
- **Left for stage 3 (not applied):** a dose-response on the constant itself (a build with `MAX_COMPACTING_L0` set to 8 and 128 would vary the knob; the file is right that it is a literal, and this design answers the same question with two arms that differ in one condition); the A3 phrase "STCS candidate is returned ahead of them" should say it is returned only when some level 1 to 7 is over score; the `getEstimatedTasks` note (`:655`) is correct.

Original text of the amended sections, as filed 2026-10-26 before the audit (kept for the record):

<details><summary>Original B2f and B2g</summary>

**B2f. Predictions.** N=31, 32: candidate is a normal L0->L1 candidate or null, never an STCS (level 0 / `Long.MAX_VALUE`) candidate. N=33, 64, 200 with max_threshold=32: STCS candidate of exactly 32 sstables, level 0, `Long.MAX_VALUE`; the L0 count (N) is unchanged until executed, and after one task the count is N-31 (32 in, 1 out). max_threshold=8: candidate size 8. disable flag true: no STCS candidate at any N. No setting makes the manifest refuse the Nth sstable.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| L0 count reaches 200 with no rejection/eviction, candidate size is `max_threshold` (not 32 by constant) | claim confirmed: 32 only triggers a task; count not capped |
| STCS candidate at N<=32 | the constant is not 32 / trace wrong; claim in doubt |
| No STCS candidate at N>=33 with flag false | bucket/trim rule hides the trigger; record why; not confirmed |
| Candidate size tracks `max_threshold`, not 32, when max_threshold=8 | confirms the bound is the table option, not the constant |
| Positive control (L1 over `maxBytesForLevel`) yields a level-1 candidate that, once executed repeatedly, returns L1 to <= 10*sstable size | confirms a real cap binds at L1+, unlike L0 |
| L0 count falls to <=32 on its own without executing tasks | claim refuted |
| Limit never reached or control does not move | not confirmed |


</details>

<details><summary>Original B3c</summary>

**B3c. Workload.** `CREATE KEYSPACE ks WITH replication={'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.t(k bigint, c int, v blob, PRIMARY KEY(k,c)) WITH compaction={'class':'LeveledCompactionStrategy','sstable_size_in_mb':'10'};` Drive with `cassandra-stress` (`write n=20000000 no-warmup -col size=FIXED(1000) -rate threads=64`), forcing a flush every ~5 s through `nodetool flush ks t` in a loop (or a small `memtable_heap_space`) so that at least 300 L0 sstables are created: 300 flushes x ~10 MB = ~3 GB, within the disk budget. Duration: about 20-30 minutes.

</details>

<details><summary>Original B3f and B3g</summary>

**B3f. Predictions.** Run A: L0 count rises above 32 (expected 100+; will exceed 32 several times over), disk grows ~linearly with bytes written; STCS log lines appear once count > 32; STCS consumes the throttled budget so count may still keep growing. Run B: L0 count equals the number of flushes (300+), disk ~ bytes written, no cap. Run C: same as B/A without STCS lines. Run D: L0 count stays low (single digits to tens) because compaction keeps up, not because of 32. Higher levels (L1/L2) settle at or below their level limits within about 1.001x after catching up.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| L0 count > 32 sustained in A and unbounded growth in B, disk tracks writes | claim confirmed: constant does not cap L0 |
| L0 count stays <= ~32-40 in B (no compaction) | claim refuted: something else caps it (investigate) |
| STCS log lines in A only when count > 32, none in C | trigger works as traced; still not a cap |
| Run D shows L0 low and L1/L2 near their `maxBytesForLevel` | positive control: caps bind at L1+ and in fast compaction, not via the constant |
| In run B, usage flat while control (D) moves | consistent with confirmed |
| L0 never exceeded 32 in A and B, or D does not show L1/L2 settling | not confirmed (limit not reached or control did not move) |


</details>

**Stage-4 feedback (2026-10-26):** run 1, no run 2. Unit **Confirmed** — does not cap; cluster **Confirmed** — does not cap; outcome class true negative. Results: `stage4-runtime-verification/results/max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous.md`. Readings: L0 reached 211 sstables (6.5x the constant) with compaction throttled to 1 MiB/s, with it off, and with `disable_stcs_in_l0=true` (209); 7 "L0 is too far behind" debug lines with the flag false, 0 with it true; unthrottled compaction kept L0 at 2; levels settle at or below nominal after the drain. Unit: the STCS candidate is returned exactly from 33 L0 sstables, with `max_threshold` members, and only on the routes of amendment A1 (a level 1-7 over score 1.001, or an empty normal L0 candidate). No section of this file is refuted; the original B2f/B3f wording was amended before any reading (A1, A5).
