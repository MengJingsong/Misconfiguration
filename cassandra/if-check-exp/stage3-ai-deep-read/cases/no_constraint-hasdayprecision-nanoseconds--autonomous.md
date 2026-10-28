# Duration.hasDayPrecision nanoseconds == 0 — verification solution  <!-- file: cases/[stem]--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`Duration.java:382`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Duration.java#L382) (helper `hasDayPrecision()`, defined at line 380) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: no constraint; the check is a format/validation test on a duration's precision, not a memory or disk cap |
| Ground | The check bounds nothing held in memory or on disk; a Duration is a fixed-size value (int, int, long) |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Operands: `getNanoseconds()` ([`Duration.java:281-284`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Duration.java#L281-L284), returns the `nanoseconds` field of the Duration value) compared with the literal `0` at [`Duration.java:382`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Duration.java#L382). Neither is a configuration entry, JVM property or limit.

**A2. What it caps.** Nothing. It could in principle bound a Duration's sub-day component, but a Duration is stored as months (int), days (int) and nanoseconds (long), a few bytes regardless of the value, so rejecting or accepting a non-zero nanoseconds part does not bound any memory or disk object.

**A3. Mechanism.** Enclosing method: `Duration.hasDayPrecision()` at `Duration.java:380-383`, `return getNanoseconds() == 0;`. Outcome true: the duration has nothing below the day level. Outcome false: it has a sub-day part. Only call site in `src/java`: [`SimpleDateType.validateDuration`, `SimpleDateType.java:118`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/SimpleDateType.java#L118), `if (!duration.hasDayPrecision()) throw invalidRequest("The duration must have a day precision. Was: %s", duration)`. So false rejects a request that adds or subtracts a duration with a sub-day part to a `date` value (`TemporalType.java:81`, `:95` call validateDuration before addTo/substractFrom). True lets the arithmetic proceed. No bypass or overshoot concept applies; the effect is semantic validation of date arithmetic.

**A4. Other consumers.** None; the check touches no shared resource.

**A5. Evidence beyond the source.** Searched `src/java` for `hasDayPrecision` (two hits: definition and the one call site), read the Javadoc at `Duration.java:377-379` ("Checks if that duration has a day precision (nothing bellow the day level)"), and read `Duration.addTo`/`substractFrom` at `Duration.java:291,301`. No config key, docs or history relied on; the Javadoc and the error message both state a format purpose.

## B. Verification solution

**B1. Claim under test.** This check does not cap memory or disk usage: it only validates that a duration added to a `date` has no sub-day component.

### B2. Unit tier

`n/a: no constraint, there is no limit whose usage-side value could be measured.` Evidence in A answers it instead: the operand is the `nanoseconds` field of a fixed-size value (A1, A2) and the sole caller only throws a validation error (A3).

### B3. Cluster tier

`n/a: no constraint, there is no resource to push to a boundary.` Evidence in A answers it instead (A2, A3): both outcomes of the check allocate or retain a constant amount.

**B4. Risks and cleanup.** None; nothing is run.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Duration.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/SimpleDateType.java
- grep of /users/jason92/cassandra-5.0.9/src/java for `hasDayPrecision`, `addTo`, `substractFrom`
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/TemporalType.java (call sites at lines 81, 95 only, via grep)

## D. Stage-4 feedback

`none yet`
