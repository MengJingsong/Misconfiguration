/*
 * Stage-4 unit tier (B2) of transition-bytes-collector-add-buffer-length--autonomous. Not part of Cassandra.
 * Copied into test/unit/org/apache/cassandra/io/tries/ of the run tree by unit-run.sh (package access to the protected
 * fields of Walker.TransitionBytesCollector). Asserts nothing: prints "TC ..." lines to the file named by -Dtc.out
 * (default build/test/tc-unit.txt), which unit-analyze.py compares with B2f.
 * Run through Ant (testsome) and, for other -Xmx values, through org.junit.runner.JUnitCore (see unit-run.sh).
 */
package org.apache.cassandra.io.tries;

import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.util.Random;

import org.apache.lucene.util.ArrayUtil;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.guardrails.Guardrails;
import org.apache.cassandra.index.sai.disk.v1.trie.TrieTermsDictionaryReader;
import org.apache.cassandra.index.sai.disk.v1.trie.TrieTermsIterator;
import org.apache.cassandra.io.tries.Walker.TransitionBytesCollector;
import org.apache.cassandra.utils.bytecomparable.ByteComparable;

public class CollectorGrowthTest
{
    static final int[] LENGTHS = {8, 32, 33, 1024, 8192, 65535};
    static final String[] THRESHOLDS = {"1KiB", "8KiB", "64KiB"};
    static final int[] PROBE = {1023, 1024, 1025, 8191, 8192, 8193, 40960, 65536, 65537};
    static final int REPS = 3;
    static PrintWriter out;
    static com.sun.management.ThreadMXBean mx;
    static String tag;

    /** The collector under test with its protected state exposed. Same class code as in Walker.getMaxTerm/getMinTerm. */
    static class Coll extends TransitionBytesCollector
    {
        int cap() { return bytes.length; }
        int pos() { return pos; }
    }

    @BeforeClass
    public static void init() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        mx = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
        tag = System.getProperty("tc.tag", "ant");
        String path = System.getProperty("tc.out", "build/test/tc-unit.txt");
        new java.io.File(path).getParentFile().mkdirs();
        out = new PrintWriter(new java.io.FileWriter(path));
        p("env tag=" + tag + " xmx=" + Runtime.getRuntime().maxMemory() + " java=" + System.getProperty("java.version")
          + " lucene=" + org.apache.lucene.util.Version.LATEST);
        // for unit-run.sh: class path and JVM arguments of this JVM, to run the same class under other -Xmx values
        if (tag.equals("ant"))
        {
            try (PrintWriter e = new PrintWriter(new java.io.FileWriter("build/test/tc-env.txt")))
            {
                e.println("CP=" + System.getProperty("java.class.path"));
                for (String a : ManagementFactory.getRuntimeMXBean().getInputArguments())
                    e.println("ARG=" + a);
            }
        }
    }

    static void p(String s) { out.println("TC " + s); out.flush(); }

    static long alloc() { return mx.getThreadAllocatedBytes(Thread.currentThread().getId()); }

    /** Expected arrays allocated for L add() calls: simulation with the library function itself. Returns {capacity, bytesAllocatedByGrows, grows}. */
    static long[] sim(int L)
    {
        byte[] b = new byte[32];
        long sum = 32 + 16;
        long grows = 0;
        for (int pos = 0; pos < L; pos++)
            if (pos == b.length) { b = ArrayUtil.grow(b, pos + 1); sum += b.length + 16; grows++; }
        return new long[]{ b.length, sum, grows };
    }

    static class Built
    {
        TrieTermsDictionaryReader reader;
        java.nio.ByteBuffer image;
        long root;
        ByteComparable key;
        TrieTermsIterator newIter() { return new TrieTermsIterator(new AbstractTrieTestBase.ByteBufRebufferer(image.duplicate()), root); }
    }

    static Built build(int L, long seed) throws Exception
    {
        byte[] k = new byte[L];
        new Random(seed ^ L).nextBytes(k);
        ByteComparable key = ByteComparable.fixedLength(k);
        AbstractTrieTestBase.DataOutputBufferPaged buf = new AbstractTrieTestBase.DataOutputBufferPaged();
        long root;
        try (IncrementalTrieWriter<Long> w = new IncrementalDeepTrieWriterPageAware<>(TrieTermsDictionaryReader.trieSerializer, buf))
        {
            w.add(key, 1L);
            root = w.complete();
        }
        Built b = new Built();
        b.key = key;
        b.reader = new TrieTermsDictionaryReader(new AbstractTrieTestBase.ByteBufRebufferer(buf.asNewBuffer()), root);
        b.image = buf.asNewBuffer();
        b.root = root;
        return b;
    }

    static int[] iterCap(TrieTermsIterator it) throws Exception
    {
        Field f = ValueIterator.class.getDeclaredField("collector");
        f.setAccessible(true);
        TransitionBytesCollector tc = (TransitionBytesCollector) f.get(it);
        Field fb = TransitionBytesCollector.class.getDeclaredField("bytes");
        Field fp = TransitionBytesCollector.class.getDeclaredField("pos");
        fb.setAccessible(true); fp.setAccessible(true);
        return new int[]{ ((byte[]) fb.get(tc)).length, fp.getInt(tc) };
    }

    @Test
    public void grid() throws Exception
    {
        p("start " + java.time.Instant.now());
        // positive control for the allocation instrument: a known array
        for (int L : LENGTHS)
        {
            long best = Long.MAX_VALUE, worst = 0;
            for (int i = 0; i < 200; i++) { byte[] w = new byte[L]; if (w.length < 0) throw new Error(); }
            long a0 = alloc();
            byte[] hold = null;
            for (int i = 0; i < 100; i++) hold = new byte[L];
            long per = (alloc() - a0) / 100;
            p("newarray L=" + L + " per_call=" + per + " expected=" + (L + 16) + " hold=" + hold.length);
        }
        // sizes 131072 standalone (beyond the 65535 key bound): no cap exists at the collector
        for (int L : new int[]{131072, 1 << 20})
        {
            Coll c = new Coll();
            for (int i = 0; i < L; i++) c.add(i);
            long[] s = sim(L);
            p("standalone L=" + L + " cap=" + c.cap() + " pos=" + c.pos() + " sim_cap=" + s[0] + " sim_S=" + s[1] + " grows=" + s[2] + " thr=none");
        }
        Built[] built = new Built[LENGTHS.length];
        for (int li = 0; li < LENGTHS.length; li++) built[li] = build(LENGTHS[li], 7);
        for (String thr : THRESHOLDS)
        {
            DataStorageSpec.LongBytesBound t = new DataStorageSpec.LongBytesBound(thr);
            DatabaseDescriptor.getGuardrailsConfig().setSaiStringTermSizeThreshold(new DataStorageSpec.LongBytesBound("1KiB"), t);
            StringBuilder sb = new StringBuilder();
            for (int sz : PROBE) sb.append(' ').append(sz).append('=').append(Guardrails.saiStringTermSize.failsOn(sz, null) ? "FAIL" : "ok");
            p("guardrail thr=" + thr + " configured_fail=" + DatabaseDescriptor.getGuardrailsConfig().getSaiStringTermSizeFailThreshold() + sb);
            for (int li = 0; li < LENGTHS.length; li++)
            {
                int L = LENGTHS[li];
                Built b = built[li];
                for (int rep = 0; rep < REPS; rep++)
                {
                    // (a) standalone collector, L adds, then L pops
                    Coll c = new Coll();
                    for (int i = 0; i < L; i++) c.add(i);
                    int capFull = c.cap(), posFull = c.pos();
                    for (int i = 0; i < L; i++) c.pop();
                    long[] s = sim(L);
                    p("standalone L=" + L + " cap=" + capFull + " pos=" + posFull + " pos_after_pop=" + c.pos() + " cap_after_pop=" + c.cap()
                      + " sim_cap=" + s[0] + " sim_S=" + s[1] + " grows=" + s[2] + " thr=" + thr + " tag=" + tag + " rep=" + rep);
                    // (b) getMaxTerm / getMinTerm on the one-key trie: thread-allocated bytes, result length
                    for (String which : new String[]{"getMaxTerm", "getMinTerm"})
                    {
                        boolean mx_ = which.equals("getMaxTerm");
                        ByteComparable r = null;
                        for (int i = 0; i < 300; i++) r = mx_ ? b.reader.getMaxTerm() : b.reader.getMinTerm();
                        long a0 = alloc();
                        for (int i = 0; i < 100; i++) r = mx_ ? b.reader.getMaxTerm() : b.reader.getMinTerm();
                        long per = (alloc() - a0) / 100;
                        int cmp = ByteComparable.compare(b.key, r, ByteComparable.Version.OSS50);
                        p("walker call=" + which + " L=" + L + " alloc_per_call=" + per + " result_equals_key=" + (cmp == 0)
                          + " lower=" + (s[1] + L) + " upper=" + (s[1] + L + 65536) + " thr=" + thr + " tag=" + tag + " rep=" + rep);
                    }
                }
                // (c) collecting=true iterator (test class TrieTermsIterator): fresh iterator per L, drained
                TrieTermsIterator it = b.newIter();
                int n = 0, valueLen = -1;
                while (it.hasNext())
                {
                    ByteComparable v = it.next().left;
                    n++;
                    valueLen = org.apache.cassandra.utils.bytecomparable.ByteSourceInverse.readBytes(v.asComparableBytes(ByteComparable.Version.OSS50)).length;
                }
                int[] cp = iterCap(it);
                long[] s = sim(L);
                p("iterator L=" + L + " entries=" + n + " value_len=" + valueLen + " cap=" + cp[0] + " pos_after=" + cp[1] + " sim_cap=" + s[0] + " thr=" + thr + " tag=" + tag);
            }
        }
        p("done " + java.time.Instant.now());
        out.close();
    }
}
