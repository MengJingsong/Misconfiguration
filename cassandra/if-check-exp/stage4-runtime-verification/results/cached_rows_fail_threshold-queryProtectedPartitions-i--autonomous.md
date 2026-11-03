# cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous — stage-4 results  <!-- file: results/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous.md -->

> **Case:** [`cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous`](../../stage3-ai-deep-read/cases/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous.md)
>
> **Status:** verdict filed (2026-10-27)
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous/`](../harness/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous/).
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e;
> the case file's feedback section is its section D. Session: Claude Opus 5.5 (claude-opus-5-5), advisor-run, on the advisor's Mac.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Branch `advisor-run`, uncommitted on 2026-10-27 (as filed in `561e1ac`'s tree with sha256 `46da06a6…0834`). Frozen after the audit's 13 amendments (U1–U5, C1–C8): sha256 `0b84c3769a2c6c399369b832003b20a67b891d6bc4e3739219a00b9614b52462`, recorded in `_INDEX-advisor.md` §2 before any harness run. The unit shakedown then found runbook defect D1 (§3); its dated fix leaves every prediction and row unchanged: sha256 **`3fe55d66c3f192e350d4322ada935b54dbf03e866b9d784fb9d8fb3d78027a9a`** (second §2 row). **Both tiers of run 1 ran at this version.** Section D is filled after this hash. |
| **Harness** | `harness/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous/`: `RfpCapProbeTest.java` (in-JVM dtest, copied into the clone only for the run), `unit-run.sh`; `stage4/rfp/RfpProbe.java` (observe-only helper) and `rfp.btm` (three Byteman rules), `RfpJmx.java` (JMX setter and histogram reader), `rfp-client.py` (bundled-driver client), `cluster-run.sh`; self-check `results/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous/run1/selfcheck.py`. Not committed (the user has not asked for a commit). Reused with attribution: `unit-run.sh` and `cluster-run.sh` adapt the structure and node start/stop functions of `harness/paxos_cache_size-close-active--autonomous/`; `rfp-client.py` adapts that folder's driver set-up; `RfpJmx.java` adapts `harness/repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous/Jmx.java`; the probe pattern (Byteman rule calling a `sys:` helper that uses `ObjectSizes.measureDeep`) follows `harness/paxos_cache_size-close-active--autonomous/pcca.btm`. Keyspaces, tables, workloads, rules and every bound are this case's. No value or derivation was taken from another case file or results file. |
| **Tiers and values** | Unit: in-JVM dtest, 2 instances, RF 2, N = 20,000 rows in one partition, T ∈ {1000, 10000, 32000 (default), 100000} plus the agreeing-replicas control at T = 100000. Cluster: 2 nodes (127.0.0.1, 127.0.0.2), RF 2, N = 100,000 rows (pad 512 B) in one partition diverged on node 1, T ∈ {1000, 10000, 32000 (default), 1000000} each twice, plus the informational CL ONE run at T = 1000000. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: rows RFP holds on the coordinator heap (`PartitionBuilder.contents`), a count with a derivable byte size; B1 also claims the heap attributable to them scales with min(T, demand). |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly | B2b {1000, 10000, 100000}, B3b {1000, 10000, 1000000}: the default 32000 (`ReplicaFilteringProtectionOptions.java:23`) in neither. Added (U2, C2). |
| A. Core question | real resource measured, not only the counter | Partly | Unit: counter only, said so (B2d). Cluster: B3d (3) samples a class histogram every 2 s and (4) uses `jstat`; a failing query is over in well under 2 s (the transient is invisible) and `jstat` cannot attach here (`-XX:+PerfDisableSharedMem`). Replaced by an observe-only Byteman probe that measures the rows RFP holds, and the raw responses, at the peak (C4). |
| A. Core question | usage driven to the limit and past it | Partly | Unit: demand 2N = 40,000 > 1000, 10000, 32000; < 100000 (control): Met. Cluster as written: N = 100,000 × 4 KiB makes node 2's response ≈ 410 MB, above the 128 MiB `internode_max_message_size` (`DatabaseDescriptor.java:990-997`, `OutboundConnection.java:331-332`): the query cannot reach RFP. Pad 512 B (C3). |
| B. Logic | each step says what it establishes | Met | B2h/B3h tie the T = 100000 / 1000000 runs to "the workload demands 2N", the fresh table per T to histogram carry-over. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | B2f "max = 1001" cannot be read: the histogram's `getMax()` returns a bucket bound (1109) (`DecayingEstimatedHistogramReservoir.java:537-549`). Restated in bucket units (U4). B3f "≤ ~1000", "~20 MB", "~400 MB" were approximate and sized for 4-KiB rows: replaced by exact counts and a proportional byte relation (C6). |
| B. Logic | every plausible outcome has a conclusions row | Partly | Missing: wrong exception, no histogram sample, control mismatch, read-back mismatch, instrument failure, repeats disagree. Added (U5, C7). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The disallow branch is the `OverloadedException` with the threshold in its message and RFP's log line; the ceiling is the histogram bucket (unit) and the probe's exact count and bytes (cluster). |
| B. Logic | alternative explanations and their controls | Partly | "Run each T twice; same data" fails as written: the default blocking read repair after a successful query removes the divergence. `read_repair = 'NONE'` (C3 (ii)). The CL ONE control's premise ("no RFP") is false in source: a range read resolves through `DataResolver` and takes the RFP path at any CL (`DataResolver.java:122-144`, `RangeCommandIterator.java:198-203`); kept as an informational run with source-derived outcomes (C8). |
| C. Specific | a human can follow it from the intro and §9a | Met | A3 states the count, the throw at T+1 and the release per partition. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | `/local` paths, jmxterm (absent), no retry policy (an Overloaded error would be retried on the other host), no start-up option for a ring on this Mac. Amended (U1, C1–C3, C5). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Order of runs, read-backs, the instrument check of the histogram reading, the read of `RecentValues` were open. Amended (U3, C4, C5). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | `/local`, `jmxterm`, `jstat` replaced (U1, C1, C2, C4). |
| D. Runnable | workload arithmetic reaches the limit | Partly | Unit Met (40,000 small rows, `-Xmx8G`). Cluster not as written (410 MB response > 128 MiB); after C3, ≈ 54 MB per response, ≈ 80 MB of cached rows at the control, 2 GiB heap per node; disk ≈ 0.1 GB per node. |
| D. Runnable | load-bearing citations spot-checked | Met | Against the clone at `b5f2a54210`: `ReplicaFilteringProtection.java:143` (`consumeEntirePartitions`), `:222` (`addRow` per version; filed as `:215-219`), `:289` (histogram update; filed `:282-286`), `:319-331` (increment, throw at T+1), `:430` (target), `:477-492` (`addRow`; null counted, not stored), `:564` (release); `DataResolver.java:122, 252-264`; `StorageService.java:6749-6752`; `ReplicaFilteringProtectionOptions.java:23,27`; `TableMetrics.java:837`. Line drift of 3–7 lines in a few filed citations; none load-bearing. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | U1: this host's clone and paths; parameters through `-Dtest.jvm.args` only for a shakedown | applied, amendment 2026-10-27 | `/local` absent |
| 2 | U2/C2: the default 32000 added to both tiers; thresholds read back | applied | group A |
| 3 | U3: exact unit procedure, run order, control, histogram instrument check | applied | group C |
| 4 | U4/U5: predictions and rows in histogram-bucket units; rows added | applied | `getMax()` returns a bucket bound; group B |
| 5 | C1: Mac host, two nodes from one clone, `auto_bootstrap: false`, read/range timeouts 60 s | applied | `/local` absent; bootstrap streaming fails here; second-phase deadline counted from query start |
| 6 | C3: pad 512 B; `read_repair = 'NONE'`; exact client incl. `FallthroughRetryPolicy` | applied | 128 MiB internode limit; read repair removes divergence; retry on another host |
| 7 | C4: Byteman probe of RFP-held rows and bytes and of raw responses; `RecentValues`; jstat dropped; 2-s sampler informational | applied | transient invisible to a 2-s sampler; jstat cannot attach |
| 8 | C5–C7: exact sequence; exact predictions; rows | applied | group B, C |
| 9 | C8: CL ONE control's premise corrected; run as informational | applied | `DataResolver` takes the RFP path at any CL for range reads |
| 10 | Stage 3: neither tier exercises the entry-pointer branch `:430` (`if (i > 0) mergeListener.populate()`): both use range reads, so `consumeEntirePartitions` is true (`:143`) and the `:387-397` branch runs instead. The constraint check (`incrementCachedRows`, reached from `onMergedRows` on both branches) is what is tested. A single-partition `LIMIT` arm (`… WHERE k = 0 AND v = 'old' LIMIT L ALLOW FILTERING`) would drive the target branch; its counting with repeated `populate()` of the same builders and SRP refills is not derivable without more source work | left for stage 3 | scope of the filed design; adding an arm needs predictions the audit cannot derive safely |
| 11 | Stage 3: state the claim as "rows held" rather than "rows cached": null versions are counted but not stored (`:479-485`), so the count is ≥ 2 × the rows actually held when one replica is silent | left for stage 3 | wording; C6 already uses both numbers |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit 03:16–03:17, cluster 03:17–03:22 local time, EDT; shakedowns 03:07–03:16) |
| Node | `yangwang-mbp`, the advisor's MacBook Pro (Apple M1 Pro, arm64), single host; 10 cores, 32 GiB (`hw.memsize` 34359738368) |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64) |
| Ant | Apache Ant 1.10.18 |
| Local `cassandra-src` clone commit | `$W/cassandra-run50` (`W=~/Library/Caches/stage4`), fresh `git clone --branch cassandra-5.0.9 ~/cassandra-src`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`; `ant -Dlocal.repository=$W/m2 build-test` BUILD SUCCESSFUL in 52 s; `git status` clean after both tiers |
| Case-file commit / harness commit | case file uncommitted at sha256 `3fe55d66…7a9a` (on `561e1ac`); harness uncommitted |
| Storage for node data | internal SSD, APFS `/dev/disk3s1`, 123 GiB free; unit data under the clone's `build/test`; node files `$W/node-rfp1`, `$W/node-rfp2` (removed at the end; sizes in `run1/cluster/node-du.txt`) |
| Loopback / ports | `127.0.0.1`–`.3` on `lo0` (`.1` and `.2` used); 7000, 7199, 7299, 9042, 9091 free before each run |
| Full logs (outside the repo) | `$W/logs/cached_rows_fail_threshold-queryProtectedPartitions-i/` (`clone.log`, `build-test.log`, `unit-shake/`, `unit-r1/`, `cluster-shake/`, `cluster-r1/`) |

Machine facts relied on: workspace `$W` and `env.sh`; commands touching `$W`/Java run unsandboxed; `-Dlocal.repository=$W/m2` on every ant call; parameters reach the forked test JVM only via `-Dtest.jvm.args` (used for the shakedown only); no `setsid` (nodes as tracked background processes, `bin/cassandra -f > log < /dev/null`); loopback aliases `.2`/`.3` checked with `ifconfig lo0`; `auto_bootstrap: false` because zero-copy bootstrap streaming fails here; `CASSANDRA_CONF`/`CASSANDRA_LOG_DIR` outside the clone so it stays clean; `JVM_EXTRA_OPTS` scoped to node 1's command; jmxterm absent, so a small JMX client; `jstat` cannot attach (the node runs with `-XX:+PerfDisableSharedMem`), so a Byteman observe-only probe for the transient and `jcmd GC.class_histogram` (columns matched exactly) only as information; the bundled Python driver with a white-list policy, `token_metadata_enabled=False`, heartbeat off, reconnect retries; a Byteman rule type-checked with `TestScript` before use; `pgrep` patterns written as `Cassandra[D]aemon`; long steps in the background and polled; node `system.log` timestamps are UTC; shakedowns of both tiers before run 1; the self-check written before run 1 and run end to end on both shakedowns (exit status 0).

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | unit shakedown (before run 1) | U3 (B2d (3)) log-line count; U1 where the `RFPU` lines are read | The plain-text count read 2 lines per failure, not 1: in the in-JVM dtest the isolated executor also reports the uncaught exception (`JVMStabilityInspector`), and that report's message line contains the same text. The test's stdout goes to the ant console (`showoutput="true"`, `build.xml:1827`), not to a `TEST-<class>.log`. | Count RFP's own logger line (`ReplicaFilteringProtection\.java:[0-9]+ - Replica filtering protection has cached over`, the `logger.error` of `:329`); keep the plain count as information; read `RFPU` lines from the copied ant log. Predictions and rows unchanged (one RFP log line per failure). Same pattern used for the cluster `system.log` count. | Fixed as dated amendment D1 in the case file, 2026-10-27; new frozen hash `3fe55d66…7a9a`; both tiers of run 1 ran after it | uncommitted (on `561e1ac`) |

No defect in run 1 itself: both tiers ran the frozen runbook as written. Shakedowns: `unit-shake` (N = 2,000, T ∈ {100, 1000, 10000}, control at 10000; self-check 44 checks, 0 failed, exit 0 after D1) and `cluster-shake` (N = 4,000, T ∈ {100, 1000, 32000, 100000}, 2 repeats, ONE at 100000; self-check 118 checks, 0 failed, exit 0). The cluster shakedown exposed two self-check checks written for the frozen grid only (a strict increase of bytes with T, and a fixed 1/100 ratio); they were generalised to the C6 relation (bytes ordered with min(T/2, N), ratio to the control = min(T/2, N)/N) before run 1. That is a fix to the self-check, not to the case file.

## 4. Run 1

**Scope:** both tiers, all values of §1, at sha256 `3fe55d66…7a9a`. **Command logs:** `cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous/run1/unit/commands.log`, `run1/cluster/commands.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/rfpu-raw.txt`, verbatim `RFPU` lines of the ant log; JUnit 1 test, 0 failures, 0 errors, `run1/unit/TEST-…RfpCapProbeTest.xml`; RFP's log lines in `run1/unit/node-log-excerpt.txt`). N = 20,000, demand 2N = 40,000; warn threshold read back as 2147483647 in every run.

| Table | T (read back) | Node-1 update | Outcome | Rows | Exception | Message has "cached over T rows" and `cached_replica_rows_fail_threshold` | RFP log lines (plain-text count) | Histogram samples / max | Predicted max | RFP requests | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `t_1000` | 1000 | yes | FAIL | — | `OverloadedException` | yes / yes | 1 (2) | 1 / **1109** | 1109 | 0 | `rfpu-raw.txt` |
| `t_10000` | 10000 | yes | FAIL | — | `OverloadedException` | yes / yes | 1 (2) | 1 / **11864** | 11864 | 0 | `rfpu-raw.txt` |
| `t_32000` (default) | 32000 | yes | FAIL | — | `OverloadedException` | yes / yes | 1 (2) | 1 / **35425** | 35425 | 0 | `rfpu-raw.txt` |
| `t_100000` | 100000 | yes | OK | 0 | — | — | 0 (0) | 1 / **42510** | 42510 | 1 | `rfpu-raw.txt` |
| `t_ctl` (control) | 100000 | no | OK | 20,000 | — | — | 0 (0) | 1 / **42510** | 42510 | 0 | `rfpu-raw.txt` |

Instrument check (U3): a fresh `DecayingEstimatedHistogramReservoir(true)` read `getMax()` = 1109, 11864, 35425, 42510, 219342 for 1001, 10001, 32001, 40000, 200000 (`RFPU-KA` lines), as computed from source.

**Cluster tier** (`run1/cluster/<tag>/`: `threshold.txt`, `query.json`, `probe.txt`, `hist-before.txt`, `hist-after.txt`, `histo-samples.txt`). N = 100,000 loaded at ALL and diverged at ONE with 0 errors (`load-*.json`, `diverge-*.json`); table `read_repair` = NONE (`schema.json`); thresholds read back as set in every run; settings at start: fail 32000, warn 2000, read/range timeouts 60000 ms, `internode_max_message_size` 134217728 B (`settings.json`). Every query left exactly one `RESP` line (2 responses: node 2 52,981,352 B, node 1 168 B; total 52,981,520 B, identical in all eight CL ALL runs).

| T | Run | Outcome (client) | `PEAK` kind | current | non-null rows held | bytes held | bytes / row | `RecentValues` top bucket | Predicted (current / rows / bucket) | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| 1000 | r1, r2 | `OverloadedErrorMessage` "cached over 1000 rows", 0.38 s / 0.17 s | throw | **1001** | **500** | 400,048 | 800.1 | 1109 | 1001 / 500 / 1109 | `T1000-r1/`, `T1000-r2/` |
| 10000 | r1, r2 | Overloaded "cached over 10000 rows", 0.19 s each | throw | **10001** | **5,000** | 4,000,048 | 800.0 | 11864 | 10001 / 5000 / 11864 | `T10000-r*/` |
| 32000 (default) | r1, r2 | Overloaded "cached over 32000 rows", 0.24 s each | throw | **32001** | **16,000** | 12,800,048 | 800.0 | 35425 | 32001 / 16000 / 35425 | `T32000-r*/` |
| 1000000 (positive control) | r1, r2 | OK, 0 rows, 1.01 s / 0.87 s | populate | **200,000** | **100,000** | 80,000,048 (76.3 MiB) | 800.0 | 219342 | 200000 / 100000 / 219342 | `T1000000-r*/` |
| 1000000, CL ONE (informational) | — | OK, 0 rows, 0.02 s | none | — | — | — | — | 0 (zero bucket) | node 1 serves: 0 rows, no `PEAK` | `ONE-T1000000/` (`RESP` with 1 response, 288 B) |

r1 and r2 are identical in every probe field. Per-builder split in every `PEAK` line: node 1's builder holds 0 rows and has counted T/2 + 1 (or N) versions, node 2's holds T/2 (or N) rows (e.g. `0/16001 16000/16000`). Node-1 `system.log` has exactly 6 RFP logger lines (`node1-rfp-error-count.txt`), one per failing query. The informational 2-s class-histogram sampler took one sample per query and saw the baseline `BTreeRow` count (183,809) every time (`histo-samples.txt`, `histo-baseline-excerpt.txt`): every query ended before a second sample, as C4 expected.

### 4.2 Conclusion and logic

1. **Validity.** Unit: thresholds and warn threshold read back as set [observed: `rfpu-raw.txt` columns 4–5]; N = 20,000 in every run; the instrument check matched [observed: `RFPU-KA`]; the control reached the full demand (20,000 rows returned, max bucket of 40,000) [observed]. Cluster: yaml overrides present on both nodes [observed: `yaml-node*.diff`], node 2 JMX 7299 [observed: `env-node2.diff`]; 100,000 rows loaded and diverged with 0 errors [observed: `load-*.json`, `diverge-*.json`]; `read_repair` NONE [observed: `schema.json`]; thresholds read back [observed: `threshold.txt`]; the positive control held exactly 2N versions and N rows [observed: `T1000000-r*/probe.txt`]; the Byteman rules type-checked [observed: `btm-check.txt`]. Usage was driven past every capped T (demand 40,000 and 200,000). The run is valid.
2. **Readings.** No gap or outlier. Beyond the predictions: bytes per held row is 800.0 B at every T (800.1 at T = 1000, where the constant 48 B of shared objects weighs more) [observed]; the T = 1000 query took 0.38 s in r1 and 0.17 s in r2 (first-query warm-up) [observed: `query.json`]; node 1's startup logged a 40 s local pause (`node1-errwarn.txt`), before any query [observed]; nothing else unusual in `node1-errwarn.txt`.
3. **Matched row.** Unit B2g row 1 as amended by U5: "failure, exactly one log line and histogram max = bucket(T+1) for every T < 2N (1000, 10000, 32000); success with max = bucket(2N) for T = 100000; control as U4 — claim holds at the operand level": FAIL with `OverloadedException` and 1 RFP log line at 1000, 10000, 32000, maxima 1109, 11864, 35425; T = 100000 OK with 0 rows and max 42510, 1 RFP request; control OK with 20,000 rows, max 42510, 0 requests [observed: `run1/unit/rfpu-raw.txt`]. Cluster B3g row 1 as amended by C7, "claim confirmed at the resource level": the three capped T fail at current = T+1 holding exactly T/2 rows; the control holds N = 100,000 rows at 2N = 200,000; bytes per row constant (800.0–800.1 B); bytes 400,048 < 4,000,048 < 12,800,048 < 80,000,048, each = min(T/2, N)/N × the control's within 0.02 %; r1 = r2; histogram buckets as predicted; one RFP log line per failure [observed: `run1/cluster/*/`].
4. **Excluded rows.** Unit row 2 (refuted: a T < 2N succeeds or max above bucket(T+1)) — all three fail, maxima equal the predicted buckets; U5 (a) another exception or max below bucket — no; (b) no histogram sample — 1 sample each; (c) control mismatch — 20,000 rows, 42510; (d) read-back mismatch — no; (e) instrument check fails — passed; B2g row 3 (control max far below 40,000) — 42510 [observed]. Cluster row 2 (refuted) — no capped run succeeded, no `PEAK` above T+1, capped bytes ≤ 12.8 MB ≪ 80.0 MB; row 3 (A4 dominates) — `RESP` + bytes is 53.38 MB at T = 1000 vs 132.98 MB at the control (ratio 2.49, not within 10 %); row 4 (control shows no rise) — control holds 100,000 rows; C7 (a) other error — none; (b) probe error or missing `PEAK` — none; (c) repeats disagree — identical; (d) read-back mismatch — none [observed].
5. **Observed vs. inferred.** The verdict rests on observed values. Inferred and not load-bearing: that the probe's bytes are the heap RFP retains (`measureDeep` of the held rows; `ColumnMetadata`/`TableMetadata` are `@Unmetered`, and the rows' buffers own their arrays because deserialization copies, `ByteBufferUtil.java:444-452`); that the 168-B node-1 response means node 1 returned no rows (it filtered its `'new'` rows); that the CL ONE run was served by node 1 (one 288-B response from 127.0.0.1).
6. **Deviations and gaps.** None from the frozen runbook. Gaps: (a) the entry-pointer branch `:430` is not exercised by either tier (both run range reads, `consumeEntirePartitions` = true, `:143`); the constraint check tested here is shared by both branches, but the `LIMIT` single-partition path's counting is not measured (recommendation 10). (b) The unit tier reads the counter only (histogram bucket), by design. (c) The cluster heap measure is the rows RFP holds, not the whole query's coordinator heap; the raw responses (`RESP`, 53 MB) and the second-phase fetch from node 1 (not measured) are A4 consumers outside the cap, as the case states.
7. **Core question.** Hypothesis (B1): for a replica-filtering query whose replicas disagree, RFP never holds more than `cached_rows_fail_threshold` row versions (the query fails at T+1), and the heap of the held rows scales with min(T, demand). Test and logic (B2b–B2e, B3b–B3e): the unit tier shows, for the same divergent partition of 20,000 rows, the query fail at each T < 40,000 with RFP's own exception and the recorded peak in the bucket of T+1, while T = 100,000 lets it complete at the bucket of 40,000 (parts 1, 3). The cluster tier measures the held rows directly at the peak: 500 / 5,000 / 16,000 rows (0.40 / 4.0 / 12.8 MB) at T = 1000 / 10000 / 32000 (default), against 100,000 rows (80.0 MB) when the threshold does not bind (parts 1, 3, 4). **Usage follows the constraint and the constraint caps it: the held rows are exactly T/2 when one replica is silent (null versions count, A3), so the cap bounds RFP's heap at about 800 B × T/2 for these rows; it does not bound the raw responses (53 MB here), as A4 says.**

**Conclusion (one line):** unit — B2g row 1 (U5) — confirmed; cluster — B3g row 1 (C7) — confirmed.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` re-parses the raw files (unit: the verbatim `RFPU` lines and the JUnit XML; cluster: per run `threshold.txt`, `query.json`, `probe.txt`, `hist-after.txt`, plus `settings.json`, `schema.json`, yaml/env diffs, load/diverge JSON and the RFP log-line count) and recomputes every amended relation; it computes the histogram bucket bounds itself from the `newOffsets` formula, without Cassandra. It was written before run 1 and run end to end on both shakedowns (exit status 0; §3). On run 1, over the committed copies with `--frozen`: **175 checks, 0 failed, exit status 0**; sub-predictions (b band, `RESP` band) **2 hit, 0 missed**; output `run1/selfcheck.out`. Run over the full log folder of the cluster tier, it gives the same result (121 cluster checks, 0 failed).

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: read-backs, frozen values, yaml/env lines, settings, `read_repair` NONE, load/diverge totals, JUnit 1/0/0, instrument check — all PASS. |
| 2. Readings | yes | Re-read `T32000-r2/probe.txt` (`PEAK,throw,…,32000,32001,0,16000,12800048,64016,0/16001 16000/16000`) and `T1000000-r1/probe.txt` (`populate`, 200000, 100000, 80000048); `node1-errwarn.txt` (40 s pause at start-up, 07:18 UTC, before the first query at 07:20 UTC). |
| 3. Matched row | yes | Every U4/U5 and C6/C7 relation recomputed from raw rows: PASS. |
| 4. Excluded rows | yes | The excluded rows' conditions are negations of PASS checks (failures at T < 2N, exact current and rows, ratio to control, row-3 margin, repeats, buckets). |
| 5. Observed vs. inferred | yes | No self-check relation uses the part-5 inferences; the 168-B and 288-B responses are in `probe.txt`. |
| 6. Deviations and gaps | yes | `commands.log` of both tiers shows every frozen step; the gaps are stated, not hidden. |
| 7. Core question | yes | Ceiling follows the knob (T+1 / T/2 exactly, bytes proportional), direct disallow evidence (exception + RFP log line per failure), positive control at full demand. |

### 5.2 Run 2?

**No** — 2026-10-27. The conclusion rests on observed readings only, every self-check part holds, the cluster repeats are identical, and the result neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested (B1):** For a replica-filtering query whose replicas disagree, the number of rows RFP holds on the coordinator heap never exceeds `cached_rows_fail_threshold` (the query fails at threshold+1), and the coordinator's live heap attributable to cached rows scales with min(threshold, rows that would be cached unbounded).

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1, U5) — in-JVM 2-node, 20,000 divergent rows: fails with `OverloadedException` at T = 1000 / 10000 / 32000 (default), peak in the bucket of T+1 (1109 / 11864 / 35425); completes at T = 100000 with the peak in the bucket of 40,000; control 20,000 rows | caps | run 1 + self-check | 2026-10-27 |
| Cluster | Confirmed (B3g row 1, C7) — 2 nodes, 100,000 divergent rows: RFP holds exactly 500 / 5,000 / 16,000 rows (0.40 / 4.0 / 12.8 MB) and fails at count T+1 for T = 1000 / 10000 / 32000; holds 100,000 rows (80.0 MB) at 2N under T = 1000000; 800 B per row constant; repeats identical | caps | run 1 + self-check | 2026-10-27 |

**Feedback filed:** the case file's section D updated (uncommitted, after sha256 `3fe55d66…7a9a`); B2–B4 carry the 14 dated amendments (U1–U5, C1–C8, D1); `_INDEX-advisor.md` §2 has two new rows (frozen and D1 hashes) and §1's Stage 4 column for this file is filled. Recommendations 10 and 11 are left for stage 3.
