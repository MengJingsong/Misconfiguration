/*
 * Stage-4 harness (not upstream code): unit tier B2 of max_space_usable_for_compactions_in_percentage-applysimpleconfig-range--autonomous.
 * One fresh JVM per yaml value (run by unit-run.sh with -Dcassandra.config=<yaml holding the value>).
 * Runs the REAL startup path DatabaseDescriptor.daemonInitialization() -> applySimpleConfig() (the check at DatabaseDescriptor.java:1016),
 * prints one PROBE line per reading, then (accepted values only) the downstream budget from the REAL Directories.getAvailableSpaceForCompactions
 * on the real FileStore of the data directory, and the runtime setter bypass (setMaxSpaceForCompactionsPerDrive(1.5), no range check).
 */
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Map;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.Directories;

public class MaxSpaceRangeProbe
{
    static void p(String s) { System.out.println("PROBE " + s); }

    static long heapUsedAfterGc()
    {
        for (int i = 0; i < 3; i++) System.gc();
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

    public static void main(String[] a) throws Exception
    {
        String tag = a[0];
        String dataDir = a[1];
        p("start tag=" + tag + " config=" + System.getProperty("cassandra.config"));
        long h0 = heapUsedAfterGc();
        try
        {
            DatabaseDescriptor.daemonInitialization();
        }
        catch (Throwable t)
        {
            p("result=REJECT tag=" + tag + " class=" + t.getClass().getName() + " msg=" + t.getMessage());
            Throwable c = t.getCause();
            while (c != null) { p("cause class=" + c.getClass().getName() + " msg=" + c.getMessage()); c = c.getCause(); }
            long h1 = heapUsedAfterGc();
            p("heap_used_after_gc_before_init=" + h0 + " after_rejected_init=" + h1);
            return;
        }
        long h1 = heapUsedAfterGc();
        p("result=ACCEPT tag=" + tag);
        double v = DatabaseDescriptor.getMaxSpaceForCompactionsPerDrive();
        p("getMaxSpaceForCompactionsPerDrive=" + v);
        p("heap_used_after_gc_before_init=" + h0 + " after_accepted_init=" + h1);
        FileStore fs = Files.getFileStore(Paths.get(dataDir));
        long minFree = DatabaseDescriptor.getMinFreeSpacePerDriveInBytes();
        long u0 = fs.getUsableSpace();
        long budget = Directories.getAvailableSpaceForCompactions(fs);
        long u1 = fs.getUsableSpace();
        long eLo = Math.max(0L, Math.round((Math.min(u0, u1) - minFree) * v));
        long eHi = Math.max(0L, Math.round((Math.max(u0, u1) - minFree) * v));
        p("filestore=" + fs + " usable_before=" + u0 + " usable_after=" + u1 + " minFree=" + minFree);
        p("budget=" + budget + " expected_lo=" + eLo + " expected_hi=" + eHi + " in_range=" + (budget >= eLo && budget <= eHi));
        // admission at the budget boundary through the real gate
        boolean under = Directories.hasDiskSpaceForCompactionsAndStreams(Map.of(fs, Math.max(0L, budget - 1)));
        boolean over = Directories.hasDiskSpaceForCompactionsAndStreams(Map.of(fs, budget + 1));
        p("gate budget-1=" + under + " budget+1=" + over);
        // runtime setter: no range check (DatabaseDescriptor.java:2584-2587)
        double[] bypass = { 1.5, -0.25 };
        for (double b : bypass)
        {
            DatabaseDescriptor.setMaxSpaceForCompactionsPerDrive(b);
            long bb = Directories.getAvailableSpaceForCompactions(fs);
            p("setter value=" + b + " accepted=true getter=" + DatabaseDescriptor.getMaxSpaceForCompactionsPerDrive() + " budget=" + bb
              + " usable_now=" + fs.getUsableSpace() + " minFree=" + minFree);
        }
        p("heap_used_after_gc_end=" + heapUsedAfterGc());
        p("done");
    }
}
