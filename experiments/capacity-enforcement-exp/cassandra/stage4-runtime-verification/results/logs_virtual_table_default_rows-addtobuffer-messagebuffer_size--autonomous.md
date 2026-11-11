# logs_virtual_table_default_rows-addtobuffer-messagebuffer_size--autonomous — stage-4 results  <!-- file: results/logs_virtual_table_default_rows-addtobuffer-messagebuffer_size--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`logs_virtual_table_default_rows-addtobuffer-messagebuffer_size--autonomous`](../../stage3-ai-deep-read/cases/logs_virtual_table_default_rows-addtobuffer-messagebuffer_size--autonomous.md)
>
> **Status:** verdict filed 2026-10-28 — unit and cluster Confirmed (does not cap); no run 2
>
> **Outcome class:** true negative (stage-3 estimate `negative`, stage-4 effect `does not cap`)
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); the feedback section is section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 after the audit's amendments, taken before run 1 and before any run-1 reading: `42b13399cae5cde6751e6489942ea22218b930d1e485bc0bcdeae7af82fc21e8`. File committed at `b68711e5` (HEAD); the amendments of 2026-10-28 are uncommitted. After run 1, section D (stage-4 feedback) was filled; claim, predictions and rows unchanged: final sha256 `8d54022480df9330742aeeb8347e0b602576cf41e7f9238ecf776df9d5b07055`. |
| **Harness** | `harness/logs_virtual_table_default_rows-addtobuffer-messagebuffer_size--autonomous/` (uncommitted; README there) |
| **Tiers and values** | Unit: appender N in {0, 1000, 49999, 50000, 50001, 120000} at 100 B payload, N in {50000, 120000} at 10 KiB, positive control `max.rows` m in {1000, 50000, 100000} (+ m = 500 fallback), 120,000 events. Cluster: runs R1 (A, appender off), R2 (A, on, `max.rows` 100000), R3 (B = constant 1,000, on, 100000), R4 (A, on, `max.rows` 1000); R2 and R3 with two extra start-up-only repetitions. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

| Group | Check | Rating | Note |
|---|---|---|---|
| A | quantity is memory or disk bytes | Partly | Heap held by `LoggingEvent`s in the startup buffer, but the constant caps an event count, not bytes (A2, B2c); the file says so and tests it (10 KiB vs 100 B payload). |
| A | knob varied (>= 3 values incl. default) or other approach | Met | Hard-coded constant (A1); stated. Varied by rebuild: 50,000 (A) vs 1,000 (B); the unit tier sweeps the event count N across the constant (49,999 / 50,000 / 50,001 / 120,000). |
| A | real resource measured | Partly -> Met | Heap after GC and live `LoggingEvent` count, plus RSS in the cluster tier (B2d, B3d); per-event retained bytes derived. RSS of a 1 GiB-heap node is noisy; the claim does not rest on it. |
| A | driven to the limit and past it | Met | Unit: N up to 120,000 > 50,000. Cluster: build B (1,000) is certain to exceed; whether build A's 50,000 is ever reached is itself a row of B3g. |
| A | positive control (negative claim) | Met | B2h/B3h: the table's own `BoundedLinkedList` (`max.rows`) binds and moves with its knob on the same events and instruments; run 4 in the cluster. |
| B | steps establish; prediction numeric; rows for every outcome; disallow evidence | Met | B2f/B2g/B3f/B3g give numbers and relations; rows cover over-cap, follows `max.rows`, byte-insensitive, control failure, limit never reached. The disallow branch is observed as `size == 50,000` with the oldest events kept (`firstSeq` 0). |
| B | alternatives and controls | Met | no-appender run, same seed and JVM flags, `-XX:+UseSerialGC`, full GC before each reading. |
| C | human / AI can follow; values exact | Partly -> Met | B3d said the flush instant was not observable and gave a `debug.log` marker; amended (Byteman observation rule). B2d `jcmd` replaced by the equivalent in-process diagnostic command (amendment). |
| D | harness exists | Met | Written in step 1 (unit probe, Byteman rule, cluster script, seed script, reader, selfcheck); `~/s4-lv` (build A) and `~/s4-lvB` (build B) on `pc39`. |
| D | workload reaches the limit | Met | Unit: 120,000 events, 10 KiB payload about 0.5 GB of a 2 GiB heap. Cluster: 1,000 seeded tables, start-up at TRACE; build B reaches its cap; build A may not reach 50,000 (a row of B3g). |
| D | citations | Met | `VirtualTableAppender.java:54, 86-92, 121-127`, `LogMessagesTable.java:57-59, 129-132, 146-152, 176-197`, `CassandraDaemon.java:291, 534-544`, `CassandraRelevantProperties.java:338`, `conf/logback.xml:114-129` match the pinned source. One slip: the static import is at `VirtualTableAppender.java:36`, not 34 (amended, dated). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Build B must recompile `VirtualTableAppender` (the constant is inlined there) and be checked with `javap` | Applied (B3a amendment, 2026-10-28) | An `ant jar` after editing `LogMessagesTable.java` alone leaves the appender at 50,000, so build B would not differ from A |
| R2 | Observe the flush instant and `messageBuffer.size()` with a Byteman rule; split table rows at the flush millisecond | Applied (B3d amendment) | B3d called the instant unobservable; a 5-s histogram would miss a start-up that takes 18 s |
| R3 | In-process class histogram instead of `jcmd` in the unit probe | Applied (B2d/B2e amendment) | Equivalent, single process |
| R4 | Import line number | Applied (A1, dated) | Group D |
| R5 | The 10-minute stress phase and 3 repetitions of every run are more than the claim needs | Left for stage 3 | Deviations are recorded in §4.2 part 6 |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-28 |
| Node | `pc39` (`node1.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`), 40 cores |
| OS / kernel | Ubuntu 22.04, `5.15.0-198-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Apache Ant 1.10.12 |
| Local source | `~/s4-lv` (build A; `copy-source.sh` of `cassandra/cassandra-5.0.9/` at repository commit `b68711e5`, `ant build-test`) and `~/s4-lvB` (build B: copy of `~/s4-lv` with `LogMessagesTable.java:58` changed to `1_000`, `VirtualTableAppender.java` and `CassandraRelevantProperties.java` touched, `ant jar`; `javap` confirms `sipush 1000` and `= 1000`) |
| Case-file / harness commit | `b68711e5` with the uncommitted amendments (sha256 in §1) / uncommitted |
| Node data | local disk `~/stage4-tmp/lv/node` (copied from the seed `~/stage4-tmp/lv/seed`, removed after each run; `/` had 53 GB free) |
| Full logs | `pc39:~/stage4-logs/lv/` (`run1/`, `seed/`, `shake/`) |

**Instrument checks before run 1** (they produced readings but are not run 1): the unit probe was run by hand with N = 1,500 / 3,000 / 50,000 (fix: baseline heap taken after a full GC through the diagnostic command); the cluster script was piloted twice (`shake/shB`, and a held node by hand): this showed that paging on `system_views.system_logs` returns only the first page (5,000 rows at `fetch_size` 5,000), so the reader uses no paging and selects only `timestamp` (defect 1 below). The case file's predictions were not edited after these.

## 3. Runbook defects

| # | Run | Step (B2/B3) | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | pilot (before run 1) | B3d | `SELECT ... FROM system_views.system_logs` with paging returns only the first page (5,000 rows at `fetch_size` 5,000; `cqlsh` `count(*)` returned 103) | the reader (`readlogs.py`) selects only `timestamp`, with paging off | harness-only; B3d says "counted client-side" and is unchanged | none |
| 2 | pilot | B3d / B3e | the build-B constant is inlined in `VirtualTableAppender` (found at the audit) | amendment B3a, `touch` + `javap` check | file amended, dated, before run 1 | uncommitted |
| 3 | run 1 | B3d (2) | `debug.log` (50 MB rolling) was rotated during the 3-4 minute stress phase, so in R1, R2, R3 and R4 the file no longer holds the start-up lines (`lines_before_flush` 0) | the ground truth of events logged before the flush is the Byteman `attempts` counter (1,993 in every run), cross-checked by `debug.log` in the four start-up-only repetitions (1,993 lines before the flush in each) | none needed; B3d gave two instruments for this | none |
| 4 | run 1 | B3d (3) | a 5-s class-histogram sampler cannot catch an 18-s start-up | covered by the audit amendment (Byteman) | applied before run 1 | uncommitted |

## 4. Run 1

**Scope:** unit tier, 12 JVMs (all exit 0); cluster tier, 8 node starts (R1, R2, R3, R4 full; R2 and R3 two more start-up-only repetitions each). **Command log:** `logs_virtual_table_default_rows-addtobuffer-messagebuffer_size--autonomous/run1/chain.log`; per-run `run1/cluster/<run>/{readings.txt,samples.csv,jvm-extra.txt,build-check.txt,stdout-excerpt.txt}`; unit `run1/unit/unit.out`; checker `harness/.../selfcheck.py`, output `run1/selfcheck.out` (106 PASS, 0 FAIL). Full logs: `pc39:~/stage4-logs/lv/run1/`.

### 4.1 Readings

**Unit tier** (`run1/unit/unit.out`; `size` = `messageBuffer.size()`; heap deltas are noisy by up to 11 MB between JVMs, the N = 0 JVM reads -22.8 MB):

| Test or assertion | Result | Evidence |
|---|---|---|
| appender, 100 B, N = 0 / 1,000 / 49,999 / 50,000 / 50,001 / 120,000 | size 0 / 1,000 / 49,999 / 50,000 / 50,000 / 50,000; first seq 0 and last seq min(N,50000) - 1 (oldest kept, newest dropped); live `LoggingEvent` instances equal size | `unit.out` A100-N* |
| after `stop()` | size 0, instances 0, heap within 25 MB of baseline, in all six | `unit.out` |
| appender, 10 KiB, N = 50,000 / 120,000 | size 50,000 both; heap delta 509.6 MB / 509.8 MB (about 10.2 KB per event) against about 14 to 26 MB (baseline-corrected) with 100 B | `unit.out` A10K-N*, `selfcheck.out` |
| table, `max.rows` = 1,000 / 50,000 / 100,000, 120,000 events | `resolveBufferSize` = m, table size m, first seq 119,999, last seq 120,000 - m (newest m kept); heap delta 0.19 / 10.0 / 20.0 MB | `unit.out` T-m* |
| appender in the same JVMs | size 50,000 for every m (the property does not touch it) | `unit.out` T-m* |
| `max.rows` = 500 (out of range) | falls back to 50,000 (table size 50,000) | `unit.out` T-m500-fallback |

**Cluster tier** (1,000 seeded tables, TRACE, `-Xmx1g`; `attempts` = events that reached `addToBuffer`, `buffered` = `messageBuffer.size()` at `flushBuffer()` entry, both from Byteman):

| Run | Build / appender / `max.rows` | Events logged before the flush (attempts) | Buffer at flush | Buffer after flush | `system_logs` rows stamped <= flush, read at start-up | Rows after stress (read) | LogMessage instances at idle end | RssAnon at idle end |
|---|---|---|---|---|---|---|---|---|
| R1 | A / off / 100000 | none (no `flushBuffer` call) | n/a | n/a | n/a | n/a | 0 | 1,537 MB |
| R2 | A (50,000) / on / 100000 | 1,993 | 1,993 | 0 | 1,993 | 99,922 | 100,000 | 1,579 MB |
| R2 r2, r3 | A / on / 100000, start-up only | 1,993 / 1,993 | 1,993 / 1,993 | 0 | 1,993 / 1,993 | n/a | n/a | n/a |
| R3 | B (1,000) / on / 100000 | 1,993 | **1,000** | 0 | **1,000** | 99,858 | 100,000 | 1,578 MB |
| R3 r2, r3 | B / on / 100000, start-up only | 1,993 / 1,993 | 1,000 / 1,000 | 0 | 1,000 / 1,000 | n/a | n/a | n/a |
| R4 | A / on / **1000** | 1,993 | 1,993 | 0 | 0 (the 1,000-row table already holds only newer rows; 977 rows read) | **1,000** | **1,000** | 1,563 MB |

Other readings: start-up to "native transport running" 17 to 18 s in every run (`readings.txt`); `debug.log` lines stamped before the flush = 1,993 in all four start-up-only runs (`readings.txt` DEBUGLOG); `LoggingEvent` instances after the flush +20 s: 0 in all four start-up-only runs; at the idle end of the full runs 1 or 2; transient peaks during the stress phase 30,736 (R2), 31,684 (R3), 33,298 (R4) while `LogMessage` instances peaked at 356,877 / 386,069 / 32,171 (`samples.csv`); `cassandra-stress` wrote 1,500,000 partitions with 0 errors in each full run (`stdout-excerpt.txt`; 264 / 261 / 169 s); `javap` confirmed `ldc 50000` (A) and `sipush 1000` (B) (`build-check.txt`).

### 4.2 Conclusion and logic

1. **Validity.** The limit was reached: unit N = 50,001 and 120,000 exceed 50,000 and are cut to exactly 50,000 [observed: `unit.out`]; in the cluster the build-B cap (1,000) was hit in 3 of 3 runs (1,993 events logged, 1,000 buffered) [observed: `readings.txt` R3, R3 r2, R3 r3]. Whether the stock cap is reached is itself a row: it is not, with this schema (1,993 < 50,000) [observed]. "Hold fixed" settings: the constant (build A `ldc 50000`, build B `sipush 1000`) [observed: `build-check.txt`]; `-Dcassandra.virtual.logs.max.rows` 100000 in R2/R3 and 1000 in R4 [observed: `jvm-extra.txt`]; the same seeded schema, `-Xmx1g`, SerialGC and the same TRACE logback in every `on` run [observed: `cmdlog.txt` of each run]; the appender is off in R1 [observed: no `LVFLUSH` line in R1's `stdout.txt`]. Valid.
2. **Readings.** (a) The transient `LoggingEvent` (up to 33,298) and `LogMessage` (up to 386,069, above the table's own 100,000 cap) counts seen by the class histogram during the stress phase are not explained; they are equal in order across R2, R3 and R4 and are back to 1 and exactly `max.rows` at the idle end [observed: `samples.csv`]. (b) The 100 B heap deltas carry a baseline wobble of about 11 MB between JVMs [observed: N = 49,999 vs 50,000 differ by 11 MB]. (c) The table read under-counts by about 80 rows at 100,000 (rows with an equal timestamp key collapse) [inferred: 99,922 and 99,858 against `LogMessage` instances exactly 100,000].
3. **Matched row.** Unit B2g row 1, "Appender size = min(N, 50,000), unchanged by `max.rows`; table size = m, moves with `max.rows`": appender size 50,000 in all three m, table size 1,000 / 50,000 / 100,000 [observed: `unit.out`]. Cluster B3g row 1, "Pre-flush `LoggingEvent` peak = 1,000 in B, steady-state `LogMessage` plateau identical in A and B, plateau follows `max.rows` in run 4": peak buffer 1,000 in B with 1,993 events logged (Byteman, 3 runs) [observed]; plateau 100,000 in R2 and R3 at the idle end, and 1,000 in R4 [observed: `samples.csv`]; table rows 99,922 / 99,858 / 1,000 [observed: `readings.txt`]. Row "Pre-flush event count in A below 50,000 so the buffer never fills": also matches (1,993 in all 4 stock-build runs) and supports the negative estimate.
4. **Excluded rows.** "Appender size exceeds 50,000": maximum 50,000 in 7 unit JVMs and 1,993 in the cluster [observed]. "Appender size follows `max.rows`": 50,000 for m = 1,000, 50,000, 100,000 [observed]. "Heap delta at 50,000 is the same for 100 B and 10 KiB": 509.6 MB against about 14 to 26 MB [observed]. "Table size does not move with m" (control fails): it moved [observed]. "N never reached 50,000" and "no `LoggingEvent` instances in run 2": 50,000 reached in the unit tier, 1,993 `LoggingEvent`s buffered in every `on` run [observed]. "Steady-state plateau differs between A and B": 100,000 vs 100,000 [observed]. "`LoggingEvent` instances persist long after the flush": 0 at +20 s in four start-up-only runs and 1 to 2 at the idle end of the full runs, equally in A, B and R4 [observed]; the stress-phase transients are not tied to the constant (peaks 30,736 with 50,000, 31,684 with 1,000) [observed], with the gap in part 2(a). "Run 4 plateau does not move to 1,000": it moved [observed].
5. **Observed vs. inferred.** Inferred: that the pre-flush rows of the table are exactly the rows stamped at or before the flush millisecond **[inferred: matches `attempts` and `buffered` to the event in the 7 runs where the table still held the pre-flush rows]**; that per-event retained size is about 10.6 KB at 10 KiB and about 0.4 KB at 100 B **[inferred: heap deltas against the N = 0 JVM, uncertainty 12 MB]**; that the stock buffer would stay below 50,000 on other schemas **[inferred: only this 1,000-table schema was run; the unit tier shows the cap does bind at 50,000 if that many events arrive]**. The verdict does not rest on the last two.
6. **Deviations and gaps.** Stress phase `cassandra-stress write n=1500000` (about 3 to 4.5 minutes) and one `nodetool flush` per minute, not 10 minutes with repeated `setlogginglevel`; one full run of R1 to R4, and two more start-up-only repetitions of R2 and R3 (not three full repetitions of each); the table was read only twice per full run; `debug.log` rotated in the full runs (defect 3); the `-XX:+UseSerialGC` JVM, not G1; idle-end heap and RSS differences between runs (R2 1,579 MB, R3 1,578 MB, R4 1,563 MB, R1 1,537 MB RssAnon) are small against the noise and carry no part of the verdict; a 100,000-row table is about 10 MB of heap per the unit tier, so a cap at the table's scale is not visible in a 1 GiB-heap node's RSS. The transients in part 2(a) are unexplained.
7. **Core question.** Usage did not follow the constant as a cap on retained log memory. The constant bounds a count: in the unit tier the buffer stops at exactly 50,000 and keeps the oldest events; but a 10 KiB payload makes the same 50,000 events about 0.5 GB, so it does not bound bytes; and on a real node the buffer holds the 1,993 events logged before `setupVirtualKeyspaces()` and is emptied at the flush. Lowering the constant to 1,000 changed only the transient buffer (1,000 instead of 1,993) and nothing at steady state (100,000 rows and `LogMessage` instances in both builds); what moved steady-state usage was `cassandra.virtual.logs.max.rows` (R4: 1,000).

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 — Confirmed (does not cap; positive control moved).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parses `unit/unit.out`, and per run `readings.txt`, `samples.csv`, `stdout.txt` (the Byteman lines), `cmdlog.txt` (the `javap` lines) and `jvm-extra.txt` from the node's full logs and re-tests each number of 4.1 and 4.2: 106 PASS, 0 FAIL (`run1/selfcheck.out`). While writing it, two of its own first-draft assertions failed and were corrected for reasons found in the raw files, not to fit the verdict: the `debug.log` count (rotated in full runs) and the baseline of the 100 B heap deltas (the first version computed a 169x ratio from uncorrected deltas; the corrected, noise-bounded ratio is at least 14x); a third (R4 pre-flush rows) had a wrong expectation because a 1,000-row table keeps only the newest rows.

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | build constants, `max.rows`, appender on/off re-read from `build-check.txt`, `jvm-extra.txt`, `stdout.txt`. |
| 2. Readings | yes | the unexplained transients are stated, not resolved. |
| 3. Matched row | yes | unit row by the `unit.out` cells, cluster row by Byteman and table readings. |
| 4. Excluded rows | yes | each re-tested in `selfcheck.out`; the "persist after the flush" row rests on the start-up-only runs and the idle ends. |
| 5. Observed vs. inferred | yes | the two inferences that carry numbers do not carry the verdict. |
| 6. Deviations and gaps | yes | listed in 4.2 and §3. |
| 7. Core question | yes | dose-response on the constant (50,000 vs 1,000) at a fixed `max.rows`, with the byte test and the `max.rows` control. |

### 5.2 Run 2?

No — 2026-10-28. The unit tier is exact and the cluster readings repeat (3 starts of each of R2 and R3 agree to the event); the inferred statements do not carry the verdict.

## 6. Run 2 — optional

Not done.

## 7. Comparison

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative.

**Claim tested:** memory held by the logging subsystem does not follow `LOGS_VIRTUAL_TABLE_DEFAULT_ROWS` as a usage cap: (i) `messageBuffer` is bounded only in event count and only during startup, and (ii) after the table is registered the retained log memory is governed by the table's own bound (`cassandra.virtual.logs.max.rows`), unaffected by this constant.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (row 1: appender stops at min(N, 50,000) and keeps the oldest; the same count is 0.5 GB at 10 KiB; table size follows `max.rows` and the appender does not) | does not cap | run 1 + self-check | 2026-10-28 |
| Cluster | Confirmed (row 1: build B buffers 1,000 of 1,993 events; steady state 100,000 in both builds; R4 plateau 1,000; the stock cap is not reached: 1,993 < 50,000) | does not cap | run 1 + self-check | 2026-10-28 |

**Positive control:** the table's own bound moved usage: unit `max.rows` 1,000 / 50,000 / 100,000 gave table sizes 1,000 / 50,000 / 100,000 and heap deltas 0.19 / 10.0 / 20.0 MB on the same events and instruments; cluster R4 (`max.rows` 1,000) held 1,000 rows and `LogMessage` instances against 100,000 in R2 and R3. The constant itself bounded the transient buffer exactly where it was set (1,000 in build B; 50,000 in the unit tier), so the instruments see a binding cap when there is one.

**Feedback filed:** section D of the case file (2026-10-28, uncommitted); audit amendments in A1, B2e, B3b and B3e (dated, uncommitted); new sha256 in the final report and `_INDEX.md` is for the orchestrator.
