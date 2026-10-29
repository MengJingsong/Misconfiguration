# no_constraint-allocateblock-inchunkpointer--autonomous — stage-4 results  <!-- file: results/no_constraint-allocateblock-inchunkpointer--autonomous.md -->

> **Case:** [`no_constraint-allocateblock-inchunkpointer--autonomous`](../../stage3-ai-deep-read/cases/no_constraint-allocateblock-inchunkpointer--autonomous.md)
>
> **Status:** verdict filed (2026-10-29) — unit tier run 1 done and self-checked, cluster tier `n/a`, no run 2
>
> **Outcome class:** **true negative** (estimate `negative`, effect `does not cap`) — [definition](../README.md#outcome-class).
>
> **Agent:** autonomous. "§9a" means B2f/B2g as amended (B2 amendment of 2026-10-29, items e and g); feedback is section D. Design: [`none-type-design.md`](../none-type-design.md); **operand kind 1** (the draft's correction from kind 3, confirmed).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `a254c929`; the case file is uncommitted. **sha256 after the audit's B2/B3 amendment (2026-10-29): `3faf8b4c7288e826140f0ea103593a19e103b73534f5eb97f13d4c43378821da`**, written to `pc29:~/s4-none/logs/freeze.sha` (copy `run1/freeze.sha`) at 2026-10-29 04:07:52 UTC (repeated in the second line block at 04:09:37 UTC, unchanged), before the harness existed and before any reading. Section D was filled after the run; sha256 of the file with D filled: `1bba0a31206d78420ebdfd604b5d518331cac119826d3cfd5e21f4e84f949f73`. Frozen text = everything above section D. |
| **Harness** | `harness/no_constraint-allocateblock-inchunkpointer--autonomous/`: `InMemoryTrieAllocBlockTest.java`, `unit-run.sh`, `analyze.py`, `selfcheck.py`, `README.md`; no Byteman; written after the freeze; uncommitted; md5s `run1/harness.md5`. **Pre-run shakedown (disclosed):** one JVM with `stage4.reps=0` (the warm-up cycle only), read before the run; A allocated 0 B, B allocated N + about 100 B, `sizeOnHeap` stepped on A; output deleted, nothing from it used. |
| **Tiers and values** | Unit tier only: i in {1, 3, 7, 11, 15, 19} on heap (N = 512 B to 128 MiB), off-heap at i = 11 and 15, 5 repetitions after a warm-up; control JVM (`-Xmx6g`): i = 22 and the hard limit at S_23. Cluster `n/a`. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-29 |

### 1.1 Design audit

Audited against `cassandra/cassandra-5.0.9/` (clean). Re-read: `InMemoryTrie.java:56-100, 106-112, 136-176, 430-500, 945-990`, `InMemoryReadTrie.java:200-255`, `BufferType.java`, `InMemoryTriePutTest.java:60-70`. The draft in `none-type-drafts-kind3.md` §3 was read and corrected where noted.

| Group | Check | Rating | Note |
|---|---|---|---|
| A. Core question | constrained quantity is memory | Met | The trie's buffer bytes (A2). |
| A. Core question | knob varied or another approach | Partly → Met | No knob (a literal 0 in a position test); the operand is `allocatedPos`, swept across six chunk starts, with both sides of the branch measured on adjacent blocks. |
| A. Core question | real resource measured | Met | Thread-allocated bytes around single calls for the heap buffer; the JDK direct gauge for off-heap (where the thread counter is blind, shown); `buffers[j]` capacities by reflection. |
| A. Core question | usage driven to the limit and past it | Partly → Met | There is no limit at line 145; the control drives the same instrument to the hard limit at line 148 (2^31 - 256) and shows it stopping the allocation. |
| A. Core question | positive control | Partly → Met | The draft's control (line 953) is a signal, not an allocation; replaced by the line-148 limit in the same instrument. |
| B. Logic | prediction in numbers; rows | Not met → Met | B2 as filed was `n/a`; item e (exact positions, bounds on bytes) and g. |
| B. Logic | branch evidence | Met | the allocation itself (A 0 B, B N_i), `buffers[i]` null then N_i. |
| B. Logic | alternatives and controls | Met | floor (empty window), off-heap arm, control. |
| C/D | specific, runnable, citations | Met | All citations in A1-A3 held (`InMemoryTrie.java:70, 140-160, 953, 961-966, 975-981`; `InMemoryReadTrie.java:127, 207-215, 231-251`; callers 433, 451, 476, 497, 964). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Operand kind 1; fill B2 with the chunk-start sweep | Applied, 2026-10-29 | design §2-§3 |
| 2 | Do the setup outside the window; start at i = 1 | Applied | the draft's call sequence would put the earlier chunks inside the window; i = 0 has no mid-chunk predecessor |
| 3 | `sizeOnHeap()` steps on the block that reaches a chunk start (A: +32+R), not on the allocating block (B: +32) | Applied | the draft had it on B |
| 4 | Replace the line-953 control with the line-148 hard limit in the same instrument | Applied | line 953 is a signal |
| 5 | B3 stays `n/a` | Applied | exact-position hook only; sweep below heap noise except at the top |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-29 04:13:59-04:14:13 UTC (14 s for both JVMs) |
| Node | `pc29` = `node3.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB) |
| OS and kernel | Ubuntu 22.04, `5.15.0-198-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Apache Ant 1.10.12 |
| Local source copy | `~/s4-none/cassandra` from `cassandra/cassandra-5.0.9/` at repository commit `a254c929`; `ant build-test` 1 min 8 s |
| Case-file commit / harness commit | uncommitted; sha256 in section 1 |
| Storage | none |
| Full logs (outside the repo) | `pc29:~/s4-none/run1/no_constraint-allocateblock-inchunkpointer--autonomous/` (`sweep/`, `control/`); excerpts in `run1/` |

## 3. Runbook defects

None.

## 4. Run 1

**Scope:** unit tier, all B2 values. **Command log:** `run1/session.log`; raw rows `run1/raw-all.csv`; judged by `run1/analyze.out` (63 PASS, 0 FAIL); `run1/selfcheck.out` (283 hold, 0 fail).

### 4.1 Readings

**Unit tier** (R = `REFERENCE_ARRAY_ON_HEAP_SIZE` = 32)

| Test or assertion | Result | Evidence |
|---|---|---|
| Instrument floor (empty window), all i | 0 B | rows `F` |
| A (the block at S_i - 32, mid-chunk, check false), i = 1..19 | 0 B allocated; `allocatedPos` S_i - 32 -> S_i; `buffers[i]` null; `sizeOnHeap` +64 (= 32 + R); retained buffers S_i | rows `A` |
| B (the block at S_i, chunk start, check true) | N_i + 96 B: 608, 2,144, 32,864, 524,384, 8,388,704, 134,217,824 for N_i = 512 B ... 128 MiB; `allocatedPos` S_i -> S_i + 32; `buffers[i]` null -> capacity N_i; `sizeOnHeap` +32; retained S_i -> S_i + N_i | rows `B` |
| Residue B - N_i | 96 B at every i; spread over the 5 repetitions 0 B | `analyze.out` |
| Retained buffers / `allocatedPos` right after B | 2.667 (i = 1), 2.105 (3), 2.006 (7), 2.000 (11, 15, 19) | `analyze.out` |
| Off-heap, i = 11 and 15 | A: direct gauge +0; B: +524,288 and +8,388,608 (= N_i exactly); thread-allocated bytes of B 168 at both | rows `OFF_HEAP` |
| Control, i = 22 (`-Xmx6g`) | A 0 B; B 1,073,741,920 B (2^30 + 96); retained 2,147,483,392 | `raw-all.csv` rows `control` |
| Control, advance to S_23 = 2,147,483,392 | 0 B (false blocks only); `allocatedPos` 2,147,483,392 | row `C1` |
| Control, the next block | `SpaceExhaustedException`, 1,584 B allocated (against 256 << 23 = 2^31 B); `allocatedPos` stays 2,147,483,392 | row `C2` |

### 4.2 Conclusion and logic

1. **Validity.** Both branches executed at every i: A skipped the allocation and B performed it, shown by the allocation itself and by `buffers[i]` going from null to N_i **[observed: `raw-all.csv`]**. The positions equal S_i - 32 / S_i / S_i + 32 exactly **[observed]**. The floor is 0 B. Hold-fixed: `-Xmx1g` (control `-Xmx6g`), single thread, no yaml, threshold property unset **[observed: `session.log`]**. Valid.
2. **Readings.** All frozen predictions held, including the corrected `sizeOnHeap` step on A. The instrument is blind to off-heap buffers (168 B for a 8 MiB buffer), as predicted; the direct gauge supplies the reading there **[observed]**.
3. **Matched row.** B2g row 1: A allocates nothing, B allocates N_i + 96 B at every i, positions and `sizeOnHeap` steps as predicted, retained buffers S_i + N_i, and the control stopped by line 148 **[observed]**.
4. **Excluded rows.** Row 2 (B allocates less than N_i, an exception or refusal at line 145 for i < 22, or A allocates): none; no exception at any chunk start through i = 22 **[observed]**. Row 3 (control did not throw, floor above 1 KiB, a position off): the control threw at S_23; floor 0; positions exact **[observed]**.
5. **Observed vs inferred.** Inferred: (a) that flipping line 145 would break rather than cap (no allocation at a chunk start, `buffers[leadBit]` null): the check cannot be flipped without editing the source; the A/B pair is the neighbouring-block flip **[inferred]**; (b) production callers (`put` paths) reach the same `allocateBlock` as `advanceAllocatedPos` (source reading, InMemoryTrie.java:433-497, 964).
6. **Deviations and gaps.** Unit tier only. `advanceAllocatedPos` drives the allocator without trie content; the production path adds `putRecursive` around it (not run here). The line-148 control is a different statement from the one under test; its role is to show the instrument can see an allocation stopped by a cap. Run 2 not done.
7. **Core question.** Line 145 is the allocation trigger: at a chunk start it allocates the next doubling buffer N_i, elsewhere it allocates nothing. Usage follows the blocks written (`allocatedPos`), with the buffers at most about twice that figure right after a chunk is created (retained / `allocatedPos` 2.0 to 2.7); nothing at line 145 limits or refuses an allocation, whereas line 148 does (control). The check does not cap **[observed: parts 3-4]**.

**Conclusion (one line):** B2g row 1 — Confirmed (does not cap).

## 5. Self-check of run 1 — AI

`harness/.../selfcheck.py` re-parses `raw-all.csv` and re-derives chunk starts (`256 * (2^j - 1)`) and retained totals from the arithmetic, not from `analyze.py`: 283 hold, 0 fail (`run1/selfcheck.out`). I also re-read `InMemoryTrie.java:140-160` and `975-981` against the `sizeOnHeap` step and the position columns.

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | positions and `buffers[i]` columns |
| 2. Readings | yes | A/B allocation figures; off-heap 168 B |
| 3. Matched row | yes | |
| 4. Excluded rows | yes | no `exc` other than the control's, which is the expected `SpaceExhaustedException` |
| 5. Observed vs inferred | yes | |
| 6. Deviations and gaps | yes | |
| 7. Core question | yes | |

### 5.2 Run 2?

**No** (2026-10-29): all figures are exact and identical across five repetitions and six octaves; no inferred statement depends on a repeat.

## 6. Run 2 — fresh AI session (optional)

Not done. Sections 6 and 7 omitted.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap).

**Claim tested** (B1): the check at `InMemoryTrie.java:145` does not cap memory or disk usage: it is a chunk-boundary test that triggers buffer allocation; total trie size is set by the blocks written and bounded elsewhere (line 148, `ALLOCATED_SIZE_THRESHOLD`). "Confirmed" means this held.

| Tier | Verdict (B2g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1) | does not cap | run 1 + self-check | 2026-10-29 |
| Cluster | not run: `n/a` (B3 amendment) | n/a | audit | 2026-10-29 |

**Positive control:** the hard limit at line 148, same instrument and same trie: it stopped the allocation (1,584 B and an exception where the unbounded pattern reads 2^31 B) at `allocatedPos` 2,147,483,392, while the instrument read N_i at every chunk start below it. It is a different statement from the one under test.

**Feedback filed:** section D of the case file and the B2/B3 amendments (2026-10-29). `_INDEX.md`, `writeup-set-A.csv`, HANDOFF left to the orchestrator. Observation for stage 3 (outside the claim): right after a chunk is created the live buffers are about 2x `allocatedPos`, which `sizeOnHeap()` reports.

**Leftovers:** no `JUnitCore` or `CassandraDaemon` running. On `pc29`, outside the repo: `~/s4-none/`.
