package org.apache.cassandra.index.sai.memory;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.reflect.Field;

import org.junit.Assume;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.memtable.AbstractAllocatorMemtable;
import org.apache.cassandra.index.sai.SAITester;
import org.apache.cassandra.index.sai.StorageAttachedIndex;
import org.apache.cassandra.index.sai.StorageAttachedIndexGroup;
import org.apache.cassandra.utils.ObjectSizes;

public class SaiMemtableChargeTest extends SAITester
{
    private static final int N = Integer.getInteger("sai.rows", 100_000);
    private static final String OUT = System.getProperty("sai.out", "/var/tmp/sai-exp/unit.csv");

    private static String term(int i)
    {
        long a = (i + 1L) * 0x9E3779B97F4A7C15L, b = (i + 7L) * 0xC2B2AE3D27D4EB4FL;
        return String.format("%016x%016x", a ^ (a >>> 29), b ^ (b >>> 31));
    }
    private static long owns(ColumnFamilyStore c)
    {
        return ((AbstractAllocatorMemtable) c.getTracker().getView().getCurrentMemtable()).getAllocator().onHeap().owns();
    }
    private static StorageAttachedIndex sai(ColumnFamilyStore c)
    {
        return (StorageAttachedIndex) StorageAttachedIndexGroup.getIndexGroup(c).getIndexes().iterator().next();
    }
    private void insert(String table, int i) throws Throwable
    {
        execute("INSERT INTO " + KEYSPACE + '.' + table + " (pk, v) VALUES (?, ?)", i, term(i));
    }

    @Test // U1 + U2: run with memtable_heap_space=512MiB
    public void testChargeAndFootprint() throws Throwable
    {
        Assume.assumeTrue(DatabaseDescriptor.getMemtableHeapSpaceInMiB() >= 512);
        String plain = createTable("CREATE TABLE %s (pk int PRIMARY KEY, v text)");
        String withSai = createTable("CREATE TABLE %s (pk int PRIMARY KEY, v text)");
        createIndex("CREATE INDEX ON %s(v) USING 'sai'");
        disableCompaction(KEYSPACE);
        ColumnFamilyStore cP = getColumnFamilyStore(KEYSPACE, plain), cS = getColumnFamilyStore(KEYSPACE, withSai);
        long p0 = owns(cP), s0 = owns(cS), f0 = cS.metric.memtableSwitchCount.getCount();
        for (int i = 0; i < N; i++) { insert(plain, i); insert(withSai, i); }
        StorageAttachedIndex idx = sai(cS);
        long S = idx.memtableIndexManager().estimatedMemIndexMemoryUsed();
        long W = idx.memtableIndexManager().liveMemtableWriteCount();
        long dP = owns(cP) - p0, dS = owns(cS) - s0;
        MemtableIndex mi = idx.memtableIndexManager().getLiveMemtableIndexesSnapshot().iterator().next();
        Field fm = MemtableIndex.class.getDeclaredField("memoryIndex"); fm.setAccessible(true);
        Field fd = TrieMemoryIndex.class.getDeclaredField("data"); fd.setAccessible(true);
        Object trie = fd.get(fm.get(mi));
        long D = ObjectSizes.measureDeep(trie), D2 = ObjectSizes.measureDeepOmitShared(trie);
        long K = ObjectSizes.measureDeep(idx.keyFactory());
        try (PrintWriter w = new PrintWriter(new FileWriter(OUT, true)))
        {
            w.println("U1U2,N,W,S,dS,dP,dS_minus_dP,D,D2,K,flushes");
            w.printf("U1U2,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d%n", N, W, S, dS, dP, dS - dP, D, D2, K,
                     cS.metric.memtableSwitchCount.getCount() - f0);
        }
    }

    private void capRun(boolean withIndex) throws Throwable
    {
        long L = DatabaseDescriptor.getMemtableHeapSpaceInMiB() << 20;
        Assume.assumeTrue(L <= (128L << 20));
        String t = createTable("CREATE TABLE %s (pk int PRIMARY KEY, v text)");
        if (withIndex) createIndex("CREATE INDEX ON %s(v) USING 'sai'");
        ColumnFamilyStore c = getColumnFamilyStore(KEYSPACE, t);
        StorageAttachedIndex idx = withIndex ? sai(c) : null;
        long maxP = 0, maxS = 0;
        try (PrintWriter w = new PrintWriter(new FileWriter(OUT, true)))
        {
            w.println("U3,withIndex,L,rows,poolUsed,ownsCurrent,S,flushes");
            for (int i = 0; i < N; i++)
            {
                insert(t, i);
                if (i % 5000 == 0 || i == N - 1)
                {
                    long P = AbstractAllocatorMemtable.MEMORY_POOL.onHeap.used();
                    long S = withIndex ? idx.memtableIndexManager().estimatedMemIndexMemoryUsed() : 0;
                    maxP = Math.max(maxP, P); maxS = Math.max(maxS, S);
                    w.printf("U3,%b,%d,%d,%d,%d,%d,%d%n", withIndex, L, i + 1, P, owns(c), S,
                             c.metric.memtableSwitchCount.getCount());
                }
            }
            w.printf("U3MAX,%b,%d,%d,%d,%d%n", withIndex, L, N, maxP, maxS);
        }
    }

    @Test public void testCapBindsSai() throws Throwable   { capRun(true); }
    @Test public void testCapBindsPlain() throws Throwable { capRun(false); }
}
