/*
 * Stage 4, unit tier (B2) of seed_count_warn_threshold-getseeds-seeds_size--autonomous. Not upstream.
 * Copy into test/unit/org/apache/cassandra/locator/ of a copy of cassandra-5.0.9 and run, one JVM per cell (unit-run.sh):
 *   ant testsome -Dtest.name=org.apache.cassandra.locator.SeedCountFootprintTest \
 *     -Dtest.jvm.args="-Dcassandra.config=file://<yaml with K seeds> [-Dcassandra.seed_count_warn_threshold=T] -Dstage4.out=<file> -Dstage4.arm=<arm> -Dstage4.k=<K>"
 * Reads: the size of the list SimpleSeedProvider.getSeeds() returns, whether the WARN was logged, the deep size of the list
 * (ObjectSizes.measureDeep), the live heap held by 10 retained copies after GC (per copy), and DatabaseDescriptor.getSeeds().
 */
package org.apache.cassandra.locator;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.junit.BeforeClass;
import org.junit.Test;
import org.slf4j.LoggerFactory;

import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.utils.ObjectSizes;

public class SeedCountFootprintTest
{
    static PrintWriter out;

    static synchronized void line(String s)
    {
        System.out.println(s);
        try
        {
            if (out == null && System.getProperty("stage4.out") != null)
                out = new PrintWriter(new FileWriter(System.getProperty("stage4.out"), true), true);
        }
        catch (java.io.IOException e)
        {
            throw new RuntimeException(e);
        }
        if (out != null)
            out.println(s);
    }

    @BeforeClass
    public static void setup()
    {
        DatabaseDescriptor.daemonInitialization();
    }

    static long usedAfterGc() throws InterruptedException
    {
        for (int i = 0; i < 3; i++)
        {
            System.gc();
            Thread.sleep(300);
        }
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

    @Test
    public void run() throws Throwable
    {
        String arm = System.getProperty("stage4.arm", "?");
        int k = Integer.parseInt(System.getProperty("stage4.k", "0"));
        String thrProp = System.getProperty("cassandra.seed_count_warn_threshold", "unset(default 20)");
        String label = arm + "-k" + k + "-t" + thrProp + "-r" + System.getProperty("stage4.rep", "1");
        SimpleSeedProvider p = new SimpleSeedProvider(Collections.emptyMap());
        ListAppender<ILoggingEvent> app = new ListAppender<>();
        app.start();
        ch.qos.logback.classic.Logger lg = (ch.qos.logback.classic.Logger) LoggerFactory.getLogger(SimpleSeedProvider.class);
        lg.addAppender(app);

        List<InetAddressAndPort> first = p.getSeeds();
        int warns = 0;
        for (ILoggingEvent e : app.list)
            if (e.getFormattedMessage().contains("Seed provider returned more than"))
                warns++;
        String warnText = warns > 0 ? app.list.stream().filter(e -> e.getFormattedMessage().contains("Seed provider returned more than")).findFirst().get().getFormattedMessage().substring(0, 40) : "-";
        lg.detachAppender(app);
        // runbook defect 1 fix: the 1000+ DEBUG lines each getSeeds() logs ('Only resolving one IP per DNS record') sit in the async log queue and
        // pollute the heap reading; log at WARN from here on and let the queue drain before the baseline
        lg.setLevel(ch.qos.logback.classic.Level.WARN);
        app.list.clear();
        Thread.sleep(2000);
        long deep = ObjectSizes.measureDeep(first);
        int ddSize = DatabaseDescriptor.getSeeds().size();

        long h0 = usedAfterGc();
        List<List<InetAddressAndPort>> hold = new ArrayList<>();
        for (int i = 0; i < 10; i++)
            hold.add(p.getSeeds());
        long h1 = usedAfterGc();
        int sizeCheck = hold.get(9).size();
        line("STAGE4 final label=" + label + " arm=" + arm + " k_in_yaml=" + k + " threshold=" + thrProp + " returned=" + first.size() + " warn_lines=" + warns
             + " deepBytes=" + deep + " heapPerCopy=" + (h1 - h0) / 10 + " copy10_size=" + sizeCheck + " databaseDescriptorGetSeeds=" + ddSize + " warnText='" + warnText + "'");
        line("STAGE4 done label=" + label);
    }
}
