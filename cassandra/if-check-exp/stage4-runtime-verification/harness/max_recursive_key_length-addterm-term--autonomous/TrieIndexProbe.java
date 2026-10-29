package org.apache.cassandra.index.sai.memory;

import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.Random;
import java.util.concurrent.atomic.AtomicLong;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.statements.schema.IndexTarget;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Clustering;
import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.db.guardrails.Guardrails;
import org.apache.cassandra.db.marshal.UTF8Type;
import org.apache.cassandra.db.tries.InMemoryTrie;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.index.sai.StorageAttachedIndex;
import org.apache.cassandra.schema.CachingParams;
import org.apache.cassandra.schema.IndexMetadata;
import org.apache.cassandra.schema.MockSchema;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.utils.ByteBufferUtil;

/**
 * Stage-4 unit probe for max_recursive_key_length-addterm-term--autonomous (B2).
 * usage: TrieIndexProbe term <L> <N> [guard]    adds N distinct random ASCII terms of exactly L bytes to a fresh TrieMemoryIndex (text column, no analyzer)
 *        TrieIndexProbe guard <thresholdBytes> <L>...   control: guardrail sai_string_term_size_{warn,fail}_threshold = thresholdBytes; adds 2000 terms of each L, prints per-L growth
 * Route counters are read from public static AtomicLong fields ROUTE_REC / ROUTE_APPLY when the overlay 'instr' is on the class path (else -1).
 * Memory: sum of add() returns, trie sizeOnHeap()/sizeOffHeap() read by reflection on field 'data', heap used after three System.gc().
 */
public class TrieIndexProbe
{
    static TrieMemoryIndex newIndex()
    {
        TableMetadata table = TableMetadata.builder("test_keyspace", "test_table")
                                           .addPartitionKeyColumn("key", UTF8Type.instance)
                                           .addRegularColumn("col", UTF8Type.instance)
                                           .partitioner(Murmur3Partitioner.instance)
                                           .caching(CachingParams.CACHE_NOTHING)
                                           .build();
        Map<String, String> options = new HashMap<>();
        options.put(IndexTarget.CUSTOM_INDEX_OPTION_NAME, StorageAttachedIndex.class.getCanonicalName());
        options.put("target", "col");
        IndexMetadata im = IndexMetadata.fromSchemaMetadata("col_index", IndexMetadata.Kind.CUSTOM, options);
        ColumnFamilyStore cfs = MockSchema.newCFS(table);
        return new TrieMemoryIndex(new StorageAttachedIndex(cfs, im));
    }

    static long counter(String name)
    {
        try { return ((AtomicLong) TrieMemoryIndex.class.getField(name).get(null)).get(); }
        catch (Throwable t) { return -1; }
    }

    static long heap()
    {
        for (int i = 0; i < 3; i++) { System.gc(); try { Thread.sleep(100); } catch (InterruptedException e) {} }
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    static ByteBuffer term(Random r, int i, int len)
    {
        byte[] b = new byte[len];
        int x = i;
        for (int k = 0; k < 4 && k < len; k++) { b[k] = (byte) ('a' + x % 26); x /= 26; }
        for (int k = 4; k < len; k++) b[k] = (byte) ('a' + r.nextInt(26));
        return ByteBuffer.wrap(b);
    }

    static long[] sizes(TrieMemoryIndex idx) throws Exception
    {
        Field f = TrieMemoryIndex.class.getDeclaredField("data");
        f.setAccessible(true);
        InMemoryTrie<?> t = (InMemoryTrie<?>) f.get(idx);
        return new long[]{ t.sizeOnHeap(), t.sizeOffHeap() };
    }

    public static void main(String[] a) throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        org.apache.cassandra.db.commitlog.CommitLog.instance.start(); // MockSchema.newCFS reads the commit log position
        String mode = a[0];
        if (mode.equals("term"))
        {
            int L = Integer.parseInt(a[1]), N = Integer.parseInt(a[2]);
            TrieMemoryIndex idx = newIndex();
            Random r = new Random(42);
            long h0 = heap();
            long sum = 0; String result = "OK"; int done = 0;
            try
            {
                for (int i = 0; i < N; i++)
                {
                    DecoratedKey k = Murmur3Partitioner.instance.decorateKey(ByteBufferUtil.bytes("k" + i));
                    sum += idx.add(k, Clustering.EMPTY, term(r, i, L));
                    done++;
                }
            }
            catch (StackOverflowError e) { result = "SOE"; }
            long[] s = sizes(idx);
            long h1 = heap();
            System.out.printf("STAGE4 TERM L=%d N=%d done=%d result=%s sumAdd=%d perTermAdd=%.3f onHeap=%d offHeap=%d perTermTrie=%.3f heapRetained=%d routeRec=%d routeApply=%d bufferType=%s%n",
                              L, N, done, result, sum, done == 0 ? 0.0 : (double) sum / done, s[0], s[1], done == 0 ? 0.0 : (double) (s[0] + s[1]) / done, h1 - h0,
                              counter("ROUTE_REC"), counter("ROUTE_APPLY"), org.apache.cassandra.db.memtable.TrieMemtable.BUFFER_TYPE);
        }
        else // guard
        {
            long thr = Long.parseLong(a[1]);
            Guardrails.instance.setSaiStringTermSizeThreshold(thr + "B", thr + "B");
            System.out.printf("STAGE4 GUARD warn=%s fail=%s%n", Guardrails.instance.getSaiStringTermSizeWarnThreshold(), Guardrails.instance.getSaiStringTermSizeFailThreshold());
            for (int ai = 2; ai < a.length; ai++)
            {
                int L = Integer.parseInt(a[ai]);
                TrieMemoryIndex idx = newIndex();
                Random r = new Random(7);
                long before[] = sizes(idx), sum = 0; int nz = 0;
                for (int i = 0; i < 2000; i++)
                {
                    DecoratedKey k = Murmur3Partitioner.instance.decorateKey(ByteBufferUtil.bytes("k" + i));
                    long d = idx.add(k, Clustering.EMPTY, term(r, i, L));
                    sum += d; if (d > 0) nz++;
                }
                long[] s = sizes(idx);
                System.out.printf("STAGE4 GUARDTERM L=%d adds=2000 addsWithGrowth=%d sumAdd=%d dOnHeap=%d dOffHeap=%d routeRec=%d routeApply=%d%n",
                                  L, nz, sum, s[0] - before[0], s[1] - before[1], counter("ROUTE_REC"), counter("ROUTE_APPLY"));
            }
        }
        System.exit(0);
    }
}
