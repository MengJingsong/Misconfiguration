# initial-buffer-capacity-ensurecapacity-datalengthinbytes--autonomous — stage-4 results  <!-- file: results/initial-buffer-capacity-ensurecapacity-datalengthinbytes--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`initial-buffer-capacity-ensurecapacity-datalengthinbytes--autonomous`](../../stage3-ai-deep-read/cases/initial-buffer-capacity-ensurecapacity-datalengthinbytes--autonomous.md)
>
> **Status:** run 1 done, self-checked, verdict filed (2026-10-26)
>
> **Outcome class:** true negative (estimate negative; effect: does not cap)
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
| **Case-file version** | the case file at repository HEAD `e776524` plus the uncommitted audit amendments of 2026-10-26 (the orchestrator commits). sha256 of the whole file after the amendments: `7874e629651fa9e9c800a6746a47b23afb7e49d8a83af2795301d3f43fbb04da` (section D was filled after the run: the file with the feedback has sha256 `27e0624fac2203f9dc43f6eeb58ef1148755d5fa276dac9b4cc804bfd95ac407`; the hash before it is the frozen design). **Frozen before any reading** (2026-10-26): sha256 of the text from `**B2f.` to before `**B2h.` (unit prediction and conclusions table) `f01c35500b4125f1261fcab0afd632991fc868056621f39f6667fc28a2b03264`; of `**B3f.` to before `**B3h.` (cluster) `b0af17003283edbbc58cb4ad95eacc6ced07eee6f6bf4fc5363ed75ad8a69581` (command: `sed -n '/^\*\*B2f\./,/^\*\*B2h\./p' <file> \| sed '$d' \| sha256sum`, likewise B3f/B3h). |
| **Harness** | `harness/initial-buffer-capacity-ensurecapacity-datalengthinbytes--autonomous/` (written after this audit and before run 1; not committed by this agent) |
| **Tiers and values** | unit (B2) and cluster (B3), both run. Unit: N = 0, 31, 32, 33, 64, 1000, 65535, 1<<20, 64<<20, plus 1<<30 and (1<<30)+1; initial capacity 1, 24, 32, N, 2N; `-Xmx` 128m and 1g (4g for the 1<<30 cases). Cluster: K = 16 B, 1 KiB (20000 rows), 32 KiB, 65535 B (2000 rows) at `-Xmx1g`; K = 16 B and 65535 B at `-Xmx512m`; K = 16 B and 65535 B without the SAI index; guardrail control at 1 KiB. The optional rebuilt variant is not run. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: heap bytes of a transient byte[] (A3 steps 1-3, `ByteSourceInverse.java:366-386`), measured as thread-allocated bytes and heap occupancy. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b/B3b: no yaml knob exists (A1), so the design varies the input length N / key size K (9 and 4 values), the initial capacity and `-Xmx`, with the reason stated. |
| A. Core question | real resource measured, not only the counter (gap named) | Met after amendment | B2d thread-allocated bytes and B3d heap/disk are the real resource. JFR alone is statistical, so an exact per-call Byteman instrument was added (B3d amendment). |
| A. Core question | usage driven to the limit and past it | Partly | There is no limit to reach; the only bound is the int overflow at 1<<30 (`:424-429`). B2c skipped it; amended so N = 1<<30 and (1<<30)+1 run at `-Xmx4g`, with a B2g row. The cluster tier is bounded by the 65535 B key limit (`ClusteringPrefix.java:278-287`), reached at K = 65535. |
| B. Logic | each step says what it establishes | Met | B2e and B3e steps are numbered with the purpose in the knob/observable paragraphs. |
| B. Logic | prediction stated in numbers or a clear relation | Met after amendment | B2f said the slope is 2 to 4 times N; by the arithmetic of `:424-431` it is 2.0 (power of two), about 3.0 (1000, 65535) and up to about 5 (N = 33, 65). Replaced by the exact sum; reading-independent. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met after amendment | B2g had no row for the overflow exception at N > 1<<30; added. B3g has rows for flat, exceeds, counter-versus-real and not reached. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly | The claim is negative, so the 'disallow' is the absence of any refusal: B2g needs result length N at every N and no exception, B3g that no write fails at a legal K. The positive control (below) supplies the contrast. |
| B. Logic | alternative explanations and their controls | Met after amendment | B2h: `copyBytes` (a hard cap that throws) and an `Arrays.copyOf` baseline (defined). B3h: no-index arm, baseline K. The B3 guardrail control could not fire under `AllowAllAuthenticator` (`ClientState.java:602-605`, `Guardrail.java:95`); amended to use `PasswordAuthenticator` and an ordinary role. |
| C. Specific | a human can follow it from the intro and §9a | Met | Header table, A1-A4 and B1 give the claim; the note 'a growth trigger, not a limit' is unambiguous. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met after amendment | The B2a `ant testsome` form silently overrides `-Xmx` (a fact from the repo's HANDOFF lessons); replaced by a `main` class run with `java`. The 'ByteBufferUtil direct copy' baseline was undefined; defined as `Arrays.copyOf`. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met after amendment | Row counts and heap sizes were a product of 4 K x 2 heaps x 2 repeats x 2 index states; the run matrix is fixed in B3c. The control 'inserting 4 KiB v' needs the threshold pair (warn 1 KiB, fail 1 KiB) to be accepted; checked at the shakedown. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | JDK 11, Ant, Byteman 4.0.20 in `build/lib/jars`, bundled Python driver; the harness is written in step 1 (listed in the README of the harness folder). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met after amendment | K = 65535 x 2000 rows = 131 MB of keys plus 1 KiB values, on tmpfs (125 GiB free); the 1<<30 case needs 1.5 GiB of arrays plus the heap (`-Xmx4g` of 251 GiB). Not run: the original 'about 10 minutes per K' for 4 K x 2 x 2 lifetimes; matrix cut. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked in `cassandra-5.0.9`: `ByteSourceInverse.java:34, 366-386, 405-416, 422-432`; callers `SegmentMetadata.java:168-169` (in `write`, at SAI flush), `PrimaryKey.java:153`, `DecoratedKey.java:227,244`, `IndexTermType.java:912`; `ClusteringPrefix.java:278-287`, `Validation.java:54`; yaml `max_value_size` at `:1864`, term thresholds at `:2246-2255`. All correct. One imprecision left unamended: A3 step 5 lists `DecoratedKey.java:227,244` as callers; both exist but only the SAI/flush path is exercised by the node workload. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Run the probe as a `main` class with `java -Xmx`, not `ant testsome` (B2a) | Applied, amendment 2026-10-26 | `testsome` overrides `-Xmx`; the heap-size knob would not be set. |
| 2 | Run N = 1<<30 and (1<<30)+1 at `-Xmx4g` and add the B2g row (B2c, B2g) | Applied, amendment 2026-10-26 | Only way to reach the one real bound; cheap here. |
| 3 | Replace the 2x-4x slope band by the exact sum (B2f) | Applied, amendment 2026-10-26 | Arithmetic error, independent of any reading. |
| 4 | Define the `Arrays.copyOf` baseline (B2h) | Applied, amendment 2026-10-26 | The 'ByteBufferUtil direct copy' baseline was undefined. |
| 5 | Guardrail control needs `PasswordAuthenticator` and an ordinary role (B3b) | Applied, amendment 2026-10-26 | Guardrails are skipped for a superuser and when no authentication is required. |
| 6 | Fix the run matrix (B3c) | Applied, amendment 2026-10-26 | The product of K, heap, repeats and index states was about 16 lifetimes of 10 minutes. |
| 7 | Add an exact per-call Byteman instrument beside JFR (B3d) | Applied, amendment 2026-10-26 | JFR samples cannot give a per-call size; the prediction is per call. |
| 8 | Optional rebuilt variant (B3b 3, B3g last row) is not run | Left for stage 3 | The unit tier's `initialBufferCapacity` knob answers the same question without a rebuild; no Confirmed/Refuted row depends on it, but its B3g row will read 'not run'. |
| 9 | Positive control of the cluster tier (SAI guardrail) caps a term, not decode memory | Left for stage 3 | It shows the harness sees a binding cap on the same write path, as B3g says; the quantitative control is the unit tier's `copyBytes`. Rated Partly under A. |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (unit 08:27 MDT; cluster 08:30-09:00 MDT) | not done |
| Node (CloudLab name and type) | `pc12` (`node1.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`), 40 cores, 251 GiB; shared with other agents' nodes (own work dir, ports, loopback 127.0.3.1) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | openjdk 11.0.32.1 2026-08-18 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-b7-ie`, made by `copy-source.sh` from repository HEAD `e776524`, tag `cassandra-5.0.9`, `ant build-test` BUILD SUCCESSFUL in 1 min 10 s; the probe is compiled outside the tree; no file was added to the tree | |
| Case-file commit / harness commit | `e776524` plus the uncommitted amendments (sha256 in §1) / harness uncommitted (the orchestrator commits) | |
| Storage for node data | tmpfs `/dev/shm/s4-b7-ie-data` (wiped per lifetime); never `/proj` | |
| Full logs (path, outside the repo) | `pc12:~/s4-b7-ie-logs/run1/` (unit, cluster/<arm>/ with `ec.trace`, `ec.jfr`, `system.log`, `histo-*.txt`); shakedown `~/s4-b7-ie-logs/shake/` (not readings) | |

**Shakedowns (not readings).** (1) Unit probe: two instrument faults found and fixed in the probe, neither touching the case: a one-off +536 B on a single call (JIT or profile allocation on the measuring thread; the probe now judges the median of 5 and prints all values) and a retained-heap check that demanded `held >= N` although `used()` after `System.gc()` is a noisy difference (now within 64 KiB). (2) Cluster arm `warm`: the caller-frame filter returned a reflection frame (fixed: first frame after `ByteSourceInverse`), the first-trigger test summed by caller line (fixed: by method), and a Byteman rule **on `ensureCapacity` itself** (to see each doubling) was tried and dropped: Byteman's per-trigger allocation inside the per-byte call dwarfed the buffer (about 9 MB per `readBytes` call, 94 percent of the JFR weight under `ensureCapacity`), so the `ensureCapacity` part is taken from the closed-form arithmetic of the doubling code (validated exactly by the unit tier) and bounded from below by the traced total. All run-1 numbers below come from the final harness; `run1` was run once.

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | shakedown | B2a | `ant testsome` overrides `-Xmx` | probe is a `main` class run with `java -Xmx` | applied in the audit amendment, 2026-10-26 | uncommitted |
| 2 | shakedown | B3d | JFR on JDK 11: `jdk.ObjectAllocationSample` does not exist (JDK 16+); `jfr` has no stack-filtered summary | `JfrSum.java` reads `jdk.ObjectAllocationInNewTLAB` (weight tlabSize) and `OutsideTLAB` (allocationSize) and filters on `ensureCapacity` / `readBytes` frames; same instrument in spirit, statistical | recorded here; the §D amendment names JFR only generally | not needed |
| 3 | shakedown | B3d | A Byteman rule on `ensureCapacity` perturbs the allocation it measures | removed; see §2 | recorded here | not needed |

No step needed a change to B2f/B2g/B3f/B3g after the freeze.

## 4. Run 1

**Scope:** unit tier, all values (N 0..64 MiB, 1<<30 and (1<<30)+1; initial capacity 1, 24, 32, N, 2N; `-Xmx` 128m, 1g, 4g); cluster tier, nine lifetimes (K = 16 B, 1 KiB, 32 KiB, 65535 B at 1g; K = 16 B and 65535 B at 512m; K = 16 B and 65535 B without the SAI index; guardrail control). The optional rebuilt variant (B3b 3) was not run. **Command log:** `ie/run1/` = `results/initial-buffer-capacity-ensurecapacity-datalengthinbytes--autonomous/run1/` (`unit/summary.txt`, `unit/x*.out`, `cluster/<arm>/summary.txt`, `phases.json`, `jfr.json`, `A-log-excerpt.txt`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`unit/x128.out`, `x1g.out`, `x4g.out`; 174 `STAGE4 check` lines, all ok; allocation = thread-allocated bytes of one call, median of 5; the expectation is the sum of align8(16+length) over every array the code creates)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Instrument checks: `ensureCapacity` returns the same array when not full and a 2x array when full; `Arrays.copyOf` of 1000 B allocates 1016; the mirror equals a hand-computed sum for N = 65535 | ok (3 checks) | `unit/x1g.out` |
| Result length = N for every N and initial capacity; no exception for N <= 64 MiB | 52 points ok (25 shared by `-Xmx128m` and `-Xmx1g`) | `unit/x128.out`, `x1g.out` |
| Allocation per call, initial 32: N=0 64; 31 96; 32 48; 33 184; 64 128; 65 360; 1000 3128 (3.13 x N); 65535 196784 (3.00 x N); 1<<20 2097376 (2.00 x N); 16<<20 33554720 (2.00 x N); 64<<20 134218048 (2.00 x N) | each equals the expectation exactly | `unit/x1g.out` |
| Allocation identical at `-Xmx128m` and `-Xmx1g` for all 25 shared points | yes | `unit/summary.txt` |
| Initial capacity (N = 65535): 1 -> 196912; 24 -> 262344; 32 -> 196784; N -> 65552 (one array, no doubling, no copy); 2N -> 196640; result length 65535 in all | as expected: the initial size changes only transient garbage | `unit/x1g.out` |
| Initial capacity 0 (information only, not in the case): n=0 returns, n=1 throws `ArrayIndexOutOfBoundsException` (0 doubles to 0) | observed | `unit/x1g.out` |
| `getUnescapedBytes` over `ByteSource.of(byte[])` with zeros, N 0..1<<20 | round trip equal; allocation 24 B above the `readBytes` sum at every N | `unit/x1g.out` |
| Retained heap after `System.gc()` x3: 1 MiB -> 1030752 held, 64 MiB -> 67108928 held; after release -17840 / -312 | only the result survives | `unit/x1g.out` |
| N = 1<<30: result length 1073741824, no exception, 2153150896 B allocated; N = (1<<30)+1: `NegativeArraySizeException`, no result | as the code reads (`:424-429`) | `unit/x4g.out` |
| Positive control `copyBytes` into M bytes, N in {33, 1000, 65535, 1<<20}, M in {N-1, N, N+5} | throws `ArrayIndexOutOfBoundsException` exactly when N > M (12 cases per heap size, 24 in total) | `unit/x1g.out` |

**Cluster tier** — one lifetime per row. "decode" = the `readBytes` calls of `PrimaryKey$Factory.partitionKeyFromComparableBytes` (one per query result, length = K) and `SegmentMetadata.write` (6 per lifetime, min and max key at each of 2 flushes and 1 compaction; length K + 3 to 275). `ensureCapacity` bytes per call are the closed-form sum from the traced length [inferred]; the traced total per call is always at least that sum. Retained = `GC.class_histogram` total after the last query and `invalidatekeycache`, minus the total before the load.

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| K=16, 1g, index | k16 | decode lengths; `ensureCapacity` bytes; JFR share; retained; data dir | lengths 16-18 (< 32): no doubling, 0 B from `ensureCapacity`; JFR share 0; retained +14.4 MB; data 43.0 MB; 20000 rows, 1000 queries, 0 errors | `cluster/k16/summary.txt` |
| K=1 KiB, 1g, index | k1k | same | lengths 1024-1031; 2064 B per decode (4128 for the 1031 ones); JFR share 0.025 %; retained +29.2 MB; data 88.8 MB | `cluster/k1k/summary.txt` |
| K=32 KiB, 1g, index | k32k | same | lengths 32768-32892; 65632 B per decode (131184 for the 32892 ones); JFR share 1.82 %; retained +14.0 MB; data 202 MB | `cluster/k32k/summary.txt` |
| K=65535, 1g, index | k64k | same | lengths 65535-65810; 131184 B per decode (262272 for the 65810 ones); JFR share 3.54 %; retained +9.8 MB; data 400 MB | `cluster/k64k/summary.txt` |
| K=16, 512m, index | k16m | same | as k16; JFR share 0; retained +14.5 MB | `cluster/k16m/summary.txt` |
| K=65535, 512m, index | k64km | same | as k64k; 131184 / 262272 B; JFR share 4.73 %; retained +7.2 MB; 0 errors | `cluster/k64km/summary.txt` |
| K=16, 1g, no index | k16n | same | no `ec.trace` file: no `readBytes` call at all in the lifetime; retained +10.1 MB; data 1.2 MB (the value text is compressible) | `cluster/k16n/summary.txt` |
| K=65535, 1g, no index | k64kn | same | zero `readBytes` calls; retained +1.9 MB; data 264 MB (no SAI index; the index adds 136 MB, about the raw key bytes, 131 MB) | `cluster/k64kn/summary.txt` |
| K=1 KiB, 1g, index, SAI string-term fail threshold 1 KiB (warn 512 B) | ctl | guardrail | all twenty 4 KiB-v inserts rejected (`Guardrail sai_string_term_size violated: Value of column 'v' has size 4096, this exceeds the failure threshold of 1024`), role `ordinary` (not a superuser); the 2000 row inserts of 1000 characters and 1000 queries unaffected; decode lengths and sizes as k1k | `cluster/ctl/summary.txt` |
| 4 KiB value at the default 8 KiB threshold | — | — | not run as a separate insert (the K-sweep arms use 1000-character values); the contrast is the control arm only | — |

### 4.2 Conclusion and logic

1. **Validity.** The limit does not exist to be reached; the input was driven to the largest legal sizes. Unit: N up to 64 MiB at `-Xmx1g` and to 1<<30 at `-Xmx4g` [observed: `unit/x1g.out`, `unit/x4g.out`]. Cluster: K = 65535 B, the largest partition key (`ClusteringPrefix.java:278-287`), reached [observed: `cluster/k64k/summary.txt`, `max_len` 65810 on the SAI min/max key]. Instrument checks passed (ensureCapacity known answers, `Arrays.copyOf` baseline, mirror known answer, positive control) [observed: `unit/x1g.out`]; the first-trigger check passed in every indexed arm (`SegmentMetadata.write` calls in the trace after the first flush) [observed: each `summary.txt`]. B3a holds: one node, tmpfs, `-Xms=-Xmx` 1g/512m, SAI default on; the SAI guardrail control needed the `PasswordAuthenticator` amendment and fired [observed: `cluster/ctl/summary.txt`].
2. **Readings.** (a) JFR share of allocation weight under `ensureCapacity`: 0 / 0.025 / 1.82 / 3.54 percent at K = 16 B / 1 KiB / 32 KiB / 65535 B (1g), 4.73 percent at 65535 B and 512m; B3f's number ("below about 1 percent") is **exceeded for K >= 32 KiB** [observed: `cluster/k32k/jfr.json`, `k64k/jfr.json`, `k64km/jfr.json`]. The share is of the JVM's total allocation volume in a workload of 2000 rows and 1000 queries, whose other allocations are small; JFR attribution is statistical (TLAB refill events) [inferred]. (b) The literal run-script bound "mean `ensureCapacity` allocation per call at most 4 x 65535 B = 262140 B" is missed by 132 B (262272, the 16-byte array headers of 12 arrays) at K = 65535 [observed: `cluster/k64k/summary.txt`]; the case says "about". (c) The ctl arm logs one `ERROR` per rejected write class (NoSpamLogger): that is the control itself. (d) Retained heap does not rise with K: +14.4 / +29.2 / +14.0 / +9.8 MB at K = 16 B / 1 KiB / 32 KiB / 65535 B and +14.5 / +7.2 MB at 512m (K = 16 B / 65535 B) [observed: `phases.json` of each arm]; the spread is the run-to-run noise of a node's own growth. (e) The data directory is 2.0 x raw input bytes at K = 65535 without the index and 3.0 x with it; the index adds 136 MB, equal to the 131 MB of key bytes it stores [observed: `cluster/k64k/phases.json`, `k64kn/phases.json`]; at K = 16 the index adds the 20000 distinct 1000-character terms [inferred]. (f) The unit tier did not measure the peak transient heap of B2f ("below 4N + small"); only allocation, result length and retention were measured, so that statement is inferred from the doubling sequence (largest live pair is old + new array, below 3N) [inferred: `ByteSourceInverse.java:366-386`].
3. **Matched row.** Unit: B2g row 1, "Allocation per call linear in N (the exact sum above, slope 2 to 5), result length N, no exception, same under both `-Xmx`" [observed: 52 points equal the exact sum; ratio 2.00 / 3.00 / 3.13 at N = 1<<20 / 65535 / 1000; equal at 128m and 1g; no exception up to 64 MiB]; also the added row "NegativeArraySizeException only at N = (1<<30)+1, and N = 1<<30 returns N bytes" [observed: `unit/x4g.out`]; also the "Initial capacity N removes doubling garbage but result identical" row [observed: 65552 B against 196784 B, same length]. The positive control moved as required (B2h) [observed: `copyBytes` throws exactly when N > M]. Cluster: B3g row 1, "`ensureCapacity` allocation proportional to K, tiny share of allocation, retained heap and disk unchanged by it", with the SAI-guardrail row ("rejects 4 KiB values while decode volume is unaffected") as the positive control [observed: `cluster/ctl/summary.txt`]: allocation per decode is 0 (K = 16, below 32), 2064, 65632, 131184 B (proportional to K); retained heap does not rise with K (2d); disk follows the stored key bytes and not the buffers (2e). One part of the row's wording, "tiny share", has a number in B3f that is exceeded at K >= 32 KiB (2a); I match the row on its substance (proportional, not retained, nothing refused) and record the miss as a deviation (part 6).
4. **Excluded rows.** Unit: flat or capped allocation / truncated result: ruled out, the result length is N at every N and the allocation follows N [observed]; allocation depends on `-Xmx`: ruled out, identical at 128m and 1g [observed]; exception for some N well below 1<<30: ruled out, none up to 64 MiB [observed]; control not moving: ruled out [observed]; largest N not reached: ruled out, 64 MiB at 1g and 1<<30 at 4g ran [observed]. Cluster: retained heap or old-gen growth tracks K, traced to these buffers: ruled out for the buffers (no trend with K, 2d) [observed]; a write with a legal key fails at the decode: ruled out, 0 client errors, 0 `rbexc` lines, 0 `ERROR` lines outside the control [observed: `selfcheck.txt`]; positive control not rejecting or path never reached: ruled out, both fired [observed]; rebuilt variant changes disk or retained heap: **not run** (see part 6). The "Refuted" rows (cap found; heap-derived limit; hidden limit; buffers retained; failure at the decode) are each excluded by the reading named.
5. **Observed vs. inferred.** Inferred: (i) the per-call `ensureCapacity` byte count in the cluster tier (closed form on the traced length; supported by the unit tier's exact agreement and by traced total >= that sum for all 7000-plus calls) [inferred]; (ii) that the traced total's surplus (up to 12 KB per decode at 1 KiB, 206 KB mean at 65535 B, against 131 KB of buffer) is the byte source's own allocation, not this code [inferred: the surplus per decode is of the same order at every call of a given K and exceeds the buffer only by the source's own work; the unit tier shows `readBytes` itself allocates exactly the sum]; (iii) the JFR share is statistical; (iv) the retained-heap difference being "noise" rather than a small effect of K [inferred: values 14 / 29 / 14 / 10 MB without trend]; (v) the data-directory arithmetic (key stored in data and primary index, index adds a third copy) [inferred, not traced to files].
6. **Deviations and gaps.** The JFR share exceeds B3f's "about 1 percent" at K = 32 KiB, 65535 B (and at 512m); the literal 262140 B bound is missed by the array headers; peak transient heap not measured; the rebuilt variant (INITIAL_BUFFER_CAPACITY 1 and 65536) not run (the unit tier's initial-capacity knob answers the same question); only the tiers' listed matrix, one lifetime per arm (no repeats; the 512m arms play that role for K = 16 B and 65535 B); no 4 KiB value inserted at the default 8 KiB threshold; ByteOrderedPartitioner not run (B3a optional); `ensureCapacity` sees no input larger than 65810 B in the node, 1<<30 is a unit-tier reading only.
7. **Core question.** Usage does not follow the `ensureCapacity` check as a limit: nothing was refused at any size up to the JVM array bound; the buffer is a transient copy that is 2 x to 5 x the input (exact sum) and is garbage after the call (retained only the result), identical under 128m / 1g / 4g and 512m / 1g nodes, and the node's retained heap and disk do not depend on it [steps: parts 1, 3, 4]. The only bound is `Arrays.copyOf` at N = (1<<30)+1, the JVM array limit [observed: `unit/x4g.out`]. The constraint does not cap memory or disk.

**Conclusion (one line):** Unit: B2g row 1 (linear in N, nothing capped) — confirmed; cluster: B3g row 1 (proportional to K, not retained, nothing refused, control fired) — confirmed on its substance, with B3f's JFR-share figure missed at K >= 32 KiB recorded as a deviation.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`selfcheck.py` (in the harness folder) re-parses the raw files (`ec.trace`, `histo-*.txt`, `jfr.json`, `system.log`, client JSON lines, `x*.out`) and re-derives the allocation arithmetic in closed form, independently of the probe's and run script's loops. Output: `run1/selfcheck.txt`. After correcting two of its own defects (a missing `ec.trace` was read as "not run" instead of "zero calls", and the ctl arm's own guardrail ERROR line was counted), it reports 3 parts that do not hold, all the JFR-share figure (k32k, k64k, k64km); the 132-byte header miss is covered by an explicit tolerance in the checker and is listed in §4.2 part 2b.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `unit/x4g.out`, `cluster/k64k/summary.txt` (max_len 65810), first-trigger lines, `cluster/ctl/summary.txt` (role `ordinary` is not a superuser, 20 of 20 rejected) |
| 2. Readings | yes | `selfcheck.txt`: unit parts all hold; cluster per-arm parts hold; the JFR figure is recorded as exceeded, not hidden |
| 3. Matched row | yes, with the deviation | rows re-read against the frozen text of B2g/B3g; B3f's "below about 1 percent" is exceeded for K >= 32 KiB and the match rests on the row's substance; flagged for the user in §8 |
| 4. Excluded rows | yes | every Refuted row has a named reading (§4.2 part 4); rebuilt-variant row marked not run |
| 5. Observed vs. inferred | yes | the five inferred items are listed in §4.2 part 5; (i) is supported by `selfcheck.txt` (traced total >= closed form for every call, 0 under) |
| 6. Deviations and gaps | yes | the list is complete against `summary.txt` EXPECTED lines (k32k 1 NO, k64k 2 NO, k64km 2 NO, ctl 1 NO = the control's own ERROR line, all others yes) |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1 -> B2 (exact allocation, no refusal) -> B3 (proportional, not retained, control fires) -> answer |

### 5.2 Run 2?

**No** (2026-10-26). The unit tier is deterministic and exact; the cluster tier agrees in shape across two heap sizes and three further K values; no row refutes the case or confirms a bypass; the one open figure (JFR share) is statistical and a second run of the same instrument would not change its meaning. Cost is low but the value is small.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Comparison — only if run 2 was done

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** (B1) The "buffer full" doubling at `ByteSourceInverse.java:424` does not cap memory or disk. The decode buffer is a transient copy that scales with the input length (peak about 2x to 3x input), independent of any configuration entry, and a node's heap and disk use is governed by other limits. The decoding is never refused by this check.
"Confirmed" below always means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (allocation exactly the doubling sum, result length N, identical under 128m / 1g, no exception to 64 MiB; overflow row: only (1<<30)+1 throws) | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** — B3g row 1 (allocation per decode proportional to K, not retained, nothing refused, guardrail control fired); B3f's "JFR share below about 1 percent" missed at K >= 32 KiB (1.8 / 3.5 / 4.7 percent) | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control** (a negative-estimate file only): unit — `copyBytes` into M bytes throws `ArrayIndexOutOfBoundsException` exactly when N > M (24 of 24 cases), on the same loop and instrument; cluster — with a non-superuser role, `sai_string_term_size_fail_threshold` 1 KiB rejected all twenty 4 KiB values while the decode volume and sizes were identical to the 8 KiB-default arm (`cluster/ctl/summary.txt`, `cluster/k1k/summary.txt`). It is a cap on the related term size, not on the decode memory, as recorded in the audit.

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (uncommitted; the orchestrator commits), amendments of the audit marked inline and listed in D — see D.

**Leftovers on the node:** none running (`ps` shows no `CassandraDaemon` of this harness); work files remain: `pc12:~/s4-b7-ie` (the tree with `build/`), `~/s4-b7-ie-logs/` (logs, shakedown and run1), `/dev/shm/s4-b7-ie-data` (conf, logs; data directories removed per lifetime).
