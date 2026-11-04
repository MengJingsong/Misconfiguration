# compression-metadata-writer-addOffset-maxCount--autonomous — stage-4 results  <!-- file: results/compression-metadata-writer-addOffset-maxCount--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`compression-metadata-writer-addOffset-maxCount--autonomous`](../../stage3-ai-deep-read/cases/compression-metadata-writer-addOffset-maxCount--autonomous.md)
>
> **Status:** verdict filed (2026-10-26); run 1 both tiers, self-checked, no run 2
>
> **Outcome class:** true negative (estimate `negative`, effect `does not cap`; [definition](../README.md#outcome-class))
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
| **Case-file version** | Repository HEAD at audit `1ae567d` (the case file is untracked there; the orchestrator commits it). sha256 of the whole file after the audit's amendments, recorded 2026-10-26 before any reading: `4fae26e45a2f9bf35d462c9e70061d75f03a64110c1a7758eeaecc8356e874ff` (the original was `b9bc399d90b846addc631a9d98bd605448a38208984d282eaba51e81e7ef5fbf`). **Frozen prediction and conclusion tables** (B2f, B2g, B2h, B3f, B3g, B3h; `sed -n '/^\*\*B2f/,/^\*\*B2h/p;/^\*\*B3f/,/^\*\*B3h/p' <case file> \| sha256sum`, run on the amended file, B2h and B3h opening lines included): `8ce93c042d9bb5a4632f02fe9fe99abe26f1e721b8d1eea68664d813b613f34d`. Section D is the only part that changes after a run. |
| **Harness** | `harness/compression-metadata-writer-addOffset-maxCount--autonomous/` (written after this audit; commit by the orchestrator) |
| **Tiers and values** | Unit: N in {99, 100, 101, 200, 201, 1000, 65,536, 100,000, 10,000,000} x chunk length {4096, 16384, 65536}, plus controls C1-C3. Cluster: K in {64, 16, 4, 1} KiB, n=400,000 rows per keyspace, one uncompressed table, chunk-cache control at 48 and 96 MiB `file_cache_size` |
| **Audit bottom line** | Ready after amendments, 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A1-A2: off-heap (native) bytes of the chunk-offset array, 8 B per chunk; source re-read: `CompressionMetadata.java:346-348, 364-373` |
| A. Core question | knob varied, >= 3 values incl. default — or another approach, with the reason | Met | `maxCount` is a literal (`:346`), not settable; B2b/B3b vary the driver (N, chunk length K in {64,16,4,1}, default 16 included) and say why |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | unit: `offHeapSize()` is the SafeMemory capacity (`:163-166`, `chunkOffsets.size()`), a counter of the allocation, cross-checked with process RSS (B2d); cluster: the gauge plus the `-CompressionInfo.db` size and a Byteman trace of the allocation sizes. RSS cannot resolve the transient peak (named in B2d) |
| A. Core question | usage driven to the limit and past it | Met | unit N from 99 to 10M passes 100 and every doubling; cluster SSTables hold 31k to 2M chunks after amendment |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps name their reading |
| B. Logic | prediction stated in numbers or a clear relation | Partly -> Met after amendment | B2f 10M row was wrong (13,107,200 / 104,857,600, not 12.8M / 102.4M) and N=200 missing; B3f numbers assumed 4 GiB and a wrong transient-RSS figure; fixed, and B3f now states an exact relation (metric = 8 x header chunk counts) |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g cover rejection at 100, no growth, plateau, errors on crossing, control not moving, data too small |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | for a negative claim the "branch" is the doubling at `:366`: unit by reflected `maxCount`/`count`, cluster by the added Byteman trace |
| B. Logic | alternative explanations and their controls | Partly -> Met after amendment | B2h was clumsy (named an unused cache, a "positive control" undefined); rewritten as C1-C3. B3 control `file_cache_size` 16/64 MiB was unusable (chunk cache off by default; cache size is file_cache_size - 32 MiB); fixed |
| C. Specific | a human can follow it from the intro and B1/B2f/B2g | Met | claim B1 is clear; B2g's wording on the control updated |
| C. Specific | an AI can run B2a-B2e / B3a-B3e without re-deriving the code path | Partly -> Met after amendment | B3c gave stress options that create one table in one keyspace; amended with the keyspace-per-K, pre-created tables. The harness is mine |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met after amendment | see recommendations 5-9 |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | none existed; listed as step-1 work (probe class, run scripts, Byteman rule, JMX client from the sibling harness) |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly -> Met after amendment | `n=4,000,000 -col size=FIXED(1000)` is 5 cells x 1000 B x 4M = about 20 GB per table, not 4 GiB (4 tables = 80 GB, node had 36 GB free). Now n=400,000 (about 2.0 GB per table) on tmpfs |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Partly -> Met after amendment | every cite re-read; 6 wrong or imprecise, fixed (below) |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | A3.2: the doubling calls `SafeMemory.copy` (`SafeMemory.java:70-74`), not `Memory.copy` (`Memory.java:211-215`) | Applied 2026-10-26 | `offsets` is a SafeMemory; `Memory.java:65` is the allocation it reaches |
| 2 | A3.4: header and offsets are written at `:425-427`, not 426-427 | Applied 2026-10-26 | line cite |
| 3 | A3.5: the int overflow happens at the doubling from 1,677,721,600 (k=25), not "at 2^30 / k=24"; `:351` (`Writer.chunkCount`) is `long`, not `int`; size at 16 KiB is 25 TiB | Applied 2026-10-26 | the arithmetic and the type were wrong |
| 4 | B2c/B2f: N=10M gives 13,107,200 entries / 104,857,600 B (12,800,000 / 102.4 MB was wrong); add N=200 and N=100,000; peak 157,286,400 B; B2e `:441-447` is `:446-450`; B4 peak ~157 MB | Applied 2026-10-26 | 100 x 2^17 = 13,107,200; arithmetic checked in Python |
| 5 | B2h rewritten as C1 (fixed 800-byte `Memory`, 101st long throws under `-ea`), C2 (reading moves up and down), C3 (-ea / -da on N=101), with the gap named; B2g control rows reworded | Applied 2026-10-26 | the old paragraph was unreadable and did not name a control that could be run |
| 6 | B3a/B3b/B3g/B3e: the chunk-cache control needs `file_cache_enabled: true` (default false, `cassandra.yaml:742`) and a size above 32 MiB (`ChunkCache.java:49-50, 53`); use 48 and 96 MiB; metric names `Size` and `Capacity` (`CacheMetrics.java:69-70`) | Applied 2026-10-26 | with the write-up's setting no cache exists |
| 7 | B3c: `-col size=FIXED(1000)` means 5 cells, about 5 kB/row, so n=4,000,000 is about 20 GB; use n=400,000 per K, a keyspace per K, tables pre-created (stress creates only `standard1`, `IF NOT EXISTS`, `SettingsSchema.java:168`) | Applied 2026-10-26 | data would not fit the node; one table per K was impossible as written |
| 8 | B3f: replace the "~3x, ~100 MiB transient RSS" prediction by the Byteman doubling trace and an exact relation (metric = 8 x header chunk counts) | Applied 2026-10-26 | 3x of a 15 MiB final is not 100 MiB and 5-s RSS sampling cannot see it |
| 9 | Data on tmpfs `/dev/shm` instead of local disk | Applied 2026-10-26 (B3a) | shared home disk had 36 GB free; HANDOFF lesson |
| 10 | The positive control is not on the same resource (chunk cache is a different native-memory consumer); no cap on compression-metadata exists | Left for stage 3 | named as a gap in section 8 |
| 11 | Cites checked and found right: `CompressionMetadata.java:346-348, 366, 368-372, 163-166, 188-202, 409-418`; `CompressedSequentialWriter.java:98, 103, 183`; `CompressionParams.java:48, 153, 344-360, 447-451`; `TableMetrics.java:761-770`; `SSTableReader.java:730-731`; `cassandra.yaml:753, 799` | n/a | recorded for the self-check |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (UTC; node shell clock 2026-10-25 MDT) | not done |
| Node (CloudLab name and type) | `pc07` (`node0.jason92-320876`, control 198.22.255.17), 40 cores, 251 GiB; local, no ssh | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-cm` by `copy-source.sh` at repository commit `1ae567d` (`cassandra-5.0.9`); `ant build-test` 1 min 17 s; the probe `ChunkOffsetGrowthTest.java` copied into `~/s4-cm/test/unit/org/apache/cassandra/io/compress/` | |
| Case-file commit / harness commit | case file untracked at `1ae567d`, sha256 `4fae26e4…874ff` at the freeze (see §1); harness uncommitted (orchestrator commits) | |
| Storage for node data | cluster tier: tmpfs `/dev/shm/s4-cm-data` (deleted after the self-check); unit tier: `/dev/shm` temp dirs | |
| Full logs (path, outside the repo) | `~/s4-cm-logs/` on pc07 (`unit-run.log`, `run1/{M,C48,C96}/`, `unit-attempt1/`, `selfcheck.out`); node ports JMX 7329, Byteman 9329, native 9351, storage 7029, `127.0.29.1` | |

## 3. Runbook defects

Every step a run could not execute as written. The run stops at the
defect; the fix is made in the case file (dated) if it leaves §9a unchanged,
and the affected tier restarts from its beginning. If the fix would change
§9a, the case goes back to the audit. "None" if there were none.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | unit attempt 1 | B2a run command | `ant testsome -Dtest.name=<simple class name>` ran the test (1 test, 0 failures) and then reported a spurious second suite "Null Test" error, so `ant` exited 1 | harness `run-unit.sh` uses the fully qualified name; unit tier re-run as attempt 2 (all readings identical in kind; attempt 1's are kept as `unit-readings-attempt1.txt`) | 2026-10-26; no change to B2f/B2g | n/a (harness only) |
| 2 | cluster shakedown | B3c command | the stress arguments contain `(`, so the shell failed (`Syntax error: "("`); found in a 20,000-row shakedown, not a reading | `shlex.quote` on stress arguments | 2026-10-26 | n/a (harness only) |
| 3 | cluster shakedown | harness check | a script-only expectation "dataLength unchanged by compaction" was too strict; loosened to 0.5 %, and it still fails in run 1 (see §4.2 part 6); it is not part of B3f | none needed | 2026-10-26 | n/a |

## 4. Run 1

**Scope:** the tiers and capacity values actually run. **Command log:**
`compression-metadata-writer-addOffset-maxCount--autonomous/run1/<file>`.

### 4.1 Readings

**Unit tier** (`ChunkOffsetGrowthTest`, `ant testsome`, JUnit 1 test, 0 failures, `-ea` on; `results/compression-metadata-writer-addOffset-maxCount--autonomous/run1/unit-readings.txt`, `unit-run-excerpt.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| N = 99, 100 (chunk 4096/16384/65536) | `maxCount` 100, `count` N, 0 doublings, `offHeapSize()` 800; after `prepareToCommit` 8N (792, 800); no exception | `unit-readings.txt` |
| N = 101 | `maxCount` 200, 1 doubling, `offHeapSize()` 1600; after prepare 808; no exception | same |
| N = 200 / 201 | 200 / 1600 and 400 / 3200 (2 doublings at 201); after prepare 1600 / 1608 | same |
| N = 1000 | 1600 / 12,800 (4 doublings); after prepare 8000 | same |
| N = 65,536 | 102,400 / 819,200 (10 doublings); after prepare 524,288 | same |
| N = 100,000 | 102,400 / 819,200; after prepare 800,000 | same |
| N = 10,000,000 | 13,107,200 / 104,857,600 (17 doublings); after prepare 80,000,000; `-CompressionInfo.db` 80,000,039 B; RssAnon rose from 265-299 MB to 354-377 MB and its 5-ms peak was 431-450 MB, 161-164 MB above the start (the case's predicted transient peak is 157,286,400 B) | same |
| `-CompressionInfo.db` size for every cell | 8N + 39 bytes | same |
| C1: `Memory.allocate(800)`, 100 longs then `setLong(800, x)` | `java.lang.AssertionError: Illegal bounds [800..808); size: 800` (assertions on) | `unit-readings.txt` last READING line |
| C3: `addOffset` x101 by plain `java`, `-ea` then `-da` | capacity 200, `offHeapSize()` 1600, no exception in both | `c3-ea.txt`, `c3-da.txt` |

**Cluster tier** (node `127.0.29.1`, heap 2 GiB, tmpfs, 400,000 rows per keyspace written with `cassandra-stress`, 0 errors each, `results/compression-metadata-writer-addOffset-maxCount--autonomous/run1/M/summary.txt`)

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| K=64 KiB | A, after flush (15 SSTables) / after compact (1) / after restart | `CompressionMetadataOffHeapMemoryUsed` ; header chunk count | 277,944 B (34,743 chunks) / 247,280 B (30,910 chunks) / 247,280 B | `M/summary.txt` (METRIC, CI lines) |
| K=16 KiB (default) | same | same | 1,111,600 B (138,950) / 989,016 B (123,627) / 989,016 B | same |
| K=4 KiB | same | same | 4,446,320 B (555,790) / 3,956,032 B (494,504) / 3,956,032 B | same |
| K=1 KiB | same | same | 17,785,184 B (2,223,148) / 15,823,728 B (1,977,966) / 15,823,728 B | same |
| uncompressed keyspace (100,000 rows) | B | same | 0 at all three readings | same |
| all | A | ratio metric(K) / metric(4K) | 4.00, 4.00, 4.00 (flush); 4.00, 4.00, 4.00 (compact) | same |
| all | A | Byteman trace of `SafeMemory.copy` in `addOffset` | 64 writers doubled, 528 doubling lines, 155 `doPrepare` lines; every writer's sequence 200, 400, 800, ..., each at `count` = previous capacity; largest capacity 3,276,800 (100 x 2^15), the K=1 compaction writer, whose final count is 1,977,966 | `M/summary.txt` TRACE lines, `M/cm.trace.*`, `selfcheck.out` |
| all | A | `system.log` ERROR lines | 0 in the main arm; 0 in the whole file after the controls | `M/summary.txt`, `selfcheck.out` |
| file_cache_size 48 MiB (cache 16 MiB) | control C48 on the same data | ChunkCache `Capacity`, `Size` (1 s), ks16 offsets gauge | Capacity 16,777,216; Size rose 1.5 MB -> 16,777,216 and stayed there; gauge 989,016 in all 16 samples | `C48/summary.txt`, `C48/samples.csv` |
| file_cache_size 96 MiB (cache 64 MiB) | control C96 | same | Capacity 67,108,864; Size reached 67,108,864; gauge 989,016 in all 17 samples | `C96/summary.txt`, `C96/samples.csv` |

### 4.2 Conclusion and logic

Tag every statement in parts 1–4 as **[observed: `<file>`]** or
**[inferred: `<reason>`]**. An untagged statement is not part of the
argument.

1. **Validity** — valid. Unit: N reached 10,000,000, far past the initial 100 and 17 doublings [observed: `run1/unit-readings.txt`]; assertions were on in the test JVM (`assertionsEnabled=true` in the RUN line) and the C3 launch covered both settings [observed: `c3-ea.txt`, `c3-da.txt`]. Cluster: every SSTable held thousands to 2.2 million chunks, against the initial 100 [observed: `M/summary.txt` CI lines]; the Byteman rule fired (528 doubling lines) [observed: `M/summary.txt`]; the control caches reached their capacity [observed: `C48/samples.csv`, `C96/samples.csv`]. "Hold fixed": the node ran with file_cache_enabled at its default (false) in the main arm, heap 2 GiB, tmpfs, autocompaction disabled for the test keyspaces until the explicit compact [observed: `M/session.log` yaml line, `M/summary.txt`].
2. **Readings** — nothing contradicts a prediction. (a) The flush SSTables of one keyspace total about 2.28 GB of data length in 15 files, against 2.03 GB in the single compacted file (11 % less); I did not explain it (about 450,000 rows' worth were flushed for 400,000 partitions written); it does not enter B3f, whose relation (metric = 8 x header chunk counts) holds at each of the three readings [observed: `M/summary.txt`]. (b) The compacted files' header counts are one more than `ceil(dataLength / chunkLength)`; the flush files' equal it [observed: `M/summary.txt` CI lines; `selfcheck.out`]. (c) The 10M RSS delta (161-164 MB) matches the 157 MB peak only roughly; RSS is a cross-check, not a reading the prediction relies on [inferred: the peak is old + new = 3 x 52,428,800 B].
3. **Matched row** — Unit B2g: "`count` passes 100 with no exception; capacity doubles per the table | Claim confirmed" [observed: all 27 cells match B2f, `unit-readings.txt`], "Capacity tracks N (ratio capacity/(8N) between 1 and 2)" [observed: e.g. 819,200 / 800,000 for N=100,000; 104,857,600 / 80,000,000 = 1.31 for 10M], and "Controls (B2h): C1 throws on the fixed 800-byte region, `addOffset` does not at the 101st offset, and C2 moves | Confirmed" [observed: C1 AssertionError; N=101 `addOffset` no exception; C2 800 -> 1600 -> ... -> 104,857,600 -> 80,000,000]. Cluster B3g: "Metric scales with 1/K and total data, far above 800 bytes, no errors | Claim confirmed" [observed: 0.25 / 0.99 / 3.96 / 15.8 MB, ratio 4.00, no ERROR line] and "Chunk cache `Size` plateaus at `Capacity` while offsets metric grows | Positive control binds; claim confirmed" [observed: Size 16,777,216 and 67,108,864 held while the offsets gauge stayed at 989,016 during the read; the offsets metric itself scaled with the chunk count across the four K values, 0.25 to 15.8 MB for the same data].
4. **Excluded rows** — B2g "offHeapSize stays at 800 for N>100, or an exception at 100": ruled out, 1600 at N=101 and no exception in any cell [observed]. "N never exceeded 100, or C1 did not throw, or C2 did not move": ruled out, N up to 10M, C1 threw, C2 moved [observed]. B3g "plateaus near a fixed value independent of data size" (**Refuted** row): ruled out, the metric tracks the chunk count and rises 4x per K step for the same data [observed]. "Writer errors/stalls when crossing 100, 200, ...": ruled out, the trace shows each doubling and the stress runs ended with 0 errors [observed]. "Chunk cache does not move, or metric does not scale with K (too small data)": ruled out, the cache filled and the SSTables hold 31k to 2M chunks [observed].
5. **Observed vs. inferred** — inferred: (i) that the Byteman line is the line-366 branch and not another copy (the rule is on `Writer.addOffset` at the `copy` invoke; the sequence 200, 400, ... at `count` = old capacity is what line 366-368 does) [inferred: source `CompressionMetadata.java:366-368`]; (ii) that "no cap" holds for any size, from the sizes tested (N to 10M; 2 million chunks on a node) [inferred: no code path rejects, `addOffset` has no limit check]; (iii) the chunk cache as a stand-in for a binding cap on the same resource [inferred: both are native memory read by the same Table gauge family, but they are different consumers].
6. **Deviations and gaps** — The transient old + new peak was not measured on a node (RSS sampling cannot resolve it; the trace gives the sizes, not the peak). The `int` overflow edge (13.4 GB buffer) was not reached. No cap exists for `maxCount`, so the positive control is a different bound (C1: a fixed 800-byte `Memory`; the chunk cache), not a cap on the same resource; section 8 names this. One cluster lifetime was a restart of the main arm; the controls ran on the same data directory. Run 2 was not done.

7. **Core question** — Usage did not follow `maxCount`: the offsets buffer grew from 800 B past 100 entries by doubling at every crossing (no rejection, 17 doublings to 104,857,600 B in the unit tier; 528 doublings on the node), and on the node the off-heap total tracked the chunk count (8 B x chunks, 4x per K step), not any ceiling [parts 3-4]. The constraint (a growth threshold) therefore does not cap usage: the bound on the resource is the data volume divided by the chunk length [part 3, inferred (ii)].

**Conclusion (one line):** B2g/B3g "claim confirmed; usage does not follow `maxCount`" — Confirmed, does not cap, both tiers.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-open every raw file the conclusion cites and confirm it says what the
conclusion says. A part that does not hold is fixed, or the conclusion is
downgraded to *Not confirmed*.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.py` (re-parses `unit-readings.txt`, the live `-CompressionInfo.db` files, `cm.trace`, `samples.csv`, stress logs, `system.log`; output `run1/selfcheck.out`, 31 of 31 checks hold) plus a re-read of the RUN line (`assertionsEnabled=true`), the 528 doubling lines and the two sample files |
| 2. Readings | yes | the 11 % flush-versus-compact data-length gap and the +1 chunk in compacted files are real in the raw CI lines and the script's own "unchanged" expectation fails for them (4 lines, `M/summary.txt`); the self-check treats that expectation as outside B3f; I did not explain the gap |
| 3. Matched row | yes | the self-check recomputes capacity = 100 x 2^ceil(log2(N/100)), doublings, 8 x capacity before and 8N after prepare for all 27 cells, and 8 x header chunks for every metric reading, from the raw files, not the EXPECTED lines |
| 4. Excluded rows | yes | no exception string in any cell; capacity above 100 for every N > 100; trace sequences are consecutive doublings; stress logs show 0 errors; `system.log` has no ERROR line |
| 5. Observed vs. inferred | yes | the three inferred items are labelled; (i) rests on the source (re-read lines 366-368) and the trace's `count` = previous capacity at each fire |
| 6. Deviations and gaps | yes | transient peak not measured; control is not the same resource; both stated. Attempt 1 of the unit tier and the quoting defect are recorded in §3 |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1 -> B2f/B3f relations -> the readings above; the only inference is generalising from tested sizes, and the code has no limit check on that path |

### 5.2 Run 2?

**No** (2026-10-26) — the readings are exact counts that the self-check recomputed from raw files, there is no refuted row, and the remaining inferred item (generalisation beyond tested sizes) is a code fact, not a measurement run 2 could add. Original template text: **Yes / no** — the reason, and the date decided. Choose yes when the conclusion rests on inferred statements, a part of §5.1 cannot be settled from run 1's evidence, or the result refutes the case or confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2 says no); §7 is left out.

**Scope:** the tiers and capacity values actually run. **Command log:**
`compression-metadata-writer-addOffset-maxCount--autonomous/run2/<file>`.

### 6.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|

**Cluster tier**

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|

### 6.2 Matched row

The §9a row these readings match, in one line.

## 7. Comparison — only if run 2 was done

| Observable | Run 1 | Run 2 | Criterion (§1) | Agree? |
|---|---|---|---|---|

**Same §9a row?** yes / no. If no, or if a reading disagrees: the cause, and
how it was resolved (see "Compare and decide" in the README).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its
date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** B1: the off-heap memory used for chunk offsets does not follow `maxCount`: capacity scales with the number of chunks written (data size / chunk length), exceeds 100 entries without any rejection, and is only bounded by data volume, not by a cap. "Confirmed" below means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed: B2g "count passes 100 with no exception; capacity doubles per the table → Claim confirmed" with the capacity-tracks-N row and the controls row | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | Confirmed: B3g "Metric scales with 1/K and total data, far above 800 bytes, no errors → Claim confirmed", with the chunk-cache control row | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control** (a negative-estimate file only): no cap binds `maxCount`'s resource, so none could be the same-resource control the protocol asks for. What moved: unit, C1 (a fixed 800-byte `Memory` rejects the 101st long with an `AssertionError`, `addOffset` does not) and C2 (`offHeapSize()` rose to 104,857,600 and fell to 80,000,000 after trimming); cluster, the chunk cache `Size` filled to its capacity (16 MiB, then 64 MiB) while the compression-metadata gauge stayed at 989,016 during the same read. The file is Confirmed on these controls; the gap (a different consumer, not a cap on this one) is recorded for stage 3. Not shown: the `int` overflow edge at 1,677,721,600 entries and the on-node transient peak.

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (uncommitted; the orchestrator commits); amendments to A3.2, A3.4, A3.5, A4/A5 cites, B2c, B2f, B2h, B2g, B3a, B3c, B3d, B3e, B3f, B3g, B3h and B4 listed in §1.1 (dated 2026-10-26, before any reading). Leftovers: none running; `~/s4-cm` (tree), `~/s4-cm-logs`, `~/s4-cm-jmx` kept on pc07; `/dev/shm/s4-cm-data` deleted.
