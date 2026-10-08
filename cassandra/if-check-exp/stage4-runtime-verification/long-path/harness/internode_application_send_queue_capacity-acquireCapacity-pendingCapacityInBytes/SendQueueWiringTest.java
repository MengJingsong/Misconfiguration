/*
 * Stage-4 harness, unit tier of internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes
 * (case file section 9, 9e unit steps U10 and U11). Not part of upstream Cassandra.
 * Copy into test/unit/org/apache/cassandra/net/ of a local clone at cassandra-5.0.9. Run it ALONE (its own ant call, its own JVM):
 * the node-wide reserve is read once, when MessagingService is first touched, so the raw config is set before that.
 * System property stage4.out: a file that also receives the STAGE4 lines.
 *
 * It builds the connections the PRODUCTION way, as MessagingService.getOutbound() does: new OutboundConnectionSettings(to).withDefaults(MESSAGING),
 * then OutboundConnections.tryRegister() (whose constructor calls withDefaultReserveLimits()). ConnectionTest calls the two in the opposite order,
 * which is why upstream cannot see which key sets the per-peer reserve.
 */
package org.apache.cassandra.net;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.concurrent.ConcurrentHashMap;

import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.commitlog.CommitLog;
import org.apache.cassandra.locator.InetAddressAndPort;

import static java.util.concurrent.TimeUnit.SECONDS;

public class SendQueueWiringTest
{
    static final long MIB = 1048576L;
    static PrintWriter out;
    static int mismatches = 0;

    @BeforeClass
    public static void setup() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        CommitLog.instance.start();
        String f = System.getProperty("stage4.out");
        if (f != null)
            out = new PrintWriter(new FileWriter(f, true));
        Config c = DatabaseDescriptor.getRawConfig();
        line("STAGE4 info SendQueueWiringTest start; raw defaults: capacity=" + c.internode_application_send_queue_capacity
             + " send_endpoint=" + c.internode_application_send_queue_reserve_endpoint_capacity
             + " send_global=" + c.internode_application_send_queue_reserve_global_capacity
             + " receive_endpoint=" + c.internode_application_receive_queue_reserve_endpoint_capacity);
        // distinct values so that each limit can be told from the others; set BEFORE MessagingService is first touched
        c.internode_application_send_queue_reserve_endpoint_capacity = new DataStorageSpec.IntBytesBound("2MiB");
        c.internode_application_receive_queue_reserve_endpoint_capacity = new DataStorageSpec.IntBytesBound("3MiB");
        c.internode_application_send_queue_reserve_global_capacity = new DataStorageSpec.IntBytesBound("5MiB");
        c.internode_application_send_queue_capacity = new DataStorageSpec.IntBytesBound("7MiB");
        line("STAGE4 info raw config set: send_endpoint=2MiB receive_endpoint=3MiB send_global=5MiB capacity=7MiB");
    }

    @AfterClass
    public static void cleanup()
    {
        line("STAGE4 info SendQueueWiringTest end; mismatches=" + mismatches);
        if (out != null)
            out.close();
    }

    static void line(String s)
    {
        System.out.println(s);
        if (out != null) { out.println(s); out.flush(); }
    }

    static void check(String name, Object expected, Object actual)
    {
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        if (!ok) mismatches++;
        line("STAGE4 check " + name + " " + expected + " " + actual + " " + (ok ? "ok" : "MISMATCH"));
    }

    /** U10: which key sets the per-peer reserve on the production path; also the node-wide reserve and the capacity. */
    @Test
    public void testWiring() throws Exception
    {
        InetAddressAndPort to = InetAddressAndPort.getByName("127.0.0.9");
        OutboundConnectionSettings settings = new OutboundConnectionSettings(to).withDefaults(ConnectionCategory.MESSAGING);
        line("STAGE4 info after withDefaults(): field send_endpoint=" + settings.applicationSendQueueReserveEndpointCapacityInBytes
             + " field capacity=" + settings.applicationSendQueueCapacityInBytes);
        OutboundConnections connections = OutboundConnections.tryRegister(new ConcurrentHashMap<>(), to, settings);
        try
        {
            // 3 MiB = the receive-side key (what section 4 predicts); 2 MiB would be the send-side key and would refute it
            check("U10 small endpoint reserve limit (3 MiB = receive key; 2 MiB would refute)", 3 * MIB, connections.small.unsafeGetEndpointReserveLimits().limit());
            check("U10 large endpoint reserve limit", 3 * MIB, connections.large.unsafeGetEndpointReserveLimits().limit());
            check("U10 urgent endpoint reserve limit", 3 * MIB, connections.urgent.unsafeGetEndpointReserveLimits().limit());
            check("U10 the three links share one endpoint reserve object", true,
                  connections.small.unsafeGetEndpointReserveLimits() == connections.large.unsafeGetEndpointReserveLimits()
                  && connections.large.unsafeGetEndpointReserveLimits() == connections.urgent.unsafeGetEndpointReserveLimits());
            check("U10 node-wide reserve limit (send global key, 5 MiB)", 5 * MIB, MessagingService.instance().outboundGlobalReserveLimit.limit());
            check("U10 small capacity", 7 * MIB, connections.small.settings().applicationSendQueueCapacityInBytes);
            check("U10 large capacity", 7 * MIB, connections.large.settings().applicationSendQueueCapacityInBytes);
            check("U10 urgent capacity", 7 * MIB, connections.urgent.settings().applicationSendQueueCapacityInBytes);
            // and the accessor the section 4 reading rests on
            check("U10 settings accessor applicationSendQueueReserveEndpointCapacityInBytes() on a fresh settings object", 3 * MIB,
                  (long) new OutboundConnectionSettings(to).applicationSendQueueReserveEndpointCapacityInBytes());
        }
        finally
        {
            connections.close(false).get(30L, SECONDS);
        }
        Assert.assertEquals("mismatches so far", 0, mismatches);
    }

    /** U11: a capacity below 1 KiB is refused when the settings are filled, not at startup; 1 KiB is accepted. */
    @Test
    public void testCapacityFloor() throws Exception
    {
        Config c = DatabaseDescriptor.getRawConfig();
        InetAddressAndPort to = InetAddressAndPort.getByName("127.0.0.9");
        DataStorageSpec.IntBytesBound saved = c.internode_application_send_queue_capacity;
        try
        {
            c.internode_application_send_queue_capacity = new DataStorageSpec.IntBytesBound("512B");
            String msg = null;
            try
            {
                new OutboundConnectionSettings(to).withDefaults(ConnectionCategory.MESSAGING);
            }
            catch (IllegalArgumentException e)
            {
                msg = e.getMessage();
            }
            check("U11 512B refused with IllegalArgumentException", "illegal application send queue capacity: 512", msg);
            c.internode_application_send_queue_capacity = new DataStorageSpec.IntBytesBound("1KiB");
            OutboundConnectionSettings ok = new OutboundConnectionSettings(to).withDefaults(ConnectionCategory.MESSAGING);
            check("U11 1KiB accepted", 1024, ok.applicationSendQueueCapacityInBytes);
        }
        finally
        {
            c.internode_application_send_queue_capacity = saved;
        }
        Assert.assertEquals("mismatches so far", 0, mismatches);
    }
}
