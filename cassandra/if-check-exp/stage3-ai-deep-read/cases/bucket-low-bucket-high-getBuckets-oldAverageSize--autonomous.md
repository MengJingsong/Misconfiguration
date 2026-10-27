<!-- file: cases/bucket-low-bucket-high-getBuckets-oldAverageSize--autonomous.md -->
# STCS bucket_low / bucket_high (similar-size test in getBuckets) — verification solution  <!-- file: cases/bucket-low-bucket-high-getBuckets-oldAverageSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/compaction/SizeTieredCompactionStrategy.java:274` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-26 (design only, nothing built or run) |
| Estimate | `negative`. The line only decides which sstables are grouped into the same size-tier bucket; it never compares a usage figure to a memory or disk budget. |
| Ground | `bucket_low`/`bucket_high` are grouping ratios, not capacities. They change which sstables get compacted together (and so indirectly the temporary disk a compaction needs), but nothing stops or throttles a node when disk or heap use grows. The only hard bound near this code is `max_threshold`, a count of sstables per compaction (line 151), which is a different constraint. |

## A. Constraint trace

**A1. The constraint.** Two per-table compaction sub-options of `SizeTieredCompactionStrategy`, `bucket_low` and `bucket_high` (the operand at line 274 is `oldAverageSize`, the running mean sstable size of an existing bucket, which they scale). Kind: table schema option (compaction map), not a yaml/-D setting. First declared: `SizeTieredCompactionStrategyOptions.java:27-28` (defaults), keys at `:30-31`; parsed at `:40-44` (amended 2026-10-26, A1); validated at `:83-89` (must parse as double, `bucket_high > bucket_low`). Unit: dimensionless ratio of sstable bytes to bucket average bytes. Defaults: `bucket_low = 0.5`, `bucket_high = 1.5` (constants, not derived). Related `min_sstable_size` default `50 MiB` (`:26`), unit bytes, must be >= 0 (`:73`). Set by `CREATE/ALTER TABLE ... WITH compaction = {'class':'SizeTieredCompactionStrategy','bucket_low':..,'bucket_high':..}`; no restart needed (ALTER re-creates the strategy, which re-reads the options in the constructor at `SizeTieredCompactionStrategy.java:76`). Not settable by yaml, -D or JMX per se.

**A2. What it caps.** Nominally nothing in bytes. It defines the width of a size tier: a sstable of `size` joins a bucket if `oldAverageSize*bucketLow < size < oldAverageSize*bucketHigh` (line 274). The compared quantity is `sstable.onDiskLength()` (`createSSTableAndLengthPairs`, `:241`) against the bucket mean (disk bytes). The resource it touches indirectly is disk (compaction output plus inputs coexist until the transaction commits) and nothing about heap.

**A3. Mechanism.**
1. `getNextBackgroundSSTables` (`:79`) takes uncompacting sstables (`:85`), builds (sstable, length) pairs and calls `getBuckets` with `bucketHigh`, `bucketLow`, `minSSTableSize` (`:87`).
2. `getBuckets` (`:248`) sorts ascending by size (`:252-258`), then for each file scans existing buckets (`:270`). Line 274: join if strictly inside (low, high) of the bucket mean, or line 275: both file and bucket mean are below `min_sstable_size`. On join, the bucket is re-keyed under the new mean (`:278-282`); otherwise a new bucket is created (`:288-290`).
3. `mostInterestingBucket` (`:116`) drops buckets with fewer than `min_threshold` sstables and trims the others to `max_threshold` coldest-removed (`:122-123`, `:151`), then picks the hottest by reads/sec/key (`:129`).
4. The chosen list becomes a `CompactionTask` (`:200`).
Outcomes: a size inside the band joins and may later produce a compaction; outside the band starts a new bucket; nothing is rejected, refused or truncated by bytes. Overshoot/bypass: `bucket_high` very large (or `bucket_low` 0) puts all sstables in one bucket, so the compaction input is limited only by `max_threshold` (count) and the temporary space needed is the sum of those inputs; the keyed HashMap iteration order (`:270`) makes the choice of bucket among several valid ones order-dependent. Major compaction (`getMaximalTask`, `:205-216`) and user-defined compaction (`:218`) skip bucketing entirely.

**A4. Other consumers.** Disk during compaction is also consumed by flushes, commit log, hints, snapshots, repair streaming, other tables' compactions (limited by `concurrent_compactors`), and by compaction-space reservation logic elsewhere (`CompactionTask` free-space check, not read here). Heap is used by compaction readers/index summaries independent of these ratios.

**A5. Evidence beyond the source.** None.

## B. Verification solution

**B1. Claim under test.** Changing `bucket_low`/`bucket_high` does not bound disk or heap use: it only changes which sstables are grouped, so peak disk during compaction follows the total bytes of the sstables chosen (up to `max_threshold`), not the ratios, and no ratio value makes the node refuse or cap growth. A bound on usage appears only when a different constraint (`max_threshold`) is applied.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tag to local disk (`rsync -a ~/cassandra-5.0.9/ /local/scratch/c509/`), `cd /local/scratch/c509 && ant jar`. Write a JUnit test (or small main) in a new class under `/local/scratch/c509/test/unit/org/apache/cassandra/db/compaction/BucketProbeTest.java` (never in the shared tree), run `ant testsome -Dtest.name=BucketProbeTest`. JVM defaults from `build.xml`.

**B2b. Knobs.** `(bucketLow, bucketHigh)` in {(0.5,1.5) default, (0.9,1.1) narrow, (0.01,100.0) very wide}; `minSSTableSize` fixed at 0 (so line 275 never joins small files and only line 274 matters); then repeat once with 50 MiB. Set by passing args directly to the static `SizeTieredCompactionStrategy.getBuckets(files, high, low, minSize)`. Chosen to span "nearly never group" to "always group".

**B2c. Workload.** Synthetic `Pair<String,Long>` list: 32 sstables with sizes 1 MiB * 1.3^i (i = 0..31, geometric, sizes `floor(MiB*1.3^i)`; largest 3.326 GiB, total 14.410 GiB; amended 2026-10-26, A2: the filed 4.2 GiB was wrong), plus a second list of 32 equal sizes of 100 MiB (total 3.125 GiB). Amended 2026-10-26 (U1): the test also uses real sstables, see D. No real sstables needed (the method is generic in `T`). Arithmetic: with ratio 1.3 successive sizes differ by 30%, so default band (0.5,1.5) joins neighbours, narrow (0.9,1.1) isolates every file, wide groups all.

**B2d. Observables and instruments.** Output of `getBuckets`: number of buckets, bucket sizes, sum of member sizes of the largest bucket (the bytes a compaction of that bucket would read and write). Plain assertions/printing; sums computed in the test. Not observable here: real disk or heap use.

**B2e. Procedure.** 1) Build. 2) Run the test over each (low, high, minSize) and each list. 3) Record bucket count and the largest-bucket byte sum, and (for that bucket) the sum after trimming to `max_threshold` = 32 via `mostInterestingBucket`-style trimming on counts. 4) Positive control: run the same lists with `max_threshold` = 4 and 32 on the trim step to show the count cap does bound the largest-input bytes.

**B2f. Predictions.** *(Replaced 2026-10-26 before any reading, amendments A2 and U1-U3 in D; the numbers come from `harness/.../model-predict.py`, a stand-alone model of lines 248-292, not from a run.)*
(i) Static call on the synthetic lists. Geometric list (32 files, 15,472,761,705 B = 14.410 GiB, largest 3.326 GiB), `minSSTableSize` 0: narrow (0.9,1.1) gives 32 buckets of one file (largest bucket 3.326 GiB); default (0.5,1.5) gives 11 buckets (ten of 3 files, one of 2; largest by bytes 5.885 GiB); wide (0.01,100) gives 1 bucket of 32 files, 14.410 GiB. With `minSSTableSize` 50 MiB: narrow 18 buckets, default 7, wide 1 (the 15 files below 50 MiB share one bucket at every ratio). Equal list (32 x 100 MiB): 1 bucket of 32 files, 3.125 GiB, at every ratio and either `minSSTableSize`. (The filed "default about 5-8 buckets" and "about 18 GiB" were arithmetic errors.)
(ii) Real sstables (U1: 12 flushes of 5,000 x 1.15^i rows, `min_threshold` 4, `max_threshold` 32, `min_sstable_size` 0): narrow: 12 buckets of one file and no task (null); default: two buckets of about 6 files each (model [6,6]; any split with both buckets of 4 to 8 files is accepted), the task takes one of them: 4 to 8 inputs; wide: one bucket of 12 and a task of all 12 inputs (input bytes = total bytes of the 12 sstables); wide with `max_threshold` 4 (U2): a task of exactly 4 inputs (model: the 4 smallest, 17% of the total bytes; judged only as inputs = 4 and input bytes below the wide task's). Executed tasks (wide, default, wide with `max_threshold` 4): peak extra Data.db bytes during the task is within 0.8 to 1.15 of the task's input bytes (output about equals input, keys are unique), so the peak extra is ordered wide > default > wide/max 4 > narrow (0, no task).
Bytes of the largest bucket therefore scale with the band width (it changes grouping) and no value caps them; only `max_threshold` shrinks the bytes a task reads and writes.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Largest-bucket byte sum grows with the band width and nothing caps it, while `max_threshold` trimming reduces it | claim confirmed: ratios only group; a count cap is the only bound |
| Some ratio value yields a bucket byte sum bounded irrespective of input (a byte ceiling) | claim refuted: ratios act as a size cap |
| Equal-size list gives identical result at all ratios | consistent with grouping-only behaviour |
| Largest bucket never reaches many files (fewer than min_threshold) in any setting, or the `max_threshold` control does not move the sum | not confirmed; fix workload sizes and rerun |

**B2h. Controls.** Same input, same method, only the knobs change; `minSSTableSize` = 0 isolates line 274 from line 275; the count-cap control shows the harness can see a bound when one exists.

### B3. Cluster tier

**B3a. Environment and build.** One node; data, commit log, hints, saved_caches on a tmpfs directory (`/dev/shm/s4b10sb`; amended 2026-10-26, C1: no 20 GiB loopback volume exists on the run node, and the data is far smaller after C2). Copy and build the tag locally (`ant jar`), run `bin/cassandra -f` from the copy with `cassandra.yaml` pointing every directory at `/local/scratch`; heap `-Xms2G -Xmx2G`; `concurrent_compactors: 1`; `compaction_throughput: 0`.

**B3b. Knobs.** Table `ks.standard1` (amended 2026-10-26, C1: stress's table; was `ks.t`) with `compaction = {'class':'SizeTieredCompactionStrategy','min_threshold':'4','max_threshold':'32','min_sstable_size':'0','bucket_low':X,'bucket_high':Y}`, (X,Y) in {(0.9,1.1), (0.5,1.5), (0.01,100)}; control run (0.01,100) with `max_threshold` = 4. Set with `ALTER TABLE` through cqlsh, no restart.

**B3c. Workload.** *(Replaced 2026-10-26, amendment C2: the filed arithmetic was wrong. 12 batches of 50 MiB x 1.5^i total 12.6 GiB, not 4 GiB, so the compaction output would not fit the 20 GiB volume with the inputs; and at an exact ratio of 1.5 a neighbour is never strictly below 1.5 x the bucket mean, so the default band would not have joined them as B3f said.)* Disable autocompaction (`nodetool disableautocompaction ks standard1`). Using `cassandra-stress write n=<rows_i> -pop seq=<a>..<b>` (unique keys, no overwrites; stress's own table `ks.standard1`, compression off), write 12 chunks of `rows_i = round(50000 * 1.15^i)` rows, i = 0..11 (50,000 ... 232,620; total 1,450,084 rows, about 300 MB), and run `nodetool flush ks standard1` after each, giving 12 sstables whose sizes grow by 15% each. Then `nodetool enableautocompaction ks standard1` and wait until compactionstats is idle (three consecutive polls). Peak on-disk need is at most about twice the total, well inside the tmpfs.

**B3d. Observables and instruments.** Disk: `du -sb /local/scratch/data/ks/t-*` and `df` every 1 s into a CSV; `nodetool compactionstats` and `nodetool tablestats ks.t` (sstable count, space used); heap via `jstat -gc <pid> 1000` and `nodetool info`; compaction log lines in `system.log` (inputs per compaction). Not observable directly: per-compaction in-flight temporary bytes except via `du` peaks.

**B3e. Procedure.** 1) Build, start node, create keyspace/table, set (X,Y). 2) Load and flush as in B3c. 3) Start sampling. 4) Enable autocompaction; wait for idle. 5) Record peak `du` (minus steady-state), number and size of compactions from the log, peak heap. 6) `nodetool stopdaemon`, delete the data dir, repeat for each (X,Y) and the control. 7) Confirm no Cassandra/jstat/sampler process remains (`pgrep -af cassandra`).

**B3f. Predictions.** *(Replaced 2026-10-26 before any reading, amendments C2-C4 in D; numbers from `model-predict.py` on row counts as sstable sizes, not from a run.)* `T` is the total Data.db bytes of the 12 sstables after the last flush.
- Narrow (0.9,1.1): no compaction runs (12 singleton buckets), the table ends with 12 sstables, peak extra disk is 0.
- Default (0.5,1.5): two buckets of about 6 (model [6,6]); each reaches `min_threshold` 4 and compacts, so the table ends with 2 sstables; the largest single compaction reads about 0.70 T (accepted 0.5 to 0.85 T) and the peak extra disk is about that.
- Wide (0.01,100): one bucket of 12, one compaction with 12 inputs, one sstable at the end; peak extra disk is about T (accepted 0.85 to 1.15 T), peak total about 2 T.
- Control, wide with `max_threshold` 4: every compaction has at most 4 inputs (model: three compactions of the 4 smallest, 0.17 T, 0.30 T and 0.53 T, 3 sstables at the end); peak extra disk about 0.53 T (accepted 0.4 to 0.7 T), below the wide arm's.
So the peak extra disk is ordered wide > default > narrow (0), it follows the bytes of the sstables picked, and the node never refuses or stalls at any ratio. Heap: not expected to depend on the ratio; "differ materially" in B3g means the peak `RssAnon` during the compaction phase differs by more than 25% between the narrow and wide arms and rises monotonically from narrow to default to wide.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Peak extra disk tracks the bytes of the chosen bucket (wide ratio highest) and no ratio stops growth | claim confirmed: usage does not follow a ratio cap |
| Peak extra disk is the same bounded value for every ratio, or a ratio sets an evident ceiling | claim refuted |
| `max_threshold` control lowers the peak below the wide case | positive control worked (a known cap binds) |
| Control did not lower the peak, or no compaction in the wide case reached more than `min_threshold` files | not confirmed; enlarge workload or lower `min_threshold`, rerun |
| Heap peaks differ materially across ratios | unexpected dependency; investigate (refutes only if monotonic in the ratio) |

**B3h. Controls.** Identical data per run (same stress seed, fresh data dir); one knob changes at a time; autocompaction held off during load so flush timing does not interact; control run with `max_threshold` shows a real bound.

**B4. Risks and cleanup.** Disk: the dedicated 20 GiB volume with a 4-8 GiB peak; stop and rerun if `df` shows more than 80% used. Shared storage: nothing outside `/local/scratch`; do not build in the shared tree. Processes: `nodetool stopdaemon`, then `pgrep -af 'cassandra|jstat|cassandra-stress'` must be empty; remove `/local/scratch/data` and the build copy.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/SizeTieredCompactionStrategy.java (lines 50-319)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/SizeTieredCompactionStrategyOptions.java

## D. Stage-4 feedback

Amendments (2026-10-26, stage 4 design audit, all before any reading; they change workload arithmetic and the numbers in B2f and B3f, not the claim B1, the readings tables B2g and B3g or their meaning):
- **A1.** `SizeTieredCompactionStrategyOptions.java` parse lines are `:40-44` (min_sstable_size :40, bucket_low :42, bucket_high :44), not `:41-44`. Other citations (`SizeTieredCompactionStrategy.java:76,79,87,116,122-123,151,205-218,241,248-290`; options `:26-31,73,83-89`) match the pinned source.
- **A2.** B2c/B2f arithmetic. `floor(1 MiB * 1.3^i)`, i = 0..31, has total 14.410 GiB (not about 18) and largest 3.326 GiB (not 4.2). The default band gives 11 buckets (not 5-8) because a 1.3x step joins about three files before the next one exceeds 1.5 x the mean. B2f is replaced with model-computed numbers.
- **U1.** Unit tier also runs real sstables (the sibling pattern of `compaction-min-threshold-...`): a test class in a `copy-source.sh` tree, four tables (`nar`, `def`, `wid`, `ctl`) with `compaction` maps `{'class':'SizeTieredCompactionStrategy','min_threshold':'4','max_threshold':'32','min_sstable_size':'0','bucket_low':X,'bucket_high':Y}`, 12 flushes of `round(5000 * 1.15^i)` rows of 1 KiB random bytes (unique keys), then both the static `getBuckets` call and the real `getNextBackgroundTask`. The synthetic lists of B2c stay.
- **U2.** Positive control at the unit tier uses the real `mostInterestingBucket` through `getNextBackgroundTask` with `setCompactionThresholds(4, 4)` on the wide table (`ctl`); B2e step 3's "trimming on counts" of synthetic pairs is not possible (the method takes `SSTableReader`s).
- **U3.** Real disk at the unit tier: the three non-null tasks (wide, default, ctl) are executed, and the Data.db bytes of the table directory are sampled every 2 ms during execution; the peak minus the starting bytes is the "peak extra". A narrow-arm task is null and is not executed.
- **C1.** Cluster node: one local node on 127.0.8.1 (JMX 7180), data on tmpfs; table `ks.standard1` created by cqlsh with `compression` off, `min_threshold` 4, `max_threshold` 32, `min_sstable_size` 0, then `ALTER TABLE` to set `bucket_low`/`bucket_high` (B3b's "set with ALTER"); `compaction` map read back from `system_schema.tables` before the load; TRACE logging on `org.apache.cassandra.db.compaction` so that the "Compaction buckets are" lines show the buckets.
- **C2.** B3c replaced (see there): 12 chunks of `round(50000 * 1.15^i)` rows. Instrument checks inside the run: first chunk gives one sstable; after the 12th flush there are 12 sstables, sizes ascending, consecutive ratios between 1.10 and 1.20 (so the narrow band cannot join neighbours and the default band can), and total bytes between 100 and 800 MB.
- **C3.** B3f replaced (see there). Observables added to B3d: per compaction, the "Compacted (...) N sstables ... X bytes to Y" line of `system.log` (inputs and input bytes); peak extra disk = peak of table-directory bytes during the compaction phase minus the bytes at its start (sampled every 0.2 s); the same for Data.db only.
- **C4.** Heap: `RssAnon` of the node sampled every 0.5 s through the compaction phase; the live-heap class histogram total at the end. Peak `RssAnon` is the heap observable for B3g's last row (definition of "materially" in B3f).
- **R1 (left for stage 3).** B1 and A2 speak of "temporary disk"; at the sstable level it is the output of the chosen task, not bytes of the whole table.

Feedback (stage-4 verdicts, 2026-10-26; results: `stage4-runtime-verification/results/bucket-low-bucket-high-getBuckets-oldAverageSize--autonomous.md`): unit **Confirmed** (B2g row 1) — does not cap; cluster **Confirmed** (B3g rows 1 and 3) — does not cap. Outcome class: true negative (estimate `negative`). Unit: the largest-bucket bytes follow the band (3.326, 5.885, 14.410 GiB for narrow, default, wide on the 14.410 GiB list) and the executed tasks' peak extra disk equals their input bytes (0 / 107.7 / 154.3 MB, control `max_threshold` 4: 26.6 MB). Cluster: peak extra disk 0 / 195 MB / 330 MB for narrow / default / wide (T = 329 MB), 175 MB with `max_threshold` 4; peak `RssAnon` flat (spread 0.6%). One detail of the (replaced) B3f missed: the default arm ended with 3 sstables, not 2 (buckets [1, 5, 6]: real neighbour ratios 1.139 to 1.157 put the largest sstable just over 1.5 x the mean of its bucket); no conclusions row depends on it. The estimate is unchanged (a confirmed negative).
