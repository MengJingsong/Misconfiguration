package org.apache.cassandra.io.sstable;

import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.concurrent.ThreadLocalRandom;

import org.apache.cassandra.io.util.File;

// usage: BufferCapProbe <outDir> <mode> <rows> <valueBytes> <sampleCurrentSize> <gcEveryRows>
//   mode: default | explicit:<MiB> (calls withMaxSSTableSizeInMiB) | sorted
//   gcEveryRows: 0 = off; N = System.gc() then read heap used every N rows (live-heap sample)
public class BufferCapProbe
{
    public static void main(String[] args)
    {
        try { run(args); System.exit(0); }
        catch (Throwable t) { t.printStackTrace(); System.exit(1); }
    }

    static void run(String[] args) throws Exception
    {
        File dir = new File(args[0]);
        String mode = args[1];
        int rows = Integer.parseInt(args[2]);
        int valueBytes = Integer.parseInt(args[3]);
        boolean sample = Boolean.parseBoolean(args[4]);
        int gcEvery = Integer.parseInt(args[5]);
        if (!dir.exists() && !dir.tryCreateDirectories())
            throw new IllegalStateException("cannot create " + dir);

        CQLSSTableWriter.Builder b = CQLSSTableWriter.builder()
            .inDirectory(dir)
            .forTable("CREATE TABLE probe.t (k bigint PRIMARY KEY, v blob) WITH compression = {'enabled': 'false'}")
            .using("INSERT INTO probe.t (k, v) VALUES (?, ?)");
        if (mode.startsWith("explicit:"))
            b.withMaxSSTableSizeInMiB(Integer.parseInt(mode.substring("explicit:".length())));
        if (mode.equals("sorted"))
            b.sorted();
        CQLSSTableWriter w = b.build();

        Field wf = CQLSSTableWriter.class.getDeclaredField("writer");
        wf.setAccessible(true);
        Object sw = wf.get(w);
        boolean unsorted = sw instanceof SSTableSimpleUnsortedWriter;
        Field limitF = sw.getClass().getDeclaredField(unsorted ? "maxSStableSizeInBytes" : "maxSSTableSizeInBytes");
        limitF.setAccessible(true);
        long limit = limitF.getLong(sw);
        System.out.println("WRITER " + sw.getClass().getSimpleName() + " LIMIT_BYTES " + limit);
        Field curF = null;
        if (unsorted)
        {
            curF = SSTableSimpleUnsortedWriter.class.getDeclaredField("currentSize");
            curF.setAccessible(true);
        }

        System.gc();
        long h0 = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
        System.out.println("H0_BYTES " + h0);
        long peakLive = h0, prev = 0, maxObs = 0;
        int resets = 0;
        for (int i = 0; i < rows; i++)
        {
            byte[] v = new byte[valueBytes];                  // fresh array per row: values are kept by reference
            ThreadLocalRandom.current().nextBytes(v);         // incompressible
            w.addRow((long) i, ByteBuffer.wrap(v));
            if (sample && curF != null)
            {
                long cur = curF.getLong(sw);
                if (cur < prev)
                {
                    resets++;
                    System.out.println("RESET " + resets + " row " + i + " lastObserved " + prev);
                }
                maxObs = Math.max(maxObs, cur);
                prev = cur;
            }
            if (gcEvery > 0 && (i + 1) % gcEvery == 0)
            {
                System.gc();
                long live = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
                peakLive = Math.max(peakLive, live);
                System.out.println("LIVE row " + (i + 1) + " bytes " + live);
            }
        }
        w.close();
        System.out.println("SUMMARY limit=" + limit + " resets=" + resets + " maxObservedCurrentSize=" + maxObs
                           + " peakLive=" + peakLive + " h0=" + h0 + " rows=" + rows);
    }
}
