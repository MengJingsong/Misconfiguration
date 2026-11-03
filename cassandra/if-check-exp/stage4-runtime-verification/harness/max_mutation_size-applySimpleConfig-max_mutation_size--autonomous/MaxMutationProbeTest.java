package org.apache.cassandra.probe;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.ByteBuffer;

import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.IMutation;
import org.apache.cassandra.db.Mutation;
import org.apache.cassandra.db.commitlog.CommitLog;
import org.apache.cassandra.db.commitlog.CommitLogPosition;
import org.apache.cassandra.db.partitions.PartitionUpdate;
import org.apache.cassandra.net.MessagingService;

/**
 * Stage-4 harness, unit tier B2 (amended 2026-10-25) of
 * max_mutation_size-applySimpleConfig-max_mutation_size--autonomous.
 * One JVM per max_mutation_size value (appended to test/conf/cassandra.yaml by unit-run.sh; S = 5 MiB from line 10).
 * Writes STAGE4 lines to -Dstage4.out (label -Dstage4.label). It records; it asserts nothing about the claim.
 */
public class MaxMutationProbeTest extends CQLTester
{
    static PrintWriter out;
    static String label;
    static long M;

    static synchronized void w(String s)
    {
        String line = "STAGE4 " + label + " " + s;
        out.println(line);
        out.flush();
        System.out.println(line);
    }

    static long oversized()
    {
        return CommitLog.instance.metrics.oversizedMutations.getCount();
    }

    /** bytes allocated between two positions: delta in the same segment, else the position in the new segment */
    static long allocated(CommitLogPosition a, CommitLogPosition b)
    {
        return a.segmentId == b.segmentId ? (long) b.position - a.position : b.position;
    }

    static String chain(Throwable t)
    {
        StringBuilder sb = new StringBuilder();
        boolean mems = false;
        for (Throwable c = t; c != null; c = c.getCause())
        {
            if (sb.length() > 0) sb.append(">");
            sb.append(c.getClass().getName());
            if (c instanceof org.apache.cassandra.db.MutationExceededMaxSizeException) mems = true;
        }
        return sb + " mems_in_chain=" + mems + " is_ire=" + (t instanceof org.apache.cassandra.exceptions.InvalidRequestException);
    }

    static String frames(Throwable t)
    {
        StringBuilder sb = new StringBuilder();
        StackTraceElement[] st = t.getStackTrace();
        for (int i = 0; i < Math.min(4, st.length); i++)
            sb.append(i == 0 ? "" : "<").append(st[i].getClassName().replaceAll(".*\\.", "")).append('.').append(st[i].getMethodName());
        return sb.toString();
    }

    static long total(String msg)
    {
        // "Rejected an oversized mutation (<t>/<M>) ..."
        int i = msg.indexOf("oversized mutation (");
        if (i < 0) return -1;
        int j = msg.indexOf('/', i);
        return Long.parseLong(msg.substring(i + "oversized mutation (".length(), j));
    }

    /** returns the reported total if refused with a parseable message, 0 if accepted, -1 if refused otherwise */
    long cqlInsert(String what, int key, int blob) throws Throwable
    {
        long c0 = oversized();
        CommitLogPosition p0 = CommitLog.instance.getCurrentPosition();
        String outcome, cls = "-", msg = "-";
        long t = 0;
        try
        {
            execute("INSERT INTO %s (k, v) VALUES (?, ?)", key, ByteBuffer.allocate(blob));
            outcome = "ACCEPTED";
        }
        catch (Throwable e)
        {
            outcome = "REFUSED";
            cls = chain(e);
            msg = String.valueOf(e.getMessage());
            t = total(msg);
            if (msg.length() > 160) msg = msg.substring(0, 160);
        }
        CommitLogPosition p1 = CommitLog.instance.getCurrentPosition();
        long c1 = oversized();
        boolean present = execute("SELECT k FROM %s WHERE k = ?", key).size() == 1;
        w("insert what=" + what + " key=" + key + " blob=" + blob + " outcome=" + outcome + " total=" + (t > 0 ? t : -1)
          + " max=" + M + " delta_count=" + (c1 - c0) + " seg0=" + p0.segmentId + " pos0=" + p0.position + " seg1=" + p1.segmentId
          + " pos1=" + p1.position + " allocated=" + allocated(p0, p1) + " row_present=" + present + " class=" + cls
          + " msg=" + msg.replace('\n', ' '));
        return outcome.equals("ACCEPTED") ? 0 : t;
    }

    void directAdd(String what, int key, int blob) throws Throwable
    {
        PartitionUpdate.SimpleBuilder pb = PartitionUpdate.simpleBuilder(getCurrentColumnFamilyStore().metadata(), key);
        pb.row().add("v", ByteBuffer.allocate(blob));
        Mutation m = pb.buildAsMutation();
        long ser = m.serializedSize(MessagingService.current_version);
        long c0 = oversized();
        CommitLogPosition p0 = CommitLog.instance.getCurrentPosition();
        String outcome, cls = "-", msg = "-", fr = "-";
        try
        {
            CommitLogPosition r = CommitLog.instance.add(m);
            outcome = "ACCEPTED returned_seg=" + r.segmentId + " returned_pos=" + r.position;
        }
        catch (Throwable e)
        {
            outcome = "REFUSED";
            cls = chain(e);
            fr = frames(e);
            msg = String.valueOf(e.getMessage());
            if (msg.length() > 160) msg = msg.substring(0, 160);
        }
        CommitLogPosition p1 = CommitLog.instance.getCurrentPosition();
        long c1 = oversized();
        w("direct what=" + what + " key=" + key + " blob=" + blob + " serialized=" + ser + " total=" + (ser + 12) + " max=" + M
          + " outcome=" + outcome.split(" ")[0] + " delta_count=" + (c1 - c0) + " seg0=" + p0.segmentId + " pos0=" + p0.position
          + " seg1=" + p1.segmentId + " pos1=" + p1.position + " allocated=" + allocated(p0, p1) + " frames=" + fr
          + " class=" + cls + " detail=" + outcome.replace(' ', ';') + " msg=" + msg.replace('\n', ' '));
    }

    @Test
    public void probe() throws Throwable
    {
        label = System.getProperty("stage4.label", "?");
        out = new PrintWriter(new FileWriter(System.getProperty("stage4.out"), true));
        M = DatabaseDescriptor.getMaxMutationSize();
        w("run S=" + DatabaseDescriptor.getCommitLogSegmentSize() + " getMaxMutationSize=" + M
          + " IMutation.MAX_MUTATION_SIZE=" + IMutation.MAX_MUTATION_SIZE + " accessMode=" + DatabaseDescriptor.getCommitLogWriteDiskAccessMode());
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob)");

        // (1), (2)
        cqlInsert("A", 1, (int) (M - 1024));
        int B = (int) (M + 1024);
        long tB = cqlInsert("B", 2, B);

        // (3) exact boundary search
        long k = tB > 0 ? tB - B : 67;
        long x = M - k + 9;
        int key = 100;
        boolean converged = false;
        for (int i = 0; i < 6; i++)
        {
            long t = cqlInsert("search" + i, key++, (int) x);
            if (t == 0) { x += 16; continue; }
            if (t < 0) break;
            if (t == M + 1) { converged = true; break; }
            x -= (t - (M + 1));
        }
        w("boundary converged=" + converged + " x=" + x + " k_from_B=" + k);
        if (converged)
            cqlInsert("edge", key++, (int) (x - 1));

        // (4) direct CommitLog.add (replica-side check)
        directAdd("over", 900, (int) (M + 1024));
        directAdd("under", 901, (int) (M - 1024));

        // (5) 50 near-limit inserts
        long c0 = oversized();
        CommitLogPosition p0 = CommitLog.instance.getCurrentPosition();
        long t0 = System.currentTimeMillis();
        int ok = 0, bad = 0;
        for (int i = 0; i < 50; i++)
        {
            try
            {
                execute("INSERT INTO %s (k, v) VALUES (?, ?)", 1000 + i, ByteBuffer.allocate((int) (M - 1024)));
                ok++;
            }
            catch (Throwable e)
            {
                bad++;
                w("workload-error i=" + i + " " + e);
            }
        }
        CommitLogPosition p1 = CommitLog.instance.getCurrentPosition();
        w("workload rows=50 blob=" + (M - 1024) + " ok=" + ok + " failed=" + bad + " delta_count=" + (oversized() - c0)
          + " seg0=" + p0.segmentId + " seg1=" + p1.segmentId + " seg_advance=" + (p1.segmentId - p0.segmentId)
          + " ms=" + (System.currentTimeMillis() - t0));
        w("done");
        out.close();
    }
}
