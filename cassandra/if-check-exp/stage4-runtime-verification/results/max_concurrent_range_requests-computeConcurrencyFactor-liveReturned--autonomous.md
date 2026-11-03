# max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous — stage-4 results  <!-- file: results/max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous.md -->

> **Case:** [`max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous`](../../stage3-ai-deep-read/cases/max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous.md)
>
> **Status:** verdict filed (2026-10-27). **Unit: Confirmed — caps** (run 1; closed, not re-run). **Cluster: Confirmed — caps** (cluster
> re-run "run 1b" of 2026-10-27 at the re-frozen version `d0bf9c41…3779`, after the user-authorised amendment of B3a, B3c, B3f, B3g and B3h;
> run 1's cluster verdict, Not confirmed (C8 row (b)), is kept in §8 and §4 unchanged). The re-run is §7.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous/`](../harness/max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous/).
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e;
> the case file's feedback section is its section D. Session: Claude Opus 5.5 (claude-opus-5-5), advisor-run, on the advisor's Mac.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Branch `advisor-run`, uncommitted on 2026-10-27 (as filed in `fa4dc0c`'s tree with sha256 `fa5a9a28…6ac`). Frozen after the audit's 14 amendments (U1–U5, C1–C9): sha256 `a2dc5f0d7677e3dc877fcf6bed05a60ef8e00e468d485efd8a044e3ddef4bded`, recorded in `_INDEX-advisor.md` §2 before any harness run. The unit shakedown then found runbook defect D1 (§3); its dated fix corrects only the unit default row: sha256 **`4c8138c989059d4927a8e8671f3bb766c1eb0f541ecdc8d65908f9ed3d289fb2`** (second §2 row). **Both tiers of run 1 ran at this version.** Section D is filled after this hash. |
| **Harness** | `harness/max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous/`: `RangeCapProbe{1,4,16,Default}Test.java` (CQLTester unit tests, copied into the clone only for the run), `unit-run.sh`; `stage4/rng/RngProbe.java` (observe-only helper) and `rng.btm` (six Byteman rules), `RngJmx.java` (JMX reader), `rng-client.py` (bundled-driver client), `cluster-run.sh`; self-check `results/max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous/run1/selfcheck.py`. Not committed (the user has not asked for a commit). Reused with attribution: `unit-run.sh` and `cluster-run.sh` adapt the structure and node start/stop functions of `harness/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous/`; `rng-client.py` adapts that folder's driver set-up; `RngJmx.java` adapts its `RfpJmx.java`; the probe pattern (Byteman rule calling a `sys:` helper) follows that folder's `rfp.btm`. The test set-up of the property follows upstream `RangeCommandsTest.java:56-66`. Ring, workload, rules and every bound are this case's; no value or derivation was taken from another case file or results file. |
| **Tiers and values** | Unit: four classes, C ∈ {1, 4, 16, default (20 in the test JVM, D1)}. Cluster: 3 nodes (127.0.0.1–.3), node 1 the coordinator with one empty token range, nodes 2/3 owning the 48 dense ranges; 288,000 rows of 2 KiB; C ∈ {1, 4, 16, 48, default (100)}, per value one traced query, 20 plain first-page queries (`fetch_size` 5000) and 3 GC-mode queries; at C = 48 also 20 queries at `fetch_size` 500 (B3h control). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: sub-range requests per batch, a count whose byte size is the buffered `ReadResponse`s on the coordinator heap (≤ page-limit rows each). |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly | B2b {1, 4, 16}, B3b {1, 4, 16, 48}: the default `10 × availableProcessors` (`RangeCommands.java:54`) in neither. Added (U2, C3). |
| A. Core question | real resource measured, not only the counter | Partly | Unit: operand only, said so (B2d). Cluster: B3d (1) `jstat` cannot attach on this host (`-XX:+PerfDisableSharedMem`), and a 50-ms envelope under G1 with young ≥ 50 % of the heap sums allocation since the last young GC. Replaced by a Byteman probe of response bytes brought into the heap (R_total), bytes held at the read's close (H) and an in-process post-GC live delta (L) (C5). |
| A. Core question | usage driven to the limit and past it | Partly | As filed, node 1 owns the wrapping range (t_47, MIN] ≈ 1/49 of the ring, so its estimate is not 0 and the first batch is not the single empty range (C2). After C2: 48 dense ranges of ≈ 6,000 rows > the 5,000-row page; C = 48 and the default are uncapped controls. |
| B. Logic | each step says what it establishes | Met | B2h/B3h tie C = 48 to "uncapped burst" and `fetch_size=500` to the per-response size term. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | Unit: exact, but "min(32, C)" for 33 sub-ranges and no default row (U2, U4). Cluster: request counts exact; heap bands approximate and for the jstat envelope; replaced by exact request counts per batch and byte bands per response (C7 P1–P6). |
| B. Logic | every plausible outcome has a conclusions row | Partly | Missing: read-back mismatch, ring mismatch, retained peak not reached, replica drops, instrument failure, counter disagreement. Added (U5, C8). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The trace line of the target branch (`:165`) and the probe's batch-2 request count with sub-ranges remaining (the loop stopped at `i < concurrencyFactor`, `:230`) are the disallow evidence; bytes per query follow min(C, 49). |
| B. Logic | alternative explanations and their controls | Partly | "First range not empty or merged" is row 4 but needs a check: node-1 sstable count 0 and 2 batches with batch 1 = 1 request (C4, C8 c). Replica-side drops (outbound reserve) added (C5, C8 b). |
| C. Specific | a human can follow it from the intro and §9a | Met | A3 states the chain to `:162` and the per-range buffering. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | `/local` paths, Linux host, cqlsh trace (pages at 100 rows), wrong MBean type, no client spec. Amended (U1, C1, C4–C6). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Key generation, load, flush check, page reading, order of runs open. Amended (C4, C6). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | `/local`, `jstat`, node 2/3 heap (8 GiB each pre-touched if unset) replaced (U1, C1, C5). |
| D. Runnable | workload arithmetic reaches the limit | Met after C2 | 288,000 × 2 KiB ≈ 0.6 GB on nodes 2/3; ≈ 10.4 MB per dense response; ≤ 48 × 11 MB ≈ 0.53 GB per uncapped read on a 4 GiB node-1 heap. |
| D. Runnable | load-bearing citations spot-checked | Met | Against the clone at `b5f2a54210`: `RangeCommandIterator.java:159-177` (`computeConcurrencyFactor`; filed `:156-176`), `:162` target, `:165` trace, `:230-240` loop, `:250` trace, `:151-156` (`updateConcurrencyFactor`; filed `:148-153`), `:292-301` accessors; `RangeCommands.java:54, 84-97, 125-135`; `ReadResponse.java:228`; `ByteBufferUtil.java:444-451`; `ReplicaPlans.java:774-793`; `InternodeInboundMetrics.java:53,65`. Line drift of 3 lines in two filed citations; none load-bearing. `liveReturned += counter.counted()` is executed twice per batch (`:115` and `:153`), which doubles the non-zero branch's estimate but cannot change the zero test at `:162`. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | U1/C1: this host's clone, paths, heaps; node 2/3 2 GiB | applied, amendments 2026-10-27 | `/local` absent; auto heap 8 GiB × 2 pre-touched |
| 2 | U2/C3: the default added to both tiers; the knob read back | applied | group A |
| 3 | U3/U4/U5: exact unit procedure, predictions, rows | applied | group B, C |
| 4 | C2: ring fixed so node 1 owns only two empty pieces | applied | the filed ring gives node 1 the wrapping range and ≈ 5,900 rows |
| 5 | C4: exact client, key generation, load, flush check, first-page reading | applied | group C |
| 6 | C5: probe (BATCH/RESP/CLOSE), in-process post-GC live delta, `InboundConnection` MBean, driver trace, replica drop counters | applied | jstat cannot attach; wrong MBean type; cqlsh page size |
| 7 | C6–C8: exact sequence; predictions P1–P6; rows | applied | group B |
| 8 | Stage 3: the claim's "peak heap" is timing-dependent for a first-page read: responses that arrive after the page is complete are dropped at once, so the retained peak can be anywhere between one response and min(C, dense) responses; the bound the cap gives is on the bytes a read can bring in (R_total) | left for stage 3 | wording of B1; C7/C8 test both |
| 9 | Stage 3: `liveReturned` is incremented twice per batch (`RangeCommandIterator.java:115` and `:153`), so the non-zero branch (`:170-173`) sees twice the rows returned and under-sizes later batches; outside this case's branch | left for stage 3 | a separate finding, not tested here |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit 03:56–03:57, cluster 03:57–04:09 local time, EDT; shakedowns 03:40–03:55) |
| Node | `yangwang-mbp`, the advisor's MacBook Pro (Apple M1 Pro, arm64), single host; 10 cores, 32 GiB (`hw.memsize` 34359738368) |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64) |
| Ant | Apache Ant 1.10.18 |
| Local `cassandra-src` clone commit | `$W/cassandra-run51` (`W=~/Library/Caches/stage4`), fresh `git clone --branch cassandra-5.0.9 ~/cassandra-src`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`; `ant -Dlocal.repository=$W/m2 build-test` BUILD SUCCESSFUL in 50 s; `git status` clean after both tiers |
| Case-file commit / harness commit | case file uncommitted at sha256 `4c8138c9…89fb2` (on `fa4dc0c`); harness uncommitted |
| Storage for node data | internal SSD, APFS `/dev/disk3s1`, 123 GiB free; unit data under the clone's `build/test`; node files `$W/node-rng1..3` (removed at the end; sizes in `run1/cluster/node-du.txt`) |
| Loopback / ports | `127.0.0.1`–`.3` on `lo0` (all three used); 7000, 7199, 7299, 7399, 9042, 9091 free before each run |
| Full logs (outside the repo) | `$W/logs/max_concurrent_range_requests-computeConcurrencyFactor-liveReturned/` (`clone.log`, `build-test.log`, `unit-shake/`, `unit-r1/`, `cluster-shake/`, `cluster-shake2/`, `cluster-r1/`) |

Machine facts relied on: workspace `$W` and `env.sh`; commands touching `$W`/Java run unsandboxed; `-Dlocal.repository=$W/m2` on every ant call; test stdout read from `build/test/logs/**/TEST-<class>.log`; no `setsid` (nodes as tracked background processes, `bin/cassandra -f > log < /dev/null`); loopback aliases `.2`/`.3` checked with `ifconfig lo0`; `auto_bootstrap: false` because bootstrap streaming fails here; `CASSANDRA_CONF`/`CASSANDRA_LOG_DIR` outside the clone so it stays clean; `JVM_EXTRA_OPTS` scoped to node 1's command; `jstat` cannot attach (`-XX:+PerfDisableSharedMem`), so a Byteman observe-only probe for the transient and an in-process class-histogram total (post-GC live heap) for retention; jmxterm absent, so a small JMX client (node JMX listens on 127.0.0.1 only: the shakedown's first attempt to reach nodes 2/3 at 127.0.0.2/.3 failed and was changed to 127.0.0.1:7299/7399); the bundled Python driver with a white-list policy, `token_metadata_enabled=False`, heartbeat off, reconnect retries; a Byteman rule type-checked with `TestScript` before use; `pgrep` patterns written as `Cassandra[D]aemon`; long steps in the background and polled; shakedowns of both tiers before run 1; the self-check written before run 1 and run end to end on the shakedowns.

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | unit shakedown (before run 1) | U2/U4 default row | The forked test JVM runs with `-XX:ActiveProcessorCount=2` (`build.xml:136,1170`); the shakedown line printed `procs=2`. The unit default is 10 × 2 = 20, not 100. | U4's default row set to cap 20, cf0 20, cf100 20, max 20, cf 1, ranges 33; the class's assertion constant changed to 20. The node default (100) and every other row unchanged. | Fixed as dated amendment D1 in the case file, 2026-10-27; new frozen hash `4c8138c9…89fb2`; both tiers of run 1 ran after it | uncommitted (on `fa4dc0c`) |

No defect in run 1 itself: both tiers ran the frozen runbook as written. Shakedowns: `unit-shake` (classes 4, then Default and 1; 23 self-check checks, 0 failed) and two cluster shakedowns (N = 28,800, `fetch_size` 500, control 50, 3 plain + 1 GC query, values 1, 48, default). The first exposed two harness errors, fixed before run 1 and not in the case file: the JMX reads of nodes 2/3 used their listen addresses (node JMX listens on 127.0.0.1 only), and a self-check test of "property absent" matched the harness path in the command line. On `cluster-shake2` the self-check ran end to end (324 checks, exit status 1): the one failed check was P4's "largest H at the default > 16 × r_max" with 3 queries of 1-MB responses (13.5 MB against 17.6 MB), a prediction-level condition on shakedown data, not an instrument fault; the prediction was not changed.

Re-freeze after run 1 (R1, a case-file amendment authorised by the user) and harness changes for the cluster re-run (added 2026-10-27 by the
cluster re-run session):

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| R1 | cluster run 1 (reading, not a runbook defect) | B3a, B3c, B3f (C7 P4 L band, numbers), B3g, B3h | The tier was Not confirmed through C8 row (b): at C = 48 and the default the replicas' outbound queues to node 1 (4 MiB + 128 MiB) dropped every 9.9-MiB response beyond about 13 per replica, so the uncapped controls (and P5) showed that bound, not the knob; and P4's L band was exceeded in 8 of 15 GC-mode reads (§4.2). | **Re-freeze, authorised by the user (Yang, the advisor) on 2026-10-27:** five dated amendments `Amendment 2026-10-27 (after run 1, authorised by the user)` — B3a (fresh clone `$W/cassandra-run68`), B3c (`fetch_size` 5000 → 1000, derived from the outbound queue limits so 24 queued responses per replica use at most half of 4 MiB + 128 MiB), B3f (C7 numbers for 1,000-row pages; P4's L band on heap footprints: responses held serialized, the consumed one also deserialized, and a `byte[]` filling [R/2, R] of the 16 MiB G1 region counted as one region), B3g (rows unchanged; reading order stated), B3h (control `fetch_size` 100). New sha256 `d0bf9c41…3779`, a new row in `_INDEX-advisor.md` §2. The whole cluster tier re-run from its beginning in a fresh clone (§7). B1, the unit tier and the relations that held unchanged. | user, 2026-10-27 | sha256 `d0bf9c41…3779` (uncommitted; no commit asked for) |
| H1 | cluster re-run | B3a / B3c amended | Run 1's `cluster-run.sh` defaults are run 1's clone and page sizes. | **No change to `cluster-run.sh`** (sha256 prefix `1be1e095`, as in run 1): it already reads `C`, `FETCH`, `CFETCH` from the environment; the re-run used `C=$W/cassandra-run68 FETCH=1000 CFETCH=100 cluster-run.sh run2`, the shakedown `C=$W/cassandra-run68 N=28800 FETCH=500 CFETCH=50 NPLAIN=3 NGC=1 VALUES="1 48 default" cluster-run.sh run2-shake`. `rng.btm`, `RngProbe.java`, `RngJmx.java`, `rng-client.py` unchanged (prefixes in `run1b-cluster/harness-sha-run2.txt` and the run's first log line). | AI, 2026-10-27 | n/a (harness) |
| H2 | cluster re-run | B3f amended (P4 (c)) | The footprint rule needs a known answer for the instrument (class-histogram total) under node 1's G1 options. | New `HumongousKnownAnswer.java` (outside Cassandra; `-XX:+UseG1GC -XX:G1HeapRegionSize=16m -Xms4G -Xmx4G`, eight arrays per length, the same `gcClassHistogram` call as `RngProbe.liveTotal()`); output `run1b-cluster/instrument/humongous-known-answer.txt`. | AI, 2026-10-27 | n/a (harness) |
| H3 | cluster re-run | self-check | `run1/selfcheck.py` checks run 1's relations. | `run1b-cluster/selfcheck.py` copies it; under `--relations run1` its output on run 1's raw files is identical to the cluster lines of `run1/selfcheck.out` (2,083 checks, 113 failed); under `--relations amended` (default) it checks the amended grid and P4 L band (region size read from node 1's gc log), drops the informational filed bands, and prints a `VERDICT` line from the amended B3g order. It exits non-zero on any failed counted check. `run1/selfcheck.py` is unchanged. | AI, 2026-10-27 | n/a (harness) |

## 4. Run 1

**Scope:** both tiers, all values of §1, at sha256 `4c8138c9…89fb2`. **Command logs:** `max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous/run1/unit/commands.log`, `run1/cluster/commands.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/rngu.txt`, verbatim `RNGU` lines; JUnit 1 test, 0 failures, 0 errors per class, `run1/unit/TEST-*.xml`). Every class printed `procs=2`, `limit=5000`.

| Class | cap (read-back) | cf0 | cf100 | max | cf | ranges | Predicted (U4/D1) | Evidence |
|---|---|---|---|---|---|---|---|---|
| `1` | 1 | 1 | 1 | 1 | 1 | 33 | 1 / 1 / 1 / 1 / 1 / 33 | `rngu.txt` |
| `4` | 4 | 4 | 4 | 4 | 1 | 33 | 4 / 4 / 4 / 4 / 1 / 33 | `rngu.txt` |
| `16` | 16 | 16 | 16 | 16 | 1 | 33 | 16 / 16 / 16 / 16 / 1 / 33 | `rngu.txt` |
| `Default` | 20 | 20 | 20 | 20 | 1 | 33 | 20 / 20 / 20 / 20 / 1 / 33 | `rngu.txt` |

**Cluster tier** (`run1/cluster/<value>/`: `trace.jsonl`, `plain.jsonl`, `gc.jsonl`, `probe-{trace,plain,gc}.txt`, `recv-*.txt`, `drops-*.txt`, `node1-cmdline.txt`; `ctl*` at 48). Ring 1 / 24 / 24 tokens (`ring.txt`); 288,000 rows loaded with 0 errors (`load-*.json`); node 1 `rng.t` SSTable count 0, nodes 2/3 3 sstables each with ≈ 142,611 / 145,094 partitions (`tablestats-node*.txt`). Every probed read had exactly 2 batches: batch 1 `cf=1`, 1 request, `live=0`, `total=50`. One dense response is 10,389,2xx B (5,000 rows, inside [10,240,000, 11,000,000]).

| C | knob read-back | `max` | batch-2 requests (trace "new concurrent requests" / "Submitted") | remaining after batch 2 | plain reads ok | dense responses delivered per read | R_total per read (mean) | ReceivedBytes per read | H: min / median / max | L (GC mode, 3 reads) | dropped large msgs (nodes 2+3) | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | 1 | 1 (1 / 1) | 48 | 20/20 | 1 of 1 | 10.39 MB | 10.39 MB | 10.4 / 10.4 / 10.4 MB | 27.8, 28.0, 28.0 MB | 0 | `1/` |
| 4 | 4 | 4 | 4 (4 / 4) | 45 | 20/20 | 4 of 4 | 41.56 MB | 41.56 MB | 10.4 / 41.6 / 41.6 MB | 78.1, 44.8, 78.3 MB | 0 | `4/` |
| 16 | 16 | 16 | 16 (16 / 16) | 33 | 20/20 | 16 of 16 | 166.23 MB | 166.23 MB | 10.4 / 62.3 / 166.2 MB | 212.7, 279.6, 111.9 MB | 0 | `16/` |
| 48 | 48 | 48 | 48 (48 / 48) | 1 | **17/20** (3 `ReadTimeout` at 10.0 s) | **26–28 of 48** (13–14 per replica) | **272.7 MB** | 272.7 MB | 10.4 / 41.6 / 270.1 MB | 78.4, 179.1, 61.6 MB | **523** | `48/` |
| default (100) | 100 | 50 | 49 (49 / 49) | 0 | **19/20** (1 `ReadTimeout`; 1 of 3 GC reads too) | **26–28 of 48** (13–15 per replica) | **271.2 MB** | 271.2 MB | 10.4 / 83.1 / 270.1 MB | 436.2, 44.9, 28.0 MB | **524** | `default/` |
| 48, `fetch_size` 500 (control) | 48 | 48 | 48 | 1 | 20/20 (500 rows) | 48 of 48 | 49.87 MB | consistent | 1.0 / 3.1 / 14.5 MB | — | (in the 48 total) | `48/ctl*`, `48/probe-ctl.txt` |

Replica logs (`node23-errwarn.txt`): `…/127.0.0.2:7000->/127.0.0.1:7000-LARGE_MESSAGES-… overloaded; dropping 9.908MiB message (queue: 128.80MiB …)`. Plain-read latency (client): median 0.12 / 0.14 / 0.24 / 0.32 / 0.38 s for C = 1 / 4 / 16 / 48 / default. Across the 15 GC-mode reads L ≈ 12.4 MB + 1.585 × H_end (least squares, largest residual 4.3 MB).

### 4.2 Conclusion and logic

1. **Validity.** Unit: knob read back as set in every class, 33 sub-ranges, limit 5000 [observed: `rngu.txt`]. Cluster: ring 1/24/24 [observed: `ring.txt`]; 288,000 rows, 0 errors [observed: `load-*.json`]; node 1 holds no sstable of `rng.t` [observed: `tablestats-node1.txt`], so the estimate is 0 and every read's batch 1 was the single empty request [observed: every `BATCH,…,1,cf=1,…,req=1,…,live=0` line]; the knob read back as C (100 for the default) in every `CLOSE` line and on node 1's command line [observed: `node1-cmdline.txt`, `probe-*.txt`]; every completed read returned exactly 5,000 rows (500 in the control) [observed: `*.jsonl`]; the rules type-checked [observed: `btm-check.txt`]. Usage was driven to the cap for C = 1, 4, 16 (each dense range holds ≈ 6,000 > 5,000 rows) and past it in the uncapped controls. The run is valid. The 5 failed reads (C8 c names "a page ≠ 5,000 rows" as invalid) are read timeouts at 10.0 s whose first dense response was among the dropped ones (`CLOSE` at ≈ 10,005–10,083 ms with 13 + 13 responses delivered) [observed]; they are an outcome of C8 (b), not a workload error [inferred: the timeouts occur only at 48/default, where drops occur].
2. **Readings.** (a) At C = 48 and the default each replica delivered only 13–15 of its 24 responses; 523 / 524 large messages were dropped by the replicas' outbound queue to node 1 ("overloaded; dropping 9.908MiB message (queue: 128.80MiB …)"): 13 responses of 9.908 MiB fill the 4 MiB queue capacity plus the 128 MiB endpoint reserve (`internode_application_send_queue_capacity` / `_reserve_endpoint_capacity`, `conf/cassandra.yaml:1386-1387`, `OutboundConnection.java:335-344`) [observed: `probe-*.txt`, `drops-*.txt`, `node23-errwarn.txt`]. (b) L exceeded P4's upper band H_end + 32 MiB in 8 of 15 GC-mode reads (C = 4: 2, 16: 3, 48: 2, default: 1), never fell below H − 16 MiB; L grows as ≈ 1.59 × H_end + 12.4 MB [observed: `probe-gc.txt`]: the node retains about 1.6 bytes of live heap per byte of held response data, more than the C5 accounting (data array + page) assumed. (c) P5 failed (ratio 0.183, not 0.093–0.107) because the C = 48 main reads were truncated by (a) while the control's 1-MB responses were all delivered [observed]. (d) The median H is timing-dependent (62 MB at 16 vs 42 MB at 48) [observed]; the informational filed bands hit for 1, 4, 16 and missed for 48 (272.7 MB vs 480 MB–1.2 GB) [observed: `selfcheck.out`].
3. **Matched row.** Unit — B2g row 1 as amended by U5/D1: "every printed value equals U4 (C for C ∈ {1, 4, 16}; the default's 20)": all 24 values equal [observed: `rngu.txt`]. Cluster — **C8 row (b)**: "a dropped large message or fewer than 1 + n2 responses for a value (P6) → another bound (the replica's outbound reserve, A4) acted; that value is not confirmed": both uncapped controls (48, default) dropped 523 / 524 messages and delivered 27–30 of 49–50 responses per read [observed]. Because row 1 needs P6 (and P2, P4, P5) for every value, the tier's row is (b): **not confirmed**. For the capped values everything except P4's L upper band held: requests per batch = C exactly (trace and probe), R_total = C × 10.39 MB, ReceivedBytes within 0.04 % of it, no drops, H ≤ C × r_max [observed: `selfcheck.out`].
4. **Excluded rows.** Unit row 2 (a value above U4) — none; U5 (a) read-back mismatch — none; (b) ranges ≠ 33 — none; (c) missing line — none; (d) value below U4 — none; row 3 (cf ≠ 1) — cf = 1 in every class [observed]. Cluster row 1 — P6, P2 and P5 fail at the controls and P4's L band fails [observed]. Row 2 (refuted at mechanism level) — no batch had more than n2 requests (probe and trace), no R_total or H above dense × r_max for a capped C (max H at 16 = 166.2 MB ≤ 176.0 MB) [observed]. Row 3 (L < H − 16 MiB at 48/default, buffering not on heap) — L ≥ H in every GC read [observed]. Row 4 (workload did not reach the burst) — batch 1 was one empty request and n2 = 48 at C = 48 [observed]. Row (a) (retained peak not past the C = 16 level) — max H 270.1 MB at 48 and at the default > 176.0 MB [observed]. Row (c) (invalid) — see part 1. Row (d) (instrument failure) — no `ERR` line, every read has a `CLOSE` line, JMX reads succeeded [observed]. Row (e) (P3 fails) — P3 held at every value [observed].
5. **Observed vs. inferred.** Inferred: that the 5 timeouts are caused by the drops (supported by their 10-s `CLOSE` and 13 + 13 delivered responses, but the probe does not name which range's response is missing); that H is the response data held by the batch's resolvers at close (from source: the `SingleRangeResponse` list is held by the iterator until `close()`, `StorageProxy.java:2067-2092`); that the extra ≈ 0.6 bytes of live heap per held data byte belongs to the held responses (the class-histogram total does not say which objects; nothing else in node 1 scales with C).
6. **Deviations and gaps.** None from the frozen runbook. Gaps: (a) the uncapped controls did not show what an unbounded burst costs on this ring, because the replicas' outbound reserves (2 × 132 MiB) cap the bytes in flight to one coordinator first; with 48 ranges of 10.4 MB, any C above about 26 is bounded by those reserves, not by the knob. (b) P4's L band was too narrow: retained live heap per held response is ≈ 1.6 × its data bytes; the cause was not traced (no per-class histogram was kept). (c) The retained peak H of a first-page read depends on arrival timing (median 62 MB at 16 vs 42 MB at 48); the cap bounds it from above (H ≤ C × r_max) but does not fix it. (d) The optional B3e step 3 (512 MB stress) was not run (C3).
7. **Core question.** Hypothesis (B1): after an empty first batch the next batch issues at most min(cap, remaining) sub-range requests, and the coordinator heap for the read rises with min(cap, dense ranges) × page × row size. Test and logic (B2b–B2e, B3b–B3e): the unit tier shows the operand equal to the cap (1, 4, 16, 20) on the target branch (parts 1, 3). The cluster tier shows, on the target branch (trace line `:165` in every traced read), batch 2 issuing exactly C requests, 10.39 MB brought into node 1's heap per request (C × 10.39 MB per read for C = 1, 4, 16, ReceivedBytes agreeing), and the retained bytes at close never above C × r_max (parts 1, 3, 4). **Usage follows the constraint and the cap bounds it for C ≤ 16; but the uncapped controls were bounded by a different limit — the replicas' 128 MiB outbound reserves dropped every response beyond about 13 per replica — so the file's "uncapped burst" comparison could not be made, and P4's live-heap cross-check band was exceeded (≈ 1.6 bytes per held byte).** The conclusions table's row (b) applies: not confirmed.

**Conclusion (one line):** unit — B2g row 1 (U5, D1) — confirmed; cluster — B3g row (b) of C8 — not confirmed (another bound acted at the uncapped controls; P4's L band missed).

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` re-parses the raw files (unit: the verbatim `RNGU` lines and the JUnit XMLs; cluster: `params.txt`, `ring.txt`, `schema.json`, `load-*.json`, `tablestats-node1.txt`, and per value the client JSON lines, every `BATCH`/`RESP`/`CLOSE` line, the JMX reads and the command line) and recomputes every frozen relation from the case file's formulas (U4/D1 recomputed from `computeConcurrencyFactor`'s arithmetic; C7's n2 = max(1, min(min(50, C), 49))). It was written before run 1 and run end to end on the shakedowns (§3). On run 1 over the committed copies with `--frozen`: **2,129 prediction checks, 113 failed** (all at the cluster tier; unit 46 checks, 0 failed); sub-predictions **3 hit, 2 missed**. The failures are the readings of part 2 (a)–(c), not instrument faults. A `--conclusion` section, written after the readings, re-reads the raw files and checks the conclusion's statements about them: every failed prediction check falls in the three named classes (controls truncated by drops; L above its upper band; P5); C = 1, 4, 16 have no other failure; at 48/default each replica delivered ≥ 13 and < 24 responses per read; every failed read is a `ReadTimeout` after ≈ 10 s; both replicas dropped large messages during each control value; the replica log carries the "overloaded; dropping" line: **58 conclusion checks, 0 failed, exit status 0** (output `run1/selfcheck.out`). The same over the full log folder gives the same totals.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: ring, load, node-1 sstables, read-backs, 2 batches per read with an empty single-request batch 1, pages — all PASS except the 5 timed-out reads, which the conclusion checks place in class "controls". |
| 2. Readings | yes, after one fix | The first draft of the conclusion said "13–14 responses per replica"; the conclusion check found one read (default q19) with 15 from node 2. Restated as "13–15 (at least the 13 that fit the queue at once, fewer than 24)"; the queue bounds bytes queued at once, not the total delivered while it drains. Re-read `default/probe-plain.txt` q19 and `node23-errwarn.txt`. |
| 3. Matched row | yes | C8 (b) conditions present at both controls (drops > 0, delivered < 1 + n2); row 1's P6/P2/P5 fail there. |
| 4. Excluded rows | yes | Row 2's conditions are negations of PASS checks (batch-2 requests, H and R_total bands at capped C); row 3: no L below H − 16 MiB (conclusion check: every L failure is above the band); rows 4, (a), (d), (e): PASS checks. |
| 5. Observed vs. inferred | yes | The verdict does not use the part-5 inferences; the timeout attribution is stated as inferred. |
| 6. Deviations and gaps | yes | `commands.log` of both tiers shows every frozen step; gaps stated. |
| 7. Core question | yes | The answer follows the audited logic: operand = cap (unit and cluster), bytes per read = C × response for C ≤ 16, disallow evidence (trace `:165`, remaining sub-ranges > 0 after a batch of C); the uncapped comparison is not available, so not confirmed. |

### 5.2 Run 2?

**No** — 2026-10-27. The conclusion rests on observed readings; every self-check part holds; the result neither refutes the case nor confirms a bypass. A repeat on this ring would meet the same outbound reserves (24 × 10.4 MB per replica > 132 MiB), so it could not move the row.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Cluster re-run ("run 1b") after the B3a, B3c, B3f, B3g, B3h amendment — 2026-10-27

Added by a stage-4 session, Claude Opus 5.5 (claude-opus-5-5), 2026-10-27, **authorised by the user (Yang, the advisor) on 2026-10-27**.
Sections 1–6 above are run 1 as filed and are not changed (only the status line at the top was updated). Run 1's excerpts under `run1/` are
untouched. The unit tier is closed and was not re-run. Excerpts of the re-run:
[`run1b-cluster/`](max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous/run1b-cluster/).

### 7.1 Frozen version and harness

| Field | Content |
|---|---|
| **Why** | Run 1's cluster tier was Not confirmed through C8 row (b) (§4.2): at C = 48 and the default each replica's outbound queue to node 1 (4 MiB + 128 MiB) dropped every 9.9-MiB response beyond about 13 (523 / 524 drops, 5 read timeouts), so P6, P2 and P5 failed at the uncapped controls; and P4's L band was exceeded in 8 of 15 GC-mode reads. The README says a wrong §9a "is a dated amendment to the case file and the affected tier starts again". The user authorised an amendment and a re-run of the whole cluster tier on 2026-10-27. |
| **Amendment** | Five dated amendments `Amendment 2026-10-27 (after run 1, authorised by the user) — B3a / B3c / B3f / B3g / B3h`, each next to the text it changes; each says plainly that it follows run 1's readings.<br>**B3c (design):** `fetch_size` 5000 → **1000** (control 500 → 100). A replica admits a response to its connection to node 1 only within 4 MiB + the 128 MiB endpoint reserve (`Config.java:250,252`; `OutboundConnection.java:325-347` `enqueue`, `:383-440` `acquireCapacity`, drop at `:344`/`:456-468`); the large-message connection (messages > 65,515 B, `OutboundConnections.java:61-70,215-228`) sends one message at a time and releases capacity only after the whole message is written (`OutboundConnection.java:966-970,991`), so at most Q = 138,412,032 B can be queued per replica. An uncapped batch sends 24 requests per replica (the C2 ring alternates the 48 dense sub-ranges). Requiring 24 × (2,200 F + 1,024) ≤ Q/2 gives F ≤ 1,310; F = 1,000 uses 52.8 MB = 38 % of Q per replica, below the 512 MiB global reserves and node 1's inbound limits (`Config.java:254,257-261`). Dense sub-ranges hold ≈ 6,000 rows, so every response still has exactly F rows; control responses (≥ 204,800 B) stay on the large-message connection.<br>**B3f (P4 L band, from source):** a delivered, unconsumed response is held **serialized**, as one array of exactly the data length (`ReadResponse.java:338`, `ByteBufferUtil.java:444-451`; frames off-heap, `BufferPoolAllocator.java:70-75`; `ReadCallback.java:187-211` and `ResponseResolver.java:60-68` only store the message); the one consumed response is in addition **deserialized** into the page (cell values copied, `AbstractType.java:587`, `ByteBufferAccessor.java:102`; kept in the `ResultSet`, ≤ F × 2.5 KiB); and a `byte[]` whose align8(16 + len) lies in [R/2, R] of node 1's G1 region (R = 16 MiB, `conf/jvm11-server.options:66`) adds a whole region to the class-histogram total (known answer outside Cassandra, H2). P4's L band becomes H* − 16 MiB ≤ L ≤ H*_end + 32 MiB on these footprints. With F = 1,000 no response is humongous, so the band equals C7's to within 16 B per response. Other C7 numbers: r_min 2,048,000 B, r_max 2,200,000 B, 16 × r_max = 35,200,000 B, control [204,800, 220,000] B; P5's band [0.0931, 0.1074] unchanged; the informational filed heap bands dropped.<br>**B3a:** fresh clone `$W/cassandra-run68`. **B3g:** no row changed; the reading order of the rows stated (d, c, 2, 4, 3, b, a, e, 1). **B3h:** control `fetch_size` 100. |
| **What was known of run 1, and would run 1 pass** | **All of run 1's readings were known** when the amendment was written (results §4.1–§5: request counts, response sizes, R_total, H, the 15 L values with L ≈ 12.4 MB + 1.585 × H_end, the drops and timeouts, P5's 0.183). While looking for the cause of the L excess the session also read run 1's raw `probe-gc.txt` CLOSE lines (each further delivered 10.39-MB response added about 16.8–17.1 MB of L) and node 1's gc log in `$W/logs/…/cluster-r1/` (`Heap region size: 16M`; the `Heap Inspection Initiated GC` full collections, so the histogram did collect). The region rule was found because of that reading; its terms come from `jvm11-server.options:66` and the known answer outside Cassandra ([`run1b-cluster/instrument/humongous-known-answer.txt`](max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous/run1b-cluster/instrument/humongous-known-answer.txt): eight 10,389,262-B arrays add 16,786,657 B each, eight 2,200,000-B arrays 2,209,478 B each; an 8,388,000-B array is not humongous, 8,388,600 B is; a 20,000,000-B two-region array adds only its own size, outside both designs' sizes). The page size 1,000 comes from the queue arithmetic, not from a run-1 count. **Would run 1 pass?** Not as a whole: on its own parameters under the amended relations its 15 L readings all lie inside the amended band, but its drops still fail P6, P2 and P5, so it stays C8 row (b), Not confirmed ([`selfcheck-known-answer-run1-relations-amended.out`](max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous/run1b-cluster/selfcheck-known-answer-run1-relations-amended.out): 2,426 checks, 105 failed); against the amended frozen grid its page size 5,000 ≠ 1,000 adds a validity failure, row (c) ([`…-amended-frozen.out`](max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous/run1b-cluster/selfcheck-known-answer-run1-relations-amended-frozen.out)). |
| **Case-file version** | sha256 **`d0bf9c415eef12169a6ce33ecb96b6d6085feaecc3b11649182db99246473779`**, a new row in `_INDEX-advisor.md` §2: "re-frozen after run 1 for cluster re-run (B3a, B3c, B3f, B3g, B3h), authorised by the user". The earlier rows (`fa5a9a28…`, `a2dc5f0d…`, `4c8138c9…`) are kept. Hashed at 20:13:19 EDT, after the fresh clone was built (20:08:02–20:08:57) and the instrument known answer (20:08), and before the shakedown (20:13:46) or any re-run reading (20:18:42); recorded again at 20:13:38 in [`run1b-cluster/harness-sha-run2.txt`](max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous/run1b-cluster/harness-sha-run2.txt). Section D was filled afterwards, so the file's current hash differs by that section only. Base commit `942f128`; nothing committed. |
| **Harness** | Run 1's harness, unchanged (H1), plus `HumongousKnownAnswer.java` (H2) and the self-check copy (H3) (§3).<br>sha256 prefixes: `cluster-run.sh` `1be1e095`, `rng.btm` `094bb6b8`, `RngProbe.java` `54304b83`, `RngJmx.java` `a88694f2`, `rng-client.py` `088cc483` (also in the run's first log line), `HumongousKnownAnswer.java` `6ddf7893`, `selfcheck.py` `48a704d4`.<br>Commands: `C=$W/cassandra-run68 N=28800 FETCH=500 CFETCH=50 NPLAIN=3 NGC=1 VALUES="1 48 default" cluster-run.sh run2-shake`, then `C=$W/cassandra-run68 FETCH=1000 CFETCH=100 cluster-run.sh run2`.<br>Instrument checks: `TestScript: no errors` (each run's `btm-check.txt`); the known answer (above). The self-check ran end to end on the shakedown first: **364 checks, 0 failed, exit status 0**, verdict line row 1 ([`run1b-cluster/shakedown/selfcheck.out`](max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous/run1b-cluster/shakedown/selfcheck.out)); it was not changed after the shakedown or the re-run. |

### 7.2 Environment

Same host as run 1 (§2): `yangwang-mbp`, macOS 27.0.1 / Darwin 27.0.0 arm64, OpenJDK 11.0.32.1, Ant 1.10.18; free disk 111 GiB; `127.0.0.1`–`.3`
on `lo0`; ports 7000, 7199, 7299, 7399, 9042, 9091 free before each run. Re-run 2026-10-27: clone and build 20:08:02–20:08:57 EDT, known answer
20:08, shakedown 20:13:46–20:18:12, re-run 20:18:42–20:29:47. Fresh clone from `~/cassandra-src` at `b5f2a54210d541339c2e7c17a794195cac0e67c2`
(tag `cassandra-5.0.9`), no local change: `$W/cassandra-run68` (`ant -Dlocal.repository=$W/m2 build-test`, `BUILD SUCCESSFUL`, 54 s;
[`run1b-cluster/clone-build-run68.txt`](max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous/run1b-cluster/clone-build-run68.txt));
`git status` clean after both runs (last log line). Node settings as run 1 (node 1 4 GiB, G1, `Heap region size: 16M` in every node-1 lifetime,
`gc-region.txt`; nodes 2/3 2 GiB). Node files `$W/node-rng1..3`, removed at the end (sizes in `node-du.txt`: 13 / 312 / 331 MiB).
Full logs: `~/Library/Caches/stage4/logs/max_concurrent_range_requests-computeConcurrencyFactor-liveReturned/`: `rerun-prep/` (`clone-run68.log`,
`build-test-run68.log`, `humongous-known-answer.txt`, `harness-sha-run2.txt`, `shake-driver.out`, `run2-driver.out`), `cluster-run2-shake/`,
`selfcheck-run2-shake.out`, `cluster-run2/` (as run 1's `cluster-r1/`), `selfcheck-run2.out`, `selfcheck-run2-under-run1-relations.out`.
Excerpts in `run1b-cluster/`: `cluster/` and `shakedown/cluster/` (run 1's kinds of files, without `probe-all.txt`, the node system logs and the
gc logs, plus `gc-region.txt`), `instrument/`, `selfcheck.py`, `selfcheck.out`, `selfcheck-rerun-under-run1-relations.out`,
`selfcheck-known-answer-run1-relations-{run1,amended,amended-frozen}.out`, `shakedown/selfcheck.out`, `driver.out` (empty: the script writes to
its logs), `harness-sha-run2.txt`, `clone-build-run68.txt`.

### 7.3 Readings

From `run1b-cluster/cluster/<value>/` (`trace.jsonl`, `plain.jsonl`, `gc.jsonl`, `probe-*.txt`, `recv-*.txt`, `drops-*.txt`, `node1-cmdline.txt`;
`ctl*` at 48), recomputed by `selfcheck.py`. Ring 1 / 24 / 24 tokens (`ring.txt`); 288,000 rows loaded with 0 errors (`load-*.json`); node 1
`rng.t` SSTable count 0, nodes 2/3 3 sstables each with ≈ 142,611 / 145,094 partitions (`tablestats-node*.txt`). Every probed read had exactly
2 batches: batch 1 `cf=1`, 1 request, `live=0`, `total=50`. Every dense response is 2,077,846–2,077,897 B (1,000 rows, inside [2,048,000,
2,200,000]); control responses 207,782–207,799 B. Every read (120 main, 20 control) completed with exactly 1,000 (100) rows.

| C | knob read-back | `max` | batch-2 requests (trace "new concurrent requests" / "Submitted") | remaining after batch 2 | plain reads ok | dense responses delivered per read | R_total per read (mean) | ReceivedBytes per read | H: min / median / max | L (GC mode, 3 reads) with H | dropped msgs (nodes 2+3) | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | 1 | 1 (1 / 1) | 48 | 20/20 | 1 of 1 | 2.078 MB | 2.081 MB | 2.08 / 2.08 / 2.08 MB | 4.10, 4.32, 4.32 MB (H 2.08) | 0 | `1/` |
| 4 | 4 | 4 | 4 (4 / 4) | 45 | 20/20 | 4 of 4 | 8.312 MB | 8.315 MB | 2.08 / 2.08 / 8.31 MB | 8.27, 6.42, 10.55 MB (H 4.16, 4.16, 8.31) | 0 | `4/` |
| 16 | 16 | 16 | 16 (16 / 16) | 33 | 20/20 | 16 of 16 | 33.25 MB | 33.25 MB | 4.16 / 12.47 / 33.25 MB | 14.53, 16.81, 18.90 MB (H 12.47, 14.55, 16.62) | 0 | `16/` |
| 48 | 48 | 48 | 48 (48 / 48) | 1 | **20/20** | **48 of 48** | **99.74 MB** | 99.74 MB | 2.08 / 12.47 / **51.95 MB** | 22.98, 10.61, 6.44 MB (H 18.70, 8.31, 2.08) | **0** | `48/` |
| default (100) | 100 | 50 | 49 (49 / 49) | 0 | **20/20** | **48 of 48** (+ 2 local) | **99.74 MB** | 99.74 MB | 2.08 / 8.31 / **41.56 MB** | 10.50, 18.93, 4.37 MB (H 4.16, 16.62, 2.08) | **0** | `default/` |
| 48, `fetch_size` 100 (control) | 48 | 48 | 48 | 1 | 20/20 (100 rows) | 48 of 48 | 9.974 MB | 9.978 MB | 0.21 / 1.25 / 2.49 MB | — | (in the 48 total) | `48/ctl*`, `48/probe-ctl.txt` |

Control ratio R_total(100)/R_total(1000) at C = 48: **0.1000** (P5 band [0.0931, 0.1074]). Largest H of the 20 plain reads: 51,946,923 B at
C = 48 and 41,557,700 B at the default, both > 16 × r_max = 35,200,000 B; at C = 16 the largest H is 33,246,106 B (all 16 responses), ≤ 16 ×
r_max. Plain-read latency (client, median): 0.029 / 0.031 / 0.049 / 0.062 / 0.054 s for C = 1 / 4 / 16 / 48 / default. `LargeMessageDroppedTasks`
and `SmallMessageDroppedTasks` on nodes 2/3 unchanged across every value; no "overloaded; dropping" line (`node23-errwarn.txt`: 5 start-up
warnings only). In GC mode L − H lies between 2.0 and 6.4 MB (the 1,000-row page, plus responses that arrived while the histogram ran:
H_end − H up to 6.2 MB).

### 7.4 Cluster re-run — conclusion and logic

1. **Validity.** The re-run used the re-frozen version (`d0bf9c41…`, hashed at 20:13:19, before the shakedown and the re-run) [observed:
   `_INDEX-advisor.md` §2; `harness-sha-run2.txt`; `cluster/commands.log` first line 20:18:42]. Fresh clone at the tag, clean afterwards
   [observed: `clone-build-run68.txt`, last log line]. Ring 1/24/24, 288,000 rows with 0 errors, node 1 holds no sstable of `rng.t`, every
   read's batch 1 the single empty request, the knob read back as C (100 for the default) in every `CLOSE` line and on node 1's command line,
   every page exactly 1,000 (100) rows, the rules type-checked, the region size 16 MiB in every node-1 lifetime [observed: `ring.txt`,
   `load-*.json`, `tablestats-node1.txt`, `probe-*.txt`, `node1-cmdline.txt`, `*.jsonl`, `btm-check.txt`, `gc-region.txt`]. Usage was driven to
   the cap for C = 1, 4, 16 (each dense sub-range ≈ 6,000 > 1,000 rows) and past it at 48 and the default. The run is valid.
2. **Readings.** Batch 2 issued exactly n2 = 1 / 4 / 16 / 48 / 49 requests on the target branch (trace line `:165` and the probe), leaving 48 /
   45 / 33 / 1 / 0 sub-ranges; R_total per read = dense × 2.078 MB (2.08 / 8.31 / 33.25 / 99.74 / 99.74 MB), ReceivedBytes within 0.2 % +
   64 KiB of the probe's remote bytes; no drop and every response delivered at every value, the uncapped controls included [observed]. H ≤ C ×
   r_max for each capped C; the largest H at 48 / default exceeds what any C = 16 read can hold [observed]. L in every GC-mode read inside the
   amended band, and in fact within H + 6.4 MB [observed]. P5 0.1000 [observed].
3. **Matched row.** **B3g row 1** (as read by C8 and the amended B3f/B3g): "requests, received bytes and heap peak scale with min(C, 48) —
   claim confirmed": P1, P2, P3, P4 (amended) and P6 hold for every value and P5 for the control [observed: `selfcheck.out`, 2,427 checks, 0
   failed; `VERDICT B3g row 1`].
4. **Excluded rows** (in the amended B3g order). (d) instrument failure — no `ERR` line, a `CLOSE` line for every read, every JMX read
   succeeded, every remote array a heap array of exactly the payload length [observed]. (c) invalid — see part 1. Row 2 (refuted at mechanism
   level) — no batch above n2, no R_total or H above dense × r_max + 8 KiB at a capped C [observed]. Row 4 (burst not reached) — batch 1 one
   empty request in every read, n2 = 48 at C = 48 [observed]. Row 3 (L < H* − 16 MiB at 48/default) — none [observed]. (b) another bound acted
   — no dropped message, 1 + n2 responses in every read [observed]. (a) retention not past the C = 16 level — 51.9 / 41.6 MB > 35.2 MB
   [observed]. (e) P3 fails — P3 holds at every value and for the control [observed].
5. **Observed vs. inferred.** Inferred: that H is the response data held by the batch's resolvers at close (from source, as in run 1); that the
   2.0–6.4 MB of L above H is the page and late responses (the class-histogram total does not name objects; the size matches F × ≈ 2.1 KB
   plus H_end − H). The verdict does not rest on either: row 1 needs only the observed relations.
6. **Deviations and gaps.** None from the re-frozen runbook. Gaps: (a) with 2-MB responses the L band's fixed slack (−16 MiB / +32 MiB) is
   wide relative to H for C ≤ 16, so for those values the live-heap cross-check is weak (the readings themselves sit within H + 6.4 MB);
   (b) the retained H of a first-page read remains timing-dependent (median 12.5 MB at 16 and at 48), so the cap bounds it from above rather
   than fixing it, as run 1 found; (c) the uncapped burst on this ring is 99.7 MB per read, far below node 1's 4 GiB heap, so the re-run shows
   the cap governing the bytes a read brings in, not a heap failure without it; the optional B3e stress step stays not run (C3).
7. **Core question.** Hypothesis (B1): after an empty first batch the next batch issues at most min(cap, remaining) sub-range requests, and
   the coordinator heap for the read rises with min(cap, dense ranges) × page × row size. On the target branch batch 2 issued exactly C
   requests (49 at the default), each bringing a 2.078-MB response into node 1's heap, so the bytes per read follow min(C, 48) × page × row
   size (2.08 → 8.31 → 33.25 → 99.74 MB), with the uncapped controls now showing the full burst (all 48 responses, no drops) and the
   1,000 → 100 page control scaling the bytes by 0.1000. **The property caps the coordinator's range-read burst, and usage follows it.**

**Conclusion (one line):** cluster re-run — B3g row 1 (C8, amended B3f/B3g) — confirmed, caps.

### 7.5 Self-check of the cluster re-run — AI

`run1b-cluster/selfcheck.py` (H3) re-reads the raw `params.txt`, `ring.txt`, `schema.json`, `load-*.json`, `tablestats-node1.txt`, the gc
log's region line and, per value, the client JSON lines, every `BATCH`/`RESP`/`CLOSE` line, the JMX reads and node 1's command line, and
recomputes every relation from the case file's formulas. It was written after the amendment and before any re-run reading, and was not
changed after the shakedown or the re-run (sha256 `48a704d4…` in `harness-sha-run2.txt`).
- **Pass 0 (shakedown, run end to end first):** 364 checks, 0 failed, exit status 0 (`run1b-cluster/shakedown/selfcheck.out`).
- **Pass 1 (re-run raw files, amended relations, frozen grid):** **2,427 checks, 0 failed**, exit status 0; `VERDICT B3g row 1 -> Confirmed -
  caps` ([`run1b-cluster/selfcheck.out`](max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous/run1b-cluster/selfcheck.out)).
  The same over the excerpt folder `run1b-cluster/cluster/` gives the same totals. One informational sub-check missed: the median H at
  C = 48 (12,467,386 B) is 5 B below that at C = 16 (12,467,391 B), so "median H non-decreasing" fails by 5 B; it is not counted.
- **Pass 2 (known answer, run 1's raw files, run-1 relations):** 2,083 checks, 113 failed — identical, line by line, to the cluster lines of
  `run1/selfcheck.out` (`selfcheck-known-answer-run1-relations-run1.out`): the copy reproduces run 1's result.
- **Pass 3 (run 1's raw files, amended relations):** on run 1's own parameters 2,426 checks, 105 failed, verdict C8 (b) (the drops); all 15
  amended L checks pass; with the amended frozen grid 2,427 checks, 106 failed, verdict (c) (`…-amended.out`, `…-amended-frozen.out`): the
  script tells run 1 apart from the re-run.
- **Pass 4 (information, re-run raw files, run-1 relations):** 2,082 checks, 0 failed (`selfcheck-rerun-under-run1-relations.out`): with
  non-humongous responses run 1's own L band would also have held.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out` validity and instrument checks all PASS; `gc-region.txt` six lines `Heap region size: 16M` (one per node-1 lifetime: the load and the five values); `node1-cmdline.txt` per value. |
| 2. Readings | yes | Re-read `48/probe-plain.txt` and `default/probe-plain.txt` (48 remote `RESP` lines per read, none after a drop), `48/drops-*.txt` and `default/drops-*.txt` (all four counters equal before/after), `48/ctl.jsonl` (20 × 100 rows); the table's means and maxima recomputed by a separate short script from the raw files agree with `SUMMARY-CLUSTER`. |
| 3. Matched row | yes | Row 1's conditions are the PASS lines tagged P1–P6 (counts in `VERDICT-TAGS`). |
| 4. Excluded rows | yes | Each excluded row's condition is the negation of PASS checks (tags `instr`, `valid`, `row2`, `row4`, `P4L`, `P6`, `P4max`, `P3`). |
| 5. Observed vs. inferred | yes | The verdict uses no inferred statement. |
| 6. Deviations and gaps | yes | `cluster/commands.log` shows every C6 step for every value; gaps stated. |
| 7. Core question | yes | Requests per batch = C (disallow evidence: trace `:165` and sub-ranges left after a batch of C), bytes per read ∝ min(C, 48), controls uncapped without another bound. |

**Run 2?** No — the conclusion rests on observed readings, every part holds, and the result neither refutes the case nor confirms a bypass.

### 7.6 Verdict of the cluster re-run

**Cluster tier (re-run at `d0bf9c41…`): Confirmed — B3g row 1 (C8; amended B3f, B3g). Effect: caps.** Run 1's cluster verdict (Not confirmed,
C8 row (b)) stays in §4 and in §8 as the result at `4c8138c9…`; the re-run's verdict is the tier's current verdict.

**End of the re-run:** no `CassandraDaemon` process (`pgrep -f 'Cassandra[D]aemon'` empty; last log lines "no Cassandra daemon left"); ports
free; `$W/node-rng1..3` removed; `$W/cassandra-run68` `git status` clean (0 lines); nothing copied into the clone.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested (B1):** For a range read whose first batch returns no rows, the next batch issues at most `min(cap, remaining ranges)` sub-range requests, and the coordinator's peak heap for that read rises in proportion to min(cap, dense ranges) × page-limit × row size; lowering the cap lowers the peak.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1, U5/D1) — `computeConcurrencyFactor(…, liveReturned = 0)` returns the cap (1 / 4 / 16 / 20 default in the test JVM); iterator `maxConcurrencyFactor` = cap, initial factor 1 on an empty table | caps (operand) | run 1 + self-check | 2026-10-27 |
| Cluster | Not confirmed (C8 row (b)) — on the target branch batch 2 issues exactly C requests (1 / 4 / 16 / 48; 49 at the default 100) and brings C × 10.39 MB into node 1's heap (10.4 / 41.6 / 166.2 MB, ReceivedBytes agreeing), held bytes ≤ C × 11 MB; at 48 and the default the replicas' 128 MiB outbound reserves dropped 20–22 of 48 responses per read (523 / 524 drops, 3 + 2 read timeouts), so the uncapped controls show the other bound, not the knob; P4's live-heap band exceeded (≈ 1.6 B live per held data byte) | caps (requests and response bytes per read for C ≤ 16; above ≈ 26 sub-ranges on this ring the replicas' outbound reserves bound first) | run 1 + self-check | 2026-10-27 |
| Cluster (re-run at `d0bf9c41…`, after the user-authorised B3a, B3c, B3f, B3g, B3h amendment) | **Confirmed** — B3g row 1 (C8; amended B3f, B3g): with 1,000-row pages (so 24 queued responses per replica use 38 % of the 4 MiB + 128 MiB outbound queue) batch 2 issues exactly C requests on the target branch (1 / 4 / 16 / 48; 49 at the default 100) and brings dense × 2.078 MB into node 1's heap (2.08 / 8.31 / 33.25 / 99.74 / 99.74 MB per read, ReceivedBytes agreeing); the uncapped controls deliver all 48 responses with no drop and hold up to 51.9 / 41.6 MB at close, above anything a C = 16 read can hold (35.2 MB); held bytes ≤ C × r_max for capped C; post-GC live delta L within the amended band (and within H + 6.4 MB) in all 15 GC-mode reads; page control 1,000 → 100 scales the bytes by 0.1000 | caps (requests and response bytes per range read follow min(C, dense sub-ranges); timing decides how many of them are still held when the page completes) | cluster re-run (§7) + self-check | 2026-10-27 |

**Feedback filed:** the case file's section D updated (uncommitted, after sha256 `4c8138c9…89fb2`); B2–B4 carry the 15 dated amendments (U1–U5, C1–C9, D1); `_INDEX-advisor.md` §2 has two new rows (frozen and D1 hashes) and §1's Stage 4 column for this file is filled. Recommendations 8 and 9 (§1.1) are left for stage 3, with: the cluster design's uncapped control needs per-replica response bytes × requests per replica below 132 MiB (smaller pages or more replicas) to show an unbounded burst; and P4-style live-heap bands should allow ≈ 1.6 × the held data bytes.

**Feedback filed for the cluster re-run (2026-10-27):** the five amendments `Amendment 2026-10-27 (after run 1, authorised by the user)` in the case file (B3a, B3c, B3f, B3g, B3h); a new `_INDEX-advisor.md` §2 row (`d0bf9c41…`); the case file's section D (new entry); the §1 Stage 4 column (run-1 text kept, re-run verdict appended). The coverage section is not touched. No refutation, so no other case section is amended. Run-1 findings kept as observations: the replicas' outbound queue reserve drops at 10-MB responses (§4), and the double increment of `liveReturned` (`RangeCommandIterator.java:115` and `:153`, §1.1 recommendation 9). Recommendations for stage 3: (1) an uncapped control must keep requests per replica × response size under the replica's outbound queue (4 MiB + 128 MiB by default) — here 1,000-row pages; (2) a live-heap band for byte arrays must use the JVM's footprint: with Cassandra's `-XX:G1HeapRegionSize=16m` (`conf/jvm11-server.options:66`) a single array of 8–16 MiB occupies a whole 16 MiB region, which the class histogram counts (run 1's ≈ 1.6 B of live heap per held byte).
