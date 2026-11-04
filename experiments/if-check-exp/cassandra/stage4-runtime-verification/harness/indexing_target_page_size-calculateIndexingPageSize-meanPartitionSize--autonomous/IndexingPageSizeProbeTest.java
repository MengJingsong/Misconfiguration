/*
 * Stage-4 probe (unit tier, B2 as amended 2026-10-26) of
 * indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous.
 * Copied into the run clone at test/unit/org/apache/cassandra/index/ by unit-run.sh and removed afterwards.
 *
 * For each case it reads the table statistics, calls SecondaryIndexManager.calculateIndexingPageSize() (ps),
 * then drives SecondaryIndexManager.indexPartition(key, {probe index}, ps) -- the call CollatedViewIndexBuilder.build()
 * makes (CollatedViewIndexBuilder.java:82) -- and records, per page (one Indexer begin()..finish()), the non-static rows,
 * the sum of Row.dataSize() over them, and the static rows. It asserts nothing beyond completion (B2e step 5).
 * Output: one ITP line per System.out write.
 */
package org.apache.cassandra.index;

import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.db.RegularAndStaticColumns;
import org.apache.cassandra.db.WriteContext;
import org.apache.cassandra.db.memtable.Memtable;
import org.apache.cassandra.db.rows.Row;
import org.apache.cassandra.index.transactions.IndexTransaction;
import org.apache.cassandra.schema.IndexMetadata;
import org.apache.cassandra.utils.ByteBufferUtil;

public class IndexingPageSizeProbeTest extends CQLTester
{
    static final String PROP = "cassandra.force_default_indexing_page_size";
    static final int ROWS = 2000;
    static final int REPS = 3;

    /** StubIndex whose indexer counts per page instead of retaining rows. */
    public static class PageProbeIndex extends StubIndex
    {
        public final List<long[]> pages = Collections.synchronizedList(new ArrayList<>());

        public PageProbeIndex(ColumnFamilyStore baseCfs, IndexMetadata metadata)
        {
            super(baseCfs, metadata);
        }

        @Override
        public Indexer indexerFor(DecoratedKey key, RegularAndStaticColumns columns, long nowInSec, WriteContext ctx,
                                  IndexTransaction.Type transactionType, Memtable memtable)
        {
            return new Indexer()
            {
                long rows, bytes, statics, maxRow;

                public void begin()
                {
                    rows = 0; bytes = 0; statics = 0; maxRow = 0;
                }

                public void insertRow(Row row)
                {
                    if (row.isStatic()) { statics++; return; }
                    rows++;
                    int d = row.dataSize();
                    bytes += d;
                    if (d > maxRow) maxRow = d;
                }

                public void finish()
                {
                    pages.add(new long[]{ rows, bytes, statics, maxRow });
                }
            };
        }
    }

    @BeforeClass
    public static void thresholdsOff()
    {
        // test/conf/cassandra.yaml:63-69 enables read thresholds; turned off so a large read cannot be rejected
        DatabaseDescriptor.setReadThresholdsEnabled(false);
        System.out.println("ITP SETUP read_thresholds_enabled=" + DatabaseDescriptor.getReadThresholdsEnabled()
                           + " maxHeap=" + Runtime.getRuntime().maxMemory());
    }

    private PageProbeIndex probe(String indexName)
    {
        return (PageProbeIndex) getCurrentColumnFamilyStore().indexManager.getIndexByName(indexName);
    }

    private void measure(String label, PageProbeIndex idx, boolean force)
    {
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        for (int rep = 1; rep <= REPS; rep++)
        {
            System.setProperty(PROP, Boolean.toString(force));
            double mps = cfs.getMeanPartitionSize();
            int mc = cfs.getMeanEstimatedCellPerPartitionCount();
            int cols = cfs.metadata().regularColumns().size();
            int ps = cfs.indexManager.calculateIndexingPageSize();
            idx.pages.clear();
            long t0 = System.nanoTime();
            cfs.indexManager.indexPartition(cfs.decorateKey(ByteBufferUtil.bytes(0)), Collections.singleton(idx), ps);
            long ms = (System.nanoTime() - t0) / 1_000_000;
            long[] rows = new long[idx.pages.size()], bytes = new long[idx.pages.size()];
            long statics = 0, maxRows = 0, maxBytes = 0, total = 0, maxRow = 0;
            for (int i = 0; i < rows.length; i++)
            {
                long[] p = idx.pages.get(i);
                rows[i] = p[0]; bytes[i] = p[1]; statics += p[2];
                maxRows = Math.max(maxRows, p[0]); maxBytes = Math.max(maxBytes, p[1]); total += p[0];
                maxRow = Math.max(maxRow, p[3]);
            }
            System.out.println("ITP CASE case=" + label + " k1=" + force + " rep=" + rep
                               + " prop=" + System.getProperty(PROP)
                               + " sstables=" + cfs.getLiveSSTables().size()
                               + " meanPartitionSize=" + mps + " meanCells=" + mc + " regularCols=" + cols
                               + " ps=" + ps + " pages=" + rows.length + " totalRows=" + total + " staticRows=" + statics
                               + " maxRows=" + maxRows + " maxBytes=" + maxBytes + " maxRowDataSize=" + maxRow + " ms=" + ms
                               + " rowsPerPage=" + Arrays.toString(rows).replace(" ", "")
                               + " bytesPerPage=" + Arrays.toString(bytes).replace(" ", ""));
        }
        System.clearProperty(PROP);
    }

    private static String cvalue(int i)
    {
        StringBuilder sb = new StringBuilder(60000);
        sb.append(String.format("%05d", i));
        for (int j = 0; j < 59995; j++) sb.append('a');
        return sb.toString();
    }

    /** T1: one regular blob column, 2000 rows of 65,536 B in k=0, flushed; K1 false then true. */
    @Test
    public void t1() throws Throwable
    {
        createTable("CREATE TABLE %s (k int, c int, v blob, PRIMARY KEY (k, c))");
        disableCompaction();
        String name = createIndexAsync("CREATE CUSTOM INDEX itp_t1 ON %s(v) USING '" + PageProbeIndex.class.getName() + "'");
        for (int i = 0; i < ROWS; i++)
        {
            byte[] b = new byte[65536];
            Arrays.fill(b, (byte) i);
            execute("INSERT INTO %s (k, c, v) VALUES (?, ?, ?)", 0, i, ByteBuffer.wrap(b));
        }
        flush();
        PageProbeIndex idx = probe(name);
        measure("T1", idx, false);
        measure("T1", idx, true);
    }

    /** T2: zero regular columns (c text clustering of 60,000 chars, s int static); guard :1164. */
    @Test
    public void t2() throws Throwable
    {
        createTable("CREATE TABLE %s (k int, c text, s int static, PRIMARY KEY (k, c))");
        disableCompaction();
        String name = createIndexAsync("CREATE CUSTOM INDEX itp_t2 ON %s(c) USING '" + PageProbeIndex.class.getName() + "'");
        for (int i = 0; i < ROWS; i++)
            execute("INSERT INTO %s (k, c, s) VALUES (?, ?, ?)", 0, cvalue(i), 1);
        flush();
        measure("T2", probe(name), false);
    }

    /** T2b: T2 plus one regular column v int = 1 in every row (control for T2). */
    @Test
    public void t2b() throws Throwable
    {
        createTable("CREATE TABLE %s (k int, c text, s int static, v int, PRIMARY KEY (k, c))");
        disableCompaction();
        String name = createIndexAsync("CREATE CUSTOM INDEX itp_t2b ON %s(c) USING '" + PageProbeIndex.class.getName() + "'");
        for (int i = 0; i < ROWS; i++)
            execute("INSERT INTO %s (k, c, s, v) VALUES (?, ?, ?, ?)", 0, cvalue(i), 1, 1);
        flush();
        measure("T2b", probe(name), false);
    }

    /** T3: T1 schema, 10 rows, no flush (no sstables); guard :1156. */
    @Test
    public void t3() throws Throwable
    {
        createTable("CREATE TABLE %s (k int, c int, v blob, PRIMARY KEY (k, c))");
        disableCompaction();
        String name = createIndexAsync("CREATE CUSTOM INDEX itp_t3 ON %s(v) USING '" + PageProbeIndex.class.getName() + "'");
        for (int i = 0; i < 10; i++)
        {
            byte[] b = new byte[65536];
            Arrays.fill(b, (byte) i);
            execute("INSERT INTO %s (k, c, v) VALUES (?, ?, ?)", 0, i, ByteBuffer.wrap(b));
        }
        measure("T3", probe(name), false);
    }
}
