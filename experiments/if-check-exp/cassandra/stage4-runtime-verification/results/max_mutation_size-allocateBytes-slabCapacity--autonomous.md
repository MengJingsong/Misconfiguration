# max_mutation_size-allocateBytes-slabCapacity--autonomous — stage-4 results  <!-- file: results/max_mutation_size-allocateBytes-slabCapacity--autonomous.md; the stem ends in --guided or --autonomous -->
> **Case:** [`max_mutation_size-allocateBytes-slabCapacity--autonomous`](../../stage3-ai-deep-read/cases/max_mutation_size-allocateBytes-slabCapacity--autonomous.md)
>
> **Status:** **Closed 2026-10-20 — unit Confirmed (B2g row 1); cluster Confirmed (B3g row 1 and R1 row 1) — caps.** Hint direct memory = slabs × slab size (32 MiB at the default and at 4 MiB, 64 MiB at 32 MiB, flat over 200,000 hints); three sub-predictions missed (RSS in 2 of 4 lifetimes; the B1 "writers briefly block" — at `MAX_HINT_BUFFERS=1` hint writers deadlock for good; R2's guard identity — the 17 MiB write is refused by the CQL frame limit, not `max_mutation_size`); no run 2
> 
> **Outcome class:** true positive — stage-3 estimate vs the stage-4 effect on the constraint
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

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
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments: `8ecb18b22d2fe470942b0dbbb77bfb1636fddd9cda4c3f5b0058d467dfe352ca` (`sha256sum`, run 2026-10-20 before any harness or run; the new line in `_INDEX.md` §4 is this one). Commit holding the file: `cd7fec5` (the step-0 audit commit on `main`). |
| **Harness** | [`harness/max_mutation_size-allocateBytes-slabCapacity--autonomous/`](../harness/max_mutation_size-allocateBytes-slabCapacity--autonomous/README.md) — written 2026-10-20 after the audit, before any reading: `SlabCapacityProbeTest.java` + `unit-run.sh` (B2), `slab.btm`, `make-node-yaml.sh`, `client.py`, `Jmx.java`, `cluster-run.py` (B3). Not committed. Instrument checks and shakedowns: §1.2. |
| **Tiers and values** | Unit (B2): `HintsBuffer.create(C)` with C = 1 · 4 · 32 MiB, fill to the first null, boundary at `C/2 − 12`, `recycle()`, plus the derived-slab arithmetic. Cluster (B3): node A with `max_mutation_size` unset (16 MiB, slab 32 MiB) · 4096 KiB (floor) · 32768 KiB (slab 64 MiB), and `MAX_HINT_BUFFERS` 3 · 1; node B down. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-20 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1/A2: direct (off-heap) memory of the hint slabs. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b slabs 1 · 4 · 32 MiB (default 32); B3b `max_mutation_size` default · 4 MiB · 32 MiB and `MAX_HINT_BUFFERS` 3 · 1. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B3d direct pool deltas and RSS; slab fill is private and inferred (named). |
| A. Core question | usage driven to the limit and past it | Met | About 420 MB offered = 13 slabs of 32 MiB, 6.5 of 64 MiB; B2c fills to the first null. |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps each state their reading. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f exact (n = floor(C/(h+12)), growth exactly C, `C/2 − 12` legal); B3f 32–96 MiB plateau, 64–192 MiB at 64 MiB slabs. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | B3g had no row for `MAX_HINT_BUFFERS=1` and none for a 17 MiB write accepted. **Added** (R1). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Confirmed needs a plateau at k × slab with k ≤ `MAX_HINT_BUFFERS` that scales with the slab; the disallow evidence is the closed slab and the null allocation. |
| B. Logic | alternative explanations and their controls | Met | B3h: hinted handoff off, noise from a repeat, B down for the whole run; `MAX_HINT_BUFFERS=1` is a second knob that binds. |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | A1-A3 and B1 state claim, derivation and floor. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Met | Runnable from B2/B3 plus the amendment block. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | `hints_flush_period` was written "3600000ms-style" and the 17 MiB bullet mixed two guards. **Amended** (R2, R3). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | Two-node setup exists; the unit probe and the hint writer are step-1 work (`cassandra-stress` or a CQL loop, 8 MiB values). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Disk under 3 GB per run; heap 2 GiB, `MaxDirectMemorySize` 2 GiB bound the worst case. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked: `HintsBuffer.java:58,75-96,148-157` (`create`, `isClosed`, `capacity`, `remaining`, `recycle`, `capacity/2` guard), `HintsService.java:79,110`, `DatabaseDescriptor.java:894-901`, `Config.java:444-448` (`hints_flush_period` 10 s). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Add B3g rows for `MAX_HINT_BUFFERS=1` (plateau at one slab; or equal to the default) and the 17 MiB write accepted | Applied 2026-10-20 (B3g, amendment block) | outcomes the prediction names had no row |
| R2 | The 17 MiB write is refused at the coordinator; the slab's `capacity/2` guard is a unit-tier test only | Applied 2026-10-20 (B3f, amendment block) | two guards were mixed in one bullet |
| R3 | `hints_flush_period: 3600000ms` | Applied 2026-10-20 (B3a, amendment block) | exact value |
| R4 | Write the unit probe and the hint writer | step 1 (harness) | prerequisites, not design changes |

### 1.2 Instruments, shakedowns and harness-level reading rules (before run 1)

**Instrument checks (not readings).**
- `slab.btm`: Byteman `TestScript`, no errors. The first version did not parse because of a cast in a `BIND`; fixed.
- Unit shakedown (`~/stage4-logs/mss/shakedown/unit/`): `HintsBufferTest` 2/2, `HintsBufferPoolTest` 1/1, and `SlabCapacityProbeTest` 115/115 checks.
- Cluster shakedown 1 (arm D, 20,000 writes): it failed at once because `make-node-yaml.sh` had lost its execute bit, so `cluster-run.py` now runs it with `bash`. A second attempt ran the whole workload but failed when writing `phases.json`, because a dict had tuple keys; fixed.
- Shakedown 2 (`OFF`, `D` at 20,000 writes, then `analyze`) found two wrong harness expectations, both fixed before run 1. Neither is a case prediction:
  - (a) The control also makes one slab before any hint (below), so the control check became "no slab created after the baseline".
  - (b) Every thread that raced past a full slab before `position.set` also reaches line 190's true branch with `prev > cap`. So the invariant is `prev + total > cap` on every `closed` line, and `prev ≤ cap` on exactly the first line of each fill.
- The self-check parser was tested on the shakedown files (a code test, not a reading).
- Before run 1 the node copy and the repo copy matched by md5 (`run1/mss.md5`). After a harness fix during run 1 (§3, defect 2) they matched again (`run1/mss-2.md5`).

**Found in shakedown 2 from the source and the trace, before any reading.** On an idle node the first slab is created before any hint, about RING_DELAY after start. The path is `BatchlogManager` → `HintsService.flushAndFsyncBlockingly` → `HintsWriteExecutor$PartiallyFlushBufferPoolTask.run` → `HintsBufferPool.currentBuffer()` → `createBuffer()`. The trace shows `created n=1 … thread=HintsWriteExecutor:1` with that stack. That slab therefore sits inside B3e's pre-write baseline in every arm, including the hints-off control.

**Harness-level reading rules, fixed before any reading.** They say how a reading is formed and do not change or override B3f/B3g; where B3f gives a number, B3f's number is the prediction. Full text: the harness README.
- *Hint-attributable direct* X = (A's direct `MemoryUsed` − its pre-write baseline) in the arm − the same delta in the `OFF` control (`hinted_handoff_enabled: false`, same workload), at the same mark. B3h's control 1 is used as the noise subtraction.
- *Pool direct* = X + (`created` lines before the baseline × slab). This is what is compared with B3f's "32–96 MiB" etc. The literal X is reported beside it.
- *Band* B = 8 MiB, for B3f's "plus noise" and "within noise": a quarter of the smallest slab, so it cannot hide a slab.
- *RSS "about the same"*: (ΔRSS arm − ΔRSS `OFF` + pre-baseline slabs) within 25 % of the pool direct at the end.
- *"Same as default"* (M4): within [min, max] of the two default runs ± B. *"Step doubles"* (M32): pool / slabs over the default's, in [1.8, 2.2].
- *"Hint write latency rises"* (B1): the count and the maximum of `HintsBufferPool.write` calls ≥ 5 ms both exceed every default run's. The client's latency is reported beside them.

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts. Run 2 was not chosen (§5.2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-20, 22:04–22:44 MDT (unit 22:04–22:05; lifetimes OFF 22:05, D-1 22:09, M4 22:13, M32 22:18, B1 22:22–22:40, D-2 22:40–22:44) | not done |
| Node (CloudLab name and type) | `pc06` = `node2.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB), used by this session alone. **Environment deviation:** the audit assumed the two-node setup `pc57` + `pc50`, which is no longer in the experiment. Node A (127.0.0.2, JMX 7102, the seed, the coordinator, the measured node) and node B (127.0.0.3, JMX 7103) ran on loopback on `pc06`, with the recipe of `internode_max_message_size-inferMessageSize` (2026-10-20). B is down for every workload, so the design is unchanged. | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18); A at `-Xmx2G`, `-XX:MaxDirectMemorySize=2g`; B at 1 GiB | |
| Ant (`ant -version`) | 1.10.12 | |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54210d541339c2e7c17a794195cac0e67c2`); `ant build-test` already done. Untracked: an earlier case's `NativeMessageSizeHoldTest.java`, and this case's `SlabCapacityProbeTest.java` | |
| Case-file commit / harness commit | case file `cd7fec5`, sha256 `8ecb18b2…` at run 1 (checked unchanged before the case-file edit of section D); harness not committed, md5s in `run1/mss.md5`, `run1/mss-2.md5` | |
| Storage for node data | `pc06` local `/dev/sda3` (ext4, 55 GB free): `~/stage4-mss/{A,B}` (data, commit log, hints; wiped at each lifetime start; deleted after run 1) | |
| Full logs (path, outside the repo) | `pc06:~/stage4-logs/mss/` — `run1/unit/`, `run1/cluster/<arm>-<rep>/` (`session.log`, `samples*.csv`, `mss.trace` with full stacks, `A-jstack-deadlock.txt` for B1), `run1/selfcheck.txt`, `run1-chain.log`, `run1-stderr.log`; shakedowns `shakedown/`, `shakedown2/`; the D-2 attempt that never started, `run1/cluster-D-2-notstarted/` | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | run 1 | B3e step 4, arm B1 (`MAX_HINT_BUFFERS=1`) | The workload could not finish as written. One slab existed (made before the baseline). It filled after 15,849 hints. The writer that switched slabs then parked in `reserveBuffers.take()` (`HintsBufferPool.java:118`) while holding the pool's monitor. The full slab is flushed only after `switchCurrentBuffer()` returns (`:79-80`), so it was never flushed or offered back. The other 31 `MutationStage` threads blocked on the monitor; MutationStage showed 32 active, 41,483 pending; TotalHints stayed at 15,849 for 656 s. This is not a harness fault: it is the reading (§4). | The thread dump and tpstats were taken (`run1/cluster/B1-1/`). The bulk client was then killed by PID at 22:36:20 so the lifetime would end, and the hung node by PID at 22:40:07, after `stopdaemon` timed out at 180 s. **No tier restart:** this is the B1 outcome that R1's rows judge, not a step the protocol can fix. The readings taken before the kill are used as they are. | AI, 2026-10-20 | none; the finding goes to section D |
| 2 | run 1 | harness (B3e step 7) | `stop_node` did not catch `stopdaemon`'s 180 s timeout, so the hung B1 node was left running. D-2's first attempt then refused to start ("a CassandraDaemon is already running") and did no workload. | `stop_node` now falls back to `kill -9` after the timeout. The repo and node copies were re-synced and matched by md5 (`run1/mss-2.md5`). D-2 ran from its start (22:40–22:44). The unstarted attempt is kept as `cluster-D-2-notstarted/`. | AI, 2026-10-20 | harness only |
| 3 | after the freeze, from the source (before run 1) and confirmed in the run | B3f 17 MiB bullet, as read through R2 | R2 says the coordinator refuses a 17 MiB write "with a mutation-too-large error". In fact the CQL transport refuses it first. Under protocol 4 (the harness's client) the refusal is `Envelope.java:429` (`native_transport_max_frame_size`, 16 MiB: "Request is too big: length 17825848 exceeds maximum allowed length 16777216."). Under v5 it would be `native_transport_max_message_size`, which defaults to min(`max_mutation_size`, heap/10, heap/40) = 16 MiB here. `Mutation.validateSize` is never reached, so the case's intended guard is pre-empted. | **Not raised:** the frozen design does not set either transport limit. R2's observable claims are judged as written: the write fails, no hint is written, no direct change. The guard's identity is recorded as a missed sub-prediction and filed in section D. The guard the case meant does fire in M4: its 8 MiB writes are refused by `validateSize` ("Rejected an oversized mutation (8388664/4194304)"). | AI, 2026-10-20 | section D only |

## 4. Run 1

**Scope:**
- Unit tier: upstream `HintsBufferTest`, `HintsBufferPoolTest`, and the harness `SlabCapacityProbeTest`.
- Cluster tier: six lifetimes, `OFF`, `D` ×2, `M4`, `M32`, `B1`. Each has 200,000 × 2,048 B (S), then 4 × 8 MiB (L), then one 17 MiB write (X), all at CL ONE through A, with B down.
- Then `analyze` and the self-check.

**Command log:** `run1/run1-chain.log`, `run1/mss-chain-run1.sh`, `run1/mss-chain-run1b.sh`; per lifetime `run1/cluster/<arm>-<rep>/summary.txt` (the full `session.log` is on the node).

### 4.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Upstream `HintsBufferTest`, `HintsBufferPoolTest` | 2/2 and 1/1 pass | `run1/unit/summary.txt`, `TEST-*.xml` |
| `create(C)`: direct `MemoryUsed` +C exactly, `Count` +1 (C = 1 · 4 · 32 MiB) | +1,048,576 · +4,194,304 · +33,554,432; `Count` 2 → 3 each time | `run1/unit/harness.out` (`create` lines) |
| Fill to the first null: n = ⌊C/(h+12)⌋, Σ ≤ C, `remaining()` = C − Σ after every allocation, then 0 and closed | 1 MiB: n = 9,362 · 1,012 · 2; 4 MiB: 37,449 · 4,048 · 2; 32 MiB: 299,593 · 32,388 · 2 (h = 100 · 1,024 · C/2 − 12), each = the formula; Σ ≤ C; the next allocation would exceed C | `harness.out` (`case … n=` lines and checks) |
| Closed slab: 5 more allocations null; no direct growth while filling or after the close | holds for all 9 (C, h) | `harness.out` |
| `recycle()`: same n again, capacity C, no direct growth | holds for all 9 | `harness.out` |
| `C/2 − 12` accepted on an empty slab; `C/2 − 11` and `C/2` throw `IllegalArgumentException`; the slab untouched afterwards | holds at all three C | `harness.out` |
| Derived slab `max(2·mms, 32 MiB)`: 4 MiB → 32, 16 MiB → 32, 32 MiB → 64 MiB; default mms 16,384 KiB → 32 MiB | holds (arithmetic, as B2b says) | `harness.out` |
| `free()` (extra) | `MemoryUsed` −C, `Count` −1 | `harness.out` |
| All | 115/115 checks, 0 mismatches | `harness.out`, `summary.txt` |

**Cluster tier.** MiB = 2^20 B. Δ = change from the pre-write baseline. "Pool" = (Δarm − ΔOFF) + slabs made before the baseline × slab (§1.2).

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| hints off | control (`OFF`) | direct Δ at end of S / at end; RSS Δ at end of S / at end; slabs; TotalHints | +0.27 / +0.48 MiB; +96.9 / +146.3 MiB; 1 slab, made before the baseline, none after; 0 hints | `run1/cluster/OFF-1/summary.txt`, `samples.csv`, `mss-trace-nondirect.txt` |
| default (mms 16 MiB → slab 32 MiB, 3 buffers) | `D-1` | slabs (`created` lines); pool at the 1.5-slab moment, end of S, end, peak; hints | 2 × 33,554,432: n=1 from `HintsWriteExecutor:1` 133 s before the bulk start; n=2 from `MutationStage-19` 3.5 s into S; then none. Pool 64.1 · 64.23 · 64.23 · 64.23 MiB. 200,004 hints, 13 slab fills, 13 slabs offered back, hints directory 431.8 MB | `D-1/summary.txt`, `phases.json`, `samples.csv`, `mss-trace-nondirect.txt`, `mss-trace-direct.txt` |
| default | `D-2` (B3h control 3) | the same | 2 slabs (1 before the baseline); pool 64.22 MiB at end and peak; 200,004 hints, 13 fills | `D-2/…` |
| `max_mutation_size: 4096KiB` | `M4-1` | slab size; pool; L writes | 2 × 33,554,432; pool 64.17 MiB (end and peak); 200,000 hints, 12 fills. The 4 × 8 MiB writes were refused by `Mutation.validateSize` ("Rejected an oversized mutation (8388664/4194304)"), with no hint written | `M4-1/…`, `keys.csv` |
| `max_mutation_size: 32768KiB` + `commitlog_segment_size: 64MiB` | `M32-1` | slab size; pool; step per slab | 2 × 67,108,864; pool 128.22 MiB (end and peak); 64.11 MiB per slab vs 32.11 MiB at the default = **1.996×**; 6 fills; the 8 MiB writes were accepted | `M32-1/…` |
| default slab, `MAX_HINT_BUFFERS=1` | `B1-1` | slabs; pool; waiting; offer; hints; thread dump | 1 × 33,554,432 `max=1`, made before the baseline; pool 31.89 MiB (peak 31.91); 1 `waiting` line (`MutationStage-9`, 138 s after the slab was made); **0 `offer` lines**; TotalHints stopped at 15,849 and stayed flat for 656 s, while `TotalHintsInProgress` rose from 95 to 21,018. The dump shows `MutationStage-9` in `LinkedBlockingQueue.take` inside `switchCurrentBuffer`, holding the pool monitor; 31 threads waiting to lock it; `HintsWriteExecutor:1` idle; MutationStage 32 active / 41,483 pending. Client never returned; `stopdaemon` hung | `B1-1/summary.txt`, `samples.csv`, `mss-trace-nondirect.txt`, `jstack-*.txt`, `A-tpstats-deadlock.txt`, `deadlock-evidence-ms.txt` |
| all hint arms | — | RSS (arm − OFF + pre) at the end vs pool; at the end of S (context) | D-1 96.6 vs 64.2; D-2 68.3 vs 64.2; M4 68.3 vs 64.2; M32 199.1 vs 128.2 MiB. At the end of S (before the 8 MiB phase): 70.4 · 55.3 · 65.2 · 155.0 MiB | `samples.csv`, `run1/selfcheck.txt` |
| all hint arms | — | hint write latency (client mean / p99; `HintsBufferPool.write` ≥ 5 ms: count / max) | D-1 3.37/10.49 ms, 80/46.6 ms; D-2 4.41/13.56 ms, 85/51.8 ms; M4 3.67/10.93 ms, 76/45.9 ms; M32 3.79/11.75 ms, 75/87.6 ms; B1: no client result, 22/7.4 ms *completed* writes, then 32 writes that never returned | `summary.txt`, `mss-trace-nondirect.txt` |
| every arm that reached it (not B1) | — | the 17 MiB write (X) | refused: "Request is too big: length 17825848 exceeds maximum allowed length 16777216." (`native_transport_max_frame_size`, protocol 4); TotalHints +0; no slab; direct +0.03 MiB. M32 the same (no prediction) | `*/summary.txt`, `keys.csv` |
| every hint arm | — | line 190's true branch (`closed` lines) | every line has `prev ≥ 0`, `prev + total > cap`, `cap` = the slab: 55 · 70 · 66 · 62 · 32 lines; the first of each fill has `prev ≤ cap` | `mss-trace-nondirect.txt` |
| every arm | — | B down | B alive in 0 samples after the baseline; A sees `DN` at the end; `listpendinghints` lists the files for B, status DOWN | `summary.txt`, `samples.csv` |

### 4.2 Conclusion and logic

1. **Validity — valid** at both tiers.
   - Unit: the pinned tag and the harness test whose md5 is recorded [observed: `run1/unit/summary.txt`].
   - Cluster, every hold-fixed setting read back from `system_views.settings` on A: `hints_flush_period` 3600000ms (R3), `max_hints_size_per_host` 0B, `hinted_handoff_enabled` as the arm, `max_mutation_size` 16384 · 4096 · 32768 KiB, `commitlog_segment_size` 32/64 MiB; `MaxDirectMemorySize` 2g and `MAX_HINT_BUFFERS=1` on A's command line [observed: `*/summary.txt`].
   - B was down for every workload [observed: `samples.csv` `b_alive` 0; `DN`].
   - The limit was reached and passed: 200,000 hints, 13 slab fills at 32 MiB and 6 at 64 MiB, 0.40–0.43 GB of hint files [observed: `summary.txt`, `mss-trace-nondirect.txt`].
2. **Readings — what is unusual:**
   - (a) The first slab is made by an idle batchlog flush, before any hint (§1.2) [observed: trace stacks].
   - (b) Only **2** of the 3 permitted slabs were ever created in any default-count run. The flush executor kept up, recycling 12–13 slabs per lifetime [observed: `offer` lines]. So B3f's upper bound of 96 MiB was never approached.
   - (c) B1 deadlocked (§3, defect 1) [observed: dump].
   - (d) RSS ran above the pool in D-1 and M32 after the 8 MiB phase [observed].
   - (e) The 17 MiB write met the frame limit (§3, defect 3) [observed].
3. **Matched row — B3g row 1: "Delta plateaus at k × slab, k ≤ MAX_HINT_BUFFERS, and the plateau scales with slab size" → Claim confirmed.**
   - Plateau: the pool's direct memory was 64.23 · 64.22 · 64.17 MiB at the default slab and 128.22 MiB at 64 MiB slabs. Each equals 2 × slab within 0.23 MiB. It did not change from the end of S to the end, or at the peak [observed: `selfcheck.txt`].
   - k ≤ `MAX_HINT_BUFFERS`: k = 2 ≤ 3, and k = 1 ≤ 1 at B1 [observed: `created` lines, each with `max=3` or `max=1`].
   - Scales with the slab: the per-slab step is 1.996× at `max_mutation_size` 32 MiB, and the trace's `size=67108864` confirms the derivation `HintsService.java:110` [observed].
   - B3f bullet 1 ("about 32 MiB after the first hint, between 32 and 96 MiB") holds on both readings. The literal Δ from the pre-write baseline is 32.2 MiB (the one slab a writer created). The pool reading is 64.2 MiB, inside [32, 96] ± B [observed].
   - **R1 row 1** ("`MAX_HINT_BUFFERS=1` delta stays at one slab plus noise, and hint write latency rises") also holds: the pool was 31.89 MiB, one slab. Hint write latency rose without bound: 32 hint writes never returned [observed: dump]. The pre-registered slow-write metric reads **No** (22 completed slow writes, max 7.4 ms, against 80/85 in the D runs), because a write that never ends never writes a `slowhint` line [inferred: the rule fires at `write()` exit]. The dump, not the metric, decides this part.
   - Unit: **B2g row 1** "Accepted sum ≤ C, null at n+1, matches formula" [observed: 115/115].
4. **Excluded rows:**
   - B3g row 2 (grows past k × slab): the peak equals the end at every arm, and pool = slabs × slab ± 0.23 MiB.
   - Row 3 (default vs 4096KiB differ): M4 64.17 MiB is inside [56.22, 72.23] MiB, the same 32 MiB slab.
   - Row 4 (stays at 32 MiB with 32768KiB): 64 MiB slabs.
   - Row 5 (never exceeds 1 slab): 13/12/6 fills.
   - Row 6 (no hints): 200,000.
   - R1 row 2 (B1 equals default): 31.89 vs 64.2 MiB.
   - R1 row 3 (17 MiB accepted): refused in every default-guard arm.
   - Unit rows 2–5: no early or late null, no growth on `allocate` or `recycle`, the over-large hint refused.
5. **Observed vs. inferred.** The conclusion rests on two inferred statements:
   - (i) The `OFF` control's direct delta is the non-hint direct growth of every arm [inferred: same workload, same build, same host; supported by `mss-trace-direct.txt`: every ≥ 1 MiB direct allocation other than `HintsBuffer.create` (BufferPool chunks, the CQL frames of the 8 MiB writes) appears in `OFF` too].
   - (ii) The idle-made first slab belongs to the hint pool's memory [observed: its stack is `HintsBufferPool.createBuffer` and the trace numbers it `n=1`].
6. **Deviations and gaps:**
   - Loopback on one host instead of `pc57` + `pc50` (§2).
   - Sampling every 1 s instead of every 5 s (finer).
   - The 17 MiB arm tests the transport's frame limit, not `max_mutation_size` (§3, defect 3).
   - B1's workload never finished, so its RSS and client latency are not comparable.
   - RSS "about the same" missed in D-1 and M32. At the end of S it was within 25 % in all four lifetimes; the excess appears in the 8 MiB phase. The cause is not traced; heap or netty arena RSS is a candidate, inferred and not checked.
   - Only 2 of 3 slabs were ever needed, so the bound at k = 3 is shown as an upper bound that was not reached; it is not shown binding. At k = 1 the bound binds.
7. **Core question.**
   - Hint direct memory followed the constraint: a 32 MiB slab at the default and at 4 MiB (the floor), a 64 MiB slab at 32 MiB (step 1.996×), one slab at `MAX_HINT_BUFFERS=1` (parts 3, 4).
   - The constraint caps it: 200,000 hints, about 4 × the 3-slab ceiling, left the pool at exactly k × slab and flat. Line 190's true branch closed every full slab (`prev + total > cap`), and the over-large single hint is refused at C/2 (unit) (parts 1, 3).
   - At `MAX_HINT_BUFFERS=1` the cap holds by deadlock: the node stops writing hints and, with them, its mutation stage.

**Conclusion (one line):** unit B2g row 1 — **confirmed**; cluster B3g row 1 (with R1 row 1) — **confirmed**, three sub-predictions missed (RSS in 2 of 4; "writers briefly block" at B1, a permanent deadlock; R2's guard identity).

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` re-parses the raw files only: `harness.out`, `TEST-*.xml`, `samples.csv`, `mss.trace`, the client JSON in `summary.txt`, and B1's dump and tpstats. It takes its own baseline (the last sample before the client's `ms_start`) and its own end. Result (`run1/selfcheck.txt`): **87 ok, 3 fail**. The three failures are exactly the misses above: RSS D-1, RSS M32, and B1's slow-write metric. Its end deltas agree with the run script's to the byte (direct, hints).

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Settings read back in each `summary.txt`; `b_alive` 0 after the baseline in every `samples.csv` (self-check); fills counted from `closed` lines with `prev ≤ cap` (13 · 13 · 12 · 6) |
| 2. Readings | yes | The idle slab's stack re-read in `mss-trace-direct.txt` (`PartiallyFlushBufferPoolTask`); B1's dump re-read (1 in `take()`, 31 waiting to lock); `offer` 0 in B1 |
| 3. Matched row | yes | Pool recomputed independently: 64.23 · 64.22 · 64.17 · 128.22 · 31.89 MiB; ratio 1.996; one slab at B1 |
| 4. Excluded rows | yes | Peak = end per arm (self-check `peak` checks); M4 in the D range; 17 MiB err in D, M4 |
| 5. Observed vs. inferred | yes | (i) checked against `mss-trace-direct.txt` of `OFF-1` and `D-1`: 151,003,683 and 151,003,682 B of non-slab ≥ 1 MiB allocations (also D-2, M32: 151,003,683 B; M4: 16,785,408 B, fewer ≥ 1 MiB allocations, cause not traced; its 8 MiB writes were refused. M4's pool reading is the same as the defaults' within 0.06 MiB, so the difference did not reach `MemoryUsed` at the marks); (ii) stack observed |
| 6. Deviations and gaps | yes | Listed; none changes the matched row |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1's claim "the slab count governs the plateau" holds from the trace and dump. The pre-registered latency metric's NO is recorded as a miss of that metric, not hidden |

### 5.2 Run 2?

**No** (2026-10-20). The conclusion rests on observed readings that agree to the byte with an independent re-parse. The two default runs agree within 0.01 MiB. The only inferred statement (the control subtraction) is supported by the identical non-slab allocation trace. Nothing is refuted and no bypass is claimed. The B1 deadlock is the one result worth repeating: it is a deterministic consequence of `HintsBufferPool.allocate` (`:74-84`: flush after a successful switch), visible in one thread dump, and the case's claim does not depend on it.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive (caveat: a fixed-size slab allocated up front).

**Claim tested:** (B1) A `HintsBuffer` never accepts allocations whose cumulative size exceeds its slab capacity, and the slab capacity equals `max(2 × max_mutation_size, 32 MiB)`. On a real node, hint direct memory equals slabs allocated (at most `MAX_HINT_BUFFERS`) × that slab size, flat in hint volume, moving with `max_mutation_size` only above 16 MiB and with `MAX_HINT_BUFFERS`.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (n = ⌊C/(h+12)⌋ exactly at 1 · 4 · 32 MiB, direct +C per slab, no growth on fill or recycle, `C/2 − 12` the largest hint; 115/115) | caps | run 1 + self-check | 2026-10-20 |
| Cluster | **Confirmed** — B3g row 1 and R1 row 1 (pool = 2 × 32 MiB at the default and at 4 MiB, 2 × 64 MiB at 32 MiB, step 1.996×, 1 × 32 MiB at `MAX_HINT_BUFFERS=1`; flat over 200,000 hints). Missed: RSS within 25 % (D-1, M32); B1 "writers briefly block" (they deadlock); R2's guard identity (the CQL frame limit refuses 17 MiB first) | caps | run 1 + self-check | 2026-10-20 |

**Feedback filed:** the case file's section D updated 2026-10-20, after run 1's readings (not committed). The case file's sha256 is now `9fc9bca6116a207581f01b61f1df48e97dd98fd2ca1241e67228c2a73e7fcce2`; it was `8ecb18b2…` (frozen, verified unchanged before the edit). `git diff` shows only section D changed. No other section amended.
