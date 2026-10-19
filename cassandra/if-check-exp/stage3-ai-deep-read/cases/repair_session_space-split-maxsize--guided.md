# repair_session_space — Merkle tree nodes built for repair validation

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | REPAIR_SESSION_SPACE-SPLIT-MAXSIZE |
| **Constraint** | `repair_session_space` — a **configuration entry** ([`Config.java:208`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L208), default **heap / 16**, set at startup, [`DatabaseDescriptor.java:609-610`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L609-L610)), **live-settable over JMX**. The limit at the check is **derived** from it and two other terms: the deprecated `repair_session_max_tree_depth` (default 20, [`:596-607`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L596-L607)) and the range's partition count. README §6.1 names a derived limit after the source a user would tune; in 5.0 that is `repair_session_space` (§4 shows which term binds when). |
| **Enforcement pattern** | **(a)** — the comparison is the decision: on disallow `split()` returns before any node is created. **Reached only on the order-preserving partitioners** (§5, §6b); on the default partitioner the same `maxsize` bounds the tree by sizing it in `init()`, with no comparison. |
| **Capacity check** | [`MerkleTree.split():409`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L409) — `size >= maxsize`. |
| **Decision point** | The same line ([`:409-410`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L409-L410)); its `false` is read by the sampling loop in [`Validator.prepare():146-152`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/Validator.java#L146-L152), which stops splitting that range. |
| **Allocation site** | [`MerkleTree.splitHelper():438-439`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L438-L439) — `size++; return new OnHeapInner(midpoint, new OnHeapLeaf(), new OnHeapLeaf());`. The default path's equivalent, outside any comparison: [`MerkleTree.init():139-146`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L139-L146) → [`initHelper():149-162`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L149-L162). |
| **Related cases** | None filed in `repair`. Same subsystem: the pending `repair_disk_headroom_reject_ratio` (`pending.md` item 12), which admits or refuses a repair on disk usage. |

```java
// MerkleTree.split():407-419 — the capacity check and decision point.
public boolean split(Token t)
{
    if (size >= maxsize)                    // <-- capacity check, :409
        return false;                       // DISALLOW: no node created

    try
    {
        root = splitHelper(root, fullRange.left, fullRange.right, 0, t);   // ALLOW
    }
    catch (StopRecursion.TooDeep e)
    {
        return false;                       // a second, non-capacity refusal (§5)
    }
    return true;
}
```

```java
// Validator.prepare():121-152 — which path builds the tree.
if (!trees.partitioner().preservesOrder() || evenTreeDistribution)
{
    // You can't beat even trees distribution for md5
    trees.init();                           // DEFAULT PATH: Murmur3/Random — :409 never runs
}
else
{
    ...
    if (keys.isEmpty())
        trees.init(range);                  // no key samples (BTI SSTables, empty table)
    else
        while (true)
        {
            DecoratedKey dk = keys.get(random.nextInt(numKeys));
            if (!trees.split(dk.getToken()))   // reads the verdict
                break;
        }
}
```

## 2. Context

Repair keeps replicas consistent by comparing their data without shipping it.
Each replica reads a token range and folds the hash of every partition into a
**Merkle tree**: a binary tree whose leaves each cover a slice of the range.
The coordinator compares the replicas' trees and streams only the slices whose
leaf hashes differ. The number of leaves sets the trade-off: more leaves mean
smaller slices and less data streamed for a small inconsistency, but more
memory, because each replica builds its tree on the heap and the coordinator
holds one tree per replica at once.

`repair_session_space` is the memory budget for that trade-off. Before a
validation starts, Cassandra turns the budget into a maximum number of leaves
(`maxsize`) for each range's tree: the budget divided by the replication factor
(since the coordinator holds that many trees), then by each range's share of
the partitions, converted to a tree depth and capped. The check in this case
stops a tree from being split once it has that many leaves. Without the
budget, a repair of a large table would build trees as deep as its partition
count allows, and a coordinator repairing many ranges or tables at once could
exhaust its heap.

Two things qualify that picture (§6b, §8). On the default partitioner the
check is never reached: the tree is built to exactly `maxsize` leaves in one
step instead. And the conversion from MiB to bytes is done in 32-bit
arithmetic, so a budget of 2 GiB or more wraps round; from 2048 to 4096 MiB
every tree is cut to two leaves.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | `repair` — anti-entropy repair: validation (Merkle tree build) and differencing (`repair/`, with the tree in `utils/MerkleTree`) |
| **One-line role** | Repair compares replicas' Merkle trees and streams the token ranges whose hashes differ; `ValidationManager` sizes each tree, `Validator` builds and hashes it, `MerkleTree` holds it. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | **Yes** — the tree's current number of leaves against a ceiling on leaves, gating the creation of more nodes. Each leaf and inner node has a fixed footprint (§7), so leaves × size is the tree's memory. |
| **Usage-side operand** | `size` — the leaf count, [`MerkleTree.java:98`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L98), incremented once per split at [`:438`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L438). |
| **Limit-side operand** | `maxsize` — [`MerkleTree.java:97`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L97), a constructor argument stored at [`:129`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L129). |
| **Limit type** | **Derived** — from `repair_session_space` (primary), the replication factor, the range's share of partitions, `repair_session_max_tree_depth` and the range's partition count. |

**Limit initialization path.**

1. [`Config.repair_session_space:208`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L208) — declared, `volatile DataStorageSpec.IntMebibytesBound`, `null`. [`Config.repair_session_max_tree_depth:206`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L206) — declared, `Integer`, `null`.
2. [`DatabaseDescriptor.java:596-615`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L596-L615) — at startup: `repair_session_max_tree_depth` set explicitly logs a deprecation warning, must be at least 10, warns above 20, and **defaults to 20**; `repair_session_space` defaults to `max(1, maxMemory / 16 MiB)`, must be at least 1 MiB and warns above a quarter of the heap. The shipped `cassandra.yaml` leaves it commented out ([`conf/cassandra.yaml:827-840`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L827-L840)).
3. Live setter: [`DatabaseDescriptor.setRepairSessionSpaceInMiB():4091-4099`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4091-L4099), exposed as the `RepairSessionSpaceInMiB` attribute of `org.apache.cassandra.db:type=RepairService` ([`ActiveRepairServiceMBean.java:50-51`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairServiceMBean.java#L50-L51)). `setRepairSessionMaxTreeDepth()` ([`:4075-4084`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4075-L4084)) has no MBean: the depth is `cassandra.yaml` only.
4. **Derived per validation**, in [`ValidationManager.createMerkleTrees():54-89`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/ValidationManager.java#L54-L89), re-read at every validation (so a JMX change applies to the next one):
   - [`:62-63`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/ValidationManager.java#L62-L63) `availableBytes = (getRepairSessionSpaceInMiB() * 1048576) / RF` — **both factors are `int`, so the product is computed in 32 bits** (see "The overflow" below);
   - [`:71`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/ValidationManager.java#L71) `rangeAvailableBytes = max(1, (int) (rangeOwningRatio * availableBytes))`, the range's share by partition count;
   - [`:74`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/ValidationManager.java#L74) `estimatedMaxDepth = MerkleTree.estimatedMaxDepthForBytes(partitioner, rangeAvailableBytes, 32)` ([`MerkleTree.java:1520-1541`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L1520-L1541): `floor(log2((bytes + inner) / (leaf + inner)))`, at least 1, with `leaf` and `inner` measured at run time by `ObjectSizes.measureDeep`);
   - [`:75-77`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/ValidationManager.java#L75-L77) `maxDepth = min(estimatedMaxDepth, getRepairSessionMaxTreeDepth())`;
   - [`:79`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/ValidationManager.java#L79) `depth = min(ceil(log2(numPartitions)), maxDepth)`;
   - [`:80`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/ValidationManager.java#L80) `trees.addMerkleTree((int) Math.pow(2, depth), range)`.
5. [`MerkleTrees.addMerkleTree():108-119`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTrees.java#L108-L119) → `new MerkleTree(partitioner, range, RECOMMENDED_DEPTH, maxsize)` — stored at [`MerkleTree.java:129`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L129).
6. Read at [`:409`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L409) (split path) or at [`init():142`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L142) (default path).

**Which term binds** (the question `pending.md` left open). Three terms meet in
`min`, and each binds in a different regime:

- **Partition count** — a range with fewer than 2^`maxDepth` partitions gets
  2^`ceil(log2 n)` leaves, about one partition per leaf. Small tables and test
  data are here, and then neither knob matters.
- **`repair_session_space`** — binds when the budget per tree, `space / RF ×
  share`, is below 2^`depth` × (leaf + inner). The upstream
  `ValidatorTest.testSizeLimiting` gets 2^12 leaves from 1 MiB at RF 1
  ([`ValidatorTest.java:234-284`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/repair/ValidatorTest.java#L234-L284)),
  so leaf + inner is between 128 and 256 bytes on that JVM (inferred from the
  test; §9's unit tier measures it). Depth 20 then needs 128 to 256 MiB per
  tree: at RF 3 a `repair_session_space` of about 384 to 768 MiB, i.e. a heap
  of about 6 to 12 GiB at the default. **Below that the budget binds.**
- **`repair_session_max_tree_depth`** (20) — binds above that, on large heaps,
  as a cap. It is deprecated; set below the budget's depth it overrides it.

**The overflow.** `getRepairSessionSpaceInMiB()` returns `int` and `1048576` is
an `int` literal, so `:62` multiplies in 32 bits before widening to `long`.
From 2048 MiB the product wraps (computed with Java's `int` rules; not run):

| `repair_session_space` | `availableBytes` at RF 1 | Effect |
|---|---|---|
| up to 2047 MiB | as intended | — |
| 2048 to 4095 MiB | negative | `rangeAvailableBytes` = 1 (`:71`), `estimatedMaxDepth` = 1: **every tree has 2 leaves** |
| 4096 MiB | 0 | the same: 2 leaves |
| 4097 MiB | 1 MiB | behaves as 1 MiB |
| 5120 MiB | 1024 MiB | behaves as 1024 MiB |

The default reaches 2048 MiB at a 32 GiB heap. No startup check caps the
value; `:614` only warns above a quarter of the heap.

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`MerkleTree.split():409-410`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L409-L410) — the capacity check is the decision; its `false` is consumed by [`Validator.prepare():151-152`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/Validator.java#L151-L152). |
| **Verdict** | n/a — the check is the decision. |

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow** | `size < maxsize` | `splitHelper` descends to the leaf holding the sampled token and replaces it with an inner node and two new leaves; `size` grows by one. |
| **Disallow** | `size >= maxsize` | `split()` returns `false` with no node created; the caller stops sampling that range, and the tree keeps exactly `maxsize` leaves. |

```java
// allow: MerkleTree.splitHelper():437-439, at the leaf that holds the token
// split
size++;
return new OnHeapInner(midpoint, new OnHeapLeaf(), new OnHeapLeaf());
```

```java
// disallow: MerkleTree.split():409-410
if (size >= maxsize)
    return false;
```

**A second refusal shares the return value.** `splitHelper` throws `TooDeep`
when the leaf is already at `hashdepth` (126, `RECOMMENDED_DEPTH`,
[`:89`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L89);
[`:425-426`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L425-L426))
or when the midpoint equals an end of the leaf's range
([`:434-435`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L434-L435)),
and `split()` turns it into the same `false`
([`:416-418`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L416-L418)).
The caller cannot tell them apart, and it stops at the **first** `false` of
either kind: one sampled key whose leaf is already 126 levels deep ends
splitting for the whole range. The tree's `size` tells them apart
(`size == maxsize` only for the capacity refusal); §9 relies on that. Splits
concentrate on the sampled keys (about one per 128 partitions, the index
summary's interval), so with few samples per leaf wanted the depth limit can
bind first.

**Where the check is reached.** `Validator.prepare()` takes the split path
only when the partitioner preserves order **and** `evenTreeDistribution` is
false ([`:121`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/Validator.java#L121)),
and only for a range with key samples:

| Condition | Path | `:409` reached? |
|---|---|---|
| `Murmur3Partitioner` (the default) or `RandomPartitioner` — `preservesOrder()` is `false` ([`Murmur3Partitioner.java:299`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/dht/Murmur3Partitioner.java#L299)) | `trees.init()` ([`:124`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/Validator.java#L124)) | **No** |
| `ByteOrderedPartitioner` or `OrderPreservingPartitioner` ([`ByteOrderedPartitioner.java:291`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/dht/ByteOrderedPartitioner.java#L291)), BIG SSTables with samples | the split loop ([`:146-152`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/Validator.java#L146-L152)) | **Yes** |
| Order-preserving, but no key samples: BTI SSTables (`getKeySamples` returns an empty list, [`BtiTableReader.java:314-319`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/bti/BtiTableReader.java#L314-L319)) or no SSTables | `trees.init(range)` ([`:139-144`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/Validator.java#L139-L144)) | **No** |

The production `Validator` always passes `evenTreeDistribution = false`
([`Validator.java:91-94`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/Validator.java#L91-L94),
called from [`RepairMessageVerbHandler.java:253-254`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairMessageVerbHandler.java#L253-L254)),
so the partitioner and the SSTable format decide. The shipped `cassandra.yaml`
says the order-preserving partitioners are kept "for backward compatibility
only" ([`conf/cassandra.yaml:385-386`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L385-L386)).

## 6. Code path

### 6a. Allow path → object creation

1. [`ValidationManager.doValidation():127-129`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/ValidationManager.java#L127-L129) — opens the validation iterator, calls `createMerkleTrees()` (§4 step 4) and `validator.prepare(cfs, trees, ...)`.
2. [`Validator.prepare():127-152`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/Validator.java#L127-L152) — order-preserving partitioner: collects the range's key samples (`cfs.keySamples(range)`, the BIG index summary), then picks a random sample in a loop.
3. [`MerkleTrees.split():172`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTrees.java#L172) → [`MerkleTree.split():407-413`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L407-L413) — `size < maxsize`, so it recurses.
4. [`splitHelper():423-453`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L423-L453) — walks down to the leaf whose range holds the token.
5. [`:438-439`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L438-L439) — **object creation**: `size++`, `new OnHeapInner(midpoint, new OnHeapLeaf(), new OnHeapLeaf())`.
6. Later, as validation reads partitions, [`OnHeapLeaf.addHash():1074-1083`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L1074-L1083) keeps the first partition's 32-byte hash array in each leaf and XORs the rest onto it; inner hashes are filled before the tree is sent. The tree reaches its full size at [`Validator.complete():222`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/Validator.java#L222-L237).

**Default path (no comparison).** [`init():139-146`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L139-L146)
computes `depth = min((int) log2(maxsize), hashdepth)` and
[`initHelper()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L149-L162)
builds the complete tree of 2^`depth` leaves at once. Since `maxsize` is a power
of two, that is exactly `maxsize` leaves (the `log10` quotient at `:142` is exact
for 2^0 to 2^30; checked with IEEE doubles).

### 6b. Disallow path effect

**A clean stop, with no error and no log, and the cost moves to streaming.**

1. [`split():409-410`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L409-L410) — returns `false`; nothing is allocated and `size` stays at `maxsize`.
2. [`Validator.prepare():151-152`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/Validator.java#L151-L152) — `break`: no more splitting for this range. The only trace is the debug line at [`:158`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/Validator.java#L158), `Prepared AEService trees of size <leaves> for <desc>`.
3. Validation proceeds with the coarser tree. Each leaf covers more partitions, so a single differing partition makes the coordinator stream its whole leaf range: **memory is traded for over-streaming** (network and disk on the receiving replica).

**On the default partitioner there is no disallow branch at all.** The tree is
built at `maxsize` leaves by `init()`; nothing is refused because nothing asks
for more. The constraint still bounds the tree, through sizing. That is the
case's non-domination finding: the comparison exists, but the deployment
default never executes it.

**Bypasses.** None lets a tree exceed `maxsize`. Two things make the knob
behave unlike its value: the overflow (§4), which **shrinks** trees to two
leaves above 2047 MiB, and the multipliers in §8, which let total memory
exceed the budget legitimately.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | `MerkleTree.OnHeapInner` plus two `OnHeapLeaf` per split (net: one inner node and one leaf); later one 32-byte hash array per non-empty leaf and per inner node. |
| **Resource consumed** | **Heap** on the replica that builds the tree. On the coordinator, received trees are rebuilt **off-heap** (`ByteBuffer.allocateDirect`, [`MerkleTree.java:747-751`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L747-L751)) when the partitioner is Murmur3 or Random and `use_offheap_merkle_trees` is `true` (the default, [`Config.java:212`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L212); [`shouldUseOffHeapTrees():733-743`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L733-L743)); with an order-preserving partitioner they stay on heap there too. The coordinator's own tree is moved off-heap before it is handed over ([`Validator.respond():281-306`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/Validator.java#L281-L306)). |
| **Rough sizing** | On heap, about 128 to 256 bytes per leaf with its share of inner nodes (§4, from the upstream test; `estimatedMaxDepthForBytes` measures it). Off heap, per tree of *L* leaves: `(L − 1) × 50 + L × 32` bytes with Murmur3 ([`offHeapBufferSize():799-802`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L799-L802); inner node 4 + 4 + 32 + 2 + 8, [`:1451-1457`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L1451-L1457); leaf 32, [`:1160-1163`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L1160-L1163)), about 82 bytes per leaf. |
| **Lifetime / release** | The replica's tree lives from `prepare()` until its response is sent. The coordinator holds the replicas' trees for a range until it has compared them. Off-heap buffers are freed by the GC cleaner of their `ByteBuffer`. |

## 8. Maximum memory bound

`repair_session_space` bounds the Merkle-tree memory of **one validation**
(one table, one repair session's ranges), and the mechanism is a ceiling on
leaves per tree:

- **Per validation, on each replica.** The trees of a validation share
  `space / RF`, split by each range's share of partitions. Each tree gets
  2^`depth` leaves with `depth` rounded **down**, so when the budget binds a
  tree uses between half of its share and all of it. Raising the budget
  doubles the leaves per doubling of the value, until the partition count or
  the depth cap (20) binds; lowering it halves them.
- **Per (table, range), on the coordinator.** It receives one tree per replica,
  so it holds about `space` for that range; that is the reason for the division
  by RF (comment at [`ValidationManager.java:60-61`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/ValidationManager.java#L60-L61)).
  Off-heap trees take less than the budget assumes (about 82 bytes per leaf
  against the 128 to 256 the budget uses).
- **Not node-wide.** Concurrent sessions, several tables and vnode ranges each
  get their own budget. `concurrent_merkle_tree_requests` would cap the
  validations in flight, but its default `0` means unlimited
  ([`Config.java:210`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L210);
  the yaml warns of OOM, [`conf/cassandra.yaml:842-858`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L842-L858)).
- **The coordinator does not apply its own setting** (derived from reading): a
  received tree carries its `maxsize` in its serialized form
  ([`MerkleTree.java:685`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L685),
  read back at [`:710-729`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L710-L729)),
  and the off-heap buffer is sized from the tree as sent. With different
  settings on different nodes, the coordinator's memory follows the replicas'.
- **Not monotonic above 2047 MiB.** The overflow (§4) gives two-leaf trees from
  2048 to 4096 MiB, so an operator raising the budget for precision gets the
  coarsest trees possible. Memory is then negligible and the cost is all in
  over-streaming.

## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers
and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../stage4-runtime-verification/README.md).
The test sweeps `repair_session_space` over JMX, runs a full repair of one
table, and reads each validation's leaf count against the predicted
`maxsize`, on both partitioners and through the overflow. **Run so far:** none.

### 9a. Procedure and conclusions

**Testability:** config, **live-settable** over JMX (`RepairSessionSpaceInMiB`,
read at every validation); `repair_session_max_tree_depth` is `cassandra.yaml`
only (restart); the partitioner is fixed when a node first starts (a separate,
fresh cluster per partitioner).

**Claim under test:** each validation's Merkle tree has at most `maxsize` =
2^`min(ceil(log2 n), estimatedMaxDepth(space / RF × share), 20)` leaves; on an
order-preserving partitioner `split()` refuses at `size == maxsize` and creates
no node (§5, §6b); on the default partitioner the same count is built by
`init()` without the comparison; and from 2048 MiB the 32-bit conversion cuts
every tree to two leaves (§4).

**How this verifies the hypothesis** (a restatement of the claim, procedure,
prediction and conclusions in this section; it adds none):

- **Hypothesis:** the leaves per tree, and so the tree's heap, follow
  `repair_session_space` until the partition count or the depth cap binds; the
  refusal at `:409` stops growth on the split path; the overflow makes the knob
  non-monotonic.
- **Test:** unit tier: the check alone, both build paths, and the derivation at
  budgets from 1 MiB through the overflow. Cluster tier: two nodes, RF 2, one
  table with about 2^20 partitions; `repair_session_space` at 1, 4, 16, 64 MiB,
  the default, and 2048 and 4097 MiB; one `nodetool repair -full -pr` per value;
  Murmur3 first, then a fresh `ByteOrderedPartitioner` cluster at two values.
- **Logic:** (1) the partition term must not bind (else the run says nothing
  about the knob). (2) Leaves per tree equal the predicted `maxsize` at every
  value: usage **stops at the limit**. (3) They double per doubling of the
  budget: usage **follows the constraint**. (4) On the ordered cluster the
  refusal trace shows `split()` returning `false` with `size == maxsize`: the
  **disallow branch** stops it; on Murmur3 `split()` is never called and the
  count is still `maxsize`: the bound comes from `init()`. (5) The replica's
  tree heap and the coordinator's off-heap buffers scale with the leaves.
  (6) 2048 MiB gives two leaves; 4097 MiB gives the 1 MiB count.
- **Refuted if:** a tree has more leaves than `maxsize`; the leaf count does not
  move with the budget while the partition term is not binding; the split path
  stops below `maxsize` at every value (another refusal binds); or the overflow
  arms give large trees (rows of the Conclusions table).

**Procedure:**

1. **Unit tier** — harness test `RepairSessionSpaceTreeTest` (9c): U1 the check
   alone, U2 `init()`, U3 the derivation and which term binds, U4 the overflow.
   Also run upstream `MerkleTreeTest` and `ValidatorTest`.
2. **Cluster tier** — two nodes, RF 2 (9b); arm M on Murmur3, then arm O on a
   fresh `ByteOrderedPartitioner` cluster.
3. **At each value:** control (idle, then a repair at the default) →
   **scenario A**, repair with the partition term not binding: the tree reaches
   `maxsize` → **scenario B**, double the partitions and repair again: the tree
   does not grow → **scenario C**, the arms in which the check does not act as
   its value says: arm M (the comparison is never reached) and the overflow
   values.
4. **Compare** with the prediction and read the result below.

**Prediction.** Notation: *s* = `repair_session_space` in MiB; *RF* = 2;
*b* = the per-tree budget in bytes, `s × 2^20 / RF × share` (share = 1 with
`-pr` and one token per node); *d*(*b*) = `estimatedMaxDepthForBytes(b)`, which
U3 prints for every *b* used here on the same JDK; *n* = the range's estimated
partitions (the `Created ... merkle trees` debug line); *L* = leaves per tree.

- `L = 2^min(ceil(log2 n), d(b), D)` with *D* = `repair_session_max_tree_depth`
  (20 unless set). With leaf + inner in (128, 256] bytes (§4), *d* rises by one
  per doubling of *b*: about 11, 13, 15, 17 for *s* = 1, 4, 16, 64 MiB at RF 2.
  *n* ≈ 2^19 for node 1's primary range of 2^20 partitions, so the partition
  term (19) does not bind. **(Amended 2026-10-14, step-0 audit, before any
  reading:** `estimatedMaxDepthForBytes` takes the partitioner, and leaf and
  inner sizes depend on its token, so U3 prints *d*(*b*) for **both**
  `Murmur3Partitioner` (arm M) and `ByteOrderedPartitioner` (unit tier, arm O),
  for *b* = 0.5, 1, 2, 4, 8, 32 and 64 MiB; the cluster prediction for each
  value is the exact *d* from that table, and "about" above is only the
  expectation. The default *s* is read back over JMX before the sweep: 128 MiB
  at `-Xmx2G` with G1, the shipped collector, where `maxMemory()` is the full
  heap; *b* = 64 MiB at RF 2.)**
- **Scenario B:** doubling the data leaves *L* unchanged while *d*(*b*) < log2 *n*.
- **Depth cap:** with `repair_session_max_tree_depth: 15` and *s* = 64 MiB,
  `L = 2^15`.
- **Heap:** the replica's `OnHeapLeaf` count equals *L* and `OnHeapInner` is
  *L* − 1; their bytes scale with *L*. **Off heap, coordinator (arm M):** two
  buffers per range (its own tree and the peer's), each `L × 50 + (L + 1) × 32`
  = `82 L + 32` bytes, logged exactly (9d). **(Amended 2026-10-14, step-0
  audit, before any reading:** the formula read `(L − 1) × 50 + L × 32`, but
  `allocate()` is passed the **leaf** count: `moveOffHeap()` passes `size`
  ([`MerkleTree.java:781`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L781)),
  and the deserializer passes the serialized `size` field
  ([`:714`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L714),
  [`:789`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L789)),
  into a parameter named `innerNodeCount`
  ([`:799-802`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L799-L802)),
  so each buffer has room for one inner node and one leaf more than the tree
  uses. The histogram counts are the change from an idle `-histo:live`
  taken on node 2 just before each held repair, so a tree an earlier
  repair left reachable is not counted against *L*.)**
- **Arm O:** the same *L*, and the refusal trace shows `size == maxsize` once
  per range per validation. With about 2^19 partitions in node 1's range there
  are about 2^19 / 128 = 4,096 key samples, so 2^13 and 2^15 leaves need about 2 and 8 splits per sample, far
  from the depth limit. If `split()` returns `false` with `size < maxsize`,
  `TooDeep` bound instead (§5). (Amended 2026-10-14, step-0 audit: the sample
  count is read from `split-trace.btm`'s `samples=` line, one per range, since
  `nodetool tablestats` does not print index-summary entries; expected about
  *n* / 128.)
- **Arm M:** zero calls to `split()`; *L* as predicted.
- **Overflow:** *s* = 2048 → *L* = 2 for every range; *s* = 4097 → the *L* of
  *s* = 1.

**Conclusions:**

| Result | Conclusion |
|---|---|
| *L* equals the prediction at every value on both arms; it doubles per doubling of *s*; scenario B leaves it unchanged; arm O shows refusals at `size == maxsize`; heap and off-heap bytes scale with *L* | **Confirmed** — the budget caps the trees as traced. |
| Arm M: `split()` never called and *L* as predicted | **Non-domination as recorded** — expected; the bound comes from `init()` sizing (§6b). |
| *s* = 2048 gives *L* = 2 and *s* = 4097 gives the 1 MiB count | **Overflow as recorded** — Target-3 material; record the over-streaming if the optional step runs. |
| *L* > the predicted `maxsize` on any validation | **Refuted** — the check or the sizing does not cap the tree. |
| *L* does not move with *s* while the partition term is not binding | **Refuted** — not the binding limit; re-read the derivation (§4), do not re-run. |
| Arm O: every refusal has `size < maxsize` | **Not confirmed** — `TooDeep`, not the capacity check, stops the split loop; record *L* and the sample count. |
| The overflow arms give large trees | **Refuted** for the overflow claim — §4's arithmetic is wrong; read the bytecode before concluding. |
| *L* = 2^`ceil(log2 n)` at every value | **Invalid run** — the partition term binds; load more data (9c) and re-run. |
| The read-back of `RepairSessionSpaceInMiB` differs from the value set | **Invalid run** — the knob did not take; fix 9b. |
| An instrument is silent: a validation with no `Prepared AEService` line or no `split calls` line, arm O with no `samples` line, or a held repair whose hold line never appears (added 2026-10-14, step-0 audit) | **Invalid run** for that reading — fix the harness and repeat the value; the leaf count is not read from anything else. |

**Why the leaf count and not only heap:** a validation's trees are short-lived
and the heap holds other repair state; the leaf count from the debug line is
exact, and the heap and off-heap readings confirm it costs what §7 says.

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | `RepairSessionSpaceInMiB` on `org.apache.cassandra.db:type=RepairService`, live: `bin/nodetool sjk mx -ms -b 'org.apache.cassandra.db:type=RepairService' -f RepairSessionSpaceInMiB -v <MiB>` on **both** nodes (each replica sizes its own tree, §8). `repair_session_max_tree_depth` in `cassandra.yaml` for the depth-cap step only (restart; it logs a deprecation warning). |
| **Confirm it took effect** | `bin/nodetool sjk mx -mg -b 'org.apache.cassandra.db:type=RepairService' -f RepairSessionSpaceInMiB` on both nodes after each change. |
| **Capacity values** | *s* = 1, 4, 16, 64 MiB; the default (`maxMemory / 16`: 128 MiB at `-Xmx2G`); overflow values 2048 and 4097 MiB (2048 also logs the "heap pressure" warning; that is all it does). Depth cap: *s* = 64 with `repair_session_max_tree_depth: 15`. |
| **Scope** | Per validation (one table, one range with `-pr`). Hold fixed: one table, one repair at a time, `-pr`, one token per node. |
| **Level** | Both. Unit: harness `RepairSessionSpaceTreeTest`; upstream [`MerkleTreeTest.testSplitLimitSize():161-174`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/utils/MerkleTreeTest.java#L161-L174) and `ValidatorTest.testSizeLimiting()` reach the check and the derivation. The unit configuration uses `ByteOrderedPartitioner` ([`test/conf/cassandra.yaml:18`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/conf/cassandra.yaml#L18)), so a `Validator` built with `evenTreeDistribution = false` takes the split path. |

**Cluster layout.** Two nodes, `pc57` and `pc50` as a ring
([`environment-notes.md`](../../stage4-runtime-verification/environment-notes.md) §1),
`num_tokens: 1` with explicit `initial_token`s: `-9223372036854775808` and `0` for Murmur3 (arm O chooses its own, 9e).
**(Amended 2026-10-14, step-0 audit:** both nodes run on `pc57`, on loopback
addresses `127.0.0.2` (node 1) and `127.0.0.3` (node 2), each with its own
`conf/`, data and log directories and JMX port (7102, 7103), as the
`internode_application_send_queue_capacity` harness ran its four-node ring.
Nothing this case measures depends on the network, and one host gives one
clock and one file system for the logs; `pc50` is not needed. `nodetool` takes
`-p <port>`; the knob is set and read with the harness's `Jmx.java`
instead of `nodetool sjk`.)**
Keyspace `SimpleStrategy`, `replication_factor` 2, one table. Node 1 runs every
repair (`-pr`: its own primary range only).

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| `num_tokens` | `1` | One primary range per node, so `-pr` gives one tree per validation with share 1. |
| `MAX_HEAP_SIZE` | `2G` on both | Fixes the default *s* (128 MiB) and keeps the histogram fast. |
| `concurrent_merkle_tree_requests` | `1` | One validation at a time per repair. |
| `use_offheap_merkle_trees` | `true` (default) | Arm M's coordinator off-heap reading depends on it. |
| `sstable.selected_format` | `big` (default) | BTI gives no key samples, so arm O would fall back to `init(range)` (§5). |
| `auto_snapshot`, compaction | defaults; the table is created before loading with `compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'}` (amended 2026-10-14: `disableautocompaction` cannot run before stress has created the table) | The partition estimate (*n*) comes from SSTable key estimates; keep the SSTable set fixed across the sweep. |
| Partitioner | `Murmur3Partitioner` (arm M), `ByteOrderedPartitioner` (arm O, fresh data directories) | Decides the path (§5). |
| Logging | `debug.log` at `DEBUG` for `org.apache.cassandra` (the shipped default) | The leaf count and off-heap lines are `DEBUG`. |

**Controls:** an idle node (no repair) for the histogram baseline; a repair at
the default *s* before the sweep.

**Reset between runs:** none for a JMX change; trees are rebuilt at every
validation. Between arms, stop both nodes and wipe data, commit log and saved
caches (a partitioner cannot change on existing data).

### 9c. Workload

**Harness.** `<harness>` stands for
`<misconfiguration-repo>/cassandra/if-check-exp/stage4-runtime-verification/long-path/harness/repair_session_space-split-maxsize`.
Work for step 1, before run 1:

| File | What it is |
|---|---|
| `RepairSessionSpaceTreeTest.java` | Unit tier, package `org.apache.cassandra.repair`, modelled on `ValidatorTest` (same schema set-up, `KeyspaceParams.simple(1)`, `CompactionsTest.populate`, `registerOutgoingMessageSink()`). Steps U1–U4 in 9e. |
| `split-trace.btm` | Byteman, observation only: (1) `AT LINE 410` of `MerkleTree.split`: `split refused size=<size> maxsize=<maxsize>`; (2) at the `return false` of the `TooDeep` catch: `split toodeep size=<size> maxsize=<maxsize>`; (3) a counter of `split()` entries, printed with the session id at `Validator.complete()` entry: `split calls=<n> trees=<trees.size()>`. |
| `hold-trees.btm` | Byteman: at `Validator.complete()` entry, `Thread.sleep(20000)`, so the built tree is still referenced while the histogram is taken. Loaded for the histogram runs only. **(Amended 2026-10-14, step-0 audit:** loaded at node 2's start and gated by a flag file, so it sleeps only while the file exists, and it writes `hold start` before the sleep and `hold end` after it. The rules then never need loading at run time, and the harness takes the histogram after `hold start`.) |
| Added 2026-10-14 (step-0 audit): `split-trace.btm` rule (4) | At `keys.clear()` in `Validator.prepare()` (the end of one range's split loop), `samples=<numKeys>`: the arm-O sample count. |
| Added 2026-10-14: `Jmx.java`, `make-node-yaml.sh`, `cluster-run.py`, `unit-run.sh` | The JMX get/set client (ports 7102, 7103), the per-node `conf/` builder, the scripted cluster tier (labels per arm and scenario, `EXPECTED:` lines in `summary.txt`), the unit-tier runner. |

```bash
# unit tier
ant testsome -Dtest.name=org.apache.cassandra.utils.MerkleTreeTest
ant testsome -Dtest.name=org.apache.cassandra.repair.ValidatorTest
cp <harness>/RepairSessionSpaceTreeTest.java test/unit/org/apache/cassandra/repair/
ant testsome -Dtest.name=org.apache.cassandra.repair.RepairSessionSpaceTreeTest

# cluster tier: schema and load (both nodes up), then flush; 2^20 partitions of one small row
bin/cqlsh <node1> -e "CREATE KEYSPACE keyspace1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 2};"
tools/bin/cassandra-stress write n=1048576 cl=ALL no-warmup -col 'n=FIXED(1)' 'size=FIXED(16)' -rate threads=32 -node <node1>,<node2>   # amended 2026-10-14: n=FIXED(1), stress's distribution syntax
bin/nodetool -h <node1> flush keyspace1 standard1 && bin/nodetool -h <node2> flush keyspace1 standard1
# per value: set the knob on both nodes (9b), then
bin/nodetool -h <node1> repair -full -pr keyspace1 standard1
```

**Scenario B data:** a second load of 2^20 new partitions (`-pop seq=1048577..2097152`), flushed, then the same repair at *s* = 4 and 16 MiB.

**Optional, the overflow's cost:** after the sweep, write one row at `CONSISTENCY ONE` with node 2 stopped, restart node 2, and repair at *s* = 64 and then (after re-creating the same difference) at 2048 MiB; read the streamed bytes from the `Repair` lines in node 1's `system.log` and `nodetool netstats`. At 2048 MiB one differing row should stream half the range.

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — leaves per tree, *L* | `grep 'Prepared AEService trees of size' logs/debug.log` on **both** nodes (`Validator.java:158`), one line per validation; *n* from `grep 'Created .* merkle trees' logs/debug.log` (`ValidationManager.java:85`, whose "size" field counts trees before they are built, not leaves). | After each repair | `MerkleTrees.size()` sums all trees of the validation; with `-pr` and one token there is one tree. |
| **Disallow evidence** (arm O) | `split refused size=… maxsize=…` lines from `split-trace.btm` (`size == maxsize`), and no `split toodeep` line. | Each validation | The caller cannot tell the two refusals apart (§5); only the trace and `size` can. |
| **Path evidence** (arm M) | `split calls=0` from `split-trace.btm`. | Each validation | — |
| **Real resource, replica heap** | With `hold-trees.btm` loaded, during the 20 s hold: `jmap -histo:live <pid> \| grep -E 'MerkleTree\$OnHeap(Leaf\|Inner)'` (instance counts and bytes), on the replica that is not the coordinator. | Once per value, in a separate repair | `-histo:live` forces a full GC; take it once per value, not repeatedly. The coordinator's own tree is moved off heap at the end. |
| **Real resource, coordinator off heap** (arm M) | `grep 'Allocating direct buffer of size' logs/debug.log` on node 1 (`MerkleTree.java:750`): two per range. Cross-check `BufferPoolMXBean` `direct` `MemoryUsed` before and after (`nodetool sjk mx -mg -b 'java.nio:type=BufferPool,name=direct' -f MemoryUsed`). **(Amended 2026-10-14, step-0 audit:** "after" cannot show the buffers, because the session releases its trees when it ends. The cross-check reads node 1's `MemoryUsed` idle, then **during node 2's hold**, when node 1's own tree is already off heap and waiting for the peer's: the rise should be one buffer, `82 L + 32` bytes, readable only where that clears the idle noise. Support, not a deciding reading.) | Each repair | Arm O logs no such line (order-preserving trees stay on heap). |

### 9e. Running the scenarios

**Unit tier.** Commands in 9c. Record each assertion and the printed values.

1. **U1, the check alone** (`RandomPartitioner`, as `MerkleTreeTest`): for `maxsize` *M* in {2, 1024, 16384}, a tree over the full range with `RECOMMENDED_DEPTH`; call `split` on random tokens until it returns `false`. Assert `size == M` when it does, and that one more call returns `false` with `size` unchanged. Measure allocation per call with `ThreadMXBean.getThreadAllocatedBytes`: a successful split allocates about one inner node and two leaves; a refused one about nothing. **(Amended 2026-10-14, step-0 audit, the numbers:** the baseline is the largest reading of 1,000 empty measurement intervals; each of 1,000 refused calls allocates **no more than that baseline**; every successful split allocates **at least** `shallow(OnHeapInner) + 2 × shallow(OnHeapLeaf)` (`ObjectSizes.measure`, printed); the first `false` comes with `size == M` exactly.)
2. **U2, `init()`:** the same *M*, plus *M* = 1000: `init()` gives `size == M`, and 512 for 1000.
3. **U3, the derivation:** load 2^14 partitions and flush (as `ValidatorTest.testSizeLimiting`). For *s* in {1, 2, 4} MiB with depth cap 20, validate with `evenTreeDistribution = true` (`init`): predicted *L* = 2^12, 2^13, 2^14 (the partition term binds at 4). Repeat *s* = 1 and 2 with `false` (split, `ByteOrderedPartitioner`): the same *L*, with the refusal at `size == maxsize`. Not *s* = 4 on the split path: 2^14 leaves from about 128 samples needs about 128 splits per sample, past the depth limit of 126, so `TooDeep` would stop it first (§5). Then *s* = 64 with `setRepairSessionMaxTreeDepth(10)`: *L* = 2^10. Print `MerkleTree.estimatedMaxDepthForBytes(partitioner, b, 32)` for *b* = 0.5, 1, 2, 8, 32 MiB: the table the cluster prediction uses. **(Amended 2026-10-14, step-0 audit, before any reading:** (a) the table is printed for both `ByteOrderedPartitioner` and `Murmur3Partitioner`, and for *b* = 0.5, 1, 2, 4, 8, 32, 64 MiB (64 MiB is the default 128 MiB at RF 2), with the leaf and inner sizes the method uses. (b) **The split-path repeats run on a second table loaded with 2^16 partitions** (about 512 key samples), not the 2^14 one: with about 128 samples, 2^13 leaves need about 64 splits per sample on average and more on the most-picked one, and the test keys (decimal strings under a byte-order token) share long prefixes, so the deepest leaf could approach the depth limit of 126 and `TooDeep` could stop the loop before `maxsize`. At 2^16, *s* = 1 and 2 still give *L* = 2^12 and 2^13 (the partition term is 16), with about 8 and 16 splits per sample. Each split-path tree's `size` and `maxsize` are printed; `size < maxsize` marks a `TooDeep` stop.)
4. **U4, the overflow:** with the same data, *s* in {2047, 2048, 4096, 4097, 5120}: predicted *L* = 2^14, 2, 2, 2^12, 2^14. (Amended 2026-10-14: on the `init()` path, `evenTreeDistribution = true`, so `TooDeep` cannot stop the 2^14-leaf rows; the test also prints `s × 1048576` computed in `int`, the product `:62` computes.)

**Cluster tier, arm M (Murmur3).**

1. **Control** — both nodes up, data loaded and flushed; histogram of node 2 idle; one repair at the default *s*: record *L*, *n*, and the two off-heap lines.
2. **Scenario A** — for *s* = 1, 4, 16, 64 MiB: set on both nodes, read back, repair, record *L*, *n*, `split calls`, the off-heap lines. Repeat each with `hold-trees.btm` for the histogram on node 2.
3. **Scenario B** — load the second 2^20 partitions, flush, repair at *s* = 4 and 16: record *L*.
4. **Scenario C** — *s* = 2048 and 4097: record *L* and the off-heap lines. Then the depth cap: stop both nodes, add `repair_session_max_tree_depth: 15`, restart, *s* = 64, repair, record *L*; remove the line afterwards. Optional: the over-streaming step (9c).

**Cluster tier, arm O (`ByteOrderedPartitioner`).** Fresh data directories, `partitioner: org.apache.cassandra.dht.ByteOrderedPartitioner`. A token is the key's raw bytes, so choose the two `initial_token`s from the keys stress writes: on a scratch single node with the same partitioner, load 1,000 rows and read `SELECT token(key) FROM keyspace1.standard1 LIMIT 20`; set node 1's token to the smallest and node 2's to the median, in hex. Load and flush as in arm M, then check that node 1's *n* (the `Created ... merkle trees` line of a first repair) is above 2^16; if not, move node 2's token and reload. For *s* = 4 and 16 MiB: repair with `split-trace.btm` loaded; record *L*, the refusal lines and their `size`/`maxsize`, any `toodeep` line, and the sample count (`nodetool tablestats` index summary entries).
**(Amended 2026-10-14, step-0 audit:** (a) in a byte-ordered table `SELECT token(key) … LIMIT 20` returns the 20 **smallest** tokens, so their median is not the data's. Read all 1,000 tokens instead (`SELECT token(key) FROM keyspace1.standard1`, paging off), set **node 2's token to `00`** (one zero byte, below every stress key) and **node 1's to the median of the 1,000**. Node 1's primary range is then `(00, median]`, about half the keys, and does not wrap. (b) The sample count is the `samples=` line of `split-trace.btm` (rule 4): `nodetool tablestats` does not print index-summary entries.)**

**Record for stage 4:** the configuration in force, the exact commands, and the raw readings from 9d for every run.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3a` — band A1, row `MerkleTree.java:409#1` of `stage2-ai-preprocessing/bands.md`, judged qualifying in the A1 pass (2026-09-28) and queued as `pending.md` item 7 under the name `repair_session_max_tree_depth`. |
| **Filed by / Date** | Claude (AI long path), 2026-10-13. |
| **Line numbers checked** | 2026-10-13, every cited line against the local clone at `cassandra-5.0.9` (`git describe --tags`). |
| **Escape hatch / Target-3 note** | No path exceeds `maxsize`. Three Target-3 notes: (1) **the check is not reached on the default partitioner** (§5); (2) **the 32-bit overflow** at `ValidationManager.java:62` gives two-leaf trees from 2048 to 4096 MiB, the default at a 32 GiB heap (§4); (3) the coordinator holds trees sized by the **replicas'** settings (§8). |
| **Stage-4 feedback** | **2026-10-14, long path, run 1 on `pc57`: Confirmed at both tiers; arm M non-domination as recorded; overflow as recorded; no run 2** ([results](../../stage4-runtime-verification/results/repair_session_space-split-maxsize--guided.md); harness `../../../stage4-runtime-verification/long-path/harness/repair_session_space-split-maxsize/`; uncommitted). Step-0 audit **Ready after amendments** (§9 hash `92f86a2d…`): the off-heap buffer is `82 L + 32` (`allocate()` gets the leaf count), the depth table is printed per partitioner, arm O's tokens and sample count, the U3 split path on 2^16 keys. Unit: `split()` refuses at `size == maxsize` and a refused call allocates 0 B; `init()` builds `maxsize` leaves; leaf + inner = 200 B (Murmur3) and 208 B (byte order); U4's 32-bit products wrap as §4 says (2048 → −2^31, 4096 → 0, 4097 → 2^20). Cluster, two nodes, RF 2, 2^20 rows: leaves per tree 2,048 · 8,192 · 32,768 · 131,072 · 262,144 at 1 · 4 · 16 · 64 · 128 (default) MiB, each the predicted `maxsize`, unchanged when the data doubles; on Murmur3 `split()` is never called; on byte order one refusal at `size == maxsize` per validation, no `TooDeep`; replica heap +*L* leaves and +(*L* − 1) inner nodes; coordinator two direct buffers of exactly `82 L + 32` B; depth cap 15 → 2^15. **2048 MiB gives two-leaf trees and 4097 MiB the 1 MiB count, at runtime.** The over-streaming step was not run. |
| **Notes** | Renamed from the queue's `repair_session_max_tree_depth`: that key is deprecated in 5.0, defaults to 20 and only caps the depth, while `repair_session_space` is the budget a user tunes and binds below heaps of about 6 to 12 GiB at RF 3 (§4). **For stage 3 (2026-10-14, from the stage-4 audit, not applied):** §7's "Rough sizing" off-heap formula `(L − 1) × 50 + L × 32` should read `L × 50 + (L + 1) × 32` — `allocate()`'s `innerNodeCount` parameter receives the leaf count (`MerkleTree.java:781`, `:714`, `:789`, `:799-802`); stage 4 read exactly `82 L + 32` B per buffer. §5's concern that `TooDeep` may bind first: at the default, byte order, about 4,273 samples gave 2^18 leaves (≈ 61 splits per sample) with a capacity stop and no `TooDeep`. |

---

## 11. Notes

- **Not the A2 refusals in the same file.** `MerkleTree.java:1103`, `:1137`, `:1322`, `:1420` were refused in the A2 batch as invariant guards on the pre-sized off-heap buffer; they check the coordinator's copy fits the buffer sized from the received tree, not the budget.
- **The `log10` depth in `init()`** is exact for powers of two up to 2^30, so `init()` builds exactly `maxsize` leaves for every `maxsize` `ValidationManager` produces; a non-power-of-two `maxsize` (only reachable from tests) gives the next lower power of two.
- **The overflow is in this version's source**; whether a later release fixed it (a `1048576L` literal, or `toBytes()`) was not checked. Stage 4's U4 settles it for 5.0.9.
