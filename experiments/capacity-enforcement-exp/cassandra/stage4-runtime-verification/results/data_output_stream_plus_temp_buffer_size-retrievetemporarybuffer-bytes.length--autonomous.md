# data_output_stream_plus_temp_buffer_size-retrievetemporarybuffer-bytes.length--autonomous — stage-4 results  <!-- file: results/data_output_stream_plus_temp_buffer_size-retrievetemporarybuffer-bytes.length--autonomous.md -->

> **Case:** [`data_output_stream_plus_temp_buffer_size-retrievetemporarybuffer-bytes.length--autonomous`](../../stage3-ai-deep-read/cases/data_output_stream_plus_temp_buffer_size-retrievetemporarybuffer-bytes.length--autonomous.md)
>
> **Status:** verdict filed (2026-11-12); run 1 done, self-checked; no run 2
>
> **Outcome class:** weak true positive (estimate `positive`; unit **Confirmed — caps**, cluster **Not confirmed** (path not exercised), so the class comes from the unit tier alone)
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `f74aade6` (case file untracked; filed sha256 `7bd7eeb1d0eecdff67c5fc242ef3d7990eb7c7ccd5c2f839e484d3fcc90ae378`, `_INDEX.md` §4). After the audit's amendments A1-A4 (2026-11-12): sha256 `8bf159fdcbb4aa00c11d90b9b74eae1212ac9c2ed0615470d8424ceb1d4d3035` (the frozen version; unit run 1 and the first cluster attempt). After amendment A5 (runbook defect D1, B3e only): `1a3a71ad9e92698107e8fece0121a342348020d0f156d0a9b957c9eabaf6fb52` (the version cluster run 1 used). Final, after section D: `18d2a8196d0551bd503346b98e5258b145c69576b9b11c2d1076416be4562c51` (the hash for `_INDEX.md` §4). sha256 of the frozen prediction and conclusions tables (text of B2f+B2g from `**B2f.` up to `**B2h.`, then B3f+B3g from `**B3f.` up to `**B3h.`, concatenated, 56 lines; copy at `/mydata/jingsong-cass-s4/o43/freeze/freeze-pred.txt`, frozen case file at `.../freeze/case-frozen.md`): `a3812c99b2659fcab89fa614c8a631dd86c7dacec7bc029c95b2664d095b231d`. Frozen 2026-11-12T03:21Z, before any reading. Section D is outside the table hash. Re-hashed after A5 and after section D: still `a3812c99…` (no prediction or conclusions row changed after any reading). |
| **Harness** | `harness/data_output_stream_plus_temp_buffer_size-retrievetemporarybuffer-bytes.length--autonomous/` (listed in its README; not committed by this session) |
| **Tiers and values** | Unit (B2): standalone probe JVM, P ∈ {4096, default 8192, 1048576, 16777216}. Cluster (B3): one node, 64 × 4 MiB blobs, `offheap_buffers`, serializing row cache, P ∈ {default, 1048576, 16777216}, plus control P=16777216 with `heap_buffers`. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-12 (A1-A3 applied; A4 is an audit note: from the source, the cluster tier is expected to land on its "path not exercised" row; A5 was added during run 1 for defect D1) |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: length of a per-thread `byte[]`, i.e. heap bytes retained per thread. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b: 4096, default, 1 MiB, 16 MiB; B3b: default, 1 MiB, 16 MiB. One JVM per value (static final). |
| A. Core question | real resource measured, not only the counter | Met | The operand is the array itself (B2d); heap via `MemoryMXBean` after GC (B2d) and `GC.class_histogram` `[B` bytes plus JFR allocation sizes (B3d). Gap named: which thread-local owns an array is inferred. |
| A. Core question | usage driven to the limit and past it | Met (unit) / Partly (cluster) | B2c: every cap is exceeded by some request. B3c: the 4 MiB request would exceed 8 KiB and 1 MiB caps, but see A4: the request does not reach `retrieveTemporaryBuffer` on a node. |
| B. Logic | each step says what it establishes | Met | B2c-B2e parts 1-3; B3e steps and B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Met after A3 | B2f exact lengths; heapDelta tolerance was "a few MiB" (A3 defines it). B3f: `ΔH ≈ T × A(P)`, ±16 MiB. |
| B. Logic | every plausible outcome has a conclusions row | Met after A3 | B2g lacked "heapDelta well below sumLen" (A3 adds it). B3g has bypass, not retained, path not exercised, workload failed, other consumer. Unmatched reading → "Not confirmed (no matching row)". |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Unit: requests > P give len = P (the false branch of :59 / the `min` of :62 is the disallow effect), lengths change with P. Cluster: JFR sizes = A(P). |
| B. Logic | alternative explanations and their controls | Met | B2h positive control (P=16 MiB grows to 16 MiB), fresh threads, non-growing reader; B3h `heap_buffers` control, `jinfo`, full-GC histogram. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate line, A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met | Full probe source and commands given. |
| C. Specific | knob, values, workload, commands, observables exact | Partly → Met after A1, A2 | Paths, ports, JMX port, direct-memory size and JFR parsing fixed by A1/A2. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | JDK 11.0.33, Ant 1.10.12, build done; bundled driver `lib/cassandra-driver-internal-only-3.29.0.zip`; `jcmd`, `jfr` in the JDK. |
| D. Runnable | workload arithmetic reaches the limit | Met (unit) / Not met (cluster, A4) | Unit: 32 × 8 MiB = 256 MiB < 1 GiB. Cluster: memory 4 GiB heap + 2 GiB max direct (actual ≈ 0.3 GiB) + ≈ 0.3 GiB row cache < 16 GiB; disk ≈ 300 MiB commit log. But the 4 MiB request never reaches the temp buffer (A4). |
| D. Runnable | load-bearing citations spot-checked | Met (unit) / Not met (cluster) | Checked in the 5.0.9 copy: `DataOutputStreamPlus.java:51, 56-65, 68-75, 78-131` (default channel, `retrieveTemporaryBuffer(toWrite)` at :115), `CassandraRelevantProperties.java:184`, `UnbufferedDataOutputStreamPlus.java:274-277, 357-369`, `WrappedDataOutputStreamPlus.java:33-37` (no channel → default channel), `SlabAllocator.java:52, 92-99`, `SerializingCache.java:109`. Not as the design assumes: `SlabAllocator.java:70` + `AtomicBTreePartition.java:220-223` + `EnsureOnHeap.java:60-65` clone memtable rows to heap on read (A4). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| A1 | Work dir `/mydata/jingsong-cass-s4/o43`, `copy-source.sh`, `ant build-test`, harness files, Python analyzer | applied 2026-11-12 (case file B2a; untracked, no commit) | shared node layout; comparison not by eye |
| A2 | Fixed ports 7300/7301/9342/JMX 7499, 127.0.0.1, `MAX_DIRECT_MEMORY_SIZE=2G`, `JVM_EXTRA_OPTS` not exported, JFR parsed in Python | applied 2026-11-12 (B3a) | shared node; 5.0.9 sets MaxDirectMemorySize itself; environment.md §6 |
| A3 | Define the heapDelta tolerance; add a B2g row for heapDelta well below sumLen | applied 2026-11-12 (B2f, B2g), before any reading | prediction must be contradictable; an outcome had no row |
| A4 | Audit note: on a node the memtable read clones values to heap (`EnsureOnHeap.CloneToHeap`), so the row-cache serialization never takes the direct-buffer branch; expect B3g "path not exercised" | note applied 2026-11-12 (B3c); workload, B3f, B3g unchanged; tier run as written | a substitute workload would not test the traced path (README) |
| A5 | Driver path `PYTHONPATH=<zip>/cassandra-driver-3.29.0` (runbook defect D1) | applied 2026-11-12 during run 1 (B3e); cluster tier restarted | B3e cannot run as written |
| R-a | Stage 3: redesign the cluster tier. The only other node caller is `writeUTF` (request ≤ 65537, array ≤ 128 KiB), so a node-level design would measure arrays ≤ min(P, 131072) per thread; or declare the cluster tier n/a with that reason | left for stage 3 | needs a new traced path |

**Agreement criteria:** not filled (no run 2).

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-11-12 (audit 03:18-03:22Z; unit 03:24:43-03:25:22Z; cluster attempt 1 03:25:34-03:27:10Z, stopped at D1; cluster run 1 03:27:42-03:37:02Z; self-check 03:37Z) | not done |
| Node | local `node0` (`node0.jason92-325405`), 32 cores, 125 GiB; shared with other stage-4 agents (this run: 127.0.0.1, storage 7300/7301, native 9342, JMX 7499) | |
| OS and kernel | Ubuntu 22.04.2 LTS, 5.15.0-198-generic | |
| JDK | openjdk 11.0.33 (G1; probe JVM region 1 MiB: `run1/g1-flags.txt`) | |
| Ant | Apache Ant 1.10.12 | |
| Local source copy | `/mydata/jingsong-cass-s4/o43/src`, `copy-source.sh` copy at repository HEAD `f74aade6` (5.0.9), `ant build-test` BUILD SUCCESSFUL in 1 min 36 s | |
| Case-file commit / harness commit | both untracked at `f74aade6` (the coordinator commits); case-file hashes in §1 | |
| Storage for node data | `/mydata` (local LVM, ext4), `$WORK/node/`; 268 MB of memtable (no SSTable, about 265 MB of commit log per run) | |
| Full logs (path, outside the repo) | `/mydata/jingsong-cass-s4/o43/run1/` (`unit/`, `cluster/<label>/` with full histograms, `system.log`, `jfr-<label>.json` from `jfr print --json`; the `.jfr` files were deleted per B4), `run1/cluster-attempt1/` (D1) | |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | cluster attempt 1 | B3e (`export PYTHONPATH=$(ls …driver-internal-only-*.zip)`) | `ModuleNotFoundError: No module named 'cassandra'`: the zip holds the package under `cassandra-driver-3.29.0/` (`run1/cluster-attempt1-default-D1.txt`). The node started and stopped cleanly; no reading was taken. | `PYTHONPATH=<zip>/cassandra-driver-3.29.0` (as `bin/cqlsh.py:56`); amendment A5; cluster tier restarted from its beginning | 2026-11-12 | untracked (no commit) |
| D2 | cluster run 1 | B3e (`jcmd … GC.class_histogram \| grep -E ' \[B$'`) | On JDK 11 the line ends `[B (java.base@11.0.33)` (`run1/cluster-default-hist-B-line-D2.txt`), so the filter printed nothing. | The harness also saved the full histogram of the same `jcmd` call (`hist0-full.txt`, `hist1-full.txt`); `cluster-analyze.py` and `selfcheck.py` read the `[B (java.base…)` line from it. **The tier was not restarted:** the command that takes the reading ran as written and its whole output was kept, and only the display filter was wrong. Recorded as a deviation from the restart rule. Not written into B3e (left for stage 3: use `grep -E ' \[B( |$)'`). | 2026-11-12 | n/a |

Instrument fix before any reading: `jfr-parse.py` first compared JFR `allocationSize` with P. The known-answer check (`JfrParseCheck`) showed that the size includes the 16-byte array header, so the parser now reports `arrayLength = allocationSize − 16`.

## 4. Run 1

**Scope:** unit tier (B2) as filed (A1, A3); cluster tier (B3) as filed (A2, A5): default, P = 1048576, P = 16777216 with `offheap_buffers`, control P = 16777216 with `heap_buffers`. **Command log:** `run1/cluster-<label>-session.log`, unit logs `run1/unit-<P>.log` (DEBUG lines removed); analyzers `run1/unit-analysis.txt`, `run1/cluster-analysis.txt`; self-check `run1/selfcheck.txt`.

### 4.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| 11 length readings × 4 P values against B2f (initial, 7 requests, directWrite 4 MiB, writeUTF 60000, part-3 sumLen) | 44/44 exactly as predicted, e.g. P=4096: every request ≥ 5000 → 4096; P=1 MiB: 4 MiB and 20 MiB → 1048576; P=16 MiB: 20 MiB → 16777216, 4 MiB → 8388608; writeUTF → 4096 / 8192 / 65536 / 65536 | `run1/unit-analysis.txt` (PASS lines), `run1/unit-<P>.log` |
| `len ≤ P` everywhere (incl. part-3 maxLen) | holds at all 4 P; max = P exactly (4096, 8192, 1048576) or 8388608 at P=16 MiB, where the largest request rounds to 16 MiB = P | `run1/unit-analysis.txt`, `run1/selfcheck.txt` |
| Requests above P | every one returned an array of length exactly P (disallow effect of :59/:62) | `run1/selfcheck.txt` |
| Part 3 heapDelta (32 live threads) | P=4096: 191,224 B (0.18 MiB); default: 322,296 B (0.31 MiB); 1 MiB: 67,167,560 B (64.06 MiB, sumLen 32 MiB); 16 MiB: 302,048,584 B (288.06 MiB, sumLen 256 MiB) | `run1/unit-<P>.log` |
| heapDelta vs A3 tolerance | noise rows PASS (P=4096, default); "tracks sumLen" FAIL at 1 MiB (+32.06 MiB, tolerance 4 MiB) and 16 MiB (+32.06 MiB, tolerance 25.6 MiB) | `run1/unit-analysis.txt` |
| Inspection of the excess (B2g "≫" row) | G1, region 1 MiB; heapDelta − 32 × ceil((len+16)/1 MiB) × 1 MiB = 58,696 B at both P | `run1/g1-flags.txt`, `run1/region-check.txt` |

**Cluster tier**

| Capacity value | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| default (8192) | A | P in the JVM | unset ("P unset (default 8192)") | `run1/cluster-default-session.log` |
| default | A | memtable / SSTables | 268,438,592 B memtable data, 268,435,712 B off-heap; SSTable count 0 before and after reads | same |
| default | A | row cache, read pass | 0 → 64 requests, 0 hits (64 misses); 64 entries, 256 MiB; "ok 64" | same |
| default | A | `[B` H0 / H1 / ΔH | 10,864,952 / 11,180,328 / +315,376 B (0.30 MiB) | `run1/cluster-analysis.txt` |
| default | A | JFR temp-buffer allocations | 0 (676 allocation events); 4 MiB clones by `HeapCloner` ← `AbstractCell.clone`: 128 | `run1/cluster-default-jfr.txt`, `run1/cluster-default-jfr-4mib-stacks.txt`, `run1/selfcheck.txt` |
| 1048576 | B | P / misses / SSTables / read | jinfo `=1048576`; 64 misses; 0; ok 64 | `run1/cluster-p1m-session.log` |
| 1048576 | B | ΔH; JFR | 10,870,472 → 11,180,992, +310,520 B (0.30 MiB); temp-buffer allocations 0; `HeapCloner` 4 MiB: 128 | `run1/cluster-analysis.txt`, `run1/cluster-p1m-jfr.txt`, `run1/selfcheck.txt` |
| 16777216 | C | P / misses / SSTables / read | jinfo `=16777216`; 64 misses; 0; ok 64 | `run1/cluster-p16m-session.log` |
| 16777216 | C | ΔH; JFR | 10,867,704 → 11,181,760, +314,056 B (0.30 MiB); temp-buffer allocations 0; `HeapCloner` 4 MiB: 126 | `run1/cluster-analysis.txt`, `run1/cluster-p16m-jfr.txt`, `run1/selfcheck.txt` |
| 16777216, `heap_buffers` | control | P / misses / SSTables / read | jinfo `=16777216`; 64 misses; 0; ok 64; memtable off-heap 0 | `run1/cluster-control-session.log` |
| 16777216, `heap_buffers` | control | ΔH; JFR | 286,641,384 → 286,958,512, +317,128 B (0.30 MiB); temp-buffer allocations 0; `HeapCloner` 4 MiB: 0 | `run1/cluster-analysis.txt`, `run1/cluster-control-jfr.txt` |

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — valid. Each P reached its JVM: the probe prints `P=<value>` [observed: `run1/unit-<P>.log`], and the lengths differ by P in the way that P predicts. Every cap was exceeded by a request (5000 > 4096, 20 MiB > 16 MiB, and so on) [observed: `run1/unit-<P>.log`]. Fresh threads in parts 2 and 3 [observed: probe source `harness/.../TempBufferProbe.java`].
2. **Readings** — unusual: heapDelta at P ≥ 1 MiB is 32.06 MiB above sumLen at both values [observed: `run1/unit-analysis.txt`]. The residual over the G1 humongous footprint is the identical 58,696 B at both P [observed: `run1/region-check.txt`]. The excess is therefore the region rounding of the same 32 arrays (1 MiB + 16 B → 2 regions, 8 MiB + 16 B → 9 regions) [inferred: G1 counts a humongous object's regions as used, and an identical residual at two different P leaves no room for a P-dependent other allocator].
3. **Matched row** — B2g row 1, "All lengths match B2f; `len ≤ P` everywhere → Claim confirmed at the operand level": 44/44 lengths equal B2f and none exceeds P [observed: `run1/unit-analysis.txt`, `run1/selfcheck.txt`]. For the heap observable, the reading falls under the row "`heapDelta` ≫ `sumLen` at the same P → Something else allocates; inspect before concluding" (2.0× at 1 MiB; +12.5 % at 16 MiB, beyond the A3 tolerance). The inspection (part 2) finds the same arrays, region-rounded, not another allocator. Retained heap follows P (0.18 → 0.31 → 64.06 → 288.06 MiB) [observed: `run1/unit-<P>.log`].
4. **Excluded rows** — "Any `len > P`" (cap bypassed, Refuted): no length > P [observed: `run1/selfcheck.txt`]. "Lengths identical across P for requests > 8192" (Refuted for the knob): the 4 MiB request gives 4096 / 8192 / 1048576 / 8388608 [observed: `run1/unit-analysis.txt`]. "writeUTF len > 131072": max 65536 [observed]. "heapDelta tracks sumLen": not met at P ≥ 1 MiB (above). "(A3) heapDelta below sumLen by more than the tolerance": heapDelta is above sumLen, not below [observed: `run1/unit-analysis.txt`].
5. **Observed vs. inferred** — the conclusion "caps" rests on observed lengths only. The one inference is that the heapDelta excess is G1 region rounding (part 2). The self-check tested it against the region size and the constant residual [`run1/selfcheck.txt`].
6. **Deviations and gaps** — the B2f heapDelta magnitudes (≈ 32 MiB, ≈ 256 MiB ± a few MiB) were not met; the prediction left out G1 humongous rounding. This limits the retained-heap part to "follows P, in region units", not "equals sumLen". The heap tolerance in A3 was set before any reading and was not changed.
7. **Core question** — yes. The array length, and so the heap each thread retains, is capped at P for every request above P, and it follows P across four values (B1's refuted-if conditions are not met: no array > P, and retained heap changes with P) [parts 1, 3, 4].

**Conclusion (unit, one line):** B2g row 1 — **confirmed** (operand level). The heap observable follows P, but its magnitude prediction missed, by G1 region rounding (inspected under the "≫" row).

**Cluster tier**

1. **Validity** — the workload ran as specified at every P: P reached the JVM (jinfo), 64 × 4 MiB stayed in the memtable (SSTable count 0, 268 MB memtable off-heap), and the read pass made 64 row-cache misses that cached 64 entries of 256 MiB [observed: `run1/cluster-<label>-session.log`, `run1/selfcheck.txt`]. The limit was never reached, because the traced call never happened (part 3).
2. **Readings** — ΔH is +0.30 MiB at all four runs, including the control [observed: `run1/cluster-analysis.txt`]. Each read pass took 60-72 s for 64 reads [observed: session logs, "read" to "JFR dump" timestamps]. It is slow but complete ("ok 64") and does not bear on the reading.
3. **Matched row** — B3g "No `retrieveTemporaryBuffer` allocations at any `P`, 64 row-cache misses seen → Path not exercised (values not direct, or different serialization); not confirmed". Zero JFR allocation events with `retrieveTemporaryBuffer` in the stack at default, 1 MiB and 16 MiB, with 64 misses each [observed: `run1/cluster-<label>-jfr.txt`, `run1/selfcheck.txt`]. The cause named in the row ("values not direct") is directly visible: on each offheap run, 126-128 4 MiB allocations by `HeapCloner.allocate` ← `ByteBufferCloner.clone` ← `AbstractCell.clone`, and none in the `heap_buffers` control [observed: `run1/cluster-default-jfr-4mib-stacks.txt`, `run1/selfcheck.txt`]. This matches the audit's source finding A4.
4. **Excluded rows** — "JFR sizes = A(P) … ΔH grows ~8×" (Confirmed): no temp-buffer allocations, and ΔH(16 MiB)/ΔH(1 MiB) = 1.01 [observed: `run1/cluster-analysis.txt`]. "A temp-buffer allocation > P" (Refuted): none at all. "JFR shows 8 MiB allocations but ΔH ≈ 0" (Refuted, not retained): JFR shows no 8 MiB temp-buffer allocations [observed]. "Row-cache misses < 64 or SSTable count > 0": 64 and 0 everywhere [observed]. "ΔH large at default": 0.30 MiB [observed].
5. **Observed vs. inferred** — the conclusion "the path was not exercised" is observed (JFR). An 8 MiB array cannot be allocated inside a TLAB (it is larger than any G1 TLAB), so at P = 16 MiB every such array would have produced an `ObjectAllocationOutsideTLAB` event [inferred: G1 TLABs are below the humongous threshold]. The flat ΔH at 16 MiB (0.30 MiB, not ≈ T × 8 MiB) confirms this independently [observed]. At P = 1 MiB a 1 MiB array could fall inside an existing TLAB and escape JFR, but ΔH is flat there too.
6. **Deviations and gaps** — D2: the tier was not restarted after the histogram filter defect (§3). JFR does not see small temp-buffer allocations made inside a TLAB (for example `writeUTF` growth to 8 KiB), so the run cannot say whether `writeUTF` used the buffer on the node; the design does not depend on it.
7. **Core question** — not answered at the cluster tier: the traced node path never calls `retrieveTemporaryBuffer` with the 4 MiB request, so usage could not follow or ignore P. The positive control (the P = 16 MiB offheap run) did not move, because the path was not reached, not because the cap held.

**Conclusion (cluster, one line):** B3g "No `retrieveTemporaryBuffer` allocations at any `P`, 64 row-cache misses seen" — **not confirmed** (path not exercised; memtable values are cloned to heap before caching).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-reads the raw files (unit logs, session logs, `nodetool info` files, full histograms, the JFR JSON), not the analyzers' output: 48 statements hold, 0 do not (`run1/selfcheck.txt`). The first pass had 4 "does not hold" lines from a miscount in the self-check itself (it expected 12 length readings per unit log; there are 11). The script was fixed and rerun; no reading changed.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | unit: P lines in `unit-<P>.log`; cluster: jinfo lines, misses = 64 from `info-before/after.txt`, SSTable 0 both times (`selfcheck.txt`) |
| 2. Readings | yes | heapDelta values re-read from the unit logs; constant residual 58,696 B recomputed (`selfcheck.txt`: "same constant at both high P"); ΔH from the full histograms |
| 3. Matched row | yes | unit: 11 lengths per P all ≤ P, requests > P capped at exactly P, 16 MiB control reached; cluster: 0 temp-buffer events in all four JSON files, `HeapCloner` 4 MiB events present only on the offheap runs |
| 4. Excluded rows | yes | each excluded row re-checked against the same files (no len > P; lengths differ across P; no temp-buffer event; ΔH < 16 MiB everywhere) |
| 5. Observed vs. inferred | yes | the G1-rounding inference is checked by the region size (`g1-flags.txt`) and the identical residual; the cluster inference (8 MiB always outside a TLAB) is backed by the observed flat ΔH |
| 6. Deviations and gaps | yes | D1 (restart done), D2 (no restart, reason given), the JFR blind spot for in-TLAB allocations, and the unit heap-magnitude miss are all recorded |
| 7. Core question | yes | unit: capped and follows P (observed lengths); cluster: path not exercised, so no answer; class follows the weak rule |

### 5.2 Run 2?

**No** — 2026-11-12. The unit conclusion rests on observed lengths; its one inference was checked in §5.1. The cluster result is "not confirmed (path not exercised)", which the source audit predicted and JFR shows directly. Neither tier refutes the case or confirms a bypass. The coordinator's instructions also excluded a run 2.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** **weak true positive**. The unit tier is Confirmed — caps; the cluster tier could not settle the effect (Not confirmed, path not exercised), so the class comes from the unit tier alone (rule of 2026-10-29). The cluster tier does not contradict the unit effect.

**Claim tested (B1):** for every thread, the length of the `DataOutputStreamPlus` temporary buffer (and so the heap it retains) is at most `cassandra.data_output_stream_plus_temp_buffer_size`; for a request `r ≥ 16` it equals `min(P, 2*highestOneBit(r))` once grown, so retained heap follows the property up to the rounded request size.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (all lengths as B2f, `len ≤ P`). Heap observable: follows P, but the B2f magnitude was missed at P ≥ 1 MiB because of G1 humongous region rounding (inspected under the "≫" row) | caps | run 1 + self-check | 2026-11-12 |
| Cluster | **Not confirmed** — B3g "No `retrieveTemporaryBuffer` allocations at any P, 64 row-cache misses seen" (path not exercised: `offheap_buffers` memtable reads are cloned to heap by `EnsureOnHeap.CloneToHeap`) | undetermined | run 1 + self-check | 2026-11-12 |

**Positive control:** unit: P = 16 MiB grew the same request sequence to 16 MiB (`run1/unit-16777216.log`). Cluster: the P = 16 MiB offheap run was meant to move heap by T × 8 MiB, but did not move (ΔH 0.30 MiB), because the path was not reached.

**Feedback filed:** case file section D (2026-11-12, run 1); amendments A1-A3 and the audit note A4 (before the freeze) and A5 (D1, during run 1) are in the case file next to the text they change. Nothing committed (the coordinator commits). For `_INDEX.md` §4 (not edited here), the case file's final sha256 is `18d2a8196d0551bd503346b98e5258b145c69576b9b11c2d1076416be4562c51`.

**What stays on the node:** `/mydata/jingsong-cass-s4/o43/` (about 0.7 GB): `src/` (built copy, conf edited, `.orig` kept), `probe/`, `probe-out/`, `freeze/`, `jfrcheck/` (class and JSON, no `.jfr`), `run1/` (unit logs, per-run session logs, full histograms, `system.log` copies, `jfr-<label>.json` about 220 MB in total), `node/logs/`, `build.log`, `copy.log`. Node data, commit logs and `.jfr` files were deleted (B4). No process of this run is left running: no `CassandraDaemon`, `TempBufferProbe` or run script under `o43`, and ports 7300/7301/7499/9342/9391 are free (checked 2026-11-12T03:38Z).
