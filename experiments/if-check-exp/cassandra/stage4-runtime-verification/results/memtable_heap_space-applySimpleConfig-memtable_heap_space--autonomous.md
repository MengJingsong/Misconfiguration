# memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous — stage-4 results  <!-- file: results/memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous.md -->

> **Case:** [`memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous`](../../stage3-ai-deep-read/cases/memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous.md)
>
> **Status:** verdict filed, 2026-10-24. **Unit: Confirmed — caps. Cluster: Confirmed — caps.**
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous/`](../harness/memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous/).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-24, on the advisor's machine (`environment-advisor.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `f361777` (sha256 `f290cb89…0128`). Frozen after the step-0 audit's five amendments (2026-10-24): sha256 **`518d69ead80aa676b95c67bd0b59eb56c6caea4801f102d49d384fdd49562fd9`**. A runbook fix during cluster run 1 (§3, defect 1) changed B3d only; the cluster tier restarted at sha256 **`02ff5a098dcd0a3ea0983950a01cec4a4303466c06980459a6efae324c6ac0e8`**. Both are new rows in `_INDEX.md` §4; the amendments are not committed (no commit was asked for). The unit tier ran at the first frozen version; the fix did not touch B2. |
| **Harness** | [`../harness/memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous/`](../harness/memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous/): `MemtableHeapCapTest.java`, `MemtableHeapSpaceZeroTest.java`, `MemtableHeapSpaceDefaultTest.java`, `unit-run.sh` (unit); `Sampler.java`, `cluster-run.sh`, `cluster-chain.sh`, `summarize.py` (cluster). Not committed. Check before run 1: the three test classes compiled in the run clone (`ant build-test`, `BUILD SUCCESSFUL`, log `$W/logs/memtable_heap_space-applySimpleConfig/instrument-compile.log`); `Sampler.java` compiled by `javac` at the start of each cluster run; each cluster run cross-checks the sampler against one `nodetool sjk mx` read at the end (equal in all four runs, §5). |
| **Tiers and values** | Unit (B2): pool limits 1, 4, 16 MiB; controls `Long.MAX_VALUE` and a blocking op group at 1 MiB; startup validation with `0MiB` and unset at `-Xmx1024m`. Cluster (B3): `memtable_heap_space` 64 MiB, 256 MiB, unset (512 MiB at a 2 GiB heap), and the B3h control (`offheap_objects`, heap and off-heap 64 MiB). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-24. |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: on-heap memtable bytes (`SubPool.allocated` vs `limit`). |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b 1/4/16 MiB plus unset (default) at startup; B3b 64/256 MiB and unset. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | Unit tier reads the pool counter only (the slab regions behind it are not measured). Cluster: the gauge is a counter; B3d adds `jstat` old-gen (real heap). Gap not named in the file. Left for stage 3. |
| A. Core question | usage driven to the limit and past it | Met | B2c offers 4 × limit; B3c offers ≈ 3 GB against at most 512 MiB. |
| B. Logic | each step says what it establishes | Partly | B2e/B3e list steps; what each establishes is implied by B2g/B3g. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f exact (≤ limit, ≈ limit/1024 calls, 256 MiB); B3f ≤ knob × 1.05, ordered. |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | B3g lacked "counter capped but real resource grows", "limit never reached/run invalid" and a pool-over-limit row; added (amendment B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after amendment | B3g row 1 required only ceiling and order; the amendment requires a `MEMTABLE_LIMIT` flush or `BlockedOnAllocation` > 0 in every run. Unit: writer `WAITING` is direct. |
| B. Logic | alternative explanations and their controls | Met | B2h (no-limit, blocking group), B3h (unset reference, flush reason, off-heap control). |
| C. Specific | a human can follow it from the intro and §9a | Met | B1 and the tables read on their own. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Release path, config source and once-per-JVM initialisation were open (amendments B2a, B2e); the blocking control lacked `markBlocking()` (B2h). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | "Sustained" undefined (defined in B3g amendment); sampler cadence not achievable with `nodetool` (B3d amendment). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | B2a/B3a list clone, build and the test class; mapped to this machine (§2). `cassandra-stress` is built by `build-test` (`build.xml:1017`). |
| D. Runnable | workload arithmetic reaches the limit | Met | 3,000,000 × 5 × 200 B ≈ 3 GB per run, ≈ 1 min at ≈ 58k op/s here; 3.0–3.1 GB data per run on 162 GiB free; 2 GiB node heap on 32 GiB RAM. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Partly | `DatabaseDescriptor.java:586-590`, `AbstractAllocatorMemtable.java:59,78-110,249-297`, `MemtablePool.java:59,151-161,192-197`, `MemtableAllocator.java:169-196`, `SlabAllocator.java:89-95` match. **B3d's parenthetical is wrong**: `AllMemtablesOnHeapDataSize` sums only the current memtable of each table (`TableMetrics.java:506-512, 876-882`), not memtables being flushed (amendment B3d). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: three test classes, one JVM each; call `daemonInitialization()` before touching `AbstractAllocatorMemtable` | Amendment 2026-10-24 (uncommitted) | `daemonInitialization` returns silently on a second call (`DatabaseDescriptor.java:257-260`); `MEMORY_POOL` is built in the class initialiser. |
| 2 | B2e: release via `pool.onHeap.released(limit/2)`; zero case from `loadConfig()` + one field; default under the fork's `maxmemory=1024m` | Amendment 2026-10-24 | B2e left alternatives open. |
| 3 | B2h: `issue()` + `markBlocking()`; sizes and expected outcomes for both controls | Amendment 2026-10-24 | `issue()` alone leaves `isBlocking` false (`OpOrder.java:319-335, 407`). |
| 4 | B3d: correct the gauge's scope; add `Used total` from `Flushing largest` lines (the pool's own `allocated/limit`); sample over one JMX connection every 1 s; cross-check with `nodetool sjk` | Amendment 2026-10-24 | Citation error; B1 names `MEMORY_POOL.onHeap.used()`, which no MBean exposes. |
| 5 | B3g: define "sustained"; require direct evidence that the limit acted; add four rows | Amendment 2026-10-24 | Audit group B. |
| 6 | Unit tier: measure the slab regions (real heap) behind the counter | Left for stage 3 | Not needed for a valid run; the gap is noted in §4.2 part 6. |
| 7 | B3a: `HEAP_NEWSIZE` has no effect under G1 (the node's default GC) | Left for stage 3 | Harmless; recorded in §2. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-24 (unit 15:47–15:48 EDT; cluster attempt 1 15:49–15:51; cluster run 1 15:52–16:01) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64; 10 cores, 32 GiB RAM; internal SSD (APFS), 162 GiB free at start |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit JVMs: junit fork `-Xmx1024m` with the build's JDK 11 test flags (CMS, `build.xml:233`). Node: G1, `-Xms2G -Xmx2G` (`MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`; G1 ignores `HEAP_NEWSIZE`) |
| Ant | 1.10.18 |
| Local `cassandra-src` clone commit | `$W/cassandra-run2` = `~/Library/Caches/stage4/cassandra-run2`, `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), built with `ant -Dlocal.repository=$W/m2 build-test` (51 s) |
| Case-file commit / harness commit | filed `f361777`; amendments and harness uncommitted (sha256 values in §1) |
| Storage for node data | local SSD, `$W/node-mhs/{data,commitlog,hints,saved_caches,cdc_raw}`, wiped before and after each run; `concurrent_compactors: 1`; loopback `127.0.0.1` only; ports 7000/7199/9042/9091 free before and after |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/memtable_heap_space-applySimpleConfig/` — `build-test-run2.log`, `instrument-compile.log`, `unit/` (ant logs, JUnit XML, `stage4.out`), `cluster/{k64,k256,kunset,ctl-offheap64}/` (`system.log`, `gc.log`, `stress.log`, `samples.csv`, `node.out`, `commands.log`, `summary.txt`), `cluster/attempt1-k64/`, `selfcheck.out` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | Cluster, run 1, first value (64 MiB, "attempt 1") | B3d `jstat -gc <pid> 1000` | jstat cannot attach: `sun.jvmstat.monitor.MonitorException: 26949 not found`, because the node runs with `-XX:+PerfDisableSharedMem` (`conf/jvm-server.options:137`). Excerpt `run1/cluster/attempt1-k64/jstat-error.txt` | Old-gen occupancy read every 1 s over the sampler's JMX connection (`G1 Old Gen` `Usage.used`, `CollectionUsage.used`, heap used); B3f/B3g unchanged | Fixed in the case file (dated "Runbook fix 2026-10-24"); cluster tier restarted from its first value, 2026-10-24 | uncommitted; sha256 `02ff5a09…c0e8` |

Harness-only fix, same attempt: the summary's OOM count matched `-XX:+HeapDumpOnOutOfMemoryError` in the JVM-arguments line; it now counts `java.lang.OutOfMemoryError`. Attempt 1's readings are kept under `cluster/attempt1-k64/` and are not used in the conclusion.

## 4. Run 1

**Scope:** both tiers, all values in §1. **Command log:** `memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous/run1/unit/{commands.log,summary.txt,stage4.out}`, `run1/cluster/<run>/{commands.log,summary.txt,samples.csv,flush-lines-excerpt.txt,gc-full-pauses.txt,stress-results.txt,startup-threshold.txt,yaml-overrides.txt,sjk-*.txt}`.

### 4.1 Readings

**Unit tier** (all from `run1/unit/stage4.out`; JUnit `Tests run: 3/1/1, Failures: 0, Errors: 0`, `run1/unit/summary.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| 1 MiB: at 2 s calls, `used()`, max sampled, writer state | 1,024 calls; `used` = max = 1,048,576; `WAITING` | `stage4.out` (limit1MiB t2s) |
| 4 MiB: same | 4,096 calls; 4,194,304; `WAITING` | `stage4.out` (limit4MiB t2s) |
| 16 MiB: same | 16,384 calls; 16,777,216; `WAITING` | `stage4.out` (limit16MiB t2s) |
| after `released(limit/2)`, 2 s later | resumed for exactly limit/2/1024 calls (512 · 2,048 · 8,192), `used` back at the limit, `WAITING` again, max ≤ limit | `stage4.out` (t4s lines) |
| control `Long.MAX_VALUE`, 65,536 calls | all done, `used` = 67,108,864 (64 MiB), finished, never blocked | `stage4.out` (ctlMaxLimit) |
| control blocking group, 1 MiB, 4,096 calls | `groupBlocking=true`; all done, `used` = 4,194,304 > limit, finished | `stage4.out` (ctlBlocking1MiB) |
| `memtable_heap_space: 0MiB` at `daemonInitialization` | `org.apache.cassandra.exceptions.ConfigurationException: memtable_heap_space must be positive, but was 0MiB` | `stage4.out` (zero) |
| unset, junit fork `-Xmx1024m` | `getMemtableHeapSpaceInMiB()` = **251**; `maxMemory` = 1,056,309,248 B (1,007.4 MiB); `maxMemory/4/MiB` = 251 | `stage4.out` (default) |

**Cluster tier** (each run: `cassandra-stress write n=3000000`, 3,000,000 partitions, 0 errors, 47–52 s of stress operation time, 57–63k op/s)

| Capacity value | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| 64 MiB | A | startup line | `Global memtable on-heap threshold is enabled at 64MiB` | `cluster/k64/startup-threshold.txt` |
| 64 MiB | A | `AllMemtablesOnHeapDataSize` peak / median (75 samples at 1 s) | **25.64 MiB** / 6.96 MiB; 0 samples over 1.05 × knob | `cluster/k64/samples.csv`, `summary.txt` |
| 64 MiB | A | `Flushing largest` lines; `Enqueuing flush` reasons | 254; `MEMTABLE_LIMIT` 254 (all `keyspace1.standard1`), `INTERNALLY_FORCED` 9 | `cluster/k64/flush-lines-excerpt.txt`, `summary.txt` |
| 64 MiB | A | `Used total` on-heap ratio at the triggers | max **1.00**, median 0.67, min 0.33 (pool at 64 MiB at the cap) | same |
| 64 MiB | A | `BlockedOnAllocation` Count at end | **4,083** (sampler and `nodetool sjk` agree) | `cluster/k64/sjk-blocked-end.txt`, `samples.csv` |
| 64 MiB | A | old gen used max; heap used max; full GCs | 78.2 MiB; 1,244 MiB; 0 full GCs; no `OutOfMemoryError` | `cluster/k64/summary.txt`, `gc-full-pauses.txt` (empty) |
| 256 MiB | B | startup line | `… enabled at 256MiB` | `cluster/k256/startup-threshold.txt` |
| 256 MiB | B | gauge peak / median (72 samples) | **85.36 MiB** / 46.08 MiB; 0 over 1.05 × knob | `cluster/k256/samples.csv` |
| 256 MiB | B | flush lines; reasons | 63; `MEMTABLE_LIMIT` 63, `INTERNALLY_FORCED` 9 | `cluster/k256/summary.txt` |
| 256 MiB | B | `Used total` ratio | max 0.67 (171.5 MiB), median 0.33 | same |
| 256 MiB | B | `BlockedOnAllocation` | **64** | `cluster/k256/sjk-blocked-end.txt` |
| 256 MiB | B | old gen used max (after-GC max); full GCs | 888.0 MiB (169.4); 2 full GCs, `2047M->169M`, `1950M->123M` of 2048M; no OOM | `cluster/k256/summary.txt`, `gc-full-pauses.txt` |
| unset (512 MiB) | C | startup line | `… enabled at 512MiB` | `cluster/kunset/startup-threshold.txt` |
| unset (512 MiB) | C | gauge peak / median (76 samples) | **170.18 MiB** / 92.92 MiB; 0 over 1.05 × knob | `cluster/kunset/samples.csv` |
| unset (512 MiB) | C | flush lines; reasons | 31; `MEMTABLE_LIMIT` 31, `INTERNALLY_FORCED` 9 | `cluster/kunset/summary.txt` |
| unset (512 MiB) | C | `Used total` ratio | max 0.67 (343.0 MiB), median 0.33 | same |
| unset (512 MiB) | C | `BlockedOnAllocation` | **0** | `cluster/kunset/sjk-blocked-end.txt` |
| unset (512 MiB) | C | old gen used max (after-GC max); full GCs | **1,933.2 MiB** (473.6); 7 full GCs, heap 1,938–2,048 MiB → 149–473 MiB; no OOM | `cluster/kunset/summary.txt`, `gc-full-pauses.txt` |
| 64 MiB, `offheap_objects`, off-heap 64 MiB | control | on-heap / off-heap gauge peaks | **9.70 MiB** / 21.07 MiB | `cluster/ctl-offheap64/summary.txt` |
| same | control | flush lines; `BlockedOnAllocation`; old gen max | 152 `MEMTABLE_LIMIT`; 3,522; 73.0 MiB, 0 full GCs | same |

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — [observed: `run1/unit/summary.txt`] all three classes ran in their own JVMs with no failures; each limit was reached (calls = limit/1024, `used` = limit) [observed: `stage4.out`]. Valid.
2. **Readings** — the default value is 251, not B2f's "256 (±1)": the junit JVM's `maxMemory` is 1,007.4 MiB under `-Xmx1024m` [observed: `stage4.out`], [inferred: CMS, the build's JDK 11 test collector (`build.xml:233`), reports `maxMemory` without one survivor space]. The value equals `maxMemory/4/MiB`, the relation B2f states in the same sentence and `DatabaseDescriptor.java:586-587` codes.
3. **Matched row** — B2g row 1, "`used()` plateaus at ≤ limit, writer blocks — mechanism works as traced (claim supported)": the plateau is exactly the limit at 1, 4 and 16 MiB, the writer is `WAITING`, and after a release it resumes for exactly the released bytes and blocks again [observed: `stage4.out`]. The validation part: zero is rejected with the predicted `ConfigurationException` [observed: `stage4.out`].
4. **Excluded rows** — row 2 (exceeds the limit with a non-blocking group): max `used` never exceeded the limit [observed]. Row 3 (never blocks, grows to 4 × limit): blocked at the limit in all three [observed]. Row 4 (zero accepted): an exception, no "accepted" line [observed]. Controls: without a limit all calls complete (so the blocking comes from the limit), and the blocking group overshoots to 4 × limit, the documented path [observed].
5. **Observed vs. inferred** — only the CMS explanation of 251 is inferred; the conclusion does not depend on it.
6. **Deviations and gaps** — B2f's number 256 missed (part 2); the prediction was not edited. Only the counter was read, not the slab regions behind it (§1 rec. 6).
7. **Core question** — the pool limit set from the knob stops the writer at exactly the limit for three values, and the limit scales 1:4:16 with them; a zero knob is refused at startup. The constraint caps memtable allocation in the pool.

**Conclusion (unit tier):** B2g row 1 — **confirmed** (with B2f's default number missed: 251 for 256, the relation `maxMemory/4` held).

**Cluster tier**

1. **Validity** — every run wrote 3,000,000 partitions with 0 errors [observed: `stress-results.txt`], ≈ 3 GB, far above every knob; each startup line shows the intended knob [observed: `startup-threshold.txt`]; `memtable_allocation_type`, data directories and `concurrent_compactors` set as B3a [observed: `yaml-overrides.txt`]. Valid.
2. **Readings** — gauge peaks sit near knob/3 (0.40, 0.33, 0.33 × knob), well under the knob: [inferred: the cleaner flushes at `limit × memtable_cleanup_threshold`, which defaults to 1/(2 flush writers + 1) = 1/3, and the gauge omits flushing memtables (amendment B3d)]. At 256 MiB and 512 MiB the 2 GiB heap filled and full GCs recovered it to 123–473 MiB [observed: `gc-full-pauses.txt`]; old gen peaked at 1,933 MiB at 512 MiB [observed: `kunset/summary.txt`].
3. **Matched row** — B3g row 1, "peaks ≤ knob and ordered with the knob — claim confirmed": peaks 25.64 < 85.36 < 170.18 MiB for 64 < 256 < 512 MiB, each ≤ 1.05 × knob [observed: `samples.csv`]; the amended requirement — the limit acted in every run — holds: `MEMTABLE_LIMIT` flushes 254 / 63 / 31, and `BlockedOnAllocation` 4,083 / 64 / 0 [observed: `flush-lines-excerpt.txt`, `sjk-blocked-end.txt`]. At 64 MiB the pool itself stood at the cap (`Used total` 1.00) while writers blocked [observed: `k64/flush-lines-excerpt.txt`].
4. **Excluded rows** — row 2 and the added "`Used total` > 1.05" row: no sample over 1.05 × knob; `Used total` max 1.00 / 0.67 / 0.67 [observed]. Row 3 (equal peaks): ordered, ratio ≈ 1 : 3.3 : 6.6 [observed]. Row 4 ("blocked > 0 only at 64 MiB") is a supporting row and does not hold as worded: 64 blocks also at 256 MiB [observed]; it is not a refuting row. Added rows: "no `MEMTABLE_LIMIT` flush and no block" — every run has flushes [observed]; "old gen reaches the heap maximum or OOM" — old gen max 78 / 888 / 1,933 MiB of 2,048, no `java.lang.OutOfMemoryError` in any `system.log` [observed]; "stress errors" — 0 [observed].
5. **Observed vs. inferred** — the knob/3 explanation of the peak level (part 2) is inferred; the match uses only observed values. That the full GCs at 256/512 MiB reflect uncollected garbage, not retained memtable data, is inferred from the post-GC sizes (123–473 MiB) being below knob + baseline; it bears on the "real resource" row only.
6. **Deviations and gaps** — runbook fix 1 (jstat → JMX old gen) and the sampler amendment; one restart of the tier. `nodetool sjk` took 0–1 s per call here, so two calls per second would have been marginal. The gauge, by its code, does not count flushing memtables; the pool reading (`Used total`) exists only at flush triggers. The off-heap control behaved as B3h says (on-heap gauge 9.70 MiB < 25.64 MiB; data counted off-heap, 21.07 MiB). The cap bounds memtable accounting, not GC pressure: at the default knob with a 2 GiB heap the write load filled the heap seven times (recovered each time, no OOM).
7. **Core question** — on-heap memtable usage followed the knob (peaks ordered 1 : 3.3 : 6.6 for 1 : 4 : 8), stayed ≤ knob in every sample, and the limit visibly acted in every run (limit-triggered flushes, and at 64 MiB the pool at the cap with 4,083 blocked allocations). The constraint caps on-heap memtable usage.

**Conclusion (cluster tier):** B3g row 1 — **confirmed**.

## 5. Self-check of run 1 — AI

Script: [`run1/selfcheck.py`](memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous/run1/selfcheck.py), run as `python3 -I selfcheck.py ~/Library/Caches/stage4/logs/memtable_heap_space-applySimpleConfig`. It re-reads the raw `stage4.out`, JUnit XML, `system.log`, `samples.csv`, `stress.log` and `sjk` files (not the harness summaries) and recomputes each number. Output: [`run1/selfcheck.out`](memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous/run1/selfcheck.out) — 52 checks, **0 do not hold**.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | JUnit XML `failures="0" errors="0"` for all three; stress `Total partitions 3,000,000`, `Total errors 0` in all four runs; startup knob 64/256/512/64 MiB read from `system.log`. |
| 2. Readings | yes | Default 251 = `maxMemory/4/MiB`; the check that B2f's 256 ± 1 does *not* hold is itself a check (holds, i.e. the deviation is real). Full-GC lines re-read from `gc.log` (2 at 256 MiB, 7 at 512 MiB, 0 at 64 MiB and in the control). |
| 3. Matched row | yes | Unit: calls = limit/1024, `used` = limit, `WAITING`, resume = limit/2/1024, for each limit. Cluster: peaks 25.64 / 85.36 / 170.18 MiB recomputed from `samples.csv`, ordered, ≤ 1.05 × knob; `MEMTABLE_LIMIT` flush of `keyspace1.standard1` counted in `system.log` in every run. |
| 4. Excluded rows | yes | No sample over 1.05 × knob in any run; `Used total` max 1.00/0.67/0.67 (on-heap), 0.76 (off-heap, control); no `java.lang.OutOfMemoryError`; old gen < 2 GiB in every sample. Row 4's wording ("only at 64 MiB") does not hold (64 blocks at 256 MiB), as stated in §4.2. |
| 5. Observed vs. inferred | yes | The match uses observed values only; the two inferred statements (knob/3 level; garbage behind the full GCs) are named and not load-bearing for row 1. |
| 6. Deviations and gaps | yes | `BlockedOnAllocation` from the sampler equals the `nodetool sjk` end read in all four runs (4,083 / 64 / 0 / 3,522), so the substituted sampler reads the same MBean. Attempt 1 excluded. |
| 7. Core question | yes | Uses only parts 1–4. |

### 5.2 Run 2?

**No** — 2026-10-24. Every self-check part holds; the result neither refutes the file nor confirms a bypass, and the matched rows rest on observed readings.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested (B1):** with `memtable_allocation_type: heap_buffers`, the global on-heap memtable usage (`MEMORY_POOL.onHeap.used()`, and the sum of `AllMemtablesOnHeapDataSize`) never exceeds `memtable_heap_space` by more than a few in-flight mutations, and its peak scales with the knob; a value of 0 is rejected at startup.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1 — **Confirmed** (pool stops the writer at exactly 1 / 4 / 16 MiB; zero refused; B2f's default number missed: 251, not 256, with `maxMemory/4` holding) | caps | run 1 + self-check | 2026-10-24 |
| Cluster | B3g row 1 — **Confirmed** (peaks 25.6 / 85.4 / 170.2 MiB for 64 / 256 / 512 MiB, all ≤ knob; limit-triggered flushes in every run; at 64 MiB the pool at the cap with 4,083 blocked allocations) | caps | run 1 + self-check | 2026-10-24 |

**Feedback filed:** the case file's section D (uncommitted); amendments of 2026-10-24 (B2a, B2e, B2h, B3d, B3g) and the runbook fix (B3d) in the case file; `_INDEX.md` §1 Stage 4 column, §2 two new sha256 rows, §3 coverage line. Notes for stage 3, not applied: the gauge excludes flushing memtables, and peaks sit near knob/3 because of the default cleanup threshold; at 256 and 512 MiB with a 2 GiB heap the load forced full GCs (the cap bounds memtable accounting, not GC pressure); B2f's 256 assumed `maxMemory` = `-Xmx`; `jstat` cannot attach under the shipped `-XX:+PerfDisableSharedMem`.
