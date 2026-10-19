/*
 * Stage-4 harness, unit tier of max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction
 * (case file section 9, 9e unit step 3, added at the 2026-10-07 audit). Not part of upstream Cassandra.
 * Copy into test/unit/org/apache/cassandra/db/compaction/ of a local clone at cassandra-5.0.9.
 * System property stage4.out: a file that also receives the STAGE4 lines.
 *
 * It drives the decision point: a real CompactionTask (a major compaction) on 8 real SSTables, with the table's Directories
 * wrapped so that the admission check reads a stub FileStore of fixed usable space U (the technique of upstream
 * PartialCompactionsTest). For each B/total in 1.5, 0.8, 0.4, 0.1 the expected ladder is SIMULATED from the SSTables' measured
 * onDiskLength() (drop the largest while the rest is above B; abort at one), and the debug lines, the counters and the live
 * SSTables are compared with it. A check that does not hold is recorded as MISMATCH and the test goes on; it fails at the end.
 */
package org.apache.cassandra.db.compaction;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.file.FileStore;
import java.nio.file.attribute.FileAttributeView;
import java.nio.file.attribute.FileStoreAttributeView;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.After;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;
import org.slf4j.LoggerFactory;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Directories;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.db.lifecycle.LifecycleTransaction;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.metrics.CompactionMetrics;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.TableMetadataRef;
import org.apache.cassandra.utils.FBUtilities;

public class CompactionLadderTest extends SchemaLoader
{
    static final String KEYSPACE = "CompactionLadderTest";
    static final String TABLE = "t";
    static final long MIB = 1024L * 1024L;
    static final long FLOOR = 50 * MIB;                        // min_free_space_per_drive
    static final long U = 4L * 1024 * MIB;                     // the stub store's usable space: 4 GiB
    static final int SSTABLES = 8, ROWS = 150, VALUE_CHARS = 8000;
    static final double[] FS = { 1.5, 0.8, 0.4, 0.1 };        // B / total
    static final int[] PLANNED = { 0, 2, 5, -1 };              // dropped inputs planned in 9a; -1 = abort
    static final Pattern PASS = Pattern.compile("FileStore (.*) has (\\d+) bytes available, checking if we can write (\\d+) bytes");
    static final String CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

    static PrintWriter out;
    static int mismatches = 0;
    static ListAppender<ILoggingEvent> dirLog, taskLog;
    static final Stub STORE = new Stub();

    static class Stub extends FileStore
    {
        public long getUsableSpace() { return U; }
        public String name() { return "stub"; }
        public String type() { return "stub"; }
        public boolean isReadOnly() { return false; }
        public long getTotalSpace() { return U; }
        public long getUnallocatedSpace() { return U; }
        public boolean supportsFileAttributeView(Class<? extends FileAttributeView> type) { return false; }
        public boolean supportsFileAttributeView(String name) { return false; }
        public <V extends FileStoreAttributeView> V getFileStoreAttributeView(Class<V> type) { return null; }
        public Object getAttribute(String attribute) { return null; }
        public String toString() { return "stub"; }
    }

    static void line(String s)
    {
        System.out.println(s);
        if (out != null) { out.println(s); out.flush(); }
    }

    static void check(String name, Object expected, Object actual)
    {
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        if (!ok) mismatches++;
        line("STAGE4 check " + name + " " + expected + " " + actual + " " + (ok ? "ok" : "MISMATCH"));
    }

    static void checkTrue(String name, boolean cond, String detail)
    {
        if (!cond) mismatches++;
        line("STAGE4 check " + name + " true " + cond + " " + (cond ? "ok" : "MISMATCH") + " [" + detail + "]");
    }

    @BeforeClass
    public static void initSchema() throws Exception
    {
        String f = System.getProperty("stage4.out");
        if (f != null) out = new PrintWriter(new FileWriter(f, true));
        CompactionManager.instance.disableAutoCompaction();
        SchemaLoader.createKeyspace(KEYSPACE, KeyspaceParams.simple(1), SchemaLoader.standardCFMD(KEYSPACE, TABLE));
        wrapDirectories();
        Logger d = (Logger) LoggerFactory.getLogger(Directories.class);
        d.setLevel(Level.DEBUG);
        dirLog = new ListAppender<>();
        dirLog.start();
        d.addAppender(dirLog);
        Logger t = (Logger) LoggerFactory.getLogger(CompactionTask.class);
        t.setLevel(Level.DEBUG);
        taskLog = new ListAppender<>();
        taskLog.start();
        t.addAppender(taskLog);
    }

    // The technique of upstream PartialCompactionsTest: re-create the table's ColumnFamilyStore on a Directories whose admission
    // check reads a stub FileStore (here of fixed usable space) instead of the real one.
    static void wrapDirectories()
    {
        Keyspace keyspace = Keyspace.open(KEYSPACE);
        ColumnFamilyStore store = keyspace.getColumnFamilyStore(TABLE);
        TableMetadataRef metadata = store.metadata;
        keyspace.dropCf(metadata.id, true);
        Directories wrapped = new Directories(store.metadata(), store.getDirectories().getWriteableLocations())
        {
            @Override
            public boolean hasDiskSpaceForCompactionsAndStreams(Map<File, Long> expectedNewWriteSizes, Map<File, Long> totalCompactionWriteRemaining)
            {
                return hasDiskSpaceForCompactionsAndStreams(expectedNewWriteSizes, totalCompactionWriteRemaining, file -> STORE);
            }
        };
        ColumnFamilyStore cfs = ColumnFamilyStore.createColumnFamilyStore(keyspace, TABLE, metadata, wrapped, false, false, true);
        keyspace.initCfCustom(cfs);
        // CompactionManager.disableAutoCompaction() only reaches tables that exist when it is called, and this table is created after it;
        // with 8 equal flushes the size-tiered strategy would merge four of them (found by the instrument run, 2026-10-07).
        cfs.disableAutoCompaction();
    }

    static ColumnFamilyStore cfs()
    {
        return Keyspace.open(KEYSPACE).getColumnFamilyStore(TABLE);
    }

    @After
    public void truncate()
    {
        cfs().truncateBlocking();
        LifecycleTransaction.waitForDeletions();
    }

    static String randomAscii(Random r, int n)
    {
        char[] c = new char[n];
        for (int i = 0; i < n; i++) c[i] = CHARS.charAt(r.nextInt(CHARS.length()));
        return new String(c);
    }

    static void buildInputs(ColumnFamilyStore cfs, long seed)
    {
        Random r = new Random(seed);
        for (int s = 0; s < SSTABLES; s++)
        {
            for (int i = 0; i < ROWS; i++)
                new RowUpdateBuilder(cfs.metadata(), 0, String.format("k%02d_%05d", s, i))
                    .clustering("c")
                    .add("val", randomAscii(r, VALUE_CHARS))
                    .build()
                    .applyUnsafe();
            cfs.forceBlockingFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS);
        }
    }

    static List<Long> lengths(ColumnFamilyStore cfs)
    {
        List<Long> l = new ArrayList<>();
        for (SSTableReader r : cfs.getLiveSSTables()) l.add(r.onDiskLength());
        return l;
    }

    static Set<String> files(ColumnFamilyStore cfs)
    {
        Set<String> s = new HashSet<>();
        for (SSTableReader r : cfs.getLiveSSTables()) s.add(r.getFilename());
        return s;
    }

    /** The ladder of 9a/section 5, simulated: one requested figure per pass; dropped = inputs shed before the pass that admits; -1 = abort. */
    static class Sim
    {
        final List<Long> requested = new ArrayList<>();
        int dropped;
    }

    static Sim simulate(List<Long> sizes, long B)
    {
        Sim s = new Sim();
        List<Long> keep = new ArrayList<>(sizes);
        Collections.sort(keep, Collections.reverseOrder());
        while (true)
        {
            long sum = 0;
            for (long x : keep) sum += x;
            s.requested.add(sum);
            if (sum <= B)                                   // the comparison is  available < toWrite  => refuse
            {
                s.dropped = sizes.size() - keep.size();
                return s;
            }
            if (keep.size() > 1)
                keep.remove(0);                             // the largest goes
            else
            {
                s.dropped = -1;
                return s;
            }
        }
    }

    @Test
    public void ladder() throws Exception
    {
        long oldMin = DatabaseDescriptor.getMinFreeSpacePerDriveInMebibytes();
        double oldPct = DatabaseDescriptor.getMaxSpaceForCompactionsPerDrive();
        CompactionMetrics metrics = CompactionManager.instance.getMetrics();
        try
        {
            DatabaseDescriptor.setMinFreeSpacePerDriveInMebibytes(50);
            for (int k = 0; k < FS.length; k++)
            {
                double f = FS[k];
                String tag = "f" + f;
                ColumnFamilyStore cfs = cfs();
                cfs.disableAutoCompaction();                // a major compaction pauses and resumes the strategies; keep the flag off
                buildInputs(cfs, 1000 + k);
                List<Long> sizes = lengths(cfs);
                Set<String> before = files(cfs);
                long total = 0, min = Long.MAX_VALUE, max = 0;
                for (long x : sizes) { total += x; min = Math.min(min, x); max = Math.max(max, x); }
                check(tag + "_inputs_are_8_sstables", SSTABLES, sizes.size());
                checkTrue(tag + "_inputs_equal_within_10pct", max <= 1.10 * min, "min=" + min + " max=" + max);

                double pct = f * total / (double) (U - FLOOR);
                DatabaseDescriptor.setMaxSpaceForCompactionsPerDrive(pct);
                long B = Math.round((double) (U - FLOOR) * pct);
                check(tag + "_B_from_the_check", B, Directories.getAvailableSpaceForCompactions(STORE));
                Sim sim = simulate(sizes, B);
                line("STAGE4 info " + tag + " total=" + total + " min=" + min + " max=" + max + " pct=" + pct + " B=" + B + " B/total=" + ((double) B / total)
                     + " simulated passes=" + sim.requested + " dropped=" + sim.dropped);
                check(tag + "_simulated_matches_the_plan", PLANNED[k], sim.dropped);

                long r0 = metrics.compactionsReduced.getCount(), d0 = metrics.sstablesDropppedFromCompactions.getCount(), a0 = metrics.compactionsAborted.getCount();
                dirLog.list.clear();
                taskLog.list.clear();
                Throwable err = null;
                try
                {
                    FBUtilities.waitOnFutures(CompactionManager.instance.submitMaximal(cfs, Integer.MAX_VALUE, false));
                }
                catch (Throwable t)
                {
                    err = t;
                }
                LifecycleTransaction.waitForDeletions();

                // (i) the debug lines, pass by pass
                List<long[]> passes = new ArrayList<>();
                for (ILoggingEvent e : dirLog.list)
                {
                    Matcher m = PASS.matcher(e.getFormattedMessage());
                    if (e.getLevel() == Level.DEBUG && m.find() && Long.parseLong(m.group(3)) >= min / 2)
                        passes.add(new long[] { Long.parseLong(m.group(2)), Long.parseLong(m.group(3)) });
                }
                check(tag + "_pass_count", sim.requested.size(), passes.size());
                for (int i = 0; i < Math.min(passes.size(), sim.requested.size()); i++)
                {
                    check(tag + "_pass" + i + "_available", B, passes.get(i)[0]);
                    check(tag + "_pass" + i + "_requested", sim.requested.get(i), passes.get(i)[1]);
                }
                int refusals = 0;
                for (ILoggingEvent e : dirLog.list)
                    if (e.getLevel() == Level.WARN && e.getFormattedMessage().contains(" has only ") && e.getFormattedMessage().endsWith(" is needed")) refusals++;
                check(tag + "_refusal_warnings", sim.requested.size() - (sim.dropped >= 0 ? 1 : 0), refusals);

                // (ii) the counters, (iii) the warnings
                long dr = metrics.compactionsReduced.getCount() - r0, dd = metrics.sstablesDropppedFromCompactions.getCount() - d0, da = metrics.compactionsAborted.getCount() - a0;
                int shed = sim.dropped >= 0 ? sim.dropped : sizes.size() - 1;
                if (sim.dropped > 0)
                {
                    check(tag + "_CompactionsReduced_delta", 1, dr);
                    check(tag + "_SSTablesDropped_delta", sim.dropped, dd);
                    check(tag + "_CompactionsAborted_delta", 0, da);
                }
                else if (sim.dropped == 0)
                {
                    check(tag + "_CompactionsReduced_delta", 0, dr);
                    check(tag + "_SSTablesDropped_delta", 0, dd);
                    check(tag + "_CompactionsAborted_delta", 0, da);
                }
                else
                {
                    check(tag + "_CompactionsReduced_delta", 0, dr);
                    check(tag + "_SSTablesDropped_delta", 0, dd);
                    check(tag + "_CompactionsAborted_delta", 1, da);
                }
                int reducing = 0, notEnough = 0;
                for (ILoggingEvent e : taskLog.list)
                {
                    String msg = e.getFormattedMessage();
                    if (e.getLevel() == Level.WARN && msg.endsWith("Reducing scope.")) reducing++;
                    if (e.getLevel() == Level.WARN && msg.startsWith("Not enough space for compaction (")) notEnough++;
                }
                check(tag + "_Reducing_scope_warnings", shed, reducing);
                check(tag + "_abort_warning", sim.dropped >= 0 ? 0 : 1, notEnough);
                check(tag + "_exception", sim.dropped >= 0 ? "none" : "RuntimeException", err == null ? "none" : "RuntimeException");
                if (err != null)
                    line("STAGE4 info " + tag + " exception: " + err);

                // (iv) the live SSTables
                if (sim.dropped >= 0)
                {
                    check(tag + "_live_after", 1 + sim.dropped, cfs.getLiveSSTables().size());
                    long kept = 0;
                    List<Long> keepSizes = new ArrayList<>(sizes);
                    Collections.sort(keepSizes, Collections.reverseOrder());
                    for (int i = sim.dropped; i < keepSizes.size(); i++) kept += keepSizes.get(i);
                    long outLen = 0;
                    Set<String> after = files(cfs);
                    for (SSTableReader r : cfs.getLiveSSTables()) if (!before.contains(r.getFilename())) outLen += r.onDiskLength();
                    line("STAGE4 info " + tag + " output length " + outLen + " against the kept inputs' " + kept + " (ratio " + ((double) outLen / kept) + ")");
                    Set<String> survivors = new HashSet<>(after);
                    survivors.retainAll(before);
                    check(tag + "_dropped_inputs_still_live", sim.dropped, survivors.size());
                }
                else
                {
                    check(tag + "_live_after", SSTABLES, cfs.getLiveSSTables().size());
                    check(tag + "_same_files_after_abort", true, before.equals(files(cfs)));
                }
                cfs.truncateBlocking();
                LifecycleTransaction.waitForDeletions();
            }
        }
        finally
        {
            DatabaseDescriptor.setMinFreeSpacePerDriveInMebibytes(oldMin);
            DatabaseDescriptor.setMaxSpaceForCompactionsPerDrive(oldPct);
        }
        line("STAGE4 summary mismatches " + mismatches);
        Assert.assertEquals(0, mismatches);
    }
}
