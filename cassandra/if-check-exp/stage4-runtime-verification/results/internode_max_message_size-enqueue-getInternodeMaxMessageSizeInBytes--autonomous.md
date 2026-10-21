# internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous — stage-4 results  <!-- file: results/internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous.md; the stem ends in --guided or --autonomous -->
> **Case:** [`internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous`](../../stage3-ai-deep-read/cases/internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous.md)
>
> **Status:** Closed — verdict filed 2026-10-20: unit Confirmed (B2g rows 1, 4); cluster Confirmed (B3g row 1; two sub-predictions missed); effect: caps the internode send queue and wire per message, but the coordinator keeps a refused message on its heap until the write timeout (A3 bypass (a), observed: node A out of heap at 1 MiB, 3 of 3 attempts); no run 2
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
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments: `9edf2196d46995984e00dd37d7497dc48fafc363bfc545e17196520f555154f0` (`sha256sum`, run 2026-10-20 before any harness or run; the new line in `_INDEX.md` §4 is this one). Commit holding the file: `cd7fec5` (the step-0 audit commit on `main`). |
| **Harness** | `harness/internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous/` (README there), written 2026-10-20 in step 1: `MaxMessageSizeProbeTest.java` + `unit-run.sh` (unit); `make-node-yaml.sh`, `client.py`, `Jmx.java`, `cluster-run.py` (cluster; the yaml, client and JMX scripts adapted from the sibling `internode_max_message_size-inferMessageSize-size--autonomous` harness); `supp-retention.sh` (a supplementary diagnostic after run 1). md5 per file in `run1/harness-md5.txt`; instrument check in §1.2. |
| **Tiers and values** | Unit (B2): `OutboundConnection.enqueue` with L = 64 KiB · 1 MiB · 8 MiB and an unlimited control (`Integer.MAX_VALUE − 1`, §3 defect 1), S = L−1 · L · L+1 · 2L. Cluster (B3): two nodes on loopback on `pc12` (§1.2), RF=2, 16 threads × 200 writes of 2 MiB at CL=ALL through node A, L = 1 MiB · 8 MiB · 128 MiB (default, added R1), and the 256 KiB control at 1 MiB (its own lifetime, §3 defect 3). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-20 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1/A2: pending outbound bytes and direct/heap held per message. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly | Unit 64 KiB · 1 MiB · 8 MiB + unlimited; cluster 1 MiB · 8 MiB only. **Amended** (R1): add the default 128 MiB. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B3d reads direct pool and RSS; the caller's `Message` heap is named as unobservable. **Amended** (R2): add the networking pool gauges. |
| A. Core question | usage driven to the limit and past it | Met | B2c reaches 2L; B3c offers 2 MiB blobs against a 1 MiB limit and 4 MiB per-link capacity. |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps each state their reading. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f exact (accepted for L−1, L; rejected for L+1, 2L; pendingBytes unchanged); B3f about 0 pending bytes at L=1 MiB, > 0 at 8 MiB. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g rows cover the claim holding, refuted, off-by-one, similar memory (does not cap at node scale), control not moving. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | B3g row 1 needs the log line, rejected writes and pending bytes ≈ 0 against the 8 MiB run's rise. |
| B. Logic | alternative explanations and their controls | Met | B3h: 256 KiB workload, the 8 MiB run as positive control, fixed heap, empty data dirs. |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | A3 states the mechanism and bypasses; B1 states what is and is not claimed. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Met | Runnable from B2/B3 plus the amendment block. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Wire arithmetic (3.2 GiB per node) was wrong and the outbound metric path was a placeholder. **Amended** (R3, R4); hints setting moved into B3a (R5). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | The two-node setup exists (`pc57` + `pc50`, section 5 of `environment.md`); the unit probe, the writer and the sampler are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 16 × 2 MiB in flight against a 4 MiB per-link capacity; 6.4 GiB offered; about 15 GiB per node on accepted runs against 47 GB free (R3). |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked: `OutboundConnection.java:329-332` (check before capacity), `Message.java:777` (`inferMessageSize`), `DatabaseDescriptor.java:990-996` (derived default), `InternodeOutboundMetrics.java:33,122-147`. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Add a run at the default (128 MiB) beside 1 MiB and 8 MiB | Applied 2026-10-20 (B3b, amendment block) | the default is among the values |
| R2 | Also read `BufferPool,scope=networking,name=Size` and `UsedSize` | Applied 2026-10-20 (B3d, amendment block) | chunk-granular; `java.nio` `MemoryUsed` can miss a short hold |
| R3 | Correct the wire and disk arithmetic (6.4 GiB on the wire, up to about 15 GiB per node) | Applied 2026-10-20 (B3c, B4, amendment block) | a wrong estimate misleads the disk check |
| R4 | Outbound gauges are `type=Connection,scope=<peer>,name=…MessagePendingBytes`; no `PendingBytes` | Applied 2026-10-20 (B3d, amendment block) | `type=Messaging`/`InternodeOutbound` do not exist |
| R5 | `hinted_handoff_enabled: false` in B3a | Applied 2026-10-20 (B3a, amendment block) | B4 relied on it but B3a did not set it |
| R6 | Write the unit probe, the 2 MiB writer and the sampler; the two internode_max_message_size files can share one cluster harness | Done 2026-10-20 in step 1 (harness folder above; yaml, client and JMX scripts adapted from the sibling's) | prerequisites, not design changes |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts. Not filled: §5.2 chose no run 2.

### 1.2 Environment deviation, instrument check and harness (step 1, 2026-10-20)

- **Environment deviation (recorded; the design is unchanged).** The audit assumed the two-node set-up `pc57` + `pc50`,
  which is no longer in this experiment. Both nodes of the cluster tier ran on one host, `pc12`
  (`node1.jason92-320876`, no LAN interface), on loopback: A = 127.0.0.2 (JMX 7102, seed, the only coordinator),
  B = 127.0.0.3 (JMX 7103), as the sibling `internode_max_message_size-inferMessageSize-size--autonomous` cluster tier
  did on one host. B3a's addresses were 127.0.0.1/127.0.0.2; the pair moved up by one. Loopback carries frames faster
  than a network, which shortens how long a message waits in the outbound queue (a lower pending-bytes peak), not a longer one.
- **Harness choices that B2/B3 leave open** (none changes B1, B2f/B2g or B3f/B3g): the client uses native protocol 4
  (large v5 requests leave unreturned direct buffers on the coordinator, HANDOFF lesson of 2026-10-15); every
  sample is taken every 200 ms and the 1 s reading of B3d is the first sample of each second (both reported); B3f's
  "no direct-memory growth from large payloads" was coded before run 1 as "direct and pool `Size` peak increment below
  one 2 MiB message", and "higher … by about the same order (MiB to tens of MiB)" as a difference in [1, 100) MiB,
  both on each node; R4's `ExpiredCount`/`OverloadedCount` are `LargeMessageDroppedTasksDueToTimeout` and
  `…DueToOverload` (both readable, step-1 check in every lifetime's summary); node data on `/mydata/stage4-ime`
  (local disk, 715 GB free), deleted after every lifetime; B3e step 6's `pgrep -f` replaced by a `ps` match on the java
  command (README safety rule).
- **Instrument check (shakedowns, not readings), all on `pc12`, logs `~/stage4-logs/ime/shakedown{1..6}/`.** Unit:
  shakedown 1 failed in set-up (`CommitLog.instance.start()` missing), 2 timed out waiting for `close()` of a link
  still handshaking (not waited for any more), 3 ran 108 checks, 0 mismatches, beside upstream
  `ConnectionTest#testInsufficientSpace` 1/1. Cluster (`IME_PER=5`): shakedown 4 found the scripts copied without
  their execute bit and the metric-scope query failing (a wildcard over `type=Connection` also matches the `Timeouts`
  meter, which has no `Value`); 5 found the per-phase log count reading 0 (the log's timestamps use `T`, the regex a
  space; a check against the raw log gave 80 of 80 after the fix); 6 checked the `Jmx.java` fix of defect 4. Harness
  md5 compared repo ↔ node before each counted attempt: identical (`run1/harness-md5.txt`).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-20 (MDT): unit 21:30–21:31; cluster attempt 1 21:30–21:47 and attempt 2 21:47–21:54 (not counted, §3); **attempt 3 (counted) 21:59–22:19**; supplementary diagnostic 22:20–22:26 | not done |
| Node (CloudLab name and type) | `pc12` = `node1.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB, driven from `pc07` over ssh; both cluster nodes on this host on loopback (§1.2) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 (2026-08-18); nodes on G1 (`jvm11-server.options`), `MAX_HEAP_SIZE=1G`, `HEAP_NEWSIZE=256M`, `-XX:MaxDirectMemorySize=1G`, GC log on (`cassandra-env.sh` default) | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54210`), built with `ant build` and `ant build-test` on 2026-10-20; the unit test is copied in and removed by `unit-run.sh`; `git status` empty after the run | |
| Case-file commit / harness commit | case file as frozen in §1 (`9edf2196…`, commit `cd7fec5`); harness not committed (md5 per file in `run1/harness-md5.txt`: `MaxMessageSizeProbeTest.java` `eb6045f1…`, `unit-run.sh` `9550f267…`, `cluster-run.py` `393bdefc…`, `client.py` `5abde33f…`, `make-node-yaml.sh` `98938741…`, `Jmx.java` `3ce3fff3…`, `supp-retention.sh` `dc7f2712…`) | |
| Storage for node data | `/mydata/stage4-ime/{A,B}/` (LVM on the local disk `sda4`, ext4, 715 GB free), wiped at the start and deleted at the end of every lifetime | |
| Full logs (path, outside the repo) | `pc12:~/stage4-logs/ime/run1/` (61 MB: `unit/`, `cluster/<label>/` with both nodes' `system.log`, `debug.log`, `gc.log`, `samples-*.csv`, `keys-*.csv`; `cluster-attempt1/`, `cluster-attempt2/`, `supp-retention/`, `selfcheck.txt`); shakedowns in `pc12:~/stage4-logs/ime/shakedown*`; excerpts in `internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous/run1/` next to this file | |

## 3. Runbook defects

Defects 1 and 2 were found from the source before the unit tier ran; 3 and 4 in the cluster tier, which was
restarted from its beginning after each (attempt 3 is the counted one; attempts 1 and 2 are kept in
`run1/cluster-attempt{1,2}/`). None changes B1, B2f/B2g or B3f/B3g. The case file's B section is not edited in this
session (the session's rule: after the readings, section D only), so each fix is recorded, dated, in section D.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | before run 1 | B2e step 4: `setInternodeMaxMessageSizeInBytes(Integer.MAX_VALUE)` | Not settable: `DataStorageSpec.IntBytesBound` rejects 2,147,483,647 B (`DataStorageSpec.java:111`; the sibling file's defect 2) | The control uses `Integer.MAX_VALUE − 1` | AI, 2026-10-20 | section D note, not committed |
| 2 | before run 1 | B2c: a loopback peer "that is not listening (as in `ConnectionTest`), or a started `InboundSockets`" | A link to a port that refuses becomes "failing to connect" after the first attempt and then refuses every reserve (`OutboundConnection.java:409-413`; the send-queue case's U9 showed it), so at *L* = 8 MiB the accepted *S* (> the 4 MiB capacity) would be dropped as overloaded; a started `InboundSockets` delivers and drains `pendingBytes` before it can be read | A bound `ServerSocket` that is never `accept()`ed: the TCP connect succeeds, the handshake never completes, nothing drains | AI, 2026-10-20 | section D note, not committed |
| 3 | run 1, cluster attempt 1 | B3e step 4: "Run the 256KiB control workload on the same setup" (after the 2 MiB workload at *L* = 1 MiB) | Node A ran out of heap during the 2 MiB workload (21:33 MDT, after 312 refused writes in 7.9 s; `ReportJavaOutOfMemory` in `gc.log`), so the control could not run after it (client `None`) | The 256 KiB control runs in its own lifetime at the same setting (label `L1MC`); A's and B's `MutationStage`/`Native-Transport-Requests` pending tasks and `ks.t`'s memtable heap added to the sampler; cluster tier restarted | AI, 2026-10-20 | section D note, not committed |
| 4 | run 1, cluster attempt 2 | B3d sampling | `Jmx.java poll` wrote the separator before reading the value, so a failed attribute printed `,,ERR` (one field too many); on B the new `MutationStage` gauges are not registered at the start, every B row was dropped and B read 0 in `L1M` and `L1MC` | Read the value first, then write `,v`; checked in shakedown 6 (90 B rows, `ERR` fields single); cluster tier restarted (attempt 3) | AI, 2026-10-20 | harness only; section D note |

## 4. Run 1

**Scope:** unit tier (B2) at *L* = 64 KiB · 1 MiB · 8 MiB and the control (`Integer.MAX_VALUE − 1`), *S* = *L* − 1 ·
*L* · *L* + 1 · 2*L*; cluster tier (B3, attempt 3) lifetimes `L1M` (1 MiB, 2 MiB workload), `L1MC` (1 MiB, 256 KiB
control), `L8M` (8 MiB, 2 MiB workload), `DEF` (unset = 128 MiB, 2 MiB workload, R1); each workload 16 client threads
× 200 INSERTs at CL ALL through A. A supplementary retention diagnostic after the tier (§4.2 part 5). **Command log:**
`internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous/run1/` (`run-all.sh`,
`run-cluster.sh`, `run-all*.log`; per lifetime `cluster/<label>/summary.txt`; every command and its output in
`session.log` on the node).

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, `probe.out`; `maxMemory` 1,056,309,248 B; `current_version` 12 = `VERSION_40`
under the test yaml's `storage_compatibility_mode`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Upstream `ConnectionTest#testInsufficientSpace` (the enqueue/capacity path of the clone) | 1/1 pass | `unit/summary.txt` |
| *S* = *L* − 1 and *S* = *L* (65,535 · 65,536; 1,048,575 · 1,048,576; 8,388,607 · 8,388,608 B) | accepted; `pendingBytes` +*S* exactly, `pendingCount` +1, `submittedCount` +1, `overloadedCount` +0 — at 8 MiB above the 4 MiB link capacity (the reserve lent the excess) | `unit/probe.out` |
| *S* = *L* + 1 and 2*L* (65,537 · 131,072; 1,048,577 · 2,097,152; 8,388,609 · 16,777,216 B) | `OversizedMessageException` "Message of size *S* bytes exceeds allowed maximum of *L* bytes"; `pendingBytes`, `pendingCount`, `submittedCount`, `overloadedCount` +0 | `unit/probe.out` |
| Control: the same 12 sizes at 2,147,483,646 | all accepted with +*S*, +1, +1, +0 | `unit/probe.out` |
| B2h: size at `VERSION_40` vs `VERSION_50`, link version | equal for all 24 messages; link version 12 | `unit/probe.out` |
| Heap used before/after `enqueue` (sanity only, B2d) | 0 B change in all 24 cases (below TLAB granularity: says nothing) | `unit/probe.out` |
| Totals | 24 case lines, 108 checks, 0 mismatches; clone clean after | `unit/summary.txt` |

**Cluster tier** (attempt 3). Read-back on both nodes in every lifetime (`system_views.settings`):
`internode_max_message_size` = `1MiB` (L1M, L1MC), `8MiB` (L8M), `134217728B` (DEF); `write_request_timeout` 30s,
`hinted_handoff_enabled` false, send queue 4MiB, reserves 128MiB, `max_mutation_size` 16384KiB,
`native_transport_max_message_size` 16777216B, `num_tokens` 1. Baselines (median of the 10 s idle control after
`GC.run`): direct 56.17–56.21 MiB, networking pool `Size` 8.00 MiB, heap 92–93 MiB, RSS 1,762–1,803 MiB on both nodes.
Peaks are increments over the baseline in the workload window plus 5 s, at 200 ms (1 s). B was never a coordinator
(B client writes +0 in every lifetime).

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| 1 MiB | L1M, 2 MiB writes | client | 0/3200 ok: 336 `ServerError` (`OversizedMessageException: Message of size 2097211 bytes exceeds allowed maximum of 1048576 bytes`), then 16 `ConnectionShutdown` and 2,848 `NoHostAvailable` after **A ran out of heap** (10.4 s window; `ReportJavaOutOfMemory` at 22:02:18 MDT; G1 old gen 941 → 930 MB just before) | `cluster/L1M/summary.txt`, `A-gc-oom.txt` |
| | | A `system.log` | 336 "exceeds allowed maximum" lines, all 2,097,211 B vs 1,048,576 B, at `OutboundConnection.enqueue(:332)` ← `MessagingService.sendWriteWithCallback(:425)` ← `StorageProxy.sendToHintedReplicas(:1575)`, each logged by `ErrorMessage` "Unexpected exception during request"; B: none | `A-log-excerpt.txt`, `A-stack-first.txt` |
| | | A → B `LargeMessagePendingBytes` | 0 in every live sample (21 of them; 1 s 0); `LargeMessageCompletedTasks` +0 in the window; overload/timeout/error drops +0 | `summary.txt`, `samples-A.csv` |
| | | B | received 2,212 B in 13 messages (gossip), applied 0 writes, dropped 0; direct +0.00, pool `Size` +0.00, RSS −0.11 MiB | `summary.txt`, `B-tablestats.txt` |
| | | A memory | direct +17.10 (+13.10) MiB, pool `Size` +0, heap +791 MiB, `ks.t` memtable heap +80 MiB, `MutationStage` and `Native-Transport-Requests` pending 0; A's data directory 734.8 MiB (it applied the refused writes locally) | `summary.txt` |
| 1 MiB | L1MC, 256 KiB control | client, logs | 3200/3200 ok in 12.3 s; no exceeds line on A or B; A `LargeMessageCompletedTasks` +3,200 (839,043,200 B); A pending peak 1.25 MiB | `cluster/L1MC/summary.txt` |
| | | memory | A direct +15.67, B direct +9.85 MiB, pool `Size` +0 on both | same |
| 8 MiB | L8M, 2 MiB writes | client, logs | 3200/3200 ok in 215.2 s; no exceeds line; B applied 3,200, dropped 0; A sent 3,200 large messages (6,711,075,200 B) | `cluster/L8M/summary.txt` |
| | | A → B `LargeMessagePendingBytes` | peak 18.00 MiB (1 s 14.00), > 0 in 133 of 1,103 samples, `LargeMessagePendingTasks` peak 9 | same |
| | | memory | A direct +60.42 (+52.03), B direct +114.64 (+108.15) MiB; B pool `Size` +48.00, `UsedSize` +22.78 MiB; A pool `Size` +0; RSS A +320, B +278 MiB; heap +878 / +859 MiB (includes garbage) | same |
| default 128 MiB | DEF, 2 MiB writes | client, logs | 3200/3200 ok in 218.3 s; no exceeds line; B applied 3,200 | `cluster/DEF/summary.txt` |
| | | A → B `LargeMessagePendingBytes` | peak 16.00 MiB (1 s 14.00), > 0 in 120 of 1,119 samples, tasks peak 8 | same |
| | | memory | A direct +54.17 (+42.23), B direct +80.66 (+66.38) MiB; B pool `Size` +24.00 MiB; RSS A +333, B +252 MiB | same |
| — | B3f relation (`analyze`) | direct peak vs L1M, 1 s (200 ms) | L8M: A +38.93 (+43.32), B **+108.15 (+114.64)**; DEF: A +29.13 (+37.07), B +66.38 (+80.66) MiB | `cluster/analysis.txt` |

Repetitions outside the counted attempt (same harness except the fixes of §3): in attempt 1, A ran out of heap in L1M
after 312 refusals (7.9 s), L8M and DEF accepted 3200/3200 with A pending peaks 22 / 20 MiB and B direct +95.4 / +94.6
MiB; in attempt 2, A ran out of heap after 287 refusals and L1MC accepted 3200/3200 (`run1/cluster-attempt{1,2}/`).

**Supplementary diagnostic** (`run1/supp-retention/`; not a reading of B2/B3): two nodes as in B3a, one client thread ×
20 INSERTs of 2 MiB through A, A's live class histogram (`GC.class_histogram`):

| Limit | Writes | At once: `CallbackInfo` / `Mutation` / `[B` | 40 s later (past the 30 s timeout) |
|---|---|---|---|
| 1 MiB | 0/20 ok, 20 exceeds lines | 20 / 20 / 103,294,544 B | 0 / 0 / 61,354,520 B (−41,940,024 B = 20 × 2,097,001) |
| 8 MiB | 20/20 ok | 0 / 0 / 61,361,304 B | 0 / 0 / 61,360,376 B (unchanged) |

### 4.2 Conclusion and logic

1. **Validity.** Valid. The limit was in force as set on both nodes in every lifetime [observed: read-back lines in each
   `cluster/<label>/summary.txt`; `unit/probe.out` "limit read back" checks]. Usage was driven past it: 2 MiB messages
   (2,097,211 B on the wire) against 1 MiB, and in the unit tier *L* + 1 and 2*L* at three limits [observed]. The
   hold-fixed settings held (heap 1 GiB, direct 1 GiB, hints off, write timeout 30 s, reserves 128 MiB, `max_mutation_size`
   16 MiB, one coordinator) [observed: read-back lines]. The instruments see a held message: at 8 MiB and the default
   the outbound gauge rose to 14–18 MiB and B's direct pool by 66–115 MiB [observed: `L8M`, `DEF` summaries], so the
   zero at 1 MiB is not a blind instrument.
2. **Readings.** One unexpected outcome: **in L1M node A ran out of heap in every attempt** (3 of 3, after 287–336
   refusals in 7–10 s), so 2,848 of the 3,200 writes failed with `NoHostAvailable` rather than with the refusal
   [observed: `L1M/summary.txt`, `A-gc-oom.txt`, `cluster-attempt*/L1M/summary.txt`]. It does not touch the claim's
   observables (no message was queued; B received nothing) but it is recorded. A's direct pool rose +17.1 MiB in L1M
   with nothing sent to B, and +15.7 MiB in the 256 KiB control: the coordinator's own path (client frames, local
   apply), not the internode layer [observed: `L1M`, `L1MC` summaries; cause inferred]. The pending-bytes peak at
   8 MiB and the default is 14–18 MiB, well below 16 × 2 MiB [observed].
3. **Matched row.** B3g row 1: "L=1MiB rejects 2MiB writes, pending bytes about 0; L=8MiB accepts them with pending
   bytes and direct memory up — claim holds; the limit governs the largest per-message memory." Rejects: 0/3200 ok, 336
   refusals at `enqueue:332` [observed]. Pending bytes about 0: `LargeMessagePendingBytes` 0 in every sample, no large
   message completed, B received 2 KB of gossip [observed]. L=8MiB accepts: 3200/3200 [observed]. Pending bytes up:
   peak 18.00 MiB, > 0 in 133 samples [observed]. Direct memory up: A +38.9 MiB and B +108.2 MiB over L1M at 1 s
   [observed: `analysis.txt`]. The default behaves as 8 MiB (R1) [observed]. The unit tier matches B2g row 1 ("exactly
   the S > L cases throw and add 0") and row 4 ("control accepts everything") [observed: 108/108 checks].
4. **Excluded rows.** B3g row 2 (L=1MiB 2 MiB writes succeed, or pending rises to a 2 MiB scale — Refuted): 0 ok and
   pending 0 [observed]. Row 3 (similar memory in both runs): B's direct +0 against +108 MiB, pool `Size` +0 against +48
   MiB [observed]. Row 4 (8 MiB run shows no pending increase): peak 18 MiB [observed]. Row 5 (256 KiB control fails at
   1 MiB): 3200/3200 [observed]. Unit B2g row 2 (an S > L message queued): `dPendingBytes` 0 for all 6 [observed];
   row 3 (S ≤ L throws): none of 6 [observed]. Alternative explanations (B3h): a timeout instead of the check — the
   refusals came within milliseconds with the check's own message, and drops +0 [observed]; a different coordinator —
   B client writes +0 [observed].
5. **Observed vs. inferred.** The verdict rests on observed readings. Inferred, and outside the claim: (a) **why A
   ran out of heap** — `MessagingService.sendWriteWithCallback` registers the write's callback, which holds the
   `Message`, before `send()` throws (`MessagingService.java:421-426`, `RequestCallbacks.java:104-107`), and the entry
   leaves the map only when it expires at the 30 s write timeout; the refused write fails fast, so 16 client threads
   send a new 2 MiB write every few milliseconds and the refused messages pile up. The supplementary diagnostic
   observes the retention directly: 20 refused writes leave 20 `CallbackInfo` and 20 `Mutation` live and 41.9 MB more
   `[B`, gone 40 s later, and accepted writes leave none [observed: `supp-retention/`]; that this alone fills 1 GiB is
   inferred (336 × 2 MiB = 672 MiB + memtable 80 MiB + baseline 92 MiB ≈ 0.85 GiB). (b) A's +17 MiB direct is the
   client and local path — inferred from it being the same in the 256 KiB control (+15.7 MiB) where every message is
   below the limit.
6. **Deviations and gaps.** Loopback on one host (§1.2); the 256 KiB control in its own lifetime (defect 3); the
   cluster tier restarted twice (defects 3, 4); sampling at 200 ms as well as 1 s. **Two sub-predictions missed**:
   B3f's "no direct-memory growth from large payloads" at 1 MiB holds on B (+0) but not on A (+17.1 MiB, the client
   side, as in the control); B3f's "higher … by about the same order (MiB to tens of MiB)" holds on A at 8 MiB and on
   both nodes at the default, but on B at 8 MiB the difference is +108 / +115 MiB, just above "tens". Not measured:
   the heap of an accepted message (the JMX heap includes garbage), as B2d/B3d say.
7. **Core question.** Yes, within B1's scope. The sender never queued a message above the limit (unit: +0 pending
   for every *S* > *L*, exactly at the boundary; cluster: pending 0 and nothing sent at 1 MiB, against 14–18 MiB
   pending and 66–115 MiB on the receiver's direct pool at 8 MiB and the default; parts 3, 4), so the limit governs the
   largest per-message memory the internode layer holds. It does not protect the coordinator: a refused message stays
   on its heap until the write timeout, and the refused write is still applied locally (part 5); under a fast client
   that exhausted a 1 GiB heap in 10 s, three times out of three.

**Conclusion (one line):** B3g row 1 — confirmed (two sub-predictions missed, §4.2 part 6); B2g rows 1 and 4 —
confirmed; A3 bypass (a) observed, in a sharper form (the refused message is held until the write timeout).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Independent script `run1/selfcheck.py` (re-parses `unit/probe.out`, each lifetime's `keys-*.csv`, `samples-{A,B}.csv`
and both `system.log`s on the node; baseline and windows from the client's own timestamps, not from `phases.json`):
**69 checks, 66 ok, 3 failed = exactly the two missed sub-predictions** (A direct at 1 MiB; B at 8 MiB vs 1 MiB, at
1 s and 200 ms); every recomputed figure equals the run script's (`run1/selfcheck.txt`). Re-read by hand on 2026-10-20:
`unit/probe.out`; every `cluster/*/summary.txt`; `cluster/analysis.txt`; `L1M/A-stack-first.txt`, `A-log-excerpt.txt`,
`A-gc-oom.txt`; `cluster-attempt{1,2}/*/summary.txt`; `supp-retention/summary.txt` and the histograms.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Read-back `1MiB`/`8MiB`/`134217728B` on both nodes; 8 MiB pending peak 18,874,899 B (selfcheck) > 0. |
| 2. Readings | yes | A's death in L1M is in all three attempts' summaries (`alive … NO` in attempts 2 and 3, `NoHostAvailable` in all); `ReportJavaOutOfMemory` at line 11253 of A's `gc.log`. |
| 3. Matched row | yes | 336 exceeds lines in the window, all `(2097211, 1048576)`; pending 0 in all 21 live samples; L8M 3200 ok; direct differences in `analysis.txt` and recomputed by the self-check. |
| 4. Excluded rows | yes | Each row has its cited reading; the 256 KiB control's 3200 ok is in `L1MC/keys-P256K.csv` (selfcheck). |
| 5. Observed vs. inferred | yes | (a) and (b) are marked inferred and lie outside B1; the retention itself is observed (histograms). |
| 6. Deviations and gaps | yes | The two misses are the self-check's only failures; defects 1–4 and the loopback set-up stated. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B3g: refusal at the check (log, 0 ok) → nothing queued (pending 0) → the same workload is queued and held when the limit admits it (8 MiB, default) → the limit governs the per-message hold. Unit B2g row 1 + control row 4. |

### 5.2 Run 2?

**No** — 2026-10-20. The verdict rests on observed readings and the self-check reproduces every figure. The result
does not refute the case. It adds a bypass beyond the claim: A3 (a), the caller's `Message`, stays held until the write
timeout. That bypass was observed directly, in three independent lifetimes (A out of heap each time) and in a
supplementary histogram, so a run 2 by hand would add no check that run 1 lacks. The two missed sub-predictions are
recorded as misses and do not depend on interpretation.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive (weakly: a per-message ceiling on the outbound and inbound paths, not a total; it does
not bound the on-heap `Message` the caller already built).

**Claim tested (B1):** no internode message larger than `internode_max_message_size` is ever queued or accumulated by
the sender or receiver (rejected messages add 0 to outbound pending bytes), and the peak per-message memory the
internode layer holds tracks the setting (more of it with a bigger limit, none above it); not that total usage is
capped. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 and row 4. `enqueue` throws `OversizedMessageException` iff `serializedSize` > *L*, exactly at the boundary (*L* accepted, *L* + 1 refused) at 64 KiB, 1 MiB and 8 MiB; a refused message adds 0 to `pendingBytes`, `pendingCount`, `submittedCount` and `overloadedCount`; an accepted one adds exactly *S* (at 8 MiB through the reserve); the control accepts all 12; size equal at both versions. 108/108 checks. | caps (one message on the send queue) | run 1 + self-check | 2026-10-20 |
| Cluster | **Confirmed** — B3g row 1. At 1 MiB every 2 MiB write is refused at `OutboundConnection.enqueue:332` (336 log lines of 2,097,211 B vs 1,048,576 B), A's `LargeMessagePendingBytes` stays 0 and B receives nothing; at 8 MiB and at the default (R1) the same workload is accepted (3200/3200), pending peaks 18 / 16 MiB, B's direct pool +115 / +81 MiB and networking pool +48 / +24 MiB. The 256 KiB control passes at 1 MiB. Two sub-predictions missed (§4.2 part 6). | caps only on some paths (bypass): the internode queue and wire hold nothing above the limit, but the coordinator keeps each refused message on its heap until the write timeout and applies the write locally — at 1 MiB a 16-thread client exhausted A's 1 GiB heap in 7–10 s, in 3 of 3 attempts | run 1 + self-check | 2026-10-20 |

**Side observations (outside the claim, for stage 3 and Target 3):**
1. **A refused write holds the coordinator's heap for the write timeout.** `sendWriteWithCallback` registers the
   callback (holding the `Message`) before `send()` throws, and nothing removes it on the exception; observed: 20
   `CallbackInfo` + 41.9 MB of `[B` held, released after the 30 s timeout (supplementary). Because the client gets
   the error at once, nothing slows a client down: node A ran out of heap three times out of three.
2. **The coordinator still applies a refused write** (A's data 735 MiB after a run in which every write failed; as in
   the sibling file's side observation 1), and with hints off nothing repairs B.
3. **The refusal is reported as `ServerError`** ("Unexpected exception during request", one `ERROR` and stack per
   write, `ErrorMessage.java:473`), not as a write failure or timeout; the drop counters (`…DueToOverload/Timeout/Error`)
   stay 0 — the check is before them.
4. **The sender's networking pool did not move** (A `Size` +0 at every value); the large-message memory is on the
   receiver (B pool +24–48 MiB) and in plain direct buffers on both.

**Feedback filed:** the case file's section D is filled (defect fixes 1–4 as dated runbook notes, the verdicts, the
side observations and recommendations). **New sha256 of the case file after section D:**
`538cbfa9dd765a1f338f05c15df5474f9c3fc4cc18b6b64c0fb4a9c94baf71a3` (the frozen `9edf2196…` was verified unchanged before
the edit; only section D changed). `_INDEX.md` §4 is not edited in this session (its new line is this sha256). Not committed.

**Node state after the run (`pc12`, 2026-10-20 22:30 MDT):** no `CassandraDaemon`; ports 7000/7102/7103/9042 free;
`~/cassandra-run1` clean (`git status` empty, its `conf/` never changed: every node ran from its own `CASSANDRA_CONF`);
`/mydata/stage4-ime` removed; kept: `~/stage4-harness-run/ime/` (harness copy) and `~/stage4-harness-run/ime-selfcheck.py`,
`~/stage4-logs/ime/` (run 1, shakedowns).
