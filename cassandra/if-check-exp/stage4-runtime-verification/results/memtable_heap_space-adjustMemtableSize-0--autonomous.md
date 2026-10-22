# memtable_heap_space-adjustMemtableSize-0--autonomous — stage-4 results  <!-- file: results/memtable_heap_space-adjustMemtableSize-0--autonomous.md -->

> **Case:** [`memtable_heap_space-adjustMemtableSize-0--autonomous`](../../stage3-ai-deep-read/cases/memtable_heap_space-adjustMemtableSize-0--autonomous.md)
>
> **Status:** verdict filed 2026-10-22. **Unit Confirmed — caps (loose, r = 3.5); cluster Not confirmed (no matching row) — undetermined.** Run 1 only.
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e; the
> feedback section is the case file's section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Not committed (untracked, as filed by stage 3). sha256 as filed `167458f9301dd6abac55d54685592393fbf2db4efbfe68dcc6d90b2c81f31724`; **frozen after the audit's amendments (2026-10-22 04:22 EDT, before any reading): `0600e3b3a0cd633b84e30ce24821ddb19797613322eaf750454e8efaa831c06d`**. |
| **Harness** | `../harness/memtable_heap_space-adjustMemtableSize-0--autonomous/`: `SaiMemtableChargeTest.java` (verbatim from B2e), `unit-run.sh`, `sai-profile.yaml`, `plain-profile.yaml`, `SaiPoll.java`, `cluster-run.sh`, `all-runs.sh`, `analyze.py`, `README.md`. Not committed (no commit asked). Run copy `pc07:~/stage4-harness-run/sai/` with `SHA256SUMS`. |
| **Tiers and values** | Unit (B2): U1/U2 at 512 MiB (non-binding), U3 at 32 and 96 MiB, `unslabbed_heap_buffers`. Cluster (B3): R1 64 / R2 256 / R5 1024 MiB (= default for a 4 GiB heap) with the SAI table; R3 64 / R4 256 / R6 1024 MiB plain twin; 10,000,000 rows each, `heap_buffers`. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-22 |

**Overlap with closed cases.** `memtable_heap_space-tryAllocate-limit--guided/--autonomous` test the hard check at
`MemtablePool.java:156`, and `memtable_heap_space-needsCleaning-nextClean--autonomous` the flush trigger at `:128`, with
plain tables. This file tests whether the **SAI memtable index's** growth (the `additionalSpace` operand at
`StorageAttachedIndex.java:1006`) is charged into that same pool and is therefore governed by `memtable_heap_space`; the pool
mechanics themselves (trigger at L·t, block at L) are taken as established there and are only re-observed here.

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: heap of the SAI memtable index; operand `additionalSpace` in bytes |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly → Met after A-K1 | Unit: two binding values (32, 96) + non-binding 512, default not run (1 GiB test JVM). Cluster as filed: 64/256 with 1024 optional; A-K1 makes R5 = 1024 MiB (default for `-Xmx4G`) required and adds its plain twin R6 |
| A. Core question | real resource measured, not only the counter (gap named) | Met | U2 `measureDeep` of the trie; B3d forced-GC class histograms (ΔH, SAI class counts); gap named (byte[] attribution) |
| A. Core question | usage driven to the limit and past it | Met | U3 400k rows ≈ 11 / 4 flushes; cluster 10M rows ≈ 5–6 GB charge vs L ≤ 1 GiB |
| B. Logic | each step says what it establishes | Met | B1, B2h, B3h |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f, B3f (bands and ratios); B3f's c_t was not computable (A-K4) |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after A-U2/A-K5 | Missing as filed: knob not applied (cluster), usage exceeds L (cluster), flat across L (unit), flush during U1, "heap grows in both arms"; B2f vs B2g contradicted each other on `poolUsed > L`; partial outcomes had no mapping. A-U2/A-K5 give each row a numeric test, an order and a verdict; bands become sub-predictions |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | the "disallow" of line 1006 is the negative-delta drop (never taken for text); the effect under test is the charge, shown directly by U1's `dS − dP == S`, and the cap acting is shown by MEMTABLE_LIMIT flushes and `Flushing largest` lines |
| B. Logic | alternative explanations and their controls | Partly → Met after A-K2 | plain twins, two/three L, H0, flush reasons. Not controlled as filed: compaction-time SAI segment buffers (default 1024 MiB, outside the pool, SAI runs only) |
| C. Specific | a human can follow it from the intro and B1 | Met | |
| C. Specific | an AI can run B2–B3 without re-deriving the code path | Met | full test code, profile and commands |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after A-U1/A-K3 | U3's allocation type implicit; 2 s sampling with `sjk` (one JVM per value) not achievable; 60 s histograms give too few points |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | clone + `ant build-test`; stress in-tree |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | ≤ 3 GB data per run, wiped between runs; 51 GB free on `/` |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Partly | Checked as cited: `StorageAttachedIndex.java:563-578, 989-1008, 635, 655`; `MemtableIndexManager.java:69-160`; `MemtableIndex.java:49-67`; `TrieMemoryIndex.java:67, 94-127, 365-378`; `AbstractAllocatorMemtable.java:59, 76-112, 194-197, 286-293`; `MemtablePool.java:47, 101-105, 216`; `DatabaseDescriptor.java:586-590`; `YamlConfigurationLoader.java:152-168`; `IndexMetrics.java:57-58`; `AbstractMetrics.java:31, 84-96`; `ColumnFamilyStore.java:1055`; `PrimaryKey.java:245` (`SkinnyPrimaryKey`). **Wrong:** `AllMemtablesOnHeapDataSize` reads only current memtables (`TableMetrics.java:506-512`), not the pool (A-K3) |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| A-U1 | U3 keeps `unslabbed_heap_buffers`; one JVM per L | Applied 2026-10-22, case file after B2e | "same command" was ambiguous |
| A-U2 | B2g decision table: numeric tests, order, verdicts, added rows (Invalid incl. flush in U1; equal flush counts; exceeds L; never-decreasing S; flat across L); settles B2f vs B2g on `poolUsed > L` (> 1.25·L refutes, (L, 1.25·L] qualifier) | Applied 2026-10-22, case file after B2g | Group B: every outcome needs a row; avoids any post-reading row (2026-10-22 rule) |
| A-K1 | R5 (1024 MiB = default) required; R6 plain at 1024 MiB added | Applied 2026-10-22, after B3b | Group A: ≥ 3 values incl. default |
| A-K2 | `sai_options.segment_write_buffer_size: 16MiB` in every run; sample `SegmentBufferSpaceUsedBytes` | Applied 2026-10-22, after B3b | compaction-time SAI segment heap (default 1 GiB, `V1OnDiskFormat.java:115-128`) is outside the pool and in SAI runs only; it would confound ΔH |
| A-K3 | JMX sampler (`SaiPoll.java`) for all values every 2 s; `AllMemtablesOnHeapDataSize` is current-only; histograms every 30 s; 50 %/100 % points defined; flush counts after the run offset for the run's table | Applied 2026-10-22, after B3d | `sjk` starts a JVM per value; citation error; too few histogram points |
| A-K4 | c_t / c_s defined from `MemtableOnHeapDataSize / MemtableColumnsCount`; R5/R6 predictions by the same formulas | Applied 2026-10-22, after B3f | "c_t = owns/W in R3" not computable (no W without SAI) |
| A-K5 | B3g decision table (numeric tests, order, verdicts, added rows) | Applied 2026-10-22, after B3g | as A-U2 |
| E1 | Paths `$WORK=/var/tmp/sai-exp` → clone `~/cassandra-sai`, data `~/stage4-sai`, logs `~/stage4-logs/sai`; node on 127.0.0.5, JMX 7205 (the file proposes 127.0.0.1 / 7199); `pgrep` checks restricted to `java` processes naming `cassandra-sai` | Environment deviation, not a case-file change | shared host: another stage-4 agent's node on 127.0.0.4 / 127.0.0.6 (JMX 7204 / 7206) |
| S1 | The unit tier could add a third binding L (e.g. 64 MiB) and the default (256 MiB in a 1 GiB test JVM, OOM risk) | Left for stage 3 | cluster tier covers the default |
| S2 | B3f's ΔH bound mixes slab (cluster, `heap_buffers`) and exact (unit, unslabbed) charges when comparing r_cluster with r_unit | Left for stage 3 | sub-prediction only |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-22, unit 04:23–04:26 EDT, cluster 04:31–05:14 EDT (log lines are UTC) |
| Node | `pc07` (`node0.jason92-320876`), 40 cores, 251 GiB; **shared** with another stage-4 agent's node (`~/cassandra-ncs`, 127.0.0.4 / 127.0.0.6), which ran its cluster tier during this run (shared CPU and disk; deviation) |
| OS and kernel | Ubuntu 22.04.2, `5.15.0-187-generic` |
| JDK | OpenJDK 11.0.32.1 |
| Ant | 1.10.12 |
| Local clone | `~/cassandra-sai`, `cassandra-5.0.9` = `b5f2a54210d541339c2e7c17a794195cac0e67c2`, `ant build-test` 1 min 10 s, `BUILD SUCCESSFUL`; untracked after the run: the copied `SaiMemtableChargeTest.java` only |
| Case-file commit / harness commit | none (untracked); sha256s in §1 and §8 |
| Storage | `/dev/sda3` local ext; node data `~/stage4-sai/node` (≤ 2.4 GB per run, wiped before each run and after the last) |
| Node settings | `MAX_HEAP_SIZE=4G` (G1, shipped options), `ulimit -n 100000`, 127.0.0.5, JMX 7205, `heap_buffers`, yaml diff per run in `run1/R<n>/yaml.diff` |
| Full logs | `pc07:~/stage4-logs/sai/` (`unit/`, `R1`…`R6`, `attempt1-R1/`, `analyze-cluster.txt`) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file change |
|---|---|---|---|---|---|---|
| D1 | 1 | B3c/B3e (cluster, R1 attempt 1) | cassandra-stress runs the profile's `extra_definitions` on every call; after B3e step 2's schema run, the load command failed at once: `InvalidQueryException: Index 't_sai_v_idx' already exists`. No load written | `CREATE INDEX IF NOT EXISTS` in the profile | 2026-10-22; attempt 1 not counted; the cluster tier restarted from R1 (attempt 2 = run 1). B3f/B3g unchanged | dated fix in B3c (sha256 after it `619815786b543db6429cde53915e26a75e81245c347ddb39667daeec8dccca81`) |
| H1 | 1 | harness (`cluster-run.sh`) | the OOM counter matched the JVM flag `-XX:+HeapDumpOnOutOfMemoryError` | count `OutOfMemoryError: ` only | 2026-10-22, with D1, before attempt 2 | none |
| H2 | 1 | harness (`analyze.py`, display only) | the "other table" count in the `Flushing largest` summary missed the `CFS(Keyspace='saiks', …)` format | match `Keyspace='saiks'` | 2026-10-22, after the readings; no test or row touched | none |

## 4. Run 1

**Scope:** both tiers, all values (unit U1/U2 512 MiB, U3 32 and 96 MiB; cluster R1–R6). **Command log:**
`memtable_heap_space-adjustMemtableSize-0--autonomous/run1/unit/` (`unit-run.log`, `unit.csv`, `junit-*.xml`, `ant-summary.txt`,
`analyze-unit.txt`); per cluster run `run1/R<n>/` (`run.log`, `yaml.diff`, `samples.csv`, `hist-index.txt`, `hist-excerpt.txt`,
`trig.txt`, `flushes.txt`, `stress-summary.txt`); `run1/analyze-cluster.txt`; `run1/aborted-attempts.txt`.

### 4.1 Readings

**Unit tier** (`run1/unit/unit.csv`, `analyze-unit.txt`; JUnit 1 + 2 + 2 tests, 0 failures, 0 skipped; startup lines show 512 / 32 / 96 MiB and `Memtables allocating with on-heap buffers` = `unslabbed_heap_buffers`)

| Test or assertion | Result | Evidence |
|---|---|---|
| U1 `dS − dP == S` | **12,979,488 = 12,979,488** (dS 69,979,488, dP 57,000,000), exact | `unit.csv` U1U2 |
| U1 `S > 0`, `W == N`, flushes | S = 12,979,488 B; W = N = 100,000; flushes 0 | same |
| U1 `S/N` in 100–400 | 129.8 B/row (hit) | same |
| U2 `(D − K)/S` in 1.2–2.5 | **3.491 (miss)**; D = D2 = 45,310,184, K = 216 | same |
| U2 `(D − K) − S ≥ 100·N` | 32,330,480 = 323.3 B/row uncharged (hit) | same |
| U3 32 MiB | SAI 25 flushes, plain 20 (ratio 1.250 vs dS/dP 1.228); max poolUsed SAI 23,602,929 (0.70 L), plain 32,975,043 (0.98 L); max S 4,393,824 (0.13 L); S decreased 24 times | `unit.csv` U3 rows |
| U3 96 MiB | SAI 8, plain 6 (1.333); max poolUsed 57,066,119 (0.57 L) / 46,171,887 (0.46 L); max S 11,567,008 (0.115 L); S decreased 7 times | same |
| U3 across L | flushes(32)/flushes(96) = 3.125 (3 ± 1, hit); maxS(96)/maxS(32) = 2.633 (2–4, hit) | same |

**Cluster tier** (`run1/analyze-cluster.txt`; every run: startup line `Global memtable on-heap threshold is enabled at <L>MiB`, 10,000,000 partitions, 0 errors, no OOM/crash, 0 `^ERROR` lines; one `USER_FORCED` flush per run after the load, from B3e step 4)

| L (MiB) | Run | MEMTABLE_LIMIT flushes | stress time / rate | max S (`MemtableIndexBytes`) | S drops > 25 % (in-stress samples) | max on-heap `Used total` | BlockedOnAllocation | ownsCur/ops (B/row) | peak ΔH (MiB) | ΔH 50 % → 100 % | max SkinnyPrimaryKey (bound 3·L/(c_t+c_s)) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 64 | R1 SAI | **289** | 91 s / 108.8 k/s | 13.1 MiB (0.205 L) | **2** (50 samples) | **1.00** (113 of 289 lines: live 0.33 + flushing 0.67) | 9,339 | 646.4 | 124.7 | 123.5 → 124.7 | 98,749 (311,455) |
| 256 | R2 SAI | **74** | 91 s / 108.9 k/s | 58.6 MiB (0.229 L) | **2** (49) | 0.67 | 1,792 | 653.5 | 422.4 | 422.4 → 369.9 | 375,638 (1,245,822) |
| 1024 | R5 SAI | **18** | 99 s / 100.5 k/s | 219.8 MiB (0.215 L) | **3** (54) | 0.67 | 352 | 662.1 | 1,502.9 | 1,022.5 → 1,502.9 | 1,555,921 (4,983,287) |
| 64 | R3 plain | **230** | 58 s / 172.1 k/s | — | — | 0.67 | 0 | 512.5 | 56.2 | 56.2 → 52.4 | 0 |
| 256 | R4 plain | **57** | 71 s / 139.8 k/s | — | — | 0.67 | 0 | 515.1 | 136.7 | 106.2 → 136.7 | 0 |
| 1024 | R6 plain | **14** | 89 s / 111.7 k/s | — | — | 0.33 | 0 | 515.8 | 561.5 | 521.6 → 561.5 | 0 |

Derived: c_t = 512.5 B/row (R3), c_t + c_s = 646.4 (R1), c_s = 133.9 (unit S/N 129.8). Flush ratios R1/R3 = 1.257 (predicted
(c_t + c_s)/c_t = 1.261; B3f band 1.3–2.5 **missed**), R1/R2 = 3.905, R2/R5 = 4.111, R3/R4 = 4.035, R4/R6 = 4.071 (all in 4 ± 1.5).
Peak ΔH R2/R1 = 3.39, R5/R2 = 3.56 (2–6, hits); SAI − plain at the same L: 68.5 / 285.7 / 941.4 MiB. r_cluster =
(ΔH_R1 − ΔH_R3)/peak S_R1 = 5.22 vs r_unit 3.49 (±30 % **missed**; not > 2 × r_unit, so qualifier Qa does not apply).
`SegmentBufferSpaceUsedBytes` max 18.7–19.7 MB in the SAI runs (A-K2's 16 MiB limit). Only 2–3 class histograms fell inside
each load (65–108 s; B3c assumed 20–50 k ops/s, the node ran 100–172 k). After the final flush R1's `SkinnyPrimaryKey` count
was 4,497 (`run1/R1/hist-excerpt.txt`, `final-…`).

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — [observed: `junit-*.xml`, `unit-run.log`] no test skipped; each JVM logged its own L (512 / 32 / 96 MiB) and the
   unslabbed pool; U1 had 0 flushes; the plain table flushed 20 times at 32 MiB. Valid.
2. **Readings** — nothing contradictory. `(D − K)/S` = 3.49 is above the predicted band. [observed: `unit.csv`]
3. **Matched row** — A-U2 row 7 (B2g row 1): "`abs(dS − dP − S) ≤ 0.01·S`; `flushes(sai) > flushes(plain)` at both L; in each
   U3 SAI run `S` decreases at least 3 times and `maxS ≤ L/2`; `flushes(sai,32)/flushes(sai,96) ≥ 1.5` and
   `maxS(96)/maxS(32) ≥ 1.5`" — difference 0; 25 > 20 and 8 > 6; 24 and 7 decreases, maxS 0.13 L and 0.115 L; 3.125; 2.633.
   [observed: `unit.csv`, `analyze-unit.txt`] Qualifier Qb: `(D − K)/S` = 3.49 > 3 (the uncharged footprint is larger than the
   charge; loose bound).
4. **Excluded rows** — 1 (Invalid): see part 1. 2 (Refuted, not applied / not governing): `dS − dP` = S > 0, SAI flushes > plain
   at both L. 3 (mis-charge): difference exactly 0. 4 (exceeds): max S 0.13 L, max poolUsed 0.98 L ≤ 1.25 L and ≤ L. 5 (not
   released): 24 and 7 decreases. 6 (flat): 3.125 and 2.633. Qa not met (no poolUsed > L). [observed: `unit.csv`]
5. **Observed vs. inferred** — the conclusion is observed throughout. Inferred only in the qualifier: that the 323 B/row
   `measureDeep` excess is the per-row key objects and trie slack the case names (A3 (a), (b)) — the unit tier does not break D down.
6. **Deviations and gaps** — paths and host (E1). The unit tier measures the charge and the pool's response, not the GC heap.
   r_unit missed its band.
7. **Core question** — each row's SAI growth estimate is charged into the on-heap memtable pool, exactly (part 3); that charge
   makes the SAI table flush more often and holds S below L/2, scaling with L (32 → 96 MiB: 3.1× fewer flushes, 2.6× larger
   peak S). At unit level `memtable_heap_space` caps the SAI memtable index's charge; the real footprint is 3.5× the charge.

**Conclusion (unit, one line):** A-U2 row 7 (B2g row 1) — **confirmed**, Effect *caps* (loose: r_unit = 3.49).

**Cluster tier**

1. **Validity** — [observed: `R<n>/run.log`] each run logged its L; 10,000,000 partitions, 0 errors; 14–289 MEMTABLE_LIMIT
   flushes of the run's own table; no crash. Valid (A-K5 row 1 not met).
2. **Readings** — R1 reached the hard cap: 113 of 289 `Flushing largest` lines show `Used total: 1.00` with
   `live 0.33, flushing 0.67`, and `BlockedOnAllocation` counted 9,339 waits [observed: `R1/trig.txt`, `R1/samples.csv`].
   S never saws to zero during the load: at 64 / 256 MiB the pool flushes every 0.3 / 1.2 s, so each 2 s sample sums several
   live and flushing memtable indexes (R1: S between 8.5 and 13.1 MiB from 11 s to 97 s into the load, with no upward trend) [observed: `R1/samples.csv`;
   inferred: flush interval = run time / flush count]. ΔH in R5 rose 1,022.5 → 1,502.9 MiB between the 50 % and 100 %
   histograms (480 MiB, under the 512 MiB threshold) [observed: `R5/hist-index.txt`].
3. **Matched row** — **none of rows 1–9; A-K5 row 10, "anything else: Not confirmed (no matching row)".** Row 9 (Confirmed) needs
   in R1, R2 and R5 "S falls by > 25 % between consecutive samples at least 3 times"; the counts are **2, 2 and 3** [observed:
   `analyze-cluster.txt`, recounted with `awk` from `samples.csv`]. Every other condition of row 9 holds: R1/R3 = 1.257 > 1.05;
   max S 0.205 / 0.229 / 0.215 L ≤ L/2; ΔH(100 %) − ΔH(50 %) = 1.2 / −52.5 / 480.4 MiB < 0.5·L; SkinnyPrimaryKey ≤ bound at every
   histogram; peak ΔH R2/R1 = 3.39 ≥ 1.25 and R5 > R2; R1/R2 = 3.9 and R2/R5 = 4.1 ≥ 2.
4. **Excluded rows** — 2 (OOM/crash): none. 3 (exceeds): max S ≤ 0.23 L; max `Used total` 1.00 is not > 1.00. 4 (charge not
   reaching the pool): R1/R3 = 1.257. 5 (retained outside the cap): R1's last SkinnyPrimaryKey count 98,749 < 311,455; R1 ΔH
   growth 1.2 MiB. 6 (positive control): R3/R4 = 4.04, R4/R6 = 4.07. 7 (flat): R1/R2 = 3.9, ΔH ratio 3.39. 8 (heap dominated by
   something else): ΔH ratio 3.39 ≥ 1.25; R1 and R3 do not grow. 9: see part 3. Qb applies (BlockedOnAllocation > 0 in R1, R2, R5);
   Qa does not (5.22 < 6.98). [observed: `analyze-cluster.txt`]
5. **Observed vs. inferred** — the row match is observed. Inferred: that the failed condition reflects sampling resolution
   (several flushes per sample) rather than an index that is not released — supported by the observed flat S range, by
   SkinnyPrimaryKey counts that stay bounded, and by R1's count falling to 4,497 after the final flush, but this cannot change
   the row.
6. **Deviations and gaps** — paths, address 127.0.0.5 / JMX 7205, shared host (E1); defect D1 restarted the tier; 2–3
   in-stress histograms per run (the load ran 2–5× faster than B3c assumed), so the ΔH growth tests rest on few points.
7. **Core question** — every observation in the table follows the constraint: the SAI table's flush count is 1.26× its plain
   twin's (as the measured charge predicts), flushes and peak S scale with L across three values including the default, peak
   live heap follows L (125 / 422 / 1,503 MiB at 64 / 256 / 1024 MiB), and writers blocked at the cap in R1. But the frozen
   decision table makes the "sawtooth" condition decisive, and it failed as specified, so this tier does not confirm the claim.

**Conclusion (cluster, one line):** A-K5 row 10 — **not confirmed (no matching row)**, Effect *undetermined*.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `unit-run.log` (threshold lines, 0 skipped in all three XMLs), each `R<n>/run.log` threshold line and stress totals re-read by `grep`; flush counts recounted from `system-run.log` (289 / 74 / 230 / 57 / 18 / 14) |
| 2. Readings | yes | `R1/trig.txt`: 113 lines with `Used total: 1.00`, each `live: 0.33, flushing: 0.67`; `R1/samples.csv` S series listed by hand (8.5–13.1 MiB) |
| 3. Matched row | yes | S-drop counts recounted independently with `awk` over the in-stress window: 2 / 2 / 3; the other row-9 conditions recomputed from the per-run figures |
| 4. Excluded rows | yes | each earlier row checked against the numbers in §4.1; `analyze.py`'s order follows A-K5 |
| 5. Observed vs. inferred | yes | the one inference (sampling resolution) is labelled and not used for the verdict |
| 6. Deviations and gaps | yes | D1 recorded; attempt 1 wrote no load (`attempt1-R1/run.log`: 0 MEMTABLE_LIMIT flushes) |
| 7. Core question | yes | unit: the audited logic leads to row 7. Cluster: per the 2026-10-22 rule no row was added or changed after the readings; the verdict is row 10 |

Unit tier: re-counted U3 flushes, max poolUsed, max S and decreases with `awk` from `unit.csv` (identical to `analyze-unit.txt`).

### 5.2 Run 2?

**No** (2026-10-22). The unit verdict rests on observed values only. The cluster verdict comes from the frozen table, not from
an unsettled reading; a run 2 under the same table and 2 s sampling would hit the same condition, and the rule forbids re-running
a tier to fit a new row. A better-resolved sawtooth test belongs in a new design (section D).

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested (B1):** every byte that `TrieMemoryIndex.add` reports is charged to the on-heap memtable pool limited by
`memtable_heap_space`, so the SAI memtable index's reported size and retained heap stay bounded by a constant multiple of
`memtable_heap_space`, the bound moves with the knob, and the retained heap exceeds the charge by r > 1.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — A-U2 row 7 (B2g row 1), qualifier Qb (r_unit = 3.49 > 3, loose bound) | **caps** | run 1 + self-check | 2026-10-22 |
| Cluster | **Not confirmed (no matching row)** — A-K5 row 10; the only failed condition of row 9 is "S falls > 25 % between consecutive 2 s samples ≥ 3 times" (2 / 2 / 3 in R1 / R2 / R5) | **undetermined** | run 1 + self-check | 2026-10-22 |

Key numbers: unit `dS − dP = S` = 12,979,488 B exactly (129.8 B/row charged, 323 B/row uncharged); U3 flushes 25 vs 20 and
8 vs 6, peak S 0.13 / 0.115 L. Cluster flushes 289 / 74 / 18 (SAI) vs 230 / 57 / 14 (plain) at 64 / 256 / 1024 MiB; peak ΔH
125 / 422 / 1,503 vs 56 / 137 / 562 MiB; R1 at the hard cap (`Used total` 1.00, 9,339 blocked allocations).

**Feedback filed:** the case file's section D (2026-10-22); amendments A-U1, A-U2, A-K1–A-K5 (audit, before any reading) and
the D1 fix in B3c. Case-file sha256: as filed `167458f9301dd6abac55d54685592393fbf2db4efbfe68dcc6d90b2c81f31724`; frozen
`0600e3b3a0cd633b84e30ce24821ddb19797613322eaf750454e8efaa831c06d`; after D1 `619815786b543db6429cde53915e26a75e81245c347ddb39667daeec8dccca81`;
final after section D: see the line below.

**Final case-file sha256 (after section D, 2026-10-22): `f8f20fdd8c4c51d73fe46d451e7bd47c68441c728c22a64a7c4a9ff92623791f`.** Clean-up: no `cassandra-sai` java process left; `~/stage4-sai/node` wiped; 127.0.0.5 and JMX 7205 free; logs kept in `pc07:~/stage4-logs/sai/` (124 MB); the clone `~/cassandra-sai` holds the untracked `SaiMemtableChargeTest.java`.
