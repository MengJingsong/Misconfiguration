# segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous — stage-4 results  <!-- file: results/segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous.md -->

> **Case:** [`segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous`](../../stage3-ai-deep-read/cases/segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous.md)
>
> **Status:** verdict filed (2026-10-28) — unit **Refuted on one sub-claim (row b), effect: does not cap**; cluster **Confirmed — does not cap**; run 1 + self-check, no run 2
>
> **Outcome class:** true negative (estimate `negative`; effect `does not cap` at both tiers; the unit "Refuted" concerns the sub-claim that the operative limit equals the setting, not the capping question)
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `6e6cf92` (case file committed there without the amendments; amendments uncommitted). sha256 of the whole file after Amendments U1–U5 and C1–C6: `1f130fc135b064d2fabd1cd94961cd29bf38ce043d1f27b18683f374c2eee2ca` (frozen 2026-10-28 03:06 UTC, before the unit run; copy `run1/case-frozen.md`; unchanged for the cluster tier). Section D changes after the run and is outside the freeze. |
| **Harness** | `harness/segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous/`: `SaiBufferProbe.java`, `unit-run.sh`, `Sampler.java`, `cluster-run.py`, `selfcheck.py` (untracked; the orchestrator commits). |
| **Tiers and values** | Unit (B2): yaml `sai_options.segment_write_buffer_size` no entry · 1 · 64 · 1024 · 4096 · 32768 · 32769 · 0 on the stock build; 1024 · 2048 · 2049 · 32768 on a build with `MAXIMUM_SEGMENT_BUFFER_MB = 2048`; two repetitions; upstream `StorageAttachedIndexOptionsTest`. Cluster (B3): one node, 4 GiB heap, one sstable of 1.29 GB (3.2M rows × 400 hex characters, indexed `text` column), setting 64 · 256 · 1024 MiB, 32769 as a startup test; **extra arm, not in the frozen plan:** 4096 MiB. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27/28 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: heap of SAI segment builders, counted by the limiter in bytes. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach | Met | the constant cannot be varied (A1): a patched build (2048) is the second arm; the setting is varied (B2b, B3b). |
| A. Core question | real resource measured, not only the counter | Partly → Met | B2 had only a counter; B3d has gauge and heap; the gap (gauge = builder's own accounting) is named; C3 adds the sampler. |
| A. Core question | usage driven to the limit and past it | Partly → Met | "~5 GiB" was loose and the limiter counts one sstable's builder: C2 builds one 1.29 GB sstable whose terms exceed every limit up to 1024 MiB. |
| A. Core question | positive control (negative file) | Met | patched constant moves the rejection point (B2h); 64 vs 256 vs 1024 moves peak usage (B3h). |
| B. Logic | prediction in numbers or a clear relation | Partly → Met | "flips at exactly n MiB" was off by one (strict `>`, `NamedMemoryLimiter.java:52-55`); "modest overshoot" had no number: U4, C4. |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met | U5, C5 added rows. |
| B. Logic | steps, alternatives, confirmation evidence | Met | B2e/B3e, B2h/B3h. |
| C. Specific | understandable, runnable, exact | Partly → Met | the original B2c built a stand-alone limiter (did not test the wiring); B3 was declared `n/a` yet gave a design: U1–U3, C1–C3. |
| D. Runnable | harness and prerequisites exist or are listed | Met | clones on `pc32`; probe, sampler and scripts are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit | Met | 1.29 GB sstable, 56 GB disk; index build about 4.5 minutes per build. |
| D. Runnable | citations spot-checked against the pinned source | Partly | `StorageAttachedIndexOptions.java:29,41`, `DatabaseDescriptor.java:1022`, `V1OnDiskFormat.java:126-137`, `SSTableIndexWriter.java:225-258`, `SegmentBuilder.java:149`: as cited. **Missed:** `V1OnDiskFormat.java:126` calls `IntMebibytesBound.toBytes()`, which returns an `int` saturated at `Integer.MAX_VALUE` (`DataStorageSpec.java:263-266`, `:442-446`); A1 noted the type bound on the setting but not this one on the limit (found by the unit run). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| U1–U5 | probe per yaml value through the real startup path and the real limiter; patched arm; flip step n+1; extra rows | applied 2026-10-27 | the stand-alone limiter did not test the wiring |
| C1–C6 | run the alternative as the cluster tier; one 1.29 GB sstable; gauges and sampler; numbers; rows | applied 2026-10-27 | `n/a` heading with a runnable alternative |
| left | A1's "Only the constant is the subject" and the missing `toBytes()` saturation | left for stage 3 | recorded in section D |

**Agreement criteria** — run 2 not chosen (see 5.2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27/28 (unit 21:06 MDT; cluster chain 21:07–22:01 MDT) |
| Node | `pc32` (`node2.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`), 40 cores, 251 GiB |
| OS and kernel | Ubuntu 22.04, `5.15.0-198-generic` |
| JDK / Ant | openjdk 11.0.32.1 2026-08-18 / Apache Ant 1.10.12 |
| Local source copy | unit stock: `~/cassandra-run4`; unit patched: `~/cassandra-run5` (`copy-source.sh` from repository commit `6e6cf92`, `StorageAttachedIndexOptions.java:29` changed to 2048, `ant jar`; `javap -constants` confirmed 2048 vs 32768); cluster: `~/cassandra-run1` (unmodified). `~/cassandra-run5` removed afterwards |
| Case-file commit / harness commit | `6e6cf92` plus uncommitted amendments (sha256 in section 1) / harness untracked |
| Storage for node data | `~/s4b-sai` on local `/dev/sda3` (seed 1.35 GB, copy 1.35 GB), never under `/proj`; removed after the run |
| Full logs | `pc32:~/s4b-logs/sai/` (`unit/`, `cluster/<label>/{summary.txt,session.log,gauges-*.csv,rss-*.csv,flush-lines-*.txt,sai-log-*.txt}`, `chain.out`, `selfcheck.txt`) |

## 3. Runbook defects

None. The unit probe, the cluster seed (first attempt) and every run executed as amended. (The extra 4096 MiB arm was added to the chain after the unit result and is labelled as outside the frozen plan.)

## 4. Run 1

**Scope:** all unit values twice on both builds; cluster `invalid`, `seed`, `run-64`, `run-256`, `run-1024`, extra `run-4096`, `down` once each. **Command log:** `segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous/run1/` (`unit-summary.txt`, `unit-probe-lines.txt`, `cluster/<label>/summary.txt`, `flush-lines-*.txt`, `gauges-*.sampled.csv` (every tenth sample), `selfcheck.txt`, `chain.out`).

### 4.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Stock: yaml 32769 | `ConfigurationException`, message `Invalid value for segment_write_buffer_size. Value must be a positive integer less than 32768MiB` (both repetitions) | `unit-probe-lines.txt` |
| Stock: no entry · 1 · 64 · 1024 · 4096 · 32768 · 0 | all accepted; `configured_MiB` = 1024 · 1 · 64 · 1024 · 4096 · 32768 · 0 | same |
| Real limiter limit (`V1OnDiskFormat.SEGMENT_BUILD_MEMORY_LIMIT` = `limiter.limitBytes()`) and flip step | 1 → 1,048,576 B, flip 2; 64 → 67,108,864, flip 65; 1024 (and default) → 1,073,741,824, flip 1025; 0 → 0, flip 1; **4096 and 32768 → 2,147,483,647 B (not 4,294,967,296 / 34,359,738,368), flip 2048** | same |
| Patched build (constant 2048) | 1024 accepted (limit 1,073,741,824, flip 1025); 2048 accepted (limit 2,147,483,647, flip 2048); **2049 and 32768 rejected** with `… less than 2048MiB` | same |
| Known answer: upstream `StorageAttachedIndexOptionsTest` | 1 test, 0 failures | `unit-summary.txt` |
| Both repetitions | identical in every line | `selfcheck.txt` |

**Cluster tier** (index build by `CREATE INDEX … USING 'sai'` on the restored single sstable of 1,294,318,837 B, then `nodetool rebuild_index`; sampler every 500 ms)

| Capacity value | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| 32769 MiB | startup | node start | exits within 3 s with the `Invalid value for segment_write_buffer_size` exception from `DatabaseDescriptor.applySimpleConfig(DatabaseDescriptor.java:1022)` | `cluster/invalid/summary.txt` |
| 64 | create (271 s) + rebuild (255 s) | `SegmentBufferSpaceLimitBytes`; peak `SegmentBufferSpaceUsedBytes`; flush lines; peak heap | 67,108,864; **67,111,788 B (64.0 MiB, +2.9 kB)**; 272 memory-limit flush DEBUG lines (`Global limit of 64.000MiB and minimum flush size of 64.000MiB exceeded. Current builder usage is 64.001MiB`); 2,847 MiB | `cluster/run-64/summary.txt`, `flush-lines-64.txt` |
| 256 | create (266 s) + rebuild (251 s) | same | 268,435,456; **268,438,236 B (256.0 MiB)**; 68 flush lines; 3,926 MiB | `cluster/run-256/…` |
| 1024 (default) | create (262 s) + rebuild (251 s) | same | 1,073,741,824; **1,073,744,152 B (1024.0 MiB)**; 16 flush lines (`Current builder usage is 1.000GiB for 376084 cells`); 3,912 MiB | `cluster/run-1024/…` |
| 4096 (extra arm, outside the frozen plan) | create (281 s) + rebuild (266 s) | same | **2,147,483,647** (not 4,294,967,296); **2,147,485,616 B (2048.0 MiB)**; 8 flush lines (`Global limit of 2.000GiB … Current builder usage is 2.000GiB for 750539 cells`); 3,954 MiB | `cluster/run-4096/…` |
| all | errors, stop | `^ERROR` lines; daemons | 0 in every run; `down`: none left | `cluster/*/summary.txt`, `chain.out` |

### 4.2 Conclusion and logic

1. **Validity** — Valid. The limit was reached and passed for every setting up to 1024 MiB: the single sstable's builder exceeds the limit and flushes at it (flush lines at 64, 256, 1024 MiB: 272, 68, 16) [observed: `flush-lines-*.txt`]. Held fixed: the same restored 1,294,318,837 B sstable per run, 4 GiB heap, the sampler present (1,044 to 1,072 samples), the limit gauge read the configured value in every run [observed: `cluster/run-*/summary.txt`]. Unit: one fresh JVM per value, repeated, known answer passes.
2. **Readings** — (a) on both builds, an accepted setting of 2048 MiB or more gives a limit of 2,147,483,647 B, not the setting: `IntMebibytesBound.toBytes()` saturates at `Integer.MAX_VALUE`; (b) the cluster peaks follow the settings 64 : 256 : 1024 = 1 : 4 : 16.0 within 3 kB; (c) peak heap does not scale (2,847 / 3,926 / 3,912 / 3,954 MiB: garbage included, G1) [observed: files above]; (d) the extra 4096 MiB arm flushes at 2 GiB.
3. **Matched rows** — Unit, B2f/U4 for the constant: 32769 throws the exact message, 32768 and below pass; patched build: 2049 and 32768 throw, 2048 and 1024 pass (the control moved) [observed: `unit-probe-lines.txt`]. **Row (b) (Amendment U5) fired:** "the real limiter's limit differs from n for an accepted value" — for n = 2048, 4096 and 32768 it is 2,147,483,647 B, so the frozen sentence "the limiter's limit equals n MiB for every accepted n" is wrong above 2047 MiB; the cause is the `int` saturation of `toBytes()`, not the constant (the same value appears with the constant at 2048 and at 32768). The row's text "(the constant acts on usage)" does not describe it: the constant never binds in either build [observed: same]. Cluster, C4/C6 (settings up to 1024 MiB): limit gauge = setting, peak used = limit (+ 2.9 / 2.8 / 2.3 kB, far below 1.25 × limit + 16 MiB), ordered 64 < 256 < 1024 with ratio 16.0, flush lines present, 32769 refused: **Confirmed — does not cap** [observed: `cluster/*/summary.txt`, `selfcheck.txt`].
4. **Excluded rows** — "no rejection at 32769" (B2g): rejected. "Limiter limit equal to 32768 / clamped to the constant": no — 2,147,483,647 is not 34,359,738,368. Unit control did not move: it moved (2049 rejected only on the patched build). Cluster "peak identical for 64 and 1024": 64.0 vs 1024.0 MiB. "Limit never reached" (C5): reached at all three settings (flush lines). "32769 starts the node": refused.
5. **Observed vs. inferred** — Inferred: (i) that the limiter figure stands for the builders' heap (the gauge is the builders' own accounting; sampled heap peak includes garbage and is a support reading only); (ii) that the compaction path behaves like the initial-build and `rebuild_index` paths (same writer, `tracker.opType() != FLUSH`; not separately run).
6. **Deviations and gaps** — Frozen text missed one fact (the `int` saturation above 2047 MiB, found by the unit tier); the cluster tier was run at settings ≤ 1024 MiB as frozen and an extra 4096 MiB arm was added afterwards (recorded, no verdict row); the memtable-flush row is `n/a` (C5); one run per setting (two builds each); a node with a setting above 1024 MiB and data above 2 GiB per sstable was not built beyond the extra arm.
7. **Core question** — No: usage does not follow the 32768 MiB constant. The check only rejects a configuration above 32 GiB at startup (unit, cluster 32769). The builders' memory follows the configured setting (peak used = setting at 64, 256 and 1024 MiB, ratio 1 : 4 : 16) up to the largest limit the code can hold, 2 GiB − 1 B, because the limit is an `int` after `toBytes()` (unit 4096 / 32768; cluster 4096 extra arm: peak 2048 MiB). So the effective ceiling is below the constant on every build and the constant never binds. The constant **does not cap** memory.

**Conclusion (one line):** unit — validation rows as predicted, row (b) fired for n ≥ 2048 (limit saturates at 2 GiB − 1, not the constant); cluster — C6: claim confirmed (effect: does not cap).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parsed all unit `probe-*.out` files and the cluster gauge CSVs, flush-line files and summaries with its own code; each line is tagged FROZEN (the frozen prediction restated) or OBSERVED: 111 PASS and 14 FAIL lines (`run1/selfcheck.txt`). The 14 FAILs are the recorded misses: 12 are the frozen "limit = n MiB / flip at n + 1" for n = 2048, 4096, 32768 (stock, both repetitions; patched 2048, both repetitions), 2 are the extra 4096 arm judged against C4, which was not written for it; every OBSERVED relation (limit = `min(n MiB, 2^31 − 1)`, flip at limit/MiB + 1) passes. By hand I re-opened `unit-probe-lines.txt` (all 30 result lines), `flush-lines-64/256/1024/4096.txt` and the four `GAUGES` lines.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | flush lines show the limit reached; gauge limit values per run |
| 2. Readings | yes | (a)–(d) each a line in the files above |
| 3. Matched row | yes | unit row (b) on the quoted limits; cluster numbers reproduced by `selfcheck.txt` |
| 4. Excluded rows | yes | each cites a number in the raw files |
| 5. Observed vs. inferred | yes | (i) is the weakest link; the verdict does not depend on heap |
| 6. Deviations and gaps | yes | listed as found |
| 7. Core question | yes | hypothesis B1 → probe and node → predictions → rows; the control moved (patched rejection point; peaks 1 : 4 : 16) |

### 5.2 Run 2?

**No** (2026-10-28). Probe outputs are exact and repeat to the byte; the cluster peaks repeat the limit within 3 kB across 8 index builds; the independent re-parse agrees. Inferred statement (i) would not change with a repeat.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** (B1) Actual SAI segment-build memory does not follow the 32768 MiB constant: it follows the configured `segment_write_buffer_size` (and soft-limit behaviour) and never approaches 32 GiB on a realistic node, so the constant is a startup validation only and does not cap memory. "Confirmed" below means this claim held; the unit tier's row (b) is the literal reading of "follows the configured segment_write_buffer_size" above 2047 MiB.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row (b) (U5): **Refuted** for the sub-claim "operative limit = the setting": above 2047 MiB the real limit is 2,147,483,647 B (int saturation of `toBytes()`); the constant behaves as predicted (32769 rejected, patched 2049 rejected) and never acts on usage | does not cap | run 1 + self-check | 2026-10-28 |
| Cluster | C6: **Confirmed** — 32769 refused; limit gauge = 64 / 256 / 1024 MiB; peak used = limit (+ ≤ 3 kB), 1 : 4 : 16; far below 32768 MiB; extra arm: 4096 MiB flushes at 2 GiB | does not cap | run 1 + self-check | 2026-10-28 |

**Positive control:** the setting moves peak usage (64.0 / 256.0 / 1024.0 MiB) and the patched constant moves the rejection point from 32769 to 2049.

**Feedback filed:** the case file's section D updated (amendments U1–U5, C1–C6 and these results). **Open points:** A1/A2 should add the `int` saturation at `V1OnDiskFormat.java:126` (effective ceiling 2 GiB − 1 B, below the constant); memtable-flush path not run; compaction path not separately run. **Leftovers on `pc32`:** no `CassandraDaemon`, sampler or script running (checked on the node); `~/s4b-sai` and `~/cassandra-run5` removed; logs kept in `~/s4b-logs/sai/`; `~/cassandra-run4` kept.
