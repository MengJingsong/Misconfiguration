# trie-pathreconstructor-keybytes-addPathBytes-growth--autonomous — stage-4 results  <!-- file: results/trie-pathreconstructor-keybytes-addPathBytes-growth--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`trie-pathreconstructor-keybytes-addPathBytes-growth--autonomous`](../../stage3-ai-deep-read/cases/trie-pathreconstructor-keybytes-addPathBytes-growth--autonomous.md)
>
> **Status:** verdict filed (2026-10-25) — run 1 done at both tiers, self-checked, no run 2
>
> **Outcome class:** **true negative** (estimate `negative`, effect `does not cap`) — [definition](../README.md#outcome-class)
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
| **Case-file version** | Base repository commit `f33e621`; the case file is **untracked** in the working tree. As filed: sha256 `eba6a1437c594ad22e161024f24b3233b3359a8bc7e712ada38e5ccaaea63953`. **After the audit's amendments (B2i, B3i, five inline markers, all dated 2026-10-25): sha256 `c14901f1ef7c079b8bbd515666fe68a8909ddcf44e069772c5275ef005a43a47`**, written at 2026-10-25T23:29:07Z to `results/<stem>/run1/freeze.sha` before any harness existed and before any reading. **Frozen tables** (B2f, B2g, B3f, B3g text, extracted into `results/<stem>/run1/frozen-tables-B2f-B2g-B3f-B3g.txt`): sha256 `bca89e2221062890a06560da23784c38ec7ee5dd81d5f7c0fbb95653e7efdd96`. Section D (feedback) is filled afterwards; the sha256 with D filled is in section 8. |
| **Harness** | `harness/trie-pathreconstructor-keybytes-addPathBytes-growth--autonomous/` (written after the freeze; not committed by this agent). |
| **Tiers and values** | **Unit (B2):** key length L = 16, 1 000, 20 000, 65 535, 131 070 at N = 1 000; N = 1, 1 000, 100 000 at L = 16 and at L = 1 000 (B2i.2); ON_HEAP and OFF_HEAP; empty trie; 3 repeats. **Cluster (B3):** labels A128, A512, B128, B512 (Run A: 1 000 000 rows of pk 16 B; Run B: 2 000 rows of pk 60 000 B; `memtable_heap_space` 128 / 512 MiB), each twice. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-25 |

### 1.1 Design audit

Estimate: **negative** (line 41 is the grow-on-demand check of a scratch array, not a limit). Audited against `cassandra/cassandra-5.0.9/` (`git status` of it prints nothing; `build.xml` `base.version` 5.0.9). Re-read in the pinned source: `TriePathReconstructor.java:26-56`, `TrieEntriesIterator.java:30-66`, `TrieEntriesWalker.java:28`, `Trie.java:205-218, 243-245, 322-331, 435`, `InMemoryReadTrie.java:63-68, 520-573`, `InMemoryTrie.java:58-68, 88, 186, 895-910, 951-978`, `TrieMemtable.java:89-127, 160-205, 340-400, 440-490, 540-560`, `AbstractShardedMemtable.java:34`, `AbstractAllocatorMemtable.java:59, 81, 118`, `DecoratedKey.java:105-113`, `ByteSource.java:46-64`, `FBUtilities.java:158`, `Validation.java:45-55`, `QueryProcessor.java:255-262`, `ClusteringPrefix.java:265-292`, `MemtableParams.java:95-135`, `TableAttributes.java:123-124`, `conf/cassandra.yaml:783-812, 825, 899`, `build.xml:1382-1385, 1128-1153`.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: an on-heap `byte[]` scratch per iterator, bytes = capacity + 16. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | The constant (65535) cannot be varied (A1); the design varies what the claim says the array follows (key length, five values) and what it should not follow (N, buffer type, `memtable_heap_space` 128 / 512 MiB with the default 1/4 heap not run). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met | Unit: the array's real length. Cluster: the filed JFR sampling can miss 32 to 64 KB allocations; replaced by an exact Byteman trace at the two growth statements (B3i.6). Gap named: liveness of arrays at an instant is not observed. |
| A. Core question | usage driven to the limit and past it | Met | Unit: L up to 131 070 (past 65 535). Cluster: Run B reaches a 60 000 B key (the largest practical, validated at 65 535) and the memtable limit is crossed at 128 MiB (B3i.3). The N sweep at L = 16 never grows the array; a second N sweep at L = 1 000 was added (B2i.2). |
| A. Core question | positive control for a negative estimate | Partly → Met | Unit: only "content moves" (not a cap); two-sided sensitivity control recorded (B2i.4). Cluster: `memtable_heap_space` is a binding cap on the same memtable (closed `memtable_heap_space` cases); flush count and occupancy peak are measured (B3i.5). |
| B. Logic | each step says what it establishes | Met | B2e / B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met | B2f has ranges (`[L, 2L+16]`); B3f was "tens to hundreds of bytes" and "120 to 250 KB". Derived numbers added, nothing in B3f or B2f changed (B2i.3, B3i.8). Two inexact statements corrected: "32 or 48" for L = 16 is exactly 32; one `addPathBytes` call delivers at most 27 bytes, not 28. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g / B3g cover growth with N, buffer type, stuck at 32, control failed, off-policy growth; the cluster rows cover scaling, >10 %, control failed, no samples. Clarified that the cluster comparisons are per iterator (B3i.7), since totals scale with the number of flushes by design. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | For this "does not cap" claim there is no disallow branch (the check always grows); the evidence is the direct reading of the array at every knob value plus the moving control. |
| B. Logic | alternative explanations and their controls | Met | B2h, B3h: key size isolates length; idle baseline (counts before the workload); known-cap control. |
| C. Specific | a human can follow it from the intro and B1 | Met | A3, B1. |
| C. Specific | an AI can run B2 / B3 without re-deriving the code path | Partly → Met | Scan-then-flush order, table syntax, config block, sizes, ports, JVM, per-run settings now exact (B3i.1-4); runner flags verified (B2i.1). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | As above; sampling every 5 s for the occupancy, the scan duration is one pass of the table. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | `ant build-test` on `~/s4-tp41` (pc12) succeeded in 1 min 8 s; Byteman 4.0.20 in `build/lib/jars`; the test, helper class, rules and driver are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly → Met | 200 000 small rows would cross the 42.7 MiB cleanup threshold at most once and never the 170.7 MiB one; raised to 1 000 000 (B3i.3). Run B about 137 MB of trie data on a 2 GiB heap; disk under 1 GB per run; 47 GB free on pc12 `/`. Unit: L = 131 070 x 1 000 keys is about 160 MB trie plus overhead in the 1 GiB test JVM. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Correct: `TriePathReconstructor.java:28,41-42`, `FBUtilities.java:158`, `Validation.java:51`, `QueryProcessor.java:259`, `ClusteringPrefix.java:272-288`, `TrieMemtable.java:94, 356, 392, 552`, `Trie.java:329, 435`, `InMemoryTrie.java:969, 975`, `conf/cassandra.yaml:797, 799, 825`. Wrong in substance: A3's "partition-key + clustering concatenated" (the memtable trie holds only token + partition key) and "up to 28 bytes" per call (27). `InMemoryTrie.java:88` is the constructor as cited. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Use the shipped `trie` configuration block; no yaml edit (the writer's unverified item) | Applied, B3i.1, 2026-10-25 | `conf/cassandra.yaml:783-790` already defines it; table clause `WITH memtable = 'trie'`. |
| 2 | Runner flags (the writer's other unverified item) | Applied, B2i.1 | `ant testsome -Dtest.name=<FQCN>`, forked JVM fixed at 1024m. |
| 3 | Scan before the explicit flush | Applied, B3i.2 | A `SELECT *` after the flush reads sstables, not the trie. |
| 4 | Run A to 1 000 000 rows | Applied, B3i.3 | The cleanup threshold is `memtable_heap_space / 3`. |
| 5 | Byteman trace at lines 34 and 42 as the primary instrument; JFR secondary | Applied, B3i.6 | Exact, countable, per iterator. |
| 6 | Per-iterator comparison across `memtable_heap_space` | Applied, B3i.7 | More flushes mean more iterators; totals cannot refute. |
| 7 | N sweep also at L = 1 000 | Applied, B2i.2 | At L = 16 the array never grows. |
| 8 | Positive-control wording for the unit tier | Applied, B2i.4 | Content moving is not a binding cap. |
| 9 | Correct A3 (path = token + key; 27 bytes per call); fix "32 or 48" | Applied (B2i.3) as an amendment note; the A-section text is left | Cosmetic; no row depends on it. |
| 10 | The array lives only while an iterator does and is O(100 KB): consider whether a negative estimate for such a scratch buffer is worth a cluster run | Left for stage 3 | The design answers the question as filed. |

**Agreement criteria** — not applicable (run 2 not chosen unless §5.2 says so).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-25 (unit 17:31 MDT; cluster 17:38 to 18:06 MDT) | not done |
| Node (CloudLab name and type) | `pc12` (`node1.jason92-320876…`, control 198.22.255.22), 40 cores, 251 GiB; shared with other agents' trees (`~/s4-cdc`, `~/s4-ci`, `~/s4-pk`, `~/s4-ss`), none touched | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2, `5.15.0-187-generic` | |
| JDK (`java -version`) | openjdk 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-tp41` by `copy-source.sh` (local baseline `fb66ee2`, tag `cassandra-5.0.9`), from repository commit `f33e621`; `ant build-test` 1 min 8 s | |
| Case-file commit / harness commit | case file untracked, sha256 `c14901f1…a43a47` (section 1); harness uncommitted (md5s in `results/<stem>/run1/unit/harness.md5` and `run1/cluster/harness.md5`) | |
| Storage for node data | local `/dev/sda3` (rotational, 63 GB, 46 GB free) under `~/s4-tp41-run/node`; nothing on `/proj` | |
| Full logs (path, outside the repo) | `pc12:~/s4-tp41-run/` (`out/unit/ant.log`, `out/cluster/<label>/system.log`, `cluster-run.out`, `shakedown-not-readings/`) | |

Ports and address (as assigned): loopback `127.0.41.1`, storage 7011, native 9143, JMX 7211; the Byteman agent ran without a listener (9111 unused). JVM `-Xms2G -Xmx2G` G1 (live command line saved per label in `cluster/<label>/evidence/cmdline.txt`). `ulimit -n 100000` in the starting shell.

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B3e step 2 | `SELECT *` after `nodetool flush` reads sstables, not the trie | scan first, then flush (B3i.2) | amended before the freeze, 2026-10-25 | untracked file; sha256 in section 1 |
| 2 | audit | B3c Run A | 200 000 rows cross the cleanup threshold at most once | 1 000 000 rows (B3i.3) | amended before the freeze | same |
| 3 | audit | B3d | JFR sampling can miss 32-64 KB allocations | Byteman trace at lines 34 and 42 (B3i.6) | amended before the freeze | same |
| 4 | harness (not a defect of the case) | driver | the bundled driver zip has a top directory `cassandra-driver-3.29.0/` | path fixed in `cluster-run.py` before any run | 2026-10-25 | n/a |

No step failed during run 1; the first cluster start-up shakedown (300 rows, not a reading, `~/s4-tp41-run/shakedown-not-readings/`) found only defect 4.

## 4. Run 1

**Scope:** unit tier, every cell of B2i (72 cells = 2 buffer types x 3 repeats x 12 cells); cluster tier, labels A128, A512, B128, B512, each twice (r1, r2), eight fresh node starts. **Command log:** `run1/unit/session.log`, `run1/cluster/` (per-label `result.json`, `tp-events.txt`, `tp-stats.txt`, `flush-lines.txt`, `evidence/`); the cluster driver's console log is on the node (`cluster-run.out`). Paths below are under `results/trie-pathreconstructor-keybytes-addPathBytes-growth--autonomous/run1/`.

### 4.1 Readings

**Unit tier** (`unit/results.csv`, `unit/analysis.txt`; JUnit `Tests run: 1, Failures: 0, Errors: 0`, `unit/ant-tail.txt`). Capacity = `keyBytes.length` after a full walk of N keys of L random bytes; the three repeats are identical in every cell.

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Empty trie (N = 0) | capacity 32 | `unit/results.csv` |
| L sweep, N = 1 000, ON_HEAP and OFF_HEAP: L = 16, 1 000, 20 000, 65 535, 131 070 | capacity 32, 1 024, 32 768, 65 536, 149 504 (all inside [L, 2L+16]; L = 16 inside because the path fits the initial 32) | `unit/analysis.txt` |
| N sweep at L = 16 (N = 1, 1 000, 100 000), both buffer types | capacity 32 in all six cells | `unit/analysis.txt` |
| N sweep at L = 1 000 (N = 1, 1 000, 100 000), both buffer types | capacity 1 024 in all six cells | `unit/analysis.txt` |
| ON_HEAP vs OFF_HEAP at every L (N = 1 000) | identical capacities | `unit/analysis.txt` |
| Control: `sizeOnHeap` (ON_HEAP) at L = 1 000, N = 1 / 1 000 / 100 000 | 1 852 / 1 174 776 / 116 895 288 B | `unit/results.csv` |
| Control: `sizeOffHeap` (OFF_HEAP) at L = 1 000, N = 1 / 1 000 / 100 000 | 1 152 / 1 169 600 / 116 493 696 B | `unit/results.csv` |
| Instrument check (Byteman events against the test's own capacity, three known-answer cells, not a reading) | the last Byteman capacity per receiver (1 024, 65 536, 1 024) equals the `PROBE` capacity | `instrument-check/main.out`, `instrument-check/tp-events.txt` |

**Cluster tier** (`cluster/<label>/`, `analysis-cluster.txt`). A = 1 000 000 rows with pk 16 B; B = 2 000 rows with pk 60 000 B; heap space 128 or 512 MiB. "Reconstructors" = `TriePathReconstructor` instances created (flush walks, scans, per-page range reads); growth events = executions of line 34 or 42.

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| idle (every label) | baseline before any write | growth events | 0 (all 8 labels) | `cluster/<label>/result.json` `stats_baseline` |
| 128 MiB | A r1 / r2 | reconstructors; growth events | 227 / 227; **0 / 0** | `tp-stats.txt`, `tp-events.txt` (empty) |
| 512 MiB | A r1 / r2 | reconstructors; growth events | 209 / 209; **0 / 0** | same |
| 128 MiB | B r1 / r2 | reconstructors; growing reconstructors; final capacities | 27 / 27; 26 / 26; 65 536 to 74 752 (flush walks 65 536; limit-flush walks during the write 65 536 to 69 632; scan pages 65 536 to 74 752) | `tp-events.txt` |
| 512 MiB | B r1 / r2 | the same | 23 / 23; 23 / 23; 65 536 (every one) | `tp-events.txt` |
| 128 MiB | B | scratch per growing reconstructor (sum of the new capacities at lines 34/42) | 131 008 to 149 431 B | `analysis-cluster.txt` |
| 512 MiB | B | the same | 131 008 B | `analysis-cluster.txt` |
| 128 MiB | B | largest per-reconstructor scratch against the smallest memtable at a flush (40.5 and 42.4 MiB) | 0.352 % and 0.336 % (r1, r2); against the 2 GiB heap 0.007 % | `analysis-cluster.txt` |
| 512 MiB | B | the same (smallest memtable at a flush 132.4 MiB) | 0.094 %; heap 0.006 % | `analysis-cluster.txt` |
| 128 MiB / 512 MiB | A r1 / r2 | control: `MEMTABLE_LIMIT` flushes of `ks.t` (excluding the one `USER_FORCED`) | 12 and 12 / 3 and 2 | `flush-lines.txt`, `system.log` |
| 128 MiB / 512 MiB | A | memtable size at a limit flush (`Usage` on the flush line) | 42.6 to 42.7 MiB / 170.7 to 170.8 MiB (= heap space / 3) | `flush-lines.txt` |
| 128 MiB / 512 MiB | B r1 / r2 | control: `MEMTABLE_LIMIT` flushes; size at the flush | 2 and 2 (43.0 to 44.0 MiB) / 0 and 0 (the single flush is the explicit one, 132.4 MiB) | `flush-lines.txt` |
| all | A, B | writes ok; scan rows; ERROR lines | 1 000 000 / 2 000 ok, 0 errors; scan returned all rows; 0 `ERROR` | `result.json`, `system.log.errors.txt` |
| 128 / 512 MiB | A, B | per-entry copy at line 54 (`toByteComparable`), outside the claim | A 57.3 to 57.8 MB total; B 279 to 363 MB total (about 60 KB per entry, transient) | `tp-stats.txt` (`copybytes`) |

### 4.2 Conclusion and logic

1. **Validity** — valid. The array was driven past its initial size and to the key-length limit: unit L up to 131 070 (past 65 535); cluster pk 60 000 B, capacities 65 536 to 74 752 **[observed: `cluster/B128r1/tp-events.txt`]**. Each "hold fixed" setting is confirmed: `-Xms2G -Xmx2G` and the Byteman agent in the live command line **[observed: `cluster/<label>/evidence/cmdline.txt`]**; `memtable_heap_space` 128MiB or 512MiB, `heap_buffers`, the assigned address and ports **[observed: `evidence/yaml-keys.txt`]**; the table is the trie memtable **[observed: `schema.txt` and the 12 / 3 limit-flush counts]**; the memtable still held data when the scan ran (43 136 columns at A128r1, 2 000 partitions at B512r1) **[observed: `result.json` `accounting.before_scan`]**; the reconstructor counts equal 2 per flush plus the scan pages (A128: 2 x 13 + 201 = 227; A512: 2 x 4 + 201 = 209; B128: 2 x 3 + 21 = 27; B512: 2 x 1 + 21 = 23) **[inferred: flush counts from `flush-lines.txt`, pages from 1 000 000 / 5 000 and 2 000 / 100; the totals match `tp-stats.txt`]**, so the flush and the scan both reached the iterator. The positive control moved (part 3).
2. **Readings** — unusual items: (a) Run A made no growth event in any of the 436 reconstructors of either repeat (227 + 209), which is the stated lower bound, not a missed instrument: the same rules fired 286 and 253 times in Run B and in the known-answer cells **[observed: `tp-events.txt`, `instrument-check/`]**. (b) The scan-page capacities at B128 (up to 74 752) exceed those at B512 (all 65 536). The arrays are sized by the first chain steps of the walked subtrie, which depend on which rows the memtable holds **[inferred: the growth formula, lines 34/42; B128 scans a memtable emptied by two limit flushes, B512 the full one]**; the larger values occur at the smaller heap space. (c) The 5-second sampler of `MemtableOnHeapDataSize` took one sample during Run B's 2 s write phase and its peaks (15.6 to 36.5 MB at B128) are not the real peaks **[observed: `result.json` `samples`]**; the control uses the exact `Usage` on each flush line instead (part 6a). (d) JFR cross-check: 880 to 1 666 allocation events with `TriePathReconstructor` in the stack at B, none at A; the 200 saved per label are all `toByteComparable` (line 54), none `addPathBytes` **[observed: `cluster/B128r1/jfr-tp-events.txt`]**; JFR is inconclusive for the scratch array, as the case file warned, and is not used.
3. **Matched row** — unit B2g row 1, "Capacity tracks L only (within [L, 2L+16]), flat in N and BufferType, while sizeOn/OffHeap grows with N: Claim confirmed". Capacity 32 / 1 024 / 32 768 / 65 536 / 149 504 for L = 16 / 1 000 / 20 000 / 65 535 / 131 070 and identical across 3 repeats **[observed: `unit/analysis.txt`]**; flat in N (1, 1 000, 100 000) at L = 16 and L = 1 000 and identical for ON_HEAP and OFF_HEAP **[observed: same]**; trie size grows 1 852 to 116 895 288 B with N at L = 1 000 **[observed: `unit/results.csv`]**. Cluster B3g row 1, "Scratch allocation tracks key size only; unchanged across memtable_heap_space; <1 % of memtable occupancy; occupancy and flush count move with memtable_heap_space: Claim confirmed". Tracks key size: Run A (16 B) no growth, Run B (60 000 B) 65 536 to 74 752 **[observed: `tp-events.txt`]**; across heap space: the same band 65 536 to 74 752 at 128 MiB and 65 536 at 512 MiB, scratch per reconstructor 131 to 149 KB vs 131 KB, never larger at the larger heap space **[observed: `analysis-cluster.txt`]**; below 1 %: 0.34 % to 0.35 % at 128 MiB, 0.094 % at 512 MiB **[observed: `analysis-cluster.txt`]**; control: limit flushes 12 vs 2 to 3 (A) and 2 vs 0 (B), flush size 42.7 vs 170.7 MiB (A) **[observed: `flush-lines.txt`]**.
4. **Excluded rows** — B2g row 2 (capacity grows with N): capacity identical for N = 1 to 100 000 at L = 16 and L = 1 000 **[observed: `unit/analysis.txt`]**. Row 3 (differs between ON_HEAP and OFF_HEAP): identical at all five L **[observed: same]**. Row 4 (stuck at 32 for all L): 1 024 to 149 504 for L >= 1 000 **[observed: same]**. Row 5 (trie size does not grow with N): it grows by a factor 63 000 **[observed: `unit/results.csv`]**. Row 6 (capacity beyond 2L+16): none; the largest ratio is 1.14 L (L = 131 070) **[observed: same]**. B3g row 2 (scales with `memtable_heap_space` or row count): per-reconstructor scratch is not larger at 512 MiB, and Run A's 1 000 000 rows make no event **[observed: `analysis-cluster.txt`]**. Row 3 (> 10 % of heap or memtable): 0.35 % at most of the smallest flushed memtable, 0.007 % of the heap **[observed: same]**. Row 4 (control failed): the flush count and size moved with heap space **[observed: `flush-lines.txt`]**. Row 5 (no samples): 286 and 253 growth events per Run B label (26 and 23 growing reconstructors) and the idle baseline at 0 **[observed: `tp-events.txt`]**.
5. **Observed vs. inferred** — inferred and load-bearing: (i) each Byteman event stands for a real `Arrays.copyOf` of the new capacity, computed by the helper from the line's own formula **[inferred: the formula is the source at lines 34 and 42; the known-answer cells show the last event's capacity equals the live `keyBytes.length`]**; (ii) a growth chain starts at old capacity 32 and one identity hash is one reconstructor within a chain **[inferred: capacity never shrinks, line 41-42; identities can repeat after GC, so a chain is cut when the old capacity is not the identity's last]**; (iii) the array is the only allocation counted by the claim, and `toByteComparable` (line 54) is a separate per-entry copy **[inferred: source, `TriePathReconstructor.java:52-55`]**; (iv) the memtable-size denominator is the on-heap `Usage` at flush time, not the live number of iterators **[inferred: at most two reconstructors are alive in a flush (`TrieMemtable.java:356, 392`), plus one per scan page]**.
6. **Deviations and gaps** — (a) the sampler cadence (3 s sleep plus about 2 s per JMX call) was too coarse for Run B's 2 s write phase; the frozen control (B3i.5) named flush count and peak; the flush count and the exact `Usage` on each flush line carry the control, the sampled peaks are reported as coarse. (b) B3f's "under 0.1 % of memtable occupancy" held at 512 MiB (0.094 %) and missed at 128 MiB (0.34 %), because the memtable at a limit flush is 42.7 MiB, not "hundreds of MiB"; B3g row 1's own threshold (1 %) holds and no row changes. (c) B3i.3 expected about three limit flushes at B128; two occurred (the data is about 130 MB and the third portion went to the explicit flush). (d) The unit tier ran before `cluster-run.py` existed, so its `harness.md5` lists no `.py`; the cluster run's md5 file is complete. (e) Liveness of arrays at an instant, and a heap dump, were not observed (named in the design). (f) JFR gave no usable cross-check. These limit the conclusion to: the array is sized by the walked path, once per reconstructor, and no memory knob set a ceiling on it in these runs; they do not weaken the unit-tier answer.
7. **Core question** — Usage of the scratch array did not follow the constraint: its capacity depended only on the longest path walked (32 for 16-byte keys, 65 536 to 74 752 for 60 000-byte keys, 1 024 to 149 504 across L = 1 000 to 131 070 in the unit tier) and stayed the same while trie content grew by a factor 63 000 and the memtable pool limit changed by a factor 4, even though the pool limit did bind the memtable itself (flush at heap space / 3: 42.7 vs 170.7 MiB) (parts 3 and 4; steps 1 to 3 of B2e/B3e). The line-41 check is a grow-on-demand test with no configured ceiling, so the constraint does not cap the usage it guards; the array is also tiny (at most 0.35 % of the smallest flushed memtable).

**Conclusion (one line):** unit: B2g row 1, claim confirmed; cluster: B3g row 1, claim confirmed (does not cap).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/trie-pathreconstructor-keybytes-addPathBytes-growth--autonomous/selfcheck.py` re-parses the raw files and does not import the analysers (it recomputes the arithmetic of every Byteman event, recounts flush reasons in `system.log`, re-derives the iterator chains per identity, compares `results.csv` with the RESULT lines of the raw test log, and checks the command line, the yaml and the schema). Its output (`run1/selfcheck.txt`): **178 OK, 0 BAD**. The parts, re-opened by hand as well:

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `evidence/cmdline.txt` and `yaml-keys.txt` of all eight labels re-read by `selfcheck.py` (heap, agent, `memtable_heap_space`, ports); idle baselines 0 events; scan after the writes found data in the memtable (`result.json`); the reconstructor counts match 2 per flush + scan pages. |
| 2. Readings | yes | `tp-stats.txt` events equals the lines of `tp-events.txt` for every label; every event obeys its formula (0 exceptions); 72 unit rows equal the test log's RESULT lines and each cell's three repeats are identical. The sampler gap (part 2c) is a real limit and is stated, not hidden. |
| 3. Matched row | yes | Unit: all inequalities of B2g row 1 recomputed. Cluster: B3g row 1 recomputed with limit-flush counts from `system.log` itself (12/12/3/2 at A, 2/2/0/0 at B) and flush sizes 42.6 to 44.0 and 170.7 to 170.8 MiB inside [hs/4, hs/2]. The "unchanged across `memtable_heap_space`" wording is satisfied as "inside one band, not larger at the larger heap space" (65 536 to 74 752 vs 65 536), not as bit-identical capacities; recorded in 4.2 part 2b. |
| 4. Excluded rows | yes | Each excluded row has the reading named in 4.2 part 4; none is contradicted by `analysis.txt` or `analysis-cluster.txt`. |
| 5. Observed vs. inferred | yes | (i) checked: the instrument check shows the last Byteman capacity per receiver equals the test's live `keyBytes.length` in three cells, and `selfcheck.py` finds no event that departs from the formula; (ii) checked on the data: no chain with inconsistent old capacity; (iii) from the source `TriePathReconstructor.java:52-55`; (iv) the flush count arithmetic matches `tp-stats.txt` exactly. |
| 6. Deviations and gaps | yes | Re-listed in 4.2 part 6 (sampler, B3f 0.1 % number, two limit flushes at B128, unit md5, JFR). None changes the matched row. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | Steps follow the audited B2e/B3e: array sized by key length (L sweep, Run B), not by N, buffer type, or heap space (N sweep, 128 vs 512), while the known cap (memtable pool) moved (flush counts and sizes). |

### 5.2 Run 2?

**No** (2026-10-25). The result is the expected non-effect, every cell was repeated (3 in-JVM repeats at the unit tier, two node starts per cluster label, identical event streams), the tier answers agree, and the inferred statements were checked in 5.1. A run 2 would not test anything the self-check cannot.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap).

**Claim tested:** (B1) The `keyBytes` scratch array's size does not follow any memory or disk limit setting: it depends only on the longest key walked (growth to about 2x the maximal encoded key, a few hundred KB at most), and stays flat while the memtable memory knobs and total memtable contents change by orders of magnitude. "Confirmed" below means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (capacity tracks L only, flat in N and BufferType, trie size grows with N) | does not cap | run 1 + self-check | 2026-10-25 |
| Cluster | **Confirmed** — B3g row 1 (scratch tracks key size only, not larger at the larger heap space, 0.35 % at most of the smallest flushed memtable, known cap moved) | does not cap | run 1 + self-check | 2026-10-25 |

**Positive control** (a negative-estimate file only): unit — the instrument is sensitive (capacity 32 to 149 504 as L goes 16 to 131 070) and content moves without the array moving (trie size x 63 000 with N, capacity constant); this shows no binding cap, so the unit tier speaks only for the array in isolation. Cluster — `memtable_heap_space`, a cap known to bind the same memtable: limit-driven flushes at heap space / 3 (42.6 to 44.0 MiB at 128 MiB, 170.7 to 170.8 MiB at 512 MiB), 12 vs 2 to 3 flushes (A) and 2 vs 0 (B), while the array stayed in the same band. Both moved in the run that left the array unchanged.

**Case file after section D was filled:** sha256 `8a9dabb08224133f9edb29981ba21b04b19c936ff98b71618ab6fa9ce5006b95`; the frozen tables re-hash to `bca89e22…dd96` (unchanged since 2026-10-25T23:29:07Z).

**Feedback filed:** the case file's section D updated (not committed; the orchestrator commits), no section of the case file amended after the freeze other than the dated audit amendments B2i and B3i. Leftovers: none (see below).

## Leftovers on pc12

No process of this run is running (`ps` for `CassandraDaemon` on `s4-tp41`: 0; the last node was stopped and checked by PID by the driver). On disk (not in `/proj`): `~/s4-tp41` (the tree), `~/s4-tp41-run/` (harness copy, helper jar, `out/`, `shakedown-not-readings/`, `node/` config and logs of the last label, `tcls/`, `tmpr1/` symlinks), `~/s4-tp41-logs/`. Node data and commit logs were deleted after each label.
