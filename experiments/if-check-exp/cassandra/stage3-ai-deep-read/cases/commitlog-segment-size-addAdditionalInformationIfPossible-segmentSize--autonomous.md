<!-- file: cases/commitlog-segment-size-addAdditionalInformationIfPossible-segmentSize--autonomous.md -->
# commitlog_segment_size — verification solution  <!-- file: cases/commitlog-segment-size-addAdditionalInformationIfPossible-segmentSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/commitlog/CommitLog.java:609` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI (Agent SDK), 2026-10-26 |
| Estimate | `negative`. The check at line 609 only decides whether to append text to an error message. It allocates nothing and refuses nothing. Its "free space" operand is also actually the volume's total space. |
| Ground | The site is a diagnostic string builder on the commit-failure path (`CommitLog.java:604-615`). It has no effect on how many segment files exist or how large they are. Its disk quantity comes from `FileStore::getTotalSpace` (`CommitLog.java:572`), which is capacity and not free space, so the branch is almost never taken and cannot reflect real disk pressure. The knob it reads, `commitlog_segment_size`, does fix the size of each segment (A3), but that is enforced elsewhere (segment creation), not here. The whole commit-log disk footprint is capped by `commitlog_total_space`, a different constraint. |

## A. Constraint trace

**A1. The constraint.** `commitlog_segment_size`, a configuration entry. It is declared at `src/java/org/apache/cassandra/config/Config.java:396-397` as `DataStorageSpec.IntMebibytesBound`, default `"32MiB"`. The yaml default is `commitlog_segment_size: 32MiB` (`conf/cassandra.yaml:660`). The legacy key `commitlog_segment_size_in_mb` is still accepted through `@Replaces`. The unit is MiB in the yaml and bytes through `DatabaseDescriptor.getCommitLogSegmentSize()` (`DatabaseDescriptor.java:2875-2878`). `applySimpleConfig` validates it: it must be non-zero and below 2048 (`DatabaseDescriptor.java:891-896`). It must also be at least twice `max_mutation_size`, which defaults to half the segment size (`DatabaseDescriptor.java:898-901`). It is set only in `cassandra.yaml` (or a `-Dcassandra.config` file) and needs a restart. The only runtime setter is `setCommitLogSegmentSize` (`DatabaseDescriptor.java:2887`), marked `@VisibleForTesting`. Its derived value is read at line 607 of the target.

**A2. What it caps.** Disk: the size of one commit-log segment file. With the mmap segment type it also caps the size of one mapped region (`MemoryMappedSegment.java:62`). For compressed and encrypted segments it sizes a per-thread scratch buffer (`CompressedSegment.java:116`, `EncryptedSegment.java:112`), which is heap or off-heap. At the target line the quantity compared is `unallocatedSpace` (bytes reported by the file store of the commit-log directory) against `segmentSize` (bytes).

**A3. Mechanism.**
1. `handleCommitError` (`CommitLog.java:576`) runs on commit-log failures. Callers are `AbstractCommitLogSegmentManager.java:206` (segment management), `AbstractCommitLogService.java:220` (sync), `CommitLogReplayer.java:539` (replay), `CommitLogSegmentManagerCDC.java:417` and `CommitLogSegment.java:390`.
2. For `die`/`stop`, it stops transports and logs. For `stop_commit` it logs and returns false. For `ignore` it logs and returns true (`CommitLog.java:579-595`). Every logging branch passes the message through `addAdditionalInformationIfPossible` (lines 588 and 591).
3. That method reads `freeDiskSpace()` (line 606) and `getCommitLogSegmentSize()` (line 607). If `unallocatedSpace < segmentSize` (line 609) it appends "N bytes required for next commitlog segment but only M bytes available. Check ... " (lines 611-612). Otherwise it returns the message unchanged (line 614).
4. `freeDiskSpace()` (line 570-573) calls `PathUtils.tryGetSpace(path, FileStore::getTotalSpace)`. Despite the names `freeDiskSpace` and `unallocatedSpace`, `getTotalSpace` is the capacity of the volume, not unallocated or usable space. `tryGetSpace` (`PathUtils.java:804-807`) returns 0 if no ancestor exists or on `IOException` (`PathUtils.java:778-795`), and `Long.MAX_VALUE` on overflow (`PathUtils.java:819-822`).
   - Outcome when the limit is reached: the effect is only a longer log line.
   - Bypass and overshoot: the check never gates anything. On any volume whose total size is at least the segment size (32 MiB by default) the branch is not taken, however full the disk is. It can fire on a roomy volume only if the volume's total size is below the segment size, or if the directory or its ancestors are unresolvable (the 0 return).
5. The real enforcement of the segment size is at segment creation (`MemoryMappedSegment.java:62-63` maps `getCommitLogSegmentSize()` bytes and calls `manager.addSize`). Total footprint is limited by `commitlog_total_space` (`Config.java:389-390`; `unusedCapacity` at `AbstractCommitLogSegmentManager.java:445`; derived at `DatabaseDescriptor.java:668` also from `getTotalSpace`, which is correct there because it takes a fraction of capacity).

**A4. Other consumers.** Memtable flush SSTables, hints, saved caches, and snapshots share the volume if the commit log is not on a dedicated disk. Archived commit logs and CDC raw files (`cdc_raw_directory`, `CommitLogSegmentManagerCDC.java:201-207`) consume space outside this check. Other users of the same file system are not counted in `getTotalSpace`.

**A5. Evidence beyond the source.** none. (`FileStore.getTotalSpace` versus `getUsableSpace`/`getUnallocatedSpace` semantics are from the JDK `java.nio.file.FileStore` javadoc: https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/FileStore.html)

## B. Verification solution

**B1. Claim under test.** Usage does not follow this check: whether the "bytes required ... only M bytes available" text is appended depends on the volume's total capacity relative to `commitlog_segment_size`, not on free space, and the check has no effect on how much disk the commit log uses. If the text appears exactly when free space drops below the segment size on a large volume, or if the check is shown to gate segment allocation, the claim is wrong.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tag to local disk (for example `rsync -a ~/cassandra-5.0.9/ /local/scratch/c509/`), never build in the shared tree. `ant jar` in the copy, then a small JUnit test or a main class in `/local/scratch/c509/test/unit/org/apache/cassandra/db/commitlog/AddInfoProbeTest.java`, run with `ant testsome -Dtest.name=AddInfoProbeTest`. The method is private, so call it by reflection (`setAccessible(true)`), or drive `CommitLog.handleCommitError("m", new IOException())` with `commit_failure_policy: ignore` and capture the log line with a logback `ListAppender`. Use `DatabaseDescriptor.daemonInitialization()` and set `commitlog_directory` to a directory on a known volume.

**B2b. Knobs.** `commitlog_segment_size` in {8MiB, 32MiB (default), 1024MiB, 2047MiB} through `DatabaseDescriptor.setCommitLogSegmentSize(int)` or the test yaml. Directory location chosen among: (a) a large local volume (for example 100 GiB total), (b) a 16 MiB tmpfs (`mount -t tmpfs -o size=16m`, needs root; otherwise skip to the alternative in B2h), (c) a not-yet-existing path under a large volume, (d) a not-yet-existing path under the 16 MiB tmpfs. *[Amended 2026-10-26, D-R1: arm (d) was "an unresolvable path"; no directory string can be unresolvable because `findExistingAncestor` walks up to `/`, which exists, so the 0 return at `PathUtils.java:785-789` is unreachable here.]* Values chosen to be below, near, and above any volume total.

**B2c. Workload.** No traffic. Call the method directly. To make `segmentSize` exceed volume total on the large volume, use 2047MiB only if the volume is smaller than 2 GiB (use the tmpfs for this). The arithmetic: unallocated operand = volume total. The branch fires iff `total < segment bytes`. For the 16 MiB tmpfs: 16 MiB < 32 MiB, so it fires. For the 100 GiB volume: 100 GiB > 2047 MiB, so it never fires for any permitted segment size.

**B2d. Observables and instruments.** Return string of the method; whether it contains "bytes required for next commitlog segment". The values printed (`segmentSize`, `unallocatedSpace`) compared with `df -B1 --output=size,avail <dir>` and `stat -f`. Directly unobservable: nothing; this is pure.

**B2e. Procedure.**
1. Build the copy; start the probe with the commit-log directory on the large volume and segment size 32MiB. Record the return value and `df`.
2. Fill the large volume to a few KiB free using a local scratch volume only (or use the tmpfs: write a filler file until `avail` < 1 MiB). Repeat the call.
3. Repeat on the 16 MiB tmpfs both empty and full.
4. Repeat with a nonexistent path under the large volume and one under the 16 MiB tmpfs. *[Amended 2026-10-26, D-R1.]*
5. Vary `commitlog_segment_size` across the values in B2b on the large volume.
6. Stop all JVMs, unmount the tmpfs, delete the scratch copy.

**B2f. Predictions.** Large volume, 32MiB, any free space including near 0: message unchanged (no augmentation), printed `unallocatedSpace` equals `df` size column and not the avail column. Large volume, every segment size in B2b: never augmented. 16 MiB tmpfs, 32MiB, empty or full: augmented, with `unallocatedSpace` = 16777216. Nonexistent path under the large volume: the large volume's total, not augmented. Nonexistent path under the 16 MiB tmpfs: `unallocatedSpace` = 16777216, augmented (not 0). *[Amended 2026-10-26, D-R1: this replaces "Unresolvable path: `unallocatedSpace` = 0, augmented".]*

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Large volume, free near 0, message unchanged, printed value equals total size | Claim confirmed: operand is capacity, not free space |
| Large volume, free near 0, message augmented with a value near avail | Claim refuted: operand follows free space |
| Augmentation flips with segment size only when `segment > total` (tmpfs) | Branch works as traced, but depends on capacity |
| Segment size changed, no change in the commit-log disk consumption in a cluster run (B3) | Supports "no cap enforced here" |
| Usage (files in commitlog dir) moves with the knob where the control binds (segment file size) | Positive control OK: `commitlog_segment_size` caps segment size at creation, not through this line |
| Branch never reached on any volume (even tmpfs), or tmpfs could not be created | Not confirmed; use the B2h alternative |

**B2h. Controls.** Positive control: in the same JVM, create a `CommitLog` segment (or read `getCommitLogSegmentSize()` in the mmap path) and show the segment file is `commitlog_segment_size` bytes, so the knob does bind elsewhere. Cross-check every value against `df`/`stat -f` in the same second. Alternative if no root for tmpfs: use a mocked `FileStore` is not possible via this API, so instead run `jshell` against the compiled jar with `PathUtils.tryGetSpace(path, FileStore::getUsableSpace)` and `getTotalSpace` side by side to show the two differ on a nearly full volume, and static-check line 572 by `grep`.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from a local copy (`ant jar`), run from a local directory. `commitlog_directory` on a small dedicated volume (a loopback ext4 of 64 MiB, or a tmpfs of 64 MiB, needing root; otherwise the largest quota-limited local partition available), `data_file_directories`, `hints_directory` and `saved_caches_directory` on a different local disk of known size. `commit_failure_policy: ignore`, `commitlog_sync: periodic`, `commitlog_segment_size: 32MiB`, `commitlog_total_space: 64MiB` (the default would be min(8192, 1/4 of volume) = 16 MiB), `commitlog_compression` unset, `disk_access_mode` default. Heap `-Xmx1G`.

**B3b. Knobs.** `commitlog_segment_size` in {8MiB, 32MiB}, with `max_mutation_size` left at default (half). Commit-log volume total size in {64 MiB, 16 MiB}. *[Amended 2026-10-26, D-R3: arms and filler.]* Arms (one node start each; `commitlog_total_space: 64MiB`, `commit_failure_policy: ignore`, `commitlog_sync: periodic`): **A1** 64 MiB tmpfs, 32MiB segments, default `commitlog_disk_access_mode: legacy` (mmap), filler leaving 4 MiB free; **A2** as A1 with `commitlog_compression` LZ4 (the `standard` access mode: plain `channel.write`); **A3** 16 MiB tmpfs, 32MiB, mmap, no filler; **A4** as A3 with LZ4; **A5** 16 MiB tmpfs, 8MiB segments, mmap, filler leaving 2 MiB free; **Z32** and **Z8** (positive control, B3h): 1 GiB tmpfs, no filler, 32MiB and 8MiB segments. Why: 64 MiB volume with 32MiB segments is above the check threshold on total capacity yet exhausts free space after two segments; the 16 MiB volume is below the threshold on capacity. Set in `cassandra.yaml`; restart between runs.

**B3c. Workload.** `cassandra-stress` (or cqlsh loop) writing 1 KiB blobs to a table with `durable_writes=true`, at a rate high enough to fill segments faster than flush reclaims, for example `cassandra-stress write n=2000000 -col size=FIXED(1024) -rate threads=64` for 10 minutes. *[Amended 2026-10-26, D-R3: the two sentences that followed ("32 MiB segments on a 64 MiB volume: the third segment cannot be allocated ..." and "On the 16 MiB volume, the first segment cannot be created") are withdrawn: mmap segments are sparse (`MemoryMappedSegment.java:62` maps the file to its full length and pages are taken only when written), so creating a segment does not use its nominal size and the volume fills only as bytes are written, while flushes recycle segments. Exhaustion is therefore made by a filler: after the node is up, `fallocate -l <free - 4MiB>` on the commit-log volume (2 MiB for A5), then the stress writes (`n=200000`, 16 threads, at most 120 s) until the volume is exhausted. A3 and A4 have no filler: the 16 MiB volume fills by the writes themselves. The Z arms use `n=2200000` and no filler.]*

**B3d. Observables and instruments.** Node log (`system.log`) lines for "Failed managing commit log segments" and whether they carry "bytes required for next commitlog segment but only ... bytes available"; `df -B1 <commitlog volume>` every 5 s; `ls -l` of the commit-log directory; JMX `org.apache.cassandra.metrics:type=CommitLog,name=TotalCommitLogSize` and `name=PendingTasks`; `jcmd <pid> GC.heap_info` for heap. Not directly observable: the internal `unallocatedSpace` value (inferred from the logged number).

**B3e. Procedure.**
1. Create the small volume (`mount -t tmpfs -o size=64m tmpfs /local/cl` or loopback ext4) and the other directories on local disk; apply the yaml.
2. Start the node; confirm via `nodetool info` and `df` that it is up and the commit-log directory is on the small volume.
3. Start the sampling loop (`df`, `ls`, JMX) writing to a local file.
4. Run the workload for 10 minutes, or until the node logs the first commit-log error.
5. Grep the log for the two message forms. Record the number printed after "only" and compare with `df` size and avail at that second.
6. Stop the workload and node (`nodetool drain`, `kill`), check `pgrep -f CassandraDaemon` is empty.
7. Repeat with the 16 MiB volume, then with the 8MiB segment size.
8. Positive control run: same workload with the commit log on a roomy volume and `commitlog_total_space: 64MiB`; observe that total commit-log bytes plateau near 64 MiB (the cap that does bind) and flushes are forced.

**B3f. Predictions.** 64 MiB volume, 32MiB segment (A1, A2, with the filler): a commit-log write error is logged through `handleCommitError` once free space is exhausted (typically "Failed to persist commits to disk", `AbstractCommitLogService.java:220`, or "Failed managing commit log segments", `AbstractCommitLogSegmentManager.java:206`) *[Amended 2026-10-26, D-R4: the message names were "Failed managing commit log segments" only]*, but the extra "bytes required ..." text is absent because total (67108864) is not below 33554432; the on-disk commit-log bytes never exceed the volume. 16 MiB volume, 32MiB segment (A3, A4): the error is logged once 16 MiB of pages have been written *[Amended 2026-10-26, D-R4]*, and the error and the extra text are both present, printed "only" value is about 16777216 (the total), not the available bytes. 8MiB segment on a 16 MiB volume (A5): no extra text, though free space still runs out. Commit-log usage stays at or below the commitlog_total_space value in the control run, independent of the target line.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Disk full on 64 MiB volume, error logged, no "bytes required" text | Claim confirmed: the check does not track free space |
| Disk full and the text appears with "only" near avail | Claim refuted |
| Text appears on the 16 MiB volume with "only" equal to the volume total | Confirms the operand is capacity |
| Commit-log bytes grow with `commitlog_segment_size` independent of this line | Knob binds elsewhere (segment creation) |
| Commit-log bytes plateau at `commitlog_total_space` in the control run while the target line is silent | Positive control OK: a cap that does bind |
| No commit-log error ever raised, or control does not plateau | Not confirmed; lengthen the run or shrink the volume |
| *[Added 2026-10-26, D-R5]* The node dies or hangs with no `handleCommitError` line in an arm | Not confirmed for that arm (the path under test was not reached); the other mode's arm may still settle it |

**B3h. Controls.** Same workload on a roomy commit-log volume (no error path reached, no message). Same node with only the segment size changed. Same volume with `commit_failure_policy: stop_commit` to show message behaviour is the same on every branch. Heap sampled throughout to show that no heap effect is attributable to the check.

**B4. Risks and cleanup.** Keep the node's data, hints, and saved caches on local disk of known size and the commit log on the dedicated small volume, so a full disk cannot affect shared storage. The `ignore` policy keeps the node alive after errors, so the run is time-boxed to 10 minutes and the workload is killed explicitly. Cleanup: stop stress and the node, confirm with `pgrep -f 'CassandraDaemon|cassandra-stress'` that nothing is left, `umount` the tmpfs or loopback and `losetup -d`, delete the local data directories and the scratch source copy.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/commitlog/CommitLog.java (lines 570-650)
- src/java/org/apache/cassandra/config/Config.java (grep: lines 389-400)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (grep: 668, 688, 891-901, 2875-2890)
- src/java/org/apache/cassandra/io/util/PathUtils.java (lines 773-822)
- src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java (grep, lines 195-215)
- src/java/org/apache/cassandra/db/commitlog/MemoryMappedSegment.java, CompressedSegment.java, EncryptedSegment.java, CommitLogSegmentManagerCDC.java (grep only)
- conf/cassandra.yaml (grep: 653-660, 880-883)
- https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/FileStore.html (cited from knowledge, not fetched)

## D. Stage-4 feedback

**Stage-4 amendments, 2026-10-26 (design audit, before any reading; reasons are from the source, not from a run).** Results: `stage4-runtime-verification/results/commitlog-segment-size-addAdditionalInformationIfPossible-segmentSize--autonomous.md`.

- **D-R1 (B2b d, B2e 4, B2f).** An "unresolvable path" arm is unreachable: `PathUtils.findExistingAncestor` (`PathUtils.java:572-581`) walks up to `/`, so `tryOnFileStore` returns the nearest existing ancestor's value, not 0 (`PathUtils.java:782-789`). Replaced by a nonexistent path under the large volume and under the tmpfs; the prediction is the ancestor volume's total.
- **D-R3 (B3b arms, B3c, B3e 4).** The commit-log segments are mmap'd and sparse (`MemoryMappedSegment.java:62`, `legacy` mode without compression), so the third-segment and first-segment arguments in B3c do not hold. Disk exhaustion is made explicitly with a filler file; added a compressed (`standard` mode) variant, because exhaustion on mmap pages arrives as a page fault rather than as an `IOException`; added the 8MiB arm on a 16 MiB volume and the roomy-volume positive-control arms. B3e step 4's "10 minutes" is replaced by the bounded stress of D-R3.
- **D-R4 (B3f).** The error message name is stated as the set of two `handleCommitError` call sites that a full commit-log volume reaches (`AbstractCommitLogService.java:220`, `AbstractCommitLogSegmentManager.java:206`); the "first segment cannot be created" claim is withdrawn.
- **D-R5 (B3g).** Added a row for a node that dies or hangs without a `handleCommitError` line.
- The claim (B1), the central relation of B2f and B3f (the extra text depends on the volume total against the segment size, not on free space) and every other row of B2g and B3g are unchanged.

**Stage-4 verdict, 2026-10-26 (run 1 only; results file above).** Estimate `negative`; stage-4 effect **does not cap**; outcome class **true negative**. Unit **Confirmed — does not cap**: on a 4 GiB volume filled to 32 KiB free the message was never extended at any of 8, 32, 1024, 2047 MiB and the operand equalled the `df` size; on a 16 MiB volume (full or empty) the text appeared with `only` = 16777216 for segments of 17 MiB and more, and not at 8 or 16 MiB; the segment file length equalled `commitlog_segment_size` (the knob binds at segment creation). Cluster **Confirmed — does not cap** in the standard (LZ4) arms: 64 MiB volume with 4 MiB free and 8 MiB segments on 16 MiB with 2 MiB free logged commit-log errors with no text; a 16 MiB volume with 32 MiB segments logged the text with `only` 16777216 while `df` showed 0 to 16 MiB free. In the default mmap mode (A1, A3, A5) the full volume killed the JVM with SIGBUS before any line (those arms **Not confirmed**). Positive control: `commitlog_total_space` 64 MiB held the commit log to a 56 to 104 MiB sawtooth under about 2.2 GB of writes (flushes COMMITLOG_DIRTY), 512 MiB let it reach 224 MiB (flushes MEMTABLE_LIMIT); Z8 exceeded the control bound fixed before the run (104 MiB against total + one segment = 72 MiB), recorded in the results file. No prediction or conclusion row was changed after any reading; two arms (A5L, ZH) were added after reading the first seven and are labelled so.

**Notes for stage 3 and upstream (candidates, JIRA check first).** (1) A1's "almost never taken" is right but the reason is sharper: the branch is taken exactly when the commit-log volume's total size is below the segment size. (2) `CommitLog.freeDiskSpace()` uses `getTotalSpace`; the logged "bytes available" is the capacity (runtime: 16777216 printed while `df` avail was 0). (3) B3c's argument that 32 MiB segments on a 64 MiB volume fail at the third segment, and that the first segment fails on a 16 MiB volume, is wrong for mmap segments (sparse); on a full volume the default mmap mode crashes the JVM with SIGBUS. (4) A short write at ENOSPC trips an `assert` at `CompressedSegment.java:83` in a `-ea` JVM.
