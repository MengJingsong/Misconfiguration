# data-free-space-warn-threshold--autonomous — stage-4 results  <!-- file: results/data-free-space-warn-threshold--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`data-free-space-warn-threshold--autonomous`](../../stage3-ai-deep-read/cases/data-free-space-warn-threshold--autonomous.md)
>
> **Status:** verdict filed 2026-10-26 (run 1 + self-check; no run 2). Unit **Confirmed** — does not cap; cluster **Confirmed** — does not cap.
>
> **Outcome class:** true negative (estimate `negative`, effect `does not cap`; [definition](../README.md#outcome-class))
>
> **Agent:** guided / autonomous (the suffix of the case-file stem). For an autonomous
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
| **Case-file version** | Case file in repo HEAD `93d6365` plus the uncommitted audit amendments (section D, 2026-10-26); whole-file sha256 after amendments `db03eef4cc0ff36461f7a2fb53379802884bfd2dcebc3347534bc4281830777f`. Frozen prediction and conclusion tables (text from `**B2f. Predictions.**` up to `**B2h.`, and from `**B3f. Predictions.**` up to `**B3h.`): unit sha256 `92e2385b009a6e4944567919cdbed5e2bd8f8ccea9fb0bfc5ee86ec647b80ab7`, cluster sha256 `733631bfba3ade011cd05b982ae126388fa8a297e017e1c67073b75c83c53d2c`, recorded before any reading. (Template note, kept for reference: **Guided file:** the commit that holds the case file, and the hash of §9's text (`sed -n '/^## 9\. /,/^## 10\. /p' <case file> \| git hash-object --stdin`), recorded after the audit's amendments; §9a is frozen at this version. **Autonomous file:** the commit that holds the file, and the sha256 of the whole file (`sha256sum`) recorded after the audit's amendments; this hash goes in `_INDEX.md` (column sha256).) |
| **Harness** | `harness/data-free-space-warn-threshold--autonomous/` (not committed by this session; the orchestrator commits) |
| **Tiers and values** | Unit: volumes 1 GiB; 2x40 GiB; 1 GiB + 100 GiB; 63.9 GiB; 64.1 GiB; full volume; positive control `Directories.getWriteableLocation`. Cluster: 4 GiB tmpfs (S), 100 GiB tmpfs (L), 100 GiB tmpfs with `commitlog_total_space: 64MiB` (C). |
| **Audit bottom line** | Ready after amendments — 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1/A2: the operand is free disk bytes; the claim is that disk usage is not capped by it. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly | Knob is a literal (A1); design uses two arms differing in one condition (volume free space 1 GiB vs 63.9/64.1/100 GiB) instead of a knob sweep, and says why. No third knob value is possible. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B3d/B3b: `df`/`du` of the real volume and commit log; unit tier reads `getUnallocatedSpace` and the WARN text, with the gap (startup-only read) named in A3. |
| A. Core question | usage driven to the limit and past it | Partly | Unit: the volume is filled to 100% (B2e.4); cluster: 6 GB logical into 4 GiB (B3c) reaches and passes the volume limit, but the 64 GiB value itself is only 'crossed' on the free-space side (below at start, above on L). |
| B. Logic | each step says what it establishes | Met | B2b-B2e / B3b-B3e each state their step's purpose (arms, summing, boundary). |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f/B3f give numbers (1 GiB, 80 GiB sum, 63.9 vs 64.1 GiB, WARN counts). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g cover: advisory only, WARN count 0, startup throws, summing, control, limit not reached; unit lacks an explicit 'positive control did not move' row (covered by 'limit never reached / control'), no change needed. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly | The claim is negative: Confirmed needs WARN fired (direct) and usage unchanged by the 64 GiB side; B2g/B3g say so. Recorded as met for a negative file; disallow branch does not exist. |
| B. Logic | alternative explanations and their controls | Partly | B2h/B3h name controls; B2h's CommitLog control was too heavy for a bare DatabaseDescriptor JVM (amendment 2); B3h two-directory comparison moved to unit tier (amendment 5). |
| C. Specific | a human can follow it from the intro and §9a | Met | Intro, A and B1 are followable without the source. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | B2a said `ant testsome` per case (one JVM per class) and ext4 loop volumes; clarified by amendments 1, 3, 4. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Values and commands exact except the 63.9/64.1 GiB sizes and stop conditions (amendments 1, 4). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | JDK 11, Ant, build-test, sudo for tmpfs on pc07 (environment.md); harness is listed as step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Unit: needs <= 100 GiB tmpfs nominal, trivial. Cluster: 4 GiB tmpfs exceeded by ~6 GB logical (6e6 rows x 5 x 200 B), minutes on tmpfs; RAM 251 GiB. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `:726`, `:709-725`, `:1654-1664`, `:478`, `:455`, `:263`, `FileUtils:77`, `FBUtilities.prettyPrintMemory` checked against the pinned tree. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Run each unit case as its own JVM via JUnitCore; fixed tmpfs sizes for 63.9/64.1 GiB | applied, amendment 1, 2026-10-26 (uncommitted) | `ant testsome` forks one JVM per class |
| 2 | Unit positive control = `Directories.getWriteableLocation` on the same volume | applied, amendment 2 | CommitLog write is too heavy for the bare unit JVM |
| 3 | Cluster volumes are tmpfs of exact size | applied, amendment 3 | local lesson: spinning disk stalls; same ENOSPC |
| 4 | Stop conditions and sampling for stress | applied, amendment 4 | B3c gave a 20-40 min window only |
| 5 | Positive-control arm on the 100 GiB volume; summing comparison left to unit tier | applied, amendment 5 | isolate the cap |
| 6 | B3h cannot show a cap on usage of the data directory itself; the only disk cap shown is the commit log | left for stage 3 | note for the feedback field |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 |
| Node (CloudLab name and type) | pc07 (`node0.jason92-320876...`), 40 cores, 251 GiB, run locally; port slot 3 (127.0.3.1, JMX 7130) |
| OS and kernel (`uname -r`) | Ubuntu 22.04, 5.15.0-187-generic |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18) |
| Ant (`ant -version`) | Apache Ant 1.10.12 |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `copy-source.sh` to `~/s4-b8-fs-u` (`ant build-test`, unit) and `~/s4-b8-fs-n` (`ant jar`, node), from repository commit `93d6365` (source tree clean) |
| Case-file commit / harness commit | case file: `93d6365` plus the uncommitted 2026-10-26 amendments (sha256 in §1); harness: uncommitted at run time (orchestrator commits) |
| Storage for node data | unit: tmpfs mounts of exact size under `~/s4-b8-fs-mnt/`; cluster: one tmpfs (4 GiB or 100 GiB) holding data, commitlog, hints, saved_caches |
| Full logs (path, outside the repo) | `~/s4-b8-fs-logs/unit-run1/`, `~/s4-b8-fs-logs/cluster-run1/{S,L,C}/` on pc07 (S `stress.out` is 3.9 GB of error lines) |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B2a / B3a | `ant testsome` runs one JVM per class; loop ext4 volumes | JUnitCore per case; tmpfs volumes (section D amendments 1, 3) | applied 2026-10-26, prediction unchanged | uncommitted |
| 2 | shakedown | B3e | `bin/cassandra -f -p` writes no pid file; stress began before the native port accepted | script launches via `exec` and records `$$`; waits for `UN` + port | fixed in harness before run 1 | harness |
| 3 | run 1, S | B3d | `cluster-run.sh`'s summary step reads the whole `stress.out`; on S it is 3.9 GB (one error line per failed write), so the python summary hung and was killed; the `Results:` block was read from the file tail instead | none needed for the verdict; a later run should tail `stress.out` | noted | harness |
| 4 | run 1, S | B3a | On the full tmpfs the JVM died with SIGBUS (`node.out`, `jbyte_disjoint_arraycopy`) 30 s into the run, after `disk_failure_policy: stop` had stopped the transports; an ext4 volume would return ENOSPC instead. Not caused by the 64 GiB value | recorded as a deviation (tmpfs substitute) | noted | — |

## 4. Run 1

**Scope:** unit tier (7 cases + controls), cluster tier arms S, L, C. **Command log:** `results/data-free-space-warn-threshold--autonomous/run1/` (`unit/summary.txt`, `cluster/<arm>/summary.txt`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/<case>.stage4`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| 1 GiB volume (`one1g`): WARN count | 1; text `Only 1.000GiB free across all data volumes. Consider adding ...`; init returned | `unit/one1g.stage4` |
| 2 x 40 GiB (`two40`): sum 85,899,345,920 B | 0 WARN, init returned | `unit/two40.stage4` |
| 1 GiB + 100 GiB (`small_big`): sum 108,447,924,224 B | 0 WARN (small volume hidden), init returned | `unit/small_big.stage4` |
| 63.9 GiB (`b639`): unallocated 68,611,473,408 B | 1 WARN | `unit/b639.stage4` |
| 64.1 GiB (`b641`): unallocated 68,827,480,064 B (threshold 68,719,476,736) | 0 WARN | `unit/b641.stage4` |
| Full volume (`full`): 0 B free | 1 WARN, init returned, no throw | `unit/full.stage4` |
| Default directory (`nodirs`, yaml without `data_file_directories`; 36.5 GB free on local disk) | 1 WARN, init returned | `unit/nodirs.stage4` |
| Printed number vs `getUnallocatedSpace` | 4.000GiB-class text matches the independently read bytes (1.000GiB for 1,073,741,824) | `unit/one1g.stage4` |
| Config snapshot (408 public fields, `data_file_directories` excluded) | identical for one1g, b639, full (WARN) and b641 (no WARN); the two-directory cases differ in 2 fields (`memtable_flush_writers`, `memtable_cleanup_threshold`, derived from the directory count at `DatabaseDescriptor.java:753-755`, not from free space) | `unit/summary.txt` |
| Positive control `Directories.getWriteableLocation` on the 1 GiB volume (max dir available 1,021,313,024) | request 510,656,512 returns a directory; request 2,042,626,048 throws `FSDiskFullWriteError` | `unit/one1g.stage4` |
| Same control on the 100 GiB volume | request 53,660,876,800 returns a directory; 214,643,507,200 throws | `unit/big_only.stage4` |

**Cluster tier**

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| 4 GiB tmpfs | S | startup WARN | exactly one, `Only 4.000GiB free across all data volumes` | `cluster/S/system-log-excerpt.txt` |
| 4 GiB tmpfs | S | writes | accepted: stress `Total partitions 6,000,000`, `Total errors 2,957,006`, i.e. 3,042,994 writes succeeded before the volume filled | `cluster/S/stress-tail.txt` |
| 4 GiB tmpfs | S | volume / data / commitlog | used reached 4,294,967,296 (100%) at t=30 s, data 4,112,594,209 B, commitlog max 234,881,204 B; node dead (SIGBUS) from t=30 s | `cluster/S/samples.csv`, `node-out-sigbus.txt` |
| 4 GiB tmpfs | S | disk failure | 6 'No space left' lines, `Stopping transports as disk_failure_policy is stop`, 9 ERROR lines, first at 19:12:49 | `cluster/S/system-log-excerpt.txt` |
| 100 GiB tmpfs | L | startup WARN | none | `cluster/L/summary.txt` |
| 100 GiB tmpfs | L | writes / usage | all 6,000,000 accepted, 0 errors, 87,776 op/s; data max 9,018,249,070 B, commitlog max 234,881,204 B; 3.5 GiB of data reached at t=30.10 s (S: 30.08 s) | `cluster/L/summary.txt`, `selfcheck.txt` |
| 100 GiB tmpfs + `commitlog_total_space: 64MiB` | C | startup WARN | none | `cluster/C/summary.txt` |
| same | C | commitlog / data | commitlog max 100,663,396 B (96 MiB; cap 64 MiB plus one 32 MiB segment) against 234,881,204 B in L; data max 9,385,923,796 B (L: 9,018,249,070 B); 3.5 GiB reached at t=30.09 s; 0 errors | `cluster/C/summary.txt`, `selfcheck.txt` |

### 4.2 Conclusion and logic

1. **Validity** — the limit was reached: S filled its 4 GiB volume (used = 4,294,967,296, avail 0) [observed: `cluster/S/samples.csv`]; the WARN branch was reached in both tiers (WARN count 1 at 1 GiB, 63.9 GiB, 4 GiB, a full volume) [observed: `unit/*.stage4`, `cluster/S/system-log-excerpt.txt`]; held-fixed settings (`commitlog_total_space` 256 MiB, `disk_failure_policy: stop`, `auto_snapshot: false`, heap 1 GiB, single node) are in the yaml and logged config [observed: `cluster/S/yaml-effective.txt`, `selfcheck.txt`]. The positive control moved: commitlog max 96 MiB under the 64 MiB cap against 224 MiB under 256 MiB [observed: `cluster/C|L/summary.txt`]. Valid.
2. **Readings** — S's node died with SIGBUS on the full tmpfs and its stress output was 3.9 GB of errors; the volume and data readings up to t=30 s are unaffected [observed: `cluster/S/samples.csv`]. The unit `nodirs` case warns because the local disk has 36.5 GB free; it is a control for default-directory effects and shows the same WARN-only behaviour [observed: `unit/nodirs.stage4`].
3. **Matched row** — unit B2g row 1: "WARN only, startup completes, `Config` unchanged, below and above 64 GiB": WARN at 1 GiB, 63.9 GiB and 0 B, none at 64.1 GiB and 100 GiB, initialization returned in all, Config dump equal [observed: `unit/*.stage4`, `unit/summary.txt`]. Cluster B3g row 1: "WARN at start, writes accepted, disk grows to the volume limit": WARN at start, 3,042,994 writes accepted, data grew until the 4 GiB volume was full [observed: `cluster/S/*`]. The "positive control" and "growth identical on small and large volumes" rows also hold: growth to 3.5 GiB took 30.08 / 30.10 / 30.09 s on S / L / C [observed: `selfcheck.txt`]; the commit-log cap bound in C [observed].
4. **Excluded rows** — "WARN count 0 with 1 GiB free": WARN present. "Startup throws when free < 64 GiB": init returned in `one1g`, `b639`, `full`, `nodirs`; the node started on the 4 GiB volume. "Node refuses to start or reject writes because of the 64 GiB value" (Refuted row): the node started and accepted writes; the only write errors came after the volume was full with `No space left on device`. "No WARN on 4 GiB": WARN present. "Limit never reached" / "Volume never fills": S filled. "Reading is an exact sum ... hides one small volume": observed (`small_big`, 0 WARN with a 1 GiB volume), which supports A3 (a refinement, not a conflicting row).
5. **Observed vs. inferred** — Inferred: that the SIGBUS and the stopped transports in S came from the full volume and not from the WARN (inferred from the log order: first ENOSPC error at 19:12:49 and used = 100% at the same second, with the WARN logged 1m45s earlier and identical L/C runs reaching the same data sizes without the WARN); that a cap in A4 (not traced here) is what ends growth on a real node (here the volume size ended it).
6. **Deviations and gaps** — tmpfs instead of ext4 loop (SIGBUS at full, not ENOSPC); the 100 GiB volume is a nominal tmpfs size (only written data uses RAM); the two-directory comparison was done at the unit tier only; the S stress output was too large to parse whole; run 1 only.
7. **Core question** — Usage did not follow the 64 GiB value: the volume of 4 GiB (WARN) and the 100 GiB volume (no WARN) accepted the same writes at the same rate (3.5 GiB of data after 30.08 s and 30.10 s), the WARN fired once at startup and changed nothing else (Config dump identical), and the only thing that ended growth on S was the volume running out of space. The positive control showed that a binding cap (`commitlog_total_space`) does move the same instruments (commit log 96 MiB against 224 MiB). The constraint does not cap usage.

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 — confirmed (does not cap).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parsed the raw `*.out` (real logback `WARN ... DatabaseDescriptor.java:727` events, not the test's echo), `system.log`, `samples.csv` and the `stress.out` tail, output in `run1/selfcheck.txt`.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | WARN events per case match `sum < 64 GiB` for every case (the script flags a mismatch; none); S used = 4,294,967,296; control moved (`selfcheck.txt`) |
| 2. Readings | yes | S dead from t=30 s and the 3.9 GB stress output are real (`samples.csv` last column 0; SIGBUS excerpt); no reading contradicts another |
| 3. Matched row | yes | rows quoted in §4.2 part 3 verified against `unit/*.stage4` and `cluster/*/summary.txt` |
| 4. Excluded rows | yes | no throw in any unit case; the S errors are all ENOSPC after t=30 s (`system-log-excerpt.txt`) |
| 5. Observed vs. inferred | yes | the SIGBUS cause is inferred; L and C, with no WARN and no full volume, ran to completion, which supports it |
| 6. Deviations and gaps | yes | recorded in §3 |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | equal growth time (30.08/30.10/30.09 s) and unchanged Config say the WARN has no effect; the control shows the instruments can see a cap |

### 5.2 Run 2?

**No** (2026-10-26). The unit result is deterministic (exact bytes, pass/fail) and the cluster result is the same in three arms with a moving control; the one inferred statement (cause of the S crash) does not bear on the verdict.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** the 64 GiB threshold at `DatabaseDescriptor.java:726` does not cap disk (or memory) usage: it only emits a startup WARN, and a node with less than 64 GiB free still accepts writes and grows its data directory until the volume is full, while the same node with more than 64 GiB free is subject to exactly the same growth. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed: WARN only, startup completes, `Config` unchanged, below and above 64 GiB | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | Confirmed: WARN at start, writes accepted, disk grows to the volume limit (identical growth on 4 GiB and 100 GiB; control binds) | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control:** unit: `Directories.getWriteableLocation` refuses a request above the free space (2.04 GB on a 1.02 GB volume, 214.6 GB on 107.3 GB) and grants one below it, on the same volumes and JVM, so a guard that depends on the same free-space operand is visible to the instruments. Cluster: `commitlog_total_space: 64MiB` kept the commit log at 96 MiB maximum against 224 MiB under 256 MiB, with data growth unchanged.

**Feedback filed:** the case file's section D updated (see below); no section of the case amended beyond the audit amendments of 2026-10-26.

**Upstream / doc candidates:** the free-space check is advisory and read once; summing across volumes hides a nearly full volume (`small_big`: 1 GiB + 100 GiB gives no WARN). On a full tmpfs the JVM dies with SIGBUS (mmap) instead of invoking `disk_failure_policy`.

**Leftovers on the node:** none running; tmpfs mounts removed; work dirs `~/s4-b8-fs-u`, `~/s4-b8-fs-n`, `~/s4-b8-fs-unitwork`, `~/s4-b8-fs-nodework`, `~/s4-b8-fs-mnt` (empty), logs `~/s4-b8-fs-logs` (3.9 GB `cluster-run1/S/stress.out`).
