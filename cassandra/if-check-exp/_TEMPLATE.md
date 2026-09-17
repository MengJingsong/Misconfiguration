# [limit] — [object]

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

**Formatting note:** Link every code reference (`` `File.java:NN` `` or `` `Class.method():NN` ``) to the pinned source on GitHub. Use the format: `` [`File.java:NN`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/<path>#LNN) `` (ranges use `#LNN-LMM`). Place the link *outside* the backticks so code renders as clickable text.

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | e.g., MEMTABLE_HEAP_SPACE-BYTEBUFFER |
| **If-statement** | [`Class.method():NN`](GitHub link) |

```java
// paste the exact if-statement (and enough surrounding context to read both branches)
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

## 4. Capacity-overflow check

| Field | Content |
|-------|---------|
| **Is this a capacity/overflow check?** | yes / no / partial — one sentence why |
| **Usage-side operand** | the variable tracking current consumption (e.g. a counter, `allocated` bytes) |
| **Limit-side operand** | the variable/constant being compared against |
| **Limit type** | Configuration / Hardcoded constant / Derived (computed from other config) |

**Limit initialization path** (short — declare → configure/derive → store → read at the check; cite line numbers; if hardcoded, just the declaration):

1. [`Class.field():NN`](link) — declared
2. [`Class.method():NN`](link) — configured / derived / validated
3. [`Class.method():NN`](link) — stored where the check reads it from
4. [`Class.method():NN`](link) — read at the point of comparison

## 5. Branch semantics

| Branch | Condition | Effect |
|--------|-----------|--------|
| **Allow** | e.g. `used + size <= limit` | proceeds to allocate / create the object |
| **Disallow** | e.g. `used + size > limit` | blocks / rejects / defers / throws instead |

```java
// allow-branch body
```

```java
// disallow-branch body
```

## 6. Code path

### 6a. Allow branch → object creation

Continuous trace from the allow branch to the actual allocation call.

1. [`Class.method():NN`](link) — allow branch taken, state updated (e.g. counter incremented / CAS)
2. [`Class.method():NN`](link) — returns to caller
3. [`Class.method():NN`](link) — caller proceeds to allocate
4. [`Class.method():NN`](link) — **object creation** (`new ...` / `ByteBuffer.allocate(...)` / etc.)

### 6b. Disallow branch effect

What actually happens when the disallow branch fires — trace the real
effect before assuming it cleanly rejects anything (per the
[verification methodology](README.md#verifying-a-case-triggering-the-disallow-branch)'s
first rule). Is it a clean reject/throw? A block-and-wait? A silent
bypass/escape hatch elsewhere in the call chain?

1. [`Class.method():NN`](link) — disallow branch taken, what state (if any) changes
2. [`Class.method():NN`](link) — what the caller does with the rejected/blocked result

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | type/class |
| **Resource consumed** | heap bytes / off-heap bytes / thread / queue slot / file handle / etc. |
| **Rough sizing** | how the size is derived, if determinable from the code (e.g. `size` param, fixed struct size) |
| **Lifetime / release** | what releases this resource back to the pool/limit (brief) |

## 8. Maximum memory bound

State plainly how the value of the limit-side operand (§4) affects maximum
memory usage: if it's raised or lowered, what happens to the maximum bytes
the system can hold via this if-check, and through what mechanism? Goes
beyond §7's per-object sizing — this is about the limit's effect on the
ceiling, not what one allowed object costs.

## Verification

See [README.md § Verifying a case](README.md#verifying-a-case-triggering-the-disallow-branch)
before setting `Status: verified` — line-number checking alone is not enough;
a designed experiment must have actually driven execution into the disallow
branch with recorded evidence.

| Field | Content |
|--------|---------|
| **Status** | pending / in-progress / verified |
| **Verified By / Date** | Who verified and when |
| **Trigger method** | Unit test / program, or live-cluster config+steps, used to drive execution into the disallow branch |
| **Evidence** | What was observed that confirms the disallow branch specifically fired (assertion/breakpoint, metric, log line, thread dump) — not just an end symptom like a hang or error |
| **Notes** | Any caveats, escape hatches/bypasses noticed along the way (flag for Target 3), or outstanding questions |

---

## Notes

- _Add any additional context, edge cases, or version-specific behavior._
