package org.apache.cassandra.locator;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.net.InetAddress;
import java.util.ArrayList;
import java.util.List;

import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.guardrails.Guardrails;
import org.apache.cassandra.dht.Murmur3Partitioner.LongToken;
import org.apache.cassandra.dht.Range;
import org.apache.cassandra.dht.Token;
import org.apache.cassandra.exceptions.InvalidRequestException;
import org.apache.cassandra.locator.AbstractReplicaCollection.ReplicaList;
import org.apache.cassandra.utils.ObjectSizes;

/**
 * Stage 4, unit tier (B2) of maximum_replication_factor-ReplicaList.add-newSize--autonomous (case file as amended 2026-10-26).
 * Package org.apache.cassandra.locator because ReplicaList is protected and its fields are package-private.
 * Output: lines "STAGE4 reading ..." and "STAGE4 check <name> ok|MISMATCH <detail>" to -Dstage4.out (and stdout).
 * Expected values are computed here by code independent of ReplicaList (expCap/expReallocs) and also given as literals from the
 * amended B2f/B2c (N=10 -> 18, N=100 -> 144, N=10_000 -> 18432 with 13 reallocations, N=1_000_000 -> 1,179,648).
 */
public class ReplicaListGrowthTest
{
    static PrintWriter out;
    static int checks = 0, bad = 0;
    static final long[] NS = { 1, 2, 3, 4, 9, 10, 100, 10_000, 1_000_000 };

    @BeforeClass
    public static void init() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        String f = System.getProperty("stage4.out");
        out = new PrintWriter(new FileWriter(f != null ? f : "/dev/null", false), true);
    }

    static void say(String s) { System.out.println(s); out.println(s); }

    static void check(String name, boolean ok, String detail)
    {
        checks++;
        if (!ok) bad++;
        say("STAGE4 check " + name + (ok ? " ok " : " MISMATCH ") + detail);
    }

    static long expCap(long n)
    {
        if (n == 0) return 0;
        if (n <= 3) return 3;
        if (n <= 9) return 9;
        long c = 9;
        while (c < n) c *= 2;
        return c;
    }

    static int expReallocs(long n)
    {
        if (n == 0) return 0;
        if (n <= 3) return 1;
        if (n <= 9) return 2;
        int r = 2;
        long c = 9;
        while (c < n) { c *= 2; r++; }
        return r;
    }

    static final Range<Token> RANGE = new Range<>(new LongToken(0), new LongToken(1000));
    static Replica replica() throws Exception
    {
        return Replica.fullReplica(InetAddressAndPort.getByAddress(InetAddress.getByAddress(new byte[]{ 127, 0, 0, 1 })), RANGE);
    }

    /** returns {size, contents.length, reallocations, bytes, meterBytes}; keeps the list in 'keep' when non-null */
    static long[] fill(long n, int initCap, List<ReplicaList> keep) throws Exception
    {
        Replica r = replica();
        ReplicaList l = new ReplicaList(initCap);
        Object prev = l.contents;
        int reallocs = 0;
        for (long i = 0; i < n; i++)
        {
            l.add(r);
            if (l.contents != prev) { reallocs++; prev = l.contents; }
        }
        long bytes = ObjectSizes.sizeOfReferenceArray(l.contents.length);
        long meter = ObjectSizes.measure(l.contents);
        if (keep != null) keep.add(l);
        return new long[]{ l.size, l.contents.length, reallocs, bytes, meter };
    }

    static String show(long[] a) { return "size=" + a[0] + " cap=" + a[1] + " reallocs=" + a[2] + " bytes=" + a[3] + " meter=" + a[4]; }

    @Test
    public void all() throws Exception
    {
        say("STAGE4 begin " + System.getProperty("java.version") + " guardrail enabled at default=" + Guardrails.maximumReplicationFactor.enabled()
            + " default threshold=" + DatabaseDescriptor.getGuardrailsConfig().getMaximumReplicationFactorFailThreshold());
        // Threshold.enabled needs a threshold > 0 (Threshold.java:80-86): the default -1 is disabled, 3 must enable it
        DatabaseDescriptor.getGuardrailsConfig().setMaximumReplicationFactorThreshold(3, 3);
        check("instrument-enabled", !throwsGuardDefaultOff() && Guardrails.maximumReplicationFactor.enabled() && Guardrails.maximumReplicationFactor.failsOn(10, null),
              "at threshold 3 the guardrail must be enabled and failsOn(10) true");
        DatabaseDescriptor.getGuardrailsConfig().setMaximumReplicationFactorThreshold(-1, -1);
        check("default-disabled", !Guardrails.maximumReplicationFactor.enabled() && !Guardrails.maximumReplicationFactor.failsOn(10, null), "at -1 disabled");

        // 1. growth, threshold default (-1), initial capacity 0 and exact N
        for (long n : NS)
        {
            long[] g = fill(n, 0, null);
            say("STAGE4 reading phase=growth thr=-1 init=0 N=" + n + " " + show(g));
            check("growth-cap N=" + n, g[1] == expCap(n) && g[0] == n, "cap " + g[1] + " exp " + expCap(n));
            check("growth-reallocs N=" + n, g[2] == expReallocs(n), "reallocs " + g[2] + " exp " + expReallocs(n));
            check("growth-bytes N=" + n, g[3] == g[4] && g[3] >= 16 + 4 * g[1], "bytes " + g[3] + " meter " + g[4] + " cap " + g[1]);
            long[] e = fill(n, (int) n, null);
            say("STAGE4 reading phase=exact thr=-1 init=N N=" + n + " " + show(e));
            check("exact-cap N=" + n, e[1] == n && e[2] == 0 && e[0] == n, "cap " + e[1] + " reallocs " + e[2]);
            if (n >= 9) check("ratio N=" + n, g[1] >= n && g[1] <= 2 * n, "cap/N " + (double) g[1] / n);
        }
        // literal values of the amended prediction
        check("literal N=10", fill(10, 0, null)[1] == 18, "");
        check("literal N=100", fill(100, 0, null)[1] == 144, "");
        long[] t = fill(10_000, 0, null);
        check("literal N=10000", t[1] == 18432 && t[2] == 13, show(t));
        check("literal N=1000000", fill(1_000_000, 0, null)[1] == 1_179_648, "");
        check("bytes-N10", fill(10, 0, null)[3] < 100, "bytes " + fill(10, 0, null)[3]);

        // 2. threshold sweep: identical readings
        long[][] base = new long[3][];
        long[] sweepN = { 10, 1000, 1_000_000 };
        for (int ti = 0; ti < 3; ti++)
        {
            int thr = new int[]{ -1, 1, 3 }[ti];
            DatabaseDescriptor.getGuardrailsConfig().setMaximumReplicationFactorThreshold(thr, thr);
            int got = DatabaseDescriptor.getGuardrailsConfig().getMaximumReplicationFactorFailThreshold();
            check("threshold-applied thr=" + thr, got == thr, "read back " + got);
            for (int ni = 0; ni < 3; ni++)
            {
                long[] g;
                try { g = fill(sweepN[ni], 0, null); }
                catch (RuntimeException ex) { check("sweep-add-no-throw thr=" + thr + " N=" + sweepN[ni], false, ex.toString()); continue; }
                say("STAGE4 reading phase=sweep thr=" + thr + " init=0 N=" + sweepN[ni] + " " + show(g));
                if (ti == 0) base[ni] = g;
                check("sweep thr=" + thr + " N=" + sweepN[ni], java.util.Arrays.equals(g, base[ni]) && g[1] == expCap(sweepN[ni]), show(g) + " vs thr=-1 " + show(base[ni]));
            }
        }

        // 3. positive control: the guardrail binds a replica count
        check("control-guard10-thr3", throwsGuard(10, 3), "failsOn must be true");
        check("control-guard10-thr1", throwsGuard(10, 1), "failsOn must be true");
        check("control-guard2-thr1", throwsGuard(2, 1), "failsOn must be true");
        check("control-guard3-thr3-boundary", !throwsGuard(3, 3), "value == threshold: failsOn false");
        check("control-guard1-thr1-boundary", !throwsGuard(1, 1), "value == threshold: failsOn false");
        check("control-guard10-thr-1", !throwsGuard(10, -1), "disabled: failsOn false");
        // a list of 1,000,000 still grows with threshold 3 (list unaffected while the guard binds)
        DatabaseDescriptor.getGuardrailsConfig().setMaximumReplicationFactorThreshold(3, 3);
        check("control-list-grows-under-thr3", fill(1_000_000, 0, null)[1] == 1_179_648 && throwsGuard(10, 3), "list 1M cap with guard binding");
        DatabaseDescriptor.getGuardrailsConfig().setMaximumReplicationFactorThreshold(-1, -1);

        // 4. only route from the knob to bytes: builder capacity = RF
        for (int rf : new int[]{ 1, 3, 10 })
        {
            EndpointsForRange.Builder b = new EndpointsForRange.Builder(RANGE, rf);
            long len = b.list.contents.length;
            say("STAGE4 reading phase=builder rf=" + rf + " cap=" + len + " bytes=" + ObjectSizes.sizeOfReferenceArray((int) len));
            check("builder-cap rf=" + rf, len == rf, "cap " + len);
        }

        // 5. real heap: 10 retained lists of 1M (cap 1,179,648) against the instrument
        System.gc(); System.gc();
        long h0 = used();
        List<ReplicaList> keep = new ArrayList<>();
        long per = 0;
        for (int i = 0; i < 10; i++) per = fill(1_000_000, 0, keep)[3];
        System.gc(); System.gc(); System.gc();
        long h1 = used();
        double ratio = (double) (h1 - h0) / (10 * per);
        say("STAGE4 reading phase=heap lists=10 heapDelta=" + (h1 - h0) + " instrument=" + (10 * per) + " ratio=" + ratio + " keep=" + keep.size());
        check("heap-matches-instrument", ratio > 0.95 && ratio < 1.10, "ratio " + ratio);

        say("STAGE4 end checks=" + checks + " mismatches=" + bad);
        Assert.assertEquals(0, bad);
    }

    static boolean throwsGuardDefaultOff() { return false; }

    /** the control: does the guardrail fire (failsOn, the predicate guard() uses); guard() with a null state logs and returns (Guardrail.java:139) */
    static boolean throwsGuard(long value, int thr)
    {
        DatabaseDescriptor.getGuardrailsConfig().setMaximumReplicationFactorThreshold(thr, thr);
        boolean fires = Guardrails.maximumReplicationFactor.failsOn(value, null);
        boolean threw = false;
        try { Guardrails.maximumReplicationFactor.guard(value, "ks", false, null); }
        catch (InvalidRequestException e) { threw = true; }
        if (threw) say("STAGE4 note guard() with a null state threw (unexpected from source)");
        return fires;
    }

    static long used()
    {
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }
}
