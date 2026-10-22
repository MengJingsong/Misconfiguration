/*
 * Stage-4 harness, internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous, unit
 * tier (B2b, the yaml-level check): own class, so own JVM. internode_application_receive_queue_reserve_global_capacity = 32MiB
 * (and the endpoint reserve 32MiB, internode_max_message_size left to derive) set on the loaded Config before
 * daemonInitialization(); the getter DatabaseDescriptor.getInternodeApplicationReceiveQueueReserveGlobalCapacityInBytes()
 * must return 33554432. Copy into test/unit/org/apache/cassandra/net/.
 */
package org.apache.cassandra.net;

import java.io.FileOutputStream;
import java.io.PrintStream;

import org.junit.Assert;
import org.junit.Test;

import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;

public class AcquireExcessConfigTest
{
    @Test
    public void thirtyTwoMiB() throws Exception
    {
        DatabaseDescriptor.daemonInitialization(() -> {
            Config c = DatabaseDescriptor.loadConfig();
            c.internode_application_receive_queue_reserve_global_capacity = new DataStorageSpec.IntBytesBound("32MiB");
            c.internode_application_receive_queue_reserve_endpoint_capacity = new DataStorageSpec.IntBytesBound("32MiB");
            return c;
        });
        int got = DatabaseDescriptor.getInternodeApplicationReceiveQueueReserveGlobalCapacityInBytes();
        int ep = DatabaseDescriptor.getInternodeApplicationReceiveQueueReserveEndpointCapacityInBytes();
        int max = DatabaseDescriptor.getInternodeMaxMessageSizeInBytes();
        boolean ok = got == 33554432 && ep == 33554432 && max == 33554432;
        String line = "STAGE4 check config.32MiB global/endpoint/maxMessage expected=33554432/33554432/33554432 actual="
                      + got + "/" + ep + "/" + max + (ok ? " ok" : " MISMATCH");
        System.out.println(line);
        String f = System.getProperty("stage4.out");
        if (f != null)
            try (PrintStream out = new PrintStream(new FileOutputStream(f, true), true))
            {
                out.println(line);
            }
        Assert.assertTrue(line, ok);
    }
}
