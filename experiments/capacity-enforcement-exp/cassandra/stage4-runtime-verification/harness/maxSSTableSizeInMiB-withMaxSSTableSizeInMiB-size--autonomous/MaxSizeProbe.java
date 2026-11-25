import java.io.File;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.ByteBuffer;
import java.util.Random;

import org.apache.cassandra.dht.ByteOrderedPartitioner;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.io.sstable.CQLSSTableWriter;

// args: mode(unsorted|sorted) limit(unset|<int MiB>) rows valueBytes outDir sampleEvery(0=off) stmt(insert|delete) [partitioner bop|m3, default bop]
public class MaxSizeProbe
{
    public static void main(String[] a) throws Exception
    {
        String mode = a[0], limit = a[1];
        long rows = Long.parseLong(a[2]);
        int valueBytes = Integer.parseInt(a[3]);
        File out = new File(a[4], "probe/t");
        int every = Integer.parseInt(a[5]);
        boolean delete = a.length > 6 && a[6].equals("delete");
        boolean m3 = a.length > 7 && a[7].equals("m3");
        boolean sorted = mode.equals("sorted");
        if (!out.mkdirs() && !out.isDirectory()) throw new IllegalStateException("cannot create " + out);

        CQLSSTableWriter.Builder b = CQLSSTableWriter.builder()
            .inDirectory(out.getAbsolutePath())
            .forTable("CREATE TABLE probe.t (k bigint PRIMARY KEY, v blob) WITH compression = {'enabled':'false'}")
            .using(delete ? "DELETE FROM probe.t WHERE k = ?" : "INSERT INTO probe.t (k, v) VALUES (?, ?)")
            // ByteOrdered: bigint keys 0..N-1 are then already in partitioner order (needed by sorted())
            .withPartitioner(m3 ? Murmur3Partitioner.instance : ByteOrderedPartitioner.instance);
        if (sorted) b.sorted();
        if (!limit.equals("unset")) b.withMaxSSTableSizeInMiB(Integer.parseInt(limit));
        CQLSSTableWriter w = b.build();

        Field wf = CQLSSTableWriter.class.getDeclaredField("writer"); wf.setAccessible(true);
        Object inner = wf.get(w);
        Field limF = inner.getClass().getDeclaredField(sorted ? "maxSSTableSizeInBytes" : "maxSStableSizeInBytes");
        limF.setAccessible(true);
        Field curF = sorted ? null : inner.getClass().getDeclaredField("currentSize");
        Field txnF = sorted ? inner.getClass().getDeclaredField("writer") : null;
        if (curF != null) curF.setAccessible(true);
        if (txnF != null) txnF.setAccessible(true);
        System.out.println("WRITER " + inner.getClass().getSimpleName() + " EFFECTIVE_LIMIT_BYTES " + limF.getLong(inner));

        MemoryMXBean mem = ManagementFactory.getMemoryMXBean();
        Random rnd = new Random(42);
        long maxOp = 0, prev = 0, firstDelta = -1, syncs = 0, maxHeap = 0, minHeap = Long.MAX_VALUE;
        Object lastTxn = null; Method onDisk = null;
        long lastTxnBytes = 0, switches = 0, maxAtSwitch = 0, minAtSwitch = Long.MAX_VALUE;
        long t0 = System.nanoTime();
        for (long i = 0; i < rows; i++)
        {
            if (delete) w.addRow(i);
            else { byte[] v = new byte[valueBytes]; rnd.nextBytes(v); w.addRow(i, ByteBuffer.wrap(v)); }
            if (!sorted)
            {
                long cur = curF.getLong(inner);          // the check's operand (bytes)
                if (firstDelta < 0) firstDelta = cur;     // = s, serialized bytes of one 1-row partition
                if (cur < prev) syncs++;                  // sync() resets currentSize to 0
                maxOp = Math.max(maxOp, cur); prev = cur;
            }
            else
            {
                Object txn = txnF.get(inner);
                if (txn != null)
                {
                    if (onDisk == null) onDisk = txn.getClass().getMethod("getOnDiskBytesWritten");
                    if (lastTxn != null && txn != lastTxn)
                    { switches++; maxAtSwitch = Math.max(maxAtSwitch, lastTxnBytes); minAtSwitch = Math.min(minAtSwitch, lastTxnBytes); }
                    lastTxn = txn; lastTxnBytes = (Long) onDisk.invoke(txn);
                    maxOp = Math.max(maxOp, lastTxnBytes);
                }
            }
            if (every > 0 && (i + 1) % every == 0)
            {
                System.gc();
                long used = mem.getHeapMemoryUsage().getUsed();
                maxHeap = Math.max(maxHeap, used); minHeap = Math.min(minHeap, used);
                System.out.println("HEAP_SAMPLE row=" + (i + 1) + " live_bytes=" + used);
            }
        }
        w.close();
        System.out.println("SUMMARY mode=" + mode + " limit=" + limit + " rows=" + rows + " stmt=" + (delete ? "delete" : "insert")
                           + " first_row_delta=" + firstDelta + " max_operand=" + maxOp + " syncs=" + syncs
                           + " switches=" + switches + " min_at_switch=" + (switches > 0 ? minAtSwitch : -1)
                           + " max_at_switch=" + maxAtSwitch + " min_live_heap=" + (every > 0 ? minHeap : -1)
                           + " max_live_heap=" + (every > 0 ? maxHeap : -1)
                           + " elapsed_s=" + (System.nanoTime() - t0) / 1_000_000_000L);
        System.exit(0);   // client mode may leave non-daemon threads
    }
}
