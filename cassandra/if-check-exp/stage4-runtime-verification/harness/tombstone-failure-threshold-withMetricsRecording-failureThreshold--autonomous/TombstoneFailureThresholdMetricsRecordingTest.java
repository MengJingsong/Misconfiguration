// Stage-4 harness for the B2 tier of
// stage3-ai-deep-read/cases/tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous.md
// (frozen sha256 4c289eb0..., amendments A1-A4, 2026-10-26).
// pk 0: N row deletions (DELETE ... WHERE pk=0 AND ck=?), gc_grace 864000, flushed (B2c).
// pk 1: NLIVE live rows with a 1 KB v: negative control (no tombstones) and positive-control arm (A3).
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
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.filter.LocalReadSizeTooLargeException;
import org.apache.cassandra.db.filter.TombstoneOverwhelmingException;
import org.apache.cassandra.db.partitions.UnfilteredPartitionIterator;
import org.apache.cassandra.db.rows.UnfilteredRowIterator;
import org.apache.cassandra.net.MessagingService;

public class TombstoneFailureThresholdMetricsRecordingTest extends CQLTester
{
    static final int N = 120_000;
    static final int NLIVE = 30_000;
    static final int REPS = 5;
    static int ORIG_T, ORIG_W;
    static boolean ORIG_RT;
    static DataStorageSpec.LongBytesBound ORIG_LRS;
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static final Pattern P = Pattern.compile("Scanned over (\\d+) tombstones");

    @BeforeClass
    public static void save()
    {
        ORIG_T = DatabaseDescriptor.getTombstoneFailureThreshold();
        ORIG_W = DatabaseDescriptor.getTombstoneWarnThreshold();
        ORIG_RT = DatabaseDescriptor.getReadThresholdsEnabled();
        ORIG_LRS = DatabaseDescriptor.getLocalReadSizeFailThreshold();
        DatabaseDescriptor.setReadThresholdsEnabled(false);   // A1: node default (Config.java:526)
    }

    @AfterClass
    public static void restore()
    {
        DatabaseDescriptor.setTombstoneFailureThreshold(ORIG_T);
        DatabaseDescriptor.setTombstoneWarnThreshold(ORIG_W);
        DatabaseDescriptor.setReadThresholdsEnabled(ORIG_RT);
        DatabaseDescriptor.setLocalReadSizeFailThreshold(ORIG_LRS);
    }

    static long allocated() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }

    static long usedAfterGc() throws InterruptedException
    {
        for (int i = 0; i < 3; i++) { System.gc(); Thread.sleep(200); }
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

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
        createTable("CREATE TABLE %s (pk int, ck int, v text, PRIMARY KEY (pk, ck)) WITH gc_grace_seconds = 864000");
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 1000; i++) sb.append('y');
        String kb = sb.toString();
        for (int i = 0; i < N; i++)
            execute("DELETE FROM %s WHERE pk = 0 AND ck = ?", i);                          // row deletion: counted at ReadCommand.java:569-576
        for (int i = 0; i < NLIVE; i++)
            execute("INSERT INTO %s (pk, ck, v) VALUES (1, ?, ?)", i, kb);                 // live control
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        Util.flush(cfs);
        DatabaseDescriptor.setTombstoneWarnThreshold(500);

        // warm-up (not a reading): one succeeding and one aborting read on each partition, so one-off allocation is out of the sweep
        for (int w = 0; w < 2; w++)
            for (int t : new int[]{ Integer.MAX_VALUE, 1_000 })
            {
                DatabaseDescriptor.setTombstoneFailureThreshold(t);
                SinglePartitionReadCommand cmd = (SinglePartitionReadCommand) Util.cmd(cfs, 0).build();
                try (ReadExecutionController ec = cmd.executionController();
                     UnfilteredPartitionIterator it = cmd.executeLocally(ec))
                { cmd.createResponse(it, ec.getRepairedDataInfo()); }
                catch (TombstoneOverwhelmingException e) { }
            }
        int[] ts = { 1_000, 10_000, 100_000, N, 200_000, Integer.MAX_VALUE };
        try (PrintWriter out = new PrintWriter(new FileWriter("build/test/tfm-unit.tsv")))
        {
            out.println("arm\tpk\tT\toutcome\tcount_at_throw\tresp_bytes\tunfiltered_in_resp\talloc_median\talloc_min\talloc_max\tfail_delta\twarn_delta\tretained_bytes");
            for (int pk : new int[]{ 0, 1 })
                for (int t : ts)
                {
                    DatabaseDescriptor.setTombstoneFailureThreshold(t);
                    long f0 = cfs.metric.tombstoneFailures.getCount(), w0 = cfs.metric.tombstoneWarnings.getCount();
                    long[] alloc = new long[REPS];
                    String outcome = "?"; long count = -1, respBytes = -1, retained = -1; int unf = -1;
                    for (int r = 0; r < REPS; r++)
                    {
                        SinglePartitionReadCommand cmd = (SinglePartitionReadCommand) Util.cmd(cfs, pk).build();
                        long u0 = r == 0 ? usedAfterGc() : 0;
                        long a0 = allocated();
                        try (ReadExecutionController ec = cmd.executionController();
                             UnfilteredPartitionIterator it = cmd.executeLocally(ec))
                        {
                            ReadResponse resp = cmd.createResponse(it, ec.getRepairedDataInfo());
                            alloc[r] = allocated() - a0;
                            respBytes = ReadResponse.serializer.serializedSize(resp, MessagingService.current_version);
                            if (r == 0) retained = usedAfterGc() - u0;                       // secondary: response held while the GC runs
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
                    String line = "sweep\t" + pk + "\t" + t + "\t" + outcome + "\t" + count + "\t" + respBytes + "\t" + unf
                                  + "\t" + alloc[REPS / 2] + "\t" + alloc[0] + "\t" + alloc[REPS - 1]
                                  + "\t" + (cfs.metric.tombstoneFailures.getCount() - f0) + "\t" + (cfs.metric.tombstoneWarnings.getCount() - w0) + "\t" + retained;
                    out.println(line);
                    System.out.println("TFM " + line);
                }

            // A3 positive control: a different cap on the same resource (local_read_size_fail_threshold), live rows pk 1
            DatabaseDescriptor.setTombstoneFailureThreshold(ORIG_T);
            for (String arm : new String[]{ "ctl-off", "ctl-1MiB" })
            {
                boolean on = arm.equals("ctl-1MiB");
                DatabaseDescriptor.setReadThresholdsEnabled(on);
                DatabaseDescriptor.setLocalReadSizeFailThreshold(on ? new DataStorageSpec.LongBytesBound("1MiB") : null);
                long[] alloc = new long[REPS];
                String outcome = "?"; long respBytes = -1; int unf = -1;
                for (int r = 0; r < REPS; r++)
                {
                    SinglePartitionReadCommand cmd = (SinglePartitionReadCommand) Util.cmd(cfs, 1).build();
                    cmd.trackWarnings();
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
                    catch (LocalReadSizeTooLargeException e)
                    {
                        alloc[r] = allocated() - a0;
                        outcome = "LRS"; respBytes = -1; unf = -1;
                    }
                }
                Arrays.sort(alloc);
                String line = arm + "\t1\t" + ORIG_T + "\t" + outcome + "\t-1\t" + respBytes + "\t" + unf + "\t" + alloc[REPS / 2] + "\t" + alloc[0] + "\t" + alloc[REPS - 1] + "\t0\t0\t-1";
                out.println(line);
                System.out.println("TFM " + line);
            }
            DatabaseDescriptor.setReadThresholdsEnabled(false);
        }
    }
}
