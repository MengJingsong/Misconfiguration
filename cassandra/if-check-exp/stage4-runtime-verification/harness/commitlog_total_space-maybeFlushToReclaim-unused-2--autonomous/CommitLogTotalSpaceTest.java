/*
 * Stage-4 harness for commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous: B2e as filed, with audit amendments
 * R1, R2 and R5 (2026-10-21). Copy to <clone>/test/unit/org/apache/cassandra/db/commitlog/ together with CLCapTrace.java.
 * System properties (passed with -Dtest.jvm.args):
 *   clcap.totalMiB (T, default 4), clcap.sleepMs (default 20), clcap.n (default 256), clcap.mode (single | M),
 *   clcap.nobreak (true: the B2i M-nobreak rule disables the test at line 259), clcap.out (CSV path).
 * Changes from the filed skeleton: the 1-ms sampler and the settle wait are written out; the SUMMARY goes to <out>.summary
 * as well (R2); mode M writes 24 tables M00..M23 in blocks of 15 mutations (R5); four Byteman rules (R5): three observation
 * rules (CHECK, SELECT, FLUSH) and the M-nobreak rule, which acts only when clcap.nobreak=true.
 */
package org.apache.cassandra.db.commitlog;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

import org.junit.Test;
import org.junit.runner.RunWith;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.Util;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.db.compaction.CompactionManager;
import org.apache.cassandra.db.marshal.AsciiType;
import org.apache.cassandra.db.marshal.BytesType;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.TableMetadata;
import org.jboss.byteman.contrib.bmunit.BMRule;
import org.jboss.byteman.contrib.bmunit.BMRules;
import org.jboss.byteman.contrib.bmunit.BMUnitRunner;

@RunWith(BMUnitRunner.class)
public class CommitLogTotalSpaceTest
{
    static final String KS = "CLCap";
    static volatile String phase = "setup";

    static long dirBytes()
    {
        long s = 0;
        File[] fs = new File(DatabaseDescriptor.getCommitLogLocation()).tryList();
        if (fs != null) for (File f : fs) if (f.name().endsWith(".log")) s += f.length();
        return s;
    }

    @Test
    @BMRules(rules = {
        @BMRule(name = "clcap check",
                targetClass = "AbstractCommitLogSegmentManager", targetMethod = "maybeFlushToReclaim",
                targetLocation = "AT ENTRY",
                action = "org.apache.cassandra.db.commitlog.CLCapTrace.check($0, $0.allocatingFrom)"),
        @BMRule(name = "clcap select",
                targetClass = "AbstractCommitLogSegmentManager", targetMethod = "maybeFlushToReclaim",
                targetLocation = "AT INVOKE flushDataFrom",
                action = "org.apache.cassandra.db.commitlog.CLCapTrace.select($0, $unused, $flushingSize, $segmentsToRecycle, $0.allocatingFrom)"),
        @BMRule(name = "clcap nobreak",
                targetClass = "AbstractCommitLogSegmentManager", targetMethod = "maybeFlushToReclaim",
                targetLocation = "AT LINE 259",
                condition = "Boolean.getBoolean(\"clcap.nobreak\")",
                action = "$flushingSize = Long.MIN_VALUE / 2"),
        @BMRule(name = "clcap flush",
                targetClass = "org.apache.cassandra.db.ColumnFamilyStore",
                targetMethod = "forceFlush(org.apache.cassandra.db.commitlog.CommitLogPosition)",
                targetLocation = "AT ENTRY",
                condition = "callerEquals(\"flushDataFrom\")",
                action = "org.apache.cassandra.db.commitlog.CLCapTrace.flush($0, $1)")
    })
    public void totalSpace() throws Throwable
    {
        int totalMiB = Integer.getInteger("clcap.totalMiB", 4);
        int sleep = Integer.getInteger("clcap.sleepMs", 20);
        int n = Integer.getInteger("clcap.n", 256);
        String mode = System.getProperty("clcap.mode", "single");
        boolean nobreak = Boolean.getBoolean("clcap.nobreak");
        String out = System.getProperty("clcap.out", "build/test/clcap.csv");

        DatabaseDescriptor.daemonInitialization();
        DatabaseDescriptor.setCommitLogSegmentSize(1);
        DatabaseDescriptor.getRawConfig().commitlog_total_space = new DataStorageSpec.IntMebibytesBound(totalMiB);
        DatabaseDescriptor.initializeCommitLogDiskAccessMode();
        SchemaLoader.prepareServer();

        List<TableMetadata.Builder> tables = new ArrayList<>();
        List<String> names = new ArrayList<>();
        if (mode.equals("M"))
            for (int t = 0; t < 24; t++)
                names.add(String.format("M%02d", t));
        else
            names.add("Standard1");
        for (String nm : names)
            tables.add(SchemaLoader.standardCFMD(KS, nm, 0, AsciiType.instance, BytesType.instance));
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1), tables.toArray(new TableMetadata.Builder[0]));
        CompactionManager.instance.disableAutoCompaction();

        List<ColumnFamilyStore> cfss = new ArrayList<>();
        for (String nm : names)
            cfss.add(Keyspace.open(KS).getColumnFamilyStore(nm));

        Util.flush(Keyspace.open("system"));
        Util.flush(Keyspace.open("system_schema"));
        CommitLog.instance.forceRecycleAllSegments();          // start from 1 active segment
        AbstractCommitLogSegmentManager clsm = CommitLog.instance.segmentManager;

        long switches0 = 0;
        for (ColumnFamilyStore c : cfss) switches0 += c.metric.memtableSwitchCount.getCount();

        String info = "INFO totalMiB=" + DatabaseDescriptor.getTotalCommitlogSpaceInMiB()
                      + " segMiB=" + (DatabaseDescriptor.getCommitLogSegmentSize() >> 20)
                      + " sleepMs=" + sleep + " n=" + n + " mode=" + mode + " nobreak=" + nobreak
                      + " heapMaxMiB=" + (Runtime.getRuntime().maxMemory() >> 20)
                      + " memtableHeapMiB=" + DatabaseDescriptor.getMemtableHeapSpaceInMiB()
                      + " accessMode=" + DatabaseDescriptor.getCommitLogWriteDiskAccessMode()
                      + " startOnDisk=" + clsm.onDiskSize() + " startActive=" + clsm.getActiveSegments().size()
                      + " tables=" + cfss.size();
        System.out.println(info);

        // sampler: every 1 ms
        final long[] peak = new long[2];
        final List<ColumnFamilyStore> cf = cfss;
        PrintWriter csv = new PrintWriter(new FileWriter(out, true));
        csv.println("tMs,phase,onDiskSize,activeSegments,dirBytes,memtableSwitches");
        Thread sampler = new Thread(() -> {
            while (!Thread.currentThread().isInterrupted())
            {
                long sz = clsm.onDiskSize(), d = dirBytes(), sw = 0;
                for (ColumnFamilyStore c : cf) sw += c.metric.memtableSwitchCount.getCount();
                synchronized (peak) { peak[0] = Math.max(peak[0], sz); peak[1] = Math.max(peak[1], d); }
                csv.println(System.currentTimeMillis() + "," + phase + "," + sz + "," + clsm.getActiveSegments().size() + "," + d + "," + sw);
                try { Thread.sleep(1); } catch (InterruptedException e) { break; }
            }
        }, "clcap-sampler");
        sampler.setDaemon(true);
        sampler.start();

        phase = "write";
        byte[] v = new byte[64 * 1024];
        for (int i = 0; i < n; i++)
        {
            new Random(i).nextBytes(v);
            ColumnFamilyStore c = mode.equals("M") ? cfss.get(i / 15) : cfss.get(0);
            new RowUpdateBuilder(c.metadata(), 0, "k" + i).clustering("c")
                .add("val", ByteBuffer.wrap(v)).build().apply();
            if (sleep > 0) Thread.sleep(sleep);
        }

        // settle: up to 10 s, until no pending flush and the size is unchanged for 500 ms
        phase = "settle";
        long deadline = System.currentTimeMillis() + 10_000, last = -1, stableSince = System.currentTimeMillis();
        while (System.currentTimeMillis() < deadline)
        {
            long pending = 0;
            for (ColumnFamilyStore c : cfss) pending += c.metric.pendingFlushes.getCount();
            long sz = clsm.onDiskSize();
            if (sz != last) { last = sz; stableSince = System.currentTimeMillis(); }
            if (pending == 0 && System.currentTimeMillis() - stableSince >= 500) break;
            Thread.sleep(10);
        }
        Thread.sleep(20);
        sampler.interrupt();
        sampler.join(1000);
        csv.close();

        long switches = 0;
        for (ColumnFamilyStore c : cfss) switches += c.metric.memtableSwitchCount.getCount();
        String summary;
        synchronized (peak)
        {
            summary = "SUMMARY totalMiB=" + totalMiB + " sleepMs=" + sleep + " mode=" + mode + " nobreak=" + nobreak
                      + " peakOnDisk=" + peak[0] + " peakDir=" + peak[1]
                      + " settledOnDisk=" + clsm.onDiskSize() + " settledDir=" + dirBytes()
                      + " switches=" + (switches - switches0);
        }
        System.out.println(summary);
        try (PrintWriter w = new PrintWriter(new FileWriter(out + ".summary", true)))
        {
            w.println(info);
            w.println(summary);
        }
    }
}
