# DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE — stage-4 results  <!-- file: long-path/results/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE.md -->

> **Case:** [`DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE`](../../stage3-ai-deep-read/cases/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided.md)
>
> **Status:** **Closed 2026-10-19 — all tiers verified at stage 4 (verdicts below).** verdict filed (2026-10-15) — **unit: Confirmed; cluster: Confirmed** (§9a row 1) with one missed sub-prediction (ΔCount; explained, not the check): every scratch buffer with *C* ≤ *L* was kept and every one with *C* > *L* replaced by 128 B, at the boundary pair too (*C* = *L* kept, *L* + 2 replaced at 262,144 · 1,048,576 · 4,194,304); the 16 held threads retained 16*C* or 2,048 B exactly, by the ledger and within 41 KB by the JDK direct pool; the staircase moved as tabled (B2: 2,048 B → 14,401,344 B from 256 KiB to 1 MiB; B3: 2,048 B → 60,801,344 B at 4 MiB); the in-use peak 3(*V* + *P*) was the same at every *L*; **bypass as recorded** (*L* = 2³¹ − 1 keeps 60,801,344 B for B3); no run 2
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
| **Case-file version** | Base commit `d47b932` (the last commit touching the case file) plus the step-0 amendment of 2026-10-15 (uncommitted at freeze). §9 hash before the amendment `97a41de373503444eaf451adb90c0465a1b70ecf`, §9a `634e47fcbfca3fae5c9d844e936c8b55c5499985`; **after the amendment §9 `2bd54ee3bc6a06571968ad8f14e6248e6d4c24b3`, §9a `634e47fcbfca3fae5c9d844e936c8b55c5499985` (unchanged)**. §9a is frozen at this version. Recorded 2026-10-15 09:25 EDT, before any reading of this case existed (no `dob` folder under `pc57:~/stage4-logs/`). |
| **Harness** | `../harness/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE/`, written after the freeze (§1.2). Node copy `pc57:~/stage4-harness-run/dob/`. |
| **Tiers and values** | Unit: upstream `DataOutputTest`; harness `DobRecycleTest` U1–U10 at *L* = 262,144 · 1,048,576 (default) · 4,194,304 · 64 and heap mode; U10's two invalid values. Cluster (one node on `pc57`, 4 GiB heap, one start per batch): *L* = 262,144 · 1,048,576 · 4,194,304 with batches B1, B2, B3, BA, BB; BN and the persistence reading at the default; scenario C at 2,147,483,647 (B3) and 64 (B1); arm H (heap mode) with B2 and B3. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-15 |

### 1.1 Design audit

Citations re-read against the pinned clone `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`).

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Direct bytes each thread's scratch buffer keeps between uses (§7); heap bytes in arm H. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 262,144 · 1,048,576 (default) · 4,194,304, plus 2,147,483,647 and 64 (scenario C); restart-only, one JVM per value (9b). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | The JDK direct pool (`MemoryUsed`, `Count`) after a forced GC, against the ledger's total; the pool is not isolating and is read as a difference after a twin warm-up (9d). |
| A. Core question | usage driven to the limit and past it | Met | BA reaches *C* = *L* exactly, BB *C* = *L* + 2, B2/B3 above the two lower values. |
| B. Logic | each step says what it establishes | Met | 9a Logic (1)–(6). |
| B. Logic | prediction stated in numbers or a clear relation | Met | *C* = 2(*V* + *P*) per batch, kept/replaced per cell of the table, 16*C* or 2,048 B retained, τ = 262,144 B, 4× for BN, 3(*V* + *P*) peaks. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | 9 rows incl. *usage exceeds the limit* (above-*L* kept), *flat* (no staircase), *counter capped but resource grows* (ΔMemoryUsed > ΔR + τ), *limit never reached*, invalid. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Staircase plus the `kept`/`replaced` lines for the same writes (9a "A confirmation needs both"). |
| B. Logic | alternative explanations and their controls | Partly → Met after rec. 1 | Twin warm-up (network path), idle window; **but** the twin cannot absorb a per-request direct-memory residue, and native-v5 large requests leave one (rec. 1). |
| C. Specific | a human can follow it from the intro and §9a | Met | — |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met | Rules, line numbers, sizes per batch, readings and their times are given. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met | 9c/9e. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Step-1 work listed (9c); `~/cassandra-run1` built; `DataOutputBuffer$1$1.class` present in `build/classes/main/org/apache/cassandra/io/util/`. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | ≤ 70 MB written per start; 16 × 5.7 MB transient at B3; 4 GiB heap; about 20 starts × ≈ 2.5 min. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Read in context: `DataOutputBuffer.java:44-190` (the `static final` at `:53`, `$1$1.close()` at `:73` / `:75` / `:79`, `allocate()` `:84-89`, `calculateNewSize()` `:158-172`, `expandToFit()` `:174-182`, `setBuffer()` `:184-188`, `buffer(false)` `:232-239`); `BufferedDataOutputStreamPlus.java:124-138` (one `write(ByteBuffer)` call fills, then `doFlush(remaining)` → growth to *V* + *P* exactly); `UnfilteredSerializer.java:413-416` and `UnfilteredRowIteratorSerializer.java:145-153` (exactly one byte after the value); `CommitLog.java:300-330` (`validateSize` first, then the scratch `try`, `getLength()` = *S*, `unsafeGetBufferAndFlip()`); `Mutation.java:81`, `:440-460` (cacheable limit 1 → no site-2 use, `serializedSize < 1` never true); `CBUtil.java:60` (pooled Netty allocator for pre-v5 decoding); `conf/cassandra.yaml:825` (`memtable_allocation_type: heap_buffers`); the `networking_cache_size` results (arm L, the v5 large-request residue). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | The cluster client uses native protocol 4 instead of 5. | Applied 2026-10-15 (9 intro amendment (1), 9c client row); uncommitted | Large v5 requests leave unreturned frame stashes and pooled slots (`CQLMessageHandler.java:755-840`); the `networking_cache_size` run measured +16.8 MB of `java.nio` direct after a GC for 64 one-MB requests. Per request, so not absorbed by the twin; it would fail τ for B2/B3 for a reason that has nothing to do with this check. The server's write path is the same for both protocols. |
| 2 | Record that the sizing derivation (*C* = 2(*V* + *P*), one trailing byte) was re-checked. | Applied 2026-10-15 (amendment (2), a note) | So the audit's check is visible in the case file. |
| 3 | A direct-pool reading that excludes Netty's allocations would isolate the scratch buffers better (e.g. `-Dio.netty.noPreferDirect`). | Left for stage 3 | The ledger already attributes each byte; changing Netty's allocator would change the node under test. |

**Agreement criteria** — not filled (run 2 not chosen yet).

### 1.2 Instrument checks (not readings)

- **Byteman:** `dob-ledger.btm` (7 rules, including the private static `MAX_RECYCLE_BUFFER_SIZE` read and `AT LINE 75` / `79`) and
  `hold.btm` type-check (`TestScript: no errors`, 09:28).
- **9e step 0, the ledger's known answer** (`unit-run.sh instrument`, 09:32, default *L*, `~/cassandra-run3`): 45 checks, 0
  MISMATCH; for the U4 probe *V* = 100,000 after a 50-byte prefix the ledger shows exactly `alloc size=128`, `new cap=128`,
  `alloc size=100050`, `grow-free cap=128`, `alloc size=200100`, `grow-free cap=100050`, `close cap=200100 pos=100051
  limit=200100 L=1048576`, `kept`, `closed cap=200100`, and `ledger.py` gives peak **300,150**; every *L* + 1 probe shows
  `replaced cap=1048577` followed by `alloc size=128`. (A first attempt at 09:29 did not compile: a duplicate variable name in
  U7; fixed. Its broken file also stopped another case's unit tier in the same clone, recorded there.)
- **Cluster shakedown 1** (`~/stage4-logs/dob/shakedown1/`, labels `Ldefault-B2` and `L262144-BB`, 09:42–09:47; not readings):
  every check ran; *P* = 42; 16 distinct held threads; ΔR = Σ per-thread change to the byte; retained 14,401,344 B (kept) and
  2,048 B (replaced); |ΔMemoryUsed − ΔR| = 37,913 / 35,462 B; persistence −35,165 B. One §9a sub-prediction did not hold:
  ΔCount +16 against 14 / 13 new scratch instances (2–3 direct buffers per batch that are not scratch buffers). §9a is frozen,
  so it is left as written and judged on run 1.
- Harness copy `~/stage4-harness-run/dob/` identical to the repository by `md5sum` (`~/stage4-harness-run/dob.md5`) before run 1.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-15, unit 09:39–09:41, cluster 09:47 on |
| Node (CloudLab name and type) | `pc57` (`node0.jason92-319347.misconfiguration-pg0.cloudlab.umass.edu`), 32 cores, 251 GiB RAM |
| OS and kernel (`uname -r`) | Ubuntu, 5.15.0-187-generic |
| JDK (`java -version`) | OpenJDK 11.0.32.1 |
| Ant (`ant -version`) | 1.10.12 |
| Local `cassandra-src` clone commit | unit tier `~/cassandra-run3`, cluster tier `~/cassandra-run1`, both `b5f2a54` (`cassandra-5.0.9`) |
| Case-file commit / harness commit | `d47b932` + uncommitted amendment (§1) / harness uncommitted, md5 list `~/stage4-harness-run/dob.md5` |
| Storage for node data | local disk, `~/cassandra-run1/data` (wiped before every start) |
| Full logs (path, outside the repo) | `pc57:~/stage4-logs/dob/` (`instrument/`, `run1-unit-defect1/`, `shakedown1/`, `run1/` with `unit/` and one folder per label, `chain.log`) |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | run 1, unit tier (09:37) | 9e unit step 1, U5 | U5 read its direct-pool baseline while buffers of earlier probes' **dead** threads were still waiting for a GC; U5's own `System.gc()` then freed them too, so "a parked thread's buffer survives GC (pool unchanged)" read −336,064 / −3,170,815 / −9,462,017 B at the three values (the instrument run had passed by chance: nothing was pending). A harness isolation defect; U5's design is unchanged. | `System.gc()` and a 1 s settle before U5's baseline (`DobRecycleTest.java`); the unit tier restarted from the beginning (09:39); the first attempt kept as `run1-unit-defect1/`. | 2026-10-15 09:39 | none needed (harness only; §9 unchanged) |

## 4. Run 1

**Scope:** unit tier (upstream `DataOutputTest`; `DobRecycleTest` at 262,144 · 4,194,304 · 64 · default · onheap and the two
invalid values; 09:39–09:41, after the restart of §3) and the cluster tier, 20 node starts in 9e order plus `report`
(09:47–10:24). **Command log:** `run1/chain.log`; per label `run1/<label>/summary.txt` (read-back, calibration, plan, twin,
readings, batch, ledger analysis, `EXPECTED:` lines) and `result.json` (the raw readings and per-thread ledger figures);
`run1/report/summary.txt`. Raw excerpts: each label's `ledger.txt.gz` (the whole ledger, compressed) and `hold.txt`;
`run1/unit/*.out`. Full logs, NMT summaries and `system.log` on the node.

### 4.1 Readings

**Unit tier** (`run1/unit/*.out`; 205 harness checks, 0 MISMATCH; upstream `DataOutputTest` 15/15):

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| U1: `MAX_RECYCLE_BUFFER_SIZE`, `ALLOCATION_TYPE` by reflection | 262,144 · 4,194,304 · 64 · 1,048,576; `DIRECT` / `ONHEAP` | `L*.out`, `onheap.out` |
| U2: 128 B direct at the first `get()`; one instance per thread | as predicted (class `DataOutputBuffer$1$1`) | all |
| U3: `write(L)` + `close()` keeps the same buffer at *L*, position 0, pool +*L* − 128, `Count` +0; `write(L + 1)` → a new 128-B buffer, pool +0 | as predicted at the three values (default: +1,048,448 / +0) | `L262144.out`, `Ldefault.out`, `L4194304.out` |
| U4: grow policy | single bytes 129 · 256 · 257 · 100,000 · 1,048,577 → 256 · 256 · 512 · 131,072 · 2,097,152; 50-B prefix + *V* + 1 B → 2(*V* + 50) (524,238 → 1,048,576 kept at the default, 524,239 → 1,048,578 replaced); one-shot 1,000 / 999,999 → 1,000 / 999,999; `calculateNewSize(1)` 134,217,728 at 64 MiB and 100,663,299 = 3(64 MiB + 2)/2 above | same |
| U5: parked thread keeps its buffer across GC; dead thread's buffer stays until a GC, then −262,144 B and `Count` −1 | as predicted (after the §3 fix) | `L262144.out`, `Ldefault.out`, `L4194304.out` |
| U6: 8 parked threads | +8(*L* − 128) at *L* (default 8,387,584), +0 at *L* + 1 | same |
| U7, U8 (*L* = 64) | every `close()` replaces even an untouched buffer, capacity stays 128; `buffer(false)` then `close()` → new 128-B buffer, no exception | `L64.out` |
| U9 (onheap) | not direct, same `byte[]` kept at *L*, replaced at *L* + 1 (128), direct pool unchanged | `onheap.out` |
| U10 | `1MiB` → `ExceptionInInitializerError` ← `ConfigurationException: … expected integer value but got '1MiB'`; `heap` → `ExceptionInInitializerError` ← `IllegalArgumentException: No enum constant …AllocationType.HEAP` | `U10-*.out` |

**Cluster tier** — *P* = 42 in every start (calibration *S*0 = 20,043; the calibration thread's buffer 40,084 = 2(20,000 + 42));
*N* = 16 held writes on 16 distinct threads (4 in BN) in every batch; τ = 262,144 B; ΔR from the ledger, ΔMU = Δ`MemoryUsed`
after a forced GC (`run1/<label>/result.json`, `summary.txt`):

| *L* | Batch | *V* | *C* = 2(*V* + *P*) | Branch (every thread) | Retained by the batch threads | ΔR | ΔMU (− ΔR) | In-use peak |
|---|---|---|---|---|---|---|---|---|
| 262,144 | B1 | 100,000 | 200,084 | kept | 3,201,344 = 16*C* | 3,161,260 | 3,202,038 (+40,778) | 300,126 |
| 262,144 | B2 | 450,000 | 900,084 | **replaced** | 2,048 | 2,048 | 42,723 (+40,675) | 1,350,126 |
| 262,144 | B3 | 1,900,000 | 3,800,084 | **replaced** | 2,048 | −38,164 | −200 (+37,964) | 5,700,126 |
| 262,144 | BA | 131,030 | **262,144 = *L*** | kept | 4,194,304 = 16*L* | 4,151,660 | 4,184,546 (+32,886) | 393,216 |
| 262,144 | BB | 131,031 | **262,146 = *L* + 2** | **replaced** | 2,048 | −40,212 | −4,681 (+35,531) | 393,219 |
| 1,048,576 | B1 | 100,000 | 200,084 | kept | 3,201,344 | 3,199,168 | 3,239,777 (+40,609) | 300,126 |
| 1,048,576 | B2 | 450,000 | 900,084 | kept | 14,401,344 | 14,357,164 | 14,397,768 (+40,604) | 1,350,126 |
| 1,048,576 | B3 | 1,900,000 | 3,800,084 | **replaced** | 2,048 | −38,036 | −2,562 (+35,474) | 5,700,126 |
| 1,048,576 | BA | 524,246 | **1,048,576** | kept | 16,777,216 | 16,734,956 | 16,773,038 (+38,082) | 1,572,864 |
| 1,048,576 | BB | 524,247 | **1,048,578** | **replaced** | 2,048 | −38,420 | −510 (+37,910) | 1,572,867 |
| 4,194,304 | B1 | 100,000 | 200,084 | kept | 3,201,344 | 3,199,296 | 3,234,732 (+35,436) | 300,126 |
| 4,194,304 | B2 | 450,000 | 900,084 | kept | 14,401,344 | 14,401,344 | 14,439,359 (+38,015) | 1,350,126 |
| 4,194,304 | B3 | 1,900,000 | 3,800,084 | kept | 60,801,344 | 60,759,212 | 60,797,243 (+38,031) | 5,700,126 |
| 4,194,304 | BA | 2,097,110 | **4,194,304** | kept | 67,108,864 | 67,068,780 | 67,101,744 (+32,964) | 6,291,456 |
| 4,194,304 | BB | 2,097,111 | **4,194,306** | **replaced** | 2,048 | −38,036 | 2,517 (+40,553) | 6,291,459 |
| 1,048,576 | BN (*N* = 4) | 450,000 | 900,084 | kept | 3,600,336 = 4*C* | 3,598,032 | 3,638,588 (+40,556) | 1,350,126 |
| 2³¹ − 1 | B3 (scenario C) | 1,900,000 | 3,800,084 | kept | 60,801,344 | 60,759,212 | 60,792,098 (+32,886) | 5,700,126 |
| 64 | B1 (scenario C) | 100,000 | 200,084 | **replaced** | 2,048 | 1,792 | 37,321 (+35,529) | 300,126 |
| 1,048,576, heap | B2 (arm H) | 450,000 | 900,084 | kept (`direct=false`) | 14,401,344 | 14,401,088 | 38,134 (direct pool) | 1,350,126 |
| 1,048,576, heap | B3 (arm H) | 1,900,000 | 3,800,084 | replaced (`direct=false`) | 2,048 | −38,292 | 38,278 (direct pool) | 5,700,126 |

Further readings: every write grew its buffer by exactly two allocations, *V* + *P* then 2(*V* + *P*) (+128 at creation or
replacement); every `close` line showed `cap` = *C* and `limit` = *S* = *V* + *P* + 1; no scratch buffer outside the batch threads
changed in any window; the twin (ks0) touched no scratch buffer above 128 B in any start. **Persistence** (default B2): 70 s
later `MemoryUsed` −35,914 B, ledger unchanged. **×N:** BN retains 3,600,336 = ¼ of B2's 14,401,344; ΔMU(B2) − 4 ΔMU(BN) =
−156,584 B (within 4τ). **Scenario C, *L* = 64:** 1,116 `replaced` and 0 `kept` lines on the node before the batch (every
close replaces, including 128-B buffers). **Arm H:** live `[B` after a full GC 48,379,896 (B2) vs 33,934,088 in the direct-mode
start of B2: +14,445,808 (16*C* = 14,401,344); B3 80,344,744 vs 80,331,928: +12,816. **ΔCount:** +14 … +20 in the direct-mode
starts against 12 … 16 new scratch instances (2 to 4 more, every start); +3 / +4 in arm H.

**Supplementary lifetime (after run 1, not a reading)** — `run1/supp-dbb/`, `Ldefault-B1` with `../harness/…/dbb-supp.btm` (every
JDK `DirectByteBuffer(int)` with its stack): the only non-scratch direct buffers created in the batch window and live after the
GC are two Netty `IovArray` buffers of **16,384 B**, one per newly used epoll event-loop thread when the batch client's two new
connections first write (`EpollEventLoop.cleanIovArray`), plus small read-path holders from the driver's schema reads at
connect (169 and 2,697 B); 2 × 16,384 + 169 + 2,697 = 35,634 B against this lifetime's ΔMU − ΔR = 35,532 B. They are per client
connection, not per write (BN, 4 writes, shows the same +2), and the twin cannot absorb them because each client call opens new
connections on event-loop threads not used before.

### 4.2 Conclusion and logic

1. **Validity** — valid in every start. The read-back of the JVM properties and the ledger's `L=` match each label
   [observed: `READBACK`, `CALIBRATION` lines]; *P* = 42 ∈ [20, 127] [observed]; 16 (4) distinct held threads in every batch
   [observed: `hold.txt`, `BATCH`]; the twin touched no scratch buffer [observed: `TWIN`]; the limit was reached (*C* = *L*) and
   passed (*C* = *L* + 2, B2/B3) at every value [observed].
2. **Readings** — nothing contradicts another. One §9a sub-prediction missed in every direct-mode start: ΔCount exceeds the new
   scratch instances by 2–4, with ΔMU − ΔR = +32.9 to +42.7 KB; explained by the supplementary lifetime (Netty `IovArray`s of the
   batch client's new connections; arm H shows the same +3/+4 with no direct scratch buffer at all) [observed: `supp-dbb/`,
   `result.json`]. The bytes stay within τ, so the resource comparison holds.
3. **Matched row** — "Every ks1 buffer with *C* ≤ *L* kept and every one with *C* > *L* replaced, including the boundary pair;
   retained bytes = 16*C* or 2,048 per batch; the staircase moves as tabled; ΔMemoryUsed within τ of ΔR; ×N and persistence
   hold" → **Confirmed** [observed: the table above, `report/summary.txt` 21/21]. Also matched: "Scenario C at 2,147,483,647
   retains 16*C*3 where the default retains 2,048" → **Bypass as recorded** (60,801,344 B vs 2,048 B) [observed].
4. **Excluded rows** — *above-*L* kept / at-or-below replaced*: none of 308 batch writes (19 × 16 + 4); *flat across *L* for B2/B3*:
   2,048 → 14,401,344 (B2) and 2,048 → 60,801,344 (B3); *ΔMU > ΔR + τ*: largest gap 42,723 B; *sizing (C or peak differs)*: *C* =
   2(*V* + *P*) on every thread, peaks identical across *L* (300,126 · 1,350,126 · 5,700,126); *no branch line*: every write has
   one; *invalid* (fewer threads, twin effect, wrong *L*, *P* out of range): excluded by part 1; *limit never reached*: BA/BB.
5. **Observed vs. inferred** — Observed: every branch, capacity, ledger total and pool reading. Inferred: that the 2–4 extra
   `Count` in the 19 direct-mode starts of run 1 have the cause seen in the one traced supplementary lifetime [inferred: same
   size class (32.9–42.7 KB), same per-batch count, also present in arm H].
6. **Deviations and gaps** — The unit tier restarted once (§3). The ΔCount sub-prediction is missed (part 2). The
   supplementary lifetime used a copy of the run script with one extra rule, after run 1. Threads of flush, compaction and
   internode paths (sites 3–4) are not exercised (scope of 9b).
7. **Core question** — Following 9a's logic: (1) each held write ran on its own thread and grew its buffer to exactly 2(*V* +
   *P*) (part 1, table); (2) *C* ≤ *L* kept and *C* > *L* replaced, at the boundary pair too (part 3): the disallow branch acts at
   the limit; (3) the same write size is kept at a larger *L* and replaced at a smaller one (staircase, part 3): retention follows
   the constraint; (4) retained bytes are *N* × *C* or *N* × 128 and scale with *N* (BN): the bound is per thread; (5) the direct
   pool agrees with the ledger within 43 KB: the counter is the resource; (6) the in-use peak is the same at every *L*: the limit
   bounds idle retention only. So `cassandra.dob_max_recycle_bytes` caps each thread's idle scratch buffer at *L* and node-wide
   retention at threads × *L*; it does not cap the buffer while in use, and at *L* above the largest buffer it caps nothing.

**Conclusion (one line):** §9a row 1 — **confirmed**, both tiers, with the ΔCount sub-prediction missed (non-scratch Netty
buffers, explained); scenario C at 2³¹ − 1 — **bypass as recorded**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

An independent script, `run1/selfcheck.py`, re-parses every label's raw ledger and hold file with its own parser (not the
harness's `ledger.py`), takes only the raw JMX and histogram readings and the ledger offsets from `result.json`, recomputes *P*,
*V*, *C*, the branch, every capacity, ΔR, retention, the pool comparison and every cross-label relation from the case's
constants, and counts the unit lines. Run against the repository copy (`ledger.txt.gz`) it gives **204 ok, 18 fail**
(`run1/selfcheck.txt`); **the 18 failures are exactly the ΔCount sub-prediction** of the 18 direct-mode starts.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | *P* re-derived from each ledger's calibration close line; held threads counted from `hold.txt`. |
| 2. Readings | yes | The 18 ΔCount failures re-derived; `supp-dbb/window-direct-buffers.txt` re-read (two 16,384-B `IovArray`s, 169 + 2,697 B). |
| 3. Matched row | yes | Every close line, branch line and final capacity re-derived per thread; staircase, boundary, ×N, scenario C and arm H recomputed. |
| 4. Excluded rows | yes | As above; peaks identical across *L* by an independent replay. |
| 5. Observed vs. inferred | yes | The one inference (the cause of ΔCount in the untraced starts) affects only the missed sub-prediction, not row 1. |
| 6. Deviations and gaps | yes | §3 defect is in the harness's U5 isolation, fixed before the counted unit run. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | 9a Logic (1)–(6) each map to observed rows. |

### 5.2 Run 2?

**No** (2026-10-15). Row 1's evidence is exact and observed (branches, capacities to the byte, the staircase, the boundary
pairs at three values), the self-check holds in every part, the one missed sub-prediction has an observed, non-scratch cause
inside τ, and nothing refutes the case or reveals a new bypass.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

| Tier | Verdict (§9a row) | Basis | Date |
|---|---|---|---|
| Unit | **Confirmed** (row 1): keep at *L*, replace at *L* + 1 (pool +*L* − 128 / +0), grow policy exact, parked vs dead thread, ×8, *L* = 64 replaces every close, heap mode the same rule; invalid values fail class initialization | run 1 (restarted, §3) + self-check | 2026-10-15 |
| Cluster | **Confirmed** (row 1); ΔCount sub-prediction **missed** (2–4 non-scratch direct buffers per batch: Netty `IovArray`s of the client's new connections, ≈ 33–43 KB, inside τ); scenario C at 2³¹ − 1 **bypass as recorded** (60,801,344 B kept by 16 threads) | run 1 + self-check | 2026-10-15 |

**Feedback filed:** the case file's §10 "Stage-4 feedback" updated (2026-10-15, uncommitted); the §9 intro amendment is in the case
file (uncommitted). No refutation; the missed ΔCount sub-prediction is a note for §9d (the direct pool's `Count` also moves with
Netty's per-event-loop `IovArray`, 16 KiB per newly used event loop), not an amendment of §5–§8.
