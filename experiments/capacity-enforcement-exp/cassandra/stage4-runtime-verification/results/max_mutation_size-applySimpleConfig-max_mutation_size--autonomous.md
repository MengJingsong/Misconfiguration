# max_mutation_size-applySimpleConfig-max_mutation_size--autonomous — stage-4 results  <!-- file: results/max_mutation_size-applySimpleConfig-max_mutation_size--autonomous.md -->

> **Case:** [`max_mutation_size-applySimpleConfig-max_mutation_size--autonomous`](../../stage3-ai-deep-read/cases/max_mutation_size-applySimpleConfig-max_mutation_size--autonomous.md)
>
> **Status:** verdict filed, 2026-10-25. **Unit: Confirmed — caps** (B2g row 1. ConfigProbe accepted 2M = S and refused 2M = S + 2 KiB at S = 8 and 32 MiB with the traced message; unset gave S/2. In each of the four mechanism JVMs (M = 1,048,576 / 1,050,624 / 2,097,152 / 2,621,440 B at S = 5 MiB), M + 1 KiB was refused with `MutationExceededMaxSizeException` (count +1, 0 bytes allocated). The boundary search ended with a refusal at total exactly M + 1, and the blob one byte smaller was accepted. A direct `CommitLog.add` of an oversized mutation was refused at `Mutation.validateSize ← CommitLog.add` with 0 bytes allocated. 50 near-limit inserts all passed, and the 1026 KiB control accepted the blob the 1024 KiB JVM refused). **Cluster: Confirmed — caps** (B3g row 1. `4097KiB` with 8 MiB stopped start-up with rc 3 and the traced message. At M = 1024 / 2048 / 4096 (default) KiB, M + 4 KiB was refused as an oversized mutation (+1, Δ commit-log content 0 / 12,986 / 0 B) and M − 4 KiB / M − 64 KiB was accepted (Δ content ≥ blob). The m1024 logged batch was refused at `CommitLog.add` (batchlog mutation 1,229,013 B > 1,048,576, `WriteFailure`, +1). Stress wrote 2,000 rows of 900,000 B with 0 errors and no oversized count. The m2048 control accepted both the request and the batch that m1024 refused). INFO arm `tdef`: with the transport defaults, the M + 4 KiB request was refused by the transport (`CQL Message of size 1052740 bytes exceeds allowed maximum of 1048576 bytes`, count +0). No run 2.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/max_mutation_size-applySimpleConfig-max_mutation_size--autonomous/`](../harness/max_mutation_size-applySimpleConfig-max_mutation_size--autonomous/).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-25, on the advisor's machine (`environment-advisor.md`).
> The verdict is against this file's own predictions and conclusions. `ConfigProbe.java` was copied unchanged from the
> `commitlog_segment_size-applySimpleConfig` harness. `unit-run.sh`, `cluster-run.sh` and `MMSampler.java` were adapted from that harness
> (copied, then changed in the copy). No reading from that case is used here.

**What the constraint is (kept apart throughout).** `max_mutation_size` (M) caps the size of **one** mutation, counted as serialized bytes
+ 12 (`Mutation.java:169-176`). It is enforced at start-up against `commitlog_segment_size` (2M ≤ S, `DatabaseDescriptor.java:898-901`) and at
runtime at two sites: the coordinator, when a CQL statement builds its mutations, and `CommitLog.add`. It does not cap a statement, a batch or
the commit log as a whole. The unlogged batch below wrote 1.23 MB in one request, each mutation under M. In this file, "caps" means
"caps the bytes one mutation can put into the commit log".

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `0dcdfe0` (DD batch 2; sha256 `5e2c5cfb…2563`, checked equal to the filed §2 row before the audit). Frozen after the step-0 audit's seventeen amendments (2026-10-25, before any harness run or reading): sha256 **`e69f7208fc0c2ec1fff91a81e9235ebbf8ade6294f105dc8fa23d19af8ed296a`**, added as a new row in `_INDEX.md` §4 and re-checked unchanged after both tiers. Both tiers' run 1 ran at this version. No runbook fix was needed. Section D was filled after the hash. Nothing is committed (no commit was asked for); base commit `c9e9434`. |
| **Harness** | [`../harness/max_mutation_size-applySimpleConfig-max_mutation_size--autonomous/`](../harness/max_mutation_size-applySimpleConfig-max_mutation_size--autonomous/):<br>• `ConfigProbe.java` (copied unchanged)<br>• `MaxMutationProbeTest.java` (CQLTester mechanism test)<br>• `unit-run.sh`<br>• `MMSampler.java` (one-connection JMX reader: `OverSizedMutations` Count, `Commitlog` `ActiveContentSize`, `TotalCommitLogSize`, heap)<br>• `mmwrite.py` (the per-arm driver requests, bundled driver, protocol 5, prepared statement, `FallthroughRetryPolicy` so that no request is retried and counted twice)<br>• `cluster-run.sh`<br>• `selfcheck.py` (independent)<br>Instrument checks before run 1: `bash -n` and `py_compile` passed. The **unit shakedown** (one JVM at M = 512 KiB, not an arm value) first found harness defect H1 (compile error); the second attempt ran end to end ([`shakedown/unit-shakedown-summary.txt`](max_mutation_size-applySimpleConfig-max_mutation_size--autonomous/shakedown/unit-shakedown-summary.txt)). The **cluster shakedown** `sd` (m1024 settings, stress n = 200) ran end to end ([`shakedown/`](max_mutation_size-applySimpleConfig-max_mutation_size--autonomous/shakedown/)).<br>**Bound check against the shakedowns** (harness checks, not readings):<br>• unit: allocated across refusals 0 (bound < 4,096); the boundary search converged in 2 tries (bound 6); 50 inserts spanned 5 segments at M = 512 KiB (bound ≥ 2).<br>• cluster: Δ ActiveContentSize 0 across both refusals (bound < 65,536); accepted Δ 1,057,529 for a 1,044,480 B blob (bound ≥ blob − 65,536); batchlog mutation 1,229,013 B, which is < 2 MiB, so the m2048 batch control is reachable; the 64 MiB transport limit and the 4096 KiB batch thresholds let every request reach the mutation check.<br>No bound was changed.<br>Self-check: [`run1/selfcheck.out`](max_mutation_size-applySimpleConfig-max_mutation_size--autonomous/run1/selfcheck.out). |
| **Tiers and values** | **Unit (B2):**<br>• ConfigProbe (`8MiB`, `4096KiB` / `4097KiB` / unset) and (`32MiB`, `16384KiB` / `16385KiB` / unset), each in its own `java`.<br>• Mechanism JVMs at S = 5 MiB: M = `1024KiB`, `1026KiB` (control), `2048KiB`, unset (→ 2560 KiB), one `ant testsome` each.<br>**Cluster (B3):** one node, 2 GiB heap, `commitlog_segment_size: 8MiB`.<br>• `a4097` (start-up refusal); `m1024`, `m2048` (control), `mdef` (default 4096 KiB); INFO `tdef`.<br>• Held fixed: `commitlog_total_space: 1024MiB`; batch warn/fail 4096 KiB; native message 64 MiB and in-flight 128 MiB (not in `tdef`).<br>• Stress (m1024): 2,000 × 900,000 B. |
| **Audit bottom line** | **Ready after amendments**, 2026-10-25. |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Estimate, A2: bytes of one mutation as it is allocated in the commit log (serialized + 12). |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly → Met after amendment | Unit mechanism had {1024, 2560 (explicit)} KiB, cluster {1024 KiB, default}. Amendments B2b and B3b give three values each including the default (unset), plus the shipped-default segment for ConfigProbe. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | Filed: exceptions, the counter and the unit commit-log position. Added: bytes allocated in the commit log across each request (unit, B2d) and the synced commit-log content `ActiveContentSize` (cluster, B3d). Gap: the per-write `DataOutputBuffer` scratch and the hint buffer (`HintsService.java:110`) are not measured. |
| A. Core question | usage driven to the limit and past it | Met | M ± 1 KiB, the byte-exact boundary (added) and 50 near-limit writes (unit); M ± 4 KiB and 2,000 × 900 KB (cluster). |
| B. Logic | each step says what it establishes | Partly | B2e/B3e list the steps, and the readings tables carry the meaning. Left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | Exact messages, byte values and tolerances (B2f, B3f). |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | B2g/B3g had three rows. Added: Invalid (another check refused, read-back, control), Not confirmed (count, search, limit not reached), and INFO for `tdef`. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The boundary is exact at each M. The disallow branch is shown by `MutationExceededMaxSizeException`, `OverSizedMutations` +1 and no allocation. |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | Filed B2h and B3h were "M raised → accepted". They were made exact (the same blob in both JVMs), and the batch control was added. **The transport alternative was missing from the file** (below). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Added which check refuses which request (B3a). Also added: one JVM per value (`IMutation.java:31`), and the batch-size guard. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | Exact blobs, keys, order, waits and stress command (B2c–B2e, B3c–B3e). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met after amendment | The `/local/...` paths and `ant jar` were replaced by this host's clone `cassandra-run16`, `build-test` and the probe/node paths (B2a, B3a, B4). |
| D. Runnable | workload arithmetic reaches the limit | **Not met → Met after amendment** | Filed B3c: the M ± 4 KiB requests were "all under the default native message limit". **Wrong:** the default `native_transport_max_message_size` is min(M, in-flight, in-flight per IP) = **M** (`DatabaseDescriptor.java:903-905, 3237-3244`), so every M + 4 KiB request would be refused by the transport (`OversizedCQLMessageException`, `CQLMessageHandler.java:551-556, 847-851`) before `Mutation.validateSize` runs. Amendment B3a holds 64 MiB / 128 MiB in every counted arm and keeps the default only in the INFO arm `tdef`, to show the shadowing. Second gap: a logged multi-partition batch over 50 KiB is refused with `Batch too large` (`BatchStatement.java:331-358`). The batch thresholds are held at 4096 KiB. Disk: ≤ 4 GB per arm against 144 GiB free. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked in `~/cassandra-src` at `cassandra-5.0.9`: `DatabaseDescriptor.java:649-656, 891-918, 2827-2830, 3218-3245`, `Config.java:284-302, 395-407`, `IMutation.java:31`, `Mutation.java:169-176`, `MutationExceededMaxSizeException.java:25-60`, `CommitLog.java:257, 300-330, 430-436`, `CommitLogSegment.java:90-96, 236-250, 650-653`, `SingleTableUpdatesCollector.java:95-117`, `BatchUpdatesCollector.java:135-152`, `BatchStatement.java:331-371, 430-446`, `StorageProxy.java:1286-1301, 1674-1700`, `BatchlogManager.java:134-165`, `CQLMessageHandler.java:170-200, 520-560, 824-851`, `Envelope.java:195-215, 400-440`, `OversizedCQLMessageException.java:21`, `CassandraDaemon.java:745-768`, `PartitionUpdate.java:541`, `test/conf/cassandra.yaml:1-30`. **HANDOFF-ADVISOR §10's "16 MiB native frame" is the pre-v5 decoder's `native_transport_max_frame_size`** (`Envelope.java:197, 429`). At protocol 5, large messages are reassembled by `CQLMessageHandler` and checked against `native_transport_max_message_size` only, so the 16 MiB limit does not bind at v5. In any case no request here exceeds 4.01 MiB. |

**Which check refuses which request** (the audit's statement, B3a; confirmed by the readings in §4):

| Check | Where | Reached by | Exception and message | OverSizedMutations |
|---|---|---|---|---|
| Native transport, message size (v5) | `CQLMessageHandler.java:551-556, 824-826, 847-851` | any request whose body exceeds `native_transport_max_message_size`. **The default is M**, so an M + 4 KiB request is caught here first | `OversizedCQLMessageException` (an `InvalidRequestException`): `CQL Message of size <n> bytes exceeds allowed maximum of <L> bytes` | +0 |
| Coordinator, statement → mutations | `SingleTableUpdatesCollector.java:112`, `BatchUpdatesCollector.java:149` → `Mutation.validateSize` | every CQL write, per mutation | `MutationExceededMaxSizeException` (an `InvalidRequestException`): `Rejected an oversized mutation (<t>/<M>) for keyspace: <ks>. Top keys are: …`; client `InvalidRequest` (code 2200) | +1 |
| Commit log | `CommitLog.java:304` → `Mutation.validateSize` | mutations that did not pass the coordinator check: on one node, the batchlog mutation of a logged multi-partition batch; in the unit tier, a direct `CommitLog.add` | the same exception; batchlog: `ERROR … Failed to apply mutation locally` (`StorageProxy.java:1688`), client `WriteFailure` (code 1500) | +1 |
| (pre-v5 only) frame size | `Envelope.java:429-439, 484` | protocol ≤ v4 frames over 16 MiB | `Request is too big: length … exceeds maximum allowed length …` | +0 |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone `cassandra-run16`, `build-test`; ConfigProbe copied; one `ant testsome` per value; `max_mutation_size` appended to the test yaml | Amendment 2026-10-25 | The paths did not exist; `IMutation.MAX_MUTATION_SIZE` is static. |
| 2 | B2b: shipped-default segment in ConfigProbe; mechanism M ∈ {1024 KiB, 2048 KiB, unset} + control 1026 KiB | Amendment 2026-10-25 | Group A. |
| 3 | B2c: exact blobs; byte-exact boundary search; direct `CommitLog.add` (replica-side check) | Amendment 2026-10-25 | The filed workload tested only the coordinator site, to ± 1 KiB. |
| 4 | B2d: bytes allocated per request; exception chain; read-back | Amendment 2026-10-25 | Group A, real resource. |
| 5 | B2e: order | Amendment 2026-10-25 | Open. |
| 6 | B2f: exact forms (i)–(vi); "caused by" read as "is or is caused by" | Amendment 2026-10-25 | Group B. The exception is a subclass, not a wrapper (`MutationExceededMaxSizeException.java:32`). |
| 7 | B2g: verdict rows | Amendment 2026-10-25 | Group B. |
| 8 | B2h: control made exact (same blob in both JVMs) | Amendment 2026-10-25 | Group B. |
| 9 | B3a: this host; native message 64 MiB / in-flight 128 MiB; batch thresholds 4096 KiB; the check map | Amendment 2026-10-25 | The default message limit is M (group D). |
| 10 | B3b: arms `a4097`, `m1024`, `m2048`, `mdef`, INFO `tdef`; shakedown `sd` | Amendment 2026-10-25 | Group A; the transport alternative shown, not assumed. |
| 11 | B3c: exact requests (with logged/unlogged batches) and stress with `no-warmup` | Amendment 2026-10-25 | Exactness; the logged batch reaches the `CommitLog.add` site. |
| 12 | B3d: JMX reader (`OverSizedMutations`, `ActiveContentSize`) instead of `sjk`; settings read-back | Amendment 2026-10-25 | `sjk` can exit 0 on failure; real resource. |
| 13 | B3e: order and waits (12 s after each request for the 10 s periodic sync) | Amendment 2026-10-25 | `contentSize` is `lastSyncedOffset`. |
| 14 | B3f: exact (i)–(vii), tolerances | Amendment 2026-10-25 | Group B. |
| 15 | B3g: verdict rows | Amendment 2026-10-25 | Group B. |
| 16 | B3h: the request and the batch control | Amendment 2026-10-25 | Group B. |
| 17 | B4: this host's cleanup | Amendment 2026-10-25 | `/local` paths. |
| 18 | B2e/B3e steps do not say what each establishes; hint-buffer sizing (`HintsService.java:110`) untested | Left for stage 3 | Not needed for a valid run. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-25. Build 15:40; unit shakedown 15:48–15:50; cluster shakedown 15:50–15:52; unit 15:52:58–15:54:09; cluster 15:55:31–16:00:37 EDT. |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab. |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64; 10 cores, 32 GiB RAM.<br>Internal SSD (APFS, `/dev/disk3s1`): 145 GiB free at the start and 144 GiB before the cluster (re-checked by the runner; it requires ≥ 20 GiB).<br>Loopback 127.0.0.1–.3 present (re-checked; one node used, 127.0.0.1).<br>Ports 7000/7199/9042/9091 free and no Cassandra process before each run; re-checked by the runner and at the end (§8). |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64).<br>ConfigProbe: `java -Xms1G -Xmx1G` + the 17 JDK 11 module flags.<br>Test: `ant testsome` forks with `-Xmx1024m` (build.xml).<br>Node: `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`. |
| Ant | 1.10.18 |
| Local `cassandra-src` clone commit | `$W/cassandra-run16` = `~/Library/Caches/stage4/cassandra-run16`, `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), built with `ant -Dlocal.repository=$W/m2 build-test` (`BUILD SUCCESSFUL`, 54 s). Clean (`git status` empty) after the unit tier. |
| Case-file commit / harness commit | Filed `0dcdfe0` (base of this run `c9e9434`). Amendments, harness and results are uncommitted (sha256 in §1). |
| Storage for node data | Local SSD, `$W/node-mms/{data,commitlog,hints,saved_caches,cdc_raw}`, wiped before and after each arm. Unit test data under `$C/build/test/cassandra` (removed by the harness). ConfigProbe data under `$W/probe-mms/data` (removed; `$W/probe-mms` deleted at the end). Nothing here depends on free space. |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/max_mutation_size-applySimpleConfig/`:<br>• `clone-build-run16.log`<br>• `unit-shakedown.attempt1-compile-error/`, `unit-shakedown/` (not evidence), `cluster-shakedown/` (not evidence)<br>• `unit-run.out`; `unit/` (`p1-*.out`, `ant-*.log`, `TEST-*.xml`, `TEST-*.log`, `stage4.out`, `summary.txt`, `commands.log`, yaml diffs)<br>• `cluster-run1/` (`summary.txt`, `commands.log`; per arm `system.log`, `debug.log`, `node.out`, `settings.txt`, `req.txt`, `readback.txt`, `log-lines.txt`; m1024 `stress.log`, `jmx-stress.csv`)<br>• `selfcheck.out` |

## 3. Runbook defects

None. Every step of B2a–B2e and B3a–B3e ran as written at the frozen version.

Harness defects (no case-file change, no effect on a reading):

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| H1 | unit shakedown (M = 512 KiB) | B2c (4) | `MaxMutationProbeTest` did not compile: `Row.SimpleBuilder.add` returns the row builder, which has no `buildAsMutation()`. | Keep the `PartitionUpdate.SimpleBuilder` in a variable, add the row, then call `buildAsMutation()` on it. The second shakedown ran end to end (directory of the first kept as `unit-shakedown.attempt1-compile-error/`). | 2026-10-25, before run 1 | none |

## 4. Run 1

**Scope:** both tiers, every value in §1. **Command logs:** `run1/unit/commands.log`, `run1/cluster/commands.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, `stage4.out`, `p1-*.line`, `TEST-*.head.txt`; all four `ant testsome` rc 0, `Tests run: 1, Failures: 0, Errors: 0`)

| ConfigProbe (segment, max_mutation_size) | Result | Evidence |
|---|---|---|
| `8MiB`, `4096KiB` / unset | `OK getMaxMutationSize=4194304` / `4194304` | `p1-8MiB-4096KiB.line`, `p1-8MiB-unset.line` |
| `8MiB`, `4097KiB` | `REJECT ConfigurationException: commitlog_segment_size must be at least twice the size of max_mutation_size / 1024` | `p1-8MiB-4097KiB.line` |
| `32MiB`, `16384KiB` / unset | `OK getMaxMutationSize=16777216` / `16777216` | `p1-32MiB-16384KiB.line`, `p1-32MiB-unset.line` |
| `32MiB`, `16385KiB` | the same REJECT message | `p1-32MiB-16385KiB.line` |

| Reading (per JVM, S = 5,242,880) | `1024KiB` | `1026KiB` (control) | `2048KiB` | unset |
|---|---|---|---|---|
| (i) M = getter = `IMutation.MAX_MUTATION_SIZE` | 1,048,576 | 1,050,624 | 2,097,152 | 2,621,440 |
| (ii) A = M − 1,024: outcome, Δcount, row | accepted, 0, yes (1,047,552 B) | accepted, 0, yes (**1,049,600 B**) | accepted, 0, yes | accepted, 0, yes |
| (iii) B = M + 1,024: class; message total; Δcount; allocated; row | `MutationExceededMaxSizeException` (an IRE); `(1049655/1048576)`; +1; 0; absent | B = 1,051,648: `(1051703/1050624)`; +1; 0; absent | `(2098232/2097152)`; +1; 0; absent | `(2622520/2621440)`; +1; 0; absent |
| (iv) boundary: tries; last refusal total; blob x − 1 | 2; **1,048,577**; 1,048,521 accepted (+0, row), allocated **1,048,576** | 2; **1,050,625**; 1,050,569 accepted, allocated 1,050,624 | 2; **2,097,153**; 2,097,097 accepted, allocated 2,097,152 | 2; **2,621,441**; 2,621,384 accepted, allocated 2,621,476 (new segment: 36 B header + 2,621,440) |
| k = total − blob (INFO) | 55 | 55 | 56 | 56 |
| (v) direct `CommitLog.add` over: frames; Δcount; allocated | `Mutation.validateSize<CommitLog.add`; +1; 0 | same; +1; 0 | same; +1; 0 | same; +1; 0 |
| (v) direct under: Δcount; allocated (INFO) vs serialized + 12 | 0; 1,047,607 = 1,047,607 | 0; 1,049,655 = 1,049,655 | 0; 2,096,219 (new segment) vs 2,096,183 | 0; 2,620,472 = 2,620,472 |
| (vi) 50 × (M − 1,024): ok, Δcount, segments advanced, ms | 50, 0, 10, 116 | 50, 0, 13, 120 | 50, 0, 25, 177 | 50, 0, 25, 165 |

Control (B2h): the 1,049,600-byte blob was refused in the `1024KiB` JVM (its B) and accepted in the `1026KiB` JVM (its A).

**Cluster tier** (`run1/cluster/summary.txt`, `<arm>/{settings.txt, req.txt, log-lines.txt}`, `a4097/{node-out-lines.txt, system-log-lines.txt}`, `m1024/{stress-results.txt, jmx-stress.csv, failed-locally.txt}`)

| Observable | Reading |
|---|---|
| (i) `a4097` | rc **3** after 2 s, no `Startup complete`; `Exception (org.apache.cassandra.exceptions.ConfigurationException) encountered during startup: commitlog_segment_size must be at least twice the size of max_mutation_size / 1024` |
| (ii) settings m1024 / m2048 / mdef | `max_mutation_size` `1024KiB` / `2048KiB` / `4096KiB`; `commitlog_segment_size` `8MiB`; native message `64MiB`; batch fail `4096KiB` |

| Request (arm, blob B) | Outcome, exception | Message (excerpt) | Δcount | Δ ActiveContentSize | Rows |
|---|---|---|---|---|---|
| m1024 key 1, 1,052,672 | **refused**, `InvalidRequest` | `Rejected an oversized mutation (1052727/1048576)` | +1 | 0 | absent |
| m1024 key 2, 1,044,480 | accepted | — | 0 | 1,057,529 | present |
| m1024 logged batch, 2 × 614,400 | **refused**, `WriteFailure` (code 1500) | system.log: `Failed to apply mutation locally` … `Rejected an oversized mutation (1229013/1048576) for keyspace: system. Top keys are: batches.…` at `Mutation.validateSize` ← `CommitLog.add(CommitLog.java:304)` | +1 | 0 | absent / absent |
| m1024 unlogged batch, 2 × 614,400 | accepted | — | 0 | 1,228,918 (INFO: > M in one request, each mutation < M) | present / present |
| m2048 key 1, 1,052,672 (control) | **accepted** | — | 0 | 1,052,735 | present |
| m2048 key 3, 2,101,248 | **refused**, `InvalidRequest` | `(2101304/2097152)` | +1 | 12,986 | absent |
| m2048 key 4, 2,093,056 | accepted | — | 0 | 2,093,119 | present |
| m2048 logged batch (control) | **accepted** | — | 0 | 2,457,996 | present / present |
| mdef key 5, 4,198,400 | **refused**, `InvalidRequest` | `(4198456/4194304)` | +1 | 0 | absent |
| mdef key 6, 4,128,768 | accepted | — | 0 | 4,141,818 | present |
| mdef key 1, 1,052,672 (INFO) | accepted | — | 0 | 1,052,735 | present |
| tdef key 1, 1,052,672 (INFO) | refused by the **transport**, `InvalidRequest` | `CQL Message of size 1052740 bytes exceeds allowed maximum of 1048576 bytes` | **0** | 0 | absent |
| tdef key 2, 1,044,480 (INFO) | accepted | — | 0 | 1,057,529 | present |

(vi) m1024 stress: `Total partitions : 2,000`, `Total errors : 0`, 3 s at 656 op/s; OverSizedMutations 2 in all 9 samples spanning the stress. INFO: the commit log reached 469,762,048 B and fell to 25,165,824 B after a flush. tdef settings (INFO): native message `1048576B`, in-flight `214748364B`, per IP `53687091B`. That is the source's min(M, heap/10, heap/40).

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity.** The run was valid:
   - The knob was applied in every JVM: read-back (i) matches the yaml diffs [observed: `stage4.out` `run` lines, `p2-yaml-diff-*.txt`].
   - The four tests ran, with rc 0 and 1 test each [observed: `TEST-*.head.txt`].
2. **Readings.** Nothing contradicts. k is 55 below 2 MiB and 56 above, from one more vint byte. The boundary search was built for this, and it converged in 2 tries in every JVM [observed]. In the unset JVM, the accepted edge entry started a new segment. Its allocated 2,621,476 is the 36 B header plus exactly M [observed; header size inferred from the 2048KiB direct-under line, 2,096,219 − 2,096,183 = 36].
3. **Matched row.** B2g row 1, "ConfigProbe as in B2f, (i)–(vi) in all four JVMs, control holds":
   - ConfigProbe: 6/6 as predicted.
   - (iii): refused with `MutationExceededMaxSizeException`, +1, 0 bytes.
   - (iv): refusal at exactly M + 1 and acceptance at M. The accepted entry allocated exactly M bytes in three JVMs, and M + header in the fourth.
   - (v): the direct `CommitLog.add` was refused at `Mutation.validateSize ← CommitLog.add`, with 0 bytes.
   - (vi): 50/50, with 10–25 segments.
   - Control: the same 1,049,600 B blob was refused at M = 1,048,576 and accepted at 1,050,624 [all observed: `stage4.out`, `selfcheck.out`].
4. **Excluded rows.**
   - Refuted (a): 4097 and 16385 KiB were refused; 4096, 16384 KiB and unset were accepted.
   - Refuted (b): no request with total > M was accepted, and 0 bytes were allocated across every refusal.
   - Invalid: read-back held, every refusal was the mutation-size exception, and the control was accepted.
   - Not confirmed: every count was +1, every search converged, and (vi) held.
5. **Observed vs. inferred.** That a refused mutation never reached the segment is observed as 0 bytes allocated. That this holds for every mutation, not only these, is inferred from the single code path (`Mutation.java:171-172`).
6. **Deviations and gaps.** None in the procedure. `allocated` for the direct-under add is INFO.
7. **Core question.**
   - At four values of M, the largest mutation the commit log accepted was exactly M bytes (allocation = M), and M + 1 was refused with nothing allocated.
   - An explicit M is accepted only when 2M ≤ S.
   - **Effect: caps** (per mutation).

**Conclusion (one line):** B2g row 1 → **Confirmed**. Effect: caps (per mutation: largest commit-log entry = M exactly; M + 1 refused at both sites).

**Cluster tier**

1. **Validity.** The run was valid:
   - Read-back (ii) held in all three counted arms [observed: `settings.txt`].
   - The held-fixed lines are in each arm's YAML summary line [observed: `summary.txt`].
   - No request in a counted arm met the transport or batch-size guard [observed: `selfcheck.out`].
2. **Readings.**
   - m2048 key 3's Δ content of 12,986 B is background system writes within the frozen 64 KiB tolerance. An appended entry would have added > 2 MiB.
   - Stress finished in 3 s. The m1024 `jmx-stress.csv` shows the commit log at 469 MB mid-stress [observed]. The 2,000 × 900,000 B writes passed.
3. **Matched row.** B3g row 1, "(i)–(vii) and the B3h control hold":
   - (i): rc 3 with the message.
   - (iii): three refusals as oversized mutations, each +1 with |Δ content| < 64 KiB.
   - (iv)/(vii): accepted with Δ content ≥ blob.
   - (v): logged batch refused at `CommitLog.add` (`WriteFailure`, +1, batchlog 1,229,013/1,048,576, no rows); unlogged accepted.
   - (vi): 2,000/0, count flat.
   - B3h: m2048 accepted the 1 MiB + 4 KiB request and the batch.
   - [All observed: `req.txt`, `failed-locally.txt`, `stress-results.txt`, `selfcheck.out`.]
4. **Excluded rows.**
   - Refuted (a): `a4097` did not start.
   - Refuted (b): no expected-refused request was accepted.
   - Invalid: no transport or batch-size refusal in the counted arms, read-back held, and the control was accepted.
   - Not confirmed: every count was +1, every content relation held, and (vi) held.
5. **Observed vs. inferred.**
   - The coordinator-vs-commit-log attribution rests on the stack frames: the batchlog refusal shows `CommitLog.add` in `failed-locally.txt` [observed]. The single-statement refusals come from the coordinator site: InvalidRequest returned to the client, and no `Failed to apply` log line [inferred from the client error code and `SingleTableUpdatesCollector.java:112`].
   - `ActiveContentSize` is the synced content, which is why the reader waits 12 s.
6. **Deviations and gaps.**
   - The driver used `FallthroughRetryPolicy` (harness choice: no request is retried; the frozen text does not mention retries).
   - The hint buffer was not exercised.
7. **Core question.**
   - Every mutation over M was refused at the site that saw it, and the commit-log content did not grow. Mutations at M − 4 KiB grew it by their size.
   - The boundary moved with M: 1 MiB + 4 KiB was refused at 1024 KiB and accepted at 2048 and 4096 KiB.
   - The start-up invariant held.
   - INFO `tdef` shows that with the shipped transport defaults, an M + 4 KiB request never reaches this check: the transport refuses it, with count +0.

**Conclusion (one line):** B3g row 1 → **Confirmed**. Effect: caps (per mutation; shadowed by the default native message limit = M at the transport).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`selfcheck.py` is a separate script. It re-reads the raw files, not `summary.txt`:
- unit: `p1-*.out`, `stage4.out`, `TEST-*.xml`;
- cluster: `node.out`, `system.log`, `settings.txt`, `req.txt`, `stress.log`, `jmx-stress.csv`.

The one exception is `a4097`'s rc, which only the runner's `summary.txt` records. The script re-evaluates every frozen relation of B2f/B2h and B3f/B3h. Result: **59 relations, 59 hold, 0 fail**, plus 4 INFO lines (`mdef` 1 MiB + 4 KiB, the two `tdef` requests, the `tdef` settings) ([`run1/selfcheck.out`](max_mutation_size-applySimpleConfig-max_mutation_size--autonomous/run1/selfcheck.out)).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Read-back re-parsed from `stage4.out` and `settings.txt`; TEST xml `tests="1" failures="0" errors="0"` in all four JVMs. |
| 2. Readings | yes | k = 55/56 and the new-segment edge re-derived from `stage4.out`. The m2048 Δ content of 12,986 is under 65,536. |
| 3. Matched row | yes | Every row-1 relation holds in the raw files at both tiers. |
| 4. Excluded rows | yes | No accepted request has a total > M. No counted request carries `CQL Message of size` or `Batch too large`. Every count is +1. |
| 5. Observed vs. inferred | yes | `system.log` re-read: the batchlog ERROR shows `at org.apache.cassandra.db.commitlog.CommitLog.add`, and the unit direct-add frames show `Mutation.validateSize<CommitLog.add`. |
| 6. Deviations and gaps | yes | The retry policy is visible in `mmwrite.py`; no request was retried (one count per refusal). |
| 7. Core question | yes | Exact boundary at four values of M (unit), refusal and content at three (cluster), and controls at both tiers. |

### 5.2 Run 2?

**No**, decided 2026-10-25. Both tiers rest on direct observations (byte-exact boundaries, counts, allocation and content deltas), and the independent script re-derived them. No conclusion rests on an inferred statement that a repeat would settle.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested (B1):** (a) With `commitlog_segment_size: S`, an explicit `max_mutation_size` M is accepted iff 2M ≤ S (KiB arithmetic). (b) A
mutation whose serialized size + 12 B exceeds M is refused and is never appended to the commit log, so no commit-log allocation exceeds M.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed**: B2g row 1. ConfigProbe 6/6 (2M = S accepted, 2M = S + 2 KiB refused, unset = S/2 at 8 and 32 MiB). At M = 1,048,576 / 1,050,624 / 2,097,152 / 2,621,440 B: total M + 1 refused (`MutationExceededMaxSizeException`, +1, 0 B allocated) and total M accepted (an entry of exactly M bytes); direct `CommitLog.add` over M refused at `CommitLog.java:304` with 0 B allocated; 50 near-limit writes passed; control held | caps (per mutation: the largest commit-log entry is exactly M) | run 1 + self-check | 2026-10-25 |
| Cluster | **Confirmed**: B3g row 1. `4097KiB` with 8 MiB: rc 3 with the traced message. M + 4 KiB refused as oversized at 1024/2048/4096 (default) KiB, +1, no commit-log content; M − 4/64 KiB accepted; logged batch refused at `CommitLog.add` (batchlog 1,229,013 > 1,048,576, `WriteFailure`, +1); stress 2,000 × 900 KB, 0 errors; m2048 control accepted the request and the batch | caps (per mutation). With the shipped native-transport defaults, the message limit equals M, so a request just over M is refused by the transport first (`tdef`, count +0) | run 1 + self-check | 2026-10-25 |

**What each outcome means here.**
- "Caps" means one mutation's commit-log entry is at most M bytes, and anything larger is refused before allocation, at whichever site sees it first.
- It does not bound a statement or a batch: the unlogged batch put 1.23 MB in one request.
- It does not bound the commit log as a whole (`commitlog_total_space`).

**Feedback filed:**
- The case file's section D was filled (uncommitted). No section was amended after the freeze.
- Index rows: `_INDEX.md` §1 (Stage 4), §2 (frozen hash row), §3 (coverage line).
- For stage 3: the filed B3c's "under the default native message limit" was wrong for every request just above M. Future designs that drive a mutation just over M through CQL must raise `native_transport_max_message_size`. HANDOFF-ADVISOR §10's 16 MiB note applies to protocol ≤ v4 only.

**Processes:** after the cluster tier, `final CassandraDaemon processes: none`, no `cassandra-stress` left, `node-mms` wiped
(`run1/cluster/summary.txt`). Re-checked at the end of the session: `ps -eo command | grep '[C]assandraDaemon'` was empty; ports 7000/7199/9042/9091 were free; `$W/probe-mms` was removed; the run clone was clean; the repository root had no `build/` or log folder.
