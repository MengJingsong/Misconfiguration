/*
 * Stage-4 harness: repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous, unit tier (B2e).
 * Not upstream code. The body is the case file's B2e skeleton verbatim; only the imports listed in B2e were added
 * (and java.util.* covers Collection/Collections/Map/NoSuchElementException). Copied into
 * test/unit/org/apache/cassandra/repair/ of a clone at cassandra-5.0.9 by unit-run.sh.
 * Readings are the stdout lines (REJECTED/ACCEPTED, getter, set .. getter, d=.. size=.. heapDelta=.., control ..),
 * read from build/test/output/TEST-org.apache.cassandra.repair.TreeDepthSetterTest.xml.
 */
package org.apache.cassandra.repair;

import java.util.*;

import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.*;
import org.apache.cassandra.db.rows.UnfilteredRowIterator;
import org.apache.cassandra.dht.*;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.service.StorageService;
import org.apache.cassandra.utils.MerkleTrees;

public class TreeDepthSetterTest extends org.apache.cassandra.cql3.CQLTester {
  static ValidationPartitionIterator stub(Range<Token> r, long n, TableMetadata md) {
    return new ValidationPartitionIterator() {
      public long getEstimatedBytes() { return 0; } public long estimatedPartitions() { return n; }
      public long getBytesRead() { return 0; } public Map<Range<Token>, Long> getRangePartitionCounts() { return Collections.singletonMap(r, n); }
      public TableMetadata metadata() { return md; } public boolean hasNext() { return false; }
      public UnfilteredRowIterator next() { throw new NoSuchElementException(); } };
  }
  static long used() { for (int i = 0; i < 3; i++) System.gc(); Runtime rt = Runtime.getRuntime(); return rt.totalMemory() - rt.freeMemory(); }
  @Test public void depth() throws Throwable {
    createTable("CREATE TABLE %s (k int PRIMARY KEY, v int)");
    ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
    Token min = cfs.getPartitioner().getMinimumToken(); Range<Token> full = new Range<>(min, min);
    java.lang.reflect.Method m = ValidationManager.class.getDeclaredMethod("createMerkleTrees", ValidationPartitionIterator.class, Collection.class, ColumnFamilyStore.class);
    m.setAccessible(true);
    for (int bad : new int[]{9, 0}) { try { StorageService.instance.setRepairSessionMaximumTreeDepth(bad); System.out.println("ACCEPTED " + bad); }
      catch (IllegalArgumentException e) { System.out.println("REJECTED " + bad); } System.out.println("getter " + DatabaseDescriptor.getRepairSessionMaxTreeDepth()); }
    for (int hi : new int[]{21, 30}) { StorageService.instance.setRepairSessionMaximumTreeDepth(hi); System.out.println("set " + hi + " getter " + DatabaseDescriptor.getRepairSessionMaxTreeDepth()); }
    DatabaseDescriptor.setRepairSessionSpaceInMiB(1024);
    for (int d : new int[]{10, 14, 18, 20}) {
      StorageService.instance.setRepairSessionMaximumTreeDepth(d);
      long u0 = used();
      MerkleTrees t = (MerkleTrees) m.invoke(null, stub(full, 1L << 22, cfs.metadata()), Collections.singletonList(full), cfs);
      t.init(); long u1 = used();
      System.out.printf("d=%d size=%d heapDelta=%d%n", d, t.size(), u1 - u0);
      t.release(); t = null;
    }
    DatabaseDescriptor.setRepairSessionSpaceInMiB(1); StorageService.instance.setRepairSessionMaximumTreeDepth(18);
    MerkleTrees c = (MerkleTrees) m.invoke(null, stub(full, 1L << 22, cfs.metadata()), Collections.singletonList(full), cfs); c.init();
    System.out.println("control space=1MiB d=18 size=" + c.size());
  }
}
