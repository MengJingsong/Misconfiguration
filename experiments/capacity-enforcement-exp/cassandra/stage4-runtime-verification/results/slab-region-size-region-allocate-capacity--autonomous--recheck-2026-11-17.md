# slab-region-size-region-allocate-capacity--autonomous — stage-4 results, recheck claim of 2026-11-17  <!-- file: results/slab-region-size-region-allocate-capacity--autonomous--recheck-2026-11-17.md -->

> **Case:** [`slab-region-size-region-allocate-capacity--autonomous`](../../stage3-ai-deep-read/cases/slab-region-size-region-allocate-capacity--autonomous.md), section "Recheck — enforcement properties (guided, 2026-11-17, blind)", its **Stage-4 claim to add**; design in the case file's section "Stage-4 design for the recheck claim (2026-11-17)"
>
> **Status:** verdict filed (run 1 done and self-checked, no run 2) — 2026-11-17
>
> **Outcome class:** unchanged — this file tests the recheck claim only; the case's class (true negative) comes from the earlier results file. This claim's verdict is **Not confirmed (no matching row)**, so it adds no class ([definition](../../../stage4-runtime-verification/README.md#outcome-class))
>
> **Agent:** autonomous file. The claim is the recheck's one-sentence claim, not B1; "§9a" below means the design section's
> "Predictions" and "Conclusions" (P1–P7, validity, conclusions table); "§9b–§9e" means its Environment, Lifetimes, Workload and
> Measurement paragraphs. The case's earlier stage-4 result (B2/B3, 2026-10-26) is
> [`slab-region-size-region-allocate-capacity--autonomous.md`](slab-region-size-region-allocate-capacity--autonomous.md) and is not redone here.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `2f76b847` plus the uncommitted design section (not committed by this session). Frozen: `sed -n '/^## Stage-4 design for the recheck claim (2026-11-17)/,$p' <case file> \| git hash-object --stdin` = `cd3c3273a7015fe24a1f7d6abd0f90301b924c7a` (9637 bytes), taken after the audit and before any run. Predictions + conclusions alone (`sed -n '/^\*\*Predictions (frozen before any run)/,/^\*\*Stop conditions/p'`) = `b77400bd3ad59bb1d5668143dc6b2212606fd123`. After the runbook-defect amendment of the Environment paragraph (§3, defect 1, before any reading) the section hash is `8e76440b03b51bb31234734a77bea9a11bff8816`; the predictions + conclusions hash is unchanged (`b77400bd…`). |
| **Harness** | `harness/slab-region-size-region-allocate-capacity--autonomous--recheck-2026-11-17/`: `client.py` (bundled driver: schema, one row per table, fill), `run.py` (one lifetime per arm, scripted and logged), `analyze.py` (P1–P7, validity, matched row; literals typed from the frozen section), `Jmx.java` (copied unchanged from the earlier harness), `HoldBytes.java` + `instrument-check.sh` (known-answer check of the histogram reading). Not committed (the caller commits). |
| **Tiers and values** | One node (cluster tier). Unit tier `n/a` (reason in the design: the claim is about tables on a node; the allocator-level fact was measured in the earlier unit tier). Lifetimes `H2048` (`heap_buffers`, default `memtable_heap_space` = 2048 MiB), `U2048` (`unslabbed_heap_buffers`, matched control), `H256`, `H64` (`heap_buffers`, 256 / 64 MiB); in each, N = 0, 50, 100, 200, 400 written tables, a same-bytes control (`c1`: 400 rows in one table), and in `H64` a positive control (`pc`: 40,000 rows in one table). |
| **Audit bottom line** | **Ready** — 2026-11-17 (one citation corrected before the freeze; one runbook defect found at the first start and amended before any reading, §3) |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Hypothesis: on-heap bytes of 1 MiB slab regions (`[B` heap) against the on-heap bytes charged to `memtable_heap_space`. |
| A. Core question | knob varied, >= 3 values incl. default — or another approach, with the reason | Met | Lifetimes: `memtable_heap_space` 64 / 256 / 2048 MiB (default); the varied dose is N written tables (0, 50, 100, 200, 400); `memtable_allocation_type` default vs `unslabbed_heap_buffers` as matched control. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | Measurement M: class histogram `[B` bytes after a full GC (primary), heap used, cgroup `memory.current`; counted = global `AllMemtablesOnHeapDataSize`; gap named: the pool has no gauge, the global gauge is the sum of the tables' current memtables. |
| A. Core question | usage driven to the limit and past it | Met | `H64`: N = 400 puts about 400 MiB of regions against a 64 MiB limit (P4); the `pc` step drives the counted bytes to the cleaner threshold (P7). |
| B. Logic | each step says what it establishes | Met | Workload: `s0` baseline, `c1` same-bytes control, `sN` dose, `pc` positive control; logic paragraph maps each to the claim. |
| B. Logic | prediction stated in numbers or a clear relation | Met | P1–P7 with numeric bands. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | Rows for confirm, no region retained, regions charged, limit caps (refuted), mechanism not isolated, magnitude off (e.g. humongous), follows the knob in part, control did not bind, invalid, other. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met (negative claim) | The claim is "does not cap"; Confirmed needs the slope flat across `memtable_heap_space` (P3) and the positive control's `MEMTABLE_LIMIT` flush of the counted-large table (P7), the disallow branch firing on counted bytes. |
| B. Logic | alternative explanations and their controls | Met | Other per-table heap from a first write: `U2048`; bytes vs tables: `c1`; humongous doubling: G1 flag check and its row; flushes: flush-line count and per-table gauges; background system-table writes (size estimates): bands of 5 % and +-15 MiB. |
| C. Specific | a human can follow it from the intro and §9a | Met | "How this verifies the claim" block and the conclusions table stand alone. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met | Exact tables, keys, values, step order, idle times, instruments. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met | Steps followed by 10 s idle and two histograms; definitions of R, A, slopes; stop conditions. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | pc91 tree `cassandra-base` (built), JDK 11.0.33; harness written in step 1. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly, fixed by amendment | 401 tables, at most 0.45 GiB of heap growth, 40 MB written; 12 GiB budget assumed an 8 GiB default heap. The 5.0.9 default is 31 GiB on this node (pre-touched): defect 1, `MAX_HEAP_SIZE=8G`. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `SlabAllocator.java:89,139`; `AbstractAllocatorMemtable.java:118`; `SkipListMemtable.java:124-125` (corrected from 122-123 before the freeze); `BTreePartitionUpdater.java:182`; `TableMetrics.java:493-512,1331-1349` (global gauge = sum of tables); `ColumnFamilyStore.java:1055` (flush line); `DatabaseDescriptor.java:755,761-763` (2 writers, threshold 1/3); `conf/jvm11-server.options:63,66`. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Pin `MAX_HEAP_SIZE=8G` | Applied 2026-11-17 (Environment paragraph, marked in place; not committed) | Defect 1: the shipped heap is 31 GiB here; with pre-touch it cannot fit the 12 GiB budget. |
| 2 | The recheck claim says "MemtablePool on-heap used"; the pool has no JMX gauge. A future design could add one (or a Byteman read of `MemtablePool.onHeap.used()`) | Left for stage 3 | The global table gauge is the same sum when no flush is in progress. |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-11-17 (attempts 10:44–10:54 MST; run 1 lifetimes 10:55–11:09 MST, about 3.5 min each) | not done |
| Node (CloudLab name and type) | `pc91` (`node0.jason92-326528`), x86_64, 32 cores, 125 GiB; driven over one open `ssh pc91` session | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, 5.15.0-203-generic | |
| JDK (`java -version`) | openjdk 11.0.33 (2026-10-20) | |
| Ant (`ant -version`) | Apache Ant 1.10.12 (not used: the tree was built already) | |
| Local source copy | `/mydata/s4/slabrc` = `cp -a /mydata/s4/cassandra-base` (built 5.0.9 copy made by `copy-source.sh`; `git describe` = `cassandra-5.0.9`, clean); repository HEAD `2f76b847` | |
| Case-file commit / harness commit | uncommitted (the caller commits); design section hash `cd3c3273…` at the freeze, `8e76440b…` after defect 1; predictions + conclusions `b77400bd…` throughout | |
| Measured JVM | node in `systemd-run --user --scope -p MemoryMax=12G -p MemorySwapMax=0` (read back: `memory.max` 12884901888, `memory.swap.max` 0; `memory.events` oom_kill 0 in every lifetime); `-Xmx8G`, G1 16m regions, `AlwaysPreTouch`; `memory.current` 9.58–9.70 GB (pre-touched heap) | |
| Storage for node data | local `/mydata/s4/slabrc-run/` (ext4 on the node's block store, 714 GiB free), removed after each lifetime | |
| Full logs (path, outside the repo) | `pc91:/mydata/s4/slabrc-logs/run1/{H2048,U2048,H256,H64}/` (session.log, summary.txt, steps.json, hist-*.txt, system.log, stdout.txt), attempts in `.../H2048-attempt{1-oomkilled-at-start,2-pidfile,3-jmxcache}/`; excerpts in `results/slab-region-size-region-allocate-capacity--autonomous--recheck-2026-11-17/run1/` | |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | run 1, `H2048` first start (no reading taken) | Environment | The design said the shipped `cassandra-env.sh` gives an 8 GiB heap; 5.0.9 gives min(RAM/2, 31744 MiB) = 31 GiB on pc91, pre-touched, so the 12 GiB scope OOM-killed the JVM 7 s after launch (`journalctl --user`: "A process of this unit has been killed by the OOM killer"). | `MAX_HEAP_SIZE=8G` in the Environment paragraph (dated, marked) and in `run.py` (flag check adds `-Xmx8G`); predictions and conclusions unchanged (hash `b77400bd…` before and after). The lifetime restarted from its beginning. | 2026-11-17, before any reading | none (uncommitted) |
| 2 | run 1, `H2048` second start (no reading taken) | Environment (harness) | `bin/cassandra -f` writes no pidfile, so `run.py` never saw the node as up (it served at 17:46:29 UTC), failed after 300 s, and could not stop it; the leftover daemon (pid 5843) was stopped by hand and `ps` checked (0 left). | `run.py` finds the node by its `-Dcassandra-pidfile=` property in `/proc/*/cmdline`. Lifetime restarted. | 2026-11-17 | n/a (harness) |
| 3 | run 1, `H2048` third start (attempt kept in `run1/attempt3-H2048/`) | Measurement M (harness) | The first per-table JMX pattern query (taken after the `s0` histograms) left about 22 MB of live heap: 771,755 `[B`, 771,747 `String`, 96,922 `HashMap` with 385,715 nodes, i.e. one 4-key property map per metric MBean of 401 tables (inferred: `ObjectName` key-property caches). It landed between `s0` and `c1`, so `Rc` read 22.8 MB. The instrument added live heap inside the measured window; the `sN` deltas (taken from `c1`) were not affected (`[B` instances flat from `c1` to `s400`). | `run.py` takes two diagnostic histograms (`s0pre`), then one per-table query and the gauges (instrument warm-up), then `s0`; M is otherwise unchanged; the design text is unchanged (it lists what M reads, not the order of the JMX calls). The whole tier restarted (all four lifetimes). Precedent: defect 2 of the case's earlier results file (a probe defect found from a reading, tier restarted, attempt kept). | 2026-11-17, after attempt 3's readings; the frozen predictions and conclusions unchanged | n/a (harness) |

Attempt 3's `sN` readings are reported in §4.1 (as an attempt, not a reading of run 1) so that nothing is hidden.

## 4. Run 1

**Scope:** one node, four lifetimes in the design's order (`H2048`, `U2048`, `H256`, `H64`), each with steps `s0`, `c1`, `s50`, `s100`, `s200`, `s400`, plus `pc` in `H64`; the diagnostic `s0pre` before the instrument warm-up (defect 3). Instrument known-answer check first: 40 x `byte[1048576]` read as 41,943,720 B against 41,943,680 (40 B off) (`run1/instrument/instrument-summary.txt`). **Command log:** `run1/session-all-lifetimes.log` (every command with its epoch ms), `run1/<arm>/summary.txt`, `run1/<arm>/steps.json` (every M reading), `run1/hist-heads.txt` (top of each histogram), `run1/flush-lines.txt`, `run1/analysis.txt` (output of `analyze.py`).

### 4.1 Readings

**Unit tier** — `n/a` (design: the claim is about tables on a node).

**One node.** R(N) = `[B` bytes at `sN` minus `c1`; A(N) = global `AllMemtablesOnHeapDataSize` at `sN` minus `c1`; slopes are least squares over N = 0, 50, 100, 200, 400 (`run1/analysis.txt`).

| Capacity value | Lifetime | Observable | Reading | Evidence |
|---|---|---|---|---|
| `heap_buffers`, space 2048 MiB (default) | H2048 | `[B` at s0 / c1 / s50 / s100 / s200 / s400 (B) | 59,082,688 / 61,187,488 / 113,557,992 / 165,988,600 / 270,848,248 / 480,573,240; `[B` instances 1,134,157 at s0 and 1,133,832–1,134,298 after (flat) | `run1/H2048/steps.json` |
| same | H2048 | R(N) per table; `slope_R`; R(200); R(400) | 1,047,410 / 1,048,011 / 1,048,304 / 1,048,464 B; 1.0000 MiB (1,048,524 B) per table; 199.95 MiB; 399.96 MiB | `run1/analysis.txt` |
| same | H2048 | A(N) per table; `slope_A`; A(200); R(200)/A(200) | 1,529 B at every N; 1.493 KiB; 0.292 MiB; 686 | same |
| same | H2048 | heap used (JMX) s400 minus c1; histogram total slope | 417.0 MiB; 1.0026 MiB per table | `run1/H2048/steps.json` |
| same | H2048 | same-bytes control `c1` (400 rows in `t0`): Rc, Ac | 2.007 MiB, 0.584 MiB | same |
| same | H2048 | tables with gauge > 0 at c1..s400; `ks.` flush lines before stop; node's own flush log at drain | 1, 51, 101, 201, 401 (= N + 1); 0; each small table "Usage: 1.493KiB (0%) on-heap" | `steps.json`, `run1/flush-lines.txt` |
| `unslabbed_heap_buffers`, 2048 MiB | U2048 (matched control) | R(N) per table; `slope_R`; R(400) | -124 / 492 / 781 / 932 B; 0.969 KiB (992 B) per table; 0.36 MiB | `run1/U2048/steps.json`, `analysis.txt` |
| same | U2048 | A(N) per table; `slope_A`; Rc; Ac | 1,560 B; 1.523 KiB; 0.412 MiB; 0.596 MiB | same |
| `heap_buffers`, 256 MiB | H256 | `slope_R`; R(200); R(400); `slope_A`; A(200); Rc; Ac | 0.9999 MiB (1,048,521 B); 199.95 MiB; 399.96 MiB; 1.492 KiB; 0.291 MiB; 2.006 MiB; 0.584 MiB | `run1/H256/steps.json`, `analysis.txt` |
| `heap_buffers`, 64 MiB | H64 | `slope_R`; R(200); R(400) (= x L); `slope_A`; A(200); Rc; Ac | 1.0000 MiB (1,048,525 B); 199.95 MiB; 399.96 MiB (6.25 L); 1.492 KiB; 0.291 MiB; 2.008 MiB; 0.584 MiB | `run1/H64/steps.json`, `analysis.txt` |
| same | H64 | global on-heap gauge at s0 / s400; of it, the `ks` tables at s400; `ks.` flush lines before `pc` | 2.134 MiB / 3.300 MiB (0.052 L); 1.166 MiB (0.018 L); 0 | `run1/H64/steps.json` |
| same | H64 `pc` (positive control, 40,000 rows into `t0`, 5.6 s, 0 errors) | `MEMTABLE_LIMIT` flushes of `t0`; flush lines of `t1..t400`; small tables still holding data; global gauge after; `[B` pc minus s400 | 3 ("Usage: 18.663MiB (29%) on-heap", 18.644, 18.633); 0; 400; 5.649 MiB (0.088 L); +11.01 MiB | `run1/flush-lines.txt`, `run1/H64/steps.json` |
| all lifetimes | | `[B` first vs second histogram; settings read-back; JVM flags; budget; `^ERROR` lines; oom_kill; client errors | equal to the byte or within 224 B; equal to the arm (`memtable_heap_space` 2048MiB / 256MiB / 64MiB, cleanup threshold 0.33333334, flush writers 2, num_tokens 16); `-Xmx8G`, G1, 16m, pre-touch; 12 GiB, swap 0; 0; 0; 0 | `run1/<arm>/summary.txt`, `steps.json` |
| diagnostic (defect 3, not a reading) | every lifetime, `s0pre` -> `s0` (the per-table JMX query, no write) | `[B` bytes and instances | H2048: 38,374,768 -> 59,082,688 B, 362,092 -> 1,134,157 (+20.71 MB, +772,065); U2048, H256, H64 give the same increase within 0.3 percent | `run1/session-all-lifetimes.log` |
| attempt 3 of H2048 (defect 3, readings discarded, shown in full) | | per-table R; per-table A; Rc | 1,047,416–1,048,459 B; 1,528 B; 21.74 MiB (the instrument's caches) | `run1/H2048-attempt3-jmxcache/steps.json` |

### 4.2 Conclusion and logic

1. **Validity** — valid by every validity clause of the design: settings read back as set in all four lifetimes, `-Xmx8G`, `-XX:+UseG1GC`, `-XX:G1HeapRegionSize=16m`, `-XX:+AlwaysPreTouch` present, scope `memory.max` 12 GiB and swap 0 **[observed: `run1/<arm>/summary.txt`, `jvm-cmdline.txt`]**; the count of `ks` tables with a gauge above 0 was N + 1 at every step, and no `ks.` flush line appeared before `pc` (all 401 per lifetime are `DRAIN` at shutdown) **[observed: `steps.json`, `flush-lines.txt`]**; client errors 0, `^ERROR` 0, oom_kill 0 **[observed]**. "Driven past the limit": in `H64`, R(400) is 6.25 x `memtable_heap_space` with no flush of the small tables **[observed]**.
2. **Readings** — one frozen sub-prediction missed: **P4**'s bound "the global gauge at `s400` below 0.02 x 64 MiB" (1.28 MiB); the reading is 3.300 MiB (0.052 L) **[observed: `run1/H64/steps.json`]**. Of it, 2.134 MiB was already there at `s0`, before any write **[observed]**: the global gauge sums every table, system tables included, and the bound did not allow for them **[inferred: `TableMetrics.java:1331-1349` sums all tables; the `ks` tables' own sum at `s400` is 1.166 MiB = 0.018 L, under the bound]**. The rest of P4 holds: R(400) = 399.96 MiB > 64 MiB and no `ks.` flush line before `pc` **[observed]**. Everything else is as predicted, with little spread: the three `heap_buffers` lifetimes agree on `slope_R` within 4 B per table and on A(N) within 1 B per table **[observed: `analysis.txt`]**. Per-table R approaches 1,048,592 B (one `byte[1048576]` with its header) from below: 1,047,410 at N = 50, 1,048,464 at N = 400, a constant offset of about -59 KB shared by all steps **[inferred: a few small arrays freed after `c1`; the `[B` instance count moves by only -433 to +455]**.
3. **Matched row** — every clause of the Confirmed row holds except P4 (part 2). P1: `slope_R` 1.0000 / 0.9999 / 1.0000 MiB per table in [0.95, 1.10]; R(200) 199.95 MiB in [190, 225]; R(400) 399.96 MiB in [380, 445]. P2: `slope_A` 1.492–1.493 KiB in [1.0, 3.0]; A(200) 0.291–0.292 MiB in [0.2, 0.6]; ratio 686 >= 300. P3: max/min of the slopes 1.0000 <= 1.05. P5: U2048 `slope_R` 0.969 KiB <= 16 KiB, `slope_A` 1.523 KiB. P6: Rc 2.006–2.008 MiB in [0.9, 2.5], Ac 0.584 MiB in [0.4, 1.2]; U2048 Rc 0.412 MiB in [0.2, 1.5]. P7 (all parts, core included): 3 `MEMTABLE_LIMIT` flushes of `t0`, 0 for `t1..t400`, 400 small tables still holding data, gauge 5.649 MiB <= 25.6 MiB, `[B` +11.01 MiB in [-2, 30] **[observed: `analysis.txt`, recomputed from `steps.json` in the self-check]**. Row 1 needs "P4 holds", so **row 1 does not match**. No other row's condition holds (part 4). Under the frozen table the readings fall to the last row: **"Any other combination — Not confirmed (no matching row)"**.
4. **Excluded rows** — "`slope_R` at most 0.10 MiB per table (Refuted)": excluded, 1.0000 **[observed]**. "`slope_A` at least 0.5 MiB per table (Refuted)": excluded, 1.49 KiB **[observed]**. "`H64`: small tables flushed and R(400) at most 64 MiB (Refuted)": excluded, 0 small-table flush lines and R(400) = 399.96 MiB **[observed]**. "U2048 slope at least half the H2048 slope (Not confirmed, mechanism)": excluded, 992 B against 1,048,524 B **[observed]**. "Slope in (0.10, 0.95) or above 1.10 MiB (magnitude)": excluded, 1.0000 **[observed]**. "P3 fails": excluded, 1.0000 **[observed]**. "P7 fails": excluded **[observed]**. "Invalid": excluded, part 1. "Confirmed": excluded only by the P4 gauge clause (part 2).
5. **Observed vs. inferred** — The conclusion depends on two inferred statements. (a) The P4 miss comes from the system tables' share of the global gauge, not from the `ks` tables: their sum, 1.166 MiB, is under the bound, and the global gauge was already 2.134 MiB at `s0`. (b) The `[B` growth per written table is the slab region. The evidence: U2048 shows 992 B per table on the same workload; the `[B` instance count is flat while bytes grow by about 1 MiB per table, so the added arrays are about N arrays of about 1 MiB; and the known-answer check reads one `byte[1048576]` as 1,048,592 B. This run does not count regions directly (no reflection on `regionCount` in a node).
6. **Deviations and gaps** — (i) `MAX_HEAP_SIZE=8G` instead of the shipped 31 GiB default (defect 1; the claim does not depend on heap size, and G1 16m regions are forced by the shipped options). (ii) Instrument warm-up before `s0` (defect 3); the frozen M order produced attempt 3, kept, whose per-table readings equal run 1's to within 15 B. (iii) "MemtablePool on-heap used" is read as the global table gauge (named gap; the pool has no gauge of its own). (iv) One run, no repeat lifetime. The three `heap_buffers` lifetimes act as near-repeats (equal slopes to 4 B), but they differ in one knob. (v) The run used a single 1 KiB write per table. Larger first writes (up to 1 MiB) or many writes to the same table are not tested: there the region is used more fully.
7. **Core question** — Real usage did not follow the counted quantity. Under the default `heap_buffers`, each table given one 1 KiB write retained 1,048,5xx B of `[B` heap (199.95 MiB for 200 tables, 399.96 MiB for 400). The memtable accounting rose by 1,528 B per table (0.29 MiB for 200), the same as under `unslabbed_heap_buffers`, where the `[B` heap rose by 992 B per table. The same 400 rows in one table cost 2 MiB. The per-table region heap was the same at `memtable_heap_space` 64, 256 and 2048 MiB. At 64 MiB it reached 6.25 times the limit with no flush of the small tables. The pool limit flushed only the table it counts as large (`t0`, three `MEMTABLE_LIMIT` flushes at about 18.6 MiB counted). So `memtable_heap_space` does not cap the slab-region heap of small memtables (parts 1, 3). The frozen table still yields Not confirmed, because the P4 gauge bound left out the system tables' 2.1 MiB baseline (part 2).

**Conclusion (one line):** "Any other combination" — **not confirmed (no matching row)**: every relation of the claim held (1.0000 MiB of `[B` against 1.49 KiB counted per written table, flat across `memtable_heap_space`, absent under `unslabbed_heap_buffers`, positive control bound). The only miss is the frozen P4 bound on the global gauge, 3.30 MiB against 1.28 MiB, of which 2.13 MiB was system tables before any write.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-read: `run1/<arm>/steps.json` (relations recomputed by an independent script, not `analyze.py`: per-table R and A at each N, R(200), A(200), ratio, Rc, the gauge split at `s400`, the `pc` values; all equal to `analysis.txt`), `run1/<arm>/summary.txt` (every EXPECTED line reads `yes`), `run1/flush-lines.txt` (3 `MEMTABLE_LIMIT` lines, all for `ks.t0`; 401 DRAIN lines per lifetime; `^ERROR` 0), `run1/H2048-attempt3-jmxcache/steps.json`, `run1/session-all-lifetimes.log` (`s0pre` lines), `run1/attempt1-H2048-journal.txt` (OOM-killer line). One analysis defect was found and fixed before the verdict: `analyze.py` first read every lifetime as invalid, because the JVM-flags EXPECTED line continues after "yes" ("yes; heap ['-Xmx8G']"). The check now matches `: yes` followed by `;` or the end of the line. No reading changed.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `summary.txt` x 4, `jvm-cmdline.txt` x 4, `steps.json` table counts and flush counts. |
| 2. Readings | yes | P4 miss confirmed: global 3,460,411 B at `s400`; `per_table_sum` 1,222,400 B; global at `s0` 2,237,337 B (`H64/steps.json`). |
| 3. Matched row | yes | Row 1 requires P4; P4 misses; no other row's condition holds; the last row applies. The verdict follows the frozen table even though the miss is in the prediction's arithmetic, not in the claim. |
| 4. Excluded rows | yes | Recomputed slopes: 1,048,521–1,048,525 B (heap), 992 B (unslabbed); 0 small-table flush lines. |
| 5. Observed vs. inferred | yes | (a) The split of the global gauge is in the raw file (`per_table_sum`). (b) The U2048 contrast and the flat `[B` instance count are in the raw files; a direct region count is not available at this tier and is not claimed. |
| 6. Deviations and gaps | yes | Defects 1–3 (§3) and the analysis fix above; attempt 3 agrees with run 1 on every `sN` relation (per-table R within 15 B, A equal). |
| 7. Core question | yes | The steps of the design's logic block hold one by one (per-table region heap; unslabbed and same-bytes controls; flat across the knob; limit flushes only the counted-large table). The formal row is Not confirmed for the reason stated. |

### 5.2 Run 2?

**No** — decided 2026-11-17. The readings are exact and repeat across three lifetimes. A run 2 under the same frozen table would miss P4 the same way, because the system tables' share of the global gauge does not depend on the run. Settling the verdict needs a stage-3/design amendment of P4, not a repeat. The amendment would bound the `ks` tables' sum (`per_table_sum`), or A(400), instead of the global gauge. Under the README's "No §9a row fits" it is made dated and the tier restarted; that is left to the orchestrator, because it would be written after this reading.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative (case Estimate line; the recheck adds "the real-vs-accounted gap is positive and decided by E3"). **Outcome class:** unchanged (true negative, from the earlier results file); this claim adds none (Not confirmed).

**Claim tested:** (the recheck's Stage-4 claim to add) "With default `heap_buffers` and N tables each given one 1 KB write (no flush), retained `[B` heap rises by about N x 1 MiB while `MemtablePool` on-heap `used` rises by about N x 1 KB (plus row overhead); N = 200 gives ~200 MiB against ~0.3 MiB accounted." It says the pool's limit does not count, and so does not cap, the per-table slab regions.
"Confirmed" below always means this claim held.

| Tier | Verdict (row of the design's conclusions table) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | not run: `n/a` — the claim is about tables on a node; the allocator-level fact was measured in the earlier unit tier | — | — | 2026-11-17 |
| One node | **Not confirmed (no matching row)**. The relations of the claim all held: 1.0000 MiB `[B` per written table against 1.49 KiB counted; N = 200 gives 199.95 MiB against 0.29 MiB; flat across `memtable_heap_space` 64 / 256 / 2048 MiB; 992 B per table under `unslabbed_heap_buffers`; positive control bound. The frozen P4 gauge bound (1.28 MiB) missed at 3.30 MiB, of which 2.13 MiB was system tables before any write | undetermined (by the rule for Not confirmed; the readings show `memtable_heap_space` does not cap the regions) | run 1 + self-check | 2026-11-17 |

**Positive control:** `H64`, 40,000 x 1 KiB rows into `t0`. The pool limit bound on counted bytes: three `MEMTABLE_LIMIT` flushes of `ks.t0` at 18.6 MiB counted (29 % of 64 MiB, cleanup threshold 1/3), the global gauge back to 5.65 MiB, and `[B` only 11.0 MiB above `s400`. The same flushes left all 400 small tables (399.96 MiB of regions, 0.018 L counted) unflushed.

**Feedback filed:** one dated line in the case file's section D pointing here (uncommitted). The design section was appended to the case file before the run, and its Environment paragraph was amended for defect 1 (marked in place). Findings for stage 3 and upstream: (1) with `heap_buffers`, every memtable with at least one write pins a 1 MiB on-heap region that `memtable_heap_space` charges at about 1.5 KiB. The node's own flush log reports such a table as "1.492KiB (0%) on-heap": 400 tables gave 400 MiB of heap at 0.6 MiB counted. (2) The pool's cleaner picks by counted bytes, so these regions are freed only by other flush triggers (commit-log, period, drain). (3) The global `AllMemtablesOnHeapDataSize` includes about 2.1 MiB of system-table memtables on an idle node; a bound written on it must allow for that. (4) Harness lesson: a JMX pattern query over about 97k metric MBeans leaves about 21 MB of live heap (`ObjectName` property maps); warm it before a heap baseline.

**Leftovers on the node:** none running. `ps -eo cmd | grep '[C]assandraDaemon'` gives 0; no `slabrc` scope or process; `/mydata/s4/slabrc-run` removed. Kept on pc91: `/mydata/s4/slabrc` (tree), `/mydata/s4/slabrc-harness`, `/mydata/s4/slabrc-logs`.
