/*
 * Stage 4, unit tier mechanism test (B2, amended 2026-10-25) of
 * paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous. Not upstream.
 * Modelled on harness/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous/CounterCacheCapProbeTest.java.
 * Copy into test/unit/org/apache/cassandra/probe/ of the run clone; one `ant testsome` (own JVM) per knob value, the knob set
 * by a `paxos_cache_size:` line appended to test/conf/cassandra.yaml (unit-run.sh):
 *   ant testsome -Dtest.name=org.apache.cassandra.probe.PaxosCacheCapProbeTest
 *       -Dtest.jvm.args="-Xms1024m -Dstage4.out=<file> -Dstage4.label=<l>"
 * Runbook fix R1 (2026-10-25): requireNetwork() first (token ring for StorageProxy.cas).
 * Order (B2e amendment): table, RECENT.clear(), calibration (LWT k = 0..99), main series (k = 100..N-1, sample every 1,000),
 * final, B2h control (a) (clear, M = floor(own/2) LWTs on fresh keys 1,000,000+), control (b) (clear, 50 LWTs on key 2,000,000).
 * Every LWT: QueryProcessor.process("INSERT INTO ks.tbl (k, v) VALUES (k, 0x<1,024 bytes of new Random(k)>) IF NOT EXISTS", QUORUM).
 */
package org.apache.cassandra.probe;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Map;
import java.util.Random;

import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.cql3.QueryProcessor;
import org.apache.cassandra.cql3.UntypedResultSet;
import org.apache.cassandra.db.ConsistencyLevel;
import org.apache.cassandra.schema.TableId;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.service.paxos.Paxos;
import org.apache.cassandra.service.paxos.PaxosState;
import org.apache.cassandra.utils.Hex;

public class PaxosCacheCapProbeTest extends CQLTester
{
    static final int N = 20_000;
    static final int CAL = 100;
    static PrintWriter out;
    static Field keyMetadata;
    static Method maximum, weightedSize;

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

    static Method find(Class<?> c, String name)
    {
        for (; c != null; c = c.getSuperclass())
        {
            try
            {
                Method m = c.getDeclaredMethod(name);
                m.setAccessible(true);
                return m;
            }
            catch (NoSuchMethodException e)
            {
                // continue with the superclass
            }
            catch (RuntimeException e)
            {
                return null;
            }
        }
        return null;
    }

    static String call(Method m)
    {
        if (m == null)
            return "n/a";
        try
        {
            return String.valueOf(m.invoke(PaxosState.RECENT));
        }
        catch (Exception e)
        {
            return "n/a(" + e.getClass().getSimpleName() + ")";
        }
    }

    static long weight(PaxosState.Snapshot v)
    {
        // the weigher formula of PaxosState.java:74, without the saturated cast (values are far below Integer.MAX_VALUE)
        return (v.accepted != null ? v.accepted.update.unsharedHeapSize() : 0L) + v.committed.update.unsharedHeapSize();
    }

    /** {own, ownWeight} over RECENT entries of table id */
    static long[] own(TableId id) throws Exception
    {
        long n = 0, w = 0;
        for (Map.Entry<PaxosState.Key, PaxosState.Snapshot> e : PaxosState.RECENT.entrySet())
        {
            TableMetadata md = (TableMetadata) keyMetadata.get(e.getKey());
            if (md.id.equals(id))
            {
                n++;
                w += weight(e.getValue());
            }
        }
        return new long[]{ n, w };
    }

    static String state(TableId id) throws Exception
    {
        long[] o = own(id);
        return "recentSize=" + PaxosState.RECENT.size() + " own=" + o[0] + " ownWeight=" + o[1] + " caffeineWeightedSize=" + call(weightedSize)
               + " active=" + PaxosState.ACTIVE.size();
    }

    String ks, tbl;

    boolean lwt(int k)
    {
        byte[] b = new byte[1024];
        new Random(k).nextBytes(b);
        UntypedResultSet rs = QueryProcessor.process("INSERT INTO " + ks + "." + tbl + " (k, v) VALUES (" + k + ", 0x" + Hex.bytesToHex(b) + ") IF NOT EXISTS",
                                                     ConsistencyLevel.QUORUM);
        return rs.one().getBoolean("[applied]");
    }

    @Test
    public void run() throws Throwable
    {
        String label = System.getProperty("stage4.label", "x");
        // runbook fix R1 (2026-10-25): a plain CQLTester has an empty token ring, so StorageProxy.cas fails in
        // ReplicaPlans.forPaxos (TokenMetadata.firstTokenIndex assertion); requireNetwork() runs StorageService.initServer()
        requireNetwork();
        keyMetadata = PaxosState.Key.class.getDeclaredField("metadata");
        keyMetadata.setAccessible(true);
        maximum = find(PaxosState.RECENT.getClass(), "maximum");
        weightedSize = find(PaxosState.RECENT.getClass(), "weightedSize");
        Runtime r = Runtime.getRuntime();
        long mib = DatabaseDescriptor.getPaxosCacheSizeInMiB();
        long autoFormula = Math.min(Math.max(1, (int) (r.totalMemory() * 0.01 / 1024 / 1024)), 50);
        line("STAGE4 run label=" + label + " paxosCacheSizeInMiB=" + mib + " cap_bytes_expected=" + (mib << 20)
             + " caffeineMaximum=" + call(maximum) + " recentClass=" + PaxosState.RECENT.getClass().getName()
             + " variant=" + Paxos.getPaxosVariant() + " useV2=" + Paxos.useV2() + " purging=" + DatabaseDescriptor.paxosStatePurging()
             + " totalMemory=" + r.totalMemory() + " maxMemory=" + r.maxMemory() + " auto_formula_now=" + autoFormula
             + " recentSize_at_start=" + PaxosState.RECENT.size());

        createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob)");
        ks = KEYSPACE;
        tbl = currentTable();
        TableId id = getCurrentColumnFamilyStore().metadata().id;

        long before = PaxosState.RECENT.size();
        PaxosState.RECENT.clear();
        line("STAGE4 cleared label=" + label + " table=" + ks + "." + tbl + " recentSize_before_clear=" + before + " " + state(id));

        long applied = 0, notApplied = 0;
        for (int k = 0; k < CAL; k++)
            if (lwt(k)) applied++; else notApplied++;
        long[] o = own(id);
        double w = o[0] > 0 ? (double) o[1] / o[0] : Double.NaN;
        line("STAGE4 calibration label=" + label + " lwts=" + CAL + " applied=" + applied + " " + state(id) + " w=" + w);

        long maxOwnWeight = o[1], maxActive = PaxosState.ACTIVE.size(), samples = 1;
        for (int k = CAL; k < N; k++)
        {
            if (lwt(k)) applied++; else notApplied++;
            if ((k + 1) % 1000 == 0)
            {
                o = own(id);
                maxOwnWeight = Math.max(maxOwnWeight, o[1]);
                maxActive = Math.max(maxActive, PaxosState.ACTIVE.size());
                samples++;
                line("STAGE4 sample label=" + label + " lwts=" + (k + 1) + " applied=" + applied + " " + state(id));
            }
        }
        o = own(id);
        long cap = mib << 20;
        line("STAGE4 final label=" + label + " cap=" + cap + " N=" + N + " applied=" + applied + " notApplied=" + notApplied + " w=" + w
             + " own=" + o[0] + " ownWeight=" + o[1] + " recentSize=" + PaxosState.RECENT.size() + " caffeineWeightedSize=" + call(weightedSize)
             + " maxOwnWeightOverSamples=" + maxOwnWeight + " maxActiveOverSamples=" + maxActive + " samples=" + samples
             + " floor_cap_over_w=" + (Double.isNaN(w) ? "n/a" : String.valueOf((long) Math.floor(cap / w)))
             + " evicted_inferred=" + (applied - o[0]));

        // B2h control (a): empty RECENT, M = floor(own_final/2) LWTs on fresh keys 1,000,000..
        long m = o[0] / 2, ca = 0;
        PaxosState.RECENT.clear();
        for (int j = 0; j < m; j++)
            if (lwt(1_000_000 + j)) ca++;
        line("STAGE4 controlA label=" + label + " M=" + m + " applied=" + ca + " " + state(id)
             + " expected_weight=" + (Double.isNaN(w) ? "n/a" : String.valueOf(Math.round(m * w))));

        // B2h control (b): empty RECENT, 50 LWTs on the one fresh key 2,000,000
        PaxosState.RECENT.clear();
        long cb = 0, cbn = 0;
        for (int j = 0; j < 50; j++)
            if (lwt(2_000_000)) cb++; else cbn++;
        line("STAGE4 controlB label=" + label + " lwts=50 applied=" + cb + " notApplied=" + cbn + " " + state(id));
        line("STAGE4 done label=" + label);
    }
}
