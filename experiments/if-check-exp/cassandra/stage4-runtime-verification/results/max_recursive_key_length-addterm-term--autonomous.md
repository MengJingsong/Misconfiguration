# max_recursive_key_length-addterm-term--autonomous — stage-4 results  <!-- file: results/max_recursive_key_length-addterm-term--autonomous.md -->

> **Case:** [`max_recursive_key_length-addterm-term--autonomous`](../../stage3-ai-deep-read/cases/max_recursive_key_length-addterm-term--autonomous.md)
>
> **Status:** **Self-checked 2026-10-28 — unit Confirmed (does not cap), cluster Confirmed (does not cap); all pre-registered numbers met (66 PASS, 0 FAIL); `z1` build overflows the stack at L >= 2048 (allowed row); no run 2**
>
> **Outcome class:** true negative — stage-3 estimate `negative` against the stage-4 effect `does not cap` ([definition](../README.md#outcome-class))
>
> **Agent:** autonomous (B2 = unit tier, B3 = cluster tier, feedback = section D).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the whole file after the audit's amendments (U/C items, dated 2026-10-28, inserted after the link rule): `3e5aa37e6289514873c3f38b8679863194e42c9b068f6da9a29f4eb2f72972ea`. Repository HEAD `b68711e5`; case file, harness and results uncommitted. Computed before any reading and unchanged through both tiers (`sha256sum` re-checked 2026-10-28). The frozen text is everything above section D. |
| **Harness** | `harness/max_recursive_key_length-addterm-term--autonomous/` (uncommitted; README lists the files). |
| **Tiers and values** | Unit (B2) and cluster (B3), both run. Capacity values: L 64/128/129/256/2048/7000 x constant 0/128/100000 (unit); L 100/128/129/400 x stock/0 x heap/off-heap (cluster). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | bytes | Met | A2: the constant selects a routine; memory measured is the trie bytes per term. |
| A | knob | Partly | Hard-coded; varied through overlays 0 / 128 / 100000 (U2, C2); term length L at 64..7000 is the second dimension. |
| A | real resource | Met | `sizeOnHeap`/`sizeOffHeap` of the trie, the returned delta, tablestats and JMX gauge, heap after GC. |
| A | driven past limit | Met | L from 64 to 7000 crosses 128; the guardrail control crosses its fail threshold. |
| B | steps | Met | B2e, B3e numbered. |
| B | prediction numbers | Partly | B2f 'smooth' and 'a few percent' made numeric (U4, C3). |
| B | every outcome has a row | Partly | no row for StackOverflowError with the constant raised (`InMemoryTrie.java:884-885`): added (U3). |
| B | confirmation needs ceiling-follows-knob and disallow evidence | Met | the guardrail control is the disallow branch; stock vs overlays is the knob. |
| B | alternative explanations | Met | route counters prove the route; guardrail control. |
| C | human can follow | Met | A1-A3. |
| C | AI can run without re-deriving | Partly | probe set-up, overlays, JVM flags (U1, U2). |
| C | exact values | Partly | full factorial of B3b (about 48 starts) replaced by a listed 15-run matrix (C2). |
| D | harness exists | Partly | written in step 1. |
| D | workload reaches limit | Met | unit N x L up to 140 MB at -Xmx2g; cluster 40 MB of term data per run. |
| D | citations spot-checked | Met | `TrieMemoryIndex.java:64,94-126,218-239`; `InMemoryTrie.java:884-920`; `StorageAttachedIndex.java:207-210,815-823`; `Config.java:941-946`: match. The default-authenticator guardrail bypass is stated (C1). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Environment, overlays, numbers, missing StackOverflow row (U1-U4) | Applied 2026-10-28 | as filed not runnable |
| R2 | Cluster matrix reduced and listed (C2); instruments (C3) | Applied | full factorial not proportionate |
| R3 | Control reading recorded for the default authenticator (C1) | Applied (note) | no change to B3f |

**Pre-run-1 instrument checks** (disclosed; none of them is a reading used in a prediction): see section 3 and the harness README.

**Pre-run-1 instrument checks and shakedowns (disclosed; none edited a prediction):** (1) `javac` of the probe and three known-answer runs (instr overlay at L = 129 and 100 with 2000 terms; the guardrail control with 900 and 1500 bytes): the counters showed 2000 on the `apply` route at L = 129 and 2000 on the recursive route at L = 100; per-term bytes 230 and 198 (an observation, not used); the guardrail returned growth for 900-byte terms and 0 for 1500. (2) `MockSchema.newCFS` needed `CommitLog.instance.start()` (added to the probe). (3) One cluster shakedown, S/heap/L = 129, 20,000 rows, discarded: it showed `MemtableIndexBytes` 3,622,432 and the JMX query form. No prediction was changed.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | unit 2026-10-28 (node clock UTC 2026-10-28 23:52 to 2026-10-29 00:09); cluster 2026-10-28 (node clock UTC 2026-10-29 00:11 to 01:10) |
| Node | `pc32` = `node2.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB); four to five other nodes of this session's other cases ran at the same time |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK / Ant | openjdk 11.0.32.1 (2026-08-18) / Apache Ant 1.10.12 |
| Local source copy | `~/s4-b34` from `cassandra/cassandra-5.0.9/` at repository commit `b68711e5` (`copy-source.sh`), `ant build-test` BUILD SUCCESSFUL; overlays `build/overlay-{instr,z0,z1,zi0}`; node variant `~/s4-b34-vZ`; the variant copies were deleted after the runs (rebuild with the harness `make-variant*.sh`) |
| Case-file / harness commit | uncommitted (working tree of `b68711e5`); case-file sha256 in section 1 |
| Storage for node data | `~/stage4-tmp/b34/c4/<label>` on local `/dev/sda3`, removed after each run; nothing under `/proj` except these excerpts |
| Full logs (outside the repo) | `pc32:~/s4-b34-logs/b4/run1/` (`unit/`, `cluster/<label>/`) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) |
|---|---|---|---|---|---|
| D1 | unit shakedown | B2a | `MockSchema.newCFS` reads the commit log position; `CommitLog` was not started (`NullPointerException`) | `CommitLog.instance.start()` in the probe | before the freeze of run 1 (instrument), 2026-10-28 |
| D2 | cluster | C2 | `-Xlog` is added by the harness (`jvm-extra.txt`); the node runs from the jar, so the Z variant needed the recompiled class in the jar, not only on `build/classes/main` | `make-variant.sh` updates the jar; `javap` of both jars shows `sipush 128` / `ifgt` in `addTerm` (`cmdlog-head.txt`) | 2026-10-28 |

## 4. Run 1

**Scope:** every B2 and B3 value of section 1 (the unit grid in full, the 15 node starts of amendment C2). **Command logs:** `max_recursive_key_length-addterm-term--autonomous/run1/`.

### 4.1 Readings

**Unit tier** (`run1/unit/unit.out`; per-term = sum of `add()` returns / N; stock build, repetition 1; all three repetitions identical wherever the run completed)

| L | per-term bytes, N = 20000 | per-term bytes, equal total (N = 2e6 / L) | routes (instr overlay) | z0 and z1 |
|---|---|---|---|---|
| 64 | 163.789 | 171.065 (N = 31250) | 20000 recursive | identical to stock |
| 128 | 227.789 | 224.897 (15625) | 20000 recursive | identical |
| 129 | 227.789 | 224.808 (15503) | 20000 `apply` | identical |
| 256 | 387.790 | 390.706 (7812) | all `apply` | identical |
| 2048 | 2435.795 | 2440.623 (976) | all `apply` | z0 identical; **z1 StackOverflowError after 0 or 1 terms** |
| 7000 | 8067.800 | 8073.404 (285) | all `apply` | z0 identical; **z1 StackOverflowError after 0 terms** |

| Test or assertion | Result | Evidence |
|---|---|---|
| routes | `instr`: L <= 128 -> counters (N, 0); L >= 129 -> (0, N), both passes; `zi0` (constant 0): (0, N) at every L | `routeRec` / `routeApply` in `unit.out` |
| step at 128 -> 129 | per-term ratio 129/128: 1.0000 (N = 20000) and 0.99961 (equal total); trie bytes (sizeOnHeap + sizeOffHeap) per term the same ratios | `TERM` lines |
| constant 0 and 100000 | per-term bytes equal to stock to the byte wherever the run completed (20 (L, pass) cells, 3 repetitions each); `z1` overflowed the stack at L = 2048 and 7000 (`-Xss512k`) in all 3 repetitions and both passes | `result=SOE` lines |
| guardrail control (`sai_string_term_size_{warn,fail}_threshold` = 1024 B) | 900-byte terms: 2000 of 2000 adds grew the trie (2,148,288 B); 1500- and 7000-byte terms: 0 of 2000 grew it, sizes unchanged; identical in 3 repetitions | `GUARDTERM` lines |

**Cluster tier** (`run1/cluster/<label>/readings.txt`; 40,000,000 / L rows, 16 stress threads, 2 GiB heap; reading after 60 s idle, no flush in any run: `FLUSHES_DURING_RUN 0`)

| Run | build / allocation | L | rows | MemtableIndexBytes | Memtable data size | heap used after GC (kB) |
|---|---|---|---|---|---|---|
| SH100 / ZH100 | stock / Z, heap_buffers | 100 | 400,000 | 67,026,328 / 67,026,328 | 47,167,589 | 462,563 / 462,687 |
| SH128 / ZH128 | stock / Z, heap | 128 | 312,500 | 60,719,208 / 60,719,208 | 43,453,323 | 409,000 / 414,192 |
| SH129 / ZH129 | stock / Z, heap | 129 | 310,077 | 60,343,880 / 60,343,880 | 43,426,126 | 411,846 / 410,031 |
| SH129b, SH129c | stock, heap | 129 | 310,077 | 60,343,880 / 60,343,880 | 43,426,126 | 412,904 / 407,979 |
| SH400 / ZH400 | stock / Z, heap | 400 | 100,000 | 43,711,912 / 43,711,912 | 35,274,787 | 286,367 / 292,307 |
| SO128 / ZO128 | stock / Z, offheap_objects | 128 | 312,500 | 60,719,208 / 60,719,208 | 43,453,323 | 232,324 / 232,463 |
| SO129 / ZO129 | stock / Z, offheap_objects | 129 | 310,077 | 60,343,880 / 60,343,880 | 43,426,126 | 231,456 / 231,238 |
| CTL1500 | stock, heap, guardrail 1 KiB | 1500 | 100,000 | **0** | 121,694,087 | 284,628 |

| Observable | Reading | Evidence |
|---|---|---|
| oversize-term warnings (control) | 78,563 lines `Term in column ... is too large and cannot be indexed` in `system.log` of CTL1500; 0 in every other run | `readings.txt` `OVERSIZE_WARNINGS` |
| the two builds | `javap` of `addTerm`: stock `sipush 128` / `if_icmpgt`, Z `ifgt` (constant 0) | `cmdlog-head.txt` |
| client acceptance | all `cassandra-stress` runs finished; CTL1500 stored 100,000 cells (`Memtable cell count` 100000) with an empty SAI memtable index | `stress-summary.txt`, `tablestats.txt` |

### 4.2 Conclusion and logic

1. **Validity.** Valid. Both routes were exercised [observed: `routeRec` / `routeApply`], the builds differ in the constant [observed: `javap` lines; the `zi0` counters], the memtable never flushed [observed: `FLUSHES_DURING_RUN 0` in the 15 runs], heap and off-heap allocation types ran [observed: `jvm-extra.txt` / yaml lines in `cmdlog-head.txt`], no daemon left [observed: `daemons left (this run root): 0`].
2. **Readings.** The `z1` runs at L >= 2048 end in `StackOverflowError` as the amended U3 allowed (the recursion is one frame per key byte) [observed]; those cells are excluded from the memory comparison. The three repetitions of every completed unit run agree to the byte [observed: `selfcheck.txt`]. The off-heap runs show the same `MemtableIndexBytes` as the heap runs and a lower heap-after-GC (232 MB against 409 MB): where the bytes are counted [observed]. `selfcheck.txt`: 66 PASS, 0 FAIL against the pre-registered numbers.
3. **Matched row.** Unit B2g row 1 "Per-term memory is smooth across 128/129 and identical across the three constant values -> claim confirmed" (with the added U3 row for the stack overflow, which is a stack resource and does not alter the memory comparison): ratio 129/128 = 1.0000 and 0.9996, z0 = stock = z1 to the byte at L <= 256 [observed]; guardrail control row: 1500 and 7000 B terms add 0 and leave sizes unchanged while 900 B terms grow the trie [observed]. Cluster B3g row 1 "Memory for 128 vs 129 equal within noise, and stock = constant-0" and the control row: 60,343,880 / 60,719,208 = 0.9938; stock and Z identical (0.00 percent) at L = 100, 128, 129, 400 on both allocation types; three S-H L = 129 repeats identical; the 1 KiB guardrail run holds `MemtableIndexBytes` 0 and data size 121.7 MB (above the L = 400 run's 35.3 MB) with 78,563 warnings [observed].
4. **Excluded rows.** "A step at 129 that disappears when the constant is changed": no (ratio 1.0000, z0 equal) [observed]. "Memory per term cut off or terms rejected at 128/129": no [observed]. "Control terms above the guardrail still grow memory": no [observed]. "Counters show no use of one route": no [observed]. "Memtable flushed during a run": no [observed].
5. **Observed vs. inferred.** Inferred: that the constant cannot affect memory beyond the trie-node layout because both routes write the same layout — the per-term byte equality is the observation; the layout identity is inferred from it [inferred: equal sizes for 30 cells]. The stack cost of the recursive route is read from the `StackOverflowError` boundary only, not from a frame size.
6. **Deviations and gaps.** (a) The factorial of B3b was replaced by the 15-run matrix of amendment C2; the off-heap runs cover L = 128 and 129 only. (b) One run per cell in the cluster tier (three for S-H L = 129). (c) Up to five nodes of this session ran at once on `pc32`; the quantities read do not depend on timing. (d) The TrieMemoryIndex of a node is also fed by flushes and queries; none occurred. (e) The guardrail control rejects terms at the memtable-side check (`TrieMemoryIndex.addTerm` -> `validateTermSize`), not at the client write, as C1 records for the shipped authenticator.
7. **Core question.** Memory used by the SAI memtable trie index follows the amount and length of the terms and nothing at the 128-byte boundary: per-term bytes step by 0 between 128 and 129, are identical in builds with the constant at 0, 128 and 100000 (where the recursion does not overflow), and node-level `MemtableIndexBytes` is identical across stock and Z builds; the only line that stops index growth is the term-size guardrail, whose control binds. So the constant does not cap memory or disk (parts 3 and 4); it bounds only the call-stack depth of the recursive route (`StackOverflowError` at L >= 2048 when raised to 100000).

**Conclusion (one line):** Unit B2g row 1 — confirmed (does not cap; z1 stack overflow at L >= 2048 recorded); Cluster B3g row 1 and control row — confirmed (does not cap).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-opened 2026-10-28: `unit/unit.out` (180 `TERM` lines, 3 guard blocks) and the 15 `cluster/*/readings.txt` re-parsed by `harness/.../selfcheck.py` (`run1/selfcheck.txt`: 66 PASS, 0 FAIL), and by hand `cluster/CTL1500/readings.txt`, `cluster/SO129/readings.txt` and `cluster/ZH400/cmdlog-head.txt`.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `unit.out` routes; `cmdlog-head.txt` `javap` lines; `readings.txt` `FLUSHES_DURING_RUN 0`. |
| 2. Readings | yes | `result=SOE` only in `-ovz1-` cells; repetitions equal. |
| 3. Matched row | yes | ratios recomputed from `unit.out` and the readings. |
| 4. Excluded rows | yes | no step, no rejection, control rows hold. |
| 5. Observed vs. inferred | yes | the layout-identity inference is labelled. |
| 6. Deviations and gaps | yes | listed. |
| 7. Core question — the steps follow the audited logic | yes | route proof -> equal memory across the boundary and across builds -> guardrail control binds. |

### 5.2 Run 2?

**No** (2026-10-28). The unit readings repeat to the byte in three fresh JVMs per cell and the cluster readings are identical to the byte between stock and Z and between repeats; the conclusion rests on observations, not on inferred statements.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap): the constant only selects between two insertion routines that build the same trie.

**Claim tested (B1):** memory used by a `TrieMemoryIndex` (and by a node's SAI memtable) does not follow `MAX_RECURSIVE_KEY_LENGTH`: for the same term data, crossing 128 bytes changes neither the memory per indexed byte nor any ceiling, and nothing is rejected at 128/129; only the term-size guardrail (positive control) rejects terms and stops memory growth.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1; guardrail control row; U3 row: `z1` StackOverflowError at L >= 2048, a stack resource) | does not cap | run 1 + self-check | 2026-10-28 |
| Cluster | Confirmed (B3g row 1; control row) | does not cap | run 1 + self-check | 2026-10-28 |

**Positive control:** the term-size guardrail at 1 KiB: unit — 1500- and 7000-byte terms return 0 and add 0 bytes while 900-byte terms add 2,148,288 bytes per 2000; cluster — `MemtableIndexBytes` 0 and 78,563 warnings with 100,000 stored cells, against 43.7 MB for 100,000 400-byte terms.

**Feedback filed:** the case file's section D updated (no commit by this session); amendments U1-U4 and C1-C3 dated 2026-10-28, made at the audit before any reading.

