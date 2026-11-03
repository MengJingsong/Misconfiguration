# index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous — stage-4 results  <!-- file: results/index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous.md -->

> **Case:** [`index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous`](../../stage3-ai-deep-read/cases/index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous.md)
>
> **Status:** verdict filed, 2026-10-25. **Unit: Not confirmed — caps (counted size)** (unit re-run "run 1b" of 2026-10-25 at the re-frozen version
> `40b91e73…b36a`, after the user-authorised amendment of B2h (b), B2f (iv) and the B2f (v)/(vi) interval relation; B2g row "own_alloc ≠ own →
> Not confirmed for the real resource", the match stated in the amendment before the run; §7, §8). Every relation about the counted size held, and so did
> both controls; the summaries rebuilt by upsampling allocate 76 × (Σ maxEntries + k) B = 1.729 × their counted size, as derived. **Cluster: Confirmed — caps**
> (run 1; closed, not re-run). The run-1 unit verdict below (Invalid) stays on record as filed.
>
> **Outcome class:** undetermined — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous/`](../harness/index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous/).
>
> **Run-1 status (as filed 2026-10-25):** verdict filed, 2026-10-25. **Unit: Invalid — undetermined** (B2g added row "a B2h control misses its expectation": control (b), raising the pool back to 4 MiB after C = 0, restored only 7 of 63 summaries — own 559,328 / 551,276 B, not S0 = 3.44 MB; every cap relation of B2f held: after each redistribution the total stayed ≤ C + 4,096 B (2,080,091 · 1,034,651 B at 2 · 1 MiB), own(2)/own(1) = 2.01 / 2.05, the zero pool gave the floor exactly (44 B × Σ⌈maxEntries/16⌉), and the pool acted only through a redistribution (control (a)); the mean-interval relation failed and after upsampling the malloc'd summary memory was 1.47 × the counted size). **Cluster: Confirmed — caps** (B3g row 1: after the R1 redistribution and through every later scheduled run the summaries' total was 2,093,412 / 8,379,692 B at 2 / 8 MiB (≤ C + 4,096 B; own 2,093,000 / 8,379,280 B, ratio 4.003), intervals ≈ 1,014 / 226 against ≈ 1,003 / 251 predicted; auto (102 MiB) left the full 16,406,460 B = 140 B × 117,189 entries; with the scheduled task off (c2null) the full size stayed until R1 and then fell to 2,091,032 B). Real resource in the cluster: the counter only (gap named; RSS did not move). No run 2.
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-25, on the advisor's machine (`environment-advisor.md`).
> The verdict is against this file's own predictions and conclusions. `ConfigProbe.java` was copied unchanged from the
> `counter_cache_size-applySimpleConfig` harness; `unit-run.sh`, `cluster-run.sh`, `cluster-chain.sh` and the JMX tool follow that
> harness's patterns (copied, then adapted in the copy). That case's readings are not used as evidence here.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `0dcdfe0` (sha256 `a7147c5b…f9570`, checked equal to the filed row before the audit). Frozen after the step-0 audit's seventeen amendments (2026-10-25, before any harness run or reading): sha256 **`6c8d37ff8ce9441ee5ee644d1882211307a3a84396e458155cea33bb11bc9579`**, a new row in `_INDEX.md` §4. Both tiers' run 1 ran at this version; no runbook fix was needed. Nothing committed (no commit was asked for). |
| **Harness** | [`../harness/index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous/`](../harness/index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous/): `ConfigProbe.java` (copied unchanged), `IndexSummaryCapProbeTest.java` (CQLTester mechanism test), `unit-run.sh`; `ISSampler.java` (one-connection JMX tool: 5-s sampler of the `IndexSummaries` MBean and the table gauge, read-back, the `redistributeSummaries` call R1, the `IndexIntervals` map), `cluster-run.sh` (one node lifetime), `cluster-chain.sh` (run 1 order and the shakedown). Instrument checks before run 1: the three Java files compiled against the run clone (`instrument-compile.log`, rc 0; `bash -n` of the scripts); cluster shakedown `sd-c1` (`1MiB`, interval 1m, 1,500,000 partitions, 100,000 reads; `shakedown/sd-c1/`, a harness check, not a reading). **Bound check against the shakedown:** the full own size after compaction was 1,640,800 B = 140 B × 11,720 entries, inside 140 × [⌈1,500,000/128⌉, + k] = 140 × [11,719, 11,722], so the 140 B per entry and the S formula the cluster bands use hold; after R1 the pool total was 1,039,072 B ≤ 1 MiB + 4,096 B and own 1,038,660 B ≥ 0.85 MiB; the three own SSTables' interval (202) was within 1 % of 128 × 1,640,800 / 1,038,660 = 202.2. No bound was changed. The shakedown found no harness defect. It already showed that the B3f (ix) INFO expectation (floor before the reads) does not hold: the no-read runs left own at 456,540 B, not at the floor (§4.2). Self-check: [`run1/selfcheck.py`](index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous/run1/selfcheck.py). |
| **Tiers and values** | Unit (B2): ConfigProbe with `-1MiB`, `0MiB`, `512KiB`, `1024KiB`, unset (auto), `-Xms1G -Xmx1G`, each its own `java`; mechanism test in two `ant testsome` JVMs (`-Xms1024m`): JVM-A startup auto (= 50 MiB), JVM-B startup `2MiB`; in each, S0, control (a), R0 at the startup value, C = 4, 2, 1, 0 MiB via the MBean setter, control (b). N = 10,000,000 rows (32-byte keys), 10,000 reads. Cluster (B3): one node, `MAX_HEAP_SIZE=2G`; lifetimes c2 (`2MiB`, 1m), c8 (`8MiB`, 1m), cauto (auto = 102 MiB, 1m), c2null (`2MiB`, null interval); 15,000,000 partitions with 128-byte keys, 1,000,000 uniform reads, R1 = the MBean operation `redistributeSummaries`. |
| **Audit bottom line** | **Ready after amendments**, 2026-10-25. |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: off-heap bytes of BIG index summaries; operand `memoryPoolBytes` against Σ `getOffHeapSize()` (`IndexSummaryManager.java:184-199`, `IndexSummaryRedistribution.java:138-145`). |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly → Met after amendment | Unit: 4/2/1/0.1 MiB by setter only; the startup value (the yaml knob under test) was never used for a redistribution, and 0.1 MiB cannot be set (the setter takes whole MiB). Amendment B2b: two JVMs (auto, `2MiB`) whose R0 uses the startup value; 0.1 → 0. Cluster: 2/8 MiB + auto; with the filed data 8 MiB would not bind (B3c amendment). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Partly (gap named) | Unit: amendment B2d adds the malloc'd sizes of each summary's two `Memory` blocks (own_alloc). Cluster: only the counter (MBean and table gauge, two paths to the same `getOffHeapSize()`); NMT does not see JNA `Native.malloc` (`MemoryUtil.java:81-84`), `vmmap` cannot attach here without `sudo` (checked); RSS recorded as INFO. Gap named in B3d. |
| A. Core question | usage driven to the limit and past it | Partly → Met after amendment | Unit: S0 = 3.28 MiB against 1 and 2 MiB caps (and 0). Cluster: the filed 10-byte keys give 4.9 MiB < 8 MiB; amendment B3c: 128-byte keys, S = 15.65 MiB, 7.8 × and 2.0 × the 2 and 8 MiB caps. |
| B. Logic | each step says what it establishes | Partly | B2e/B3e list steps; the readings tables carry the meaning. Left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | "≈ 3.4 MiB (±30 %)", "≈ 7 MiB", "≈ 128 × S0/2" replaced by sizes derived from the source (44 B / 140 B per entry, S0, S, F exact) and fixed tolerances (B2f, B3f). |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | B2g/B3g had three or four rows. Added: read-back mismatch, KiB accepted, zero read rate / wrong format, S0 off, usage above C (Refuted), overshrink, own_alloc ≠ own, control failure, c8 not binding, interval relation failing, c2null failures. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Size ≤ C and ∝ C, plus the disallow branch: the `index summaries: downsample: n` lines and the sampling levels below 128 (levels/intervals read in both tiers). |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | Control (a) (no redistribution → no change) and (b) (upsampling back) made exact; the c2null lifetime separates the cap from the scheduled task; cauto is the non-binding arm. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3 and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Added: how redistribution is triggered (setter + `redistributeSummaries()` in the unit test with the scheduled task cancelled; R1 on the MBean in the node), why reads must precede it (read rates; 0/0), compaction disabled, the format, the test timeout. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | Exact keys, batches, read seed, waits, stress commands, compaction wait, windows, sampler, R1 time (B2c–B2e, B3c–B3e). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met after amendment | `/local/...` paths replaced by this host's clone, probe and node directories (B2a, B3a, B4). |
| D. Runnable | workload arithmetic reaches the limit | Met after amendment | Unit 10 M inserts (≈ 1 min per JVM measured later); cluster ≈ 2.7 GB per lifetime against 147 GiB free; 15 M writes at ≈ 75 k/s (shakedown rate). |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked in `~/cassandra-src` at `cassandra-5.0.9`: `DatabaseDescriptor.java:866-876, 3886-3889, 4136-4150`, `Config.java:373, 539-543`, `DataStorageSpec.java:42-108`, `conf/cassandra.yaml:931-947`, `IndexSummaryManager.java:96-145, 184-252, 286-289`, `IndexSummaryManagerMBean.java:24-50`, `IndexSummaryRedistribution.java:54-330`, `IndexSummaryBuilder.java:100-149, 196-251, 273, 294-314`, `IndexSummary.java:64-120, 208-262`, `SafeMemoryWriter.java:24-120`, `Memory.java:58-80`, `MemoryUtil.java:81-84`, `RestorableMeter.java:36-215`, `SSTableReader.java:1405-1450, 1618-1660`, `SinglePartitionReadCommand.java:1360-1375`, `BigTableWriter.java:150-180, 305-330`, `IndexSummaryMetrics.java:30-50`, `TableStatsPrinter.java:130-137`, `SettingsCommandPreDefined.java:82-128`, `StorageService.java:976-980`. The citation lines in the amendments were corrected against the clone before the freeze. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone, probe dir, ConfigProbe copied with the JDK 11 flags, one `ant testsome` per startup value, `-Xms1024m`, `-Dtest.timeout=1800000`, format BIG checked | Amendment 2026-10-25 | Paths did not exist; once-per-JVM initialisation; auto reads `totalMemory()`; 10 M inserts exceed 480 s. |
| 2 | B2b: `0MiB`, `1024KiB` ConfigProbe variants (the yaml's "Min unit: KiB" is wrong); two JVMs whose R0 uses the startup value; 0.1 → 0 | Amendment 2026-10-25 | Group A; the setter takes whole MiB. |
| 3 | B2c: exact workload, scheduled task cancelled, compaction disabled, reads + 6 s wait before any redistribution; sizes 44 B, S0, F derived | Amendment 2026-10-25 | Exactness; a redistribution without read rates is not the traced share. |
| 4 | B2d: own_alloc (malloc'd `Memory` sizes), levels, intervals, rates | Amendment 2026-10-25 | Group A real resource. |
| 5 | B2e: order | Amendment 2026-10-25 | Open. |
| 6 | B2f: exact relations (i)–(viii), 4,096 B allowance derived | Amendment 2026-10-25 | "≈" without tolerance; "≤ C" needs the rounding allowance. |
| 7 | B2g: ten rows | Amendment 2026-10-25 | Group B. |
| 8 | B2h: controls (a), (b) exact | Amendment 2026-10-25 | "confirm or note". |
| 9 | B3a: this host; read-back by log line and MBean | Amendment 2026-10-25 | Paths; no read-back named. |
| 10 | B3b: c2, c8, cauto, c2null | Amendment 2026-10-25 | B3h's null-interval run had no place. |
| 11 | B3c: 128-byte keys, 15 M partitions (8 MiB binds); exact commands; S, F derived | Amendment 2026-10-25 | 10-byte keys give 4.9 MiB < 8 MiB. |
| 12 | B3d: R1 on the MBean as the deterministic trigger; JMX sampler instead of `sjk`; NMT not applicable; RSS INFO; gap named | Amendment 2026-10-25 | Group A, determinism; `sjk` can exit 0 on failure. |
| 13 | B3e: order, windows, shakedown with a bound check | Amendment 2026-10-25 | Exactness. |
| 14 | B3f: relations (i)–(viii) and INFO (ix), (x) | Amendment 2026-10-25 | Group B. |
| 15 | B3g: seven rows | Amendment 2026-10-25 | Group B. |
| 16 | B3h: controls exact | Amendment 2026-10-25 | Exactness. |
| 17 | B4: this host's disk check and cleanup | Amendment 2026-10-25 | `/local` paths. |
| 18 | B2e/B3e steps do not say what each establishes | Left for stage 3 | Not needed for a valid run. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-25 (unit 11:32–11:35 EDT; shakedown 11:36–11:42; cluster 11:43–12:19 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64; 10 cores, 32 GiB RAM; internal SSD (APFS, `/dev/disk3s1`), 148 GiB free at start and 147 GiB before each lifetime (re-checked; the harness requires ≥ 20 GiB); loopback 127.0.0.1–.3 present (re-checked with `ifconfig lo0`, `env-check-before-cluster.txt`; one node used, 127.0.0.1); ports 7000/7199/9042/9091 free and no `CassandraDaemon` before the run (re-checked by every lifetime and at the end, §8) |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). ConfigProbe: `java -Xms1G -Xmx1G` + the 17 JDK 11 module flags. Test: `ant testsome` forks, `-Xmx1024m` (build.xml) + `-Xms1024m` (`totalMemory` = `maxMemory` = 1,056,309,248 B → auto 50). Node: G1, `-Xms2G -Xmx2G` (`MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`) → auto 102 (read back) |
| Ant | 1.10.18 |
| Local `cassandra-src` clone commit | `$W/cassandra-run14` = `~/Library/Caches/stage4/cassandra-run14`, `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), built with `ant -Dlocal.repository=$W/m2 build-test` (`BUILD SUCCESSFUL`, 50 s) |
| SSTable format | BIG (logged by the test; `nb-*-big-*` files in the node) |
| Case-file commit / harness commit | filed `0dcdfe0`; amendments, harness and results uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-isc/{data,commitlog,hints,saved_caches,cdc_raw,logs}`, wiped before and after each lifetime; unit test data under `$C/build/test/cassandra` (removed by the harness); ConfigProbe data under `$W/probe-isc/data` (removed) |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/index_summary_capacity-applySimpleConfig/`: `clone-build-run14.log`, `instrument-compile.log`, `unit-run.out`, `unit/` (`p1-*.out`, `ant-*.log`, `TEST-*.xml`, `TEST-log-both-jvms.log`, `stage4.out`, `summary.txt`, `commands.log`, yaml diffs), `shakedown/sd-c1/` (not evidence), `cluster/{c2,c8,cauto,c2null}/` (`system.log`, `node.out`, `samples.csv`, `r1.txt`, `intervals-final.txt`, `tablestats-*.txt`, `stress-*.log`, `redistribution-lines.txt`, `summary.txt`, `commands.log`), `cluster/chain.out`, `env-check-before-cluster.txt`, `selfcheck.out` |

## 3. Runbook defects

None: every step of B2a–B2e and B3a–B3e ran as written at the frozen version.

Harness defects (no case-file change, no effect on a reading):

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| H1 | run 1, unit | B2d (log excerpt) | `unit-run.sh` looked for the test log under `build/test/logs/*IndexSummaryCapProbeTest*.log`; at this tag it is `build/test/logs/_jdk11/TEST-org.apache.cassandra.probe.IndexSummaryCapProbeTest.log`, and both JVMs append to it, so `ism-lines-<v>.txt` and the `READBACK` lines of `summary.txt` came out empty | the log was copied by hand after the run (`unit/TEST-log-both-jvms.log`, excerpt `ism-lines-from-test-log.txt`); the glob was corrected in `unit-run.sh` afterwards (commented "harness fix H1"). The knob read-back used by B2f is the test's own `STAGE4 run` line, not this log | 2026-10-25, after run 1 | none |

Re-freeze after run 1 (R1, a case-file amendment authorised by the user) and harness changes for the unit re-run (added 2026-10-25 by the unit re-run session):

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| R1 | unit run 1 (readings, not a runbook defect) | B2h (b), B2f (iv), B2f (v)/(vi) interval relation | The read rates at S0 were 270–273 × apart per summary entry: a meter whose first 5-s tick came after its reads took them at full weight, the others at α = 0.0055. So control (b) restored only 7 of 63 summaries, (iv) failed in JVM-B and the interval relation failed. The tier was Invalid (§4.2) | **Re-freeze, authorised by the user (Yang, the advisor) on 2026-10-25:** six dated amendments `Amendment 2026-10-25 (after run 1, authorised by the user) — B2h (b), B2f (iv), B2f (v)/(vi) interval relation` (B2c, B2d, B2e, B2f, B2g, B2h). The read meters are initialised before the reads, and the reads hit every 100th key once in shuffled order. New precondition (P): max ρ / min ρ ≤ 1.10, maxEntries ≥ 160. (iv) and control (b) are re-derived (values unchanged). The interval relation is re-derived, with a per-SSTable level band added. own_alloc after an upsample is stated as INFO, and the frozen own_alloc relation is unchanged. B2g gains a (P) row and an evenness row. New sha256 `40b91e73…b36a` as a new row in `_INDEX.md` §4. The whole unit tier was re-run from its beginning in a fresh clone `$W/cassandra-run19` (§7). B1, the cap relations that held, control (a), ConfigProbe and B3 are unchanged; the cluster tier stays closed | user, 2026-10-25 | uncommitted (no commit asked for) |
| H2 | unit re-run | B2c–B2e (amended) | The test implemented run 1's reads (10,000 random keys, no meter initialisation) | `IndexSummaryCapProbeTest.java` changed only as the amendment requires: wait 6 s and initialise every own meter (logged), 100,000 reads of `key(100 p + 50)` in `Collections.shuffle(…, new Random(42))` order, read-phase duration logged, rate and `count()` per SSTable at every reading. sha256 `ea3b905c…` (run 1, commit `4b93658`) → `fed35ea6…`. Compiled against the run clone before the run (`run1b-unit/clone-build-run19.txt`). `unit-run.sh` (`b3b5af4a…`, with H1) and `ConfigProbe.java` (`f6243b52…`) unchanged; the runner takes the clone, probe and log paths from `C`, `P`, `L` | AI, 2026-10-25 | n/a (harness) |
| H3 | unit re-run | self-check | `run1/selfcheck.py` evaluates run 1's wording and also the closed cluster tier | `run1b-unit/selfcheck.py`: the unit part of `run1/selfcheck.py`, extended with `--relations amended` ((P), interval (b), per-SSTable parsing) or `--relations run1`. `run1/selfcheck.py` unchanged. Known-answer pass on run 1's raw unit files: with `--relations run1` it reproduces run 1's 10 unit failures exactly; with `--relations amended` run 1 fails (P) (`run1b-unit/selfcheck-known-answer-on-run1.out`) | AI, 2026-10-25 | n/a (harness) |
| H4 | unit re-run | derivation check | — | `harness/<stem>/derivation-sim.py` (new): the transcription of `adjustSamplingLevels` cited in the B2f amendment as a check of the derivation; it is not an instrument of the run | AI, 2026-10-25 | n/a (harness) |

## 4. Run 1

**Scope:** both tiers, every value in §1. **Command logs:** `run1/unit/commands.log`, `run1/cluster/<label>/commands.log`, `run1/cluster/chain.out`.

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, `stage4.out`, `p1-*.line`, `TEST-*.xml`, `ism-lines-from-test-log.txt`; one JVM per startup value; both `ant testsome` rc 0, `Tests run: 1, Failures: 0, Errors: 0`, 70 s each)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| ConfigProbe `-1MiB` | `REJECT ConfigurationException: Invalid yaml: …/-1MiB.yaml / root: java.lang.IllegalArgumentException: Invalid data storage: -1MiB Accepted units:[MEBIBYTES, GIBIBYTES] where case matters and only non-negative values are accepted`; the line-872 message does not appear | `p1--1MiB.line` |
| ConfigProbe `0MiB` | `OK getIndexSummaryCapacityInMiB=0` | `p1-0MiB.line` |
| ConfigProbe `512KiB` / `1024KiB` | `REJECT … Invalid data storage: 512KiB Accepted units:[MEBIBYTES, GIBIBYTES]` / the same for `1024KiB`: **the yaml comment "Min unit: KiB" (`conf/cassandra.yaml:938`) is wrong**; even a whole MiB written in KiB is refused | `p1-512KiB.line`, `p1-1024KiB.line` |
| ConfigProbe unset (`-Xms1G -Xmx1G`) | `OK getIndexSummaryCapacityInMiB=51` | `p1-unset.line` |
| Knob read-back in the test JVMs | JVM-A: knob 50 = `max(1, (int)(1,056,309,248 × 0.05 / 2^20))`, manager 50, format `big`; JVM-B: knob 2, manager 2; resize interval 60 → set to −1 in both | `stage4.out` (`STAGE4 run`, `resize-interval`) |
| Load | 10,000,000 rows, 63 own SSTables (21 per batch: memtables flushed on their own as well), 2 other BIG SSTables (35 B of summary); 10,000 reads, all found | `stage4.out` (`batch`, `reads`) |
| Read rates at S0 | 0.095–35.6 /s (JVM-A), 0.063–35.6 /s (JVM-B), median 0.18; the SSTables flushed in the last seconds before the reads carry ≈ 170–200 × the rate of the others | `stage4.out` (`per-sstable … tag=S0`) |

| Reading (own = Σ `getOffHeapSize()` of the 63 own summaries) | JVM-A total / own / own_alloc (B) | JVM-A levels; mean interval (pred.) | JVM-B total / own / own_alloc (B) | JVM-B levels; mean interval (pred.) | `downsample / upsample` (A; B) |
|---|---|---|---|---|---|
| S0 (pool = startup) | 3,439,207 / 3,439,172 = 44 × 78,163 / = own | 128; 128 | 3,438,591 / 3,438,556 = 44 × 78,149 / = own | 128; 128 | — |
| control (a): pool 1 MiB, 10 s, no redistribution | 3,439,207 / 3,439,172 / = own | 128 | 3,438,591 / 3,438,556 / = own | 128 | — |
| R0 at the startup value (50; 2 MiB) | 3,439,207 / 3,439,172 / = own | 128 | **2,064,603** / 2,064,568 / = own | 8–128; 920 (213) | 0/0; 26/0 |
| C = 4 MiB | 3,439,207 / 3,439,172 / = own | 128 | 2,064,603 / 2,064,568 / = own (**not S0**) | 8–128; 920 | 0/0; 0/0 |
| C = 2 MiB | **2,080,091** / 2,080,056 / = own | 8 (26 SSTables) – 128 (37); 920 (212) | **2,064,603** / 2,064,568 / = own | 8–128; 920 (213) | 26/0; 0/0 |
| C = 1 MiB | **1,034,651** / 1,034,616 / = own | 8–128; 1,530 (426) | **1,007,723** / 1,007,688 / = own | 8–128; 1,530 (437) | 20/0; 20/0 |
| C = 0 | 217,043 / **217,008 = 44 × 4,932** / = own | 8; 2,048 | 217,307 / **217,272 = 44 × 4,938** / = own | 8; 2,048 | 17/0; 17/0 |
| control (b): C = 4 MiB after C = 0 | 559,363 / **559,328** / **825,588** | 8–128; 1,835 | 551,311 / **551,276** / **811,104** | 8–128; 1,835 | 0/7; 0/7 |

Bounds (B2f): C + 4,096 B = 2,101,248 B (C = 2) and 1,052,672 B (C = 1); lower bounds 1,887,437 B and 891,290 B. own(2)/own(1) = **2.0105** (A), **2.0488** (B).

**Cluster tier** (`run1/cluster/<label>/summary.txt`, `r1.txt`, `intervals-final.txt`, `samples.csv`, `tablestats-*.txt`, `redistribution-lines.txt`, `stress-*-results.txt`; one node lifetime per value)

| Observable | c2 (`2MiB`, 1m) | c8 (`8MiB`, 1m) | cauto (102 MiB, 1m) | c2null (`2MiB`, null) |
|---|---|---|---|---|
| (i) log line / MBean capacity, interval | 2 MB, 1 min / 2, 1 | 8 MB, 1 min / 8, 1 | 102 MB, 1 min / 102, 1 | 2 MB, −1 min / 2, −1 |
| (ii) write partitions, errors; rate; read ops, errors | 15,000,000, 0; 90.0 k/s; 1,000,000, 0 | 15,000,000, 0; 89.9 k/s; 1,000,000, 0 | 15,000,000, 0; 89.2 k/s; 1,000,000, 0 | 15,000,000, 0; 89.9 k/s; 1,000,000, 0 |
| compaction settled after; live SSTables | 8 s; 6 | 8 s; 5 | 8 s; 4 | 10 s; 5 |
| own after compaction settled (tablestats) | 11,670,680 | 11,677,680 | **16,406,460** | **16,406,460** |
| (ix, INFO) own after the 75-s no-read window | 1,904,140 | 6,949,880 | 16,406,460 | 16,406,460 (no run) |
| scheduled runs before R1 | 5 | 5 | 5 | **0** |
| R1: pool total before → after; call time | 1,904,552 → **2,093,412**; 2.6 s | 6,950,292 → **8,379,692**; 1.4 s | 16,406,872 → 16,406,872; 2 ms | **16,406,872 → 2,091,032**; 40 ms |
| R1 `downsample / upsample` | 3 / 3 | 2 / 2 | 0 / 0 | 5 / 0 |
| max pool total after R1 (samples after R1; bound C + 4,096) | 2,093,412 (32; 2,101,248) | 8,379,692 (33; 8,392,704) | 16,406,872 | 2,091,032 (14; 2,101,248) |
| final own (table gauge = tablestats) | **2,093,000** | **8,379,280** | **16,406,460** | **2,090,620** |
| (vii) own intervals at the end; mean (predicted 128 × 16,406,250 / own) | 1024 ×5, 964; 1,014 (1,003) | 252 ×3, 248, 128; 226 (251) | 128 ×4 | 1024 ×3, 964, 1092 |
| scheduled runs after R1 | 4, all `downsample 0, upsample 0` | 4, all 0 / 0 | 4, all 0 / 0 | 0 |
| (x, INFO) RSS before → after R1 (KiB); own change | 4,490,720 → 4,490,736; +184 KiB | 4,573,952 → 4,574,016; +1,396 KiB | no change; 0 | 4,526,784 → 4,526,832; **−13,980 KiB** |

Derived (recomputed by `selfcheck.py`): own_final(c8)/own_final(c2) = **4.0035**. The full own size 16,406,460 B = 140 B × 117,189 entries, inside 140 × [117,188, 117,188 + k]. c2null: own constant at 16,406,460 B in all 54 samples from compaction-settled to R1, including the 150 s after the reads.

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity.** [observed: `stage4.out`, `p1-*.line`, `TEST-*.xml`] The startup value reached the pool in both JVMs (50 = the auto formula on the logged `totalMemory`; 2). The format was BIG and every own SSTable supports summaries. Every own read rate was > 0 at S0. All 10,000 reads found their row. Compaction was off and the scheduled task cancelled, so only the explicit calls redistributed (the log shows six redistributions per JVM, one per call; `ism-lines-from-test-log.txt`). S0 was 3.3 × the 1 MiB cap. Control (a) held. **Control (b) missed its frozen expectation** in both JVMs (own 559,328 / 551,276 B, not S0). By the frozen B2g row "a B2h control misses its expectation → tier Invalid", the tier is invalid.
2. **Readings.** (a) The read rates are very unequal [observed: `per-sstable … S0`]: the 15-minute rate initialises at the meter's first 5-s tick, and an SSTable whose first tick came before the reads gets only α ≈ 0.0055 of its reads per tick, while one created in the last 5 s before the reads gets them all (`RestorableMeter.java:76-94`, `RestorableEWMA.tick`) [inferred: from the source and the ≈ 170–200 × spread, close to 1/α ≈ 180]. The audit assumed equal shares. (b) So the downsampling is uneven: at C = 2 MiB 26 SSTables went to the floor and 37 stayed at full sampling, and the arithmetic mean of the intervals (920) is not 128 × S0/own (212). The frozen interval relation of (v)/(vi) fails at every redistributed reading. (c) For the same reason, raising C again (JVM-B C = 4 after R0; control (b) after C = 0) upsampled only the hot SSTables (`upsample: 7`): a cold SSTable's target stays below 1.5 × its current entries (`IndexSummaryRedistribution.java:235`). (d) **After upsampling, the malloc'd summary memory exceeds the counted size**: own_alloc 825,588 B vs own 559,328 B (1.48 ×) and 811,104 vs 551,276 B (1.47 ×). The upsample path builds a new summary from the primary index without `prepareToCommit()`'s trim (`BigTableReader.java:631-640`; compare `BigTableWriter.java:320` and `IndexSummaryBuilder.java:245-251`), so the `Memory` blocks keep the builder's capacity, sized for 64-byte keys (`cassandra.index_summary_expected_key_size`, `IndexSummaryBuilder.java:42, 105-128`), while `getOffHeapSize()` counts only the used bytes [inferred: from the source; observed: the two sums]. Before any upsampling own_alloc = own exactly at every reading.
3. **Matched row.** B2g added row "a B2h control misses its expectation" → **tier Invalid**. [observed: control (b) own ≠ S0 in both JVMs.] The added row "own_alloc ≠ own → Not confirmed for the real resource" also matches [observed: control (b) readings].
4. **Excluded rows.** Row 1 ("claim holds"): it needs B2f (i)–(viii) and both controls; (iv) (JVM-B), the interval part of (v)/(vi) and control (b) fail. "size stays ≈ S0 for C < S0" (row 2): own fell to 2.08 / 1.03 MB. "size < C/2" (row 3) and "own below the lower bound": own ≥ 0.96 C everywhere. "C = 0.1 gives ≈ F" (now C = 0): holds exactly (44 × Σ⌈maxEntries/16⌉), consistent with the claim. "total > C + 4,096 B" (Refuted): the largest excess is none — the totals are 13,925–40,853 B below C. ConfigProbe rows: `-1MiB`, `512KiB`, `1024KiB` refused as predicted, `0MiB` accepted, auto 51. Knob read-back, zero read rate, format and S0 rows: not triggered (S0 = 44 × Σ maxEntries, in range).
5. **Observed vs. inferred.** The explanations in 2(a), 2(c), 2(d) are inferred from the source. The verdict does not rest on them: it rests on the observed control (b) reading.
6. **Deviations and gaps.** None in the procedure. The derivation behind (v)'s interval relation, (iv) for JVM-B and control (b) assumed equal read shares; the run shows that the meter's first-tick behaviour makes the shares unequal. This is a design error found by the readings, so it is not amended (the prediction stands as frozen) and goes to stage 3 as feedback (section D).
7. **Core question.** Within this tier, every reading of the size against the cap behaved as B1 says: the startup value sets the pool, a redistribution brings the counted total under C (2,080,091 and 1,034,651 B for 2 and 1 MiB; 2,064,603 B at the startup value 2 MiB), the size scales with C (2.01 / 2.05 for 2:1), a zero pool gives the floor exactly, and nothing changes without a redistribution. But the tier is Invalid by its own conclusions table, and its real-allocation reading shows that the counter can understate the malloc'd memory by ≈ 1.5 × after upsampling.

**Unit tier conclusion:** B2g added row "a B2h control misses its expectation" — **invalid run** (tier).

**Cluster tier**

1. **Validity.** [observed: `readback-line.txt`, `readback-mbean.txt`, `stress-*-results.txt`, `samples.csv`, `yaml-overrides.txt`] The read-back gives 2 / 8 / 102 / 2 MB and intervals 1 / 1 / 1 / −1 minutes. Every lifetime wrote 15,000,000 partitions and read 1,000,000 with 0 errors. Compaction settled before the reads in each lifetime. The full own size 16,406,460 B (cauto, c2null) lies in the derived range, so the caps were passed 7.8 × (2 MiB) and 1.96 × (8 MiB). Only the knob lines differ between lifetimes (`yaml-overrides.txt`). Valid.
2. **Readings.** (a) INFO (ix) did not hold: the no-read redistributions left own at 1,904,140 B (c2) and 6,949,880 B (c8), both under C but well above the floor (≈ 1.03 MB), and cauto stayed at full size [observed: `tablestats-noread.txt`]. The audit missed that `distributeRemainingSpace` (`IndexSummaryRedistribution.java:258-264, 327-355`) gives leftover pool back to SSTables slated for downsampling [inferred: source]. It is not a condition of any row. (b) During the write, the logged total exceeded C (up to 6.04 MiB in c2 at 15:45–15:46), because new and compacting SSTables arrive or stay at full size between runs, as the file's B3f says. (c) RSS did not follow the summaries: in c2null the counted size fell by 13,980 KiB and RSS rose by 48 KiB (INFO; macOS malloc keeps freed pages, so RSS cannot isolate them).
3. **Matched row.** B3g row 1, "settled size ≤ C, interval rising as C falls → cap governs off-heap summaries", with the amended B3f (i)–(viii) and B3h. [observed: (i) exact; (ii) complete; (iii) full size 16,406,460 B in range; (iv) c2: ≤ 2,093,412 B after R1 and at all 32 later samples (bound 2,101,248), own 2,093,000 ≥ 1,782,579; (v) c8: ≤ 8,379,692 B (bound 8,392,704), own 8,379,280 ≥ 7,130,317; (vi) 4.0035 ∈ [3.4, 4.7]; (vii) mean intervals 1,014 and 226 within 12 % of 1,003 and 251, cauto all 128; (viii) cauto full size; B3h (a) c2null: interval −1, no redistribution before R1, own constant at full size for 54 samples, then 2,091,032 B after R1; (b) = (viii).]
4. **Excluded rows.** "settled size ≈ S for all C" (row 2): 2.09 and 8.38 MB against 16.41 MB. "floor F > C" (row 3): the floor (≈ 1.03 MB) is below 2 MiB and no own SSTable reached interval 2,048. Added rows: read-back and workload fine; full size in range, so c8 binds; no total above C + 4,096 B after R1; no own below the lower bound; (vi) and (vii) hold; c2null held its size before R1 and shrank at R1; cauto stayed full.
5. **Observed vs. inferred.** [inferred: the counter is the off-heap allocation] The cluster reads `getOffHeapSize()` by two paths (MBean, table gauge), which agree to the byte apart from the other keyspaces' 412 B. The unit tier found that this equals the malloc'd size except for summaries rebuilt by upsampling, which allocate ≈ 1.5 × more for 32-byte keys. In c2 and c8, R1 upsampled 3 and 2 SSTables, so their real allocation is probably above the counted 2.09 / 8.38 MB. By how much is not measured here: the builder starts with room for 64 + 8 bytes per entry (`IndexSummaryBuilder.java:105-128`), and these entries are 136 bytes, so the buffer grows by `DataOutputBuffer.calculateNewSize` (doubling, `DataOutputBuffer.java:158-170`) and ends somewhere between the used size and twice it. The verdict rests on the counted total, as frozen.
6. **Deviations and gaps.** None in the procedure. Real resource: the counter only. NMT does not see JNA malloc, `vmmap` cannot attach, and RSS did not respond (gap named at the audit).
7. **Core question.** The counted off-heap size of the index summaries follows the constraint once a redistribution runs. It settles at ≈ C (2.09 / 8.38 MB, 0.998 C) for 2 and 8 MiB, ratio 4.00, with the sampling interval rising as C falls (≈ 1,014 / 226). It stays at full size when C is above it (auto, 102 MiB). With the periodic task off (null interval) it stays at full size until a redistribution is called, then drops under C within 40 ms. Between runs, new SSTables can carry it above C. The cap is soft and periodic, as the Estimate says.

**Cluster tier conclusion:** B3g row 1 — **confirmed**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.py` was written separately from the harness. It re-reads the raw `p1-*.out`, `stage4.out`, `TEST-*.xml` and `TEST-log-both-jvms.log`, and for each lifetime `readback-line.txt`, `readback-mbean.txt`, `stress-write.log`, `stress-read.log`, `samples.csv`, `r1.txt`, `intervals-final.txt`, `summary.txt` and `system.log` under the full log root. It re-tests every frozen relation. Result: **59 hold, 10 fail** (`run1/selfcheck.out`). All 10 failures are in the unit tier, and they are exactly the ones §4.2 names: control (b) ×2, own_alloc = own at control (b) ×2, the interval relation ×5 (A: C2, C1; B: R0, C2, C1), and (iv) in JVM-B. All 36 cluster relations hold.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Unit: knob, format, rates, reads, junit counts re-read; control (b) failure confirmed in both JVMs. Cluster: read-back, workload, full size, compaction, yaml overrides re-read. |
| 2. Readings | yes | Rate spread recomputed from `per-sstable` lines; own_alloc vs own at every reading; the no-read own values and the RSS lines are INFO and not counted as relations. |
| 3. Matched row | yes | Unit: the frozen "control misses → Invalid" row is matched by observed readings; no other row decides first. Cluster: B3f (i)–(viii), B3h (a), (b) recomputed from raw samples (max after R1 over all later samples, not only the final). |
| 4. Excluded rows | yes | Every row of B2g/B3g, original and added, is addressed in §4.2 with a reading. |
| 5. Observed vs. inferred | yes | The unit explanations (meter first tick, untrimmed upsample buffer) and the cluster's counter-equals-allocation are labelled inferred. Neither verdict rests on them. |
| 6. Deviations and gaps | yes | H1 affected only an excerpt, and the self-check reads the full test log. |
| 7. Core question — the steps follow the audited logic | yes | read-back → workload → full size → R1 → settled size vs C → ratio → intervals → controls, in B3e's order; unit in B2e's order. |

### 5.2 Run 2?

**No** (decided 2026-10-25). The cluster verdict rests on observed readings that the self-check recomputed. The unit verdict follows mechanically from a frozen row and an observed reading. A run 2 of the same frozen design would meet the same control (b); a re-run needs a stage-3 amendment (section D).

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 7. Unit re-run ("run 1b") after the B2h (b), B2f (iv), (v)/(vi) amendment — 2026-10-25

Added by a stage-4 session, Claude Opus 5.5 (claude-opus-5-5), 2026-10-25, **authorised by the user (Yang, the advisor) on 2026-10-25**.
Sections 1–6 above are run 1 as filed and are not changed. Run 1's excerpts under `run1/` are untouched. The cluster tier is closed and
was not re-run.

### 7.1 Frozen version and harness

| Field | Content |
|---|---|
| **Why** | In unit run 1, control (b), (iv) in JVM-B and the interval relation of (v)/(vi) missed their frozen expectations because the read rates were 270 × apart per summary entry; the tier was Invalid (§4.2). The README says a wrong §9a "is a dated amendment to the case file and the affected tier starts again". The user authorised the amendment and a re-run of the whole unit tier on 2026-10-25. |
| **Amendment** | Six paragraphs `Amendment 2026-10-25 (after run 1, authorised by the user) — B2h (b), B2f (iv), B2f (v)/(vi) interval relation; here: …`, under B2c, B2d, B2e, B2f, B2g and B2h. Each says plainly that it follows run 1's readings.<br>**Option (a), from the source:** a workload that gives every own SSTable a comparable read rate per summary entry. `adjustSamplingLevels` gives SSTable i the space `remainingSpace × r_i / Σ r` (`IndexSummaryRedistribution.java:173, 182-183, 255`), so the redistribution is even, at one level for all, only when r_i ∝ maxEntries_i. Option (b), expectations restated in the recorded rates, would replay that method's arithmetic instead of testing B1's "≈ C, proportional".<br>**Why run 1's rates were unequal:** a new SSTable has an uninitialised meter (`SystemKeyspace.java:1531-1536`, `RestorableMeter.java:52-58`). Its first tick takes the interval's marks at full weight, and later ticks take them at α = 1 − e^(−5/900) = 0.00554 (`RestorableMeter.java:76-94, 175, 202-215`).<br>**Workload:** wait 6 s after the last flush, then one `fifteenMinuteRate()` call per own SSTable, which initialises it at 0. Then 100,000 reads of `key(100 p + 50)` in shuffled order. A read marks only the SSTable where the key is found (`BigTableReader.java:272, 345`, `SSTableReader.java:1904-1909, 1411-1415`, `SinglePartitionReadCommand.java:1361-1373`), so reads_i ∈ [n_i/100 ± 1].<br>**Relations:** (P) every init rate and count 0, `found` 100,000, max ρ / min ρ ≤ 1.10 (ρ = rate/maxEntries at S0), maxEntries ≥ 160. (iv) and control (b) keep their values (own = S0 exactly, every level 128). They are derived by induction over the visiting order: with H/S0 ≥ 0.2186, idealSpace_i ≥ (ρ_min/ρ_max)(1 + H/S0) F_i ≥ 44 (maxEntries_i + 17), which `calculateSamplingLevel` (`IndexSummaryBuilder.java:299-314`) needs for level 128. Interval: (a) as frozen, the mean within ±10 % of 128 × S0/own; (b) new, every level within 0.10 L̄ + 2 of L̄ = 128 × own/S0.<br>**What a redistribution after raising the pool must and need not restore:** it must restore every summary whose target reaches 1.5 × its current entries (`:235`). It need not restore one whose share falls short (`:247-253`).<br>**INFO, stated before the run:** an upsampled summary keeps the builder's untrimmed capacity, 76 × (maxEntries + 1) B at level 128 (`BigTableReader.java:433-436, 625-640`, `IndexSummary.java:216-219`, `IndexSummaryBuilder.java:42, 100-128`). So own_alloc ≠ own was expected at JVM-B C = 4 and at control (b), and the frozen own_alloc = own relation and its row were left unchanged, so that "Not confirmed for the real resource", not row 1, was the expected match if all else held.<br>B1, the cap relations that held, control (a), ConfigProbe and B3 are unchanged. |
| **What was known of run 1, and would run 1 pass** | All of run 1's unit readings were known when the amendment was written (k = 63, per-SSTable maxEntries, rates and levels, own and own_alloc at every reading, the 7 upsampled SSTables, the means 920 / 1,530). The own_alloc formula was checked against run 1's control (b) and reproduces its own_alloc exactly (825,588 / 811,104 B). A transcription of the method (`harness/<stem>/derivation-sim.py`) was run after the derivation as a check: no violations for spreads ≤ 1.15, violations from 1.20, and it reproduces run 1's own at C = 2 / 1 from run-1-like rates. No bound was taken from it. **Run 1 would not pass:** its ρ spread was 273 × / 271 × against 1.10, so it matches the amended "(P) fails → Invalid" row. Its interval (a) and (b), (iv) in JVM-B and control (b) also fail (`run1b-unit/selfcheck-known-answer-on-run1.out`: 21 failures under the amended relations). |
| **Case-file version** | sha256 **`40b91e735b5d5fafd4d3250bcb0cc23c86b0e1ae74dbe2ffea35f773d591b36a`**. It is a new row in `_INDEX.md` §4, "re-frozen after run 1 for unit re-run (B2h (b), B2f (iv), B2f (v)/(vi) interval relation), authorised by the user". The earlier rows (`a7147c5b…`, `6c8d37ff…`) are kept. Hashed at 17:05:48 EDT, before any re-run reading (first runner command 17:06:30). Section D was filled afterwards. Base commit `61322ed`; nothing committed. |
| **Harness** | Run 1's harness with change H2 (§3) only, i.e. the test's reads and logging, plus the new self-check (H3).<br>sha256 prefixes at the re-run: `IndexSummaryCapProbeTest.java` `fed35ea6` (run 1 `ea3b905c`), `unit-run.sh` `b3b5af4a` (unchanged since H1), `ConfigProbe.java` `f6243b52` (unchanged), `run1b-unit/selfcheck.py` `753fa56a` (new).<br>Command: `C=$W/cassandra-run19 P=$W/probe-isc2 L=$W/logs/index_summary_capacity-applySimpleConfig/unit-run2 unit-run.sh all`. This runs all five ConfigProbe processes, then JVM-A (auto) and JVM-B (`2MiB`) in the frozen order. |

### 7.2 Environment

Same host and storage as run 1 (§2). The unit tier ran 2026-10-25 17:06:30–17:10:00 EDT.

- **Clone:** fresh clone `$W/cassandra-run19` from `~/cassandra-src` at `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), no local change. `ant -Dlocal.repository=$W/m2 build-test` finished `BUILD SUCCESSFUL` in 52 s (`run1b-unit/clone-build-run19.txt`).
- **Disk:** 144 GiB free.
- **JVM:** `-Xms1024m`, `totalMemory` 1,056,309,248 B (auto = 50), as in run 1.
- **Before the run:** no `CassandraDaemon`.
- **After the run:** no `CassandraDaemon`, `ConfigProbe` or test JVM; ports 7000/7199/9042/9091 free; the clone is clean (`git status` 0 entries, probe test removed, `test/conf/cassandra.yaml` restored); `$C/build/test/cassandra` and `$W/probe-isc2` removed.
- **Full logs:** `$W/logs/index_summary_capacity-applySimpleConfig/unit-run2/` (`commands.log`, `summary.txt`, `stage4.out`, `p1-*.out`, `ant-*.log`, `TEST-*.xml`, `TEST-log-both-jvms.log` (copied from the clone's `build/test/logs/_jdk11/`), `ism-lines-*.txt`, yaml diffs). Also `unit-run2.out`, `unit-run2-build/` (clone and build log, instrument compile, known-answer self-check) and `selfcheck-unit-run2.out`.
- **Excerpts:** [`run1b-unit/`](index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous/run1b-unit/) (`unit/` with the same kinds of files as `run1/unit/`, plus `ism-lines-*.txt`; `selfcheck.py`; `selfcheck.out`; `selfcheck-known-answer-on-run1.out`; `clone-build-run19.txt`).

### 7.3 Readings

From `run1b-unit/unit/summary.txt`, `stage4.out`, `p1-*.line`, `TEST-*.xml` and `ism-lines-*.txt`. Both `ant testsome` runs returned rc 0 with `Tests run: 1, Failures: 0, Errors: 0`, 86 s each.

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| ConfigProbe `-1MiB` | `REJECT … Invalid data storage: -1MiB Accepted units:[MEBIBYTES, GIBIBYTES] where case matters and only non-negative values are accepted`; no line-872 message | `p1--1MiB.line` |
| ConfigProbe `0MiB` / `512KiB` / `1024KiB` / unset | `OK …=0` / `REJECT … Invalid data storage: 512KiB Accepted units` / the same for `1024KiB` / `OK …=51` | `p1-*.line` |
| Knob read-back | JVM-A knob 50 = formula on `totalMemory` 1,056,309,248, manager 50, format `big`; JVM-B knob 2, manager 2; log lines `memory pool size of 50 MB` / `2 MB`; resize interval 60 → −1 | `stage4.out`, `ism-lines-*.txt` |
| Load | 10,000,000 rows, 63 own SSTables in each JVM (21 per batch), 2 other BIG SSTables (35 B) | `stage4.out` (`batch`) |
| (P) meter init | 63 of 63 own meters: rate 0.0, count 0 (both JVMs) | `stage4.out` (`meter-init`) |
| (P) reads | 100,000 / 100,000 found; read phase 7.15 s (A), 6.75 s (B) | `stage4.out` (`reads`) |
| (P) rates at S0 | counts per SSTable 764–1,630 (A), 582–1,639 (B), Σ = 100,000, each within [(maxEntries − 1) × 1.28 − 1, maxEntries × 1.28 + 1]; rates 0.844–1.801 /s (A), 0.642–1.811 /s (B); **max ρ / min ρ = 1.0059 (A), 1.0058 (B)** (bound 1.10); smallest maxEntries 597 (A), 455 (B) (bound 160) | `stage4.out` (`per-sstable … tag=S0`) |

| Reading (own = Σ `getOffHeapSize()` of the 63 own summaries) | JVM-A total / own / own_alloc (B) | JVM-A levels; mean interval (pred.) | JVM-B total / own / own_alloc (B) | JVM-B levels; mean interval (pred.) | `downsample / upsample` (A; B) |
|---|---|---|---|---|---|
| S0 (pool = startup) | 3,439,867 / 3,439,832 = 44 × 78,178 / = own | 128; 128 | 3,439,603 / 3,439,568 = 44 × 78,172 / = own | 128; 128 | — |
| control (a): pool 1 MiB, 10 s, no redistribution | 3,439,867 / 3,439,832 / = own | 128 | 3,439,603 / 3,439,568 / = own | 128 | — |
| R0 at the startup value (50; 2 MiB) | 3,439,867 / 3,439,832 / = own | 128 | **2,096,943** / 2,096,908 / = own | 77–79; 210.0 (210.0) | 0/0; 63/0 |
| C = 4 MiB | 3,439,867 / 3,439,832 / = own | 128 | 3,439,603 / **3,439,568 = S0** / **5,945,860** | 128 (63 of 63) | 0/0; 0/63 |
| C = 2 MiB | **2,099,407** / 2,099,372 / = own | 77–79; 210.1 (209.7) | **2,096,943** / 2,096,908 / = own | 77–79; 210.0 (210.0) | 63/0; 63/0 |
| C = 1 MiB | **1,050,843** / 1,050,808 / = own | 38–40; 420.5 (419.0) | **1,048,335** / 1,048,300 / = own | 38–40; 420.3 (420.0) | 63/0; 63/0 |
| C = 0 | 216,251 / **216,216 = 44 × 4,914** / = own | 8; 2,048 | 215,107 / **215,072 = 44 × 4,888** / = own | 8; 2,048 | 63/0; 63/0 |
| control (b): C = 4 MiB after C = 0 | 3,439,867 / **3,439,832 = S0** / **5,946,316** | 128 (63 of 63) | 3,439,603 / **3,439,568 = S0** / **5,945,860** | 128 (63 of 63) | 0/63; 0/63 |

Bounds (B2f): C + 4,096 B = 2,101,248 B (C = 2) and 1,052,672 B (C = 1); lower bounds 1,887,437 B and 891,290 B. own(2)/own(1) = **1.9979** (A), **2.0003** (B). Interval (b): L̄ = 78.12 / 39.10 (A) and 78.03 / 39.01 (B); worst |L − L̄| 1.12 / 1.10 / 1.03 / 1.01 against bounds 9.81 / 5.91 / 9.80 / 5.90. **own_alloc after an upsample:** 5,946,316 = 76 × (78,178 + 63) and 5,945,860 = 76 × (78,172 + 63), exactly the amendment's INFO formula, **1.7287 ×** the counted size; after the next downsample own_alloc = own again.

### 7.4 Unit re-run — conclusion and logic

1. **Validity.**
   - The re-run used the re-frozen version (`40b91e73…`), hashed before the first command [observed: `_INDEX.md` §4; `run1b-unit/unit/commands.log` first line 17:06:30].
   - It ran every ConfigProbe process and both mechanism JVMs of B2 from the beginning in the frozen order, in a fresh clone [observed: `commands.log`: clone `cassandra-run19`, `b5f2a54210…`].
   - Read-back held: 50 = the auto formula, 2 for `2MiB` [observed: `stage4.out` `run` lines, `ism-lines-*.txt`].
   - Format BIG, every own SSTable `IndexSummarySupport` [observed: `notSupported=0`].
   - (P) held in both JVMs: meters initialised at 0, 100,000 found, ρ spread 1.006 ≤ 1.10, maxEntries ≥ 455 ≥ 160 [observed: `meter-init`, `reads`, `per-sstable … S0`].
   - The scheduled task was cancelled and compaction was off: the log shows one redistribution per explicit call, six per JVM [observed: `ism-lines-*.txt`, downsample/upsample counts].
   - The run is valid.
2. **Readings.**
   - With comparable rates the redistribution was even. At 2 and 1 MiB every own SSTable went to the same level ± 1 (77–79, 38–40), with the counted total 2,099,407 / 1,050,843 B (A) and 2,096,943 / 1,048,335 B (B), under C + 4,096 B and ≥ 0.999 C [observed].
   - Raising the pool to 4 MiB restored every summary to level 128, own = S0 exactly, both after R0 at 2 MiB (JVM-B) and after the zero pool (control (b), both JVMs) [observed].
   - The malloc'd memory of the 63 upsampled summaries was 76 × (Σ maxEntries + k) B, 1.729 × the counted size, exactly as derived from `BigTableReader.java:625-640` and `IndexSummaryBuilder.java:100-128` [observed: the numbers; inferred: the cause, from the source]. After the next downsample own_alloc = own again [observed: JVM-B C = 2].
3. **Matched row.** B2g added row "own_alloc ≠ own → the counter is not the real allocation; **Not confirmed for the real resource**" [observed: own_alloc ≠ own at JVM-B C = 4 and at control (b) in both JVMs; the frozen relation "own_alloc = own exactly at every reading" fails at 3 of 16 readings].
   - Row 1 ("claim holds") is excluded only by that relation. ConfigProbe as predicted.
   - (P), (i), (iii), (iv) in both JVMs, (v) and (vi) (bounds, interval (a) and (b)), (vii) and (viii) all hold.
   - Control (a) and the amended control (b) hold.
   - This is the outcome the amendment stated before the run.
4. **Excluded rows.**
   - "(P) fails → Invalid": (P) holds.
   - "a B2h control misses its expectation → Invalid": both controls hold.
   - "(P) holds and (iv) or interval (a)/(b) fails → Not confirmed (evenness)": all hold.
   - "total > C + 4,096 B → Refuted": the largest total is 1,841 B under C + 4,096 B at 2 MiB (2,099,407 B) and 1,829 B under it at 1 MiB (1,050,843 B).
   - "own stays ≈ S0 at C = 1 and 2": own fell to 0.61 / 0.31 S0.
   - "own < lower bound while ≤ C", "size < C/2": own ≥ 0.9997 C.
   - "C = 0.1 gives ≈ F" (now C = 0): holds exactly, 44 × Σ⌈maxEntries/16⌉.
   - Knob read-back, ConfigProbe failure, zero rate / format, S0 outside (i): not triggered.
   - KiB accepted: no.
5. **Observed vs. inferred.**
   - Inferred: the cause of own_alloc > own (the untrimmed builder buffer). The verdict rests on the observed sums, which match the source formula to the byte.
   - Inferred: that comparable rates caused the even levels. The levels and the ρ spread are both observed.
6. **Deviations and gaps.**
   - None against the re-frozen runbook.
   - As in run 1, own_alloc reads the malloc'd sizes, not resident memory (gap named at the audit).
7. **Core question.**
   - The startup value sets the pool.
   - A redistribution brings the counted off-heap total of the summaries to just under C: 2.099 / 1.051 MB at 2 / 1 MiB, ratio 2.00. Every SSTable shares the cut evenly (one sampling level ± 1, mean interval 210 / 420 = 128 × S0/own). The zero pool gives the floor exactly. Raising the pool restores the full summaries, and nothing changes without a redistribution.
   - So the constraint caps the **counted** size and the counted size follows it.
   - The real allocation does not follow it exactly: a summary rebuilt by upsampling holds 1.73 × its counted bytes (for 32-byte keys) until it is next downsampled. The cap is on what `getOffHeapSize()` counts, not on the malloc'd memory. That is why the frozen design's own row says Not confirmed for the real resource.

**Conclusion (one line):** B2g row "own_alloc ≠ own" → **Not confirmed (for the real resource)**. Effect: caps (the counted summary size, evenly and proportionally after each redistribution; upsampled summaries allocate 1.73 × what is counted).

### 7.5 Self-check of the unit re-run — AI

`run1b-unit/selfcheck.py <unit-run2> --relations amended` re-reads the raw `p1-*.out`, `stage4.out`, `TEST-*.xml` and `TEST-log-both-jvms.log`, not `summary.txt`. It recomputes ρ from the per-SSTable rates and maxEntries, and the mean interval and the level band from the per-SSTable levels, not from the harness's summary fields.

- **Pass 1 (re-run raw files, amended relations):** [`run1b-unit/selfcheck.out`](index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous/run1b-unit/selfcheck.out). **61 relations: 58 hold, 3 fail.** The 3 failures are exactly own_alloc = own at JVM-B C4 and at control (b) in both JVMs. The INFO lines confirm own_alloc = 76 × Σ⌊(maxEntries + 1) L/128⌋ = 76 × (Σ maxEntries + k) at each.
- **Pass 2 (known answer, run 1's raw unit files):** [`run1b-unit/selfcheck-known-answer-on-run1.out`](index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous/run1b-unit/selfcheck-known-answer-on-run1.out).
  - With `--relations run1`: 52 relations, 42 hold and 10 fail. The 10 are exactly run 1's 10 unit failures in §5.1: control (b) ×2, own_alloc at control (b) ×2, interval ×5, (iv) JVM-B.
  - With `--relations amended`: 61 relations, 40 hold and 21 fail, (P) among them (spread 273 × / 271 ×; no meter-init line; 10,000 reads). So the script tells run 1 apart from the re-run, and run 1 does not pass the amended relations.
- **Re-opened by hand:**
  - The two `meter-init` lines: 63 × `r=0.0c=0` each.
  - The `reads` lines: `found=100000`.
  - The `per-sstable … tag=C2` and `tag=C1` lines: levels 77/78/79 and 38/39/40 only.
  - The `controlB` reading lines: `own=3439832 ownAlloc=5946316` and `own=3439568 ownAlloc=5945860`, levels 128–128.
  - The unit log's `index summaries: downsample: …, upsample: …` lines: 63 per call, as in the table.
  - The two `TEST-*.xml` (`tests="1" failures="0" errors="0"`).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-frozen hash recorded before the run. Read-back, (P), format, call count re-read. |
| 2. Readings | yes | Totals, own, own_alloc, levels and ratios recomputed from raw lines. |
| 3. Matched row | yes | The only failing relation is own_alloc = own (3 readings), which selects the "own_alloc ≠ own" row. No Invalid or Refuted row applies. |
| 4. Excluded rows | yes | Every row of B2g, original and amended, checked against the raw values. |
| 5. Observed vs. inferred | yes | The cause of the allocation gap is labelled inferred; the verdict uses the observed sums. |
| 6. Deviations and gaps | yes | None; H2/H3 recorded; resident memory not measured (named). |
| 7. Core question | yes | Counted size capped and proportional, with even levels; real allocation 1.73 × after upsampling. |

**Run 2?** No, decided 2026-10-25. The verdict rests on direct readings that the independent script reproduces to the byte, including a source-derived allocation formula. A further run of the same frozen design would meet the same untrimmed buffers.

### 7.6 Verdict of the unit re-run

**Not confirmed — caps (counted size)** (B2g row "own_alloc ≠ own → Not confirmed for the real resource"). Filed in §8 as a new unit row; the run-1 unit row (Invalid) is kept.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive (soft, periodic).

**Claim tested (B1):** After a redistribution, the total index-summary off-heap size is ≤ max(C, F), where C is `index_summary_capacity` and F is the floor reached when every summary is at `max_index_interval`; when F < C ≤ full size, the total after redistribution is ≈ C (≤ C) and differs between two values of C proportionally. "Confirmed" means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Invalid**, B2g added row "a B2h control misses its expectation" (control (b): after C = 0, raising the pool to 4 MiB restored only the 7 hot SSTables; own 559,328 / 551,276 B, not S0 ≈ 3.44 MB). Also matched: "own_alloc ≠ own" (the summaries rebuilt by upsampling allocate 1.47–1.48 × their counted size). Every cap relation held: total ≤ C + 4,096 B at 2 and 1 MiB (2,080,091 / 1,034,651 B; at the startup value 2 MiB 2,064,603 B), ∝ C (2.01 / 2.05), the zero pool gave the floor exactly, and nothing changed without a redistribution. The interval relation failed (unequal read shares). `-1MiB`, `512KiB` and `1024KiB` are refused by the parser (the yaml's "Min unit: KiB" is wrong); `0MiB` → 0; auto → 51 / 50. | undetermined | run 1 + self-check | 2026-10-25 |
| Cluster | **Confirmed**, B3g row 1. After R1 (the MBean operation) and every later scheduled run: 2,093,412 / 8,379,692 B at 2 / 8 MiB (≤ C + 4,096 B; ratio 4.00), intervals ≈ 1,014 / 226 (predicted ≈ 1,003 / 251); auto 102 MiB left the full 16,406,460 B; with the schedule off (c2null), full size until R1, then 2,091,032 B. Transiently above C during writes, as filed. | caps (the counted off-heap summary size, after each redistribution; soft and periodic. The real allocation was not measured in this tier, and the unit tier shows that upsampled summaries allocate ≈ 1.5 × what is counted) | run 1 + self-check | 2026-10-25 |
| Unit (re-run at `40b91e73…`, after the user-authorised B2h (b), B2f (iv), (v)/(vi) amendment) | **Not confirmed**, B2g row "own_alloc ≠ own → Not confirmed for the real resource" (the match stated in the amendment before the run). Every other relation and both controls held in both JVMs: (P) ρ spread 1.006 (≤ 1.10), meters initialised at 0, 100,000 found; S0 = 44 × Σ maxEntries; total ≤ C + 4,096 B at 2 and 1 MiB (2,099,407 / 1,050,843 B in JVM-A; 2,096,943 at R0 and C = 2, 1,048,335 B in JVM-B), own ≥ 0.9997 C, ratio 2.00; every SSTable at one level ± 1 (77–79, 38–40), mean interval 210 / 420 = 128 × S0/own; zero pool = floor exactly; C = 4 after R0 (JVM-B) and control (b) restored all 63 summaries, own = S0 exactly; control (a) held. own_alloc after an upsample = 76 × (Σ maxEntries + k) = 5,946,316 / 5,945,860 B, 1.729 × own, as derived from the source (untrimmed builder buffer, `BigTableReader.java:625-640`) | caps (the counted off-heap summary size: ≤ C after each redistribution, proportional, evenly across SSTables under comparable read rates; not the malloc'd memory, which is 1.73 × the counted size for summaries rebuilt by upsampling until their next downsample) | unit re-run (§7) + self-check | 2026-10-25 |

**Feedback filed:** the case file's section D (uncommitted). No section of the case was amended after a reading. Recommendations for stage 3, not applied:
1. The yaml comment for `index_summary_capacity` says "Min unit: KiB", but the type is `LongMebibytesBound` and KiB values (even `1024KiB`) are refused (`DataStorageSpec.java:80, 84-88`). Observed.
2. A3 could state that each SSTable's share follows its 15-minute read rate, whose first 5-s tick decides how many early reads count. SSTables created just before a burst of reads get ≈ 1/α ≈ 180 × the share of older ones, so the downsampling is very uneven. A unit design should initialise every meter before the reads (one `fifteenMinuteRate()` call after more than 5 s), then read, then wait for a tick, or else predict per-SSTable levels.
3. A3 could state that with no reads the pool is not ignored: `distributeRemainingSpace` hands leftover pool back to SSTables slated for downsampling. The total stays ≤ C but does not drop to the floor.
4. A2/A4 could note that summaries rebuilt by upsampling (`BigTableReader.java:631-640`) keep the builder's untrimmed capacity, sized for 64-byte keys, so `getOffHeapSize()` (what the cap and every metric count) can understate the malloc'd memory: 1.47 × for 32-byte keys here. For long keys the buffer grows by doubling. The cap is on the counted size, not the allocation.
5. B2h(b) and B2f(iv) should expect upsampling only for SSTables whose target is ≥ 1.5 × their current entries, and the interval relation should be per SSTable or size-weighted.
6. B4 still names `/local` paths (superseded by the B4 amendment).

**End of run:** `pgrep -f CassandraDaemon` is empty and no ConfigProbe, stress or sampler process is left; ports 7000/7199/9042/9091 are free. `$W/node-isc` and `$W/probe-isc` are removed, as is `$C/build/test/cassandra`. The probe test is removed from `$W/cassandra-run14`, and its `test/conf/cassandra.yaml` is restored (`git status` clean). No `build/` or log folder exists in the repository root. Checked 2026-10-25 after the self-check.

**Feedback filed for the unit re-run (2026-10-25):** the six amendments `Amendment 2026-10-25 (after run 1, authorised by the user) — B2h (b), B2f (iv), B2f (v)/(vi) interval relation` in the case file (B2c, B2d, B2e, B2f, B2g, B2h); a new `_INDEX.md` §4 row (`40b91e73…`); the case file's section D (new entry); the §1 Stage 4 column (unit Not confirmed — caps (counted size) after the re-run; cluster Confirmed — caps). The §3 coverage line is unchanged, because the case was already counted as closed. No refutation, so no other case section is amended. Recommendations 2 and 5 above were applied in this form, authorised by the user. Recommendation 4 stands, now with the exact formula: a summary rebuilt by upsampling allocates 76 × (maxEntries + 1) B at level 128 against 44 × maxEntries counted.

**Processes (unit re-run):** no `CassandraDaemon` before or after; no `ConfigProbe` or test JVM left (`run1b-unit/unit/commands.log`: `no ConfigProbe left`); ports 7000/7199/9042/9091 free; clone `cassandra-run19` clean (`git status` 0 entries) after the runner restored its test yaml and removed the probe test; `$C/build/test/cassandra` and `$W/probe-isc2` removed; no `build/` or log folder in the repository root. Re-checked at the end of the session.
