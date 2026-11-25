# default_max_capacity-protocolversiontracker-capacity--autonomous — stage-4 results (o134)

> **Case:** `cassandra/stage3-ai-deep-read/cases/default_max_capacity-protocolversiontracker-capacity--autonomous.md` (writeup-set-ext order 134, band B)
>
> **Status:** verdict filed (run 1 + self-check), 2026-11-25. Both tiers run on `pc72`.
>
> **Outcome class:** true positive (estimate `positive`; unit and cluster tiers both `caps`)
>
> **Agent:** autonomous. "§9a" means B2f/B2g (unit) and B3f/B3g (cluster); feedback goes to section D.

Everything here is outside the repo: harness `~/writeup-ext/out/o134/harness/`, raw files `~/writeup-ext/out/o134/run1/`
(`unit/`, `cluster/{stock,uncapped}/`, `logs/`, `analysis.txt`), amended case file `~/writeup-ext/out/o134/case-amended.md`.
The same raw files remain on the node at `/mydata/jingsong-cass-s4/o134/{unit,cluster,logs,harness}` (13 MB; build copies and node data deleted).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed: commit `bef6bc8a6`, sha256 `92723b762ae7e7e72ed99760ad74c2b75cc773c8d526a57d7989bf3c48392c0d` (equal to `_INDEX.md` §4; repo HEAD `cd9e1cded`). Frozen after the audit's amendments S4-A1 to S4-A3 (section D still "none yet"): sha256 `447c4fc55efacac12277595a11773e41e573c6a5099d12b161d27a88aa0cc993` (`harness/case-frozen.md`). With section D filled: `case-amended.md`, sha256 `6e0fb423fa393b478ff1e05e278a6a68d9139151f80e8b8416a380d04be9bfa3`. |
| **Harness** | `harness/`: `PvtProbe.java` (B2c, verbatim), `StartupFlood.java` (B3a, verbatim), `setup.sh`, `unit-all.sh` (B2e), `cluster-run.sh` (B3e + B4), `drive.sh` (detached driver, PID file `/mydata/s4/DRIVER-jingsong-o134.pid`), `analyze.py`, `md5.txt`, `case-as-filed.md`, `case-frozen.md`, `freeze.sha256`. Not committed (the task forbids repo edits). |
| **Tiers and values** | Unit: capacity ∈ {100 (stock no-arg constructor), 1000, 2147483647} × N ∈ {50, 100, 101, 1000, 10000, 1000000} × 3 reps, + `ProtocolVersionTrackerTest`. Cluster: build ∈ {stock (100), uncapped (1 000 000)} × cumulative V4 N ∈ {50, 100, 150, 1000, 20000}, then 1000 each on V3/V5/V6, repeat, clear. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Met | A2: entry count with a derivable byte size; heap measured (B2d heap delta, B3d class histogram) |
| A | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met (unit) / Partly (cluster) | A1: constant, not settable. Unit varies it by reflection (100/1000/MAX). Cluster uses two builds (100 vs 1 000 000) — a two-arm design, reason stated in B3b |
| A | real resource measured, not only the counter | Met | B2d heap after GC; B3d `GC.class_histogram` bytes of the entry classes |
| A | usage driven to the limit and past it | Met | B2b N up to 10^6 (10^4 × cap); B3b N up to 20 000 (200 × cap) |
| B | each step says what it establishes | Met | B2b/B2h, B3b/B3h |
| B | prediction stated in numbers or a clear relation | Met | B2f exact sizes; B3f exact row counts and ≤ 1/40 ratio |
| B | every plausible outcome has a conclusions row | Met | B2g/B3g cover exceeds-cap, flat, counter-capped-but-heap-grows, control failed, workload not registering |
| B | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly | Ceiling following the knob: cap 100 vs 1000 vs MAX (unit). Eviction evidence is the count held at cap while > cap distinct keys were written (Caffeine stats disabled, so no eviction counter). Acceptable: no other path removes entries (A3.7) |
| B | alternative explanations and their controls | Met | B2h/B3h: uncapped controls, below-cap N, `cleanUp()`, clear-history, idle node |
| C | a human can follow it from the intro and B1 | Met | |
| C | an AI can run B2e/B3e without re-deriving the code path | Met | Code given verbatim |
| C | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Paths `/local/…`, readiness wait and row-count parsing needed pinning (S4-A1, S4-A3) |
| D | harness and environment prerequisites exist or are listed | Met | JDK 11, Ant, built base on `pc72` |
| D | workload arithmetic reaches the limit | Met | MAX_VALUE N = 10^6 plus the 1.5 M second pass ≈ 0.5 GB; 4 GB heap (S4-A2). 20 000 handshakes took 5.5–6.2 s |
| D | load-bearing citations spot-checked | Met | `ProtocolVersionTracker.java:36,40-54,56-59` read on the node copy; `ClientStats.java` `--by-protocol` output format (`<n>/v<n>` first column) checked; `cassandra.in.sh` loads `build/apache-cassandra*.jar` (hence `ant jar` for the uncapped copy) |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| S4-A1 | Pin paths to `/mydata/jingsong-cass-s4/o134/`; copy the built base; uncapped = copy + edit + `ant jar`, checked with `javap` | Applied 2026-11-25 (before any reading), `case-amended.md` B2a/B3a | Runnable on this node set |
| S4-A2 | `-Xms4g -Xmx4g` on all unit runs | Applied 2026-11-25 (before any reading), B2a | The B2c note's own option, so the MAX_VALUE second pass runs at every N with one JVM size for all arms |
| S4-A3 | Readiness = `statusbinary running` + `UN`; `ulimit -n 100000`; port check; row count by `^[0-9]+/v` | Applied 2026-11-25 (before any reading), B3e | `environment.md` §6; the awk's `NR>3` depends on header position |
| R1 | Add a direct eviction observable (e.g. `recordStats()` in a test-only copy, or `asMap().size()` after each step) | Left for stage 3 | Not needed for the verdict |
| R2 | B2f's "may exceed the cap by a small amount" should say the transient overshoot is bounded by Caffeine's write buffer, which scales with CPU count | Left for stage 3 | See §4.2 part 2 |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25, 08:52–09:02 UTC |
| Node | `pc72` = `node2.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu` (UMass), **x86_64**, 40 cores, 125 GiB, `/mydata` 753 GB (705 GB free) |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-203-generic` |
| JDK | OpenJDK 11.0.33 (2026-10-20) |
| Ant | 1.10.12 |
| Local source copy | `cp -a /mydata/s4/cassandra-base` (from repo `systems/cassandra/source/`, `cassandra-5.0.9`) ×3: `c509-unit`, `c509-stock`, `c509-uncapped` (+ line 36 → `1_000_000`, `ant jar` 35 s, `logs/uncapped.diff`) |
| Case-file commit / harness | `bef6bc8a6` / not committed (outside the repo, md5 in `harness/md5.txt`) |
| Storage for node data | `/mydata/jingsong-cass-s4/o134/s3data` (local disk) |
| Full logs | `~/writeup-ext/out/o134/run1/`; on the node `/mydata/jingsong-cass-s4/o134/` |
| Node lock | acquired 01:49:40 MST (free, no partial `o134` folder on `pc72`); released at the end |

## 3. Runbook defects

None. (The setup's first `javap` check printed nothing because its grep window was too short; it was re-run by hand with a wider window and
appended to `logs/setup.log`. That was a harness check, not a runbook step.)

## 4. Run 1

**Scope:** both tiers, all values. **Command logs:** `run1/logs/setup.log`, `run1/unit/session.log`, `run1/cluster/{stock,uncapped}/session.log`, `run1/logs/driver.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/results.txt`, `run1/analysis.txt`; 3 reps identical in every size reading)

| cap | N | V4 size = getAll(V4) after cleanUp | maxRawBeforeCleanup (3 reps) | heap delta, median (B) | V3/V5/V6/total after second pass |
|---|---|---|---|---|---|
| 100 | 50 / 100 / 101 / 1000 / 10000 / 10^6 | 50 / 100 / 100 / 100 / 100 / 100 | 1… / 8032 8019 8137 (N=10^4) / 16139 16002 16159 (N=10^6) | 219 224 / 229 200 / 246 696 / 256 024 / 322 776 / 379 104 | 25,25,25/125; 50…/250; 50…/250; 100,100,100/400; 100…/400; 100…/400 |
| 1000 | same | 50 / 100 / 101 / 1000 / 1000 / 1000 | 1… / 8120 8186 8175 / 16906 16333 15796 | 218 184 / 226 024 / 228 008 / 373 640 / 467 232 / 581 408 | …; 1000,1000,1000/4000 at N ≥ 10^4 |
| MAX | same | 50 / 100 / 101 / 1000 / 10000 / 1000000 | 1… / 8193 / 999425 | 218 184 / 226 024 / 228 368 / 365 368 / 1 755 800 / **155 045 320** | 500000×3 / 2 500 000 at N = 10^6 |
| shakedown | cap 100 N 50 → 50; cap MAX N 101 → 101 (known answers) | | | | |
| `ant testsome ProtocolVersionTrackerTest` | Tests run 3, Failures 0, Errors 0 — BUILD SUCCESSFUL (`run1/unit/ant-testsome.log`) | | | | |

**Cluster tier** (`run1/cluster/<build>/session.log`, `r-*.txt`, `h-*.txt`; deltas vs `h-0.txt` from `analysis.txt`)

| Build | Step | by-protocol rows | count Δ of each of `Inet4Address`, `InetAddress$InetAddressHolder`, `Long`, `caffeine.cache.PSMS` | Σ bytes Δ (4 classes) |
|---|---|---|---|---|
| stock | baseline (after clear-history + 30 s) | 0 | 0 | 0 |
| stock | V4 N = 50 / 100 / 150 / 1000 / 20000 | 50 / 100 / 100 / 100 / 100 | +50 / +100 / +100 / +100 / +100 | 5 600 / 11 200 / 11 200 / 11 200 / 11 200 |
| stock | + 1000 each on V3, V5, V6 | v3 100, v4 100, v5 100, v6-beta 100 = 400 | +400 | 44 800 |
| stock | repeat same 20 000 on V4 | 400 (unchanged) | +400 | 44 800 |
| stock | after `--clear-history` | 0 | 0 | 0 |
| uncapped | V4 N = 50 / 100 / 150 / 1000 / 20000 | 50 / 100 / 150 / 1000 / 20000 | +50 / +100 / +150 / +1000 / +20000 | 5 600 / 11 200 / 16 800 / 112 000 / 2 240 000 |
| uncapped | + 1000 each on V3, V5, V6 | 1000 / 20000 / 1000 / 1000 = 23 000 | +23 000 | 2 576 000 |
| uncapped | repeat | 23 000 (unchanged) | +23 000 | 2 576 000 |
| uncapped | after `--clear-history` | 0 | 0 | 0 |

Both builds: every `StartupFlood` reply was READY (all `flood-*.err` empty); `system.log` 0 ERROR, 5 WARN (start-up checks only: jemalloc, JMX local,
sigar swap, `vm.max_map_count`, new host ID). Heap 1 G (`jvm-args.txt`). `ConcurrentHashMap$Node` (context only): stock +166 to +718, uncapped +23 271.
The caffeine class identified in the uncapped control as rising by exactly N is `com.github.benmanes.caffeine.cache.PSMS`, as B3d expected.

### 4.2 Conclusion and logic

1. **Validity.** Limit reached and passed in both tiers: unit N up to 10^6 distinct keys [observed: `unit/results.txt`]; cluster 20 000 distinct V4 IPs,
   all handshakes READY [observed: `cluster/stock/session.log`, empty `flood-*.err`]. Stock and uncapped builds carry 100 and 1 000 000 [observed:
   `logs/setup.log` javap lines]. The node was idle apart from the probe; no other Cassandra was running [observed: port and process checks in `session.log`]. Valid.
2. **Readings.** No gaps. One reading is off prediction: B2f's last line expected `maxRawBeforeCleanup` to exceed the cap "by a small amount" and
   "not grow with N". It reached ~8 000 at N = 10^4 and 15 796–16 906 at N = 10^6 for caps 100 and 1000 [observed: `unit/results.txt`]. From N = 10^4 to
   10^6 (×100) it grew ×2 and is the same for both caps, so it levels off; it is consistent with Caffeine's write buffer, sized from the CPU count, filling
   faster than the asynchronous maintenance drains it [inferred: Caffeine 3.1.8 design, library source not read in this run]. B2d calls this observable
   informational and B1 states the claim "after maintenance has drained", so it does not decide the verdict. The N = 10^4 sample is at put 8192 of 10 000, so it
   only shows that maintenance had barely run by then.
3. **Matched rows.** Unit, B2g row 1: "After `cleanUp()`, size = min(N, cap) for cap 100 and 1000; per-version ≤ cap; heap flat at cap 100 while MAX_VALUE
   grows ~linearly". Sizes equal min(N, cap) in all 36 capped runs, and the per-version maximum is 100 or 1000 [observed: `analysis.txt`]. Cap-100 heap delta at N = 10^6 is
   379 KB vs 256 KB at N = 1000 (+123 KB). MAX_VALUE is 155.0 MB at N = 10^6, about 155 B per entry, 408× the capped run [observed]. Cluster, B3g row 1: stock rows hold at
   100 per version and the class deltas hold at +100/+400 from N = 100 to 20 000; uncapped rows = N and deltas = +N [observed: `r-*.txt`, `h-*.txt`].
   Stock end-state 44.8 KB vs uncapped 2.576 MB is 1/57.5, meeting B3f's ≤ 1/40.
4. **Excluded rows.** Unit row 2 (size > 100 after cleanUp): none of 18 cap-100 runs. Row 3 (cap-100 heap at 10^6 comparable to MAX_VALUE): 0.38 MB vs 155 MB.
   Row 4 (size far below min(N, cap)): sizes are exact. Row 5 (maxRaw grows without bound): levels off at ~16k (part 2). Row 6 (MAX_VALUE does not grow): it grows to N.
   Cluster row 2 (> 100 rows, or deltas growing from 1000 to 20 000): 100 rows and identical deltas. Row 3 (rows plateau, histogram grows): the four classes plateau
   exactly. Row 4 (uncapped stuck at 100): reached 20 000. Row 5 (rows < N below cap, or non-READY): 50 at N = 50, 0 non-READY. Row 6 (repeat increases rows): unchanged in both builds.
5. **Observed vs. inferred.** The only inferred statement is the cause of the transient overshoot (part 2). The verdict does not depend on it.
6. **Deviations and gaps.** S4-A1 to S4-A3 (pre-reading). There is no direct eviction counter: eviction is inferred from the count holding at the cap
   while more distinct keys were written, and the tracker has no other remover (A3.7). The transient overshoot was not measured on the node (the cluster reads after a 10 s settle).
   Byte sums cover the four B3d classes; adding the `ConcurrentHashMap$Node` deltas gives about 67.8 KB stock vs 3.32 MB uncapped, still within B3f's "order of" figures.
7. **Core question.** Yes. The tracker's retained entries and their heap follow the constant: 100 per version at the stock value, 1000 at 1000, N when uncapped. This holds in the
   unit tier (exact sizes, flat heap vs 155 MB uncapped) and on a real node (rows and class histograms flat at 100/400 vs +N uncapped). Usage stops at the cap
   once maintenance drains (parts 1, 3, 4). Before it drains, it can run ahead by up to about 16k entries (≈ 2–2.5 MB) on this 40-core node (part 2).

**Conclusion:** Unit B2g row 1 — confirmed. Cluster B3g row 1 — confirmed.

## 5. Self-check of run 1

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `logs/setup.log` javap lines (bipush 100 / ldc 1000000, both jar and classes); `flood-*.err` total 0 bytes; port/process checks in both `session.log` |
| 2. Readings | yes | `unit/results.txt` maxRaw values re-read; overshoot recorded, not hidden |
| 3. Matched row | yes | `analysis.txt` regenerated locally from the copied raw files; `cluster/stock/h-v4-20000.txt` PSMS 101 (100 + 1 baseline), `uncapped/h-all.txt` PSMS 23 001 |
| 4. Excluded rows | yes | every B2g/B3g row addressed above |
| 5. Observed vs. inferred | yes | one inferred statement, not load-bearing |
| 6. Deviations and gaps | yes | amendments pre-date readings (scripts and amended text written before `drive.sh` started; `driver.log` times) |
| 7. Core question | yes | dose-response across 100/1000/MAX (unit) and 100/10^6 (cluster) with positive controls moving |

### 5.2 Run 2?

**No** (2026-11-25). The conclusion rests on observed exact counts, the self-check settles every part, and the result neither refutes the case nor confirms a bypass.

## 6. Run 2

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** **true positive** (positive, caps; both tiers settled).

**Claim tested (B1):** the number of client-address entries the native-transport protocol-version tracker retains, and the heap they occupy, stop growing at
`DEFAULT_MAX_CAPACITY` (100) per protocol version no matter how many distinct client IPs connect; with the cap raised, the same workload makes them grow one per distinct IP.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g row 1 | caps | run 1 + self-check | 2026-11-25 |
| Cluster | Confirmed — B3g row 1 | caps | run 1 + self-check | 2026-11-25 |

**Note (bound is eventual):** before Caffeine's maintenance drains, the cache transiently held up to ~16k entries (≈ 160× the cap) under a tight single-thread
put loop. This is bounded and does not change the verdict. A real node only adds entries at connection-handshake rate (~3.5k/s here).

**Feedback filed:** section D of `case-amended.md` (outside the repo; not committed, per the task). Index row to set: stage-4 `Confirmed — caps (unit, cluster)`, Outcome class `TP`, sha256 `6e0fb423…bfa3`.
