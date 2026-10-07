/*
 * Stage-4 harness, unit tier of max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction
 * (case file section 9, 9e unit steps 2.1 to 2.7). Not part of upstream Cassandra.
 * Copy into test/unit/org/apache/cassandra/db/ of a local clone at cassandra-5.0.9.
 * System property stage4.out: a file that also receives the STAGE4 lines.
 *
 * It drives the check alone: the static Directories.hasDiskSpaceForCompactionsAndStreams(Map, Map, Function) and
 * Directories.getAvailableSpaceForCompactions(FileStore), against stub FileStores whose getUsableSpace() is set by the test.
 * The decision point (the shrink ladder and the counters) is CompactionLadderTest.
 */
package org.apache.cassandra.db;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.file.FileStore;
import java.nio.file.attribute.FileAttributeView;
import java.nio.file.attribute.FileStoreAttributeView;
import java.util.HashMap;
import java.util.Map;
import java.util.function.Function;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;
import org.slf4j.LoggerFactory;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.io.util.File;

public class CompactionBudgetTest
{
    static final long MIB = 1024L * 1024L;
    static final long FLOOR = 50 * MIB;                       // min_free_space_per_drive, default 50MiB (Config.java:339)
    static final long U = 1_000_000_000L;                     // the stub store's usable space (9e: U = 1,000,000,000)
    static final double[] PCTS = { 0.95, 0.5, 0.1, 0.01 };
    static final Pattern PASS = Pattern.compile("FileStore (.*) has (\\d+) bytes available, checking if we can write (\\d+) bytes");

    static PrintWriter out;
    static int mismatches = 0;
    static ListAppender<ILoggingEvent> appender;

    static class Stub extends FileStore
    {
        final String name;
        volatile long usable;

        Stub(String name, long usable)
        {
            this.name = name;
            this.usable = usable;
        }

        public long getUsableSpace() { return usable; }
        public String name() { return name; }
        public String type() { return "stub"; }
        public boolean isReadOnly() { return false; }
        public long getTotalSpace() { return usable; }
        public long getUnallocatedSpace() { return usable; }
        public boolean supportsFileAttributeView(Class<? extends FileAttributeView> type) { return false; }
        public boolean supportsFileAttributeView(String name) { return false; }
        public <V extends FileStoreAttributeView> V getFileStoreAttributeView(Class<V> type) { return null; }
        public Object getAttribute(String attribute) { return null; }
        public String toString() { return name; }
    }

    static void line(String s)
    {
        System.out.println(s);
        if (out != null) { out.println(s); out.flush(); }
    }

    static void check(String name, Object expected, Object actual)
    {
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        if (!ok) mismatches++;
        line("STAGE4 check " + name + " " + expected + " " + actual + " " + (ok ? "ok" : "MISMATCH"));
    }

    static void checkTrue(String name, boolean cond, String detail)
    {
        if (!cond) mismatches++;
        line("STAGE4 check " + name + " true " + cond + " " + (cond ? "ok" : "MISMATCH") + " [" + detail + "]");
    }

    static Map<File, Long> m(File f, long v)
    {
        Map<File, Long> r = new HashMap<>();
        r.put(f, v);
        return r;
    }

    static Map<File, Long> none()
    {
        return new HashMap<>();
    }

    static boolean admits(Map<File, Long> newWrites, Map<File, Long> inFlight, Function<File, FileStore> mapper)
    {
        return Directories.hasDiskSpaceForCompactionsAndStreams(newWrites, inFlight, mapper);
    }

    @BeforeClass
    public static void setup() throws Exception
    {
        String f = System.getProperty("stage4.out");
        if (f != null) out = new PrintWriter(new FileWriter(f, true));
        DatabaseDescriptor.daemonInitialization();
        Logger l = (Logger) LoggerFactory.getLogger(Directories.class);
        l.setLevel(Level.DEBUG);
        appender = new ListAppender<>();
        appender.start();
        l.addAppender(appender);
    }

    @Test
    public void budget() throws Exception
    {
        long oldMin = DatabaseDescriptor.getMinFreeSpacePerDriveInMebibytes();
        double oldPct = DatabaseDescriptor.getMaxSpaceForCompactionsPerDrive();
        try
        {
            DatabaseDescriptor.setMinFreeSpacePerDriveInMebibytes(50);
            check("floor_bytes", FLOOR, DatabaseDescriptor.getMinFreeSpacePerDriveInBytes());
            steps1to4();
            step5();
            step6();
            step7();
        }
        finally
        {
            DatabaseDescriptor.setMinFreeSpacePerDriveInMebibytes(oldMin);
            DatabaseDescriptor.setMaxSpaceForCompactionsPerDrive(oldPct);
        }
        line("STAGE4 summary mismatches " + mismatches);
        Assert.assertEquals(0, mismatches);
    }

    // 2.1 the limit is round((U - 50 MiB) x pct); 2.2 the boundary and one byte past it; 2.3 the in-flight term; 2.4 aggregation over stores
    void steps1to4()
    {
        for (double pct : PCTS)
        {
            DatabaseDescriptor.setMaxSpaceForCompactionsPerDrive(pct);
            check("getter_pct" + pct, pct, DatabaseDescriptor.getMaxSpaceForCompactionsPerDrive());
            String p = "_pct" + pct;
            Stub a = new Stub("storeA", U);
            long B = Math.round((double) (U - FLOOR) * pct);
            line("STAGE4 info " + p + " B=" + B + " (U=" + U + ", floor=" + FLOOR + ")");
            check("1_B" + p, B, Directories.getAvailableSpaceForCompactions(a));

            File f = new File("/stage4/dirA");
            File g = new File("/stage4/dirB");           // a second directory of the same store, or of another store, per mapper
            Function<File, FileStore> oneStore = x -> a;
            check("2_request_equals_B" + p, true, admits(m(f, B), none(), oneStore));
            check("2_request_B_plus_1" + p, false, admits(m(f, B + 1), none(), oneStore));
            check("2_request_B_minus_1" + p, true, admits(m(f, B - 1), none(), oneStore));

            long R = B / 3, w = B - R;                   // w + R == B
            check("3_inflight_w_plus_R_equals_B" + p, true, admits(m(f, w), m(f, R), oneStore));
            check("3_inflight_w_plus_R_equals_B_plus_1" + p, false, admits(m(f, w + 1), m(f, R), oneStore));
            check("3_inflight_other_dir_same_store_equals_B" + p, true, admits(m(f, w), m(g, R), oneStore));
            check("3_inflight_other_dir_same_store_B_plus_1" + p, false, admits(m(f, w + 1), m(g, R), oneStore));
            check("3_no_inflight_same_w_plus_1_admitted" + p, true, admits(m(f, w + 1), none(), oneStore));   // the term is what refuses

            Stub other = new Stub("storeB", U);
            Function<File, FileStore> twoStores = x -> x.equals(g) ? other : a;
            check("3_inflight_on_another_store_is_not_counted" + p, true, admits(m(f, B), m(g, 10 * B + 1), twoStores));

            // 2.4 aggregation: f on store A, g on store B2 with its own usable space
            long u2 = 600_000_000L;
            Stub b2 = new Stub("storeB2", u2);
            Function<File, FileStore> agg = x -> x.equals(g) ? b2 : a;
            long Ba = B, Bb = Math.round((double) (u2 - FLOOR) * pct);
            Map<File, Long> both = new HashMap<>();
            both.put(f, Ba); both.put(g, Bb);
            check("4_both_exactly_fit" + p, true, admits(both, none(), agg));
            both.put(g, Bb + 1);
            check("4_B2_one_byte_over" + p, false, admits(both, none(), agg));
            both.put(g, Bb); both.put(f, Ba + 1);
            check("4_A_one_byte_over" + p, false, admits(both, none(), agg));
            both.put(g, Bb + 1);
            check("4_both_over" + p, false, admits(both, none(), agg));
        }
    }

    // 2.5 the second knob: min_free_space_per_drive raised by d moves B by pct x d, whatever U
    void step5()
    {
        for (double pct : new double[] { 0.95, 0.5 })
        {
            DatabaseDescriptor.setMaxSpaceForCompactionsPerDrive(pct);
            for (long usable : new long[] { U, 2_000_000_000L })
            {
                DatabaseDescriptor.setMinFreeSpacePerDriveInMebibytes(50);
                Stub s = new Stub("storeK", usable);
                long B0 = Directories.getAvailableSpaceForCompactions(s);
                for (long dMiB : new long[] { 50, 100, 450 })
                {
                    DatabaseDescriptor.setMinFreeSpacePerDriveInMebibytes(50 + dMiB);
                    long Bd = Directories.getAvailableSpaceForCompactions(s);
                    long expect = Math.round((double) (usable - FLOOR - dMiB * MIB) * pct);
                    String n = "5_knob2_pct" + pct + "_U" + usable + "_d" + dMiB + "MiB";
                    check(n + "_B", expect, Bd);
                    double fall = B0 - Bd, want = pct * dMiB * MIB;
                    checkTrue(n + "_fall_is_pct_x_d", Math.abs(fall - want) <= 1.0, "fall=" + fall + " pct*d=" + want);
                }
            }
        }
        DatabaseDescriptor.setMinFreeSpacePerDriveInMebibytes(50);
    }

    // 2.6 the floor: B is never negative
    void step6()
    {
        DatabaseDescriptor.setMaxSpaceForCompactionsPerDrive(0.95);
        File f = new File("/stage4/dirA");
        for (long usable : new long[] { 10 * MIB, FLOOR })
        {
            Stub s = new Stub("storeF", usable);
            Function<File, FileStore> one = x -> s;
            check("6_floor_B_U" + usable, 0L, Directories.getAvailableSpaceForCompactions(s));
            check("6_floor_request_0_U" + usable, true, admits(m(f, 0), none(), one));
            check("6_floor_request_1_U" + usable, false, admits(m(f, 1), none(), one));
        }
        DatabaseDescriptor.setMaxSpaceForCompactionsPerDrive(0);
        Stub z = new Stub("storeZ", U);
        check("6_pct0_B", 0L, Directories.getAvailableSpaceForCompactions(z));
    }

    // 2.7 the lines the check logs: the pattern the cluster tier parses, and the WARN of a refusal
    void step7()
    {
        double pct = 0.5;
        DatabaseDescriptor.setMaxSpaceForCompactionsPerDrive(pct);
        Stub a = new Stub("storeL", U);
        long B = Math.round((double) (U - FLOOR) * pct);
        File f = new File("/stage4/dirA");
        File g = new File("/stage4/dirB");
        Function<File, FileStore> one = x -> a;
        long R = 12_345_678L, w = B - R;

        appender.list.clear();
        boolean ok = admits(m(f, w), m(g, R), one);
        check("7_admitted", true, ok);
        check("7_admitted_events", 1, appender.list.size());
        ILoggingEvent e = appender.list.get(0);
        check("7_admitted_level", Level.DEBUG, e.getLevel());
        Matcher mt = PASS.matcher(e.getFormattedMessage());
        checkTrue("7_admitted_pattern", mt.find(), e.getFormattedMessage());
        if (mt.find(0))
        {
            check("7_admitted_store", "storeL", mt.group(1));
            check("7_admitted_available", B, Long.parseLong(mt.group(2)));
            check("7_admitted_requested_is_w_plus_R", w + R, Long.parseLong(mt.group(3)));
        }

        appender.list.clear();
        ok = admits(m(f, w + 1), m(g, R), one);
        check("7_refused", false, ok);
        check("7_refused_events", 2, appender.list.size());
        ILoggingEvent d = appender.list.get(0), wn = appender.list.get(1);
        check("7_refused_first_level", Level.DEBUG, d.getLevel());
        check("7_refused_second_level", Level.WARN, wn.getLevel());
        mt = PASS.matcher(d.getFormattedMessage());
        if (mt.find())
        {
            check("7_refused_available", B, Long.parseLong(mt.group(2)));
            check("7_refused_requested", w + R + 1, Long.parseLong(mt.group(3)));
        }
        else
            checkTrue("7_refused_pattern", false, d.getFormattedMessage());
        String wm = wn.getFormattedMessage();
        checkTrue("7_refused_warn_text", wm.startsWith("FileStore storeL has only ") && wm.endsWith(" is needed"), wm);
        line("STAGE4 info warn line: " + wm);
    }
}
