# tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous — stage-4 results  <!-- file: results/tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous`](../../stage3-ai-deep-read/cases/tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous.md)
>
> **Status:** **Closed 2026-10-26 — unit Confirmed — caps (per read); cluster Not confirmed (partial) — caps per read, node-level heap peak not shown.** Estimate positive. No run 2.
>
> **Outcome class:** undetermined — stage-3 estimate (positive) vs the stage-4 effect (unit: caps per read; cluster: node-level effect not settled) ([definition](../README.md#outcome-class))
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
| **Case-file version** | Case file not yet committed (untracked at audit time; the orchestrator commits). **Frozen version, 2026-10-26, after the audit's amendments A1-A8: sha256 of the whole file `4c289eb01ce314c368a110346c2aee28cb9802f4b307b1df10127ec2f17b0f88`** (pre-audit `c54919847c88774a1a4ff1b0658f91dbb40d592f880729937872b4feda3f5ac7`). Frozen before any reading: sha256 of the B2f-B2g block (prediction and conclusions table, unit) `5cadc0bc5ce254c9816a81f7093f8336b5aea618429af35720680972e6822488`; of the B3f-B3g block (cluster) `679a36ec0609fae1c1e9de2a226921cbc9728aeb5b3b67b963fa9caae041cf1a`; of the amendment block after B2h (A1-A4) `4f32889bba657e6075f1e40b3408efc030ace4b95a43792006ebd862c7e3d47a`; of the one after B3h (A5-A7) `4dc7e9c92e606b9cf64f703d3a06356bf160c8e0ed2b95c606141b0f2bc665eb` (each hashed as the file's text lines of that block, joined by newline, plus a final newline). The case file's section D is edited after the run; that is not a new frozen version. |
| **Harness** | `harness/tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous/` (see its README); not committed (the orchestrator commits). Adapted from the closed twin `harness/tombstone_failure_threshold-countTombstone-tombstones--autonomous/` (same knob, same code path). |
| **Tiers and values** | Unit: T in {1000, 10000, 100000, 120000, 200000, MAX} on 120,000 row tombstones (A2). Cluster: T in {10000, 100000, 1000000}, N = 1,200,000, 8 clients x 300 s, plus size variant, live-row positive control (A5-A7). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26 |

**Note on the freeze.** Amendments A6 and A7 were revised twice on 2026-10-26 after three harness shakedowns (instrument checks, not readings; no reading of this case existed): (1) the live-row control reads use `PAGING OFF` (cqlsh's 100-row pages made every page a separate read command below any 1 MiB cap); (2) A7's decisive per-read measure became the background-corrected node allocation per read A(T), JFR's largest response buffer B(T) became secondary (JFR does not sample allocations below the TLAB size), and P(T) uses the lowest heap level seen as its floor. The hashes above are of the final text; B2f-B2g and B3f-B3g (the prediction and conclusions tables) were never changed.

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A1/A2: heap, but the knob is a count (tombstones) with a derivable byte size (about response bytes per tombstone, measured as s). The entry line (`ReadCommand.java:639`) itself only bumps a metric; the enforcing check is `:591` (one hop up, same `MetricRecording`). |
| A. Core question | knob varied, >= 3 values incl. default | Met | B2b {1000, 10000, 100000}, B3b {10k, 100k, 1M}; 100000 is the default (`Config.java:535`). |
| A. Core question | real resource measured, not only the counter | Partly | B2d(c) retained heap is empty for aborted reads (no `ReadResponse`); the measure that can show the cap is the allocation up to the abort. Gap closed by A2 (thread-allocated bytes) and A7 (JFR response buffer, node heap). Transient merge-heap garbage stays unobservable (named in B2d). |
| A. Core question | usage driven to the limit and past it | Met | N = 120,000 > 100,000 (B2c); 1.2M > 1M (B3c); both abort at every T < N. |
| B. Logic | each step says what it establishes | Met | B1, B2e, B3e. |
| B. Logic | prediction in numbers or a clear relation | Partly | B2f has abort counts (exact) but no number for heap; B3f has MB figures with a factor-3 band. A4/A7 add the precise criteria before any reading. |
| B. Logic | every plausible outcome has a row with evidence | Partly | B2g row 3 untestable as filed (T = 10000 and 100000 both abort, A4); no row for "abort does not save the allocation" or for the node peak saturating (B3, A7). Rows added. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met after A4/A7 | Abort count T+1, `tombstoneFailures`, "Scanned over" lines are the direct evidence; A(T) / B(T) the ceiling. |
| B. Logic | alternative explanations and their controls | Not met as filed | B2h's `system_distributed` control is invalid (`SchemaConstants.java:59-60`, `:118-121`: not a local system keyspace). A3 replaces it with T = MAX and adds a live-row positive control (`ReadCommand.trackWarnings()` `:253`, `withQuerySizeTracking` `:663`). |
| C. Specific | a human can follow it | Met | claim, steps, and table are readable. |
| C. Specific | an AI can run B2e-B3e without re-deriving | Partly | paths (`/localdisk`, `~/cassandra-5.0.9`) do not exist; "client", "5 minutes" and sampling underspecified; `jstat` unavailable (`-XX:+PerfDisableSharedMem`). A1, A5, A6. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | as above; fixed by A1-A7. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | none existed; listed as step-1 work; reuse of the twin's tools (HeapPoll, ThreadAlloc, JfrBuf). JDK 11 and Ant 1.10 present on this host. |
| D. Runnable | workload arithmetic reaches the limit | Met | 120,000 / 1.2M row deletions; ingest via `cqlsh -f` of 60,000 batches; tmpfs data a few hundred MB; 2 GiB heap, 8 x up to about 64 MiB buffers at T = 1M. Cluster time about 25 min. |
| D. Runnable | load-bearing citations spot-checked | Partly | `:639`, `:529-532`, `Config.java:534-535`, `ReadResponse.java:197-201`, `DatabaseDescriptor.java:2832-2849`, `StorageService.java:6711-6731` right; `countTombstone` is `:588`, failure branch `:591-601`, `onClose` `:622` (A8). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| A1 | Real paths, test class name, test yaml read thresholds off for the tombstone arms | applied 2026-10-26 (case file, next to B2h) | filed paths do not exist; the test yaml's 8 MiB thresholds are not node defaults |
| A2 | T set incl. N and 200000/MAX; thread-allocated bytes and response size as observables; `tombstoneWarnings` sub-prediction | applied 2026-10-26 | retained heap of an aborted read is empty |
| A3 | Replace the `system_distributed` control; add a live-row positive control and a negative control | applied 2026-10-26 | `system_distributed` is respected by the check |
| A4 | Decisive criteria c1-c6 and extra rows for B2g | applied 2026-10-26 | row 3 untestable as filed |
| A5 | Node on tmpfs, port slot 1, 2 GiB heap, timeouts, JMX heap polling | applied 2026-10-26 (next to B3h) | `/localdisk` absent; shared host |
| A6 | Delete-only ingest, client definition, size variant at one client, live control table | applied 2026-10-26 | otherwise ambiguous or unsafe for a 2 GiB heap |
| A7 | Definitions of B(T), P(T); decisive criteria b1-b3; row for node-peak saturation | applied 2026-10-26 | the B3f bands name no measurement |
| A8 | Citation fixes in the case file's A section | recorded in section D; the A section text is left for stage 3 | cosmetic, no prediction depends on them |
| S1 | A held-heap reading (a held read plus a class histogram) would test the node-level sentence of B1 | left for stage 3 | outside this design |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (unit 21:30 EDT, cluster 21:31-22:17 EDT) | not done |
| Node (CloudLab name and type) | `pc07`: `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB; shared with other cases running in parallel, own port slot 1) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 (2026-08-18) | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy | `copy-source.sh` copies of `cassandra/cassandra-5.0.9/` (repository HEAD `93d6365`, source tree unmodified): unit `~/s4-b10-tf-src` (`ant build-test`), cluster `~/s4-b10-tf-n` (`ant jar`); local baseline commit `2113bf6` (tag `cassandra-5.0.9`) | |
| Case-file commit / harness commit | case file and harness not committed at run time (orchestrator commits); frozen by sha256 above; harness md5s in `results/<stem>/run1/harness.md5` | |
| Storage for node data | tmpfs `/dev/shm/s4-b10-tf` (126 GB); heap dumps would go to `~/s4-b10-tf-logs/dumps` (none written) | |
| Full logs (path, outside the repo) | `~/s4-b10-tf-logs/run1/` on `pc07` (`unit/`, `cluster/` incl. `system-*.log`, `gc-*.log`); raw JFR files were on `/dev/shm/s4-b10-tf/jfr` until the self-check | |

## 3. Runbook defects

Found by the harness shakedowns (instrument checks, before the freeze above, no reading of this case); each was fixed in the harness or as a pre-run amendment, and none changed B2f-B2g or B3f-B3g. No defect appeared in run 1 itself.

| # | Run | Step (B2e-B3e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | shakedown | B3c (client) | cqlsh's default 100-row pages make each page of the live-row control its own read command (about 110 KB), so `local_read_size_fail_threshold` = 1 MiB never fired | live-control reads use `PAGING OFF` (A6 text) | 2026-10-26 | not committed |
| D2 | shakedown | B3d | `jstat` cannot attach (`-XX:+PerfDisableSharedMem`); JFR does not sample allocations below the TLAB size, so B(T) is unreliable below about 1 MiB; an idle-window baseline for the heap can exceed the storm peak | HeapPoll over JMX; A(T) (background-corrected node allocation per read) is the decisive per-read measure, B(T) secondary, P(T) from the lowest level seen (A7 text) | 2026-10-26 | not committed |
| D3 | shakedown | harness | `nodetool statusbinary` prints "not running", which matched `'running'`; the OOM regex matched the JVM flag `HeapDumpOnOutOfMemoryError` in the startup log | exact match on the first word; regex `java\.lang\.OutOfMemoryError\|OutOfMemoryError:` | 2026-10-26 | n/a (harness) |
| D4 | audit | B2h | the `system_distributed` control is invalid (that keyspace is respected by the check) | A3 | 2026-10-26 | not committed |

## 4. Run 1

**Scope:** unit tier, T in {1000, 10000, 100000, 120000, 200000, MAX} (5 reads each) plus controls; cluster tier, T in {10000, 100000, 1000000} (8 clients x 300 s each), size variant at T = 10000 and 100000, live-row negative control at each T, 1 MiB positive-control lifetime. No run 2. **Command log:** `tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous/run1/` (`unit/summary.txt`, `cluster/session-nocmd.log`, `cluster/summary.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/tfm-unit.tsv`, `run1/unit/summary.txt`; 1 test, 0 failures; A = bytes allocated by the reading thread per read, median of 5)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| pk 0 (120,000 row deletions), T = 1000 / 10000 / 100000 | `TombstoneOverwhelmingException` with count 1001 / 10001 / 100001 (= T+1); `tombstoneFailures` +5 each; `tombstoneWarnings` +0 | `run1/unit/tfm-unit.tsv` |
| pk 0, T = 120000 (= N), 200000, MAX | read succeeds, 120,000 items in a 1,400,426-byte response; failures +0; `tombstoneWarnings` +0 at T = N, +5 at 200000 and MAX | `run1/unit/tfm-unit.tsv` |
| A(T) over the aborting T | 0.68 / 6.53 / 54.73 MB (676 / 653 / 547 B per tombstone counted); 64.82 MB for every read that scans all 120,000 (540 B per tombstone); A(1000)/A(MAX) = 0.0104 | `run1/unit/tfm-unit.tsv`, `unit/summary.txt` |
| pk 1 (30,000 live rows, 1 KB each), every T | all OK, 30,390,031-byte response, A = 110.73 MB at every T (max/min 1.000), no tombstone metrics | `run1/unit/tfm-unit.tsv` |
| positive control, 1 MiB `local_read_size_fail_threshold` on pk 1, `trackWarnings()` | `LocalReadSizeTooLargeException` on the last of 5 repetitions (A identical, min = max); A = 3.36 MB against 111.37 MB unrestricted | `run1/unit/tfm-unit.tsv` |
| `unit-analyze.py` | c1-c6 and control all yes; `MATCHED: B2g row 1` | `run1/unit/summary.txt` |

**Cluster tier** (`run1/cluster/summary.txt`, `readings.csv`, `phases.json`; node 2 GiB heap, G1 with 16 MiB regions as shipped)

| Capacity value | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| ingest | setup | pk 0 of `ks.t` | 1,200,000 tombstone cells and 0 live rows read back at T = MAX (first-trigger check); `ks.t2` 120,000 markers | `run1/cluster/check-trace.out`, `check-trace-t2.out` |
| T = 10000 | main (8 clients x 300 s) | reads / outcomes | 3,855 reads, all `READ_TOO_MANY_TOMBSTONES`; `system.log` "Scanned over 10001 tombstones" x3,859 (incl. warm-up and the variant's 3); `TombstoneFailures` 3,856 | `run1/cluster/summary.txt`, `session-nocmd.log`, `scanned-summary.txt` |
| T = 10000 | main | A (node allocation per read) / B (largest response buffer, JFR) / P (peak heap rise) | 10.66 MB / 0.13 MiB / 1,262 MB | `run1/cluster/readings.csv`, `alloc-*-T10000-main.txt`, `jfr-T10000-main-head60.tsv`, `heap-storm-T10000-main.txt` |
| T = 100000 (default) | main | reads / outcomes | 3,051 reads, all `READ_TOO_MANY_TOMBSTONES`; "Scanned over 100001 tombstones" x3,055; `TombstoneFailures` 3,052 | same |
| T = 100000 | main | A / B / P | 69.39 MB / 2.0 MiB / 1,258 MB | same, `T100000` |
| T = 1000000 | main | reads / outcomes | 872 reads, all `READ_TOO_MANY_TOMBSTONES`; "Scanned over 1000001 tombstones" x873; `TombstoneFailures` 873 | same |
| T = 1000000 | main | A / B / P | 612.65 MB / 16.0 MiB / 1,817 MB (absolute peak 2,068 MB of 2,048 MiB heap) | same, `T1000000` |
| T sweep | main | ratios | A: 6.51x then 8.83x per decade; B: 16x then 8x; P: 1.00x then 1.44x | `run1/cluster/summary.txt` |
| T = 10000 / 100000 | size variant (1 client x 3 reads on 120,000 markers with 1000-char clusterings) | outcome / B / A | all aborted at T+1; B = 16.1 / 144.7 MiB (1,686 / 1,517 B per marker against 13 / 21 B per row tombstone, ratio 72-129x); A = 50.3 / 516.8 MB | `run1/cluster/summary.txt`, `jfr-T10000-variant.tsv`, `jfr-T100000-variant.tsv` |
| every T | live-row negative control (`ks.live`, `PAGING OFF`) | outcome / A | 3/3 OK (30,000 rows) at each T; A = 154.4 / 155.8 / 156.1 MB, flat; `TombstoneFailures` unchanged | `run1/cluster/summary.txt` |
| T = 100000 + `read_thresholds_enabled`, 1 MiB `local_read_size_fail_threshold` | positive control | outcome / A | 3/3 `READ_SIZE` failures; A = 16.4 MB against 155.8 MB unrestricted | `run1/cluster/summary.txt`, `session-nocmd.log` |
| all lifetimes | OOM / full GC | `system.log`, gc logs | no `OutOfMemoryError`; no Pause Full; pauses 45 / 183 / 1,251 and highest post-GC occupancy 151 / 1,293 / 1,704 MB at T = 10000 / 100000 / 1000000 | `run1/selfcheck.txt` |

### 4.2 Conclusion and logic

1. **Validity** — valid. [observed: `run1/cluster/session-nocmd.log`] Each lifetime read back its T through JMX (10000, 100000, 1000000) and its traced warm-up read failed with `READ_TOO_MANY_TOMBSTONES` (the stop-on-failure first-trigger check); the setup check read exactly 1,200,000 tombstones and 0 live rows [observed: `check-trace.out`]. The limit was reached on every read: N (1.2M) exceeds every T [observed: `summary.txt`]. Hold-fixed settings: `read_thresholds_enabled: false` in the tombstone lifetimes, `concurrent_reads: 4`, 2 GiB heap, 8 clients, fresh JVM per T [observed: `session-nocmd.log` "conf for T=..." lines]. The positive control moved usage (A 16.4 against 155.8 MB), so the instrument could show a cap that binds [observed: `summary.txt`]. Unit: c1-c6 and the control hold [observed: `unit/summary.txt`].
2. **Readings** — the response buffer B(T) is far smaller than B3f predicted (0.13 / 2.0 / 16.0 MiB against about 1 / 10 / 100 MB) because a row tombstone with an `int` clustering serializes to 11.7 bytes (1,400,426 B / 120,000) [observed: `tfm-unit.tsv`], not the assumed 100 bytes; the per-read allocation is much larger (10.7 / 69.4 / 612.7 MB) because each tombstone scanned costs about 540-650 B of transient merge and iterator garbage [observed: `tfm-unit.tsv`, `readings.csv`]. The JFR B(T) is quantised by buffer doubling and below the TLAB size it is not sampled [observed: D2].
3. **Matched row** — unit: B2g row 1, "Abort at T+1 for every T, response size grows with T when T > 120000": abort count T+1 at 1000 / 10000 / 100000 and a constant 1,400,426-byte response for every T >= N [observed: `tfm-unit.tsv`], with A(T) strictly increasing (0.68, 6.53, 54.73 MB) and A(1000) at 1.0 % of A(MAX) [observed]. Cluster: the A7 row added before any reading, "b1 and b2 hold and b3 fails (the node peak saturates)": 7,778 of 7,778 main reads failed with the tombstone code and every logged count was T+1 (b1) [observed: `summary.txt`]; A grew 6.5x then 8.8x per decade, inside [3.3, 30] (b2) [observed]; P(T) = 1,262 / 1,258 / 1,817 MB, ratios 1.00 and 1.44, outside [3.3, 30] and not increasing between 10000 and 100000 (b3 fails) [observed: `readings.csv`]. Result: *Not confirmed (partial)*.
4. **Excluded rows** — unit row 2 ("Read succeeds with count above T"): no read succeeded with a count above T (c1) [observed]. Unit row 3 (retained or allocated heap the same across T): A(1000) is 1.0 % of A(MAX) and the aborting values increase [observed]. Unit last row ("abort at T but no memory difference ever shows"): a difference does show, in A. Cluster row 1 ("Heap above baseline scales about linearly with T"): b3 fails. Cluster row 2 ("Peak heap equal at 10000 and 1000000"): A differs 57x and P differs 1.44x, B differs 123x, so the per-read measures are not equal; P(10k) and P(100k) are equal within 0.4 % but P(1M) is higher, which the A7 partial row covers. Cluster row 3 ("Reads at T=1000000 succeed with tombstones counted far above T"): none of the 872 reads succeeded [observed]. Cluster row 4 ("bytes per tombstone vary 10x between row and range variants"): observed in a stronger form, 72-129x (1000-character clusterings against `int` clusterings), so the cap bounds the count, not the bytes [observed: size variant rows]. Cluster row 5 ("Positive control does not move heap"): it moved (A 16.4 against 155.8 MB, 3/3 `READ_SIZE` failures) [observed].
5. **Observed vs. inferred** — inferred: (i) that the response buffer (`DataOutputBuffer` in `ReadResponse.LocalDataResponse.build`, `ReadResponse.java:197-201`) is the memory a read holds, while the 540-650 B per tombstone of allocation is garbage freed after the read [inferred: the code path, and the GC logs showing no full GC and post-GC occupancy far below the allocated volume per read]; (ii) that P(T) saturates because eight concurrent reads allocate 69-613 MB each and fill the 2 GiB heap's young generation and humongous regions before a collection [inferred: gc logs, 183 and 1,251 pauses, post-GC occupancy 1,293 and 1,704 MB at T = 100000 and 1000000]; (iii) that A(T) is the transient allocation of the scan, since a straight line through A(10,000) and A(100,000) has a slope of 652 B per tombstone and an intercept of about 4.1 MB per request, and the next decade has a slope of 604 B [inferred: arithmetic on `readings.csv`].
6. **Deviations and gaps** — A6's omission of the `INSERT` before the `DELETE` (flushed state identical); the size variant ran one client and the live control `PAGING OFF` (D1); P(T) is an allocation-pressure measure, not a held-heap measure (a held read plus a class histogram, recommendation S1, was not run); B(T) from JFR is secondary; the unit tier's secondary retained-heap reading (`retained_bytes`) is noisy (2.1 MB for the response of 1.4 MB, 33-45 MB for the 30 MB live response) and is not used; run 2 not done.
7. **Core question** — the failure threshold caps the memory one read can use: the replica aborts at T+1 tombstones, the response buffer it would hold is at most (T+1) x its tombstone size (0.13 / 2.0 / 16.0 MiB for row tombstones; 145 MiB at T = 100000 for 1000-character range markers), and the allocation a read performs is proportional to min(T+1, N) (c2-c4, b2). Usage at the replica follows the constraint per read (Logic steps 1-3). It does not cap the node's heap under eight concurrent tombstone-heavy reads: the peak of the heap in use is already 1.26 GB at T = 10000, is the same at the default 100000 (1.26 GB) and reaches 2.07 GB (the whole 2 GiB heap) at T = 1,000,000, so the node-level sentence of B1 is not shown (step 4).

**Conclusion (one line):** unit — B2g row 1, confirmed (caps per read); cluster — the A7 row "b1 and b2 hold and b3 fails": **Not confirmed (partial)**, caps per read, node-level heap peak not shown.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/<stem>/selfcheck.py` re-parsed the raw files (junit logs, `session.log`, `system.log` segments, HeapPoll files, ThreadAlloc files, gc logs, raw `.jfr` through `jfr print --json`), not the analyzers' outputs. Output: `run1/selfcheck.txt`.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | T read-back lines and the warm-up failures in `session-nocmd.log`; 1,200,000 tombstones in `check-trace.out`; no OOM in `system-*.log` (self-check CHECK lines) |
| 2. Readings | yes | A per read recomputed from the raw ThreadAlloc files: 10.66 / 69.39 / 612.65 MB (identical); raw JFR maxima of `expandToFit`: 0.13 MiB (T = 10000), 2.0 MiB (100000), 16.0 MiB (11,806 events of 7.18M) (1000000), 16.1 / 144.7 MiB (variant) |
| 3. Matched row | yes | self-check re-derived: unit c1-c6 and control; cluster b1 (7,778 reads, log counts >= reads, every value T+1), b2 (ratios 6.51, 8.83), P ratios 1.00 / 1.44 so b3 fails |
| 4. Excluded rows | yes | no OK read in any main storm (`session-nocmd.log` outcomes); control A 16.37 against 155.84 MB; variant ratio 72-129x |
| 5. Observed vs. inferred | yes | the inferred statements are labelled; gc logs show 0 full GCs and max post-GC 151 / 1,293 / 1,704 MB (self-check output) |
| 6. Deviations and gaps | yes | listed in 4.2 part 6; none changes the matched row |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | per-read follows T (b2, c2-c4); node-level peak does not (b3) |

### 5.2 Run 2?

**No** — decided 2026-10-26. The verdict on each tier is a table row that the raw files fix (aborts at exactly T+1, an allocation ratio per decade, a peak that does not scale); the inferred statements (what the read holds, why the peak saturates) do not change which row matches, and the cluster result repeats the closed twin's outcome for the same knob (`tombstone_failure_threshold-countTombstone-tombstones--autonomous`, unit Confirmed, cluster Not confirmed (partial)). A run 2 would cost another 35 minutes of the shared node for no new information. A held-heap run (S1) is the experiment that could settle the node-level sentence, and it is a new design, not a repeat.

## 6. Run 2 — fresh AI session (optional)

Not done (see 5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive (qualified: the per-read tombstone count is capped by `tombstone_failure_threshold` and tombstones are buffered on heap in the replica's data response, so heap per read is bounded by roughly threshold x tombstone size; the bound is a count, not bytes). **Outcome class:** undetermined — the unit tier found `caps` (per read) and the cluster tier could not settle the node-level effect (Not confirmed, partial).

**Claim tested:** B1 — "Lowering or raising `tombstone_failure_threshold` moves the peak heap that a single tombstone-heavy read holds on a replica roughly in proportion to the threshold, and a read that would exceed it fails instead of growing. If heap use per read stays flat as the threshold changes while the read succeeds or fails as expected, the cap does not govern memory." "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (abort at exactly T+1 for T = 1000 / 10000 / 100000; allocation per read 0.68 · 6.53 · 54.73 MB, then 64.82 MB at T >= N; response 1,400,426 B at every T >= N; live control flat at 1.000; 1 MiB read-size control aborts (LRS) and allocates 3.36 against 111.37 MB) | caps (per read) | run 1 + self-check | 2026-10-26 |
| Cluster | **Not confirmed (partial)** — the A7 row "b1 and b2 hold and b3 fails": 7,778/7,778 reads abort at T+1; allocation per read 10.7 · 69.4 · 612.7 MB (6.5x, 8.8x per decade); response buffer 0.13 · 2.0 · 16.0 MiB; node heap peak rise 1,262 · 1,258 · 1,817 MB (1.0x, 1.4x) | caps (per read); the node-level heap peak is not capped by it (undetermined as a held-heap reading) | run 1 + self-check | 2026-10-26 |

**Positive control** (a negative-estimate file only): not required (positive estimate); run anyway: the 1 MiB `local_read_size_fail_threshold` on a 30 MB live partition moved usage at both tiers (unit A 3.36 against 111.37 MB; cluster 16.4 against 155.8 MB), so the instruments could show a binding cap. The live partition read at each T was flat (cluster A 154.4 / 155.8 / 156.1 MB), so T does not touch non-tombstone reads.

**Findings beyond the claim (no table row):**
1. A tombstone costs 11.7 B in the response but 540-650 B of transient allocation while it is scanned (unit A / count). The threshold therefore bounds the held response at about (T+1) x 11.7 B (1.4 MB at the default for row tombstones) while one aborting read at the default still allocates about 55-69 MB; at T = 1,000,000 about 0.6 GB. The cap is a count, not bytes: 100,000 range markers with 1000-character clusterings give a 145 MiB response buffer (about 1.5 KB each, 72-129x the row tombstone).
2. Eight concurrent clients at the default T = 100000 already drive the heap to about 1.3 GB of the 2 GiB (P = 1,258 MB, post-GC occupancy up to 1,293 MB), the same as at T = 10000 (1,262 MB). The threshold does not bound the node's heap under concurrent tombstone-heavy reads.
3. Boundary quirk (metric only, no memory effect): `tombstoneWarnings` is bumped only when `tombstones < failureThreshold` (`ReadCommand.java:639`), so a read that completes with exactly T tombstones logs the warning but does not increment the metric (unit T = N = 120000: +0, while T = 200000 and MAX: +5). Aborted reads (count T+1) never increment it.
4. Reads of a tombstone-only partition do not fill a page, so cqlsh's 100-row paging does not limit the scan: one page scans to the threshold (all 7,778 main reads).

**Feedback filed:** the case file's section D updated 2026-10-26 (audit amendments A1-A8 already in the file next to B2h and B3h; run 1 summary in D). New sha256 of the whole case file after section D: `808d47c853598f91af58f606876bd2a70f9571e16b19942d779b1e9d393587a7` (not a new frozen version; for `_INDEX.md` §4). Not committed (the orchestrator commits).

**Leftovers on the node:** the tmpfs directory `/dev/shm/s4-b10-tf` (node data, JFR files) is removed; kept on local disk for the record: trees `~/s4-b10-tf-src` and `~/s4-b10-tf-n`, logs `~/s4-b10-tf-logs/`. No process left running.
