# max_space_usable_for_compactions_in_percentage — verification solution  <!-- file: cases/max-space-usable-for-compactions-in-percentage.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/Directories.java:551` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-sonnet-5, 2.1.294 (Claude Code), 2026-10-08, attempt 1 |

## A. Constraint trace

**A1. The constraint.** `max_space_usable_for_compactions_in_percentage` — a YAML configuration entry. First declared at `src/java/org/apache/cassandra/config/Config.java:344`:
```
public volatile Double max_space_usable_for_compactions_in_percentage = .95;
```
with the preceding comment "fraction of free disk space available for compaction after min free space is subtracted" (`Config.java:343`). Unit: dimensionless fraction in `[0,1]`. Default `0.95`, validated at startup in `DatabaseDescriptor.java:1016-1017` (`ConfigurationException` thrown if `<0` or `>1`). Read through `DatabaseDescriptor.getMaxSpaceForCompactionsPerDrive()` (`DatabaseDescriptor.java:2579-2582`), written through `DatabaseDescriptor.setMaxSpaceForCompactionsPerDrive(double)` (`DatabaseDescriptor.java:2584-2587`), the latter used only by unit tests, never wired to any JMX/MBean/nodetool entry point. It is set exclusively via the `cassandra.yaml` key of the same name (bound by field name through Cassandra's standard snakeyaml-based config loader); since the setter is not exposed over JMX, **changing it requires a node restart**.

**A2. What it caps.** Disk space (not heap/off-heap) — specifically the additional bytes that **new compaction-output writes and incoming streamed sstables** are allowed to consume on a given `java.nio.file.FileStore` (the OS filesystem/mount backing one or more Cassandra data directories), on top of whatever other compactions/streams are already writing there. The quantity compared is `availableForCompaction` (the capped budget) vs. `toWrite.getValue()` (requested bytes for that FileStore).

**A3. Mechanism.**
1. `Directories.getAvailableSpaceForCompactions(FileStore)` (`Directories.java:563-569`) computes the budget: `availableSpace = FileStore.getUsableSpace() - DatabaseDescriptor.getMinFreeSpacePerDriveInBytes()`, then returns `max(0, round(availableSpace * getMaxSpaceForCompactionsPerDrive()))`.
2. `Directories.hasDiskSpaceForCompactionsAndStreams(Map<FileStore,Long>)` (`Directories.java:544-561`) compares that budget against the requested write size per FileStore; if `availableForCompaction < toWrite.getValue()` for any FileStore it logs a WARN (`Directories.java:553-556`) and the overall result is `false`.
3. Two call sites feed this: `CompactionTask.buildCompactionCandidatesForAvailableDiskSpace` (`CompactionTask.java:384-457`), called before a compaction runs, and `StreamSession.checkDiskSpace`/`checkAvailableDiskSpaceAndCompactions` (`StreamSession.java:901-951`, `StreamSession.java:856-873`), called before accepting an incoming stream.
4. **Outcome on compaction**: if the check fails, `CompactionTask.reduceScopeForLimitedSpace` (`CompactionTask.java:98-115`) drops the largest sstable from the candidate set and the check is retried; if no more sstables can be dropped, the task throws `RuntimeException` and the compaction is aborted (`CompactionTask.java:434-442`), unless all remaining sstables are fully expired (partial-compaction fallback, `CompactionTask.java:427-432`).
5. **Outcome on streaming**: `checkAvailableDiskSpaceAndCompactions` throws `RuntimeException`, failing the stream session (`StreamSession.java:871-872`).
6. **Bypass paths**: (a) per-table JMX flag `ColumnFamilyStoreMBean.compactionDiskSpaceCheck(false)` (`ColumnFamilyStore.java:2081-2091`, default `true`) skips the whole check, but only when `compactionType == OperationType.COMPACTION` (`CompactionTask.java:386`) — validation/scrub/etc. compactions remain gated. (b) Global yaml/JMX flag `skip_stream_disk_space_check` (`Config.java:701`, `StorageServiceMBean.java:1285-1286`) skips the streaming-side check entirely.
7. **Overshoot path**: ordinary (non-compaction) sstable writes — notably memtable flush — pick a directory through `Directories.getWriteableLocation(long)` → `DataDirectory.getAvailableSpace()` (`Directories.java:781-785`), which subtracts only `min_free_space_per_drive` and **does not** multiply by `max_space_usable_for_compactions_in_percentage`. So the percentage knob never limits flush-driven disk growth, only the compaction/stream paths.

**A4. Other consumers.** Memtable flush output (path above, uncapped by this knob), commit log segments, hints, snapshots (`auto_snapshot`/manual), saved caches, secondary-index (SAI/SASI) build output, and any other table sharing the same FileStore — each table's compaction check is computed independently against the FileStore's live `getUsableSpace()`, so concurrent compactions across tables can race for the same headroom (no reservation/locking).

**A5. Evidence beyond the source.** Unit tests `DirectoriesTest.testFreeCompactionSpace` (`test/unit/org/apache/cassandra/db/DirectoriesTest.java:902-924`) and `testHasAvailableSpace`/`testHasAvailableSpaceSumming` (`:977-1105`) exercise exactly this arithmetic with a `FakeFileStore` stub (`:1134-1155`); `StreamSessionTest.java:85` and `PartialCompactionsTest.java:222` exercise the same knob for the streaming and partial-compaction paths respectively. `CHANGES.txt:4181` (CASSANDRA-8562, "Check for available disk space before starting a compaction") and `CHANGES.txt:1966` (CASSANDRA-13068, "Improve calculation of available disk space for compaction") document the lineage of the surrounding mechanism; no CHANGES.txt/NEWS.txt entry names `max_space_usable_for_compactions_in_percentage` specifically, so its introduction isn't attributable to a ticket number from the sources read.

## B. Verification solution

**B1. Claim under test.** "Raising or lowering `max_space_usable_for_compactions_in_percentage` proportionally raises or lowers the byte budget `Directories.getAvailableSpaceForCompactions` returns for a FileStore, and that budget is what gates whether a compaction's output (or an incoming stream) is allowed to proceed on that FileStore — i.e. it bounds disk growth caused by compaction/streaming, but not disk growth caused by memtable flush or other writers." The unit tier tests the first half (the operand/arithmetic and the gate decision); the cluster tier tests the second half (real disk behavior, including the flush overshoot).

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Clone the pinned tag to **local disk**, e.g. `cd ~/work && git clone <local-path-to-shared-clone> cassandra-5.0.9-unit && cd cassandra-5.0.9-unit && git checkout cassandra-5.0.9` (never build inside the shared clone). Add one new test file in this local clone only: `test/unit/org/apache/cassandra/db/MaxCompactionSpaceOperandTest.java`, in package `org.apache.cassandra.db` so it can reuse `DirectoriesTest.FakeFileStore` (`DirectoriesTest.java:1134-1155`). Build/run: `ant jar` then `ant test -Dtest.name=MaxCompactionSpaceOperandTest`. No special JVM options needed.

**B2b. Knobs.** `DatabaseDescriptor.setMaxSpaceForCompactionsPerDrive(double)` set in-process to `1.0` (no-cap control), `0.95` (shipped default), `0.5`, and `0.0`. `DatabaseDescriptor.setMinFreeSpacePerDriveInMebibytes(0)` held fixed across all four values to isolate the percentage term (mirrors `DirectoriesTest.testFreeCompactionSpace`).

**B2c. Workload.** One `FakeFileStore` with `usableSpace = 1_000_000_000` bytes (1 GB), fixed across all four percentage values. For each value compute `expected = Math.round(1_000_000_000 * pct)` and call `Directories.hasDiskSpaceForCompactionsAndStreams(Map.of(fs, expected - 1))` and `...(Map.of(fs, expected + 1))` — one request just under, one just over the computed budget, driving the operand across the limit exactly as `DirectoriesTest.testHasAvailableSpace` does (`:1000-1016`).

**B2d. Observables and instruments.** (1) The `long` returned by `Directories.getAvailableSpaceForCompactions(fs)` — direct read of the operand. (2) The `boolean` returned by `hasDiskSpaceForCompactionsAndStreams`. (3) WARN/DEBUG log lines captured with a logback `ListAppender` attached to `Directories.class`'s logger (pattern already used at `DirectoriesTest.java:937-949`), to corroborate the exact byte figures logged at `Directories.java:553-556`. Cannot be observed in this tier: any real OS disk usage — `FakeFileStore` never touches the filesystem, so this tier cannot show whether the cap governs actual bytes on disk (that is the cluster tier's job).

**B2e. Procedure.**
1. Clone tag to local disk, checkout `cassandra-5.0.9`.
2. Add `MaxCompactionSpaceOperandTest.java` with four `@Test` methods (or one parameterized loop) implementing B2b/B2c, saving/restoring `DatabaseDescriptor` state in a `finally` block as the existing tests do.
3. `ant jar`
4. `ant test -Dtest.name=MaxCompactionSpaceOperandTest`
5. Inspect JUnit output and the captured log lines.

**B2f. Predictions.** With `usableSpace=1e9`, `minFree=0`:

| pct | expected `getAvailableSpaceForCompactions` | `hasDiskSpaceForCompactionsAndStreams(expected-1)` | `hasDiskSpaceForCompactionsAndStreams(expected+1)` |
|---|---|---|---|
| 1.0 | 1,000,000,000 | true | false |
| 0.95 | 950,000,000 | true | false |
| 0.5 | 500,000,000 | true | false |
| 0.0 | 0 | true (0 < 0 is false, request=−1 clamped — use request=0 instead, which must return true) | false (any request ≥1 must return false) |

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `getAvailableSpaceForCompactions` equals `round(usableSpace*pct)` for all four values | confirms A1/A3 arithmetic as traced |
| `getAvailableSpaceForCompactions` is flat/unchanged across pct values | contradicts the claim — the knob is not actually read by this path |
| `hasDiskSpaceForCompactionsAndStreams(expected-1)==true` and `(expected+1)==false` for every pct>0 | confirms the gate enforces the computed budget at the boundary |
| `hasDiskSpaceForCompactionsAndStreams` returns `true` for a request above `expected` | contradicts the claim — the check does not actually gate on this budget |
| Log line shows a budget value inconsistent with `round(usableSpace*pct)` | contradicts the traced arithmetic |

**B2h. Controls.** Only `pct` varies between the four sub-runs; `usableSpace` and `minFree` are held constant. The `pct=1.0` run is the "no cap" baseline — if behavior there differs from the others only in scale (not in kind), that isolates the percentage as the sole varying cause. Repeating with a second `usableSpace` (e.g. 10,000,000 bytes) and checking the budget scales linearly rules out a hidden additive constant or floor other than `min_free_space_per_drive` (held at 0 here, so irrelevant).

### B3. Cluster tier

**B3a. Environment and build.** One Linux node (JDK 11). Clone the tag to local disk (not the shared clone), e.g. `/local/disk/cassandra-5.0.9-cluster`, `git checkout cassandra-5.0.9`, build with `ant jar`. Create a **size-bounded local filesystem** dedicated to Cassandra's single data directory so `FileStore.getUsableSpace()` is small and controllable rather than the shared disk's real (large, shared) free space:
```
fallocate -l 2G /local/disk/cass-data.img
mkfs.ext4 /local/disk/cass-data.img
mkdir -p /local/disk/cass-data
sudo mount -o loop /local/disk/cass-data.img /local/disk/cass-data
```
In `cassandra.yaml`: `data_file_directories: [/local/disk/cass-data/data]`; `commitlog_directory`, `hints_directory`, `saved_caches_directory` on a separate local path (not the loop mount, per the shared-storage-care instructions, and not shared storage). Set `max_space_usable_for_compactions_in_percentage: 1.0` for the baseline run and `0.5` for the boundary run — each requires editing the yaml and **restarting** the node (confirmed in A1: no JMX setter exists). Set `min_free_space_per_drive: 10MiB` (fixed across both runs). Leave `compaction_disk_space_check` (per-table JMX default `true`) and `skip_stream_disk_space_check: false` at their defaults in both runs (controls). Start with `bin/cassandra -f`.

**B3b. Knobs.** `max_space_usable_for_compactions_in_percentage` ∈ `{1.0, 0.5}`, each via a full yaml edit + restart. Everything else (schema, dataset, `min_free_space_per_drive`, compaction strategy = default `SizeTieredCompactionStrategy`) held identical between the two runs.

**B3c. Workload.** Data dir capacity ≈ 2 GiB; after `min_free_space_per_drive=10MiB`, usable ≈ 2038 MiB. At pct=1.0, budget ≈ 2038 MiB; at pct=0.5, budget ≈ 1019 MiB. Create one keyspace/table (`RF=1`), disable autocompaction (`nodetool disableautocompaction ks.tbl`), and load ~1.5 GiB of raw data with `cassandra-stress write n=<rows> -schema keyspace=ks ... -node 127.0.0.1` sized so on-disk sstables total ≈1.5 GiB (verify with `du -sh /local/disk/cass-data`). Then trigger a single deterministic compaction event with `nodetool compact ks tbl`, which (STCS, default) needs roughly the size of the input sstables again as write headroom (~1.5 GiB) — this fits under the pct=1.0 budget (2038 MiB) but exceeds the pct=0.5 budget (1019 MiB), isolating the knob's effect. Duration: data load + compaction should complete within a few minutes given the small dataset.

**B3d. Observables and instruments.** `du -sh /local/disk/cass-data/data` and `df -h /local/disk/cass-data` sampled every 2s in a loop during `nodetool compact`; `nodetool compactionstats` and `nodetool tpstats` polled alongside; `grep -E "Not enough space for compaction|Reducing scope|FileStore .* has only" /local/disk/.../logs/system.log` after the run. Cannot be observed directly: the in-process percentage arithmetic (that's B2's job) — here only the externally visible effect (compaction completes/aborts/partial, and final/peak disk usage) is observed.

**B3e. Procedure.**
1. Build node as in B3a with `max_space_usable_for_compactions_in_percentage: 1.0`; start `bin/cassandra -f`.
2. Create schema, `nodetool disableautocompaction`, load ~1.5 GiB with `cassandra-stress`, confirm size via `du -sh`.
3. Start disk-sampling loop (`while true; do date; du -sh data; df -h mountpoint; sleep 2; done >> sample1.log &`).
4. Run `nodetool compact ks tbl`; wait for completion; stop sampling; grep logs.
5. Stop node; wipe data dir (`rm -rf /local/disk/cass-data/data/*`, keep the mount); edit yaml to `pct=0.5`; restart; repeat steps 2-4 with the same dataset size (sample2.log, logs2).
6. Compare.

**B3f. Predictions.**

| Knob | Predicted outcome |
|---|---|
| pct=1.0 | `nodetool compact` completes; no "Not enough space"/"Reducing scope" lines in the log; peak `du -sh` during compaction ≈ 2×1.5 GiB momentarily (old+new sstables) up to ≈2038 MiB headroom, settling to ≈1.5 GiB after old sstables are removed |
| pct=0.5 | log shows ≥1 "Not enough space for compaction" and/or "Reducing scope" WARN line; `nodetool compact` either partially compacts (drops largest sstable repeatedly) leaving some originals un-merged, or throws (visible as an error in the nodetool output / log), and peak additional disk growth attributable to this compaction stays ≤ ~1019 MiB rather than reaching ~1.5 GiB |

A result showing pct=0.5 completing the full compaction identically to pct=1.0, with no log warnings and no reduced/aborted scope, would contradict the claim that this knob governs real disk behavior.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| pct=0.5 run shows "Not enough space"/"Reducing scope" in log, pct=1.0 run does not | confirms the knob gates real compaction writes as traced |
| Both runs behave identically (no warnings either way) | contradicts the claim — knob has no observable effect on disk behavior |
| pct=0.5 run aborts/reduces but disk usage still grows past ~1019 MiB from this compaction | contradicts the claim that the budget bounds compaction-driven growth |
| Memtable flush (before any compaction) grows the data dir past the pct-based budget while compaction is still disabled | confirms A3's overshoot finding — flush is ungated by this knob |

**B3h. Controls.** Identical schema, dataset, `min_free_space_per_drive`, and default (enabled) disk-space-check flags across both runs; only `max_space_usable_for_compactions_in_percentage` changes. Wipe the data directory and repeat the load between runs so pre-existing sstable layout cannot explain a difference. Keep `nodetool disableautocompaction` until the deliberate `nodetool compact` call so no background minor compaction interferes with the single measured event. Optionally repeat each run once more to rule out timing flakiness.

**B4. Risks and cleanup.** All building happens in a local clone, never in the shared source tree. Data/commitlog/hints live on local disk, bounded by the 2 GiB loop image (not shared storage); confirm free space on the host before `fallocate`. After each run: stop Cassandra (`kill <pid>`; verify with `ps -ef | grep CassandraDaemon` that nothing remains), `umount /local/disk/cass-data`, `rm /local/disk/cass-data.img`, remove the local build clone and any stress-generated data. No change is made outside the node(s) created for this test.

## C. Paths read

src/java/org/apache/cassandra/db/Directories.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java
src/java/org/apache/cassandra/config/Config.java
src/java/org/apache/cassandra/db/compaction/CompactionTask.java
src/java/org/apache/cassandra/streaming/StreamSession.java
src/java/org/apache/cassandra/db/ColumnFamilyStore.java
src/java/org/apache/cassandra/db/ColumnFamilyStoreMBean.java
src/java/org/apache/cassandra/service/StorageServiceMBean.java
src/java/org/apache/cassandra/service/StorageService.java
test/unit/org/apache/cassandra/db/DirectoriesTest.java
conf/cassandra.yaml
CHANGES.txt
NEWS.txt
