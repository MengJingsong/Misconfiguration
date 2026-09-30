# [constraint] — [object]  <!-- file name: [constraint]-[function]-[operand].md -->

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

**Formatting note:** Link every code reference (`` `File.java:NN` `` or `` `Class.method():NN` ``) to the pinned source on GitHub. Use the format: `` [`File.java:NN`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/<path>#LNN) `` (ranges use `#LNN-LMM`). Place the link *outside* the backticks so code renders as clickable text.

**Relative links in this template** (`../_INDEX.md`, `../../README.md`) are written for
where a *copy* of it lives — inside `cases/` — **not** for the template's own location one
level up. They look wrong here and resolve correctly in a real case file. When checking
links repo-wide, resolve this file's relative links against `cases/`, not against its own
directory: skipping the file instead hides real breakage (that is how these two links went
stale through the 2026-09-23 folder moves).

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | filename stem upper-cased, e.g., MEMTABLE_HEAP_SPACE-TRYALLOCATE-LIMIT |
| **Constraint** | the resource constraint name (first part of the file name) and its source: configuration entry / JVM system property / constant / runtime-queried accessor (README §6.1) |
| **Enforcement pattern** | (a) the check is the decision / (b) the check sets a verdict (flag, enum, return value) that a separate decision point reads / (c) guard clause(s) before an allocation that is not inside a branch — see [README.md §3.2](../../README.md#3-core-concept-the-if-check-case) |
| **Capacity check** | [`Class.method():NN`](GitHub link) — the usage-vs-limit comparison (names the file: `[constraint]-[function]-[operand].md`). List any additional check sites feeding the same decision point. |
| **Decision point** | [`Class.method():NN`](GitHub link) — where allow and disallow diverge (same as the capacity check for pattern (a)) |
| **Allocation site** | [`Class.method():NN`](GitHub link) — where the memory/disk-significant object is created |
| **Related cases** | links to sibling cases sharing the same check code or constraint (e.g. heap/off-heap variants), or "none" |

```java
// paste the capacity check and, if different, the decision point (enough surrounding context to read both outcomes)
```

## 2. Context

_High-level, non-code description of what this if-check does and why it
exists — written so any computer-science researcher unfamiliar with
Cassandra internals can understand the case at a glance. One short
paragraph: what mechanism this is part of, what problem it solves, what
would go wrong without it. No line numbers, no code snippets here — those
come later._

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | e.g., storage engine — memtable allocation (`utils/memory`, `db/memtable`) |
| **One-line role** | what this module does in Cassandra, one sentence |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | yes / no / partial — one sentence why |
| **Usage-side operand** | the variable tracking current consumption (e.g. a counter, `allocated` bytes) |
| **Limit-side operand** | the variable/constant being compared against |
| **Limit type** | Configuration entry / JVM system property / Hardcoded constant / Runtime-queried (accessor method) / Derived (computed from other config) |

**Limit initialization path** (short — declare → configure/derive → store → read at the check; cite line numbers; if hardcoded, just the declaration):

1. [`Class.field():NN`](link) — declared
2. [`Class.method():NN`](link) — configured / derived / validated
3. [`Class.method():NN`](link) — stored where the check reads it from
4. [`Class.method():NN`](link) — read at the point of comparison

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`Class.method():NN`](GitHub link) — where allow and disallow diverge (repeat the §1 entry in full; same as the capacity check for pattern (a)) |
| **Verdict** | patterns (b)/(c): the flag/enum/return value or guard — name, where it is set, where it is read; pattern (a): "n/a — the check is the decision" |

For pattern (b), first state the verdict (flag/enum values or return outcomes), where it is set, and where it is read; for (c), the guard and what it throws or returns.

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow** | e.g. `used + size <= limit` | proceeds to allocate / create the object |
| **Disallow** | e.g. `used + size > limit` | blocks / rejects / defers / throws instead |

```java
// allow-outcome body
```

```java
// disallow-outcome body
```

## 6. Code path

### 6a. Allow path → object creation

Continuous trace from the allow outcome to the actual allocation call. For patterns (b) and (c), include how the verdict travels from the capacity check to the decision point.

1. [`Class.method():NN`](link) — allow branch taken, state updated (e.g. counter incremented / CAS)
2. [`Class.method():NN`](link) — returns to caller
3. [`Class.method():NN`](link) — caller proceeds to allocate
4. [`Class.method():NN`](link) — **object creation** (`new ...` / `ByteBuffer.allocate(...)` / etc.)

### 6b. Disallow path effect

What actually happens when the disallow verdict fires — trace the real
effect before assuming it cleanly rejects anything (the first pitfall in
[`../playbook.md`](../playbook.md)). Is it a clean reject/throw? A block-and-wait? A silent
bypass/escape hatch elsewhere in the call chain?

1. [`Class.method():NN`](link) — disallow branch taken, what state (if any) changes
2. [`Class.method():NN`](link) — what the caller does with the rejected/blocked result

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | type/class |
| **Resource consumed** | heap bytes / off-heap bytes / on-disk bytes / thread / queue slot / file handle / etc. |
| **Rough sizing** | how the size is derived, if determinable from the code (e.g. `size` param, fixed struct size) |
| **Lifetime / release** | what releases this resource back to the pool/limit (brief) |

## 8. Maximum memory/disk bound

State plainly how the value of the limit-side operand (§4) affects maximum
memory or disk usage (whichever §7 identifies as the resource): if it's
raised or lowered, what happens to the maximum bytes the system can hold
or write via this check, and through what mechanism? Goes beyond §7's
per-object sizing — this is about the limit's effect on the ceiling, not
what one allowed object costs.

## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it.** It carries **no
measured numbers and no verdict** — those are stage 4's, and where they land is
set out in
[`../../stage4-runtime-verification/README.md`](../../stage4-runtime-verification/README.md).
Method and pitfalls: [README.md §8](../../README.md#8-designing-a-test-for-a-case).

**Two audiences.** The intro and 9a are for a **human reader**: what the test
does and what each result would mean, readable on their own. 9b–9e are the
**runbook**: steps a person or an AI session can follow on a Linux machine.
**Stage 4 audits this section before any run**, against four groups of
requirements (the core question, step-by-step logic, specificity, runnability) in
[`../../stage4-runtime-verification/README.md`](../../stage4-runtime-verification/README.md#step-0--the-design-audit);
write to them.

_In a case file, keep this intro to two or three lines: what the test does,
and the state of any run already done. Then delete this note and the writing
rules below — they guide the case writer and belong only in the template._

**Writing rules:**

- **State each fact once.** Settings live in 9b, conclusions in 9a; other
  subsections point to them rather than restating them.
- **Commands are copy-pasteable**, with `<placeholders>` in angle brackets and
  paths relative to the Cassandra clone root.
- **Source links only in 9b–9e**, and only where a setting is not obvious or a
  trap needs justifying. The intro and 9a have none.
- **Shared setup is linked, not copied** — JDK, `ant`, building the clone, and
  the generic instruments in [README.md §8.3](../../README.md#83-measuring-the-resource).
- **Delete what does not apply** (a tier, scenario C, a row) instead of writing
  "n/a".

### 9a. Procedure and conclusions

**Testability:** config, live-settable / config, restart-only / JVM system
property / **needs patched build** (say what to patch) / not settable. State
this first: it decides whether the case is worth a cluster allocation at all.

**Claim under test:** one sentence — which limit bounds which resource, and
what the disallow outcome does (from §6b and §8).

**How this verifies the hypothesis:** four to eight lines, placed here so a
reader sees the argument before the steps. It restates the claim, procedure,
prediction and conclusions below and adds no claim of its own; every line must
match them. Four parts:

- **Hypothesis:** the constraint caps this resource (memory or disk bytes), and
  what the disallow outcome does.
- **Test:** the knob varied, the values, how usage is driven to the limit and
  past it, and what is measured (the real resource, not only the check's counter).
- **Logic:** the readings in order, each with what it shows. Normally: the limit
  is reached (else the run is invalid); usage stops at the limit; usage follows
  the constraint when the knob changes; the disallow branch, not something else,
  is what enforces it. Where the knob cannot be varied, say what replaces the
  sweep and why.
- **Refuted if:** the readings that would show the constraint does not cap usage
  (rows of the Conclusions table).

**Procedure:**

1. **Unit tier** — drive the check to its limit. Assert the allow outcome at the
   limit and the §6b disallow effect one step past it.
2. **Cluster tier** — set up as in 9b and run every capacity value.
3. **At each capacity value:** control run → **scenario A**, reach the limit →
   **scenario B**, try to exceed it → **scenario C**, the bypass arm (only if
   §6b or §10 records a bypass: an escape hatch, an unguarded path, or a
   setting that turns the check off).
4. **Compare** with the prediction below and read the result in the table.

**Prediction:** how the ceiling should move with the knob if the traced path is
the binding limit (for example proportional, or `limit × N` for a scoped
limit), what the disallow effect looks like from outside, and — if a bypass is
recorded — how far usage should go in scenario C.

**Conclusions.** Adapt the wording to this case, delete rows that cannot
occur, and keep the **Refuted** rows explicit: they are what stage 4's feedback
settles.

| Result | Conclusion |
|---|---|
| Usage stops at the limit, disallow evidence appears, and the ceiling moves with the knob | **Confirmed** — the check enforces as traced. |
| Usage passes the limit, and the recorded bypass accounts for all of the excess | **Bypass as recorded** — expected, not a refutation. Record its size (Target-3 material). |
| Usage passes the limit, and no recorded bypass explains it | **Refuted** — the check does not cap usage. |
| The usage counter stays capped, but the real resource keeps growing | **Refuted** — the counter does not track the resource; §8's ceiling claim is wrong. |
| The ceiling does not move with the knob | **Refuted** — not the binding limit. Re-read, do not re-run. |
| The ceiling moves, but there is no disallow evidence | **Not confirmed** — something else derived from the same limit may be binding. Re-read. |
| The limit is never reached | **Invalid run** — fix the setup (9b, 9c) and re-run. |

Two rules behind this table:

- **A confirmation needs both** the ceiling moving with the knob **and** direct
  evidence that the disallow branch fired (README §8.2 rule 5). A curve alone
  can come from another mechanism derived from the same limit.
- **If a bypass is recorded, say how an overshoot will be attributed to it** —
  a measurement of how much went through the bypass (9d), or an arm in which
  the bypass cannot fire. Without one, "bypass" and "does not cap" look the
  same.

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | The exact thing to change and how: `cassandra.yaml` entry, `-D` system property, JMX/`nodetool` setter, or the `DatabaseDescriptor` setter a unit test calls. Name it as §4's limit path names it. Say whether a change needs a restart. |
| **Confirm it took effect** | How to read back the value actually in force (a startup log line, a `nodetool` or JMX read, a unit-test assertion). |
| **Capacity values** | At least three, including the default, with units. If the limit is derived rather than used raw, give the capacity each value produces, and what else must be pinned for that to hold. |
| **Scope** | Global, or per table / connection / host / file. For a scoped limit, give the multiplier N (node-wide usage moves by `limit × N`) and how to hold N steady. |
| **Level** | Unit, cluster, or both. Name any existing test under `test/unit/...` that already reaches this check. |

**Hold fixed** — every setting that must not change across the sweep, stated
once here:

| Setting | Value | Why |
|---|---|---|
| `<setting>` | `<value>` | one line: what it would confound |

**Controls:** a baseline at the default configuration and an idle run are the
minimum; add any case-specific control.

**Reset between runs:** how to return to a clean state (stop the node, clear
the relevant data directories, restart).

### 9c. Workload

What pushes the usage side toward the limit: the operation, the payload size,
the concurrency, and what releases capacity at the same time. Prefer a
**deterministic single-shot trigger** — a capacity smaller than one operation
needs — over a throughput race (README §8.2 rule 2).

```bash
# unit tier
ant testsome -Dtest.name=<fully.qualified.TestClass>
# cluster tier: load tool or small client, with its exact options
<command>
```

### 9d. Observables

One row per observable. Delete the bypass row if no bypass is recorded.

| Observable | How to read it (command) | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — §4's usage-side operand | … | … | … |
| **Disallow evidence** — a signal only the disallow path produces | … | … | … |
| **Bypass volume** — how much went through the recorded bypass | … | … | … |
| **Real resource** — heap, off-heap or disk bytes (README §8.3) | … | … | … |

If the usage counter is not exposed, name the proxy and state the gap
plainly: a proxy that moves for other reasons is a confounder, not a
measurement. Before relying on a disallow signal, confirm from the source that
no other path produces it.

### 9e. Running the scenarios

For each run below, list the steps in order as commands, what to record, and
when to stop. What a result means belongs in 9a, not here.

1. **Control run** — …
2. **Scenario A — reach the limit** — …
3. **Scenario B — try to exceed the limit** — …
4. **Scenario C — bypass arm** (only if a bypass is recorded) — …

**Record for stage 4:** the configuration in force, the exact commands, and the
raw readings from 9d for every run.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3a` (from stage 1/2 — cite the `bands.md` row and its band) or `3b` (found by reading the source directly — say which subsystem/call chain led here) |
| **Filed by / Date** | Who wrote this case up and when |
| **Line numbers checked** | date each cited line was checked against the local pinned-tag clone (`git describe --tags` = `cassandra-5.0.9`) — a case is not filed until this is done |
| **Escape hatch / Target-3 note** | any bypass of the disallow branch noticed (flag for Target 3, do not chase here), or "none found yet" |
| **Stage-4 feedback** | "none yet" until stage 4 reports. Then: a link to its results entry, and — if the feedback corrected anything above — which section was amended and when. Measured numbers stay in stage 4's file; they are not copied here. |
| **Notes** | Any other caveats or outstanding questions |

---

## 11. Notes

- _Add any additional context, edge cases, or version-specific behavior._
