/*
 * Stage-4 harness, internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous, unit tier
 * (case file B2b, the yaml-level check): its own class, so its own JVM, because the configuration is initialised once.
 * internode_application_receive_queue_capacity = 8MiB set on the loaded Config before daemonInitialization(); the getter
 * DatabaseDescriptor.getInternodeApplicationReceiveQueueCapacityInBytes() must return 8388608. Copy into
 * test/unit/org/apache/cassandra/net/ and run with `ant testsome -Dtest.name=org.apache.cassandra.net.ReleaseCapacityConfigTest`.
 */
package org.apache.cassandra.net;

import java.io.FileOutputStream;
import java.io.PrintStream;

import org.junit.Assert;
import org.junit.Test;

import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;

public class ReleaseCapacityConfigTest
{
    @Test
    public void eightMiB() throws Exception
    {
        DatabaseDescriptor.daemonInitialization(() -> {
            Config c = DatabaseDescriptor.loadConfig();
            c.internode_application_receive_queue_capacity = new DataStorageSpec.IntBytesBound("8MiB");
            return c;
        });
        int got = DatabaseDescriptor.getInternodeApplicationReceiveQueueCapacityInBytes();
        boolean ok = got == 8388608;
        String line = "STAGE4 check config.8MiB.queueCapacity expected=8388608 actual=" + got + (ok ? " ok" : " MISMATCH");
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
