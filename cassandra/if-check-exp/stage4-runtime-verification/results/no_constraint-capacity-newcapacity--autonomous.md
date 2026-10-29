# no_constraint-capacity-newcapacity--autonomous — stage-4 results  <!-- file: results/no_constraint-capacity-newcapacity--autonomous.md -->

> **Case:** [`no_constraint-capacity-newcapacity--autonomous`](../../stage3-ai-deep-read/cases/no_constraint-capacity-newcapacity--autonomous.md)
>
> **Status:** verdict filed (2026-10-29) — unit tier run 1 done and self-checked, cluster tier `n/a`, no run 2
>
> **Outcome class:** **true negative** (estimate `negative`, effect `does not cap`) — [definition](../README.md#outcome-class).
>
> **Agent:** autonomous. "§9a" means B2f/B2g as amended (B2 amendment of 2026-10-29, items e and g); "§9b-§9e" means B2a-B2e; feedback is section D. Design: [`none-type-design.md`](../none-type-design.md), operand kind 3.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `a254c929`; the case file is uncommitted. **sha256 after the audit's amendment (2026-10-29), with one pre-run correction (the M arm's exception type): `21e6380bae064949d453b768c43814a4e3dbfab782152efc52a59ad8f00d868a`**, written to `pc29:~/s4-none/logs/freeze.sha` (copy `run1/freeze.sha`) at 2026-10-29 04:09:37 UTC, before the harness and before any reading. (The first freeze, 04:07:52 UTC, was `dfc16c2b5e760d2e6c83301fa1a0f326507f109de6309bcfbcaef46c94d07acf`; the correction does not depend on any run reading: it was found in the netty-buffer bytecode.) Later edits before the run: none. Section D was filled after the run; sha256 of the file with D filled: `08f5f29337074273d4edefc2798de31a91398b4a06b1953cde4b0d69202c90ef`. Frozen text = everything above section D. |
| **Harness** | `harness/no_constraint-capacity-newcapacity--autonomous/`: `BufferPoolCapacityTest.java`, `NetProbe.java`, `rules.btm`, `unit-run.sh`, `analyze.py`, `selfcheck.py`, `README.md`; written after the freeze; uncommitted; md5s `run1/harness.md5`. **Pre-run shakedown (disclosed):** one JVM at C = 4096, 1 repetition, read before the run to check compile and rules; E, G, S, M behaved as predicted; output deleted, nothing from it used. The run itself then hit defect D1 (section 3). |
| **Tiers and values** | Unit tier only: C in {128 B, 4 KiB, 64 KiB, 1 MiB, 16 MiB}, arms E / G / S / M, 5 repetitions after a discarded warm-up; control JVMs (4 KiB with `networking_cache_size` 128 and 0; 16 MiB known answer). Cluster `n/a`. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-29 |

### 1.1 Design audit

Audited against `cassandra/cassandra-5.0.9/` (clean). Re-read: `BufferPoolAllocator.java` (all), `BufferPool.java:120-135, 200-300, 380-480, 780-960, 1595-1670`, `BufferPools.java:36-60`, `GlobalBufferPoolAllocator.java`, `BufferPoolAllocatorTest.java` (all), `DatabaseDescriptor.java` (`getNetworkingCacheSizeInMiB`), and the netty-buffer 4.1.130 bytecode of `AbstractByteBuf.checkNewCapacity`.

| Group | Check | Rating | Note |
|---|---|---|---|
| A. Core question | constrained quantity is memory | Partly | No constraint (A1); the quantity is one direct buffer taken from the networking pool or allocated outside it. |
| A. Core question | knob varied or another approach | Partly → Met | B2 as filed was `n/a`; the amendment sweeps the request over five sizes across the 128 KiB pooled/overflow boundary and compares the equal call with the growing and shrinking calls. |
| A. Core question | real resource measured | Partly → Met | The pool's own gauges (`usedSizeInBytes`, `overflowMemoryInBytes`, `sizeInBytes`), the JDK `direct` gauge and a line-128 snapshot of both buffers held; thread allocation only for residue. |
| A. Core question | usage driven to the limit and past it | Partly | No limit; the sweep reaches 16 MiB. |
| A. Core question | positive control for a negative estimate | Partly | `networking_cache_size` 128 vs 0 moves the pooled/overflow gauges; it is the pool's cap, not a cap on line 121 (stated). |
| B. Logic | steps, numbers, rows | Not met → Met | item e (exact integers per arm), g (rows). |
| B. Logic | confirmation needs direct branch evidence | Met | Byteman counter at line 124 (0 for E, 1 for G/S/M) and the snapshot at line 128. |
| B. Logic | alternatives and controls | Met | arm M shows the bound that does bind (Netty `maxCapacity`), at another statement. |
| C. Specific | human / AI can follow; values exact | Met after amendment | package, class, flags, sizes. |
| D. Runnable | prerequisites exist | Partly | the run needed `--add-exports/--add-opens` for `jdk.internal.ref` (defect D1). |
| D. Runnable | citations spot-checked | Met, with corrections | `BufferPoolAllocator.java:112-131`, `BufferPool.java:233-264, 282-293`; the draft's "64 KiB overflows" is wrong (128 KiB, `NORMAL_CHUNK_SIZE`, :128); the amendment's claim that overflow memory is freed at GC is wrong (`BufferPool.java:817`, see 4.2 part 2). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Fill B2 (sweep, gauges, Byteman counters, exact predictions, control) | Applied, 2026-10-29 | design §3-§4 |
| 2 | Correct the overflow boundary to 128 KiB and the rounding units (tiny 32 B, normal 2 KiB) | Applied | accuracy |
| 3 | M arm expects `IllegalArgumentException`, not `IndexOutOfBoundsException` | Applied before the run (re-freeze) | netty-buffer bytecode |
| 4 | B3 stays `n/a` | Applied | no Cassandra caller; equal branch only by direct call; MiB scale |
| 5 | Add the JVM options of `conf/jvm11-clients.options` to the run | Applied in `unit-run.sh` after defect D1 | the tier was rerun from the start |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-29 04:13 UTC (attempt 1, aborted) and 04:15-04:16 UTC (the counted run) |
| Node | `pc29` = `node3.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB) |
| OS and kernel | Ubuntu 22.04, `5.15.0-198-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Apache Ant 1.10.12 |
| Local source copy | `~/s4-none/cassandra` by `copy-source.sh` at repository commit `a254c929`; `ant build-test` 1 min 8 s |
| Case-file commit / harness commit | uncommitted; sha256 in section 1 |
| Storage | none (pool buffers only) |
| Full logs (outside the repo) | `pc29:~/s4-none/run1/no_constraint-capacity-newcapacity--autonomous/` (counted run) and `...autonomous.attempt1-defect/` (aborted attempt); excerpts in `run1/` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| D1 | attempt 1 | B2a (JVM flags) | In four of eight JVMs (C = 1 MiB, 16 MiB, control cache 0, known-answer 16 MiB) the test aborted at `release()`: `BufferPool.LocalPool.put` of an overflow buffer reaches `FileUtils.clean` (BufferPool.java:817), whose static initialiser needs `jdk.internal.ref` access (`IllegalAccessException ... Cleaner.clean`, `run1/attempt1-defect-excerpt.txt`). No reading from attempt 1 is used. | `unit-run.sh` passes the options of `conf/jvm11-clients.options` (the `--add-exports/--add-opens` lines); the whole tier was rerun from the start, all 8 JVMs exit 0. | applied 2026-10-29 before any reading was examined; claim, prediction and table unchanged | untracked |

## 4. Run 1

**Scope:** unit tier, all B2 values. **Command log:** `run1/session.log`; raw rows `run1/raw-all.csv`; judged by `run1/analyze.out`.

### 4.1 Readings

**Unit tier** (`run1/analyze.out`: 81 PASS, 5 FAIL; `run1/selfcheck.out`: 402 hold, 0 fail). The 5 FAIL are two secondary figures, see 4.2 part 2.

| Test or assertion | Result | Evidence |
|---|---|---|
| Allocation state | used after allocation = cap0 (exact); overflow = cap0 for 1 MiB and 16 MiB (cap0 = C), 0 for 128 B, 4 KiB, 64 KiB | `raw-all.csv` |
| Arm E (`capacity(cap0)`) | SC 0 at every C; used, overflow, pooled and direct gauges unchanged; capacity unchanged; residue 0 B | rows `E` |
| Arm G (`capacity(cap0+1)`) | SC 1; capNew = cap0+1 for 1 MiB and 16 MiB, cap0+32 (128 B), +2048 (4 KiB), +2048 (64 KiB: 67,584); **used after = capNew** (one buffer); overflow after = capNew for the two overflow sizes; line-128 snapshot used = cap0 + capNew (e.g. 33,554,433 at 16 MiB) | rows `G` |
| Arm S (`capacity(cap0/2)`) | SC 1; used after = capNew (cap0/2 exactly in all five); line-128 snapshot = cap0 + capNew | rows `S` |
| Arm M (`capacity(max+1)`) | `IllegalArgumentException`, SC 1, usage and capacity unchanged | rows `M` |
| After `release()` | used 0 and overflow 0, every arm, every C | `u2`, `o2` columns |
| JDK direct gauge, overflow sizes | G: delta 1 byte (= capNew - cap0) right after the call and after `System.gc()`; S: -cap0/2; E: 0 | columns `d0,d1,d2` |
| On-heap residue | E 0 B; S 1,888 B (128 B-64 KiB) and 2,520 B (1-16 MiB); M 2,592-2,600 B; G 1,888-2,520 B in three of five repetitions, 15,920-17,008 B in repetitions 3 and 5 | column `heap` |
| Control, `networking_cache_size` 128 MiB, C = 4096 | pooled bytes 8,388,608, overflow 0 | `raw-all.csv` rows `control`, `cache=128` |
| Control, `networking_cache_size` 0, C = 4096 | pooled bytes 0, overflow 4096 (= cap0) | `cache=0` |
| Known answer, C = 16 MiB | overflow 16,777,216 | `known-16m` |

### 4.2 Conclusion and logic

1. **Validity.** `super.capacity` was reached by G, S, M (SC 1) and not by E (SC 0), by a Byteman counter at line 124 **[observed: `raw-all.csv` column `sc`]**; the line-128 snapshot fired for G and S **[observed: `u128`]**. Hold-fixed: `-Xmx512m`, one thread, fresh JVM per C, `networking_cache_size` 128 MiB (0 only in the control) **[observed: `session.log`, `# cache=` headers]**. Valid, after the rerun of defect D1.
2. **Readings.** Two secondary sub-predictions missed. (a) Frozen: "after G, the direct gauge delta = capNew (the old region stays counted until collection)". Observed: delta 1 byte right after the call. **My amendment was wrong**: `BufferPool.LocalPool.put` calls `FileUtils.clean(buffer)` (BufferPool.java:817) for a buffer with no parent chunk, so the old overflow region is released at the `put` on line 128, not at garbage collection **[observed: delta 1 at `d1` and `d2`; source: BufferPool.java:812-820]**. The after-GC prediction (delta within 4096 of capNew - cap0) held. The pool-gauge predictions all held. (b) G's on-heap residue exceeded 16,384 B in repetitions 3 and 5 at C = 64 KiB, 1 MiB, 16 MiB (16,456; 17,008; 17,008), by 72 to 624 B. Per B2g's last row, neither changes the verdict. The recurrence at the same repetition indices at every C suggests a JIT or first-use effect **[inferred]**.
3. **Matched row.** B2g row 1: E leaves every gauge unchanged with SC 0; G and S leave steady-state used equal to the one new buffer's capacity, with two buffers visible only in the line-128 snapshot; M rejected by Netty; the control moved; release returned all gauges to 0 **[observed]**.
4. **Excluded rows.** Row 2 (E changes a gauge, or steady state keeps both buffers, or line 121 clamps or refuses a request within the max capacity): none **[observed: E delta 0; u1 = capNew in all G and S rows; M is refused by Netty's `maxCapacity` at line 124's callee, not by line 121]**. Row 3 (control flat, SC 0 for G, gauge not returning to 0): the control moved (8,388,608 to 0 pooled; 0 to 4096 overflow), SC was 1, gauges returned to 0 **[observed]**.
5. **Observed vs inferred.** Inferred: (a) Netty's own growth path only asks for a larger capacity, so the equal branch is reached in production only through a direct call, of which there is none in the tree (source grep in A3 and the amendment, not re-run); (b) the cause of the residue outliers; (c) that a transient second buffer replaced by one of equal steady-state size is not a cap (same judgement as the sibling resizeTo file).
6. **Deviations and gaps.** Unit tier only. The control is the pool's own cap moving the gauges, not a cap on line 121; `case-notes.md` records for the closed `networking_cache_size` case that large-request buffers are left in the overflow (not re-read here), so I do not claim it caps the overflow path. The direct-memory prediction of the amendment was wrong (part 2). Run 2 not done.
7. **Core question.** Line 121 compares the requested and the current capacity of one buffer; it limits nothing. After every call the usage is the one buffer's capacity (E: cap0; G, S: capNew); the only effect of the branch is to skip a same-size replacement that would hold two buffers for a moment (visible at line 128) **[observed: parts 3-4]**. The size that does bind a request is Netty's `maxCapacity` (arm M), a different statement.

**Conclusion (one line):** B2g row 1 — Confirmed (does not cap), with the direct-gauge and residue sub-predictions missed.

## 5. Self-check of run 1 — AI

`harness/.../selfcheck.py` re-parses `raw-all.csv` with the `csv` module and derives expectations from the pool rules (128 KiB boundary, one buffer in steady state, two at the put), not from `analyze.py`: 402 hold, 0 fail (`run1/selfcheck.out`). I re-read `BufferPoolAllocator.java:118-131` and `BufferPool.java:812-820` for the claim in part 2.

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | SC and line-128 columns as stated; 8 JVMs exit 0 (`session.log`) |
| 2. Readings | yes | `d1`/`d2` columns equal 1 for G at 1 MiB and 16 MiB |
| 3. Matched row | yes | every counted E, G, S, M row satisfies the re-derived expectations |
| 4. Excluded rows | yes | no row has u1 != capNew for G or S |
| 5. Observed vs inferred | yes | listed |
| 6. Deviations and gaps | yes | the self-check does not test the direct gauge (that is `analyze.py` only) |
| 7. Core question | yes | |

### 5.2 Run 2?

**No** (2026-10-29): the pool gauges are exact integers repeated in five fresh JVMs; the open points (judgement, residue cause) are not settled by a repeat.

## 6. Run 2 — fresh AI session (optional)

Not done. Sections 6 and 7 omitted.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap).

**Claim tested** (B1): this check does not cap memory or disk usage; it only skips a redundant resize when the requested capacity equals the current capacity. "Confirmed" means this held.

| Tier | Verdict (B2g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1; direct-gauge and residue sub-predictions missed, recorded) | does not cap | run 1 + self-check | 2026-10-29 |
| Cluster | not run: `n/a` (B3 amendment: no Cassandra caller; a network workload only grows buffers through Netty; pool memory is bounded by `networking_cache_size` and overflow accounting, other statements) | n/a | audit | 2026-10-29 |

**Positive control:** `networking_cache_size` 128 MiB vs 0 moved the pooled bytes 8,388,608 to 0 and the overflow 0 to 4096 under the same gauges; known answer 16 MiB overflow = 16,777,216. It is the pool's cap on chunk memory, not a cap on line 121; no setting caps the resize.

**Judgement:** same as the sibling resizeTo file (B2g): the branch gates a transient second buffer, not a retained size; a reader who counts any avoided allocation as `caps` would classify it differently.

**Feedback filed:** section D of the case file, B2/B3 amendments (2026-10-29). `_INDEX.md`, `writeup-set-A.csv`, HANDOFF left to the orchestrator.

**Leftovers:** no `JUnitCore` or `CassandraDaemon` running. On `pc29`, outside the repo: `~/s4-none/` (source copy, `logs`, `run1`, including the aborted `...attempt1-defect`).
