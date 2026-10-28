/*
 * Stage-4 harness, unit tier U4b of repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio (case 9e).
 * Not upstream. Copy into test/unit/org/apache/cassandra/repair/. Set-up as RepairMessageVerbHandlerOutOfRangeTest.
 * Prints "STAGE4 check <name> <expected> <actual> ok|MISMATCH" (also to -Dstage4.out); fails at the end on a mismatch.
 */
package org.apache.cassandra.repair;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.TimeUnit;

import com.google.common.collect.Lists;
import com.google.common.util.concurrent.ListenableFuture;
import org.junit.After;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;
import org.slf4j.LoggerFactory;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.net.Message;
import org.apache.cassandra.net.MessagingService;
import org.apache.cassandra.net.Verb;
import org.apache.cassandra.repair.messages.PrepareMessage;
import org.apache.cassandra.repair.messages.RepairMessage;
import org.apache.cassandra.repair.state.ParticipateState;
import org.apache.cassandra.schema.TableId;
import org.apache.cassandra.service.ActiveRepairService;
import org.apache.cassandra.service.StorageService;
import org.apache.cassandra.service.disk.usage.DiskUsageMonitor;
import org.apache.cassandra.streaming.PreviewKind;
import org.apache.cassandra.utils.TimeUUID;

import static org.apache.cassandra.utils.TokenRangeTestUtil.MessageDelivery;
import static org.apache.cassandra.utils.TokenRangeTestUtil.generateRanges;
import static org.apache.cassandra.utils.TokenRangeTestUtil.node1;
import static org.apache.cassandra.utils.TokenRangeTestUtil.randomInt;
import static org.apache.cassandra.utils.TokenRangeTestUtil.registerOutgoingMessageSink;
import static org.apache.cassandra.utils.TokenRangeTestUtil.setLocalTokens;
import static org.apache.cassandra.utils.TokenRangeTestUtil.token;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

public class RepairHeadroomVerbTest
{
    private static final String TEST_NAME = "repair_message_vh_test_";
    private static final String KEYSPACE = TEST_NAME + "cql_keyspace";
    private static final String TABLE = "table1";
    private static List<TableId> tableIds;
    static PrintWriter out;
    static int checks = 0, mismatches = 0;
    static DiskUsageMonitor original;
    static ListAppender<ILoggingEvent> appender;

    static void line(String s) { System.out.println(s); if (out != null) { out.println(s); out.flush(); } }

    static void check(String name, Object expected, Object actual)
    {
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        checks++; if (!ok) mismatches++;
        line("STAGE4 check " + name + " " + expected + " " + actual + " " + (ok ? "ok" : "MISMATCH"));
    }

    @BeforeClass
    public static void init() throws Exception
    {
        String f = System.getProperty("stage4.out");
        if (f != null) out = new PrintWriter(new FileWriter(f, true));
        DatabaseDescriptor.setPartitionerUnsafe(Murmur3Partitioner.instance);
        SchemaLoader.loadSchema();
        SchemaLoader.schemaDefinition(TEST_NAME);
        StorageService.instance.initServer(0);
        tableIds = Collections.singletonList(Keyspace.open(KEYSPACE).getColumnFamilyStore(TABLE).metadata().id);
        StorageService.instance.getTokenMetadata().clearUnsafe();
        StorageService.instance.getTokenMetadata().updateNormalTokens(Lists.newArrayList(token(0), token(200), token(400)), node1);
        setLocalTokens(100);
        original = DiskUsageMonitor.instance;
        appender = new ListAppender<>();
        appender.start();
        ((Logger) LoggerFactory.getLogger(ActiveRepairService.class)).addAppender(appender);
    }

    @After
    public void restore()
    {
        DiskUsageMonitor.instance = original;
        DatabaseDescriptor.setRepairDiskHeadroomRejectRatio(0.0);
    }

    static void usage(double u)
    {
        DiskUsageMonitor m = mock(DiskUsageMonitor.class);
        when(m.getDiskUsage()).thenReturn(u);
        DiskUsageMonitor.instance = m;
    }

    static long errorLines(int from)
    {
        return appender.list.subList(from, appender.list.size()).stream()
                            .filter(e -> e.getFormattedMessage().contains("Rejecting incoming repair, disk usage")).count();
    }

    static MessageDelivery deliver(Message<RepairMessage> message) throws Exception
    {
        ListenableFuture<MessageDelivery> sink = registerOutgoingMessageSink(false);
        new RepairMessageVerbHandler().doVerb(message);
        return sink.get(500, TimeUnit.MILLISECONDS);
    }

    static String registered(TimeUUID id)
    {
        try { ActiveRepairService.instance().getParentRepairSession(id); return "registered"; }
        catch (NoSuchRepairSessionException e) { return "NoSuchRepairSessionException"; }
    }

    @Test
    public void participant() throws Throwable
    {
        DatabaseDescriptor.setRepairDiskHeadroomRejectRatio(0.5);
        for (PreviewKind pk : new PreviewKind[]{ PreviewKind.NONE, PreviewKind.ALL })
            for (boolean inc : new boolean[]{ true, false })
            {
                String tag = pk + "_inc=" + inc;
                usage(0.50001);
                TimeUUID id = TimeUUID.Generator.nextTimeUUID();
                PrepareMessage prepare = new PrepareMessage(id, tableIds, generateRanges(10, 20), inc, ActiveRepairService.UNREPAIRED_SSTABLE, true, pk);
                Message<RepairMessage> msg = Message.builder(Verb.PREPARE_MSG, (RepairMessage) prepare).from(node1).withId(randomInt()).build();
                int from = appender.list.size();
                MessageDelivery d = deliver(msg);
                check("U4b_refused_verb_" + tag, Verb.FAILURE_RSP, d.message.verb());
                check("U4b_refused_reason_" + tag, "UNKNOWN", String.valueOf(d.message.payload));
                ParticipateState st = ActiveRepairService.instance().participate(id);
                check("U4b_failure_cause_" + tag, "Not enough disk headroom to perform repair", st == null ? "null" : st.getFailureCause());
                check("U4b_nothing_registered_" + tag, "NoSuchRepairSessionException", registered(id));
                check("U4b_one_error_line_" + tag, 1L, errorLines(from));
                // the dedup path: the same message delivered again
                int from2 = appender.list.size();
                MessageDelivery d2 = deliver(msg);
                check("U4b_dedup_verb_" + tag, Verb.FAILURE_RSP, d2.message.verb());
                check("U4b_dedup_no_second_error_" + tag, 0L, errorLines(from2));

                usage(0.5);
                TimeUUID id2 = TimeUUID.Generator.nextTimeUUID();
                PrepareMessage ok = new PrepareMessage(id2, tableIds, generateRanges(10, 20), inc, ActiveRepairService.UNREPAIRED_SSTABLE, true, pk);
                MessageDelivery d3 = deliver(Message.builder(Verb.PREPARE_MSG, (RepairMessage) ok).from(node1).withId(randomInt()).build());
                check("U4b_admitted_verb_" + tag, Verb.REPAIR_RSP, d3.message.verb());
                check("U4b_admitted_registered_" + tag, "registered", registered(id2));
                ActiveRepairService.instance().removeParentRepairSession(id2);
            }
        MessagingService.instance().outboundSink.clear();
        MessagingService.instance().inboundSink.clear();
        line("STAGE4 summary checks " + checks + " mismatches " + mismatches);
        Assert.assertEquals(0, mismatches);
    }
}
