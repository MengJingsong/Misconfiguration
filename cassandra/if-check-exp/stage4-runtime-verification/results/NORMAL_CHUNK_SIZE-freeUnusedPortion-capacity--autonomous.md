# NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous — stage-4 results  <!-- file: results/NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous.md -->

> **Case:** [`NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous`](../../stage3-ai-deep-read/cases/NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous.md)
>
> **Status:** verdict filed 2026-10-22. **Unit: Confirmed — does not cap. Cluster: Not confirmed (row K2b-4: the cap was never reached in a run where the check runs) — undetermined.** Run 1 only.
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e; the feedback section is the case file's section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Not committed (untracked, as filed by stage 3). sha256 as filed `af9a7512118d8b97ced5faa65874927fa68851170b36cf0fd6623750be958da5`. **Frozen after the audit's amendments (U1–U3, K1–K4): `b4a452ceeeaecb18b5b0091612d59443e48b728c364ec8c20ee2d604c5bdd94e`** (2026-10-22 04:17 EDT, before any reading; copy `pc07:~/stage4-logs/ncs/case-frozen-b4a452ce.md`). Two runbook-defect fixes to B2e followed during the unit tier: after D1 `e38add515e31dd6b0b83b216f8b0a31a9a086ee090924cda090b82de5f077995`, after D2 `fcccaef08fac920f9b13dcd2f419bc0bbb72b88252b26cbf149bbd6a7aca5afc` (this is the version both counted tiers ran). Neither fix touches a prediction or a row. The hash after section D is in §8. |
| **Harness** | `../harness/NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous/`: `FreeUnusedPortionProbeTest.java`, `unit-run.sh` (unit); `ncs.btm`, `PoolSampler.java`, `cluster-run.sh`, `all-runs.sh`, `analyze.py`, `README.md` (cluster). Not committed. The copy that ran is `pc07:~/stage4-harness-run/ncs/` (`SHA256SUMS`; each cluster run records `harness-sha256.txt`, and all five cluster runs show the same hashes). Checks before run 1: the test compiled with `javac` against the build; `ncs.btm` passed `org.jboss.byteman.check.TestScript` (parse and type check, no errors); `javap` confirmed that `LocalPool.putUnusedPortion` calls `updateOverflowMemoryUsage` directly (the `ovftrim` rule's `AT INVOKE`). |
| **Tiers and values** | Unit (B2): rows N1–N6, T1–T2, O1, and the CTL fills at 8 MiB (with and without trim) and 16 MiB. Cluster (B3): `networking_cache_size` = 4 / 8 (K4) / 16 / 128 MiB (128 = the default for a 4 GiB heap), two nodes, stress write 1.5 M and read 1 M (K3) at CL=ALL over v5. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-22 |

**What this file tests beyond the closed `networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided` case.** That case tested the pool's **admission** check (`allocateMoreChunks`, `BufferPool.java:443`): with held response frames, the pool stopped at the threshold, and the retained memory followed the knob. This file tests the **release-side** guard at `:1521` in `Chunk.freeUnusedPortion`, whose operand comes from the hard-coded `NORMAL_CHUNK_SIZE`. It tests:
- both outcomes of the guard in both slot units (2048 B and 32 B);
- that neither outcome changes the pool's reservation or the process's direct memory;
- that the free branch lets more buffers fit inside a fixed reservation (576 vs 128) without the reservation moving;
- the `OverflowSize` drift from trimming unpooled buffers (`LocalPool.putUnusedPortion` `:883-885`);
- on a node, how often each outcome fires under load at four `networking_cache_size` values.

Overlap: the cluster tier's dose-response on `networking_cache_size` repeats the guided case's question (the cap is that knob), and that case's U4 already found a −6 B-per-frame drift of `OverflowSize`. Both are noted in section D.

### 1.1 Design audit

Citations re-read against `~/cassandra-ncs` (= the tag, `git diff` against `cassandra-5.0.9` empty for `BufferPool.java`).

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: the networking pool's reserved off-heap (`memoryAllocated`) and direct memory |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly | A1: `NORMAL_CHUNK_SIZE` is a constant (no yaml, `-D` or JMX). B2b varies what it yields: the two slot units, and the guard outcome through `limit`. That approach answers "does the check cap usage" without a rebuild. A source mutant of the constant (64 / 128 / 256 KiB) was not added: it would also move `MACRO_CHUNK_SIZE` (= 64 × it), and so the cap's granularity, which is a different path (S2) |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after U2, K1 | Unit tier read only pool bookkeeping: U2 adds direct `MemoryUsed`. Cluster: direct `MemoryUsed`, RSS, and the exact slab count (K1) |
| A. Core question | usage driven to the limit and past it | Partly | Unit CTL fills to the first overflow. Cluster: B3c itself doubts that 16 MiB is reached; K4 adds 8 MiB |
| A. Core question | positive control (negative estimate) | Met | Unit CTL: threshold 8 → 16 MiB. Cluster: 4 MiB vs larger values |
| B. Logic | each step says what it establishes | Met | B1, B2g, B3g |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f exact per row; B3f per value |
| B. Logic | every plausible outcome has a conclusions row | Not met → Met after U3, K2b | Unit: O1's `dSize` would have fired the Refuted row (U1); no row for "no drift", for a failing reference test, or for "trim does not help reuse". Cluster: rows overlapped (0 / 16 / 16 with the cap binding fitted neither row 1 nor row 4); no row for "free branch never taken on the node", "drift not shown", or an invalid run; no combination rule |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after K1 | The disallow branch of the real cap (`refuse`) and the :1521 outcome were not observable on the node |
| B. Logic | alternative explanations and their controls | Met | B2h, B3h (idle baseline, 4 MiB floor, Capacity read back, fixed `MaxDirectMemorySize`) |
| C. Specific | a human can follow it from the intro and B1 | Met | |
| C. Specific | an AI can run B2–B3 without re-deriving the code path | Met | full test code and commands |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after K1, K2b | the derived `pooled` is two gauge reads (K1); the B3g row conditions were not exact |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | clone + build; stress, Byteman in the build |
| D. Runnable | workload arithmetic reaches the limit | Partly | Disk: 3 M rows × RF 2 on one host ≈ 16 GiB per run, over the ~20 GB budget (K3). Cap reachability uncertain (K4) |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `:1519-1521`, `:1543`, `:443`, `:877-891`, `:1185`, `BufferPools.java:44`, `DatabaseDescriptor.java:573-574`, `FrameEncoder.java:98-104` as cited. Off by a few lines, not load-bearing: `unit()` is `:1364-1367` (not `:1348-1351`), `roundUp(int)` `:1481-1484` (not `:1483-1486`), the overflow branch of `LocalPool.put` `:813-817` (not `:808-812`), the double-free assert `:1539` (not `:1538`) (S1) |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| U1 | O1's `dSize = −261120` (overflow counter in `Size`); "every ROW `dSize = 0`" limited to N1–T2; `sizeAfterGet` printed | Applied 2026-10-22, case file after B2f | a prediction error independent of readings: as filed, O1 fired the Refuted row by construction |
| U2 | `dDirect` per row, `directDelta` per CTL, predicted 0 and `k × (8 MiB + 4096)` | Applied 2026-10-22, after B2f; harness test | real resource |
| U3 | exact row conditions, rows for direct memory, reuse, O1 drift both ways, reference test; combination rule | Applied 2026-10-22, after B2g | outcomes without rows; HARD RULE: rows only before readings |
| K1 | exact pooled from a Byteman `made` trace; counters `refuse`, `gtrue`, `gfalse`, `gtiny`, `ovftrim`; one-connection JMX sampler; idle-tail reading of the derived `pooled` | Applied 2026-10-22, after B3d | two-moment gauge reads; :1521 and the real disallow branch unobservable |
| K2a/K2b | predictions for K1 observables and 8 MiB; exact rows 1–8 and a combination rule | Applied 2026-10-22, after B3f / B3g | overlapping and missing rows |
| K3 | write n = 1.5 M, read n = 1 M | Applied 2026-10-22, after B3c | disk budget on a shared host; no prediction depends on volume |
| K4 | add `networking_cache_size: 8MiB` | Applied 2026-10-22, after B3b | B3c doubts 16 MiB is reached; without a binding non-zero value the tier cannot confirm |
| E1 | paths `~/cassandra-ncs`, `~/stage4-ncs`, `~/stage4-logs/ncs`; nodes 127.0.0.4 (seed, JMX 7204) / 127.0.0.6 (JMX 7206) instead of .1/.2 (7199/7299); `cluster_name 'ncs-stage4'`; process checks by `cassandra-ncs` in the command line instead of `pgrep -f CassandraDaemon` | Environment deviation, not a case-file change | shared host (another stage-4 agent's SAI node on 127.0.0.5 / 7205) |
| S1 | fix the off-by-a-few line citations listed above; A1 notes `MACRO_CHUNK_SIZE` javadoc "1 MiB" is stale (correct) | Left for stage 3 | not load-bearing |
| S2 | say in A1/B1 that `NORMAL_CHUNK_SIZE` also sets the cap's granularity (`MACRO_CHUNK_SIZE = 64 ×`, so `floor(threshold / 64·NCS)` slabs) and the pooled/unpooled split (`size > NORMAL_CHUNK_SIZE` is never pooled): the constant does shape usage, only not through :1521 | Left for stage 3 | scope of the claim |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-22, 04:07–04:56 EDT (node clock; Cassandra log lines are UTC) |
| Node | `pc07` (`node0.jason92-320876`), 40 cores, 251 GiB, **shared** with another stage-4 agent's node (SAI case, 127.0.0.5 / JMX 7205), which ran stress during the cluster tier |
| OS and kernel | Ubuntu 22.04.2, `5.15.0-187-generic` |
| JDK | OpenJDK 11.0.32.1 |
| Ant | 1.10.12 |
| Local clone | `~/cassandra-ncs`, `cassandra-5.0.9` = `b5f2a54210d541339c2e7c17a794195cac0e67c2`; `ant build-test` 1 min 9 s, `BUILD SUCCESSFUL`; `git status` clean after the run |
| Case-file commit / harness commit | none (untracked; sha256 in §1) |
| Storage | `/dev/sda3` local; node data under `~/stage4-ncs/n4`, `~/stage4-ncs/n6` (3.7 GB per node per run, removed at the end of every run) |
| Node settings | two nodes, `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M`, `-XX:MaxDirectMemorySize=2g` (last on the command line, after the env script's 15872M), `ulimit -n 100000`, Byteman 4.0.20 agent with `ncs.btm` (no listener) |
| Full logs | `pc07:~/stage4-logs/ncs/` (`build-test.log`, `unit*/`, `cluster/V4 V8 V16 V128 V128-attempt1-invalid/`, `cluster/analyze-out.txt`) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file change |
|---|---|---|---|---|---|---|
| D1 | 1 (unit, attempt 1) | B2e step 1 (the listed test) | `fill()` calls `unsafeReset()` with all buffers still held. Under `-ea`, the first fill fails in `Chunk.recycleFully` ("Status of chunk … was not EVICTED", `BufferPool.java:1308`). `probeRows` passed; one CTL line printed | `fill()` keeps its buffers and `put`s them back after its CTL line, before `unsafeReset()` | 2026-10-22; attempt 1 not counted; unit tier restarted | dated note in B2e (sha `e38add51…`); B2f/B2g unchanged |
| D2 | 1 (unit, attempt 2) | B2e step 3 | the test XML holds stdout only when a test fails, so the grep found nothing (the test passed) | extract from the ant console output logged by `unit-run.sh` | 2026-10-22; attempt 2 not counted (its lines were not read); unit tier restarted | dated note in B2e (sha `fcccaef0…`) |
| V128-1 | 1 (cluster, V128 attempt 1) | B3e step 4 (stress write) | both nodes logged one 13.5 s commit-log sync and dropped messages. Stress then failed with `WriteTimeoutException` at CL=ALL after 1,151,008 of 1,500,000 writes (`write rc=1`). Before that, n4 had a 73.6 s local pause during n6's start-up. Row K2b-8 (Invalid run for that value) | none needed in the runbook: the same script ran the value again (attempt 2, valid). Attempt 1 is kept as `run1/V128-attempt1-invalid/` | 2026-10-22; attempt 1 not counted | none |

## 4. Run 1

**Scope:** both tiers, all values. **Command log:** `NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous/run1/unit/unit-run.log` (+ `unit-lines.txt`, `probe-junit.xml`, `shipped-junit.xml`); per cluster value `run1/V<v>/run.log` (+ `bm-n4.txt`, `bm-n6.txt`, `samples-n4.csv`, `samples-n6.csv`, `rss.txt`, `yaml-*.diff`, `status.txt`, `stress-*-summary.txt`, `system-*-excerpt.txt`, `t-*`); `run1/analyze-out.txt`; `run1/all-runs.log`; attempts in `run1/unit-attempt1/`, `run1/unit-attempt2/`, `run1/V128-attempt1-invalid/`.

### 4.1 Readings

**Unit tier** (`run1/unit/unit-lines.txt`; `probe-junit.xml`: tests 2, failures 0; `shipped-junit.xml`: tests 1, failures 0)

| Row | guard | capAfter | dFree | dUsed | dSize | dOverflow | dDirect | B2f / U1 / U2 |
|---|---|---|---|---|---|---|---|---|
| N1 | true | 8192 | 0 | 0 | 0 | 0 | 0 | exact |
| N2 | true | 8192 | 0 | 0 | 0 | 0 | 0 | exact |
| N3 | false | 6144 | +2048 | −2048 | 0 | 0 | 0 | exact |
| N4 | false | 2048 | +6144 | −6144 | 0 | 0 | 0 | exact |
| N5 | true | 5000 | 0 | 0 | 0 | 0 | 0 | exact |
| N6 | false | 4096 | +2048 | −904 | 0 | 0 | 0 | exact |
| T1 | true (unit 32) | 128 | 0 | 0 | 0 | 0 | 0 | exact |
| T2 | false (unit 32) | 96 | +32 | −32 | 0 | 0 | 0 | exact |
| O1 | n/a | 262144 | 0 | −261120 | −261120 | −261120 | 0 | exact |

PUT lines: `sizeBeforePut` 8388608 for N1–T2; O1 `sizeAfterGet` 8650752, `sizeBeforePut` 8389632, **`overflowAfterPut` −261120**. SHIFT: `mask = −1` (assertion passed). INFO: NORMAL_CHUNK_SIZE 131072, units 2048 / 32, MACRO 8388608, pageSize 4096.

| CTL | buffers | pooledBytes | k | directDelta | usedBytes | Prediction |
|---|---|---|---|---|---|---|
| (a) 8 MiB, no trim | 128 | 8388608 | 1 | 8392704 | 8388608 | exact |
| (b) 8 MiB, trim | 576 | 8388608 | 1 | 8392704 | 1179648 | exact |
| (c) 16 MiB, no trim | 256 | 16777216 | 2 | 16785408 | 16777216 | exact |

**Cluster tier** (`run1/analyze-out.txt`, re-derived with `grep`/`awk` in §5; per node n4 / n6; `cap` = floor(NCS/8 MiB) × 8 MiB)

| NCS | Capacity (JMX) | `k` (made lines) → P_exact | `refuse` | `gtrue` | `gfalse` | `gtiny` | `ovftrim` | idle-tail derived pooled | OverflowSize min | direct max − baseline | "Maximum memory usage reached" | stress write / read errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 4 MiB | 4194304 / 4194304 | 0 / 0 → 0 | 2,991,562 / 3,038,609 | 0 / 0 | 0 / 0 | 0 / 0 | 2,863,852 / 2,911,488 | 0 / 0 | **−14,704,894,404 / −14,471,485,709** | 1.45 / 1.40 MiB | 1 / 1 | 0 / 0 (1.5 M / 1 M) |
| 8 MiB | 8388608 ×2 | 1 / 1 → 8 MiB | 0 / 0 | 1,998,647 / 2,058,354 | 983,671 / 904,736 | 1,226,390 / 1,214,899 | 0 / 0 | 8388608 / 8388608 | 0 / 0 | 1.42 / 1.28 MiB | 0 / 0 | 0 / 0 |
| 16 MiB | 16777216 ×2 | 1 / 1 → 8 MiB | 0 / 0 | 2,029,359 / 2,012,692 | 909,664 / 958,418 | 1,193,372 / 1,214,187 | 0 / 0 | 8388608 / 8388608 | 0 / 0 | 1.37 / 1.31 MiB | 0 / 0 | 0 / 0 |
| 128 MiB | 134217728 ×2 | 1 / 1 → 8 MiB | 0 / 0 | 2,014,716 / 2,016,634 | 938,013 / 943,337 | 1,201,210 / 1,211,411 | 0 / 0 | 8388608 / 8388608 | 0 / 0 | 1.31 / 1.29 MiB | 0 / 0 | 0 / 0 |

Other readings:
- In every run with NCS ≥ 8 MiB, the single slab was made about 104 s **before** the write phase (node start-up and gossip), and none during load.
- JMX `Misses` equals `refuse` exactly at 4 MiB (2,991,562 / 3,038,609) and is 0 elsewhere; `Hits` is 2.5–3.1 M per node.
- `UsedSize > Size` while `OverflowSize = 0`: never.
- At 4 MiB the derived `pooled` reached 430,685 / 914,927 B in single samples under load, though no slab existed. This is the two-moment effect that K1 anticipated; idle-tail 0.
- RSS max 5.49–5.60 GiB in every run.
- Stress write 12.9–15.6 k op/s, read 49–53 k op/s.
- V128 attempt 1 (invalid, §3) also had `k = 1`, `refuse = 0`.

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — [observed: `unit/probe-junit.xml`, `unit/unit-run.log`] both probe tests and the shipped reference test passed. The CTL fills reached the first overflow ("Maximum memory usage reached (8.000MiB) for ctl buffer pool" in the attempt-1 log; in the counted run each CTL line follows its overflow). Both guard outcomes occurred in both units. Valid.
2. **Readings** — nothing unusual; every value equals B2f / U1 / U2 exactly [observed: `unit/unit-lines.txt`].
3. **Matched rows** — U3's combination: row 1 ("N1–N6, T1–T2 have `dSize = 0`; guard true ⇒ dFree = 0; guard false ⇒ dFree = capacity − size") holds: 8/8 rows `dSize = 0`, dFree 0 for the four true rows, 2048 / 6144 / 2048 / 32 = capacity − size for the four false rows. Row 3 holds: `buffers(b) = 576 > buffers(a) = 128`, `pooledBytes(a) = pooledBytes(b) = 8388608`, `pooledBytes(c) = 16777216`. Every `dDirect` is 0, the shift assertion passed (`mask = −1`), and the shipped test passed [observed: same files]. Secondary row: "O1 `overflowAfterPut = −261120`, `capAfter = 262144`, `dDirect = 0`: confirms the A3 accounting defect exactly" [observed].
4. **Excluded rows** — Refuted (`dSize ≠ 0` in N1–T2, or guard-true with dFree ≠ 0): none. Refuted (`abs(dDirect) ≥ 2048`, or `abs(directDelta(b) − directDelta(a)) ≥ 1 MiB`): all `dDirect` 0, and (a) = (b) = 8,392,704. Refuted (`pooledBytes` with trim > 8 MiB): 8,388,608. Not confirmed (positive control did not move): 8 → 16 MiB moved. Not confirmed (no `guard=false`): four false rows. Not confirmed (trim does not help reuse): 576 > 128. Not confirmed (reference failed): passed. "O1 `overflowAfterPut = 0`": −261120.
5. **Observed vs. inferred** — nothing the conclusion uses is inferred. `dDirect` reads the JVM's direct-memory accounting (`Bits.reserveMemory`), not RSS. That is the right resource for direct buffers, but it is still a JDK counter.
6. **Deviations and gaps** — fixes D1 and D2 (attempts 1 and 2 not counted); path deviation E1.
7. **Core question** — the guard at :1521 decides only whether whole slots of an already-reserved chunk are marked free (parts 3, 4). Neither outcome changes `memoryAllocated` or direct memory, in either unit (part 3: `dSize = 0`, `dDirect = 0`). The free outcome makes the same 8 MiB reservation serve 4.5× as many 64 KiB requests, while the reservation moves only with the threshold (8 → 16 MiB, `directDelta` 8.39 → 16.79 MB) (part 3, row 3). The check does not cap usage; `memoryUsageThreshold` does.

**Conclusion (unit, one line):** U3 combination → rows 1 and 3 — **confirmed** (the claim held); the A3 drift confirmed exactly (secondary).

**Cluster tier**

1. **Validity** — [observed: `V*/run.log`, `V*/status.txt`, `V*/stress-*-summary.txt`, `V*/samples-*.csv`] For every counted value:
   - both nodes were UN;
   - the `Global buffer pool limit is … <v>MiB for networking` line was logged and JMX `Capacity` equalled v MiB;
   - stress completed 1.5 M writes and 1 M reads with 0 errors at CL=ALL.

   Row 8 does not fire, and every run is valid. V128 attempt 1 was invalid (row 8) and is not counted (§3).
2. **Readings** — (a) At 8, 16 and 128 MiB the pool made exactly one slab, at start-up, and never asked for another (`refuse = 0`): about 3 M pooled requests per node were served from 64 normal chunks [observed: `bm-*.txt`]. (b) The derived `pooled` under load is not exact (4 MiB samples up to 0.9 MB with no slab) [observed], which is why K1 reads `P_exact`. (c) At 4 MiB, `OverflowSize` fell from −0.34 / −0.57 MB at the baseline to −14.7 / −14.5 **GB**, while direct memory rose by only 1.45 / 1.40 MiB [observed: `samples-*.csv`]. This is about 5.0–5.1 kB per overflow trim (OverflowSize / `ovftrim`) [inferred: arithmetic; the per-trim sizes are not traced].
3. **Matched row** — **K2b row 4: "Rows 2, 3, 5 and 8 do not fire, but no 8MiB or 16MiB run has `refuse > 0` with `P_exact = cap(v)` — Not confirmed: the cap was never reached where the check runs."** In the 8 MiB run `P_exact = 8 MiB = cap`, but `refuse = 0` on both nodes. In the 16 MiB run `P_exact = 8 MiB < 16 MiB` and `refuse = 0` [observed: `V8/bm-*.txt`, `V16/bm-*.txt`]. Under the frozen combination rule, rows 5, 4 and 6 are checked in that order and the first that fires decides: row 5 does not fire, and row 4 does. Secondary: the last B3g row ("`OverflowSize` < 0 in the 4MiB run while java.nio `MemoryUsed` stays bounded — confirms the A3 accounting defect") matches [observed].
4. **Excluded rows** — Row 2 (**Refuted**, `P_exact > cap`, or idle derived > cap + 1 MiB): `P_exact` 0 / 8 / 8 / 8 MiB against caps 0 / 8 / 16 / 128; idle derived 0 / 8388608 ×3. Row 3 (**Refuted as traced**, a slab released): the idle derived `pooled` equals `P_exact` exactly in every run. Row 5 (positive control failed): 4 MiB had `k = 0` and `refuse` = 2.99 / 3.04 M. Row 6 (`gfalse = 0` everywhere ≥ 8 MiB): `gfalse` 0.77–0.98 M per node per run. Row 8 (Invalid): see part 1. Row 1 (Confirmed): needs a binding run at 8 or 16 MiB, which did not happen. Row 7 (drift not shown): `OverflowSize` < 0 in all 47 samples at 4 MiB on both nodes. The original B3g rows replaced by K2b are covered by the same readings.
5. **Observed vs. inferred** — the matched row rests on observed counts (`made` lines, `refuse` on the dump lines). Inferred: the ~5 kB per overflow trim (2.c), and that the `g*` counters belong to the networking pool. The second follows from the source (every `putUnusedPortion` caller uses `forNetworking()`) and is consistent with `ovftrim` and `gtrue + gfalse` both counting the same callers.
6. **Deviations and gaps** — E1 (loopback .4/.6, JMX 7204/7206, shared host with another agent's node and stress); K3 smaller volume; V128 attempt 1 invalid and repeated. Missed sub-predictions: K2a "8 MiB: `refuse > 0` expected" (0 on both nodes); B3f "`MemoryUsed − baseline ≥ pooled`" is uninformative, because the slab was made before the baseline. Every other B3f/K2a sub-prediction held: k order 0 ≤ 1 ≤ 1 ≤ 1; Capacity; idle derived = `P_exact`; OverflowSize 0 at 128 MiB; `UsedSize ≤ Size`; 4 MiB pooled 0 with the log line. **Gap:** a workload (or a smaller `networking_cache_size`, below one slab's worth of chunk demand) that makes the local pools want more than 64 chunks at once was not run, so no run with the check active had the cap binding.
7. **Core question** — the check at :1521 ran about 2.9–3.0 M times per node per run with NCS ≥ 8 MiB, and took the slot-freeing branch about a third of the time (part 4). The pool's reservation stayed exactly one 8 MiB slab, and direct memory moved by about 1.4 MiB whatever the outcome (parts 2, 4). This is consistent with B1, but the frozen table requires the real cap to bind in such a run, and it never did (part 3). So the cluster tier cannot say that usage holds at the cap with the check active. The 4 MiB floor shows the cap binding only where the check is never reached.

**Conclusion (cluster, one line):** K2b row 4 — **not confirmed** (the cap was never reached where the check runs); A3 drift confirmed (secondary).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-read `run1/V{4,8,16,128}/stress-*-summary.txt` (`Total errors : 0`, 1,500,000 / 1,000,000), `status.txt` (2 × UN), `system-n*-excerpt.txt` (limit lines 4 / 8 / 16 / 128 MiB) and the Capacity column of `samples-*.csv` (`awk`, one unique value per run). `V128-attempt1-invalid/stress-write-summary.txt` shows `FAILURE` and 7,509 `WriteTimeoutException` lines; its `system-n*-excerpt.txt` shows the 13.5 s commit-log sync. |
| 2. Readings | yes | `grep -c '^made'`: 0 / 1 / 1 / 1 per node, and `sort | uniq -c` shows each `made n=1` once, at ms values about 104 s before `t-start-write`. The last `dump` lines match §4.1 digit for digit. `OverflowSize` min from `awk` matches (−14,704,894,404 / −14,471,485,709). JMX `Misses` at 4 MiB equals `refuse`. |
| 3. Matched row | yes | Row 4's condition re-checked from the dump lines: V8 `refuse=0` on both nodes, V16 `refuse=0` and `made=1`. Rows 2, 3, 5 and 8 checked as not firing (part 4). The combination order is the frozen one (K2b, sha `b4a452ce…`, unchanged since). |
| 4. Excluded rows | yes | each row checked against the same raw numbers. The Refuted rows are addressed: `P_exact ≤ cap` everywhere; idle derived = `P_exact`. |
| 5. Observed vs. inferred | yes | the verdict uses only observed counts; the two inferences are labelled and do not carry it |
| 6. Deviations and gaps | yes | the other agent's node was running (`ps`: one `CassandraDaemon` plus stress with `jmx=7205`, not ours); our processes were matched by `cassandra-ncs` only |
| 7. Core question | yes | the answer follows the frozen logic and does not claim Confirmed from the consistent but non-binding runs |

Unit tier: re-read `run1/unit/unit-lines.txt` against B2f, U1 and U2 line by line: 9 ROW lines, 9 PUT lines, SHIFT, and 3 CTL lines, all as in §4.1. `probe-junit.xml` shows `tests="2" failures="0" errors="0"`, and `shipped-junit.xml` `tests="1" failures="0"`.

**HARD RULE check:** every row and prediction was written in the step-0 audit (sha `b4a452ce…`, 04:17 EDT), before the first unit reading (attempt 1 at 04:17:39 UTC−4 = 08:17:39 UTC in the test log, after the freeze). D1 and D2 changed only the B2e procedure. No row or prediction was added or changed after any reading.

### 5.2 Run 2?

**No** — 2026-10-22. The unit conclusion is exact and observed. The cluster conclusion is a Not confirmed that rests on observed counts. A run 2 of the same runbook would not reach the cap either, because the demand is set by the workload, not by the session. What would settle the cluster tier is a different design (gap in §4.2 part 6), which is stage-3 feedback.

## 6. Run 2

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative.

**Claim tested (B1):** the check at `BufferPool.java:1521`, whose operand `capacity` comes from `NORMAL_CHUNK_SIZE`, does **not** cap memory. Whatever its outcome, the networking pool's reserved off-heap (`memoryAllocated`) is unchanged by the call. The pool's ceiling is set only by `memoryUsageThreshold` (`networking_cache_size`), in whole 8 MiB macro chunks.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — U3 combination: B2g rows 1 and 3 (every prediction exact; `dSize = 0` and `dDirect = 0` on both outcomes in both units; 128 vs 576 buffers in the same 8 MiB, 8 → 16 MiB with the threshold) | does not cap | run 1 + self-check | 2026-10-22 |
| Cluster | **Not confirmed** — K2b row 4: the cap was never reached in a run where the check runs (one slab made at start-up at 8 / 16 / 128 MiB, `refuse = 0`; :1521 ran about 2.9 M times per node per run, a third of them freeing slots) | undetermined | run 1 + self-check | 2026-10-22 |

**Positive control:** unit, the threshold 8 → 16 MiB moved `pooledBytes` 8,388,608 → 16,777,216 and `directDelta` 8,392,704 → 16,785,408 with the same workload. Cluster, at 4 MiB the pool made no slab and refused 2.99 / 3.04 M chunk requests ("Maximum memory usage reached (4.000MiB)"), against one slab at 8 / 16 / 128 MiB. The cluster control moved, but only between "no pooling" and "one slab".

**Secondary finding (A3 accounting defect), both tiers:**
- Unit: one trimmed 256 KiB overflow buffer left `OverflowSize` at exactly −261,120 after its release, with no memory freed.
- Cluster at 4 MiB: about 2.9 M overflow trims per node drove `OverflowSize` (and so `Size`) to **−14.7 / −14.5 GB** over about 2 minutes of load, while direct memory rose 1.4 MiB.

When the pool is exhausted, `Size` and `OverflowSize` are meaningless as usage figures. The closed guided `networking_cache_size` case recorded −6 B per frame on its CRC response path; here the per-trim average is about 5 kB (inferred), so FrameDecoder and internode trims dominate.

**Feedback filed:**
- The case file's section D (2026-10-22).
- The dated audit amendments U1–U3 and K1–K4, and the runbook-defect fixes D1 and D2, next to the text they change.
- Case-file sha256 after section D: `72a15084e82cfb7881e3856e1815b988295100ce7ddc0d9bad44fd071903e8da` (for `_INDEX.md` §4, filled by the orchestrator).

Not committed.

**Node state after the run:**
- No `java` process matching `cassandra-ncs`.
- `~/stage4-ncs` holds 756 KB of configuration only (data removed after every run).
- Kept: `~/cassandra-ncs` (443 MB, clean, test file removed) and `~/stage4-logs/ncs` (67 MB).
