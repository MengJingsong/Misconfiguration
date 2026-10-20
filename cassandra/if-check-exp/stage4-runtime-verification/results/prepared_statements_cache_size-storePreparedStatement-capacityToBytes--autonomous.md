# prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous — stage-4 results  <!-- file: results/prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous`](../../stage3-ai-deep-read/cases/prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous.md)
>
> **Status:** verdict filed 2026-10-19 — unit Confirmed; cluster Confirmed for the cache with one prediction missed (total heap is not flat); the persisted-statement memtable is a bypass; no run 2
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
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
| **Case-file version** | Autonomous file, sha256 after the audit's amendments: `b055bdde92e1f4861f05424defc1d19a994dd39ac4893fcceb7abe9232aba812` (`sha256sum`, run 2026-10-19 before any harness or run; filed hash `f086b0d2…` in `_INDEX.md` §4, the new line there is this one). Commit holding the file: `0df2870` (HEAD before the amendments: `dc5227d`). |
| **Harness** | `harness/prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous/` (to be written in step 1; none yet) |
| **Tiers and values** | Unit (B2): knob 1 · 2 · 4 · 8 MiB plus the 10 MiB auto default, `-Xmx1g`, plus the oversize statement and the 64 MiB no-eviction control (B2h a). Cluster (B3): 1 · 4 · 16 · 64 MiB, one node, `-Xms2g -Xmx2g`, G1. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-19 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: on-heap bytes of `QueryProcessor.preparedStatements`; weight is a byte estimate (`measureDeep`). |
| A. Core question | knob varied | Met | B2b 1·2·4·8 MiB + auto 10 MiB; B3b 1·4·16·64 MiB. Knob is restart-only (A1), one JVM per value. |
| A. Core question | real resource measured | Partly | B2d/B3d named a heap histogram and MAT; MAT is not installed. **Amended** (R2): live-heap delta after forced GC against an empty-cache baseline. |
| A. Core question | usage driven to the limit and past it | Met | B2c offers 4× the cap; B3c 200,000 statements with a stop condition (**amended**, R3). |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps each name their reading. |
| B. Logic | prediction in numbers | Met | B2f/B3f: sum-of-weights ≤ cap (1/2/4/8 MiB in bytes), count ≈ cap/w, live delta within 2× of weights. |
| B. Logic | every plausible outcome has a row | Partly | B2g/B3g had a row for live heap *much larger* than weight but none for *much smaller* — the over-count A3 itself names. **Added** (R4). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Plateau across values (B2f/B3f) and the oversize rejection (guard at `QueryProcessor.java:825`, text checked) are both required. |
| B. Logic | alternative explanations and controls | Met | B2h/B3h: 64 MiB no-eviction control, duplicate PREPARE, fixed JVM flags, no-PREPARE baseline. |
| C. Specific | a human can follow it | Met | A1–A3 and B1 state claim, mechanism, bypass. |
| C. Specific | an AI can run B2/B3 without re-deriving | Partly | B2a gave no recipe for the per-value yaml (test yaml pins 1 MiB at `test/conf/cassandra.yaml:48`) — **amended** (R1). |
| C. Specific | knob, values, workload, commands, stop conditions exact | Partly | B3c had no stop condition; PREPARE stores one or two entries per statement depending on the session keyspace (`QueryProcessor.java:760-779`) — **amended** (R3, R5). |
| D. Runnable | harness/environment prerequisites | Met | `pc57` has JDK 11.0.32.1, Ant 1.10.12, built `~/cassandra-run1`/`run3` at `cassandra-5.0.9`, bundled driver in `lib/`; no MAT (R2 removes the need). |
| D. Runnable | workload arithmetic reaches the limit | Met | w is unknown until calibration (unit tier, B2c); even at w = 3 KB, 200,000 statements ≈ 600 MB offered against a 64 MiB cap. 47 GB local disk free. |
| D. Runnable | citations spot-checked | Met | Checked in `~/cassandra-run1` at `cassandra-5.0.9`: cache build 113-118, `capacityToBytes` 142-145, guard 825 (message text verbatim), weigher 952-957, `clearPreparedStatementsCache` 970, `Config.java:584-585`, `DatabaseDescriptor.java:795-808`, metric names `PreparedStatementsCount`/`PreparedStatementsEvicted` (`CQLMetrics.java:44,48`), preload log text (`QueryProcessor.java:198`), `Initialized prepared statement caches` (line 138), caffeine 3.1.8. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Per-value yaml = a copy of `test/conf/cassandra.yaml` with the one line changed, passed by `-Dtest.jvm.args=-Dcassandra.config=file://…` | Applied 2026-10-19 (B2a) | the test yaml already sets `prepared_statements_cache_size: 1MiB` |
| R2 | Real-heap reading = live used heap after two GCs minus an empty-cache baseline (unit: in-JVM; cluster: `jcmd GC.run` ×2 + `GC.heap_info` + histogram), not MAT | Applied 2026-10-19 (B2d, B3d) | no heap analyser installed; the prediction (≈ cap within ~2×, linear) is unchanged |
| R3 | B3c stop condition: evictions ≥ 5 × count and Count constant over 10 samples, or 200,000 statements; unmet at 200,000 is Not confirmed | Applied 2026-10-19 (B3c) | a run needs a defined end and a defined failure |
| R4 | Add a row for live-heap delta well *below* the sum of weights (weight over-counts the shared graph) | Applied 2026-10-19 (B2g, B3g), before any reading | outcome the file's own A3 names had no conclusions row |
| R5 | Statements fully qualified, session with no keyspace: one cache entry per PREPARE | Applied 2026-10-19 (B2c, B3c) | `prepare()` stores a second entry under the keyspace-salted id when a session keyspace is set, which breaks `n = 4·cap/w` |
| R6 | B3e step 4 and B3f's third bullet still mention a heap dump and MAT | Left for stage 3 | superseded in place by the dated amendment in B3d; the text is not rewritten |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | | |
| Node (CloudLab name and type) | | |
| OS and kernel (`uname -r`) | | |
| JDK (`java -version`) | | |
| Ant (`ant -version`) | | |
| Local `cassandra-src` clone commit | | |
| Case-file commit / harness commit | | |
| Storage for node data | | |
| Full logs (path, outside the repo) | | |

**Run 1, unit tier (2026-10-19, node `pc57`):** Ubuntu 22.04, kernel `5.15.0-187-generic`; JDK `openjdk 11.0.32.1`; Ant 1.10.12; clone `~/cassandra-run3` at `cassandra-5.0.9`, HEAD `b5f2a54210d541339c2e7c17a794195cac0e67c2` (untracked test files from earlier cases present, none touched); node data not used (unit tier: CQLTester temp dirs on local disk); case file sha256 `b055bdde…` (§1); harness `harness/prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous/` (uncommitted at run 1). Full logs: `~/stage4-logs/psc/unit/` (`run.out`, `ant-<label>.log`, `cassandra-<label>.yaml`), excerpt in `prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous/run1/unit/`.

**Run 1, cluster tier (2026-10-19, node `pc57`, `node0.jason92-319347`):** same OS, kernel, JDK and Ant as the unit tier; clone `~/cassandra-run1` at `cassandra-5.0.9`, HEAD `b5f2a54210d541339c2e7c17a794195cac0e67c2`; one node on 127.0.0.1, `MAX_HEAP_SIZE=2G` (G1, the tag's `jvm11-server.options`), data/commitlog/hints/saved_caches under `~/stage4-psc/` on the local disk (`/dev/sda3`, 47 GB free before); client: the driver bundled in `lib/`, protocol 5, no session keyspace, 8 threads, paced 500 statements/s. Full logs: `~/stage4-logs/psc/cluster/k<MiB>/` (`session.log`, `summary.txt`, `samples.csv`, `histo-*.txt`, `heapinfo-*.txt`); excerpts and the self-check script in `prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous/run1/`. Shakedown (4,000 statements at 1 MiB, `~/stage4-logs/psc/shakedown/`) was a harness check, not a reading.

## 3. Runbook defects

Every step a run could not execute as written. The run stops at the
defect; the fix is made in the case file (dated) if it leaves §9a unchanged,
and the affected tier restarts from its beginning. If the fix would change
§9a, the case goes back to the audit. "None" if there were none.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | unit, attempt 0 | harness compile | `PreparedCacheCapTest` called `QueryProcessor.prepare(...)` statically; `prepare(String, ClientState)` is an instance method (`QueryProcessor.instance.prepare`). `ant` stopped at compile, **before any test ran**, so no reading existed | harness only: `QueryProcessor.instance.prepare(...)` in the five calls | 2026-10-19; harness defect, the case file and §9a/B2f/B2g unchanged | none (harness only) |
| 2 | cluster, shakedown | restart check, ROWS read | (a) the restart wait matched `Starting listening for CQL clients` in the *old* `system.log`, so the restart check read the first boot's `Preloaded 0` line; (b) `cqlsh -e count(*)` printed only the aggregation warning in the captured tail | harness only: the wait reads only log text written after the start (byte offset); the row count is read with `--request-timeout=300` and a numeric-line filter | 2026-10-19; found by the shakedown before any reading; case file and B3f/B3g unchanged | none |
| 3 | cluster, run 1 | B3c stop rule | B3c says samples every 30 s with "Count constant" without a tolerance; the writer (200,000 statements at 500/s = 400 s) gives about 13 samples | the harness reads "constant" as max − min ≤ 1 % of max over the last 10 samples (observed: exactly equal at every value); the load is paced at 500/s so 10 samples exist | 2026-10-19; reading rule only, §9a unchanged | none |
| 4 | cluster, run 1 | B3c oversize PREPARE | at 16 and 64 MiB the oversize literal (cap + 1 MiB) is refused by the **transport** (`CQL Message of size … exceeds allowed maximum of 16777216 bytes`) before `storePreparedStatement` runs, so the guard at line 825 is not exercised there | none: the case's step is run as written; the unit tier covers the guard at all five values | 2026-10-19; recorded as a gap, not a substitute experiment | none |


## 4. Run 1

**Scope:** the tiers and capacity values actually run. **Command log:**
`prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous/run1/<file>`.

### 4.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|

**Cluster tier** — one row per capacity value, scenario and observable:

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|

### 4.2 Conclusion and logic

Tag every statement in parts 1–4 as **[observed: `<file>`]** or
**[inferred: `<reason>`]**. An untagged statement is not part of the
argument.

1. **Validity** — was the run valid? The limit was reached; each §9b "hold
   fixed" setting is confirmed, with its evidence. If not valid, stop here: the
   conclusion is "invalid run".
2. **Readings** — anything unusual in §4.1: a gap, an outlier, a reading that
   contradicts another.
3. **Matched row** — the §9a row, quoted, and the reading that satisfies each
   part of it.
4. **Excluded rows** — for every other §9a row, the reading that rules it out.
   Every **Refuted** row must be addressed.
5. **Observed vs. inferred** — list the inferred statements that the
   conclusion depends on. These are what the self-check most needs to check.
6. **Deviations and gaps** — anything skipped, changed or not observable, and
   how it limits the conclusion.

7. **Core question** — in two or three sentences: did usage follow the
   constraint, and does the constraint cap usage? Follow the "Logic" steps of the
   case's "How this verifies the hypothesis" block (§9a), and cite for each step
   the part above that supports it.

**Conclusion (one line):** `<§9a row>` — confirmed / bypass as recorded /
refuted / not confirmed / invalid run.

### Unit tier readings (run 1, 2026-10-19; `run1/unit/run.out`)

Command log: `~/stage4-logs/psc/unit/summary.txt` (all six `ant` calls rc 0, `Tests run: 1, Failures: 0`; 35 `STAGE4 check` lines, 0 `MISMATCH`). One JVM per value, same test, the test yaml with only `prepared_statements_cache_size` changed (the five yaml copies differ from each other in that line only). Calibration (every JVM): `pstmntSize` 2,696 B, weight `w` = 2,716 B (key 20 B), one cache entry per PREPARE (`keyspace_in_clientstate=null`). `n` = 4·cap/w.

| Label | Knob | cap (B) | n | sum of weights | count | evicted | `system.prepared_statements` rows | live-heap delta (B) | `measureDeep(map)` (B) |
|---|---|---|---|---|---|---|---|---|---|
| k1 | 1 MiB | 1,048,576 | 1,544 | 1,048,376 | 386 | 1,159 | 387 | 1,792,208 | 844,704 |
| k2 | 2 MiB | 2,097,152 | 3,088 | 2,096,752 | 772 | 2,317 | 773 | 3,727,968 | 1,688,736 |
| k4 | 4 MiB | 4,194,304 | 6,177 | 4,193,504 | 1,544 | 4,634 | 1,545 | 8,084,376 | 3,376,800 |
| k8 | 8 MiB | 8,388,608 | 12,354 | 8,387,008 | 3,088 | 9,267 | 3,089 | 16,798,872 | 6,752,928 |
| kauto | auto = 10 MiB (`max(10, 1007/256)`; `maxMemory` 1,056,309,248) | 10,485,760 | 15,442 | 10,483,760 | 3,860 | 11,583 | 3,861 | 21,225,272 | 8,432,800 |
| k64ctl (control B2h a) | 64 MiB, n = 1,544 | 67,108,864 | 1,544 | 4,196,220 | 1,545 | **0** | 1,546 | 4,657,272 | 3,378,976 |

Oversize statement (one `'x…'` literal of cap + 1 MiB chars; every JVM): rejected with `Prepared statement of size 4,196,976 bytes is larger than allowed maximum of 1 MB` (and 6,294,128 / 2 MB, 10,488,432 / 4 MB, 18,877,040 / 8 MB, 23,071,344 / 10 MB, 136,317,552 / 64 MB); count unchanged before/after at every value. Duplicate control: 100 re-PREPAREs of one text added at most one entry (386→386 … 1,545→1,546 where the text was new).

Derived ratios (recomputed independently from `run.out`): sum/cap = 0.9998 at 1 · 2 · 4 · 8 · 10 MiB, 0.0625 at the 64 MiB control; count × w = sum at every value; live-heap delta / sum = 1.71 · 1.78 · 1.93 · 2.00 · 2.02 (control 1.11); `measureDeep(map)` / sum = 0.81 at every value (0.80 at kauto).

### Unit tier conclusion (B2g)

1. **Validity** — [observed: `run.out` plan/final lines] the cap was reached and passed at every knob value (offered weight 4× cap, evictions 1,159–11,583); each "hold fixed" setting is in the logs (same JVM flags, same test, same yaml but the knob; `keyspace_in_clientstate=null`).
2. **Readings** — the live-heap delta is not constant against the weights (1.71 → 2.02 × sum); it includes the `system.prepared_statements` memtable rows written for every one of the n inserts (n grows with the cap), which the cache does not hold.
3. **Matched row** — B2g row 1, "Sum-of-weights plateaus at <= cap and count scales linearly with cap": [observed] sum/cap 0.9998 at five values; count 386 · 772 · 1,544 · 3,088 · 3,860 = ⌊cap/w⌋ (cap/w = 386.0 · 772.1 · 1,544.3 · 3,088.6 · 3,860.7); the oversize statement is rejected at every value and never cached; the 64 MiB control evicted nothing and held all n + 1.
4. **Excluded rows** — "exceeds cap persistently": sum ≤ cap in 5/5 capped runs. "Oversize cached": count unchanged in 6/6. "Cap never reached": evictions > 0 in 5/5, 0 in the control. "Much larger than weight (more than 2x) / flat vs knob": delta/sum is 1.71–2.02, **at the line at k8 (2.00) and just past it at kauto (2.02)**, not "much larger"; the delta rises with the knob (1.79 → 21.2 MB across 1 → 10 MiB) and drops to 4.66 MB with the same 1,544 offered statements when the cap is not binding, so it is not flat. The new row "less than half of the weight" did not fire: delta/sum ≥ 1.71. **A literal reading of the row's "(more than 2x)" would call kauto's 2.02 a hit; the row's own words say "much larger", and the control below shows what the excess is, so this is recorded as a deviation, not as the matched row.**
5. **Observed vs. inferred** — [inferred: control] k64ctl holds the same 1,544 statements as k1 saw, with delta/sum 1.11, so the cache's own heap is about 1.1 × its weights, and the extra (k1: 1.79 − 1.16 ≈ 0.63 MB) is the other n-dependent heap, i.e. the system-table memtable; [inferred: `measureDeep(map)` = 0.81 × sum] the weights over-count by about 19 % because each `Prepared`'s shared graph is counted once per statement in the weigher but once in the map walk — the over-count is a constant factor, so the cap is conservative on the estimate, not unbounded.
6. **Deviations and gaps** — no heap analyser (R2): the live-heap delta is a whole-JVM delta with an empty-cache baseline, so it includes the system-table memtable rows; the unit tier therefore bounds the ratio of cache heap to weights only through the 64 MiB control (one point). Not run here: concurrency overshoot (B2 is single-threaded). `Preload`/restart is cluster tier.
7. **Core question** — usage (the cache's weight and entry count) follows the constraint exactly: it plateaus at ⌊cap/w⌋ entries at five values and falls back to 1,545 entries (no plateau) when the cap is 64 MiB; one oversize statement is refused at every value. The real heap tracks the knob too (1.8 → 21.2 MB for 1 → 10 MiB) and sits at about 1.1 × the weights for the cache alone. The constraint caps the cache; whether the cap also holds under a real node is the cluster tier.

**Unit tier conclusion (one line):** B2g row 1 — **confirmed** (weights ≤ cap, count ∝ cap, oversize refused; live-heap ratio 1.71–2.02 recorded as a deviation).

### Cluster tier readings (run 1, 2026-10-19; `run1/cluster/k<MiB>/summary.txt`, `samples.csv`, `histo-excerpt.txt`)

One node lifetime per value (wipe, start, work, stop). Knob read-back from `system.log` each time (`Initialized prepared statement caches with N MiB`). Each lifetime: baseline heap → 20,000 unprepared SELECTs (control d) → 100 re-PREPAREs of one text (control a) → paced PREPARE load until the stop rule → settle 30 s → final heap → oversize PREPARE.

| Knob | cap (B) | statements prepared (stop rule met at) | `PreparedStatementsCount` (last 10 samples) | evicted | `system.prepared_statements` rows | `Prepared` instances (histogram) | live bytes: baseline → after plain → after load | `AllMemtablesHeapSize` of `system.prepared_statements` | oversize PREPARE |
|---|---|---|---|---|---|---|---|---|---|
| 1 MiB | 1,048,576 | 151,819 (304 s) | 395 (395..395) | 151,450 | 395 | 426 | 66.73 M → 68.14 M → 161.35 M | 110.40 M | guard refused: size 4,196,904 > 1 MB; count 395 → 395 |
| 4 MiB | 4,194,304 | 151,807 (304 s) | 1,581 (1,581..1,581) | 150,243 | 1,581 | 1,612 | 66.74 M → 68.03 M → 163.79 M | 110.34 M | guard refused: 10,488,360 > 4 MB; 1,581 → 1,581 |
| 16 MiB | 16,777,216 | 151,813 (304 s) | 6,326 (6,326..6,326) | 145,498 | 6,326 | 6,357 | 66.73 M → 68.24 M → 174.09 M | 110.11 M | transport refused (17,825,831 > 16,777,216); 6,326 → 6,326 |
| 64 MiB | 67,108,864 | 167,056 (335 s) | 25,305 (25,305..25,305) | 141,762 | 25,305 | 25,336 | 66.74 M → 68.25 M → 224.06 M | 120.30 M | transport refused (68,157,479 > 16,777,216); 25,305 → 25,305 |

Other readings: 100 re-PREPAREs of one text added one entry (0 → 1) at every value. Hot statements (executed every 200th operation, 760–836 per run): all executed correctly, 0 client errors in every load. 20,000 unprepared queries grew live bytes by 1.40 M · 1.30 M · 1.51 M · 1.51 M. At 1 MiB the node was stopped and restarted without wiping: `Preloaded 395 prepared statements in 787 ms`, no "filling up" warning, count after restart 395. `du` of the table's SSTables is 4,096 B at every value (nothing flushed). Rows: 395 · 1,581 · 6,326 · 25,305. Derived (recomputed by `run1/selfcheck.py`, ALL HOLD): per-entry weight cap/count = 2,654.6 · 2,652.9 · 2,652.1 · 2,652.0 B; count ratios to 1 MiB = 1 : 4.003 : 16.015 : 64.063; `Prepared` instances = count + 31 at every value; count + evicted − prepared = 26 · 17 · 11 · 11; live delta after load (vs after plain) = 93.21 M · 95.75 M · 105.85 M · 155.82 M; (k4 − k1) / (4 − 1 MiB) = 0.809 and (k16 − k1) / (16 − 1 MiB) = 0.804 at equal offered n (151,807 / 151,813 vs 151,819).

### Cluster tier conclusion (B3g)

1. **Validity** — [observed: `summary.txt`] the knob read back as the case's value in 4/4 lifetimes; the cap was reached and passed (evictions 141,762–151,450, at least 5 × count in every run: 5.6× at 64 MiB, 23× at 16, 95× at 4, 383× at 1 MiB); each fixed setting held (`MAX_HEAP_SIZE=2G`, same yaml but the knob, same client and rate); the stop rule of B3c was met at every value before 200,000.
2. **Readings** — [observed] the count is identical in every one of the last 10 samples. The live-heap total grows by 93–156 M although the cache holds 1–25 k entries; at equal offered n the growth is the same for 1, 4 and 16 MiB apart from a difference that follows the cap. The memtable accounting of the system table (110.1–120.3 M) is larger than the live delta (93.2–105.9 M) at 1/4/16 MiB, so it cannot simply be subtracted.
3. **Matched row** — B3g row 1, "Count and retained heap plateau, scale with the knob": [observed] the count plateaus at ⌊cap/w⌋ with w ≈ 2,652 B and scales 1 : 4 : 16 : 64 within 0.4 %; [observed] the retained heap that depends on the knob scales with it: at equal offered n, each extra MiB of cap adds 0.80–0.81 MiB of live heap; [observed] the oversize PREPARE is refused with count unchanged (by the guard at 1 and 4 MiB, by the transport at 16 and 64 MiB).
4. **Excluded rows** — "Count grows with offered statements regardless of the knob": count is constant over 10 samples at 395 / 1,581 / 6,326 / 25,305. "Heap keeps growing": **the whole-JVM live heap does grow with the offered statements, by a knob-independent amount (about 93 M at 151,819 PREPAREs, about 614 B each)**; this is the part of the row that literally applies, and it is addressed under Deviations, because B1's claim is about the cache's weight and heap. "Oversize accepted": never. "Evicted counter stays 0": no. "Cap bounds the estimate, not real heap (more than 2x)": the knob-dependent heap is 0.80 × the weights, so the estimate over-counts slightly, the cap is conservative; the new "less than half" row did not fire (0.80 > 0.5). "Heap difference swamped by GC noise": the histogram's live-bytes reading is exact after a full GC (`jmap -histo:live`).
5. **Observed vs. inferred** — [inferred: same-n pairs] the extra heap per extra MiB of cap is the cache's; the rows that depend on offered n are the same across values (151,807–151,819), so the n-dependent heap cancels. [inferred: plain control and k1 growth] the knob-independent growth is caused by the PREPARE path itself, not by connections or queries in general: 20,000 unprepared queries grew live bytes by 1.4 M and 151,819 PREPAREs by 93.2 M (66× the growth for 7.6× the statements: 70 B per unprepared query against 614 B per PREPARE). [inferred: `AllMemtablesHeapSize` 110 M, table SSTables 4,096 B] that growth is the memtable of `system.prepared_statements` (one row written per PREPARE, a delete per eviction, nothing flushed in the run). [inferred] the 64 MiB lifetime's extra live heap includes about 15 k more rows than the others.
6. **Deviations and gaps** — (a) **B3f's last bullet ("Total heap used does not grow with the offered workload beyond the plateau") is refuted as stated**: total live heap grew 93 M at 1 MiB while the cache stayed at 1 MiB; the cause is a consumer the knob does not bound. (b) The 16/64 MiB oversize PREPARE never reached the guard (runbook defect 4). (c) No heap analyser, so the cache's own retained size is read only by differences (0.80 × weights); the absolute retained size of the cache is not measured. (d) 64 MiB is not an equal-n comparison; it is shown, not used for the ratio. (e) Flush behaviour of the system table beyond 150 k statements, and concurrency overshoot (one client, 500/s), were not tested. (f) The restart check ran only at 1 MiB.
7. **Core question** — usage of the cache follows the constraint exactly: its entry count and weight plateau at the knob (1 : 4 : 16 : 64) and the live heap that follows the knob grows 0.8 × the knob, so the constraint caps the cache. But the same workload still grows the node's heap without bound by the knob, by about 0.6 KB per PREPARE through the persisted-statements memtable, so the knob does not cap the memory a PREPARE flood uses.

**Cluster tier conclusion (one line):** B3g row 1 — **confirmed for the cache**; **bypass as recorded**: the persisted-statements memtable (`system.prepared_statements`) grows with offered statements, independent of the knob; B3f's last bullet refuted.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-open every raw file the conclusion cites and confirm it says what the
conclusion says. A part that does not hold is fixed, or the conclusion is
downgraded to *Not confirmed*.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.py` (exit 0, ALL HOLD) re-reads each `k<MiB>/summary.txt`: count = rows, `Prepared` instances = count + 31, last 10 samples constant, evicted ≥ 5 × count at 4/4 values; unit `run.out`: knob and `maxMemory` lines re-read. |
| 2. Readings | yes | Re-read `samples.csv` (13 samples per value, count constant from the first sample at 395 · 1,581 · 6,326 and from sample 2 at 25,305) and the histogram totals; the unit table recomputed (ratios 1.71–2.02, 0.81). |
| 3. Matched row | yes | B2g row 1 and B3g row 1 each quoted against the reading; the 0.809 and 0.804 ratios recomputed to three digits from the raw live-bytes lines. |
| 4. Excluded rows | yes, one qualified | every row addressed; the "heap keeps growing" row is addressed through the knob-independent growth and the 66× contrast with the plain control, not dismissed (66× the growth for 7.6× the statements, 614 B against 70 B each). |
| 5. Observed vs. inferred | yes | the memtable attribution is inferred from `AllMemtablesHeapSize`, the 4,096 B SSTable size and the plain control; it is labelled as inferred and the verdict does not depend on it beyond naming the bypass. |
| 6. Deviations and gaps | yes | runbook defects 1–4 in §3; the guard not reached at 16/64 MiB; no analyser. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | steps B3e 1–7 map to the phases; plateau → scale → oversize → control, in the case's order. |

### 5.2 Run 2?

**No** (decided 2026-10-19). The load-bearing figures (counts, evictions, rows, instance counts, guard messages) are observed in raw files and recomputed by `run1/selfcheck.py`; the inferred statements (the same-n difference 0.809 / 0.804, the memtable attribution) are labelled, agree across two independent pairs and with the unit tier's `measureDeep` ratio 0.81. The default guidance would favour a run 2 because the result confirms a bypass and rests on inferred statements; the bypass is recorded as such (as in earlier closed cases), and a run 2 that tests the memtable attribution directly (`nodetool tablestats`, or flushing the table) is the thing to ask for if Jingsong wants it.

## 6. Run 2 — fresh AI session (optional)

"Not done" if §5.2 says no, and §7 is left out.

**Scope:** the tiers and capacity values actually run. **Command log:**
`prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous/run2/<file>`.

### 6.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|

**Cluster tier**

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|

### 6.2 Matched row

The §9a row these readings match, in one line.

## 7. Comparison — only if run 2 was done

| Observable | Run 1 | Run 2 | Criterion (§1) | Agree? |
|---|---|---|---|---|

**Same §9a row?** yes / no. If no, or if a reading disagrees: the cause, and
how it was resolved (see "Compare and decide" in the README).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive (from the case file: the entry bounds the estimated weight of the on-heap prepared-statement cache; the weight is an estimate).

**Claim tested (B1):** the total estimated weight of `QueryProcessor.preparedStatements` never stays above `prepared_statements_cache_size` after insertions settle, and the real retained on-heap bytes of the cache grow roughly in proportion to that value until it is reached and stay flat beyond; a single statement heavier than the cap is rejected at line 825 and never cached. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1: sum of weights 0.9998 × cap at 1 · 2 · 4 · 8 · 10 MiB, count ⌊cap/w⌋ (386 · 772 · 1,544 · 3,088 · 3,860), oversize refused at 6/6, 64 MiB control evicted nothing; live-heap delta ÷ weights 1.71–2.02 recorded as a deviation (the system-table memtable rows are in it) | caps (the cache) | run 1 + self-check | 2026-10-19 |
| Cluster | **Confirmed for the cache** — B3g row 1: count 395 · 1,581 · 6,326 · 25,305 (1 : 4 : 16 : 64), constant over 10 samples, rows equal count, knob-dependent live heap 0.80 × weights, guard refused the oversize PREPARE at 1 and 4 MiB (transport refused at 16 and 64); restart preload 395 statements. **B3f's last bullet refuted:** total live heap grew 93 M (≈ 614 B per PREPARE, knob-independent) through the memtable of `system.prepared_statements` | caps only on some paths (bypass) | run 1 + self-check | 2026-10-19 |

**Feedback filed:** the case file's section D updated (not committed; commit when Jingsong asks). No section of the case amended after run 1. Recommendations for stage 3, left unapplied: (1) the case's A4 names the system table as an "other consumer"; the run shows it is the **dominant** one for the PREPARE path and the claim could say so; (2) B3's oversize PREPARE needs a cap below the transport limit (16 MiB) to reach the guard; (3) the cache's own retained size needs a heap analyser (MAT) if it is to be read directly.
