# hints-HintsBuffer-put-slabCapacity--autonomous — stage-4 results  <!-- file: results/hints-HintsBuffer-put-slabCapacity--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`hints-HintsBuffer-put-slabCapacity--autonomous`](../../stage3-ai-deep-read/cases/hints-HintsBuffer-put-slabCapacity--autonomous.md)
>
> **Status:** run 1 done, self-checked, verdict filed (2026-10-26)
>
> **Outcome class:** true positive (estimate positive; effect: caps)
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
| **Case-file version** | the case file at repository HEAD `1ae567d` plus the uncommitted audit amendments of 2026-10-26 (the orchestrator commits). sha256 of the whole file after the amendments: `e8a7255335602c2750b55d223673c6388da4198e8d6a418b7bbc37d3ea7a9a0e` (before: `0552190b61477cbb1f2ff61cc3272ce9951671aed2b719f051cafeb9c0a1aff6`). **Frozen before any reading** (2026-10-26): sha256 of the extracted text of B2f `9a36e86f82b298e83beab2ed151d9866b3eb24455524ad78e1a8ffc670dc03b9`, B2g `399a7d39cf341ef83bd5e23f1c2ca898a0d16ec196bea04b82cc99cf980656ca`, B3f `c7749c23c759f12a03f5faf4ea6e3737ab1ef25cf364819fea0fb9ffbac15017`, B3g `5335c30d3c7641692c19b7187b2483102fd75674d5df2e11bf13a1b3a662c564`; the four concatenated `780af0197f522f7298c4c608983b0a8c4f81caad38b700d081d470d7d3c7b7af` (extracts kept at `~/s4-hb-logs/hb-B*.txt`). |
| **Harness** | `harness/hints-HintsBuffer-put-slabCapacity--autonomous/` (written after this audit and before run 1; not committed by this agent) |
| **Tiers and values** | unit (B2) and cluster (B3), both run. Unit: slab 1/4/32 MiB, n = 1 (stall only), 2, 3, 5; derivation 4/16/24/40 MiB. Cluster: configs A (4 MiB), C (default 16 MiB), D (24 MiB), B (40 MiB), n series 2/3/6 at A, peer-up control, large-hint boundary at C. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: direct (off-heap) bytes held by the slabs, `ByteBuffer.allocateDirect(slabSize)` (`HintsBuffer.java:75-78`), measured as `java.nio` direct `MemoryUsed`. |
| A. Core question | knob varied, >= 3 values incl. default — or another approach, with the reason | Met after amendment | B2b/B3b as filed give only two distinct slabs (4 MiB and 16 MiB `max_mutation_size` both give the 32 MiB floor, `HintsService.java:79,110`). Amended: 24 MiB (slab 48 MiB) added in both tiers; the buffer-count knob `MAX_HINT_BUFFERS` is the second knob (2, 3, 6; the 1 is a deadlock, rec. 2). Positive estimate, so no positive control is required; the buffer-count series is the dose-response of the cap. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d/B3d read the JVM direct-buffer pool (`MemoryUsed`, `Count`) as well as `allocatedBuffers`; the gap (all other direct users) is named and handled by baseline deltas. |
| A. Core question | usage driven to the limit and past it | Partly, fixed by amendment | B3c as filed does not force the ceiling (a fast disk can recycle before the stress fills three slabs; B3g row 4 would then say "not confirmed"). Amended: the closed MAX_HINT_BUFFERS case's `hold-flush.btm` holds every flush 2 s so that writers reach `take()` (`HintsBufferPool.java:118`). Unit tier: the 200 ms stub delay and a stall stub reach it directly. |
| B. Logic | each step says what it establishes | Met | B2e, B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Met after amendment | B2f/B3f give `n x slab`. Two numbers were wrong against the source and are amended with their reason (not a reading): n = 1 (rec. 2), and the large-hint rows, which are mutation sizes, not blob sizes (rec. 5). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | B2g/B3g cover exceed / refute, no-block, off-by-overhead, derivation, not enough pressure. Missing: a row for "capped by the buffer count but the slab size does not follow `max_mutation_size`" (covered by the last B2g row for the unit tier; in the cluster tier by B3g row 2) and a "bypass" row; the results file reads a bypass as: the pool is capped but an oversized hint is silently lost (a recorded path, not a refutation). Not applied to the case file (table is frozen); left for stage 3. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met after amendment | Disallow evidence: the `waiting` Byteman trace at `take()` and, for the per-hint cap, the exception exit of `HintsBuffer.allocate` (rec. 5); B3e/B3g now name both. |
| B. Logic | alternative explanations and their controls | Met | B3h: peer-up no-hint arm (direct stays at baseline), buffer-count series, baseline deltas. |
| C. Specific | a human can follow it from the intro and §9a | Met | A1-A3, B1. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly | B2c(1) "or a bare size via a stub" is exact enough (`HintsBuffer.allocate(int)`); B3c lacked the stress column count and row count (rec. 4); the large-hint blob needs calibration (rec. 5). Fixed by amendment. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met after amendment | see above; sampling every 1 s (harness). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | `~/s4-hb` built (`ant build-test`, 1 min 18 s); Byteman 4.0.20 in `build/lib/jars`; reusable closed-case harness (`hints-pool.btm`, `hold-flush.btm`, `HintsPoolCeilingTest`) and the `hints-CompressedHintsWriter` cluster driver. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met after amendment | B3c as filed: `-col size=FIXED(2000)` is 5 columns by default, so 2,000,000 rows would be about 20 GB of hints, not 4 GB. Amended to one column and 500,000 rows (about 1.05 GB), 10 x the 96 MiB ceiling at config A, 4 x the 240 MiB ceiling at config B; 55 GB free on `/` shared with other agents. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met after amendment | All of these checked 2026-10-26 against `cassandra/cassandra-5.0.9/` (clean `git status`): `HintsBuffer.java:58,75-78,96-100,148-157,183-196`; `HintsBufferPool.java:41,46,59-66,68-84,86-90,107-128,130-134,136-139`; `HintsService.java:79,110-111,161-170`; `CassandraRelevantProperties.java:351`; `DatabaseDescriptor.java:898-901,2827-2829`; `Config.java:407,447-448`; `IMutation.java:31`; `Mutation.java:169-177`; `CommitLog.java:304`; `MutationVerbHandler.java:54`; `StorageProxy.java:2811`; `Hint.java:163-168`; `HintsWriteExecutor.java:53,60,83,241`; `conf/cassandra.yaml:660`. Wrong: `HintsBuffer.java:100-108` for the offsets (is `:199-206`); `FlushBufferTask.run` `:140-153` (is `:141-155`). Arithmetic: default slab 32 MiB, per-hint cap 16 MiB, `hintSize + 12 > capacity/2` boundary: right; "about 3" gcgs bytes is exactly 3. Mechanism claim "exception goes up through the HintRunnable": it is wrapped (`StorageProxy.java:2718-2723`) and swallowed by the unread `Stage.MUTATION.submit` future (`:2826`), so there is no log line (rec. 5). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Citation fixes (offsets `:199-206`; `FlushBufferTask.run` `:141-155`), gcgs vint exactly 3 bytes and the exact hinted-versus-commit-log window (`M + 23 <= slab/2` versus `M + 12 <= m`) | Applied 2026-10-26 (case file amendments in A3; uncommitted, the orchestrator commits) | Wrong cites and an inexact figure. |
| 2 | `MAX_HINT_BUFFERS = 1` cannot run the workload: `flushCallback.flush` is called only after `switchCurrentBuffer` returns (`HintsBufferPool.java:79-80`) but `switchCurrentBuffer` blocks in `take()` first when `allocatedBuffers >= 1` (`:113-118`): deadlock. Series 2, 3, 5 (unit) and 2, 3, 6 (cluster); n = 1 only as a stall observation in the unit tier. | Applied 2026-10-26 (B2e, B2f, B3b, B3f) | Source-derived, no reading involved; the closed MAX_HINT_BUFFERS case and HANDOFF's follow-up list the same deadlock. |
| 3 | Add `max_mutation_size` 24 MiB (slab 48 MiB) to both tiers | Applied 2026-10-26 (B2b, B3b, B3f) | 4 MiB and 16 MiB give the same 32 MiB floor, so the knob would show only two distinct slabs. |
| 4 | Workload size and trigger: one column, 500,000 rows; `hold-flush.btm` (2 s) in every arm; flush stub delay 200 ms in the unit tier | Applied 2026-10-26 (B2c, B3c) | The default stress row is 5 columns (about 10 KB), so the filed arithmetic was 5 x too large; without a held flush the ceiling is not guaranteed to be reached. |
| 5 | Large-hint rows are mutation sizes, with the exact window; `native_transport_max_message_size` raised to 20 MiB for that arm; evidence is the Byteman exception-exit trace and the unchanged `TotalHints` (this row first said 'not a log line' and 'swallowed'; wrong, the node logs an ERROR line per rejected hint, corrected 2026-10-26 after cluster run 1, results 3) | Applied 2026-10-26 (A3 a, B3c, B3e, B3f) | Default CQL message limit equals `max_mutation_size` (`DatabaseDescriptor.java:3236-3244`), (the rejection is wrapped at `StorageProxy.java:2718-2723` and does log). |
| 6 | The filed B2g/B3g lack a "bypass / silent loss" row and a "slab does not follow the knob in the cluster" row | Left for stage 3 | Tables are frozen; the results file maps such an outcome to the nearest row and says so. |
| 7 | B2a/B3a name a `/local/scratch` copy and `-Xms2G -Xmx2G` | Deviation recorded: copy at `~/s4-hb` made by `copy-source.sh`, data under `~/s4-hb-data/` on local `/`; node A heap 2 GiB, node B 1 GiB | Shared node, per-agent trees. |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | unit 2026-10-26 (local 2026-10-25 22:03-22:07 EDT), cluster 2026-10-26 (22:25 EDT to about 03:20 EDT, finished while the agent session was rate-limited; see §3) | not done |
| Node | `pc07` (`node0.jason92-320876`), 40 cores, 251 GiB, shared with other agents | |
| OS and kernel | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK / Ant | OpenJDK 11.0.32.1 / Ant 1.10.12 | |
| Local source copy | `~/s4-hb` by `copy-source.sh` from `cassandra/cassandra-5.0.9/` at repository HEAD `1ae567d`, tag `cassandra-5.0.9`, `ant build-test` 1 min 18 s | |
| Case-file / harness commit | uncommitted (orchestrator commits); case-file sha256 after run 1 `03a5c8667e477ceed2dce8e584c947875cbf969fe67a3fe82e9313c243693639` | |
| Storage for node data | `~/s4-hb-data/{A,B}` on local `/` (sda3, 63 GB, about 36 GiB free), wiped after every arm | |
| Full logs | `~/s4-hb-logs/run1/{unit,cluster}`, attempt 1: `~/s4-hb-logs/run1-attempt1`, `~/s4-hb-logs/run1-cluster-attempt1` (on pc07, outside the repo) | |
| Ports | JMX 7320/7321, Byteman 9320, native 9342, storage 7020, loopback 127.0.20.1-2 (7322, 9343-9344, 7022, 127.0.20.3 unused) | |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | unit attempt 1 | B2e step 3 validity check | My check `rotation-many-slabs-through` counted flushes that had started; at n = 5 the 1-thread flusher still had 3 queued at the end (17 started of 20 rotations), so it failed (17 of 18 checks ok; no B2f/B2g relation failed). | Count rotations (flush callbacks): `submitted`. Whole unit tier rerun as run 1 (attempt 1 summary kept in `run1/attempt1/`). | 2026-10-26 | uncommitted |
| 2 | cluster attempt 1 | B3c trigger | Hold of 2000 ms per flush is too short for the offered load (about 12 MB/s from the one client process: a 32 MiB slab fills every 2.7 s): arm A3 created 2 slabs of 3, no writer waited, ceiling not reached (B3g row 4, "not confirmed, raise load"). Arm A2 was interrupted at start-up (nodes stopped by pid; no reading). | Hold 10000 ms (longer than the 80 MiB fill time of 6.7 s); case-file amendment dated 2026-10-26; B3f/B3g unchanged; the whole cluster tier restarted. Attempt 1 ctl and A3 summaries are in `run1/attempt1/`. | 2026-10-26 | uncommitted |
| 3 | audit statement | A3/B3c amendment | My amendment said a rejected hint leaves no log line; it does (one ERROR with `Hint of N bytes is too large` per rejection, `L/A-log-excerpt.txt`). Corrected in the case file; the Byteman trace stays the primary evidence. This edit changed the extracted text of B3f (new sha256 `2807bee20a144acf7158f2c7810705d4458a8d8d133869dbbfdb9217e38d5057`, was `c7749c23...`); only an audit-written sentence in the amendment differs, no number or row. | | 2026-10-26 | uncommitted |

**Interruption (2026-10-26).** The agent session was cut off by an API rate limit while the cluster tier ran. The cluster driver is a detached background job and finished all 8 arms meanwhile; on resume no process or port of this harness was left (`ps`, `ss` checked) and the timing log has a line for it. No arm was cut mid-way, so nothing was rerun for that reason.

## 4. Run 1

**Scope:** unit tier: boundary at S = 1/4/32 MiB; rotation and stall at n = 1 (stall only), 2, 3, 5; derive at m = 4/16/24/40 MiB. Cluster tier: arms ctl, A3, A2, A6, C3, D3, B3, L (all of them, attempt 2). **Command log:** `hints-HintsBuffer-put-slabCapacity--autonomous/run1/` (unit `.out` per n, cluster `summary.txt`, `phases.json`, `hb.trace`, `A-log-excerpt.txt` per arm, `selfcheck-run1.txt`).

### 4.1 Readings

**Unit tier** (all `STAGE4 check` lines ok: n=1 12/12, n=2 18/18, n=3 18/18, n=5 18/18, derive 3/3 for each m; upstream `HintsBufferTest` 2 and `HintsBufferPoolTest` 1 pass)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Boundary S = 1, 4, 32 MiB | `S/2-12` accepted; `S/2-11` and `S/2+1` rejected "Hint of N bytes is too large - the maximum size is S/2" (e.g. S = 32 MiB: 16777205 rejected, max 16777216) | `unit/n3.out` |
| Rotation, S = 4 MiB, 81 hints = 20.17 x S bytes, 20 slab rotations | n=2: allocatedBuffers 2, direct delta 8,388,608 (max the same); n=3: 3, 12,582,912; n=5: 5, 20,971,520; Count delta = n; all slabs 4 MiB | `unit/n2.out`, `n3.out`, `n5.out` |
| Stall (flush never returns) | writer WAITING in `LinkedBlockingQueue.take` under `switchCurrentBuffer`; allocatedBuffers n; delta n x S exactly, unchanged after 2 s; flush callbacks n-1; n=1: writer parked with 1 slab, 0 flush callbacks | `unit/n1.out` ... `n5.out` |
| Derivation | slab 33,554,432 for m = 4 and 16 MiB; 50,331,648 for 24; 83,886,080 for 40; boundary hint (hintSize = slab/2-12) accepted and +1 rejected on the real `HintsService` pool; slab allocation adds exactly the slab to direct `MemoryUsed` | `unit/derive*.out` |

**Cluster tier** (A = measured coordinator; baseline after B down, GC x2, 10 s; pool bytes = direct delta + slabs created before the baseline x slab; 500,000 rows of 2,000 B at CL ANY, 1 hold of 10 s per flush; hints on disk 986.6 MiB in every hint arm)

| Capacity value | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| mms 4 MiB (slab 32), n=3 | ctl (peer up) | slabs, waiting, delta | 1 slab (idle), 0 waits, peak delta 1.85 MiB, no hints | `cluster/ctl/summary.txt` |
| 4 MiB, n=3 | A3 | slabs / waiting / peak pool bytes / plateau | 3 / 28 / 97.87 MiB (n x S = 96) / second-half range 1.19 MiB | `cluster/A3/summary.txt` |
| 4 MiB, n=2 | A2 | same | 2 / 29 / 65.90 MiB (64) | `cluster/A2/summary.txt` |
| 4 MiB, n=6 | A6 | same | 6 / 24 / 193.89 MiB (192) | `cluster/A6/summary.txt` |
| 16 MiB default (slab 32), n=3 | C3 | same | 3 / 28 / 97.88 MiB (96) | `cluster/C3/summary.txt` |
| 24 MiB (slab 48), n=3 | D3 | same | 3 / 18 / 145.86 MiB (144) | `cluster/D3/summary.txt` |
| 40 MiB (slab 80), n=3 | B3 | same | 3 / 8 / 241.89 MiB (240) | `cluster/B3/summary.txt` |
| 16 MiB, large hints | L | M = m-100, m-23 | hinted (no `allocreject`; TotalHints 2, 3) | `cluster/L/summary.txt`, `hb.trace` |
| 16 MiB, large hints | L | M = m-22, m-15, m-12 | `allocreject` hint 16777205 / 16777212 / 16777215 (cap 16777216 incl. +12: rejected); TotalHints stays 3; 3 ERROR lines "Hint of N bytes is too large" | `cluster/L/summary.txt`, `A-log-excerpt.txt` |
| 16 MiB, large hints | L | M = m-11 | refused by the CQL layer "Request is too big: length 16777217 exceeds maximum allowed length" before any hint | `cluster/L/summary.txt` |

All hint arms: client ok 500,000 of 500,000, `TotalHints` 500,000, no OutOfMemoryError, no "Direct buffer memory" error; `analysis.txt`: the n series (65.9 / 97.9 / 193.9 MiB = 2/3/6 x 32 MiB) and the slab series (97.9 / 97.9 / 145.9 / 241.9 MiB for mms 4, 16, 24, 40) both follow within 2 MiB.

### 4.2 Conclusion and logic

1. **Validity** [observed: `cluster/*/summary.txt`, `unit/*.out`]. The limit was reached in every hint arm: slabs created == n and writers waited at `take()` 8 to 29 times (A2 29, A3 28, A6 24, C3 28, D3 18, B3 8). Held settings: MAX_HINT_BUFFERS on A's command line, `max_mutation_size` read back, slab sizes from the `created` trace equal the derived 32/48/80 MiB, MaxDirectMemorySize 1g, same client and rows in every arm. The control arm (peer up) did not create hints. The first cluster attempt (hold 2 s) was not valid (§3 #2) and is not used.
2. **Readings** [observed]. The idle node already holds one slab, created by the periodic flush before the baseline (`created n=1` on `HintsWriteExecutor:1`); so growth over baseline is (n-1) x slab. [inferred: pool bytes add the pre-baseline slab; the `created` trace gives it exactly.] Plateau second-half range 0.1 to 1.2 MiB while hints on disk grew to 986.6 MiB [observed: `selfcheck-run1.txt`].
3. **Matched row.** Unit B2g: "Direct delta stays <= n x S while many times n x S bytes pass through" (n=2: 10x; n=3: 6.7x; n=5: 4x; 20.17 x S of entries each), plus "Threshold sits exactly at S/2" and derivation follows `max_mutation_size`. Cluster B3g: "Direct memory plateaus at about n x slab ... while hints on disk grow" and "Plateau moves proportionally with `max_mutation_size` and `MAX_HINT_BUFFERS`".
4. **Excluded rows.** Off-by-overhead (accept at S/2-11 / reject at S/2-12): the opposite was observed. "Delta over n x S or allocatedBuffers > n": max 8,388,608 / 12,582,912 / 20,971,520 = n x S exactly, allocatedBuffers n, cluster peak pool bytes within 1.9 MiB of n x S (the excess is JVM noise on the direct pool). "Writer never blocks": it parked in `take()` (unit) and 8-29 `waiting` lines (cluster). "Slab does not follow `max_mutation_size`": slabs 32/32/48/80. "Peak lower than n x slab": attempt 1 only; ruled out in attempt 2 (peak pool bytes >= n x S - 2 MiB). "Large-hint rows both stored": the m-22/-15/-12 rows were rejected.
5. **Observed vs inferred.** Inferred: that all of the pool-attributable growth is the slabs (other direct users held flat, supported by ctl 1.85 MiB and the 1.1 MiB plateau range); the hinted/rejected status of each large row is observed (trace + TotalHints + ERROR line), M = hintSize - 11 is inferred from `Hint.serializedSize` (calibration line: blob 16773120 -> hintSize 16773175).
6. **Deviations and gaps.** Copy at `~/s4-hb`, not `/local/scratch`; client is the bundled Python driver at 200 in flight, not `cassandra-stress`; 500,000 rows of 1 column; hold-flush 10 s trigger in every arm (a slow-disk imitation: with a fast flush the pool would stay below its cap, as attempt 1 showed, which does not contradict the cap); `native_transport_max_message_size` 20 MiB in arm L; peer B is on loopback; heap 2 GiB on A. Only 1 value of the cap exists in hint-free runs, so the `ctl` arm shows the idle slab only. No NMT reading was taken (not needed: the `direct` pool equals the slabs). `MAX_HINT_BUFFERS=1` was not run in the cluster (deadlock; unit stall only).
7. **Core question.** Usage follows the constraint: the off-heap bytes held by the hints pool are exactly `n x max(2 x max_mutation_size, 32 MiB)` (unit and cluster, parts 1, 3), they stop there while hints on disk grow and writers wait (part 2), and the per-hint rejection sits at slab/2 (unit boundary, cluster L). The constraint caps usage; the filed estimate (positive) holds. One bypass-like effect is recorded, not a bypass: a mutation of size m-22 to m-12 passes the commit log but its hint is rejected (data stays only in the mutation's other replicas).

**Conclusion (one line):** unit B2g "delta stays <= n x S while many times n x S bytes pass through; threshold at S/2; slab follows `max_mutation_size`" and cluster B3g "plateau at about n x slab above while hints on disk grow; plateau moves proportionally with both knobs" — confirmed.

## 5. Self-check of run 1 — AI

The self-check re-parsed the raw files with `harness/hints-HintsBuffer-put-slabCapacity--autonomous/selfcheck.py` (`hb.trace`, `samples-jmx.csv`, `hints-ls.txt`, the `.out` files) and did not use `phases.json` or `samples.csv`. Its numbers (`selfcheck-run1.txt`) equal the driver's: created 1/3/2/6/3/3/3 slabs for ctl/A3/A2/A6/C3/D3/B3 as filed, waiting 0/28/29/24/28/18/8, peak pool 33.85/97.87/65.90/193.89/97.88/145.86/241.89 MiB, hints dir 986.6 MiB.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `hb.trace` per arm: `created` count equals n, `waiting` lines present; `selfcheck` k0 = 1 everywhere; ctl has 0 waiting; sizes 32/48/80 MiB. |
| 2. Readings | yes | `samples-jmx.csv`: second-half range of direct during the workload 0.10-1.19 MiB; hints directory 986.6 MiB by `ls -l`. |
| 3. Matched row | yes | unit `.out` files: S/2 boundary, n x S deltas; cluster peak pool bytes within 1.9 MiB of n x S in all six hint arms. |
| 4. Excluded rows | yes | no delta above n x S + 64 KiB (unit); cluster excess max 1.89 MiB (B3: 241.89 vs 240) inside the 2 MiB band set before the run. |
| 5. Observed vs inferred | yes | calibration line and `alloc`/`allocreject` sizes in `L/hb.trace`: hint = M + 11; rejected sizes 16777205, 16777212, 16777215 all > 16777204. |
| 6. Deviations and gaps | yes | listed; none changes the matched row. |
| 7. Core question | yes | the steps from B1 to answer follow B2e/B3e. |

### 5.2 Run 2?

No (2026-10-26). The conclusion rests on observed trace lines and exact deltas in two tiers that agree; no part is settled only by inference; the result neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps).

**Claim tested:** (B1) a hint whose serialized size plus 12 exceeds half the slab is rejected and one at or below is accepted, where the slab is `max(2 x max_mutation_size, 32 MiB)`; the direct memory held by the hints pool never exceeds `MAX_HINT_BUFFERS x slab`, however many hints are written, so the ceiling moves proportionally with both knobs. "Confirmed" means this held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed: threshold exactly at S/2; direct delta <= n x S (exactly n x S) with 4-10 x n x S through; slab follows `max_mutation_size` | caps | run 1 + self-check | 2026-10-26 |
| Cluster | Confirmed: plateau at n x slab (pool bytes within 1.9 MiB) while hints on disk grew to 986.6 MiB; ceiling moves proportionally with `MAX_HINT_BUFFERS` (2/3/6) and `max_mutation_size` (32/32/48/80 MiB slabs); large-hint boundary at m-23 / m-22 | caps | run 1 + self-check | 2026-10-26 |

**Positive control:** not required (positive estimate). The `ctl` arm (peer up) stayed at the idle slab; the buffer-count series is the dose-response.

**Feedback filed:** case file section D filled (uncommitted); amendments in A3, B2b/B2c/B2e/B2f, B3b/B3c/B3e/B3f (dated 2026-10-26); sha256 after run 1 `03a5c8667e477ceed2dce8e584c947875cbf969fe67a3fe82e9313c243693639`. Candidate upstream issue: `MAX_HINT_BUFFERS=1` deadlocks the hint path (already in HANDOFF follow-ups).

**Leftovers.** No process or listening port of this harness remains (`ps`, `ss` checked 2026-10-26). On pc07: `~/s4-hb` (tree with untracked `HintsSlabCapTest.java`), `~/s4-hb-data/` (empty node dirs and `jmx/` classes, about 150 MB from shakedowns removed per arm), `~/s4-hb-logs/` (all logs), `~/s4-hb-build.log`, `~/s4-hb-copy.log`.
