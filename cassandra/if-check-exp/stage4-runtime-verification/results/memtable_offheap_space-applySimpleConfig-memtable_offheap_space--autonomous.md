# memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous — stage-4 results  <!-- file: results/memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous.md -->

> **Case:** [`memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous`](../../stage3-ai-deep-read/cases/memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous.md)
>
> **Status:** verdict filed, 2026-10-24. **Unit: Confirmed — caps. Cluster: Confirmed — caps.**
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous/`](../harness/memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous/).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-24, on the advisor's machine (`environment-advisor.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `f361777` (sha256 `1b5fcef4…a145`). Frozen after the step-0 audit's nine amendments (2026-10-24): sha256 **`a5fc8f86344642e3a06ba2f145a731e9ce97e563bd91d0bd39ed5d5154cff808`**, a new row in `_INDEX-advisor.md` §2. The amendments are not committed (no commit was asked for). No runbook fix was needed; both tiers ran at this version. |
| **Harness** | [`../harness/memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous/`](../harness/memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous/): `MemtableOffHeapCapTest.java`, `unit-run.sh` (unit); `Sampler.java`, `cluster-run.sh`, `cluster-chain.sh`, `summarize.py` (cluster). Not committed. Checks before run 1: the test class compiled in the run clone (`ant build-test`, `BUILD SUCCESSFUL`, log `$W/logs/memtable_offheap_space-applySimpleConfig/instrument-compile.log`); a probe JVM holding 200 MiB of `com.sun.jna.Native.malloc` showed NMT `Other` 2 KB and RSS ≈ 247 MiB (the reason for the B3d amendment; `vmmap`/`footprint` need root and could not attach); `Sampler.java` compiled by `javac` at the start of each cluster run; each run cross-checks the sampler's `BlockedOnAllocation` against one `nodetool sjk mx` read at the end (equal in all five runs that reached stress, §5). |
| **Tiers and values** | Unit (B2): `offheap_buffers` and `offheap_objects` at off-heap limits 0, 1, 8 MiB (on-heap 64 MiB); controls `Long.MAX_VALUE` (both types) and `heap_buffers` at 1 MiB. Cluster (B3): (a) `offheap_objects` with `memtable_offheap_space` 64 MiB, 256 MiB, unset (512 MiB at a 2 GiB heap); (b) `offheap_buffers` 0 MiB; (c) `offheap_objects` 0 MiB; B3h control `heap_buffers` with 64 MiB. `memtable_heap_space: 512MiB` throughout. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-24. |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: off-heap memtable bytes (`MEMORY_POOL.offHeap.allocated` vs `limit`). |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly → Met after amendment | B2b 0/1/8 MiB (no default, acceptable for a pool-level test); B3b (a) had 64 and 256 MiB only — the default (unset) added (amendment B3b). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Partly after amendment | B3d's real-resource reading was NMT, which cannot see `offheap_objects` memory (JNA `malloc`, `MemoryUtil.java:81-84`); replaced by daemon RSS (amendment B3d). RSS on macOS still mixes in heap pages and mapped files (§4.2 part 6). Unit tier reads the counter only. |
| A. Core question | usage driven to the limit and past it | Met | B2c offers 32 MiB against 1/8 MiB; B3c ≈ 3 GB against at most 512 MiB. |
| B. Logic | each step says what it establishes | Partly | Implied by B2g/B3g rather than stated per step. Left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | B2f exact; B3f "≈ knob plus other consumers" and "≈ 192 MiB" undefined — given a definition and tolerance (amendment B3f). |
| B. Logic | every plausible outcome has a conclusions row | Not met → Met after amendment | B2g and B3g lacked "limit never reached / invalid", "counter capped but real resource grows", "not ordered", partial stall, stall from another cause, control failure; added (amendments B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after amendment | Unit: writer `WAITING` is direct (made explicit, B2g). Cluster row 1 required peaks and order only; the amendment requires a `MEMTABLE_LIMIT` flush led by the off-heap ratio or `BlockedOnAllocation` > 0 in every (a) run; (c) requires a thread waiting in `SubAllocator.allocate`. |
| B. Logic | alternative explanations and their controls | Met | B2h (no limit; `heap_buffers`), B3h (`heap_buffers` control, flush reason). The thread dump (amendment B3d) rules out a stall from another cause in (c). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, B1 and the tables read on their own. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Initialisation order (B2a), the meaning of "32 MiB worth" and writer stop (B2e), control sizes (B2h), stall stop conditions (B3e) were open. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | 1 s cadence not achievable with `nodetool` (sampler, B3d); "persistently" and "normally" undefined (B3g); no bound for stress or drain on a stalled node (B3e). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | B2a/B3a list clone, build, test class; mapped to this machine (§2). |
| D. Runnable | workload arithmetic reaches the limit | Met | 3,000,000 × 5 × 200 B ≈ 3 GB per run, ≈ 50 s at ≈ 60k op/s here; 3.0–3.1 GB data per run on 160 GiB free; 2 GiB heap on 32 GiB RAM. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Partly | `DatabaseDescriptor.java:583-594`, `AbstractAllocatorMemtable.java:59,78-110`, `MemtablePool.java:60,125-161`, `MemtableAllocator.java:169-196`, `SlabPool.java:28`, `SlabAllocator.java:89-94`, `NativeAllocator.java:138-141` match. Two errors: B3d's "where `Unsafe.allocateMemory` … appear" — `NativeAllocator` uses `MemoryUtil.allocate` → JNA `Native.malloc`, invisible to NMT; and the off-heap gauge counts only current memtables (`TableMetrics.java:515-521`). Both corrected (amendment B3d). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: call `DatabaseDescriptor.daemonInitialization()` before touching `AbstractAllocatorMemtable` | Amendment 2026-10-24 (uncommitted) | Its class initialiser builds `MEMORY_POOL` from the config. |
| 2 | B2e: 32,768 calls; stop rule; readings at 2 s; "≈0" is exactly 0 | Amendment 2026-10-24 | B2e left these open. |
| 3 | B2g: rows for invalid scenario, fallback failure, on-heap charge, control failure; row 1 needs `WAITING` | Amendment 2026-10-24 | Audit group B. |
| 4 | B2h: sizes and exact expected outcomes of the controls | Amendment 2026-10-24 | Not given. |
| 5 | B3b: add the default (unset) to (a) | Amendment 2026-10-24 | Group A needs ≥ 3 values incl. the default. |
| 6 | B3d: gauge scope; `Used total` off-heap ratio; 1 s JMX sampler with `WriteLatency`; NMT → RSS; thread dump for (c) | Amendment 2026-10-24 | Two citation errors; `nodetool` cadence; no stall observable. |
| 7 | B3e: startup definition; (c) bounds (120 s, stress 180 s, drain 60 s, kill -9) | Amendment 2026-10-24 | A stalled node does not drain. |
| 8 | B3f: prediction for the default; RSS reading with tolerance; "≈ 192 MiB" = 96–288 MiB | Amendment 2026-10-24 | Undefined relations. |
| 9 | B3g: define "persistently", "normally"; direct-evidence requirement; eleven rows | Amendment 2026-10-24 | Audit group B. |
| 10 | Measure native memory with a tool that sees `malloc` without macOS page compression effects (e.g. a Linux node's `/proc/<pid>/smaps` anon or jemalloc stats) | Left for stage 3 / a Linux run | Not available on this machine without root. |
| 11 | B3a: `HEAP_NEWSIZE` has no effect under G1 (the node's default GC) | Left for stage 3 | Harmless. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-24 (unit 16:16 EDT; cluster 16:17–16:30 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64; 10 cores, 32 GiB RAM; internal SSD (APFS), 160 GiB free at start; loopback 127.0.0.1–.3 present (one node used, 127.0.0.1) |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit JVM: junit fork `-Xmx1024m` with the build's JDK 11 test flags. Node: G1, `-Xms2G -Xmx2G` (`MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`), `-XX:+AlwaysPreTouch`, `-XX:NativeMemoryTracking=summary` added to the node's copy of `jvm-server.options` |
| Ant | 1.10.18 |
| Local `cassandra-src` clone commit | `$W/cassandra-run3` = `~/Library/Caches/stage4/cassandra-run3`, `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), built with `ant -Dlocal.repository=$W/m2 build-test` (49 s) |
| Case-file commit / harness commit | filed `f361777`; amendments and harness uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-mos/{data,commitlog,hints,saved_caches,cdc_raw,logs}`, wiped before and after each run; `concurrent_compactors: 1`; ports 7000/7199/9042/9091 free before and after; no `CassandraDaemon` before or after |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/memtable_offheap_space-applySimpleConfig/` — `clone.log`, `build-test-run3.log`, `instrument-compile.log`, `unit/` (ant log, JUnit XML, `stage4.out`), `cluster/{a-k64,a-k256,a-kunset,b-buffers0,c-objects0,ctl-heap64}/` (`system.log`, `gc.log*`, `stress.log`, `samples.csv`, `rss.csv`, `nmt.txt`, `flush-lines.txt`, `threaddump.txt` for (c), `node.out`, `commands.log`, `summary.txt`), `cluster/chain.out`, `selfcheck.out` |

## 3. Runbook defects

None. Both tiers ran as amended at the frozen version.

## 4. Run 1

**Scope:** both tiers, all values in §1. **Command log:** `memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous/run1/unit/{commands.log,summary.txt,stage4.out}`, `run1/cluster/<run>/{commands.log,summary.txt,samples.csv,rss.csv,nmt.txt,markers.txt,flush-lines-excerpt.txt,stress-results.txt,startup-threshold.txt,yaml-overrides.txt,sjk-*.txt}`; for (c) `run1/cluster/c-objects0/{commands.log,summary.txt,startup.txt,startup-threshold.txt,threaddump-main.txt,system-tail.txt}`.

### 4.1 Readings

**Unit tier** (all from `run1/unit/stage4.out`; JUnit `Tests run: 2, Failures: 0, Errors: 0`, `run1/unit/summary.txt`)

| Scenario (type / off-heap limit) | Calls at 2 s | `offHeap.used` | `onHeap.used` | Writer | Evidence |
|---|---|---|---|---|---|
| `offheap_buffers` / 1 MiB | 1,024 | 1,048,576 (max seen = same) | 0 | `WAITING` | `stage4.out` |
| `offheap_buffers` / 8 MiB | 8,192 | 8,388,608 | 0 | `WAITING` | same |
| `offheap_objects` / 1 MiB | 1,024 | 1,048,576 | 0 | `WAITING` | same |
| `offheap_objects` / 8 MiB | 8,192 | 8,388,608 | 0 | `WAITING` | same |
| `offheap_buffers` / 0 | 32,768 (all) | 0 | 33,554,432 (32 MiB) | `TERMINATED` (finished) | same |
| `offheap_objects` / 0 | **0** | 0 | 0 | **`WAITING` at the first call** | same |
| control `Long.MAX_VALUE`, `offheap_buffers` | 32,768 | 33,554,432 | 0 | `TERMINATED` | same |
| control `Long.MAX_VALUE`, `offheap_objects` | 32,768 | 33,554,432 | 0 | `TERMINATED` | same |
| control `heap_buffers`, off-heap 1 MiB | 32,768 | 0 (limit 0 in the pool) | 33,554,432 | `TERMINATED` | same |

Every blocked writer ended `stopped:UncheckedInterruptedException` on interrupt (the wait at `MemtableAllocator.java:195`).

**Cluster tier** (runs that reached stress: `cassandra-stress write n=3000000`, 3,000,000 partitions, 0 errors, 48–51 s operation time, 58.6–62.5k op/s)

| Capacity value | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| 64 MiB | (a) | startup line | `Global memtable off-heap threshold is enabled at 64MiB` (`:594`); on-heap 512MiB | `cluster/a-k64/startup-threshold.txt` |
| 64 MiB | (a) | `AllMemtablesOffHeapDataSize` peak / median (78 samples at 1 s) | **21.23 MiB** / 10.51 MiB; 0 samples over 1.05 × knob | `cluster/a-k64/samples.csv`, `summary.txt` |
| 64 MiB | (a) | `Flushing largest` lines; `Enqueuing flush` reasons | 152, all led by the off-heap ratio; `MEMTABLE_LIMIT` 152 (all `keyspace1`), `INTERNALLY_FORCED` 9 | `cluster/a-k64/flush-lines-excerpt.txt`, `summary.txt` |
| 64 MiB | (a) | `Used total` off-heap ratio (on-heap max) | max 0.67 (42.9 MiB), median 0.67 (on-heap ≤ 0.04) | same |
| 64 MiB | (a) | `BlockedOnAllocation` at end | **1,260** (sampler = `nodetool sjk`) | `cluster/a-k64/sjk-blocked-end.txt` |
| 64 MiB | (a) | RSS pre-stress → peak; growth | 2,361.7 → 2,431.0 MiB; **69.2 MiB**; then fell to ≈ 1,700 MiB from 8 s into stress to the end | `cluster/a-k64/rss.csv`, `summary.txt` |
| 256 MiB | (a) | startup line | `… enabled at 256MiB` | `cluster/a-k256/startup-threshold.txt` |
| 256 MiB | (a) | gauge peak / median (74 samples) | **82.83 MiB** / 20.29 MiB; 0 over 1.05 × knob | `cluster/a-k256/samples.csv` |
| 256 MiB | (a) | flush lines; reasons | 38, all led by off-heap; `MEMTABLE_LIMIT` 38 | `cluster/a-k256/summary.txt` |
| 256 MiB | (a) | `Used total` off-heap | max 0.67 (171.5 MiB), median 0.33 | same |
| 256 MiB | (a) | `BlockedOnAllocation` | **0** | `cluster/a-k256/sjk-blocked-end.txt` |
| 256 MiB | (a) | RSS growth | 2,371.6 → 2,701.6 MiB; **330.0 MiB** | `cluster/a-k256/rss.csv` |
| unset (512 MiB) | (a) | startup line | `… enabled at 512MiB` | `cluster/a-kunset/startup-threshold.txt` |
| unset (512 MiB) | (a) | gauge peak / median (75 samples) | **160.60 MiB** / 36.93 MiB; 0 over 1.05 × knob | `cluster/a-kunset/samples.csv` |
| unset (512 MiB) | (a) | flush lines; reasons | 19, all led by off-heap; `MEMTABLE_LIMIT` 19 | `cluster/a-kunset/summary.txt` |
| unset (512 MiB) | (a) | `Used total` off-heap | max 0.33 (169.0 MiB) | same |
| unset (512 MiB) | (a) | `BlockedOnAllocation` | **0** | `cluster/a-kunset/sjk-blocked-end.txt` |
| unset (512 MiB) | (a) | RSS growth | 2,371.1 → 2,815.8 MiB; **444.7 MiB** | `cluster/a-kunset/rss.csv` |
| all (a), (b), control | — | NMT `Other` committed first → max | 56.7 → 385.1–385.2 MiB in every run (same in (b) and the control) | `cluster/*/nmt.txt` |
| 0 MiB, `offheap_buffers` | (b) | startup line | `Global memtable off-heap threshold is disabled, HeapAllocator will be used instead` (`:592`) | `cluster/b-buffers0/startup-threshold.txt` |
| 0 MiB, `offheap_buffers` | (b) | off-heap / on-heap gauge peaks | **0** throughout / **166.62 MiB** (median 96.45) | `cluster/b-buffers0/samples.csv` |
| 0 MiB, `offheap_buffers` | (b) | flushes; `Used total` | 31 `MEMTABLE_LIMIT`, all led by on-heap; off-heap ratio 0.00, on-heap max 0.33 | `cluster/b-buffers0/summary.txt` |
| 0 MiB, `offheap_objects` | (c) | startup line | line `:592` "disabled, HeapAllocator will be used instead" | `cluster/c-objects0/startup-threshold.txt` |
| 0 MiB, `offheap_objects` | (c) | startup | **not complete at 120 s**; JMX never listened (`nodetool` connection refused); the last log line is at 20:26:22 (≈ 1 s after launch) | `cluster/c-objects0/startup.txt`, `system-tail.txt`, `summary.txt` |
| 0 MiB, `offheap_objects` | (c) | thread dump at 121 s | 51 threads; **1 in `MemtableAllocator$SubAllocator.allocate`**: `main`, `WAITING (parking)` at `MemtableAllocator.java:195` ← `NativeAllocator.allocate:141` ← `NativeDecoratedKey.<init>` ← `SkipListMemtable.estimateRowOverhead:228` ← `SkipListMemtable.<clinit>:79` ← `MemtableParams` ← `SchemaKeyspace.<clinit>` ← `Schema.<clinit>` ← `StartupChecks.java:722` | `cluster/c-objects0/threaddump-main.txt` |
| 0 MiB, `offheap_objects` | (c) | stress | not run (B3e amended: startup not complete); node killed with `kill -9` | `cluster/c-objects0/commands.log` |
| 64 MiB, `heap_buffers` | control | off-heap / on-heap gauge peaks | **0** / 161.92 MiB | `cluster/ctl-heap64/samples.csv` |
| 64 MiB, `heap_buffers` | control | flushes; RSS growth | 31 `MEMTABLE_LIMIT` (on-heap ratio max 0.67); **121.8 MiB** | `cluster/ctl-heap64/summary.txt`, `rss.csv` |

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — one JVM, 2 tests, no failures [observed: `run1/unit/summary.txt`]; each nonzero limit was reached (calls = limit/1024, `offHeap.used` = limit) [observed: `stage4.out`]. Valid.
2. **Readings** — nothing unusual; every number is exact.
3. **Matched row** — B2g row 1, "table above matches — mechanism as traced": both off-heap types stop at exactly 1 and 8 MiB with the writer `WAITING` and nothing charged on-heap; `offheap_buffers`/0 puts all 32 MiB on the heap pool and completes; `offheap_objects`/0 blocks at the first call with nothing charged anywhere [observed: `stage4.out`].
4. **Excluded rows** — row 2 (over a nonzero limit): max `offHeap.used` equals the limit [observed]. Row 3 (`offheap_objects`/0 completes): 0 calls [observed]. Row 4 (`offheap_buffers`/0 charges off-heap): `offHeap.used` 0 [observed]. Added rows: fallback blocks early — no, all 32,768 calls [observed]; invalid scenario — every nonzero scenario `WAITING` [observed]; on-heap charge by an off-heap type — 0 [observed]; controls — both `Long.MAX_VALUE` scenarios finished 32 MiB, `heap_buffers` charged 0 off-heap and 32 MiB on-heap [observed].
5. **Observed vs. inferred** — none load-bearing.
6. **Deviations and gaps** — only the pool counter is read, not the regions behind it (malloc'd or direct).
7. **Core question** — the off-heap pool limit built from the knob stops writers at exactly the limit for both off-heap types, scaling 1:8 with it; at 0 the two types differ: `offheap_buffers` moves to the heap pool, `offheap_objects` admits nothing.

**Conclusion (unit tier):** B2g row 1 — **confirmed**.

**Cluster tier**

1. **Validity** — the five runs that reached stress wrote 3,000,000 partitions with 0 errors [observed: `stress-results.txt`]; each startup line shows the intended knob (64, 256, 512 MiB; the disabled message in (b) and (c)) and on-heap 512 MiB [observed: `startup-threshold.txt`]; types and directories as set [observed: `yaml-overrides.txt`]. Run (c) is valid for its own question (startup is the observable, B3e). Valid.
2. **Readings** — the gauge peaks sit at 0.33, 0.32 and 0.31 × knob, and the pool's own `Used total` never exceeded 0.67: [inferred: the cleaner triggers a flush at `limit × memtable_cleanup_threshold` = 1/3 by default (`conf/cassandra.yaml:811`, two flush writers), and the gauge omits flushing memtables (amendment B3d)]. At 256 and 512 MiB no writer blocked; the limit acted through limit-derived cleaner flushes only [observed: `sjk-blocked-end.txt` 0, `MEMTABLE_LIMIT` 38/19]. RSS growth at 64 MiB (69.2 MiB) was below the control's (121.8 MiB) [observed: `rss.csv`]. In (c) the stall came earlier than B3f's parenthetical says: not at a system-table write, but in `SkipListMemtable`'s class initialiser, which clones a test key through a `MEMORY_POOL` allocator to estimate row overhead (`SkipListMemtable.java:79`, `:215-228`), reached from the startup checks' schema load about 1 s after launch [observed: `threaddump-main.txt`, `system-tail.txt`].
3. **Matched rows** — (a): B3g row 1, "peaks ≤ knob and ordered — claim confirmed": 21.23 < 82.83 < 160.60 MiB for 64 < 256 < 512 MiB, each ≤ 1.05 × knob [observed: `samples.csv`], and in every run the amended requirement holds — `MEMTABLE_LIMIT` flushes of `keyspace1.standard1` led by the off-heap ratio (152 / 38 / 19), plus 1,260 blocked allocations at 64 MiB [observed: `flush-lines-excerpt.txt`, `sjk-blocked-end.txt`]. (c): the amended row "startup not complete in 120 s … and the thread dump shows ≥ 1 thread in `MemtableAllocator$SubAllocator.allocate` — stall confirmed at the allocator (the line-592 message is inaccurate for `offheap_objects`)": startup not complete, `main` waiting at `MemtableAllocator.java:195` from `NativeAllocator.allocate` [observed: `startup.txt`, `threaddump-main.txt`], with line 592 logged [observed: `startup-threshold.txt`]. (b): B3f(b) held — off-heap gauge 0 throughout, on-heap gauge to 166.62 MiB ≤ 512 MiB, line 592 present [observed: `b-buffers0/samples.csv`, `startup-threshold.txt`]; no refuting row fires.
4. **Excluded rows** — row 2 and the "`Used total` > 1.05" row: no sample over 1.05 × knob; off-heap `Used total` max 0.67 / 0.67 / 0.33 [observed]. "Not ordered": strictly ordered [observed]. "Off-heap limit not reached in a run": every (a) run has off-heap-led `MEMTABLE_LIMIT` flushes [observed]. "Counter capped but real resource grows": RSS growth − control = −52.5 / 208.2 / 323.0 MiB against bounds 131.2 / 332.8 / 601.6 MiB [observed: `rss.csv` of each run and the control]. "Stress errors / fewer partitions": none [observed]. Row 3 ((b) off-heap gauge > 0): 0 [observed]; "(b) on-heap gauge < 1 MiB": 166.62 MiB [observed]; "line 594 instead of 592" in (b)/(c): 592 in both [observed]. Row 4 ((c) writes proceed normally), "stall from another cause" and "partial stall": startup never completed and the one blocked thread is in the allocator [observed]. Control row: off-heap gauge 0, on-heap gauge to 161.92 MiB [observed].
5. **Observed vs. inferred** — the knob/3 explanation of the peak level (part 2) is inferred; the matches use observed values only. That the (c) stall is total (no other path would ever wake `main`) is inferred from the source (`MemtablePool.java:125-129`: `needsCleaning` is `0 > 0` false, so no cleaner runs and nothing calls `released`) together with the 120 s observation; the row needs only the observation.
6. **Deviations and gaps** — (i) RSS is a weak real-resource reading on macOS: before stress it was ≈ 2.36–2.37 GiB in every run, but in run (a) 64 MiB it fell from 2,430 MiB to ≈ 1,700 MiB 8 s into stress and stayed there to the end — below the pre-touched 2 GiB heap [observed: `a-k64/rss.csv`]. [inferred: macOS compressed or reclaimed resident pages of the process during the run], so RSS moves for reasons other than native allocation, in either direction, and the subtraction of the control cannot isolate memtable native memory (the growth at 64 MiB was taken at the peak before the drop, 69.2 MiB, and is below the control's). The row it feeds did not fire; nothing else rests on it. (ii) NMT `Other` grew 56.7 → 385 MiB identically in every run including (b) and the control [observed: `nmt.txt`], i.e. non-memtable direct memory, consistent with NMT not seeing `Native.malloc` (§1). (iii) B3f's "≈ 192 MiB" sub-prediction, read as RSS growth(256) − growth(64): 260.7 MiB, inside 96–288 MiB (held, with gap (i)). (iv) In (c) no stress ran, as B3e amended allows; the cause in B3f's parenthetical ("system-table writes block") is not what was observed (part 2). (v) At 256 and 512 MiB writers never reached the hard cap; the limit acted through the cleaner threshold derived from it.
7. **Core question** — off-heap memtable accounting followed the knob (peaks ordered 1 : 3.9 : 7.6 for 1 : 4 : 8), stayed ≤ knob in every sample, and the off-heap limit drove every limit flush in every (a) run, with writers blocked at 64 MiB. At 0 the knob does not mean "disabled" uniformly: `offheap_buffers` falls back to the heap pool as the log says, while `offheap_objects` gets a 0-byte limit and the node hangs in startup. The constraint caps off-heap memtable usage for the off-heap types.

**Conclusion (cluster tier):** B3g row 1 for (a) and the amended (c) stall row — **confirmed**; (b) as predicted.

## 5. Self-check of run 1 — AI

Script: [`run1/selfcheck.py`](memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous/run1/selfcheck.py), run as `python3 -I selfcheck.py ~/Library/Caches/stage4/logs/memtable_offheap_space-applySimpleConfig`. It re-reads the raw `stage4.out`, JUnit XML, `system.log` (full, not the flush excerpt), `samples.csv`, `rss.csv`, `markers.txt`, `stress.log`, `sjk` files, `startup.txt` and `threaddump.txt` (not the harness summaries) and recomputes each number. Output: [`run1/selfcheck.out`](memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous/run1/selfcheck.out) — 67 checks, **0 do not hold**.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | JUnit XML `tests="2" failures="0" errors="0"`; stress `Total partitions 3,000,000`, `Total errors 0` in all five stress runs; knobs 64/256/512 MiB and on-heap 512 MiB read from each `system.log`; no `java.lang.OutOfMemoryError`. |
| 2. Readings | yes | Peaks / knob recomputed from `samples.csv`; `Used total` ratios re-parsed from the full `system.log`; the (c) stack re-read from `threaddump.txt` (the one thread in `SubAllocator.allocate` is `main`). |
| 3. Matched row | yes | Unit: each scenario's calls, `offHeap.used`, `onHeap.used`, state against B2f. Cluster: peaks ≤ 1.05 × knob, ordered; off-heap-led `MEMTABLE_LIMIT` flushes in every (a) run; (c) startup not complete and ≥ 1 thread in the allocator; (b) off-heap 0, on-heap 166.62 MiB, line 592. |
| 4. Excluded rows | yes | No 3 consecutive samples over 1.05 × knob; off-heap `Used total` ≤ 0.67; RSS differences within bounds; control off-heap 0. |
| 5. Observed vs. inferred | yes | The two inferred statements (knob/3 level; the stall is permanent) are named and not needed by the matched rows. |
| 6. Deviations and gaps | yes (corrected) | On re-reading `a-k64/rss.csv` the first draft's description of the RSS gap was wrong (it said the 1.7 GiB reading was before stress; it is during stress, after a drop from 2.43 GiB); corrected in §4.2 part 6 and §4.1. The RSS row's outcome is unchanged. Sampler `BlockedOnAllocation` equals the `nodetool sjk` end read in all five stress runs (1,260 / 0 / 0 / 0 / 0). The RSS gap is stated; the RSS row is checked but carries no weight in the matched rows. |
| 7. Core question | yes | Uses only parts 1–4. |

### 5.2 Run 2?

**No** — 2026-10-24. Every self-check part holds; the result neither refutes the file nor confirms a bypass, and the matched rows rest on observed readings (the (c) stall on a thread dump that names the waiting frame).

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested (B1):** with `offheap_objects` (and `offheap_buffers`), off-heap memtable accounting (`AllMemtablesOffHeapDataSize`, global) stays ≤ `memtable_offheap_space` (plus in-flight overshoot) and its peak scales with the knob; with value 0, `offheap_buffers` puts all memtable data on heap, and `offheap_objects` stalls writes.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1 — **Confirmed** (both off-heap types stop the writer at exactly 1 / 8 MiB; at 0 `offheap_buffers` moves to the heap pool, `offheap_objects` blocks at the first call) | caps | run 1 + self-check | 2026-10-24 |
| Cluster | B3g row 1 and the amended (c) row — **Confirmed** (peaks 21.2 / 82.8 / 160.6 MiB for 64 / 256 / 512 MiB, all ≤ knob, off-heap-led limit flushes in every run, 1,260 blocked allocations at 64 MiB; `offheap_buffers`/0 all on heap; `offheap_objects`/0 hangs startup in `SubAllocator.allocate` although line 592 says the heap allocator will be used) | caps | run 1 + self-check | 2026-10-24 |

**Feedback filed:** the case file's section D (uncommitted); the nine amendments of 2026-10-24 in the case file; `_INDEX-advisor.md` §1 Stage 4 column, §2 a new sha256 row, §3 coverage line. Notes for stage 3, not applied: the (c) stall happens before any system-table write, in `SkipListMemtable`'s class initialiser (`SkipListMemtable.java:79`, `:215-228`) during the startup checks, so a `0MiB` value with `offheap_objects` makes the node hang about 1 s after launch with no error and no JMX; `NativeAllocator` memory comes from JNA `malloc` and is invisible to NMT; peaks sit near knob/3 (cleanup threshold); at 256 and 512 MiB no writer blocked.
