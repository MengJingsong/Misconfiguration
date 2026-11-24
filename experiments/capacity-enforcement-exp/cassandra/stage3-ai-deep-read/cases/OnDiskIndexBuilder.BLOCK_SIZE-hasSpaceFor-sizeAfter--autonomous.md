# OnDiskIndexBuilder.BLOCK_SIZE — verification solution  <!-- file: cases/OnDiskIndexBuilder.BLOCK_SIZE-hasSpaceFor-sizeAfter--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`OnDiskIndexBuilder.java:545`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java#L545) — `return sizeAfter(element) < BLOCK_SIZE;` in `MutableBlock.hasSpaceFor` (a capacity-set place: the given line is the check) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-opus-5-5, Claude Code 2.1.330, 2026-11-24 |
| Estimate | `negative`. The check caps only how many terms go into one fixed, pre-allocated 4 KiB staging buffer (one per index level) before it is written out. Builder heap and SASI index file size grow linearly with the number of terms, and `BLOCK_SIZE` sets only the block size and padding. |
| Ground | The bounded object is not significant for memory or disk. `DataOutputBufferFixed(BLOCK_SIZE)` allocates 4096 bytes up front whether or not the check holds (`OnDiskIndexBuilder.java:528`). At most `levels + 1` of these buffers are live, and `levels` grows as about log N, so the total is tens of KiB. The check only stops a `BufferOverflowException` and keeps the on-disk block format readable (`OnDiskBlock.java:53`). Builder heap is governed by a different limit, `PerSSTableIndexWriter.java:247` (1 GiB on memtable flush, or `max_compaction_flush_memory_in_mb` on compaction). Index file size has no limit at all: it is about one data block per k terms plus token trees outside the 4 KiB term block. |

## A. Constraint trace

**A1. The constraint.** `OnDiskIndexBuilder.BLOCK_SIZE` is a compile-time constant (`public static final int`), declared at
[`OnDiskIndexBuilder.java:127`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java#L127)
as `BLOCK_SIZE = 4096`.
- **Unit:** bytes.
- **Default:** the literal 4096, a page-size block. `doc/SASI.md:425-427` calls the blocks "page-size blocks".
- **How it can be set:** not settable. There is no yaml key, `-D` property, JMX attribute or index option. To change it you must edit the source and rebuild. That is also an on-disk format change, because the reader uses the same constant (`OnDiskBlock.java:53,56`; `OnDiskIndex.java:639`), so SASI files written with another value cannot be read.

Other uses in the same file:
- the `SequentialWriter` buffer size, `WRITER_OPTION` (`:131-133`)
- the header padding, `out.skipBytes(BLOCK_SIZE - position)` (`:287`)
- block alignment, `alignToBlock` (`:341-346`)
- the per-block staging buffer, `new DataOutputBufferFixed(BLOCK_SIZE)` (`:528`)

A separate, unrelated constant with the same value is `TokenTreeBuilder.BLOCK_BYTES = 4096` (`TokenTreeBuilder.java:30`).

**A2. What it caps.**
- **Resource:** the heap bytes of one `MutableBlock` staging buffer, and the on-disk size of one term block (the term section of a pointer or data block) in the SASI index component `*-SI_<index>.db`.
- **Quantity compared:** `sizeAfter(element)` = `getWatermark() + 4 + element.serializedSize()` (`:548-551`), where `getWatermark()` = `4 + offsets.size()*2 + buffer.position()` (`:553-556`). For data blocks it adds `ptrLength(element)` (`:616-619`, `:644-649`): 5 if the term has more than 5 tokens, else `1 + 8*tokens`.
- **What sizeAfter means:** the size the block's header (term count + 2-byte offsets) plus term bytes would reach if the next term were added, with 4 bytes of headroom.
- **Not compared:** the token trees ("containers") that follow each data block on disk, the builder's term map, and the number of blocks or levels.

**A3. Mechanism.**
1. `OnDiskIndexBuilder.add` collects terms into `Map<ByteBuffer, TokenTreeBuilder> terms` (`:165-197`) and updates `estimatedBytes`. `BLOCK_SIZE` plays no part in this phase. Terms with `remaining() >= MAX_TERM_SIZE` (1024) are rejected (`:167-173`), and so are they in `PerSSTableIndexWriter.java:218-227`.
2. `finish(File)` (`:244-262`) builds a suffix array (`SuffixSA` for CONTAINS text, `IntegralSA` otherwise) and calls `finish(descriptor, range, file, termIterator)` (`:264-324`). That method writes a header padded to `BLOCK_SIZE` (`:287`), creates the data level with one `MutableDataBlock` (`:289-290`), and feeds each sorted term to `addTerm` (`:204-217`).
3. `MutableLevel.add(term)` (`:428-442`) calls `inProcessBlock.hasSpaceFor(term)`. That is the check at
   [`OnDiskIndexBuilder.java:545`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java#L545):
   `return sizeAfter(element) < BLOCK_SIZE;`.
   - **True:** the term is serialized into the 4 KiB `DataOutputBufferFixed` (`:532-541`; data blocks `:592-614`, `:659-664`).
   - **False:**
     1. `flush()` (`:444-448`) records the block offset.
     2. `flushAndClear` (`:558-570`) writes the term count, the short offsets and the buffer contents, then pads to the next `BLOCK_SIZE` boundary. For a data block (`:621-642`) it then writes an int and every term's token tree, and pads again.
     3. The block's last term is promoted as an `InMemoryPointerTerm` into the next pointer level (`:213-215`). `getIndexLevel` (`:326-339`) creates that level if needed, so each level up holds about 1/k of the entries below it.
     4. The buffer is cleared and the new term is added, **without re-checking** (`:432-438`).
4. **Bypass / overshoot:**
   - **No re-check after flush.** A term that alone did not fit an empty block would hit `DataOutputBufferFixed.doFlush`, which throws `BufferOverflowException` (`DataOutputBufferFixed.java:46-50`). `MAX_TERM_SIZE = 1024` upstream prevents this: an empty-block worst case is `4+4+(2+1023)+41 = 1074 < 4096`. Suffixes in CONTAINS mode are never longer than their source term.
   - **Conservative check.** In non-SPARSE mode `sizeAfter` counts `ptrLength` = 1+8·tokens for terms with ≤5 tokens, but `writeTerm(term, offset)` (`:659-664`) writes only 5 bytes. Blocks therefore fill to less than 4096, never more.
   - **Token trees are outside the check.** A data block's on-disk extent is `BLOCK_SIZE + align(4 + Σ treeSize, BLOCK_SIZE)` (`:621-642`), which has no limit. One term held by many keys can make one block many MB. In SPARSE mode the per-block `combinedIndex` and the 64-block `superBlockTree` (`:469-519`) are also outside it.
   - **Heap does not depend on the check.** The 4096-byte heap array is allocated at construction (`:528` → `BufferedDataOutputStreamPlus.java:70-78`, `ByteBuffer.allocate`). The live count is one per level plus the data level, each created once per `finish` (`:289-290`, `:329`, `:335`), so heap use is the same whichever way the check goes.

**A4. Other consumers.** The same heap and disk are used outside this check by:
- **Builder heap:** the `terms` HashMap and one `DynamicTokenTreeBuilder` per term (`estimatedMemoryUse`, `:180-194`). It is capped per segment at `PerSSTableIndexWriter.java:247`:
  - 1 GiB for memtable flush (`:365-369`)
  - otherwise the index option `max_compaction_flush_memory_in_mb`, default 0.15 × 1 GiB (`IndexMode.java:58-60,186-194`)
- **Other heap during `finish`:** the SA arrays built in `finish`, the `containers` list per data block, `TokenTreeBuilder.write`'s 4 KiB `ByteBuffer.allocate(BLOCK_BYTES)` (`AbstractTokenTreeBuilder.java:77`), the `SequentialWriter` buffer (4096), and the `LongArrayList` block offsets per level.
- **Disk:**
  - the SI file itself
  - temporary segment files `SI_<idx>.db_<n>` during compaction (`PerSSTableIndexWriter.java:358-362`, deleted at `:334-340`)
  - the SSTable components
  - the commit log
- **Read-side:** `OnDiskIndex` maps the SI file (`OnDiskIndex.java:150-153`).
- **Memtable-side:** the SASI in-memory index for the memtable.

**A5. Evidence beyond the source.**
- `doc/SASI.md:417-450` describes the on-disk index as page-size blocks of terms plus pointer levels.
- `test/unit/org/apache/cassandra/index/sasi/disk/OnDiskIndexTest.java` covers construction and lookup. Its `testSuperBlockRetrieval` builds 100,000 terms. No test asserts block fill.
- SASI contribution: CASSANDRA-10661, https://issues.apache.org/jira/browse/CASSANDRA-10661. Cited for provenance only; not opened in this session.
- Git history: not available, because the source copy has no `.git`.

## B. Verification solution

**B1. Claim under test.** The `BLOCK_SIZE` check at `OnDiskIndexBuilder.java:545` caps only each term block's footprint (≤ 4093 bytes, or ≤ `BLOCK_SIZE − 3` for the patched value). It does **not** cap the memory or disk that SASI index building uses:
- builder heap and index file size grow about linearly with the number of indexed terms N;
- the check-governed buffers stay at (levels+1) × `BLOCK_SIZE` bytes, a few tens of KiB;
- doubling `BLOCK_SIZE` changes total index file size by less than 2%.

The claim is refuted if total heap or disk levels off at a value set by `BLOCK_SIZE`, or scales with it.

### B2. Unit tier

**B2a. Environment and build.**
- **Machine:** Linux, JDK 11 (`JAVA_HOME` set), Apache Ant 1.10.
- **Run directory:** `RUN=/mydata/<operator>-s4/o167`, on local disk.
- **Two private copies of the tag:**
  - `$RUN/stock`: unchanged.
  - `$RUN/b8192`: `BLOCK_SIZE` changed to 8192. This is the only way to vary a constant. It changes the whole format consistently, because reader and writer both read the constant.
- **Probe class:** `BlockSizeProbeTest` (below), placed in `test/unit/org/apache/cassandra/index/sasi/disk/` of **each copy only**, never in the shared tree.
- **JVM:** the test JVM comes from `ant testsome`, which uses `-Xmx4G` and the jamm javaagent (`build.xml:1255`, `:1159`). Raise the timeout with `-Dtest.timeout=3600000` (the default is 480 s, `build.xml:125`).

```java
package org.apache.cassandra.index.sasi.disk;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.List;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.BufferDecoratedKey;
import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.db.marshal.LongType;
import org.apache.cassandra.db.marshal.UTF8Type;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.utils.ByteBufferUtil;
import org.apache.cassandra.utils.ObjectSizes;

public class BlockSizeProbeTest
{
    static final int B = OnDiskIndexBuilder.BLOCK_SIZE;
    static final String DIR = System.getenv("PROBE_DIR");   // must be set, local disk
    static PrintWriter out;

    @BeforeClass
    public static void setup() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        out = new PrintWriter(new FileWriter(DIR + "/probe-B" + B + ".csv", true), true);
        out.println("run,B,L,N,k_first,F_max,F_min_nonfinal,data_blocks,ptr_blocks,levels,block_buf_bytes,est_bytes,deep_bytes,file_bytes");
    }

    static DecoratedKey keyAt(long i)
    {
        return new BufferDecoratedKey(new Murmur3Partitioner.LongToken(i), ByteBufferUtil.bytes(i));
    }

    /** fixed-length, zero-padded decimal string of exactly L bytes; sorted order == numeric order */
    static ByteBuffer term(long i, int L)
    {
        String s = Long.toString(i);
        StringBuilder sb = new StringBuilder(L);
        for (int c = s.length(); c < L; c++) sb.append('0');
        return UTF8Type.instance.decompose(sb.append(s).toString());
    }

    static OnDiskIndexBuilder newBuilder()
    {
        return new OnDiskIndexBuilder(LongType.instance, UTF8Type.instance, OnDiskIndexBuilder.Mode.PREFIX);
    }

    static Object get(Object o, String name) throws Exception
    {
        for (Class<?> c = o.getClass(); c != null; c = c.getSuperclass())
        {
            try { Field f = c.getDeclaredField(name); f.setAccessible(true); return f.get(o); }
            catch (NoSuchFieldException ignore) { }
        }
        throw new NoSuchFieldException(name);
    }

    /** capacity of the DataOutputBufferFixed inside a level's in-process block */
    static int bufCap(Object level) throws Exception
    {
        Object block = get(level, "inProcessBlock");
        Object dob = get(block, "buffer");                 // MutableBlock.buffer (DataOutputBufferFixed)
        return ((ByteBuffer) get(dob, "buffer")).capacity(); // BufferedDataOutputStreamPlus.buffer
    }

    /** footprint as the check counts it: 4 (count) + 2n (offsets) + bytes up to the end of the last term */
    static long footprint(ByteBuffer f, int off, int trailer)
    {
        int n = f.getInt(off);
        int base = off + 4 + 2 * n;
        int last = f.getShort(off + 4 + 2 * (n - 1)) & 0xFFFF;
        int len = f.getShort(base + last) & 0x7FFF;          // VARIABLE term: 2-byte length (+partial bit)
        return 4 + 2L * n + last + 2 + len + trailer;        // trailer: 4 (pointer blockCnt) / 5 (data: 0x0 + int)
    }

    /** {dataBlocks, ptrBlocks, kFirst, Fmax, FminNonFinal} parsed from the written file */
    static long[] parse(String path) throws Exception
    {
        try (FileChannel ch = FileChannel.open(Paths.get(path), StandardOpenOption.READ))
        {
            ByteBuffer f = ch.map(FileChannel.MapMode.READ_ONLY, 0, ch.size());
            int p = (int) f.getLong((int) (ch.size() - 8));   // levelIndexPosition (OnDiskIndexBuilder.java:302-310)
            int numLevels = f.getInt(p); p += 4;
            long ptrBlocks = 0, fMax = 0, fMin = Long.MAX_VALUE, kFirst = -1;
            for (int l = 0; l < numLevels; l++)
            {
                int cnt = f.getInt(p); p += 4;
                for (int b = 0; b < cnt; b++, p += 8)
                    fMax = Math.max(fMax, footprint(f, (int) f.getLong(p), 4));
                ptrBlocks += cnt;
            }
            int dcnt = f.getInt(p); p += 4;
            for (int b = 0; b < dcnt; b++, p += 8)
            {
                int off = (int) f.getLong(p);
                long fp = footprint(f, off, 5);
                if (b == 0) kFirst = f.getInt(off);
                fMax = Math.max(fMax, fp);
                if (b < dcnt - 1) fMin = Math.min(fMin, fp);
            }
            return new long[]{ dcnt, ptrBlocks, kFirst, fMax, fMin == Long.MAX_VALUE ? -1 : fMin };
        }
    }

    void run(String id, int L, long N) throws Exception
    {
        OnDiskIndexBuilder b = newBuilder();
        for (long i = 0; i < N; i++)
            b.add(term(i, L), keyAt(i), i);
        long est = b.estimatedMemoryUse();
        long deep = ObjectSizes.measureDeep(b);
        String path = DIR + "/" + id + "-B" + B + ".db";
        b.finish(new File(path));
        List<?> levels = (List<?>) get(b, "levels");
        long bufBytes = bufCap(get(b, "dataLevel"));
        for (Object l : levels) bufBytes += bufCap(l);
        long size = new java.io.File(path).length();
        long[] r = parse(path);
        out.printf("%s,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d%n",
                   id, B, L, N, r[2], r[3], r[4], r[0], r[1], levels.size(), bufBytes, est, deep, size);
        new java.io.File(path).delete();
    }

    @Test public void r1() throws Exception { run("R1", 16,    10_000); }
    @Test public void r2() throws Exception { run("R2", 16,   100_000); }
    @Test public void r3() throws Exception { run("R3", 16, 1_000_000); }
    @Test public void r4() throws Exception { run("R4", 64,   100_000); }
    @Test public void r5() throws Exception { run("R5", 256,  100_000); }
    @Test public void r6() throws Exception { run("R6", 1000,  10_000); }

    /** positive control: the in-tree segment rule (PerSSTableIndexWriter.java:247) with a 1 MiB cap */
    @Test public void c1() throws Exception
    {
        final long cap = 1L << 20; final int L = 16; final long N = 100_000;
        OnDiskIndexBuilder b = newBuilder();
        int seg = 0; long maxEst = 0, maxDeep = 0;
        for (long i = 0; i < N; i++)
        {
            b.add(term(i, L), keyAt(i), i);
            if (b.estimatedMemoryUse() >= cap)
            {
                maxEst = Math.max(maxEst, b.estimatedMemoryUse());
                maxDeep = Math.max(maxDeep, ObjectSizes.measureDeep(b));
                seg++;
                b = newBuilder();
            }
        }
        if (!b.isEmpty()) { seg++; maxDeep = Math.max(maxDeep, ObjectSizes.measureDeep(b)); }
        out.printf("C1,%d,%d,%d,segments=%d,maxEst=%d,maxDeep=%d%n", B, L, N, seg, maxEst, maxDeep);
    }
}
```

If `ObjectSizes.measureDeep` throws on JDK 11 (module access), replace `deep` with the difference in `Runtime.totalMemory()-freeMemory()`, each reading taken after `System.gc()` three times: once before the add loop and once after it, with the builder still reachable. Note in the readings that this fallback was used.

**B2b. Knobs.**
- **`BLOCK_SIZE`:** 4096 (stock) and 8192 (patched copy). The patch is `sed -i 's/public static final int BLOCK_SIZE = 4096;/public static final int BLOCK_SIZE = 8192;/' src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java` in `$RUN/b8192`. The patched copy runs only R2 and R3 (`-Dtest.methods=r2,r3`). 8192 is the smallest change that keeps term offsets inside a signed short (`:534`) and keeps `MAX_TERM_SIZE` fitting. It isolates "does total usage follow the constant?".
- **N (terms):** 10⁴, 10⁵, 10⁶ at L = 16. This shows whether usage grows with workload while the check's quantity stays bounded.
- **L (term length):** 16, 64, 256, 1000. This varies how many terms fit per block, k, and the number of levels. 1000 is just under `MAX_TERM_SIZE`.

**B2c. Workload.** N distinct UTF-8 terms of exactly L bytes, one key each (token = i), PREFIX mode. That gives `IntegralSA`, with no suffix expansion. With one key per term, `ptrLength` = 9 and the bytes written per data term are `2 + L + 5`.

For the i-th term (0-based) of a data block, the check is `19 + L + i·(L+9) < BLOCK_SIZE`. So:
- terms per full data block: k = ⌊(B − 20 − L)/(L+9)⌋ + 1
- full-block footprint: F = 4 + k·(L+9)

| L | k (B=4096) | F, full block | Data blocks for the run |
|---|---|---|---|
| 16 | 163 | 4079 | R1: 62, R2: 614, R3: 6135 |
| 64 | 55 | 4019 | R4: 1819 |
| 256 | 15 | 3979 | R5: 6667 |
| 1000 | 4 | 4040 | R6: 2500 |
| 16, B=8192 | 327 | 8179 | R2′: 306, R3′: 3059 |

The limit is reached and passed about N/k times per run, between 62 and 6667 crossings.

Pointer levels:
- Pointer term: `2 + L + 4` bytes, plus 2 bytes of offset per entry.
- Pointer-block capacity: k_ptr = ⌊(B − 15 − L)/(L+8)⌋ + 1, which is 170 for L=16, 56 for L=64, 15 for L=256 and 4 for L=1000.
- Each data-block overflow promotes one entry.

**B2d. Observables and instruments.** All are written per run to `$PROBE_DIR/probe-B<B>.csv`.
- **`F_max`:** the maximum check footprint over all pointer and data blocks, parsed from the written file. This is the check's own operand, measured after the fact.
- **`F_min_nonfinal`:** the minimum footprint over non-final data blocks. It shows blocks are filled up to the limit, not stopped early.
- **`k_first`:** the term count of the first data block.
- **`data_blocks`, `ptr_blocks`, `levels`:** from the file's level index and the builder's `levels` field.
- **`block_buf_bytes`:** Σ capacity of all `MutableBlock` buffers, through reflection. This is the heap held by the check-governed buffers.
- **`est_bytes`:** `estimatedMemoryUse()`. **`deep_bytes`:** jamm `measureDeep(builder)` before `finish`. Together they are builder heap.
- **`file_bytes`:** SI file size on disk.
- **Not observable directly:** how full the buffer was when each check was evaluated. It is inferred from the file, because every flushed block holds exactly what the buffer held. Transient heap inside `finish` (the SA arrays) is not measured.

**B2e. Procedure.**
1. `RUN=/mydata/<operator>-s4/o167; mkdir -p $RUN/probe; df -h /mydata`. At least 10 GB must be free.
2. `rsync -a ~/cassandra-5.0.9/ $RUN/stock/ && rsync -a ~/cassandra-5.0.9/ $RUN/b8192/`
3. Apply the B2b `sed` in `$RUN/b8192` only. Confirm with `grep -n 'BLOCK_SIZE =' $RUN/*/src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java`.
4. Copy `BlockSizeProbeTest.java` into `test/unit/org/apache/cassandra/index/sasi/disk/` of both copies.
5. `cd $RUN/stock && ant jar build-test && PROBE_DIR=$RUN/probe ant testsome -Dtest.name=org.apache.cassandra.index.sasi.disk.BlockSizeProbeTest -Dtest.timeout=3600000 -Dno-build-test=true`
6. `cd $RUN/b8192 && ant jar build-test && PROBE_DIR=$RUN/probe ant testsome -Dtest.name=org.apache.cassandra.index.sasi.disk.BlockSizeProbeTest -Dtest.methods=r2,r3,c1 -Dtest.timeout=3600000 -Dno-build-test=true`
7. `cat $RUN/probe/probe-B4096.csv $RUN/probe/probe-B8192.csv`, then compare with B2f.
8. `ls $RUN/probe/*.db`: should list nothing, because the probe deletes its files. `pgrep -f "$RUN"`: should list nothing.

**B2f. Predictions.** All stated before any run.
- **`est_bytes`:** exact, because the formula is deterministic: N·(220+L).
- **Footprint:** `F_max ≤ 4093` for every stock run (`≤ 8189` for B=8192), and `F_min_nonfinal ≥ 4081 − L`.
- **File sizes:** approximate, within ±1%.

`F_data` is the footprint of a full data block (`4 + k·(L+9)`). `F_ptr` is the footprint of a full pointer block (`4 + k_ptr·(L+8)`), and counts only when level 0 overflows at least once. The CSV column `F_max` is the larger of the two that occur.

| Run | B | L | N | k_first | F_data | F_ptr (full) | F_max (CSV) | data_blocks | levels | block_buf_bytes | est_bytes | file_bytes ≈ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R1 | 4096 | 16 | 10⁴ | 163 | 4079 | — (level 0 holds 61 entries, 1468) | 4079 | 62 | 1 | 8 192 | 2 360 000 | 1.27 MB |
| R2 | 4096 | 16 | 10⁵ | 163 | 4079 | 4084 | 4084 | 614 | 2 | 12 288 | 23 600 000 | 12.60 MB |
| R3 | 4096 | 16 | 10⁶ | 163 | 4079 | 4084 | 4084 | 6135 | 2 | 12 288 | 236 000 000 | 125.85 MB |
| R4 | 4096 | 64 | 10⁵ | 55 | 4019 | 4036 | 4036 | 1819 | 2 | 12 288 | 28 400 000 | 22.5 MB |
| R5 | 4096 | 256 | 10⁵ | 15 | 3979 | 3964 | 3979 | 6667 | 4 | 20 480 | 47 600 000 | 56.6 MB |
| R6 | 4096 | 1000 | 10⁴ | 4 | 4040 | 4036 | 4040 | 2500 | 6 | 28 672 | 12 200 000 | 23.9 MB |
| R2′ | 8192 | 16 | 10⁵ | 327 | 8179 | — (level 0 holds 305 of 341) | 8179 | 306 | 1 | 16 384 | 23 600 000 | 12.54 MB |
| R3′ | 8192 | 16 | 10⁶ | 327 | 8179 | 8188 | 8188 | 3059 | 2 | 24 576 | 236 000 000 | 125.4 MB |

Relations:
- `deep_bytes(R3)/deep_bytes(R2)` and `file_bytes(R3)/file_bytes(R2)` are each in [9, 11]. `block_buf_bytes` stays ≤ 28 KiB in every run.
- `deep_bytes` with B=8192 is within ±2% of the same run with B=4096, because `add()` never reads `BLOCK_SIZE`.
- `file_bytes` with B=8192 is within ±2% of B=4096, even though the per-block buffer doubles.
- Every `F_max` is ≤ `BLOCK_SIZE` − 3 (the check allows a new footprint of at most `sizeAfter − 2` = 4093; data blocks at most `sizeAfter − 6`, because `ptrLength` counts 9 bytes where 5 are written).

C1 (both builds):
- `segments` = 23: 22 full segments of 4444 terms, plus a remainder of 2232.
- `maxEst` = 1 048 784.
- `maxDeep` ≈ `deep_bytes(R2)`/22.5, within ±20%.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| F_max ≤ 4093 (≤ 8189 patched); k_first and data_blocks as predicted | The check binds its own operand as traced. Needed before any other reading counts. |
| F_max > `BLOCK_SIZE` − 3, or a `BufferOverflowException` | The trace in A3 is wrong: the operand overshoots. |
| deep_bytes and file_bytes grow about 10× per 10× N; block_buf_bytes ≤ 28 KiB; B=8192 changes deep and file by < 2%; C1 shows deep capped near 1 MiB | **Claim confirmed:** usage does not follow `BLOCK_SIZE`, and the instruments do respond where a real cap binds. |
| deep_bytes or file_bytes level off as N grows, or change by > 10% between B=4096 and B=8192 at the same N | **Claim refuted:** usage follows the constraint. |
| block_buf_bytes grows about linearly with N (not as log N) | **Claim refuted:** the staging buffers are significant for memory. |
| data_blocks ≈ 1 (limit never crossed), or C1 shows segments ≠ 23 or deep not reduced versus R2 | **Not confirmed:** the workload did not exercise the check, or the positive control did not move. Fix the harness and rerun. |

**B2h. Controls.**
- **Positive control C1:** the same terms, under the in-tree segment rule at a 1 MiB cap. It shows `deep_bytes` does respond when a heap cap binds.
- **Patched build as a direct knob control:** if the constant governed usage, total usage would move with it.
- **Exact `est_bytes`** confirms that the same workload went into each run.
- **One key per term** removes token-tree size variation.
- **Fixed-length terms** make k exact.
- **`F_min_nonfinal`** confirms blocks are filled up to the limit, not cut short for another reason, for example the SPARSE 5-key rule. That rule does not apply in PREFIX mode.

### B3. Cluster tier

**B3a. Environment and build.**
- **Nodes:** one Linux node, with the stock copy `$RUN/stock` already built by `ant jar` in B2e.
- **JVM:** `MAX_HEAP_SIZE=4G`, `HEAP_NEWSIZE=800M`.
- **Configuration:** a private configuration copy, set up as follows.

```
C=$RUN/conf; cp -r $RUN/stock/conf $C
sed -i -e 's/^storage_port: 7000/storage_port: 17000/' \
       -e 's/^ssl_storage_port: 7001/ssl_storage_port: 17001/' \
       -e 's/^native_transport_port: 9042/native_transport_port: 19042/' \
       -e 's/127.0.0.1:7000/127.0.0.1:17000/' \
       -e 's/^sasi_indexes_enabled: false/sasi_indexes_enabled: true/' $C/cassandra.yaml
cat >> $C/cassandra.yaml <<EOF
data_file_directories:
    - $RUN/data
commitlog_directory: $RUN/commitlog
hints_directory: $RUN/hints
saved_caches_directory: $RUN/saved_caches
cdc_raw_directory: $RUN/cdc_raw
EOF
sed -i 's/^JMX_PORT="7199"/JMX_PORT="17199"/' $C/cassandra-env.sh
```

The edits do the following:
- **Ports:** move to 17000/17001/19042/17199, so another instance on the node is not disturbed.
- **SASI:** turned on with `sasi_indexes_enabled: true` (`conf/cassandra.yaml:1992`). Without it, `CreateIndexStatement.java:122` rejects the index.
- **Directories:** all go under `$RUN`.

**B3b. Knobs.**
- **`BLOCK_SIZE`:** stays at 4096. It is not settable, and B2 already varies it in-process.
- **Workload size N:** 10⁵ and 10⁶.
- **Term length L:** 16 and 256.
- **Positive-control knob:** the SASI index option `max_compaction_flush_memory_in_mb`, `1` versus default (153.6 MiB). It is set per index in `CREATE CUSTOM INDEX ... WITH OPTIONS` and needs no restart.

**B3c. Workload.** Tables, each with `id bigint PRIMARY KEY, v text`, autocompaction disabled, and a PREFIX SASI index on `v`:

| Table | N | L | Load |
|---|---|---|---|
| `t16` | 10⁵ | 16 | one load |
| `t16m` | 10⁶ | 16 | one load |
| `t256` | 10⁵ | 256 | one load |
| `pc_def` | 10⁵ | 16 | two halves (0..49 999, then 50 000..99 999), flush after each, then `nodetool compact` |
| `pc_cap` | 10⁵ | 16 | as `pc_def`, with `max_compaction_flush_memory_in_mb` = 1 |

- **Values:** `v` = the id zero-padded to L characters, the same terms as B2.
- **Limit reached:** a memtable flush builds one SI file per SSTable through `PerSSTableIndexWriter` → `OnDiskIndexBuilder.finish`. The block check is crossed about N/k times: 614, 6135 and 6667 times for `t16`, `t16m` and `t256`.
- **Compaction (pc tables):** the builder estimate is 236 B/row × 10⁵ = 23.6 MB. That is above `pc_cap`'s 1 MiB and below `pc_def`'s 153.6 MiB.
- **Duration:** under 30 min in total.

**B3d. Observables and instruments.**
1. **SI disk usage per table:** after each flush or compaction, `find $RUN/data/ks -path "*/<table>-*" -name '*SI_<table>_v_idx.db' -printf '%s\n' | awk '{s+=$1} END {print s, NR}'`. This gives total bytes and the file count.
2. **Segment flushes (positive control):** `grep -c "Flushed index segment .*SI_pc_cap_v_idx" $RUN/logs/system.log`, and the same for `pc_def`. Each line is one segment that the heap cap forced (`PerSSTableIndexWriter.java:247,272-274`).
3. **Check-governed heap (secondary):** `jcmd $PID GC.class_histogram | grep -E 'OnDiskIndexBuilder\$Mutable(Data)?Block '` in a loop, run back to back during `nodetool flush ks t16m`. This gives the instance count.
4. **Not observable directly:** the node's heap share for the ≤ 28 KiB of staging buffers. It is far below GC and sampling noise in a 4 GiB heap, and the histogram can miss the seconds-long `finish` window. Node-level heap is therefore not used as evidence. The unit tier carries the heap claim.

**B3e. Procedure.**
1. **Start the node:** `cd $RUN/stock && CASSANDRA_CONF=$C CASSANDRA_LOG_DIR=$RUN/logs MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M bin/cassandra -p $RUN/cassandra.pid`. Then wait until `bin/nodetool -p 17199 status` shows `UN`.
2. **Generate CSVs:** `python3 -c "import sys;N,L,a=map(int,sys.argv[1:]);[print(f'{i},{str(i).zfill(L)}') for i in range(a,a+N)]" N L START > $RUN/<name>.csv`. Make:
   - `t16.csv` (100000 16 0)
   - `t16m.csv` (1000000 16 0)
   - `t256.csv` (100000 256 0)
   - `h1.csv` (50000 16 0)
   - `h2.csv` (50000 16 50000)
3. **Create the schema** with `bin/cqlsh 127.0.0.1 19042`. Repeat the table and index for each table name:
   ```
   CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy','replication_factor':1};
   CREATE TABLE ks.t16 (id bigint PRIMARY KEY, v text) WITH compaction = {'class':'SizeTieredCompactionStrategy','enabled':'false'};
   CREATE CUSTOM INDEX t16_v_idx ON ks.t16 (v) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode':'PREFIX'};
   ```
   `t16m`, `t256` and `pc_def` are the same. `pc_cap` uses `OPTIONS = {'mode':'PREFIX','max_compaction_flush_memory_in_mb':'1'}`.
4. **Load and flush:** for each of `t16`, `t256`, `t16m`, run `bin/cqlsh 127.0.0.1 19042 -e "COPY ks.<t> (id, v) FROM '$RUN/<t>.csv' WITH CHUNKSIZE=5000"`, then `bin/nodetool -p 17199 flush ks <t>`, then record instrument 1.
   - During the `t16m` flush, run instrument 3 in a second shell until the flush returns.
5. **Positive control:** for each pc table:
   1. COPY `h1.csv`, then flush.
   2. COPY `h2.csv`, then flush.
   3. `nodetool -p 17199 compact ks <t>`.
   4. Record instruments 1 and 2.
6. **Stop:** `kill $(cat $RUN/cassandra.pid)`. Wait for the process to exit, then confirm `pgrep -f "$RUN"` is empty.

**B3f. Predictions.** Per-row SI bytes depend only on L, through k and the 80-byte one-token trees: about 126 B/row at L=16 and about 566 B/row at L=256 (including pointer levels).

| Table | Σ SI bytes ≈ | Notes |
|---|---|---|
| `t16` | 12.6 MB | ±2%, plus ≤ 30 KiB per extra SSTable if the memtable flushed more than once |
| `t16m` | 125.9 MB | ratio `t16m`/`t16` in [9.5, 10.5] |
| `t256` | 56.6 MB | |
| `pc_def` | ≈ `t16` (±2%) | 0 "Flushed index segment" lines |
| `pc_cap` | ≈ `t16` (±2%) | 23 "Flushed index segment" lines (22 at the cap plus 1 inline remainder, `PerSSTableIndexWriter.java:299-303`); temporary `_n` files deleted afterwards |

Instrument 3: if any `MutableBlock` or `MutableDataBlock` instances are seen, there are ≤ 3 per concurrently finishing SASI builder (levels+1 = 3 for N=10⁶, L=16).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| SI bytes scale about linearly with N (ratio about 10) and with L as predicted; `pc_cap` shows about 23 segment flushes against 0 for `pc_def` | **Claim confirmed:** disk follows the workload, not `BLOCK_SIZE`. The same workload's builder heap is capped where a real cap binds. |
| SI bytes level off (ratio well below 9.5) at a value tied to 4096 | **Claim refuted.** |
| SI file per SSTable never exceeds a fixed bound tied to `BLOCK_SIZE` while data grows | **Claim refuted.** |
| Instrument 3 shows `MutableBlock` counts growing with N (more than about 10) | **Claim refuted** for heap: the buffers are significant. |
| `pc_cap` shows 0 segment flushes (positive control did not move), or no SI files were written (SASI not enabled or the index failed) | **Not confirmed.** Check `system.log` for "SASI indexes are disabled" or "Failed to build index segment", then rerun. |

**B3h. Controls.**
- **Positive control:** `pc_cap` against `pc_def` on identical data.
- **Same terms as B2**, so the cluster totals can be checked against the unit-tier `file_bytes` (R2 ≈ `t16`, R3 ≈ `t16m`, R5 ≈ `t256`). Any gap is per-SSTable overhead, and is explained by the file count from instrument 1.
- **Autocompaction disabled**, so the SSTable count is under control.
- **One key per value.**
- **Private ports and directories**, so no other instance's files are counted.

**B4. Risks and cleanup.**
- **Disk:** about 3 GB for the two build copies, under 500 MB of unit-tier files at peak (R3 about 126 MB, deleted per run), and about 1 GB for the cluster tier (CSVs about 60 MB, SSTables, SI files, commit log). Everything goes on `/mydata` under `$RUN`, never on shared storage or in the shared source tree. Check `df -h /mydata` first.
- **Processes:** the forked test JVM ends with ant. Cassandra runs under `$RUN/cassandra.pid`, and must be stopped with `kill` and confirmed with `pgrep -f "$RUN"`.
- **Ports:** 17000/17001/19042/17199. If any is in use, choose others and change both the yaml and `cassandra-env.sh`.
- **Cleanup:** `rm -rf $RUN/data $RUN/commitlog $RUN/hints $RUN/saved_caches $RUN/cdc_raw $RUN/*.csv $RUN/probe/*.db`. Keep `$RUN/probe/*.csv`, `$RUN/logs/system.log` and the instrument outputs as results. Remove `$RUN/stock` and `$RUN/b8192` when stage 4 is done.

## C. Sources read

src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java
src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java
src/java/org/apache/cassandra/index/sasi/disk/OnDiskBlock.java
src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndex.java (lines 150-175, 625-650, grep for BLOCK_SIZE)
src/java/org/apache/cassandra/index/sasi/disk/TokenTreeBuilder.java
src/java/org/apache/cassandra/index/sasi/disk/AbstractTokenTreeBuilder.java (serializedSize, write)
src/java/org/apache/cassandra/index/sasi/conf/IndexMode.java
src/java/org/apache/cassandra/index/sasi/conf/ColumnIndex.java (FILE_NAME_FORMAT, getComponent)
src/java/org/apache/cassandra/io/util/DataOutputBufferFixed.java
src/java/org/apache/cassandra/io/util/DataOutputBuffer.java
src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java
src/java/org/apache/cassandra/io/sstable/format/SSTableFormat.java (SECONDARY_INDEX component)
src/java/org/apache/cassandra/cql3/statements/schema/CreateIndexStatement.java (SASI guard)
src/java/org/apache/cassandra/config/Config.java, DatabaseDescriptor.java (sasi_indexes_enabled)
src/java/org/apache/cassandra/utils/ObjectSizes.java (measureDeep)
test/unit/org/apache/cassandra/index/sasi/disk/OnDiskIndexTest.java
conf/cassandra.yaml, conf/cassandra-env.sh, bin/cassandra
build.xml (testsome, test.timeout, -Xmx, jamm agent)
doc/SASI.md
https://issues.apache.org/jira/browse/CASSANDRA-10661 (cited, not opened)

## D. Stage-4 feedback

none yet
