# trie_2gb_hard_limit-allocateblock-leadbit--autonomous — stage-4 results  <!-- file: results/trie_2gb_hard_limit-allocateblock-leadbit--autonomous.md -->

> **Case:** [`trie_2gb_hard_limit-allocateblock-leadbit--autonomous`](../../stage3-ai-deep-read/cases/trie_2gb_hard_limit-allocateblock-leadbit--autonomous.md)
>
> **Status:** **Self-checked 2026-10-27 — unit Confirmed (caps), cluster Confirmed (the soft guard switches the trie before the hard limit; no `SpaceExhaustedException`); one sub-prediction missed (the `direct` pool total, see 4.2 part 2); no run 2**
>
> **Outcome class:** true positive — estimate `positive`, effect `caps` (per trie; the node total is not bounded by this limit, as the case's estimate says)
>
> **Agent:** autonomous (B2 = unit tier, B3 = cluster tier, feedback = section D).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the whole file after the audit's amendments (6 dated blocks, 2026-10-27): `36b9e61409b9f2ab1bdb3a65db10ed759f9efc27f66c5d130166d8e9b5e0a33c` (`sha256sum`, taken before the unit run). Repository HEAD when the file was written: `68f9c3c`; the case file, harness and results are uncommitted in the working tree (no commit by this session). The file later gains section D (feedback), which changes its hash; the frozen text is everything above section D. |
| **Harness** | [`harness/trie_2gb_hard_limit-allocateblock-leadbit--autonomous/`](../harness/trie_2gb_hard_limit-allocateblock-leadbit--autonomous/README.md), uncommitted: `Trie2GbLimitProbeTest.java`, `unit-run.sh`, `RunOne.java`, `unit-control.sh` (B2); `make-node.sh`, `trie.yaml`, `Jmx.java`, `cluster-run.sh`, `analyze.py` (B3). **Instrument checks (not readings):** `javac` of the probe and `RunOne` against the build; `bash -n` of the four scripts; `ast.parse` of `analyze.py`, run on the calibration run's files (known answer: 100000 partitions, 0 errors, flush reason DRAIN, 0 trie-size signals) ; the in-tree test `testOver1GSize` passes in the run copy (known answer for the probe's edge arithmetic); one `ant testsome` shakedown of the probe (toolchain, see D1) and one 100000-key calibration run of the cluster script (sizing, amendment C). The output of both was seen before the freeze (disclosed in the case file's amendment (4)). |
| **Tiers and values** | Unit (B2): `OFF_HEAP` with the knob unset, `512`, `2047`; `ON_HEAP` unset; invalid `0` and `2048`; positive control `testOver1GSize`. Cluster (B3): single node, one shard, knob unset / `512` / `2047`, N = 1,088,000 / 300,000 / 1,197,000 inserts of 2000-byte keys, and the positive control `memtable_offheap_space: 512MiB` with N = 1,088,000. Both tiers kept. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A1/A2: bytes of one trie's buffers, heap or direct. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | The hard limit is a compiled constant (A1), so the knob that is varied is the soft threshold `row_overhead_size` (unset, 512, 2047, plus invalid 0/2048) and `BufferType`; B2b says why. The question answered is "does the hard limit hold whatever the soft threshold is". |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B2d lists the `direct` pool, NMT and heap next to the counter, but "not directly observable: `allocatedPos`" was wrong (reflection reads it) and `sizeOffHeap()` is 0 for `ON_HEAP`. Fixed by amendment (3) and (7). For the cluster tier the `direct` pool saturates at 2^31 - 256 once the 1 GiB buffer exists, so it cannot show an overshoot: amendment (D) adds the table metric `MemtableOffHeapSize` (same counter, named as a proxy) next to it. |
| A. Core question | usage driven to the limit and past it | Met (unit) / Partly (cluster) | Unit: `advanceAllocatedPos` reaches 2^31 - 256 in seconds on a 10 GiB heap. Cluster: the real memtable reaches the soft threshold (1.9 to 2.1 GB per trie) but is designed never to reach the hard limit; the design says so (B1 claim 2). The threshold `2047` leaves 1 MiB of headroom, the closest the real path can be driven to the hard limit with a configuration; kept as the stress arm. |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps are numbered with the reading each gives. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | B2f was right except for one block at the edge (the throw is the second allocation after 0x7FFFFEE0, not the first; the final value is exactly 2147483392) and for `ON_HEAP`; fixed by amendments (5)-(7). B3f's direct-pool sentence was wrong in kind (see "A. real resource"); fixed by amendment (D) and the B3f block. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g cover: throw point moves, counter beyond the limit, OOM, invalid knob accepted, no flush signal, exception in the log, direct total not rising, positive control. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Claim (1) needs the throw at the same `allocatedPos` for every knob value (B2g row 1) — the disallow branch is the thrown exception. Claim (2) needs the signal line and the absence of the exception (B3g row 1). |
| B. Logic | alternative explanations and their controls | Partly | B2h/B3h have `ON_HEAP` vs `OFF_HEAP`, the shard count, the `memtable_offheap_space` control. Missing: the memtable-wide cleaner firing before the trie threshold (with the shipped `memtable_cleanup_threshold` it would at about 2048 MiB of off-heap): added by amendment (A), and the control arm shows the cleaner with the flush reason and `SlabPoolCleaner` thread. |
| C. Specific | a human can follow it from the intro and B1/B2g/B3g | Met | A1-A4 and B1 are self-contained. |
| C. Specific | an AI can run B2a-B2e / B3a-B3e without re-deriving the code path | Partly | The probe, the node yaml and the workload tool were not specified to the level of a command; supplied by the harness and amendments (1), (2), (A)-(C). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | "e.g. a small Python/Java driver script or cassandra-stress", key counts "about 0.8 million": fixed to `cassandra-stress` and counts from the calibration (amendment C). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | Written in step 1 (this session); ant/JDK present on pc41. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met after amendment | Unit: 2 GiB direct or heap, seconds. Cluster: 837k to 920k keys at 2332 B each, 3.5 min per arm at about 6.2k inserts/s; 3.4 GB of SSTable per big arm against 55 GB free on `/`; 16 GiB heap, 10 GiB direct on a 251 GiB node. The case's 8 GB heap would have been tight (heap peaked at 8.6 GB in the runs: young-generation garbage, G1). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked in `cassandra/cassandra-5.0.9`: `InMemoryTrie.java:140-159` (allocateBlock, the `leadBit + BUF_START_SHIFT == 31` check at :148), `:58-67` (threshold, range 1..2047), `:90` (31 - BUF_START_SHIFT buffers), `:949-955` and `:961-965` (reached..., advanceAllocatedPos), `:969-981` (sizes), `InMemoryReadTrie.java:207-208`, `:231-234`; `TrieMemtable.java:192-205` (signal, IllegalStateException), `:478-484` (offHeap adjust); `CassandraRelevantProperties.java:356-357`; `DatabaseDescriptor.java:761-773` (cleanup threshold); `InMemoryTriePutTest.java:62-111`. All as cited. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Probe class name must end in `Test`; run through `java`/JUnitCore, not `ant testsome` (heap) | Applied 2026-10-27, amendment (1)-(2) | defect D1 |
| R2 | Read `allocatedPos` by reflection; `ON_HEAP` has `sizeOffHeap() == 0` | Applied, amendments (3), (7) | observable |
| R3 | Edge off-by-one: the throw is the second allocation after 0x7FFFFEE0; final value 2147483392 | Applied, amendment (5) | prediction wording |
| R4 | `direct` increase bounded by [allocatedPos, 2^31 - 256], not the absolute total | Applied, amendment (6) | other direct memory |
| R5 | Cleanup threshold 0.99, spaces 8192 MiB, heap 16G, direct 10g | Applied, amendment (A) | memtable-wide cleaner |
| R6 | Cluster observable `MemtableOffHeapSize`; key counts from a calibration | Applied, amendments (C), (D) and B3f block | direct pool saturates |
| R7 | Stage 3: when a trie case speaks of "the direct total", note two tries coexist during a flush (the node total is not bounded by one trie) | left for stage 3 | A4(a) already says so; the amendment-(D) sentence that missed is mine |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit 21:11-21:13 UTC; cluster 21:14-21:33 UTC) |
| Node | `pc41` = `node4.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB) |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK | openjdk 11.0.32.1 (2026-08-18) |
| Ant | 1.10.12 |
| Local source copy | `~/cassandra-run1` from `cassandra/cassandra-5.0.9/` at repository commit `68f9c3c` (tag `cassandra-5.0.9`), `ant build-test` BUILD SUCCESSFUL (1 min 55 s) |
| Case-file / harness commit | uncommitted (working tree of `68f9c3c`); case-file sha256 above |
| Storage for node data | `~/stage4-trie2gb/node` on local `/dev/sda3` (63 GB, 55 GB free at the end), removed after each arm; nothing under `/proj` |
| Full logs (outside the repo) | `pc41:~/stage4-logs/trie2gb/run1/{unit,cluster}/` (per arm: `samples.csv`, `system.log`, `stress.txt`, NMT summaries, `tablestats.txt`, `cmdlog.txt`); shakedowns in `~/stage4-logs/trie2gb/{shake,ant-shake.log}` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | 
|---|---|---|---|---|---|
| D1 | shakedown | B2a (`ant testsome ... -Dtest.jvm.args="-Xmx10g ..."`) | (a) `check-test-names` rejected `Trie2GbLimitProbe`: a class with `@Test` must be named `*Test`. (b) The test JVM's max heap was about 1 GiB although `-Xmx10g` was passed (`ant` appends its own heap setting after `test.jvm.args`); enough for `OFF_HEAP`, impossible for `ON_HEAP` and for `testOver1GSize`. | Class renamed `Trie2GbLimitProbeTest`; the probe runs through `java ... org.junit.runner.JUnitCore` with the run copy's classpath (`unit-run.sh`), flags otherwise unchanged. | Case-file amendments (1)-(2), 2026-10-27, before the freeze; claim, prediction and table unchanged. |
| D2 | cluster | B3a (`memtable_offheap_space: 6144MiB`, default `memtable_cleanup_threshold`) | The memtable-wide cleaner would flush at about 2048 MiB off-heap and 1365 MiB heap, on top of or below the trie thresholds. | cleanup threshold 0.99, spaces 8192 MiB, heap 16G (amendment A). | before the freeze. |
| D3 | cluster | B3d (direct pool as the usage observable) | saturates at 2^31 - 256 + other users once the 1 GiB buffer exists; cannot show an overshoot. | add `MemtableOffHeapSize` (amendment D). | before the freeze. |
| D4 | cluster | `cluster-run.sh` end-of-arm check | Printed `CassandraDaemon processes left: 1` after every arm: the check ran while the stopped daemon was still exiting (`pgrep -F` on a pid file that is removed at shutdown). Not a leftover: the next arm started on the same ports, and `ps -eo cmd \| grep '[C]assandraDaemon'` after the last arm printed 0 lines. | Not fixed in the script (the final manual check is the evidence); noted. | no effect on readings. |

## 4. Run 1

**Scope:** every B2 and B3 value listed in section 1. **Command logs:** `trie_2gb_hard_limit-allocateblock-leadbit--autonomous/run1/` (unit: `unit/*.out`, `control.log`; cluster: `cluster/<arm>/`, `cluster/cluster-all.log`). Abbreviations: HARD = 2^31 - 256 = 2147483392; P = `allocatedPos`.

### 4.1 Readings

**Unit tier** (all in `run1/unit/`)

| Test or assertion | Result | Evidence |
|---|---|---|
| `OFF_HEAP`, knob unset: threshold | 1951399936 (1861 MiB); `reached` false at thr - 0x1000, true at thr and thr + 0x1000, true at the edge | `off-default.out` lines `THRESHOLD`, `tag=after-thr*` |
| `OFF_HEAP`, 512 and 2047 | thresholds 536870912 and 2146435072; `reached` false at thr - 0x1000, true at thr | `off-512.out`, `off-2047.out` |
| Edge: `advanceAllocatedPos(0x7FFFFEE0)` | OK, P = 2147483360, in all four valid runs | `op=edge-0x7FFFFEE0` |
| `putRecursive(t3)` at the edge | `SpaceExhaustedException`; P 2147483360 -> 2147483392 (one block allocated, then the throw); t1 still readable, t3 null | `op=putRecursive-t3`, `CHECK read-t1=test1` |
| `advanceAllocatedPos(MAX_VALUE)` twice | both `SpaceExhaustedException` ("The hard 2GB limit on trie size has been exceeded"); P stays 2147483392 | `op=advance-MAX_VALUE-try1/2` |
| Phase 2, fresh trie: edge then `MAX_VALUE` | edge OK at 2147483360; `MAX_VALUE` throws, P 2147483360 -> 2147483392 | `op=B-advance-*` |
| Maximum P over all readings | 2147483392 = HARD in every valid run (knob unset, 512, 2047, `ON_HEAP`); never above | `tag=*` lines (script in 5.1) |
| `direct` pool | `OFF_HEAP`: 2147491587 at the edge, base 8195 at start (increase 2147483392 = HARD); at thr for knob 512: 1073749763 (whole buffers); `ON_HEAP`: 8192 throughout, heap 2.19 GB | `directUsed=` |
| NMT "Other" (direct) | 2097162 KB = HARD/1024 + 10 KB at the end of `OFF_HEAP`; 10 KB for `ON_HEAP`; heap 2184452856 to 2188647160 B for `ON_HEAP` | `nmt=[...]` |
| Invalid knob `0`, `2048` | `CLINIT_FAIL ... java.lang.AssertionError "cassandra.memtable.row_overhead_size must be within 1 and 2047"` | `bad-0.out`, `bad-2048.out` |
| Positive control `testOver1GSize` (`@Ignore` removed in the run copy, `-Xmx12g`) | `run=1 failures=0 ignored=0` (the in-tree test expects the same throws) | `control.log`, `control.diff` |

**Cluster tier** (all in `run1/cluster/<arm>/`; threshold bytes: default 1951399936, 512 -> 536870912, 2047 -> 2146435072; metric = `MemtableOffHeapSize`)

| Capacity value | Run | Observable | Reading | Evidence |
|---|---|---|---|---|
| default (1861 MiB) | N = 1,088,000, 0 stress errors | trie-size signal | 1 line "Scheduling flush due to trie size limit reached." at 21:17:33.70 UTC; flush `Reason: MEMTABLE_LIMIT`, `Usage: 1.818GiB off-heap` | `default/analysis.txt`, `system-log-excerpt.txt` |
| | | metric at/after the signal | sample before: 1944678665 (0.35% below the threshold); next sample 6766190 (new memtable) | `analysis.txt` |
| | | metric max / exception | 1944678665 < HARD (margin 202,804,727); 0 `SpaceExhausted`/`IllegalState` lines, 0 `ERROR` lines | `analysis.txt` |
| | | `direct` pool | start 62.8 MB; 2213708358 at the signal (= start + HARD + 3.4 MB); max 3288629895 after it | `analysis.txt`, `samples-excerpt.csv` |
| | | switch count | 1 (plus the final drain) | `tablestats.txt` |
| 512 | N = 300,000, 0 errors | signal / metric | 1 signal at 21:20:55.51; sample before 537100001; max 537100001 (threshold 536870912); flush `Usage 512.229MiB off-heap` | `k512/analysis.txt` |
| | | exception | none; `direct` max 1409611064 | same |
| 2047 | N = 1,197,000, 0 errors | signal / metric | 1 signal at 21:25:16.77; sample before 2138764799 (0.36% below the threshold 2146435072); flush `Usage 2.000GiB off-heap`; next sample 5591774 | `k2047/analysis.txt`, `samples-excerpt.csv` |
| | | headroom / exception | max 2138764799 < HARD, margin 8,718,593; 0 exception lines; `direct` max 3288628041 | same |
| control: `memtable_offheap_space: 512MiB` | N = 1,088,000, 0 errors | flushes | 4 flushes `Reason: MEMTABLE_LIMIT` by thread `SlabPoolCleaner`, each at `Usage 506.89 MiB off-heap` (0.99 x 512 MiB = 506.88); 0 trie-size signals; switch count 4 | `control512/analysis.txt`, `system-log-excerpt.txt`, `tablestats.txt` |
| | | metric max / `direct` max | 527207307 / 612853119 | same |
| all arms | | JVM | `vmflags.txt`: `MaxHeapSize=17179869184`, `MaxDirectMemorySize=10737418240`, `NativeMemoryTracking=summary`; shard count 1 set in `jvm-extra.txt`; `DESCRIBE TABLE` shows `memtable = 'trie'` | `vmflags.txt`, `jvm-extra.txt`, `cmdlog.txt` |

### 4.2 Conclusion and logic

1. **Validity.** The run is valid. The limit was reached in the unit tier: P = HARD in every valid run [observed: `off-*.out`, `on-default.out`, `tag=after-put-t3`]. In the cluster tier the soft threshold was reached in the three arms [observed: `*/analysis.txt` signals]; the hard limit is not reachable on that path by design (B1 claim 2), and the 2047 arm came within 8.7 MB of it in the sampled series [observed: `k2047/analysis.txt`]. Held-fixed settings: shard count 1 [observed: `jvm-extra.txt`; inferred that it took effect: one `Enqueuing flush of ks.t` per memtable with all 827,635 ops in one flush, `default/system-log-excerpt.txt`], `memtable = 'trie'` [observed: `schema.txt` via `cmdlog.txt`], off-heap buffers [observed: `Usage ... off-heap` in the flush lines and the metric rising with the writes], heap 16G / direct 10g [observed: `vmflags.txt`], cleanup threshold 0.99 [observed: `cmdlog.txt` conf line; control arm shows the cleaner then fires at 506.9 MiB].
2. **Readings.** (a) The amendment-(D)/B3f sub-prediction that the `direct` pool total stays within a few MB of start + HARD **missed**: it reaches 3288629895 (default) and 3288628041 (2047) and 1409611064 (512) after the flush signal [observed: `analysis.txt`]. [inferred: the old memtable's buffers (2^31 - 256 B) stay allocated while the flush writes them out, and the new memtable's trie allocates its own buffers meanwhile: 3288629895 - 62834891 = 3225795004 = HARD + about 1.07e9 (buffers 0..21 of the new trie, 2^30 - 256 = 1073741568) + 4.6 MB; this is the A4(a) "live memtables" case, two tries.] The per-trie metric did not exceed HARD in any sample. (b) Unit: in phase 2 the `direct` increase over the `start` reading is 2147483389, 3 bytes under HARD, because phase 2 has a different baseline of other direct buffers (8192 versus 8195 at `start`) [observed: `off-*.out` `B-after-MAX`]; the amendment-(6) bound holds up to this 3-byte baseline difference. (c) Heap peaks of 8.6 GB in the cluster arms are G1 young-generation garbage from 2 KB keys [inferred: GC count 3 and live data 262-288 MiB on-heap in the flush lines]. (d) The control arm's rate was lower (4.4k vs 6.2k ops/s) because of four flushes [observed: `stress-summary.txt`].
3. **Matched row.** Unit: B2g row 1 "Throw occurs at `allocatedPos` = 2^31 - 256 for every knob value; reading does not grow after": P = 2147483392 at the first throw-out and after both `MAX_VALUE` calls for the knob unset, 512, 2047 and `ON_HEAP` [observed: `off-default.out`, `off-512.out`, `off-2047.out`, `on-default.out`, line `final-allocatedPos`]. Supporting rows: "Direct buffer total keeps growing in step" (increase = whole buffers, equal to HARD at the end) and "0 / 2048 raise AssertionError" [observed: `bad-*.out`]. Cluster: B3g row 1 "Flush signal at the threshold, peak ... below the hard limit, no exception": signal in all three arms, metric at the last sample before the signal 0.35% below / 0.04% above / 0.36% below the threshold, max below HARD, 0 exception lines [observed: `*/analysis.txt`]; the positive control row (flushes early, trie-size line absent) [observed: `control512/analysis.txt`].
4. **Excluded rows.** B2g "throw point moves with the knob / counter above HARD": P identical for all knobs and never above [observed: the four `.out` files]. "OOM before the limit": no OOM, `DONE` in each file [observed]. "0/2048 do not raise": both raised [observed]. B3g "peak above HARD": metric max 2138764799 [observed]; "`IllegalStateException` caused by `SpaceExhaustedException`": 0 lines in four logs [observed: `system-log-excerpt.txt` empty of such lines]; "no flush signal, workload finished below threshold": signals present [observed]; "direct total does not rise": it rises [observed]. The `direct` row "peak direct total above HARD" is the one the data meets (3.29e9) but its stated explanation, a second trie, is the one in 4.2 part 2, so it does not refute claim (1) [inferred, see part 5].
5. **Observed vs. inferred.** Inferred: (i) the metric `MemtableOffHeapSize` equals the live trie's `allocatedPos` (from `TrieMemtable.java:478-484` and the unit-style check that 100000 keys give 233229024 B in the calibration; no second independent reading of `allocatedPos` in a live node); (ii) the post-signal `direct` excess is the second trie; (iii) that the switch happened within the 1 MiB headroom of the 2047 arm rests on the 1 Hz series plus the absence of the exception (the exception is the decisive, observed evidence).
6. **Deviations and gaps.** `ant testsome` replaced by `java`/JUnitCore (D1). The B3f/B3e sentence "writing doubles the keys beyond the threshold ... changes the number of flushes, not the peak": only 1.3x was written, so the second memtable's peak (580-669 MiB) never approached a threshold and the "doubling" claim was not tested. The cluster tier cannot drive the real path to the hard limit by design; it shows that the soft guard wins the race at 6.2k inserts/s with one writer shard, not that no workload could win it (a faster writer, a stalled flush executor, or the SAI tries, which have no soft guard, are not tested). The 1 Hz resolution cannot see a sub-second peak. One run per arm, no repeats.
7. **Core question.** Does the constraint cap usage? Yes, per trie: with three soft thresholds and both buffer types the buffer space of one `InMemoryTrie` stops at exactly 2^31 - 256 bytes and the next allocation throws, with the real buffers (direct pool, NMT "Other", heap for `ON_HEAP`) growing in step up to that point (parts 3-4, unit). In a node the soft guard switched the memtable before the limit in every arm, even at 2047 MiB with 1 MiB of headroom, so the hard limit is a backstop that was not reached (part 3, cluster). It does not bound the node total: two tries coexisted during a flush and the `direct` pool reached 3.29 GB (part 2).

**Conclusion (one line):** Unit B2g row 1 — confirmed (caps); Cluster B3g row 1 — confirmed (soft guard prevents reaching the hard limit), with the amended direct-pool sub-prediction missed (second trie during flush).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Raw files re-opened 2026-10-27 from `run1/`: all four unit `.out` files with a script (max P, flip lines, direct increase vs [P, HARD]), `bad-0.out`, `bad-2048.out`, `control.log`, and for each arm `analysis.txt`, `system-log-excerpt.txt`, `samples-excerpt.csv`, `stress-summary.txt`, `tablestats.txt`.

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | `vmflags.txt` shows 17179869184 / 10737418240 / NMT; `jvm-extra.txt` shows `shard.count=1`; control arm's `SlabPoolCleaner` lines at 506.89 MiB confirm the cleanup threshold took effect (0.99 x 512). |
| 2. Readings | yes | The script over the unit files found the only exceptions to "increase in [P, HARD]" at phase 2 `B-after-MAX`, -3 bytes (baseline 8192 vs 8195): as recorded. Direct arithmetic for the cluster excess re-computed: 3288629895 - 62834891 - 2147483392 = 1078311612 = 2^30 - 256 + 4.57 MB: holds. |
| 3. Matched row | yes | `final-allocatedPos=2147483392` in all four valid unit files; `sizeBefore`/`posAfter` of the throws as quoted; signal lines and "0" exception lines in all four arm excerpts. |
| 4. Excluded rows | yes | `system-log-excerpt.txt` of each arm contains only `Enqueuing flush` lines (no exception, no ERROR); no OOM text in the unit logs. |
| 5. Observed vs. inferred | yes | The inference (i) is the weakest: the metric and `allocatedPos` are the same field via the allocator; flush `Usage` figures (1.818 GiB = 1951 MB at the default signal; 512.229 MiB at 512; 2.000 GiB at 2047) are the memtable's own accounting and agree with the thresholds to 0.1%, which supports it. |
| 6. Deviations and gaps | yes | The "doubling" claim and the faster-writer race are listed as untested; no statement in 4.2 depends on them. |
| 7. Core question | yes | Steps follow B1: (1) unit table, (2) cluster signal + no exception. The conclusion says "caps per trie, not the node total", the same as the case's estimate caveat. |

### 5.2 Run 2?

**No** (2026-10-27). The unit tier's result is an exact value (2147483392) repeated in four independent JVMs and matching the in-tree test; the cluster result is the absence of an exception in three arms with a working positive control. The weakest inference is (i) above and a second run would not change it.

## 6. Run 2

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps).

**Claim tested:** (1) One `InMemoryTrie` never holds more than 2^31 - 256 bytes of buffer space: `allocatedPos` stops growing at that value and the next allocation throws `SpaceExhaustedException`, with the allocated buffer memory growing in step. (2) In a running node with the default configuration the trie memtable is switched at the soft threshold, so the per-trie buffer memory stays below the hard limit and `SpaceExhaustedException` is not reached on the normal write path.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1: throw at 2^31 - 256 for every knob value, no growth after) | caps | run 1 + self-check | 2026-10-27 |
| Cluster | Confirmed (B3g row 1: flush signal at the threshold, metric peak below the hard limit, no exception; positive control moved) | caps (soft guard keeps the trie under the hard limit; node total not bounded by it) | run 1 + self-check | 2026-10-27 |

**Feedback filed:** the case file's section D updated (no commit by this session); amendments 2026-10-27 in B2a, B2c, B2f, B3a, B3c, B3f. Missed sub-prediction: the `direct` pool total during a flush (two tries).
