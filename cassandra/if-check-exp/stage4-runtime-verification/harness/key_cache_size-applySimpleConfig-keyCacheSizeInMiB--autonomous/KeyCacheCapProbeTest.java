/*
 * Stage 4, unit tier mechanism test (B2, amended 2026-10-25) of
 * key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous. Not upstream.
 * Copy into test/unit/org/apache/cassandra/probe/ of the run clone; one `ant testsome` (own JVM) per knob value, the knob set
 * by a `key_cache_size:` line appended to test/conf/cassandra.yaml (unit-run.sh):
 *   ant testsome -Dtest.name=org.apache.cassandra.probe.KeyCacheCapProbeTest
 *       -Dtest.jvm.args="-Xms1024m -Dstage4.out=<file> -Dstage4.label=<l>"
 * Order (B2e amendment): table, N inserts, flush, format check, clear key cache, calibration (reads 0..999),
 * main series (reads 1000..N-1, sample every 10,000), final, B2h control (clear, re-read the first floor(plateau/2) keys).
 */
package org.apache.cassandra.probe;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.Iterator;
import java.util.TreeMap;

import org.junit.Test;

import org.apache.cassandra.cache.InstrumentingCache;
import org.apache.cassandra.cache.KeyCacheKey;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.io.sstable.AbstractRowIndexEntry;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.schema.TableId;
import org.apache.cassandra.service.CacheService;

public class KeyCacheCapProbeTest extends CQLTester
{
    static final int N = 200_000;
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

    static InstrumentingCache<KeyCacheKey, AbstractRowIndexEntry> kc()
    {
        return CacheService.instance.keyCache;
    }

    static long own(TableId id)
    {
        long n = 0;
        Iterator<KeyCacheKey> it = kc().keyIterator();
        while (it.hasNext())
            if (it.next().tableId.equals(id))
                n++;
        return n;
    }

    static String state(TableId id)
    {
        return "size=" + kc().size() + " own=" + own(id) + " weightedSize=" + kc().weightedSize() + " capacity=" + kc().getCapacity()
               + " requests=" + kc().getMetrics().requests.getCount() + " hits=" + kc().getMetrics().hits.getCount()
               + " misses=" + kc().getMetrics().misses.getCount();
    }

    @Test
    public void run() throws Throwable
    {
        String label = System.getProperty("stage4.label", "x");
        Runtime r = Runtime.getRuntime();
        long mib = DatabaseDescriptor.getKeyCacheSizeInMiB();
        long autoFormula = Math.min(Math.max(1, (int) (r.totalMemory() * 0.05 / 1024 / 1024)), 100);
        line("STAGE4 run label=" + label + " keyCacheSizeInMiB=" + mib + " cap_bytes_expected=" + mib * 1024 * 1024
             + " capacity=" + kc().getCapacity() + " totalMemory=" + r.totalMemory() + " maxMemory=" + r.maxMemory()
             + " auto_formula_now=" + autoFormula + " selected_format=" + DatabaseDescriptor.getSelectedSSTableFormat().name()
             + " size_at_start=" + kc().size());

        createTable("CREATE TABLE %s (k int PRIMARY KEY, v int) WITH caching = {'keys':'ALL'}");
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        disableCompaction();
        TableId id = cfs.metadata().id;
        for (int i = 0; i < N; i++)
            execute("INSERT INTO %s (k, v) VALUES (?, ?)", i, i);
        flush();
        TreeMap<String, Integer> formats = new TreeMap<>();
        for (SSTableReader s : cfs.getLiveSSTables())
            formats.merge(s.descriptor.version.format.name() + "/" + s.descriptor.version.version + "/" + s.getClass().getSimpleName(), 1, Integer::sum);
        line("STAGE4 table label=" + label + " N=" + N + " sstables=" + cfs.getLiveSSTables().size() + " formats=" + formats
             + " caching_keys=" + cfs.metadata().params.caching.cacheKeys() + " memtable_rows_after_flush=" + cfs.getTracker().getView().getCurrentMemtable().operationCount());

        kc().clear();
        line("STAGE4 cleared label=" + label + " " + state(id));
        long req0 = kc().getMetrics().requests.getCount(), miss0 = kc().getMetrics().misses.getCount(), hit0 = kc().getMetrics().hits.getCount();

        // calibration: keys 0..999
        for (int i = 0; i < 1000; i++)
            execute("SELECT v FROM %s WHERE k = ?", i);
        long sz = kc().size(), ws = kc().weightedSize();
        double w = sz > 0 ? (double) ws / sz : Double.NaN;
        line("STAGE4 calibration label=" + label + " reads=1000 " + state(id) + " w=" + w);

        long maxWs = ws;
        long samples = 1;
        for (int i = 1000; i < N; i++)
        {
            execute("SELECT v FROM %s WHERE k = ?", i);
            if ((i + 1) % 10_000 == 0)
            {
                ws = kc().weightedSize();
                maxWs = Math.max(maxWs, ws);
                samples++;
                line("STAGE4 sample label=" + label + " reads=" + (i + 1) + " " + state(id));
            }
        }
        long sizeEnd = kc().size(), ownEnd = own(id), wsEnd = kc().weightedSize();
        long misses = kc().getMetrics().misses.getCount() - miss0, hits = kc().getMetrics().hits.getCount() - hit0,
             reqs = kc().getMetrics().requests.getCount() - req0;
        line("STAGE4 final label=" + label + " cap=" + kc().getCapacity() + " N=" + N + " w=" + w + " size=" + sizeEnd + " own=" + ownEnd
             + " weightedSize=" + wsEnd + " maxWeightedSizeOverSamples=" + maxWs + " samples=" + samples
             + " requests_delta=" + reqs + " hits_delta=" + hits + " misses_delta=" + misses
             + " evicted_inferred=" + (N - ownEnd));

        // B2h control: empty cache, re-read keys 0..M-1 with M = floor(own_end/2)
        long m = ownEnd / 2;
        kc().clear();
        for (int i = 0; i < m; i++)
            execute("SELECT v FROM %s WHERE k = ?", i);
        line("STAGE4 control label=" + label + " M=" + m + " " + state(id) + " expected_weight=" + (Double.isNaN(w) ? "n/a" : String.valueOf(m * w)));
        line("STAGE4 done label=" + label);
    }
}
