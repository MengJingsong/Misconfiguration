# repair_session_space-split-maxsize — stage-4 results  <!-- file: long-path/results/repair_session_space-split-maxsize.md -->

> **Case:** [`repair_session_space-split-maxsize`](../../stage3-ai-deep-read/cases/repair_session_space-split-maxsize--guided.md)
>
> **Status:** **Closed 2026-10-19 — all tiers verified at stage 4 (verdicts below).** verdict filed (2026-10-14) — **Confirmed at both tiers**; arm M **non-domination as recorded** (the check is never reached on Murmur3; `init()` sizes the tree); **overflow as recorded** (2048 MiB → two-leaf trees); no run 2
> 
> **Outcome class:** true positive — stage-3 estimate vs the stage-4 effect on the constraint
>
> **Path:** long. One results file per path, each in its path's folder.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base commit `5f66f62` plus the step-0 amendments of 2026-10-14 (uncommitted at freeze). §9 hash after the amendments: **`92f86a2dfba524c78a7d17b58d3a75e1a2e18355`** (`sed -n '/^## 9\. /,/^## 10\. /p' <case> \| git hash-object --stdin`); §9a alone `cae80073…`. §9a is frozen at this version. |
| **Harness** | `../harness/repair_session_space-split-maxsize/` (written 2026-10-14; uncommitted at run 1): `RepairSessionSpaceTreeTest.java`, `unit-run.sh`, `split-trace.btm`, `hold-trees.btm`, `Rss.java`, `Jmx.java`, `make-node-yaml.sh`, `cluster-run.py`, `README.md`. Node copy `pc57:~/stage4-harness-run/rss/`, `md5sum -c` against the repo clean before the cluster run (`~/stage4-logs/rss/harness.md5`; `cluster-run.py` `md5` recorded there). **Instrument checks (2026-10-14, not readings):** Byteman `TestScript` against the build: all six rules type-checked, `TestScript: no errors` (the first try failed to parse `new java.io.File(…)` in a condition; moved to the helper `Rss.java`). `unit-run.sh instrument` (`u3Derivation` with `split-trace.btm`): `split calls=0` on the three `init()` validations, `split refused size=maxsize` and `samples=512` on both split-path validations, no `toodeep` (`~/stage4-logs/rss/unit-instrument/`). Cluster shakedown with 2^16 rows (`~/stage4-logs/rss-shakedown/`): every label ran; it found two harness bugs, fixed before run 1 (the client-port wait matched "not running"; `o-setup`'s first repair, a set-up read of *n*, was judged against 9a). With 2^16 rows arm O had 267 samples and stopped on `TooDeep` at 2^15 leaves, which also checked the `toodeep` rule. |
| **Tiers and values** | Unit: upstream `MerkleTreeTest`, `ValidatorTest`; harness `RepairSessionSpaceTreeTest` U1–U4. Cluster (two nodes on `pc57`, RF 2): arm M (`Murmur3Partitioner`) at *s* = 1, 4, 16, 64 MiB and the default, scenario B at 4 and 16, overflow at 2048 and 4097, depth cap 15 at 64; arm O (`ByteOrderedPartitioner`) at 4 and 16. The optional over-streaming step is not planned. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-14 |

### 1.1 Design audit

Citations re-read against the pinned clone `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`).

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Merkle-tree leaves per validation, a count with a derivable byte size (§7: on heap per leaf with its inner node; off heap `82 L + 32` per buffer after rec. 1). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | *s* = 1, 4, 16, 64 MiB and the default (128 MiB at `-Xmx2G`), live over JMX (9b); plus the overflow values and the depth cap. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | Heap: `jmap -histo:live` instance counts on node 2 during a held validation (9d). Off heap: the logged buffer size is the allocation request, not measured memory; the proposed `MemoryUsed` "after" reading cannot see buffers released when the session ends. Changed to a reading during node 2's hold, as support (rec. 6); the gap is named. |
| A. Core question | usage driven to the limit and past it | Met | Arm O and U1/U3 drive `split()` until it refuses (the sample loop asks for more after `maxsize`); arm M has no "past", by the case's finding (no comparison, §6b), which is its own conclusions row. |
| B. Logic | each step says what it establishes | Met | "How this verifies the hypothesis", Logic (1)–(6). |
| B. Logic | prediction stated in numbers or a clear relation | Partly | `L = 2^min(…)` is exact, but *d*(*b*) depends on the partitioner, and U3 printed it for one partitioner and without 64 MiB (the default at RF 2); and the off-heap formula was one inner node and one leaf short (`allocate()` is passed the leaf count, `MerkleTree.java:781`, `:714`, `:789`, `:799-802`). Amended (recs. 1, 2). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | Rows for over, flat, partition-bound, `TooDeep`, overflow and knob-not-taken exist; a silent instrument (no leaf-count or trace line, hold never reached) had none. Added (rec. 3). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The Confirmed row needs *L* doubling per doubling and arm O's `split refused size == maxsize`, with no `toodeep`. |
| B. Logic | alternative explanations and their controls | Met | Partition term (*n* from the `Created` line, scenario B doubles it); `TooDeep` (trace, and `size < maxsize`); knob not taken (read-back); the depth cap (its own step). The histogram's baseline is now taken just before each held repair (rec. 1), so an earlier tree still reachable is not counted. |
| C. Specific | a human can follow it from the intro and §9a | Met | §9 intro, §9a. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | Arm O's token step was wrong: in a byte-ordered table `LIMIT 20` returns the 20 smallest tokens, so "the median" was not the data's (rec. 4); its sample count read a statistic `nodetool tablestats` does not print (rec. 5). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | `-col n=1` is not stress distribution syntax (`n=FIXED(1)`); `disableautocompaction` "before loading" cannot run before stress creates the table; the hold rule had no way to load only for the histogram runs (recs. 7, 8). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Harness listed as step-1 work (9c). `pc57` (this host): JDK 11.0.32.1, Ant, `~/cassandra-run1` at `cassandra-5.0.9`, Byteman 4.0.20 in `build/lib/jars/`. The two nodes run on `pc57` (rec. 9). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly | Cluster: 2^20 rows × ≈ 60 B ≈ 60 MB per node, 2^21 after B; two 2 GiB heaps; `pc57` has 32 cores, 251 GiB, 55 GB free; the largest tree (2^18 leaves at the default) is ≈ 40 MB on heap. Unit U3 split path: with 2^14 rows (≈ 128 samples), 2^13 leaves need ≈ 64 splits per sample, and the decimal test keys under byte order share long prefixes, so `TooDeep` (depth 126) could stop the loop before `maxsize`: moved to a 2^16-row table (rec. 10). |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met, one defect | Read in context: `ValidationManager.java:54-89` (`:62-63` the `int` product, `:71`, `:74`, `:75-77`, `:79`, `:80`, `:85`), `:127-129`; `Validator.java:91-114`, `:117-160` (`:121`, `:124`, `:139-144`, `:146-152`, `:158`), `:222-237`, `:281-306`; `MerkleTree.java:89`, `:97-98`, `:108-130`, `:139-162`, `:180-190` (`size()`, `maxsize()`), `:407-453`, `:683-729`, `:733-751`, `:769-802` (the defect: `allocate(size)` with `size` the leaf count, rec. 1), `:1058-1065`, `:1160-1163`, `:1245-1254`, `:1451-1457`, `:1520-1541`; `MerkleTrees.java:108-119`, `:137-173`, `:197-207`, `:273-292`; `DatabaseDescriptor.java:596-615`, `:4070-4101`; `ActiveRepairService.java:305-354` and `ActiveRepairServiceMBean.java:40-51` (attribute `RepairSessionSpaceInMiB`); `Config.java:206-212`; `CassandraValidationIterator.java:174-236` (share = 1 for one range); `Murmur3Partitioner.java:52`, `:269-272`, `:299`; `ByteOrderedPartitioner.java:291`; `BtiTableReader.java:314-319`; `Range.java:293-296`; `conf/logback.xml:132` (DEBUG); `conf/jvm11-server.options:63` (G1); `test/conf/cassandra.yaml:18`; `MerkleTreeTest.java:161-174`; `ValidatorTest.java:234-284`. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Off-heap buffer per tree is `L × 50 + (L + 1) × 32 = 82 L + 32` bytes, not `(L − 1) × 50 + L × 32`: `allocate()`'s `innerNodeCount` parameter receives the leaf count. The heap histogram is a change from an idle histogram taken just before each held repair. | Applied 2026-10-14 (9a Prediction "Heap"); uncommitted | The off-heap line is predicted "exactly"; the old formula would be 82 B off on every line. Source only. §7's "Rough sizing" carries the same formula: left for stage 3 (noted in the case's §10). |
| 2 | U3 prints *d*(*b*) for both partitioners, for *b* = 0.5, 1, 2, 4, 8, 32, 64 MiB; the cluster prediction takes the exact *d* from it; the default *s* is read back. | Applied 2026-10-14 (9a Prediction, 9e U3) | `estimatedMaxDepthForBytes` measures the partitioner's token; arm M runs Murmur3, the unit tier byte order. |
| 3 | Add an "instrument silent" row (no leaf-count or trace line, hold not reached → invalid for that reading). | Applied 2026-10-14 (9a table) | Every plausible outcome needs a row. |
| 4 | Arm O tokens: read all 1,000 tokens; node 2 at `00`, node 1 at their median; node 1's range `(00, median]` does not wrap. | Applied 2026-10-14 (9e arm O) | `LIMIT 20` in token order gives the 20 smallest. |
| 5 | Arm O sample count from a fourth trace rule at `keys.clear()` (`$numKeys`; the build keeps local variable tables, `build.xml:33`). | Applied 2026-10-14 (9a Prediction arm O, 9c, 9e) | `nodetool tablestats` does not print index-summary entries. |
| 6 | Off-heap cross-check: node 1's direct `MemoryUsed` idle and during node 2's hold (node 1's own buffer allocated, the peer's not yet), as support. | Applied 2026-10-14 (9d) | The session releases its trees when it ends, so "after" shows nothing. |
| 7 | Stress `-col 'n=FIXED(1)'`; create the table with autocompaction disabled before loading. | Applied 2026-10-14 (9b, 9c) | The written command and order cannot run. |
| 8 | `hold-trees.btm` loaded at node 2's start, gated by a flag file, writing `hold start` and `hold end`. | Applied 2026-10-14 (9c) | No run-time rule loading; the harness knows when to take the histogram. |
| 9 | Both nodes on `pc57` on loopback addresses with their own ports (as the `internode_application_send_queue_capacity` ring); `Jmx.java` for the knob. | Applied 2026-10-14 (9b) | Nothing measured depends on the network; one clock and one file system for the logs. |
| 10 | U3's split-path repeats on a 2^16-row table; U4 on the `init()` path. | Applied 2026-10-14 (9e U3, U4) | `TooDeep` risk at ≈ 64 splits per sample with prefix-sharing keys; a 2^14-leaf split-path tree from 128 samples cannot be built. |
| 11 | §6b "the only trace is the debug line": `Validator.complete()` also logs per-leaf histograms at DEBUG (`:227-233`), which a reader of `debug.log` sees. | Left for stage 3 | Wording; no effect on the run. |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-14 (unit 11:04–11:06 MDT; cluster attempt 2 from 11:29 MDT) | not done |
| Node (CloudLab name and type) | `pc57` (`node0.jason92-319347`), 32 cores, 251 GiB; both nodes on this host, N1 `127.0.0.2` (JMX 7102), N2 `127.0.0.3` (JMX 7103), `MAX_HEAP_SIZE=2G` each (G1) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54`) | |
| Case-file commit / harness commit | case `5f66f62` + step-0 amendments (uncommitted) / harness uncommitted at run 1 | |
| Storage for node data | `/dev/sda3` (local, 55 GB free), `~/stage4-rss/N1`, `~/stage4-rss/N2` | |
| Full logs (path, outside the repo) | `pc57:~/stage4-logs/rss/` (`unit/`, one folder per cluster label with `raw/`; first attempts in `unit.attempt1/`, `cluster.attempt1/`; shakedown `~/stage4-logs/rss-shakedown/`) | |

## 3. Runbook defects

Both are harness defects found in run 1; neither changes §9a, and each restarted its tier from the beginning.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | 1, unit, attempt 1 | 9e U1, U2 (leaf count) | The harness counted leaves by walking `MerkleTree.TreeRangeIterator`, which yields the leaf whose range wraps around **twice** by design (`MerkleTree.java:623-626`, "put to be taken again last"). On the full-ring trees of U1 and U2 (`(min, min]`), every count was *M* + 1, giving 7 `MISMATCH` lines; the `size` field, U3 and U4 (partial ranges) agreed. An instrument defect: the tree has *M* leaves. | Count distinct leaf nodes by identity. Attempt 1 is kept in `unit.attempt1/`. | Unit tier restarted 2026-10-14 11:04; 78/78 checks | none (harness only) |
| 2 | 1, cluster, attempt 1 | 9e (evidence) | Every reading matched (92 `EXPECTED` yes, 0 no), but `o-setup` wipes the node folders to start arm O, which deleted arm M's raw `debug.log` and trace files, and the `jmap` histograms were parsed and not saved. The self-check could not re-read arm M's raw files. | Each repair's `debug.log` and trace segments, the histograms, the direct-memory readings, the `nodetool repair` output and the scratch tokens are saved under `<label>/raw/`; set-up copies the previous node logs before a wipe. Attempt 1 is kept in `cluster.attempt1/` (its summaries only). | Cluster tier restarted 2026-10-14 11:29 | none (harness only) |

## 4. Run 1

**Scope:** both tiers, every value in §1. Unit: `unit-run.sh all` (attempt 2, after defect 1). Cluster: `rss-chain.sh`, labels
`m-setup m-control m-a m-b m-c m-depth down o-scratch o-setup o-run down`, 2026-10-14 11:29–11:42 MDT (attempt 2, after defect 2),
2^20 rows. **Command logs:** `<label>/session.log` on the node; excerpts in
[`repair_session_space-split-maxsize/run1/`](repair_session_space-split-maxsize--guided/run1/) (`unit/`, `cluster/<label>/summary.txt`,
`readings.csv`, `raw/` with the trace files, the `Created`/`Prepared`/`Allocating` lines of each `debug.log` segment, the
histogram lines, the direct-memory readings; `chain.log`, `harness.md5`, `selfcheck.out`). The optional over-streaming step was not run.

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, `run1/unit/harness.out`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Upstream `MerkleTreeTest` | 27 run, 0 failures, 0 errors | `unit/summary.txt`, `unit/TEST-org.apache.cassandra.utils.MerkleTreeTest.xml` |
| Upstream `ValidatorTest` (incl. `testSizeLimiting`: 2^12 leaves at 1 MiB) | 6 run, 0 failures | `unit/TEST-org.apache.cassandra.repair.ValidatorTest.xml` |
| Harness `RepairSessionSpaceTreeTest` | 4 run, 0 failures; 78 `STAGE4 check` lines, 78 ok | `unit/harness.out` |
| U1, the check alone (*M* = 2, 1024, 16384) | First `false` at `size == M` every time; *M* − 1 successful splits; 1,000 further calls all `false`, `size` unchanged; leaves counted = *M*. Allocation: empty-interval baseline **0 B**; every refused call **0 B**; each successful split 224–696 B (mean 296–552), all ≥ 112 B (`OnHeapInner` 48 + 2 × `OnHeapLeaf` 32; the rest is the `RandomPartitioner` midpoint token) | `unit/harness.out` (`U1 …`) |
| U2, `init()` | 2 → 2, 1024 → 1024, 16384 → 16384, 1000 → 512 leaves (counted and `size`); `measureDeep` 168 B per leaf (`RandomPartitioner`, no hashes yet) | `U2 …` |
| U3, depth table | **Leaf 80 B; inner 120 B (Murmur3), 128 B (byte order)**: leaf + inner 200 and 208 B, inside (128, 256]. *d* = 11, 12, 13, 14, 15, 17, 18 for *b* = 0.5, 1, 2, 4, 8, 32, 64 MiB, the **same for both partitioners** | `U3 depth_table …` |
| U3, derivation, `init()` path, 2^14 keys (*n* = 16384) | *s* = 1, 2, 4 → 4096, 8192, 16384 leaves (the last also the partition term) | `U3 init …` |
| U3, split path, 2^16 keys (*n* = 65536) | *s* = 1, 2 → 4096, 8192 leaves, `size == maxsize` (a capacity stop, not `TooDeep`); with the trace attached (instrument run): `split refused size=maxsize`, `samples=512`, `split calls` = *L* | `U3 split …`; `~/stage4-logs/rss/unit-instrument/split.trace` |
| U3, depth cap 10 at *s* = 64 | 1024 leaves | `U3 depthcap10 …` |
| U4, the overflow (`init()` path, RF 1) | 32-bit products: 2047 → 2,146,435,072; **2048 → −2,147,483,648; 4096 → 0; 4097 → 1,048,576; 5120 → 1,073,741,824**. Leaves: **16384, 2, 2, 4096, 16384** — each equal to 9e's prediction and to the formula | `U4 …` |

**Cluster tier** — *n* is each node's `Created … merkle trees` count; *L* is the `Prepared AEService trees of size` count; both nodes read the same *L* at every value (`readings.csv`). Arm M: N1 *n* = N2 *n* = 524,288 before B, 1,048,704 after.

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| default (read back **128** MiB on both) | control | *L*; `split calls`; N1 off-heap lines | **262,144** (pred. 2^min(20, 18, 20)); 0; two × **21,495,840** B = 82 *L* + 32 | `cluster/m-control/summary.txt`, `raw/control-sdefault-*` |
| default | control, held | N2 histogram change; N1 direct `MemoryUsed` during hold | `OnHeapLeaf` **+262,144** (8,388,608 B), `OnHeapInner` **+262,143** (12,582,864 B); direct +21,496,034 B (one buffer: 21,495,840) | `raw/control-hold-sdefault-N2-histo-*.txt`, `raw/…-N1-direct-*.txt` |
| 1 MiB | A, A held | *L*; calls; off-heap; heap Δ; direct Δ | **2,048**; 0; 2 × 167,968 B; +2,048 / +2,047; +167,968 B | `cluster/m-a/summary.txt`, `raw/A-s1-*`, `raw/A-hold-s1-*` |
| 4 MiB | A, A held | same | **8,192**; 0; 2 × 671,776 B; +8,192 / +8,191; +671,392 B | `raw/A-s4-*`, `raw/A-hold-s4-*` |
| 16 MiB | A, A held | same | **32,768**; 0; 2 × 2,687,008 B; +32,768 / +32,767; +2,686,624 B | `raw/A-s16-*`, `raw/A-hold-s16-*` |
| 64 MiB | A, A held | same | **131,072**; 0; 2 × 10,747,936 B; +131,072 / +131,071; +10,747,552 B | `raw/A-s64-*`, `raw/A-hold-s64-*` |
| 4, 16 MiB | B (2^21 rows, *n* = 1,048,704) | *L* | **8,192, 32,768** — unchanged from A | `cluster/m-b/summary.txt` |
| 2048 MiB | C, overflow | *L*; off-heap | **2** on both nodes; 2 × 196 B | `cluster/m-c/summary.txt` |
| 4097 MiB | C, overflow | *L*; off-heap | **2,048** (= the 1 MiB count); 2 × 167,968 B | `cluster/m-c/summary.txt` |
| 64 MiB, `repair_session_max_tree_depth: 15` | C, depth cap | *L*; deprecation warning | **32,768** = 2^15 (*d* = 17 capped); warning logged on both nodes | `cluster/m-depth/summary.txt` |
| — | every arm-M repair | `split calls` | **0** on both nodes in all 15 validations per node; no refusal line | `raw/*-trace.log` |
| default | arm O set-up (not judged) | *L*, refusal, samples | 262,144 on both; `split refused size=262144 maxsize=262144`, no `toodeep`; samples 4,273 / 4,272; *n* = 546,944 / 546,816 (> 2^16) | `cluster/o-setup/summary.txt` |
| 4 MiB | arm O, A | *L*; refusal; calls; samples; off-heap | **8,192**; `split refused size=8192 maxsize=8192` once per node, no `toodeep`; 8,192 calls; 4,273 / 4,272 (*n*/128 = 4,273 / 4,272); none | `cluster/o-run/summary.txt`, `raw/A-s4-*-trace.log` |
| 16 MiB | arm O, A | same | **32,768**; `split refused size=32768 maxsize=32768` once per node, no `toodeep`; 32,768 calls; 4,273 / 4,272; none | `raw/A-s16-*-trace.log` |

Arm O tokens (scratch node, 1,000 keys): smallest `0x303032344c3531304d30`, median `0x3835344d4b4c36363131` (node 1), largest `0x5050504f3938304f4f30`; node 2 at `00` (`cluster/o-scratch/`, `raw/scratch-tokens.txt`).
Cluster attempt 1 (before defect 2) gave the same *L* at every value and 92 `EXPECTED` yes, 0 no (`cluster/attempt1/`).

### 4.2 Conclusion and logic

1. **Validity.** The run is valid. The knob took at every value: `KNOB … set s read back s / s` on both nodes for 1, 4, 16, 64, 2048, 4097 and 64 (depth arm), and the default read back 128 [observed: `cluster/*/summary.txt`]. The partition term never bound: ceil(log2 *n*) = 20 (arm M before B, arm O) or 21 (after B) against depth ≤ 18 [observed: `readings.csv`; self-check]. Hold-fixed settings: `num_tokens: 1`, `concurrent_merkle_tree_requests: 1`, the partitioners and tokens are in each node's yaml tail [observed: `cluster/m-setup/summary.txt`, `o-setup/summary.txt`]; `use_offheap_merkle_trees` and the `big` format at their defaults [observed: off-heap lines present on arm M; `samples=` lines on arm O, which BTI would not give]; one table, `-pr`, autocompaction disabled at creation [observed: `session.log` CQL]. Every instrument fired: one `Created`, one `Prepared` and one `split calls` line per validation per node, a `hold start` for each held repair, a `samples` line for each arm-O validation [observed: `raw/`; self-check].
2. **Readings.** No gap or outlier. Both nodes read the same *L* at every value. The direct-memory rise during the hold is within 384 B of one buffer at every value (support only). Arm O's set-up repair at the default reached 2^18 leaves from about 4,273 samples (≈ 61 splits per sample) with a capacity refusal and no `TooDeep` [observed: `o-setup/summary.txt`]; this is an extra observation, not judged.
3. **Matched rows.**
   - **Confirmed** — "*L* equals the prediction at every value on both arms; it doubles per doubling of *s*; scenario B leaves it unchanged; arm O shows refusals at `size == maxsize`; heap and off-heap bytes scale with *L*": *L* = 2,048 · 8,192 · 32,768 · 131,072 · 262,144 at 1 · 4 · 16 · 64 · 128 MiB, each equal to 2^min(ceil log2 *n*, *d*(*b*), 20) with *d* from the unit tier's table [observed: `readings.csv`]; ×4 per ×4 of *s*, ×2 to the default [observed]; B: 8,192 and 32,768 with twice the data [observed: `m-b`]; arm O: one `split refused size=L maxsize=L` per node per validation, no `toodeep`, at 4 and 16 MiB [observed: `raw/A-s*-trace.log`]; heap: `OnHeapLeaf` +*L*, `OnHeapInner` +(*L* − 1) at five values, 80 B per leaf shallow [observed: histograms]; off heap: two buffers of exactly 82 *L* + 32 B per validation [observed: `debug.log` lines]. Unit tier U1–U3 the same, with the split-path stop at `size == maxsize` and refused calls allocating 0 B [observed: `unit/harness.out`].
   - **Non-domination as recorded** — "Arm M: `split()` never called and *L* as predicted": `split calls=0` on both nodes in every arm-M validation, *L* as predicted [observed: traces].
   - **Overflow as recorded** — "*s* = 2048 gives *L* = 2 and *s* = 4097 gives the 1 MiB count": 2 and 2,048 on both nodes [observed: `m-c`]; the 32-bit products in U4 [observed: `unit/harness.out`]. Target-3 material; the over-streaming step was not run.
4. **Excluded rows.** *Refuted (L > maxsize)*: no validation exceeded its prediction; the split path stopped at exactly `maxsize` [observed]. *Refuted (L does not move with s)*: it moved ×4 per ×4 [observed]. *Not confirmed (TooDeep)*: no `toodeep` line in any run-1 validation; every arm-O and U3 split-path refusal had `size == maxsize` [observed]. *Refuted (overflow arms give large trees)*: 2 and 2,048 leaves [observed]. *Invalid (partition term binds)*: ceil log2 *n* ≥ 20 > depth [observed]. *Invalid (read-back differs)*: every read-back equal [observed]. *Invalid (instrument silent)*: every line present [observed].
5. **Observed vs. inferred.** The conclusion rests on no inferred statement. Two readings are interpreted rather than read: that the histogram change is the held tree (the idle histogram before each held repair showed no `OnHeapLeaf` or `OnHeapInner` instance, only a 16-byte `MerkleTree` lambda singleton; inferred: no other tree was built on N2 during the hold, since one validation runs at a time), and that the direct-memory rise is N1's own buffer (support only, not used for the verdict).
6. **Deviations and gaps.** Both nodes ran on one host (amendment, §1 rec. 9). The heap histogram counts the node objects' shallow size (80 B per leaf with its inner node); the 32-byte hash arrays filled during validation are `byte[]` and not attributed to the tree in a class histogram, so the tree's full heap is larger than read (U3's `measureDeep` of trees without hashes: ≈ 120 B per leaf). The off-heap reading is the logged allocation size, cross-checked by `MemoryUsed`; the budget assumes 200–208 B per leaf, the off-heap tree takes 82 B per leaf. The optional over-streaming step was not run, so the overflow's cost (streaming) is not measured. Arm O ran two values, as 9e specifies.
7. **Core question.** (1) The partition term did not bind (part 1). (2)–(3) Leaves per tree equal the predicted `maxsize` at every value and follow the knob ×4 per ×4 up to the default, unchanged when the data doubles (part 3): usage stops at the limit and follows the constraint. (4) On the ordered partitioner the capacity check's disallow branch stops the split loop at `size == maxsize` with no `TooDeep`; on Murmur3 `split()` is never called and `init()` builds exactly `maxsize` leaves (part 3). (5) The replica's heap node count and the coordinator's off-heap buffers scale exactly with *L* (part 3). (6) From 2048 MiB the 32-bit product wraps and the knob cuts trees to two leaves; 4097 MiB behaves as 1 MiB (part 3). **`repair_session_space` caps each validation's Merkle tree as traced, and the cap follows the knob, until it overflows at 2 GiB.**

**Conclusion (one line):** **Confirmed** at both tiers (arm O: the capacity check stops the split at `maxsize`); arm M **non-domination as recorded**; **overflow as recorded**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.py` (independent of `cluster-run.py`: it re-parses the raw `debug.log` and trace segments, histograms, direct readings and
`harness.out`, and recomputes every prediction from 9a's formula with the unit tier's depth table): **266 checks, 0 failed**, exit 0
(`run1/selfcheck.out`). Every *L* equals 2^min(ceil log2 *n*, *d*(*b*), *D*) recomputed from the raw *n*; the partition term never binds; arm M has
`split calls=0` and two `82 L + 32` buffers per validation; arm O has exactly one refusal at `size == maxsize == L`, `L` split calls and
*n*/128 samples (within 2 %); the histogram changes are +*L* / +(*L* − 1); the sequence across *s* is ×4, ×4, ×4, ×2; B unchanged; overflow 2
and 2,048; depth cap 2^15; arm O equals arm M at 4 and 16 MiB; unit JUnit XML clean, U1–U4 against 9e's literal values and the formula.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Read-backs re-read from each label's `summary.txt` (`KNOB` lines); *n* from the raw `Created` lines; instrument lines counted per validation in `raw/`. |
| 2. Readings | yes | `readings.csv` rows against `raw/` segments; both nodes agree at every value. |
| 3. Matched row | yes | Each part of the Confirmed, non-domination and overflow rows re-derived by `selfcheck.py` from raw files. |
| 4. Excluded rows | yes | No `toodeep` line in any run-1 trace (`grep -c` over `raw/*-trace.log` = 0); no *L* above prediction. |
| 5. Observed vs. inferred | yes | The idle histograms (`raw/*-histo-idle.txt`) show no `OnHeapLeaf` or `OnHeapInner` before each held repair (only a 16-byte lambda singleton); the one inference (no other tree on N2 during the hold) is supported by `concurrent_merkle_tree_requests: 1` and one repair at a time. |
| 6. Deviations and gaps | yes | Stated; none bears on the matched rows. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | Logic (1)–(6) of 9a's "How this verifies the hypothesis", each with an observed reading. |

### 5.2 Run 2?

**No** — decided 2026-10-14. Every reading is an exact count matched to an exact prediction, the conclusion rests on no inferred statement,
and the independent self-check over the raw files holds with no failures. The overflow row is a runtime confirmation of a defect in the
knob's conversion, not of a path past the cap; it is observed at both tiers (the 32-bit products printed in U4, two-leaf trees on both
nodes), so a by-hand repeat would add no independence the unit tier does not already give. Cluster attempt 1 (before defect 2, same
harness logic) read the same *L* at every value.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

| Tier | Verdict (§9a row) | Basis | Date |
|---|---|---|---|
| Unit | **Confirmed** (U1 the check refuses at `size == maxsize` and allocates nothing; U2 `init()` builds `maxsize` leaves; U3 the derivation and both build paths; depth cap) — and **overflow as recorded** (U4) | run 1 + self-check | 2026-10-14 |
| Cluster | **Confirmed** (arm M sweep and B, arm O refusals at `size == maxsize`, heap and off-heap scale with *L*); arm M **non-domination as recorded**; **overflow as recorded** (2048 MiB → 2 leaves, 4097 MiB → the 1 MiB count) | run 1 + self-check | 2026-10-14 |

**Feedback filed:** the case file's §10 "Stage-4 feedback" field (uncommitted), and a §10 note for stage 3: §7's off-heap
"Rough sizing" carries the formula corrected in §9a (rec. 1, not applied to §7); §11's open point ("whether a later release fixed it") stays
open, but the overflow is now observed at runtime in 5.0.9. No section beyond the step-0 amendments to §9 was amended: no row refuted
the traced path, and the overflow was already recorded in §4, §8 and §10.
