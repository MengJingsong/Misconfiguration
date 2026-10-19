/*
 * Stage-4 harness, internode_application_receive_queue_capacity-acquireCapacity-queueCapacity, unit tier (case 9e, unit
 * step 6 as amended 2026-10-14): the limit's initialization path of the case's section 4, steps 1-5. Runs in its own JVM
 * (its own `ant testsome`), because MessagingService reads the global reserve once, when it is built.
 *
 * The raw config is set to capacity 123,456 B, endpoint reserve 654,321 B and global reserve 777,777 B before
 * MessagingService exists; then getInbound(<peer>) must hold those values, and a handler made by createHandler() must
 * carry the capacity in its final queueCapacity field, the field the check at AbstractMessageHandler.java:419 reads.
 * Prints "STAGE4 check ..." lines as AcquireCapacityTest does.
 */
package org.apache.cassandra.net;

import java.io.FileOutputStream;
import java.io.PrintStream;
import java.lang.reflect.Field;

import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import io.netty.channel.embedded.EmbeddedChannel;
import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.locator.InetAddressAndPort;
import org.apache.cassandra.net.ResourceLimits.Limit;

public class ReceiveQueueWiringTest
{
    private static PrintStream out;
    private static int checks, mismatches;

    @BeforeClass
    public static void setUp() throws Exception
    {
        DatabaseDescriptor.daemonInitialization(() -> {
            Config c = DatabaseDescriptor.loadConfig();
            c.internode_application_receive_queue_capacity = new DataStorageSpec.IntBytesBound("123456B");
            c.internode_application_receive_queue_reserve_endpoint_capacity = new DataStorageSpec.IntBytesBound("654321B");
            c.internode_application_receive_queue_reserve_global_capacity = new DataStorageSpec.IntBytesBound("777777B");
            return c;
        });
        String f = System.getProperty("stage4.out");
        out = f == null ? null : new PrintStream(new FileOutputStream(f, true), true);
    }

    @AfterClass
    public static void tearDown()
    {
        say("STAGE4 summary checks=" + checks + " mismatches=" + mismatches);
        if (out != null)
            out.close();
    }

    private static void say(String s)
    {
        System.out.println(s);
        if (out != null)
            out.println(s);
    }

    private static void check(String name, Object expected, Object actual)
    {
        checks++;
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        if (!ok)
            mismatches++;
        say("STAGE4 check " + name + " expected=" + expected + " actual=" + actual + (ok ? " ok" : " MISMATCH"));
    }

    private static Object field(Object o, String name) throws Exception
    {
        Field f = o.getClass().getDeclaredField(name);
        f.setAccessible(true);
        return f.get(o);
    }

    @Test
    public void wiring() throws Exception
    {
        check("u6.getter.capacity", 123456, DatabaseDescriptor.getInternodeApplicationReceiveQueueCapacityInBytes());
        check("u6.getter.endpoint", 654321, DatabaseDescriptor.getInternodeApplicationReceiveQueueReserveEndpointCapacityInBytes());
        check("u6.getter.global", 777777, DatabaseDescriptor.getInternodeApplicationReceiveQueueReserveGlobalCapacityInBytes());

        InboundMessageHandlers handlers = MessagingService.instance().getInbound(InetAddressAndPort.getByName("127.0.0.9:7012"));
        check("u6.handlers.queueCapacity", 123456, field(handlers, "queueCapacity"));
        check("u6.handlers.endpoint.limit", 654321, ((Limit) field(handlers, "endpointReserveCapacity")).limit());
        check("u6.handlers.global.limit", 777777, ((Limit) field(handlers, "globalReserveCapacity")).limit());

        for (ConnectionType type : new ConnectionType[]{ ConnectionType.URGENT_MESSAGES, ConnectionType.SMALL_MESSAGES, ConnectionType.LARGE_MESSAGES })
        {
            InboundMessageHandler h = handlers.createHandler(null, type, new EmbeddedChannel(), MessagingService.current_version);
            check("u6.handler." + type + ".queueCapacity", 123456L, h.queueCapacity);
            check("u6.handler." + type + ".endpoint.limit", 654321L, h.endpointReserveCapacity.limit());
            check("u6.handler." + type + ".global.limit", 777777L, h.globalReserveCapacity.limit());
            check("u6.handler." + type + ".sharedEndpoint", true, h.endpointReserveCapacity == field(handlers, "endpointReserveCapacity"));
        }
        // a second peer gets its own endpoint reserve and the same global one
        InboundMessageHandlers other = MessagingService.instance().getInbound(InetAddressAndPort.getByName("127.0.0.10:7012"));
        check("u6.otherPeer.ownEndpoint", true, field(other, "endpointReserveCapacity") != field(handlers, "endpointReserveCapacity"));
        check("u6.otherPeer.sharedGlobal", true, field(other, "globalReserveCapacity") == field(handlers, "globalReserveCapacity"));

        Assert.assertEquals("STAGE4 mismatches", 0, mismatches);
    }
}
