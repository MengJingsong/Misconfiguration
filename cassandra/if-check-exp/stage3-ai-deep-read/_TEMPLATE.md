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

**Stage 3 writes this section; stage 3 never runs it.** This is executor-facing
guidance: everything stage 4 needs to run the experiment without re-deriving
the code path above. It carries **no measured numbers and no verdict** — those
are stage 4's, and where they land is set out in
[`../../stage4-runtime-verification/README.md`](../../stage4-runtime-verification/README.md).
Method and pitfalls: [README.md §8](../../README.md#8-designing-a-test-for-a-case).

| Field | Content |
|-------|---------|
| **Testability** | Config-testable / JVM system property / **Needs patched build** (hardcoded constant or type bound — say what to patch) / Not settable. State this first: it decides whether the case is worth a cluster allocation at all. |
| **Constraint knob** | The exact thing stage 4 changes, and how: `cassandra.yaml` entry, `-D` system property, or the `DatabaseDescriptor` setter a unit test would call. Name it as §4's limit path names it, not as the check-site operand. |
| **Capacity values to test** | **At least three, including the default**, with units. Two points cannot show whether the response is linear. Say what capacity each value produces if the limit is derived rather than used raw (e.g. a percentage of free space). |
| **Usage-side observable** | §4's usage-side operand — the counter the check actually compares. |
| **Instrument** | How to read that operand, and **whether the real operand is exposed at all**. If it is not, name the proxy and state the gap plainly; a proxy that moves for other reasons is a confounder, not a measurement. |
| **Scope of the limit** | Global/process-wide, per-table, per-connection, or per-file. For a per-object limit, give the multiplier: node-wide usage moves by `limit × N`, so say what N is and how to control it. |
| **Suggested level** | Unit and/or cluster (both where practical — they answer different questions). Name any existing scaffolding under `test/unit/...` that already reaches this check, and the `ant testsome -Dtest.name=<FQCN>` line to run it. |

### 9a. Workload — driving the usage operand

What stage 4 must do to make the usage side climb toward the limit: the
operation, the payload size, the concurrency, and what (if anything) releases
capacity concurrently (flush, cleanup thread, consumer). Prefer a
**deterministic single-shot approach** — size the capacity below what one
operation needs, so the first attempt lands on the boundary — over a
throughput race against whatever reclaims capacity.

### 9b. Scenario A — just reach capacity

How to bring usage up to the limit without crossing it, and what stage 4
should observe at each capacity value. Expect usage ≈ capacity here in almost
every case; this scenario establishes that the knob moves the ceiling at all.

### 9c. Scenario B — try to exceed capacity

How to cross the limit, and what to observe. **Derive the expectation from
§6b**, not from an assumption that the check rejects cleanly: a clean reject,
a block-and-wait, and an escape hatch all look different from outside.

### 9d. Expected dose-response

State, before the run, what usage-vs-constraint should look like across the
three-plus capacity values **if the traced path is the binding limit** — and
what it should look like instead if the escape hatch or non-domination
recorded in §6b/§10 dominates. A design that predicts only the enforcing
outcome cannot tell a bypass from experimental noise.

### 9e. Interpretation — what each outcome means

So stage 4 can decide at the cluster without coming back to stage 3. Adjust
the rows to this case; the third is the one that refutes it.

| Observation at scenario B | Reading |
|---|---|
| Usage pinned at the ceiling; rejections/parks/exceptions rise as §6b predicts | The check enforces as traced. |
| Usage climbs past the ceiling | §6b's escape hatch or non-domination dominates — Target-3 material, and the case's §8 ceiling claim needs amending. |
| Usage flat across every capacity value | The traced path is **not** the binding limit. Stage 3 misread it; the case needs re-reading, not a re-run. |

### 9f. What would refute this case

The specific observation that would mean the traced path is wrong — stated
plainly enough that stage 4's feedback can settle it. A case with nothing
here is not falsifiable and the design is incomplete.

### 9g. Confounders and controls

What could move the observable for reasons unrelated to this check, and the
control run that separates them. Baseline at default config and an idle
control are the minimum; add per-case items (background compaction, GC
timing, a shared global pool picking up unrelated traffic, other tables).

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
