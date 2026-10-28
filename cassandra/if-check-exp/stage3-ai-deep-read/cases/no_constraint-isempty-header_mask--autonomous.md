# no_constraint — ClusteringPrefix.Serializer.isEmpty(long header, int i) — verification solution

| Field | Value |
|---|---|
| Entry pointer | [`ClusteringPrefix.java:575`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ClusteringPrefix.java#L575) (`return (header & mask) != 0;` inside `Serializer.isEmpty(long, int)`, defined at line 572) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: the helper is a bit test on a serialization header; it caps no memory or disk. |
| Ground | The check decodes a per-element "is empty" flag from a 64-bit header word; no size, count or byte quantity is compared to any limit. |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Operands of the helper's comparison: `header & mask` against `0`. `header` is a `long` read by `in.readUnsignedVInt()` ([`ClusteringPrefix.java:660`-area, deserializeOne; see A3]) or built by `makeHeader` at [`ClusteringPrefix.java:548`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ClusteringPrefix.java#L548). `mask` is the local `1L << (i * 2)` (line 574), where `i` is the clustering column index (2 bits per element, 32 elements per header). `0` is a literal. No yaml entry, JVM property or constant is compared.

**A2. What it caps.** Nothing. The check could at most relate to the clustering values being deserialized, but it only selects whether to materialise `ByteArrayUtil.EMPTY_BYTE_ARRAY` (a shared constant) or to read bytes; the actual byte read is bounded elsewhere by `DatabaseDescriptor.getMaxValueSize()` passed to `readArray` (lines 516, 673-674), which is not part of this helper. The helper itself bounds no held object.

**A3. Mechanism.** Enclosing method: [`ClusteringPrefix.java:575`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ClusteringPrefix.java#L575) `private static boolean isEmpty(long header, int i)` in `ClusteringPrefix.Serializer` (572-576). True: the element was written as an empty value (flag bit set by `makeHeader`, lines 548-561, `accessor.isEmpty(v)`), so no value bytes follow in the stream. False: the element is either null (the null bit checked first by `isNull`, 565-569) or has bytes to read/skip. Call sites read (all in `ClusteringPrefix.java`): 516 (`deserializeValuesWithoutSize`: choose empty array vs `readArray`), 535 (`skipValuesWithoutSize`: skip or not), 673 (`Deserializer.deserializeOne`), 708 (`Deserializer.skipNext`). Both outcomes only choose between "nothing to read" and "read one value"; no limit is reached.

**A4. Other consumers.** n/a: no resource constraint. The adjacent real limit is `max_value_size` (`DatabaseDescriptor.getMaxValueSize()`) on the `readArray` branch, a separate check outside this helper.

**A5. Evidence beyond the source.** Searched the helper's callers (the four sites above; no external callers since it is `private static` in `Serializer`, with `Deserializer` in the same outer class using it), the code comment at lines 541-547 (header = 2 bits per element: null/empty/neither), and the absence of any config key in the helper. Not tracked in docs or issues; none relied on.

## B. Verification solution

**B1. Claim under test.** This check does not cap memory or disk usage: it is a pure bit test on a header word and bounds no stored object.

### B2. Unit tier

n/a: no constraint. The helper has no limit to drive past; A1 (operands are a header word, a local bit mask and zero) and A3 (callers only choose empty-vs-read) answer the question instead.

### B3. Cluster tier

n/a: no constraint. There is no knob that moves the compared value toward a limit; A2 shows the only size cap on this path is the separate `max_value_size` check in `readArray`, which is not this target.

**B4. Risks and cleanup.** None; no run is proposed.

## C. Sources read

- src/java/org/apache/cassandra/db/ClusteringPrefix.java (lines 246, 455-580, 655-730)

## D. Stage-4 feedback

`none yet`
