# default_buffer_size_in_mib_for_unsorted-build-maxsstablesizeinmib--autonomous — stage-4 results

> **Case:** `experiments/capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/default_buffer_size_in_mib_for_unsorted-build-maxsstablesizeinmib--autonomous.md` (extension set, `writeup-set-ext.csv` order 115, band B)
>
> **Status:** verdict filed (run 1 + self-check; no run 2), 2026-11-25, Jingsong (AI session). Not yet filed in the repository: this file, the harness and the amended case file are outside the repo (`~/writeup-ext/out/o115/`).
>
> **Outcome class:** **weak true positive** — estimate `positive`; unit tier **Confirmed — caps**; cluster tier **Not confirmed (no matching row)** only because one live-heap peak (C16) lies 0.7 MiB above its frozen band; every other cluster reading matched, and none contradicts the unit effect (rule of 2026-10-29).
>
> **Agent:** autonomous. "§9a" = B2f/B2g (unit), B3f/B3g (cluster); runbook = B2a–B2e / B3a–B3e; feedback = section D.

**Claim tested (B1):** for an unsorted `CQLSSTableWriter` built without a positive size (no call, or `withMaxSSTableSizeInMiB(0)`), the effective buffer cap is 128 MiB, the buffered serialized size never exceeds 134,217,728 B plus one row, the writer's live heap above baseline follows the cap (≈1–2.3× the cap), not the total written, and each SSTable's `Data.db` is ≈128 MiB.

| Tier | Verdict | Effect on the constraint |
|---|---|---|
| Unit (B2) | **Confirmed** (B2g row 1 + U2 = U1 + positive control U3 + reference U4; B2i.6) | **caps** |
| Cluster (B3) | **Not confirmed (no matching row)** (B3i.4: B3g row 1 needs each of C16–C128 in its B3f band; C16 peak 37.7 MiB vs band 14–37 MiB; all other parts of rows 1 and 5, file counts and node count hold; no "Claim wrong" row fires) | undetermined (direction: caps) |

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository commit `bef6bc8a6` holds the filed version (sha256 `0356af5411e0…bb78bf3`, which already carries the 2026-11-24 audit amendments B2i.1–7 / B3i.1–4 of the interrupted run). This run added B2i.8 and B3i.5 (node `pc91`, flush + compactionstats before node readings) before run 1, in `~/writeup-ext/out/o115/case-amended.md`. **Frozen sha256 (before run 1): `44851469308e43c2c0462bb8b0dec78330b5c08c38ad10422df66eebda27608b`** (copy: `harness/case-frozen.md`, `harness/FROZEN-SHA256`). The case-amended.md now also carries section D feedback, so its current hash differs. |
| **Harness** | `~/writeup-ext/out/o115/harness/` (not committed; the repo is not edited by this session): `org/apache/cassandra/io/sstable/BufferCapProbe.java` (B2a listing verbatim), `common.sh`, `unit-run.sh`, `cluster-run.sh`, `analyze.py`. Copied to `pc91:/mydata/jingsong-cass-s4/o115/harness/`. |
| **Tiers and values** | Unit: U1 default, U2 `explicit:0`, U3 `explicit:32`, U4 `explicit:2047` (-Xmx3g), U5 `sorted`. Cluster: live heap C16/C32/C64/C128(default)/CX(2047) at -Xmx2g; OOM sweep C128 @ 256/384/512/768m, C16 @ 256m, CX @ 768m; node ingest of the C128 output via `sstableloader`. W2 (optional) not run. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25. |

### 1.1 Design audit

| Group | Check | Rating | Note |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Met | client JVM heap (live set) and per-SSTable `Data.db` bytes (A2, B3d) |
| A | knob varied, ≥ 3 values incl. default | Met | unit 4 sizes + sorted; cluster 16/32/64/128/2047 MiB (B2b, B3b) |
| A | real resource measured, not only the counter | Met | `currentSize` counter (unit) + live heap after `System.gc()`, G1 log, OOM exit, file bytes (B3d) |
| A | usage driven to the limit and past it | Met | 1,030 MiB written ≈ 8× the default cap (B2c, B3c) |
| B | each step says what it establishes | Met | B2g/B3g rows name what each reading means |
| B | prediction in numbers | Met | exact LIMIT_BYTES, reset counts, file counts, heap bands (B2f, B3f) with B2i.5/B3i.3 tolerances |
| B | every plausible outcome has a row | Met | over-cap, flat-across-caps, upward trend, no-rise, OOM rows present (B2g, B3g) |
| B | confirmation needs ceiling-follows-knob + disallow evidence | Met | resets (sync fired) + heap/file sizes following B |
| B | alternative explanations and controls | Met | U4/CX no-cap reference, U3/C16 positive control, compression off, completeness check (B2h, B3h) |
| C | human can follow from intro and B1 | Met | |
| C | AI can run B2/B3 without re-deriving | Met | full harness listing and commands |
| C | exact knobs, values, commands, sampling, stops | Met | after B2i/B3i |
| D | harness and environment exist | Met | built `/mydata/s4/cassandra-base`; harness from B2a |
| D | workload arithmetic reaches the limit | Met | 1.1 GB per output, ≤3 GiB heap, 703 GiB free, 125 GiB RAM |
| D | load-bearing citations spot-checked | Met | `CQLSSTableWriter.java:677-680`, `SSTableSimpleUnsortedWriter.java:68,74,81-131,153-161` read in the repo source; the three files are byte-identical in the node copy |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Record the new node (pc91, x86_64) and the fresh harness; K0 known-answer check | Applied, B2i.8 (2026-11-25, before run 1) | environment only; no prediction changed |
| 2 | `nodetool flush` and `compactionstats` before node readings | Applied, B3i.5 (2026-11-25, before run 1) | makes `tablestats` final and identifies a transient compaction |
| 3 | B3f's live-heap bands (k ≤ 2.3) ignore the fixed `DiskWriter`/`SSTableTxnWriter` overhead (A4), which is a larger share at small B | left for stage 3 | found only after the readings (C16), so it may not be applied to this run |
| 4 | B3i.3 "flat" metric compares thirds including the first buffer's ramp-up; a reading of the post-first-sync samples would be cleaner | left for stage 3 | does not change this run's outcome |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25 (node clock 2026-11-24 22:40–22:46 MST) |
| Node | `pc91` = `node0.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu`, **x86_64**, 32 cores, 125 GiB RAM, `/mydata` 753 GB (703 GB free) |
| OS / kernel | Ubuntu 22.04.2 / `5.15.0-203-generic` |
| JDK | OpenJDK 11.0.33 (2026-10-20) |
| Ant | 1.10.12 |
| Local source copy | `/mydata/jingsong-cass-s4/o115/src` = `cp -a /mydata/s4/cassandra-base` (built `ant build-test` copy of `systems/cassandra/source/`, cassandra-5.0.9); the three cited source files byte-identical to the repo's at commit `cd9e1cded` |
| Case-file commit / harness | `bef6bc8a6` + amendments in `case-amended.md` (frozen sha256 `44851469…`) / harness outside the repo, not committed |
| Storage for node data | local `/mydata` (`/dev/mapper/emulab-node0--bs`) |
| Full logs | `~/writeup-ext/out/o115/raw/unit/`, `~/writeup-ext/out/o115/raw/cluster/` (on pc91 also `/mydata/jingsong-cass-s4/o115/out/`, logs only) |
| Node lock | `/mydata/s4/NODE-LOCK` acquired 22:40:04 MST, released at the end |

## 3. Runbook defects

None in this run. (Defect 1 of 2026-11-24, the JDK 11 module options, was already fixed in B2i.7 and the harness applies it.) Instrument check K0 (`explicit:1`, 3,000 × 60,000 B): `LIMIT_BYTES 1048576`, 166 resets (first at row 17 = 18 rows per sync), 167 `Data.db` — the known answer exactly (`raw/unit/unit-K0.log`).

## 4. Run 1

Scope: all of B2 (U1–U5) and B3 except optional W2. Command logs: `raw/unit/unit-driver-run.log`, `raw/cluster/cluster-driver-all.log`.

### 4.1 Readings

**Unit tier** (`raw/unit/unit-U*.log`)

| Run | LIMIT_BYTES | resets | maxObserved / lastObserved | `Data.db` | sizes | other |
|---|---|---|---|---|---|---|
| U1 default | 134,217,728 | 8 (rows 2235, 4471, …; 2,236 rows/sync) | 134,187,165 / 134,187,165 (∈ [134,157,628, 134,217,728]) | 9 | 8 × 134,222,608 B; 1 × 6,723,136 B | exit 0 |
| U2 `explicit:0` | 134,217,728 | 8 | 134,187,165 | 9 | as U1 | warning "A non-positive value for maximum SSTable size is specified, which disables the size limiting effectively" logged; exit 0 |
| U3 `explicit:32` | 33,554,432 | 32 | 33,501,762 (∈ [33,494,332, 33,554,432]) | 33 | 32 × 33,555,652 B; 1 × 6,723,136 B | exit 0 |
| U4 `explicit:2047` | 2,146,435,072 | 0 | 1,080,702,000 | 1 | 1,080,504,000 B | -Xmx3g; exit 0 |
| U5 `sorted` | −1,048,576 | — | — | 0 | — | `SSTableSimpleWriter`; exit 0 |

**Cluster tier** (`raw/cluster/<run>.log`, `gc-<run>.log`; H0 = 12.4 MiB in every run)

| Run (B) | peakLive − H0 | band (B3f) | last-third − first-third mean | flat bound | `Data.db` | big file | du -sb |
|---|---|---|---|---|---|---|---|
| C16 | **37.7 MiB** (39,542,368 B) | 14–37 | −0.9 MiB | 16 | 65 | 16,807,840 B (small 4,802,240) | 1,081,234,984 |
| C32 | 70.3 MiB | 29–74 | 3.3 MiB | 16 | 33 | 33,555,652 B | 1,081,068,637 |
| C64 | 133.8 MiB | 58–147 | 16.9 MiB | 32 | 17 | 67,111,304 B | 1,080,979,892 |
| C128 (default) | 257.1 MiB | 115–295 | 56.1 MiB | 64 | 9 | 134,222,608 B | 1,080,938,197 |
| CX (2047) | 1,038.8 MiB, rising linearly 15 → 1,039 over 72 samples | 950–1,250 | 692.4 MiB (≥ 400 needed) | — | 1 | 1,080,504,000 B | 1,080,870,746 |

`peakLive(C128) − peakLive(C16)` = 219.4 MiB (band 100–260). Max − min of peaks over C16–C128 = 219.4 MiB (row 3 needs ≤ 30). G1 log cross-check: highest heap after a full GC 50 MiB (C16) and 268 MiB (C128), i.e. 37.6 and 255.6 MiB above H0. The C16–C128 `LIVE` series are sawtooths (e.g. C128: ramps to 251 MiB, drops to 132, ramps to 253, …), not trends.

OOM sweep (`raw/cluster/oom-*.log`; exit 3 = `ExitOnOutOfMemoryError`, line "Terminating due to java.lang.OutOfMemoryError: Java heap space"; `OOM_LINES` counts include the logged `-XX:+ExitOnOutOfMemoryError` command line, so 1 = none):

| Run | -Xmx | exit | predicted |
|---|---|---|---|
| C128 | 256m | **3** (OOM) | fail ✓ |
| C128 | 384m | 0 | either |
| C128 | 512m | 0 | complete ✓ |
| C128 | 768m | 0 | complete ✓ |
| C16 | 256m | 0 | complete ✓ |
| CX | 768m | **3** (OOM) | fail ✓ |

Node ingest (`raw/cluster/load.log`, `node-system.log`): `sstableloader` exit 0, 36 files / 1.007 GiB streamed; `SELECT count(*)` = **18,000**; partition estimate 18,123 (±10% ✓); "Space used (live)" 1,080,867,135 B (1.08–1.12 × 10⁹ ✓); `du -sb data/probe` 1,391,130,709 B during an STCS compaction shown by `compactionstats` (≤ 2.3 × 10⁹ ✓); 0 `ERROR` lines in system.log.

### 4.2 Conclusion and logic

1. **Validity.** Valid. The limit was crossed repeatedly (8 resets at 128 MiB, 32 at 32 MiB) [observed: `unit-U1.log`, `unit-U3.log`]; same workload, compression off, fresh arrays in every run [observed: harness listing, `case-frozen.md` B2a]; K0 known answer exact [observed: `unit-K0.log`].
2. **Readings.** One out-of-band reading: C16 peak 37.7 MiB vs band 14–37 MiB (k = 2.36 vs ≤ 2.3) [observed: `C16.log` SUMMARY, `gc-C16.log`]. C128 flatness 56.1 MiB is within its 64 MiB bound but the metric includes the first buffer's ramp [observed: `C128.log`]. C128 at 384m completed (allowed either way).
3. **Matched row.** *Unit:* B2g row 1 (LIMIT 134,217,728, 8 resets, max ≤ cap, 9 files at 134,222,608 B within ±2% and 6.72 MB small file within 6.0–8.0 MB), U2 = U1 with the warning, row 5 (U3 → 32/33), row 7 (U4 0 resets, ~1.08 × 10⁹), row 8 (U5 −1,048,576) → B2i.6 **Confirmed (caps)**. *Cluster:* B3g row 5 holds in full; row 1 holds except that C16 is 0.7 MiB above its band; B3f file counts (65/33/17/9/1), totals and node count hold. B3i.4 requires every part of row 1 → **Not confirmed (no matching row)**.
4. **Excluded rows.** Unit row 2 (LIMIT ≠ cap) no; row 3 (max > cap / resets ≠ 8 / oversized file) no; row 4 (U2 unlimited) no — U2 LIMIT 134,217,728 with 8 resets despite the warning; row 6 (U3 unchanged) no. Cluster row 2 (C128 ≥ 600 MiB or upward trend) no — 257 MiB, sawtooth; row 3 (C16–C128 within 30 MiB) no — 219 MiB spread; row 4 (CX no rise / C16 needs > 256m) no; row 6 (C128 succeeds at 256m) no — exit 3; row 7 (C128 file > 1.1 × 128 MiB) no — 134,222,608 B; row 8 (count ≠ 18,000) no.
5. **Observed vs. inferred.** Inferred: the C16 excess comes from the fixed `DiskWriter` / `SSTableTxnWriter` overhead (A4 "other consumers"), which does not scale with B and is ≈ 5–6 MiB [inferred: 37.7 − 2 × 16.0 MiB; the excess in MiB is similar for C32 (70.3 − 64 ≈ 6) and does not grow with B]. Not used for the verdict.
6. **Deviations and gaps.** W2 (optional) not run. The instantaneous heap between samples is not observed (B3d). No other deviation.
7. **Core question.** Usage follows the constraint: buffered serialized bytes are bounded by the cap (unit), the writer's live heap scales with B (≈ 2 × B + ≈ 6 MiB) and stays flat in rows written, while with no binding cap it grows to ≈ 1 GiB; the OOM sweep shows the same workload's heap need is set by the cap (C128 dies at 256m, C16 lives at 256m, uncapped dies at 768m); each SSTable is ≈ 128 MiB at the default. The 128 MiB default does cap writer heap and per-file disk. The cluster tier's formal verdict is Not confirmed only because of the 0.7 MiB band miss at C16.

**Conclusion (one line):** unit — B2g row 1 (+ controls): **Confirmed — caps**; cluster — **Not confirmed (no matching row)** (C16 0.7 MiB over its band; all else matched).

## 5. Self-check of run 1

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `unit-K0.log` 166 resets / 167 files; `unit-U1.log`, `unit-U3.log` resets 8 / 32 |
| 2. Readings | yes | `C16.log` SUMMARY peakLive 52,551,744 − h0 13,009,376 = 39,542,368 B = 37.71 MiB; `gc-C16.log` 50M after full GC agrees |
| 3. Matched row | yes | re-read SUMMARY/EXIT/DATA_DB lines of all unit and cluster logs; B3i.4 read again: "each of C16–C128 in its B3f band" is a condition of Confirmed |
| 4. Excluded rows | yes | every B2g/B3g row addressed in 4.2 part 4 |
| 5. Observed vs. inferred | yes | the only inferred statement (cause of the C16 excess) is not used for either verdict |
| 6. Deviations and gaps | yes | W2 optional; no runbook defect |
| 7. Core question | yes | unit Confirmed → caps; cluster direction agrees (no contradiction), so the weak class rule applies, not "(cluster disagrees)" |

Run 2: not chosen. The run is deterministic in the deciding parts (counts, LIMIT_BYTES, exit codes), and the cluster verdict rests on a frozen band, which a repeat would not change.

## 8. Verdict

- **Unit tier: Confirmed — caps.** **Cluster tier: Not confirmed (no matching row) — undetermined**, direction caps.
- **Outcome class: weak true positive** (estimate positive; unit effect caps; cluster could not settle only because of the C16 band miss; it does not disagree).
- An owner override of the cluster tier to Confirmed (treating the 0.7 MiB / 1.9% miss at the smallest cap as within measurement of a fixed writer overhead) would make the class **true positive**; this session does not make that call, because the bands were frozen before any reading.
- Side finding (A1 quirk, confirmed at runtime): `withMaxSSTableSizeInMiB(0)` logs that it "disables the size limiting effectively", but the unsorted writer applies 128 MiB (U2: 8 resets, 9 files).

## Cleanup

All probe JVMs and the Cassandra node stopped (`no BufferCapProbe/CassandraDaemon running` at the end of each driver; `ps` on pc91 shows no process of this run); the monitoring `tail` on pc91 killed. Bulk data deleted on pc91 (`out/C128`, `src` incl. `data/`, `logs/`); `/mydata/jingsong-cass-s4/o115` keeps only `harness/` and `out/*.log` (644 KB). No detached driver was used. Node lock released.
