# repair_disk_headroom_reject_ratio-setrepairdiskheadroomrejectratio-value--autonomous — stage-4 results  <!-- file: results/repair_disk_headroom_reject_ratio-setrepairdiskheadroomrejectratio-value--autonomous.md -->

> **Case:** [`repair_disk_headroom_reject_ratio-setrepairdiskheadroomrejectratio-value--autonomous`](../../stage3-ai-deep-read/cases/repair_disk_headroom_reject_ratio-setrepairdiskheadroomrejectratio-value--autonomous.md)
>
> **Status:** verdict filed (2026-10-27) — unit **Confirmed — does not cap**, cluster **Confirmed — does not cap**; run 1 + self-check, no run 2
>
> **Outcome class:** true negative (estimate `negative`; effect `does not cap`)
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `6e6cf92` (the case file is committed there without the amendments; the amendments are uncommitted). The file as filed declared both tiers `n/a`; they were un-declared by Amendments U1–U6 and C1–C6. sha256 of the whole file after those: `6efb7f2170bf1f3201a705e6deb90dff2b3fa76aa7d8fa7036b93293cf031328` (frozen 2026-10-27 02:46 UTC, before any run; copy `run1/case-frozen.md`; unchanged for the cluster tier). Section D changes after the run and is outside the freeze. |
| **Harness** | `harness/repair_disk_headroom_reject_ratio-setrepairdiskheadroomrejectratio-value--autonomous/`: new `HeadroomSetterRangeTest.java`, `selfcheck.py`; copied from the closed `repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio--guided/` harness: `RepairHeadroomCheckTest.java`, `RepairHeadroomVerbTest.java`, `DiskUsageOperandTest.java`, `headroom.btm`, `Jmx.java` (unchanged); `unit-run.sh` (mode `setter`, paths), `cluster-run.py` (label `range`, `bad=` argument of `trigger()`, `NaN` read-back, paths), `make-node-yaml.sh` (path). Untracked; the orchestrator commits. |
| **Tiers and values** | Unit (B2): setter argument rejected {−0.1, 1.1, 1.0000001, +Inf, −Inf, −1e300}, accepted {0.0, −0.0, 0.5, 1.0, NaN}; the real `verifyDiskHeadroomThreshold` at the boundary of stored 0.5 (also after rejected writes), 1.0 and NaN; closed `RepairHeadroomCheckTest` (92 checks), `RepairHeadroomVerbTest` (36), `DiskUsageOperandTest` (7), upstream `ActiveRepairServiceTest`, `GuardrailDiskUsageTest`. Cluster (B3): two nodes on loopback, RF 2, cap 1 GiB, sparse pad sets usage; sweep r = 0.0 (default) · 0.2 · 0.5 · 0.8 with usage below and above `L = (1 − r) × cap ± 4 MiB`; range arm: r = 0.5 plus rejected JMX writes −0.1 · 1.1 · 1.0000001 on both holders; NaN; yaml 1.5 (closed `valid`). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2/B1: the check bounds a setter argument; the stored ratio gates repairs on disk usage (`ActiveRepairService.java:649-662`). The check holds no bytes (named). |
| A. Core question | knob varied, ≥ 3 values incl. default | Not met → Met | both tiers `n/a`; U2/C1 give the rejected and accepted sets and the sweep 0.0 · 0.2 · 0.5 · 0.8. |
| A. Core question | real resource measured, not only the counter | Not met → Met | none in the file; the cluster arm reads real file-system bytes (a sparse pad file's apparent size plus the data directory, as `DiskUsageMonitor` counts) and real refusals; the unit tier's usage is a mock (named, U3). |
| A. Core question | usage driven to the limit and past it | Not met → Met | triggers at `L ± 4 MiB` for each ratio. |
| A. Core question | positive control (negative file) | Not met → Met | the closed same-knob case supplies it (U1, C1). |
| B. Logic | each step has an establishes-line | Not met → Met | U3, C2. |
| B. Logic | prediction in numbers or a clear relation | Not met → Met | U4, C3. |
| B. Logic | every plausible outcome has a conclusions row | Not met → Met | U5, C4. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | the setter's own exception text and the refusing node's own `ERROR` line with `HDR verdict admit=false`. |
| B. Logic | alternative explanations and controls | Met | C5. |
| C. Specific | a human can follow it from the intro and §9a | Met | A1–A3, B1. |
| C. Specific | an AI can run it without re-deriving the code path | Not met → Met | U2–U3, C1–C2. |
| C. Specific | knob, values, workload, commands, observables exact | Not met → Met | same. |
| D. Runnable | harness and prerequisites exist or are listed | Met | the closed harness exists. |
| D. Runnable | workload arithmetic reaches the limit | Met | pads are sparse; the ring is two JVMs of 2 GiB; 56 GB free; 13 triggers with a pad plus 4 ratio-0 controls, about 5 minutes. |
| D. Runnable | citations spot-checked against the pinned source | Met | `DatabaseDescriptor.java:5340-5352`, `ActiveRepairService.java:649-666`, `:1082-1090`, `Config.java:352`: as cited. The audit found one gap in the claim's reading: the comparison `value < 0.0 \|\| value > 1.0` is false for `NaN`, so `NaN` is accepted (U1); added as a recorded observation. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| U1–U6 | run the unit tier: setter outcomes (incl. NaN), boundary of the real check at the stored ratio, closed control, rows, verdict wording | applied 2026-10-27 | the `n/a` left the negative claim without a control |
| C1–C6 | run the cluster tier: the closed ring with a new `range` label, the sweep as control, the `valid` arm, rows | applied 2026-10-27 | same |
| left | A5's "Docs: `auto_repair.adoc:338-341`" and A4's grep list | left for stage 3 | no effect on the run |

**Agreement criteria** — run 2 not chosen (see 5.2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (node clock MDT; unit 20:46–20:52, cluster chain 20:57–21:02) |
| Node | `pc32` (`node2.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`), 40 cores, 251 GiB |
| OS and kernel | Ubuntu 22.04, `5.15.0-198-generic` |
| JDK | openjdk 11.0.32.1 2026-08-18 |
| Ant | Apache Ant 1.10.12 |
| Local source copy | unit: `~/cassandra-run4` (`copy-source.sh` from repository commit `6e6cf92`, `git describe`: `cassandra-5.0.9`, `ant build-test`); cluster: `~/cassandra-run1` (built, unmodified), Byteman 4.0.20 from its build |
| Case-file commit / harness commit | `6e6cf92` plus uncommitted amendments (sha256 in section 1) / harness untracked |
| Storage for node data | cluster: `~/s4b-hdr/N1`, `~/s4b-hdr/N2` on local `/dev/sda3` (a few MB each plus sparse pads), never under `/proj`; removed after the run |
| Full logs | `pc32:~/s4b-logs/hdr2/` (`unit/`, `run1/<label>/{summary.txt,triggers.csv,session.log}`, `chain.out`, `selfcheck.txt`, `case-frozen.md`) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| H1 | harness, before any cluster run | set-up | the copied `make-node-yaml.sh` still defaulted to `~/stage4-hdr` while `cluster-run.py` used `~/s4b-hdr` (the same slip that case 2 hit; caught by `grep` before the run) | default changed to `~/s4b-hdr` | 2026-10-27 | untracked |

No step failed to run as written in run 1; nothing was restarted.

## 4. Run 1

**Scope:** all unit classes; cluster labels `setup`, `sweep-p`, `range`, `valid`, `down` once each. **Command log:** `repair_disk_headroom_reject_ratio-setrepairdiskheadroomrejectratio-value--autonomous/run1/` (`unit/{summary.txt,S1-S2.out,U1-U2-U4a.out,U4b.out,U3.out}`, `cluster/<label>/{summary.txt,triggers.csv}`, `selfcheck.txt`, `chain.out`).

### 4.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Known answers: upstream `ActiveRepairServiceTest` / `GuardrailDiskUsageTest` | 16 / 13 tests, 0 failures | `unit/summary.txt` |
| S1, rejected −0.1 · 1.1 · 1.0000001 · +Inf · −Inf · −1e300 | setter and MBean wrapper throw `IllegalArgumentException("Value must be >= 0 and <= 1 for repair_disk_headroom_reject_ratio")`; getter stays 0.3; the setter call allocates 720 B each | `unit/S1-S2.out` |
| S1, accepted 0.0 · −0.0 · 0.5 · 1.0 · **NaN** | all stored (bit-exact; `NaN` read back as NaN); the call allocates 0 B | same |
| S2, stored 0.5 | real `verifyDiskHeadroomThreshold`: u = 0.50000 admit (0 `ERROR` lines), u = 0.50001 refuse (1 `ERROR` line); after rejected writes of 1.1 and −0.1: getter 0.5 and the same two verdicts | same |
| S2, stored 1.0; stored NaN | 1.0: u = 0.0 admit, 0.00001 refuse; NaN: u = 0.99999 admit and u = 5.0 admit, 0 `ERROR` lines | same |
| Setter test totals | 45 checks, 45 ok, 0 mismatches | `unit/summary.txt` |
| Closed positive control and operand tests | `RepairHeadroomCheckTest` 92 checks ok (boundary at r = 0.0 · 0.2 · 0.5 · 0.8, 1.0, default; raw 1.5 refuses at u = 0.00001 with threshold −50.00%); `RepairHeadroomVerbTest` 36 ok; `DiskUsageOperandTest` 7 ok; 0 mismatches | `unit/U1-U2-U4a.out`, `unit/U4b.out`, `unit/U3.out` |

**Cluster tier** (cap 1 GiB on both nodes; usage = data directory + sparse pad; `L = (1 − r) × cap`)

| Capacity value | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| — | setup | instrument | Byteman `TestScript` no errors; control repair: two `HDR usage` lines, `admit=true`, usage 0.00016 / 0.00014 vs the walk 0.000155 / 0.000131 (within 0.0005) | `cluster/setup/summary.txt` |
| r = 0.0 · 0.2 · 0.5 · 0.8 on the participant N2 (sweep, positive control) | A: `U0 = L − 4 MiB`; B: `U0 = L + 4 MiB` | verdicts, `nodetool repair` exit, `ERROR` line, started? | A admitted at u = 0.9961 · 0.7961 · 0.4961 · 0.1961 (two `admit=true`, exit 0); B refused by N2 only at u = 1.00391 · 0.80391 · 0.50391 · 0.20391 with `Rejecting incoming repair, disk usage (100.39% · 80.39% · 50.39% · 20.39%) above threshold (100.00% · 80.00% · 50.00% · 20.00%)`, nothing started; 32 of 32 expectations yes | `cluster/sweep-p/summary.txt`, `triggers.csv` |
| r = 0.5, rejected JMX writes on N2 | −0.1 · 1.1 · 1.0000001 (before A and before B) | write result; read-back | `SETFAIL … IllegalArgumentException: Value must be >= 0 and <= 1 for repair_disk_headroom_reject_ratio` ×6; read back 0.5 each time | `cluster/range/summary.txt` |
| same, then A and B | triggers after the rejected writes | verdicts | A admitted at u = 0.4961; B refused by N2 at 50.39% / 50.00% as in the sweep | same |
| r = 0.5, rejected JMX writes on N1 | same six writes (coordinator holder) | write result; verdicts | `SETFAIL` ×6, read back 0.5; A admitted; B refused by N1 (coordinator) at 50.39% / 50.00%, one `ERROR` line on N1 only | same |
| NaN on N2 | JMX write NaN, trigger at `U0 = L(0.5) + 4 MiB` | read-back; verdicts | read back NaN; usage 0.50391; both nodes `admit=true`; `nodetool repair` exit 0; no `ERROR` line | same |
| yaml 1.5 on N2 | `valid` (closed) | read-back; verdicts; JMX write | node started, JMX reads 1.5; a repair with no pad is refused by N2 (`disk usage (0.03%) above threshold (-50.00%)`); a JMX write of 1.5 fails with the range text; write 0.0 → repair admitted; restart without the yaml line reads 0.0 | `cluster/valid/summary.txt` |
| all | stop | daemons | `down`: none left | `cluster/down/summary.txt` |

### 4.2 Conclusion and logic

1. **Validity** — Valid. The limit was reached and passed: A is 4 MiB below `L`, B 4 MiB above, at every ratio, and the operand u was read from the Byteman trace within 0.0005 of the plan [observed: `cluster/sweep-p/summary.txt`]. Hold-fixed: ratio read back before every trigger (`KNOB … read back`), usage cap 1 GiB read back on both nodes (`INSTRUMENT jmx`), the ratio-0 control repair admitted before each ratio, and the instrument control repair matched the directory walk [observed: `cluster/setup/summary.txt`, `cluster/sweep-p/summary.txt`]. Unit: known answers pass [observed: `unit/summary.txt`].
2. **Readings** — nothing unusual; the one new fact is that `NaN` is accepted by the setter and by JMX and never rejects a repair (u = 0.50391 above the 0.5 boundary was admitted). The yaml value 1.5 is read back unvalidated (`valid`) [observed: `cluster/range/summary.txt`, `cluster/valid/summary.txt`].
3. **Matched rows** — Unit, B2g row (1) (Amendment U5): every rejected value throws the range text and leaves the getter at 0.3 and the boundary at 0.5; every accepted value is stored; the closed boundary tests pass, so the stored ratio moves the verdict [observed: `unit/S1-S2.out`, `unit/U1-U2-U4a.out`]: **Confirmed**. Cluster, B3g row (1) (Amendment C4): the sweep boundary moves with r (A admitted, B refused at 0.0 · 0.2 · 0.5 · 0.8); after rejected writes of −0.1, 1.1 and 1.0000001 on either holder the verdicts are those of 0.5; NaN is accepted; the yaml route is unvalidated [observed: `cluster/*/summary.txt`, `selfcheck.txt`]: **Confirmed — does not cap**.
4. **Excluded rows** — (2) rejected value changes getter or boundary: no, 0.3 and 0.5 unchanged, 12 of 12 read-backs 0.5 (`selfcheck.txt`). (3) out-of-range value accepted: no, six values rejected by the setter and the MBean, three by JMX on each holder. (4) control does not move or the closed checks mismatch: the boundary moved at four ratios; closed 92 + 36 + 7 checks ok. (5) NaN rejected: accepted. Cluster (3) refusal is not the check's own `ERROR` line: every B has exactly one, on the holder only, with the percentages of the plan.
5. **Observed vs. inferred** — Inferred: (i) "usage independent of whether the check exists" is read from the raw-value arms: the yaml 1.5 start (no setter, no check) behaves as a ratio of 1.5 (refuses every repair), i.e. skipping the check changes the admission outcome, not any held bytes; (ii) the unit tier's usage is a mocked `DiskUsageMonitor` (the cluster tier reads the real walk).
6. **Deviations and gaps** — One repair per cell (the closed ring's sweep was run once per ratio, as filed); two nodes on one host; the pad is sparse (apparent bytes, as the operand counts) and the real-bytes overshoot arm of the closed case was not re-run; the memory side is not applicable (the check holds nothing).
7. **Core question** — No: usage (disk usage as the check counts it) does not follow the setter's range check. The check accepts or rejects a number and stores or refuses it; a refused write changes neither the read-back nor the next repair's verdict [part 3, observed]. The stored ratio is the downstream, soft admission cap: the boundary follows it to 5 decimals at four ratios (positive control). The range check itself **does not cap** memory or disk. Two gaps in the check were seen: `NaN` passes it and turns the downstream cap off, and the yaml value is not checked at all.

**Conclusion (one line):** unit B2g row (1) and cluster B3g row (1) — claim confirmed: the range check is argument validation; the downstream `verifyDiskHeadroomThreshold` is the soft cap (effect: does not cap).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parsed `triggers.csv` of `sweep-p` and `range` (operand u from the trace, r, the verdict lines, the `nodetool` exit, the `ERROR` count) and recomputed `admit = (u + r <= 1)` itself for 13 triggers, counted the rejected-write lines and re-read the unit `.out` files: 23 checks PASS, 0 FAIL (`run1/selfcheck.txt`). By hand I re-opened `cluster/range/summary.txt` (the `REJECT` and `KNOB` lines, the NaN trigger), `cluster/valid/summary.txt`, `unit/S1-S2.out`.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | read-backs, `INSTRUMENT` lines, plan vs operand in `cluster/setup`, `sweep-p` |
| 2. Readings | yes | NaN trigger line: `usage … (0.50391, nan) … verdict … [True] … rc=0` |
| 3. Matched row | yes | each number reproduced by `selfcheck.txt` |
| 4. Excluded rows | yes | each cites a number in the raw files |
| 5. Observed vs. inferred | yes | (i) rests on the closed `valid` arm; it does not change the matched row |
| 6. Deviations and gaps | yes | listed as found |
| 7. Core question | yes | hypothesis B1 → setter test and ring → predictions → rows; the control moved at four ratios |

### 5.2 Run 2?

**No** (2026-10-27). Setter outcomes are exact exception texts and stored values; the cluster boundary reproduces the closed case's to the digit (percentages to two decimals) in 13 triggers; the independent re-parse agrees. The inferred statement (i) would not change with a repeat.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** (B1) The range check at `DatabaseDescriptor.java:5347` does not cap memory or disk usage: it only accepts or rejects a number, and no resource reading changes with the accepted or rejected value at this point. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row (1): **Confirmed** — rejected values throw the range text and change nothing, accepted values (incl. NaN) are stored, the control moves the real check's boundary | does not cap | run 1 + self-check | 2026-10-27 |
| Cluster | B3g row (1): **Confirmed** — sweep boundary at 0.0 · 0.2 · 0.5 · 0.8; rejected writes leave the 0.5 verdicts on both holders; NaN accepted and never refuses; yaml 1.5 unvalidated | does not cap (the downstream admission check is the soft cap) | run 1 + self-check | 2026-10-27 |

**Positive control:** the stored ratio moves the real check's verdict: unit boundary at u = 0.50000 / 0.50001 for r = 0.5 (and the closed 92 checks); cluster A admitted and B refused at `L ± 4 MiB` for r = 0.0 · 0.2 · 0.5 · 0.8, with the refusing node's own `ERROR` line.

**Feedback filed:** the case file's section D updated (amendments U1–U6, C1–C6 and these results). **Open points:** (1) `NaN` passes the range check and disables the downstream cap (`diskUsage + NaN > 1` is false); the yaml value skips the check altogether (observed with 1.5); both belong to the claim's A3 text. (2) The real-bytes overshoot arm of the closed case was not re-run. **Leftovers on `pc32`:** no `CassandraDaemon` running (checked with `ps -eo cmd | grep '[C]assandraDaemon'` on the node); node folders `~/s4b-hdr` removed; logs kept in `~/s4b-logs/hdr2/`; `~/cassandra-run4` kept for the next case.
