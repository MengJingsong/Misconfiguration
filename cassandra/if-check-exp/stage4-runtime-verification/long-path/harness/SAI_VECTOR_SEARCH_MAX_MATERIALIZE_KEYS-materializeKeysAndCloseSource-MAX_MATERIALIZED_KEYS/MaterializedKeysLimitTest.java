/*
 * Stage-4 harness, unit tier of SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS (case file
 * section 9, 9e unit steps U1-U5, amended 2026-10-15). Not part of upstream Cassandra. Copy into
 * test/unit/org/apache/cassandra/index/sai/cql/ of a local clone at cassandra-5.0.9 and run with unit-trace.btm loaded by -javaagent
 * (unit-run.sh). System property stage4.out: a file that also receives the STAGE4 lines.
 *
 * The rules of unit-trace.btm call rec() with the same lines mat-trace.btm writes on a node (mat refuse / mat exit / ann / hybrid /
 * pairs / processed) and, at the refusal, measure() with the list itself. Each query clears the recorder first, so the lines a
 * check reads are that query's. Every assertion is a STAGE4 check line; a mismatch is recorded and the test goes on, and fails at
 * the end. QueryController.MAX_MATERIALIZED_KEYS is written before each query and restored in finally, as
 * VectorTypeTest.testTooManyMaterializedKeys does. Extends CQLTester, not SAITester: SAITester's ResourceLeakDetector attaches its own
 * Byteman agent (Injections.loadAgent), which fails in a JVM that already has unit-trace.btm's agent (shakedown 1, 2026-10-15).
 */
package org.apache.cassandra.index.sai.cql;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Random;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.junit.Assert;
import org.junit.Test;

import org.apache.cassandra.cql3.UntypedResultSet;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.index.sai.plan.QueryController;
import org.apache.cassandra.utils.ObjectSizes;

public class MaterializedKeysLimitTest extends CQLTester
{
    private static final List<String> LINES = Collections.synchronizedList(new ArrayList<>());
    private static final List<Long> DEEP = Collections.synchronizedList(new ArrayList<>());

    private PrintWriter out;
    private int checks, mismatches;

    /** Called by unit-trace.btm. */
    public static void rec(String line)
    {
        LINES.add(line);
    }

    /** Called by unit-trace.btm at the refusal with the list of L + 1 keys. */
    public static void measure(List<?> keys)
    {
        DEEP.add(ObjectSizes.measureDeep(keys));
    }

    private void say(String s)
    {
        System.out.println(s);
        if (out != null)
        {
            out.println(s);
            out.flush();
        }
    }

    private boolean check(String what, boolean ok, String detail)
    {
        checks++;
        if (!ok)
            mismatches++;
        say("STAGE4 check " + what + " " + detail + " " + (ok ? "ok" : "MISMATCH"));
        return ok;
    }

    private static int count(List<String> lines, String prefix)
    {
        int n = 0;
        for (String l : lines)
            if (l.startsWith(prefix))
                n++;
        return n;
    }

    private static String first(List<String> lines, String prefix)
    {
        for (String l : lines)
            if (l.startsWith(prefix))
                return l;
        return null;
    }

    private static long field(String line, String name)
    {
        if (line == null)
            return Long.MIN_VALUE;
        Matcher m = Pattern.compile("\\b" + name + "=(-?\\d+)").matcher(line);
        return m.find() ? Long.parseLong(m.group(1)) : Long.MIN_VALUE;
    }

    private static String vec(float[] v)
    {
        StringBuilder b = new StringBuilder("[");
        for (int i = 0; i < v.length; i++)
            b.append(i == 0 ? "" : ", ").append(v[i]);
        return b.append(']').toString();
    }

    private static float[] gaussian(Random r, int d)
    {
        float[] v = new float[d];
        for (int i = 0; i < d; i++)
            v[i] = (float) r.nextGaussian();
        return v;
    }

    private static double cosine(float[] a, float[] b)
    {
        double ab = 0, aa = 0, bb = 0;
        for (int i = 0; i < a.length; i++)
        {
            ab += a[i] * b[i];
            aa += a[i] * a[i];
            bb += b[i] * b[i];
        }
        return ab / Math.sqrt(aa * bb);
    }

    private String newTable(int dim)
    {
        String t = createTable("CREATE TABLE %s (pk int PRIMARY KEY, i int, val vector<float, " + dim + ">)");
        disableCompaction();
        createIndex("CREATE CUSTOM INDEX ON %s(val) USING 'StorageAttachedIndex'");
        createIndex("CREATE CUSTOM INDEX ON %s(i) USING 'StorageAttachedIndex'");
        waitForTableIndexesQueryable();
        return t;
    }

    /** rows pk = i = order[k], vectors from vecs[pk - 1]; flushes after every flushEvery rows (0: never). */
    private void load(int[] order, float[][] vecs, int flushEvery) throws Throwable
    {
        int n = 0;
        for (int pk : order)
        {
            execute("INSERT INTO %s (pk, i, val) VALUES (?, ?, ?)", pk, pk, vector(vecs[pk - 1]));
            if (flushEvery > 0 && ++n % flushEvery == 0)
                flush();
        }
    }

    private static int[] shuffled(int n, long seed)
    {
        List<Integer> l = new ArrayList<>();
        for (int i = 1; i <= n; i++)
            l.add(i);
        Collections.shuffle(l, new Random(seed));
        int[] a = new int[n];
        for (int i = 0; i < n; i++)
            a[i] = l.get(i);
        return a;
    }

    /** runs the hybrid query at limit L and returns the recorder's lines; rows checked against M */
    private List<String> query(String tag, int L, int M, int k, float[] q)
    {
        int saved = QueryController.MAX_MATERIALIZED_KEYS;
        QueryController.MAX_MATERIALIZED_KEYS = L;
        LINES.clear();
        DEEP.clear();
        UntypedResultSet rows;
        try
        {
            rows = execute("SELECT pk, i FROM %s WHERE i <= ? ORDER BY val ANN OF " + vec(q) + " LIMIT " + k, M);
        }
        catch (Throwable t)
        {
            check(tag + " query", false, "threw " + t);
            return new ArrayList<>(LINES);
        }
        finally
        {
            QueryController.MAX_MATERIALIZED_KEYS = saved;
        }
        List<String> lines = new ArrayList<>(LINES);
        int n = 0, bad = 0;
        for (UntypedResultSet.Row r : rows)
        {
            n++;
            if (r.getInt("i") > M)
                bad++;
        }
        check(tag + " rows", n == k && bad == 0, "rows=" + n + " i>M=" + bad + " (want " + k + ", 0)");
        check(tag + " one mat exit", count(lines, "mat exit") == 1, "mat-exit-lines=" + count(lines, "mat exit"));
        for (String l : lines)
            say("STAGE4 line " + tag + " " + l);
        return lines;
    }

    /** the boundary outcome of U1: allowed below or at L, refused at L + 1 */
    private void outcome(String tag, List<String> lines, int L, int M)
    {
        String refuse = first(lines, "mat refuse");
        String exit = first(lines, "mat exit");
        String hybrid = first(lines, "hybrid");
        int ann = count(lines, "ann");
        if (M <= L)
        {
            check(tag + " allow", refuse == null && exit != null && exit.contains("returned=" + M) && hybrid != null
                                  && field(hybrid, "size") == M && ann == 0 && count(lines, "hybrid") == 1,
                  "refuse=" + refuse + " exit=" + exit + " hybrid=" + hybrid + " ann=" + ann);
        }
        else
        {
            long want = (long) L + 1 <= 0 ? 1 : (long) L + 1;
            check(tag + " refuse", refuse != null && field(refuse, "size") == want && field(refuse, "count") == want
                                   && count(lines, "mat refuse") == 1 && exit != null && exit.contains("returned=null")
                                   && ann == 1 && hybrid == null,
                  "refuse=" + refuse + " exit=" + exit + " hybrid=" + hybrid + " ann=" + ann + " (want size=count=" + want + ")");
        }
    }

    @Test
    public void materializedKeysLimit() throws Throwable
    {
        String path = System.getProperty("stage4.out");
        if (path != null)
            out = new PrintWriter(new FileWriter(path, true));
        say("STAGE4 start limit-at-start=" + QueryController.MAX_MATERIALIZED_KEYS);
        try
        {
            u1();
            u2u3();
            u4();
            u5();
        }
        finally
        {
            say("STAGE4 summary checks=" + checks + " mismatches=" + mismatches);
            if (out != null)
                out.close();
        }
        Assert.assertEquals("STAGE4 mismatches", 0, mismatches);
    }

    /** U1, the boundary, flushed (one SSTable) and again on a memtable at L = 100 */
    private void u1() throws Throwable
    {
        int n = 4010;
        Random r = new Random(9001);
        float[][] vecs = new float[n][];
        for (int i = 0; i < n; i++)
            vecs[i] = gaussian(r, 2);
        float[] q = gaussian(new Random(9002), 2);
        newTable(2);
        load(shuffled(n, 9003), vecs, 0);
        flush();
        for (int L : new int[]{ 10, 100, 1000 })
            for (int M : new int[]{ L - 1, L, L + 1, 4 * L })
            {
                String tag = "U1 sstable L=" + L + " M=" + M;
                outcome(tag, query(tag, L, M, 3, q), L, M);
            }
        newTable(2);
        load(shuffled(n, 9004), vecs, 0);
        int L = 100;
        for (int M : new int[]{ L - 1, L, L + 1, 4 * L })
        {
            String tag = "U1 memtable L=" + L + " M=" + M;
            outcome(tag, query(tag, L, M, 3, q), L, M);
        }
    }

    /** U2, heap per key (measureDeep of the list at the refusal); U3, the escape values on the same table */
    private void u2u3() throws Throwable
    {
        int n = 16010;
        Random r = new Random(9011);
        float[][] vecs = new float[n][];
        for (int i = 0; i < n; i++)
            vecs[i] = gaussian(r, 2);
        float[] q = gaussian(new Random(9012), 2);
        newTable(2);
        load(shuffled(n, 9013), vecs, 0);
        flush();
        int[] ls = { 100, 1000, 4000 };
        long[] deep = new long[ls.length];
        for (int j = 0; j < ls.length; j++)
        {
            int L = ls[j];
            String tag = "U2 L=" + L + " M=" + 4 * L;
            List<String> lines = query(tag, L, 4 * L, 3, q);
            outcome(tag, lines, L, 4 * L);
            List<Long> d = new ArrayList<>(DEEP);
            check(tag + " one measurement", d.size() == 1, "measurements=" + d);
            deep[j] = d.isEmpty() ? -1 : d.get(0);
            say("STAGE4 deep L=" + L + " keys=" + (L + 1) + " bytes=" + deep[j]);
        }
        double[] b = new double[3];
        int[][] pairs = { { 0, 1 }, { 1, 2 }, { 0, 2 } };
        for (int p = 0; p < 3; p++)
        {
            int x = pairs[p][0], y = pairs[p][1];
            b[p] = (double) (deep[y] - deep[x]) / (ls[y] - ls[x]);
            check("U2 slope " + ls[x] + "-" + ls[y], b[p] >= 120 && b[p] <= 200, String.format("b=%.2f B/key (want 120..200)", b[p]));
        }
        double lo = Math.min(b[0], Math.min(b[1], b[2])), hi = Math.max(b[0], Math.max(b[1], b[2]));
        check("U2 slopes within 2%", hi <= lo * 1.02, String.format("min=%.2f max=%.2f ratio=%.4f", lo, hi, hi / lo));

        String tag = "U3 L=0 M=5";
        List<String> lines = query(tag, 0, 5, 3, q);
        outcome(tag, lines, 0, 5);
        tag = "U3 L=MAX M=16000";
        lines = query(tag, Integer.MAX_VALUE, 16000, 3, q);
        outcome(tag, lines, Integer.MAX_VALUE, 16000);
    }

    /** U4, per-segment arrays: four SSTables of shuffled keys, L = M = 4,000 */
    private void u4() throws Throwable
    {
        int n = 16000;
        Random r = new Random(9021);
        float[][] vecs = new float[n][];
        for (int i = 0; i < n; i++)
            vecs[i] = gaussian(r, 2);
        float[] q = gaussian(new Random(9022), 2);
        newTable(2);
        load(shuffled(n, 9023), vecs, 4000);
        int sstables = getCurrentColumnFamilyStore().getLiveSSTables().size();
        check("U4 sstables", sstables == 4, "live-sstables=" + sstables);
        String tag = "U4 L=4000 M=4000";
        List<String> lines = query(tag, 4000, 4000, 3, q);
        outcome(tag, lines, 4000, 4000);
        List<Long> caps = new ArrayList<>();
        for (String l : lines)
            if (l.startsWith("pairs"))
                caps.add(field(l, "cap"));
        boolean ok = caps.size() == 4;
        for (long c : caps)
            ok &= c >= 3950;
        check(tag + " pairs", ok, "caps=" + caps + " (want 4, each >= 3950)");
    }

    /** U5, the disallow plan's retention: matches are the 101 rows least similar to q */
    private void u5() throws Throwable
    {
        int n = 2000, dim = 8;
        Random r = new Random(9031);
        float[] q = gaussian(new Random(9032), dim);
        List<float[]> drawn = new ArrayList<>();
        for (int i = 0; i < n; i++)
            drawn.add(gaussian(r, dim));
        drawn.sort((a, b) -> Double.compare(cosine(a, q), cosine(b, q)));   // ascending: index 0 = least similar = i 1
        float[][] vecs = drawn.toArray(new float[0][]);
        newTable(dim);
        load(shuffled(n, 9033), vecs, 0);
        flush();
        String tag = "U5 L=100 M=101";
        List<String> lines = query(tag, 100, 101, 3, q);
        outcome(tag, lines, 100, 101);
        String p = first(lines, "processed=");
        check(tag + " processed", field(p, "processed") >= 1709, "line=" + p + " (want processed >= 1709)");
        tag = "U5 L=1000 M=101";
        lines = query(tag, 1000, 101, 3, q);
        outcome(tag, lines, 1000, 101);
        p = first(lines, "processed=");
        check(tag + " processed", field(p, "processed") <= 10 && field(p, "processed") >= 0, "line=" + p + " (want processed <= 10)");
    }
}
