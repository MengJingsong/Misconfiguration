# no_constraint — ErrorCollector.isTokenValid (token position validity) — verification solution  <!-- file: cases/no_constraint-istokenvalid-token_position--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the check in `ErrorCollector.isTokenValid(Token)`: [`ErrorCollector.java:189`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/ErrorCollector.java#L189) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: no constraint. The check validates that an ANTLR token carries a positive line number and a non-negative column; it caps no memory or disk. |
| Ground | The check is a validity test on two ints. Failing it only skips appending a snippet to a syntax-error message; nothing held is bounded. |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Operands compared: `token.getLine()` against literal `0` and `token.getCharPositionInLine()` against literal `0`, both in [`ErrorCollector.java:189`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/ErrorCollector.java#L189). The operands are the ANTLR `Token` fields (line and column), set by the lexer when it produces the token (ANTLR 3 runtime, `CommonToken`); the `0` literals are inline, not named constants. ANTLR uses line 0 / column -1 for synthetic tokens (for example EOF or an invented token), which this test rejects.

**A2. What it caps.** Nothing. No memory or disk object is bounded. The check decides whether a position is meaningful enough to print in a snippet. The snippet is built into a `StringBuilder` for an error message whose size is not limited by this check.

**A3. Mechanism.** Enclosing method: `private static boolean isTokenValid(Token token)` at ErrorCollector.java:187-190; body is `return token.getLine() > 0 && token.getCharPositionInLine() >= 0;` ([`ErrorCollector.java:189`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/ErrorCollector.java#L189)). Sole caller: `areTokensValid(Token...)` (ErrorCollector.java:171-179), which loops over tokens and returns false on the first invalid one (line 175). Sole caller of that: `appendSnippet(...)` at ErrorCollector.java:135 (`if (!areTokensValid(from, to, offending)) return;`). `appendSnippet` is called from `appendQuerySnippet` (line 120), called from `syntaxError(BaseRecognizer, String[], RecognitionException)` (line 77) when the recognizer is a `Parser`. The ErrorCollector is created in `CQLFragmentParser.java:66`.
- Outcome true (valid): `appendSnippet` goes on to split the query into lines and append a snippet (lines 137-160).
- Outcome false: `appendSnippet` returns early; the error message has no snippet. The error is still recorded (`errorMsgs.add`, line 80) and still thrown by `throwFirstSyntaxError` (line 98-102).
No path bypasses or overshoots a limit, as there is none. Call sites read: the one in `areTokensValid` only.

**A4. Other consumers.** Not applicable (no resource). For context, the unrelated `errorMsgs` LinkedList (line 52) grows with the number of syntax errors and is not bounded by this check either.

**A5. Evidence beyond the source.** Searched `grep -rn isTokenValid src` (only ErrorCollector.java:175 and :187), `grep -rn "new ErrorCollector" src` (only CQLFragmentParser.java:66), and the method Javadoc (lines 183-186: "Checks that the specified token is valid"). No config key, doc or issue ties this to a size limit. History not consulted beyond the tree.

## B. Verification solution

**B1. Claim under test.** `isTokenValid` does not cap memory or disk usage: its outcome changes only whether a snippet is appended to a syntax-error message, and no resource limit exists to follow.

### B2. Unit tier

`n/a: no constraint, there is no limit value to vary and no usage-side quantity to measure.` Evidence in A answers the question instead: A1 (operands are token position ints against literal 0), A3 (both outcomes only add or omit message text), A2 (no bounded object). Optional sanity check, not needed for the claim: a JUnit test calling `appendSnippet` with a token from `CommonToken` with line 0 and one with line 1, asserting that the first yields no snippet and the second does.

### B3. Cluster tier

`n/a: no constraint, there is no knob and no resource cap to push to a boundary.` Evidence in A (A2, A3) answers the question instead: the only effect is the text of a syntax error returned to the client.

**B4. Risks and cleanup.** None; nothing is run.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/ErrorCollector.java (lines 40-215)
- grep over /users/jason92/cassandra-5.0.9/src for `isTokenValid`, `areTokensValid`, `new ErrorCollector`

## D. Stage-4 feedback

`none yet`
