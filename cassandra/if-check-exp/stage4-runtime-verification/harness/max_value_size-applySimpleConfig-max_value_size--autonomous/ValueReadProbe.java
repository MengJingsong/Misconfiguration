// Unit tier (B2a-B2h, amended 2026-10-25) of max_value_size-applySimpleConfig-max_value_size--autonomous.
// One JVM per value of max_value_size (daemonInitialization() runs once per JVM). After daemonInitialization() with the probe yaml:
//   read-back getMaxValueSize(); an unrecorded warm-up; then for len in {V-1, V, V+1, 64 MiB}: build the stream (vint len + len zero
//   bytes) BEFORE the measurement, then call BytesType.instance.readBuffer(in, getMaxValueSize()) and record the outcome and the bytes
//   allocated by this thread across the call only (com.sun.management.ThreadMXBean). Controls (B2h): the V+1 and 64 MiB streams read
//   with limit Integer.MAX_VALUE.
// Output lines:  STAGE4 <key> k=v ...   (no assertion about the claim; the summary and the self-check judge the lines)
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.marshal.BytesType;
import org.apache.cassandra.io.util.DataInputBuffer;
import org.apache.cassandra.io.util.DataOutputBuffer;

public class ValueReadProbe
{
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static final byte[] ZEROS = new byte[1 << 20];


    static DataInputBuffer stream(int len) throws Exception
    {
        DataOutputBuffer out = new DataOutputBuffer(len + 16);
        out.writeUnsignedVInt32(len);
        int left = len;
        while (left > 0)
        {
            int n = Math.min(left, ZEROS.length);
            out.write(ZEROS, 0, n);
            left -= n;
        }
        return new DataInputBuffer(out.getData(), 0, out.getLength());
    }

    static long alloc()
    {
        return TMX.getThreadAllocatedBytes(Thread.currentThread().getId());
    }

    static void call(String phase, int len, int limit, boolean record) throws Exception
    {
        DataInputBuffer in = stream(len);
        Runtime rt = Runtime.getRuntime();
        long used0 = rt.totalMemory() - rt.freeMemory();
        long a0 = alloc();
        String outcome;
        ByteBuffer result = null;
        try
        {
            result = BytesType.instance.readBuffer(in, limit);
            long a1 = alloc();
            outcome = "outcome=RETURNED remaining=" + result.remaining() + " delta=" + (a1 - a0);
        }
        catch (Throwable t)
        {
            long a1 = alloc();
            outcome = "outcome=THREW delta=" + (a1 - a0) + " exc=" + t.getClass().getName() + " msg=" + t.getMessage();
        }
        long used1 = rt.totalMemory() - rt.freeMemory();
        if (record)
            System.out.println("STAGE4 call phase=" + phase + " len=" + len + " limit=" + limit + " " + outcome
                               + " info_runtime_used_delta=" + (used1 - used0));
        result = null;
        in.close();
    }

    public static void main(String[] a) throws Exception
    {
        String label = a.length > 0 ? a[0] : "?";
        DatabaseDescriptor.daemonInitialization();
        int v = DatabaseDescriptor.getMaxValueSize();
        System.out.println("STAGE4 readback label=" + label + " getMaxValueSize=" + v
                           + " allocSupported=" + TMX.isThreadAllocatedMemorySupported()
                           + " allocEnabled=" + TMX.isThreadAllocatedMemoryEnabled()
                           + " maxMemory=" + Runtime.getRuntime().maxMemory());
        // warm-up, not recorded: load the classes of both outcomes
        for (int i = 0; i < 3; i++)
        {
            call("warmup", 1024, v, false);
            call("warmup", 1024, 512, false);
        }
        int[] lens = { v - 1, v, v + 1, 64 << 20 };
        for (int len : lens)
        {
            System.gc();
            call("cap", len, DatabaseDescriptor.getMaxValueSize(), true);
        }
        int[] ctl = { v + 1, 64 << 20 };
        for (int len : ctl)
        {
            System.gc();
            call("control", len, Integer.MAX_VALUE, true);
        }
        System.out.println("STAGE4 done label=" + label);
        System.exit(0);
    }
}
