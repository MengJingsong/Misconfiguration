# max-region-size-region-allocate-capacity--autonomous — stage-4 results  <!-- file: results/max-region-size-region-allocate-capacity--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`max-region-size-region-allocate-capacity--autonomous`](../../stage3-ai-deep-read/cases/max-region-size-region-allocate-capacity--autonomous.md)
>
> **Status:** run 1 done, self-checked, verdict filed (2026-10-26); run 2 not done
>
> **Outcome class:** undetermined (estimate negative; unit tier: does not cap; cluster tier: Not confirmed, see §8). The evidence points to a true negative; the cluster row is withheld only because a frozen RSS relation failed (§4.2 part 3), and the reviewer may overrule to true negative.
>
> **Agent:** autonomous. For an autonomous
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
| **Case-file version** | The case file at repository HEAD `e776524` plus the uncommitted audit amendments of 2026-10-26 (the file is untracked; the orchestrator commits). sha256 of the whole file after the amendments (frozen before any reading): `9d344c9c77925c5af0e8ff65f170ef04094fb292aad909bf45a9d1a6881ea48c`. sha256 of the prediction and conclusions text (from `**B2f. Predictions` up to `**B2h.`, then from `**B3f. Predictions` up to `**B3h.`, the two pieces concatenated: B2f, B2g, B3f, B3g): `885629d6b2aed857310a5183418dda57c65b155cbfb80b65aa780798b792e2ed` (8035 characters). Section D takes the feedback afterwards, so the whole-file hash changes then and the table hash does not. |
| **Harness** | `harness/max-region-size-region-allocate-capacity--autonomous/` (`RegionCapProbe.java`, `unit-run.sh`, `instrument-check.sh`, `make-node-yaml.sh`, `client.py`, `Jmx.java`, `cluster-run.py`, `selfcheck.py`, `README.md`); written after this audit and before run 1; not committed by this agent (the orchestrator commits). Adapted from the `memtable-offheap-space-allocate-size--autonomous` harness (same node yaml, JMX reader, driver client). |
| **Tiers and values** | Unit (B2): cases A (s=100, N=2,000,000), B (s=100000), C (s=131072), D (s=131073), N=1000 each, on three builds (`MAX_REGION_SIZE` 256 KiB, 1 MiB stock, 4 MiB); an 8-thread stash run (stock); case E (L = 16 MiB, stock). Cluster (B3): `m256`, `m1024` (twice), `m4096` at `memtable_offheap_space` 64 MiB; positive control `o128`, `o256` (stock build); 20,000 rows x 100,000 B each. |
| **Audit bottom line** | **Ready after amendments** - 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: native (`Unsafe.allocateMemory` via `MemoryUtil.allocate`, `NativeAllocator.java:176,190`) bytes of memtable regions; the constant bounds one slab only. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b/B3b: `MAX_REGION_SIZE` is a compile-time constant, so three source-edited builds (256 KiB, 1 MiB default, 4 MiB) are the knob; the pool limit (`memtable_offheap_space` 64/128/256 MiB) is the positive-control sweep. The reason a build is needed is stated in A1. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d/B3d: `RssAnon` next to the charged gauge, gap named (untouched tail pages, glibc retention, NMT blind to `Unsafe` memory). Region capacity (the uncharged slack) is read by reflection in the unit tier only (B3d says so). |
| A. Core question | usage driven to the limit and past it | Partly, fixed by amendment | B3a left `memtable_cleanup_threshold` at 1/3, so the cleaner flushes at ~21 MiB of 64 MiB and the pool limit is never reached; amended to 0.99 (the maximum `DatabaseDescriptor.java:772-773` accepts) with one flush writer. Unit tier: case E fills to L and parks an extra writer (B2c as amended). |
| B. Logic | each step says what it establishes | Met | B2e and B3e number the steps and name the observable of each. |
| B. Logic | prediction stated in numbers or a clear relation | Partly, fixed by amendment | B2f case B gave slack 4.9 percent (true value 5.38 percent: the last region is half empty); the constant-variants clause said slack stays within 5 percent, but the stock rule gives 31.07 percent at 256 KiB with s = 100000 (two cells per 256 KiB region). B3f's 'few MiB' and B3g's 'under about 10 MiB' had no derivation. All replaced by exact replay values and quantified relations (replay run in Python, independent of any reading). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly, fixed by amendment | B2g/B3g cover confirm, refute, flat/proportional, limit-not-reached, overshoot. Missing: 'total' was undefined (charged bytes vs sum of capacities), and no row for a replay/instrument mismatch; added. B3g's confirming row lacked direct disallow evidence (below). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly, fixed by amendment | B3g row 1 had the ceiling relation only; amended to need `BlockedOnAllocation` growth and at least two MEMTABLE_LIMIT-style flush lines in each sweep arm. Unit: parked extra allocation (B2g). |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: fresh JVM per variant, fixed s and N, the L-binding run is the positive control, 8-thread run for the stash; direct memory capped at 256 MiB (B3a) so it cannot pass as memtable memory. |
| C. Specific | a human can follow it from the intro and §9a | Met | A1-A3 and B1 state the claim, and B2f/B2g/B3f/B3g are readable alone. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly, fixed by amendment | N for cases C and D, the shape of case E, the way variants are built, and the key layout of the cluster workload were missing; added (B2c, B3c). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly, fixed by amendment | Sampling set to 200 ms / 5 s, baseline definition, repeat count (15 lifetimes to six), compression, table creation and tmpfs directories added to B3a/B3c/B3e. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | pc12: JDK 11.0.32.1, Ant 1.10.12, `~/.m2` populated; trees by `copy-source.sh`; the sibling memtable-offheap harness supplies the yaml/JMX/client patterns; the harness is listed as step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met after amendment | 2 GB (20,000 x 100,000 B) is 31 x 64 MiB, 7.8 x 256 MiB; with threshold 0.99 the pool is reached. Data and commit log on tmpfs (126 GiB free); heap 1 GiB + 256 MiB direct limit + up to 256 MiB native regions fits. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `NativeAllocator.java` :46-48 (constants), :138-156 (allocate), :158-184 (trySwapRegion), :186-198 (oversize), :200-206 (setDiscarded), :209-227 (RaceAllocated), :244/:258-262 (capacity), :269-278 (line 273 check); `MemtableAllocator.java:169-196` (here `:172-196`); `NativePool.java:23` constructor; `AbstractAllocatorMemtable.java:106-108`; `DatabaseDescriptor.java:583-584, 761-775`; `Config.java:189-190`. All hold. A3 point 3's ':151' and ':154' match. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | B2f case B slack: 5,381,888 (5.38 percent), not 4.9 percent | Applied 2026-10-26 (B2f amendment) | Arithmetic; the last region holds 5 of 10 cells. |
| 2 | B2f constant variants: replace '<=5 percent' by exact replay values (31.07 percent slack at 256 KiB, s = 100000) | Applied 2026-10-26 | The old clause is false from the source alone, and a reading of 31 percent would otherwise be mis-filed as a refutation. |
| 3 | B2c N for C and D (1000) and case E shape; variants run A-D; skip-C/D advice dropped | Applied 2026-10-26 | Missing values; the skip advice was based on a wrong premise (128 KiB < 256 KiB). |
| 4 | B2g define 'total' (charged bytes; sum of capacities at s = 100); add two rows (variant geometry matches replay; replay mismatch) | Applied 2026-10-26 | Without a definition the 31 percent slack reads as 'total changes'. |
| 5 | B3a `memtable_cleanup_threshold: 0.99`, `memtable_flush_writers: 1`, `commitlog_total_space: 4096MiB`, tmpfs directories | Applied 2026-10-26 | Limit never reached at 1/3; commit log must not force the flushes. |
| 6 | B3f/B3g quantify 'flat' (charged within 0.05 L; RssAnon spread <= 0.25 L, ratio <= 1.3) and add blocked-counter/flush evidence to the confirming row | Applied 2026-10-26 | Untestable thresholds; direct disallow evidence required by the protocol. |
| 7 | B3e six lifetimes (m256, m1024 twice, m4096, o128, o256) instead of 15; no warm-up; 200 ms sampling | Applied 2026-10-26 | Session length; the relations are on direct counters; warm-up would break arm symmetry. A reading inside the m1024/m1024b noise band is not read as a difference. |
| 8 | Slack is not visible in `RssAnon` (untouched tail pages); the cluster tier cannot read it | Recorded in B3f amendment; left for stage 3 as a design note | The unit tier reads capacity directly. |
| 9 | Upstream doc candidate: the class javadoc (:34-43) does not say that region tails are uncharged | Left for stage 3 | Not needed for a valid run. |

**Bottom line: Ready after amendments** (2026-10-26). The amendments are in section D of the case file and marked in place.


### 1.2 Supplement declared after the first six cluster readings (2026-10-26, before its data exist)

Run 1's six lifetimes were read first (section 4). Their `RssAnon` knob-axis relation failed numerically while the charged-gauge relations held, and the
`m1024`/`m1024b` pair differs by 30 MiB, so the frozen single-run relation cannot tell a build effect from noise. Because B3e step 7 asks for three repeats per
build (cut to six lifetimes at the audit), five more lifetimes are run with the same harness and rules: `m256b`, `m256c`, `m1024c`, `m4096b`, `m4096c`
(arms added to `cluster-run.py` `ARMS`, nothing else changed). **Rules fixed here:** (1) the run 1 rows and the frozen relations are not re-evaluated; the
run 1 matched row stands as filed. (2) The supplement is reported as readings: per build, the three `rss_peak_delta` values, their mean and range. (3) The
between-build spread of the three means is called "within noise" if it is at most the largest within-build range, and "a build effect" otherwise; a build
effect is called "proportional to the constant" only if the means rise at least 4x for the 16x range of the constant, which B3g's refuting row names.
(4) The supplement cannot turn a Not confirmed into a Confirmed; it is recorded as the reason to ask for a run 2 (or not).

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (unit 08:28 MDT; cluster 08:35-09:02 MDT) | not done |
| Node (CloudLab name and type) | `pc12` (`node1.jason92-320876...`, 40 cores, 251 GiB); shared with other cases, port slot 4 (127.0.4.1, JMX 7140) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | openjdk 11.0.32.1 2026-08-18 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | three `copy-source.sh` copies at repository commit `e776524`, `git -C ... status --short cassandra/cassandra-5.0.9` empty (`~/s4-b7-mr-logs/src-status.txt`): `~/s4-b7-mr` stock (`ant build-test`, 1 min 19 s), `~/s4-b7-mr-m256` (`MAX_REGION_SIZE = 256 * 1024`) and `~/s4-b7-mr-m4096` (`4096 * 1024`), both `ant jar`. Constant checked in the class dir and the jar of each (`run1/instrument-checks.txt`) | |
| Case-file commit / harness commit | case file untracked at HEAD `e776524` (sha256 in §1); harness not committed by this agent (md5 below) | |
| Storage for node data | tmpfs `/dev/shm/s4-b7-mr` (wiped per lifetime); logs on `/` (`~/s4-b7-mr-logs/run1/`) | |
| Full logs (path, outside the repo) | `pc12:~/s4-b7-mr-logs/run1/` (unit `.out`, per-arm `jmx.csv`, `rss.csv`, `nmt.csv`, `system.log`, `session.log`) | |

Harness md5 at the end of run 1: `RegionCapProbe.java` 160891392ae8, `unit-run.sh` 17048d101374, `client.py` 6fe150b1acbd, `Jmx.java` a9ef136f33e7, `make-node-yaml.sh` d5acf7858d19, `cluster-run.py` d9e86b460b21 (five `ARMS` entries added after the first six readings, §1.2; before that only the node-class-path check, the `client.py` table-creation quoting and the `ARMS` list were edited during shakedown), `selfcheck.py` 43e5e7175937 (supplement block added after the readings), `cluster-chain.sh` c1eaccdad6ae, `instrument-check.sh` 1a9cba63d417.

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | shakedown (not a reading) | B3c client | `client.py schema` had a Python quoting error (single quotes inside a single-quoted string) | double-quoted string | harness fix, 2026-10-26 | none (harness only) |
| 2 | shakedown | B3e node check | the check that the node runs from the arm's tree looked at `/proc/<pid>/cmdline` and then `/proc/<pid>/maps`; the class path entry is `<tree>/bin/../build/apache-cassandra-5.0.9-SNAPSHOT.jar` | `jcmd VM.command_line` plus `os.path.normpath` | harness fix, 2026-10-26 | none |
| 3 | run 1 | B3f/B3g RSS relation | The frozen `RssAnon` bound (`<= 1.3 L`) and flatness relation (spread `<= 0.25 L`, ratio `<= 1.3`) did not hold in 10 of 11 arms and for the knob axis (§4.2). This is a prediction defect (the bound ignores a 56-84 MiB JVM-side growth that does not depend on L or the build, and ignores run-to-run noise of about 30 MiB), not a step that cannot be run. | not changed (predictions are not tuned to data); the case file's section D records it as feedback for the design | no restart | none |

## 4. Run 1

**Scope:** unit tier complete (A to D on three builds, `threads`, `limit`; 18 JVMs); cluster tier six lifetimes as declared at the audit (`m1024`, `m256`, `m4096`, `m1024b`, `o128`, `o256`) plus five supplementary repeats declared in §1.2 after reading the first six (`m256b`, `m4096b`, `m1024c`, `m256c`, `m4096c`). **Command log:** `max-region-size-region-allocate-capacity--autonomous/run1/` (`unit-excerpt.txt`, `cluster/<arm>/summary.txt`, `phases.json`, `big.out`, `analysis-six-arms.txt`, `analysis.txt`, `selfcheck.txt`, `chain.log`, `cluster-system-log-excerpt.txt`, `instrument-checks.txt`).

### 4.1 Readings

**Instrument checks (not readings):** `javap -constants` shows the constant 262144 / 1048576 / 4194304 in the class dir and jar of the three trees; the unit probe on 1024 x 1 KiB gave 2,088,960 in 8 regions, max 1,048,576, used 1,048,576, the hand-computed answer; the cluster shakedown (1000 rows, run name `shake`, not kept) showed the pipeline, the gauge, the blocked counter and the flush lines work.

**Unit tier** (`run1/unit-excerpt.txt`; 158 probe checks, 152 ok, 6 mismatches, all of one kind, below)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| A, stock (s=100, N=2,000,000): charged, sum of capacities, regions, max | owns = used = 200,000,000; capacity 200,269,824 in 197 regions; max 1,048,576 (B2f: >= 200 M, 190-200 regions, max 1 MiB) | `unit-excerpt.txt` `fill-stock-2000000-100` |
| B, stock (s=100000, N=1000) | owns = 100,000,000; capacity 105,381,888 in 101 regions; slack 5,381,888 = 5.38 percent (B2f as amended: 101, 105,381,888) | `fill-stock-1000-100000` |
| C, D, stock | C: 131,072,000 in 125 regions, slack 0; D: 131,073,000 in 1000 regions, max capacity 131073 | `fill-stock-1000-131072`, `-131073` |
| A-D, 256 KiB build | A: 200,269,824 in 768; B: 131,072,000 in 500 regions, slack 31.07 percent, max 262,144; C: 131,072,000 in 500; D as stock; owns identical to stock | `fill-m256-*` |
| A-D, 4 MiB build | A: 201,318,400 in 56; B: 104,333,312 in 27 (4.33 percent); C: 133,169,152 in 33 (1.60 percent); D as stock; owns identical to stock; max capacity 4,194,304 | `fill-m4096-*` |
| Replay of the :163-168 rule, and B2f literals | equal to the real region count, sum and max in all 12 fill runs (instrument and prediction both) | `check instrument-model-capacity`, `B2f-literal-capacity-and-regions` lines |
| Release | `setDiscarded` returns the charge to 0 in all 12 fill runs | `used_after_discard=0` |
| `threads` (8 threads, 400,000 x 100 B, stock) | owns = used = 40,000,000; capacity of the allocator's regions 40,886,272 in 45; the static stash holds 8192:7 16384:7 32768:5 65536:7 131072:7 262144:7 524288:7 1048576:3 regions = 10,362,880 B, never more than 7 per class (<= 8) and not charged | `threads-stock-400000-100.out` |
| `limit` (case E, L = 16 MiB, s = 100000, stock) | non-blocking fill stops at used = 16,700,000 <= L; a second non-blocking allocation is WAITING for 2 s with used unchanged (positive control); blocking group allocates 10 more without parking: used = 17,700,000 > L; the parked allocation completes after `setDiscarded` | `limit-stock-16-100000.out` |
| RssAnon cross-check (B2d "optional"; my own band [used - 1 MiB, capacity + 4 MiB], not in B2f) | 6 of 18 runs outside it: 5 above by 1.3 to 6.8 MiB (A on three builds, D on two) and one 0.09 MB below (C, stock); every run is 0.99 to 1.06 x charged | `unit-excerpt.txt`, `selfcheck.txt` info lines |

**Cluster tier** — per arm (L = `memtable_offheap_space`; `peak_off` = max of the JMX gauge `AllMemtablesOffHeapDataSize`; Blocked = growth of `MemtablePool BlockedOnAllocation` Count; Flushes = `Enqueuing flush of ks.t` lines, of them MEMTABLE_LIMIT; RSS = peak `RssAnon` above the baseline). Every arm: settings read-back equals the yaml, JVM flags as required, node runs from the arm's tree jar, 20,000 rows written, 0 client errors, tracked gauge back to 0 after the final flush, nothing left running (`cluster/<arm>/summary.txt`).

| Capacity value | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| L = 64, build 256 KiB | `m256`, `m256b`, `m256c` | peak_off / Blocked / Flushes / RSS | 61.9, 63.6, 63.6 MiB / +1839, +1864, +1820 / 38, 37, 38 (36-37 MEMTABLE_LIMIT) / 110.5, 121.0, 132.4 MiB | `cluster/m256*/summary.txt`, `analysis.txt` |
| L = 64, build 1 MiB (stock) | `m1024`, `m1024b`, `m1024c` | same | 63.1, 63.4, 63.2 MiB / +1937, +1681, +2133 / 40, 39, 42 (38-41 MEMTABLE_LIMIT) / 99.3, 129.7, 99.3 MiB | `cluster/m1024*` |
| L = 64, build 4 MiB | `m4096`, `m4096b`, `m4096c` | same | 61.6, 63.3, 60.4 MiB / +1927, +2298, +2059 / 39, 46, 41 (38-45 MEMTABLE_LIMIT) / 150.0, 121.5, 108.1 MiB | `cluster/m4096*` |
| L = 128, stock | `o128` | same | 119.0 MiB (0.929 L) / +869 / 19 (18) / 185.5 MiB | `cluster/o128` |
| L = 256, stock | `o256` | same | 251.0 MiB (0.980 L) / +281 / 10 (9) / 317.6 MiB | `cluster/o256` |
| derived | knob axis, run 1 (three builds, one lifetime each) | peaks within 0.05 L; RSS spread, ratio | peaks 61.92, 63.06, 61.63 MiB (spread 1.4 MiB <= 3.2: yes); RSS 110.5, 99.3, 150.0 MiB: spread 50.7 MiB (> 16), ratio 1.51 (> 1.3): **no** | `analysis-six-arms.txt` |
| derived | control sweep (m1024, o128, o256) | peaks ordered; RSS ratios | 63.1 < 119.0 < 251.0 MiB (yes); RSS ratios 128/64 = 1.87 (1.5-2.5), 256/64 = 3.20 (3.0-5.0): yes | `analysis-six-arms.txt` |
| derived | noise, run 1 | `m1024` vs `m1024b` | peak 63.06 / 63.44 MiB; RSS 99.3 / 129.7 MiB (30 MiB apart) | `analysis-six-arms.txt` |
| derived | supplement (§1.2 rules) | per-build RSS means and ranges | 256 KiB mean 121.3 (range 21.9); 1 MiB mean 109.4 (range 30.4); 4 MiB mean 126.5 (range 41.9); spread of means 17.1 MiB <= largest range 41.9: within noise; ratio of means 1.16 (< 4); nine tracked peaks within 3.2 MiB (3.2005 against 3.2 = 0.05 L: on the line) | `selfcheck.txt` |
| derived | JVM-side growth | NMT total committed, peak minus baseline | 56.0 to 84.5 MiB in every arm, no trend with L or build; `RssAnon` delta minus tracked peak is 36 to 88 MiB | `selfcheck.txt` info lines |

### 4.2 Conclusion and logic

1. **Validity** — [observed: `cluster/*/summary.txt`] every "hold fixed" setting was read back and equal to the yaml in all 11 lifetimes (`memtable_allocation_type=offheap_objects`, `memtable_offheap_space` per arm, heap space 256MiB, flush writers 1, cleanup threshold 0.99, commit log 4096MiB, caches 0), the JVM ran with `-Xmx1G`, `AlwaysPreTouch`, `MaxDirectMemorySize=256m`, from the arm's tree. [observed: `analysis.txt`] the limit was reached and passed in every arm (peak 0.93 to 0.99 L; `BlockedOnAllocation` grew by 281 to 2298; 10 to 46 flushes, MEMTABLE_LIMIT in every arm). [observed: `unit-excerpt.txt`] the unit pool filled exactly to its limit and parked the next writer. The run is valid.
2. **Readings** — [observed: `analysis.txt`] `RssAnon` rises 99 to 150 MiB at L = 64 against a charged peak of 62 to 64 MiB: 36 to 88 MiB above the charge. [observed: `selfcheck.txt`] the JVM's own native tracking (NMT total committed) grows 56 to 84 MiB in every arm, with no trend in L or build, and `m1024`/`m1024b` differ by 30 MiB with identical settings. [observed: `unit-excerpt.txt`] six unit `RssAnon` cross-checks fall outside my own band (by at most 6.8 MiB); the band is not a B2f prediction (part 6).
3. **Matched row** — **Unit.** B2g rows matched: (a) "Sum of capacities grows linearly with N, region count >> 1, max capacity == `MAX_REGION_SIZE`" [observed: A on stock, 200,269,824 in 197 regions, max 1,048,576; on 256 KiB 768 regions, max 262,144; on 4 MiB 56 regions, max 4,194,304]: Claim confirmed. (b) "Sum capacity > `owns()` in B (about 5 percent)" [observed: 5,381,888 = 5.38 percent, 100,000,000 charged]: uncharged slack exists. (c) the amended variant row "max capacity equals its constant, `owns` identical across variants, sum of capacities equals the B2f replay" [observed: all 12 fill runs equal both the replay and the B2f literals]. (d) "With a non-blocking group and L = 16 MiB, `owns` stops at <= L and the writer waits" [observed: used 16,700,000 <= 16,777,216; extra writer WAITING 2 s, used unchanged]: positive control. (e) "Blocking group exceeds L" [observed: 17,700,000 > L, writer not parked]: documented overshoot, not a refutation. Rows (a)-(e) hold together; the refuting rows do not (parts 4). **Cluster.** No B3g row matches as a whole. The charged half of row 1 (the amended text) holds: the pool limit sets the ceiling and the constant does not [observed: charged peaks 60.4 to 63.6 MiB over nine lifetimes at L = 64 for 256 KiB, 1 MiB and 4 MiB; 119.0 and 251.0 MiB at L = 128 and 256; blocked counters and MEMTABLE_LIMIT flushes in every arm]. The `RssAnon` half of that row (spread <= 0.25 L and max/min <= 1.3 across the three builds, and `RssAnon` <= 1.3 L) does not hold on run 1's single lifetimes [observed: spread 50.7 MiB, ratio 1.51; 10 of 11 arms above 1.3 L]. The closest row is "RSS-above-baseline exceeds charged peak by far more than slack plus 16 MiB stash": [observed] 36 to 88 MiB above the charge against about 20 MiB of slack plus stash allowed; its meaning is "report the gap, not the constant's effect". That row names a gap, not a verdict, so the tier is **Not confirmed (no matching row)**.
4. **Excluded rows** — Refuting B2g row "Sum of capacities never exceeds `MAX_REGION_SIZE`": [observed] sums are 100 to 200 MB with a 1 MiB constant. Refuting row "Total changes proportionally to the variants": [observed] `owns` identical across builds; at s = 100 the sum of capacities differs by at most 0.52 percent between builds (200,269,824; 200,269,824; 201,318,400). "Limit not reached" rows: [observed] reached in all arms. B3g "Peak RSS growth proportional to `MAX_REGION_SIZE`": [observed, `selfcheck.txt`] the three-repeat means are 121.3, 109.4 and 126.5 MiB for 256 KiB, 1 MiB and 4 MiB, ratio of means 1.16 for a 16x range of the constant, and within the largest within-build range of 41.9 MiB. "Charged peak flat across `memtable_offheap_space` values (control did not move)": [observed] 63.1, 119.0, 251.0 MiB. "Peak charged use never reaches the limit": [observed] 0.93 to 0.99 L. "Charged peak exceeds `memtable_offheap_space` by tens of MiB": [observed] never above 0.994 L.
5. **Observed vs. inferred** — [inferred: the charged gauge is the pool's own count, and the constant is not in the charge at `NativeAllocator.java:141`] the charged flatness across builds says what the pool accounts, not what the OS holds; the OS-level statement rests on `RssAnon`, whose knob-axis relation is within noise only by the supplement's rule (§1.2). [inferred: NMT total growth of 56 to 84 MiB, with no trend in L or build, is the JVM-side part of the `RssAnon` excess; NMT cannot see `Unsafe` memory, so the split of the 36 to 88 MiB between JVM-tracked growth and uncharged native regions is not measured.] [inferred: the slack (31 percent at 256 KiB) is mostly untouched tail pages and so largely absent from `RssAnon` (B3f amendment); the cluster tier cannot show it, the unit tier reads it directly (31.07 percent).]
6. **Deviations and gaps** — Six lifetimes planned at the audit, eleven run (the supplement of §1.2 was added after reading the first six, with rules fixed before its data). The unit `RssAnon` band (my choice) is exceeded in 6 of 18 runs by at most 6.8 MiB (m4096, case A; page rounding of 131,073-byte requests alone is about 4 MB over 1000 allocations, the A excesses are not explained here); not a prediction, not used in the row choice. The nine tracked peaks span 3.2005 MiB against the supplement's 3.2 MiB line (run 1's three peaks span 1.4 MiB, inside). Per-region slack and the `RACE_ALLOCATED` stash are invisible in a live node (case file B3d); only the unit tier measures them. The frozen RSS bound (1.3 L) and flatness thresholds were derived without a noise estimate (runbook defect 3).
7. **Core question** — Did usage follow the constraint? The usage that the constraint's mechanism charges did not: [observed: unit] the constant sets each slab's size (max capacity equals the constant on all three builds) and the uncharged slack (0.13 to 31 percent), while the charged bytes and, at s = 100, the total capacity are the same on all three builds; the sum of capacities grows linearly with N far past the constant. The pool limit is what binds: [observed: unit `limit`; cluster sweep] the writer parks at L, the charged peak is 0.93 to 0.99 L at 64, 128 and 256 MiB, and the real resource (RssAnon) rises with L in the predicted ratios (1.87 and 3.20). The constant does not cap the total: it is a per-slab size. What is not shown with the frozen rule is that the real-resource peak is flat across the constant on single lifetimes: the 50.7 MiB spread is comparable with run-to-run noise (30 MiB between two identical lifetimes), and the supplement's means are within noise, so the build effect, if any, is below what these runs can resolve.

**Conclusion (one line):** Unit: B2g rows "sum of capacities grows linearly ... max capacity == `MAX_REGION_SIZE`", "sum capacity > owns" and the positive control — **Confirmed**, does not cap. Cluster: **Not confirmed (no matching row)** — the charged ceiling follows `memtable_offheap_space` and not the constant, but the frozen real-resource flatness relation failed numerically (noise and an L-independent JVM-side growth).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-parsed from the raw files by `harness/.../selfcheck.py run1` (own re-implementation of the :163-168 region rule; does not read the probe's check lines or import the run scripts); output in `run1/selfcheck.txt` (111 `ok` lines, 12 `BAD`). The 12 `BAD` lines are exactly: the frozen `RssAnon <= 1.3 L` bound in 10 of 11 cluster arms, the frozen knob-axis RSS relation (spread 50.7 MiB, ratio 1.51), and the supplement's nine-peak span line (3.2005 against 3.2 MiB). No unit line is BAD.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.txt`: every arm's client wrote 20,000 rows with 0 errors, peak in [0.9 L, 1.05 L], blocked counter grew, MEMTABLE_LIMIT flushes; `summary.txt` lines "settings read-back ... yes", "node runs from this arm's tree jar ... yes". |
| 2. Readings | yes | `RssAnon` excess and its 30 MiB repeat noise re-derived from `rss.csv`/`phases.json`; NMT growth re-derived from `nmt.csv`; the unit RSS cross-check re-printed as info. |
| 3. Matched row | yes, with the stated limit | Unit rows (a)-(e) re-derived from the raw `.out` files: caps, regions, replay and literals agree in all 12 fill runs; limit run re-read. Cluster: no row matches as a whole; the filed verdict is Not confirmed (no matching row), which the re-parse supports (the two RSS lines are BAD). |
| 4. Excluded rows | yes | Refuting rows checked against the same files: owns identical across builds, s = 100 capacity within 0.52 percent, not proportional (ratio of means 1.16). |
| 5. Observed vs. inferred | yes | The inferred statements are listed in §4.2 part 5; the self-check does not turn them into observations (NMT split, slack invisibility). |
| 6. Deviations and gaps | yes | The supplement and its rules are timestamped in §1.2 before its data; the case file's section D carries the prediction defect. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | The audited chain (constant sets slab size and slack only; pool limit binds; real resource follows L) is supported at the unit tier and by the charged and L-sweep readings in the cluster tier; the one link not demonstrated by the frozen relation is the flatness of the real resource across the constant on single lifetimes. |

### 5.2 Run 2?

**No** (2026-10-26). The unit tier is exact (replay and literals agree to the byte on 12 runs) and needs no repeat. The cluster tier's open point is not a doubt about the claim but a defective RSS relation in the frozen prediction; a fresh run 2 under the same relation would fail the same way, and the declared supplement (three repeats per build) already shows the build spread is within noise. If the reviewer wants a Confirmed cluster row, the case needs a prediction amendment (charged gauge primary, `RssAnon` tolerance at least 40 MiB), and the cluster tier restarts, which the protocol allows only before reading; it is left to the reviewer.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** undetermined by the protocol's wording (unit: does not cap; cluster: Not confirmed). The reading of the data is that the effect is `does not cap`, i.e. a true negative; an overrule to **true negative** is the natural alternative.

**Claim tested:** (B1) Total native memory held by a `NativeAllocator` is not bounded by `MAX_REGION_SIZE`/`Region.capacity`: the number of regions and the sum of capacities grow linearly with the data written; the sum of capacities exceeds the bytes charged to the off-heap pool; on a real node peak off-heap use follows `memtable_offheap_space` and not `MAX_REGION_SIZE`. "Confirmed" below means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g "Sum of capacities grows linearly with N, region count >> 1, max capacity == `MAX_REGION_SIZE`"; also "sum capacity > owns", variant geometry row, positive control) | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | **Not confirmed (no matching row)** — charged peaks follow `memtable_offheap_space` (0.93 to 0.99 L) and are flat across the constant (spread 1.4 MiB at run 1, 3.2 MiB over nine lifetimes); the frozen `RssAnon` bound and flatness relation failed (noise and L-independent JVM-side growth) | does not cap (from the charged gauge and the unit tier; the real-resource relation is not demonstrated by the frozen rule) | run 1 + self-check + supplement | 2026-10-26 |

**Positive control** (a negative-estimate file only): [unit] the L = 16 MiB pool with a non-blocking group stops at 16,700,000 B and parks the next writer, with the same allocator and region code (`limit-stock-16-100000.out`); [cluster] the same workload and instruments, stock build, with `memtable_offheap_space` 64 -> 128 -> 256 MiB moved the charged peak 63.1 -> 119.0 -> 251.0 MiB and `RssAnon` 99.3 -> 185.5 -> 317.6 MiB (ratios 1.87 and 3.20), while the 16x range of the constant moved the charged peak by 1.4 MiB. The control moved, so "flat" is not "the workload could not have shown an effect".

**Feedback filed:** the case file's section D "Stage-4 feedback" (2026-10-26, this session; uncommitted, the orchestrator commits), including the prediction defect of the RSS relation and the unit-tier findings — no section of the case other than the audit amendments of 2026-10-26 was changed.

## Leftovers

On `pc12`: nothing running (`ps` for `s4-b7-mr` and `ss` for 127.0.4.* empty), tmpfs `/dev/shm/s4-b7-mr` removed. Kept on disk for the reviewer: `~/s4-b7-mr`, `~/s4-b7-mr-m256`, `~/s4-b7-mr-m4096` (471 MiB each, scratch builds; not the shared tree), `~/s4-b7-mr-logs/` (4.6 MiB). `/tmp/mr-build.sh` removed.
