# MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS — stage-4 results  <!-- file: results/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS.md -->

> **Case:** [`MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS`](../../stage3-ai-deep-read/cases/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS.md)
>
> **Status:** **unit tier: run 1 done 2026-09-30, self-checked, verdict filed** (consistent with Confirmed). Cluster tier not started: it needs the second-node setup and the hold-rule check. Run 2 not chosen.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Committed in `0598801` (2026-09-30). §9's text, from `## 9.` to the next heading, hashes to `7625dee7fc24f43c2674ff0aed083c007a86c734` (`sed -n '/^## 9\. /,/^## 10\. /p' <case file> \| git hash-object --stdin`); §9a is frozen at this version, and the hash was unchanged when the unit tier ended. **Amended afterwards, 2026-09-30 (not a prediction change):** a "How this verifies the hypothesis" block was added to §9a and the §9 intro's stale sentence ("nothing has been run") corrected; no claim, step, prediction or conclusion changed (the diff is additions plus that one sentence). §9's hash was then `704ae786d729741a09962835e556fc3a60db4956` (`7625dee…` is the hash at `0598801`). **A second documentation-only amendment, 2026-09-30:** §9c's sentence that the second-node setup "is not in `environment.md` yet" now points to `environment.md` §5, which was written that day; nothing else changed. §9's hash is now `c346eb82e1ae5a32707f7faf1edf5f4c9109feff`. The whole file hashed `400b800…` at that commit and changes whenever §10 takes feedback, so the §9 hash is the freeze. (The first freeze, `65a66cb…`, was superseded before any run.) |
| **Harness** | Committed in `0598801` under `../harness/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS/`: `HintsPoolCeilingTest.java`, `hints-pool.btm`, `hold-flush.btm` and a README. Run 1 used a byte-identical copy on node0, checked with `sha256sum -c` (`run1/unit-session.log:17–19`). Checks: §1.2 |
| **Tiers and values** | Unit first: upstream `HintsBufferPoolTest` and `HintsPoolCeilingTest` at *n* = 2, 3, 6, plus *n* = 3 with 2 MiB buffers. Then cluster: *n* = 2, 3, 6, the second-knob arm, the natural-load control. *n* = 1 is excluded (case §9b) |
| **Audit bottom line** | **Ready after amendments** — 2026-09-30. The second node was set up on 2026-09-30 (`environment.md` §5; §1.2 below). The hold rule's functional check passed the same day (§1.2). Still open before the cluster tier: the cluster run script. Node0 has JDK 11, Ant, the clone at `cassandra-5.0.9` and `byteman-bmunit-4.0.20.jar`, and the upstream test ran under BMUnit there (run 1) |

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
| 1 | Add a reading rule: unit `Count` +*n*, `MemoryUsed` +`n × bufferSize`; cluster `Count` +(*n* − 1), `MemoryUsed` +(*n* − 1) × `bufferSize` over idle, 4 MiB band | Applied 2026-09-30, case 9a (committed in `0598801`) | The conclusions need a decidable threshold, and the cluster cannot measure from a no-pool baseline. A 4 MiB band is an eighth of the smallest step (32 MiB), so it cannot hide an extra buffer |
| 2 | Reword the Confirmed and third Refuted rows to the predicted amount; add rows for "second-knob arm disagrees" and "writer never resumes" | Applied 2026-09-30, case 9a | Both outcomes were plausible and had no row |
| 3 | Add the in-flight hint estimate and an early stop for B on `HintsInProgress` > 75 % of `128 × cores`; sample it every 5 s | Applied 2026-09-30, case 9c, 9e | `StorageProxy.java:202` makes the limit scale with cores; the estimate (about 1,900 in 60 s, marked as not measured) approaches it on a 16-core node |
| 4 | Note `max_hint_window` (3 h) under "Hold fixed" and in the hints-flowing trap; record when node 2 was stopped | Applied 2026-09-30, case 9b, 9d | `StorageProxy.java:2461-2463`: a long sweep would stop hinting silently |
| 5 | Call `HintsBufferTest.defineSchema()` in the harness test | Applied 2026-09-30, case 9e | The hint helper needs the schema |
| 6 | Scope `JVM_EXTRA_OPTS` to the `bin/cassandra` command (`VAR=… bin/cassandra`) instead of `export` | Applied 2026-09-30, case 9e | The handoff's heap-run lesson says it clashed on the Byteman port in the `nodetool` and stress JVMs; the scripts say it should not, and scoping is free |
| 7 | For the stage-3 template: have each conclusions row use the quantity each tier can actually measure, and give the workload's hidden limits (here the in-flight hint limit) in the estimate | Left for stage 3 | Both gaps above came from the template not asking for them |

All amendments above were made before any run and are in `0598801`.

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
| Second node (`environment.md` §5), 2026-09-30 | **Passed.** Two-node ring on node0 and `pc80`; node 2 stopped and seen `DN`; node 1 restarted alone wrote 2,000 stress rows with no error and `TotalHints` rose 0 → 2000, with a hint file named for node 2 (about 5.2 KB per hint). Data and logs wiped afterwards. Not a reading of the case |
| Hold rule, functional (case 9e, steps 2 and 3), 2026-09-30, node 1 on node0 with node 2 on `pc80` (`instrument-check/hold-check.sh`; evidence in `instrument-check/hold-check-out/`) | **Passed** on the second attempt. `Submit -l` listed the trace rules' triggers on `createBuffer()` and `switchCurrentBuffer(...)`. With `hold-flush.btm` loaded, 10,000 stress rows filled one 32 MiB buffer; a thread dump caught `HintsWriteExecutor:1` `TIMED_WAITING (sleeping)` in Byteman `Helper.delay`, inside `FlushBufferTask.run`; the trace has one `hold … delay=3000` line and `created=1` (idle flush) then `created=2` (`size=33554432`, `max=3`, from a `MutationStage` thread). A throwaway counting rule (`flush-count.btm`) shows one flush, and it was held. After `Submit -u`, 6,000 more rows caused a second flush with no new `hold` line, so the unload releases the hold. No `ERROR` in node 1's `system.log`. Not a reading of the case. **First attempt failed on my own expectation, not the instrument** (`attempt1-session.log`): it expected `created=3` after the unload, but the pool reuses a recycled buffer before it creates one, so a third buffer never appears; the check now compares flushes with `hold` lines instead |

These checks were at *n* = 3 only. The unit tier's other values ran afterwards as run 1 (§4).

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-09-30, 19:39–19:42 UTC (unit tier) | |
| Node (CloudLab name and type) | `node0.jason92-317394` (`pc66`; 40 cores, 125 GiB) | |
| CPU cores (`nproc`) — sets the in-flight hint limit `128 × cores` (case 9c) | 40 (limit 5,120); not used by the unit tier | |
| Time node 2 was stopped, and time of each run (`max_hint_window`, case 9b) | not applicable to the unit tier | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local `cassandra-src` clone commit | `b5f2a54` (`~/cassandra-run1`, tag `cassandra-5.0.9`). Dirty: `conf/cassandra.yaml` modified by the heap run, two untracked test files (part 6 of §4.2) | |
| Case-file commit / harness commit | `0598801` / `0598801` | |
| Storage for node data | local `/dev/sda3` (ext3); the unit tier writes only under the clone's `build/test` | |
| Full logs (path, outside the repo) | node0 `~/stage4-logs/hints/unit/` (532 KB: one folder per JVM, `session.log`, `summary.txt`). Committed: `run1/unit-session.log` and the excerpts in §4 | |

## 3. Runbook defects

Every step a run could not execute as written. The run stops at the
defect; the fix is made in the case file (dated) if it leaves §9a unchanged,
and the affected tier restarts from its beginning. If the fix would change
§9a, the case goes back to the audit. "None" if there were none.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | Instrument check, unit, *n* = 3 | 9e unit, step 1 | The exact deltas failed: `Count` +4 and `MemoryUsed` +3 MiB + 128 B instead of +3 and +3 MiB. Cause, traced with a throwaway Byteman rule (`trace-alloc-ant.txt` on node0): the first `Mutation.serializedSize()` on a thread creates a netty `FastThreadLocal` scratch `DataOutputBuffer` whose constructor calls `allocateDirect(128)` (`Mutation.java:453`, `DataOutputBuffer.java:87`). The first attempt, with no GC settle, also read `Count` +1, because garbage buffers were freed mid-test | The writer thread serializes one hint before the baseline, the JVM settles (`System.gc()`, 500 ms), then the baseline is read. Harness test and 9e step 1 | AI, 2026-09-30 | `0598801` |
| 2 | Instrument check, unit (found by following 1 to its cause) | 9a reading rule; 9d "Real resource" | The same scratch buffer exists on every thread that serializes a mutation. In the cluster tier the 32 `MutationStage` threads each hold one, so the audit's rule "`Count` up by exactly *n* − 1" would fail for an unrelated reason | Cluster `Count` is reported, not asserted. `MemoryUsed` within the 4 MiB band and the create trace decide. Unit tier unchanged (exact, after the warm-up) | AI, 2026-09-30 | `0598801` |

**Why these two fixes are not tuning.** Both change how the JVM-wide direct-buffer
counters are read, before any run of the case. The pool's own readings matched the
prediction on every attempt (`allocatedBuffers=3`, `queued=2`, `created=1,2,3`).
The ceiling claim, the prediction and the conclusions rows are unchanged.

## 4. Run 1

**Scope:** unit tier, 2026-09-30, seven JVMs: the upstream `HintsBufferPoolTest` at *n* = 2, 3, 6, and
`HintsPoolCeilingTest` at *n* = 2, 3, 6 with 1 MiB buffers and at *n* = 3 with 2 MiB. Cluster tier: not started.
**Command log:** [`MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS/run1/unit-run.sh`](MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS/run1/unit-run.sh), run on node0 from
`~/stage4-harness-run/`. Its whole log is committed as `run1/unit-session.log` (146 lines); per-JVM logs are on
node0 under `~/stage4-logs/hints/unit/<label>/`. Files cited below are all in
[`MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS/run1/`](MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS/run1/):
`unit-session.log`, `unit-summary.txt`, `unit-harness-readings.txt`, `unit-junit-testcases.txt`,
`unit-ant-excerpts.txt`, and the self-check `unit-selfcheck.py` with its output `unit-selfcheck.txt`.

### 4.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Upstream `HintsBufferPoolTest.testBackpressure`, *n* = 2 | pass (1 test, 0 failures, 0 errors) | `unit-session.log:29`; `unit-junit-testcases.txt` |
| Same, *n* = 3 | pass | `unit-session.log:37` |
| Same, *n* = 6 | pass | `unit-session.log:45` |
| `HintsPoolCeilingTest`, *n* = 2, 1 MiB buffers | pass. At the wait: `allocatedBuffers` 2, callback buffers 1, `Count` +2, `MemoryUsed` +2,097,152 | `unit-session.log:53`; `unit-harness-readings.txt`, block `ceiling-n2-1MiB` |
| Same, *n* = 3, 1 MiB | pass. 3, 2, +3, +3,145,728 | `unit-session.log:74`; block `ceiling-n3-1MiB` |
| Same, *n* = 6, 1 MiB | pass. 6, 5, +6, +6,291,456 | `unit-session.log:96`; block `ceiling-n6-1MiB` |
| Same, *n* = 3, 2 MiB buffers | pass. 3, 2, +3, +6,291,456 | `unit-session.log:121`; block `ceiling-n3-2MiB` |

The harness test in detail. Each JVM started from the same baseline (`Count` 15, `MemoryUsed` 267,010). "One buffer" is
⌊`bufferSize` / 78⌋ hints, where 78 is the printed `entrySize` (a 66-byte hint plus 12 bytes of entry overhead).

| Value | Hints written when the writer parked | 2 s later | After one recycle | At the end |
|---|---|---|---|---|
| *n* = 2 × 1 MiB | 26,886 = 2 × 13,443 | all six readings unchanged | 40,329 hints (+13,443); `allocatedBuffers`, callback buffers, `Count`, `MemoryUsed` unchanged | 67,217 written, 67,217 found in buffers; 2 buffers, +2,097,152 |
| *n* = 3 × 1 MiB | 40,329 = 3 × 13,443 | unchanged | 53,772 (+13,443); unchanged | 80,660 and 80,660; 3 buffers, +3,145,728 |
| *n* = 6 × 1 MiB | 80,658 = 6 × 13,443 | unchanged | 94,101 (+13,443); unchanged | 120,990 and 120,990; 6 buffers, +6,291,456 |
| *n* = 3 × 2 MiB | 80,658 = 3 × 26,886 | unchanged | 107,544 (+26,886); unchanged | 161,320 and 161,320; 3 buffers, +6,291,456 |

While the writer ran, `Count` rose one step per buffer, from baseline to baseline + *n*, and stopped there
(`directChange` lines of each block). The 50 relations above are asserted by `unit-selfcheck.py` (`unit-selfcheck.txt`: all pass).

**Cluster tier** — one row per capacity value, scenario and observable: **not run yet.**

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|

### 4.2 Conclusion and logic — unit tier

Files are in `run1/`. **[observed: file]** means the file says it; **[inferred: reason]** gives the reason. The
cluster tier has no conclusion yet.

1. **Validity — valid for the unit tier.**
   - The code under test is the pinned tag [observed: `unit-session.log:11`, HEAD `b5f2a54`, `describe` `cassandra-5.0.9`]
     and the committed instruments [observed: `unit-session.log:17–19`, `sha256sum -c` OK; `:22–23`, the test in the
     clone and the harness copy have the same sha256]. The harness folder equalled commit `0598801` when it was copied
     [observed: `git diff --quiet HEAD` on it, run locally before the copy; not in the node log].
   - The knob took effect in every harness JVM: the test asserts `HintsBufferPool.MAX_ALLOCATED_BUFFERS` equals the
     `cassandra.MAX_HINT_BUFFERS` it was given, before anything else, and all four passed [observed:
     `HintsPoolCeilingTest.java:87` in the harness; `unit-summary.txt`]. The flag was passed to the three upstream JVMs
     [observed: `unit-session.log:24, 32, 40`], but that test asserts no value [inferred: same `-D` route as the harness runs].
   - The limit was reached in every harness JVM: the writer was parked in `LinkedBlockingQueue.take` under
     `HintsBufferPool.switchCurrentBuffer` and `allocatedBuffers` equalled *n* [observed: the `parkedAt` and `atWait`
     lines of each block of `unit-harness-readings.txt`]. The upstream test's Byteman flag was set at every *n*, since
     the test asserts it [observed: pass at `unit-session.log:29, 37, 45`; the assertions are `HintsBufferPoolTest.java:66`
     and `:72` at the pinned tag].
   - The §9b "hold fixed" settings are cluster settings and do not apply. The unit JVMs loaded `test/conf/cassandra.yaml`,
     not the clone's modified `conf/cassandra.yaml` [observed: `unit-ant-excerpts.txt`, the two "Configuration location" lines].
2. **Readings — nothing unusual.** All seven JVMs passed [observed: `unit-summary.txt`; `unit-session.log:29–121`].
   Every harness reading is exact, with no tolerance used [observed: `unit-harness-readings.txt`]: at the wait
   `allocatedBuffers` = *n*, the callback had received *n* − 1 buffers, `Count` was up by *n* and `MemoryUsed` by
   `n × bufferSize`. The same numbers had appeared at *n* = 3 in the instrument check after the two §3 fixes (a separate
   JVM, not a reading). Two cross-checks that the numbers are not an artefact of the test's own arithmetic: the hints
   written when the writer parked equal `n × ⌊bufferSize / 78⌋` exactly, so it stopped when the *n*-th buffer was full,
   not before or after [observed: the `written` values; inferred: the ⌊bufferSize/78⌋ capacity, from the printed entry
   size]; and one recycle let through exactly one buffer's worth of hints [observed: `afterOneRecycle` minus `after2s`].
3. **Matched row — the unit-tier part of "Confirmed":** "The pool holds exactly *n* buffers at every value, direct memory
   is up by the predicted amount …, a writer waits at the check, and the ceiling moves with *n* and with `bufferSize`".
   The unit tier covers §9a procedure step 1 only.
   - *The pool holds exactly *n* buffers when the writer waits:* `allocatedBuffers` was 2, 3, 6 and 3 [observed: `atWait`].
   - *Direct memory is up by `n × bufferSize`:* `MemoryUsed` +2,097,152, +3,145,728, +6,291,456 and +6,291,456 (the
     reading rule's unit tier: exact) and `Count` +2, +3, +6, +3 [observed: `atWait`]. It rose one step per buffer and
     stopped at the *n*-th [observed: the `directChange` lines].
   - *The ceiling moves with *n*:* 2, 3, 6 MiB at 1 MiB buffers, three values including the default 3 [observed].
   - *…and with `bufferSize`, as a product:* 3 × 2 MiB and 6 × 1 MiB both land at 6,291,456 bytes [observed: blocks
     `ceiling-n3-2MiB` and `ceiling-n6-1MiB`]. That is §9a's second-knob prediction, at the unit tier.
   - *A writer waits at the check:* parked in `take()` under `switchCurrentBuffer` at every value [observed: `parkedAt`].
     That the call site is line 118 is [inferred: the method has one `take()` call, `HintsBufferPool.java:118`, case §5].
   - *Nothing grows while the writer waits:* `allocatedBuffers`, callback buffers, hints written, `Count` and `MemoryUsed`
     were identical 2 s later [observed: `atWait` and `after2s`].
   - *Recycling one buffer releases the writer without creating another:* the writer resumed (hints written rose by one
     buffer's worth) and parked again, and `allocatedBuffers`, `Count` and `MemoryUsed` did not change [observed: `afterOneRecycle`].
   - *The hint is not dropped (at this tier):* every hint written was found in exactly one buffer — 67,217, 80,660, 120,990
     and 161,320 [observed: `atEnd`, `hintsCounted`]. This counts hints in buffers, not their delivery.
4. **Excluded rows.**
   - *Refuted — "More than *n* buffers are ever created":* excluded at this tier. Each writer wrote hints worth *n* + 3
     buffers and the pool still held *n* at the end [observed: `atEnd`; `hintsToWrite` in each block].
   - *Refuted — "direct memory keeps rising above the predicted amount":* excluded at this tier. `MemoryUsed` was exactly
     `n × bufferSize` at the wait, after 2 s, after the recycle and at the end [observed]. The exactness depends on the §3
     fixes (writer warm-up, settled baseline).
   - *Refuted in part — "follows *n* but not `bufferSize`":* excluded; the 2 MiB arm landed at 6,291,456 [observed].
   - *Not confirmed — "a writer waits but never resumes":* excluded at this tier; the writer resumed after each recycle
     and finished [observed: `atEnd`; the test passed].
   - *Refuted — "direct memory is flat across *n*":* excluded; it rose 2, 3, 6 MiB [observed].
   - *Not confirmed — "no writer is ever seen waiting":* excluded [observed: `parkedAt` in all four blocks].
   - *Invalid run:* excluded; the cap was reached at every value [observed: `atWait`].
   - *Not testable at this tier:* the default 32 MiB buffers; `bufferSize` derived from `max_mutation_size`; the wiring
     through `HintsService` and `HintsWriteExecutor` (the test's flush callback only queues buffers, and the test does the
     recycling); the hold rule; node-wide direct memory with other users.
5. **Observed vs. inferred — what the conclusion rests on that was not directly seen:**
   - The parked call site is line 118 of `HintsBufferPool` [inferred from the frames and the single `take()` call].
   - `MAX_HINT_BUFFERS` took effect in the three upstream JVMs [inferred]. The *n*-dependence rests on the harness JVMs,
     which assert it.
   - The per-buffer capacity 13,443 (26,886 at 2 MiB) is arithmetic on the printed entry size [inferred]; the exact
     multiples in `written` support it.
   - That recycling releases a waiting writer on a real node, through `HintsWriteExecutor.FlushBufferTask`
     [inferred from source, case §6b; `HintsWriteExecutor.java:141–154`]. The unit tier does the recycling itself.
   - The exact direct-memory deltas depend on the two §3 fixes. A buffer freed by the JVM mid-test would shift them.
     The identical baseline and deltas across four JVMs [observed] make that unlikely here.
6. **Deviations and gaps.**
   - The instrument files were copied to node0 from the local repo (commit `0598801` is not pushed) and verified with
     `sha256sum -c`, rather than read from the `/proj` clone.
   - The node's clone is dirty: `conf/cassandra.yaml` holds the heap run's edits (`memtable_heap_space: 256MiB`,
     `memtable_allocation_type: unslabbed_heap_buffers`, seen with `git diff` on node0 after the tier, not in the committed
     log) and two test files are untracked [observed: `unit-session.log:12–15`; `git.sha=…-dirty` in `unit-ant-excerpts.txt`].
     The unit JVMs do not read that file [observed]. It must be reset before the cluster tier.
   - Before this run the harness test failed five times with the agent attached, plus two diagnostic runs (no agent; an
     allocation trace), during the instrument check; the causes are §3 defects 1–2, fixed before this run. Those attempts
     are not part of run 1.
   - One JVM per value, no repeat. The numbers are exact and equal to the instrument check's at *n* = 3, but run-to-run
     spread was not measured.
   - The unit tier cannot show the node-level behaviour listed under "Not testable" in part 4.
7. **Core question — does the constraint cap the resource, and does usage follow it?** At the unit tier, yes, for the pool
   on its own. With `MAX_HINT_BUFFERS` = *n* the pool never held more than *n* direct buffers, however many hints were
   written (part 4); when its writer needed an (*n*+1)-th buffer it waited at the check rather than allocating (part 3);
   and the direct memory the pool held was exactly `n × bufferSize`, rising 2, 3, 6 MiB with *n* and reaching the same
   6 MiB from 3 × 2 MiB as from 6 × 1 MiB (part 3). What this does not yet show is the same thing on a running node with
   the default 32 MiB buffers and the real flush path; that is the cluster tier.

**Conclusion (one line):** unit tier — consistent with **Confirmed**; no Refuted or Not-confirmed row fired. The case's
verdict still needs the cluster tier.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-open every raw file the conclusion cites and confirm it says what the
conclusion says. A part that does not hold is fixed, or the conclusion is
downgraded to *Not confirmed*.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-read `unit-session.log` lines 11, 17–19, 22–24, 29, 32, 37, 40, 45: each says what part 1 says. `unit-ant-excerpts.txt`: both "Configuration location" lines name `test/conf/cassandra.yaml`. The harness's line 87 is the knob assertion. One statement is not in the node log: that the harness equalled commit `0598801` when copied (a local check); the node's `sha256sum -c` does cover the copy |
| 2. Readings | yes | `unit-selfcheck.py` re-reads `unit-summary.txt`, `unit-session.log`, `unit-harness-readings.txt` and `unit-ant-excerpts.txt` and asserts 50 relations, all pass (`unit-selfcheck.txt`): the exact deltas, the same baseline in all four JVMs, `written` at the wait = *n* × ⌊bufferSize/78⌋, one recycle = one buffer's worth, written = found |
| 3. Matched row | yes | Each bullet maps to a check above: *n* buffers (`allocatedBuffers`), exact `Count` and `MemoryUsed`, the ceiling moving 2 < 3 < 6 MiB, the second-knob equality (both 6,291,456), the writer parked, 2 s unchanged, recycle releases without a new buffer, written = found |
| 4. Excluded rows | yes | Every Refuted and Not-confirmed row of §9a's table is addressed and maps to a reading. "Hints worth *n* + 3 buffers" is asserted (`hintsToWrite` = (*n*+3) × ⌊bufferSize/78⌋ + 1). "Not testable at this tier" lists what no reading covers |
| 5. Observed vs. inferred | yes | The five inferred statements are the only ones without a file line. One more was checked and is observed, not inferred: the flush callback only queues buffers and the test does the recycling (harness lambda and recycle loop) |
| 6. Deviations and gaps | yes | The dirty clone is in `unit-session.log:12–15` and `unit-ant-excerpts.txt`; the `git diff` of `conf/cassandra.yaml` is the one item from outside the committed log and is marked so. The count of failed instrument attempts (five with the agent, two diagnostic) matches `instrument-ant*.txt`, `noagent-ant.txt` and `trace-alloc-ant.txt` on node0 |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | The chain in part 7 uses only parts 3 and 4, and the audited logic (vary *n*, read the pool's real direct memory, find the disallow evidence, exclude the Refuted rows) was followed. The conclusion says "consistent with Confirmed" at the unit tier and does not claim the cluster-level result |

### 5.2 Run 2?

**No** — 2026-09-30, for the unit tier. The readings are exact and were re-asserted mechanically; no part of §5.1 is
open; and the result neither refutes the case nor confirms a bypass. The inferred statements (part 5) are about the
cluster tier's questions. A run 2 is worth reconsidering for the cluster tier once it has run. *Criterion, for
reference:* choose yes when the conclusion rests on inferred statements, a part of §5.1 cannot be settled from run 1's evidence, or the result refutes the case or confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

**Not done** (§5.2 says no), and §7 is left out.

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
| Unit | Consistent with **Confirmed**; no Refuted or Not-confirmed row fired | run 1 + self-check | 2026-09-30 |
| Cluster | Not run | — | — |

**Feedback filed (uncommitted, 2026-09-30):** the case file's §10 "Stage-4 feedback" field updated for the unit tier.
Sections amended: none after run 1 started. §9 was amended before it, in `0598801` (the audit; §3 defects 1–2). §8's
ceiling claim and the Target-3 note: not amended. The freeze (§1) was checked at the end of run 1 and still holds.
