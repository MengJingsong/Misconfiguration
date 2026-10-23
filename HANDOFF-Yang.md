# If-Check Exp — Handoff for Yang (set B)

Created 2026-10-23; made self-contained the same day (the shared parts of
[`HANDOFF.md`](HANDOFF.md) as of `be9f005` are copied in below). Read this file, then
[`cassandra/if-check-exp/README.md`](cassandra/if-check-exp/README.md) for the full format spec.
Jingsong works on set A in parallel ([`HANDOFF-Jingsong.md`](HANDOFF-Jingsong.md)).

> **Handoff-notes rule (2026-10-23):** a session that starts from this file records **all**
> handoff notes (progress, decisions, lessons, node state, follow-ups) **here**, in
> `HANDOFF-Yang.md` — not in `HANDOFF.md`. `HANDOFF.md` is Jingsong's shared file; leave it alone
> unless asked.

**Project context:** the three project-wide targets are in the repo-root [`README.md`](README.md) §0.
The running plan and findings live in two Google Docs —
[*Meeting Summary*](https://docs.google.com/document/d/1tldFFEk28qtQD0QdsnC2Br-BisTyOUp8OCwG1SZ_6Jk/edit)
and [*Progress Report*](https://docs.google.com/document/d/1gMRFwaTvgahSiRi10ad_Y3CLDkxyF1QTYkAhZ4be4x8/edit).
The paused sibling experiment has its own brief at
[`cassandra/entry-restriction-exp/HANDOFF.md`](cassandra/entry-restriction-exp/HANDOFF.md) (do not
cross-reference it).

## Progress

| | Targets | Written up | Stage 4 closed |
|---|---|---|---|
| Set B | 161 | 0 | 0 |

## The job

Use **fresh autonomous agents** to write up a case file for every target in **set B**, then
verify each case at **stage 4** (audit, run 1 at both tiers, results file, outcome class).

- **The list:** [`cassandra/if-check-exp/stage3-ai-deep-read/writeup-set-B.csv`](cassandra/if-check-exp/stage3-ai-deep-read/writeup-set-B.csv) —
  **161 targets covering 169 stage-2 units** (band A 45, B 92, C 32). Mostly `io/`, `net/`,
  `repair/`, `service/`, `streaming/`, `transport/`, `utils/` and the rest of `index/` (from
  `index/sai/disk/v1/vector/` on), plus a few lines elsewhere tied to the same queue rows.
- **Where the list came from (2026-10-23):** the 402 band A/B/C units of
  `stage2-ai-preprocessing/bands.csv`, minus the 65 that are already the target of a case file
  (a guided file's **Capacity check** or an autonomous file's **Entry pointer**), leaves **337**.
  They were split into two sets of near-equal size by source area, keeping every unit of one
  source file and every unit of one `predicted-negative.md` row in the same set, so siblings are
  written up by one person. Set A has 168 units / 159 targets.
- **A target** is one `file:line` (units on the same line, `#1`/`#2`, are merged) or one helper
  method (`helper <class>.<method>()`; give the agent the comparison line inside the helper,
  found with `grep -n` in `cassandra/cassandra-5.0.9/`).
- **CSV columns:** `order` (suggested order), `target`, `units`, `band`, `estimate`,
  `stage3_record` (where stage 3 recorded the line: a `predicted-negative.md` section, a
  `predicted-positive.md` item, or a note), `stage2_reason`, and two columns to fill as you go:
  `case_file` (the stem) and `stage4` (the outcome class, or "running").
- **Special rows:**
  - **The two accepted candidates come first** (orders 1–3, positive estimate, from
    `predicted-positive.md`): `native_transport_max_frame_size` (`Envelope.java:429`, with its
    allow side `:441` — one case can cover both) and `cached_rows_fail_threshold`
    (`ReplicaFilteringProtection.java:323`). The queue file names the guided agent for them; write
    them up with the autonomous agent like the rest, and remove them from `predicted-positive.md`
    when their case files land.
  - `ResourceLimits.java:213` (settled 2026-10-21: cited, not a case; the production reserves are
    `Concurrent:138`) and `Dispatcher.java:345` (no queue entry; same method as an existing case's
    target, `:348`). Decide per row whether a separate case is worth it; record the decision in the
    CSV either way.

## How to do one target

### 1. Write-up (stage 3, autonomous agent)

1. Make a copy of the source **outside the repository**, so the agent cannot read other cases:
   `rsync -a cassandra/cassandra-5.0.9/ ~/cassandra-5.0.9/`.
2. Open a **fresh** Claude Code session in that copy. Give it only
   [`playbook-autonomous.md`](cassandra/if-check-exp/stage3-ai-deep-read/playbook-autonomous.md),
   [`_TEMPLATE-autonomous.md`](cassandra/if-check-exp/stage3-ai-deep-read/_TEMPLATE-autonomous.md)
   and the target as `file:line`. Nothing else about the line (not the stage-3 ground, not the CSV).
3. File the result as `cases/<stem>--autonomous.md`. The stem follows the existing ones:
   `<constraint>-<method>-<operand>`; check `ls cases/` first and add `-2` if the stem is taken.
4. Add the `_INDEX.md` §1 row (Agent `autonomous`, the file's own estimate, Stage 4 empty) and its
   sha256 in `_INDEX.md` §4. Put the stem in the CSV's `case_file` column. Leave the line in
   `predicted-negative.md` until stage 4 has closed the case.

### 2. Verification (stage 4, a separate agent)

Protocol: [`stage4-runtime-verification/README.md`](cassandra/if-check-exp/stage4-runtime-verification/README.md)
("The run protocol"); environment: [`environment.md`](cassandra/if-check-exp/stage4-runtime-verification/environment.md).

1. **Step-0 audit** (A–D) against `cassandra/cassandra-5.0.9/`: re-read every load-bearing
   citation, check the trigger really reaches the check (find the `OperationType` / caller it
   produces), check the predictions have numbers and the workload arithmetic reaches the limit.
   Fixes go in the case file as dated amendments (section D). Write the audit and the frozen hash
   of the predictions and conclusions tables (B2f–g, B3f–g) into a new results file from
   `_TEMPLATE.md` **before any reading**.
2. Harness under `harness/<stem>--autonomous/` (unit test + one run script per case with
   `EXPECTED:` lines, a stop on a failed first-trigger check, node stopped on any exit);
   instrument-check it. Shakedowns are not readings. Working trees from
   [`copy-source.sh`](cassandra/if-check-exp/stage4-runtime-verification/copy-source.sh), one per
   case. Write audit, amendments, freeze hash and harness to the repo before run 1.
3. Run 1, unit tier then each cluster label as a background job; read `summary.txt`, not whole
   logs; pull small excerpts to `results/<stem>/run1/`, full logs stay on the node.
4. **Independent self-check** that re-parses the raw logs; fill the results file, including the
   **Outcome class**, and the case file's feedback section; decide run 2 and say why.
5. Close the case: `_INDEX.md` §1 Stage 4 and Outcome class cells, the new sha256 in §4 if the case
   file was amended, remove the line from `predicted-negative.md` (or `predicted-positive.md`),
   fill the CSV's `stage4` column, update **Progress** above.

### Rules that hold for every case

- **No conclusions row or prediction is changed after any reading.** A reading that matches no
  frozen row is "Not confirmed (no matching row)". Amendments are dated and made before the first
  reading.
- A negative-estimate case needs a **positive control** (a knob or arm that does move usage), so a
  "does not cap" result cannot come from a workload that never reached the check.
- Nothing is left running on a node; each results file lists what stays on the node.
- Commit per closed batch; `git pull --rebase` before every push (Jingsong commits to the same
  `main`). Edit only set-B rows in the shared files (`_INDEX.md`, `predicted-negative.md`,
  `predicted-positive.md`).

## Suggested batching

- **4–5 targets per batch, one stage-4 agent per node**, as in the four batches of 2026-10-21/22.
- Keep the targets of one `predicted-negative.md` row in one batch (they share a design).
- Order within the CSV: the two positive candidates, then band A → B → C by source area.
  Low-value rows (§13 not production code, §12 emptiness tests, §1 configuration validation) can
  wait until the rest is done.

## What this experiment is

Part of the **misconfiguration** project (Target 1: find resource constraints that limit memory or
disk usage; Target 2: show how the code enforces each; Target 3, bypass analysis, is out of scope
here), on **Apache Cassandra 5.0.9**. `if-check-exp` inventories **capacity checks** — a comparison
of usage against a limit — and the **decision points** they feed, where one outcome lets a memory-
or disk-significant allocation happen and the other blocks, defers or rejects it. It is a standalone
inventory: no cross-referencing with `entry-restriction-exp`, no shared infrastructure; bypasses
noticed along the way are noted in case files for Target 3, not chased.

**Four stages:** (1) CodeQL finds the comparisons; (2) an AI ranks every row into bands A–D;
(3) agents read the source and write a **case file** per line, with an **estimate** and a two-tier
(unit + cluster) verification design; (4) an AI audits and runs each design and files the verdict.

## State before set B started (2026-10-23)

- **Stage 1:** 17,343 `if` statements → 4,489 numeric comparisons + 1,099 helper-guarded rows.
- **Stage 2:** 4,789 units banded (A 134, B 174, C 94, D 4,387); `stage2-ai-preprocessing/bands.csv`.
- **Stage 3:** bands A, B and C fully read; **58 case files** (29 guided, 29 autonomous; estimate
  positive 42, negative 16). 65 of the 402 A/B/C units are a case's target; the other **337** are
  the two-set job (2 accepted candidates in `predicted-positive.md`, the rest rejected lines in
  `predicted-negative.md`, ~151 rows). Nothing is undecided. Band D is not read.
- **Stage 4:** **all 58 closed**, run 1 only (no run 2 anywhere): 41 Confirmed, 4 Refuted,
  12 partial, 1 not confirmed. **Outcome class:** 38 true positive, 0 false positive, 4 true
  negative, 4 false negative, 12 undetermined (all 12 autonomous, mostly the cluster tier).
  Per-case verdicts: `stage3-ai-deep-read/_INDEX.md` §1.

## Decisions in force

- **Two agents** (2026-10-19): the **autonomous agent** gets only
  `playbook-autonomous.md`, `_TEMPLATE-autonomous.md` and a `file:line`, run by hand in a fresh
  Claude Code session in a copy of the source outside this repo; the **guided agent** gets human
  suggestions and asks per case whether to read the autonomous file. A case file's agent is its
  suffix: `<stem>--autonomous.md`, `<stem>--guided.md`. No leakage control beyond that.
- **Estimate vocabulary:** stage 3 predicts `positive` (usage follows the constraint), `negative`
  (it does not, with a **Ground**) or `undetermined`. A negative line still gets a full two-tier
  design that tests that usage does **not** follow the constraint, with a positive control.
- **Every rejected line is a write-up item** (2026-10-19): it leaves `predicted-negative.md` once
  its case is verified at stage 4. `predicted-negative.md` is the only rejection file.
- **Stage 4 has no human gate** (2026-09-30): the AI audits, runs, self-checks and files the
  verdict; a human may overrule any verdict (record it with date and reason).
- **Verdict wording:** "Confirmed" always means the file's own claim held; each results file
  records the claim tested and the **Effect on the constraint**, and since 2026-10-22 the
  **Outcome class** (estimate vs stage-4 effect, stage 4 taken as truth; definition in
  `stage4-runtime-verification/README.md`).
- **Frozen predictions** (2026-10-22): see "Rules that hold for every case".

## Working preferences

- **Plan before editing** rules, naming, scope or folder structure: give an opinion or a
  file-by-file plan and wait for Yang's go-ahead. Small factual fixes need no plan.
- **Commit and push only on request**, asked separately. Two people commit to `main`:
  `git pull --rebase` before every push.
- **Sync before restructuring:** files are also uploaded to GitHub directly, so `git fetch` and
  compare with `origin/main` before renaming or reorganizing.
- **Keep settled decisions** (for example, no cross-referencing `entry-restriction-exp`).

## Where things live

- **Repo:** `MengJingsong/Misconfiguration` on GitHub; no checkout on the CloudLab shared mount.
- **`cassandra/cassandra-5.0.9/`** — the pinned source (`apache/cassandra` tag `cassandra-5.0.9`,
  commit `b5f2a54`, unmodified, committed 2026-10-22). Read and cite from it; never build in it.
  Confirm with `build.xml` `base.version` = `5.0.9` and `git status cassandra/cassandra-5.0.9`
  (nothing changed). GitHub links: `.../blob/cassandra-5.0.9/<path>#L<NN>`, line checked in the
  local file. Records before 2026-10-22 name the old `cassandra-src` clone (same files).
- **`cassandra/if-check-exp/`**
  - `README.md` — format spec, the three rules (§3.4–§3.6), required content, version pinning (§2).
  - `stage1-codeql-preprocessing/` — pointers only; queries in `codeql-queries/`, CSVs gitignored.
  - `stage2-ai-preprocessing/` — `bands.csv` (per-row verdicts), `bands.md`, `playbook.md`, `README.md`.
  - `stage3-ai-deep-read/` — both playbooks and templates, `cases/`, `_INDEX.md` (master index; §4
    holds the autonomous files' sha256), `predicted-negative.md`, `predicted-positive.md`,
    `undetermined.md`, `writeup-set-A.csv`, `writeup-set-B.csv`.
  - `stage4-runtime-verification/` — `README.md` (run protocol, safety rules, outcome class),
    `environment.md` (**start here on a new node**), `environment-notes.md`, `case-notes.md`,
    `_TEMPLATE.md`, `copy-source.sh` (local working tree with a git baseline), `results/<stem>.md`
    + `results/<stem>/run1/`, `harness/<stem>/`.
- **`codeql-queries/`** — the CodeQL packs; results gitignored, regenerated per machine.
- **Outside the repo (CloudLab `/proj/misconfiguration-PG0/`):** `tools/codeql/`, `codeql-dbs/`,
  and the superseded `git-repos/cassandra-src` clone.

## Lessons

**From the earlier write-up batches (19 lines tested, 2026-10-21/22)**
- "Counts items, not bytes" and "a soft target, not a ceiling" were weak grounds when each item has
  a known size or the target is a configurable byte count: those lines mostly came back **caps**.
  Hard-coded water marks and pool-internal bookkeeping did not.
- The cluster tier is where negative cases go **undetermined** (12 of 58 cases): plan a cluster arm
  that isolates the line (hold `native_transport_max_threads`, throttle the load, add a Byteman
  `AT LINE` mutant) and a positive control that is known to move.

**Design**
- With one table, "how much to reclaim" logic is invisible: use several tables plus a Byteman
  `AT LINE` mutant. Unthrottled stress puts peaks at flush throughput, not the limit.
- Read the real resource first and the check's counter second (counters are asynchronous
  estimates); a counter's own trace does not show it tracks the resource.
- Any request held longer than 12 s needs `native_transport_timeout` raised (the coordinator waits
  for the nearer of it and the verb timeout). 5.0 also caps the internode mutation deadline at it.
- `native_transport_max_threads` (128) limits messages held per sender and queued depth;
  `cassandra-stress` limits itself to 1,024 requests in flight (raise `connectionsPerHost`).
- Check a request's size against `LARGE_MESSAGE_THRESHOLD` (131,071 B on the CQL side) before
  predicting its path. Large native-v5 requests leave unreturned direct buffers: use protocol 4
  for direct-memory readings with large client writes.
- `nodetool compact` is a `MAJOR_COMPACTION`; a background compaction (`enableautocompaction`) is
  `COMPACTION`. The first abort or first use in a JVM carries one-off allocation: warm up first.

**Running**
- The node runs from `build/apache-cassandra-*.jar`: Byteman helper classes go on the boot class
  path; a rule on a JDK class needs `boot:`; Byteman's parser needs `(new X(…)).m()`;
  `CassandraDaemon` closes stdout, so trace to a file. Move Byteman listeners off 9091 when two
  JVMs share a host (BMUnit: `-Dorg.jboss.byteman.contrib.bmunit.agent.port=19091`).
- A standalone client JVM on Cassandra classes needs `conf/jvm11-clients.options` on JDK 11. The
  bundled Python driver: use protocol 5 for per-replica failure codes; on one node use
  `DCAwareRoundRobinPolicy` and `token_metadata_enabled=False`.
- Several local nodes applying every write stall on a spinning disk: put data on a tmpfs.
  Timed-out writes expire in the sender's queue and are hinted: truncate hints between arms.
- `ant testsome` forks a 1 GiB JVM (`maxmemory` overrides `-Xmx`); every test copied into a tree
  is compiled by every later `testsome` there; Ant's 1 s timestamps defeat a mutant built from a
  copied `build/` (delete the class files). Never run `ant` in a tree a node runs from.
- A node refuses `concurrent_writes: 1` (set 2, then `nodetool setconcurrency <stage> <n>`, the
  two-argument form). Live heap: the `GC.class_histogram` total, not `GC.heap_info` after `GC.run`.
  Read `RssAnon`, not `VmRSS`. logback rolls `system.log` at local midnight.
- Launch node scripts as `( setsid nohup … < /dev/null > /dev/null 2>&1 & )`; wait with bounded
  background polls, never a foreground `sleep`, and inside the agent's turn. Kill by PID
  (`pkill -f` can match its own shell); match daemons by `java` and working directory. Scripts
  synced to a node can lose the execute bit (call them with `bash`); never edit a running script.
- `grep '^ERROR'` misses messages on the next line; compare numbers in Python, not ad hoc `awk`;
  a self-check matching log seconds takes the last line at or before the second.
- More in each closed results file's §8.

## Nodes

**Yang's nodes: to be announced by Yang** (the earlier suggestion of `pc06`/`pc13` does not hold).
Do not run anything on a node until they are named here. Jingsong uses `pc07` and `pc12`; do not
use those.

Known setup on experiment `jason92-320876` (checked 2026-10-21; Ubuntu 22.04, 40 cores, 251 GiB
each; JDK 11.0.32.1, Ant 1.10.12, `~/cassandra-run1` built with `build-test`). If Yang's nodes are
elsewhere, set them up from `stage4-runtime-verification/environment.md` and record them here.

- SSH to the peers needs `-i /proj/misconfiguration-PG0/.ssh/id_ed25519` (the `cluster_ed25519`
  key named in `~/.ssh/config` is refused). Peers' `ulimit -n` is 1024: raise it in the shell that
  starts a node.
- Untracked test files and `~/stage4-*` folders from closed cases remain on each node (listed in
  each results file). Two cases on one node need separate working trees, data directories, JMX and
  Byteman ports, and loopback addresses (recorded as an environment deviation).
- Full table and setup history: `stage4-runtime-verification/environment.md` §7. CloudLab nodes are
  rebuilt from scratch, so this repo is the only record a new node inherits.

## Open follow-ups (shared, not assigned)

For context only; not part of set B unless Yang takes one on.

- **Upstream bug candidates (JIRA check first):** native-v5 large-request frame buffers never
  returned (`networking_cache_size`, `OverflowSize` grows); `BufferPool` overflow trims drive
  `OverflowSize` negative (`NORMAL_CHUNK_SIZE`); pre-V5 THROW-path direct-memory retention;
  `MAX_HINT_BUFFERS=1` deadlocks the hint path; `sendWriteWithCallback` holds a refused write until
  the timeout (`internode_max_message_size`); `maxHintsInProgress` can never fire (bare
  `CacheLoader`, `StorageProxy.java:203`).
- **Reruns that could settle undetermined cluster tiers:** the `SEPExecutor` cases (pin
  `native_transport_max_threads`, throttle the load), `flushLowWaterMark`, the SAI sawtooth,
  `NORMAL_CHUNK_SIZE` with held frames, a throttled arm for `commitlog_total_space` `:259`.
- **Stage-3 notes not yet applied to filed cases:** `SystemKeyspace.java:1919` as a second check
  site of `prepared_statements_cache_size`; stream receive (`StreamSession.checkDiskSpace()`) as a
  second decision point of `max_space_usable_for_compactions_in_percentage`; `max_mutation_size` §5
  calls `commitlog_total_space` a ceiling (it is a reclaim target); `file_cache_size` §4 names
  `applyConfig()` (it is `applySimpleConfig()`). Older rulings: `git show d40ee0c:HANDOFF.md`.
- **Remaining band-D lines in `predicted-negative.md` §10** (`SEPWorker`, `SharedExecutorPool.java:137`,
  `SEPExecutor.java:373`): low value after the `SEPExecutor` results.
- **`undetermined.md` §2 re-audit** and **band D** (4,387 units, one filed case already came from it).

## Handoff log

Dated notes from Yang's sessions go here, newest first.

- **2026-10-23** — File made self-contained; handoff-notes rule added; node assignment withdrawn
  pending Yang's choice.
