package org.apache.cassandra.io.util;

import java.io.*;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.CountDownLatch;

public class TempBufferProbe
{
    static int cur() { return DataOutputStreamPlus.retrieveTemporaryBuffer(1).length; } // 1 <= len: never reallocates
    static final OutputStream SINK = new OutputStream() {
        public void write(int b) {}
        public void write(byte[] b, int o, int l) {}
    };
    static long heapUsed() { System.gc(); System.gc(); return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed(); }

    public static void main(String[] args) throws Exception
    {
        System.out.println("P=" + System.getProperty("cassandra.data_output_stream_plus_temp_buffer_size", "default"));
        // 1. direct calls, one thread, increasing requests
        System.out.println("initial len=" + cur());
        for (int r : new int[]{ 100, 5000, 8193, 65537, 1 << 20, 4 << 20, 20 << 20 })
            System.out.println("request=" + r + " len=" + DataOutputStreamPlus.retrieveTemporaryBuffer(r).length);
        // 2. real paths, each on a fresh thread
        Thread t1 = new Thread(() -> { try {
            new WrappedDataOutputStreamPlus(SINK).write(ByteBuffer.allocateDirect(4 << 20));
            System.out.println("directWrite 4MiB len=" + cur()); } catch (IOException e) { throw new UncheckedIOException(e); } });
        t1.start(); t1.join();
        Thread t2 = new Thread(() -> { try {
            char[] c = new char[60000]; Arrays.fill(c, 'x');
            new WrappedDataOutputStreamPlus(SINK).writeUTF(new String(c));
            System.out.println("writeUTF 60000 len=" + cur()); } catch (IOException e) { throw new UncheckedIOException(e); } });
        t2.start(); t2.join();
        // 3. 32 live threads, each writes a 4 MiB direct buffer, then waits
        int n = 32; CountDownLatch done = new CountDownLatch(n), release = new CountDownLatch(1);
        int[] lens = new int[n];
        ByteBuffer src = ByteBuffer.allocateDirect(4 << 20);
        long before = heapUsed();
        for (int i = 0; i < n; i++) { final int id = i; new Thread(() -> { try {
            new WrappedDataOutputStreamPlus(SINK).write(src.duplicate()); lens[id] = cur(); done.countDown(); release.await();
        } catch (Exception e) { throw new RuntimeException(e); } }).start(); }
        done.await();
        long after = heapUsed();
        System.out.println("threads=" + n + " sumLen=" + Arrays.stream(lens).asLongStream().sum()
                           + " maxLen=" + Arrays.stream(lens).max().getAsInt() + " heapDelta=" + (after - before));
        release.countDown();
    }
}
