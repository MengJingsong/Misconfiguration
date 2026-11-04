package org.apache.cassandra.index.sai.disk.v1.postings;

import java.lang.management.ManagementFactory;
import java.lang.reflect.Constructor;
import javax.management.ObjectName;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.index.sai.disk.ArrayPostingList;
import org.apache.cassandra.index.sai.disk.io.IndexFileUtils;
import org.apache.cassandra.index.sai.disk.io.IndexOutputWriter;
import org.apache.cassandra.io.util.File;

/**
 * Stage-4 unit probe, block_size-writeposting-blocksize--autonomous (B2, amended 2026-10-28).
 * usage: PostingsBlockProbe <blockSize> <N> <stride> <lists> <dir> [label]
 * Opens a real IndexOutputWriter in <dir> (local disk), builds PostingsWriter(IndexOutputWriter, blockSize) through its private constructor by reflection
 * (the package-private (IndexDescriptor, IndexIdentifier, int) constructor needs a descriptor; the body is the same), then writes <lists> posting lists
 * of N ascending postings (posting i = i * stride, so every delta is `stride`), complete(). Prints the thread-allocated bytes of the constructor and of the writes,
 * the file pointer / on-disk length, the summary offset returned by write() (data bytes = summary offset - header), and the [J / [B rows of the class histogram
 * (full GC first, writer still referenced) as the retained heap.
 */
public class PostingsBlockProbe
{
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static long tid() { return Thread.currentThread().getId(); }

    static long[] hist(String cls) throws Exception
    {
        ObjectName n = new ObjectName("com.sun.management:type=DiagnosticCommand");
        String out = (String) ManagementFactory.getPlatformMBeanServer().invoke(n, "gcClassHistogram", new Object[]{ new String[0] }, new String[]{ String[].class.getName() });
        for (String l : out.split("\n"))
        {
            String[] f = l.trim().split("\\s+");
            if (f.length >= 4 && f[3].equals(cls))
                return new long[]{ Long.parseLong(f[1]), Long.parseLong(f[2]) };
        }
        return new long[]{ 0, 0 };
    }

    public static void main(String[] a) throws Exception
    {
        int bs = Integer.parseInt(a[0]);
        long n = Long.parseLong(a[1]);
        long stride = Long.parseLong(a[2]);
        int lists = Integer.parseInt(a[3]);
        String dir = a[4];
        String id = "bs=" + bs + " N=" + n + " stride=" + stride + " lists=" + lists + " label=" + (a.length > 5 ? a[5] : "");
        DatabaseDescriptor.daemonInitialization();
        Constructor<PostingsWriter> c = PostingsWriter.class.getDeclaredConstructor(IndexOutputWriter.class, int.class);
        c.setAccessible(true);
        // warm-up: one small writer, dropped, so class loading is not counted
        {
            File f0 = new File(dir + "/warm.bin");
            try (PostingsWriter w0 = c.newInstance(IndexFileUtils.instance.openOutput(f0), 128)) { w0.write(new ArrayPostingList(1, 2, 3, 400, 500)); w0.complete(); }
        }
        long[] long0 = hist("[J"), byte0 = hist("[B");
        File f = new File(dir + "/postings.bin");
        long a0 = TMX.getThreadAllocatedBytes(tid());
        PostingsWriter w = c.newInstance(IndexFileUtils.instance.openOutput(f), bs);
        long a1 = TMX.getThreadAllocatedBytes(tid());
        long header = w.getFilePointer();
        System.out.println("STAGE4 ctor " + id + " ctorAlloc=" + (a1 - a0) + " headerBytes=" + header + " expectedDeltaBuffer=" + (8L * bs + 16));
        long[] posting = new long[(int) n];
        for (int i = 0; i < n; i++) posting[i] = i * stride;
        long tw = 0, lastSummary = -1;
        long a2 = TMX.getThreadAllocatedBytes(tid());
        long t0 = System.nanoTime();
        long dataBytes = 0;
        for (int l = 0; l < lists; l++)
        {
            long before = w.getFilePointer();
            long summary = w.write(new ArrayPostingList(posting));
            dataBytes += summary - before;
            lastSummary = summary;
        }
        long a3 = TMX.getThreadAllocatedBytes(tid());
        long beforeComplete = w.getFilePointer();
        w.complete();
        long fp = w.getFilePointer();
        long[] long1 = hist("[J"), byte1 = hist("[B");
        System.out.println("STAGE4 wrote " + id + " writeAlloc=" + (a3 - a2) + " dataBytes=" + dataBytes + " filePointerBeforeComplete=" + beforeComplete + " filePointer=" + fp
                           + " J_bytes_delta=" + (long1[1] - long0[1]) + " J_instances_delta=" + (long1[0] - long0[0]) + " B_bytes_delta=" + (byte1[1] - byte0[1])
                           + " totalPostings=" + w.getTotalPostings() + " ms=" + (System.nanoTime() - t0) / 1_000_000);
        w.close();
        System.out.println("STAGE4 file " + id + " onDiskBytes=" + f.length() + " blocksPerList=" + ((n + bs - 1) / bs));
        System.exit(0);
    }
}
