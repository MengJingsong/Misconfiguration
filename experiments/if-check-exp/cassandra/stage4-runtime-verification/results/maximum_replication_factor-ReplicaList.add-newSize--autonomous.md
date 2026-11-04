# maximum_replication_factor-ReplicaList.add-newSize--autonomous — stage-4 results  <!-- file: results/maximum_replication_factor-ReplicaList.add-newSize--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`maximum_replication_factor-ReplicaList.add-newSize--autonomous`](../../stage3-ai-deep-read/cases/maximum_replication_factor-ReplicaList.add-newSize--autonomous.md)
>
> **Status:** verdict filed (2026-10-26); run 1 both tiers, self-checked; no run 2
>
> **Outcome class:** true negative (estimate negative, effect does not cap)
>
> **Outcome class:** true positive / false positive / true negative / false negative / undetermined — the stage-3 estimate against the effect found below ([definition](../README.md#outcome-class)); fill it when both tiers are filed
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
| **Case-file version** | Base commit `e776524` plus the audit's amendments of 2026-10-26 (uncommitted at freeze time; the orchestrator commits). **sha256 of the whole file after amendments: `5afd908846f2fc6cd6cc8fe29d24a12a88d0676d97f6cd5cae45c0361d93ffa8`.** Frozen before run 1: sha256 of the unit prediction and conclusions text (B2f through B2g: from `**B2f.` up to, not including, `**B2h.`): `86cb96d8ca4bd279e029906014d8b9ed4a47db4ff113c1a01c550e835a329103`; of the cluster text (B3f through B3g: `**B3f.` up to `**B3h.`): `c873096e9355af0d9571df1c87a9170ac477717d321bf68a31b02d695f6e09c2`. History: first freeze (whole file `adcb65fb...`, B2 text `7fcde701...`) was taken before any reading; a shakedown of the unit test then showed the unit positive control cannot throw with a null ClientState, so B2e step 4 and two B2g rows were reworded (amendment 5 in section D, reason from `Guardrail.java:139-140` and `Threshold.java:80-86`, not from a growth reading); the B2 text hash was re-taken before run 1. The B3 text hash never changed. Section D takes feedback after the runs, so the whole-file hash will change then; the two table hashes will not. |
| **Harness** | `harness/maximum_replication_factor-ReplicaList.add-newSize--autonomous/` (listed in its README.md); not committed by the agent (the orchestrator commits) |
| **Tiers and values** | Unit (B2): N in 1,2,3,4,9,10,100,10_000,1_000_000 x initial capacity 0 / N x threshold -1, 1, 3. Cluster (B3): one node, PasswordAuthenticator, 1 GiB heap, threshold -1/1/3 x two stress runs of 1M writes into an RF-1 keyspace; DDL control by an ordinary role; 200-keyspace step. The optional 3-node ring is n/a (one node; reason in the case file's B3a amendment). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | B1/A2: the guardrail constrains a replica count (RF), not bytes; the bytes are the `Replica[]` array (16 + 4 x capacity, derivable). Acceptable for a negative claim: the quantity under test is the array's bytes, named in B2d/B3d. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met after amendment | B2b had two threshold values (-1, 3); amended to -1, 1, 3. B3b has -1, 1, 3. N and initial capacity are a second varied knob. |
| A. Core question | real resource measured, not only the counter (gap named) | Met after amendment | B2d measured `contents.length` and MemoryMeter bytes of the array; amended to add the heap of 10 retained 1M lists as the real-resource check. B3d reads the live `Replica[]` histogram line (bytes) and jstat heap. |
| A. Core question | usage driven to the limit and past it | Met | There is no byte limit; N goes to 1_000_000 (4.7 MB array) and the DDL control exceeds thresholds 1 and 3 (RF 10 and RF 3). In the cluster tier the arrays stay tiny, which is the claim. |
| B. Logic | each step says what it establishes | Met | B2e and B3e steps each name their purpose or a prediction. |
| B. Logic | prediction stated in numbers or a clear relation | Met after amendment | B2f gives the capacity sequence; its reallocation count for N=10_000 was wrong (12; the listed sequence has 13): amended 2026-10-26 (arithmetic, not from a reading). B3f gives bounds (<1 MB, +/-10 percent). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g cover flat, refuted (threshold changes the list), control not working, limit not reached, measurement wrong, retained too large. Not covered: usage exceeds the limit (there is none). An unmatched reading is Not confirmed (no matching row). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met (adapted) | For a negative claim: bytes independent of the threshold plus the control that proves the knob was applied and binds (guard throws; DDL rejected). Both are required by the first B2g/B3g rows. |
| B. Logic | alternative explanations and their controls | Met after amendment | B2h/B3h: exact initial capacity, shared Replica, threshold unset, fixed heap, twice for noise. Added: the DDL control must run as a non-superuser, or it is vacuous. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, ground, A1-A4 and B1 are clear. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met after amendment | Amendments give the setter name, daemon initialisation, authenticator, ports and the JMX route. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | B3 leaves exact stress options and sample timing to the harness (fixed in its README before run 1); sampling interval amended to 10 s. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | pc12 has JDK 11, Ant and a build; the unit test, Jmx.java and run scripts are step-2 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 1M adds in the unit test take milliseconds; 1M stress writes on tmpfs with a 1 GiB heap take about 1-3 minutes; disk under 1 GB on tmpfs. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked in cassandra-5.0.9: AbstractReplicaCollection.java:103-118 (growth 3/9/x2 at 109-114, copyOf 115), Config.java:931-932, Guardrails.java:481-487, GuardrailsOptions.java:806 (setter), SimpleStrategy.java:71 and 111-112, NetworkTopologyStrategy.java:187 and 352-353, EndpointsForRange.java:82-83. Two defects found: Guardrail.java:95 and ClientState.java:604 (superusers skip guardrails) make the B3 DDL control vacuous without an authenticator; B2f's reallocation count. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Threshold values -1, 1, 3 and the two-argument setter | Applied 2026-10-26 (B2b) | Three knob values; `setMaximumReplicationFactorThreshold(warn, fail)` is the only setter |
| 2 | Reallocation count 13, capacity rule | Applied 2026-10-26 (B2c, B2f) | Arithmetic error in the filed prediction |
| 3 | `daemonInitialization()` in the unit test; copy-source.sh; extra reads | Applied 2026-10-26 (B2a, B2e, B2h) | `Guardrail.enabled` is false before daemon init, so the control would pass vacuously |
| 6 | Unit control reads `failsOn(10, null)` (not a thrown exception) | Applied 2026-10-26 (B2e step 4, B2g rows 2-3), re-frozen before run 1 | A null `ClientState` never throws (`Guardrail.java:139-140`); the guardrail is disabled while thresholds are -1 (`Threshold.java:80-86`) |
| 4 | PasswordAuthenticator and an ordinary role for the DDL control; local ports/tmpfs; no ring; JMX threshold change; 10 s histogram | Applied 2026-10-26 (B3a, B3d, B3e) | Superusers skip guardrails; AllowAll makes everyone a superuser |
| 5 | B3f's per-array byte figures (24 vs 32) assume compressed oops | Left for stage 3 | Stated as approximate; the rows use the relation, not the number |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-10-26 | not done |
| Node | `pc12` (`node1.jason92-320876`, 40 cores, 251 GiB) | |
| OS and kernel | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK | OpenJDK 11.0.32.1 | |
| Ant | 1.10.12 | |
| Local source copy | `copy-source.sh` from `cassandra/cassandra-5.0.9/` at repository commit `e776524`: `~/s4-b7-rl` (unit, `ant build-test`) and `~/s4-b7-rl-node` (cluster, `ant jar`) | |
| Case-file / harness commit | uncommitted at run time (orchestrator commits); case-file sha256 `5afd9088...` (section 1), harness md5 of the test `1e7f6a7bb47d46165af3e77a2f359d15` | |
| Storage for node data | tmpfs `/dev/shm/s4-b7-rl` (removed afterwards) | |
| Full logs | `pc12:~/s4-b7-rl-logs/{run1,run1-supp-rf3,shakedown0}/`; excerpts in `results/maximum_replication_factor-ReplicaList.add-newSize--autonomous/run1/` | |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | shakedown (not run 1) | B2e step 4 | The first test run (`run1/shakedown0/`) failed its instrument check: `Guardrail.enabled()` was false at threshold -1 and `guard(10, ..., null)` returned without throwing at 1 and 3. Cause from source: `Threshold.enabled` needs a threshold above 0 (`Threshold.java:80-86`); `Guardrail.fail` throws only for a non-null state (`Guardrail.java:139-140`). The other 65 checks of that run matched the prediction but the run is a shakedown and is not used. | B2e step 4 and two B2g rows reworded to `failsOn(10, null)`; test changed; B2 table hash re-taken before run 1 | 2026-10-26 | uncommitted (orchestrator) |
| 2 | cluster attempt 0 (not a reading) | B3e step 1 | `bin/cassandra -f -p` writes no pid file, so the script could not find the node and would have timed out; found by the log (no readings taken). The node was killed by PID; no leftover. | Script uses the Popen pid (the shell `exec`s the JVM) and checks it is the CassandraDaemon JVM | 2026-10-26 | harness only |
| 3 | cluster attempt 0b (not a reading) | script | A `\0` in an f-string put a NUL in a command; the script failed and its `finally` stopped the node. | Escaped | 2026-10-26 | harness only |

## 4. Run 1

**Scope:** unit tier (all N, both initial capacities, thresholds -1/1/3); cluster tier (six stress phases at thresholds -1, 1, 3, -1, 1, 3, P0 control, 200-keyspace step), plus one supplement (RF-3 keyspace, thresholds -1 and 3; not in the plan, run after run 1 to exercise the B3f per-array bullet). **Command log:** `maximum_replication_factor-ReplicaList.add-newSize--autonomous/run1/{unit,cluster,cluster-supp-rf3}/`; self-check output `run1/selfcheck.txt`.

### 4.1 Readings

**Unit tier** (`run1/unit/out.txt`, `summary.txt`: ant exit 0, 71 checks, 0 MISMATCH)

| Test or assertion | Result | Evidence |
|---|---|---|
| Capacity from 0, N = 1,2,3,4,9,10,100,10_000,1_000_000 | 3,3,3,9,9,18,144,18432,1179648 | `out.txt` `phase=growth` |
| Reallocations N=10_000 / 1_000_000 | 13 / 19 | `out.txt` |
| Bytes (N=10 / 10_000 / 1_000_000) | 88 / 73,744 / 4,718,608 (JVM measure equals `16 + 4 x cap`, 8-aligned) | `out.txt` |
| Exact initial capacity | cap = N, 0 reallocations, every N | `phase=exact` |
| Threshold -1, 1, 3 at N = 10, 1000, 1_000_000 | one (cap, reallocs, bytes) per N: (18,3,88), (1152,9,4624), (1179648,19,4718608); no `add` threw | `phase=sweep` |
| Control: guardrail fires (`failsOn`) | 10 vs thr 3: yes; 10 vs 1: yes; 2 vs 1: yes; 3 vs 3: no; 1 vs 1: no; 10 vs -1: no; at thr 3 a 1M list still grows to 1,179,648 | `control-*` checks |
| Builder capacity = RF | rf 1,3,10 -> 24, 32, 56 bytes | `phase=builder` |
| Heap of 10 retained 1M lists | 46,235,960 B vs instrument 47,186,080 B (ratio 0.980) | `phase=heap` |

**Cluster tier** (`run1/cluster/`; one node, PasswordAuthenticator, 1 GiB G1, stress 1M rows per phase, 0 errors, 10-12 s each)

| Threshold (phase) | Observable | Reading | Evidence |
|---|---|---|---|
| baseline | live `Replica[]` instances / bytes | 19 / 448 | `hist.csv` |
| -1 (p1, p4), 1 (p2, p5), 3 (p3, p6) | `Replica[]` after stress (and during, end) | 35 / 832 B in all six phases, at every sample (max over all samples 832) | `hist.csv`, `selfcheck.txt` |
| same | live heap (histogram total) | 108 to 159 MB after stress, varies with GC timing | `hist.csv` |
| K200 (thr -1) | `Replica[]` before / after 200 keyspaces (100 RF 1, 100 RF 3) | 35 / 832 B both | `hist.csv` |
| P0, thr 1 | ordinary role, RF 3 | rejected: "above the failure threshold of 1" (first-trigger check) | `ddl.csv`, `system-log-excerpt.txt` |
| per phase | DDL matrix (ordinary role RF 3, 4, 1; superuser RF 3) | as expected in all 24 rows: thr 1 rejects RF 3 and 4; thr 3 accepts RF 3, rejects RF 4; thr -1 accepts all; the superuser is never rejected | `ddl.csv` |
| supplement, RF-3 keyspace `ks_rf3`, thr -1 and 3 | `Replica[]` after stress | 35 / 960 B both (832 + 128 = 16 arrays x 8 B, 24 to 32 B each) | `cluster-supp-rf3/hist.csv` |

### 4.2 Conclusion and logic

1. **Validity** — valid. The limit in this file is "no byte limit", so reaching it means the list grew far past the threshold and the knob was shown applied and binding. [observed: `unit/out.txt`] N reached 1,000,000 (4.7 MB array) while threshold 3 was set and `failsOn(10)` was true. [observed: `cluster/ddl.csv`] The threshold read back as set (warn and fail) before every phase (`cluster/session.log`), and the ordinary role was rejected above it. The B3 hold-fixed settings: heap `-Xms1G -Xmx1G`, G1, loopback, same row count and seed in every phase [observed: `cluster/summary.txt` jvm line; `stress-p*.txt`: 1,000,000 partitions, 0 errors].
2. **Readings** — nothing contradicts another. [observed] The unit tier matches the frozen B2f exactly, including the amended count of 13 reallocations. The cluster `Replica[]` figure does not move at all (832 B), so the noise between repeated phases is zero.
3. **Matched row** — B2g row 1: "Bytes track capacity = 3/9/18/doubling and are independent of the threshold | Claim confirmed" and row 3 (guardrail fires at threshold 3 while the list still grows to 1,000,000: confirmed). B3g row 1: "`Replica[]` retained < 1 MB, identical across threshold values | Confirmed" and row 3: "RF 3 DDL rejected at threshold 1 (positive control), writes to RF 1 keyspace unchanged | Confirmed". Evidence in 4.1.
4. **Excluded rows** — B2g "add throws or capacity differs at threshold 3": no add threw, and one triple per N across thresholds. "Control `guard` does not fire": it fired (3 values). "N never beyond 18": N reached 1,000,000. "Bytes flat across N": bytes grew from 32 to 4.7 MB. B3g "changes with threshold alone": identical 832 B in six phases. "RF 3 DDL accepted at threshold 1": rejected. "Stress did not reach 1M, or histogram never shows `Replica[]`": 1M each, line present. "Retained tens of MB": 832 B.
5. **Observed vs. inferred** — Inferred: (a) the live `Replica[]` figure is a fair proxy for bytes held by `ReplicaList` arrays (only `ReplicaList.contents` is a `Replica[]` in the locator package; checked by the source but not by a heap dump); (b) the short-lived per-request lists are garbage and need not show in a forced-GC histogram, which is the claim; the allocation volume is not measured; (c) the unit bytes formula holds for the cluster JVM's compressed oops (the figures 24 and 32 B per array fit it).
6. **Deviations and gaps** — (i) No 3-node ring (declared `n/a`). (ii) Live heap is the histogram total, not `jstat` OU (histogram total is the lesson-preferred figure); heap varied by 50 MB between phases for unrelated reasons (memtable and caches), so only `Replica[]` is the instrument for the claim. (iii) B3f bullet 3 (RF 1 to 3 changes per-array size) was not exercised in the planned cluster phases; the supplement and the unit builder reading show it (24 to 32 B), so it holds, but the supplement is outside the planned run. (iv) The unit control cannot throw (null state); it reads `failsOn`; the throw was seen at the cluster tier. (v) The control binds a replica count at DDL, not bytes: it shows the knob is applied, and the instrument's sensitivity is shown by `Replica[]` moving 448 to 832 to 960 B and the array bytes moving with N and RF; no byte cap exists to bind.
7. **Core question** — Usage of the `ReplicaList` array followed the number of replicas added (N, and RF through the builder capacity) and did not follow the `maximum_replication_factor` threshold: the unit sweep gave one triple per N for -1, 1, 3, and the cluster gave 832 B in all six phases (parts 1-4). The threshold fires on RF at DDL (positive control), so it caps a count of replicas per new keyspace, not the bytes of this growth; the whole object is under 1 KB live. The line at `AbstractReplicaCollection.java:109` is not capped by any memory or disk limit.

**Conclusion (one line):** B2g row 1 and 3 / B3g row 1 and 3 — Confirmed, does not cap.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/maximum_replication_factor-ReplicaList.add-newSize--autonomous/selfcheck.py` re-parses `unit/out.txt`, `hist.csv`, `ddl.csv` and `stress-*.txt` and recomputes capacity, reallocations, bytes, sweep triples, the heap ratio, `Replica[]` per phase, the DDL matrix and stress totals without using the harness's own check lines: output `run1/selfcheck.txt`, ending `ALL HOLD`. I re-read the cited raw files.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `session.log` threshold read-backs; `ddl.csv` P0 rejected; stress totals |
| 2. Readings | yes | `out.txt` capacities and 13/19 reallocations recomputed; `hist.csv` all samples 832 B |
| 3. Matched row | yes | rows quoted from B2g/B3g (hash-frozen text) match the readings |
| 4. Excluded rows | yes | each excluded row checked above against `out.txt`, `ddl.csv`, `hist.csv` |
| 5. Observed vs. inferred | yes | inferred (a) to (c) listed; none changes the row |
| 6. Deviations and gaps | yes | gap (iii) closed by the supplement and the unit builder reading |
| 7. Core question | yes | follows the audited logic |

### 5.2 Run 2?

**No** (2026-10-26). The unit result is deterministic and exact, the cluster result is flat at 832 B in six phases with a firing control, and nothing rests on a fragile inference; a second run would add no information.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Comparison

Not applicable.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** (B1) The `ReplicaList` growth at line 109 is not capped by any memory or disk limit, and heap occupied by `ReplicaList` arrays follows the number of replicas added (and so RF), not the `maximum_replication_factor_*` thresholds.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1 and 3 — Confirmed | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | B3g row 1 and 3 — Confirmed | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control:** the guardrail fires on RF count: `failsOn` true for 10 against 3 and 1 (unit); an ordinary role is refused "above the failure threshold of 1" and 3 (cluster, `ddl.csv`), a superuser is not. The instrument (live `Replica[]`) moves with a real change: 19 to 35 arrays (448 to 832 B) after the first writes and 960 B with RF 3. The control is on a count, not on bytes of this array (none is capped), as audit item A1 says.

**Feedback filed:** the case file's section D updated (uncommitted; the orchestrator commits). Amendments 1 to 5 of section D were made before run 1.

**Upstream / doc candidates:** (1) the guardrail is skipped for superusers, and every client is a superuser under `AllowAllAuthenticator`, so `maximum_replication_factor` has no effect on a default install (`ClientState.java:604`); documenting this would help. (2) `Guardrail.fail` with a null `ClientState` logs and does not throw (`Guardrail.java:139-140`), so an internal caller of `guard(..., null)` is never refused (only a note; not used on this path).

**Leftovers on the node (pc12):** no process. `/dev/shm/s4-b7-rl` removed. Kept: build trees `~/s4-b7-rl`, `~/s4-b7-rl-node` and logs `~/s4-b7-rl-logs/`.
