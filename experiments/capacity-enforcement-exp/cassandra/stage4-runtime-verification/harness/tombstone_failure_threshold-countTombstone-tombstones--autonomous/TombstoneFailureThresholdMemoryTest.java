// Stage-4 harness copy of the B2e test of
// stage3-ai-deep-read/cases/tombstone_failure_threshold-countTombstone-tombstones--autonomous.md
// (frozen sha256 9e62de3a...), with audit amendments R1 (UPDATE ... SET v = null), R2 (ORIGINAL in @BeforeClass)
// and runbook fix D1 (read thresholds off, as on a default node).
package org.apache.cassandra.db;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.util.Arrays;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.junit.AfterClass;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.Util;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.filter.TombstoneOverwhelmingException;
import org.apache.cassandra.db.partitions.UnfilteredPartitionIterator;
import org.apache.cassandra.db.rows.UnfilteredRowIterator;
import org.apache.cassandra.net.MessagingService;

public class TombstoneFailureThresholdMemoryTest extends CQLTester
{
    static final int N = 30_000;
    static final int CK_LEN = 1000;
    static final int REPS = 5;
    static int ORIGINAL; // audit amendment R2 (2026-10-21): read after CQLTester.setUpClass, not in a static initialiser
    static final com.sun.management.ThreadMXBean TMX =
        (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static final Pattern P = Pattern.compile("Scanned over (\\d+) tombstones");

    @BeforeClass
    public static void saveOriginal()
    {
        ORIGINAL = DatabaseDescriptor.getTombstoneFailureThreshold();
        ORIGINAL_RT = DatabaseDescriptor.getReadThresholdsEnabled();
        DatabaseDescriptor.setReadThresholdsEnabled(false); // runbook fix D1 (2026-10-21): node default, Config.java:526
    }
    static boolean ORIGINAL_RT;

    @AfterClass
    public static void restore() { DatabaseDescriptor.setTombstoneFailureThreshold(ORIGINAL); DatabaseDescriptor.setReadThresholdsEnabled(ORIGINAL_RT); }

    static String ck(int i)
    {
        StringBuilder sb = new StringBuilder(String.format("%08d", i));
        while (sb.length() < CK_LEN) sb.append('x');
        return sb.toString();
    }

    static long allocated() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }

    static int countUnfiltered(ReadResponse resp, ReadCommand cmd)
    {
        int n = 0;
        try (UnfilteredPartitionIterator pi = resp.makeIterator(cmd))
        {
            while (pi.hasNext())
                try (UnfilteredRowIterator ri = pi.next()) { while (ri.hasNext()) { ri.next(); n++; } }
        }
        return n;
    }

    @Test
    public void sweep() throws Throwable
    {
        createTable("CREATE TABLE %s (pk int, ck text, v text, PRIMARY KEY (pk, ck))");
        for (int i = 0; i < N; i++)
        {
            execute("UPDATE %s SET v = null WHERE pk = 0 AND ck = ?", ck(i)); // cell tombstone, no row marker (audit amendment R1)
            execute("INSERT INTO %s (pk, ck, v) VALUES (1, ?, '')", ck(i));   // live row (control)
        }
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        Util.flush(cfs);

        int[] ts = { 1_000, 10_000, 20_000, N - 1, N, 100_000, Integer.MAX_VALUE };
        try (PrintWriter out = new PrintWriter(new FileWriter("build/test/tft-unit.tsv")))
        {
            out.println("pk\tT\toutcome\tcount_at_throw\tresp_bytes\tunfiltered_in_resp\talloc_median\talloc_min\talloc_max");
            for (int pk : new int[]{ 0, 1 })
                for (int t : ts)
                {
                    DatabaseDescriptor.setTombstoneFailureThreshold(t);
                    long[] alloc = new long[REPS];
                    String outcome = "?"; long count = -1, respBytes = -1; int unf = -1;
                    for (int r = 0; r < REPS; r++)
                    {
                        SinglePartitionReadCommand cmd = (SinglePartitionReadCommand) Util.cmd(cfs, pk).build();
                        long a0 = allocated();
                        try (ReadExecutionController ec = cmd.executionController();
                             UnfilteredPartitionIterator it = cmd.executeLocally(ec))
                        {
                            ReadResponse resp = cmd.createResponse(it, ec.getRepairedDataInfo());
                            alloc[r] = allocated() - a0;
                            respBytes = ReadResponse.serializer.serializedSize(resp, MessagingService.current_version);
                            unf = countUnfiltered(resp, cmd);
                            outcome = "OK";
                        }
                        catch (TombstoneOverwhelmingException e)
                        {
                            alloc[r] = allocated() - a0;
                            Matcher m = P.matcher(e.getMessage());
                            count = m.find() ? Long.parseLong(m.group(1)) : -2;
                            outcome = "TOE"; respBytes = -1; unf = -1;
                        }
                    }
                    Arrays.sort(alloc);
                    String line = pk + "\t" + t + "\t" + outcome + "\t" + count + "\t" + respBytes + "\t" + unf
                                  + "\t" + alloc[REPS / 2] + "\t" + alloc[0] + "\t" + alloc[REPS - 1];
                    out.println(line);
                    System.out.println("TFT " + line);
                }
        }
    }
}
