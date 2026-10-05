# Stage 3, short path — verification solutions without the human method

**An experiment, decided 2026-10-02.** The short path is stage 3's second path
(see [`../README.md`](../README.md)); the established one is the
[long path](../long-path/README.md). No solution is filed yet; the pilot on
the three closed cases was skipped by decision, so the first real comparison
happens when a case gets both solutions and reaches stage 4.

## What it is

For a candidate code location, an AI does **two things**:

1. **Trace the constraint** — find where the limit is declared, its unit and
   default, how it is set, which resource it bounds, and the mechanism that
   enforces it.
2. **Design a verification solution** — the test stage 4 would run — from
   whatever the AI itself collects from the sources, and its own decisions.

It applies **none of the long path's method**: not the three rules (§3.4–§3.6
of the experiment README), not the three enforcement patterns (§3.2), not the
test-design rules (§8), not the case template, not the playbook. The reason is
to find out whether that method helps the AI or limits it. If the two
solutions come out the same, the method costs nothing; if the short one is
better, the method is holding the AI back; if worse, the method is earning its
keep.

**The short path files no verdict.** It does not say whether the line is "a
case worth testing". It states the claim its own solution tests and designs
that test. Whether the two solutions agree, and how many tests they need, is
decided in stage 4 ([comparison](../../stage4-runtime-verification/README.md#solution-comparison)).

## What stays, and what goes

| Kept — objective and safety, not method | Dropped — method |
|---|---|
| The goal: does the constraint cap the node's memory or disk usage? | The three rules and three patterns |
| The pinned `cassandra-5.0.9` source | The six test-design rules and the §9 layout |
| Shared-infrastructure safety rules for stage 4 | The case template and the playbook |
| A minimal output skeleton ([`_TEMPLATE.md`](_TEMPLATE.md)), so the pair can be compared | Every filed case, every results file, `HANDOFF.md` |

**Scope: memory and disk.** CPU constraints are out of scope for now, matching
the experiment's resource scope (§3.3 of its README). Revisit if the
comparison shows the long path's Rule 2 excluded something real.

## Files

| File | Holds |
|---|---|
| [`BRIEF.md`](BRIEF.md) | The prompt the isolated agent receives, followed by `_TEMPLATE.md`, the entry pointer and one return instruction (see below). Self-contained: it links to nothing in this repo. |
| [`_TEMPLATE.md`](_TEMPLATE.md) | The output skeleton: A. constraint trace, B. verification solution, C. paths read. No verdict field. |
| [`isolation-test.py`](isolation-test.py) | The isolation test (canary) the runner executes before a writer run. It also holds the writer's exact CLI flags and the web allowlist: `python3 isolation-test.py --print-flags`. |
| [`_INDEX.md`](_INDEX.md) | One row per filed solution: stem, entry pointer, feed, filing date, sha256, model, isolation, leakage audit, comparison link. |
| [`cases/`](cases/) | The solutions, one file per case, named by the same stem as the long-path file. |

## Running a case — instructions for the AI session that runs it

**Three roles, never the same session.**

| Role | Who | May read | Must not |
|---|---|---|---|
| **Runner** (you, following this section) | any session | this README, `BRIEF.md`, `_TEMPLATE.md`, `_INDEX.md`, and the Cassandra source | edit the solution; put anything about the case into the prompt beyond the entry pointer; open the case's long-path file or any stage-4 file for it before the solution is filed |
| **Writer** | a fresh, isolated headless session you launch | the Cassandra source tree and nothing else | see anything else — the whole point of the path |
| **Comparator** | a later fresh session | both frozen solutions | have been the runner or the writer of either |

The runner may have read this repository; the writer must not have. That is
why the writer is a separate process whose file access you confine, not a
subagent of your own session.

### 0. Inputs

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

### 1. Prepare a clean workspace

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

### 2. Build the prompt

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

### 3. Isolation test — before the first run on a machine or CLI version, and whenever the flags or the allowlist change

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

### 4. Run the writer

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

### 5. Extract the solution and audit it

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

**Audit 3 — completeness.** Sections A1–A5, B1–B10 and C are all present, and
section C's paths are a subset of what the tool-call log shows. A solution with
a missing section is a failed run, not something to patch.

**A failed audit means discard and re-run** in a new attempt directory. Never
edit the solution, and never explain to the writer what went wrong. Keep the
failed attempt's directory and note it in the index row.

### 6. File and freeze

1. Copy `solution.md` to `cases/<stem>.md`. Fill in only the header table's
   *Session / date* row (model, CLI version, date, attempt number). Change
   nothing else.
2. `sha256sum cases/<stem>.md`.
3. Add the row to [`_INDEX.md`](_INDEX.md): stem, entry pointer, feed, date,
   sha256, model, isolation (the index cell the isolation test printed, for example `restricted+web (allowlist v1), canary pass, <CLI version>, <date>`; name any variant, below), audit
   (`pass`, or `fail` for a discarded attempt), comparison (`pending`).
4. Commit only when Jingsong asks. A filed solution is **never amended**; it
   has no feedback field.

### 7. Hand off

The comparison is stage 4's, by a fresh session
([Solution comparison](../../stage4-runtime-verification/README.md#solution-comparison)).
For a case that already has stage-4 results, the long side to compare is the
**frozen** version — §9's hash recorded in that case's results §1 — not the
later-amended §9c–e or §10, which carry measured outcomes.

## Limits of the standard run, and variants

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
short one. Only the stage-4 comparator reads both.

**Noise check (optional).** Running the short path twice on a case, filed as
`cases/<stem>--r2.md`, measures run-to-run variation, so a disagreement with the
long path is not mistaken for a difference between the paths.
