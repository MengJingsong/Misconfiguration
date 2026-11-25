# maxSSTableSizeInMiB-withMaxSSTableSizeInMiB-size--autonomous — stage-4 results  <!-- file: results/maxSSTableSizeInMiB-withMaxSSTableSizeInMiB-size--autonomous.md -->

> **Case:** [`maxSSTableSizeInMiB-withMaxSSTableSizeInMiB-size--autonomous`](../../stage3-ai-deep-read/cases/maxSSTableSizeInMiB-withMaxSSTableSizeInMiB-size--autonomous.md) (stage-3 order o114, `writeup-set-ext.csv`; amended working copy `~/writeup-ext/out/o114/case-amended.md`, outside the repo)
>
> **Status:** self-checked, verdict filed by the stage-4 session (2026-11-25); run 2 not chosen
>
> **Outcome class:** true positive (estimate `positive`; unit **Confirmed — caps (bypass recorded)**, client-process tier **Confirmed — caps**)
>
> **Agent:** autonomous. "§9a" means B2f/B2g (unit) and B3f/B3g (client-process tier, which replaces the cluster tier: B3 is
> `n/a` for a running node because `CQLSSTableWriter` is a client library); "§9b–§9e" means B2a–B2e / B3a–B3e; the case
> file's feedback section is section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `cd9e1cded`; the case file is committed (`bef6bc8a6`). Filing sha256 `b0fc5eddbb80ef89733c4b9aaf116fafa1dce0371faefe1f39b2d951a74b5064` (equal to `_INDEX.md` §4; copy `harness/case-as-filed.md`). After the audit's amendments S4-A1 to S4-A3 (section D only, 2026-11-25 ~05:25 UTC, before any reading): `9321c31e45509c46be09ac440756d982d733aebfcd16fa40090fae5e1b30c7f0`. Frozen prediction text (B2f–B2h, B3f–B3h, the amendments; `harness/freeze-pred.txt`): `5cf348d3b6f04ba76b85f80f0352130f7d592785d0a710cb853dae3f28b0e6c7`. B2f/B2g/B3f/B3g are byte-identical to the filed version (only section D changed: `diff` shows one hunk at line 510). Final sha256 after D1 and the result paragraph: `125e51c201b0ae7f6200f0fdef57e37c3232009eb0c64a59eaf2849efeeab3b2`. |
| **Harness** | `~/writeup-ext/out/o114/harness/` (to become `harness/maxSSTableSizeInMiB-withMaxSSTableSizeInMiB-size--autonomous/`): `MaxSizeProbe.java` and `run.sh` extracted verbatim from B2a (plus one `data_by_id=` output line, S4-A1), `unit-all.sh` (B2e), `cluster-all.sh` (B3e 1–3), `validity.sh` (B3e 4–5, with D1), `analyze.py`, `md5.txt`, `freeze.sha256`, `freeze-pred.txt`, `case-as-filed.md`. Not committed by this session. **Instrument check** (`run1/instrument-check.log`): md5 of the deployed files OK; `javac` clean; known-answer runs with 2,048 rows at L = 1 MiB: unsorted `EFFECTIVE_LIMIT_BYTES 1048576`, `first_row_delta` 1,062, syncs 2, 3 files (2 × 1,037,400 + 75,600 B); sorted 2 switches at 1,048,950 B, 3 files — as expected for 2.07 MiB of data. |
| **Tiers and values** | Unit (B2): unsorted insert L ∈ {1, 4, 16} MiB, N = 65,536 × 1 KiB; default handling L ∈ {unset, 0, −1} for both modes, N = 196,608; sorted insert L ∈ {1, 4, 16}; bypass: unsorted delete-only, L = 1, N = 262,144. Client-process tier (B3): unsorted L ∈ {16, 64, unset (128), 256} plus positive control 1024, sorted L ∈ {16, 256}, N = 524,288 × 1 KiB, `-Xms2g -Xmx2g` G1, heap sampled after `System.gc()` every 8,192 rows; heap ceiling `-Xmx320m` L ∈ {16, 256}; optional validity load into one node (Murmur3, L = 16). |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 (S4-A1 to S4-A3 in the case file's section D) |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: unsorted — heap of the row buffer (via serialized bytes) and per-file Data.db bytes; sorted — per-file Data.db bytes. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b 1/4/16 and unset/0/−1; B3b 16/64/unset(128)/256 + 1024. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2 reads the operand (`currentSize`, `getOnDiskBytesWritten`) and the files; B3 measures live heap after forced GC, the G1 log and the files; the gap (instantaneous peak between samples, split between the two buffers) is named in B3d. |
| A. Core question | usage driven to the limit and past it | Met | B2c T ≈ 67–74 × L at L = 1; B3c T ≈ 531 MiB vs L ≤ 256; control L = 1024 > T. |
| B. Logic | each step says what it establishes | Met | B2h/B3h. |
| B. Logic | prediction in numbers | Met | B2f table (exact limits, operand bands, ±1 counts, size bands); B3f ratio band, ≥ 150 MiB, ≤ 80 MiB, 3%, OOM split. |
| B. Logic | every plausible outcome has a row | Partly → Met after S4-A2, S4-A3 | No verdict labels; "far above 4", "flat", "rises", "does not change with L" undefined. Thresholds and labels added before any reading; B2f/B2g/B3f/B3g text unchanged. |
| B. Logic | confirmation needs ceiling-follows-knob and disallow evidence | Met | Unit: `max_operand` ≤ L and the reset count (`syncs`) is the disallow branch (`sync()`); sorted: `min_at_switch` is the operand at the switch. B3: heap ladder plus the OOM split. |
| B. Logic | alternative explanations and controls | Met | L = 1024 positive control (instrument sees growth), sorted contrast (growth comes from the buffer), `EFFECTIVE_LIMIT_BYTES` printed, fresh output dir per run, `-Xms = -Xmx`. |
| C. Specific | understandable from the intro and B1 | Met | Estimate line, A3, B1. |
| C. Specific | an AI can run the runbook without re-deriving | Partly → Met after S4-A1 | Paths and the built copy on this node; `data_sizes` is sorted by size, so "all but the last" needed generation order (`data_by_id`). |
| C. Specific | values, commands, observables exact | Met | B2e, B3e in full. |
| D. Runnable | prerequisites exist | Met | JDK 11.0.33, Ant 1.10.12, built 5.0.9 copy `/mydata/s4/cassandra-base` (md5 of `CQLSSTableWriter.java`, `SSTableSimpleUnsortedWriter.java`, `SSTableSimpleWriter.java`, `AbstractSSTableSimpleWriter.java`, `DeleteStatement.java`, `build.xml` equal to the repository's `systems/cassandra/source`). |
| D. Runnable | workload arithmetic reaches the limit | Met | ≤ 600 MiB output per run, 700 GB free on `/mydata`; 2 GiB heaps on a 125 GiB node. |
| D. Runnable | citations spot-checked | Met | `CQLSSTableWriter.java:131-138` (client init), `:395`, `:407`, `:539-545`, `:563-587`, `:677-680`, `:738-740`, `:761-764`; `SSTableSimpleUnsortedWriter.java:68` (`newBlockingQueue(0)`), `:74`, `:89`, `:103`, `:110`, `:153-178`, `:206-237`; `SSTableSimpleWriter.java:70`, `:105`; `BlockingQueues.java:43-47` (SynchronousQueue for 0); `DeleteStatement.java:72` (`addPartitionDeletion`, no `add(Row)`). All as cited. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| S4-A1 | `WORK=/mydata/jingsong-cass-s4/o114`, `cp -a` of the built base instead of rsync + `ant jar`; `data_by_id=` line in `run.sh`; validity-node yaml dirs, timeouts, `ulimit -n 100000`, `CASSANDRA_CONF` for tools | applied 2026-11-25, before any reading | runnable on this node; "the last file" made observable |
| S4-A2 | B2g verdict labels and thresholds (core verdict from insert runs; default handling and bypass as sub-findings feeding the Effect field) | applied 2026-11-25, before any reading | undefined labels |
| S4-A3 | B3g verdict labels and thresholds ("flat" ≤ 32 MiB, control rises ≥ 0.8·T, "far above 4" > 4.0; Confirmed / Partial / Refuted / Not confirmed) | applied 2026-11-25, before any reading | undefined words |
| R-a | Instrument the DiskWriter side (a heap histogram of `PartitionUpdate$Builder` count, or a sample from a second thread) to show directly how many buffers are live | left for stage 3 | the two-buffer reading is inferred (see §4.2 part 5) |
| R-b | The sorted contrast's P is below zero because H0 comes from an unsorted run; take each mode's own minimum as its baseline | left for stage 3 | cosmetic; the criteria hold either way |
| R-c | Validity step: set `native_transport_timeout` with the other timeouts (D1) | applied to the step (D1) | 5.0 default 12 s |

**Agreement criteria** — run 2 not planned.

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-11-25 UTC: instrument check ~05:28; unit 05:29:47–05:30:45; client-process 05:31:07–~05:32:30; validity attempt 1 ~05:32:30–05:34:37 (D1), attempt 2 ~05:35–05:37 | not done |
| Node | `pc75` (`node4` of experiment `jason92-326528`, UMass), **x86_64**, 40 cores, 125 GiB RAM, `/mydata` 753 GB (700 GB free); held under `/mydata/s4/NODE-LOCK` for the whole run (acquired 22:26 MST = 05:26 UTC, released after cleanup) | |
| OS / kernel | Ubuntu 22.04 / `5.15.0-203-generic` | |
| JDK / Ant | openjdk 11.0.33 (2026-10-20) / Ant 1.10.12 | |
| Local source copy | `cp -a /mydata/s4/cassandra-base` → `/mydata/jingsong-cass-s4/o114/src` (5.0.9, built; md5-checked against repo `systems/cassandra/source`, repo HEAD `cd9e1cded`, source clean); deleted after the run | |
| Case-file commit / harness commit | `bef6bc8a6` / harness not committed (outside the repo) | |
| Storage | probe output under `/mydata/jingsong-cass-s4/o114/out` (deleted per run by `run.sh`, rest at the end); validity node under `.../o114/node` (deleted) | |
| Full logs | node: `/mydata/jingsong-cass-s4/o114/logs/` (1.3 MB kept); copy: `~/writeup-ext/out/o114/run1/logs/` (driver logs, per-run logs, G1 logs, loader and node logs); analysis `run1/analysis.txt` | |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | 1 | B3e 4.5 (optional validity) | `SELECT count(*)` → `ReadTimeout` after 12 s (`driver-validity-attempt1.log`; node log `p-m3-node-system-attempt1.log` line 687) although read/range timeouts were 120 s: 5.0's `native_transport_timeout` (default 12 s, `Config.java:1399`) bounds the whole request | `native_transport_timeout: 600s` in the validity node's yaml; step 4 rerun from its beginning | 2026-11-25; B3f/B3g unchanged (step is optional, feeds only B3h "valid output") | section D of `case-amended.md` (working copy; not committed) |

## 4. Run 1

**Scope:** both tiers, all values in B2b and B3b, plus the optional validity step. **Command log:** `run1/logs/driver-unit.log`,
`driver-cluster.log`, `driver-validity.log` (attempt 1: `driver-validity-attempt1.log`); every command echoed by `set -x`.

### 4.1 Readings

**Unit tier** (s = `first_row_delta` = 1,062 B; N·s = 69,599,232 B ≈ 66.4 MiB for N = 65,536)

| Run | Result | Evidence |
|---|---|---|
| u-ins-1 | limit 1,048,576; `max_operand` 1,048,194 (in (L − s, L]); syncs 66 (n − 1 = 66); 67 files (n = 67); non-last files all 1,037,400 B (0.99 L); last 344,400 | `driver-unit.log`, `u-ins-1.log`, `analysis.txt` |
| u-ins-4 | limit 4,194,304; `max_operand` 4,193,838; syncs 16; 17 files; non-last 4,147,500 B (0.99 L) | same |
| u-ins-16 | limit 16,777,216; `max_operand` 16,776,414; syncs 4; 5 files; non-last 16,587,900 B (0.99 L) | same |
| u-def-unset / 0 / −1 | limit **134,217,728** in all three; `max_operand` 134,217,684; syncs 1; **2** files, first 132,702,150 B (126.6 MiB); warning "…disables the size limiting effectively…" logged for `0` and `−1` (not for unset) | `driver-unit.log`, `u-def-0.log`, `u-def--1.log` |
| s-def-unset / 0 / −1 | limit −1,048,576; switches 0; **1** file of 206,438,400 B | `driver-unit.log` |
| s-ins-1 / 4 / 16 | limit L·2^20; switches 65 / 16 / 4 = files − 1; 66 / 17 / 5 files; every non-last file and `min_at_switch` = 1,048,950 / 4,194,750 / 16,777,950 B, i.e. L + 374 / + 446 / + 734 B (s_disk = 1,050 B) | `driver-unit.log`, `analysis.txt` |
| u-del-1 | limit 1,048,576; `first_row_delta` 26; `max_operand` **6,815,744** (6.5 × L); **syncs 0**; **1** file of 6,029,312 B | `driver-unit.log`, `u-del-1.log` |

**Client-process tier** (H0 = `min_live_heap` of p-u-16 = 22,400,936 B = 21.4 MiB; T = 524,288 × 1,062 = 556,793,856 B = 531.0 MiB)

| L | Run | Observable | Reading | Evidence |
|---|---|---|---|---|
| 16 | p-u-16 | P / P/L; syncs; files; du | 39.1 MiB / 2.45; 33; 34 (pred 34 ± 1); 558,781,780 | `p-u-16.log`, `driver-cluster.log`, `analysis.txt` |
| 64 | p-u-64 | same | 173.0 MiB / 2.70; 8; 9; 558,561,816 | `p-u-64.log` |
| unset (128) | p-u-unset | same | 352.0 MiB / 2.75; 4; 5; 558,528,289 | `p-u-unset.log` |
| 256 | p-u-256 | same | 722.1 MiB / 2.82; 2; 3; 558,511,493 | `p-u-256.log` |
| 1024 | p-u-1024 (positive control) | last sample above H0; syncs; files | 752.1 MiB (≥ 0.8·T = 424.8); 0; 1; samples rise linearly, ~96 MiB per 65,536 rows (0, 96, 191, 287, 382, 478, 573, 669, last 752) | `p-u-1024.log` |
| 16 / 256 | p-s-16 / p-s-256 (sorted) | P; files; non-last sizes | −6.1 / −6.1 MiB (max live 16.0 MiB both); 33 / 3 files; L + 734 / L + 194 B | `p-s-*.log`, `analysis.txt` |
| all | — | `du_bytes` spread | 0.05% (558.51–558.78 MB) | `analysis.txt` |
| 16 | p-oom-16 (`-Xmx320m`) | exit | 0, 34 files | `p-oom-16.log` |
| 256 | p-oom-256 (`-Xmx320m`) | exit | 1, `java.lang.OutOfMemoryError` in `main`, no summary | `p-oom-256.log` |
| — | G1 log cross-check | max heap after `Pause Full` | 60 / 194 / 373 / 743 / 773 MiB (p-u 16 / 64 / unset / 256 / 1024); sorted 15 MiB | `p-*-gc.log` |
| 16 (Murmur3) | validity | loader; count | `sstableloader` exit 0, 532.8 MiB transferred; `count = 524288` | `driver-validity.log`, `p-m3-loader.log` |

### 4.2 Conclusion and logic

1. **Validity.** Every run exited 0 except the predicted OOM run [observed: `driver-unit.log`, `driver-cluster.log`]. Limits
   were reached many times (syncs 66/16/4 unit; 33/8/4/2 client tier) [observed: same]. The knob reached the writer as
   intended: `EFFECTIVE_LIMIT_BYTES` printed per run equals L·2^20 or the normalised default [observed]. Only L changed:
   same N, seed 42, schema, and JVM flags per tier [observed: `set -x` lines in the driver logs]. The run is valid.
2. **Readings.** No gaps or outliers. The p-u samples form a sawtooth whose troughs after the first flush stay at about
   one buffer above H0 (p-u-unset: 96, 191, 292, 204, 299, 211, 306) [observed: `analysis.txt`]. The sorted P is negative
   only because H0 comes from an unsorted run (sorted live set 15.2–16.0 MiB vs 21.4 MiB) [observed: `p-s-*.log`].
3. **Matched rows.** *Unit:* B2g row 1 ("max_operand ≤ limit, syncs and file count scale as 1/L, file sizes ≈ L") — every
   u-ins and s-ins criterion of S4-A2 passes (`analysis.txt`, 0 FAIL); row 5 (u-def: 2 files and 134,217,728 also for 0 and
   −1); row 7 (u-del-1: syncs 0, `max_operand` 6.5 × L) [observed]. → **Confirmed — caps**, bypass confirmed.
   *Client tier:* B3g row 1 ("P rises with L within the stated ratio band, and the L = 1024 control rises") — strictly
   increasing P, ratios 2.70–2.82 in [0.6, 4.0], P(256) − P(64) = 549 ≥ 150, P(16) = 39.1 ≤ 80, control 752 ≥ 425 with
   syncs 0; disk bullets hold; and row 5 ("L = 16 passes and L = 256 runs out of memory") [observed]. → **Confirmed — caps**.
4. **Excluded rows.** Unit row 2 (operand above limit / syncs 0 with T > L on insert): max operand ≤ L, syncs > 0. Row 3
   (file count flat): 67 vs 5 (13.4×). Row 4 (default differs): limit 134,217,728, 2 files. Row 6 (sorted switch wrong):
   every non-last file in (L, L + 2,048]. Row 8 (bypass refuted): syncs 0. Last row (operand far below L): within 1,062 B of
   L. Client row 2 / 3 (flat P): spread 683 MiB. Row 4 (P/L > 4): max 2.82. Rows 6/7 (both pass / both OOM): split as
   predicted. Row 8 (disk does not track / du > 3%): counts ±0, spread 0.05%. Row 9 (sorted > 32 MiB): diff 0.0 MiB.
   [observed: `analysis.txt`]
5. **Observed vs. inferred.** (a) P/L ≈ 2.8 ≈ 2 × the per-byte overhead 1.42 measured by the control means about two
   full buffers are live at the peak [inferred: arithmetic from p-u-1024 and p-u-L; the split between buffers is not
   instrumented]. (b) The troughs never return to H0 after the first flush, consistent with the DiskWriter's local `b`
   (`SSTableSimpleUnsortedWriter.java:216`) still referencing the last written buffer while it blocks in `take()`
   [inferred: source reading; not instrumented]. Neither (a) nor (b) is needed for the verdict: the verdict rests on the
   observed ladder and band criteria; (a)/(b) only explain the multiplier, which B3f already allowed ("two buffers").
6. **Deviations and gaps.** S4-A1 paths/build and an added output line; D1 in the optional step (rerun, passed). The
   instantaneous peak between samples is not observed (B3d), so true peaks may exceed P slightly; the ceiling runs bound it
   from the other side (L = 256 cannot fit in 320 MiB). Heap is not measured in the unit tier (by design).
7. **Core question.** Usage follows the constraint: the check's operand is held at or below L before each flush and the
   flush count and file sizes scale with 1/L and L (parts 3, unit); live heap of the writer process rises linearly with L
   at ≈ 2.8 heap bytes per byte of L, while the same workload with L above the data volume grows with the rows and the
   sorted writer stays flat (parts 1, 3); lowering L avoids an OOM that a larger L hits (part 3). So the value caps heap
   (unsorted) and per-file disk (both modes), not total disk, and it has a bypass: partition deletes are not counted and
   never flush (part 3, u-del-1).

**Conclusion (one line):** unit B2g row 1 (+ rows 5 and 7) — confirmed, bypass as recorded; client tier B3g row 1 (+ row 5) — confirmed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-read `driver-unit.log` (all 13 `exit=0`, `no probe left`), `driver-cluster.log` (8 × exit 0, p-oom-256 exit 1), the `WRITER` lines. |
| 2. Readings | yes | Re-read the `HEAP_SAMPLE` lines of `p-u-256.log` (max 779,527,352 at row 499,712), `p-u-16.log` (min 22,400,936 at row 8,192), `p-u-1024.log` (last 811,022,336 at row 524,288); G1 `Pause Full` maxima agree to ≤ 1 MiB. |
| 3. Matched row | yes | `analysis.txt` recomputed from the copied logs: 28 PASS, 0 FAIL; the u-def `0`/`−1` warning re-read in `u-def-0.log`. |
| 4. Excluded rows | yes | Each excluded row checked against a number in `analysis.txt`. |
| 5. Observed vs. inferred | yes | The two inferred statements explain the multiplier only; the verdict criteria (S4-A2/A3) use observed numbers. |
| 6. Deviations and gaps | yes | D1 confined to the optional step; `count = 524288` re-read in `driver-validity.log`. |
| 7. Core question | yes | The steps follow B1: operand bounded → files track L → heap tracks L (with control and sorted contrast) → OOM avoided; bypass confirmed on its own probe. |

### 5.2 Run 2?

**No** — 2026-11-25. Every criterion is met with wide margins by observed numbers, the result does not refute the case, and
the confirmed bypass was predicted by the file itself and is directly observed (syncs = 0, operand 6.5 × L), not inferred.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** **true positive** — estimate `positive`, effect `caps` in both tiers (with a recorded bypass, which `caps` includes).

**Claim tested (B1):** in the unsorted writer, `withMaxSSTableSizeInMiB(L)` keeps the buffered serialized size at or below
L MiB before each flush, so live heap rises with L (up to about one or two buffers × overhead), each output Data.db is about
L MiB, and total output does not depend on L; in the sorted writer each finished Data.db is larger than L by at most one
partition and heap does not depend on L.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g row 1; default handling row 5: a non-positive value keeps 128 MiB in the unsorted writer, the warning is misleading; bypass row 7 confirmed) | caps (bypass: delete-only workloads are not counted and never flush) | run 1 + self-check | 2026-11-25 |
| Cluster (client-process tier; running-node tier n/a — client library) | **Confirmed** (B3g row 1 and row 5) | caps (heap ≈ 2.8 × L for 1 KiB rows; per-file disk ≈ L; total disk not capped) | run 1 + self-check | 2026-11-25 |

**Feedback filed:** section D of the amended working copy `~/writeup-ext/out/o114/case-amended.md` (S4-A1 to S4-A3, D1,
and the result paragraph). Not written to the repository and not committed (this session does not edit the repo);
`_INDEX.md`, `writeup-set-ext.csv` and `HANDOFF.md` rows are left for the orchestrator.
