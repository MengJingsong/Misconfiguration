# sasi-max_compaction_flush_memory-PerSSTableIndexWriter-estimatedMemoryUse--autonomous — stage-4 results  <!-- file: results/sasi-max_compaction_flush_memory-PerSSTableIndexWriter-estimatedMemoryUse--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`sasi-max_compaction_flush_memory-PerSSTableIndexWriter-estimatedMemoryUse--autonomous`](../../stage3-ai-deep-read/cases/sasi-max_compaction_flush_memory-PerSSTableIndexWriter-estimatedMemoryUse--autonomous.md)
>
> **Status:** self-checked; verdict filed (2026-10-26)
>
> **Outcome class:** true positive — the stage-3 estimate (positive) against the effect found below (caps, with a recorded overshoot) ([definition](../README.md#outcome-class))
>
> **Agent:** guided / autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Case file untracked at audit time (orchestrator commits). Original sha256 `75e5b20ea02d769ebe2b003ae7cfb8b04252edb568de95feb091ac91253e8bef`; sha256 after the audit's amendments (B5.1-B5.7, inline notes in B2c and B3f/B3g): `ac21dffb110a0f8f163d1f053d6c04a45b0c170f7b2d02fdde441ef2cfa7b8c4`. Frozen tables, written before any reading: B2f-g (from `**B2f.` to before `**B2h.`) sha256 `9bccd37a00736421b95fd3264afcf1be17d422b44fb05b3166e20b6cd4bc9bb6`; B3f-g (from `**B3f.` to before `**B3h.`) sha256 `71b9b2005c30d9124bf829316a9eb912c8b7119c503b3a625fe395358555d27b`. Final sha256 after the section D feedback (2026-10-26): `701973346bddb8fa78149b2167ff94337d1bb24e49655b985602fe2554d3ba2c`. |
| **Harness** | `harness/sasi-max_compaction_flush_memory-PerSSTableIndexWriter-estimatedMemoryUse--autonomous/` (uncommitted; orchestrator commits). Instrument checks (not readings): unit test at N=20,000 (analyzer 0 fails at STAGE4_N=20000), cluster shakedowns of 300,000 rows (arms 1024, 8) and 3,000,000 rows (arm 1024), the latter used to size the heap. |
| **Tiers and values** | Unit: COMPACTION cap 1/4/16 MiB and default, FLUSH with 1 MiB option and default, N=100,000 unique Int32. Cluster: 3,000,000 rows, one sstable, caps 1024, 8, 32, 128, default, 1024 MiB (SPARSE) in series on one node, heap 3 GiB. |
| **Audit bottom line** | **Ready after amendments** - 2026-10-26 (work interrupted by an API rate limit between 2026-10-26 02:47Z and 04:24Z; no frozen reading existed) |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: heap bytes of the active builder (estimate in bytes, `OnDiskIndexBuilder.java:182,194`); real heap measured separately. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b 1/4/16/default and FLUSH; B3b 8/32/128/default/1024 MiB. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B3d: histogram live bytes + JMX heap; unit B2d heap delta only for the active builder. Gap: estimate is a hand-coded approximation (shakedown: about 1.7x), named in the Estimate line. |
| A. Core question | usage driven to the limit and past it | Met | B2c: 100,000 adds pass 1/4/16 MiB; B3c: 3M rows pass 8/32/128 MiB and default (153.6 MiB); the 1024 arm is the no-cap control. |
| B. Logic | each step says what it establishes | Met | B2e/B3e with B2g/B3g. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f exact counts; B3f counts (amended to cuts + 1) and ordering. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | B3g lacked an OOM row at 1024 MiB: added (B5.5). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Segment cuts (the disallow action) in logs and counts plus live bytes ordered by cap. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: 1024 MiB control first and last, FLUSH vs COMPACTION, default cross-check. |
| C. Specific | a human can follow it from the intro and §9a | Met | A3 and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | Test construction and sampling left to the harness (B5.2). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Histogram interval, one-sstable step, heap were open: fixed in B5.3-B5.5. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Listed as step-1 work; written. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly | Arithmetic correct except one product (B5.1) and log counts (cuts + 1); heap 2 GiB too tight (B5.5). Disk 36 GB free; index about 0.32 GB. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | All A1-A5 cites re-read; no wrong line cite. Queue bound resolved (B5.4). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Fix 22*4682 = 103,004 | Applied 2026-10-26 (B5.1) | arithmetic |
| 2 | Log counts are cuts + 1 per sstable; one sstable by major compaction | Applied (B5.3) | `PerSSTableIndexWriter.java:300-304,:276` |
| 3 | Direct writer construction; six unit arms | Applied (B5.2) | reachable without SchemaLoader |
| 4 | Heap 3 GiB; OOM row | Applied (B5.5) | shakedown: 2 GiB left 0.2 GiB margin |
| 5 | Queue unbounded; observe pending count and builder instances | Applied (B5.4) | `ThreadPoolExecutorBuilder.java:160-168` |
| 6 | Stale 1G comment and log text (`IndexMode.java:60,:192`) | left for stage 3 | does not affect the claim |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-10-26 (unit 04:2xZ, cluster 04:25 to 04:42Z); interrupted by an API rate limit 02:47Z to 04:24Z between shakedowns and the freeze, no frozen reading existed | not done |
| Node | `pc07` (`node0.jason92-320876...`), 40 cores, 251 GiB, shared with other agents | |
| OS / kernel | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK / Ant | OpenJDK 11.0.32.1 / Ant 1.10.12 | |
| Local source copy | `~/s4-pm` by `copy-source.sh` at repository commit `1ae567d`; `ant build-test` 1 min 16 s; unit tier `ant testsome` first, the node ran from it afterwards with no further `ant`; shakedown nodes ran from a spare copy `~/s4-pm-sh` (deleted) | |
| Case-file / harness commit | untracked at run time (sha256 in section 1); harness uncommitted | |
| Storage | local `/dev/sda3` (35 GB free), `~/s4-pm-data/cl` (removed after the run) | |
| Full logs | `pc07:~/stage4-logs/pm/` (`run1-unit/`, `run1-cl/`, `shake1`, `shake2`, `unit-shake` are shakedowns, not readings) | |

Ports: JMX 7332, native 9354, storage 7032, loopback 127.0.32.1 (checked free before start); Byteman 9332 not used.

## 3. Runbook defects

None stopped a run. Fixed before the freeze as amendments B5.1-B5.7 (arithmetic product, log count cuts + 1, one sstable, heap 3 GiB, OOM row, unit construction). Harness defect found in shakedown 1: the histogram interval (6 s) missed a 5 s build; changed to back-to-back (about 1 s). SASI thread-pool MBeans appear only after the first index build (earlier -1 values in the sampler are before that).

## 4. Run 1

**Scope:** unit tier, 6 arms x 100,000 adds; cluster tier, 3,000,000 rows, one sstable, six index builds in series (1024, 8, 32, 128, default, 1024 MiB), heap 3 GiB. **Command log:** `sasi-max_compaction_flush_memory-PerSSTableIndexWriter-estimatedMemoryUse--autonomous/run1/` (`unit/session.log`, `cluster/session.log`, `cluster/summary.json`).

### 4.1 Readings

**Unit tier** (`run1/unit/unit-results.csv`, `unit-cuts.csv`; `unit/analysis.txt` all PASS)

| Test or assertion | Result | Evidence |
|---|---|---|
| COMPACTION 1 / 4 / 16 MiB / default: segments cut before `complete()` | 21 / 5 / 1 / 0; estimate at every cut 1,048,768 / 4,194,400 / 16,777,376 (exact n*224) | `unit-results.csv`, `unit-cuts.csv` |
| max estimate | limit + at most 224 for the three caps; 22,400,000 (default and FLUSH arms) | same |
| FLUSH with 1 MiB option, FLUSH default | 0 segments, max estimate 22,400,000: option ignored | same |
| `Flushed index segment` logs | 22 / 6 / 2 / 0 / 0 / 0 (cuts + 1 tail) | same |
| segment files on disk before complete = segments; none after; final index 100,000 terms, 9,947,276 B in every arm | as stated | same |
| heap delta of the active builder / estimate (indicative) | 2.81 (small builder), 1.76, 1.77, 1.79, 1.79, 1.79: real heap about 1.8x the estimate (about 400 B per entry vs 224) | same |

**Cluster tier** (3,000,000 rows, one sstable of 53,978,071 B; index file 322,805,532 B in every arm; no OOM, no failure line)

| Cap (MiB) | Arm | `Flushed index segment` (exp.) | Peak live excess, histogram (MB) | max builder instances | max SASI-General pending | max old gen after GC (MB) | build time |
|---|---|---|---|---|---|---|---|
| 1024 | a1 | 0 (0) | 1491 | 2 | 0 | 1605 | 56.8 s |
| 8 | a2 | 81 (81) | 77 | 5 | 0 | 167 | 32.6 s |
| 32 | a3 | 21 (21) | 305 | 5 | 0 | 393 | 32.6 s |
| 128 | a4 | 6 (6) | 1012 | 4 | 0 | 1100 | 38.6 s |
| default 153.6 | a5 | 5 (5) | 1171 | 5 | 0 | 1259 | 40.6 s |
| 1024 | a6 | 0 (0) | 1501 | 2 | 0 | 1607 | 58.6 s |

Evidence: `cluster/summary.json`, `histo-a*.jsonl`, `pool-every4th.csv` (every 4th row of the 250 ms sampler), `segments-a*.txt`.

### 4.2 Conclusion and logic

1. **Validity** - valid. The limit was reached: every capped arm cut segments (81/21/6/5 lines) and the 1024 arm built the whole index in memory [observed: `cluster/segments-*.txt`]. Hold-fixed: heap 3 GiB, one sstable, same data, SPARSE [observed: `node-cmdline.txt`, `summary.json`]. Unit: estimates equal n*224 [observed: `unit-cuts.csv`].
2. **Readings** - the peak live excess is 4 to 5 times the active builder's real size at each cap (8 MiB cap: estimate 8.4 MB, real about 15 MB, peak 77 MB; 128 MiB cap: real about 240 MB, peak 1012 MB) [observed: histograms]. Pending queue was never above 0 [observed: `pool-every4th.csv`, `analysis.txt`]; the extra live builders are in-flight ones (up to 5 `OnDiskIndexBuilder` instances alive, 8 writer threads) [observed]. Heap-used peaks include garbage and are not read as evidence (2023 MB at 128 and 1836 MB at 1024).
3. **Matched row** - B2g row 1 (counts and cut estimates match) and B3g row 1 (counts 81/21/6/0 with 5 at default; peak live bytes ordered 77 < 305 < 1012 < 1171 < 1491/1501; ratio 1024 to 8 is 19.4, above 5), with the B3g row "queued/in-flight segments exceed the cap" noted as the overshoot factor (about 4 to 5) rather than the leading row: it did not make the peak independent of the cap.
4. **Excluded rows** - counts unchanged with N: no (81 vs 0). Peak heap flat across N: no (post-GC old gen 167 to 1607 MB, ordered). 1024 equals 8: no (19.4x). FLUSH with the 1 MiB option cutting 21: no (0). Estimate far above limit + one value: no (max exactly limit + at most 224). Limit never reached: no. OOM: none.
5. **Observed vs. inferred** - inferred: that "in-flight builders" explain the 4 to 5 overshoot (instance counts and zero pending are observed; the lifetime of each is not); that the unit FLUSH arm stands for the flush path (direct constructor with `OperationType.FLUSH`, not a real memtable flush; the 1 GiB flush cap was not reached on a node).
6. **Deviations and gaps** - unit writer built directly (B5.2); heap 3 GiB (B5.5); arm order has the default arm in the middle; cluster flush path not exercised; the peak is taken from forced-GC histograms, so garbage and the final-merge transient are not counted except through the sampler. Queue unboundedness was shown by source and 0 observed pending, not by stress.
7. **Core question** - Yes: usage follows the constraint. The unit estimate stops at the limit (+ one add) and segment count falls as the cap rises; on a node the number of segments and the live heap during the build both scale with the cap (77, 305, 1012, 1171, about 1500 MB), while the stale 1G text in `IndexMode.java` is only a message. The cap binds the estimate exactly and live heap proportionally with a looseness: real heap about 1.8x the estimate and 4 to 5 builders alive at once.

**Conclusion (one line):** B2g row 1 / B3g row 1 - confirmed (claim: caps, with a recorded looseness).

## 5. Self-check of run 1 - AI

### 5.1 Check of run 1's conclusion

`harness/sasi-max_compaction_flush_memory-PerSSTableIndexWriter-estimatedMemoryUse--autonomous/selfcheck.py` re-parses `unit-results.csv`, `unit-cuts.csv`, `segments-*.txt`, `errors-*.txt`, `histo-*.jsonl`, `pool.csv` and `summary.json` independently of the analyzers (`run1/selfcheck.txt`: all HOLD, BAD 0).

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | `node-cmdline.txt` (`-Xmx3G`, JMX 7332); one sstable; segment lines re-counted per arm from the log excerpts. |
| 2. Readings | yes | peaks recomputed from histograms (77/305/1012/1171/1491/1501 MB); sampler old-gen after GC 167/393/1100/1259/1605/1607 MB. |
| 3. Matched row | yes | cut counts and estimates recomputed from the cut list for 5 unit arms. |
| 4. Excluded rows | yes | index file size equal in all arms (322,805,532), index dropped between arms. |
| 5. Observed vs. inferred | yes, with a gap | in-flight explanation inferred. |
| 6. Deviations and gaps | yes | listed. |
| 7. Core question | yes | |

### 5.2 Run 2?

**No** (2026-10-26). Both tiers agree, the decisive readings are exact counts and ordered sizes from independent raw files; the inferred in-flight explanation does not change the verdict.

## 6. Run 2

Not done (5.2).

## 7. Comparison

Not done.

## 8. Verdict - AI

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps).

**Claim tested:** the writer cuts a new segment whenever the active builder's estimate reaches the limit, so segment count and live builder heap follow `max_compaction_flush_memory_in_mb` (B1). "Confirmed" means this held.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1) | caps (estimate); FLUSH ignores the option | run 1 + self-check | 2026-10-26 |
| Cluster | Confirmed (B3g row 1), with the overshoot noted | caps (about 4 to 5 builders in flight; real heap about 1.8x the estimate) | run 1 + self-check | 2026-10-26 |

**Positive control:** n/a for a positive file; the 1024 MiB arm (run first and last, 1491 and 1501 MB) is the no-effective-cap control.

**Flags checked:** (1) 224 estimated B per entry holds exactly; real about 400 B per entry (1.8x). (2) Queue unbounded by source (`Integer.MAX_VALUE`); pending never above 0 on this disk, but up to 5 builders alive. (3) Stale 1G comment/log at `IndexMode.java:60,:192` confirmed; real default 161,061,273 B.

**Leftovers:** none running (no node, sampler or Byteman; ports 7332/9354/7032 free). Removed `~/s4-pm-data/*` and the spare tree `~/s4-pm-sh`. Kept: `~/s4-pm` (CapProbeTest untracked, built), `~/stage4-logs/pm/`.

**Feedback filed:** case file section D updated, amendments in B5 (sha256 in section 1 and below).
