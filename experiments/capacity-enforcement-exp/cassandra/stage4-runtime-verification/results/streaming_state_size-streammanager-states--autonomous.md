# streaming_state_size-streammanager-states--autonomous — stage-4 results  <!-- file: results/streaming_state_size-streammanager-states--autonomous.md -->

> **Case:** [`streaming_state_size-streammanager-states--autonomous`](../../stage3-ai-deep-read/cases/streaming_state_size-streammanager-states--autonomous.md)
>
> **Status:** self-checked, verdict filed by the stage-4 session (2026-11-11); run 2 not chosen
>
> **Outcome class:** true positive (estimate `positive`; unit **Confirmed — caps**, cluster **Confirmed — caps**)
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `f74aade6` (the case file is untracked there; the coordinator commits it). Filing sha256 (`_INDEX.md` §4): `61bdce66f4bec5d3c2d7f79dae4e745403956ad5ddc9214b1bf733ddb041bb9c`. sha256 of the whole file after the audit's amendments S4-A1 to S4-A9 (2026-11-11): `b021248915597cd9ec6aa7b8d4db129de8372440a6b910225c0fb5d6e1cc1510`. sha256 of the frozen prediction and conclusion tables (text of B2f+B2g from `**B2f.` up to `**B2h.`, and B3f+B3g from `**B3f.` up to `**B3h.`, concatenated, amendments S4-A3/A4/A8/A9 included; copy at `/mydata/jingsong-cass-s4/o53/logs/freeze-pred.txt`): `cdeefe149160d9360165f2491b446b691eb3f06a67da1a17ea4ed82a475c6eca`. Frozen 2026-11-12 03:46 UTC (2026-11-11 local), before any reading. Section D (feedback) is outside the table hash and changes after the run. After section D was filled (2026-11-11): file sha256 `a18e4d1f83465b0e293c8f8fc4c2d16f1a22007e99f2974b952aabde7806de15`; table hash re-checked unchanged (`cdeefe14…`). |
| **Harness** | `harness/streaming_state_size-streammanager-states--autonomous/` (files listed in its README; not committed by this session, the coordinator commits) |
| **Tiers and values** | Unit (B2): `streaming_state_size` ∈ {16KiB, 256KiB, 1MiB, 40MiB (default)} × addPeer ∈ {false, true}, N = 5000 completed states each (S4-A2), samples every 250. Cluster (B3): two nodes on 127.0.0.21/.22, S ∈ {16KiB, 32KiB, 4MiB} (S4-A7) plus 4MiB with `streaming_stats_enabled: false`; 150 sequential `nodetool rebuild` of keyspace `o53` on node 2; samples at i = 25…150 every 25. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-11 (S4-A1 to S4-A9 applied) |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: heap bytes of the `StreamingState` tracking set, compared as summed weigher bytes (`StreamManager.java:278-282`). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met (unit) / Met after S4-A7 (cluster) | B2b: 16KiB, 256KiB, 1MiB, 40MiB (default). B3b had two values; S4-A7 adds 32KiB. The cluster default 40MiB is represented by 4MiB (both non-binding for 150 plans). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | Unit: jamm `measureDeep` of the retained states (B2d) besides the weigher; cluster: live-histogram count of `StreamingState` besides the vtable (B3d). Gap: cluster real bytes are count × unit deep-per-entry (inferred), named in B3d. |
| A. Core question | usage driven to the limit and past it | Met after S4-A2 | At N = 2000 the 1MiB cap binds only if w > 525 B (B2c); the source puts w around 330–550 B, so N = 5000. Cluster: 150 plans × w ≫ 16KiB and 32KiB. |
| B. Logic | each step says what it establishes | Met | B2h/B3h name the role of each value and of addPeer. |
| B. Logic | prediction stated in numbers or a clear relation | Met after S4-A3, S4-A8 | B2f/B3f give floor(cap/w) within −30 %; "plateau", "flat", "same", "factor" were undefined; fixed in writing. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met after S4-A4, S4-A9 | B2g/B3g rows had no verdict labels; added rows: flat but over the weight (V6/C7), stats-disabled non-zero (C2), live ≫ vtable with growth (C4). Unmatched reading → Not confirmed (no matching row). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Plateau ≈ floor(S/w) across three caps (unit) and two binding caps (cluster) = ceiling follows knob; the disallow branch (Guava eviction) is observed directly as entries leaving the cache (`retained` < `inserted`, vtable count < i) while the uncapped control keeps all. |
| B. Logic | alternative explanations and their controls | Met | Expiry (3d) ruled out by 40MiB/4MiB controls (B2h/B3h); weight-estimate accuracy separated by addPeer; stats-disabled shows the counted objects come from this path. |
| C. Specific | a human can follow it from the intro and B1 | Met | Estimate line, A3 and B1. |
| C. Specific | an AI can run B2a–B2e / B3a–B3e without re-deriving the code path | Partly → Met after S4-A6 | As filed, rebuilds 2–150 would throw before `streamPlan.execute()` (`RangeStreamer.java:716-749`): no plans, no states. S4-A6 adds `-Dcassandra.reset_bootstrap_progress=true` and `auto_bootstrap: false` on node 2. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met after S4-A5, S4-A7 | Shared-node addresses/ports (S4-A5); samples, failure logging and size-log stop condition (S4-A7). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | JDK 11.0.33, Ant 1.10.12, `copy-source.sh` + `ant build-test` (BUILD SUCCESSFUL, 1 min 18 s); the test class is given in B2a. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met after S4-A2 | Unit: 5000 × ~0.5 KB per config, trivial in the 1 GiB test heap. Cluster: 2 × 1 GiB heap, data negligible, ~150 × 3 s ≈ 8 min per value, 4 values. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked in `systems/cassandra/source` (5.0.9): `StreamManager.java:228, 238-251 (onRegister, put before phase.start), 256-261, 265-272 (maximumWeight), 278-282 (weigher), 305-315 (putStreamingState)`; `StreamingState.java:51 (EMPTY), 75-80 (unsharedHeapSize), 253-258 (streamPrepared adds peer), 296-302 (onFailure re-put)`; `Config.java:948-951`; `DatabaseDescriptor.java:5003-5015`; `StreamResultFuture.java:82-86` (test constructor, follower coordinator); `InetAddressAndPort extends InetSocketAddress`; Guava 32.0.1-jre (`.build/parent-pom-template.xml:309`). All as cited. Extra finding: `RangeStreamer.java:716-749` (S4-A6). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| S4-A1 | Stage-4 paths, `copy-source.sh`, test-log location | applied 2026-11-11 (case file untracked; no commit) | runnable on this node |
| S4-A2 | N = 5000 | applied 2026-11-11 | 1MiB must be reached for any plausible w |
| S4-A3 | Unit reading rules (plateau, flat, band, factor, bound) | applied 2026-11-11 | predictions must be contradictable; thresholds fixed before reading |
| S4-A4 | B2g verdict labels and missing rows | applied 2026-11-11 | every outcome needs a row |
| S4-A5 | Addresses 127.0.0.21/.22, ports 7300/7301/9342, JMX 7499/7498 | applied 2026-11-11 | shared node |
| S4-A6 | `reset_bootstrap_progress=true`, `auto_bootstrap: false` on node 2 | applied 2026-11-11 | as filed only one rebuild would register a plan |
| S4-A7 | Third cluster value 32KiB; samples every 25; stats-disabled run included | applied 2026-11-11 | ≥ 3 values; flatness test |
| S4-A8 | Cluster thresholds | applied 2026-11-11 | as S4-A3 |
| S4-A9 | B3g verdict labels and missing rows | applied 2026-11-11 | as S4-A4 |
| R-a | State in A3 that Guava splits `maximumWeight` over 4 segments, so a single entry heavier than S/4 is never retained | left for stage 3 | already implied by "Tiny caps" |
| R-b | Use JMX from one client JVM instead of 150 `nodetool` JVMs | left for stage 3 | speed only |

**Agreement criteria** — run 2 not planned.

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-11-12 UTC (2026-11-11 local): unit 03:50 UTC; cluster 03:53–04:16 UTC | not done |
| Node (CloudLab name and type) | local `node0.jason92-325405` (32 cores, 125 GiB), shared; this run on loopback 127.0.0.21/.22, ports 7300/7301/9342, JMX 7499/7498 | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, 5.15.0-198-generic | |
| JDK (`java -version`) | openjdk 11.0.33 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy | `/mydata/jingsong-cass-s4/o53/src` (`copy-source.sh` at repository HEAD `f74aade6`, tag `cassandra-5.0.9`; `ant build-test` 1 min 18 s); node trees `n1`, `n2` = `cp -a` of it | |
| Case-file / harness commit | both untracked at HEAD `f74aade6` (the coordinator commits); case-file sha256 in section 1; harness md5 in `run1/unit-summary.txt` and `run1/cluster-*-summary.txt` | |
| Storage for node data | `/mydata` (local disk), per label `/mydata/jingsong-cass-s4/o53/run1/cluster/<label>/n<k>/`; heap 1 GiB per node | |
| Full logs (path, outside the repo) | `/mydata/jingsong-cass-s4/o53/run1/{unit,cluster}/` (test log, junit XML, per-label `system.log`, `gc.log`, `samples.csv`, `rebuild-<i>.txt`, final histograms and vtable dumps); shakedowns in `/mydata/jingsong-cass-s4/o53/shakedown/` | |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | audit (before run 1) | B3c / B3e.4 | As filed, only the first `nodetool rebuild -ks o53` would register a stream plan: `RangeStreamer.fetchAsync` (`RangeStreamer.java:716-749`) finds the ranges already available from the previous rebuild and throws "Discovered existing bootstrap data …" before `streamPlan.execute()` unless `cassandra.reset_bootstrap_progress` is set. Node 2's join would also add a BOOTSTRAP plan. | S4-A6: `-Dcassandra.reset_bootstrap_progress=true` and `auto_bootstrap: false` on node 2. Found from the source before any run; prediction unchanged. | 2026-11-11 | untracked (no commit) |
| D2 | audit | B2c | N = 2000 does not reach the 1MiB cap unless w > 525 B. | S4-A2: N = 5000. (Run 1's first sample showing eviction at 1MiB is inserted = 2750, `run1/selfcheck.txt`: the filed N would have made the 1MiB prediction fail for a workload reason.) | 2026-11-11 | untracked |
| D3 | shakedowns | harness | (a) `printf("...%n")` in the test is split over several lines by the test logger; (b) Cassandra deletes its `-p` pid file at shutdown, so the stop routine lost node 1's PID (the node still shut down on SIGTERM, checked by PID). | harness only: one `println(String.format(...))` per line; PID saved once the node is up. | 2026-11-11 | n/a |

## 4. Run 1

**Scope:** unit tier (B2) all 8 configurations as amended (N = 5000); cluster tier (B3) all four labels of S4-A7 (16KiB, 32KiB, 4MiB, 4MiB stats disabled), 150 rebuilds each, samples every 25. **Command log:** `run1/unit-summary.txt`, `run1/cluster-<label>-summary.txt`; raw readings `run1/unit-o53-lines.txt`, `run1/cluster-<label>-samples.csv`; analyzer output (the `EXPECTED:` lines) in `run1/unit-summary.txt` and `run1/cluster-analysis.txt`; self-check `run1/selfcheck.txt`; frozen tables `run1/freeze-pred.txt`.

### 4.1 Readings

**Unit tier** (w = EMPTY 352 + TIMEUUID_SIZE 32 = **384 B**; Guava split the cache into 4 segments, so the plateau is 4 · floor(cap/4/w))

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| 40MiB, addPeer false / true | `retained` = `inserted` at all 20 samples (5000 at the end) | `run1/unit-o53-lines.txt`, `run1/selfcheck.txt` |
| 16KiB, addPeer false / true | plateau 40 / 40 from the first sample (inserted 250) to 5000; plateau·w 15,360 ≤ 16,384; deep 14,080 / 23,696 B (deep/cap 0.86 / 1.45) | same |
| 256KiB | plateau 680 / 680 from inserted 750; plateau·w 261,120 ≤ 262,144; deep 239,360 / 402,576 (0.91 / 1.54) | same |
| 1MiB | plateau 2728 / 2728 from inserted 2750; plateau·w 1,047,552 ≤ 1,048,576; deep 960,256 / 1,614,992 (0.92 / 1.54) | same |
| weigher vs jamm, addPeer=false | deep / weightNow = 0.917 in every configuration (the weigher counts the `TimeUUID` twice: it is in `EMPTY` and added again as `TIMEUUID_SIZE`) | `run1/unit-summary.txt` |
| addPeer=true overshoot | weightNow/cap = 1.445 / 1.536 / 1.540, deep/cap = 1.446 / 1.536 / 1.540 (16KiB / 256KiB / 1MiB); deep per entry 592 B vs insert weight 384 B (factor 1.54) | same |
| B2f/B2g checks | 38 PASS, 0 FAIL; matched V5 | `run1/unit-summary.txt` |

**Cluster tier** (P(S) = floor(S/384); d = 592.4 B; both nodes identical at every sample)

| Capacity value | Run | Observable | Reading (i = 25 / 50 / 75 / 100 / 125 / 150) | Evidence (file) |
|---|---|---|---|---|
| 16KiB (P = 42) | binding | vtable count = live histogram count, n1 and n2 | 22 / 34 / 40 / 40 / 40 / 40 | `run1/cluster-s16k-samples.csv`, `run1/cluster-analysis.txt` |
| 32KiB (P = 85) | binding | same | 25 / 50 / 70 / 84 / 84 / 84 | `run1/cluster-s32k-samples.csv` |
| 4MiB | control | same | 25 / 50 / 75 / 100 / 125 / 150 | `run1/cluster-s4m-samples.csv` |
| 4MiB, `streaming_stats_enabled: false` | control | same | 0 at every sample | `run1/cluster-s4m-nostats-samples.csv` |
| all | | rebuilds; plans in `system.log`; ERROR lines; size log line | 150 / 150 exit 0 per label; 150 plans on each node per label (0 bootstrap plans); 0 ERROR; size line 16384 / 32768 / 4194304 / 4194304 | `run1/selfcheck.txt`, `run1/cluster-*-summary.txt` |
| all | | final vtable: operation/status, peers | only `Rebuild/success`; one peer per entry (node 1: follower, peer `/127.0.0.22:7300`) | `run1/cluster-*-summary.txt`; `n1-vtable-final.txt` on the node |
| binding values | | live · d vs 2·S | 16KiB: 40 · 592.4 = 23,696 ≤ 32,768; 32KiB: 84 · 592.4 = 49,762 ≤ 65,536 | `run1/cluster-analysis.txt` |
| all | | shallow histogram bytes; whole heap | 64 B per `StreamingState`; heap used 68.8–74.3 MB in every label (cannot resolve these KB-scale differences, B3d) | `run1/cluster-*-samples.csv` |
| B3f/B3g checks | | | 19 PASS, 0 FAIL; matched C6 | `run1/cluster-analysis.txt` |

### 4.2 Conclusion and logic

1. **Validity** — Valid. Limit reached and passed: the first unit sample showing eviction is at inserted 250 / 750 / 2750 for 16KiB / 256KiB / 1MiB (samples every 250), well before N = 5000 [observed: `run1/selfcheck.txt`]; cluster counts stop below i at 16KiB from i ≈ 40 and at 32KiB from i ≈ 70 [observed: `run1/cluster-analysis.txt`]. Hold-fixed settings: fresh `StreamManager` per unit configuration; for the cluster, fresh data directories per label, identical yaml except the knob (`n<k>-cassandra.yaml` kept per label), 150 rebuilds with exit 0 and 150 plans in each node's log, 0 bootstrap plans, size log line as configured on both nodes [observed: `run1/selfcheck.txt`, `run1/cluster-*-summary.txt`]. Positive controls moved: 40MiB retained = inserted (5000), 4MiB count = i (150) [observed].
2. **Readings** — Nothing unusual. The plateaus are exactly 4 · floor(cap/4/w) (40, 680, 2728 unit; 40 and 84 cluster), which is Guava's per-segment limit with 4 segments [observed numbers; segment arithmetic inferred from Guava `LocalCache`]. The node's insert-time weight equals the unit w: the cluster plateaus 40 and 84 are the unit formula's values [observed]. weightNow/cap and deep/cap agree to 0.001 for addPeer=true [observed].
3. **Matched row** — Unit B2g row 1 / S4-A4 V5: "40MiB `retained` = `inserted` at every sample; every capped configuration flat with plateau · w ≤ cap; deep ≤ 2 · cap everywhere" — 5000 = 5000; flat (last-three spread 0) with plateau·w 15,360 / 261,120 / 1,047,552 below 16,384 / 262,144 / 1,048,576; max deep/cap 1.54 [observed: `run1/unit-summary.txt`]. All secondary bands met (in band, weigher within 8.3 %, same plateau, overshoot factor 1.45–1.54 in [1.1, 2.0]). Cluster B3g row 1 / S4-A9 C6: "4MiB count = i at every sample; both binding values flat with count ≤ P(S); live − count ≤ 5; live · d ≤ 2 · S" — 150 at i = 150; 40 ≤ 42 and 84 ≤ 85, spread 0 between i = 125 and 150; live − count = 0; 23,696 ≤ 32,768 and 49,762 ≤ 65,536 [observed: `run1/cluster-analysis.txt`]. Secondary: in band 4/4, live − count ≤ 2 at 48/48 samples.
4. **Excluded rows** — Unit: V1 (40MiB < inserted): 5000 = 5000. V2 (plateau 0): plateaus 40–2728. V3 (keeps growing past S): spread 0, weight below cap. V4 (deep > 2·cap): max 1.54·cap. V6: V5 matched. Cluster: C1 (4MiB count < i, failed rebuild, wrong size line): none. C2 (stats disabled non-zero): 0 at every sample on both nodes. C3 (growth past S, or ≥ 135 at 150): 40 and 84, flat. C4 (live ≫ vtable): live = vtable at every sample; no live `StreamResultFuture`/`StreamSession`/`StreamCoordinator` at the end. C5 (live · d > 2·S): 0.72·2S and 0.76·2S. C7: C6 matched [all observed: `run1/cluster-analysis.txt`, `run1/selfcheck.txt`].
5. **Observed vs. inferred** — Inferred: (i) cluster real bytes = live count × d, with d the unit's deep size per entry with one peer (592 B); the node's entries also hold one peer each (vtable `peers`), and the node's insert-time weight equals the unit w (plateaus match the formula), but a per-entry jamm reading was not taken on the node; in the node the peer address object may be shared with other structures, so d is if anything an over-estimate of unshared bytes. (ii) That the per-segment split explains the exact plateau values (Guava source, not instrumented). Neither changes the matched rows: (ii) is explanatory only, and (i) has a margin of 24–28 % below 2·S.
6. **Deviations and gaps** — Amendments S4-A1 to S4-A9 (section 1); defects D1–D3 (section 3). The cluster default 40MiB was not run (4MiB stands in, both non-binding). Whole-heap readings cannot resolve the tracking set (B3d says so). The weigher double-counts the `TimeUUID` (deep/weightNow 0.917 without a peer) — conservative, not a bypass. The insert-time underestimate is real (an entry with one peer holds 1.54 × its weight), so a node holds up to about 1.54 · S of tracking state, inside the claimed 2 · S. The `onFailure` re-put path (`StreamingState.java:296-302`) was not exercised (no rebuild failed).
7. **Core question** — Usage followed the constraint and the constraint caps it. In the unit tier the retained set stopped at 40, 680 and 2728 entries for 16KiB, 256KiB and 1MiB while 5000 were inserted, and kept all 5000 at 40MiB (parts 1, 3); on two real nodes 150 rebuilds left 40 entries at 16KiB, 84 at 32KiB and 150 at 4MiB on both the initiator and the follower, with the live heap object count equal to the tracking count (parts 3, 4). The real heap held is about 1.54 × the configured size (weight frozen at insert, before peers are added), inside the claimed bound of 2 × S (part 5).

**Conclusion (one line):** Unit B2g row 1 (S4-A4 V5) and cluster B3g row 1 (S4-A9 C6) — confirmed: `streaming_state_size` caps the streaming-state tracking set (effect: caps, soft by a factor of about 1.54 from the insert-time weight).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parses the raw files with its own code (junit XML; the raw `test.log`, not the extracted lines; `samples.csv` against the summary's own sample lines; the final `GC.class_histogram` and vtable dumps; `rebuilds.csv`; each node's `system.log`). Output `run1/selfcheck.txt`: 33 holds, 0 fails.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.txt`: first sample with eviction at inserted 250 / 750 / 2750; 150 rebuilds exit 0 and 150 plans per node per label; histogram = vtable at the end of every label. |
| 2. Readings | yes | Plateaus recomputed as 4 · floor(cap/4/w) = 40 / 680 / 2728 from the raw test log; cluster 40 / 84 in `cluster-s16k-samples.csv`, `cluster-s32k-samples.csv`. |
| 3. Matched row | yes | Every term of V5 and C6 recomputed (`selfcheck.txt`, `cluster-analysis.txt`). |
| 4. Excluded rows | yes | Each exclusion cites a number re-read above; C4 additionally checked with the final histogram (no live futures, sessions or coordinators). |
| 5. Observed vs. inferred | yes | (i) has a 24–28 % margin; the vtable dump shows one peer per entry, the case d was measured for. |
| 6. Deviations and gaps | yes | Listed; none touches a primary condition. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1 → B2b–B2e / B3b–B3e → B2f / B3f → B2g / B3g as amended, in that order; positive controls (40MiB, 4MiB) moved with the workload; stats-disabled control shows the counted objects come only from this path. |

### 5.2 Run 2?

**No** (2026-11-11). Both tiers agree, every primary and secondary prediction held, the plateau values match the cache's own arithmetic exactly, and the only inferred step (cluster real bytes via d) has a wide margin. The result neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps) — both tiers Confirmed with effect `caps`.

**Claim tested:** (B1) With `streaming_state_size = S`, the number of `StreamingState` objects retained after many completed stream plans stops growing once their summed weight reaches S (summed weight ≤ S), while with a large S all of them are retained; the real heap they retain is bounded by S times a constant (1 < factor ≤ 2) that comes from the insert-time weight underestimate. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1 (S4-A4 V5): **Confirmed** — plateaus 40 / 680 / 2728 for 16KiB / 256KiB / 1MiB, 5000 retained at 40MiB; real bytes ≤ 1.54 · S | caps (soft, factor ≈ 1.54 with one peer) | run 1 + self-check | 2026-11-11 |
| Cluster | B3g row 1 (S4-A9 C6): **Confirmed** — 40 / 84 / 150 entries at 16KiB / 32KiB / 4MiB on both nodes after 150 rebuilds; live objects = tracked entries; 0 with stats disabled | caps (soft) | run 1 + self-check | 2026-11-11 |

**Positive control:** unit — 40MiB keeps every inserted state (5000 of 5000, both addPeer settings); cluster — 4MiB tracks every plan (count = i at every sample, 150 at the end on both nodes) under the same workload that leaves 40 and 84 at 16KiB and 32KiB.

**Feedback filed:** the case file's section D updated (amendments S4-A1 to S4-A9 and the stage-4 result); no section of the trace was refuted. **Notes for stage 3:** the weigher counts the `TimeUUID` twice (it is inside `EMPTY` and added as `TIMEUUID_SIZE`), so without peers it slightly over-charges (deep/weight 0.917); with one peer, added after the insert, an entry holds 1.54 × its weight; the plateau is exactly 4 · floor(S/4/w) because Guava splits `maximumWeight` over 4 segments. **Upstream / doc candidates:** none for a bug; a doc note could say the limit is approximate (entries are weighed before their peers are known). **Leftovers on the node:** nothing running (checked by PID and by `CassandraDaemon` command lines under `/mydata/jingsong-cass-s4/o53`: none). Kept on disk: `/mydata/jingsong-cass-s4/o53/` (about 1.5 GB: `src` build tree, node trees `n1`, `n2`, logs `logs/`, `shakedown/`, `run1/`).
