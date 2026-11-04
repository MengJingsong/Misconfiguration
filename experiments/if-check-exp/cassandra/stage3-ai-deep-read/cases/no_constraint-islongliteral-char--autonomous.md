# no constraint: ParseUtils.isLongLiteral character test — verification solution  <!-- file: cases/no_constraint-isLongLiteral-char--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`ParseUtils.java:234`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/ParseUtils.java#L234) (helper `isLongLiteral`, defined at line 227) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code agent, 2026-10-27 |
| Estimate | `negative`: no constraint; the check is a syntax test (digits with optional leading minus) and bounds no memory or disk object. |
| Ground | The comparison is on character codes of a string already held in memory; it only chooses a parse branch (`Long.parseLong` vs. date parsing). |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Compared operands: `c` (the `char` at index `i` of `str`, a parameter of `isLongLiteral`, [`ParseUtils.java:233`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/ParseUtils.java#L233)) against the character literals `'0'`, `'9'`, `'-'` (inline literals at [`ParseUtils.java:234`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/ParseUtils.java#L234), no named constant, no yaml key, no JVM property); and `i != 0` (loop index, `ParseUtils.java:231`).

**A2. What it caps.** Nothing. The only object involved is `chars = str.toCharArray()` (line 230), a transient copy of a string the caller already holds; the check does not bound its size, and returns `false` early on the first non-digit. It validates format only.

**A3. Mechanism.** Enclosing method `static boolean isLongLiteral(String str)`, `ParseUtils.java:227-237`. Null/empty returns false (229); otherwise each char is tested at [`ParseUtils.java:234`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/ParseUtils.java#L234): false if char is below `'0'` (except `'-'` at index 0) or above `'9'`; true if the loop finishes. Outcomes: true leads the caller to `Long.parseLong` (a `NumberFormatException` becomes `InvalidTypeException` for overflow); false leads the caller to date parsing (timestamp, `TypeCodec.java:1727`, then `ParseUtils.parseDate`) or the next branch (date, `TypeCodec.java:1799`; time, `TypeCodec.java:1890`). Call sites read: `TypeCodec.java:1727` (timestamp parse), `1799` (date parse), `1890` (time parse); no other callers (grep over `src`). No bypass/overshoot relevant: nothing is limited.

**A4. Other consumers.** n/a: no resource is bounded. The input string length is not capped here; it is whatever the CQL/UDF literal parse supplied.

**A5. Evidence beyond the source.** Searched: callers (`grep -rn isLongLiteral src`, three hits above, all in `TypeCodec`), config keys (none referenced in the method), javadoc at lines 219-226 (describes it as a literal syntax test). No issues/docs consulted; none needed.

## B. Verification solution

**B1. Claim under test.** `isLongLiteral` does not cap memory or disk usage: it is a syntax test whose outcome selects a parse branch and does not limit any held object.

### B2. Unit tier

n/a: no constraint, there is no usage-side value compared against a limit. Evidence in A1-A3 (operands are char literals; only transient `char[]` allocated) answers the question instead.

### B3. Cluster tier

n/a: no constraint, there is no limit to push to a boundary. Evidence in A2-A3 answers the question instead: the result only selects a parse path, and no stored or retained structure depends on it.

**B4. Risks and cleanup.** None; nothing is run.

## C. Sources read

- src/java/org/apache/cassandra/cql3/functions/types/ParseUtils.java (lines 210-250)
- src/java/org/apache/cassandra/cql3/functions/types/TypeCodec.java (lines 1715-1745, 1795-1810, 1885-1900)

## D. Stage-4 feedback

`none yet`
