# profileload-capacity-beginsampling-capacity--autonomous — stage-4 results  <!-- file: results/profileload-capacity-beginsampling-capacity--autonomous.md -->

> **Filed 2026-11-24 (coordinator):** case file (with the stage-4 amendments and section D) in [`../../stage3-ai-deep-read/cases/profileload-capacity-beginsampling-capacity--autonomous.md`](../../stage3-ai-deep-read/cases/profileload-capacity-beginsampling-capacity--autonomous.md), harness in [`../harness/profileload-capacity-beginsampling-capacity--autonomous/`](../harness/profileload-capacity-beginsampling-capacity--autonomous/); the evidence excerpts (`~/writeup-ext/out/o123/run1/`) stay outside the repo; full logs on `ms0604` in `/mydata/jingsong-cass-s4/o123/run1/`. Paths below that point to `~/writeup-ext/out/` are where the run kept them.
>
> **Case:** [`profileload-capacity-beginsampling-capacity--autonomous`](../../stage3-ai-deep-read/cases/profileload-capacity-beginsampling-capacity--autonomous.md) (stage-3 order o123; working copy `~/writeup-ext/out/o123/profileload-capacity-beginsampling-capacity--autonomous.md`, outside the repo)
>
> **Status:** self-checked, verdict filed by the stage-4 session (2026-11-24); run 2 not chosen
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
| **Case-file version** | Repository HEAD `8f76f2390` (the case file is not in the repo; stage 3 wrote it to `~/writeup-ext/out/o123/`; the coordinator files it). Filing sha256: `e2a78b88c8d91afc4ebf3059a20a5b20c52280ee9792af2346febe18d2e42583` (copy `harness/case-as-filed.md`). After the audit's amendments S4-A1 to S4-A4 (2026-11-24 06:19 UTC, before any reading): `26da5f1c69734b8dbf8c4c8f926e2576c10c7356c4a7206cfbcb18b5615e1e4e`. sha256 of the frozen prediction and conclusion text (B2f+B2g from `**B2f.` to `**B2h.`, then B3f+B3g from `**B3f.` to `**B3h.`, S4-A2 and S4-A4 included; copy `harness/freeze-pred.txt`): `a219b9ab65f58d7da8bd59c199396b266af787bd44636bf36cfe3b5a7d6627ca`. The defect fixes S4-A5 and S4-A6 and section D left that hash unchanged (re-checked after section D). Final file sha256 (after section D): `b4af7d313d1f74c2cbe18126be0d6b08b6a06a6d2ad5c5ea90dd95a927fce86c`. |
| **Harness** | `~/writeup-ext/out/o123/harness/` (to become `harness/profileload-capacity-beginsampling-capacity--autonomous/`): `MaxSamplerCapacityProbeTest.java`, `SamplerCtl.java`, `run-unit.sh`, `run-cluster.sh`, `analyze.py`, `README.md`, md5s in `md5.txt`. Not committed by this session. |
| **Tiers and values** | Unit (B2): `capacity` ∈ {−5, 0, 1, 10, 256, 1024, 10000, 100000} × order {ASC, RND}, N = 50,000 direct `insert`s; controls `fieldHuge` and inactive baseline. Cluster (B3): one node, 2 GiB heap, sampler `WRITE_SIZE` on `keyspace1.standard1` via JMX, C ∈ {256, 1024, 100000, 2000000 (control)}, 1,000,000 stress writes per arm; `nodetool profileload -s 2000` rejection check. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-24 (S4-A1 to S4-A4 applied before the freeze) |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: heap held by `Sampler.Sample` entries in the `MinMaxPriorityQueue`; a count with a derivable byte size, measured as bytes too (B2d jamm, B3d histo and heap). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b eight values incl. 256 (nodetool default) and 1024 (max); B3b four values incl. 256. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | Unit: `ObjectSizes.measureDeep(q)`; cluster: `jmap -histo:live` instance count/bytes and the G1 used heap before and after releasing the queue (B3d). |
| A. Core question | usage driven to the limit and past it | Met | Unit N = 50,000 ≥ every binding cap; cluster 1,000,000 writes ≥ 100000 (B3c). Positive controls non-binding (100000 unit, 2,000,000 cluster). |
| B. Logic | each step says what it establishes | Met | B2h/B3h name each control's role. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f/B3f give exact sizes `min(max(1,C), N)` and byte ranges. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → Met after S4-A2, S4-A4 | B2g/B3g rows had no verdict labels, "∝", "≈ S" and "same order" were undefined, and "counter capped but the real resource grows" had no row. Added before any reading. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Exact ceilings at every C; the disallow branch shows directly as `size` = C while N or S ≫ C, and the uncapped control keeps everything. |
| B. Logic | alternative explanations and their controls | Met | Inactive baseline, non-binding control, two orders, direct `insert` (no load shedding), `fieldHuge` (line 46 vs 48), flush before M1 and no writes between M1 and M2. |
| C. Specific | a human can follow it from the intro and B1 | Met | Estimate line, note on the given line, A3, B1. |
| C. Specific | an AI can run B2a–B2e / B3a–B3e without re-deriving the code path | Partly → Met after S4-A1, S4-A3 | `~/cassandra-5.0.9` does not exist on the node (S4-A1); S defined from `_SAMPLE` drops only, which misses stress retries (S4-A3: table write count); node soft `ulimit -n` 1024; pid file deleted at shutdown. Two further defects only surfaced in the run (D1, D2, section 3). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met | Commands given in full (B2e, B3e). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | JDK 11.0.33, Ant 1.10.12, built 5.0.9 copy at `/mydata/s4/cassandra-base` on `ms0604`; test class and JMX helper in the file. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Unit: 50,000 × ~85 B, trivial. Cluster: 1M writes at 7–11 k/s ≈ 100–145 s per arm; ~0.5 GB disk per arm, truncated; control ~120 MB in a 2 GiB heap; 30 GB free on `/mydata`. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked in `systems/cassandra/source` (5.0.9, clean): `MaxSampler.java:35-49` (maximumSize at 45-47, field at 48), `:66-75` (insert, permitsValue), `:37` (reverse comparator); `Sampler.java:100-113` (executor, queue limit 1000, `_SAMPLE` drop); `ColumnFamilyStore.java:1480-1482` (`WRITE_SIZE` sample per write, value `update.dataSize()`), `:2055-2077` (begin/finishLocalSampling signatures used by `SamplerCtl`); `ColumnFamilyStoreMBean.java:302`; `ProfileLoad.java:52-53, 76-79`; `TableMetrics.java` MaxSampler instances; Guava 32.0.1-jre (`.build/parent-pom-template.xml:309`); jamm 0.4.0 (`build.xml:164`). All as cited. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| S4-A1 | Node paths: copy `/mydata/s4/cassandra-base` to `/mydata/jingsong-cass-s4/o123/cassandra-5.0.9` | applied 2026-11-24 | runnable on this node |
| S4-A2 | B2g verdict labels (U1–U3) and thresholds ("bytes ∝ size": ±20 % per-entry; cap-1024 bytes < 0.1 × uncapped) | applied 2026-11-24, before any reading | every outcome needs a labelled row; "∝" undefined |
| S4-A3 | S = table write-count delta − `_SAMPLE` drops; `ulimit -n 100000`; save PID; `GC.heap_info` right after the histo | applied 2026-11-24 | stress retries; node limits; pid file deleted at shutdown |
| S4-A4 | B3g verdict labels (C1–C3) and thresholds ("≈ S" within 0.1 %; control delta ≥ 20 MB; delta(100000) ≤ 0.3 × control; delta(256/1024) ≤ 5 MB) plus the counter-capped-but-heap-grows row | applied 2026-11-24, before any reading | as S4-A2 |
| S4-A5 | D1 fix: `println(String.format(...))`; read `RESULT` lines from the test log | applied 2026-11-24 (defect; tier restarted) | step B2e.4 could not run as written |
| S4-A6 | D2 fix: `cqlsh TRUNCATE`; histo `Total` as a secondary heap reading | applied 2026-11-24 (defect; tier restarted) | step B3e.3.9 could not run as written |
| R-a | Note in B3 that stress writes all carry the same `WRITE_SIZE` value, so the cluster tier exercises the `permitsValue` refusal (line 48), not `maximumSize` eviction (line 46) | left for stage 3 | explanatory; both bound at C |
| R-b | Use the histo `Total` line as the primary heap reading | left for stage 3 | G1 "used" after the histo includes young regions allocated afterwards (16 MB granularity) |

**Agreement criteria** — run 2 not planned.

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-11-24 UTC: unit 06:23–06:24 (first attempt 06:19–06:21); cluster 06:37–06:50 (shakedown attempt 06:24–06:37) | not done |
| Node (CloudLab name and type) | `ms0604` = `node2.jason92-326377.misconfiguration-pg0.utah.cloudlab.us`, Utah m400, **aarch64**, 8 cores, 62 GiB; exclusive via `/mydata/s4/NODE-LOCK` for the run | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.1 LTS, `5.15.0-191-generic` (aarch64) | |
| JDK (`java -version`) | OpenJDK 11.0.33 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy | `/mydata/jingsong-cass-s4/o123/cassandra-5.0.9` = `cp -a /mydata/s4/cassandra-base` (a `copy-source.sh` copy of the repo's `systems/cassandra/source`, `git describe` `cassandra-5.0.9`, clean); `ant jar build-test` 59 s; repository HEAD `8f76f2390` | |
| Case-file / harness commit | not committed (outside the repo); case-file sha256 in section 1; harness md5 in `harness/md5.txt` (test class md5 `db72fff4…` matches the copy that ran, `run1/unit/run-unit.log`) | |
| Storage for node data | `/mydata` (local LVM, 39 GB, 30 GB free); node data under the copy's `data/`; heap 2 GiB (`MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`), G1 | |
| Full logs (path, outside the repo) | On `ms0604`: `/mydata/jingsong-cass-s4/o123/run1/` (14 MB: `unit/` first attempt, `unit-restart/`, `cluster/` shakedown attempt, `cluster-restart/` with per-arm histo, heap-info, stress output and log, `system.log`; `analysis.txt`). Small excerpts copied to `~/writeup-ext/out/o123/run1/`. | |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | run 1, unit | B2e.4 | No `RESULT` text in the XML's system-out: the test JVM routes `System.out` through the logger, which writes each `printf` argument as its own log line in `build/test/logs/_jdk11/TEST-…log` (`run1/unit/run-unit-attempt1.log`; `grep RESULT` rc 1). The test itself passed (3 tests, 0 failures). | S4-A5: one `println(String.format(...))` per line; read the test log. Prediction unchanged; unit tier restarted from B2e.1. | 2026-11-24 | none (file outside the repo) |
| D2 | run 1, cluster | B3e.3.9 | `bin/nodetool truncate keyspace1 standard1` → "Found unexpected parameters" (rc 1): nodetool has no truncate (`run1/cluster-attempt1/run-cluster.log`). | S4-A6: `bin/cqlsh 127.0.0.1 -e "TRUNCATE keyspace1.standard1"`; histo `Total` recorded as secondary. Cluster tier restarted from B3e.1 with fresh data and log directories. The shakedown attempt's readings are kept but not used for the verdict. | 2026-11-24 | none |
| D3 | run 1, cluster (harness) | summary | The harness's own summary columns for the histo count were 0 in the shakedown (awk pattern required a trailing space) and the baseline summary line in the restart printed empty (functions defined after use). | harness only: `analyze.py` re-parses every raw histo file; raw files unaffected. | 2026-11-24 | n/a |

## 4. Run 1

**Scope:** unit tier (B2) all 16 arms and both controls; cluster tier (B3) baseline, `-s 2000` check and all four arms. **Command log:** `run1/unit-restart/run-unit.log`, `run1/cluster-restart/run-cluster.log` (node); excerpts `~/writeup-ext/out/o123/run1/unit/`, `…/run1/cluster/`. **Analyzer:** `run1/analysis.txt` (41 PASS, 0 FAIL).

### 4.1 Readings

**Unit tier** (`run1/unit/result-lines-restart.txt`; testsuite `tests="3" failures="0" errors="0"`)

| cap | size (ASC / RND) | expected | bytes (both orders) | bytes per entry |
|---|---|---|---|---|
| −5 | 1 / 1 | 1 | 272 | 272.0 |
| 0 | 1 / 1 | 1 | 272 | 272.0 |
| 1 | 1 / 1 | 1 | 272 | 272.0 |
| 10 | 10 / 10 | 10 | 1,032 | 103.2 |
| 256 | 256 / 256 | 256 | 21,696 | 84.8 |
| 1024 | 1024 / 1024 | 1024 | 86,208 | 84.2 |
| 10000 | 10000 / 10000 | 10000 | 840,192 | 84.0 |
| 100000 (control) | 50000 / 50000 | 50000 | 4,265,880 | 85.3 |
| `fieldHuge` (begin 10, field forced to `Integer.MAX_VALUE`) | 10 | 10 | | |
| inactive baseline | queue `null` | `null` | | |

ASC and RND bytes are identical because every retained key `"k"+i` (2–6 Latin-1 chars) occupies a 24-byte `byte[]` either way [inferred from object layout; the numbers are observed].

**Cluster tier** (`run1/cluster/summary.csv`, re-parsed from raw files in `run1/analysis.txt`; per arm W = 1,000,000 writes, 0 `_SAMPLE` drops, S = 1,000,000, 0 stress errors, 7.5–10.8 k op/s)

| C | Sample count M1 | Sample bytes M1 (histo) | G1 used M1 → M2 (KB) | release delta | histo live bytes M1 → M2 | live delta | count M2 | `finish` returned |
|---|---|---|---|---|---|---|---|---|
| 256 | 256 | 8,192 | 60,678 → 60,719 | −0.04 MB | 62,135,120 → 62,176,872 | −0.04 MB | 0 | 11 |
| 1024 | 1024 | 32,768 | 64,978 → 64,906 | 0.07 MB | 66,538,424 → 66,464,560 | 0.07 MB | 0 | 11 |
| 100000 | 100000 | 3,200,000 | 73,220 → 61,936 | 11.6 MB (11,284 KB) | 74,978,280 → 63,423,008 | 11.56 MB | 0 | 11 |
| 2000000 (control) | 1,000,000 | 32,000,000 | 176,918 → 63,153 | 116.5 MB (113,765 KB) | 181,164,216 → 64,669,352 | 116.49 MB | 0 | 11 |

Other cluster readings: baseline histo has no `Sampler$Sample` (live 57.8 MB, `run1/cluster/excerpt-baseline.txt`); `nodetool profileload keyspace1 standard1 1000 -s 2000 -a WRITE_SIZE` → "Capacity (-s) cannot exceed 1024.", rc 1 (`run1/cluster/profileload-s2000.txt`); 0 `ERROR` lines in `system.log`. Control composition (histo M1 − M2, `run1/cluster/histo-M1-2000000-top.txt`): `byte[]` +32.0 MB (1.0 M keys, 32 B each), `HeapByteBuffer` +48.0 MB, `Sample` 32.0 MB, `Object[]` +4.5 MB (queue array) = 116.5 B per entry.

### 4.2 Conclusion and logic

1. **Validity** — Valid. The limit was reached and passed in every binding arm: unit N = 50,000 against caps ≤ 10,000; cluster S = 1,000,000 samples offered to `insert` (W1 − W0 = 1,000,000, 0 drops) against C ≤ 100,000 [observed: `run1/analysis.txt`]. Hold-fixed: fresh `MaxSampler` per unit arm; one node, one sampler on one table, flush before M1, no writes between M1 and M2, truncate between arms, identical stress command, 0 stress errors [observed: `run-cluster.log`]. Positive controls moved: unit cap-100000 kept all 50,000 (4.27 MB); cluster C = 2,000,000 kept 1,000,000 (116.5 MB) [observed].
2. **Readings** — Nothing unusual. The per-entry heap is constant: 84.0–85.3 B (unit, `String` values) and 115.6–116.5 B (cluster, key `ByteBuffer` + 10-byte array) [observed]. Keys are their own 32-byte arrays, not slices of larger frames [observed in the histo composition]. Stress writes all had the same `dataSize`, so at the cluster tier the queue filled to C and later samples were refused by `permitsValue` [inferred: fixed stress column sizes and `MaxSampler.java:74`; the exact counts are observed].
3. **Matched row** — Unit: B2g row 1 + row 3 + `fieldHuge` row = **S4-A2 U1 (Confirmed — caps)**: all 16 arms `size == min(max(1,cap),N)`; per-entry bytes within ±20 % (84.0–84.8, mean 84.3); cap-1024 bytes 86,208 < 0.1 × 4,265,880; control 50,000 entries, 4.27 MB ≥ 1 MB; `fieldHuge` 10; baseline `null` [observed: `run1/analysis.txt`]. Cluster: B3g rows 1 and 3 = **S4-A4 C1 (Confirmed — caps)**: count1 = 256 / 1024 / 100000 exactly; control count1 = 1,000,000 = S; control delta 116.5 MB ≥ 20 MB; delta(100000) 11.6 MB ≤ 0.3 × 116.5 = 34.9 MB; delta(256) −0.04 MB and delta(1024) 0.07 MB ≤ 5 MB; count2 0; no `Sample` at baseline [observed]. B3f numbers all inside their ranges: histo bytes ~8 KB / ~33 KB / ~3.2 MB / ~32 MB; release delta < 1 MB, 8–15 MB, 80–150 MB; ratio 100000/control 0.099 (predicted ≈ 0.1).
4. **Excluded rows** — Unit: row 2 / U2 (size > max(1,cap)): no arm. U2 bytes rule: 86,208 ≪ 0.5 × 4,265,880. Row 4 / U3 (control < N): 50,000 = N. `fieldHuge` > 10: 10. Cap −5/0 size 0: size 1. Cluster: row 2 / C2 (count1 > C): none; counter-capped-heap-grows (delta(100000) ≥ 0.5 × control): 0.099 ×. Row 4 / C3 (control ≪ S, drops ≈ N, control delta < 20 MB): control = S, 0 drops, 116.5 MB. Row 5 (count2 > 1): 0. Row 6 (nodetool accepts 2000): rejected [all observed: `run1/analysis.txt`, `run1/cluster/profileload-s2000.txt`].
5. **Observed vs. inferred** — Inferred: (i) that the cluster refusals came from `permitsValue` rather than eviction (no per-sample instrument); it does not affect the matched rows, which rest on counts and bytes only. (ii) ASC = RND bytes explained by array alignment; explanatory only. The heap deltas are observed with two independent readings (G1 used and histo live total), which agree to 0.3 MB in the arms that matter.
6. **Deviations and gaps** — Amendments S4-A1 to S4-A6; defects D1–D3 (section 3); each defect restarted its tier and the verdict uses only the restarted runs. The shakedown cluster attempt (no truncation between arms) gave the same counts (256 / 1024 / 100000 / 1,000,000) and live deltas (−0.04 / 0.05 / 11.5 / 116.5 MB) (`run1/cluster-attempt1/`), but is not used. Not exercised: the `-i` scheduled path, `samplePartitions` without a table, the other four `MaxSampler` types, and capacities ≤ 0 or above 1024 at the cluster tier through nodetool (JMX values 100000 and 2,000,000 were used, as designed). The run was on aarch64 (m400); the shared x86 runs of other cases are not comparable in timing, which this design does not depend on.
7. **Core question** — The constraint caps usage and usage follows it. The retained sample set stopped at exactly `max(1, C)` entries at every cap in the unit tier, both when every new sample beat the minimum (ASC, eviction on every add) and in random order, and on a real node it stopped at exactly C for C = 256, 1024 and 100000 under 1,000,000 writes while the uncapped control kept all 1,000,000 (parts 1, 3). The heap released with the queue was 11.6 MB at C = 100000 against 116.5 MB uncapped, i.e. proportional to the cap (part 3).

**Conclusion (one line):** Unit S4-A2 U1 (B2g row 1) and cluster S4-A4 C1 (B3g row 1) — confirmed: the sampler capacity caps the `MaxSampler` queue at `max(1, capacity)` entries, ≈ 85–116 B each (effect: caps).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/analyze.py` re-parses the raw files with its own code (the test log's `RESULT` lines; each arm's full `jmap -histo:live` file, `GC.heap_info` file and stress output; the run log's D0/D1/W0/W1 lines), not the run script's summary. Output `run1/analysis.txt`: 41 PASS, 0 FAIL. Spot re-reads by hand: `histo-M1-100000.txt` line 6 `100000 3200000 org.apache.cassandra.metrics.Sampler$Sample`, `Total 1231361 74978280`; `histo-M1-2000000.txt` line 3 `1000000 32000000 …Sampler$Sample`; `heapinfo-M1-100000.txt` used 73220K, `heapinfo-M2-100000.txt` used 61936K; `stress-2000000.out` 1,000,000 partitions, 0 errors.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `analysis.txt`: W = 1,000,000 and 0 drops per arm; stress 0 errors; unit control 50,000. |
| 2. Readings | yes | Per-entry bytes recomputed from `result-lines-restart.txt` and from histo M1 − M2 (`histo-M1-2000000-top.txt`, M2 grep). |
| 3. Matched row | yes | Every U1 and C1 term recomputed by `analyze.py` from raw files. |
| 4. Excluded rows | yes | Each exclusion cites a number re-read above. |
| 5. Observed vs. inferred | yes | Both inferred items are explanatory; no matched-row term depends on them. |
| 6. Deviations and gaps | yes | D1/D2 restarts recorded; shakedown kept separate and agrees. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1 → B2b–B2e / B3b–B3e → B2f / B3f → B2g / B3g as amended (S4-A2, S4-A4, frozen before readings, hash unchanged); positive controls moved under the same workload. |

### 5.2 Run 2?

**No** (2026-11-24). Both tiers agree, every term of the frozen rows held with wide margins, exact counts leave no tolerance question, and the shakedown attempt reproduced the same counts. The result neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps) — both tiers Confirmed with effect `caps`.

**Claim tested:** (B1) For a `MaxSampler` started with capacity `C`, the number of retained `Sampler.Sample` entries (and hence their heap) is at most `max(1, C)` however many samples arrive; the retained heap grows with sampled operations only until `max(1, C)` entries, roughly `min(max(1,C), N_sampled) × s`. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1 (S4-A2 U1): **Confirmed** — sizes exactly `max(1,cap)` for all 14 binding arms (both orders), 50,000 at the non-binding cap; 84–85 B per entry; `fieldHuge` 10 (bound from `maximumSize`, line 46) | caps | run 1 + self-check | 2026-11-24 |
| Cluster | B3g row 1 (S4-A4 C1): **Confirmed** — 256 / 1024 / 100000 live samples at C = 256 / 1024 / 100000 after 1M writes; 1,000,000 at the control; released heap 11.6 MB vs 116.5 MB | caps | run 1 + self-check | 2026-11-24 |

**Positive control:** unit — cap 100000 keeps all 50,000 inserted samples (4.27 MB); cluster — C = 2,000,000 keeps every one of the 1,000,000 samples (116.5 MB released) under the same workload that leaves exactly C at the binding values.

**Feedback filed:** the case file's section D (working copy `~/writeup-ext/out/o123/…--autonomous.md`), with amendments S4-A1 to S4-A6 next to the text they change; no section of the trace was refuted. **Notes for stage 3:** R-a and R-b (section 1); the "bypass" items of A3 (executor tasks, per-table multiplication, retention after expiry, JMX values above 1024) were not exercised and stay as source claims. **Upstream / doc candidates:** none for a bug; the JMX operations accept any capacity (2,000,000 was accepted here, as A1 says), so the 1024 maximum is a nodetool-only guard. **Leftovers on the node:** nothing running (checked by `ps` for `CassandraDaemon`, `cassandra-stress`, `SamplerCtl`, the test and the run scripts: none; ports 7000/7199/9042 free). The source copy and node data (1.4 GB) were deleted; kept: `/mydata/jingsong-cass-s4/o123/` (14 MB: `harness/`, `logs/`, `run1/`, `start.log`). Node lock `/mydata/s4/NODE-LOCK` released.
