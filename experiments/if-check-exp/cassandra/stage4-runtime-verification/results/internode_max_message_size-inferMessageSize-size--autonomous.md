# internode_max_message_size-inferMessageSize-size--autonomous — stage-4 results  <!-- file: results/internode_max_message_size-inferMessageSize-size--autonomous.md; the stem ends in --guided or --autonomous -->
> **Case:** [`internode_max_message_size-inferMessageSize-size--autonomous`](../../stage3-ai-deep-read/cases/internode_max_message_size-inferMessageSize-size--autonomous.md)
>
> **Status:** Closed — verdict filed 2026-10-20: unit Confirmed; cluster Confirmed (R2: the receiver rejects at `inferMessageSize` and holds nothing that scales with the message; R3: the sender rejects at `enqueue`); effect: caps (one message's wire size, both sides); no run 2
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
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments: `46d2788e90644e4835d69e728ec6cac99769453d7dbf0f6f30ccfaca2e5eb437` (`sha256sum`, run 2026-10-20 before any harness or run; the new line in `_INDEX.md` §4 is this one). Commit holding the file: `cd7fec5` (the step-0 audit commit on `main`). |
| **Harness** | `harness/internode_max_message_size-inferMessageSize-size--autonomous/` (README there), written 2026-10-20 in step 1: `InferMessageSizeLimitTest.java` + `unit-run.sh` (unit); `make-node-yaml.sh`, `client.py`, `Jmx.java`, `cluster-run.py` (cluster). md5 of every file in `run1/harness-md5.txt`. Checked by a shakedown before run 1 (`~/stage4-logs/imm/shakedown*`: unit 36/36 checks at both heaps beside upstream `MessageTest` 9/9; cluster R2, R1, R3 with 3 writes per size, 7/7 · 5/6 · 7/7 expected lines, the R1 miss being the count step's own read reply — defect 1 in §3). |
| **Tiers and values** | Unit (B2): `Message.serializer.inferMessageSize` with L = 64 KiB · 1 MiB · 16 MiB, the exact boundary and a truncated payload. Cluster (B3): two nodes, RF=2, runs R1 (16/16 MiB), R2 (16/1 MiB), R3 (1/1 MiB) and R0 (default/default, added R1), blobs 512 KiB · 4 MiB · 12 MiB at CL=ALL. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-20 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1/A2: direct and heap memory pinned by one message on the receiver. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly | Unit 64 KiB · 1 MiB · 16 MiB; cluster 16 · 1 MiB; the 128 MiB default is not among the values. **Amended** (R1): run R0. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B3d reads direct pool, RSS and inbound counters, not the networking pool. **Amended** (R2). |
| A. Core question | usage driven to the limit and past it | Met | 12 MiB blobs against a 1 MiB limit (R2, R3); 20 × 12 MiB = 240 MiB offered, above the 4 MiB per-link capacity. |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps each state their reading. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f exact; B3f: B's peak increment in R2 ≤ 1/3 of R1's and flat in S. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g cover holds, refuted (accepted / buffered), retry amplification, instrument blind. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Needs the exceeds-max log line, the failed writes, no row on B and a small flat memory increment against R1. |
| B. Logic | alternative explanations and their controls | Met | B3h: R1 as control, 512 KiB in every run, repeats, tpstats to exclude timeouts. |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | A1-A3 and B1 state claim and bypasses. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Met | Runnable from B2/B3 plus the amendment block. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met | Values, sizes, counts, sampling and cleanup are exact. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | Two-node setup exists; the probe, the writer and the CSV sampler are step-1 work; hints off (R3). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 240 MiB per size against 4 MiB links; disk under 5 GiB per node; 1 GiB heap + 1 GiB direct per node. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked: `Message.java:777` (signature), `OutboundConnection.java:329-332`, `InternodeInboundMetrics.java:53,67-68`, `DatabaseDescriptor.java:990-996`, `InboundMessageHandler.java:128-138`. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Add run R0 at the default beside R1–R3 | Applied 2026-10-20 (B3b, amendment block) | the default is among the values |
| R2 | Also read the networking pool `Size`/`UsedSize` on node B | Applied 2026-10-20 (B3d, amendment block) | receive-side large messages accumulate there; `MemoryUsed` can miss a short hold |
| R3 | `hinted_handoff_enabled: false` on both nodes | Applied 2026-10-20 (B3a, amendment block) | a failed replica write would otherwise add hints |
| R4 | Keep `native_transport_max_message_size` at the derived default (16 MiB); raising to 32 MiB would fail at startup | Applied 2026-10-20 (B3a, amendment block) | it may not exceed the per-ip limit (about 25 MiB at 1 GiB heap) |
| R5 | Write the probe, the writer and the sampler; share the cluster harness with the `enqueue` file | Done 2026-10-20 in step 1 (harness folder above; the `enqueue` file can reuse `make-node-yaml.sh`, `client.py`, `Jmx.java` and the sampler of `cluster-run.py`) | prerequisites, not design changes |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's runbook observables:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-20, 18:25–18:52 EDT (unit 18:25–18:27, cluster 18:27–18:52) | not done |
| Node (CloudLab name and type) | `pc57` (`node0.jason92-319347.misconfiguration-pg0.cloudlab.umass.edu`), 32 cores, 251 GiB; both nodes of the cluster tier on this host on loopback (A = 127.0.0.1, B = 127.0.0.2), as B3a allows | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 (2026-08-18) | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local `cassandra-src` clone commit | `~/cassandra-run5`, fresh clone of the shared clone at `cassandra-5.0.9` (`b5f2a54210d541339c2e7c17a794195cac0e67c2`), `ant build-test` 1 min 39 s; `git status` clean after the run (the test file is copied in and removed by `unit-run.sh`) | |
| Case-file commit / harness commit | case file as frozen in §1 (`46d2788e…`, commit `cd7fec5`); harness not committed (md5 in `run1/harness-md5.txt`: `InferMessageSizeLimitTest.java` `93769ee8…`, `cluster-run.py` `81ecbb4c…`, `client.py` `0b3afdc5…`, `make-node-yaml.sh` `485d25fd…`, `Jmx.java` `2f18ec53…`, `unit-run.sh` `af69aead…`) | |
| Storage for node data | local disk `/dev/sda3` (ext3, 46 GB free before the run), `~/stage4-imm/{A,B}/`, wiped at the start of every lifetime | |
| Full logs (path, outside the repo) | `pc57:~/stage4-logs/imm/run1/` (6 MB: `unit/`, `cluster/<label>-<rep>/` with both `system.log`s, `run-all.log`); excerpts in `internode_max_message_size-inferMessageSize-size--autonomous/run1/` next to this file | |

## 3. Runbook defects

Both were found in the harness shakedown, before run 1; run 1 used the fixes, so no tier was restarted. Neither changes
B1, B2f/B2g or B3f/B3g.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | shakedown | B3d (6), B3e step 6: `select count(*)` at ONE through each node | The unpaged count's replica reply is one internode message holding every row the replica sends, so it hits `internode_max_message_size` itself: in shakedown R2 B refused to send A a 1,572,958-byte reply (three 512 KiB rows; `OutboundConnection.enqueue`, B's limit 1 MiB) and in shakedown R1 B refused a 51,904,758-byte reply (16 MiB limit), so the count through A failed. Also, a count at ONE says nothing about which node's rows were counted (shakedown R3: 3 through A although A holds 9). | Count with one row per page (`fetch_size=1`), so a reply holds one row; per-node row counts read from `nodetool tablestats` "Local write count" and from B's `Table WriteLatency` count before and after each size (exact per node). The log lines are read before the counts and the counts' own lines reported apart. | AI, 2026-10-20 | amendment "Runbook fix (stage 4, 2026-10-20)" at the end of the case file's B section; not committed |
| 2 | shakedown | B2h: "L set to Integer.MAX_VALUE" | `DatabaseDescriptor.setInternodeMaxMessageSizeInBytes(Integer.MAX_VALUE)` throws `IllegalArgumentException: Invalid data storage: 2147483647 bytes. It shouldn't be more than 2147483646` (`DataStorageSpec.java:111`); the B2h alternative, 128 MiB, would not pass the 8 × 16 MiB message. | The control uses `Integer.MAX_VALUE − 1`, the largest settable value. | AI, 2026-10-20 | same amendment |

## 4. Run 1

**Scope:** unit tier (B2) at *L* = 64 KiB · 1 MiB · 16 MiB plus the controls, at the default test heap (1 GiB) and at
2 GiB; cluster tier (B3) runs R0 (default/default), R1 (16/16 MiB), R2 (16 MiB on A / 1 MiB on B), R3 (1/1 MiB), each
twice (B3h), *S* = 512 KiB · 4 MiB · 12 MiB, 20 writes each at CL ALL through A. **Command log:**
`internode_max_message_size-inferMessageSize-size--autonomous/run1/` (`run-all.sh`, `run-all.log`; per lifetime
`cluster/<label>-<rep>/summary.txt`; the full `session.log` of every command is on the node).

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, `xmx1g.out`, `xmx2g.out`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Upstream `MessageTest` (its `testInferMessageSize` is the instrument's known-answer test) | 9/9 pass | `unit/summary.txt` |
| *L* − 1 KiB message (sizes 64,526 · 1,047,568 · 16,776,208 B) | returns exactly `serializedSize`, which equals the bytes written | `unit/xmx1g.out` |
| Limit = size / size − 1 on the same bytes | returns size / throws "Message of size N bytes exceeds allowed maximum of N−1 bytes", at all three *L* | `unit/xmx1g.out` |
| Size exactly *L* / *L* + 1 | returns *L* / throws with N = *L* + 1, at all three *L* | `unit/xmx1g.out` |
| *P* = 2*L* and 8*L* (up to 134,217,742 B) | throws with N = `serializedSize` | `unit/xmx1g.out` |
| Header + length vint only (payload absent; 13–14 B given of up to 33,554,446) | 2*L*: throws with the full size; *L* − 1 KiB: returns the full size | `unit/xmx1g.out` |
| One byte less (length vint incomplete) | returns −1 | `unit/xmx1g.out` |
| Control: 8 × 16 MiB at `Integer.MAX_VALUE − 1` | returns 134,217,742 | `unit/xmx1g.out` |
| Control: the same 4 MiB message at 16 MiB / 1 MiB | returns 4,194,318 / throws | `unit/xmx1g.out` |
| Totals | 36 checks, 0 mismatches at `maxMemory` 1,056,309,248 and at 2,130,051,072; the 33 case lines identical at both heaps | `unit/summary.txt`, `unit/xmx-diff.txt` (empty) |

**Cluster tier.** Read-back on every lifetime from `system_views.settings`: A/B = 134217728B/134217728B (R0),
16MiB/16MiB (R1), 16MiB/1MiB (R2), 1MiB/1MiB (R3); `native_transport_max_message_size` 16777216B and
`hinted_handoff_enabled` false on both nodes. Baseline on B after `GC.run` (median of the 10 s control): direct
54.47–54.48 MiB, networking pool `Size` 8.00 MiB and `UsedSize` 0, heap 82.9–83.1 MiB, RSS 1,706–1,732 MiB. Peak
increments are over that baseline, in the size's write window plus 5 s; "200 ms" is every sample, "1 s" the first sample
of each second (B3d's rate). Both repetitions are given as rep 1 / rep 2.

| Capacity value | Run | *S* | Writes ok (client error) | B applied (local writes) | B received from A | B peak direct, 200 ms (1 s) | B peak pool `Size` | B peak RSS (1 s) | Log lines | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| default 128 MiB both | R0 | 512 KiB | 20/20 · 20/20 | 20 · 20 | 10.01 MiB | +0.50 (+0.50) | 0 | +10.4 · −1.0 | none | `cluster/R0-*/summary.txt` |
| | R0 | 4 MiB | 20/20 · 20/20 | 20 · 20 | 80.01 MiB | +16.0 · +12.0 (+8.5 · +12.0) | +8.0 | +40.8 · +28.5 | none | same |
| | R0 | 12 MiB | 20/20 · 20/20 | 20 · 20 | 240.01 MiB | +52.5 · +52.5 (+28.5 · +28.5) | +16.0 | +82.8 · +96.5 | none | same |
| 16 MiB both | R1 (control) | 512 KiB | 20/20 · 20/20 | 20 · 20 | 10.01 MiB | +0.50 (+0.50) | 0 | +10.6 · +10.7 | none | `cluster/R1-*/summary.txt` |
| | R1 | 4 MiB | 20/20 · 20/20 | 20 · 20 | 80.01 MiB | +16.0 · +16.0 (+8.5 · +16.0) | +8.0 | +40.5 · +39.0 | none | same |
| | R1 | 12 MiB | 20/20 · 20/20 | 20 · 20 | 240.01 MiB | +52.5 · +52.5 (+28.5 · +52.5) | +16.0 | +93.7 · +99.8 | none | same |
| A 16 MiB, B 1 MiB | R2 | 512 KiB | 20/20 · 20/20 | 20 · 20 | 10.01 MiB | +0.50 (+0.50) | 0 | +10.3 · +10.5 | none | `cluster/R2-*/summary.txt` |
| | R2 | 4 MiB | 0/20 · 0/20 (`WriteTimeout` ×20) | 0 · 0 | 0.005 MiB | +0.50 (+0.50) | 0 | +19.2 · +18.5 | B: 20 × "Message of size 4194363 bytes exceeds allowed maximum of 1048576 bytes", 20 "terminating connection" | same; `cluster/R2-1/B-stack-first.txt` |
| | R2 | 12 MiB | 0/20 · 0/20 (`WriteTimeout` ×20) | 0 · 0 | 0.006 MiB | +0.50 (+0.50) | 0 | +15.1 · +15.2 | B: 20 × "… 12582971 bytes … 1048576 bytes", 20 "terminating connection" | same |
| 1 MiB both | R3 | 512 KiB | 20/20 · 20/20 | 20 · 20 | 10.01 MiB | +0.50 (+0.50) | 0 | +10.7 · +10.4 | none | `cluster/R3-*/summary.txt` |
| | R3 | 4 MiB | 0/20 · 0/20 (`ServerError` ×20) | 0 · 0 | 0.005 MiB | +0.50 (+0.50) | 0 | +16.5 · +13.6 | A: 20 × "… 4194363 bytes … 1048576 bytes" at `OutboundConnection.enqueue`; B: none | same; `cluster/R3-1/A-stack-first.txt` |
| | R3 | 12 MiB | 0/20 · 0/20 (`ServerError` ×20) | 0 · 0 | 0.005 MiB | +0.50 (+0.50) | 0 | +11.3 · +9.4 | A: 20 × "… 12582971 bytes …"; B: none | same |

Further readings, every lifetime: B's inbound `ErrorCount` +0 in every phase (the rejection is not counted there); B's
dropped `MUTATION_REQ` 0 (JMX delta and `tpstats`); A applied every write locally (+20 per size, 60 in all) in R2 and R3
as in R0/R1; `tablestats` local write count and partitions: A 60/60 in all runs, B 60/60 in R0/R1 and 20/20 in R2/R3; no
`OverflowSize` above 0 anywhere; pool `UsedSize` peaks only at 200 ms in R0/R1 (+4.0 / +11.1 MiB at 4 / 12 MiB, R0-1),
mostly 0 at 1 s. The R2 stack (all 40 lines): `Message$Serializer.inferMessageSize(Message.java:818)` ←
`InboundMessageHandler.processFirstFrameOfLargeMessage(InboundMessageHandler.java:214)` on the
`127.0.0.1:7000->127.0.0.2:7000-LARGE_MESSAGES` connection, then `fatalExceptionCaught` closes it. The R3 stack (all 40):
`OutboundConnection.enqueue(:332)` ← `MessagingService.sendWriteWithCallback(:425)` ← `StorageProxy.sendToHintedReplicas(:1575)`,
logged by `ErrorMessage` as "Unexpected exception during request". Write latencies of the refused writes: R2 60–150 ms
(the coordinator answers once the connection closes, not at the 2 s write timeout), R3 a few ms. B's JMX `heap_used` peaks
(+256 / +832 MiB at 4 / 12 MiB in R0/R1, +48–64 MiB in R2/R3) include garbage and are not used below.
After the workload (B3d (6), with the fix of defect 1): count through A 60 (R0, R1), 32 · 33 (R2), 20 · 20 (R3); through
B 60 (R0, R1), 20 · none (R2), 20 · 20 (R3). The missing R2-2 count through B is a read reply from A holding one 4 MiB
row, refused by B's inbound check (`B-stack-during-counts.txt`: 4,194,356 B against 1,048,576 B, the same
`inferMessageSize` path).

### 4.2 Conclusion and logic

1. **Validity.** The run is valid. The limit was in force as set: read back on both nodes in every lifetime
   [observed: `cluster/*/summary.txt` read-back lines]. Usage was driven past the limit: in R2 and R3, 20 messages of
   4 MiB and 20 of 12 MiB each against 1 MiB [observed: `keys.csv`, the exceeds-maximum lines]. The hold-fixed
   settings held: heap 1 GiB (`MAX_HEAP_SIZE`), direct 1 GiB, hints off, `native_transport_max_message_size` 16 MiB, RF 2
   with A as the only client contact [observed: read-back lines, `*-cassandra.yaml` on the node]. The instruments see a
   held message: in R1 and R0, B's direct pool rose ≥ *S* at 4 and 12 MiB and pool `Size` by 8 and 16 MiB
   [observed: `cluster/R1-*/summary.txt`, `R0-*`], so a flat reading elsewhere is not a blind instrument.
2. **Readings.** Nothing contradicts. The two repetitions agree within a few MiB on every memory reading and exactly on
   every count. One reading is not flat: B's RSS rose 9–19 MiB during the refused sizes of R2/R3, about the same as at
   512 KiB (+10 MiB), and fell from 4 MiB to 12 MiB, so it does not scale with *S* [observed: `summary.txt`].
   R0's 4 MiB direct peak at 1 s is +8.5 / +12.0 MiB against R1's +8.5 / +16.0, sampling noise around the same
   200 ms reading.
3. **Matched row.** B3g row 1: "R2 large S fails, B logs exceeds-max, B peak memory increment much lower than R1 and
   flat in S — Claim supported: the limit caps what the receiver holds." R2 large *S* fails: 0/20 at 4 and 12 MiB in both
   reps [observed: `R2-*/summary.txt`, `keys.csv`]. B logs exceeds-max: 40 lines per lifetime at sizes *S* + 59 B against
   1,048,576 B, from `inferMessageSize` called by `processFirstFrameOfLargeMessage` [observed: `R2-1/B-stack-first.txt`,
   `B-log-excerpt.txt`]. Increment much lower than R1 and flat: at 12 MiB B's direct +0.50 vs R1 +52.5 MiB, pool `Size`
   0 vs +16 MiB, RSS +15.2 vs +93.7 / +99.8 MiB, all ≤ 1/3 of R1 (the B3f relation) in both reps [observed:
   `cluster/analysis.txt`]; at 1 s too (+0.50 vs +28.5 / +52.5). Flat in *S*: direct +0.50 at 512 KiB, 4 MiB and
   12 MiB [observed]. No oversized row on B: B's local writes +0 at 4 and 12 MiB, B's table 20 partitions
   [observed: `R2-*/B-tablestats.txt`]. B3g row 4 also holds: "R3 write fails with exception on A and nothing arrives at
   B — outbound check works as traced": 0/20, A logs 40 lines at `OutboundConnection.enqueue:332`, B received ≤ 0.006 MiB
   per size, B applied 0 [observed: `R3-*/summary.txt`, `R3-1/A-stack-first.txt`].
4. **Excluded rows.** Row 2 (R2 large *S* succeeds, row present on B): 0/20 and B's local writes +0 [observed]. Row 3 (R2
   fails but B's memory grows with *S* like R1 — the Refuted row in memory terms): B's direct and pool flat at +0.5 / 0
   MiB against +52.5 / +16 MiB in R1 [observed]; RSS does not grow with *S* (+19.2 → +15.1 MiB from 4 to 12 MiB)
   [observed]. Row 5 (R1 shows no growth: instrument blind): R1 grew +52.5 MiB direct and +16 MiB pool at 12 MiB
   [observed]. Row 6 (retry amplification): exactly one exceeds line and one "terminating connection" line per refused
   message (20 + 20) and no growth across the 20 refusals [observed: `B-log-excerpt.txt`, `samples.csv`]; the driver
   does not retry (`FallthroughRetryPolicy`) and Cassandra does not resend a message after the connection closes
   [inferred: one line per write in `keys.csv` and per message in the log]. Alternative explanations (B3h): a timeout
   rather than the size check — no `MUTATION_REQ` drops on B, and the refused writes fail in 60–150 ms, not at the 2 s
   write timeout [observed]; the knob rather than the setup — R1 and R2 differ only in B's limit and only the sizes above
   it fail [observed].
5. **Observed vs. inferred.** The conclusion rests on observed readings. Inferred: (a) that what B "holds" for a message is
   seen in the direct pool, the networking pool and RSS. This rests on the source (frames are kept in `LargeMessage.buffers`
   until complete, `AbstractMessageHandler.java:527,572`, released at `:595`) and on R1, where these instruments rose by about *S*. A
   short-lived heap object is not excluded by them. (b) That the refused message's other frames never reach a buffer
   on B. B's `ReceivedBytes` rose only 5–6 KB per 20 refused messages [observed], so no more than one first frame each
   was counted; that the rest were dropped by the closed channel, not decoded, follows from `fatalExceptionCaught`
   closing it (`InboundMessageHandler.java:289-300`).
6. **Deviations and gaps.** (1) Sampling every 200 ms as well as at 1 s (B3d says 1 s); both are reported and the
   relation holds on either. (2) The unit -Xmx control needed a temporary `build-stage4.xml` (ant's `maxmemory` overrides
   an `-Xmx` in `test.jvm.args`). (3) The two defects of §3. (4) Not measured: the deserialized heap footprint of an
   accepted message (A3's bypass (a)). The JMX heap reading includes garbage, so the run says nothing about it.
   (5) Both nodes on one host on loopback, which B3a allows. Frames therefore arrive faster than over a network, which
   makes R1's accumulation shorter, not longer.
7. **Core question.** Yes. The receiver's peak memory for one message follows the limit, not the sender's message size.
   At B's limit of 1 MiB, B held nothing measurable for 4 and 12 MiB messages (+0.5 MiB direct, constant), against
   +16 / +52.5 MiB when the limit admitted them, and refused them at the size check before any capacity or buffer
   (parts 3 and 4). The same limit on the sender stops the message before it leaves (R3). The unit tier shows the
   decision depends only on the limit and the declared length, with the payload absent.

**Conclusion (one line):** B3g row 1 (with row 4 for R3); B2g row 1 — confirmed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-read on 2026-10-20: `run1/unit/xmx1g.out`, `xmx2g.out`, `summary.txt`; every `cluster/*/summary.txt`;
`cluster/analysis.txt`; `R2-1/B-stack-first.txt`, `R3-1/A-stack-first.txt`, `R2-2/B-stack-during-counts.txt`;
`R2-1/keys.csv`, `R3-1/keys.csv`; `R2-1/B-tablestats.txt`; on the node, the stacks counted in `R2-1/B-system.log` and
`R3-1/A-system.log`.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Read-back lines say `16MiB`/`1MiB` in R2 and `1MiB`/`1MiB` in R3. R1's 12 MiB peaks of +52.54 / +52.51 MiB direct and +16.00 MiB pool are in `analysis.txt`. |
| 2. Readings | yes | RSS during R2's refused sizes is +19.16 / +15.28 (rep 1) and +18.51 / +15.26 (rep 2); at 512 KiB it is +10.38 / +10.52. It does not scale with *S*. |
| 3. Matched row | yes | `keys.csv` R2-1 holds 20 `err,WriteTimeout` rows each at 4194304 and 12582912. B's log has 40 `OversizedMessageException` stacks, every one through `processFirstFrameOfLargeMessage(InboundMessageHandler.java:214)`. The B3f relation lines in `analysis.txt` read "R2 <= R1/3" for all six readings. |
| 4. Excluded rows | yes | Each row is ruled out by a cited reading. The retry row rests on 40 exceeds and 40 close lines per lifetime, matching 40 refused writes. |
| 5. Observed vs. inferred | yes | (a) and (b) are marked inferred. Neither is needed for the memory comparison, which is observed. |
| 6. Deviations and gaps | yes | The extra sampling, the two defect fixes and the unmeasured deserialized footprint are stated. None changes a B3f/B3g row. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | The logic follows B3g: the instrument works (R1) → the receiver rejects (log, 0 rows) → its memory is flat and ≤ R1/3 (the B3f relation) → claim supported. The unit tier carries B2g row 1. |

### 5.2 Run 2?

**No** — 2026-10-20. The conclusion rests on observed readings. Each cluster run was repeated in run 1 (B3h), and the
two repetitions agree. The result neither refutes the case nor confirms a bypass. Under the README's rule, none of the
reasons for a run 2 applies.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive (from the case file: `internode_max_message_size` is a hard per-message cap on one
internode message's wire size, checked on both sides; it bounds what one message can pin, not the aggregate).

**Claim tested (B1):** a message whose on-wire size exceeds `internode_max_message_size` is rejected
(`OversizedMessageException`) at the receive-side `inferMessageSize` check before any capacity is acquired or any message
buffer is retained, so the peak memory one such message can pin on the receiver is bounded by the limit rather than by
the sender's message size. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1. `inferMessageSize` throws if and only if size > *L*, exactly at the boundary (*L* = size − 1 throws, *L* = size returns), at 64 KiB, 1 MiB and 16 MiB. N in the message is `serializedSize`. The decision is made from the header and length vint with the payload absent, and −1 is returned only while the vint is incomplete. Results are identical at 1 and 2 GiB heap. 36/36 checks. | caps (one message's size) | run 1 + self-check | 2026-10-20 |
| Cluster | **Confirmed** — B3g row 1, both reps. At B's 1 MiB limit, the 4 and 12 MiB replica writes fail (0/20) and B logs one `inferMessageSize` rejection per message from `processFirstFrameOfLargeMessage`. B applies none of them. B's peak direct is +0.5 MiB (flat in *S*) against +52.5 MiB in R1, pool `Size` is 0 against +16 MiB, and RSS is +15 against +94–100 MiB. **B3g row 4** also held: at A's 1 MiB limit A refuses at `OutboundConnection.enqueue` and B receives ≤ 6 KB per size. R0 (default 128 MiB) behaves as R1. | caps (one message, receive side and send side) | run 1 + self-check | 2026-10-20 |

**Side observations (outside the claim, for stage 3 and Target 3):**
1. **A refused write is still applied on the coordinator.** In R2 and R3 the client got `WriteTimeout` / `ServerError`, but A applied every
   refused write locally (A 60 rows, B 20) and, with hints off, nothing repairs B. With hints on, the hint would carry the
   same oversized mutation.
2. **Replies are capped too.** An unpaged `count(*)` reply above the replica's limit is refused at the replica's
   `enqueue`. A one-row read reply above the coordinator's limit is refused at the coordinator's `inferMessageSize`. A
   node with a lower limit therefore cannot read a row larger than that limit from a peer (§3 defect 1, R2-2's count through B).
3. **The rejection is not counted by B's inbound `ErrorCount`/`ErrorBytes`.** These stay 0 in every phase; it shows only in the log.
4. **A refused write fails fast in R2.** It fails in 60–150 ms because the connection close fails the callback, not at the 2 s write timeout.

**Feedback filed:** the case file's section D is updated, and a "Runbook fix (stage 4, 2026-10-20)" note is added at the end
of its B section for §3's defects (not committed; commit when Jingsong asks). The new sha256 is in `_INDEX.md` §4.
Recommendations for stage 3, not applied:
1. A1's "upper bound Integer.MAX_VALUE" is Integer.MAX_VALUE − 1 in practice (`DataStorageSpec.java:111`).
2. A3 item 2's unverified channel outcome is now observed. `fatalExceptionCaught` logs "unexpected exception caught while
   processing inbound messages; terminating connection" and closes the large-messages connection. The sender reconnects,
   and the coordinator reports the write as timed out.
3. The B3d count step needs paging (§3).
4. A3's bypass (a), the deserialized heap footprint of an accepted message, is untested here.
