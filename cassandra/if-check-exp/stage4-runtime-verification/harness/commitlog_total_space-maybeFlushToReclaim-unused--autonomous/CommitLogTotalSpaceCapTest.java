/*
 * Stage-4 harness for commitlog_total_space-maybeFlushToReclaim-unused--autonomous (B2e, as amended 2026-10-21 R1-R2).
 * Copy to <clone>/test/unit/org/apache/cassandra/db/commitlog/. Parameters by environment variable:
 *   CLCAP_MIB (commitlog_total_space, MiB), CLCAP_SLEEP_MS (throttle per mutation), CLCAP_N (mutations), CLCAP_OUT (CSV path).
 * Changes from the filed B2e code: memtable_heap_space = 768 MiB (R1); a wall-clock column; SUMMARY built as one string
 * and also appended to $CLCAP_OUT.summary (R2). The workload, observables and sampling are as filed.
 */
package org.apache.cassandra.db.commitlog;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.ByteBuffer;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.db.marshal.AsciiType;
import org.apache.cassandra.db.marshal.BytesType;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.MemtableParams;

public class CommitLogTotalSpaceCapTest
{
    static final String KS = "CLCapKS", T = "t";
    static int env(String k, int d) { String v = System.getenv(k); return v == null ? d : Integer.parseInt(v); }

    @BeforeClass
    public static void setup()
    {
        KeyspaceParams.DEFAULT_LOCAL_DURABLE_WRITES = false;
        DatabaseDescriptor.daemonInitialization();
        Config c = DatabaseDescriptor.getRawConfig();
        c.memtable_cleanup_threshold = 0.99f;                                  // before MEMORY_POOL class-loads
        c.memtable_heap_space = new DataStorageSpec.IntMebibytesBound(768);     // R1: 1 GiB test heap -> default 256 MiB
        c.commitlog_total_space = new DataStorageSpec.IntMebibytesBound(env("CLCAP_MIB", 25));
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1),
            SchemaLoader.standardCFMD(KS, T, 0, AsciiType.instance, BytesType.instance).memtable(MemtableParams.get("skiplist")));
    }

    static long dirBytes()
    {
        long s = 0;
        File[] fs = new File(DatabaseDescriptor.getCommitLogLocation()).tryList();
        if (fs != null) for (File f : fs) s += f.length();
        return s;
    }

    @Test
    public void sweep() throws Exception
    {
        ColumnFamilyStore cfs = Keyspace.open(KS).getColumnFamilyStore(T);
        AbstractCommitLogSegmentManager mgr = CommitLog.instance.segmentManager;
        int n = env("CLCAP_N", 300), sleep = env("CLCAP_SLEEP_MS", 10);
        long cap = DatabaseDescriptor.getTotalCommitlogSpaceInMiB() << 20, peak = 0, peakDir = 0;
        String out = System.getenv().getOrDefault("CLCAP_OUT", "build/test/clcap.csv");
        String info = "INFO capMiB=" + (cap >> 20) + " segMiB=" + (DatabaseDescriptor.getCommitLogSegmentSize() >> 20)
                      + " heapMaxMiB=" + (Runtime.getRuntime().maxMemory() >> 20)
                      + " memtableHeapMiB=" + DatabaseDescriptor.getMemtableHeapSpaceInMiB()
                      + " cleanup=" + DatabaseDescriptor.getMemtableCleanupThreshold()
                      + " accessMode=" + DatabaseDescriptor.getCommitLogWriteDiskAccessMode()
                      + " startOnDisk=" + mgr.onDiskSize() + " startSwitches=" + cfs.metric.memtableSwitchCount.getCount();
        System.out.println(info);
        try (PrintWriter w = new PrintWriter(new FileWriter(out, true)))
        {
            w.println("capMiB,phase,i,tMs,onDiskSize,activeSegments,dirBytes,memtableSwitches");
            for (int i = 0; i < n + 10; i++)
            {
                String phase = i < n ? "write" : "settle";
                if (i < n)
                {
                    new RowUpdateBuilder(cfs.metadata(), 0, "k" + i).clustering("c")
                        .add("val", ByteBuffer.allocate(1 << 20)).build().apply();
                    if (sleep > 0) Thread.sleep(sleep);
                }
                else Thread.sleep(1000);
                long sz = mgr.onDiskSize(), d = dirBytes();
                peak = Math.max(peak, sz); peakDir = Math.max(peakDir, d);
                w.printf("%d,%s,%d,%d,%d,%d,%d,%d%n", cap >> 20, phase, i, System.currentTimeMillis(), sz,
                         mgr.getActiveSegments().size(), d, cfs.metric.memtableSwitchCount.getCount());
            }
        }
        String summary = String.format("SUMMARY capMiB=%d sleepMs=%d n=%d peakOnDisk=%d peakDir=%d final=%d finalDir=%d switches=%d",
                                       cap >> 20, sleep, n, peak, peakDir, mgr.onDiskSize(), dirBytes(),
                                       cfs.metric.memtableSwitchCount.getCount());
        System.out.println(summary);
        try (PrintWriter w = new PrintWriter(new FileWriter(out + ".summary", true)))
        {
            w.println(info);
            w.println(summary);
        }
    }
}
