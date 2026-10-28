# no_constraint — ClusteringPrefix.Deserializer.hasComponent — verification solution  <!-- file: cases/no_constraint-hasComponent-i_nextSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | helper `org.apache.cassandra.db.ClusteringPrefix$Deserializer.hasComponent(int)`; its check [`ClusteringPrefix.java:653`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ClusteringPrefix.java#L653) (`if (i >= nextSize)`), loop at [`:656`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ClusteringPrefix.java#L656) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI (Agent SDK), 2026-10-27 |
| Estimate | `negative`: no constraint. The check is a bounds test on a component index against the clustering size, and a loop that deserializes components up to that index; it caps no memory or disk. |
| Ground | Bookkeeping / loop control. The memory allocated is governed elsewhere (`nextSize`, and the per-value read limit). |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Operands of the check at [`ClusteringPrefix.java:653`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ClusteringPrefix.java#L653):
- `i`: the parameter, a component index supplied by the caller `compareNextTo`, the loop variable `for (int i = 0; i < bound.size(); i++)` at `ClusteringPrefix.java:633`. It ranges over the bound's size.
- `nextSize` (field, declared `ClusteringPrefix.java:597`): set in `prepare()` at `:612` to `comparator.size()` for a row (the table's clustering column count) or `in.readUnsignedShort()` (bound size read from the sstable) otherwise.
- loop condition `deserializedSize <= i` (`:656`): `deserializedSize` is a field (`:599`) reset to 0 in `prepare()` (`:613`) and incremented in `deserializeOne()` (`:675`).
No yaml entry, JVM property or constant takes part.

**A2. What it caps.** Nothing. The check decides whether the in-progress clustering has a component at index `i`: false means the sstable-side clustering is shorter than the bound (the caller returns `nextKind.comparedToClustering`), true means deserialize components lazily up to `i`. The memory involved is `nextValues = new byte[nextSize][]` (`:620`, sized from `nextSize`, at most 65535 slots from the unsigned short or the clustering column count) plus the component bytes, which `deserializeOne()` reads with `readArray(in, DatabaseDescriptor.getMaxValueSize())` (`:677`). That value-size limit is a separate check inside `deserializeOne()`, not this helper, and the helper only prevents reading past `nextSize`. So the check bounds no held object.

**A3. Mechanism.** Enclosing method: `hasComponent(int)`, [`ClusteringPrefix.java:651-660`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ClusteringPrefix.java#L651-L660), private, single definition and no overloads.
- Outcome `i >= nextSize` ([`:653`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ClusteringPrefix.java#L653)): return false, nothing is read.
- Otherwise `while (deserializedSize <= i) deserializeOne();` (`:656-657`) reads components from the input until index `i` is available, then returns true. `deserializeOne()` (`:662-678`) itself returns false once `deserializedSize == nextSize`, so the loop terminates because `i < nextSize`.
- Call sites read: the only caller is `compareNextTo` at `ClusteringPrefix.java:636`. `compareNextTo` is called by `UnfilteredDeserializer.compareNextTo` (`UnfilteredDeserializer.java:115`) and from `AbstractSSTableIterator.java:495,530`, `big/SSTableIterator.java:170`, `big/SSTableReversedIterator.java:206,238`, `bti/SSTableReversedIterator.java:195,217` (seen by grep; these are slice-bound comparison loops).
- Bypass or overshoot: none relevant; the lazy deserialization only lowers allocation versus deserializing everything (see the comment at `:615-618`).

**A4. Other consumers.** n/a: no resource is capped here. The related memory (clustering values) is read by `deserializeOne` under `DatabaseDescriptor.getMaxValueSize()` and by `deserializeAll`/`skipNext`, none controlled by this check.

**A5. Evidence beyond the source.** Searched: callers of `hasComponent` (grep: only `:636`), `compareNextTo` callers (above), the class Javadoc at `:580-587` (describes lazy deserialization to do as little work as possible). No config key, doc, test or history item ties this check to a limit. `none` otherwise (the source copy has no git history).

## B. Verification solution

**B1. Claim under test.** The check `i >= nextSize` / loop in `hasComponent` does not cap memory or disk usage; it is index-bounds and loop control.

### B2. Unit tier

n/a: no constraint. The evidence in A1-A3 (operands are an index and a clustering size; the only held object, `nextValues`, is sized by `nextSize` before this method runs, and component bytes by the separate `getMaxValueSize` limit in `deserializeOne`) answers the question instead.

**B2a-B2h.** n/a: no constraint, see A3 and A2 for the evidence.

### B3. Cluster tier

n/a: no constraint, same reason; nothing to push to a boundary because no knob feeds the check.

**B3a-B3h.** n/a: no constraint, see A1-A3.

**B4. Risks and cleanup.** n/a: nothing to run.

## C. Sources read

- `src/java/org/apache/cassandra/db/ClusteringPrefix.java` (lines 585-720)
- grep results over `src/` for `hasComponent` and `compareNextTo`

## D. Stage-4 feedback

`none yet`
