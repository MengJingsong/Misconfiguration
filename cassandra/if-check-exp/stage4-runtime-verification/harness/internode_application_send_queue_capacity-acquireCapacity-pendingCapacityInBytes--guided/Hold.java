package stage4;

import java.io.File;

/**
 * Helper for hold-delivery.btm (compiled into a jar on the boot class path). park() blocks the calling thread while the file exists.
 * An interrupt ends the wait. It changes nothing else.
 */
public final class Hold
{
    private Hold() {}

    /** true while the hold file exists (a rule cannot construct a File itself) */
    public static boolean held(String path)
    {
        return path != null && new File(path).exists();
    }

    public static void park(String path)
    {
        File f = new File(path);
        try
        {
            while (f.exists())
                Thread.sleep(25);
        }
        catch (InterruptedException e)
        {
            Thread.currentThread().interrupt();
        }
    }
}
