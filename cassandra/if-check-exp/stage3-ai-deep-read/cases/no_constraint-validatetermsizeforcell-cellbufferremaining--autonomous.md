# Empty-or-null cell skip in SAI term-size validation (no constraint) — verification solution  <!-- file: cases/no_constraint-validatetermsizeforcell-cellbufferremaining--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`StorageAttachedIndex.java:791`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java#L791) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (Claude Code agent), 2026-10-27 |
| Estimate | `negative`: no constraint. The check is a null/empty short-circuit; it bounds no memory or disk object. |
| Ground | The check only avoids running the term-size guardrail on a value that has no bytes. The actual size cap is the separate guardrail call at line 795. |

**Type:** non-config (none). The numeric literal `0` in `cellBuffer.remaining() == 0` makes this non-config under the constant rule; no yaml entry or JVM property takes part in this condition.

## A. Constraint trace

**A1. The constraint.** no constraint. Operands of `if (cellBuffer == null || cellBuffer.remaining() == 0)` at [`StorageAttachedIndex.java:791`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java#L791):
- `cellBuffer`: method parameter (`StorageAttachedIndex.java:789`), a `ByteBuffer` taken from the indexed cell by `IndexTermType.valueOf` (`IndexTermType.java:400-422`, returns null for missing or dead cells or for a static-row mismatch) or from `indexTermType.valuesOf` for non-frozen collections (`StorageAttachedIndex.java:777-780`).
- `cellBuffer.remaining()`: runtime size of the value in bytes.
- literal `0`: numeric literal, language-level; no declaration.

**A2. What it caps.** Nothing. The check could be said to relate to the term-size guardrail (`maxTermSizeGuardrail`, assigned from `Guardrails.saiVectorTermSize` / `saiFrozenTermSize` / `saiStringTermSize` at `StorageAttachedIndex.java:207-210`, declared in `Guardrails.java:520-544`). But 791 is not that limit: it only discards values with nothing to measure. An empty or null value holds zero bytes, so skipping it neither bounds nor leaves unbounded any held memory or disk.

**A3. Mechanism.** Enclosing method: `validateTermSizeForCell` (`StorageAttachedIndex.java:789`), private.
- True branch (null or zero length): `return` at line 792, nothing validated. An empty term cannot exceed any size threshold, so the result is identical to running the guardrail on it.
- False branch: line 795 `if (!maxTermSizeGuardrail.warnsOn(cellBuffer.remaining(), null)) return;` is the actual threshold test (the warn threshold is the first filter); then the analyzer or `validateTermSize` (line 815) runs, which calls `maxTermSizeGuardrail.guard` (line 819) for client mutations or `failsOn` (line 823) for non-client ones.
- Callers: only `validateTermSizeForRow` (lines 780 and 785), which is called from `validateTermSizeForRow` call sites at lines 526 and 529 (client mutation path, `isClientMutation=true`). `validateTermSize` is also called from `TrieMemoryIndex.java:220` but that bypasses this method.
- Bypass/overshoot: none relevant. A null or empty value is never a risk for size.

**A4. Other consumers.** Not applicable (no resource governed). The guardrail at line 795/819/823 is the real term-size limit; its own thresholds are guardrail config, outside this target.

**A5. Evidence beyond the source.** Searched: callers of `validateTermSizeForCell` / `validateTermSizeForRow` (above), `Guardrails.java:520-544` declarations, `IndexTermType.valueOf` null returns. No docs or issues relied on. none.

## B. Verification solution

**B1. Claim under test.** The check at line 791 does not cap memory or disk usage: it returns early only for null or zero-byte values, and removing it would change neither the accepted set of writes nor any resource usage.

### B2. Unit tier

n/a: no constraint. The evidence in A3 (the guardrail call at line 795 is the actual limit; an empty value cannot exceed any threshold, since `warnsOn(0, null)` is false for any non-negative threshold) answers the question instead. Optional reading check: a unit test that builds a `StorageAttachedIndex` with an empty `ByteBuffer.allocate(0)` value and calls `validateTermSizeForRow` should return with no guardrail event and no exception, with `saiStringTermSize` fail threshold set to 1 byte.

### B3. Cluster tier

n/a: no constraint. There is no resource to push to a boundary: the branch only fires for values holding zero bytes, so no workload can make it hold memory or disk. A4/A5 and A3 give the evidence. Alternative sanity check: with an SAI index on a text column and `sai_string_term_size_fail_threshold` set to `1B`, insert an empty string and a 2-byte string; the empty insert is accepted and the 2-byte insert is rejected. This shows the 791 branch is the pass-through case and the real limit is line 795/819.

**B4. Risks and cleanup.** Only the optional sanity check above; use a throwaway node and its data directories, then stop the process and delete them.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java (lines 183-210, 520-530, 765-830)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/utils/IndexTermType.java (lines 400-422)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Guardrails.java (grep of lines 520-544)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java (grep line 220)

## D. Stage-4 feedback

`none yet`
