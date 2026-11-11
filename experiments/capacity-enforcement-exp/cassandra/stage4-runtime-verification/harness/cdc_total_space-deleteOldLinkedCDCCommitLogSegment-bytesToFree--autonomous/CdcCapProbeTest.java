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
import java.util.concurrent.ExecutionException;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.After;
import org.junit.Before;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.ServerTestUtils;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.exceptions.CDCWriteException;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.schema.TableMetadata;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

/**
 * Unit tier of the stage-4 run for the if-check-exp case
 * cdc_total_space-deleteOldLinkedCDCCommitLogSegment-bytesToFree--autonomous (case file B2).
 *
 * Writes 8 MiB mutations (1/2 of max_mutation_size at 32 MiB segments) to a CDC-tracked table (or, as a control,
 * a non-CDC table) with nothing consuming cdc_raw, for a total of volumeMiB, and reads the real resource (the bytes
 * of the files in cdc_raw) with a 5 ms sampler plus a reading at each segment boundary. One JVM per cell.
 * Every reading is a STAGE4 line; the matching to the case's B2f/B2g rows is done afterwards from the raw lines
 * (unit-readings.py), not here. The only assertions are those that show the set-up took effect.
 *
 * Settings (system properties, via -Dtest.jvm.args):
 *   stage4.cdc.totalSpaceMiB  n in MiB (required)
 *   stage4.cdc.segmentMiB     segment size, default 32 (the unit yaml has 5)
 *   stage4.cdc.mode           blocking (default) | nonblocking
 *   stage4.cdc.enabled        true (default) | false  (the CDC-off control)
 *   stage4.cdc.table          cdc (default) | plain   (the non-CDC-table control)
 *   stage4.cdc.volumeMiB      attempted volume; default 3 x n
 *   stage4.cdc.rowMiB         row size, default 8
 *   stage4.cdc.sampleWaitMs   wait before each boundary reading (the "1 s wait" control), default 0
 *   stage4.unit.out           file that also receives every STAGE4 line
 *
 * Package org.apache.cassandra.db.commitlog because allocatingFrom() is package-private.
 */
public class CdcCapProbeTest extends CQLTester
{
    private static final long MIB = 1L << 20;

    private static int totalMiB;
    private static int segmentMiB;
    private static boolean blocking;
    private static boolean cdcEnabled;
    private static boolean cdcTable;
    private static int volumeMiB;
    private static int rowMiB;
    private static long sampleWaitMs;

    @BeforeClass
    public static void setUpClass()
    {
        String total = System.getProperty("stage4.cdc.totalSpaceMiB");
        if (total == null)
            throw new IllegalStateException("-Dstage4.cdc.totalSpaceMiB=<MiB> is required");
        totalMiB = Integer.parseInt(total);
        segmentMiB = Integer.getInteger("stage4.cdc.segmentMiB", 32);
        blocking = !"nonblocking".equals(System.getProperty("stage4.cdc.mode", "blocking"));
        cdcEnabled = !"false".equals(System.getProperty("stage4.cdc.enabled", "true"));
        cdcTable = !"plain".equals(System.getProperty("stage4.cdc.table", "cdc"));
        volumeMiB = Integer.getInteger("stage4.cdc.volumeMiB", 3 * totalMiB);
        rowMiB = Integer.getInteger("stage4.cdc.rowMiB", 8);
        sampleWaitMs = Long.getLong("stage4.cdc.sampleWaitMs", 0L);

        ServerTestUtils.daemonInitialization();
        DatabaseDescriptor.setCDCEnabled(cdcEnabled);
        DatabaseDescriptor.setCommitLogSegmentSize(segmentMiB);
        // The unit yaml derives max_mutation_size (2.5 MiB) from its 5 MiB segments at start-up; the setter above does not
        // update it. Set it to half of the segment, as a 32 MiB node has (DatabaseDescriptor.java:898-899).
        DatabaseDescriptor.getRawConfig().max_mutation_size = new org.apache.cassandra.config.DataStorageSpec.IntKibibytesBound(segmentMiB * 1024 / 2);
        DatabaseDescriptor.setCDCTotalSpaceInMiB(totalMiB);
        DatabaseDescriptor.setCDCBlockWrites(blocking);
        CQLTester.setUpClass();
    }

    @Before
    public void beforeTest() throws Throwable
    {
        CommitLog.instance.stopUnsafe(true);
        CommitLog.instance.start();
        super.beforeTest();
        if (cdcEnabled)
            ((CommitLogSegmentManagerCDC) CommitLog.instance.segmentManager).updateCDCTotalSize();
    }

    @After
    public void afterTest() throws Throwable
    {
        super.afterTest();
        CommitLog.instance.stopUnsafe(true);
        for (File f : cdcFiles())
            f.deleteIfExists();
    }

    @Test
    public void probe() throws Throwable
    {
        long S = DatabaseDescriptor.getCommitLogSegmentSize();
        long A = DatabaseDescriptor.getCDCTotalSpace();
        int rowBytes = rowMiB * (int) MIB;
        int rows = (volumeMiB + rowMiB - 1) / rowMiB;
        emit("config totalSpaceMiB=" + totalMiB + " segmentMiB=" + segmentMiB + " mode=" + (blocking ? "blocking" : "nonblocking")
             + " cdcEnabled=" + cdcEnabled + " table=" + (cdcTable ? "cdc" : "plain") + " S=" + S + " A=" + A + " volumeMiB=" + volumeMiB
             + " rowMiB=" + rowMiB + " rows=" + rows + " maxMutationSize=" + DatabaseDescriptor.getMaxMutationSize()
             + " sampleWaitMs=" + sampleWaitMs + " cdcDir=" + DatabaseDescriptor.getCDCLogLocation());
        assertEquals("commitlog_segment_size took effect", segmentMiB * MIB, S);
        assertEquals("cdc_total_space took effect", totalMiB * MIB, A);
        assertEquals("cdc_block_writes took effect", blocking, DatabaseDescriptor.getCDCBlockWrites());
        assertEquals("cdc_enabled took effect", cdcEnabled, DatabaseDescriptor.isCDCEnabled());
        assertTrue("row fits max_mutation_size", rowBytes + 1024 < DatabaseDescriptor.getMaxMutationSize());

        createTable("CREATE TABLE %s (id int PRIMARY KEY, payload blob) WITH cdc = true");
        TableMetadata cdcMeta = Keyspace.open(keyspace()).getColumnFamilyStore(currentTable()).metadata();
        createTable("CREATE TABLE %s (id int PRIMARY KEY, payload blob) WITH cdc = false");
        TableMetadata plainMeta = Keyspace.open(keyspace()).getColumnFamilyStore(currentTable()).metadata();
        TableMetadata target = cdcTable ? cdcMeta : plainMeta;

        CommitLogSegmentManagerCDC mgr = cdcEnabled ? (CommitLogSegmentManagerCDC) CommitLog.instance.segmentManager : null;
        Sampler sampler = new Sampler();
        sampler.start();
        byte[] payload = new byte[rowBytes];
        new java.util.Random(20261022L).nextBytes(payload);
        int accepted = 0, rejected = 0;
        String lastMessage = null;
        try
        {
            Thread.sleep(1000);
            emit("idle " + reading(mgr));
            CommitLogSegment lastSeg = CommitLog.instance.segmentManager.allocatingFrom();
            int boundaries = 0;
            for (int i = 0; i < rows; i++)
            {
                CommitLogSegment seg = CommitLog.instance.segmentManager.allocatingFrom();
                if (seg != lastSeg)
                {
                    lastSeg = seg;
                    boundaries++;
                    if (sampleWaitMs > 0)
                        Thread.sleep(sampleWaitMs);
                    emit("boundary n=" + boundaries + " before row " + i + " accepted=" + accepted + " rejected=" + rejected + " " + reading(mgr));
                }
                payload[0] = (byte) i; payload[1] = (byte) (i >> 8);
                boolean ok = true;
                try
                {
                    new RowUpdateBuilder(target, 0, i).add("payload", ByteBuffer.wrap(payload)).build().applyFuture().get();
                    accepted++;
                }
                catch (CDCWriteException e) // applyFuture() throws it directly when the segment is forbidden
                {
                    rejected++;
                    ok = false;
                    lastMessage = e.getMessage();
                }
                catch (ExecutionException e)
                {
                    if (!(e.getCause() instanceof CDCWriteException))
                        throw e;
                    rejected++;
                    ok = false;
                    lastMessage = e.getCause().getMessage();
                }
                emit("row i=" + i + " " + (ok ? "accepted" : "REJECTED") + " attemptedMiB=" + (long) (i + 1) * rowMiB + " " + reading(mgr));
            }
            emit("writesDone attempted=" + rows + " accepted=" + accepted + " rejected=" + rejected + " acceptedMiB=" + (long) accepted * rowMiB
                 + " lastMessage=\"" + lastMessage + "\"");
            Thread.sleep(2 * (DatabaseDescriptor.getCDCDiskCheckInterval() + 50L));
            emit("afterWait2Intervals " + reading(mgr));
            if (mgr != null)
                emit("afterUpdateCDCTotalSize allocatedSize=" + mgr.updateCDCTotalSize() + " " + reading(mgr));
            Thread.sleep(1000);
            emit("final " + reading(mgr));
            emit("listing " + names(cdcFilesAll()));
            emit("du " + duOut("du -sb " + DatabaseDescriptor.getCDCLogLocation()) + " | allocated " + duOut("du -s --block-size=1 " + DatabaseDescriptor.getCDCLogLocation()));
        }
        finally
        {
            sampler.finish();
        }
        emit("sampler peakLinks=" + sampler.peakLinks + " peakBytes=" + sampler.peakBytes + " peakLinkBytes=" + sampler.peakLinkBytes
             + " distinctLinksSeen=" + sampler.seen.size() + " ticks=" + sampler.ticks);
        emit("RESULT totalSpaceMiB=" + totalMiB + " mode=" + (blocking ? "blocking" : "nonblocking") + " cdcEnabled=" + cdcEnabled
             + " table=" + (cdcTable ? "cdc" : "plain") + " accepted=" + accepted + " rejected=" + rejected);
    }

    // ---------------------------------------------------------------- helpers

    private static File[] cdcFilesAll()
    {
        File[] files = new File(DatabaseDescriptor.getCDCLogLocation()).tryList();
        return files == null ? new File[0] : files;
    }

    private static File[] cdcFiles() { return cdcFilesAll(); }

    private static List<String> names(File[] files)
    {
        List<String> names = new ArrayList<>();
        for (File f : files)
            names.add(f.name() + ":" + f.length());
        Collections.sort(names);
        return names;
    }

    private static String duOut(String cmd)
    {
        try
        {
            Process p = new ProcessBuilder("bash", "-c", cmd).redirectErrorStream(true).start();
            String out = new String(p.getInputStream().readAllBytes()).trim();
            p.waitFor();
            return out.replace('\t', ' ');
        }
        catch (Exception e)
        {
            return "du failed: " + e;
        }
    }

    private static long counter(CommitLogSegmentManagerCDC mgr) throws Exception
    {
        Field trackerField = CommitLogSegmentManagerCDC.class.getDeclaredField("cdcSizeTracker");
        trackerField.setAccessible(true);
        Object tracker = trackerField.get(mgr);
        Field sizeField = tracker.getClass().getDeclaredField("sizeInProgress");
        sizeField.setAccessible(true);
        return ((AtomicLong) sizeField.get(tracker)).get();
    }

    /** One line: links, their bytes, index files and bytes, all bytes (du -sb equivalent), the tracker and the segment's state. */
    private static String reading(CommitLogSegmentManagerCDC mgr) throws Exception
    {
        int links = 0, idx = 0, other = 0;
        long linkBytes = 0, idxBytes = 0, all = 0;
        for (File f : cdcFilesAll())
        {
            long len = f.length();
            all += len;
            if (CommitLogDescriptor.isValid(f.name())) { links++; linkBytes += len; }
            else if (f.name().endsWith("_cdc.idx")) { idx++; idxBytes += len; }
            else other++;
        }
        String tracker = mgr == null ? "na" : Long.toString(counter(mgr));
        String state = mgr == null ? "na" : mgr.allocatingFrom().getCDCState().toString();
        return "links=" + links + " linkBytes=" + linkBytes + " idxFiles=" + idx + " idxBytes=" + idxBytes + " otherFiles=" + other
               + " duBytes=" + all + " tracker=" + tracker + " allocatingState=" + state;
    }

    /** Lists cdc_raw every 5 ms: peak link count, peak bytes of all files, every link name seen. */
    private static final class Sampler extends Thread
    {
        volatile boolean stop;
        volatile int peakLinks;
        volatile long peakBytes, peakLinkBytes, ticks;
        final java.util.Set<String> seen = java.util.concurrent.ConcurrentHashMap.newKeySet();

        Sampler() { super("stage4-cdc-sampler"); setDaemon(true); }

        public void run()
        {
            while (!stop)
            {
                int links = 0;
                long all = 0, lb = 0;
                for (File f : cdcFilesAll())
                {
                    long len = f.length();
                    all += len;
                    if (CommitLogDescriptor.isValid(f.name())) { links++; lb += len; seen.add(f.name()); }
                }
                peakLinks = Math.max(peakLinks, links);
                peakBytes = Math.max(peakBytes, all);
                peakLinkBytes = Math.max(peakLinkBytes, lb);
                ticks++;
                try { Thread.sleep(5); } catch (InterruptedException e) { return; }
            }
        }

        void finish() throws InterruptedException { stop = true; join(2000); }
    }

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
