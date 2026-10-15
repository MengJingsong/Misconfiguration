/*
 * Stage-4 harness, unit tier U1, U2, U4a of repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio
 * (case file section 9e, amended 2026-10-15). Not upstream. Copy into test/unit/org/apache/cassandra/service/.
 * Prints "STAGE4 check <name> <expected> <actual> ok|MISMATCH" (also to the file named by -Dstage4.out); fails at the end.
 */
package org.apache.cassandra.service;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.math.BigDecimal;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.junit.After;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;
import org.slf4j.LoggerFactory;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.repair.NoSuchRepairSessionException;
import org.apache.cassandra.repair.messages.RepairOption;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.service.disk.usage.DiskUsageMonitor;
import org.apache.cassandra.streaming.PreviewKind;
import org.apache.cassandra.utils.FBUtilities;
import org.apache.cassandra.utils.TimeUUID;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

public class RepairHeadroomCheckTest
{
    static final String KS = "hdr_unit", CF = "t";
    static PrintWriter out;
    static int checks = 0, mismatches = 0;
    static DiskUsageMonitor original;
    static double originalRatio;
    static ListAppender<ILoggingEvent> appender;

    static void line(String s) { System.out.println(s); if (out != null) { out.println(s); out.flush(); } }

    static void check(String name, Object expected, Object actual)
    {
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        checks++; if (!ok) mismatches++;
        line("STAGE4 check " + name + " " + expected + " " + actual + " " + (ok ? "ok" : "MISMATCH"));
    }

    @BeforeClass
    public static void setUp() throws Exception
    {
        String f = System.getProperty("stage4.out");
        if (f != null) out = new PrintWriter(new FileWriter(f, true));
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1), SchemaLoader.standardCFMD(KS, CF));
        original = DiskUsageMonitor.instance;
        originalRatio = DatabaseDescriptor.getRepairDiskHeadroomRejectRatio();
        appender = new ListAppender<>();
        appender.start();
        ((Logger) LoggerFactory.getLogger(ActiveRepairService.class)).addAppender(appender);
    }

    @After
    public void restore()
    {
        DiskUsageMonitor.instance = original;
        DatabaseDescriptor.setRepairDiskHeadroomRejectRatio(originalRatio);
    }

    static void usage(double u)
    {
        DiskUsageMonitor m = mock(DiskUsageMonitor.class);
        when(m.getDiskUsage()).thenReturn(u);
        DiskUsageMonitor.instance = m;
    }

    static List<String> errorsSince(int from)
    {
        return appender.list.subList(from, appender.list.size()).stream()
                            .filter(e -> e.getFormattedMessage().contains("Rejecting incoming repair, disk usage"))
                            .map(ILoggingEvent::getFormattedMessage).collect(Collectors.toList());
    }

    static double lit(String s) { return Double.parseDouble(s); }

    /** verdict at (u, r); on false also checks the one ERROR line and its percentages */
    static void verdict(String name, String u, String r, boolean expected)
    {
        usage(lit(u));
        DatabaseDescriptor.setRepairDiskHeadroomRejectRatio(lit(r));
        TimeUUID id = TimeUUID.Generator.nextTimeUUID();
        int from = appender.list.size();
        boolean got = ActiveRepairService.instance().verifyDiskHeadroomThreshold(id, PreviewKind.NONE);
        check("U1_" + name + "_u=" + u + "_r=" + r, expected, got);
        List<String> errs = errorsSince(from);
        if (!expected)
        {
            String want = "[" + PreviewKind.NONE.logPrefix(id) + "] Rejecting incoming repair, disk usage (" + String.format("%.2f", lit(u) * 100) + "%) above threshold ("
                          + String.format("%.2f", (1 - lit(r)) * 100) + "%)";
            check("U1_" + name + "_error_line", want, errs.size() == 1 ? errs.get(0) : errs.toString());
        }
        else
            check("U1_" + name + "_no_error_line", 0, errs.size());
    }

    static String minus(String a, String b) { return new BigDecimal(a).subtract(new BigDecimal(b)).toPlainString(); }
    static String plus(String a, String b) { return new BigDecimal(a).add(new BigDecimal(b)).toPlainString(); }

    @Test
    public void headroom() throws Throwable
    {
        // U1 — the boundary
        for (String r : new String[]{ "0.0", "0.2", "0.5", "0.8" })
        {
            String b = minus("1", r);
            verdict("below", minus(b, "0.00001"), r, true);
            verdict("at", b, r, true);
            verdict("above", plus(b, "0.00001"), r, false);
        }
        verdict("r1_zero", "0.0", "1.0", true);              // amendment (1)
        verdict("r1_min", "0.00001", "1.0", false);
        verdict("default_full", "1.0", "0.0", true);
        verdict("default_over", "1.00001", "0.0", false);
        verdict("default_5x", "5.0", "0.0", false);
        for (int i = 1; i <= 9; i++)                          // IEEE: (1 - r) + r == 1.0 as 5-decimal literals
        {
            String r = "0." + i, b = minus("1", r);
            check("U1_ieee_sum_r=" + r, 1.0, lit(b) + lit(r));
            verdict("ieee_at", b, r, true);
        }

        // U2 — the knob's range
        DatabaseDescriptor.setRepairDiskHeadroomRejectRatio(0.3);
        for (double bad : new double[]{ -0.01, 1.01 })
        {
            String e1 = "none", e2 = "none";
            try { DatabaseDescriptor.setRepairDiskHeadroomRejectRatio(bad); } catch (IllegalArgumentException e) { e1 = e.getMessage(); }
            try { ActiveRepairService.instance().setIncrementalRepairDiskHeadroomRejectRatio(bad); } catch (IllegalArgumentException e) { e2 = e.getMessage(); }
            check("U2_setter_rejects_" + bad, "Value must be >= 0 and <= 1 for repair_disk_headroom_reject_ratio", e1);
            check("U2_mbean_rejects_" + bad, "Value must be >= 0 and <= 1 for repair_disk_headroom_reject_ratio", e2);
            check("U2_unchanged_after_" + bad, 0.3, DatabaseDescriptor.getRepairDiskHeadroomRejectRatio());
        }
        for (double ok : new double[]{ 0.0, 1.0 })
        {
            ActiveRepairService.instance().setIncrementalRepairDiskHeadroomRejectRatio(ok);
            check("U2_accepts_" + ok, ok, ActiveRepairService.instance().getIncrementalRepairDiskHeadroomRejectRatio());
        }
        DatabaseDescriptor.getRawConfig().repair_disk_headroom_reject_ratio = 1.5;   // what YAML binding does
        check("U2_raw_1.5_read", 1.5, DatabaseDescriptor.getRepairDiskHeadroomRejectRatio());
        usage(0.00001);
        int from = appender.list.size();
        check("U2_raw_1.5_refuses_min_usage", false, ActiveRepairService.instance().verifyDiskHeadroomThreshold(TimeUUID.Generator.nextTimeUUID(), PreviewKind.NONE));
        List<String> e15 = errorsSince(from);
        check("U2_raw_1.5_threshold_text", true, e15.size() == 1 && e15.get(0).endsWith("above threshold (-50.00%)"));
        DatabaseDescriptor.getRawConfig().repair_disk_headroom_reject_ratio = 0.0;

        // U4a — the coordinator
        List<ColumnFamilyStore> cfs = Collections.singletonList(Keyspace.open(KS).getColumnFamilyStore(CF));
        DatabaseDescriptor.setRepairDiskHeadroomRejectRatio(0.5);
        for (PreviewKind pk : new PreviewKind[]{ PreviewKind.NONE, PreviewKind.ALL })
            for (boolean inc : new boolean[]{ true, false })
            {
                String tag = pk + "_inc=" + inc;
                usage(0.50001);
                TimeUUID id = TimeUUID.Generator.nextTimeUUID();
                String msg = "none";
                from = appender.list.size();
                try { ActiveRepairService.instance().prepareForRepair(id, FBUtilities.getBroadcastAddressAndPort(), Collections.emptySet(), opts(pk, inc), false, cfs); }
                catch (RuntimeException e) { msg = e.getMessage(); }
                check("U4a_refused_" + tag, "Rejecting incoming repair, disk usage above threshold", msg);
                String reg = "registered";
                try { ActiveRepairService.instance().getParentRepairSession(id); } catch (NoSuchRepairSessionException e) { reg = "NoSuchRepairSessionException"; }
                check("U4a_nothing_registered_" + tag, "NoSuchRepairSessionException", reg);
                List<String> errs = errorsSince(from);
                check("U4a_error_prefix_" + tag, true, errs.size() == 1 && errs.get(0).startsWith("[" + pk.logPrefix(id) + "] Rejecting incoming repair, disk usage (50.00%) above threshold (50.00%)"));

                usage(0.5);
                TimeUUID id2 = TimeUUID.Generator.nextTimeUUID();
                String msg2 = "none";
                try { ActiveRepairService.instance().prepareForRepair(id2, FBUtilities.getBroadcastAddressAndPort(), Collections.emptySet(), opts(pk, inc), false, cfs); }
                catch (RuntimeException e) { msg2 = e.getMessage(); }
                String reg2 = "registered";
                try { ActiveRepairService.instance().getParentRepairSession(id2); } catch (NoSuchRepairSessionException e) { reg2 = "NoSuchRepairSessionException"; }
                check("U4a_admitted_no_exception_" + tag, "none", msg2);
                check("U4a_admitted_registered_" + tag, "registered", reg2);           // amendment (2): checked at once
                ActiveRepairService.instance().removeParentRepairSession(id2);
            }

        line("STAGE4 summary checks " + checks + " mismatches " + mismatches);
        Assert.assertEquals(0, mismatches);
    }

    static RepairOption opts(PreviewKind pk, boolean incremental)
    {
        Map<String, String> m = new HashMap<>();
        m.put(RepairOption.INCREMENTAL_KEY, Boolean.toString(incremental));
        m.put(RepairOption.PREVIEW, pk.toString());
        return RepairOption.parse(m, DatabaseDescriptor.getPartitioner());
    }
}
