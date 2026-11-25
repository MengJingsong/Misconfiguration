# dob_doubling_threshold_mb-calculatenewsize-capacity--autonomous — stage-4 results  <!-- file: results/dob_doubling_threshold_mb-calculatenewsize-capacity--autonomous.md -->

> **Case:** [`dob_doubling_threshold_mb-calculatenewsize-capacity--autonomous`](../../stage3-ai-deep-read/cases/dob_doubling_threshold_mb-calculatenewsize-capacity--autonomous.md) (extension set, order 119, band B, writeup-set-ext.csv; amended working copy `/users/jason92/writeup-ext/out/o119/case-amended.md`, outside the repo)
>
> **Status:** self-checked, verdict filed by the stage-4 session (2026-11-25); run 2 not chosen
>
> **Outcome class:** true negative (estimate `negative`; unit **Confirmed — does not cap**, cluster **Confirmed — does not cap**)
>
> **Agent:** autonomous. "§9a" means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e; the case
> file's feedback section is section D.

Written outside the repository by a fresh stage-4 session working as Jingsong, 2026-11-25. Nothing in the repository was
edited. Earlier attempts (2026-11-24) were interrupted; no partial run folder existed on `pc75`, and the old copy in
`~/writeup-ext/out/o119/` (identical to the filed case file) was discarded. This run started clean.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `cd9e1cded`; case file committed in `bef6bc8a6`. Filing sha256 `ca38468a1acb52d1697dfc9dc9a5fef36abbf170dafb8fb6a4ebc336ad701320` (equal to `_INDEX.md` §4; copy `harness/case-as-filed.md`). After audit amendments S4-A1–S4-A3 (section D, 2026-11-25 06:55 UTC, before any reading): `67ce3af3…1c81c72`. After runbook defect S4-D1: `9ad1901c…30d3db`. After S4-A4 (before any cluster reading): `5f6369eb…9d054f` (all in `harness/freeze.sha256`). Frozen prediction text (B2f–B2h, B3f–B3h, amendments S4-A1–S4-A3): `harness/freeze-pred.txt`, sha256 `7e91b527…a3572`. B2f/B2g/B3f/B3g text is byte-identical to the filed version. Final sha256 after the section-D result paragraph: `64510676933148c8ad3d5debbe420de4e1b716738608c23807a6cb603c685a49`. |
| **Harness** | `/users/jason92/writeup-ext/out/o119/harness/` (to become `harness/dob_doubling_threshold_mb-calculatenewsize-capacity--autonomous/`): `DobGrowthProbe.java`, `JfrDob.java`, `dob.py` (all three byte-for-byte from the case file's B2a/B3a listings), `unit-run.sh`, `cluster-run.sh`, `sim_b2f.py` (pre-run arithmetic check), `analyze_unit.py`, `analyze_cluster.py`, `case-as-filed.md`, `freeze.sha256`, `freeze-pred.txt`. Not committed. |
| **Tiers and values** | Unit (B2): `-Dcassandra.DOB_DOUBLING_THRESHOLD_MB` T ∈ {unset, 0, 16, 64, 128, 1024} × {`bytes`, `rows`} × {100, 200} MiB (unset: 200 only), one JVM each; positive control `fixed 200`; repeat of `bytes 200` for each set T. Cluster (B3): one node, 4 GiB G1 heap, T ∈ {unset, 0, 16, 64, 128, 1024}, one node restart per T; 200 × 1 MiB rows in one partition, loaded and flushed once; per T 1 warm-up + 3 recorded `SELECT max(v)` with paging off, then 3 with `fetch_size=100` (positive control) for every T. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 (S4-A1–S4-A3 before run 1; S4-A4 before the cluster tier) |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Met | Capacity of a growable `DataOutputBuffer` = heap `byte[]` length (A2, B2d, B3d). |
| A | knob varied, ≥ 3 values incl. default | Met | unset, 0, 16, 64, 128, 1024 (B2b, B3b). |
| A | real resource measured, not only the counter | Met | Unit: `capacity()` of the real buffer at every resize. Cluster: JFR `ObjectAllocationOutsideTLAB` size of each new buffer array on the real read path. Gap named in B3d (exact free time not observable). |
| A | usage driven to the limit and past it | Met | S ≈ 200 MiB > T for every T except 1024 (the always-x2 reference). |
| A | negative estimate: positive control | Met | Unit `DataOutputBufferFixed(1 MiB)` (a cap that binds); cluster page size (`fetch_size=100`), a limit known to bind this buffer. |
| B | "how this verifies" block mapped | Met | B1 (claim, refuted-if), B2b–B2e / B3b–B3e (test), B2f / B3f (prediction), B2g / B3g (conclusions). |
| B | prediction stated in numbers | Met | B2f exact bytes per cell; B3f MiB ±0.1 per T and ratio pattern. Re-derived independently before the run (`harness/sim_b2f.py`): every B2f cell agrees. |
| B | every plausible outcome has a row | Partly → Met after S4-A2, S4-A3 | Rows exist for cap, follows-knob, not applied, control fails, OOM, header offset; "matches exactly", "near T", "proportional", "about 1.5–2x smaller" had no numbers. |
| B | confirmation needs disallow evidence | Met (n/a in kind) | The claim is that no disallow branch exists; the evidence is the branch's effect (x2 vs x1.5) seen at every resize and C ≥ S. |
| B | alternative explanations and controls | Met | Property read back (printed field; `jcmd VM.system_properties`), unset = 64, fixed buffer, payload halving, repeats, one JVM per T, stack filter. |
| C | understandable from the header and B1 | Met | Estimate / Ground lines, B1. |
| C | an AI can run the runbook without re-deriving | Partly → Met after S4-A1 | Paths, built copy, `ulimit -n` and process checks for this node. |
| C | values, commands, observables exact | Met | Full probe, parser and driver sources given. |
| D | prerequisites exist | Met | JDK 11.0.33, Ant 1.10.12, built `/mydata/s4/cassandra-base` on `pc75`; md5 of `DataOutputBuffer.java`, `BufferedDataOutputStreamPlus.java`, `ReadResponse.java`, `CassandraRelevantProperties.java` and of `conf/{cassandra.yaml,cassandra-env.sh,jvm11-server.options,jvm-server.options,logback.xml}` equal to repo `systems/cassandra/source`. |
| D | workload arithmetic reaches the limit | Met | Unit peak ≈ 490 MB in a 2 GB heap; cluster ≈ 200 MB data, 4 GB heap, 700 GB free on `/mydata`, 123 GiB RAM available. |
| D | citations spot-checked | Partly | `DataOutputBuffer.java:48,118-125,136-139,143-155,158-172,174-182`, `CassandraRelevantProperties.java:203`, `ReadResponse.java:197-203`, `BufferedDataOutputStreamPlus.java:75-78,102-136,145-146` as cited. B3c/B3f assume 2 MiB G1 regions; `conf/jvm11-server.options:66` sets 16 MiB (S4-A4; affects only the secondary GC-log line). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| S4-A1 | Run on `pc75` under `/mydata/jingsong-cass-s4/o119`; `cp -a` the built base instead of rsync + `ant jar`; add `build/lib/jars/*` to the probe class path; `ulimit -n 100000`; stop by PID; `ps … grep '[C]assandraDaemon'`; skip optional B2e step 8; run the B3 control for every T | applied 2026-11-25, before run 1 | runnable on this node |
| S4-A2 | B2g numbers: exact-match definition, per-step ratio rule, (v) range, row 2/3 thresholds, repeat identity | applied 2026-11-25, before run 1 | undefined words |
| S4-A3 | B3g numbers: burst split, C definition, ±1 MiB / ratio rule, 0.1 MiB agreement, control ≤ 0.75 × paging-off, row 2/3/6 thresholds | applied 2026-11-25, before run 1 | undefined words |
| S4-A4 | G1 region size is 16 MiB (`jvm11-server.options:66`): secondary GC-log prediction becomes ≥ ceil(C/16 MiB) regions; driver PID file | applied 2026-11-25, after the unit tier, before any cluster reading | wrong environmental assumption, independent of readings; no B3g row changes |
| R-a | B2e step 7's fallback does not address the JDK 11 module-access failure; the probe JVM needs `conf/jvm11-clients.options` (found as S4-D1) | applied as S4-D1 | runbook defect |
| R-b | B2g row 2 should name its threshold only for T with S > 2T (see §4.2 part 4: my S4-A2 wording included T = 128, where 2T = 256 MiB > S) | left for stage 3 | audit wording error, found after the unit readings; not edited after reading |
| R-c | B3f's control "2 pages per query" is right for the buffers that matter; a third, empty page is fetched but its buffer stays inside a TLAB | left for stage 3 | clarity only |

**Agreement criteria** — run 2 not planned.

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-11-25 UTC: unit attempt 1 (defect) 06:55:56; unit run 06:56:2x–06:57:1x; cluster 06:58–07:05:35 | not done |
| Node | `pc75` (`node3.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu`), **x86_64**, 40 cores, 125 GiB RAM, `/mydata` 753 GB (700 GB free), 8 GiB swap; held under `/mydata/s4/NODE-LOCK` for the whole run | |
| OS / kernel | Ubuntu 22.04 / `5.15.0-203-generic` | |
| JDK / Ant | openjdk 11.0.33 (2026-10-20, build 11.0.33+9-post-1ubuntu1-22.04.1) / Ant 1.10.12 | |
| Local source copy | `cp -a /mydata/s4/cassandra-base` → `/mydata/jingsong-cass-s4/o119/cassandra` (5.0.9, built with `ant build-test` on 2026-11-17); md5-checked against repo `systems/cassandra/source` at HEAD `cd9e1cded` (source clean) | |
| Storage | node data under `$RUN/cassandra/data` (202 MB after load, SSTable 200.0 MiB, uncompressed); removed after the run | |
| Logs | node `pc75:/mydata/jingsong-cass-s4/o119/{probe,attempt1-defect,jfr,logs,harness,*.out,cluster-session.txt}` (7.7 MB kept, `.jfr` files deleted after parsing); copies here: `run1/unit/` (`out-*.txt`, `repeat/`, `probe-driver.out`, `analysis-unit.txt`, `attempt1-defect/`), `run1/cluster/` (`cluster-session.txt`, `jfr/T*.txt` parsed events, `*-reads.txt`, `*-heap-{before,after}.txt`, `*-sysprop.txt`, `*-jvmargs.txt`, `logs/T*/{system.log,stdout.txt,gc-humongous.txt}`, `analysis-cluster.txt`) | |

## 3. Runbook defects

| # | Step | Problem | Fix | Effect |
|---|---|---|---|---|
| S4-D1 | B2e step 3 (first probe JVM) | `ExceptionInInitializerError` from `FileUtils.<clinit>` at the first resize: `IllegalAccessException` on `jdk.internal.ref.Cleaner.clean` (JDK 11 module access) (`run1/unit/attempt1-defect/out-unset-bytes200.err`). Step 7's fallback does not address it. | Every probe JVM also takes the non-comment lines of `conf/jvm11-clients.options` (as `tools/bin` launchers do); probe source unchanged. Dated in section D. | B1/B2f/B2g unchanged; unit tier restarted from its beginning. |

No defect in the cluster tier.

## 4. Run 1

**Scope:** unit tier B2 as amended (22 growable JVMs + `fixed` + 5 repeats); cluster tier B3 as amended (one load, 6 node starts, 36 recorded queries). **Command log:** `run1/unit/probe-driver.out`, `run1/cluster/cluster-session.txt`. **Analyzers:** `harness/analyze_unit.py` → `run1/unit/analysis-unit.txt`; `harness/analyze_cluster.py` → `run1/cluster/analysis-cluster.txt`.

### 4.1 Readings

**Unit tier** (`run1/unit/out-*.txt`; every run printed the T it was given, 64 when unset; every final capacity equals B2f to the byte, with B2f's number of resizes)

| T | bytes 200: C (MiB) / C÷S / resizes | bytes 100: C (MiB) | rows 200: C (MiB) / C÷S / resizes | rows 100: C (MiB) | largest transient old+new (rows 200) |
|---|---|---|---|---|---|
| unset (read 64) | 288.00 / 1.440 / 14 | — | 216.01 / 1.080 / 10 | — | 360.02 MiB |
| 0 | 277.10 / 1.386 / 21 | 123.16 | 291.94 / 1.460 / 15 | 129.75 | 486.57 MiB |
| 16 | 243.00 / 1.215 / 15 | 108.00 | 273.39 / 1.367 / 12 | 121.51 | 455.65 MiB |
| 64 | 288.00 / 1.440 / 14 | 128.00 | 216.01 / 1.080 / 10 | 144.01 | 360.02 MiB |
| 128 | 256.00 / 1.280 / 13 | 128.00 | 288.01 / 1.440 / 10 | 128.01 | 480.02 MiB |
| 1024 | 256.00 / 1.280 / 13 | 128.00 | 256.01 / 1.280 / 9 | 128.01 | 384.02 MiB |
| fixed 200 (control) | `OVERFLOW position=1048576 capacity=1048576`, 0 resizes | | | | |

Every `EXPAND` step obeys `after = max(2·before, before+count)` while `before` ≤ T MiB and `max(⌊1.5·before⌋, before+count)` above it (e.g. T=64 `rows 200`: 64.00 → 96.00 → 144.01 → 216.01 MiB at ratio 1.5000). C(200)/C(100) is between 1.5 and 2.25 at every T and mode. The five `bytes 200` repeats are byte-identical (`REPEAT T=… identical`).

**Cluster tier** (`run1/cluster/jfr/T*.txt`; capacity = `allocationSize − 16`; load 200 rows, flushed, `Space used (live): 209741797`)

| T | property on the JVM (`jcmd`) | largest buffer per query, 3 queries (MiB) | B3f | step pattern from 1 MiB | fetch-100 control: largest per internal page (MiB), 3 queries | B3f control |
|---|---|---|---|---|---|---|
| unset | absent | 216.006 ×3 | ≈ 216.0 | 1, 2, …, 64, 96, 144, 216.01 | 144.004 ×3 | ≈ 144.0 |
| 0 | `=0` | 291.937 ×3 | ≈ 291.9 | 1, 1.5, 2.25, …, 194.62, 291.94 | 129.750 ×3 | — |
| 16 | `=16` | 273.383 ×3 | ≈ 273.4 | 1, 2, …, 16, 24, 36, …, 182.26, 273.38 | 121.504 ×3 | — |
| 64 | `=64` | 216.006 ×3 | ≈ 216.0 | as unset | 144.004 ×3 | ≈ 144.0 |
| 128 | `=128` | 288.008 ×3 | ≈ 288.0 | 1, 2, …, 128, 192.01, 288.01 | 128.004 ×3 | — |
| 1024 | `=1024` | 256.007 ×3 | ≈ 256.0 | 1, 2, …, 128, 256.01 | 128.004 ×3 | ≈ 128.0 |

Every recorded query returned a 1,048,576-byte value in 0.43–0.65 s (`*-reads.txt`). Each control query shows two internal 100-row pages, each growing from 1 MiB to the value above. The first recorded query of each T ran the local read on `Native-Transport-Requests-1`, the others on `ReadStage-2` (same sizes). 0 `^ERROR` lines in all six `system.log`s; heap region size 16 MiB (`gc-humongous.txt`); G1 humongous region counts at GC start reached 141–179 regions (≥ the amended ceil(C/16 MiB) = 14–19), consistent but not discriminating. JVM args per T: `-Xms4G -Xmx4G -XX:G1HeapRegionSize=16m -XX:FlightRecorderOptions=stackdepth=128` plus the `-D` for set T (`*-jvmargs.txt`).

### 4.2 Conclusion and logic

1. **Validity** — Valid. Unit: each JVM printed the T it was given (64 for unset) [observed: `out-*.txt` first line]; the fixed buffer overflowed, so the instrument sees a binding cap [observed: `out-fixed.txt`]. Cluster: the property was on each JVM as intended and absent for unset [observed: `*-sysprop.txt`, `*-jvmargs.txt`]; the data was a single 200-row partition [observed: `cluster-session.txt` tablestats]; JFR captured the `LocalDataResponse.build` resizes in every query [observed: `jfr/T*.txt`].
2. **Readings** — Unusual: none material. The local read ran on the request thread for the first query after each start, which the stack filter covers. The control's ratio sequence restarts at 1 MiB per internal page, as expected for a new buffer per page [observed].
3. **Matched row** — Unit B2g row 1 and row 5: (i) C ≥ S in all 20 growable runs; (ii) ratio rule holds on every `EXPAND`; (iii) C non-monotone in T (rows 200: 291.94 / 273.39 / 216.01 / 288.01 / 256.01 MiB); (iv) T read back, unset = 64; (v) C(200)/C(100) ∈ [1.5, 2.25]; every cell equals B2f to the byte; fixed overflows at 1 MiB [observed: `analysis-unit.txt`]. Cluster B3g row 1 and row 5: per T every query's C ≥ 200 MiB and within 0.01 MiB of B3f, ratio rule holds, three queries identical, C(64) 216.01 < C(1024) 256.01 < C(128) 288.01 MiB, unset = 64, and the fetch-100 control lowers C to 0.44–0.67 of paging-off at every T (≤ 0.75) [observed: `analysis-cluster.txt`].
4. **Excluded rows** — Unit row 2 (C < S, or growth stops near T): C ≥ S everywhere and growth never stopped (written = S in every run) [observed]. The S4-A2 numeric form "C ≤ 2·T MiB for some T ∈ {16, 64, 128}" is satisfied at T = 128 `bytes 200` (256.00 ≤ 256 MiB), but this is the value B2f itself predicts for row 1 and equal to the uncapped T = 1024 value; with S = 200 MiB < 2·128 MiB the test cannot tell a cap from no cap there. This is an error in my S4-A2 wording, not a cap; it is recorded here and as R-b, and the amendment is not edited after the reading. For T = 16 and 64, where S > 2T, C (243.00–288.00 MiB) is far above 2T (32, 128 MiB) [observed]. Row 3 (proportional to T): C not increasing over T [observed]. Row 4 (not applied): T read back differs per run [observed]. Row 6 (fixed does not overflow): it overflows [observed]. Cluster row 2 (C ≤ 2T for T=16 or 64): 273.38 > 32 and 216.01 > 128 MiB [observed]. Row 3: not monotone [observed]. Row 4 (not applied): property present and values differ [observed]. Row 6 (control does not reduce C): 0.44–0.67 [observed]. Row 7 (query fails): none failed [observed].
5. **Observed vs. inferred** — Inferred: (i) that the JFR `allocationSize − 16` equals the buffer capacity (16-byte array header on 64-bit HotSpot with compressed class pointers; the unit tier's exact capacities, e.g. 226,503,648 B vs JFR 226,498,696 − 16 for the cluster's slightly different header bytes, agree to within the serialization difference) [inferred]; (ii) that the old array is garbage after each resize, so the transient peak is old + new (code reading of `expandToFit`; not measured) [inferred]. Neither affects the verdict: the claim concerns the size of the allocation, which is observed.
6. **Deviations and gaps** — S4-A1–S4-A4 and S4-D1 (sections 1, 3). B2e step 8 (off-heap `SafeMemoryWriter`) not run. The cluster capacities differ from the unit `rows 200` values by a few KB (the real row header), as B3f allows. GC-log humongous counts are only consistent, not discriminating (buffers from several queries coexist between GCs). Run on x86_64 (`pc75`), not the aarch64 m400s of the interrupted attempt; the design is architecture-independent (deterministic arithmetic).
7. **Core question** — The constraint does not cap usage. For a fixed 200 MiB payload, every T from 0 to 1024 lets the buffer grow past the payload (216–292 MiB in the node), and the peak is not ordered by T (the default 64 gives the smallest, 128 the largest); T only switches the growth factor between x2 and x1.5, which both tiers show at every step. A real limit on the same buffer (fixed capacity; page size) moves the same instruments.

**Conclusion (one line):** Unit B2g row 1/5, cluster B3g row 1/5 — claim confirmed: `cassandra.DOB_DOUBLING_THRESHOLD_MB` sets only the growth factor of `DataOutputBuffer`; the buffer always reaches at least the bytes written, and its peak is not capped by, nor monotone in, the knob (effect: does not cap).

## 5. Self-check of run 1 — AI

Re-read by hand, not from the analyzers: `out-T128-bytes200.txt` (T 128, C 268,435,456), `out-T0-rows200.txt` (C 306,125,095), `out-T16-rows200.txt` (C 286,668,679), `out-T64-rows200.txt` (the ten `EXPAND` lines, 1.5000 from 64 MiB up), `out-fixed.txt`; `jfr/T128.txt` (tail 134,221,456 → 201,332,176 → 301,998,256 B), `jfr/T16.txt` (191,108,280 → 286,662,408 B), `jfr/T1024-ctl.txt` (two pages ending at 134,221,456 / 134,221,840 B), `T1024-ctl-reads.txt` and `T16-reads.txt` (len 1048576 ×3), `T*-sysprop.txt`, the six `system.log` `^ERROR` counts (0).

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | Property read back in both tiers; fixed control overflows; JFR events present. |
| 2. Readings | yes | Re-read numbers above match the tables. |
| 3. Matched row | yes | Every number of both rows re-read; B2f cells checked by the analyzer and spot-checked by hand. |
| 4. Excluded rows | yes, with a note | The S4-A2 row-2 threshold misfires at T = 128 (2T > S); handled openly in part 4, and the original B2g row-2 wording is not met. |
| 5. Observed vs. inferred | yes | The verdict rests on observed allocation sizes. |
| 6. Deviations and gaps | yes | Amendments, defect, skipped optional step stated. |
| 7. Core question | yes | B1 → B2/B3 runbooks → B2f/B3f → B2g/B3g row 1/5, positive controls moving. |

### 5.2 Run 2?

**No** (2026-11-25). The code is deterministic and both tiers match the pre-run predictions to the byte (unit) or within 0.01 MiB (cluster), repeats are identical, the positive controls move, and the result neither refutes the case nor confirms a bypass.

## 6. Run 2 — not done. ## 7. Comparison — not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap): both tiers Confirmed with effect `does not cap`.

**Claim tested:** (B1) For a growable `DataOutputBuffer` that receives S bytes, the final capacity C ≥ S for every value T of `cassandra.DOB_DOUBLING_THRESHOLD_MB`; T only sets the step ratio (x2 at or below T MiB, x1.5 above), so usage is neither capped at or near T nor monotone in T; on a node the `LocalDataResponse.build` buffer for a ~200 MiB page is ≥ 200 MiB at every T, and halving the page roughly halves it.

| Tier | Verdict | Effect | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1 / row 5: **Confirmed** — 20 growable runs equal B2f to the byte; C ≥ S; rows 200 C = 291.94 / 273.39 / 216.01 / 288.01 / 256.01 MiB for T = 0 / 16 / 64 / 128 / 1024; unset = 64; fixed buffer overflows at 1 MiB | does not cap | run 1 (after S4-D1) + self-check | 2026-11-25 |
| Cluster | B3g row 1 / row 5: **Confirmed** — read buffer 216.01 / 291.94 / 273.38 / 216.01 / 288.01 / 256.01 MiB for T = unset / 0 / 16 / 64 / 128 / 1024 (3 identical queries each); fetch-100 control 144.00 / 129.75 / 121.50 / 144.00 / 128.00 / 128.00 MiB | does not cap | run 1 + self-check | 2026-11-25 |

**Positive control:** unit `DataOutputBufferFixed(1 MiB)` → `OVERFLOW` at 1,048,576 B; cluster page size 100 rows → peak buffer 0.44–0.67 of the 200-row page at every T.

**Feedback filed:** the amended case file's section D (`/users/jason92/writeup-ext/out/o119/case-amended.md`: amendments S4-A1–S4-A4, runbook defect S4-D1, and the stage-4 result paragraph). No section of the trace was refuted. **Doc note:** `cassandra.DOB_DOUBLING_THRESHOLD_MB` is a growth-policy switch, not a memory limit; for the same 200 MiB page the peak buffer ranged from 216 MiB (default 64) to 292 MiB (T = 0), and transient old+new reached 360–487 MiB. **Leftovers on pc75:** nothing running (no CassandraDaemon, probe, JFR parser, driver or `dob.py`; ports 7000/7199/9042/9091 free); the source copy and node data removed, `.jfr` files deleted after parsing; kept `/mydata/jingsong-cass-s4/o119/{probe,attempt1-defect,jfr,logs,harness,probe-driver.out,cluster-driver.out,cluster-session.txt}` (7.7 MB). Driver PID file removed after the driver exited; node lock released at the end. The other folder on the node, `/mydata/jingsong-cass-s4/o114`, belongs to another run and was not touched.
