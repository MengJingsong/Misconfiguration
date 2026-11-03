/* Stage-4 harness, unit tier (B2, amended 2026-10-24) of native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous. Not upstream.
 * No override: the knob is the yaml/Config default (Config.java:285, 16MiB); the read-back line shows it. */
package org.apache.cassandra.transport;

import org.junit.BeforeClass;
import org.junit.Test;
import org.apache.cassandra.config.DatabaseDescriptor;

public class FrameCapDefaultTest extends FrameCapBase
{
    @BeforeClass
    public static void setup() { init("N=default", -1); }

    @Test
    public void run() { runAll("N=default", DatabaseDescriptor.getNativeTransportMaxFrameSize()); }
}
