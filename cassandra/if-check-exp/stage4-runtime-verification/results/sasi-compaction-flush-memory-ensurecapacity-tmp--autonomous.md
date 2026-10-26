# sasi-compaction-flush-memory-ensurecapacity-tmp--autonomous — stage-4 results  <!-- file: results/sasi-compaction-flush-memory-ensurecapacity-tmp--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`sasi-compaction-flush-memory-ensurecapacity-tmp--autonomous`](../../stage3-ai-deep-read/cases/sasi-compaction-flush-memory-ensurecapacity-tmp--autonomous.md)
>
> **Status:** self-checked; verdict filed (2026-10-26)
>
> **Outcome class:** true negative - the stage-3 estimate (negative) against the effect found below (does not cap) ([definition](../README.md#outcome-class))
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
| **Case-file version** | Case file untracked at audit time (orchestrator commits). Original sha256 `56f7d58ca87212e0306ce350fa452507cf57f1a529f5f543e55f665973f45261` (copy at `~/s4-b7-st-logs/case-original.md`); sha256 after the audit's amendments (B5.1-B5.10 and the inline notes): `def8bc85556363c7a00924ba7e78e9ecb51e45a9eb2d981d911e5f13d2d561cd`. Frozen tables, written before any reading: B2f-g (from `**B2f.` to before `**B2h.`; `sed -n '/^\*\*B2f\./,/^\*\*B2h\./p' <file> \| sed '$d' \| sha256sum`) `a85fe3a50913856a5edf2611b19a4cc2f596e49d91ff5f3b2971e185394c064a`; B3f-g (same with `B3f`/`B3h`) `814981b3fbb7c78a8d9e847b15995f919a75818dcbf49b34017fe68948b36629`. (B5.9 and B5.10 also corrected two rounding slips in B3c/B3f (4,993 and 19,972 terms per segment are 4,994 and 19,973) and recorded the memtable-limit flushes; this second freeze is the one used. A first freeze of B3f-g, `f9e955d3...`, with the whole-file hash `76579a63...`, was superseded the same day by amendment B5.9 before any reading: the instrument check showed the index file is about 180 bytes per character at L=100, which made the 1000-character workload impossible on disk. The check runs were M=1 MiB, L=100 and a 4-sort Part 1 run, not readings.) |
| **Harness** | `harness/sasi-compaction-flush-memory-ensurecapacity-tmp--autonomous/` (uncommitted; orchestrator commits). Instrument checks are listed in section 2. |
| **Tiers and values** | Unit: Part 1 `LongTimSort` n in {2^16, 2^20, 2^23} x {random, ascending, descending, runs}; Part 2 CONTAINS L=16,64 x M in {8, 32, 128} MiB and L=256,1000 x M in {8, 32}, PREFIX control at each of these cells (and at M=128 for L=256, 1000). Cluster: 200,000 rows of 200 characters, CONTAINS M in {2, 8, 32} and default (unset), PREFIX control at M=8 and 32, CONTAINS M=8 with 50-character values, a no-index baseline, OOM probe M=32 at 512 MiB heap; heap 8 GiB. |
| **Audit bottom line** | **Ready after amendments** - 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: on-heap bytes of the SASI segment build; the check's own counter is `estimatedBytes` (bytes); the sort buffer `tmp` is bytes (`long[]`). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly | B2b M in {8,32,128}, B3b M in {4,16,64}; the default (161 MB) is not in either list. B5.7: default arm runs last in the cluster tier if time allows (about 25 min of sort, 1.9 GiB of arrays). The target line itself (`tmp` cap `a.length>>>1`) is a constant: B2 Part 1 varies `a.length` instead. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B2d/B3d named JFR and cumulative allocation; cumulative allocation is dominated by comparator garbage (B5.1) and JFR has a TLAB threshold. Replaced (B5.2) by exact array sizes (Byteman) and live heap (class histogram). Gap: the histogram is sampled (lower bound of the peak). |
| A. Core question | usage driven to the limit and past it | Met | B2c builds each builder to the estimate crossing M (mirrors `PerSSTableIndexWriter.java:247`); B3c: 200,000 terms x 1220 B = 244 MB passes M=4/16/64. |
| A. Core question | positive control for a negative-estimate file | Met | B2h(a)/B3h(a) PREFIX arms on the same data with the same cap; closed case `sasi-max_compaction_flush_memory-PerSSTableIndexWriter-estimatedMemoryUse--autonomous` (B5.5). |
| B. Logic | each step says what it establishes | Met | B2e/B3e with B2g/B3g; B1 maps to hypothesis, B2b-e/B3b-e to test and logic, B2g/B3g row 2 is the refuted-if. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | B2f Part 2 and B3f gave cumulative allocation and single-segment peaks; corrected before freeze (B5.1, B5.3) to array sizes and live increment (>= 3x M). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | B3g lacked an OOM/segment-failure row at the main heap: added (B5.3). Values between 1.5x and 3x M in B2g/B3g have no row: reported as `Not confirmed (no matching row)` if they occur. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Disallow event = the segment cut (`Flushed index segment` log lines and the `sort` entries in the Byteman trace); array sizes vs N*L; B3g row 4 (segment count falls with M). |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: PREFIX (same terms, no SuffixSA), L sweep at fixed M, Part 1 shapes (cap binds), baseline without index. |
| C. Specific | a human can follow it from the intro and §9a | Met | Ground line, A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | Test class and sampling are left to the harness; B5.2/B5.4/B5.6 fix the instruments, sizes and runner. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Missing: sampling interval, heap for the main arms, baseline definition, stop for slow cells: fixed in B5.2-B5.4. B3b says 'recreate the index per value with a fresh table': done as a fresh keyspace per arm. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Listed as step-1 work; built into `harness/` (this folder). JDK 11, Ant, Byteman jars in `build/lib/jars` of the copy. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly | Sizes correct (checked: 33554432/1220 = 27,503; 8*27.5 M = 220 MB). Memory: 2 GiB heap too small because 8 segments build at once (`PerSSTableIndexWriter.java:63-69`): main arms 8 GiB (B5.3). Time: the comparator allocates, 110 M characters is about 3 billion comparisons (B5.4). Disk: tmpfs for node data (200 MB of values per arm plus sstable and index copies, under 1 GB). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | All re-read in the 5.0.9 copy: LongTimSort.java:607, 715, 820-839 (the guard is at 821, the cap at 833); SuffixSA.java:64, 84; SA.java:52; OnDiskIndexBuilder.java:182, 194, 245-262; PerSSTableIndexWriter.java:247, 365-369; IndexMode.java:58-60, 186-193; Config.java:606. No wrong line cite. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Cumulative allocation is not a usage measure; judge live-heap increment and exact array sizes | Applied 2026-10-26 (B5.1, B5.2; B2d, B2f, B2g, B2h) | `SuffixSA.java:84-88` + `CharTerm.getSuffix` allocate per comparison |
| 2 | SASI general pool is 8 threads: peak = up to min(8, segments) segments; heap 8 GiB for main arms; OOM probe at low heap | Applied (B5.3; B3a, B3f, B3g, B3h(e)) | `PerSSTableIndexWriter.java:63-69` |
| 3 | Workload sizes and repeats by cell size; stop for slow cells | Applied (B5.4; B2h(d)) | comparator-bound sort time |
| 4 | Runner: ant testsome for the instrument check, JUnitCore per cell for readings | Applied (B5.6; B2a) | per-cell heap and agent; parallel cells |
| 5 | Default arm and positive-control statement | Applied (B5.5, B5.7) | audit group A |
| 6 | Stale '1G default' text and log message (`IndexMode.java:60,:192`) | left for stage 3 (B5.8) | does not affect the claim |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-10-26 (unit run 14:00-14:21Z, cluster run 14:22-15:29Z, OOM probe 15:47-15:59Z) | not done |
| Node | `pc07` (`node0.jason92-320876...`), 40 cores, 251 GiB, shared with other agents; port slot 2 (127.0.2.1, JMX 7120) | |
| OS / kernel | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK / Ant | OpenJDK 11.0.32.1 / Ant 1.10.12 | |
| Local source copy | `~/s4-b7-st` by `copy-source.sh` at repository commit `e776524`; `ant build-test` 1 min 10 s; the unit readings and the node ran from its built classes with no further `ant` (the instrument check used `ant testsome` before) | |
| Case-file / harness commit | untracked at run time (sha256 in section 1); harness uncommitted | |
| Storage for node data | `/dev/shm` (tmpfs, 126 GB, shared; own data removed after each arm; node data peaked at 9.1 GB for the index of one arm, a unit cell at 33 GB) | |
| Full logs (outside the repo) | `~/s4-b7-st-logs/{unit-check,unit-run1,cl-check,cl-run1,cl-oom,cl-oom-invalid1,cl-oom-failed-load}` on `pc07` (`cells/*/jvm.log`, `system.log.filtered`, `pool.csv`, `histo-*.jsonl`) | |

Instrument checks (not readings): unit `check` (`ant testsome` on a 2-size Part 1 cell, then JUnitCore with the agent: ascending sorts keep `tmp` at 256 longs, random reach `a.length>>>1`; `p2:CONTAINS:1:100` and `p2:PREFIX:1:100` builds, which also showed the index file size per character and so led to amendment B5.9); cluster check `cl-check` (50,000 rows, heap 2g: M=2 CONTAINS, M=2 PREFIX, no index; it showed the many small memtable-limit flushes (B5.10) and an early exit in the wait for the memtable index builds, fixed). The OOM probe was run three times: `cl-oom-failed-load` (heap 512m during the load: the load itself timed out, so the probe now loads at 8g), `cl-oom-invalid1` (restart at 512m: the restarted JVM started an automatic compaction of 32 sstables, which built one 7.2 M-character segment and made the arm invalid; fixed with `-Dcassandra.autocompaction_on_startup_enabled=false`), and the run reported here.

## 3. Runbook defects

None beyond the audit amendments B5.1-B5.10 (found before run 1 and filed in the case file). Harness-level fixes, all made before the readings they affect: the port check must test the slot address, not the port alone (another node held 7000 on its own address); the load wait compares memtable index builds with the sstable count; the probe restarts with autocompaction off.

## 4. Run 1

**Scope:** unit tier: Part 1 (12 shape x size cells, 3 repeats) and Part 2 (CONTAINS 10 cells, PREFIX 13 cells; 23 JVMs, all `rc=0`). Cluster tier: 200,000 rows, CONTAINS M=2, 8, 32 and default (unset), PREFIX M=8 and 32, CONTAINS M=8 with 50-character values, no index; OOM probe M=32 at 512 MiB. **Command log:** `sasi-compaction-flush-memory-ensurecapacity-tmp--autonomous/run1/unit/session.log`, `sasi-compaction-flush-memory-ensurecapacity-tmp--autonomous/run1/cluster/session.log`, `sasi-compaction-flush-memory-ensurecapacity-tmp--autonomous/run1/cluster-oom-probe/session.log`; summaries `unit/unit-summary.txt`, `cluster/cluster-summary.txt`, `cluster-oom-probe/cluster-summary.txt`; self-check output `unit/selfcheck-unit.txt`, `cluster/selfcheck-cluster.txt`.

### 4.1 Readings

**Unit tier** (all under `run1/unit/`; "live increment" = peak of the full-GC class-histogram total sampled during `finish()` minus the total just before it)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Part 1, 36 sorts (n = 2^16, 2^20, 2^23 x random, ascending, descending, runs x 3) | every `tmp` <= `a.length>>>1` (largest 4,194,304 longs = 32 MiB at 2^23); random and runs reach exactly `a.length>>>1`; ascending and descending stay at 256 longs (2 KiB); all outputs sorted; thread allocation / final tmp for random 2^23 within [1, 2] | `unit-summary.txt` (Part 1), `cells/p1/trace.txt`, `cells/p1/p1.csv` |
| Part 2, estimate crossing | in all 23 cells `estimatedMemoryUse()` = limit + overshoot, overshoot 12 to 572 bytes (< 1.3 KiB), `chars` = N*L | `cells/p2_*/p2_*.csv`, `selfcheck-unit.txt` |
| Part 2 CONTAINS, array sizes | the `LongTimSort.sort` call of every CONTAINS build has `a.length` = N*L exactly (so the suffix array is exactly `8*N*L` bytes), final tmp = `a.length>>>1` longs | `cells/p2_CONTAINS_*/trace.txt` |
| Part 2 CONTAINS, live increment per limit (increment / M), L=16 / 64 / 256 / 1000 | M=8: 1.32 / 3.08 / 7.72 / 11.55; M=32: 1.33 / 3.50 / 7.72 / 11.57; M=128: 1.35 / 3.49 / not run / not run. Bytes per character 13.7 to 19.9. At L=1000, M=32: 27.5 M characters, 370 MiB live increment (11.6 x M), index file 33 GB, 765 s | `unit-summary.txt`, `selfcheck-unit.txt` |
| Part 2 PREFIX (same terms and limits) | no `LongTimSort` call and no trace file in any of the 13 PREFIX JVMs; sampled live increment <= 0.38 x M (mostly 0.0); one sample per cell (the build lasts 3 to 280 ms) | `cells/p2_PREFIX_*/`, `unit-summary.txt` |

**Cluster tier** (under `run1/cluster/`; heap 8 GiB; baseline = histogram total after full GC, once the memtable index builds are done)

| Capacity value | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| M=2 | CONTAINS, L=200 | segments (`Flushed index segment`), sorts, array | 41 segments = 40 cuts + tail; 41 sorts, 40 of exactly 998,800 elements (7.6 MiB), tail 48,000; 8 at once; peak live increment 184 MiB = 92 x M; compaction 238 s | `segments-c2.txt`, `lts-trace.txt`, `histo-c2.csv`, `cluster-summary.txt` |
| M=8 | CONTAINS, L=200 | same | 11 segments; 10 sorts of exactly 3,994,600 elements (30.5 MiB, tmp 15.2 MiB), tail 54,000; 8 at once; increment 558 MiB = 70 x M; 260 s | `segments-c8.txt`, same |
| M=32 | CONTAINS, L=200 | same | 3 segments; sorts of 15,978,400 (121.9 MiB, tmp 61 MiB) x 2 and 8,043,200; 3 at once; increment 604 MiB = 18.9 x M; 368 s | `segments-c32.txt`, same |
| default (unset) | CONTAINS, L=200 | same | no cut line (the final all-in-memory path), one sort of 40,000,000 elements (305 MiB, tmp 152.6 MiB); increment 664 MiB = 4.3 x the 153.6 MiB default; 546 s | `histo-cdef.csv`, `cluster-summary.txt` |
| M=8 | PREFIX, L=200 | segments, sorts, increment | 11 segments; no sort; increment 11.4 MiB = 1.43 x M | `segments-p8.txt`, `cluster-summary.txt` |
| M=32 | PREFIX, L=200 | same | 3 segments; no sort; increment 45.9 MiB = 1.43 x M | `segments-p32.txt` |
| M=8 | CONTAINS, L=50 (B3h(b)) | increment | 7 segments of 1,553,450 elements, 7 at once; increment 245 MiB, against 558 MiB at L=200 and the same M | `cluster-summary.txt` |
| none | no index (B3h(c)) | increment | 3.1 MiB; no index file | `cluster-summary.txt` |
| M=32, restart at `-Xmx512m` (OOM probe) | CONTAINS, L=200 | node | sort of 15,978,400 elements started, `tmp` grew to 262,144 longs, then `java.lang.OutOfMemoryError: Java heap space`; node killed (`-XX:OnOutOfMemoryError=kill -9`); sampled live total 327 MiB just before; no segment line | `cluster-oom-probe/node-stdout-oom-excerpt.txt`, `lts-trace-sasi-general.txt`, `histo-c32.csv` |

Unit tier: 23 JVMs, three at a time; cluster run 67 minutes (about 8.5 minutes of load per CONTAINS arm). Raw checks: `selfcheck-unit.txt` 117 checks, 0 failed; `selfcheck-cluster.txt` 26 checks, 0 failed.

### 4.2 Conclusion and logic

1. **Validity** - valid. The limit was reached in every cell: unit, `estimatedMemoryUse()` crossed M by less than one term in all 23 cells [observed: `cells/p2_*/p2_*.csv`]; cluster, the cut counts equal cuts + tail for M=2/8/32 (41/11/3) and none for the default [observed: `segments-*.txt`, `selfcheck-cluster.txt`]. Held-fixed settings: JDK, tree and rules the same for all cells [observed: `unit/harness.md5`, `session.log`]; node with `sasi_indexes_enabled: true`, `concurrent_compactors: 1`, heap 8 GiB [observed: `cluster/node-cmdline.txt`]; the option reached the writer [observed: the cut counts differ by M]. Autocompaction off during load and before compaction in the main arms [observed: `cluster/session.log`, `disableautocompaction` lines].
2. **Readings** - (a) PREFIX unit increments are sampled once (the build lasts milliseconds), so "no increment" is a low-resolution reading; the evidence that matters for PREFIX is the absence of any sort. (b) Cluster peak increments are not proportional to M: 184, 558, 604, 664 MiB for M=2, 8, 32, default. [inferred: the SASI general pool has 8 threads and queued segments keep their builders; the trace shows 8, 8, 3, 1 sorts at once and `pool.csv` the same active counts, so the sum saturates at min(8, segments) segments; per segment the live cost is 10 to 20 bytes per character at every M.] (c) The default arm produced 4.3 x the default limit although it never cut.
3. **Matched row** - unit, B2g row 1 ("biggest `long[]` ~ `8*N*L` and peak live increment over `finish()` at least 3x M at L=1000, growing with L at fixed M"): the sorted array has exactly N*L elements in every CONTAINS cell [observed: traces]; increment/M is 11.55 and 11.57 at L=1000 and rises 1.3, 3.1-3.5, 7.7, 11.6 with L at fixed M [observed: `unit-summary.txt`]. Cluster, B3g row 1 ("peak live increment at least 3x M, rising with M, `long[]` of exactly `8*charCount`", values as amended by B5.9): 92 x M (M=2), 69.8 x M (M=8), 18.9 x M (M=32); increments rise with M (184, 558, 604, 664 MiB); sorted arrays exactly 8 x 998,800 / 3,994,600 / 15,978,400 / 40,000,000 bytes [observed: `cluster-summary.txt`, `lts-trace.txt`]. The probe prediction (OOM although the limit is 32 MiB) held [observed: `node-stdout-oom-excerpt.txt`]. Control rows also seen: tmp shape (256 longs on sorted input, `a.length>>>1` on random), PREFIX (1.43 x M, no sort), segment count falls with M (41, 11, 3, 0 cuts).
4. **Excluded rows** - "increment <= 1.5x M / flat across L, no long[] ~ 8*charCount" (Refuted row): the arrays are exactly `8*N*L` and the increment per M rises from 1.3 to 11.6 across L; ruled out. "tmp > 4*a.length bytes": the largest tmp is exactly `a.length>>>1` longs (4 bytes per array element), never above [observed: Part 1 and all traces]; ruled out. "Estimate never reached / index never builds": ruled out by the cut counts. "Heap increment constant across M while the control moves": the PREFIX control stayed at 1.43 x M while CONTAINS moved from 184 to 664 MiB; ruled out. "OOM or failed segment in a main arm at 8 GiB": none (`OutOfMemory` and `Failed to` counts 0). Values between 1.5x and 3x M (no row): none occurred (smallest CONTAINS ratio at L=1000 or L=200 is 11.55 and 18.9).
5. **Observed vs. inferred** - inferred: (i) the increment of a CONTAINS build is suffix array + tmp + decoded chars [8 + 4 + 2 bytes per character against 13.7 to 14.4 measured at L >= 64; 19.9 at L=16 includes about 130 bytes per term]; (ii) the cluster increment saturates because of the 8-thread pool; (iii) reading a multiplier that depends on L (1.3 to 11.6 at fixed M) as "does not cap" is a judgment on observed numbers; (iv) sampling at 1 to 2 s gives a lower bound of the true peak.
6. **Deviations and gaps** - values of 200 characters (cluster) and a reduced unit grid because of index size (B5.9); M=128 not run at L=256 and 1000; unit cells above 20 M characters run once; PREFIX unit increments sampled once; the default arm builds one segment, so it cannot show a cap by cut; the probe lowers the heap only for the compaction; JFR not used (Byteman trace instead); runner is JUnitCore, not `ant testsome` (B5.6).
7. **Core question** - The constraint does not cap the heap of the build: with the option at M, a SASI segment build holds 10 to 20 bytes per character of the segment's terms (a `long[]` of exactly `8*N*L` bytes, a `tmp` of up to half that, decoded chars), which is 1.3 x M at L=16 and 11.6 x M at L=1000 for the same limit (steps 1-3), up to 8 such segments at a time, and a 512 MiB node dies of OutOfMemoryError at a 32 MiB limit (step 3). The `tmp` guard itself holds as traced: at most half the array, 2 KiB when the input is already sorted.

**Conclusion (one line):** B2g row 1 (unit) and B3g row 1 (cluster) - confirmed: the real heap does not follow `max_compaction_flush_memory_in_mb` (does not cap).

## 5. Self-check of run 1 - AI

### 5.1 Check of run 1's conclusion

Re-parsed from the raw files by `harness/sasi-compaction-flush-memory-ensurecapacity-tmp--autonomous/selfcheck.py` (separate code from the analyzers), run 2026-10-26: unit 117 checks, 0 failed; cluster 26 checks, 0 failed (`unit/selfcheck-unit.txt`, `cluster/selfcheck-cluster.txt`). The OOM probe was re-read by hand (the script checks the main arms).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | overshoot < 1.3 KiB in all unit cells; cut counts 41/11/3 and 0 re-counted from `segments-*.txt`. |
| 2. Readings | yes | PREFIX sampling resolution and the saturation of the cluster increment are stated; no reading contradicts another. |
| 3. Matched row | yes | `alen` equals N*L in every CONTAINS cell (re-parsed); ratios re-computed from CSV bytes. |
| 4. Excluded rows | yes | tmp never above `a.length>>>1` in every sort of the traces; no OOM in main arms. |
| 5. Observed vs. inferred | yes | the inferred statements are marked; none changes the matched row: the exact array sizes and the OOM are observed. |
| 6. Deviations and gaps | yes | listed above. |
| 7. Core question - the steps from reading to answer follow the audited logic | yes | B1 -> exact arrays -> live increment against M and L -> PREFIX and tmp controls -> probe. |

### 5.2 Run 2?

**No** (2026-10-26). The conclusion rests on exact array sizes read from the Byteman trace (unit and cluster agree with `8*N*L` to the byte), a PREFIX control with no sort, and an OOM; the unit repeats agree within 3 percent. A run 2 would not change a row.

## 6. Run 2 - fresh AI session (optional)

Not done.

## 8. Verdict - AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested (B1):** the heap used while building a SASI CONTAINS-mode index segment does not follow `max_compaction_flush_memory_in_mb`: it is several times M (about `8n + up to 4n + 2n` bytes for n characters) even though `estimatedMemoryUse()` stays just under M. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed - B2g row 1 (suffix array exactly `8*N*L`; live increment 11.6 x M at L=1000, 1.3 x M at L=16) | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | Confirmed - B3g row 1 (arrays exactly `8*n`; increment 18.9 x M at M=32, 70 x M at M=8, 92 x M at M=2; OOM at 512 MiB with M=32) | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control:** the `tmp` buffer follows the array (Part 1: 4 bytes per element for random input, 2 KiB for sorted), and where the estimate describes the data (PREFIX, same terms, limit and cuts) the live increment stayed at 1.43 x M in the cluster and no sort array existed; the closed case `sasi-max_compaction_flush_memory-PerSSTableIndexWriter-estimatedMemoryUse--autonomous` showed the estimate binding in PREFIX mode. The control moved while CONTAINS did not follow M.

**Feedback filed:** the case file's section D updated (not committed by this agent); amendments B5.1-B5.10 in B2/B3/B5, no other section changed. Upstream/doc candidates: the "1G default" text in `IndexMode.java:60,:192` (default is 0.15 GiB); the SASI estimate omits the CONTAINS suffix array (8 bytes per character) and the comparator allocates two buffers per comparison (`CharTerm.getSuffix`).

**Leftovers:** none running; tree `~/s4-b7-st` and logs `~/s4-b7-st-logs` kept; `/dev/shm` data removed.
