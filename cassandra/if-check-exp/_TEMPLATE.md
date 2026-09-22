# [constraint] — [object]  <!-- file name: [constraint]-[function]-[operand].md -->

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

**Formatting note:** Link every code reference (`` `File.java:NN` `` or `` `Class.method():NN` ``) to the pinned source on GitHub. Use the format: `` [`File.java:NN`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/<path>#LNN) `` (ranges use `#LNN-LMM`). Place the link *outside* the backticks so code renders as clickable text.

**Relative links in this template** (`../README.md`, `../_INDEX.md`) are written for where a
*copy* of it lives — inside a `<module>/` folder — not for the template's own location at the
experiment root. They will look broken here and resolve correctly in a real case file.

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | filename stem upper-cased, e.g., MEMTABLE_HEAP_SPACE-TRYALLOCATE-LIMIT |
| **Constraint** | the resource constraint name (first part of the file name) and its source: configuration entry / JVM system property / constant / runtime-queried accessor (README §6.1) |
| **Enforcement pattern** | (a) the check is the decision / (b) the check sets a verdict (flag, enum, return value) that a separate decision point reads / (c) guard clause(s) before an allocation that is not inside a branch — see [README.md §3.2](../README.md#3-core-concept-the-if-check-case) |
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
effect before assuming it cleanly rejects anything (per the
[verification methodology](../README.md#8-verifying-a-case-triggering-the-disallow-branch)'s
first rule). Is it a clean reject/throw? A block-and-wait? A silent
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

## 9. Verification

See [README.md § Verifying a case](../README.md#8-verifying-a-case-triggering-the-disallow-branch)
before setting `Status: verified` — line-number checking alone is not enough;
a designed experiment must have actually driven execution into the disallow
branch with recorded evidence.

| Field | Content |
|--------|---------|
| **Status** | pending / in-progress / verified — note behavioral verification is **deferred by decision** (README §7.5); new cases stay `pending` with the trigger designed but not run |
| **Verified By / Date** | Who verified and when |
| **Line numbers checked** | date each cited line was checked against the local pinned-tag clone (`git describe --tags` = `cassandra-5.0.9`) |
| **Trigger method** | Unit test / program, or live-cluster config+steps, used to drive execution into the disallow branch |
| **Evidence** | What was observed that confirms the disallow branch specifically fired (assertion/breakpoint, metric, log line, thread dump) — not just an end symptom like a hang or error |
| **Escape hatch / Target-3 note** | any bypass of the disallow branch noticed (flag for Target 3, do not chase here), or "none found yet" |
| **Notes** | Any other caveats or outstanding questions |

---

## 10. Notes

- _Add any additional context, edge cases, or version-specific behavior._
