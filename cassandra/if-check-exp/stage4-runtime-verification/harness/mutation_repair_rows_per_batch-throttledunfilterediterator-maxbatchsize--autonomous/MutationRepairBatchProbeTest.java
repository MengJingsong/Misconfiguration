package org.apache.cassandra.db.rows;

import java.io.FileWriter;
import java.io.PrintWriter;

import org.junit.Test;

import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.db.filter.ColumnFilter;
import org.apache.cassandra.db.partitions.PartitionUpdate;
import org.apache.cassandra.db.partitions.UnfilteredPartitionIterator;
import org.apache.cassandra.io.sstable.ISSTableScanner;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.utils.CloseableIterator;

/**
 * Stage-4 unit-tier probe for mutation_repair_rows_per_batch-throttledunfilterediterator-maxbatchsize--autonomous (case B2).
 * Reproduces what CassandraStreamReceiver.sendThroughWritePath does per sstable: scanner -> ThrottledUnfilteredIterator.throttle(scanner, N)
 * -> PartitionUpdate.fromIterator(batch, ColumnFilter.all(metadata)) (the object the receiver wraps in a Mutation), and records for
 * every batch the number of Unfilteds iterated (rows and range-tombstone markers), the update's rowCount(), dataSize(),
 * unsharedHeapSize(), and the real retained heap of the largest update (GC'd used-heap delta while it is held).
 * Environment: PROBE_OUT = output file; PROBE_VAR = comma list of variants "<label>:<valueBytes>:<rows>:<tomb 0|1>:<N list ;-sep>".
 * Run through "ant testsome -Dtest.name=org.apache.cassandra.db.rows.MutationRepairBatchProbeTest" in the run copy.
 */
public class MutationRepairBatchProbeTest extends CQLTester
{
    static PrintWriter out;

    static void log(String s)
    {
        out.println(s);
        out.flush();
        System.out.println("PROBE " + s);
    }

    static String pad(int n)
    {
        StringBuilder sb = new StringBuilder(n);
        for (int i = 0; i < n; i++) sb.append((char) ('a' + (i % 26)));
        return sb.toString();
    }

    static long usedAfterGc()
    {
        Runtime rt = Runtime.getRuntime();
        for (int i = 0; i < 4; i++) System.gc();
        return rt.totalMemory() - rt.freeMemory();
    }

    /** counts the Unfilteds handed out by one batch */
    static class Counting implements WrappingUnfilteredRowIterator
    {
        final UnfilteredRowIterator wrapped;
        int unfiltereds, rows, markers;

        Counting(UnfilteredRowIterator w) { wrapped = w; }

        public UnfilteredRowIterator wrapped() { return wrapped; }

        public Unfiltered next()
        {
            Unfiltered u = wrapped.next();
            unfiltereds++;
            if (u.isRow()) rows++; else markers++;
            return u;
        }
    }

    @Test
    public void probe() throws Throwable
    {
        out = new PrintWriter(new FileWriter(System.getenv("PROBE_OUT")));
        for (String var : System.getenv("PROBE_VAR").split(","))
        {
            String[] p = var.split(":");
            String label = p[0];
            int valBytes = Integer.parseInt(p[1]), nrows = Integer.parseInt(p[2]);
            boolean tomb = p[3].equals("1");
            createTable("CREATE TABLE %s (pk int, ck int, v text, PRIMARY KEY (pk, ck))");
            String val = pad(valBytes);
            if (tomb)
                execute("DELETE FROM %s USING TIMESTAMP 100 WHERE pk = 1 AND ck >= 0 AND ck < ?", nrows);
            for (int i = 0; i < nrows; i++)
                execute("INSERT INTO %s (pk, ck, v) VALUES (1, ?, ?) USING TIMESTAMP " + (tomb ? 200 : 300), i, val);
            ColumnFamilyStore cfs = Keyspace.open(keyspace()).getColumnFamilyStore(currentTable());
            cfs.forceBlockingFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS);
            cfs.disableAutoCompaction();
            cfs.forceMajorCompaction();
            SSTableReader reader = cfs.getLiveSSTables().iterator().next();
            log("variant " + label + " valueBytes=" + valBytes + " rows=" + nrows + " tombstoneBoundary=" + tomb + " sstables=" + cfs.getLiveSSTables().size()
                + " sstableDataBytes=" + reader.onDiskLength());
            for (String ns : p[4].split(";"))
            {
                int n = Integer.parseInt(ns);
                long base = usedAfterGc();
                int batches = 0, maxUnf = 0, maxRows = 0, minUnf = Integer.MAX_VALUE;
                long totalRows = 0, totalUnf = 0, maxHeap = 0, maxData = 0;
                PartitionUpdate held = null;
                long t0 = System.nanoTime();
                try (ISSTableScanner scanner = reader.getScanner();
                     CloseableIterator<UnfilteredRowIterator> throttled = ThrottledUnfilteredIterator.throttle(scanner, n))
                {
                    log("N=" + n + " sameObjectAsScanner=" + (throttled == scanner));
                    while (throttled.hasNext())
                    {
                        Counting c = new Counting(throttled.next());
                        PartitionUpdate u = PartitionUpdate.fromIterator(c, ColumnFilter.all(cfs.metadata()));
                        batches++;
                        totalUnf += c.unfiltereds;
                        totalRows += u.rowCount();
                        maxUnf = Math.max(maxUnf, c.unfiltereds);
                        minUnf = Math.min(minUnf, c.unfiltereds);
                        maxRows = Math.max(maxRows, u.rowCount());
                        maxData = Math.max(maxData, u.dataSize());
                        if (u.unsharedHeapSize() > maxHeap)
                        {
                            maxHeap = u.unsharedHeapSize();
                            held = u;
                        }
                    }
                }
                long retained = usedAfterGc() - base;
                int heldRows = held == null ? -1 : held.rowCount();   // reads `held` after the measurement, so it is live during it
                log("RESULT variant=" + label + " N=" + n + " batches=" + batches + " maxUnfilteredsPerBatch=" + maxUnf + " minUnfilteredsPerBatch=" + minUnf
                    + " maxRowsPerBatch=" + maxRows + " totalRows=" + totalRows + " totalUnfiltereds=" + totalUnf + " maxUnsharedHeapSize=" + maxHeap
                    + " maxDataSize=" + maxData + " retainedHeapOfLargestUpdate=" + retained + " heldRows=" + heldRows + " ms=" + (System.nanoTime() - t0) / 1_000_000);
                held = null;
            }
        }
        out.close();
    }
}
