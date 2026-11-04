# sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous — stage-4 results  <!-- file: results/sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous.md -->

> **Case:** [`sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous`](../../stage3-ai-deep-read/cases/sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous.md)
>
> **Status:** verdict filed, 2026-10-28. **Unit: Confirmed — caps only on some paths (bypass)** (run 1; closed, not re-run). **Cluster: Confirmed — caps only on some paths (bypass)**
> (cluster re-run "run 1b" of 2026-10-28 at the re-frozen version `83890d4b…33f8`, after the user-authorised amendment of B3a, B3f (drift control), B3h and B4; §7, §8). The run-1 cluster verdict below (Not confirmed) stays on record as filed.
>
> **Outcome class:** undetermined — the stage-3 estimate (`undetermined`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/`](../harness/sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/).
>
> **Run-1 status (as filed 2026-10-26):** verdict filed, 2026-10-26. **Unit: Confirmed — caps only on some paths (bypass): running tasks and worker threads capped, queued-task memory not capped. Cluster: Not confirmed (frozen idle drift control missed by one thread) — as observed, running tasks and worker threads with their stack reservation capped; queue holds all excess.**
>
> **Agent:** autonomous. In this file, "§9a" means each tier's predictions and conclusions table: B2f and B2g for the unit tier, B3f and B3g for the cluster tier. "§9b–§9e" means B2a–B2e or B3a–B3e. The case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-26, on the advisor's machine (`environment-advisor.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | **Filed:** sha256 `9f100262…adb3`. **After the step-0 audit's nineteen amendments (2026-10-26), frozen:** `d5d2f12267ce12950ca82d70ef4673a75e83d80b786df1ca6f6f70848df43a25` (new row in `_INDEX.md` §4). **Unit attempt 0 hit runbook defect 1;** its dated fix to B2d gave `f8eb812b1ac007b14a69c4b3c93d567ed4973ea48e291054fe80ee4fde985605`, at which the unit tier's run 1 ran. **The cluster shakedowns hit defects 2 and 3** (fixes to B3d: `1ccbf2d4…`, `e9ce4c6c…`). **Cluster run 1 attempt 0 hit defect 4** (fix to B3c), giving `b60d547517e40c7b9cb4c486f0f549529324facac44aadfe6e50db00a8377770`, at which the cluster tier's run 1 ran. No prediction, band or row changed after the first freeze. All five hashes are rows in `_INDEX.md` §4. Nothing is committed (no commit was asked for). |
| **Harness** | [`../harness/sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/`](../harness/sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/) (not committed). Unit: `SEPMaxPoolSizeFootprintTest.java` (the filed B2c sketch with the B2b/B2c amendments) and `unit-run.sh`. Cluster: `cluster-run.sh` (conf, start/stop, sampler, phases, drain, JMX shrink and read-back), `loadclient.py` (closed-loop count(\*) client, 4 × 100 or 1 × 8, reconnect on connection errors), `Jmx.java` (copied from the `coordinator_read_size_fail_threshold` autonomous harness), `summarize.py` (the harness's own summary). Audit probe: `NmtProbe.java`. Instrument checks: (i) the test compiled in the run clone at the audit (`audit-compile.log`); (ii) the NMT probe ([`audit/nmt-probe.txt`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/audit/nmt-probe.txt)); (iii) four cluster shakedowns plus one timing probe ([`shakedown/`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/shakedown/), `NOTE.txt`). These found defects 2 and 3 and a harness bug; shakedown 3 ran every step with 5.0 s samples, every read-back, the shrink, the drain and 400 in flight with 0 errors, and checked the frozen bounds against measured quantities (W, R_ntr, Pending, NMT slope). Shakedown 4 validated the defect-4 client fix. `Sampler.java` (replacing `TpPoll.java`) is the B3d sampler. Shakedown readings are not used. |
| **Tiers and values** | **Unit (B2):** a fresh `SharedExecutorPool` per arm; N ∈ {1, 4, 16, 32, 64, 128} with M = 256 blocking tasks, each arm without and with a 256 KiB payload per task; shrink 64 → 1 with a 35 s wait; control D (N = 64, M = 8); three runs. **Cluster (B3):** one node, 2 GiB heap, NMT summary, 200 k rows of `keyspace1.standard1`; `native_transport_max_threads` ∈ {16, 64, 128, 256}, a fresh start each, with idle 30 s, C = 8 for 180 s, C = 400 for 180 s; at 256 a JMX shrink to 16 with 60 s idle and 60 s of new C = 400 load; control X at 256 with `-Xss1m`. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26. |

### 1.1 Design audit

Citations were re-read in `~/cassandra-src` at `cassandra-5.0.9` (`b5f2a54210`), the commit of the run clone. What the audit derived from the source is in the A3 amendment (i)–(viii). In short:
- (i) One count(\*) holds one NTR permit for its whole run.
- (ii) The default 12 s `native_transport_timeout` would shed the filed load.
- (iii) The SharedPool thread count never falls within a JVM, so a low-demand control must run first.
- (iv) Workers are reused before new ones are made.
- (v) NTR `Active` is the permit counter itself.
- (vi) A shrink takes effect only as tasks finish.
- (vii) NMT on macOS reports stack committed = reserved; per thread, it adds Xss + 12 KiB (probe: [`audit/nmt-probe.txt`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/audit/nmt-probe.txt)).
- (viii) `tpstats` has no MaxPoolSize column.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2: a count of running tasks and of worker threads. Each thread has a derivable byte size (stack reservation Xss + 12 KiB, RSS ≈ 115 KiB parked, probe); queued tasks hold heap bytes. The B1 amendment keeps the three quantities apart. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly → Met after amendment | Unit had no default among {1, 4, 16, 64}, and cluster lacked 128. Added 32 and 128 to the unit values and 128 to the cluster values (B2b, B3b). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | Unit: heap after GC (running and queued payloads). Cluster: NMT stack reservation, thread dumps and RSS. NTR `Active` is the permit counter itself, so an independent running count R_ntr from thread dumps was added (B3d). NMT committed cannot show touched stack on macOS; this gap is named, and significance is read on RSS (B3f/B3g). |
| A. Core question | usage driven to the limit and past it | Partly → Met after amendment | M = 256 > N and C = 400 > 256. The filed timeouts would have shed the load (A3 (ii)), so `native_transport_timeout` was raised to 300 s, and the 2 M rows were reduced to 200 k so that queries finish inside it (B3a, B3c). |
| B. Logic | each step says what it establishes | Met | B2h/B3h, plus the amendments. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | "About Σ maximumPoolSize + 2" and "≈" were replaced by exact bands (B1, B2f, B3f). |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | Rows added and split by finding F1/F2/F3 (B2g, B3g), with the tier-verdict and Effect mappings in B1. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after amendment | Disallow evidence: tasks left queued (`pending` = M − N; NTR Pending ≈ 400 − knob) while the running count equals the cap. The cluster running count is independent of the permit counter (R_ntr). |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | The filed C = 8 control ran **after** C = 400 in the same JVM, where it reads the earlier high-water mark (A3 (iii)). It now runs first. Added unit control D (demand below cap). The filed `-Xss1m` control compared totals; it now compares per-thread slopes. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | The post-shrink check needed new load after a drain (A3 (vi)); the populate needed its own start. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | `tpstats` MaxPoolSize does not exist; `nodetool sjk mx --help` prints an NPE, so JMX is used for the shrink and the read-back (B3b). Drain stop condition added (B3e). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Mapped to this host (B2a, B3a). |
| D. Runnable | workload arithmetic reaches the limit | Met after amendment | At 2 M rows and 400 outstanding, the per-request latency approaches 300 s on 10 cores (B3c amendment). At 200 k it does not, and the cap binds whenever demand exceeds it, whatever a scan costs (A3 (i)). The shakedown checks this. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `SEPExecutor.java:50-80, :103-145, :156-240, :336-396`; `SEPWorker.java:54-62, :82-207, :212-266, :289-340`; `SharedExecutorPool.java:65-183`; `Dispatcher.java:57-127, :238-270, :355-368`; `RangeCommandIterator.java:186-210`; `Stage.java:45-50, :205-235`; `Config.java:179-182, :283, :287, :1391-1399`; `conf/cassandra.yaml:1033-1034`; `TpStatsPrinter.java:55`; `build.xml:225-240`. All filed citations matched. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | A3 (i)–(viii): request path, timeouts, monotone thread count, reuse, `Active` = counter, shrink timing, NMT on macOS, `tpstats` columns | Amendment 2026-10-26 | Runbook depends on them |
| 2 | B1: three findings F1/F2/F3, refuted-if, verdict and Effect mappings | Amendment 2026-10-26 | Caller; group B |
| 3 | B2a, B3a, B4: this host; `native_transport_timeout: 300s`, timeouts 300 s | Amendment 2026-10-26 | CloudLab paths; A3 (ii) |
| 4 | B2b, B3b: defaults among the values (unit 32, 128; cluster 128); unit control D | Amendment 2026-10-26 | Group A |
| 5 | B2c: M parameter, settle rule, exact high-water, 35 s shrink wait | Amendment 2026-10-26 | Filed 2 s cannot test the 30 s comment |
| 6 | B2d/B2e: output location; r1–r3 | Amendment 2026-10-26 | This build |
| 7 | B2f/B3f: exact bands | Amendment 2026-10-26 | Group B |
| 8 | B2g/B3g: rows by finding | Amendment 2026-10-26 | Group B; caller |
| 9 | B3b: JMX shrink and read-back | Amendment 2026-10-26 | `tpstats` has no column; sjk usage unclear |
| 10 | B3c: populate in its own start, 200 k rows, compacted; client 4 × 100 with reconnect | Amendment 2026-10-26 | High-water contamination; timeouts; ENOBUFS lesson |
| 11 | B3d: R_ntr from thread dumps; raw files kept | Amendment 2026-10-26 | Independent running count |
| 12 | B3e: C8 before C400; drain; post-shrink load; shakedown | Amendment 2026-10-26 | A3 (iii), (vi) |
| 13 | B3h/B2h: controls as run | Amendment 2026-10-26 | Group B |
| 14 | The yaml comment "idle threads are stopped after 30 seconds" (`conf/cassandra.yaml:1033-1034`) contradicts `SEPWorker.java:116-118` | Recorded (stage-3 finding), not tuned for | Caller |
| 15 | A Linux run of the cluster tier, where NMT committed shows touched stack pages | Left for stage 3 | Not possible on this host |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26. Audit 10:12–10:27; unit attempt 0 10:27–10:31; unit run 1 (r1–r3) 10:31–10:36; shakedowns 10:36–11:09; cluster attempt 0 11:10–11:28 (stopped at knob 128, defect 4); shakedown 4 11:30–11:35; **cluster run 1 11:35:10–12:17:13 EDT** under `caffeinate -ims`, with no sleep or wake event (`pmset`: last wake 09:44:14). |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64; 10 cores, 32 GiB RAM; internal SSD (APFS), 134 GiB free; loopback 127.0.0.1, .2, .3 on `lo0` (only .1 used); ports 7000, 7199, 9042, 9091 free; no Cassandra process before; `ulimit -n` 1,048,576, `ulimit -u` 5,333, `kern.ipc.somaxconn` 128, `kern.num_taskthreads` 8,192 ([`run1/stepE.txt`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1/stepE.txt)) |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit: the junit fork of `ant testsome` (CMS). Node: `MAX_HEAP_SIZE=2G` (G1, `-XX:+AlwaysPreTouch`), `-XX:NativeMemoryTracking=summary -Dcassandra.set_sep_thread_name=false` |
| Ant | 1.10.18 |
| Python | 3.8.11; bundled driver `cassandra-driver-internal-only-3.29.0.zip`, protocol 5 |
| Local `cassandra-src` clone commit | `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), `$W/cassandra-run29`, `ant -Dlocal.repository=$W/m2 build-test` `BUILD SUCCESSFUL` (1 min 0 s); `W=~/Library/Caches/stage4` |
| Case-file commit / harness commit | uncommitted (sha256 values in §1) |
| Storage for node data | local SSD, `$W/node-sep` (wiped at the end); JMX 7199 |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/sep_maximum_pool_size-takeWorkPermit/`: `stepE.txt`, `clone-build-run29.log`, `audit-compile.log`, `audit-nmt-probe/`, `hashes-before-*.txt`; `unit-attempt0-r{1,2,3}/`, `unit-r{1,2,3}/` (ant log, JUnit XML, test log, `sepfp-lines.txt`); `cluster-shake/`, `cluster-timing/`, `cluster-shake2/`, `cluster-shake3/`, `cluster-shake4/`, `cluster-run1-attempt0/`; `cluster-run1/` (`summary.txt`, `phases.txt`, `commands.log`, and per start `populate`, `k16`, `k64`, `k128`, `k256`, `X`: node logs, `samples/` with the raw `td-`, `nmt-` and `tp-<t>.txt`, `samples.csv`, `tpjmx.log`, `sample-timing.txt`, `readback-*.txt`, `vmflags.txt`, and the client folders `C8`, `C400`, `postshrink-C400` with `w*.lines`, `w*.json`, `phase.json`); `run1-start-epoch.txt`, `run1-end-epoch.txt`, `run1-pmset-tail.txt` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| 1 | Unit attempt 0 (r1–r3, JUnit passing) | B2c/B2d | The test JVM logs each write to `System.out` as its own line with an `INFO  [main] <ts> ` prefix. The sketch's `printf` therefore split every reading over about twenty lines, and the `^SEPFP` filter found none ([`run1/unit/attempt0/r1-split-lines-excerpt.txt`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1/unit/attempt0/r1-split-lines-excerpt.txt)). The values were not read. | One `println(String.format(…))` per reading, read from `SEPFP` to the end of the line. The self-check's line filter was changed the same way before any reading. | Applied 2026-10-26; §9a unchanged; the unit tier restarted from r1 | `f8eb812b…` |
| 2 | Cluster shakedown 1 and timing probe | B3d | Under the C = 400 load, one `nodetool tpstats` takes 12–27 s here, so the 5 s shell sampler ran every 11–38 s ([`shakedown/timing-k16-sample-timing.txt`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/shakedown/timing-k16-sample-timing.txt)). | The same ThreadPools gauges are read once a second through one persistent JMX connection (`tpjmx.log`); the two `jcmd` outputs are taken in parallel. | Applied 2026-10-26, before cluster run 1; §9a unchanged | `1ccbf2d4…` |
| 3 | Cluster shakedown 2 | B3d | Loaded samples still came every 8–36 s: under the saturated CPU each process spawn costs 0.2–2 s, and the shell sampler spawns about 25 per sample ([`shakedown/shake2-k16-sample-timing.txt`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/shakedown/shake2-k16-sample-timing.txt)). | `Sampler.java` runs the same diagnostic commands (`Thread.print`, `VM.native_memory summary`) through the `DiagnosticCommand` MBean every 5 s, and the gauges every 1 s; it spawns only `ps`. Shakedown 3: every sample 5.0 s apart. | Applied 2026-10-26, before cluster run 1; §9a unchanged | `e9ce4c6c…` |
| 4 | Cluster run 1 attempt 0 (stopped at knob 128) | B3c | At knob 16 under C = 400, the driver's 30 s heartbeat (an `OPTIONS` request in the same NTR queue) timed out behind about 384 queued queries. One client process lost its connection and 100 queries (5.9%), and its `Cluster.shutdown()` blocked the rebuild for about 100 s ([`run1/cluster/attempt0/`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1/cluster/attempt0/)). | `idle_heartbeat_interval=0`; old session shut down in a thread for at most 5 s; `inflight` lines from a reporter thread; a stricter coverage check in the self-check. Validated at knob 16 with a 90 s load: 0 errors, 0 reconnects ([`shakedown/shake4-summary.txt`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/shakedown/shake4-summary.txt)). | Applied 2026-10-26; §9a unchanged; the cluster tier restarted from its beginning | `b60d5475…` |

One harness bug that is not a step of the case file: in shakedown 1, the JMX read-back asked for an attribute `ActiveCount` that the SEPExecutor MBean does not have. It was fixed before run 1 ([`shakedown/NOTE.txt`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/shakedown/NOTE.txt)).

The cluster re-run session added these on 2026-10-28: the re-freeze after run 1 (R1, a case-file amendment authorised by the user) and the harness changes for the cluster re-run (H1–H4).

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| R1 | Cluster run 1 (a reading, not a runbook defect) | B3a, B3f (drift control), B3h, B4 | The cluster tier was Not confirmed only through the frozen idle drift control "in each idle phase, W is constant". It failed by one thread (W 0 → 1) in k16, k64 and X, from an internal task about 10 s after start-up (§4.2). | **Re-freeze, authorised by the user (Yang, the advisor) on 2026-10-28:** four dated amendments `Amendment 2026-10-28 (after run 1, authorised by the user)`. **B3f:** the drift control restated from the source. The default-role setup task (`CassandraRoleManager.java:485-504`, 10,000 ms after `doAuthSetup`) makes one CL ONE read (`:480`). `Stage.READ.maybeExecuteImmediately` queues it because `takeWorkPermit` needs `taskPermits != 0` (`SEPExecutor.java:196`, `:221-223`), and `addTask` starts one spinning worker (`:135-142`, `SharedExecutorPool.java:108-116`): exactly one if none exists, none otherwise. New control: (d1) W never decreases and rises at most once, 0 → 1; (d2) no W ≥ 1 in a dump that ended before T_ar + 10 s; (d3) S ≤ 4 MiB, unchanged. **B3h:** the idle control = (d1)–(d3). **B3a, B4:** fresh clone `$W/cassandra-run72` and node `$W/node-sep72`. The whole cluster tier was re-run from its beginning in the fresh clone (§7). B1, every F1/F2/F3 relation, B3g and the unit tier are unchanged. | user, 2026-10-28 | sha256 `83890d4b…33f8` (uncommitted; no commit was asked for) |
| H1 | Cluster re-run | B3a/B4 paths | `cluster-run.sh` was fixed to run 1's clone (`cassandra-run29`) and node (`$W/node-sep`). | It now reads `SEP_C` and `SEP_NODE`; the defaults reproduce run 1. sha256 prefix `c5b09938` → `7ac0da6c` (the same file also carries H2). | AI, 2026-10-28 | n/a (harness) |
| H2 | Before the amendment (diagnostic) | identification of the idle worker | The task that creates the idle worker had to be found. | New observe-only Byteman rules `sep-worker-origin.btm` (`TestScript: no errors`) and a plan `probe` in `cluster-run.sh`: populate, then one knob-16 start with the rules and 90 s of idle. Output: [`run1b-cluster/instrument/`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1b-cluster/instrument/). The shakedown and the re-run use the `shake` and `run1` plans, which load no agent. | AI, 2026-10-28 | n/a (harness) |
| H3 | Cluster re-run | self-check | `run1/selfcheck.py` checks run 1's relations (and the closed unit tier). | `run1b-cluster/selfcheck.py` copies the cluster part of `run1/selfcheck.py`. Under `--relations run1`, its output on run 1's raw files is identical to the 84 cluster lines of `run1/selfcheck.out`. Under `--relations amended` (the default), the idle check "W const" is replaced by (d1)–(d3) and a check that the JVM arguments do not set `superuser_setup_delay_ms`; T_ar is read from `system.log` and the dump durations from `sample-timing.txt`. `--plan shake` handles the two-start shakedown. It exits non-zero on any failed check. `run1/selfcheck.py` is unchanged. | AI, 2026-10-28 | n/a (harness) |
| H4 | Cluster re-run | excerpts | — | New `excerpt.sh` (reads only): copies run 1's kinds of excerpt files plus `system-log-marks.txt` (the `StorageService.java:1466`, `CassandraDaemon.java:450` and `:744` lines, and the `CassandraRoleManager`, `Resized` and `ERROR` lines). | AI, 2026-10-28 | n/a (harness) |

## 4. Run 1

**Scope:** both tiers, all values in §1. **Command logs:**
- Unit: [`run1/unit/`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1/unit/). For each of `r1`–`r3`: `commands.log`, `sepfp-lines.txt` (the `SEPFP` text copied from the raw test log) and `junit-testsuite.txt`; plus `attempt0/`.
- Cluster: [`run1/cluster/`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1/cluster/). `summary.txt`, `phases.txt` and `commands.log`. For each start: `samples.csv`, `tpjmx.log`, `sample-timing.txt`, `readback-*.txt`, `vmflags-excerpt.txt` and the client `*-phase.json`. Also `NOTE-idle-W.txt`, and `attempt0/` (defect 4).

### 4.1 Readings

**Unit tier.** Each of r1, r2 and r3 ran 1 JUnit test with 0 failures and 0 errors. The test JVM used CMS with a 1,007 MiB heap. Every exact reading is identical in the three runs; heap deltas differ by ≤ 1 MiB.

| N | M | maxRunning = final | active | pending | threads (r1/r2/r3) | heapDelta no Q (MiB, r1/r2/r3) | ΔQ = Q − no Q (MiB, r1) | Predicted |
|---|---|---|---|---|---|---|---|---|
| 1 | 256 | 1 | 1 | 255 | 1 / 1 / 2 | −0.05 / 0.97 / 0.30 | 65.07 | 1; 255; [1,3]; [−3,5]; [60,68] |
| 4 | 256 | 4 | 4 | 252 | 4 / 4 / 4 | 4.24 / 4.02 / 4.02 | 64.56 | [0,8] |
| 16 | 256 | 16 | 16 | 240 | 16 / 16 / 16 | 16.09 / 16.09 / 15.94 | 64.57 | [12,20] |
| 32 | 256 | 32 | 32 | 224 | 32 / 32 / 32 | 32.04 / 32.04 / 32.04 | 64.53 | [28,36] |
| 64 | 256 | 64 | 64 | 192 | 64 / 64 / 64 | 63.96 / 63.96 / 63.96 | 64.52 | [60,68] |
| 128 | 256 | 128 | 128 | 128 | 128 / 128 / 128 | 128.02 / 128.02 / 128.03 | 64.32 | [124,132] |
| 64 (control D) | 8 | 8 | 8 | 0 | 8 / 8 / 8 | 8.01 (M = 8) | — | 8; [8,10] |

Shrink 64 → 1: read-back `max=1`, and **threads = 64 after 35 s** in all three runs (`activeAfter=0`). ΔQ across all runs and N lies in 64.32–65.36 MiB.

Evidence: `run1/unit/r*/sepfp-lines.txt` and `junit-testsuite.txt`.

**Cluster tier.** One node, 200,000 rows (one SSTable, 49 MB live). Each knob value had a fresh start, with the read-back equal to the knob (attribute and gauge). `ThreadStackSize` was 256 (1,024 in X), and there were 0 `ERROR` lines. Every C8 and C400 phase had 0 client errors and 0 reconnects, the in-flight medians were 8 or 4 × 100, and coverage was 100%. Every sample was 5.0 s apart. Steady window: 30 samples.

| knob | C8 W_max | C400 W_max (band) | steady median Active / R_ntr | max Active (1 s polls) / max R_ntr | steady median Pending (band) | median ReadStage Active | peak NMT thread # / stack reserved (KiB) | peak RSS (KiB) |
|---|---|---|---|---|---|---|---|---|
| 16 | 17 | **34** ([16, 160]) | 16 / 16 | 16 / 16 | 384 ([344, 392]) | 12 | 116 / 79,472 | 2,476,432 |
| 64 | 17 | **96** ([64, 208]) | 64 / 64 | 64 / 64 | 336 ([296, 344]) | 32 | 180 / 98,416 | 2,424,064 |
| 128 | 17 | **160** ([128, 272]) | 128 / 128 | 128 / 128 | 272 ([232, 280]) | 32 | 241 / 112,972 | 2,452,064 |
| 256 | 17 | **288** ([256, 400]) | 256 / 256 | 256 / 256 | 144 ([104, 152]) | 32 | 371 / 147,812 | 2,497,760 |
| X (256, `-Xss1m`) | — | 288 | 256 / 256 | 256 / 256 | 144 | 32 | 367 / 407,860 | 2,534,640 |

- **C8 control** (every knob): Active and R_ntr ≤ 8 in every sample, and W_max = 17 ≤ max(W_idle, 56).
- **Runtime shrink at 256.** JMX set 16, read back as 16 (attribute and gauge); `system.log` shows "Resized Native-Transport-Requests maximum pool size from 256 to 16". W was 288 in all 12 postshrink-idle samples (60 s) and in every later sample. Under new C = 400 load: every 1 s poll had Active ≤ 16 with `ntrMax` = 16 (121 polls); every sample had R_ntr ≤ 16; the steady medians were Active 16 and Pending 384.
- **Cross-knob.**
  - W_max 34 < 96 < 160 < 288; ΔW(16→256) = 254.
  - ΔS = 68,340 KiB = 66.7 MiB over ΔT = 255 threads, i.e. **268.0 KiB per thread**. Committed = reserved.
  - Control X: idle→peak slope 1,036.0 KiB per thread (ΔT = 290) against 268.0 at 256 (ΔT = 294), **ratio 3.866**.
  - ΔRSS(16→256) = 21,328 KiB = 20.8 MiB (informational).
- **Idle phases.** W = 0 → 1 within the idle phase in k16, k64 and X; W = 1 throughout in k128 and k256. The S drift was ≤ 536 KiB, and 2,072 KiB in X (`NOTE-idle-W.txt`).

Evidence: `run1/cluster/summary.txt`, `run1/cluster/<start>/*` and `run1/selfcheck.out`. The full thread dumps and NMT outputs are in the logs.

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity.** Three runs, each with 1 test and 0 failures [observed: `junit-testsuite.txt`]. All 13 arms completed M tasks, and the settle stayed 2 s everywhere (the cap was reached at the first look) [observed: `sepfp-lines.txt`]. Valid.
2. **Readings.** Nothing unusual. r3 N = 1 shows threads = 2, inside [1, 3]. Most likely a spinner, or overshoot path A3 (a) [inferred]. The heap deltas follow N to within 0.3 MiB, except N = 1 r2 (+0.97 MiB) [observed].
3. **Matched rows** [observed: `sepfp-lines.txt` r1–r3, `selfcheck.out` 301 unit checks]:
   - **F1 supported:** `maxRunningFinal` = min(N, M) and `pending` = M − min(N, M) for every N in all three runs; heapDelta (no Q) within [N − 4, N + 4].
   - **F2 supported:** threads ∈ [min(N, M), min(N, M) + 2], including control D (8); threads ≥ 64 35 s after the shrink, so no reclamation, against the yaml comment.
   - **F3 supported:** ΔQ ∈ [60, 68] MiB for every N (64.3–65.4).
4. **Excluded rows.** None of these occurred [observed]:
   - maxRunning > N, or < min(N, M).
   - threads > c + 2, or ≥ 2N.
   - threads < 64 after the shrink.
   - ΔQ outside [60, 68], or < 8.
   - heapDelta outside its band.
5. **Observed vs. inferred.** All rows rest on printed readings. The only inference (r3's one extra thread) is not used by any row.
6. **Deviations and gaps.** Defect 1 changed only the print format. The unit tier cannot see per-thread native memory (B2d).
7. **Core question.** For a directly driven executor:
   - At most N tasks ran, and the rest waited in the queue (pending = M − N).
   - Live worker threads equalled N (or the demand, when it was lower). Running heap rose with N, at 1 MiB per running task.
   - The 64 MiB carried by queued tasks was present in full at every N, from 1 to 128: queued memory does not follow the knob.
   - Threads created at N = 64 were all still alive 35 s after the knob was lowered to 1.

**Conclusion (unit tier):** B2g as amended: F1, F2 (with no reclamation) and F3 supported, and the controls hold. **Confirmed.**

**Cluster tier**

1. **Validity.**
   - Read-backs equalled the knob, and `ThreadStackSize` was 256 / 1,024 as intended [observed: `readback-*.txt`, `vmflags-excerpt.txt`].
   - The client held 400 queries in flight with 0 errors, 0 reconnects and 100% coverage in every C400 phase [observed: `*-phase.json`, raw `w*.lines`].
   - There was no laptop sleep (`run1-pmset-tail.txt` in the logs: the last wake was at 09:44, before the run).
   - The limit was reached at every knob: steady median Active = knob, and Pending ≈ 400 − knob.
   - **One frozen control did not hold:** "in each idle phase, W is constant" failed by one thread in k16, k64 and X [observed: `selfcheck.out`, `NOTE-idle-W.txt`]. The run is otherwise valid.
2. **Readings.**
   - W_max − knob = 18, 32, 32, 32. That is the knob plus ReadStage (12–32 running, at most 32) plus 2 [observed]. The expected "≈ knob + R + a few" holds.
   - The idle W event (0 → 1, 10–12 s after start-up, in every start) is an internal task whose worker parked at `SEPWorker.java:118` within about 2 s [observed: dump in the logs].
3. **Matched rows** [observed: `selfcheck.out` 83 cluster checks, of which 3 failed, all the idle drift]:
   - **F1 supported:** every 1 s poll and every sample had Active ≤ knob and R_ntr ≤ knob. The steady medians equalled the knob, and Pending was in band at all four knobs. C8 ≤ 8, and post-shrink ≤ 16.
   - **F2 supported (threads):** W_max within [knob, knob + 144], strictly increasing, ΔW = 254 ≥ 200. The C8 W_max of 17 ≤ 56 at every knob shows demand-driven creation. W did not drop after the shrink (288 → 288).
   - **F2 memory supported:** ΔS/ΔT = 268.0 KiB ∈ [256, 320] and ΔS = 66.7 MiB ≥ 50. Control X ratio 3.866 ∈ [3.0, 4.0].
   - **F3 (count) supported:** Pending = 400 − knob at every knob.
   - **Not met: the drift control** (W constant in idle) in 3 of 5 starts. By the tier-verdict mapping (B1 amendment: "Not confirmed: … a control fails"), the tier is **Not confirmed**.
4. **Excluded rows.** None of these occurred [observed]:
   - Active or R_ntr > knob (or > 16 after the shrink).
   - Median Active < knob, or client in-flight below 390.
   - W_max > knob + 144, ΔW < 200, or W_max not increasing.
   - C8 W_max > 56.
   - W dropping after the shrink.
   - X ratio < 3.0 or > 4.0.
   - ΔS/ΔT out of band.
   - Informational: ΔRSS = 20.8 MiB is not < 20.48 MiB, so the "not memory-significant" row does not fire, by 0.3 MiB. RSS differed by up to 18 MiB between idle starts, so this reading cannot separate the two sides of the 1% line [observed: `summary.txt` idle RSS].
5. **Observed vs. inferred.**
   - That the idle W event is unrelated to the knob is inferred: it occurred at the same time after start-up in all five starts, before any client connected, and its worker parked at once.
   - That it cannot account for any F2 relation is a computation [inferred from the margins: one thread against ΔW = 254 and every band margin ≥ 18 threads].
6. **Deviations and gaps.**
   - Defects 2–4 changed the instruments and the client, not the quantities.
   - NMT committed equals reserved on macOS, so touched stack is not observed. RSS is the only real-resident reading, and it is noisy (informational).
   - F3 bytes are not measured on the node (requests are about 100 B each).
   - The 1 s polls and 5 s dumps cannot see a sub-second overshoot. The unit tier's exact high-water covers that.
7. **Core question.**
   - On a node, `native_transport_max_threads` capped the NTR requests running at once at exactly the knob (16, 64, 128, 256, and 16 after a runtime shrink), with the excess queued.
   - The SharedPool worker-thread count followed the knob: about knob + 32. So did the threads' stack reservation: 268 KiB per added thread, 66.7 MiB more at 256 than at 16. RSS was about 21 MiB more at 256 than at 16.
   - Threads were created on demand: 17 at C = 8, whatever the knob. They were not released, staying at 288 for at least 60 s after the knob was cut to 16 and through new load.
   - The queue held all the excess, at every knob.

**Conclusion (cluster tier):** every "supported" row of F1, F2 and F3 holds, but the frozen idle drift control did not hold (one thread, in 3 of 5 starts). **Not confirmed** by the tier mapping.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

The self-check script is [`run1/selfcheck.py`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1/selfcheck.py). It was written before any reading (sha256 `8f3bdb1e…` in `hashes-before-unit-run1.txt` in the logs). It changed three times afterwards, each time before the run it reads:
- (i) The unit line filter follows the log prefix (defect 1; no unit reading had been seen).
- (ii) Active and Pending are read from the raw `tpjmx.log` (defect 2; after the shakedown, before cluster run 1).
- (iii) A stricter coverage check of the client's in-flight record (defect 4; it can only fail more). Cluster attempt 0's readings were seen, and that attempt is discarded.

It does not import the harness and does not read `samples.csv` or `summary.txt`. It re-reads:
- The raw unit test logs and XML.
- The raw thread dumps, NMT outputs and `tpjmx.log` of every sample (5,000+ files).
- The client `w*.lines`, `phases.txt`, the read-backs, `vmflags.txt` and `system.log`.

Result: **384 checks, 3 failed** ([`run1/selfcheck.out`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1/selfcheck.out)). The three failures are the idle drift control (k16, k64, X).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Unit: JUnit, completions. Cluster: read-backs, flags, client totals and coverage, no ERROR lines; the drift-control failure is stated, not hidden. |
| 2. Readings | yes | All W, R_ntr, NMT and Active/Pending values recomputed from the raw dumps and polls match `summary.txt`. |
| 3. Matched row | yes | Unit: every F1/F2/F3 check passes in r1–r3. Cluster: every F1/F2/F3 check passes. The tier is Not confirmed only through the drift control, exactly as the B1 mapping says. |
| 4. Excluded rows | yes | No refuting condition occurs in any raw file. |
| 5. Observed vs. inferred | yes | The only inferences (the idle event is unrelated to the knob, and too small to matter) are not used to lift the verdict. |
| 6. Deviations and gaps | yes | Defects 1–4 stated; the macOS NMT gap and the RSS noise stated. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | F1: independent running count = knob with queued excess. F2: W and NMT stack follow the knob, C8 separates demand from knob, X validates the instrument, the shrink shows no release. F3: unit ΔQ constant across N. |

### 5.2 Run 2?

**No.** Decided 2026-10-26. The unit tier is exact in three runs. The cluster tier's only open part is a frozen control that fails because of a reproducible post-start-up event, seen in all five starts. A run 2 by the same runbook would meet the same event and the same Not confirmed, and the conclusion rests on no inferred statement.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 7. Cluster re-run ("run 1b") after the B3a, B3f (drift control), B3h, B4 amendment — 2026-10-28

Session: Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-28, on the advisor's machine. Run 1's sections above are kept as filed; the
unit tier (Confirmed) was not re-run. Excerpts: [`run1b-cluster/`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1b-cluster/).

### 7.1 Frozen version and harness

| Field | Content |
|---|---|
| **Why** | Run 1's cluster tier was Not confirmed only through the frozen idle drift control "in each idle phase, W is constant". It failed by one thread (W 0 → 1, about 10 s after start-up) in k16, k64 and X, while every F1/F2/F3 "supported" row held (§4.2). The README says a wrong §9a "is a dated amendment to the case file and the affected tier starts again". The user authorised on 2026-10-28 that the control be restated from the source and the whole cluster tier re-run. |
| **Identification (source, then an instrument check)** | Read from the source first (`file:line` in the amendment; summary in R1, §3). The only internal task that submits to a SharedPool executor in an idle node after start-up is `CassandraRoleManager`'s default-role setup task. It is scheduled 10,000 ms (`AuthKeyspace.java:69`) after `doAuthSetup` (`CassandraDaemon.java:406` → `CassandraRoleManager.java:165-171`, `:485-504`). Its one CL ONE read of `system_auth.roles` (`:480`) goes to `Stage.READ.maybeExecuteImmediately` (`AbstractReadExecutor.java:165`). That call queues the task on an idle executor, because `takeWorkPermit` requires `taskPermits != 0` (`SEPExecutor.java:196`, `:221-223`). `addTask` then starts one spinning worker (`:135-142`, `SharedExecutorPool.java:137-138`, `:108-116`). So the task creates one worker if none exists and none otherwise. **Instrument check (before the amendment, a diagnostic start, not a case reading):** observe-only Byteman rules (`sep-worker-origin.btm`, [`TestScript: no errors`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1b-cluster/instrument/btm-check.txt)) in one knob-16 start on populated data, in the re-run clone (01:41:51–01:44:48 EDT). They logged exactly one `addTask` (ReadStage, caller `OptionalTasks:1`) and one `new SEPWorker` (`SharedPool-Worker-1`). The creator's stack runs from `CassandraRoleManager.hasExistingRoles:480` ← `setupDefaultRole:450` ← the `scheduleSetupTask` lambda `:497` through `AbstractReadExecutor.makeRequests:165` → `SEPExecutor.maybeExecuteImmediately:223` → `addTask:142` → `maybeStartSpinningWorker:138` → `schedule:114`. The task started 10,006 ms after `doAuthSetup` ([`instrument/origin-probe-kp-node-out-SEPW.txt`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1b-cluster/instrument/origin-probe-kp-node-out-SEPW.txt), [`origin-probe-system-log-lines.txt`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1b-cluster/instrument/origin-probe-system-log-lines.txt)). |
| **Amendment** | Four dated amendments `Amendment 2026-10-28 (after run 1, authorised by the user)`, each next to the text it changes and each saying that it follows run 1's readings. **B3f:** the drift control "W constant" is replaced by (d1) W never decreases and rises at most once, by exactly 1, only from 0 to 1; (d2) no idle sample whose dump ended before T_ar + 10,000 ms shows W ≥ 1, where T_ar is the `StorageService.java:1466` line of the start's `system.log` and precedes `doAuthSetup`; (d3) S ≤ 4 MiB, unchanged. It also checks that the JVM arguments do not set `cassandra.superuser_setup_delay_ms`. Reported, not conditions: the step's time against [T_ar + 10 s, T_pw + 10 s], and "Setup task failed" lines. **Why an allowance and not a wait:** the task logs nothing when the role exists (`CassandraRoleManager.java:449-457`), a not-safe rerun is logged only at TRACE (`:491`), and each rerun moves it by 10 s. A wait would need a margin with no source basis, while the source fixes the number of workers (one, and only from W = 0). The allowance also keeps B3e's timeline. **B3h:** the idle control is (d1)–(d3). **B3a / B4:** fresh clone `$W/cassandra-run72`, node `$W/node-sep72`. B1, every F1/F2/F3 relation, the S part, B3g, the verdict and Effect mappings and the unit tier are unchanged. |
| **What was known of run 1 when writing it, and would run 1 pass** | **Everything in run 1's §4–§5 was known**, including the idle readings: W 0 → 1 between the samples about 7 and 12 s after "Startup complete" in k16, k64 and X; W = 1 at every idle sample in k128 and k256; S drift ≤ 2,072 KiB; `NOTE-idle-W.txt`. Run 1's raw `system.log` files were not opened for T_ar or T_pw before the amendment was written. The allowance of one worker and the 10,000 ms come from the source (`SharedExecutorPool.java:108-116`; `AuthKeyspace.java:69`), not from run 1's count. **Would run 1 pass? Yes.** The amended self-check on run 1's raw files gives **98 checks, 0 failed** ([`run1b-cluster/selfcheck-known-answer-on-run1-relations-amended.out`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1b-cluster/selfcheck-known-answer-on-run1-relations-amended.out)). In each of k16, k64 and X, the W = 0 sample lies before T_ar + 10 s and the W = 1 dump after it; in k128 and k256, the first idle sample (W = 1) is 113 ms and 50 ms after T_ar + 10 s. So run 1's tier, read with the amended control, would have been Confirmed. That is why the amendment is stated as following run 1, and why the tier was re-run rather than re-judged. |
| **Case-file version** | sha256 **`83890d4b2115b867a0259d96261547ae352c3fbb427377ca9198236edfbc33f8`**, a new row in `_INDEX.md` §4: "re-frozen after run 1 for cluster re-run (B3a, B3f drift control, B3h, B4), authorised by the user". The earlier rows (`9f100262…`, `d5d2f122…`, `f8eb812b…`, `1ccbf2d4…`, `e9ce4c6c…`, `b60d5475…`) are kept. Hashed at 01:50:04 EDT, after the clone and build (01:38:59–01:39:52) and the instrument check, and before the shakedown (01:52:18) and any re-run reading. It was recorded again at 01:52:17 in [`run1b-cluster/harness-sha-run2.txt`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1b-cluster/harness-sha-run2.txt), and a copy of the file at that hash is in the log folder (`case-file-at-refreeze-83890d4b.md`). Section D was filled afterwards, so the file's current hash differs by that section only. Base commit `18814283`; nothing committed. |
| **Harness** | Run 1's harness with H1 (paths), H2 (probe plan and rules, used only before the amendment), H3 (self-check copy) and H4 (excerpts) only (§3). `loadclient.py`, `Jmx.java`, `Sampler.java` and `summarize.py` are unchanged (sha256 prefixes `e92f29a5`, `2521f467`, `7d871444`, `80010a05`, as in run 1); `cluster-run.sh` `7ac0da6c`. Commands: `SEP_C=$W/cassandra-run72 SEP_NODE=$W/node-sep72 cluster-run.sh shake-run2 shake`, then `… caffeinate -ims cluster-run.sh run2 run1`. **The self-check ran end to end on the shakedown first:** 39 checks, 0 failed, exit status 0 ([`run1b-cluster/shakedown/selfcheck.out`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1b-cluster/shakedown/selfcheck.out)). It was not changed after the shakedown or the re-run (sha256 `e511d63b…` in `harness-sha-run2.txt`). The shakedown ran every step (populate; k256 with C8, C400, the JMX shrink, postshrink idle and load; k16), with 0 client errors and every read-back right. No runbook defect. |

### 7.2 Environment

Same host as run 1 (§2): `yangwang-mbp`, macOS 27.0.1 / Darwin 27.0.0 arm64, 10 cores, 32 GiB; OpenJDK 11.0.32.1, Ant 1.10.18, Python 3.8.11 with the
bundled driver 3.29.0; 107 GiB free; loopback `.1`–`.3` present (only `.1` used); ports 7000, 7199, 9042, 9091 free and no Cassandra process
before each run. 2026-10-28 (EDT):
- fresh clone and build 01:38:59–01:39:52;
- instrument check 01:41:51–01:44:48;
- re-freeze 01:50:04;
- shakedown 01:52:18–01:59:55;
- **re-run 02:01:35–02:42:51** under `caffeinate -ims`, with no sleep or wake event (`pmset`: last wake 2026-10-27 18:15).

The clone is `$W/cassandra-run72`, from `~/cassandra-src` at `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), with no local change (`ant -Dlocal.repository=$W/m2 build-test`, `BUILD SUCCESSFUL`, 52 s; [`run1b-cluster/clone-build-run72.txt`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1b-cluster/clone-build-run72.txt)). The node is as in run 1: `MAX_HEAP_SIZE=2G`, `-XX:NativeMemoryTracking=summary -Dcassandra.set_sep_thread_name=false` (plus `-Xss1m` in X), and no agent. Node data is in `$W/node-sep72`, wiped at the end.

Full logs are in `~/Library/Caches/stage4/logs/sep_maximum_pool_size-takeWorkPermit/`:
- `clone-build-run72.log`, `origin-probe/btm-check.txt`, `cluster-origin-probe/` (the instrument check);
- `case-file-at-refreeze-83890d4b.md`, `harness-sha-run2.txt`;
- `cluster-shake-run2/`, `driver-shake-run2.out`, `selfcheck-shake-run2.out`;
- `cluster-run2/`, laid out as run 1's `cluster-run1/`, with the raw `td-`, `nmt-` and `tp-` files of every sample;
- `driver-run2.out`, `run2-start-epoch.txt`, `run2-end-epoch.txt`, `run2-pmset-tail.txt`;
- `selfcheck-run2.out`, `selfcheck-run2-under-run1-relations.out`.

Excerpts in `run1b-cluster/`:
- `cluster/`: run 1's kinds of files, plus `system-log-marks.txt` per start, the k16 idle dump of `SharedPool-Worker-1`, and the k256 peak NMT block;
- `shakedown/`, `instrument/`, `selfcheck.py`, `selfcheck.out`, `selfcheck-rerun-under-run1-relations.out`;
- `selfcheck-known-answer-on-run1-relations-{run1,amended}.out`, `harness-sha-run2.txt`, `clone-build-run72.txt`.

### 7.3 Readings

From `run1b-cluster/cluster/summary.txt`, the per-start `samples.csv`, `tpjmx.log`, `sample-timing.txt`, `readback-*.txt`, `*-phase.json` and `system-log-marks.txt`. `selfcheck.py` recomputed them from the raw dumps, polls, client lines and logs.
- Populate: 200,000 rows, one SSTable of 49 MB live; `Created default superuser role 'cassandra'` in the populate start only.
- Each knob start: read-back equal to the knob (attribute and gauge); `ThreadStackSize` 256 (1,024 in X); 0 `ERROR` lines.
- Clients: every C8 and C400 phase had 0 client errors and 0 reconnects, in-flight medians of 8 or 4 × 100, and 100% coverage.
- Samples were 5.0 s apart, and every drain finished in 7–8 s.

| knob | C8 W_max | C400 W_max (band) | steady median Active / R_ntr | max Active (1 s polls) / max R_ntr | steady median Pending (band) | median ReadStage Active | peak NMT thread # / stack reserved (KiB) | peak RSS (KiB) |
|---|---|---|---|---|---|---|---|---|
| 16 | 17 | **33** ([16, 160]) | 16 / 16 | 16 / 16 | 384 ([344, 392]) | 11 | 115 / 79,204 | 2,026,560 |
| 64 | 17 | **104** ([64, 208]) | 64 / 64 | 64 / 64 | 336 ([296, 344]) | 32 | 187 / 98,500 | 2,410,224 |
| 128 | 17 | **160** ([128, 272]) | 128 / 128 | 128 / 128 | 272 ([232, 280]) | 32 | 243 / 113,508 | 2,406,240 |
| 256 | 17 | **288** ([256, 400]) | 256 / 256 | 256 / 256 | 144 ([104, 152]) | 32 | 371 / 147,812 | 2,429,296 |
| X (256, `-Xss1m`) | — | 288 | 256 / 256 | 256 / 256 | 144 | 32 | 367 / 407,860 | 2,526,192 |

- **C8 control** (every knob): Active and R_ntr ≤ 8 in every sample; W_max = 17 ≤ max(W_idle, 56).
- **Runtime shrink at 256.** JMX set 16, and it read back as 16 (attribute and gauge); `system.log` has "Resized Native-Transport-Requests maximum pool size from 256 to 16". W was 288 in all 12 postshrink-idle samples and in every later sample. Under new C = 400 load, every 1 s poll (115) had Active ≤ 16 with `ntrMax` = 16, and every sample had R_ntr ≤ 16; the steady medians were Active 16 and Pending 384.
- **Cross-knob.**
  - W_max 33 < 104 < 160 < 288; ΔW(16→256) = 255.
  - ΔS = 68,608 KiB = 67.0 MiB over ΔT = 256 threads: **268.0 KiB per thread**. Committed = reserved.
  - Control X: idle→peak slope 1,036.0 KiB per thread (ΔT = 290), against 268.0 (ΔT = 294) at 256: **ratio 3.866**.
  - ΔRSS(16→256) = 402,736 KiB, informational. k16's peak RSS (2,026,560 KiB) is about 400 MiB *below* its own idle RSS (2,433,120 KiB). On this macOS host, RSS moves with the OS's page handling, not only with the JVM, so this reading says nothing about significance.

**Idle phases (the amended control)**, from the raw dumps, `sample-timing.txt` and `system-log-marks.txt` (offsets from "Startup complete"):

| start | W sequence (6 samples) | last W = 0 sample | first W = 1 dump ended | T_ar + 10 s / T_pw + 10 s | S drift (KiB) | (d1) / (d2) / (d3) |
|---|---|---|---|---|---|---|
| k16 | 0,1,1,1,1,1 | +7.35 s | +12.36 s | +9.960 / +9.973 s | 536 | hold / hold / hold |
| k64 | 0,1,1,1,1,1 | +7.18 s | +12.20 s | +9.957 / +9.969 s | 536 | hold / hold / hold |
| k128 | 0,1,1,1,1,1 | +7.19 s | +12.20 s | +9.961 / +9.974 s | 536 | hold / hold / hold |
| k256 | 0,1,1,1,1,1 | +7.13 s | +12.15 s | +9.961 / +9.973 s | 536 | hold / hold / hold |
| X | 0,1,1,1,1,1 | +7.12 s | +12.13 s | +9.963 / +9.976 s | 2,072 | hold / hold / hold |

No "Setup task failed" line, and no `superuser_setup_delay_ms` on any JVM command line. In k16, the first W = 1 dump shows `SharedPool-Worker-1` with `elapsed=2.37s`, i.e. created at about +9.98 s, inside [T_ar + 10 s, T_pw + 10 s + run time]. It was parked at `SEPWorker.run(SEPWorker.java:118)` ([`cluster/k16/td-idle-1793167378163-SharedPool-Worker-1.txt`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1b-cluster/cluster/k16/td-idle-1793167378163-SharedPool-Worker-1.txt)). This time the step fell inside the idle phase in all five starts (in run 1, in three).

### 7.4 Cluster re-run — conclusion and logic

1. **Validity.**
   - The re-run used the re-frozen version (`83890d4b…`, hashed at 01:50:04, before the shakedown and the re-run) [observed: `_INDEX.md` §4; `harness-sha-run2.txt`].
   - Every B3 step ran from the beginning in the frozen order, in a fresh clone, after a shakedown that ran every step [observed: `cluster/summary.txt`, `shakedown/`].
   - The read-backs and flags are as intended. The client held 400 in flight with 0 errors and 100% coverage, and there was no laptop sleep.
   - The limit was reached at every knob: steady median Active = knob, and Pending = 400 − knob [observed].
   - Valid.
2. **Readings.**
   - The F readings repeat run 1. W_max − knob = 17, 40, 32, 32. At k64 it was 32 in run 1; the k64 reading of 40 is knob + 32 ReadStage + 8, inside the band, and is an expected run-to-run difference in transitional workers (A3 (a)) [observed; the explanation is inferred].
   - The idle W step happened once per start, 0 → 1, at the source-derived time [observed].
3. **Matched row** [observed: `selfcheck.out`, 98 checks, 0 failed]:
   - **F1 supported:** every 1 s poll and every sample had Active ≤ knob and R_ntr ≤ knob. The steady medians equal the knob, with Pending in band at all four knobs. C8 ≤ 8; post-shrink ≤ 16 with median 16.
   - **F2 supported (threads):** W_max within [knob, knob + 144], strictly increasing, ΔW = 255 ≥ 200. C8 W_max = 17 ≤ 56. No reclamation (288 → 288 through 60 s of idle and new load).
   - **F2 memory supported:** ΔS/ΔT = 268.0 KiB ∈ [256, 320], ΔS = 67.0 MiB ≥ 50, control X ratio 3.866 ∈ [3.0, 4.0].
   - **F3 (count) supported:** Pending = 400 − knob at every knob.
   - **Controls hold**, including the amended drift control (d1)–(d3) in all five starts.

   Tier rule (B1 amendment): **Confirmed**. Effect: **caps only on some paths (bypass)**. Running tasks and worker threads with their stack reservation are capped; the queue holds all the excess (on the node by count, in bytes in the unit tier).
4. **Excluded rows** [observed]. None of these occurred:
   - Active or R_ntr > knob, or > 16 after the shrink.
   - Median Active < knob, or client in-flight below 390.
   - W_max > knob + 144, ΔW < 200, or W_max not increasing.
   - C8 W_max > 56.
   - W dropping after the shrink.
   - X ratio outside [3.0, 4.0], or < 1.5.
   - ΔS/ΔT out of band.
   - An idle W outside (d1)–(d3).
   - Informational: ΔRSS ≥ 20.48 MiB, so the "not memory-significant" row does not fire, but the reading is noise (§7.3).
5. **Observed vs. inferred.**
   - Observed: every condition, from the raw dumps, polls, client lines and logs.
   - Inferred: that the idle worker in the re-run's starts is the default-role task's. This rests on the source and on the instrument check in a separate start. The re-run's own evidence agrees: one 0 → 1 step per start, created at +9.98 s (k16, from `elapsed`), inside the derived window. The re-run starts carry no agent, so they do not show the creator.
6. **Deviations and gaps.**
   - None against the re-frozen runbook: no runbook defect, and no harness change after the re-freeze besides H1–H4.
   - The amendment was written knowing run 1's readings, and run 1 would also pass it (§7.1). The re-run therefore adds a run under the stated control, not an independent test of whether the control was chosen fairly. The control's terms (one worker, only from 0, not before T_ar + 10 s) come from the source.
   - The other gaps as in run 1: NMT committed = reserved on macOS; RSS is not a usable significance reading here; F3 bytes are not measured on the node; a sub-second overshoot is not visible at 1 s / 5 s (the unit tier's exact high-water covers it).
7. **Core question.**
   - On a node, `native_transport_max_threads` capped the NTR requests running at once at exactly the knob (16, 64, 128, 256, and 16 after a runtime shrink), with the excess queued.
   - The SharedPool worker-thread count and its stack reservation followed the knob: 33 / 104 / 160 / 288 workers; 268 KiB per added thread, 67 MiB more at 256 than at 16.
   - Workers were created on demand (17 at C = 8, whatever the knob) and never released.
   - Before any load, exactly one worker appeared about 10 s after start-up, from the default-role setup task, as the source says.

**Conclusion (one line):** cluster re-run: B3g rows F1, F2 (threads and memory) and F3 supported, and every control held, including the amended drift control. Confirmed — caps only on some paths (bypass).

### 7.5 Self-check of the cluster re-run — AI

`run1b-cluster/selfcheck.py` (H3) re-reads the raw files and does not read `samples.csv` or `summary.txt`:
- the thread dumps and NMT outputs of every sample;
- `tpjmx.log` and `sample-timing.txt`;
- the client `w*.lines` and `phase.json`;
- `phases.txt`, the read-backs, `vmflags.txt` and `system.log` (T_ar, T_pw, "Startup complete", JVM arguments, "Setup task failed").

It was written after the re-freeze and before any re-run reading, and was not changed afterwards.
- **Pass 0 (shakedown, run end to end first):** 39 checks, 0 failed, exit status 0; verdict line "not judged" (two starts) ([`shakedown/selfcheck.out`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1b-cluster/shakedown/selfcheck.out)).
- **Pass 1 (re-run raw files, amended relations):** **98 checks, 0 failed**, exit status 0; `VERDICT B3g: F1 supported, F2 supported (threads; no reclamation), F2 memory supported, F3 (count) supported; controls hold -> Confirmed - caps only on some paths (bypass)` ([`selfcheck.out`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1b-cluster/selfcheck.out)).
- **Pass 2 (known answer: run 1's raw files, run-1 relations):** 83 checks, 3 failed (the three idle drift lines, k16, k64, X). The 84 cluster lines are **identical** to the cluster lines of `run1/selfcheck.out` (`diff` empty) ([`selfcheck-known-answer-on-run1-relations-run1.out`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1b-cluster/selfcheck-known-answer-on-run1-relations-run1.out)).
- **Pass 3 (run 1's raw files, amended relations):** 98 checks, 0 failed. Run 1 would pass the amended control (§7.1) ([`selfcheck-known-answer-on-run1-relations-amended.out`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1b-cluster/selfcheck-known-answer-on-run1-relations-amended.out)).
- **Pass 4 (information: re-run raw files, run-1 relations):** 83 checks, 5 failed. All five are the frozen "W constant": this time the step fell inside the idle phase in every start ([`selfcheck-rerun-under-run1-relations.out`](sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/run1b-cluster/selfcheck-rerun-under-run1-relations.out)).

Raw files re-opened by hand:
- `cluster-run2/k16/samples/td-1793167378163.txt` (`SharedPool-Worker-1`, `elapsed=2.37s`, parked at `SEPWorker.java:118`);
- `cluster-run2/k16/system.log` (`06:02:45,768 StorageService.java:1466`, `06:02:45,781 CassandraDaemon.java:450`, `06:02:45,808 Startup complete`);
- `cluster-run2/k256/samples/nmt-1793169279455.txt` (`thread #371`, `stack: reserved=147812KB`);
- `cluster-run2/k256/system.log` ("Resized … from 256 to 16");
- `cluster-run2/summary.txt` (final: no Cassandra or stress process, node wiped).

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | Re-frozen hash before the shakedown; read-backs, flags, client totals and coverage, no ERROR lines. |
| 2. Readings | yes | W, R_ntr, NMT, Active/Pending and the idle step times recomputed from the raw files match `summary.txt`. |
| 3. Matched row | yes | Every F1/F2/F3 check and every control passes, including (d1)–(d3). |
| 4. Excluded rows | yes | No refuting or Not-confirmed condition in any raw file. |
| 5. Observed vs. inferred | yes | The idle worker's origin in the re-run starts is inferred (source + instrument check + timing); no row depends on it beyond (d1)–(d2), which are observed. |
| 6. Deviations and gaps | yes | The non-blind amendment (run 1 would pass it), the k64 W_max difference, and the RSS noise are stated. |
| 7. Core question — logic | yes | As in run 1, with the idle baseline now checked against what the source says an idle node does. |

**Run 2?** No (2026-10-28). The re-run repeats run 1's F readings, the idle control holds in all five starts, and its terms are exact source quantities; a further run would not change the row.

### 7.6 Verdict of the cluster re-run

**Confirmed — caps only on some paths (bypass)**: B3g F1, F2 (threads and memory) and F3 supported, and every control held, including the amended drift control (d1)–(d3). It is filed in §8 as a new cluster row; the run-1 cluster row (Not confirmed) is kept.

**End of the re-run:**
- No `CassandraDaemon`, stress or load-client process; port 9042 free.
- `$W/node-sep72` removed; `git -C $W/cassandra-run72 status` clean; no `cassandra.logdir_IS_UNDEFINED/` folder.
- `results/<stem>/run1/` unchanged.

## 8. Verdict — AI

**Stage-3 estimate:** undetermined.

**Claim tested** (B1, as amended): with demand above the cap, the number of tasks of an SEP executor running at once never exceeds `maximumPoolSize` (F1). The SharedPool worker-thread count and its stack memory rise with the knob within the derived bands, and threads are not released when the knob is lowered (F2). Memory held by queued tasks does not follow the knob (F3). "Confirmed" means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed.** F1: maxRunning = min(N, M), pending = M − N, running heap = N MiB (N = 1…128). F2: threads = N (8 at control D), still 64 35 s after a shrink to 1. F3: queued payloads +64.3–65.4 MiB at every N. Three identical runs. | **caps only on some paths (bypass):** running tasks and worker threads capped; queued-task memory does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | **Not confirmed** (tier mapping: the frozen idle drift control "W constant" failed by one thread in 3 of 5 starts, from a post-start-up internal task). Every F1/F2/F3 "supported" row holds: running NTR tasks = knob exactly (16/64/128/256; 16 after the runtime shrink), Pending = 400 − knob; W_max 34/96/160/288 (ΔW 254), 17 at C = 8, 288 kept after the shrink; NMT stack +268 KiB per thread, +66.7 MiB from 16 to 256; `-Xss1m` control ratio 3.87 | as observed: **caps** running tasks and worker threads with their stack reservation; the queue holds all excess (count) | run 1 + self-check | 2026-10-26 |
| Cluster (re-run at `83890d4b…`, after the user-authorised B3a, B3f drift control, B3h, B4 amendment) | **Confirmed.** B3g F1, F2 (threads and memory) and F3 supported; every control held, including the amended drift control: in all five starts a single idle step W 0 → 1, never before T_ar + 10 s, S drift ≤ 2,072 KiB. That is the one ReadStage worker the default-role setup task creates (`CassandraRoleManager.java:480`, `SEPExecutor.java:196`, `:221-223`, `:135-142`). Running NTR tasks = knob exactly (16/64/128/256; 16 after the runtime shrink), Pending = 400 − knob; W_max 33/104/160/288 (ΔW 255), 17 at C = 8, 288 kept after the shrink; NMT stack +268.0 KiB per thread, +67.0 MiB from 16 to 256; `-Xss1m` control ratio 3.866. Run 1's raw files would also pass the amended control (98/98) | **caps only on some paths (bypass):** running tasks and worker threads with their stack reservation capped and following the knob; queued-task memory does not follow it (the queue holds all excess; bytes shown in the unit tier) | cluster re-run (§7) + self-check | 2026-10-28 |

**Positive control** (the instruments): unit, the Q phase moved heap by 64 MiB; cluster, `-Xss1m` moved the per-thread stack reservation 3.87×.

**Stage-3 finding recorded** (not tuned for): stopped SharedPool workers park forever (`SEPWorker.java:116-118`), contrary to the `cassandra.yaml` comment that idle threads stop after 30 s. Both tiers observed it: 64 threads 35 s after the unit shrink, and 288 threads for 60 s of idle after the node shrink.

**Feedback filed:**
- The case file's section D (uncommitted). The nineteen step-0 amendments and the four runbook-fix amendments are in the case file, dated.
- All post-filing hashes are new rows in `_INDEX.md` §4.
- The §1 Stage 4 column and the coverage line are updated.
- No section was amended for a refutation (none occurred).

**Feedback filed for the cluster re-run (2026-10-28):**
- The four amendments `Amendment 2026-10-28 (after run 1, authorised by the user)` in the case file (B3a, B3f drift control, B3h, B4).
- A new `_INDEX.md` §4 row (`83890d4b…`).
- A new entry in the case file's section D.
- The §1 Stage 4 column (run-1 text kept, re-run verdict appended). The coverage section is not touched.
- No refutation, so no other case section is amended.

Run-1 findings kept as observations: SharedPool workers never retire, contrary to the yaml's "idle threads are stopped after 30 seconds" (`conf/cassandra.yaml:1033-1034`; `SEPWorker.java:116-118`).

New source observation, for stage 3: `SEPExecutor.maybeExecuteImmediately` never runs a task inline on an idle executor. `takeWorkPermit(false)` returns false whenever no task is queued (`SEPExecutor.java:196`), so the "immediate" path queues the task and starts a worker (`:221-223`, `:135-142`). A3's "if no permit is available, the task is queued instead" describes only part of that path.
