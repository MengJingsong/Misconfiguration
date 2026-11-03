# cdc_total_space (default derivation in applySimpleConfig) — verification solution  <!-- file: cases/cdc_total_space-applySimpleConfig-cdc_total_space--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:684`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L684) (`684#1`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5), Claude Code (CLI version not obtainable: `claude --version` failed inside the sandbox), 2026-10-24, band D triage |
| Estimate | `positive`: line 684 replaces a 0 value with `min(4096 MiB, total space of the cdc_raw volume / 8)`; the resulting value is the CDC disk allowance that `CommitLogSegmentManagerCDC` compares against tracked CDC bytes, forbidding new CDC segments (writes to CDC tables rejected) in blocking mode or deleting the oldest CDC segments in non-blocking mode. Granularity is one commit-log segment, so overshoot up to about one segment is expected. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `cdc_total_space`, configuration entry ([`Config.java:418-419`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L418-L419), `IntMebibytesBound`, default `0MiB`, legacy `cdc_total_space_in_mb`), commented at `conf/cassandra.yaml:923`. Only applied if `cdc_enabled: true` ([`DatabaseDescriptor.java:677`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L677), yaml default false at `conf/cassandra.yaml:413`). When 0: `calculateDefaultSpaceInMiB("cdc", cdc_raw_directory, …, 4096, totalSpace, 1, 8)` ([`DatabaseDescriptor.java:684-695`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L684-L695), helper `:1147-1162`) returns `min(4096, totalMiB/8)` and warns when the volume is small. Getter `getCDCTotalSpace()` in bytes (`:4370-4373`); only a `@VisibleForTesting` setter (`:4376-4379`), so production changes need a restart (it is re-read at every segment event, so the test setter takes effect immediately).


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** Disk used by CDC commit-log hard links in `cdc_raw` plus in-flight CDC-containing segments. Operand: `cdcSizeTracker.sizeInProgress` (+ segment size) vs `allowance`.

**A3. Mechanism.**
1. New segment: `processNewSegment` sets the segment `FORBIDDEN` if `cdc_block_writes` and `segmentSize + sizeInProgress > allowance`, else `PERMITTED` and adds `segmentSize` ([`CommitLogSegmentManagerCDC.java:326-342`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L326-L342)).
2. Non-blocking mode: if `sizeInProgress > allowance`, deletes oldest linked CDC segments (`:345-354`).
3. A mutation to a CDC table landing in a `FORBIDDEN` segment throws `CDCWriteException` and logs "Rejecting mutation to keyspace …" (`:212-225`).
4. A forbidden segment is permitted again once `sizeInProgress + segmentSize < allowance` (e.g. consumer deleted files) (`:195-210`); size recalculation over `cdc_raw` runs at `cdc_free_space_check_interval` ([`Config.java:420-421`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L420-L421); tracker `:286-430`).
- Overshoot: size is charged per segment (`commitlog_segment_size`, 32 MiB by default, `conf/cassandra.yaml:660`), and the check is `>` on the projected size, so on-disk CDC can reach allowance (rounded to segments) plus the segment currently being written; file deletion by the consumer is external.

**A4. Other consumers.** Commit log itself (`commitlog_total_space`), data directories, hints. The CDC allowance does not bound files the consumer copies elsewhere.

**A5. Evidence beyond the source.** Comments citing CASSANDRA-10013/10199 (`DatabaseDescriptor.java:687`); `test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDCTest.java` (`testCDCWriteFailure` `:81`, `testNonblockingShouldMaintainSteadyDiskUsage` `:122`).

## B. Verification solution

**B1. Claim under test.** With `cdc_enabled: true`, total bytes in `cdc_raw` stay ≤ `cdc_total_space` + one commit-log segment; in blocking mode writes to a CDC table are then rejected, in non-blocking mode old CDC files are deleted; with `cdc_total_space: 0MiB` the effective allowance equals `min(4096 MiB, cdc_raw volume size / 8)`.

### B2. Unit tier

**B2a. Environment and build.** Local clone `/local/c509`, JDK 11, `ant jar build-test`. New test `test/unit/org/apache/cassandra/db/commitlog/CDCAllowanceTest.java` extending `CQLTester` with the same setup as `CommitLogSegmentManagerCDCTest` (`cdc_enabled`, `@BeforeClass`), run with `ant testsome -Dtest.name=org.apache.cassandra.db.commitlog.CDCAllowanceTest` (or `ant test-cdc` targets if preferred). Commit log segment size set to 1 MiB in the test's config for fast filling.

**Amendment 2026-10-24 (step-0 audit, Claude Opus 5.5) — B2a/B2b, how the test is built and the third value.** The test is `CDCAllowanceTest` in package `org.apache.cassandra.db.commitlog`, one JVM per scenario (`DatabaseDescriptor.daemonInitialization()` runs once per JVM), settings as system properties via `-Dtest.jvm.args`: `stage4.cdc.scenario` = `block` / `nonblock` / `ctl-plain` / `ctl-1024` / `helper`, `stage4.cdc.s` (MiB). S = 1 MiB is set with `DatabaseDescriptor.setCommitLogSegmentSize(1)` (`DatabaseDescriptor.java:2887`) followed by `CommitLog.instance.stopUnsafe(true)` and `start()`, after `cdc_raw` is emptied. Knob values s ∈ {8, **16**, 32} MiB in both modes (16 added: group A asks for three values; the default cannot be set at the unit tier and is covered by the helper). `calculateDefaultSpaceInMiB` is package-private in `org.apache.cassandra.config`, so the helper scenario calls it by reflection. Reason: B2a/B2b did not say how S is set or how the helper is reached from another package; two values are fewer than group A asks.

**B2b. Knobs.** `DatabaseDescriptor.setCDCTotalSpaceInMiB(s)` for s ∈ {8, 32}; `DatabaseDescriptor.setCDCBlockWrites(true/false)`. Separately, call `DatabaseDescriptor.calculateDefaultSpaceInMiB("cdc", "/x", "cdc_total_space", 4096, totalBytes, 1, 8)` (package-private static) with totalBytes ∈ {4 GiB, 100 GiB}.

**B2c. Workload.** `CREATE TABLE … WITH cdc=true`, insert rows with 64 KiB blobs until either `CDCWriteException` (blocking) or 4×s MiB written (non-blocking); call `CommitLog.instance.forceRecycleAllSegments()` / `sync` periodically so segments are linked into `cdc_raw`.

**Amendment 2026-10-24 (step-0 audit, Claude Opus 5.5) — B2c, exact workload.** Rows of 64 KiB random blobs (`RowUpdateBuilder`, as the upstream test) into `CREATE TABLE … (k int PRIMARY KEY, v blob) WITH cdc=true`; `CommitLog.instance.sync(true)` after every row; **no `forceRecycleAllSegments()` during the workload**: hard links are made when a segment is created (`CommitLogSegmentManagerCDC.java:236-249`), so the call B2c gives as the reason is not needed, and a forced recycle would add partly filled linked segments, which moves the bytes written at the first rejection. Stop conditions: blocking at the first `CDCWriteException` or at 4·s MiB written (then "no rejection" is a reading); non-blocking at 4·s MiB. Reason: "periodically" was not exact and its premise does not hold in this source.

**B2d. Observables and instruments.** `((CommitLogSegmentManagerCDC) CommitLog.instance.segmentManager).updateCDCTotalSize()` (as used in the existing test) and `FileUtils.folderSize(new File(DatabaseDescriptor.getCDCLogLocation()))` after each 1 MiB written; exception type.

**Amendment 2026-10-24 (step-0 audit, Claude Opus 5.5) — B2d, sampling.** After every row: number and apparent bytes of `CommitLog-*.log` links in `cdc_raw`, and of `*_cdc.idx` files, **separately** (an index file holds a few bytes of text; the bound below is on link bytes); `updateCDCTotalSize()` (it sleeps about 2 × 300 ms) after every 16 rows (1 MiB) as written; the set of link names, so a deleted link is seen (direct evidence of the non-blocking deletion). Reason: B2d did not separate index bytes from link bytes, and gave no observable for deletion.

**B2e. Procedure.** For each s and mode: reset `cdc_raw`, run the workload, record max folder size and the bytes written at first rejection.

**B2f. Predictions.** Blocking: first `CDCWriteException` after ≈ s MiB written; max `cdc_raw` size ≤ s + 1 MiB. Non-blocking: no exception; folder size stays ≤ s + 1 MiB while 4·s MiB written. Default helper: 4 GiB → 512; 100 GiB → 4096.

**Amendment 2026-10-24 (step-0 audit, Claude Opus 5.5) — B2f, tolerances from the source.** Links are made at segment creation, including the segment prepared ahead, and a segment is refused when `S + counter > A` (`:335-337`), so at the first rejection L ∈ {k − 1, k, k + 1} links with k = ⌊s/S⌋ (k − 1 at an exact multiple when index bytes tip it; k + 1 when the counter is stale), and the two newest are the current (partly filled) and the prepared (empty) segment. Hence, with S = 1 MiB: **blocking** — the first `CDCWriteException` comes with rows accepted × 64 KiB in [s − 4, s + 1] MiB; max link bytes ≤ s + 1 MiB at every sample. **Non-blocking** — no exception; max link bytes ≤ s + 1 MiB at every sample; at least one link name deleted. **Helper** — exactly 512 for 4 GiB and 4096 for 100 GiB. Reason: "≈ s" and "near s" were not numbers a reading could contradict.

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| sizes ≤ s + segment, rejection/deletion near s | claim confirmed |
| folder size grows past s + 2 segments | cap not binding (claim wrong) |
| default helper result ≠ min(4096, total/8) | default derivation differs from trace |

**Amendment 2026-10-24 (step-0 audit, Claude Opus 5.5) — B2g, rows added; the three rows above are unchanged.** Row 1 needs every amended B2f item for the scenario (in blocking mode the exception is the direct disallow evidence; in non-blocking mode a deleted link). Added rows: (4) max link bytes in (s + 1, s + 2] MiB with the rejection or deletion present → **Not confirmed**: the cap binds, with more overshoot than predicted. (5) blocking: first rejection with accepted bytes below s − 4 MiB → **Not confirmed**: a cap that does not follow the knob as predicted. (6) blocking: no exception within 4·s MiB and link bytes ≤ s + 2 MiB → **Not confirmed**: rejection path not reached. (7) non-blocking: any `CDCWriteException` → **Refuted** for the non-blocking clause. (8) non-blocking: no link deleted → **Invalid**: limit not reached. (9) a control (B2h) fails → **Invalid**. **Tier verdict:** Confirmed if all six scenarios match row 1, the helper is exact and both controls hold; Refuted if any scenario matches row 2 or 7 or the helper differs (row 3); otherwise the weakest matched row. Reason: outcomes between the confirm and refute rows had no row.

**B2h. Controls.** Same workload on a table with `cdc=false`: no rejection, `cdc_raw` stays empty while commit log grows; s = 1024 with the same volume: no rejection (limit not reached), showing rejection is driven by the allowance.

**Amendment 2026-10-24 (step-0 audit, Claude Opus 5.5) — B2h, control expectation corrected from the source.** `cdc=false` control (s = 8, blocking, 4·8 = 32 MiB written): no `CDCWriteException`; `cdc_raw` is **not** expected to stay empty while writing — every PERMITTED segment is hard-linked at creation whatever its contents (`CommitLogSegmentManagerCDC.java:241-247`) and the link is deleted when a segment without CDC data is discarded (`:75-80`) — so after `forceRecycleAllSegments()` and `awaitManagementTasksCompletion()` at the end, ≤ 2 links remain. s = 1024 control: no exception with 128 MiB written (4 × the largest s). Reason: "cdc_raw stays empty" contradicts the cited source; the control's purpose (rejection comes from CDC tracking and from the allowance) is unchanged.

### B3. Cluster tier

**B3a. Environment and build.** One node from `/local/c509`, `MAX_HEAP_SIZE=2G`, all dirs under `/local/c509-node` (local disk, ≥ 20 GB free), `cdc_enabled: true`, `cdc_raw_directory: /local/c509-node/cdc_raw`, `commitlog_segment_size: 32MiB`, `cdc_free_space_check_interval: 250ms`.

**Amendment 2026-10-24 (step-0 audit, Claude Opus 5.5) — B3a, this machine.** Per `environment-advisor.md`: clone `$W/cassandra-run6` (`W=~/Library/Caches/stage4`) in place of `/local/c509`; all node directories under `$W/node-cdc` on the internal SSD (APFS, 460 GiB total, about 156 GiB free); `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` (`cassandra-env.sh` needs both). The yaml lines of B3a are kept. A writable fixed-size volume is not available on this machine (a mounted disk image is not writable from the session), so `cdc_raw` is on the SSD as B3a says. Reason: the paths and the heap pair were not runnable here as written.

**B3b. Knobs.** `cdc_total_space` ∈ {`256MiB`, `1024MiB`, `0MiB` (default)}; `cdc_block_writes` ∈ {`true`, `false`}. Restart per value.

**B3c. Workload.** `CREATE KEYSPACE ks WITH replication={'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.c (k uuid PRIMARY KEY, v blob) WITH cdc=true;` then `cassandra-stress user profile=cdc.yaml ops(insert=1) n=200000 -rate threads=16` with 16 KiB blobs (≈3.2 GB, > 3× the largest explicit knob). No CDC consumer runs, so nothing is deleted externally.

**Amendment 2026-10-24 (step-0 audit, Claude Opus 5.5) — B3b/B3c, exact runs and workload.** Six arms, one node start each: `cdc_total_space` ∈ {256MiB, 1024MiB, 0MiB} × `cdc_block_writes` ∈ {true, false}, then the B3h controls. Profile `cdc.yaml` (harness): keyspace `ks` (SimpleStrategy, RF 1), table `c (k uuid PRIMARY KEY, v blob) WITH cdc=true`, `v` fixed 16,384 bytes, one row per insert. Command: `tools/bin/cassandra-stress user profile=cdc.yaml "ops(insert=1)" n=<N> no-warmup -rate threads=16 throttle=2000/s -errors retries=0 ignore -node 127.0.0.1`; N = 200,000 (3.3 GB) at 256 and 1024 MiB, **N = 320,000** (5.2 GB) at the default, which resolves to 4096 MiB here (B3f: "raise n accordingly"). `-errors … ignore` keeps the writer running after the first rejection (otherwise stress stops there and no plateau under pressure is seen); the throttle bounds the node's log volume (each rejected write logs an `ERROR` with a stack). Reason: the profile, the error mode, the log volume and N for the default were not given.

**B3d. Observables and instruments.** `du -sb /local/c509-node/cdc_raw` every 1 s; stress error count; `grep "Rejecting mutation" logs/system.log`; effective value via `cqlsh -e "SELECT value FROM system_views.settings WHERE name='cdc_total_space'"`; `df -B1 /local/c509-node` for the default arithmetic.

**Amendment 2026-10-24 (step-0 audit, Claude Opus 5.5) — B3d, macOS commands and added observables.** `du -sb` (GNU) is replaced by a Python sampler every 0.25 s (finer than 1 s, so a short overshoot is not missed) that records the apparent bytes (`st_size`, what `du -sb` and the CDC counter count) and allocated bytes of `CommitLog-*.log` links and of `*_cdc.idx` files separately, and every name that appears or disappears; `df -B1` is replaced by `statvfs` (`f_blocks × f_frsize`, the value `FileStore.getTotalSpace()` returns). Added: non-blocking deletion evidence — `debug.log` lines `Freed up … after deleting the oldest CDC commit log segments` (`CommitLogSegmentManagerCDC.java:351`) and link names deleted in the sampler; rejection evidence — `system.log` `Rejecting mutation` (NoSpamLogger, at most once per 10 s, `:220-224`) and the stress `Total errors` line; accepted rows by `SELECT count(*) FROM ks.c` after the stress. Reason: two Linux-only commands, and no observable for the non-blocking deletion or the accepted data.

**B3e. Procedure.** Configure → start → check effective value → create schema → start `du` sampler → stress → stop sampler → drain → stop → wipe → next knob/mode.

**B3f. Predictions.** Blocking: `du` max ≤ knob + 32 MiB (≈ 288 MiB / 1056 MiB); stress reports write failures after ≈ knob of data; "Rejecting mutation" logged. Non-blocking: no failures, `du` plateaus ≤ knob + 32 MiB. Default: effective value = min(4096, df total MiB / 8), and `du` max ≤ that + 32 MiB (if the volume makes the default > the 3.2 GB workload, raise `n` accordingly).

**Amendment 2026-10-24 (step-0 audit, Claude Opus 5.5) — B3f, tolerances from the source** (as B2f, with S = 32 MiB, k = ⌊A/S⌋). Blocking: stress reports failures; `Rejecting mutation` logged; rows accepted × 16 KiB in [A − 4S, A + S]; max link bytes ≤ A + S at every sample. Non-blocking: 0 failures; at least one `Freed up` line and one deleted link; max link bytes ≤ A + S. Default: read-back `cdc_total_space` = min(4096, ⌊⌊total/2^20⌋/8⌋) MiB with total from `statvfs` (4096 on this machine; the `/8` branch is exercised only by the unit tier's helper here). Reason: "≈ knob of data" was not a number.

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| `du` plateaus at ≈ knob (+1 segment) | claim confirmed |
| `du` grows with data written past knob + 2 segments | cap not binding (claim wrong) |
| no failures in blocking mode and `du` capped | rejection path not reached (recheck) |
| effective default ≠ min(4096, total/8) | line 684 derivation differs |

**Amendment 2026-10-24 (step-0 audit, Claude Opus 5.5) — B3g, rows added; the four rows above are unchanged.** Row 1 needs every amended B3f item for the arm. Added rows: (5) max link bytes in (A + S, A + 2S] with rejection or deletion present → **Not confirmed** (more overshoot than predicted). (6) blocking: failures begin with accepted bytes below A − 4S → **Not confirmed** (cap does not follow the knob as predicted). (7) non-blocking: any stress failure or `Rejecting mutation` → **Refuted** for the non-blocking clause. (8) non-blocking: no deletion evidence → **Invalid** (limit not reached). (9) a control fails → **Invalid**. **Tier verdict:** Confirmed if all six arms match row 1, the default reads back as predicted and the controls hold; Refuted if any arm matches row 2 or 7 or the default differs (row 4); otherwise the weakest matched row. Reason: outcomes between the confirm and refute rows had no row.

**B3h. Controls.** The same stress against a `cdc=false` table: `cdc_raw` stays ≈ 0 and no rejections; `cdc_enabled: false` node ignores the knob.

**Amendment 2026-10-24 (step-0 audit, Claude Opus 5.5) — B3h, control expectations and exact runs.** (a) `cdc=false` table, `cdc_total_space: 256MiB`, blocking, the same stress (N = 200,000) with profile `plain.yaml` (table `ks.p`, `WITH cdc=false`): 0 failures, no `Rejecting mutation`; `cdc_raw` holds links of live segments (made at creation whatever their contents, `CommitLogSegmentManagerCDC.java:241-247`), so max link bytes ≤ A + S during the run, and ≤ 2 links 30 s after `nodetool flush ks` (links of segments without CDC data are deleted on discard, `:75-80`) — not "≈ 0" as filed. (b) `cdc_enabled: false`, `cdc_total_space: 256MiB`, `cdc_block_writes: true`, profile `cdc.yaml` (N = 200,000): 0 failures, no link in `cdc_raw` at any sample. (c) start-up only: `cdc_enabled: false`, `cdc_total_space: 0MiB` → read-back `0MiB` (the derivation at line 684 runs only under `cdc_enabled`, `DatabaseDescriptor.java:677`). Reason: "≈ 0" contradicts the cited source; the controls' purpose is unchanged.

**Amendment 2026-10-24 (after run 1, authorised by the user) — B3h (a).** *Follows a run-1 reading:* in cluster run 1 control (a) missed its expectation (6 links about 34 s after `nodetool flush ks`, expected ≤ 2; results file §4.3), so by the rule "a wrong §9a is a dated amendment and the affected tier starts again" this amendment was authorised by the user (Yang, the advisor) on 2026-10-24 and the **whole cluster tier is re-run** at the new frozen version. The audit's error: flushing only `ks` leaves older segments dirty for system tables, and `discardCompletedSegments` discards a segment only when **every** table dirty in it has been marked clean (`CommitLog.java:353-383`, `CommitLogSegment.isUnused()` `CommitLogSegment.java:611-619`). **What changes** (only the post-flush step and value of (a); its workload, during-run bound, 0 failures and no `Rejecting mutation` stay as above): after the stress and the 5 s settle, run **`nodetool flush` with no keyspace argument**, which flushes every keyspace in the schema, local system keyspaces included (`Flush.java:38-45`; `NodeTool.java:471-488`, default `KeyspaceSet.ALL` → `getKeyspaces()`; `StorageService.java:6231-6234` → `Schema.java:353-356`, distributed ∪ local), then wait 30 s; the **post-flush link count** is the largest `links` value of every sampler row taken from 30 s after `nodetool flush` returns until the sampler stops. **Expected: ≤ 2 links**, derived from the source: (1) `nodetool flush` returns only after each table's flush and its post-flush commit-log discard have run (`StorageService.java:4743-4749` → `forceBlockingFlush` waits on the flush future, `ColumnFamilyStore.java:1114-1116`; the post-flush task calls `CommitLog.discardCompletedSegments`, `ColumnFamilyStore.java:1147-1152`), so no wait is needed beyond the return; the 30 s is kept as a margin. (2) Each discard call marks the flushed table clean in every active segment up to the one holding the flush's upper bound and discards each segment that has become unused (`CommitLog.java:361-382`); a segment still being allocated is never unused (`CommitLogSegment.java:421-424`, `:615-616`). With every table flushed and no workload running (system-table writes after the flush land in the segment being allocated), every active segment except the one being allocated is discarded. (3) A discarded segment's hard link and index file are deleted when it does not contain CDC data (`CommitLogSegmentManagerCDC.java:66-83`, `CDCState != CONTAINS`); the `cdc=false` table's mutations never set `CONTAINS` (`:186-187`, only `mutation.trackedByCDC()`). (4) The remaining links can belong only to the segment being allocated (linked at creation, `:236-249`, or on re-permission, `:195-210`) and the one segment prepared ahead, which is created and linked by the manager thread (`AbstractCommitLogSegmentManager.java:189`) but joins `activeSegments` only when it becomes the allocating segment (`:307-312`), so no discard reaches it. Hence ≤ 2. This value comes from the source, not from run 1's readings (run 1's unit control, which flushes every table through `forceRecycleAllSegments()`, is consistent with it). Nothing else in B1, B3a–B3g or the other controls changes; B3e's "drain" step and B3g's rows do not name the flush and are unchanged; the unit tier (B2) is closed and untouched. Paths only: the re-run uses a fresh clone `$W/cassandra-run9` and node directories `$W/node-cdc2` (same host and SSD) in place of the B3a amendment's `$W/cassandra-run6` and `$W/node-cdc`.

**B4. Risks and cleanup.** Up to ≈ 4 GB commit log + data on `/local/c509-node`; never point `cdc_raw_directory` at shared storage. Stop node/stress, `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` empty, `rm -rf /local/c509-node`.

## C. Sources read

src/java/org/apache/cassandra/config/DatabaseDescriptor.java (664-698, 1147-1162, 4370-4385)
src/java/org/apache/cassandra/config/Config.java (413-421)
src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java (185-225, 286-430)
test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDCTest.java (59-160, 425-440)
conf/cassandra.yaml (413-425, 660, 923-929)

## D. Stage-4 feedback

**2026-10-24, stage 4 run 1 (Claude Opus 5.5, claude-opus-5-5), advisor's machine; results in
[`../../stage4-runtime-verification/results/cdc_total_space-applySimpleConfig-cdc_total_space--autonomous.md`](../../stage4-runtime-verification/results/cdc_total_space-applySimpleConfig-cdc_total_space--autonomous.md).**
Frozen at sha256 `cfaee9a0…82e5` after twelve dated audit amendments (above); nothing committed.

- **Unit: Confirmed — caps** (B2g row 1). S = 1 MiB: blocking plateaus 7, 15, 31 MiB of links for s = 8, 16, 32 (k − 1 links at an exact
  multiple: index bytes tip the counter), first rejection after 6.6 / 14.1 / 29.1 MiB accepted; non-blocking held ≤ s MiB while writing
  4·s MiB and deleted 29 / 55 / 107 links; helper 512 (4 GiB) and 4096 (100 GiB); controls held.
- **Cluster: Invalid — undetermined** (B3g row 9). All six arms matched row 1: `cdc_raw` stopped at exactly 256, 1024 and 4096 MiB (the
  default read back as 4096 MiB on a 471,482 MiB volume), blocking arms rejected writes with `Rejecting mutation`, non-blocking arms
  deleted old links with no failures. But control (a) (`cdc=false` table) kept **6** links 34 s after `nodetool flush ks`, against the
  audit's expectation of ≤ 2: segments still holding unflushed system-table writes are not discarded by flushing one keyspace (inferred;
  the unit control, which flushes everything, left 0). The expectation was the audit's error and cannot be edited after the reading.
- **For stage 3 / a later stage-4 session:** (1) B3h (a): flush all keyspaces (or force a recycle) before the post-flush reading, then
  re-run the cluster tier as a new frozen version. (2) Exercise the `/8` branch at the cluster tier on a fixed-size volume holding both
  `cdc_raw` and the commit log (hard links cannot cross file systems); this host cannot give the session a writable disk image.
  (3) B1's "+ one segment" never showed: with values that are multiples of S the plateau was ⌊A/S⌋ or ⌊A/S⌋ − 1 segments, never above A.

**2026-10-25, stage 4 cluster re-run ("run 1b", Claude Opus 5.5, claude-opus-5-5), authorised by the user (Yang, the advisor) on
2026-10-24; results file §7.** Re-frozen at sha256 `ad11ccdc…5cb2` after one dated amendment, `Amendment 2026-10-24 (after run 1,
authorised by the user) — B3h (a)` (flush all keyspaces with `nodetool flush`; ≤ 2 links re-derived from the source); the whole cluster
tier re-run from its beginning on a fresh clone; nothing committed.

- **Cluster: Confirmed — caps** (B3g row 1). All six arms matched row 1 again: `cdc_raw` stopped at 256, 1024 and 4096 MiB (bdef one segment
  below, 4064 MiB, allowed by the k − 1 tolerance), blocking arms rejected writes (`Rejecting mutation`, 61 k–184 k failures), non-blocking
  arms deleted old links (26–74 `Freed up` lines) with 0 failures; the default read back 4096 MiB. Control (a): after `nodetool flush` (50
  tables in six keyspaces) the links fell from 9 to 0, then 1; max 1 from 30 s after the flush (≤ 2 expected) — holds; (b) and (c) hold.
  Self-check 15 / 15. Run 1's cluster verdict (Invalid) stays on record.
- **Stage 4 for this file is closed:** unit Confirmed — caps (run 1), cluster Confirmed — caps (re-run). Open for stage 3: the `/8` branch is
  still exercised only by the unit helper on this host (item (2) above); B1's "+ one segment" (item (3)) again never showed.
