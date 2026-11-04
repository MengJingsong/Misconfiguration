# native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided — stage-4 results  <!-- file: results/native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided.md; the stem ends in --guided or --autonomous -->
> **Case:** [`native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided`](../../stage3-ai-deep-read/cases/native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided.md)
>
> **Status:** **Closed 2026-10-20 — verdict filed: unit Refuted; cluster Refuted** (§9a row 2: "retained memory follows the knob, per request"). The claim under test (the negative estimate: the knob does not bound the memory held for a large request) does not hold: one 8 MiB v5 request held before its last frame kept 8,389,184 B (64 frame stashes) at 16 MiB and at the derived default, and 0 B at 4 and 1 MiB, where it was refused at its first frame; the reserves control lowered two held requests from 16.001 to 8.251 MiB. The source reading of the case's §10 Notes is borne out. No run 2 (§5.2).
> 
> **Outcome class:** false negative — stage-3 estimate vs the stage-4 effect on the constraint
>
> **Agent:** guided (the suffix of the case-file stem). One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Guided file, hash of §9's text after the audit's amendments (`sed -n '/^## 9\. /,/^## 10\. /p' <file> | git hash-object --stdin`): `14c3b5fd4cf4bfa36ad10c616a096d871b62ea60`, computed 2026-10-20 before any harness or run. §9a is frozen at this version, including the dated block 9f. Commit holding the file: `cd7fec5` (the step-0 audit commit on `main`). |
| **Harness** | `harness/native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided/` (written 2026-10-20 in step 1, before any reading; file list and checks in its `README.md`): `NativeMessageSizeHoldTest.java` + `unit-run.sh` + `unit-summary.py` (unit), `hold-client.py` (the raw v5 client of 9c, R3) + `drv.py`, `nms.btm`, `cluster-run.py`, `make-node-yaml.sh`, `Jmx.java` (cluster). Node copy `pc06:~/stage4-harness-run/nms/`, md5 compared with the repo before run 1. Instrument checks: the unit test compiled against the clone; `TestScript` on `nms.btm`: 6 rules type checked, no errors; cluster shakedown 1 on shakedown-only labels (2 MiB request, values of no 9a arm). |
| **Tiers and values** | Unit (9a step 1): `CQLMessageHandler` large-message path, first frame above, at and below the limit. Cluster (9e): knob 1 · 4 · 16 MiB (default derived = 16 MiB) with one 8 MiB v5 request held; positive control replaced by the two-request reserves arms (9f R1). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-20 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | 9a Claim, 9d: off-heap bytes in the networking buffer pool. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 9b knob 1, 4, 16 MiB; the default is derived (`min(max_mutation_size, in-flight limits)` = 16 MiB, `DatabaseDescriptor.java:3237-3245`). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | 9d networking pool `Size` minus baseline, `RequestDiscarded`, `RssAnon` cross-check; gap (Netty read buffers share the wrapper) named. |
| A. Core question | usage driven to the limit and past it | Met | 8 MiB request is above 1 and 4 MiB (disallow) and below 16 MiB (allow); the limit-at-request case is not run. |
| B. Logic | each step says what it establishes | Met | 9a block matches steps, prediction and rows. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | "About 8 MiB" and "about one frame" had no tolerance. **Amended** (R2). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | Rows: ≈ request size at every value + control lowers (Confirmed), ≈ one frame below the request and ≈ 8 MiB above (Refuted), ≈ one frame everywhere (Not confirmed), pool does not rise (Invalid), control flat (Not confirmed). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Confirmed needs equal retention across values and the control moving; the disallow evidence is `RequestDiscarded` and the oversize error text. |
| B. Logic | alternative explanations and their controls | Not met | The control (`native_transport_receive_queue_capacity` 2 MiB, reserves 256 MiB) cannot bind a multi-frame request: the closed `native_transport_receive_queue_capacity` case found large requests held to the reserves, and one 8 MiB request is far below 256 MiB. Without a binding control the file could not reach Confirmed. **Replaced** (R1). |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | Intro explains the multi-frame v5 path and why a single-frame request is outside the check. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Met | Knob, restart and the in-flight prerequisite are exact. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Control arithmetic (R1) and the tolerances (R2) were missing; the raw v5 client is named, not written. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | Raw v5 client (`hold_large_request.py`) is step-1 work; `SimpleClient` of the closed receive-queue harness can send frames. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 8 MiB per request × a few connections is small against 125 GiB RAM; restarts per value are cheap. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked: `CQLMessageHandler.java:551` (compare), `:799` (`tooBig` branch), `DatabaseDescriptor.java:910-915` and `:3237-3245`, `Config.java:284-288`, `BufferPoolMetrics` `Size` and scope `networking` (`BufferPools.java:45`). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Replace the positive control: two connections each hold an 8 MiB request; reference arm reserves 256 MiB / queue capacity 128 MiB (≈ 16 MiB), control arm reserves 12 MiB / queue capacity 1 MiB (≈ 8 MiB + a frame) | Applied 2026-10-20 (9a step 3, 9e C, 9f) | the filed control does not bind a multi-frame request; this one binds on the reserves without changing the knob |
| R2 | Tolerances: "about 8 MiB" = 6–10 MiB over the idle baseline; "about one frame" ≤ 1 MiB over it | Applied 2026-10-20 (9a, 9f) | numeric edges fixed before any reading |
| R3 | Write `hold_large_request.py` (raw v5 client), reuse `SimpleClient` | step 1 (harness) | prerequisites, not design changes |
| R4 | Source reading disagrees with the recorded rejection (§10 Notes); a Refuted result is the route to reverse it | left for stage 3 | not an audit matter; the estimate stays as filed |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's runbook observables:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-20: shakedown 21:18–21:22 MDT, unit 21:23:29–21:24:11, cluster 21:24:11–21:34:33 | not done |
| Node (CloudLab name and type) | `pc06` = `node2.jason92-320876` (40 cores, 251 GiB), driven over ssh from `pc07` | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54210`), built; only the harness test added (untracked) | |
| Case-file commit / harness commit | case file `cd7fec5` (frozen §9 `14c3b5fd…`, verified unchanged before run 1); harness not committed (repo working tree; node copy md5-identical before run 1, `pc06:~/stage4-harness-run/nms.md5`) | |
| Storage for node data | `pc06` local disk, `~/stage4-nms/` (data, logs, conf); nothing on `/proj` | |
| Full logs (path, outside the repo) | `pc06:~/stage4-logs/nms/` — `run1/unit/`, `run1/cluster/<label>/` (`client.txt`, `poll.csv`, `nms.trace`, `nmt-*.txt`, `system.log`, `stdout.txt`), `run1/selfcheck.txt`, `run1-chain.log`, `shakedown1/`, `run1-aborted-launch/`, `instrument/` (4 MB) | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | run 1 (launch) | order "unit tier, then cluster" | `unit-run.sh` had lost its execute bit in the copy to `pc06`, so the chain skipped the unit tier and started the `k16` node. Stopped (the node killed) at the yaml step, before any client connection or reading (`run1/aborted-launch/summary.txt`). | `chmod +x`; logs moved to `run1-aborted-launch/`; md5 re-compared (identical); run 1 relaunched from the unit tier. Harness defect, not a §9 defect. | 2026-10-20 | none needed (§9 unchanged) |
| 2 | run 1 (unit) | unit summary | `unit-summary.py` raised `KeyError: 'resp_msg'` (an empty value did not match `\S+`). The tests had run and passed; only the post-processing table was missing. | regex `\S*`; the summary re-run on the same raw `harness.out` (`run1/unit/unit-summary.txt`); no test re-run (no test step changed). The repo copy is the fixed one (md5 `b92575ad…`); the run used `881d41a3…`. | 2026-10-20 | none needed |

## 4. Run 1

**Scope:** unit tier (upstream `MessageSizeLimitTest` + `NativeMessageSizeHoldTest`, limits 1 · 4 · 16 MiB); cluster tier, one
node lifetime per label: `k16`, `k4`, `k1` (9e A, B), `kdef` (knob unset; supplementary), `ref`, `ctl` (9f R1). Request: 8 MiB
blob (body 8,388,664 B on the cluster, envelope 8,388,673 B = 65 frames); every frame but the last sent, held 30 s; reading at
5 s of the hold. **Command log:** `native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided/run1/`
(`run1-chain.log`, `unit/summary.txt`, `cluster/summary.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/harness.out`, `unit-summary.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Upstream `MessageSizeLimitTest` (3 tests) | 3/3 pass | `unit/summary.txt` |
| Harness instrument checks (handler found, hold reached, response) | 34/34 ok | `unit/harness.out` |
| Body *L* + 1 at *L* = 1 · 4 · 16 MiB | `tooBig`, **0 buffers / 0 B kept** with 8 · 32 · 128 frames received, `RequestDiscarded` +1, error 8704 "CQL Message of size *L*+1 bytes exceeds allowed maximum of *L* bytes" | `harness.out` |
| Body *L* and *L* − 1 | admitted: every received frame kept, 8 · 32 · 128 buffers = 1,048,568 · 4,194,272 · 16,777,088 B; discarded +0; RESULT | `harness.out` |
| **8 MiB request** (64 of 65 frames sent) | kept **0 B** at 1 MiB, **0 B** at 4 MiB (refused, error with body 8,388,726), **8,388,544 B** (64 buffers) at 16 MiB | `unit-summary.txt` |
| 64 KiB request (control, and after each limit) | one self-contained frame, no `LargeMessage`, RESULT; the connection keeps working after every refusal | `harness.out` |

**Cluster tier** — baseline = median networking-pool `Size` over 30–31 samples with the connection(s) idle (8,388,608 B in every
lifetime: the pool's first slab); reading at 5 s of the hold (`run1/cluster/summary.txt`, `<label>/poll.csv`, `client.txt`, `nms.trace`).

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| 16 MiB | control (64 KiB) | response; pool | RESULT; pool at its idle baseline | `k16/client.txt`, `poll.csv` |
| 16 MiB | A | retained (`Size` − baseline) | **8,389,184 B = 8.001 MiB** (= 64 × 131,081, all `OverflowSize`; `java.nio` direct +8,389,184 B) | `summary.txt` READING |
| 16 MiB | A | trace / response | `acq` SUCCESS, 64 buffers kept, `toobig=false`; RESULT; `RequestDiscarded` +0 | `k16/nms.trace` |
| 4 MiB | B | retained | **0 B** (`Size`, `OverflowSize`, direct all +0) | READING |
| 4 MiB | B | disallow evidence | `toobig` at the first frame, 0 buffers through the hold; `RequestDiscarded` +1; error 8704 "…size 8388664 bytes exceeds allowed maximum of 4194304 bytes"; follow-up request OK | `k4/nms.trace`, `client.txt` |
| 1 MiB | B | retained / disallow | **0 B**; same refusal evidence (…maximum of 1048576 bytes) | `k1/*` |
| unset (16 MiB) | supplementary | retained | 8,389,184 B, RESULT (config dump `native_transport_max_message_size=null`, derived 16 MiB) | `kdef/*` |
| 12 MiB, reserves 256 MiB | C reference | retained, 2 connections | **16,778,368 B = 16.001 MiB** (128 stashes); both `acq` SUCCESS; both RESULT | `ref/*` |
| 12 MiB, reserves 12 MiB, queue 1 MiB | C control | retained, 2 connections | **8,651,346 B = 8.251 MiB** (64 + 2 stashes); connection 2 `acq` INSUFFICIENT_GLOBAL, `ffl ret=false` (paused) for 33 s, admitted when connection 1 completed; both RESULT | `ctl/*` |
| all | real resource | `RssAnon` at 5 s | +1.2 to +2.0 MB in every arm (coarse; does not separate the arms) | READING lines |

Also recorded: after an admitted request completed, `OverflowSize` stayed at its held value to the end of the lifetime (`k16` 8,389,184 B;
`ctl` 16,778,368 B; tail of `poll.csv`), the `networking_cache_size` arm-L leak; refused requests left nothing.

### 4.2 Conclusion and logic

1. **Validity.** Valid. The held request took the v5 large-message path (`lm` line, 65 frames) [observed: `nms.trace`]; the pool rose
   for it at 16 MiB (+8.0 MiB) [observed: `k16/poll.csv`]; each knob took effect (config dump 16MiB · 4MiB · 1MiB · 12MiB, and the
   refusal text names the limit) [observed: `summary.txt`, `client.txt`]; hold-fixed settings in the dump: in-flight 256 MiB,
   queue capacity 128 MiB, `throw_on_overload=false`; one connection per scenario, two in C; heap 4G.
2. **Readings.** Nothing contradictory. The pool rise equals `OverflowSize` and the `java.nio` direct rise to the byte in every arm,
   and equals 131,081 B (6 + 131,071 + 4: a frame's stash) × the buffers the trace shows kept [observed: `selfcheck.txt`]. One
   sub-prediction of R1 missed: the control arm held 8 MiB + **two** frame stashes (262,162 B), not "at most one frame"; the
   paused connection's decoder held its first frame and one more [observed: retained − 64 × 131,081; inferred: which two].
3. **Matched row.** "Retained bytes are about one frame at 1 MiB and 4 MiB and about 8 MiB at 16 MiB → **Refuted** — retained memory
   follows the knob, per request": 0 B and 0 B (≤ 1 MiB) at 1 and 4 MiB, 8.001 MiB (in 6–10 MiB) at 16 MiB (R2 bands)
   [observed: READING lines]. The unit tier shows the same at the handler: 0 / 0 / 8,388,544 B [observed: `unit-summary.txt`].
4. **Excluded rows.** Confirmed: needs about 8 MiB at every value; 0 B at 1 and 4 MiB rules it out (the control did move, 16.001 →
   8.251 MiB, so the Confirmed row fails only on its first part). Not confirmed (one frame everywhere): 8.001 MiB at 16 MiB. Invalid
   (pool does not rise): +8.0 MiB at 16 MiB. Not confirmed (control flat): the control lowered retention by 7.75 MiB.
5. **Observed vs. inferred.** All load-bearing readings are observed at three instruments that agree to the byte (the server's
   `LargeMessage` state in the unit tier, the pool gauge and the per-frame trace in the cluster tier). Inferred only: that the
   131,081-B units are the decoder's per-frame stashes (from the size and the code, `FrameDecoder.stash()` → `getAtLeast()`, `FrameDecoder.java:334-336`), and why the
   control's paused connection held two of them.
6. **Deviations and gaps.** The two runbook defects of §3 (no reading affected). The request is the 9b prepared INSERT on the
   cluster and a QUERY with a bound blob in the unit tier (unit yaml `max_mutation_size` is small; the transport path is the same).
   NMT `Other` was recorded (`nmt-*.txt`) but not used; `RssAnon` is too coarse to separate 8 MiB arms (as 9d warns).
7. **Core question.** Usage follows the constraint, and the constraint caps it per request (Logic 1–2: the pool rose 8.0 MiB for a
   request under the knob and 0 B for the same request over it, part 3). The control showed the instrument sees a binding cap
   (Logic 3, part 4). Logic 4's condition for Confirmed (same retention at every value) fails, so the negative estimate is refuted:
   the check gates the buffering of every frame after the first, as the case's §10 Notes read from the source.

**Conclusion (one line):** §9a row 2 ("about one frame at 1 MiB and 4 MiB and about 8 MiB at 16 MiB") — **refuted** at both tiers.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (independent parser of `harness.out`, `client.txt`, `poll.csv`, `nms.trace`, `system.log`), run on `pc06`:
**59 ok, 0 fail** (`run1/selfcheck.txt`).

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | config dumps in every `system.log` (knob, in-flight, queue capacity, `throw_on_overload=false`); `lm` lines with size 8,388,673 in every trace |
| 2. Readings | yes | retained recomputed from `poll.csv` equals the run script to the byte in all six labels; pool rise = `OverflowSize` = direct rise; = 131,081 × kept buffers (+2 stashes in `ctl`, the missed R1 sub-prediction, recorded) |
| 3. Matched row | yes | bands recomputed: k16 about 8 MiB, k4 and k1 about one frame (0 B); derived row Refuted = the run script's |
| 4. Excluded rows | yes | k4/k1: `toobig=true`, n=0 through the hold, discarded +1, error 8704; control lowers (ctl one SUCCESS + one INSUFFICIENT during the hold; ref both SUCCESS) |
| 5. Observed vs. inferred | yes | every row-deciding figure observed; the stash attribution is inferred but exact in size, and the unit tier's direct handler reading does not depend on it |
| 6. Deviations and gaps | yes | defects 1–2 left no reading affected (aborted launch stopped before the client; summary re-run on unchanged raw output) |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | Logic 1 (pool rises at 16 MiB), 2 (reading per value), 3 (control moves it), 4 (not equal across values → not Confirmed; the Refuted row's two parts both hold) |

### 5.2 Run 2?

**No** — decided 2026-10-20. The result refutes the case's claim, which the README names as a reason to choose run 2, but here
nothing the verdict needs rests on inference or on a part the self-check could not settle: the refusal and the per-request
retention are observed exactly at three independent instruments in two tiers (handler state, pool gauge, per-frame trace), they
agree to the byte, the boundary is exact (*L* admitted, *L* + 1 refused) at three limits, and the outcome is the one the code
reading in the case's §10 Notes predicts. A repeat would add nothing (the same reasoning as `concurrent_compactors`, the other
Refuted case). A fresh session may still run it from `harness/<stem>/` unchanged.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2 says no).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative (from the case file; the Effect column below is what the run found, and a mismatch is the result).

**Claim tested:** "`native_transport_max_message_size` does not bound the memory held for a large request: the bytes the server
retains while it receives a large request do not depend on the knob." "Confirmed" below always means this claim held.

| Tier | Verdict (§9a row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Refuted** (row 2): the 8 MiB request kept 0 · 0 · 8,388,544 B at 1 · 4 · 16 MiB; *L* + 1 kept 0 buffers, *L* and *L* − 1 kept every frame | caps (per request) | run 1 + self-check | 2026-10-20 |
| Cluster | **Refuted** (row 2): 0 · 0 · 8,389,184 B at 1 · 4 · 16 MiB (and 8,389,184 B at the derived default) | caps (per request; node-wide = knob × concurrent large requests, held by the reserves) | run 1 + self-check | 2026-10-20 |

**Positive control** (9f R1): two held 8 MiB requests at knob 12 MiB kept 16.001 MiB with reserves 256 MiB and 8.251 MiB with
reserves 12 MiB / queue capacity 1 MiB (the second request paused at its first frame, `INSUFFICIENT_GLOBAL`, until the first
completed). Missed sub-prediction: 8 MiB + 2 frame stashes, not + at most one frame.

**Findings beyond the claim:** (1) the operand is the envelope's **body** size (`header.bodySizeInBytes`, `CQLMessageHandler.java:534`):
body *L* is admitted, *L* + 1 refused; the case's §4 "declared body size plus header" is off by the 9-byte header. (2) A refused
request is refused at its first frame and every later frame is released at once (0 B held through a 30 s hold), and the
connection keeps serving requests. (3) An admitted large request's frame stashes are 131,081-B overflow allocations whose
accounting is not returned after the request completes (`OverflowSize` stayed +8,389,184 B), the `networking_cache_size` arm-L leak,
seen again.

**Feedback filed:** the case file's §10 "Stage-4 feedback" field updated and a dated note added to its §8 (2026-10-20, not
committed); the recorded rejection in `predicted-negative.md` is left for stage 3 (a Refuted negative estimate is the route to
reversing it, case §10 Notes).
