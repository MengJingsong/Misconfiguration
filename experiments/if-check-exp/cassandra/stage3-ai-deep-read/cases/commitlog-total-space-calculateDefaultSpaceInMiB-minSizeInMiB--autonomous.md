# commitlog_total_space (default derived by calculateDefaultSpaceInMiB; cdc_total_space is the sibling) — verification solution  <!-- file: cases/commitlog-total-space-calculateDefaultSpaceInMiB-minSizeInMiB--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/config/DatabaseDescriptor.java:1152` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude (Sonnet 5.5), Claude Code CLI, 2026-10-26 |
| Estimate | `positive`. The helper only sizes the default, but the limit it sizes (`commitlog_total_space`, sibling `cdc_total_space`) is compared against on-disk segment bytes and drives flush/recycle (commitlog) or write rejection (CDC), so disk use is bounded to roughly the limit plus a bounded overshoot. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** The target line (`if (minSizeInMiB < preferredSizeInMiB)`, DatabaseDescriptor.java:1152) is inside `calculateDefaultSpaceInMiB` (1147-1162). The helper is not a limit itself; it picks the default value for two limits:
- `commitlog_total_space` (config entry): declared `Config.java:389-390` (`DataStorageSpec.IntMebibytesBound`, no default in Config, null means "derive"). Commented-out default `8192MiB` at `conf/cassandra.yaml:883`.
- `cdc_total_space` (config entry): declared `Config.java:418-419`, default `0MiB` meaning "derive". `conf/cassandra.yaml:923` shows `4096MiB`. Only derived if `cdc_enabled: true` (Config.java:410, default false).

Unit: MiB. Default derivation:
- Commitlog (DatabaseDescriptor.java:664-675): preferred 8192 MiB; minimum is 1/4 of the total size of the volume holding `commitlog_directory` (`tryGetSpace(..., FileStore::getTotalSpace)`, :668; fraction args `1, 4` at :673). Result = `min(8192, total/4)` MiB.
- CDC (:684-697): preferred 4096 MiB, fraction `1, 8` of the volume holding `cdc_raw_directory`. Result = `min(4096, total/8)` MiB.
- Helper arithmetic (:1149-1161): `minSizeInMiB = saturatedCast(num * (totalBytes / ONE_MIB) / den)`; if `minSizeInMiB < preferred` it logs a warning "Small {} volume detected..." and returns `minSizeInMiB`, else returns `preferred`. The comparison is strict, so equality returns `preferred` (same value anyway). Integer division truncates. Note the helper uses TOTAL volume size, not free space, so the "cap" can exceed free space.

Setting: yaml key `commitlog_total_space` / `cdc_total_space` (legacy `*_in_mb` names via `@Replaces`, Config.java:389, 418). Read at startup (applyConfig); no JMX setter for the commitlog value found at :3830 (getter only), so a change needs a restart. Existing unit test: `DatabaseDescriptorTest.java:488-507`.

**A2. What it caps.** Resource: disk.
- Commitlog: `size` (bytes of all commit log segment files, `AbstractCommitLogSegmentManager.java:434` addAndGet, `:442`, `:529` reset) compared against `getTotalCommitlogSpaceInMiB()*1024*1024` (`:445-451`, `DatabaseDescriptor.java:3830-3832`).
- CDC: `cdcSizeTracker.sizeInProgress` (CDC bytes in `cdc_raw` plus estimated new segments) compared against `getCDCTotalSpace()` (`CommitLogSegmentManagerCDC.java:329-336`, `:201`).

**A3. Mechanism.**
1. Commitlog. The management thread loop (`AbstractCommitLogSegmentManager.java:~185-200`) creates a segment, then calls `maybeFlushToReclaim()` (`:200`, defined `:246`). `unusedCapacity()` = limit - `size.get()` (`:445-451`). If negative, it walks `activeSegments` oldest first (stopping before `allocatingFrom`, :252-258) accumulating `onDiskSize()` until the overage is covered, and calls `flushDataFrom(..., false)` (:262) to flush the dirty tables so segments can be recycled/deleted.
2. Outcome at the limit: no write is rejected; instead memtables are flushed (extra flush I/O, more SSTables). Segments become deletable only after flush completes.
3. Overshoot paths: (a) the check happens after a new segment is created, so size can exceed the limit by at least one segment (`commitlog_segment_size` default 32MiB, Config.java:396-397); (b) the walk never flushes the segment currently allocated from; (c) flush is asynchronous, so a write burst can exceed the limit until flushes finish; (d) a segment still dirty for a table that cannot flush (e.g. flush blocked) stays; (e) `commitlog_total_space` smaller than a few segments gives no useful bound.
4. CDC. `processNewSegment` (:326-340) marks a new segment `FORBIDDEN` when `blocking && segmentSize + sizeInProgress > allowance`, else `PERMITTED` and counts its size. A FORBIDDEN segment rejects CDC-tracked mutations with `CDCWriteException` (`throwIfForbidden`, :212-225) when `cdc_block_writes` is true (`DatabaseDescriptor.java:4345`). With `cdc_block_writes: false` the check never forbids (`blocking` false), so cdc_raw is NOT capped.
5. Default derivation bypass: an explicit yaml value skips the helper entirely (:664, :684). The derived value is based on volume total size, so on a volume shared with data, the cap may be unreachable without exhausting the disk.

**A4. Other consumers.** SSTable data, hints, saved caches, snapshots, and logs on the same volume if `commitlog_directory`/`cdc_raw_directory` share a filesystem with data; the CDC hard links to commit log segments (`permitSegmentMaybe`, :199-210) share inodes with the commitlog (the same bytes counted in both limits); the commit log mmap/direct buffers for segments are memory, not governed by this limit.

**A5. Evidence beyond the source.** In-tree comments cite JIRA CASSANDRA-10013 and CASSANDRA-10199 for the 1/4 and 1/8 fractions (DatabaseDescriptor.java:666, 687). Unit test `DatabaseDescriptorTest.java:488-507`. Docs: Cassandra `cassandra.yaml` comments for `commitlog_total_space` and `cdc_total_space` (conf/cassandra.yaml:870-925).

## B. Verification solution

**B1. Claim under test.** (i) The helper returns `min(preferred, num*totalMiB/den)` and `commitlog_total_space` takes that value when unset; (ii) the commit log directory's on-disk size stays within `commitlog_total_space + ~2 segments + flush lag` under sustained writes, i.e. the limit (not just the default) caps disk. Falsified if commitlog dir bytes grow persistently beyond that bound, or the derived default differs from the formula.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk: `rsync -a ~/cassandra-5.0.9/ /local/scratch/c509/ && cd /local/scratch/c509 && ant jar`. Run `ant testsome -Dtest.name=org.apache.cassandra.config.DatabaseDescriptorTest -Dtest.methods=testCalculateDefaultSpaceInMiB`, plus a new scratch test class in `/local/scratch/c509/test/unit/org/apache/cassandra/config/` (copy only, never the shared tree). JVM options: defaults from build.xml.

**B2b. Knobs.** Arguments of `calculateDefaultSpaceInMiB` (package-private static; test in same package): `totalSpaceInBytes` in {0, 999 MiB, 32768 MiB exactly, 32769 MiB, 1 TiB, `Long.MAX_VALUE`}, with (preferred, num, den) = (8192,1,4) and (4096,1,8). The boundary at 8192*4 = 32768 MiB (commitlog) and 4096*8 = 32768 MiB (CDC) tests the strict `<`. Set by direct call.

**B2c. Workload.** Direct calls. Arithmetic: total=32768 MiB -> min=8192, not `<` 8192 -> returns 8192; total=32767 MiB -> min=8191 -> returns 8191 (warn logged); total=999 MiB, (2,3) -> 666 (existing test); `Long.MAX_VALUE` -> `saturatedCast` clamps to `Integer.MAX_VALUE`, not `<` preferred -> 8192. Also load `DatabaseDescriptor.daemonInitialization()` with a yaml that omits `commitlog_total_space`, and read `getTotalCommitlogSpaceInMiB()`.

**B2d. Observables and instruments.** Return value; log WARN text "Small commitlog volume detected"; `getTotalCommitlogSpaceInMiB()` after init; `FileStore.getTotalSpace()` of the commitlog dir (via `df -B1M --output=size`). Cannot observe the cap enforcement itself at this tier.

**B2e. Procedure.** 1. Build. 2. Run existing test. 3. Add test method with the table in B2b/B2c asserting returns. 4. Init with yaml lacking the key; assert getter == `min(8192, df_total/4)`. 5. Repeat with `commitlog_total_space: 64MiB` and assert the getter returns 64 and no "Small volume" warning.

**Amendment 2026-10-26 (stage-4 audit, R2).** Step 4-5 need the node yaml chosen per JVM, which `ant testsome` fixes to `test/conf/cassandra.yaml`. Run the added test class `org.apache.cassandra.config.CommitlogDefaultSpaceTest` (copied into the local tree only) four times, each with `-Dtest.jvm.args="-Dcassandra.config=file://<yaml> -Dcltest.arm=<arm>"` (the later `-Dcassandra.config` wins over build.xml's): arm H (key omitted, `commitlog_directory` on the host volume, `cdc_enabled: false`): getter == `min(8192, df_total/4)`; arm E (`commitlog_total_space: 64MiB`): getter 64, no WARN; arm V (key omitted, `commitlog_directory` on a 4 GiB tmpfs): getter 1024 and the WARN `Small commitlog volume detected`; arm C (arm V plus `cdc_enabled: true`, `cdc_total_space` omitted, `cdc_raw_directory` on the same tmpfs): `getCDCTotalSpace()` 512 and WARN `Small cdc volume detected`; with the host volume instead the CDC value is 4096. The expected value is computed in the test from `Files.getFileStore(dir).getTotalSpace()` and cross-checked against `df -B1 --output=size` in the run script. The arithmetic table (B2b/B2c) is one JUnit method in the same class, in the arm-free JVM of arm H.

**B2f. Predictions.** 32768 MiB -> 8192; 32767 -> 8191; 0 -> 0 (and WARN); 1 TiB -> 8192 (commitlog) / 4096 (CDC with den 8); init default equals formula on the host volume; explicit 64MiB bypasses helper.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Returns match B2f | helper correct; claim part (i) holds |
| 32767 MiB returns 8192 or 32768 returns 8191 | comparison/arith differs from trace; claim wrong |
| Init default != min(8192, total/4) | different code path sets the default; trace wrong |
| Explicit value ignored/overwritten | override path wrong |
| Returned value 0 on tiny volume | cap of 0: later behaviour needs the cluster tier |
| Values match B2f but the WARN line is missing where `min < preferred`, or present where it is not | arithmetic holds, logging differs from the trace; claim part (i) holds for the values (note the logging) |
| A JUnit failure or an arm that cannot start (yaml error, directory unusable) | invalid run; fix the instrument and restart the tier |

**Amendment 2026-10-26 (stage-4 audit, R3).** The last two rows were added before any run; they name outcomes the table did not cover (the logging side of B2f, and an invalid run). No prediction changed.



**B2h. Controls.** Use the same JVM and the same call with preferred swapped (100 vs 667) to show the branch flips; run twice for determinism; use a yaml file copy not the shared conf.

### B3. Cluster tier

**B3a. Environment and build.** One node (single is sufficient), JDK 11, built from the local copy (`ant jar` in `/local/scratch/c509`). Put `commitlog_directory`, `data_file_directories`, `hints_directory`, `saved_caches_directory` on a dedicated local filesystem of known size (e.g. a 4 GiB loop-mounted or partition volume, or simply a dedicated dir with `du` monitoring and 20 GiB free). `cdc_enabled: false` for the commitlog run. Heap `-Xmx2G`. `commitlog_sync: periodic`, `commitlog_segment_size: 32MiB`.

**B3b. Knobs.** `commitlog_total_space` in {unset (derived default), 256MiB, 128MiB}. Unset case on a 4 GiB volume derives 1024 MiB (4096/4 < 8192, WARN logged), which verifies the helper on a real node; the small values force the cap to bind quickly. Also memtable settings to make flushes slow enough: `memtable_heap_space: 1024MiB`, `memtable_flush_writers: 1`, and `memtable_cleanup_threshold` default. Set in a copy of `conf/cassandra.yaml` per run; restart each time.

**Amendment 2026-10-26 (stage-4 audit, R4-R6), made before any run.** (a) Volume: `commitlog_directory` goes on a 4 GiB tmpfs (`sudo mount -t tmpfs -o size=4g`, `FileStore.getTotalSpace()` = 4096 MiB exactly, so the unset arm derives 1024 MiB); `data_file_directories`, `hints_directory`, `saved_caches_directory`, `cdc_raw_directory` go on a separate tmpfs directory (`/dev/shm`), because a 4 GiB volume cannot also hold the sstables of a multi-GiB write and the helper reads only the commit log's volume. (b) Heap and memtable: the filed `-Xmx2G` with a 1024 MiB memtable would flush on `MEMTABLE_LIMIT` before the commit log reaches 1024 MiB and hide the cap; use `MAX_HEAP_SIZE=24G`, `HEAP_NEWSIZE=4G`, `memtable_allocation_type: heap_buffers`, `memtable_heap_space: 8192MiB`, `memtable_cleanup_threshold: 0.9`, and read the flush reasons from `system.log` (a `MEMTABLE_LIMIT` flush in an arm makes it invalid). (c) Node: loopback `127.0.2.1` (port slot 2), JMX 7120, native 9042 on 127.0.2.1, one node. (d) The unset arm and the 8192 MiB control are both run; the control is an explicit `commitlog_total_space: 8192MiB`, whose unset value on this 4 GiB volume would not be 8192.

**B3c. Workload.** `tools/bin/cassandra-stress write n=6000000 -col size=FIXED(1000) n=FIXED(5) -rate threads=64` (about 5 KB per row x 6M = 30 GB nominal of mutations, far over every limit) with a table whose memtable would not flush on its own before the commit log fills (many tables spreading dirtiness: create 20 tables, run stress per table in turn so the oldest segments stay dirty). Duration 10-15 min or until 1.5x the largest limit has been written 10 times over. Arithmetic: 128 MiB limit / 32 MiB segments = 4 segments; any run writing >1 GiB reaches the limit many times over.

**Amendment 2026-10-26 (stage-4 audit, R4), made before any run.** `cassandra-stress` writes only `keyspace1.standard1`, so the filed "20 tables" and "30 GB" cannot run as written (the data would also not fit the volume). The workload is one table: `tools/bin/cassandra-stress write n=2200000 cl=ONE -col 'size=FIXED(1000)' 'n=FIXED(1)' -rate threads=64 -mode native cql3 -node 127.0.2.1` (about 2.4 GiB of commit log, 2.3 times the unset limit, 9.5 times the 256 MiB limit, and below 90 % of the 4 GiB tmpfs for the 8192 MiB control), then a 60 s settle. Single-table dirtiness lets one forced flush free every older segment (see `results/commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous.md`), so this is the cap check of B1, not a test of the walk's stop condition. Unquoted `FIXED(1000)` breaks in bash; quote it.

**B3d. Observables and instruments.** Every 2 s: `du -sb commitlog_directory` (primary); JMX `org.apache.cassandra.metrics:type=CommitLog,name=TotalCommitLogSize` via `nodetool sysigar`-free means (`jmxterm` or `nodetool tpstats` for flush pending); `nodetool tablestats` flush counts; `system.log` for "Small commitlog volume" and "flushing ... to reclaim" lines. Cannot see per-segment dirty state except via logs.

**Amendment 2026-10-26 (stage-4 audit, R4).** The primary sampler is `du -sb --apparent-size` of `commitlog_directory` every 0.25 s with the file count; the JMX gauge is read with `bin/nodetool -h 127.0.2.1 -p 7120 sjk mx -mg -b org.apache.cassandra.metrics:type=CommitLog,name=TotalCommitLogSize -f Value` back to back (each call starts a JVM). `jmxterm`, `nodetool sysigar` and `nodetool getcommitlogsize` do not exist here; the effective limit is read from the startup config line `commitlog_total_space=` in `system.log` and from the `Small commitlog volume detected` WARN.

**B3e. Procedure.** 1. Create volume, copy yaml. 2. Start node with the knob value; confirm `grep commitlog_total_space` effective value through `nodetool getcommitlogsize`-equivalent log line or JMX `TotalCommitLogSize` baseline and the startup WARN. 3. Start the sampler loop. 4. Run the stress workload. 5. Record max of `du -sb`. 6. `nodetool drain`, stop the node, `kill` check with `pgrep -f CassandraDaemon`, delete the dirs. 7. Repeat for each knob value, then the control.

**B3f. Predictions.** Unset on a 4 GiB volume: effective limit 1024 MiB (the WARN line present); peak commitlog dir <= limit + 2 x 32 MiB + flush lag, expected below ~limit x 1.25 for the 128/256 MiB runs; peak scales with the knob (128 MiB run peak < 256 MiB run peak < unset run peak). Flush count rises as the limit shrinks.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Peak `du` <= limit + ~100 MiB for each value and ordered by knob | limit caps disk; claim holds |
| Peak independent of knob (same plateau) | limit does not govern; claim wrong |
| Peak grows unbounded with workload | claim wrong |
| Overshoot > 2 segments + flush lag but bounded | caps with larger overshoot; note |
| Unset run effective limit != min(8192, vol/4) | default derivation wrong |
| Never reached the limit (peak well below it) | not confirmed; raise the workload |
| Unset run: effective limit equals the formula but the WARN line is absent, or a `MEMTABLE_LIMIT` flush occurs in an arm, or the volume passes 90 % | WARN absent: logging differs, note it; `MEMTABLE_LIMIT` flush or full volume: invalid arm, rerun |

**Amendment 2026-10-26 (stage-4 audit, R3).** The last row was added before any run to cover the logging check and the validity conditions B4 names. No prediction changed.



**B3h. Controls.** Same workload with the limit set above the written volume (e.g. 8192MiB on 20 GiB free volume, shortened run) showing growth unbounded by the small values, i.e. the knob is what stops it; same node build; flush writers constant; repeat each value twice; separate fresh data dir each run. CDC variant (optional): `cdc_enabled: true`, `cdc_total_space: 64MiB`, `cdc_block_writes: true`, table with `cdc=true`, no consumer; expect `cdc_raw` size to plateau near 64 MiB and `CDCWriteException` on writes; with `cdc_block_writes: false` expect no plateau (cap not enforced).

**B4. Risks and cleanup.** Disk: workload up to tens of GB written but data dir is on the sized volume; stop if the volume passes 90%. No shared storage; hints disabled for the run (`hinted_handoff_enabled: false`). Leftover processes: `pgrep -f cassandra`, `pgrep -f cassandra-stress`, kill; unmount and remove the loop volume and scratch dirs.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 640-715, 1120-1190, 3826-3833)
- src/java/org/apache/cassandra/config/Config.java (grep of lines 389-419)
- src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java (185-275, 436-470)
- src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java (190-232, 322-340, greps)
- test/unit/org/apache/cassandra/config/DatabaseDescriptorTest.java (485-510)
- conf/cassandra.yaml (grep)

## D. Stage-4 feedback

- 2026-10-26 stage-4 audit: amendments R2-R6 above (yaml-per-arm unit runs, tmpfs layout, heap and memtable, one-table workload, samplers, two table rows). Predictions B2f and B3f unchanged. Results: `stage4-runtime-verification/results/commitlog-total-space-calculateDefaultSpaceInMiB-minSizeInMiB--autonomous.md` (the verdict section is added after the run).
- 2026-10-26 run 1 (both tiers, 2 repetitions; results file above): **unit Confirmed** (B2g row 1, 357 checks pass, init arms H/E/V/C/D match); **cluster Confirmed, B3g row 4** (caps with larger overshoot, soft): peaks 224 / 448 / 1760-1952 MiB for limits 128 / 256 / 1024 (unset, derived from the 4096 MiB tmpfs) against 2336 MiB with an explicit 8192 MiB; `COMMITLOG_DIRTY` flushes 23 / 10 / 2 / 0. Outcome class: true positive. The B3f sub-predictions (limit + 2 segments; below about 1.25 x the limit) were missed at 1.72-1.91 x under unthrottled 110 k op/s: for stage 3, state the bound as limit + flush lag, or add a throttled arm. The case file's section D was edited after the freeze (feedback field only; the frozen sha256 in the results file covers B2-B3 as amended on 2026-10-26).
