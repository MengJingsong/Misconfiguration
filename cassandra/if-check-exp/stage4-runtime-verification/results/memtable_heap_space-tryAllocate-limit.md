# memtable_heap_space-tryAllocate-limit — stage-4 results

> **Case:** [`memtable_heap_space-tryAllocate-limit`](../../stage3-ai-deep-read/cases/memtable_heap_space-tryAllocate-limit.md)
>
> **Status:** run 1 done (unit tier, 2026-09-28); run 2 not chosen; reviewed by Jingsong; unit-tier verdict filed (2026-09-29) — cluster tier not run

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
| Date | 2026-09-28 | |
| Node (CloudLab name and type) | `node0.jason92-317394` (40 cores, 125 GiB) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local `cassandra-src` clone commit | `b5f2a54` (`~/cassandra-run1`) | |
| Case-file commit / harness commit | `98ad478` / `66ebf93` | |
| Storage for node data | local `/dev/sda3` (ext3) | |
| Full logs (path, outside the repo) | node0 `~/stage4-logs/` | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Approved (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | 1 | §9c, unit tier | Non-blocking. §9c says to restore `HeapPoolTest` from `git show e90423c^:…`; the stage-4 README says to use the committed harness. Run 1 used the harness copy (`66ebf93`); its code is the same as the history copy, apart from one comment line. | Point §9c at `harness/memtable_heap_space-tryAllocate-limit/HeapPoolTest.java`. | 2026-09-28 | `745c1ab` |

## 4. Run 1 — AI session

**Scope:** unit tier only, 2026-09-28. Cluster tier not run.
**Command log:** [`memtable_heap_space-tryAllocate-limit/run1/unit-run.sh`](memtable_heap_space-tryAllocate-limit/run1/unit-run.sh), run under `script`; full log on node0 at `~/stage4-logs/run1-unit/session.log` (856 lines); excerpt in [`memtable_heap_space-tryAllocate-limit/run1/unit-session-excerpt.txt`](memtable_heap_space-tryAllocate-limit/run1/unit-session-excerpt.txt), JUnit test cases in [`memtable_heap_space-tryAllocate-limit/run1/unit-junit-testcases.txt`](memtable_heap_space-tryAllocate-limit/run1/unit-junit-testcases.txt).

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

**Cluster tier** — not run.

### 4.2 Conclusion and logic

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

## 5. Review of run 1 — Jingsong

### 5.1 Check of run 1's conclusion

Reviewed 2026-09-29.

| Part | Agree? | Note |
|---|---|---|
| 1. Validity | yes | |
| 2. Readings | yes | |
| 3. Matched row | yes | |
| 4. Excluded rows | yes | |
| 5. Observed vs. inferred | yes | The wait is inferred from a timeout; it may need verifying later with a thread dump. |
| 6. Deviations and gaps | yes | |

### 5.2 Run 2?

**No** — decided 2026-09-29, with the change to the protocol that made run 2
optional.

## 6. Run 2 — Jingsong (optional)

Not done (§5.2). §7 is left out.

## 8. Verdict — Jingsong

| Tier | Verdict (§9a row) | Basis | Date |
|---|---|---|---|
| Unit | Consistent with **Confirmed** and **Escape hatch as recorded**; no Refuted row fired | run 1 + review | 2026-09-29 |
| Cluster | | | |

**Feedback filed:** the case file's §10 "Stage-4 feedback" field updated
(commit), and any section amended (which one, commit) — or "none needed".
