/*
 * Stage-4 harness, unit tier (B2, amendments U1-U5 of 2026-10-27) of
 * max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous.
 * One class per knob value (the field RangeCommands.MAX_CONCURRENT_RANGE_REQUESTS is static final); the four classes differ only in
 * LABEL and VALUE (VALUE = -1: property not set, the default 10 x availableProcessors). Set-up of the property follows
 * RangeCommandsTest.java:56-66. Copied into the clone's test/unit/org/apache/cassandra/service/reads/range/ only for the run.
 */
package org.apache.cassandra.service.reads.range;

import java.lang.reflect.Field;

import org.junit.AfterClass;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.Util;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.db.PartitionRangeReadCommand;
import org.apache.cassandra.db.filter.DataLimits;
import org.apache.cassandra.distributed.shared.WithProperties;
import org.apache.cassandra.transport.Dispatcher;

import static org.apache.cassandra.config.CassandraRelevantProperties.MAX_CONCURRENT_RANGE_REQUESTS;
import static org.apache.cassandra.db.ConsistencyLevel.ONE;
import static org.junit.Assert.assertEquals;

public class RangeCapProbe16Test extends CQLTester
{
    static final String LABEL = "16";
    static final int VALUE = 16;
    static final int DEFAULT_CAP = 20; // U2 and D1: 10 x 2 (-XX:ActiveProcessorCount=2 in the forked test JVM, build.xml:136,1170; RangeCommands.java:54)
    static WithProperties properties;

    @BeforeClass
    public static void setProperty()
    {
        properties = new WithProperties();
        if (VALUE > 0)
            properties.set(MAX_CONCURRENT_RANGE_REQUESTS, VALUE);
    }

    @AfterClass
    public static void cleanup()
    {
        properties.close();
    }

    @Test
    public void probe() throws Exception
    {
        Field f = RangeCommands.class.getDeclaredField("MAX_CONCURRENT_RANGE_REQUESTS");
        f.setAccessible(true);
        int cap = f.getInt(null); // initialises RangeCommands now, after the property is set

        int cf0 = RangeCommandIterator.computeConcurrencyFactor(32, 1, cap, 5000, 0);
        int cf100 = RangeCommandIterator.computeConcurrencyFactor(32, 1, cap, 5000, 100);

        long[] a = new long[16], b = new long[16];
        for (int i = 0; i < 16; i++)
        {
            a[i] = 10L * (2 * i + 1);
            b[i] = 10L * (2 * i + 2);
        }
        new TokenUpdater().withTokens("127.0.0.1", a).withTokens("127.0.0.2", b).update();

        String table = createTable("CREATE TABLE %s (k int PRIMARY KEY, v int)");
        Keyspace keyspace = Keyspace.open(KEYSPACE);
        ColumnFamilyStore cfs = keyspace.getColumnFamilyStore(table);
        PartitionRangeReadCommand cmd = (PartitionRangeReadCommand) Util.cmd(cfs).build();
        cmd = cmd.withUpdatedLimit(DataLimits.cqlLimits(5000));

        int max, cf, ranges;
        try (RangeCommandIterator it = RangeCommands.rangeCommandIterator(cmd, ONE, Dispatcher.RequestTime.forImmediateExecution());
             ReplicaPlanIterator rp = new ReplicaPlanIterator(cmd.dataRange().keyRange(), cmd.indexQueryPlan(), keyspace, ONE))
        {
            max = it.maxConcurrencyFactor();
            cf = it.concurrencyFactor();
            ranges = rp.size();
        }
        System.out.println("RNGU," + LABEL + ",cap=" + cap + ",cf0=" + cf0 + ",cf100=" + cf100 + ",max=" + max + ",cf=" + cf + ",ranges=" + ranges
                           + ",limit=" + cmd.limits().count() + ",procs=" + Runtime.getRuntime().availableProcessors());
        System.out.flush();

        int c = VALUE > 0 ? VALUE : DEFAULT_CAP;
        assertEquals("cap read-back", c, cap);
        assertEquals("cf0", Math.max(1, Math.min(c, 31)), cf0);
        assertEquals("cf100", Math.max(1, Math.min(Math.min(c, 31), 49)), cf100);
        assertEquals("max", Math.min(33, c), max);
        assertEquals("cf", 1, cf);
        assertEquals("ranges", 33, ranges);
    }
}
