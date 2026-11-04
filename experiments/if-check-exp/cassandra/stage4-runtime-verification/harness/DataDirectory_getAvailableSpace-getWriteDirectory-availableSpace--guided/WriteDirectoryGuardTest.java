/*
 * Stage 4, unit tier, DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace (case 9c/9e, amended 2026-10-15).
 * Not upstream. Copy into test/unit/org/apache/cassandra/db/compaction/writers/ of a clone at cassandra-5.0.9 and run once per
 * partitioner:
 *   ant testsome -Dtest.name=org.apache.cassandra.db.compaction.writers.WriteDirectoryGuardTest \
 *     -Dtest.jvm.args="-Dstage4.partitioner=ByteOrderedPartitioner -Dstage4.out=<file>"
 *
 * The guard is CompactionAwareWriter.getWriteDirectory():281-286, reached only from maybeSwitchLocation() when the table's disk
 * boundaries are null (:181-191). The stub is a Byteman rule on Directories$DataDirectory.getAvailableSpace() that returns STUB
 * when STUB >= 0 (off at -1). Every check prints "STAGE4 check <name> expected=<..> actual=<..> -> ok|MISMATCH" to stdout and
 * to the file named by -Dstage4.out; a mismatch is recorded and the test goes on, then fails at the end of its method.
 */
package org.apache.cassandra.db.compaction.writers;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Collections;
import java.util.List;
import java.util.Random;
import java.util.Set;
import java.util.TreeSet;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import org.junit.BeforeClass;
import org.junit.FixMethodOrder;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.MethodSorters;

import org.apache.cassandra.ServerTestUtils;
import org.apache.cassandra.config.CassandraRelevantProperties;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Directories;
import org.apache.cassandra.db.compaction.AbstractCompactionStrategy;
import org.apache.cassandra.db.compaction.CompactionController;
import org.apache.cassandra.db.compaction.CompactionIterator;
import org.apache.cassandra.db.compaction.OperationType;
import org.apache.cassandra.db.lifecycle.LifecycleTransaction;
import org.apache.cassandra.dht.ByteOrderedPartitioner;
import org.apache.cassandra.dht.IPartitioner;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.dht.Token;
import org.apache.cassandra.io.FSDiskFullWriteError;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.service.StorageService;
import org.apache.cassandra.utils.FBUtilities;
import org.jboss.byteman.contrib.bmunit.BMRule;
import org.jboss.byteman.contrib.bmunit.BMUnitRunner;

import static org.apache.cassandra.utils.TimeUUID.Generator.nextTimeUUID;
import static org.junit.Assert.assertEquals;

@RunWith(BMUnitRunner.class)
@FixMethodOrder(MethodSorters.NAME_ASCENDING)
@BMRule(name = "stage4 dds stub getAvailableSpace",
        targetClass = "org.apache.cassandra.db.Directories$DataDirectory",
        targetMethod = "getAvailableSpace",
        targetLocation = "AT ENTRY",
        condition = "org.apache.cassandra.db.compaction.writers.WriteDirectoryGuardTest.STUB >= 0",
        action = "return org.apache.cassandra.db.compaction.writers.WriteDirectoryGuardTest.STUB;")
public class WriteDirectoryGuardTest extends CQLTester
{
    public static volatile long STUB = -1;

    static final String PART = System.getProperty("stage4.partitioner", "ByteOrderedPartitioner");
    static final boolean BOP = PART.equals("ByteOrderedPartitioner");
    static final int SSTABLES = 3, ROWS = 200, PAYLOAD = 5120;
    static PrintWriter out;
    int mismatches = 0;

    /** Shadows CQLTester.setUpClass(): the same steps, with the partitioner of this JVM instead of Murmur3. */
    @BeforeClass
    public static void setUpClass()
    {
        CassandraRelevantProperties.SUPERUSER_SETUP_DELAY_MS.setLong(0);
        ServerTestUtils.daemonInitialization();
        IPartitioner p = BOP ? ByteOrderedPartitioner.instance : Murmur3Partitioner.instance;
        StorageService.instance.setPartitionerUnsafe(p);
        prepareServer();
        try
        {
            String f = System.getProperty("stage4.out");
            if (f != null)
                out = new PrintWriter(new FileWriter(f, true), true);
        }
        catch (IOException e)
        {
            throw new RuntimeException(e);
        }
        info("JVM partitioner " + DatabaseDescriptor.getPartitioner().getClass().getSimpleName() + " (stage4.partitioner=" + PART + ")");
    }

    static void info(String s)
    {
        String l = "STAGE4 [" + PART + "] info " + s;
        System.out.println(l);
        if (out != null)
            out.println(l);
    }

    void check(String name, Object expected, Object actual)
    {
        boolean ok = expected == null ? actual == null : expected.equals(actual);
        if (!ok)
            mismatches++;
        String l = "STAGE4 [" + PART + "] check " + name + " expected=" + expected + " actual=" + actual + " -> " + (ok ? "ok" : "MISMATCH");
        System.out.println(l);
        if (out != null)
            out.println(l);
    }

    void done(String test)
    {
        info(test + " done, mismatches " + mismatches);
        assertEquals("mismatches in " + test, 0, mismatches);
    }

    ColumnFamilyStore build(int sstables, int rows, int seed) throws Throwable
    {
        createTable("CREATE TABLE %s (pk int PRIMARY KEY, v blob) WITH compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'} AND compression = {'enabled': false}");
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        cfs.disableAutoCompaction();
        Random r = new Random(seed);
        for (int s = 0; s < sstables; s++)
        {
            for (int i = 0; i < rows; i++)
            {
                byte[] b = new byte[PAYLOAD];
                r.nextBytes(b);
                execute("INSERT INTO %s (pk, v) VALUES (?, ?)", s * 1_000_000 + i, ByteBuffer.wrap(b));
            }
            cfs.forceBlockingFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS);
        }
        return cfs;
    }

    static Set<String> files(ColumnFamilyStore cfs) throws IOException
    {
        Set<String> all = new TreeSet<>();
        for (org.apache.cassandra.io.util.File d : cfs.getDirectories().getCFDirectories())
            try (Stream<Path> st = Files.list(d.toPath()))
            {
                all.addAll(st.filter(Files::isRegularFile).map(p -> p.getFileName().toString()).collect(Collectors.toList()));
            }
        return all;
    }

    static long dataDbCount(Set<String> names)
    {
        return names.stream().filter(n -> n.endsWith("-Data.db")).count();
    }

    static String positions(ColumnFamilyStore cfs)
    {
        List<?> p = cfs.getDiskBoundaries().positions;
        return p == null ? "null" : "list(" + p.size() + ")";
    }

    /** Outcome of building a DefaultCompactionWriter over every live SSTable and appending the first partition. */
    static class Attempt
    {
        long T;
        String message;              // null if the append did not throw
        Set<String> before, atAppend, afterAbort;
        int liveBefore, liveAfter;
    }

    /** The upstream compact() of CompactionAwareWriterTest, stopped after the first append; the writer is always aborted. */
    Attempt attempt(ColumnFamilyStore cfs) throws Throwable
    {
        Attempt a = new Attempt();
        Set<SSTableReader> live = cfs.getLiveSSTables();
        a.liveBefore = live.size();
        a.T = SSTableReader.getTotalBytes(live);
        LifecycleTransaction txn = cfs.getTracker().tryModify(live, OperationType.COMPACTION);
        CompactionAwareWriter writer = new DefaultCompactionWriter(cfs, cfs.getDirectories(), txn, txn.originals());
        a.before = files(cfs);
        long nowInSec = FBUtilities.nowInSeconds();
        try (AbstractCompactionStrategy.ScannerList scanners = cfs.getCompactionStrategyManager().getScanners(txn.originals());
             CompactionController controller = new CompactionController(cfs, txn.originals(), cfs.gcBefore(nowInSec));
             CompactionIterator ci = new CompactionIterator(OperationType.COMPACTION, scanners.scanners, controller, nowInSec, nextTimeUUID()))
        {
            try
            {
                writer.append(ci.next());
            }
            catch (RuntimeException e)
            {
                a.message = e.getMessage();
            }
            a.atAppend = files(cfs);
        }
        finally
        {
            writer.abort(null);
            writer.close();
        }
        a.afterAbort = files(cfs);
        a.liveAfter = cfs.getLiveSSTables().size();
        return a;
    }

    static String guardMessage(long est, Directories.DataDirectory d, long avail)
    {
        return String.format("Not enough space to write %s to %s (%s available)",
                             FBUtilities.prettyPrintMemory(est), d.location, FBUtilities.prettyPrintMemory(avail));
    }

    @Test
    public void t1_positions() throws Throwable
    {
        ColumnFamilyStore cfs = build(1, 10, 1);
        String before = positions(cfs);
        info("positions before a local token: " + before);
        IPartitioner p = DatabaseDescriptor.getPartitioner();
        Token tok = p.getTokenFactory().fromString(BOP ? "00" : "0");
        StorageService.instance.getTokenMetadata().updateNormalTokens(Collections.singleton(tok), FBUtilities.getBroadcastAddressAndPort());
        cfs.invalidateLocalRanges();
        String after = positions(cfs);
        info("positions after registering local token " + tok + ": " + after);
        check("t1 positions before the token (a unit JVM owns no ranges)", "null", before);
        check("t1 positions after the token", BOP ? "null" : "list(1)", after);
        done("t1_positions");
    }

    @Test
    public void t2_boundary() throws Throwable
    {
        ColumnFamilyStore cfs = build(SSTABLES, ROWS, 2);
        info("t2 positions " + positions(cfs) + "; inputs " + cfs.getLiveSSTables().size());
        Directories.DataDirectory d = cfs.getDirectories().getWriteableLocations()[0];
        long T = SSTableReader.getTotalBytes(cfs.getLiveSSTables());
        info("t2 T (sum of onDiskLength) = " + T + " in " + d.location);
        try
        {
            for (long stub : new long[]{ T - 1, T, 1 })
            {
                STUB = stub;
                Attempt a = attempt(cfs);
                STUB = -1;
                long newData = dataDbCount(a.atAppend) - dataDbCount(a.before);
                info("t2 stub=" + stub + ": message=" + a.message + "; files " + a.before.size() + " -> " + a.atAppend.size() + " -> " + a.afterAbort.size()
                     + "; new Data.db at the append " + newData + "; live " + a.liveBefore + " -> " + a.liveAfter);
                check("t2 stub=" + stub + " estimate is the inputs' onDiskLength sum", T, a.T);
                boolean refuse = BOP && stub < T;
                check("t2 stub=" + stub + " guard message", refuse ? guardMessage(T, d, stub) : null, a.message);
                check("t2 stub=" + stub + " new files at the append", refuse ? a.before : "a new Data.db", refuse ? a.atAppend : (newData == 1 ? "a new Data.db" : "Data.db +" + newData));
                check("t2 stub=" + stub + " inputs live after the abort", SSTABLES, a.liveAfter);
                check("t2 stub=" + stub + " no new Data.db left after the abort", dataDbCount(a.before), dataDbCount(a.afterAbort));
                if (stub == 1 && BOP)
                    check("t2 stub=1 message ends (1B available)", true, a.message != null && a.message.endsWith("(1B available)"));
            }
        }
        finally
        {
            STUB = -1;
        }
        done("t2_boundary");
    }

    @Test
    public void t3_clamp() throws Throwable
    {
        ColumnFamilyStore cfs = build(SSTABLES, ROWS, 3);
        Directories.DataDirectory d = cfs.getDirectories().getWriteableLocations()[0];
        long T = SSTableReader.getTotalBytes(cfs.getLiveSSTables());
        long m0 = DatabaseDescriptor.getMinFreeSpacePerDriveInMebibytes();
        try
        {
            long mBytes = DatabaseDescriptor.setMinFreeSpacePerDriveInMebibytes(1L << 30);   // 1 PiB, above any device
            long avail = d.getAvailableSpace();
            info("t3 min_free_space_per_drive " + mBytes + " B; getAvailableSpace() = " + avail);
            check("t3 getAvailableSpace() clamps at 0", 0L, avail);
            Attempt a = attempt(cfs);
            info("t3 message=" + a.message);
            check("t3 guard message at the clamp", BOP ? guardMessage(T, d, 0) : null, a.message);
            if (BOP)
                check("t3 message ends (0B available)", true, a.message != null && a.message.endsWith("(0B available)"));
            check("t3 inputs live after the abort", SSTABLES, a.liveAfter);
        }
        finally
        {
            DatabaseDescriptor.setMinFreeSpacePerDriveInMebibytes(m0);
            info("t3 min_free_space_per_drive restored to " + DatabaseDescriptor.getMinFreeSpacePerDriveInMebibytes() + " MiB");
        }
        done("t3_clamp");
    }

    @Test
    public void t4_complete() throws Throwable
    {
        ColumnFamilyStore cfs = build(SSTABLES, ROWS, 4);
        STUB = -1;
        Set<SSTableReader> live = cfs.getLiveSSTables();
        long T = SSTableReader.getTotalBytes(live);
        LifecycleTransaction txn = cfs.getTracker().tryModify(live, OperationType.COMPACTION);
        CompactionAwareWriter writer = new DefaultCompactionWriter(cfs, cfs.getDirectories(), txn, txn.originals());
        int rows = 0;
        long nowInSec = FBUtilities.nowInSeconds();
        try (AbstractCompactionStrategy.ScannerList scanners = cfs.getCompactionStrategyManager().getScanners(txn.originals());
             CompactionController controller = new CompactionController(cfs, txn.originals(), cfs.gcBefore(nowInSec));
             CompactionIterator ci = new CompactionIterator(OperationType.COMPACTION, scanners.scanners, controller, nowInSec, nextTimeUUID()))
        {
            while (ci.hasNext())
                if (writer.append(ci.next()))
                    rows++;
        }
        writer.finish();
        long outLen = SSTableReader.getTotalBytes(cfs.getLiveSSTables());
        info("t4 stub off: partitions written " + rows + "; live " + cfs.getLiveSSTables().size() + "; output onDiskLength " + outLen + " against T " + T);
        check("t4 one output", 1, cfs.getLiveSSTables().size());
        check("t4 every partition written", SSTABLES * ROWS, rows);
        check("t4 rows readable", (long) SSTABLES * ROWS, execute("SELECT count(*) FROM %s").one().getLong("count"));
        check("t4 output length within 1 % of T (disjoint, incompressible)", true, Math.abs(outLen - T) <= T / 100);
        done("t4_complete");
    }

    @Test
    public void t5_flush() throws Throwable
    {
        createTable("CREATE TABLE %s (pk int PRIMARY KEY, v blob) WITH compression = {'enabled': false}");
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        cfs.disableAutoCompaction();
        Random r = new Random(5);
        for (int i = 0; i < ROWS; i++)
        {
            byte[] b = new byte[PAYLOAD];
            r.nextBytes(b);
            execute("INSERT INTO %s (pk, v) VALUES (?, ?)", i, ByteBuffer.wrap(b));
        }
        Throwable failure = null;
        STUB = 1;
        try
        {
            cfs.forceFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS).get(120, TimeUnit.SECONDS);
        }
        catch (Throwable t)
        {
            failure = t;
        }
        finally
        {
            STUB = -1;
        }
        boolean diskFull = false;
        for (Throwable t = failure; t != null; t = t.getCause())
            if (t instanceof FSDiskFullWriteError)
                diskFull = true;
        info("t5 flush with stub 1: failure=" + failure + "; FSDiskFullWriteError in the chain " + diskFull + "; live " + cfs.getLiveSSTables().size());
        check("t5 flush refused by getWriteableLocation (FSDiskFullWriteError) iff the guarded path", BOP, diskFull);
        check("t5 flushed SSTables", BOP ? 0 : 1, cfs.getLiveSSTables().size());
        done("t5_flush");
    }
}
