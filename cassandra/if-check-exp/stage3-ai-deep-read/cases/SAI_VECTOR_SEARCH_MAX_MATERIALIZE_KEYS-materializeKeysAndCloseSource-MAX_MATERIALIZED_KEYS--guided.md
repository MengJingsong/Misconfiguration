# SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS — primary keys materialized for a hybrid vector query

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-MATERIALIZEKEYSANDCLOSESOURCE-MAX_MATERIALIZED_KEYS |
| **Constraint** | `SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS` — a **JVM system property**, `cassandra.sai.vector_search.max_materialized_keys`, declared in [`CassandraRelevantProperties.java:476`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L476) with a default of **16000** keys. Not a `cassandra.yaml` entry, no JMX or `nodetool` setter. It is copied once, at class initialization, into the **non-final** `public static int` [`QueryController.MAX_MATERIALIZED_KEYS`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L96), the operand at the check: restart-only on a node, writable from inside the JVM (tests, a Byteman rule). |
| **Enforcement pattern** | **(a)** — the comparison sits inside the loop that builds the key list, and on disallow it returns before another key is added: the `if` is the decision for the list's growth. Its `null` return is then read by the caller ([`QueryController.java:393`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L393)), which **switches the query to a different plan** rather than refusing it (§5). |
| **Capacity check** | [`QueryController.materializeKeysAndCloseSource():449`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L449) — `MAX_MATERIALIZED_KEYS < ++count`. One site; no other code reads the constant (the upstream test writes it, §9b). |
| **Decision point** | The same line ([`:449-453`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L449-L453)); its verdict (`null` or the list) is read at [`QueryController.getTopKRows(KeyRangeIterator, …):390-398`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L390-L398), which picks the plan. |
| **Allocation site** | [`QueryController.materializeKeysAndCloseSource():445-448`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L445-L448) — `source.next()` materializes a `PrimaryKey` from the index (for an SSTable index, a new key read from disk: [`PostingListRangeIterator.java:114`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/postings/PostingListRangeIterator.java#L114) → [`SkinnyPrimaryKeyMap.java:148-151`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/SkinnyPrimaryKeyMap.java#L148-L151)) and `primaryKeys.add(next)` retains it in the `ArrayList` created at [`:441`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L441). Downstream, the allow plan sizes per-index structures by the list ([`VectorIndexSegmentSearcher.orderResultsBy():288-299`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java#L288-L299), [`VectorMemoryIndex.orderResultsBy():214-233`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java#L214-L233)). |
| **Related cases** | None filed in `sai`. No other case bounds a per-query structure by a **count**; the closest is `local_read_size_fail_threshold` (a per-command byte total that aborts), whose disallow refuses where this one re-plans. |

```java
// QueryController.materializeKeysAndCloseSource():428-457 — the capacity check and decision point.
private List<PrimaryKey> materializeKeysAndCloseSource(KeyRangeIterator source)
{
    try (source)
    {
        ...
        List<PrimaryKey> primaryKeys = new ArrayList<>();                          // :441
        int count = 0;
        while (source.hasNext())
        {
            PrimaryKey next = source.next();                                       // :445 key materialized
            if (hasLimitingMaxToken && next.compareTo(maxToken) > 0)
                break;
            primaryKeys.add(next);                                                 // :448 retained
            if (MAX_MATERIALIZED_KEYS < ++count)                                   // :449 <-- capacity check
            {
                Tracing.trace("WHERE clause generated more than {} rows. Switching to ORDER BY then post filter.",  MAX_MATERIALIZED_KEYS);
                return null;                                                       // DISALLOW: list dropped, no more keys
            }
        }
        return primaryKeys;                                                        // ALLOW: every matching key, <= MAX
    }
}
```

```java
// QueryController.getTopKRows(KeyRangeIterator, QueryExpressionView):390-398 — reads the verdict.
public CloseableIterator<PrimaryKeyWithScore> getTopKRows(KeyRangeIterator source, QueryViewBuilder.QueryExpressionView queryExpressionView)
{
    List<PrimaryKey> primaryKeys = materializeKeysAndCloseSource(source);
    if (primaryKeys == null)
        return getTopKRows(queryExpressionView);          // DISALLOW: ANN over the whole index, then post-filter
    if (primaryKeys.isEmpty())
        return CloseableIterator.empty();
    return getTopKRows(primaryKeys, queryExpressionView); // ALLOW: order only the materialized keys
}
```

## 2. Context

Cassandra 5.0's storage-attached indexes (SAI) can answer a **hybrid vector
query**: "the 10 rows whose embedding is nearest this vector, among rows where
`category = 'x'`". There are two ways to run it. The first applies the
ordinary filter first, collects the key of every row that passes, and then
ranks only those rows by vector distance; it is exact and cheap when few rows
pass, but it holds every passing key in memory at once. The second walks the
vector index from the nearest vector outwards and checks each row against the
filter as it goes, stopping once it has 10 rows that pass; it holds no list,
but when the filter rejects most rows it reads many rows to find 10. This
check chooses between them: while collecting keys for the first plan, the
replica counts them, and once the count passes a fixed limit (16,000 keys by
default) it throws the collected list away and switches to the second plan.
The limit therefore caps how many keys one query can hold for the first plan.
It does not refuse the query, and it is not a cap on the query's memory as a
whole: the second plan keeps state of its own that the limit does not bound
(§6b, §8).

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | `sai` — storage-attached secondary indexes, vector (ANN) query planning (`index/sai/plan`, `index/sai/disk/v1`, `index/sai/memory`) |
| **One-line role** | Answers `WHERE` and `ORDER BY … ANN OF` queries from per-SSTable and per-memtable index structures, on each replica. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | Yes — a running count of keys materialized into one list, against a fixed maximum; past it the list stops growing and is dropped. |
| **Usage-side operand** | `count`, a local of `materializeKeysAndCloseSource()`, incremented after each `primaryKeys.add(next)`; it always equals `primaryKeys.size()`. |
| **Limit-side operand** | `MAX_MATERIALIZED_KEYS`, a `public static int` of `QueryController`. |
| **Limit type** | JVM system property (`CassandraRelevantProperties`), read once at class initialization. No range validation: any `int` is accepted (§8 for 0, negative and `Integer.MAX_VALUE`). |

**Limit initialization path:**

1. [`CassandraRelevantProperties.java:476`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L476) — declared: `SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS("cassandra.sai.vector_search.max_materialized_keys", "16000")`; its Javadoc ([`:467-475`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L467-L475)) states the purpose: "Increasing this limit allows more primary keys to be buffered in memory".
2. [`QueryController.java:96`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L96) — configured and stored: `public static int MAX_MATERIALIZED_KEYS = CassandraRelevantProperties.SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS.getInt();`, evaluated when `QueryController` is first loaded (the first SAI query), so `-D` at JVM start is the only production setting.
3. [`QueryController.java:449`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L449) — read at the point of comparison, on every key. Because the field is read at each comparison, a write to it (a test, a Byteman rule) takes effect on the next key.

**Name.** The queue (`pending.md` item 8) carried the operand's name,
`MAX_MATERIALIZED_KEYS`. Traced to its declaration it is the
`CassandraRelevantProperties` constant, which names the case per README §6.1,
as `MAX_HINT_BUFFERS` and `CACHEABLE_MUTATION_SIZE_LIMIT` were named; the
operand keeps its own name in the file name's third part.

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`QueryController.materializeKeysAndCloseSource():449-453`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L449-L453); the verdict is read at [`getTopKRows():393-394`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L393-L394) |
| **Verdict** | n/a — the check is the decision for the list. Its outcome leaves the method as the return value: the list (allow) or `null` (disallow); the caller treats `null` as "use the other plan". |

**Where the check is reached.** Only on a **hybrid** top-k query: a `SELECT …
ORDER BY <vector> ANN OF … LIMIT k` with at least one other indexed
restriction. `StorageAttachedIndexSearcher.search()` builds a
`ScoreOrderedResultRetriever` for every top-k command
([`StorageAttachedIndexSearcher.java:131-149`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/StorageAttachedIndexSearcher.java#L131-L149)), whose constructor calls
[`Operation.buildIteratorForOrder():331-340`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/Operation.java#L331-L340):
with a single expression (the ANN alone) it goes straight to the ANN plan and
never materializes; otherwise it builds the filter's `KeyRangeIterator` and
calls `getTopKRows(iterator, view)`. A top-k range read is sent to each replica
**once, for all of its ranges**
([`RangeCommands.java:81-82`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/range/RangeCommands.java#L81-L82),
`ScanAllRangesCommandIterator`), so the check runs once per query per replica,
over every key on that replica that passes the filter, not once per vnode.

**Boundary.** `count` is incremented after the add, so with limit *L* and *M*
keys passing the filter (within the command's range):

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow** | *M* ≤ *L* (the loop ends with `source.hasNext()` false, or at the range's right bound) | Returns the list of *M* keys. The caller orders only those keys by vector distance (`getTopKRows(List, …)`, [`:400-420`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L400-L420)). |
| **Disallow** | *M* > *L*: fires when the (*L* + 1)-th key has been added | Traces one line, returns `null`; the list of *L* + 1 keys becomes garbage and the source is closed (`try (source)`). The caller runs the plain ANN plan over the whole index (`getTopKRows(view)`, [`:367-387`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L367-L387)) and the retriever re-applies the filter to each row it reads. |

```java
// allow-outcome body (:443-456): keep accumulating, then
return primaryKeys;
```

```java
// disallow-outcome body (:451-452)
Tracing.trace("WHERE clause generated more than {} rows. Switching to ORDER BY then post filter.",  MAX_MATERIALIZED_KEYS);
return null;
```

**Rule 3.** The branches diverge on object creation in two places. (1) At the
check: allow materializes and retains one more `PrimaryKey` per further
matching row; disallow materializes none, and frees the *L* + 1 it holds. (2)
At the caller: allow builds structures sized by the list in every index of the
query view (§6a); disallow builds the ANN search's state, which does not
depend on *M*, plus the retriever's set of rejected keys (§6b). Both branches
allocate at (2), so the limit **withholds** the list's growth and **replaces**
the plan; it does not withhold every allocation of the query. This is the
weaker form of Rule 3 already accepted for `column_index_cache_size` and
`CACHEABLE_MUTATION_SIZE_LIMIT` (the divergence is what is retained).

**Why (a) and not (b).** What the limit directly withholds, the next key in the
list, is withheld by the `if` itself, in the loop that allocates it. The
caller's `null` test chooses which downstream structures are built, and both of
its branches allocate; it is recorded here as the place the plan changes, not
as the decision point the limit acts through.

## 6. Code path

### 6a. Allow path → object creation

1. [`StorageAttachedIndexSearcher.ScoreOrderedResultRetriever.<init>():641`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/StorageAttachedIndexSearcher.java#L641) → [`Operation.buildIteratorForOrder():338-339`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/Operation.java#L338-L339) — the filter's `KeyRangeIterator` (one iterator for one non-ANN expression; an intersection or union for several, [`QueryController.getIndexQueryResults():248-321`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L248-L321)) is passed to `getTopKRows(source, view)`.
2. [`QueryController.materializeKeysAndCloseSource():443-448`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L443-L448) — each `source.next()` yields a `PrimaryKey`. **From an SSTable index it is a new object** read from disk ([`PostingListRangeIterator.computeNext():114`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/postings/PostingListRangeIterator.java#L114) → [`SkinnyPrimaryKeyMap.primaryKeyFromRowId():148-151`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/SkinnyPrimaryKeyMap.java#L148-L151) → [`readPartitionKey():205-208`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/SkinnyPrimaryKeyMap.java#L205-L208) → [`PrimaryKey.Factory.partitionKeyFromComparableBytes():151-155`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/utils/PrimaryKey.java#L151-L155): a `byte[]`, a `HeapByteBuffer`, a token, a `BufferDecoratedKey`, then [`create(DecoratedKey):102-108`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/utils/PrimaryKey.java#L102-L108) a `SkinnyPrimaryKey`). **From a memtable index it is a reference** to a key the memtable already holds (`InMemoryKeyRangeIterator`). `primaryKeys.add(next)` retains it; the check at `:449` allows.
3. [`QueryController.getTopKRows():397`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L397) → [`getTopKRows(List, …):405-408`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L405-L408) — the list is passed to every memtable index and every SSTable index in the view.
4. **SSTable index, per segment:** [`V1SSTableIndex.orderResultsBy():189-196`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/V1SSTableIndex.java#L189-L196) → [`VectorIndexSegmentSearcher.orderResultsBy():288-291`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java#L288-L291) copies the keys between the segment's `minKey` and `maxKey` into `keysInRange`, then **[`:299`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java#L299) `new SegmentRowIdOrdinalPairs(keysInRange.size())`**, an `int[2 × keysInRange.size()]` allocated up front ([`SegmentRowIdOrdinalPairs.java:40-46`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/vector/SegmentRowIdOrdinalPairs.java#L40-L46)), filled only with the keys whose row is in this segment ([`:300-316`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java#L300-L316)). Then brute force (a `NeighborQueue` of the pairs found, [`:326-328`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java#L326-L328)) or a graph search restricted to their ordinals ([`:331-336`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java#L331-L336)). **Derived:** a segment's `[minKey, maxKey]` covers nearly the whole ring when its SSTable's partitions are spread over the ring, so `keysInRange` and the pair array are about *M* long **in every segment**, though only the segment's own share is filled; the allow plan's arrays are about *S* × *M* entries for *S* segments.
5. **Memtable index:** [`VectorMemoryIndex.orderResultsBy():214-217`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java#L214-L217) copies the keys within its bounds; brute force builds an `ArrayList<PrimaryKeyWithScore>` and a `PriorityQueue` of them ([`:230`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java#L230), [`:251-260`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java#L251-L260)); otherwise a `KeyFilteringBits` over the list ([`:233`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java#L233)).

The list and everything sized by it live for the command: the merged iterator
is drained by `VectorTopKProcessor.takeTopKThenSortByPrimaryKey()`
([`VectorTopKProcessor.java:168-185`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/VectorTopKProcessor.java#L168-L185)) and released when the command ends.

### 6b. Disallow path effect

1. [`QueryController.materializeKeysAndCloseSource():449-452`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L449-L452) — the (*L* + 1)-th key is already added; one trace line; `return null`. The `try (source)` closes the index iterators; the list (*L* + 1 keys) is unreachable from here on. **No key after the (*L* + 1)-th is materialized for the list.** No exception, no metric, no log line: the trace line (written only when the query is traced) is the only external sign, and it is produced nowhere else (`grep -rn "Switching to ORDER BY" src/java` finds this line only).
2. [`QueryController.getTopKRows():393-394`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L393-L394) → [`getTopKRows(view):367-379`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L367-L379) — an ANN search of every memtable and SSTable index **over the whole command range**, as for a query with no filter. On an SSTable segment it is [`VectorIndexSegmentSearcher.orderBy():111-126`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java#L111-L126) → [`searchInternalUnrestricted():208-212`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java#L208-L212) for a full-ring read, a search that **resumes until the graph is exhausted** if asked ([`DiskAnn.search():117-120`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/vector/DiskAnn.java#L117-L120)). Nothing in it is sized by *M* or *L*.
3. [`ScoreOrderedResultRetriever.fillPendingRows()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/StorageAttachedIndexSearcher.java#L663-L689) pulls keys in score order and [`readAndValidatePartition():763-825`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/StorageAttachedIndexSearcher.java#L763-L825) reads each row from storage (`partitionsRead++`, `:773`) and applies the filter (`filterPartition`); **every key whose row fails the filter is added to `processedKeys`** ([`:782`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/StorageAttachedIndexSearcher.java#L782), [`:802`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/StorageAttachedIndexSearcher.java#L802)), a `HashSet` that lives until the retriever is closed. It stops when *k* rows pass, the index is exhausted, or the query's time quota expires (`queryContext.checkpoint()`, `:774`, throws `QueryCancelledException` past `range_request_timeout`: [`QueryContext.java:85-92`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/QueryContext.java#L85-L92), quota set at [`StorageAttachedIndexQueryPlan.java:134-141`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/StorageAttachedIndexQueryPlan.java#L134-L141)).

**The real effect.** The disallow branch does not reject the query and the
client sees the same kind of answer (*k* rows, each passing the filter; the
filter is applied to the stored row on both plans). It trades the list for
work: the number of rows read on the ANN plan depends on how the filter's
matches are placed in vector space, not on *L*. When the rows nearest the
query vector mostly fail the filter, the plan reads (and keeps in
`processedKeys`) up to every non-matching row before the first match: up to
*N* − *M* keys for a replica holding *N* rows. **The disallow branch's own
retention is therefore not bounded by *L*,** and on such data it exceeds what
the allow branch would have held (*M* keys, with *M* only just above *L*).
Recorded for Target 3 (§10); the test measures it (scenario C2).

**Non-domination before the check (memtable data).** A memtable term index
collects **all** its matches before the iterator is handed to the check: a
range restriction drains its trie into a `PriorityQueue` in
[`TrieMemoryIndex.rangeMatch():352-361`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java#L352-L361),
and an equality builds one from the term's key set
([`exactMatch():257-263`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java#L257-L263) →
[`InMemoryKeyRangeIterator.java:38-42`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/InMemoryKeyRangeIterator.java#L38-L42)).
Those queues hold references to keys the memtable already owns (one array slot
per match), whatever *L* is. SSTable postings are streamed and not collected
ahead of the check.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | `PrimaryKey` (`PrimaryKey$Factory$SkinnyPrimaryKey` for a table without clustering columns; `WidePrimaryKey` with a `Clustering` otherwise) and the `ArrayList<PrimaryKey>` holding them; downstream on allow, per index segment an `ArrayList` copy and a `SegmentRowIdOrdinalPairs` (`int[]`). |
| **Resource consumed** | Heap bytes, per query, on each replica. |
| **Rough sizing** | Per SSTable-derived skinny key with an `int` partition key, with compressed oops (derived from the fields, not measured): `SkinnyPrimaryKey` 24 B + `LongToken` 24 B + `BufferDecoratedKey` 24 B + `HeapByteBuffer` 48 B + `byte[4]` 24 B ≈ **144 B**, plus 4 B of list slot (the `ArrayList` grows by half, so up to about 6 B per key of backing array). Longer keys add their bytes; a wide key adds its `Clustering` and buffers. A memtable-derived key costs only the slot. Downstream, per segment: `keysInRange` (4 B per key) and `int[2 × keysInRange]` (8 B per key). At the default *L* = 16,000: the list ≈ 2.4 MB at the refusal (16,001 keys); allowed at *M* = 16,000 with *S* = 4 segments, plus ≈ 16,000 × 4 × 12 B ≈ 0.8 MB of per-segment arrays. |
| **Lifetime / release** | The list lives from the first key to the end of `getTopKRows()` on disallow (garbage at once), or to the end of the command on allow (referenced by the per-index iterators). Nothing is pooled or accounted; the garbage collector reclaims it. |

## 8. Maximum memory/disk bound

**What the limit bounds.** For one hybrid top-k command on one replica, the
key list holds at most **min(*M*, *L* + 1)** keys, so at most about
(*L* + 1) × *b* bytes, *b* the per-key cost of §7 (≈ 148 B for SSTable-derived
`int` keys). The allow plan's per-segment arrays follow the same list: at most
about *S* × *L* × 12 B for *S* segments (derived, §6a step 4). Raising *L*
raises both in proportion; lowering it lowers them. The bound is **per
command**: node-wide, the number of hybrid top-k commands in flight multiplies
it, which the read stage's thread count caps (`concurrent_reads`, 32 by
default: at most 32 × (*L* + 1) keys, about 76 MB at the default *L* and
*b* = 148 B). **Derived from reading**, not observed.

**What it does not bound.**

- **The disallow plan.** Past the limit the query is not refused; it runs the
  ANN plan, whose `processedKeys` set grows with every row it reads and
  rejects (§6b). That growth depends on the data, not on *L*, and is limited
  only by the rows on the replica and by the read timeout. Lowering *L* can
  therefore **raise** a query's peak heap: a query whose matches are far from
  the query vector holds up to *N* − *M* rejected keys on the ANN plan,
  against *M* keys on the list plan. The knob selects a plan; it caps one plan's
  memory, not the query's.
- **Memtable matches** are collected before the check (§6b, references only).
- **Escape values.** *L* ≤ 0: every hybrid query that matches at least one
  key is switched at its first key (the list holds 1 key), so the list plan is
  never used. *L* = `Integer.MAX_VALUE`: `count` cannot pass it before the list
  is out of memory, so the list holds every match on the replica (*M* keys);
  the check is off. Neither value is rejected at start-up.

**Shape.** Linear in *L*, with a slope of *b* per key, until *M* ≤ *L* for the
workload, where the list holds *M* and the knob stops mattering.

## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers
and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../stage4-runtime-verification/README.md).
The test drives hybrid vector queries with a known number of matching rows
around the limit, at several limits, and reads the list's size at the check,
the plan taken, and the keys held on the heap. **Run so far:** none.

*Amended 2026-10-15 (stage-4 audit, before any reading; rec. numbers are those of the results file's §1).* (1) **`TotalPartitionReads`
does not move for a top-k query:** only the plain `ResultRetriever.close()` calls `tableQueryMetrics.record(queryContext)`
([`StorageAttachedIndexSearcher.java:520-524`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/StorageAttachedIndexSearcher.java#L520-L524)); `ScoreOrderedResultRetriever.close()` (`:828-831`) closes its
iterator and records nothing. C2's partition reads are therefore read from the same field the metric would have summed,
`queryContext.partitionsRead` (`:773`), printed by rule (7) at the retriever's `close()` as `reads=`; the prediction's numbers
are unchanged. (2) **C2's far-matches data is built by rank, not as two antipodal clusters:** two tight clusters at *q* and −*q*
are near-duplicate vectors under cosine similarity, and nothing guarantees the graph links them, so the resumed search
(`AutoResumingNodeScoreIterator`, [`DiskAnn.java:117-120`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/vector/DiskAnn.java#L117-L120)) could end without reaching the matches, an outcome
with no row. Instead every vector is drawn as for `ks.t` and `i` is the row's rank by cosine similarity to *q*, ascending
(9b), so the *M* matches are exactly the *M* rows least similar to *q*; a conclusions row for a C2 query returning fewer than
*k* rows is added. (3) **The `ann` line also marks the ANN-only control**, which enters the same
`getTopKRows(QueryExpressionView)` ([`Operation.java:333-335`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/Operation.java#L333-L335)); "if and only if" applies to hybrid queries. (4) **The unit
tier loads its rules with `-javaagent`** (as the `native_transport_receive_queue_capacity` harness), not `BMUnitRunner`: no SAI
test uses the runner, and the rules call a static recorder in the test either way. (5) Hold point (c) is `AT NEW
InMemoryUnfilteredPartitionIterator` in `takeTopKThenSortByPrimaryKey()`, whose only caller is the searcher (`:148`).

### 9a. Procedure and conclusions

**Testability:** JVM system property, **restart-only** on a node
(`-Dcassandra.sai.vector_search.max_materialized_keys=<L>`); in a unit test
the field `QueryController.MAX_MATERIALIZED_KEYS` is written directly and takes
effect on the next comparison, as the upstream test does.

**Claim under test:** on a hybrid top-k query, the replica's key list grows to
min(*M*, *L* + 1) keys; at *M* > *L* the check drops it at the (*L* + 1)-th key
and the query switches to the ANN-then-filter plan; the list's heap moves in
proportion to *L*; and the ANN plan's rejected-key set is not bounded by *L*
(§5, §6b, §8).

**How this verifies the hypothesis** (a restatement of the claim, procedure,
prediction and conclusions in this section; it adds none):

- **Hypothesis:** `SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS` caps the number of
  keys (and so the heap) one hybrid query holds for the list plan; past it the
  list is dropped and the plan changes, and the other plan's retention does not
  follow the knob.
- **Test:** unit tier: the check on a CQL table in one JVM, *L* set per query,
  *M* placed at *L* − 1, *L*, *L* + 1 and 4*L*; heap per key from the list
  itself; the escape values; the per-segment arrays; a data set where the
  matches are the rows farthest from the query vector. Cluster tier: one node,
  200,000 rows in 4 SSTables, *L* = 1,000, 4,000, 16,000 (default), 64,000 by
  restart; queries with *M* = *L*, *L* + 1 and 4*L*; eight concurrent queries
  held at the check for a heap histogram; the escape values; the far-matches
  table at three *L*.
- **Logic:** (1) the trace instrument shows the check reached with *M* keys
  available (else the run is invalid); (2) the list reaches exactly *M* when
  *M* ≤ *L* and stops at exactly *L* + 1 when *M* > *L*: usage **stops at the
  limit**; (3) the keys held per query move 1 : 4 : 16 : 64 with *L*: usage
  **follows the constraint**; (4) the trace line and the ANN-plan entry appear
  exactly when the list is dropped: the **disallow branch** enforces it;
  (5) the heap histogram's key count matches the list sizes: the counter
  tracks the real resource; (6) on the far-matches table the ANN plan reads and
  holds about *N* − *M* keys at every *L* below *M*: the switch is not a
  memory bound for the query.
- **Refuted if:** a list holds more than *L* + 1 keys with the check enabled;
  the switch happens at a count other than *L* + 1; the held keys do not move
  with *L*; the histogram's key count does not match the list sizes; or a query
  returns rows that fail the filter (rows of the Conclusions table).

**Procedure:**

1. **Unit tier** — harness test `MaterializedKeysLimitTest` (9c), steps U1–U5 in
   9e. Also run upstream `VectorTypeTest#testTooManyMaterializedKeys`.
2. **Cluster tier** — one node (9b), data loaded once, the node restarted
   once per *L*.
3. **At each *L*:** control (an ANN-only query, which never reaches the check)
   → **scenario A**, *M* = *L*: the list reaches the limit and is kept →
   **scenario B**, *M* = *L* + 1 and 4*L*: the list is dropped at *L* + 1, and
   eight held queries give the heap reading → **scenario C**, the arms where
   the check does not act as its value says: C1 the escape values, C2 the
   far-matches table (the disallow plan's own retention).
4. **Compare** with the prediction and read the result below.

**Prediction.** Notation: *L* the limit; *M* the rows passing the filter on
the replica (all rows here, one node); *N* the table's rows; *S* the SSTables
(one segment each, 9b); *Q* = 8 concurrent queries; *b* the heap per
SSTable-derived key, from U2.

- **List size at the check** (`mat` lines, 9d): *M* ≤ *L* → returned list of
  *M*; *M* > *L* → `null`, with exactly *L* + 1 keys in the list and `count` =
  *L* + 1 at the refusal. One `mat` line per query (one command per replica,
  §5). The ANN-only control: no `mat` line (*amended 2026-10-15, rec. 3:* and one `ann` line, the same method).
- **Plan:** on a hybrid query, the ANN-plan entry (`ann` line) and the trace event "WHERE clause
  generated more than *L* rows" appear **if and only if** the list is `null`;
  the list plan's entry (`hybrid size=<M>`) appears otherwise.
- **Heap per key:** U2's slope *b* is between 120 and 200 B for `int`
  partition keys (§7 derives ≈ 148 B), the same within 2 % at every pair of *L*.
- **Held keys, cluster (scenario B, *M* = 4*L*, *Q* = 8 held at the
  refusal):** the change in live `SkinnyPrimaryKey` instances from the idle
  baseline is *Q* × (*L* + 1) = 8,008 · 32,008 · 128,008 · 512,008 at *L* = 1,000
  · 4,000 · 16,000 · 64,000 (the last at *M* = 200,000), each within 1 % +
  100 instances; `BufferDecoratedKey`'s change is the same count within the
  same tolerance. Scenario A (*M* = *L*, held at the method's exit): *Q* × *L*.
  Ratios 1 : 4 : 16 : 64 across *L*. Bytes: the change in the five classes of
  §7 is the count × *b* within 10 % (the `[B`, `HeapByteBuffer` and `LongToken`
  baselines are shared and noisy; the two key classes decide).
- **Per-segment arrays (allow, *M* = *L*):** *S* = 4 `pairs` lines per query, each
  with capacity ≥ *M* − 50 (derived, §6a step 4: about *M* in every segment).
- **C1:** *L* = 0 → every hybrid query refuses with 1 key in the list;
  *L* = 2,147,483,647 → no refusal, the list holds *M* = 200,000, and held *Q* ×
  200,000 instances.
- **C2 (far-matches table, *N* = 50,000, the 16,001 rows with `i` ≤ 16,001
  pointing away from the query vector, query `i <= 16001 … LIMIT 10`):**
  at *L* = 1,000 and 16,000 (*M* > *L*): refusal; partition reads per query
  (*amended 2026-10-15, rec. 1:* `reads=`, the retriever's `queryContext.partitionsRead`, which `TotalPartitionReads` would sum
  but does not record for top-k) at least 0.9 × (*N* − *M*) = 30,599 and at most
  *N*; `processed=` (which counts the accepted keys as well as the rejected ones, `:816`) equal to the partition reads within 10;
  held (*Q* = 8, at the end of the top-k loop) at least 0.9 × *Q* × 33,999 =
  244,792 live `SkinnyPrimaryKey`, above the *Q* × 16,001 = 128,008 the list plan
  would hold. At *L* = 64,000 (*M* ≤ *L*): no refusal, list of 16,001,
  partition reads ≤ 20 per query.
- **Every query** returns 10 rows, each with `i` ≤ *M* (both plans).

**Conclusions:**

| Result | Conclusion |
|---|---|
| Lists stop at *L* + 1 with a refusal, reach *M* below it, the plan switch and trace appear exactly at refusals, held keys move 1 : 4 : 16 : 64 and match *Q* × list size | **Confirmed** — the limit caps the list as traced. |
| C1: *L* = 0 refuses at 1 key; *L* = 2^31 − 1 never refuses and holds *M* | **Escape values as recorded** — Target-3 material; record the held count. |
| C2: the ANN plan reads and holds about *N* − *M* keys at *L* < *M*, more than the list would | **Disallow retention as recorded** — the knob is not a bound on the query (§8); Target-3 material. |
| A list holds more than *L* + 1 keys, or a refusal comes at a count other than *L* + 1 | **Refuted** — the check does not cap the list as traced. |
| The held key count does not move with *L* while *M* > *L* | **Refuted** — not the binding limit; re-read §6a, do not re-run. |
| The `mat` sizes follow *L* but the histogram's key count does not match *Q* × list size | **Refuted** for §7/§8 — the list is not what holds the keys (or they are not new objects); re-read the source of `source.next()`. |
| A refusal with no `ann` line, or an `ann` line with no refusal | **Refuted** — the verdict is read elsewhere than traced (§5). |
| *Added 2026-10-15 (rec. 2):* a C2 query on the ANN plan returns fewer than 10 rows (no error) | **Not confirmed** for §6b — the resumed search ended before reaching the matches; record `reads=` and the rows returned. |
| C2 at *L* < *M* reads ≤ 20 rows per query | **Not confirmed** for §6b's retention claim — the ANN plan did not meet the far matches first; check the data's vectors (9c) before concluding. |
| `pairs` capacities are near *M* / *S* rather than *M* | **Not confirmed** for §6a step 4's derived sizing (segments do not span the ring); the case's claim does not rest on it. Record it. |
| A query returns a row with `i` > *M* | **Refuted** for the "same answer" claim of §6b. |
| The knob read-back differs from *L*, a query has two `mat` lines or none, or the trace event is missing on a traced refusal | **Invalid run** — fix the set-up (9b) or the instrument and repeat that *L*. |

**Why the list and a key count, not heap totals:** the list lives for one
query and the heap holds the table's other state; the `mat` line gives the
exact count, the held histogram shows the keys are new objects on the heap,
and U2 gives the bytes per key.

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | Node: `-Dcassandra.sai.vector_search.max_materialized_keys=<L>` appended to `conf/jvm-server.options` (or `JVM_EXTRA_OPTS`), then restart. Unit: `QueryController.MAX_MATERIALIZED_KEYS = <L>` before the query, restored in `finally`, as [`VectorTypeTest.java:697-722`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/index/sai/cql/VectorTypeTest.java#L697-L722). |
| **Confirm it took effect** | The `mat-trace.btm` start-up line `limit=<L>` (it prints `QueryController.MAX_MATERIALIZED_KEYS` at the first `materializeKeysAndCloseSource()` entry); `jcmd <pid> VM.system_properties \| grep max_materialized`; the trace event prints the value too. |
| **Capacity values** | *L* = 1,000, 4,000, 16,000 (default, no `-D`), 64,000; C1: 0 and 2,147,483,647. |
| **Scope** | Per command per replica (§8). One node: one command per query. *Q* = 8 concurrent queries for the heap reading, below `concurrent_reads` (32). |
| **Level** | Both. Upstream [`VectorTypeTest.testTooManyMaterializedKeys():697-722`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/index/sai/cql/VectorTypeTest.java#L697-L722) reaches the refusal at *L* = 10 and asserts only the row count. |

**Data (loaded once, 9c).** Keyspace `ks`, `SimpleStrategy` RF 1.

- `ks.t (pk int PRIMARY KEY, i int, val vector<float, 8>)`, SAI on `i` and on
  `val` (`USING 'StorageAttachedIndex'`); *N* = 200,000 rows, `pk` = `i` = 1…*N*,
  `val` 8 floats drawn from a seeded normal distribution (independent of `i`).
  Rows inserted in a seeded random order and flushed after every 50,000, so
  *S* = 4 SSTables each spread over the ring.
- `ks.far` (same schema), *N* = 50,000: ~~rows with `i` ≤ 16,001 get `val` =
  −*q* + ε, the others *q* + ε, with *q* the query vector and ε small seeded
  noise (|ε| ≤ 0.01 per component); one flush.~~ *Amended 2026-10-15 (rec. 2):* 50,000
  vectors drawn as for `ks.t` (its own seed); `i` = `pk` = the vector's rank by cosine similarity to *q*, ascending
  (`i` = 1 the least similar), so `i` ≤ 16,001 selects exactly the 16,001 rows farthest from *q*; inserted in a seeded
  random order; one flush.

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| `data_file_directories` | one directory | A vector index refuses more than one ([`StorageAttachedIndex.java:302-303`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java#L302-L303)). |
| Compaction | table option `compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'}` at creation | Keeps *S* = 4 across the sweep (the per-segment prediction). |
| Memtables | flushed before every query run (`nodetool flush ks`) | Memtable keys are references, not new objects (§6a step 2); the heap prediction is for SSTable keys. |
| `range_request_timeout` | `120s` | The SAI quota is this value ([`StorageAttachedIndexQueryPlan.java:134-141`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/StorageAttachedIndexQueryPlan.java#L134-L141)); a 15 s hold or the C2 reads must not cancel the query. |
| `read_request_timeout`, `native_transport_timeout` | `120s`, `180s` | The coordinator waits for the nearer of these and the verb timeout (the 2026-10-14 trap in HANDOFF). The client's own timeout ≥ 200 s. |
| `MAX_HEAP_SIZE` | `4G`, G1 | The largest held reading, C1's 8 × 200,000 keys, is about 0.25 GB live at *b* ≈ 148 B; 8 × 512,008 at *L* = 64,000 about 76 MB. |
| Consistency | `ONE` | Top-k range reads require `ONE`/`LOCAL_ONE` (`ScanAllRangesCommandIterator`). |
| Query | `SELECT pk, i FROM ks.<t> WHERE i <= ? ORDER BY val ANN OF <q> LIMIT 10` | One non-ANN expression: a single iterator, so strict and non-strict filtering give the same key stream ([`QueryController.java:248-321`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L248-L321)), and *M* is exact. |

**Controls:** an idle node (histogram baseline); an ANN-only query
(`SELECT pk FROM ks.t ORDER BY val ANN OF <q> LIMIT 10`, no `mat` line); a
traced query at the default before the sweep.

**Reset between runs:** stop the node, change `-D`, start; no data change
(reads only). Take the idle histogram after each start, once the first query
has loaded `QueryController`.

### 9c. Workload

**Harness.** `<harness>` stands for
`<misconfiguration-repo>/cassandra/if-check-exp/stage4-runtime-verification/long-path/harness/SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS`.
Work for step 1, before run 1:

| File | What it is |
|---|---|
| `MaterializedKeysLimitTest.java` | Unit tier, package `org.apache.cassandra.index.sai.cql`, extends `SAITester`, ~~`@RunWith(BMUnitRunner.class)`~~ (*amended 2026-10-15, rec. 4:* the JVM loads `unit-trace.btm` with `-javaagent`) with the rules below calling a static recorder in the test. Steps U1–U5 (9e). Not `VectorTester`: it is parameterized over `FORCE_BRUTE_FORCE_ANN`, which this test leaves `null`. |
| `mat-trace.btm` | Byteman, observation only, on `org.apache.cassandra.index.sai.plan.QueryController`: (1) `materializeKeysAndCloseSource` AT ENTRY, first call: `limit=<MAX_MATERIALIZED_KEYS>`; (2) AT INVOKE `Tracing.trace` in that method: `mat refuse size=<$primaryKeys.size()> count=<$count> limit=<…>`; (3) AT EXIT: `mat exit returned=<null\|$!.size()>`; (4) `getTopKRows(QueryViewBuilder$QueryExpressionView)` AT ENTRY: `ann`; (5) `getTopKRows(java.util.List, QueryViewBuilder$QueryExpressionView)` AT ENTRY: `hybrid size=<$1.size()>`; (6) `SegmentRowIdOrdinalPairs.<init>` AT ENTRY: `pairs cap=<$1>`; (7) `StorageAttachedIndexSearcher$ScoreOrderedResultRetriever.close` AT ENTRY: `processed=<$0.processedKeys.size()>` (*amended 2026-10-15, rec. 1:* and `reads=<$0.this$0.queryContext.partitionsRead>`). Locals are visible: the build compiles with `debuglevel="source,lines,vars"`. |
| `hold.btm` | Byteman, loaded at start and gated by a flag file (as the `repair_session_space` harness): while `/tmp/mmk-hold` exists, sleep 15 s at (a) rule (2)'s point (refusal), (b) `materializeKeysAndCloseSource` AT EXIT (allowed lists), (c) AT INVOKE `InMemoryUnfilteredPartitionIterator.<init>` (*amended 2026-10-15, rec. 5:* `AT NEW`) in `VectorTopKProcessor.takeTopKThenSortByPrimaryKey` ([`VectorTopKProcessor.java:183`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/VectorTopKProcessor.java#L183), C2: the retriever and its `processedKeys` are still open); each writes `hold start <point>` and `hold end`. A file per point selects it. |
| `load.py` | Creates the schema and loads `ks.t` and `ks.far` (9b) with the driver bundled with `cqlsh` (as earlier harnesses' `send-*.py`); seeds printed; flushes as 9b says. |
| `query.py` | Runs one query or *Q* concurrent copies, at `ONE`, with a 200 s timeout; prints the rows, checks every `i` ≤ *M*, and with `--trace` prints the trace events. |
| `cluster-run.py`, `unit-run.sh` | The scripted tiers with `EXPECTED:` lines in `summary.txt`; stop the node on any exit. |

*Amended 2026-10-15 (unit shakedown 1, before run 1; §9a unchanged):* `MaterializedKeysLimitTest` extends `CQLTester`, not
`SAITester`, whose `ResourceLeakDetector` attaches a second Byteman agent (`Injections.loadAgent()`) that fails to initialize in
a JVM already running `unit-trace.btm`'s agent; and `VectorTypeTest` is parameterized (`VectorTester`), so `-Dtest.methods`
matches nothing: the whole class runs and the three `testTooManyMaterializedKeys[…]` cases are read from its report. The cluster
node runs with its own `CASSANDRA_CONF` and directories under `~/stage4-mmk` (`pc57` is shared with another session's node), and
a helper jar `Mmk.java` on the boot class path gates the holds (Byteman 4.0.20 cannot parse `new` in a condition, as in the
`repair_session_space` harness).

```bash
# unit tier
ant testsome -Dtest.name=org.apache.cassandra.index.sai.cql.VectorTypeTest -Dtest.methods=testTooManyMaterializedKeys
cp <harness>/MaterializedKeysLimitTest.java test/unit/org/apache/cassandra/index/sai/cql/
ant testsome -Dtest.name=org.apache.cassandra.index.sai.cql.MaterializedKeysLimitTest

# cluster tier: node started with -javaagent:build/lib/jars/byteman-4.0.20.jar=script:<harness>/mat-trace.btm,script:<harness>/hold.btm,listener:true
python3 <harness>/load.py --host 127.0.0.1                         # once
python3 <harness>/query.py --table t --m <M> [--q 8] [--trace]      # per reading
```

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — the list's size at the check | `mat exit returned=…` and `mat refuse size=… count=…` lines (`mat-trace.btm`) in the node's stdout log | Every query | One line per query is the validity check (§5); two would mean two commands. |
| **Disallow evidence** | `mat refuse` line, then `ann`; and on a `--trace` query the `system_traces.events` activity "WHERE clause generated more than *L* rows. Switching to ORDER BY then post filter." | Every query; trace once per (*L*, *M*) | The trace line is only written when the query is traced; the Byteman lines are the deciding evidence. |
| **Plan evidence** | `hybrid size=<M>` (list plan) or `ann` (ANN plan) | Every query | — |
| **Real resource, heap** | During a hold (after `hold start` for all 8 queries): `jmap -histo:live <pid> \| grep -E 'PrimaryKey\$Factory\$SkinnyPrimaryKey\|BufferDecoratedKey\|LongToken\|HeapByteBuffer\|^ *[0-9]+: .* \[B'`, minus the idle baseline | Once per held reading | `-histo:live` forces a full GC: once per reading. Memtable-derived keys are not new objects (flush first, 9b). |
| **Disallow plan's work (C2)** | ~~`TotalPartitionReads` … before and after one query~~ *amended 2026-10-15, rec. 1:* the `reads=` and `processed=` fields of rule (7)'s line; `TotalPartitionReads` is read before and after as a recorded side reading (expected unchanged: top-k does not record it) | Each C2 query | — |
| **Allow plan's arrays** | `pairs cap=` lines | Scenario A queries | One per segment searched; a memtable index adds none. |

### 9e. Running the scenarios

**Unit tier.** Commands in 9c. Each step records the `mat`, `ann`, `hybrid`,
`pairs` and `processed` lines through the recorder and asserts on them.

1. **U1, the boundary:** table as `ks.t` with 2-dimensional vectors, *N* = 4,010 rows, `pk` = `i`, flushed. For *L* in {10, 100, 1,000} and *M* in {*L* − 1, *L*, *L* + 1, 4*L*}: run the query (`LIMIT 3`). Assert: *M* ≤ *L* → `returned=M`, `hybrid size=M`, no `ann`; *M* > *L* → `refuse size=L+1 count=L+1`, `returned=null`, `ann`; 3 rows, each `i` ≤ *M*. Repeat once on unflushed data (memtable index) at *L* = 100: the same outcomes.
2. **U2, heap per key:** *N* = 16,010, flushed. At the refusal for *L* = 100, 1,000, 4,000 (*M* = 4*L*), record `ObjectSizes.measureDeep($primaryKeys)` from rule (2). *b* = the slope between each pair of *L*; assert 120 ≤ *b* ≤ 200 and the three slopes within 2 %.
3. **U3, the escape values:** on U2's table, *L* = 0 with *M* = 5: `refuse size=1`; *L* = `Integer.MAX_VALUE` with *M* = 16,000: `returned=16000`, no refusal.
4. **U4, per-segment arrays:** *N* = 16,000 inserted in shuffled order, flushed after every 4,000 (*S* = 4), *L* = *M* = 4,000: four `pairs cap=` lines, each ≥ 3,950.
5. **U5, the disallow plan's retention:** a far-matches table (*N* = 2,000; `i` ≤ 101 the rows least similar to *q*, built by rank as `ks.far`, amended 2026-10-15), query `i <= 101 … LIMIT 3`: at *L* = 100, a refusal and `processed=` ≥ 0.9 × 1,899 = 1,709; at *L* = 1,000, no refusal and `processed=` ≤ 10 (the 3 accepted keys and any stale ones). Both return 3 rows with `i` ≤ 101.

**Cluster tier** (one node on `pc57`, 9b; data loaded once).

1. **Control** — the default *L*: an idle histogram; the ANN-only query (no `mat` line); one traced hybrid query at *M* = 16,001 (the trace event present).
2. **Scenario A** — for each *L*: *M* = *L*, one query (record `mat`, `hybrid`, `pairs`), then *Q* = 8 held at the method's exit (hold point b): histogram.
3. **Scenario B** — for each *L*: *M* = *L* + 1 (one traced query: `mat refuse`, `ann`, the trace event), then *M* = 4*L* (200,000 at *L* = 64,000), *Q* = 8 held at the refusal (hold point a): histogram.
4. **Scenario C1** — restart at *L* = 0, then at 2,147,483,647: *M* = 5 and *M* = 200,000 respectively; for the latter, *Q* = 8 held at the exit: histogram.
5. **Scenario C2** — on `ks.far`, at *L* = 1,000, 16,000 and 64,000 (in the same restarts as B): one query (record `reads=`, `processed=`; `TotalPartitionReads` before and after as a side reading), then *Q* = 8 held at hold point c: histogram.

**Record for stage 4:** the configuration in force, the exact commands, and the raw readings from 9d for every run.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — found 2026-09-22 by the capacity-word pass reading the source directly, and recorded in `pending.md` under the operand's name `MAX_MATERIALIZED_KEYS` (write-up queue item 8, "read it again (a or b); trace its constant"). Also surfaced by stage 1/2 as band-A row `QueryController.java:449#1` (`bands.md`, anchors). Written up 2026-10-14. |
| **Filed by / Date** | Claude (AI long path), 2026-10-14. |
| **Line numbers checked** | 2026-10-14, every cited line against the local clone at `cassandra-5.0.9` (`git describe --tags`). |
| **Escape hatch / Target-3 note** | *Stage 4 (2026-10-15) observed (1) and (2): C2 held 245,256 keys at *L* < *M*; *L* = 0 made a 5-match query scan 115,401 rows and time out.* Three notes. (1) **The disallow branch is not bounded by the knob**: the ANN plan keeps every rejected key in `processedKeys`, up to *N* − *M* on data whose matches are far from the query vector, so lowering the limit can raise a query's heap (§6b, §8). (2) **Escape values**: *L* ≤ 0 always switches, `Integer.MAX_VALUE` never does; neither is rejected (§8). (3) **Memtable matches are collected before the check** (references only, §6b). |
| **Stage-4 feedback** | **2026-10-15, long path run 1 on `pc57` — unit Confirmed; cluster Confirmed (§9a row 1), escape values and disallow retention as recorded; no run 2** ([results](../../stage4-runtime-verification/results/SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS--guided.md)). Audit amendments before run 1 (§9 note, dated): C2 reads from `queryContext.partitionsRead` because `TotalPartitionReads` is never recorded for top-k queries; `ks.far` built by rank. Readings: every refusal at exactly *L* + 1 (unit *L* = 0 … 4,000; cluster 1,000 · 4,000 · 16,000 · 64,000), lists of *M* below it, plan switch and trace event only at refusals; 8 held queries hold 8*L* (allowed) and 8(*L* + 1) + 32 (refused) live `SkinnyPrimaryKey`, ≈ 152 B each (U2 *b* = 156 B); *L* = 2^31 − 1 holds 1,600,000; C2 at *L* = 1,000 and 16,000: 30,656 rows read and 245,256 keys held for 10 rows, against 10 reads at 64,000. **Beyond §9a (no row): at *L* = 0 a hybrid query matching 5 rows read 115,401 partitions and failed with `ReadTimeout` at the 120 s quota** — the escape value turns every selective hybrid query into a whole-replica scan (§8 "Escape values" understates it; Target-3 material). Missed sub-prediction: five-class bytes for B held at *L* = 1,000 / 4,000 (trace rows of the preceding traced query in the idle-to-held difference). Not predicted, recorded: the allow plan does **not** keep the list for the whole command — at the end of the top-k loop only 88 keys were live (§7 "Lifetime" and §6a's last paragraph overstate it). |
| **Notes** | Renamed from the queue's `MAX_MATERIALIZED_KEYS` to the `CassandraRelevantProperties` constant it is read from (§4, "Name"). The queue's "(a) or (b)" question is settled as (a) with the caller's `null` test recorded as the plan switch (§5). The queue's phrase "forces a different query path" holds; the case adds that the path is not a refusal and that its own retention is unbounded by the limit. |

---

## 11. Notes

- **Not a clean byte bound.** The limit counts keys, and a key's cost depends on the partition and clustering key lengths; §8's bytes are for `int` partition keys. The cluster tier fixes the key type so *b* is a constant.
- **`SAI_INTERSECTION_CLAUSE_LIMIT`** (mentioned in the constant's Javadoc) limits how many clauses an intersection uses, before the key stream reaches this check; with one non-ANN clause (9b) it does not act.
- **The trace line is the only built-in disallow signal.** No metric counts plan switches; `TableQueryMetrics` records partition reads and rows filtered per query, which differ between the plans but are not specific to the switch.
- **Allowed lists from a memtable** add no key objects (the keys are the memtable's), so on unflushed data the knob moves only list slots and the per-index arrays; the cluster tier flushes for that reason.
