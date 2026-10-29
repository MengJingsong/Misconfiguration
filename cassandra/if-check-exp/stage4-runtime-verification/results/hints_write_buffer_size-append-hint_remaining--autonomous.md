# hints_write_buffer_size-append-hint_remaining--autonomous — stage-4 results  <!-- file: results/hints_write_buffer_size-append-hint_remaining--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`hints_write_buffer_size-append-hint_remaining--autonomous`](../../stage3-ai-deep-read/cases/hints_write_buffer_size-append-hint_remaining--autonomous.md)
>
> **Status:** **Closed 2026-10-28 — unit Confirmed, cluster Confirmed — does not cap** (estimate negative, matched); two sub-predictions of B3f missed; no run 2
>
> **Outcome class:** true negative — stage-3 estimate vs the stage-4 effect on the constraint
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments: `f2f1a8e29419d28d0e1ec066706f0acc6ffa3a391843c74a76cff8469a031588` (`sha256sum`, run 2026-10-28 before any harness check or run, after the block "Audit amendments (stage 4 step 0, 2026-10-28)" R1-R7 in the file). The file before the amendments had sha256 `8e936e41fe98c1598c06e952dadb51ad8e2761ed5eac55edcae9dcfed9eff26a` (in `b68711e5`). The amended file is not committed by this session. |
| **Harness** | [`harness/hints_write_buffer_size-append-hint_remaining--autonomous/`](../harness/hints_write_buffer_size-append-hint_remaining--autonomous/README.md), written 2026-10-28; not committed by this session. |
| **Tiers and values** | Unit (B2): aggregation buffer N = 64 KiB · 256 KiB · 1 MiB x hint size H = 1 · 100 · 255 · 300 KiB · 2 MiB, 2 reps; controls: file-size stop at 1 MiB for every N and H, heap aggregation buffer. Cluster (B3): builds with `WRITE_BUFFER_SIZE` = 64 KiB · 256 KiB (stock) · 4 MiB x payload 1 KiB · 200 KiB · 2 MiB x 2 reps, 1 GiB of values per arm; controls on the stock build: `max_hints_file_size` 8MiB, `max_hints_size_per_host` 64MiB, `max_mutation_size` 32768KiB (+ `commitlog_segment_size` 64MiB), `max_mutation_size` 4096KiB; per-build delivery check. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: off-heap bytes of one 256 KiB direct buffer (B1 also claims the disk bytes of hint files). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | A1: the constant cannot be set. Unit: the buffer size passed to `newSession` (64 KiB · 256 KiB · 1 MiB) and five hint sizes either side of it; cluster: three builds (64 KiB · 256 KiB · 4 MiB), plus three real caps as controls (B3b). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B3d: direct pool, NMT, RSS, `du -sb`; the buffer's own share inside the pool total is inferred from build differences and a Byteman trace (named in B3d, R6). |
| A. Core question | usage driven to the limit and past it | Partly → Met after R3 | B3c's 6 GiB of 1 KiB hints is 6 million client writes per arm and 18+ arms; 1 GiB still cycles the 256 KiB buffer 4,096 times and the 32 MiB slab about 30 times. |
| B. Logic | each step says what it establishes | Met | B2e / B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after R1 | B2f says the file length "stays 0", but the 42-byte descriptor header is written at `HintsWriter.create` (`HintsWriter.java:67-91`); read relative to the header. B3f numbers (−192 KiB, +3.75 MiB, 12 %) are exact. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → Met after R6 | B3g has no row for a pool total that moves by whole 32 MiB slabs (the previous closed case saw 1–3 slabs, 72–153 MiB, which swamps a 192 KiB–3.75 MiB step); row added. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Confirmed needs the oversize write-through (no loss, no rejection), the file-size stop binding for every N, and the real caps moving usage. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: positive controls on the same instruments (`max_hints_file_size`, `max_hints_size_per_host`, slab size via `max_mutation_size`), idle baseline, repeats. |
| C. Specific | a human can follow it from the intro and §9a | Met | A1–A4 and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after R2–R5 | Entry shape (direct), writer observation, control payload and volume, per-build delivery check were not stated; added. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after R3–R5 | Same items; B3e step 6 (restart node2 and confirm delivery) cannot be run per 1 GiB arm at the default throttle of 1024 KiB/s (about 17 min per GiB), made a short per-build arm (R5). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | The previous case's cluster driver, client, JMX tool and Byteman rules are reusable; the probe test, the three builds and the multi-build driver are step-1 work. pc29: JDK 11.0.32.1, Ant 1.10.12, 52 GB free, 251 GiB RAM. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met after R3 | 22 arms x 1 GiB of hints + 1 GiB of data, reset between arms; peak about 3 GiB of 52 GB; about 4 min per arm. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Re-read in `cassandra/cassandra-5.0.9/`: `HintsWriteExecutor.java:50,60,239-247`; `HintsWriter.java:67-91,136,167,174,200-222,269-286`; `HintsBuffer.java:58,77,150-157`; `HintsService.java:79,110`; `DatabaseDescriptor.java:898-901`; `StorageProxy.java:2488-2491`; `Config.java:446-448`; `conf/cassandra.yaml:102,106,111`. All hold. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | B2f: "file length stays 0" → stays at the header length | Applied 2026-10-28 (B2f; not committed) | the descriptor is written when the writer is opened |
| R2 | B2c/B2d: direct entries, counting `HintsWriter` subclass | Applied 2026-10-28 (amendment block) | the instrument and the production entry shape were unstated |
| R3 | B3c: 1 GiB of values per arm (was 6 / 6 / 2 GiB) | Applied 2026-10-28 (B3c) | feasibility; still far past the limit |
| R4 | B3b/B3h: control payload (200 KiB), volume, once each, repeats, shuffled order | Applied 2026-10-28 (amendment block) | unstated values |
| R5 | B3e step 6: delivery check once per build, short arm | Applied 2026-10-28 (B3e step 6) | default throttle makes it infeasible per arm |
| R6 | B3g: row for a pool total that moves by whole slabs | Applied 2026-10-28 (B3g) | otherwise no row fits a likely outcome |
| R7 | B3a: `hints_flush_period` default; heap through `MAX_HEAP_SIZE=2G` | Applied 2026-10-28 (amendment block) | wording only |

**Agreement criteria** — run 2 is not planned (decided in §5.2 after run 1).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-28 (node clock, MDT): unit 08:32–08:33; cluster 08:33–10:37; instrument shakedowns 08:08–08:32 (not counted) | not done |
| Node (CloudLab name and type) | `pc29` = `node3.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB). Both Cassandra nodes on this host on loopback: A = 127.0.0.2 (JMX 7102, measured), B = 127.0.0.3 (JMX 7103) (as in the previous `WRITE_BUFFER_SIZE-append-remaining` case; B3a assumed two hosts) | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` | — |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18) | — |
| Ant (`ant -version`) | 1.10.12 | — |
| Local source copy | `~/s4-hwb/base` made by `copy-source.sh` from `cassandra/cassandra-5.0.9/` at repository commit `b68711e5` (local tag `cassandra-5.0.9`, baseline `055dd3e`), `ant build-test` 1 min 8 s; variants `~/s4-hwb/var-64k`, `var-4096k` = `cp -a` of it with `HintsWriteExecutor.java:50` edited and `ant jar`; constants confirmed with `javap -constants` (65536 / 262144 / 4194304, `summary.txt`) | — |
| Case-file commit / harness commit | case file sha256 `f2f1a8e2…` (verified by `sha256sum` before run 1); nothing committed by this session | — |
| Storage for node data | `~/s4-hwb/n-hwb1/{A,B}` on local `/dev/sda3` (63 GB, 48 GB free after the run) | — |
| Full logs (path, outside the repo) | `pc29:~/s4-hwb/logs/hints_write_buffer_size-append-hint_remaining--autonomous/run1/` (`unit/`, `cluster/`: per-arm `keys-*.csv`, `samples-jmx-*.csv`, `hints-*.csv`, `hwb-*.trace`, `nmt-*.txt`, `*-system.log`, gc logs); chain log `~/s4-hwb/logs/chain.log` | — |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | instrument check (unit shakedown1) | B2d/B2f (harness model) | `Session.append` calls `writeBuffer` on an empty buffer when an oversized entry arrives (flush at `HintsWriter.java:205-209` runs even with 0 bytes buffered), so the channel-write count of a through-written entry is 2 calls (one of 0 B). The first model counted only non-empty writes against all calls. | Zero-length calls are counted apart (`zeroLengthWriteCalls`); the model compares non-empty writes. Instrument only; no prediction touched. | 2026-10-28 | none |
| D2 | cluster shakedown1 | harness | the sampled `asamp` line never fired for 32 appends (the Byteman counter returns the new value, so `% 128 == 0` skips the first), leaving the traced capacity empty for the 2 MiB arm; the appended-bytes expectation forgot that a hint is larger than its value (about 69 B per 1 KiB value). | sample on `== 1`; the expectation is appended bytes + 42 B per file = bytes on disk. Instrument/expectation only. | 2026-10-28 | none |

No step of B2/B3 failed to run as written after the audit's amendments. Deviations from the text are the audit's R3 (1 GiB per arm) and R5 (delivery check as a short per-build arm), recorded in §1.

## 4. Run 1

**Scope:** unit tier B2 (3 N x 5 H x 2 reps = 30 cells, 5 heap-buffer cells x 2, file-size stop for 3 N x 5 H) and cluster tier B3 (3 builds x 3 payloads x 2 reps = 18 arms of 1 GiB, four controls, three delivery arms = 25 arms, control with B up). **Command log:** [`hints_write_buffer_size-append-hint_remaining--autonomous/run1/`](hints_write_buffer_size-append-hint_remaining--autonomous/run1/) (`unit/summary.txt`, `unit/test-nonappend.out`, `cluster/summary.txt`, `cluster/analysis.txt`, `cluster/arms.json`, `cluster/A-yaml-tail.txt`, `selfcheck.py`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (probe 1/1 passed, upstream `HintsReaderTest` 4/4; 349 checks, 349 ok, 0 mismatches, 0 errors — `unit/summary.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Model of `Session.append` vs every append, all 30 cells (N = 64 KiB · 256 KiB · 1 MiB, H = 1 · 100 · 255 · 300 KiB · 2 MiB) | file length and buffer position equal the model after every append; the 42-byte descriptor header is the file length until the first flush | `unit/test-nonappend.out` (`_model_each_append`), `selfcheck.txt` |
| Buffer position | never above N (e.g. N = 262144, H = 1 KiB: max 262108); first jump at entry floor(N / E) with floor(N / E) x E bytes (253 x 1036 = 262108) | `unit/test-nonappend.out` (`case` lines, `_first_jump_after_N`, `_bufpos_le_N`) |
| Entries with H + 12 > N (e.g. 300 KiB at N = 64 KiB or 256 KiB, 2 MiB at every N) | each append grows the file by exactly H + 12 and leaves the buffer at 0; one non-empty channel write per entry; no exception, nothing refused | same (`_oversized_written_through`, `_channel_writes_`) |
| Every cell | `getBytesWritten` = K x E; file after close = header + K x E; file bytes identical to header + K copies of the entry | same (`_bytesWritten`, `_fileLen_after_close`, `_file_bytes_identical`) |
| Heap aggregation buffer (256 KiB), 5 H | the (file length, position) sequence equals the direct buffer's | same (`heapagg_…_same_(fileLen,pos)_sequence_as_direct`) |
| Positive control: flushInternal loop with `maxHintsFileSize` = 1 MiB | stops after 1013 · 11 · 5 · 4 · 1 entries for H = 1 KiB · 100 KiB · 255 KiB · 300 KiB · 2 MiB, the same for every N; position at stop 1,049,510 · 1,126,574 · 1,305,702 · 1,228,890 · 2,097,206 | `unit/summary.txt` (`filesizestop` lines, `filesizestop_H=…` checks) |
| Side observation | for an oversized entry `writeBuffer` is also called once with an empty buffer (0 B; D1) | `unit/test-nonappend.out` (`zeroLengthWriteCalls`) |

**Cluster tier** (`cluster/summary.txt`, `analysis.txt`, `arms.json`; 126 `EXPECTED` lines: 125 yes, 1 NO — the per-host control's "every write succeeds", 5226 of 5242, 16 coordinator `WriteTimeout`s of the kind that also occur in 4 of the 18 no-limit hint arms; every write was hinted)

| Capacity value | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| builds 64 KiB · 256 KiB · 4 MiB, B down | all 18 hint arms | traced buffer capacity (`asamp`) | 65536 / 262144 / 4194304 in every arm of that build | `summary.txt` (EXPECTED "traced aggregation-buffer capacity") |
| same | 1 KiB, 2 reps x 3 builds | hint bytes on disk | 1,146,093,946 B in all six arms (1.0674 x values), 9 files | `analysis.txt` |
| same | 200 KiB, 2 reps x 3 builds | hint bytes on disk | 1,073,928,876 B in all six (1.0003 x), 8 files | `analysis.txt` |
| same | 2 MiB, 2 reps x 3 builds | hint bytes on disk | 1,073,778,512 B in all six (1.0000 x), 8 files | `analysis.txt` |
| same | every arm | hinted and stored | `Hints_created` = writes = entries appended; appended bytes + 42 B x files = bytes on disk; files roll at 128 MiB (largest 134.2 MB) | `summary.txt` |
| same | 200 KiB at 64 KiB and 256 KiB builds; 2 MiB at all three builds' 64 KiB, 256 KiB | bypass | `over` = `wrdirect` = writes (5242 · 512): every entry larger than the buffer is written to the channel directly; at the 4 MiB build 200 KiB and 2 MiB entries fit: `over` 0, `wrdirect` 0 | `summary.txt` |
| same | idle baseline (median 10 s after GC, B down), direct pool minus traced slabs | per build | 33.22 MB (64 KiB) · 33.42 MB (256 KiB) · 37.35 MB (4 MiB); differences −196,318 B and +3,927,400 B against the constants' −196,608 and +3,932,160 | `analysis.txt` |
| same | NMT "Other" committed before each arm | per build | 251.33 MB · 251.53 MB · 255.46 MB, i.e. −0.20 MB and +3.93 MB from the stock build | `arms.json` (`nmt_other_before`) |
| same | direct pool peak, 1 KiB | per build | 97.2 · 97.4 · 101.1 MiB, 2 slabs each; build differences −0.19 and +3.75 MiB = the constants' differences to 0.05 MiB, both reps | `analysis.txt` |
| same | direct pool peak, 200 KiB | per build | 142.1–143.7 · 142.9–143.7 · 146.1–147.4 MiB, 3 slabs each; pairwise differences from the constants' difference within ±1.4 MiB | `analysis.txt` |
| same | direct pool peak, 2 MiB | per build | 144.8 / 166.8 · 161.9 / 163.9 · 165.7 / 166.8 MiB, 3 slabs each; the two reps of the 64 KiB build differ by 22 MiB, more than the 3.75 MiB step; no ordering by build | `analysis.txt` |
| same | pool peak vs payload | all builds | 97 (1 KiB, 2 slabs) → 143 (200 KiB, 3 slabs) → 165 MiB (2 MiB, 3 slabs): rises with payload at every build | `analysis.txt` |
| same | RSS peak, heap peak | all | RSS 2,952–3,255 MiB, heap 1,499–1,875 MiB of 2,048 MiB, no ordering by build | `analysis.txt` |
| same | hints written but B up (control) | 128 MiB of 1 MiB values | no hint written, TotalHints +0 | `summary.txt` |
| per-build delivery | 250 x 200 KiB, B restarted, throttle raised | `HintsSucceeded` | +250 of 250 at each of the three builds, 49.5 s, no `.hints` file left | `summary.txt` |
| control `max_hints_file_size` 8MiB | 200 KiB, stock build | files | 128 files (1,073,933,916 B total), largest 8,399,712 B, against 8 files of up to 134 MB without it | `summary.txt` |
| control `max_hints_size_per_host` 64MiB | 200 KiB, stock build | disk | stops at 174,959,064 B (166.9 MiB; one 128 MiB file closed + 39 MiB open) against 1,073,928,876 B; 854 of 5242 hints stored; 1,774 refusals, sampled operands above the limit; 0 growth in the last 40 % of the window | `summary.txt` |
| control `max_mutation_size` 32768KiB + `commitlog_segment_size` 64MiB | 200 KiB, stock build | slab, pool | slabs 67,108,864 B, 3 of them; pool peak 238.8 MiB against 143.7 MiB for the stock-build maximum (+95 MiB); disk unchanged | `summary.txt` |
| control `max_mutation_size` 4096KiB | 200 KiB, stock build | slab, pool | slabs 33,554,432 B (floor), pool peak 143.3 MiB (no change); disk unchanged | `summary.txt` |

Writers waiting at the 3-buffer pool cap: 27–31 `waiting` lines in each 200 KiB / 2 MiB arm, 0 in the 1 KiB arms (`arms.json`, `trace.waiting`).

### 4.2 Conclusion and logic

1. **Validity.** Unit: all cells ran, 349 checks, no instrument error [observed: `unit/summary.txt`]. Cluster: B was down for every hint arm (A restarted per arm, hints cleared, no `.hints` file at the start) and hints were really written (`Hints_created` = writes in all 18 arms; control with B up wrote 0 hints) [observed: `summary.txt`]; the builds' constants confirmed by `javap` and by the traced capacity [observed]; B3a settings in force (command line has `-Xmx2G`, `MaxDirectMemorySize=1g`, NMT, Byteman) [observed]. The volume per arm, 1 GiB, is 4,096 buffer cycles and 32 slabs: far past the limit; the three real controls moved. Valid.
2. **Readings.** (a) The pool total rises with the payload at every build (97 → 143 → 165 MiB); 2 → 3 slabs explains 32 MiB, the remaining ~18 MiB between 200 KiB and 2 MiB is unattributed direct memory (probably client frames), the same at every build [inferred: slab count from the create trace; nothing in the trace explains the rest]. (b) Pool peaks at 2 MiB vary 22 MiB between two reps of the same build, so the pool total cannot resolve the constant at that payload [observed: `analysis.txt`]. (c) Coordinator `WriteTimeout`s (7–24 per affected arm) in 8 of 25 arms, none in the 1 KiB arms; the hint for each was still created [observed]. (d) The per-host limit overshoots to 167 MiB because the check reads closed-file sizes and the open file/slab content is not yet counted [inferred from the 128 MiB + 39 MiB split].
3. **Matched row.** Unit, B2g row 1 "Flush points move with N exactly as predicted; oversized hints pass through; every byte arrives": flush points equal the model for three N, oversized entries are written through with exactly H + 12 growth, every byte arrives; the heap and direct buffers behave identically, and the file-size stop binds at the same entry count for every N (row 5 does not apply). Cluster, B3g row 1 and the added R6 row: hint disk is byte-identical across the three builds at every payload; no hint is rejected or dropped (the 64 KiB and 256 KiB builds write every 200 KiB and 2 MiB entry directly); the buffer's capacity is the constant (trace) and the idle baseline and NMT differ across builds by exactly the constants' difference (−196,608 / +3,932,160 B); the pool peak differs by the constants' difference to within 0.05 MiB at 1 KiB and 1.4 MiB at 200 KiB with equal slab counts, and the slab count (2 or 3), not the constant, explains the pool total; the controls bind (8 MiB files, 167 MiB disk plateau, 64 MiB slabs +95 MiB pool, 32 MiB floor unchanged). The row-1 sub-prediction "otherwise flat in payload" did not hold (reading 2a) and at the 2 MiB payload the pool peak is not within "about the constants' difference" (reading 2b); both are rep-to-rep or payload effects that do not scale with the constant.
4. **Excluded rows.** Refuted rows: "grows with the constant by more than its own capacity difference, or grows in time with load": the baseline, NMT and 1 KiB/200 KiB pool peaks track the constant exactly, and the 2 MiB pool peaks do not order by build (b64k 144.8 / 166.8, b256k 161.9 / 163.9, b4096k 165.7 / 166.8 MiB) [observed: `analysis.txt`]. "Hints rejected, dropped or errors when a hint exceeds the constant": none, `Hints_created` = writes = appended, disk identical. "Hint disk differs across builds": identical. "Controls do not change disk/memory as predicted": all four moved as predicted. "Hints not produced": 1 GiB per arm produced. Unit: no throw or loss (row 2), position never above N (row 3), file length grows only at flushes for small H (row 4), file-size stop triggered (row 5).
5. **Observed vs. inferred.** Inferred: that the unattributed direct memory at 200 KiB–2 MiB is not caused by the constant (supported by it not ordering with the constant); that the 256 KiB buffer is inside the pool total (supported by the exact baseline/NMT differences).
6. **Deviations and gaps.** 1 GiB per arm instead of 6 GiB (R3); delivery checked at 250 hints per build (R5); both nodes on one host; `jstat` replaced by JMX heap. The buffer's own contribution is resolved by the idle baseline, NMT and the trace, not by the pool peak under load at 2 MiB (reading 2b).
7. **Core question.** Usage did not follow the constant: hint disk, hint count, slab count and every real-load peak are independent of it; the only quantity that moved with it is the one buffer's own capacity, by exactly the difference (baseline, NMT, pool at 1 KiB). Oversized hints bypass it and are stored in full, and the quantities that do cap hint usage (`max_hints_file_size`, `max_hints_size_per_host`, `max_mutation_size`) moved disk and memory under the same instruments (steps 3–4 of the audited logic). The constant does not cap hint-writing memory or disk usage.

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 (with the R6 row) — confirmed, does not cap.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`results/hints_write_buffer_size-append-hint_remaining--autonomous/run1/selfcheck.py` re-parses the raw logs without the test's or driver's code: unit re-simulation of 40 cells from the per-append lines (0 disagreements), the 349 check lines, and for each of 25 arms the key CSV (written/succeeded), the hints CSV (bytes), the samples CSV (pool peak), the Byteman trace (slabs, capacities, last flush counters): 128 ok, 0 FAIL (`selfcheck.txt`).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `summary.txt` set-up lines and `javap` lines; `selfcheck.txt` recomputed written/succeeded and slabs |
| 2. Readings | yes | `analysis.txt` re-read: 2 MiB pool peaks and the idle-baseline residuals as quoted |
| 3. Matched row | yes, with the two sub-predictions of B3f that missed named in 4.2 part 3 | `analysis.txt`; the 2 MiB pool peaks are not within the constants' difference but do not order by build |
| 4. Excluded rows | yes | disk equality from `analysis.txt` X1; controls from `summary.txt` |
| 5. Observed vs. inferred | yes | |
| 6. Deviations and gaps | yes | |
| 7. Core question | yes | the steps follow the audited logic (B1 and B3f) |

### 5.2 Run 2?

No (2026-10-28): the unit tier is exact and deterministic, the cluster tier's disk, trace, baseline and NMT readings are identical across reps; the one weak reading (pool peak at 2 MiB) is not what the conclusion rests on.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** total off-heap memory and disk used by hint writing do not follow `WRITE_BUFFER_SIZE`: changing the constant changes only the one aggregation buffer by exactly the difference, independent of hint volume, host count or hint size, while the settings that actually bound hint memory/disk move usage. "Confirmed" means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1) | does not cap | run 1 + self-check | 2026-10-28 |
| Cluster | Confirmed (B3g row 1 and the R6 row); two sub-predictions of B3f missed (pool "flat in payload"; pool peak at 2 MiB "about the constants' difference") | does not cap | run 1 + self-check | 2026-10-28 |

**Positive control:** `max_hints_file_size` 8MiB (128 files of ≤ 8.4 MB against 8), `max_hints_size_per_host` 64MiB (disk 167 MiB against 1,024 MiB), `max_mutation_size` 32768KiB + `commitlog_segment_size` 64MiB (slab 64 MiB, pool +95 MiB), unit file-size stop at 1 MiB for every N; `max_mutation_size` 4096KiB left the slab at the 32 MiB floor, as predicted.

**Feedback filed:** section D of the case file filled (dated 2026-10-28); the case file amended before run 1 (audit block R1–R7, sha256 `f2f1a8e2…`); no later amendment.
