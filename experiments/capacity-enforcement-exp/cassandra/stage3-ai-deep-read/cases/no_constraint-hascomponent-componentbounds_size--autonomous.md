# no constraint: MultiColumnRestriction.SliceRestriction.hasComponent() — verification solution

| Field | Value |
|---|---|
| Entry pointer | [`MultiColumnRestriction.java:580`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/MultiColumnRestriction.java#L580) (`return componentBounds.get(b).size() > index;`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `negative` — no constraint: the check compares a list size to a loop index to decide whether a tuple bound has a value at that column position; it bounds no memory or disk object. |
| Ground | Bookkeeping/ordering test over a per-query list that is already materialised; nothing is capped or held based on the outcome. |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Operands: `componentBounds.get(b).size()` (size of the `List<ByteBuffer>` of tuple elements for bound `b`, built by `componentBounds(Bound, QueryOptions)` at [`MultiColumnRestriction.java:563-572`] from `Tuples.Value.getElements()` or a singleton list of the terminal, origin: the client's query tuple literal/bind marker) and `index` (the method parameter, the loop counter `i` in `appendBoundTo`, `MultiColumnRestriction.java:440`, bounded by `columnDefs.size()`, i.e. the number of columns in the `(a,b,c) > (...)` clause). Neither comes from a yaml entry, JVM property or constant. Declaration/origin of the comparison: [`MultiColumnRestriction.java:580`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/MultiColumnRestriction.java#L580).

**A2. What it caps.** Nothing. The check could at most relate to the per-query tuple-bound lists, but it only tests whether one is long enough to have an element at position `index` (a tuple may have fewer values than columns, e.g. `(a,b) > (1)`); the lists are already built before the check, and the outcome only decides whether `appendBoundTo` skips a column or adds a value to a short-lived `values` list.

**A3. Mechanism.** Enclosing method: `SliceRestriction.hasComponent(Bound, int, EnumMap)` at `MultiColumnRestriction.java:578-581` (private). Callers, all in `SliceRestriction.appendBoundTo` (`:429-480`): `:453` (`!hasComponent(b,i,...)` -> `continue`, new bound side has no value for this column in a mixed-order direction switch), `:457` (`hasComponent(b.reverse(),...)` -> `toAdd.add(values)` to close the slice already open), `:475` (`!hasComponent(b,i,...)` -> `continue`, otherwise appends `componentBounds.get(b).get(i)` to `values`). True: the column position has a bound value and it is appended (null value rejected by `checkNotNull`); false: that column is skipped. Check: [`MultiColumnRestriction.java:580`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/MultiColumnRestriction.java#L580). No bypass or overshoot concept applies. The other method named `hasComponent` in `ClusteringPrefix.java:651` and `IndexDescriptor.java:157` are different methods and were not traced.

**A4. Other consumers.** n/a: no resource is governed. (The size of tuple values is limited elsewhere by the generic native-protocol frame / `native_transport_max_message_size`-style limits, unrelated to this check.)

**A5. Evidence beyond the source.** Searched `hasComponent` under `src/java` (callers above; only 3 call sites in this class, all in `appendBoundTo`); no config keys or properties are referenced in the class; no tests or docs consulted. `none`.

## B. Verification solution

**B1. Claim under test.** The comparison `componentBounds.get(b).size() > index` does not cap memory or disk usage; it is a positional-presence test over per-query tuple bound lists.

### B2. Unit tier
n/a: no constraint, there is no limit to push against; evidence in A1 (operands are a list size and a loop index with no limit/config) and A3 (both outcomes only skip or append one element in a transient list).

### B3. Cluster tier
n/a: no constraint, there is no resource cap to saturate; evidence in A2 (no memory or disk object bounded) and A3 (callers and outcomes).

**B4. Risks and cleanup.** n/a: nothing is run.

## C. Sources read

- src/java/org/apache/cassandra/cql3/restrictions/MultiColumnRestriction.java (lines 401-590)
- grep of `hasComponent` over src/java

## D. Stage-4 feedback

`none yet`
