# trie-pathreconstructor-keybytes-growth--autonomous — stage-4 results  <!-- file: results/trie-pathreconstructor-keybytes-growth--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`trie-pathreconstructor-keybytes-growth--autonomous`](../../stage3-ai-deep-read/cases/trie-pathreconstructor-keybytes-growth--autonomous.md)
>
> **Status:** verdict filed 2026-10-25 (run 1, unit then cluster, self-checked; no run 2). Estimate negative. Unit **Confirmed — does not cap** (on the text amended at R9; see §1 and §3); cluster **Confirmed — does not cap**. Run by the autonomous stage-4 session (tag tp33) on `pc07` (node0).
>
> **Outcome class:** **true negative** (stage-3 estimate `negative`; stage-4 effect on the constraint: `does not cap`, both tiers) — [definition](../README.md#outcome-class)
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
| **Case-file version** | Autonomous file, untracked in the repository at HEAD `f33e621`. As filed (2026-10-25): sha256 `f63a3a522be2e79b60005f558baf3b7f782fb137af5daf7ed308646fe67acae7`. **Version 1**, after the step-0 audit amendments R1-R8 (case-file section B5 and dated in-place edits, written before any reading): `60e72bb7a0da3c226f5adce42f5678a895d18020e2d8e9585de257b7f58e2c72`; frozen prediction and conclusion tables (B2f, B2g, B3f, B3g text extracted with `sed -n '/^\*\*B2f\./,/^\*\*B2h\./p'` and the B3 pair, last line dropped): sha256 `383252ce16d221d5f760235d6d8782f5876302d1ab0bab35581d25fb81e76c66` (copies `~/s4-tp33-logs/case-frozen.md`, `frozen-tables.txt`). **Unit run 1a** ran on version 1. It failed B2f (2) and (3) for the all-0x00 key only (path L+12, not about 2L+c): an error in R3's own reading of the zero escape (`ByteSource.java:329-376`: one extra byte per run of zeros, not per zero). **R9** (case-file B5, dated 2026-10-25, **written after run 1a's readings**, an amendment the README's compare-and-decide table allows for "no row fits" and the "mistake that does not depend on the readings" rule only in part: the correction is derived from the source text, but it was found by the readings) restates only those two zero-key sub-parts. **Version 2 (the frozen version for everything below, and the hash for `_INDEX.md` §4, before the section D feedback): `7378eec190e23d6e74a44e4f356d349a1965f1369a21cbbab520131d9e24fb8b`**; tables sha256 `7bbb0831fddb620b0453ac49058affa37cd30a7c0a7c259205d04fcb4a691e77` (copies `case-frozen-v2-R9.md`, `frozen-tables-v2-R9.txt`). The unit tier was run again from the start on version 2 (run 1b); the cluster tier ran once, after R9, on version 2 (no cluster text changed in R9). No prediction or conclusion row was changed after any cluster reading. After the verdict the case file's section D (feedback) was filled, which changes only the whole-file hash: `2ae2a52d77f88cfa8fa3f4b1c6d7cd1eef4e7c23c5d1afd442dbfe70163a2f3b` (version 2 plus section D; the tables are unchanged). |
| **Harness** | [`harness/trie-pathreconstructor-keybytes-growth--autonomous/`](../harness/trie-pathreconstructor-keybytes-growth--autonomous/README.md), written 2026-10-25 after the version-1 freeze, not committed (the orchestrator commits): `PathReconstructorSizeTest.java`, `unit-run.sh`, `unit-analyze.py`, `trie-growth.btm`, `client.py`, `Jmx.java`, `cluster-run.py`, `cluster-analyze.py`, `selfcheck.py`, `README.md`. md5 list at the start of the cluster run: `results/trie-pathreconstructor-keybytes-growth--autonomous/run1/harness.md5` (`selfcheck.py` was edited once after the run, only its leftover-process test; `unit-analyze.py` was edited at R9). **Instrument checks (shakedowns, not readings):** `shake1` (scale 50, H64): the node reported `statusbinary running` about seven seconds before the native port accepted a connection, so every client call failed (runbook defect D1 below); `shake2` (scale 50, H64): lines written, lengths 64..65536, analyzer and self-check ran end to end on 38,808 trace lines (its metric rows are not readings). The unit test was compiled and first run as run 1a (a reading). |
| **Tiers and values** | Both tiers. Unit: L in {8,31,32,33,1000,32768,65535}, raw and real-`DecoratedKey` paths, ON_HEAP/OFF_HEAP, N in {1,8,64}, M in {10k,100k} at L=100. Cluster: `memtable_heap_space` 64/256/1024 MiB, t_big (60,000-byte keys) and t_small (16-byte), R in {1,32}; heap_buffers, plus an offheap_objects run. Tree `~/s4-tp33`, node data `~/s4-tp33-run/`, ports JMX 7210, Byteman 9110, native 9142, storage 7010, loopback 127.0.33.1. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-25 |

### 1.1 Design audit

Checked against the pinned source `cassandra/cassandra-5.0.9/` (read only; `git status cassandra/cassandra-5.0.9` empty). The write-up was by a design-only agent; its line cites and arithmetic were re-read.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A1/A2: on-heap bytes of a transient scratch array (32 B initial, hard-coded); there is no configured constraint, the nearest limit is the key size 65535 (`Validation.java:51-55`). Counts as a byte quantity with a derivable size. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B1/B2b: the knob cannot be varied (constant); the design varies the key length L (7 values), `memtable_heap_space` (3 values) and the buffer type, and asks whether the array follows any memtable setting. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after R5 | Unit: `cap()` of the real array (reflection-free subclass). Cluster: JFR (as filed) cannot be used on JDK 11 and is sampled; replaced by a Byteman trace of every growth (exact lengths) plus `GC.class_histogram`; the retained scratch is inferred (≤ (R+4) x 2P). |
| A. Core question | usage driven to the limit and past it | Met (nothing to reach) | There is no limit; "past" is the 65535-byte key at the unit tier and 60,000-byte keys in the cluster. The array bound the source gives is P <= cap <= 2P (R3). |
| A. Core question | positive control present (negative-estimate file) | Met | B2h/B3h and R7: the accounted trie size rises with M and L while `cap()` does not; `memtable_heap_space` moves memtable size and flush count in the same runs. |
| B. Logic | each step says what it establishes | Partly | B2e/B3e are procedures; the hypothesis B1 and the rows of B2g/B3g carry the logic (mapped as the README says). |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after R3/R5 | Filed numbers were wrong (131072 bound, power-of-two staircase, 64..65536 sizes, 128 KiB per iterator). Restated as the invariant P <= cap <= 2P and exact equalities (sizes unchanged by the drain). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | Confirmed; refuted by accounting or by dependence on a setting; mis-traced; control did not move / scans never ran (Not confirmed). 'Counter capped but resource grows' is the last row of the unit set (accounted size unchanged while `cap()` grows). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The claim is that there is no ceiling and no disallow branch (A3.6); the direct evidence is the traced growth (no refusal, no limit consulted) and the size-accounting equalities. |
| B. Logic | alternative explanations and their controls | Met | Accounting (sizes before/after drain), flush threshold effects (the control), buffer type, garbage vs retained (inferred, named). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3, B1, B2g/B3g. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after R4 | The test is described, not given; API names were wrong (`ByteComparable.of`, `usedSize*`). Fixed; the harness supplies the code. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after R6 | B3 omitted the stop condition of the scans and used `pgrep -f` for cleanup; the harness kills by PID. Scan time and volume fixed in R6. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | None exists; unit test, Byteman rule, driver script, JMX poller are listed work for step 1. JDK 11.0.32.1, Ant 1.10.12, Byteman in `build/lib/jars` (`environment.md` §4). Paths `/localscratch` do not exist on the nodes: local disk under `~`. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly → Met after R6 | 5,000 x 60,000 B = 300 MB of keys; the trie stores them in 32-byte chain blocks of about 28 key bytes, roughly 345 MB per full table in a memtable; with 1,000,000 x 16 B small keys about 100 to 150 MB; local disk 41 GB free. Flush starts at a fraction of the pool (about one third): about 21 MB at 64 MiB, 85 MB at 256 MiB, 341 MB at 1024 MiB, so the settings differ in flush count. 10-minute scans x 3 settings was too long; 3 minutes (R6). 2 GiB heap holds a 1024 MiB pool. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Partly → Met after R1/R2 | Re-read: `TriePathReconstructor.java:21-56`, `TrieEntriesIterator.java:30-86`, `TrieEntriesWalker.java:9-43`, `Trie.java:195-225, 427-436`, `InMemoryReadTrie.java:540-590`, `InMemoryTrie.java:88, 855-885, 960-985`, `TrieMemtable.java:98, 340-400, 470-490, 535-560`, `DecoratedKey.java:104-133`, `ByteSource.java:101-163`, `Validation.java:45-60`, `Config.java:183-190`. Cites off by one to two lines (R1), `usedSize*` method names (R2), the 65535 path bound (R3, the unverified item: false) and the line 'TrieMemtable flush/range-read sites' (R1: `:356` and `:392` flush, `:552` range read) corrected. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Correct the line cites (A1, A3, B2c) | Applied 2026-10-25 (case file; not committed) | spot-check |
| R2 | `usedSizeOnHeap/OffHeap` -> `sizeOnHeap()/sizeOffHeap()` (`:975/:969`) | Applied 2026-10-25 | the methods filed do not exist |
| R3 | Replace the 65535/131072 path bound by P <= cap <= 2P (path = escaped `DecoratedKey`, longer than the key) | Applied 2026-10-25, before the freeze | the 65535 bound is on the key; a 65535-byte key has path > 65535 |
| R4 | Test API: `ByteComparable.fixedLength`, real `DecoratedKey`s; `new InMemoryTrie<>(BufferType)` | Applied 2026-10-25 | `ByteComparable.of` does not exist |
| R5 | Drop the power-of-two staircase; restate B2f numerically; JFR -> Byteman trace on both growth methods | Applied 2026-10-25 | `addPathBytes` can give `newPos+16`; JDK 11 has no `ObjectAllocationSample` |
| R6 | Cluster: 1,000,000 small partitions, 3-minute scans, no 0x00 in keys, flush-threshold wording | Applied 2026-10-25 | time/arithmetic; escaping |
| R7 | Record the controls | Applied 2026-10-25 | negative-estimate file |
| R8 | Freeze the tables | Applied 2026-10-25 | protocol |
| R9 | Rename the unit-tier 'stays at 128' (done in R5); the `Ground` line's '~128 KiB per live iterator' remains in the stage-3 header and is superseded by R3 | Left for stage 3 | header text, not a design element |

**Agreement criteria** — no run 2 chosen so far.

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-25 (unit 1a 19:33 EDT, unit 1b 19:35, cluster 19:41 to 20:25) | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB; shared with other stage-4 sessions (own tree, ports and loopback) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, 5.15.0-187-generic | |
| JDK (`java -version`) | openjdk 11.0.32.1 2026-08-18 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-tp33` by `copy-source.sh` at repository HEAD `f33e621` (tag `cassandra-5.0.9`, local baseline), `ant build-test` BUILD SUCCESSFUL in 1 min 8 s (`~/s4-tp33-logs/build-test.log`) | |
| Case-file commit / harness commit | case file untracked (sha256 in §1); harness untracked | |
| Storage for node data | local disk `/dev/sda3` (`~/s4-tp33-run/`), 39 GB free at the start; peak about 0.95 GB; JDK heap 2 GiB (`-Xmx2G`), G1; ports JMX 7210, Byteman listener 9110, native 9142, storage 7010 (SSL 7011), loopback `127.0.33.1` | |
| Full logs (path, outside the repo) | `~/s4-tp33-logs/run1a/unit`, `run1b/unit`, `run1/cluster/` (one directory each for H64, H256, H1024, O256) (trace, 33 to 34 raw class histograms, series, `system.log` segment, `gc-*.log`), `cluster-run1.out`; excerpts under `results/trie-pathreconstructor-keybytes-growth--autonomous/run1/` | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | cluster shakedown `shake1` (not a reading) | B3e step 2 "wait for `nodetool status` UN" | `nodetool statusbinary` printed `running` about 7 s before the native port accepted connections (Netty started listening at 23:37:56 UTC, `UN` + `running` seen at 23:37:49), so the first client call got `Connection refused` | harness waits for a TCP connect to the native port (also an environment lesson for `environment.md` §6) | 2026-10-25; harness only, no case-file text | none |
| D2 | unit run 1a | B2f (2) and (3) | the frozen text said the all-0x00 key has path about 2L+c; measured L+12 (same constant as the random keys). R3's own description of the escape was wrong (one extra byte per run of zeros). | R9: the two zero-key sub-parts restated from `ByteSource.java:329-376`; unit tier rerun from the start as 1b | 2026-10-25, **after** run 1a's readings; the strict reading is in §4.2 and §8 | none (case file untracked) |

## 4. Run 1

**Scope:** both tiers. Unit: run 1a (version 1, kept) and run 1b (version 2, the run that counts), 139 `TP33` lines each, identical (`diff` of the two outputs is empty apart from the allocation counters). Cluster: four lifetimes, 1,000,000 x 16-byte and 5,000 x 60,000-byte partitions each, 180-second scan phases at R = 1 and R = 32, 60-second t_small scan. **Command log:** `results/trie-pathreconstructor-keybytes-growth--autonomous/run1/` (`unit-1a/summary-as-run.txt`, `unit-1b/summary.txt`, `cluster/session.log`, `cluster/cells.jsonl`).

### 4.1 Readings

**Unit tier** (run 1b, `unit-1b/tp33-unit.txt`; `unit-1b/analysis.txt` has every `EXPECTED:` line; `P` = longest path walked, `c` = P - L for random keys)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| JUnit `PathReconstructorSizeTest.grid` | 1 test, 0 failures, 0 errors, 17 s | `unit-1b/TEST-...xml`, `unit-1b/summary.txt` |
| B2f (1) cap = 32 if P <= 32, else P <= cap <= 2P | holds at all 126 grid points (3 key kinds x 2 buffer types x 7 lengths x 3 repetitions); e.g. raw L = 33 -> cap 64, raw L = 1000 -> 1024, raw L = 32768 -> 32768, real L = 32768 (P = 32780) -> 65536 | `unit-1b/tp33-unit.txt` |
| B2f (1b) P at insert time equals the path walked | 0 mismatches | same |
| B2f (2) L = 65535 | raw: P = 65535, cap = 65536; real random: P = 65547, cap = 71680; all-0x00: P = 65547, cap = 72704 (ON_HEAP and OFF_HEAP the same) | same |
| B2f (3) c | P - L = 12 for every real random key and every all-0x00 key at every L | same |
| B2f (4) sizes unchanged by the drain | `sizeOnHeap()` and `sizeOffHeap()` equal before and after in 139/139 rows; e.g. three raw 65535-byte keys: onHeap 225,700 B before and after | same |
| B2f (5) M control, L = 100 | ON_HEAP `sizeOnHeap()` 1,578,392 B at M = 10k -> 14,497,912 B at M = 100k (x9.2); OFF_HEAP `sizeOffHeap()` 1,537,088 -> 14,096,416 (x9.2); cap 128 at both M | same |
| B2f (6) ON_HEAP vs OFF_HEAP | cap identical in all 63 (kind, L) pairs | same |
| B2f (7) N iterators in N threads, L = 65535 real | per-thread allocation 145,856 B (N = 1, 8, 64) >= cap 72,704 B; sum 9,334,784 B at N = 64 | same |
| Repetitions | the 3 repetitions agree at every grid point | `unit-1b/analysis.txt` |
| Run 1a (version 1 text) | B2f (1), (1b), (4)-(7) hold; (2) and (3) fail for the all-0x00 key only (path L+12) | `unit-1a/tp33-unit.txt` (same lines as 1b) |

**Cluster tier** — one row per capacity value and observable (all from `run1/cluster/<life>/`; `analysis`: `cluster-analysis.txt`). P_big = 60,012 (60,000 + c), P_small = 28.

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| `memtable_heap_space` 64 MiB, heap_buffers | A (scan_big_R1, R32) | traced `keyBytes` growth lengths, t_big phases | 117,095 growth lines in all; every iterator grows through 64, 128, ..., 65536 (11 steps, 10,645 each); max 65,536 (<= 2 x 60,012) | `H64/growth-trace-lengths.txt`, `cluster-analysis.txt` |
| 256 MiB | A | same | 193,182 lines; same 11 lengths; max 65,536 | `H256/growth-trace-lengths.txt` |
| 1024 MiB | A | same | 266,475 lines; same 11 lengths; max 65,536 | `H1024/growth-trace-lengths.txt` |
| offheap_objects, heap 256 MiB, off-heap 256 MiB | A | same | 219,483 lines; same 11 lengths; max 65,536 | `O256/growth-trace-lengths.txt` |
| all four | control (t_small, 16-byte keys, P = 28 <= 32) | growth during load_small and scan_small_R1 | 0 growth lines in both phases, in all four lifetimes (the 32-byte initial array suffices) | `cluster-analysis.txt`, `*/phases.csv` |
| 64 / 256 / 1024 MiB | control (memtable limit binds) | max t_big `MemtableOnHeapDataSize` (load_big..scan_big_R32, JMX every 2 s) | 8.63 MB / 55.13 MB / 218.46 MB; O256 on-heap 0.27 MB, off-heap max 58.56 MB | `*/series.csv`, `cluster-analysis.txt` |
| 64 / 256 / 1024 MiB / O256 | control | t_small flushes during its load (`MemtableSwitchCount` change) | 17 / 4 / 1 / 3 | `*/series.csv` |
| 64 / 256 / 1024 MiB / O256 | control, real resource | class histogram `byte[]` bytes after load_big | 53.2 MB / 194.4 MB / 490.0 MB / 11.9 MB (off-heap trie) | `*/histo-*.txt` (raw, on the node), `cells.jsonl` |
| all four | scans ran | scan phase rows, errors | R1: 47,801 to 138,601 rows, 0 errors; R32: 632,831 to 2,285,732 rows, 0 errors; ReadStage threads with growth in R32: 82 to 86; flush-writer growth in every scan phase | `cells.jsonl`, `phases.csv` |
| all four | validity | `system.log` ERROR/OOM, loads | 0 ERROR lines; loads 1,000,000 and 5,000 acknowledged, 0 errors; leftovers none | `*/system-log-errors.txt`, `cells.jsonl` |

### 4.2 Conclusion and logic

1. **Validity** — **[observed: `cluster/*/cassandra.yaml`, `system.log` segment lines `memtable_heap_space=…`, `JVM Arguments`]** each lifetime ran with its intended allocation type and pool size, `-Xmx2G`, the Byteman agent and the trace rule loaded (trace files non-empty); **[observed: `cells.jsonl`]** all loads completed without error and every scan phase read rows without error; **[observed: `*/phases.csv`, `growth-trace.txt`]** growth lines occur inside the scan_big phases (ReadStage threads) in all four lifetimes, so the scans exercised the traced path; **[observed: unit-1b]** L = 65535 was reached. The memtable-size control moved (below). The unit tier is valid on version 2; on version 1 (run 1a) it was valid for everything except the two zero-key sub-parts. The run is valid.
2. **Readings** — **[observed]** the only unusual points: the real 65535-byte key's array is 71,680 B (not a power of two: a first `addPathBytes` growth gives `newPos + 16`), while in the cluster every iterator reached exactly 65,536 by doubling; the t_big phases include flush-writer iterators in every lifetime, including during load_big at 64 and 256 MiB; ReadStage thread names rotate (82 to 86 names with growth in a phase), so thread names do not give the concurrency (live iterators are inferred, not counted). The O256 lifetime's t_big on-heap datasize is near zero because the trie is off-heap, yet the scratch lengths are the same.
3. **Matched row** — unit: B2g row 1, *"B2f (1) to (6) hold: `cap()` is set by the longest path P only (inside P <= cap <= 2P), sizes unchanged by the drain, sizes rise with M while `cap()` stays in the band"* — **[observed: `unit-1b/analysis.txt`]** (1) 126/126, (4) 139/139, (5) x9.2 with cap 128, (6) 63/63. Cluster: B3g row 1, *"The traced growth lengths independent of `memtable_heap_space` (largest per table equal within one growth step) and set by L; the memtable size scales with the setting (control moved)"* — **[observed]** largest traced length 65,536 in all four lifetimes (ratio 1.0); t_small shows no growth; memtable size 8.6 / 55.1 / 218.5 MB for 64 / 256 / 1024 MiB and t_small flushes 17 / 4 / 1.
4. **Excluded rows** — unit: *refuted: sizes change when the iterator is drained* — **[observed]** 139/139 rows equal; *`cap()` depends on M or a memtable setting at fixed L* — **[observed]** cap 128 at both M, unit tier has no memtable setting, cluster tier below; *mis-traced, cap outside P..2P* — **[observed]** 0 of 126 points; *Not confirmed (control did not move or L not reached)* — **[observed]** sizes rose x9.2 and L = 65535 was reached in every kind. Cluster: *refuted, lengths move with the setting* — **[observed]** one value (65,536) at 64, 256, 1024 MiB and offheap_objects; *mis-traced, a length above 2P or another growth path* — **[observed]** the trace holds only the 11 power-of-two lengths up to 65,536 <= 120,024, and only from the two traced methods; *Not confirmed (control did not move, scans never ran)* — **[observed]** memtable size and flush counts moved with the setting and growth lines are present in every scan phase.
5. **Observed vs. inferred** — **[inferred: from the executors and the per-iterator maximum]** the peak scratch alive at once is at most (R + 4) x 2 P_big, about 4.3 MiB at R = 32: the trace gives each iterator's maximum, not how many were alive together. **[inferred: the iterator's array is garbage after the page]** that the arrays are not retained; the histogram `byte[]` total is dominated by memtable and read buffers and cannot isolate them. **[inferred: Java semantics]** that the scratch is on-heap in the offheap_objects mode (the trace shows a `byte[]` of the same lengths in O256). **[inferred: B1]** that the memtable allocator does not charge the array: observed directly only in the unit tier (sizes unchanged by the drain); the cluster tier shows lengths independent of the pool size.
6. **Deviations and gaps** — the workload follows the amendments (1,000,000 small partitions, 3-minute scans, keys without 0x00; R6); a lifetime used one table size, so the dose-response over L at cluster scale has two points (16 and 60,000 bytes), the finer one is the unit grid; no direct count of live iterators; JFR not used (JDK 11, R5); the unit tier was run twice with the R9 amendment after run 1a (§1, §3).
7. **Core question** — Following the logic of the case's B1 block: the array's length follows only the longest path walked (P <= cap <= 2P at all 126 grid points; always 65,536 for the cluster's 60,012-byte paths), it is not part of the trie's accounted size (139/139 rows unchanged by the drain), and it did not move with `memtable_heap_space` (64, 256, 1024 MiB) or with the allocation type, while the memtable size and the flush count did move in the same runs (positive control). No configured constraint caps it; it does not follow one.

**Strict reading.** On the text frozen at R8 (version 1), unit run 1a matches no B2g row exactly: its Confirmed row requires B2f (1) to (6), and (2) and (3) failed for the all-0x00 key. The failure is in an auxiliary sub-claim (an extra-length estimate for one key kind), none of the claim-deciding parts (cap bound, accounting, control) failed, and run 1b on the R9 text, whose only change is those two sub-claims, matched. The verdict below is on version 2 and says so; if R9 is rejected the unit tier is *Not confirmed* on version 1 with the same effect finding (does not cap).

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 — Confirmed (claim: usage does not follow the constraint).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Independent script `selfcheck.py` (own parsers, does not read the analyzers' output), output in `results/trie-pathreconstructor-keybytes-growth--autonomous/run1/cluster/selfcheck-cluster.txt` and, for the unit tier, run on `unit-1b` (ALL PASS); plus a re-read of the raw files by hand where noted.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | per lifetime: yaml and the node's own `Node configuration` line show the intended `memtable_allocation_type` / `memtable_heap_space` and `JVM Arguments` with the Byteman agent and `-Xmx2G` (selfcheck PASS x24); `system.log` segments have 0 `^ERROR`; phase windows from `phases.csv` match `cells.jsonl` records; no tp33 process left (read from `/proc`). |
| 2. Readings | yes | trace re-read: 11 distinct lengths 64..65536 in every lifetime, none above 2 x 60,012; byte growth never shrinks per iterator; `series.csv` max t_big on-heap size 8.2 / 52.6 / 208.3 MiB (whole series) for 64 / 256 / 1024, 0.3 MiB for O256. The reading that thread names do not give concurrency stands. |
| 3. Matched row | yes | unit: the independent script recomputed cap vs P (130 rows with a path) 0 outside, sizes unchanged 139/139, c = 12 only, M control x5 or more, allocation sum >= N x cap; cluster: largest length per lifetime equal (65,536). |
| 4. Excluded rows | yes | each excluded row has its reading in 4.2.4; the raw histogram peak `byte[]` (162 to 467 MiB) is memtable and read-buffer dominated and is not used to exclude anything. |
| 5. Observed vs. inferred | yes | the four inferred statements are those listed in 4.2.5; none of the cluster verdict rows rests on them (rows 1 and the exclusions rest on the trace lengths and the memtable-size control). |
| 6. Deviations and gaps | yes | the R9 post-reading amendment is stated in §1, §3 and the strict reading; the cluster tier was not affected by it. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1's falsifiers: (a) size changes with the pool — no (one value, four settings); (b) bytes appear in the accounted size — no (unit rows unchanged). |

### 5.2 Run 2?

**No** — decided 2026-10-25. The finding is a negative that the unit tier shows exactly (accounting equalities, a deterministic invariant over 126 points) and the cluster tier shows by an exact trace of every growth rather than a sampled measure; no part of §5.1 is settled only by inferred statements. The one risk, the R9 post-reading amendment, is recorded openly (strict reading in §4.2); a run 2 would reproduce the same deterministic unit output.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2); §7 is left out.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap) — both tiers agree, so the class is not undetermined.

**Claim tested:** (B1) `keyBytes.length` of a `TriePathReconstructor` follows only the longest path length walked, regardless of any memtable memory setting, and the array is outside the memtable allocator's accounting; therefore no configured limit caps it. "Confirmed" below means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1: Confirmed (array not accounted, not limited, bounded only by the path length), on version 2 of the file (R9); on the version-1 text unit run 1a matched no row exactly, the two failing sub-claims being the all-0x00 key's path length (§4.2 strict reading) | does not cap | run 1b + self-check (run 1a kept) | 2026-10-25 |
| Cluster | B3g row 1: Confirmed (usage does not follow any configured limit; positive control moved) | does not cap | run 1 + self-check | 2026-10-25 |

**Positive control** (a negative-estimate file only): unit — the accounted trie size rose x9.2 with the key count (M 10k -> 100k at L = 100, 1.58 MB -> 14.50 MB on heap, 1.54 -> 14.10 MB off heap) while the scratch array stayed in its band (cap 128); cluster — in the same runs and with the same instruments, the largest memtable size moved 8.6 / 55.1 / 218.5 MB and the t_small flush count 17 / 4 / 1 with `memtable_heap_space` 64 / 256 / 1024 MiB (heap_buffers), and the post-load `byte[]` total 53 / 194 / 490 MB, while the traced scratch length stayed 65,536.

**Feedback filed:** the case file's section D "Stage-4 feedback" field updated (case file untracked; no commit), and amended in section B5 (R1-R9, dated 2026-10-25; R9 after unit run 1a). Findings for stage 3: the written 65535 bound on the memtable path length is false (path = escaped `DecoratedKey`, 12 bytes longer than the key, up to about 1.5 x for alternating zeros), `usedSizeOnHeap/usedSizeOffHeap` are `sizeOnHeap()/sizeOffHeap()`, the exact power-of-two staircase is not exact (a first `addPathBytes` growth gives `newPos + 16`), `Ground`'s "at most ~128 KiB per live iterator" is superseded by P <= cap <= 2P (about 120 KB for the 60 KB keys used), JFR `ObjectAllocationSample` does not exist on JDK 11. Leftovers on `pc07`: tree `~/s4-tp33` (built, test file removed, git clean), `~/s4-tp33-run/{conf,logs,tools}` (node data, commit log, hints removed), `~/s4-tp33-logs/` (full logs, about 175 MB); no process running, ports 7210, 9110, 9142, 7010 free.
