/*
 * Stage 4, unit tier mechanism test (B2, amended 2026-10-25) of
 * counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous. Not upstream.
 * Modelled on harness/key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous/KeyCacheCapProbeTest.java.
 * Copy into test/unit/org/apache/cassandra/probe/ of the run clone; one `ant testsome` (own JVM) per knob value, the knob set
 * by a `counter_cache_size:` line appended to test/conf/cassandra.yaml (unit-run.sh):
 *   ant testsome -Dtest.name=org.apache.cassandra.probe.CounterCacheCapProbeTest
 *       -Dtest.jvm.args="-Xms1024m -Dstage4.out=<file> -Dstage4.label=<l>"
 * Order (B2e amendment): table, clear counter cache, calibration (updates k = 0..999), main series (k = 1000..N-1, sample every
 * 10,000), final, B2h control (clear, re-update the first floor(own/2) keys).
 */
package org.apache.cassandra.probe;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.Iterator;

import org.junit.Test;

import org.apache.cassandra.cache.CounterCacheKey;
import org.apache.cassandra.cache.InstrumentingCache;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.ClockAndCount;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.schema.TableId;
import org.apache.cassandra.service.CacheService;

public class CounterCacheCapProbeTest extends CQLTester
{
    static final int N = 300_000;
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

    static InstrumentingCache<CounterCacheKey, ClockAndCount> cc()
    {
        return CacheService.instance.counterCache;
    }

    static long own(TableId id)
    {
        long n = 0;
        Iterator<CounterCacheKey> it = cc().keyIterator();
        while (it.hasNext())
            if (it.next().tableId.equals(id))
                n++;
        return n;
    }

    static String state(TableId id)
    {
        return "size=" + cc().size() + " own=" + own(id) + " weightedSize=" + cc().weightedSize() + " capacity=" + cc().getCapacity()
               + " requests=" + cc().getMetrics().requests.getCount() + " hits=" + cc().getMetrics().hits.getCount()
               + " misses=" + cc().getMetrics().misses.getCount();
    }

    @Test
    public void run() throws Throwable
    {
        String label = System.getProperty("stage4.label", "x");
        Runtime r = Runtime.getRuntime();
        long mib = DatabaseDescriptor.getCounterCacheSizeInMiB();
        long autoFormula = Math.min(Math.max(1, (int) (r.totalMemory() * 0.025 / 1024 / 1024)), 50);
        line("STAGE4 run label=" + label + " counterCacheSizeInMiB=" + mib + " cap_bytes_expected=" + mib * 1024 * 1024
             + " capacity=" + cc().getCapacity() + " totalMemory=" + r.totalMemory() + " maxMemory=" + r.maxMemory()
             + " auto_formula_now=" + autoFormula + " size_at_start=" + cc().size());

        createTable("CREATE TABLE %s (k int PRIMARY KEY, c counter)");
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        TableId id = cfs.metadata().id;

        long before = cc().size();
        cc().clear();
        line("STAGE4 cleared label=" + label + " size_before_clear=" + before + " " + state(id));
        long req0 = cc().getMetrics().requests.getCount(), miss0 = cc().getMetrics().misses.getCount(), hit0 = cc().getMetrics().hits.getCount();

        // calibration: keys 0..999
        for (int i = 0; i < 1000; i++)
            execute("UPDATE %s SET c = c + 1 WHERE k = ?", i);
        long sz = cc().size(), ws = cc().weightedSize();
        double w = sz > 0 ? (double) ws / sz : Double.NaN;
        line("STAGE4 calibration label=" + label + " updates=1000 " + state(id) + " w=" + w);

        long maxWs = ws;
        long samples = 1;
        for (int i = 1000; i < N; i++)
        {
            execute("UPDATE %s SET c = c + 1 WHERE k = ?", i);
            if ((i + 1) % 10_000 == 0)
            {
                ws = cc().weightedSize();
                maxWs = Math.max(maxWs, ws);
                samples++;
                line("STAGE4 sample label=" + label + " updates=" + (i + 1) + " " + state(id));
            }
        }
        long sizeEnd = cc().size(), ownEnd = own(id), wsEnd = cc().weightedSize();
        long misses = cc().getMetrics().misses.getCount() - miss0, hits = cc().getMetrics().hits.getCount() - hit0,
             reqs = cc().getMetrics().requests.getCount() - req0;
        line("STAGE4 final label=" + label + " cap=" + cc().getCapacity() + " N=" + N + " w=" + w + " size=" + sizeEnd + " own=" + ownEnd
             + " weightedSize=" + wsEnd + " maxWeightedSizeOverSamples=" + maxWs + " samples=" + samples
             + " requests_delta=" + reqs + " hits_delta=" + hits + " misses_delta=" + misses
             + " evicted_inferred=" + (N - ownEnd));

        // B2h control (a): empty cache, re-update keys 0..M-1 with M = floor(own_end/2)
        long m = ownEnd / 2;
        cc().clear();
        for (int i = 0; i < m; i++)
            execute("UPDATE %s SET c = c + 1 WHERE k = ?", i);
        line("STAGE4 control label=" + label + " M=" + m + " " + state(id) + " expected_weight=" + (Double.isNaN(w) ? "n/a" : String.valueOf(m * w)));
        line("STAGE4 done label=" + label);
    }
}
