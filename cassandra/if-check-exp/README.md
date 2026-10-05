# If-Check Experiment — Results Format

Structured results for **Target 1** (identify resource constraints) and
**Target 2** (show how each constraint restricts resource usage) of the
misconfiguration project, scoped to **Cassandra-5.0.9**.

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

### 1.1 Targets vs. stages — two unrelated numberings

**The three targets above are project scope**, shared by every experiment
folder in this repo (`if-check-exp`, `entry-restriction-exp`, ...). They say
*what the project wants to know*.

**The stages (§7.2) belong to `if-check-exp` alone.** They say *how strongly
a line has been evidenced* — stage 1 structural, stage 2 lexical, stage 3
semantic. They are a ladder of evidence, not a division of the targets.

The two numberings do not correspond. In particular:

- **Stages 1 and 2 produce no target output at all.** They emit no findings,
  only a shrunken and ordered worklist. **Only stage 3 produces a case**, and
  a case completes Target 1 and Target 2 *together* — it names the constraint
  and shows the enforcing code path in one artifact.
- **There is no stage matching Target 3.** Bypass analysis is out of scope
  for this folder (§4). Bypass-relevant observations noticed during stage 3
  are noted in the case file for later Target-3 use, but are not pursued
  here, and no stage number implies otherwise.

So: three targets, project-wide, answering *what*; three stages, this folder
only, answering *how well evidenced*. A case is the point where they meet.

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
they are flagged inline in `stage3-ai-deep-read/long-path/_INDEX.md`'s rejected table rather than
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
which of these applies — "trace the real effect, don't assume it rejects" —
is exactly what Rule 3 is asking for, and the first pitfall in
[`stage3-ai-deep-read/long-path/playbook.md`](stage3-ai-deep-read/long-path/playbook.md).

Checks that don't pass all three rules (pure validation, logging-only
branches, null-guards unrelated to capacity, non-diverging outcomes, rate/
concurrency limits, etc.) are out of scope — note them as "considered,
rejected" in `stage3-ai-deep-read/long-path/_INDEX.md` rather than writing a case file, noting which rule
they failed, so later passes don't re-discover and re-reject the same line.

## 4. Scope: what this folder does NOT cover

- **No bypass analysis, no failure-mode scoring.** Target 3 (bypass potential)
  and the proxy/enforcement-point/default failure-mode axes are out of scope
  here — this folder is a Target 1 + 2 inventory: what the constraint is,
  what enforces it, and the path to the object it gates. Bypass-relevant
  observations made along the way (escape hatches, default-mode gaps) are
  noted in the case file's Notes for later Target-3 use, not chased down
  here.
- **No cross-referencing other experiments.** This is a standalone inventory;
  it does not check for or note overlap with `entry-restriction-exp` or any
  other folder, even when a line number happens to coincide.

## 5. Required content per if-check case

Every case file answers exactly these nine questions (see `stage3-ai-deep-read/long-path/_TEMPLATE.md`):

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
     cleanly rejects anything (see
     [`stage3-ai-deep-read/long-path/playbook.md`](stage3-ai-deep-read/long-path/playbook.md)).
     For patterns (b) and (c), include the verdict's propagation from the
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
9. **Test design** — how stage 4 should test this case: which knob changes the
   constraint, at least three capacity values to try, the usage-side
   observable and how to read it, the workload that drives it, how to *just
   reach* and how to *try to exceed* capacity, the dose-response predicted
   before the run, what each outcome would mean, and what would refute the
   case. Written as guidance for someone else to execute — stage 3 designs
   the test and never runs it (§8, §7.5).

## 6. Files per case

Each case is **one file**, all of them together in
`stage3-ai-deep-read/long-path/cases/` — stage 3's positive output, filed with the
stage that produced it:

| File | Content |
|------|---------|
| `stage3-ai-deep-read/long-path/cases/[constraint]-[function]-[operand].md` | All nine required fields for one case. Use `stage3-ai-deep-read/long-path/_TEMPLATE.md`. |

**The layout is flat; the module is a field, not a folder.** Cases were once
filed under per-module directories; that was flattened 2026-09-23 because the
file name is already fully qualified and the module is recorded as `Module`
in the case file (§5, question 3) and as a column in `_INDEX.md`, which is
where grouping belongs. Module naming guidance below still applies to that
field.

### 6.1 Naming

- **Module** (a *field*, not a folder — see §6) — the Cassandra
  module/subsystem a case belongs to (e.g. `memtable`, `native_transport`,
  `compaction`), lowercase with underscores. Modules are not a precise or
  predefined taxonomy: if a new case doesn't fit an existing module name,
  invent one — don't force-fit it. Prefer a **broad** name over a narrow one,
  so it can plausibly hold future cases too (e.g. `memtable` rather than
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
  locations is recorded in the case file's §1 and in `stage3-ai-deep-read/long-path/_INDEX.md`.
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
  part of the file name; it's the `Object` column in `stage3-ai-deep-read/long-path/_INDEX.md` and §5
  question 7.
- **Case ID** — the filename stem (without `.md`) upper-cased, recorded in each case file's header table (`Case ID`). `stage3-ai-deep-read/long-path/_INDEX.md` has no Case column; its `File` link identifies the case.

### 6.2 Directory layout

```
(repo root)/HANDOFF.md       # start-here brief for a new session
cassandra/if-check-exp/
├── README.md                # this file: rules, format, the three stages
├── stage1-codeql-preprocessing/   # structural narrowing — see §7.2
│   └── README.md            #   pointers to codeql-queries/, output, blind spot
├── stage2-ai-preprocessing/       # lexical narrowing, rows only — see §7.2
│   ├── README.md            #   what stage 2 is, how a row is triaged, progress
│   ├── playbook.md          #   start here to run a batch: bands, procedure
│   ├── bands.md             #   every row banded A-D = stage 3's 3a queue
│   └── bands.csv            #   the per-row verdicts
├── stage3-ai-deep-read/           # semantic qualification — the deciding stage
│   ├── README.md            #   what stage 3 is, its two feeds, where verdicts go
│   ├── playbook.md          #   how to run a pass: order of checks, pitfalls
│   ├── _TEMPLATE.md         #   template for a new case file (stage 3's output)
│   ├── _INDEX.md            #   master index of every case (cases only)
│   ├── rejected.md          #   read with source open, refused against the rules
│   ├── deferred.md          #   the (b)/(c) worklist — unjudged, now live (§7.5)
│   ├── pending.md           #   qualified, not yet written up as a case
│   └── cases/               #   THE RESULTS — flat, one file per case
│       ├── <constraint>-<function>-<operand>.md
│       └── <constraint>-<function>-<operand>.md
└── stage4-runtime-verification/   # audits and runs the §9 designs — AI only, no human gate
    └── README.md            #   the feedback contract: what it consumes/emits
```

Everything stage 3 produces — the cases, their index, the template, and its
rejected/deferred verdicts — lives in `stage3-ai-deep-read/`, matching the
rule that a verdict is filed with the stage that made it (§7.2).

## 7. Workflow

### 7.1 Orient (before starting)

1. Read [`../../HANDOFF.md`](../../HANDOFF.md) first — it's the start-here
   brief for a new session (what this experiment is, current state, open
   items) — then the Google Docs ([*Meeting Summary*](https://docs.google.com/document/d/1tldFFEk28qtQD0QdsnC2Br-BisTyOUp8OCwG1SZ_6Jk/edit),
   [*Progress Report*](https://docs.google.com/document/d/1gMRFwaTvgahSiRi10ad_Y3CLDkxyF1QTYkAhZ4be4x8/edit)) for the current plan, scope, and next step.
2. Open `stage3-ai-deep-read/long-path/_INDEX.md` to see which modules/cases already exist (and which
   lines were considered and rejected) — continue from there, don't duplicate.
### 7.2 Discover and qualify candidate capacity checks

Work proceeds in **three stages, numbered by evidence standard** — how
strongly a line has been evidenced — **not by position in a pipeline**. A
higher stage is a stronger kind of evidence, not a later step in a chain, and
**a stage can be entered directly**. See §1.1 for why these numbers have
nothing to do with the Target numbers.

| Stage | Evidence | Reads source? | Decides? | Folder |
|---|---|---|---|---|
| **1** | Structural — the shape of the code (CodeQL) | queries the DB | no | [`stage1-codeql-preprocessing/`](stage1-codeql-preprocessing/README.md) |
| **2** | Lexical — operand, class, method and package *names* | **no** | no | [`stage2-ai-preprocessing/`](stage2-ai-preprocessing/README.md) |
| **3** | Semantic — the code itself, against the three rules | yes | **yes** | [`stage3-ai-deep-read/`](stage3-ai-deep-read/README.md) |
| **4** | Behavioral — manual review and a running cluster | *(planned)* | *(planned)* | — not created |

**Stage 3 is the only stage that decides whether something is a real case.**
Stage 2 only orders what stage 3 must read, and produces no findings of its
own; stage 1 narrows structurally before it.

**Stage 4 runs the experiment; stage 3 designs it.** Reserved 2026-09-23 and
opened 2026-09-25: each case file's §9 is a test design written for stage 4 to
execute, and stage 4 reports back
([`stage4-runtime-verification/README.md`](stage4-runtime-verification/README.md)).
Nothing in this folder runs anything, and no case here carries a measured
number — see §7.5.

#### Stage 1 — structural preprocessing (CodeQL)

Narrows ~17k `if` statements structurally — **no keyword list** — to a
worklist. Results are **gitignored** under `codeql-queries/results/cassandra/`
and regenerated per machine; nothing about a result set is committed or
pinned.

Stage 1 sees structure only, and has a known blind spot: a check written as a
ternary, assignment, `return` expression or method argument is invisible to
it at all. Details and the query pointers are in
[`stage1-codeql-preprocessing/README.md`](stage1-codeql-preprocessing/README.md).

#### Stage 2 — lexical preprocessing (rows only)

An AI session works **only from the stage-1 rows** — operand names, enclosing
class and method, package, operator class — **without reading the Cassandra
source**. It does **one** thing:

> **Rank every stage-1 row by how likely it is to become a valid case**, by AI
> lexical and semantic judgement of the row's text.

Each row gets one of four bands — **A** reads as a real capacity check, **B**
plausibly a resource bound, **C** named operands with nothing resource-shaped
(the insurance band), **D** clearly not one — plus a one-line reason. The
banded rows are stage 2's result and stage 3's queue, in
`stage2-ai-preprocessing/bands.md`.

**No fixed keyword list and no mechanical pre-filter (2026-09-23).** The
banding is the AI's reading of the row, start to finish. This is what this
section's "deliberately no fixed keyword list" rule always implied.

**Stage 2 rules nothing out (2026-09-23).** A row that looks impossible takes
the bottom rank; it is never removed from the queue. A rule-out is permanent
and invisible, while a bad rank costs a little reading and self-corrects as
stage 3 works down the list. The rule-outs made before this decision were
held in a `negatives.md` in that folder, closed the same day and deleted on
2026-09-24; those rows carry band D in `bands.csv` instead.

Which CSV a row came from, whether it compares by magnitude or equality, and
whether its comparison hides behind a boolean helper are reading order and
technique — not further stages.

**Stage 2 is preprocessing, not qualification.** It does **not** apply the
three rules in §3.4–§3.6. Rule 3 in particular ("does the verdict reach a
decision point that diverges on object creation?") cannot be answered from a
row — it needs the branches read.

**Because stage 2 cannot see the source, it ranks and never rejects.** A
wrong rejection is permanent and invisible — nothing re-reads a rejection —
while a wrong promotion costs only a little reading later. When in doubt,
downrank; band D is the bottom of the order, not a bin. See
[`stage2-ai-preprocessing/README.md`](stage2-ai-preprocessing/README.md).

#### Stage 3 — AI deep read (semantic qualification)

An AI session takes the ranked rows in order and, for each one, **deep-reads
its context** — tracing backward to where the limit and the usage come from,
forward to where the verdict is consumed, and out into whatever related
Cassandra code the answer depends on. It applies the three rules (§3.4–§3.6)
and the three enforcement patterns (§3.2): it identifies the pattern, locates
the decision point and the allocation site, and judges whether the verdict
reaches a decision point that diverges on object creation (Rule 3) — not only
whether the comparison's own branches diverge, since under patterns (b) and
(c) they may not. Prefer the local clone over fetching whole files through
GitHub (grep/window it — saves tokens).

It then **designs the test** that would confirm or refute the case — §9 of the
case file, written as guidance for stage 4 to execute (§8).

**What stage 3 extracts are candidate cases, not settled findings.** A case
file records a traced code path checked against the pinned tag, plus a test
design. Confirming it still needs **manual review and runtime verification**,
which happen in [stage 4](stage4-runtime-verification/README.md), not here
(§7.5). A filed case is complete *as stage-3 evidence*, not as a verified
result — and it carries no measured numbers.

**Stage 3 has two feeds, and both are required:**

| Feed | Points stage 3 at a line via | Coverage | Progress measurable? |
|---|---|---|---|
| **3a** | `stage2-ai-preprocessing/bands.md`, band A first | bounded, enumerable | **yes** |
| **3b** | the session's own reading of subsystems and call chains | unbounded, opportunistic | **no** — no denominator |

**3b is not optional.** It is the standing insurance against stage 1's
*syntactic* blind spot — it found the `cdc_total_space` ternary, which stage 1
cannot surface at all because the comparison is not in an `if` condition. Record the feed (`3a`/`3b`) on every case and
every verdict; without it, "stage 3 progress" has no coherent answer.

Method, pitfalls and the order to work a row:
[`stage3-ai-deep-read/long-path/playbook.md`](stage3-ai-deep-read/long-path/playbook.md). How to
write the test design: §8.

#### Where verdicts live — filed by the stage that judged

Not by the stage that surfaced the row. A row **stage 2 ranked** and
**stage 3 then read and refused** is a *stage-3* rejection.

| | Stage 2 verdict | Stage 3 verdict |
|---|---|---|
| Evidence | the row alone, source unread | the source, against the three rules |
| Qualified | *(cannot qualify)* | a case file in `stage3-ai-deep-read/long-path/cases/`, indexed in `stage3-ai-deep-read/long-path/_INDEX.md` |
| Ranked | `stage2-ai-preprocessing/bands.md` — every row, banded A–D | *(n/a)* |
| Rejected | *(cannot reject — bottom rank instead)* | `stage3-ai-deep-read/long-path/rejected.md` |
| Deferred | *(cannot defer — see below)* | `stage3-ai-deep-read/long-path/deferred.md` |

**Stage 2 cannot produce a pattern-(b)/(c) deferral.** Deciding a line "would
qualify only under (b) or (c)" means tracing where the verdict is read and
whether the branches diverge, which no row shows. All deferrals are stage-3
judgments.

A line is recorded in exactly one place. If stage 2 reaches a line stage 3
already judged, cite the stage-3 entry rather than re-recording it.

### 7.3 Write up the case

3. Fill `stage3-ai-deep-read/long-path/cases/[constraint]-[function]-[operand].md` from `stage3-ai-deep-read/long-path/_TEMPLATE.md`. If the limit side is
   config-derived, trace its short declare → configure → store → read
   sub-path (this names the constraint, completing Target 1 for the case); if
   hardcoded, just cite the constant's declaration.
4. **Verify every `file:line` against the local clone before filing** (§2.1).
   This is a stage-3 exit condition, not a tracked state: a case is not filed
   until its citations are checked.
5. Add/refresh the `stage3-ai-deep-read/long-path/_INDEX.md` Master Index row (columns: Constraint name,
   Capacity check, Decision point, Module, Object, Pattern, Feed, File), and
   record the stage-3 feed (`3a`/`3b`) in the case's Notes.

### 7.4 Drafting convention

Draft new/changed case files in the Claude session first for review, then
push to `main` after approval.

### 7.5 Active scope decisions (revised 2026-09-25)

Two decisions govern this folder's boundaries. Both were changed on
2026-09-25 by Jingsong; what they replaced is recorded at the end of each.

#### All three enforcement patterns are in scope

Candidate triage covers patterns **(a)**, **(b)** and **(c)** (§3.2). A row is
read, the pattern identified, and the three rules applied — with no pattern
filter and no parking.

- **Nothing new is needed to start.** The existing stage-1 corpus already
  contains (b) and (c) candidates, and stage 2's banding was
  pattern-agnostic — it ranked whether a row *reads as a capacity check*, not
  where its decision sits. So band A is directly readable under all three
  patterns.
- **What stage 1's filter actually selects.** `NarrowedIfStatements.ql`
  selects numeric magnitude comparisons whose enclosing statement is an `if`.
  That is a **syntactic** filter — comparison inside an `if` — and it spans
  all three patterns, which are defined by *where the decision sits relative
  to the comparison*, not by syntax. Two parked candidates prove it: the
  pattern-(b) check at
  [`Directories.java:551`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L551)
  is an ordinary `if` whose branch sets `hasSpace = false` (stage 2 surfaced
  it from the corpus), and pattern-(c) guard clauses such as
  [`TrackedDataInputPlus.checkCanRead():184`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TrackedDataInputPlus.java#L184)
  *are* `if` statements. **Corrected 2026-09-25:** this section and
  `stage3-ai-deep-read/long-path/deferred.md` §3 previously called that filter
  "structurally exactly pattern (a)" / "precisely pattern (a)". That was
  wrong, and it understated the corpus.
- **The real gap is narrower, and it is about syntax.** A comparison written
  as a ternary, an assignment, a `return` expression or a method argument is
  invisible to the current queries. Such a comparison cannot be pattern (a)
  — (a) requires the comparison's own `if` — so every miss of this kind is a
  (b) or (c) check. The known instance is the `cdc_total_space` ternary,
  found by direct reading. The implication runs one way only: *not in an `if`
  ⟹ (b) or (c)*, **never** *(b)/(c) ⟹ not in an `if`*.
- **Consequently the three unwritten queries are not blockers.** Of the three
  specified in the [CodeQL pipeline README](../../codeql-queries/cassandra/queries/if-check-exp/README.md):
  "comparisons anywhere" closes the only genuine *coverage* gap; "guard
  clauses" and "verdict links" are **precision aids**, since (c) guards and
  flag-setting (b) checks are already in the corpus. None gates the band-A
  pass.
- **`deferred.md` is now a live worklist, not a parking lot.** Its entries —
  `hasDiskSpaceForCompactionsAndStreams`, `column_index_cache_size`,
  `TrackedDataInputPlus_limit` — are queued for reading, and its §2 re-audit
  of rejections made under the old (a)-only assumption is scheduled rather
  than parked.
- **Expect (b)/(c) rows to cost more to judge.** Rule 3 under (b) needs the
  verdict's path traced to its reader; under (c) it needs domination checked
  across callers. The compaction case is the precedent: establishing that the
  guard *does not* dominate meant reading the callers, and non-domination is a
  finding to record, not grounds for rejection.

*Replaces the decision of 2026-09-22, which restricted triage to pattern (a)
and parked (b)/(c) as "not descoped, resuming once (a) is finished". (b)/(c)
resume now instead. Already-filed cases are unaffected — they keep their
recorded pattern.*

#### Stage 3 designs the test; stage 4 runs it

A case file's §9 is a **test design**: guidance for stage 4, covering which
knob moves the constraint, the capacity values to try, the observable and its
instrument, how to just-reach and how to exceed, the predicted dose-response,
and what would refute the case. Method: §8.

| | Stage 3 | Stage 4 |
|---|---|---|
| Evidence | the source, against the three rules | a measured run |
| Test | designs it (§9) | executes it, and reports back |
| Records measured numbers? | **never** | yes, in its own folder |
| Needs a cluster or build? | no | yes |

**This keeps the folder's rule intact.** A test design is derivable from the
traced code path alone, so writing one needs no cluster, no build and no run —
the property that made verification a separate stage in the first place.
What stage 3 still must not do is *execute* anything, or record a measured
number, or call a case verified. **There is no `Status` field**, and a filed
case is complete as stage-3 evidence, not as a verified result.

**Feedback returns, and can refute a case.** Stage 4 reports measurements into
[`stage4-runtime-verification/`](stage4-runtime-verification/README.md); a
refutation of the traced path amends the case file itself, dated and citing
the run. Each case's §10 carries a **Stage-4 feedback** field, "none yet" until
then. Two things a case still needs: **design verification** (stage 4's AI
design audit checks the proposal against the requirements in its README and
spot-checks the load-bearing citations; revised 2026-09-30, previously "a person
reads the traced path and agrees") and **runtime verification** (execution
actually driven into the disallow branch). **No step of stage 4 waits for a
human**; Jingsong may overrule a verdict at any time.

*Replaces the decision of 2026-09-23, under which test design as well as
execution sat outside this folder. Design moves in; execution stays out.
Earlier trigger designs and the one executed test are recoverable from
`git show e7f9963:HANDOFF.md` — note the `:HANDOFF.md` suffix, since that
commit's own diff is an unrelated folder rename.*

## 8. Designing a test for a case

Stage 3 writes a design; [stage 4](stage4-runtime-verification/README.md) runs
it. The design's purpose is to make the case **falsifiable**: it states, before
any run, what should be observed if the traced path is the binding limit, and
what would show it is not.

### 8.1 The shape of the experiment

**Vary the constraint, and at each capacity value drive usage to the boundary
twice** — once to just reach it, once to try to exceed it. The constraint is
the dose; peak resource usage is the response. A single-point test can only say
"the disallow branch fired"; a sweep says whether the constraint actually
governs the ceiling, which is what Target 2 is claiming.

- **At least three capacity values, including the default.** Two points cannot
  distinguish a linear response from a coincidence.
- **"Just reach" establishes the knob moves the ceiling.** Usage ≈ capacity
  here in nearly every case; the scenario is a control, not the finding.
- **"Try to exceed" carries the information**, and what it shows depends
  entirely on §6b's real disallow effect — which is why §6b must be traced
  before the design is written.

### 8.2 The six rules

Recovered from this folder's earlier verification methodology (2026-09-16 to
09-22) and still the method:

1. **Don't assume the disallow path rejects anything.** Trace what the
   decision point's caller actually does with a `false`/blocked result before
   designing anything — some checks reject or throw cleanly, others only
   retry, block and wait, or get silently overridden by an escape-hatch flag
   further down the chain. Design the experiment, and what counts as
   "expected", around the real effect.
2. **Prefer a deterministic single-shot trigger over a sustained-load race.**
   Size the capacity below what one operation needs, so the first attempt
   deterministically lands on the boundary, rather than relying on
   allocation throughput outracing whatever reclaims capacity (flush, cleanup
   thread, GC) — which is racy and hard to reproduce.
3. **Check whether the limit is global or scoped, before believing the case
   is about total memory.** A per-connection, per-table or per-file cap bounds
   one object's share, not the node's ceiling: node-wide usage moves by
   `limit × N`, so the design must say what N is and how to hold it steady.
   For a process-wide pool, an experiment on one table is not isolated from
   background activity — use a dedicated single-node instance.
4. **Choose the level, and prefer both.** They answer different questions.
   - **Unit/programmatic** — construct the classes directly and drive them to
     the boundary. Fast, deterministic, no cluster, and it can assert at the
     exact line. Check `test/unit/...` for existing coverage of the class and
     extend it rather than writing a harness from scratch. This tier measures
     the *operand*, which proves the mechanism.
   - **Live cluster** — push config to the boundary and drive the check
     through a real node. This tier measures *actual memory or disk*, which is
     what the dose-response claim is about. Needed to confirm the check is
     reachable and behaves the same in the full system.
5. **Capture direct evidence that this check fired**, not a symptom with other
   possible causes — a hang or an error alone proves nothing. An assertion at
   the exact line, a metric or log line reachable only from this disallow path
   (confirm by reading the source; don't assume one exists), or a thread dump
   parked at the decision point.
6. **Write the design so it can be run without re-deriving the code path**,
   and so a later session re-running it gets the same result: the knob, the
   values, the workload, the commands, and what to record.

### 8.3 Measuring the resource

**Instrument the check's own usage-side operand — not process RSS.** §4 already
names that operand. If it is exposed, read it; if it is not, name the proxy and
state the gap, because a proxy that moves for other reasons is a confounder
rather than a measurement.

A verified example of that gap: the pool-wide `allocated` counter that
`MemtablePool.SubPool.tryAllocate()` compares is **not exposed as a metric** —
a grep of `src/java/org/apache/cassandra/metrics/` finds no `MemtablePool`
gauge. `TableMetrics` offers `allMemtablesOnHeapDataSize` /
`allMemtablesOffHeapDataSize`
([`TableMetrics.java:93-95`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TableMetrics.java#L93-L95)),
which are per-table proxies for a node-wide counter. Checked 2026-09-25.

Pick the external instrument from §7's "Resource consumed":

| Resource | Instrument | Trap |
|---|---|---|
| On-heap bytes | Cassandra metrics over JMX / `nodetool`; heap after a forced full GC via `jcmd <pid> GC.heap_info` | Process RSS is useless — `-Xms` pre-commits the heap and GC timing masks the live set |
| Off-heap / native bytes | JVM Native Memory Tracking: `-XX:NativeMemoryTracking=summary`, then `jcmd <pid> VM.native_memory summary`; RSS as a cross-check | NMT must be enabled at JVM start, so it belongs in the node's jvm options before the run |
| On-disk bytes | `du -sb` on the data / commitlog / cdc / hints directory, **sampled over time** | The final size is not the peak — compaction or segment recycling erases the evidence |

Load generation: `cassandra-stress` ships in the distribution's `tools/bin/`
(confirmed present in the pinned clone) and can hold concurrency steady via
`-rate threads=`, which rule 3 needs for a per-connection cap. A small CQL
client is better where the payload size must be exact.

**Limits that cannot be varied by config.** §4's "Limit type" already
classifies these: a hardcoded constant or a type bound such as
`Integer.MAX_VALUE` needs a patched build to move at all. Record that in §9's
Testability field rather than leaving stage 4 to discover it on the cluster.

### 8.4 Reading the result

A design must predict **both** curves, or it cannot tell a bypass from noise:

| Observation when trying to exceed | Reading |
|---|---|
| Usage pinned at the ceiling; rejections, parks or exceptions rise as §6b predicts | The check enforces as traced. |
| Usage climbs past the ceiling | The §6b escape hatch or non-domination dominates. Target-3 material, and §8 of the case needs amending. |
| Usage flat across every capacity value | The traced path is **not** the binding limit — stage 3 misread it. The case needs re-reading, not a re-run. |

Two filed cases already predict the second row: `memtable_heap_space`
overshoots via `markBlocking()`, and the compaction disk guard is skipped
entirely on the default `diskBoundaries != null` path. On those, a constraint
that fails to govern usage is the *expected* result.

**Controls are not optional.** A baseline at default config and an idle run are
the minimum; background compaction, GC timing and unrelated traffic on a shared
global pool can all move an observable on their own.

## 9. Related context (for a new session)

- **Google Docs** — [*Meeting Summary*](https://docs.google.com/document/d/1tldFFEk28qtQD0QdsnC2Br-BisTyOUp8OCwG1SZ_6Jk/edit) (per-meeting decisions and next steps) and [*Progress Report*](https://docs.google.com/document/d/1gMRFwaTvgahSiRi10ad_Y3CLDkxyF1QTYkAhZ4be4x8/edit) (running log of entry points, cases and findings). Both live in Jingsong's Google Drive; a session with the Google Drive connector enabled can read them directly.
