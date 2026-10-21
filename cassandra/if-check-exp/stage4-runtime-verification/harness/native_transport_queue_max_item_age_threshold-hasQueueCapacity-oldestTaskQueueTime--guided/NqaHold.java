/*
 * Stage-4 harness, both tiers, for native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided
 * (case 9f R2, 2026-10-20). The Byteman helper of the stall rule in nqa.btm: await(file) returns when the file exists
 * (polled every 10 ms), or at once if the thread is interrupted. The node runs from the jar, so this class goes on the
 * boot class path (-Xbootclasspath/a); in the unit tier it is compiled with the tests (test/unit/stage4/).
 */
package stage4;

import java.io.File;
import java.util.concurrent.atomic.AtomicInteger;

public class NqaHold
{
    /** requests currently held by the rule (for the trace lines) */
    public static final AtomicInteger held = new AtomicInteger();

    public static int await(String file)
    {
        int n = held.incrementAndGet();
        File f = new File(file);
        try
        {
            while (!f.exists())
            {
                try
                {
                    Thread.sleep(10);
                }
                catch (InterruptedException e)
                {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
        }
        finally
        {
            held.decrementAndGet();
        }
        return n;
    }
}
