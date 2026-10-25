/* Stage-4 harness (not upstream): unit tier of cases/lcs-level-capacity-shouldSwitchWriterInCurrentLocation-totalWrittenInLevel--autonomous.md (B2, as amended B2i). */
package org.apache.cassandra.db.compaction.writers;

import org.junit.Test;

import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.lifecycle.LifecycleTransaction;

public class LcsFanoutCapacityTest extends WriterHarnessBase
{
    /** B2i.1: STCS input, then ALTER to LCS with fanout F; the writer's S = total / divisor */
    private void arm(String tag, int fanout, int divisor) throws Throwable
    {
        ColumnFamilyStore cfs = newInputTable(false);
        populate(0, partitions());
        flushToOneSSTable(cfs);
        alterTable("ALTER TABLE %s WITH compaction = {'class': 'LeveledCompactionStrategy', 'fanout_size': '" + fanout + "', 'sstable_size_in_mb': '1'}");
        cfs.disableAutoCompaction();
        if (cfs.getLevelFanoutSize() != fanout)
            throw new IllegalStateException("getLevelFanoutSize()=" + cfs.getLevelFanoutSize() + " expected " + fanout);
        LifecycleTransaction txn = openTxn(cfs);
        long total = txn.originals().iterator().next().onDiskLength();
        runArm(tag, cfs, txn, total / divisor, "F=" + fanout + " S=total/" + divisor + " total=" + total + " fanoutSeenByWriter=" + cfs.getLevelFanoutSize());
    }

    @Test public void f2() throws Throwable { arm("f2", 2, 50); }
    @Test public void f4() throws Throwable { arm("f4", 4, 50); }
    @Test public void f10() throws Throwable { arm("f10", 10, 50); }
    @Test public void f41() throws Throwable { arm("f41", 41, 50); }
    @Test public void f10s20() throws Throwable { arm("f10s20", 10, 20); }
    @Test public void f10s100() throws Throwable { arm("f10s100", 10, 100); }
}
