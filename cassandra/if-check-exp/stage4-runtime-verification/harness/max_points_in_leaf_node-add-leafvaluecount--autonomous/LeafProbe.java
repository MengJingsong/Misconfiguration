package org.apache.cassandra.index.sai.disk.v1.bbtree;

import java.lang.management.ManagementFactory;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Iterator;
import java.util.Map;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.index.sai.SAITester;
import org.apache.cassandra.index.sai.disk.format.IndexComponent;
import org.apache.cassandra.index.sai.disk.format.IndexDescriptor;
import org.apache.cassandra.index.sai.disk.io.IndexOutputWriter;
import org.apache.cassandra.index.sai.disk.v1.segment.SegmentMetadata;
import org.apache.cassandra.index.sai.postings.PostingList;
import org.apache.cassandra.index.sai.utils.IndexEntry;
import org.apache.cassandra.index.sai.utils.IndexIdentifier;
import org.apache.cassandra.io.sstable.Descriptor;
import org.apache.cassandra.io.sstable.SequenceBasedSSTableId;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.utils.bytecomparable.ByteComparable;

/**
 * Stage-4 unit probe for max_points_in_leaf_node-add-leafvaluecount--autonomous (B2), and shared by max_array_length (not used there).
 * usage: LeafProbe cell <M> <N> <B>    writeCompleteSegment(N sorted B-byte terms, one row id each) with NumericIndexWriter(M, B); then LEAFPOST and SCRATCH passes
 *        LeafProbe reject <M>          constructor check (M=0, M=MAX_ARRAY_LENGTH+1 passed as -1 meaning MAX+1)
 *        LeafProbe alloc <k>           harness-sensitivity control: allocated bytes of new long[k]
 */
public class LeafProbe
{
    static final com.sun.management.ThreadMXBean TM = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();

    static long alloc() { return TM.getThreadAllocatedBytes(Thread.currentThread().getId()); }

    static long heap()
    {
        for (int i = 0; i < 3; i++) { System.gc(); try { Thread.sleep(100); } catch (InterruptedException e) {} }
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

    static Iterator<IndexEntry> entries(long n, int b)
    {
        return new Iterator<>()
        {
            long i = 0;
            public boolean hasNext() { return i < n; }
            public IndexEntry next()
            {
                byte[] t = new byte[b];
                long x = i;
                for (int k = Math.min(b, 8) - 1; k >= 0; k--) { t[k] = (byte) x; x >>>= 8; } // big-endian counter in the last min(b,8) bytes
                IndexEntry e = IndexEntry.create(ByteComparable.fixedLength(t), new One(i));
                i++;
                return e;
            }
        };
    }

    static void rmrf(java.io.File f)
    {
        java.io.File[] k = f.listFiles();
        if (k != null) for (java.io.File c : k) rmrf(c);
        f.delete();
    }

    static IndexDescriptor newDescriptor(Path base, String name) throws Exception
    {
        Path d = Files.createDirectory(base.resolve(name));
        return IndexDescriptor.create(new Descriptor(new File(d.toFile()), "ks", "cf", new SequenceBasedSSTableId(1)), Murmur3Partitioner.instance, SAITester.EMPTY_COMPARATOR);
    }

    public static void main(String[] a) throws Exception
    {
        DatabaseDescriptor.toolInitialization();
        String mode = a[0];
        if (mode.equals("alloc"))
        {
            int k = Integer.parseInt(a[1]);
            long x = alloc(); long[] arr = new long[k]; long y = alloc();
            System.out.printf("STAGE4 ALLOCCTL k=%d allocBytes=%d len=%d%n", k, y - x, arr.length);
            System.exit(0);
        }
        if (mode.equals("reject"))
        {
            long m = Long.parseLong(a[1]);
            int v = m == -1 ? org.apache.lucene.util.ArrayUtil.MAX_ARRAY_LENGTH + 1 : (int) m;
            try { new BlockBalancedTreeWriter(4, v); System.out.printf("STAGE4 REJECT M=%d accepted MAX_ARRAY_LENGTH=%d%n", v, org.apache.lucene.util.ArrayUtil.MAX_ARRAY_LENGTH); }
            catch (IllegalArgumentException e) { System.out.printf("STAGE4 REJECT M=%d IllegalArgumentException: %s%n", v, e.getMessage()); }
            System.exit(0);
        }
        int M = Integer.parseInt(a[1]); long N = Long.parseLong(a[2]); int B = Integer.parseInt(a[3]);
        Path base = Files.createTempDirectory(java.nio.file.Paths.get(System.getProperty("probe.tmp", System.getProperty("java.io.tmpdir"))), "s4-b1-");
        IndexIdentifier ident = new IndexIdentifier("ks", "t", "idx");

        // warm-up (discarded): 20000 values at the same M, B
        { IndexDescriptor w = newDescriptor(base, "warm"); new NumericIndexWriter(w, ident, M, B).writeCompleteSegment(entries(20000, B)); }

        // main: allocated bytes and component metadata
        IndexDescriptor id = newDescriptor(base, "main");
        NumericIndexWriter nw = new NumericIndexWriter(id, ident, M, B);
        heap();
        long a0 = alloc(); long t0 = System.nanoTime();
        SegmentMetadata.ComponentMetadataMap comps = nw.writeCompleteSegment(entries(N, B));
        long a1 = alloc(); long ms = (System.nanoTime() - t0) / 1_000_000;
        SegmentMetadata.ComponentMetadata tree = null, post = null;
        try { tree = comps.get(IndexComponent.BALANCED_TREE); post = comps.get(IndexComponent.POSTING_LISTS); } catch (IllegalArgumentException e) { /* N = 0: nothing written; get() throws (runbook defect D1) */ }
        if (tree == null)
            System.out.printf("STAGE4 CELL M=%d N=%d B=%d empty=true alloc=%d%n", M, N, B, a1 - a0);
        else
            System.out.printf("STAGE4 CELL M=%d N=%d B=%d num_leaves=%s max_points_in_leaf_node=%s num_values=%s bytes_per_value=%s treeLen=%d postLen=%d alloc=%d ms=%d expectLeaves=%d%n",
                              M, N, B, tree.attributes.get("num_leaves"), tree.attributes.get("max_points_in_leaf_node"), tree.attributes.get("num_values"), tree.attributes.get("bytes_per_value"),
                              tree.length, post.length, a1 - a0, ms, (N + M - 1) / M);

        // LEAFPOST: heap retained by the real (private) LeafCallback after a direct write through BlockBalancedTreeWriter
        IndexDescriptor id2 = newDescriptor(base, "leafpost");
        Class<?> lc = Class.forName("org.apache.cassandra.index.sai.disk.v1.bbtree.NumericIndexWriter$LeafCallback");
        Constructor<?> lcc = lc.getDeclaredConstructor(); lcc.setAccessible(true);
        Object cb = lcc.newInstance();
        long h0 = heap();
        try (IndexOutputWriter out = id2.openPerIndexOutput(IndexComponent.BALANCED_TREE, ident, true))
        {
            new BlockBalancedTreeWriter(B, M).write(out, entries(N, B), (BlockBalancedTreeWriter.Callback) cb);
        }
        long h1 = heap();
        Method nl = lc.getDeclaredMethod("numLeaves"); nl.setAccessible(true);
        int leaves = (Integer) nl.invoke(cb);
        System.out.printf("STAGE4 LEAFPOST M=%d N=%d B=%d leaves=%d retainedBytes=%d perLeaf=%.1f%n", M, N, B, leaves, h1 - h0, leaves == 0 ? 0.0 : (double) (h1 - h0) / leaves);
        System.out.println("STAGE4 KEEP " + cb.hashCode());

        // SCRATCH: construct the private LeafWriter and hold it
        IndexDescriptor id3 = newDescriptor(base, "scratch");
        Class<?> lw = Class.forName("org.apache.cassandra.index.sai.disk.v1.bbtree.BlockBalancedTreeWriter$LeafWriter");
        Constructor<?> lwc = lw.getDeclaredConstructors()[0]; lwc.setAccessible(true);
        BlockBalancedTreeWriter bw = new BlockBalancedTreeWriter(B, M);
        try (IndexOutputWriter out = id3.openPerIndexOutput(IndexComponent.BALANCED_TREE, ident, true))
        {
            long s0 = heap();
            Object w = lwc.newInstance(bw, out, (BlockBalancedTreeWriter.Callback) (p, o, c) -> {});
            long s1 = heap();
            StringBuilder lens = new StringBuilder();
            for (String f : new String[]{ "leafValues", "leafRowIDs", "rowIDAndIndexes", "orderIndex" })
            {
                Field fl = lw.getDeclaredField(f); fl.setAccessible(true);
                lens.append(f).append('=').append(java.lang.reflect.Array.getLength(fl.get(w))).append(' ');
            }
            System.out.printf("STAGE4 SCRATCH M=%d B=%d retainedBytes=%d perM=%.2f arrays: %s%n", M, B, s1 - s0, (double) (s1 - s0) / M, lens.toString().trim());
            System.out.println("STAGE4 KEEP " + System.identityHashCode(w));
        }
        rmrf(base.toFile());
        System.exit(0);
    }
}
