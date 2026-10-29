# filename_length-validatesnapshotname-snapshotname--autonomous — stage-4 results  <!-- file: results/filename_length-validatesnapshotname-snapshotname--autonomous.md -->

> **Case:** [`filename_length-validatesnapshotname-snapshotname--autonomous`](../../stage3-ai-deep-read/cases/filename_length-validatesnapshotname-snapshotname--autonomous.md)
>
> **Status:** **Closed 2026-10-28 — unit Confirmed, cluster Confirmed (disk; one heap tolerance deviation, see §4.2) — does not cap** (estimate negative, matched); no run 2
>
> **Outcome class:** true negative — stage-3 estimate vs the stage-4 effect on the constraint
>
> **Agent:** autonomous. "§9a" = B2f/B2g (unit), B3f/B3g (cluster); "§9b–§9e" = B2a–B2e / B3a–B3e; feedback section is D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments: `752b8b601cc031d70d416f6cf9983482a01469f653f81e003f4d8c8ac331472f` (`sha256sum`, 2026-10-28 14:09 EDT, before any harness check or run, after the block "Audit amendments (stage 4 step 0, 2026-10-28)" R1-R5). Not committed by this session. |
| **Harness** | `harness/filename_length-validatesnapshotname-snapshotname--autonomous/`, written 2026-10-28; not committed by this session. |
| **Tiers and values** | Unit (B2): L in {1,100,255,256,300} x validation {false,true} x N in {1k,100k} x 3 reps. Cluster (B3): one node, L in {1,100,255,256}, validation true; N = 200k and 2M rows; then validation false with L = 256. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2: the operand is a name length (characters), not bytes; the design asks whether snapshot disk/heap follows it. Acceptable for a negative estimate. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | Constant not settable (A1); the operand L is varied (1, 100, 255, 256, 300) and validation on/off; reason stated. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d/B3d disk (file bytes, whole-dir `du`, listsnapshots) and heap/RSS; B3d names the snapshot record as not observable (R5). |
| A. Core question | usage driven to the limit and past it | Met | L = 255 (limit) and 256, 300 (past); data N 1k to 2M rows. |
| B. Logic | each step says what it establishes | Met | B2e, B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after R1, R2 | "may fail in OS" and "within noise" had no criterion; added. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g (plus R1 for L>255 with validation false). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | accept/reject flip at 255/256 is the direct evidence; flat size vs L, rising with N. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h. |
| C. Specific | a human can follow it from the intro and §9a | Met | A1-A3, B1. |
| C. Specific | an AI can run B2e–B3e without re-deriving the code path | Met | |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after R2, R3, R4 | tolerances and repetition rule; `du --apparent-size` double counts links. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | pc41: JDK 11.0.32.1, Ant 1.10.12, 53 GB free local disk; test class and drivers are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit | Met | 2M x ~200 B is a few hundred MB against a name term of < 300 B. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Re-read: see amendment block; all hold. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | validation false, L>255: OS rejection predicted (ext3 NAME_MAX 255 checked) | Applied 2026-10-28 (B section amendment block) | prediction was vague |
| R2 | numeric tolerances for "flat" and "rises" | Applied 2026-10-28 | readings needed criteria |
| R3 | repetition rule | Applied 2026-10-28 | |
| R4 | `du --apparent-size` double counts hard links | Applied 2026-10-28 | |
| R5 | snapshot record memory is only coarsely bounded | Applied 2026-10-28 | |

**Agreement criteria** — run 2 not planned.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-28 (node clock MDT): unit 12:13-12:14; cluster 12:14-12:22; supplementary heap-noise probe 12:23-12:27; a unit shakedown at 12:10 (discarded) |
| Node | `pc41` = `node4.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB) |
| OS and kernel | Ubuntu 22.04, `5.15.0-198-generic` (node `uname -r` not re-run; as pc29) |
| JDK / Ant | openjdk 11.0.32.1 (2026-08-18) / Ant 1.10.12 |
| Local source copy | `~/s4-b2/base` by `copy-source.sh` from `cassandra/cassandra-5.0.9/` at repository commit `b68711e5` (local tag `cassandra-5.0.9`), `ant build-test` (1 min 8 s) |
| Case-file / harness commit | case file sha256 `752b8b60...` at freeze; nothing committed by this session |
| Storage for node data | `~/s4-b2/node/` on local ext3 `/dev/sda3` (52 GB free at start); ext3 NAME_MAX 255 confirmed by `mkdir` |
| Full logs | `pc41:~/s4-b2/logs/filename_length-validatesnapshotname-snapshotname--autonomous/run1/` (`unit/`, `cluster/log.txt` full command log) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| D1 | cluster | B3d (harness) | `cluster-run.py` picked the `listsnapshots` row for the first table whose name matched; at L >= 255 the first row is `counter1` (1015 B, an empty table), so the tail column of the `SNAP` lines for L=255 shows `1015 bytes`, not the `standard1` row. | Instrument only: the full `listsnapshots` output is saved (`listsnapshots-N200k-L*.out`) and the `standard1` row read from there (1.01 KiB / 48.44 MiB at L=1, 100, 255). | 2026-10-28 | none |
| D2 | cluster | B3e step 5 | After the restart (validation false) startup compaction ran before `disableautocompaction`, so the on-disk set changed (66 to 10 sstables, `physDelta` -476,798,887 B and heap -503 MB in that arm). Those two deltas are not readings of the name; only accept/reject and the L=255 success are used from that arm. | none (design is B3e as written; noted) | 2026-10-28 | none |
| D3 | cluster | B2/B3 R2 | The frozen heap tolerance (1 MiB) is below G1 heap granularity on the node (see 4.2). | recorded, not edited | 2026-10-28 | none |

No other step of B2/B3 failed to run as written.

## 4. Run 1

**Scope:** unit B2 (2 N x 2 validation x 5 L x 3 reps = 60 cells) and cluster B3 (N = 200k: L = 1, 100, 255, 256 plus a warm-up; N = 2M: L = 100, 255; validation false: L = 256, 255), plus a supplementary heap-noise probe on the same data. **Command log:** `run1/` (`unit/summary.txt`, `unit/test.out`, `cluster/summary.txt`, `cluster/rows.csv`, `cluster/noise-summary.txt`, `cluster/listsnapshots-*.out`, `selfcheck.py` output `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (1/1 test passed; 90 checks, 90 ok, 0 mismatch; `unit/summary.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| validation true, L = 1, 100, 255 | accepted in all 3 reps x 2 N | `unit/test.out` (`case` lines) |
| validation true, L = 256, 300 | `IllegalArgumentException` with the line-2187 text, no snapshot directory | same |
| validation false, L = 1, 100, 255 | accepted | same |
| validation false, L = 256, 300 | not the line-2187 text: `FSWriteError` (IOException "Unable to create directory"), no directory | same |
| Snapshot file bytes, `manifest.json`, `schema.cql` over L = 1, 100, 255 | identical in all 9 reps: 31,688 B (N = 1k; manifest 129, schema 976), 2,571,365 B (N = 100k) | same |
| Physical bytes added to the table directory (inodes counted once) | 1,105 B for every accepted cell (L = 1 ... 255, both N), 0 for rejected ones | same |
| Heap delta (`System.gc()` before/after), mean of 3, L = 255 minus L = 1 | 19,592 · 94,773 · 83,403 · 776,075 B (all under 1 MiB; rep range up to 2.3 MB) | `selfcheck.txt` |
| Positive control: N | snapshot bytes 81.1x larger at 100k rows than at 1k, with and without validation | same |

**Cluster tier** (`cluster/summary.txt`, `rows.csv`; 33 `EXPECTED` lines, 32 yes, 1 NO)

| Capacity value | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| N = 200k, validation true | L = 1, 100, 255 | `nodetool snapshot` | rc 0 each | `summary.txt` |
| same | L = 256 | `nodetool snapshot` | rc 1, "Snapshot name must not be more than 255 characters long", no directory | `summary.txt`, `log.txt` |
| same | L = 1, 100, 255 | snapshot bytes / manifest / schema | 50,797,538 B, 10 files, 129 B, 903 B in all three | `summary.txt` |
| same | L = 1, 100, 255 | `listsnapshots` standard1 row | True size 1.01 KiB, size on disk 48.44 MiB in all three | `listsnapshots-N200k-L*.out` |
| same | L = 1, 100, 255 | physical growth of the data dir | +2,047 B each | `rows.csv` |
| same | L = 1, 100, 255 | heap / RSS delta after 30 s | -52,224 / -1,024 / +19,456 B; RSS -135,168 / -118,784 / +200,704 B | `rows.csv` |
| N = 2M, validation true | L = 100, 255 | snapshot bytes, files | 507,111,470 B, 66 files, both; physical +2,187 B both | `summary.txt` |
| same | L = 100 / 255 | heap delta | 0 / 1,489,920 B (**exceeds the 1 MiB criterion: NO**); RSS -122,880 / +618,496 B | `summary.txt` |
| supplementary probe (same data after restart, 6 snapshots alternating L = 100, 255) | heap delta | +16,738,304 · -16,777,216 · +16,778,240 · +16,778,240 · -16,775,168 · +1,024 B (multiples of the 16 MiB G1 region; no ordering by L); physical +2,047 B in all six | `noise-summary.txt` |
| positive control | N = 2M vs 200k | snapshot bytes | 10.0x (507,111,470 vs 50,797,538) | `summary.txt` |
| validation false | L = 256 | `nodetool snapshot` | rc 2, "Unable to create directory ... snapshots/aaaa..." (OS), not the line-2187 text, no directory | `summary.txt` |
| validation false | L = 255 | `nodetool snapshot` | rc 0 | `summary.txt` |

### 4.2 Conclusion and logic

1. **Validity** - Unit: ran, 90/90 checks [observed: `unit/summary.txt`]. Cluster: JVM flags `-Dcassandra.snapshot.validation=true -Xmx2G` confirmed from `/proc/<pid>/cmdline`; stress `Total errors 0` for both loads; autocompaction disabled and flush before snapshots (66 files at 2M); each snapshot cleared; no daemon left [observed: `summary.txt`, `log.txt`]. Valid.
2. **Readings** - (a) heap deltas are quantised in 16 MiB steps at the cluster tier and the single N = 2M pair differs by 1.49 MiB; the six-snapshot probe shows swings of +-16 MiB with the same sign mix at L = 100 and 255 [observed: `noise-summary.txt`]. (b) The validation-false arm's `physDelta`/heap are confounded by startup compaction (D2). (c) `listsnapshots` tail column in the `SNAP` lines is the `counter1` row at L >= 255 (D1).
3. **Matched row** - Unit B2g row 1 (accept/reject flips exactly at 255/256 with validation true, no flip with false - the OS rejects instead; snapshot bytes flat over L, rising with N): all parts read as above. R1 row for validation false holds (FSWriteError). Cluster B3g row 1: reject at 256 only; snapshot bytes, manifest/schema, True size, size on disk and physical growth identical across L; grow 10x with N [observed].
4. **Excluded rows** - "size or heap grow with L": snapshot bytes and physical growth are equal to the byte over L = 1 ... 255; heap deltas do not order with L (probe) [observed]. "L = 256 accepted with validation true": rejected, no directory. "Rejected with validation false at line 2185 text": no, OS error text. "Control did not move": it moved 81x (unit) and 10x (cluster).
5. **Observed vs. inferred** - Inferred: that the 1.49 MiB heap difference is G1 granularity/noise rather than a name effect [inferred: the probe's swings of 16 MiB with no ordering by L, and identical physical growth]; that the in-memory `TableSnapshot` record is small [inferred: heap deltas under 1 MiB at the unit tier; not directly observable, R5].
6. **Deviations and gaps** - The frozen heap tolerance (R2, 1 MiB) is not met by one cluster pair (1.49 MiB) and cannot be met on this node's heap measurement (granularity 16 MiB); heap therefore cannot resolve name-length effects below about 16 MiB at the cluster tier; the unit tier (GC-forced, deltas under 1 MiB) bounds them to under 1 MiB. L = 1 and 100 were not run at N = 2M (as designed: 100, 255 only). Single node, single repeat per cluster cell (unit has 3). The constant itself was not varied (not settable); the operand L was.
7. **Core question** - Snapshot disk usage (bytes, True size, physical growth) was identical for names of 1, 100 and 255 characters and tracked the data volume instead (10x to 81x), and heap/RSS showed no dependence on L beyond noise. The 255-limit decides only whether the name is accepted (reject at 256 with validation true; the OS rejects 256 with it off). The constant does not cap memory or disk usage.

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 - confirmed (negative estimate), with the cluster heap tolerance of R2 recorded as not met by noise.

## 5. Self-check of run 1 - AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.py` (output `selfcheck.txt`) re-parses `unit/test.out` and the cluster `summary.txt`/`log.txt`/`listsnapshots-*.out`/`stress-*.out` independently of the test and `cluster-run.py`: all unit cells re-derived (accept/reject, flatness, physical range, heap means, control), the cluster rc and byte equalities, the OS vs line-2187 messages: 0 FAIL ("RESULT ALL OK").

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `log.txt` (flags, stress errors 0) |
| 2. Readings | yes | `noise-summary.txt` |
| 3. Matched row | yes | `selfcheck.txt` |
| 4. Excluded rows | yes | `selfcheck.txt` |
| 5. Observed vs. inferred | yes | heap noise attribution is inferred, flagged |
| 6. Deviations and gaps | yes | |
| 7. Core question | yes | follows the audited logic |

### 5.2 Run 2?

No (2026-10-28): disk readings are exact and repeat identically across L, reps and tiers; the one open reading (heap) is noise-limited and a repeat would not change that.

## 6. Run 2 - Not done.

## 8. Verdict - AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** snapshot disk and heap use do not depend on snapshot-name length (1, 100, 255 characters) but on the amount of SSTable data; the limit changes only whether a name is accepted. "Confirmed" means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1; R1 row for validation false) | does not cap | run 1 + self-check | 2026-10-28 |
| Cluster | Confirmed (B3g row 1) - disk exact; heap tolerance of R2 not met at N = 2M (1.49 MiB), shown to be 16 MiB-granular noise | does not cap | run 1 + self-check | 2026-10-28 |

**Positive control:** data volume N: snapshot bytes 81.1x (100k vs 1k rows, unit), 10.0x (2M vs 200k, cluster), under the same instruments that read identical values across L.

**Feedback filed:** section D of the case file filled (2026-10-28); amended before run 1 (audit block R1-R5, sha256 `752b8b60...`), no later amendment to B.
