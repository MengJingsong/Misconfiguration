# no-constraint-Duration.hasMillisecondPrecision-nanoseconds — verification solution

| Field | Value |
|---|---|
| Entry pointer | [`Duration.java:391`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Duration.java#L391) (`return getNanoseconds() % NANOS_PER_MILLI == 0;` in `hasMillisecondPrecision()`, line 389) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: no constraint; the check is a precision (format) test on a Duration value and bounds no memory or disk object. |
| Ground | The modulo test only decides whether a duration is whole milliseconds. It accepts or rejects a request; nothing it guards is held in memory or on disk in a size that depends on it. |

**Type:** non-config (none). The constant `NANOS_PER_MILLI` takes part, but only as a unit divisor, not a limit.

## A. Constraint trace

**A1. The constraint.** `no constraint`. Operands: `getNanoseconds()` (the `nanoseconds` field of the Duration, [`Duration.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Duration.java#L44) declares `NANOS_PER_MILLI = 1000 * NANOS_PER_MICRO` = 1,000,000, a unit-conversion constant) and the literal 0. No yaml entry or JVM property is read. Not settable.

**A2. What it caps.** Nothing. No memory or disk object is bounded. A Duration is three fixed-width fields (months, days, nanoseconds), serialized as vints and held as a small object; the modulo test only checks whether the nanosecond part is a multiple of 1,000,000.

**A3. Mechanism.** Enclosing method: `Duration.hasMillisecondPrecision()` at [`Duration.java:389-392`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Duration.java#L391). Returns true when `nanoseconds % 1_000_000 == 0`. Callers read:
- `TimestampType.validateDuration`, `src/java/org/apache/cassandra/db/marshal/TimestampType.java:178`: false throws `invalidRequest("The duration must have a millisecond precision...")`, true lets the arithmetic proceed.
- `TimeFcts` floor-function validation, `src/java/org/apache/cassandra/cql3/functions/TimeFcts.java:340`: false throws `invalidRequest("The floor cannot be computed ... precision is below 1 millisecond")`, true proceeds to compute the floor.
Both outcomes are request validation; neither path stores more or less data, and no limit is "reached". No bypass or overshoot concept applies.

**A4. Other consumers.** n/a, no resource is bounded.

**A5. Evidence beyond the source.** Searched: all callers (`grep hasMillisecondPrecision` in `src/java`: only the two above plus the definition); yaml and `CassandraRelevantProperties` for any related key (none; the method reads no config); Javadoc at Duration.java:384-388 says it only checks "nothing below the millisecond level". No issues or docs relied on.

## B. Verification solution

**B1. Claim under test.** `hasMillisecondPrecision()` does not cap memory or disk usage: its outcome depends only on `nanoseconds mod 1,000,000`, and the memory/disk cost of the Durations and results it guards is the same for either outcome.

### B2. Unit tier
n/a: no constraint, there is no usage-side operand against a limit. The evidence in A3 (both outcomes only throw or proceed with fixed-size arithmetic) and A2 (Duration is fixed-size) answers the question instead.

### B3. Cluster tier
n/a: no constraint, no resource to push to a boundary. A3 shows the only effect is accepting or rejecting a request; A2 shows the guarded object is fixed-size.

**B4. Risks and cleanup.** None; nothing is run.

## C. Sources read
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Duration.java (lines 40-46, 380-395)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/TimestampType.java (lines 170-190)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/TimeFcts.java (lines 330-350)

## D. Stage-4 feedback
`none yet`
