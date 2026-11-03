package org.apache.cassandra.db.guardrails;

import java.util.*;
import org.junit.Test;

// Stage-4 harness of items_per_collection-doAdd-elements_size--autonomous: the B2c probe as filed, with the
// step-0 amendments of 2026-10-26 (marked "amended"): one println per reading; the ordinary user's literal
// name and password (GuardrailTester's constants are private); T values and append count from -Dprobe.t /
// -Dprobe.appends (defaults are the filed 100,1000 and 50; only the shakedown changes them); threshold
// read-back line; superuser memDelta; the disabled (-1/-1) reference arm.
public class ItemsPerCollectionProbeTest extends GuardrailTester
{
    private static Set<Integer> range(int from, int to) { Set<Integer> s = new HashSet<>(); for (int i = from; i < to; i++) s.add(i); return s; }
    private long mem() { return getCurrentColumnFamilyStore().metric.memtableLiveDataSize.getValue(); }
    private int card(int k) throws Throwable { return executeNet("SELECT v FROM %s WHERE k = " + k).one().getSet("v", Integer.class).size(); }
    private static void out(String fmt, Object... a) { System.out.println(String.format(fmt, a)); } // amended: one write per line

    @Test
    public void probe() throws Throwable
    {
        // amended (runbook defect U1, 2026-10-26): the read-back of the stored set is an instrument; test/conf/cassandra.yaml:63-67
        // enables read thresholds (local_read_size_fail_threshold 8192KiB), which abort SELECT v at about 46,000 items
        org.apache.cassandra.config.DatabaseDescriptor.setReadThresholdsEnabled(false);
        out("PROBE readThresholdsEnabled=%s", org.apache.cassandra.config.DatabaseDescriptor.getReadThresholdsEnabled());
        int appends = Integer.getInteger("probe.appends", 50);                       // amended
        for (String ts : System.getProperty("probe.t", "100,1000").split(","))      // amended (filed: {100, 1000})
        {
            int t = Integer.parseInt(ts.trim());
            createTable("CREATE TABLE %s (k int PRIMARY KEY, v set<int>)");
            Guardrails.instance.setItemsPerCollectionThreshold(t / 2, t);
            out("PROBE t=%d readback warn=%d fail=%d", t, Guardrails.instance.getItemsPerCollectionWarnThreshold(),
                Guardrails.instance.getItemsPerCollectionFailThreshold());          // amended
            // (i) single write at T and T+1
            executeNet("INSERT INTO %s (k, v) VALUES (1, ?)", range(0, t));
            long m0 = mem(); String r;
            try { executeNet("INSERT INTO %s (k, v) VALUES (2, ?)", range(0, t + 1)); r = "accepted"; }
            catch (Exception e) { r = "rejected:" + e.getMessage(); }
            out("PROBE t=%d single(T+1)=%s memDelta=%d", t, r, mem() - m0);
            // (iii) empty add
            m0 = mem(); executeNet("UPDATE %s SET v = v + {} WHERE k = 1");
            out("PROBE t=%d emptyAdd memDelta=%d card=%d", t, mem() - m0, card(1));
            // (ii) appends of T items each
            executeNet("INSERT INTO %s (k, v) VALUES (3, {})");
            for (int j = 0; j < appends; j++)
            {
                executeNet("UPDATE %s SET v = v + ? WHERE k = 3", range(j * t, (j + 1) * t));
                if (j % 10 == 9) out("PROBE t=%d appends=%d card=%d mem=%d", t, j + 1, card(3), mem());
            }
            // superuser control: same over-threshold single write
            useSuperUser();
            m0 = mem();                                                              // amended
            executeNet("INSERT INTO %s (k, v) VALUES (4, ?)", range(0, t + 1));
            long d = mem() - m0;
            out("PROBE t=%d superuser(T+1) card=%d memDelta=%d", t, card(4), d);     // amended: memDelta added
            useUser("guardrail_user", "guardrail_password");                         // amended: literals
        }
        // amended: disabled reference (-1/-1), ordinary user, the same over-threshold single write at 1001 items
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v set<int>)");
        Guardrails.instance.setItemsPerCollectionThreshold(-1, -1);
        out("PROBE t=-1 readback warn=%d fail=%d", Guardrails.instance.getItemsPerCollectionWarnThreshold(),
            Guardrails.instance.getItemsPerCollectionFailThreshold());
        long m0 = mem(); String r;
        try { executeNet("INSERT INTO %s (k, v) VALUES (2, ?)", range(0, 1001)); r = "accepted"; }
        catch (Exception e) { r = "rejected:" + e.getMessage(); }
        long d = mem() - m0;
        out("PROBE t=-1 single(1001)=%s memDelta=%d card=%d", r, d, r.equals("accepted") ? card(2) : -1);
        Guardrails.instance.setItemsPerCollectionThreshold(-1, -1);
    }
}
