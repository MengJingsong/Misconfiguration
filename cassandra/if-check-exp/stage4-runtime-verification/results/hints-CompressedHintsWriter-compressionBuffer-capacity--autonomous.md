# hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous — stage-4 results  <!-- file: results/hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous`](../../stage3-ai-deep-read/cases/hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous.md)
>
> **Status:** **Run 1 and self-check done 2026-10-25 (no run 2) — unit Confirmed (B2g row 1); cluster: Refuted as worded by one lifetime (`F1`, B3g row 2), Confirmed in the other eight lifetimes and the positive control (B3g row 1 and the last row). Effect: does not cap (the buffer size); `max_hints_file_size` ends a buffer's life but does not bound it.**
>
> **Outcome class:** true negative — stage-3 estimate `negative` against the stage-4 effect `does not cap`; the F1 sub-prediction missed (§8 says how, and why the class is not changed by it)
>
> **Agent:** guided / autonomous (the suffix of the case-file stem). For an autonomous
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
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments: `374f9e0c4b52181e22503a70149cc3dd885fb9c9a867b0bb307943352a6734bb` (`sha256sum`, 2026-10-25, before any run-1 reading; an earlier freeze, `03e4458535…`, differed only in the JMX ports of B3 amendment 2, changed after shakedown 3 found 7214 in use by another agent's node; the file as written by stage 3 was `118aa1e81fd572e7efaadaac718a577181755d797f353340328ce8d5729bfd99`). Not committed yet (the orchestrator commits; HEAD of the repository `f33e621`). **Frozen prediction and conclusion tables:** the text of B2f, B2g, B3f and B3g (from `**B2f.` up to `**B2h.`, and from `**B3f.` up to `**B3h.`, both heading lines of the next paragraph excluded, concatenated) has sha256 `d46dfb1b4bbf4a9823342bea9bf39094862c18f1e84dd8e538dd66ec7d9dffa7` (28 lines, 3,357 bytes), computed before any reading. |
| **Harness** | [`harness/hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous/`](../harness/hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous/README.md) — written 2026-10-25 after the audit, before any reading (list and checks in its README). Not committed. |
| **Tiers and values** | Unit (B2): `CompressedHintsWriter` driven directly, S = 100 B · 200 KiB · 256 KiB · 1 MiB · 4 MiB · 16 MiB, ascending then descending, `max_hints_file_size` 1 MiB / 128 MiB, N = 1 · 4 · 16 writers, uncompressed reference, per-hint cap at the `HintsBuffer`, slab positive control. Cluster (B3): node A (127.0.14.1) with B (127.0.14.2) down (and C, 127.0.14.3, in `P2`): lifetimes `S`, `US`, `D1`, `D2`, `F1`, `H1`, `U`, `P2`, `M128` (B3 amendment, items 1-5). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-25 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". Sections are those of the autonomous file (B1 = hypothesis; B2a-B2e / B3a-B3e = test and logic; B2f / B3f = prediction; B2g / B3g = conclusions table; B2h / B3h = controls).

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: the off-heap `compressionBuffer` capacity in bytes (`CompressedHintsWriter.java:55`); constraint = none declared, nearest are the per-hint cap (half the slab) and the hint-file knobs. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | There is no knob for the buffer, so the design varies the driver (hint size S, six values; N writers, three values) and the two hint-file knobs (B2b, B3b); `max_hints_file_size` has two values (default and 1 MiB), `max_hints_size_per_host` two (0 and 1 MiB). The two-value knobs are the ones whose claim is "no effect", with the default as one of the two; the three-value sweep is on S. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d/B3d: the `java.nio` direct pool (the real resource) plus the buffer's own `capacity()`. B3d says one buffer is not observable in the cluster: the amendment adds a Byteman capacity trace (B3 amendment 3). |
| A. Core question | usage driven to the limit and past it | Partly | Unit: S = 16 MiB is the cap (record, 16,777,216 B) and the 17 MiB / 16,777,205 B hint is refused by the `HintsBuffer` (B2 amendment 1). Cluster: V = 8 MiB is half the cap; reaching the cap itself needs a hint of 16,777,204 B payload, i.e. a 16 MiB mutation, which `max_mutation_size` refuses at about 16 MiB, so the cluster tier stops at 8 MiB by design (B3b(4)). Left as filed; the unit tier covers the cap. |
| B. Logic | each step says what it establishes | Met | B2e / B3e steps each say what they record; B3e step 8 contradicted B3f on the control (fixed, B3 amendment 5). |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f: exact formula within ±64 B, non-decreasing, N x capacity within 10 %; B3f: 8.0-8.1 MiB per peer, ≤ 0.3 MiB for 1 KiB, "about" made decidable by the 2 MiB band (B3 amendment 4). Arithmetic re-done: 4 + (S + S/255 + 16) + 8 = 128 B (100 B), 263,200 B (256 KiB), 1,052,716 B (1 MiB), 4,210,780 B (4 MiB), 8,421,532 B (8 MiB, 8.031 MiB), 16,843,037 B (16 MiB, 16.063 MiB); N = 16 x 4 MiB = 67.4 MB; N = 16 x 16 MiB = 257 MiB (the write-up's figures hold). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | Rows cover file-size-dependent, shrinking, chunked/capped, reading error and control failure. Missing: an `H1` lifetime in which no 8 MiB hint reaches the writer (the host-size knob stops hints, so no buffer is allocated and X is near 0); not a row of B3g, read as "Not confirmed" for that lifetime (B3 amendment 1) and recorded as a recommendation for stage 3. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met (negative claim) | For this negative claim: "no knob moves the buffer" needs the buffer to be measured to have followed the data (B2f/B3f) and the control to move (B2g/B3g last row). There is no disallow branch (A3: no limit-reached branch). |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: uncompressed arm, compressible vs random data, GC before reading, idle baseline, repeat run. |
| C. Specific | a human can follow it from the intro and §9a | Met | B1 and the table of A1-A3 are clear. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | B2a/B3a give directories and flags but not the yaml lines, the client, the sampler or the ports; supplied by the harness (README) and the B3 amendment (ports, timeouts, lifetimes). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | S and L sizes are exact; "about", "2 min" and the small-V count were not decidable: fixed by the B3 amendment (marks, band, workloads). B3e step 9's `pkill -f` is not allowed on the shared node (amendment 6). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | JDK 11, Ant, Byteman 4.0.20 and the bundled driver are on the node; the harness is the `max_mutation_size ... slabCapacity` one adapted (client, Jmx, node-yaml, runner). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 200 x 8 MiB = 1.6 GB of hints on local disk (40 GB free); S is 200 MB; the hint-file knob F1 writes a file per hint; the direct pool peak is bounded (3 slabs x 32 MiB, up to 3 x 128 MiB in `M128`, plus buffers) against `MaxDirectMemorySize` 2 GiB. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met after two corrections | Checked: `CompressedHintsWriter.java:39,51,53-56,60,68`; `HintsWriter.java:157-161,200-222`; `HintsWriteExecutor.java:50,60,228-229,239-248`; `HintsStore.java:295-300`; `HintsService.java:79,110,117-121`; `HintsBuffer.java:58,150-152`; `HintsBufferPool.java:41`; `LZ4Compressor.java:113-116,240-243`; `Config.java:406-407,445-450`; `DatabaseDescriptor.java:898-899,2827-2830,3723-3731`; `CassandraRelevantProperties.java:351`; `StorageProxy.java:2488`; yaml line 125. Wrong: `HintsWriter.java:86-89` (is 88-89) and `HintsStore.java:325-333` (is 322-330); both corrected in the case file. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | State the cap exactly: record ≤ `max(max_mutation_size, 16 MiB)` = 16,777,216 B, payload ≤ 16,777,204 B, largest buffer 16,843,037 B | Applied 2026-10-25 (case file A3 note, B2 amendment 1) | A hint is 12 B larger than its payload; the cap does not fall below 16 MiB. |
| 2 | Separate lifetimes for the small and the 8 MiB workloads | Applied 2026-10-25 (B3 amendment 1) | A grow-only buffer keeps the high-water mark. |
| 3 | Replace the contradictory slab positive-control prediction (2x vs 3 x 128 MiB) by a relation the trace can check | Applied 2026-10-25 (B3f, B3g, B3 amendment 5) | B3e and B3f disagreed; the number of slabs created is a trace count. |
| 4 | Make "about" decidable: marks, slab correction, 2 MiB band | Applied 2026-10-25 (B3 amendment 4) | B3f's tolerances were not stated. |
| 5 | Per-writer capacity trace (Byteman) | Applied 2026-10-25 (B3 amendment 3) | The pool total cannot separate one writer's buffer from other direct memory. |
| 6 | Add a B3g row for "no 8 MiB hint reached the writer" (the `max_hints_size_per_host` lifetime) | left for stage 3 | It decides nothing about the claim; read as Not confirmed for that lifetime. |
| 7 | B3 reaches only 8 MiB; the 16 MiB end needs the unit tier or a `max_mutation_size` above 16 MiB with a 16 MiB hint | left for stage 3 | The cluster tier cannot make a 16 MiB hint at the default `max_mutation_size`. |

**Agreement criteria** — not needed: run 2 not done (§5.2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-25 (unit 20:04-20:06 EDT; cluster 20:10-20:48 EDT) | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (the local host; 40 cores, 251 GiB); shared with other stage-4 agents (their nodes ran on 127.0.12.x and 127.0.33.x) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18) | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-hw`, `copy-source.sh` from repository commit `f33e621` (the working tree has this batch's uncommitted files); local baseline `4632395`, tag `cassandra-5.0.9`; `ant build-test` 1 min 10 s, `BUILD SUCCESSFUL`. Test files copied in by `unit-run.sh` (untracked). | |
| Case-file commit / harness commit | the case file as amended is uncommitted (sha256 in §1); harness uncommitted | |
| Storage for node data | local disk `/dev/sda3` (ext, 63 GB, about 38 GB free at start); `~/s4-hw-data/{A,B,C}`, wiped before each lifetime and the data directories removed after it | |
| Full logs (path, outside the repo) | `~/s4-hw-logs/run1/` on `pc07` (`unit/`, `cluster/<arm>/` with `hw.trace`, `samples.csv`, `session.log`, `phases.json`); shakedowns in `~/s4-hw-logs/shakedown{,2,3,4}/` | |

Deviations from the assigned ports (recorded in the case file's B3 amendment 2 and the harness README, finding 3): JMX 7814 / 7815 / 7816 instead of 7214 (and B's 7614, C's 7714), because 7214 is used by another agent's node and a `nodetool drain` from that agent reached this harness's node A during shakedown 3. Byteman 9114, native 9146 and storage 7014 as assigned; loopback 127.0.14.1-3 (the third only in `P2`).

## 3. Runbook defects

No step of B2a-B2e or B3a-B3e failed to run as written in run 1. Defects found in the harness and in B3's text during the audit and the four shakedowns (before any run-1 reading) and fixed:

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B3e step 8 vs B3f | positive-control prediction disagreed (2 x vs 3 x 128 MiB) | B3 amendment 5, B3f/B3g wording | 2026-10-25 | uncommitted |
| 2 | audit | B3e steps 3-4 | small and 8 MiB workloads in one lifetime would hide the grow-only buffer | one workload per lifetime (amendment 1) | 2026-10-25 | uncommitted |
| 3 | shakedown 1 | B2d (extra check) | heap compression buffer still moves the direct pool (JDK temporary direct buffer for `FileChannel.write`) | pool delta printed as information for Deflate | 2026-10-25 | harness only |
| 4 | shakedown 1 | B3d | `system_views.settings` renders `hints_compression` as null; the runner read the trace after node stop (shutdown closes writers) | compression read from the trace; trace read before stop | 2026-10-25 | harness only |
| 5 | shakedown 2 | B3a / B3b(5) | C died at start when started while B was joining | start B, wait UN, then C | 2026-10-25 | harness only |
| 6 | shakedown 3 | assigned JMX port | 7214 in use by another agent's node; its `drain` hit this node A | JMX 7814-7816 (amendment 2) | 2026-10-25 | uncommitted |

## 4. Run 1

**Scope:** unit tier (all of B2); cluster tier: nine lifetimes `US`, `S`, `U`, `D1`, `D2`, `F1`, `H1`, `P2`, `M128` (B3 amendment 1). One run of each (`D1`/`D2` are the repeat). **Command log:** `hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous/run1/` (`unit/summary.txt`, `unit/harness.out`, `cluster/<arm>/summary.txt`, `run1-chain.log`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`unit/harness.out`; `unit/summary.txt`: `HintsCompressionTest` 4 tests, `HintsBufferTest` 2 tests and the probe all pass; 19 checks, 0 MISMATCH)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| `lz4-bound`: lz4-java `maxCompressedLength(n) == n + n/255 + 16` and `initialCompressedBufferLength(n) == 4 + that`, n = 0 ... 16 MiB | ok | `unit/harness.out` |
| `asc-<S>`, fresh LZ4 writer, one record of S bytes: capacity 128 · 205,631 · 263,200 · 1,052,716 · 4,210,780 · 16,843,037 B for S = 100 B · 200 KiB · 256 KiB · 1 MiB · 4 MiB · 16 MiB | each equals `4 + (S + S/255 + 16) + 8` exactly (diff 0), direct | `unit/harness.out` |
| `seq`: one writer, S 100 B, 1 MiB, 16 MiB, then 1 MiB, 100 B, 200 KiB | capacities 128, 1,052,716, 16,843,037, 16,843,037, 16,843,037, 16,843,037: never shrinks | `unit/harness.out` |
| `filesize`: `max_hints_file_size` 1 MiB and 128 MiB | 4,210,780 and 16,843,037 B in both | `unit/harness.out` |
| `n-1`, `n-4`, `n-16`: N writers holding a 4 MiB record | pool delta 4,210,780 · 16,843,120 · 67,372,480 B = N x 4,210,780 (ratio 1.0000, count +N) | `unit/harness.out` |
| `uncompressed`: plain `HintsWriter`, 4 MiB record | no `compressionBuffer` field, pool delta 0 | `unit/harness.out` |
| `compressible`: 4 MiB of zeros | capacity 4,210,780 (same as random) | `unit/harness.out` |
| `deflate` (extra) | buffer on heap; LZ4 buffer direct | `unit/harness.out` |
| `cap-boundary`: `HintsBuffer.create(32 MiB)` | `allocate(16,777,204)` accepted; `allocate(16,777,205)` and `allocate(17 MiB)` throw "Hint of N bytes is too large - the maximum size is 16777216" | `unit/harness.out` |
| `cap-formula`: `max(2 x max_mutation_size, 32 MiB) / 2` | 16 · 16 · 16 · 16 · 32 · 64 MiB for max_mutation_size 1 · 4 · 8 · 16 · 32 · 64 MiB | `unit/harness.out` |
| `slab-control-32`, `-128` (positive control): pool around `HintsBuffer.create(C)` | +33,554,432 and +134,217,728 B exactly, count +1, `free()` returns the same | `unit/harness.out` |

**Cluster tier** — one row per lifetime. `dPool` = A's java.nio direct `MemoryUsed` after the final `GC.run` x 2 minus the baseline; `Corr` = slabs created after the baseline x slab size; `X` = (dPool − Corr) minus the control's (`U` for the L lifetimes, `US` for `S`). "Trace" = the Byteman capacity trace (`hw.trace`), the exact capacity of each writer's buffer.

| Lifetime (workload) | Observable | Reading | Evidence (file) |
|---|---|---|---|
| `US` (S, no compression, control) | CompressedHintsWriter lines; dPool, Corr | 0 opened, 0 `writeBuffer`; dPool 32.29 MiB = Corr 32 MiB + 0.29 | `cluster/US/summary.txt`, `hw.trace.excerpt` |
| `S` (200,000 x 1 KiB, LZ4) | trace capacity; X | 2 writers (a file roll at 128 MiB), largest capacity 262,279 B (= exp(261,227), below exp(256 KiB) = 263,200), live 262,279 B; X = 0.12 MiB | `cluster/S/summary.txt`, `selfcheck.txt` |
| `U` (200 x 8 MiB, no compression, control) | CompressedHintsWriter lines; dPool, Corr; hints | 0 opened, 0 `writeBuffer`; dPool 64.04 MiB = Corr 64.00 + 0.04; 200 hints, hints dir 1,677.7 MB | `cluster/U/summary.txt` |
| `D1` (200 x 8 MiB, LZ4, defaults) | trace; X | 13 writers (files of 128 MiB), every buffer 8,421,599 B = exp(8,388,675) (grow-only, exact), live at the end 1 writer = 8,421,599 B; X = 8.04 MiB | `cluster/D1/summary.txt`, `selfcheck.txt` |
| `D2` (repeat of `D1`) | same | same numbers; X = 8.04 MiB (D1 vs D2 differ by 0.00 MiB) | `cluster/D2/summary.txt` |
| `F1` (`max_hints_file_size: 1MiB`) | trace; X; peak | 200 writers (a new file and writer per hint), each buffer 8,421,599 B (2 `writeBuffer` calls each: the empty aggregation buffer, then the hint), none live at the end; **X = 0.01 MiB**; peak direct delta 362.2 MiB (D1 136.1, D2 105.1, U 112.1) | `cluster/F1/summary.txt`, `cluster/F1/samples.csv` |
| `H1` (`max_hints_size_per_host: 1MiB`) | hints stored; trace; X | 11 of 200 hints stored (hints dir 92.6 MB), 1 writer, buffer 8,421,599 B (live); X = 8.04 MiB | `cluster/H1/summary.txt` |
| `P2` (two peers down, RF 3) | trace; X | 26 writers (13 per peer), live 2 = 16,843,198 B; X = 16.07 MiB | `cluster/P2/summary.txt` |
| `M128` (`commitlog_segment_size: 128MiB`, slabs 128 MiB) | slabs; dPool, Corr; X | slabs created after the baseline 2 x 134,217,728 B, dPool 264.09 MiB, Corr 256.00; dPool(M128) − dPool(D1) = 192.00 MiB = Corr(M128) − Corr(D1); buffer X = 8.04 MiB | `cluster/M128/summary.txt`, `cluster/analysis-summary.txt` |

Validity per lifetime (every `EXPECTED:` line in `cluster/<arm>/summary.txt`): the peer(s) down for the whole workload, 200 of 200 (200,000 of 200,000 in S) acknowledged with no error, TotalHints +200 (+400 in `P2`, +200,000 in S, +11 in `H1`), hints directory about 1.68 GB (3.37 GB in `P2`). 0 ERROR lines in node A's log in every lifetime. Per-lifetime `EXPECTED` lines (yes / no): `US` 7/0, `S` 10/0, `U` 7/0, `D1` 11/0, `D2` 11/0, `F1` 11/1, `H1` 8/0, `P2` 11/0, `M128` 12/0; `analyze` 8/1. The two `NO` lines are both `F1`: the runner's "live writers 0 >= peers 1" (a check that did not apply to a lifetime in which every writer is closed after its hint) and "same increment as the default" (B3f's F1 sentence, the prediction that missed).

### 4.2 Conclusion and logic

1. **Validity.** The run was valid. [observed: `cluster/<arm>/summary.txt`] workload acknowledged in full, peers DN throughout, hints produced in the expected number (except `H1`, where the knob under test stops them, 11 stored), `CompressedHintsWriter` active in every LZ4 lifetime and absent in `U` and `US`. The "limit" here is the per-hint cap: the unit tier reaches it (16 MiB record accepted by the writer, 16,777,205 B hint refused by the `HintsBuffer`); the cluster tier reaches half of it (8 MiB hints), as the audit recorded. The positive control moved (below). The uncompressed controls carry every other direct allocation, so the compression buffer is read as a difference. [observed: `unit/harness.out`, `cluster/M128/summary.txt`]
2. **Readings.** Two points. (a) `F1` is the outlier: its post-GC increment is 0.01 MiB against 8.04 MiB in every other compressed lifetime, and its peak direct delta is 362 MiB against 105-136 MiB in `D1`/`D2`: with a 1 MiB file limit `HintsWriteExecutor.flushInternal` returns false after every 8 MiB hint (`session.position() >= maxHintsFileSize`, `HintsWriteExecutor.java:247-248`), `closeWriter()` runs at once (lines 228-229), and the next hint opens a new writer with a new compression buffer. 200 buffers of 8.03 MiB were allocated, each released at a later GC. [observed: `cluster/F1/summary.txt`, `hw.trace.excerpt`, `samples.csv`; the reason is inferred from the source] (b) `H1` stored 11 hints, so the writer got its 8.03 MiB buffer from the first flush and then received nothing. [observed: `cluster/H1/summary.txt`]
3. **Matched row.** Unit: B2g row 1, "Capacity tracks the compressor bound of the largest S, equal across file-size settings, never shrinks, N-fold sum": `asc-*` exact, `filesize` equal, `seq` never shrinks, `n-*` ratio 1.0000 [observed: `unit/harness.out`]; the 17 MiB row (`cap-boundary`) and the positive-control row (`slab-control-*`) also hold. Cluster: B3g row 1 for `D1`, `D2`, `H1`, `P2` ("about 1 x largest hint x peers, same for both file-size/host-size settings, none uncompressed" — except the file-size setting, see 4) and the last positive-control row for `M128`; row 2 ("Increment shrinks when max_hints_file_size or max_hints_size_per_host is lowered → Claim refuted") as worded for `F1`. S: X = 0.12 MiB <= 0.3 MiB + 2 MiB. [observed: `cluster/analysis-summary.txt`, `selfcheck.txt`]
4. **Excluded rows.** "Capacity shrinks on descending S": `seq` no. "Capacity constant at 256 KiB+ regardless of S": no, 1 MiB, 4 MiB, 16 MiB give their bound. "Increment bounded below 8 MiB at V = 8 MiB": no, 8,421,599 B in every LZ4 lifetime. "Increment not seen / positive control does not move": the increment is seen (8.04 and 16.07 MiB) and the positive control moved by 192.00 MiB. "Only the per-hint cap bounds it": consistent (unit). The one row that is **not** excluded is B3g row 2, for `F1` only: the post-GC increment fell from 8.04 to 0.01 MiB when `max_hints_file_size` was lowered. It is not excluded and the verdict records it; what it means is in part 7. [observed: `unit/harness.out`, `cluster/*/summary.txt`]
5. **Observed vs. inferred.** Inferred and relied on: (i) the pool difference is the compression buffer, from the equality of the trace's live capacity sum with X in `D1`, `D2`, `H1`, `P2`, `M128` (8.03 vs 8.04 MiB, 16.06 vs 16.07 MiB) [observed: `selfcheck.txt`]; (ii) in `F1` the zero increment is the closure of every writer (`closed` lines 200, live 0 at the end mark) and not a smaller buffer: each writer's capacity is 8,421,599 B [observed: `phases.json`: 200 writers, one capacity]; (iii) "the knob closes the writer" from `HintsWriteExecutor.java:228-229,247-248` [inferred from the source, matched by 200 `opened`/`closed` pairs].
6. **Deviations and gaps.** The cluster tier reaches 8 MiB hints, not 16 MiB (audit rating "Partly", recommendation 7). `hints_compression` could not be read back from `system_views.settings` (null); compression was shown by the trace. JMX ports differ from the assignment. The runner's one `NO` in `F1`'s own summary is explained above. `P2` and `M128` have one lifetime each; `D1`/`D2` agree to 0.00 MiB, which bounds the noise of this method for the others.
7. **Core question.** The off-heap buffer follows the largest write handed to the writer (1.0 x the LZ4 bound, exact to the byte at six sizes and in 200 hint writes), grows only, is held once per open writer (16.07 MiB for two peers) and is not bounded by `max_hints_size_per_host` (H1: same 8.04 MiB, with 11 hints stored) or by `max_hints_file_size` (F1: every writer's buffer is the same 8,421,599 B; the unit tier shows equal capacities for 1 MiB and 128 MiB). The only ceiling is the per-hint cap, 16,777,216 B for a record (half the 32 MiB slab; it does not fall below 16 MiB), which the `HintsBuffer` enforces before the writer is reached (unit `cap-boundary`); the positive control moved exactly with the slab size (192 MiB for 96 MiB x 2 slabs), so the instruments could show a cap that binds. The file-size knob does change the memory in one respect: it ends each buffer's life (a closed writer's buffer is released at the next GC), so with 1 MiB files the live increment at rest is 0 while the peak is 3 x larger (362 MiB) because 200 buffers are allocated instead of 13; that is a churn effect of closing writers, not a bound on the buffer. Steps follow the audited logic: unit sizes → cluster trace → pool difference with control → positive control. [observed: as cited in parts 1-6]

**Conclusion (one line):** unit — B2g row 1, confirmed; cluster — B3g row 1 / positive-control row confirmed for `S`, `D1`, `D2`, `H1`, `P2`, `M128`; row 2 matched as worded for `F1` (refuted for that sub-prediction: the frozen B3f said the live total "stays about 1 per peer", the node holds 0 because every writer is closed after its hint).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-parsed from the raw files by `harness/hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous/selfcheck.py` (its own code; the output is `run1/selfcheck.txt`), and the cited files re-opened.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.txt`: every lifetime 200 (200,000) ok, 0 errors; `US`/`U` have 0 CompressedHintsWriter lines; LZ4 lifetimes have `opened` and `cbuf` lines; `M128` slabs 134,217,728 B. A first version of the self-check counted the node-stop closes as writer closes (live 0 everywhere); the self-check was fixed to ignore closes after the end mark, and the runner's own trace read, taken before the stop, agrees (live 1 / 1 / 1 / 2). |
| 2. Readings | yes | X recomputed independently: S 0.12, D1 8.04, D2 8.04, F1 0.01, H1 8.04, P2 16.07, M128 8.04 MiB, equal to the runner's `analyze`; unit capacities recomputed with the formula (6 of 6 equal, N = 1/4/16 ratio 1.0000). |
| 3. Matched row | yes | Unit row 1 and cluster rows as in 4.2 part 3; F1 against B3g row 2 re-read in the case file (the row says "Increment shrinks when `max_hints_file_size` ... is lowered"); the frozen table hash `d46dfb1b…` re-computed from the amended case file before the verdict is written. |
| 4. Excluded rows | yes | `selfcheck.txt` (capacities identical in all LZ4 lifetimes; positive control 192.00 MiB = 192.00 MiB); F1's row stays matched, not excluded. |
| 5. Observed vs. inferred | yes | (i) live capacity sum vs X agree to 0.01 MiB; (ii) F1: `phases.json` shows 200 writers, one capacity; (iii) source lines re-read: `HintsWriteExecutor.java:228-229` (`closeWriter` when `flushInternal` returns false) and 247-248. |
| 6. Deviations and gaps | yes | JMX ports, 8 MiB ceiling in the cluster tier, `hints_compression` read-back: each stated. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes, with one caveat | The logic (B2 → B3 → control → positive control) is followed. The caveat is F1: B3f assumed the writer stays open between flushes, which `HintsWriteExecutor.java:228-229` (read in the audit as a cite, not as a consequence) contradicts; the prediction missed and is not edited. |

### 5.2 Run 2?

**No** — decided 2026-10-25. The unit tier is exact and deterministic, the cluster numbers rest on an exact per-writer trace plus a control and a positive control, `D1` and `D2` already repeat each other, and the only open point (F1) is a wording problem of the frozen table that a second run would repeat, not a measurement doubt.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** B1 — the off-heap compression buffer of a `CompressedHintsWriter` has capacity equal to the largest compressor bound seen (about 1.0 x the largest written buffer plus a few tens of bytes, LZ4) and is unaffected by `max_hints_file_size` and `max_hints_size_per_host`; it is capped only by the per-hint size cap, and grows with the number of peers holding open writers. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g row 1 (also the 17 MiB / `HintsBuffer` row and the slab positive-control row) | does not cap | run 1 + self-check | 2026-10-25 |
| Cluster | Confirmed for `S`, `D1`, `D2`, `H1`, `P2` and the positive control `M128` (B3g row 1, last row); B3g row 2 matched as worded by `F1` (post-GC increment 0.01 MiB at `max_hints_file_size` 1 MiB) — **Refuted as worded for that sub-prediction** | does not cap (the buffer's size); `max_hints_file_size` ends the buffer's life, it does not bound it | run 1 + self-check | 2026-10-25 |

**Why the class is true negative although a B3g refuted row matched.** The estimate says the capacity test at `CompressedHintsWriter.java:53` is not a limit and no hints size knob bounds the buffer. Run 1: the buffer is exactly the LZ4 bound of the largest write in every arm, unchanged by either knob (all 400 `writeBuffer` lines in `D1`, `F1`, `M128` end at the same 8,421,599 B per writer), and the peak direct memory with the lower file limit is higher, not lower (362 vs 105-136 MiB). What F1 shows is a different mechanism, writer closure releasing the buffer, which the frozen B3g row 2 words as "those knobs bound it". The row is reported as matched, the cluster verdict says so, the class follows the effect on the constraint, and Jingsong may overrule the label. If the F1 row is read strictly the cluster tier is "Refuted" and the class "undetermined" (tiers disagree); I did not choose that reading because the memory behaviour does not follow the knob as a cap would.

**Positive control** (a negative-estimate file): the slab size derived from `max_mutation_size` (here through `commitlog_segment_size: 128MiB`): unit — `HintsBuffer.create(32 MiB)` and `create(128 MiB)` move the direct pool by exactly 33,554,432 and 134,217,728 B; cluster — `M128` against `D1`: dPool +192.00 MiB for 2 slabs x (128 − 32) MiB, within 0.00 MiB of the trace accounting (limit 8 MiB). A cap that binds on this resource and these instruments shows.

**Feedback filed:** the case file's section D updated (not committed); amendments: dated 2026-10-25 in A3's note, B2, B3 (items 1-6), B3f and B3g (positive control), listed in §1.1. For stage 3: (1) the F1 prediction (B3f) assumed the writer stays open between flushes; with `max_hints_file_size` below the hint size `flushInternal` closes it after every hint (`HintsWriteExecutor.java:228-229,247-248`), so the live total is 0 and the allocations multiply; (2) the cap is `max(max_mutation_size, 16 MiB)` for a record, 16 MiB less 12 B for a payload; (3) B3g needs a row for "no hint reached the writer" (`max_hints_size_per_host`) and for "increment 0 because writers are closed"; (4) `system_views.settings` does not show `hints_compression`; (5) the case file's A1 claim that the only ceiling is the per-hint cap holds, and the total is the sum over open writers: 16.07 MiB for two peers, which at 16 MiB hints would be 32.1 MiB plus, per file roll, a garbage buffer until the next GC.

### Leftovers

No process of this harness is running (`ps` filter on `~/s4-hw-data/` empty after the last lifetime). On disk on `pc07`: the tree `~/s4-hw` (with the probe test copied into `test/unit/org/apache/cassandra/hints/`), `~/s4-hw-logs/` (27 MB of logs in total), `~/s4-hw-data/` (configs, node logs and `jmx/`; data, commit log and hints directories removed). Nothing in `/proj` except the repository files of this stage.
