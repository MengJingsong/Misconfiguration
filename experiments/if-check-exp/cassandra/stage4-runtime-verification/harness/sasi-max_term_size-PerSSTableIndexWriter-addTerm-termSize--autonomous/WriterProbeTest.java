/*
 * Stage-4 harness (not upstream code) for sasi-max_term_size-PerSSTableIndexWriter-addTerm-termSize--autonomous, unit tier (B2, as amended B5).
 * Copied by unit-run.sh into test/unit/org/apache/cassandra/index/sasi/disk/ of a copy-source.sh tree.
 * Every arm drives PerSSTableIndexWriter.Index.add (the writer's own check at :218), never OnDiskIndexBuilder.add directly.
 * Env: STAGE4_OUT (output dir), STAGE4_TMP (scratch dir for index files). Optional STAGE4_SCALE=<int> divides every N (instrument check only).
 * Output: $STAGE4_OUT/writer-results.csv, writer-estimates.csv (estimate series and one line per segment cut).
 */
package org.apache.cassandra.index.sasi.disk;

import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
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

public class WriterProbeTest
{
    static final int SCALE = System.getenv("STAGE4_SCALE") != null ? Integer.parseInt(System.getenv("STAGE4_SCALE")) : 1;
    static final long PER_TERM = 1243;               // S=1023: 64+48+1023 + 60+40+8
    static final String ALNUM = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

    static class Counter extends AppenderBase<ILoggingEvent>
    {
        final AtomicInteger infoReject = new AtomicInteger(), errReject = new AtomicInteger(), segLines = new AtomicInteger(), errors = new AtomicInteger();
        protected void append(ILoggingEvent e)
        {
            String m = e.getFormattedMessage();
            if (e.getLevel() == Level.INFO && m.startsWith("Rejecting value (size")) infoReject.incrementAndGet();
            else if (e.getLevel() == Level.ERROR && m.startsWith("Rejecting value (value size")) errReject.incrementAndGet();
            else if (e.getLevel() == Level.INFO && m.startsWith("Flushed index segment")) segLines.incrementAndGet();
            else if (e.getLevel() == Level.ERROR) errors.incrementAndGet();
        }
    }

    @BeforeClass
    public static void setup() { DatabaseDescriptor.daemonInitialization(); }

    static ByteBuffer term(long i, int size)
    {
        byte[] b = new byte[size];
        byte[] pre = String.format("%08d", i).getBytes(StandardCharsets.US_ASCII);
        for (int k = 0; k < size; k++)
            b[k] = k < pre.length ? pre[k] : (byte) ALNUM.charAt((int) ((i * 31 + k * 17L + (long) k * k) % ALNUM.length()));
        return ByteBuffer.wrap(b);
    }

    static ByteBuffer words(int count)   // count distinct 7-byte words "w000000".."w131071", one space after each: 8 bytes per word
    {
        StringBuilder sb = new StringBuilder(count * 8);
        for (int i = 0; i < count; i++) sb.append(String.format("w%06d ", i));
        return ByteBuffer.wrap(sb.toString().getBytes(StandardCharsets.US_ASCII));
    }

    static DecoratedKey key(long i)
    {
        return new BufferDecoratedKey(new Murmur3Partitioner.LongToken(i * 7919L + 13), ByteBufferUtil.bytes(String.format("key%09d", i)));
    }

    static long usedHeap()
    {
        System.gc(); System.gc();
        Runtime rt = Runtime.getRuntime();
        return rt.totalMemory() - rt.freeMemory();
    }

    static long estimate(PerSSTableIndexWriter.Index idx) throws Exception
    {
        Field f = PerSSTableIndexWriter.Index.class.getDeclaredField("currentBuilder");
        f.setAccessible(true);
        return ((OnDiskIndexBuilder) f.get(idx)).estimatedMemoryUse();
    }

    @Test
    public void probe() throws Exception
    {
        String out = System.getenv("STAGE4_OUT"), tmp = System.getenv("STAGE4_TMP");
        if (out == null || tmp == null) throw new IllegalStateException("STAGE4_OUT / STAGE4_TMP not set");
        new java.io.File(out).mkdirs(); new java.io.File(tmp).mkdirs();
        Counter c = new Counter(); c.setContext(((Logger) LoggerFactory.getLogger("ROOT")).getLoggerContext()); c.start();
        for (Class<?> k : new Class<?>[]{ PerSSTableIndexWriter.class, OnDiskIndexBuilder.class })
        {
            ((Logger) LoggerFactory.getLogger(k)).addAppender(c);
            ((Logger) LoggerFactory.getLogger(k)).setAdditive(false);   // tens of thousands of lines per arm are not wanted in the test log
        }
        try (PrintWriter res = new PrintWriter(out + "/writer-results.csv"); PrintWriter ser = new PrintWriter(out + "/writer-estimates.csv"))
        {
            res.println("arm,size,n_adds,source,option_mb,reached_builder,info_reject_lines,err_reject_lines,est_final,file_len,cuts_before_complete,segment_lines,min_est_at_cut,max_est_at_cut,heap_delta_bytes,millis");
            ser.println("arm,size,source,option_mb,kind,at_add,value");

            // boundary: S around the limit, N = 10,000, default option, COMPACTION
            for (int s : new int[]{ 1022, 1023, 1024, 1025 })
                arm(c, res, ser, "boundary", s, 10_000 / SCALE, OperationType.COMPACTION, null, tmp, false);
            // growth: S = 1023, N = 1k/10k/100k, default option
            for (int n : new int[]{ 1_000, 10_000, 100_000 })
                arm(c, res, ser, "growth", 1023, n / SCALE, OperationType.COMPACTION, null, tmp, n == 100_000);
            // positive control: option 1, 8, default (null) at N = 100k; the default arm is the growth arm, repeated here for the table
            for (String opt : new String[]{ "1", "8", null })
                arm(c, res, ser, "cap", 1023, 100_000 / SCALE, OperationType.COMPACTION, opt, tmp, false);
            // default option, N = 200k: the 0.15 GiB threshold is crossed once
            arm(c, res, ser, "cap200k", 1023, 200_000 / SCALE, OperationType.COMPACTION, null, tmp, false);
            // FLUSH source, option 1 present but ignored: 1 GiB cap not reached
            arm(c, res, ser, "flush", 1023, 100_000 / SCALE, OperationType.FLUSH, "1", tmp, false);
            // tokenized arm: one 1 MiB value of 131,072 distinct words, default option and option 1
            tokenArm(c, res, ser, null, tmp);
            tokenArm(c, res, ser, "1", tmp);
        }
    }

    static PerSSTableIndexWriter.Index[] open(String name, OperationType op, String optionMb, boolean analyzed, String tmp, PerSSTableIndexWriter[] wOut, ColumnIndex[] ciOut, Descriptor[] dOut)
    {
        ColumnMetadata col = ColumnMetadata.regularColumn("ks", "tbl", "v", UTF8Type.instance);
        Map<String, String> opts = new HashMap<>();
        opts.put("target", "v");
        opts.put("mode", "PREFIX");
        if (optionMb != null) opts.put("max_compaction_flush_memory_in_mb", optionMb);
        if (analyzed) { opts.put("analyzed", "true"); opts.put("analyzer_class", "org.apache.cassandra.index.sasi.analyzer.StandardAnalyzer"); }
        IndexMetadata im = IndexMetadata.fromSchemaMetadata("idx_" + name, IndexMetadata.Kind.CUSTOM, opts);
        ColumnIndex ci = new ColumnIndex(UTF8Type.instance, col, im);
        File dir = new File(tmp + "/" + name);
        dir.tryCreateDirectories();
        Descriptor d = new Descriptor(dir, "ks", "tbl", new SequenceBasedSSTableId(1));
        PerSSTableIndexWriter w = new PerSSTableIndexWriter(UTF8Type.instance, d, op, Collections.singletonMap(col, ci));
        wOut[0] = w; ciOut[0] = ci; dOut[0] = d;
        return new PerSSTableIndexWriter.Index[]{ w.getIndex(col) };
    }

    void arm(Counter c, PrintWriter res, PrintWriter ser, String arm, int s, int n, OperationType op, String opt, String tmp, boolean heap) throws Exception
    {
        c.infoReject.set(0); c.errReject.set(0); c.segLines.set(0); c.errors.set(0);
        String name = arm + "-" + s + "-" + n + "-" + op + "-" + (opt == null ? "def" : opt);
        PerSSTableIndexWriter[] w = new PerSSTableIndexWriter[1]; ColumnIndex[] ci = new ColumnIndex[1]; Descriptor[] d = new Descriptor[1];
        long h0 = heap ? usedHeap() : 0;
        long t0 = System.currentTimeMillis();
        PerSSTableIndexWriter.Index idx = open(name, op, opt, false, tmp, w, ci, d)[0];
        w[0].begin();
        long optBytes = opt == null ? 161_061_273L : Long.parseLong(opt) * 1048576L;
        long cap = op == OperationType.FLUSH ? 1073741824L : optBytes;
        int reached = 0, cuts = 0;
        long minAtCut = Long.MAX_VALUE, maxAtCut = -1;
        for (int i = 0; i < n; i++)
        {
            DecoratedKey k = key(i);
            long before = estimate(idx);
            int segsBefore = idx.segments.size();
            w[0].startPartition(k, i, i);
            idx.add(term(i, s), k, i);
            boolean cut = idx.segments.size() != segsBefore;
            long after = estimate(idx);
            if (cut || after > before) reached++;
            if (cut)
            {
                cuts++;
                long atCut = before + PER_TERM;   // the builder that was cut held `before` plus this add's 1243 bytes
                minAtCut = Math.min(minAtCut, atCut); maxAtCut = Math.max(maxAtCut, atCut);
                ser.println(String.join(",", arm, "" + s, "" + op, opt == null ? "def" : opt, "cut", "" + (i + 1), "" + atCut));
            }
            if ((i + 1) % 10_000 == 0) ser.println(String.join(",", arm, "" + s, "" + op, opt == null ? "def" : opt, "estimate", "" + (i + 1), "" + after));
        }
        long estFinal = estimate(idx);
        long hd = 0;
        if (heap) hd = usedHeap() - h0;
        int cutsBefore = idx.segments.size();
        w[0].complete();
        File f = d[0].fileFor(ci[0].getComponent());
        long len = f.exists() ? f.length() : -1;
        res.println(String.join(",", arm, "" + s, "" + n, "" + op, opt == null ? "def" : opt, "" + reached, "" + c.infoReject.get(), "" + c.errReject.get(), "" + estFinal, "" + len, "" + cutsBefore, "" + c.segLines.get(),
                                cuts == 0 ? "" : "" + minAtCut, cuts == 0 ? "" : "" + maxAtCut, "" + hd, "" + (System.currentTimeMillis() - t0)));
        res.flush(); ser.flush();
    }

    void tokenArm(Counter c, PrintWriter res, PrintWriter ser, String opt, String tmp) throws Exception
    {
        c.infoReject.set(0); c.errReject.set(0); c.segLines.set(0); c.errors.set(0);
        String name = "token-" + (opt == null ? "def" : opt);
        PerSSTableIndexWriter[] w = new PerSSTableIndexWriter[1]; ColumnIndex[] ci = new ColumnIndex[1]; Descriptor[] d = new Descriptor[1];
        long t0 = System.currentTimeMillis();
        PerSSTableIndexWriter.Index idx = open(name, OperationType.COMPACTION, opt, true, tmp, w, ci, d)[0];
        w[0].begin();
        ByteBuffer v = words(131_072 / SCALE);
        int valueBytes = v.remaining();
        DecoratedKey k = key(1);
        w[0].startPartition(k, 0, 0);
        int segsBefore = idx.segments.size();
        idx.add(v, k, 0);
        int cuts = idx.segments.size() - segsBefore;
        long est = estimate(idx);   // 0 when the single add caused a cut (the cut builder was replaced), else the estimate of the one value
        ser.println(String.join(",", "token", "" + valueBytes, "COMPACTION", opt == null ? "def" : opt, "estimate_after_add", "1", "" + est));
        w[0].complete();
        File f = d[0].fileFor(ci[0].getComponent());
        res.println(String.join(",", "token", "" + valueBytes, "1", "COMPACTION", opt == null ? "def" : opt, "" + (131_072 / SCALE), "" + c.infoReject.get(), "" + c.errReject.get(), "" + est, "" + (f.exists() ? f.length() : -1), "" + cuts, "" + c.segLines.get(), "", "", "", "" + (System.currentTimeMillis() - t0)));
        res.flush(); ser.flush();
    }
}
