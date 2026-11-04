package org.apache.cassandra.probe;

import java.io.BufferedReader;
import java.io.FileWriter;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.nio.MappedByteBuffer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.cql3.UntypedResultSet;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.IMutation;
import org.apache.cassandra.db.commitlog.AbstractCommitLogSegmentManager;
import org.apache.cassandra.db.commitlog.CommitLog;
import org.apache.cassandra.db.commitlog.CommitLogPosition;
import org.apache.cassandra.db.commitlog.CommitLogSegment;

/**
 * Stage-4 harness, unit tier B2 (amended 2026-10-25) of
 * commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous.
 * One JVM per configuration (commitlog_segment_size set in test/conf/cassandra.yaml by unit-run.sh).
 * Writes STAGE4 lines to -Dstage4.out (label -Dstage4.label). It records; it asserts nothing about the claim.
 */
public class SegmentSizeProbeTest extends CQLTester
{
    static PrintWriter out;
    static String label;

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

    static String stat(java.io.File f)
    {
        try
        {
            Process p = new ProcessBuilder("/usr/bin/stat", "-f", "%z %b", f.getAbsolutePath()).redirectErrorStream(true).start();
            try (BufferedReader r = new BufferedReader(new InputStreamReader(p.getInputStream())))
            {
                String l = r.readLine();
                p.waitFor();
                String[] x = l.trim().split(" ");
                return "apparent=" + x[0] + " alloc=" + (Long.parseLong(x[1]) * 512);
            }
        }
        catch (Exception e)
        {
            return "stat-error=" + e;
        }
    }

    static void readings(String tag, long S) throws Exception
    {
        java.io.File dir = new java.io.File(DatabaseDescriptor.getCommitLogLocation());
        java.io.File[] fs = dir.listFiles((d, n) -> n.startsWith("CommitLog-") && n.endsWith(".log"));
        Arrays.sort(fs);
        int n = 0, eqS = 0, zeroThenS = 0, other = 0;
        for (java.io.File f : fs)
        {
            long len = f.length();
            String note = "";
            if (len == 0)
            {
                Thread.sleep(1000);
                long len2 = f.length();
                note = " reread_after_1s=" + len2;
                if (len2 == S) zeroThenS++;
                else other++;
            }
            else if (len == S) eqS++;
            else other++;
            n++;
            w("file tag=" + tag + " name=" + f.getName() + " length=" + len + note + " " + stat(f));
        }
        long disk = CommitLog.instance.segmentManager.onDiskSize();
        w("files tag=" + tag + " n=" + n + " eqS=" + eqS + " zeroThenS=" + zeroThenS + " other=" + other
          + " onDiskSize=" + disk + " nS=" + (n * S) + " k=" + ((double) disk / S));

        Field bf = CommitLogSegment.class.getDeclaredField("buffer");
        bf.setAccessible(true);
        Field af = AbstractCommitLogSegmentManager.class.getDeclaredField("availableSegment");
        af.setAccessible(true);
        List<CommitLogSegment> segs = new ArrayList<>(CommitLog.instance.segmentManager.getActiveSegments());
        CommitLogSegment spare = (CommitLogSegment) af.get(CommitLog.instance.segmentManager);
        int mapped = 0, capS = 0;
        for (CommitLogSegment s : segs)
        {
            ByteBuffer b = (ByteBuffer) bf.get(s);
            boolean m = b instanceof MappedByteBuffer;
            if (m) mapped++;
            if (b != null && b.capacity() == S) capS++;
            w("segment tag=" + tag + " role=active id=" + s.id + " class=" + s.getClass().getSimpleName() + " mapped=" + m
              + " capacity=" + (b == null ? -1 : b.capacity()));
        }
        if (spare != null)
        {
            ByteBuffer b = (ByteBuffer) bf.get(spare);
            boolean m = b instanceof MappedByteBuffer;
            if (m) mapped++;
            if (b != null && b.capacity() == S) capS++;
            w("segment tag=" + tag + " role=spare id=" + spare.id + " class=" + spare.getClass().getSimpleName() + " mapped=" + m
              + " capacity=" + (b == null ? -1 : b.capacity()));
        }
        int total = segs.size() + (spare == null ? 0 : 1);
        String pool = "";
        for (BufferPoolMXBean p : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (p.getName().equals("mapped"))
                pool = " INFO_mapped_pool_count=" + p.getCount() + " INFO_mapped_pool_capacity=" + p.getTotalCapacity();
        w("segments tag=" + tag + " total=" + total + " mapped=" + mapped + " capacityS=" + capS + pool);
    }

    void bigInsert(String what, int key, int blob, String expect) throws Throwable
    {
        long c0 = oversized();
        String outcome, cls = "-", msg = "-";
        try
        {
            execute("INSERT INTO %s (k, v) VALUES (?, ?)", key, ByteBuffer.allocate(blob));
            outcome = "ACCEPTED";
        }
        catch (Throwable t)
        {
            outcome = "REFUSED";
            cls = t.getClass().getName();
            msg = String.valueOf(t.getMessage());
            if (msg.length() > 200) msg = msg.substring(0, 200);
        }
        long c1 = oversized();
        UntypedResultSet rs = execute("SELECT k FROM %s WHERE k = ?", key);
        w("insert what=" + what + " expect=" + expect + " key=" + key + " blob=" + blob + " outcome=" + outcome + " class=" + cls
          + " oversized_before=" + c0 + " oversized_after=" + c1 + " delta=" + (c1 - c0) + " row_present=" + (rs.size() == 1)
          + " msg=" + msg.replace('\n', ' '));
    }

    @Test
    public void probe() throws Throwable
    {
        label = System.getProperty("stage4.label", "?");
        out = new PrintWriter(new FileWriter(System.getProperty("stage4.out"), true));
        long S = DatabaseDescriptor.getCommitLogSegmentSize();
        long mms = DatabaseDescriptor.getMaxMutationSize();
        w("run S=" + S + " maxMutation=" + mms + " IMutation.MAX_MUTATION_SIZE=" + IMutation.MAX_MUTATION_SIZE
          + " accessMode=" + DatabaseDescriptor.getCommitLogWriteDiskAccessMode() + " compression=" + DatabaseDescriptor.getCommitLogCompression()
          + " commitlogDir=" + DatabaseDescriptor.getCommitLogLocation() + " segmentClass="
          + CommitLog.instance.segmentManager.getActiveSegments().iterator().next().getClass().getSimpleName() + " totalSpaceMiB=" + DatabaseDescriptor.getTotalCommitlogSpaceInMiB());

        createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob)");
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        readings("before-workload", S);
        long sw0 = cfs.metric.memtableSwitchCount.getCount();
        CommitLogPosition p0 = CommitLog.instance.getCurrentPosition();
        int R = (int) (3 * S / 65536);
        int ok = 0;
        long t0 = System.currentTimeMillis();
        for (int i = 0; i < R; i++)
        {
            execute("INSERT INTO %s (k, v) VALUES (?, ?)", i, ByteBuffer.allocate(65536));
            ok++;
        }
        CommitLogPosition p1 = CommitLog.instance.getCurrentPosition();
        long sw1 = cfs.metric.memtableSwitchCount.getCount();
        UntypedResultSet cnt = execute("SELECT count(*) FROM %s");
        w("workload rows=" + R + " ok=" + ok + " count=" + cnt.one().getLong("count") + " ms=" + (System.currentTimeMillis() - t0)
          + " seg0=" + p0.segmentId + " pos0=" + p0.position + " seg1=" + p1.segmentId + " pos1=" + p1.position
          + " n_w=" + (p1.segmentId - p0.segmentId + 1) + " switches=" + (sw1 - sw0));
        readings("after-workload", S);

        boolean control = mms != S / 2;
        int refuse = control ? (int) (S / 2 - 65536) : (int) (S / 2 + 1024);
        int accept = control ? (int) (mms - 65536) : (int) (S / 2 - 65536);
        bigInsert("refused", R, refuse, "REFUSED");
        bigInsert("accepted", R + 1, accept, "ACCEPTED");
        readings("end", S);
        w("done switches_total=" + (cfs.metric.memtableSwitchCount.getCount() - sw0));
        out.close();
    }
}
