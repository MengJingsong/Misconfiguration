# internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous — stage-4 results  <!-- file: results/internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous.md; the stem ends in --guided or --autonomous -->
> **Case:** [`internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous`](../../stage3-ai-deep-read/cases/internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous.md)
>
> **Status:** **Closed 2026-10-21 — unit Confirmed (B2g row 1); cluster B3g row 3, partial: the accounted cap (⌊(Q + E)/M⌋·M exact at every value) and the release at `:464` confirmed on the node, the heap-tracking clause refuted for 512 KiB messages (heap flat at ~36–37 MB = `concurrent_writes` × M from C = 16.8 MiB to 160 MiB; the rest of the queue waits off heap in the networking pool).** Effect: caps (accounting and held memory; heap only on the small-message path). No run 2. Audited 2026-10-20 (estimate positive).
> 
> **Outcome class:** undetermined — stage-3 estimate vs the stage-4 effect on the constraint
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
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments: `b63484779685490d51411d3ac753f84f9cd78c29e146076c69d43940b7ddb631` (`sha256sum`, run 2026-10-20 before any harness or run; the new line in `_INDEX.md` §4 is this one). Commit holding the file: `cd7fec5` (the step-0 audit commit on `main`). |
| **Harness** | `harness/internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous/` — written 2026-10-20/21 (step 1), in the repository before run 1; files and checks in its `README.md`. Instrument checks: Byteman `TestScript` of both rule files, no errors (`pc13:~/stage4-logs/rrc/instrument/testscript.txt`); unit shakedown 1 (108 checks, 0 mismatches); cluster shakedowns 1–3 (`RRC_N=4000`; not readings), whose harness fixes are listed in the harness README. Copy on the node `pc13:~/stage4-harness-run/rrc/`; md5 comparison in `results/<stem>/run1/harness-md5.txt`. |
| **Environment deviation (recorded 2026-10-21, before run 1)** | The audit assumed `pc57` + `pc50`, which are no longer available. Nodes A and B run on one host, `pc13` (node3 of `jason92-320876`, 40 cores, 251 GiB), on loopback (A 127.0.0.2, JMX 7102; B 127.0.0.3, JMX 7103), as `internode_max_message_size-inferMessageSize-size--autonomous` did on 2026-10-20. Node data, commit logs and hints are on an 80 GiB tmpfs `/mnt/stage4-rrc` (local RAM; `pc13`'s disk is a spinning RAID volume, and the closed sibling found that several nodes applying every write there stall), wiped after each lifetime. The design is unchanged: A and B are separate JVMs with separate yaml files, and every A→B message crosses a real internode TCP connection. |
| **Harness choices fixed before any reading** | (1) `hinted_handoff_enabled: false` on both nodes: A's sends to B that A drops (overload) or that time out would otherwise be hinted and replayed into B's queue after the load. (2) `memtable_allocation_type: offheap_buffers` on B only: the B3d(2) histogram reads `Mutation` + `[B` for the queued messages, and with the default `heap_buffers` every applied 512 KiB value stays in B's memtable as a `[B` (up to the 512 MiB memtable space), which would swamp the queued messages; the memtable's sizes are still sampled (`AllMemtablesOnHeapDataSize`/`OffHeapDataSize`). (3) The keyspace uses the `SimpleSnitch`'s data centre, `datacenter1: 2` (B3e's `dc1:2` would place no replica). (4) The histogram cadence: from 2 s after the load reaches B, every 10 s through the drain (B3d's 30 s gives at most one sample inside the ~25 s stress). (5) Reading rules for B3f's wording (M, ceiling band, retained, near zero, drained) are in `cluster-run.py`'s docstring; they do not change a B2f/B3f number. |
| **Tiers and values** | Unit (B2): `AbstractMessageHandler` acquire/release script with Q = 1024 · 4096 B and reserves 2048 · 8192 B, boundary cases, a concurrent release, a mutation that must fail (R1). Cluster (B3): B receives from A, Byteman 200 ms stall, 512 KiB blobs, Q = 64 KiB · 4 MiB (default) · 32 MiB, reserves 16 MiB (set 1) and default 128/512 MiB (set 2). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-20 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1/A2: accounted wire bytes of inbound messages (a proxy for heap); the heap proxy gap is named. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b Q = 1024 · 4096 B and the yaml default check (4 MiB); B3b Q = 64 KiB · 4 MiB (default) · 32 MiB. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B3d class histogram of `Mutation`/`byte[]` after `GC.run`, `jstat`, native memory; `queueSize` is not exposed by any metric (named) and is traced with Byteman. |
| A. Core question | usage driven to the limit and past it | Partly | The offered window was reasoned for a closed loop; at CL=ONE the backlog is bounded by the send queues and B's limits. **Amended** (R4). |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps each state their reading. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | B3f used 3 × Q (and 2 types); 512 KiB messages use only the large connection, so the allowance term is 1 × Q. **Corrected** (R2). B2f worked sequence checked by hand (176 borrowed, refusal on the third acquire, release 176 then 0). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g cover invariants, overshoot, leak, over-release, insensitive test, limit never reached, OOM. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Confirmed needs the invariant at every unit step and, on a node, a rise with Q plus falling `ThrottledCount` (the proof that the cap bound). |
| B. Logic | alternative explanations and their controls | Partly | The `>` → `>=` mutation is equivalent for the reserve counts, so the sensitivity control could not fail. **Replaced** (R1). B3h has the Byteman-off, reserve-lowering, small-message and repeat controls. |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | A1-A3 and B1 state the mechanism and the claim. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Met | Runnable from B2/B3 plus the amendment block. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Message expiry (2 s) would have capped the backlog; `write_request_timeout` was not set. **Amended** (R3). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | The closed sibling `harness/internode_application_receive_queue_capacity-acquireCapacity-queueCapacity--guided/` already has `hold-handler.btm`, `sample-inbound.py`, `Jmx.java`, `make-node-yaml.sh`, `write-load.py`, `unit-run.sh` to reuse; Byteman and `cassandra-stress` are in the build. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly | Backlog and disk arithmetic corrected (R4): up to about 20 GiB per node per run against 47 GB free; 6 runs of about 12 min. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked: `AbstractMessageHandler.java:461-474`, `InternodeInboundMetrics.java:53,67-68`, `OutboundConnections.java:68-69`, `InboundMessageHandler.java:128-138`, `ResourceLimits.java:159-169`. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Replace the `>=` mutation by a clamp/guard-removing mutation that must fail | Applied 2026-10-20 (B2e, B2g row 5, amendment block) | `>=` releases `min(0, bytes)` = 0, an equivalent mutant |
| R2 | Prediction ceilings use Q + reserve (large connection only): 16.1 · 20 · 48 MiB for set 1 | Applied 2026-10-20 (B3f, amendment block) | every 512 KiB message exceeds the 64 KiB threshold |
| R3 | `write_request_timeout: 60000ms` on both nodes | Applied 2026-10-20 (B3a, amendment block) | expired inbound messages are skipped before capacity, capping the backlog at the 2 s default |
| R4 | State the CL=ONE open-loop backlog and the disk plan (up to about 20 GiB per node, delete after each run) | Applied 2026-10-20 (B3c, B4, amendment block) | the 200 client threads do not bound the backlog |
| R5 | Reuse the closed sibling's harness (Byteman hold, inbound sampler, node-yaml maker) | step 1 (harness) | prerequisite, not a design change |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's runbook observables:

| Observable | Must match | Tolerance |
|---|---|---|
| — | — | not filled: no run 2 (§5.2) |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-20 22:26–22:54 MDT (2026-10-21 04:26–04:54 UTC): unit 22:26–22:28, cluster 22:28–22:54; self-check 2026-10-21 | not done |
| Node (CloudLab name and type) | `pc13` = `node3.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB), driven over SSH from `pc07`; nodes A (127.0.0.2, JMX 7102) and B (127.0.0.3, JMX 7103) on loopback on this one host (environment deviation, §1) | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | — |
| JDK (`java -version`) | OpenJDK 11.0.32.1; G1, `-Xms2G -Xmx2G` on both nodes (`MAX_HEAP_SIZE=2G`); NMT summary on B | — |
| Ant (`ant -version`) | 1.10.12 | — |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54`), built; the R1 mutants in a fresh clone `~/cassandra-rrc-mut` at the same commit (`ant build-test`), removed after | — |
| Case-file commit / harness commit | case file `cd7fec5` (sha256 `b6348477…` verified unchanged before run 1); harness not committed (md5 of every file, repo = node, in `run1/harness-md5.txt`) | — |
| Storage for node data | 80 GiB tmpfs `/mnt/stage4-rrc` on `pc13`'s RAM (data, commit logs, hints, caches), wiped after every lifetime, unmounted after the run; node logs and conf in `pc13:~/stage4-rrc/{A,B}/` | — |
| Full logs (path, outside the repo) | `pc13:~/stage4-logs/rrc/run1/` (`unit/`; `cluster/<label>/` with `rrc.trace`, `jmx-B.csv`, `vt-in.csv`, `vt-out.csv`, `jstat-B.txt`, `samples/` (histograms, NMT, tpstats, thread dumps, `ss`), `stress.log`, both nodes' `system.log`/`debug.log`; 99 MB in all), `pc13:~/stage4-logs/rrc/run1-chain.log`; shakedowns in `pc13:~/stage4-logs/rrc/shakedown{1,2,3}/` | — |

## 3. Runbook defects

Every step a run could not execute as written. The run stops at the
defect; the fix is made in the case file (dated) if it leaves §9a unchanged,
and the affected tier restarts from its beginning. If the fix would change
§9a, the case goes back to the audit. "None" if there were none.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | shakedown 2 (before run 1) | B3a / amendment R3 | R3 sets `write_request_timeout: 60000ms` so that inbound messages do not expire, but the coordinator stamps a `MUTATION_REQ`'s expiry with the nearer of the verb timeout and the client deadline `native_transport_timeout` (12 s default; `Dispatcher.java:238-244`, `Message.java:222-233`): in the 1 KiB control 3,048 of 5,187 messages expired at B within 20 s | `native_transport_timeout: 60000ms` on both nodes (harness `make-node-yaml.sh`); R3's intent and every B3f/B3g number unchanged | fixed in the harness 2026-10-21, before run 1; recorded in the case file's section D after run 1 (the case file is frozen until then) | none (section D only) |
| 2 | harness writing (before run 1) | B3e step 3 | `NetworkTopologyStrategy` with `dc1: 2` under B3a's `SimpleSnitch` (whose data centre is `datacenter1`) places no replica | `datacenter1: 2` (`client.py`, `big.yaml`, `small.yaml`) | harness 2026-10-21, before any reading; section D | none (section D only) |

Run 1 itself ran every step as written (no defect, no restart). Shakedowns 1–3 (`RRC_N=4000`, not readings) found harness
defects only, fixed before run 1 and listed in the harness README (`Jmx poll` field count, thread-dump timing and thread
name, the OOM pattern, histogram cadence, `Jmx` recompilation).

## 4. Run 1

**Scope:** unit tier (B2) complete; cluster tier (B3) complete: set 1 at Q = 64 KiB · 4 MiB (default, 3 runs) · 32 MiB,
set 2 at the same three Q, controls B3h(a) (no hold, at 64 KiB and 32 MiB), (b), (c), (d) — 12 lifetimes, each
`cassandra-stress` n = 20,000 (+ its 5,000-write warm-up) of 512 KiB (1 KiB for (c)) at CL ONE through A.
**Command log:** `[stem]/run1/chain-excerpt.log`, `run1-chain.sh`; per lifetime `run1/cluster/<label>/summary.txt`.

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, `run1/unit/harness.out`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Upstream `ResourceLimitsTest` | 5/5 pass | `unit/summary.txt` |
| B2f script at Q 1024 / R 2048: outcomes, (q, E) after each step | `SUCCESS, SUCCESS, INSUFFICIENT_GLOBAL`; `600/0, 1200/176, 1200/176, 600/0, 0/0` — as B2f | `unit/harness.out` |
| Invariant `E = G = max(0, q − Q)` and `q − Q ≤ R` after every step, Q 1024/4096 × R 2048/8192 | 23 of 23 steps; final (0, 0, 0) in all four cells; e.g. 1024/8192: `3200/2176, 2600/1576, 2000/976, 0/0` | `unit/harness.out` |
| Q = 4096 (control B2h): reserve use | 0 throughout at R 2048 and 8192 | `unit/harness.out` |
| Boundary: release at old = Q (another handler holds 100 B) | reserves stay 100/100: 0 released | `unit/harness.out` |
| Boundary: old = Q + 1, bytes 5 | 101 → 100: exactly 1 released | `unit/harness.out` |
| `throttledCount`: outer (5-argument) refusal / inner (3-argument) refusal | +1 / +0; state unchanged (1200, 176, 176) | `unit/harness.out` |
| Concurrent: 1 acquirer + 4 releasers, 100,000 messages, ×5 | (0, 0, 0) and no exception in all 5; 25,427–48,885 refusals retried; reserve max 2,048 = R | `unit/harness.out` |
| Reactivation (beyond B2f) | release at old > Q wakes the waiter (retry `SUCCESS`, q 2600, E = G = 1576 = q − Q); release at old = Q wakes nobody | `unit/harness.out` |
| Yaml level: default / 8 MiB in its own JVM | 4,194,304 / 8,388,608 | `unit/harness.out` |
| Sensitivity (R1): M1 release `bytes` not `excess` | fails: 16 mismatches, `UnrecoverableIllegalStateException` (`using=-178`), boundary 101 → 96 | `unit/mutant-M1.out`, `.diff` |
| Sensitivity (R1): M2 guard removed | fails: 11 mismatches, `AssertionError` (`release` of a negative amount) | `unit/mutant-M2.out`, `.diff` |
| The filed `>=` mutant (M0, recorded for R1 only) | passes all 108 checks: an equivalent mutant, as the audit said | `unit/mutant-M0.out` |
| All checks | 109 checks, 0 mismatches | `unit/summary.txt` |

**Cluster tier** — M = 524,350 B (median; 524,350–524,351) for the 512 KiB writes, 1,084 B for the 1 KiB ones. C = Q + E
(R2). "Retained" = live `Mutation` + `[B` bytes above the idle histogram (after `GC.run`), peak over the 3 histograms
inside the loaded window (6 for (c)). "Pool" = networking `BufferPool` `UsedSize` above idle, max. Files: `run1/cluster/<label>/summary.txt`, `readings.json`, `histo-excerpt.txt`, `jmx-B.csv`.

| Capacity value | Run | Data-handler peak q (= n·M) | C = Q + E; n | Refusals (all one kind) / `ThrottledCount` Δ, rate | Retained peak (k = /C) | Live `Mutation` above idle | Pool above idle | B received / A overloaded |
|---|---|---|---|---|---|---|---|---|
| Q 64 KiB, set 1 | B (held) | 16,779,232 (32 M) | 16,842,752; 32 | 1,900 `INSUFFICIENT_GLOBAL` / 1,900, 61.3/s | 36,410,808 (2.16) | 31, 30, 31 | 0.90 MB | 3,677 / 21,416 |
| Q 4 MiB (default), set 1 | B ×3 (B3h(d)) | 20,449,689 (39 M) all three | 20,971,520; 39 | 1,892 · 1,889 · 1,711 / same, 63.1 · 63.0 · 57.0/s | 36,433,424 · 36,946,536 · 37,536,176 (1.74–1.79) | 31–32 | 5.89 · 5.82 · 5.82 MB | ~3,700 / ~21,400 |
| Q 32 MiB, set 1 | B | 49,813,345 (95 M) | 50,331,648; 95 | 1,344 `INSUFFICIENT_GLOBAL` / 1,344, 43.4/s | 37,013,392 (0.735) | 31, 31, 32 | 50.77 MB | 3,901 / 21,190 |
| Q 64 KiB, set 2 (128/512 MiB) | B | 134,233,856 (256 M) | 134,283,264; 256 | 1,326 `INSUFFICIENT_ENDPOINT` / 1,326, 39.0/s | 36,422,272 (0.27) | 32 | 174.0 MB | 4,476 / 20,624 |
| Q 4 MiB, set 2 | B | 137,904,313 (263 M) | 138,412,032; 263 | 1,076 `INSUFFICIENT_ENDPOINT` / 1,076, 31.6/s | 37,537,952 (0.27) | 32 | 175.4 MB | 4,443 / 20,656 |
| Q 32 MiB, set 2 | B | 167,267,969 (319 M) | 167,772,160; 319 | 915 `INSUFFICIENT_ENDPOINT` / 915, 26.1/s | 37,008,528 (0.22) | 31–32 | 217.4 MB | 4,633 / 20,470 |
| Q 64 KiB, set 1 | B3h(a) no hold | 16,779,232 (32 M) | as above | 5 / 5, 0.2/s | 5,663,608 | 0–2 | 4.12 MB | 22,367 / 2,721 |
| Q 32 MiB, set 1 | B3h(a) no hold | 32,509,700 (62 M) | as above | 0 / 0 | 6,782,488 | 0–2 | 1.26 MB | 22,805 / 2,285 |
| Q 64 KiB, reserves 4 MiB, max message 2 MiB | B3h(b) | 4,194,808 (8 M) | 4,259,840; 8 | 760 `INSUFFICIENT_GLOBAL` / 760, 20.5/s | 11,171,720 (2.62) | 8, 8, 8 | 0.80 MB | 1,285 / 23,826 |
| Q 4 MiB, set 1, 1 KiB writes | B3h(c) | 20,971,520 (= C exactly, 19,346 M) | 20,971,520; 19,346 | 2,060 `INSUFFICIENT_GLOBAL` / 2,060, 30.7/s | 45,498,992 (2.17) | up to 19,341 | 0.13 MB | 25,200 / 0; 15,496 expired at B (backlog ≈ 120 s > 60 s) |

Every lifetime, all on the trace and the virtual table: the read-back (first `acq` line: `cap`, endpoint and global
limits) equalled the label; the hold fired in every held lifetime (32 workers asleep in `doVerb`, 8 in (b), 29–31 at
32 MiB); **the target line on the node**: every release with `old > cap` released exactly `min(old − cap, b)` to the
reserves (summed per handler, e.g. 3,584 releases, 1,879,205,961 B at 64 KiB), no release with `old ≤ cap` released
anything, 0 violations in 12 lifetimes; every `SUCCESS` had `q ≤ cap + E`; after each drain A's `using_bytes` and
`using_reserve_bytes` were 0 and live `Mutation`s back to idle (−1…0); no `OutOfMemoryError`, no
`UnrecoverableIllegalStateException`, no GC warning on either node; no message expired except in (c). Cross-run
(`run1/cluster/analysis.txt`, `analyze/summary.txt`): noise (range of the 3 repeats) retained 1,102,752 B, peak q 0,
rate 6.0/s; set-1 retained 36.41 → 36.97 (mean) → 37.01 MB, Δ(32 MiB − 64 KiB) = 0.60 MB < 2 × noise = 2.21 MB.

### 4.2 Conclusion and logic

1. **Validity.** Valid. The limit was reached in every held lifetime (refusals and `ThrottledCount` > 0)
   [observed: `cluster/<label>/summary.txt`]; the knobs reached the handler (read-back) [observed: same]; the hold
   fired [observed: thread dumps, `hold` lines]; held fixed: heap 2 GiB on both, `concurrent_writes` 32, timeouts 60 s,
   A's raised send limits, hints off, B's `offheap_buffers` (§1) [observed: `B-yaml-tail.txt`; the A lines in each
   summary]. Unit tier: every check ran, the sensitivity mutants fail [observed: `unit/summary.txt`].
2. **Readings.** Nothing contradicts another. Unusual: (i) the retained heap is the same, about 36.4–37.5 MB, in every
   held 512 KiB lifetime whatever C is (16.8 MiB to 160 MiB) [observed: §4.1]; (ii) the networking pool holds what the
   heap does not: above idle 0.9 / 5.9 / 50.8 MB for (n − 32)·M = 0 / 3.7 / 33.0 MB in set 1, 174–217 MB in set 2
   [observed: `jmx-B.csv`]; [inferred: the queued large messages beyond the 32 a `MutationStage` worker is running
   wait as frames from the networking pool and are deserialized only on the stage thread, `InboundMessageHandler.java:358-384`, `:481-510`
   and the closed sibling's §1.1 finding 2; the pool's ratio to (n − 32)·M (1.54 at 32 MiB) matches the sibling's 1.47];
   (iii) set 2's refusals are `INSUFFICIENT_ENDPOINT` (the endpoint reserve, 128 MiB, binds before the 512 MiB global)
   [observed]; (iv) A dropped about 85 % of its sends to B as overload in the held runs [observed: `vt-out` deltas] —
   the open loop R4 described, which keeps B at its ceiling for the whole stress.
3. **Matched row.** Unit: B2g row 1, "Invariant holds at every step, final state (0,0) → Claim holds at the
   accounting level: release at 464 mirrors acquire": 23/23 steps, all finals (0, 0, 0), boundary 0 and 1 released,
   5/5 concurrent runs (0, 0) [observed: `unit/harness.out`]. Cluster: B3g row 3, "Peak retained heap flat across Q
   though `ThrottledCount` > 0": retained 36.41 / 36.97 / 37.01 MB at 64 KiB / 4 MiB / 32 MiB, Δ 0.60 MB < 2 × noise,
   with 1,900 / 1,711–1,892 / 1,344 throttles [observed: §4.1, `analysis.txt`]. The row's stated meaning ("Q does not
   matter once reserves dominate; only reserve binds") is **not** what the readings show: Q binds the accounted bytes
   exactly (32 → 39 → 95 messages, n·M = ⌊C/M⌋·M to the byte) [observed]; the heap is flat because only the
   `concurrent_writes` = 32 running messages are deserialized on the heap [observed: 30–32 live `Mutation`s in every
   held large lifetime, 8 in (b)] and the rest are off-heap frames [inferred, part 2 (ii)]. So the matched row is row 3
   with a corrected meaning: "partial: refines the claim".
4. **Excluded rows.** Unit: rows 2–6 — no admitted state with `q − Q > R` (28 checks), reserves 0 after every drain, no
   negative reserve or exception in the real code, the guard mutants M1/M2 change the result (row 5 not met), Q = 4096
   borrows nothing [observed: `unit/`]. Cluster: row 1 (heap rises with Q and `ThrottledCount` falls) — the heap does not
   rise (above); row 2 (far above (Q + reserve) × 3) — 36.4 MB at 64 KiB against 48.3 MB, k ≤ 2.62 in every lifetime;
   row 4 (`ThrottledCount` 0 in all runs) — 760–2,060 in every held lifetime; row 5 (no return to baseline) — live
   `Mutation`s back to idle, reserves 0; row 6 (OOM or GC pressure) — none, heap max 1.36 GB of 2 GB [observed: §4.1,
   `readings.json`].
5. **Observed vs. inferred.** The conclusion rests on observed readings, except: (a) that the pool's rise is the
   queued large messages' frames (code path and the sibling's identical finding; the pool rises with (n − 32)·M in
   every lifetime and falls to idle after the drain); (b) that the extra ~20 MB of `[B` beyond 32 × 512 KiB in the
   held large lifetimes (36.4 MB vs 16.8 MB) is per-message deserialization state of the 32 running mutations — it
   is the same at every C and is 2.8 MB after the drain, but it was not attributed by class or allocation site.
   Neither changes the matched row: the heap reading is flat whichever classes it is made of.
6. **Deviations and gaps.** Loopback on one host (§1, environment); tmpfs storage; `offheap_buffers` on B (§1: the
   default `heap_buffers` would put every applied 512 KiB value into B's heap, so the deviation makes the queued
   messages' share visible, it does not create the flat reading — the flat part is the 32 running messages);
   histogram every 10 s (3 samples per lifetime) instead of 30 s; stress lasted ~30 s per lifetime (n = 20,000 as
   R4 kept it), not 10 min; B3h(a) run at two Q, not three. `ss -tmi` and NMT were taken (`samples/`) but not used.
7. **Core question.** The constraint caps what it accounts: the bytes of admitted-but-unreleased inbound messages from A
   stop at exactly ⌊(Q + E)/M⌋·M at every Q and both reserve sets, the release at `:464` hands back exactly the part
   above Q on the node and in the unit tier, and everything returns to 0 (parts 3, 4). Usage follows Q only partly: the
   memory the queue holds (heap + networking pool: 37 / 43 / 88 MB in set 1) rises with Q, but **the heap does not** for
   512 KiB messages — it stays at `concurrent_writes` × M plus overhead (~36–37 MB) from Q = 64 KiB to C = 160 MiB,
   because queued large messages wait off heap; the heap follows the limit only when the ceiling holds fewer messages
   than `concurrent_writes` (B3h(b): 8 messages, 11.2 MB) or for small messages, which are deserialized before they
   queue (B3h(c): 19,341 live `Mutation`s, 45.5 MB = 2.17 × C) (parts 2, 3).

**Conclusion (one line):** unit B2g row 1 — confirmed; cluster B3g row 3 (heap flat across Q while `ThrottledCount` > 0)
— the claim confirmed for the accounting and the release at `:464`, refuted for its heap-tracking clause on the
512 KiB (large-message) path; refines the claim.

**Sub-predictions of B3f / B3h** — met: R2's ceilings (all six values and (b), inside (C − M, C]); `ThrottledCount` > 0
at every set-1 Q; "not much greater than 16 MiB × 3" at 64 KiB (36.4 MB); k in 1.2–3 at 64 KiB (2.16) and 4 MiB (1.74–1.79);
B3h(b) "drops proportionally" (retained ratio 0.307 vs ceiling ratio 0.253). **Missed:** k at 32 MiB (0.735); "retained
scales with these totals" / does change from 64 KiB to 32 MiB (the claim-wrong clause of B3f is met: Δ 0.60 MB < 2 × noise);
"`ThrottledCount` rate should fall as Q rises" (61.3 → 61.0 → 43.4/s: falls overall by more than 2 × noise, not
between 64 KiB and 4 MiB); set 2 at 4 MiB "throttling near zero" (1,076 refusals: the open loop of R4 fills any
ceiling) and "peak queued heap about 100 MiB × k" (37.5 MB); B3h(a) "queued bytes near zero regardless of Q" without the
hold (B still reached its ceiling at 64 KiB, 62 messages at 32 MiB; throttles 5 and 0 against 1,900 and 1,344);
B3h(c) "small messages do not hit the limits" (they reached C exactly, 2,060 refusals).

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` re-parses the raw files on `pc13` with its own code (whole-trace parse, the `:464` rule as per-handler
sums rather than line pairing, the window from `session.log`'s own timestamps, the histograms' text) and compares with
the run script's `readings.json`: **102 checks, 0 failed** (`run1/selfcheck.out`). Its first pass reported 3 failures
that were the self-check's own mistakes (`run1/selfcheck-pass1.out`): it expected 20 script steps (there are 23; it also
caught the reactivation check's `.inv`) and read the cross-run verdicts from `analysis.txt`, where `analyze` does not
write its EXPECTED lines (they are in `cluster/analyze/summary.txt`); fixed in the self-check only, then 102/102.

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | read-back, hold lines and held workers re-counted from the trace and the dumps in every held lifetime; refusals and `ThrottledCount` re-derived (equal to the run's, Δ 0) |
| 2. Readings | yes | every §4.1 figure re-derived: M, peak q, refusals and kind, retained per histogram, live `Mutation`s, drained state; the self-check's throttle rate uses a 1-s window from `session.log` (61.0 · 60.9 · 55.2/s for the repeats against the run's 63.1 · 63.0 · 57.0) — same relations |
| 3. Matched row | yes | flat retained heap (36.41 / 36.97 / 37.01 MB, Δ 0.60 MB vs 2 × noise 2.21 MB) with throttles > 0 recomputed; the ceiling n·M exact at every value; the row's meaning corrected from the readings, not assumed |
| 4. Excluded rows | yes | row 1 (no rise), row 2 (k ≤ 2.62), row 4 (throttles > 0), row 5 (drain to idle, reserves 0), row 6 (no OOM/GC warning) re-checked; unit rows 2–6 from `harness.out` and the mutant logs |
| 5. Observed vs. inferred | yes | the two inferred statements (pool = queued frames; the ~20 MB extra `[B`) are named; the matched row does not depend on them |
| 6. Deviations and gaps | yes | loopback, tmpfs, `offheap_buffers`, cadence, short stress and two-Q B3h(a) recorded; none reverses a reading |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1's three falsifiers checked in order: accounted bytes never exceeded the limits (0 violations); reserves returned to 0; real heap did not respond to Q for 512 KiB messages (B3f's own claim-wrong clause), did respond to the reserve in (b) and for 1 KiB messages in (c) |

### 5.2 Run 2?

**No** — decided 2026-10-21. The conclusion rests on observed readings (§4.2 part 5); every part of §5.1 holds from
run 1's raw files; the partial refutation is robust inside run 1 (the flat heap holds across 9 held 512 KiB lifetimes
covering C from 16.8 MiB to 160 MiB, with a 3-run noise estimate) and was observed independently in the closed sibling
(`acquireCapacity--guided`, another session and harness: live `Mutation`s `min(n, 32)` in its large arms, the rest in
the pool). A run 2 would repeat what run 1 already repeated.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its
date and reason.

**Stage-3 estimate:** positive (the case file's Estimate line).

**Claim tested:** (B1) "For inbound internode traffic from one peer, the bytes held in admitted-but-unreleased messages
never exceed `queueCapacity` (per connection) plus what the endpoint/global reserves grant, with the release at line 464
returning exactly the above-allowance part to the reserves; and, on a real node, the heap actually retained by queued
inbound messages tracks this accounted total (so shrinking the three limits shrinks the backlog heap, growing them grows
it) rather than being bounded elsewhere."
"Confirmed" below always means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1: the invariant `E = G = max(0, q − Q)` at every step, the B2f sequence exact, `>` boundary (0 at old = Q, 1 at Q + 1), (0, 0) after 5 × 100,000 concurrent messages; the guard/clamp mutants fail, the filed `>=` mutant is equivalent (R1) | caps (the accounting) | run 1 + self-check | 2026-10-21 |
| Cluster | **B3g row 3 — partial: refines the claim** (not Confirmed as filed). Accounting and `:464` confirmed: plateau ⌊(Q + E)/M⌋·M = 32 · 39 · 95 messages (set 1) and 256 · 263 · 319 (set 2), every above-Q release exact, reserves back to 0. Heap-tracking clause refuted for 512 KiB messages: retained heap 36.4 / 37.0 / 37.0 MB at Q 64 KiB / 4 MiB / 32 MiB (Δ 0.60 MB < 2 × noise) and the same in set 2; the queued messages beyond `concurrent_writes` wait off heap (networking pool 0.9 → 50.8 MB, set 2 174–217 MB). The heap follows the limit for small messages (B3h(c): 2.17 × C) and when C < 32 messages (B3h(b)) | caps — the accounted bytes exactly and the held memory (heap + networking pool) with Q; the **heap** only on the small-message path (on the large path it stays at about `concurrent_writes` × M whatever Q is) | run 1 + self-check | 2026-10-21 |

**Feedback filed:** the case file's section D "Stage-4 feedback" updated 2026-10-21 (not committed): the verdicts, the
corrected meaning of B3g row 3, the missed sub-predictions, runbook defects 1–2 and the stage-3 notes; no other section
amended (the file was frozen; the refutation is of the heap clause only and is recorded in D). The case file's sha256 was `b63484779685490d51411d3ac753f84f9cd78c29e146076c69d43940b7ddb631` (verified unchanged) until run 1's readings were taken; after the section-D edit it is `dd512ec51def6f1eaa85e37cc37e5383a6bfd4c9741763b32d7a37f445ea08da` (only section D differs from commit `cd7fec5`).
