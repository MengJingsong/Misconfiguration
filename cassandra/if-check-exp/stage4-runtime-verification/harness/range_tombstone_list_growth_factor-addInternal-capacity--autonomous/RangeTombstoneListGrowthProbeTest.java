package org.apache.cassandra.db;

import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;

import org.junit.AfterClass;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.utils.ByteBufferUtil;
import org.apache.cassandra.utils.ObjectSizes;

/**
 * Unit tier (B2) of range_tombstone_list_growth_factor-addInternal-capacity--autonomous (harness for the autonomous case file).
 * One probe class for the three sibling case files; CASE selects the grid of that file's B2b/B2c:
 *   A = addInternal-capacity (B2: f in {1.2,1.5,2.0,5.0,1.0,0.5}, s in {0,1,1024}, N in {1k,10k,100k}, sorted + random order, copy(), 3 repeats)
 *   G = growToFree-newLength (B2: f in {1.2,1.5,2.0,5.0}, n0 in {0,1,1024}, N in {10,1000,100k}, N+1 add, addAll, LinkedHashMap control)
 *   N = grow-newLength       (B2: f in {1.2,1.5,2.0,5.0,1.0,0.5,100}, c in {1,1024}, n in {1,10,1000,100k}, copy()+add x1000, addAll, c>n control)
 * Writes one "RTL ..." line per run to build/test/rtl-unit-A.txt (and stdout). The analyzer (unit-analyze.py) reads that file.
 * Capacity is read by reflection on the private arrays; unsharedHeapSize() is the check's own accounting, ObjectSizes.measureDeep
 * (Jamm) minus the same measure of an empty list with the same comparator is the independent size.
 */
public class RangeTombstoneListGrowthProbeTest
{
    static final String CASE = "A";
    static final ClusteringComparator cmp = new ClusteringComparator(Int32Type.instance);
    static final long DEL_TIME = 1_000_000L;
    static PrintWriter out;
    static double origF;
    static int origS;
    static Field fStarts, fEnds, fMarked, fDel, fBoundary;
    static long emptyDeep;

    @BeforeClass
    public static void beforeClass() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        origF = DatabaseDescriptor.getRangeTombstoneListGrowthFactor();
        origS = DatabaseDescriptor.getInitialRangeTombstoneListAllocationSize();
        fStarts = fld("starts"); fEnds = fld("ends"); fMarked = fld("markedAts"); fDel = fld("delTimesUnsignedIntegers");
        fBoundary = fld("boundaryHeapSize");
        java.io.File d = new java.io.File("build/test");
        d.mkdirs();
        out = new PrintWriter(new java.io.FileWriter("build/test/rtl-unit-" + CASE + ".txt", false), true);
        emit("HEADER case=" + CASE + " java=" + System.getProperty("java.version") + " maxHeap=" + Runtime.getRuntime().maxMemory()
             + " origF=" + origF + " origS=" + origS + " compressedOops=" + System.getProperty("sun.arch.data.model"));
        emptyDeep = ObjectSizes.measureDeep(new RangeTombstoneList(cmp, 0));
    }

    @AfterClass
    public static void afterClass()
    {
        DatabaseDescriptor.setRangeTombstoneListGrowthFactor(origF);
        DatabaseDescriptor.setInitialRangeTombstoneListAllocationSize(origS);
        emit("RESTORED f=" + DatabaseDescriptor.getRangeTombstoneListGrowthFactor() + " s=" + DatabaseDescriptor.getInitialRangeTombstoneListAllocationSize());
        out.close();
    }

    static Field fld(String n) throws Exception
    {
        Field f = RangeTombstoneList.class.getDeclaredField(n);
        f.setAccessible(true);
        return f;
    }

    static synchronized void emit(String s)
    {
        System.out.println(s);
        out.println(s);
    }

    static ByteBuffer bb(int i) { return ByteBufferUtil.bytes(i); }

    static RangeTombstone rt(int i)
    {
        return new RangeTombstone(Slice.make(BufferClusteringBound.inclusiveStartOf(bb(2 * i)), BufferClusteringBound.inclusiveEndOf(bb(2 * i + 1))),
                                  DeletionTime.build(1L, DEL_TIME));
    }

    static int cap(RangeTombstoneList l) throws Exception { return ((Object[]) fStarts.get(l)).length; }

    static String lens(RangeTombstoneList l) throws Exception
    {
        return ((Object[]) fStarts.get(l)).length + "/" + ((Object[]) fEnds.get(l)).length + "/" + ((long[]) fMarked.get(l)).length + "/" + ((int[]) fDel.get(l)).length;
    }

    static long arrays(RangeTombstoneList l) throws Exception
    {
        return ObjectSizes.sizeOfArray((Object[]) fStarts.get(l)) + ObjectSizes.sizeOfArray((Object[]) fEnds.get(l))
               + ObjectSizes.sizeOfArray((long[]) fMarked.get(l)) + ObjectSizes.sizeOfArray((int[]) fDel.get(l));
    }

    static long trueBounds(RangeTombstoneList l) throws Exception
    {
        ClusteringBound<?>[] s = (ClusteringBound<?>[]) fStarts.get(l), e = (ClusteringBound<?>[]) fEnds.get(l);
        long t = 0;
        for (int i = 0; i < l.size(); i++)
            t += s[i].unsharedHeapSize() + e[i].unsharedHeapSize();
        return t;
    }

    static long deep(RangeTombstoneList l) { return ObjectSizes.measureDeep(l) - emptyDeep; }

    /** Adds the tombstones in the given order; returns the growth series "size:cap,..." (size after the add that grew it). */
    static String build(RangeTombstoneList l, int[] order, StringBuilder events) throws Exception
    {
        StringBuilder series = new StringBuilder();
        int prev = cap(l), ev = 0;
        for (int k = 0; k < order.length; k++)
        {
            l.add(rt(order[k]));
            int c = cap(l);
            if (c != prev)
            {
                ev++;
                if (ev <= 80)
                    series.append(l.size()).append(':').append(c).append(',');
                prev = c;
            }
        }
        events.append(ev);
        return series.toString();
    }

    static int[] sorted(int n) { int[] a = new int[n]; for (int i = 0; i < n; i++) a[i] = i; return a; }

    static int[] shuffled(int n, long seed)
    {
        List<Integer> l = new ArrayList<>();
        for (int i = 0; i < n; i++) l.add(i);
        Collections.shuffle(l, new Random(seed));
        int[] a = new int[n];
        for (int i = 0; i < n; i++) a[i] = l.get(i);
        return a;
    }

    static void setKnobs(double f, int s)
    {
        DatabaseDescriptor.setRangeTombstoneListGrowthFactor(f);
        DatabaseDescriptor.setInitialRangeTombstoneListAllocationSize(s);
    }

    /** One run: build N tombstones (sorted or random order), record everything, then copy() it. */
    static String run(String kind, double f, int s, int n, int[] order, boolean withDeep, int rep) throws Exception
    {
        setKnobs(f, s);
        RangeTombstoneList l = new RangeTombstoneList(cmp, s);
        StringBuilder ev = new StringBuilder();
        String series = build(l, order, ev);
        long bnd = (Long) fBoundary.get(l);
        String line = "RTL kind=" + kind + " f=" + f + " s=" + s + " N=" + n + " rep=" + rep + " size=" + l.size() + " lens=" + lens(l)
                      + " events=" + ev + " unshared=" + l.unsharedHeapSize() + " arrays=" + arrays(l) + " boundary=" + bnd
                      + " trueBounds=" + trueBounds(l) + " empty=" + new RangeTombstoneList(cmp, 0).unsharedHeapSize()
                      + (withDeep ? " deep=" + deep(l) : "") + " series=" + series;
        emit(line);
        RangeTombstoneList c = l.copy();
        emit("RTL kind=" + kind + "-copy f=" + f + " s=" + s + " N=" + n + " rep=" + rep + " size=" + c.size() + " lens=" + lens(c)
             + " unshared=" + c.unsharedHeapSize() + " arrays=" + arrays(c) + " boundary=" + (Long) fBoundary.get(c)
             + (withDeep ? " deep=" + deep(c) : ""));
        return line.substring(line.indexOf("size="), line.indexOf(" unshared=")) + line.substring(line.indexOf(" unshared="), line.indexOf(" arrays="));
    }

    @Test
    public void probe() throws Exception
    {
        try
        {
            if (CASE.equals("A")) caseA();
            else if (CASE.equals("G")) caseG();
            else caseN();
        }
        finally
        {
            DatabaseDescriptor.setRangeTombstoneListGrowthFactor(origF);
            DatabaseDescriptor.setInitialRangeTombstoneListAllocationSize(origS);
        }
    }

    // ---- addInternal-capacity (B2b/B2c/B2e of that file) ----
    void caseA() throws Exception
    {
        double[] fs = { 1.2, 1.5, 2.0, 5.0, 1.0, 0.5 };
        int[] ss = { 0, 1, 1024 };
        int[] ns = { 1_000, 10_000, 100_000 };
        boolean allIdentical = true;
        for (double f : fs)
            for (int s : ss)
                for (int n : ns)
                {
                    String first = null;
                    for (int rep = 1; rep <= 3; rep++)
                    {
                        String k = run("sorted", f, s, n, sorted(n), rep == 1, rep);
                        if (first == null) first = k; else allIdentical &= first.equals(k);
                    }
                    String rfirst = null;
                    for (int rep = 1; rep <= 3; rep++)
                    {
                        String k = run("random", f, s, n, shuffled(n, 42), rep == 1, rep);
                        if (rfirst == null) rfirst = k; else allIdentical &= rfirst.equals(k);
                    }
                }
        emit("RTL kind=repeat-identical value=" + allIdentical);
    }

    // ---- growToFree-newLength ----
    void caseG() throws Exception
    {
        double[] fs = { 1.2, 1.5, 2.0, 5.0 };
        int[] n0s = { 0, 1, 1024 };
        int[] ns = { 10, 1_000, 100_000 };
        for (double f : fs)
            for (int n0 : n0s)
                for (int n : ns)
                {
                    run("sorted", f, n0, n, sorted(n), true, 1);
                    // B2e step 3: N+1 more adds after the last growth are accepted (no rejection)
                    setKnobs(f, n0);
                    RangeTombstoneList l = new RangeTombstoneList(cmp, n0);
                    for (int i = 0; i < n; i++) l.add(rt(i));
                    int before = l.size();
                    boolean ok = true; String err = "";
                    try { l.add(rt(n)); } catch (Throwable t) { ok = false; err = t.toString(); }
                    emit("RTL kind=plusone f=" + f + " s=" + n0 + " N=" + n + " before=" + before + " after=" + l.size() + " accepted=" + ok + " err=" + err);
                }
        // B2e step 4: addAll bypass (into an empty list, for each f and n0), compare capacity with src.size
        for (double f : fs)
            for (int n0 : n0s)
            {
                setKnobs(1.5, 1);
                RangeTombstoneList src = new RangeTombstoneList(cmp, 1);
                for (int i = 0; i < 1000; i++) src.add(rt(i));
                setKnobs(f, n0);
                RangeTombstoneList dst = new RangeTombstoneList(cmp, n0);
                dst.addAll(src);
                emit("RTL kind=addAll f=" + f + " s=" + n0 + " srcSize=" + src.size() + " srcLens=" + lens(src) + " dstSize=" + dst.size() + " dstLens=" + lens(dst));
            }
        // B2e step 5: positive control, a structure with a known bound: LinkedHashMap with removeEldestEntry at M entries
        final int M = 1000;
        Map<Integer, Integer> bounded = new LinkedHashMap<Integer, Integer>(16, 0.75f, false)
        {
            protected boolean removeEldestEntry(Map.Entry<Integer, Integer> e) { return size() > M; }
        };
        setKnobs(1.5, 1);
        RangeTombstoneList l = new RangeTombstoneList(cmp, 1);
        for (int i = 0; i < 100_000; i++)
        {
            bounded.put(i, i);
            l.add(rt(i));
            if (i == 999 || i == 9_999 || i == 99_999)
                emit("RTL kind=control adds=" + (i + 1) + " boundedMapSize=" + bounded.size() + " listSize=" + l.size() + " listUnshared=" + l.unsharedHeapSize());
        }
    }

    // ---- grow-newLength ----
    void caseN() throws Exception
    {
        double[] fs = { 1.2, 1.5, 2.0, 5.0, 1.0, 0.5, 100.0 };
        int[] cs = { 1, 1024 };
        int[] ns = { 1, 10, 1_000, 100_000 };
        // the setter takes any value (no validation at the DatabaseDescriptor level)
        for (double f : new double[] { 100.0, 0.5, 1.0 })
        {
            String err = "none";
            try { DatabaseDescriptor.setRangeTombstoneListGrowthFactor(f); } catch (Throwable t) { err = t.toString(); }
            emit("RTL kind=setter f=" + f + " readback=" + DatabaseDescriptor.getRangeTombstoneListGrowthFactor() + " error=" + err);
        }
        DatabaseDescriptor.setRangeTombstoneListGrowthFactor(origF);
        for (double f : fs)
            for (int c : cs)
                for (int n : ns)
                {
                    String first = null; boolean same = true;
                    for (int rep = 1; rep <= 2; rep++)
                    {
                        String k = run("sorted", f, c, n, sorted(n), rep == 1, rep);
                        if (first == null) first = k; else same &= first.equals(k);
                    }
                    emit("RTL kind=sorted-repeat f=" + f + " s=" + c + " N=" + n + " identical=" + same);
                }
        // second shape: copy() then add one more, 1000 times (models BTreePartitionUpdater.merge)
        for (double f : new double[] { 1.2, 1.5, 2.0, 5.0 })
            for (int c : cs)
            {
                setKnobs(f, c);
                RangeTombstoneList l = new RangeTombstoneList(cmp, c);
                for (int i = 0; i < 1000; i++) l.add(rt(i));
                StringBuilder sb = new StringBuilder();
                for (int it = 0; it < 1000; it++)
                {
                    l = l.copy();
                    int sizeBefore = l.size(), capBefore = cap(l);
                    l.add(rt(1000 + it));
                    sb.append(sizeBefore).append(':').append(capBefore).append(':').append(cap(l)).append(',');
                }
                emit("RTL kind=copyadd f=" + f + " s=" + c + " m=1000 iters=1000 unshared=" + l.unsharedHeapSize() + " triples=" + sb);
            }
        // third shape: addAll into an empty list (the target line 696 path), n = 1000
        for (double f : fs)
            for (int c : cs)
            {
                setKnobs(1.5, 1);
                RangeTombstoneList src = new RangeTombstoneList(cmp, 1);
                for (int i = 0; i < 1000; i++) src.add(rt(i));
                setKnobs(f, c);
                RangeTombstoneList dst = new RangeTombstoneList(cmp, c);
                dst.addAll(src);
                emit("RTL kind=addAll f=" + f + " s=" + c + " srcSize=" + src.size() + " srcLens=" + lens(src) + " dstSize=" + dst.size() + " dstLens=" + lens(dst));
            }
        // positive control: c large, n < c never calls growToFree; capacity stays c whatever f is
        for (double f : new double[] { 1.2, 1.5, 2.0, 5.0 })
        {
            setKnobs(f, 1024);
            RangeTombstoneList l = new RangeTombstoneList(cmp, 1024);
            for (int i = 0; i < 1000; i++) l.add(rt(i));
            emit("RTL kind=control f=" + f + " s=1024 n=1000 size=" + l.size() + " lens=" + lens(l));
        }
    }
}
