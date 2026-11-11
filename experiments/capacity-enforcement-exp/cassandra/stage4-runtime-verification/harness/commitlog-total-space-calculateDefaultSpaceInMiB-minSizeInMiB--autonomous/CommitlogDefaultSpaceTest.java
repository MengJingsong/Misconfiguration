/*
 * Stage-4 unit tier (B2) for commitlog-total-space-calculateDefaultSpaceInMiB-minSizeInMiB--autonomous.
 * Copied into <tree>/test/unit/org/apache/cassandra/config/ (local tree only). Package-private access to
 * DatabaseDescriptor.calculateDefaultSpaceInMiB. One JVM per arm (-Dcltest.arm=H|E|V|C|D), see unit-run.sh.
 * Prints "RESULT ..." lines to the file named by -Dcltest.out (appended) and asserts every one of them.
 */
package org.apache.cassandra.config;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

import org.junit.Test;
import org.slf4j.LoggerFactory;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;

import static org.junit.Assert.assertTrue;

public class CommitlogDefaultSpaceTest
{
    static final long MIB = 1024L * 1024L;
    static final long GIB = 1024L * MIB;
    static final long TIB = 1024L * GIB;
    static PrintWriter out;
    static final List<String> failures = new ArrayList<>();
    static ListAppender<ILoggingEvent> appender;

    static void result(String line)
    {
        System.out.println("RESULT " + line);
        out.println("RESULT " + line);
        out.flush();
    }

    static void check(String what, Object expected, Object actual)
    {
        boolean ok = expected.equals(actual);
        result((ok ? "PASS " : "FAIL ") + what + " expected=" + expected + " actual=" + actual);
        if (!ok)
            failures.add(what);
    }

    static int warnCount(String type)
    {
        int n = 0;
        for (ILoggingEvent e : appender.list)
            if (e.getFormattedMessage().startsWith("Small " + type + " volume detected"))
                n++;
        return n;
    }

    /** one call of the helper with its WARN check: WARN iff min < preferred (the strict comparison). */
    static int call(String label, String type, int preferred, long totalBytes, long num, long den)
    {
        appender.list.clear();
        int got = DatabaseDescriptor.calculateDefaultSpaceInMiB(type, "/path", "setting", preferred, totalBytes, num, den);
        long min = Math.min(Integer.MAX_VALUE, num * (totalBytes / MIB) / den);
        int warns = warnCount(type);
        check(label + " warn", min < preferred ? 1 : 0, warns);
        return got;
    }

    @Test
    public void run() throws Exception
    {
        String arm = System.getProperty("cltest.arm", "H");
        out = new PrintWriter(new FileWriter(System.getProperty("cltest.out", "cltest.out"), true));
        Logger l = (Logger) LoggerFactory.getLogger("org.apache.cassandra.config.DatabaseDescriptor");
        appender = new ListAppender<>();
        appender.start();
        l.addAppender(appender);

        DatabaseDescriptor.daemonInitialization();
        result("ARM " + arm + " cassandra.config=" + System.getProperty("cassandra.config"));

        // ---- init arms (B2e steps 4, 5; amendment R2)
        String cldir = System.getProperty("cltest.cldir");
        String cdcdir = System.getProperty("cltest.cdcdir");
        long clTotalMiB = Files.getFileStore(Paths.get(cldir)).getTotalSpace() / MIB;
        long cdcTotalMiB = Files.getFileStore(Paths.get(cdcdir)).getTotalSpace() / MIB;
        result("VOLUME cldir=" + cldir + " totalMiB=" + clTotalMiB + " cdcdir=" + cdcdir + " totalMiB=" + cdcTotalMiB);
        long initWarnsCl = warnCount("commitlog");
        long initWarnsCdc = warnCount("cdc");
        long gotCl = DatabaseDescriptor.getTotalCommitlogSpaceInMiB();
        long gotCdc = DatabaseDescriptor.getCDCTotalSpace() / MIB;   // the getter returns bytes (shakedown 1 instrument defect)
        result("INIT commitlog_total_space=" + gotCl + " cdc_total_space=" + gotCdc
               + " warnCommitlog=" + initWarnsCl + " warnCdc=" + initWarnsCdc + " cdc_enabled=" + DatabaseDescriptor.isCDCEnabled());
        if (arm.equals("E"))
        {
            check("E explicit commitlog_total_space", 64L, gotCl);
            check("E no commitlog WARN", 0L, initWarnsCl);
        }
        else
        {
            long expCl = Math.min(8192L, clTotalMiB / 4);
            check(arm + " derived commitlog_total_space = min(8192, total/4)", expCl, gotCl);
            check(arm + " commitlog WARN iff total/4 < 8192", clTotalMiB / 4 < 8192 ? 1L : 0L, initWarnsCl);
        }
        if (arm.equals("C") || arm.equals("D"))
        {
            long expCdc = Math.min(4096L, cdcTotalMiB / 8);
            check(arm + " derived cdc_total_space = min(4096, total/8)", expCdc, gotCdc);
            check(arm + " cdc WARN iff total/8 < 4096", cdcTotalMiB / 8 < 4096 ? 1L : 0L, initWarnsCdc);
        }
        else
            check(arm + " cdc disabled", false, DatabaseDescriptor.isCDCEnabled());

        // ---- arithmetic table (B2b, B2c, B2f, B2h), every arm's JVM, twice for determinism
        for (int rep = 1; rep <= 2; rep++)
        {
            String r = "rep" + rep + " ";
            check(r + "CL 0", 0, call(r + "CL 0", "commitlog", 8192, 0, 1, 4));
            check(r + "CL 999MiB", 249, call(r + "CL 999MiB", "commitlog", 8192, 999 * MIB, 1, 4));
            check(r + "CL 4GiB", 1024, call(r + "CL 4GiB", "commitlog", 8192, 4 * GIB, 1, 4));
            check(r + "CL 32767MiB", 8191, call(r + "CL 32767MiB", "commitlog", 8192, 32767 * MIB, 1, 4));
            check(r + "CL 32768MiB", 8192, call(r + "CL 32768MiB", "commitlog", 8192, 32768 * MIB, 1, 4));
            check(r + "CL 32769MiB", 8192, call(r + "CL 32769MiB", "commitlog", 8192, 32769 * MIB, 1, 4));
            check(r + "CL 1TiB", 8192, call(r + "CL 1TiB", "commitlog", 8192, TIB, 1, 4));
            check(r + "CL Long.MAX", 8192, call(r + "CL Long.MAX", "commitlog", 8192, Long.MAX_VALUE, 1, 4));
            check(r + "CDC 0", 0, call(r + "CDC 0", "cdc", 4096, 0, 1, 8));
            check(r + "CDC 32767MiB", 4095, call(r + "CDC 32767MiB", "cdc", 4096, 32767 * MIB, 1, 8));
            check(r + "CDC 32768MiB", 4096, call(r + "CDC 32768MiB", "cdc", 4096, 32768 * MIB, 1, 8));
            check(r + "CDC 1TiB", 4096, call(r + "CDC 1TiB", "cdc", 4096, TIB, 1, 8));
            check(r + "CDC Long.MAX", 4096, call(r + "CDC Long.MAX", "cdc", 4096, Long.MAX_VALUE, 1, 8));
            check(r + "upstream 667,2/3,999MiB", 666, call(r + "upstream1", "type", 667, 999 * MIB, 2, 3));
            check(r + "upstream 100,1/3,999MiB", 100, call(r + "upstream2", "type", 100, 999 * MIB, 1, 3));
            // control B2h: same total 999 MiB, 1/3 (min = 333); preferred swapped 100 vs 667: the branch flips
            check(r + "swap preferred=100", 100, call(r + "swap100", "type", 100, 999 * MIB, 1, 3));
            check(r + "swap preferred=667", 333, call(r + "swap667", "type", 667, 999 * MIB, 1, 3));
        }
        result("DONE failures=" + failures.size());
        out.close();
        assertTrue("failed checks: " + failures, failures.isEmpty());
    }
}
