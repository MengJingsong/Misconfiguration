# no_constraint — ParseUtils.isQuoted — verification solution

| Field | Value |
|---|---|
| Entry pointer | [`ParseUtils.java:247-250`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/ParseUtils.java#L247-L250) delegating to the check at [`ParseUtils.java:487-490`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/ParseUtils.java#L487-L490) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code, 2026-10-27 |
| Estimate | `negative`: the helper is a string-format test with no memory or disk cap. |
| Ground | It only tests whether a CQL literal starts and ends with a quote character; it holds, allocates and bounds nothing. |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Overloads `isQuoted(String)` (ParseUtils.java:247, package-private, delegates with `'\''`) and `isQuoted(String, char)` (ParseUtils.java:485) share one logic, traced together. Operands: `value` (a CQL literal string passed by caller, origin: the `parse(String)` argument of a TypeCodec), the constant length bound `1` (literal at [`ParseUtils.java:487`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/ParseUtils.java#L487), meaning "at least two chars so open and close quote are distinct"), and `quoteChar` (`'\''` literal at ParseUtils.java:249, or caller-supplied at ParseUtils.java:566). No yaml entry, JVM property or limit is read.

**A2. What it caps.** Nothing. It could in principle relate to the size of the string `value`, but `length() > 1` is a lower bound for well-formedness, not an upper bound; no upper limit exists, and the string is already in memory when tested.

**A3. Mechanism.** Enclosing method: `isQuoted(String, char)` at [`ParseUtils.java:485-490`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/ParseUtils.java#L487-L490): returns `value != null && length>1 && first char == quote && last char == quote`. True outcome: caller strips the quotes (`unquote`, ParseUtils.java:566) and parses; false outcome: the caller throws `InvalidTypeException` ("text or varchar values must be enclosed by single quotes", TypeCodec.java:958-959) or treats the value as unquoted (TypeCodec.java:1725, 1797). Call sites read: TypeCodec.java:958, 1485, 1725, 1797, 1886, and ParseUtils.java:566. No path allocates or retains memory or disk based on the result.

**A4. Other consumers.** n/a: no resource is bounded. The string itself is held by the caller (UDF/codec literal parsing) outside this check's control.

**A5. Evidence beyond the source.** Searched `grep -rn isQuoted src` (callers above only); the Javadoc at ParseUtils.java:240-246 and 478-484 describes pure format inspection; no config key, test or docs relation to resource limits. Adopted from the DataStax driver codec utilities (no resource semantics).

## B. Verification solution

**B1. Claim under test.** `isQuoted` does not cap memory or disk usage; this is a format check.

### B2. Unit tier
n/a: no constraint, there is no usage-side value to measure; A1 and A3 show the operands are a literal-string format test with a constant `1` lower bound.

### B3. Cluster tier
n/a: no constraint, no resource moves with this check; A2 and A3 answer the question (the check neither allocates nor limits anything).

**B4. Risks and cleanup.** None; nothing is run.

## C. Sources read

- src/java/org/apache/cassandra/cql3/functions/types/ParseUtils.java
- src/java/org/apache/cassandra/cql3/functions/types/TypeCodec.java (call sites)

## D. Stage-4 feedback

`none yet`
