/* Stage-4 harness (not upstream): unit tier of cases/DEFAULT_SMALLEST_SSTABLE_BYTES-shouldSwitchWriterInCurrentLocation-getEstimatedOnDiskBytesWritten--autonomous.md (B2, as amended B2i). */
package org.apache.cassandra.db.compaction.writers;

import org.junit.Test;

import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.lifecycle.LifecycleTransaction;

public class SplittingConstantProbeTest extends SplitWriterHarnessBase
{
    private static final long DEFAULT = SplittingSizeTieredCompactionWriter.DEFAULT_SMALLEST_SSTABLE_BYTES;

    /** smallest < 0 means 10 * T (a value larger than the input); parts = number of 10-row partitions */
    private void split(String tag, long smallest, int parts, boolean compressed) throws Throwable
    {
        ColumnFamilyStore cfs = newInputTable(compressed);
        populate(0, parts);
        flushToOneSSTable(cfs);
        LifecycleTransaction txn = openTxn(cfs);
        long total = txn.originals().iterator().next().onDiskLength();
        long s = smallest < 0 ? 10 * total : smallest;
        RecSplit w = new RecSplit(cfs, cfs.getDirectories(), txn, txn.originals(), s);
        runArm(tag, cfs, txn, w, "split", Long.toString(s), "compressed=" + compressed + " T=" + total);
    }

    private void max(String tag, long m, int parts) throws Throwable
    {
        ColumnFamilyStore cfs = newInputTable(false);
        populate(0, parts);
        flushToOneSSTable(cfs);
        LifecycleTransaction txn = openTxn(cfs);
        RecMax w = new RecMax(cfs, cfs.getDirectories(), txn, txn.originals(), m);
        runArm(tag, cfs, txn, w, "max", Long.toString(m), "compressed=false");
    }

    @Test public void d50() throws Throwable { split("d50", DEFAULT, partitions(), false); }
    @Test public void d0() throws Throwable { split("d0", 0, partitions(), false); }
    @Test public void d5() throws Throwable { split("d5", 5_000_000L, partitions(), false); }
    @Test public void dbig() throws Throwable { split("dbig", -1, partitions(), false); }
    @Test public void small() throws Throwable { split("small", DEFAULT, Math.max(1, partitions() * 3800 / 20000), false); }
    @Test public void d50z() throws Throwable { split("d50z", DEFAULT, partitions(), true); }
    @Test public void ctl20() throws Throwable { max("ctl20", 20_000_000L, partitions()); }
    @Test public void ctl40() throws Throwable { max("ctl40", 40_000_000L, partitions()); }
}
