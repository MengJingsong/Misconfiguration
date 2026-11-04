/* Stage-4 harness, unit tier (B2, amended 2026-10-24) of native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous. Not upstream.
 * 2048MiB: daemonInitialization must throw ConfigurationException; the outcome is printed, not asserted. */
package org.apache.cassandra.transport;

import org.junit.Test;
import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;

public class FrameCap2048MiBTest extends FrameCapBase
{
    @Test
    public void run()
    {
        String outcome;
        try
        {
            DatabaseDescriptor.daemonInitialization(() -> {
                Config c = DatabaseDescriptor.loadConfig();
                c.native_transport_max_frame_size = new DataStorageSpec.IntMebibytesBound("2048MiB");
                return c;
            });
            outcome = "accepted readback=" + DatabaseDescriptor.getNativeTransportMaxFrameSize();
        }
        catch (Throwable t)
        {
            outcome = "exception class=" + t.getClass().getName() + " message=\"" + t.getMessage() + "\"";
        }
        out("STAGE4 N=2048MiB startup " + outcome);
    }
}
