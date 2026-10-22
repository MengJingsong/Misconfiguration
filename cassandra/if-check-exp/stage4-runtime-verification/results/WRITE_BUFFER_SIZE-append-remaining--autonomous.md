# WRITE_BUFFER_SIZE-append-remaining--autonomous — stage-4 results  <!-- file: results/WRITE_BUFFER_SIZE-append-remaining--autonomous.md; the stem ends in --guided or --autonomous -->
> **Case:** [`WRITE_BUFFER_SIZE-append-remaining--autonomous`](../../stage3-ai-deep-read/cases/WRITE_BUFFER_SIZE-append-remaining--autonomous.md)
>
> **Status:** **Closed 2026-10-21 — unit Confirmed, cluster Confirmed — does not cap** (estimate negative, matched); one sub-prediction missed (8/2048 write timeouts per limit arm); no run 2
> 
> **Outcome class:** true negative — stage-3 estimate vs the stage-4 effect on the constraint
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
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments: `55bf043e43ebcbb70b926e214b47356edd69ce76a20a9d4aee7d832563bc5ab6` (`sha256sum`, run 2026-10-20 before any harness or run; the new line in `_INDEX.md` §4 is this one). Commit holding the file: `cd7fec5` (the step-0 audit commit on `main`). |
| **Harness** | [`harness/WRITE_BUFFER_SIZE-append-remaining--autonomous/`](../harness/WRITE_BUFFER_SIZE-append-remaining--autonomous/README.md), written 2026-10-20 (step 1, R4): `WriteBufferProbeTest.java` + `unit-run.sh` (B2), `wbs.btm`, `client.py`, `Jmx.java`, `make-node-yaml.sh`, `cluster-run.py` (B3), `selfcheck.py`. **Instrument checks (not readings):** `javac` of the test against the clone; unit shakedown1 (266 checks; the only mismatch is the filed B2h control, defect D1 below); `TestScript` on `wbs.btm` (8 rules, no errors); cluster shakedown1 (`WBS_RUN=shakedown1`, 128 MiB per arm, one rep). |
| **Tiers and values** | Unit (B2): `HintsWriter.Session.append(Hint)` and `append(ByteBuffer)` with hint sizes 1 · 100 · 255 · 257 KiB · 1 · 4 · 15 MiB, the 256 KiB buffer and a 64 KiB variant, positive control `HintsBuffer.allocate` at `capacity/2`. Cluster (B3): node A, B down, 100 KiB · 1 MiB · 8 MiB values (2 GiB each), `MAX_HINT_BUFFERS` 3 · 1, `max_hints_size_per_host` 0 · 64 MiB. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-20 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1/A2: heap of the temporary buffer, direct memory and disk bytes of hint writing. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | The constant cannot be varied (A1); the design varies the hint size across 255/257 KiB, adds a 64 KiB buffer variant, and varies the governing knobs in B3b. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d thread-allocated bytes, file length, `getBytesWritten`; B3d direct pool, `du`, heap, NMT (the 256 KiB buffer inside the pool total is inferred; named). |
| A. Core question | usage driven to the limit and past it | Met | 15 MiB hints are 64 × the buffer; 2 GiB of hints per run far exceeds the 32 MiB slab and the 128 MiB file size. |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps each state their reading. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f exact thresholds (alloc ≥ S+12 above 257 KiB, ≈ 0 for `append(ByteBuffer)`); B3f plateaus in MiB and disk totals. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | The negative-file rows are present (Refuted when usage follows; Confirmed when flat and the control moves; Not confirmed otherwise) but no row for the memory-side control not moving. **Added** (R1). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Confirmed needs overshoot written in full plus the control binding (unit allocate guard; cluster per-host limit and `MAX_HINT_BUFFERS=1`). |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: positive controls on both tiers (a binding guard; `max_hints_size_per_host` for disk, `MAX_HINT_BUFFERS=1` for memory), baseline with B up, repeats. |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | A1-A3 and B1 explain the test-only overload and the production path. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Met | Runnable from B2/B3 plus the amendment block. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met | Sizes, counts, rates, sampling and cleanup are exact. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | Two-node setup exists; the probe and the writer are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 2 GiB of hints per run; 5 runs with truncation between (R2) and up to about 25 GiB of other data against 47 GB free. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked: `HintsWriteExecutor.java:50,60`, `HintsWriter.java:136,184,200,232`, `HintsBuffer.java:148-157`, `StorageMetrics.java:45-46`, `StorageProxy.java:2418` (cited as 2413). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Add a B3g row for `MAX_HINT_BUFFERS=1` not lowering the direct-pool delta (Not confirmed) | Applied 2026-10-20 (B3g, amendment block) | the memory-side control had no row for failing to move |
| R2 | Truncate the table (or recreate the keyspace) between value-size runs | Applied 2026-10-20 (B3e, amendment block) | `truncatehints` leaves 2 GiB of table data and commit log per run |
| R3 | Live setter is at `StorageProxy.java:2418` | Applied 2026-10-20 (amendment block) | citation off by five lines |
| R4 | Write the unit probe, the hint writer and the 1-s sampler | step 1 (harness) | prerequisites, not design changes |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's runbook observables:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-20 23:51 – 2026-10-21 02:38 EDT (shakedowns 23:51–00:23; unit 00:24–00:25; cluster attempt 1 00:25–01:22, not counted, D2; cluster 01:33–02:38) | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB); session ran on it directly. **Environment deviation E1:** both nodes on this host on loopback (A 127.0.0.2 / JMX 7102, B 127.0.0.3 / JMX 7103), not `pc57` + `pc50` | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | — |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18) | — |
| Ant (`ant -version`) | 1.10.12 | — |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54210d541339c2e7c17a794195cac0e67c2`), `ant build-test` done earlier | — |
| Case-file commit / harness commit | case file `cd7fec5` (sha256 `55bf043e…` verified before the run); harness not committed (md5 of the node copy in `~/stage4-harness-run/wbs.md5`, equal to the repo files) | — |
| Storage for node data | `~/stage4-wbs/{A,B}` on local `/dev/sda3` (ext, PERC H730P RAID, spinning), 54.5 GiB free at start | — |
| Full logs (path, outside the repo) | `pc07:~/stage4-logs/wbs/run1/` (`unit/`, `cluster/{main,mhb1-1,mhb1-2}/` with per-start `wbs-<n>.trace`, keys, NMT, thread dumps, system/gc logs; `cluster-attempt1-defectD2/`); shakedowns `~/stage4-logs/wbs/shakedown{1,2,3}/` | — |

## 3. Runbook defects

Every step a run could not execute as written. The run stops at the
defect; the fix is made in the case file (dated) if it leaves §9a unchanged,
and the affected tier restarts from its beginning. If the fix would change
§9a, the case goes back to the audit. "None" if there were none.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | instrument check (unit shakedown1, before run 1) | B2h | The filed positive control `HintsBuffer.create(1 << 20).allocate(400 KiB)` cannot refuse: 400 KiB + 12 = 409,612 B is below `slab.capacity()/2` = 524,288 B (`HintsBuffer.java:150-155`); arithmetic, not a reading. | The harness keeps the filed check (reported, expected to fail) and adds `allocate(600 KiB)` (refused) and the pair `capacity/2 − 12` admitted / `+ 1` refused; 400 and 600 KiB hints also go through the 256 KiB write buffer. B2f/B2g unchanged. | 2026-10-20, harness only (the case file is not edited before run 1's readings; noted in section D after run 1) | none (not committed) |
| N1 | pre-run source note (before run 1) | B3b item 3 / B3e step 4 | `MAX_HINT_BUFFERS=1` can never recycle a buffer: `allocate()` hands a full buffer to the flush callback only after `switchCurrentBuffer()` returns (`HintsBufferPool.java:79-80`), and with one buffer `switchCurrentBuffer` waits in `take()` (`:112-118`) for a recycle only that callback's task performs (`HintsWriteExecutor.java:141-154`; the periodic flush does not recycle, `:160-176`). The guided `MAX_HINT_BUFFERS` file records the same ("Do not use n ≤ 1", its 9b). So the arm's hint writer is expected to wait for good once the first slab fills, stalling the `MutationStage` and the client's writes. | Run as filed (the B3f/B3g rows are about direct memory, which the arm can still read); each half bounded at 90 s (`WBS_MHB_MAX_S`) and 20 consecutive failures, three thread dumps, one fresh lifetime per rep, A killed if `stopdaemon` does not return. Not a §9a change; the stall is recorded as an observation. | 2026-10-20, before run 1 | none |
| D2 | run 1, cluster tier, attempt 1 (00:25–01:22 EDT) | B3e step 3 (amended R2) | "`nodetool truncatehints` on A and wait for `du` to return to baseline" could not be done: `truncatehints` → `HintsStore.deleteAllHints()` (`HintsStore.java:167-181`) deletes only closed files in the dispatch queue, never the file the writer has open. Before 5 of 8 arms a file stayed: 1.02 · 2.05 · 1.05 · 1.05 MB before `s100k-r2`, `s1024k-r1`, `s1024k-r2`, `s8192k-r1` (≤ 0.1 % of 2 GiB) and **71.3 MB before `limit64-r2`**, which therefore started above the 64 MiB limit and stored no hint (not an independent repeat). The harness warned and went on. | Reset = drop the keyspace, **restart A** (B stays down; a clean stop closes the writer and a restarted A catalogues every file as closed), `truncatehints` until no `.hints` file is left (now a hard stop), a per-arm baseline (GC + 10 s), the per-host limit set again after the restart in the limit arms. One Byteman trace per A start (`traceOpen` truncates). Shakedown3 checked it. B2f–B3g unchanged. The cluster tier restarted from its beginning (01:33 EDT); attempt 1's logs kept as `~/stage4-logs/wbs/run1/cluster-attempt1-defectD2/` (not counted). | 2026-10-21 | none (not committed) |
| H1 | instrument check (cluster shakedown1) | harness | A node hung by `MAX_HINT_BUFFERS=1` outlived `stopdaemon`, which deletes the pid file first, so the stop helper lost the pid and left the JVM running. | The helper keeps the pid from the file and kills it after 120 s. | 2026-10-20 | — |
| H2 | instrument check (cluster shakedown2) | harness | `ps … \| grep '[C]assandraDaemon'` matched another session's ssh wait loop on `pc07` (its text contains the word), which would have failed the run's "no daemon" set-up check. | The check matches java processes running `org.apache.cassandra.service.CassandraDaemon` only. | 2026-10-21 | — |
| E1 | environment | B3a | The audit assumed two hosts (`pc57` + `pc50`), no longer in this experiment. | Both nodes on `pc07` on loopback: A = 127.0.0.2 (JMX 7102, seed, measured), B = 127.0.0.3 (JMX 7103, down for the hint arms), as `internode_max_message_size-inferMessageSize` ran on one host; `initial_token` set per node with `num_tokens: 1`. Does not change the design. | 2026-10-20 | none |

## 4. Run 1

**Scope:** unit tier B2 (all sizes, variants H, H64, B, D, twice; controls), cluster tier B3 (control with B up; 100 KiB · 1 MiB · 8 MiB × 2 with limit 0; per-host limit 64 MiB × 2 with 1 MiB; `MAX_HINT_BUFFERS=1` × 2 with 1 MiB, one lifetime each). 2 GiB of values per arm, the first GiB with 1 request in flight and the second with 8. This is how B3c's "single thread then 8 threads" was read. **Command log:** [`WRITE_BUFFER_SIZE-append-remaining--autonomous/run1/`](WRITE_BUFFER_SIZE-append-remaining--autonomous/run1/) (`chain.log`, `unit/`, `cluster/<lifetime>/summary.txt`, `arms.json`, merged samplers, trace excerpts, `analysis.txt`, `selfcheck.py`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, `test.out`; probe 1/1 passed, upstream `HintsReaderTest` 4/4; 279 checks, 278 ok, the 1 mismatch is the filed control, D1)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| H (`append(Hint)`), S = 1 · 100 · 255 KiB, 64 appends after 20 warm-ups, both reps | 56 B allocated per append at every S (min = max); capacity 262,144 throughout; `remaining` drops by `totalSize` and resets at each flush; the file grows only in whole buffers (2 entries at 100 KiB, 1 at 255 KiB) | `unit/test.out` |
| H, S = 257 KiB · 400 KiB · 600 KiB · 1 MiB · 4 MiB · 15 MiB, 8 appends, both reps | allocated per append = 263,360 · 409,792 · 614,592 · 1,049,280 · 4,195,008 · 15,729,344 B, i.e. `totalSize` + 126…638 B, the same at every append. ≥ S + 12 at every size. The buffer is left empty after every append and the file grows by exactly `totalSize` each time (direct write) | `unit/test.out` |
| Written in full (every variant, size, rep) | file after close = 42-B header + count × `totalSize` exactly (e.g. 15 MiB: 440,403,838 B = 28 × 15,728,707 + 42); `HintsReader` reads back every hint at its size (84 or 28) | `unit/summary.txt` |
| B (`append(ByteBuffer)`, heap entry) and D (direct entry, supplementary), every S incl. 15 MiB | 0 B allocated per append (max 0) | `unit/test.out` |
| H64 (64 KiB buffer), S = 100 KiB | 102,592 B per append (≥ S + 12) against 56 B with the 256 KiB buffer: the threshold follows the buffer's capacity | `unit/test.out` |
| Positive control `HintsBuffer.create(1 MiB)` | 600 KiB refused, "Hint of 614400 bytes is too large - the maximum size is 524288"; 100 KiB admitted; 524,276 B (capacity/2 − 12) admitted, 524,277 refused. The filed 400 KiB check admitted, as derived in D1 | `unit/summary.txt` |
| Side observation | first large H append per size raised the JVM direct pool by 0.26 · 0.79 · 3.1 · 11.5 MB in rep 1, by 0 in rep 2 | `unit/test.out` (`directUsedDelta`) |

**Cluster tier** (`run1/cluster/*/summary.txt`, `analysis.txt`; A restarted before each arm, D2; baseline per arm after GC, 47.8–63.9 MiB direct with 1 slab already made by the start-up periodic flush)

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| limit 0, B up | control | hints / TotalHints | 256 × 1 MiB written, all ok; A hints 0 B, TotalHints +0 | `main/summary.txt` |
| limit 0, MHB 3 | 100 KiB r1 / r2 | hints on disk at the end | 2,148,796,614 B both (1.0007 × values), 17 files, largest 134,235,742 B | `main/summary.txt`, `main/hints-merged.csv` |
| limit 0, MHB 3 | 1 MiB r1 / r2 | hints on disk | 2,147,627,680 B both (1.0001 ×), 16 files, largest 134,226,730 B | same |
| limit 0, MHB 3 | 8 MiB r1 / r2 | hints on disk | 2,147,502,496 B both (1.0000 ×), 16 files, largest 134,218,906 B | same |
| limit 0, MHB 3 | every limit-0 arm | hinted and stored | `Hints_created` = requests written = entries appended (20,970 · 2,048 · 256); 1 MiB and 8 MiB: every entry > 256 KiB, every one written to the channel directly (`wr buf=false` = written); 100 KiB: none bypasses | `main/summary.txt`, `main/trace-excerpt.txt` |
| limit 0, MHB 3 | every limit-0 arm | hint slabs (create trace) | 3 slabs by arm end (2 created in the arm), attributable 3 × 32 MiB + 256 KiB = 96.25 MiB at every size; `waiting` lines 15 · 16 · 23 · 22 · 46 · 44 (writers held at the 3-buffer cap under natural load) | `main/trace-excerpt.txt` |
| limit 0, MHB 3 | 100 KiB / 1 MiB / 8 MiB | direct pool peak over the arm baseline | +72.6 · +72.6 / +73.1 · +83.2 / +145.2 · +153.2 MiB; heap peak 1.67–1.88 GiB of 2 GiB | `main/summary.txt` |
| limit 64 MiB (live, read back) | r1 / r2 | disk, refusals | end 75,502,554 / 81,794,430 B (72 / 78 MiB), 0 B growth in the last 40 % of the window; 1,976 / 1,970 refusals, first operand 75,502,554 / 81,794,430 > 67,108,864; 72 / 78 hints stored | `main/summary.txt`, `main/trace-excerpt.txt` |
| limit 64 MiB | r1 / r2 | client writes | 2,040 / 2,048 succeeded in each; 8 `WriteTimeout`s each at the start of the 8-in-flight half (06:15:03, 06:18:56 UTC), while A completed memtable flushes every ~2 s | `main/summary.txt`, `main/A-system.log` (node) |
| MHB 1 | lifetime 1 / 2 | slabs, direct, hints | 1 slab (attributable 32.25 MiB); direct peak +0.07 / +0.08 MiB over baseline; 31 hints (32,508,068 B) then nothing | `mhb1-*/summary.txt` |
| MHB 1 | lifetime 1 / 2 | writer state | 1 `waiting` line; 3 thread dumps each: one `MutationStage` thread parked in `LinkedBlockingQueue.take` at `HintsBufferPool.switchCurrentBuffer(HintsBufferPool.java:118)`, all 32 `MutationStage` threads in `HintsBufferPool` frames; 63 writes ok, then 20 consecutive `WriteTimeout`s stopped the writer; `stopdaemon` did not return in 120 s, A killed | `mhb1-*/summary.txt`, `mhb1-1/thread-dump-excerpt.txt` |
| cross-arm | analysis | X1–X4 | disk ratios within 0.07 % across sizes; limit arms 78 MiB vs 2,048 MiB; MHB 1 delta 0.08 MiB < default 153.16 MiB; slabs 1 < 3 | `analysis.txt` |

Run-script totals: main 44 yes / 2 no (both "writes still succeed" in the limit arms), each `mhb1` 1/1, analysis 4/4. Attempt 1 (D2, not counted) gave the same figures within 0.1 % except `limit64-r2`.

### 4.2 Conclusion and logic

1. **Validity.** The unit tier ran every size and variant twice, 20 warm-ups discarded [observed: `unit/test.out`]. The cluster hint arms reached 2 GiB of hints per arm, 16 × the 128 MiB file size and 64 × a slab. B was down for every arm and hints were really written (`Hints_created` = writes; control 0) [observed: `main/summary.txt`]. B3a's settings were in force: yaml tail and command-line checks in `summary.txt` (`-Xmx2G`, `MaxDirectMemorySize=1g`, NMT, Byteman, 128 MiB files, 1000 ms flush) [observed]. The arms started clean after D2's fix (no `.hints` file after each reset) [observed: `reset` lines]. Valid.
2. **Readings.** (a) The direct-pool delta grows with the value size (+73 → +153 MiB) while the slab count is 3 everywhere. The excess over 64 MiB of slabs 2–3 is not attributed: other direct users, possibly netty/networking buffers for 8 MiB client frames [inferred: the create trace shows no further slab, and B3d named this attribution as not directly observable]. (b) Writes timed out in some arms (limit-0: 8 at 1 MiB r1, 32/28 at 8 MiB). Every one was still hinted (`Hints_created` = written) [observed]; they are local replica-write timeouts at 2 s [inferred: flush timing]. (c) `MAX_HINT_BUFFERS=1` stalled hint writing for good, as noted from the source before the run (N1) [observed: dumps].
3. **Matched rows.** Unit, B2g row 1, "S >= 257 KiB written in full, heap delta >= S in `append(Hint)`, ~0 in `append(ByteBuffer)`": every S ≥ 257 KiB was written and read back in full, allocated `totalSize` + ≤ 638 B per append, and `append(ByteBuffer)` allocated 0. Also row 2, "same plus threshold moves with the 64 KiB variant": 100 KiB goes from 56 B to 102,592 B. Cluster, B3g row 1, "Hint dir grows to ~2 GiB in all three sizes; direct pool peak is tens of MiB, tied to `MAX_HINT_BUFFERS`": 2.0007–2.0000 GiB at all three sizes; the attributable direct memory is 96.25 MiB with 3 buffers against 32.25 MiB with 1; the measured deltas are tens of MiB vs 0.08 MiB. B3g row 2 (positive control): the disk stops at 72/78 MiB with the limit on, while limit 0 continues to 2,048 MiB.
4. **Excluded rows.** Unit: "usage ≤ 262144 for all S" — 15 MiB hints are 15,728,707 B each; "S ≥ 257 KiB throws or truncates" — none threw, every file is exact; "heap delta not measurable" — 15.7 MB measured; "positive control does not stop" — the corrected control refuses at capacity/2 + 1. The filed 400 KiB size cannot refuse by arithmetic (D1), so it is not a reading against the harness. Cluster: "direct pool within ~1 MiB of baseline and not changing with `MAX_HINT_BUFFERS`" — +72.6 MiB or more with 3, +0.08 with 1, and the slab count follows the property; "1 MiB / 8 MiB hints missing" — all 2,048 / 256 stored, `Hints_created` equal; "neither disk growth nor direct change, or the limit does not bind" — both moved; R1 "`MAX_HINT_BUFFERS=1` delta not lower" — 0.08 < 72.6 MiB. No Refuted row fits.
5. **Observed vs. inferred.** Inferred: the cause of the 8 limit-arm timeouts (memtable flush backpressure); the attribution of the non-slab direct growth at 8 MiB; the unit side observation's cause (the JDK's per-thread temporary direct buffer for `FileChannel.write` of a heap buffer). None of the three is needed for the matched rows.
6. **Deviations and gaps.** E1 (one host); D1 (control size corrected in the harness); D2 (reset by restart of A, cluster tier restarted); N1 (MHB 1 arm bounded, the writer stalls); B3c read as halves at 1 and 8 in flight; `auto_snapshot` kept, so `clearsnapshot --all` after each drop. **One sub-prediction missed:** B3f's "writes still succeed at CL=ONE" in the limit arms holds for 2,040 of 2,048 writes, not all, in both reps. The limit's own effect (refusals, plateau) is unaffected.
7. **Core question.** Usage does not follow `WRITE_BUFFER_SIZE`. A hint of up to 15 MiB (64×) passes the 256 KiB comparison and is written in full: in the test-only overload it costs a heap buffer of its own size, and in the production overload nothing [parts 3, 4]. On the cluster, 2 GiB of 100 KiB–8 MiB hints reach disk in full. Hint memory follows the slab count (`MAX_HINT_BUFFERS`: 96.25 vs 32.25 MiB), and disk stops only at `max_hints_size_per_host` [part 3]. The constant is a flush-batching size and caps nothing.

**Conclusion (one line):** unit B2g rows 1–2, cluster B3g rows 1–2 — **Confirmed** (claim: the constant does not cap); one sub-prediction missed (8/2048 write timeouts per limit arm).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Independent script [`run1/selfcheck.py`](WRITE_BUFFER_SIZE-append-remaining--autonomous/run1/selfcheck.py) re-parses `test.out`'s per-append lines and the cluster's per-start traces, sampler files and key logs. It uses `arms.json` only for the time windows and trace names. Output [`run1/selfcheck.txt`](WRITE_BUFFER_SIZE-append-remaining--autonomous/run1/selfcheck.txt): **346 ok, 2 FAIL** — exactly the missed sub-prediction (2,040/2,048 in each limit arm). Its own figures agree with the run script's for every arm: written, appended, hints at end, slabs, direct peak.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `reset` lines show no file before any counted arm; `Hints_created` = written in every limit-0 arm (selfcheck recount from `keys-*.csv` and `app` lines) |
| 2. Readings | yes | 8 MiB direct growth and timeouts re-read in `samples-jmx-*.csv` and keys; flush times in `A-system.log` |
| 3. Matched row | yes | unit: per-append allocations recomputed (min ≥ S + 12 above the buffer, max < 8 KiB below it and for `append(ByteBuffer)`), file steps = `totalSize`; cluster: disk ratios 1.0007/1.0001/1.0000, slabs 3 vs 1 from the raw traces |
| 4. Excluded rows | yes | recomputed: no throw, read-back complete, MHB-1 delta 0.08 MiB, limit arms ≤ 78 MiB, refusals with operand > limit |
| 5. Observed vs. inferred | yes | the three inferences are not used by the matched rows |
| 6. Deviations and gaps | yes | D1, D2, N1, E1 and the halves reading recorded in §3/§4.2; the missed sub-prediction is the selfcheck's only failure |
| 7. Core question | yes | the steps follow B1's two parts: (a) unit, (b) cluster memory and disk, each with its positive control moving |

### 5.2 Run 2?

**No** — decided 2026-10-21. The conclusion rests on observed readings: exact byte counts, the create trace, and thread dumps. The self-check settled every part from run 1's files. The result confirms the file's own negative estimate; it neither refutes the case nor confirms a bypass. The one missed sub-prediction is explained and does not touch the matched rows.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2); §7 left out.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its
date and reason.

**Stage-3 estimate:** negative (the file's Estimate line; ground: a hard-coded flush-batching constant, not a limit).

**Claim tested:** B1 — "`WRITE_BUFFER_SIZE` does not cap hint memory or disk: (a) a hint larger than 256 KiB is written in full and costs extra heap equal to its size in the `append(Hint)` overload (none extra in the production overload), and (b) node-level direct/heap memory attributable to hint writing does not stay within 256 KiB plus a constant and is governed instead by the `HintsBuffer` slabs and hint size, while disk growth is stopped only by `max_hints_size_per_host`." "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g rows 1 and 2 (hints of 257 KiB–15 MiB written in full; `append(Hint)` allocates `totalSize` + ≤ 638 B, `append(ByteBuffer)` 0 B; the threshold moves to 64 KiB with a 64 KiB buffer) | does not cap | run 1 + self-check | 2026-10-21 |
| Cluster | **Confirmed** — B3g rows 1 and 2 (2 GiB of hints on disk at 100 KiB, 1 MiB and 8 MiB alike, ratio 1.0000–1.0007; hint memory 3 slabs = 96.25 MiB, 1 slab = 32.25 MiB with `MAX_HINT_BUFFERS=1`; disk stops at 72/78 MiB only with the 64 MiB per-host limit); one sub-prediction missed (8/2048 write timeouts in each limit arm) | does not cap | run 1 + self-check | 2026-10-21 |

**Positive control:** unit — `HintsBuffer.allocate` refuses at `capacity/2 + 1` (524,277 B) and at 600 KiB while the same sizes pass the write buffer. The filed 400 KiB size was below the limit (D1). Cluster, disk — `max_hints_size_per_host` 64 MiB stopped the disk at 72/78 MiB, with 1,976/1,970 refusals whose operand was above the limit, while the same workload at 0 reached 2,048 MiB. Cluster, memory — `MAX_HINT_BUFFERS=1` held hint memory at one slab (+0.08 MiB over the baseline against +72.6 to +153 MiB) and, as derived from the source before the run (N1), stalled every hint writer for good.

**Findings beyond the claim (no §9a row):** (1) `nodetool truncatehints` never deletes the hints file the writer has open (`HintsStore.deleteAllHints`, `HintsStore.java:167-181`). (2) `MAX_HINT_BUFFERS=1` stalls the whole `MutationStage` (32 threads), and the node then does not stop on `stopdaemon`. (3) With the default 3 buffers, writers reached the cap and waited 15–46 times per 2 GiB arm under natural load.

**Feedback filed:** the case file's section D updated 2026-10-21 (only section D changed; not committed). New sha256 of the whole case file: `4a4b3b8680dbe3e5adefa0ebf6c9ee44e5504df01b5c899a4a5bc67a20ea20d6` (was `55bf043e…` at the freeze). No other section amended.
