# write_buffer_size-append-hint--autonomous — stage-4 results  <!-- file: results/write_buffer_size-append-hint--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`write_buffer_size-append-hint--autonomous`](../../stage3-ai-deep-read/cases/write_buffer_size-append-hint--autonomous.md)
>
> **Status:** **Closed 2026-10-28 — unit Confirmed, cluster Confirmed — does not cap** (estimate negative, matched); no run 2
>
> **Outcome class:** true negative — stage-3 estimate vs the stage-4 effect on the constraint
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments: `fe0f472ffe3420673f915745af1ccaa1b9b021d36851c37a8965e4d159d79214` (`sha256sum`, run 2026-10-28 before any harness check or run, after the block "Audit amendments (stage 4 step 0, 2026-10-28)" R1-R5 in the file). The file before the amendments had sha256 `b1f2e537d2450b05301d11e84c37ba7e44bf0f69982efd70552ac8fc755ad1b7` (in `b68711e5`). The amended file is not committed by this session. |
| **Harness** | [`harness/write_buffer_size-append-hint--autonomous/`](../harness/write_buffer_size-append-hint--autonomous/README.md), written 2026-10-28; not committed by this session. |
| **Tiers and values** | Unit (B2): own direct aggregation buffer N = 64 KiB · 256 KiB · 1 MiB x hint size h = 1 KiB · 100 KiB · 300 KiB · 2 MiB, 3 reps, count = min(20000, ceil(256 MiB / (h + 12))); control: `HintsBuffer.create` 32 MiB vs 64 MiB. Cluster (B3): builds with `WRITE_BUFFER_SIZE` = 64 KiB · 256 KiB (stock) · 1 MiB x payload 1 KiB · 400 KiB x 2 reps, 1 GiB of values per arm; controls on the stock build with the 1 KiB workload: `commitlog_segment_size` 128MiB, `max_hints_size_per_host` 64MiB. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: direct memory of one fixed buffer; B1 adds the hint bytes on disk. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | The constant cannot be set (A1): unit varies the buffer size (64 KiB · 256 KiB · 1 MiB) and four hint sizes; cluster varies the build (B3a). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d direct pool, B3d pool / NMT / RSS / `du`; B3d names that the buffer alone is not observable and the build difference is the signal. |
| A. Core question | usage driven to the limit and past it | Met | 1 GiB of hints per arm against a 256 KiB buffer and 32 MiB slabs; hints both below and above the buffer. |
| B. Logic | each step says what it establishes | Met | B2e / B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after R1, R2 | B2c's count formula "2 GiB / hint size capped at 20000 so total is a few hundred MiB" is inconsistent (2 GiB for the 2 MiB and 300 KiB cells); B3f's 400 KiB sentence is wrong for the 1 MiB build (a 400 KiB hint fits it). Both are arithmetic, corrected. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → Met after R4 | The "not distinguishable" row exists, but a pool total that moves by whole slabs is a likely outcome (previous closed case: 1–3 slabs) and had a row only by implication; row added, the existing one clarified. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Oversized hints written through, file identical, memory and disk controls move. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: slab size (memory) and `max_hints_size_per_host` (disk) as positive controls, an unmodified build as reference, repeats. |
| C. Specific | a human can follow it from the intro and §9a | Met | A1–A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met | Runnable with the amendment block (observation of channel writes, entry shape). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after R1, R3 | B3e step 4 says "same wall-clock length" while B3c fixes the volume; B2's count formula; control run counts. Fixed in the amendment block. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | The previous case's cluster driver, client, JMX tool and Byteman rules are reusable; probe test, builds, multi-build driver are step-1 work. pc29: JDK 11.0.32.1, Ant 1.10.12, 52 GB free. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 14 arms x 1 GiB of hints + 1 GiB of data, reset between arms; the 128 MiB-segment control needs up to 3 x 128 MiB slabs under `MaxDirectMemorySize=1G` (B4). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Re-read in `cassandra/cassandra-5.0.9/`: `HintsWriteExecutor.java:50,60,239-247`; `HintsWriter.java:136,167,174-181,200-222,277-286`; `HintsBuffer.java:58,77,150-157`; `HintsService.java:79,110`; `DatabaseDescriptor.java:898-901`; `Config.java:446-448`; `conf/cassandra.yaml:102,106,111,660`. All hold. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | B2c/B2e: count formula, direct entries, counting writer, CRC check, three pool readings | Applied 2026-10-28 (B2c, B2e, amendment block; not committed) | inconsistent arithmetic; unstated instrument |
| R2 | B3f: 400 KiB sentence, the 1 MiB build does not bypass | Applied 2026-10-28 (B3f) | source arithmetic |
| R3 | B3e step 4: volume, not wall-clock; run counts and controls once | Applied 2026-10-28 (B3e step 4, amendment block) | B3c and B3e disagreed |
| R4 | B3g: row for a pool total that moves by whole slabs | Applied 2026-10-28 (B3g) | likely outcome without a row |
| R5 | Note the 128 MiB-segment control's direct memory budget | Applied 2026-10-28 (amendment block) | against `MaxDirectMemorySize=1G` |

**Agreement criteria** — run 2 is not planned (decided in §5.2 after run 1).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-28 (node clock, MDT): unit 10:37–10:39; cluster 10:39–12:02; instrument shakedowns earlier the same morning (not counted) | not done |
| Node (CloudLab name and type) | `pc29` = `node3.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB). Both Cassandra nodes on this host on loopback: A = 127.0.0.2 (JMX 7102, measured), B = 127.0.0.3 (JMX 7103) | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` | — |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18) | — |
| Ant (`ant -version`) | 1.10.12 | — |
| Local source copy | `~/s4-hwb/base` made by `copy-source.sh` from `cassandra/cassandra-5.0.9/` at repository commit `b68711e5` (local tag `cassandra-5.0.9`, baseline `055dd3e`), `ant build-test`; variants `~/s4-hwb/var-64k`, `var-1024k` = `cp -a` with `HintsWriteExecutor.java:50` edited and `ant jar`; constants confirmed with `javap -constants` (65536 / 262144 / 1048576, `summary.txt`) | — |
| Case-file commit / harness commit | case file sha256 `fe0f472f…` (verified before run 1); nothing committed by this session | — |
| Storage for node data | `~/s4-hwb/n-hwb2/{A,B}` on local `/dev/sda3` (49 GB free after the run) | — |
| Full logs (path, outside the repo) | `pc29:~/s4-hwb/logs/write_buffer_size-append-hint--autonomous/run1/` (`unit/`, `cluster/`); chain log `~/s4-hwb/logs/chain.log` | — |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | instrument check (unit shakedown1) | B2d (harness) | (a) `Session.append` calls `writeBuffer` on an empty buffer before every oversized entry (flush at `HintsWriter.java:205-209`), so the call count of a through-written hint is 2 (one of 0 B); (b) the direct pool occasionally fell between P1 and P2 (−10,368 B, count −2) when GC released an unrelated buffer, failing a `== 0` check. | (a) zero-length calls counted apart; (b) the check reads "no growth" (`<= 0`); no cell of run 1 showed a decrease. Instrument only. | 2026-10-28 | none |
| D2 | cluster shakedown (case 1's harness, shared code) | harness | `asamp` sampling and the appended-bytes expectation, as in the sibling case. | `== 1`; appended bytes + 42 B per file = bytes on disk. | 2026-10-28 | none |

No step of B2/B3 failed to run as written after the audit's amendments (R1–R5, §1). The cluster driver of this case was not shaken down separately; its code is the sibling case's, with this case's builds, payloads, 1000 ms flush period and controls.

## 4. Run 1

**Scope:** unit tier B2 (3 N x 4 h x 3 reps = 36 cells, control slab 32 / 64 MiB) and cluster tier B3 (3 builds x 2 payloads x 2 reps = 12 arms of 1 GiB, two controls, control with B up). **Command log:** [`write_buffer_size-append-hint--autonomous/run1/`](write_buffer_size-append-hint--autonomous/run1/) (`unit/summary.txt`, `unit/test-nonappend.out`, `cluster/summary.txt`, `analysis.txt`, `arms.json`, `A-yaml-tail.txt`, `selfcheck.py`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (probe 1/1 passed, upstream `HintsReaderTest` 4/4; 333 checks, 333 ok, 0 errors — `unit/summary.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| `WRITE_BUFFER_SIZE` | 262144 | `unit/test-nonappend.out` (`constant_WRITE_BUFFER_SIZE`) |
| File after close, 12 (N, h) x 3 reps | header 42 B + count x (h + 12) in every cell, identical across the three N for each h (20,720,042 · 268,524,306 · 268,503,330 · 268,437,034 B); CRC32 of the bytes after the header equals the expected | `unit/test-nonappend.out` (`case` lines, `_file_bytes_CRC_equal_expected`) |
| Direct pool P1 − P0 (aggregation buffer allocated) | exactly N in all 36 cells (65,536 · 262,144 · 1,048,576), one buffer | same (`_direct_pool_delta_P1-P0_=_N`) |
| Direct pool P2 − P1 (after 20,000 x 1 KiB … 128 x 2 MiB appends and close) | 0 in all 36 cells, including the 300 KiB and 2 MiB hints written through | same (`directP1`, `directP2`) |
| Channel writes | model equal in every cell: 1 KiB: 318 · 80 · 20 writes for N = 64 KiB · 256 KiB · 1 MiB, each ≤ N; 300 KiB: one write per hint at 64 KiB and 256 KiB (874), 292 at 1 MiB; 2 MiB: one per hint (128) at every N; buffer position never above N | same |
| Positive control | `HintsBuffer.create(32 MiB)` moves the direct pool by 33,554,432 B and `create(64 MiB)` by 67,108,864 B (count +1); the allocate guard admits capacity/2 − 12 and refuses +1 at both sizes | same (`control_…`) |

**Cluster tier** (`cluster/summary.txt`, `analysis.txt`, `arms.json`; 82 `EXPECTED` lines, all yes; the flush period 1000 ms confirmed in `A-yaml-tail.txt`)

| Capacity value | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| builds 64 KiB · 256 KiB · 1 MiB, B down | all 12 hint arms | traced buffer capacity | 65536 / 262144 / 1048576 in every arm of that build | `summary.txt` |
| same | 1 KiB x 6 | hint bytes on disk | 1,146,093,946 B in all six (1.0674 x values), 9 files | `analysis.txt` |
| same | 400 KiB x 6 | hint bytes on disk | 1,073,745,406 B in all six (1.0002 x), 8 files | `analysis.txt` |
| same | all | hinted and stored | `Hints_created` = writes = entries appended; appended bytes + 42 B x files = bytes on disk | `summary.txt` |
| same | 400 KiB at 64 KiB and 256 KiB builds | bypass | `over` = `wrdirect` = 2621 = writes; at the 1 MiB build `over` 0, `wrdirect` 0 (the 400 KiB hint fits the buffer, as amended in B3f) | `summary.txt` |
| same | idle baseline, direct pool minus traced slabs | per build | 33.22 MB · 33.42 MB · 34.20 MB; differences −194,459 B and +787,164 B against the constants' −196,608 and +786,432 | `analysis.txt` |
| same | NMT "Other" committed before each arm | per build | 251.33 MB · 251.53 MB · 252.31 MB (−0.20 MB, +0.78 MB) | `arms.json` |
| same | direct pool peak, 1 KiB | per build | 97.1 · 97.4 · 98.1 MiB, 2 slabs; differences from the stock build −0.17…−0.25 and +0.69…+0.76 MiB against −0.19 and +0.75 | `analysis.txt` |
| same | direct pool peak, 400 KiB | per build | 157.0–158.5 · 157.6–157.9 · 159.5–160.2 MiB, 3 slabs each; the same-build rep spread is up to 1.5 MiB; the 1 MiB build is +1.5…+2.7 MiB over the stock one against +0.75 | `analysis.txt` |
| same | pool peak vs payload | all builds | 97 (1 KiB, 2 slabs) → 158 MiB (400 KiB, 3 slabs) at every build | `analysis.txt` |
| same | heap peak, RSS peak | all | heap 1,464–1,859 MiB of 2,048 MiB, RSS 2,993–3,066 MiB, no ordering by build | `analysis.txt` |
| control: B up | 128 MiB of 1 MiB values | hints | none, TotalHints +0 | `summary.txt` |
| control `commitlog_segment_size` 128MiB | 1 KiB, stock build | slab, pool | slabs 134,217,728 B, 2 of them (256 MiB); pool peak 289.4 MiB against 97.4 MiB (+192 MiB); NMT "Other" 352.2 MB against 251.5 MB; disk unchanged (1,146,093,946 B) | `summary.txt`, `arms.json` |
| control `max_hints_size_per_host` 64MiB | 1 KiB, stock build | disk | stops at 71,965,348 B (68.6 MiB; 65,842 of 1,048,576 hints stored) against 1,146,093,946 B; 146 sampled-counter refusals, operands above the limit; 0 growth in the last 40 % of the window; all 1,048,576 writes succeeded | `summary.txt` |

Writers waiting at the 3-buffer cap: 21–26 `waiting` lines in every 400 KiB arm, 0 in the 1 KiB arms (`arms.json`). Coordinator `WriteTimeout`s occurred only in 4 of the six 400 KiB arms (up to 16; the hint for each was still created).

### 4.2 Conclusion and logic

1. **Validity.** Unit: 36 cells ran, 333 checks, no error [observed: `unit/summary.txt`]. Cluster: B down for each hint arm, A restarted per arm with no `.hints` file at the start, `Hints_created` = writes (12 arms), B-up control wrote no hint [observed: `summary.txt`]; the builds' constants confirmed by `javap` and the trace [observed]; 1 GiB per arm is 4,096 cycles of the 256 KiB buffer and 32 slabs; both real controls moved. Valid.
2. **Readings.** (a) At 400 KiB the 1 MiB build's pool peak is up to 1.95 MiB above what the constants' difference gives, within the 1.5 MiB spread of same-build reps plus the quantisation of the sampler; slab counts equal [observed: `analysis.txt`]. (b) The pool total differs between payloads (97 vs 158 MiB) by a slab (2 → 3) and about 29 MiB unattributed, equal at every build [inferred: from the create trace; nothing explains the rest]. (c) The per-host limit stopped at 68.6 MiB, 4.6 MiB over 64 MiB, the check reading on-disk sizes [inferred].
3. **Matched row.** Unit, B2g row 1 "File length identical across buffer sizes; direct delta = buffer capacity only; flat as N and h grow": file length identical across N for every h, direct delta = N exactly, zero growth for 128 hints of 2 MiB and 20,000 of 1 KiB; the control row "slab delta moves by 32 MiB between settings while the aggregation buffer delta is flat" also holds (exactly 33,554,432 and 67,108,864). Cluster, B3g row 1 and the added R4 row: hint disk byte-identical across builds at both payloads; heap equal across builds in shape; the pool total differs by the constants' difference at 1 KiB (≤ 0.07 MiB) and, at 400 KiB, by the constants' difference plus ≤ 1.95 MiB with equal slab counts (within 2 MiB: the R4 row); each build's buffer capacity is its constant (trace) and the idle baseline and NMT differ by exactly the constants' difference; flat in time apart from slab steps; controls move by tens of MiB (+192 MiB pool) or plateau (68.6 MiB against 1,093 MiB).
4. **Excluded rows.** Refuted rows: "grows with the constant by more than its own capacity difference, or grows in time with load": no, slab steps only, 400 KiB builds within 2 MiB of each other, no ordering of the 64 KiB and 256 KiB builds [observed: `analysis.txt`]; "Hint sizes never reach the bypass or no hints are created": 2621 bypasses at 64 KiB and 256 KiB, hints created = writes; "Memory control does not raise the direct pool, or disk control does not plateau": both moved; "Build differences are below sampler noise" (not distinguishable): excluded because the baseline, NMT and the 1 KiB peaks resolve the step exactly and the R4 row applies at 400 KiB. Unit: direct delta is exactly N (no growth with N or h), file lengths equal; nothing lost; control moved.
5. **Observed vs. inferred.** Inferred: the unattributed ~29 MiB between payloads is not caused by the constant (it does not order with it); that the 256 KiB sits inside the pool total (shown by exact baseline/NMT differences).
6. **Deviations and gaps.** 1 GiB per arm as filed; 256 MiB per unit cell (R1); both nodes on one host; the cluster driver had no own shakedown; `jstat` replaced by JMX heap. The 400 KiB pool-peak comparison is limited to ±2 MiB resolution.
7. **Core question.** Usage did not follow the constant: hint disk, hint count, slab count and the pool peaks under load are independent of it to within the sampler's resolution, while the constant itself changes the one fixed buffer by exactly its difference (unit: pool delta = N, baseline and NMT in the cluster). Hints above the buffer bypass it and are stored byte for byte; the real caps (slab size via `commitlog_segment_size`, `max_hints_size_per_host`) moved memory (+192 MiB) and disk (68.6 MiB against 1,093 MiB) under the same instruments. The constant does not cap hint-writing memory or disk usage.

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 (with the R4 row) — confirmed, does not cap.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.py` re-parses the raw logs independently: the unit `case` lines are re-simulated (writes, bytes, zero-length calls, file length, pool deltas) for 36 cells, and for each of 14 arms the key CSV, the hints CSV, the samples CSV, the trace (slabs, capacities, flush counters): 73 ok, 0 FAIL (`selfcheck.txt`).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `summary.txt`; `selfcheck.txt` (written/succeeded, slabs) |
| 2. Readings | yes | `analysis.txt` (400 KiB differences) |
| 3. Matched row | yes | the 400 KiB excess is up to 1.95 MiB, so the R4 row (within 2 MiB), not the strict 768 KiB, is what matches there |
| 4. Excluded rows | yes | `analysis.txt` X1; `summary.txt` controls |
| 5. Observed vs. inferred | yes | |
| 6. Deviations and gaps | yes | |
| 7. Core question | yes | follows the audited logic |

### 5.2 Run 2?

No (2026-10-28): unit readings are exact; cluster disk, trace, baseline and NMT readings repeat identically across reps.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** node memory and disk usage do not follow `WRITE_BUFFER_SIZE`: with the same hint workload, changing the constant changes the aggregation buffer's own capacity by exactly that amount and nothing else that grows with load, and hint bytes on disk are identical in every case, including for hints larger than the buffer. "Confirmed" means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1; control row) | does not cap | run 1 + self-check | 2026-10-28 |
| Cluster | Confirmed (B3g row 1 and the R4 row) | does not cap | run 1 + self-check | 2026-10-28 |

**Positive control:** `commitlog_segment_size` 128MiB (slab 128 MiB, pool +192 MiB), `max_hints_size_per_host` 64MiB (disk 68.6 MiB against 1,093 MiB); unit `HintsBuffer.create` 32 vs 64 MiB (exact +33,554,432 / +67,108,864 B).

**Feedback filed:** section D of the case file filled (2026-10-28); the case file was amended before run 1 (audit block R1–R5, sha256 `fe0f472f…`), no later amendment.
