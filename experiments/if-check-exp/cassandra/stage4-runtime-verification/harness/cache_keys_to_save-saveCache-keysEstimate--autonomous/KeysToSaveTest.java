package org.apache.cassandra.cache;

import org.apache.cassandra.io.util.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.Random;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.Assume;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.Util;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.*;
import org.apache.cassandra.db.compaction.CompactionManager;
import org.apache.cassandra.db.marshal.*;
import org.apache.cassandra.io.sstable.AbstractRowIndexEntry;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.io.sstable.keycache.KeyCacheSupport;
import org.apache.cassandra.io.util.DataOutputPlus;
import org.apache.cassandra.schema.*;
import org.apache.cassandra.service.CacheService;
import org.apache.cassandra.service.CacheService.CacheType;
import org.apache.cassandra.utils.ByteBufferUtil;
import org.apache.cassandra.utils.Pair;
import org.apache.cassandra.utils.concurrent.Future;

import static org.apache.cassandra.config.CassandraRelevantProperties.TEST_ORG_CAFFINITAS_OHC_SEGMENTCOUNT;
import static org.apache.cassandra.utils.ByteBufferUtil.bytes;

/**
 * Stage-4 unit tier (B2) of cache_keys_to_save-saveCache-keysEstimate--autonomous.
 * Output: file named by -Dstage4.out, lines "STAGE4 ...". See the harness README.
 */
public class KeysToSaveTest
{
    private static final String KS = "KeysToSave";
    private static final String KEYT = "KeyT", ROWT = "RowT", CNTT = "CntT";
    private static final int PK = 10000, PR = 2000, PC = 2000;
    private static PrintWriter out;
    private static int checks = 0, bad = 0;

    @BeforeClass
    public static void setup() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        Assume.assumeTrue(KeyCacheSupport.isSupportedBy(DatabaseDescriptor.getSelectedSSTableFormat()));
        TEST_ORG_CAFFINITAS_OHC_SEGMENTCOUNT.setInt(16);
        String o = System.getProperty("stage4.out", "/tmp/stage4-kt.out");
        out = new PrintWriter(new FileWriter(o, false), true);
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1),
            TableMetadata.builder(KS, KEYT).addPartitionKeyColumn("pKey", AsciiType.instance).addRegularColumn("col1", AsciiType.instance),
            TableMetadata.builder(KS, ROWT).addPartitionKeyColumn("pKey", AsciiType.instance).addRegularColumn("col1", AsciiType.instance)
                         .caching(CachingParams.CACHE_EVERYTHING),
            TableMetadata.builder(KS, CNTT).isCounter(true).addPartitionKeyColumn("key", Int32Type.instance)
                         .addClusteringColumn("name", Int32Type.instance).addRegularColumn("c", CounterColumnType.instance));
        info("env java=" + System.getProperty("java.version") + " maxHeapMiB=" + Runtime.getRuntime().maxMemory() / (1 << 20)
             + " rowCacheClass=" + CacheService.instance.rowCache + " rowCacheCapMiB=" + CacheService.instance.rowCache.getCapacity() / (1 << 20)
             + " keyCacheCapMiB=" + CacheService.instance.keyCache.getCapacity() / (1 << 20)
             + " counterCacheCapMiB=" + CacheService.instance.counterCache.getCapacity() / (1 << 20)
             + " savedCachesDir=" + DatabaseDescriptor.getSavedCachesLocation());
    }

    static void info(String s) { out.println("STAGE4 info " + s); }

    static void check(String desc, Object expected, Object actual, boolean ok)
    {
        checks++;
        if (!ok) bad++;
        out.println("STAGE4 check " + desc + " expected=" + expected + " actual=" + actual + (ok ? " ok" : " MISMATCH"));
    }

    static long allocBytes()
    {
        return ((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean()).getThreadAllocatedBytes(Thread.currentThread().getId());
    }

    interface Pop { void run() throws Exception; }

    /** one save at N on the given cache: B2e step 2 (submitWrite path) plus the direct Writer for counters/allocation. */
    static <K extends CacheKey, V> void oneSave(String name, AutoSavingCache<K, V> cache, Pop populate, int p, int n, int rep, boolean allocToo) throws Exception
    {
        cache.clear();
        populate.run();
        int live0 = cache.size();
        File data = cache.getCacheDataPath("g");
        data.tryDelete();
        int expected = (n == 0 || n >= live0) ? live0 : n;
        // path 1: the scheduler's path
        cache.submitWrite(n).get();
        long len1 = data.exists() ? data.length() : -1;
        int live1 = cache.size();
        // path 2: direct Writer (same saveCache code), for the completed counter and the thread's allocation
        AutoSavingCache<K, V>.Writer w = cache.getWriter(n);
        long a0 = allocBytes();
        w.saveCache();
        long a1 = allocBytes();
        long completed = w.getCompactionInfo().getCompleted();
        long len2 = data.length();
        // reload
        cache.clear();
        int loaded = cache.loadSaved();
        int sizeAfterLoad = cache.size();
        out.println("STAGE4 save cache=" + name + " rep=" + rep + " N=" + n + " P=" + p + " live=" + live0 + " expectedItems=" + expected
                    + " completed=" + completed + " fileLen=" + len1 + " fileLenDirect=" + len2 + " liveAfterSave=" + live1
                    + " loaded=" + loaded + " sizeAfterLoad=" + sizeAfterLoad + " allocBytesSave=" + (a1 - a0));
        String tag = name + " N=" + n + " rep=" + rep;
        check(tag + " live population before save == P", p, live0, live0 == p);
        check(tag + " items completed == min(N,P) [N=0 or >=P: P]", expected, completed, completed == expected);
        check(tag + " reloaded count == items", completed, loaded, loaded == completed);
        check(tag + " size after reload == items", completed, sizeAfterLoad, sizeAfterLoad == completed);
        check(tag + " live size unchanged by the save", live0, live1, live0 == live1);
        check(tag + " both save paths wrote the same length", len1, len2, len1 == len2);
        lengths.put(name + "/" + n + "/" + rep, len1);
        if (allocToo) allocs.put(name + "/" + n + "/" + rep, a1 - a0);
    }

    static final java.util.Map<String, Long> lengths = new java.util.HashMap<>();
    static final java.util.Map<String, Long> allocs = new java.util.HashMap<>();

    static <T> List<T> shuffled(List<T> l, long seed) { List<T> c = new ArrayList<>(l); Collections.shuffle(c, new Random(seed)); return c; }

    @Test
    public void keyCache() throws Exception
    {
        ColumnFamilyStore cfs = Keyspace.open(KS).getColumnFamilyStore(KEYT);
        cfs.truncateBlocking();
        CompactionManager.instance.disableAutoCompaction();
        ColumnMetadata col = ColumnMetadata.regularColumn(cfs.metadata(), bytes("col1"), AsciiType.instance);
        for (int i = 0; i < PK; i++)
            new RowUpdateBuilder(cfs.metadata(), 1000 + i, "key" + i).add(col, "v").build().apply();
        Util.flush(cfs);
        check("keyT live sstables == 1", 1, cfs.getLiveSSTables().size(), cfs.getLiveSSTables().size() == 1);
        SSTableReader sst = cfs.getLiveSSTables().iterator().next();
        Pop populate = () -> {
            for (int i = 0; i < PK; i++) sst.getPosition(Util.dk("key" + i), SSTableReader.Operator.EQ);
            for (int r = 0; r < 5; r++)
                for (int i = 0; i < 100; i++) sst.getPosition(Util.dk("key" + i), SSTableReader.Operator.EQ);
        };
        AutoSavingCache<KeyCacheKey, AbstractRowIndexEntry> kc = CacheService.instance.keyCache;
        // control (B2e 5): no save -> no file; live size unchanged
        kc.clear(); kc.getCacheDataPath("g").tryDelete(); populate.run();
        check("keyT control: file absent without a save", false, kc.getCacheDataPath("g").exists(), !kc.getCacheDataPath("g").exists());
        check("keyT control: populated size == P", PK, kc.size(), kc.size() == PK);
        List<Integer> ns = List.of(1, 100, 1000, 9999, 10000, 20000, 0);
        for (int rep = 1; rep <= 2; rep++)
            for (int n : shuffled(ns, 42 + rep))
                oneSave("key", kc, populate, PK, n, rep, n == 1 || n == PK);
        // hot-key check: N=100 persisted keys vs the 100 touched
        kc.clear(); populate.run();
        // instrument control (added after shakedown/run-1a): the lookup finds all 10000 keys before the save
        int presentBefore = 0;
        for (int i = 0; i < PK; i++)
            if (kc.getInternal(new KeyCacheKey(cfs.metadata(), sst.descriptor, ByteBufferUtil.bytes("key" + i))) != null) presentBefore++;
        check("key hot-check lookup control: all P keys found before the save", PK, presentBefore, presentBefore == PK);
        kc.submitWrite(100).get();
        kc.clear(); int ld = kc.loadSaved();
        int hot = 0, anyPresent = 0;
        for (int i = 0; i < PK; i++)
            if (kc.getInternal(new KeyCacheKey(cfs.metadata(), sst.descriptor, ByteBufferUtil.bytes("key" + i))) != null)
            { anyPresent++; if (i < 100) hot++; }
        out.println("STAGE4 hot N=100 loaded=" + ld + " hotPresent=" + hot + " anyPresent=" + anyPresent);
        check("key hot-check lookup control: loaded entries are found by the lookup (anyPresent == loaded)", ld, anyPresent, anyPresent == ld);
        check("key N=100 persisted keys are the 100 touched (side finding)", 100, hot, hot == 100);
        lengthChecks("key");
        raceTest(cfs, sst);
    }

    static void lengthChecks(String name)
    {
        for (int rep = 1; rep <= 2; rep++)
        {
            Long l100 = lengths.get(name + "/100/" + rep), l1000 = lengths.get(name + "/1000/" + rep);
            if (l100 != null && l1000 != null)
            {
                double r = (double) l1000 / l100;
                out.println("STAGE4 ratio " + name + " rep=" + rep + " len(1000)/len(100)=" + r);
                check(name + " len(1000) ~ 10 x len(100) within 10% rep=" + rep, "9..11", r, r > 9.0 && r < 11.0);
            }
            Long a = lengths.get(name + "/10000/" + rep), z = lengths.get(name + "/0/" + rep), b = lengths.get(name + "/20000/" + rep);
            if (a != null && z != null && b != null)
                check(name + " len(N=P) == len(N=0) == len(N=20000) rep=" + rep, z, a + "," + b, a.equals(z) && b.equals(z));
        }
    }

    static class Val implements IMeasurableMemory { public long unsharedHeapSize() { return 8; } }

    /** B2e step 3 (U4): private KEY_CACHE-typed cache, stub serializer that blocks at the 100th key; 5000 more keys are added meanwhile. */
    void raceTest(ColumnFamilyStore cfs, SSTableReader sst) throws Exception
    {
        final AtomicInteger calls = new AtomicInteger();
        final CountDownLatch reached = new CountDownLatch(1), release = new CountDownLatch(1);
        AutoSavingCache.CacheSerializer<KeyCacheKey, Val> ser = new AutoSavingCache.CacheSerializer<KeyCacheKey, Val>()
        {
            public void serialize(KeyCacheKey key, DataOutputPlus o, ColumnFamilyStore c) throws IOException
            {
                int k = calls.incrementAndGet();
                if (k == 100) { reached.countDown(); try { release.await(); } catch (InterruptedException e) { throw new RuntimeException(e); } }
                o.writeInt(k);
            }
            public Future<Pair<KeyCacheKey, Val>> deserialize(org.apache.cassandra.io.util.DataInputPlus in) { return null; }
        };
        AutoSavingCache<KeyCacheKey, Val> pc = new AutoSavingCache<>(CaffeineCache.<KeyCacheKey, Val>create(100L << 20), CacheType.KEY_CACHE, ser);
        for (int i = 0; i < 10000; i++)
            pc.put(new KeyCacheKey(cfs.metadata(), sst.descriptor, bytes("a" + i)), new Val());
        // counterfactual iterator (no break): advance 100, add 5000, drain
        Iterator<KeyCacheKey> it = pc.keyIterator();
        int seen = 0;
        for (; seen < 100; seen++) it.next();
        for (int i = 0; i < 5000; i++)
            pc.put(new KeyCacheKey(cfs.metadata(), sst.descriptor, bytes("b" + i)), new Val());
        while (it.hasNext()) { it.next(); seen++; }
        for (int i = 0; i < 5000; i++) pc.remove(new KeyCacheKey(cfs.metadata(), sst.descriptor, bytes("b" + i)));
        check("race: private cache size back to 10000", 10000, pc.size(), pc.size() == 10000);
        out.println("STAGE4 race counterfactual-iterator-yield=" + seen + " (iterator started at 10000 entries, 5000 added after 100 steps)");
        // the real run
        final AutoSavingCache<KeyCacheKey, Val>.Writer w = pc.getWriter(0);
        Thread t = new Thread(w::saveCache);
        t.start();
        reached.await();
        for (int i = 0; i < 5000; i++)
            pc.put(new KeyCacheKey(cfs.metadata(), sst.descriptor, bytes("b" + i)), new Val());
        int sizeDuring = pc.size();
        release.countDown();
        t.join();
        long done = w.getCompactionInfo().getCompleted();
        out.println("STAGE4 race sizeAtConstruction=10000 sizeDuringSave=" + sizeDuring + " serializerCalls=" + calls.get() + " completed=" + done);
        check("race: cache reached 15000 during the save", 15000, sizeDuring, sizeDuring == 15000);
        check("race: items written <= size at Writer construction (10000)", "<=10000", done, done <= 10000);
        check("race: counterfactual iterator would have yielded more than 10000 (so the break at :388 did the bounding)", ">10000", seen, seen > 10000);
        pc.clear();
        // restore the real caches' files so later classes are not affected
        CacheService.instance.keyCache.getCacheDataPath("g").tryDelete();
    }

    @Test
    public void rowCache() throws Exception
    {
        ColumnFamilyStore cfs = Keyspace.open(KS).getColumnFamilyStore(ROWT);
        cfs.truncateBlocking();
        ColumnMetadata col = ColumnMetadata.regularColumn(cfs.metadata(), bytes("col1"), AsciiType.instance);
        for (int i = 0; i < PR; i++)
            new RowUpdateBuilder(cfs.metadata(), 1000 + i, "key" + i).add(col, "v").build().apply();
        AutoSavingCache<RowCacheKey, IRowCacheEntry> rc = CacheService.instance.rowCache;
        Pop populate = () -> { for (int i = 0; i < PR; i++) Util.getAll(Util.cmd(cfs, Util.dk("key" + i)).build()); };
        rc.clear(); populate.run();
        info("row cache populated size=" + rc.size());
        for (int rep = 1; rep <= 2; rep++)
            for (int n : shuffled(List.of(100, PR, 0), 7 + rep))
                oneSave("row", rc, populate, PR, n, rep, false);
        rc.clear();
    }

    @Test
    public void counterCache() throws Exception
    {
        ColumnFamilyStore cfs = Keyspace.open(KS).getColumnFamilyStore(CNTT);
        cfs.truncateBlocking();
        AutoSavingCache<CounterCacheKey, ClockAndCount> cc = CacheService.instance.counterCache;
        Pop populate = () -> {
            for (int i = 0; i < PC; i++)
                new CounterMutation(new RowUpdateBuilder(cfs.metadata(), 0, bytes(i)).clustering(1).add("c", 1L).build(), ConsistencyLevel.ONE).apply();
        };
        cc.clear(); populate.run();
        info("counter cache populated size=" + cc.size());
        for (int rep = 1; rep <= 2; rep++)
            for (int n : shuffled(List.of(100, PC, 0), 11 + rep))
                oneSave("counter", cc, populate, PC, n, rep, false);
        cc.clear();
    }

    @org.junit.AfterClass
    public static void summary()
    {
        for (String k : new java.util.TreeSet<>(allocs.keySet()))
            out.println("STAGE4 alloc " + k + " bytes=" + allocs.get(k));
        out.println("STAGE4 summary checks=" + checks + " mismatches=" + bad);
        out.close();
        SchemaLoader.cleanupSavedCaches();
    }
}
