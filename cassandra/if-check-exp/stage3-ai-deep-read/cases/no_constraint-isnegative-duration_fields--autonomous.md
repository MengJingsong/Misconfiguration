# no constraint: Duration.isNegative sign test — verification solution  <!-- file: cases/[stem]--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`Duration.java:527`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Duration.java#L527) (`return nanoseconds < 0 \|\| days < 0 \|\| months < 0;` in `Duration.isNegative()`, defined at line 525) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: the check is a sign test on three primitive fields of a CQL duration value; it compares against the constant 0 and bounds no memory or disk object. |
| Ground | No constraint: bookkeeping/validation of a value's sign. A Duration is a fixed-size object (int, int, long) whatever its sign. |

**Type:** non-config (none). No yaml entry or JVM property takes part; the only operand besides the instance fields is the literal `0`.

## A. Constraint trace

**A1. The constraint.** `no constraint`. The compared operands are the instance fields `months` (int), `days` (int) and `nanoseconds` (long) of `org.apache.cassandra.cql3.Duration`, declared as `private final` fields of the class (declared near the top of [`Duration.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Duration.java#L525); they are assigned in the constructor and set from parsed user input or from the serialized value), each compared with the literal `0`. No named constant, yaml key, JVM property or runtime-queried limit is read. Not settable; not a limit.

**A2. What it caps.** Nothing. The check could bound no memory or disk object: it only answers "is any component of this duration below zero". A `Duration` is 16 bytes of payload regardless of the answer, and the callers use the answer only to reject a query or choose a leading `-` sign character in a string.

**A3. Mechanism.** Enclosing method: `Duration.isNegative()` at `src/java/org/apache/cassandra/cql3/Duration.java:525-528`; the if-like check is the boolean expression at [`Duration.java:527`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Duration.java#L527). It returns true if any of `nanoseconds`, `days`, `months` is negative, else false.
Call sites (all in the tree, `grep -rn "\.isNegative()" src/java`, BigDecimal uses excluded; `DecimalType.java:214` is an unrelated local variable):
- `Duration.java:356` in `toString()`: true appends `'-'` to the output string; false appends nothing. Output size differs by one character.
- `Duration.java:423` in `floorTimestamp(long, Duration, long)`: `checkFalse(duration.isNegative(), "Negative durations are not supported by the floor function")`; true throws an InvalidRequestException for the query, false continues to compute the floor.
- `Duration.java:510` in `floorTime(long, Duration)`: same `checkFalse` rejection.
The private `Builder(boolean isNegative)` field (`Duration.java:535`, used at 788) is a separate parse-time flag and does not call this method. The sibling `functions/types/Duration.java` (driver-copy class) has no `isNegative()` method of its own to compare.
Bypass/overshoot: not applicable; there is no limit.

**A4. Other consumers.** n/a: no resource is bounded.

**A5. Evidence beyond the source.** Searched: all callers of `isNegative()` in `src/java` (three, above); config keys (`cassandra.yaml`, `CassandraRelevantProperties`) for "duration" negative handling: none relate to this check; the method's Javadoc (`Duration.java:520-524`) says only "Checks if the duration is negative". Tests, docs and git history were not needed to conclude there is no constraint: the method body reads no external value.

## B. Verification solution

**B1. Claim under test.** `Duration.isNegative()` does not cap memory or disk usage; it is a sign test with no resource bound.

### B2. Unit tier

`n/a: no constraint, there is no usage-side quantity to measure.` Evidence in A answering the question instead: A1 (operands are fields compared with literal 0) and A3 (callers only throw an invalid-request error or add a `-` character).

### B3. Cluster tier

`n/a: no constraint, there is no resource-bearing object bounded by the check.` Evidence in A answering the question instead: A2 (fixed-size 16-byte value) and A3 (callers).

**B4. Risks and cleanup.** None; nothing is to be run.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Duration.java (lines 140-165, 345-365, 415-430, 505-560)
- grep results for `isNegative` under /users/jason92/cassandra-5.0.9/src/java
- /users/jason92/cassandra-5.0.9/playbook and template provided by the lead

## D. Stage-4 feedback

`none yet`
