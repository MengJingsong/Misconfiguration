/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package org.apache.cassandra.db.commitlog;

import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Random;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.atomic.AtomicLong;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.junit.After;
import org.junit.Before;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.ServerTestUtils;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.db.commitlog.CommitLogSegment.CDCState;
import org.apache.cassandra.exceptions.CDCWriteException;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.schema.TableMetadata;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

/**
 * Unit tier of the stage-4 run for the if-check-exp case
 * cdc_total_space-processNewSegment-allowance (case file §9e).
 *
 * Writes 1 MiB CDC-tracked rows with nothing consuming cdc_raw and reads the real resource, the
 * files in cdc_raw, at the points the case's §9a names. One JVM per value.
 *
 * Blocking mode (default): writes until the first CDCWriteException and checks
 *   - the link count L is k = floor(A / S) (k - 1 or k when A is an exact multiple of S);
 *   - every link is S bytes, and the counter printed in the message is within L*S .. L*S + 64*L;
 *   - ten more writes are all rejected and nothing in cdc_raw changes; a non-CDC write succeeds;
 *   - after the links are deleted (a consumer) a CDC write is accepted again.
 * Non-blocking mode: writes until at least k + 10 distinct links have existed and checks no rejection,
 * L <= k + 1 at every sample (5 ms background sampler), the first link deleted, final L <= k + 1.
 *
 * A check that does not hold is RECORDED ("check MISMATCH ...") and the test goes on, so every later step
 * still produces its readings; the test fails at the end if any check was a mismatch. Only a broken setup
 * (a setting that did not take effect, no rejection at all) stops the test at once. Every link that appears
 * or disappears is logged with its time ("linkEvent"), so the analysis can set the check's counter (the
 * Byteman trace) against the files that existed at each segment creation.
 *
 * Settings, all system properties (pass them with -Dtest.jvm.args):
 *   stage4.cdc.totalSpaceMiB  A in MiB (required)
 *   stage4.cdc.segmentMiB     S in MiB, default 32. The unit yaml has 5 MiB; the node default is 32.
 *   stage4.cdc.mode           blocking (default) | nonblocking
 *   stage4.unit.out           optional file that also receives every STAGE4 line
 *
 * Package org.apache.cassandra.db.commitlog because awaitManagementTasksCompletion() and allocatingFrom()
 * are package-private. Not upstream; run it from a local clone of cassandra-5.0.9, never the shared one.
 */
public class CdcTotalSpaceCeilingTest extends CQLTester
{
    private static final long MIB = 1L << 20;
    private static final int ROW_BYTES = (int) MIB;
    private static final Pattern COUNTER_IN_MESSAGE = Pattern.compile("Total CDC bytes on disk is (\\d+)");

    private static int totalMiB;
    private static int segmentMiB;
    private static boolean blocking;
    private static final Random random = new Random(20261001L);
    private final List<String> mismatches = new ArrayList<>();

    @BeforeClass
    public static void setUpClass()
    {
        String total = System.getProperty("stage4.cdc.totalSpaceMiB");
        if (total == null)
            throw new IllegalStateException("-Dstage4.cdc.totalSpaceMiB=<MiB> is required");
        totalMiB = Integer.parseInt(total);
        segmentMiB = Integer.getInteger("stage4.cdc.segmentMiB", 32);
        blocking = !"nonblocking".equals(System.getProperty("stage4.cdc.mode", "blocking"));

        ServerTestUtils.daemonInitialization();
        DatabaseDescriptor.setCDCEnabled(true);
        // The unit yaml has commitlog_segment_size 5MiB; the node default is 32MiB and the cluster tier uses it,
        // so both tiers share k for each A. Set before the commit log starts (DatabaseDescriptor.java:2887).
        DatabaseDescriptor.setCommitLogSegmentSize(segmentMiB);
        DatabaseDescriptor.setCDCTotalSpaceInMiB(totalMiB);
        DatabaseDescriptor.setCDCBlockWrites(blocking);
        CQLTester.setUpClass();
    }

    @Before
    public void beforeTest() throws Throwable
    {
        // Anything the commit log made before the setters above has the yaml's segment size; start afresh.
        CommitLog.instance.stopUnsafe(true);
        CommitLog.instance.start();
        super.beforeTest();
        ((CommitLogSegmentManagerCDC) CommitLog.instance.segmentManager).updateCDCTotalSize();
    }

    @After
    public void afterTest() throws Throwable
    {
        super.afterTest();
        CommitLog.instance.stopUnsafe(true);
        for (File f : allCdcFiles())
            f.deleteIfExists();
    }

    @Test
    public void ceilingHolds() throws Throwable
    {
        CommitLogSegmentManagerCDC mgr = (CommitLogSegmentManagerCDC) CommitLog.instance.segmentManager;
        long S = DatabaseDescriptor.getCommitLogSegmentSize();
        long A = DatabaseDescriptor.getCDCTotalSpace();
        long k = A / S;
        boolean multiple = A % S == 0;
        emit("config totalSpaceMiB=" + totalMiB + " segmentMiB=" + segmentMiB + " mode=" + (blocking ? "blocking" : "nonblocking")
             + " S=" + S + " A=" + A + " k=" + k + " exactMultiple=" + multiple + " rowBytes=" + ROW_BYTES
             + " cdcDir=" + DatabaseDescriptor.getCDCLogLocation());
        assertEquals("commitlog_segment_size took effect", segmentMiB * MIB, S);
        assertEquals("cdc_total_space took effect", totalMiB * MIB, A);
        assertEquals("cdc_block_writes took effect", blocking, DatabaseDescriptor.getCDCBlockWrites());
        assertTrue("cdc_enabled", DatabaseDescriptor.isCDCEnabled());

        createTable("CREATE TABLE %s (id int PRIMARY KEY, payload blob) WITH cdc = true");
        TableMetadata cdcTable = Keyspace.open(keyspace()).getColumnFamilyStore(currentTable()).metadata();
        createTable("CREATE TABLE %s (id int PRIMARY KEY, payload blob) WITH cdc = false");
        TableMetadata plainTable = Keyspace.open(keyspace()).getColumnFamilyStore(currentTable()).metadata();

        // The 5 ms sampler logs every link that appears or disappears, from here to the end, in both modes.
        Sampler sampler = new Sampler();
        sampler.start();
        try
        {
            // Control: the idle floor, once the segment prepared ahead exists.
            mgr.awaitManagementTasksCompletion();
            Thread.sleep(1000);
            Reading idle = read(mgr, S);
            emit("idle " + idle);
            expect(idle.links == Math.min(k, 2), "idle floor is min(k, 2) = " + Math.min(k, 2) + " links, got " + idle.links);

            if (blocking)
                blockingArm(mgr, cdcTable, plainTable, S, A, k, multiple, sampler);
            else
                nonBlockingArm(mgr, cdcTable, S, A, k, sampler);
        }
        finally
        {
            sampler.finish();
        }
        emit("RESULT mismatches=" + mismatches.size() + " totalSpaceMiB=" + totalMiB + " segmentMiB=" + segmentMiB
             + " mode=" + (blocking ? "blocking" : "nonblocking") + (mismatches.isEmpty() ? "" : " " + mismatches));
        assertTrue("checks that did not hold (each is a reading, see the STAGE4 lines): " + mismatches, mismatches.isEmpty());
    }

    private void blockingArm(CommitLogSegmentManagerCDC mgr, TableMetadata cdcTable, TableMetadata plainTable,
                             long S, long A, long k, boolean multiple, Sampler sampler) throws Throwable
    {
        // A: write until the first rejection. Invalid run if there is none within (k + 4) segments' worth of rows.
        int maxRows = (int) ((k + 4) * (S / ROW_BYTES)) + 50;
        int accepted = 0;
        String message = null;
        for (int i = 0; i < maxRows; i++)
        {
            try
            {
                write(cdcTable, i);
                accepted++;
            }
            catch (CDCWriteException e)
            {
                message = e.getMessage();
                break;
            }
        }
        Reading first = read(mgr, S);
        emit("firstRejection accepted=" + accepted + " " + first + " message=\"" + message + "\"");
        assertNotNull("invalid run: no rejection within " + maxRows + " rows (limit never reached)", message);
        expect(message.startsWith("Rejecting mutation to keyspace"), "the message is the check's: " + message);
        Matcher m = COUNTER_IN_MESSAGE.matcher(message);
        assertTrue("the message carries the counter: " + message, m.find());
        long counter = Long.parseLong(m.group(1));
        emit("rejectionCounter N=" + counter + " linkBytes=" + first.linkBytes + " N-linkBytes=" + (counter - first.linkBytes));
        expect(first.state == CDCState.FORBIDDEN, "segment state at the first rejection is FORBIDDEN, got " + first.state);
        expectLinks("links at the first rejection", first.links, k, multiple);
        expect(first.everyLinkIsS, "every link is S bytes");
        expect(first.links * S == first.linkBytes, "apparent bytes are L x S: " + first.linkBytes);
        expect(counter >= first.links * S && counter <= first.links * S + 64L * Math.max(first.links, 1),
               "N = " + counter + " within L*S .. L*S + 64*L (L = " + first.links + ")");

        // B: ten more tries are all rejected and nothing in cdc_raw changes.
        int rejected = 0;
        for (int i = 0; i < 10; i++)
        {
            try
            {
                write(cdcTable, 100_000 + i);
                fail("a CDC write was accepted after the limit, row " + i);
            }
            catch (CDCWriteException e)
            {
                rejected++;
            }
        }
        Thread.sleep(1000); // at least one directory walk (250 ms interval) after the last rejection
        Reading later = read(mgr, S);
        emit("afterTenMore rejected=" + rejected + " " + later);
        expect(first.links == later.links, "links unchanged after ten more rejections: " + first.links + " then " + later.links);
        expect(first.linkBytes == later.linkBytes, "link bytes unchanged after ten more rejections");
        expect(later.state == CDCState.FORBIDDEN, "segment still forbidden, got " + later.state);

        // Control: a non-CDC write is accepted at the limit.
        write(plainTable, 1);
        emit("nonCdcWrite accepted=true");

        // Release: a consumer deletes every file in cdc_raw; the writer must resume without a restart.
        if (k == 0)
        {
            emit("release skipped: k = 0, a segment can never be permitted");
            return;
        }
        File[] before = allCdcFiles();
        long t0 = System.nanoTime();
        for (File f : before)
            f.deleteIfExists();
        emit("release consumerDeleted=" + before.length + " files");
        int rejectedBefore = 0;
        boolean resumed = false;
        while (System.nanoTime() - t0 < 10_000_000_000L)
        {
            try
            {
                write(cdcTable, 200_000 + rejectedBefore);
                resumed = true;
                break;
            }
            catch (CDCWriteException e)
            {
                rejectedBefore++;
                Thread.sleep(100);
            }
        }
        long ms = (System.nanoTime() - t0) / 1_000_000L;
        Reading after = read(mgr, S);
        emit("release resumed=" + resumed + " afterMs=" + ms + " rejectedBefore=" + rejectedBefore + " " + after);
        expect(resumed, "the writer resumed within 10 s of the links being deleted");
    }

    private void nonBlockingArm(CommitLogSegmentManagerCDC mgr, TableMetadata cdcTable, long S, long A, long k, Sampler sampler) throws Throwable
    {
        int maxRows = (int) ((k + 12) * (S / ROW_BYTES)) + 100;
        int written = 0;
        boolean rejected = false;
        for (int i = 0; i < maxRows && sampler.seen.size() < k + 10; i++)
        {
            try
            {
                write(cdcTable, i);
                written++;
            }
            catch (CDCWriteException e)
            {
                rejected = true;
                emit("nonBlocking REJECTED at row " + i + ": " + e.getMessage());
                break;
            }
        }
        Thread.sleep(1000);
        List<String> seen = new ArrayList<>(sampler.seen);
        Collections.sort(seen);
        List<String> finalLinks = names(links());
        Reading end = read(mgr, S);
        int deleted = 0;
        for (String name : seen)
            if (!finalLinks.contains(name))
                deleted++;
        emit("nonBlocking rowsWritten=" + written + " distinctLinksSeen=" + seen.size() + " maxLinks=" + sampler.maxLinks
             + " finalLinks=" + finalLinks.size() + " deletedLinks=" + deleted + " firstSeen=" + (seen.isEmpty() ? "-" : seen.get(0))
             + " firstStillPresent=" + (!seen.isEmpty() && finalLinks.contains(seen.get(0))) + " " + end);
        emit("nonBlocking bytesWritten=" + (long) written * ROW_BYTES + " bytesRetained=" + end.linkBytes);
        assertTrue("invalid run: fewer than k + 10 distinct links were made: " + seen.size(), seen.size() >= k + 10 || rejected);
        expect(!rejected, "no write was rejected in non-blocking mode");
        expect(sampler.maxLinks <= k + 1, "maximum L " + sampler.maxLinks + " is at most k + 1 = " + (k + 1));
        expect(!seen.isEmpty() && !finalLinks.contains(seen.get(0)), "the oldest link was deleted");
        expect(finalLinks.size() <= k + 1, "final L " + finalLinks.size() + " is at most k + 1");
        expect(deleted > 0, "links were deleted: " + deleted);
    }

    // ---------------------------------------------------------------- helpers

    /** Records a check: a mismatch is a reading, not a stop (see the class comment). */
    private void expect(boolean ok, String what) throws java.io.IOException
    {
        emit("check " + (ok ? "PASS" : "MISMATCH") + " " + what);
        if (!ok)
            mismatches.add(what);
    }

    private void expectLinks(String what, long links, long k, boolean multiple) throws java.io.IOException
    {
        if (multiple)
            expect(links == k - 1 || links == k, what + ": L = " + links + ", expected k - 1 or k (k = " + k + ", A an exact multiple of S)");
        else
            expect(links == k, what + ": L = " + links + ", expected k = " + k);
    }

    /** One 1 MiB CDC (or non-CDC) row. CDCWriteException is rethrown as itself, as the upstream test expects. */
    private static void write(TableMetadata table, int id) throws Throwable
    {
        byte[] payload = new byte[ROW_BYTES];
        random.nextBytes(payload);
        try
        {
            new RowUpdateBuilder(table, 0, id).add("payload", ByteBuffer.wrap(payload)).build().applyFuture().get();
        }
        catch (ExecutionException e)
        {
            if (e.getCause() instanceof CDCWriteException)
                throw e.getCause();
            throw e;
        }
    }

    private static File[] allCdcFiles()
    {
        File[] files = new File(DatabaseDescriptor.getCDCLogLocation()).tryList();
        return files == null ? new File[0] : files;
    }

    private static List<File> links()
    {
        File[] files = new File(DatabaseDescriptor.getCDCLogLocation()).tryList(f -> CommitLogDescriptor.isValid(f.name()));
        return files == null ? Collections.<File>emptyList() : Arrays.asList(files);
    }

    private static List<String> names(List<File> files)
    {
        List<String> names = new ArrayList<>();
        for (File f : files)
            names.add(f.name());
        Collections.sort(names);
        return names;
    }

    /** The check's counter, read by reflection (CommitLogSegmentManagerCDC.cdcSizeTracker.sizeInProgress, both private). */
    private static long counter(CommitLogSegmentManagerCDC mgr) throws Exception
    {
        Field trackerField = CommitLogSegmentManagerCDC.class.getDeclaredField("cdcSizeTracker");
        trackerField.setAccessible(true);
        Object tracker = trackerField.get(mgr);
        Field sizeField = tracker.getClass().getDeclaredField("sizeInProgress");
        sizeField.setAccessible(true);
        return ((AtomicLong) sizeField.get(tracker)).get();
    }

    private static final class Reading
    {
        final int links;
        final long linkBytes;
        final boolean everyLinkIsS;
        final int idxFiles;
        final long idxBytes;
        final long counter;
        final CDCState state;

        Reading(CommitLogSegmentManagerCDC mgr, long S) throws Exception
        {
            int n = 0, idx = 0;
            long bytes = 0, idxB = 0;
            boolean allS = true;
            for (File f : allCdcFiles())
            {
                if (CommitLogDescriptor.isValid(f.name()))
                {
                    n++;
                    bytes += f.length();
                    allS &= f.length() == S;
                }
                else if (f.name().endsWith("_cdc.idx"))
                {
                    idx++;
                    idxB += f.length();
                }
            }
            links = n;
            linkBytes = bytes;
            everyLinkIsS = allS;
            idxFiles = idx;
            idxBytes = idxB;
            counter = counter(mgr);
            state = mgr.allocatingFrom().getCDCState();
        }

        public String toString()
        {
            return "links=" + links + " linkBytes=" + linkBytes + " everyLinkIsS=" + everyLinkIsS + " idxFiles=" + idxFiles
                   + " idxBytes=" + idxBytes + " counter=" + counter + " allocatingState=" + state;
        }
    }

    private static Reading read(CommitLogSegmentManagerCDC mgr, long S) throws Exception
    {
        return new Reading(mgr, S);
    }

    /**
     * Lists cdc_raw every 5 ms; keeps the maximum link count and every link name ever seen, and logs each link
     * that appears or disappears ("linkEvent ms=... + name").
     */
    private static final class Sampler extends Thread
    {
        volatile boolean stop;
        volatile int maxLinks;
        final Set<String> seen = ConcurrentHashMap.newKeySet();

        Sampler()
        {
            super("stage4-cdc-sampler");
            setDaemon(true);
        }

        public void run()
        {
            Set<String> previous = new java.util.TreeSet<>();
            while (!stop)
            {
                Set<String> now = new java.util.TreeSet<>(names(links()));
                maxLinks = Math.max(maxLinks, now.size());
                seen.addAll(now);
                try
                {
                    for (String added : now)
                        if (!previous.contains(added))
                            emit("linkEvent + " + added);
                    for (String removed : previous)
                        if (!now.contains(removed))
                            emit("linkEvent - " + removed);
                    if (now.size() != previous.size())
                        emit("linkCount n=" + now.size()); // the count at this tick, so a same-tick add and remove is not read as a peak
                }
                catch (java.io.IOException e)
                {
                    throw new RuntimeException(e);
                }
                previous = now;
                try { Thread.sleep(5); }
                catch (InterruptedException e) { return; }
            }
        }

        void finish() throws InterruptedException
        {
            stop = true;
            join(2000);
        }
    }

    /** Prints a line, and appends it to stage4.unit.out if set. */
    private static synchronized void emit(String line) throws java.io.IOException
    {
        String stamped = "ms=" + System.currentTimeMillis() + " " + line;
        System.out.println("STAGE4 " + stamped);
        String out = System.getProperty("stage4.unit.out");
        if (out != null)
        {
            try (java.io.FileWriter writer = new java.io.FileWriter(out, true))
            {
                writer.write(stamped + "\n");
            }
        }
    }
}
