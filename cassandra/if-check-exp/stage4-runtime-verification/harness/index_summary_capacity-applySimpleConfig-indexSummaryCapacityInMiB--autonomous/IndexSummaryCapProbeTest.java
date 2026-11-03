/*
 * Stage 4, unit tier mechanism test (B2, amended 2026-10-25) of
 * index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous. Not upstream.
 * Modelled on harness/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous/CounterCacheCapProbeTest.java.
 * Copy into test/unit/org/apache/cassandra/probe/ of the run clone; one `ant testsome` (own JVM) per startup value, the value
 * set by an `index_summary_capacity:` line appended to test/conf/cassandra.yaml (none = auto) by unit-run.sh:
 *   ant testsome -Dtest.name=org.apache.cassandra.probe.IndexSummaryCapProbeTest -Dtest.timeout=1800000
 *       -Dtest.jvm.args="-Xms1024m -Dstage4.out=<file> -Dstage4.label=<l>"
 * Order (B2e amendment): log knob, cancel scheduled resizing, table, disable compaction, load 10 M rows in 3 flushed batches,
 * 10,000 reads, wait 6 s, reading S0, control (a) (pool 1 MiB, no redistribution, 10 s), restore startup value, R0 at the
 * startup value, sweep C = 4, 2, 1, 0 MiB (set + redistributeSummaries), control (b) (C = 4, redistribute).
 * Harness change H2 (unit re-run, 2026-10-25), for the case-file amendment "after run 1, authorised by the user" (B2c-B2e):
 * after the last flush, wait 6 s and initialise every own read meter (one fifteenMinuteRate() call; rate and count logged, both
 * must be 0); then 100,000 reads of key(100 p + 50), p over 0..99,999 shuffled by Collections.shuffle(list, new Random(42));
 * read-phase duration logged; each own SSTable's rate and count() logged at every reading. Run 1 used the version in commit 4b93658.
 */
package org.apache.cassandra.probe;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Random;

import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.io.sstable.indexsummary.IndexSummary;
import org.apache.cassandra.io.sstable.indexsummary.IndexSummaryManager;
import org.apache.cassandra.io.sstable.indexsummary.IndexSummarySupport;
import org.apache.cassandra.io.util.Memory;

public class IndexSummaryCapProbeTest extends CQLTester
{
    static final int N = 10_000_000;
    static final int READS = 100_000;
    static PrintWriter out;

    static synchronized void line(String s)
    {
        System.out.println(s);
        try
        {
            if (out == null && System.getProperty("stage4.out") != null)
                out = new PrintWriter(new FileWriter(System.getProperty("stage4.out"), true), true);
        }
        catch (java.io.IOException e)
        {
            throw new RuntimeException(e);
        }
        if (out != null)
            out.println(s);
    }

    static String key(int i)
    {
        return String.format("k%031d", i);
    }

    static Field OFFSETS, ENTRIES;

    static long alloc(IndexSummary s) throws Exception
    {
        if (OFFSETS == null)
        {
            OFFSETS = IndexSummary.class.getDeclaredField("offsets");
            OFFSETS.setAccessible(true);
            ENTRIES = IndexSummary.class.getDeclaredField("entries");
            ENTRIES.setAccessible(true);
        }
        return ((Memory) OFFSETS.get(s)).size() + ((Memory) ENTRIES.get(s)).size();
    }

    static long totalAllKeyspaces()
    {
        long t = 0;
        for (Keyspace ks : Keyspace.all())
            for (ColumnFamilyStore c : ks.getColumnFamilyStores())
                for (SSTableReader r : c.getLiveSSTables())
                    if (r instanceof IndexSummarySupport)
                        t += ((IndexSummarySupport<?>) r).getIndexSummary().getOffHeapSize();
        return t;
    }

    String reading(String label, String tag, ColumnFamilyStore cfs, boolean rates) throws Exception
    {
        IndexSummaryManager<?> m = IndexSummaryManager.instance;
        long own = 0, ownAlloc = 0, maxEntries = 0, entries = 0, floorEntries = 0;
        int minLevel = Integer.MAX_VALUE, maxLevel = 0, k = 0, notSupported = 0;
        double sumInterval = 0, minRate = Double.MAX_VALUE, maxRate = 0;
        StringBuilder per = new StringBuilder();
        List<SSTableReader> live = new ArrayList<>(cfs.getLiveSSTables());
        for (SSTableReader r : live)
        {
            if (!(r instanceof IndexSummarySupport))
            {
                notSupported++;
                continue;
            }
            IndexSummary s = ((IndexSummarySupport<?>) r).getIndexSummary();
            k++;
            own += s.getOffHeapSize();
            ownAlloc += alloc(s);
            maxEntries += s.getMaxNumberOfEntries();
            entries += s.size();
            floorEntries += (long) Math.ceil(s.getMaxNumberOfEntries() / 16.0);
            minLevel = Math.min(minLevel, s.getSamplingLevel());
            maxLevel = Math.max(maxLevel, s.getSamplingLevel());
            sumInterval += s.getEffectiveIndexInterval();
            double rate = r.getReadMeter() == null ? -1 : r.getReadMeter().fifteenMinuteRate();
            long count = r.getReadMeter() == null ? -1 : r.getReadMeter().count();
            minRate = Math.min(minRate, rate);
            maxRate = Math.max(maxRate, rate);
            per.append(' ').append(r.descriptor.id).append(':').append(s.getMaxNumberOfEntries()).append('/').append(s.size())
               .append('@').append(s.getSamplingLevel());
            if (rates)
                per.append(String.format("r=%.6fc=%d", rate, count));
        }
        long total = totalAllKeyspaces();
        double poolMB = m.getMemoryPoolSizeInMB();
        String l = "STAGE4 reading label=" + label + " tag=" + tag
                   + " capacityMB=" + m.getMemoryPoolCapacityInMB()
                   + " total=" + total + " poolSizeMB_bytes=" + Math.round(poolMB * 1024 * 1024)
                   + " own=" + own + " ownAlloc=" + ownAlloc + " others=" + (total - own)
                   + " k=" + k + " notSupported=" + notSupported + " sumMaxEntries=" + maxEntries + " sumEntries=" + entries
                   + " floorEntries=" + floorEntries + " minLevel=" + minLevel + " maxLevel=" + maxLevel
                   + " meanInterval=" + (k > 0 ? sumInterval / k : Double.NaN)
                   + " avgIndexIntervalMBean=" + m.getAverageIndexInterval()
                   + " minRate=" + minRate + " maxRate=" + maxRate;
        line(l);
        line("STAGE4 per-sstable label=" + label + " tag=" + tag + per);
        return l;
    }

    @Test
    public void run() throws Throwable
    {
        String label = System.getProperty("stage4.label", "x");
        Runtime rt = Runtime.getRuntime();
        IndexSummaryManager<?> m = IndexSummaryManager.instance;
        long knob = DatabaseDescriptor.getIndexSummaryCapacityInMiB();
        long autoFormula = Math.max(1, (int) (rt.totalMemory() * 0.05 / 1024 / 1024));
        long startup = m.getMemoryPoolCapacityInMB();
        line("STAGE4 run label=" + label + " indexSummaryCapacityInMiB=" + knob + " managerCapacityMB=" + startup
             + " totalMemory=" + rt.totalMemory() + " maxMemory=" + rt.maxMemory() + " auto_formula_now=" + autoFormula
             + " format=" + DatabaseDescriptor.getSelectedSSTableFormat().name()
             + " resizeIntervalMin=" + m.getResizeIntervalInMinutes()
             + " settings_index_summary_capacity=" + DatabaseDescriptor.getRawConfig().index_summary_capacity);
        m.setResizeIntervalInMinutes(-1);
        line("STAGE4 resize-interval label=" + label + " now=" + m.getResizeIntervalInMinutes());

        createTable("CREATE TABLE %s (k text PRIMARY KEY, v int) WITH min_index_interval = 128 AND max_index_interval = 2048");
        disableCompaction();
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();

        int[] bounds = { 0, 3_333_334, 6_666_667, N };
        long t0 = System.currentTimeMillis();
        for (int b = 0; b < 3; b++)
        {
            for (int i = bounds[b]; i < bounds[b + 1]; i++)
                execute("INSERT INTO %s (k, v) VALUES (?, ?)", key(i), i);
            flush();
            line("STAGE4 batch label=" + label + " batch=" + b + " upTo=" + bounds[b + 1] + " liveSSTables=" + cfs.getLiveSSTables().size()
                 + " secs=" + (System.currentTimeMillis() - t0) / 1000);
        }

        // amended B2c (1): initialise every own read meter before the reads
        Thread.sleep(6000);
        StringBuilder init = new StringBuilder();
        double initMaxRate = 0;
        long initMaxCount = 0;
        int initK = 0;
        for (SSTableReader r : cfs.getLiveSSTables())
        {
            double rate = r.getReadMeter() == null ? -1 : r.getReadMeter().fifteenMinuteRate();
            long count = r.getReadMeter() == null ? -1 : r.getReadMeter().count();
            initK++;
            initMaxRate = Math.max(initMaxRate, Math.abs(rate));
            initMaxCount = Math.max(initMaxCount, Math.abs(count));
            init.append(' ').append(r.descriptor.id).append(":r=").append(rate).append("c=").append(count);
        }
        line("STAGE4 meter-init label=" + label + " k=" + initK + " maxAbsRate=" + initMaxRate + " maxAbsCount=" + initMaxCount + init);

        // amended B2c (2): every 100th key once, in shuffled order
        List<Integer> order = new ArrayList<>(READS);
        for (int p = 0; p < READS; p++)
            order.add(p);
        Collections.shuffle(order, new Random(42));
        int found = 0;
        long r0 = System.nanoTime();
        for (int p : order)
            found += execute("SELECT v FROM %s WHERE k = ?", key(100 * p + 50)).size();
        long readMs = (System.nanoTime() - r0) / 1_000_000;
        line("STAGE4 reads label=" + label + " reads=" + READS + " found=" + found + " readPhaseMs=" + readMs);
        Thread.sleep(6000);

        reading(label, "S0", cfs, true);

        // control (a): pool 1 MiB, no redistribution, 10 s
        m.setMemoryPoolCapacityInMB(1);
        Thread.sleep(10_000);
        reading(label, "controlA-1MiB-noRedistribute", cfs, true);
        m.setMemoryPoolCapacityInMB(startup);

        // R0 at the startup value
        m.redistributeSummaries();
        reading(label, "R0-startup-" + startup, cfs, true);

        for (long c : new long[]{ 4, 2, 1, 0 })
        {
            m.setMemoryPoolCapacityInMB(c);
            m.redistributeSummaries();
            reading(label, "C" + c, cfs, true);
        }

        // control (b): back to 4 MiB
        m.setMemoryPoolCapacityInMB(4);
        m.redistributeSummaries();
        reading(label, "controlB-C4-after-C0", cfs, true);
        line("STAGE4 done label=" + label);
    }
}
