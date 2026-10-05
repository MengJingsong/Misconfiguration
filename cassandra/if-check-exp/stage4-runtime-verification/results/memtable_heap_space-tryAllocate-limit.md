# memtable_heap_space-tryAllocate-limit — stage-4 results

> **Case:** [`memtable_heap_space-tryAllocate-limit`](../../stage3-ai-deep-read/long-path/cases/memtable_heap_space-tryAllocate-limit.md)
>
> **Status:** run 1 done — unit tier (2026-09-28) reviewed by Jingsong and its verdict filed (2026-09-29); cluster tier run 1 done 2026-09-29, reviewed by Jingsong (2026-09-29) and its verdict filed (2026-09-30); run 2 not chosen. **Case closed.**

**Fill the sections in order.** Run 1 (§4) and the review (§5) are required;
run 2 (§6) and the comparison (§7) are filled only if the review chooses run 2.
The protocol behind each section is in
[`../README.md`](../README.md#the-run-protocol).
This file was started under the 2026-09-28 two-run protocol and moved to the
2026-09-29 one before any run 2.

## 1. Before run 1

| Field | Content |
|---|---|
| **Case-file commit** | Unit tier: `98ad478` — §9a frozen here. Cluster tier: `bf1f6bb` — §9a (Confirmed row amended 2026-09-29), §9c and §9e frozen here. |
| **Harness** | [`../harness/memtable_heap_space-tryAllocate-limit/`](../harness/memtable_heap_space-tryAllocate-limit/) — `HeapPoolTest.java`, commit `66ebf93`; Byteman rule `escape-hatch.btm`, commit `bf1f6bb`. |
| **Tiers and values** | Unit tier done. Cluster tier: 128, 256, 512 MiB and default, plus the cleanup-threshold control at 256 MiB. |
| **Approved by Jingsong** | Unit tier: 2026-09-28. Cluster tier: 2026-09-29. |

**Agreement criteria** — approved 2026-09-28, under the two-run protocol. Kept
for a later run 2; unused while there is none:

| Observable | Must match | Tolerance |
|---|---|---|
| `HeapPoolTest` — each of its 2 tests | exactly | pass/fail identical |
| `MemtableSizeUnslabbedTest` | exactly | pass/fail identical |
| Resolved limit per capacity value (startup log) | exactly | same bytes |
| Scenario A peak ÷ limit, per value | in shape | both runs between 0.95 and 1.00; ordering across the four values identical |
| Writers waiting in B (`BlockedOnAllocation` count rises; frame at `MemtableAllocator.java:195`) | exactly, as yes/no per value | counts themselves not compared |
| Scenario C excess ≤ Byteman byte sum | exactly, as yes/no per value | magnitudes within a factor of 2 |
| Idle heap (control run) | in shape | within 20% |

## 2. Environment

| Field | Run 1 (AI) | Run 2 (Jingsong, if done) |
|---|---|---|
| Date | 2026-09-28 (unit tier); 2026-09-29 (cluster tier) | |
| Node (CloudLab name and type) | `node0.jason92-317394` (40 cores, 125 GiB) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local `cassandra-src` clone commit | `b5f2a54` (`~/cassandra-run1`) | |
| Case-file commit / harness commit | `98ad478` / `66ebf93` | |
| Storage for node data | local `/dev/sda3` (ext3) | |
| Full logs (path, outside the repo) | node0 `~/stage4-logs/` (unit); `~/stage4-logs/cluster/<value>/` (cluster) | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Approved (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | 1 | §9c, unit tier | Non-blocking. §9c says to restore `HeapPoolTest` from `git show e90423c^:…`; the stage-4 README says to use the committed harness. Run 1 used the harness copy (`66ebf93`); its code is the same as the history copy, apart from one comment line. | Point §9c at `harness/memtable_heap_space-tryAllocate-limit/HeapPoolTest.java`. | 2026-09-28 | `745c1ab` |
| 2 | 1 (cluster) | §9d, Real heap | Non-blocking. `GC.run` and `GC.heap_info` are two commands 1–2 s apart. With stress running, `used` includes the young generation allocated in between: at 128 MiB, end of A, `used` was 754,558 K, of which 557,056 K (34 regions × 16 MiB) was young — 4× the limit, and misleading. (Also: the first cluster script omitted the end-of-A/B samples; a script error, fixed, not a runbook defect.) | §9d: read `used` minus the young-generation figure on the `N young (…K)` line, and compare it with idle's same figure plus the limit. | 2026-09-29 | `5ad5c16` |

Cluster tier (2026-09-29): no blocking defect. The instrument check and each of the five node runs passed every check in `cluster-run.sh` on the first attempt. One non-blocking defect (#2, §9d's heap reading) was approved 2026-09-29 and fixed in §9d.

## 4. Run 1 — AI session

**Scope:** unit tier 2026-09-28; cluster tier 2026-09-29.
**Cluster command log:** [`memtable_heap_space-tryAllocate-limit/run1/cluster-run.sh`](memtable_heap_space-tryAllocate-limit/run1/cluster-run.sh) (`instrument`, `value 128`, then `rest`). Full logs on node0: `~/stage4-logs/cluster/<value>/session.log` (every command and its output), `summary.txt`, thread dumps, `system-log-key-lines.txt`, `escape-hatch.txt`. Repo excerpts, per value: [`memtable_heap_space-tryAllocate-limit/run1/cluster/<value>/`](memtable_heap_space-tryAllocate-limit/run1/cluster/) — `summary.txt`, `cassandra.yaml.diff`, `submit-l.txt`, `limit-flush-lines.txt`; plus `instrument-check-*.txt` and one thread-dump stack (`threaddump-excerpt-128MiB-B1.txt`).
**Unit-tier command log:** [`memtable_heap_space-tryAllocate-limit/run1/unit-run.sh`](memtable_heap_space-tryAllocate-limit/run1/unit-run.sh), run under `script`; full log on node0 at `~/stage4-logs/run1-unit/session.log` (856 lines); excerpt in [`memtable_heap_space-tryAllocate-limit/run1/unit-session-excerpt.txt`](memtable_heap_space-tryAllocate-limit/run1/unit-session-excerpt.txt), JUnit test cases in [`memtable_heap_space-tryAllocate-limit/run1/unit-junit-testcases.txt`](memtable_heap_space-tryAllocate-limit/run1/unit-junit-testcases.txt).

### 4.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Local clone HEAD | `b5f2a54210d541339c2e7c17a794195cac0e67c2` | excerpt, log line 4 |
| Harness copy = file compiled | same SHA-256 `ecbafe55…` for both | excerpt, log lines 7–8 |
| `HeapPoolTest` (suite) | `Tests run: 2, Failures: 0, Errors: 0, Skipped: 0` | excerpt, log line 109 |
| — `testBlocksThenUnblocksOnRelease` | pass (0.768 s) | `unit-junit-testcases.txt` |
| — `testForcesThroughWhenOpGroupIsBlocking` | pass (0.001 s) | `unit-junit-testcases.txt` |
| `MemtableSizeUnslabbedTest` (suite) | `Tests run: 3, Failures: 0, Errors: 0, Skipped: 0` | excerpt, log line 222 |
| — pool type in use | `Memtables allocating with on-heap buffers`; `allocation type unslabbed_heap_buffers` | excerpt, log lines 359, 472 |
| — `testSize[skiplist]` (the case's path) | accounted on-heap 83.842 MiB vs. measured deep size 83.911 MiB: 70.1 KiB (0.08%) apart; test bound 3% | excerpt, log lines 548–550 |
| — `testSize[skiplist_sharded]` | 83.842 MiB vs. 83.913 MiB: 72.3 KiB apart | excerpt, log lines 648–650 |
| — `testSize[trie]` | 76.564 MiB vs. 76.568 MiB (after the test's trie adjustment): 3.6 KiB apart | excerpt, log lines 758–760 |
| Both `ant` invocations | `BUILD SUCCESSFUL`, exit 0 | excerpt, log lines 117–120, 850–853 |

**Cluster tier** — one node, `unslabbed_heap_buffers`, `memtable_cleanup_threshold: 0.99` (control: default), `-Xms4G -Xmx4G`, `durable_writes = false`, Byteman rule loaded from startup. Source for every row: `run1/cluster/<value>/summary.txt` (repo copy) unless another file is named. Wait-timer numbers are the raw values `sjk` printed; the unit was not checked (Cassandra timers normally report microseconds).

| Reading | 128 MiB | 256 MiB | 512 MiB | default | Control: 256 MiB, default threshold |
|---|---|---|---|---|---|
| Limit in the startup log | 128 MiB | 256 MiB | 512 MiB | 1024 MiB | 256 MiB |
| `Memtables allocating with on-heap buffers` (debug.log) | yes | yes | yes | yes | yes |
| Idle real heap, after `GC.run` | 75,559 K | 75,562 K | 75,561 K | 75,560 K | 75,560 K |
| Idle `BlockedOnAllocation` count | 0 | 0 | 0 | 0 | 0 |
| **A** — first limit flush, after stress start | 7.1 s | 7.6 s | 8.6 s | 9.7 s | 7.1 s |
| **A** — `Usage` at that flush | 127.305 MiB (99%) | 254.118 MiB (99%) | 511.126 MiB (100%) | 1014.648 MiB (99%) | 85.681 MiB (**33%**) |
| **A** — `Used total` (on-heap) | 0.99 | 0.99 | 0.99 | 0.99 | 0.33 |
| **A** — wait count, read 1–2 s after the flush was enqueued | 64 | 32 | 0 | 0 | 160 |
| **B** — thread dumps with 32 frames at `MemtableAllocator.java:195` (of 3) | 2 | 3 | 3 | 3 | 2 |
| **B** — wait count: at A → after the 4th limit flush → at the percentile read | 64 → 185 → 281 | 32 → 128 → 160 | 0 → 96 → 128 | 0 → 96 → 96 | 160 → 224 → 256 |
| **B** — wait timer p50 / p95 / max (raw) | 654,949 / 1,629,722 / 1,629,722 | 1,131,752 / 1,955,666 / 1,955,666 | 2,346,799 / 3,379,391 / 5,839,588 | 5,839,588 / 8,409,007 / 8,409,007 | 263,210 / 1,629,722 / 1,629,722 |
| Whole run — `MEMTABLE_LIMIT` flushes of `keyspace1.standard1` | 23 | 14 | 9 | 6 | 29 |
| Whole run — largest `Usage` of any `keyspace1` flush (`limit-flush-lines.txt`) | 127.979 MiB (99.98%) | 254.792 MiB (99.53%) | 511.126 MiB (99.83%) | 1015.394 MiB (99.16%) | 87.551 MiB (34.2%) |
| Whole run — largest `Used total` (on-heap) | 1.00 | 0.99 | 0.99 | 0.99 | 0.68 |
| **C** — wait count rising, just before `nodetool flush` | 673 → 830 | 320 → 384 | 224 → 256 | 128 → 160 | not run |
| **C** — `nodetool flush` returned after | 1 s | 3 s | 4 s | 10 s | not run |
| **C** — any `Used total` above 1.00 | none | none | none | none | not run |
| Byteman trace — total | 1,511 calls, 1,263,250 B | 330 calls, 266,200 B | 320 calls, 260,535 B | 288 calls, 234,204 B | **no file** |
| — window A (stress start → first limit flush) | 0 calls, 0 B | 0 calls, 0 B | 6 calls, 5,864 B | 44 calls, 40,380 B | — |
| — window B (→ C's `nodetool flush`; control: → stop) | 1,267 calls, 1,062,282 B | 95 calls, 78,752 B | 95 calls, 73,034 B | 0 calls, 0 B | — |
| — window C (→ node stop) | 244 calls, 200,968 B | 235 calls, 187,448 B | 219 calls, 181,637 B | 244 calls, 193,824 B | — |
| Trace total as a share of the limit | 0.94% | 0.099% | 0.049% | 0.022% | 0 |
| Trace `limit` field = knob in bytes | yes | yes | yes | yes | — |
| Client `WriteTimeoutException` lines in `stress.txt` (symptom only) | 0 | 96 | 1,469 | 2,111 | 0 |
| Checks passed in `session.log` / node stopped, `pgrep` empty | 12 / yes | 12 / yes | 12 / yes | 12 / yes | 11 / yes |

Other readings: `Submit -l` lists the `allocated(long)` trigger in every run (`submit-l.txt`). The instrument check passed: 2 tests, 0 failures, one trace line `forced=1 limit=100` (`instrument-check-*.txt`). Each run's `Enqueuing flush` reasons at B's end were 33 `INTERNALLY_FORCED` plus the limit flushes; none of the 33 is on `keyspace1` in any run, and the 128 MiB run's 33 are all `system`/`system_schema` flushes between startup and the first limit flush (`system-log-key-lines.txt`). At B's end, tablestats show memtable cells outside `keyspace1` only in tiny system tables (1–27 cells each).

**Real-heap pass** — a second, separate pass (`cluster-run.sh heap`: the same five values, A and B only, no C; folders `run1/cluster/<value>-heap/`), because the first pass sampled heap only at idle. `jcmd GC.run`, then `jcmd GC.heap_info`, at the end of A and of B. `heap_info` printed no old-generation line, so "non-young" = `used` − young. All sizes in K (region size 16,384 K).

| Value | Sample | `used` | Young | `used` − young | Idle (`used` − young) + limit | Excess | Excess ÷ limit |
|---|---|---|---|---|---|---|---|
| 128 MiB | end A | 754,558 | 557,056 (34 regions) | 197,502 | 173,866 | +23,636 | 18.0% |
| 128 MiB | end B | 269,956 | 65,536 | 204,420 | 173,866 | +30,554 | 23.3% |
| 256 MiB | end A | 358,578 | 32,768 | 325,810 | 304,939 | +20,871 | 8.0% |
| 256 MiB | end B | 382,328 | 49,152 | 333,176 | 304,939 | +28,237 | 10.8% |
| 512 MiB | end A | 725,483 | 147,456 | 578,027 | 550,698 | +27,329 | 5.2% |
| 512 MiB | end B | 637,617 | 49,152 | 588,465 | 550,698 | +37,767 | 7.2% |
| default (1024 MiB) | end A | 1,118,109 | 16,384 | 1,101,725 | 1,091,375 | +10,350 | 1.0% |
| default (1024 MiB) | end B | 1,172,007 | 65,536 | 1,106,471 | 1,091,375 | +15,096 | 1.4% |
| control (256 MiB) | end A | 451,277 | 114,688 | 336,589 | 304,942 | +31,647 | 12.1% |
| control (256 MiB) | end B | 385,967 | 49,152 | 336,815 | 304,942 | +31,873 | 12.2% |

Idle `used` was 75,562 / 75,563 / 59,178 / 75,567 / 75,566 K for 128 / 256 / 512 MiB / default / control; idle young was 32,768 K in all five, so idle non-young was 42,794 / 42,795 / 26,410 / 42,799 / 42,798 K. The baseline column uses idle non-young + limit, which is like for like. Using the idle `used` instead shifts every excess down by idle's 32,768 K young, giving −22 to +5 MiB. Source: `run1/cluster/<value>-heap/heap-{idle,endA,endB}.txt` and `summary.txt`.

### 4.2 Conclusion and logic — unit tier

1. **Validity — valid for the unit tier.**
   - The code under test is the pinned tag [observed: log line 4] and the committed harness [observed: log lines 7–8].
   - `HeapPoolTest` reaches the limit: it asserts `pool.onHeap.used() == LIMIT` (100 bytes) before the over-limit call, and the suite passed [observed: log line 109; assertion at harness `HeapPoolTest.java:94`].
   - `MemtableSizeUnslabbedTest` ran on the `HeapPool` path, not the default `SlabPool` [observed: log lines 359, 472].
   - The §9b "hold fixed" settings are cluster settings and do not apply to this tier.
2. **Readings — nothing unusual.** Every test passed. The accounting gap on the case's path (skiplist) is 0.08%, far inside the 3% bound [observed: log line 550]. The two extra memtable types (sharded, trie) also passed; they are outside this case's path.
3. **Matched row — the unit-tier part of "Confirmed", together with "Escape hatch as recorded".** The unit tier covers §9a procedure step 1 only.
   - *The check refuses at the limit and the writer waits:* `testBlocksThenUnblocksOnRelease` passed, so the over-limit `allocate()` did not return within 300 ms [observed: pass; assertion at `HeapPoolTest.java:106–112`]. That it was **waiting at the decision point**, not merely slow, is [inferred: the test proves this by timing only; it takes no thread dump].
   - *The counter does not grow while the writer waits:* `used() == LIMIT` after the timeout [observed: pass; `HeapPoolTest.java:114`].
   - *Freeing capacity wakes the writer:* after `released(50)`, the call completes and `used() == LIMIT − 50 + 1` [observed: pass; `:119–125`].
   - *The escape hatch forces a write through, by exactly its own size:* after `markBlocking()`, a 1-byte call returns and `used() == LIMIT + 1` [observed: pass; `:146–156`]. So the excess (1 byte) equals the bytes forced through (1 byte), which is §9a's "Escape hatch as recorded" row in miniature.
   - *The counter tracks real heap:* accounted on-heap within 0.08% of the measured deep size [observed: log line 550].
4. **Excluded rows.**
   - *Refuted — "passes the limit by more than the escape hatch explains":* excluded at this tier; the only excess was the 1 forced byte [observed: `:155`].
   - *Refuted — "real heap grows well beyond the counter":* excluded for the memtable's own data; the gap is 0.08% [observed: log line 550]. The test measures the memtable object graph with jamm, not whole-JVM heap [inferred: from the test's log text "Memtable deep size"], so the cluster tier's heap reading is still needed.
   - *Refuted — "peak flat across the four values":* **not testable** at this tier; the unit tests use one limit each.
   - *Not confirmed — "no writer ever waits":* excluded; the over-limit call waited [observed: pass at `:112`].
   - *Invalid run:* excluded; the limit was reached [observed: `:94`].
5. **Observed vs. inferred — what the conclusion rests on that was not directly seen:**
   - The wait is inferred from a timeout, not seen in a thread dump.
   - `HeapPoolTest` builds a `HeapPool` directly, so it tests the shared `SubPool`/`SubAllocator` code, not the `cassandra.yaml` → pool path. That path was seen only in `MemtableSizeUnslabbedTest`'s log lines.
6. **Deviations and gaps.**
   - Used the committed harness copy instead of the `git show` step in §9c (defect #1). Same test code.
   - The unit tier cannot show the dose-response (the peak moving with the knob) or the cluster-only instruments (`BlockedOnAllocation`, flush log lines). Those need the cluster tier and, for scenario C, the unwritten Byteman rule.

**Conclusion (one line):** unit tier — consistent with **Confirmed** and **Escape hatch as recorded**; no Refuted row fired. The case's verdict still needs the cluster tier.

### 4.3 Conclusion and logic — cluster tier

Cites `run1/cluster/<value>/summary.txt` unless another file is named; "table" means the cluster table in §4.1.

1. **Validity — valid for all four values and the control.**
   - The limit took effect and the `HeapPool` was built at every value: startup line and debug.log line, and the resolved limit equals the knob (the default resolved to 1024 MiB, one quarter of the 4 GiB heap) [observed: `system.log`/`debug.log`/`resolved on-heap limit` lines].
   - The instrument was in place: `Submit -l` lists the trigger at every value, the JVM had `-Xms4G -Xmx4G` and the agent, and every trace line's `limit` equals the knob in bytes [observed: `submit-l.txt`; `jvm-args.txt` on node0; last trace row of the table].
   - The workload made writers wait in all four 0.99 runs, so §9a's *Invalid run* row does not apply; flushes started at 99% of the limit, not below it [observed: table, A and B rows].
   - Nothing else disturbed the pool: the yaml diff is exactly the three intended lines per run, `keyspace1` had `durable_writes = false`, none of the 33 `INTERNALLY_FORCED` flushes touched `keyspace1`, and no other table held more than 27 memtable cells [observed: `cassandra.yaml.diff`; `keyspace1.txt` on node0; §4.1 "Other readings"].
2. **Readings — nothing unusual, with two features worth checking.**
   - The peak follows the knob: the first limit flush started at 127.3, 254.1, 511.1 and 1014.6 MiB, which is 99.5%, 99.3%, 99.8% and 99.1% of the limit [observed: table, A rows].
   - The wait length grows with the knob (p50 0.65, 1.13, 2.35, 5.84 in raw units) and so does the client's write-timeout count (0, 96, 1,469, 2,111) [observed: table, B row and last rows].
   - The escape hatch fired in every 0.99 run, in both A/B and C windows, and forced 0.02–0.94% of the limit through in total [observed: trace rows]. Per call it forced about 800 bytes (181–201 KB in 219–244 calls in window C).
   - In the control, flushes started at 33% (85.7 MiB), the largest `Used total` at any flush start was 0.68, **writers still waited** (count 160 → 256), and the rule recorded no forced-through call at all [observed: control column].
3. **Matched row — Confirmed**, at all four values, with the escape hatch exercised and its size recorded.
   - *Writers wait, not rejected:* the count rose in B in every run, and 11 of the 12 thread dumps show all 32 `MutationStage` threads at `MemtableAllocator.java:195`. That is the wait itself, not a timeout inference. It answers the unit-tier review's note on part 5 [observed: table, B rows; frame counts in `summary.txt` and `threaddump-excerpt-128MiB-B1.txt`].
   - *The peak follows the knob:* see part 2 (agreement band 0.95–1.00 met; order across the four values follows the knob) [observed].
   - *The counter does not pass the limit except through the escape hatch:* no logged `Usage` or `Used total` is above the limit — the largest `Usage` is 99.98%, 99.53%, 99.83%, 99.16% of it, and the largest `Used total` is 1.00 [observed: table]. That the counter did not grow while writers waited, and that it exceeded the limit by no more than the forced bytes, is [inferred: see part 5].
   - *The escape hatch, recorded:* per whole run 1.26 MB, 266 KB, 261 KB, 234 KB of forced bytes; in window C 181–201 KB, about 32 writers × one ~5 KiB write [inferred: the write size is an estimate from 5 columns × 1024 B, not traced] (Target-3 material).
   - *The counter tracks real heap, at the cluster tier too:* after `GC.run`, with the young generation subtracted, heap is within +37 MiB / −22 MiB of idle + limit at all ten samples [observed: real-heap table]. The excess does not grow with the knob (at end of A: 18%, 8%, 5%, 1% of the limit for 128, 256, 512 MiB and default), which looks like a roughly fixed overhead of the node, 10–37 MiB [inferred: not attributed]. The unit tier's jamm reading (0.08%) stays the primary evidence for counter vs. memory; this is supporting evidence under real load.
   - §9a's *Escape hatch as recorded* row was **not matched on its own terms**: it needs the counter observed above the limit, and no reading showed that (part 5).
   - *Control (no §9a row depends on it):* the default flush trigger starts flushes at a third of the limit (85.7 MiB), as §9b predicts, but at this workload writers waited anyway, about as often as at 0.99. So the trigger sets where flushes start; it did not keep writers from reaching the limit here [observed]. Why the pool refilled during a flush is [inferred: flushes finish slower than 256 clients fill memory].
4. **Excluded rows.**
   - *Refuted — "peak flat across the four values":* excluded; the peak moved with the knob and each startup log shows the new limit [observed: table].
   - *Not confirmed — "peak follows the knob but no writer waits":* excluded; the count rose and threads were seen waiting [observed].
   - *Invalid run:* excluded (part 1) [observed].
   - *Refuted — "passes the limit by more than the escape hatch explains":* **not excluded by measurement.** The counter's excess was never read (part 5). No reading supports the row: nothing logged is above the limit. `Used total` has two decimals (about 0.6 MiB at 128 MiB, 5 MiB at 1024 MiB), which is not fine enough to exclude an excess of a few hundred KB.
   - *Refuted — "real heap grows well beyond the counter":* excluded. Unit tier: 0.08% for the memtable's own graph [observed]. Cluster tier: within +37/−22 MiB of idle + limit once the young generation is subtracted [observed]. The raw `used` reading alone would have looked like a refutation: 754,558 K at 128 MiB, end of A, of which 557,056 K is young.
5. **Observed vs. inferred — what the conclusion rests on that was not directly seen:**
   - No gauge exposes the counter. `Used total` and `Usage` are logged only when a flush starts, so the counter was never read while writers waited or while the escape hatch forced writes through. "Does not grow while waiting" and "excess ≤ forced bytes" rest on the unit tier (`testBlocksThenUnblocksOnRelease`, `testForcesThroughWhenOpGroupIsBlocking`) plus the absence of any logged value above the limit.
   - Which flush's blocking mark caused each forced call is not in the trace; that they come from flush barriers is [inferred: the rule's comment and the case's §6b], consistent with calls appearing only in windows that contain a flush start or a `nodetool flush`.
   - "Young" is what was allocated between `GC.run` and `GC.heap_info` (two `jcmd` calls, 1–2 s apart, stress running at full rate) [inferred from how G1 reports regions; no GC log was taken]. It may include some newly added live memtable data, but the pool was at its limit with writers waiting, so little can have been added [inferred; the counter itself was not read at the sample moment]. The 10–37 MiB fixed excess is not attributed to a component.
   - The wait length growing with the knob, and its cause (bigger flushes take longer), is [inferred]; the timer unit was not checked.
   - "No writer waited before A's flush" is untested at 128 and 256 MiB (counts of 64 and 32 were read after the flush was enqueued); at 512 MiB and default the count was still 0 at that read.
6. **Deviations and gaps.**
   - **Real heap was sampled in a second pass.** §9d asks for `GC.run` + `GC.heap_info` at the end of A and B; the first-pass script took it only at idle (a script omission). The `heap` pass repeats A and B at all five values (no C), so its flushes, wait counts and timings are new runs, not the first pass's. The script changed between the passes; the first version is kept at `~/stage4-logs/cluster/cluster-run.sh.pass1-copy` on node0.
   - **Runbook defect #2 (§3, approved and fixed 2026-09-29):** the raw `used` figure includes the young generation and misleads (754,558 K at 128 MiB, end of A). The conclusion above uses `used` − young. The 512 MiB idle baseline is lower than the other four (59,178 K vs about 75,560 K; non-young 26,410 K vs about 42,800 K), so the 512 MiB excesses depend on which idle figure is used.
   - Deviation: the script unsets `JVM_EXTRA_OPTS` and `MAX_HEAP_SIZE` after the node starts, so the Byteman agent (port 9091) does not load into the stress, `nodetool` and `cqlsh` JVMs. The node's environment matches §9e.
   - Wait counts and percentiles were read with `nodetool sjk` (a new JVM, 1–2 s per attribute), so each reading lags its trigger and B's "after" figures come a few seconds after the 4th flush. Each of the percentile attributes is a separate call.
   - Dump 3 at 128 MiB and dump 1 of the control show 0 waiting frames: the flush had finished, or the pool was not full at that instant [observed].
   - The clone's commit is not written in the cluster run logs; it was `b5f2a54` (`cassandra-5.0.9`) when checked just before the runs. `logs/` was moved at each run's start as §9e says; the last run's `logs/` was moved into its own folder at the end.
   - The control has no trace file. Per §9e that means no allocation was forced through (`Submit -l` shows the rule was loaded).
   - `stress.txt` "error" line counts are mostly stress's own header lines at 128 MiB and in the control; at 256 MiB and above they are client `WriteTimeoutException`s. Timeouts are a symptom, not evidence (§9d).

**Conclusion (one line):** cluster tier — consistent with **Confirmed** at 128, 256, 512 MiB and the default: writers wait (seen in thread dumps), the peak follows the knob, and the escape hatch forced 0.02–0.94% of the limit through; real heap, with the young generation subtracted, stays within +37/−22 MiB of idle + limit at every sample; **not measured:** the counter's excess over the limit (only inferred). The verdict is Jingsong's.

## 5. Review of run 1 — Jingsong

### 5.1 Check of run 1's conclusion — unit tier

Reviewed 2026-09-29.

| Part | Agree? | Note |
|---|---|---|
| 1. Validity | yes | |
| 2. Readings | yes | |
| 3. Matched row | yes | |
| 4. Excluded rows | yes | |
| 5. Observed vs. inferred | yes | The wait is inferred from a timeout; it may need verifying later with a thread dump. |
| 6. Deviations and gaps | yes | |

### 5.1b Check of run 1's conclusion — cluster tier

Reviewed 2026-09-29 (§4.3). Filled in by the AI session on 2026-09-30, after Jingsong reported the review done: all six parts recorded as agreed. Amend any row Jingsong did not agree with.

| Part | Agree? | Note |
|---|---|---|
| 1. Validity | yes | |
| 2. Readings | yes | |
| 3. Matched row | yes | Confirmed; the wait is now seen in thread dumps, which answers the unit-tier note on part 5. |
| 4. Excluded rows | yes | "Passes the limit by more than the escape hatch explains" is not excluded by measurement (counter never read). |
| 5. Observed vs. inferred | yes | The counter's excess over the limit is inferred, not read. |
| 6. Deviations and gaps | yes | |

### 5.2 Run 2?

**No** — decided 2026-09-29, with the change to the protocol that made run 2
optional. This covers both tiers.

## 6. Run 2 — Jingsong (optional)

Not done (§5.2). §7 is left out.

## 8. Verdict — Jingsong

| Tier | Verdict (§9a row) | Basis | Date |
|---|---|---|---|
| Unit | Consistent with **Confirmed** and **Escape hatch as recorded**; no Refuted row fired | run 1 + review | 2026-09-29 |
| Cluster | Consistent with **Confirmed** at 128, 256, 512 MiB and the default. **Escape hatch as recorded** not matched on its own terms: the counter was never read above the limit (the forced bytes were measured separately, by the Byteman trace). No Refuted row fired. Not measured: the counter's excess over the limit (inferred, not read). | run 1 + review (2026-09-29), no run 2 | 2026-09-30 |

**Feedback filed:** the case file's §10 "Stage-4 feedback" field updated for
both tiers (unit: `bf1f6bb`; cluster: `5ad5c16`). Sections amended: §9c
(runbook defect #1, `745c1ab`); §9a's Confirmed row, §9c and §9e, before the
cluster tier (`bf1f6bb`); §9d's "Real heap" row (runbook defect #2, `5ad5c16`).
§8's ceiling claim and the Target-3 note: not amended.
