# name_length-validatecustomindexcolumnname-name--autonomous — stage-4 results  <!-- file: results/name_length-validatecustomindexcolumnname-name--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`name_length-validatecustomindexcolumnname-name--autonomous`](../../stage3-ai-deep-read/cases/name_length-validatecustomindexcolumnname-name--autonomous.md)
>
> **Status:** verdict filed (2026-10-28) - run 1 done at both tiers, self-checked, no run 2
>
> **Outcome class:** **true negative** (estimate `negative`, effect `does not cap`) — [definition](../README.md#outcome-class)
>
> **Agent:** autonomous. For an autonomous
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
| **Case-file version** | Base repository commit `b68711e5`; the case file is modified/untracked in the working tree (no commit holds the audited version). **sha256 of the whole file after the audit amendments (B2i, B3i, 2026-10-28): `d0354079b6936ca5442172f2fd32fc5fe6eb19e4b4ed01c41bd008358ad7c6b0`**. First frozen 2026-10-28 as `40b4934e624b3f47594694e3761592d283fa04d2458f533eb94bdaba4b52ee8f` before the harness existed and before any reading (the unit tier ran against that version; the unit text is unchanged). **Re-frozen 2026-10-28 12:45 MDT** after one amendment to B3i.3 (row count 2,000,000 reduced to 500,000 by that item's own rule, because the first 2,000,000-row arm ran at about 2,700 rows/s; that arm was aborted after 2 minutes and discarded, its logs kept on the node as `~/s4-b2-logs/run1-b/cluster-aborted-2M`); no cluster reading of run 1 existed at the re-freeze. **sha256 of the frozen B2-B3 text** (copied to `harness/name_length-validatecustomindexcolumnname-name--autonomous/frozen-prediction.txt`): `4fe48673c51549bc4476b7400fe48f931992401a0795a0f010b36d8345090742`. B2f, B2g, B3f, B3g are unchanged by the audit; B2i and B3i only give numbers and exact procedures. Section D is filled after the runs; the file's sha256 with D filled is in section 8. |
| **Harness** | `harness/name_length-validatecustomindexcolumnname-name--autonomous/` (written after the freeze; not committed; md5s at each run start in `name_length-validatecustomindexcolumnname-name--autonomous/run1/harness.md5.*`) |
| **Tiers and values** | Unit (B2): L in {1, 47, 48, 49, 64, 200}, custom (SASI) and plain index, 10,000 rows x 100 B, 3 repeats; row-count control 1,000 / 10,000 / 100,000 at L = 10; unindexed baseline. Cluster (B3): L in {40, 48, 49, 100}, custom and plain, 2,000,000 rows x 100 B, `memtable_heap_space` 256 MiB, plus the pool control at 128 and 512 MiB (plain L = 48). |
| **Audit bottom line** | **Ready after amendments** (B2i, B3i) - 2026-10-28 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

Estimate: **negative**. Audited against `cassandra/cassandra-5.0.9/` (clean, `base.version` 5.0.9). Citations re-read: `CreateIndexStatement.java:63-64, 118-123, 168-180, 195-230`, `SchemaConstants.java:42, 69-91, 105-110`, `KeyspaceMetadata.java:62-72`, `TableMetadata.java:512-520`, `IndexMetadata.java:118-128`, `Config.java:186-189, 605-606`, `DatabaseDescriptor.java:585-592, 4243`, `AbstractAllocatorMemtable.java:55-84`, `SkipListMemtable.java:363`, `conf/cassandra.yaml:797-825, 1990-1992`. All line numbers hold; two corrections: SASI creation is gated by `sasi_indexes_enabled` (default false), and the SASI warning is at `CreateIndexStatement.java:201-205`.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Not met (by design) | A2 states plainly that the constant caps a character count of an identifier, not memory or disk; the question asked is whether memory or disk follows it. Rated as designed for a negative estimate: the claim is about absence. |
| A. Core question | knob varied, >= 3 values incl. default - or another approach, with the reason | Met | A1: not settable; B2b/B3b vary L across the boundary (6 and 4 values); the optional rebuild with the constant at 96 is declared not run (B2i.2). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d/B3d: memtable pool bytes, flushed bytes, heap, off-heap (accessors checked, B2i.4). |
| A. Core question | usage driven to the limit and past it | Partly -> Met | L = 49, 64, 200, 100 go past the limit (rejected for custom, accepted for plain); resource usage is driven to a pool cap by the 2,000,000-row load (B3i). |
| A. Core question | positive control for a negative estimate | Met | row-count control (unit) and pool control (cluster), made exact in B2i.6, B3i.5; `DatabaseDescriptor.java:585-592` and `AbstractAllocatorMemtable.java:81` confirm the pool wiring. |
| B. Logic | each step says what it establishes | Met | B2e, B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly -> Met | "small", "same within a margin" given bounds (B2i.5, B3i.5). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | rows exist; no row for "custom L=48 rejected" other than the boundary row; the generic rule covers a mixed result. Left for stage 3. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | row 1 needs the exact rejection text at 49 and acceptance at 48. |
| B. Logic | alternative explanations and their controls | Met | plain-index bypass, unindexed baseline, row-count control, pool control. |
| C. Specific | a human can follow it from the intro and B1 | Met | A1-A3, B1. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly -> Met | SASI gate unknown (the file said "not verified"); launcher; names; B2i.1-4, B3i.1-3. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly -> Met | B2i.5-7, B3i.2-5. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | build copy, bundled Python driver, `nodetool`, `jcmd`; test class and node script are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly -> Met | 2,000,000 x 100 B = 200 MB raw is above a 128 MiB heap pool after overhead; the time per arm depends on the driver and is checked by the shakedown (B3i.3). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met (2 notes) | all hold; SASI gate and warning line recorded as B2i.1. |
| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | SASI needs `sasi_indexes_enabled: true` (B2i.1) | Applied, 2026-10-28 | without it the check at line 213 is never reached |
| 2 | Launcher, yaml and local paths (B2i.2, B3i.1) | Applied | `/users/.../cassandra-5.0.9`, `-Dtest.jvm.args` unverified |
| 3 | Explicit index names, identical data across L, 3 repeats (B2i.3-4) | Applied | the generated index name grows with L; noise |
| 4 | Numbers for "small", "same within a margin" and the control (B2i.5-6, B3i.5) | Applied | prediction needs bounds |
| 5 | Control is the pool knob at three values in one allocation type (B3i.1-2) | Applied | B3h's two values cannot show dose-response; `heap_buffers` makes `memtable_heap_space` the binding pool |
| 6 | Optional rebuild with the constant at 96 | Not run, declared (B2i.2) | optional in B2b |
| 7 | Add a conclusions row for mixed results | Left for stage 3 | the no-matching-row rule covers it |
**Agreement criteria** - not applicable (run 2 not planned).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-28 (unit 12:37 to 12:39 MDT; cluster 12:43 to 13:18 MDT, after the aborted 2,000,000-row start at 12:40) | not done |
| Node (CloudLab name and type) | `pc32` (`node2.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB); other stage-4 agents ran on other nodes; the case-1 run of this session ran on the same node earlier, never at the same time | not done |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-198-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12; `ant build-test` once (1 min 7 s) | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-b2/c` by `copy-source.sh`, repository commit `b68711e5` (tag `cassandra-5.0.9`, local baseline); one tree for both tiers and both cases, one run at a time | |
| Case-file commit / harness commit | the case file is not committed (sha256 in section 1); harness uncommitted | |
| Storage for node data | unit: local disk `~/s4-b2-store/run1-b-*` (removed after each JVM); cluster: tmpfs `/dev/shm/s4-b2/node` (removed at the end), so disk bytes are tmpfs bytes | |
| Full logs (path, outside the repo) | on `pc32`: `~/s4-b2-logs/run1-b/{unit,cluster}/` (`summary.txt`, `*.out`, `*.junit.log`, `session.log`, `system.log.life{A,B,C}`, `samples-*.csv`, `arms.jsonl`); the aborted 2,000,000-row start: `~/s4-b2-logs/run1-b/cluster-aborted-2M/`; shakedowns `~/s4-b2-logs/shake1/` (unit full run, cluster quick with 20,000 rows). Unit: JUnitCore, `-Xmx4g`, test yaml with `sasi_indexes_enabled: true`, `memtable_heap_space: 2048MiB`. Node: JDK 11, `MAX_HEAP_SIZE=1G` (G1), one node 127.0.2.1, `heap_buffers`, `sasi_indexes_enabled: true`, `auto_snapshot: false`, `memtable_cleanup_threshold` default, `memtable_heap_space` 256 MiB (life A), 128 MiB (B), 512 MiB (C) | |

## 3. Runbook defects

The audit fixed what it found before run 1 (B2i, B3i); those are listed for stage 3. Run 1 itself hit these:

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B3a | "not verified whether a yaml flag gates SASI": it does (`sasi_indexes_enabled`, default false, `CreateIndexStatement.java:122-123`); without it the check at line 213 is never reached | B2i.1 | 2026-10-28 | untracked file (sha256 in section 1) |
| 2 | audit | B2a / B3a | `/users/.../cassandra-5.0.9`, `-Dtest.jvm.args`, local scratch paths unverified | B2i.2, B3i.1 | 2026-10-28 | same |
| 3 | audit | B3h | the control was two pool values (128 vs 512 MiB) in a file whose arms use 256 MiB; made a three-point pool control with heap_buffers (`memtable_heap_space` binding) | B3i.1-2 | 2026-10-28 | same |
| 4 | unit shakedown | harness | `NameLengthProbeTest` summed `getCFDirectories()` as `java.io.File`; it returns Cassandra's `File` | `toJavaIOFile()`; recompiled before the run | 2026-10-28 | n/a (harness) |
| 5 | run 1, cluster | B3c / B3i.3 | the first arm at 2,000,000 rows ran at about 2,700 rows/s (heap memtable ~1.4 KB per row, a flush per 60,000 rows at 256 MiB): 12 minutes or more per arm and about 100 minutes in all; the 20,000-row shakedown had shown 4,000 rows/s | aborted after 2 minutes (arm discarded); by B3i.3's own rule N = 500,000 for every arm; B3i.3 amended (dated), case file re-frozen (section 1), the whole cluster tier restarted from its beginning | 2026-10-28 | untracked file (sha256 in section 1) |
| 6 | run 1, cluster | harness (`cluster-run.py` evaluate) | the check "none40: DDL accepted and no row insert failed" tested `create_index in (None, 'ok')`, but the driver reports `'none'` for the arm without an index, so `summary.txt` carries one `EXPECTED ... NO` line (16 yes, 1 NO); the arm itself had ok = 500,000, errors = 0 | script fixed after the run (`('none', 'ok')`); the independent `selfcheck.py` part for that arm holds; the NO line is a script defect, not a reading | 2026-10-28 | n/a (harness) |

## 4. Run 1

**Scope:** unit tier (names: L = 1, 47, 48, 49, 64, 200 x custom / plain x 3 repeats, 10,000 rows; rows: row-count control and unindexed baseline) and cluster tier (life A at 256 MiB: custom 40, 48, 49, 100, plain 40, 48, 100, no-index 40; lives B and C at 128 and 512 MiB: plain 48; N = 500,000 rows of 100 bytes per loaded arm). **Command logs:** `name_length-validatecustomindexcolumnname-name--autonomous/run1/unit/summary.txt`, `run1/cluster/summary.txt`, `run1/cluster/session.log.head` (first 5 KB; full logs on the node). The harness was checked by a unit shakedown and a cluster quick shakedown (20,000 rows) before run 1; the unit shakedown showed the same numbers (owns spread 0.000 percent, directory spread 0.019 percent), so run 1's unit numbers are not independent of what the author had seen; the thresholds of B2i and B3i were frozen first.

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`: 2 JVMs, JUnit OK each, all EXPECTED lines yes)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Custom (SASI) L = 1, 47, 48 | CREATE INDEX accepted, 10,000 rows stored, 3 of 3 repeats | `unit/names.out` |
| Custom L = 49, 64, 200 | CREATE INDEX rejected 3 of 3, exactly "Column '<name>' is longer than the permissible name length of 48 characters" | `unit/names.out` |
| Plain L = 1, 47, 48, 49, 64, 200 (a 200-character column name is accepted by CREATE TABLE) | all accepted, 3 of 3 repeats | `unit/names.out` |
| Memtable `owns()` after 10,000 x 100 B rows, plain index, six L | 6,020,000 B for every L (spread 0.000 percent); custom L = 1, 47, 48: 14,930,308 B for every L | `unit/names.out` |
| Directory bytes after flush (median of 3), plain, six L | 6,787,540 / 6,787,414 / 6,786,852 / 6,787,412 / 6,786,926 / 6,787,236 B for L = 1, 47, 48, 49, 64, 200: spread 0.010 percent; L = 49 vs 48 differ by 560 B; custom L = 1, 47, 48: 4,699,932 / 4,699,320 / 4,699,928 B (0.013 percent) | `unit/names.out` |
| Heap after GC, after load minus before (information) | plain 14.65 to 14.81 MB and custom 10.92 to 11.13 MB at every L, no trend with L | `unit/summary.txt` (INFO lines) |
| Row-count control, plain L = 10, N = 1000 / 10,000 / 100,000 | `owns()` 607,000 / 6,070,000 / 60,700,000 B (ratios 10.00, 10.00); directory 707,236 / 6,789,168 / 68,086,096 B (ratios 9.60, 10.03) | `unit/rows.out` |
| Unindexed baseline, L = 10, N = 10,000 | directory 2,436,076 B against 6,789,168 B indexed | `unit/rows.out` |

**Cluster tier** (`run1/cluster/arms.jsonl`, `summary.txt`; 16 EXPECTED lines yes, 1 NO that is a script defect, section 3 row 6). "dir" = recursive byte sum of the table directory (includes the plain index's hidden directory and the SASI files).

| Arm (pool) | DDL; rows accepted / failed | dir after flush | dir after compaction | MEMTABLE_LIMIT flushes; first logged on-heap usage | Evidence (file) |
|---|---|---|---|---|---|
| custom40 (256 MiB) | accepted; 500,000 / 0 | 174,182,689 | 174,248,268 | 8; 85.424 MiB | `cluster/arms.jsonl` |
| custom48 | accepted; 500,000 / 0 | 174,192,914 | 174,259,086 | 8; 85.360 MiB | same |
| custom49 | CREATE INDEX rejected, exact text; 0 indexes in `system_schema.indexes`; nothing loaded | n/a | n/a | n/a | same, `cluster/summary.txt` |
| custom100 | same, exact text with the 100-character name | n/a | n/a | n/a | same |
| plain40 | accepted; 500,000 / 0 | 170,328,764 | 170,365,850 | 7; 85.406 MiB | same |
| plain48 | accepted; 500,000 / 0 | 170,328,288 | 170,365,253 | 7; 85.325 MiB | same |
| plain100 | accepted; 500,000 / 0 | 170,324,041 | 170,363,381 | 7; 85.375 MiB | same |
| none40 (no index) | n/a; 500,000 / 0 | 114,453,491 | 61,894,672 | 3; 85.375 MiB | same |
| plain48 (128 MiB, life B) | accepted; 500,000 / 0 | 170,324,844 | 170,388,538 | 14; 42.801 MiB | same, `cluster/flush-lines.lifeB.txt` |
| plain48 (512 MiB, life C) | accepted; 500,000 / 0 | 276,558,713 (compaction running) | 170,359,707 | 3; 170.648 MiB | same, `cluster/flush-lines.lifeC.txt` |

Other cluster readings: every logged `MEMTABLE_LIMIT` flush was at 33 percent of the heap pool (85.4 MiB of 256, 42.8 of 128, 170.6 of 512); `jcmd GC.heap_info` used heap after a forced GC ranged from 99.6 MB (custom40) to 150.9 MB (plain100) and 126 to 210 MB across the three plain48 lives, so it varies by more than any plausible effect of a 60-byte difference in column name (information only); RssAnon peaks 1.77 to 1.79 GB for every arm; no `ERROR` line in any `system.log`.

### 4.2 Conclusion and logic

1. **Validity.** The boundary was driven across at both tiers (L = 48 versus 49, 64, 100, 200) and the SASI gate was open (`sasi_enabled=true` printed by the unit test; the custom arms ran) [observed: `unit/names.out`, `cluster/arms.jsonl`]. The pool cap was reached in every life: 7 to 8 pool-triggered flushes per loaded arm at 85.4 MiB logged heap usage in life A (256 MiB), 14 at 42.8 MiB in life B (128 MiB), 3 at 170.6 MiB in life C (512 MiB) [observed: `cluster/flush-lines.life{A,B,C}.txt`]. Fixed settings held: same yaml tail per life, fresh table per arm, same seeded data in every arm [observed: `cluster/summary.txt` (yaml tail), harness]. The controls moved (part 3). Valid.
2. **Readings.** (a) A 200-character column name is accepted by CREATE TABLE and by a plain index; only the custom-index path measures it [observed: `unit/names.out`]. (b) The memtable `owns()` is identical across L to the byte (6,020,000), which is expected if the name is held once in schema metadata and not per row; the rows-mode JVM (L = 10) read 6,070,000 for the same 10,000 rows, 0.8 percent higher than the names-mode JVM: a JVM-to-JVM difference that was not examined, small against the 10x of the control [observed: `unit/names.out`, `unit/rows.out`]. (c) `none40` shows the cost of the index: the plain index adds 108 MB to a 62 MB table [observed: `cluster/arms.jsonl`].
3. **Matched row.** Unit B2g row 1, "Custom L=48 ok, L=49 rejected; plain index accepts 49+ -> Mechanism as traced", and row 2, "Memtable live size and heap flat (differences only a few bytes per name) across L while the control moves -> Claim confirmed: usage does not follow the constraint": L = 1, 47, 48 accepted and 49, 64, 200 rejected with the predicted text for the custom index, all six accepted for the plain index [observed: `unit/names.out`]; memtable `owns()` spread 0.000 percent, directory bytes spread 0.010 percent (plain) and 0.013 percent (custom), no step between 48 and 49 (560 B) [observed: `unit/names.out`]; the row-count control moved the same instruments 10-fold per 10-fold rows (ratios 10.00, 10.00, 9.60, 10.03) [observed: `unit/rows.out`]. Cluster B3g row 1, "Rejection at 49 only for custom; usage equal across L at equal data -> Claim confirmed", and row 2, "Control moves heap/disk while L does not -> negative claim stands": custom 49 and 100 rejected with the exact text and no index created; custom 40, 48 and plain 40, 48, 100 accepted with all 500,000 rows; directory bytes after compaction 170,365,850 / 170,365,253 / 170,363,381 (spread 0.001 percent) for plain L = 40, 48, 100 and 174,248,268 / 174,259,086 for custom L = 40, 48 (0.006 percent); the first logged pool flush was at 85.406 / 85.325 / 85.375 MiB for plain 40, 48, 100 (0.1 percent spread) [observed: `cluster/arms.jsonl`, `flush-lines.lifeA.txt`]. The pool control moved the memory plateau and flush frequency 4-fold and 4.7-fold (42.801 / 85.325 / 170.648 MiB first flush usage; 14 / 7 / 3 flushes at 128 / 256 / 512 MiB) while the final directory bytes stayed 170,388,538 / 170,365,253 / 170,359,707 (0.017 percent) [observed: `flush-lines.life{B,A,C}.txt`, `arms.jsonl`].
4. **Excluded rows.** Unit "Usage scales with L beyond a few bytes, or jumps at 48": spreads 0.000 and 0.010 percent, 560 B between 48 and 49 [observed]. "Control does not move, or L=49 not rejected": the control moved 10-fold, custom 49 rejected 3 of 3 [observed]. "Custom L=49 accepted": no [observed]. Cluster "Usage differs materially with L": 0.001 and 0.006 percent [observed]. "Control does not move, or limit never reached": the pool flush usage followed the pool 4-fold and 3 to 14 flushes occurred [observed].
5. **Observed vs. inferred.** [inferred: "usage does not follow the constraint" is read from usage being independent of L at equal data, and the knob itself cannot be varied (a rebuild with the constant at 96 was not run).] [inferred: tmpfs bytes stand for disk bytes.] [inferred: the column name costs a few bytes once per table, not per row, from the identical memtable bytes; the source (`NAME_LENGTH` is compared once at DDL time) is consistent but the schema storage was not measured.] [inferred: the heap, in a 1 GB G1 heap with 10 to 15 MB noise between arms, cannot show a 60-byte effect; it is not evidence either way, the memtable and file byte counts are.]
6. **Deviations and gaps.** (a) N = 500,000 per arm instead of 2,000,000 (section 3 row 5); the pool was still reached in every life. (b) A pilot of the cluster at 20,000 rows and an aborted 2,000,000-row arm preceded the run. (c) Heap (information) is noisy and not used as evidence. (d) The optional rebuild with the constant at 96 was not run. (e) SASI was exercised at L <= 48 only in the data arms (L = 49 and above are rejected before any SASI work), which is the claim's boundary. (f) One summary line (`none40 ... NO`) is a script defect (section 3 row 6). (g) A plain `CREATE INDEX` on a 200-character column name worked at the unit tier only; the cluster tier used L = 100 as its longest plain name.
7. **Core question.** Usage did not follow `NAME_LENGTH`: at equal data, memtable bytes and file bytes were the same for L = 1 to 200 (to 0.01 percent) and showed no step at 48 (parts 3, 4); the only effect of the constant is to accept or reject the DDL for a custom index at 48 versus 49 characters (part 3). The instruments move where something real moves: with the row count (10-fold per 10-fold) and with the memtable pool (4-fold for a 4-fold setting), while the column name length does not (part 3).

**Conclusion (one line):** unit B2g rows 1 and 2 and cluster B3g rows 1 and 2 - confirmed (the claim: usage does not follow `NAME_LENGTH`).

## 5. Self-check of run 1 - AI

### 5.1 Check of run 1's conclusion

`harness/name_length-validatecustomindexcolumnname-name--autonomous/selfcheck.py` re-parses the raw files (`unit/{names,rows}.out`, `cluster/arms.jsonl`, the node's `system.log.life{A,B,C}` for `MEMTABLE_LIMIT` usage and counts, `summary.txt`) with its own code; output `run1/selfcheck.out`: 32 parts hold, 0 do not hold.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: all 3 repeats per (kind, L) present; pool flushes in every life from the node log (7, 14, 3); no `ERROR`; no daemon of the run left and `/dev/shm/s4-b2` gone (checked also by `ps` after the run). |
| 2. Readings | yes | The identical `owns()` and the directory spreads recomputed from the raw lines; custom49 / custom100 rejected with the exact text and zero indexes. |
| 3. Matched row | yes | Spreads (0.000, 0.010, 0.013, 0.004, 0.006, 0.017 percent) and the pool control (first usage 42.801 vs 170.648 MiB, 14 vs 3 flushes) recomputed from the node's own flush lines, not from `arms.jsonl`. |
| 4. Excluded rows | yes | Same files. |
| 5. Observed vs. inferred | yes | Inferences named in 4.2 part 5; the raw files hold nothing stronger. |
| 6. Deviations and gaps | yes | Listed in 4.2 part 6 and section 3. |
| 7. Core question - the steps from reading to answer follow the audited logic | yes | Boundary (DDL), equal usage across L, and the two moving controls follow B1, B2h, B3h. |

### 5.2 Run 2?

**No** (2026-10-28). The conclusion rests on exact rejection text and on spreads of 0.01 percent or less that the node's own flush lines and file sizes reproduce; the inference that the knob cannot be varied is stated, not hidden. A run 2 would repeat a 35-minute cluster run and add nothing the logs do not hold.

## 6. Run 2 - fresh AI session (optional)

Not done.

## 7. Comparison - only if run 2 was done

Not applicable.

## 8. Verdict - AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap): `NAME_LENGTH` limits a character count at DDL time; the memory and disk of a node, at equal data, do not depend on it.

**Claim tested (B1):** node heap, off-heap and disk usage do not follow `NAME_LENGTH`: the only effect of the limit is accepting or rejecting the DDL at 48 versus 49 characters; indexing and ingesting with a name at 48 and (via a non-custom index) well above 48 costs resource in proportion to data written, not to the limit. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g rows 1 and 2) | does not cap | run 1 + self-check | 2026-10-28 |
| Cluster | **Confirmed** (B3g rows 1 and 2) | does not cap | run 1 + self-check | 2026-10-28 |

**Positive control:** the row-count control moved the instruments 10-fold per 10-fold rows at the unit tier (`owns()` 607,000 / 6,070,000 / 60,700,000 B), and the known-binding cap `memtable_heap_space` moved the first pool-flush usage 42.8 / 85.3 / 170.6 MiB and the flush count 14 / 7 / 3 at 128 / 256 / 512 MiB at the cluster tier, with the same final 170.4 MB (0.017 percent) and no dependence on L.

**Side findings (do not change the verdict):** (1) SASI index creation is off by default in 5.0.9 (`sasi_indexes_enabled: false`); the check at line 213 is behind it. (2) The `NAME_LENGTH` javadoc ("KS or CF name") is stale for tables, which use `TABLE_NAME_LENGTH`. (3) The check is flagged in the source for removal (CASSANDRA-20235, in the TODO at line 226). (4) The disk cost of a plain index on 500,000 rows of 100 B is 2.75 times the table without it after compaction (170 MB against 62 MB), independent of the name.

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (untracked file; sha256 below); the audit amendments B2i and B3i (and the 2026-10-28 amendment to B3i.3) are listed in section 1. Sha256 of the case file with D filled: `489caf966de01305f4d20676f4c3e35b12b998561cf2eb878c86f21089b580df`.
