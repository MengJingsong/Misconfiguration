/*
 * Stage-4 unit-tier probe for CommitLog.addAdditionalInformationIfPossible (case commitlog-segment-size-
 * addAdditionalInformationIfPossible-segmentSize--autonomous, B2). Not upstream code.
 * System properties: sgtest.big (dir on a >= 4 GiB tmpfs), sgtest.small (dir on a 16 MiB tmpfs), sgtest.out (result file).
 * Every case appends "RESULT PASS|FAIL <name> <detail>" lines; the run script checks them against its EXPECTED list.
 */
package org.apache.cassandra.db.commitlog;

import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.concurrent.TimeUnit;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.BeforeClass;
import org.junit.Test;
import org.slf4j.LoggerFactory;

import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.utils.JVMStabilityInspector;
import org.apache.cassandra.utils.KillerForTests;

public class SgAddInfoProbeTest
{
    static final String NEEDLE = "bytes required for next commitlog segment but only ";
    static PrintWriter out;
    static int fails = 0;
    static String big, small;

    @BeforeClass
    public static void setup() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        // handleCommitError -> JVMStabilityInspector.inspectCommitLogError kills the JVM when daemon setup has not completed (as in a unit JVM)
        JVMStabilityInspector.replaceKiller(new KillerForTests());
        big = System.getProperty("sgtest.big");
        small = System.getProperty("sgtest.small");
        out = new PrintWriter(new FileWriter(System.getProperty("sgtest.out"), true), true);
    }

    static void rec(boolean ok, String name, String detail)
    {
        if (!ok) fails++;
        out.println("RESULT " + (ok ? "PASS " : "FAIL ") + name + " " + detail);
    }

    static String sh(String... cmd) throws Exception
    {
        Process p = new ProcessBuilder(cmd).redirectErrorStream(true).start();
        String s = new String(p.getInputStream().readAllBytes()).trim();
        p.waitFor(30, TimeUnit.SECONDS);
        return s;
    }

    /** df size and avail, in bytes, of the volume holding dir */
    static long[] df(String dir) throws Exception
    {
        File e = new File(dir);
        while (!e.exists()) e = e.getParentFile(); // df needs an existing path: the nearest existing ancestor (as PathUtils does)
        String[] l = sh("df", "-B1", "--output=size,avail", e.getPath()).split("\n");
        String[] f = l[l.length - 1].trim().split("\\s+");
        return new long[]{ Long.parseLong(f[0]), Long.parseLong(f[1]) };
    }

    static String call(Method m, String dir, int segMiB) throws Exception
    {
        DatabaseDescriptor.setCommitLogLocation(dir);
        DatabaseDescriptor.setCommitLogSegmentSize(segMiB);
        return (String) m.invoke(null, "base message");
    }

    /** one probe: calls the private method, cross-checks the operand against df in the same call */
    static void probe(Method m, String name, String dir, int segMiB, boolean expectAug, long expectOperand, boolean operandIsTotal /* the operand is always compared with the df SIZE column */) throws Exception
    {
        DatabaseDescriptor.setCommitLogLocation(dir);
        DatabaseDescriptor.setCommitLogSegmentSize(segMiB);
        long[] d0 = df(dir);
        long operand = CommitLog.freeDiskSpace();
        String r = call(m, dir, segMiB);
        long[] d1 = df(dir);
        boolean aug = r.contains(NEEDLE);
        long only = -1;
        if (aug)
        {
            String t = r.substring(r.indexOf(NEEDLE) + NEEDLE.length());
            only = Long.parseLong(t.substring(0, t.indexOf(' ')));
        }
        String detail = String.format("seg=%dMiB aug=%s only=%d operand=%d df_size=%d df_avail_before=%d df_avail_after=%d",
                                      segMiB, aug, only, operand, d1[0], d0[1], d1[1]);
        boolean ok = aug == expectAug && operand == d1[0];
        if (expectOperand >= 0) ok &= operand == expectOperand;
        if (aug) ok &= only == operand;
        rec(ok, name, detail);
    }

    static void fill(String dir, String name, long leaveFree) throws Exception
    {
        long avail = df(dir)[1];
        if (avail > leaveFree)
            sh("fallocate", "-l", Long.toString(avail - leaveFree), dir + "/" + name);
    }

    @Test
    public void run() throws Exception
    {
        Method m = CommitLog.class.getDeclaredMethod("addAdditionalInformationIfPossible", String.class);
        m.setAccessible(true);
        Config.CommitFailurePolicy saved = DatabaseDescriptor.getCommitFailurePolicy();
        String bigd = big + "/cl", smalld = small + "/cl";
        new File(bigd).mkdirs(); new File(smalld).mkdirs();
        long bigTotal = df(bigd)[0], smallTotal = df(smalld)[0];
        rec(smallTotal == 16777216L, "KA small volume total", "df_size=" + smallTotal + " expected=16777216");
        rec(bigTotal >= 4294967296L, "KA big volume total", "df_size=" + bigTotal + " expected>=4294967296");

        // Known-answer / instrument check: the needle appears for the tmpfs (total < segment) and is absent for the big volume.
        probe(m, "S1 small empty seg32", smalld, 32, true, 16777216L, true);
        probe(m, "S2 big empty seg32", bigd, 32, false, bigTotal, true);

        // B2e step 1/5: large volume, every segment size, nearly empty
        for (int s : new int[]{ 8, 32, 1024, 2047 })
            probe(m, "S3 big empty seg" + s, bigd, s, false, bigTotal, true);

        // B2e step 2: fill the large volume to <= 64 KiB free; then every segment size again
        fill(bigd, "filler", 32768L);
        long[] bd = df(bigd);
        rec(bd[1] <= 65536L, "KA big volume full", "df_avail=" + bd[1]);
        for (int s : new int[]{ 8, 32, 1024, 2047 })
            probe(m, "S4 big FULL seg" + s, bigd, s, false, bigTotal, true);

        // B2e step 3: 16 MiB tmpfs, empty (done: S1) and full
        fill(smalld, "filler", 262144L);
        long[] sd = df(smalld);
        rec(sd[1] <= 1048576L, "KA small volume full", "df_avail=" + sd[1]);
        probe(m, "S5 small FULL seg32", smalld, 32, true, 16777216L, true);
        // boundary dose-response around total = 16 MiB, volume full (avail < 1 MiB throughout)
        probe(m, "S6 small FULL seg8", smalld, 8, false, 16777216L, true);
        probe(m, "S6 small FULL seg16", smalld, 16, false, 16777216L, true);
        probe(m, "S6 small FULL seg17", smalld, 17, true, 16777216L, true);
        probe(m, "S6 small FULL seg1024", smalld, 1024, true, 16777216L, true);
        // B2e step 4 (amendment D-R1): nonexistent paths
        probe(m, "S7 nonexistent under big", bigd + "/no/such/dir", 32, false, bigTotal, true);
        probe(m, "S7 nonexistent under small", smalld + "/no/such/dir", 32, true, 16777216L, true);

        // Through the real entry: CommitLog.handleCommitError with policy stop_commit and ignore, log line captured
        Logger lg = (Logger) LoggerFactory.getLogger(CommitLog.class);
        ListAppender<ILoggingEvent> app = new ListAppender<>();
        app.start();
        lg.addAppender(app);
        for (Config.CommitFailurePolicy p : new Config.CommitFailurePolicy[]{ Config.CommitFailurePolicy.stop_commit, Config.CommitFailurePolicy.ignore })
        {
            DatabaseDescriptor.setCommitFailurePolicy(p);
            for (String[] c : new String[][]{ { "small", smalld, "true" }, { "big", bigd, "false" } })
            {
                app.list.clear();
                DatabaseDescriptor.setCommitLogLocation(c[1]);
                DatabaseDescriptor.setCommitLogSegmentSize(32);
                boolean ret = CommitLog.handleCommitError("Failed managing commit log segments", new java.io.IOException("probe"));
                String msg = app.list.isEmpty() ? "" : app.list.get(0).getFormattedMessage();
                boolean aug = msg.contains(NEEDLE);
                rec(aug == Boolean.parseBoolean(c[2]) && !msg.isEmpty(), "S8 handleCommitError " + p + " " + c[0],
                    "ret=" + ret + " aug=" + aug + " msg=" + msg.replace('\n', ' '));
            }
        }
        lg.detachAppender(app);
        DatabaseDescriptor.setCommitFailurePolicy(saved);

        // B2h positive control: the knob binds elsewhere, at segment creation: the segment file is commitlog_segment_size bytes
        for (int s : new int[]{ 8, 32, 64 })
        {
            DatabaseDescriptor.setCommitLogSegmentSize(s);
            CommitLog.instance.resetUnsafe(true);
            // the newest segment file of the manager's own directory (the allocating one)
            File dir = new File(CommitLog.instance.segmentManager.storageDirectory);
            File[] fs = dir.listFiles((d, n) -> n.startsWith("CommitLog-") && n.endsWith(".log"));
            File f = null;
            for (File c : fs) if (f == null || c.getName().compareTo(f.getName()) > 0) f = c;
            StringBuilder all = new StringBuilder();
            for (File c : fs) all.append(c.getName()).append(':').append(c.length()).append(' ');
            long len = f == null ? -1 : f.length();
            rec(len == (long) s * 1048576L, "C1 segment file length seg" + s, "newest=" + (f == null ? null : f.getName()) + " length=" + len + " expected=" + (long) s * 1048576L + " files=" + all);
        }
        out.println("RESULT DONE failures=" + fails);
        out.close();
    }
}
