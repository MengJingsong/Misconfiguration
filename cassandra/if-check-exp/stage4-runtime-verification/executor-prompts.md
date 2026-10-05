# Prompts and pre-flight for stage-4 sessions of a two-path case

For a case that has both a long-path case file and a short-path solution
([README "Two paths, two tiers each"](README.md#two-paths-two-tiers-each)). A
session executing one path must stay blind to the other; this file holds the
pre-flight, the deny rules, and the prompts that enforce it. The worked case is
`memtable_heap_space-tryAllocate-limit`: substitute your own stem elsewhere.

## 1. Short-path executor (one case)

### 1.1 Pre-flight (you, once per case)

1. **The short solution is filed and committed.** Its row in
   [`../stage3-ai-deep-read/short-path/_INDEX.md`](../stage3-ai-deep-read/short-path/_INDEX.md)
   says `current`, and `sha256sum` of `cases/<stem>.md` equals the recorded value.
2. **Pick a node** and check access ([`environment.md`](environment.md) §7), for
   example `ssh -o BatchMode=yes jason92@pc80.cloudlab.umass.edu true`.
3. **Add the deny rules** (section 1.2) to `.claude/settings.local.json` in the
   repo root (local, never committed), then start the session **after** saving.
   Test them: in the new session ask it to read the first line of `HANDOFF.md`;
   it must be refused.
4. **Start a new session** in the repo. Do not continue any session that has read
   the long path, the case's results, or `HANDOFF.md`.

### 1.2 Deny rules

These block the file tools (Read, Grep, Glob) from the other path's files for
this case. They do **not** stop `cat` through Bash, so the prompt also forbids
it, and section 1.4 checks the session afterwards.

```json
{
  "permissions": {
    "deny": [
      "Read(//home/jingsong/repos/Misconfiguration/HANDOFF.md)",
      "Read(//home/jingsong/repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/long-path/**)",
      "Read(//home/jingsong/repos/Misconfiguration/cassandra/if-check-exp/stage4-runtime-verification/results/memtable_heap_space-tryAllocate-limit.md)",
      "Read(//home/jingsong/repos/Misconfiguration/cassandra/if-check-exp/stage4-runtime-verification/results/memtable_heap_space-tryAllocate-limit/**)",
      "Read(//home/jingsong/repos/Misconfiguration/cassandra/if-check-exp/stage4-runtime-verification/harness/memtable_heap_space-tryAllocate-limit/**)",
      "Read(//home/jingsong/repos/Misconfiguration/cassandra/if-check-exp/stage4-runtime-verification/comparison/**)"
    ]
  }
}
```

`HANDOFF.md` is blocked because it names the case's long-path finding. The
`--short` results and harness names do not match these patterns, so the
executor can create and read them.

### 1.3 The prompt

Give the new session this text, with the stem and node filled in.

```text
You are the stage-4 executor for the SHORT path of one case:
memtable_heap_space-tryAllocate-limit.

Read only:
- cassandra/if-check-exp/stage4-runtime-verification/README.md (the run protocol,
  "Two paths, two tiers each", and the safety rules), _TEMPLATE.md, environment.md
- cassandra/if-check-exp/stage3-ai-deep-read/short-path/cases/memtable_heap_space-tryAllocate-limit.md
  (your design: it is frozen, never edit it)
- the Cassandra source (clone it to local disk as the safety rules say).
Do not open, by any tool (Bash and ssh included), and do not look up in git
history: HANDOFF.md; anything under stage3-ai-deep-read/long-path/;
results/memtable_heap_space-tryAllocate-limit.md or its folder; harness/
memtable_heap_space-tryAllocate-limit/ (the one without --short); the
comparison/ folder. If you open one by accident, stop and say so in results §1.

Deliverables:
1. results/memtable_heap_space-tryAllocate-limit--short.md, from _TEMPLATE.md.
   In §1, list every file you opened from this repo ("Files read").
2. harness/memtable_heap_space-tryAllocate-limit--short/ for any code your runs
   need that is not upstream (a test class, a script).

Work tier by tier: the unit tier (B2) first, then the cluster tier (B3), each on
the full protocol in the README: audit for runnability and shared-node safety
only (do not apply the long path's design requirements A to C; note what they
would have flagged); record the hash of the solution file as the freeze; check
instruments; run 1, scripted and logged; conclusion matched against that tier's
own B2f/B2g (or B3f/B3g); self-check; verdict. A tier the solution declares n/a
is not run: say why. If a step cannot run as written, log a runbook defect in §3
and fix it in the harness; never edit the solution file.

Node: jason92@pc80.cloudlab.umass.edu. Use a fresh working directory ~/short-run
there. Do not open or reuse the other cases' directories on it (~/stage4-logs,
~/stage4-harness-run, ~/cassandra-run1, ~/cassandra-node2). Stop every process
you start and check none is left.

Do not commit or push. When both tiers are done (or you are blocked), stop and
report briefly: the verdict per tier, the runbook defects, and anything that needs
my decision.
```

### 1.4 After the session ends (you)

1. **Check the deliverables:** `results/<stem>--short.md` has a verdict row for
   each tier (or `not run: <reason>`) and a "Files read" list;
   `harness/<stem>--short/` exists if any code was needed.
2. **Check blindness** with [`check-blindness.py`](check-blindness.py). It scans the
   session transcript's tool calls (not the prompt, which names the blocked
   paths) for anything the short-path executor must not touch. It checks the
   newest transcript by default and prints that session's first prompt so you can
   confirm it is the executor's; pass `--transcript FILE` to choose one.

   ```bash
   python3 /home/jingsong/repos/Misconfiguration/cassandra/if-check-exp/stage4-runtime-verification/check-blindness.py --stem memtable_heap_space-tryAllocate-limit --for short
   ```

   Zero hits (exit 0) is the pass. A hit means that tier's result is contaminated:
   record it in the side-by-side, and rerun the tier in a fresh session if it
   mattered.
3. **Commit and push** (when you are satisfied): the results file, the harness
   folder, and any small log excerpts the template asks for.

## 2. Side-by-side writer

### 2.1 Pre-flight

Both paths' results are filed (the long path's already exist for the three closed
cases), and the short executor's work is committed. **Remove the deny rules**
from `.claude/settings.local.json` first: this session must read both paths'
results. Start a new session.

### 2.2 The prompt

```text
Write cassandra/if-check-exp/stage4-runtime-verification/comparison/
memtable_heap_space-tryAllocate-limit.md from comparison/_TEMPLATE.md, using
results/memtable_heap_space-tryAllocate-limit.md (long path) and
results/memtable_heap_space-tryAllocate-limit--short.md (short path). Report, rate
nothing; edit neither results file nor either solution. Add a line to
comparison/_INDEX.md. Do not commit or push.
```

## 3. Why these rules

The two paths are only comparable if neither executor saw the other's design or
readings. The short path in particular is meant to show what the AI does without
the long path's human method, so a short executor that had read the long path's
conclusions would measure nothing. The deny rules are the cheap structural
guard, the prompt the instruction, and the transcript check the audit; none of
the three is enough alone.
