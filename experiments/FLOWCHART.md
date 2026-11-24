# Experiments — functionality and flowchart

*Written 2026-11-17; redesigned the same day (owner).* What `capacity-enforcement-exp` (phase 1) and
`OOM-exp` (phase 2) do and how they hand work to each other, with one flowchart. The method of each step
stays in the file each row points to; this page is the map. In prose: [`README.md`](README.md).

> **Rule ([`CLAUDE.md`](CLAUDE.md), 2026-11-17, widened 2026-11-23):** whenever a commit under `experiments/` changes
> the design (a step, agent, playbook, list, vocabulary or hand-off) **or a result number** of either experiment, update
> this page in the same commit: tables and chart plus a change-log line for design; arrow labels and §5.1 for numbers.

## 1. The two experiments

**Phase 1, [`capacity-enforcement-exp/`](capacity-enforcement-exp/README.md)** (Targets 1 + 2; Cassandra
5.0.9, Hadoop 3.4.2). It finds the **resource constraints** that are supposed to cap a node's memory or
disk and checks whether usage follows each one (stages 1–4), then reads every filed case for **clues that
could lead to OOM** and writes them as **OOM candidates** (stage 5).
[`entry-restriction-exp/`](entry-restriction-exp/README.md) is a paused phase-1 supplement.

**Phase 2, [`OOM-exp/`](OOM-exp/README.md)** (Target 3; Cassandra so far). An **OOM agent** picks
candidates (and earlier cases worth a retry), writes a case file with a design that should lead to OOM
(stage 1), then a fresh OOM-agent session runs that design and concludes **true positive**, **false
positive** or **retry** (stage 2). Every true positive is then checked read-only against Apache JIRA (stage 3-a) and
for whether an ordinary client could trigger it (stage 3-b).
Only default constraints are considered (rule 2026-11-23).

## 2. Phase 1 — functionality

| Step | What it does | Where |
|---|---|---|
| Stage 1 — CodeQL | Narrows `if` statements structurally to a worklist (no keyword list) | [`stage1-codeql-preprocessing/`](capacity-enforcement-exp/stage1-codeql-preprocessing/README.md) |
| Stage 2 — AI banding | Ranks rows A/B/C/D by name only; rules nothing out | [`stage2-ai-preprocessing/`](capacity-enforcement-exp/stage2-ai-preprocessing/README.md) |
| Stage 3 — autonomous agent | Target only, isolated source copy: traces the constraint, estimates, designs unit + cluster tiers (a non-config variant skips config-type constraints) | [`playbook-autonomous.md`](capacity-enforcement-exp/stage3-ai-deep-read/playbook-autonomous.md), [`playbook-non-config-autonomous.md`](capacity-enforcement-exp/stage3-ai-deep-read/playbook-non-config-autonomous.md) |
| Stage 3 — guided agent | Target + the three rules, enforcement patterns, test-design method | [`playbook-guided.md`](capacity-enforcement-exp/stage3-ai-deep-read/playbook-guided.md) |
| Stage 3 — verdict files | `_INDEX.md`, `predicted-negative/positive.md`, `undetermined.md` | `capacity-enforcement-exp/<system>/stage3-ai-deep-read/` |
| Stage 4 — runtime verification | Design audit, frozen predictions, runs, verdict, outcome class (TP / FP / TN / FN / undetermined); feedback amends the case file | [`stage4-runtime-verification/`](capacity-enforcement-exp/stage4-runtime-verification/README.md) |
| JIRA OOM report | Per system: analysis of the project's JIRA OOM reports (cause patterns, by-design closures); read only | [`jira-mining.md`](capacity-enforcement-exp/stage5-oom-clue-find/jira-mining.md), `<system>/stage5-oom-clue-find/jira-oom-report.md` |
| OOM clue patterns | System-agnostic `CP-<n>` patterns from the JIRA reports and phase-2 true positives | [`oom-clue-patterns.md`](capacity-enforcement-exp/stage5-oom-clue-find/oom-clue-patterns.md) |
| Stage 5 — autonomous agent | Reads one case file (+ stage-4 results), finds clues in its own words; never sees patterns, JIRA or phase 2 | [stage-5 `playbook-autonomous.md`](capacity-enforcement-exp/stage5-oom-clue-find/playbook-autonomous.md) |
| Stage 5 — guided agent | The same, checking each OOM clue pattern | [stage-5 `playbook-guided.md`](capacity-enforcement-exp/stage5-oom-clue-find/playbook-guided.md) |
| Phase 1 OOM candidate list | One row per candidate (`OC-<n>`), agent, patterns, Status written back by phase 2; plus `coverage.csv` | `<system>/stage5-oom-clue-find/phase1-oom-candidates.md` |

## 3. Phase 2 — functionality

| Step | What it does | Where |
|---|---|---|
| Stage 1 — pick and design (OOM agent) | Picks from the candidate list and the retry list (JIRA prior-art check, skips recorded); writes the case file: the phase-1 case file, a frozen design solution, conclusion `pending` | [`oom-agent-playbook.md`](OOM-exp/oom-agent-playbook.md), [`_TEMPLATE-case.md`](OOM-exp/_TEMPLATE-case.md) |
| Technique notes | Convergence (custom / default), combo, bypass: shapes for a design | [`custom-convergence`](OOM-exp/custom-convergence-playbook.md), [`default-convergence`](OOM-exp/default-convergence-playbook.md), [`combo`](OOM-exp/combo-playbook.md), [`bypass`](OOM-exp/bypass-playbook.md) |
| Stage 2 — verify (fresh OOM agent) | Runs the frozen design, records harness and runs, adds the conclusion | oom-agent playbook, [`verification-protocol.md`](OOM-exp/verification-protocol.md) |
| Verdict | **true positive** (OOM, V1–V7 met) / **false positive** (a valid design cannot reach OOM, or OOM only with a non-default constraint) / **retry** | oom-agent playbook "False positive or retry" |
| Scope rule (2026-11-23) | Default constraints only: stage 1 skips a candidate that needs a non-default constraint; budgets follow V7; control/intervention arms may change one | [`verification-protocol.md`](OOM-exp/verification-protocol.md) "Default constraints only" |
| Stage 3-a — JIRA check (fresh session, 2026-11-23) | Each true positive checked read-only against Apache JIRA: match level, issue state, fix in the pinned version, documented source; one label per case | oom-agent playbook, `OOM-exp/<system>/stage3-jira-check/` |
| Stage 3-b — client trigger check (fresh session, 2026-11-23) | Each true positive checked against a client threat model (authenticated non-admin user, native protocol only): lowest privilege, conditions outside the client's control, blast radius; optional confirm runs | oom-agent playbook, `OOM-exp/<system>/stage3b-client-trigger/` |
| Phase 2 retry list | Cases worth another try, with what a better design should change | `OOM-exp/<system>/phase2-retry-list.md` |
| Case index | Every case with its verdict, phase-1 case file, stage 3-a JIRA label and stage 3-b client label | [`OOM-exp/cassandra/cases/_INDEX.md`](OOM-exp/cassandra/cases/_INDEX.md) |

## 4. Links between the experiments

| Link | Direction | Where |
|---|---|---|
| Stage 5 writes OOM candidates; the OOM agent picks from them | phase 1 → 2 | candidate list |
| Stage 2 writes each candidate's verdict back (per-agent true-positive rate) | phase 2 → 1 | candidate list Status |
| A true positive whose shape no pattern covers becomes a new clue pattern | phase 2 → 1 | `oom-clue-patterns.md` |
| A new holder a stage-2 run revealed but did not claim becomes a candidate row (owner-approved, Agent `phase-2 (<ID>)`) | phase 2 → 1 | candidate list |
| Each phase-2 case names its phase-1 case file | phase 2 → 1 | case file §1, `_INDEX.md` |

## 5. Flowchart

Step names only; what each step does is in sections 2–4. Arrow labels carry the **current numbers** as
**Cassandra/Hadoop** (for example `295/26`), as of 2026-11-24; **–** = not started for that system. The full breakdown
with sources is in 5.1. **Node markers** (open work, details in 5.2): **orange border** = work at this step waits on an
owner decision; **dashed border** = not started for Hadoop (phase 2 is Cassandra only and is not marked). Solid arrows: the main path. Dotted arrows:
write-back and feedback. Cylinders: lists and files that one step writes and another reads.

```mermaid
flowchart TD
  classDef store fill:#e3eefc,stroke:#3a6fb0,color:#222
  classDef verdict fill:#e2f4e2,stroke:#3a8a3a,color:#222
  classDef owner stroke:#d97706,stroke-width:3px
  classDef storeOwner fill:#e3eefc,stroke:#d97706,stroke-width:3px,color:#222
  classDef hadoopPending stroke-dasharray:6 4

  subgraph P1["Phase 1: capacity-enforcement-exp"]
    S1["Stage 1: CodeQL"]
    S2["Stage 2: AI banding"]
    S3A["Stage 3: autonomous agent"]
    S3G["Stage 3: guided agent"]
    CF[("Phase-1 case files")]
    S4["Stage 4: runtime verification"]
    JR[("JIRA OOM reports")]
    CPAT[("OOM clue patterns")]
    S5A["Stage 5: autonomous agent"]
    S5G["Stage 5: guided agent"]
    CL[("Phase 1 OOM candidate list")]
  end

  subgraph P2["Phase 2: OOM-exp"]
    RL[("Phase 2 retry list")]
    O1["Stage 1: OOM agent, pick and design"]
    CASE[("Phase-2 case files")]
    O2["Stage 2: OOM agent, verify"]
    TP["True positive"]
    FP["False positive"]
    RT["Retry"]
    O3["Stage 3-a: JIRA check"]
    JC[("Stage 3-a JIRA check files")]
    O3B["Stage 3-b: client trigger check"]
    CT[("Stage 3-b client trigger files")]
  end

  S1 -->|"11,228/19,674 units"| S2
  S2 -->|"units read: 2,758/30"| S3A
  S2 -->|"targets: 29/–"| S3G
  S3A -->|"case files: 295/26"| CF
  S3G -->|"case files: 29/–"| CF
  CF -->|"run: 263/8 (of 324/26)"| S4
  S4 -.->|"TP 123/4, TN 99/3, FN 6/0"| CF
  JR -->|"issues kept: 246/368; 16 patterns"| CPAT
  CF -->|"files read: 306/2"| S5A
  CF -->|"files read: 306/2"| S5G
  CPAT --> S5G
  S5A -->|"candidates: 257/2"| CL
  S5G -->|"candidates: 269/3"| CL

  CL -->|"candidates: 590/5, open 71/5, picked 23/–"| O1
  RL -->|"retry rows: 23/–, open 0/–, picked again 3/–"| O1
  O1 --> CASE
  CASE -->|"cases: 79/–, 10 at stage 1"| O2
  O2 -->|"44/–"| TP
  O2 -->|"4/–"| FP
  O2 -->|"21/–"| RT
  RT --> RL
  O2 -.->|verdict| CL
  O2 -.->|new holder| CL
  TP -.->|new pattern| CPAT
  TP -->|"checked: 45/– (44 + R15-B)"| O3
  O3 -->|"known 21/–, fixed upstream 1/–, documented 5/–, new 18/–"| JC
  TP -->|"checked: 45/– (44 + R15-B)"| O3B
  O3B -->|"alone 32/–, conditional 12/–, admin 1/–; confirmed 20/–"| CT

  class CF,JR,CPAT,CL,RL,CASE,JC,CT store
  class S4,O2,O3,O3B owner
  class S3G hadoopPending
  class TP verdict
```

Notes on the chart:

- **Stage 5 never chases a clue** and phase-1 agents never read phase-2 results; the only phase-2 signal
  that reaches phase 1 is a new clue pattern, which only the guided agent reads.
- **Hadoop** has run phase 1 stages 1–3 (Jingsong's queue orders 1–25, Yang's first 5 rechecks), stage 4 on 8 of its 26
  case files (18 wait), its JIRA OOM report and stage 5 on the 2 case files of 2026-11-24 (5 candidates); its guided
  stage-3 agent and phase 2 are not started.

### 5.1 Results snapshot (as of 2026-11-24)

Each step is written as **in = out + … + left**, Cassandra and Hadoop separately, and every sum closes. Counts are
recomputed from the data files named (where a README or handoff states an older count, the data file wins); refreshed
in the same commit as any result change (rule in [`CLAUDE.md`](CLAUDE.md)). Paths are under
`capacity-enforcement-exp/` unless they start with `OOM-exp/` or `codeql-queries/`.

#### Phase 1 — `capacity-enforcement-exp`

**Stage 1, CodeQL: result rows → units** (`codeql-queries/results/<sys>/`, gitignored; unit ids from
`codeql-queries/scripts/make-stage2-batches.py`). Narrowed rows are one unit each; helper-guarded rows collapse to one
unit per helper; enforcement rows to one per comparison/call key, verdict rows to one per verdict method; capacity-set
rows are one unit each.

| Query | Cassandra rows → units | Hadoop rows → units |
|---|---|---|
| NarrowedIfStatements | 4,489 → 4,489 | 9,269 → 9,269 |
| HelperGuardedIfStatements | 1,099 → 300 | 1,573 → 415 |
| EnforcementPlaces, comparison or call | 4,212 → 3,482 | 4,481 → 3,677 |
| EnforcementPlaces, verdict | 1,340 → 465 | 2,251 → 1,194 |
| CapacitySetPlaces | 2,492 → 2,492 | 5,119 → 5,119 |
| **Total** (`if` corpus + extension) | **13,632 → 11,228** (4,789 + 6,439) | **22,693 → 19,674** (9,684 + 9,990) |

**Stage 2, banding** (`<sys>/stage2-ai-preprocessing/bands.csv`): units = A + B + C + D.

| | A | B | C | D | Units |
|---|---|---|---|---|---|
| Cassandra `if` corpus / extension | 134 / 90 | 174 / 124 | 94 / 307 | 4,387 / 5,918 | 4,789 / 6,439 |
| **Cassandra** | 224 | 298 | 401 | 10,305 | **11,228** |
| Hadoop `if` corpus / extension | 90 / 110 | 170 / 272 | 489 / 615 | 8,935 / 8,993 | 9,684 / 9,990 |
| **Hadoop** | 200 | 442 | 1,104 | 17,928 | **19,674** |

**Stage 3, deep read — units** (Cassandra: `cassandra/stage3-ai-deep-read/` set CSVs, band-D progress CSVs,
`band-d-noncfg-processed.md`; Hadoop: `hadoop/status.py`, the two `queue.csv`).

- **Cassandra: 11,228 = read 2,758 + already a case target, not re-read 13 + queued, not read 2,539 + not queued 5,918.**
  - read 2,758 = `if` A–C 402 (pre-existing targets 65, set A 168, set B 169) + band-D set B 2,193 + band-D set A helpers
    30 + extension orders 1–134 except the existing case at 75, 133;
  - read 2,758 = became a case target **373** (65 + 163 + 27 + 88 + 30) + judged not a case **2,385** (set A config-type skips
    5, set B judged without write-up 169, band-D helpers 3, band-D set B refused 2,105, extension covered 103);
  - extension 133 = band A batch 1 (orders 1–53: 10 written up + 43 covered) + batch 1 of 2026-11-24 (orders 54–134 less
    75: 20 written up + 60 covered);
  - not re-read 13 = 6 extension anchors (not in `writeup-set-ext.csv`) + 7 extension rows already a case target;
  - queued, not read 2,539 = band-D set A 2,164 + extension A–C 375 (orders 135 on); not queued = extension band D 5,918.
- **Hadoop: 19,674 = read 30 + queued, not read 10,651 (Yang 8,930, Jingsong 1,721) + not queued 8,993** (extension band D).
  Read 30 = became a case 26 (Yang 1, Jingsong 25: queue orders 1–25) + not a case 4 (Yang's rechecks that stayed in band D).

**Stage 3 — case files** (`<sys>/stage3-ai-deep-read/_INDEX.md` §1; §2's "58" is stale).

| Cassandra source | Files | Guided | Positive / negative / undetermined |
|---|---|---|---|
| Before the two-set job (2026-10-22) | 58 | 29 | 42 / 16 / 0 |
| Set A, autonomous write-ups | 125 | 0 | 22 / 103 / 0 |
| Set A, non-config agent | 27 | 0 | 13 / 14 / 0 |
| Band-D set A helpers, non-config job | 27 | 0 | 0 / 27 / 0 |
| Band-D set B, advisor run | 57 | 0 | 50 / 0 / 7 |
| Extension, band A batch 1 | 10 | 0 | 10 / 0 / 0 |
| Extension, batch 1 of 2026-11-24 (orders 54–134) | 20 | 0 | 13 / 7 / 0 |
| **Total** | **324** (autonomous 295 + guided 29) | **29** | **150 / 167 / 7** |

Hadoop: **26** case files = autonomous 26 = positive 18 + negative 8 (Yang 1 negative; Jingsong 25 = batch of 2026-11-06
3 + 2, batch of 2026-11-24 15 + 5).

**Stage 4, runtime verification** (`_INDEX.md` outcome column, `stage4-runtime-verification/results/`).

- **Cassandra: 324 = run 263 + not run 61.**
  - run 263 = TP 123 + FP 0 + TN 99 + FN 6 + undetermined 16 + weak 19 (TP 6, TN 12, FN 1);
  - not run 61 = `none`-type cases awaiting the owner's decision 29 + cases with a constraint type but no stage-4 run
    recorded 14 + waiting 18 (extension batch of 2026-11-24, run interrupted by an API usage limit; 2 of its 20 finished).
- **Hadoop: 26 = run 8 + waiting 18**; run 8 = TP 4 + TN 3 + undetermined 1; waiting 18 = Jingsong's batch of 2026-11-24
  (orders 6–25 less 19 and 21, which finished; run interrupted by the same usage limit).

**JIRA OOM report** (`<sys>/stage5-oom-clue-find/jira-oom-survey.csv`).

- **Cassandra: 604 = kept 246 + excluded 358**; kept 246 = Fixed 120 + open 45 + by design or invalid 45 + duplicate or
  cannot reproduce 36.
- **Hadoop: 961 = kept 368 + excluded 593**; kept 368 = Fixed 201 + unresolved 97 + by design or invalid 35 + duplicate or
  cannot reproduce 35.

**OOM clue patterns** (`stage5-oom-clue-find/oom-clue-patterns.md`): **16** = from Cassandra's report only 13 (CP-1–7,
9–14) + from Hadoop's only 2 (CP-15, CP-16) + from both 1 (CP-8) + added by phase 2 0.

**Stage 5, clue find** (`<sys>/stage5-oom-clue-find/coverage.csv`, `phase1-oom-candidates.md`).

- **Cassandra:** case files read 306 of 324 by each agent (coverage.csv has 613 rows = 306 + 306 + 1 placeholder row; the
  18 waiting for stage 4 are not read yet); files with at least one candidate: autonomous 183, guided 197.
- **Candidates 590** (OC-1–590), agent × Status:

| Agent \ Status | Open | Picked (phase-2 stage 1) | True positive | Covered | Retry | Skipped | Total |
|---|---|---|---|---|---|---|---|
| Autonomous | 21 | 12 | 30 | 124 | 0 | 70 | 257 |
| Guided | 33 | 7 | 21 | 121 | 2 | 85 | 269 |
| Legacy (migrated lists) | 17 | 2 | 25 | 5 | 1 | 12 | 62 |
| Phase-2 | 0 | 2 | 0 | 0 | 0 | 0 | 2 |
| **Total** | **71** | **23** | **76** | **250** | **3** | **167** | **590** |

  Covered 250 = by a true positive 216 + by a retry later re-tested as a true positive 16 (B14 → R13 7, B18 → R21 4,
  B11 → R12 2, U6 → R15 2, U5 → R14 1) + by a retry still retry 9 (B7 6, R8 3) + by a false positive 9 (B1 6, C3 3).
  Skipped 167 (triage lists of 2026-11-18 and 2026-11-20 closed, 2026-11-24) = needs a non-default constraint 82 + disk-only
  or too slow 33 + duplicate of a case 31 + needs corrupt input 9 + overshoot of one item already capped 6 + small 4 + a
  caveat, not a memory mechanism 2. Picked 23 = B27 12 + B25 2 + B26 2 + B29 2 + R24 2 + B28 1 + U16 1 + U17 1.
- **Hadoop:** case files read 2 of 26 by each agent (`dfs.qjournal.queued-edits.limit.mb`, `CachePoolInfo_limit`; not read
  24 = waiting for stage 4 18 + the 6 of 2026-11-06); files with at least one candidate: autonomous 1, guided 2.
  **Candidates 5** (`hadoop:OC-1`–`OC-5`) = autonomous 2 + guided 3, all open.

#### Phase 2 — `OOM-exp` (Cassandra; Hadoop not started)

**Inputs:** candidates 590 (open 71, picked 23, above). **Retry list** (`OOM-exp/cassandra/phase2-retry-list.md`): **23
rows = closed 20 + picked again 3 + open 0**; picked again 3 = B8 → R23 (a true positive re-opened for a deployment-level
OOM), B22 → R24, R19 → R25 (2026-11-24). Closed 20 = re-tried → true positive 8 + re-tried → retry again 6 + re-tried →
split (U6 → R15) 1 + covered by the default re-tests (R2–R4) 3 + C3 false positive 1 + disk-paused skip 1.

**Stages 1–2, verdicts** (`OOM-exp/cassandra/cases/_INDEX.md`; verdicts matched with and without bold).

- **Case files 79 = verified 69 + at stage 1 (conclusion pending) 10.** The 10 are the owner-approved batch of 2026-11-24
  (case folders under `OOM-exp/cassandra/cases/`, not yet rows of `_INDEX.md`): from the candidate list 7 (B25, B26, B27,
  B28, B29, U16, U17) + from the retry list 3 (R23, R24, R25).
- **Index rows 74 = history rows 5 + cases 69.** History → successor: R1 → R1-V, R6 → R6-V, C1 run 3 / reopen /
  multiplicity → C1 run 4.
- **Verified cases 69 = true positive 44 + false positive 4 + retry 21** (R15 counted as retry: its condition A is a retry, its
  condition B a true positive).
  - true positive 44 = `deployment` 42 + `diagnostic` 2 (C1, B8);
  - false positive 4 = R6-V, C3, R9, B1;
  - retry 21 = re-tried → true positive 8 (U1 → R7, B11 → R12, B14 → R13, U5 → R14, R10 → R18, R16 → R21, R15-A → R20,
    R17 → R22) + re-tried → retry again 6 + re-tried → split 1 (U6 → R15) + covered by the default re-tests 3 (R2–R4) +
    disk-paused skip 1 + **re-picked, at stage 1 2** (R19 → R25, B22 → R24).

**Stage 3-a, JIRA check** (`OOM-exp/cassandra/stage3-jira-check/`).

- **Checked 45 = true positives 44 + R15-B** (R15's condition B; R15 counts as a retry). 30 on 2026-11-23 + 15 on
  2026-11-24 (B9, B10, B12, B13, B15, C4–C8, U2–U4, R7, R15-B; missed on 2026-11-23 by a counting error).
- **Checked 45 = known-open 13 + known-fixed (not in 5.0.9) 5 (U10, B20, R21, U2, U4) + known-fixed (incomplete) 4 (B8, B10,
  B15, C7) + documented only 5 (R1-V, R18, U12, C4, U3) + new 18.** Mentioned in JIRA (exact or partial match) = 21 (exact
  10 + partial 11); not mentioned but fixed incidentally 1 (R21). Chart: known 21 + fixed upstream 1 + documented 5 + new 18.

**Stage 3-b, client trigger** (`OOM-exp/cassandra/stage3b-client-trigger/`).

- **Checked 45** (as 3-a: 30 on 2026-11-23, 15 on 2026-11-24 by analysis only).
- **Checked 45 = user alone 32 + given an outside condition 12 + admin only 1** (R18).
  - alone 32 = pre-auth 2 (B19, U2) + login role without grants 3 (R13, R20, R15-B) + data role 20 + DDL role 7 (C9, U8,
    B20, U14, C4, C6, C8);
  - outside condition 12 = a node or replica event 5 (B23, B6, B8, B15, C5) + a small node or an operator memory budget
    below the resolved one 6 (C1, S1, U13, R1-V, R7, B9) + an operator-run repair 1 (C7).
- **Confirm runs: 45 = run 23 + not run 22; run 23 = confirmed 20 + partly 3** (R13, U7, U14); not run 22 = judged low
  value on 2026-11-23 7 + analysed 2026-11-24 15 (recommended 10, low priority 1 (U2), not worthwhile 4 (B15, C5, C7,
  R7)).

### 5.2 Open work (as of 2026-11-24)

What is left at each step, from the "+ left" terms of 5.1 and the open items in the handoffs. Numbers are
**Cassandra/Hadoop** where both apply. **Waiting on**: **owner** = a decision only the owner can make (orange border in
the chart); **queue** = ordinary work for whoever runs that queue; **node** = a broken node or environment. Refreshed with
5.1 (rule in [`CLAUDE.md`](CLAUDE.md)).

**Phase 1 — `capacity-enforcement-exp`**

| Step | What is left | Waiting on | Tracked in |
|---|---|---|---|
| Stage 1 — CodeQL | nothing; optional: numeric `switch` case labels are not matched | — | `stage1-codeql-preprocessing/README.md` |
| Stage 2 — banding | nothing | — | `bands.csv` |
| Stage 3 — deep read | queued, not read **2,539/10,651** (C: band-D set A 2,164, extension A–C 375 from order 135; H: Yang 8,930, Jingsong 1,721 from order 26); not queued **5,918/8,993** (extension band D); judged but not written up 169/– (set B); unresolved unit 1/–; notes backlog (stage-3 notes not applied to filed cases, `undetermined.md` §2 re-audit, `predicted-negative.md` §10 band-D lines); filer's calls of 2026-11-24 open to overrule (Cassandra extension: orders 100, 125 counted new, 70 and 122 typed `not-a-case`, builder/JMX arguments typed `query parameter`) | **queue** (Jingsong: band-D set A, extension, Hadoop queue; Yang: set B write-ups, Hadoop queue); **owner**: whether to queue extension band D; the 2026-11-24 filer's calls | set CSVs, `hadoop/<name>/queue.csv`, `HANDOFF.md` "Open follow-ups", `HANDOFF-Jingsong.md` 2026-11-24 |
| Stage 4 — runtime verification | not run **61/18**: C 29 `none`-type + 14 with no run recorded + **18 waiting** (extension batch 1 of 2026-11-24), H **18 waiting** (Jingsong's orders 6–25 less 19 and 21); the 36 waiting runs were **interrupted at ≈ 02:30 on 2026-11-24 by an API usage limit**, and 8 of them (C 57, 72, 115, 117, 120; H 9, 11, 13) carry dated audit amendments of the interrupted run; undetermined **16/1** (rerun list in the handoff) | **owner**: the `none`-type design (29 cases); clean-up of the 10 nodes (Nodes row below); **node**: the 10 nodes are reserved for OOM-exp from 05:00 on 2026-11-24; **queue**: the 36 waiting cases once the nodes are free and clean, reruns | `_INDEX.md` §1 (both systems), `HANDOFF-Jingsong.md` 2026-11-24, `HANDOFF.md` |
| JIRA OOM report | nothing | — | `jira-oom-report.md` |
| OOM clue patterns | nothing | — | `oom-clue-patterns.md` |
| Stage 5 — clue find | case files not yet read **18/24** (C: the 18 waiting for stage 4; H: the 18 waiting + the 6 of 2026-11-06) | **queue** (after stage 4 for the waiting cases) | `coverage.csv` |
| Candidate list | open **71/5**; picked, at phase-2 stage 1 23/–; the 2026-11-18 / 2026-11-20 triage lists and B18's rows are closed (2026-11-24) | **queue** (OOM agent picks) | `phase1-oom-candidates.md` |

**Phase 2 — `OOM-exp`** (Cassandra; Hadoop not started)

| Step | What is left | Waiting on | Tracked in |
|---|---|---|---|
| Stages 1–2 — design, verify | **new batch of 2026-11-24 at stage 1: 10 cases** (B25, B26, B27, B28, B29, U16, U17 from the candidate list; R23 ← B8, R24 ← B22, R25 ← R19 from the retry list), conclusion pending, not yet rows of `_INDEX.md`; open retries **0**; owner rulings **5** (B19 T2's form, B21 failed I-2G intervention, U13 deployment vs diagnostic, U15 "not corrupt input", B15 proposed status); optional follow-ups 4 (R21 unclaimed lead, R22 512 MiB service-loss arm, R20 2 GiB matched set, B6 status caveat) | **queue**: stage 2 of the 10 (nodes reserved for OOM-exp from 05:00); **owner**: the 5 rulings; **queue**: follow-ups | `cases/<case>/` (the 10), `cassandra/phase2-retry-list.md`, `cases/_INDEX.md`, `HANDOFF.md` waves |
| Stage 3-a — JIRA check | true positives not checked **0**; not ruled: C9, R1-V labels (as filed); flagged for the owner on 2026-11-24: B10 (`new` if CASSANDRA-20052 is rated related), C7 (by design or known-open), C8 (CASSANDRA-20752 borderline partial), U4 (opt-in fix as known-fixed) | **owner**: the 4 flags; **queue** | `stage3-jira-check/README.md` |
| Stage 3-b — client trigger | true positives not analysed **0**; confirm runs not run for the 15 of 2026-11-24 (recommended: B9 (needed: pre-auth by code reading), B10, B12, B13, C4, C6, C8, U3, U4, R15-B; low priority: U2); confirm: U14 one more run (OOM 1 of 2), repetition across nodes (all cases), B21 ring-wide fan-out, B20/U14 cluster-wide reach; 7 cases of 2026-11-23 not confirm-run (low value) | **owner**: approve confirm runs (as for the 23); **queue** | `stage3b-client-trigger/README.md` |
| Nodes (both experiments) | **stale locks and orphaned processes left at ≈ 02:30 on 2026-11-24 on the 10 nodes** (`pc91`, `pc82`, `pc72`, `pc75`, `pc99`; `ms0625`, `ms0640`, `ms0604`, `ms0611`, `ms0617`) when both stage-4 batches stopped: e.g. case 11's NameNode and DataNode still running on `pc82`, partial run folders on `pc91`, `pc82`, `pc99` (`/mydata/jingsong-s4/…-run1`, 1.7–5.5 GB) and possibly `/mydata/jingsong-cass-s4/o<order>/` on the m400s; wave-6 run folders on all 10 nodes (`/mydata/s4/<case>`, 0.6–6 GB each; heap dumps 2.2 GB on `pc75`, 2.4 GB on `pc99`) | **owner**: clean up (stop, unlock) before the nodes are used again; delete or keep the wave-6 folders | `HANDOFF-Jingsong.md` 2026-11-24, `HANDOFF.md` wave 6 and "Nodes" |

## 6. Change log of this page

| Date | Change |
|---|---|
| 2026-11-17 | Written: both experiments, linking functionality through the 2026-11-17 rulings (agent queues rows, autonomous OOM leads, recheck sweep, back-link updates the guided agent, lead-list status, rescan claims) |
| 2026-11-17 | Flowchart reduced to step names; descriptions stay in sections 2–4 (owner) |
| 2026-11-17 | **Redesign (owner):** the 2026-11-16/17 linking machinery and phase 2's lead sources removed; phase 1 gains stage 5 (OOM clue find: JIRA OOM reports → clue patterns; autonomous and guided agents → candidate list); phase 2 becomes the OOM agent's two stages with true positive / false positive / retry and a retry list; data-flow tracing dropped |
| 2026-11-18 | Candidate list status vocabulary gains `closed: covered by <case ID> (<verdict>)` (owner); no step or arrow changed |
| 2026-11-20 | New lead source (owner): stage 2 may propose a holder its runs revealed but did not claim; with approval it becomes a candidate row with Agent `phase-2 (<case ID>)` (first: OC-578 from R12). §4 row and a dotted `new holder` arrow O2 → CL added |
| 2026-11-23 | Phase 2 gains **stage 3, JIRA check** (owner): every true positive checked read-only against Apache JIRA; new chart nodes O3 and JC; case index gains a JIRA column. Scope rule (owner): default constraints only, an OOM needing a non-default constraint is a false positive and stage 1 skips such candidates (verdict row and new scope row) |
| 2026-11-23 | Stage 3 split (owner): the JIRA check becomes **3-a**; new **3-b, client trigger check** (could an ordinary authenticated user trigger the OOM and affect other users); chart nodes O3B and CT; case index gains a Client column |
| 2026-11-23 | Stage 3-b privilege levels gain `login role, no grants` (between pre-auth and data role), from the confirm runs; no step or arrow changed |
| 2026-11-23 | Result numbers added (owner): arrow labels in the chart and a results snapshot (5.1) for both phases, refreshed with each batch's results; Hadoop note corrected (its JIRA report exists, stage 5 not started) |
| 2026-11-23 | Arrow-label format (owner): numbers written as Cassandra/Hadoop with a legend, – = not started; phase-2 counts corrected (44 true positives, not 30; stage 3 covered 30 of them) |
| 2026-11-23 | Rule widened (owner): result-number changes in either experiment also update this page in the same commit; pointers added to the root `CLAUDE.md` batch-commit step and Hadoop `PROCEDURE.md` |
| 2026-11-23 | §5.1 rewritten as splits that close (owner): each step as in = out + … + left, per system; corrections: phase-2 cases 69, open retries 2, Cassandra units read 2,678, pattern origins 13 + 2 + 1 |
| 2026-11-24 | Open work shown (owner): new §5.2 (what is left per step, waiting on owner / queue / node) and node markers in the chart (orange border = waits on an owner decision; dashed = not started for Hadoop) |
