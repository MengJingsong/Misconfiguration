# file_cache_size-CompressedChecksummedDataInput-readBuffer-compressedBuffer--autonomous — stage-4 results  <!-- file: results/file_cache_size-CompressedChecksummedDataInput-readBuffer-compressedBuffer--autonomous.md -->

> **Case:** [`file_cache_size-CompressedChecksummedDataInput-readBuffer-compressedBuffer--autonomous`](../../stage3-ai-deep-read/cases/file_cache_size-CompressedChecksummedDataInput-readBuffer-compressedBuffer--autonomous.md)
>
> **Status:** **verdict filed 2026-10-25 — unit Confirmed, cluster Confirmed — does not cap.** Estimate negative; claim tested: the compressed-hint reader's two block buffers do not follow `file_cache_size` (blocks > 128 KiB bypass the pool). Reader memory was 12.62 MiB per reader at every threshold (1 / 8 / 64 / 512 MiB), identical to the byte; in the cluster 25.25 MiB (two readers) at 512 / 64 / 1 MiB, 8 KiB with uncompressed hints. Five audit amendments (macro chunk 8 MiB, `Size` includes overflow, counter leak, workload, control); no run 2.
>
> **Outcome class:** **true negative** — stage-3 estimate `negative` against the stage-4 effect `does not cap`
>
> **Agent:** autonomous. "§9a" below = B2f/B2g (unit) and B3f/B3g (cluster); runbook = B2a–B2e / B3a–B3e; feedback = section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the whole file after the audit's amendments (2026-10-25, before any reading of a run): `078ef94b502b5661dfba20fb54eb4f4604dbc177dfd859b7664e6bcecf9376f7`. sha256 of the prediction and conclusion tables (B2f through the end of B2g, then B3f through the end of B3g, text between the headings `**B2f.**`..`**B2h.**` and `**B3f.**`..`**B3h.**` concatenated): `cb2814c558a81ab09eadbe857ae4f6435d6b140e21daae87b93c6fae83d403fb`, written here before run 1. Commit holding the file: not committed yet (base `f33e621` plus working tree; the orchestrator commits). |
| **Harness** | `harness/file_cache_size-CompressedChecksummedDataInput-readBuffer-compressedBuffer--autonomous/`: `unit/FcsReadBufferMain.java`, `unit/run-cell.sh`, `unit/unit-all.sh`; `cluster/cluster-run.sh`, `cluster/gen-conf.py`, `cluster/Sampler.java`, `cluster/write_blobs.py`, `cluster/summarize.py`. Not committed (orchestrator). Instrument checks: see "Harness checks" below. |
| **Tiers and values** | Unit: `file_cache_size` 1 / 8 / 64 / 512 MiB x block 32 KiB / 100 KiB / 1 MiB / 6 MiB x readers 1 / 2 / 8 (LZ4), Deflate for 1 MiB and 6 MiB x readers 1 / 8, plus the control. Cluster: node 1 at 512 / 64 / 1 MiB (hints, 6 MiB blobs, N = 100), HU1 (uncompressed hints at 1 MiB), stress control at 1 / 64 / 512 MiB. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-25 |

**Harness checks (shakedowns, not readings of the case; done before the freeze and not part of any run):** the unit main class compiled and ran one cell (LZ4, 8 MiB, 1 MiB blocks, 4 hints, 2 readers: 8 hints read, 0 failures, exit 0); a cluster run with N = 24 and a control run with 1 MiB were run end to end to debug the scripts (an output parse, the stress `-pop` range, the sampler start). Their numbers were seen by the auditor. Two things in the case file were corrected afterwards, both source facts: the macro chunk is 8 MiB (the shakedown log line "cannot allocate chunk of 8.000MiB" showed it; the source constant `BufferPool.java:385` gives the same) and the java.nio counter is JVM-wide (HU1 subtracts the messaging buffers). The predicted values for the hint readers (`~12.6 MiB` per reader, `1.05*B - 4096` residual) were written from the source before any shakedown.

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: off-heap bytes in the chunk-cache BufferPool; B1 reader buffers (direct/heap bytes) |
| A. Core question | knob varied, >= 3 values incl. default | Met | B2b {1, 8, 64, 512 MiB}; B3b {1, 64, 512 MiB}; 512 MiB is the default (`DatabaseDescriptor.java:576-577`: min(512, heap/4)) |
| A. Core question | real resource measured, not only the counter | Met after amendment | B2d/B3d have `java.nio` direct `MemoryUsed`, RssAnon (added to the sampler) and heap. The counter `OverflowSize` drifts (see recommendation 3), so the real resource is primary |
| A. Core question | usage driven to the limit and past it | Met after amendment | 6 MiB blocks x 2 buffers exceed every threshold >= 1 MiB; the 1 MiB value has no pooled memory at all (macro chunk 8 MiB) |
| B. Logic | each step says what it establishes | Met | B2e, B3e |
| B. Logic | prediction in numbers or a clear relation | Met after amendment | corrected: pooled = Size - Overflow; 8 MiB steps; counter residual after close; band for the reader share |
| B. Logic | every plausible outcome has a conclusions row | Partly | B2g / B3g cover confirmed, refuted, control invalid, limit not reached, OOM. No row for "claim holds but the 12-30 MiB band is missed"; left for stage 3, would be recorded as Not confirmed on the band and Confirmed on invariance in the narrative |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | B2g row 2 (equal across thresholds incl. 1 MiB) plus overflow > Capacity; the "disallow" here is the bypass (`LocalPool.tryGet` returns null for > 128 KiB, `BufferPool.java:940`; allocation at `:923`) |
| B. Logic | alternative explanations and controls | Met after amendment | B2h/B3h; HU1 made required to separate messaging buffers from the readers' |
| C. Specific | a human can follow it | Met | |
| C. Specific | an AI can run the runbook without re-deriving the path | Partly | needed the harness details (one Session per hint; main class instead of ant; JMX ports; throttle). Applied in amendments |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | hint count, N, throttle, client, control workload were not exact; applied |
| D. Runnable | harness and prerequisites exist or listed | Met | built tree `~/s4-fc` (`ant build-test` 1 min 8 s), no Byteman needed |
| D. Runnable | workload arithmetic reaches the limit | Met after amendment | N = 300 would take hours at the default 1024 KiB hints throttle (divided by node count, `HintsDispatchExecutor.java:220`); N = 100 with 30 MiB/s throttle: about 600 MiB per target, 4-5 hints files per target, dispatch about 2-3 min; node disk 40 GB free |
| D. Runnable | load-bearing citations spot-checked | Partly, fixed | the `~` line cites were replaced by exact ones (list below); one arithmetic error (macro chunk) |

**Citation check** (all against `cassandra/cassandra-5.0.9`): `BufferPool.java` get ON_HEAP `:206-211` (was ~203-209), `allocate` `:233-238`, overflow counter `:261-264`, `LocalPool.get` fallback `:904-923`, `LocalPool.tryGet` `size > NORMAL_CHUNK_SIZE` `:940` (was ~940, correct), `allocateMoreChunks` `:438-470`, OOM catch `:462`; `CompressedChecksummedDataInput.java:118-139` and `:155-159` correct; `BufferPools.java:38-39` correct; `Config.java:493-499, 514` and `DatabaseDescriptor.java:576-577, 898-899`, `conf/cassandra.yaml:93, 125`, `conf/jvm-server.options:174`, `HintsService.java:79, 110`, `HintsWriteExecutor.java:50` correct; `HintsWriter.java` Session.append(ByteBuffer) is `:200-228`. Facts the write-up did not have: (a) `MACRO_CHUNK_SIZE = 64 * 128 KiB = 8 MiB`, not 1 MiB (`BufferPool.java:385`, its comment at `:384` is wrong); (b) `BufferPool.sizeInBytes()` and the `Size` metric include the overflow (`:274-277`; `BufferPoolMetrics.java`); (c) `ChecksummedDataInput.close()` (`:242-246`) only cleans the decompressed buffer, so the counter keeps ~`1.05*B` per closed reader; the initial 4 KiB buffer (`ChecksummedDataInput.java:56`, `RandomAccessReader.DEFAULT_BUFFER_SIZE` = 4096) is "put" into the pool on the first block and lowers the counter by 4096; (d) `ChunkCache.cacheSize = file_cache_size - 32 MiB` (`ChunkCache.java:49-50`), so the cache is off at 1 and 8 MiB; (e) hint blocks of aggregated hints are 256 KiB (`HintsWriteExecutor.java:50`) and so never poolable; one-hint blocks of <= ~120 KiB are the only poolable ones.

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Macro chunk is 8 MiB: pooled memory moves in 8 MiB steps, the 1 MiB value pools nothing | Applied 2026-10-25 (A2, B2b, B2f, B3b, B3f) | arithmetic, source |
| 2 | `Size` includes overflow: define pooled = Size - Overflow in all predictions | Applied 2026-10-25 (B2e, B2f) | source |
| 3 | Counter drift: after close the decompressed buffer stays in `OverflowSize` (`1.05*B - 4096` per reader); cluster counter is per-file, not a 12-30 MiB peak | Applied 2026-10-25 (B2f, B2h 4, B3f) | source |
| 4 | Small-B regime needs one Session per hint (aggregation makes 256 KiB blocks) | Applied (B2c) | source |
| 5 | MaxDirectMemorySize 3g for the unit control at 512 MiB | Applied (B2a) | arithmetic |
| 6 | Cluster: N = 100, throttle 30720KiB, protocol 4 client | Applied (B3b/B3c) | time |
| 7 | Cluster control: no file cache (cache is off below 40 MiB anyway); stress write+flush+read with the sampler from before the write; criterion pooled = 0 at 1 MiB, >= 8 MiB at 64/512 | Applied (B3f, B3g) | source |
| 8 | HU1 (uncompressed hints at 1 MiB) required; reader share = difference of direct peaks over the pre-dispatch level | Applied (B3e, B3f, B3g) | JVM-wide counter |
| 9 | Add a conclusions row for "invariant but outside the band" | Left for stage 3 | |
| 10 | The B1 sentence "arguably not memory-significant" (small object) is a judgement, not tested; the run reports the size (about 25 MiB for 2 readers) | Left for stage 3 | |
| 11 | Real hint readers drain `close()` leak; not a bug report here, listed in the follow-ups for the orchestrator | Left | out of scope |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-25 |
| Node | pc07 (`node0.jason92-320876`), 40 cores, 251 GiB; shared with other agents |
| OS and kernel | Ubuntu 22.04, 5.15.0-187-generic |
| JDK / Ant | see `java -version` below (OpenJDK 11.0.32.1) / Ant 1.10.12 |
| Local source copy | `~/s4-fc` from `cassandra/cassandra-5.0.9/` at repository commit `f33e621` (working tree), `ant build-test` (log `~/s4-fc-logs/build-test.log`) |
| Ports / addresses | JMX 7212 (node 1), 7213, 7214; native 9144; storage 7012; loopback 127.0.12.1-3 (Byteman 9112 unused) |
| Deviations | `-Dcassandra.ring_delay_ms=5000`, `-Dcassandra.skip_sync=true` for the three nodes; node 1 `-Xmx2g`, `-XX:MaxDirectMemorySize=4g`; nodes 2, 3 `-Xmx2g` (G1 default otherwise) |
| Storage | local disk `/` (ext, 40 GB free), under `~/s4-fc-run/<label>` and `~/s4-fc-logs` |
| Full logs | `~/s4-fc-logs/unit/`, `~/s4-fc-logs/cluster/<label>/` on pc07 |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | cluster, first attempt of H512 | B3a (nodes' JMX) | the harness gave nodes 2 and 3 JMX ports 7213 and 7214, which were not in this agent's allocation; another agent's JVM took 7214 and node 3 died with `BindException` at start. No reading had been taken | nodes 2 and 3 now use 7412 and 7413 (node 1 keeps the assigned 7212); H512 restarted from its start (the aborted attempt's directory was deleted) | 2026-10-25, harness only, case file unchanged | none |
| 2 | self-check script | | two checker bugs: the regex missed the argument-less line `OBS done`, and the ERROR scan matched `HeapDumpOnOutOfMemoryError` in the JVM argument line | fixed in `selfcheck.py`, rerun on the same raw files | 2026-10-25 | none |
| 3 | audit | A2, B2b-B2f, B3b-B3g | case-file errors found by the audit (not at a run): macro chunk 8 MiB; `Size` includes overflow; counter leak at close; aggregation makes 256 KiB blocks; JVM-wide direct counter; the control did not use the pool | dated amendments in the case file, frozen in §1 before run 1 | 2026-10-25 | not committed |

## 4. Run 1

**Scope:** unit tier, all 68 cells; cluster tier, hints runs H512 / H64 / H1 / HU1 and stress controls C1 / C64 / C512. **Command log / excerpts:** `file_cache_size-CompressedChecksummedDataInput-readBuffer-compressedBuffer--autonomous/run1/` (`unit/analysis.txt`, `unit/obs-lines.txt`, `cluster/<label>/{run.log,phases.txt,sampler.csv,summary-*.txt}`, `cluster/collect.txt`, `selfcheck.txt`). Full logs: `~/s4-fc-logs/` on pc07.

### 4.1 Readings

**Unit tier** (`unit/analysis.txt`; "reader overflow" = `overflowMemoryInBytes` with the readers parked at their last block, minus the baseline; expected = R * (2 * 1.05 * B - 4096)):

| Test or assertion | Result | Evidence |
|---|---|---|
| Control: pool plateau at `floor(threshold / 8 MiB) * 8 MiB` after requesting 3 x threshold of 64 KiB buffers | 1 MiB: pooled 0, overflow 3,145,728; 8 MiB: pooled 8,388,608, overflow 16,777,216; 64 MiB: pooled 67,108,864, overflow 134,217,728; 512 MiB: pooled 536,870,912, overflow 1,073,741,824; all released to 0 / 0 | `unit/analysis.txt` "controls" |
| LZ4, B = 6 MiB, R = 1 / 2 / 8: reader overflow | 13,234,018 / 26,468,036 / 105,872,144 B (12.62 MiB per reader) **at all four thresholds, identical to the byte**; expected 13.21 / 26.42 / 105.66 M (ratio 1.002); pooled unchanged | `unit/analysis.txt` rows `reader_t*_LZ4_B6291456_R*` |
| Same cells, real resource: `java.nio` direct delta | 13,500,391 / 26,738,641 / 106,168,141 (the counter + 0.26 MB of reader state); same at all thresholds | same |
| LZ4, B = 1 MiB | 2,202,380 per reader (2.10 MiB), same at all thresholds | rows `..._B1048576_R*` |
| Close, LZ4 6 MiB R = 8 | counter keeps 52,816,040 B (expected 52,815,462); real direct falls back to baseline + 263,168 | `closed` lines |
| LZ4, B = 32 / 100 KiB (one hint per block) | threshold 1 MiB: reader overflow 519,992 / 1,692,104 (R = 8, equals the expected); thresholds 8 / 64 / 512 MiB: -32,768 (the readers took pooled buffers: in-use pooled +552,760 / +1,724,872; after close in-use +275,816 / +860,728, never returned) | rows `..._B32768_R8`, `..._B102400_R8` |
| Deflate (ON_HEAP), B = 1 / 6 MiB, R = 1 / 8 | pooled unchanged, counter equal to the LZ4 figure, heap delta 119 MiB at 6 MiB R = 8; **real direct delta not zero**: 56,896,040 B (R = 8, 6 MiB) | rows `reader_t*_Deflate_*` |
| Failures | 0 readers failed, every hint read (`hintsRead == n * R`) in every cell | `unit/analysis.txt` |

**Cluster tier** (`cluster/collect.txt`; node 1 with `file_cache_size` = the label; 100 rows of 6 MiB blobs; 10 hints files, 1,263,249,420 B on disk; dispatch about 1 minute):

| Capacity value | Run | Observable | Reading | Evidence |
|---|---|---|---|---|
| 512 MiB | H512 | `Capacity` metric; log line | 536,870,912; "Global buffer pool limit is 512.000MiB" | `H512/run.log` |
| 512 / 64 / 1 MiB | H512 / H64 / H1 | java.nio direct `MemoryUsed`, peak during dispatch minus the last sample before dispatch | **26,476,236 B (25.25 MiB, two readers at 12.62 MiB) in all three** | `collect.txt` |
| 1 MiB | HU1 (uncompressed hints) | same | 8,192 B | `HU1/summary-dispatch.txt`, `collect.txt` |
| 512 / 64 / 1 MiB | H512 / H64 / H1 | `OverflowSize` peak; final value after the 10 files | 79,284,052 peak and 66,020,030 final (6,602,003 per file) in all three; HU1 0 / 0 | `collect.txt` |
| 1 MiB | H1 | `OverflowSize` / `Capacity` | 75.6 x capacity; log "Maximum memory usage reached (1.000MiB) ... cannot allocate chunk of 8.000MiB" | `H1/n1-pool-log-lines.txt` |
| 512 / 64 / 1 MiB | H512 / H64 / H1 | pooled (`Size - OverflowSize`) | 8,388,608 / 8,388,608 / 0 at the dispatch peak (the node's own other use; unchanged by the readers) | `collect.txt` |
| 1 / 64 / 512 MiB | C1 / C64 / C512 | stress write 200,000 rows + flush + 120 s read at 100 threads (0 errors): pooled; `OverflowSize` | C1: pooled median 0, max 73,728 (two gauges read a moment apart; below the 8 MiB step), overflow max 155,648 in 228 of 304 samples; C64 and C512: pooled exactly 8,388,608 in every sample, overflow 0 in every sample | `collect.txt`, `C*/sampler.csv` |
| all | node 1 `system.log` | `ERROR` lines, `OutOfMemoryError` | none | `selfcheck.txt` |

### 4.2 Conclusion and logic

1. **Validity.** The limit was reached: reader memory is 12.6 MiB per reader (unit) and 25.25 MiB (cluster), above 1 MiB and above the 8 MiB macro chunk at the smaller thresholds. [observed: `unit/analysis.txt`, `cluster/collect.txt`] Hold-fixed settings: the capacity metric equals the setting in every cluster run [observed: `*/run.log` "Capacity metric"]; the same 100 x 6 MiB workload and JVM options in H512 / H64 / H1 [observed: `*/run.log`, `phases.txt`: 10 hints files each, same bytes]; compression on in H*, off in HU1 [observed: HU1 overflow 0]. The hints dispatch read the compressed files with two concurrent readers [inferred: the direct delta is exactly 2 x 13,238,118 and the counter gains 6,602,003 per file, both absent in HU1]. The positive control moved [observed: unit control plateaus follow the threshold; cluster C1 against C64 / C512].
2. **Readings.** Two details differ from the written prediction without changing the claim: (a) Deflate's real direct memory rose (56.9 MB at R = 8, 6 MiB) although the buffers are heap arrays; [inferred: the JDK's per-thread temporary direct buffer for `FileChannel.read` into a heap buffer, sized to the read; not tested]; (b) in the cluster control the pool is almost unused (8 MiB at 64 and 512 MiB), so the control separates 1 MiB from the rest only; the pooled figure at 1 MiB is not exactly 0 in 118 samples because the sampler reads `Size` and `OverflowSize` at slightly different instants [inferred: values < 74 KiB, below the 8 MiB step; pooled memory can only change in 8 MiB steps, `BufferPool.java:443-452`].
3. **Matched row.** Unit B2g row 2: "B = 6 MiB: reader memory (overflow, direct delta) ~ R*12.6 MiB and equal across thresholds incl. 1 MiB" -> Confirmed (12.62 MiB per reader, spread 0.0000 over 1 / 8 / 64 / 512 MiB). Cluster B3g row 1 (as amended): direct peak over pre-dispatch less HU1's = 26,476,236 - 8,192 = 26.47 MB = 25.24 MiB, inside 12-30 MiB at all three thresholds (spread 0), `OverflowSize` identical and 75.6 x `Capacity` at 1 MiB -> Confirmed. Positive control row ("`pooled` = 0 at 1 MiB, >= 8 MiB at 64 and 512 MiB, 1 MiB run's overflow peak the larger") -> met, with the 73,728 B skew noted in item 2.
4. **Excluded rows.** Refuted rows (reader memory shrinks with the threshold; peak increases with threshold): excluded by the identical figures at 1 and 512 MiB [observed]. "Overflow only in the control, not in the hints run" (hint path stays in the pool): excluded, hints overflow 66 MB [observed]. "Control did not move / no hints dispatched": excluded, 10 files delivered and removed, `delivered` lines 10 [observed: `H1/run.log`]. "Peak < 1 MiB": excluded. "Heap or direct OOM": none [observed: `selfcheck.txt`]. B = 100 KiB row ("cap binds only for small blocks"): at 8 MiB and above the readers were served from the pool with no overflow, at 1 MiB all went to overflow [observed], consistent with the trace but not a test of the pool cap binding under exhaustion.
5. **Observed vs inferred.** Inferred and relied on: the 8 MiB step reason for the 1 MiB figure [source `BufferPool.java:385`, log line observed]; that dispatch used two readers at once [inferred as in item 1]; that the leaked counter is `ChecksummedDataInput.close()` [source `:242-246`, residual 52,816,040 B observed to match `1.05*B - 4096` per reader].
6. **Deviations and gaps.** Production blocks (aggregates of up to 256 KiB, or one large hint) were not varied in the cluster; only 6 MiB hints. The unit small-B cells never exhaust the pool at 8 MiB (the pool had free chunks), so they do not show the cap binding on a reader buffer. The cluster control is weak (8 MiB vs 0). Shakedown runs preceded the freeze (§1). The pooled/`Size` figures depend on two non-atomic gauge reads. JMX port clash in the first H512 attempt (§3).
7. **Core question.** Usage of the compressed-hint reader (about 12.6 MiB per reader for a 6 MiB hint) did not follow `file_cache_size` at 1, 8, 64 or 512 MiB, and exceeded the 1 MiB capacity 75-fold in the cluster; the knob caps only the pooled 8 MiB macro chunks that other consumers draw (control), not the oversize and overflow allocations this path makes (unit, cluster). So the constraint does not cap this resource. Steps: setting verified (item 1), control moved (items 1 and 3), workload exceeded every value (item 1), reading invariant across values (item 3).

**Conclusion (one line):** B2g row 2 (unit) and B3g row 1 (cluster) — claim confirmed: reader memory does not follow `file_cache_size`.

## 5. Self-check of run 1 — AI

Independent re-derivation: `harness/.../selfcheck.py` parses the raw cell logs' OBS lines and the raw `sampler.csv` / `phases.txt` files with its own code (not `analyze_unit.py`, `collect_cluster.py` or `summarize.py`) and re-checks the conclusion's numbers; output `run1/selfcheck.txt`: **OVERALL PASS**, 0 FAIL. The same raw files were cross-checked by `summarize.py` / `collect_cluster.py` (same peaks).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.txt`: capacities 512 / 64 / 1 / 1 MiB, 10 files per run, HU1 direct delta 8,192 B and overflow 0, no ERROR / OOM line in any node-1 log |
| 2. Readings | yes | Deflate direct and the 73,728 B pooled skew re-read in `analysis.txt` / `C1/sampler.csv` (118 of 304 samples non-zero, all below 74 KiB) |
| 3. Matched row | yes | unit 6 MiB R = 1 / 2 / 8 equal across thresholds (spread 0.0000, 12.62 MiB per reader); cluster direct share 26,476,236 in the three runs |
| 4. Excluded rows | yes | no run shows overflow shrinking with a larger threshold; the 1 MiB run has the same peak as the 512 MiB run |
| 5. Observed vs inferred | yes | the two concurrent readers and the Deflate direct memory are inferred and flagged; neither decides the row |
| 6. Deviations and gaps | yes | listed in §4.2 item 6 |
| 7. Core question | yes | the steps follow the audited block: setting verified, control moved, limit exceeded, reading invariant |

### 5.2 Run 2?

**No** (2026-10-25). The readings are deterministic to the byte across four thresholds and three reader counts, the claim is confirmed rather than refuted, and the inferred statements do not decide a row. A run 2 would add only the weak control.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** B1: the memory used by the compressed-hint reader's two block buffers does not follow `file_cache_size`; blocks > 128 KiB (or an exhausted pool) are allocated outside the pool, so reader memory is about `1.05 * (compressed + uncompressed)` per active reader for every value including 1 MiB, and `OverflowSize` exceeds `Capacity`.

| Tier | Verdict (row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g: 6 MiB reader memory equal across thresholds incl. 1 MiB — **Confirmed** | does not cap | run 1 + self-check | 2026-10-25 |
| Cluster | B3g row 1 (as amended) — **Confirmed** | does not cap | run 1 + self-check | 2026-10-25 |

**Positive control:** unit: the same instruments on 64 KiB requests made directly from the pool: pooled memory stopped at `floor(threshold / 8 MiB) * 8 MiB` (0, 8, 64, 512 MiB) and the rest went to overflow (1.0 GiB at 512 MiB). Cluster: a stress write + read workload on node 1: pooled 0 at 1 MiB (overflow up to 155,648 B in 75% of samples) against exactly 8 MiB and no overflow at 64 and 512 MiB. A weak control (it separates 1 MiB from the rest), enough for the file's own criterion.

**Feedback filed:** the case file's section D updated (no commit; the orchestrator commits), and the audit amendments in sections A2, B2a-B2h, B3b-B3g (dated 2026-10-25). Facts for the orchestrator: (1) `ChecksummedDataInput.close()` never returns the decompressed buffer to the pool, so `OverflowSize`/`UsedSize` drift upward by about `1.05*B` per closed hints reader (a counter bug, the real memory is freed by `FileUtils.clean`); (2) `BufferPool.java:384` comment says the macro chunk is 1 MiB, the constant gives 8 MiB; (3) `file_cache_size` below 8 MiB disables pooling (log "Maximum memory usage reached").

## Leftovers

No Cassandra, stress, Sampler or test JVM left running by this case (checked `ps` after the last run). Directories on pc07, outside the repo: `~/s4-fc` (tree), `~/s4-fc-logs` (logs and shakedowns), `~/s4-fc-run` (empty). `/tmp/fcs-hints*` removed.
