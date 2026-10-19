# CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT — stage-4 results  <!-- file: long-path/results/CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT.md -->

> **Case:** [`CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT`](../../stage3-ai-deep-read/cases/CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT--guided.md)
>
> **Status:** **Closed 2026-10-19 — all tiers verified at stage 4 (verdicts below).** verdict filed (2026-10-14) — **Confirmed at both tiers, both check sites**; *L* = 0 **bypass as recorded** (the receive side keeps every copy, 2 MB included, the serialize side none); no run 2
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
| **Case-file version** | Base commit `b244df7` (the filing commit; the case file is unchanged since) plus the step-0 amendments of 2026-10-14 (uncommitted at freeze). §9 hash before the amendments `000fe7c0e2a23ee1bbcf732bcdc5348f2d2076e3`; **after the amendments `71a37be99d0763938fb7cd2d9f8ac473f685b92b`** (`sed -n '/^## 9\. /,/^## 10\. /p' <case> \| git hash-object --stdin`); §9a alone `3ea8c867e1177c5bc780f4bb36667b1f8c83c0be`. §9a is frozen at this version. Recorded 2026-10-14 15:51 EDT, before any reading of this case existed (no earlier session ran it; `pc57:~/stage4-logs/` had no `cms` folder). |
| **Harness** | `../harness/CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT/` (uncommitted at run 1), written 2026-10-14 by this session after the freeze: `CacheableMutationSizeTest.java`, `unit-run.sh`, `cache-trace.btm`, `hold.btm`, `make-node-yaml.sh`, `send-mutation.py`, `histo.sh`, `cluster-run.py`, `README.md`. md5s and the instrument checks: §1.2. Node copy `pc57:~/stage4-harness-run/cms/`. |
| **Tiers and values** | Unit: upstream `TeeDataInputPlusTest`; harness `CacheableMutationSizeTest`, one JVM per value, *L* = 100,000 · 1,000,000 (default) · 4,000,000 · 1 (reference) · 0 (escape). Cluster (one node on `pc57`, RF 1): the same five values, each Phase 1 (live writes, serialize site) then Phase 2 (kill and commit-log replay, receive site). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-14 |

### 1.1 Design audit

Citations re-read against the pinned clone `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`).

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | The heap `byte[]` of one mutation's serialized copy (§7, §9a claim). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 100,000 · 1,000,000 (default) · 4,000,000, plus the reference 1 and the escape 0, at both tiers (9b "Capacity values"). Restart-only, so one JVM / node start per value. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | Unit: the slot's array length (exact, retained) and the thread's allocated bytes. Cluster: the live `[B` bytes and the two classes' live counts from a collecting class histogram, read as differences from the reference *L* = 1 (9d names why absolute `[B` is not read, and that the direct scratch buffer is not measured on the node). |
| A. Core question | usage driven to the limit and past it | Met | Unit: *T* = *L* − 1, *L*, ≈ 1.01 *L*, ≈ 2 *L* at every value; cluster: three sizes, each under one value and over the next. |
| B. Logic | each step says what it establishes | Met | §9a "How this verifies", Logic (1)–(5). |
| B. Logic | prediction stated in numbers or a clear relation | Met | Exact boundary (*L* − 1 cached, *L* not), array length *T*, counts +8 *c*(*L*), `[B` excess 0.72 · 4.72 · 20.72 MB, ratio ≈ 4.4. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | Rows for over-limit copies, under-limit misses and off-by-one, wrong length or bytes, counts follow but bytes do not, flat across values, refused / delayed writes, invalid run. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The two rules below the table: slot class (unit), `cached=` field and the live `SizeOnly…` count (node). |
| B. Logic | alternative explanations and their controls | Partly | The "refused, delayed past the hold" row had no control for the node's own client deadline: every held write would have timed out at 12 s (rec. 1). Otherwise: reference *L* = 1 and the equal runs for the `[B` noise, idle pair for the counts, the small write for the rule, the replay arm under 100,000 / 1,000,000 / 0 for the receive-side overshoot. |
| C. Specific | a human can follow it from the intro and §9a | Met | §9 intro, §9a. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | The "unheld" control write is in keyspace `ks1`, which the hold rule holds, and it is replayed in Phase 2 beside the 24 (rec. 2); Phase 2's release has no idle baseline of its own (rec. 4). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | The calibration's start, *L* − 200, is above *p\** if *k* > 200, and the walk direction is not given (rec. 3); one `hold.txt` per value mixes the phases' `held` lines (rec. 5). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Harness listed as step-1 work (9c); written (above). `pc57` (this host): JDK 11.0.32.1, Ant 1.10.12, `jcmd`, `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54`), built (`build/apache-cassandra-5.0.9-SNAPSHOT.jar`), Byteman 4.0.20 in `build/lib/jars/`, the bundled Python driver 3.29.0; unit tests run with `-Xmx4G` (`build.xml:1245-1255`). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly | Volumes are small (24 writes, ≈ 20.7 MB held, ≈ 21 MB of commit log per value; 4 GiB heap; 54 GB free on `/`), but as written the hold cannot be observed: the client deadline cuts every held write at 12 s (rec. 1). |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Read in context: `Mutation.java:74-81`, `:158-176`, `:326-342`, `:412-426`, `:439-467` (the `if` at `:451`, the store at `:463`, `serializedSize` in scope there), `:487-523` (the tee at `:493`, the flag at `:518`, the copy at `:519`), `:530-533`, `:541-599`; `TeeDataInputPlus.java:39-62`, `:65-76`, `:192-224`; `DataOutputBuffer.java:50-90` (scratch, direct, 128 B, recycle ≤ 1 MiB), `:143`, `:158-180`, `:265-291`; `SingleTableUpdatesCollector.java:112`; `StorageProxy.java:1495-1501`, `:1644-1660`, `:2623-2667`; `Keyspace.java:472-530` (every apply reaches `applyInternal`); `CassandraKeyspaceWriteHandler.beginWrite()` (the commit log only when durable); `CommitLogReader.java:427-433`; `CommitLogReplayer.java:282-326` (the closure holds the deserialized mutation; the rebuilt one is applied non-durably, so nothing sizes it); `AbstractWriteResponseHandler.java:112-158`; `Dispatcher.java:238-271`; `Config.java:1399`; `DatabaseDescriptor.java:503-507`; `SchemaKeyspace.java:81` (schema tables flushed on change, so `ks1` exists before replay); `build.xml:33`, `:94`, `:1192`; `TeeDataInputPlusTest.java:67`, `:73`, `:135-139`; `CommitLogTest.java:467-489`; `conf/cassandra.yaml:634-636`, `:723`, `:825`, `:1330`, `:2320`. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Add `native_transport_timeout: 180000ms` to the node yaml. The coordinator waits for a write until the nearer of `write_request_timeout` and the client deadline, enqueue time + `native_transport_timeout` (`AbstractWriteResponseHandler.currentTimeoutNanos():152-158` → `Dispatcher.RequestTime.computeDeadline():238-244`), default 12 s (`Config.java:1399`). | Applied 2026-10-14 (9b hold-fixed row; 9c amendment); uncommitted | As written, every write held 45 s returns `WriteTimeout` after 12 s: the "refused, delayed" row would fire on an artefact. |
| 2 | Put the control write in a second keyspace, `ks0.ctl`; trace rules match `ks0` and `ks1`, the hold rule `ks1` only; Phase 2's 24 are the `ks1` lines and the control's replayed line is recorded, not counted. | Applied 2026-10-14 (9a Phase 2 bullet, 9b Controls, 9e Phase 1 step 1) | A `ks1` write cannot be unheld; replayed, it would add a 25th `held` and `deserialize` line and a copy. |
| 3 | Calibration starts at *L* − 1 − *k*₁ − *s* (*k*₁ from a one-byte payload) and walks both ways, ≤ 64 steps. | Applied 2026-10-14 (9e unit step 3) | The written start and walk could miss *p\**. |
| 4 | Phase 2's after-replay histogram is read against Phase 1's idle pair at the same value, with that pair's spread. | Applied 2026-10-14 (9a "Release", 9e Phase 2 step 6) | Phase 2 has no idle histogram of its own; "the idle baseline" was undefined there. |
| 5 | One `hold-p<n>.txt` and `trace-p<n>.txt` per phase; the trace rules print `ks=`, `pk=` (and `v=` on `serialize`); `cluster-run.py` (Python) in place of `cluster-run.sh`; `send-mutation.py many` is asynchronous on one session. | Applied 2026-10-14 (9c amendment) | Counting and joining lines per phase and per write; the run-script form of the other long-path harnesses. |
| 6 | §9b's `concurrent_writes` row says the 24 writes are held "on mutation-stage threads". A coordinator's local apply goes through `Stage.MUTATION.maybeExecuteImmediately()` (`StorageProxy.java:1646`), so it may run on the native-transport request thread while holding a mutation-stage permit. Replay's applies are on the mutation stage (`CommitLogReplayer.java:323`). | Left for stage 3 | No effect on the run: 24 permits of 32 either way, and the held thread keeps the mutation reachable. |
| 7 | 9c "Budget" quotes 125 GiB and 63 GB (the `pc66` figures); `pc57` has 251 GiB and 54 GB free. | Left for stage 3 | Cosmetic. |

### 1.2 Instrument checks (not readings)

- **Before the chain:** the unit test compiled with `javac` against the clone's classpath (not run). Byteman `TestScript` first rejected
  `cache-trace.btm` (`PlusExpression.typeCheck : invalid argument type boolean`: a boolean cannot be concatenated); the `deserialize`
  rule now prints `($teeIn.isLimitReached() ? "false" : "true")`, and all three rules type-check (`TestScript: no errors`). The repository
  folder and the node copy `~/stage4-harness-run/cms/` are byte-identical (`md5sum` diff, 16:06); the md5s are in each run's `summary.txt`.
- **Cluster instrument check** (`cluster-run.py instrument`, 2026-10-14 16:00–16:03, after the unit tier in the run-1 chain;
  `pc57:~/stage4-logs/cms/instrument/summary.txt`): (i) `TestScript: no errors`; `Submit -l` lists the three rules on their trigger
  methods. (ii) `histo.sh` parses each histogram (about 0.45 s each). (iii) idle pair 10 s apart: `CachedSerialization` 0 → 0,
  `SizeOnly…` 0 → 0, `[B` 15,277,944 → 16,331,600 B (the `[B` row moves about 1 MB on its own in 10 s). (iv) the control write to
  `ks0.ctl` returned in 0.009 s with no `held` line; `serialize T=1066 cached=CachedSerialization ks=ks0`. (v) 24 × 90,000: 24 `held`
  lines; held − idle `CachedSerialization` +24 against both idle histograms; 24 `serialize` lines, all `T=90043 cached=CachedSerialization`;
  all 24 writes `OK` after 45.016–45.025 s (the amended client deadline holds). (vi) `kill -9`, restart: 24 `held` and 24 `deserialize`
  lines (all `cached=true teeLen=90043`) within 8 s of the start command; during the hold `CachedSerialization` 24 and `Mutation` 48 (the
  deserialized mutation in the replay task's closure and the rebuilt one, as §7 traces); node `UN` after 61 s; after the replay 0.
  `INSTRUMENT CHECK PASSED`. These are instrument checks at the default and are not counted as readings.
- **The unit harness was not shaken down separately**: its own setup checks (`allocated_bytes_supported`, the read-back) are its instrument
  checks and ran inside the counted run (§4).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-14, 15:58–16:19 EDT | not done |
| Node (CloudLab name and type) | `pc57` = `node0.jason92-319347.misconfiguration-pg0.cloudlab.umass.edu` (32 cores, 251 GiB); this session ran on it, no ssh | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 (`11.0.32.1+1-post-1ubuntu1-22.04-Ubuntu`) | |
| Ant (`ant -version`) | 1.10.12 | |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at `b5f2a54210d541339c2e7c17a794195cac0e67c2` (`cassandra-5.0.9`), built; harness test copied into `test/unit/org/apache/cassandra/db/` (untracked) | |
| Case-file commit / harness commit | base `b244df7` + uncommitted step-0 amendments (§9 `71a37be9…`) / harness uncommitted; node copy `~/stage4-harness-run/cms/`, md5s in each run's `summary.txt` | |
| Storage for node data | local disk `/dev/sda3` (63 GB, 54 GB free; PERC H710P), clone's `data/`, `commitlog/` | |
| Full logs (path, outside the repo) | `pc57:~/stage4-logs/cms/` (`unit/`, `instrument/`, `<L>/`, `chain.log`) | |


## 3. Runbook defects

None in run 1. The one defect found before it — Byteman cannot concatenate a boolean (`TestScript` type error in `cache-trace.btm`) — was
an instrument check, fixed before any reading (§1.2); it does not touch §9.

## 4. Run 1

**Scope:** unit tier at all five values plus the upstream class; cluster tier at all five values, both phases each, and the cross-value
comparison. One chain on `pc57`, 2026-10-14 15:58:42–16:19:08 EDT ([`chain.log`](CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT--guided/run1/chain.log)):
unit 15:58–16:00, instrument check 16:00–16:03 (§1.2, not counted), values 4,000,000 → 1,000,000 → 100,000 → 1 → 0 at about 3 min each, then
`compare`. **Command log:** `CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT/run1/` holds `unit.summary`, `unit-<L>.out`,
`unit-upstream-TEST.xml`, and per value `summary-<L>.txt` (every `EXPECTED` line), `histo-<L>.csv`, `histo-rows-<L>.txt` (the three rows of each raw
histogram), `trace-p1-<L>.txt`, `trace-p2-<L>.txt`, `hold-p<n>-<L>.txt`, `writers-p1-<L>.txt`, `replay-<L>.txt`; full logs (`session.log`, raw
histograms, system logs) in `pc57:~/stage4-logs/cms/`. Every `EXPECTED` line of the five value runs and of `compare` reads **yes**.

### 4.1 Readings

**Unit tier** (`MessagingService.current_version` 12 = 4.0, slot ordinal 2; JDK 11.0.32.1; `unit.summary`, `unit-<L>.out`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Upstream `TeeDataInputPlusTest` | pass (1 test, 0 failures) | `unit-upstream-TEST.xml` |
| Harness, all values | 39 · 39 · 39 · 19 · 25 checks at 100,000 · 1,000,000 · 4,000,000 · 1 · 0, **0 mismatches**, no `record` differs | `unit.summary` |
| Read-back | private field and `getLong()` = *L* at all five | `unit-<L>.out` `readback.*` |
| Calibration (*k* = 51, 51, 52) | *p\** = 99,948 · 999,948 · 3,999,947 in 0 steps; *T*(*p\**) = *L* − 1, *T*(*p\** + 1) = *L* exactly | `calibration` notes |
| Serialize site | *T* = *L* − 1: `CachedSerialization`, array length *T*; *T* = *L*, ≈ 1.01 *L*, ≈ 2 *L*: `SizeOnlyCacheableSerialization`; 1,024 B (*T* 1,074): cached at 100,000 and above | `ser.*` notes |
| Heap allocated | *Δ*(*p\**) − *Δ*(*p\** + 1) = 100,608 · 1,002,504 · 4,002,504 B for *T* 99,999 · 999,999 · 3,999,999 (*T* + 609 · 2,505 · 2,505; band *T* … *T* + 65,536); the call at *T* = *L* allocates 592 B | `heap.delta_diff` |
| Scratch (recorded) | after *p\**: 199,996 B at 100,000 (kept); **128 B at 1,000,000** and 4,000,000 (grew past 1 MiB, replaced at close); unchanged across *p\** + 1 | `record` lines |
| Receive site | *W* = *T* for every size; *T* < *L*: a copy of length *W*, bytes equal to *W*; *T* ≥ *L*: slot **null**, then `SizeOnly…` after `serializedSize` | `recv.*` |
| Tee alone | *L* − 1 read: not reached, *L* − 1 mirrored; *L* read: reached, 0 mirrored (1 byte at *L* = 1) | `tee.*` |
| *L* = 1 | no copy at either site, 1,024 B included | `unit-1.out` |
| *L* = 0 (escape) | serialize site: no copy at 1,074 · 100,051 · 3,000,052 B; receive site: **a copy of each, 3,000,052 B included**, equal to the wire bytes; tee of 3,000,000 B: not reached, all mirrored | `unit-0.out` |
| Idle | 0 B allocated over 2 s (the meter itself 0 B), scratch unchanged | `idle` notes |

**Cluster tier** — one node, RF 1; *T*₁, *T*₂, *T*₃ = **90,043 · 500,043 · 2,000,043** at every value (trace). Counts are live instances from `jcmd GC.class_histogram`
(idle pair 0 / 0 at every value); `[B` excess = `[B` bytes at *L* − at *L* = 1, same phase, held-1 histogram (held-2 within 56 B of it).

| *L* | *c*(*L*) | Phase 1 held: Cached / SizeOnly (pred.) | Phase 1 trace `cached=` | Phase 2 held: Cached (pred.) | Phase 2 trace | `[B` excess p1 / p2 (pred.) |
|---|---|---|---|---|---|---|
| 4,000,000 | 3 | 24 / 0 (24 / 0) | all 24 `CachedSerialization` | 24 (24) | 24 `cached=true`, `teeLen` = *T* | 20,718,296 / 20,722,800 B (20,721,536) |
| 1,000,000 | 2 | 16 / 8 (16 / 8) | 2 MB → `SizeOnly…` | 16 (16) | 2 MB: `cached=false teeLen=42` | 4,716,744 / 4,721,712 B (4,721,024) |
| 100,000 | 1 | 8 / 16 (8 / 16) | 500 KB, 2 MB → `SizeOnly…` | 8 (8) | 500 KB, 2 MB: `cached=false teeLen=42` | 716,816 / 720,464 B (720,512) |
| 1 (reference) | 0 | 0 / 24 (0 / 24) | all `SizeOnly…` | 0 (0) | all `cached=false teeLen=0` | — |
| 0 (escape) | 0 · *c*′ = 3 | 0 / 24 (0 / 24) | all `SizeOnly…` | **24 (24)** | all `cached=true`, `teeLen` = *T*, 8 of 2,000,043 | p2: **20,722,248 B** over *L* = 1 (20,721,536) |

| Observable | Reading | Evidence (file) |
|---|---|---|
| Cross-run spread *S*_B (Phase 1, *L* = 0 vs 1) | 7,416 B (held-1), 7,472 B (held-2); every predicted excess is above 3 *S*_B, so all are read | `summary-compare.txt`; `histo-0.csv`, `histo-1.csv` |
| Dose-response | excess(4,000,000) / excess(1,000,000) = **4.39** in both phases (≈ 4.4 predicted) | same |
| Property in force | `jcmd VM.system_properties` = *L* at every value; JVM command line carries it | `session.log` (node), `summary-<L>.txt` |
| Writes | 24 of 24 `OK` at every value, completed 45.016–45.121 s after the start (the 45 s hold); no `ERROR` or `WriteTimeout` line in any system log | `writers-p1-<L>.txt`, self-check |
| Holds | Phase 1: 24 `held` lines within 1.0 s, at 4,000,000 on 21 `MutationStage` and 3 `Native-Transport-Requests` threads (the coordinator's `maybeExecuteImmediately()`, audit rec. 6); Phase 2: 24 within 7.8–8.3 s of the start command, all on `MutationStage` | `hold-p<n>-<L>.txt` |
| Replay | `Replaying … CommitLog-7-…`, `Log replay complete, 83 replayed mutations in 45,407–45,526 ms`; node `UN` 58 s after the start | `replay-<L>.txt` |
| Release | both counts back to 0 after the hold (Phase 1) and after the replay (Phase 2) at every value | `histo-<L>.csv` |
| Phase 2 `SizeOnly…` | 0 during the replay hold at every value (predicted unchanged) | `histo-<L>.csv` |
| Control write (`ks0.ctl`) | returned in 0.006–0.013 s, no `held` line; `T=1066`, `CachedSerialization` at 100,000 and above, `SizeOnly…` at 1 and 0; replayed: `cached=true teeLen=1066` except at 1 (`false`, 0) | `summary-<L>.txt`, `trace-p<n>-<L>.txt` |

### 4.2 Conclusion and logic

1. **Validity** — valid. The property reached `Mutation` at every value [observed: unit `readback.field` = *L*; cluster `VM.system_properties` and the
   JVM command line, `summary-<L>.txt`]. Hold-fixed settings in force: batch sync with no period, `write_request_timeout` 120000ms,
   `native_transport_timeout` 180000ms, `concurrent_writes` 32, `heap_buffers`, `storage_compatibility_mode: CASSANDRA_4`, 4 GiB heap, Byteman loaded
   [observed: `summary-<L>.txt` "yaml in force", `jvm-args` checks]. Every Invalid trigger is absent: 24 `held` lines in 1 s (Phase 1) and 8.3 s (Phase 2), all
   three rules type-checked, histograms parsed, the control write traced, `isThreadAllocatedMemorySupported()` true, upstream green [observed: §1.2,
   `hold-p<n>-<L>.txt`, `unit-<L>.out`]. The limit was reached and passed at every value: sizes on both sides of *L* at both tiers.
2. **Readings** — nothing contradicts another. The `[B` row moves about 1 MB in 10 s on an idle node [observed: idle pairs], but two runs with the same
   held writes differ by only 7.4 kB at the hold, so the excesses are read well above noise. At 1,000,000 the scratch buffer ended at 128 B after the
   999,999 B copy (it grew past 1 MiB and was replaced at close) — inside the recorded prediction ("≥ *T* if kept, or 128"), noted for stage 3 in the case's §10.
   The withheld receive-side copies show `teeLen=42`: the tee mirrored the 42 bytes before the value and stopped at the value's own read [observed:
   `trace-p2-<L>.txt`]; at *L* = 1 it mirrored nothing.
3. **Matched row** — "Unit: at every value the boundary is exactly *T* = *L* − 1 cached and *T* = *L* not, at both sites, with the array length *T*
   (receive: equal to the wire bytes), and *L* = 1 caches nothing. Cluster: the live counts and the byte arrays follow *c*(*L*) at both phases, the trace
   names the branch of each write, and every written mutation is applied" → **Confirmed**. Unit: boundary exact at 100,000, 1,000,000, 4,000,000 at
   both sites, lengths *T*, bytes equal to *W*, nothing at 1 [observed: `unit-<L>.out`]. Cluster: counts 24 / 16 / 8 / 0 = 8 *c*(*L*) at both phases, `SizeOnly…`
   8 (3 − *c*) in Phase 1, `[B` excesses within 0.6 % of 8 Σ(*T*ᵢ + 16), the trace's branch per write, 24 acknowledged writes and 83 replayed mutations
   per value [observed: table above]. And "At *L* = 0 the serialize side holds nothing and the receive side holds a copy of every mutation, the 2 MB ones
   included" → **Bypass as recorded**: unit (3,000,052 B copy) and Phase 2 (24 copies, 8 of 2,000,043 B; 20,722,248 B of `[B` over the reference)
   [observed: `unit-0.out`, `trace-p2-0.txt`, `histo-0.csv`].
4. **Excluded rows** — *Refuted (over-limit copy)*: no mutation with *T* ≥ *L* (*L* ≥ 1) has a copy at any value, by slot, trace or count. *Refuted in
   part (boundary)*: *T* = *L* − 1 cached and *T* = *L* not, at three values, both sites. *Refuted in part (length or bytes)*: every copy's length is *T*,
   receive-side bytes equal to the wire. *Not confirmed (bytes below a third)*: the `[B` excesses are within 0.6 % of the prediction. *Refuted (flat)*: the
   counts are 24 · 16 · 8 · 0 across the values. *Refuted (refused / delayed / lost)*: 24 of 24 `OK` after the hold at every value, no error logged, 83 mutations
   replayed. *Invalid run*: none of its triggers (part 1).
5. **Observed vs. inferred** — the conclusion depends on: (a) the histogram's live counts are the copies retained by the held mutations [inferred: the
   histogram collects first; the idle and release counts are 0, so nothing else holds these classes at the node; counts match 8 *c* exactly]; (b) the `[B`
   excess is the copies' arrays [inferred: the only difference between the runs is the property; its size matches the arrays' predicted size to within
   0.6 %, and its count matches the class counts]; (c) an acknowledged write was applied [inferred: CL ONE on one node returns after the local apply;
   the replay of 83 mutations confirms they reached the commit log].
6. **Deviations and gaps** — none from the frozen procedure. Gaps named by §9 itself: the network receive path (a replica), mixed versions, *N* not
   varied, the direct scratch buffer not measured on the node, the collector's behaviour with humongous arrays (§11 "What this design does not cover").
7. **Core question** — Logic (1): the limit read back equals the value set (part 1). (2) Usage stops at the limit: *T* = *L* − 1 keeps a copy of exactly that
   length and *T* = *L* none, at both sites (part 3, unit). (3) Usage follows the constraint: live copies 24 · 16 · 8 · 0 and `[B` 20.72 · 4.72 · 0.72 MB · 0
   at 4,000,000 · 1,000,000 · 100,000 · 1, at both phases, ratio 4.39 (part 3, cluster). (4) The disallow branch withholds the copy: the size-only object or
   a null slot, `cached=` per write, and the writes applied (parts 3, 4). (5) At 0 the receive side holds every copy, 2 MB included, and the serialize side
   none (part 3). **The constraint caps the serialized copy each mutation keeps at below *L*, per copy, and the heap of the copies follows it; it caps no
   total, and 0 removes its bound on the receive side.**

**Conclusion (one line):** Confirmed (unit and cluster, both sites); *L* = 0 bypass as recorded.

## 5. Self-check of run 1 — AI

Independent script [`run1/selfcheck.py`](CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT--guided/run1/selfcheck.py), written while the
cluster tier was running (before any value's reading had been read). It re-parses the unit test's `STAGE4 note` lines (not its own check verdicts), the
upstream JUnit XML, and per value the Byteman traces, the hold files, the **raw** `jcmd` histograms, the writers' client lines, the JVM command lines,
the yaml copies, `session.log`'s `VM.system_properties` output and the system logs; it never reads `summary.txt`, `histo.csv` or `sizes.json`.
**Result: 269 checks, 0 failed** ([`selfcheck.out`](CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT--guided/run1/selfcheck.out)).
Its first version accepted any line containing "replay" as evidence that the replay ran; after re-reading the system logs by hand it was tightened to
`Replaying … CommitLog-` plus `Log replay complete` and a no-`ERROR` check (5 + 5 checks added), and re-run.

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Self-check lines for the JVM command line, the yaml settings and `VM.system_properties` at every value; `hold-p<n>`, `unit-<L>.out` read-back and setup lines re-read. |
| 2. Readings | yes | `histo-rows-<L>.txt` re-read against `histo-<L>.csv` (raw rows equal, e.g. 4,000,000 held-1: `[B` 59,910,704, Cached 24); idle pairs and `[B` drift re-read. |
| 3. Matched row | yes | Re-derived by the self-check from raw files: unit boundary, lengths and wire equality at every value; per-write branch in both traces; counts against both idle histograms; `[B` excesses and *S*_B from the raw histograms. |
| 4. Excluded rows | yes | Each excluding reading is a self-check line (no over-limit copy, boundary, lengths, not flat, 24/24 writes, no `ERROR`, replay complete). |
| 5. Observed vs. inferred | yes | (a)–(c) consistent with the raw files: release and idle counts 0 (`histo-rows`), `[B` matches the arrays' sizes, `Log replay complete, 83 replayed mutations` in `replay-<L>.txt`. None decides the row alone: the trace gives the branch per write independently. |
| 6. Deviations and gaps | yes | No step skipped; the scratch reading at 1,000,000 is inside its recorded prediction (`unit-1000000.out` `record` line `as-predicted`). |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | Logic (1)–(5) of §9a, each with its part. |

### 5.2 Run 2?

**No** — 2026-10-14. The conclusion rests on observed readings at both sites and both tiers; the inferences of part 5 are each backed by an independent
observable (trace per write, exact counts, `[B` to within 0.6 %). The self-check settles every part from run 1's raw files. The result does not refute the
case, and the one bypass it confirms (*L* = 0) was recorded at stage 3 and is observed directly (unit slot, trace, count and bytes), not inferred.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its
date and reason.

| Tier | Verdict (§9a row) | Basis | Date |
|---|---|---|---|
| Unit | **Confirmed** — boundary exact (*T* = *L* − 1 cached, *T* = *L* not) at 100,000 · 1,000,000 · 4,000,000 at both sites, copy length *T*, receive copy equal to the wire bytes, nothing at 1; *L* = 0 **bypass as recorded** (receive side copies 3,000,052 B) | run 1 + self-check | 2026-10-14 |
| Cluster | **Confirmed** — live copies 8 *c*(*L*) = 24 · 16 · 8 · 0 at both phases, `[B` excess 20.72 · 4.72 · 0.72 MB (within 0.6 % of predicted, ratio 4.39), branch per write in the trace, every write acknowledged and replayed; *L* = 0 **bypass as recorded** (24 replayed copies, 8 of 2,000,043 B, 20.72 MB) | run 1 + self-check | 2026-10-14 |

**Feedback filed:** the case file's §10 "Stage-4 feedback" and "Notes" updated (2026-10-14, uncommitted); §9 amended by the step-0 audit (dated, §1);
no section of §2–§8 amended. Stage-3 notes (not applied): the scratch reading at the default (§4.2 part 2), audit recommendations 6 and 7.
