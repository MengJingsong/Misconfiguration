# max_compaction_flush_memory_in_mb-getmode-maxmembytes--autonomous — stage-4 results

> **Case:** [`max_compaction_flush_memory_in_mb-getmode-maxmembytes--autonomous`](../../stage3-ai-deep-read/cases/max_compaction_flush_memory_in_mb-getmode-maxmembytes--autonomous.md)
>
> **Status:** self-checked; verdict filed (2026-10-27)
>
> **Outcome class:** true positive (estimate positive; effect `caps only on some paths (bypass)`, which the README counts as `caps`). The cluster tier refuted the "live heap stays near M" part of B1 at M = 1 (unbounded flush queue), see section 8.
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); the feedback section of the case file is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Case file in the working tree at repository commit `68f9c3c` plus uncommitted amendments (the orchestrator commits). Original sha256 `0d232a9562361ec8e442a1ccaa562e3350791e6fefb6d7047dac2974a5011020`; sha256 after the audit's amendments (B1a, inline notes in B2b/B2c/B2f/B2g/B3b/B3c/B3f/B3g, section B5): **`e8b3e12937841c504a9594993ae24f87e463a7f004790e408282095ce38e87fc`** (frozen 2026-10-27 before the unit run and the cluster run). Frozen tables at that version: B2f-g (from `**B2f.` to before `**B2h.`) sha256 `ab7de4b47c5eb5277e97afb020ab21f54e57ebff0e56d0be7f44938030c24e3b`; B3f-g (from `**B3f.` to before `**B3h.`) sha256 `cb96824bee32d0bbb879b1e9a3c28dec8493a85de67654784bc7533963de2960`. The file's sha256 changes after the run because section D takes the feedback (final sha256 after the section D feedback, 2026-10-27: `f10e4c7ea5b5603fdedbec15b930af4175bc07a9846f35f6c68cfc770cf1b5c8`). |
| **Harness** | `harness/max_compaction_flush_memory_in_mb-getmode-maxmembytes--autonomous/` (uncommitted; the orchestrator commits): `SanityCapProbeTest.java`, `unit-run.sh`, `analyze_unit.py`, `cluster-run.py`, `analyze_cluster.py`, `selfcheck.py`, `loader.py`, `cql.py`, `PoolSampler.java` (the last four and most of `cluster-run.py` are the sibling's, with the arm list, expectations and port-independent paths changed). Checks, not readings: `py_compile` of every script; unit instrument check at N = 20,000 (analyzer 0 fails, the `getMode` table printed as expected); cluster shakedown with 300,000 rows and arms 102400, 1, 102401 (65 segment lines at 1 MiB, `reverting` error line only in the 102401 arm, node stopped cleanly). Logs `pc29:~/stage4-logs/gm/unit-shake`, `shake`. |
| **Tiers and values** | Unit: `IndexMode.getMode` for 10 option strings; writer arms COMPACTION 102400 / 102401 / default / 1 MiB and FLUSH with 1 MiB, N = 1,000,000 int32 terms. Cluster: 3,000,000 rows, one sstable, arms 102400, 1, 16, 128, default, 102401, 102400 in series on one node, heap 3 GiB. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: heap bytes of the active SASI builder; the line-190 check itself bounds the configured value only (B1a added). |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b 1/8/64/absent/0/102401 and B3b 1/16/128/absent; amended to add 102400 and 102401, the two sides of line 190. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B3d: forced-GC class histograms and JMX heap; the estimate is a hand-coded counter (real ≈ 1.8 × estimate in the sibling). Gap named in the Estimate line. |
| A. Core question | usage driven to the limit and past it | Not met as written | B2c N = 200,000 terms (47 MB) never reaches the 161 MB default, so 102401 (reset) cannot be told from 102400 (passed). Fixed: N = 1,000,000 (B5.2). Cluster 672 MB of estimate passes every cap but 102400 (B5.4). |
| B. Logic | each step says what it establishes | Met | A3, B2e, B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | B2f's 102401 parenthetical was garbled and the cluster counts did not include the tail flush; restated (B5.3, B5.5). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | No row for the pass/reset boundary, for the overflow wrap, or for an OOM at the uncapped arm: added. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Cut counts and estimate at each cut (unit); `Flushed index segment` lines and histogram ordering (cluster). |
| B. Logic | alternative explanations and their controls | Met | FLUSH arm, default arm, 102400 arms first and last (B2h/B3h). |
| C. Specific | a human can follow it from the intro and §9a | Met | A3, B1 (plus B1a). |
| C. Specific | an AI can run B2a-e/B3a-e without re-deriving the code path | Partly | Test construction left open ("not verified"); fixed by the harness and B5.2. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | CONTAINS text layout and JVM option file names unverified; replaced by the sibling's int/SPARSE layout and the `MAX_HEAP_SIZE` environment variable (B5.4, B5.6). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Listed as step-1 work; the sibling's harness reused. |
| D. Runnable | workload arithmetic reaches the limit | Partly | See the A row above; after B5 all arithmetic recomputed (n = ceil(limit/224): 719,024; 4682; 599,187; 74,899). Disk: index 0.32 GB, 54 GB free on `/`. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `IndexMode.java:58-60,65,186-195`, `PerSSTableIndexWriter.java:247,250,368`, `ColumnIndex.java:79`, `OnDiskIndexBuilder.java:182,194,253-254` re-read in `cassandra/cassandra-5.0.9`; no wrong line. Stale text at `IndexMode.java:60,:192` confirmed (default is 0.15 GiB). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Add sub-claim B1a (line 190 boundary) | Applied 2026-10-27 (B1a, B5.1) | the file's named check is a sanity cap; B1 is about the sibling's enforcement site |
| 2 | N = 1,000,000; arms 102400/102401/default/1/FLUSH; getMode table | Applied (B5.2, B5.3) | reach the default cap |
| 3 | Cluster: int/SPARSE layout, arms 102400,1,16,128,def,102401,102400, heap 3 GiB, new counts and rows | Applied (B5.4, B5.5, B5.6) | calibration and the boundary |
| 4 | `ps -eo cmd`, grep for CassandraDaemon, instead of `pgrep -f` | Applied (B5.7) | README safety rule |
| 5 | Stale 1G comment/log text at `IndexMode.java:60,:192` | left for stage 3 | does not affect the claim |

Agreement criteria: run 2 not chosen.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit 21:11-21:12Z; cluster 21:12-21:28Z) |
| Node | `pc29` (`node3.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`), 40 cores, 251 GiB |
| OS / kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Ant 1.10.12 |
| Local source copy | `~/s4-gm`, a copy of `~/cassandra-run1` (itself made by `copy-source.sh` from `cassandra/cassandra-5.0.9/`; `git describe` = `cassandra-5.0.9`; `ant build-test` BUILD SUCCESSFUL) at repository commit `68f9c3c` |
| Case-file / harness commit | untracked at run time (sha256 in section 1); harness uncommitted. Harness file checksums: `run1/unit/harness.md5` |
| Storage | local `/dev/sda3` (54 GB free), node data `~/s4-gm-data/cl` (removed after the run); nothing under `/proj` |
| Full logs | `pc29:~/stage4-logs/gm/` (`run1-unit/`, `run1-cl/`; `unit-shake`, `shake` are instrument checks, not readings) |

Ports: JMX 7332, native 9354, storage 7032, loopback 127.0.32.1.

## 3. Runbook defects

None stopped a run. All changes were audit amendments made before the freeze (B1a, B5.1-B5.8). One harness note: the cluster `PATS` count for `reverting to default` is 2 per 102401 index creation (logged once by `validateOptions`, once by the `ColumnIndex` constructor), so the analyzer tests `>= 1`.

## 4. Run 1

**Scope:** unit tier (getMode table + 5 writer arms, N = 1,000,000) and cluster tier (3,000,000 rows, one sstable of 54,004,969 B, seven index builds in series, heap 3 GiB). **Command logs:** `max_compaction_flush_memory_in_mb-getmode-maxmembytes--autonomous/run1/unit/session.log`, `run1/cluster/session.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/getmode.csv`, `unit-results.csv`, `unit-cuts.csv`; `analysis.txt`: 61 PASS, 0 FAIL)

| Test or assertion | Result | Evidence |
|---|---|---|
| `getMode` bytes for absent / 0 / 1 / 8 / 64 / 102400 / 102401 / -1 / Long.MAX / abc | 161061273 / 0 / 1048576 / 8388608 / 67108864 / 107374182400 / 161061273 / -1048576 / -1048576 / NumberFormatException | `getmode.csv` |
| `reverting` error lines | 1 for 102401 only | `getmode.csv` |
| comp-102400: cuts, max estimate | 0, 224,000,000 | `unit-results.csv` |
| comp-102401 and comp-default | 1 cut each, at add 719,024, estimate 161,061,376 (= limit + 103 ≤ limit + 224) | `unit-cuts.csv` |
| comp-1 | 213 cuts, estimate 1,048,768 at each (n × 224) | `unit-cuts.csv` |
| flush-1 (FLUSH, option 1 MiB) | 0 cuts, max estimate 224,000,000 | `unit-results.csv` |
| `Flushed index segment` logs, comp-102400 / 102401 / default / 1 / flush-1 | 0 / 2 / 2 / 214 / 0 | `unit-results.csv` |
| segment files before complete = cuts; 0 after; final index 1,000,000 terms in every arm | as stated | `unit-results.csv` |
| heap delta of the active builder / estimate (indicative) | 1.79 (comp-102400), 1.78, 1.78, 2.25 (1 MiB builder), 1.79 | `analysis.txt` |

**Cluster tier** (3,000,000 rows, index file 322,805,532 B in every arm, no OOM, no failure line; `run1/cluster/analysis.txt`, `summary.json`)

| Arm | Cap MiB | `Flushed index segment` (predicted) | Peak live excess, histogram (MB) | max `OnDiskIndexBuilder` instances | max SASI-General pending | max old gen after GC (MB) | build (s) |
|---|---|---|---|---|---|---|---|
| a1 | 102400 | 0 (0) | 1500 | 2 | 0 | 1617 | 60 |
| a2 | 1 | 641 (641) | 939 | 512 | 503 | 1032 | 59 |
| a3 | 16 | 41 (41) | 327 | 11 | 5 | 415 | 35 |
| a4 | 128 | 6 (6) | 1057 | 5 | 0 | 1145 | 42 |
| a5 | default 153.6 | 5 (5) | 1195 | 5 | 0 | 1284 | 44 |
| a6 | 102401 | 5 (5), `reverting` error line x2 | 1160 | 5 | 0 | 1250 | 44 |
| a7 | 102400 | 0 (0) | 1493 | 2 | 0 | 1599 | 58 |

Frozen comparisons: peak ordered 1 < 16 < 128 < default < 102400: **FAIL** (939 vs 327); peak(102400)/peak(1) > 5: **FAIL** (1.6); peak(102401) within 25% of default: PASS (0.97); peak(102400) ≥ 1.10 × peak(102401): PASS (1.29); two 102400 arms within 10%: PASS (1500 vs 1493). Evidence: `analysis.txt`, `histo-a*.jsonl`, `pool-every4th.csv`, `segments-a*.txt`.

### 4.2 Conclusion and logic

1. **Validity** — valid. The default cap was crossed (5-6 segment lines) and the 102400 arms built the whole index in memory [observed: `segments-a1-102400.txt`, `analysis.txt`]. Hold-fixed: heap 3 GiB, one sstable, same data, same mode [observed: `node-cmdline.txt` `-Xms3G -Xmx3G`; `summary.json` `data_files`; identical index size in all arms]. Unit estimates are exactly n × 224 [observed: `unit-cuts.csv`].
2. **Readings** — the 1 MiB arm is the unusual one: 641 segment lines (as predicted), but 512 builder instances alive at once and 503 tasks pending in the SASI-General executor, and a peak excess of 939 MB, 63% of the uncapped arm and 2.9 times the 16 MiB arm [observed: `histo-a2-1.jsonl`, `pool-every4th.csv`, `analysis.txt`]. The build also took 59 s against 35 s at 16 MiB [observed: `summary.json`].
3. **Matched row** — Unit: B2g row 1 ("max estimate stays under `M*1048576 + one add`; segment count falls as M rises; FLUSH shows none") and the added B1a rows (102400 passes, 102401 equals default, overflow negative) [observed: `unit-results.csv`, `unit-cuts.csv`, `getmode.csv`]. Cluster: B3g row 2 ("segment count scales with M but peak builder bytes do not, or exceed M by a large multiple: the estimate does not track real heap; claim refuted for actual usage") for the M = 1 arm, and the added B3g row for 102401/102400 (B1a confirmed on a node: 5 segments and 1160 MB against 0 segments and about 1500 MB) [observed: `analysis.txt`].
4. **Excluded rows** — "segment count independent of M": no (0 / 641 / 41 / 6 / 5). "Memtable flush segment count changes with M": not exercised on a node (the unit FLUSH arm shows none) [observed: `unit-results.csv`]. "No segments for any M": no. "102401 shows 0 segments like 102400": no (5 vs 0). "OOM at the uncapped arm": no [observed: `errors-a1-102400.txt` empty]. B3g row 1 (all scale as predicted) is excluded by the 1 MiB reading (939 > 327 MB), though it holds for 16 → 128 → default → 102400 (327 < 1057 < 1195 < 1500).
5. **Observed vs. inferred** — inferred: that the 1 MiB overshoot is the executor queue (many full builders waiting for 8 flush threads while the producer outruns them). Observed: 512 builder instances and 503 pending tasks at the peak. Not observed: the lifetime of each queued builder, or whether the same happens at 8 MiB (the sibling's 8 MiB arm showed pending 0 and peak 77 MB with the same data). Inferred: the unit FLUSH arm stands for the memtable flush path (direct constructor with `OperationType.FLUSH`, not a real memtable flush).
6. **Deviations and gaps** — layout changed to int/SPARSE (B5.4); writer built directly in the unit tier (B5.2); heap 3 GiB (B5.6); only one run at M = 1, so its variance is unmeasured (the two 102400 arms agree within 0.5%); the peak is from forced-GC histograms, so garbage is excluded; the cluster FLUSH path was not run; the overflow value was checked at `getMode` only, never through a writer or a node.
7. **Core question** — At the entry line, `getMode` keeps any value up to 107374182400 B and replaces anything above by 161061273 B [observed: `getmode.csv`]; so 100 GiB is itself no cap on a 3 GiB heap (a7: 0 segments, 1.5 GB live), and 102401 behaves as the default (a6 ≈ a5). The configured value does bound the active builder's estimate exactly (limit + at most 224, unit) and the segment count follows it on a node (0, 641, 41, 6, 5). Live heap follows the cap from 16 MiB up (327, 1057, 1195, about 1500 MB) but not at 1 MiB, where the queue of full builders held 939 MB: the cap bounds each builder, not the sum of builders waiting to be flushed.

**Conclusion (one line):** Unit: B2g row 1 plus B1a rows — confirmed. Cluster: B3g row 2 at M = 1 (refuted for actual usage there), B1a confirmed; Effect: caps only on some paths (bypass: unbounded flush queue).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parses `unit-results.csv`, `unit-cuts.csv`, `getmode.csv`, `segments-*.txt`, `errors-*.txt`, `histo-*.jsonl`, `pool.csv`, `summary.json` independently of the analyzers (`run1/cluster/selfcheck.txt`). Its two "DOES NOT HOLD" lines are the frozen ordering predictions (peak order, post-GC order across all arms) that the 1 MiB reading contradicts; they are the result, not a defect of the check. I also re-read the pending-task and instance maxima per arm from `pool.csv` and `histo-*.jsonl` with a separate snippet (pending 0 / 503 / 5 / 0 / 0 / 0 / 0; instances 2 / 512 / 11 / 5 / 5 / 5 / 2).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `node-cmdline.txt`: `-Xms3G -Xmx3G`, JMX 7332; `summary.json` one data file; `selfcheck.txt`: index size equal in all arms; `errors-*.txt`: only the two expected `reverting` lines (102401). |
| 2. Readings | yes | peaks recomputed from `histo-*.jsonl` (1500, 939, 327, 1057, 1195, 1160, 1493 MB); 641 lines counted in `segments-a2-1.txt` header ("lines: 642" = 641 flushes + the final `Index flush to` line). |
| 3. Matched row | yes | unit cut counts and estimates recomputed in `selfcheck.txt`; getMode table in `getmode.csv`. |
| 4. Excluded rows | yes | segment counts differ across caps; 102401 ≠ 102400; the FLUSH arm cut 0 times with the 1 MiB option. |
| 5. Observed vs. inferred | yes, with a gap | queue explanation inferred from observed pending and instance counts; no per-builder lifetime. |
| 6. Deviations and gaps | yes | listed above. |
| 7. Core question | yes | steps follow B1/B1a: ceiling (estimate) follows the knob; segment cuts fire; heap follows except through the queue. |

### 5.2 Run 2?

**No** (2026-10-27). The decisive readings are exact counts and ordered sizes from independent files, and the one surprising reading (M = 1) is a refutation of a frozen heap-ordering prediction whose mechanism (queue) is already in A3c of the case file. A repeat of M = 1 alone would sharpen its variance but not change the verdict row; left as a recommended follow-up.

## 6. Run 2

Not done (5.2).

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive; effect caps with a recorded bypass).

**Claim tested:** (B1 + B1a) a compaction/index-build writer flushes its builder whenever the estimate reaches `M × 1048576`, so the live builder estimate and the live builder heap stay near or below M MiB (plus one add), segment count rises as M falls, FLUSH is unaffected, and the entry line at `IndexMode.java:190` keeps values up to 100 GiB and resets larger ones to the default. "Confirmed" means this held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g row 1 and the added B1a rows | caps (builder estimate, exactly; 100 GiB passes, 102401 resets to default; FLUSH ignores the option) | run 1 + self-check | 2026-10-27 |
| Cluster | B3g row 2 at M = 1 — Refuted for actual heap there (peak 939 MB, 512 builders alive, 503 tasks queued); rows for M ≥ 16 and for B1a — Confirmed | caps only on some paths (bypass: the unbounded flush queue lets small caps pile up full builders) | run 1 + self-check | 2026-10-27 |

**Positive control:** n/a for a positive file; the 102400 arms (a1 and a7, 1500 and 1493 MB) are the no-effective-cap control.

**Flags:** (1) the sanity cap is 100 GiB, 33 times the 3 GiB test heap, so on any real heap line 190 itself is never the binding limit; it only rewrites an absurd value to 0.15 GiB. (2) The overflow value `9223372036854775807` makes `getMode` return -1048576 (passes the strict `>`), so a writer would flush on every add (every estimate ≥ a negative limit); this is more restrictive, not a path around the cap, and was not run through a writer. (3) Stale text at `IndexMode.java:60` and `:192` ("1G", "1GB") against the real default of 161,061,273 B.

**Feedback filed:** the case file's section D updated; amendments are in the case file's B1a and B5.
