# Stage 4, short path — running a case (human + AI)

The short path's stage 4: a **blind** AI executor runs a short-path solution on a real node, both tiers, and files its own results ([`../README.md`](../README.md), "Two paths, two tiers each"). The long path's stage 4 needs none of this: it runs first, and an ordinary AI session does all of it by following [`../README.md`](../README.md).

**Why a human is in the loop.** The executor must not know the long path's design or findings. Any session in this repository has read them, so the executor has to be a **fresh process started outside it**. The human starts that process from a terminal, with one command; the AI does everything before and after.

| # | Step | Who | Command or action |
|---|---|---|---|
| 0 | Once per machine, CLI version, or change to the flags: the canary | human | `python3 $S4/short-path/run-executor.py canary --node pc80` |
| 1 | The short solution is filed and committed ([stage 3, short path](../../stage3-ai-deep-read/short-path/README.md)) | human + AI | its `_INDEX.md` row says `current` |
| 2 | Preview: preflight checks, the prompt, nothing started | human | `python3 $S4/short-path/run-executor.py run --stem <stem> --node pc80 --dry-run` |
| 3 | Run the executor: unit tier, then cluster tier. You watch and answer its permission questions; it stops by itself | human (the executor is an AI) | `python3 $S4/short-path/run-executor.py run --stem <stem> --node pc80` |
| 3b | If the session was interrupted | human | `... run --stem <stem> --resume` |
| 4 | Audit the transcripts and the deliverables, copy them into this folder | human, or the AI (no isolation needed) | `python3 $S4/short-path/run-executor.py collect --stem <stem>` |
| 5 | Review the collect report (section 3 below) | AI | read `results/<stem>/collect-report.txt` and the results file |
| 6 | Commit and push | AI, when the human asks | the results file, `results/<stem>/`, `harness/<stem>/` |
| 7 | Write the side-by-side | AI, a new session | [`../executor-prompts.md`](../executor-prompts.md) §2 |

`S4=<repo>/cassandra/if-check-exp/stage4-runtime-verification`. Run everything from a plain terminal where `claude` is logged in (`claude -p hi` prints a reply) and `ssh-add -l` lists a key.

## 1. What `run` sets up

- A workspace **outside the repository**, `~/sp-run/stage4/<stem>/exec/`, mirroring the repository's relative layout but holding only what the executor may read: the stage-4 `README.md`, `_TEMPLATE.md`, `environment.md`, and its own solution (read-only). `meta/` next to it holds the prompt, the run record and the reports.
- An interactive Claude Code session started in it, with `--restricted --safe-mode --strict-mcp-config`: the file tools cannot leave the workspace, there are no MCP servers, memory, CLAUDE.md, hooks or sub-agents, and the web is limited to the stage-3 allowlist. Bash and ssh are on, because the executor works on the node.
- The prompt, [`EXECUTOR-PROMPT.md`](EXECUTOR-PROMPT.md), with the stem, the node and the node's current home-directory listing filled in.

`run` refuses to start unless: the solution is filed, `current`, committed and equals its recorded sha256; the canary passed with exactly these flags; `claude`, an ssh key and every node work; the workspace is new (a second attempt is `--attempt 2`); no `CLAUDE.md` sits above it. It prints any line of the shared stage-4 files that mentions the case (a leak check on what the executor will read) and asks before starting if there is one.

## 2. What is and is not isolated

| Reaches | Blocked by | Strength |
|---|---|---|
| This repository, `~/.claude`, other local files, through the file tools | `--restricted`: confined to the workspace | enforced; the canary proves it |
| This repository, `~/.claude`, through plain read commands in Bash (`cat`, `head`, `ls`, `grep` on a path outside the workspace) | the permission layer refuses them, even though the command is on the allowlist | enforced in the canary (B1); in a live session it would be a question to you: say no |
| This repository, `~/.claude`, through any other Bash route (`python3`, `bash -c`, a pipeline) | nothing | **not blocked**; detected afterwards by `collect` (canary B3 runs it and checks the audit flags it) |
| The copy of the repository on the nodes' shared mount (`/proj/misconfiguration-PG0/git-repos/`) | the prompt | **not blocked**; detected afterwards (canary B2) |
| The long path's leftovers in a node's home (`~/stage4-logs` and the like) | the prompt, which lists them | **not blocked**; they cannot be hidden, only named |
| The project's GitHub and Google Docs, search engines | not on the allowlist, no search tool | enforced; the canary proves it |
| Memory, CLAUDE.md, MCP servers, other sessions' notes | `--safe-mode`, `--strict-mcp-config` | enforced; the canary's X1 probe checks it |

So the isolation is enforced for everything the executor would reach by accident, and audited for everything it could reach on purpose. The canary includes three Bash probes (B1, B2, B3) that deliberately do the forbidden thing and check that the audit flags it.

## 3. Judging the collect report (AI)

`collect` prints and saves `collect-report.txt`: the blindness audit over every transcript of the session, then the deliverable checks. The verdict line is `COLLECT: PASS`, `REVIEW` or `FAIL`.

| Item | Means | What to do |
|---|---|---|
| `BLINDNESS: FAIL`, an `[EXECUTED]` hit | the executor touched something it must not have | read the call and its output. If it exposed anything of the other path, do not file that tier's result and rerun it in a fresh attempt. If it was harmless (for example a directory listing that showed no names), say so, ask the human, copy with `--force`, and record the decision in the side-by-side |
| `[REFUSED]` hits | it tried and was refused (or the command failed) | a note: record it; nothing else happened |
| `D1 solution unchanged` FAIL | the frozen solution was edited | discard the attempt |
| `D2`/`D3`/`D4` | no results file, no "Files read" list, or no verdict per tier | read the results file; the executor may have stopped early; resume it with the human |
| `D5` REVIEW | no harness folder | fine only if the design needed no code |

Read the results file's §1 "Files read" against the transcript hits: they should agree. **Judge leakage and completeness only.** Do not accept or reject a result because it agrees or disagrees with the long path, and never edit the executor's results or its solution; what the result means is the side-by-side's job, and it rates nothing.

## 4. Prompts for the AI session

Step 5, after `collect`:

```text
Review the short-path stage-4 run for <stem>. Read cassandra/if-check-exp/stage4-runtime-verification/short-path/README.md
section 3, short-path/results/<stem>/collect-report.txt, and short-path/results/<stem>.md (§1 "Files read", §3 runbook
defects, §8 verdicts). Judge leakage and completeness only: never accept or reject a result because it agrees or
disagrees with the long path, and edit neither the results file nor the solution. List each REVIEW item and what you
decided about it. Do not commit.
```

Step 7, the side-by-side: the prompt in [`../executor-prompts.md`](../executor-prompts.md) §2.2, after step 6.

## 5. Worked example: `memtable_heap_space` (2026-10-06)

First run of this procedure. Both tiers confirmed by the executor; the audit reported one executed hit (an `ls` of `/proj/.../git-repos`
whose output showed no names), accepted by the human and copied with `--force`. What the run changed in the tooling: the audit now
exempts the session's own scratchpad; the prompt no longer suggests `pgrep -f` (it matched its own ssh shell and sent the executor
off to check two other nodes), and asks for scripts to be written into the harness folder, because this executor left them in its
scratchpad and on the node, and the reviewer had to copy them into `harness/<stem>/scripts/` afterwards. The run directory on the
node was deleted after the results were copied (the evidence excerpts are in `results/<stem>/run1/`). Another pitfall: the human
pasted the `collect` command into the executor session; run it in a separate terminal.

## 6. Files

| File | Holds |
|---|---|
| [`run-executor.py`](run-executor.py) | `canary`, `run` and `collect` |
| [`EXECUTOR-PROMPT.md`](EXECUTOR-PROMPT.md) | the executor's prompt, with `{{placeholders}}` the script fills in |
| `results/<stem>.md` | the executor's results file (copied by `collect`), and `results/<stem>/` for its excerpts, `collect-report.txt` and `executor-run.json` |
| `harness/<stem>/` | the executor's code (copied by `collect`) |
