package org.apache.cassandra.index.sai.disk.v1.bbtree;

import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.util.Iterator;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.index.sai.postings.PostingList;
import org.apache.cassandra.index.sai.utils.IndexEntry;
import org.apache.cassandra.utils.bytecomparable.ByteComparable;
import org.apache.lucene.store.IndexOutput;
import org.apache.lucene.util.ArrayUtil;

/**
 * Stage-4 unit probe for max_array_length-checkmaxleafnodecount-numleaves--autonomous (B2).
 * usage: LeafCountProbe <label> <B> <M> <N|L|L-1|L-5>
 *   B = bytesPerValue, M = maxPointsInLeafNode, N = number of points (one row id each); L = floor(ArrayUtil.MAX_ARRAY_LENGTH / B) + 1 (first leaf count that throws, M = 1 only).
 * Writes through BlockBalancedTreeWriter(B, M).write into a counting, discarding IndexOutput; the Callback is a no-op that counts calls and, at 1/4, 1/2 and E-1 leaves
 * (E = ceil(N/M)), records heap used after forced GCs (retained bytes against leaf count).
 */
public class LeafCountProbe
{
    static long heap()
    {
        for (int i = 0; i < 2; i++) { System.gc(); try { Thread.sleep(50); } catch (InterruptedException e) {} }
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    static class One implements PostingList
    {
        final long row; boolean done;
        One(long row) { this.row = row; }
        public long nextPosting() { if (done) return END_OF_STREAM; done = true; return row; }
        public long size() { return 1; }
        public long advance(long t) { return END_OF_STREAM; }
    }

    static class CountingOut extends IndexOutput
    {
        long pos;
        CountingOut() { super("discard", "discard"); }
        public void close() {}
        public long getFilePointer() { return pos; }
        public long getChecksum() { return 0; }
        public void writeByte(byte b) { pos++; }
        public void writeBytes(byte[] b, int off, int len) { pos += len; }
    }

    static long consumed;

    public static void main(String[] a) throws Exception
    {
        DatabaseDescriptor.toolInitialization();
        String label = a[0];
        int B = Integer.parseInt(a[1]), M = Integer.parseInt(a[2]);
        long limit = ArrayUtil.MAX_ARRAY_LENGTH;
        long L = limit / B + 1;
        long N = a[3].equals("L") ? L : a[3].equals("L-1") ? L - 1 : a[3].equals("L-5") ? L - 5 : Long.parseLong(a[3]);
        final long expectLeaves = (N + M - 1) / M;
        System.out.printf("STAGE4 PARAMS label=%s B=%d M=%d N=%d LIMIT=%d L=%d expectLeaves=%d%n", label, B, M, N, limit, L, expectLeaves);

        final long[] pts = { expectLeaves / 4, expectLeaves / 2, expectLeaves - 1 };
        final StringBuilder samples = new StringBuilder();
        final long[] calls = { 0 };
        final long h0 = heap();
        BlockBalancedTreeWriter.Callback cb = (p, off, cnt) -> {
            calls[0]++;
            for (long x : pts)
                if (calls[0] == x && x > 0) samples.append(calls[0]).append(':').append(heap() - h0).append(' ');
        };
        final int bb = B;
        Iterator<IndexEntry> it = new Iterator<>()
        {
            long i = 0;
            public boolean hasNext() { return i < N; }
            public IndexEntry next()
            {
                byte[] t = new byte[bb];
                long x = i;
                for (int k = Math.min(bb, 8) - 1; k >= 0; k--) { t[k] = (byte) x; x >>>= 8; }
                IndexEntry e = IndexEntry.create(ByteComparable.fixedLength(t), new One(i));
                i++; consumed = i;
                return e;
            }
        };
        String result = "OK", msg = "";
        long t0 = System.nanoTime();
        CountingOut out = new CountingOut();
        BlockBalancedTreeWriter w = new BlockBalancedTreeWriter(B, M);
        long fp = -2;
        try { fp = w.write(out, it, cb); }
        catch (IllegalStateException e) { result = "THROW"; msg = e.getMessage(); }
        long ms = (System.nanoTime() - t0) / 1_000_000;
        long leavesAtEnd = result.equals("THROW") ? calls[0] + 1 : calls[0];
        System.out.printf("STAGE4 RESULT label=%s B=%d M=%d N=%d result=%s consumed=%d callbackCalls=%d leavesAtEnd=%d product=%d LIMIT=%d ratio=%.6g treeFilePointer=%d bytesWritten=%d valueCount=%d ms=%d msg=[%s] retainedSamples=[%s]%n",
                          label, B, M, N, result, consumed, calls[0], leavesAtEnd, (long) B * leavesAtEnd, limit, (double) B * leavesAtEnd / limit, fp, out.pos, w.getValueCount(), ms, msg, samples.toString().trim());
        System.exit(0);
    }
}
