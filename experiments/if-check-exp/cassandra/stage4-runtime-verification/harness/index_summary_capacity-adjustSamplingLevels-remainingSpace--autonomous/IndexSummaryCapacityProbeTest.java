package org.apache.cassandra.io.sstable.indexsummary;

// Stage-4 harness, case index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous, unit tier (B2).
// The case file's B2e test with audit amendments R1 (whole PROBE lines to -Dprobe.out), R2 (reset with read meters 100)
// and R3 (exact operand prediction R = P - N*F'). Reads remainingSpace as it stands at IndexSummaryRedistribution.java:258
// by two readers: reflection on the field, and memoryPoolBytes - getCompactionInfo().getCompleted() (:360).

import java.io.IOException;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Arrays;
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
import org.apache.cassandra.db.compaction.CompactionManager;
import org.apache.cassandra.db.compaction.OperationType;
import org.apache.cassandra.db.lifecycle.LifecycleTransaction;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.metrics.RestorableMeter;
import org.apache.cassandra.schema.CachingParams;
import org.apache.cassandra.schema.KeyspaceParams;

import static org.apache.cassandra.io.sstable.Downsampling.BASE_SAMPLING_LEVEL;

public class IndexSummaryCapacityProbeTest<R extends SSTableReader & IndexSummarySupport<R>>
{
    static final String KS = "ISRProbe", CF = "T";
    static final int N = 10;                                                        // B2b
    static final int NUM_PARTITIONS = Integer.getInteger("probe.partitions", 10000); // B2c; != 10000 is a shakedown only
    static final int MIN_II = 8, MAX_II = 256;

    @BeforeClass
    public static void defineSchema()
    {
        DatabaseDescriptor.daemonInitialization();
        Assume.assumeTrue(IndexSummarySupport.isSupportedBy(DatabaseDescriptor.getSelectedSSTableFormat()));
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1),
                                    SchemaLoader.standardCFMD(KS, CF).minIndexInterval(MIN_II).maxIndexInterval(MAX_II)
                                                .caching(CachingParams.CACHE_NOTHING));
        IndexSummaryManager.instance.setResizeIntervalInMinutes(-1); // no background run
    }

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

    String sizes(List<R> l)
    {
        StringBuilder b = new StringBuilder(); for (R r : l) b.append(r.getIndexSummary().getOffHeapSize()).append(','); return b.toString();
    }

    void rates(double v) { for (R r : live()) r.overrideReadMeter(new RestorableMeter(v, v)); }

    static long operandReflect(IndexSummaryRedistribution r) throws Exception
    {
        Field f = IndexSummaryRedistribution.class.getDeclaredField("remainingSpace");
        f.setAccessible(true);
        return f.getLong(r);
    }

    /** Runs one redistribution of all live sstables with nonRedistributing = 0 and the given pool; returns the object. */
    IndexSummaryRedistribution redistribute(long pool) throws IOException
    {
        ColumnFamilyStore cfs = cfs();
        List<R> l = live();
        Assert.assertEquals(N, l.size());                                               // B2h same data
        Assert.assertTrue(CompactionManager.instance.active.getCompactions().isEmpty()); // B2h clean slate
        try (LifecycleTransaction txn = cfs.getTracker().tryModify(l, OperationType.UNKNOWN))
        {
            IndexSummaryRedistribution r = new IndexSummaryRedistribution(ImmutableMap.of(cfs.metadata.id, txn), 0L, pool);
            IndexSummaryManager.redistributeSummaries(r);
            return r;
        }
    }

    void resetToFull(long sFull) throws IOException
    {
        rates(100.0);                    // R2: zero rates cannot upsample (:183-188, :235)
        redistribute(10 * sFull);        // B2c step 1: pool = 10*N*S
        for (R x : live()) Assert.assertEquals(BASE_SAMPLING_LEVEL, x.getIndexSummary().getSamplingLevel());
    }

    @Test
    public void probe() throws Exception
    {
        ColumnFamilyStore cfs = cfs();
        cfs.truncateBlocking(); cfs.disableAutoCompaction();
        ByteBuffer v = ByteBuffer.wrap(new byte[100]);
        for (int s = 0; s < N; s++)
        {
            for (int p = 0; p < NUM_PARTITIONS; p++)
                new RowUpdateBuilder(cfs.metadata(), 0, String.format("%08d", p))
                    .clustering("column").add("val", v).build().applyUnsafe();
            cfs.forceBlockingFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS);
        }
        List<R> l = live();
        Assert.assertEquals(N, l.size());
        for (R x : l) Assert.assertEquals(BASE_SAMPLING_LEVEL, x.getIndexSummary().getSamplingLevel());
        long sFull = total(l);
        IndexSummary is = l.get(0).getIndexSummary();
        long S = is.getOffHeapSize();
        for (R x : l) Assert.assertEquals(S, x.getIndexSummary().getOffHeapSize());
        int entries = is.size(), maxEntries = is.getMaxNumberOfEntries();
        int minLevel = (int) Math.ceil(BASE_SAMPLING_LEVEL * MIN_II / (double) MAX_II);
        double avgEntrySize = S / (double) entries;                                   // as :186
        int floorEntries = IndexSummaryBuilder.entriesAtSamplingLevel(minLevel, maxEntries);
        long Fp = (long) Math.ceil(avgEntrySize * floorEntries);                       // as :244
        out("PROBE setup N=%d partitions=%d S=%d sFull=%d entries=%d maxEntries=%d minLevel=%d floorEntries=%d Fp=%d%n",
            N, NUM_PARTITIONS, S, sFull, entries, maxEntries, minLevel, floorEntries, Fp);

        // B2e step 3: pool = 0 measures F
        rates(0.0);
        IndexSummaryRedistribution r0 = redistribute(0);
        l = live();
        long F = l.get(0).getIndexSummary().getOffHeapSize();
        for (R x : l) Assert.assertEquals(F, x.getIndexSummary().getOffHeapSize());
        out("PROBE floor P=0 R_refl=%d R_compl=%d Rpred=%d T=%d F=%d floorEntriesActual=%d levels=%s%n",
            operandReflect(r0), 0 - r0.getCompactionInfo().getCompleted(), -N * Fp, total(l), F, l.get(0).getIndexSummary().size(), levels(l));

        long d = S - Fp;
        long[] pools = { N * F / 2,                     // P0
                         N * F + (S - F) / 2,           // P1
                         N * F + 7 * (S - F) / 2,       // P2
                         N * F + 15 * (S - F) / 2,      // P3
                         N * S + 1024 };                // P4
        for (int i = 0; i < pools.length; i++)
        {
            long P = pools[i];
            resetToFull(sFull);
            long tBefore = total(live());
            rates(0.0);                                  // B2c step 2
            IndexSummaryRedistribution r = redistribute(P);
            l = live();
            long T = total(l);
            int k = 0; for (R x : l) if (x.getIndexSummary().getSamplingLevel() == BASE_SAMPLING_LEVEL) k++;
            long rRefl = operandReflect(r), rCompl = P - r.getCompactionInfo().getCompleted();
            long rPred = P - N * Fp;
            long kPred = rPred > 0 ? Math.min(N, rPred / d) : 0;
            long tPred = kPred * S + (N - kPred) * F;
            out("PROBE P%d P=%d tBefore=%d R_refl=%d R_compl=%d Rpred=%d branch=%b k=%d kPred=%d T=%d Tpred=%d T<=P=%b levels=%s sizes=%s%n",
                i, P, tBefore, rRefl, rCompl, rPred, rRefl > 0, k, kPred, T, tPred, T <= P, levels(l), sizes(l));
        }
        out("PROBE done%n");
    }
}
