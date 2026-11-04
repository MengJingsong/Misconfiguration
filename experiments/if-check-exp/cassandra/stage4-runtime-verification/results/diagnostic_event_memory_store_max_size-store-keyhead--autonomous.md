# diagnostic_event_memory_store_max_size-store-keyhead--autonomous — stage-4 results  <!-- file: results/diagnostic_event_memory_store_max_size-store-keyhead--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`diagnostic_event_memory_store_max_size-store-keyhead--autonomous`](../../stage3-ai-deep-read/cases/diagnostic_event_memory_store_max_size-store-keyhead--autonomous.md)
>
> **Status:** **Verdict filed 2026-10-27 — unit Confirmed, cluster Confirmed (for the store's retention), both: caps** (estimate positive, matched); two filed whole-heap cluster sub-predictions missed (memtable confound) and one filed unit tolerance check missed (harness overhead); no run 2
>
> **Outcome class:** true positive — stage-3 estimate `positive` against the stage-4 effect `caps` ([definition](../README.md#outcome-class))
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments. Unit tier: file after amendments U1-U3 and C1-C7 (`a6fa28c611ef27de7b939fc33a05df6ab5b49330a4b4a6a36c4c8142c822bc09`), then the dated runbook-defect fix R-D1 in U2 (the JVM flag; unit attempt 1 crashed at JVM start, before any reading). Cluster tier (frozen before any cluster reading): `cebc9b084588157eb596267b70e0efac76f03de8921ddf04d21348754c5c3ce6` (adds C8). The post-run supplement S1 (paragraph before B4, written after the main cluster run and before the S1 arms ran) gives `8074f33d558f68057c9e2bcbf574e372d9073f28ecf4144cb28f6ea474da1c1f`; the final file with section D filled is `b9c42a361f7f181b6310be0c27770f9eb4d466674f066b62cd26754a10947855`. Base commit holding the unamended file: `7a35ec5` (the amendments are uncommitted: this session does not commit). |
| **Harness** | [`harness/diagnostic_event_memory_store_max_size-store-keyhead--autonomous/`](../harness/diagnostic_event_memory_store_max_size-store-keyhead--autonomous/README.md), written 2026-10-27, not committed. Checks (not readings): `javac` of the probe against the clone; unit attempt 2 is itself the known-answer run (153 PASS lines); `cluster-run.py` shakedown on S-50 (`shake`, discarded) which found the `statusbinary` "not running" substring bug (fixed); `analyze.py` and `selfcheck.py` run on the readings. |
| **Tiers and values** | Unit (B2): m in {1, 50, 200, 1000}, N up to 100000, payload 0 and 64 KiB, 8-thread run, unbounded-map control. Cluster (B3): one node, 3 literals (50 / 200 / 1000 in patched copies) × small (~200 B) and 256 KiB `INSERT` statements, subscription-off arm, second class `SchemaEvent`, client-side retainer, supplementary comment-padded `SELECT` arms. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: heap (on-heap `ConcurrentSkipListMap`); the cap is a count, byte size derivable as count × event size (named in A2). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly → Met | `maxSize` is a literal with no setter outside tests (A1). B2 varies it with `setMaxSize` (1, 50, 200, 1000: Met); filed B3 varied only workload, so a live ceiling could not be seen following the knob. **C1** adds patched-literal copies (50, 200, 1000) that differ in one condition. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met | B3d had instance count and "heap after GC" but no byte reading isolated from other consumers. **C3** adds `[B` bytes from the live class histogram; the memtable confound was not foreseen (see §4, supplement S1). |
| A. Core question | usage driven to the limit and past it | Met | B2c N = 100000 (500 × the cap); B3c 20000 small / 2000 large statements (10-100 × cap). |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps state their reading. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f exact (`min(N,m)`, key range, `[200, 208]`); B3f counts exact, bytes `200 × S`. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | rows exist for flat/growing/over-eviction/overshoot/held-elsewhere; none for "plateau scales with m although size() does" (unit) and for the byte delta missing `M × S` (cluster). **Added** (U1, C4). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met | Unit: yes (size and key range, eviction visible in weak refs). Cluster: needed the varied literal (**C1**) and the in-run growth control (**C2b**). |
| B. Logic | alternative explanations and their controls | Partly → Met | B3 step 8 "persistence disabled" is not a growth control: no subscriber means no `AuditEvent` is ever created (`AuditEvent.java:47-50`). Restated as the one-condition arm (**C2**). |
| C. Specific | a human can follow it from the intro and §9a | Met | A1-A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | needs a JMX client and a client choice (cqlsh vs driver): **C6, C7**. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | second class `GossiperEvent` not producible on one node: **C5** (`SchemaEvent`); heap size for the 1000 arm: **C8**; `-Xmx512m` too small for the control with comfort: **U2**. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | probe test, JMX client, driver script are step-1 work (done). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | pc32: 40 cores, 251 GiB, 54 GB free on `/`. Largest data: 2000 × 256 KiB = 500 MiB per arm; node data under `~/stage4-diag/` (local, 43 MB at the end after truncation by arm); nothing under `/proj`. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked in `cassandra-5.0.9`: `DiagnosticEventMemoryStore.java:39,50-57,86,92`; `DiagnosticEventPersistence.java:99-111,122-129,149-152`; `DiagnosticEventService.java:72-75,221-266,293-301`; `AuditEvent.java:41-50`; `DiagnosticEventAuditLogger.java:27-35`; `FBUtilities.java:648-651`; `conf/cassandra.yaml:1893-1936`. All as cited. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | 64 KiB payload run at m in {50,200,1000}, heap vs m (U1) | Applied 2026-10-27 | byte reading must follow the knob |
| R2 | test heap `-Xmx1g` (U2) | Applied 2026-10-27 | headroom |
| R3 | vary the literal on the live node by patched copies (C1) | Applied 2026-10-27 | the filed B3 never varied the knob |
| R4 | restate the controls of step 8 (C2); in-run growth control | Applied 2026-10-27 | "disabled" arm cannot show growth |
| R5 | byte reading from the histogram (C3), added predictions and rows (C4) | Applied 2026-10-27 | named gap |
| R6 | `SchemaEvent` as second class (C5), JMX client (C6), driver client (C7), heap per family (C8) | Applied 2026-10-27 | runnability |
| R7 | The absolute byte predictions must subtract the memtable (writes store the values too) | **Not seen at audit**; discovered by the readings; recorded as a prediction miss and handled by supplement S1 (§4.2) | A4 lists memtables as another consumer; the audit should have required a statement that stores nothing |
| R-D1 | JVM flag conflict in unit run (see §3) | Applied 2026-10-27 | runbook defect |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 |
| Node | `pc32` (`node2.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`), 40 cores, 251 GiB |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK | OpenJDK 11.0.32.1 |
| Ant | Apache Ant 1.10.12 |
| Local source copy | `~/cassandra-run1` (unmodified `cassandra-5.0.9`, `ant build-test`), `~/cassandra-run2` and `~/cassandra-run3` (copies with only `DiagnosticEventMemoryStore.java:39` changed to `50` and `1000`, `ant jar`), all from `cassandra/cassandra-5.0.9/` at repository commit `68f9c3c` |
| Case-file commit / harness commit | `7a35ec5` (unamended) plus uncommitted amendments (hashes in §1) / harness uncommitted |
| Storage for node data | local `/dev/sda3` (63 GB, 54 GB free), `~/stage4-diag/run1/<arm>/` (removed after the run) |
| Full logs (outside the repo) | `pc32:~/stage4-logs/diag/run1/` (cluster arms, `analysis.txt`, `unit/`), `run1-attempt1-jvmflag-defect/`, `run1-attempt1-guava-defect/` (discarded attempts), `chain*.out` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| R-D1 | unit attempt 1 | B2a (`-Dtest.jvm.args`) | `-Xmx1g -XX:+UseSerialGC`: "Multiple garbage collectors selected", JVM exited before any reading (`results/diagnostic_event_memory_store_max_size-store-keyhead--autonomous/run1/defect-attempts/R-D1-jvmflag.txt`) | dropped `-XX:+UseSerialGC`; U2 amended (dated); unit tier restarted | 2026-10-27, §9a unchanged | uncommitted |
| R-D2 | cluster attempt 1 | B3d (1) / C5 JMX client | `readEvents` for `SchemaEvent` failed to unmarshal: `ClassNotFoundException: com.google.common.collect.ImmutableSet$SerializedForm` (`defect-attempts/R-D2-guava.txt`); `AuditEvent` maps contain only JDK types | client classpath gets `lib/guava-*.jar`; harness fix only; whole cluster tier restarted (attempt 1 discarded) | 2026-10-27, §9a unchanged | n/a (harness) |
| R-D3 | cluster shakedown | B3e step 1 | wait loop `'running' in nodetool statusbinary` is true for "not running" | `strip() == 'running'`; shakedown discarded | 2026-10-27 | n/a (harness) |

## 4. Run 1

**Scope:** unit tier all of B2 (+ supplementary method); cluster tier all of B3 as amended (arms S-50, S-200, S-1000, L-50, L-200, L-1000, OFF) plus supplement S1 (Q-50, Q-200, Q-1000, QOFF). **Command logs:** `diagnostic_event_memory_store_max_size-store-keyhead--autonomous/run1/<arm>/commands.log`, `unit/unit-stage4.txt`.

### 4.1 Readings

**Unit tier** (`run1/unit/unit-stage4.txt`, JUnit `DiagnosticEventMemoryStoreCapTest`, heap max 1056309248)

| Test or assertion | Result | Evidence |
|---|---|---|
| part 1: `size()`, `scan` size, `lastKey`, low/high key, live weak refs after 3 × GC, m in {1,50,200,1000}, N in {m-1,m,m+1,10m,100000} | all exact: size = min(N,m); keys `N-m+1..N`; live refs = min(N,m) (114 checks PASS; 153 PASS and 1 FAIL in the whole test) | `unit-stage4.txt` "part1" lines |
| part 2: 64 KiB payload, heap above baseline at checkpoints | m=50: 3.28/3.35/3.73 MB at N=50/100/10000 (expected 3.28 MB); m=200: 13.13/13.14/13.17/13.51 MB at N=200/400/1000/10000, **16.76 MB at N=100000**; m=1000: 65.68/65.72/66.02 MB at N=1000/2000/10000 (expected 65.5 MB) | "part2" lines |
| part 2, filed tolerance check m=200, N=100000, ±20 percent + 1 MB | **FAIL** (ratio 1.278) | `unit-stage4.txt` |
| part 2b (supplementary, no per-event reference list), m=200 | 13.12/13.26/13.27/13.27/13.27 MB at N=200..100000 (ratio 1.001-1.012) | `unit/unit-part2b.log` |
| part 3: 8 threads × 20000, m=200 | `lastKey` 160000; final `size()` 200; sampled maximum 208 | "part3" lines |
| part 4: unbounded map control | size = N; heap 65.6 MB at N=1000, 328.2 MB at N=5000 (≈ linear, expected 65.5 / 327.7) | "part4" lines |
| upstream `DiagnosticEventMemoryStoreTest` | 6 run, 0 failures | `unit.log` |

**Cluster tier** (`run1/analysis.txt`, `run1/<arm>/readings.jsonl`; M = literal; "live" = `jcmd GC.class_histogram` live `AuditEvent` instances; ΔB = `[B` total minus the post-schema baseline; e0 = 2 events from the schema statements)

| M / arm | Observable | Reading |
|---|---|---|
| 50 / S-50 | readEvents count, live AuditEvent at N = 100, 200, 201, 1000, 3000 | 50, 50 (every N); ΔB 2.0 MiB |
| 200 / S-200 | same at N = 100, 200, 201, 1000, 20000, 20000+30 s | 102, 200, 200, 200, 200, 200 (live equal); ΔB 2.05 → 5.13 MiB; Δheap after GC 2.7 → 14.8 MiB (+12 MiB, see 4.2) |
| 1000 / S-1000 | same at N = 100, 200, 201, 1000, 3000 | 102, 202, 203, 1000, 1000 |
| 200 / S-200, C5 | SchemaEvent subscription, 250 `ALTER TABLE` | SchemaEvent `readEvents` 200 (`maxKey` 1750 = events emitted), AuditEvent 200, live SchemaEvent 200 |
| 200 / S-200, C2d | client-side retainer during 3000 more statements | retained 3200 (= 3000 + 200); store 200 |
| 50, 200, 1000 / L-M | ΔB (MiB) at N = 100, 200, 400, 2000; count | M=50: 39.5, 64.5, 114.5, 173.6, count 50; M=200: 52.0, 102.1, 152.1, 211.1, count 102 → 200; M=1000: 52.0, 102.1, 202.1, 410.7, count 102, 202, 402, 1000 |
| 200 / OFF | ΔB (MiB) at N = 100, 200, 400, 2000; live AuditEvent | 27.0, 52.0, 102.0, 161.1; 0 |
| L-M minus OFF at equal N | ΔB difference (MiB) vs live × 256 KiB | M=50: 12.51 at N = 100..2000 (12.50); M=200: 25.01, 50.03, 50.03, 50.03 (25.5, 50.0, 50.0, 50.0); M=1000: 25.01, 50.02, 100.05, 249.65 (25.5, 50.5, 100.5, 250.0) (`selfcheck.txt`) |
| 50, 200, 1000 / Q-M (supplement S1) | ΔB (MiB) at N = 100, 200, 400, 2000 | M=50: 13.53, 13.53, 13.54, 13.55; M=200: 26.03, 51.05, 51.06, 51.07; M=1000: 26.03, 51.05, 101.08, 251.17 (live 50 / 200 / 1000 at N = 2000) |
| 200 / QOFF | ΔB at N = 100..2000; live AuditEvent | 1.02-1.04 MiB; 0 |

### 4.2 Conclusion and logic

1. **Validity** — [observed: `analysis.txt`, `commands.log`] every arm started the node with `diagnostic_events_enabled: true` and `DiagnosticEventAuditLogger` (yaml tail logged) and JMX reported diagnostics enabled; the limit was passed in every arm (N up to 20000 against M = 200, 2000 against M = 1000, 100000 against m = 200 in the unit tier); the literal in each source copy was changed with `sed` and checked (`grep int maxSize` printed `= 50` / `= 1000` when the copies were made; arm logs show `source cassandra-run2/3`, and the live counts equal 50 / 1000); one client thread. The OFF/QOFF arms never made the subscription (live `AuditEvent` 0 [observed]). Valid.
2. **Readings** — (a) unit part 2 at N = 100000 is above the ±20 percent tolerance: the extra 3.6 MB is the harness's own `WeakReference` list (36 B × 99000 events [inferred: 3.59 MB/99000 = 36.3 B, and part 2b without the list is flat at 13.27 MB, observed]); (b) the 256 KiB `INSERT` arms show `[B` and heap growing past `M × S` and not plateauing at it (L-200: 211 MiB at N = 2000), and the OFF arm, in which no event exists, grows by 161 MiB: the values are also retained elsewhere [inferred: memtable; supported by `S-200` histogram diff N=1000→20000 where `BufferCell`, `BTreeRow`, `AtomicBTreePartition` instances grow ≈ 19000 each (`hist-N01000.txt`, `hist-N20000.txt`) and by the Q arms, where a statement that stores nothing gives the exact plateau]; (c) peak concurrency size 208 is the filed upper bound 200 + 8.
3. **Matched row** — Unit B2g row 1: "`size()` = min(N, m) at every point, live refs ~ m, heap flat after N > m → Cap works as traced (claim confirmed)" [observed: part 1 all PASS; part 2 and 2b]. Cluster B3g row 1, for the store's own retention: "`readEvents` count capped, histogram live `AuditEvent` ~ cap, ... plateau around cap × S → cap bounds heap as traced": count and live instances = min(events, M) for M = 50, 200, 1000 [observed: `analysis.txt`]; byte plateau = live × 256 KiB within 0.1-2 percent when the memtable is cancelled (L minus OFF) [observed: `selfcheck.txt`] and when nothing is written (Q arms: 13.55 / 51.07 / 251.17 MiB against 12.5 / 50 / 250) [observed: `analysis.txt`]; class scaling: 200 per class with two classes [observed: c5]. Two clauses of that row as filed **did not hold**: "heap after GC flat from N = 1000 to 20000" (S-200: +12 MiB) and the absolute "256 KiB phase plateaus around 200 × S" (L-200: 211 MiB, OFF: 161 MiB). The pre-registered OFF-arm prediction (±5 MiB) was also wrong. These are recorded as prediction misses, not tuned.
4. **Excluded rows** — "size() keeps growing / heap grows with N" no: count stays at M while N goes 100×; "size < m after N ≥ m" no (exactly m); "final size beyond m + threads" no (200, max 208); "count capped but heap keeps rising → something else holds the events": the literal whole-heap reading matches the row's condition, but its stated meaning (the cap does not release the events) is excluded because the OFF arm rises identically with no events, ON minus OFF is flat at M × S, and the Q arms plateau at M × S; "count 400 with two classes" fits (200 + 200); "control also flat → invalid": no, the unbounded map grows linearly (unit), the in-run pre-cap growth shows ΔB rising to M × S (Q-200: 26 → 51 MiB), Q-1000 vs Q-50 differ ×18.5, and the client retainer grows to 3200.
5. **Observed vs. inferred** — inferred: (i) the extra growth in L/OFF arms is the memtable (not measured directly; supported by the histogram diff and the exact Q results); (ii) the 36 B/event unit overhead; (iii) S-arm +12 MiB heap growth is memtable rows, not the store (the store's own instance counts are flat).
6. **Deviations and gaps** — no S-OFF arm (the small-statement heap growth is attributed by the histogram diff only); single node, single client thread, simple (unprepared) statements; bytes via `[B` totals and heap-after-GC, no heap dump/dominator tree (dropped, C3); the Q/QOFF arms and the on-minus-off analysis are post-run supplements whose predictions were written before the Q arms ran (S1) but after the main run's readings.
7. **Core question** — Usage of the store followed the cap and not the event count: live events = min(events, M), bytes = events retained × event size, for three values of the literal (50 / 200 / 1000) and for two event classes, over 100-fold more events than the cap. The constraint therefore caps the store's heap, in event count; as a byte bound it is only as tight as the event size (256 KiB events: 50 MiB at 200) [observed + the inferred memtable attribution above].

**Conclusion (one line):** unit B2g row 1, confirmed; cluster B3g row 1 confirmed for the store (count, live instances, class scaling, bytes = M × S via ON-minus-OFF and the no-write arms), with the filed whole-heap absolute-byte, flat-heap-N20000 and OFF-arm predictions missed because the writes' memtable data was not controlled.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | re-read `commands.log` of L-1000 and OFF: `node up ... heap 2G; source cassandra-run3` / `cassandra-run1`, `ENABLED true`, `ENABLE-OK ...AuditEvent` present in L-1000 and absent in OFF; `analysis.txt` baselines e0 = 2 (OFF 0); `ss` port check logged at each start (no listener line); `~/build2.log`, `~/build3.log` BUILD SUCCESSFUL. |
| 2. Readings | yes | re-parsed from raw `hist-*.txt` (`selfcheck.txt`): ΔB per live event at N = 2000 in Q arms 277 / 261 / 257 KiB, in L arms 3555 / 1081 / 421 KiB (memtable). |
| 3. Matched row | yes, with the stated misses | counts and live instances in `readings.jsonl`; `selfcheck.txt` PAIRED lines (12.51 / 50.03 / 249.65 MiB). |
| 4. Excluded rows | yes | OFF `hist-N02000.txt` shows 0 `AuditEvent` rows while `[B` = 161 MiB above baseline. |
| 5. Observed vs. inferred | yes | the memtable attribution stays inferred; it does not change the effect because the isolating readings (ON-OFF, Q arms) are direct. |
| 6. Deviations and gaps | yes | listed. |
| 7. Core question follows the audited logic | yes | steps: configure and reach the limit (1), varied literal (3), disallow evidence = eviction visible as constant live instances while N grows and as the bytes plateau (3), controls (4). |

### 5.2 Run 2?

**No**, decided 2026-10-27: the effect is read directly in three independent literal values and two independent isolations (ON minus OFF, no-write arms) agreeing within 2 percent; the one inferred cause (memtable) does not affect the verdict. A run 2 could add a heap-dump dominator tree or a prepared-statement variant.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** true positive.

**Claim tested (B1):** for any single event class persisted in `DiagnosticEventMemoryStore`, the retained events never exceed `maxSize` (200) plus a small in-flight margin, so retained heap plateaus after about 200 events; the plateau scales with event size and with the number of event classes.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1: Cap works as traced — **Confirmed** (one filed tolerance check missed from harness overhead; supplementary run flat) | caps | run 1 + self-check | 2026-10-27 |
| Cluster | B3g row 1 for the store's retention — **Confirmed** (count, live instances, class scaling, bytes = M × S by ON-minus-OFF and no-write arms); filed absolute whole-heap predictions, flat-heap N=1000→20000 and OFF-arm ±5 MiB **missed** (memtable); a stricter reading could class it Not confirmed as filed | caps (the byte bound is `M × event size`, so only as tight as the events are small; one store per event class) | run 1 + self-check | 2026-10-27 |

**Feedback filed:** the case file's section D updated (not committed); amendments U1-U3, C1-C8, R-D1 and supplement S1 are in the case file; for stage 3: a byte reading for an event store must separate the store from the writes that produced the events (use a non-storing statement or an on-minus-off difference).
