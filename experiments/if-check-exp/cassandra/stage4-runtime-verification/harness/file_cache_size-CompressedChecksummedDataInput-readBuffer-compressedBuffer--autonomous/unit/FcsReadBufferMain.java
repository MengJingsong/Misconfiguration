package org.apache.cassandra.hints;

import java.io.IOException;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

import com.google.common.collect.ImmutableMap;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.config.ParameterizedClass;
import org.apache.cassandra.db.Mutation;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.Schema;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.utils.memory.BufferPool;
import org.apache.cassandra.utils.memory.BufferPools;
import org.apache.cassandra.io.compress.BufferType;

/**
 * Stage-4 unit tier for file_cache_size / CompressedChecksummedDataInput.readBuffer.
 * args: mode(reader|control) compressor(LZ4Compressor|DeflateCompressor) blockBytes nHints readers
 * One JVM per cell. Prints "OBS <label> key=value ..." lines.
 */
public class FcsReadBufferMain
{
    static BufferPool pool;
    static final String KS = "fcs_ks", TBL = "t";

    static long direct()
    {
        for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (b.getName().equals("direct")) return b.getMemoryUsed();
        return -1;
    }

    static long heap()
    {
        System.gc();
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

    static void snap(String label)
    {
        long size = pool.sizeInBytes(), over = pool.overflowMemoryInBytes();
        System.out.println("OBS " + label + " threshold=" + pool.memoryUsageThreshold() + " size=" + size + " overflow=" + over
                           + " pooled=" + (size - over) + " used=" + pool.usedSizeInBytes() + " direct=" + direct() + " heap=" + heap());
    }

    static Hint hint(int idx, long ts, int bytes)
    {
        TableMetadata table = Schema.instance.getTableMetadata(KS, TBL);
        byte[] v = new byte[bytes];
        new Random(idx * 7919L + bytes).nextBytes(v);   // incompressible
        Mutation m = new RowUpdateBuilder(table, TimeUnit.MILLISECONDS.toMicros(ts), ByteBuffer.wrap(new byte[]{ (byte) idx }))
                     .clustering(ByteBuffer.wrap(new byte[]{ (byte) idx }))
                     .add("val", ByteBuffer.wrap(v)).build();
        return Hint.create(m, ts);
    }

    public static void main(String[] a) throws Exception
    {
        String mode = a[0], comp = a[1];
        int B = Integer.parseInt(a[2]), n = Integer.parseInt(a[3]), R = Integer.parseInt(a[4]);
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1), SchemaLoader.standardCFMD(KS, TBL));
        pool = BufferPools.forChunkCache();
        System.out.println("OBS config mode=" + mode + " comp=" + comp + " B=" + B + " n=" + n + " R=" + R + " threshold=" + pool.memoryUsageThreshold());
        snap("baseline");

        if (mode.equals("control"))
        {
            long threshold = pool.memoryUsageThreshold(), want = 3 * threshold, got = 0;
            List<ByteBuffer> held = new ArrayList<>();
            long nextReport = threshold;
            boolean reportedAtThreshold = false;
            while (got < want)
            {
                held.add(pool.get(64 * 1024, BufferType.OFF_HEAP));
                got += 64 * 1024;
                if (!reportedAtThreshold && got >= threshold) { snap("control_at_1x"); reportedAtThreshold = true; }
            }
            snap("control_at_3x");
            for (ByteBuffer b : held) pool.put(b);
            snap("control_released");
            System.out.println("OBS done");
            System.exit(0);
        }

        ImmutableMap<String, Object> params = ImmutableMap.of(HintsDescriptor.COMPRESSION,
                                                     ImmutableMap.of(ParameterizedClass.CLASS_NAME, comp));
        UUID host = UUID.randomUUID();
        long ts = System.currentTimeMillis();
        HintsDescriptor d = new HintsDescriptor(host, ts, params);
        File dir = new File(Files.createTempDirectory("fcs-hints").toFile());
        ByteBuffer wb = ByteBuffer.allocateDirect(HintsWriteExecutor.WRITE_BUFFER_SIZE);
        try (HintsWriter w = HintsWriter.create(dir, d))
        {
            for (int i = 0; i < n; i++)
                try (HintsWriter.Session s = w.newSession(wb)) { s.append(hint(i, ts + i, B)); }   // one block per hint
        }
        File f = d.file(dir);
        System.out.println("OBS file bytes=" + f.length() + " path=" + f.absolutePath());
        snap("after_write");

        final AtomicLong peakOver = new AtomicLong(Long.MIN_VALUE), peakDirect = new AtomicLong(), peakPooled = new AtomicLong();
        final AtomicBoolean stop = new AtomicBoolean();
        Thread sampler = new Thread(() -> {
            while (!stop.get())
            {
                peakOver.accumulateAndGet(pool.overflowMemoryInBytes(), Math::max);
                peakPooled.accumulateAndGet(pool.sizeInBytes() - pool.overflowMemoryInBytes(), Math::max);
                peakDirect.accumulateAndGet(direct(), Math::max);
                try { Thread.sleep(10); } catch (InterruptedException e) { return; }
            }
        });
        sampler.setDaemon(true);
        sampler.start();

        CountDownLatch arrived = new CountDownLatch(R), release = new CountDownLatch(1);
        AtomicInteger hintsRead = new AtomicInteger(), failures = new AtomicInteger();
        List<Thread> ts_ = new ArrayList<>();
        for (int r = 0; r < R; r++)
        {
            Thread t = new Thread(() -> {
                try (HintsReader reader = HintsReader.open(f))
                {
                    if (!(reader.getInput() instanceof CompressedChecksummedDataInput)) throw new IllegalStateException("not compressed input");
                    for (HintsReader.Page page : reader)
                    {
                        Iterator<Hint> it = page.hintsIterator();
                        while (it.hasNext()) { it.next(); hintsRead.incrementAndGet(); }
                    }
                    arrived.countDown();
                    release.await();
                }
                catch (Throwable e) { failures.incrementAndGet(); e.printStackTrace(); arrived.countDown(); }
            }, "fcs-reader-" + r);
            t.start();
            ts_.add(t);
        }
        arrived.await();
        Thread.sleep(300);
        snap("parked");
        System.out.println("OBS parked hintsRead=" + hintsRead.get() + " expected=" + (long) n * R + " failures=" + failures.get()
                           + " peakOverflow=" + peakOver.get() + " peakPooled=" + peakPooled.get() + " peakDirect=" + peakDirect.get());
        release.countDown();
        for (Thread t : ts_) t.join();
        Thread.sleep(300);
        snap("closed");
        stop.set(true);
        System.out.println("OBS done");
        System.exit(failures.get() == 0 ? 0 : 3);
    }
}
