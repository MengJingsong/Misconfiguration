package org.apache.cassandra.io.sstable.indexsummary;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

import com.google.common.collect.ImmutableMap;
import org.junit.Assert;
import org.junit.Assume;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.ServerTestUtils;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.db.compaction.OperationType;
import org.apache.cassandra.db.lifecycle.LifecycleTransaction;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.metrics.RestorableMeter;
import org.apache.cassandra.schema.CachingParams;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.SchemaTestUtil;

import static org.apache.cassandra.io.sstable.Downsampling.BASE_SAMPLING_LEVEL;

public class IndexSummaryCapacityProbeTest<R extends SSTableReader & IndexSummarySupport<R>>
{
    static final String KS = "ISCProbe", CF = "Probe";
    static final int NUM_SSTABLES = 8, NUM_PARTITIONS = Integer.getInteger("probe.partitions", 2048); // stage-4 R1: override for the shakedown only

    @BeforeClass
    public static void defineSchema()
    {
        DatabaseDescriptor.daemonInitialization();
        Assume.assumeTrue(IndexSummarySupport.isSupportedBy(DatabaseDescriptor.getSelectedSSTableFormat()));
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1),
                                    SchemaLoader.standardCFMD(KS, CF).minIndexInterval(8).maxIndexInterval(256)
                                                .caching(CachingParams.CACHE_NOTHING));
        IndexSummaryManager.instance.setResizeIntervalInMinutes(-1); // no background run
    }

    // stage-4 amendment R1 (instrument only): format each PROBE line once, print it, and append it whole to -Dprobe.out
    static void out(String fmt, Object... args)
    {
        String line = String.format(fmt, args);
        System.out.print(line);
        String f = System.getProperty("probe.out");
        if (f != null)
        {
            try { java.nio.file.Files.write(java.nio.file.Paths.get(f), line.getBytes(java.nio.charset.StandardCharsets.UTF_8),
                                            java.nio.file.StandardOpenOption.CREATE, java.nio.file.StandardOpenOption.APPEND); }
            catch (IOException e) { throw new RuntimeException(e); }
        }
    }

    ColumnFamilyStore cfs() { return Keyspace.open(KS).getColumnFamilyStore(CF); }

    List<R> live()
    {
        List<R> l = new ArrayList<>(ServerTestUtils.<R>getLiveIndexSummarySupportingReaders(cfs()));
        l.sort(Comparator.comparing(SSTableReader::getFilename));
        return l;
    }

    static long total(List<? extends IndexSummarySupport<?>> l)
    {
        long t = 0; for (IndexSummarySupport<?> r : l) t += r.getIndexSummary().getOffHeapSize(); return t;
    }

    String levels(List<R> l)
    {
        StringBuilder b = new StringBuilder(); for (R r : l) b.append(r.getIndexSummary().getSamplingLevel()).append(','); return b.toString();
    }

    void rates(double... r) { List<R> l = live(); for (int i = 0; i < l.size(); i++) l.get(i).overrideReadMeter(new RestorableMeter(r[i], r[i])); }

    void redistribute(long pool) throws IOException
    {
        ColumnFamilyStore cfs = cfs();
        try (LifecycleTransaction txn = cfs.getTracker().tryModify(live(), OperationType.UNKNOWN))
        {
            IndexSummaryManager.redistributeSummaries(new IndexSummaryRedistribution(ImmutableMap.of(cfs.metadata.id, txn), 0L, pool));
        }
    }

    void resetToFull(long sFull) throws IOException
    {
        double[] r = new double[NUM_SSTABLES]; java.util.Arrays.fill(r, 100.0); rates(r);
        redistribute(4 * sFull);
        for (R x : live()) Assert.assertEquals(BASE_SAMPLING_LEVEL, x.getIndexSummary().getSamplingLevel());
    }

    @Test
    public void probe() throws IOException
    {
        ColumnFamilyStore cfs = cfs();
        cfs.truncateBlocking(); cfs.disableAutoCompaction();
        ByteBuffer v = ByteBuffer.wrap(new byte[100]);
        for (int s = 0; s < NUM_SSTABLES; s++)
        {
            for (int p = 0; p < NUM_PARTITIONS; p++)
                new RowUpdateBuilder(cfs.metadata(), 0, String.format("%08d", s * NUM_PARTITIONS + p))
                    .clustering("column").add("val", v).build().applyUnsafe();
            cfs.forceBlockingFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS);
        }
        List<R> l = live();
        Assert.assertEquals(NUM_SSTABLES, l.size());
        long sFull = total(l);
        long s = l.get(0).getIndexSummary().getOffHeapSize();
        IndexSummary is = l.get(0).getIndexSummary();
        int effMin = (int) Math.ceil(BASE_SAMPLING_LEVEL * 8 / 256.0);
        long mPred = (long) Math.ceil((s / (double) is.size()) * Math.ceil(effMin * is.getMaxNumberOfEntries() / (double) BASE_SAMPLING_LEVEL));
        long F = NUM_SSTABLES * mPred, d = s - mPred;
        out("PROBE setup sFull=%d s=%d mPred=%d F=%d d=%d%n", sFull, s, mPred, F, d);

        // Scenario A: zero read rates -> every keep decision is made at IndexSummaryRedistribution.java:341
        long[] pools = { 0, F - 1, F, F + d - 1, F + d, F + 3 * d - 1, F + 3 * d, F + 7 * d, F + 8 * d - 1, F + 8 * d, 2 * sFull };
        for (long P : pools)
        {
            resetToFull(sFull);
            rates(new double[NUM_SSTABLES]);
            redistribute(P);
            l = live();
            long T = total(l);
            int kept = 0; for (R x : l) if (x.getIndexSummary().getSamplingLevel() == BASE_SAMPLING_LEVEL) kept++;
            long kPred = P <= F ? 0 : Math.min(NUM_SSTABLES, (P - F) / d);
            out("PROBE A P=%d T=%d kept=%d kPred=%d Tpred=%d T<=P=%b levels=%s%n",
                              P, T, kept, kPred, F + kPred * d, T <= P, levels(l));
        }

        // Scenario B: proportional read rates
        for (long P : new long[]{ sFull / 2, sFull / 4, sFull / 8, F })
        {
            resetToFull(sFull);
            rates(10, 20, 30, 40, 50, 60, 70, 80);
            redistribute(P);
            l = live();
            long T = total(l);
            out("PROBE B P=%d T=%d slackBound=%d T<=P=%b levels=%s%n", P, T, P + s / 4 + F, T <= P, levels(l));
        }

        // Control: floor equals full (max_index_interval == min_index_interval) -> cap cannot bind
        SchemaTestUtil.announceTableUpdate(cfs.metadata().unbuild().maxIndexInterval(8).build());
        resetToFull(sFull);
        rates(new double[NUM_SSTABLES]);
        redistribute(sFull / 4);
        l = live();
        out("PROBE C floor P=%d T=%d levels=%s%n", sFull / 4, total(l), levels(l));
        SchemaTestUtil.announceTableUpdate(cfs.metadata().unbuild().maxIndexInterval(256).build());
    }
}
