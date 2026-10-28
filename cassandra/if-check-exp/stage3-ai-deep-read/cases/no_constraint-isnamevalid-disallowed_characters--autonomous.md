# function-name character validation (no constraint) — verification solution  <!-- file: cases/no_constraint-isnamevalid-disallowed_characters--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`FunctionName.java:56`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/FunctionName.java#L56) (`if (DISALLOWED_CHARACTERS.contains(c))` inside `isNameValid`, defined at line 51) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: no constraint. The check is a character-set validation of a function name; it caps no memory or disk object. |
| Ground | The check tests membership of each character in a fixed 3-element set; it compares no size, count or byte quantity, and the validated name is stored as an ordinary string in schema. |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Operands of the check: `c = name.charAt(i)` (each character of the function or aggregate name argument; origin: the CQL statement text, via `functionName` / `aggregateName`) and `DISALLOWED_CHARACTERS`, a hard-coded `Set<Character>` of `'/'`, `'['`, `']'`, declared at [`FunctionName.java:32-33`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/FunctionName.java#L32-L33). It is not a yaml entry, JVM property, or size limit; not settable. (Constant rule note: a constant takes part, so the row is non-config, but it is a character set, not a quantity.)

**A2. What it caps.** Nothing. It could in principle bound the content of a name string, but it does not bound its length or any held object: it only rejects names containing `/`, `[` or `]`. The stored name is a `String` in the function's schema row, whose size is unaffected by the check (any length of allowed characters passes).

**A3. Mechanism.** Enclosing method: static `FunctionName.isNameValid(String)` at `FunctionName.java:51`; loop at line 53 over name characters; check at [`FunctionName.java:56`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/FunctionName.java#L56). Outcome true (character disallowed): return `false` (line 58); outcome false: continue, and after the loop return `true` (line 61). Callers (the only two in `src`, none in `test`): [`CreateFunctionStatement.java:92`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/schema/CreateFunctionStatement.java#L92) and [`CreateAggregateStatement.java:97`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/schema/CreateAggregateStatement.java#L97); on `false` each throws `ire("... name '%s' is invalid")` (an InvalidRequestException) and the CREATE is rejected. Javadoc at lines 46-50 says it validates "no disallowed characters". Cost of the check is O(length) time and no allocation beyond boxing a char; nothing is retained.

**A4. Other consumers.** The name string, once accepted, is held in `UDFunction`/`UDAggregate` metadata and system_schema rows, with no limit from this check. Any length cap on names would come from elsewhere (for example the CQL name grammar or schema/keyspace-name limits); none is applied here.

**A5. Evidence beyond the source.** Searched: `grep -rn isNameValid src test` (only the definition and the two callers above; no tests); `DISALLOWED_CHARACTERS` declared and used only in `FunctionName.java`; no yaml key or `CassandraRelevantProperties` refers to it. No docs or history consulted beyond the Javadoc. The reason for the disallowed characters (by inference from the comment and code, not verified) is to keep names safe in contexts such as path/ID-like strings and CQL signatures, not resource control.

## B. Verification solution

**B1. Claim under test.** `FunctionName.isNameValid` does not cap memory or disk usage: it rejects only names containing `/`, `[` or `]` and accepts arbitrarily long names of other characters.

### B2. Unit tier

n/a: no constraint, there is no usage-side quantity to measure. A1 and A3 answer the question: the only comparison is a character-set membership test with a fixed 3-element set, and the method returns a boolean without retaining state. (Optional sanity check for a reader: call `isNameValid` with a 1 MB string of `a` and expect `true`; with `"a/b"`, `"a[b"`, `"a]b"` expect `false`.)

### B3. Cluster tier

n/a: no constraint, there is no resource cap to push to a boundary. A3's two callers and the unchanged storage of the name (A2, A4) answer the question instead.

**B4. Risks and cleanup.** None; nothing is run.

## C. Sources read

- src/java/org/apache/cassandra/cql3/functions/FunctionName.java
- src/java/org/apache/cassandra/cql3/statements/schema/CreateFunctionStatement.java
- src/java/org/apache/cassandra/cql3/statements/schema/CreateAggregateStatement.java
- grep of `isNameValid` over src and test

## D. Stage-4 feedback

`none yet`
