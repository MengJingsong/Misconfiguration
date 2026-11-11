/*
 * Stage-4 harness, autonomous: repair_disk_headroom_reject_ratio-setrepairdiskheadroomrejectratio-value (unit tier, added by the 2026-10-27 audit).
 * Not upstream. Copy into test/unit/org/apache/cassandra/service/. Prints "STAGE4 check <name> <expected> <actual> ok|MISMATCH" and
 * "STAGE4 value <name> <text>" (also to the file named by -Dstage4.out); fails at the end on any mismatch.
 * Style and the mocked DiskUsageMonitor follow the closed harness RepairHeadroomCheckTest.
 */
package org.apache.cassandra.service;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.util.List;
import java.util.stream.Collectors;

import org.junit.After;
import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;
import org.slf4j.LoggerFactory;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.service.disk.usage.DiskUsageMonitor;
import org.apache.cassandra.streaming.PreviewKind;
import org.apache.cassandra.utils.TimeUUID;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

public class HeadroomSetterRangeTest
{
    static PrintWriter out;
    static int checks = 0, mismatches = 0;
    static DiskUsageMonitor original;
    static double originalRatio;
    static ListAppender<ILoggingEvent> appender;
    static final String RANGE_MSG = "Value must be >= 0 and <= 1 for repair_disk_headroom_reject_ratio";

    static void line(String s) { System.out.println(s); if (out != null) { out.println(s); out.flush(); } }

    static void check(String name, Object expected, Object actual)
    {
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        checks++; if (!ok) mismatches++;
        line("STAGE4 check " + name + " " + expected + " " + actual + " " + (ok ? "ok" : "MISMATCH"));
    }

    static void value(String name, String text) { line("STAGE4 value " + name + " " + text); }

    @BeforeClass
    public static void setUp() throws Exception
    {
        String f = System.getProperty("stage4.out");
        if (f != null) out = new PrintWriter(new FileWriter(f, true));
        SchemaLoader.prepareServer();
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

    @AfterClass
    public static void end()
    {
        value("summary", "checks=" + checks + " mismatches=" + mismatches);
        if (out != null) out.close();
        Assert.assertEquals("STAGE4 mismatches (see the STAGE4 lines)", 0, mismatches);
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

    /** the real verifyDiskHeadroomThreshold at usage u; returns {verdict, number of ERROR lines} */
    static boolean verdict(String name, double u, boolean expected, int expectedErrors)
    {
        usage(u);
        int from = appender.list.size();
        boolean got = ActiveRepairService.instance().verifyDiskHeadroomThreshold(TimeUUID.Generator.nextTimeUUID(), PreviewKind.NONE);
        check(name + "_u=" + u + "_verdict", expected, got);
        check(name + "_u=" + u + "_error_lines", expectedErrors, errorsSince(from).size());
        return got;
    }

    @Test
    public void s1SetterOutcomes() throws Exception
    {
        com.sun.management.ThreadMXBean tmx = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
        tmx.setThreadAllocatedMemoryEnabled(true);
        long tid = Thread.currentThread().getId();
        double[] bad = { -0.1, 1.1, 1.0000001, Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY, -1e300 };
        double[] good = { 0.0, -0.0, 0.5, 1.0, Double.NaN };
        DatabaseDescriptor.setRepairDiskHeadroomRejectRatio(0.3);
        for (double b : bad)
        {
            String e1 = "none", e2 = "none";
            long a0 = tmx.getThreadAllocatedBytes(tid);
            try { DatabaseDescriptor.setRepairDiskHeadroomRejectRatio(b); } catch (IllegalArgumentException e) { e1 = e.getMessage(); }
            long a1 = tmx.getThreadAllocatedBytes(tid);
            try { ActiveRepairService.instance().setIncrementalRepairDiskHeadroomRejectRatio(b); } catch (IllegalArgumentException e) { e2 = e.getMessage(); }
            check("S1_reject_" + b + "_setter", RANGE_MSG, e1);
            check("S1_reject_" + b + "_mbean", RANGE_MSG, e2);
            check("S1_reject_" + b + "_getter_unchanged", 0.3, DatabaseDescriptor.getRepairDiskHeadroomRejectRatio());
            value("S1_reject_" + b, "allocated_bytes_of_the_setter_call=" + (a1 - a0));
        }
        for (double g : good)
        {
            long a0 = tmx.getThreadAllocatedBytes(tid);
            DatabaseDescriptor.setRepairDiskHeadroomRejectRatio(g);
            long a1 = tmx.getThreadAllocatedBytes(tid);
            double back = ActiveRepairService.instance().getIncrementalRepairDiskHeadroomRejectRatio();
            check("S1_accept_" + g + "_stored", Double.doubleToLongBits(g), Double.doubleToLongBits(back));
            value("S1_accept_" + g, "allocated_bytes_of_the_setter_call=" + (a1 - a0) + " getter=" + back);
        }
    }

    @Test
    public void s2StoredValueSetsTheBoundary() throws Exception
    {
        DatabaseDescriptor.setRepairDiskHeadroomRejectRatio(0.5);
        verdict("S2_r0.5_at", 0.50000, true, 0);
        verdict("S2_r0.5_above", 0.50001, false, 1);
        for (double b : new double[]{ 1.1, -0.1 })
        {
            try { DatabaseDescriptor.setRepairDiskHeadroomRejectRatio(b); Assert.fail("accepted " + b); } catch (IllegalArgumentException expected) { }
            check("S2_after_rejected_" + b + "_getter", 0.5, DatabaseDescriptor.getRepairDiskHeadroomRejectRatio());
            verdict("S2_after_rejected_" + b + "_at", 0.50000, true, 0);
            verdict("S2_after_rejected_" + b + "_above", 0.50001, false, 1);
        }
        DatabaseDescriptor.setRepairDiskHeadroomRejectRatio(1.0);
        verdict("S2_r1.0_zero", 0.0, true, 0);
        verdict("S2_r1.0_min", 0.00001, false, 1);
        DatabaseDescriptor.setRepairDiskHeadroomRejectRatio(Double.NaN);
        verdict("S2_rNaN_high", 0.99999, true, 0);
        verdict("S2_rNaN_5x", 5.0, true, 0);
    }
}
