# max_value_size-applySimpleConfig-max_value_size--autonomous — stage-4 results  <!-- file: results/max_value_size-applySimpleConfig-max_value_size--autonomous.md -->

> **Case:** [`max_value_size-applySimpleConfig-max_value_size--autonomous`](../../stage3-ai-deep-read/cases/max_value_size-applySimpleConfig-max_value_size--autonomous.md)
>
> **Status:** verdict filed, 2026-10-25. **Unit: Confirmed — caps** (B2g row 1. ConfigProbe: `0MiB` and `2048MiB` refused with the traced messages, `1MiB` / `2047MiB` / unset read back as 1,048,576 / 2,146,435,072 / 268,435,456. At V = 1 MiB, 4 MiB and the default 256 MiB, lengths V − 1 and V were returned with Δ = len + 64 B, and V + 1 (and 64 MiB at 1 and 4 MiB) was refused with the guard's exact `IOException` and Δ = 2,144–2,176 B. The same streams read with limit `Integer.MAX_VALUE` were allocated). **Cluster: Confirmed — caps** (read side; B3g row 1. `0MiB` and `2048MiB` stopped start-up with rc 3. Seven values of 512 KiB to 12 MiB were written under the default and flushed. After drain and restart, the largest value read back was 1,048,576 B at `1MiB`, 8,388,608 B at `8MiB` and 12,582,912 B at the default. That is exact at both boundaries: V passes, V + 1 is refused. Each refused read was a `ReadFailure`, logged with the guard's message carrying l and V inside a `CorruptSSTableException`, and Byteman saw no array of a refused length. The default-value control read all 8 values back with equal sha256). Write side **bypass as recorded**: under `1MiB` a 2 MiB insert was acknowledged and its read refused (`ServerError`, the guard's message). No run 2.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/max_value_size-applySimpleConfig-max_value_size--autonomous/`](../harness/max_value_size-applySimpleConfig-max_value_size--autonomous/).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-25, on the advisor's machine (`environment-advisor.md`).
> The verdict is against this file's own predictions and conclusions. Copied unchanged: `ConfigProbe.java` (from the `max_mutation_size-applySimpleConfig` harness)
> and `value-alloc.btm` (from the `max_value_size-read-maxValueSize--guided` harness). `unit-run.sh` and `cluster-run.sh` were adapted
> from the `max_mutation_size-applySimpleConfig` harness (copied, then changed). No reading from another case is used here.

**What the constraint is (kept apart throughout).** `max_value_size` (V) is a **read-side** corruption guard. When a variable-length value
is deserialized, its declared length *l* is compared with V before the value's array is allocated. If *l* > V, an `IOException` is thrown
instead (`AbstractType.java:590-599`). Nothing on the write path consults it. A value larger than V can therefore be written, and is held in the
memtable and on disk. What the guard caps is the heap array that one deserialized value can claim. In this file, "caps" means "caps the
array a single value read can allocate".

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `0dcdfe0` (DD batch 2). Before the audit, sha256 `b2c8bf79…c43c` was checked equal to the filed §2 row. The step-0 audit made eighteen amendments (2026-10-25, before any harness run or reading), and the file was frozen at sha256 **`e1376b72544b7e9a6e61a487d8c736dca64120ee4bbd6f590fe4e5b0292766ee`**. That hash is a new row in `_INDEX.md` §4. It was re-checked unchanged before the unit run and after both tiers. Both tiers' run 1 ran at this version, and no runbook fix was needed. Section D was filled after the hash. Nothing is committed (no commit was asked for); base commit `a10cac5`. |
| **Harness** | [`../harness/max_value_size-applySimpleConfig-max_value_size--autonomous/`](../harness/max_value_size-applySimpleConfig-max_value_size--autonomous/):<br>• `ConfigProbe.java` (copied unchanged)<br>• `ValueReadProbe.java`: the B2 mechanism. Plain `java`, one JVM per V. Measures thread-allocated bytes across each `BytesType.readBuffer` call only.<br>• `unit-run.sh`<br>• `value-alloc.btm`: Byteman entry rules at `ByteArrayAccessor.read(DataInputPlus,int)` and `ByteBufferUtil.read(DataInput,int)` for lengths ≥ 262,144 (copied unchanged)<br>• `mvsclient.py`: bundled driver, protocol 5, `FallthroughRetryPolicy`, random values with sha256<br>• `cluster-run.sh`<br>• `selfcheck.py` (independent)<br>**Instrument checks before run 1:** `bash -n` and `ast.parse` passed. The **unit shakedown** (one JVM at V = 2 MiB, not an arm value; [`shakedown/unit-shakedown-summary.txt`](max_value_size-applySimpleConfig-max_value_size--autonomous/shakedown/unit-shakedown-summary.txt)) gave Δ = len + 64 for accepted lengths and Δ = 2,144 / 2,152 for refused ones, inside both frozen bands ([len, len + 65,536) and < 65,536). The **cluster shakedown** `sd` ([`shakedown/cluster-shakedown-summary.txt`](max_value_size-applySimpleConfig-max_value_size--autonomous/shakedown/cluster-shakedown-summary.txt)) found the following:<br>• Byteman `TestScript: no errors`, and `Submit -l` lists both rules.<br>• One 307,200 B value gave 1 `alloc` line on a read before the flush and 2 after it.<br>• After drain, the commit-log directory holds one segment, and the restart logs `Log replay complete, 0 replayed mutations`, so (iv) is reachable.<br>No bound was changed. |
| **Tiers and values** | **Unit (B2):**<br>• ConfigProbe `0MiB`, `1MiB`, `2047MiB`, `2048MiB`, unset.<br>• ValueReadProbe V = `1MiB`, `4MiB`, unset (256 MiB), with lengths V − 1, V, V + 1 and 64 MiB, plus the `Integer.MAX_VALUE` controls.<br>**Cluster (B3):** one node, 2 GiB heap, Byteman agent on every start.<br>• `z0` and `z2048` (start-up refusals).<br>• `p1`: write under the default. Seven values: 524,288; 4,194,304; 12,582,912; 1,048,576; 1,048,577; 8,388,608; 8,388,609 B.<br>• `r1` / `r8` / `r256`: restarts on the same data at `1MiB` / `8MiB` / default; `r256` is the control.<br>• In `r1`, a 2,097,152 B insert under `1MiB`. |
| **Audit bottom line** | **Ready after amendments**, 2026-10-25. |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Estimate, A2: the heap array allocated for one deserialized value. |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly → Met after amendment | Filed unit tier: V ∈ {1, 4} MiB; ConfigProbe without the default. Amendments B2b add the default 256 MiB to both. Cluster: {1, 8, 256 (default, control)} MiB, already three. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | Filed: `Runtime` used-heap delta (coarse) and `jcmd GC.heap_info` / humongous logging, which cannot attribute one array to one read. Replaced by thread-allocated bytes across the call (B2d) and Byteman array requests at the allocation sites (B3a, B3d). Gap: the node's heap residency is not measured. |
| A. Core question | usage driven to the limit and past it | Partly → Met after amendment | Unit: V − 1, V, V + 1, 64 MiB. Cluster: the filed 512 KiB / 4 MiB / 12 MiB do not test the boundary. Amendment B3c adds V and V + 1 for both V (k = 4–7). |
| B. Logic | each step says what it establishes | Partly | B2e and B3e list steps without saying what each establishes; the readings tables carry the meaning. Left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | Exact messages, byte bands and per-key outcomes added (B2f, B3f). |
| B. Logic | every plausible outcome has a conclusions row | Not met → Met after amendment | B2g and B3g had three rows each, with no Invalid, Not confirmed or exact-limit-refused row. Rows added (B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The ceiling is shown by the largest value read back at each V. The disallow branch is shown by the guard's message with l and V, plus no array of the refused length. |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | **Data damage:** the `r256` control now also checks sha256 equality. **Another limit:** every value fits `max_mutation_size` and the native message limit (A3 amendment). **Commit-log replay:** drain, the start-up check (iv), and the Invalid row. **Instrument failure:** an accepted read must leave a trace line. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Added the read paths with what each produces (A3 amendment). The filed text did not say how a stop affects replay, nor what a refusal looks like at the client. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | The filed `SELECT * FROM ks.t` had no prediction, and the stop method, timeouts and driver retry policy were not stated (B3c–B3f). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met after amendment | The `/local/...` paths were replaced by this host's clone `cassandra-run20` (`build-test`), `$W/probe-mvs` and `$W/node-mvs` (B2a, B3a, B4). |
| D. Runnable | workload arithmetic reaches the limit | Met | The largest write is 12,582,912 B (+ about 50 B of mutation overhead), under `max_mutation_size` = 16,777,216 B (32 MiB segment / 2) and under the default `native_transport_max_message_size` = min(16 MiB, heap/10, heap/40) = 16,777,216 B at 2 GiB (`DatabaseDescriptor.java:649-656, 898-905, 3237-3244`). The 16 MiB frame limit is pre-v5 only. No limit had to be raised. Data about 38 MB; unit heap ≤ 3 GiB. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked in `~/cassandra-src` at `cassandra-5.0.9` (A3 amendment):<br>• `DatabaseDescriptor.java:944-948, 1928-1937`, `Config.java:305-310`<br>• `AbstractType.java:565-600`, `ByteBufferAccessor.java:100-103`, `ByteArrayAccessor.java:100-105`, `ByteBufferUtil.java:444-452`<br>• `Cell.java:307-342`, `AbstractSSTableIterator.java:401-433`<br>• `StorageProxy.java:2195-2253`, `DigestResolver.java:77-83`, `UnfilteredRowIteratorSerializer.java:236-246`<br>• `DefaultFSErrorHandler.java:44-58`, `CompactionController.java:318`, `AbstractCompactionStrategy.java:240`<br>• `CommitLogReplayer.java:150-186, 376-382`, `CommitLogReader.java:292-299, 415-480`<br>• `StorageService.java:5840-5970`, `AbstractCommitLogSegmentManager.java:357-397`<br>• `CassandraDaemon.java:740-768`, `conf/cassandra.yaml:471, 1322-1330, 1864` |

**How an over-limit value reaches a read, which read checks it, and what each produces** (the audit's A3 statement; §4 confirms rows 1–2):

| Path | Where the guard runs | Reached here by | When l > V |
|---|---|---|---|
| SSTable read | `Cell.deserialize():339` in the SSTable row iterator | a value written under the default and flushed, read after a restart under a smaller V | `CorruptSSTableException` (`AbstractSSTableIterator.java:411/432`), SSTable marked suspect (compaction only). `LocalReadRunnable` reports `UNKNOWN` and rethrows (`StorageProxy.java:2243-2253`). Client sees `ReadFailure`; `ERROR` logged; `disk_failure_policy: stop` takes no action |
| Coordinator decode of the local response | `DigestResolver.getData():83` → `makeIterator` → `Cell.deserialize` | a value still in the memtable (written under the smaller V) | `IOError` (`UnfilteredRowIteratorSerializer.java:244`). Client sees `ServerError`; logged by the request handler |
| Commit-log replay | `CommitLogReader.readMutation():431` | a segment holding an over-limit mutation, after the global replay position | `handleUnrecoverableError`, so the node does not start. Avoided here by `nodetool drain` (recycles every segment) |
| Internode, hints, batchlog, streaming; clustering, partition key | the same `Cell.deserialize` / `readArray` / `readBuffer` | not reachable on one node; this table has an `int` key and no clustering column | not tested |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | A3: read paths, how an over-limit value gets onto disk, which write-side limits must admit it | Amendment 2026-10-25 (audit statement; no claim changed) | The brief and group C: the filed text did not say how a stop affects replay, nor what each path produces. |
| 2 | B2a: this host; `ValueReadProbe` as plain `java`, one JVM per V | Amendment 2026-10-25 | Paths; `daemonInitialization()` runs once per JVM. |
| 3 | B2b: add the default (unset) to ConfigProbe and ValueReadProbe | Amendment 2026-10-25 | Group A. |
| 4 | B2c: build the stream before the measurement; unrecorded warm-up | Amendment 2026-10-25 | Δ must exclude the input and class loading. |
| 5 | B2d: thread-allocated bytes per call; `Runtime` delta as INFO | Amendment 2026-10-25 | Real resource. |
| 6 | B2e: order and timeout | Amendment 2026-10-25 | Exactness. |
| 7 | B2f: exact messages and Δ bands | Amendment 2026-10-25 | Group B. |
| 8 | B2g: verdict rows | Amendment 2026-10-25 | Group B. |
| 9 | B2h: control on the V + 1 and 64 MiB streams | Amendment 2026-10-25 | Group B. |
| 10 | B3a: this host; timeouts 10 s; the Byteman instrument; `FallthroughRetryPolicy`; no limit to raise | Amendment 2026-10-25 | Real resource; exactness. |
| 11 | B3b: starts `z0`, `z2048`, `p1`, `r1`, `r8`, `r256`; shakedown `sd` | Amendment 2026-10-25 | Exactness; the control as the third value. |
| 12 | B3c: random values with sha256; boundary keys 4–7; the whole-table read predicted; the k = 8 write under `1MiB` (filed row 3 "if tried") | Amendment 2026-10-25 | Limit and boundary; data integrity; the write-side row made decidable. |
| 13 | B3d: observables; `jcmd` / humongous logging dropped | Amendment 2026-10-25 | They cannot attribute one array to one read. |
| 14 | B3e: drain before each stop; start checks | Amendment 2026-10-25 | Replay (A3 row 3). |
| 15 | B3f: exact (i)–(viii) | Amendment 2026-10-25 | Group B. |
| 16 | B3g: verdict rows | Amendment 2026-10-25 | Group B. |
| 17 | B3h: sha256 equality and the 8-row whole-table read | Amendment 2026-10-25 | Group B. |
| 18 | B4: this host's cleanup | Amendment 2026-10-25 | `/local` paths. |
| 19 | B2e/B3e steps do not say what each establishes; internode, hints and streaming paths and the clustering / key sites are untested | Left for stage 3 | Not needed for a valid run. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-25 (unit 17:28–17:28:38, cluster 17:31:17–17:32:39 EDT) |
| Node | `yangwang-mbp` (advisor's laptop), 10 cores (Apple T6000, arm64), 32 GiB |
| OS and kernel | macOS 27.0.1 (26A434) / Darwin 27.0.0 |
| JDK | OpenJDK 11.0.32.1 (Homebrew) |
| Ant | 1.10.18 |
| Local clone commit | `$W/cassandra-run20` at `b5f2a54210d541339c2e7c17a794195cac0e67c2` (`cassandra-5.0.9`); `ant build-test` succeeded in 55 s; no file added to the clone; test yaml untouched (`git status` clean) |
| Case-file commit / harness commit | `0dcdfe0` + uncommitted amendments (sha256 above) / uncommitted |
| Storage for node data | internal APFS SSD, `$W/node-mvs` (wiped at the end); 143 GiB free before and after |
| Re-checked at step E | free disk 143 GiB; ports 7000, 7199, 9042, 9091 free; loopback 127.0.0.1–.3 present; no `CassandraDaemon` |
| Full logs | `~/Library/Caches/stage4/logs/max_value_size-applySimpleConfig/` (`unit-run1/`, `cluster-run1/`, shakedowns, `selfcheck.out`, `build-test.log`) |

## 3. Runbook defects

None. Every step of B2e and B3e ran as written (as amended at the audit).

**Not a defect (no reading):** the first launch of `cluster-run.sh run1` (17:29:15) stopped at its own pre-check with `ABORT: a Cassandra node is running`.
The launching shell's command line contained the literal word, so the bracketed `ps` grep matched the launcher itself (the pitfall noted
in the brief). No node had started and nothing had been read. The folder is kept as `cluster-run1.attempt-1792963877/`, and the run was relaunched without the word.

## 4. Run 1

**Scope:** both tiers, every value and start of B2b and B3b. **Command log:** `unit-run1/commands.log` and `cluster-run1/commands.log`.
Excerpts are in [`max_value_size-applySimpleConfig-max_value_size--autonomous/run1/`](max_value_size-applySimpleConfig-max_value_size--autonomous/run1/):
- `unit/summary.txt` and `unit/p[12]-*.lines.txt`
- `cluster/summary.txt` and `cluster/req.txt`
- `cluster/alloc-<start>.trace` and `cluster/guard-lines-<start>.txt`
- `cluster/refusal-z*.txt`
- `cluster/corrupt-sstable-excerpt-r1.txt` and `cluster/memtable-read-excerpt-r1.txt`
- `selfcheck.out`

### 4.1 Readings

**Unit tier** ([`unit/summary.txt`](max_value_size-applySimpleConfig-max_value_size--autonomous/run1/unit/summary.txt); Δ = bytes allocated by the thread across the call)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| ConfigProbe `0MiB` | `REJECT ConfigurationException: max_value_size must be positive` | `unit/p1-0MiB.lines.txt` |
| ConfigProbe `2048MiB` | `REJECT ConfigurationException: max_value_size must be smaller than 2048, but was 2048MiB` | `unit/p1-2048MiB.lines.txt` |
| ConfigProbe `1MiB` / `2047MiB` / unset | `OK getMaxValueSize=1048576` / `=2146435072` / `=268435456` | `unit/p1-*.lines.txt` |
| Read-back, measurement | V = 1,048,576 / 4,194,304 / 268,435,456; `allocSupported=true allocEnabled=true` | `unit/p2-*.lines.txt` |
| len = V − 1 and V | returned, `remaining` = len, Δ = len + 64 at every V | `unit/p2-*.lines.txt` |
| len = V + 1 | `java.io.IOException`, message exactly `Corrupt value length <V+1> encountered, as it exceeds the maximum of <V>, which is set via max_value_size in cassandra.yaml`; Δ = 2,144 (1, 4 MiB) / 2,176 (256 MiB) | `unit/p2-*.lines.txt` |
| len = 64 MiB | refused with the exact message, Δ = 2,152 (V = 1, 4 MiB); returned, Δ = 67,108,928 (V = 256 MiB, below V) | `unit/p2-*.lines.txt` |
| Control: limit `Integer.MAX_VALUE` | V + 1 returned, Δ = V + 72; 64 MiB returned, Δ = 67,108,928 at every V | `unit/p2-*.lines.txt` |
| INFO `Runtime` used delta | 0 on every refusal; ≈ len to 2 × len on accepted calls (coarse) | `unit/p2-*.lines.txt` |

**Cluster tier** (one node, 127.0.0.1, `MAX_HEAP_SIZE=2G`; starts up in 5–10 s; [`cluster/summary.txt`](max_value_size-applySimpleConfig-max_value_size--autonomous/run1/cluster/summary.txt), [`cluster/req.txt`](max_value_size-applySimpleConfig-max_value_size--autonomous/run1/cluster/req.txt))

| Capacity value | Start | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| `0MiB` | z0 | exit, output | rc 3 after 2 s, no `Startup complete`; `Exception (…ConfigurationException) encountered during startup: max_value_size must be positive` | `summary.txt`, `refusal-z0.txt` |
| `2048MiB` | z2048 | exit, output | rc 3 after 2 s; `… max_value_size must be smaller than 2048, but was 2048MiB` | `summary.txt`, `refusal-z2048.txt` |
| default | p1 | settings, writes, disk, trace | `256MiB`; all seven inserts acknowledged; after `flush ks t`, `nb-1-big-Data.db` = 36,339,486 B (the values are on disk); no `alloc` line (the write path allocates nothing at the read sites); commit-log replay at later starts: `0 replayed mutations` | `summary.txt`, `req.txt`, `alloc-p1.trace` (empty) |
| `1MiB` | r1 | settings, start-up | `1MiB`; `Startup complete`, `Log replay complete, 0 replayed mutations`, no guard line before it | `summary.txt` |
| `1MiB` | r1 | reads | k = 1 (524,288) and k = 4 (1,048,576) read back whole, sha256 equal. k = 5 (1,048,577), k = 6, k = 7, k = 2, k = 3 each gave `ReadFailure` (code 1300, `UNKNOWN from /127.0.0.1:7000`). Whole-table read: `ReadFailure` | `req.txt` |
| `1MiB` | r1 | log | For each refused l, `Caused by: java.io.IOException: Corrupt value length <l> encountered, as it exceeds the maximum of 1048576`. The line sits under `CorruptSSTableException` at `AbstractSSTableIterator$AbstractReader.hasNext(AbstractSSTableIterator.java:411)`, thread `ReadStage-*`; 14 guard lines, 13 `^ERROR` | `guard-lines-r1.txt`, `corrupt-sstable-excerpt-r1.txt` |
| `1MiB` | r1 | trace | `alloc` lengths {524,288 × 2; 1,048,576 × 2}, i.e. 2 per accepted read. **No line of any refused length** | `alloc-r1.trace` |
| `1MiB` | r1 write side | client, log, trace | The k = 8 insert of 2,097,152 B was **acknowledged** under `1MiB`. Its read gave `ServerError`: `java.io.IOError: java.io.IOException: Corrupt value length 2097152 encountered, as it exceeds the maximum of 1048576`, from `ExceptionHandlers.java:271` on `Native-Transport-Requests-3` via `UnfilteredRowIteratorSerializer.java:244`. No `alloc` line of 2,097,152 | `req.txt`, `memtable-read-excerpt-r1.txt`, `alloc-r1.trace` |
| `8MiB` | r8 | settings, start-up | `8MiB`; `Startup complete`, 0 replayed mutations | `summary.txt` |
| `8MiB` | r8 | reads | k = 1, 2, 4, 5 (1,048,577), 6 (8,388,608) and 8 read back whole, sha256 equal. k = 7 (8,388,609) and k = 3 gave `ReadFailure`. Whole-table read: `ReadFailure` | `req.txt` |
| `8MiB` | r8 | log, trace | Guard lines for (8388609, 8388608) and (12582912, 8388608); 6 guard lines. Trace: 2 lines per accepted read, plus partial lines from the whole-table read. **No line of 8,388,609 or 12,582,912** | `guard-lines-r8.txt`, `alloc-r8.trace` |
| default | r256 (control) | reads, log, trace | All 8 values read back whole with sha256 equal. Whole-table read returned 8 rows with the written lengths. No guard line, 0 `^ERROR`. Trace: 4 lines of each length (2 per single read + 2 in the whole-table read), including 12,582,912 | `req.txt`, `summary.txt`, `alloc-r256.trace` |
| all | ceiling | largest value read back | 1,048,576 (r1) · 8,388,608 (r8) · 12,582,912 (r256, all values) | `req.txt` |

### 4.2 Conclusion and logic

1. **Validity.** Valid.
   - The settings read back equal the values set: `256MiB`, `1MiB`, `8MiB`, `256MiB` [observed: `req.txt` `op=settings`].
   - Every `p1` insert was acknowledged, so the limit was reached and passed [observed: `req.txt`].
   - Every phase-2 start completed with 0 replayed mutations and no guard line before `Startup complete` [observed: `summary.txt` STARTUP lines].
   - The `r256` control read every value back intact (sha256) [observed: `req.txt`].
   - Every accepted read left trace lines, and the Byteman agent was on every phase-2 JVM [observed: `summary.txt` `byteman_agent=1`, `alloc-*.trace`].
   - Unit: thread-allocation measurement was supported and enabled, and the controls allocated ≥ len [observed: `unit/p2-*.lines.txt`].
   - Held fixed at every start: the three 10 s timeouts, `num_tokens: 1` [observed: `summary.txt` YAML lines]; the clone at `b5f2a54` [observed: `summary.txt`].
2. **Readings.** Nothing unusual. The whole-table read at r8 left partial trace lines of the accepted lengths before it failed. This was expected: it scans in token order [observed: `alloc-r8.trace`, counts 3 for the lengths of keys 1, 2, 4, 5, 8; inferred: the scan reached those partitions before k = 3 or k = 7].
3. **Matched row.**
   - Unit — B2g "**Confirmed — caps**: the five ConfigProbe lines as in B2f, and in every ValueReadProbe JVM (i)–(iv) hold and the B2h controls allocate". The five lines match exactly. At each V, V − 1 and V returned with Δ = len + 64 ∈ [len, len + 65,536). V + 1 (and 64 MiB below the default) was refused with the exact message and Δ ≤ 2,176 < 65,536. The largest Δ was V + 64 < V + 65,536. The controls returned with Δ ≥ len [observed: `unit/p*-*.lines.txt`].
   - Cluster — B3g "**Confirmed — caps** (read side): (i)–(v), (vii), (viii) hold and the B3h control holds":
     - (i) rc 3 with both messages [observed: `summary.txt`, `refusal-z*.txt`].
     - (ii) settings [observed: `req.txt`].
     - (iii) seven inserts acknowledged [observed: `req.txt`].
     - (iv) starts [observed: `summary.txt`].
     - (v) r1 accepts exactly k = 1, 4 and refuses k = 5, 6, 7, 2, 3 and the whole-table read, as `ReadFailure` with the guard's (l, 1048576) lines [observed: `req.txt`, `guard-lines-r1.txt`].
     - (vii) r8 accepts k = 1, 2, 4, 5, 6, 8 and refuses k = 7, 3 and the whole-table read with (l, 8388608) [observed: `req.txt`, `guard-lines-r8.txt`].
     - (viii) at least one (in fact 2) `alloc` line of the exact length per accepted read. No line of any length refused from the SSTable at any time in r1 or r8, and none of 2,097,152 in r1 [observed: `alloc-r1.trace`, `alloc-r8.trace`; `selfcheck.out`].
     - B3h: 8/8 values intact, whole-table read 8 rows, no guard line [observed: `req.txt`, `summary.txt`].
     - Ceiling: 1,048,576 → 8,388,608 → 12,582,912 [observed: `req.txt`].
   - Write side — filed B3g row 3, as amended: "acknowledged and then unreadable at r1 → **bypass as recorded**". (vi) k = 8 (2,097,152 B) was acknowledged under `1MiB`. Its read failed with `ServerError` carrying the guard's message (2097152, 1048576) [observed: `req.txt`, `memtable-read-excerpt-r1.txt`].
4. **Excluded rows.**
   - Unit **Refuted**: no len > V was returned, and no refusal had Δ ≥ len (max 2,176). V itself was returned at every V [observed: `unit/p2-*.lines.txt`].
   - Unit **Refuted (start-up)**: 0 and 2048 were refused; 1 and 2047 were accepted [observed: `unit/p1-*.lines.txt`].
   - Unit **Not confirmed**: every refusal carried the guard's `IOException` with the exact message [observed: same].
   - Unit **Invalid**: none of its conditions held (part 1).
   - Cluster **Refuted**: no over-limit value was returned at r1 or r8 (12 MiB at `8MiB` failed). k = 4 (= V) at r1 and k = 5, 6 at r8 were returned. No `alloc` line of a refused length appeared [observed: `req.txt`, `alloc-r*.trace`].
   - Cluster **Refuted (start-up)**: `z0` and `z2048` did not start [observed: `summary.txt`].
   - Cluster **write side consults it**: the k = 8 insert was acknowledged [observed: `req.txt`].
   - Cluster **Not confirmed**: every refusal carried the guard's message, and the ceiling followed both values [observed: `guard-lines-r*.txt`, `req.txt`].
   - Cluster **Invalid**: settings equal, inserts acknowledged, starts clean, control intact, trace present (part 1).
5. **Observed vs. inferred.**
   - (a) The two `alloc` lines per accepted read are the SSTable read and the coordinator's decode of the local response [inferred: A3 rows 1–2. One line per read before the flush and two after it in the shakedown; the trace's thread names split 16 `ReadStage-*` / 16 `Native-Transport-Requests-*` in `alloc-r256.trace`]. It decides nothing: the rows need "≥ 1".
   - (b) No array of a refused length was allocated [observed at the two traced allocation sites, which are the only ones `AbstractType.read():599` reaches through `ByteBufferAccessor` / `ByteArrayAccessor`]. Residency in the node's heap is not measured (named gap).
   - (c) The 36,339,486 B `Data.db` holds the over-limit values [inferred: random data does not compress, and the file is 163,612 B larger than the 36,175,874 B of values written; INFO only].
6. **Deviations and gaps.**
   - The node heap is not measured; the trace shows array requests, not residency.
   - Internode messages, hints, batchlog and streaming, the clustering and partition-key sites, and commit-log replay under a smaller V are not exercised on one node. Replay was avoided by drain; the guided case's replay arm covers it.
   - The first launch aborted at its own pre-check before any start (§3).
   - The self-check reads the refusal exit codes from `commands.log`, the runner's record of the `bin/cassandra` exit status; no other file holds them.
7. **Core question.**
   - A length equal to V passes the guard and allocates its array; one byte more is refused and allocates nothing. This holds directly at the unit tier (Δ = 2.1 KB against len + 64), and on a real node at both boundaries (parts 3 and 4).
   - The largest value a read can return follows the knob: 1 MiB, 8 MiB, and everything at the default, from the same SSTable (part 3).
   - The over-limit values are on disk and intact (control) and can still be written while the smaller limit is in force (k = 8). So the guard caps the **read**, not what is stored.
   - **`max_value_size` caps the heap array of every deserialized value, one for one with the knob. It caps nothing on the write side.**

**Conclusion (one line):** Unit B2g row 1 and cluster B3g row 1 — **Confirmed — caps** (read side); write side **bypass as recorded** (B3g row 3).

## 5. Self-check of run 1 — AI

Independent script [`harness/.../selfcheck.py`](../harness/max_value_size-applySimpleConfig-max_value_size--autonomous/selfcheck.py). It was written before the cluster run's readings were read. It re-parses the raw files and never reads `summary.txt`:
- unit: `p1-<v>.out`, `p2-<v>.out`;
- cluster: `req.txt` and `written.json`;
- per start: `system.log`, `node.out` and `alloc.trace`, with trace lines assigned to requests by the client's epoch-ms window ± 50 ms.

It re-derives every B2f and B3f clause. **Result: 84 of 84 checks hold** ([`run1/selfcheck.out`](max_value_size-applySimpleConfig-max_value_size--autonomous/run1/selfcheck.out)). INFO lines: 2 `alloc` lines per accepted read at every start; r1's k = 8 read class `ServerError`.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: settings ×4, inserts ×7, starts ×3, r256 8/8 and 8-row whole-table read, readback lines with `allocSupported/Enabled=true`. `byteman_agent=1` re-read in `cluster-run1/commands.log`. |
| 2. Readings | yes | The partial trace lines of r8's whole-table read were re-read in `alloc-r8.trace` (3 = 2 + 1 for keys 1, 2, 4, 5, 8; 2 for k = 6). |
| 3. Matched row | yes | Each clause re-derived from the raw files (unit Δ bands, exact messages, per-key outcomes, guard (l, V) pairs, trace lengths, ceilings). |
| 4. Excluded rows | yes | Each excluding reading is a self-check line (`refused … alloc_of_len_anytime=0`, `accepted` at V, `insert.8.acknowledged`, `z*.refused`). |
| 5. Observed vs. inferred | yes | (a) does not decide a row. The (b) gap is named. (c) is INFO. The `ReadStage`/`Native-Transport-Requests` thread names were re-read in `alloc-r256.trace`. |
| 6. Deviations and gaps | yes | The aborted first launch has no node output (`cluster-run1.attempt-1792963877/summary.txt` ends at the pre-check). |
| 7. Core question | yes | Unit boundary → cluster boundary at two values → control → write side, each with its part. |

### 5.2 Run 2?

**No** — 2026-10-25. The conclusion rests on observed readings; the one inference (a) does not decide any row. The self-check settles every part from run 1's raw files. The result neither refutes the case nor confirms a new bypass (the write-side bypass is the file's own A3 statement). It also agrees with the closed guided case on the same guard, which ran on another machine; that is not used for this verdict.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested (B1):**
- (a) `0MiB` and `2048MiB` stop start-up; `1MiB` and `2047MiB` are accepted.
- (b) With `max_value_size: V`, reading a stored value longer than V fails without allocating it, while values ≤ V read normally. So the largest single-value allocation on the read path is ≤ V.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed**: B2g row 1. ConfigProbe 5/5. At V = 1 MiB, 4 MiB and 256 MiB (default), V returned (Δ = V + 64) and V + 1 refused with the exact guard message (Δ ≤ 2,176 B); 64 MiB refused below the default; controls allocated | caps (per value read: the largest allocation is V + 64 B) | run 1 + self-check | 2026-10-25 |
| Cluster | **Confirmed**: B3g row 1. rc 3 at `0MiB` / `2048MiB`. From one SSTable written under the default, `1MiB` returned exactly the values ≤ 1,048,576 and `8MiB` exactly those ≤ 8,388,608. Each refusal was a `ReadFailure` with the guard's (l, V) inside a `CorruptSSTableException`, with no array of the refused length. The default control read all 8 intact. Write side: **bypass as recorded** (B3g row 3): a 2 MiB insert acknowledged under `1MiB`, its read refused (`ServerError`) | caps (read side: per value read); does not cap what is written or stored | run 1 + self-check | 2026-10-25 |

**What each outcome means here.**
- "Caps" means no single deserialized value can allocate an array larger than V. A larger declared length is refused at the guard before allocation, on the SSTable read path and on the coordinator's decode.
- It does not bound what is written, stored, or held in the memtable. The limits on writes are `max_mutation_size` and the native message size; at defaults both are 16 MiB here.
- The refusal behaves as corruption: `CorruptSSTableException`, a suspect SSTable, and an `ERROR` per read.

**Feedback filed:**
- The case file's section D was filled (uncommitted). No section was amended after the freeze.
- Index rows: `_INDEX.md` §1 (Stage 4), §2 (frozen hash row), §3 (coverage line).
- For stage 3: the filed B3 did not say how the node is stopped. Only a drained node avoids replaying the phase-1 mutations under the smaller limit. A replayed over-limit mutation stops the node starting (A3 row 3).
- For stage 3: a value written under the smaller limit is refused on the next read even before a flush (coordinator decode), with `ServerError` rather than `ReadFailure`.

**Processes:** after the cluster tier, `final CassandraDaemon processes: none` and `node-mvs` was wiped (`run1/cluster/summary.txt`).
Re-checked at the end of the session: `ps -eo command | grep '[C]assandraDaemon'` was empty; ports 7000/7199/9042/9091 were free; `$W/probe-mvs` was removed; the run clone was clean (test yaml untouched); the repository root had no `build/` or log folder.
