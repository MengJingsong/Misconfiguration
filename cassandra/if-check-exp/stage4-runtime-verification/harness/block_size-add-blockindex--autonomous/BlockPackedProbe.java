package org.apache.cassandra.index.sai.disk.v1.bitpack;

import java.lang.management.ManagementFactory;
import javax.management.ObjectName;

import org.apache.lucene.store.IndexOutput;

/**
 * Stage-4 unit probe, block_size-add-blockindex--autonomous (B2, amended 2026-10-28).
 * usage: BlockPackedProbe <plain|mono|ctl> <blockSize> <N> [label]
 * One (writer kind, blockSize, N) per JVM. Prints STAGE4 lines (key=value pairs).
 *  plain/mono: constructs BlockPackedWriter / MonotonicBlockPackedWriter (counting subclass over flushBlock), measures the constructor's
 *   thread-allocated bytes, blockValues.length (protected field, same package), adds N values sampling blockIndex, counts flushBlock calls,
 *   counts bytes out through a sink that retains nothing, takes the [J row of the class histogram (a full GC first) before the constructor,
 *   after N adds with the writer alive and (with blockMeta size) after finish().
 *  ctl: positive control, N values appended to a growing long[] (what an accumulating list would hold); [J delta must follow N.
 */
public class BlockPackedProbe
{
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();

    static class CountingOut extends IndexOutput
    {
        long pos;
        CountingOut() { super("sink", "sink"); }
        public void close() {}
        public long getFilePointer() { return pos; }
        public long getChecksum() { return 0; }
        public void writeByte(byte b) { pos++; }
        public void writeBytes(byte[] b, int o, int l) { pos += l; }
    }

    static long[] histJ() throws Exception
    {
        ObjectName n = new ObjectName("com.sun.management:type=DiagnosticCommand");
        String out = (String) ManagementFactory.getPlatformMBeanServer().invoke(n, "gcClassHistogram", new Object[]{ new String[0] }, new String[]{ String[].class.getName() });
        for (String l : out.split("\n"))
        {
            String[] f = l.trim().split("\\s+");
            if (f.length >= 4 && f[3].equals("[J"))
                return new long[]{ Long.parseLong(f[1]), Long.parseLong(f[2]) };
        }
        return new long[]{ -1, -1 };
    }

    static long tid() { return Thread.currentThread().getId(); }

    public static void main(String[] a) throws Exception
    {
        String kind = a[0];
        int bs = Integer.parseInt(a[1]);
        long n = Long.parseLong(a[2]);
        String label = a.length > 3 ? a[3] : "";
        String id = "kind=" + kind + " bs=" + bs + " N=" + n + " label=" + label;
        if (!kind.equals("ctl"))
        {   // warm-up (class loading would otherwise be counted in the first constructor's allocation); a bs=64 writer of the same kind, dropped
            AbstractBlockPackedWriter wu = kind.equals("plain") ? new BlockPackedWriter(new CountingOut(), 64) : new MonotonicBlockPackedWriter(new CountingOut(), 64);
            for (int i = 0; i < 200; i++) wu.add(i);
            wu.finish();
        }
        histJ();
        long[] h0 = histJ();
        System.out.println("STAGE4 base " + id + " J_instances=" + h0[0] + " J_bytes=" + h0[1]);
        if (kind.equals("ctl"))
        {
            long[] arr = new long[16];
            for (long i = 0; i < n; i++)
            {
                if (i == arr.length) arr = java.util.Arrays.copyOf(arr, (int) Math.min(Integer.MAX_VALUE - 8, arr.length * 2L));
                arr[(int) i] = i;
            }
            long[] h1 = histJ();
            System.out.println("STAGE4 control " + id + " J_bytes_delta=" + (h1[1] - h0[1]) + " arr_len=" + arr.length + " held=" + (arr.length > 0));
            return;
        }
        final long[] flushes = { 0 };
        CountingOut out = new CountingOut();
        AbstractBlockPackedWriter w;
        long a0 = TMX.getThreadAllocatedBytes(tid());
        try
        {
            if (kind.equals("plain"))
                w = new BlockPackedWriter(out, bs) { protected void flushBlock() throws java.io.IOException { flushes[0]++; super.flushBlock(); } };
            else
                w = new MonotonicBlockPackedWriter(out, bs) { protected void flushBlock() throws java.io.IOException { flushes[0]++; super.flushBlock(); } };
        }
        catch (IllegalArgumentException e)
        {
            long a1 = TMX.getThreadAllocatedBytes(tid());
            System.out.println("STAGE4 invalid " + id + " exception=IllegalArgumentException ctorAlloc=" + (a1 - a0) + " message=\"" + e.getMessage() + "\"");
            return;
        }
        long a1 = TMX.getThreadAllocatedBytes(tid());
        System.out.println("STAGE4 ctor " + id + " ctorAlloc=" + (a1 - a0) + " blockValuesLen=" + w.blockValues.length
                           + " minBlock=" + AbstractBlockPackedWriter.MIN_BLOCK_SIZE + " maxBlock=" + AbstractBlockPackedWriter.MAX_BLOCK_SIZE);
        int maxIdx = 0;
        long x = 88172645463325252L;
        long t0 = System.nanoTime();
        for (long i = 0; i < n; i++)
        {
            long v;
            if (kind.equals("mono")) v = i * 3;
            else { x ^= x << 13; x ^= x >>> 7; x ^= x << 17; v = (x >>> 44); }
            w.add(v);
            if (w.blockIndex > maxIdx) maxIdx = w.blockIndex;
        }
        long a2 = TMX.getThreadAllocatedBytes(tid());
        long meta1 = w.blockMetaWriter.intSize();
        long[] h1 = histJ();
        System.out.println("STAGE4 adds " + id + " maxBlockIndex=" + maxIdx + " flushesAfterAdds=" + flushes[0] + " metaBytesBeforeFinish=" + meta1
                           + " addAlloc=" + (a2 - a1) + " bytesOutBeforeFinish=" + out.pos + " J_bytes_delta=" + (h1[1] - h0[1]) + " J_instances_delta=" + (h1[0] - h0[0])
                           + " ms=" + (System.nanoTime() - t0) / 1_000_000);
        w.finish();
        long exp = (n + bs - 1) / bs;
        System.out.println("STAGE4 finish " + id + " flushes=" + flushes[0] + " expectedFlushes=" + exp + " bytesOut=" + out.pos + " metaBytes=" + w.blockMetaWriter.intSize()
                           + " expectedMetaGrowsWithBlocks=" + exp);
        System.out.println("STAGE4 done " + id + " alive=" + (w != null));
    }
}
