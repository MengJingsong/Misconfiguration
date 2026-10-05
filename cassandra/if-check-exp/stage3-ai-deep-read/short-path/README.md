# Stage 3, short path — verification solutions without the human method

**An experiment, decided 2026-10-02.** The short path is stage 3's second path
(see [`../README.md`](../README.md)); the established one is the
[long path](../long-path/README.md). The first case,
`memtable_heap_space`, has a filed two-tier solution (version 2); version 1, a
single-tier one, is kept as `--v1` and marked superseded. The pilot on the three
closed cases was skipped by decision, so the first real side-by-side happens
when a case has both paths' stage-4 results.

## 1. What it is

For a candidate code location, an AI does **two things**:

1. **Trace the constraint** — find where the limit is declared, its unit and
   default, how it is set, which resource it bounds, and the mechanism that
   enforces it.
2. **Design a verification solution** — the test stage 4 would run — from
   whatever the AI itself collects from the sources, and its own decisions. The
   solution has **two tiers**, each a complete procedure of its own: a **unit
   tier** (drive the relevant classes directly; measure the check's own operand)
   and a **cluster tier** (a real node; measure the actual resource). The
   two-tier structure is the one thing asked of the AI about *how* to design;
   everything inside each tier is its own decision.

It applies **none of the long path's method**: not the three rules (§3.4–§3.6
of the experiment README), not the three enforcement patterns (§3.2), not the
test-design rules (§8), not the case template, not the playbook. The reason is
to find out whether that method helps the AI or limits it. If the two
solutions come out the same, the method costs nothing; if the short one is
better, the method is holding the AI back; if worse, the method is earning its
keep.

**The short path files no verdict.** It does not say whether the line is "a
case worth testing". It states the claim its own solution tests and designs
that test. Stage 4 runs **both** paths, both tiers each, and reports the
results side by side
([Two paths, two tiers](../../stage4-runtime-verification/README.md#two-paths-two-tiers-each)).
There is no rating of the two solutions and no scoring across paths.

## 2. What stays, and what goes

| Kept — objective and safety, not method | Dropped — method |
|---|---|
| The goal: does the constraint cap the node's memory or disk usage? | The three rules and three patterns |
| The pinned `cassandra-5.0.9` source | The six test-design rules and the §9 layout |
| Shared-infrastructure safety rules for stage 4 | The case template and the playbook |
| A minimal output skeleton ([`_TEMPLATE.md`](_TEMPLATE.md)), so the pair can be compared | Every filed case, every results file, `HANDOFF.md` |

**Scope: memory and disk.** CPU constraints are out of scope for now, matching
the experiment's resource scope (§3.3 of its README). Revisit if the
comparison shows the long path's Rule 2 excluded something real.

## 3. Files

| File | Holds |
|---|---|
| [`BRIEF.md`](BRIEF.md) | The prompt the isolated agent receives, followed by `_TEMPLATE.md`, the entry pointer and one return instruction (see below). Self-contained: it links to nothing in this repo. |
| [`_TEMPLATE.md`](_TEMPLATE.md) | The output skeleton: A. constraint trace, B. verification solution (B1 claim, B2 unit tier, B3 cluster tier, B4 risks), C. paths read. No verdict field. |
| [`run-case.py`](run-case.py) | Runs a case end to end (steps 1 to 6 below): workspace, prompt, the isolated writer, extraction, audits, and — only on request — filing. Refuses to start unless the isolation test passed with the same flags. `run` and `file` subcommands. |
| [`isolation-test.py`](isolation-test.py) | The isolation test (canary) the runner executes before a writer run. It also holds the writer's exact CLI flags and the web allowlist: `python3 isolation-test.py --print-flags`. |
| [`_INDEX.md`](_INDEX.md) | One row per filed solution: stem, entry pointer, feed, filing date, sha256, model, isolation, leakage audit, comparison link, status (`current` or `superseded`). |
| [`cases/`](cases/) | The solutions, one file per case, named by the same stem as the long-path file. |

## 4. Guide: going through the short path for one case

The whole path in one page. Details of each step are in "Running a case" below.
Commands use the script; `<stem>` is the case's file stem, and
`SP=/home/jingsong/repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/short-path`.

### 4.1 Ground rules (read once)

- Run everything from a plain Linux terminal where the `claude` CLI is logged in
  (`claude -p hi` prints a reply). A `claude` started inside another Claude
  session may not authenticate.
- **Stay blind:** do not open the case's long-path file or any stage-4 file for
  it until its solution is filed. The side-by-side depends on it.
- **Never edit a solution, never reuse an attempt directory.** A failed or
  rejected attempt is kept and the next one is `--attempt N+1`.
- The scripts never commit. You commit and push when you choose.

### 4.2 Once per machine, CLI version, or change to the flags or allowlist


```bash
python3 $SP/isolation-test.py
```

Pass means `RESULT: PASS` (19 probes). Any `FAIL` means stop and do not run a
writer. The report is `~/short-path-run/isolation-test/isolation-test-report.txt`.
`run-case.py` refuses to start unless that report passed with the same flags.

### 4.3 Per case


| Step | Command | Result |
|---|---|---|
| 1. Preview (optional) | `python3 $SP/run-case.py run --stem <stem> --dry-run` | the entry pointer, flags and prompt tail; nothing is run |
| 2. Run the writer | `python3 $SP/run-case.py run --stem <stem>` | a few minutes to tens of minutes; ends with `AUDIT: PASS`, `REVIEW` or `FAIL`; files in `~/short-path-run/<stem>/` |
| 3. Judge the audit | read `run-report.txt`; for `REVIEW`, read `solution.md` | see the table below |
| 4. File it | `python3 $SP/run-case.py file --stem <stem>` (add `--accept-review` after a reviewed `REVIEW`) | copied to `cases/<stem>.md`, header filled, `_INDEX.md` row with its sha256 |
| 5. Commit and push | `git add`, `git commit`, `git push` | the solution is frozen in history |
| 6. Hand off | stage 4 runs both tiers of this solution, by a session that sees only this path | `results/<stem>--short.md` |

A case with no preset needs `--pointer <file:line> --feed 3a|3b` in step 2
(`file:line` is the capacity check only; take it from the long-path index's
*Capacity check* column, and nothing else from that row).

### 4.4 Judging the audit (step 3)


| Verdict | Meaning | What to do |
|---|---|---|
| `PASS` | no tool call left the clone or the allowlist, no URL named the project, no stage-4 vocabulary, all sections present, section C matches the log | file it |
| `REVIEW` | something needs a human look | read each item, then decide below |
| `FAIL` | a leak, a forbidden tool, a project URL, or a missing section | discard; rerun with `--attempt N+1`; do not tell the writer why |

For a `REVIEW` item, ask whether the writer could only have known it from
outside the source tree:

| Item | Acceptable if | Reject if |
|---|---|---|
| Section C lists a path the log never opened | the file shows up only as a grep hit (a minor overstatement; it stays on record) | the claims about that file's contents could not have come from the grep output |
| URL cited but never fetched | it is a well-known public page the writer plausibly knew | it carries a specific figure or conclusion with no fetch behind it |
| A vocabulary hit (`harness`, `run 1`, `results`, …) | it is ordinary engineering language in a design (a test harness it proposes) | it points to this experiment's artifacts, section names or measured numbers |
| A denied attempt outside the clone | it is recorded and nothing else happened (a note, not a verdict) | it names this project or its files |

### 4.5 What counts as done

For the short path: the solution is filed, its sha256
is in `_INDEX.md`, and the commit is pushed. It is not judged here: the short
path files no verdict, and whether it agrees with the long path is stage 4's
decision.

### 4.6 Worked example

**First case, version 1 (`memtable_heap_space-tryAllocate-limit`,
2026-10-05).** The writer took about 3 minutes and made 28 tool calls, all
inside the clone and none on the web. The audit passed everything except one
`REVIEW` item: section C listed two paths seen only as grep hits. It was
accepted, filed, committed and pushed; stage-4 runs are pending. It was later
superseded: version 2 was written under the two-tier skeleton (a fresh
`--attempt 2`), filed with `--supersede`, and version 1 was kept as `--v1`.

## 5. Running a case — instructions for the AI session that runs it

### 5.1 Roles

**Three roles, never the same session.**

| Role | Who | May read | Must not |
|---|---|---|---|
| **Runner** (you, following this section) | any session | this README, `BRIEF.md`, `_TEMPLATE.md`, `_INDEX.md`, and the Cassandra source | edit the solution; put anything about the case into the prompt beyond the entry pointer; open the case's long-path file or any stage-4 file for it before the solution is filed |
| **Writer** | a fresh, isolated headless session you launch | the Cassandra source tree and nothing else | see anything else — the whole point of the path |
| **Stage-4 executor** (one per path) | a later session | only its own path's frozen solution | read the other path's solution or readings before its own runs are filed |
| **Side-by-side writer** | the session that finishes the last run | both paths' results | edit either solution |

The runner may have read this repository; the writer must not have. That is
why the writer is a separate process whose file access you confine, not a
subagent of your own session.

**The script does steps 1 to 6.** `python3 run-case.py run --stem <stem>` does
steps 1 to 5 and prints the audit; `python3 run-case.py file --stem <stem>` does
step 6 once the audit passed (`--accept-review` after you have read every
REVIEW item). It never edits a solution and never commits. The steps below say
what it does, and what to do by hand if you cannot use it.

### 5.2 Step 0 — Inputs

- **Case stem.** The long-path file's stem if the case has one (for example
  `memtable_heap_space-tryAllocate-limit`), otherwise the §6.1 naming in the
  experiment README. The writer never sees it.
- **Entry pointer:** a `file:line` in the pinned source, relative to the clone
  root (Cassandra's layout makes that `src/java/org/apache/...`). Either Jingsong
  gives it, or you copy **only** the `file:line` of the *Capacity check* column
  from [`../long-path/_INDEX.md`](../long-path/_INDEX.md). Do not read the rest of that row: the
  constraint name and decision point would leak into your context and then
  into the prompt.
- **Feed** (`3a` or `3b`) for the index row.

### 5.3 Step 1 — Prepare a clean workspace

The workspace must sit **outside this repository's tree**, in a directory with
no `CLAUDE.md` in it or in any parent directory, and the source clone must be
pristine with no remote pointing back to a clone that holds extra files.

```bash
CASE=/home/jingsong/short-path-run/<stem>; mkdir -p $CASE && git clone -q --branch cassandra-5.0.9 --no-hardlinks /home/jingsong/repos/cassandra-src $CASE/src && git -C $CASE/src remote remove origin
```

Verify: `git describe --tags` prints `cassandra-5.0.9`, `git status --short --ignored` prints nothing, and
`ls -a | grep -i claude` prints nothing.

```bash
cd /home/jingsong/short-path-run/<stem>/src && git describe --tags && git status --short --ignored && ls -a | grep -i claude
```

A second attempt on the same case gets its own directory (`<stem>--attempt2`),
never a reused one.

### 5.4 Step 2 — Build the prompt

`BRIEF.md`, a blank line, `_TEMPLATE.md`, then the entry pointer and one
return instruction. The return instruction is operational, not method: the
writer cannot write files, so its final message is the solution.

```bash
M=/home/jingsong/repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/short-path; CASE=/home/jingsong/short-path-run/<stem>; { cat $M/BRIEF.md; echo; cat $M/_TEMPLATE.md; printf '\n---\nEntry pointer: <file>:<line>\n\nReturn the completed skeleton as your final message.\n'; } > $CASE/prompt.md
```

Check that the prompt names nothing about the case. The only hit for the case's
own words may be the entry-pointer line.

```bash
grep -n -i -E '<words from the stem>|stage|result|long-path|handoff' /home/jingsong/short-path-run/<stem>/prompt.md
```

### 5.5 Step 3 — Isolation test — before the first run on a machine or CLI version, and whenever the flags or the allowlist change

The confinement is the only isolation; test it, do not assume it. The script
runs probes through the **same flags** as the writer and grades each from the
CLI's tool-call log (not from what the model says): a positive control (source
readable, an allowlisted page fetchable), the tool inventory (no Bash, no
write tools, no MCP tools, no WebSearch), a no-project-context probe, reads and
searches of this repository, the Google Docs links and a planted token file
(by absolute path, by `../` and through a symlink), and fetches of this
project's GitHub copies and other non-allowlisted hosts.

```bash
python3 /home/jingsong/repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/short-path/isolation-test.py
```

It needs a `claude` CLI that is logged in **in that terminal** (check with
`claude -p hi`; a CLI launched from inside another Claude session may not be),
and takes a few minutes. `--only F1,W2` runs a subset, `--dry-run` lists the
probes.

- **Exit 0 and `RESULT: PASS`** (or `PASS with warnings`, which means some
  probe was *inconclusive*, usually because the model made no attempt; read
  those and rerun them): go ahead. The script prints the *index cell* to record
  in `_INDEX.md`; the report is in `<workdir>/isolation-test-report.txt`.
- **Exit 1, any `FAIL`: do not run the writer.** Report it to Jingsong, with
  the logs under `<workdir>/logs/`.
- The test does not replace the audits in step 5; it checks the mechanism, the
  audits check the run.

### 5.6 Step 4 — Run the writer

The flags are fixed by `isolation-test.py` (print them with `--print-flags`),
so the test and the run cannot drift apart:

- `--restricted` ignores user, project and local settings files, removes Bash,
  and confines the file tools to the working directory.
- `--strict-mcp-config` drops MCP servers, which `--restricted` alone does not:
  the user's Google Docs connector could otherwise read the project's progress
  report. `--safe-mode` disables CLAUDE.md, skills, plugins, hooks and custom
  agents; `--disable-slash-commands` disables skills.
- `--tools Read,Grep,Glob,WebFetch` plus an `--allowedTools` list of
  `WebFetch(domain:...)` entries: **the web is on, but only for an allowlist**
  (allowlist `v1`: `issues.apache.org`, `cassandra.apache.org`,
  `lists.apache.org`, `docs.oracle.com`, `docs.openjdk.org`, `netty.io`).
  Everything else is denied by default. `github.com` and
  `raw.githubusercontent.com` are deliberately **not** on it: a domain rule
  cannot tell `github.com/apache` from this project's repository.
- **No `WebSearch`.** A search engine can return snippets of this repository or
  of the Google Docs, and domain rules cannot filter them. Add it only as a
  variant, after the repository and both Google Docs are confirmed private
  (open each link logged out).

Record the model that ran (it is in the log's first line).

```bash
cd /home/jingsong/short-path-run/<stem>/src && claude -p $(python3 /home/jingsong/repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/short-path/isolation-test.py --print-flags | tr -d "'") --output-format stream-json --verbose < ../prompt.md > ../run.jsonl
```

The `$(…)` form is only a convenience; if the shell mangles the parentheses in
the allowlist entries, paste the printed flags directly. Drop `--verbose` if the
CLI rejects it. Run it in the background and read the log when it finishes; a
solution can take many minutes.

### 5.7 Step 5 — Extract the solution and audit it

```bash
python3 - <<'EOF'
import json
D='/home/jingsong/short-path-run/<stem>/'
calls=[]; result=''
for l in open(D+'run.jsonl'):
    try: e=json.loads(l)
    except Exception: continue
    if e.get('type')=='assistant':
        for c in e['message'].get('content',[]):
            if c.get('type')=='tool_use': calls.append(c['name']+' '+json.dumps(c['input']))
    if e.get('type')=='result': result=e.get('result','')
open(D+'tool-calls.txt','w').write('\n'.join(calls)+'\n')
open(D+'solution.md','w').write(result)
print(len(calls),'tool calls;',len(result),'chars in solution')
EOF
```

**Audit 1 — files touched.** Every path in the tool-call log must be under the
clone. The output must be empty.

```bash
grep -o '/home/[^" ]*' /home/jingsong/short-path-run/<stem>/tool-calls.txt | grep -v '/short-path-run/<stem>/src'
```

**Audit 1b — web use.** Every `WebFetch` URL in the log must be on the
allowlist, and none may mention this project (`MengJingsong`, `Misconfiguration`,
`docs.google.com`, `if-check`). The solution's A5 must cite only pages the log
shows were fetched, each with its retrieval date. Keep `run.jsonl`: web pages
change, and it holds the fetched content.

```bash
grep -o 'WebFetch {[^}]*' /home/jingsong/short-path-run/<stem>/tool-calls.txt
```

**Audit 2 — the solution's content.** Scan for signs of stage-4 knowledge.
Every hit needs a read. A claim derived from the code (with a `file:line` that
supports it) is fine; a measured number, a results-file artifact, a harness
name or a section reference from this experiment is a **fail**.

```bash
grep -n -i -E 'stage.4|long.path|handoff|results|run 1|measured|HeapPoolTest|harness' /home/jingsong/short-path-run/<stem>/solution.md
```

**Audit 3 — completeness.** Sections A1–A5, B1, B2a–h (unit tier), B3a–h (cluster tier), B4 and C are all present (a tier may instead say `n/a: <reason>`, which is accepted and noted), and
section C's paths are a subset of what the tool-call log shows. A solution with
a missing section is a failed run, not something to patch.

**A failed audit means discard and re-run** in a new attempt directory. Never
edit the solution, and never explain to the writer what went wrong. Keep the
failed attempt's directory and note it in the index row.

### 5.8 Step 6 — File and freeze

1. Copy `solution.md` to `cases/<stem>.md`. Fill in only the header table's
   *Session / date* row (model, CLI version, date, attempt number). Change
   nothing else.
2. `sha256sum cases/<stem>.md`.
3. Add the row to [`_INDEX.md`](_INDEX.md): stem, entry pointer, feed, date,
   sha256, model, isolation (the index cell the isolation test printed, for example `restricted+web (allowlist v1), canary pass, <CLI version>, <date>`; name any variant, below), audit
   (`pass`, or `fail` for a discarded attempt), comparison (`pending`).
4. Commit only when Jingsong asks. A filed solution is **never amended**; it
   has no feedback field.

**A new version of a case that already has a solution** (for example after the
skeleton changed): run with a fresh `--attempt N`, then
`file --stem <stem> --supersede`. The existing `cases/<stem>.md` is renamed
`cases/<stem>--vN.md` with its content untouched, its index row is marked
`superseded`, and the new solution takes `cases/<stem>.md`. Versions and
attempts are different things: an attempt is a run of the writer, a version is
a filed solution.

### 5.9 Step 7 — Hand off

Stage 4 runs both tiers of this solution on its own protocol
([Two paths, two tiers](../../stage4-runtime-verification/README.md#two-paths-two-tiers-each)),
by a session that has read this path's solution and nothing from the other
path. The side-by-side of the two paths' results is written at the end, by the
session that finishes the last run.

## 6. Limits of the standard run, and variants

The standard run reads the source tree and the allowlisted sites, nothing
else: no `git log`/`blame` (Bash is removed), no GitHub, no search engine.
A **variant** that widens the sources is allowed as a second attempt, filed as
a separate solution (`cases/<stem>--r2.md`); name it in the index's isolation
column, because it changes what the comparison means, and rerun the isolation
test with the changed flags first.

| Variant | Change to the run | Check first |
|---|---|---|
| `+search` | add `WebSearch` to `--tools` | The repository and both Google Docs are private (open each link logged out) |
| `+git` | add `Bash(git log:*)`, `Bash(git show:*)`, `Bash(git blame:*)` to `--tools` and `--allowedTools` | Bash is still confined to the clone; the test's probes must still pass with this exact flag set |
| `+domain` | add a `WebFetch(domain:...)` entry | The domain cannot serve this project's content; bump the allowlist version and record it |

**Blind both ways.** Whoever writes a case's short solution does not open that
case's long-path file, and whoever writes the long-path file does not open the
short one. In stage 4, an executor reads only its own path's solution; only the session that writes the side-by-side reads both paths' results.

**Noise check (optional).** Running the short path twice on a case, filed as
`cases/<stem>--r2.md`, measures run-to-run variation, so a disagreement with the
long path is not mistaken for a difference between the paths.
