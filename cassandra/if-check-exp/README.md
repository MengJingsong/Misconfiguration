# If-Check Experiment — Results Format

Structured results for **Target 1** (identify resource constraints) and
**Target 2** (show how each constraint restricts resource usage) of the
Throttling project, scoped to **Cassandra-5.0.9**.

## Project context (the three targets)

- **Target 1** — identify all resource constraints (config, hardcoded constants, variable types, etc.) that limit memory/CPU usage.
- **Target 2** — show *how* each constraint restricts usage, via the exact code path.
- **Target 3** — investigate bypass methods that could lead to resource exhaustion (not covered by this folder — see Scope below).

This folder captures **Target 1 + Target 2** at the granularity of a single
`if` statement: a standalone inventory of if-checks, independent of any
other experiment in this repo.

## Source of truth (version pinning — read this first)

Every `file:line` reference in these results is pinned to one exact source ref:

```
git clone --depth 1 --branch cassandra-5.0.9 https://github.com/apache/cassandra.git
```

**All line numbers are only valid for `apache/cassandra` @ tag `cassandra-5.0.9`.**
Before trusting or extending any case, check out that exact tag and re-verify the
lines — a different checkout (trunk, another patch release) will drift. Each case
file restates its source ref in the header for this reason.

### Verifying and linking against the local clone

Jingsong has a local copy of the pinned source on device `heisenberg-laptop`
(a `cassandra-5.0.9` tag download, not a live `git` checkout — its `.git`
directory is empty, so version is confirmed by content, not `git verify-tag`).
Use it instead of fetching whole files through GitHub — grep/window it, which
saves tokens versus pulling entire files into context.

- **Root mapping:** the download unpacks with a doubled folder name
  (`cassandra-cassandra-5.0.9/cassandra-cassandra-5.0.9/`) — the **inner**
  folder is the actual repo root (it directly contains `build.xml`,
  `CHANGES.txt`, `src/`, etc.). Everything below that inner folder maps
  1:1 onto the GitHub repo's paths.
- **Version confirmation:** `build.xml`'s `base.version` property and
  `CHANGES.txt`'s top entry both read `5.0.9`, confirming the content
  matches the pinned tag.
- **Building a link:** take the file's path **relative to that inner root**
  (e.g. `src/java/org/apache/cassandra/utils/memory/MemtablePool.java`) and
  splice it into `https://github.com/apache/cassandra/blob/cassandra-5.0.9/<that path>#L<NN>`
  (ranges: `#L<NN>-L<MM>`). Verify the line number by reading the local file
  itself, not by trusting a remembered offset.

## Core concept: the if-check case

An **if-check case** is a single `if` statement (or tight cluster of branches
implementing one decision) where:

- the compared operands are related to **object creation** (memory/resource
  allocation) on one side, and to a **capacity/constraint** (a limit, threshold,
  or counter cap — hardcoded or configured) on the other, and
- the two branches **genuinely diverge**: one branch proceeds to allow the
  object creation / resource acquisition, the other blocks, rejects, defers,
  or throws instead of creating it.

Checks that don't diverge this way (pure validation, logging-only branches,
null-guards unrelated to capacity) are out of scope — note them as "considered,
rejected" in `_INDEX.md` rather than writing a case file, so later passes don't
re-discover and re-reject the same line.

## Scope: what this folder does NOT cover

- **No bypass analysis, no failure-mode scoring.** Target 3 (bypass potential)
  and the proxy/enforcement-point/default failure-mode axes are out of scope
  here — this folder is purely a Target 1 + 2 inventory: what the check is,
  what it gates, and the path to the object it creates.
- **No cross-referencing other experiments.** This is a standalone inventory;
  it does not check for or note overlap with `entry-restriction-exp` or any
  other folder, even when a line number happens to coincide.

## Required content per if-check case

Every case file answers exactly these six questions (see `_TEMPLATE.md`):

1. **Location** — the if-statement's file:line, pinned to `cassandra-5.0.9`.
2. **Module** — which Cassandra module/subsystem this if-check belongs to
   (e.g. storage engine / memtable, native transport, compaction).
3. **Capacity-overflow check?** — is this comparing a counter/usage value
   against a limit (general capacity overflow), and if so, where is that
   limit initialized (its own short codepath: declared → configured/derived →
   stored → read at the check)?
4. **Branch semantics** — which branch allows object creation, which
   disallows it (quote the branch bodies).
5. **Code path to object creation** — the continuous trace from the
   allow-branch to the actual `new`/allocation call.
6. **Object & resource** — what is being created (type), and what resource
   it consumes (heap bytes, off-heap/native bytes, a thread, a queue slot,
   a file handle, etc.), including rough sizing if derivable from the code.

## Files per case

Each if-check case is **one file**, filed under the folder of the module it
belongs to (there is no single "entry point" to group by, so the module is
the grouping unit instead):

| File | Content |
|------|---------|
| `[limit]-[object].md` | All six required fields for one if-check case. Use `_TEMPLATE.md`. |

### Naming
- `<module>/` — a Cassandra module/subsystem folder used to *categorize*
  case files (e.g. `memtable`, `native_transport`, `compaction`), lowercase
  with underscores. Modules are not a precise or predefined taxonomy: if a
  new case doesn't fit an existing module folder, create a new module name
  for it — don't force-fit it into an existing one. When inventing a new
  module name, prefer a **broad** one over a narrow/specific one, so it can
  plausibly hold future cases too (e.g. `memtable` rather than
  `memtable_onheap_allocation`; `native_transport` rather than
  `native_transport_request_queue`).
- `[limit]` — the constraint being checked:
  - **Configuration-backed** → the config name, e.g. `memtable_heap_space`.
  - **Hardcoded or derived** → the limit declaration's **fully-qualified**
    `ClassName_fieldName`, including outer/inner class nesting, e.g.
    `MemtablePool_SubPool_limit`, `ExecutorPlus_DEFAULT_QUEUE_CAPACITY`.
- `[object]` — the type of object the allow-branch creates, lowercase with
  underscores (e.g. `bytebuffer`, `sstable_reader`, `connection`).
- **Collisions** — if two cases in the same module would produce the same
  `[limit]-[object]` name (e.g. the same limit gating the same object type
  at two different enforcement points), disambiguate with a short prefix or
  postfix rather than an index, e.g. `memtable_heap_space-bytebuffer-onheap.md`
  / `memtable_heap_space-bytebuffer-offheap.md`.
- **Case ID** — the filename stem (without `.md`) upper-cased, used in `_INDEX.md`.

### Directory layout

```
cassandra/if-check-exp/
├── README.md                     # this file
├── _INDEX.md                      # master index of every case (navigation + progress)
├── _TEMPLATE.md                    # template for each new case file
└── <module>/                       # one folder per Cassandra module
    ├── <limit>-<object>.md
    └── <limit>-<object>.md
```

## Workflow

**Orient (before starting):**

0. Read the Google Docs (*Meeting Summary*, *Progress Report*) for the current plan, scope, and next step.
1. Open `_INDEX.md` to see which modules/cases already exist (and which
   lines were considered and rejected) — continue from there, don't duplicate.

**Target 1 — discover candidate if-checks:**

2. Grep for comparisons (`<`, `>`, `<=`, `>=`, `==`) near identifiers
   containing `limit`, `threshold`, `capacity`, `max`, `size`, `count`,
   inside or near allocation-adjacent code. Prefer the local repo clone over
   fetching whole files through GitHub (grep/window it — saves tokens).
3. For each candidate, confirm the two branches actually diverge on object
   creation before writing a case file (see scope note above).

**Target 2 — trace & verify:**

4. Fill `<module>/[limit]-[object].md` from `_TEMPLATE.md`. If the limit side is
   config-derived, trace its short declare → configure → store → read
   sub-path; if hardcoded, just cite the constant's declaration.
5. Add/refresh the `_INDEX.md` row; set `Status` (`pending` →
   `in-progress` → `verified` once checked against the pinned tag **and**
   verified per [Verifying a case](#verifying-a-case-triggering-the-disallow-branch) below).

**Drafting convention:** draft new/changed case files in the Claude session
first for review, then push to `main` after approval.

## Verifying a case (triggering the disallow branch)

Line-number verification (above) confirms the citations are accurate — it
does **not** confirm the if-check actually behaves as described. A case only
earns `Status: verified` in `_INDEX.md` / the case file's Verification table
after a designed experiment has actually driven execution into the
**disallow branch** and produced observed evidence of it. Follow this before
flipping a case to `verified`:

1. **Don't assume the disallow branch "rejects" anything.** Trace what the
   disallow branch's caller actually does with a `false`/blocked result
   before designing a trigger — some checks throw or reject cleanly, but
   others only cause a retry, a block/wait, or (via an escape-hatch flag
   elsewhere in the call chain) get silently overridden and let the
   allocation through anyway. Design the experiment — and what you look for
   as "success" — around the check's real effect, not an assumed one.
2. **Prefer a deterministic single-shot trigger over a sustained-load race.**
   Where possible, size the limit smaller than what a single request/operation
   needs, so the very first attempt deterministically hits the disallow
   branch — rather than relying on write/allocation throughput outracing
   whatever reclaims capacity (flush, cleanup thread, GC), which is racy and
   harder to reproduce.
3. **Check whether the limit/pool is global or scoped.** Some limits are
   per-connection or per-table; others are a single process-wide static
   instance shared across all callers. For a shared/global limit, an
   experiment against one table/connection isn't isolated from unrelated
   background activity — run it on a dedicated single-node instance (or
   otherwise control for other traffic) rather than a shared/loaded cluster.
4. **Choose the right level for the trigger:**
   - **Unit/programmatic level** (preferred first pass when feasible) —
     construct the relevant class(es) directly in a small program or test
     (check `test/unit/...` for existing coverage of the class first; reuse
     or extend it rather than writing a new harness from scratch) and drive
     it straight to the boundary condition. Fast, deterministic, no cluster
     needed, and lets you assert/breakpoint at the exact check.
   - **Live-cluster / end-to-end level** — exercise the check through a real
     Cassandra node (e.g. via `cqlsh`, `nodetool`, or a client program) with
     config pushed to the boundary. Needed to confirm the check is actually
     reachable and behaves the same way in the full system, not just in
     isolation — do this in addition to, not instead of, a unit-level check
     where one is practical.
5. **Capture direct evidence the specific if-check fired**, not just a
   symptom that could have other causes (a hang or an error alone isn't
   proof — several things can hang or error). Depending on what's available
   for the check in question:
   - An assertion or breakpoint in a unit test at the exact line.
   - A JMX metric, counter, or log line that only fires from this check's
     disallow branch (confirm this by reading the source around the check —
     don't assume one exists).
   - A thread/stack dump showing execution parked or returned from the exact
     method/line of the disallow branch.
6. **Record the experiment in the case file** (config used, the test/program
   used to trigger it, and the evidence observed) before setting
   `Status: verified` — the goal is that a later session can re-run the same
   trigger and get the same result, not just trust the checkmark.

## Related context (for a new session)

- **Google Docs** — *Meeting Summary* and *Progress Report* hold the current plan and next steps; read them first (the Claude project is configured to surface them).
