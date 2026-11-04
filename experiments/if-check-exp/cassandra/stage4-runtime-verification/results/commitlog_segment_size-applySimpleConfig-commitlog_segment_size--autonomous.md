# commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous — stage-4 results  <!-- file: results/commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous.md -->

> **Case:** [`commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous`](../../stage3-ai-deep-read/cases/commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous.md)
>
> **Status:** verdict filed, 2026-10-25. **Unit: Confirmed — caps** (unit re-run "run 1b" of 2026-10-25 at the re-frozen version
> `b382ecfa…a364`, after the user-authorised amendment of B2f (iii); B2g row 1; §7, §8). **Cluster: Confirmed — caps** (run 1; closed, not re-run).
> The run-1 unit verdict below (Not confirmed) stays on record as filed.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous/`](../harness/commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous/).
>
> **Run-1 status (as filed 2026-10-25):** verdict filed, 2026-10-25. **Unit: Not confirmed — caps** (no B2g row fits. Every size relation held: at S = 2, 8 and 32 MiB every commit-log file was exactly S bytes and every live segment mapping was exactly S; onDiskSize = files × S; n_w = 4 in every arm; the default `max_mutation_size` was S/2 and an S/2 + 1 KiB insert was refused with `MutationExceededMaxSizeException`, count +1; `0MiB`/`2048MiB` refused, `1MiB`/`2047MiB` accepted; control (a) held. But the frozen relation B2f (iii), "every active and spare segment buffer is a `MappedByteBuffer` of capacity S", failed as worded: 3 of the 5 active segments at each reading had no buffer at all, because a full segment is synced, closed and unmapped. That was an audit mistake in the amendment, and the source shows it (§4.2). **Cluster: Confirmed — caps** (B3g row 1. At S = 8, 32 and 64 MiB, all 1,185, 580 and 461 file-samples were exactly S, and the JVM's mapped-buffer total was Count × S in every sample (max Count 2, 2, 3). TotalCommitLogSize was a multiple of S throughout. S/2 + 1 MiB was refused as an oversized mutation (count +1) and S/2 − 1 MiB was accepted. `0MiB`/`2048MiB` stopped startup with rc 3 and the traced messages. The LZ4 control held: no mappings, files below S, same mutation boundary). No run 2.
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-25, on the advisor's machine (`environment-advisor.md`).
> The verdict is against this file's own predictions and conclusions. `ConfigProbe.java` was copied unchanged from the
> `index_summary_capacity-applySimpleConfig` harness. `unit-run.sh`, `cluster-run.sh`, `seg-sampler.py` and `CLSampler.java` were
> adapted from the `index_summary_capacity` and `cdc_total_space` harnesses (copied, then changed in the copy). No reading from those cases is used here.

**What the constraint is (kept apart throughout).** `commitlog_segment_size` fixes the size of **each** commit-log segment: its file
and, in the default mmap mode, its mapping. By default it also sets `max_mutation_size` to S/2. It does **not** cap the total
commit log, which `commitlog_total_space` governs (flush-to-reclaim, `AbstractCommitLogSegmentManager.java:246-248`). Here "caps" means
"caps the per-segment footprint", and the total is recorded as INFO only.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `0dcdfe0` (sha256 `76546d40…6334`, checked equal to the filed row before the audit). Frozen after the step-0 audit's seventeen amendments (2026-10-25, before any harness run or reading): sha256 **`463ab140cf316683e6726f39878b88d94ee340b6cb2b313e9eaf825b710aaa59`**, added as a new row in `_INDEX.md` §4 and re-checked unchanged after both tiers. Both tiers' run 1 ran at this version. No runbook fix was needed. Section D was filled after the hash. Nothing is committed (no commit was asked for); base commit `4b93658`. |
| **Harness** | [`../harness/commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous/`](../harness/commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous/):<br>• `ConfigProbe.java` (copied unchanged)<br>• `SegmentSizeProbeTest.java` (CQLTester mechanism test)<br>• `unit-run.sh`<br>• `seg-sampler.py` (1-s commit-log directory sampler: apparent `st_size`, allocated `st_blocks`×512, events)<br>• `CLSampler.java` (one-connection JMX sampler: `TotalCommitLogSize`, `OverSizedMutations`, `java.nio` `mapped` pool Count/TotalCapacity, heap)<br>• `bigwrite.py` (the two large inserts, bundled driver, protocol 5, prepared statement)<br>• `cluster-run.sh`, `cluster-readings.py`<br>• `selfcheck.py` (independent)<br>Instrument checks before run 1: `SegmentSizeProbeTest` and `CLSampler` compiled against the run clone (`instrument-compile.log`, rc 0); `bash -n` and `py_compile` passed.<br>Cluster shakedown `sd` (8 MiB, 200,000 rows; a harness check, not a reading): the first attempt found harness defect H1 (driver path); `shakedown2` ran end to end ([`shakedown/`](commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous/shakedown/)).<br>**Bound check against the shakedown:** 471/471 file-samples at S; mapped TotalCapacity = Count × S = 2 S in 49/49 samples, so with `disk_access_mode: standard` nothing else is mapped and (iv) is measurable; TotalCommitLogSize a multiple of S in 49/49; id span 28 for 200,000 rows (≥ 10 holds a fortiori at 2,000,000); 5 MiB refused with `Rejected an oversized mutation (5242936/4194304)` and +1, 3 MiB accepted, so the transport no longer intercepts. No bound was changed.<br>Self-check: [`run1/selfcheck.out`](commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous/run1/selfcheck.out). |
| **Tiers and values** | **Unit (B2):**<br>• ConfigProbe `0MiB`, `1MiB`, `32MiB`, `2047MiB`, `2048MiB`, `512KiB`, then `getMaxMutationSize` for `1MiB`, `32MiB`, `2047MiB`, each in its own `java`.<br>• Mechanism JVMs S = 2, 8, 32 MiB plus control `2MiB` + `max_mutation_size: 512KiB`, each one `ant testsome` with `memtable_heap_space: 512MiB`.<br>• R = 3 S / 64 KiB rows, then the refused and accepted large inserts.<br>**Cluster (B3):** one node, 2 GiB heap.<br>• `z0`, `z2048` (start-up refusal); `s8`, `s32` (shipped default, no line), `s64`.<br>• Control `lz4` (8 MiB + LZ4).<br>• Each arm: stress 2,000,000 × 1 KiB writes, then S/2 ± 1 MiB inserts.<br>• Held fixed: `commitlog_total_space: 1024MiB`, `disk_access_mode: standard`, `native_transport_max_message_size: 64MiB`, in-flight limits 128 MiB. |
| **Audit bottom line** | **Ready after amendments**, 2026-10-25. |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Estimate, A2: bytes of each segment file and each segment mapping (`MemoryMappedSegment.java:62-63`); the per-segment cap is kept apart from the total (`commitlog_total_space`, A3 step 4). |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly → Met after amendment | Unit had S ∈ {2, 8} and the cluster had {8, 64}; neither tier included the default 32 MiB. Amendments B2b and B3b add 32 MiB to both. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | Files are measured directly (`File.length`, `st_size`). The cluster's `/proc/<pid>/smaps` does not exist on macOS, so amendment B3d uses the JVM's own `mapped` buffer-pool account, made specific to segments by `disk_access_mode: standard`; the OS mapping table is the named gap (`vmmap` needs `sudo`). Unit mapping capacity is read by reflection (B2d). Allocated blocks are INFO: on macOS the JDK grows the mapped file with `ftruncate`, so APFS allocates lazily. |
| A. Core question | usage driven to the limit and past it | Met | Each segment is filled and rolled over: unit 3 S of data per arm; cluster ≈ 2.1 GB per arm (34–261 segments). The mutation boundary is tested on both sides of S/2. |
| B. Logic | each step says what it establishes | Partly | B2e/B3e list steps, and the readings tables carry the meaning. Left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | Exact forms were added for each relation. "≤ 1024 MiB + a few S" is not numeric and belongs to another constraint, so it became INFO (B3f). |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | B2g and B3g had four and three rows. Added: Refuted (a) and (b), read-back mismatch / Invalid, control failure, refusal by the transport (Invalid), limit not reached. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Sizes = S across three S values. The disallow branches are the `ConfigurationException`s at lines 891/894, `MutationExceededMaxSizeException` with `OverSizedMutations` +1, and `CommitLogSegment.allocate` returning −1, shown by n_w ≥ 4 and the segment ids rolling over. |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | B2h (a) is exact: an explicit `max_mutation_size` moves the boundary but not the segment size. B2h (b): "≈ 4×" is replaced by n_w ∈ [4, 6]. B3h: "files smaller than S" is not source-guaranteed for incompressible values, so it is replaced by no mapping, a file below S, and the same boundary. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Added which CQL path validates (`SingleTableUpdatesCollector.java:112`), why one JVM per configuration is needed (`IMutation.java:31`), and that the default native message limit is S/2 (`DatabaseDescriptor.java:903-905, 3237-3244`). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | Exact rows and blob sizes, stress command, driver settings, sampler periods, arm order and waits (B2c–B2e, B3c–B3e). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met after amendment | The `/local/...` paths and `/proc` were replaced by this host's clone, probe and node paths and the JMX/file samplers (B2a, B3a, B3d, B4). |
| D. Runnable | workload arithmetic reaches the limit | Partly → Met after amendment | Filed B3c: for S = 8 MiB, a 5 MiB blob was "below the default native message limit". **Wrong**: the default is min(max_mutation_size, in-flight) = 4 MiB, so the request would have been refused by the transport before the check. Amendment B3a sets 64 MiB and 128 MiB in-flight in every arm. Disk: ≤ 3 GB per arm against 147 GiB free. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked in `~/cassandra-src` at `cassandra-5.0.9`: `DatabaseDescriptor.java:533-551, 649-656, 891-916, 1486-1528, 2827-2830, 2875-2890, 3237-3245`, `Config.java:389-407`, `MemoryMappedSegment.java:40-113`, `CommitLogSegment.java:93, 141-172, 201-256, 320-345, 430-436, 505-526`, `CommitLogSegmentManagerStandard.java:31-70`, `AbstractCommitLogSegmentManager.java:81-111, 432-443`, `FileDirectSegment.java:36-52`, `CompressedSegment.java:44-120`, `Mutation.java:169-176`, `IMutation.java:31`, `MutationExceededMaxSizeException.java:32-60`, `SingleTableUpdatesCollector.java:97-117`, `CommitLog.java:300-325`, `CommitLogMetrics.java:50-80`, `CassandraDaemon.java:745-768`, `test/conf/cassandra.yaml:1-13`. Two citation lines in the amendments were corrected against the clone before the freeze. **Missed at the audit:** `CommitLogSegment.java:320-345, 510-526` with `MemoryMappedSegment.java:108-113`. A full segment is synced, closed and unmapped (buffer set to null). This is what made the amended B2f (iii) wrong (§4.2). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone `cassandra-run15`; ConfigProbe copied with the JDK 11 flags; one `ant testsome` per configuration; `memtable_heap_space: 512MiB` | Amendment 2026-10-25 | The paths did not exist. Initialisation runs once per JVM, and `IMutation.MAX_MUTATION_SIZE` is static. A flush in the 32 MiB arm would discard segments. |
| 2 | B2b: add the default 32 MiB and `getMaxMutationSize` probes; add the control JVM | Amendment 2026-10-25 | Group A. |
| 3 | B2c: exact rows and blob sizes; the internal CQL path validates | Amendment 2026-10-25 | Exactness. |
| 4 | B2d: read-back, mapping capacity by reflection, n_w, switch count, allocated (INFO), refusal details | Amendment 2026-10-25 | Group A real resource; B. |
| 5 | B2e: order | Amendment 2026-10-25 | Open. |
| 6 | B2f: exact forms (i)–(vi) | Amendment 2026-10-25 | Group B. (iii) was worded wrongly (§4.2). |
| 7 | B2g: verdict rows | Amendment 2026-10-25 | Group B. |
| 8 | B2h: control (a) exact; (b) replaced by n_w ∈ [4, 6] | Amendment 2026-10-25 | "≈ 4× with the same row count" cannot be exact with a spare and a partial first segment. |
| 9 | B3a: this host; `disk_access_mode: standard`; native message 64 MiB and in-flight 128 MiB in every arm | Amendment 2026-10-25 | The default message limit is S/2, which would refuse the S/2 + 1 MiB request before the check. Standard disk access isolates the segment mappings. |
| 10 | B3b: arms `z0`, `z2048`, `s8`, `s32` (default), `s64`, `lz4`, shakedown `sd` | Amendment 2026-10-25 | Group A. |
| 11 | B3c: exact stress command; prepared driver insert | Amendment 2026-10-25 | Exactness. |
| 12 | B3d: `mapped` buffer pool instead of `/proc/smaps`; JMX sampler instead of `sjk`; file sampler | Amendment 2026-10-25 | macOS has no `/proc`; `sjk` can exit 0 on failure. |
| 13 | B3e: order and waits | Amendment 2026-10-25 | Exactness. |
| 14 | B3f: exact (i)–(vii); creation-instant rule; total → INFO | Amendment 2026-10-25 | Group B. |
| 15 | B3g: verdict rows | Amendment 2026-10-25 | Group B. |
| 16 | B3h: control expectations the source guarantees | Amendment 2026-10-25 | "Files smaller than S" is not guaranteed for incompressible values. |
| 17 | B4: this host's cleanup | Amendment 2026-10-25 | `/local` paths. |
| 18 | B2e/B3e steps do not say what each establishes | Left for stage 3 | Not needed for a valid run. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-25. Unit 12:35–12:37 EDT; shakedowns 12:38–12:41; cluster 12:43–12:49 EDT. |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab. |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64; 10 cores, 32 GiB RAM.<br>Internal SSD (APFS, `/dev/disk3s1`): 147 GiB free at the start and before the cluster (re-checked; the harness requires ≥ 20 GiB).<br>Loopback 127.0.0.1–.3 present (re-checked, `run1/cluster/env-check-before-cluster.txt`; one node used, 127.0.0.1).<br>Ports 7000/7199/9042/9091 free and no `CassandraDaemon` before the run; re-checked by the runner and at the end (§8). |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64).<br>ConfigProbe: `java -Xms1G -Xmx1G` + the 17 JDK 11 module flags.<br>Test: `ant testsome` forks with `-Xmx1024m` (build.xml).<br>Node: `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`. |
| Ant | 1.10.18 |
| Local `cassandra-src` clone commit | `$W/cassandra-run15` = `~/Library/Caches/stage4/cassandra-run15`, `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), built with `ant -Dlocal.repository=$W/m2 build-test` (`BUILD SUCCESSFUL`, 50 s). |
| Case-file commit / harness commit | Filed `0dcdfe0`. Amendments, harness and results are uncommitted (sha256 in §1). |
| Storage for node data | Local SSD, `$W/node-cls/{data,commitlog,hints,saved_caches,cdc_raw}`, wiped before and after each arm. Unit test data under `$C/build/test/cassandra` (removed by the harness). ConfigProbe data under `$W/probe-cls/data` (removed). No tmpfs and no fixed-size image is needed: nothing here depends on free space. |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/commitlog_segment_size-applySimpleConfig/`:<br>• `clone-build-run15.log`, `instrument-compile.log`<br>• `unit-run.out`; `unit/` (`p1-*.out`, `ant-*.log`, `TEST-*.xml`, `TEST-*.log`, `stage4.out`, `summary.txt`, `commands.log`, yaml diffs)<br>• `cluster-shakedown/`, `cluster-shakedown2/` (not evidence); `cluster-run1.attempt-aborted-precheck/` (H2, no reading)<br>• `cluster-run1/` (`summary.txt`, `readings.txt`, `commands.log`; per arm `system.log`, `debug.log`, `node.out`, `settings.txt`, `seg.csv/.files/.events`, `jmx.csv`, `stress.log`, `big.txt`, `readback.txt`)<br>• `env-check-before-cluster.txt`, `selfcheck.out` |

## 3. Runbook defects

None. Every step of B2a–B2e and B3a–B3e ran as written at the frozen version.

Harness defects (H rows: no case-file change, no effect on a reading) and the re-freeze after run 1 (R1, a case-file amendment authorised by the user, added 2026-10-25 by the unit re-run session):

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| H1 | shakedown | B3c | `bigwrite.py` put the driver zip itself on `sys.path`. The zip holds `cassandra-driver-3.29.0/`, so `import cassandra` failed and no large insert ran. | Insert `<zip>/cassandra-driver-<ver>`, as `bin/cqlsh.py` does; `shakedown2` then ran end to end. | 2026-10-25, before run 1 | none |
| H2 | run 1, cluster (first launch) | B3e pre-check | The runner's `ps … \| grep '[C]assandraDaemon'` matched the launching shell's own command line, which contained the words "no CassandraDaemon". The runner aborted at its pre-check, before any node started. | Relaunched from a command line without that word (directory kept as `cluster-run1.attempt-aborted-precheck/`) | 2026-10-25 | none |
| R1 | unit run 1 (reading, not a runbook defect) | B2f (iii) | the audit's wording of (iii), "every active and spare segment buffer is a `MappedByteBuffer` of capacity S", was wrong: full segments are synced, closed and unmapped, so 3 of 5 listed segments had no buffer; no B2g row fitted and the unit tier was Not confirmed (§4.2) | **Re-freeze, authorised by the user (Yang, the advisor) on 2026-10-25:** dated amendment `Amendment 2026-10-25 (after run 1, authorised by the user) — B2f (iii)` ((a) every listed segment holding a buffer maps exactly S; (b) a spare, if present, holds one; (c) p ≤ m ≤ n_active + p; re-derived from the source) and the dependent B2g wording plus one Not-confirmed row; new sha256 `b382ecfa…a364` as a new row in `_INDEX.md` §4; the whole unit tier re-run from its beginning in a fresh clone `$W/cassandra-run17` (§7). B1, the other B2f relations, B2h and B3 unchanged; the cluster tier stays closed | user, 2026-10-25 | uncommitted (no commit asked for) |
| H3 | unit re-run | B2f (iii) evaluation | `selfcheck.py` evaluates (iii) in run 1's wording | `selfcheck-unit-rerun.py`: a copy with the cluster part removed and (iii) evaluated as amended (run 1's wording printed as INFO). `selfcheck.py`, `unit-run.sh`, `SegmentSizeProbeTest.java` and `ConfigProbe.java` unchanged (the runner takes the clone and log paths from `C`, `L`, `P`). Known-answer check on run 1's raw unit logs: 33/33 relations computed, the INFO line reproduces run 1's 6 null-buffer lines per JVM (`run1b-unit/selfcheck-known-answer-on-run1.out`) | AI, 2026-10-25 | n/a (harness) |

## 4. Run 1

**Scope:** both tiers, every value in §1. **Command logs:** `run1/unit/commands.log`, `run1/cluster/commands.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, `stage4.out`, `p1-*.line`, `TEST-*.xml`; all four `ant testsome` rc 0, `Tests run: 1, Failures: 0, Errors: 0`, 14 s each)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| ConfigProbe `0MiB` | `REJECT ConfigurationException: commitlog_segment_size must be positive, but was 0MiB` | `p1-0MiB.line` |
| ConfigProbe `2048MiB` | `REJECT ConfigurationException: commitlog_segment_size must be smaller than 2048, but was 2048MiB` | `p1-2048MiB.line` |
| ConfigProbe `512KiB` | `REJECT … Invalid data storage: 512KiB Accepted units:[MEBIBYTES, GIBIBYTES]` (refused at yaml load) | `p1-512KiB.line` |
| ConfigProbe `1MiB` / `32MiB` / `2047MiB` | `OK getCommitLogSegmentSize=` 1048576 / 33554432 / 2146435072 | `p1-1MiB.line`, `p1-32MiB.line`, `p1-2047MiB.line` |
| getMaxMutationSize `1MiB` / `32MiB` / `2047MiB` | 524288 / 16777216 / 1073217536 | `p1-*-mms.line` |

| Reading (per JVM) | 2 MiB | 8 MiB | 32 MiB | 2 MiB + mms 512 KiB |
|---|---|---|---|---|
| (i) S / max mutation / `IMutation.MAX` / mode / class | 2,097,152 / 1,048,576 / = / mmap / MemoryMappedSegment | 8,388,608 / 4,194,304 / = / mmap / MMS | 33,554,432 / 16,777,216 / = / mmap / MMS | 2,097,152 / **524,288** / = / mmap / MMS |
| rows R, all ok; table switches | 96, 96; 0 | 384, 384; 0 | 1,536, 1,536; 0 | 96, 96; 0 |
| (ii) files at the two readings: count, all = S | 5 and 5, **all S** | 5 and 5, **all S** | 5 and 5, **all S** | 5 and 5, **all S** |
| (iv) onDiskSize = files × S; k | 10,485,760 = 5 S; 5 | 41,943,040 = 5 S; 5 | 167,772,160 = 5 S; 5 | 10,485,760 = 5 S; 5 |
| (v) n_w (segment ids spanned by the R rows) | **4** | **4** | **4** | **4** |
| (iii) segment buffers at each reading after the workload (4 active + 1 spare; see the note) | 2 mapped, capacity **S**; 3 closed with **buffer null** | same | same | same |
| before the workload (INFO) | 2 files, 2 mapped (active + spare), capacity S | same | same | same |
| (vi) refused insert (blob, message, Δcount) | 1,049,600 B: `MutationExceededMaxSizeException`, `(1049655/1048576)`, +1 | 4,195,328 B: `(4195384/4194304)`, +1 | 16,778,240 B: `(16778296/16777216)`, +1 | 983,040 B: `(983095/524288)`, +1 |
| (vi) accepted insert (blob, Δcount, row read back) | 983,040 B, 0, yes | 4,128,768 B, 0, yes | 16,711,680 B, 0, yes | 458,752 B, 0, yes |
| INFO: allocated bytes per file (`stat -f %b` × 512) | written segments S, unwritten (latest, spare) 0 | same | same | same |
| INFO: JVM `mapped` pool | count 4, capacity 2 S + 19 B (two SSTable-index mappings, `mmap_index_only` in the test yaml) | 4, 2 S + 19 | 4, 2 S + 19 | 4, 2 S + 19 |

Note to (iii). At each reading after the workload, `getActiveSegments()` listed 4 segments and the spare made a 5th. The 3 oldest active segments were full, synced and closed, and their `buffer` was null (`capacity=-1`, `mapped=false`). The allocating segment and the spare were `MappedByteBuffer`s of capacity S. **No mapping of any other size existed** (`stage4.out`, `segment tag=…` lines).

**Cluster tier** (`run1/cluster/summary.txt`, `readings.txt`, `<arm>/{settings.txt, mode-lines.txt, seg.csv, seg.events, jmx.csv, big.txt, stress-results.txt}`; z arms `node.out`, `system-log-lines.txt`)

| Observable | z0 | z2048 |
|---|---|---|
| (i) exit, time, `Startup complete` | rc **3** after 1 s, none | rc **3** after 1 s, none |
| (i) message (node.out and system.log) | `Exception (org.apache.cassandra.exceptions.ConfigurationException) encountered during startup: commitlog_segment_size must be positive, but was 0MiB` | `… commitlog_segment_size must be smaller than 2048, but was 2048MiB` |

| Observable | s8 (`8MiB`) | s32 (default) | s64 (`64MiB`) | lz4 (`8MiB` + LZ4) |
|---|---|---|---|---|
| (ii) settings `commitlog_segment_size` / `max_mutation_size`; mode resolved | 8MiB / 4096KiB; mmap | 32MiB / 16384KiB; mmap | 64MiB / 32768KiB; mmap | 8MiB / 4096KiB; **standard** (`commitlog_compression=LZ4Compressor` in the node configuration line) |
| stress: partitions, errors, rate | 2,000,000, 0, 57.5 k/s | 2,000,000, 0 | 2,000,000, 0 | 2,000,000, 0, 61.0 k/s |
| (iii) file-samples (samples) at size S; other | **1,185 / 1,185** (78); 0 (no creation-instant zero seen) | **580 / 580** (76); 0 | **461 / 461** (77); 0 | 0 of 1,318: sizes 83 B … 8,158,712 B (control) |
| (vii) distinct segments / id span | 260 / 261 | 67 / 67 | 34 / 34 | 258 / 261 |
| (iv) `mapped` TotalCapacity: positive multiple of S; = Count × S; max Count | 77/77; 77/77; 2 | 75/75; 75/75; 2 | 77/77; 77/77; 3 | **0 in 75/75** (control a) |
| (v) TotalCommitLogSize multiple of S; max (INFO) | 77/77; 256 MiB | 75/75; 416 MiB | 77/77; 576 MiB | not a multiple (compressed sizes); max 233.7 MiB |
| (vi) S/2 + 1 MiB insert | 5,242,880 B **refused**: `InvalidRequest … Rejected an oversized mutation (5242936/4194304)`, Δ +1 | 17,825,792 B refused `(17825848/16777216)`, +1 | 34,603,008 B refused `(34603064/33554432)`, +1 | 5,242,880 B refused `(5242936/4194304)`, +1 |
| (vi) S/2 − 1 MiB insert | 3,145,728 B accepted, Δ 0, read back | 15,728,640 B accepted, 0, yes | 32,505,856 B accepted, 0, yes | 3,145,728 B accepted, 0, yes |
| INFO: allocated per file-sample = S / 0 / partial; > apparent | 1,135 / 50 / 0; 0 | 444 / 43 / 93; 0 | 316 / 57 / 88; 0 | — / — / 1,318 (block rounding); 1,318 |

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity.** The run was valid:
   - The knob was applied in every JVM, by read-back of S, max mutation and access mode (i) [observed: `stage4.out` `run` lines].
   - Every row succeeded and the table never flushed [observed: `workload … ok=R switches=0`].
   - Each arm filled more than three segments [observed: n_w = 4, k = 5].
   - The held-fixed `memtable_heap_space: 512MiB` and the knob line are in the yaml diffs [observed: `p2-yaml-diff-*.txt`].
2. **Readings.** One relation failed as worded: (iii). After the workload, 3 of the 5 segments at each reading had a null buffer [observed: `stage4.out` `segment … mapped=false capacity=-1`]. The reason is in the source: when a segment is full, `sync` allocates no further marker and sets `close = true` (`CommitLogSegment.java:327-332`), and `internalClose` unmaps it (`FileUtils.clean(buffer)`, `MemoryMappedSegment.java:108-113`) and sets `buffer = null` (`CommitLogSegment.java:520-526`) [inferred: source read after the reading]. The audit did not read these lines when it worded (iii). No other reading is unusual.
3. **Matched row.** None. The first row needs "(i)–(vi) all hold", and (iii) failed. The Refuted row needs "a file length or a segment mapping ≠ S", and no file or mapping had another size: every one of the 40 file lines was S, and every existing mapping had capacity S [observed: `stage4.out`]. Read with its words, a closed segment has no mapping, not one ≠ S. No other row applies (below). Per the README, when no row fits the prediction missed an outcome. The README would allow a dated amendment and a restart of the tier. The session instructions forbid editing a prediction after a reading, so (iii) stays as frozen and the tier is filed **Not confirmed**, following the file's own wording.
4. **Excluded rows.**
   - Refuted (sizes): every file length = S at 2, 8 and 32 MiB, so the sizes follow S [observed].
   - Refuted (b): every S/2 + 1 KiB insert was refused [observed].
   - Refuted (a): 0/2048 were refused and 1/2047 accepted [observed: `p1-*.line`].
   - Invalid (read-back): (i) held [observed].
   - Invalid (control / n_w): control (a) held, with the 983,040-byte insert refused against max 524,288 and 458,752 accepted; n_w = 4 ∈ [4, 6] [observed].
   - Not confirmed (wrong class or Δ ≠ 1): the class was right and Δ = 1 [observed].
5. **Observed vs. inferred.** The cause of the (iii) failure (closed segments are unmapped) is inferred from the source. It does not change the readings.
6. **Deviations and gaps.** None in the procedure. Allocated bytes are INFO only: the written segments allocate S and the unwritten ones allocate 0.
7. **Core question.** At each of 2, 8 and 32 MiB, every commit-log file was S and every live mapping was S [observed]. The data spanned the same 4 segments per 3 S whatever S was, so segments roll over at S. Mutations over S/2 were refused through the derived default. The per-segment footprint follows the knob, and the closed segments' unmapping only lowers mapped memory below "segments × S". **Effect: caps (per segment)**. The verdict is Not confirmed only because the frozen (iii) over-claimed for closed segments.

**Conclusion (one line):** no B2g row fits → **Not confirmed**. Effect: caps (per-segment file and live mapping = S; default max mutation S/2).

**Cluster tier**

1. **Validity.** The run was valid:
   - Read-back (ii) held in all four running arms [observed: `settings.txt`, `mode-lines.txt`].
   - Stress wrote 2,000,000 partitions with 0 errors [observed: `stress-results.txt`].
   - The limit was reached: 34–261 segments per arm were created and rolled over [observed: `readings.txt`, (vii)].
   - The held-fixed lines are in each arm's `YAML` summary line [observed: `summary.txt`].
2. **Readings.**
   - No creation-instant zero was ever sampled: the rule was never needed [observed].
   - The max mapped Count was 3 at s64, consistent with the allocating segment, the spare and one full segment not yet synced [inferred].
   - The total commit log peaked at 256/416/576 MiB, under 1,024 MiB (INFO; a separate constraint).
3. **Matched row.** B3g row 1, "(i)–(vii) hold in s8, s32, s64 and the B3h control holds":
   - (i): z0 and z2048 exited with rc 3 and the traced messages.
   - (ii): read-back as above.
   - (iii): every file-sample = S.
   - (iv): TotalCapacity = Count × S in every sample (100 %, allowance 1 %).
   - (v): TotalCommitLogSize a multiple of S in every sample.
   - (vi): refused with `Rejected an oversized mutation (n/S/2)` and Δ +1; accepted with Δ 0 and the row read back.
   - (vii): spans 261/67/34 ≥ 10, 2,000,000 partitions, 0 errors.
   - B3h: (a) capacity 0 in 75/75 samples; (b) 1,318 file-samples below S; (c) same boundary [all observed: `readings.txt`, `selfcheck.out`].
4. **Excluded rows.**
   - Refuted (sizes): 0 file-samples ≠ S and 0 mapping samples ≠ Count × S.
   - Refuted (b): S/2 + 1 MiB was refused in every arm.
   - Refuted (a): z0 and z2048 did not start.
   - Invalid (refused elsewhere): every refusal message is the oversized-mutation text, with OverSizedMutations +1. The 64 MiB transport limit was not involved.
   - Invalid (read-back, (vii), control): all held.
   - The total-space row is INFO.
5. **Observed vs. inferred.**
   - That each `mapped` pool entry is a segment rests on `disk_access_mode: standard` (no SSTable mappings) [inferred from `DatabaseDescriptor.java:533-551`]. It is supported by the lz4 arm, which had 0 mappings, and by the idle readings, which showed 2 mappings = active + spare [observed: `readback.txt`].
   - The pool's capacity is the JVM's account of `FileChannel.map` sizes, not the OS mapping table (named gap).
6. **Deviations and gaps.**
   - `commitlog_compression` is not in `system_views.settings`. For lz4 it was read back from the node-configuration log line and from `resolved to: standard`.
   - Allocated bytes are INFO. APFS allocated lazily: unwritten segments were 0 and partly written ones were partial. Allocation never exceeded the apparent size in the mmap arms.
7. **Core question.**
   - At 8, 32 and 64 MiB, every segment file on disk and every segment mapping in the JVM was exactly S, so usage per segment follows the constraint [parts 3, 5].
   - Without the mmap path (LZ4), files are not pre-sized and nothing is mapped. The exact-S footprint belongs to the legacy/mmap path the trace names [B3h].
   - The derived default `max_mutation_size` = S/2 refuses larger mutations [part 3].
   - The total commit log is governed by `commitlog_total_space`, not by this knob (INFO).

**Conclusion (one line):** B3g row 1 → **Confirmed**. Effect: caps (per segment).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`selfcheck.py` is a separate script. It re-reads the raw `p1-*.out`, `stage4.out`, `node.out`, `settings.txt`, `system.log`,
`seg.files` (every file of every sample), `jmx.csv`, `big.txt` and `stress.log`, not `summary.txt` or `readings.txt`, and re-evaluates every frozen
relation. Result: **57 relations, 53 hold, 4 fail — exactly the four unit (iii) relations** (one per JVM: 6 segment lines without
a mapping of S, all with capacity −1, and 0 mappings of another size) ([`run1/selfcheck.out`](commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous/run1/selfcheck.out)).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Unit read-back, rows, switch count and n_w recomputed from the segment ids. Cluster read-back, stress totals and id spans recomputed from `seg.files`. |
| 2. Readings | yes | The (iii) failure is confirmed: 6 null-buffer lines per JVM. The source lines cited for its cause were re-opened (`CommitLogSegment.java:327-332, 520-526`, `MemoryMappedSegment.java:108-113`). |
| 3. Matched row | yes | Unit: no row fits. Neither row 1 (needs (iii)) nor Refuted (needs a size ≠ S; none found) applies, so the tier is Not confirmed. Cluster: all relations of row 1 hold. |
| 4. Excluded rows | yes | Every Refuted condition is false in the raw files (0 sizes ≠ S, refusals present, start-up refused). |
| 5. Observed vs. inferred | yes | The mapped-pool-is-segments inference is consistent with lz4 = 0 and idle = 2 mappings (`readback.txt`). |
| 6. Deviations and gaps | yes | The compression read-back comes from the configuration line (`compression-config.txt`). |
| 7. Core question | yes | Unit and cluster both show per-segment sizes = S across three S values. The unit verdict stays Not confirmed because a frozen relation failed as worded, not because a size contradicted the claim. |

### 5.2 Run 2?

**No**, decided 2026-10-25. Both tiers rest on direct observations re-derived by the independent script. The only failure is a wording
error of a frozen relation, and its cause is shown by the source; a repeat of the same runbook would fail it the same way. A re-run of the
unit tier after a corrected (iii) is a matter for the user (§8).

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Unit re-run ("run 1b") after the B2f (iii) amendment — 2026-10-25

Added by a stage-4 session, Claude Opus 5.5 (claude-opus-5-5), 2026-10-25, **authorised by the user (Yang, the advisor) on 2026-10-25**.
Sections 1–6 above are run 1 as filed and are not changed. Run 1's excerpts under `run1/` are untouched. The cluster tier is closed and
was not re-run.

### 7.1 Frozen version and harness

| Field | Content |
|---|---|
| **Why** | In unit run 1, relation (iii) as worded at the audit failed: full segments are closed and unmapped. No B2g row fitted, so the tier was Not confirmed (§4.2). The README says a wrong §9a "is a dated amendment to the case file and the affected tier starts again". The user authorised the amendment and a re-run of the whole unit tier on 2026-10-25. |
| **Amendment** | `Amendment 2026-10-25 (after run 1, authorised by the user) — B2f (iii)`, placed under the B2f amendment in the case file. It says plainly that it follows a run-1 reading. It re-derives from the source which segments hold a mapping:<br>• A segment's buffer is assigned once, from `channel.map(…, 0, S)` (`CommitLogSegment.java:168`, `MemoryMappedSegment.java:58-64`). It is set to null only in `internalClose` after `FileUtils.clean` (`CommitLogSegment.java:520-526`, `MemoryMappedSegment.java:108-113`). So a segment holds one mapping of S or none.<br>• The spare (`availableSegment`, at most one, `AbstractCommitLogSegmentManager.java:81, 108, 181, 189`) is not in `activeSegments` until it is taken (`:307-312`). The sync loop never reaches it (`:625-635`), so it is closed only by `discardAvailableSegment` (`:573-583`).<br>• A left segment has its tail discarded (`:330`, `CommitLogSegment.java:258-287`). Its next sync cannot place a marker, so it closes the segment (`CommitLogSegment.java:327-332, 356-368`). The sync is periodic (10 s, `test/conf/cassandra.yaml:8-9`) and also runs on request (`:334`). The allocating segment is closed only if a sync finds less than a marker of room (`:240-247`).<br>**(iii) now reads:** (a) every listed segment holding a buffer holds a `MappedByteBuffer` of capacity exactly S; (b) a spare, if present, holds a buffer; (c) p ≤ m ≤ n_active + p, where m is the number holding a mapping and p ∈ {0, 1} is whether a spare is present. The source fixes no tighter upper bound, because the number of full segments not yet synced depends on timing.<br>Dependent B2g wording: row 2's "a segment mapping ≠ S" means a non-null buffer of capacity ≠ S. One added row: (iii)(b)/(c) failing with all sizes = S → Not confirmed.<br>Paths: clone `$W/cassandra-run17`, logs `unit-run2/`. B1, the other B2f relations, B2h and B3 are unchanged. The bounds were not chosen from run 1's counts. |
| **Case-file version** | sha256 **`b382ecfad75913a394719660f666f9f13c7f45e0dbcc27567231ae20dfbda364`**. It is a new row in `_INDEX.md` §4, "re-frozen after run 1 for unit re-run (B2f (iii)), authorised by the user". The earlier rows (`76546d40…`, `463ab140…`) are kept. Hashed before any re-run reading; section D was filled afterwards. Base commit `4838a2f`; nothing committed. |
| **Harness** | Run 1's harness with change H3 (§3) only, i.e. a new `selfcheck-unit-rerun.py`.<br>sha256 prefixes at the re-run: `unit-run.sh` `d1704171` (the runner logged the same), `SegmentSizeProbeTest.java` `b3990368`, `ConfigProbe.java` `f6243b52`, `selfcheck.py` `7854001d` (unchanged), `selfcheck-unit-rerun.py` `572acd7f` (new).<br>Command: `C=$W/cassandra-run17 P=$W/probe-cls L=$W/logs/commitlog_segment_size-applySimpleConfig/unit-run2 unit-run.sh all`. This runs all nine ConfigProbe processes, then the four mechanism JVMs in the frozen order, the control JVM included. |

### 7.2 Environment

Same host and storage as run 1 (§2). The unit tier ran 2026-10-25 16:30:05–16:31:24 EDT.

- **Clone:** fresh clone `$W/cassandra-run17` from `~/cassandra-src` at `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), no local change. `ant -Dlocal.repository=$W/m2 build-test` finished `BUILD SUCCESSFUL` in 55 s (`run1b-unit/clone-build-run17.txt`).
- **Disk:** 145 GiB free.
- **Before the run:** no `CassandraDaemon`.
- **After the run:** no `CassandraDaemon`, `ConfigProbe` or test JVM; the clone is clean (`git status` 0 entries); `$W/probe-cls` removed.
- **Full logs:** `$W/logs/commitlog_segment_size-applySimpleConfig/unit-run2/` (`commands.log`, `summary.txt`, `stage4.out`, `p1-*.out`, `ant-*.log`, `TEST-*.xml/.log`, yaml diffs). Also `unit-run2.out`, `unit-run2-build/` (clone and build log, known-answer self-check) and `selfcheck-unit-run2.out`.
- **Excerpts:** [`run1b-unit/`](commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous/run1b-unit/) (`unit/` with the same files as `run1/unit/`; `selfcheck.out`; `selfcheck-known-answer-on-run1.out`; `clone-build-run17.txt`).

### 7.3 Readings

From `run1b-unit/unit/summary.txt`, `stage4.out`, `p1-*.line` and `TEST-*.xml`. All four `ant testsome` runs returned rc 0 with `Tests run: 1, Failures: 0, Errors: 0`, 14–15 s each.

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| ConfigProbe `0MiB` | `REJECT ConfigurationException: commitlog_segment_size must be positive, but was 0MiB` | `p1-0MiB.line` |
| ConfigProbe `2048MiB` | `REJECT ConfigurationException: commitlog_segment_size must be smaller than 2048, but was 2048MiB` | `p1-2048MiB.line` |
| ConfigProbe `512KiB` | `REJECT … Invalid data storage: 512KiB Accepted units:[MEBIBYTES, GIBIBYTES]` | `p1-512KiB.line` |
| ConfigProbe `1MiB` / `32MiB` / `2047MiB` | `OK getCommitLogSegmentSize=` 1048576 / 33554432 / 2146435072 | `p1-1MiB.line`, `p1-32MiB.line`, `p1-2047MiB.line` |
| getMaxMutationSize `1MiB` / `32MiB` / `2047MiB` | 524288 / 16777216 / 1073217536 | `p1-*-mms.line` |

| Reading (per JVM) | 2 MiB | 8 MiB | 32 MiB | 2 MiB + mms 512 KiB |
|---|---|---|---|---|
| (i) S / max mutation / `IMutation.MAX` / mode / class | 2,097,152 / 1,048,576 / = / mmap / MemoryMappedSegment | 8,388,608 / 4,194,304 / = / mmap / MMS | 33,554,432 / 16,777,216 / = / mmap / MMS | 2,097,152 / **524,288** / = / mmap / MMS |
| rows R, all ok; table switches | 96, 96; 0 | 384, 384; 0 | 1,536, 1,536; 0 | 96, 96; 0 |
| (ii) files at the two readings: count, all = S | 5 and 5, **all S** | 5 and 5, **all S** | 5 and 5, **all S** | 5 and 5, **all S** |
| (iii)(a) listed segments holding a buffer: count, capacities | 2 and 2, **all S** (no other size) | 2 and 2, all S | 2 and 2, all S | 2 and 2, all S |
| (iii)(b) spare present / holds a buffer | yes / **yes** (both readings) | yes / yes | yes / yes | yes / yes |
| (iii)(c) n_active, p, m; p ≤ m ≤ n_active + p | 4, 1, 2; **1 ≤ 2 ≤ 5** (both readings) | 4, 1, 2; 1 ≤ 2 ≤ 5 | 4, 1, 2; 1 ≤ 2 ≤ 5 | 4, 1, 2; 1 ≤ 2 ≤ 5 |
| which hold a buffer | the newest active segment (the allocating tail) and the spare; the 3 older active segments have no buffer (capacity −1) | same | same | same |
| (iv) onDiskSize = files × S; k | 10,485,760 = 5 S; 5 | 41,943,040 = 5 S; 5 | 167,772,160 = 5 S; 5 | 10,485,760 = 5 S; 5 |
| (v) n_w | **4** | **4** | **4** | **4** |
| (vi) refused insert (blob, message, Δcount) | 1,049,600 B: `MutationExceededMaxSizeException`, `(1049655/1048576)`, +1 | 4,195,328 B: `(4195384/4194304)`, +1 | 16,778,240 B: `(16778296/16777216)`, +1 | 983,040 B: `(983095/524288)`, +1 |
| (vi) accepted insert (blob, Δcount, row read back) | 983,040 B, 0, yes | 4,128,768 B, 0, yes | 16,711,680 B, 0, yes | 458,752 B, 0, yes |
| before the workload (INFO) | 2 files, active + spare, both mapped, capacity S | same | same | same |
| INFO: allocated bytes per file | the 3 closed segments S; the allocating segment and the spare 0 | same | same | same |
| INFO: JVM `mapped` pool | count 4, capacity 2 S + 19 B | 4, 2 S + 19 | 4, 2 S + 19 | 4, 2 S + 19 |

### 7.4 Unit re-run — conclusion and logic

1. **Validity.**
   - The re-run used the re-frozen version (`b382ecfa…`), hashed before the run [observed: `_INDEX.md` §4].
   - It ran every ConfigProbe process and every mechanism JVM of B2, the control included, from the beginning in the frozen order, in a fresh clone [observed: `run1b-unit/unit/commands.log`, first line: clone `cassandra-run17`, `b5f2a54210…`, runner `d1704171…`].
   - Read-back (i) held in all four JVMs [observed: `stage4.out` `run` lines].
   - Every row succeeded and no table switch happened [observed: `workload … ok=R switches=0`].
   - The yaml diffs show the knob line and the held-fixed `memtable_heap_space: 512MiB` [observed: `p2-yaml-diff-*.txt`].
   - The run is valid.
2. **Readings.**
   - Every reading repeats run 1's [observed: same counts and messages as §4.1; only the segment ids differ].
   - In every JVM the full segments were already closed at the reading taken right after the workload. That fits the extra sync requested at each segment switch (`AbstractCommitLogSegmentManager.java:334`), not only the 10-s period [inferred]. The verdict does not rest on this: (iii)(c) allows any number of full segments still mapped.
   - The allocating segment and the spare were written to but never synced, so they had 0 allocated bytes. INFO: APFS allocates lazily.
3. **Matched row.** B2g row 1: "B2f ConfigProbe lines and (i)–(vi) all hold, control (B2h) holds".
   - ConfigProbe: `0MiB` and `2048MiB` were refused with the exact messages; `512KiB` was refused at yaml load; 1/32/2047 MiB were accepted with the exact byte values; max mutation was 524288 / 16777216 / 1073217536.
   - (i): read-back held.
   - (ii): 40 of 40 file lines at the two readings were S.
   - (iii): (a) every buffer that existed was a `MappedByteBuffer` of capacity S, 16 of 16 across the JVMs and readings, with no other size; (b) the spare held a buffer in 8 of 8 readings; (c) m = 2 ∈ [1, 5] in 8 of 8.
   - (iv): onDiskSize = 5 S, k = 5 ≥ 3 with switches 0.
   - (v): n_w = 4 ∈ [4, 6].
   - (vi): every refusal was `MutationExceededMaxSizeException` with max = S/2 and Δ = 1; every accepted insert had Δ = 0 and its row read back.
   - B2h (a): in the control, max mutation was 524,288. The 983,040-byte insert, accepted in the default 2 MiB JVM, was refused (+1); 458,752 B was accepted; files and mappings stayed 2 MiB.
   - All observed [`stage4.out`, `p1-*.line`, `run1b-unit/selfcheck.out`].
4. **Excluded rows.**
   - Refuted (sizes): no file length and no existing mapping ≠ S, at three values of S, and sizes followed S.
   - Refuted (b): every S/2 + 1 KiB insert was refused.
   - Refuted (a): 0/2048 were refused and 1/2047 accepted.
   - Invalid (read-back, R rows): (i) held and all rows succeeded.
   - Invalid (control, n_w): control (a) held and n_w = 4.
   - Not confirmed (class/Δ): the class was right and Δ = 1.
   - Added Not confirmed row ((iii)(b)/(c)): (b) and (c) held.
   - All observed.
5. **Observed vs. inferred.**
   - Inferred: which sync closed the full segments (part 2). It carries no verdict.
   - Inferred: that the newest active segment is the allocating one. The harness lists active segments in queue order, and the tail is `allocatingFrom` (`AbstractCommitLogSegmentManager.java:85, 311`). The amended (iii) does not use it.
   - Everything the verdict uses is observed.
6. **Deviations and gaps.**
   - None against the re-frozen runbook.
   - As in run 1, allocated bytes are INFO.
   - The JVM's `mapped` pool also holds two SSTable-index mappings (`mmap_index_only` in the test yaml), so it is INFO here. The cluster tier measured mapped memory without them.
7. **Core question.**
   - At 2, 8 and 32 MiB, every commit-log file was exactly S, and every segment mapping that existed was exactly S [parts 3].
   - The data rolled over at S: 4 segments for 3 S of data whatever S was.
   - The default `max_mutation_size` = S/2 refused larger mutations, and an explicit `max_mutation_size` moved that boundary without changing the segment size (control).
   - The constraint caps the per-segment footprint, and usage follows it. Closing a full segment unmaps it, so the live mapped memory is the allocating segment plus the spare (2 S here), plus any full segment not yet synced.

**Conclusion (one line):** B2g row 1 → **Confirmed**. Effect: caps (per segment: every file and every live mapping = S; default max mutation S/2).

### 7.5 Self-check of the unit re-run — AI

`selfcheck-unit-rerun.py <unit-run2>` re-reads the raw `p1-*.out` and `stage4.out`, not `summary.txt`. It re-evaluates every frozen B2f relation, with (iii) as amended, and B2h (a). It recomputes n_w from the segment ids.

- **Output:** [`run1b-unit/selfcheck.out`](commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous/run1b-unit/selfcheck.out). **33 relations, 33 hold, 0 fail.**
- **INFO line:** run 1's wording of (iii) would again find 6 of 10 segment lines without a buffer per JVM. That is the same physical state as run 1, now covered by the amended wording.
- **Re-opened by hand:** the 40 `segment tag=` lines of `stage4.out`. At each reading, 3 older active segments had `mapped=false capacity=-1`, and the newest active segment and the spare had `mapped=true capacity=<S>`. No other capacity appears.
- **Also re-opened:** the 40 `file tag=` lines (all `length=<S>`), the four `insert what=refused` lines (`MutationExceededMaxSizeException`, `delta=1`), `p1-0MiB.line` and `p1-2048MiB.line`, and the four `TEST-*.xml` (`tests="1" failures="0" errors="0"`).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-frozen hash recorded before the run. Read-back, rows and switch count re-read. Clone and runner hash in `commands.log` line 1. |
| 2. Readings | yes | Same counts and messages as run 1; only the segment ids differ. |
| 3. Matched row | yes | Every row-1 relation holds in the independent script, (iii) as amended and control (a) included. |
| 4. Excluded rows | yes | Every Refuted, Invalid and Not-confirmed condition is false in the raw files. |
| 5. Observed vs. inferred | yes | The two inferences are labelled and carry no verdict. |
| 6. Deviations and gaps | yes | None against the runbook; INFO items stated. |
| 7. Core question | yes | Per-segment file and mapping = S at three values of S; boundary S/2. |

**Run 2?** No, decided 2026-10-25. The verdict rests on direct observations that the independent script reproduces, and the re-run repeats run 1's readings exactly. Run 1 was an independent repeat of the same runbook, at the earlier frozen version.

### 7.6 Verdict of the unit re-run

**Confirmed — caps** (B2g row 1). It is filed in §8 as a new unit row; the run-1 unit row (Not confirmed) is kept.

## 8. Verdict — AI

**Stage-3 estimate:** positive (per-segment).

**Claim tested (B1):** (a) `0MiB` and `2048MiB` prevent startup with the messages at `DatabaseDescriptor.java:892` and `:895`; `1MiB` and
`2047MiB` are accepted. (b) With segment size S, every commit-log file is exactly S bytes and every segment mapping is S bytes; a
mutation larger than S/2 (default `max_mutation_size`) is refused; total commit-log size is a multiple of S.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Not confirmed**: no B2g row fits. All size, boundary and start-up relations held (files = S, live mappings = S, onDiskSize = files × S, n_w = 4 at 2/8/32 MiB, S/2 + 1 KiB refused with +1, control (a)). Frozen B2f (iii) "every active and spare segment buffer is a mapped buffer of capacity S" failed as worded: full segments are closed and unmapped (`CommitLogSegment.java:327-332, 520-526`, `MemoryMappedSegment.java:108-113`), so 3 of 5 had no buffer | caps (per segment: file = S and every live mapping = S; default max mutation S/2; closing a full segment unmaps it, so the live mapped memory was 2 S in the unit JVMs and at most 3 S in the cluster) | run 1 + self-check | 2026-10-25 |
| Cluster | **Confirmed**: B3g row 1. At 8/32/64 MiB, 1,185/580/461 file-samples = S; mapped TotalCapacity = Count × S in every sample; TotalCommitLogSize a multiple of S; S/2 + 1 MiB refused as oversized (+1) and S/2 − 1 MiB accepted; `0MiB`/`2048MiB` rc 3 with the traced messages; LZ4 control (no mapping, files < S, same boundary) | caps (per segment; the total commit log is `commitlog_total_space`'s, peak 256–576 MiB ≤ 1,024 MiB, INFO) | run 1 + self-check | 2026-10-25 |
| Unit (re-run at `b382ecfa…`, after the user-authorised B2f (iii) amendment) | **Confirmed**: B2g row 1. ConfigProbe lines exact; (i)–(vi) hold at 2/8/32 MiB: 40/40 files = S; every existing segment mapping = S (16/16), the spare holds one in 8/8 readings, m = 2 ∈ [p, n_active + p] = [1, 5]; onDiskSize = 5 S; n_w = 4; S/2 + 1 KiB refused with `MutationExceededMaxSizeException`, +1; control (a) holds (983,040 B refused at max 524,288; 458,752 B accepted) | caps (per segment: file = S and every live mapping = S; default max mutation S/2; full segments are unmapped once synced) | unit re-run (§7) + self-check | 2026-10-25 |

**What each outcome means for a per-segment cap.** "Caps" here means each segment's file and mapping are fixed at S, and the largest
accepted mutation is S/2 by default. It does not mean a bound on the number of segments or on the total commit log. A run where the
total exceeded `commitlog_total_space` would not have refuted this claim (B3g, INFO row).

**Recommendation (not applied; the prediction is not edited after a reading).** Re-word B2f (iii) to cover only the segments that hold a mapping:
"the allocating segment and the spare (and any full segment not yet synced) each map exactly S; a closed segment has no buffer". Then
re-run the unit tier at a new frozen hash. With today's readings that tier would match row 1.

**Feedback filed:** the case file's section D was filled (uncommitted). No section was amended after the freeze. The index rows are in
`_INDEX.md` §1 (Stage 4), §2 (frozen hash row) and §3 (coverage line).

**Feedback filed for the unit re-run (2026-10-25):** the amendment `Amendment 2026-10-25 (after run 1, authorised by the user) — B2f (iii)`
and the dependent B2g amendment in the case file; a new `_INDEX.md` §4 row (`b382ecfa…`); the case file's section D (new entry); the §1
Stage 4 column (now unit and cluster Confirmed — caps). The §3 coverage line is unchanged, because the case was already counted as closed. No refutation, so no other case section is amended.
The recommendation above was applied in this form, authorised by the user.

**Processes:** after the cluster tier, `final CassandraDaemon processes: none`, no `cassandra-stress` left, `node-cls` wiped
(`run1/cluster/summary.txt`). Re-checked at the end of the session (`ps -eo command | grep '[C]assandraDaemon'` empty; ports free).

**Processes (unit re-run):** no `CassandraDaemon` before or after; no `ConfigProbe` or test JVM left (`run1b-unit/unit/commands.log`: `no ConfigProbe left`); clone `cassandra-run17` clean after the runner restored its test yaml and removed the probe test; `$W/probe-cls` removed. Re-checked at the end of the session.
