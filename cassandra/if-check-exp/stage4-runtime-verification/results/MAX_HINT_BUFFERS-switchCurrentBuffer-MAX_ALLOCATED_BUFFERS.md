# MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS — stage-4 results  <!-- file: results/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS.md -->

> **Case:** [`MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS`](../../stage3-ai-deep-read/cases/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS.md)
>
> **Status:** **both tiers: run 1 done 2026-09-30, self-checked, verdicts filed.** Unit tier: consistent with Confirmed. **Cluster tier: Confirmed, with one recorded deviation from the reading rule** (its 4 MiB band was exceeded at every value; the rule's create-trace clause decides, and a supplementary allocation trace attributes the excess to non-pool allocations: §4.3, §8). Run 2 not chosen.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Committed in `0598801` (2026-09-30). §9's text, from `## 9.` to the next heading, hashes to `7625dee7fc24f43c2674ff0aed083c007a86c734` (`sed -n '/^## 9\. /,/^## 10\. /p' <case file> \| git hash-object --stdin`); §9a is frozen at this version, and the hash was unchanged when the unit tier ended. **Amended afterwards, 2026-09-30 (not a prediction change):** a "How this verifies the hypothesis" block was added to §9a and the §9 intro's stale sentence ("nothing has been run") corrected; no claim, step, prediction or conclusion changed (the diff is additions plus that one sentence). §9's hash was then `704ae786d729741a09962835e556fc3a60db4956` (`7625dee…` is the hash at `0598801`). **A second documentation-only amendment, 2026-09-30:** §9c's sentence that the second-node setup "is not in `environment.md` yet" now points to `environment.md` §5, which was written that day; nothing else changed. §9's hash was then `c346eb82e1ae5a32707f7faf1edf5f4c9109feff`. **A third amendment, 2026-09-30, after the cluster tier had run (documentation only):** the second-knob arm's row count (9c and 9e; §3, defect 3) and two stale statements (the §9 intro's "run so far" and 9c's "harness not written yet"). **§9a and §9b are byte-identical to before**: §9a hashes to `766bb7b5fdda004c01505d585cac149f920dbef2` at `HEAD` and in the working tree, checked with `sed -n '/^### 9a\. /,/^### 9b\. /p' <case file> \| git hash-object --stdin` on `git show HEAD:<case file>` and on the file. §9's hash is now `46b2d0dac514e0fcbd40d0a75059b3e6b044a6f3`. The whole file hashed `400b800…` at that commit and changes whenever §10 takes feedback, so the §9 hash is the freeze. (The first freeze, `65a66cb…`, was superseded before any run.) |
| **Harness** | Committed in `0598801` under `../harness/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS/`: `HintsPoolCeilingTest.java`, `hints-pool.btm`, `hold-flush.btm` and a README. Run 1 used a byte-identical copy on node0, checked with `sha256sum -c` (`run1/unit-session.log:17–19` for the unit tier, and the three `OK` lines in each cluster value's `session.log`). The node's `SHA256SUMS` matched the local files before the cluster tier (compared by hand; `git diff` on the harness folder was empty). Checks: §1.2 |
| **Tiers and values** | Unit first: upstream `HintsBufferPoolTest` and `HintsPoolCeilingTest` at *n* = 2, 3, 6, plus *n* = 3 with 2 MiB buffers. Then cluster: *n* = 2, 3, 6, the second-knob arm, the natural-load control. *n* = 1 is excluded (case §9b) |
| **Audit bottom line** | **Ready after amendments** — 2026-09-30. The second node was set up on 2026-09-30 (`environment.md` §5; §1.2 below). The hold rule's functional check and the cluster run script's smoke test passed the same day (§1.2). The cluster tier was then run the same day, with `run1/ring.sh` once and `run1/cluster-run.sh value <label>` for each value (§4). Node0 has JDK 11, Ant, the clone at `cassandra-5.0.9` and `byteman-bmunit-4.0.20.jar`, and the upstream test ran under BMUnit there (run 1) |

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
| Cluster run script, `smoke` mode (`run1/cluster-run.sh`), 2026-09-30, node 1 alone on node0, no ring (`instrument-check/cluster-run-smoke/`) | **Passed.** Every helper ran on the real node: the tag's yaml plus the three ring edits (diff adds 3 lines), start with the agent, `Submit -l`, the `MAX_HINT_BUFFERS` property check, the `sjk` readings (idle `MemoryUsed` 50,182,384, `Count` 180, NMT `Other` 65,408 KB, `TotalHints` 0, `HintsInProgress` 0), the thread-dump parser, loading and unloading the hold. 0 `ERROR` lines. `data/` and `logs/` removed afterwards. Not a reading of the case. The idle `Count` of 180 is one more reason the cluster rule reports `Count` without asserting it |
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
| Date | 2026-09-30. Unit tier 19:39–19:42 UTC. Cluster tier 21:06–21:43 UTC: the ring 21:06–21:09, the five values 21:10–21:32, the supplementary diagnostic 21:42–21:44 | |
| Node (CloudLab name and type) | `node0.jason92-317394` (`pc66`; 40 cores, 125 GiB), the measured node. Cluster tier also `pc80` (`node0.jason92-318546`; 40 cores, 125 GiB), node 2, only the hint target | |
| CPU cores (`nproc`) — sets the in-flight hint limit `128 × cores` (case 9c) | 40, so the limit is 5,120 and B would have ended early at 3,840; the highest `HintsInProgress` read was 159. Not used by the unit tier | |
| Time node 2 was stopped, and time of each run (`max_hint_window`, case 9b) | Node 2 stopped 21:08:17 UTC and seen `DN` by node 1 at 21:08:31 (`run1/ring/session.log`, converted from the workstation's EDT). Control readings: *n* = 2 at 21:10:20, *n* = 3 at 21:14:54, *n* = 6 at 21:18:21, 64 MiB arm attempt 1 at 21:21:51, natural-load control at 21:26:32, arm attempt 2 at 21:29:32 UTC. The last value ended 21:31:44, 23 min after node 2 went down, against `max_hint_window` of 3 h; the diagnostic's control reading was at 21:42:55 (34 min). `TotalHints` rose at every value (§4.1), so hints flowed throughout | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local `cassandra-src` clone commit | `b5f2a54` (`~/cassandra-run1`, tag `cassandra-5.0.9`). Unit tier: dirty, `conf/cassandra.yaml` held the heap run's edits and two test files were untracked (part 6 of §4.2). Cluster tier: `conf/cassandra.yaml` holds only the three ring edits (plus two lines in the second-knob arm, restored after it; each value's `cassandra.yaml.diff` shows exactly that), the two untracked test files and the old `data.heap-run-2026-09-29/` are still there. Node 2's clone `~/cassandra-node2` is at `b5f2a54` on `pc80` (`run1/ring/session.log:2-5`) | |
| Case-file commit / harness commit | `0598801` / `0598801` (unit tier). Cluster tier: case file at `88c07fb` plus the uncommitted amendments of this session (§1: §9a unchanged); harness `0598801`. Run scripts uncommitted when run, sha256 prefixes: `ring.sh` `b1f35566`, `cluster-run.sh` `125833d3`, `diag-run.sh` `440a070f`, `diag-alloc.btm` `0a34958c` | |
| Storage for node data | local `/dev/sda3` (ext3). The unit tier writes only under the clone's `build/test`. Cluster tier: data, commit log and hints under `~/cassandra-run1/data/` on the same disk (47 GB free at the end; the hints directory reached 1.0 GB per value and 2.0 GB in the 400,000-row arm) | |
| Full logs (path, outside the repo) | node0 `~/stage4-logs/hints/unit/` (532 KB: one folder per JVM, `session.log`, `summary.txt`). Committed: `run1/unit-session.log` and the excerpts in §4. Cluster tier: node0 `~/stage4-logs/hints/cluster/<label>/` (40 MB in all: full thread dumps, stress output, `system.log`, `stdout.txt`), the diagnostic's `diag-alloc-n3/` beside them, and the ring's node logs under `~/stage4-logs/hints/cluster/ring-node1-stdout.txt` and, on `pc80`, `~/stage4-logs/second-node/`. Committed: `run1/cluster/<label>/` (summary, readings, traces, dump excerpts, stress excerpt, session log), `run1/ring/session.log`, `run1/diag-alloc/` | |

## 3. Runbook defects

Every step a run could not execute as written. The run stops at the
defect; the fix is made in the case file (dated) if it leaves §9a unchanged,
and the affected tier restarts from its beginning. If the fix would change
§9a, the case goes back to the audit. "None" if there were none.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | Instrument check, unit, *n* = 3 | 9e unit, step 1 | The exact deltas failed: `Count` +4 and `MemoryUsed` +3 MiB + 128 B instead of +3 and +3 MiB. Cause, traced with a throwaway Byteman rule (`trace-alloc-ant.txt` on node0): the first `Mutation.serializedSize()` on a thread creates a netty `FastThreadLocal` scratch `DataOutputBuffer` whose constructor calls `allocateDirect(128)` (`Mutation.java:453`, `DataOutputBuffer.java:87`). The first attempt, with no GC settle, also read `Count` +1, because garbage buffers were freed mid-test | The writer thread serializes one hint before the baseline, the JVM settles (`System.gc()`, 500 ms), then the baseline is read. Harness test and 9e step 1 | AI, 2026-09-30 | `0598801` |
| 2 | Instrument check, unit (found by following 1 to its cause) | 9a reading rule; 9d "Real resource" | The same scratch buffer exists on every thread that serializes a mutation. In the cluster tier the 32 `MutationStage` threads each hold one, so the audit's rule "`Count` up by exactly *n* − 1" would fail for an unrelated reason | Cluster `Count` is reported, not asserted. `MemoryUsed` within the 4 MiB band and the create trace decide. Unit tier unchanged (exact, after the warm-up) | AI, 2026-09-30 | `0598801` |
| 3 | 1 (cluster), second-knob arm, first attempt | 9c "Rows"; 9e "Second-knob arm" | Non-blocking for the claim, blocking for the step as written. With 64 MiB buffers each recycled buffer admits twice the hints of a 32 MiB one, so the 200,000 rows ran out: the stress exited 34 s into B, not at about 60 s, only one B dump (B10) could be taken, and the release check was empty (nothing was left waiting: `TotalHints` was 200,768 and could not rise). `created=3`, `size=67108864`, the waits and the flat memory were all seen in that attempt | Rows for this arm raised to `n=400000` (`ROWS=400000`, an existing override of `cluster-run.sh`); the arm was re-run from its start; the first attempt is kept as `run1/cluster/n3-buf64MiB-attempt1/`. The other four runs are unaffected: their stress was still running at 60 s | AI, 2026-09-30 | uncommitted: §9c Rows and §9e second-knob paragraph amended; §9a and §9b unchanged |

**Why these two fixes are not tuning.** Both change how the JVM-wide direct-buffer
counters are read, before any run of the case. The pool's own readings matched the
prediction on every attempt (`allocatedBuffers=3`, `queued=2`, `created=1,2,3`).
The ceiling claim, the prediction and the conclusions rows are unchanged.

**Cluster tier (2026-09-30): no blocking defect.** Every check in `cluster-run.sh` passed on the first attempt at all five values. One non-blocking defect, #3 above, was fixed in §9c and §9e (documentation only; §9a unchanged) and its arm re-run. Not runbook defects, recorded in §4.3: the reading rule's band was too small (a finding about the prediction, not a step that could not run), and the supplementary diagnostic's first attempt died in start-up (the diagnostic is not in §9).

## 4. Run 1

**Scope:** unit tier, 2026-09-30, seven JVMs: the upstream `HintsBufferPoolTest` at *n* = 2, 3, 6, and
`HintsPoolCeilingTest` at *n* = 2, 3, 6 with 1 MiB buffers and at *n* = 3 with 2 MiB. Cluster tier: 2026-09-30, five capacity values, each a fresh JVM on node 1 (node0) with node 2 (`pc80`) a stopped ring member: *n* = 2, 3, 6 at 32 MiB buffers, the second-knob arm (*n* = 3, 64 MiB buffers; run twice, §3 defect 3) and the natural-load control (*n* = 3, no hold); then a supplementary allocation-trace diagnostic (§4.3).
**Command log:** [`MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS/run1/unit-run.sh`](MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS/run1/unit-run.sh), run on node0 from
`~/stage4-harness-run/`. Its whole log is committed as `run1/unit-session.log` (146 lines); per-JVM logs are on
node0 under `~/stage4-logs/hints/unit/<label>/`. Files cited below are all in
[`MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS/run1/`](MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS/run1/):
`unit-session.log`, `unit-summary.txt`, `unit-harness-readings.txt`, `unit-junit-testcases.txt`,
`unit-ant-excerpts.txt`, and the self-check `unit-selfcheck.py` with its output `unit-selfcheck.txt`.
**Cluster tier command logs:** `run1/ring.sh` once (its log is `run1/ring/session.log`), then `run1/cluster-run.sh value <label>` for each value, run from the workstation over ssh on node0 from `~/stage4-harness-run/`, one value at a time. Each value's whole log, every command with its output, is `run1/cluster/<dir>/session.log`; the readings are `readings.csv`, the notes `summary.txt`. The diagnostic is `run1/diag-alloc/diag-run.sh` with `diag-alloc.btm`. The checks are `run1/cluster-selfcheck.py` (output `cluster-selfcheck.txt`), `run1/dump-recount.py` (output `dump-recount.txt`) and `run1/diag-alloc/diag-analysis.py` (output `diag-alloc/diag-analysis.txt`).

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

**Cluster tier**, 2026-09-30: five capacity values and the shortened first attempt of the 64 MiB arm. Files are in `run1/cluster/<dir>/` (`<dir>` as named in §4.3); `ms` in the files is epoch milliseconds, and UTC times are in §2. Each reading is a `nodetool sjk mx` call that starts a JVM (1–2 s), so a row's `Count` is read 1–2 s after its `MemoryUsed`. The hold was 3,000 ms. The stress was `cassandra-stress write n=<rows> no-warmup -col size=FIXED(1024) -rate threads=64`, with 200,000 rows (400,000 in the arm's second attempt).

*The four fixed moments* (scenario A ends at the row named "A"; B is 60 s; then the hold is released)

| Capacity value | Phase | `MemoryUsed` (bytes) | `Count` | NMT `Other` (KB) | `TotalHints` | `HintsInProgress` | Evidence (file, in `run1/cluster/<dir>/`) |
|---|---|---|---|---|---|---|---|
| n2 | control (idle, ≥ 15 s up) | 58,531,181 | 176 | 73,555 | 0 | 0 | `n2/readings.csv` |
| n2 | A: at `created=n` | 101,402,479 | 298 | 1,426,148 | 19,284 | 95 | `n2/readings.csv` |
| n2 | end of B | 101,391,862 | 297 | 1,426,130 | 167,128 | 159 | `n2/readings.csv` |
| n2 | after the hold is released | 101,391,862 | 297 | 1,426,130 | 201,664 | 0 | `n2/readings.csv` |
| n3 | control (idle, ≥ 15 s up) | 50,146,484 | 176 | 65,369 | 0 | 0 | `n3/readings.csv` |
| n3 | A: at `created=n` | 126,553,524 | 297 | 1,450,712 | 25,712 | 95 | `n3/readings.csv` |
| n3 | end of B | 126,537,943 | 295 | 1,450,686 | 173,556 | 159 | `n3/readings.csv` |
| n3 | after the hold is released | 126,537,943 | 295 | 1,450,686 | 201,664 | 0 | `n3/readings.csv` |
| n6 | control (idle, ≥ 15 s up) | 50,190,380 | 180 | 65,412 | 0 | 0 | `n6/readings.csv` |
| n6 | A: at `created=n` | 227,270,919 | 305 | 1,549,068 | 51,424 | 95 | `n6/readings.csv` |
| n6 | end of B | 227,254,282 | 303 | 1,549,042 | 192,840 | 95 | `n6/readings.csv` |
| n6 | after the hold is released | 227,254,282 | 303 | 1,549,042 | 201,600 | 0 | `n6/readings.csv` |
| n3 × 64 MiB, attempt 1 (200,000 rows) | control (idle, ≥ 15 s up) | 83,737,831 | 180 | 98,173 | 0 | 0 | `n3-buf64MiB-attempt1/readings.csv` |
| n3 × 64 MiB, attempt 1 (200,000 rows) | A: at `created=n` | 227,242,070 | 304 | 1,549,040 | 51,424 | 95 | `n3-buf64MiB-attempt1/readings.csv` |
| n3 × 64 MiB, attempt 1 (200,000 rows) | end of B | 227,225,901 | 302 | 1,549,014 | 200,768 | 0 | `n3-buf64MiB-attempt1/readings.csv` |
| n3 × 64 MiB, attempt 1 (200,000 rows) | after the hold is released | 227,225,901 | 302 | 1,549,014 | 200,768 | 0 | `n3-buf64MiB-attempt1/readings.csv` |
| n3 × 64 MiB, attempt 2 (400,000 rows) | control (idle, ≥ 15 s up) | 83,744,966 | 180 | 98,180 | 0 | 0 | `n3-buf64MiB/readings.csv` |
| n3 × 64 MiB, attempt 2 (400,000 rows) | A: at `created=n` | 227,241,158 | 304 | 1,549,040 | 51,424 | 95 | `n3-buf64MiB/readings.csv` |
| n3 × 64 MiB, attempt 2 (400,000 rows) | end of B | 227,224,505 | 302 | 1,549,013 | 334,256 | 95 | `n3-buf64MiB/readings.csv` |
| n3 × 64 MiB, attempt 2 (400,000 rows) | after the hold is released | 227,224,505 | 302 | 1,549,013 | 401,536 | 0 | `n3-buf64MiB/readings.csv` |
| n3 natural (no hold) | control (idle, ≥ 15 s up) | 50,253,236 | 179 | 65,473 | 0 | 0 | `n3-natural/readings.csv` |
| n3 natural (no hold) | end of B | 126,669,866 | 299 | 1,450,819 | 200,000 | 0 | `n3-natural/readings.csv` |

*Scenario B* — a reading every 5 s and three thread dumps (B10, B30, B50: about 10, 30 and 50 s in). "Parked / blocked" is the count of threads in `take()` and of threads blocked on the pool's monitor; each was recounted from the full dump by a second method (`run1/dump-recount.txt`). The first B sample of the natural-load control was taken before its pool had filled, so its `MemoryUsed` range starts at the idle level.

| Capacity value | B readings | `MemoryUsed` over B: min – max | `Count` over B | `HintsInProgress` over B | `TotalHints` A → end of B | Dumps in B (parked in `take()` / blocked on the monitor) | `waiting` lines | held flushes | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| n2 | 13 | 101,391,862 – 101,402,607 | 297 – 298 | 95 – 159 | 19,284 → 167,128 | B10 1/31, B30 1/31, B50 1/31 | 27 | 26 | `n2/summary.txt`, `readings.csv`, `hints-pool.txt`, `hold.txt` |
| n3 | 13 | 126,537,943 – 126,553,652 | 295 – 297 | 18 – 159 | 25,712 → 173,556 | B10 1/31, B30 1/31, B50 1/31 | 27 | 26 | `n3/summary.txt`, `readings.csv`, `hints-pool.txt`, `hold.txt` |
| n6 | 13 | 227,254,282 – 227,270,919 | 303 – 306 | 15 – 159 | 51,424 → 192,840 | B10 1/31, B30 1/31, B50 0/0 | 26 | 26 | `n6/summary.txt`, `readings.csv`, `hints-pool.txt`, `hold.txt` |
| n3 × 64 MiB, attempt 1 (200,000 rows) | 8 | 227,225,901 – 227,242,206 | 302 – 305 | 0 – 159 | 51,424 → 200,768 | B10 1/31 | 13 | 15 | `n3-buf64MiB-attempt1/summary.txt`, `readings.csv`, `hints-pool.txt`, `hold.txt` |
| n3 × 64 MiB, attempt 2 (400,000 rows) | 13 | 227,224,505 – 227,241,294 | 302 – 305 | 19 – 159 | 51,424 → 334,256 | B10 1/31, B30 1/31, B50 1/31 | 26 | 25 | `n3-buf64MiB/summary.txt`, `readings.csv`, `hints-pool.txt`, `hold.txt` |
| n3 natural (no hold) | 4 | 50,253,236 – 126,669,866 | 200 – 300 | 0 – 95 | – → 200,000 | B10 1/31 | 16 | – (no hold) | `n3-natural/summary.txt`, `readings.csv`, `hints-pool.txt` |

*The create trace* — every `created` line. The `waiting` and `hold` counts are in the table above.

| Capacity value | `created` lines | `max=` / `size=` on every line | `created=1` (thread, time) | `created=2…n` (threads) | time from A start to `created=n` | Evidence |
|---|---|---|---|---|---|---|
| n2 | 2 (numbered 1–2) | `max=2`, `size=33554432` | HintsWriteExecutor:1 | MutationStage-18 | 6560 ms | `n2/hints-pool.txt`, `summary.txt` |
| n3 | 3 (numbered 1–3) | `max=3`, `size=33554432` | HintsWriteExecutor:1 | MutationStage-18, MutationStage-12 | 7061 ms | `n3/hints-pool.txt`, `summary.txt` |
| n6 | 6 (numbered 1–6) | `max=6`, `size=33554432` | HintsWriteExecutor:1 | MutationStage-33, MutationStage-57, MutationStage-65, MutationStage-53, MutationStage-40 | 8066 ms | `n6/hints-pool.txt`, `summary.txt` |
| n3 × 64 MiB, attempt 1 (200,000 rows) | 3 (numbered 1–3) | `max=3`, `size=67108864` | HintsWriteExecutor:1 | MutationStage-25, MutationStage-60 | 8075 ms | `n3-buf64MiB-attempt1/hints-pool.txt`, `summary.txt` |
| n3 × 64 MiB, attempt 2 (400,000 rows) | 3 (numbered 1–3) | `max=3`, `size=67108864` | HintsWriteExecutor:1 | MutationStage-24, MutationStage-69 | 8080 ms | `n3-buf64MiB/hints-pool.txt`, `summary.txt` |
| n3 natural (no hold) | 3 (numbered 1–3) | `max=3`, `size=33554432` | HintsWriteExecutor:1 | MutationStage-27, MutationStage-95 | – | `n3-natural/hints-pool.txt`, `summary.txt` |

*The reading rule (9a), applied as written* — cluster tier, over the idle control; the band is ±4 MiB = 4,194,304 bytes. The rule sends a difference larger than the band to the create trace (§4.3, part 3).

| Capacity value | Idle `MemoryUsed` | At A | Rise over idle | Predicted `(n − 1) × bufferSize` | Difference | 4 MiB band | Other direct buffers added (`Count` rise − (*n* − 1)) |
|---|---|---|---|---|---|---|---|
| n2 | 58,531,181 | 101,402,479 | 42,871,298 | 33,554,432 | +9,316,866 (+8.89 MiB) | exceeded by 5,122,562 | 121 |
| n3 | 50,146,484 | 126,553,524 | 76,407,040 | 67,108,864 | +9,298,176 (+8.87 MiB) | exceeded by 5,103,872 | 119 |
| n6 | 50,190,380 | 227,270,919 | 177,080,539 | 167,772,160 | +9,308,379 (+8.88 MiB) | exceeded by 5,114,075 | 120 |
| n3 × 64 MiB, attempt 1 (200,000 rows) | 83,737,831 | 227,242,070 | 143,504,239 | 134,217,728 | +9,286,511 (+8.86 MiB) | exceeded by 5,092,207 | 122 |
| n3 × 64 MiB, attempt 2 (400,000 rows) | 83,744,966 | 227,241,158 | 143,496,192 | 134,217,728 | +9,278,464 (+8.85 MiB) | exceeded by 5,084,160 | 122 |

*Also recorded per value*, in `run1/cluster/<dir>/`: the `JVM_EXTRA_OPTS` line and the `cassandra.yaml` diff (`summary.txt`, `cassandra.yaml.diff`); `Submit -l` before and after the hold was loaded (`submit-l.txt`, `submit-l-loaded.txt`); the dump excerpts (`dump-*-excerpt.txt`); the stress result (`stress-excerpt.txt`); every command and its output (`session.log`). The ring's first-time step is `run1/ring/session.log`: two `UN` after 85 s, `keyspace1` with RF = 2, the stress table written with 0 errors, node 2 stopped and seen `DN` by node 1 after 4 s, both nodes stopped.

### 4.2 Conclusion and logic — unit tier

Files are in `run1/`. **[observed: file]** means the file says it; **[inferred: reason]** gives the reason. The
cluster tier's conclusion is §4.3.

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

**Conclusion (one line):** unit tier — consistent with **Confirmed**; no Refuted or Not-confirmed row fired. The cluster tier
is §4.3.

### 4.3 Conclusion and logic — cluster tier

Files are in `run1/cluster/<dir>/` (`<dir>` is `n2`, `n3`, `n6`, `n3-buf64MiB`, `n3-buf64MiB-attempt1` or `n3-natural`), in
`run1/ring/` and in `run1/diag-alloc/`. **[observed: file]** means the file says it; **[inferred: reason]** gives the reason.
The arithmetic behind every number is `run1/cluster-selfcheck.py` (output `cluster-selfcheck.txt`: 127 checks, all pass, §5.1).
Every thread-dump count was also recounted from the full dumps by a second method (`run1/dump-recount.txt`).

1. **Validity — valid for all five values.**
   - The code under test is the pinned tag and the instruments are the committed ones [observed: each `session.log` has
     `CHECK PASS: the clone is at cassandra-5.0.9` and three `sha256sum -c` `OK` lines for `HintsPoolCeilingTest.java`,
     `hints-pool.btm`, `hold-flush.btm`; the clone is `b5f2a54`, §2].
   - The knob took effect at every value: the JVM reports `cassandra.MAX_HINT_BUFFERS=<n>` [observed: `summary.txt`, from
     `jcmd VM.system_properties`], and every `created` line carries `max=<n>` and the `size=` the value should give: 33,554,432,
     and 67,108,864 in the second-knob arm, whose yaml diff adds exactly `commitlog_segment_size: 64MiB` and
     `max_mutation_size: 32MiB` [observed: `hints-pool.txt`, `cassandra.yaml.diff`]. So the pool read the knob and the second knob.
   - The limit was reached at every value: `created=<n>` appeared 6.6 to 8.1 s after the stress started [observed: the `A:` lines of
     `summary.txt`], and a writer then waited at the check: 26 or 27 `waiting` lines per value (13 in the shortened attempt, 16 in
     the natural-load control) and one thread in `LinkedBlockingQueue.take` under `HintsBufferPool.switchCurrentBuffer(…:118)` in
     every B dump but one [observed: `hints-pool.txt`; `dump-*-excerpt.txt`; `dump-recount.txt`].
   - Node 2 was down and hints flowed: `DN 198.22.255.91` at each start, `TotalHints` 0 at idle and rising through A, B and the
     release [observed: `summary.txt`, `readings.csv`]. The last value ended 23 minutes after node 2 was stopped, against
     `max_hint_window` of 3 hours (§2).
   - B was never cut short: the highest `HintsInProgress` was 159, against a stop level of 3,840 [observed: `readings.csv`].
   - The hold rule was in force where it should be: `Submit -l` lists the `FlushBufferTask` trigger after loading [observed:
     `submit-l-loaded.txt`], 25 or 26 `hold … delay=3000` lines per run (15 in the shortened attempt) [observed: `hold.txt`], and the
     natural-load control has neither [observed: no `hold.txt`, no `A: loading the hold` line].
   - The §9b "hold fixed" settings: each value's yaml is the tag's `conf/cassandra.yaml` plus the three ring edits (plus the two
     lines of the arm) and nothing else [observed: `cassandra.yaml.diff`]; 32 `MutationStage` threads in every dump, which is
     `concurrent_writes` [observed: `dump-recount.txt`].
2. **Readings — three things were not as the design expected.**
   - **The reading rule's 4 MiB band was exceeded at every value.** Rise over idle less `(n − 1) × bufferSize`: +9,316,866 (*n* = 2),
     +9,298,176 (*n* = 3), +9,308,379 (*n* = 6), +9,278,464 (*n* = 3 with 64 MiB buffers), which is +8.85 to +8.89 MiB against a band
     of ±4 MiB [observed: the last table of §4.1; `cluster-selfcheck.txt`]. The excess is the same at every value and both
     `bufferSize`s, within 38,402 bytes, and it was already there at A: `MemoryUsed` does not move afterwards (part 3). What it is, is
     in the supplementary diagnostic below. The rule itself says what to do with a larger difference: "decided by the create trace".
   - **NMT `Other` rose by 1.29 to 1.41 GiB between idle and A** (1,352,593 KB at *n* = 2, 1,385,343 at *n* = 3, 1,483,656 at
     *n* = 6, 1,450,860 in the arm), while `MemoryUsed` rose by only 41 to 169 MiB [observed: `readings.csv`]. NMT `Other` minus
     `MemoryUsed` rose by **1,310,726 to 1,310,727 KB, 1.25 GiB, at every value and both `bufferSize`s**, and is constant within
     11 KB from A to the release; the natural-load control agrees [observed: `cluster-selfcheck.txt`]. So the ~1.25 GiB is the
     same at every value and is not the pool. [inferred: native memory the network stack allocates without
     `ByteBuffer.allocateDirect`; it is exactly 80 × 16 MiB, which would be one netty chunk in each of 2 × 40 direct arenas, but no
     trace here covers it.] Consequence: the NMT cross-check of case 9d cannot isolate the pool at this load. It moves with
     `MemoryUsed` one for one, so it confirms `MemoryUsed` and adds nothing independent.
   - **The B50 dump at *n* = 6 found no writer in the pool** (0 parked, 0 blocked; all 32 `MutationStage` threads `RUNNABLE`
     [observed: `dump-recount.txt`]). The trace explains it: a `hold` line 114 ms before the dump and a `waiting` line 47 ms after it
     [observed: `n6/hold.txt`, `hints-pool.txt`, `summary.txt`: the dump is at ms 1790803175733]. [inferred: the dump landed in the
     ~0.15 s window after a flush had recycled a buffer and before the writers had refilled it.] The `waiting` lines either side are
     3.1 s apart like the rest, and the B10 and B30 dumps at this value show 1 parked and 31 blocked.
   - Also recorded: the 64 MiB arm's first attempt ran out of rows (§3, defect 3); the *n* = 2 run's idle `MemoryUsed` is 8 MiB
     higher than the others' (part 6).
3. **Matched row — "Confirmed"**, with the deviation in the fifth bullet:
   - *The pool holds exactly *n* buffers at every value:* 2, 3, 6 and 3 `created` lines, numbered 1 to *n*, none after the
     cap [observed: `hints-pool.txt`, table of §4.1]. `created=1` is the hints executor's, made at idle; `created=2…n` are
     `MutationStage` writers, made after the hold was loaded [observed].
   - *A writer waits at the check:* `waiting` lines and a parked thread in `take()` at `HintsBufferPool.java:118` with 31 blocked on
     the pool's monitor, in 13 of the 14 B dumps taken (12 of the 13 with the hold, and the natural-load control's one; the
     exception is the refill window above) [observed: `dump-recount.txt`]. The waits repeat once per flush: the `waiting` lines are
     about 3.1 s apart, one per held flush, and the hints admitted during B are the same at *n* = 2 and *n* = 3 (147,844 each),
     as they should be if the flush's recycle rate, not *n*, sets the pace once the pool is full [observed: `TotalHints`;
     inferred: the reading of that equality]. The writer is released by a recycled buffer, not by a new one.
   - *The ceiling moves with *n*:* the rise over idle is 42,871,298, 76,407,040 and 177,080,539 bytes at *n* = 2, 3, 6. From 2
     to 3 it rose by 33,535,742, one 32 MiB buffer being 33,554,432 (−18,690); from 3 to 6 by 100,673,499, three buffers being
     100,663,296 (+10,203) [observed: §4.1; `cluster-selfcheck.txt`]. Each step is one buffer to within 19 KB, which a constant
     background cancels.
   - *…and with `bufferSize`, as a product:* *n* = 3 × 64 MiB and *n* = 6 × 32 MiB both hold 201,326,592 bytes of pool buffers by
     the create trace, and `MemoryUsed` at A is 227,241,158 and 227,270,919, 29,761 bytes (0.013 %) apart [observed].
   - *Direct memory is up by the predicted amount (reading rule):* **read literally, this clause is not met.** The difference is
     +8.85 to +8.89 MiB and the band is ±4 MiB (part 2). The rule's own text decides it: "provided the create trace shows exactly
     *n* buffers … A larger difference is decided by the create trace (9d)". The trace shows exactly *n* at every value, so the excess
     cannot be pool buffers: a pool buffer is 32 or 64 MiB and the excess is 8.9 MiB [inferred: the pool creates buffers only in
     `createBuffer()`, `HintsBufferPool.java:130-134`, and every one of them is a `created` line]. Three observations then say it is
     not the pool: it is the same at every value and both `bufferSize`s (38 KB spread); it does not change during 60 s of pressure or
     after the release; and the natural-load control, which has no hold, carries the same non-pool memory (26.0 MB against
     25.9 MB at *n* = 3, `cluster-selfcheck.txt`) [observed]. The diagnostic below observes what it is.
   - *No bypass and no extra allocation:* nothing in the readings shows memory above the pool's ceiling that the pool made.
4. **Excluded rows.**
   - *Refuted — "more than *n* buffers are ever created":* excluded. Exactly *n* `created` lines at every value, through 60 s of
     pressure (about 141,000 to 283,000 hints written while the pool was at its cap) and after the release [observed]. At *n* = 3 an
     independent trace of every `ByteBuffer.allocateDirect` call shows exactly three calls of 33,554,432 bytes, all from
     `HintsBuffer.create` [observed: `diag-alloc/diag-analysis.txt`].
   - *Refuted — "exactly *n* buffers, but direct memory keeps rising above the predicted amount":* excluded. `MemoryUsed` never
     rose after A: from A through B and the release it stayed within +136 and −16,653 bytes of its value at A, at every value and for
     34 to 60 s [observed: `cluster-selfcheck.txt`]. The excess over the prediction is there at A and is constant.
   - *Refuted in part — "follows *n* but not `bufferSize`":* excluded; the arm lands with *n* = 6 (part 3).
   - *Not confirmed — "a writer waits but does not resume after the hold is released":* excluded. After the release `TotalHints`
     rose at every value that still had rows left (167,128 → 201,664; 173,556 → 201,664; 192,840 → 201,600; 334,256 → 401,536) and
     the release dump has no thread in `switchCurrentBuffer` [observed: `readings.csv`, `dump-recount.txt`]. The shortened first
     attempt of the arm cannot show it, since nothing was left to write (§3, defect 3); attempt 2 does.
   - *Refuted — "direct memory is flat across every value of *n*":* excluded; 42.9, 76.4 and 177.1 MB over idle.
   - *Not confirmed — "no writer is ever seen waiting":* excluded; part 3.
   - *Invalid run — "the cap was never reached":* excluded at every value; `created=<n>` was seen at A at all five.
   - *Not tested here:* *n* = 1 (excluded by design, 9b); the hint flow to node 2's return and replay; hints under
     `hints_compression`; a disk that is really slow. The natural-load control shows the cap is reached and enforced on this
     disk without the hold: 3 `created` lines, 16 `waiting`, one writer parked in `take()`, `TotalHints` exactly 200,000, 0 stress
     errors [observed]. It is a control, and no §9a row depends on it.
5. **Observed vs. inferred — what the conclusion rests on that was not directly seen:**
   - That the 8.9 MiB excess is non-pool memory is **observed at the allocation level at *n* = 3** by the diagnostic, and carried to
     the other values by their equality [observed: the excess equal within 38 KB] [inferred: the same load through the same code].
   - That the 8,392,704-byte call is the networking buffer pool rather than the file chunk cache: the site is
     `BufferPool$GlobalPool.allocateMoreChunks` [observed], on a netty `epollEventLoopGroup` thread [observed]; that it is the
     *networking* pool is [inferred: a native-transport event-loop thread, and no sstable is read in this workload].
   - That the 920,306 residual bytes are the live small buffers the diagnostic lists, and that the 3,992,242 bytes requested but not
     held were freed, is [inferred: 460 calls in the window against a `Count` rise of 123]. Frees are not traced.
   - That the ~1.3 GB of NMT `Other` is network-stack memory is [inferred]. It is constant and not the pool [observed]; the verdict
     does not use what it is.
   - That a parked writer is released by the flush's recycle, through `HintsWriteExecutor.FlushBufferTask`, at the cluster tier:
     [inferred from source, case §6b, and supported by the `waiting` lines being one per held flush and `TotalHints` advancing in
     steps of about one buffer per cycle]. The unit tier did the recycling itself; this tier uses the real path.
   - That the hold imitates a slow disk and does not make the path: [observed, by the natural-load control, which reaches the cap
     and waits with no hold].
6. **Deviations and gaps.**
   - **The reading rule's 4 MiB band was exceeded at every value** (parts 2 and 3). It is reported, not hidden, and §9a was not
     edited: the rule's own clause decides, and the feedback for stage 3 is in §8.
   - The 64 MiB arm was run twice. Attempt 1 (200,000 rows) ended its stress 34 s into B and took one B dump; attempt 2
     (`ROWS=400000`, an existing override of the script) ran the full 60 s with three dumps and a release that resumed the writers.
     Both agree on the excess (+9,286,511 and +9,278,464) [observed]. The row count is a documentation-only amendment of §9c
     and §9e (§3, defect 3).
   - The values ran one at a time over ssh, in the order *n* = 2, 3, 6, arm attempt 1, natural-load control, arm attempt 2, not
     the script's `all` order; each value is an independent JVM start.
   - The `n = 2` run's idle and A `MemoryUsed` carry 8 MiB more non-pool memory than the other four runs (idle 24,976,749 bytes
     against 16.59–16.70 MB, and +8,384,697 at idle, +8,403,387 at A) [observed]. The difference is the same at idle and at A, so it
     cancels in the rise over idle; [inferred: one extra 8 MiB `BufferPool` chunk in that JVM's start-up, not traced].
   - `cassandra-stress` logged `WriteTimeoutException` lines at every value with a hold (1,536 to 1,664 at full length, 768 in
     the shortened attempt) and still finished every row with `Total errors: 0` [observed: `stress-excerpt.txt`]. They are the expected symptom of writers queued behind the pool
     (case 9d), not evidence. The natural-load control had none.
   - One JVM per value and no repeat, apart from the arm. The four hold values agree on the excess within 38 KB, which is the only
     measure of run-to-run spread this tier has.
   - The first `B` reading of the natural-load control (`MemoryUsed` 50,253,236, `Count` 200) was taken before its pool had filled,
     so its B range in §4.1 starts at the idle level.
   - The diagnostic was written after the readings existed and is not part of the frozen design; it observes and changes nothing.
     Its first attempt died in start-up (below). The self-check's own corrections are in §5.1.
7. **Core question — does the constraint cap the resource, and does usage follow it?** Yes, on a running node, with the real flush
   path and the default and a doubled `bufferSize`. With `MAX_HINT_BUFFERS` = *n* the pool created exactly *n* direct buffers
   (2, 3, 6), however many hints arrived; when a writer needed one more it waited at `switchCurrentBuffer` line 118 rather than
   allocating, and was released by a recycled buffer, not a new one (parts 3, 4). The JVM's direct memory stopped rising at the *n*-th
   buffer and stayed flat for 60 s under pressure and after the release, stepped by one buffer per *n* to within 19 KB, and reached the
   same 192 MiB from 3 × 64 MiB as from 6 × 32 MiB to within 30 KB (part 3). One thing in the readings is not as predicted: the rise
   over idle is about 9.3 MB larger than `(n − 1) × bufferSize`, at every value, which the reading rule's 4 MiB band did not allow for.
   It is constant, it does not move with *n*, `bufferSize`, time or the hold, and the diagnostic shows it is not the pool.

#### Supplementary diagnostic — what allocated the non-pool direct memory (not a reading of the case)

**What and why.** Part 2's first bullet needed an explanation that did not rest on the create trace alone. The question: what
allocates the ~9.3 MB of direct memory between the idle control and scenario A? **How.** One more start at *n* = 3, 32 MiB buffers,
with the same options, hold and stress as the `n3` value, plus a Byteman rule (`run1/diag-alloc/diag-alloc.btm`) that writes one line for
every `ByteBuffer.allocateDirect` call: size, time, thread and stack. `allocateDirect` is the only way the bean's `MemoryUsed` rises.
It ran once, on 2026-09-30 at 21:42–21:44 UTC, through `run1/diag-alloc/diag-run.sh` and stopped after scenario A. **Attempt 1 failed
in start-up, not in the run:** a rule on a JDK class runs in the bootstrap class loader, which cannot see Byteman's classes, and node 1
died with `NoClassDefFoundError: org/jboss/byteman/rule/exception/EarlyReturnException` before it touched any data [observed: the
first attempt's `stdout.txt`, kept on node0 as `diag-alloc-n3.attempt-*`]. The fix is the agent option `boot:<byteman jar>` (now in
`environment.md` §5). The run-1 rules are on Cassandra classes and were never affected.

**Result** (`run1/diag-alloc/diag-analysis.txt`, from `diag-alloc.txt.gz`; 2,637 calls in all). Between the idle reading (21:42:55 UTC)
and A (21:43:10 UTC), `MemoryUsed` rose by 76,421,874 bytes and `Count` by 123 [observed: `readings.csv`]. The window holds:

| What allocated it | Calls | Bytes requested | Note |
|---|---|---|---|
| **The hints pool:** `HintsBuffer.create`, from `HintsBufferPool.createBuffer()` | 2 (`created=2`, `created=3`; `created=1` was before the window) | 67,108,864 (2 × 33,554,432) | All three `allocateDirect(33554432)` calls of the run are these; each matches a `created` line within 50 ms and on the same thread [observed] |
| `BufferPool$GlobalPool.allocateMoreChunks` → `allocateDirectAligned`, on an `epollEventLoopGroup` thread | 1 | 8,392,704 (8 MiB + 4 KiB alignment) | A macro-chunk (`MACRO_CHUNK_SIZE`, `BufferPool.java:385`; allocated at `:460`) of a `BufferPool`: the chunk-cache pool (`file_cache_size`) or the networking pool (`networking_cache_size`), `BufferPools.java:59`, `:67` |
| `DataOutputBuffer` scratch buffers: `expandToFit` (321 calls) and the 128-byte initial (97) | 418 | 1,341,053 | Threads: `Native-Transport-Requests` 375, `MutationStage` 42, `HintsWriteExecutor` 1 (`DataOutputBuffer.java:63-87`) |
| Compressed-sstable read-ahead and chunk buffers of `ReadStage` threads (`ThreadLocalReadAheadBuffer`, `ThreadLocalByteBufferHolder`) | 30 | 3,424,039 | 13 of them 256 KiB. **Not hints:** a read path, most likely the stress client's connect-time metadata queries [inferred] |
| netty `IovArray` buffers (16 KiB each) | 9 | 147,456 | `epollEventLoopGroup` threads |

The accounting: bytes requested 80,414,116, of which the pool's 67,108,864 and the 8,392,704 chunk; the bean's change less those three
is 920,306 bytes over the remaining 120 buffers (7,669 bytes each on average) [observed: `diag-analysis.txt`]. Of the window's 460
calls only 123 net buffers remained; the difference, 3,992,242 bytes, is [inferred] buffers the JVM freed (per-thread scratch buffers
replaced as they grew; read-ahead buffers released). **So the non-pool rise of 9,313,010 bytes is the 8 MiB + 4 KiB buffer-pool chunk
(8,392,704) plus about 120 small live buffers (920,306), none of them the hints pool.** The 8 MiB lump also explains the *n* = 2 run's
8 MiB higher floor (part 6). Limits: one run, at *n* = 3; frees are not traced; the same rule perturbs timing slightly (A took 10.3 s
here against 7.1 s in the `n3` run).

**Conclusion (one line):** cluster tier — **Confirmed**, with one recorded deviation from the reading rule's 4 MiB band (attributed by
observation to non-pool allocations); no Refuted or Not-confirmed row fired.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion — unit tier

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

### 5.1b Check of run 1's conclusion — cluster tier (§4.3)

The mechanical part is `run1/cluster-selfcheck.py` (output `cluster-selfcheck.txt`: **127 PASS, 0 FAIL**). It re-reads every committed file the conclusion cites and
asserts each relation; it prints the 4 MiB band result for every value and does not assert it. `run1/dump-recount.py` (output `dump-recount.txt`) recounts every thread dump
from the full dumps by a method other than the run script's. The table records what I re-read, part by part.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `summary.txt`, `session.log`, `cassandra.yaml.diff`, `submit-l*.txt`, `hints-pool.txt` and `hold.txt` of each value: the knob and the `max=` / `size=` fields match *n* and `bufferSize` at all five values and at attempt 1 of the arm; `DN` for node 2 at each start; yaml diffs of 3 lines (5 in the arm); 12 `CHECK PASS` and no `CHECK FAILED` per log; the natural-load control has no hold. One statement is not in any node log: that the harness folder equalled commit `0598801` when the node's copy was compared (a local check: empty `git diff`, the node's `SHA256SUMS` equal to `sha256sum` of the local files); node0's `sha256sum -c` covers the copy |
| 2. Readings | yes | The script asserts the numbers quoted in §4.3: flatness from A through B and the release (max +136, min −16,653 bytes), no new `created` line after the release, `TotalHints` rising at A, end of B and after the release, `HintsInProgress` ≤ 3,840, the NMT gap constant within 11 KB, and each dump. The dump excerpts were re-read: the parked frame at `HintsBufferPool.java:118` and a `waiting to lock` example are there, and the counts (1 and 31) agree with the recount. The B50 dump at *n* = 6 is explained by the trace timeline and by all 32 threads `RUNNABLE` |
| 3. Matched row | yes, **with the deviation stated in the part** | Each bullet maps to a check: *n* `created` lines, a parked writer, steps of one buffer within 19 KB, the arm within 29,761 bytes of *n* = 6. **One clause, read literally, does not hold:** direct memory within the 4 MiB band. Part 3 says so and applies the rule's own clause; I re-read that text at §9a ("A larger difference is decided by the create trace (9d)"), which is unchanged since the freeze (§9a hash in §1). **This is the part most open to disagreement.** If the band is read as binding on its own, the tier has "no §9a row fits" and the README's answer is to amend §9a and run the tier again. I do not read it that way, because each other clause is observed, the clause that is not met is covered by the rule's text, and the cause is observed at the allocation level (diagnostic). Jingsong may overrule |
| 4. Excluded rows | yes | Every Refuted and Not-confirmed row of §9a's table is addressed and tied to a reading: "more than *n*" by the trace and the allocation trace; "keeps rising" by the flat `MemoryUsed`; "never resumes" by `TotalHints` after the release and the release dumps, with attempt 1's empty release stated |
| 5. Observed vs. inferred | yes | The inferred statements are the only ones without a file line. The diagnostic turns the main one (what the excess is) into an observation at *n* = 3; the carry-over to the other values rests on the observed equality of the excess |
| 6. Deviations and gaps | yes | The band, the arm's two attempts, the run order, the *n* = 2 run's 8 MiB higher floor, the stress timeouts, the natural-load control's first B sample, the diagnostic's late addition and its failed first attempt. All are traceable to a file |
| 7. Core question | yes | The chain in part 7 uses parts 3 and 4 and states the one unpredicted reading; it claims the cluster-level result with the real flush path, at the default and a doubled `bufferSize`, and nothing about the node-level behaviours listed under "Not tested here" |

**The self-check's own corrections.** Stated because a check adjusted until it passes proves nothing. The first run of `cluster-selfcheck.py` printed 14 FAIL lines. Nine
came from an assertion that expected the committed dump excerpt to show all 31 blocked threads; the run script's `dump()` writes the parked thread and **one** blocked example
by design, and the 31 comes from the full dump. I replaced it with the check the design implies (the parked frame and an example in the excerpt) and added the independent
recount of the full dumps, which agrees everywhere. Five came from an NMT tolerance of 2 KB that I chose before reading the data; the real spread is 3 to 11 KB on a 1.3 GB
quantity, so I set the limit at 64 KB and wrote the reason into the script. `diag-analysis.py` had one FAIL on its first run: I had named the wrong method
(`HintsBuffer.allocate`); the trace said `HintsBuffer.create` and the source agrees (`HintsBuffer.java:75-77`, called from `HintsBufferPool.java:133`). While drafting §4.3 I also
corrected four statements against the data: the dump count (13 of 14, not "all but one of five runs"), a per-buffer hint figure I had derived and then dropped, the NMT figures
(recomputed: a 1.29–1.41 GiB rise, of which exactly 1.25 GiB is not `MemoryUsed`), and the range of client timeouts. None of these changed a reading or the conclusion.

### 5.2 Run 2?

**No** — 2026-09-30, for the unit tier. The readings are exact and were re-asserted mechanically; no part of §5.1 is
open; and the result neither refutes the case nor confirms a bypass. The inferred statements (part 5) are about the
cluster tier's questions. A run 2 is worth reconsidering for the cluster tier once it has run (answered below). *Criterion, for
reference:* choose yes when the conclusion rests on inferred statements, a part of §5.1 cannot be settled from run 1's evidence, or the result refutes the case or confirms a bypass.

**Cluster tier: no** — 2026-09-30. Against the criterion: the conclusion's inferred statements (§4.3 part 5) concern what the excess is beyond *n* = 3 and what the NMT
remainder is, and neither decides the row; every part of §5.1b holds and the checks were re-run after correction; and the result confirms the case, neither refuting it nor
confirming a bypass. What would change the answer is part 3 of §5.1b: if the band clause is read as binding, the tier has no matching row and the README sends it back to
§9a, not to run 2. A fresh session repeating the runbook would add independent readings of the same exceedance, not a different reading of the rule.

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
| Cluster | **Confirmed**, with one recorded deviation: the reading rule's 4 MiB band was exceeded at every value (+8.85 to +8.89 MiB). The rule's own clause sends it to the create trace, which shows exactly *n* at every value; the excess is attributed, by an allocation trace at *n* = 3, to non-pool allocations (one 8 MiB + 4 KiB `BufferPool` chunk and about 120 small buffers) | run 1 + self-check (§5.1b) + supplementary diagnostic (§4.3) | 2026-09-30 |
| Case, both tiers | **Confirmed**: `MAX_HINT_BUFFERS` caps the hints pool at *n* buffers, so at `n × bufferSize` of direct memory; a writer at the cap waits at `switchCurrentBuffer` (line 118) until a flush recycles a buffer, and nothing is created around the check. No bypass seen | both tiers | 2026-09-30 |

**Feedback filed (uncommitted, 2026-09-30):** the case file's §10 "Stage-4 feedback" field, for the unit tier and then the cluster tier.
Sections amended after a reading existed, all documentation only: §9c (Rows, second-knob arm; the stale "harness not written yet"), §9e (second-knob
arm), and the §9 intro's "run so far"; §9a and §9b are byte-identical to the freeze (§1). §8's ceiling claim and the Target-3 note: not amended (nothing
refuted; no bypass seen). The freeze was checked at the end of the cluster tier and holds.

**Recommendations for stage 3** (not applied: readings existed, and only a reading-independent mistake may be amended; the tier did not restart because
the rule's own clause covered the case):

1. **The reading rule's band.** 4 MiB under-estimated the direct memory outside the pool under this stress load, which was 8.85–8.89 MiB above idle at every value: one
   8 MiB + 4 KiB `BufferPool` macro-chunk allocated from a netty event-loop thread, plus about 120 small per-thread buffers (§4.3, diagnostic). Either state the lump (a
   band of about 12 MiB, with the reason) or, better, make the create trace the deciding evidence at the cluster tier and read `MemoryUsed` as the cross-check, by
   its step between values (one buffer within 19 KB) rather than its absolute rise. The design named the small per-thread buffers and missed the chunk.
2. **The NMT cross-check of 9d.** Under this load NMT `Other` holds a constant 1.25 GiB that is not direct `ByteBuffer`s, so it cannot isolate the pool; it only confirms
   `MemoryUsed`. Say so, or replace it with an allocation trace: `run1/diag-alloc/diag-alloc.btm` is a ready instrument (it needs the `boot:` agent option).
3. **Workload arithmetic for the second-knob arm.** Rows needed scale with `bufferSize`: each recycled buffer admits `bufferSize / hint size` hints, so 60 s of B at
   64 MiB needs about 330,000 hints (measured: `TotalHints` 51,424 → 334,256 over B). The estimate in 9c said 200,000 rows were enough for every value.
4. **Dump timing.** A dump can land in the ~0.15 s window after a recycle and before the refill (one of 14 here, *n* = 6, B50). The design asks for "two or three" dumps;
   take at least three per value and treat the `waiting` trace lines as the primary disallow evidence, the dumps as corroboration.
5. **Byteman on JDK classes.** A rule on a `java.*` class needs `boot:<byteman jar>` in the agent string, or the JVM dies in start-up (`environment.md` §5).
