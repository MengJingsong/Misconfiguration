/*
 * Stage-4 harness (not upstream code) for sasi-max_term_size-TrieMemIndex-add-termSize--autonomous, unit tier (B2, as amended B5).
 * Copied by unit-run.sh into test/unit/org/apache/cassandra/index/sasi/memory/ of a copy-source.sh tree.
 * Env: STAGE4_OUT (output dir, required).
 * Writes $STAGE4_OUT/unit-results.csv (one line per arm) and $STAGE4_OUT/unit-estimates.csv (every add's returned size).
 */
package org.apache.cassandra.index.sasi.memory;

import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
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
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.db.marshal.AbstractType;
import org.apache.cassandra.db.marshal.UTF8Type;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.index.sasi.conf.ColumnIndex;
import org.apache.cassandra.index.sasi.disk.OnDiskIndexBuilder;
import org.apache.cassandra.index.sasi.plan.Expression;
import org.apache.cassandra.index.sasi.utils.RangeIterator;
import org.apache.cassandra.schema.ColumnMetadata;
import org.apache.cassandra.schema.IndexMetadata;
import org.apache.cassandra.utils.ByteBufferUtil;
import org.slf4j.LoggerFactory;

public class TrieMemIndexSizeTest
{
    static final String ALNUM = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

    static class Counter extends AppenderBase<ILoggingEvent>
    {
        final AtomicInteger cantAdd = new AtomicInteger(), other = new AtomicInteger();
        protected void append(ILoggingEvent e)
        {
            if (e.getLevel() == Level.INFO && e.getFormattedMessage().startsWith("Can't add term of column")) cantAdd.incrementAndGet();
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
            b[0] = (byte) ALNUM.charAt(i % ALNUM.length());   // only 62 distinct 1-byte terms exist
            return ByteBuffer.wrap(b);
        }
        Random r = new Random(31L * size + i);
        for (int k = 0; k < size; k++)
            b[k] = (byte) ALNUM.charAt(r.nextInt(ALNUM.length()));
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

    static ColumnIndex column(AbstractType<?> type, String mode, String name)
    {
        ColumnMetadata col = ColumnMetadata.regularColumn("ks", "tbl", "v", type);
        Map<String, String> opts = new HashMap<>();
        opts.put("target", "v");
        opts.put("mode", mode);
        opts.put("analyzed", "false");
        IndexMetadata im = IndexMetadata.fromSchemaMetadata(name, IndexMetadata.Kind.CUSTOM, opts);
        return new ColumnIndex(UTF8Type.instance, col, im);
    }

    static boolean found(ColumnIndex ci, AbstractType<?> type, ByteBuffer v)
    {
        Expression e = new Expression("v", type).setOp(Expression.Op.EQ).setLower(new Expression.Bound(v, true));
        RangeIterator<Long, ?> it = ci.getCurrentMemtable().search(e);
        return it != null && it.getCount() > 0;
    }

    PrintWriter res, est;
    Counter c;

    void arm(String mode, int L, int N) throws Exception
    {
        c.cantAdd.set(0);
        long t0 = System.currentTimeMillis();
        long h0 = used();
        boolean skip = mode.equals("SKIPLIST");
        AbstractType<?> type = skip ? Int32Type.instance : UTF8Type.instance;
        ColumnIndex ci = column(type, skip ? "PREFIX" : mode, "idx_" + mode + "_" + L + "_" + N);
        long sum = 0;
        int accepted = 0;
        ByteBuffer first = null, last = null;
        for (int i = 0; i < N; i++)
        {
            ByteBuffer v = skip ? ByteBufferUtil.bytes(1000 + i * 7) : term(i, L);
            if (i == 0) first = v.duplicate();
            if (i == N - 1) last = v.duplicate();
            long r = ci.getCurrentMemtable().index(key(i), v);
            sum += r;
            if (r > 0) accepted++;
            est.println(mode + "," + L + "," + N + "," + i + "," + r);
        }
        long h1 = used();
        boolean f1 = found(ci, type, first), f2 = found(ci, type, last);
        res.println(String.join(",", mode, "" + L, "" + N, "" + accepted, "" + sum, "" + f1, "" + f2, "" + c.cantAdd.get(), "" + (h1 - h0), "" + (System.currentTimeMillis() - t0), "" + OnDiskIndexBuilder.MAX_TERM_SIZE));
        res.flush(); est.flush();
        ci = null;
    }

    @Test
    public void probe() throws Exception
    {
        String out = System.getenv("STAGE4_OUT");
        if (out == null) throw new IllegalStateException("STAGE4_OUT not set");
        new java.io.File(out).mkdirs();
        c = new Counter(); c.setContext(((Logger) LoggerFactory.getLogger("ROOT")).getLoggerContext()); c.start();
        Logger lg = (Logger) LoggerFactory.getLogger(TrieMemIndex.class);
        lg.addAppender(c);
        lg.setAdditive(false);
        try (PrintWriter r = new PrintWriter(out + "/unit-results.csv"); PrintWriter e = new PrintWriter(out + "/unit-estimates.csv"))
        {
            res = r; est = e;
            res.println("mode,L,N,accepted_adds,sum_estimate,found_first,found_last,cant_add_logs,heap_delta_bytes,millis,MAX_TERM_SIZE");
            est.println("mode,L,N,i,returned");
            for (String mode : new String[]{ "PREFIX", "CONTAINS" })
            {
                for (int L : new int[]{ 100, 512, 1023 })
                    for (int N : new int[]{ 1, 10, mode.equals("CONTAINS") && L == 1023 ? 30 : 100 })
                        arm(mode, L, N);
                arm(mode, 1, 10);
                arm(mode, 1022, 10);
                for (int L : new int[]{ 1024, 1025, 4096 })
                    arm(mode, L, 10);
            }
            for (int N : new int[]{ 1, 10, 100 })
                arm("SKIPLIST", 4, N);
        }
    }
}
