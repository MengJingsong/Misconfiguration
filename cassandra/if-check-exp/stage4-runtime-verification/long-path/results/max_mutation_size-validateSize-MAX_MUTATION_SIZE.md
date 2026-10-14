# max_mutation_size-validateSize-MAX_MUTATION_SIZE — stage-4 results  <!-- file: long-path/results/max_mutation_size-validateSize-MAX_MUTATION_SIZE.md or short-path/results/max_mutation_size-validateSize-MAX_MUTATION_SIZE.md -->

> **Case:** [`max_mutation_size-validateSize-MAX_MUTATION_SIZE`](../../../stage3-ai-deep-read/long-path/cases/max_mutation_size-validateSize-MAX_MUTATION_SIZE.md)
> (short path: `../../../stage3-ai-deep-read/short-path/cases/max_mutation_size-validateSize-MAX_MUTATION_SIZE.md`)
>
> **Status:** verdict filed (2026-10-11) — **Confirmed at both tiers**; replay **bypass as recorded**; derived-cap control **shadowed as recorded**; no run 2
>
> **Path:** long. One results file per path, each in its path's folder.
> For a short-path file (`short-path/results/max_mutation_size-validateSize-MAX_MUTATION_SIZE.md`), the "case file" below is the short-path
> solution, and for each tier "§9a" means that tier's predictions and conclusions
> table: B2f and B2g (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or
> B3a–B3e. If the case has both paths, see [`comparison/max_mutation_size-validateSize-MAX_MUTATION_SIZE.md`](../../comparison/max_mutation_size-validateSize-MAX_MUTATION_SIZE.md)
> for the side-by-side.

**Relative links in this template** are written for where a *copy* of it lives
— inside `long-path/results/` or `short-path/results/` — not for the template's own location two levels up.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../../README.md`](../../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base commit `45d8542` plus the step-0 amendments of 2026-10-11 (uncommitted at freeze; committed in `b3cbff9`). §9 hash after the amendments: **`16618c143ee2192f29f8364b3a8a214e24d80b7f`** (`sed -n '/^## 9\. /,/^## 10\. /p' <case> \| git hash-object --stdin`). §9a is frozen at this version. |
| **Harness** | `../harness/max_mutation_size-validateSize-MAX_MUTATION_SIZE/` (written 2026-10-11; uncommitted at run 1, committed in `b3cbff9`). Node copy `pc66:~/stage4-harness-run/mms/`, `md5sum` equal to the repo before run 1. **Instrument checks (2026-10-11, shakedowns, not readings):** *unit* — `MaxMutationSizeGuardTest` at 256 KiB: the first try showed `add.at_limit.position_delta` = −4,980,701 because after `resetUnsafe(true)` no segment is active and `getCurrentPosition()` reads the last closed one (position 5,242,881 = end of buffer + 1); fixed in the harness with one small warm-up entry and a sync before *P*0 (adds a `same_segment` check), then 0 mismatches (delta 262,144). Logs `pc66:~/stage4-logs/mms-shakedown/`. *Cluster* — `cluster-run.py instrument` (1 MiB yaml): the first try stopped before the start because `make-node-yaml.sh` exited 1 on `diff`'s status (fixed); second try passed (i)–(vii): protocol 4, JMX reads, 1 KiB insert +1,396 B, logged batch of two 1 KiB rows OK, *M* + 8,192 refused with `(1056823/1048576)` and `OverSizedMutations` 0→1, idle 30 s moved 0 B, `system_views.settings` `max_mutation_size = 1MiB`. Logs `pc66:~/stage4-logs/mms/instrument/`. |
| **Tiers and values** | Unit: `max_mutation_size` 262,144 · 1,048,576 · 2,097,152 · unset (derived 2,621,440) B, plus the 3 MiB range control, with 5 MiB segments; upstream `GroupCommitLogTest`. Cluster (one node, `pc66`): 1,048,576 · 4,194,304 · unset (derived 16,777,216) B with 32 MiB segments; Phase 1 and Phase 2 at each, the derived-cap control and the replay arm at the default. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-11 |

### 1.1 Design audit

Citations re-read against the local clone `~/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`).

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Disk bytes of one commit-log entry, and the off-heap serialization buffer built for it (§7, §9a hypothesis). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | Four unit values and three node values, each set including the derived default; the default differs by tier and §9a says why (9a Testability, 9b). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | Disk: `ActiveContentSize` (= `lastSyncedOffset`, `CommitLogSegment.java:650-652`, a byte position in the segment, so it is the entry's bytes, not a separate counter), the unit allocation position, and `Data.db` after a flush. The off-heap buffer is not measured; 9d names that gap. |
| A. Core question | usage driven to the limit and past it | Met | *T* = *M* accepted, *M* + 1, ≈ *M* + 8 KiB and ≈ *M* + 1 MiB refused, at every value (9e). |
| B. Logic | each step says what it establishes | Met | "How this verifies the hypothesis", Logic (1)–(5), and each scenario's purpose in 9e. |
| B. Logic | prediction stated in numbers or a clear relation | Met | Exact boundaries per value, +*M*+8 content rise, ratio 1 : 4 : 16, counter boundary *T* + 5, the range-control message (9a Prediction). One relation was wrong for one write and is amended (rec. 1). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | Over-limit accepted, refused-but-log-moves (counter capped, resource grows), flat across values, transport refuses instead, logged batch not reached, counter arithmetic, range, invalid run (limit never reached is the exact-boundary-refused invalid row). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Stated as the first rule under the table: the message with both operands and `OverSizedMutations`. |
| B. Logic | alternative explanations and their controls | Met | Transport caps → derived-cap control and the hold-fixed caps; per statement vs. per entry → unlogged twin; replay → the 1 MiB fresh-write refusal next to the replayed row; background writes → idle control. |
| C. Specific | a human can follow it from the intro and §9a | Met | §9 intro and §9a. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met | Commands, payload arithmetic, observables and traps are given (9c–9e). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Exact except the yaml reset (names a `cassandra.yaml.orig` the clone does not have) and the run script's name; amended (recs. 2, 3). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Harness listed as step-1 work (9c); `pc66` has JDK 11.0.32.1, Ant, `~/cassandra-run1` at the tag, the bundled driver `lib/cassandra-driver-internal-only-3.29.0.zip`. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Largest write ≈ 17 MiB, below the 64 MiB transport caps and the ≈ 102 MiB per-IP in-flight cap at a 4 GiB heap; each phase's accepted bytes (≤ 17.6 MiB + startup writes) fit one 32 MiB segment; `pc66` has 47 GB free and 125 GiB of memory. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Read in context: `Mutation.validateSize():169-177`, `serializedSize():326-341` (the `(int)` casts), `CounterMutation.validateSize():91-98` and its serializer size `:379-382`, `CommitLog.add():300-336`, `IMutation.java:31`, `DatabaseDescriptor:891-901` (range message text matches 9a), `:2827-2830`, `:3237-3245`, `:619-626`, `CommitLogSegment.java:93`, `:96`, `:179-180`, `:201-256`, `:303-366` (a sync allocates the next 8-byte marker and sets `lastSyncedOffset` to it, so a synced entry raises the content size by entry + 8), `:650-652`; `CommitLog.getActiveContentSize():430-436`, MBean name `:95`; `CommitLogMetrics:55` (`OverSizedMutations`); `StorageProxy.mutateAtomically()` → `syncWriteToBatchlog()` → `performLocally()` (`Failed to apply mutation locally : ` at ERROR, `handler.onFailure`), `ReplicaPlans.forBatchlogWrite():238-267` (a single-node DC may host its own batchlog); `BatchlogManager.store():134-164` (durable); `CommitLogReplayer:326` applies with `writeCommitLog = false`, so replay never meets the guard; `Envelope.java:197`, `:429`, `:484` (v4 frame cap and its message). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Scenario B's "*T* = payload + *k*" fails for the *M* + 1 MiB write at *M* = 1 MiB: its 2,097,152 B payload, and the row body, cross the 3→4-byte unsigned-vint class, so *T* is payload + *k* + 1 to 3. State *T* = payload + *k* for the one-byte-over write only, and *T* − payload − *k* ∈ [0, 4] for the two farther writes. | Applied 2026-10-11 (9a Phase 1 scenario B, 9e step 4); committed in `b3cbff9` | A false MISMATCH would otherwise be recorded; does not depend on any reading. |
| 2 | 9b's reset restores `conf/cassandra.yaml.orig`, which the run clone does not have. Rebuild from the tag (`git show HEAD:conf/cassandra.yaml`), as the closed cases' `make-node-yaml.sh` do. | Applied 2026-10-11 (9b Reset, 9c table) | Runnable as written. |
| 3 | 9c names the run script `cluster-run.sh`; the closed cases use Python (`cluster-run.py`) for its arithmetic and checks. | Applied 2026-10-11 (9c table) | Name only. |
| 4 | §8's `limit × N` and the replica-side, read-repair and protocol-v5 paths are untested (9b Scope and §11 say so). | Left for stage 3 | Out of this design's scope; recorded. |
| 5 | Several §5 line anchors were spot-checked only where the prediction depends on them; the rest were checked by stage 3 on 2026-10-06. | Left for stage 3 | Not load-bearing for §9a. |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-11 (chain 13:47:49 – 14:13:28 node-local time, `max_mutation_size-validateSize-MAX_MUTATION_SIZE/run1/chain.log`) | not done |
| Node (CloudLab name and type) | `pc66` (`node0.jason92-317394`), 40 cores, 125 GiB | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 (2026-08-18) | |
| Ant (`ant -version`) | 1.10.12 | |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at `b5f2a54` (`cassandra-5.0.9`), harness tests copied in untracked | |
| Case-file commit / harness commit | base `45d8542` + the 2026-10-11 amendments (§9 hash `16618c14…`) / harness uncommitted at run 1, node copy md5-equal to the repo; both committed in `b3cbff9` | |
| Storage for node data | local disk, clone's `data/` (`/dev/sda3`, 47 GB free) | |
| Full logs (path, outside the repo) | `pc66:~/stage4-logs/mms/` (`unit/`, `1m`, `1m-batch`, `4m`, `4m-batch`, `default`, `default-batch`, `derived`, `replay`, `instrument/`; each with `session.log`, `system.log`, `summary.txt`, `readings.csv`); shakedowns in `pc66:~/stage4-logs/mms-shakedown/` | |

## 3. Runbook defects

None in run 1. (The two instrument-check fixes before run 1, the unit warm-up entry and `make-node-yaml.sh`'s exit status, are harness fixes recorded in §1; the step-0 amendments are in §1.1.)

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|

## 4. Run 1

**Scope:** both tiers, every value of 9b: unit 256 KiB · 1 MiB · 2 MiB · unset (2,621,440) + 3 MiB range control + upstream `GroupCommitLogTest`; cluster 1 MiB · 4 MiB · unset (16,777,216), Phase 1 and Phase 2 at each, the derived-cap control and the replay arm. **Command log:** `max_mutation_size-validateSize-MAX_MUTATION_SIZE/run1/chain.log`, `max_mutation_size-validateSize-MAX_MUTATION_SIZE/run1/<run>/summary.txt` and `readings.csv`; full `session.log` on the node.

### 4.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Upstream `GroupCommitLogTest` (six settings) | 180 run, 0 failures, 0 errors, 1 skipped (`testHeaderOnlyFileFiltering[1]`, unrelated); `testEqualRecordLimit`, `testExceedRecordLimit`, `testExceedRecordLimitWithMultiplePartitions` pass under all six | `max_mutation_size-validateSize-MAX_MUTATION_SIZE/run1/chain.log`; node `unit/TEST-…GroupCommitLogTest.xml` |
| Read-back (`getMaxMutationSize()`, `IMutation.MAX_MUTATION_SIZE`) | equal to the value set at all four: 262,144 · 1,048,576 · 2,097,152 · 2,621,440 | `max_mutation_size-validateSize-MAX_MUTATION_SIZE/run1/unit/<label>.out` |
| Calibration: *p\**, *k*; *T*(*p\**) = *M*, *T*(*p\**+1) = *M*+1 | *p\** = 262,081 · 1,048,513 · 2,097,089 · 2,621,376; *k* = 63 · 63 · 63 · 64; both equalities hold at all four | same |
| Boundary at `validateSize()` | *p\** returns, meter +0; *p\**+1 throws, `mutationSize` = *M*+1, message `(<M+1>/<M>)` (e.g. `(2621441/2621440)`), meter +1 — all four | same |
| `CommitLog.add()` accepted / refused | accepted: position +*M* exactly (262,144 · 1,048,576 · 2,097,152 · 2,621,440), same segment; refused: position +0, segment count unchanged, content +0, meter +1 — all four | same |
| Counter site | `CounterMutation` size = *T* − 12 + 5; *p\**−5 returns, *p\**−4 throws with *M*+1; meter +0 — all four | same |
| Idle 2 s | position +0 — all four | same |
| Range control (3 MiB, 5 MiB segments) | JVM fails: `commitlog_segment_size must be at least twice the size of max_mutation_size / 1024`; no STAGE4 line | `max_mutation_size-validateSize-MAX_MUTATION_SIZE/run1/chain.log`, `max_mutation_size-validateSize-MAX_MUTATION_SIZE/run1/unit/range.out` |
| Total | 22 checks × 4 values, 0 MISMATCH | `max_mutation_size-validateSize-MAX_MUTATION_SIZE/run1/unit/*.out` |

**Cluster tier** — content = `ActiveContentSize` delta around the write; meter = `OverSizedMutations` delta.

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| all | control | idle drift | 165 B over 30 s at each of 1 MiB, 4 MiB and the default (< 64 KiB) | `max_mutation_size-validateSize-MAX_MUTATION_SIZE/run1/<label>/summary.txt` |
| 1 MiB | control | 1 KiB write | +1,231 B | `max_mutation_size-validateSize-MAX_MUTATION_SIZE/run1/1m/summary.txt` |
| 1 MiB | calibration | guard operands | `(1056823/1048576)`, *k* = 55 | same |
| 1 MiB | A | exact *T* = *M* (payload 1,048,521) | OK; content **+1,048,584 = *M* + 8**; meter +0; readback 1,048,521 | same |
| 1 MiB | B | +1 B, +8 KiB, payload 2 MiB | each `InvalidRequest` with `(1048577/1048576)`, `(1056823/…)`, `(2097208/…)`; *T* − payload − *k* = 0, 0, **1** (vint class, amended 9a); meter +1 each; content +0 each; no rows | same |
| 1 MiB | flush | `Data.db` | 1,049,604 B (in [1,049,545, 1,057,737]); 0 ERROR lines in `system.log` | same |
| 4 MiB | A | exact | OK; content **+4,194,312 = *M* + 8**; *k* = 56; readback 4,194,248 | `max_mutation_size-validateSize-MAX_MUTATION_SIZE/run1/4m/summary.txt` |
| 4 MiB | B | three over-limit writes | refused by the guard, `M` = 4,194,304; meter +1 each; content +0 | same |
| 4 MiB | flush | `Data.db` | 4,195,333 B | same |
| default (16 MiB) | A | exact | OK; content **+16,777,224 = *M* + 8**; *k* = 56; readback 16,777,160 | `max_mutation_size-validateSize-MAX_MUTATION_SIZE/run1/default/summary.txt` |
| default | B | three over-limit writes | refused by the guard, `M` = 16,777,216; meter +1 each; content +0 | same |
| default | flush | `Data.db` | 16,778,245 B | same |
| 1 / 4 / 16 MiB | Phase 2 | unlogged twin, 2 × ⌊0.55 *M*⌋ | OK; content +1,153,695 · +4,613,999 · +18,455,201 (each **> *M***); both rows read back | `max_mutation_size-validateSize-MAX_MUTATION_SIZE/run1/<label>-batch/summary.txt` |
| 1 / 4 / 16 MiB | Phase 2 | logged batch | `WriteFailure` (code 1500, `UNKNOWN from localhost`); meter +1; content +0; no rows; `system.log`: `Failed to apply mutation locally` → `MutationExceededMaxSizeException: Rejected an oversized mutation (1153645/1048576) for keyspace: system. Top keys are: batches.…` at `Mutation.validateSize(Mutation.java:175)` ← `CommitLog.add(CommitLog.java:304)`; batchlog entries 1,153,645 · 4,613,951 · 18,455,153 | `max_mutation_size-validateSize-MAX_MUTATION_SIZE/run1/<label>-batch/failed-locally.txt`, `system.excerpt` |
| default, transport caps default | derived-cap control | `insert 20` of *M* + 8 KiB | `InvalidRequest: Request is too big: length 16785464 exceeds maximum allowed length 16777216.`; meter +0; content +145 (background); `insert 21 1024` OK | `max_mutation_size-validateSize-MAX_MUTATION_SIZE/run1/derived/summary.txt` |
| default → 1 MiB | C (replay) | row written under 16 MiB, `kill -9`, restart under 1 MiB | `Replaying …CommitLog-7-1791749438786.log, …787.log`, `Log replay complete, 47 replayed mutations`; **readback 30 = 16,777,160 B** under the 1 MiB limit; new write of the same size refused `(16777216/1048576)` | `max_mutation_size-validateSize-MAX_MUTATION_SIZE/run1/replay/summary.txt`, `replay-lines.txt` |

### 4.2 Conclusion and logic

1. **Validity** — valid. The limit read back equals the value set in every run [observed: `unit/*.out` read-back checks; cluster calibration lines `(T/M)` with *M* = 1,048,576 · 4,194,304 · 16,777,216, `<label>/summary.txt`]. The exact-boundary write was accepted (not refused by the transport, not timed out) at every value [observed: `A exact … OK`]. Idle drift 165 B ≪ 64 KiB; the 1 KiB control rose by 1,231 B, inside 1,044–1,536 [observed: `1m/summary.txt`]. Upstream green at the derived default [observed: `chain.log`]. Hold-fixed settings in force: batch sync, 10 s write timeout, 64 MiB batch threshold and transport caps [observed: `<run>/cassandra.diff`]; protocol 4 [observed: `instrument/summary.txt` (i)].
2. **Readings** — nothing contradicts. The well-over write at 1 MiB gave *T* − payload − *k* = 1, inside the amended 0–4 band (the amendment was made at step 0, before any reading). *k* is 55 at 1 MiB and 56 at 4 and 16 MiB, one more vint byte above 2,097,152 B, as §9c "If sizes drift" anticipates [observed: calibration lines].
3. **Matched row** — "Unit: at every value the boundary is exactly as predicted, and a refused `CommitLog.add()` leaves the position unchanged and marks the meter once. Cluster: the largest accepted entry follows the knob (1 : 4 : 16), every over-limit write is refused with the guard's message and counter and leaves no entry or row, and the logged batch is refused at the commit-log site" → **Confirmed**. Unit [observed: `unit/*.out`, 0 MISMATCH]; largest accepted entry (content rise − 8) = 1,048,576 · 4,194,304 · 16,777,216 = **1 : 4 : 16** [observed: `A exact` lines]; 9 over-limit writes refused with message and meter +1, content +0, no rows [observed: B lines, readbacks]; logged batch refused at `CommitLog.add` naming `system.batches` [observed: `failed-locally.txt`]. Plus **Bypass as recorded** (replay: 16,777,160 B row readable under 1 MiB) [observed: `replay/summary.txt`] and **Shadowed as recorded** (transport refuses at stock caps, meter +0) [observed: `derived/summary.txt`] — both expected, non-refuting rows.
4. **Excluded rows** — *Refuted (over-limit accepted)*: every over-limit write refused, no row, no content [B lines]. *Refuted (refused write moves the log)*: unit position +0 and content +0; node content +0 for all 12 refusals (9 Phase 1 + 3 logged batches). *Refuted (flat across values)*: 1 : 4 : 16. *Not confirmed (transport refuses instead)*: with the hold-fixed caps every refusal carries the guard's text and the meter. *Not confirmed (logged batch)*: `WriteFailure`, not `InvalidRequest`, naming `system`/`batches`. *Refuted in part (counter)*: boundary *T* + 5 and meter +0 at all four unit values. *Refuted (range)*: 3 MiB did not start. *Invalid run*: see part 1.
5. **Observed vs. inferred** — the conclusion rests on observed readings. Inferred: (a) the content rise of an accepted write is its commit-log entry plus one sync marker (*M* + 8) — from `CommitLogSegment.sync():303-366` and `contentSize():650-652`, and matched to the byte; (b) the off-heap serialization buffer is bounded with the entry — **not measured** (9d names the gap); it follows because the refusal precedes `CommitLog.add():306` (observed indirectly: refused adds leave every commit-log reading unchanged).
6. **Deviations and gaps** — none in run 1. Not tested by design (9b Scope, §11): *N* > 1 (`limit × N`), the replica-side site, read repair, protocol v5's derived message cap, `durable_writes = false`. Heap/off-heap bytes not measured.
7. **Core question** — Usage follows the constraint: the largest commit-log entry the node wrote equals the limit to the byte at 1, 4 and 16 MiB (parts 1, 3). The constraint caps it: one byte over is refused at every value, before any commit-log byte is reserved, both for client writes and for the logged batch that only the commit-log site sees (parts 3, 4). It caps per entry, not per statement (the unlogged twin wrote 1.1 *M*), and it does not cap what replay restores (16 MiB row under a 1 MiB limit) (part 3).

**Conclusion (one line):** Confirmed (both tiers) — with the replay arm **bypass as recorded** and the derived-cap control **shadowed as recorded**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Independent script `max_mutation_size-validateSize-MAX_MUTATION_SIZE/run1/selfcheck.py`, run on the node over the **raw** files (it re-parses each `session.log`'s JMX outputs and client lines in order, `system.log` and the unit `.out`/ant logs, without the run script's code): **113 checks, 0 failed, exit 0** (`max_mutation_size-validateSize-MAX_MUTATION_SIZE/run1/selfcheck.out`); its content deltas equal `readings.csv` at every Phase-1 write.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out` (calibration *M*, control 1,044–1,536, upstream green); `cassandra.diff` per run |
| 2. Readings | yes | *k* 55/56/56 and the +1 at 1 MiB pk5 re-derived from the raw client lines |
| 3. Matched row | yes | `dose-response … 1 : 4 : 16` check; unit per-value checks; Phase 2 `system.log` refusal block with `CommitLog.add` and `system`/`batches` |
| 4. Excluded rows | yes | refusal meter/content checks; derived and counter checks |
| 5. Observed vs. inferred | yes | (a) matches to the byte at three values; (b) stays an inference, stated as such |
| 6. Deviations and gaps | yes | none recorded; untested items listed in the case's 9b/§11 |
| 7. Core question | yes | follows Logic (1)–(5) of 9a |

### 5.2 Run 2?

**No** — 2026-10-11. The conclusion rests on observed, exact readings (byte-equal at every value) re-derived by an independent parser; the one confirmed bypass (replay) is the one stage 3 already recorded from the source and is attributed by its control arm (the fresh 1 MiB refusal beside the replayed row); nothing refutes the case.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

| Tier | Verdict (§9a row) | Basis | Date |
|---|---|---|---|
| Unit | **Confirmed** — boundary exact at 262,144 · 1,048,576 · 2,097,152 · 2,621,440; refused `add()` reserves nothing; counter boundary *T* + 5, unmetered; range control refuses to start; upstream green | run 1 + self-check | 2026-10-11 |
| Cluster | **Confirmed** — largest entry = *M* (1 : 4 : 16), 9/9 over-limit writes refused by the guard with no entry or row, logged batch refused at the commit-log site; **bypass as recorded** (replay restores a 16,777,160 B row under a 1 MiB limit); **shadowed as recorded** (stock v4 frame cap refuses first, meter +0) | run 1 + self-check | 2026-10-11 |

**Feedback filed:** the case file's §10 "Stage-4 feedback" updated, §8 and the Target-3 note amended for the replay bypass (dated 2026-10-11; committed in `b3cbff9`).
