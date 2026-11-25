# commitlog_max_outstanding_replay_count-handlemutation-futures_size--autonomous — stage-4 results  <!-- file: results/commitlog_max_outstanding_replay_count-handlemutation-futures_size--autonomous.md -->

> **Case:** [`commitlog_max_outstanding_replay_count-handlemutation-futures_size--autonomous`](../../stage3-ai-deep-read/cases/commitlog_max_outstanding_replay_count-handlemutation-futures_size--autonomous.md) (stage-3 order o100, writeup-set-ext.csv; amended working copy `~/writeup-ext/out/o100/case-amended.md`, outside the repo)
>
> **Status:** self-checked, verdict filed by the stage-4 session (2026-11-25); run 2 not chosen
>
> **Outcome class:** true positive (estimate `positive`; unit **Confirmed — caps**, cluster **Confirmed — caps**)
>
> **Agent:** autonomous. "§9a" means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e; the case
> file's feedback section is section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `cd9e1cded`; the case file is committed (`bef6bc8a6`). Filing sha256 `81f0d466d3353fdc0e7e336240234e6e6b48204ec4c007477b017424dcb262c6` (equal to `_INDEX.md` §4; copy `harness/case-as-filed.md`). After the audit's amendments S4-A1 to S4-A4 (section D only, 2026-11-25 05:00 UTC, before any reading of a frozen value): `6b033a75912d1347d777ea961dfaef93123ffc9cfe72124ef43c6516d5979cff`. Frozen text (B2f–B2h, B3f–B3h, the amendments; `harness/freeze-pred.txt`): `afa7f6a66806e0edb74b22a16c8a5febe33ffd8e834a195a399039a86f2203ed`. B2f/B2g/B3f/B3g text is byte-identical to the filed version (checked by diff). Final file sha256 after the section-D result paragraph: `8220bc2e34d7933cc98fc3a145d1476243f67986c86c41f909460b2b3ea3ea80`. |
| **Harness** | `~/writeup-ext/out/o100/harness/` (to become `harness/commitlog_max_outstanding_replay_count-handlemutation-futures_size--autonomous/`): `ReplayOutstandingCountTest.java`, `unit-run.sh`, `unit-all.sh`, `mkconf.py`, `slow-replay.btm`, `sampler.py`, `cluster-run.sh`, `cluster-all.sh`, `analyze.py`, `README.md`, `md5.txt`. Not committed by this session. |
| **Tiers and values** | Unit (B2): `-Dcassandra.commitlog_max_outstanding_replay_count` C ∈ {16, 256, 4096}, 3 repeats each, bytes cap `Long.MAX_VALUE`, N = 20000, single consumer 200 µs per task; controls bytes cap 4096 B (C = 4096) and consumer delay 0 (C = 4096). Cluster (B3): one node, 4 GiB heap G1, `concurrent_writes: 4`, Byteman 1 ms per replay task, `replayList=system_auth`, bytes cap 1 TiB; C ∈ {1024 (default), 16384, 131072}, each twice; controls ctlBytes (bytes 4 MiB, C 131072), ctlFast (no Byteman), ctlFull (no replayList, C 1024), each twice; 300000 stress rows replayed from one archived commit log. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 (S4-A1 to S4-A4 in the case file's section D) |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: a count (in-flight replay entries) with a derivable heap size; B3d measures live heap and per-entry heap. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b three values (default not included, unit only); B3b 1024 (default), 16384, 131072. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | Unit reads `futures.size()` (the operand); cluster reads live task and `Mutation` instances and live heap; the gap (private `futures.size()` not visible on the node, finished-but-unpolled entries) is named in B3d. |
| A. Core question | usage driven to the limit and past it | Met | Unit N = 20000 > 4096 with a slow consumer; cluster 300000 mutations against ≤ 131072 with the stage capped at ~4000/s. |
| B. Logic | each step says what it establishes | Met | B2h/B3h. |
| B. Logic | prediction in numbers | Met | B2f exact `peak_queue` = C + 1; B3f max ≤ C + 1, plateau floors, heap +9–31 / +78–260 MB, e ≈ 0.6–2 KB. |
| B. Logic | every plausible outcome has a row | Partly → Met after S4-A3, S4-A4 | No verdict labels; "≪", "a few", "within a few hundred", "plateau", "stable e" undefined; no rows for a control-2 / ctlFast backlog or for an unstable e. Added before any reading. |
| B. Logic | confirmation needs ceiling-follows-knob and disallow evidence | Met | The ceiling is exactly C + 1 (the reader blocked in the drain loop), with a larger C showing a larger ceiling; MutationStage Pending at C − 3 shows the blocking directly. |
| B. Logic | alternative explanations and controls | Met | Bytes-cap positive controls, no-backlog controls, `count_cap` printed from the field, `ps`/JVM args per run, `replayList` to remove memtable growth, ctlFull for the log contents. |
| C. Specific | understandable from the intro and B1 | Met | Estimate line, A3, B1. |
| C. Specific | an AI can run the runbook without re-deriving | Partly → Met after S4-A1, S4-A2 | `printf` output is split by the test logger (o123 D1); paths and the built copy on this node; soft `ulimit -n` 1024. |
| C. Specific | values, commands, observables exact | Met | B2e, B3e given in full. |
| D. Runnable | prerequisites exist | Met | JDK 11.0.33, Ant 1.10.12, built 5.0.9 copy `/mydata/s4/cassandra-base` (md5 of `CommitLogReplayer.java`, `CommitLogReader.java`, `CassandraRelevantProperties.java`, `build.xml` equal to the repository's source), Byteman 4.0.20 in `build/lib/jars`. |
| D. Runnable | workload arithmetic reaches the limit | Met | 300000 × ~112 B ≈ 34 MB of mutations (3 × 32 MiB segments); 4 GiB heap vs ≤ 260 MB predicted; 656 GB free on `/mydata`. |
| D. Runnable | citations spot-checked | Met | `CommitLogReplayer.java:75` (bytes field), `:79` (count field, `static final`), `:82,106` (deque), `:290-331` (anonymous runnable, `Stage.MUTATION.submit`), `:307` (`replayFilter.filter` inside the task), `:395-440` (`replayList` parsing), `:512-531` (handleMutation, while at 525-527); `CassandraRelevantProperties.java:114-115,130`; `CommitLogReader.java:420-478` (handleMutation only past `minPosition`). All as cited. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| S4-A1 | Paths under `/mydata/jingsong-cass-s4/o100/`, built copy instead of `ant clean jar stress-build build-test`, default ports, `ulimit -n 100000`, stop by PID | applied 2026-11-25 | runnable on this node |
| S4-A2 | `println(String.format(...))`; read the test log too | applied 2026-11-25 | o123 defect D1 (same test harness) |
| S4-A3 | B2g thresholds and labels; row for control 2 not small | applied 2026-11-25, before any reading | undefined words; uncovered outcome |
| S4-A4 | B3 primary heap = histogram `Total`; plateau, "few", "few hundred", "stable e", ctlBytes / C131072 thresholds; labels; rows for ctlFast backlog and unstable e | applied 2026-11-25, before any reading | undefined words; `GC.heap_info` noise of the size of the C16384 effect (o32, o123) |
| R-a | Sample ctlFast/ctlFull faster (replay lasts 2–4 s) or record the peak in-process | left for stage 3 | the 5 s sampler took one sample in each |
| R-b | Unit tier: include the default 1024 | left for stage 3 | the cluster tier covers it |

**Agreement criteria** — run 2 not planned.

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-11-25 UTC: unit shakedown 05:00:03–05:00:24, unit run 05:00:5x–05:05:42; cluster load 05:06:31–05:07:42, replays 05:07:42–05:22:53 | not done |
| Node | `pc82` (`node1.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu`), **x86_64**, 40 cores, 125 GiB RAM, `/mydata` 753 GB (656 GB free); held under `/mydata/s4/NODE-LOCK` for the whole run | |
| OS / kernel | Ubuntu 22.04 / `5.15.0-203-generic` (experiment `jason92-326665`) | |
| JDK / Ant | openjdk 11.0.33 (2026-10-20) / Ant 1.10.12 | |
| Local source copy | `cp -a /mydata/s4/cassandra-base` → `/mydata/jingsong-cass-s4/o100/c509-unit` (unit) and `.../c509-node` (cluster); 5.0.9, md5-checked against repo `systems/cassandra/source` (repo HEAD `cd9e1cded`, source clean) | |
| Storage | unit: the tree's `build/test`; cluster: `/mydata/jingsong-cass-s4/o100/replay-count` (commit log 100,667,392 bytes = 3 × 32 MiB segments after the load; `snap.tar` 101 MB) — all removed after the run | |
| Logs | node `pc82:/mydata/jingsong-cass-s4/o100/{unit,cluster,logs,harness}` (4.3 MB kept); copies here: `run1/unit/`, `run1/cluster/<label>/` (`session.txt`, `samples.jsonl`, `samples-raw.txt`, `jvm-args.txt`, `system.log`, `cassandra.out`; load: `stress*.txt`, `tablestats.txt`, `commitlog-ls.txt`), `run1/driver-logs/`, `run1/analysis.txt` | |

## 3. Runbook defects

None in run 1. The two known-in-advance problems (S4-A1 paths/build, S4-A2 `printf`) were fixed in the audit, before the freeze. Shakedown before run 1: C = 2, N = 2000 → `peak_queue=3 peak_not_yet_run=3 handled=2000` (`run1/unit/shakedown/run-shake-C2.log`).

## 4. Run 1

**Scope:** unit tier B2 as amended (9 + 2 JVMs); cluster tier B3 as amended (one load, 12 replays). **Command log:** `run1/unit/run1/run-<label>.log`, `run1/cluster/<label>/session.txt`, `run1/driver-logs/{unit-all,cluster-all}.out`. **Analyzer:** `harness/analyze.py` → `run1/analysis.txt`.

### 4.1 Readings

**Unit tier** (`run1/unit/run1/run-*.log`, `TEST-*.xml`; each JUnit 1 test, 0 failures, 0 errors)

| Run | `count_cap` | `peak_queue` | `peak_not_yet_run` | `handled` | `peak_pending_bytes` |
|---|---|---|---|---|---|
| C = 16, repeats 1–3 | 16 | 17, 17, 17 | 17, 17, 17 | 20000 each | 901 |
| C = 256, repeats 1–3 | 256 | 257, 257, 257 | 257, 257, 257 | 20000 each | 13,621 |
| C = 4096, repeats 1–3 | 4096 | 4097, 4097, 4097 | 4097, 4097, 4097 | 20000 each | 217,141 |
| Control 1: bytes cap 4096 B, C = 4096 | 4096 | **81** | 81 | 20000 | 4,149 (= 4096 + 53, one entry) |
| Control 2: consumer delay 0, C = 4096 | 4096 | **3** | 2 | 20000 | 156 |

Mean serialized entry ≈ 53 B (217,141 / 4097).

**Cluster tier** (load: 300,000 partitions, 0 errors, 48,113 op/s; `SSTable count: 1`, memtable 300,000 cells — `run1/cluster/load/`)

| Run (both repeats) | JVM args (`jvm-args.txt`) | Replay (system.log) | Max / plateau-median `MutationInitiator$1` | `Mutation` plateau median | Live heap plateau median (histo `Total`) | `GC.heap_info` used median |
|---|---|---|---|---|---|---|
| C1024 | count 1024, bytes 1 TiB, Byteman, replayList | 85,853 / 85,883 ms, 1 replayed | 1025 / 1025 (both) | 1025 | 68.1 / 68.1 MB | 101.7 / 101.7 MB |
| C16384 | count 16384 | 85,819 / 85,841 ms | 16385 / 16385 (both) | 16385 | 84.1 / 84.0 MB | 117.6 / 117.6 MB |
| C131072 | count 131072 | 86,340 / 86,229 ms | 131073 / 131073, 131072.5 | 131073, 131072.5 | 202.9 / 202.9 MB | 236.5 / 233.6 MB |
| ctlBytes | count 131072, bytes 4 MiB | 86,022 / 86,290 ms | 37450 / 37450 (both) | 37450 | 105.9 / 105.9 MB | 139.4 / 139.4 MB |
| ctlFast | count 131072, no Byteman | 2,316 / 2,190 ms | 0 / 1 (one sample each) | — | — | — |
| ctlFull | count 1024, no Byteman, no replayList | 4,245 / 4,395 ms, **300,001 replayed** | 2 / 1 (one sample each) | — | — | — |

18 samples per Byteman run, 8 in the plateau window. MutationStage in every Byteman plateau sample: Active 4, Pending C − 3 (1021 / 16381 / 131069 / 37446) (`samples-raw.txt`). C131072's series is 131073 for 9 samples, then drains in steps of ~17,500 once the reader has read the whole log (`analysis.txt`). 0 `^ERROR` lines in every system.log.

### 4.2 Conclusion and logic

1. **Validity** — Valid. Unit: every run handed all 20000 workload mutations to `handleMutation` and printed `count_cap` = intended C from the field [observed: `run-*.log`]; the bytes cap was `Long.MAX_VALUE` in the C runs [observed]. Cluster: the load held 300,000 rows only in the commit log (SSTable count 1 is the pre-load 1-row flush; ctlFull replays 300,001) [observed: `load/tablestats.txt`, `ctlFull-r*/system.log`]; each run's JVM carried the intended `-D` values [observed: `jvm-args.txt`]; Byteman was effective (stage Active 4, replay 86 s vs 2 s without it) [observed].
2. **Readings** — Unusual: none material. ctlFast and ctlFull had one sample each, because replay took 2–4 s against a 5 s sampler. The cluster plateau sits at exactly C + 1, not C: during the drain wait the deque holds C entries after `poll()` and the polled entry's task is still reachable in the stage until it runs [inferred from `CommitLogReplayer.java:525-530` and the stage's Active 4 / Pending C − 3 = C + 1 tasks].
3. **Matched row** — Unit B2g row 1: `peak_queue` = C + 1 for all three C in all three repeats, control 1 = 81 (≤ 410) [observed]. Cluster B3g row 1: counts plateau at C + 1 (1025 / 16385 / 131073), never above, in both repeats; live heap rises 68.1 → 84.0 → 202.9 MB with e = 1037 B per entry for both C16384 and C131072 (ratio 1.00), ΔC131072−C1024 = 134.8 MB inside B3f's +78–260 MB, ΔC16384−C1024 = 16 MB inside +9–31 MB; ctlBytes 37450 ≤ 65536 [observed: `analysis.txt`].
4. **Excluded rows** — Unit row 2 (> C + 1): never [observed]. Unit row 3 (≪ C + 1 at 4096): 4097 [observed]. Unit row 4 (handled < 20000): 20000 [observed]. Unit row 5 (control 1 ≈ 4097): 81 [observed]. S4-A3 control-2 row: 3 ≤ 410, not met [observed]. Cluster row 2: max excess over C + 1 is 0 [observed]. Row 3 (heap flat): Δ 134.8 MB [observed]. Row 4 (C131072 ≤ 1.5 × C16384): 131073 vs 16385 [observed]. Row 5 (ctlBytes ≈ 131072): 37450 [observed]. Row 6 (ctlFull < 300000): 300,001 [observed]. S4-A4 rows: ctlFast 0–1 ≤ 65536; e ratio 1.00 [observed].
5. **Observed vs. inferred** — Inferred: (i) that the live heap difference between runs is the queue: all settings except C are equal, `replayList` keeps `keyspace1` out of the memtable (1 replayed mutation per Byteman run), and the per-entry e is identical across two independent pairs and consistent with ctlBytes ((105.9 − 68.1) MB / (37450 − 1025) = 1038 B) [inferred from observed numbers]; (ii) the C + 1 explanation in part 2; (iii) ctlFast's "no backlog" rests on one sample per run plus the 2 s replay time.
6. **Deviations and gaps** — S4-A1 to S4-A4 (section 1). Heap measured as the histogram `Total` (S4-A4); `GC.heap_info` used gives the same e (1037 / 1014 B) with a ~33.5 MB constant offset. The unit tier does not include the default 1024 (the cluster does). Run on x86_64 (`pc82`); timings are not comparable to the aarch64 m400 runs of other cases, which this design does not depend on. The cap bounds entries, not bytes: per-entry heap is shape-dependent (A3.5), here ~1.04 KB for ~112-byte serialized mutations (4 MiB / 37450).
7. **Core question** — The constraint caps usage and usage follows it. The unit tier shows the operand `futures.size()` is held at exactly C + 1 for three values spaced 16x, while a known-binding bytes cap moves the same instrument to 81. The cluster tier shows the real resource follows: live not-yet-applied replay tasks and their `Mutation`s plateau at C + 1 for the default and two larger values, and live heap rises by ~1.04 KB per allowed entry, ~135 MB at 131072 vs the default.

**Conclusion (one line):** Unit B2g row 1, cluster B3g row 1 — claim confirmed: `cassandra.commitlog_max_outstanding_replay_count` caps in-flight replay mutations at C + 1 and their heap (effect: caps; ~1 KB per entry for small mutations).

## 5. Self-check of run 1 — AI

Re-read by hand, not from the analyzer: `samples-raw.txt` of all eight Byteman runs (max `MutationInitiator$1` 1025 / 16385 / 131073 / 37450, `Total` in samples 6–9 68.1 / 84.0–84.1 / 202.9 / 105.9 MB), `jvm-args.txt` (count and bytes values), each `system.log` (`Log replay complete` lines, 0 `^ERROR`), `ctlFull-r1/system.log` (300,001), the unit `run-*.log` `READING` lines and the XML counts (11 × 1 test, 0 failures, 0 errors).

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | `load/tablestats.txt`, `ctlFull-r*/system.log`, `jvm-args.txt`, unit `count_cap`. |
| 2. Readings | yes | C + 1 plateau re-read in `samples-raw.txt` with MutationStage `4 / C−3`. |
| 3. Matched row | yes | Every number of both rows re-read in the raw files. |
| 4. Excluded rows | yes | Each exclusion cites a re-read number. |
| 5. Observed vs. inferred | yes | (i) supported by three independent e values (1037, 1037, 1038 B); (iii) stated as thin. |
| 6. Deviations and gaps | yes | Amendments and the one-sample controls stated. |
| 7. Core question | yes | B1 → B2/B3 runbooks → B2f/B3f → B2g/B3g row 1, with positive controls moving. |

### 5.2 Run 2?

**No** (2026-11-25). Both tiers agree with exact, repeated readings (C + 1 in every repeat; e identical across pairs), positive controls move as predicted, and the result neither refutes the case nor confirms a bypass.

## 6. Run 2 — not done. ## 7. Comparison — not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps): both tiers Confirmed with effect `caps`.

**Claim tested:** (B1) During commit-log replay, with the mutation stage slower than the reader and the bytes cap out of the way, the number of replay mutations outstanding never exceeds `cassandra.commitlog_max_outstanding_replay_count` + 1 and does reach it; the heap held by those mutations grows with the cap (≈ cap × heap per mutation).

| Tier | Verdict | Effect | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1: **Confirmed** — `peak_queue` 17 / 257 / 4097 for C = 16 / 256 / 4096 (3 repeats each); bytes-cap control 81; no-delay control 3 | caps | run 1 + self-check | 2026-11-25 |
| Cluster | B3g row 1: **Confirmed** — live replay tasks 1025 / 16385 / 131073 for C = 1024 / 16384 / 131072 (both repeats); live heap 68.1 / 84.0 / 202.9 MB, e = 1037 B; ctlBytes 37450; ctlFull 300,001 replayed | caps | run 1 + self-check | 2026-11-25 |

**Positive control:** unit bytes cap 4096 B → `peak_queue` 81; cluster bytes cap 4 MiB → 37450 entries, 105.9 MB.

**Feedback filed:** the amended case file's section D (`~/writeup-ext/out/o100/case-amended.md`: amendments S4-A1 to S4-A4 and the stage-4 result paragraph). No section of the trace was refuted. **Doc note:** the replay queue holds at most C + 1 deserialized mutations; for small mutations about 1 KB each, so the default 1024 bounds it near 1 MB, and raising the property to 131072 let it hold ~135 MB here. **Leftovers on pc82:** nothing running (no java, CassandraDaemon, stress, sampler or test JVM; ports 7000/7199/9042 free); source trees, node data and `snap.tar` removed; kept `/mydata/jingsong-cass-s4/o100/{unit,cluster,logs,harness}` (4.3 MB). Driver PID file removed; node lock released at the end.
