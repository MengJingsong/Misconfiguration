# codec cache maximum weight (`CodecRegistry` `maximumWeight(1000)`) — verification solution  <!-- file: cases/codec_cache_maximum_weight-defaultCacheBuilder-cache_weight--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (capacity-set unit: the codec-cache builder chain that sets `initialCapacity(100)` and `maximumWeight(1000)`), **linked**: [`CodecRegistry.java:396`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/CodecRegistry.java#L396) (statement spans [`#L395-L401`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/CodecRegistry.java#L395-L401)) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `negative`. The limit is a hard-coded total of type-complexity units for a Guava cache of driver `TypeCodec` objects. It is not a byte budget. In normal use the cache holds kilobytes to low megabytes, so it does not bound a memory-significant object, and its bytes do not follow the limit. |
| Ground | (1) The weigher counts type-nesting depth, not bytes ([`CodecRegistry.java:297-353`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/CodecRegistry.java#L297-L353)). A tuple or UDT of any width made of primitives weighs 1. Shallow collections of primitives weigh 0 and are never evicted, so the bytes held per unit of weight have no upper bound. (2) The server reaches the cache only through the static `JavaDriverUtils` registry, when it resolves UDF/UDA argument and return types (and from the client-side `CQLSSTableWriter`). Each live UDF keeps its own reference to the codec (`UDFDataType.typeCodec`), so evicting it frees nothing while the function exists. (3) Realistic totals are at most about 1000 weighted entries plus a few hundred zero-weight entries, at tens to hundreds of bytes each (roughly 0.1–0.5 MB), which is negligible next to the heap. |

## A. Constraint trace

**A1. The constraint.**
- *Name:* maximum weight of the driver-codec cache in `org.apache.cassandra.cql3.functions.types.CodecRegistry`. The name used in this case is `codec_cache_maximum_weight`.
- *Kind:* constant, a literal in code.
- *Declaration:* [`CodecRegistry.java:400`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/CodecRegistry.java#L400): `.maximumWeight(1000)`. It is part of the `CacheBuilder` chain that starts at the given line 396, inside `defaultCacheBuilder()` (L393-406). That method is called once per `CodecRegistry` instance from its constructor (L387-391).
- *Same statement:* `.initialCapacity(100)` at L399. That is only a pre-sizing hint for the hash table. The comment at L397-398 explains it as "roughly 1/4" of 440 codecs. It caps nothing: Guava grows the table past it. This case therefore treats `maximumWeight(1000)` as the constraint of the capacity-set unit and covers `initialCapacity` only as a non-cap.
- *Unit:* abstract weight units returned by `TypeCodecWeigher` (L297-353). They are not bytes and not entries.
- *Default and derivation:* 1000, with no derivation. The tree contains no comment that justifies the number.
- *How to set:* not settable. There is no yaml key, `-D` property or JMX attribute. Changing it means editing the source and rebuilding. The relevant registry instance is the `static final` field `JavaDriverUtils.codecRegistry` ([`JavaDriverUtils.java:37`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/JavaDriverUtils.java#L37)), which is created once per JVM, so any change needs a restart.

**A2. What it caps.** On-heap memory, nominally: a Guava `LoadingCache<CacheKey, TypeCodec<?>>` (field `cache`, L382) that memoizes driver codecs for non-primitive CQL types. The quantity the cache compares against the limit is the **sum of `weigh(key, value)` over its entries**, computed by `TypeCodecWeigher` as follows:
- 0 for codecs registered by a user (L303). Nothing in `src/java` calls `register`.
- 0 for primitive types (`default: return 0`, L351-352).
- For list, set and map: the level plus the weights of the element types at level+1 (L310-320). `list<int>` and `map<text,int>` therefore weigh 0, and `list<frozen<list<int>>>` weighs 1.
- For vector, UDT and tuple: the level plus the element weights, with a minimum of 1 (L321-348). `vector<int,N>`, and a tuple or UDT of any number of primitive fields, each weigh exactly 1.
- 1 for custom types (L349-350).

The weight is fixed when the entry is inserted, and it does not depend on the codec's size in bytes.

**A3. Mechanism.**
1. A caller asks for a codec. The server paths are:
   - [`JavaDriverUtils.java:60-63`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/JavaDriverUtils.java#L60-L63) calls `codecRegistry.codecFor(dataType)`.
   - That is reached from `UDFDataType` (`src/java/org/apache/cassandra/cql3/functions/UDFDataType.java:72`). `UDFunction` (`UDFunction.java:219-220`) and `UDAggregate` (`UDAggregate.java:66-67`) create a `UDFDataType` for every argument and return type when a function is created or loaded from schema.
   - `CQLSSTableWriter.java:150` is a client-side offline writer, not node memory.
   - `UDFContextImpl.java:90,114` calls `driverType(...)`, which passes the same registry to `DataTypeClassNameParser` but performs no cache lookup itself.
2. `codecFor(DataType)` (L527) calls `lookupCodec` (L597-627). Primitive types are returned straight from `BUILT_IN_CODECS_MAP` (L600-605) and never touch the cache. Anything else runs `cache.get(new CacheKey(cqlType, javaType))` (L610-611).
3. On a miss, `TypeCodecCacheLoader.load` (L259-276) builds the codec with `createCodec` → `maybeCreateCodec` (L716-783). Nested element codecs come from `findCodec` and are not cached separately. The new entry is inserted and weighed by `TypeCodecWeigher`.
4. **The check** is the cache's weight bound, configured in the given statement, [`CodecRegistry.java:396`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/CodecRegistry.java#L396) through [`:400`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/CodecRegistry.java#L400). Guava enforces it, not Cassandra code. As I recall from Guava 32.0.1 `LocalCache`:
   - `CacheBuilder`'s default `concurrencyLevel` is 4.
   - Because 4 × 20 ≤ 1000, there are 4 segments, each with `maxSegmentWeight` = 1000/4 = 250.
   - After each write, `evictEntries` removes entries in access order while the segment's total weight is above 250.
   - `getNextEvictable` skips entries whose weight is 0.

   **Outcome when the limit is reached:** the least recently used weighted entry in that segment is evicted silently. When the TRACE logger is on, `TypeCodecRemovalListener` (L360-371) logs it. No error is raised and the caller still gets its codec. **Outcome below the limit:** the entry stays.
5. **Bypasses and overshoot:**
   - Zero-weight entries (shallow collections of primitives) are never evicted and never counted. There are at most 20 + 20 + 20² = 440 of them, because `CollectionType.equals` ignores `frozen` (`DataType.java:625-631`) and `text`/`varchar` compare equal (`DataType.java:575-581`). This is the same 440 that the comment at L397 gives.
   - Bytes per weight unit are unbounded. A `tuple<int × M>` weighs 1 whatever M is, but its `TupleType.types` is an `ImmutableList` of M references (`TupleType.java:40-46`).
   - Eviction does not release a codec that a live `UDFDataType` still references (`UDFDataType.java:55-72`, field `typeCodec`), so for UDF types the cache never drives memory down while the function exists.
   - `findCodec` and `createCodec` for nested element types allocate codecs outside the cache (L629-683).

**A4. Other consumers.** These use the same resource (heap) outside this limit's control and dominate the UDF path:
- the UDF's compiled Java class and class loader (metaspace and heap);
- `UDFunction` and `UDFDataType` objects;
- schema objects in `Schema` and `KeyspaceMetadata`, plus `system_schema.functions` memtable and sstable data;
- the uncached nested codecs from `findCodec`;
- the static `BUILT_IN_CODECS` and `BUILT_IN_CODECS_MAP` (L163-197).

Outside UDFs, Cassandra's real heap and off-heap users (memtables, key and row caches, chunk cache, prepared-statement cache in `QueryProcessor.java:116`, streaming state cache in `StreamManager.java:271`) are unrelated to this cache.

**A5. Evidence beyond the source.**
- Guava `CacheBuilder.maximumWeight` javadoc, which says that entries of weight zero are never evicted for size and that the cache may evict before the limit is exceeded: https://guava.dev/releases/32.0.1-jre/api/docs/com/google/common/cache/CacheBuilder.html#maximumWeight(long)
- Guava 32.0.1 `LocalCache` source (segment count, `maxSegmentWeight`, `evictEntries`, `getNextEvictable`): https://github.com/google/guava/blob/v32.0.1/guava/src/com/google/common/cache/LocalCache.java
- Guava version 32.0.1-jre, from `.build/parent-pom-template.xml:307-309`.
- The class is a copy of the DataStax Java driver 3.x `CodecRegistry`, with the same weigher and `maximumWeight(1000)`: https://github.com/datastax/java-driver/blob/3.x/driver-core/src/main/java/com/datastax/driver/core/CodecRegistry.java
- No Cassandra JIRA issue was found or relied on, and git history is not present in the source copy.

## B. Verification solution

**B1. Claim under test (negative).** The heap retained by `CodecRegistry`'s codec cache does not follow `maximumWeight(1000)`. The limit does cap the cache's weight sum, and with it the count of weighted entries. The retained bytes, however, vary independently:
- zero-weight entries add bytes without being counted;
- at a constant weight sum of 1000, retained bytes scale with tuple width M (a factor of 10³–10⁴ across the M values used);
- on a running node, the heap held by UDF codecs is the same at, below and past the limit, because live functions keep their codecs; only after `DROP FUNCTION` does the cache retain at most about 1000 weighted codecs.

The claim is refuted if retained bytes are roughly proportional to the weight sum, and plateau with it, whatever M is.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11 (`java -version` reports 11.x), Ant 1.10+.
- Copy the tree to local disk: `export WORK=/mydata/<run>/codec96` (any local disk with ≥ 5 GB free), then `rsync -a ~/cassandra-5.0.9/ $WORK/cassandra/` and `cd $WORK/cassandra`.
- **Knob patch, needed for B2b values other than 1000.** Replace L400 in the copy:
  `sed -i 's/\.maximumWeight(1000)/.maximumWeight(Long.getLong("cassandra.test.codec_cache_max_weight", 1000L))/' src/java/org/apache/cassandra/cql3/functions/types/CodecRegistry.java`
  Check it with `grep -n maximumWeight src/java/org/apache/cassandra/cql3/functions/types/CodecRegistry.java`, which should show L400 changed. With the property unset, behaviour is identical to stock.
- Build with `ant -Duse.jdk11=true jar build-test`. Running the test also triggers `maybe-build-test`.
- Test source: `test/unit/org/apache/cassandra/cql3/functions/types/CodecCacheWeightProbeTest.java` in the **copy**. It must live in this package to reach the package-private constructors. The test JVM already runs the jamm agent (`build.xml:1159`), so `ObjectSizes.measureDeep` works.
- JVM options are passed through `-Dtest.jvm.args` (`build.xml:1192`).

The probe test, as a skeleton to paste:

```java
package org.apache.cassandra.cql3.functions.types;

import java.lang.reflect.*;
import java.util.*;
import com.google.common.cache.*;
import org.junit.Test;
import org.apache.cassandra.transport.ProtocolVersion;
import org.apache.cassandra.utils.ObjectSizes;

public class CodecCacheWeightProbeTest
{
    static LoadingCache<Object, TypeCodec<?>> cache(CodecRegistry r) throws Exception
    { Field f = CodecRegistry.class.getDeclaredField("cache"); f.setAccessible(true); return (LoadingCache<Object, TypeCodec<?>>) f.get(r); }

    static long weightSum(CodecRegistry r) throws Exception
    {
        Class<?> wc = Class.forName("org.apache.cassandra.cql3.functions.types.CodecRegistry$TypeCodecWeigher");
        Constructor<?> k = wc.getDeclaredConstructor(CodecRegistry.class); k.setAccessible(true);
        Weigher<Object, TypeCodec<?>> w = (Weigher<Object, TypeCodec<?>>) k.newInstance(r);
        long s = 0; for (Map.Entry<Object, TypeCodec<?>> e : cache(r).asMap().entrySet()) s += w.weigh(e.getKey(), e.getValue());
        return s;
    }

    static void report(String tag, CodecRegistry r) throws Exception
    {
        LoadingCache<Object, TypeCodec<?>> c = cache(r); c.cleanUp();
        System.gc(); Thread.sleep(200);
        long used = Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory();
        System.out.printf("PROBE %s size=%d weight=%d deepBytes=%d heapUsed=%d%n",
                          tag, c.size(), weightSum(r), ObjectSizes.measureDeep(r), used);
    }

    static DataType[] wideTuple(int m, int d)            // weight 1 for any m
    {
        DataType[] t = new DataType[m + 1];
        Arrays.fill(t, 0, m, DataType.cint());
        t[m] = DataType.vector(DataType.cint(), d);       // makes each key distinct; weighs 1 at level 1
        return t;
    }

    @Test public void narrow() throws Exception        // W-A
    {
        int k = Integer.getInteger("probe.k", 2000);
        CodecRegistry r = new CodecRegistry();
        report("A-empty", r);
        for (int d = 1; d <= k; d++) r.codecFor(DataType.vector(DataType.cint(), d));
        report("A-k" + k, r);
    }

    static final DataType[] PRIMS = { DataType.ascii(), DataType.bigint(), DataType.blob(), DataType.cboolean(),
        DataType.counter(), DataType.decimal(), DataType.cdouble(), DataType.cfloat(), DataType.inet(), DataType.cint(),
        DataType.text(), DataType.timestamp(), DataType.uuid(), DataType.varint(), DataType.timeuuid(),
        DataType.smallint(), DataType.tinyint(), DataType.date(), DataType.time(), DataType.duration() };   // 20

    @Test public void zeroWeight() throws Exception    // W-B
    {
        CodecRegistry r = new CodecRegistry();
        for (DataType a : PRIMS)
        {
            r.codecFor(DataType.list(a)); r.codecFor(DataType.set(a));
            for (DataType b : PRIMS) r.codecFor(DataType.map(a, b));
        }
        report("B-zero-only", r);
        for (int d = 1; d <= 5000; d++) r.codecFor(DataType.vector(DataType.cint(), d));
        report("B-zero-plus-5000-vectors", r);
        DataType li = DataType.list(DataType.cint());
        System.out.println("PROBE B list<int> still cached: "
                           + cache(r).asMap().values().stream().anyMatch(c -> c.getCqlType().equals(li)));
    }

    @Test public void wide() throws Exception          // W-C
    {
        int m = Integer.getInteger("probe.m", 1000), k = Integer.getInteger("probe.k", 2000);
        CodecRegistry r = new CodecRegistry();
        report("C-empty-m" + m, r);
        for (int d = 1; d <= k; d++) r.codecFor(TupleType.of(ProtocolVersion.CURRENT, r, wideTuple(m, d)));
        report("C-m" + m + "-k" + k, r);
    }
}
```

**B2b. Knobs.**
- `cassandra.test.codec_cache_max_weight` takes the values **100, 1000 (stock), 10000**. These are one decade below, at, and one decade above stock, and they are used only on the patched copy. It is set with `-Dtest.jvm.args="-Dcassandra.test.codec_cache_max_weight=<v>"`. With Guava's 4 segments the per-segment caps are 25, 250 and 2500.
- Workload knobs:
  - `probe.k` (distinct keys): 500, 1000, 2000, 5000; and 12000 for the 10000 run.
  - `probe.m` (tuple width at constant weight 1): 1, 1000, 10000.

**B2c. Workload.**
- **W-A:** K distinct `vector<int,d>` codecs, each weighing 1. The weight sum would be K without eviction, so K=2000 and K=5000 are 2× and 5× past the limit of 1000, and K=500 is below it.
- **W-B:** every shallow list, set and map of the 20 primitives: 20 + 20 + 400 = 440 keys, all weighing 0. Then 5000 weight-1 vectors are added on top.
- **W-C:** K=2000 distinct `tuple<int × M, vector<int,d>>`, each weighing 0 + M·0 + 1 = 1. The weight sum would be 2000, so the limit is passed 2× and the cache should plateau at 1000 entries. Each retained `TupleType` holds an `ImmutableList` of M+1 references, about 4(M+1) bytes with compressed oops plus around 100 bytes of fixed overhead. At the plateau:
  - M=1: about 1000 × 0.2 KB ≈ 0.2 MB;
  - M=1000: about 1000 × 4.1 KB ≈ 4 MB;
  - M=10000: about 1000 × 40 KB ≈ 40 MB, which fits the default test heap.

**B2d. Observables and instruments.**
- Per checkpoint, the `PROBE` line on stdout, captured in `build/test/output/TEST-*.xml` / `-Dtest.output` or on the console. It holds:
  - `size`: `cache.size()` after `cleanUp()`, the count the cap acts on;
  - `weight`: the sum of the real `TypeCodecWeigher` over entries, the check's own operand;
  - `deepBytes`: `ObjectSizes.measureDeep(registry)` through jamm, the retained bytes of the registry and its cache;
  - `heapUsed` after `System.gc()`, a coarse cross-check.
- Each run is sampled once at the end; the B2e repetitions give 3 samples per cell.
- Not observable directly: Guava's internal per-segment weights, which are inferred from `size` and `weight`.

**B2e. Procedure.**
1. Set up B2a: copy the tree, apply the patch, then run `ant -Duse.jdk11=true jar build-test`.
2. Stock-equivalent runs (property unset = 1000). Repeat each command 3 times:
   ```
   for K in 500 1000 2000 5000; do ant testsome -Dtest.name=org.apache.cassandra.cql3.functions.types.CodecCacheWeightProbeTest -Dtest.methods=narrow -Dtest.jvm.args="-Dprobe.k=$K" | grep PROBE; done
   ant testsome -Dtest.name=org.apache.cassandra.cql3.functions.types.CodecCacheWeightProbeTest -Dtest.methods=zeroWeight | grep PROBE
   for M in 1 1000 10000; do ant testsome -Dtest.name=org.apache.cassandra.cql3.functions.types.CodecCacheWeightProbeTest -Dtest.methods=wide -Dtest.jvm.args="-Dprobe.m=$M -Dprobe.k=2000" | grep PROBE; done
   ```
   If `PROBE` lines go only to the XML report, read `build/test/output/TEST-org.apache.cassandra.cql3.functions.types.CodecCacheWeightProbeTest-*.xml` instead.
3. Knob runs (positive control on the cache's own operand): `narrow` with `-Dtest.jvm.args="-Dcassandra.test.codec_cache_max_weight=100 -Dprobe.k=2000"`, then with `=10000 -Dprobe.k=12000`. Also run `wide` with M=1000 and K=2000 at max-weight 100 and at 10000.
4. Record every `PROBE` line in a table: method, knob, K, M, size, weight, deepBytes.
5. Run `rm -rf $WORK/cassandra/build/test/{output,logs}` if space is needed. No process outlives `ant`.

**B2f. Predictions** (stated before any run; cache cap 1000 unless noted).

| Run | size | weight | deepBytes |
|---|---|---|---|
| A, K=500 | 500 | 500 | baseline + ≈ 500 × (0.1–0.2 KB) |
| A, K=1000 | 950–1000 (eviction may start just before 1000 because of per-segment caps of 250) | = size | ≈ 0.1–0.3 MB |
| A, K=2000, 5000 | 1000 (accept 990–1000) | 1000 | the same as K=1000 within ±10 %: plateau |
| B, zero-only | 440 | 0 | ≈ 0.1–0.3 MB |
| B, + 5000 vectors | 440 + 1000 = 1440 | 1000 | zero-weight entries all still present (`list<int> still cached: true`) |
| C, M=1 / 1000 / 10000, K=2000 | 1000 in each | 1000 in each | ≈ 0.2 MB / ≈ 4 MB / ≈ 40 MB: grows about 4 bytes × M per entry while weight stays at 1000 |
| A, K=2000, cap=100 | 100 | 100 | about one tenth of the cap-1000 plateau |
| A, K=12000, cap=10000 | 10000 | 10000 | about 10× the cap-1000 plateau |
| C, M=1000, cap=100 / 10000 | 100 / 2000 (K < cap) | 100 / 2000 | ≈ 0.4 MB / ≈ 8 MB |

The claim is wrong if, in W-C, `deepBytes` at M=10000 stays within 2× of M=1 while `weight` is 1000 in both, meaning bytes are bounded by weight. It is also wrong if W-B shows zero-weight entries being evicted or counted.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| W-C `deepBytes` rises about linearly with M (≥ 100× from M=1 to M=10000) while `size` = `weight` = 1000 | Bytes do not follow the constraint: **claim confirmed** |
| W-B: 440 zero-weight entries stay alongside 1000 weighted ones and the total exceeds 1000 entries | The cap does not count part of the cache: **claim confirmed** |
| `size`/`weight` plateau at 100 / 1000 / 10000 as the knob changes (positive control moves) and bytes per entry still depend on M | The cap binds on its own operand, but bytes are governed by type shape: **claim confirmed** |
| `deepBytes` roughly ∝ `weight`, the same at every M, and plateaus with the knob | Usage follows the constraint: **claim refuted** |
| `size` never plateaus (grows to K) even at K=5000 with cap 1000 | Limit not enforced as traced, so A3 is wrong: **not confirmed**, re-trace |
| `size`/`weight` do not change between cap 100 and 10000 (the patch did not take effect) | Positive control did not move: **not confirmed**. Check the patch and the property spelling. |
| K below the cap in every run (no eviction seen) | Limit never reached: **not confirmed** |

**B2h. Controls.**
- An empty-registry baseline (`*-empty` lines) separates fixed overhead.
- `weight` is computed with the real private weigher, not a copy.
- `size` is read after `cleanUp()`, so pending evictions are applied.
- The same K and the same key generator are used across M, so only bytes per entry change.
- The stock (unpatched) jar is equivalent to the property unset. Optionally confirm by running `narrow` K=2000 on an unpatched copy and getting the same `size`.
- Three repetitions per cell, with medians reported.
- `deepBytes` excludes static singletons such as `BUILT_IN_CODECS`, since statics are not traversed, so it reflects instance state only.

**B2i. Stage-4 audit amendments (2026-11-25, stage 4, before unit run 1; none changes B1, a B2f prediction or a B2g row).**
- *S4-A1 (B2a, paths).* `WORK=/mydata/jingsong-cass-s4/o96` on the run node (local LVM disk). The tree is not rsynced from `~/cassandra-5.0.9` (absent on the shared nodes): `cp -a /mydata/s4/cassandra-base $WORK/unit` (a `copy-source.sh` copy of the repository's `systems/cassandra/source/`, 5.0.9, already built; `src/` and `test/` checked identical to the repository with `diff -rq`, only build-generated files differ). The patch is applied to `$WORK/unit` only, then `ant -Duse.jdk11=true jar build-test`. The test directory `test/unit/org/apache/cassandra/cql3/functions/types/` does not exist at the tag and is created.
- *S4-A2 (B2d, reading the PROBE line; runbook defect S4-D1).* The unit-test JVM sends `System.out` through a logger that writes each `printf` argument as its own log line (`SubstituteLogger.java:222 - <token>`), so no single `PROBE` line appears in the console or the XML. The run script joins the tokens of the Standard Output block and splits at `PROBE `; the probe code is unchanged. Each reassembled line is kept in `raw/unit/probe-<tag>.txt` beside the full `ant-<tag>.log`.
- *S4-A3 (B2e, repetitions).* Every cell, including the knob runs of step 3, is run 3 times (each a fresh JVM); the median is reported.
- *S4-A4 (B2f/B2g, numeric reading rules fixed before any reading).* "Plateau" = the K=2000 and K=5000 medians of `size` and `deepBytes` within ±10 % of each other (B2f's own tolerance). `size` "= 1000" accepts 950–1000 (B2f's per-segment tolerance). "≈ X MB" predictions of `deepBytes` are order-of-magnitude estimates; they count as met within [0.5X, 2X], and a miss is recorded as a deviation, not a row change. W-C "rises about linearly with M" = median `deepBytes` at M=10000 ≥ 100× that at M=1 with `weight` = 1000 in both (B2g row 1); "bounded by weight" = within 2× (B2f). Positive control "moves" = median `size` at cap 100 ≤ 110 and at cap 10000 ≥ 9000, with `deepBytes` changing in the same direction.

### B3. Cluster tier

**B3a. Environment and build.**
- One node (Linux, JDK 11, Ant). A second node adds nothing, because the cache is per JVM.
- Build from a local copy, **without** the B2 patch (stock 1000): `rsync -a ~/cassandra-5.0.9/ $WORK/node/` then `cd $WORK/node && ant -Duse.jdk11=true jar`.
- Edits to `$WORK/node/conf/cassandra.yaml`:
  - `user_defined_functions_enabled: true` (`conf/cassandra.yaml:1760`, `Config.java:588`)
  - `data_file_directories: [$WORK/data]`
  - `commitlog_directory: $WORK/commitlog`
  - `hints_directory: $WORK/hints`
  - `saved_caches_directory: $WORK/saved_caches`
  - `cdc_raw_directory: $WORK/cdc`
  - `listen_address`/`rpc_address: 127.0.0.1`
  - `cluster_name: 'codec96'`
- Heap: `export MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M`.
- Leave the default GC in `conf/jvm11-server.options`.
- Start with `bin/cassandra -p $WORK/cassandra.pid`, then wait until `bin/nodetool status` shows `UN`.

**B3b. Knobs.**
- The constraint itself is not settable on a stock node, so it stays at 1000. The tier varies the load against it instead:
  - the number N of distinct UDF argument types: **500 (below the limit), 2000 (2× past), 4000 (4× past)**;
  - for the bytes test, tuple width **M ∈ {1, 2000}** at K=1500 functions (1.5× past).
- Optional positive-control re-run: the B2-patched jar with `JVM_EXTRA_OPTS="-Dcassandra.test.codec_cache_max_weight=100"` exported before `bin/cassandra`.

**B3c. Workload.**
- **Narrow phase.** In keyspace `ks`, create functions `f_i(v vector<int, i>) CALLED ON NULL INPUT RETURNS int LANGUAGE java AS 'return 1;'` for i = 1..4000. Each new argument type causes one `codecFor(vector<int,i>)` in `UDFDataType` and inserts one weight-1 cache entry. The weight sum would be N, so N=500 is below the limit and N=2000 and N=4000 are past it. Generate the statements:
  ```
  bin/cqlsh 127.0.0.1 -e "CREATE KEYSPACE ks WITH replication={'class':'SimpleStrategy','replication_factor':1};"
  python3 - <<'EOF' > $WORK/narrow_1_500.cql   # repeat with ranges 501-2000 and 2001-4000
  for i in range(1, 501):
      print(f"CREATE FUNCTION ks.f_{i}(v vector<int, {i}>) CALLED ON NULL INPUT RETURNS int LANGUAGE java AS 'return 1;';")
  EOF
  ```
  Then drop all of them (`DROP FUNCTION ks.f_i;` for every i).
- **Wide phase**, after the narrow drop. Create `g_i(t tuple<int × M, vector<int, i>>) ... AS 'return 1;'` for i = 1..1500, then drop them all. Run it once with M=1 and once with M=2000. Each argument type weighs 1, so the cache plateaus at about 1000 entries.
  - The codecs that remain **after** the drop are held only by the cache: about 1000 × 4·(M+1) bytes, which is about 8 MB at M=2000 and about 0.1 MB at M=1.
  - The schema text for M=2000 is about 10 KB per function, about 15 MB in total in `system_schema`. That is fine on local disk.
- Expected duration: about 5–30 min per phase, because each Java UDF is compiled.

**B3d. Observables and instruments.** At each checkpoint, sample 3 times, 30 s apart:
- **Live class histogram**, which forces a full GC: `jcmd $(cat $WORK/cassandra.pid) GC.class_histogram > $WORK/h_<tag>_<n>.txt`. From it take:
  - instance counts of `org.apache.cassandra.cql3.functions.types.VectorCodec$FixedLength` (codecs for `vector<int,i>`, held by UDFs and/or the cache);
  - instance counts of `org.apache.cassandra.cql3.functions.types.TypeCodec$TupleCodec` and `org.apache.cassandra.cql3.functions.types.TupleType`;
  - instance count of `com.google.common.cache.LocalCache$WeightedStrongValueReference` (entries of weighted Guava caches; the codec cache is the only one active on an idle node apart from streaming, so subtract the baseline);
  - bytes of `[Ljava.lang.Object;` (the `ImmutableList` arrays of wide tuples).
- **Heap after full GC:** `jcmd <pid> GC.run; sleep 5; jcmd <pid> GC.heap_info`, plus `bin/nodetool info | grep -i heap`.
- **Function count:** `bin/cqlsh -e "SELECT count(*) FROM system_schema.functions WHERE keyspace_name='ks';"`.
- Not observable directly: the cache's weight sum and which entries it holds. They are inferred from codec counts after the drops, when UDF references are gone. A heap dump (`jcmd <pid> GC.heap_dump $WORK/h.hprof`, opened in Eclipse MAT, path to GC roots of `TupleCodec` → `JavaDriverUtils.codecRegistry`) is an optional confirmation. Delete the dump afterwards.

**B3e. Procedure.**
1. Build and start the node (B3a). Take the baseline: histogram, heap and function count (tag `base`).
2. Create the keyspace. Run `bin/cqlsh 127.0.0.1 -f $WORK/narrow_1_500.cql`, then sample (tag `n500`).
3. Run `narrow_501_2000.cql`, then sample (tag `n2000`). Run `narrow_2001_4000.cql`, then sample (tag `n4000`).
4. Drop all `f_i` (generated `DROP FUNCTION` file), then sample (tag `ndrop`).
5. Wide with M=1: create `g_1..g_1500`, then sample (`w1`). Drop them, then sample (`w1drop`).
6. Wide with M=2000: create `g_1..g_1500` (rename to `h_i` so they do not collide with the earlier set), then sample (`w2000`). Drop them, then sample (`w2000drop`).
7. Optional positive-control re-run: stop the node (B4), restart it on the patched jar with cap 100, and repeat steps 2–4.
8. Stop and clean up (B4).

**B3f. Predictions** (stated before any run; let Δ be the change from `base`).

| Tag | ΔVectorCodec$FixedLength | ΔWeightedStrongValueReference | Δheap after GC |
|---|---|---|---|
| n500 | ≈ 500 | ≈ 500 | rises (UDF classes and schema dominate, about 10–100 KB per function); the codec share is < 0.1 MB |
| n2000 | ≈ 2000 (not capped: UDFs hold codecs) | ≈ 1000 (plateau) | keeps rising roughly linearly in N, with no knee at N≈1000 |
| n4000 | ≈ 4000 | ≈ 1000 | linear in N, with no knee |
| ndrop | 950–1000 (cache-held remainder; the most recent i) | ≈ 1000 | back to within a few MB of base |
| w1drop | ΔTupleCodec 950–1000 | ≈ 1000 | ≈ base (+ < 0.5 MB) |
| w2000drop | ΔTupleCodec 950–1000 (same count as w1drop) | ≈ 1000 | ≈ +8 MB over `w1drop`; Δ`[Ljava.lang.Object;` bytes ≈ +8 MB |
| cap=100 re-run, ndrop | ≈ 100 | ≈ 100 | ≈ base; n500…n4000 heap deltas the same as at cap 1000 within noise |

The claim is wrong if the heap at n2000 and n4000 stays flat relative to n500, with a knee at about 1000 that matches the cap. It is also wrong if `w2000drop` retains the same bytes as `w1drop` at the same entry count.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Heap rises linearly with N through 500→4000 with no knee at 1000, while `WeightedStrongValueReference` plateaus at ≈1000 (positive control: the cap binds on its own operand and the instrument sees the workload move heap) | Usage flat with respect to the cap while the control moves: **claim confirmed** |
| `VectorCodec$FixedLength` count = N above 1000 | Eviction frees nothing while UDFs live: **claim confirmed** |
| Same post-drop entry count at M=1 and M=2000 but about 8 MB more heap at M=2000 | Bytes not governed by weight: **claim confirmed** |
| Heap plateaus or flattens at N≈1000, and the cap=100 re-run moves the knee to N≈100 | Usage follows the constraint: **claim refuted** |
| `WeightedStrongValueReference` never plateaus (rises to ≈N) | The cap was not reached or not enforced as traced: **not confirmed**. Check that functions were created and look at the heap dump. |
| Heap delta per phase is within the run-to-run noise (±2 MB) at every N, so the workload did not move heap | Positive control did not move: **not confirmed**. Raise N or M. |
| Fewer functions than intended in `system_schema.functions` | Workload not applied: **not confirmed** |

**B3h. Controls.**
- The baseline histogram is taken before any UDF exists, which removes other Guava weighted caches (streaming) and built-in codecs.
- Three samples per checkpoint, each taken after a forced full GC.
- M=1 against M=2000 at the same K isolates bytes per entry at a constant weight.
- The drop phases separate UDF-held memory from cache-held memory.
- The optional patched cap=100 re-run checks that the knee does not move with the cap.
- The function count confirms the workload was applied.
- No client traffic other than the DDL.

**B3i. Stage-4 audit amendments (2026-11-25, stage 4, before cluster run 1; none changes B1, a B3f prediction or a B3g row).**
- *S4-A5 (B3a, paths and start).* `cp -a /mydata/s4/cassandra-base $WORK/node` (stock, unpatched; its `build/apache-cassandra-5.0.9-SNAPSHOT.jar` is the stock `ant jar` output, so no rebuild). The yaml edits of B3a are applied to `$WORK/node/conf/cassandra.yaml` by `harness/mkyaml.py`, with the data directories under `$WORK/cdata/`. `ulimit -n 100000` before `bin/cassandra` (node soft limit 1024); ports 7000, 7199, 9042 checked free. `MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M` as written; G1 (the `jvm11-server.options` default).
- *S4-A6 (B3c, statements).* The CQL files are generated by `harness/gen-cql.py` exactly as B3c gives them (`f_i`, `g_i` for M=1, `h_i` for M=2000, and the matching `DROP FUNCTION` files) and run with `bin/cqlsh 127.0.0.1 --request-timeout=120 -f <file>`; cqlsh's stderr is kept and its error lines counted. The function count of B3d is taken after every create and drop file.
- *S4-A7 (B3d, instruments).* Each sample is: `jcmd <pid> GC.class_histogram` (forces a full GC; instance counts and bytes are read from it, plus its `Total` line as the live-object bytes); then `jcmd <pid> GC.run`, 5 s, `jcmd <pid> GC.heap_info` (the `garbage-first heap ... used` value is "heap after GC"); then `nodetool info` heap line. Three samples per checkpoint, 30 s apart; medians are reported. The Guava entry class in the histogram is `com.google.common.cache.LocalCache$WeightedStrongValueReference`; the codec classes are `org.apache.cassandra.cql3.functions.types.VectorCodec$FixedLength`, `...TypeCodec$TupleCodec`, `...TupleType`.
- *S4-A8 (B3f/B3g, numeric reading rules fixed before any reading).* "≈ N" for an instance count = within ±10 % of N; "plateau at ≈1000" = Δ`WeightedStrongValueReference` in 900–1100 at both n2000 and n4000. Heap slopes: s0 = Δheap(n500)/500, s1 = (heap(n2000) − heap(n500))/1500, s2 = (heap(n4000) − heap(n2000))/2000. "Rises linearly, no knee" = s1 ≥ 0.5·s0 and s2 ≥ 0.5·s0, with each segment's rise larger than the ±2 MB noise of B3g. "Plateaus or flattens at N≈1000" (the refuting row) = s1 and s2 both < 0.25·s0, or both segment rises within ±2 MB. A slope between these bands matches no row and gives **not confirmed**. Noise = the spread of the three samples at a checkpoint, and at least ±2 MB. "About 8 MB more heap at M=2000" = heap(w2000drop) − heap(w1drop) ≥ +4 MB with the same post-drop `TupleCodec` count (±10 %); "the same bytes" (refuting) = within ±2 MB.
- *S4-A9 (B3e step 7, positive control re-run).* Optional as written; it is run only if time allows within the 3-hour cap, and the results file says whether it ran. The B3g positive control (the cap binding on its own operand, `WeightedStrongValueReference` plateauing, while the workload moves heap) is read in any case.

- *S4-A10 (B3d/B3f/B3g, the entry-count instrument; runbook defect S4-D2, found by the shakedown on a throwaway node before cluster run 1).* Guava 32.0.1 stores an entry of weight exactly 1 as `LocalCache$StrongValueReference` and only other weights as `LocalCache$WeightedStrongValueReference` (`LocalCache$Strength$1.referenceValue`: `weight == 1 ? new StrongValueReference : new WeightedStrongValueReference`, checked with `javap` on `guava-32.0.1-jre.jar`). Every `vector<int,i>` and `tuple<..., vector<int,i>>` entry of B3c weighs 1, so the class named in B3d sees none of them (the shakedown histogram had no such instance after 5 functions). The cache-entry count of B3d, B3f's column "ΔWeightedStrongValueReference" and B3g's rows that name it are read instead from `org.apache.cassandra.cql3.functions.types.CodecRegistry$CacheKey` instances in the post-full-GC histogram: one is retained per cache entry, and lookup keys of hits are garbage. `StrongValueReference` and `WeightedStrongValueReference` counts are recorded as cross-checks (Δ from `base`). The quantity, the predictions and the rows are unchanged; only the class that counts the entries changes.

**B4. Risks and cleanup.**
- **Disk:**
  - unit tier: the tree copy plus build, about 2–3 GB under `$WORK`;
  - cluster tier: about 1 GB data, commit log and hints (schema only), plus about 15 MB of schema for the wide phase;
  - optional heap dump: about 1 GB.
  All of it is on the local disk at `$WORK`, nothing is on shared storage, and the source tree `~/cassandra-5.0.9` and anything under `/proj` are left untouched.
- **Processes:** `kill $(cat $WORK/cassandra.pid)`, wait, then `pgrep -f CassandraDaemon` must print nothing. Ant test JVMs exit by themselves; check with `pgrep -f junit` → nothing.
- **Cleanup:** `rm -rf $WORK/data $WORK/commitlog $WORK/hints $WORK/saved_caches $WORK/cdc $WORK/*.hprof`. Delete `$WORK` entirely once readings are copied out.
- **Risk:** a heap of 1 GB with 4000 compiled UDFs could hit metaspace or heap pressure. If GC overhead appears, stop at N=2000; the 500 → 2000 comparison is enough to test for a knee.

## C. Sources read

- src/java/org/apache/cassandra/cql3/functions/types/CodecRegistry.java
- src/java/org/apache/cassandra/cql3/functions/types/TypeCodec.java (vector/tuple/UDT codec factories, AbstractTupleCodec, TupleCodec)
- src/java/org/apache/cassandra/cql3/functions/types/VectorCodec.java
- src/java/org/apache/cassandra/cql3/functions/types/TupleType.java
- src/java/org/apache/cassandra/cql3/functions/types/UserType.java
- src/java/org/apache/cassandra/cql3/functions/types/DataType.java
- src/java/org/apache/cassandra/cql3/functions/types/DataTypeClassNameParser.java
- src/java/org/apache/cassandra/utils/JavaDriverUtils.java
- src/java/org/apache/cassandra/cql3/functions/UDFDataType.java
- src/java/org/apache/cassandra/cql3/functions/UDFunction.java
- src/java/org/apache/cassandra/cql3/functions/UDAggregate.java
- src/java/org/apache/cassandra/cql3/functions/UDFContextImpl.java
- src/java/org/apache/cassandra/io/sstable/CQLSSTableWriter.java
- src/java/org/apache/cassandra/utils/ObjectSizes.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/db/marshal/VectorType.java
- src/java/org/apache/cassandra/cache/ChunkCache.java, CaffeineCache.java, SerializingCache.java; src/java/org/apache/cassandra/cql3/QueryProcessor.java; src/java/org/apache/cassandra/streaming/StreamManager.java (other weighted caches, via grep)
- conf/cassandra.yaml
- build.xml
- .build/parent-pom-template.xml
- test/unit/org/apache/cassandra/cql3/validation/operations/CQLVectorTest.java (only grepped for vector-typed UDFs)
- https://guava.dev/releases/32.0.1-jre/api/docs/com/google/common/cache/CacheBuilder.html#maximumWeight(long) (from memory of the docs; not fetched in this session)
- https://github.com/google/guava/blob/v32.0.1/guava/src/com/google/common/cache/LocalCache.java (from memory; not fetched in this session)
- https://github.com/datastax/java-driver/blob/3.x/driver-core/src/main/java/com/datastax/driver/core/CodecRegistry.java (origin of the copy; from memory, not fetched)

## D. Stage-4 feedback

**2026-11-25, stage 4 run 1, Jingsong, node `pc72` (x86_64):** results file `results/codec_cache_maximum_weight-defaultCacheBuilder-cache_weight--autonomous.md` (written outside the repo at `~/writeup-ext/out/o96/results.md`). Frozen version sha256 `5e1d073f0cfed803090eb67a3173420325f19576e9318a541f5e00817d2e3ee0` (after audit amendments B2i, B3i; this section added afterwards).
- **Unit: Confirmed — does not cap.** B2g rows 1–3. At weight sum 1000, `deepBytes` was 0.24 / 4.24 / 40.24 MB for M = 1 / 1000 / 10000 (166.6×; 242 + 4.0·M bytes per entry). 440 zero-weight entries stayed uncounted (1440 entries, weight 1000). `size` and `weight` followed the patched cap 100 / 1000 / 10000. All 3 repetitions identical.
- **Cluster: Confirmed — does not cap.** B3g row 2: live argument codecs = N (2000, 4000) against 1000 cache entries; exactly 1000 remain after `DROP`. The optional cap-100 re-run (B3e step 7) moved the entry plateau to 100, and the heap at N = 500 / 2000 / 4000 was unchanged within 0.06 MB. Row 3 partly met: same 1000 post-drop entries at M=1 and M=2000, `[Object;` +8.3 MiB, but heap after GC −9.2 MB because schema memtables flushed. Row 1 not met under the S4-A8 slope band (s1 = 0.45·s0).
- **Outcome class: true negative.**
- **Notes for stage 3 (not applied):**
  - (R-a) Guava 32.0.1 holds an entry of weight exactly 1 in `LocalCache$StrongValueReference`, not `WeightedStrongValueReference` (A3/B3d). Every B3c entry weighs 1, so the instrument named in B3d reads 0; stage 4 counted `CodecRegistry$CacheKey` instead (S4-D2).
  - (R-b) B2a/B3a assume `~/cassandra-5.0.9`.
  - (R-c) B3f's "Δheap back to within a few MB of base" after the drops does not hold on a node with `heap_buffers` memtables: the DDL's schema mutations add tens of MB that move with flushes. The whole-heap observable cannot resolve the cache's share, which is ≤ 0.2 MB narrow and ≈ 8 MB wide.
  - (R-d) The unit-test JVM splits `System.out` `printf` output into logger tokens (S4-D1).
