/*
 * Stage-4 harness (not upstream): unit tier B2 of segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous.
 * One fresh JVM per yaml value (sai_options.segment_write_buffer_size), run by unit-run.sh with -Dcassandra.config=<yaml>.
 * Runs the REAL startup path DatabaseDescriptor.daemonInitialization() -> applySimpleConfig() -> conf.sai_options.validate() (the check at
 * StorageAttachedIndexOptions.java:41), prints PROBE lines, and for an accepted value reads the REAL limiter that SSTableIndexWriter uses
 * (V1OnDiskFormat.SEGMENT_BUILD_MEMORY_LIMITER) and feeds it 1 MiB increments until usageExceedsLimit() flips.
 */
import java.lang.reflect.Field;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.config.StorageAttachedIndexOptions;
import org.apache.cassandra.index.sai.disk.v1.V1OnDiskFormat;
import org.apache.cassandra.index.sai.utils.NamedMemoryLimiter;

public class SaiBufferProbe
{
    static void p(String s) { System.out.println("PROBE " + s); }

    public static void main(String[] a) throws Exception
    {
        p("start tag=" + a[0] + " config=" + System.getProperty("cassandra.config"));
        Field f = StorageAttachedIndexOptions.class.getField("MAXIMUM_SEGMENT_BUFFER_MB");
        p("MAXIMUM_SEGMENT_BUFFER_MB(field)=" + f.getInt(null));
        try
        {
            DatabaseDescriptor.daemonInitialization();
        }
        catch (Throwable t)
        {
            p("result=REJECT tag=" + a[0] + " class=" + t.getClass().getName() + " msg=" + t.getMessage());
            p("msg_equals_INVALID_BUFFER_SIZE_ERROR=" + StorageAttachedIndexOptions.INVALID_BUFFER_SIZE_ERROR.equals(t.getMessage()));
            return;
        }
        long configured = DatabaseDescriptor.getSAISegmentWriteBufferSpace().toMebibytes();
        p("result=ACCEPT tag=" + a[0] + " configured_MiB=" + configured);
        NamedMemoryLimiter lim = V1OnDiskFormat.SEGMENT_BUILD_MEMORY_LIMITER;   // loads V1OnDiskFormat: reads the config into the static limit
        p("SEGMENT_BUILD_MEMORY_LIMIT=" + V1OnDiskFormat.SEGMENT_BUILD_MEMORY_LIMIT + " limiter.limitBytes=" + lim.limitBytes()
          + " equals_configured_bytes=" + (lim.limitBytes() == configured * 1048576L));
        long mib = 1048576L, steps = 0;
        long cap = Math.min(configured + 4, 40000);
        long flip = -1;
        for (long i = 1; i <= cap; i++)
        {
            lim.increment(mib);
            steps++;
            if (flip < 0 && lim.usageExceedsLimit())
            {
                flip = i;
                break;
            }
        }
        p("flip_step_MiB=" + flip + " (first 1 MiB increment after which usageExceedsLimit()==true; strict '>' predicts configured+1) used=" + lim.currentBytesUsed());
        p("done");
    }
}
