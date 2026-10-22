# index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous — stage-4 results  <!-- file: results/index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous.md -->

> **Case:** [`index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous`](../../stage3-ai-deep-read/cases/index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous.md)
>
> **Status:** **Closed 2026-10-21 — unit Confirmed (caps), cluster Confirmed — caps only on some paths (bypass)** (estimate positive, matched). Line 341 sets the summary total to exactly F + kept·d ≤ pool (unit, 11/11 rows exact); on a node the resize task brings 808.7 MiB of summaries under 409 / 400 / 100 MiB and to the floor 6.3 MiB at 0, and RssAnon falls by the same bytes (within 1–3 %). Bypasses as the estimate said: new sstables add +202 MiB over a 100 MiB cap with no run, and `max_index_interval` forces 808.7 MiB at a 0 MiB cap. Cluster tier ran twice (runbook fix D3, a definition error in an audit amendment); self-check 93/93. No run 2.
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D. One results file per case file.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file. As filed (untracked, 2026-10-21): sha256 `068aceefe840d89b516cafaa805e695242b4fd79214c935d864fac19cf9c6c82`. After the step-0 audit amendments R1–R7 (dated 2026-10-21, in the file next to the text they change): `5ea57d51…`; then R4's appender wording corrected (additivity on, so `system.log` keeps the INFO lines; found while writing the harness, before any reading): **`5bc45c0d58fdd575b430537c561d50d4dfe94d830cbbd126af294e9d8e9a90b1`** (the audit freeze; **the unit tier ran on this version**). After runbook fixes D1–D2 (found by the cluster instrument checks before any run-1 cluster reading; they touch only B3c and B3e, B1 and B2f–B3g unchanged): `e62b1253…` (cluster attempt 1 ran on it; not counted, see D3). After runbook fix D3 (a definition error in R5's RSS-agreement row, independent of the readings; only that row changes): **`72266fd36376045df55fac0acc2da2d6f1522ff3038ed19b099a6d6b96c52941`, the version the counted cluster tier (attempt 2) ran on**. The file is not committed; repo HEAD `a74026e`. |
| **Harness** | [`harness/index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous/`](../harness/index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous/README.md), written 2026-10-21, not committed: `IndexSummaryCapacityProbeTest.java` (the filed B2e test + R1), `unit-run.sh`, `unit-analyze.py` (B2); `cluster-run.py`, `cluster-analyze.py` (B3); `selfcheck.py`. md5 of the node copy in `pc12:~/stage4-harness-run/isc.md5`, equal to the repo files. **Instrument checks (not readings):** shakedown1 (unit, 256 partitions: test compiles, `probe.out` whole, analyzer); shakedown2 (cluster, N = 300,000: harness bug H1); shakedown3 (all lifetimes, N = 300,000: found H2, D1, D2; `sjk` invoke and read work); shakedown4 (steps 5–6 only after D1/D2: 300,000 writes → 63,600,000 B = 300,000 × 212 B; force upsample 3; +100,000 → +20.2 MiB). |
| **Tiers and values** | Unit (B2): pool P in bytes, 11 values from 0 to 2·S_full under zero read rates (scenario A), 4 values under proportional rates (B), floor control C; repeated once. Cluster (B3): `index_summary_capacity` 4096 MiB · default (5 % of 8 GiB = 409 MiB, R3) · 400 · 100 · 0 MiB (0 twice), then `max_index_interval = 1` at 0, then step 6 (100 MiB, interval `null`, +1 M partitions). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-21 |

### 1.1 Design audit

Source spot-checks were made in the shared clone read-only (`cassandra-5.0.9`, `b5f2a54210`) and on the node's fresh clone `pc12:~/cassandra-isc`.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: native bytes of BIG index summaries (`IndexSummary.getOffHeapSize()`, JNA malloc). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach | Partly → Met | Unit: 11 pool values (bytes, as `IndexSummaryManager` passes them). Cluster: 4096 / 400 / 100 / 0 lacked the default (5 % of heap); **added** (R3). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | Unit: operand only, gap named (B2d). Cluster: RssAnon (B3d item 2), Summary.db bytes; NMT blind to JNA named. R4 adds a 2-s RssAnon sampler for a within-lifetime reading. |
| A. Core question | usage driven to the limit and past it | Met | Unit: pools from 0 to 2·S_full cross F and S_full. Cluster: S_full ≈ 809 MiB against 409 / 400 / 100 / 0. |
| A. Core question | positive control (negative-estimate file only) | n/a | Positive estimate. The file still has one (X = 4096 / P = 2·S_full). |
| B. Logic | each step says what it establishes | Met | B2h/B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f exact table (kept, T); B3f T ≤ X and > X − r_max, RssAnon = R4096 − (809 − T) ± σ. |
| B. Logic | every plausible outcome has a conclusions row | Partly | Unit: repeat disagreement and a non-monotone B had no row (**R2**). Cluster: "T does not fall", noise too large, floor control not moving, step 6 not overshooting, and the RSS "≈" were undefined (**R5**). Neither table mapped rows to verdict words (**R2, R5**). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met | Unit: `kept` under zero rates is exactly line 341's success count (every `isc` sstable is in `toDownsample` since the NaN target is 1 entry, `:183-188`, `:241`). Cluster had only the aggregate "downsample: N" INFO line; **R4** adds a TRACE appender for the per-sstable keep / re-sample lines of `:343` and `:278`. |
| B. Logic | alternative explanations and their controls | Met | Positive control (cap not binding), floor control C / step 5 (table params decide the floor), compaction off (`nonRedistributing` = 0), bloom filter and compression off, pre-touched fixed heap, noise repeat. |
| C. Specific | a human can follow it from the intro and §9a | Met | Header, A3, B1. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Met | B2e complete test; B3e commands. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | B2e step 3's `grep` meets fragmented stdout (**R1**); step 6 "optional", without a recorded T_trig or wait (**R6**); `system.log` accumulates across lifetimes (**R4** item 7); node detection by `pgrep -f` and `ulimit -n` 1024 on `pc12` (**R7**). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Unit test given in full; the cluster needs a sampler and a run script (step 1 work). Fresh clone `~/cassandra-isc` built (`ant build-test` 1 min 7 s). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Unit: 8 × 2048 × 8-byte keys, s = 5120 B, F = 1280 B, S_full = 40960 B; P from 0 to 81920. Cluster: 4,000,000 × (200 + 8 + 4) B = 848 MB = 808.7 MiB at `min_index_interval` 1, 30-ish sstables of ≈ 27 MiB (memtable 256 MiB); floor 1/128 → 6.3 MiB. Disk: Data ≈ 0.95 GB, Index ≈ 0.85 GB, commit log ≤ 8 GiB → < 12 GiB of 55 GB free on `/`. Memory: 8 GiB heap + ≈ 1 GiB native of 251 GiB. Load ≈ 1–3 min at 64 threads; 7 lifetimes × ≈ 3.5 min. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `Config.java:539-542`; `DatabaseDescriptor.java:866-876, 4136-4142`; `IndexSummaryManager.java:97-148, 184-187, 200-256, 285-289` (log text "memory pool size of {} MB"); `IndexSummaryRedistribution.java:100-160, 165-266, 327-356`; `IndexSummaryBuilder.java:294-314`; `IndexSummary.java:259-262`; `BigTableWriter.java:254`; `BigTableReader.java:598-620`; `Memory.java:60-80`, `MemoryUtil.java:81-84`; `SSTableReader.java:1640-1645`; `IndexSummaryManagerMBean.java`; `conf/cassandra.yaml:26, 395, 408, 431, 525, 611, 706, 797, 825, 939, 947, 960, 966, 981, 1023, 1090`; `jvm-server.options:128`. All as cited (line 254 vs 255 for the `IndexSummaryBuilder` construction in `BigTableWriter`, one off). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Harness test writes whole `PROBE` lines to `-Dprobe.out`; `NUM_PARTITIONS` overridable for the shakedown only | Applied 2026-10-21 (B2e) | stdout of a test JVM is fragmented by the logger (lesson H1 of `concurrent_writes`) |
| R2 | B2g: rows for repeat disagreement and non-monotone B; verdict mapping and Effect | Applied 2026-10-21 (B2g) | outcomes without a row; no verdict words |
| R3 | Add the default (empty → 409 MiB) to B3b's values, with its B3f row | Applied 2026-10-21 (B3b) | group A requires the default |
| R4 | RssAnon every 2 s (within-lifetime fall), a TRACE appender for `IndexSummaryRedistribution` (per-sstable line-341 outcomes), per-lifetime log offsets | Applied 2026-10-21 (B3d) | direct disallow evidence; a second RSS reading; accumulated logs |
| R5 | B3g: define T ≤ X, ≈ F, "RssAnon falls by ≈", σ; rows for "T does not fall", noise, RSS disagreement, floor control, step 6; verdict mapping and Effect fixed before the run | Applied 2026-10-21 (B3g) | ambiguous terms; outcomes without a row |
| R6 | Step 6 required, with T_trig, the second profile, a 120-s wait and the no-run check | Applied 2026-10-21 (B3e) | it tests A3 7b, part of the estimate |
| R7 | Environment: fresh clone `~/cassandra-isc`, `RUN=/tmp/isc-jason92`, `ulimit -n 100000`, node detection by `java … CassandraDaemon` | Applied 2026-10-21 (B3e) | node facts, no design change |
| S1 | A3 item 5's "total ≤ pool whenever remainingSpace ≥ 0" assumes the planned size (`avgEntrySize × entries`, `:244`) equals the real downsampled size; with variable-length keys they can differ, and upsamples are charged without `ceil` (`:238`) | Left for stage 3 | not load-bearing here: all keys of `isc.t` and of the unit table are fixed-length |
| S2 | Only the zero-read-rate path decides by line 341 alone; the keep band (A3 7d) with real read rates is untested on the cluster | Left for stage 3 | needs a read workload; scenario B covers the proportional path at unit level only |
| S3 | `BigTableWriter.java:255` → `:254` | Left for stage 3 | citation off by one |

**Agreement criteria** — only if run 2 is chosen.

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-10-21 (MDT): unit shakedown 15:44, unit run 1 15:45:54–15:46:27; cluster shakedowns 15:46–16:23; cluster attempt 1 16:23:54–16:46:29 (not counted, D3); **cluster attempt 2 (counted) 16:48–17:11** | not done |
| Node | `pc12` = `node1.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB); no other agent used it; the session ran on `pc07` and drove `pc12` over ssh. Loopback only (127.0.0.1; `pc12` has no LAN interface), non-default ports 17000 / 17001 / 19042 / 17199 as B3a. | — |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | — |
| JDK | openjdk 11.0.32.1 (2026-08-18) | — |
| Ant | 1.10.12 | — |
| Local clone | `pc12:~/cassandra-isc`, fresh clone of `cassandra-5.0.9` (`b5f2a54210d541339c2e7c17a794195cac0e67c2`), `ant build-test` 1 min 7 s (R7). Only untracked file: the harness test. | — |
| Case-file / harness commit | case file untracked (HEAD `a74026e`): unit on `5bc45c0d…`, cluster attempt 2 on `72266fd3…`; harness not committed (md5 in `pc12:~/stage4-harness-run/isc.md5`) | — |
| Storage for node data | `/tmp/isc-jason92` on local `/dev/sda3` (ext4, 55 GB free at the start; peak use ≈ 3 GB) | — |
| Node JVM | `MAX_HEAP_SIZE=8G HEAP_NEWSIZE=2G MALLOC_MMAP_THRESHOLD_=131072`, G1, `-XX:+AlwaysPreTouch` (conf default), `ulimit -n 100000` | — |
| Full logs | `pc12:~/stage4-logs/isc/`: `run1/unit/` (ant logs, junit XML, per-test logs, `rep{1,2}.probe`, `summary.txt`), `run1/cluster/` (attempt 2: `session.log`, `phases.json`, `rss-<life>.csv`, `system-<life>.log`, `isr-trace-<life>.log`, `stress-*.out`, `summary.txt`, `selfcheck.txt`), `run1-attempt1-cluster/` (attempt 1), `shakedown{1,2,3,4}/` | — |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| H1 | cluster shakedown2 (instrument check) | harness | `cluster-run.py` read a timestamp from a log slice that began at "Redistributing index summaries", so the regex found nothing (`TypeError`) after the first measurement. | Field dropped; the 2-s poll time of the "Redistributing" line is the pre-resize window's end (R4 item 5). | 2026-10-21, harness only | — |
| H2 | cluster shakedown3 (instrument check) | harness | The TRACE keep / re-sample counts covered every run in the lifetime (the 80-s wait holds a second scheduled run), so 3 sstables counted 6. | Counts are taken from the first run after the offset only; steps 5–6 pass the trace offset taken at the ALTER / manual invoke. | 2026-10-21, harness only | — |
| D1 | cluster shakedown3 (instrument check, before run 1) | B3c, B3e step 6 | `population: seq(1..N)` on `k` repeats keys: stress samples the population after `setSeed(seed ^ salt)` and `DistributionSequence` returns `start + next % N` (`Generator.java:51-55`, `DistributionSequence.java:41-46, 66-69`). 300,000 writes gave 267,461 summary entries (89 %); at 4 M, S_full would be ≈ 721 MiB, under R5's 728 MiB positive-control line. Derivable from source. | `population:` removed from `k` (identity defaults to `uniform(1..100B)`); step 6 uses `-pop seq=4000001..5000000` with the same profile. Shakedown4: 300,000 writes → exactly 300,000 × 212 B. B1, B3f, B3g unchanged. | 2026-10-21, dated runbook fix D1 in the case file | none (not committed) |
| D2 | cluster shakedown3 (instrument check, before run 1) | B3e step 5 | `ALTER TABLE isc.t WITH max_index_interval = 1` is refused: "max_index_interval must be greater than or equal to min_index_interval (128) (got 1)"; an ALTER naming only `max_index_interval` is validated against the default min (128), not the table's 1. | `WITH min_index_interval = 1 AND max_index_interval = 1` (restore: `… = 1 AND … = 128`). Shakedown4: force upsample 3, T back to S_full. B3f/B3g unchanged. | 2026-10-21, dated runbook fix D2 | none |

| D3 | cluster run 1, attempt 1 (a reading) | B3g, amendment R5 | R5's RSS-agreement row compared ΔR_w with "0.5 × ΔT" without saying which ΔT. In a lifetime whose run changes nothing (X = 400 right after the default 409 had already brought T to 393 MiB; foreseeable before the run: the audit noted 400 after 409 may shrink nothing), T_before − T_after = 0 and noise alone decides the side: ΔR_w = −0.4 MiB tripped the row and the analyzer returned *Not confirmed*, while every other row read as row 1. | Dated fix D3: ΔR_w is compared with 0.5 × (T_before − T_after) of its own lifetime, only where the run changed T by ≥ 16 MiB; elsewhere ΔR_w must lie within 3σ of 0. B3f and every other row unchanged. The harness-only check "line 341 both outcomes at every X" had the same flaw and now expects no re-sample where nothing changed. **The cluster tier restarted from its beginning (attempt 2, counted); attempt 1 is kept, not counted** (`run1/cluster-attempt1/`, full logs `pc12:~/stage4-logs/isc/run1-attempt1-cluster/`). | 2026-10-21, dated runbook fix D3 | none |
| H3 | self-check test on attempt 1 | harness (`selfcheck.py`) | The unit cross-check looked for the `PROBE` lines in the junit XML, which holds no stdout in this build; it matched 1/17 by accident. | The cross-check compares `probe.out` with the `[main] SubstituteLogger` `PROBE` lines of the ant log (the second capture path), line for line. | 2026-10-21, harness only | — |

The cluster tier ran from its beginning after D1–D2 (attempt 1) and again after D3 (attempt 2, the counted run). The unit tier had no defect.

## 4. Run 1

**Scope:** unit tier (B2, 2048 partitions, twice) on case-file version `5bc45c0d…`; cluster tier (B3) attempt 2 on `72266fd3…`:
L0 load (4,000,000 partitions) · L1 4096 · L2 default (409) · L3 400 · L4 100 · L5 0 · L6 0 + step 5 · L7 step 6. Each lifetime is a
fresh node start. **Command logs:** `index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous/run1/unit/summary.txt`
and `…/run1/cluster/session.log`. Excerpts below are in `run1/`; full logs on `pc12:~/stage4-logs/isc/run1/`.

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, `rep1.probe`, `rep2.probe`, `ant-probe-lines.txt`). Setup: s = 5120, m = 160, F = 1280, d = 4960,
S_full = 40960 B, exactly as B2f.

| Test or assertion | Result | Evidence |
|---|---|---|
| junit, both runs | 1 test, 0 failures, 0 errors (17 s, 15 s) | `summary.txt` |
| Scenario A (zero read rates), P = 0 · 1279 · 1280 · 6239 · 6240 · 16159 · 16160 · 36000 · 40959 · 40960 · 81920 | kept = 0 · 0 · 0 · 0 · 1 · 2 · 3 · 7 · 7 · 8 · 8 and T = 1280 · 1280 · 1280 · 1280 · 6240 · 11200 · 16160 · 36000 · 36000 · 40960 · 40960 — **every row equal to the B2f table**; T ≤ P for every P ≥ F; T = F > P for P < F; equality at P = F + d (line 341's `<=`) | `rep1.probe` |
| Scenario B (rates 10…80), P = 20480 · 10240 · 5120 · 1280 | T = 20480 · 10240 · 5120 · 1280 (T = P exactly; within F ≤ T ≤ P + s/4 + F); strictly decreasing; levels rise with read rate (14 … 128) | `rep1.probe` |
| Positive control (P = 2·S_full) | T = 40960 = S_full, all levels 128 | `rep1.probe` |
| Control C (`max_index_interval` = 8, P = S_full/4) | T = 40960, all levels 128 | `rep1.probe` |
| Repeat | rep2 identical to rep1, line for line | `rep2.probe`, `summary.txt` |

**Cluster tier** (attempt 2; `run1/cluster/summary.txt`, `resize-lines.txt`, `phases.json`). T = the first "Completed resizing" of the lifetime;
R = median RssAnon of five samples 30–70 s after it; ΔR_w = within-lifetime fall (R4); trace = TRACE lines for `isc/t` in the first run
(kept by line 341 / re-sampled). 31 `isc.t` sstables; r_max = 26.19 MiB.

| Capacity | Observable | Reading | Evidence |
|---|---|---|---|
| load | stress | 4,000,000 partitions, 0 errors, 104,240 op/s | `stress-results.txt` |
| 4096 | pool line / T / trace | 4096 MB; T = 808.716 MiB (`tablestats` isc 848,000,000 B = 4 M × 212 B); 31 kept / 0 re-sampled | `resize-lines.txt`, `summary.txt` |
| 4096 | RssAnon R4096 | 9785.2 MiB (8 GiB pre-touched heap included) | `phases.json` |
| default | pool line / T / trace | **409 MB**; T = 393.706 MiB (≤ 409, > 409 − r_max); downsample 16; 15 kept / 16 re-sampled | `resize-lines.txt` |
| default | RSS | R = 9358.5 (fall 426.6 vs ΔT 415.0); ΔR_w = 417.7 vs T_before − T = 415.0 | `summary.txt` |
| 400 | T / trace | T = 393.706 (unchanged: the 409 state already fits); 15 kept / 0 re-sampled | `resize-lines.txt` |
| 400 | RSS | R = 9363.3 (fall 421.8 vs ΔT 415.0); ΔR_w = −0.9 vs 0 | `summary.txt` |
| 100 | T / trace | T = 82.617 MiB (≤ 100, > 100 − r_max); 3 kept / 12 re-sampled (16 already at floor) | `resize-lines.txt` |
| 100 | RSS | R = 9056.1 (fall 729.1 vs ΔT 726.1); ΔR_w = 312.9 vs 311.1 | `summary.txt` |
| 0 (a) | T / trace | T = 6.321 MiB (≈ F = 808.7/128 = 6.32; above the cap 0); 0 kept / 3 re-sampled | `resize-lines.txt` |
| 0 (a) | RSS | R = 8981.3 (fall 803.9 vs ΔT 802.4); ΔR_w = 76.3 vs 76.3 | `summary.txt` |
| 0 (b) | noise | T = 6.322; R = 9004.1 → **σ = 22.8 MiB** (≤ 0.25 × 802 = 201) | `summary.txt` |
| 0 + `min = max_index_interval = 1` (step 5) | T / RSS | force upsample 31; T = 808.716 MiB at pool 0; R = 9832.6 (back to R4096 + 47) | `resize-lines.txt`, `summary.txt` |
| 100, interval `null` (step 6) | manual run | T_trig = 82.617 MiB (≤ 100); 3 kept / 28 re-sampled | `resize-lines.txt` |
| 100, interval `null` (step 6) | +1,000,000 partitions, flush, 120 s | T_after = 284.796 MiB (JMX `MemoryPoolSizeInMB`; `tablestats` 298,629,560 B) = T_trig + 202.18 MiB (= 1 M × 212 B); **no "Completed resizing" line** after the manual run | `session.log`, `summary.txt` |
| every lifetime | Summary.db total | = T + 13 KB (file headers) at every state | `summary.txt` |

Attempt 1 (not counted, D3) read the same to within noise: T 808.716 / 393.140 / 393.140 / 81.601 / 6.323; falls 413.8 / 423.8 / 732.3 /
806.0; σ = 11.5; step 6 81.602 → 283.781 (`run1/cluster-attempt1/summary-D3.txt`).

### 4.2 Conclusion and logic

1. **Validity.** Unit: both runs passed, the setup line equals B2f's arithmetic, both controls held [observed: `run1/unit/summary.txt`].
   Cluster: the pool line of every lifetime shows the value set (4096 / 409 / 400 / 100 / 0 / 0 / 100), every lifetime has a
   "Completed resizing" line, the positive control holds (T4096 = 808.716 ≥ 728 MiB), no compaction ran (no `nonRedistributing` charge:
   Beginning T equals the previous lifetime's T throughout), bloom filter and compression off (B3c profile in `session.log`), heap
   fixed and pre-touched [observed: `run1/cluster/summary.txt`, `resize-lines.txt`, `session.log`]. The limit was reached and passed:
   S_full = 808.7 MiB against pools of 409, 400, 100 and 0. Valid.
2. **Readings.** Nothing contradicts. Unit T equals the B2f table exactly. On the cluster the 400 lifetime changed nothing because the
   default lifetime (409) had already brought T to 393.7 [observed: `resize-lines.txt`]; this is B3f's own relation (T ≤ 400 and >
   400 − r_max) and was foreseen. σ = 22.8 MiB is small against the 400–800 MiB effects [observed: `summary.txt`].
3. **Matched row.** Unit B2g row 1, "Scenario A rows match `kept`=kPred and T=F+kPred·d, with T ≤ P for every P ≥ F — Line 341 enforces the
   pool exactly", with row 4 (T = F > P below F), scenario B within bound, both controls and an identical repeat: **Confirmed** by R2's
   mapping [observed: `run1/unit/rep1.probe`, `rep2.probe`]. Cluster B3g row 1, "T ≤ X for X ∈ {400, 100}, T ≈ S_full at 4096, and
   RssAnon falls by ≈ (809 − T) — Claim confirmed: the cap governs real native usage after a run": T ≤ X at default / 400 / 100;
   T4096 = 808.716; across-lifetime falls 426.6 / 421.8 / 729.1 / 803.9 MiB against ΔT 415.0 / 415.0 / 726.1 / 802.4 (each ≥ 0.5 × ΔT, and
   within max(3σ, 0.15ΔT) of it); plus row 6 (T ≈ F at X = 0), the floor control moved (row 7), and step 6 rose above the cap with no
   run (row 8): **Confirmed** by R5's mapping [observed: `run1/cluster/summary.txt`].
4. **Excluded rows.** Unit row 2 (T > P for P ≥ F, or B above P + s/4 + F): no row [observed: `rep1.probe`]. Row 3 (T unchanged as P
   falls): T takes 6 values [observed]. Row 5 (off by one): no row off. Rows 6/7 (controls fail): both held. R2 repeat row: identical.
   Cluster row 2 (T > X): largest T − X is −6.3 MiB (400) [observed]. "T does not fall" (R5): T(100) = 82.6 ≪ 0.9 × 808.7. Row 3 (RSS
   does not fall): every fall ≥ 0.98 × ΔT. Row 4 (positive control): 808.716. Row 5 (no run): a run in every lifetime. Noise row: σ =
   22.8 ≤ 201. RSS-disagreement row (D3): the within-lifetime fall agrees at default / 100 / 0 (417.7 / 312.9 / 76.3 vs 415.0 / 311.1 /
   76.3), and at 400 |ΔR_w| = 0.9 ≤ 3σ. Floor-control "did not move" row: T rose to 808.7 > 2 × 6.3. Step-6 "not seen" row: T_after =
   284.8 > 100 [observed: `summary.txt`, `selfcheck.txt`].
5. **Observed vs. inferred.** Inferred: (a) that the RssAnon falls are the freed summary memory rather than another native consumer —
   [inferred: the falls equal ΔT within 1–3 % in two independent readings (across and within lifetimes), and step 5 reverses the fall
   (+828.5 MiB of RssAnon, 9004.1 → 9832.6, for +802.4 MiB of summaries) with nothing else changed]; (b) that the TRACE "Using leftover space to keep" lines are line 341's
   `true` branch — [inferred from source: the message is at `IndexSummaryRedistribution.java:343`, inside the `if` at `:341`].
6. **Deviations and gaps.** Cluster tier ran twice (D3; attempt 1 kept, not counted, same readings within noise). The unit tier reads
   the operand only (named in B2d). Only the zero-read-rate path was run on the cluster, so the keep band (A3 7d) and the proportional
   targets are tested at unit level only (scenario B). One node on loopback; `pc12` has no LAN (no effect: single node).
7. **Core question.** The hypothesis (B1) is that after a redistribution run the BIG summaries' total, and the node's native memory,
   is at most `index_summary_capacity` down to the floor F. The unit tier shows line 341 sets the total to exactly F + kept·d ≤ P for
   every pool (parts 1, 3). The cluster tier shows the real resize task brings the total under 409 / 400 / 100 MiB and to F at 0, and
   RssAnon falls by the same bytes (parts 3, 4). The cap holds only at resize time. Between runs new sstables bypass it: +202 MiB with
   no run. Table parameters can also force usage above it (step 5) (parts 3, 4). **Usage follows the constraint, and the constraint caps it at each run.**

**Conclusion (one line):** unit B2g row 1 — **confirmed**; cluster B3g row 1 (with rows 6, 7, 8) — **confirmed**, bypass as recorded (between runs; table parameters).

## 5. Self-check of run 1 — AI

`selfcheck.py` (`run1/selfcheck.py`, output `run1/cluster/selfcheck.txt`) re-parses the raw files: the PROBE lines in the ant log
(the logger's capture path) against `probe.out`; the B2f table typed in from the case file rather than taken from the test's own
values; per lifetime, the `system.log` slice (pool line, every run's Beginning and Completed T), the TRACE slice split per run,
the 2-s RssAnon csv at the sample times (a second reader of R), and `session.log`'s JMX and stress output. **93 / 93 checks hold.**

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | pool line per lifetime equals the value set (7 checks); load wrote 4,000,000 partitions, 0 errors; Beginning T of each lifetime equals the last T of the previous one (no compaction, no hidden change) — `system-*.log`, `stress-load.out` |
| 2. Readings | yes | every Completed T in the raw slices equals the script's T; later runs in a lifetime leave T unchanged; trace counts equal the script's; the 2-s sampler agrees with R within 32 MiB in every lifetime |
| 3. Matched row | yes | unit: all 11 A rows equal the typed-in B2f table, B within bound and decreasing, C and the positive control at S_full, repeat identical; cluster: T ≤ X + 64 KiB at default / 400 / 100 from the raw lines; T0 = 6.32 with no keep |
| 4. Excluded rows | yes | RSS falls ≥ 0.5 ΔT by both RSS readers; σ ≤ 0.25 ΔT by both; step 5 run force-upsampled 31 and T rose; step 6: one Completed line only, JMX 82.6 → 284.8 |
| 5. Observed vs. inferred | yes | (a) within-lifetime falls re-derived from the csv: 417.7 / 312.9 / 76.3 vs 415.0 / 311.1 / 76.3; step 5 +828.5 MiB re-read; (b) the TRACE message text and `:343` re-read in the pinned source |
| 6. Deviations and gaps | yes | attempt 1 re-checked with the same script: 93 / 93 (`pc12:~/stage4-logs/isc/run1-attempt1-cluster/selfcheck-test.txt`); its readings agree with attempt 2 within σ |
| 7. Core question | yes | the steps from reading to answer follow B1 → B2g/B3g → R2/R5 mapping; the Effect follows R5's pre-run rule (Confirmed + step 6 overshoot → `caps only on some paths (bypass)`) |

### 5.2 Run 2?

**No** — 2026-10-21. The conclusion rests on observed readings with two independent RSS readers; the unit tier is exact and
deterministic; both cluster attempts gave the same row.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive (best-effort, enforced at resize time). (Stage 3's earlier `predicted-negative.md` §9 entry for the same lines estimated negative.)

**Claim tested (B1):** after a redistribution run, the total `getOffHeapSize()` of all BIG index summaries, and the node's corresponding
native memory, is at most `index_summary_capacity`, whenever the capacity is at or above the floor F; below F the total settles at F.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (+ row 4; controls; identical repeat) | caps | run 1 + self-check | 2026-10-21 |
| Cluster | **Confirmed** — B3g row 1 (+ rows 6, 7, 8) | **caps only on some paths (bypass)**: caps at each resize run, down to the floor; new sstables escape until the next run (+202 MiB over a 100 MiB cap with no run), and table parameters force usage above it (808.7 MiB at a 0 MiB cap) | run 1 (attempt 2) + self-check | 2026-10-21 |

**Feedback filed:** the case file's section D (2026-10-21; not committed); after it the case file's sha256 is `3c2498d3ef77398b7788d74de4e9e80158c4e601584c7f88699a4701641f8619` (for `_INDEX.md` §4). The amendments R1–R7 and runbook fixes D1–D3 are dated in
the file.
