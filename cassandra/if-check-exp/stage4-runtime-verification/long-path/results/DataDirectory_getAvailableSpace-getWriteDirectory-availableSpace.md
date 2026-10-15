# DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace — stage-4 results  <!-- file: long-path/results/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md -->

> **Case:** [`DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace`](../../../stage3-ai-deep-read/long-path/cases/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md)
>
> **Status:** verdict filed (2026-10-15) — **unit: Confirmed; cluster: Confirmed** (§9a row 1, including §5's non-domination): on the guarded path (`ByteOrderedPartitioner`) the guard refused at `U − m < T` to the byte at both sides of two boundaries 206 MiB apart (`d` = ±16 MiB at `m` = 50 MiB; `m` = 240/272 MiB at `U` = *T* + 256 MiB), before any file; on the default path (`Murmur3Partitioner`) no guard ran, the compaction ate 18 MB into the 50 MiB reserve at `d` = −16 MiB and filled the disk at −256 MiB (`FSWriteError`, transports stopped); one sub-prediction missed (start-up flushes on arm A pass the second check site); no run 2
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
| **Case-file version** | Base commit `531c3ba` (the last commit touching the case file) plus the step-0 amendments of 2026-10-15 (uncommitted at freeze). §9 hash before the amendments `d1b480597e2c130df18573b9c3a220420f954b23`, §9a `9e9a2a14ef29539aa484fca0b7f1502eb459c3cf`; **after the amendments §9 `ee1b30c6eed72654a63f25489bdbc87d7200211c`, §9a `4c82f05a783daec2ced058b7ea0c7edfd903c6c4`** (`sed -n '/^## 9\. /,/^## 10\. /p' <case> \| git hash-object --stdin`; §9a: `'/^### 9a\. /,/^### 9b\. /p'`). §9a is frozen at this version. Recorded 2026-10-15 03:04 EDT, before any reading of this case existed (`pc57:~/stage4-logs/` and `~/stage4-harness-run/` had no folder for it; no mount of the case's filesystem). |
| **Harness** | `../harness/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace/`, written by this session after the freeze (§1.2). Node copy `pc57:~/stage4-harness-run/dds/`. |
| **Tiers and values** | Unit: upstream `CompactionAwareWriterTest`; harness `WriteDirectoryGuardTest` once per partitioner (exact boundary *T* − 1 / *T*, stub 1 B, clamp at 0, default path, flush site). Cluster (one node on `pc57`, a fresh 4 GiB loop filesystem per label): arm B (`ByteOrderedPartitioner`) `d` = +256 · +16 · −16 · −256 MiB at `m` = 50 MiB, `m` = 50 · 240 · 272 · 512 MiB at `U` = *T* + 256 MiB, sibling control; arm A (`Murmur3Partitioner`) `d` = +256 · +16 · −16 · −256 MiB. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-15 |

### 1.1 Design audit

Citations re-read against the pinned clone `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`).

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Bytes of compaction output on the data filesystem (§7; 9a claim). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | The device's free space by ballast (4 values) and `min_free_space_per_drive` (default 50 MiB plus three); the path selector by two clusters (9a Testability, 9b). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | `df`/`du` sampled every 0.5 s beside the exception text; 9a "Why the exception text and `df`". |
| A. Core question | usage driven to the limit and past it | **Not met → Met after rec. 1** | As written the trigger is `nodetool compact`, a `MAJOR_COMPACTION`: the JMX switch covers only `COMPACTION` (`CompactionTask.java:386`), and the sibling's budget `round(max(0, U − m) × pct)` with `pct ≤ 1` (`DatabaseDescriptor.java:1016-1017`, `Directories.java:563-569`) is never above the guard's `U − m` (`Directories.java:781-785`), so the sibling sheds inputs (`CompactionTask.java:396-448`) until the guard admits. **The guard's disallow branch is unreachable by the written trigger** (stage 4 observed exactly this mechanism in `max_space…` H1). |
| B. Logic | each step says what it establishes | Met | 9a "How this verifies", Logic (1)–(4). |
| B. Logic | prediction stated in numbers or a clear relation | Partly | The boundary `U − m = T` is a relation, but *T* is defined as `du` of the SSTable files while the estimate is the sum of `Data.db` lengths only (`ColumnFamilyStore.java:1700-1703`, `SSTableReader.java:541-546`), and arm A's "writes until full" is wrong at `d` = −16 MiB, where `U` = *T* + 34 MiB holds the output (rec. 2, 3). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | Missing: a guard outcome that disagrees with its own operands, arm A at −16 MiB completing or failing, a task of fewer than eight inputs (rec. 3, 5). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The exception text with both operands (9d); a trace makes it exact (rec. 5). |
| B. Logic | alternative explanations and their controls | Met | The sibling check (control with it on), drift (`df` band), idle control, ample-space control (9b). |
| C. Specific | a human can follow it from the intro and §9a | Met | §9 intro, §9a. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | Unit step 2.2 assumes `positions` non-null under `Murmur3Partitioner`, but a unit JVM owns no token ranges, so `DiskBoundaryManager.java:116-117` returns null on both partitioners (rec. 6); 9e's `(1 byte available)` is rendered `1B` (`FBUtilities.java:935-939`). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | The `m` = 2 GiB value clamps the available space to 0, and on arm B **every flush** calls `getWriteableLocation(estimatedSize)` (`Flushing.java:106-111`, the second check site `Directories.java:453`), so the node would fail its flushes (`FSDiskFullWriteError`, policy `stop`) before any compaction — possibly at start-up (`DefaultFSErrorHandler.java:126-131`) (rec. 4); the `m` sweep keeps inputs across restarts while an admitted run consumes them (rec. 7). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Listed as step-1 work (9c). `pc57` (this host): JDK 11.0.32.1, Ant 1.10.12, `~/cassandra-run1` at `cassandra-5.0.9` (built), Byteman 4.0.20 in `build/lib/jars`, the bundled Python driver; 32 cores, 251 GiB RAM, 50 GB free on `/`; no daemon running; `sudo` for the loop mount. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 8 × 12,800 × 5 KiB ≈ 525 MB of inputs; the 4 GiB filesystem holds inputs, output and ballast; ≈ 4 min per label, 13 labels. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Read in context: `CompactionAwareWriter.java:84-94` (`diskBoundaries = db.positions`), `:166-204` (`maybeSwitchLocation`, the only caller of `getWriteDirectory`), `:220-236` (writer creation), `:265-295` (the guard `:281-286`, fallback `:290`), `:303-306`; `DiskBoundaryManager.java:44-62` (no splitter → fresh `DiskBoundaries` with null positions, no debug line), `:101-122`; `DiskBoundaries` 3-argument constructor (positions null); `IPartitioner.java:148-151`, `Murmur3Partitioner.java:435-437`, `ByteOrderedPartitioner` (no `splitter()` override); `Directories.java:226-302` (`canonicalPathToDD` keyed by the canonical table directory), `:325-330`, `:436-473`, `:781-785`; `Descriptor.java:131` (canonical directory); `ColumnFamilyStore.java:1698-1703`; `SSTableReader.java:541-546`, `:983-986`; `CompactionTask.java:148`, `:303-308` (`DefaultCompactionWriter`), `:384-457`; `CompactionManager.java:343-384` (a failed background task is not resubmitted); `Flushing.java:57-115`; `Config.java:339` (`IntMebibytesBound`, 50 MiB), `:344`; `DatabaseDescriptor.java:1016-1017`, `:2567-2570`; `DefaultFSErrorHandler.java:61-74`, `:126-131`; `FBUtilities.java:924-945`; shipped `conf/cassandra.yaml` `disk_failure_policy: stop` (`:471`), `num_tokens: 16` and `allocate_tokens_for_local_replication_factor: 3`; `test/conf/cassandra.yaml:18` (unit partitioner) and `CQLTester.java:411-418` (`prePrepareServer` sets Murmur3). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Trigger a **background** compaction (`nodetool enableautocompaction ks1 t`, STCS puts the eight equal inputs in one task) with `compactionDiskSpaceCheck(false)` set over JMX, then `disableautocompaction`; keep the sibling control as its own label with the check on. | Applied 2026-10-15 (9 intro, 9a Test, Procedure, Conclusions, 9b, 9c, 9e); uncommitted | The written trigger cannot reach the guard's disallow (A, "driven past the limit"). A background task is a `COMPACTION`, which the switch covers (`CompactionTask.java:386`); stage 4 of `max_space…` saw a background task compact all eight inputs in one task (its H2). |
| 2 | Define *T* as the sum of the inputs' `Data.db` lengths, read from the files, and set the ballast against it. | Applied 2026-10-15 (9a Prediction, 9c, 9d) | The estimate is `Σ onDiskLength()`, Data component only; `du` of the table adds Index, Filter, Summary, Statistics and so on, which would offset every boundary. |
| 3 | Split arm A's prediction: at `d` = −16 MiB it completes and the minimum free space during it falls below *m* (the reserve the guard keeps); at `d` = −256 MiB it fills the filesystem; add the rows for both. | Applied 2026-10-15 (9a Logic (4), Prediction, Conclusions) | The guard's boundary `U − m = T` is not the filesystem's (`U` ≈ *T* + a few MiB): between them the guarded path refuses and the default path writes into the reserve. As written, the −16 MiB reading would have matched no row. |
| 4 | Replace `m` = 2 GiB by a ±16 MiB pair around the boundary at `U` = *T* + 256 MiB (`m` = 240 and 272 MiB) plus 50 and 512 MiB; move the clamp at 0 to the unit tier; record that on arm B every flush passes the second check site. | Applied 2026-10-15 (9a Prediction "Boundary shifts", "Flush site"; 9b Capacity values, Scope) | A clamped node cannot flush on the guarded path, so the 2 GiB run would end in `FSDiskFullWriteError` before its trigger; the pair shows the refusal point moving by exactly the change in *m*. |
| 5 | Add Byteman observation rules (`guard-trace.btm`): the guard's two operands as compared, the path that created each writer, the flush site's write size; add the operand-consistency and fewer-than-eight rows. | Applied 2026-10-15 (9a Prediction, Conclusions; 9c, 9d) | The exception rounds both figures; the trace makes the boundary exact at the cluster tier and gives arm A a positive "no guard line" reading. |
| 6 | Unit tier: register one local token under `Murmur3Partitioner` (print `positions` before and after); stub to *T* − 1 and *T* for the exact boundary; message text `1B` / `0B`; add the clamp and flush-site steps. | Applied 2026-10-15 (9a Procedure 1, 9c, 9e unit steps) | Without a token the unit JVM takes the guarded path under both partitioners and step 2.2 would fail for a reason unrelated to the claim. |
| 7 | One label per value, each with a fresh filesystem and dataset; `num_tokens: 1` with an `initial_token`, `concurrent_compactors: 1`, every directory but data on local disk under `~/stage4-dds/`. | Applied 2026-10-15 (9b layout, Capacity values, 9e) | An admitted run consumes the inputs; the shipped token allocator is not needed for one node (and is the one setting not tested under `ByteOrderedPartitioner` before); `repair_session_space` ran a byte-ordered node this way. |
| 8 | §5/§6b/§10: the second check site is reached by **every memtable flush** on the null-boundary path (`Flushing.java:106-111`), not only by a compaction whose inputs span directories; and under `Murmur3Partitioner` flushes are not space-checked either (`:111`). | Left for stage 3 (fed back in §10 after the run) | Widens the case's non-domination finding to flushes; does not change this run's claim. |
| 9 | §6b step 2: a background task's exception is not resubmitted (`CompactionManager.java:374-383`), a later flush or `enableautocompaction` submits it again. | Left for stage 3 | Precision on "the strategy may reschedule". |

**Agreement criteria** — not filled (run 2 not chosen yet).

### 1.2 Instrument checks (not readings)

- **Byteman:** `guard-trace.btm` type-checks (`TestScript: no errors`) against the clone's classes; the first form of the
  `writeable` rule (`$0.paths[0].getAvailableSpace()`) did not parse, and a typed array binding did not type-check, so it
  binds `dirs = $0.paths; first = dirs[0]` untyped. `cluster-run.py` re-runs `TestScript` before every start.
- **Unit instrument run** (`unit-run.sh instrument`, 03:07–03:10, in `~/cassandra-run1`, `pc57:~/stage4-logs/dds/unit-instrument/`):
  `CompactionAwareWriterTest` 5/5; `WriteDirectoryGuardTest` 5/5 under each partitioner, every `STAGE4 check` ok. Not a
  reading; run 1 repeats the tier.
- **Shakedown 1** (`cluster-run.py shakedown1 b_m16`, 03:10–03:16, `pc57:~/stage4-logs/dds/shakedown1/b_m16/`): node up in
  12 s, dataset 8 × 65.9 MB in 50 s, ballast within 6,376 B of *U*, switch read back `false`, every `EXPECTED` line `yes`.
  One environment defect, not the harness's: `nodetool disableautocompaction` failed with `ClassNotFoundException: NodeTool`
  because a second AI session (stage 4 of `SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS`) was running `ant testsome` in the same
  clone `~/cassandra-run1` at that moment. Fix: this case's tiers run from a private clone `~/cassandra-run3`
  (`cassandra-5.0.9`, `b5f2a54`, `ant build-test` 03:20–03:22), the harness's default `CASSANDRA_HOME`; the two sessions take
  turns on the node (agreed over the cross-session channel). §9 unchanged.

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-15 | — |
| Node (CloudLab name and type) | `pc57` (`node0.jason92-319347`), 32 cores, 251 GiB RAM; the session ran on the node itself | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | — |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | — |
| Ant (`ant -version`) | 1.10.12 | — |
| Local `cassandra-src` clone commit | `~/cassandra-run3` at `cassandra-5.0.9` (`b5f2a54210d5`), cloned and built 2026-10-15 03:20 for this session's runs | — |
| Case-file commit / harness commit | case file: base commit plus the uncommitted step-0 amendments (§1); harness: uncommitted, node copy checked by `md5sum` (`~/stage4-harness-run/*.md5`) | — |
| Storage for node data | a fresh 4 GiB loop-mounted ext4 per label at `/mnt/stage4-dds` (image `~/stage4-dds.img` on `/dev/sda3`); commit log, hints, caches under `~/stage4-dds/` | — |
| Full logs (path, outside the repo) | `pc57:~/stage4-logs/dds/run1/<label>/` (unit: `~/stage4-logs/dds/unit-run1/`) | — |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | shakedown 1 (not a reading) | 9e cluster step 2, `disableautocompaction` | `bin/nodetool` could not load its main class while another session's `ant` rebuilt the shared clone | private clone `~/cassandra-run3` (§1.2); no change to §9 | 2026-10-15 | none needed |

None in run 1.

## 4. Run 1

**Scope:** unit tier (upstream `CompactionAwareWriterTest`; `WriteDirectoryGuardTest` under each partitioner) and the 13
cluster labels of 9b, 2026-10-15 03:33–03:36 (unit) and 03:48–04:17 EDT (cluster, `chainA.sh`, one label after another, each
its own lifetime and filesystem). **Command log:** each label's `session.log` on the node; excerpts in
`DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace/run1/` (`unit/`, `cluster/<label>/` with `summary.txt`,
`trace-window.txt`, `system-window.log`, `table-dir-final.txt`, `yaml-tail.txt`; `selfcheck.py`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, `run1/unit/run.out`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| U1 upstream `CompactionAwareWriterTest` | 5/5 pass | `unit/summary.txt` |
| `WriteDirectoryGuardTest`, `ByteOrderedPartitioner` | 5/5, every check ok: `positions` null before and after a local token; stub *T* − 1 = 3,089,266: `Not enough space to write 2.946MiB to build/test/cassandra/data (2.946MiB available)`, no new file, inputs live; stub *T* = 3,089,267: a writer created (a new `Data.db`); stub 1: `(1B available)`; clamp (`m` = 1 PiB): `getAvailableSpace()` = 0, `(0B available)`; stub off: compaction completes (600 rows, output within 1 % of *T*); flush with stub 1: `FSDiskFullWriteError` | `unit/run.out` |
| `WriteDirectoryGuardTest`, `Murmur3Partitioner` | 5/5, every check ok: `positions` null without a token, `list(1)` after one; stubs *T* − 1, *T* and 1: no exception, a writer created every time; clamp: `getAvailableSpace()` = 0 but no exception; flush with stub 1 succeeds | `unit/run.out` |
| Totals | 13/13 tests, 54 checks, 0 MISMATCH | `unit/summary.txt` |

**Cluster tier** — *T* = sum of the 8 inputs' `Data.db` lengths (≈ 527.30 MB); `U` = `df` Available at the trigger; the guard's
operands from the trace (`cluster/<label>/trace-window.txt`), the rest from `summary.txt`, `system-window.log`, `table-dir-final.txt`.

| Label | Arm | `m` | `U − m − T` (B) | Guard trace: est / avail / refused | Outcome | Files after | Min `df` during | Evidence |
|---|---|---|---|---|---|---|---|---|
| `b_p256` | B | 50 MiB | +268,427,736 | *T* / 795,725,824 / false | compacted in 9 s, no exception | one `Data.db` 527,352,386 | 319.7 MB | `cluster/b_p256/` |
| `b_p16` | B | 50 MiB | +16,771,416 | *T* / 544,071,680 / false | compacted | one 527,353,269 | 68.0 MB | `cluster/b_p16/` |
| `b_m16` | B | 50 MiB | −16,782,770 | *T* / 510,517,248 / **true** | `RuntimeException: Not enough space to write 502.873MiB to /mnt/stage4-dds/data (486.867MiB available)`; no `switch` line | the 8 inputs, same lengths, same 64 files | unchanged (563.0 MB) | `cluster/b_m16/` |
| `b_m256` | B | 50 MiB | −268,440,973 | *T* / 258,859,008 / **true** | guard exception (`(246.867MiB available)`) | the 8 inputs unchanged | unchanged | `cluster/b_m256/` |
| `b_mm050` | B | 50 MiB | +215,998,768 | *T* / 743,297,024 / false | compacted | one 527,353,262 | 267.2 MB | `cluster/b_mm050/` |
| `b_mm240` | B | 240 MiB | +16,769,749 | *T* / 544,067,584 / false | compacted | one 527,352,733 | 267.2 MB | `cluster/b_mm240/` |
| `b_mm272` | B | 272 MiB | −16,783,378 | *T* / 510,517,248 / **true** | guard exception | the 8 inputs unchanged | unchanged | `cluster/b_mm272/` |
| `b_mm512` | B | 512 MiB | −268,441,757 | *T* / 258,859,008 / **true** | guard exception | the 8 inputs unchanged | unchanged | `cluster/b_mm512/` |
| `b_sib` (check on) | B | 50 MiB | −268,443,184 | 197,736,042 (3 smallest inputs) / 258,854,912 / false | first task: 5 × `Reducing scope`, then compacted 3 inputs; a second background task shed 4 and aborted with the sibling's message | 5 inputs + one 197,752,074 output | 113.1 MB | `cluster/b_sib/` |
| `a_p256` | A | 50 MiB | +268,427,788 | **no guard line** | compacted; `switch positions=1` | one 527,353,401 | 319.7 MB | `cluster/a_p256/` |
| `a_p16` | A | 50 MiB | +16,769,112 | none | compacted | one 527,353,552 | 68.0 MB | `cluster/a_p16/` |
| `a_m16` | A | 50 MiB | −16,783,327 | **none** | **compacted** (no exception) | one 527,353,423 | **34.4 MB (< `m` = 52.4 MB)** | `cluster/a_m16/` |
| `a_m256` | A | 50 MiB | −268,440,328 | **none** | `FSWriteError: java.io.IOException: No space left on device` 5 s in; `Stopping transports as disk_failure_policy is stop`, native transport and gossip stopped (`statusbinary`/`statusgossip` "not running"); no `Compacted` line | the 8 inputs unchanged, **no partial output left** | 21.6 MB (sampled every 0.5 s); peak `du` 817.6 MB | `cluster/a_m256/` |

Every label: one `Compacting` line of `ks1.t` with all 8 inputs (3 for the sibling's first task), one
`Compaction space check is disabled` line (not `b_sib`), `df` at the trigger within 7.7 KiB of the planned *U*, idle control
flat. Arm B: 8 `writeable` lines for the flushes of `ks1.t` in every lifetime and no `Refreshing disk boundary cache` line;
every guard line in the arm-B traces (system tables included) obeys `refused == (avail < est)`. Arm A: the `Refreshing disk
boundary cache for ks1.t` debug line in every lifetime, every `ks1.t` writer `positions=1`, **24 `writeable` lines of
`system.local`/`system_schema.*` flushes in every lifetime, all 30–35 ms before the node's `state jump to NORMAL`**, none for
`ks1.t`.

### 4.2 Conclusion and logic

1. **Validity.** Valid. The limit was reached and passed on both sides at two boundaries [observed: `cluster/*/summary.txt`, the
   `U − m − T` column]; every task held all eight inputs and ran as a `COMPACTION` with the switch off [observed: the
   `Compacting` and `space check is disabled` lines]; the partitioner, token and `m` of each lifetime are those of 9b
   [observed: `yaml-tail.txt`]; `df` at the trigger was within 16 MiB of *U* (within 7.7 KiB) [observed: `selfcheck.txt`].
2. **Readings.** Arm A's start-up flushes pass the second check site (24 `writeable` lines per lifetime, all before NORMAL)
   [observed: `dds.trace` on the node, `selfcheck.txt` "explains" lines]. The sibling control ran two background tasks: the
   first as predicted, then a resubmitted one that the sibling aborted [observed: `cluster/b_sib/system-window.log`]. In
   `a_m256` the 0.5 s sampler's lowest reading was 21.6 MB and its peak `du` 22.3 MB short of `du₀ + U` [observed:
   `samples.csv` on the node, `selfcheck.txt`].
3. **Matched row.** "Arm B refuses at `U − m < T` before any file, every trace line obeys 'refused iff available <
   estimate', the boundary follows *U* and *m* exactly; arm A prints no guard line, throws no guard message at the same *U*,
   completes into the `m` reserve at `d` = −16 MiB and fails later on a full filesystem at `d` = −256 MiB" — **Confirmed**:
   refusals at −16.8 MB and −268 MB, admissions at +16.8 MB and above, with `m` = 50 MiB (`d` pair) and with `m` = 240/272 MiB
   (the boundary 206 MiB higher, by exactly the change in `m`) [observed: the table]; no new file on any refusal [observed:
   `table-dir-final.txt` = the 8 inputs]; `est` = *T* to the byte and `avail` = `U − m` to the byte at each trigger
   [observed: trace]; arm A: no guard line or exception in any lifetime, minimum free 34.4 MB < 52.4 MB at −16 MiB, and
   `No space left on device` at −256 MiB [observed].
4. **Excluded rows.** "§5 refuted" — arm A printed no guard line and no guard message in four lifetimes. "Operand misread" —
   every guard line's outcome equals `avail < est` and `est` = *T*. "Arm B compacts with `T > U − m`" — never. "Boundary does
   not move with *m*" — at `m` = 50 MiB the guard refused at `U − T` = 34 MiB and admitted at 66 MiB; at `U − T` = 256 MiB it
   admitted at `m` = 240 MiB and refused at 272 MiB: both pairs straddle `U − T = m`, so the boundary moved by the change in
   `m` (206 MiB). "A file of the output exists" — none. "Arm A at −16 MiB fails, or its minimum stays ≥ *m*" — it completed and
   fell to 34.4 MB. "Fewer than eight inputs" — every trigger task held 8 (the sibling control by design). "Sibling's message
   outside the sibling control" — none. "`df` drift > 16 MiB" — none. "Arm A completes although the filesystem cannot hold
   the output" — at −256 MiB it failed.
5. **Observed vs. inferred.** Inferred: that `a_m256`'s filesystem reached 0 available at the failure — the kernel's
   `ENOSPC` (`No space left on device`) says so directly, but the sampler did not catch the instant (its interval is
   0.5 s at ~100–200 MB/s of writing); that the start-up `writeable` lines come from flushes before the node owns ranges
   (`DiskBoundaryManager.java:116-117`, null positions with empty local ranges; the unit tier's t1 shows the same).
6. **Deviations and gaps.** Two frozen sub-predictions are not borne out: (a) "flushes … print `writeable` trace lines on
   arm B and none on arm A" — arm A's start-up flushes before NORMAL also do; (b) the sampler bands at −256 MiB (minimum ≤
   1 MiB, peak within 16 MiB of `du₀ + U`) — resolution, see 5. Neither is in a Conclusions row; the partial output **was**
   removed after the failure (§9a left it open). The second-site flush check on arm B was observed only through the trace
   (no flush was made to fail at the cluster tier; the unit tier shows the failure).
7. **Core question.** On the guarded path the constraint caps usage exactly: a compaction whose estimated output exceeds
   `usable − min_free_space_per_drive` is refused before any file exists, and the refusal point follows both terms to the
   byte (Logic 1–3; parts 1, 3). On the default path it does not run at all: the same compaction eats into the configured
   reserve and, past it, fills the device until the write fails (Logic 4; part 3) — the constraint does not cap usage under
   `Murmur3Partitioner`.

**Conclusion (one line):** §9a row 1 — **confirmed** (including §5's non-domination), with two sub-predictions missed (arm A's
start-up flushes reach the second site; the −256 MiB sampler bands).

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` re-reads every label's raw files on the node with none of the run script's code (`selfcheck.txt`):
**153 checks hold, 7 fail**, and each failure is one of the items in §4.2 part 6, pinned by a passing explanatory check (all
arm-A `writeable` lines before NORMAL and none for `ks1.t`; the sibling's first task = 5 sheds and the guard admitting the 3
smallest inputs' sum exactly).

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.txt` yaml, dataset, `df` and Compacting checks for all 13 labels |
| 2. Readings | yes | the three unusual readings re-derived from `dds.trace`, `system.log`, `samples.csv` |
| 3. Matched row | yes | guard lines re-parsed; `est` = *T* and `avail` = `U − m` per label; refusals leave the 8 inputs (`table-dir-final.txt`) |
| 4. Excluded rows | yes | no guard line in any arm-A trace; `a_m16` minimum 34,447,360 < 52,428,800 |
| 5. Observed vs. inferred | yes | the `ENOSPC` lines re-read (`system-window.log` lines 4–5, 32) |
| 6. Deviations and gaps | yes | the 7 failures are exactly these |
| 7. Core question | yes | follows Logic 1–4 |

### 5.2 Run 2?

**No** — 2026-10-15. The conclusion rests on exact trace operands and file listings, not on inferred statements; the
self-check re-derives every row from raw files; the non-domination finding (a bypass on the default path) was the case's
own §5 prediction and is observed directly in four lifetimes.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

| Tier | Verdict (§9a row) | Basis | Date |
|---|---|---|---|
| Unit | **Confirmed** — exact boundary *T* − 1 refused / *T* admitted on the guarded path; never consulted on the default path (stub 1 admitted); clamp at 0; flush site refused only on the guarded path | run 1 + self-check | 2026-10-15 |
| Cluster | **Confirmed** (row 1, including §5's non-domination); sub-predictions missed: arm-A start-up flushes reach the second site, the −256 MiB sampler bands | run 1 + self-check | 2026-10-15 |

**Feedback filed:** the case file's §10 "Stage-4 feedback" (2026-10-15, uncommitted), with the stage-3 notes: (1) the second
check site guards **every memtable flush** on the null-boundary path, and on any partitioner during start-up before the node
owns ranges; (2) a major compaction (`nodetool compact`) can never reach the guard's disallow, because the sibling admission
check runs first with a budget never above `U − m`; (3) the default path writes into the `min_free_space_per_drive` reserve
and then fills the device (Target-3, confirmed at runtime); (4) after `ENOSPC` the partial output is removed and the inputs
stay. §8's caveat stands as written (confirmed); no section is refuted.
