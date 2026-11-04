# bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous — stage-4 results  <!-- file: results/bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous.md -->

> **Case:** [`bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous`](../../stage3-ai-deep-read/cases/bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous.md)
>
> **Status:** verdict filed (2026-10-27). **Unit: Refuted — caps** (run 1; closed, not re-run). **Cluster: Refuted — caps** (cluster re-run
> "run 1b" of 2026-10-27 at the re-frozen version `c8b73fda…7006`, after the user-authorised amendment of C6 I1 and I3; run 1's cluster verdict,
> Invalid — undetermined (C6 I1, I3), is kept in §4 and §8 unchanged). The re-run is §7.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/`](../harness/bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/).
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster) as amended; "§9b–§9e" means B2a–B2e / B3a–B3e;
> the feedback section is the case file's section D.
>
> **Session:** Claude Opus 5.5 (`claude-opus-5-5`), Claude Code CLI, 2026-10-27, on the advisor's Mac (`environment-advisor.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | filed with sha256 `5f694732…` (as filed, 2026-10-26, commit `8b7d953`); the ten audit amendments of 2026-10-27 (U1–U4, C1–C6) are uncommitted in the working tree. Frozen sha256 after the amendments: **`8bc80c3842e0e4dcd621a27ca5dc8e10ddec1a126856aea9d0f04a6e8ffe11f7`** (new row in `_INDEX.md` §4). An intermediate hash `559c963b…` was written to that row first and replaced before any harness ran: C5/C6 were corrected (Lbf compared as a difference from B0 with a 64 KiB allowance and a per-rewrite `BMBF BA` line, because Lbf also counts other tables' filters), a reading-independent fix. Both tiers of run 1 ran at the frozen version; section D was filled after this hash. |
| **Harness** | `harness/bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/` (uncommitted): `BloomFpChanceMemoryTest.java` (B2's test, U2's lines), `unit-run.sh`, `bf.btm` (C3 (4) observe-only Byteman rules), `make-node-conf.sh`, `cluster-run.sh`; `selfcheck.py` under `results/<stem>/run1/`. `unit-run.sh` and `make-node-conf.sh` are adapted by sed of names from the harness folder of `bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous`, and `cluster-run.sh`'s node mechanics (timeouts, start/stop, final check, wait-up) from that folder's `cluster-run.sh`; the workload, samples, Byteman rules, self-check and every expected value are new. Every number here was derived from the pinned source; none was taken from another case or results file. |
| **Tiers and values** | Unit: fp ∈ {1.0, 0.5, 0.393, 0.2, 0.1, 0.01, 0.001, 0.0001, 0.0000672, 0.0000671} at N = 1 000 000 and 2 000 000 (two repetitions), M = 1 000 000 absent keys; `computeBloomSpec(20, fp)` for the same values plus 0.00006. Cluster: one node, 10 M partitions, fp ∈ {1.0, 0.5, 0.1, 0.01, 0.001, 0.0001} by ALTER + `upgradesstables -a`, 0.00006 attempted, control 20 M partitions at 0.01. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: off-heap bit-set bytes of each sstable's filter and the same bytes in `Filter.db`. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b 10 values, B3b 6 values, both including the default 0.01. |
| A. Core question | real resource measured, not only the counter | Partly → Met | B2d names the gap (offHeapSize is the malloc size). B3d's real-memory instrument is NMT "Other/Internal", which cannot see the filter: `OffHeapBitSet.java:47` → `Memory.java:65` → `MemoryUtil.java:81-84` is JNA `Native.malloc`, not `Unsafe`. C3 keeps NMT for information and adds observe-only Byteman rules on `MemoryUtil.allocate/free` and `OffHeapBitSet` (Lmal, Lbf); `vmmap` cannot attach here and RSS does not fall on free (known-answer check below), so the OS view is a named gap. |
| A. Core question | usage driven to the limit and past it | Met | Floor (0.5 / 0.393), ceiling (0.0000672 / 0.0000671), a value below the minimum (0.0000671 in B2; 0.00006 in B3 and, by U2, in B2). |
| B. Logic | each step says what it establishes | Met | B2h/B3h. |
| B. Logic | prediction stated in numbers | Partly → Met | B2f exact; "within sampling error" and "record it" made exact by U3 (3σ bound; serialized = offheap + 8). B3f had exact bands; C5 names N_est and replaces the NMT sentence's instrument, keeping its ±2 MB. |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met | B2g/B3g had no verdict words, order, Invalid or no-row-fits rows, and B3g's ">5% deviation" row only named an estimate overshoot; U4/C6 add them and a row (R4) for a deviation at some fp values only. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met | B2 relied on 0.0000671 throwing; U2 adds `computeBloomSpec(20, 0.00006)` so the line-151 throw is tested directly; B3 has the 0.00006 refusal. |
| B. Logic | alternative explanations and their controls | Met | fp = 1.0 zero baseline, N doubling, repeat; one sstable, same data, 2× keys control, sstable generation (C3 (2)). |
| C. Specific | a human can follow it from the intro and §9a | Met | |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met | U2 fixes keys, order and line format; C2/C4 the sample points. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | idle condition, sample contents, CTRL's ALTER back to 0.01 (C4 (6)). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met | `/local`, Linux, `-p` pid file, `jvm-server.options` edits: replaced by this host's paths (U1, C1). |
| D. Runnable | workload arithmetic reaches the limit | Met | 10 M × ~60 B ≈ 0.6 GB data, 20 M at CTRL; filters ≤ 25 MB; 2 GiB heap; 119 GiB free. |
| D. Runnable | load-bearing citations spot-checked | Met, with two findings | `BloomCalculations.java:43-66, 140-172, 180-198`, `FilterFactory.java:35, 60-75, 110-120`, `OffHeapBitSet.java:39-53, 63-71, 139-142`, `BloomFilterSerializer.java:65-70`, `TableParams.java:156-167`, `CompactionParams.java:261-264`, `SortedTableWriter.java:445`, `Upgrader.java:67-79`, `SSTableReader.java:302-332`, `TableMetrics.java:537-548`, `MemoryUtil.java:81-89` hold at the pinned clone. Findings S1, S2 below. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| U1 | This host's clone `$W/cassandra-run58`, harness test, `-Dlocal.repository`, shakedown | applied 2026-10-27 (uncommitted) | no `/local` here |
| U2 | Exact keys, order, line format; `computeBloomSpec(20, 0.00006)` added; no assertions | applied | runnable without re-deriving; direct test of line 151 |
| U3 | serialized = offheap + 8; 3σ FP bound; exact BFSPEC texts | applied | prediction in numbers |
| U4 | B2g verdict rows (I, R1–R4, C, N) and the Effect rule | applied | every outcome has a row |
| C1 | macOS node set-up (`$W/node-bfcs`, tracked `bin/cassandra -f`, `JVM_EXTRA_OPTS`), stop and wipe | applied | this host |
| C2 | exact load, idle condition, read-backs | applied | exact sampling |
| C3 | `stat -f %z`, generation, sstablemetadata; NMT information only; Byteman Lmal/Lbf as the real-memory instrument | applied | NMT cannot see JNA malloc |
| C4 | exact order LOAD, B0, F<fp>, REJ, CTRL | applied | exact procedure |
| C5 | N_est named, ±5% applied per value, NMT sentence's instrument replaced (±2 MB kept) | applied | prediction in numbers |
| C6 | B3g verdict rows (I1–I3, R1–R4, N1, C, N0) and the Effect rule | applied | every outcome has a row |
| S1 | **For stage 3 (claim):** line 149 (the body of the line-147 `if`) is `return new BloomSpecification(2, optKPerBuckets[2]);` and the constructor is `(int k, int bucketsPerElement)` (`BloomCalculations.java:114`), so the floor is **K = 2 and 1 bit per key** (`optKPerBuckets[2]` = 1), not 2 bits and K = 1 as B1/B2f/B3f state. Source-derived expectation: offheap 125 008 / 250 008 at N = 1 M / 2 M, and an FP rate near (1 − e^(−2))^2 ≈ 0.75, above fp = 0.5. | left for stage 3; predictions not changed | it changes B1's claim; the run decides |
| S2 | **For stage 3 (claim):** line 151 throws only when `maxFalsePosProb < probs[20][14]`; 0.0000671 *is* `probs[20][14]` (6.71e-05, the same double), so it does **not** throw and returns bpe 20, K 14. The minimum is rejected by schema validation (`TableParams.java:161`, `<=`), not by `computeBloomSpec`. | left for stage 3; predictions not changed (U2 adds 0.00006 so the throw is still tested) | it changes B2f's 0.0000671 row |
| S3 | For stage 3: A3/B3d say NMT's Other/Internal holds the filter's Unsafe allocations; the filter is JNA `Native.malloc`, which NMT does not track | applied as C3 for the run; left for stage 3 as a text fix | instrument mis-trace |

**Instrument checks before run 1.** (a) `bf.btm` type-checked with Byteman `TestScript` against the clone's classes: "TestScript: no errors" (4 rules). (b) Known-answer for the OS view (`$W/tools-bfcs/MallocKA.java`, 2026-10-27): `vmmap -summary <pid>` on a JVM: "cannot examine process … try running with sudo"; a 25 000 008-byte JNA malloc that is written raises RSS by ~29 MiB and RSS stays there after `Native.free`, so neither can read freed native memory on this Mac. (c) Cluster shakedown (N = 200 000): each rewrite at fp < 1.0 printed a `BMBF BA` equal to tablestats off-heap exactly, ΔLmal matched Δtablestats within 74 B, and NMT Other moved by ≤ 183 KB while the filter moved by up to 249 KB (`run1/shake/selfcheck-cluster-shake.out`). (d) Unit compile (`unit-compile`) and shakedown, after which the test was changed to initialise logging first (its first lines had gone to ant's output; harness only).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit 08:04:33–08:04:53; cluster 08:13:01–08:22:45 local time, EDT; node logs in UTC) |
| Node | `yangwang-mbp`, the advisor's laptop, single host (Apple T6000, 10 cores, 32 GiB) |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 |
| JDK | OpenJDK 11.0.32.1 (Homebrew); `jcmd` in its `bin/` |
| Ant | 1.10.18 |
| Python | 3.8.11 (`bin/cqlsh`, `selfcheck.py`) |
| Local clone commit | `$W/cassandra-run58` (`W=~/Library/Caches/stage4`), fresh clone of `cassandra-5.0.9`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`; `ant -Dlocal.repository=$W/m2 build-test` succeeded in 51 s; `git status` clean after the run |
| Case-file commit / harness commit | uncommitted amendments on top of `8b7d953` (frozen sha256 `8bc80c38…`) / harness uncommitted |
| Storage for node data | internal SSD, APFS, 119 GiB free; node files `$W/node-bfcs`, fresh, removed at the end |
| Loopback / ports | 127.0.0.1–.3 on `lo0` (only .1 used); 7000, 7199, 9042, 9091 free before the run |
| Full logs | `$W/logs/bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/` (`clone.log`, `build-test.log`, `unit-compile/`, `unit-shake/`, `unit-r1/`, `cluster-shake/`, `cluster-r1/` incl. `node/node.out` with the Byteman lines and `node/system.log`) |

Machine facts relied on (from earlier runs on this Mac): workspace `$W` only, no `mkdir` in `$HOME` outside it; commands touching `$W`/Java run
unsandboxed; `-Dlocal.repository=$W/m2` on every `ant` call; no `setsid` (node started as a tracked background `bin/cassandra -f > log 2>&1 < /dev/null`);
BSD `stat -f %z` instead of `du -b`; `auto_snapshot: false` so rewrites leave no snapshots; `cassandra-env.sh` ignores `HEAP_NEWSIZE` under G1 (logged);
test stdout lands in `build/test/logs/**/TEST-<class>.log` (here only after logging starts — the shakedown finding); a constant is varied only by
patching or Byteman (not needed: the knob is settable); the Byteman rule type-checked with `TestScript` before use; `JVM_EXTRA_OPTS` scoped to the node
command; daemon class name kept out of `pkill` patterns; node `system.log` timestamps in UTC; long steps in the background and polled; shakedown
before run 1; `selfcheck.py` written before run 1 and run end to end on both shakedowns (exit status 0 checked); macOS RSS does not track freed
native memory (re-checked here for JNA malloc).

## 3. Runbook defects

None in the frozen runbook. Two harness faults were fixed during the shakedowns, before any run-1 reading (not runbook defects: the
case-file steps were unchanged): the unit test's first lines were printed before logging started and went to ant's output (logging is now
initialised first), and the idle wait parsed `compactionstats` with a colon that 5.0.9 does not print (`pending tasks  0`).

Re-freeze after run 1 (R1, a case-file amendment authorised by the user) and harness changes for the cluster re-run (added 2026-10-27 by the
cluster re-run session):

| # | Found in | Section | Problem | Fix | Who / date | Case-file version after |
|---|---|---|---|---|---|---|
| R1 | cluster run 1 (reading, not a runbook defect) | B3g C6 I1 and I3 | The tier was Invalid only because C6 required `totalRows` = 10 000 000 after the load and 20 000 000 at CTRL; the sstable held 9 999 195 and 19 997 026 with 0 stress errors (§4.2). C6 had assumed that n stress writes give n distinct partitions. | **Re-freeze, authorised by the user (Yang, the advisor) on 2026-10-27:** one dated amendment `Amendment 2026-10-27 (after run 1, authorised by the user) — B3g C6 I1 and I3`: the expected `totalRows` is the number of distinct keys the legacy stress write produces, which the stress source determines exactly (seeds i·(10^16+1) for i in seq, one 10-character key per seed from a reseeded java.util.Random): E(1..10 M) = 9 999 195, E(1..20 M) = 19 997 026, tolerance zero; I1 also requires stress `Total partitions` = N. New sha256 `c8b73fda…7006`, a new row in `_INDEX.md` §4. The whole cluster tier re-run from its beginning in a fresh clone (§7). B1, the size relations (C5), the other C6 rows and the unit tier unchanged. | user, 2026-10-27 | sha256 `c8b73fda…7006` (uncommitted; no commit asked for) |
| H1 | cluster re-run | B3a / C1 (fresh clone) | `cluster-run.sh` and `make-node-conf.sh` hard-coded run 1's clone `$W/cassandra-run58`. | One line each: `C=${C:-$W/cassandra-run58}` (and `export C` in `cluster-run.sh` so `make-node-conf.sh` sees it); the re-run used `C=$W/cassandra-run69`. Nothing else changed; `bf.btm` unchanged (sha256 prefix `76780bc5`, as in run 1). | AI, 2026-10-27 | n/a (harness) |
| H2 | cluster re-run | C6 I1/I3 amended | The amendment needs the distinct-key count of the stress seeds. | New `harness/<stem>/StressKeyCount.java`: runs stress's own `HexBytes`/`GeneratorConfig`/`OptionDistribution` classes from the run clone, outside any node, over the seeds `SeedManager` issues, and counts distinct keys (a sort, cross-checked with a `HashSet` up to 1 M keys; a known-answer self-test of the count). A first version decoded the key characters wrongly (it assumed `A`–`F`; `HexBytes.java:49-50` writes `K`–`P`) and printed other counts; the key strings it printed showed the error, it was fixed on the source's key format, and both outputs are kept (`run1b-cluster/stress-key-count-v0-encoding-bug.txt`, `run1b-cluster/stress-key-count.txt`). | AI, 2026-10-27 | n/a (harness) |
| H3 | cluster re-run | self-check | `run1/selfcheck.py` checks run 1's I1/I3. | `run1b-cluster/selfcheck.py` copies it and adds `--relations run1|amended` (default amended: I1/I3 with E and stress `Total partitions` = N); under `--relations run1` its output on run 1's raw files equals `run1/selfcheck-cluster.out` line for line after its one-line header. `run1/selfcheck.py` is unchanged. | AI, 2026-10-27 | n/a (harness) |

## 4. Run 1

**Scope:** unit tier as frozen (B2b's 10 values × N = 1 M, 2 M × 2 repetitions, plus the 11 `BFSPEC` lines); cluster tier as frozen
(LOAD, B0, six F<fp> samples, REJ, CTRL). **Command logs:** `run1/unit/commands.log`, `run1/cluster/commands.log`; summaries
`run1/unit/summary.txt`, `run1/cluster/summary.txt`; raw test lines `run1/unit/stdout.txt`; per-sample excerpts `run1/cluster/<sample>/`;
the Byteman lines `run1/cluster/node-out.txt`.

### 4.1 Readings

**Unit tier** (`run1/unit/stdout.txt`; rep 1 and rep 2 identical in every cell)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Line count | 11 `BFSPEC`, 40 `BFP`, `END bfspec=11 bfp=40`; ant `Tests run: 1, Failures: 0, Errors: 0` | `run1/unit/stdout.txt`, `run1/unit/ant-summary.txt` |
| fp = 1.0 | `AlwaysPresentFilter`, offheap 0, serialized 0, fpcount 1 000 000 (= M) at both N — as B2f | stdout.txt |
| fp = 0.5 and 0.393 (floor) | `BFSPEC bpe=1 K=2` for both; `BFP` K = 2, offheap **125 008** (N = 1 M) / **250 008** (N = 2 M), serialized +8; fpcount **747 347** / **748 426** (rate 0.747), bound 501 500 (0.5) / 394 465 (0.393). Predicted bpk 2, K 1, 250 008 / 500 008, rate ≤ fp | stdout.txt |
| fp = 0.2 | bpe 4, K 2, 500 008 / 1 000 008, fpcount 154 882 / 154 886 (bound 201 200) — as B2f | stdout.txt |
| fp = 0.1 | bpe 5, K 3, 625 008 / 1 250 008, fpcount 91 983 / 91 856 (bound 100 900) — as B2f | stdout.txt |
| fp = 0.01 | bpe 10, K 5, 1 250 008 / 2 500 008, fpcount 9 375 / 9 329 (bound 10 299) — as B2f | stdout.txt |
| fp = 0.001 | bpe 15, K 7, 1 875 008 / 3 750 008, fpcount 1 029 / 1 007 (bound 1 095) — as B2f | stdout.txt |
| fp = 0.0001 | bpe 20, K 10, 2 500 008 / 5 000 008, fpcount 88 / 77 (bound 130) — as B2f | stdout.txt |
| fp = 0.0000672 | bpe 20, K 14, 2 500 008 / 5 000 008, fpcount 66 / 76 (bound 91.8) — as B2f | stdout.txt |
| fp = 0.0000671 | **`BFSPEC fp=6.71E-5 bpe=20 K=14`**, `BFP` builds a 20-bit filter (2 500 008 / 5 000 008, K 14) — predicted to throw at line 151 | stdout.txt |
| fp = 0.00006 (U2) | `THROWS java.lang.UnsupportedOperationException: Unable to satisfy 6.0E-5 with 20 buckets per element` — as U3 (c) | stdout.txt |
| serialized − offheap | 8 for every fp < 1.0, 0 at fp = 1.0 — as U3 (a) | stdout.txt |
| Doubling | offheap(2 M) − 8 = 2·(offheap(1 M) − 8) at every fp < 1.0 | stdout.txt |

**Cluster tier** (N_est = 9 901 570 for LOAD … F0.0001, 19 923 827 at CTRL; one sstable at every sample)

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| load | LOAD | stress / sstablemetadata | stress `Total partitions : 10,000,000`, `Total errors : 0`; **`totalRows: 9999195`**, estimated cardinality 9 901 570 | `run1/cluster/stress-LOAD-excerpt.txt`, `run1/cluster/LOAD/sstablemetadata-excerpt.txt` |
| 0.01 (default, baseline) | B0 | tablestats off-heap / Filter.db | 12 376 968 / 12 376 976 (F = 12 376 968); `nb-38` | `run1/cluster/B0/` |
| 1.0 | F1.0 | off-heap / Filter.db / gen. | 0 / no file / `nb-39`; ΔLmal −12 377 005 vs Δtablestats −12 376 968; no `BMBF BA` of filter size | `run1/cluster/F1.0/`, node-out.txt |
| 0.5 | F0.5 | off-heap / Filter.db / gen. | **1 237 704** / 1 237 712 / `nb-40`; F(bpk 2) = 2 475 400 → −50.0%; ΔLmal −11 139 338 vs −11 139 264; `BMBF BA 1237704` | `run1/cluster/F0.5/`, node-out.txt |
| 0.1 | F0.1 | same | 6 188 488 / 6 188 496 / `nb-41`; F = 6 188 488 (0.000%); ΔLmal = Δtablestats exactly; BA 6 188 488 | `run1/cluster/F0.1/` |
| 0.01 | F0.01 | same | 12 376 968 / 12 376 976 / `nb-42`; F exact; ΔLmal −37 vs 0; BA 12 376 968 | `run1/cluster/F0.01/` |
| 0.001 | F0.001 | same | 18 565 448 / 18 565 456 / `nb-43`; F exact; ΔLmal 6 188 406 vs 6 188 480; BA 18 565 448 | `run1/cluster/F0.001/` |
| 0.0001 | F0.0001 | same | 24 753 928 / 24 753 936 / `nb-44`; F exact; ΔLmal = Δtablestats exactly; BA 24 753 928 | `run1/cluster/F0.0001/` |
| 0.00006 | REJ | cqlsh exit / text / read-back | exit 2, `ConfigurationException: bloom_filter_fp_chance must be larger than 6.71E-5 and less than or equal to 1.0 (got 6.0E-5)`; read-back 0.0001 | `run1/cluster/alter-REJ.txt`, `readback-REJ.txt` |
| 0.01, 2× keys | CTRL | off-heap / Filter.db / rows | 24 904 792 / 24 904 800 (F at 19 923 827 = 24 904 792, exact; 2.012 × F0.01); stress 10 M more, 0 errors; **`totalRows: 19997026`** | `run1/cluster/CTRL/`, `stress-CTRL-excerpt.txt` |
| all | all | NMT `Other` diff from B0 | +10 KB … +57 KB while the filter moved by up to −12.4 MB / +12.4 MB (information only, C3 (3)) | `run1/cluster/<sample>/nmt-diff-head.txt` |
| all | all | Byteman bookkeeping | 1 819 `BMBF` lines, no unmatched free, no duplicate address, no malformed line; 0 `ERROR` lines in system.log | `run1/selfcheck-cluster.out`, `run1/cluster/error-count.txt` |

### 4.2 Conclusion and logic

**Unit tier.**

1. **Validity** — valid: all 11 + 40 lines and `END` are present and rep 1 = rep 2 in every cell [observed: `run1/unit/stdout.txt`]; U4 row I does not hold.
2. **Readings** — the floor cells and 0.0000671 differ from B2f; every interior value (0.2 … 0.0000672) matches B2f exactly in bytes, K and
   serialized size [observed: `stdout.txt`].
3. **Matched row** — **Refuted (R1, R3, R4)**. R1 (filed row 2, "bytes differ from formula"): 0.5 and 0.393 give 125 008 / 250 008, not
   250 008 / 500 008; R3 (filed row 4, "0.0000671 does not throw"): `BFSPEC fp=6.71E-5 bpe=20 K=14`; R4 (filed row 5, "FP rate >> fp"):
   fpcount 747 347 against bounds 501 500 (0.5) and 394 465 (0.393) [observed: `stdout.txt`]. The floor is 1 bit per key with K = 2, which is
   what S1 derived from line 149 before the run [inferred: source, `BloomCalculations.java:149, 114`]; the FP rate 0.747 equals
   (1 − e^(−2))² = 0.748 for 1 bit/key and K = 2 [inferred: arithmetic].
4. **Excluded rows** — I: excluded by (1). R2 (0.393 and 0.5 differ): the two are identical at both N [observed]. C: excluded by R1, R3, R4.
   N: not reached (a Refuted row holds).
5. **Observed vs. inferred** — the verdict rests on observed lines only; the inferred statements explain the cause (the constructor-argument
   order at line 149 and `<` at line 151) and are not needed for the row.
6. **Deviations and gaps** — none from the frozen runbook. The unit tier sees the requested malloc size (`offHeapSize`), not the OS view (B2d).
7. **Core question** — usage follows the knob: offheap is a non-increasing step function of fp, constant at 1 bit/key for every fp ≥ 0.393
   (the line-147 floor), largest and constant at 20 bits/key for fp ≤ 0.0001 down to 6.71e-05, and `computeBloomSpec` refuses 6.0e-05 (line 151)
   [parts 2–3]. So the knob caps bytes per key between a floor and a ceiling (Effect **caps**), but B1's claim is wrong in two places: the floor
   is 1 bit/key (K = 2), not 2 bits (K = 1), with an FP rate of 0.75 above the requested 0.5 or 0.393, and line 151 does not reject 6.71e-05
   itself (schema validation's `<=` does).

**Conclusion (one line):** B2g filed rows 2, 4, 5 (U4 R1, R3, R4) — **refuted** (Effect: caps).

**Cluster tier.**

1. **Validity** — **not valid by the frozen rule.** C6 I1 requires `totalRows` = 10 000 000 after the load; the sstable holds 9 999 195
   rows although stress wrote 10 000 000 partitions with 0 errors [observed: `LOAD/sstablemetadata-excerpt.txt`, `stress-LOAD-excerpt.txt`].
   I3 also holds: CTRL `totalRows` 19 997 026 ≠ 20 000 000 [observed: `CTRL/sstablemetadata-excerpt.txt`]. Every other validity condition
   held: N_est within ±5% of 10 M (−0.98%), stress errors 0, one sstable at every sample, a new generation at every rewrite (I2 not holding)
   [observed: `selfcheck-cluster.out`]. The shortfall is duplicate keys from stress itself: the legacy write's partition key is `HexBytes` of a
   pseudo-random value from `uniform(1..100B)` (`SettingsCommandPreDefined.java:79-81`, `HexBytes.java:39-53`, `Generator.java:59-62`), so distinct
   sequence numbers can map to the same 10-character key; the doubling of the load quadruples the shortfall (805 → 2 974; 4 × 805 = 3 220), the
   birthday pattern [inferred: source and arithmetic]. The audit's I1/I3 assumed distinct keys; that assumption, not the node, failed. **The
   conclusion is "invalid run".**
2. **Readings (information only, not a verdict)** — had the run been valid: F0.1 … F0.0001 equal F(fp) at N_est to the byte and Filter.db =
   off-heap + 8; F1.0 is 0 with no file; F0.5 is −50.0% from F (1 bit per key, as the unit tier and S1); ΔLmal tracks Δtablestats within 74 B and
   each rewrite's `BMBF BA` equals tablestats' figure; 0.00006 is refused with the C5 text and the value stays 0.0001; CTRL = F at 19.9 M to the
   byte (2.012 × F0.01). Under C6 these would match R4 (the 0.5 value only deviates), i.e. "Refuted (R4) — caps" [observed: `selfcheck-cluster.out`].
3. **Matched row** — **I1 (and I3), Invalid.**
4. **Excluded rows** — not evaluated for the verdict (Invalid is checked first, C6).
5. **Observed vs. inferred** — the Invalid verdict rests on observed `totalRows`; the stress-duplicate explanation is inferred.
6. **Deviations and gaps** — none from the runbook. NMT did not see the filter (expected, C3 (3)); the OS view of malloc'd bytes is a named gap.
7. **Core question** — not answered by this tier's verdict (invalid run). The readings in part 2 show the same picture as the unit tier, but they
   cannot carry a verdict without a re-run at a re-frozen version.

**Conclusion (one line):** C6 I1, I3 — **invalid run** (Effect: undetermined).

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (written before run 1, run end to end on both shakedowns with exit status 0: `run1/shake/selfcheck-unit-shake.out`,
`run1/shake/selfcheck-cluster-shake.out`) re-read the raw files (`unit-r1/TEST-*.log`; `cluster-r1/<sample>/*.txt`, `stress-*.txt`,
`alter-REJ.txt`, `readback-REJ.txt`, `node/node.out` up to each sample's offset), never `summary.txt`. Output: `run1/selfcheck-unit.out`
(exit 0, `UNIT VERDICT: Refuted (R1, R3, R4) — caps`), `run1/selfcheck-cluster.out` (exit 0, `CLUSTER VERDICT: Invalid (I1, I3) — caps`;
the script's Effect is mechanical — for an Invalid tier the filed Effect is `undetermined`). Totals: unit 40 BFP + 11 BFSPEC lines checked,
4 R1 cells, 1 R3 line, 4 R4 cells, 0 rep differences; cluster 9 samples checked, I1 1 condition, I3 1 condition, R4 1 value, R1/R2/R3 0,
1 819 Byteman lines with 0 anomalies. I also re-read by hand `LOAD/` and `CTRL/sstablemetadata.txt` (totalRows), `F0.5/` and `F0.0001/tablestats.txt`,
both stress files and `alter-REJ.txt` in the full logs.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | unit: 53 lines, reps equal (`selfcheck-unit.out` "U-I holds: False"); cluster: `totalRows: 9999195` and `19997026` re-read in the full sstablemetadata files — I1/I3 hold as stated |
| 2. Readings | yes | every number in §4.1 re-read in `stdout.txt` and the sample files; the 3σ bounds recomputed by the script |
| 3. Matched row | yes | unit R1/R3/R4 as the script finds; R2 does not hold; cluster I1/I3 first in C6's order |
| 4. Excluded rows | yes | unit I, R2, C, N excluded as stated; cluster rows after Invalid are reported as information only |
| 5. Observed vs. inferred | yes | the two verdicts use observed values only; the floor cause (line 149) and the stress-duplicate cause are marked inferred |
| 6. Deviations and gaps | yes | no runbook deviation; harness fixes were before run 1 (§3); NMT blind as predicted by C3 |
| 7. Core question | yes | the unit tier answers it (caps per key, floor and ceiling, claim's floor and line-151 boundary wrong); the cluster tier does not, by rule |

### 5.2 Run 2?

**No** (2026-10-27). The unit tier is deterministic and exact (rep 1 = rep 2), and its refutation rests on observed bytes that S1/S2 derived
from source before the run. The cluster tier needs a re-run at a re-frozen version, not a run 2: C6 I1/I3 would have to accept the distinct
row count stress actually produces (for example `totalRows` within 0.1% of the stress count, or keys from a generator without duplicates).
Changing that after this reading needs the user's authorisation (README, "Predictions are not tuned to data").

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Cluster re-run ("run 1b") after the C6 I1/I3 amendment — 2026-10-27

Run 1's sections above are unchanged; run 1's cluster verdict (Invalid — undetermined, C6 I1, I3) stays the result at `8bc80c38…`. Run 1's
excerpts under `run1/` are untouched. The unit tier is closed and was not re-run. Excerpts of the re-run:
[`run1b-cluster/`](bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/run1b-cluster/).

### 7.1 Frozen version and harness

| Field | Content |
|---|---|
| **Why** | Run 1's cluster tier was Invalid under C6 I1 and I3 only: `totalRows` 9 999 195 after the load and 19 997 026 at CTRL against the exact 10 000 000 / 20 000 000 C6 required, with 0 stress errors and every other validity condition holding (§4.2). The README says a wrong §9a "is a dated amendment to the case file and the affected tier starts again". The user authorised an amendment of I1/I3 and a re-run of the whole cluster tier on 2026-10-27. |
| **Amendment** | One dated amendment `Amendment 2026-10-27 (after run 1, authorised by the user) — B3g C6 I1 and I3`, next to C6; it says plainly that it follows run 1's readings. **Choice:** option (a), the expected number of distinct keys, because the stress source determines it exactly; option (b) (measured `totalRows` as N within a fraction of n) would need a fraction the source does not supply, and the size relations (C5) already take N_est from each sample. **Source derivation** (`tools/stress/src/org/apache/cassandra/stress/`): partition key `HexBytes("key", GeneratorConfig("randomstrkey", null, fixed(10), null))` (`settings/SettingsCommandPreDefined.java:77-82, 108`), identity distribution `uniform(1..100B)` (`generate/values/Generator.java:59-62`; `OptionDistribution.java:181-196, 489-502`, `DistributionBoundApache.java:40-59`), reseeded per partition with `seed ^ salt` (`Generator.java:51-55`, `GeneratorConfig.java:39-48`), 10 characters from one draw (`HexBytes.java:39-55`); one key per seed and one partition per operation (`PartitionIterator.java:71-77, 87-101, 140-146`, `PredefinedOperation.java:49`); seeds `(start + next % totalCount) · (10^16 + 1)` for exactly n permits (`SeedManager.java:46-69, 81, 95-111, 156-182`, `SettingsInsert.java:61-62`, `WorkManager.java:31-55`, `PartitionOperation.java:89-119`). The key set of a load is therefore a fixed function of the source; tolerance **zero**. Counts, by stress's own classes (H2): **E(1..10 M) = 9 999 195**, **E(1..20 M) = 19 997 026**; shakedown E(1..200 000) = 200 000, E(1..400 000) = 400 000 ([`run1b-cluster/stress-key-count.txt`](bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/run1b-cluster/stress-key-count.txt), 22:48:59–22:49:28 EDT). I1: `totalRows` ≠ E(1..N), N_est outside ±5% of 10 M, stress errors > 0, stress `Total partitions` ≠ N, or SSTable count ≠ 1; I3: CTRL bytes outside ±5% of F(0.01) at the CTRL N_est, or CTRL `totalRows` ≠ E(1..2N). The independent-draw model (n²/2D ≈ 500 and 2 000 lost keys for D = 10^11) is named in the amendment and not used: the java.util.Random states of the seeds form an arithmetic progression modulo 2^48, so the draws are not independent. |
| **What was known of run 1, and would run 1 pass** | **All of run 1's results were known** when the amendment was written (§4–§5: `totalRows` 9 999 195 / 19 997 026, the 805 / 2 974 shortfall, the −50% at fp 0.5, every other reading). The amendment takes no number from them: the expected counts come from running stress's generator, and they **equal run 1's readings exactly** (805 and 2 974 lost keys) — this confirms run 1's inference that the shortfall is stress's own key collisions, now computed rather than inferred. The random-draw model, by contrast, would have rejected run 1 (805 against 500 ± 3·22). **Would run 1 pass?** Yes: under the amended I1/I3 run 1's readings pass every validity condition and match **R4** (fp 0.5 at −50.0% while every other value is within ±5%), i.e. **Refuted — caps** ([`run1b-cluster/selfcheck-known-answer-run1-relations-amended.out`](bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/run1b-cluster/selfcheck-known-answer-run1-relations-amended.out)). |
| **Case-file version** | sha256 **`c8b73fda2643ca746f0cf417c0012d75e2577ebc85d62b89cd8b5110e4ad7006`**, a new row in `_INDEX.md` §4: "re-frozen after run 1 for cluster re-run (B3g C6 I1 and I3), authorised by the user". The earlier rows (`5f694732…`, `8bc80c38…`) are kept. Hashed at 22:50:37 EDT, after the fresh clone was built (22:45:44–22:46:42) and the key count (22:49), and before the shakedown (22:51:35) or any re-run reading; recorded again at 22:51:20 in [`run1b-cluster/harness-sha-run2.txt`](bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/run1b-cluster/harness-sha-run2.txt). Section D was filled afterwards, so the file's current hash differs by that section only. Base commit `bee8ad3`; nothing committed. |
| **Harness** | Run 1's harness with the one-line clone override (H1), plus `StressKeyCount.java` (H2) and the self-check copy (H3) (§3).<br>sha256 prefixes: `cluster-run.sh` `0d11bdf2`, `make-node-conf.sh` `08bb9ffe`, `bf.btm` `76780bc5` (also in the run's first log line), `StressKeyCount.java` `a9465572`, `selfcheck.py` `0a56bf7f`.<br>Commands: `C=$W/cassandra-run69 cluster-run.sh run2-shake 200000`, then `C=$W/cassandra-run69 cluster-run.sh run2 10000000`.<br>Instrument checks: `bf.btm` type-checked against run69's classes, "TestScript: no errors" ([`run1b-cluster/btm-check-run69.txt`](bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/run1b-cluster/btm-check-run69.txt)); `StressKeyCount` self-test and `HashSet` cross-check (H2). The self-check ran end to end on the shakedown first: **exit status 0**, `CLUSTER VERDICT: Refuted (R4) — caps`, I1/I2/I3 not holding (`totalRows` 200 000 / 400 000 = E), each rewrite's `BMBF BA` equal to tablestats, ΔLmal within 74 B ([`run1b-cluster/shakedown/selfcheck-cluster-shake.out`](bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/run1b-cluster/shakedown/selfcheck-cluster-shake.out)); it was not changed after the shakedown or the re-run. |

### 7.2 Environment

As run 1 (§2: `yangwang-mbp`, macOS 27.0.1, Darwin 27.0.0 arm64, OpenJDK 11.0.32.1, Ant 1.10.18, Python 3.8.11, internal SSD, 111 GiB free before
the re-run). Fresh clone `$W/cassandra-run69` from `~/cassandra-src` at `b5f2a54210d541339c2e7c17a794195cac0e67c2`, `ant -Dlocal.repository=$W/m2
build-test` BUILD SUCCESSFUL in 52 s ([`run1b-cluster/clone-build-run69.txt`](bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/run1b-cluster/clone-build-run69.txt));
`git status` clean after the re-run. Ports 7000, 7199, 9042, 9091 free and no daemon before each run; node files `$W/node-bfcs`, fresh, wiped at
the end of each run. Times (EDT; node logs in UTC): shakedown 22:51:35–22:54:27, re-run 22:55:11–23:04:48. Full logs:
`$W/logs/bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/` — `cluster-run2-prep/` (clone and build log, key counts),
`cluster-run2-shake/`, `cluster-run2/` (incl. `node/node.out` with the Byteman lines and `node/system.log`). Excerpts in `run1b-cluster/`:
`cluster/` and `shakedown/cluster/` (run 1's kinds of files: per-sample `tablestats-excerpt.txt`, `sstablemetadata-excerpt.txt`, Filter.db/Data.db
names and sizes, `nmt-diff-head.txt`, `nodeout-offset.txt`, `rss.txt`; stress excerpts, ALTER and read-back outputs, `node-out.txt` = the `BMBF`
lines), made after capture by a copy script that does not edit them.

### 7.3 Readings

N_est = 9 901 570 for LOAD … F0.0001, 19 923 827 at CTRL; one sstable at every sample; a new generation at every rewrite (`nb-38` … `nb-44`, CTRL `nb-82`).

| Capacity value | Run | Observable | Reading | Evidence (`run1b-cluster/cluster/`) |
|---|---|---|---|---|
| load | LOAD | stress / sstablemetadata | `Total partitions : 10,000,000`, `Total errors : 0` (69 365 op/s, 2 min 24 s); **`totalRows: 9999195`** = E(1..10 M) | `stress-LOAD-excerpt.txt`, `LOAD/sstablemetadata-excerpt.txt` |
| 0.01 (default) | B0 | tablestats off-heap / Filter.db | 12 376 968 / 12 376 976 (F = 12 376 968) | `B0/` |
| 1.0 | F1.0 | off-heap / Filter.db | 0 / no file; ΔLmal −12 377 005 vs Δtablestats −12 376 968 | `F1.0/`, `node-out.txt` |
| 0.5 | F0.5 | off-heap / Filter.db | **1 237 704** / 1 237 712; F(bpk 2) = 2 475 400 → **−50.0%**; ΔLmal −11 139 338 vs −11 139 264; `BMBF BA 1237704` | `F0.5/` |
| 0.1 | F0.1 | same | 6 188 488 / 6 188 496; F exact; ΔLmal = Δtablestats; BA 6 188 488 | `F0.1/` |
| 0.01 | F0.01 | same | 12 376 968 / 12 376 976; F exact; ΔLmal −37 vs 0; BA 12 376 968 | `F0.01/` |
| 0.001 | F0.001 | same | 18 565 448 / 18 565 456; F exact; ΔLmal 6 188 406 vs 6 188 480; BA 18 565 448 | `F0.001/` |
| 0.0001 | F0.0001 | same | 24 753 928 / 24 753 936; F exact; ΔLmal = Δtablestats; BA 24 753 928 | `F0.0001/` |
| 0.00006 | REJ | cqlsh | exit 2, `ConfigurationException: bloom_filter_fp_chance must be larger than 6.71E-5 and less than or equal to 1.0 (got 6.0E-5)`; read-back 0.0001 | `alter-REJ.txt`, `readback-REJ.txt` |
| 0.01, 2× keys | CTRL | off-heap / Filter.db / rows | 24 904 792 / 24 904 800 (F at 19 923 827 = 24 904 792 exact; 2.012 × F0.01); stress 10 M more, 0 errors; **`totalRows: 19997026`** = E(1..20 M) | `CTRL/`, `stress-CTRL-excerpt.txt` |
| all | all | NMT `Other` diff from the baseline | +2 KB … +65 KB while the filter moved by up to ±12.4 MB (information only, C3 (3)) | `<sample>/nmt-diff-head.txt` |
| all | all | Byteman bookkeeping | 1 823 `BMBF` lines, no unmatched free, no duplicate address, no malformed line; 0 `ERROR` lines in system.log | `selfcheck-cluster.out`, `error-count.txt` |

Every filter, Lmal and Lbf figure is identical to run 1's to the byte (the load is deterministic: same keys, same flush and compaction
sequence, same generations).

### 7.4 Cluster re-run — conclusion and logic

1. **Validity** — valid under the amended C6: `totalRows` 9 999 195 = E(1..10 M) and 19 997 026 = E(1..20 M); stress `Total partitions`
   10 000 000 for both loads with 0 errors; N_est −0.98% from 10 M; one sstable at every sample [observed: `LOAD/` and `CTRL/sstablemetadata-excerpt.txt`,
   stress excerpts]. I2: a new generation at every rewrite [observed: `<sample>/data-files.txt`]. I3: CTRL = F(0.01) at the CTRL N_est to the byte.
   The re-run used the re-frozen version (`c8b73fda…`, hashed before the shakedown) [observed: `harness-sha-run2.txt`].
2. **Readings** — F0.1 … F0.0001 equal F(fp) at N_est to the byte and Filter.db = off-heap + 8; F1.0 is 0 with no file; F0.5 is −50.0% from
   F (1 bit per key); ΔLmal tracks Δtablestats within 74 B, ΔLbf within 16 B, and each rewrite at fp < 1.0 prints a `BMBF BA` equal to the
   sample's off-heap figure; 0.00006 is refused with the C5 text and the value stays 0.0001 [observed: `selfcheck-cluster.out`, the sample files].
3. **Matched row** — **R4, Refuted** (C6 R4, the row the audit added: bpk at one or more values not as traced): the bytes at fp 0.5
   deviate by −50.0% from F(0.5) while every other value is within ±5% (all exactly 0%) at the same N_est [observed]. The cause is the line-147
   floor: line 149 builds `BloomSpecification(2, optKPerBuckets[2])` with the arguments in `(k, bucketsPerElement)` order, so 1 bit per key and
   K = 2 (S1, `BloomCalculations.java:114, 149`), the same as the unit tier [inferred: source; the bytes equal ceil((N_est·1 + 20)/64)·8 = 1 237 704].
4. **Excluded rows** — I1, I2, I3: by (1). R1 (bytes unchanged after a rewrite at a new fp): every rewrite moved the bytes. R2 (Lmal/Lbf/`BA` tracking):
   holds within 74 B / 16 B and every `BA` line present. R3 (0.00006 accepted): refused. N1 (all deviate in one direction): five of six exact.
   C: excluded by R4. N0: not reached.
5. **Observed vs. inferred** — the verdict rests on observed bytes, `totalRows` and stress counts; E comes from executing stress's generator
   (a computation from source, H2); the line-149 cause is inferred from the source and agrees with the unit tier's observation.
6. **Deviations and gaps** — none from the re-frozen runbook. NMT did not see the filter (expected, C3 (3)); the OS view of malloc'd bytes is a
   named gap (C3 (4)).
7. **Core question** — usage follows the knob: filter bytes (off-heap, Filter.db and the native allocation the Byteman ledger sees) rise as fp
   falls across the six values (0, 1.24, 6.19, 12.38, 18.57, 24.75 MB at 9.9 M keys), are largest at 0.0001, double with twice the keys, and
   0.00006 is refused at ALTER: **Effect caps** (bytes per key between a 1-bit floor and a 20-bit ceiling). B1's claim is wrong at the floor
   (1 bit per key, not 2), so the tier is **Refuted**.

**Conclusion (one line):** cluster re-run — C6 R4 (at fp 0.5 only) — **refuted** (Effect: caps).

### 7.5 Self-check of the cluster re-run — AI

`run1b-cluster/selfcheck.py` (H3) re-reads the raw files (`cluster-run2/<sample>/*.txt`, `stress-*.txt`, `alter-REJ.txt`, `readback-REJ.txt`,
`node/node.out` up to each sample's offset), never `summary.txt`, and applies C5 and the amended C6. It was written after the amendment and before
any re-run reading, and not changed afterwards (sha256 `0a56bf7f…` in `harness-sha-run2.txt`).
- **Pass 0 (shakedown, run end to end first):** exit status 0, `CLUSTER VERDICT: Refuted (R4) — caps` (`run1b-cluster/shakedown/selfcheck-cluster-shake.out`).
- **Pass 1 (re-run raw files, amended relations):** exit status 0, **`CLUSTER VERDICT: Refuted (R4) — caps`**; I1/I2/I3/R1/R2/R3/N1 not holding,
  R4 holding for fp 0.5 only; 9 samples, 1 823 Byteman lines, 0 anomalies ([`run1b-cluster/selfcheck-cluster.out`](bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/run1b-cluster/selfcheck-cluster.out)).
- **Pass 2 (known answer, run 1's raw files, run-1 relations):** output identical to `run1/selfcheck-cluster.out` after its one-line header,
  `Invalid (I1, I3)` ([`selfcheck-known-answer-run1-relations-run1.out`](bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/run1b-cluster/selfcheck-known-answer-run1-relations-run1.out)).
- **Pass 3 (run 1's raw files, amended relations):** `Refuted (R4) — caps` ([`selfcheck-known-answer-run1-relations-amended.out`](bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/run1b-cluster/selfcheck-known-answer-run1-relations-amended.out)).
- **Pass 4 (information, re-run raw files, run-1 relations):** `Invalid (I1, I3)` ([`selfcheck-rerun-under-run1-relations.out`](bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/run1b-cluster/selfcheck-rerun-under-run1-relations.out)):
  the script tells the two relation sets apart, and the re-run differs from run 1 only by the rule.
- By hand, in the full logs: `totalRows: 9999195` and `totalRows: 19997026` in `LOAD/` and `CTRL/sstablemetadata.txt`; `Total partitions : 10,000,000`
  and `Total errors : 0` in both stress files; `Bloom filter off heap memory used: 1237704` and `24753928` in `F0.5/` and `F0.0001/tablestats.txt`;
  the `nb-40` `Filter.db` of 1 237 712 B; the REJ text.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `totalRows` = E at LOAD and CTRL, stress counts and errors, one sstable, new generations — re-read in the raw files |
| 2. Readings | yes | every number in §7.3 re-read in the sample files; F recomputed by the script |
| 3. Matched row | yes | R4 is the first Refuted part holding in C6's order after the Invalid rows; R1–R3 do not hold |
| 4. Excluded rows | yes | as stated in §7.4 (4) |
| 5. Observed vs. inferred | yes | the verdict uses observed values; E is a computation from source; the floor cause is marked inferred |
| 6. Deviations and gaps | yes | no runbook deviation; harness changes H1–H3 recorded before the re-run |
| 7. Core question | yes | bytes per key follow fp between a floor and a ceiling, 0.00006 refused (caps); the claim's floor is wrong (Refuted) |

### 7.6 Verdict of the cluster re-run

**Cluster tier (re-run at `c8b73fda…`): Refuted — C6 R4 (added row; at fp 0.5 only). Effect: caps.** Run 1's cluster verdict (Invalid —
undetermined, C6 I1, I3) stays in §4 and in §8 as the result at `8bc80c38…`; the re-run's verdict is the tier's current verdict. Run 2 not done:
the re-run is byte-identical to run 1 and agrees with the unit tier's observed floor.

**End of the re-run:** no `CassandraDaemon` process, no stress JVM, no cqlsh (last summary lines of both runs); `$W/node-bfcs` wiped;
`$W/cassandra-run69` `git status` clean, no `cassandra.logdir_IS_UNDEFINED/` left.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested (B1):** for a fixed N, the bloom filter's off-heap bytes (and Filter.db bytes) equal `ceil((N_est·bpk(fp)+20)/64)·8` with
bpk = 2 for fp ≥ 0.393, 5 for 0.1, 10 for 0.01, 15 for 0.001, 20 for 0.0001, 0 bytes for fp = 1.0; fp below 6.71e-05 is rejected.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Refuted** — U4 R1, R3, R4 (filed B2g rows 2, 4, 5): the floor is 1 bit/key with K = 2 (125 008 / 250 008 B, FP rate 0.747 above fp 0.5 / 0.393), and `computeBloomSpec(20, 6.71E-5)` does not throw; every interior value matches B2f exactly and 6.0E-5 throws | **caps** (bytes per key a step function of fp between 1 and 20 bits) | run 1 + self-check | 2026-10-27 |
| Cluster | **Invalid** — C6 I1, I3: `totalRows` 9 999 195 / 19 997 026 ≠ 10 M / 20 M (stress's legacy keys collide); readings, for information, would give R4 (fp 0.5 at −50%) with every other value exact, ΔLmal within 74 B and the 0.00006 refusal | **undetermined** (invalid run) | run 1 + self-check | 2026-10-27 |
| Cluster (re-run at `c8b73fda…`, after the user-authorised C6 I1/I3 amendment) | **Refuted** — C6 R4 (added row; fp 0.5 only): with `totalRows` 9 999 195 / 19 997 026 equal to the distinct-key counts the stress source determines, fp 0.5 gives 1 237 704 B, −50.0% from F (1 bit per key, the line-149 argument order), while 0.1, 0.01, 0.001, 0.0001 equal F at N_est to the byte, fp 1.0 gives 0 and no Filter.db, Byteman ΔLmal tracks tablestats within 74 B with a `BMBF BA` per rewrite, CTRL at 2× keys = F (2.012 × F0.01), and 0.00006 is refused at ALTER | **caps** (filter bytes per key a step function of fp between 1 and 20 bits; the minimum refused) | cluster re-run (§7) + self-check | 2026-10-27 |

**Feedback filed:** the case file's section D (uncommitted), and `_INDEX.md` §1 Stage 4 column and §2 frozen row (uncommitted).
B1/B2f/B3f are not edited (a refuted claim is left as filed; S1 and S2 are the feedback for stage 3). A cluster re-run needs a user-authorised
re-freeze of C6 I1/I3.

**Feedback filed for the cluster re-run (2026-10-27):** the amendment `Amendment 2026-10-27 (after run 1, authorised by the user) — B3g C6 I1
and I3` in the case file; a new `_INDEX.md` §4 row (`c8b73fda…`); the case file's section D (new entry); the §1 Stage 4 column (run-1 text
kept, re-run verdict appended). The coverage section is not touched. B1, B3f and the unit tier are not edited (the refutation is recorded here and
in section D; S1 is the feedback for stage 3). Run-1 findings kept as observations: the 1-bit floor from the swapped arguments at
`BloomCalculations.java:149`, `computeBloomSpec(20, 6.71E-5)` not throwing (S2), NMT blind to JNA malloc (S3). New finding for stage 3: the legacy
cassandra-stress write does not give n distinct partitions for n writes — its keys are a fixed function of the seeds (805 of 10 M and 2 974 of
20 M collide here, reproduced exactly by stress's own generator); a design that needs an exact partition count must compute it or use a
collision-free key generator.
