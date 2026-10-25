# sstable_size_in_mb (LCS) — verification solution  <!-- file: cases/sstable-size-in-mb-getCandidatesFor-maxSSTableSizeInBytes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/compaction/LeveledManifest.java:557` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI (version not recorded), 2026-10-24 |
| Estimate | `negative`. The entry line only compares the summed on-disk size of the chosen L0 candidates with `sstable_size_in_mb` to decide whether to pull in overlapping L1 sstables. It is a scheduling heuristic, not a limit on disk or memory. |
| Ground | The operand `maxSSTableSizeInBytes` (a) is a threshold for choosing compaction inputs and never rejects, blocks or deletes data. (b) Level "max bytes" (`maxBytesForLevel`, :185) only raises a compaction score (:255-258), so a level can sit above it while compactions are blocked, lag or are disabled. L0 has no byte cap at all. (c) Even where the value does bound something (the output sstable file size, `MaxSSTableSizeWriter.java:78`), it is checked only after a partition is written, so a file can exceed it by one partition. The total disk used by the table is not bounded by it. |

## A. Constraint trace

**A1. The constraint.**
- Name: LCS table option `sstable_size_in_mb`. The target operand `LeveledManifest.maxSSTableSizeInBytes` is its byte form.
- Kind: per-table schema option, in the `compaction = {...}` map of CREATE/ALTER TABLE. It is not a yaml key or a `-D` property.
- First declared: `LeveledCompactionStrategy.java:52` (`SSTABLE_SIZE_OPTION = "sstable_size_in_mb"`). The field `LeveledManifest.maxSSTableSizeInBytes` is declared at `LeveledManifest.java:76` and assigned at `:84` (`maxSSTableSizeInMB * 1024L * 1024L`).
- Unit: MiB in the option, bytes in the manifest.
- Default: 160 MiB, a hardcoded literal at `LeveledCompactionStrategy.java:67`, overridden by `Integer.parseInt` at `:75`.
  - Validation (`:576-588`) requires an integer ≥ 1. The fallback of "1" at `:576` is used only for validation when the option is absent.
  - `:610-616` rejects values where `fanout^(MAX_LEVEL_COUNT-1) * size` overflows a long. `MAX_LEVEL_COUNT` is 9 (`LeveledGenerations.java:57`).
  - Warnings at `:78-83` for sizes ≥ 1000 or < 50, suppressed by the JVM property `cassandra.tolerate_sstable_size` (`CassandraRelevantProperties.java:604`).
- How set: `ALTER TABLE ks.t WITH compaction = {'class':'LeveledCompactionStrategy','sstable_size_in_mb':'N'}`. A schema change rebuilds the strategy and a new `LeveledManifest` (`LeveledCompactionStrategy.java:101`). No node restart is needed.
- Related constants used in the same decision:
  - `MAX_COMPACTING_L0 = 32` (`LeveledManifest.java:62`)
  - `max_threshold`, default 32 (`CompactionParams.java:80`), read through `cfs.getMaximumCompactionThreshold()` (`ColumnFamilyStore.java:3086`)
  - `fanout_size`, default 10 (`LeveledCompactionStrategy.java:56`)

**A2. What it caps.** Nominally disk: the target size of one sstable file, and through `maxBytesForLevel` the target size of each level. At the entry line, the compared quantity is `SSTableReader.getTotalBytes(candidates)` (`SSTableReader.java:541-547`), the sum of `onDiskLength()` over the L0 candidate set. It is compared with `maxSSTableSizeInBytes` at `LeveledManifest.java:557`. It is on-disk (compressed) bytes, not heap.

**A3. Mechanism.**
1. `getCompactionCandidates` (`LeveledManifest.java:~215-302`) first asks for an STCS-in-L0 candidate (`:243`, `:304-317`, only when L0 has more than 32 sstables). It then walks levels from the top down. A level whose score `remainingBytes / maxBytesForLevel(i)` exceeds 1.001 (`:253-258`) is compacted through `getCandidatesFor(i)` (`:274`). Otherwise L0 is handled by `getCandidatesFor(0)` (`:293`).
2. `maxBytesForLevel` (`:185-193`) is `4 * size` for L0 (`:188`) and `fanout^level * size` above that. It throws only on long overflow.
3. In `getCandidatesFor(0)` (`:502-573`), L0 sstables are taken oldest first together with their overlapping L0 sstables. The count is cut to `max_threshold` oldest when it goes above it (`:548-553`).
4. Entry line `:557`:
   - Candidates total > `maxSSTableSizeInBytes`: L1 sstables overlapping the candidates are added (`:562`, `:567`). If any of them is already compacting (`:563`), or the candidates overlap sstables already compacting in L0 (`:565`), the method returns an empty list and no compaction is scheduled. The comment at `:561` ("TODO try to find a set...") acknowledges this.
   - Candidates total ≤ the value: L1 is skipped. If at least 2 candidates remain (`:569`) they are compacted within L0. `getNextLevel` (`:667`) returns 0 for an all-L0 input smaller than the size (`:678`), so the output stays in L0.
5. The output file size is controlled by `LeveledCompactionTask.getCompactionAwareWriter` (`LeveledCompactionTask.java:46-54`). It passes the same value as `maxSSTableBytes` into `MaxSSTableSizeWriter`. The writer starts a new file when `getEstimatedOnDiskBytesWritten() > maxSSTableSize` (`MaxSSTableSizeWriter.java:78`). The check runs per key, so a file overshoots by up to one partition, and a single partition larger than the size produces a single larger file.
6. The scheduling path for the L0→L1 compaction returns `new CompactionCandidate(candidates, nextLevel, maxSSTableSizeInBytes)` (`:301`).

Bypasses and overshoots:
- STCS-in-L0 candidates use `Long.MAX_VALUE` as the output limit (`:312`), so the size is ignored for them.
- Candidate input can reach roughly 32 sstables × any size, plus the overlapping L1 sstables. Nothing bounds the L0 input bytes.
- Levels can exceed their `maxBytesForLevel`, and nothing blocks writes. The top level only logs a warning (`:262-266`).
- A compaction that cannot run for lack of disk space is reduced in scope by `LeveledCompactionTask.reduceScopeForLimitedSpace` (`:68-`). That is a different limit, a free-space check.

**A4. Other consumers.** Memtable flushes write new L0 sstables with no size cap beyond the memtable size. Commit log, hints, snapshots and backups, other tables and keyspaces, and concurrent compactions all use the same disk. Compaction temp files exist while an old and new sstable coexist, so space usage temporarily doubles for the inputs. Bloom filters, index summaries and the key cache are on-heap or off-heap objects that scale with sstable count and are unrelated to this option.

**A5. Evidence beyond the source.** Code comments in the tree (`LeveledManifest.java:225-240`, `:516-528`); `LeveledCompactionStrategy.java:82` refers to CASSANDRA-5727 (performance testing of the 160 MB default). Existing unit tests: `test/unit/org/apache/cassandra/db/compaction/LeveledCompactionStrategyTest.java`. No external pages were fetched.

## B. Verification solution

**B1. Claim under test.** Total disk usage of an LCS table does not follow `sstable_size_in_mb`. The option sets only (i) a threshold for whether L0 candidates drag in L1 overlaps and (ii) the approximate size of output files, so (a) with compaction held back, L0 bytes grow without limit regardless of the value, and (b) the live data set size is the same at different values, while the sstable file size and count differ.

### B2. Unit tier

**B2a. Environment and build.** Copy the tree to local disk (`rsync -a /path/cassandra-5.0.9/ /local/c509/`). JDK 11, Ant. In `/local/c509`: `ant build-test` (or `ant jar`) once. Put a new test class, `LcsL0ThresholdProbeTest`, beside `LeveledCompactionStrategyTest` in the copy, using its setup (schema, `cfs`, helper that writes sstables, `LeveledCompactionStrategy` constructor with an options map). Run with `ant testsome -Dtest.name=org.apache.cassandra.db.compaction.LcsL0ThresholdProbeTest`. JVM defaults from `build.xml` are fine. Use a local-disk `-Dcassandra.storagedir`.

**B2b. Knobs.** `sstable_size_in_mb` ∈ {1, 5, 160}. 1 and 5 are small so the threshold can be crossed with a few sstables, and 160 is the default. For the L1 overlap branch, set the key range of the L1 sstables to overlap L0. Hold `max_threshold` at 32 and `fanout_size` at 10. Set via the options map on `LeveledCompactionStrategy` (or `ALTER TABLE` in the test via `SchemaLoader`).

**B2c. Workload.** The test creates L0 sstables of known on-disk size, S ≈ 0.4 × the configured size each. For example, with size 5 MiB it creates 6 overlapping L0 sstables of about 2 MiB each (12 MiB total > 5 MiB) and with 160 MiB it creates the same 6 (12 MiB < 160 MiB). Also add one L1 sstable overlapping the L0 range. The arithmetic: the sum of candidate `onDiskLength()` crosses 5 MiB at the third sstable, never crosses 160 MiB. A second phase adds sstables to L0 (up to 200) without ever running compaction tasks, to measure total L0 bytes.

**B2d. Observables and instruments.**
- `SSTableReader.getTotalBytes` of the candidates returned by `strategy.getNextBackgroundTask`/`manifest.getCompactionCandidates()`. It is package-private, so put the test in the same package.
- Whether the L1 sstable is in the candidate set.
- Sum of `onDiskLength()` of all L0 sstables (phase 2).
- Not observable here: real heap or disk of a node.

**B2e. Procedure.**
1. Build as in B2a.
2. For each size in {1, 5, 160}, create the strategy and write the L0 sstables (and the L1 sstable).
3. Record the candidate set, its byte total, and whether L1 sstables are included. Do not execute the task.
4. Execute the task for size 5 and record the output file sizes (via `MaxSSTableSizeWriter` through `LeveledCompactionTask`). Include one case with a single partition larger than the size (e.g. 12 MiB at size 5).
5. Phase 2: for size 1 and 160, add 200 L0 sstables of ~1 MiB with the compaction strategy disabled (`cfs.disableAutoCompaction()`), and record L0 total bytes.
6. Clean up the data directory.

**B2f. Predictions (before any run).**
- Size 1 and 5: candidate total (≥ 12 MiB or ≥ 5 MiB) > size, so the candidate set includes the overlapping L1 sstable.
- Size 160: the total is < 160 MiB, so no L1 sstable is added and the output stays in L0.
- Output files at size 5: every file is ≈ 5 MiB, plus up to one partition. The oversized single partition gives one file larger than 5 MiB.
- Phase 2: L0 total ≈ 200 MiB for both sizes. It does not depend on the option.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| L1 inclusion flips exactly where candidate total crosses the size | The mechanism works as traced (a threshold, nothing more). |
| Phase 2 L0 total is the same at size 1 and 160 and grows with the number of sstables written | Usage does not follow the knob. Claim confirmed. |
| Phase 2 L0 total is held to a function of the size (e.g. 4 × size) | Claim refuted: the option caps L0. |
| Output file size follows the size (±1 partition) while total bytes are unchanged | Positive control moved. The knob binds file size, not total usage. |
| Output files do not follow the size, or candidate set does not flip | The control did not move. Result not confirmed; check the setup. |

**B2h. Controls.** The output-file-size row is the positive control (a cap known to bind, `MaxSSTableSizeWriter.java:78`). Keep the data, partitioner and compression the same across sizes. Disable auto-compaction in phase 2 so that nothing but the knob differs. Repeat each value three times.

### B3. Cluster tier

**B3a. Environment and build.** One node is enough. Copy the tree to local disk, `ant jar`, run from `/local/c509` with a dedicated local data directory on a volume of known size (e.g. 30 GiB; commit log and hints on the same local volume). Heap 2 GiB (`MAX_HEAP_SIZE=2G`, `HEAP_NEWSIZE=400M` in `conf/cassandra-env.sh`/`jvm11-server.options`). `cassandra.yaml`: `concurrent_compactors: 1`, `compaction_throughput: 16MiB/s` (so compaction lags), `memtable_flush_writers: 1`. Tools: `bin/cassandra-stress` and `cqlsh` from the same build, `nodetool`.

**B3b. Knobs.** Table `ks.t` with `compaction = {'class':'LeveledCompactionStrategy','sstable_size_in_mb': N}`, N ∈ {5, 160, 1024}. Reason: 5 is small enough to produce many files; 160 is the default; 1024 shows a large unit. Run each N on a fresh table (separate run), same data. Set by CREATE TABLE; N=5 is also altered to 160 mid-run in a secondary experiment. The positive control is the output file size, which the same option is known to bind (B3g).

**B3c. Workload.** `cassandra-stress` with a user profile of fixed row size (~1 KiB, `n=6,000,000` → about 6 GiB raw, ~4–6 GiB on disk uncompressed; set `compression = {'enabled':'false'}` so bytes are comparable). Unique keys only (no overwrites), so the live data size is the same for all N. Write threads 16. Then stop writing and wait until `nodetool compactionstats` shows no pending tasks (up to 30 min), and record. Total disk need is below 30 GiB even at the transient peak (inputs plus outputs).

**B3d. Observables and instruments.**
- `du -sb` on `data/ks/t-*` every 10 s (the actual resource).
- `nodetool tablestats ks.t`: Space used (live), SSTable count, SSTables in each level.
- `nodetool compactionstats` (pending tasks).
- File sizes via `ls -l *-Data.db`, to show the distribution of file sizes.
- Not observable directly: per-candidate-set decisions. The debug log (`logger.debug "L0 is too far behind"`, `LeveledManifest.java:311`) can be enabled with `nodetool setlogginglevel org.apache.cassandra.db.compaction DEBUG`.

**B3e. Procedure.**
1. Build, start the node, create the keyspace (RF=1) and table for N=5.
2. Start the `du` sampler, run the stress write, then wait for compaction to settle. Record peak and settled `du`, `tablestats` and the file-size histogram.
3. `DROP TABLE`, `nodetool clearsnapshot --all`, and confirm the data directory is empty. Repeat for N=160 and N=1024.
4. Secondary: with the N=160 table, throttle compaction to the minimum (`nodetool setcompactionthroughput 1`) while writing, and record L0 bytes and sstable count as they grow past `4 × N`.
5. Stop the node (`nodetool drain`, then kill). Check no process is left (`pgrep -f CassandraDaemon`, `pgrep -f cassandra-stress`).

**B3f. Predictions.**
- Settled live disk usage is the same (within ~10%) for N=5, 160 and 1024. It is set by the data volume, not by N.
- File count and median file size scale with N: median file ≈ N MiB for N=5 and 160 (each file at most N plus one partition, ~1 KiB); at N=1024 files are bounded by the data volume itself.
- Peak transient `du` is above the settled value in all three runs, and the excess grows with the compaction input size.
- Secondary experiment: L0 bytes exceed `4 × 160 MiB = 640 MiB` (`LeveledManifest.java:188`) with no mechanism stopping writes, up to the full write volume.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Settled `du` the same for all N, while file size and count differ | Claim confirmed: the option does not bound disk usage; it controls file granularity (the positive control). |
| Settled `du` differs materially (> 25%) and tracks N | Claim refuted: usage follows the knob. Check for compression or overwrite differences first (B3h). |
| L0 bytes exceed 4 × N with compaction throttled | The level limit is a trigger only. Confirms no hard cap. |
| L0 stays ≤ 4 × N under throttling | Refutes the claim for L0 (something blocks writes). |
| File sizes do not follow N | The positive control did not move. Result not confirmed. |
| `du` never approaches any level limit (e.g. N=1024, data below 4 GiB) | Limit never reached. Not confirmed for that N; use a smaller N or more data. |

**B3h. Controls.** Same data, same row count and size, no overwrites or deletes, compression off, same compaction throughput. The file-size histogram is the positive control (a cap known to bind). Snapshots cleared between runs. The same sampler for each run. Account for commit log/hints outside `data/ks/t-*`.

**B4. Risks and cleanup.** Disk: peak need ≈ 2 × data (< 15 GiB) on a 30 GiB local volume; never use shared storage. Drop the table and clear snapshots after each run, delete the data, commitlog, hints and saved_caches directories at the end. Stop the node and stress, then check `pgrep -fl 'CassandraDaemon|cassandra-stress|ant'` is empty. The unit tier writes only to the local copy's build and temp directories; delete `/local/c509` when done. Do not build in the shared source tree.

**Audit amendments (stage 4 step 0, 2026-10-24).** Made before any build output, run or reading; each leaves B1, B2f/B3f and B2g/B3g as filed. Where an amendment corrects text above, the amendment governs. Reasons are in the results file §1.1.
- **C1 (B2c, B2e steps 2-3, candidate set).** Flush real sstables, set the L1 one with `mutateLevelAndReload(1)`, build the manifest with `LeveledManifest.create(cfs, N, 10, sstables)` and read `manifest.getCompactionCandidates().sstables`. The unit yaml's partitioner is `ByteOrderedPartitioner` (`test/conf/cassandra.yaml:18`), so key ranges are chosen: every L0 sstable and the L1 sstable cover the same key range (`k000000`..`k999999` prefix) and all overlap. L1 inclusion is "the candidate set contains a level-1 reader". Random-byte values (incompressible); 2000 rows × 1 KiB per sstable.
- **C2 (B2e step 5, phase 2).** Phase 2 adds 200 L0 sstables of ~1 MiB with `cfs.disableAutoCompaction()` and unique keys; L0 total is the sum of `onDiskLength()` over `cfs.getLiveSSTables()`, all at level 0 (asserted).
- **C3 (B2e step 4).** The size-5 task is `strategy.getNextBackgroundTask(gcBefore)` from a strategy over the live sstables, executed once; the oversized partition is one partition key with 3000 clustering rows of 4 KiB (≈ 12 MiB).
- **C4 (B3a, B3c, storage and workload).** Same as the sibling amendment F5: dedicated tmpfs of 24 GiB, `n=2,000,000` rows (≈ 2 GiB) per N instead of 6 M. Table `ks.t` is created by `cqlsh` with the `cassandra-stress` `standard1` layout (`key blob`, `C0..C3 blob`), `compression = {'enabled':'false'}`, then `cassandra-stress write ... -schema keyspace=ks` fills it. Workload arithmetic: at N=5 the L0 target is 20 MiB and L1 50 MiB; at N=160 the L0 target is 640 MiB (2 GiB ≈ 3×); at N=1024 the L0 target is 4 GiB (never reached by 2 GiB: that row is the filed "limit never reached" row, not a failure of the run).
- **C5 (B3e step 2, drain).** At 16 MiB/s the drain would take hours. After the write stops (lag phase), run `nodetool setcompactionthroughput 0` and `setconcurrentcompactors 4`; "settled" is 3 reads 20 s apart with 0 pending and identical `du -sb` (cap 25 min). Peaks are read before the change.
- **C6 (B3e step 4, secondary).** Secondary run: N=160, `setcompactionthroughput 1` for the whole write, per-level bytes from `nodetool tablestats` (**SSTable bytes in each level**, `TableStatsHolder.java:264`) at the end of the write. The "N=5 altered to 160 mid-run" experiment named in B3b has no procedure or prediction and is **not run** (left for stage 3).
- **C7 (B3h, instrument control).** `TRUNCATE` at the end of every run: `du -sb` must fall to ≈ 0 (the instrument sees real usage change). The file-size histogram stays the filed positive control.
- **C8 (runbook defect D1, 2026-10-24, found in a discarded shakedown before any cluster reading; leaves B3f/B3g unchanged).** C5's "0 pending" can never hold when one L0 sstable is left without a partner (`LeveledManifest.java:569`): `compactionstats` shows only an estimate. "Settled" is now: three reads 20 s apart with `CompactionExecutor` active + pending = 0 in `nodetool tpstats` and identical file bytes (cap 25 min).

## C. Sources read

- `/users/jason92/writeup-A/playbook-autonomous.md`
- `/users/jason92/writeup-A/_TEMPLATE-autonomous.md`
- `src/java/org/apache/cassandra/db/compaction/LeveledManifest.java` (lines 480-610 and the grep hits at :59-84, :180-191, :225-345, :651-678)
- `src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java` (:46-104, :570-620)
- `src/java/org/apache/cassandra/db/compaction/LeveledCompactionTask.java` (:25-95)
- `src/java/org/apache/cassandra/db/compaction/writers/MaxSSTableSizeWriter.java` (:40-97)
- `src/java/org/apache/cassandra/io/sstable/format/SSTableReader.java` (:541-547)
- `src/java/org/apache/cassandra/schema/CompactionParams.java` (grep hits)
- `src/java/org/apache/cassandra/db/ColumnFamilyStore.java` (grep hit :3086)
- `src/java/org/apache/cassandra/db/compaction/LeveledGenerations.java` (grep hit :57)
- `src/java/org/apache/cassandra/config/CassandraRelevantProperties.java` (grep hit :604)
- `src/java/org/apache/cassandra/db/compaction/writers/MajorLeveledCompactionWriter.java` (grep hits)
- Existence only: `test/unit/org/apache/cassandra/db/compaction/LeveledCompactionStrategyTest.java`

## D. Stage-4 feedback

**Stage 4, run 1, 2026-10-24 — unit Confirmed, cluster Confirmed — does not cap; outcome class: true negative** (estimate `negative`, effect `does not cap`). Results: [`stage4-runtime-verification/results/sstable_size_in_mb-getCandidatesFor-maxSSTableSizeInBytes--autonomous.md`](../../stage4-runtime-verification/results/sstable_size_in_mb-getCandidatesFor-maxSSTableSizeInBytes--autonomous.md). One run per tier, self-checked from the raw files (18 claims hold), no run 2. Not committed (the human commits).

- **Unit (B2):** at N=1 and 5 the candidate set (6 overlapping L0 sstables, 12.2 MiB) pulled in the overlapping L1 sstable (7 candidates, output level 1); at N=160 (total 0.076 × N) it did not (6 candidates, level 0). The size-5 task wrote files of 5.00 MiB; one ≈ 12 MiB partition stayed one 11.8 MiB file. 200 L0 sstables held 212.4 MB at size 1 and at size 160 (0.006% apart).
- **Cluster (B3):** 2,000,000 rows (≈ 2 GiB) per N. Settled table bytes 2,055 / 2,047 / 2,049 MiB for N = 5 / 160 / 1024 (spread 0.4%) in 482 / 13 / 2 files (median Data.db 5.0 / 160.0 / ≈ 1,007 MiB). L0 reached 91.7× (N=5) and 2.86× (N=160) of its target, and 3.14× at N=160 with compaction at 1 MiB/s, with no write error. **N=1024 never reached its L0 target (2,009 of 4,096 MiB): the filed "limit never reached" row for that N.**
- **Prediction notes (no row changed):** B3f's "at N=1024 files are bounded by the data volume itself" missed in wording: the two files are 989.6 and 1,024.0 MiB, so the option bounds the file when the volume is 2 N. B2f's "third sstable crosses 5 MiB" is irrelevant to the result (all six overlapping sstables are taken at once).
- **Amendments made at the audit (2026-10-24, before any reading):** C1-C7 (how the L1 sstable and overlap are made; phase 2 as 200 flushes; task for the size-5 case; tmpfs, 2 M rows and `ks.standard1` created by `cqlsh`; drain boost; secondary experiment defined and the "alter mid-run" variant not run; truncate control). **Runbook defect D1 (C8):** "0 pending" can never hold when one L0 sstable has no partner; replaced before the cluster readings.
- **For stage 3:** the entry line `:557` is a scheduling threshold, as filed; the file-size cap that does bind (`MaxSSTableSizeWriter.java:78`) bounds a file, not the table. A negative LCS file would be sharper with an overwrite or TTL arm.
- **Left on the node:** none running; `~/cassandra-lcsC`, `~/stage4-logs/lcs/` (see the results file).
