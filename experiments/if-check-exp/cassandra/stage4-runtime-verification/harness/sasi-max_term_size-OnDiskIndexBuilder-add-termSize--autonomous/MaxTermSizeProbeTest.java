/*
 * Stage-4 harness (not upstream code) for sasi-max_term_size-OnDiskIndexBuilder-add-termSize--autonomous, unit tier (B2).
 * Copied by unit-run.sh into test/unit/org/apache/cassandra/index/sasi/disk/ of a copy-source.sh tree.
 * Env: STAGE4_OUT (output dir, required), STAGE4_TMP (scratch dir for index files, required).
 * Writes $STAGE4_OUT/unit-results.csv (one line per measurement) and $STAGE4_OUT/unit-estimates.csv.
 */
package org.apache.cassandra.index.sasi.disk;

import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.Random;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.BeforeClass;
import org.junit.Test;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.AppenderBase;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.BufferDecoratedKey;
import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.db.compaction.OperationType;
import org.apache.cassandra.db.marshal.UTF8Type;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.index.sasi.conf.ColumnIndex;
import org.apache.cassandra.io.sstable.Descriptor;
import org.apache.cassandra.io.sstable.SequenceBasedSSTableId;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.schema.ColumnMetadata;
import org.apache.cassandra.schema.IndexMetadata;
import org.apache.cassandra.utils.ByteBufferUtil;
import org.slf4j.LoggerFactory;

public class MaxTermSizeProbeTest
{
    static final int N = System.getenv("STAGE4_N") != null ? Integer.parseInt(System.getenv("STAGE4_N")) : 100_000;   // STAGE4_N only for the instrument check
    static final int CAP_ADDS = (int) Math.ceil(10.0 * 16 * 1048576 / (220 + 512));   // 229,197
    static final String ALNUM = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

    static class Counter extends AppenderBase<ILoggingEvent>
    {
        final AtomicInteger errorRejecting = new AtomicInteger(), infoRejecting = new AtomicInteger(), infoFlushedSegment = new AtomicInteger(), other = new AtomicInteger();
        protected void append(ILoggingEvent e)
        {
            String m = e.getFormattedMessage();
            if (e.getLevel() == Level.ERROR && m.startsWith("Rejecting value (value size")) errorRejecting.incrementAndGet();
            else if (e.getLevel() == Level.INFO && m.startsWith("Rejecting value (size")) infoRejecting.incrementAndGet();
            else if (e.getLevel() == Level.INFO && m.startsWith("Flushed index segment")) infoFlushedSegment.incrementAndGet();
            else other.incrementAndGet();
        }
    }

    @BeforeClass
    public static void setupDD()
    {
        DatabaseDescriptor.daemonInitialization();
    }

    static ByteBuffer term(int i, int size)
    {
        byte[] b = new byte[size];
        if (size == 1)
        {
            b[0] = (byte) ALNUM.charAt(i % ALNUM.length());   // only 62 distinct terms exist
            return ByteBuffer.wrap(b);
        }
        Random r = new Random(31L * size + i);
        String prefix = String.format("%08d", i);
        for (int k = 0; k < size; k++)
            b[k] = (byte) (k < 8 && k < prefix.length() && size >= 8 ? prefix.charAt(k) : ALNUM.charAt(r.nextInt(ALNUM.length())));
        if (size < 8)   // sizes 2..7: counter in the low positions, still distinct for the sizes used (not used by the plan)
            for (int k = 0; k < size; k++) b[k] = (byte) prefix.charAt(8 - size + k);
        return ByteBuffer.wrap(b);
    }

    static DecoratedKey key(int i)
    {
        ByteBuffer k = ByteBufferUtil.bytes(String.format("key%08d", i));
        return new BufferDecoratedKey(new Murmur3Partitioner.LongToken(i * 7919L + 13), k);
    }

    static long used()
    {
        System.gc(); System.gc();
        Runtime rt = Runtime.getRuntime();
        return rt.totalMemory() - rt.freeMemory();
    }

    @Test
    public void probe() throws Exception
    {
        String out = System.getenv("STAGE4_OUT"), tmp = System.getenv("STAGE4_TMP");
        if (out == null || tmp == null) throw new IllegalStateException("STAGE4_OUT / STAGE4_TMP not set");
        new java.io.File(out).mkdirs(); new java.io.File(tmp).mkdirs();
        Counter c = new Counter(); c.setContext(((Logger) LoggerFactory.getLogger("ROOT")).getLoggerContext()); c.start();
        ((Logger) LoggerFactory.getLogger(OnDiskIndexBuilder.class)).addAppender(c);
        ((Logger) LoggerFactory.getLogger(PerSSTableIndexWriter.class)).addAppender(c);
        ((Logger) LoggerFactory.getLogger(OnDiskIndexBuilder.class)).setAdditive(false);   // 100,000 error lines per arm are not wanted in the test log
        ((Logger) LoggerFactory.getLogger(PerSSTableIndexWriter.class)).setAdditive(false);

        try (PrintWriter res = new PrintWriter(out + "/unit-results.csv"); PrintWriter ser = new PrintWriter(out + "/unit-estimates.csv"))
        {
            res.println("arm,size,n_adds,cap_mb,accepted_adds,err_rejecting_logs,info_rejecting_logs,est_final,file_len,segments_before_complete,flushed_segment_logs,heap_delta_bytes,millis");
            ser.println("arm,size,adds,estimate");

            // Part 1: direct OnDiskIndexBuilder.add (B2e step 2 and 4), PREFIX mode (B5.1)
            for (int S : new int[]{ 1, 512, 1023, 1024, 1025, 4096 })
            {
                c.errorRejecting.set(0); c.infoRejecting.set(0);
                long t0 = System.currentTimeMillis();
                long h0 = used();
                OnDiskIndexBuilder b = new OnDiskIndexBuilder(UTF8Type.instance, UTF8Type.instance, OnDiskIndexBuilder.Mode.PREFIX);
                for (int i = 0; i < N; i++)
                {
                    b.add(term(i, S), key(i), i);
                    if ((i + 1) % 10_000 == 0) ser.println("direct," + S + "," + (i + 1) + "," + b.estimatedMemoryUse());
                }
                long h1 = used();
                long est = b.estimatedMemoryUse();
                int rejected = c.errorRejecting.get();
                File f = new File(tmp + "/direct-" + S + ".db");
                boolean wrote = b.finish(f);
                long len = f.exists() ? f.length() : -1;
                res.println(String.join(",", "direct", "" + S, "" + N, "", "" + (N - rejected), "" + rejected, "" + c.infoRejecting.get(), "" + est, "" + len + (wrote ? "" : ""), "", "", "" + (h1 - h0), "" + (System.currentTimeMillis() - t0)));
                res.println("finish_returned,direct," + S + "," + wrote + ",isEmpty," + b.isEmpty());
                res.flush(); ser.flush();
                if (f.exists()) f.tryDelete();
                b = null;
            }

            // Part 2: writer path, COMPACTION source, cap control (B2e step 3, B2h(d))
            for (int cap : new int[]{ 1, 4, 16 })
                writerArm(c, res, ser, "writer-cap", 512, cap, CAP_ADDS, tmp);   // same workload for every cap: 10 x the 16 MB cap (B2e step 3), so segments fall as C rises
            // boundary through the writer's own filter (the first copy of the check): 1023 accepted, 1024 rejected
            writerArm(c, res, ser, "writer-boundary", 1023, 16, 20_000, tmp);
            writerArm(c, res, ser, "writer-boundary", 1024, 16, 20_000, tmp);
        }
    }

    void writerArm(Counter c, PrintWriter res, PrintWriter ser, String arm, int S, int capMb, int adds, String tmp) throws Exception
    {
        c.errorRejecting.set(0); c.infoRejecting.set(0); c.infoFlushedSegment.set(0);
        long t0 = System.currentTimeMillis();
        ColumnMetadata col = ColumnMetadata.regularColumn("ks", "tbl", "v", UTF8Type.instance);
        Map<String, String> opts = new HashMap<>();
        opts.put("target", "v");
        opts.put("mode", "PREFIX");
        opts.put("max_compaction_flush_memory_in_mb", "" + capMb);
        IndexMetadata im = IndexMetadata.fromSchemaMetadata("idx_" + arm + "_" + S + "_" + capMb, IndexMetadata.Kind.CUSTOM, opts);
        ColumnIndex ci = new ColumnIndex(UTF8Type.instance, col, im);
        File dir = new File(tmp + "/w-" + arm + "-" + S + "-" + capMb);
        dir.tryCreateDirectories();
        Descriptor d = new Descriptor(dir, "ks", "tbl", new SequenceBasedSSTableId(1));
        PerSSTableIndexWriter w = new PerSSTableIndexWriter(UTF8Type.instance, d, OperationType.COMPACTION, Collections.singletonMap(col, ci));
        PerSSTableIndexWriter.Index idx = w.getIndex(col);
        w.begin();
        int prevSegs = 0;
        for (int i = 0; i < adds; i++)
        {
            DecoratedKey k = key(i);
            w.startPartition(k, i, i);
            idx.add(term(i, S), k, i);
            int segs = idx.segments.size();
            if (segs != prevSegs) { ser.println(arm + "-segmentcut," + S + "," + (i + 1) + "," + segs + ",cap_mb=" + capMb); prevSegs = segs; }
        }
        int segsBefore = idx.segments.size();
        w.complete();
        File f = d.fileFor(ci.getComponent());
        long len = f.exists() ? f.length() : -1;
        res.println(String.join(",", arm, "" + S, "" + adds, "" + capMb, "", "" + c.errorRejecting.get(), "" + c.infoRejecting.get(), "", "" + len, "" + segsBefore, "" + c.infoFlushedSegment.get(), "", "" + (System.currentTimeMillis() - t0)));
        res.flush(); ser.flush();
    }
}
