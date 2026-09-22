# If-Check Experiment — Results Format

Structured results for **Target 1** (identify resource constraints) and
**Target 2** (show how each constraint restricts resource usage) of the
Throttling project, scoped to **Cassandra-5.0.9**.

## 1. Project context (the three targets)

- **Target 1** — identify all resource constraints (config, hardcoded constants, variable types, etc.) that limit memory/CPU usage.
- **Target 2** — show *how* each constraint restricts usage, via the exact code path.
- **Target 3** — investigate bypass methods that could lead to resource exhaustion (not covered by this folder — see §4).

This folder always captures **Target 1 + Target 2 together**: every case both
*finds* a constraint and *shows* how it restricts usage. The direction is
enforcement-first — discovery starts from the code that enforces a limit (a
capacity check), and the constraint itself is found by tracing the limit
back to where it is first declared (§5, question 4). A case is not complete
until both halves are recorded.

This folder is a standalone inventory of capacity checks and the decision
points they feed, at the granularity of individual code locations.

## 2. Source of truth (version pinning — read this first)

Every `file:line` reference in these results is pinned to one exact source ref:

```
git clone --depth 1 --branch cassandra-5.0.9 https://github.com/apache/cassandra.git
```

**All line numbers are only valid for `apache/cassandra` @ tag `cassandra-5.0.9`.**
Before trusting or extending any case, check out that exact tag and re-verify the
lines — a different checkout (trunk, another patch release) will drift. Each case
file restates its source ref in the header for this reason.

### 2.1 Verifying and linking against the local clone

The pinned source is kept as a real git clone at
`/proj/misconfiguration-PG0/git-repos/cassandra-src` (tag `cassandra-5.0.9`;
see the root `README.md` §2). On another machine, create your own with the
`git clone` command above. Use the clone instead of fetching whole files
through GitHub — grep/window it, which saves tokens versus pulling entire
files into context.

- **Root mapping:** the clone's root is the repo root (it directly contains
  `build.xml`, `CHANGES.txt`, `src/`, etc.), so every path in it maps 1:1
  onto the GitHub repo's paths.
- **Version confirmation:** `git describe --tags` prints `cassandra-5.0.9`.
  Independently, `build.xml`'s `base.version` property and `CHANGES.txt`'s
  top entry both read `5.0.9`. If a copy has no usable `.git` (for example a
  tag tarball), confirm by those two files.
- **Building a link:** take the file's path **relative to that root** (e.g.
  `src/java/org/apache/cassandra/utils/memory/MemtablePool.java`) and splice
  it into `https://github.com/apache/cassandra/blob/cassandra-5.0.9/<that path>#L<NN>`
  (ranges: `#L<NN>-L<MM>`). Verify the line number by reading the local file
  itself, not by trusting a remembered offset.

## 3. Core concept: the if-check case

The purpose of this folder is to find **resource constraints that limit
memory or disk usage**, and to show **how the code enforces each one**. A
candidate qualifies only if it passes all three rules in §3.4–§3.6.

### 3.1 Capacity check, decision point, allocation site

Every case has three code locations. They may coincide (pattern (a) below)
or be far apart (patterns (b) and (c)):

- **Capacity check** — the comparison of a usage-side operand (current
  consumption) against a limit-side operand. It can sit in an `if`
  condition, a ternary, an assignment, or a `return` expression; it does not
  have to be an `if` statement. This is where the limit-side operand lives,
  so it anchors the case's file name (§6.1).
- **Decision point** — the statement whose outcome actually differs between
  allow and disallow: an `if`/`else`, a guard clause that throws or returns,
  or a caller that branches on a returned verdict. This is where creation is
  withheld, deferred or rejected.
- **Allocation site** — the code that creates the memory- or disk-significant
  object (`new`, `ByteBuffer.allocate(...)`, a file write, and so on).

### 3.2 Enforcement patterns

How the capacity check's verdict reaches the allocation falls into three
patterns. Every case records which one it is.

- **(a) The check is the decision.** The capacity check is itself the `if`
  whose allow branch leads to the allocation and whose disallow branch
  withholds it. The disallow branch may be empty or implicit (skip the
  allocation), but its outcome must still be observable (Rule 3).
- **(b) The check produces a verdict; a separate decision point reads it.**
  The comparison sets a boolean flag or enum status (or returns a
  boolean/enum outcome), and another statement — often in a different
  method, class or thread — tests that verdict and branches. The verdict's
  path (who writes it, who reads it, what can reset it) must be traced. The
  decision point may itself depend on configuration.
- **(c) The allocation is not inside a branch.** One or more guard clauses
  before the allocation `throw` or `return` early when the limit is
  exceeded; the allocation is the fall-through. The allow "branch" is
  implicit, so a case must show that the allocation is dominated by the
  guard (every path to it passes the guard) and record any path that
  reaches it without passing the guard.

### 3.3 Resource scope: memory and disk

Disk was added to this folder's scope on 2026-09-18; before that it was
memory-only. A case whose limit-side operand bounds total on-disk bytes
(SSTable data, commitlog segments, hint files, and so on), gating creation of
an on-disk object, qualifies the same way a memory case does — read
"memory" as "memory or disk" throughout the rules. Lines rejected before
that date specifically because they were disk-related are worth revisiting;
they are flagged inline in `_INDEX.md`'s rejected table rather than
silently re-triaged.

### 3.4 Rule 1 — Identify the capacity check and its limit-side operand

The capacity check compares a usage-side operand (current consumption)
against a limit-side operand. The limit-side operand must represent a
**capacity/constraint** — a limit, threshold, or counter cap, whether
hardcoded, configured, or queried at runtime (for example a device's free
space). This names the candidate constraint; it is not by itself a pass/fail
test — Rules 2 and 3 are.

### 3.5 Rule 2 — Allocation creates memory- or disk-significant objects, gated by that operand

The gated allocation creates an object (or acquires a resource) whose
memory **or disk** footprint is non-negligible, and the limit-side
operand's value directly bounds the **maximum total memory or disk bytes**
such object creation can consume — not just the *rate*, *concurrency*, or
*throughput* at which existing allocations/writes happen.

**Test:** if the limit-side operand's configured value changes, does the
maximum bytes resident in memory (heap or off-heap) *or* the maximum bytes
written/held on disk change as a direct consequence?

- **Valid (memory)** — the limit is compared against a byte count, buffer
  size, or a count of objects whose per-object footprint is fixed/derivable
  (so total bytes = count × size). Example: `memtable_heap_space` bounds
  the bytes a `HeapPool` can hold; raising it lets more `ByteBuffer`s be
  allocated.
- **Valid (disk)** — the limit is compared against on-disk bytes (available
  disk space, an SSTable/segment size cap, a total-on-disk-data ceiling) and
  directly gates whether an on-disk object (SSTable, commitlog segment,
  hint file, etc.) gets written. Example: a write-directory selection check
  that compares `availableSpace` against `estimatedWriteSize` before
  allowing a compaction/flush writer to target that directory.
- **Reject** — the limit is a thread-pool size, worker/task concurrency cap,
  or a throughput/rate limiter. Example: `concurrent_compactors` bounds how
  many compactions run in parallel; raising it changes *speed*, not the
  total bytes any single compaction task allocates or writes.
- **Edge case — queue/buffer depth:** don't reject on "it's a queue" alone.
  If each queued slot holds a memory-significant object (e.g. buffered
  write bytes), queue depth is a memory limit in disguise and total bytes
  held does scale with it → valid. If each slot just holds a lightweight
  task reference (a lone `Runnable`/pointer), the memory difference across
  depths is negligible → reject, same reasoning as thread-pool size.
- **Edge case — writer rollover vs. rejection:** a check that triggers
  starting a *new* file/segment/writer once the current one is full (e.g.
  "if this SSTable would exceed `maxSSTableSize`, switch to a new writer")
  does **not** qualify — the write proceeds either way, just split across
  more files; total bytes written aren't bounded by this check, only how
  they're chunked. This applies equally to memory (`CommitLogSegment.java:242`,
  `HintsBuffer.java:190`) and disk (per-file size-triggered writer switches)
  — see Rule 3.

This rule also carries this folder's deliberate scoping choice: it narrows
Target 1's "memory/CPU usage" (see §1) to **memory and disk usage**
specifically. CPU-limiting constraints (thread-pool sizes, concurrency
caps, rate limiters) are still valid Target 1 material, just not
inventoried here.

### 3.6 Rule 3 — The decision point must withhold that object creation, verifiably

The verdict of the capacity check must reach a decision point whose outcome
differs, with respect to object creation, between allow and disallow — a
clean reject/throw, a deferred/blocked creation, or (at minimum) a change in
accounting/caller state — as opposed to the object being created
identically regardless of the verdict. This is what makes the operand's
limiting effect real and checkable, rather than decorative: it confirms
the check is an enforcement mechanism, not just a comparison that happens to
run near an allocation.

For pattern (a) the decision point is the check itself. For pattern (b) the
verdict's path to the decision point must be traced: which code writes the
flag/enum or returns the outcome, which code reads it, and whether anything
resets it or ignores it. For pattern (c) the guard must dominate the
allocation.

**What fails this rule:** a decision point with *zero* observable effect —
object creation happens unconditionally whatever the verdict, with no
difference in state, timing, or accounting. That check isn't actually
gating anything, even if it looks like it should.

**Note the exact effect can vary** — don't assume "disallow" means "clean
reject." The disallow outcome can permanently reject, defer/block the caller
until capacity frees up, or only change accounting/caller state while an
escape hatch elsewhere still lets the allocation through (in
`native_transport_receive_queue_capacity`'s case, even by default). Tracing
which of these applies is exactly the first step of
[§8 Verifying a case](#8-verifying-a-case-triggering-the-disallow-branch) —
applying that same "trace the real effect, don't assume" discipline at
candidate-discovery time is what Rule 3 is asking for.

Checks that don't pass all three rules (pure validation, logging-only
branches, null-guards unrelated to capacity, non-diverging outcomes, rate/
concurrency limits, etc.) are out of scope — note them as "considered,
rejected" in `_INDEX.md` rather than writing a case file, noting which rule
they failed, so later passes don't re-discover and re-reject the same line.

## 4. Scope: what this folder does NOT cover

- **No bypass analysis, no failure-mode scoring.** Target 3 (bypass potential)
  and the proxy/enforcement-point/default failure-mode axes are out of scope
  here — this folder is a Target 1 + 2 inventory: what the constraint is,
  what enforces it, and the path to the object it gates. Bypass-relevant
  observations made along the way (escape hatches, default-mode gaps) are
  noted in the case file's Verification notes for later Target-3 use, not
  chased down here.
- **No cross-referencing other experiments.** This is a standalone inventory;
  it does not check for or note overlap with `entry-restriction-exp` or any
  other folder, even when a line number happens to coincide.

## 5. Required content per if-check case

Every case file answers exactly these eight questions (see `_TEMPLATE.md`):

1. **Location** — the three locations from §3.1 (capacity check, decision
   point, allocation site), each as `file:line` pinned to `cassandra-5.0.9`,
   and which enforcement pattern (§3.2) the case follows: (a), (b) or (c).
2. **Context** — a short, high-level description of what this if-check does
   and why it exists, written so that any computer-science researcher
   unfamiliar with Cassandra internals can understand the case at a glance —
   no line numbers or code, just the functional gist (e.g. "this check
   throttles how much unflushed write data a node can buffer in memory
   before forcing writers to wait, so a slow disk can't let memory grow
   without bound").
3. **Module** — which Cassandra module/subsystem this if-check belongs to
   (e.g. storage engine / memtable, native transport, compaction).
4. **Capacity check & limit** — is this comparing a counter/usage value
   against a limit (general capacity overflow), and if so, where is that
   limit initialized (its own short codepath: declared → configured/derived →
   stored → read at the check)? This is the Target 1 half of the case: the
   first declaration on this path names the resource constraint.
5. **Decision point & branch semantics** — the decision point (`file:line`, same as question 1), then: for pattern (a), which branch allows object
   creation and which disallows it (quote the branch bodies). For (b), what
   the verdict is (flag/enum values or return outcomes), where it is set, and
   the decision point's two outcomes. For (c), the guard and what it throws
   or returns.
6. **Code path** — two subsections:
   - **(a) Allow path → object creation** — the continuous trace from the
     allow outcome to the actual `new`/allocation call.
   - **(b) Disallow path effect** — what actually happens when the verdict is
     "disallow" (reject / throw / block-and-wait / defer / a silent bypass
     elsewhere in the call chain) — trace the real effect before assuming it
     cleanly rejects anything, per
     [§8](#8-verifying-a-case-triggering-the-disallow-branch) step 1. For
     patterns (b) and (c), include the verdict's propagation from the
     capacity check to the decision point.
7. **Object & resource** — what is being created (type), and what resource
   it consumes (heap bytes, off-heap/native bytes, on-disk bytes, a thread,
   a queue slot, a file handle, etc.), including rough sizing if derivable
   from the code.
8. **Maximum memory/disk bound** — a plain statement of how the value of the
   limit-side operand (question 4) affects maximum memory or disk usage
   (whichever question 7 identifies): if this value is raised or lowered,
   what happens to the maximum bytes the system can hold or write via this
   check, and through what mechanism? This goes beyond
   the per-object sizing in question 7 — it's about the limit's effect on
   the ceiling, not just what one allowed object costs.

## 6. Files per case

Each case is **one file**, filed under the folder of the module it belongs
to (there is no single "entry point" to group by, so the module is the
grouping unit instead):

| File | Content |
|------|---------|
| `[constraint]-[function]-[operand].md` | All eight required fields for one case. Use `_TEMPLATE.md`. |

### 6.1 Naming

- `<module>/` — a Cassandra module/subsystem folder used to *categorize*
  case files (e.g. `memtable`, `native_transport`, `compaction`), lowercase
  with underscores. Modules are not a precise or predefined taxonomy: if a
  new case doesn't fit an existing module folder, create a new module name
  for it — don't force-fit it into an existing one. When inventing a new
  module name, prefer a **broad** one over a narrow/specific one, so it can
  plausibly hold future cases too (e.g. `memtable` rather than
  `memtable_onheap_allocation`; `native_transport` rather than
  `native_transport_request_queue`).
- `[constraint]` — the **resource constraint name**: the variable that is
  *first declared/initialized* along the limit initialization path (§5,
  question 4), verbatim:
  - **Configuration entry** → the config name, e.g. `memtable_heap_space`.
  - **JVM system property** → the property's declaring variable, e.g.
    `MAX_HINT_BUFFERS` (`CassandraRelevantProperties`).
  - **Constant / hardcoded variable** → the declaring variable's name,
    qualified with its outer/inner class only if the bare name is
    ambiguous, e.g. `ExecutorPlus_DEFAULT_QUEUE_CAPACITY`.
  - **Runtime-queried limit with no declared variable** → the accessor
    method that supplies it, e.g. `DataDirectory_getAvailableSpace`.
  - **Derived from several sources** → the primary one (the one a user
    would tune); mention the others in §5 question 4.
- `[function]` — the name of the method that directly encloses the
  **capacity check** (§3.1; for pattern (a) that is the if-statement),
  no class prefix, verbatim, e.g. `tryAllocate`, `acquireCapacity`,
  `processNewSegment`. The exact `Class.method():line` of all three
  locations is recorded in the case file's §1 and in `_INDEX.md`.
- `[operand]` — the limit-side operand's name exactly as written at the
  capacity check (§5, question 4), e.g. `limit`, `queueCapacity`,
  `allowance`, `MAX_ALLOCATED_BUFFERS`.
- Names are joined with hyphens as `[constraint]-[function]-[operand].md`
  (hyphens never occur inside Java identifiers or config names). Keep each
  part's original casing.
- **One case, several check sites** — if one constraint is compared at more
  than one place feeding the same decision point (for example a state set at
  creation and re-evaluated later), file one case named after the primary
  check site and list the others in the case's Location section.
- **Collisions** — if a new case would produce the same file name as an
  existing one, the **first (existing) file keeps its name unchanged** — it is
  never renamed, so no existing reference changes — and only the
  **newcomer** gets a numeric postfix `-2` (a third gets `-3`, and so on), e.g.
  `memtable_heap_space-tryAllocate-limit.md` (existing, untouched) /
  `memtable_heap_space-tryAllocate-limit-2.md` (new). The object created is not
  part of the file name; it's the `Object` column in `_INDEX.md` and §5
  question 7.
- **Case ID** — the filename stem (without `.md`) upper-cased, recorded in each case file's header table (`Case ID`). `_INDEX.md` has no Case column; its `File` link identifies the case.

### 6.2 Directory layout

```
(repo root)/HANDOFF.md              # start-here brief for a new session: what this experiment is, current state, next steps
cassandra/if-check-exp/
├── README.md                     # this file
├── _INDEX.md                      # master index of every case (navigation + progress)
├── _TEMPLATE.md                    # template for each new case file
├── candidates/                      # method 2, stage-2 (AI filtering) verdicts — see §7.2
│   ├── README.md                    #   what stage 2 is, and which batches have been read
│   ├── positives.md                 #   survivors, pending promotion to a case file
│   ├── negatives.md                 #   read and refused, each citing the rule it failed
│   └── deferred.md                  #   not yet judged: parked by the pattern-(a)-only scope (§7.5)
└── <module>/                       # one folder per Cassandra module
    ├── <constraint>-<function>-<operand>.md
    └── <constraint>-<function>-<operand>.md
```

## 7. Workflow

### 7.1 Orient (before starting)

1. Read [`../../HANDOFF.md`](../../HANDOFF.md) first — it's the start-here
   brief for a new session (what this experiment is, current state, open
   items) — then the Google Docs (*Meeting Summary*, *Progress Report*) for
   the current plan, scope, and next step.
2. Open `_INDEX.md` to see which modules/cases already exist (and which
   lines were considered and rejected) — continue from there, don't duplicate.

### 7.2 Discover candidate capacity checks (Target 1)

Two discovery methods are in use. They are complementary, not alternatives —
both feed the same case files, and both are subject to the same three rules
(§3.4–§3.6).

**Method 1 — direct AI search.** An AI session reads the Cassandra source
directly, following subsystems and call chains, and identifies real if-check
cases end to end without any mechanical pre-filter. This is how the folder's
first cases were found. Its strength is that it follows semantics a
structural query can't express (it found the `cdc_total_space` ternary that
the CodeQL pipeline structurally cannot surface). Its weakness is cost and
coverage: the full source is far more than one session can read, so coverage
is opportunistic rather than systematic, and it places a heavy burden on the
reading session. Rejections found this way are recorded in `_INDEX.md`'s
"lines considered and rejected" section.

**Method 2 — CodeQL + AI preprocessing.** A two-stage pipeline that exists to
relieve method 1's burden by shrinking what has to be read:

- **Stage 1 — mechanical filtering (CodeQL).** The queries under
  [`codeql-queries/cassandra/queries/if-check-exp/`](../../codeql-queries/cassandra/queries/if-check-exp/README.md)
  narrow ~17k `if` statements structurally (no keyword list) down to a
  candidate set. Results are written to the **gitignored**
  `codeql-queries/results/cassandra/` and regenerated per machine; nothing
  about a result set is committed or pinned.
- **Stage 2 — AI filtering.** An AI session reads stage 1's rows against the
  three rules and sorts each into positive, negative or deferred, recording
  the verdicts under `candidates/` (see §6.2). Survivors are then promoted to
  full case files.

The point of method 2 is that stage 1 + stage 2 *filter out* the invalid
candidates cheaply, so the expensive per-case work of method 1 is spent only
on the positives.

**Where rejections live (one line, one place).** Method 1's rejections go in
`_INDEX.md`; method 2's go in `candidates/negatives.md`. They are kept apart
because they differ in kind — method 1's are few, narrative, and often
deferred-rather-than-refused; method 2's are bulk, per-batch, one line each
citing the rule failed. A line is recorded in exactly one of the two: if
stage 2 reaches a line method 1 already judged, cite the `_INDEX.md` entry
rather than re-recording it.

Then, for either method:

3. Use the CodeQL pipeline under
   [`codeql-queries/cassandra/queries/if-check-exp/`](../../codeql-queries/cassandra/queries/if-check-exp/README.md)
   to mechanically narrow the code down to candidate capacity checks, then
   read the results and judge each one by hand for capacity/memory- or
   disk-relatedness — deliberately no fixed keyword list (real cases like
   `memtable_heap_space` don't share predictable vocabulary), so this is a
   read-and-judge pass over CodeQL's structural narrowing, not a grep.
   CodeQL only shrinks the search space; it does not decide what qualifies.
   Prefer the local repo clone over fetching whole files through GitHub when
   reading a candidate's surrounding code (grep/window it — saves tokens).
4. For each candidate, identify which enforcement pattern (§3.2) applies and
   locate the decision point and the allocation site. Judge the candidate by
   whether the verdict reaches a decision point that diverges on object
   creation (Rule 3) — not only by whether the comparison's own branches
   diverge, since under patterns (b) and (c) they may not.

### 7.3 Trace & verify (Target 2)

5. Fill `<module>/[constraint]-[function]-[operand].md` from `_TEMPLATE.md`. If the limit side is
   config-derived, trace its short declare → configure → store → read
   sub-path (this names the constraint, completing Target 1 for the case); if
   hardcoded, just cite the constant's declaration.
6. Add/refresh the `_INDEX.md` Master Index row (columns: Constraint name, Capacity check,
   Decision point, Module, Object, Pattern, Status, File); set `Status` (`pending` →
   `in-progress` → `verified` once checked against the pinned tag **and**
   verified per [§8](#8-verifying-a-case-triggering-the-disallow-branch)).

### 7.4 Drafting convention

Draft new/changed case files in the Claude session first for review, then
push to `main` after approval.

### 7.5 Active scope decision (2026-09-22): pattern (a) only

**Candidate triage is currently restricted to enforcement pattern (a)** — the
capacity check is itself the `if` whose branches decide allow vs. disallow
(§3.2). Patterns **(b)** and **(c)** are *parked, not descoped*: how to
handle them systematically is still an open question, so they are left
untouched rather than half-done, and **they resume once pattern (a) is
finished**. Their rules in §3.2 stand unchanged in the meantime.

- **Stage 1 already fits this scope with no changes.**
  `NarrowedIfStatements.ql` selects numeric magnitude comparisons whose
  enclosing statement is an `if` — structurally exactly pattern (a). The
  three planned structural queries (comparisons anywhere, guard clauses,
  verdict links) exist only to surface (b)/(c) and are not prerequisites for
  the pattern-(a) pass. Two residual gaps to note: the query captures the
  *form* only, so Rule 3 (do the branches actually diverge?) remains entirely
  a stage-2 judgment; and a pattern-(a) check whose comparison hides behind a
  boolean helper (`if (!pool.hasRoom())`) keeps its comparison in the callee
  and so will not appear — stage 1 is a near-complete superset for (a), not a
  provably complete one.
- **Rows that would qualify only under (b) or (c) go to
  `candidates/deferred.md`, never to `negatives.md`.** They are unjudged, not
  refused; keeping them in a separate file means resuming (b)/(c) is a matter
  of reading one file rather than re-scanning the corpus.
- **Already-filed cases are unaffected.** This governs new candidate triage
  only; existing case files keep their recorded pattern, including the four
  pattern-(b) cases.

**Verification is also deferred (2026-09-22).** The §8 "trigger the disallow
branch" step is not being run for now; cases are filed with their citations
checked against the pinned tag and left at `Status: pending` until
verification resumes. §8 stands unchanged as the methodology for when it
does.

## 8. Verifying a case (triggering the disallow branch)

Line-number verification (§2.1) confirms the citations are accurate — it
does **not** confirm the check actually behaves as described. A case only
earns `Status: verified` in `_INDEX.md` / the case file's Verification table
after a designed experiment has actually driven execution into the
**disallow path** and produced observed evidence of it. For patterns (b) and
(c) the evidence must show the capacity check produced the disallow verdict
*and* the decision point reacted to it. Follow this before flipping a case to
`verified`:

1. **Don't assume the disallow path "rejects" anything.** Trace what the
   decision point's caller actually does with a `false`/blocked result
   before designing a trigger — some checks throw or reject cleanly, but
   others only cause a retry, a block/wait, or (via an escape-hatch flag
   elsewhere in the call chain) get silently overridden and let the
   allocation through anyway. Design the experiment — and what you look for
   as "success" — around the check's real effect, not an assumed one.
2. **Prefer a deterministic single-shot trigger over a sustained-load race.**
   Where possible, size the limit smaller than what a single request/operation
   needs, so the very first attempt deterministically hits the disallow
   path — rather than relying on write/allocation throughput outracing
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
5. **Capture direct evidence the specific check fired**, not just a
   symptom that could have other causes (a hang or an error alone isn't
   proof — several things can hang or error). Depending on what's available
   for the check in question:
   - An assertion or breakpoint in a unit test at the exact line.
   - A JMX metric, counter, or log line that only fires from this check's
     disallow path (confirm this by reading the source around the check —
     don't assume one exists).
   - A thread/stack dump showing execution parked or returned from the exact
     method/line of the decision point.
6. **Record the experiment in the case file** (config used, the test/program
   used to trigger it, and the evidence observed) before setting
   `Status: verified` — the goal is that a later session can re-run the same
   trigger and get the same result, not just trust the checkmark.

## 9. Related context (for a new session)

- **Google Docs** — *Meeting Summary* and *Progress Report* hold the current plan and next steps; read them first (the Claude project is configured to surface them).
