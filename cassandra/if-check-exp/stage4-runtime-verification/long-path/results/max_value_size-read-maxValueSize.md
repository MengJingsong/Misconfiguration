# max_value_size-read-maxValueSize — stage-4 results  <!-- file: long-path/results/max_value_size-read-maxValueSize.md -->

> **Case:** [`max_value_size-read-maxValueSize`](../../../stage3-ai-deep-read/long-path/cases/max_value_size-read-maxValueSize.md)
>
> **Status:** verdict filed (2026-10-14) — **Confirmed at both tiers**; write side **bypass as recorded** (values above the limit accepted and held, refused on every read); sibling primitive **bypass as recorded**; compaction and replay **refusal as traced**; one replay sub-prediction missed (no `Replay stopped` line); no run 2
>
> **Path:** long. One results file per path, each in its path's folder.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../../README.md`](../../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base commit `2ac7a92` (case file unchanged since `639fb5c`) plus the step-0 amendments of 2026-10-14 (uncommitted at freeze). §9 hash after the amendments: **`d37c723416aed9dfec568ff19c0a0004edf94a03`** (`sed -n '/^## 9\. /,/^## 10\. /p' <case> \| git hash-object --stdin`); §9a alone `4b2e31da5f110dd9d70bb9fbb39814fe39aaed6c`. §9a is frozen at this version. |
| **Harness** | `../harness/max_value_size-read-maxValueSize/` (uncommitted at run 1): `MaxValueSizeGuardTest.java`, `unit-run.sh`, `make-unit-yaml.sh`, `make-node-yaml.sh`, `value-alloc.btm`, `send-value.py`, `cluster-run.py`, `README.md`. **Written 2026-10-13 by the session that first audited the case and restored from its node copy on 2026-10-14** (see "Provenance" below); md5s equal those printed by every 2026-10-13 run summary (`MaxValueSizeGuardTest.java` `f8512fa7…`, `value-alloc.btm` `ef063c7f…`, `cluster-run.py` `a633c532…`, `send-value.py` `0eda58c3…`, `make-node-yaml.sh` `5dbf68ff…`, `make-unit-yaml.sh` `01009d13…`, `unit-run.sh` `2173f470…`). Node copy `pc57:~/stage4-harness-run/mvs/`, identical. Instrument checks: §1.2. |
| **Tiers and values** | Unit: harness `MaxValueSizeGuardTest` at *M* = 1, 4, 8 MiB and 256 MiB (live, one JVM); range controls 0 and 2048 MiB; upstream `SSTableWriterTest`. Cluster (one node on `pc57`, RF 1): Phase 1 at `1m`, `4m`, `8m`, `default`; compaction arm at 1 MiB; replay arm 4 → 1 → 4 MiB. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-14 |

### Provenance — the lost 2026-10-13 audit and the run that is not counted

A session audited this case on 2026-10-13, amended its §9, wrote the harness and ran the whole design on `pc57`
(19:42–19:54 MDT: unit, `1m`, `4m`, `8m`, `default`, compaction, replay, then a self-check). Its audit record, the case-file
amendments, this results file, the repository harness folder and its self-check script never reached the repository (the
2026-10-14 handoff found only the node copies: `~/stage4-harness-run/mvs/`, file times 19:39, and `~/stage4-logs/mvs/`). The
protocol requires the audit and the freeze to be recorded before any reading, so **that run is not counted**: its logs are kept
on the node as `~/stage4-logs/mvs-2026-10-13/` and cited only here and in §8 as an earlier, unrecorded run.

This session (2026-10-14) **read that run's summaries before re-auditing**, so the re-audit is not blind to readings. To keep
predictions from being tuned to them, the amendments are restricted to what the **pre-run harness** already encoded (its
`EXPECTED` lines and test checks, dated 19:39, three minutes before the first reading), and each was re-derived from the cited
source before it was written into §9. Every other prediction is left as stage 3 wrote it, **including one the 2026-10-13
readings contradict** (the replay arm's `Replay stopped` line; the harness kept that prediction, and so does §9a). The harness
code's comments name the lost audit's recommendations "rec. 2" and "rec. 3"; recommendation 1 and any others are not
recoverable and are not reconstructed.

### 1.1 Design audit

Citations re-read against the pinned clone `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`).

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | The heap `byte[]` made for one deserialized value (§7); the disk effect (a suspect SSTable no longer compacted) is a secondary arm. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | Unit 1, 4, 8, 256 (default) MiB, live; cluster 1, 4, 8 MiB and the default as a control (a client cannot write 256 MiB at stock caps, §11). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | Unit: thread-allocated bytes *Δ* around each call (exact). Cluster: the array sizes requested at the allocation site (Byteman); the node's heap is not measured and 9d names the gap. |
| A. Core question | usage driven to the limit and past it | Met | *M*, *M* + 1, *M* + 65,536 at every value, 2³¹−1 and 2³¹ at the unit tier. |
| B. Logic | each step says what it establishes | Met | §9a "How this verifies", Logic (1)–(5). |
| B. Logic | prediction stated in numbers or a clear relation | Met | Exact lengths, *Δ* bands (*M* … *M* + ε, < ε), ratio 1 : 4 : 8, message text with both operands. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | Scenario C's rows assumed a memtable read never deserializes a value; it does (rec. 1), so the outcome "over-limit values fail before the flush" had no row, and the "read back whole before the flush" row could not occur. Rows added (rec. 1). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The Confirmed row needs the 1 : 4 : 8 ceiling and the guard's message with both operands, plus no `alloc` line of a refused length. |
| B. Logic | alternative explanations and their controls | Met | Frame and mutation caps (every row is below them), timeouts (raised to 10 s), the known-answer row for the trace, the `ks1.ok` compaction control, the replay control under 4 MiB, the sibling / skip / fixed-length unit controls. |
| C. Specific | a human can follow it from the intro and §9a | Met | §9 intro, §9a. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | Scenario C, the default arm's pre-flush read and the error class of a pre-flush refusal needed the local-response path (rec. 1); the real deserializers' exception type (rec. 2); the compaction arm's leftover-file check names a file kind 5.0 does not write (rec. 3). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | The driver's default retry policy turns a one-node `ServerError` into `NoHostAvailable`, hiding the class scenario C reads (rec. 4). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Harness restored (above). `pc57` (this host): JDK 11.0.32.1, Ant 1.10.12, `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54`), built, Byteman 4.0.20 in `build/lib/jars/`, the bundled Python driver. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Largest write 15,728,640 B, under the 16 MiB mutation and frame caps; 4 GiB node heap; the unit JVM allocates a few 256 MiB arrays under `-Xmx4G`; disk under 100 MB per value on a 55 GB disk. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Read in context: `AbstractType.java:567-601` (`:590`, `:591-592`, `:594`, `:595-597`, `:599`); `ByteArrayAccessor.java:100-105`; `ByteBufferUtil.java:371-389`, `:444-452`; `Cell.java:307-348`; `UnfilteredSerializer.java:620-632` (`WrappedException` unwrapped to `IOException`); `UnfilteredRowIteratorSerializer.java:236-246` (`IOError` at `:244`); `ReadResponse.java:46-53`, `:182-207`, `:248-262`; `StorageProxy.java:2200-2253` (`LocalReadRunnable`: `createResponse` at `:2211`, `UNKNOWN` and rethrow at `:2252-2253`); `DigestResolver.java:77-83`; `ErrorMessage.java:459-475`; `DatabaseDescriptor.java:944-948`, `:1928-1937`; `LogFile.java:76-79`, `:545-546`; `CommitLogReader.java:452-473`; `CommitLogReplayer.java:533-546`; `CommitLog.java:576-596`; `JVMStabilityInspector.java:92-95`. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | **A single-node read deserializes the value once, in the coordinator's decode of its own replica's response** (`StorageProxy.java:2211` → `ReadResponse.createDataResponse()` → `LocalDataResponse.build()` serializes; `DigestResolver.getData():83` → `DataResponse.makeIterator()` deserializes through `Cell.deserialize():339`). So scenario C predicts: the three values held (`Memtable data size` in [3*M* + 65,537, +ε)), A read back with one trace line of *M*, B1 and B2 refused with `ServerError` (the `IOError` reaches `ErrorMessage.fromException()` on the request thread: `Unexpected exception during request`, no `CorruptSSTableException`); scenario A expects one or more (two) lines of *M*; the default arm's pre-flush read adds a line; a unit step drives `createSimpleDataResponse()` → `makeIterator()`; two conclusions rows. | Applied 2026-10-14 (9a unit and cluster bullets, Conclusions, 9c, 9e); uncommitted. Harness: "rec. 3" of the lost audit | The stage-3 claim "a read served from the memtable never deserializes a value" (§5 last bullet, §9a scenario C) is wrong; the scenario-C prediction could not hold. §5's sentence is left for stage 3 (case §10). |
| 2 | The real deserializers (`Mutation.serializer`, the local response) throw `java.io.IOError` whose cause is the guard's `IOException` (`UnfilteredRowIteratorSerializer.java:244`); check the root cause's type and message. | Applied 2026-10-14 (9a unit bullet). Harness: "rec. 2" | The written prediction named the `IOException` as the thrown type. |
| 3 | Compaction arm: 5.0 writes transaction logs, not `tmp-` files; check the listing is unchanged and has no `_txn_` file; the failed `nodetool compact` exits non-zero. | Applied 2026-10-14 (9a compaction bullet) | The written check could not fail. |
| 4 | `send-value.py` uses `FallthroughRetryPolicy`; the run script is `cluster-run.py` (Python), with a `settings` mode for 9b's secondary read. | Applied 2026-10-14 (9c) | The default policy retries a `ServerError` on the next host, which on one node surfaces as `NoHostAvailable`. |
| 5 | §5's last write-side sentence ("A read served from the memtable never deserializes a value, so it never meets the guard") and §8's "it bounds what re-reading it can allocate" should say that every client read of a value re-reads it (the local response). | Left for stage 3 (case §10 Notes) | Stage-3 text; §9 now carries the corrected prediction. |

### 1.2 Instrument checks (not readings)

`cluster-run.py instrument` (2026-10-14 11:55, first step of the run-1 chain; [`summary-instrument.txt`](max_value_size-read-maxValueSize/run1/summary-instrument.txt)): Byteman `TestScript` type-checked both rules, `TestScript: no errors`; `Submit -l` lists both rules with their trigger methods; probe over protocol 4 (`5.0.9-SNAPSHOT`); an idle 10 s left no `alloc` line; the 1,024 B and 307,200 B rows read back at their lengths, the trace has two lines of 307,200 and none of 1,024; the secondary read `system_views.settings` returns `max_value_size = 1MiB`. The unit harness was not shaken down separately: its own checks (`allocated_bytes_supported`, the read-back before any set) are its instrument checks and run inside the counted run (§4).

### 1.3 Audit erratum (found after the freeze, 2026-10-14; §9 not edited)

Rec. 1's amendment cites [`ErrorMessage.fromException():472-475`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/messages/ErrorMessage.java#L472-L475) for the pre-flush refusal. That is where the `ServerError` is built, but the `Unexpected exception during request` line is **logged by the handler** the dispatcher passes in: [`Dispatcher.java:443-444`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Dispatcher.java#L443-L444) → [`ExceptionHandlers.UnexpectedChannelExceptionHandler.apply():229-271`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ExceptionHandlers.java#L229-L271) with `alwaysLogAtError = true`, so `ErrorMessage.java:473` is not reached (the run's lines are `ExceptionHandlers.java:271`, [`guard-lines-1m.txt`](max_value_size-read-maxValueSize/run1/guard-lines-1m.txt)). Found while writing the self-check's parser, after run 1 had started. The predicted outcome (a `ServerError`, the text `Unexpected exception during request`, no `CorruptSSTableException`) is the same on both paths, so §9 is left as frozen and the citation is corrected here and in the case's §10.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-14 |
| Node (CloudLab name and type) | `pc57` (`node0.jason92-319347.misconfiguration-pg0.cloudlab.umass.edu`), 32 cores, 251 GiB |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2, `5.15.0-187-generic` |
| JDK (`java -version`) | OpenJDK 11.0.32.1 |
| Ant (`ant -version`) | 1.10.12 |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at `b5f2a54210d541339c2e7c17a794195cac0e67c2` (`cassandra-5.0.9`), harness test copied in untracked |
| Case-file commit / harness commit | `2ac7a92` + uncommitted §9 amendments (hash above) / uncommitted |
| Storage for node data | the clone's `data/` on the node's local disk |
| Full logs (path, outside the repo) | `pc57:~/stage4-logs/mvs/` (run 1); the uncounted 2026-10-13 run in `pc57:~/stage4-logs/mvs-2026-10-13/` |

## 3. Runbook defects

None. Every step of 9e ran as written (as amended at the audit); no step stopped and no tier restarted.

## 4. Run 1

**Scope:** both tiers, every value and arm of §9a: unit (harness at 1, 4, 8, 256 MiB; range controls; upstream); cluster Phase 1 at `1m`, `4m`, `8m`, `default`, the compaction arm (1 MiB), the replay arm (4 → 1 → 4 MiB). 2026-10-14 11:55–12:07 MDT, one chain (`~/stage4-harness-run/mvs-chain.sh`), [`chain.log`](max_value_size-read-maxValueSize/run1/chain.log). **Command log:** each run's `session.log` on the node; excerpts in [`max_value_size-read-maxValueSize/run1/`](max_value_size-read-maxValueSize/run1/) (`summary-<run>.txt`, `readings-<run>.csv`, `alloc-<run>.trace`, `guard-lines-<run>.txt`, `replay-*-excerpt.txt`, `unit-guard.out`, `unit.summary`).

### 4.1 Readings

**Unit tier** ([`unit.summary`](max_value_size-read-maxValueSize/run1/unit.summary), [`unit-guard.out`](max_value_size-read-maxValueSize/run1/unit-guard.out); *Δ* in bytes)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Harness `MaxValueSizeGuardTest`, all checks | **186 checks, 0 mismatches**, JUnit green | `unit.summary`, `unit-guard.out` |
| Read-back before any set; after each set | 268,435,456; equal to *M* at 1, 4, 8, 256 MiB; restored at the end | `unit-guard.out` |
| At the check, `readBuffer`, *l* = *M* | `EOFException` after *Δ* = 1,050,072 · 4,195,800 · 8,390,104 · 268,436,952 (*M* + 1,496) | `unit-guard.out` |
| At the check, *l* = *M* + 1 and 2³¹−1 | guard `IOException` with both operands, *Δ* = 2,144–2,176 | `unit-guard.out` |
| *l* = 2³¹; vint 2⁶⁴−1 | `VIntOutOfRangeException` (not an `IOException`), *Δ* = 816; `Corrupt (negative) value length encountered`, *Δ* = 720 | `unit-guard.out` |
| `readArray`, clustering site, *l* = *M* / *M* + 1 | allocated (*Δ* = *M* + 816 … *M* + 1,520) / guard (*Δ* = 2,144–2,200), at every *M* | `unit-guard.out` |
| Controls: fixed length, limit 0, skip | 4 bytes returned under limit 0; `BytesType` *l* = 1 refused with `1`/`0`; skip of *M* + 1 → `EOFException`, not the guard, *Δ* = 800 | `unit-guard.out` |
| Sibling `readWithVIntLength`, *l* = *M* + 1 | `EOFException` after *Δ* = 1,049,400 · 4,195,128 · 8,389,432 · 268,436,280 (≥ *M* + 1): **allocates for the over-limit length** | `unit-guard.out` |
| `Mutation.serializer`, *M* / *M* + 1 (1, 4, 8 MiB) | cell of *M* bytes, *Δ* = *M* + 2,496 … 2,520 / `IOError` caused by the guard, *Δ* = 8,312–8,336 | `unit-guard.out` |
| Local read response, *M* / *M* + 1 (1, 4, 8 MiB) | cell of *M* bytes, *Δ* = *M* + 920 / `IOError` caused by the guard, *Δ* = 6,480 | `unit-guard.out` |
| Live change | the same 2 MiB mutation refused under 1 MiB (guard 2097152/1048576), accepted after `setMaxValueSize(4 MiB)` (cell 2,097,152) | `unit-guard.out` |
| Range controls | `2048MiB`: `max_value_size must be smaller than 2048, but was 2048MiB`; `0MiB`: `max_value_size must be positive`; no test method ran in either | `unit.summary` |
| Upstream `SSTableWriterTest` | 5 tests, 0 failures, 0 errors, `testValueTooBigCorruption` passed | `unit.summary` |

**Cluster tier** (one node, `pc57`, `MAX_HEAP_SIZE=4G`, every start up in 40–41 s)

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| 1, 4, 8 MiB, default | control | client, trace | 1,024 and 307,200 read back; 2 trace lines of 307,200, none of 1,024; idle 10 s: no line | `summary-<v>.txt`, `alloc-<v>.trace` |
| 1 MiB | C (before flush) | writes, memtable | *M*, *M* + 1, *M* + 65,536 acknowledged; no trace line of them; `Memtable data size` 3,211,412 (band [3,211,265, 3,276,801)) | `summary-1m.txt` |
| 4 MiB | C | writes, memtable | acknowledged; no trace line; 12,648,596 ([12,648,449, 12,713,985)) | `summary-4m.txt` |
| 8 MiB | C | writes, memtable | acknowledged; no trace line; 25,231,508 ([25,231,361, 25,296,897)) | `summary-8m.txt` |
| 1 · 4 · 8 MiB | C | client, trace, log | A read back = *M* with **one** new trace line of *M*; B1 and B2 → **`ServerError`**, message `java.io.IOError: java.io.IOException: Corrupt value length <l> encountered, as it exceeds the maximum of <M>`; `system.log` `ERROR … ExceptionHandlers.java:271 - Unexpected exception during request`, no `CorruptSSTableException`; no trace line of *M* + 1 or *M* + 65,536 | `summary-<v>.txt`, `guard-lines-<v>.txt` |
| 1 · 4 · 8 MiB | flush | disk | new `Data.db` 3,211,357 · 12,648,547 · 25,231,459 B (in the 3*M* + 65,537 band) | `summary-<v>.txt` |
| 1 · 4 · 8 MiB | A (after flush) | client, trace | read back = *M*; **two** new trace lines of *M* (SSTable read + response), no other new large length | `summary-<v>.txt`, `alloc-<v>.trace` |
| 1 · 4 · 8 MiB | B | client, log, trace | B1 and B2 → **`ReadFailure`** (`UNKNOWN from localhost/127.0.0.1:7000`); `system.log` has the guard's line for each `<l>`/`<M>` inside a `CorruptSSTableException` (`JVMStabilityInspector.java:70`/`:76`, `ReadStage-1`); no trace line of *M* + 1 or *M* + 65,536 at any time | `summary-<v>.txt`, `guard-lines-<v>.txt` |
| 1 · 4 · 8 MiB | separation | client | A read back = *M* after the refused reads (the SSTable is suspect and still served) | `summary-<v>.txt` |
| 1 · 4 · 8 MiB | whole run | trace | lengths `{307200: 2, M: 5}`; 6 `^ERROR` lines, 8 lines with `Corrupt value length` | `summary-<v>.txt` |
| default | C, A | client, trace, log | 15,728,640 B acknowledged; no trace line after the write; read back whole before the flush (one trace line) and after it (one more); `Data.db` 15,728,671 B; no `Corrupt value length`, 0 `^ERROR` lines | `summary-default.txt` |
| 1 MiB | compaction | nodetool, log, listing | `compact ks1 ok` rc 0, `nb-1` → `nb-2`; 1st `compact ks1 t` **rc 2**, `CorruptSSTableException … nb-1-big-Data.db` caused by the guard (1048577/1048576) under `CompactionIterator.hasNext` → `CompactionTask.runMayThrow` → `CompactionManager$9`; listing unchanged, no `_txn_` file; 2nd `compact ks1 t` rc 0, no new guard line, listing unchanged; `readback 1` = *M* | `summary-compaction.txt`, `guard-lines-compaction.txt` |
| 4 → 1 MiB | replay | start-up, log | 2,097,152 B acknowledged and read back under 4 MiB; segment present; `kill -9`; restart under 1 MiB **exited after 13 s**; `Corrupt value length 2097152 encountered, as it exceeds the maximum of 1048576` in a `CommitLogReadException` (entry saved to `/tmp/mutation13579100519394862803dat`, 2,097,196 B); `ERROR [main] … JVMStabilityInspector.java:212 - Exiting due to error while processing commit log during initialization.`; **no `Replay stopped` line** | `summary-replay.txt`, `replay-1m-excerpt.txt` |
| 4 MiB | replay control | start-up, client | restart under 4 MiB up after 9 s, `Log replay complete, 48 replayed mutations`; `readback 30` = 2,097,152 | `summary-replay.txt`, `replay-ctl-4m-excerpt.txt` |

### 4.2 Conclusion and logic

1. **Validity** — valid. The limit read back from the first refusal equals the value set at 1, 4, 8 MiB [observed: `summary-<v>.txt` "limit read back from the first refusal"], the default run reads 268,435,456 at the unit tier [observed: `unit-guard.out`]; the known-answer row is traced and the idle trace empty [observed: `summary-instrument.txt`, `summary-<v>.txt`]; the `ks1.ok` compaction control wrote a new generation [observed: `summary-compaction.txt`]; `ThreadMXBean` allocated-bytes measurement is supported and enabled [observed: `unit-guard.out`]; the upstream baseline is green [observed: `unit.summary`]. Hold-fixed settings in force at every start: `commitlog_sync: batch`, both timeouts 10 s, both failure policies `stop`, 32 MiB segments, `-Xmx4G`, the Byteman agent [observed: `summary-<v>.txt` "yaml in force", the JVM-args check].
2. **Readings** — nothing unusual except the replay arm's missing `Replay stopped` line (part 6). Every reading equals the uncounted 2026-10-13 run's to the byte (same *Δ*, same file and memtable sizes, same trace counts) [observed: `~/stage4-logs/mvs-2026-10-13/*/summary.txt` against run 1's].
3. **Matched row** — "Unit: at every value the boundary is as predicted …, at the check and at both real deserializers, and the live change takes effect. Cluster: the largest value read back after the flush is *M* at 1, 4 and 8 MiB (1 : 4 : 8), each refused value has the guard's message in `system.log` and no `alloc` line of its length, each accepted one has `alloc` lines of its length only" → **Confirmed**. Unit: *l* = *M* allocates *M* + 816 … 1,520 and *M* + 1 allocates ≤ 2,200 at every site and every *M*; the real deserializers return *M* and refuse *M* + 1 with the guard as cause; live change as predicted [observed: `unit-guard.out`]. Cluster: largest read back after the flush 1,048,576 · 4,194,304 · 8,388,608 (1 : 4 : 8); each B refusal has the guard line with *l* and *M*; the trace has lengths 307,200 and *M* only [observed: `summary-<v>.txt`, `guard-lines-<v>.txt`, `alloc-<v>.trace`]. Also matched: the added row "values above the limit are acknowledged and held …, and every read of them fails" → **bypass as recorded** (write side; held 3*M* + 65,537 + 147 B in the memtable at each value) [observed: `summary-<v>.txt`]; "the sibling primitive allocates for the over-limit length" → **bypass as recorded** [observed: `unit-guard.out`]; "the node does not start and the log shows the message" → **refusal as traced** [observed: `replay-1m-excerpt.txt`].
4. **Excluded rows** — *Refuted* (a refused length allocates): no unit *Δ* ≥ *M* on a refusal (max 8,336) and no `alloc` line of *M* + 1 or *M* + 65,536 in any run [observed: `unit-guard.out`, `alloc-<v>.trace`]. *Refuted* (exact limit refused / read back below *M*): *M* passes at every site and value [observed: same]. *Refuted* (same ceiling at every *M*): 1 : 4 : 8 [observed: `summary-<v>.txt`]. *Not confirmed* (refusal lacks the guard's message / another exception): every refusal carries it [observed: `guard-lines-<v>.txt`]. *Refuted in part* (sibling refused with the guard, or fixed-length or skip refused): neither [observed: `unit-guard.out`]. *Refuted in part* (A unreadable after B, or a write refused): A read back after B; every write acknowledged [observed: `summary-<v>.txt`]. *Refuted in part* (B1/B2 read back whole before the flush): both `ServerError` [observed: `summary-<v>.txt`]. The stage-3 row "read back whole before the flush … fail only after it" cannot match for the same reason (superseded at the audit). *Not confirmed* (compaction succeeds, or the 2nd fails again with the guard): rc 2 then rc 0 with no new guard line [observed: `summary-compaction.txt`]. *Refuted in part* (replay under 1 MiB starts): it exited [observed: `summary-replay.txt`]. *Invalid run*: none of its conditions (part 1).
5. **Observed vs. inferred** — (a) The second `compact ks1 t` started no task **because the SSTable is suspect** [inferred: rc 0, no new guard line and no `Compacted` line, as `filterSuspectSSTables()` predicts; the suspect flag itself is not read]. (b) Scenario A's two trace lines per read are the SSTable read and the response decode [inferred: two lines of *M* per accepted read after the flush and one before it; of the five lines of *M* per run, two are on `ReadStage-*` (the SSTable reads) and three on `Native-Transport-Requests-*` (the coordinator's decodes), `alloc-<v>.trace`]. (c) The node's heap holds no refused array [inferred from the trace: requests, not residency; 9d names the gap]. (d) The replay process exit is the commit-log handler's [observed: `Exiting due to error while processing commit log during initialization` at `JVMStabilityInspector.java:212`].
6. **Deviations and gaps** — **One sub-prediction missed:** the replay arm's log has no `Replay stopped. If you wish to override this error` line. Source, read after the reading: `CommitLogReplayer.shouldSkipSegmentOnError():539` calls `CommitLog.handleCommitError()`, whose first statement `JVMStabilityInspector.inspectCommitLogThrowable()` (`CommitLog.java:578`, `JVMStabilityInspector.java:92-95`) reaches `inspectCommitLogError()` (`JVMStabilityInspector.java:208-213`), which, while `isDaemonSetupCompleted()` is false, logs the line seen (`:212`) and kills the JVM (`:213`), so `:541` is never reached. The outcome the row decides on (the node does not start; the guard's message in the log) holds; the miss is in §6b's description of the path, recorded for stage 3 (case §10), and §9a is not edited. The node heap is not measured (9d). *N* > 1, the inbound-message, hints, streaming, batchlog and read-repair consumers, and sites 3–4 are not covered (case §11). The audit's citation erratum (§1.3) changes no prediction.
7. **Core question** — Logic (1): the limit read back equals the value set (part 1). (2) A length of exactly the limit passes the guard and allocates its array; one byte more is refused with the guard's message and allocates nothing, at the check, the array path, the clustering site and both real deserializers (part 3): usage stops at the limit. (3) The largest value read back after the flush is 1 : 4 : 8 across the values (part 3): usage follows the constraint. (4) The over-limit values are accepted and held by the write side, and the sibling primitive allocates for the same length (part 3): the recorded bypasses, but the memtable read meets the guard too (the audit's rec. 1). (5) A failed read leaves the other value readable, a compaction of the SSTable fails and leaves the file, and a replay under a lower limit stops the node starting (parts 3, 6): the refusal acts as corruption. **`max_value_size` caps the array of every deserialized value, one for one with the knob, and caps nothing on the write side.**

**Conclusion (one line):** Confirmed (unit and cluster); write side and sibling primitive bypass as recorded; compaction and replay refusal as traced; one replay sub-prediction (the `Replay stopped` line) not borne out.

## 5. Self-check of run 1 — AI

Independent script [`run1/selfcheck.py`](max_value_size-read-maxValueSize/run1/selfcheck.py) (written 2026-10-14 before run 1's readings were read; its parser was tested on the uncounted 2026-10-13 logs, format only). It re-parses `guard.out`, the JUnit XML, and per run the client lines of `session.log`, `alloc.trace`, the copied `system.log` (entries timed in UTC and assigned to client calls by time), and the raw `nodetool tablestats` output; it never reads `summary.txt` or `readings.csv`. **Result: 188 of 189 checks hold** ([`selfcheck.out`](max_value_size-read-maxValueSize/run1/selfcheck.out)); the one failure is the replay sub-prediction of part 6. Its parser found two bugs of its own on the format test (it expected five reads after the flush instead of four, and the JUnit test names carry a `-_jdk11` suffix), fixed before it was run on run 1.

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out` "limit read back from the refusals = M" at 1/4/8 MiB, instrument checks, control rows, compaction control, upstream green; yaml lines re-read in `summary-<v>.txt`. |
| 2. Readings | yes | Run-1 and 2026-10-13 summaries compared line by line for the figures in §4.1: identical. |
| 3. Matched row | yes | Re-derived by the self-check from raw files: unit *Δ* bands at every *M*, 1 : 4 : 8, guard operands per refusal, trace lengths. |
| 4. Excluded rows | yes | Each excluding reading is a self-check line (`no trace line of M+1 or M+65536`, `ServerError` before the flush, compaction rc, replay `exited`). |
| 5. Observed vs. inferred | yes | (a) and (b) are inferences consistent with the raw files and do not decide the row; (c) is the named gap; (d) re-read in `replay-1m-excerpt.txt`. |
| 6. Deviations and gaps | yes | The replay miss is the self-check's one failure; source lines re-read (`CommitLog.java:576-596`, `JVMStabilityInspector.java:92-95`, `:208-213`, `CommitLogReplayer.java:533-546`). |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | Logic (1)–(5) of §9a, each with its part. |

### 5.2 Run 2?

**No** — 2026-10-14. The conclusion rests on observed readings (the inferences in part 5 do not decide any row), the self-check settles every part from run 1's raw files, the result neither refutes the case nor confirms a new bypass (both bypasses were recorded at stage 3), and the uncounted 2026-10-13 run with the same harness gave the same figures to the byte.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

| Tier | Verdict (§9a row) | Basis | Date |
|---|---|---|---|
| Unit | **Confirmed** (boundary exact at 1, 4, 8, 256 MiB at the check, `readArray`, the clustering site, `Mutation.serializer` and the local read response; live change; range and upstream controls); sibling primitive **bypass as recorded** | run 1 + self-check | 2026-10-14 |
| Cluster | **Confirmed** (1 : 4 : 8; guard on every refusal; no array of a refused length); write side **bypass as recorded** (held in the memtable, refused on every read, before the flush as `ServerError`, after it as `ReadFailure`); compaction **refusal as traced** (suspect SSTable left on disk, not compacted again); replay **refusal as traced** (the node does not start under the lower limit), with the `Replay stopped` sub-prediction **not borne out** | run 1 + self-check | 2026-10-14 |

**Feedback filed:** the case file's §10 "Stage-4 feedback" and "Notes" (2026-10-14, uncommitted): the memtable-read claim of §5 and §8 (rec. 5), the replay path of §6b (no `Replay stopped`: the JVM is killed at `JVMStabilityInspector.java:212` first), the logging site of a pre-flush refusal (§1.3), and Target-3 material (the bytes held above the limit; the client sees a `ServerError` before a flush and a `ReadFailure` after it). §9 is not edited after the freeze. Also recorded: the uncounted 2026-10-13 run (§1 "Provenance").
