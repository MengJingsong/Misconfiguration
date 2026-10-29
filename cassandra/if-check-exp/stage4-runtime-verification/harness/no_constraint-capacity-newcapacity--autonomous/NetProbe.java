package org.apache.cassandra.net;

/**
 * Stage-4 probe for no_constraint-capacity-newcapacity--autonomous, fed by Byteman (rules.btm).
 * sc: calls that reached BufferPoolAllocator.java:124 (super.capacity). At line 128 (old buffer about to be returned to the pool)
 * it records usedSizeInBytes() and overflowMemoryInBytes() (both old and new buffer are held at that moment).
 */
public final class NetProbe
{
    static long sc, at128 = 0, used128 = -1, ovf128 = -1;

    public static void reset() { sc = 0; at128 = 0; used128 = -1; ovf128 = -1; }

    public static void sc() { sc++; }

    public static void atPut()
    {
        at128++;
        used128 = GlobalBufferPoolAllocator.instance.usedSizeInBytes();
        ovf128 = GlobalBufferPoolAllocator.instance.overflowMemoryInBytes();
    }
}
