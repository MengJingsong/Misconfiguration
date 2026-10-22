# tombstone_failure_threshold-countTombstone-tombstones--autonomous — stage-4 results  <!-- file: results/tombstone_failure_threshold-countTombstone-tombstones--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`tombstone_failure_threshold-countTombstone-tombstones--autonomous`](../../stage3-ai-deep-read/cases/tombstone_failure_threshold-countTombstone-tombstones--autonomous.md)
>
> **Status:** **Closed 2026-10-21 — unit Confirmed — caps (per read); cluster Not confirmed (partial) — caps per read, node-level peak not shown** (B3g row added by audit amendment R6). Estimate positive. No run 2.
> 
> **Outcome class:** undetermined — stage-3 estimate vs the stage-4 effect on the constraint
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file. As filed (untracked, 2026-10-21): sha256 `1fc393050f3a350d255f5478fc5d4805372fcfdc6958457f36c21cc6e09f4bf7`. After the step-0 audit amendments R1–R6: **`9e62de3a079dff64b91da43ece36e12c03ec93cffeb5709e3f6b140fed1f5c89`, the frozen version** (written before any reading). After runbook fix D1 (unit attempt 1, §3): `677b8abbe2e50fe4094fd6de070dbf6efc3724c779e0e7ef2939a0f0a7e318e4`, **the version the counted unit run used**. After runbook fixes D2–D3 (cluster instrument checks, before any cluster reading): `b509de1d184a2d23fe3cbe79c7c7011af9371ee5023fc71efb286aa58713041f`, **the version the cluster run used**. B1, B2f–B3g and R1–R6 are unchanged by D1–D3, except that D2 moves R4's criteria (c) and (d) from the EU + OU rise to the OU rise. The file is not committed; the repo HEAD was `a74026e`. |
| **Harness** | [`harness/tombstone_failure_threshold-countTombstone-tombstones--autonomous/`](../harness/tombstone_failure_threshold-countTombstone-tombstones--autonomous/README.md) written 2026-10-21 (not committed): `TombstoneFailureThresholdMemoryTest.java` (B2e test + R1, R2, D1), `unit-run.sh`, `unit-analyze.py`, `cluster-run.py`, `cluster-analyze.py`, `HeapPoll.java` (D3), `ThreadAlloc.java` (R5), `JfrBuf.java`, `selfcheck.py`, `README.md`. **Instrument checks (not readings):** unit shakedown1 (N = 300 copy, T / 100); cluster shakedown2 (N = 2,000: found D3 and a stop-wait bug in the script), shakedown2b and shakedown3 (N = 2,000 and 20,000, T scaled; checked JFR matching, `HeapPoll`, the analysis). md5 of the node copy: `pc13:~/stage4-logs/tft/run1/harness.md5`. |
| **Tiers and values** | Unit (B2): T = 1,000 · 10,000 · 20,000 · 29,999 · 30,000 · 100,000 (default) · `Integer.MAX_VALUE`, N = 30,000 tombstones of ≈ 1 KB, 5 reps, plus the live-row control. Cluster (B3): one node, 8 GiB heap, T = 1,000 · 20,000 · 100,000 (default) · 300,000 · 1,000,000, N = 200,000, 8 × 5 concurrent `cqlsh` reads per T, live control at T = 1,000 and 1,000,000. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-21 |

### 1.1 Design audit

Checked against the pinned source (`/proj/misconfiguration-PG0/git-repos/cassandra-src` at `cassandra-5.0.9`, read only).

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: heap held by one read's response buffer; the knob is a count with a derivable byte size (s ≈ 1 KB per tombstone by construction of the workload). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b seven values incl. 100,000; B3b five values incl. 100,000. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | Unit: per-thread allocated bytes (real heap allocation, not retention); B2d item 4 names the gap. Cluster: JFR allocation sizes and a `jstat` peak, which includes garbage (eden) as well as live buffers; B3d item 5 names the gap. R4 defines the statistics, R5 adds a node-wide allocation reading because JFR's out-of-TLAB events miss small buffers. |
| A. Core question | usage driven to the limit and past it | **Not met as filed** → Met after R1 | As filed, `INSERT … null` writes live rows (`UpdateStatement.java:73-74`) and `cqlsh` pages at 100 rows (`cqlshmain.py:362, 945`), so each cluster command scans ≤ 100 tombstones and no T ≥ 100 could be reached. R1 writes the tombstones with `UPDATE … SET v = null`. Unit tier was unaffected (it reads with `DataLimits.NONE`) but contradicts B1's "no live rows"; R1 applies there too. |
| B. Logic | each step says what it establishes | Met | B2h/B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f/B3f: outcome and count T+1 exactly; allocation ∝ min(T+1, N), with bands. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | Missing: unit "abort saves only part" (between row 1 and row 2); cluster "buffers follow but peak heap does not"; "buffers do not follow". Added (R6). "≈", "grows linearly", "follows" undefined → defined (R4). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Disallow evidence: `TombstoneOverwhelmingException` with "Scanned over T+1", `TombstoneFailures`, system.log ERROR lines; ceiling: A(T) / buffer sizes per T. |
| B. Logic | alternative explanations and their controls | Met | Live-row partition (T-independence), T = MAX / 1M (positive control), T = N−1/N (boundary), restart per T, raised timeouts (cancellation), `read_thresholds_enabled` off (byte cap). |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | Estimate line, A3, B1. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Met | B2e is a complete test; B3e commands are given. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Peak-heap baseline statistic, `TombstoneFailures` delta with the warm-up, and the order of the live-control storms are unstated (R4); `native_transport_timeout` and `ulimit -n` missing (R3). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | The filed test cannot load: `ORIGINAL` is read in a static initialiser before `DatabaseDescriptor` is initialised (`DatabaseDescriptor.java:2842-2845`, `CQLTester.java:403-414`) → R2. JDK 11 on pc13 has `jcmd`, `jstat`, `jfr`. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met after R1 | 200,000 × ≈ 1 KB = ≈ 0.2 GB data; uncapped 8 × ≈ 216 MiB buffers fit in 8 GiB; unit 30 MB per read in a 1 GiB test JVM. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `ReadCommand.java:366-374, 421-504` (chain order `:455-459`), `:525-654` (`MetricRecording`; T read at `:529`, the check at `:591`, the throw at `:601`), `ReadResponse.java:197-210`, `StorageProxy.java:2207-2248`, `ReadCommandVerbHandler.java:88-100`, `DataOutputBuffer.java:57, 158-182` (heap: `BufferedDataOutputStreamPlus.java:75-77`; only the scratch buffer is direct), `TombstoneOverwhelmingException.java:27-33` (extends `RejectException`; message carries T+1), `Config.java:179, 526, 534-535, 1399`, `conf/cassandra.yaml:1814-1815, 2015`, `DatabaseDescriptor.java:2842-2850`, `StorageService.java:6722-6731`, `build.xml:125, 1153`. Several `ReadCommand` citations are off by one line (S1). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Write the tombstones with `UPDATE … SET v = null` (no row liveness), both tiers; correct cqlsh's page size (100) and the pk = 1 prediction wording | Applied 2026-10-21 (amendment block before section C; not committed) | As filed the cluster limit is unreachable: live rows end each 100-row page before any T ≥ 100 |
| R2 | Read `ORIGINAL` in a `@BeforeClass` method | Applied 2026-10-21 | The filed class fails to initialise (NPE on `DatabaseDescriptor.conf`) |
| R3 | `native_transport_timeout: 180s`; `ulimit -n 100000` | Applied 2026-10-21 | a 200 MB read may approach the 12 s client timeout; the node's soft fd limit is 1024 |
| R4 | Define the decisive criteria of B2g row 1 and B3g row 1, the peak-heap statistic, the `TombstoneFailures` delta and the order of storms | Applied 2026-10-21 | "≈", "linearly", "follows", "baseline" were undefined |
| R5 | Supplementary node-wide thread allocation per read (JMX) | Applied 2026-10-21 | JFR out-of-TLAB events miss buffers that fit in a TLAB, so the per-read JFR sum under-counts at T = 1k |
| R6 | Three added rows (B2g partial saving; B3g peak heap not shown; B3g buffers not following) | Applied 2026-10-21 | outcomes without a row |
| S1 | `ReadCommand` line citations off by one (`:528`→`:529`, `:531`→`:532`, `:558-565`→`:559-566`, `:587-602`→`:588-603`); the entry pointer `:591` is right | Left for stage 3 | not load-bearing |
| S2 | B3f's "≤ 2 MB (no humongous growth)" at T = 1k: a 2 MiB buffer would be humongous with 4 MiB regions (≥ half a region); the content (≈ 1.02 MB) most likely fits a 1 MiB buffer | Left for stage 3 | sub-prediction wording only |
| S3 | The `jstat` peak (max EU + OU) measures allocation pressure as much as retention; a retained-heap reading would need a held read (Byteman) and a class histogram | Left for stage 3 | R4/R6 make the decisive rows rest on buffer sizes; the peak is reported |

**Agreement criteria** — only if run 2 is chosen.

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-21, MDT: unit shakedown 15:42; unit attempt 1 15:43:54 (D1); counted unit run 15:45:44–15:46:11; cluster shakedowns 15:46–15:58; cluster run 15:59:02–16:22:52 (ingest 15:59:46–16:15:24) | not done |
| Node (CloudLab name and type) | `pc13` = `node3.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB; no other session used it. Driven over ssh from `pc07`. The node listened on 127.0.0.1 with ports 7100 / 7101 / 9142 / JMX 7299 as filed. | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | — |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18); `jcmd`, `jfr` from the same JDK | — |
| Ant (`ant -version`) | 1.10.12 | — |
| Local `cassandra-src` clone commit | fresh `~/cassandra-tft` at `cassandra-5.0.9` (`b5f2a54210d541339c2e7c17a794195cac0e67c2`), `ant build-test` 1 min 12 s; used for both tiers instead of B2a/B3a's `~/cassandra-run1` (environment deviation E1; the design is unchanged). The test file was removed after the unit run (B2e step 5); the clone is clean. | — |
| Case-file commit / harness commit | case file untracked (HEAD `a74026e`): unit run on `677b8abb…`, cluster run on `b509de1d…`; harness not committed (md5 in `pc13:~/stage4-logs/tft/run1/harness.md5`) | — |
| Storage for node data | `/local/tft-run` on local `/dev/sda3` (55 GB free); removed at the end (B4) after copying `client/`, `jfr/`, `logs/`, `conf/` to `~/stage4-logs/tft/run1/cluster-raw/` | — |
| Full logs (path, outside the repo) | `pc13:~/stage4-logs/tft/` — `run1/unit/` (ant log, test.log, junit XML, tsv), `run1/cluster/` (session.log, phases.json, reads.csv, HeapPoll `jstat-*`, `alloc-*`, `jfr-*.tsv`, `system-<T>.log` segments, `gc-<T>.log`), `run1/cluster-raw/` (raw `.jfr`, every client output, node logs and conf), `run1/selfcheck.txt`; `run1-unit-attempt1/`; shakedowns `shakedown1`, `shakedown2a`, `shakedown2b`, `shakedown3` | — |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | unit, run-1 attempt 1 | B2a/B2e | The unit tests' yaml enables the byte-based read thresholds (`test/conf/cassandra.yaml:63-69`, 8 MiB row-index and local-read caps), unlike a node (`Config.java:526`). Every pk = 0 read aborted with `RowIndexEntryReadSizeTooLargeException` (estimated 12,647,595 B, `RowIndexEntry.java:401`) before the tombstone check; 0 TFT lines (`run1/unit/attempt1-and-shakedown-excerpt.txt`). | The test sets `read_thresholds_enabled` false in `@BeforeClass` (restored after), as on a default node. The unit tier restarted from its beginning; attempt 1 is not counted. | 2026-10-21, dated runbook fix D1 | none (not committed) |
| D2 | cluster shakedown2a (instrument check) | B3a/B3d, R4 (c)/(d) | B3a assumes a 4 MiB G1 region, but the copied `conf/jvm11-server.options` sets `G1HeapRegionSize=16m` (`:66`) and `G1NewSizePercent=50` (`:70`) (seen in the node's JVM arguments). Eden is ≥ 4 GiB, so the EU + OU peak measures allocation pressure. | Keep the shipped options; R4's criteria (c) and (d) read the **OU** peak rise (buffers ≥ 8 MiB are humongous, allocated in old regions); EU + OU still reported against B3f's bands; humongous regions × 16 MiB. | 2026-10-21, dated runbook fix D2 (before any cluster reading) | none |
| D3 | cluster shakedown2a (instrument check) | B3d item 2 | `jstat -gc <pid>` fails ("MonitorException: <pid> not found") because `conf/jvm-server.options:137` sets `-XX:+PerfDisableSharedMem`. | EU and OU are read every 250 ms from the JMX memory pools by `HeapPoll`. | 2026-10-21, dated runbook fix D3 | none |
| H1 | cluster shakedown2a | harness | `stop_node` waited on the pid file, which the node removes before the JVM exits; the next start found the old daemon and aborted. Also the OOM test matched `-XX:+HeapDumpOnOutOfMemoryError` in the logged JVM arguments, and JfrBuf's first match counted row deserialization under `LocalDataResponse.build` as buffer growth. | Wait on `/proc/<pid>`; match `java.lang.OutOfMemoryError`; only stacks with `DataOutputBuffer.expandToFit` count as the response buffer. | 2026-10-21, harness only | — |

Environment deviation E1: the fresh clone `~/cassandra-tft` instead of `~/cassandra-run1` (both tiers).

## 4. Run 1

**Scope:** unit tier B2 (7 T × 2 partitions × 5 reps, counted attempt 2), cluster tier B3 (T = 1M · 300k · 100k · 20k · 1k, one fresh lifetime each, 40 reads per storm, live control at 1M and 1k). **Command log:** [`tombstone_failure_threshold-countTombstone-tombstones--autonomous/run1/`](tombstone_failure_threshold-countTombstone-tombstones--autonomous/run1/) (`unit/summary.txt`, `unit/tft-unit.tsv`, `unit/tft-lines.txt`; `cluster/summary.txt`, `readings.csv`, `phases.json`, `reads.csv`, `session.log`, `syslog-excerpt.txt`, `trace-excerpt.txt`, `scanned-*.txt`, `alloc-*.txt`, `jstat-*.txt` (HeapPoll samples), `jfr-*-1MB.tsv`; `selfcheck.py`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`; `Tests run: 1, Failures: 0, Errors: 0`, 27 s; analysis 13 yes / 1 NO; s = 30,287,664 / 30,000 = 1,009.6 B per tombstone)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| pk 0 outcome and count | T = 1,000 · 10,000 · 20,000 · 29,999: `TombstoneOverwhelmingException`, "Scanned over" 1,001 · 10,001 · 20,001 · 30,000; T = 30,000 · 100,000 · MAX: OK, 30,000 unfiltered, `resp_bytes` 30,287,664 | `unit/tft-unit.tsv`, `unit/tft-lines.txt` |
| pk 0 allocation per read (median of 5) | 4.10 · 53.36 · 106.68 · 126.39 MB at T = 1k · 10k · 20k · 29,999; 125.89 MB at T = 30,000 · 100,000 · MAX. A(1k)/A(MAX) = 0.033; A/(s · min(T+1, N)) = 4.06 · 5.28 · 5.28 · 4.17 · 4.16 | same |
| pk 1 (live control) | OK at every T, 30,257,666 B, 30,000 rows; allocation 121.3–123.0 MB, max/min 1.014 | same |
| B2f ratio bands | A(10k)/A(1k) = 13.01 (band 7–13: **missed by 0.01**); A(20k)/A(10k) = 2.00 (1.6–2.4) | `unit/summary.txt` |

**Cluster tier** (`run1/cluster/summary.txt`, `readings.csv`; analysis 24 yes / 9 NO; B3e step 4 trace: "Read 0 live rows and 200000 tombstone cells", data on disk 10.8 MB after LZ4 compression)

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| each T | all | T in force | the node's config dump and `sjk mx -mg` read back 1,000,000 · 300,000 · 100,000 · 20,000 · 1,000 | `syslog-excerpt.txt`, `session.log` |
| 1k · 20k · 100k | pk 0 storm | client outcome | 40/40 `ReadFailure … READ_TOO_MANY_TOMBSTONES` each | `reads.csv` |
| 1k · 20k · 100k | pk 0 | operand | 41 ERROR lines each (warm-up + 40), all "Scanned over 1001 / 20001 / 100001 tombstones" (`StorageProxy.java:2248`); `TombstoneFailures` +40 per storm | `syslog-excerpt.txt`, `scanned-*.txt`, `summary.txt` |
| 300k · 1M | pk 0 | client outcome, operand | 40/40 OK, 0 rows; no ERROR line; `TombstoneScannedHistogram` Max 219,342 (bucket of 200,000) | `reads.csv`, `summary.txt` |
| 1k · 20k · 100k · 300k · 1M | pk 0 | max response buffer (JFR, `expandToFit`) | 1.05 · 33.62 · 151.29 · 226.93 · 226.93 MB (1.00 · 32.06 · 144.28 · 216.42 · 216.42 MiB) = 1.04 · 1.66 · 1.50 × s(T+1) for the failing T | `jfr-*-1MB.tsv`, `readings.csv` |
| same | pk 0 | node allocation per read (R5) | 8.0 · 103.1 · 544.2 · 1,176.1 · 1,152.9 MB | `alloc-*.txt` |
| same | pk 0 | OU peak rise (D2) | 0.25 · 4,009 · 6,050 · 6,015 · 6,262 MB | `jstat-*.txt` |
| same | pk 0 | EU + OU peak rise (as filed) | −402 · 6,308 · 5,710 · 5,369 · 5,777 MB | same |
| same | pk 0 | gc.log max humongous regions (× 16 MiB) | 0 · 6 · 355 · 357 · 408 | `summary.txt` |
| 1k · 1M | pk 1 (live control) | outcome, buffer, allocation, OU | 40/40 OK with 20,000 rows at both; max buffer 0.13 MB at both; node allocation 129.8 vs 127.0 MB per read; OU rise 22.3 vs 0 MB; EU + OU 3,221 vs 2,819 MB | `reads.csv`, `readings.csv` |
| all | all | OOM | none | `syslog-excerpt.txt`, `summary.txt` |

### 4.2 Conclusion and logic

1. **Validity.**
   - Unit: every T was set and read by its own command (the throw counts T+1 exactly), 5 reps each; T ≥ N reads returned all 30,000 tombstones, so the workload reaches and passes every T [observed: `unit/tft-unit.tsv`]. The partition has no live rows (R1) [observed: unfiltered 30,000 and the cluster trace's "Read 0 live rows"].
   - Cluster: each T in its own lifetime, read back two ways [observed: `syslog-excerpt.txt`, `session.log`]; all 200,000 tombstones visible to one command [observed: `trace-excerpt.txt`]; no OOM, no cancellation, no read-size threshold (`read_thresholds_enabled` unset; no other ERROR) [observed: `syslog-excerpt.txt`]. Valid.
2. **Readings.**
   - (a) The EU + OU and OU peaks saturate near 6 GB from T = 100k on and are already 4 GB at T = 20k, where 8 concurrent buffers hold at most 8 × 32 MiB [observed: `readings.csv`]. With 16 MiB regions every buffer of ≥ 8 MiB (and every growth step above it) is a humongous allocation in old regions, and these accumulate as garbage until a GC: 40 reads × (32 + 16 + 8 MiB) ≈ 2.3 GB of humongous allocation at T = 20k, ≈ 15 GB at 100k and ≈ 24 GB at T ≥ 300k (each growth step from 8 MiB up) [inferred: buffer growth chain and the humongous counts 6 / 355 / 357 / 408]. So the OU peak measures humongous garbage up to the GC trigger (IHOP 70 % of 8 GiB ≈ 5.7 GB), not the buffers held at once.
   - (b) At T = 1k the read thread's JFR out-of-TLAB sum (0.35 MB/read) under-counts as R5 anticipated; the node-wide allocation is 8.0 MB/read [observed].
   - (c) The live control's OU rise of 22 MB at T = 1k (0 at 1M) is a promotion at a young GC during a 26 s storm, unrelated to T [inferred: no humongous region in that lifetime; maximum buffer 0.13 MB at both].
3. **Matched rows.**
   - **Unit, B2g row 1** ("throws exactly when T < N, with count = T+1; A(T) grows linearly in min(T+1, N) and is flat for T ≥ N; pk = 1 flat"), with R4's criteria: throws exactly for the four T < N with count T+1; A increasing 4.10 < 53.36 < 106.68 < 126.39 MB; A(1k) = 0.033 × A(MAX) ≤ 0.10; A(29,999), A(30,000), A(100k) within 0.4 % of A(MAX); pk 1 max/min 1.014. Sub-prediction missed: A(10k)/A(1k) = 13.01 against 7–13.
   - **Cluster, R6's added B3g row** ("(a) and (b) of R4 hold, but (c) does not … Per-read cap confirmed, node-level peak not shown: Not confirmed (partial) for B1 item 2's second sentence; Effect 'caps' (per read)"):
     - (a) holds: 40/40 failures with "Scanned over T+1" at 1k / 20k / 100k; 40/40 successes with 0 rows at 300k / 1M.
     - (b) holds: maximum buffer 1.05 < 33.62 < 151.29 < 226.93 MB, 1M = 300k exactly, failing T at 1.04 / 1.66 / 1.50 × s(T+1) ≤ 2.2.
     - (c) fails: OU rise 0.25 < 4,009 < 6,050 but 300k = 6,015 < 6,050 (100k); 1M within 4 % of 300k.
     - (d) partly: buffer and rows identical in the control, OU 22 vs 0 MB fails the "both < 4 MiB" rule.
4. **Excluded rows.**
   - Unit: row 2 (**Refuted**, A(T) ≈ A(MAX)): A(1k) = 0.033 × A(MAX). Row 3 (mechanism differs): the count is T+1 exactly. Row 4 (`resp_bytes` ≪ N × 1 KB): 30.29 MB. Row 5 (pk 1 varies): 1.014. Row 6 (positive control does not move): A(MAX)/A(1k) = 30.7. R6 row (partial saving, order broken): neither.
   - Cluster: row 1 (Confirmed): needs (c), which failed. Row 2 (**Refuted**, "buffer sizes or peak heap equal those at T = 1M"): the buffers differ 216× between T = 1k and 1M; the OU peak at 100k equals 1M's within 4 %, but at 1k (0.25 MB) and 20k (4.0 GB) it does not, so the abort does prevent the allocation it bounds. Row 3 (reads succeed at T < N): none did. Row 4 (positive control flat): 408 humongous regions and +6.3 GB at 1M. Row 5 (peak rises by much more than C × 3 × content): it does at 20k–1M (reading 2a); it gives the direction, but its own statement "rises with T" does not hold beyond 100k. Row 6 (OOM only at T ≥ 300k): no OOM anywhere. R6 row 3 (buffers do not follow): they do.
5. **Observed vs. inferred.** The matched rows rest on observed readings only (outcomes, ERROR lines, JFR sizes, HeapPoll samples). Inferred: the explanation of the OU saturation (2a), the control's 22 MB (2c), and that the 216 MiB buffers of T ≥ 300k are what fills the heap at the same rate as the 144 MiB buffers of 100k.
6. **Deviations and gaps.**
   - E1 (clone), D1 (unit restart), D2 (OU instead of EU + OU for (c)/(d)), D3 (HeapPoll instead of `jstat`), H1 (harness). No reading was used to choose a fix.
   - **Missed sub-predictions:** every B3f peak-heap band (EU + OU: −0.40 / 6.31 / 5.71 / 5.37 / 5.78 GB against ≤ 0.1 / 0.16–0.5 / 0.8–2.4 / 1.6–4.9 / 1.6–4.9); JFR out-of-TLAB sum ratio 20k:1k = 174.6 (TLAB under-count) and the R5 node-allocation ratio 20k:1k = 12.9 (band 14–26); unit A(10k)/A(1k) = 13.01; B3e step 4's "0.2–0.3 GB" data (10.8 MB: the 1,000-character clusterings compress).
   - **Gap:** the heap held by the reads at any instant was not measured; the OU and EU + OU peaks include garbage (S3 of the audit). The node-level part of B1 item 2 is therefore not shown either way.
7. **Core question.** Per read, usage follows the constraint: one read's response buffer is 1.0 / 32 / 144 MiB when it stops at T = 1k / 20k / 100k and 216 MiB uncapped, i.e. it is bounded by about (T+1) tombstones, and its total allocation follows min(T+1, N) (unit A(T) linear to the abort, flat above N) [parts 3, 4]. The disallow branch fired exactly at T+1 every time [part 3]. The node-level heap peak did not follow T beyond 20k: 8 concurrent readers filled the old generation with humongous garbage up to the GC trigger at 100k, 300k and 1M alike [parts 2a, 3]. The check caps each read's response memory; it does not cap the node's heap use under concurrent reads.

**Conclusion (one line):** unit B2g row 1 — **Confirmed**; cluster R6's added B3g row — **Not confirmed (partial)**: per-read cap confirmed, node-level peak not shown.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

[`run1/selfcheck.py`](tombstone_failure_threshold-countTombstone-tombstones--autonomous/run1/selfcheck.py) is independent of the run scripts' outputs: it does not read `summary.txt`, `readings.csv`, `tft-unit.tsv` or the `jfr-*.tsv` files. It rebuilds the unit records from the test JVM's own log (`test.log`), each storm read's outcome from its `cqlsh` output file (`cluster-raw/client/`), the ERROR lines and the startup config dump from the `system-<T>.log` segments, the buffer sizes from the raw `.jfr` files through the JDK's `jfr print --json` (not `JfrBuf`), and the OU rise from the HeapPoll samples with its own code. Output [`run1/selfcheck.txt`](tombstone_failure_threshold-countTombstone-tombstones--autonomous/run1/selfcheck.txt): **41 ok, 2 FAIL**; the two FAILs are exactly R4's criterion (c) (OU order 6,050 > 6,015 MB) and the control's OU (22 vs 0 MB), the same two the analysis marked NO. Every figure agrees with the run script's (maximum buffers to the byte, OU rises to the MB).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | config dump `tombstone_failure_threshold=<T>` and the sjk read-back for all five lifetimes; trace "Read 0 live rows and 200000 tombstone cells"; no `java.lang.OutOfMemoryError` |
| 2. Readings | yes | humongous maxima 0 / 6 / 355 / 357 / 408 re-read from the gc logs; OU and EU + OU recomputed from HeapPoll |
| 3. Matched row | yes | unit criteria recomputed from `test.log` (7/7 ok); cluster (a) and (b) recomputed from client outputs, ERROR lines and `jfr print --json` (all ok); (c) fails as reported |
| 4. Excluded rows | yes | positive control: 1M buffer 216× the 1k buffer; no read succeeded below N; no OOM |
| 5. Observed vs. inferred | yes | the three inferences are not used by the matched rows |
| 6. Deviations and gaps | yes | E1, D1–D3, H1, the missed sub-predictions and the held-heap gap are recorded |
| 7. Core question | yes | follows B1: item 1 (abort exactly at T+1) observed; item 2's per-read part observed at both tiers; item 2's node part not shown |

### 5.2 Run 2?

**No** — decided 2026-10-21. The matched rows rest on observed readings and the independent re-parse agrees with them; the cluster verdict is already the conservative one. A run 2 would repeat the same instruments; what the node-level question needs is a different instrument (a held-heap reading), which is a design change for stage 3, not a repeat.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2); §7 left out.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its
date and reason.

**Stage-3 estimate:** positive (the file's Estimate line: the check aborts while the tombstones stream into the replica's on-heap response buffer, so one read's response heap is bounded by about (T+1) × one tombstone's size; per read command, not per node). An earlier stage-3 entry (`predicted-negative.md` §10, `ReadCommand.java:591`) had estimated negative ("counts tombstones scanned, not held").

**Claim tested:** B1 — "(1) for one data read of a partition holding N non-purgeable tombstones and no live rows, the replica stops after counting exactly min(N, T+1) tombstones and throws iff N > T; (2) the heap that read allocates and holds for its response grows in proportion to min(N, T+1), not N; under concurrent reads the node's peak heap grows by about C × that per-read amount; (3) refuted if lowering T below N leaves the response heap use unchanged." "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (throws exactly at T+1 for T < 30,000; allocation per read 4.10 · 53.36 · 106.68 · 126.39 MB at T = 1k · 10k · 20k · 29,999 vs 125.89 MB at T ≥ N; live control flat, 1.014). Sub-prediction missed: A(10k)/A(1k) = 13.01 (band 7–13) | caps (per read) | run 1 + self-check | 2026-10-21 |
| Cluster | **Not confirmed (partial)** — R6's added B3g row: (a) 40/40 aborts with "Scanned over T+1" at 1k · 20k · 100k, 40/40 successes at 300k · 1M; (b) maximum response buffer 1.0 · 32.1 · 144.3 · 216.4 · 216.4 MiB; (c) failed — old-generation peak 0.25 · 4,009 · 6,050 · 6,015 · 6,262 MB, saturated by humongous garbage. Peak-heap bands of B3f all missed | caps (per read); the node-level heap peak is not capped by it (undetermined as a held-heap reading) | run 1 + self-check | 2026-10-21 |

**Findings beyond the claim (no §9a row):**
1. As filed, the design could not reach the limit on a cluster: `INSERT … null` writes live rows, and `cqlsh` pages at 100 rows, so no command would ever scan more than 100 tombstones (audit R1). Tombstones written as `UPDATE … SET v = null` are the case the threshold guards.
2. The unit test yaml enables 8 MiB read-size and row-index thresholds that a default node does not (D1); a tombstone-heavy partition with large clusterings trips the row-index cap first there.
3. With the shipped G1 options (16 MiB regions), every response buffer from 8 MiB up is a humongous allocation; at T ≥ 20k eight concurrent readers filled 4–6 GB of old generation with humongous garbage before a GC, at 100k (the default) as much as uncapped. The default threshold therefore bounds one read's buffer (≈ 144 MiB at 1 KB tombstones) but not the heap churn of concurrent tombstone-heavy reads.
4. A read can run on a `Native-Transport-Requests`-named worker (SEP threads are renamed per task); the JFR stacks show the same `LocalDataResponse.build` path.

**Feedback filed:** the case file's section D updated 2026-10-21. Before that: the dated audit amendments R1–R6 and runbook fixes D1–D3 (only those blocks and section D changed; not committed). New sha256 of the whole case file after section D: `f617adea89cdfb317d1d94c410c689ba96cf27d5d5e9c24daf75d719e4f1e1f5` (not a new frozen version; for `_INDEX.md` §4).
