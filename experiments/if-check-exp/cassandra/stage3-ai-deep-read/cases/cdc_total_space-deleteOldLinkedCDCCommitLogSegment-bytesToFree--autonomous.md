# cdc_total_space — verification solution  <!-- file: cases/cdc_total_space-deleteOldLinkedCDCCommitLogSegment-bytesToFree--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java:93` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI (Agent SDK), 2026-10-22 |
| Estimate | `positive`. Disk used by the CDC directory (`cdc_raw`) is held at about `cdc_total_space` by two mechanisms: rejecting CDC writes (blocking mode) or deleting the oldest hard-linked segments (non-blocking mode). The overshoot is bounded by a small number of 32 MiB segments plus the tracker's lag. |
| Ground | — (positive; caveats in A3/A4: the bound is soft, and it covers only the `cdc_raw` directory, not the commit log directory) |

## A. Constraint trace

**A1. The constraint.** `cdc_total_space` is a configuration entry (YAML). It was previously `cdc_total_space_in_mb`, kept as a deprecated alias through `@Replaces`.
- Declared at `Config.java:418-419` as `DataStorageSpec.IntMebibytesBound cdc_total_space = new ...("0MiB")`.
- Unit: MiB in the YAML, converted to bytes at use by `DatabaseDescriptor.getCDCTotalSpace()` (`DatabaseDescriptor.java:4370-4372`, `toBytesInLong()`).
- Default: the declared default 0 is replaced when `cdc_enabled` is true (`DatabaseDescriptor.java:677-695`). The value becomes `min(4096 MiB, 1/8 of the total space of the filesystem holding cdc_raw_directory)`, computed by `calculateDefaultSpaceInMiB("cdc", ..., 4096, totalSpace, 1, 8)`. The documented default is in `conf/cassandra.yaml:915-923`. I did not read `calculateDefaultSpaceInMiB`, so the exact fraction/clamping is unverified.
- Settable: the YAML key `cdc_total_space: <n>MiB`, which needs a restart. It is not in the JMX `CommitLogMBean` (only `cdc_block_writes` and `cdc_on_repair_enabled` are, `CommitLog.java:454-485`). `DatabaseDescriptor.setCDCTotalSpaceInMiB` (`:4376`) is a test-only setter.
- Gated by `cdc_enabled` (`Config.java:410`, default false). `cdc_enabled` selects `CommitLogSegmentManagerCDC` and needs a restart. Mode switch `cdc_block_writes` (`Config.java:413`, default true) is runtime-settable through JMX.
- The target line (`:93`) is the first guard in `deleteOldLinkedCDCCommitLogSegment(long bytesToFree)`. The operand `bytesToFree` is the overage `sizeInProgress - cdc_total_space` (`:347`).

**A2. What it caps.** Disk. The resource is the total on-disk size of the files in `cdc_raw_directory`, which are hard links to commit log segments plus their `_cdc.idx` index files. The code compares the tracker's `sizeInProgress` (an AtomicLong, `:292`) against `getCDCTotalSpace()` (`:329`, `:345`, and `:201` in `permitSegmentMaybe`). `sizeInProgress` has two parts:
- an estimate: `commitlog_segment_size` added per PERMITTED segment (`:341`), swapped for the real `onDiskSize()` on discard if the segment CONTAINS CDC data (`:371-378`);
- ground truth, which overwrites the estimate: a periodic directory walk of `cdc_raw` (`calculateSize`, `:407-414`, using `DirectorySizeCalculator`, `utils/DirectorySizeCalculator.java:48`, which sums `attrs.size()`).

**A3. Mechanism.**
1. Each new segment calls `createSegment` (`:237-249`), which calls `processNewSegment` (`:326`).
2. Blocking mode (`cdc_block_writes=true`): if `segmentSize + sizeInProgress > allowance`, the segment is marked FORBIDDEN (`:335-337`). Otherwise it is PERMITTED, its size is added (`:340-341`) and a hard link is made in `cdc_raw` (`:243-247`).
3. On the write path, `allocate` calls `throwIfForbidden` (`:175`, `:212-227`). A CDC-tracked mutation into a FORBIDDEN segment triggers `submitOverflowSizeRecalculation` and throws `CDCWriteException`. Non-CDC mutations still succeed.
4. A FORBIDDEN segment is promoted to PERMITTED by `permitSegmentMaybe` (`:195-210`) when blocking is off, or when `sizeInProgress + segmentSize < allowance` (after a consumer deleted files and the recalculation caught up).
5. Non-blocking mode (`cdc_block_writes=false`): segments are always PERMITTED (`:335`). If `sizeInProgress > allowance` (`:345`), then `bytesToFree = sizeInProgress - allowance` (`:347`) and `deleteOldLinkedCDCCommitLogSegment(bytesToFree)` runs (`:348`).
6. Inside `deleteOldLinkedCDCCommitLogSegment` (`:91-131`):
   - `bytesToFree <= 0` returns 0 (`:93-94`).
   - It lists valid commit-log-named files in `cdc_raw` (`:98`) and sorts them by segment id, oldest first (`:104-107`).
   - It deletes the link plus its index file (`:127`, `deleteCDCFiles`, `:133-148`) until `bytesDeleted >= bytesToFree` or the file is the currently-allocating segment's link (`:117`).
   - It returns the size of the remaining `.log` files (`:122`, `:130`).
7. The caller then sets `sizeInProgress = remainingSize` (`:349-350`).

Outcomes and gaps:
- **Reached, blocking:** CDC writes fail with `CDCWriteException`; data is not lost, the client gets an error.
- **Reached, non-blocking:** the oldest un-consumed CDC segments are deleted, which loses CDC data silently (`logger.debug`, `:351`).
- **Soft bound, estimate vs truth:** the check is only against `sizeInProgress`, which is an estimate between directory walks. The walk is rate-limited to one per `cdc_free_space_check_interval` (default 250 ms, `:288`; `Config.java:421`) and is dropped if one is already queued (`DiscardPolicy`, `:310`). Overshoot of roughly one segment (32 MiB default, `yaml:660`) is expected. The estimate also charges a full segment size even when the segment is partially written.
- **Non-blocking never deletes the active segment:** the `:117` stop means the loop never removes the link of `allocatingFrom()`. If the allowance is smaller than one segment, usage stays above the cap by design.
- **Line 93, race:** `:345` and `:347` read `sizeInProgress` separately, so a concurrent decrement can make `bytesToFree <= 0`. The method then returns 0, and `:349-350` sets `sizeInProgress` to 0 even though files remain. The tracker briefly undercounts until the next walk (`:357`) corrects it. This is a transient, self-healing undercount, not a correctness failure of the cap.
- **Remaining-size accounting:** `bytesRemaining` (`:122`) sums only commit-log-named files, so it omits `_cdc.idx` files. This is another small estimate error that the next walk corrects.
- **Bypass:** blocking mode at `:335` uses `>` on `segmentSize + sizeInProgress`, so usage can end at about allowance. Replay hard-links add size through `addCDCSize` (`:274`) without any check.
- **When CDC is off:** `cdc_total_space` does nothing. A non-CDC segment manager is used, and `cdc_raw` is not created or managed.

**A4. Other consumers.** The same disk is also used by:
- the commit log directory (`commitlog_directory`, bounded by `commitlog_total_space`, a separate constraint). The CDC hard link and the commit log file are the same inode until both names are deleted, so deleting a `cdc_raw` link frees blocks only once the commit log copy is also discarded;
- data directories, hints and saved caches, if they share the filesystem;
- any file placed in `cdc_raw` by the external consumer. Foreign files count in the walk (`:412`) but only valid commit-log-named files are deletable (`:98`).

**A5. Evidence beyond the source.**
- Existing test `test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDCTest.java` (`testNonblockingShouldMaintainSteadyDiskUsage` at `:122`, `testCDCWriteFailure` at `:81`). I only listed its method names and did not read it in detail. The names suggest it checks the same property.
- `conf/cassandra.yaml:915-923` (documentation of the key).
- No external web sources used.

## B. Verification solution

**B1. Claim under test.** With CDC enabled, the total bytes in `cdc_raw_directory` stay at most `cdc_total_space` plus a small bounded slack (at most a few `commitlog_segment_size` segments), in both blocking mode (writes are rejected) and non-blocking mode (oldest links are deleted), with no consumer deleting files. If the files in `cdc_raw` exceed that bound for sustained periods, the claim is wrong.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Work in a local clone of the tag at `/tmp/<user>/cass-unit` (never in the shared clone). Run `ant build-test` once. Use a new test class `test/unit/.../CdcCapProbeTest.java` in the local clone, modelled on `CommitLogSegmentManagerCDCTest` (its setup configures `DatabaseDescriptor.setCDCEnabled(true)` and `CommitLog` with a CDC-tracked table). Run it with `ant testsome -Dtest.name=CdcCapProbeTest`. Point `cdc_raw_directory`, `commitlog_directory` and the data directories at local disk (`/tmp/<user>/cdcunit/...`, at least 2 GiB free). Default JVM options of the test target.

**B2b. Knobs.**
- `DatabaseDescriptor.setCDCTotalSpaceInMiB(n)` with n in {64, 128, 256, 512}. These are multiples of the 32 MiB segment: 2, 4, 8 and 16 segments.
- `CommitLog.instance.setCDCBlockWrites(true|false)`.
- `commitlog_segment_size` fixed at 32 MiB (the test default). Optionally reduce it to 8 MiB for finer resolution, by building the test config with `DatabaseDescriptor.setCommitLogSegmentSize`. This is a test setter, so confirm it exists before use. **[Runbook-defect fix 2026-10-22, found in the instrument check before any reading, leaves B2f/B2g unchanged: the unit yaml's segment size is 5 MiB, not 32 MiB, and `max_mutation_size` is derived from it once at start-up (2.5 MiB; `DatabaseDescriptor.java:898-899`), so the setter alone leaves the 8 MiB mutations of B2c over the limit. The harness test sets the segment size to 32 MiB with `setCommitLogSegmentSize(32)` and `getRawConfig().max_mutation_size` to 16 MiB, so the cell has the node's geometry; the setter exists.]**
- `cdc_free_space_check_interval` default 250 ms, with `updateCDCTotalSize()` sleeping `interval + 50 ms` twice (`:441-446`).

**B2c. Workload.** Insert mutations on a CDC-enabled table (`WITH cdc = true`) through `CommitLog.instance.add` or the test helper `bulkWrite` (`CommitLogSegmentManagerCDCTest.java:454`). Use large mutations of about 1/2 `max_mutation_size`, so each segment fills quickly. Write at least `3 x cdc_total_space` of CDC data in total. For n=128 MiB that is 384 MiB, or 12 segments. Nobody deletes files in `cdc_raw`. Arithmetic: with no consumer, `sizeInProgress` grows 32 MiB per segment, so it crosses 128 MiB by segment 5 and the limit is reached and passed.

**B2d. Observables and instruments.**
1. `cdcMgr.updateCDCTotalSize()` (`:439`): the tracker's value after a fresh walk. It is the check's own operand.
2. An independent `Files.walkFileTree` or `du -sb` over `cdc_raw`, sampled after every segment boundary (the test thread polls `CommitLog.instance.segmentManager.allocatingFrom()` identity).
3. `CommitLogSegment.getCDCState()` of the current segment.
4. Count of `CDCWriteException`s thrown by the writer.
5. The `Rejecting mutation ...` WARN, and in non-blocking mode the DEBUG line `Freed up ...` (enable DEBUG on `CommitLogSegmentManagerCDC`).
6. Directory listing of `cdc_raw` (which segment ids remain).
The test cannot observe the true OS block allocation of the hard-linked inodes beyond what `du` reports; `du -sb` (apparent bytes) is used and `du --block-size=1` (allocated) is recorded too.

**B2e. Procedure.**
1. Clone the tag to `/tmp/<user>/cass-unit`, add the probe test, `ant build-test`.
2. For each (mode, n): start from an empty `cdc_raw`, set the knobs, call `updateCDCTotalSize()` to initialise.
3. Write CDC mutations until `3 x n` MiB has been attempted, catching `CDCWriteException` and counting it. After each segment boundary, record the tracker value and the `du -sb` value.
4. After the writes, wait `2 x interval`, call `updateCDCTotalSize()` and record the final tracker value and `du` value.
5. Repeat each cell 3 times.
6. Clean `cdc_raw`, the commit log directory and the data directory between runs. Confirm no JVM is left (`pgrep -f CdcCapProbeTest`).

**B2f. Predictions.** (stated before any run)
- Blocking, n = 64..512 MiB: the final `du -sb` of `cdc_raw` is at most `n + 1 segment` (32 MiB), plus index files (small). Tracker equals `du` within one segment after the final walk. `CDCWriteException` count is greater than 0 for every n, and the writes after the cap is hit are rejected. Usage is flat in the attempted volume once the cap is hit.
- Non-blocking: no `CDCWriteException`. Peak `du` over the run is at most `n + about 2 segments`, and the final `du` is at most `n + 1 segment`. The oldest segment ids are gone from the listing. Usage tracks n (it doubles when n doubles) rather than the volume written.
- Line 93: for n so large that `sizeInProgress` never exceeds the cap, `deleteOldLinkedCDCCommitLogSegment` is never called (no `Freed up` DEBUG lines).
- Dose-response: the final `du` rises roughly linearly with n, with slope near 1 and an intercept within one segment.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Final and peak `du` within `n + about 2 segments` in both modes, tracker agrees with `du` within one segment | Claim holds at unit level: the cap bounds `cdc_raw`. |
| `du` grows with the volume written, past `n + 2 segments`, for sustained time | Claim wrong: the cap does not bound `cdc_raw` (or the tracker undercounts persistently). |
| Blocking mode with zero `CDCWriteException` while `du` exceeds `n + segment` | Claim wrong in blocking mode (the enforcement fails). |
| Non-blocking mode with `Freed up` lines absent although `du` exceeds `n` | Deletion path not engaged; the claim is wrong or the limit was not reached. Check that the writes were CDC-tracked. |
| Tracker value sits at 0 right after a `Freed up` line while files remain in the directory | The `:93` zero-return race (A3) occurred: transient undercount, which the next walk should fix within 2 intervals. If it persists across walks, the claim is wrong. |
| Total written less than `n` | Limit not reached; the run is not a test of the claim. |

**B2h. Controls.**
- Positive control: n large (4096 MiB) with the same volume, in both modes. `du` must be at least the volume written (no cap binding) and no more than the volume plus the per-segment slack, and `deleteOldLinkedCDCCommitLogSegment` must not be called, which shows the writer produces enough CDC data to exceed the smaller caps. **[Amendment 2026-10-22, step 0 audit, independent of any reading: the filed text said `du` "must equal the volume written". Files in `cdc_raw` are whole 32 MiB segments, and a segment holding 8 MiB mutations carries at most three of them (24 MiB), so `du` is the number of segments times 32 MiB, never exactly the volume. The row is stated as an inequality with that granularity; the control's meaning is unchanged. Rows are 8 MiB (1/2 of `max_mutation_size`, 16 MiB at 32 MiB segments), as B2c says.]**
- CDC-off control: `cdc_enabled=false` with the same workload; `cdc_raw` stays empty, showing the growth comes from the CDC path.
- Non-CDC table writes of the same size: they must never produce `CDCWriteException` or `cdc_raw` growth.
- Re-measure the time between segments to rule out walk-rate artefacts: repeat with a 1 s wait before each sample.

### B3. Cluster tier

**B3a. Environment and build.** One node first (a second node optional for replication, not needed). JDK 11, Ant, with a local clone of the tag (`ant jar`) under `/tmp/<user>/cass-node`. In `conf/cassandra.yaml`:
- `cdc_enabled: true`
- `cdc_raw_directory: /tmp/<user>/cdc/cdc_raw`
- `commitlog_directory: /tmp/<user>/cdc/commitlog`
- `data_file_directories: [/tmp/<user>/cdc/data]`
- `hints_directory` and `saved_caches_directory` also under `/tmp/<user>/cdc`
- `commitlog_segment_size: 32MiB` (default)
- `commitlog_total_space` left at default, but see B4 for disk sizing
- `cdc_free_space_check_interval: 250ms`
- `cdc_total_space: 256MiB` (varied)
- JVM heap fixed (`MAX_HEAP_SIZE=2G`, `HEAP_NEWSIZE=400M`) so memory does not interfere.
The local disk must be a separate filesystem or directory with at least 8 GiB free.

**B3b. Knobs.**
- `cdc_total_space`: 128 MiB, 256 MiB, 512 MiB (YAML, restart per value).
- `cdc_block_writes`: true and false (set live through JMX `org.apache.cassandra.db:type=Commitlog`, attribute `CDCBlockWrites`; or in YAML for the first start).
- Optionally a very small `cdc_total_space` (16 MiB, less than one segment) as a boundary case for the `:117` rule.
- Workload table with `cdc = true`.

**B3c. Workload.** `cassandra-stress` (from the same build) or CQL inserts through the normal client path. Table: `CREATE TABLE ks.t (k int PRIMARY KEY, v blob) WITH cdc = true`. Insert 64 KiB blob values at a rate that writes about `3 x cdc_total_space` of commit log in about 2 minutes. For 256 MiB that is 768 MiB, or about 12000 inserts of 64 KiB. Commit log mode must make CDC data hit disk quickly; use the default periodic sync (10 s). Keep the node running with no CDC consumer, so `cdc_raw` is never drained. Also keep memtable flushing rare (large `memtable_heap_space`); run `nodetool flush` only at the end. **[Amendment 2026-10-22, step 0 audit, from source and independent of any reading: the filed text said a flush would remove the link and the cap would not be reached. `discard` (`CommitLogSegmentManagerCDC.java:66-83`) deletes the `cdc_raw` link only for a segment that did not contain CDC data (`getCDCState() != CONTAINS`); a segment with CDC data keeps its link after a flush. So flushing, including the forced flushes that `commitlog_total_space: 1024MiB` causes once more than 1 GiB of segments is dirty (B4), does not by itself shrink `cdc_raw`. The workload and the instruction are kept; the reason is corrected.]**

**B3d. Observables and instruments.**
- `du -sb /tmp/<user>/cdc/cdc_raw` and `ls -l` every 2 s (the actual resource).
- `df` of the filesystem, to confirm disk use.
- Client-side error counts (`WriteTimeout`/`WriteFailure` from `CDCWriteException`; in 5.0 it is reported as a write failure) from the stress output.
- Node log: `Rejecting mutation to keyspace ...` (WARN), and DEBUG `Freed up ...` after `nodetool setlogginglevel org.apache.cassandra.db.commitlog.CommitLogSegmentManagerCDC DEBUG`.
- JMX `Commitlog` MBean: `CDCBlockWrites`, `ActiveSegmentCompressionRatios`, etc. (`CommitLogMBean`).
- `du` of the commit log directory (separate resource).
Not directly observable: the tracker's `sizeInProgress` (private). Infer it from the log message `Total CDC bytes on disk is ...`.

**B3e. Procedure.**
1. Clone, `ant jar`, copy the config. Create the directories on local disk.
2. For each (mode, `cdc_total_space`): wipe the directories, start the node (`bin/cassandra -f` under a wrapper that records the PID), wait for ready.
3. Create the CDC table. Start the samplers (`du` loop in the background).
4. Run the workload for 2 minutes (or until `3 x cap` attempted).
5. Record the peak and final size of `cdc_raw`, the listing of segment ids, and the error counts.
6. For the blocking runs: after the writes stop, delete the two oldest links and their `_cdc.idx` files by hand (simulating a consumer), and run a few more inserts. Check that writes resume once the tracker catches up (a few seconds), and that `cdc_raw` returns to at most the cap. **[Amendment 2026-10-22, step 0 audit, from source and independent of any reading: the filed text said "the oldest link" (one). `permitSegmentMaybe` (`CommitLogSegmentManagerCDC.java:195-210`) promotes only when `sizeInProgress + segmentSize < allowance` (strict), and the forbidden segment has no link of its own (`createSegment`, `:243-247`). At an exact multiple of the segment size (128, 256, 512 MiB are all multiples of 32 MiB) the tracker holds about k x S plus index bytes, so after one deletion `(k-1) x S + S + index bytes` is not below the cap and the writer is correctly not released. Two deletions are needed. Deleting one is a different experiment, so the step now says two.]**
7. For the non-blocking runs: switch the mode live with `CDCBlockWrites=false` while blocked, and check that writes resume and old segments are deleted.
8. Stop the node (`nodetool drain`, then kill by PID), confirm no Cassandra process remains (`pgrep -f CassandraDaemon`), remove the directories.

**B3f. Predictions.** (stated before any run)
- Blocking: peak `du` of `cdc_raw` at most `cap + about 2 segments`; client sees write failures for CDC inserts once the cap is hit; the `Rejecting mutation` WARN appears (rate limited to once every 10 s). Final size flat at roughly the cap while the attempted volume triples.
- Non-blocking: no write failures; `du` oscillates at roughly the cap, peak at most `cap + 2 segments`; the oldest segment ids disappear; the surviving files are the newest.
- Dose-response: the plateau scales with `cdc_total_space` (128, 256, 512 MiB gives plateaus about 128..192, 256..320, 512..576 MiB).
- Switching blocking to non-blocking resumes writes without restart.
- Boundary case (16 MiB cap, less than one segment): blocking mode rejects CDC writes after the first segments; non-blocking mode keeps at least the active segment, so `cdc_raw` holds about one segment (about 32 MiB) and exceeds the cap by design.
- The commit log directory is not bounded by `cdc_total_space`: its size depends on `commitlog_total_space` and flushes.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Plateau at about the cap (within 2 segments), scaling with the knob, in both modes | Claim confirmed: the limit governs real disk in `cdc_raw`. |
| `du` of `cdc_raw` keeps growing with the attempted volume | Claim wrong: the cap does not bound actual usage. |
| Blocking mode: no write failures although `cdc_raw` is above the cap + 2 segments | Claim wrong in blocking mode. |
| Non-blocking mode: usage above the cap + 2 segments with no deletions in the log | Deletion path failed or never reached; check that DEBUG is on and that `cdc = true` data is in the segments. |
| Writes do not resume after the manual deletion of the two oldest links, beyond about 3 walk intervals (*amended 2026-10-22: "two"; see B3e step 6*) | Tracker or promotion path problem (`permitSegmentMaybe`, `:195-210`). |
| `cdc_raw` never reaches the cap | The limit was not reached (e.g. the writes did not carry CDC data, or the volume was too small); not a test of the claim. *(Amended 2026-10-22: a flush alone does not remove the links of CDC-containing segments; see B3c.)* |
| 16 MiB case exceeds the cap in non-blocking mode | Expected (the `:117` rule keeps the active segment); not a refutation. |

**B3h. Controls.**
- Large cap (4096 MiB) with the same workload: `cdc_raw` grows with the volume written (no cap binding), proving the workload can fill the directory.
- `cdc = false` table, same workload: `cdc_raw` stays empty and no write failures occur.
- `cdc_enabled: false` node: `cdc_raw` absent; the commit log behaves as usual.
- Repeat each cell twice to see run-to-run variance.

**B4. Risks and cleanup.**
- Disk: each run writes at most about `3 x 512 MiB` of CDC data, plus up to `commitlog_total_space` of commit log segments (default is the min of 8 GiB and 1/4 of the filesystem, so set `commitlog_total_space: 1024MiB` for the runs) and the data files. Use a local disk with at least 8 GiB free. Never point any directory at shared storage (NFS or `/proj`).
- Processes: stop the node (`nodetool drain`, kill PID), confirm with `pgrep -f CassandraDaemon`, and confirm no `ant` or JUnit JVMs remain (`pgrep -f junit`).
- Cleanup: remove `/tmp/<user>/cdc*` and the cloned trees when finished. Do not build in or write to the shared source clone.
- Risk: enabling DEBUG logging produces many lines; return the level to INFO afterwards.

## C. Sources read

- `/proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/playbook-autonomous.md`
- `/proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/_TEMPLATE-autonomous.md`
- `src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java`
- `src/java/org/apache/cassandra/config/Config.java` (lines 405-422)
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java` (lines 675-700, grep of 4336-4383)
- `src/java/org/apache/cassandra/db/commitlog/CommitLog.java` (lines 450-480)
- `conf/cassandra.yaml` (lines 410-430, 915-932, grep for `commitlog_segment_size`)
- `test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDCTest.java` (grep of method names only)
- `src/java/org/apache/cassandra/utils/DirectorySizeCalculator.java` (grep only)
- grep over `src/` and `conf/` for CDC-related names

## D. Stage-4 feedback

**2026-10-22, stage 4 run 1 (both tiers), results `stage4-runtime-verification/results/cdc_total_space-deleteOldLinkedCDCCommitLogSegment-bytesToFree--autonomous.md`; nothing committed.**

- **Unit tier: B2g row 1, Confirmed — caps.** 30 JVMs (3 repeats of blocking and non-blocking at n = 64, 128, 256, 512 MiB, plus controls). Blocking: final = peak du = n or n − 1 segment (224 and 480 MiB in 3 of 12 cells), every CDC write after the cap rejected, `deleteOld` never called. Non-blocking: no rejection, final du n to n + 1 segment, peak n + 1 segment, 6 to 28 `deleteOld` passes, oldest links gone. Tracker = du after the final walk. The 4096 MiB control grew to 544 MiB for 384 MiB written, with no `deleteOld`.
- **Cluster tier: B3g row 1, Confirmed — caps.** One node, 22 cells, 2 repeats. Plateaus 96 / 256 / 512 MiB (blocking) and 128 / 256 / 512 (non-blocking) at caps 128 / 256 / 512; the 16 MiB boundary 0 (blocking) and 64 MiB (non-blocking); the 4096 MiB control 1,600 MiB for 1,536 MiB written. Identical in both repeats. The release and live-switch steps worked (first CDC write accepted about 1.3 s after two links were deleted, about 0.55 s after the switch).
- **Sub-predictions missed (the matched rows still hold):** B3f's blocking plateau for 128 MiB (`128..192`; observed 96 MiB, k − 1 segments); B3f's 16 MiB non-blocking value (about 32 MiB; observed 64 MiB, two links). **Control that did not hold:** B2h/B3h "a non-CDC table leaves `cdc_raw` empty" — a non-CDC workload made up to cap + 1 segment of links (160 MiB at a 128 MiB cap, then deleted on discard), because `processNewSegment` links every permitted segment before it knows whether it will hold CDC data; **Not confirmed (no matching row)**.
- **Amendments made at the audit (dated 2026-10-22, before any reading):** B3e step 6 and its B3g row (delete two oldest links, not one: strict `<` in `permitSegmentMaybe`), B2h (large-cap control `du` ≥ volume, not equal), B3c and a B3g row (a flush keeps the link of a CDC-containing segment), B2b (unit yaml has 5 MiB segments and 2.5 MiB `max_mutation_size`). Recommendations left for stage 3: `HEAP_NEWSIZE` has no effect with G1 (B3a); a per-step "establishes" line; no driven default-value arm.
- **A3 text:** the sentence on the `:93` race (tracker set to 0 while files remain) was not observed in any traced unit or cluster cell; the only return of 0 was the first pass at a 16 MiB cap, with no link yet on disk.
