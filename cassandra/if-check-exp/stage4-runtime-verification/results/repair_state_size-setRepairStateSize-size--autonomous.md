# repair_state_size-setRepairStateSize-size--autonomous — stage-4 results  <!-- file: results/repair_state_size-setRepairStateSize-size--autonomous.md -->

> **Case:** [`repair_state_size-setRepairStateSize-size--autonomous`](../../stage3-ai-deep-read/cases/repair_state_size-setRepairStateSize-size--autonomous.md)
>
> **Status:** verdict filed, 2026-10-28. **Unit: Confirmed — caps** (run 1; closed, not re-run). **Cluster: Confirmed — caps**
> (cluster re-run "run 1b" of 2026-10-28 at the re-frozen version `92f32f87…ef3b`, after the user-authorised amendment of B3d, B3e,
> B3f (iv), B3g, B3h and B4; §7, §8). The run-1 cluster verdict below (Not confirmed) stays on record as filed.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/repair_state_size-setRepairStateSize-size--autonomous/`](../harness/repair_state_size-setRepairStateSize-size--autonomous/).
>
> **Run-1 status (as filed 2026-10-26):** verdict filed, 2026-10-26. **Unit: Confirmed — caps. Cluster: Not confirmed — caps (entry count).**
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-26, on the advisor's machine (`environment-advisor.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed as sha256 `46c6d010…5414` (DD batch 4). Frozen after the step-0 audit's thirteen amendments (2026-10-26): sha256 **`020f07adb6e461e31a3f91ab057455d567f40f2bd032c718ad34ea162273bb88`**, at which the unit tier's run 1 ran. After the cluster harness shakedown and before cluster run 1, one more dated amendment to B3e only (a 180 s settle before the baselines; no prediction, band or row changed) gave **`348f780b12eafec6f8a12e781d109ad005dcc0962019f56b6e44d2899d2c09d2`**, at which the cluster tier's run 1 ran. All three are rows in `_INDEX.md` §4. Nothing is committed (no commit was asked for). |
| **Harness** | [`../harness/repair_state_size-setRepairStateSize-size--autonomous/`](../harness/repair_state_size-setRepairStateSize-size--autonomous/): `RepairStateSizeTest.java` (B2e's skeleton with the B2e amendment's changes), `unit-run.sh`; `Rep.java` (B3c verbatim), `make-node-conf.sh`, `cluster-run.sh`. Not committed. Instrument checks: (i) the test class compiled in the run clone at the audit (`ant build-test`, `BUILD SUCCESSFUL`, `$W/logs/…/audit-compile.log`); (ii) the Guava layout probe [`audit/GuavaLayout.java`](repair_state_size-setRepairStateSize-size--autonomous/audit/GuavaLayout.java) read Guava's own segment fields ([`audit/guava-layout.txt`](repair_state_size-setRepairStateSize-size--autonomous/audit/guava-layout.txt)); (iii) a cluster shakedown (`cluster-run.sh shake 200 50`) ran every step ([`shakedown/summary.txt`](repair_state_size-setRepairStateSize-size--autonomous/shakedown/summary.txt)); it showed a 0.9 MB live-heap drift in the baseline window that started right after start-up, which led to the B3e settle amendment, and that the Guava entry class is `$StrongAccessWriteEntry`. Its readings are not used. |
| **Tiers and values** | Unit (B2): S = 10, 100, 1000, 100000 set through `setRepairStateSize` before a new `ActiveRepairService`, 5,000 bare `CoordinatorState`s each; post-construction control (built at 100, set to 100000); a repeated same-value set; three runs. Cluster (B3): one node, yaml `repair_state_size` 50, 500, 100000 (restart per value), 2,000 `repairAsync` commands on keyspace `rs` (RF 2) per value. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26. |

### 1.1 Design audit

Citations re-read in `~/cassandra-src` at `cassandra-5.0.9` (`b5f2a54210`), the commit of the run clone. The Guava arithmetic was read
from the pinned jar (`guava-32.0.1-jre`, `.build/parent-pom-template.xml:307-309`) by the layout probe, before any reading.

**Derived from the source (A3 amendment).** Both caches are Guava `Cache`s with `expireAfterWrite(3d)` and `maximumSize(S)`
(`ActiveRepairService.java:37-38`, `:250-260`): the bound is an entry count, enforced per segment, and the segment caps sum to S
exactly (S = 10 → 1 × 10; 50 → 13 + 13 + 12 + 12; 100 → 4 × 25; 500 → 4 × 125; 1000 → 4 × 250; 100000 → 4 × 25000), so a full cache holds
exactly S. Expiry cannot act within the test. Eviction is silent; its evidence is registered − retained. A bare entry (B2c) is ≈ 0.6 KB;
a failed single-node repair's entry (B3) ≈ 1.5 KB; a real repair's entry grows with sessions and jobs, and no knob bounds one entry's
bytes, so bytes are capped only as S × (that workload's entry size). The setter has no caller, MBean, nodetool command or writable
settings row; the yaml value is written into `Config` directly; so on a node line 5070 never runs and B3 tests startup only.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2/B1: an entry count with a per-entry byte size; the byte size per entry is not bounded (A3 amendment). |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b: 10, 100, 1000, 100000; B3b: 50, 500, 100000 (default 100000). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | Unit `measureDeep` of the retained states; cluster: B3d's jmap/heap_info replaced by the class histogram (per-class rows and live Total), with a drift control. |
| A. Core question | usage driven to the limit and past it | Met | N = 5000 > S ≤ 1000 (unit); N = 2000 > S ≤ 500 (cluster). |
| B. Logic | each step says what it establishes | Partly | Implied by B2g/B3g; left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | The filed "≥ 0.75 × S" is looser than the Guava arithmetic; bytes had no band on the cluster. Exact counts, log-line counts and bytes bands added (B2f, B3f). |
| B. Logic | every plausible outcome has a conclusions row | Not met → Met after amendment | Missing: bytes not following the count, exact-S wrong, startup value wrong, setter-line count, workload not reaching the coordinator, queued commands, runs disagree, second count. Added (B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after amendment | Eviction is silent; registered (unit) and issued/`Starting` lines (cluster) now observed, so evicted = N − retained is read. |
| B. Logic | alternative explanations and their controls | Met | S = 100000 not-binding arm; post-construction control; instance counts and `RepairCoordinator` for the queue bypass; drift control for bytes. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3, B1, tables. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Output location wrong (B2e); order of reads and baselines open (B3e). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | B3d named `GC.heap_info`, which counts young regions on this JDK. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Mapped to this host (B2a, B3a): one clone, one node, JMX 7199. |
| D. Runnable | workload arithmetic reaches the limit | Met | 5,000 bare states ≈ 3 MB in a 1 GiB test JVM; 2,000 commands at 50/s ≈ 40 s per value. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `DatabaseDescriptor.java:5063-5075`; `Config.java:957-958`; `ActiveRepairService.java:37-38`, `:191-193`, `:235-260`, `:684`, `:1192-1217`; `RepairCoordinator.java:128-132`, `:373-396`; `StorageService.java:4797-4802`, `:4862`; `CoordinatorState.java:47-65`; `RepairOption.java:278-295`; `LocalRepairTables.java:119`, `:295`; `MBeanWrapper.java:61-66`; `build.xml:94`, `:1192`, `:1382-1392`. All match. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | A3: cache type, Guava segment arithmetic, entry contents and heap, setter reachability, derived | Amendment 2026-10-26 (uncommitted) | Asked by the audit; the filed text estimated "≥ 0.75 × S". |
| 2 | B2a: this host's clone and runner | Amendment 2026-10-26 | CloudLab path. |
| 3 | B2d: readings from the test log; `registered` observable | Amendment 2026-10-26 | Output location; silent eviction. |
| 4 | B2e: `println` with prefix, same-value set, getters | Amendment 2026-10-26 | Output; both branches of line 5070. |
| 5 | B2f: exact counts, control 100, log-line values, bytes bands | Amendment 2026-10-26 | Group B. |
| 6 | B2g: row 1's requirements, split count / bytes; eight rows added | Amendment 2026-10-26 | Group B. |
| 7 | B3a: one node on this host | Amendment 2026-10-26 | CloudLab paths. |
| 8 | B3b: no runtime path; B3 tests startup only | Amendment 2026-10-26 | Reachability. |
| 9 | B3d: class histogram instead of jmap/heap_info; participant count; log-segment and `issued` counts | Amendment 2026-10-26 | Live heap; workload evidence. |
| 10 | B3e: order of reads, two baselines (drift₀), second after-reading (drift₁), shakedown | Amendment 2026-10-26 | Open. |
| 11 | B3f: exact counts 50 / 500 / 2000, instance counts, e in [0.5, 5] KB, resolvability rule | Amendment 2026-10-26 | Group B. |
| 12 | B3g: row 1's requirements, split count / bytes; eight rows added | Amendment 2026-10-26 | Group B. |
| 13 | B4: this host's cleanup | Amendment 2026-10-26 | CloudLab paths. |
| 14 | B3e: 180 s settle before the baselines (shakedown drift) | Amendment 2026-10-26, after the shakedown and before cluster run 1 | Instrument check; no prediction changed. |
| 15 | Exercise the participant cache (a two-node ring, so every repair prepares and registers `ParticipateState`s on both nodes) and real entries (sessions, jobs) | Left for stage 3 | B1 claims the coordinator cache only; one node never prepares. |
| 16 | Expose or remove the dead setter (no caller; a runtime change would only log) | Left for stage 3 (section D) | Not a stage-4 question. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 (audit 01:12–01:19; unit run 1 01:20–01:21; shakedown 01:22–01:26; cluster attempt 0 01:27 (aborted at the pre-check, see §3); cluster run 1 01:27–01:47 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64; 10 cores, 32 GiB RAM; internal SSD (APFS), 136 GiB free at start (135 GiB at cluster run 1); loopback 127.0.0.1, .2, .3 on `lo0` (only .1 used); ports 7000, 7199, 7299, 7399, 9042, 9091 free; no `CassandraDaemon` before |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit JVM: junit fork (1 GiB), `-Dorg.apache.cassandra.disable_mbean_registration=true`. Node: `MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M` (`-Xms1G -Xmx1G` in `JVM Arguments`), shipped `jvm-server.options` |
| Ant | 1.10.18 |
| Local `cassandra-src` clone commit | `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`): `$W/cassandra-run27` (`ant -Dlocal.repository=$W/m2 build-test`, `BUILD SUCCESSFUL`); `W=~/Library/Caches/stage4` |
| Case-file commit / harness commit | uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-rss/n1` (kept across the three values, wiped before and after); JMX 7199 |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/repair_state_size-setRepairStateSize/` — `clone.log`, `build-test-run27.log`, `audit-compile.log`, `unit-r{1,2,3}/` (ant log, JUnit XML, test log, `stdout.txt`, `storing.txt`, `setting.txt`), `cluster-shake/`, `cluster-run1-attempt0/`, `cluster-run1/` (`commands.log`, `summary.txt`, per value `S<v>/`: `n1/` node logs, `hist-base-{a,b}.txt`, `hist-after-{a,b}.txt`, `cql-*.txt`, `rep.log`, `system-segment.log`, `schema.txt`) |

## 3. Runbook defects

None. Cluster attempt 0 (01:27) stopped at the harness's own pre-check ("a CassandraDaemon is running") because the operator's wrapper
command line contained the daemon class name, which the check's `ps | grep` matched; no node was started and nothing was read
([`run1/cluster/attempt0-summary.txt`](repair_state_size-setRepairStateSize-size--autonomous/run1/cluster/attempt0-summary.txt)). The same
script was re-run unchanged from a command line without that name. This is an operator slip, not a step of the case file.

Re-freeze after run 1 (R1, a case-file amendment authorised by the user) and harness changes for the cluster re-run (added 2026-10-28 by the cluster re-run session):

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| R1 | cluster run 1 (reading, not a runbook defect) | B3d, B3e, B3f (iv), B3g, B3h, B4 | The bytes half of B3g row 1 rested on "Δ difference = Δcount × e", which needs the common part of the live-heap total to cancel between node starts; the self-check (§5, part 7) found it differing by ≥ 1.2 MB between starts (Δ(500) − Δ(50) = −1,199,568 B), invisible to the frozen drift control; the tier was Not confirmed — caps (entry count). | **Re-freeze, authorised by the user (Yang, the advisor) on 2026-10-28:** six dated amendments `Amendment 2026-10-28 (after run 1, authorised by the user)` — B3d (instrument (6): the retained heap of the `repairs` cache read from one heap dump per reading, `HprofRetained.java`, cut at `ActiveRepairService.repairs`), B3e (fresh clone `$W/cassandra-run71`, base and after dumps in each node start), B3f (iv′) (the Δ relations become records; conditions (iv′-1)–(iv′-4); derived expectations E_src = 1,680 B and 112 B + T of structure), B3g (row 1's bytes half read with (iv′); four rows added; the Δ rows superseded), B3h (base dump as null control), B4 (paths). New sha256 `92f32f87…ef3b` as a new row in `_INDEX.md` §4. The whole cluster tier re-run from its beginning in a fresh clone (§7). B1, B3f (i)–(iii), (v), the count half of row 1 and the unit tier unchanged. | user, 2026-10-28 | sha256 `92f32f87…ef3b` (uncommitted; no commit asked for) |
| H1 | cluster re-run | B3a/B3e paths | `cluster-run.sh` and `make-node-conf.sh` were fixed to run 1's clone (`cassandra-run27`) and node (`$W/node-rss`). | Both read `RSS_C` and `RSS_NODE`; the defaults reproduce run 1. | AI, 2026-10-28 | n/a (harness) |
| H2 | cluster re-run | B3d (6), B3e (amended) | Run 1's harness took no heap dump. | With `RSS_DUMP=1`, `cluster-run.sh` takes `jcmd GC.heap_dump` after histogram base-b and after the second count, and after the node stops runs the new `HprofRetained.java` on each dump (`ret-base.txt`, `ret-after.txt`, `RET` summary lines); a settings line records the clone, node, and the sha256 of `HprofRetained.java` and of the script. New `KnownAnswer.java` (the analyser's known answer outside Cassandra), `EntryLayoutProbe.java` (the JVM's shallow sizes for the derivation) and `excerpt.sh` (copies excerpts; reads only). Without the variables the script behaves as in run 1. sha256 prefixes: `cluster-run.sh` `35dbf4ee` (run 1) → `bf567357`; `make-node-conf.sh` `e734eea0` → `84c2ec65`; `Rep.java` `cc0857f3` unchanged; new `HprofRetained.java` `6abd3aaa`, `KnownAnswer.java` `1182b2fd`, `EntryLayoutProbe.java` `75c76961` ([`run1b-cluster/harness-sha-run2.txt`](repair_state_size-setRepairStateSize-size--autonomous/run1b-cluster/harness-sha-run2.txt)). | AI, 2026-10-28 | n/a (harness) |
| H3 | cluster re-run | self-check | `run1/selfcheck.py` checks run 1's relations (and the closed unit tier). | `run1b-cluster/selfcheck.py` copies the cluster part of `run1/selfcheck.py` (only the directory, N and the S values are parameters); under `--relations run1` its output on run 1's raw files is identical to the 53 cluster lines of `run1/selfcheck.out`; under `--relations amended` the Δ relations become uncounted INFO lines, and B3f (iv′) is checked on the raw dumps with its own HPROF reader (it does not run `HprofRetained.java`; it compares its numbers with the harness's afterwards), plus the amended B3g row; `--ka` checks the reader on the known-answer dump. Exit status non-zero on any failed counted check. `run1/selfcheck.py` is unchanged. | AI, 2026-10-28 | n/a (harness) |

## 4. Run 1

**Scope:** both tiers, all values in §1. **Command logs:** [`run1/unit/`](repair_state_size-setRepairStateSize-size--autonomous/run1/unit/) (`r1`–`r3`: `commands.log`, `summary.txt`, `stdout.txt`, `storing.txt`, `setting.txt`, `junit-testsuite.txt`); [`run1/cluster/`](repair_state_size-setRepairStateSize-size--autonomous/run1/cluster/) (`commands.log`, `summary.txt`, `attempt0-summary.txt`; per value `S<v>/`: `startline.txt`, `rep.log`, `cql-*.txt`, `hist-{base,after}-{a,b}-excerpt.txt`, `system-segment-first3.txt`).

### 4.1 Readings

**Unit tier** (JUnit 1 test, 0 failures, 0 errors in each run; the three runs printed identical lines)

| Test or assertion | r1 = r2 = r3 | Predicted (B2f as amended) | Evidence |
|---|---|---|---|
| `start getter` | 100000 | 100000 | `run1/unit/r*/stdout.txt` |
| S = 10: registered / retained / bytes | 5000 / **10** / 6,144 | 5000 / 10 / recorded | `stdout.txt` |
| S = 100 | 5000 / **100** / 60,504 | 5000 / 100 | `stdout.txt` |
| S = 1000 | 5000 / **1000** / 604,104 | 5000 / 1000 | `stdout.txt` |
| S = 100000 (not binding) | 5000 / **5000** / 3,020,104 | 5000 / 5000 | `stdout.txt` |
| bytes(1000)/bytes(100) · bytes(5000)/bytes(1000) | 9.985 · 4.999 | [8, 12] · [4, 6] | computed |
| bytes/retained at S = 100 · 1000 · 100000 | 605.0 · 604.1 · 604.0 B | [300, 1500] B | computed |
| post-construction control (built at 100, then set 100000) | retained **100**, getter 100000 | 100, 100000 | `stdout.txt` |
| `Storing repair state … or for <S> elements` | 10, 100, 1000, 100000, 100 | same, in order | `storing.txt` |
| `Setting repair_state_size to <S>` | 10, 100, 1000, 100000, 100, 100000 (6) | same, none for the same-value call | `setting.txt` |
| same-value set | getter 100000, no line | no line | `stdout.txt`, `setting.txt` |

**Cluster tier** (one node, RF 2 keyspace `rs`, 1 GiB heap; each value a fresh start; `issued 2000`, Rep exit 0, 42–43 s; log segment per value: 2,000 `Starting repair command #`, 2,000 `Nothing to repair for`, 2,000 `WARN … Repair … aborted`, 0 `ERROR`)

| S (yaml) | Startup line | count₀ · count₁ · 30 s later | participates₀ · ₁ | `CoordinatorState` inst / bytes | `$Phase` · `RepairOption` inst | `RepairCoordinator` · `ParticipateState` | used₀ (B) · drift₀ | used₁ · drift₁ | Δ = used₁ − used₀ | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| 50 | `… or for 50 elements` | 0 · **50** · 50 | 0 · 0 | 50 / 4,400 | 50 · 50 | 0 · 0 | 50,586,376 · −124,736 | 58,945,648 · −1,880 | 8,359,272 | `S50/` |
| 500 | `… or for 500 elements` | 0 · **500** · 500 | 0 · 0 | 500 / 44,000 | 500 · 500 | 0 · 0 | 62,500,136 · −114,640 | 69,659,840 · −3,024 | 7,159,704 | `S500/` |
| 100000 (default) | `… or for 100000 elements` | 0 · **2000** · 2000 | 0 · 0 | 2000 / 176,000 | 2000 · 2000 | 0 · 0 | 62,618,368 · −114,624 | 72,517,560 · 0 | 9,899,192 | `S100000/` |

Derived: `CoordinatorState` 88 B, `$Phase` 24 B, `RepairOption` 56 B per instance at every S. Δ(100000) − Δ(500) = **2,739,488 B** over
1,500 entries (e = 1,826 B); Δ(100000) − Δ(50) = **1,539,920 B** over 1,950 entries (e = 790 B); the resolvability thresholds (3 × the
largest drift of the pair) are 343,920 and 374,208 B. Not a frozen comparison, but from the same readings: Δ(500) − Δ(50) =
**−1,199,568 B**, where the model predicts +450 × e. `LocalCache$StrongAccessWriteEntry` 2,050 / 2,500 / 4,000 = count₁ + 2,000 (the
`repairStatusByCmd` cache holds one entry per command), 64 B each; `$StrongWriteEntry` 0 (recorded only).

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — three runs, each 1 test, 0 failures [observed: `run1/unit/r*/junit-testsuite.txt`]; registered = 5000 in every arm, so N > S for S ≤ 1000 [observed: `stdout.txt`]; the constructor read the value set before it [observed: `storing.txt`]. Valid.
2. **Readings** — nothing unusual; the three runs are identical [observed].
3. **Matched row** — B2g row 1, "retained ≤ S for all S < N, = N otherwise, bytes ∝ retained — Claim confirmed", with the amendment's requirements: retained 10 · 100 · 1000 and 5000; registered 5000; post-construction 100 with getter 100000; bytes ratio 9.985 in [8, 12]; `Storing` values 10, 100, 1000, 100000, 100; in all three runs [observed: `stdout.txt`, `storing.txt`]. Count and bytes reported apart: **entry count capped** (exactly S, 5000 − S evicted silently); **bytes of the retained entries follow the count** (604–605 B per bare entry, ratios 9.985 and 4.999) [observed].
4. **Excluded rows** — "retained = 5000 for S = 10": 10 [observed]. "postConstructionSet retained > 100": 100 [observed]. "retained ≪ 0.75 × S": exactly S [observed]. Added rows: retained < S — no; bytes ratios out of band — no; bytes/retained out of band — no; `Storing` ≠ S — no; `Setting` lines ≠ the 6 values or a line for the same value — no; registered ≠ 5000 — no; runs disagree — no; compile/run failure — none [observed].
5. **Observed vs. inferred** — the match needs no inferred statement. That Guava's layout makes the count exactly S is the audit's derivation, borne out by the readings.
6. **Deviations and gaps** — the states are bare (B2c), so 604 B is a lower bound for a real entry; `measureDeep` counts shared objects once (the S = 10 arm, 614 B per entry, includes them).
7. **Core question** — set before construction, `repair_state_size` fixes the coordinator cache's capacity: 5,000 registrations leave exactly S entries, and their deep bytes follow (≈ 604 B × S for bare states). Set after construction (line 5070 runs, the field changes) it has no effect on the live cache: 100 stays 100.

**Conclusion (unit tier):** B2g row 1 — **confirmed**.

**Cluster tier**

1. **Validity** — each start logged the yaml's S [observed: `S*/startline.txt`]; 2,000 commands issued and 2,000 reached the coordinator at every S [observed: `S*/rep.log`, `summary.txt` `LOG`]; count₀ = 0 [observed: `cql-repairs-0.txt`]; the limit was passed at S = 50 and 500 (2,000 > S) [observed]. Valid.
2. **Readings** — Δ(500) is 1.2 MB smaller than Δ(50) [observed: `summary.txt` `USED`], although S = 500 retains 450 more entries; the live-heap Total therefore varies from one start to the next by more than the drift control sees (drifts ≤ 125 KB). A plausible cause is that memtables on this yaml (`memtable_allocation_type: heap_buffers`, `conf/cassandra.yaml:825`) take heap in 1 MiB slab regions (`SlabAllocator.java:51`), so the 2,000 `parent_repair_history` updates per value move the Total in 1 MiB steps [inferred: source, not measured].
3. **Matched row (by the frozen numbers)** — B3g row 1, "count₁ tracks min(S, N) and instance counts agree — claim confirmed on a node": count₁ 50 · 500 · 2000 exactly (and 30 s later); `CoordinatorState` and `$Phase` instances = count₁; `RepairCoordinator` 0; startup lines = S; issued and `Starting` 2,000 [observed]. Its bytes half: the `CoordinatorState` row's bytes = 88 B × count₁ at every S [observed: `hist-after-a-excerpt.txt`]; Δ(100000) − Δ(500) = 2,739,488 and Δ(100000) − Δ(50) = 1,539,920, both positive, above 3 × drift and with e = 1,826 and 790 B inside [512, 5120] B [observed: `summary.txt`].
4. **Excluded rows** — "count₁ = 2000 for S = 50": 50 [observed]. "count₁ ≤ S but instances ≫ S": instances = count₁ [observed]. "count₁ = 0 for all S": 50, 500, 2000 [observed]. Added rows: count₁ < S — no; `RepairCoordinator` > 0 — 0; startup line ≠ S — no; issued or `Starting` ≠ 2000 — no; participates > 0 — 0; second count ≠ count₁ — no; Δ difference unresolved — not by the frozen rule (but see 7) [observed].
5. **Observed vs. inferred** — the bytes half rests on the inference that the other consumers in Δ are the same at every S and cancel in a difference. The readings contradict it: Δ(500) − Δ(50) is −1.2 MB, against a prediction of about +0.4 to +0.8 MB, and the two e values that pass the band differ by a factor of 2.3. The slab-region cause is inferred.
6. **Deviations and gaps** — one node, so every entry is a failed-early state (≈ 1.5 KB by the audit's layout estimate) and the participant cache is never used (participates 0, `ParticipateState` 0); B3 tests startup, not the setter (no runtime path); the 180 s settle was added after the shakedown (§1). Per-class histogram bytes are shallow.
7. **Core question** — with `repair_state_size: S` in the yaml, the node keeps exactly min(S, N) coordinator states and no more state objects on the heap (instances = count₁, nothing queued): **the entry count is capped and follows S**. The heap held by those entries follows the count in the per-class rows (88 + 24 + 56 B per entry for the three state classes), but the live-heap total cannot resolve the difference between values: the start-to-start variation (≥ 1.2 MB) is as large as the differences that passed the frozen rule. So the bytes half of B1 is not shown on the node.

**Conclusion (cluster tier):** by the frozen numbers B3g row 1; after the self-check (§5, part 7), **the added row "count part holds, but a Δ difference is not resolved — entry count capped; heap bytes not shown to follow it — Not confirmed for bytes"**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

[`run1/selfcheck.py`](repair_state_size-setRepairStateSize-size--autonomous/run1/selfcheck.py), written before any reading and not changed
since, independent of the harness (it re-reads the raw JUnit XML and raw test logs; per value the node's whole raw `system.log`,
`rep.log`, the raw cqlsh outputs and the raw `jcmd` histograms; it does not read `summary.txt`): **125 checks, 0 failed**
([`run1/selfcheck.out`](repair_state_size-setRepairStateSize-size--autonomous/run1/selfcheck.out)).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | JUnit counts; startup lines, `Starting`/`Nothing`/`aborted` counts from the whole raw `system.log` of each start; `issued 2000`. |
| 2. Readings | yes | Counts from the raw cqlsh files; Totals and class rows from the raw histograms; Δ and drifts recomputed. |
| 3. Matched row | yes (unit) / **no for the bytes half (cluster)** | Unit: every row-1 check passes in r1–r3. Cluster: the count half passes exactly; the bytes half passes the frozen numbers, but see part 7. |
| 4. Excluded rows | yes | Every other row's condition is absent in the raw files. |
| 5. Observed vs. inferred | yes | The cancelling of other consumers is the one inference; it is named and is contradicted by Δ(500) < Δ(50). |
| 6. Deviations and gaps | yes | Stated. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes (unit) / **does not hold for cluster bytes** | The logic "Δ difference = Δcount × e" needs the common part to cancel; re-reading `S50/hist-after-a` and `S500/hist-after-a` with their baselines shows the common part differing by ≥ 1.2 MB between starts, which the drift control (≤ 125 KB) cannot see. The cluster bytes finding is downgraded to Not confirmed; the count finding stands. |

### 5.2 Run 2?

**No** — decided 2026-10-26. The unit tier and the cluster count readings are exact and agree with the self-check. The cluster bytes
half failed because of the instrument (live-heap total against slab-quantised memtables), not the run; a second run of the same frozen
runbook uses the same instrument and cannot settle it. A design that measures the retained heap of the cache itself (for example a heap
dump's retained size of the `repairs` map, or more entries per value so that S × e is several MB) would need a re-frozen B3d/B3f.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 7. Cluster re-run ("run 1b") after the B3d, B3e, B3f (iv), B3g, B3h, B4 amendment — 2026-10-28

Session: Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-28, on the advisor's machine. Run 1's sections above are kept as filed; the
unit tier (Confirmed) was not re-run.

### 7.1 Frozen version and harness

| Field | Content |
|---|---|
| **Why** | Run 1's cluster tier was Not confirmed only through its bytes half: the count half of B3g row 1 held exactly (50 · 500 · 2000 states, live instances = count, nothing queued, startup line = S), but "Δ difference = Δcount × e" needs the common part of the live-heap total to cancel between node starts, and re-reading `S50/hist-after-a` and `S500/hist-after-a` with their baselines showed it differing by ≥ 1.2 MB, which the drift control (≤ 125 KB) could not see (§4.2, §5). The README says a wrong §9a "is a dated amendment to the case file and the affected tier starts again". The user authorised an amendment and a re-run of the whole cluster tier on 2026-10-28. |
| **Choice of instrument, and why** | The retained heap of the cache itself, read from one heap dump per reading: `jcmd <pid> GC.heap_dump` (live objects after a full GC) and `HprofRetained.java`, which computes the bytes reachable from the GC roots with and without the one reference `ActiveRepairService.repairs` (`ActiveRepairService.java:191`) — R_cache — and with and without entering any `CoordinatorState` — R_values. B1's bytes half is about the states' *retained* heap, which R_values is by definition, and both are absolute readings inside one node start, so nothing has to cancel between starts. The two routes named in the brief were checked against the source first: **S cannot be varied in one JVM** — `maximumSize` is fixed when `ActiveRepairService` is built (`:250-256`) and the setter has no caller, MBean, nodetool command or writable settings row (A3 amendment (iii)); and there is **no weigher** for an observe-only probe to read — Guava counts entries (A3 amendment (i)). Instance counts × size from the class histogram cannot attribute an entry either: of the 14 kinds of objects one entry retains, only `CoordinatorState`, `$Phase`, `RepairOption` and `Completable$Result` are exclusive to repair state; `HashMap$Node`, `HashMap`, `HashSet`, `String`, `byte[]`, `long[]`, `Range`, `ConcurrentHashMap` and `AtomicReference` are shared with every other consumer. A dump attributes every object; the analysis is observe-only (no agent in the node). |
| **Amendment** | Six dated amendments `Amendment 2026-10-28 (after run 1, authorised by the user) — B3d / B3e / B3f (iv′) / B3g / B3h / B4`, each next to the text it changes; each says plainly that it follows run 1's readings.<br>**B3d (6)**: the instrument above; known answer and limits.<br>**B3f (iv′), derived from the source:** one entry of this workload (empty spec, 16 local ranges, failed in `getNeighborsAndRanges`) retains `CoordinatorState` 88, `long[6]` 64, `$Phase` 24, `AtomicReference` 16, `Result` 24 (its message string is shared with `repairStatusByCmd`, `RepairCoordinator.java:220,236-237`), empty `ConcurrentHashMap` 64, keyspace `String` + `byte[2]` 48, `RepairOption` 56, 4 `HashSet` + 4 `HashMap` 256, `HashMap$Node[32]` 144, 16 `HashMap$Node` 512, 16 new `Range` 384 (`SimpleStrategy.java:68`) = **E_src 1,680 B**; the cache's structure per entry is 112 B (entry 64, value reference 16, key `TimeUUID` 32), plus segment tables T = 640 / 4,224 / 16,512 B (Guava 32.0.1 `Segment.put`/`expand`, read with `javap`). **Conditions:** (iv′-1) `CoordinatorState` in the after-dump = reachable = count₁, none reachable with the cut, the referent unreachable with the cut; (iv′-2) e_v = R_values/count₁ in the frozen [512, 5120] B at every S and max/min e_v ≤ 1.01; (iv′-3) null control: base dump R_values = 0, no `CoordinatorState`; (iv′-4) R_cache ≤ count₁ × (e_v + 112) + T + 4,096 B and strictly increasing with S. **Derived expectations (report only):** e_v = 1,680 B; structure(after) − structure(base) = 112 × count₁ + T − 192 B. The Δ live-heap relations of 2026-10-26 become records.<br>**B3g:** row 1's bytes half read with (iv′); added rows: state outside the cache → Not confirmed for bytes; (iv′-2)/(iv′-4) miss → Not confirmed for bytes; (iv′-3) or the instrument fails → Invalid for bytes (tier Not confirmed — caps (entry count)); all hold but a derived size missed → Confirmed, reported. The run-1 Δ rows are superseded for this tier. **B3h:** the base dump as null control. **B3e / B4:** fresh clone `$W/cassandra-run71`, node `$W/node-rss71`, paths.<br>B1, B3f (i)–(iii), (v), the count half of row 1, the other controls and the unit tier are unchanged. |
| **Case-file version** | sha256 **`92f32f87e6f36e4053e6c0528e59d136168594f593ec9cdbdbc5523c37bcef3b`**, a new row in `_INDEX.md` §4: "re-frozen after run 1 for cluster re-run (B3d, B3e, B3f (iv), B3g, B3h, B4), authorised by the user". The earlier rows (`46c6d010…`, `020f07ad…`, `348f780b…`) are kept. Hashed at 00:56:07 EDT, after the fresh clone was built (00:48:31–00:49:32) and before the shakedown (00:59:30) or any re-run reading; recorded again at 00:59:24 in [`run1b-cluster/harness-sha-run2.txt`](repair_state_size-setRepairStateSize-size--autonomous/run1b-cluster/harness-sha-run2.txt), and a copy of the file at that hash is kept as `case-file-at-refreeze-92f32f87.md` in the log folder. Section D was filled afterwards, so the file's current hash differs by that section only. Base commit `a2460b60`; nothing committed. |
| **Harness** | Run 1's harness with changes H1 (paths), H2 (dumps and analyser) and H3 (self-check) only (§3). Command: `RSS_C=$W/cassandra-run71 RSS_NODE=$W/node-rss71 RSS_DUMP=1 cluster-run.sh shake2 200 50`, then the same with `run2 2000 50 500 100000`. Instrument checks: the known answer (above) for `HprofRetained` (first before the re-freeze, again at 00:58:40 with the final version, which only added the "unreached" line: R_cache 7,568, R_values 7,200, 1 item reachable after the cut) and for the self-check's reader; `EntryLayoutProbe`; in the shakedown both dumps were taken and analysed, the cut removed one edge with the referent unreachable, the empty-cache dump retained 0 B of state, and the two readers agreed. The self-check ran end to end on the shakedown first: 28 checks, 0 failed, exit 0. |
| **What was known of run 1 when writing it, and would run 1 pass** | Everything in §4.1–§5 of run 1: the counts, Totals and drifts, the Δ differences (2,739,488 and 1,539,920 B; e = 1,826 and 790 B), Δ(500) − Δ(50) = −1,199,568 B, and run 1's histogram rows for `CoordinatorState` (88 B), `$Phase` (24 B), `RepairOption` (56 B), `Completable$Result` (24 B), `LocalCache$StrongAccessWriteEntry` (64 B) and `$StrongValueReference` (16 B) per instance. The shallow sizes in the derivation were read again from a fresh probe JVM (`EntryLayoutProbe.java`, before the re-freeze; they agree with run 1's rows); E_src, the 112 B, T and every band and allowance come from the source and the Guava jar, and the e band [512, 5120] B is the frozen one, unchanged. **Run 1 would not pass**: it took no heap dump, so under the amended B3g its bytes half falls in the Invalid row (shown by the self-check's pass 3: 6 failed checks, all "dump present"); its count half holds as before. |

### 7.2 Environment

Same host as run 1 (§2): `yangwang-mbp`, macOS 27.0.1 / Darwin 27.0.0 arm64, OpenJDK 11.0.32.1, Ant 1.10.18; free disk 109 GiB; loopback `.1`–`.3` present (only `.1`
used); ports 7000/7199/9042 free and no `CassandraDaemon` before. 2026-10-28 (EDT): fresh clone and build 00:48:31–00:49:32; instrument checks (probe 00:53, known
answer first before the re-freeze, again with the final analyser at 00:58:40); re-freeze 00:56:07; harness hashes recorded 00:59:24; shakedown 00:59:30–01:06:04;
re-run 01:07:56–01:28:17. Fresh clone from `~/cassandra-src` at `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), no local change:
`$W/cassandra-run71` (`ant -Dlocal.repository=$W/m2 build-test`, `BUILD SUCCESSFUL`, 55 s; [`run1b-cluster/clone-build-run71.txt`](repair_state_size-setRepairStateSize-size--autonomous/run1b-cluster/clone-build-run71.txt)).
Node `MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M` (`-Xms1G -Xmx1G` in every start's `JVM Arguments`), shipped `jvm*-server.options` (G1, no string deduplication), no agent.
Node data in `$W/node-rss71`, wiped before and after. Full logs: `~/Library/Caches/stage4/logs/repair_state_size-setRepairStateSize/`: `clone-run71.log`,
`build-test-run71.log`, `clone-build-run71.txt`, `instrument-run2/` (`entry-layout-probe.txt`, `known-answer.txt`, `ka-dump.hprof`, `ka-hist.txt`, `ka-hprofretained.txt`),
`case-file-at-refreeze-92f32f87.md`, `harness-sha-run2.txt`, `driver-shake2.out`, `cluster-shake2/`, `selfcheck-shake2.out`, `driver-run2.out`, `cluster-run2/` (as run 1's
`cluster-run1/`, plus per value `dump-base.hprof`, `dump-after.hprof` (78–104 MB each) and `ret-base.txt`, `ret-after.txt`), `selfcheck-run2.out`,
`selfcheck-run2-under-run1-relations.out`, `selfcheck-known-answer-run1-relations-{run1,amended}.out`. Excerpts:
[`run1b-cluster/`](repair_state_size-setRepairStateSize-size--autonomous/run1b-cluster/) (`cluster/` with run 1's kinds of files plus `ret-*.txt` and `dump-sizes.txt`;
`shakedown/`; `instrument/`; `selfcheck.py`; `selfcheck.out`; `selfcheck-rerun-under-run1-relations.out`; `selfcheck-known-answer-on-run1-relations-{run1,amended}.out`;
`harness-sha-run2.txt`; `clone-build-run71.txt`).

### 7.3 Readings

From `run1b-cluster/cluster/summary.txt` and, per value, `startline.txt`, `rep.log`, `cql-*.txt`, `hist-*-excerpt.txt`, `ret-base.txt`, `ret-after.txt`; recomputed from
the raw files (including the raw dumps, with its own HPROF reader) by `selfcheck.py`. Every value: startup line with the yaml's S once; `issued 2000`, Rep exit 0, 41–42 s;
log segment 2,000 `Starting repair command #`, 2,000 `Nothing to repair for`, 2,000 `WARN … Repair … aborted`, 0 `ERROR`; participates 0 before and after;
`ParticipateState` 0; `$StrongWriteEntry` 0.

**Count half and live-heap records** (as run 1's table)

| S (yaml) | Startup line | count₀ · count₁ · 30 s later | `CoordinatorState` inst / bytes | `$Phase` · `RepairOption` inst | `RepairCoordinator` | used₀ (B) · drift₀ | used₁ · drift₁ | Δ = used₁ − used₀ (record) | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| 50 | `… or for 50 elements` | 0 · **50** · 50 | 50 / 4,400 | 50 · 50 | 0 | 50,763,368 · −124,832 | 59,046,720 · −1,576 | 8,283,352 | `cluster/S50/` |
| 500 | `… or for 500 elements` | 0 · **500** · 500 | 500 / 44,000 | 500 · 500 | 0 | 62,224,536 · −115,144 | 69,306,440 · −3,024 | 7,081,904 | `cluster/S500/` |
| 100000 (default) | `… or for 100000 elements` | 0 · **2000** · 2000 | 2000 / 176,000 | 2000 · 2000 | 0 | 62,526,080 · −121,088 | 72,617,528 · +160 | 10,091,448 | `cluster/S100000/` |

`LocalCache$StrongAccessWriteEntry` 2,050 / 2,500 / 4,000 = count₁ + 2,000 (`repairStatusByCmd` holds one entry per command), as in run 1.

**Bytes half: instrument (6), one heap dump per reading, each inside one node start** (B3f (iv′))

| S | base dump: R_cache · R_values · `CoordinatorState` | after dump: `CoordinatorState` in dump / reachable / reachable with the cut | R_values | **e_v = R_values / count₁** | R_cache (bound count₁ × (e_v + 112) + T + 4,096) | structure = R_cache − R_values; after − base (derived 112 × count₁ + T − 192) | Evidence |
|---|---|---|---|---|---|---|---|
| 50 | 1,408 · **0** · 0 | 50 / 50 / **0** | 88,400 | **1,768.00 B** | 95,856 (98,736) | 7,456; **6,048** (6,048) | `S50/ret-*.txt` |
| 500 | 1,408 · **0** · 0 | 500 / 500 / **0** | 884,000 | **1,768.00 B** | 945,440 (948,320) | 61,440; **60,032** (60,032) | `S500/ret-*.txt` |
| 100000 | 1,408 · **0** · 0 | 2000 / 2000 / **0** | 3,536,000 | **1,768.00 B** | 3,777,728 (3,780,608) | 241,728; **240,320** (240,320) | `S100000/ret-*.txt` |

In every dump the cut removed exactly one reference and left its referent unreachable; no object inside R_cache was sized by the layout estimate; the harness's
`HprofRetained` and the self-check's independent reader give the same R_cache and R_values for all six dumps. max e_v / min e_v = **1.00000**; R_cache 95,856 <
945,440 < 3,777,728. The cache's fixed objects F = structure(base) − 192 = 1,216 B at every value.

Per-class content of R_values (every value; per entry): `CoordinatorState` 88, `long[6]` 64, `$Phase` 24, `AtomicReference` 16, `Completable$Result` 24, `ConcurrentHashMap` 64,
`String` 24 + `byte[2]` 24, `RepairOption` 56, 4 `HashSet` 64, 4 `HashMap` 192, `HashMap$Node[32]` 144, 16 `HashMap$Node` 512, 16 `Range` 384 — the 1,680 B derived — plus
**4 `HashMap$KeySet` (64 B) and 1 `ConcurrentHashMap$KeySetView` (24 B)** = 1,768 B (`S100000/ret-after.txt`, `CLASS R_values` lines). The structure: 2,000
`$StrongAccessWriteEntry` 128,000, 2,000 `$StrongValueReference` 32,000, 2,000 `TimeUUID` 64,000, four `Object[1024]` tables, and the fixed Guava objects.

Records (were conditions in run 1, superseded by the amendment): Δ(100000) − Δ(500) = 3,009,544 B (e = 2,006.4 B) and Δ(100000) − Δ(50) = 1,808,096 B (e = 927.2 B),
both above 3 × drift (363,264 and 374,496 B); **Δ(500) − Δ(50) = −1,201,448 B** — the start-to-start variation of the live-heap total seen in run 1 recurs at the same size.

### 7.4 Cluster re-run — conclusion and logic

1. **Validity.**
   - The re-run used the re-frozen version (`92f32f87…ef3b`, hashed at 00:56:07, before the shakedown and the re-run) [observed: `_INDEX.md` §4; `harness-sha-run2.txt`; `summary.txt` first line 01:07:56].
   - Every step of B3 ran from the beginning in the frozen order, in a fresh clone, after a shakedown that ran every step including both dumps and both analyses [observed: `cluster/summary.txt`, `shakedown/summary.txt`].
   - Each start logged the yaml's S; 2,000 commands issued and 2,000 reached the coordinator at every S; count₀ = 0; the limit was passed at S = 50 and 500 [observed].
   - Instrument (6): two dumps per start, each analysed; one cut edge, referent unreachable after the cut, in all six; the null control (base dumps) R_values = 0 and no state; the known answer holds for both readers [observed: `ret-*.txt`, `selfcheck.out`].
   - Valid.
2. **Readings.** The count half repeats run 1 exactly (50 · 500 · 2000). The retained heap of the cached states is exactly 1,768 B × count₁ at all three values, and the cache's total retained heap is that plus 112 B per entry, the segment tables and 1,216 B of fixed objects. The live-heap Total again varies between starts by 1.2 MB (Δ(500) < Δ(50)), now only a record [observed].
3. **Matched row.** B3g row 1 read with the 2026-10-26 and 2026-10-28 amendments, through the added row "count part and (iv′-1)–(iv′-4) hold, but e_v ≠ 1,680 B — Confirmed; the derived entry size is wrong (reported)". Each part [observed; computed by `run1b-cluster/selfcheck.py`]:
   - count half: count₁ 50 · 500 · 2000 exactly (and 30 s later); `CoordinatorState` and `$Phase` instances = count₁; `RepairCoordinator` 0; startup line = S; issued and `Starting` 2,000;
   - (iv′-1) `CoordinatorState` in each after-dump = reachable = count₁, **0 reachable with the cut**, referent unreachable with the cut;
   - (iv′-2) e_v = 1,768.00 B at each S, in [512, 5120] B; max/min 1.00000 ≤ 1.01;
   - (iv′-3) base dumps R_values 0, no state;
   - (iv′-4) R_cache 95,856 ≤ 98,736; 945,440 ≤ 948,320; 3,777,728 ≤ 3,780,608; strictly increasing;
   - derived expectations: structure(after) − structure(base) = 6,048 / 60,032 / 240,320 B, **equal** to 112 × count₁ + T − 192; e_v = 1,768 B, **88 B above** E_src = 1,680 B.

   **Tier rule: Confirmed.**
4. **Excluded rows.**
   - Row 2 (count₁ = 2000 for S = 50): 50. Row 3 (instances ≫ S): instances = count₁. Row 4 (count₁ = 0): no.
   - 2026-10-26 added rows: count₁ < S — no; `RepairCoordinator` > 0 — 0; startup line ≠ S — no; issued or `Starting` ≠ 2000 — no; participates > 0 — 0; second count ≠ count₁ — no. The Δ rows are superseded (their quantities recorded above).
   - 2026-10-28 added rows: state outside the cache — 0 at every S; (iv′-2)/(iv′-4) miss — no; (iv′-3) or instrument failure — no.

   [observed]
5. **Observed vs. inferred.**
   - Observed: every condition, from the raw cqlsh outputs, histograms, logs and dumps.
   - Inferred: that R_values is the states' retained heap rests on the dump containing every live object and on the roots being complete for these objects; the dump lacks the string table and class-mirror fields as roots (≈ 45,000 objects, ≈ 2 MB per dump, "unreached"), and an object held both by such a root and by a state would be counted as retained. The source holds no repair-state object there, and the per-class content of R_values is exactly the derived list plus the two lazily cached views, all created per command.
   - The 88 B the derivation missed are lazily created, cached collection views: `HashSet.iterator()` makes and caches its map's `KeySet` (16 B), and three of the four sets are iterated by `RepairOption.toString()` for the "Starting repair command" line (`RepairCoordinator.java:366-367`, `RepairOption.java:437-441`) and the ranges set by `getNeighborsAndRanges` (`RepairCoordinator.java:382`); `ConcurrentHashMap.keySet()` caches a `KeySetView` (24 B) when the virtual table builds a row (`LocalRepairTables.java:156`, `getSessionIds()`). This is read from the source after the readings, as an explanation; nothing is amended because of it.
6. **Deviations and gaps.**
   - None against the re-frozen runbook; no runbook defect; no harness change after the re-freeze besides those listed in §3 (H1–H3).
   - The amendment was written knowing run 1's readings (stated in §7.1 and in the amendment); the shakedown, after the re-freeze, already showed e_v = 1,768 B, and nothing was changed after it.
   - One node, so every entry is a failed-early state; the participant cache is not exercised; B3 tests startup, not the setter. The per-entry figure is for this workload: a real repair's entry also holds sessions, jobs, the column-family list and `NeighborsAndRanges`, which no knob bounds (A3 amendment (ii)).
7. **Core question.** With `repair_state_size: S` in the yaml, the node keeps exactly min(S, N) coordinator states, and the heap they keep alive is exactly 1,768 B × that count inside one node start (88,400 / 884,000 / 3,536,000 B for 50 / 500 / 2000 entries); no state is held anywhere but the cache; the cache's whole retained heap is 1,880 B per entry plus its tables and 1.2 KB of fixed objects (95,856 / 945,440 / 3,777,728 B). So the knob caps the bytes of the repair-state cache as S × the entry size of the workload; it does not bound the size of one entry.

**Conclusion (one line):** B3g row 1 with the amended B3f (iv′), through the added row "derived entry size wrong (reported)": confirmed — caps.

### 7.5 Self-check of the cluster re-run — AI

`run1b-cluster/selfcheck.py` (H3) re-reads, per value, the raw `system.log`, `rep.log`, cqlsh outputs and `jcmd` histograms, and parses the raw heap dumps with its own
HPROF reader (written separately from `HprofRetained.java`; it compares its numbers with the harness's `ret-*.txt` only afterwards); it does not read `summary.txt`.
It was written after the re-freeze and before any re-run reading, and was changed once before the shakedown (sizes of hidden classes taken from the histogram name with its
`/0x…` suffix, else a layout estimate that is reported; one message text) and not after it.
- **Pass 0 (shakedown, run end to end first):** 28 checks, 0 failed, exit 0 (one value, so the across-S relations are reported as not evaluable; verdict line marked "not judged") ([`run1b-cluster/shakedown/selfcheck.out`](repair_state_size-setRepairStateSize-size--autonomous/run1b-cluster/shakedown/selfcheck.out)).
- **Pass 1 (re-run raw files, amended relations):** **80 checks, 80 hold, 0 fail**, exit 0; verdict `added derived-size row -> Confirmed, caps` ([`run1b-cluster/selfcheck.out`](repair_state_size-setRepairStateSize-size--autonomous/run1b-cluster/selfcheck.out)). The known answer holds for its reader (R_cache 7,568, R_values 7,200, 1 item reachable after the cut).
- **Pass 2 (known answer, run 1's raw files, run-1 relations):** 49 checks, 0 failed; the 53 cluster lines are **identical** to the cluster lines of `run1/selfcheck.out` (`diff` empty) ([`selfcheck-known-answer-on-run1-relations-run1.out`](repair_state_size-setRepairStateSize-size--autonomous/run1b-cluster/selfcheck-known-answer-on-run1-relations-run1.out)).
- **Pass 3 (run 1's raw files, amended relations):** 54 checks, 6 failed — all "dump present"; verdict `Invalid for bytes; tier Not confirmed, caps (entry count)`: run 1 would not pass the amended relations, and the script tells it apart from the re-run ([`…-relations-amended.out`](repair_state_size-setRepairStateSize-size--autonomous/run1b-cluster/selfcheck-known-answer-on-run1-relations-amended.out)).
- **Pass 4 (information, re-run raw files, run-1 relations):** 49 checks, 0 failed — the frozen Δ relations pass again by their numbers (e = 2,006 and 927 B), while Δ(500) − Δ(50) = −1,201,448 B repeats the cross-start variation that made run 1's self-check downgrade them ([`selfcheck-rerun-under-run1-relations.out`](repair_state_size-setRepairStateSize-size--autonomous/run1b-cluster/selfcheck-rerun-under-run1-relations.out)).

Raw files re-opened by hand: `cluster-run2/S500/cql-repairs-1.txt` (`500`, 1 row); the three starts' `n1/system.log` (`Storing repair state for 3d or for 50 / 500 / 100000 elements`);
`S500/ret-after.txt` (`CUT … edges=1 targetsReachableAfterCut=0`, `VALUE … inDump=500 reachable=500 reachableAfterCut=0`, `RETAINED R_cache=945440 R_values=884000`);
`S50/ret-base.txt` (`R_values=0`, `inDump=0`); `S100000/ret-after.txt` (`CLASS R_values` lines: 16 kinds, 3,536,000 B); `S100000/rep.log` (`issued 2000`); `summary.txt`
(final daemon processes none, node wiped).

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | Re-frozen hash before the shakedown; counts, startup lines and command counts re-read; both readers agree on every dump; null control and known answer hold. |
| 2. Readings | yes | Counts, Totals, drifts and every dump quantity recomputed from the raw files. |
| 3. Matched row | yes | Count half and (iv′-1)–(iv′-4) pass; the derived e_v misses by 88 B, which selects the "derived size wrong, reported" row, a Confirmed row. |
| 4. Excluded rows | yes | |
| 5. Observed vs. inferred | yes | The completeness of the dump's roots for these objects is the one inference; named, with the per-class content as support. |
| 6. Deviations and gaps | yes | The non-blind amendment, the shakedown's e_v and the 88 B explanation are stated. |
| 7. Core question — logic | yes | The bytes reading no longer needs anything to cancel between starts: each value's retained heap is read inside its own start, with an empty-cache control in the same start. |

**Run 2?** No (2026-10-28). The count half repeats run 1 exactly, and the bytes half is an exact, deterministic reading (identical per entry at three values, and the
structure equal to the derivation to the byte), confirmed by two independent readers of the same dumps; a further run would not change the row.

### 7.6 Verdict of the cluster re-run

**Confirmed — caps** (B3g row 1 with the amended B3f (iv′), through the added row "derived entry size wrong (reported)": e_v = 1,768 B, not the derived 1,680 B).
It is filed in §8 as a new cluster row; the run-1 cluster row (Not confirmed — caps (entry count)) is kept.

**End of the re-run:** no `CassandraDaemon`, `Rep.java` or analyser process; ports 7199/9042 free; `$W/node-rss71` removed; `git -C $W/cassandra-run71 status` clean;
no `cassandra.logdir_IS_UNDEFINED/` folder; `results/<stem>/run1/` unchanged.

## 8. Verdict — AI

**Stage-3 estimate:** positive (with three limits: entry count, startup only, bytes per entry unbounded).

**Claim tested:** "With `repair_state_size: S` at startup, after N > S repair commands the coordinator cache holds at most S
`CoordinatorState` objects, and their retained heap is bounded by S × the per-entry size. For N ≤ S, all N are retained. Calling
`DatabaseDescriptor.setRepairStateSize(S')` after construction does not change how many entries are retained." (B1)

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (row 1: retained exactly 10, 100, 1000 of 5,000 and 5,000 at the default, in three runs; bytes 604 B per bare entry, ratios 9.985 and 4.999; post-construction set leaves 100; line 5070 logs only on change) | caps (entry count; bytes of the retained entries follow it) | run 1 + self-check | 2026-10-26 |
| Cluster | **Not confirmed** for bytes (added row "count part holds, Δ difference not resolved", by the self-check's part 7; the count half of row 1 is exact: 50 · 500 · 2000 states, instances = count, nothing queued, startup line = S) | caps (entry count) | run 1 + self-check | 2026-10-26 |
| Cluster (re-run at `92f32f87…`, after the user-authorised B3d, B3e, B3f (iv), B3g, B3h, B4 amendment) | **Confirmed** — B3g row 1 with the amended B3f (iv′), through the added row "derived entry size wrong (reported)": count₁ exactly 50 · 500 · 2000 of 2,000 commands, instances = count₁, nothing queued, startup line = S; in one heap dump per start the cached states retain exactly 1,768 B each (R_values 88,400 / 884,000 / 3,536,000 B; max/min 1.00000), no state is reachable outside the cache, the empty-cache control retains 0 B, and the whole cache retains 95,856 / 945,440 / 3,777,728 B (≤ the derived bound; structure equal to the derivation to the byte); the derived entry size was 1,680 B (88 B of lazily cached collection views missed); the live-heap Δ relations are records (Δ(500) − Δ(50) = −1.2 MB again) | caps (entry count, and the cache's retained heap = count × 1,880 B + tables + 1.2 KB for this workload; one entry's size is not bounded) | cluster re-run (§7) + self-check | 2026-10-28 |

"Entry count is capped" holds on both tiers; "bytes are capped" holds in the unit tier for bare entries (≈ 604 B × S) and is not shown on
the node. In no tier does the knob bound the size of one entry, so bytes are capped only as S × the workload's entry size. The setter at
line 5070 cannot be reached on a node; called directly, it changes the field and logs but leaves a live cache's capacity unchanged.

**Feedback filed:** the case file's section D (uncommitted); the thirteen step-0 amendments and the post-shakedown B3e amendment are in
the case file, dated, with both sha256 values as new rows in `_INDEX.md` §4; `_INDEX.md` §1 Stage 4 column and the
coverage line updated. No section was amended for a refutation (none occurred).

**Feedback filed for the cluster re-run (2026-10-28):** the six amendments `Amendment 2026-10-28 (after run 1, authorised by the user)` in the case file (B3d, B3e, B3f (iv′), B3g, B3h, B4); a new `_INDEX.md` §4 row (`92f32f87…`); the case file's section D (new entry); the §1 Stage 4 column (run-1 text kept, re-run verdict appended). The coverage section is not touched. No refutation, so no other case section is amended. Recommendations for stage 3: (1) a claim about the heap a cache *retains* is best tested on the retained set itself, inside one JVM (here a heap dump cut at the cache's field, exact to the byte), not on differences of live-heap totals between node starts, which on this host vary by ≈ 1.2 MB from start to start; (2) an entry-size derivation should count lazily cached views (`HashMap.keySet`, `ConcurrentHashMap.keySet`) created by logging or by virtual-table reads (88 B of 1,768 B here).
