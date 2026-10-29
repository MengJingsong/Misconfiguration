package org.apache.cassandra.schema;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.List;

import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.db.marshal.UTF8Type;
import org.apache.cassandra.exceptions.ConfigurationException;
import org.apache.cassandra.utils.ObjectSizes;

/**
 * Stage-4 unit tier (B2) of table_name_length-validatetablename-name_length--autonomous.
 * Output: lines "STAGE4 ..." appended to the file named by -Dstage4.out.
 *   check <what> ok|MISMATCH          known-answer checks (B2f first sentence)
 *   case  L= validate=... dirlen=     one line per table-name length
 *   size  L= N= extra_cols= rep= total= per_table=   reflective walk (B5 item 1) of a list of N TableMetadata, after 3 x System.gc()
 */
public class TableNameLengthProbeTest
{
    static PrintWriter out;
    static int mismatches = 0;

    @BeforeClass
    public static void setup() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        out = new PrintWriter(new FileWriter(System.getProperty("stage4.out", "/tmp/stage4.out"), true), true);
    }

    @AfterClass
    public static void done()
    {
        out.close();
    }


    // ---- deep sizer (B5 item 1): ObjectSizes.measureDeep stops at @Unmetered TableMetadata/ColumnMetadata ----
    static final org.github.jamm.MemoryMeter METER = org.github.jamm.MemoryMeter.builder().build();

    static long walk(Object root)
    {
        java.util.IdentityHashMap<Object, Boolean> seen = new java.util.IdentityHashMap<>();
        java.util.ArrayDeque<Object> todo = new java.util.ArrayDeque<>();
        todo.push(root);
        long total = 0;
        while (!todo.isEmpty())
        {
            Object o = todo.pop();
            if (o == null || seen.put(o, Boolean.TRUE) != null) continue;
            Class<?> c = o.getClass();
            if (o instanceof Class || o instanceof ClassLoader || o instanceof Thread || o instanceof Enum
                || o instanceof org.apache.cassandra.db.marshal.AbstractType || o instanceof java.lang.ref.Reference)
                continue;
            total += METER.measure(o);
            if (c.isArray())
            {
                if (!c.getComponentType().isPrimitive())
                    for (Object e : (Object[]) o) if (e != null) todo.push(e);
                continue;
            }
            for (Class<?> k = c; k != null && k != Object.class; k = k.getSuperclass())
                for (java.lang.reflect.Field f : k.getDeclaredFields())
                {
                    if (java.lang.reflect.Modifier.isStatic(f.getModifiers()) || f.getType().isPrimitive()) continue;
                    try
                    {
                        f.setAccessible(true);
                        Object v = f.get(o);
                        if (v != null) todo.push(v);
                    }
                    catch (Exception e)
                    {
                        throw new RuntimeException(f.toString(), e);
                    }
                }
        }
        return total;
    }

    static void p(String s)
    {
        out.println("STAGE4 " + s);
    }

    static void check(String what, boolean ok)
    {
        if (!ok) mismatches++;
        p("check " + what + (ok ? " ok" : " MISMATCH"));
    }

    /** the index in base 36 left-padded with 'a' to exactly L characters (B5 item 3) */
    static String name(int idx, int L)
    {
        String b = Integer.toString(idx, 36);
        if (b.length() > L) throw new IllegalArgumentException("index " + idx + " does not fit " + L + " characters");
        return "a".repeat(L - b.length()) + b;
    }

    static TableMetadata table(String t, int extraCols)
    {
        TableMetadata.Builder b = TableMetadata.builder("ks", t).addPartitionKeyColumn("k", Int32Type.instance).addRegularColumn("v", UTF8Type.instance);
        for (int c = 0; c < extraCols; c++)
            b.addRegularColumn("col" + c, UTF8Type.instance);
        return b.build();
    }

    @Test
    public void probe() throws Exception
    {
        boolean ea = false;
        assert ea = true;
        p("info TABLE_NAME_LENGTH=" + SchemaConstants.TABLE_NAME_LENGTH + " NAME_LENGTH=" + SchemaConstants.NAME_LENGTH
          + " FILENAME_LENGTH=" + SchemaConstants.FILENAME_LENGTH + " assertionsEnabled=" + ea + " jdk=" + System.getProperty("java.version"));
        check("assertions are enabled (-ea)", ea);
        int[] lens = { 1, 48, 100, 221, 222, 223, 255 };
        for (int L : lens)
        {
            String n = "a".repeat(L);
            TableMetadata tm = table(n, 0);
            String r;
            try
            {
                tm.validate();
                r = "pass";
            }
            catch (ConfigurationException e)
            {
                r = "throw:" + e.getMessage();
            }
            catch (AssertionError e)
            {
                r = "ASSERT:" + e.getMessage();
            }
            int dirlen = tm.getTableDirectoryName().length();
            p("case L=" + L + " validate=" + (r.length() > 110 ? r.substring(0, 110) + "..." : r) + " dirlen=" + dirlen);
            check("L=" + L + (L <= 222 ? " accepted" : " rejected with 'more than 222 characters long'"),
                  L <= 222 ? r.equals("pass") : (r.startsWith("throw:") && r.contains("Table name must not be more than 222 characters long")));
            if (L == 222)
                check("L=222 directory name length is 255", dirlen == 255);
            if (L == 223 || L == 255)
                check("L=" + L + " not an assertion failure (line 517 fires first)", !r.startsWith("ASSERT:"));
        }
        for (int rep = 1; rep <= 3; rep++)
        {
            for (int[] cfg : new int[][]{ { 1, 0 }, { 2, 0 }, { 48, 0 }, { 100, 0 }, { 221, 0 }, { 222, 0 }, { 48, 50 } })
            {
                int L = cfg[0], extra = cfg[1];
                int N = L == 1 ? 36 : 1000;
                List<TableMetadata> list = new ArrayList<>(N);
                for (int i = 0; i < N; i++)
                    list.add(table(name(i, L), extra));
                for (int g = 0; g < 3; g++) System.gc();
                long total = walk(list);
                    long jamm = ObjectSizes.measureDeep(list);
                p("size L=" + L + " N=" + N + " extra_cols=" + extra + " rep=" + rep + " total=" + total + " jamm_objectsizes=" + jamm + " per_table=" + String.format("%.2f", total / (double) N));
                Assert.assertEquals(N, list.size());
            }
        }
        p("summary mismatches=" + mismatches);
        Assert.assertEquals("known-answer checks with MISMATCH", 0, mismatches);
    }
}
