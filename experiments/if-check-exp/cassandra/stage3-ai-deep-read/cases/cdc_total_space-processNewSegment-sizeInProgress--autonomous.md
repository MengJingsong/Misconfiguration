# cdc_total_space — verification solution  <!-- file: cases/cdc_total_space-processNewSegment-sizeInProgress--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java:345` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI via Agent SDK, 2026-10-25 |
| Estimate | `positive`. `cdc_total_space` bounds the CDC disk footprint (unflushed CDC-capable commit log segments plus the hard-linked segments in `cdc_raw_directory`), by rejecting CDC writes (blocking mode) or deleting the oldest `cdc_raw` links (non-blocking mode, the code at the entry pointer). It is a soft cap that can overshoot by a few segments. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `cdc_total_space` (legacy name `cdc_total_space_in_mb`).
- Kind: configuration entry. Declared at `src/java/org/apache/cassandra/config/Config.java:418-419` as `DataStorageSpec.IntMebibytesBound cdc_total_space = new IntMebibytesBound("0MiB")`, with `@Replaces(oldName = "cdc_total_space_in_mb")`. Commented in `conf/cassandra.yaml:923` (`# cdc_total_space: 4096MiB`, min unit MiB).
- Unit: MiB in the yaml; the code reads bytes through `DatabaseDescriptor.getCDCTotalSpace()` (`DatabaseDescriptor.java:4370-4373`, `conf.cdc_total_space.toBytesInLong()`).
- Default: 0 means "derive". Only when `cdc_enabled: true`, `DatabaseDescriptor.java:677-695` sets it with `calculateDefaultSpaceInMiB("cdc", cdc_raw_directory, "cdc_total_space", 4096, totalSpaceOfCdcRawVolume, 1, 8)`, i.e. min(4096 MiB, 1/8 of the cdc_raw volume), per the yaml comment (`cassandra.yaml:918-919`) and `doc/modules/cassandra/pages/managing/operating/cdc.adoc:60`.
- Setting: yaml key only, read at startup; needs a restart. No JMX setter (only `setCDCTotalSpaceInMiB` at `DatabaseDescriptor.java:4376`, annotated `@VisibleForTesting`). No `-D` override found. Only has effect if `cdc_enabled: true` (`Config.java:410`, startup-only) and the table has `cdc=true`; the CDC segment manager is chosen at `DatabaseDescriptor.java:242`.
- Related knobs used by the check: `cdc_block_writes` (`Config.java:413`, volatile, settable at runtime via `CommitLog.setCDCBlockWrites`, `CommitLog.java:460-470`, i.e. via JMX `CommitLogMBean`), `commitlog_segment_size` (`Config.java:397`, default 32MiB), `cdc_free_space_check_interval` (`Config.java:421`, default 250ms), `cdc_raw_directory` (`Config.java:417`).

**A2. What it caps.** Disk. The quantity compared is `CDCSizeTracker.sizeInProgress` (an `AtomicLong`, `CommitLogSegmentManagerCDC.java:292`): estimated 32 MiB per PERMITTED/CONTAINS unflushed segment, plus actual file sizes of segments in `cdc_raw`, periodically reset by a directory walk of `cdc_raw` (`calculateSize`, lines 407-419). It does not cap heap or off-heap.

**A3. Mechanism.**
1. Every new commit log segment calls `createSegment()` (line 237) -> `cdcSizeTracker.processNewSegment(segment)` (line 241).
2. `processNewSegment` (line 326): `allowance = getCDCTotalSpace()`, `blocking = getCDCBlockWrites()` (329-330). Under `cdcStateLock` it sets the segment FORBIDDEN if `blocking && segmentSize + sizeInProgress > allowance`, else PERMITTED (335-337). A PERMITTED segment is counted at once with `addSize(segmentSize)` (340-341), where `segmentSize` is `commitlog_segment_size`. PERMITTED segments get a hard link into `cdc_raw` (`createSegment`, 243-247).
3. **Entry pointer, line 345**: `if (!blocking && sizeInProgress.get() > allowance)` -> `bytesToFree = sizeInProgress - allowance` (347); `deleteOldLinkedCDCCommitLogSegment(bytesToFree)` (348, defined 91-131) lists `cdc_raw` valid segment files, sorts by segment id, and deletes link + `_cdc.idx` file of the oldest ones until `bytesDeleted >= bytesToFree` or it reaches the file of `allocatingFrom()` (117). It returns the byte count of the files remaining (summing `File.length()` of the retained segment files, 122); `sizeInProgress` is then set to that value (350). So in non-blocking mode the limit is enforced only at segment-creation time, by deleting unconsumed CDC data.
4. Blocking mode (the default): a FORBIDDEN segment makes `allocate` call `throwIfForbidden` (175, 183, 212-228) and throw `CDCWriteException` for mutations on CDC tables (surfaces to clients as a write failure/timeout, `ErrorMessage.java`). `permitSegmentMaybe` (195-210) re-permits when `sizeInProgress + segmentSize < cdc_total_space` after a consumer deletes files; `submitOverflowSizeRecalculation` (385-398) re-walks `cdc_raw` at most once per `cdc_free_space_check_interval` (rate limiter, 288).
5. On discard (`processDiscardedSegment`, 360-383) a CONTAINS segment is re-counted at `onDiskSize()` and the 32 MiB estimate removed; the segment's hard link stays in `cdc_raw` until a consumer (or the non-blocking trim) deletes it. A segment with no CDC data has its link deleted in `discard` (76-83).
- Overshoot / bypass paths: (a) the check is only made on segment creation, so in non-blocking mode usage can sit above the allowance for up to one segment of writes; (b) the trim never deletes the link of the current `allocatingFrom` segment or newer (117), and the newest link is counted even if over; (c) `sizeInProgress` between walks is an estimate (`defaultSegmentSize()` per segment, whereas real file length can differ, e.g. segments with `commitlog_compression`); (d) blocking mode: a FORBIDDEN segment already created stays FORBIDDEN until `permitSegmentMaybe` runs on a later `allocate`; non-CDC-table mutations are not rejected and still use commit log disk; (e) the test `CommitLogSegmentManagerCDCTest.testNonblockingShouldMaintainSteadyDiskUsage` (lines 121-139) itself only asserts `actualSize <= limit * targetFilesCount` (3x), documenting the tolerated overshoot; (f) deleting a link in non-blocking mode frees disk only if the commit log segment itself has already been discarded; otherwise the inode survives via the commitlog directory (see A4).

**A4. Other consumers.** The commit log directory itself (capped by `commitlog_total_space`, `Config.java:390`, not by this constraint) holds the same inodes as hard links while a segment is unflushed; `du` over both directories double counts unless hard links are de-duplicated. Memtables, SSTables, hints and the `_cdc.idx` index files (small; written by `CommitLogSegment.writeCDCIndexFile`, `CommitLogSegment.java:379`; counted by the directory walk but not by the line-122 remaining-size sum) are outside this constraint.

**A5. Evidence beyond the source.** In-tree only: `doc/modules/cassandra/pages/managing/operating/cdc.adoc:55-69` and warnings section; `conf/cassandra.yaml:405-431, 915-931`; unit test `test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDCTest.java`. Upstream JIRA referenced by the docs: CASSANDRA-8844, CASSANDRA-12148 (not fetched).

## B. Verification solution

**B1. Claim under test.** With `cdc_enabled: true` and a CDC table, the on-disk size of `cdc_raw` (plus CDC-counted unflushed segments) stays at or below `cdc_total_space` plus a bounded overshoot (about 1-3 segments of `commitlog_segment_size`), in non-blocking mode (oldest links deleted at line 345-354) and in blocking mode (CDC writes rejected), whereas with a much larger `cdc_total_space` the same workload makes it grow well beyond that value.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk: `rsync -a /users/jason92/cassandra-5.0.9/ /tmp/ca-unit/`; build in the copy only: `cd /tmp/ca-unit && ant jar` (and `ant build-test`). Test source: a new JUnit class in the copy, `test/unit/org/apache/cassandra/db/commitlog/CdcTotalSpaceProbeTest.java`, modelled on `CommitLogSegmentManagerCDCTest` (same `@BeforeClass`: `ServerTestUtils.daemonInitialization(); DatabaseDescriptor.setCDCEnabled(true); DatabaseDescriptor.setCDCTotalSpaceInMiB(..); CQLTester.setUpClass();`, helpers `createTableAndBulkWrite`, `updateCDCTotalSize`, `testWithNonblockingMode`, `testWithCDCSpaceInMb`). Run with `ant testsome -Dtest.name=org.apache.cassandra.db.commitlog.CdcTotalSpaceProbeTest`. Test data dirs under `/tmp/ca-unit/build/test/cassandra` (local disk, at least 5 GiB free). Add `<logger name="org.apache.cassandra.db.commitlog.CommitLogSegmentManagerCDC" level="DEBUG"/>` to the copy's `test/conf/logback-test.xml` so line 351-353 log "Freed up ... Total on-disk CDC size ... allowed CDC size".

> **Amendment 2026-10-25 (stage-4 audit, B2a/B2b/B2c/B2d/B2e; reasons from the source and the node, no reading).**
> (1) Paths: `/users/jason92/cassandra-5.0.9` and `/tmp/ca-unit` do not exist / must not be used; the run copies the pinned source with `stage4-runtime-verification/copy-source.sh ~/s4-cdc/clone` on `pc12` and builds there (`ant build-test`). The unit test class is `CdcTotalSpaceProbeTest` (harness folder `harness/cdc_total_space-processNewSegment-sizeInProgress--autonomous/`), launched by `ant testsome` with `-Dtest.jvm.args` carrying the settings; data under `~/s4-cdc/clone/build/test/cassandra` on local `/` (51 GiB free).
> (2) Segment size: the unit yaml has `commitlog_segment_size: 5MiB` (`test/conf/cassandra.yaml:10`), and `max_mutation_size` is derived from it once at start-up (`DatabaseDescriptor.java:898-899`, 2.5 MiB). With S = 5 MiB, N = 96 / 192 / 1024 MiB are 19 / 38 / 204 segments and the 12 x S = 60 MiB workload could never reach 96 MiB. The harness therefore sets `setCommitLogSegmentSize(32)` and `max_mutation_size` = 16 MiB (half a segment) itself, so S = 32 MiB as B2b says, and N = 96 / 192 / 1024 are 3 / 6 / 32 segments.
> (3) Mutation size: "S/3" is read as a payload of 11,184,810 bytes (S/3 rounded down); three of these plus headers do not fit in one 32 MiB segment, so a segment holds two. The loop attempts 37 mutations (ceil(384 MiB / 11,184,810 B); >= 12 x S attempted, about 18 segments) in every cell, **counting rejections as attempts** (blocking mode keeps attempting after the first `CDCWriteException`); sampling is after every mutation and at every segment boundary, plus a 5 ms sampler for the peak. After the loop the harness flushes the written table (`forceBlockingFlush`), waits two check intervals, then reads `updateCDCTotalSize()`, the `Files.walk` sum, `du -sb` and `du -s` (allocated) and the file listing.
> (4) Extra instruments (observation only): the Byteman rules of the earlier cdc harness (creation trace `pre`/`post`, `deleteOld`, `reject`) loaded into the unit JVM, and the DEBUG logger of B2a for line 351. Reading B2d(1) `updateCDCTotalSize()` is called only after the loop (it sleeps and recomputes the tracker), so it is not an in-loop sample; in-loop `sizeInProgress` comes from reflection.

**B2b. Knobs.** `DatabaseDescriptor.setCDCTotalSpaceInMiB(N)` for N in {96, 192, 1024}; with the default `commitlog_segment_size` of 32 MiB (test conf may differ: print `DatabaseDescriptor.getCommitLogSegmentSize()` and use it as S) these are 3, 6 and 32 segments. Mode: `CommitLog.instance.setCDCBlockWrites(false|true)`. 96 and 192 test two limits to show the bound scales with the knob; 1024 is the positive control (limit not reached).

**B2c. Workload.** `createTableAndBulkWrite(mutationSize = S/3)` style: CDC table (`WITH cdc=true`), mutations of about S/3 bytes written in a loop until at least 12*S bytes (about 384 MiB) have been written, so about 12+ segments are created, far past 96 and 192 MiB. After the loop, force segments to be discarded/flushed (`Keyspace.open(ks).getColumnFamilyStore(t).forceBlockingFlush(...)`) so links remain in `cdc_raw`. In blocking mode keep writing until a `CDCWriteException` is thrown and record how many bytes were accepted.

**B2d. Observables and instruments.** (1) `updateCDCTotalSize()` (returns `cdcSizeTracker.getAllocatedSize()` after a fresh directory walk, line 439-451), the real byte total of `cdc_raw`; (2) a direct `Files.walk` sum of `cdc_raw` regular files, in test code, as a cross-check; (3) the DEBUG log line at 351; (4) count of `CDCWriteException`s; (5) the CDC state of `allocatingFrom()`. `sizeInProgress` is private, so the estimate between walks is only observable via the log line and via reflection (`CDCSizeTracker.sizeInProgress` via `setAccessible`) if wanted. Sample after every write batch of S/3.

**B2e. Procedure.**
1. Copy tree, build (B2a), add the probe test and logback change.
2. For each (mode, N) in {non-blocking, blocking} x {96, 192, 1024}: set N and mode, run the B2c workload, sampling (1) and (2) after each batch; record max over the run and final.
3. Record the counts from (4) for blocking mode and the max accepted bytes.
4. Run the same loop on a table with `cdc=false` as a negative control.
5. Remove `/tmp/ca-unit` after saving the logs outside it.

**B2f. Predictions (S = 32 MiB).**
- Non-blocking, N=96: max measured `cdc_raw` size <= N + 3*S = 192 MiB and final <= about N + S = 128 MiB; log line 351 appears at least once with remaining size <= N + S. N=192: max <= 288 MiB. Max scales with N (difference between the two maxima about 96 MiB, within +-S).
- Blocking, N=96: `CDCWriteException` is thrown once about N - S to N MiB of CDC segments exist; `cdc_raw` size never exceeds N + S; no file is deleted by the manager (nothing is trimmed). N=192 likewise with 192.
- N=1024 (control): no trim log line and no exception; `cdc_raw` size reaches at least 12*S = 384 MiB, i.e. well above 192.
- `cdc=false` table: `cdc_raw` stays at 0 bytes. **Superseded 2026-10-25 (source, not a reading):** `createSegment` hard-links every PERMITTED segment (`CommitLogSegmentManagerCDC.java:243-247`) before it is known whether it will hold CDC data, and only `discard` removes the link of a segment that did not become CONTAINS (`:76-83`). So a non-CDC table does put links in `cdc_raw` while its segments are live. New prediction (N = 96, both modes, table with `cdc=false`, same 37 mutations): zero `CDCWriteException` in blocking mode (`Mutation.trackedByCDC()` is false, `throwIfForbidden` `:214`); peak link bytes <= N + S = 128 MiB; after the final flush and the 2-interval wait at most 2 links (<= 64 MiB) remain, against the CDC-table cell at the same N, whose links are all CONTAINS and stay (final >= N - S = 64 MiB). The control's role is therefore "the CDC table's retained footprint is CDC-attributable", not "a non-CDC table leaves cdc_raw empty".
- Segment accounting for the blocking cells (arithmetic from `:335-337`, S = 32 MiB, no consumer): with k = N / S, the counter after k segments is k x S (estimates), so the check for segment k+1 (`S + sip > N`) forbids it only if a directory walk has replaced the estimates by real bytes, which include the small `_cdc.idx` files (the walk sums every file under `cdc_raw`, `DirectorySizeCalculator`); without a walk in between it is permitted. So N = 96 permits 2 or 3 segments and forbids the next, N = 192 permits 5 or 6. Blocking final `cdc_raw` link bytes are therefore expected to be (k-1) x S or k x S: 64 or 96 MiB at N = 96, 160 or 192 MiB at N = 192 (never above N), accepted mutations 2 per permitted segment (4 to 6 and 10 to 12), rejected = 37 - accepted.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Non-blocking max size <= N + 3S for both N and the trim line logged | Claim confirmed for the mechanism at line 345 |
| Non-blocking size at N=96 and N=192 both reach 384 MiB, no trim logged | Claim refuted: line 345 not effective (or limit not read) |
| Blocking: exception raised with size <= N + S | Claim confirmed for blocking mode |
| Blocking: no exception and size >> N | Claim refuted |
| N=1024 control does not exceed 192 MiB | Workload too small; result not confirmed |
| Max size much above N + 3S (e.g. > N + 5S) | Cap leaks more than expected; report as overshoot, claim only partly holds |
| *(added 2026-10-25)* A capped cell in which the cap was never reached (blocking: no FORBIDDEN segment and no rejection; non-blocking: no `deleteOld` pass) | Not confirmed for that cell (workload too small or the knob did not take effect) |
| *(added 2026-10-25)* Reflected tracker differs from the `Files.walk` sum by more than S after the final recalculation | Counter and real resource disagree: report the gap; the verdict is read from the real bytes |
| *(added 2026-10-25)* `cdc=false` table, blocking: any `CDCWriteException`; or non-blocking/blocking: more than 2 links left after flush | Control row: the non-CDC table is counted or rejected like a CDC one; report as an additional finding, the cap's rows above are unaffected |

(Estimate is positive, so the negative-estimate rows are not needed.)

**B2h. Controls.** N=1024 run (limit not reached) rules out the workload being too small; `cdc=false` table rules out commit log segments being counted independent of CDC tables; the directory-walk sum vs `updateCDCTotalSize()` rules out an instrument bug; disk: check no consumer deletes files (nothing else touches `cdc_raw`).

### B3. Cluster tier

**B3a. Environment and build.** One node suffices (a second node only adds replication of the same mutations). Copy the tree to local disk, `rsync -a /users/jason92/cassandra-5.0.9/ /data/local/ca-node/` (a local disk with at least 20 GiB free, not shared storage), `ant jar`. Use JDK 11. Configuration changes in `/data/local/ca-node/conf/cassandra.yaml`: `cdc_enabled: true`; `cdc_raw_directory: /data/local/ca-node/data/cdc_raw` (same volume as commitlog); `commitlog_directory`, `data_file_directories`, `hints_directory` under `/data/local/ca-node/data`; `cdc_free_space_check_interval: 250ms` (default); `commitlog_segment_size: 32MiB` (default); `commitlog_total_space: 2048MiB` so that the commit log dir doesn't hide the effect; `commitlog_sync: periodic` (default); `cdc_block_writes` as per run; `cdc_total_space` as per run. Heap: `MAX_HEAP_SIZE=1G` `HEAP_NEWSIZE=256M` in `conf/jvm11-server.options`/env.

> **Amendment 2026-10-25 (stage-4 audit, B3a to B3e; reasons from the source and the node, no reading).**
> (1) Paths: no `/data/local`; the node is `pc12`, working tree from `copy-source.sh` at `~/s4-cdc/clone` (built with `ant build-test`), node directories under `~/s4-cdc/run` on local `/` (commit log and `cdc_raw` on the same filesystem, as hard links need). `bin/cassandra -R` is not needed (not root): `bin/cassandra -p <pidfile>`. `ulimit -n 100000` in the starting shell. The node is stopped with `nodetool stopdaemon`, by PID if that fails. Only `MAX_HEAP_SIZE=1G` is set; `HEAP_NEWSIZE` is ignored under G1 (`cassandra-env.sh`), so it is omitted.
> (2) Added run **R6 = blocking, 256 MiB** (B3b). Reason: the claim covers blocking mode and the README's group B requires that a confirmation shows the ceiling following the knob; B3b as filed has only one capped blocking value (128). R6's prediction is below.
> (3) Workload (B3c), made exact: tables `k.t` (`cdc = true`) and `k.tp` (`cdc = false`) with `id bigint PRIMARY KEY, v blob`, written by one `cassandra-stress user profile=... "ops(insert=1)" n=32768 no-warmup -rate threads=8 throttle=200/s -errors retries=0 ignore` (64 KiB blob = one row; 32768 rows = 2 GiB; a fresh stress run per batch would restart its key sequence and overwrite the same keys), with `nodetool flush k t` (`tp` for the control) every 10 s, i.e. after about every 2000 rows = 128 MiB (the 16 batches of the filed text), and a last flush 30 s after the stress ends. The 200 rows/s throttle (12.5 MiB/s, about 10 s per batch) keeps rejected writes from flooding the log (rejections are counted as attempts) and gives the 50 ms sampler resolution; the cap check itself is made at segment creation and does not depend on the rate. Flushing does **not** remove the link of a segment that held CDC data (`discard` `:76-83` deletes only non-CONTAINS links).
> (4) Instruments (observation only, added to B3d): the Byteman rules of the earlier cdc harness loaded at node start (`pre`/`post`/`deleteOld`/`reject` trace to a file), the 50 ms `cdc_raw` sampler, a 2 s `du -sb` and `du -s --block-size=1` (apparent and allocated bytes) loop for `cdc_raw`, the commit log directory and data, and `system_views.settings` for the read-back of `cdc_total_space`, `cdc_block_writes`, `cdc_enabled`, `commitlog_segment_size`. The size is read in apparent bytes of the `cdc_raw` files (hard links); the allocated-bytes figure is recorded beside it because a link shares its inode with the commit log copy until that copy is discarded (A4).
> (5) B3e step for R4/R6 (writes resume): delete the **two** oldest `.log` links with their `_cdc.idx` files, then probe a one-row CDC insert every 200 ms for up to 60 s. Reason (source): `permitSegmentMaybe` re-permits only when `sizeInProgress + S < cdc_total_space` strictly (`:201`) and a FORBIDDEN segment has no link of its own (`:243-247` links only PERMITTED ones), so at an exact multiple of S one deletion leaves `(k-1)S + S + index bytes`, not below the cap. The "1 s" of B3f is replaced by "within 10 s" (the walk is rate limited to one per 250 ms and each `cqlsh` probe starts in about half a second); timing is not part of the claim.
> (6) Numbers: R3 and R5 "about 2 GiB" means at least 1.8 GiB of `.log` links at the end (2,048 MiB written is about 64 segments of 32 MiB, less any in flight).

**B3b. Knobs.** `cdc_total_space`: 128MiB (4 segments), 256MiB (8), 4096MiB (control, effectively unlimited for this workload). `cdc_block_writes`: false (runs R1-R3), true (R4-R5; startup value or JMX `CommitLog` MBean attribute `CDCBlockWrites`). Restart between values, since `cdc_total_space` is startup-only.

**B3c. Workload.** `cqlsh`: `CREATE KEYSPACE k WITH replication={'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE k.t (id bigint PRIMARY KEY, v blob) WITH cdc=true;` Then `cassandra-stress` (from `tools/bin`) or a short loop issuing about 64 KiB blob inserts: write 2 GiB total (about 64 segments of 32 MiB, far beyond 128, 256 MiB), in 16 batches of 128 MiB; after each batch run `nodetool flush k t` so segments become discard-eligible and move to `cdc_raw`-only links. Total time a few minutes. Repeat the same total on a `cdc=false` table for a negative control.

**B3d. Observables and instruments.** (1) `du -sb --apparent-size` on `cdc_raw` alone, and `find cdc_raw -name '*.log' -printf '%s %n %p\n'` (link count `%n`, 2 = still in commitlog dir too); to de-duplicate use `du -s` on `cdc_raw` first, then commitlog dir with `--exclude` or via inode listing (`find -printf '%i'` + `sort -u`); (2) `df`-independent: `ls -l` file count in `cdc_raw`, sampled every 2 s by a shell loop writing to a log outside the node dirs; (3) `system.log` lines "Rejecting mutation to keyspace" (blocking) and "Freed up ... bytes after deleting the oldest CDC commit log segments" (DEBUG logger `org.apache.cassandra.db.commitlog.CommitLogSegmentManagerCDC` set via `nodetool setlogginglevel`); (4) client errors (stress write failures / timeouts). Not directly observable: `sizeInProgress`; use the log messages.

**B3e. Procedure.**
1. Prepare the copy and yaml (B3a); create empty data dirs.
2. For each run R1 (non-blocking, 128MiB), R2 (non-blocking, 256MiB), R3 (non-blocking, 4096MiB), R4 (blocking, 128MiB), R5 (blocking, 4096MiB): wipe data dirs, set yaml, start `bin/cassandra -R` (record pid), wait for "Starting listening for CQL clients", `nodetool setlogginglevel org.apache.cassandra.db.commitlog.CommitLogSegmentManagerCDC DEBUG`, create schema, start the sampling loop, run the B3c workload, then wait 30 s and take a final reading.
3. Stop the node (`kill` the pid, wait for exit), stop the sampling loop, copy logs aside, wipe data dirs.
4. Repeat R1 with the `cdc=false` table.

**B3f. Predictions (S = 32 MiB).**
- R1: max `cdc_raw` bytes <= 128 + 3*32 = 224 MiB; typical steady state 128-160 MiB; "Freed up" lines in the debug log; file count in `cdc_raw` stabilises at about 4-6 `.log` files. Client writes succeed throughout.
- R2: max <= 256 + 96 = 352 MiB; steady about 256-290 MiB. Steady-state difference R2 - R1 about 128 MiB (+-S).
- R3: `cdc_raw` grows to about 2 GiB (all 64 segments retained, minus the in-flight ones); no "Freed up" lines.
- R4: once `cdc_raw` plus CDC-counted unflushed segments reaches about 128 MiB, writes fail with the "Rejecting mutation ... Free up space" error (client sees WriteFailure/timeout); `cdc_raw` bytes <= 128 + S and stop growing; after deleting the files in `cdc_raw` by hand and 1 s, writes resume.
- R5: no rejection; `cdc_raw` about 2 GiB.
- `cdc=false` run: `cdc_raw` empty; no cap logs. **Superseded 2026-10-25 (source, as in B2f):** non-CDC segments are hard-linked at creation and unlinked at discard. New prediction (non-blocking, cap 128 MiB, table `k.tp`, same 2 GiB in 16 flushed batches): no rejection; peak link bytes <= cap + S = 160 MiB; after the final flush at most 2 links (<= 64 MiB) remain, while R1 (CDC table) ends with 4 to 5 links (>= 96 MiB).
- **R6 (added 2026-10-25):** blocking, cap 256 MiB: writes fail with "Rejecting mutation" once about 8 segments exist; link bytes <= 256 + S = 288 MiB and stop growing (expected 256 MiB, 8 links); the plateau of R6 minus that of R4 is about 128 MiB (+-S); after deleting two links, writes resume.
- R4 plateau arithmetic (from `:335-337`, no consumer): at cap 128 MiB the 5th segment is forbidden after 4 are permitted (4 x 32 = 128, then 128 + 32 > 128), so the plateau is expected at 3 or 4 links (96 or 128 MiB; 3 when a walk added the index-file bytes before the check, as in B2f) and never above 128 MiB + S = 160 MiB; the counter (estimated 32 MiB per segment) can sit above the file bytes because files are counted by `File.length()` at the walk.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| R1/R2 plateau at about the limit (within +3S), R3 reaches about 2 GiB | Claim confirmed |
| R1 and R2 plateau, but at a value not scaling with the limit | Another bound is acting; the claim is not shown for this knob |
| R1 grows with writes like R3 (>> 224 MiB) | Claim refuted (non-blocking cap not effective) |
| R4 rejects writes at about the limit and `cdc_raw` is flat | Claim confirmed for blocking mode |
| R4 never rejects and `cdc_raw` > 128 + S | Claim refuted for blocking mode |
| R3 does not grow well past 256 MiB | Control failed (workload too small / files already flushed away); not confirmed |
| Files in R1 vanish from `cdc_raw` but `du` of the data volume still grows | Links removed but inodes held by commitlog dir; account with inode de-duplication (A3 f) |
| *(added 2026-10-25)* R4 and R6 plateaus (blocking) both at or below cap + S, rejections in both, and R6 - R4 about 128 MiB (+-S) | Blocking ceiling follows the knob; claim confirmed for blocking mode (needed with the R4 row, the README requires two capped values) |
| *(added 2026-10-25)* R4/R6 after two links are deleted: writes resume within 60 s | Disallow state is released by the counter falling (`permitSegmentMaybe`); not resuming within 60 s is reported as a defect of the release step, not as a refutation |
| *(added 2026-10-25)* `k.tp` (non-CDC) run: any rejection, or more than 2 links after the final flush | Control row: the non-CDC table is treated like a CDC one; report as an additional finding, the cap's rows are unaffected |
| *(added 2026-10-25)* A capped run in which the cap was never reached (blocking: no FORBIDDEN segment; non-blocking: no `deleteOld` pass) | Not confirmed for that run |

**B3h. Controls.** R3 and R5 (large limit) are the positive control: same workload without a binding cap; `cdc=false` table shows the footprint is CDC-attributable; dedup by inode avoids double counting; the second set of runs with a different `cdc_total_space` rules out a fixed bound unrelated to the knob.

**B4. Risks and cleanup.** Disk: unit tier writes up to a few hundred MiB under `/tmp/ca-unit`; cluster tier up to about 2.2 GiB of cdc_raw plus up to 2 GiB commit log per run (commit log capped by `commitlog_total_space: 2048MiB`), all on local disk; wipe data dirs after each run. Ensure the volume holding the node has at least 20 GiB free and is not shared. Processes: record every pid (JVM, `ant`, sampling loop, stress), kill them, and check with `ps -u $USER -o pid,cmd | grep -E 'cassandra|ant|stress|sleep'` that none remain. Never build or write inside `/users/jason92/cassandra-5.0.9`. Remove `~/s4-cdc/clone` build outputs of the run, `~/s4-cdc/run` and the unit test data at the end (logs stay in `~/s4-cdc/logs`).

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 242, 670-705, 4336-4385)
- src/java/org/apache/cassandra/config/Config.java (grep of cdc and commitlog entries)
- src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java (CDCState, setCDCState, getCDCFile, writeCDCIndexFile)
- src/java/org/apache/cassandra/db/commitlog/MemoryMappedSegment.java (onDiskSize)
- src/java/org/apache/cassandra/db/commitlog/CommitLog.java (setCDCBlockWrites, ensureCDCEnabled)
- src/java/org/apache/cassandra/utils/DirectorySizeCalculator.java
- src/java/org/apache/cassandra/db/Mutation.java (trackedByCDC)
- src/java/org/apache/cassandra/io/util/FileUtils.java (createHardLink)
- conf/cassandra.yaml (lines 405-431, 915-931)
- doc/modules/cassandra/pages/managing/operating/cdc.adoc
- test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDCTest.java

## D. Stage-4 feedback

Stage 4, 2026-10-25, `pc12`, results in `stage4-runtime-verification/results/cdc_total_space-processNewSegment-sizeInProgress--autonomous.md` (uncommitted; this file is untracked). Audit sha256 frozen before any reading: `8cf71e6b116796c2ce3b0fcdf25ffc40d7ade516eb51859519468feb4039bb7b`; hash of B2f+B2g+B3f+B3g text `4d8d5fe5027e56fb4147a0a698499bdd5558573ff3a6fe0d72eb45c72dbcd725`.

- **Verdict:** unit **Confirmed, caps (soft)**; cluster **Confirmed, caps (soft)**; estimate `positive`, outcome class **true positive**. Non-blocking: `cdc_raw` held at the cap (unit 128 / 192-224 MiB at N = 96 / 192; cluster 128 and 224-256 MiB at caps 128 / 256) by 8 to 42 `deleteOld` passes per cell; blocking: it stopped at or just under the cap (unit 96-128 and 192; cluster 128 and 224 MiB) with FORBIDDEN segments and rejected writes, and writes resumed 1.35 s after two links were deleted; the same workload with the cap out of reach filled 640 MiB (unit) and 2112 MiB (cluster).
- **Amendments (2026-10-25, before any reading):** B2/B3 blocks: wrong paths, 5 MiB unit segments (harness sets 32 MiB), exact S/3 payload and 37 attempts, `cdc=false` prediction replaced (the table is linked at creation and unlinked at discard, `:243-247`, `:76-83`: it is not empty but transient, <= N + S, <= 2 links after flush), segment-accounting bullets, R6 (blocking 256 MiB) added, two links deleted to release a blocked writer (`:201` strict `<`), one stress run with a flush every 10 s, added conclusions rows.
- **Sub-predictions missed:** (1) B2f accounting for blocking N = 96: 128 MiB / 8 accepted in 2 of 3 unit repeats where (k-1)S or kS = 64 or 96 MiB / 4 to 6 was filed (the headline "never above N + S" held); the trace shows the tracker had lost the estimate of an earlier segment in those JVMs (test restarts the commit log), not seen on the node; (2) B3f R2 steady "256 to 290 MiB": 224 MiB in one repeat, the cap sawtooths between 7 and 8 links (224 / 256). Neither changes a row.
- **Findings for Target 3 / stage 3 notes:** the cap is soft by up to one segment, and the budget is consumed transiently by non-CDC writers (every PERMITTED segment is linked at creation); the apparent bytes of `cdc_raw` exceed the allocated bytes (sparse mapped segments) and the commit log directory holds its own copy of unflushed segments, so the cap is not a bound on disk blocks.
- **Not tested:** the derived default value, a real consumer, unthrottled writes, commit log compression, replication.
