/*
 * Stage-4 harness, unit tier (B2, amendments U1-U4 of 2026-10-27) of
 * ExecuteMessage_literal_1000-traceQuery-1000--autonomous. Copied into test/unit/org/apache/cassandra/cql3/ of the run clone
 * by unit-run.sh and removed afterwards. Prints PROBE / MULTI / TRACEFAIL / END lines; asserts nothing.
 */
package org.apache.cassandra.cql3;

import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Random;

import org.junit.AfterClass;
import org.junit.BeforeClass;
import org.junit.Test;

import com.datastax.driver.core.PreparedStatement;
import com.datastax.driver.core.QueryTrace;
import com.datastax.driver.core.Session;
import com.datastax.driver.core.SimpleStatement;
import org.apache.cassandra.db.marshal.UTF8Type;
import org.apache.cassandra.tracing.TraceStateImpl;
import org.apache.cassandra.utils.ByteBufferUtil;

public class TraceBoundValueTruncationProbeTest extends CQLTester
{
    static int DEFAULT_WAIT;
    static final String ALNUM = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";

    @BeforeClass
    public static void setUpWait()
    {
        DEFAULT_WAIT = TraceStateImpl.WAIT_FOR_PENDING_EVENTS_TIMEOUT_SECS;
        TraceStateImpl.WAIT_FOR_PENDING_EVENTS_TIMEOUT_SECS = 5;
    }

    @AfterClass
    public static void tearDownWait()
    {
        TraceStateImpl.WAIT_FOR_PENDING_EVENTS_TIMEOUT_SECS = DEFAULT_WAIT;
    }

    static String expectedStored(String full)
    {
        return full.length() > 1000 ? full.substring(0, 1000) + "...'" : full;
    }

    static byte[] blob(int s)
    {
        byte[] b = new byte[s];
        new Random(42).nextBytes(b);
        return b;
    }

    String tbl;
    // shakedown (not a reading): -Demt.shake=1 via -Dtest.jvm.args runs other, smaller values
    static final boolean SHAKE = System.getProperty("emt.shake") != null;
    static final int MB = SHAKE ? 700 : 65536;

    /** returns L (or -1) and prints one line */
    long report(String kind, int s, long k, String key, QueryTrace tr, String full, String expected, long[] mOut)
    {
        try
        {
            Map<String, String> p = tr.getParameters();
            String v = p.get(key);
            if (v == null)
            {
                System.out.println("TRACEFAIL kind=" + kind + " S=" + s + " err=missing_key_" + key);
                return -1;
            }
            Map<String, String> m = execute("SELECT parameters FROM system_traces.sessions WHERE session_id = ?", tr.getTraceId())
                                    .one().getMap("parameters", UTF8Type.instance, UTF8Type.instance);
            long M = 0;
            for (Map.Entry<String, String> e : m.entrySet())
                M += e.getKey().length() + e.getValue().length();
            String vi = m.get(key);
            String q = p.get("query");
            long L = v.length();
            System.out.println("PROBE kind=" + kind + " S=" + s + " k=" + k + " key=" + key + " L=" + L
                               + " Lint=" + (vi == null ? -1 : vi.length())
                               + " suffix=" + (v.endsWith("...'") ? 1 : 0)
                               + " match=" + (v.equals(expected) ? 1 : 0)
                               + " M=" + M + " R=" + (M - L)
                               + " Lq=" + (q == null ? -1 : q.length())
                               + " uncut=" + full.length() + " tbl=" + tbl);
            if (mOut != null) mOut[0] = M;
            return L;
        }
        catch (Throwable t)
        {
            System.out.println("TRACEFAIL kind=" + kind + " S=" + s + " err=" + t.getClass().getSimpleName() + ":" + String.valueOf(t.getMessage()).replace('\n', ' '));
            return -1;
        }
    }

    @Test
    public void probe() throws Throwable
    {
        requireNetwork();
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob, t text, b0 blob, b1 blob, b2 blob, b3 blob, b4 blob, b5 blob, b6 blob, b7 blob)");
        tbl = KEYSPACE + "." + currentTable();
        Session s = sessionNet();
        System.out.println("START tbl=" + tbl + " tbllen=" + tbl.length() + " shake=" + SHAKE);

        // prepared blob
        PreparedStatement ps = s.prepare("INSERT INTO " + tbl + " (k, v) VALUES (?, ?)").enableTracing();
        for (int S : (SHAKE ? new int[]{ 100, 700 } : new int[]{ 100, 499, 500, 600, 65536, 1048576 }))
        {
            byte[] b = blob(S);
            String full = "0x" + ByteBufferUtil.bytesToHex(ByteBuffer.wrap(b));
            try
            {
                QueryTrace tr = s.execute(ps.bind(S, ByteBuffer.wrap(b))).getExecutionInfo().getQueryTrace();
                report("prepared", S, S, "bound_var_1_v", tr, full, expectedStored(full), null);
            }
            catch (Throwable t)
            {
                System.out.println("TRACEFAIL kind=prepared S=" + S + " err=" + t);
            }
        }

        // prepared text
        PreparedStatement pt = s.prepare("INSERT INTO " + tbl + " (k, t) VALUES (?, ?)").enableTracing();
        for (int n : (SHAKE ? new int[]{ 500 } : new int[]{ 998, 999 }))
        {
            Random r = new Random(42);
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < n; i++) sb.append(ALNUM.charAt(r.nextInt(ALNUM.length())));
            String T = sb.toString();
            String full = "'" + T + "'";
            int k = 2_000_000 + n;
            try
            {
                QueryTrace tr = s.execute(pt.bind(k, T)).getExecutionInfo().getQueryTrace();
                report("text", n, k, "bound_var_1_t", tr, full, expectedStored(full), null);
            }
            catch (Throwable t)
            {
                System.out.println("TRACEFAIL kind=text S=" + n + " err=" + t);
            }
        }

        // multi
        PreparedStatement pm = s.prepare("INSERT INTO " + tbl + " (k, b0, b1, b2, b3, b4, b5, b6, b7) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)").enableTracing();
        Random rm = new Random(42);
        List<Object> vals = new ArrayList<>();
        List<String> fulls = new ArrayList<>();
        vals.add(3_000_000);
        for (int j = 0; j < 8; j++)
        {
            byte[] b = new byte[MB];
            rm.nextBytes(b);
            vals.add(ByteBuffer.wrap(b));
            fulls.add("0x" + ByteBufferUtil.bytesToHex(ByteBuffer.wrap(b)));
        }
        try
        {
            QueryTrace tr = s.execute(pm.bind(vals.toArray())).getExecutionInfo().getQueryTrace();
            long sumL = 0, M = -1;
            for (int j = 0; j < 8; j++)
            {
                long[] mo = new long[1];
                long L = report("multi", MB, 3_000_000, "bound_var_" + (j + 1) + "_b" + j, tr, fulls.get(j), expectedStored(fulls.get(j)), mo);
                sumL += L;
                M = mo[0];
            }
            System.out.println("MULTI M=" + M + " sumL=" + sumL + " R=" + (M - sumL));
        }
        catch (Throwable t)
        {
            System.out.println("TRACEFAIL kind=multi S=65536 err=" + t);
        }

        // control: unprepared QUERY with an inline literal
        for (int S : (SHAKE ? new int[]{ 700 } : new int[]{ 500, 65536 }))
        {
            byte[] b = blob(S);
            String hex = ByteBufferUtil.bytesToHex(ByteBuffer.wrap(b));
            int k = 1_000_000 + S;
            String q = "INSERT INTO " + tbl + " (k, v) VALUES (" + k + ", 0x" + hex + ")";
            SimpleStatement st = new SimpleStatement(q);
            st.enableTracing();
            try
            {
                QueryTrace tr = s.execute(st).getExecutionInfo().getQueryTrace();
                report("control", S, k, "query", tr, "0x" + hex, q, null);
            }
            catch (Throwable t)
            {
                System.out.println("TRACEFAIL kind=control S=" + S + " err=" + t);
            }
        }
        System.out.println("END");
    }
}
