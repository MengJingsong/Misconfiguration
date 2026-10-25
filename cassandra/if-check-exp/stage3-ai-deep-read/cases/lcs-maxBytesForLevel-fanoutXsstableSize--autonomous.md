# LCS per-level size target (`fanout_size` ^ level × `sstable_size_in_mb`) — verification solution  <!-- file: cases/lcs-maxBytesForLevel-fanoutXsstableSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/compaction/LeveledManifest.java:190` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (`claude-sonnet-5-5`), Claude Code CLI (version not exposed to the session), 2026-10-24 |
| Estimate | `negative`: the per-level size is a compaction trigger threshold (a score denominator), not a cap. Data above it is still kept, and the top level only logs a warning. Line 190 itself is only a `long` overflow guard. |
| Ground | Exceeding `maxBytesForLevel` makes the level a compaction candidate. It never rejects a write or deletes data. L0 can hold an unbounded backlog (the L0-STCS path even uses `Long.MAX_VALUE` as the output limit). The highest level (L8) is explicitly allowed to exceed its "maximum" (`LeveledManifest.java:262-267`). `sstable_size_in_mb` is a soft per-file rollover threshold, not a hard size cap. Total disk used is set by data ingested, overwrites/TTL and compaction progress, not by this formula. |

## A. Constraint trace

**A1. The constraint.** The LCS per-level size target `maxBytesForLevel(level) = fanout_size^level × sstable_size_in_mb` (L0 = `4 × sstable size`), computed at `LeveledManifest.java:185-193`. The line given (`:190`) is `double bytes = Math.pow(levelFanoutSize, level) * maxSSTableSizeInBytes;` at `:189` followed by the `> Long.MAX_VALUE` overflow check at `:190`. Its two inputs are compaction sub-options of the table, so the kind is a per-table CQL compaction option, not a yaml entry or `-D` property.
- `sstable_size_in_mb`: declared at `LeveledCompactionStrategy.java:52`. Unit MiB. Default **160**, hard-coded in the constructor (`LeveledCompactionStrategy.java:67`). When the key is absent from options the value stays 160; `validateOptions` uses `"1"` as its own fallback at `:576`, but that is only for the overflow check. It is converted to bytes at `LeveledManifest.java:84` (`maxSSTableSizeInMB * 1024L * 1024L`) and in `getMaxSSTableBytes()` at `LeveledCompactionStrategy.java:289-292`.
- `fanout_size`: declared at `LeveledCompactionStrategy.java:54`. Default `DEFAULT_LEVEL_FANOUT_SIZE = 10` (`:56`).
- Both are set per table: `CREATE/ALTER TABLE ... WITH compaction = {'class':'LeveledCompactionStrategy','sstable_size_in_mb':'N','fanout_size':'M'}`. Both are parsed in the constructor (`:73-90`). `ALTER TABLE` takes effect without a restart because the strategy manager rebuilds its strategies. Validation is at `:568-632`: both must be ≥ 1, and `fanout^(MAX_LEVEL_COUNT-1) × size` must fit in a `long`; see `ConfigurationException` at `:614-616`. The warning thresholds at `:78-83` (≥ 1000 MB, < 50 MB) are skipped if the JVM property `TOLERATE_SSTABLE_SIZE` is set (`:53`).
- `MAX_LEVEL_COUNT = 9`, so L0..L8 (`LeveledGenerations.java:57`).

**A2. What it caps.** Disk (SSTable bytes in each level on the node's data directory). The quantity compared is `score = (bytes in the level not currently compacting) / maxBytesForLevel(level)` (`LeveledManifest.java:251-255`). It is compared against `1.001` at `:258`. A second use is `getEstimatedTasks` (`:643-665`), which reports pending work only. In terms of "does it cap resource use", the claim in play is that a level's bytes stay bounded by roughly this value.

**A3. Mechanism.**
1. `getCompactionCandidates()` (`:199`) walks levels from the highest (`levelCount()-1 = 8`) down to L1 (`:245`).
2. For each non-empty level it computes the score (`:251-255`).
3. If `score > 1.001` (`:258`):
   - **Top level (L8):** only a `logger.warn` and `continue` (`:262-267`). No compaction, no cap. L8 can grow without limit.
   - **Otherwise:** if L0 is far behind (> `MAX_COMPACTING_L0 = 32` sstables, `:62`, `:306`) an STCS-in-L0 compaction is returned first (`:270-271`). If not, candidates are picked by `getCandidatesFor(i)` (`:495`) and returned with output limit `maxSSTableSizeInBytes` (`:281`). If no candidates (all overlapping sstables are already compacting or suspect) it logs at trace and moves on (`:283-286`).
4. If no level above L0 is over-full, L0 is compacted normally (`:291-301`). L0 candidates are capped at `getMaximumCompactionThreshold()` files per round (`:548-553`), so a fast writer simply builds a backlog.
5. The output of a compaction is rolled into new sstables by `MaxSSTableSizeWriter.shouldSwitchWriterInCurrentLocation`, which switches only when `getEstimatedOnDiskBytesWritten() > maxSSTableSize` (`writers/MaxSSTableSizeWriter.java:75-79`). It checks between partitions, so a single partition larger than `sstable_size_in_mb` produces a larger file. For major compaction, `MajorLeveledCompactionWriter` uses the same formula at `:78` to decide when to move to the next level.
6. **Line 190.** Pure arithmetic: if `fanout^level × size` exceeds `Long.MAX_VALUE` it throws `RuntimeException`. `validateOptions` (`LeveledCompactionStrategy.java:607-621`) pre-checks the worst case (level 8) so this should be unreachable for validated tables.

*Bypass / overshoot paths:* L0 backlog (no size limit); L8 (warn only); starved-level injection (`getOverlappingStarvedSSTables`, `:342-394`) moves data between levels but does not limit it; sstables that overlap on add are sent to L0 (`LeveledGenerations.java:157-161`); user-defined or L0 STCS tasks use `Long.MAX_VALUE` (`LeveledCompactionStrategy.java:211`, `LeveledManifest.java:209`, `:312`) so can produce one oversized sstable. Compactions in progress temporarily need old + new bytes on disk.

**A4. Other consumers.** Commit log, hints, saved caches, snapshots/backups, other tables and keyspaces, and the temporary space of in-flight compactions and streaming all use the same disk with no relation to this value. Memory is not capped by this constraint at all (only the per-compaction candidate set is capped by `max_threshold`).

**A5. Evidence beyond the source.** In-tree: the explanatory comment at `LeveledManifest.java:213-240` (LevelDB-style scoring; "if you are consistently writing too fast for LCS to keep up, you're still screwed", i.e. no write blocking). Unit test model: `test/unit/org/apache/cassandra/db/compaction/LeveledCompactionStrategyTest.java` (uses `sstable_size_in_mb`=1 at `:107`, `:568`, `:918`; validation of invalid fanout/size at `:975-978`) and `LeveledGenerationsTest.java`. Public docs: Cassandra docs, "Leveled Compaction Strategy" (`sstable_size_in_mb`, `fanout_size`) — consulted from memory, not fetched in this session. Issue CASSANDRA-5727 is cited in the source at `:82`.

## B. Verification solution

**B1. Claim under test.** The per-level size target `fanout_size^level × sstable_size_in_mb` does **not** cap the bytes a level or the table holds on disk: (a) with writes faster than compaction, L0 and the sum over levels exceed their targets by a large factor without any write rejected; (b) the highest level (L8) is only warned about; (c) `sstable_size_in_mb` is a soft per-file threshold that a large partition exceeds. Total disk instead tracks bytes ingested.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk first (e.g. `rsync -a ~/cassandra-5.0.9/ /tmp/lcs-unit/src/`), never build in the shared tree. `cd /tmp/lcs-unit/src && ant jar` then `ant testsome -Dtest.name=LeveledManifestCapTest -Dtest.classlist...` — simplest: add a new test class `test/unit/org/apache/cassandra/db/compaction/LeveledManifestCapTest.java` in the copy, modelled on `LeveledCompactionStrategyTest` (same `@BeforeClass` schema setup, `SchemaLoader`, same `ColumnFamilyStore` creation), and run `ant testsome -Dtest.name=org.apache.cassandra.db.compaction.LeveledManifestCapTest`. JVM options are the defaults of the test target (the default `-Xmx1g` is enough). Use `-Dcassandra.test.*` defaults.

**B2b. Knobs.** The two table options, set via `CompactionParams.lcs(map)` as at `LeveledCompactionStrategyTest.java:107`:
- `sstable_size_in_mb` ∈ {1, 2, 4}. Small values make levels reachable with MB of data. 1 is the smallest allowed (`:580-582`).
- `fanout_size` ∈ {2, 10}. Default 10 and a small 2 so L2/L3 targets are reachable.
- Also call the static `LeveledManifest.maxBytesForLevel(level, fanout, bytes)` directly for the arithmetic check.

**B2c. Workload.** Directly flush sstables with known size (as the existing test does: write N partitions with fixed-size values, `cfs.forceBlockingFlush`, no background compaction, `cfs.disableAutoCompaction()`). Arithmetic for fanout 10, size 1 MiB: L0 target 4 MiB, L1 10 MiB, L2 100 MiB. Write ≈ 40 MiB into L0 (e.g. 40 flushes of ≈ 1 MiB; 1 KiB values × 1000 rows). That is 10× the L0 target and 4× the L1 target after one promotion. Separate case: one partition with ≈ 5 MiB of clustering rows with `sstable_size_in_mb=1`, then compact it.

**B2d. Observables and instruments.** Per level: `getAllLevelSize()` (count) and `getAllLevelSizeBytes()` (bytes) from the strategy (`LeveledCompactionStrategy.java:110-118`), plus `manifest.getEstimatedTasks()`. File sizes via `SSTableReader.onDiskLength()` and `Descriptor` directory listing (`du -sb` of the table directory under the test data dir). The score is not exposed; compute it as bytes/`maxBytesForLevel`. Not directly observable: the internal `compactionCounter`; use trace logging if needed.

**B2e. Procedure.**
1. Create the table with the knob values; disable auto-compaction.
2. For each knob combination, flush 40 sstables of ≈ 1 MiB into L0; record `getAllLevelSizeBytes()[0]` and the ratio to `maxBytesForLevel(0, …)`. Assert no exception on flush/insert.
3. Call `getNextBackgroundTask(gcBefore)` repeatedly and execute each task (`task.execute(...)`) until it returns null; record per-level bytes and the largest sstable file each time.
4. Level-8 case: construct a manifest through `LeveledManifest.create` with ≈ 3 hand-made L8 sstables whose total bytes exceed `maxBytesForLevel(8, …)` — with fanout 2, size 1 MiB this is only 256 MiB; fake lengths are not possible, so instead use fanout 1 and size 1 (target = 1 MiB for every level; `fanout_size ≥ 1` is valid, `:597`) and write 3 sstables with level metadata 8 (`SSTableReader.mutateLevelAndReload(8)`). Call `getCompactionCandidates()` and observe null plus the warn log at `LeveledManifest.java:264`.
5. Large-partition case: one ≈ 5 MiB partition, `sstable_size_in_mb=1`; run a compaction; record the output sstable length.
6. Overflow guard (line 190): call `LeveledManifest.maxBytesForLevel(8, 1000, 1L<<40)` and expect `RuntimeException`; also `maxBytesForLevel(3, 10, 160L<<20)` returns `10^3 × 160 MiB` exactly.
7. Positive control: same workload with a strategy that does bound something, namely `max_threshold` on L0 candidates: show one `getCandidatesFor(0)` round returns ≤ `max_threshold` sstables (`:548-553`).

**B2f. Predictions** (before any run).
- Step 2: L0 bytes ≈ 40 MiB for every knob value, i.e. ≈ 10× target (size=1) and the ratio scales as `1/sstable_size` (size 4 → target 16 MiB, ratio ≈ 2.5); no exception.
- Step 3: after draining, L1 bytes may be ≈ target ×(1.0–1.1) but L-total ≈ ingested bytes (± compaction savings); the sum over levels is never below the ingested live bytes. Level 8 case: `getCompactionCandidates()` returns null, warn emitted, bytes unchanged.
- Step 5: output sstable > 1 MiB (≈ 5 MiB), i.e. the size knob is not a hard cap.
- Step 6: throws for the overflow input; exact value otherwise.
- Control (step 7): ≤ `max_threshold` (default 32) candidates.
What would show the claim wrong: any level (L1–L7 steady state, or L0 in step 2) whose bytes are held at or below the target by something other than compaction; an ingestion failure or write refusal in step 2; or L8 being compacted/trimmed in step 4; or the 5 MiB partition being split below `sstable_size_in_mb`.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| L0 bytes ≈ 10× target, writes accepted (step 2) | usage does not follow the target — claim confirmed |
| Per-level bytes after draining ≈ ingested bytes regardless of `sstable_size_in_mb`/`fanout_size` | usage flat w.r.t. the knob; claim confirmed |
| Bytes in a level drop with a smaller target for the same data | usage follows the knob → claim refuted |
| L8 stays over target, warn logged, no task | top level uncapped — claim confirmed |
| Output sstable ≈ 5 MiB with size=1 | soft threshold — confirmed |
| Positive control (`max_threshold`) fails to bound candidate count | control did not bind: result not confirmed, fix the setup |
| Level never exceeds target (e.g. data too small, <4 MiB L0) | limit never reached: not confirmed |

**B2h. Controls.** Same data with `disableAutoCompaction` on and off; same workload with a different compaction class (e.g. STCS) to show bytes are identical when no leveling happens; repeat each case 3 times; confirm overlap-induced "send to L0" (`LeveledGenerations.java:157-161`) did not occur by checking levels before and after.

### B3. Cluster tier

**B3a. Environment and build.** One node (single-node is sufficient; the claim is about local disk). JDK 11 + Ant, `ant jar` in a local copy (`/tmp/lcs-cluster/src`). Dedicated local dirs of known size, e.g. a 20 GiB filesystem or directory under `/tmp/lcs-cluster/{data,commitlog,hints,saved_caches}` set via `cassandra.yaml` (`data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory`). JVM: `-Xms2g -Xmx2g` in `conf/jvm11-server.options`. Set `concurrent_compactors: 1` and `compaction_throughput: 8MiB/s` (accurate unit syntax for 5.0 yaml) to make compaction slow so it falls behind. Disable auto-snapshot (`auto_snapshot: false`). `JMX` on localhost. Client: `cassandra-stress` from the same build (`tools/bin/cassandra-stress`).

**B3b. Knobs.** Table option pairs (set by `ALTER TABLE ... WITH compaction=…`, no restart):
- A: `sstable_size_in_mb=10`, `fanout_size=10`
- B: `sstable_size_in_mb=160`, `fanout_size=10` (default)
- C: `sstable_size_in_mb=10`, `fanout_size=2`
Target L1 = 100 MiB / 1.6 GiB / 20 MiB; L2 = 1 GiB / 16 GiB / 40 MiB. Control table D uses `SizeTieredCompactionStrategy` with the same data.

**B3c. Workload.** `cassandra-stress` with a user profile, one table per configuration (or one at a time, keyspace dropped between runs), unique keys (no overwrites) so live data = ingested: `cassandra-stress write n=6000000 -col size=FIXED(1000) n=FIXED(1) -rate threads=64` — ≈ 6 GB raw per run (6 M rows × ~1 KB; on disk ≈ 6 GB with `LZ4`; check the compression ratio and scale `n` to ≈ 5 GB on disk). Arithmetic: for config A the L1 target is 100 MiB and L2 1 GiB, so at 5 GB of data L3 (10 GiB target) is the level holding the overflow and L0 target is 40 MiB; ingestion at several tens of MB/s versus 8 MiB/s compaction guarantees the L0 backlog exceeds the 40 MiB target by > 10×. Duration ≈ 10–20 minutes per run, then 30 minutes of idle compaction.

**B3d. Observables and instruments.** Actual resource = disk: `du -sb <data>/<ks>/<table>-*` every 10 s; `nodetool tablestats <ks.table>` (Space used (live), SSTable count, "SSTables in each level"); `nodetool compactionstats` (pending tasks); JMX `org.apache.cassandra.metrics:type=Table,name=LiveDiskSpaceUsed`, `TotalDiskSpaceUsed`, `PendingCompactions`; `system.log` grep for `L8 (maximum supported level)` and `Compaction score`. `df` on the data volume. Not observable: the score itself (compute from level bytes via `nodetool tablestats` "SSTables in each level" counts × approx size, or `sstablemetadata` level field).

**B3e. Procedure.**
1. Build; configure; start the node; `nodetool status` to confirm up.
2. `cassandra-stress` creates the schema; `ALTER TABLE` to config A.
3. Start the sampler loop (`du`, `nodetool tablestats`, `nodetool compactionstats`) writing to `/tmp/lcs-cluster/samples-A.csv`.
4. Run the write workload; stop it; keep sampling until `PendingCompactions == 0` for 5 minutes.
5. Record: peak L0 bytes, peak total live bytes, final per-level bytes, whether any write errored.
6. Truncate/drop the keyspace, `nodetool clearsnapshot`, repeat for B, C, then control D.
7. Positive control: on the same workload, set `concurrent_compactors: 4` and `compaction_throughput: 0` to show level bytes approach their targets once compaction can keep up, and set a `max_threshold` of 4 to show the L0-STCS batch size follows it (`nodetool compactionhistory`).
8. Stop the node (`kill` the pid; `pgrep -f CassandraDaemon` must be empty), delete `/tmp/lcs-cluster`.

**B3f. Predictions.**
- Peak L0 bytes ≫ 4 × sstable_size: ≥ 10× for A and C (≥ 400 MiB), for B ≥ 1 (B's L0 target is 640 MiB; expect the ratio to be smaller, ≈ 2–5×), with no write error.
- Peak total live bytes for A, B, C, D differ by < 15% for the same ingested data (≈ ingested size + compaction temp up to ≈ one compaction's worth, i.e. a few × `sstable_size`), i.e. total disk follows the data volume, not `sstable_size_in_mb × fanout^level`.
- Config C (fanout 2): lower targets (L3 80 MiB) yet total bytes ≈ the same as A.
- After draining, level occupancy reaches roughly the target shape (L1 ≤ ≈ target) while total bytes unchanged, showing the targets steer compaction, not storage.
What would show the claim wrong: total live bytes at the same ingested volume systematically smaller (> 15%) with smaller targets; or writes failing/stalling when L0 > target; or bytes in L8/L-top clamped by the target.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| L0 bytes ≫ target while writes continue, total disk ≈ ingest for A/B/C/D | claim confirmed: target doesn't cap disk |
| Total disk differs between A/B/C in proportion to targets (smaller target → less disk) | claim refuted |
| Write errors/timeouts once L0 > target | refuted (write blocking exists) — contradicts source trace; re-check |
| Under positive control (faster compaction) levels settle at their targets but total bytes unchanged | targets only schedule compaction: confirmed |
| `concurrent_compactors`/throughput change moves the peak L0 but `max_threshold` change moves the candidate batch | positive control moved as expected |
| Pending compactions never rise above 0 / L0 never exceeds target (workload too slow) | limit never reached: not confirmed; raise ingest rate or lower compaction throughput |
| Positive control shows no change | control did not move: not confirmed |

**B3h. Controls.** STCS table D with identical data (no leveling); a run with `compaction_throughput: 0` (compaction keeps up) vs 8 MiB/s (falls behind) to isolate the compaction-lag effect; stress seeds fixed (`-pop seq=1..N`) so no overwrites; snapshots disabled; compressed vs uncompressed size noted once; page-cache irrelevant to `du -sb`.

**B4. Risks and cleanup.** Disk: cluster run writes ≈ 6 GB plus compaction temp (≤ 2×); use a local volume with ≥ 20 GiB free, never the shared home or network FS; the unit tier writes < 1 GiB under `/tmp/lcs-unit`. Put commit log and hints on the same local volume (`commitlog_total_space` default is bounded by the yaml). Leftover processes: `pgrep -f CassandraDaemon`, `pgrep -f cassandra-stress`, `pgrep -f ant` must all be empty after each run; `kill` then `kill -9` if needed. Cleanup: `rm -rf /tmp/lcs-unit /tmp/lcs-cluster`; confirm with `ls /tmp` and `df`. Nothing is modified outside the copied tree.

**Audit amendments (stage 4 step 0, 2026-10-24).** Made before any build output, run or reading; each leaves B1, B2f/B3f and B2g/B3g as filed. Where an amendment corrects text above, the amendment governs. Reasons are in the results file §1.1.
- **F1 (B2e step 4, level 8).** Use **one** sstable of ≥ 2 MiB at level 8, not three. With `sstable_size_in_mb=1`, `fanout_size=1` every level's target is 1 MiB, so one 2 MiB sstable scores ≈ 2 > 1.001 (`LeveledManifest.java:255-258`). Several sstables written as separate flushes would overlap, and `LeveledGenerations` sends overlapping sstables of one level to L0 (`:157-161`). Build the manifest with `LeveledManifest.create`, set the level with `mutateLevelAndReload(8)`, and capture the `:264` WARN with a logback `ListAppender` on the `LeveledManifest` logger. L0 is empty, so a null return means no task.
- **F2 (B2c, B2e step 2).** Values are random bytes (incompressible) and every row key is unique across all flushes, so live data equals ingested data and `onDiskLength` is comparable across knob values.
- **F3 (B2e step 3, step 7).** "Drain" means: loop `strategy.getNextBackgroundTask(gcBefore)` and `execute` it, up to 500 tasks, until it returns null. `getCandidatesFor` is private (`:495`), so the `max_threshold` control reads the public `getCompactionCandidates()` on 40 overlapping L0 sstables with `max_threshold` 4 and 32 (candidate count ≤ 4 vs. > 4). **Added control:** `truncateBlocking()` must bring the summed level bytes to 0, showing the instrument sees real usage change.
- **F4 (B3d).** `nodetool tablestats` prints **SSTable bytes in each level** in 5.0 (`TableStatsHolder.java:264`, `ColumnFamilyStore.getPerLevelSizeBytes`): per-level bytes are observed directly, not computed from counts.
- **F5 (B3a, B3c, B4 workload and storage).** Node data, commit log, hints and saved caches go on a dedicated tmpfs of known size (`sudo mount -t tmpfs -o size=24g`), because a spinning local disk stalls several-GiB writes (HANDOFF "Running"); `du -sb` and `df` read the same file bytes as on a disk filesystem. Each run writes `n=2,000,000` rows of ~1 KiB (≈ 2 GiB; calibrated once by a discarded shakedown) instead of 6 M. The arithmetic still reaches the limits: L0 target is 40 MiB for A and C (≈ 50×) and 640 MiB for B (≈ 3×).
- **F6 (B3e step 4, drain).** At 8 MiB/s the LCS rewrite of 2 GiB would take hours. After the write stops (the lag phase, where peak L0 is read), run `nodetool setcompactionthroughput 0` and `nodetool setconcurrentcompactors 4`, and call the drain done when pending compactions are 0 on three reads 20 s apart (cap 25 min). Peaks are read before the change.
- **F7 (B3e step 7, control).** The cluster positive control is a run of config A with `concurrent_compactors 4` and `compaction_throughput 0` from the start (A′), plus `TRUNCATE` at the end of every run (du must fall to ≈ 0). The `max_threshold` batch-size control is done at the unit tier (F3) only.
- **F8 (runbook defect D1, 2026-10-24, found in a discarded 150,000-row shakedown before any cluster reading; leaves B3f/B3g unchanged).** F6's "pending compactions are 0" can never hold: `nodetool compactionstats` shows an estimate (here 6) while the only sstable left in L0 has no partner, so no task can run (`LeveledManifest.java:569`, fewer than 2 candidates). "Drain done" is now: three reads 20 s apart with `CompactionExecutor` active + pending = 0 in `nodetool tpstats` and identical table file bytes (cap 25 min); the estimate is recorded, not tested.
- **Left for stage 3:** the file's "Sources read" lists a sibling playbook path outside the repository.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/compaction/LeveledManifest.java (lines 1-720)
- src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java (lines 50-300, 565-633)
- src/java/org/apache/cassandra/db/compaction/LeveledGenerations.java (lines 40-190)
- src/java/org/apache/cassandra/db/compaction/writers/MaxSSTableSizeWriter.java (lines 44-96)
- src/java/org/apache/cassandra/db/compaction/writers/MajorLeveledCompactionWriter.java, CompactionStrategyManager.java (grep matches only)
- test/unit/org/apache/cassandra/db/compaction/LeveledCompactionStrategyTest.java (grep matches only); test file list for `Leveled*.java`

## D. Stage-4 feedback

**Stage 4, run 1, 2026-10-24 — unit Confirmed, cluster Confirmed — does not cap; outcome class: true negative** (estimate `negative`, effect `does not cap`). Results: [`stage4-runtime-verification/results/lcs-maxBytesForLevel-fanoutXsstableSize--autonomous.md`](../../stage4-runtime-verification/results/lcs-maxBytesForLevel-fanoutXsstableSize--autonomous.md). One run per tier, self-checked from the raw files (20 claims hold), no run 2. Not committed (the human commits).

- **Unit (B2):** 18 runs (size {1,2,4} × fanout {2,10} × 3): L0 held 40.5 MiB of 40 flushes against targets of 4, 8 and 16 MiB (10.13×, 5.06×, 2.53×), no write refused; after draining the level bytes summed to 42.518 MB in every run (spread 0.004%); one 2.23 MB sstable at L8 (target 1 MiB) gave a null candidate and one WARN; a ≈ 5 MiB partition came out as a 5.02 MiB file against `sstable_size_in_mb=1`; `max_threshold` bounded the candidate batch (4 and 32).
- **Cluster (B3):** 2,000,000 rows (≈ 1.9 GiB) per label. L0 reached 1,872 MiB (46.8× its 40 MiB target) in A and C and 2.92× its 640 MiB target in B, with 0 write errors; after the drain the table held 1,907.2 (A), 1,905.5 (B), 1,905.4 (C, fanout 2), 1,907.6 MiB (STCS), and the A′ control (fast compaction) 1,906.8 MiB with its peak L0 30% lower. The levels below the top settled at their targets (C: L1-L5 at 1.00), which is the only effect of the constraint: it steers compaction.
- **Amendments made at the audit (2026-10-24, before any reading):** F1-F7 (one ≥ 2 MiB L8 sstable; random values and unique keys; drain by task loop; per-level bytes from `nodetool tablestats`, which exists in 5.0; tmpfs and 2 M rows; drain boost; A′ control). **Runbook defect D1 (F8):** the "pending compactions 0" stop condition can never hold when one L0 sstable has no partner; replaced before the cluster readings by "no active or queued compaction task and identical file bytes".
- **For stage 3:** the file's "no byte cap binds" ground held. Two points to note: the cluster tier never reached L8 (C peaked at L7, 620 MiB of 1,280 MiB), so the "top level only warns" part rests on the unit tier; and the estimate's reasoning on L0 STCS (`Long.MAX_VALUE` output) was not exercised separately. The B3 comparison of totals is largely a consequence of unique keys (ingest = live data); a TTL or overwrite arm would test "disk follows the live data" more sharply.
- **Left on the node:** none running; `~/cassandra-lcsF`, `~/stage4-logs/lcs/` (see the results file).
