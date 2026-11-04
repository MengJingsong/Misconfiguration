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
 * Stage-4 unit tier (B2) of schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous.
 * Output: lines "STAGE4 ..." appended to the file named by -Dstage4.out. Observation only; the one JUnit assertion at the
 * end fails the test if any known-answer check printed MISMATCH.
 *   check <what> ok|MISMATCH        known-answer checks of the traced path (B2f first sentence)
 *   size  L= N= T= rep= total= per_ks=   reflective walk (B5 item 1) of a list of N KeyspaceMetadata, after 3 x System.gc()
 */
public class NameLengthProbeTest
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

    /** the index in base 36 left-padded with 'k' to exactly L characters (B5 item 2) */
    static String name(int idx, int L)
    {
        String b = Integer.toString(idx, 36);
        if (b.length() > L) throw new IllegalArgumentException("index " + idx + " does not fit " + L + " characters");
        return "k".repeat(L - b.length()) + b;
    }

    static TableMetadata table(String ks, String t)
    {
        return TableMetadata.builder(ks, t).addPartitionKeyColumn("k", Int32Type.instance).addRegularColumn("v", UTF8Type.instance).build();
    }

    static String tryValidate(String ks)
    {
        try
        {
            KeyspaceMetadata.validateKeyspaceName(ks, ConfigurationException::new);
            return "pass";
        }
        catch (ConfigurationException e)
        {
            return "throw:" + e.getMessage();
        }
    }

    @Test
    public void probe() throws Exception
    {
        p("info NAME_LENGTH=" + SchemaConstants.NAME_LENGTH + " TABLE_NAME_LENGTH=" + SchemaConstants.TABLE_NAME_LENGTH
          + " jdk=" + System.getProperty("java.version") + " compactStrings=" + (System.getProperty("java.version").startsWith("1.8") ? "no" : "yes"));
        int[] lens = { 1, 10, 47, 48, 49, 100 };
        // 1. the check: validateKeyspaceName, KeyspaceMetadata.validate(), TableMetadata.validate() (A3 callers)
        for (int L : lens)
        {
            String ks = "k".repeat(L);
            String r = tryValidate(ks);
            p("case validateKeyspaceName L=" + L + " -> " + (r.length() > 120 ? r.substring(0, 120) + "..." : r));
            check("validateKeyspaceName L=" + L + (L <= 48 ? " passes" : " throws ConfigurationException with 'more than 48 characters long'"),
                  L <= 48 ? r.equals("pass") : (r.startsWith("throw:") && r.contains("must not be more than 48 characters long")));
            String r2;
            try
            {
                KeyspaceMetadata.create(ks, KeyspaceParams.simple(1)).validate();
                r2 = "pass";
            }
            catch (ConfigurationException e)
            {
                r2 = "throw:" + e.getMessage();
            }
            p("case KeyspaceMetadata.validate L=" + L + " -> " + (r2.length() > 120 ? r2.substring(0, 120) + "..." : r2));
            check("KeyspaceMetadata.validate L=" + L + (L <= 48 ? " passes" : " throws"), L <= 48 ? r2.equals("pass") : r2.startsWith("throw:"));
            String r3;
            try
            {
                table(ks, "t").validate();
                r3 = "pass";
            }
            catch (ConfigurationException e)
            {
                r3 = "throw:" + e.getMessage();
            }
            p("case TableMetadata.validate(ks L=" + L + ") -> " + (r3.length() > 120 ? r3.substring(0, 120) + "..." : r3));
            check("TableMetadata.validate ks L=" + L + (L <= 48 ? " passes" : " throws"), L <= 48 ? r3.equals("pass") : r3.startsWith("throw:"));
        }
        // 2. retained size per keyspace, L x T, 3 repetitions
        for (int rep = 1; rep <= 3; rep++)
            for (int T : new int[]{ 0, 10 })
                for (int L : lens)
                {
                    int N = L == 1 ? 36 : 1000;
                    List<KeyspaceMetadata> list = new ArrayList<>(N);
                    for (int i = 0; i < N; i++)
                    {
                        String ks = name(i, L);
                        Tables.Builder tb = Tables.builder();
                        for (int t = 0; t < T; t++)
                            tb.add(table(ks, "t" + t));
                        list.add(KeyspaceMetadata.create(ks, KeyspaceParams.simple(1), tb.build()));
                    }
                    for (int g = 0; g < 3; g++) System.gc();
                    long total = walk(list);
                    long jamm = ObjectSizes.measureDeep(list);
                    p("size L=" + L + " N=" + N + " T=" + T + " rep=" + rep + " total=" + total + " jamm_objectsizes=" + jamm + " per_ks=" + String.format("%.2f", total / (double) N));
                    Assert.assertEquals(N, list.size());
                }
        p("summary mismatches=" + mismatches);
        Assert.assertEquals("known-answer checks with MISMATCH", 0, mismatches);
    }
}
