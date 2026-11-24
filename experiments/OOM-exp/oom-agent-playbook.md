# OOM agent playbook — phase 2, stages 1, 2, 3-a and 3-b

*Written 2026-11-17 (owner's redesign).* Phase 2 has one agent role, the **OOM agent**, and two stages.
Stage 1 picks a candidate and writes its case file with a design that should lead to OOM; stage 2
follows that design on real nodes and adds the conclusion. Every picked candidate is treated as
**estimated positive** (it will OOM) after stage 1, so stage 2's conclusion is one of three verdicts:

| Verdict | Meaning |
|---|---|
| **true positive** | it leads to OOM: the verification protocol's V1–V7 hold (status `verified-OOM`) |
| **false positive** | it does not lead to OOM: a valid run of the design reached its target load, and the measurements show the endpoint cannot be reached at defaults and an acceptable budget (see "False positive or retry") |
| **retry** | no final conclusion: worth another try with a better design. The case goes to the retry list |

*Stage 3 added 2026-11-23 (owner):* every **true positive** then gets two checks: **3-a, JIRA check** (read only: is the
verified mechanism already reported in the system's Apache JIRA, and in what state) and **3-b, client trigger check**
(could an ordinary user, not an admin or developer, trigger the OOM and so affect other users).

Evidence rules, measurement, budgets and statuses are in [`verification-protocol.md`](verification-protocol.md);
this playbook does not restate them. The protocol's finer statuses stay in the case file as detail
(`verified-gap`, `reproduced-OOM`, `candidate`, `negative`, with `deployment` / `diagnostic`); the verdict
is what counts.

## Inputs

1. **The phase 1 OOM candidate list**, per system:
   `../capacity-enforcement-exp/<system>/stage5-oom-clue-find/phase1-oom-candidates.md`, rows with Status `open`.
2. **The phase 2 retry list**, per system: [`<system>/phase2-retry-list.md`](cassandra/phase2-retry-list.md),
   rows with Status `open`.

Nothing else is a lead source (JIRA OOM history and data-flow tracing were retired as phase-2 sources
on 2026-11-17; JIRA now feeds phase 1's clue patterns).

## Stage 1 — pick and design

1. **Pick.** Read the open rows of both lists. Prefer a candidate that is reachable at shipped defaults,
   names a concrete holder, and whose rough size can reach a deployment budget; prefer a retry whose
   "what to change" is concrete. Before picking, check JIRA for prior art (read only; nothing is posted
   to JIRA or reported upstream): a known-fixed bug is picked only as a positive control. For each row
   you pass over on purpose, write `skipped: <reason>` in its Status (disk-only, needs corrupt input,
   needs non-default constraint (rule 2026-11-23),
   overshoot of one item already capped, small heap-derived cap, duplicate). Rows you simply did not get
   to stay `open`.
2. **Mark it.** Candidate list: Status `picked: <case ID>`. Retry list: Status `picked again: <case ID>`.
3. **Case ID and folder.** The direction prefix of the design (README "ID prefixes": C convergence, B
   bypass, U unprotected accumulation, S stacked combo, R a new attempt at an earlier case with
   `-V` for the re-test at defaults), next free number. Case folder:
   `<system>/cases/<constraint or holder>--<short mechanism>/` (flat; the verdict lives in `_INDEX.md`, not
   in the folder; cases filed before 2026-11-17 stay in their old `convergence/`, `bypass/`,
   `candidates/`, `negatives/` folders); the case file has the same stem.
4. **Write the case file** from [`_TEMPLATE-case.md`](_TEMPLATE-case.md):
   - **§1 Candidate:** its `OC-` or retry row, quoted; the **corresponding phase-1 case file** (link) or
     `none`; the phase-1 stage-4 result if any; JIRA prior art.
   - **§2 Design solution:** the mechanism, the protection map, the configuration and budget audit, the
     workload, instruments, predicted response, stopping budget, controls and intervention, as the
     protocol requires. Use the technique notes (below) for the shape. Freeze it: record the sha256 of §1–§2
     in §2's last line. Stage 2 runs this design; a change after the freeze is a dated amendment with
     its reason.
   - **§3 Runs** and **§4 Conclusion:** `pending`.
5. Stage 1 ends there. It does not run anything.

## Stage 2 — verify

Run by a **fresh** OOM-agent session (not the one that wrote the design), so the design cannot drift to
fit the readings.

1. Read the case file; check the freeze hash; check the nodes (root `HANDOFF.md`, "Nodes and access")
   and what runs on them.
2. Build the harness under `<case folder>/harness/` (scripts, configs, workload drivers), run the design,
   keep logs on the node and small excerpts in `<case folder>/logs/`. Follow the protocol's design and
   execution rules (repetitions, matched controls, intervention, initiating failure, budgets).
3. Fill **§3 Runs**: environment, every run with its readings, deviations from the design.
4. Fill **§4 Conclusion**: the verdict, the protocol status as detail, the one-paragraph reason, and for
   `retry` what a better design should change.
5. **Write back:**
   - the candidate list row (or the retry row): `true positive (<ID>)`, `false positive (<ID>)` or
     `retry (<ID>)`;
   - for `retry`, add a row to the retry list;
   - update the case's row in [`<system>/cases/_INDEX.md`](cassandra/cases/_INDEX.md) (Verdict column);
   - for a new holder the runs revealed but the design did not claim (for example one that dominates some dumps),
     propose it to the owner; with approval it becomes a candidate-list row with Agent `phase-2 (<case ID>)`
     (added 2026-11-20, owner);
   - for a `true positive` whose shape no clue pattern covers, add a pattern to
     `../capacity-enforcement-exp/stage5-oom-clue-find/oom-clue-patterns.md` with source
     `phase 2: <case ID>` and the date.
6. Stop every process the run started and say what is left on the nodes.

## Stage 3-a — JIRA check

*Called stage 3 until 2026-11-23; results stay in `<system>/stage3-jira-check/`.*

*Added 2026-11-23 (owner).* Input: every case whose verdict is **true positive** (false positives and retries are not
checked). Run by a **fresh** session that did not design or verify the case. **Read only**: nothing is posted, commented or
voted on in JIRA, and nothing is reported upstream (README, owner 2026-11-17).

1. **What is checked.** The case's verified mechanism as stated in its §4 (holder, trigger, the control that fails or is
   missing), not the phase-1 clue wording. Read the case file's Summary, §1 (stage 1's JIRA prior art) and §4.
2. **Search (reproducible).** The system's JIRA REST API (`https://issues.apache.org/jira/rest/api/2/search`, Cassandra:
   `project = CASSANDRA`; Hadoop: `project in (HADOOP, HDFS, YARN, MAPREDUCE)`), requests ≥ 2 s apart. Search by
   - code identifiers: class, method, field and config names on the path (`text ~ "…"`);
   - symptom: `OutOfMemoryError` / OOM / heap / direct memory together with the component;
   - links: read the closest issues in full (`/rest/api/2/issue/<KEY>?fields=summary,description,comment,resolution,fixVersions,issuelinks,status,created,updated`)
     and follow their issue links and duplicates.
   Log **every JQL query with its hit count** and the snapshot date in the case's stage-3 file.
3. **Match level** of the closest issue(s):

   | Level | Meaning | Counts as "mentioned" |
   |---|---|---|
   | **exact** | same holder and same trigger (or the same root cause that the trigger exercises) | yes |
   | **partial** | same holder with a different trigger, or the OOM symptom reported with this holder but no root cause | yes |
   | **related** | same component or control only; a different holder or root cause | no |
   | **none** | nothing on point | no |

4. **Issue state** of each exact/partial issue: `open` (unresolved, any workflow state), `won't fix`, `by design` (closed
   as intended behaviour, not a problem, invalid), `duplicate` (follow to the target), `cannot reproduce`, or `fixed`.
   For `fixed`, read the fix commit(s) in the history clone and test `git merge-base --is-ancestor <fix> <pinned tag>`
   (Cassandra: `cassandra-5.0.9`):
   - fix **not** in the pinned version → **fixed upstream, not in <pinned version>** (name the fix versions);
   - fix **in** the pinned version → **regression** (the mechanism came back) or the case's root cause is wrong: say which.
   - fix in the pinned version that does **not cover** the mechanism (for example it bounds a different unit) → **known-fixed
     (incomplete)** (owner, 2026-11-23);
   - a fix in a newer version counts as **known-fixed** even when its issue does not describe the mechanism (fixed
     incidentally); the match level still records what the issue reports (owner, 2026-11-23).
   - an **opt-in** fix (a new setting or mode that must be enabled) counts as a fix: the same rules apply (owner,
     2026-11-24; first applied to U4).
5. **Documented.** Check whether the shipped docs warn about the behaviour (Cassandra: `conf/cassandra.yaml`,
   `conf/cassandra-env.sh`, `conf/jvm*-server.options`, `NEWS.txt`, `CHANGES.txt`, `doc/`, at the pinned source).
   If so, the case is also **documented**, with the **source labelled** (file and line, and the quoted sentence).
6. **Case label** (one): `known-open`, `known-fixed (not in <pinned>)`, `known-fixed (incomplete)`, `known-wontfix / by design`, `regression`,
   `documented only` (no issue, but the docs warn), or `new` (no exact or partial issue and no doc). Add the match level
   and the issue key(s), for example `known-open (exact: CASSANDRA-11082)`.
7. **Write back:** the case's stage-3 file `<system>/stage3-jira-check/<case ID>.md` (mechanism checked, queries and hits,
   closest issues table with match level, state and fix-in-pinned result, documented source, label, one-paragraph
   reason, snapshot date); the case's `_INDEX.md` **JIRA (stage 3-a)** cell; and the counts in
   `<system>/stage3-jira-check/README.md` (true positives checked; mentioned = exact + partial, split by state; new;
   documented).

## Stage 3-b — client trigger check

*Added 2026-11-23 (owner).* Input: every **true positive** (as 3-a). Question: could a **client** — a Cassandra user, not
an admin or developer — trigger this OOM, so that a malicious user takes down the node(s) and affects other users? Run by a
**fresh** session that did not design or verify the case. Two parts: **3-b analysis** (every case, from the case file and
the code) and **3-b confirm** (optional, on nodes, for `client-triggerable` cases, on the owner's word). Nothing is reported
upstream (README).

1. **Threat model.**
   - **Authentication on:** `PasswordAuthenticator` + `CassandraAuthorizer` (security settings, not capacity constraints;
     5.0.9 ships `AllowAllAuthenticator`, under which anyone who reaches the native port is effectively a superuser —
     record that as the default exposure). All capacity constraints at their defaults (scope rule).
   - **Interface:** the native CQL protocol only, through any client: drivers, cqlsh, or hand-crafted protocol frames.
     Any number of connections and any request rate (connection limits and rate limiting ship off). **Not** a client:
     internode ports, JMX/nodetool, sstableloader, the config or data files.
   - **Privilege levels** (lowest that triggers counts):
     - **pre-auth** — network access to the native port only; the OOM is reached before or during authentication;
     - **login role, no grants** — any authenticated role, no permission at all (added 2026-11-23 from R13/R20's confirm runs);
     - **data role** — SELECT/MODIFY on tables someone else created (schema as an admin made it);
     - **DDL role** — may create its own keyspaces/tables/indexes/types (a shared, multi-tenant cluster);
     - **admin only** — needs superuser, JMX/nodetool, a config change or file access: not client-triggerable.
2. **Conditions outside the client's control.** Some cases need an operator-side or environmental condition (a replica
   down, a restart with commit-log replay, a flush or compaction stall, a compaction backlog). Classify **reach** as:
   - **alone** — the client's own requests (and schema, at DDL role) are enough;
   - **given <condition>** — name the condition and how common it is in operation (routine, occasional, rare);
   - **not client-triggerable** — a step no client can take (or admin only).
3. **Blast radius ("affects other users").** Which node dies (the coordinator the attacker connects to; replicas it can
   steer to by choosing keys; any node), whether the attacker can repeat it across nodes to take down a replica set or the
   cluster, and what other tenants see (unavailable or timed-out requests at their consistency level, lost hints, restart
   time). Note anything an operator could see beforehand or use to attribute it (warnings, guardrail logs, audit).
4. **Each step of the verified test arm** is checked against the threat model: schema (who must create it), data (can the
   client write it), requests (protocol, consistency level, concurrency), environment (topology, faults, budgets), and
   any diagnostic aid (the step a client cannot take is named). Budgets follow V7 as in stage 2.
5. **Label** (one): `client-triggerable · <privilege>` (alone), `client-triggerable given <condition> · <privilege>`, or
   `not client-triggerable (<the step>)`. Add the blast radius in a few words, e.g. `client-triggerable · data role;
   coordinator, repeatable on every node`.
6. **3-b confirm (optional).** Re-run the verified test arm with authentication on, as a non-superuser role holding only
   the labelled privilege, plus a second **victim** client on another role measuring its own success rate and latency.
   Same rules as stage 2 (one victim node at a time, defaults, budgets per V7, everything stopped after). A confirmed
   label is marked `(confirmed)`.
7. **Write back:** `<system>/stage3b-client-trigger/<case ID>.md` (threat-model walk of every step, label, privilege,
   condition, blast radius, the code lines that decide, confirm-run evidence if any); the case's `_INDEX.md` **Client
   (stage 3-b)** cell; counts in `<system>/stage3b-client-trigger/README.md` (by privilege and reach; blast radius).

## False positive or retry

A run that does not reach OOM is a **false positive** only when all of these hold; otherwise it is a
**retry**:

- the design ran as frozen (or with recorded amendments) and reached its target load or multiplicity;
- the claimed holder was measured (U independent of K) and its growth stopped below the budget, or the
  ceiling arithmetic at defaults (sum of every contract capacity plus baseline) cannot reach an acceptable
  budget;
- no realistic fault, multiplicity or overlap named in the design is left untried.

A gap without OOM (`verified-gap`: an overshoot, a leak or service loss) and an OOM only with a tightened
budget (`reproduced-OOM`) are **retry**: the mechanism is real but the design has not reached OOM at
defaults. **Default constraints only (owner, 2026-11-23):** an OOM reached only with a constraint changed from
its default in the test arm is a **false positive**, not a retry; OOM-exp does not consider such cases
([`verification-protocol.md`](verification-protocol.md), "Default constraints only").

## The phase 2 retry list format

`<system>/phase2-retry-list.md`:

```
| Case | Verdict date | Why retry (what was shown, what was missing) | What a better design should change | Status |
|---|---|---|---|---|
| B7 | 2026-11-12 | weighers hold 2.14× / 1.80× their caps (verified-gap), no OOM at defaults 0/3 | stack with another heap pool at 2 GiB; more distinct keys | open |
```

Status: `open` → `picked again: <new case ID>` → closed by that case's verdict.

## Technique notes

The earlier direction playbooks are kept as notes on how to shape a design in §2:
[`custom-convergence-playbook.md`](custom-convergence-playbook.md),
[`default-convergence-playbook.md`](default-convergence-playbook.md), [`combo-playbook.md`](combo-playbook.md)
(multiplicity → stack → accounting gap), [`bypass-playbook.md`](bypass-playbook.md). Their own "pick" and
"queue" steps are superseded by stage 1 above.
