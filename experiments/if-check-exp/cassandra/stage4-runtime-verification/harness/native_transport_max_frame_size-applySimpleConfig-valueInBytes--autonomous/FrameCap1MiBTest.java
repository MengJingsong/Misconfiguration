/* Stage-4 harness, unit tier (B2, amended 2026-10-24) of native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous. Not upstream. */
package org.apache.cassandra.transport;

import org.junit.BeforeClass;
import org.junit.Test;

public class FrameCap1MiBTest extends FrameCapBase
{
    @BeforeClass
    public static void setup() { init("N=1MiB", 1); }

    @Test
    public void run() { runAll("N=1MiB", 1L << 20); }
}
