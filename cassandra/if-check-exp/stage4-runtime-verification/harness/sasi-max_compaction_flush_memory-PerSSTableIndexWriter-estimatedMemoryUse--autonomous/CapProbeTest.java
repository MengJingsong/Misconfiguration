/*
 * Stage-4 harness (not upstream code) for sasi-max_compaction_flush_memory-PerSSTableIndexWriter-estimatedMemoryUse--autonomous, unit tier (B2).
 * Copied by unit-run.sh into test/unit/org/apache/cassandra/index/sasi/disk/ of a copy-source.sh tree.
 * Env: STAGE4_OUT (output dir), STAGE4_TMP (scratch dir for index files), optional STAGE4_N (adds per arm, instrument check only).
 * Writes $STAGE4_OUT/unit-results.csv (one line per arm) and $STAGE4_OUT/unit-cuts.csv (one line per segment cut).
 */
package org.apache.cassandra.index.sasi.disk;

import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.Collections;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;
import java.util.concurrent.Future;
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
import org.apache.cassandra.db.marshal.Int32Type;
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

public class CapProbeTest
{
    static final int N = System.getenv("STAGE4_N") != null ? Integer.parseInt(System.getenv("STAGE4_N")) : 100_000;

    static class Counter extends AppenderBase<ILoggingEvent>
    {
        final AtomicInteger flushedSegment = new AtomicInteger(), failed = new AtomicInteger();
        protected void append(ILoggingEvent e)
        {
            String m = e.getFormattedMessage();
            if (e.getLevel() == Level.INFO && m.startsWith("Flushed index segment")) flushedSegment.incrementAndGet();
            if (e.getLevel() == Level.ERROR) failed.incrementAndGet();
        }
    }

    @BeforeClass
    public static void setupDD()
    {
        DatabaseDescriptor.daemonInitialization();
    }

    static DecoratedKey key(int i)
    {
        ByteBuffer k = ByteBufferUtil.bytes(String.format("key%06d", i));
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
        ((Logger) LoggerFactory.getLogger(PerSSTableIndexWriter.class)).addAppender(c);

        try (PrintWriter res = new PrintWriter(out + "/unit-results.csv"); PrintWriter cuts = new PrintWriter(out + "/unit-cuts.csv"))
        {
            res.println("arm,source,cap_option_mb,adds,segments_before_complete,segment_files_on_disk,segments_nonnull,max_estimate,estimate_at_first_cut,estimate_active_before_complete,heap_delta_active_bytes,flushed_segment_logs,errors_logged,segment_files_after_complete,final_file_len,final_terms,millis");
            cuts.println("arm,add_index,segments,estimate_at_cut");
            // order: COMPACTION 1, 4, 16, default (no option), then FLUSH with the 1 MiB option and FLUSH default
            arm(c, res, cuts, "comp-1", OperationType.COMPACTION, "1", tmp);
            arm(c, res, cuts, "comp-4", OperationType.COMPACTION, "4", tmp);
            arm(c, res, cuts, "comp-16", OperationType.COMPACTION, "16", tmp);
            arm(c, res, cuts, "comp-default", OperationType.COMPACTION, null, tmp);
            arm(c, res, cuts, "flush-1", OperationType.FLUSH, "1", tmp);
            arm(c, res, cuts, "flush-default", OperationType.FLUSH, null, tmp);
        }
    }

    void arm(Counter c, PrintWriter res, PrintWriter cuts, String name, OperationType src, String capMb, String tmp) throws Exception
    {
        c.flushedSegment.set(0); c.failed.set(0);
        long t0 = System.currentTimeMillis();
        long h0 = used();
        ColumnMetadata col = ColumnMetadata.regularColumn("ks", "tbl", "age", Int32Type.instance);
        Map<String, String> opts = new HashMap<>();
        opts.put("target", "age");
        opts.put("mode", "PREFIX");
        if (capMb != null) opts.put("max_compaction_flush_memory_in_mb", capMb);
        IndexMetadata im = IndexMetadata.fromSchemaMetadata("idx_" + name, IndexMetadata.Kind.CUSTOM, opts);
        ColumnIndex ci = new ColumnIndex(UTF8Type.instance, col, im);
        File dir = new File(tmp + "/w-" + name);
        dir.tryCreateDirectories();
        Descriptor d = new Descriptor(dir, "ks", "tbl", new SequenceBasedSSTableId(1));
        PerSSTableIndexWriter w = new PerSSTableIndexWriter(UTF8Type.instance, d, src, Collections.singletonMap(col, ci));
        PerSSTableIndexWriter.Index idx = w.getIndex(col);
        Field fb = PerSSTableIndexWriter.Index.class.getDeclaredField("currentBuilder");
        fb.setAccessible(true);
        w.begin();
        long maxEst = 0, firstCut = -1;
        int prevSegs = 0;
        for (int i = 0; i < N; i++)
        {
            DecoratedKey k = key(i);
            w.startPartition(k, i, i);
            OnDiskIndexBuilder before = (OnDiskIndexBuilder) fb.get(idx);   // the builder this add goes to
            idx.add(Int32Type.instance.decompose(i), k, i);
            long est = before.estimatedMemoryUse();                          // its estimate after this add (the value at a cut)
            if (est > maxEst) maxEst = est;
            int segs = idx.segments.size();
            if (segs != prevSegs)
            {
                cuts.println(name + "," + (i + 1) + "," + segs + "," + est);
                if (firstCut < 0) firstCut = est;
                prevSegs = segs;
            }
        }
        int segsBefore = idx.segments.size();
        int nonnull = 0;
        for (Future<OnDiskIndex> f : idx.segments) if (f.get() != null) nonnull++;   // wait for the segment writes
        int filesOnDisk = 0;
        String[] names = new java.io.File(dir.path()).list();
        if (names != null) for (String n : names) if (n.matches(".*_\\d+$")) filesOnDisk++;
        OnDiskIndexBuilder active = (OnDiskIndexBuilder) fb.get(idx);
        long activeEst = active.estimatedMemoryUse();
        long h1 = used();
        w.complete();
        File f = d.fileFor(ci.getComponent());
        long len = f.exists() ? f.length() : -1;
        int after = 0;
        names = new java.io.File(dir.path()).list();
        if (names != null) for (String n : names) if (n.matches(".*_\\d+$")) after++;
        long terms = 0;
        if (len > 0)
        {
            try (OnDiskIndex oi = new OnDiskIndex(f, Int32Type.instance, p -> null))
            {
                Iterator<OnDiskIndex.DataTerm> it = oi.iterator();
                while (it.hasNext()) { it.next(); terms++; }
            }
        }
        res.println(String.join(",", name, src.name(), capMb == null ? "default" : capMb, "" + N, "" + segsBefore, "" + filesOnDisk, "" + nonnull, "" + maxEst, "" + firstCut, "" + activeEst, "" + (h1 - h0), "" + c.flushedSegment.get(), "" + c.failed.get(), "" + after, "" + len, "" + terms, "" + (System.currentTimeMillis() - t0)));
        res.flush(); cuts.flush();
        idx = null; w = null; active = null;
        deleteDir(new java.io.File(dir.path()));
    }

    static void deleteDir(java.io.File d)
    {
        java.io.File[] fs = d.listFiles();
        if (fs != null) for (java.io.File f : fs) f.delete();
        d.delete();
    }
}
