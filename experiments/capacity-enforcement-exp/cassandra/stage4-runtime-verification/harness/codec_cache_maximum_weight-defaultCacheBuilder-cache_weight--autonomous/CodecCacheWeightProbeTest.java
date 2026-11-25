package org.apache.cassandra.cql3.functions.types;

// Stage-4 harness for order 96 (codec_cache_maximum_weight-defaultCacheBuilder-cache_weight--autonomous).
// The B2a skeleton verbatim, plus @SuppressWarnings("unchecked") on the class (compile hygiene only).

import java.lang.reflect.*;
import java.util.*;
import com.google.common.cache.*;
import org.junit.Test;
import org.apache.cassandra.transport.ProtocolVersion;
import org.apache.cassandra.utils.ObjectSizes;

@SuppressWarnings("unchecked")
public class CodecCacheWeightProbeTest
{
    static LoadingCache<Object, TypeCodec<?>> cache(CodecRegistry r) throws Exception
    { Field f = CodecRegistry.class.getDeclaredField("cache"); f.setAccessible(true); return (LoadingCache<Object, TypeCodec<?>>) f.get(r); }

    static long weightSum(CodecRegistry r) throws Exception
    {
        Class<?> wc = Class.forName("org.apache.cassandra.cql3.functions.types.CodecRegistry$TypeCodecWeigher");
        Constructor<?> k = wc.getDeclaredConstructor(CodecRegistry.class); k.setAccessible(true);
        Weigher<Object, TypeCodec<?>> w = (Weigher<Object, TypeCodec<?>>) k.newInstance(r);
        long s = 0; for (Map.Entry<Object, TypeCodec<?>> e : cache(r).asMap().entrySet()) s += w.weigh(e.getKey(), e.getValue());
        return s;
    }

    static void report(String tag, CodecRegistry r) throws Exception
    {
        LoadingCache<Object, TypeCodec<?>> c = cache(r); c.cleanUp();
        System.gc(); Thread.sleep(200);
        long used = Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory();
        System.out.printf("PROBE %s size=%d weight=%d deepBytes=%d heapUsed=%d%n",
                          tag, c.size(), weightSum(r), ObjectSizes.measureDeep(r), used);
    }

    static DataType[] wideTuple(int m, int d)            // weight 1 for any m
    {
        DataType[] t = new DataType[m + 1];
        Arrays.fill(t, 0, m, DataType.cint());
        t[m] = DataType.vector(DataType.cint(), d);       // makes each key distinct; weighs 1 at level 1
        return t;
    }

    @Test public void narrow() throws Exception        // W-A
    {
        int k = Integer.getInteger("probe.k", 2000);
        CodecRegistry r = new CodecRegistry();
        report("A-empty", r);
        for (int d = 1; d <= k; d++) r.codecFor(DataType.vector(DataType.cint(), d));
        report("A-k" + k, r);
    }

    static final DataType[] PRIMS = { DataType.ascii(), DataType.bigint(), DataType.blob(), DataType.cboolean(),
        DataType.counter(), DataType.decimal(), DataType.cdouble(), DataType.cfloat(), DataType.inet(), DataType.cint(),
        DataType.text(), DataType.timestamp(), DataType.uuid(), DataType.varint(), DataType.timeuuid(),
        DataType.smallint(), DataType.tinyint(), DataType.date(), DataType.time(), DataType.duration() };   // 20

    @Test public void zeroWeight() throws Exception    // W-B
    {
        CodecRegistry r = new CodecRegistry();
        for (DataType a : PRIMS)
        {
            r.codecFor(DataType.list(a)); r.codecFor(DataType.set(a));
            for (DataType b : PRIMS) r.codecFor(DataType.map(a, b));
        }
        report("B-zero-only", r);
        for (int d = 1; d <= 5000; d++) r.codecFor(DataType.vector(DataType.cint(), d));
        report("B-zero-plus-5000-vectors", r);
        DataType li = DataType.list(DataType.cint());
        System.out.println("PROBE B list<int> still cached: "
                           + cache(r).asMap().values().stream().anyMatch(c -> c.getCqlType().equals(li)));
    }

    @Test public void wide() throws Exception          // W-C
    {
        int m = Integer.getInteger("probe.m", 1000), k = Integer.getInteger("probe.k", 2000);
        CodecRegistry r = new CodecRegistry();
        report("C-empty-m" + m, r);
        for (int d = 1; d <= k; d++) r.codecFor(TupleType.of(ProtocolVersion.CURRENT, r, wideTuple(m, d)));
        report("C-m" + m + "-k" + k, r);
    }
}
