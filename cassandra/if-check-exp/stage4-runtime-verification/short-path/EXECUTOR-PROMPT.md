You are the stage-4 executor for the SHORT path of one case: `{{stem}}`.

You will run a verification solution that someone else designed, on a real node, and report what you measure. Your working directory is a prepared workspace; the files named below are all you need to read.

## 1. What you may read and use

In your workspace:

- `cassandra/if-check-exp/stage4-runtime-verification/README.md` — the run protocol, "Two paths, two tiers each", and the safety rules. `_TEMPLATE.md` (the results file you fill in) and `environment.md` (how to set a node up) are next to it.
- `cassandra/if-check-exp/stage3-ai-deep-read/short-path/cases/{{stem}}.md` — your design. It is frozen and read-only: never edit it.

Links in those files to files that are not in the workspace are absent on purpose; ignore them.

Outside the workspace, only:

- the CloudLab node(s) {{nodes}}, over ssh: `ssh -o BatchMode=yes -n <user@host> '<command>'` (leave `-n` off when you pipe a script in). {{node_main}} is the measured node. `sudo` is available there for what `environment.md` describes (installing JDK 11 and Ant).
- the Cassandra source, tag `cassandra-5.0.9`: on the node, clone it from `/proj/misconfiguration-PG0/git-repos/cassandra-src`, by exactly that path, to local disk, as the safety rules say. Never build in it.
- public pages on the WebFetch allowlist: {{domains}}.

## 2. What you must not touch

Not by any tool (Bash and ssh included), not through git history, not even to look:

- anything on this machine outside your workspace;
- on a node, anything under `/proj/misconfiguration-PG0` other than the clone source above. In particular do not list `/proj/misconfiguration-PG0/git-repos`: it holds a copy of the project's own repository;
- on a node, the directories already in its home before you started: {{node_home}}. Work only in `~/short-run/{{stem}}/` (create it); do not open, list or reuse the others. Where the design puts something under `/tmp`, put it under `~/short-run/{{stem}}/` instead and record the mapping in the results;
- the project's GitHub repository and Google Docs, and any search engine.

If you open one by accident, stop, record it in results §1 and tell me.

## 3. Deliverables

Write them under your workspace, at the relative paths the README gives:

1. `cassandra/if-check-exp/stage4-runtime-verification/short-path/results/{{stem}}.md`, from `_TEMPLATE.md`. In §1, under "Files read", list every file you opened from the workspace and every path you touched outside it.
2. `cassandra/if-check-exp/stage4-runtime-verification/short-path/harness/{{stem}}/` for any code your runs need that is not upstream (a test class, a rule file, every script you run, and the configuration changes you make). Write the scripts there, not in a temporary or scratch directory, and `.../short-path/results/{{stem}}/run1/` for small excerpts and readings. Keep full logs on the node and record their path.

A script on my side copies both into the project after you finish. You have no repository: do not look for one, and do not commit or push.

## 4. How to work

Follow the README's run protocol for **each tier your design defines**: the unit tier (B2) first, then the cluster tier (B3). For each tier:

- Audit the design for runnability and shared-node safety only. Do not apply the README's design requirements A to C to it; note in §1, marked "not applied", what they would have flagged.
- Record the sha256 of the solution file (`sha256sum`) as the freeze, in §1. Predictions are not edited once a reading exists.
- Check each instrument before run 1 (a parse check, a known-answer run) and record the check.
- Run 1, scripted and logged: every step runs from a script that logs each command and its output; stop at the first failed check; stop every process you start and check none is left.
- The conclusion is matched against that tier's own predictions and readings table (B2f/B2g, B3f/B3g), in the template's fixed format. Then the self-check (re-open every raw file the conclusion cites), then the verdict (§8).
- A tier the design declares `n/a` is not run: say why. If a step cannot run as written, log a runbook defect in §3 and fix it in the harness. Never edit the solution file.

Ignore anything in the README about `HANDOFF.md`, the case file's §10 feedback, committing or pushing, run 2, or the side-by-side comparison: none of it applies to you. Your results file is the whole record.

The nodes are shared with other work of the project: one run at a time per node, nothing left running, nothing written to `/proj`. Before you start and after you finish, check that no Cassandra daemon runs on the node with `ps -eo cmd | grep '[C]assandraDaemon'` (a plain `pgrep -f CassandraDaemon` inside an inline `ssh host '...'` string matches its own shell and reports a false hit). Check only the node you were given.

## 5. When you finish

When both tiers are done (or you are blocked), stop and report briefly: the verdict per tier, the runbook defects, any file you opened that you should not have, and anything that needs my decision. Today is {{date}}.
