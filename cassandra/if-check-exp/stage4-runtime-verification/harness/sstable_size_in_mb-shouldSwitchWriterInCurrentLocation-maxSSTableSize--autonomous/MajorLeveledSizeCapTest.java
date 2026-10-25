/* Stage-4 harness (not upstream): unit tier of cases/sstable_size_in_mb-shouldSwitchWriterInCurrentLocation-maxSSTableSize--autonomous.md (B2, as amended B2i). */
package org.apache.cassandra.db.compaction.writers;

import org.junit.Test;

import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.lifecycle.LifecycleTransaction;

public class MajorLeveledSizeCapTest extends WriterHarnessBase
{
    /** S = total / divisor; divisor 0 means Long.MAX_VALUE */
    private void arm(String tag, int divisor, boolean compressed) throws Throwable
    {
        ColumnFamilyStore cfs = newInputTable(compressed);
        populate(0, partitions());
        flushToOneSSTable(cfs);
        LifecycleTransaction txn = openTxn(cfs);
        long total = txn.originals().iterator().next().onDiskLength();
        long s = divisor == 0 ? Long.MAX_VALUE : total / divisor;
        runArm(tag, cfs, txn, s, "S=" + (divisor == 0 ? "MAX" : "total/" + divisor) + " compressed=" + compressed + " total=" + total);
    }

    @Test public void s10() throws Throwable { arm("s10", 10, false); }
    @Test public void s50() throws Throwable { arm("s50", 50, false); }
    @Test public void s200() throws Throwable { arm("s200", 200, false); }
    @Test public void smax() throws Throwable { arm("smax", 0, false); }
    @Test public void s50Compressed() throws Throwable { arm("s50z", 50, true); }

    /** B2i.4: S = 4 MiB, 10,000 small partitions + one 12 MiB partition (key -1, 12,288 rows of 1 KiB) */
    @Test public void wide() throws Throwable
    {
        ColumnFamilyStore cfs = newInputTable(false);
        populate(0, Math.min(partitions(), 10000));
        populateWide(-1, 12288, BLOB);
        flushToOneSSTable(cfs);
        LifecycleTransaction txn = openTxn(cfs);
        long total = txn.originals().iterator().next().onDiskLength();
        runArm("wide", cfs, txn, 4L * 1024 * 1024, "S=4MiB wide=12MiB total=" + total);
    }
}
