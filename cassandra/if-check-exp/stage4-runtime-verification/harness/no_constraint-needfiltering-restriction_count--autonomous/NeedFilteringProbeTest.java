/*
 * Stage-4 harness, reachability probe for no_constraint-needfiltering-restriction_count--autonomous (step 0 gate, not a measurement).
 * For each query: (a) is it rejected at prepare time without ALLOW FILTERING (SelectStatement.java:1610)? (b) with ALLOW FILTERING
 * (which skips :1610), what do StatementRestrictions.needFiltering(table), isKeyRange(), usesSecondaryIndexing() return, and
 * does line 992 decide the result (needFiltering true while filterRestrictions.needsFiltering(registry), line 985, is false)?
 * Prints PROBE lines. Asserts nothing.
 */
package org.apache.cassandra.cql3;

import java.lang.reflect.Field;

import org.junit.Test;

import org.apache.cassandra.cql3.restrictions.StatementRestrictions;
import org.apache.cassandra.cql3.statements.SelectStatement;
import org.apache.cassandra.index.IndexRegistry;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.schema.Schema;
import org.apache.cassandra.service.ClientState;

public class NeedFilteringProbeTest extends CQLTester
{
    void probe(String label, String cql) throws Throwable
    {
        String rej;
        try { QueryProcessor.getStatement(cql, ClientState.forInternalCalls()); rej = "accepted"; }
        catch (Throwable e) { rej = "REJECTED:" + e.getClass().getSimpleName() + ":" + (e.getMessage() == null ? "" : e.getMessage().substring(0, Math.min(60, e.getMessage().length()))); }
        try
        {
            SelectStatement st = (SelectStatement) QueryProcessor.getStatement(cql + " ALLOW FILTERING", ClientState.forInternalCalls());
            StatementRestrictions r = st.getRestrictions();
            TableMetadata t = Schema.instance.getTableMetadata(st.keyspace(), st.table());
            boolean nf = r.needFiltering(t);
            Field f = StatementRestrictions.class.getDeclaredField("filterRestrictions");
            f.setAccessible(true);
            Object fr = f.get(r);
            boolean l985 = (Boolean) fr.getClass().getMethod("needsFiltering", IndexRegistry.class).invoke(fr, IndexRegistry.obtain(t));
            System.out.println("PROBE " + label + " | " + cql + " | noAF=" + rej + " | needFiltering=" + nf + " line985=" + l985
                               + " line992=" + (nf && !l985) + " keyRange=" + r.isKeyRange() + " usesIndex=" + r.usesSecondaryIndexing());
        }
        catch (Throwable e)
        {
            System.out.println("PROBE " + label + " | " + cql + " | noAF=" + rej + " | AF variant failed: " + e);
        }
    }

    @Test
    public void probes() throws Throwable
    {
        String t = KEYSPACE + "." + createTable("CREATE TABLE %s (pk int, ck1 int, ck2 int, v int, PRIMARY KEY (pk, ck1, ck2))");
        String t1 = KEYSPACE + "." + createTable("CREATE TABLE %s (pk int, ck int, v int, PRIMARY KEY (pk, ck))");
        String ti = KEYSPACE + "." + createTable("CREATE TABLE %s (pk int, ck1 int, ck2 int, v int, PRIMARY KEY (pk, ck1, ck2))");
        createIndex("CREATE INDEX ON %s (v)");
        String tc = KEYSPACE + "." + createTable("CREATE TABLE %s (pk int, ck1 int, ck2 int, v int, PRIMARY KEY (pk, ck1, ck2))");
        createIndex("CREATE INDEX ON %s (ck1)");
        String[][] q = {
            { "Q1 pk+ck1+ck2",    "SELECT * FROM " + t + " WHERE pk=1 AND ck1=1 AND ck2=1" },
            { "Q2 pk+ck1",        "SELECT * FROM " + t + " WHERE pk=1 AND ck1=1" },
            { "Q3 ck1 only",      "SELECT * FROM " + t + " WHERE ck1=1" },
            { "Q4 ck1+ck2",       "SELECT * FROM " + t + " WHERE ck1=1 AND ck2=2" },
            { "Q5 ck2 only",      "SELECT * FROM " + t + " WHERE ck2=1" },
            { "Q6 v only",        "SELECT * FROM " + t + " WHERE v=1" },
            { "Q7 ck1+v",         "SELECT * FROM " + t + " WHERE ck1=1 AND v=1" },
            { "Q8 no WHERE",      "SELECT * FROM " + t },
            { "Q9 token+ck1",     "SELECT * FROM " + t + " WHERE token(pk)>0 AND ck1=1" },
            { "Q10 1-ck ck",      "SELECT * FROM " + t1 + " WHERE ck=5" },
            { "Q11 1-ck pk+ck",   "SELECT * FROM " + t1 + " WHERE pk=1 AND ck=5" },
            { "Q12 idx v",        "SELECT * FROM " + ti + " WHERE v=1" },
            { "Q13 idx v + ck1",  "SELECT * FROM " + ti + " WHERE ck1=1 AND v=1" },
            { "Q14 idx ck1",      "SELECT * FROM " + tc + " WHERE ck1=1" },
            { "Q15 idx ck1+ck2",  "SELECT * FROM " + tc + " WHERE ck1=1 AND ck2=1" },
            { "Q16 slice ck1",    "SELECT * FROM " + t + " WHERE ck1>1" },
        };
        for (String[] e : q) probe(e[0], e[1]);
    }
}
