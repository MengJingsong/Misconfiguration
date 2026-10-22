/*
 * Stage-4 harness for commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous (B2i, audit amendment R5, 2026-10-21).
 * Helper called from the Byteman rules of CommitLogTotalSpaceTest. Observation only. Writes one line per event to
 * <clcap.out>.trace:
 *   CHECK  n=<check#> tMs=<ms> onDisk=<bytes> unused=<bytes>
 *   SELECT n=<select#> tMs unused flushingSizeLocal sel=<sum onDiskSize of selected> k older firstId lastId allocId
 *          allocIdAtCheck gap stop259 minimal onDisk
 *   (H1, shakedown 2026-10-21: "older" is counted when the rule runs and races with discards; "gap" = allocId - lastId - 1,
 *    from segment ids, is the race-free count of older segments left unselected; allocIdAtCheck flags a concurrent switch.)
 *   FLUSH  sel=<select#> tMs table=<ks.tbl> switch=<mayContainDataBefore>
 * Copy to <clone>/test/unit/org/apache/cassandra/db/commitlog/.
 */
package org.apache.cassandra.db.commitlog;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.List;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ColumnFamilyStore;

public class CLCapTrace
{
    private static PrintWriter w;
    private static int checks = 0, selects = 0;
    private static long allocIdAtCheck = -1;

    private static synchronized PrintWriter out()
    {
        if (w == null)
        {
            try
            {
                w = new PrintWriter(new FileWriter(System.getProperty("clcap.out", "build/test/clcap.csv") + ".trace", true), true);
            }
            catch (Exception e) { throw new RuntimeException(e); }
        }
        return w;
    }

    public static synchronized void check(AbstractCommitLogSegmentManager mgr, CommitLogSegment allocatingFrom)
    {
        allocIdAtCheck = allocatingFrom == null ? -1 : allocatingFrom.id;
        long cap = DatabaseDescriptor.getTotalCommitlogSpaceInMiB() << 20;
        long sz = mgr.onDiskSize();
        out().println("CHECK n=" + (++checks) + " tMs=" + System.currentTimeMillis() + " onDisk=" + sz + " unused=" + (cap - sz) + " allocId=" + allocIdAtCheck);
    }

    public static synchronized void select(AbstractCommitLogSegmentManager mgr, long unused, long flushingSizeLocal,
                                           List<CommitLogSegment> selected, CommitLogSegment allocatingFrom)
    {
        long sel = 0, last = 0, firstId = -1, lastId = -1;
        for (CommitLogSegment s : selected) { last = s.onDiskSize(); sel += last; if (firstId < 0) firstId = s.id; lastId = s.id; }
        long allocId = allocatingFrom == null ? -1 : allocatingFrom.id;
        // gap = older segments left unselected between the last selected one and allocatingFrom (ids are consecutive)
        long gap = allocId - lastId - 1;
        int older = 0;
        for (CommitLogSegment s : mgr.getActiveSegments())
        {
            if (s == allocatingFrom) break;
            older++;
        }
        boolean stop259 = sel + unused >= 0;
        boolean minimal = sel - last + unused < 0;
        out().println("SELECT n=" + (++selects) + " tMs=" + System.currentTimeMillis() + " unused=" + unused
                      + " flushingSizeLocal=" + flushingSizeLocal + " sel=" + sel + " k=" + selected.size()
                      + " older=" + older + " firstId=" + firstId + " lastId=" + lastId + " allocId=" + allocId
                      + " allocIdAtCheck=" + allocIdAtCheck + " gap=" + gap + " stop259=" + stop259 + " minimal=" + minimal + " onDisk=" + mgr.onDiskSize());
    }

    public static synchronized void flush(ColumnFamilyStore cfs, CommitLogPosition pos)
    {
        boolean sw = cfs.getTracker().getView().getCurrentMemtable().mayContainDataBefore(pos);
        out().println("FLUSH sel=" + selects + " tMs=" + System.currentTimeMillis() + " table=" + cfs.getKeyspaceName() + "." + cfs.name
                      + " switch=" + sw);
    }
}
