import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;

import io.netty.util.concurrent.FastThreadLocal;

/** Byteman helper (agent option sys:): the calling thread's retained decrypt buffer capacity (private static
 *  EncryptedChecksummedDataInput.reusableBuffers) and the thread's allocated bytes. */
public class EcHelper
{
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static Field f;

    @SuppressWarnings("unchecked")
    public static int tl()
    {
        try
        {
            if (f == null)
            {
                f = Class.forName("org.apache.cassandra.hints.EncryptedChecksummedDataInput").getDeclaredField("reusableBuffers");
                f.setAccessible(true);
            }
            return ((FastThreadLocal<ByteBuffer>) f.get(null)).get().capacity();
        }
        catch (Throwable t)
        {
            return -1;
        }
    }

    public static long alloc()
    {
        return TMX.getThreadAllocatedBytes(Thread.currentThread().getId());
    }

    public static String thread()
    {
        return Thread.currentThread().getName() + "#" + Thread.currentThread().getId();
    }
}
