# native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous — stage-4 results

> **Case:** [`native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous`](../../stage3-ai-deep-read/cases/native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous.md)
> (target `PreV5Handlers.java:127`, the unpause condition in `LegacyDispatchHandler.releaseItem`; from `predicted-negative.md` §9)
>
> **Status:** verdict filed (run 1 at both tiers + self-check; no run 2) — 2026-10-22
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster), "§9b–§9e" means B2a–B2e or B3a–B3e, and the
> case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Not committed (untracked file; repo HEAD `64f23ca`). sha256 **as filed** `c60e0fd5e18f9e7240d2a5e850cfab2535f9f3047cc48154c4c01cef6572dbd9`; **frozen after the step-0 audit** (2026-10-22 04:20 EDT) `7c7fa7a839d0d1568564436569197db31eff1d70fa9becbdd793f5684ad80ebd`; **after runbook fix D1** (step 1, before either tier's run 1; B2f/B2g/B3f/B3g unchanged) `f0f7942d101f81e2917547359c5727aa94003e3fbff9de13da0a2a718b92a451` — both tiers' run 1 used this version. Final (after section D): see §8. |
| **Harness** | `harness/native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous/` (not committed): `PreV5InflightCapTest.java` (the B2e test, one import added, H1), `InflightProbe.java` and `v4load.py` (B3a, verbatim), `unit-run.sh`, `cluster-run.sh` (B3e steps 1–9 for one run), `cluster-all.sh` (the seven runs), `reduce.py` (B3e step 9). Run copies with `SHA256SUMS` in `pc12:~/stage4-harness-run/pv5/`. |
| **Tiers and values** | Unit: L = 1e6 / 4e6 / 16e6 B (U-A), C = 1 / 8 / 64 (U-B), U-C, controls U-D (throw) and U-E (L = 1e12). Cluster: L = 64MiB, 256MiB, **default (heap/10, added by the audit)**, 4GiB at C = 1; 64MiB at C = 32; 64MiB THROW=1 control; 4GiB periodic-commitlog control. 1024 × 1 MiB INSERTs per run. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-22 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: request-body bytes (pooled direct `ByteBuf`s) accounted by `bodySizeInBytes`. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly → Met after R2 | B3b had 64MiB / 256MiB / 4GiB, not the default (heap/10). R2 adds a default run. Unit tier uses three non-default L plus an unlimited control (left: unit tier tests the mechanism). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B3d: BufferPool direct MXBean (with `-Dio.netty.maxDirectMemory=0`), NMT "Other", heap; gaps named (pool slack, chunk granularity, unaccounted header/heap copies). Unit tier counter only, stated. |
| A. Core question | usage driven to the limit and past it | Met | 1024 × 1 MiB ≫ 64/256 MiB; U-A sends to L/S + 1, U-C past it. |
| B. Logic | each step says what it establishes | Met | B2c/B3e with B2h/B3h controls. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f exact; B3f bands [L, L + 2S], orderings. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → Met after R3, R4 | B2g had no verdict words, no U-C row, no row for "follows L with a different overshoot"; B3g had no verdict words, no default row, no instrument-blind row, and its `other_err` row asked for a re-run. R3/R4 add the verdict lines U1–U5 and C1–C7. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | U3 needs `unpausedAfterCompletions` = 2 and `unpausedWhileGlobalAboveLimit` = true (both disjuncts of `:127`); C5 needs bands per L plus Δdirect ordering; `paused` observed. |
| B. Logic | alternative explanations and their controls | Met | U-D/U-E, THROW=1, 4GiB, periodic control, idle baseline. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate line, B1, A3 step 5. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met | Code given in full; one compile error (H1). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after R1, R5 | Paths (`/tmp/s3-inflight`) and process checks (`pgrep -f`) did not fit the node; probe duration too short for the real completion rate. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | B2a/B3a; build in step 1. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly → Met after R5 | B3c assumed completion of "L per 10-s window"; with `concurrent_writes` = 32 each blocked in `awaitDiskSync`, completion is ≈ 32 writes per window, so a run lasts ≈ 320 s and requests wait far past `write_request_timeout` 30 s / `native_transport_timeout` 60 s. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met (one shift) | `:127`, `:106`, `:110`, `ResourceLimits.java:130-144,156-172,263-287`, `Config.java:296-298`, `DatabaseDescriptor.java:649-657`, `StorageService.java:7044-7054`, `CBUtil.java:60` as cited; `:176/:181/:182` are `:179/:184/:185` (R6). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Environment: `pc12`, clone `~/cassandra-pv5`, data `~/stage4-pv5/data`, logs `~/stage4-logs/pv5`, tools `~/stage4-harness-run/pv5`; detect the node by `java` + clone path; `ulimit -n 100000`; wait for `UN` and `statusbinary` | Applied 2026-10-22 (B2a, B3a, B3e amendments) | the filed paths and `pgrep -f` do not fit the node / lessons |
| R2 | Add the default value: global unset (heap/10), per-IP pinned to 858993459B, prediction [D, D + 2S] | Applied 2026-10-22 (B3b, B3f) | the audit requires the default among the values |
| R3 | Unit verdict lines U1–U5 | Applied 2026-10-22 (after B2g) | B2g gave meanings, not verdicts; U-C and "different overshoot" had no row |
| R4 | Cluster verdict lines C1–C7; THROW Δdirect rows; periodic row; instrument-blind row; `other_err` row without a re-run | Applied 2026-10-22 (after B3g) | as R3; and a post-reading re-run is not allowed |
| R5 | `write_request_timeout` and `native_transport_timeout` 600000ms; probe 480 s; corrected completion arithmetic | Applied 2026-10-22 (B3a, B3c, B3e) | ≈ 3.2 writes/s ⇒ ≈ 320 s per run; filed timeouts would turn the 4GiB/default runs into timeouts |
| R6 | A3 line citations `:176/:181/:182` → `:179/:184/:185` | Applied 2026-10-22 (A3) | wrong citations, not load-bearing |
| R7 | THROW=1 control Δdirect not predicted ≤ the T0 run: the pre-V5 throw path never releases a rejected request's envelope (`:157-159`, `:239-252`) | Applied 2026-10-22 (A3 note, B3f, B3g) | source-level; the filed prediction would otherwise be a predictable miss |
| R8 | The unit tier's L values do not include the default; a unit arm at heap/10 of the test JVM | Left for stage 3 | the unit tier tests mechanism exactness; the default is covered at the cluster tier |

**Freeze.** sha256 after the audit `7c7fa7a8…80ebd` (above), recorded before any step-1 check or run.

**Step 1 — instruments (2026-10-22, before any tier run).**

| Check | Result | Evidence |
|---|---|---|
| Fresh clone `~/cassandra-pv5` (cloned from `~/cassandra-run1`), `git checkout cassandra-5.0.9` = `b5f2a54210d5…`; `ant build-test </dev/null` | BUILD SUCCESSFUL, 1 min 7 s | `pc12:~/stage4-logs/pv5/clone-build.log` |
| Unit harness compiles as written | **No** — `package ErrorMessage does not exist` (missing `import org.apache.cassandra.transport.messages.ErrorMessage`). Harness fix H1: one import line, no production class touched; then compiles | `pc12:~/stage4-logs/pv5/step1-unit-compile{,2}.log` |
| Assumption 1: `-Dio.netty.maxDirectMemory=0` makes Netty's pool visible in the direct BufferPool MXBean | **Holds.** Source: Netty 4.1.130 `PlatformDependent.<clinit>` sets `USE_DIRECT_BUFFER_NO_CLEANER = false` when the property is 0 (javap). Check A (flag on, 4GiB, 64 requests): direct `MemoryUsed` 100.5 MB idle → 1,056.8 MB. Check B (flag **off**, periodic): MXBean Δ = 0 B while NMT "Other" rose 116 MiB over its baseline — without the flag the pool is invisible to the MXBean, as the case says | `run1/step1/step1-checkA-flag-group/`, `run1/step1/step1-checkB-noflag-periodic/` |
| Assumption 2: the unit harness runs as written | After H1, yes (5 tests, 0 failures, 0 errors in run 1) | `run1/unit/unit-run.log` |
| Group-commit hold (B3a rationale) | **Not as written (defect D1).** Check A: 64 writes in 0.41 s. Cause: each 32 MiB segment switch calls `commitLog.requestExtraSync()` (`AbstractCommitLogSegmentManager.java:334`). Fix: `commitlog_segment_size: 1536MiB`; check B then showed a 1.6 GB idle direct baseline (the hint buffer slab sized from the implied `max_mutation_size` 768 MiB), so the fix also pins `max_mutation_size: 16MiB` (the shipped effective value). Check C (fixed config, 4GiB, 64 requests): 12.5 s for 64 writes (two 10-s windows), idle direct 100.5 MB, NMT "Other" base 95.9 MiB | `run1/step1/step1-checkC-flag-group-seg1536/` |
| Node start under group commit | `UN` + binary after 418–419 s (each system write waits for a 10-s sync); schema setup ≈ 74 s | `pc12:~/stage4-logs/pv5/cluster/step1-*/run.log` |
| `InflightProbe` compiles; `reduce.py` parses; scripts `bash -n` | yes | `pc12:~/stage4-harness-run/pv5/SHA256SUMS` |

The three step-1 checks used 64 requests at L = 4GiB (no limit binding); they are instrument checks, not tier readings, and no
prediction or row was changed after them. D1 changes a hold-fixed setting so that B3a's stated mechanism (each write held up to
10 s) holds; B3f and B3g are unchanged.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-22 (unit 04:49 EDT; cluster from 04:52 EDT) |
| Node (CloudLab name and type) | `pc12` = `node1.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB, no LAN interface (loopback only) |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` |
| JDK (`java -version`) | OpenJDK 11.0.32.1 (2026-08-18) |
| Ant (`ant -version`) | 1.10.12 |
| Local `cassandra-src` clone commit | `~/cassandra-pv5`, `cassandra-5.0.9`, `b5f2a54210d541339c2e7c17a794195cac0e67c2` |
| Case-file commit / harness commit | not committed; case-file sha256 `f0f7942d…a451` (§1); harness sha256s in `pc12:~/stage4-harness-run/pv5/SHA256SUMS` |
| Storage for node data | `/dev/sda3` local ext3, 54 GB free; `~/stage4-pv5/data` |
| Full logs (path, outside the repo) | `pc12:~/stage4-logs/pv5/` (`unit/`, `cluster/<run>/`) |

Node JVM: G1, `-Xms8G -Xmx8G`, `-XX:MaxDirectMemorySize=15872M` (set by `cassandra-env.sh`), `-Dio.netty.maxDirectMemory=0 -XX:NativeMemoryTracking=summary`.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| H1 | step 1 | B2e (test source) | missing import of `ErrorMessage` — the test does not compile | add `import org.apache.cassandra.transport.messages.ErrorMessage;` (harness only) | 2026-10-22 | harness only (B2e allows harness fixes) |
| D1 | step 1 | B3a (yaml) | the group-commit hold releases all writes at each 32 MiB segment switch (`AbstractCommitLogSegmentManager.java:334`), so 1 MiB writes are not held | `commitlog_segment_size: 1536MiB`, `max_mutation_size: 16MiB` in every run | 2026-10-22, before any cluster-tier run; B3f/B3g unchanged | `f0f7942d…a451` |
| H2 | step 1 | B3e step 1 (script) | the port check ran 6 ms after the previous node exited and found 7199 still bound (check C attempt 0, no node started) | wait up to 60 s for the ports before failing | 2026-10-22 | harness only |
| — | run 1 | — | none: both tiers ran as written at version `f0f7942d…a451` | — | — | — |

## 4. Run 1

**Scope:** unit tier (all five tests) and cluster tier (all seven runs: r1 64MiB-C1, r2 256MiB-C1, r3 default-C1, r4 4GiB-C1,
r5 64MiB-C32, r6 64MiB-C1 THROW=1, r7 4GiB-C1 periodic). **Command logs:** `run1/unit/unit-run.log`,
`run1/cluster/<run>/run-log-excerpt.txt` (the full logs, CSVs, NMT samples and node logs are in `pc12:~/stage4-logs/pv5/`).
S = 100,000 B (unit) and 1,048,634 B (cluster). The session stopped once on the API session limit while r6 was running; the
driver script (`cluster-all.sh`) ran on unattended and finished r6 and r7 as scripted; nothing was re-run or changed.

### 4.1 Readings

**Unit tier** (`run1/unit/U-lines.txt`; 5 tests, 0 failures, 0 errors)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| U-A, L = 1e6 / 4e6 / 16e6 | `admitted` 11 / 41 / 161; `peak` 1,100,000 / 4,100,000 / 16,100,000 (= L + S); `unpausedAfterCompletions` 2 / 2 / 2; `final` 0 | `run1/unit/U-lines.txt` |
| U-B, L = 1e6, C = 1 / 8 / 64 | `peak` 1,200,000 / 1,900,000 / 7,500,000 (= L + S + C·S); `pausedB` = C; `maxDuring100Cycles` = `peak`; `unpausedWhileGlobalAboveLimit` true at every C; `afterDrain` 0 ×3 | same |
| U-C | `usage` 5,000,000, `chan` 5,000,000, `autoRead` false | same |
| U-D (throw control) | `admitted` 10, `rejected` 10, `maxUsage` 1,000,000 | same |
| U-E (unlimited control) | `usage` 20,000,000, `autoRead` true | same |

**Cluster tier** (`run1/cluster/<run>/summary.txt`, recomputed from the full CSVs in `run1/selfcheck.txt`; Δdirect = peak
BufferPool direct `MemoryUsed` − median of the 10-s idle baseline; NMT = peak "Other" committed − its baseline sample)

| Capacity value | Run | Peak `RequestsSize` (B) | = n·S | `paused` max | Δdirect (MiB) | NMT Δ (MiB) | Peak heap (MiB) | Client ok / overloaded / other | Run time |
|---|---|---|---|---|---|---|---|---|---|
| 64MiB (L = 67,108,864) | r1 C1 T0 | 67,112,576 (L + 3,712) | 64 | 1 | 1,233.0 | 1,232.0 | 2,818.5 | 1024 / 0 / 0 | 312.4 s |
| 256MiB (268,435,456) | r2 C1 T0 | 268,450,304 (L + 14,848) | 256 | 1 | 1,872.0 | 1,872.0 | 3,043.1 | 1024 / 0 / 0 | 312.4 s |
| default (D = 858,993,459, JMX) | r3 C1 T0 | 859,879,880 (D + 886,421) | 820 | 1 | 3,010.0 | 2,992.0 | 3,072.0 | 1024 / 0 / 0 | 312.4 s |
| 4GiB | r4 C1 T0 | 1,053,877,170 | 1005 | 0 | 3,264.0 | 3,264.0 | 3,072.0 | 1024 / 0 / 0 | 312.4 s |
| 64MiB | r5 C32 T0 | 99,620,230 (L + 32,511,366) | 95 | 32 | 1,472.5 | 1,472.5 | 3,026.4 | 1024 / 0 / 0 | 312.4 s |
| 64MiB | r6 C1 THROW=1 | 66,063,942 (≤ L) | 63 | 0 | 3,182.0 (3,040 at the end, `RequestsSize` 0) | 3,134.0 | 1,810.5 | 95 / 929 / 0 | 22.2 s |
| 4GiB, periodic | r7 C1 T0 | 10,486,340 | 10 | 0 | 577.0 | 576.0 | 2,608.0 | 1024 / 0 / 0 | 2.5 s |

Idle direct baseline 100.5 MB in every run; NMT "Other" baseline 95.9 MiB. Every node reached `UN` + binary in 418–419 s
(group) or 44 s (periodic); the knob read back as L (and D for r3); 0 `LEAK:` lines; one `ERROR` per run, the shutdown
hook's drain timeout after `kill` (after the probe ended), not during the workload.

### 4.2 Conclusion and logic

1. **Validity.** Unit: both controls valid — U-E moved the operand linearly (200·S) with no cap, U-D refused exactly 10
   **[observed: `run1/unit/U-lines.txt`]**. Cluster: the limit was reached in every limited run (peaks ≥ L, `paused` = 1 or 32)
   **[observed: `run1/cluster/r1…r5/summary.txt`]**; the hold worked (each group run took 312.4 s, 4GiB peak 1,005 MiB)
   **[observed]**; hold-fixed settings confirmed from each run's `yaml.diff` and the JVM argument lines in `run-log-excerpt.txt`
   (`-Xmx8G`, G1, `-Dio.netty.maxDirectMemory=0`, segment 1536MiB, `max_mutation_size` 16MiB, timeouts 600 s) **[observed]**.
   Both tiers valid.
2. **Readings.** Every peak `RequestsSize` is an exact multiple of S **[observed: `run1/selfcheck.txt`]**. Δdirect is 7–19 ×
   the accounted bytes in the limited runs: a least-squares line over r1–r4 gives Δdirect ≈ 1,207 MiB + 2.12 × peak
   `RequestsSize` (residuals ≤ 122 MiB) **[inferred: fit of the four readings]**. The step-1 check at L = 4GiB with only 64 requests
   already showed 912–1,120 MiB **[observed: `run1/step1/*/summary.txt`]**, so about 1.1–1.2 GiB of the pool growth does not
   depend on L. The direct memory stays after the drain (r1 1,024 MiB, r4 1,248 MiB) — the pool keeps its chunks **[observed]**.
3. **Matched rows.** Unit **U3**: `admitted` = L/S + 1, `peak` = L + S, `unpausedAfterCompletions` = 2 at all three L; U-B
   `peak` = L + S + C·S, stable over 100 cycles, `unpausedWhileGlobalAboveLimit` true at C = 1, 8, 64; U-C 5,000,000 with
   `autoRead` false — every clause holds **[observed: `run1/unit/U-lines.txt`]**. Cluster **C5**: peaks in [L, L + 2S] for r1
   (L + 3,712) and r2 (L + 14,848), r3 in [D, D + 2S] (D + 886,421 ≤ 2S = 2,097,268); Δdirect ordered 1,233 < 1,872 < 3,264
   MiB; C32 peak 99,620,230 ≥ C1 peak + 4S = 71,307,112 **[observed: `run1/selfcheck.txt`]**.
4. **Excluded rows.** U1: controls valid. U2 (Refuted): peak changes with L (1.1e6 → 16.1e6), `admitted` = L/S + 1, no
   growth over cycles. U4/U5: U3 applies. C1: 4GiB peak 1,005 MiB ≥ 256 MiB; THROW overloaded 929 > 0 and peak 63·S ≤ L.
   C2: Δdirect(4GiB) 3,264 ≥ 0.5 × 1,005 MiB. C3 (Refuted): RS(64)/RS(4GiB) = 0.064 < 0.9; RS ordered; Δdirect ratio 0.378 < 0.8.
   C4 (bypass): every peak within its band, C32 ≤ L + 2·C·S = 134,221,440. C6/C7: C5 applies.
   Added rows: THROW Δdirect 3,182 MiB ≫ the T0 run's 1,233 and ≥ 0.5 × 929 × S = 464.5 MiB ⇒ the "throw path leaks" row
   (separate finding, not B1). Periodic: peak 10 MiB ≪ 1,005 MiB ⇒ accumulation comes from the hold, as filed.
5. **Observed vs. inferred.** The verdict rests on observed values only (peaks, ordering, paused, client counts). Inferred:
   (a) the ~1.2 GiB L-independent part of Δdirect is pool slack — 16 MiB chunks in many of Netty's direct arenas touched by the
   `Native-Transport-Requests` threads that encode responses (`PreV5Handlers.java:95`) — not observed (no allocator
   metrics); (b) the THROW run's retained 3,040 MiB is the rejected envelopes' pinned buffers (A3 note), not ordinary pool
   retention — consistent (r1 kept 1,024 MiB after a run with no rejections) but not directly observed (0 `LEAK:` lines; the leak
   detector samples only a fraction of buffers and reports on GC).
6. **Deviations and gaps.** H1, D1, H2 (§3), all before any tier reading. Missed sub-predictions (do not change the row):
   Δdirect bands — r1 ≤ ~165 MiB (1,233), r2 [256, ~550] (1,872), r5 ceiling ~770 (1,472.5); the B1 sentence "pooled direct
   memory follows within ≤ 2× plus 16 MiB pool-chunk granularity" is therefore wrong in its offset (slope ≈ 2.1 holds,
   offset ≈ 1.2 GiB). Hits: paused counts, ok = 1024 and `other_err` = 0, THROW several hundred overloaded with ok + overloaded =
   1024, periodic far lower, C32 expected ≥ L + 8 MiB (L + 31 MiB), C32 Δdirect well below the 4GiB run. The run used one host
   for client and node (as designed). The session paused during r6; the script was unaffected.
7. **Core question.** The accounted in-flight request bytes follow the knob exactly: peak = (⌊L/S⌋ + 1)·S at 64 MiB, 256 MiB
   and the default heap/10, and 1,005 MiB with no binding limit (parts 1, 3). Line 127 does what the trace says: a paused
   connection stays paused at using = L and resumes at L − S, and resumes on reaching zero own bytes while the global count is
   above L, so each extra connection adds exactly one request (95·S at C = 32) (parts 3, 4). Direct memory rises with the knob
   at ≈ 2.1 × the accounted bytes but on top of a ≈ 1.2 GiB L-independent pool overhead (parts 2, 5). So the constraint caps
   retained request memory, as a soft cap whose overshoot is one request per connection.

**Conclusion (one line):** unit **U3 — confirmed**; cluster **C5 — confirmed**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `run1/unit/unit-run.log` (5 tests, 0 failures); each `run1/cluster/<run>/run-log-excerpt.txt` shows the knob read-back, JVM args, `yaml.diff` the D1 lines; U-D/U-E lines re-read |
| 2. Readings | yes | `run1/selfcheck.txt` recomputed every peak and Δdirect from the full `run.csv`/`base.csv` on the node, independently of `reduce.py`; identical values |
| 3. Matched row | yes | U3 clauses checked line by line against `U-lines.txt`; C5 clauses printed true in `selfcheck.txt` (bands, ordering, C32 ≥ C1 + 4S) |
| 4. Excluded rows | yes | C1–C4 conditions printed false/true as stated in `selfcheck.txt`; U2 excluded by the U-A lines |
| 5. Observed vs. inferred | yes | the two inferred statements (pool slack, throw-path leak) are not used by U3 or C5; they are labelled findings |
| 6. Deviations and gaps | yes | defects all before readings; frozen hash `7c7fa7a8…` vs run version `f0f7942d…` differ only by the D1 paragraph (diff checked); no row or prediction changed after any reading |
| 7. Core question | yes | follows the B1 logic: ceiling follows L (unit exact, cluster bands), disallow evidence (`paused`, `autoRead` false, `unpausedAfterCompletions`), overshoot ∝ C |

### 5.2 Run 2?

**No** (2026-10-22). Both verdicts rest on observed, exact readings (integer multiples of S) that the self-check recomputed from
raw files; the result neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive (soft cap).

**Claim tested (B1):** on protocol V4 connections, request memory retained by a node rises and falls with
`native_transport_max_request_data_in_flight` (L); accounted global in-flight bytes are held at or below L + C·2F and do not
grow with offered load beyond that; pooled direct memory follows within a small factor; the cap is soft, with an overshoot of
about one frame per connection.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (U3) — peak = L + S exactly at L = 1e6 / 4e6 / 16e6; L + S + C·S at C = 1 / 8 / 64, stable over 100 cycles; both `:127` disjuncts observed | caps (soft) | run 1 + self-check | 2026-10-22 |
| Cluster | **Confirmed** (C5) — peak `RequestsSize` 64.0 / 256.0 / 820.0 / 1,005.1 MiB at 64MiB / 256MiB / default / 4GiB (each = (⌊L/S⌋ + 1)·S); 95·S at C = 32; Δdirect 1,233 / 1,872 / 3,010 / 3,264 MiB | caps (soft; overshoot one request per connection) | run 1 + self-check | 2026-10-22 |

**Findings beyond the verdict.** (1) Δdirect ≈ 1.2 GiB + 2.1 × accounted bytes: the knob governs the slope, but the
Netty pool carries a ~1.2 GiB overhead independent of L at this load (inferred: per-arena chunk slack), so B1's "within ≤ 2×"
holds only for the increment. (2) THROW_ON_OVERLOAD: the counter is hard-capped (63·S, 929 refused), but direct memory rose
to +3,182 MiB and stayed at +3,040 MiB after `RequestsSize` returned to 0, consistent with the source reading that the pre-V5
throw path never releases a rejected request's envelope (`PreV5Handlers.java:157-159, 239-252`); an upstream JIRA candidate,
inferred, not proven by a leak report. (3) Under group commit with 1 MiB writes, each commit-log segment switch releases all
waiting writes (`AbstractCommitLogSegmentManager.java:334`). (4) A node start under `commitlog_sync: group` with a 10-s window
takes ~7 min.

**Feedback filed:** the case file's section D, plus the dated audit amendments (A3, B2a, B2e, B2g, B3a, B3b, B3c, B3e, B3f,
B3g) and runbook fix D1 (B3a). Not committed. Case-file sha256: as filed `c60e0fd5…bdd9`, frozen `7c7fa7a8…0ebd`,
after D1 `f0f7942d…a451`, final after section D: `1b2d84d3564ebba5509bae62f19550de5436e9a14b5b534df53a01954c7bae73`.
