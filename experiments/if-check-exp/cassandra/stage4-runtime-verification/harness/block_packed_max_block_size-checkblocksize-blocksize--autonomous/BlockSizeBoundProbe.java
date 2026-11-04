package org.apache.cassandra.index.sai.disk.v1.bitpack;

import java.lang.management.ManagementFactory;

import org.apache.cassandra.index.sai.disk.v1.SAICodecUtils;
import org.apache.lucene.store.ByteBuffersDataInput;
import org.apache.lucene.store.ByteBuffersDataOutput;
import org.apache.lucene.store.ByteBuffersIndexOutput;
import org.apache.lucene.store.IndexOutput;

/**
 * Stage-4 unit probe, block_packed_max_block_size-checkblocksize-blocksize--autonomous (B2, amended 2026-10-28).
 * usage: BlockSizeBoundProbe writer <plain|mono> <blockSize> [label]       one writer construction (+ 3 x blockSize adds, capped at 2^22, then finish, when blockSize <= 2^21)
 *        BlockSizeBoundProbe check <blockSize> [label]                      SAICodecUtils.checkBlockSize(bs, MIN, MAX) alone
 *        BlockSizeBoundProbe reader <plain|mono> <blockSize> <valueCount>   a reader constructor on a forged NumericValuesMeta (null FileHandle: the check
 *                                                                           precedes the numBlocks-sized arrays, which precede file.createReader())
 * MIN/MAX are read reflectively from the loaded class (a static final int is inlined into this probe at compile time, which would hide a patched bound).
 */
public class BlockSizeBoundProbe
{
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static long tid() { return Thread.currentThread().getId(); }

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

    static int constant(String name) throws Exception
    {
        java.lang.reflect.Field f = AbstractBlockPackedWriter.class.getDeclaredField(name);
        f.setAccessible(true);
        return f.getInt(null);
    }

    public static void main(String[] a) throws Exception
    {
        String mode = a[0];
        int min = constant("MIN_BLOCK_SIZE"), max = constant("MAX_BLOCK_SIZE");
        // warm-up so class loading is not counted in the measured allocation
        try { SAICodecUtils.checkBlockSize(128, min, max); new BlockPackedWriter(new CountingOut(), 64).finish(); } catch (Exception e) {}
        try { SAICodecUtils.checkBlockSize(99, min, max); } catch (IllegalArgumentException e) {}
        try { SAICodecUtils.checkBlockSize(max * 2, min, max); } catch (IllegalArgumentException e) {}
        try { SAICodecUtils.checkBlockSize(8, min, max); } catch (IllegalArgumentException e) {}
        try { new BlockPackedReader(null, new NumericValuesMeta(forged(64, 10))); } catch (Exception e) {}
        try { new BlockPackedReader(null, new NumericValuesMeta(forged(99, 10))); } catch (Exception e) {}
        try { new MonotonicBlockPackedReader(null, new NumericValuesMeta(forged(64, 10))); } catch (Exception e) {}
        String hdr = "bounds=" + min + ".." + max;
        if (mode.equals("check"))
        {
            int bs = Integer.parseInt(a[1]);
            long a0 = TMX.getThreadAllocatedBytes(tid());
            try
            {
                int shift = SAICodecUtils.checkBlockSize(bs, min, max);
                System.out.println("STAGE4 check bs=" + bs + " " + hdr + " accepted shift=" + shift + " alloc=" + (TMX.getThreadAllocatedBytes(tid()) - a0));
            }
            catch (IllegalArgumentException e)
            {
                System.out.println("STAGE4 check bs=" + bs + " " + hdr + " rejected message=\"" + e.getMessage() + "\" alloc=" + (TMX.getThreadAllocatedBytes(tid()) - a0));
            }
        }
        else if (mode.equals("writer"))
        {
            String kind = a[1];
            int bs = Integer.parseInt(a[2]);
            String id = "kind=" + kind + " bs=" + bs + " label=" + (a.length > 3 ? a[3] : "") + " " + hdr;
            CountingOut out = new CountingOut();
            long[] flushes = { 0 };
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
                System.out.println("STAGE4 writer-rejected " + id + " message=\"" + e.getMessage() + "\" ctorAlloc=" + (TMX.getThreadAllocatedBytes(tid()) - a0));
                return;
            }
            long a1 = TMX.getThreadAllocatedBytes(tid());
            System.out.println("STAGE4 writer-accepted " + id + " ctorAlloc=" + (a1 - a0) + " blockValuesLen=" + w.blockValues.length + " expectedMin=" + (8L * bs + 16));
            if (bs <= (1 << 21))
            {
                long n = Math.min(3L * bs, 1L << 22);
                for (long i = 0; i < n; i++) w.add(kind.equals("mono") ? i * 3 : (i * 2654435761L) & 0xFFFFF);
                w.finish();
                System.out.println("STAGE4 writer-wrote " + id + " N=" + n + " flushes=" + flushes[0] + " bytesOut=" + out.pos + " totalAlloc=" + (TMX.getThreadAllocatedBytes(tid()) - a0));
            }
            else
                System.out.println("STAGE4 writer-wrote " + id + " skipped=construction-only");
        }
        else if (mode.equals("reader"))
        {
            String kind = a[1];
            int bs = Integer.parseInt(a[2]);
            long vc = Long.parseLong(a[3]);
            String id = "kind=" + kind + " bs=" + bs + " valueCount=" + vc + " " + hdr;
            NumericValuesMeta meta = new NumericValuesMeta(forged(bs, vc));
            long a0 = TMX.getThreadAllocatedBytes(tid());
            String outcome;
            try
            {
                if (kind.equals("plain")) new BlockPackedReader(null, meta); else new MonotonicBlockPackedReader(null, meta);
                outcome = "constructed";
            }
            catch (IllegalArgumentException e) { outcome = "IllegalArgumentException(\"" + e.getMessage() + "\")"; }
            catch (Throwable e) { outcome = e.getClass().getSimpleName() + "(after the check, in file.createReader())"; }
            long alloc = TMX.getThreadAllocatedBytes(tid()) - a0;
            System.out.println("STAGE4 reader " + id + " metaBlockSize=" + meta.blockSize + " outcome=" + outcome + " alloc=" + alloc);
        }
    }

    static ByteBuffersDataInput forged(int bs, long valueCount) throws Exception
    {
        ByteBuffersDataOutput d = new ByteBuffersDataOutput();
        ByteBuffersIndexOutput o = new ByteBuffersIndexOutput(d, "f", "f");
        NumericValuesMeta.write(o, valueCount, bs, 0L);
        o.close();
        return d.toDataInput();
    }
}
