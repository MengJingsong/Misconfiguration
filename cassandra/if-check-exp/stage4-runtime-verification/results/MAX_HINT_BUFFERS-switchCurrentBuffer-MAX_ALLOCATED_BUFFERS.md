# MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS — stage-4 results  <!-- file: results/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS.md -->

> **Case:** [`MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS`](../../stage3-ai-deep-read/cases/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS.md)
>
> **Status:** **audited 2026-09-30** (Ready after amendments); harness written and checked on node0 (unit instrument check passed, hold rule type-checked only); no run yet

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | `git hash-object` `400b80049d85b0b1ea71ffaa7bda4a4cfc58ebc3`, on top of HEAD `e462a97`, recorded 2026-09-30 after the audit's amendments and the two instrument-check fixes in §3 (not yet committed). The first freeze, `65a66cb…`, was superseded before any run. §9a is frozen at this version |
| **Harness** | written 2026-09-30, not yet committed: `HintsPoolCeilingTest.java`, `hints-pool.btm`, `hold-flush.btm` and a README under `../harness/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS/`. Checks: see §1.2 |
| **Tiers and values** | Unit first: upstream `HintsBufferPoolTest` and `HintsPoolCeilingTest` at *n* = 2, 3, 6, plus *n* = 3 with 2 MiB buffers. Then cluster: *n* = 2, 3, 6, the second-knob arm, the natural-load control. *n* = 1 is excluded (case §9b) |
| **Audit bottom line** | **Ready after amendments** — 2026-09-30. Work still open before run 1 (step 1, not a design defect): add the second-node setup to `environment.md` (cluster tier only) and run the hold-rule check that needs it (case 9e, "Instrument check, hold rule"). Done 2026-09-30: harness written; node0 has JDK 11, Ant, the clone at `cassandra-5.0.9` and `byteman-bmunit-4.0.20.jar` |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Case §4, §7, §8: off-heap direct `ByteBuffer`s, total bytes = `n × bufferSize`. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 9b: *n* = 2, 3 (default), 6, plus a second-knob arm on `bufferSize`. *n* = 1 is excluded with a reason that holds in the source (flush callback runs only after `switchCurrentBuffer()` returns, `HintsBufferPool.java:79-80`; `take()` at `:118`). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | 9d: direct-memory MBean plus NMT cross-check, and a create trace as the counter, because no gauge exposes `allocatedBuffers`. |
| A. Core question | usage driven to the limit and past it | Met | 9a scenarios A (reach) and B (try to exceed); 9c's hold rule makes B deterministic rather than a race. |
| B. Logic | each step says what it establishes | Met | 9a procedure 1–4 and 9e each state a purpose (idle floor, reach, exceed, release). |
| B. Logic | prediction stated in numbers or a clear relation | Partly | Numbers given (64/96/192 MiB), but no tolerance, and the cluster can measure only the rise over idle, `(n − 1) × bufferSize`. **Applied:** reading rule with a 4 MiB band (9a). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | Missing: second-knob arm disagreeing, and a writer that never resumes after the hold. **Applied:** two rows (9a). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | 9a Confirmed row needs both; direct evidence is the `waiting` trace line plus a thread dump at `HintsBufferPool.java:118` (9d). |
| B. Logic | alternative explanations and their controls | Met | Idle control, natural-load control, hints-flowing control; other direct-buffer users and in-flight-hint overload named as non-evidence (9d). |
| C. Specific | a human can follow it from the intro and §9a | Met | Readable on its own. The Confirmed row mixed the unit and cluster quantities; fixed with the reading rule. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | One gap: the unit test needs the schema defined first. **Applied:** `defineSchema()` (9e). The harness it runs does not exist yet (see D). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met | Commands with placeholders, values, sampling times. B's stop condition was a bare "about 60 s"; **applied:** early-stop rule on `HintsInProgress` (9e). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | Listed as work in 9c and in §1 above, none exists yet: three harness files, the second-node setup, Byteman attach on this JDK. Acceptable under the README rule (listed as work for step 1). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly | Reaches it: about 44,000 rows force a wait at *n* = 6, against 200,000 (about 1 GB of hints, which fits the 63 GB local disk); under the hold one buffer returns per 3 s. Gap: the in-flight hint limit (`128 × cores`) could end B early on a small node. **Applied:** estimate and stop rule (9c, 9e). |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | About 35 citations checked at tag `cassandra-5.0.9` (files fetched from GitHub raw; this machine has no clone): pool `:41,:46,:79-80,:107,:112-113,:118,:125,:130-134`; `HintsService` `:79,:110,:111,:116-121,:169-171`; `HintsWriteExecutor` `:50,:60,:88-94,:141-154,:168`; `HintsBuffer` `:75-78,:96-100`; `CassandraRelevantProperties:351`; `DatabaseDescriptor` `:898-901`; `Config` `:180,:397`; `StorageProxy` `:202,:1592-1597,:2444-2447,:2801`; `build.xml:1192`; `HintsBufferPoolTest:49-73`; `HintsBufferTest:196`; both yaml defaults. No mismatch. Not re-checked: the absence of a pool gauge in `metrics/`, NMT figures, Byteman behaviour. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Add a reading rule: unit `Count` +*n*, `MemoryUsed` +`n × bufferSize`; cluster `Count` +(*n* − 1), `MemoryUsed` +(*n* − 1) × `bufferSize` over idle, 4 MiB band | Applied 2026-09-30, case 9a (uncommitted) | The conclusions need a decidable threshold, and the cluster cannot measure from a no-pool baseline. A 4 MiB band is an eighth of the smallest step (32 MiB), so it cannot hide an extra buffer |
| 2 | Reword the Confirmed and third Refuted rows to the predicted amount; add rows for "second-knob arm disagrees" and "writer never resumes" | Applied 2026-09-30, case 9a | Both outcomes were plausible and had no row |
| 3 | Add the in-flight hint estimate and an early stop for B on `HintsInProgress` > 75 % of `128 × cores`; sample it every 5 s | Applied 2026-09-30, case 9c, 9e | `StorageProxy.java:202` makes the limit scale with cores; the estimate (about 1,900 in 60 s, marked as not measured) approaches it on a 16-core node |
| 4 | Note `max_hint_window` (3 h) under "Hold fixed" and in the hints-flowing trap; record when node 2 was stopped | Applied 2026-09-30, case 9b, 9d | `StorageProxy.java:2461-2463`: a long sweep would stop hinting silently |
| 5 | Call `HintsBufferTest.defineSchema()` in the harness test | Applied 2026-09-30, case 9e | The hint helper needs the schema |
| 6 | Scope `JVM_EXTRA_OPTS` to the `bin/cassandra` command (`VAR=… bin/cassandra`) instead of `export` | Applied 2026-09-30, case 9e | The handoff's heap-run lesson says it clashed on the Byteman port in the `nodetool` and stress JVMs; the scripts say it should not, and scoping is free |
| 7 | For the stage-3 template: have each conclusions row use the quantity each tier can actually measure, and give the workload's hidden limits (here the in-flight hint limit) in the estimate | Left for stage 3 | Both gaps above came from the template not asking for them |

**Checked:** whether exporting `JVM_EXTRA_OPTS` in 9e reaches `nodetool` or
`cassandra-stress`. Read from the scripts at the pinned tag, not run: only
`conf/cassandra-env.sh:307`, which `bin/cassandra` sources, reads it;
`bin/nodetool:112` and `tools/bin/cassandra-stress:40` use `$JVM_OPTS`. That
reading does not reproduce the clash the handoff's heap-run lesson (3) names, so
the audit does not treat it as a defect. Because scoping it costs nothing, it is
also recommendation 6.

### 1.2 Instrument checks

Checks of the instruments, not readings of the case (README, step 1). Run on
node0 (`pc66`, 40 cores, JDK 11.0.32, local clone `~/cassandra-run1` at
`cassandra-5.0.9`); logs are on node0 under `~/stage4-logs/hints/`.

| Check | Result |
|---|---|
| Byteman `TestScript` (parse and type-check against `build/classes/main`) on `hints-pool.btm` | both rules parsed and type-checked: "no errors" |
| Same on `hold-flush.btm` | rule parsed and type-checked: "no errors" |
| Unit: `HintsPoolCeilingTest` at *n* = 3, `bufferSize` 1 MiB, with `hints-pool.btm` attached (case 9e, "Instrument check, unit") | **Passed** on the sixth attempt, after the two fixes in §3 (`instrument-ant6.txt`, `unit-instrument.out`). Trace: exactly three `created` lines (`created=1,2,3`, each `max=3`, `size=1048576`), then `waiting` lines, as 9e expects. The test's own readings: `allocatedBuffers=3`, `queued=2`, `Count` +3, `MemoryUsed` +3,145,728, unchanged over 2 s and after one recycle, and 80,660 of 80,660 hints found across the buffers |
| Unit: the test without the agent, before the fixes | failed exactly as with the agent (`Count` +4, +128 B), so the agent is not what perturbs the direct-buffer readings (§3, defect 1). Not re-run without the agent after the fixes |
| Hold rule, functional (case 9e, "Instrument check, hold rule") | **Not done.** It needs a node that has hints to flush, so a second node |

These runs were at *n* = 3 only. The unit tier's values (*n* = 2, 6, and the
2 MiB arm) have not been run.

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | | |
| Node (CloudLab name and type) | | |
| CPU cores (`nproc`) — sets the in-flight hint limit `128 × cores` (case 9c) | | |
| Time node 2 was stopped, and time of each run (`max_hint_window`, case 9b) | | |
| OS and kernel (`uname -r`) | | |
| JDK (`java -version`) | | |
| Ant (`ant -version`) | | |
| Local `cassandra-src` clone commit | | |
| Case-file commit / harness commit | | |
| Storage for node data | | |
| Full logs (path, outside the repo) | | |

## 3. Runbook defects

Every step a run could not execute as written. The run stops at the
defect; the fix is made in the case file (dated) if it leaves §9a unchanged,
and the affected tier restarts from its beginning. If the fix would change
§9a, the case goes back to the audit. "None" if there were none.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | Instrument check, unit, *n* = 3 | 9e unit, step 1 | The exact deltas failed: `Count` +4 and `MemoryUsed` +3 MiB + 128 B instead of +3 and +3 MiB. Cause, traced with a throwaway Byteman rule (`trace-alloc-ant.txt` on node0): the first `Mutation.serializedSize()` on a thread creates a netty `FastThreadLocal` scratch `DataOutputBuffer` whose constructor calls `allocateDirect(128)` (`Mutation.java:453`, `DataOutputBuffer.java:87`). The first attempt, with no GC settle, also read `Count` +1, because garbage buffers were freed mid-test | The writer thread serializes one hint before the baseline, the JVM settles (`System.gc()`, 500 ms), then the baseline is read. Harness test and 9e step 1 | AI, 2026-09-30 | uncommitted (case-file hash `400b800…`) |
| 2 | Instrument check, unit (found by following 1 to its cause) | 9a reading rule; 9d "Real resource" | The same scratch buffer exists on every thread that serializes a mutation. In the cluster tier the 32 `MutationStage` threads each hold one, so the audit's rule "`Count` up by exactly *n* − 1" would fail for an unrelated reason | Cluster `Count` is reported, not asserted. `MemoryUsed` within the 4 MiB band and the create trace decide. Unit tier unchanged (exact, after the warm-up) | AI, 2026-09-30 | uncommitted (same hash) |

**Why these two fixes are not tuning.** Both change how the JVM-wide direct-buffer
counters are read, before any run of the case. The pool's own readings matched the
prediction on every attempt (`allocatedBuffers=3`, `queued=2`, `created=1,2,3`).
The ceiling claim, the prediction and the conclusions rows are unchanged.

## 4. Run 1

**Scope:** the tiers and capacity values actually run. **Command log:**
`MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS/run1/<file>`.

### 4.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|

**Cluster tier** — one row per capacity value, scenario and observable:

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|

### 4.2 Conclusion and logic

Tag every statement in parts 1–4 as **[observed: `<file>`]** or
**[inferred: `<reason>`]**. An untagged statement is not part of the
argument.

1. **Validity** — was the run valid? The limit was reached; each §9b "hold
   fixed" setting is confirmed, with its evidence. If not valid, stop here: the
   conclusion is "invalid run".
2. **Readings** — anything unusual in §4.1: a gap, an outlier, a reading that
   contradicts another.
3. **Matched row** — the §9a row, quoted, and the reading that satisfies each
   part of it.
4. **Excluded rows** — for every other §9a row, the reading that rules it out.
   Every **Refuted** row must be addressed.
5. **Observed vs. inferred** — list the inferred statements that the
   conclusion depends on. These are what the self-check most needs to check.
6. **Deviations and gaps** — anything skipped, changed or not observable, and
   how it limits the conclusion.

7. **Core question** — in two or three sentences: did usage follow the
   constraint, and does the constraint cap usage? Each step from reading to
   answer cites the part above that supports it.

**Conclusion (one line):** `<§9a row>` — confirmed / bypass as recorded /
refuted / not confirmed / invalid run.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-open every raw file the conclusion cites and confirm it says what the
conclusion says. A part that does not hold is fixed, or the conclusion is
downgraded to *Not confirmed*.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | | |
| 2. Readings | | |
| 3. Matched row | | |
| 4. Excluded rows | | |
| 5. Observed vs. inferred | | |
| 6. Deviations and gaps | | |
| 7. Core question — the steps from reading to answer follow the audited logic | | |

### 5.2 Run 2?

**Yes / no** — the reason, and the date decided. Choose yes when the conclusion rests on inferred statements, a part of §5.1 cannot be settled from run 1's evidence, or the result refutes the case or confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

"Not done" if §5.2 says no, and §7 is left out.

**Scope:** the tiers and capacity values actually run. **Command log:**
`MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS/run2/<file>`.

### 6.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|

**Cluster tier**

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|

### 6.2 Matched row

The §9a row these readings match, in one line.

## 7. Comparison — only if run 2 was done

| Observable | Run 1 | Run 2 | Criterion (§1) | Agree? |
|---|---|---|---|---|

**Same §9a row?** yes / no. If no, or if a reading disagrees: the cause, and
how it was resolved (see "Compare and decide" in the README).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its
date and reason.

| Tier | Verdict (§9a row) | Basis | Date |
|---|---|---|---|
| Unit | | run 1 + self-check / run 1 + run 2 | |
| Cluster | | run 1 + self-check / run 1 + run 2 | |

**Feedback filed:** the case file's §10 "Stage-4 feedback" field updated
(commit), and any section amended (which one, commit) — or "none needed".
