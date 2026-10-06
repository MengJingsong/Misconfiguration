# Prompts for the short path's stage 4

For a case that has both a long-path case file and a short-path solution
([README "Two paths, two tiers each"](README.md#two-paths-two-tiers-each)). The long path always goes first and needs no special
prompt: an AI session in this repository follows the [README](README.md). This file holds what is specific to the short path's
sessions.

## 1. The short path's executor

It is started by a script, not by a prompt you paste: [`short-path/run-executor.py`](short-path/run-executor.py) does the
pre-flight (the solution is filed, committed and unchanged; the canary passed; the nodes and your ssh key work; the shared files
do not discuss the case), builds the isolated workspace, fills in and delivers the prompt
([`short-path/EXECUTOR-PROMPT.md`](short-path/EXECUTOR-PROMPT.md)), starts the session, and afterwards audits every transcript
and copies the deliverables (`collect`). The commands and the table of who does what are in
[`short-path/README.md`](short-path/README.md). The earlier manual flow (deny rules in `.claude/settings.local.json`, a prompt
pasted into a new session, `check-blindness.py` on the newest transcript) is replaced by it: Bash could not be denied that way,
and the prompt named paths that differ between machines.

## 2. The side-by-side writer (an AI session in this repository)

### 2.1 Pre-flight

Both paths' results are filed and committed: the long path's, and the short path's from `run-executor.py collect`. This session
reads both, so nothing needs hiding; start a normal session in the repository.

### 2.2 The prompt

```text
Write cassandra/if-check-exp/stage4-runtime-verification/comparison/<stem>.md from comparison/_TEMPLATE.md, using
long-path/results/<stem>.md and short-path/results/<stem>.md (and short-path/results/<stem>/collect-report.txt for the
blindness audit; report any EXECUTED or REFUSED hit in section 4). Report, rate nothing; edit neither results file nor
either solution. Add a line to comparison/_INDEX.md, and change the Comparison cell of the case's row in
stage3-ai-deep-read/short-path/_INDEX.md from `pending` to a link to the new file (touch nothing else in that row).
Do not commit or push.
```

## 3. Why these rules

The two paths are only comparable if the short executor never saw the long path's design or readings. The short path is meant to
show what the AI does without the long path's method, so an executor that had read the long path's conclusions would measure
nothing. Three layers guard it: the workspace (the executor is not in this repository and its file tools cannot leave it), the
prompt (it names what a node holds that it must not open), and the transcript audit (everything Bash could reach is detected
afterwards). None of the three is enough alone.
