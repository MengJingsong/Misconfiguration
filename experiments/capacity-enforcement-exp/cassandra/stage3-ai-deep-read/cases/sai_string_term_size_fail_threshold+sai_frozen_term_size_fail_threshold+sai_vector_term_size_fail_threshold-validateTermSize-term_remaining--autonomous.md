# sai_string_term_size_fail_threshold / sai_frozen_term_size_fail_threshold / sai_vector_term_size_fail_threshold: verification solution  <!-- file: cases/sai_string_term_size_fail_threshold+sai_frozen_term_size_fail_threshold+sai_vector_term_size_fail_threshold-validateTermSize-term_remaining--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given lines (capacity set of three call sites of the same check), **linked**: [`SSTableIndexWriter.java:207`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java#L207), [`TrieMemoryIndex.java:220`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java#L220), [`VectorMemoryIndex.java:90`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java#L90) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-opus-5-5, Claude Code 2.1.330, 2026-11-24 (autonomous agent) |
| Estimate | `positive`, with one bypass. Each of the three lines drops a term whose byte size is above the SAI term-size fail threshold before it reaches the in-memory index (trie or vector graph), the compaction/build segment builder or the on-disk SAI components. So the SAI index's heap and disk follow the threshold term by term: a term above it adds 0 bytes, a term at or below it adds about its own size. Bypass: `VectorMemoryIndex.update` (an overwrite of a row already in the memtable) adds the vector to the graph without the check, so vector-index heap does not follow `sai_vector_term_size_fail_threshold` under overwrites until the next compaction or rebuild. The cap applies per term only. It does not bound the total index size, and it does not touch the base-table data (memtable/Data.db), which still stores the value. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- Name: the SAI term-size guardrail family. These are three `MaxThreshold` guardrails that share one check, `StorageAttachedIndex.validateTermSize`. Which one applies depends on the index's term type ([`StorageAttachedIndex.java:207-210`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java#L207-L210)):
  - vector columns use `sai_vector_term_size_*`,
  - frozen types (frozen collections/UDTs/tuples) use `sai_frozen_term_size_*`,
  - everything else (text, ascii, numeric, inet, the elements of non-frozen collections) uses `sai_string_term_size_*`.
- The value that matters at the given lines is the **fail** threshold. The warn threshold only logs, and only on the client path (A3).
- Kind: configuration entry (cassandra.yaml), read at run time through the guardrails config provider.
- First declared ([`Config.java:941-946`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L941-L946)):
  - [`Config.java:942`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L942) `sai_string_term_size_fail_threshold = new DataStorageSpec.LongBytesBound("8KiB")`
  - [`Config.java:944`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L944) `sai_frozen_term_size_fail_threshold = ... ("8KiB")`
  - [`Config.java:946`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L946) `sai_vector_term_size_fail_threshold = ... ("32KiB")`
  - The warn values are 1KiB / 1KiB / 16KiB (Config.java:941, 943, 945).
- Guardrail objects: `Guardrails.saiStringTermSize` / `saiFrozenTermSize` / `saiVectorTermSize`, `src/java/org/apache/cassandra/db/guardrails/Guardrails.java:520-551`. Each threshold provider is `sizeToBytes(getSai*TermSizeFailThreshold())`, where null becomes -1 (Guardrails.java:1442-1445).
- Unit: bytes, written as a DataStorageSpec string (`8KiB`, `16KiB`, `9000B`).
- Defaults are the hard-coded constants above. The shipped yaml has them commented out (`conf/cassandra.yaml:2245-2255`).
- How to set:
  1. **yaml** keys `sai_string_term_size_fail_threshold` (and `_warn_threshold`), `sai_frozen_term_size_*`, `sai_vector_term_size_*`. Needs a restart.
  2. **JMX at run time**, no restart: MBean `org.apache.cassandra.db:type=Guardrails`, operations `setSaiStringTermSizeThreshold(String warn, String fail)`, `setSaiFrozenTermSizeThreshold`, `setSaiVectorTermSizeThreshold` (Guardrails.java:1327 ff.). The fields are `volatile` and are re-read on every check, so a change takes effect on the next term.
  3. **nodetool** `setguardrailsconfig sai_string_term_size_threshold <fail> <warn>`. Note the order: fail first, then warn. The tool reverses the arguments for `*Threshold` setters (`tools/nodetool/GuardrailsConfigCommand.java:289-294`).
- Validation: warn ≤ fail, and sizes must be positive (GuardrailsOptions.java:980, 1207-1222). `null` disables the threshold (MaxThreshold.failValue maps ≤0 to `Long.MAX_VALUE`, `MaxThreshold.java:55-60`).

**A2. What it caps.**
- The quantity compared against the limit is `term.remaining()`, the byte length of one term as SAI encodes it. The comparison is strict: a term fails if `term.remaining() > fail` (`MaxThreshold.compare`, MaxThreshold.java:50-53).
- What the check governs is whether that term is admitted into the SAI structures:
  - **Heap (or memtable-allocator off-heap):** the memtable index. For non-vector types this is the `InMemoryTrie` in `TrieMemoryIndex`. Each term is stored as trie chain cells: 32-byte blocks holding up to 27 key bytes (`InMemoryReadTrie.java:127,147`), so roughly 1.2× the term length. For vectors it is the `OnHeapGraph`, which holds a `float[]` copy of the vector, postings and graph node (`OnHeapGraph.java:133-190`). These bytes are charged to the memtable's on-heap allocator (`StorageAttachedIndex.java:1004-1008`, `AbstractAllocatorMemtable.java:194-197`).
  - **Heap during compaction/index build:** the `SegmentBuilder` buffer, tracked by the global `SEGMENT_BUILD_MEMORY_LIMITER` (`sai_options.segment_write_buffer_size`, `V1OnDiskFormat.java:126-129`).
  - **Disk:** the per-column SAI components written from either of those structures (term dictionary, postings, vector graph files).
- The constraint is a **per-term** admission cap. It does not bound the number of terms or the total bytes of the index.

**A3. Mechanism.**
1. On a write, `UpdateIndexer.insertRow` calls `MemtableIndexManager.index`, then `MemtableIndex.index`, then `MemoryIndex.add` (StorageAttachedIndex.java:990-994; MemtableIndexManager.java:69-95; MemtableIndex.java:90-99).
   - **Trie path** ([`TrieMemoryIndex.java:220`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java#L220)): `add` converts the value with `asIndexBytes` and runs it through the analyzer, if there is one. It calls `addTerm` once per term or token (TrieMemoryIndex.java:94-125). `addTerm` checks `if (index.validateTermSize(primaryKey.partitionKey(), term, false, null))`:
     - true: the term goes into `data` (`putRecursive`/`apply`, lines 227-234), and the trie's on-heap and off-heap growth is returned as the bytes used;
     - false: nothing is added and the delta is 0.
   - **Vector path** ([`VectorMemoryIndex.java:90`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java#L90)): `if (value == null || value.remaining() == 0 || !index.validateTermSize(key, value, false, null)) return 0;`. Otherwise the vector is added through `graph.add(...)` (lines 93-104).
2. On compaction, index build or `rebuild_index`, `V1OnDiskFormat.newPerColumnIndexWriter` chooses `SSTableIndexWriter` whenever the operation is not a memtable FLUSH (V1OnDiskFormat.java:174-180). `SSTableIndexWriter.addRow` calls `addTerm` for each value (lines 77-101).
   - [`SSTableIndexWriter.java:207`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java#L207): `if (!index.validateTermSize(key.partitionKey(), term, false, null)) return;`. On failure the term never reaches `currentBuilder.add` (lines 223-236), so it adds nothing to the segment builder's heap (`limiter.increment`) or to the segment files.
   - A memtable FLUSH instead uses `MemtableIndexWriter`, which serialises what the memtable index already holds (V1OnDiskFormat.java:183-188; MemtableIndexWriter.java:141, 212). The flush path has no check of its own and relies on step 1.
3. Inside `validateTermSize` (StorageAttachedIndex.java:815-834), with `isClientMutation=false` and `state=null`:
   - `maxTermSizeGuardrail.failsOn(term.remaining(), null)` holds when `Guardrail.enabled(null)` is true and `term.remaining() > fail`. `enabled(null)` requires `DatabaseDescriptor.isDaemonInitialized()` (Guardrail.java:93-96) and at least one of warn/fail > 0 (Threshold.java:80-86).
   - When it fails, `noSpamLogger.warn(TERM_OVERSIZE_MESSAGE)` logs "Term in column '%s' for key '%s' is too large and cannot be indexed. (term size: %s)" at most once per minute (StorageAttachedIndex.java:145-147), and the method returns `false`.
   - Outcome at the limit: the row is still written to the base table. Only the index skips the term, so queries on that value do not find the row.
4. **Client path (outside the given lines).** `StorageAttachedIndex.validate(PartitionUpdate, ClientState)` checks the term size at the coordinator (StorageAttachedIndex.java:520-530, 773-807, 817-821). It calls `guard(...)`, which throws `GuardrailViolatedException` and rejects the write. This applies only to ordinary users: superusers, internal calls, and every client under `AllowAllAuthenticator` (`ClientState.isSuper()` is true when the authenticator does not require authentication, ClientState.java:602-605) are exempt. So on a default node an oversized value is accepted and reaches the given lines.
5. **Bypasses and overshoots:**
   - **Vector overwrite bypass.** When a row that is already in the memtable is written again, `SecondaryIndexManager.WriteTimeTransaction.onUpdated` calls `Indexer.updateRow` (SecondaryIndexManager.java:1552-1590). That goes through `MemtableIndexManager.update` to `VectorMemoryIndex.update` (MemtableIndexManager.java:98-111). `update` calls `graph.add(newValue, ...)` with **no** `validateTermSize` (VectorMemoryIndex.java:107-142). All values of a vector column have the same byte size, so if the first insert was refused as oversized, every later overwrite is just as oversized and is indexed anyway. A memtable flush then writes it to disk (no check on the flush path). The next compaction or rebuild drops it again at line 207. Non-vector `update` goes back through `index` → `add` and is checked (MemtableIndexManager.java:100-103).
   - **Analyzer mismatch.** The memtable path checks each analyzer token (TrieMemoryIndex.java:104-112), but `SSTableIndexWriter` checks the whole cell value *before* analysis (line 207, then the analyzer at lines 227-240). An analyzed cell longer than the threshold, made of short tokens, is indexed in the memtable but dropped entirely at compaction. That is an index-correctness inconsistency, not a memory overshoot.
   - **Warn pre-filter on the client path.** `validateTermSizeForCell` returns early unless `warnsOn(cell)` (StorageAttachedIndex.java:795-796). With warn set to null and fail set, coordinator rejection never fires. The given lines are not affected.
   - **Daemon not initialized** (offline tools such as sstable-based index builds in a non-daemon JVM): `enabled()` is false and nothing is refused.
   - **Granularity overshoot:** per term the cap is exact. In total the index can still hold up to (number of terms) × threshold, which only memtable sizing (`memtable_heap_space`, cleanup threshold) and `sai_options.segment_write_buffer_size` bound.

**A4. Other consumers.** Outside this constraint's control:
- the base-table memtable and Data.db, which still hold the oversized value (and `max_value_size` / commit-log mutation size are separate limits);
- the per-row primary-key structures of indexed terms;
- `InMemoryTrie`'s buffer growth (allocated capacity rather than bytes used);
- the SAI segment builder limiter (`segment_write_buffer_size`, default 1024MiB, StorageAttachedIndexOptions.java:35);
- chunk cache / index file cache;
- `vector_dimensions_*` guardrails (Guardrails.java:419), which bound vector size at schema time and are disabled by default (Config.java:924-925).

**A5. Evidence beyond the source.**
- `CHANGES.txt:374`: "SAI in-memory index should check max term size (CASSANDRA-18926)", the origin of the memtable checks at TrieMemoryIndex:220 / VectorMemoryIndex:90 (https://issues.apache.org/jira/browse/CASSANDRA-18926).
- Tests: `test/unit/org/apache/cassandra/db/guardrails/GuardrailSaiStringTermSizeTest.java`. `testFailingTermOnBuild` (lines 200-215) shows an oversized term is not indexed on the initial build (the line-207 path). `GuardrailSaiFrozenTermSizeTest`, `GuardrailSaiVectorTermSizeTest` are the frozen and vector counterparts.
- `conf/cassandra.yaml:2245-2255` comments.

## B. Verification solution

**B1. Claim under test.**
(a) For string/frozen and vector SAI indexes, a term whose encoded size is above the matching `sai_*_term_size_fail_threshold` adds 0 bytes to the SAI memtable index and 0 bytes to the SAI on-disk components, on flush and on compaction/rebuild. A term at or below the threshold adds at least its own size. So SAI heap and disk follow the knob, while base-table usage does not.
(b) Exception predicted from the source: for a vector index, overwriting rows already in the memtable indexes oversized vectors anyway. Heap then does **not** follow `sai_vector_term_size_fail_threshold` until a compaction or rebuild.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11 (`java -version` shows 11), Ant ≥ 1.10.
- Copy the tree to local disk: `rsync -a ~/cassandra-5.0.9/ /mydata/$USER/c509-unit/` (any local, non-shared disk with ≥ 10 GB free). Work only there.
- Build: `cd /mydata/$USER/c509-unit && ant realclean && ant jar && ant build-test`.
- Test source: `test/unit/org/apache/cassandra/index/sai/TermSizeCapProbeTest.java` (below).
- It extends `SAITester`. That extends `CQLTester`, which calls `ServerTestUtils.daemonInitialization()` (CQLTester.java:411-414), so `isDaemonInitialized()` is true and the guardrails are active with a null state. Test config: `test/conf/cassandra.yaml` (`memtable_allocation_type: heap_buffers`).
- JVM options: the `testsome` defaults.

```java
package org.apache.cassandra.index.sai;

import java.nio.ByteBuffer;
import java.util.Collections;
import java.util.Random;

import org.junit.Test;

import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.db.guardrails.Guardrails;
import org.apache.cassandra.utils.ByteBufferUtil;

public class TermSizeCapProbeTest extends SAITester
{
    static final int N = 500;                   // string rows
    static final int S = 12288;                 // 12 KiB string term
    static final int M = 200;                   // vector rows
    static final int D = 4096;                  // 4096 floats = 16384 B vector term
    final Random r = new Random(42);

    String ascii(int len) { char[] c = new char[len]; for (int i = 0; i < len; i++) c[i] = (char) ('a' + r.nextInt(26)); return new String(c); }
    float[] vec() { float[] v = new float[D]; for (int i = 0; i < D; i++) v[i] = 0.01f + r.nextFloat(); return v; }
    StorageAttachedIndex sai(String idx) { return (StorageAttachedIndex) getCurrentColumnFamilyStore().indexManager.getIndexByName(idx); }
    void out(String fmt, Object... a) { System.out.printf("PROBE " + fmt + "%n", a); }

    // Boundary of the check itself (operand term.remaining() vs fail threshold)
    @Test
    public void boundary() throws Throwable
    {
        Guardrails.instance.setSaiStringTermSizeThreshold("1KiB", "8KiB");
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v text)");
        String idx = createIndex("CREATE INDEX ON %s(v) USING 'sai'");
        DecoratedKey key = getCurrentColumnFamilyStore().decorateKey(ByteBufferUtil.bytes(0));
        for (int len : new int[]{ 8191, 8192, 8193 })
            out("arm=boundary fail=8KiB len=%d admitted=%b", len, sai(idx).validateTermSize(key, ByteBuffer.allocate(len), false, null));
    }

    // String arm: memtable trie (TrieMemoryIndex:220), flush, and rebuild (SSTableIndexWriter:207)
    void stringArm(String fail, String flipTo, int termBytes) throws Throwable
    {
        Guardrails.instance.setSaiStringTermSizeThreshold("1KiB", fail);
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v text)");
        String idx = createIndex("CREATE INDEX ON %s(v) USING 'sai'");
        String probe = null;
        for (int k = 0; k < N; k++) { String v = ascii(termBytes); if (k == 0) probe = v; execute("INSERT INTO %s (k, v) VALUES (?, ?)", k, v); }
        long mem = sai(idx).memtableIndexManager().estimatedMemIndexMemoryUsed();
        int hitsMem = execute("SELECT k FROM %s WHERE v = ?", probe).size();
        flush();
        long disk = sai(idx).diskUsage();
        int hitsDisk = execute("SELECT k FROM %s WHERE v = ?", probe).size();
        Guardrails.instance.setSaiStringTermSizeThreshold("1KiB", flipTo);
        getCurrentColumnFamilyStore().indexManager.rebuildIndexesBlocking(Collections.singleton(idx));
        long diskRebuilt = sai(idx).diskUsage();
        int hitsRebuilt = execute("SELECT k FROM %s WHERE v = ?", probe).size();
        long dataBytes = getCurrentColumnFamilyStore().metric.liveDiskSpaceUsed.getCount();
        out("arm=string fail=%s S=%d N=%d memIndexBytes=%d hitsMem=%d diskFlush=%d hitsFlush=%d flipTo=%s diskRebuilt=%d hitsRebuilt=%d liveDiskSpaceUsed=%d",
            fail, termBytes, N, mem, hitsMem, disk, hitsDisk, flipTo, diskRebuilt, hitsRebuilt, dataBytes);
    }

    @Test public void stringBelowKnob() throws Throwable { stringArm("8KiB", "16KiB", S); }   // refused, then admitted on rebuild
    @Test public void stringAboveKnob() throws Throwable { stringArm("16KiB", "8KiB", S); }   // admitted, then dropped on rebuild
    @Test public void stringControlSmall() throws Throwable { stringArm("8KiB", "8KiB", 1024); } // positive control

    // Vector arm: VectorMemoryIndex:90 and the update() bypass
    void vectorArm(String fail, boolean overwrite) throws Throwable
    {
        Guardrails.instance.setSaiVectorTermSizeThreshold("1KiB", fail);
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v vector<float, " + D + ">)");
        String idx = createIndex("CREATE INDEX ON %s(v) USING 'sai'");
        for (int k = 0; k < M; k++) execute("INSERT INTO %s (k, v) VALUES (?, ?)", k, vector(vec()));
        long memInsert = sai(idx).memtableIndexManager().estimatedMemIndexMemoryUsed();
        if (overwrite)
            for (int k = 0; k < M; k++) execute("INSERT INTO %s (k, v) VALUES (?, ?)", k, vector(vec()));
        long memAfter = sai(idx).memtableIndexManager().estimatedMemIndexMemoryUsed();
        int ann = execute("SELECT k FROM %s ORDER BY v ANN OF ? LIMIT 5", vector(vec())).size();
        flush();
        long disk = sai(idx).diskUsage();
        getCurrentColumnFamilyStore().indexManager.rebuildIndexesBlocking(Collections.singleton(idx));
        long diskRebuilt = sai(idx).diskUsage();
        out("arm=vector fail=%s overwrite=%b M=%d bytesPerVec=%d memInsert=%d memAfter=%d annRows=%d diskFlush=%d diskRebuilt=%d",
            fail, overwrite, M, D * 4, memInsert, memAfter, ann, disk, diskRebuilt);
    }

    @Test public void vectorRefused() throws Throwable { vectorArm("8KiB", false); }
    @Test public void vectorAdmitted() throws Throwable { vectorArm("32KiB", false); }
    @Test public void vectorOverwriteBypass() throws Throwable { vectorArm("8KiB", true); }
}
```

(Optional frozen arm: the same as `stringArm`, with `v frozen<list<text>>`, `CREATE INDEX ON %s(FULL(v)) USING 'sai'`, three 4 KiB elements per row (value ≈ 12.3 KB), and `setSaiFrozenTermSizeThreshold`. The predictions mirror the string arm.)

**B2b. Knobs.**
- `sai_string_term_size_fail_threshold` ∈ {8KiB (default), 16KiB}. A 12 KiB term sits between them, so the knob alone decides admission.
- `sai_vector_term_size_fail_threshold` ∈ {8KiB, 32KiB (default)}. A 16 KiB vector sits between them.
- The boundary test uses 8KiB with lengths 8191/8192/8193 to show the strict `>`.
- Warn is set to 1KiB throughout so warn ≤ fail holds.
- Everything is set through `Guardrails.instance.setSai*TermSizeThreshold(warn, fail)`, the same setters the JMX MBean exposes.

**B2c. Workload.**
- String: N=500 rows of distinct random lowercase ASCII, S=12,288 B each (UTF8 byte-comparable encoding ≈ S+1 bytes). N·S = 6,144,000 B ≈ 5.86 MiB. Random terms share almost no prefix, so the trie stores close to their full length.
- Control: the same with S=1,024 B (N·S = 512,000 B), always below the threshold.
- Vector: M=200 rows × 4096 floats = 16,384 B per term. M·16 KiB = 3,276,800 B.
- Overwrite variant: 200 more inserts to the same keys with different vectors, before any flush, so they hit `updateRow`.
- All writes go through `execute` (an internal ClientState), so the coordinator guard is skipped as on a default node and only the given lines decide.

**B2d. Observables and instruments.**
- `validateTermSize` return value (boundary).
- `MemtableIndexManager.estimatedMemIndexMemoryUsed()`: the sum of the trie/graph byte deltas returned by `add`/`update`. This is the same number as the `MemtableIndexBytes` gauge, IndexMetrics.java:58.
- `StorageAttachedIndex.diskUsage()`: the per-column SAI component bytes, after flush and after rebuild.
- Query hits for the probe term (index-only read path) and ANN row count.
- `liveDiskSpaceUsed`: base-table data, to show it is unaffected.
- All lines are printed with prefix `PROBE` into `build/test/output/TEST-org.apache.cassandra.index.sai.TermSizeCapProbeTest.xml` (`<system-out>`). The log line "too large and cannot be indexed" goes to `build/test/logs/`.
- Not directly observable: real heap bytes of the trie buffers (the estimate counts allocated buffer growth, not live bytes). The cluster tier covers that.

**B2e. Procedure.**
1. `cd /mydata/$USER/c509-unit` and write the test file above.
2. `ant testsome -Dtest.name=org.apache.cassandra.index.sai.TermSizeCapProbeTest 2>&1 | tee /mydata/$USER/unit-run.log`
3. `grep -h 'PROBE' build/test/output/TEST-org.apache.cassandra.index.sai.TermSizeCapProbeTest*.xml`
4. `grep -h 'too large and cannot be indexed' build/test/logs/*/*.log | head` (if the logs are elsewhere, use `find build/test/logs -name '*.log' | xargs grep -l 'too large'`).
5. Repeat step 2 three times and check the readings agree.

**B2f. Predictions** (stated before any run):

| Test | Prediction |
|---|---|
| boundary | 8191 → true, 8192 → true, 8193 → false |
| stringBelowKnob (fail 8KiB, S=12 KiB) | memIndexBytes = 0; hitsMem = 0; diskFlush ≤ 64 KiB; hitsFlush = 0. After flip to 16KiB + rebuild (SSTableIndexWriter path): diskRebuilt ≥ 0.9·N·S ≈ 5.5 MB; hitsRebuilt = 1 |
| stringAboveKnob (fail 16KiB) | 6.1 MB ≤ memIndexBytes ≤ 18.4 MB (1×–3× N·S); hitsMem = 1; diskFlush ≥ 5.5 MB; hitsFlush = 1. After flip to 8KiB + rebuild: diskRebuilt ≤ 64 KiB; hitsRebuilt = 0 |
| stringControlSmall | memIndexBytes ≥ 512,000; hits 1 at every stage; diskFlush, diskRebuilt ≥ 0.9·512,000 |
| liveDiskSpaceUsed | within ±10 % between stringBelowKnob and stringAboveKnob (base data does not follow the knob) |
| vectorRefused (fail 8KiB) | memInsert = memAfter = 0; annRows = 0; diskFlush ≤ 64 KiB |
| vectorAdmitted (fail 32KiB) | memInsert ≥ 3.27 MB; annRows = 5; diskFlush ≥ 3.0 MB |
| vectorOverwriteBypass (fail 8KiB) | memInsert = 0, then **memAfter ≥ 3.27 MB**; annRows = 5; diskFlush ≥ 3.0 MB; diskRebuilt ≤ 64 KiB (line 207 drops them again) |

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Predictions above hold | Claim (a) and bypass (b) confirmed at unit level |
| stringBelowKnob memIndexBytes ≥ N·S or hitsMem = 1 | TrieMemoryIndex:220 does not refuse; claim (a) **wrong** for the memtable path |
| stringAboveKnob diskRebuilt ≥ 0.9·N·S after flip to 8KiB | SSTableIndexWriter:207 does not refuse; claim (a) **wrong** for the compaction/build path |
| vectorRefused memInsert > 0 | VectorMemoryIndex:90 does not refuse; claim (a) **wrong** for vectors |
| vectorOverwriteBypass memAfter = 0 and annRows = 0 | Bypass (b) refuted: overwrites are also checked |
| Boundary 8192 → false | The comparison is `≥`, not `>`; adjust the boundary claim |
| Control memIndexBytes = 0 | Index not being fed, or guardrail broken in general; run not valid |
| All refused cases also show 0 in the admitted cases | Workload never reached the index; not confirmed |

**B2h. Controls.**
- The small-term control and the admitted runs show that the same workload moves the measured numbers. The `liveDiskSpaceUsed` comparison shows the base table is written in every run, so a 0 reading comes from the index skipping the term and not from the write being lost.
- The flip-and-rebuild step isolates line 207 from the memtable path: the same SSTable is re-indexed under a different threshold.
- The fixed seed (42) makes term content identical across runs.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node with JDK 11 and ≥ 20 GB free local disk. A single node is enough; the paths are per-replica.
- Copy and build:
  - `rsync -a ~/cassandra-5.0.9/ /mydata/$USER/c509/`
  - `cd /mydata/$USER/c509 && ant realclean && ant jar`
- Run directory `R=/mydata/$USER/s4run`, on local disk.
- Configuration changes in `conf/cassandra.yaml`:
  - `data_file_directories: [$R/data]`, `commitlog_directory: $R/commitlog`, `saved_caches_directory: $R/saved_caches`, `hints_directory: $R/hints`, `cdc_raw_directory: $R/cdc`
  - `memtable_heap_space: 512MiB` (flush at ≈ 0.33 × 512 MiB ≈ 170 MiB)
  - `sai_string_term_size_warn_threshold: 1KiB`, `sai_vector_term_size_warn_threshold: 1KiB`
  - the fail thresholds per run (B3b)
  - leave `authenticator: AllowAllAuthenticator`, so the coordinator guard is inert (A3 step 4) and oversized values reach the given lines
- `conf/cassandra-env.sh`: `MAX_HEAP_SIZE=2G`, `HEAP_NEWSIZE=400M`.
- `conf/jvm-server.options`: no changes. JMX stays local-only on 7199.
- Start: `bin/cassandra -p $R/cassandra.pid > $R/stdout.log 2>&1`. Wait until `bin/nodetool status` shows `UN`.

**B3b. Knobs.**

| Run | Knob values | Purpose |
|---|---|---|
| C1 | `sai_string_term_size_fail_threshold: 8KiB` (default) | 12 KiB terms refused |
| C2 | same key, `16KiB` | 12 KiB terms admitted |
| C3 | after C2's load+flush, lower to 8KiB at run time: `bin/nodetool setguardrailsconfig sai_string_term_size_threshold 8KiB 1KiB`, then `rebuild_index` | line 207 |
| C4 | after C1's load+flush, raise to 16KiB at run time, then `rebuild_index` | line 207, opposite direction |
| C5 | `sai_vector_term_size_fail_threshold: 8KiB`, vector table, insert then overwrite | VectorMemoryIndex:90 and the update bypass |
| C6 | same, `32KiB` | vector positive control |

- For each run, check the value with `bin/nodetool getguardrailsconfig | grep -i term_size`.
- C1/C2/C5/C6 set yaml and start a fresh node (wipe `$R`). C3/C4 change at run time only.

**B3c. Workload.**
- Schema (cqlsh):
  - `CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy','replication_factor':1};`
  - `CREATE TABLE ks.t_big (k int PRIMARY KEY, v text);` with `CREATE INDEX idx_big ON ks.t_big(v) USING 'sai';`
  - `CREATE TABLE ks.t_small (k int PRIMARY KEY, v text);` with `CREATE INDEX idx_small ON ks.t_small(v) USING 'sai';`
  - `CREATE TABLE ks.t_vec (k int PRIMARY KEY, v vector<float, 2304>);` with `CREATE INDEX idx_vec ON ks.t_vec(v) USING 'sai';`
- Data generation, in a directory of its own (`$R/gen`):

```bash
mkdir -p $R/gen && cd $R/gen
python3 -I - <<'EOF'
import random, csv
r = random.Random(42)
def s(n): return ''.join(chr(97 + r.randrange(26)) for _ in range(n))
with open('big.csv','w',newline='') as f:
    w = csv.writer(f)
    for k in range(2000):
        v = s(12288); w.writerow([k, v])
        if k == 0: open('probe.txt','w').write(v)
with open('small.csv','w',newline='') as f:
    w = csv.writer(f)
    for k in range(2000): w.writerow([k, s(1024)])
for p in (1, 2):
    with open(f'vec{p}.cql','w') as f:
        for k in range(500):
            v = ','.join('%.4f' % (0.01 + r.random()) for _ in range(2304))
            f.write(f'INSERT INTO ks.t_vec (k, v) VALUES ({k}, [{v}]);\n')
EOF
```

- Load:
  - `bin/cqlsh -e "COPY ks.t_big (k,v) FROM '$R/gen/big.csv' WITH MAXBATCHSIZE=5 AND CHUNKSIZE=50"`
  - the same for `t_small` with `small.csv`
  - vector runs: `bin/cqlsh -f $R/gen/vec1.cql`, then (overwrite) `bin/cqlsh -f $R/gen/vec2.cql`
- Arithmetic:
  - t_big: 2000 × 12,288 B = 24,576,000 B ≈ 23.4 MiB of terms.
  - t_small: 2,048,000 B.
  - Vectors: 2304 × 4 = 9,216 B per term, which is > 8 KiB and < 32 KiB. 500 × 9,216 = 4,608,000 B.
  - Base data plus index in memory ≤ ~100 MB, below the ≈170 MiB flush trigger, so no flush happens until `nodetool flush`.
- Duration: loading takes a few minutes per table. Each run takes about 15 minutes.

**B3d. Observables and instruments.**
- SAI memtable-index bytes, per index, read before flush:
  `bin/nodetool sjk mx -b "org.apache.cassandra.metrics:type=StorageAttachedIndex,keyspace=ks,table=t_big,index=idx_big,scope=IndexMetrics,name=MemtableIndexBytes" -mg -f Value`. Do the same for idx_small and idx_vec.
- Actual heap: after `jcmd $(cat $R/cassandra.pid) GC.run`, run `jmap -histo:live $(cat $R/cassandra.pid) | awk '$4=="[B"{print $3}'`. That gives the total bytes of `byte[]`; the trie buffers are heap ByteBuffers. Also read `MemtableOnHeapDataSize` for t_big with `bin/nodetool sjk mx -b "org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t_big,name=MemtableOnHeapDataSize" -mg -f Value`; it includes the SAI bytes charged via `markExtraOnHeapUsed`.
- SAI disk, after `bin/nodetool flush ks`:
  - `bin/cqlsh -e "SELECT index_name, sstable_name, per_column_disk_size FROM system_views.sai_sstable_indexes WHERE keyspace_name='ks'"`
  - `du -cb $R/data/ks/t_big-*/*idx_big* | tail -1`
- Base data: `du -cb $R/data/ks/t_big-*/*Data.db | tail -1`.
- Index visibility:
  - `bin/cqlsh -e "SELECT k FROM ks.t_big WHERE v = '$(cat $R/gen/probe.txt)'"` (expect 0 or 1 row)
  - vectors: `SELECT k FROM ks.t_vec ORDER BY v ANN OF [<2304 floats from vec1.cql line 1>] LIMIT 5`
- Refusal log: `grep -c 'too large and cannot be indexed' $R/../c509/logs/system.log` (logs go to `/mydata/$USER/c509/logs`; at most one line per minute because of NoSpamLogger).
- Sampling: one reading per stage (after load, after flush, after rebuild). Three runs per configuration; report the median.
- Not observable directly: how heap splits between trie cells and buffer slack. The histogram gives the total only.

**B3e. Procedure.**
1. Build (B3a). For C1: set `sai_string_term_size_fail_threshold: 8KiB`, `rm -rf $R/{data,commitlog,saved_caches,hints,cdc}`, start the node, create the schema, generate data (once).
2. Load t_small, then t_big. Read `MemtableIndexBytes` (idx_big, idx_small), `MemtableOnHeapDataSize` (t_big), the `jmap -histo:live` `[B` total, the probe query result, and the log count.
3. `bin/nodetool flush ks`. Read `per_column_disk_size` / `du` for idx_big and idx_small, and the Data.db size. Re-run the probe query.
4. (C4) `bin/nodetool setguardrailsconfig sai_string_term_size_threshold 16KiB 1KiB`; confirm with `getguardrailsconfig`; run `bin/nodetool rebuild_index ks t_big idx_big`; wait for `nodetool compactionstats` to be empty. Read idx_big disk and run the probe query.
5. `bin/nodetool stopdaemon`; confirm `pgrep -f CassandraDaemon` is empty; wipe `$R/{data,commitlog,saved_caches,hints,cdc}`.
6. C2 (+C3): set `16KiB` in yaml and repeat steps 1-3. Then `setguardrailsconfig sai_string_term_size_threshold 8KiB 1KiB`, `rebuild_index ks t_big idx_big`, and read again. Stop and wipe.
7. C5: `sai_vector_term_size_fail_threshold: 8KiB`, fresh node, schema. Run `cqlsh -f vec1.cql` and read `MemtableIndexBytes` (idx_vec) and ANN rows. Run `cqlsh -f vec2.cql` (overwrite, no flush in between) and read them again. Then `nodetool flush ks`, read idx_vec disk, run `rebuild_index ks t_vec idx_vec`, and read the disk again. Stop and wipe.
8. C6: as C5 with `32KiB`, vec1 only (and optionally vec2).
9. Repeat C1, C2, C5 twice more.

**B3f. Predictions** (stated before any run; N·S = 24.58 MB):

| Run / stage | Prediction |
|---|---|
| C1 load | idx_big `MemtableIndexBytes` = 0; idx_small ≥ 2.0 MB; probe query 0 rows; log count ≥ 1 |
| C2 load | idx_big `MemtableIndexBytes` between 24.6 MB and 73.7 MB; probe 1 row |
| C2 − C1, heap | `[B` live total ≥ +20 MB; t_big `MemtableOnHeapDataSize` ≥ +24 MB |
| C1 flush | idx_big per-column disk ≤ 64 KiB |
| C2 flush | idx_big per-column disk ≥ 22 MB |
| Data.db, C1 vs C2 | within ±5 % (base table does not follow the knob) |
| C3 (C2 data, lowered to 8KiB, rebuild) | idx_big disk ≤ 64 KiB; probe 0 rows; Data.db unchanged |
| C4 (C1 data, raised to 16KiB, rebuild) | idx_big disk ≥ 22 MB; probe 1 row |
| C5 after vec1 | idx_vec `MemtableIndexBytes` = 0; ANN 0 rows |
| C5 after vec2 overwrite | `MemtableIndexBytes` ≥ 4.6 MB (bypass); ANN 5 rows. After flush, disk ≥ 4.0 MB; after `rebuild_index`, ≤ 64 KiB |
| C6 after vec1 | `MemtableIndexBytes` ≥ 4.6 MB; ANN 5 rows |

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| C1 ≈ 0 and C2 ≥ N·S for memtable bytes, heap and disk | Claim (a) confirmed with the actual resource |
| C1 idx_big `MemtableIndexBytes` ≥ N·S, or `[B` delta C2−C1 < 5 MB | Memtable usage does **not** follow the knob; claim (a) wrong |
| C3 disk stays ≥ 22 MB after rebuild under 8KiB | Line 207 does not cap disk; claim (a) wrong for compaction/build |
| C5 after overwrite stays 0 and ANN 0 rows | Bypass (b) refuted |
| C5 after vec1 > 0 | VectorMemoryIndex:90 not effective; claim (a) wrong for vectors |
| idx_small = 0 or C2 also 0 | Workload did not reach the index; not confirmed |
| Data.db differs > 20 % between C1 and C2 | Something other than the index changed (for example coordinator rejection is active); check the authenticator and rerun |

**B3h. Controls.**
- t_small (always admitted) gives a positive-control series in every run.
- C2 and C6 are the "cap not binding" positive controls for the same workload.
- Data.db comparison and the probe query: the write is accepted in every run, so a 0 comes from the index refusing the term.
- C3/C4 change only the knob on the same on-disk data, which isolates line 207 from the memtable path.
- A fresh data directory per yaml run, the same generated files for every run (seed 42), and a heap histogram after a forced GC.

**B4. Risks and cleanup.**
- Disk: ≤ 1 GB per run under `/mydata/$USER/s4run` (local); the unit tier writes under `build/test` in the local copy. Never use the shared source tree or shared storage.
- The fixed 2 GB heap stays within the node.
- After each cluster run: `bin/nodetool stopdaemon`, then `pgrep -f CassandraDaemon` (must be empty; otherwise `kill $(cat $R/cassandra.pid)`).
- After the unit tier: `pgrep -f 'ant|junit'` must be empty.
- Cleanup: `rm -rf /mydata/$USER/s4run /mydata/$USER/c509 /mydata/$USER/c509-unit` once the results are copied.
- The 24 MB CSV and the vector scripts stay under `$R/gen` and are removed with it.

## C. Sources read

- src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java
- src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java
- src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java
- src/java/org/apache/cassandra/index/sai/memory/MemtableIndex.java
- src/java/org/apache/cassandra/index/sai/memory/MemtableIndexManager.java
- src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java
- src/java/org/apache/cassandra/index/sai/disk/v1/V1OnDiskFormat.java
- src/java/org/apache/cassandra/index/sai/disk/v1/MemtableIndexWriter.java (grep)
- src/java/org/apache/cassandra/index/sai/disk/v1/vector/OnHeapGraph.java
- src/java/org/apache/cassandra/index/sai/metrics/IndexMetrics.java, AbstractMetrics.java
- src/java/org/apache/cassandra/index/sai/virtual/SSTableIndexesSystemView.java (grep)
- src/java/org/apache/cassandra/index/sai/utils/IndexTermType.java (grep)
- src/java/org/apache/cassandra/index/SecondaryIndexManager.java
- src/java/org/apache/cassandra/db/guardrails/Guardrails.java, Guardrail.java, Threshold.java, MaxThreshold.java, GuardrailsConfig.java
- src/java/org/apache/cassandra/config/Config.java, GuardrailsOptions.java, StorageAttachedIndexOptions.java, DatabaseDescriptor.java (grep)
- src/java/org/apache/cassandra/service/ClientState.java, src/java/org/apache/cassandra/auth/AuthenticatedUser.java
- src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java
- src/java/org/apache/cassandra/db/tries/InMemoryReadTrie.java, InMemoryTrie.java (constants)
- src/java/org/apache/cassandra/db/marshal/VectorType.java, src/java/org/apache/cassandra/cql3/CQL3Type.java (grep)
- src/java/org/apache/cassandra/metrics/TableMetrics.java (grep)
- src/java/org/apache/cassandra/tools/nodetool/GuardrailsConfigCommand.java, RebuildIndex.java, Sjk.java (grep)
- conf/cassandra.yaml, conf/cassandra-env.sh
- test/unit/org/apache/cassandra/db/guardrails/GuardrailSaiStringTermSizeTest.java, GuardrailTester.java (grep)
- test/unit/org/apache/cassandra/cql3/CQLTester.java, test/unit/org/apache/cassandra/index/sai/SAITester.java (grep)
- test/conf/cassandra.yaml, build.xml (testsome target), .build/cassandra-deps-template.xml (sjk)
- CHANGES.txt
- https://issues.apache.org/jira/browse/CASSANDRA-18926 (cited from CHANGES.txt, not fetched)

## D. Stage-4 feedback

none yet
