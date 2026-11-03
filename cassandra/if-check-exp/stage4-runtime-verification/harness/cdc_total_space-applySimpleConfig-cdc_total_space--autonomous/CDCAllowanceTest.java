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

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.lang.reflect.Method;
import java.nio.ByteBuffer;
import java.util.HashSet;
import java.util.Random;
import java.util.Set;
import java.util.concurrent.ExecutionException;
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
import org.apache.cassandra.exceptions.CDCWriteException;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.schema.TableMetadata;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

/**
 * Stage-4 unit tier (B2, as amended 2026-10-24) of the if-check-exp case
 * cdc_total_space-applySimpleConfig-cdc_total_space--autonomous. Not upstream.
 *
 * One JVM per scenario, chosen by system properties (pass with -Dtest.jvm.args):
 *   stage4.cdc.scenario  block | nonblock | ctl-plain | ctl-1024 | helper
 *   stage4.cdc.s         s in MiB (block/nonblock; ctl-plain uses 8, ctl-1024 uses 1024)
 *   stage4.out           file that receives every STAGE4 line
 * S = 1 MiB (setCommitLogSegmentSize(1), commit log restarted). Rows of 64 KiB random blobs, sync(true) after
 * every row, no forced recycle. After every row: links (CommitLog-*.log) and index files (*_cdc.idx) in cdc_raw,
 * counted separately, and deleted link names. updateCDCTotalSize() after every 16 rows.
 * The test records readings; it fails only if a setting did not take effect. Judging is done by the readings script.
 */
public class CDCAllowanceTest extends CQLTester
{
    private static final long MIB = 1L << 20;
    private static final int ROW = 64 * 1024;
    private static final Pattern COUNTER = Pattern.compile("Total CDC bytes on disk is (\\d+)");
    private static String scenario;
    private static int s;
    private static boolean blocking;
    private static PrintWriter out;
    private static final Random random = new Random(20261024L);

    @BeforeClass
    public static void setUpClass()
    {
        scenario = System.getProperty("stage4.cdc.scenario", "block");
        switch (scenario)
        {
            case "ctl-plain": s = 8; blocking = true; break;
            case "ctl-1024": s = 1024; blocking = true; break;
            case "nonblock": s = Integer.getInteger("stage4.cdc.s", 8); blocking = false; break;
            default: s = Integer.getInteger("stage4.cdc.s", 8); blocking = true; break;
        }
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
        ServerTestUtils.daemonInitialization();
        DatabaseDescriptor.setCDCEnabled(true);
        DatabaseDescriptor.setCommitLogSegmentSize(1);
        DatabaseDescriptor.setCDCTotalSpaceInMiB(s);
        DatabaseDescriptor.setCDCBlockWrites(blocking);
        CQLTester.setUpClass();
    }

    @Before
    public void beforeTest() throws Throwable
    {
        CommitLog.instance.stopUnsafe(true);
        for (File f : cdcFiles())
            f.deleteIfExists();
        CommitLog.instance.start();
        super.beforeTest();
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
    public void allowance() throws Throwable
    {
        long S = DatabaseDescriptor.getCommitLogSegmentSize();
        long A = DatabaseDescriptor.getCDCTotalSpace();
        emit("config scenario=" + scenario + " s=" + s + " blocking=" + blocking + " S=" + S + " A=" + A
             + " cdcEnabled=" + DatabaseDescriptor.isCDCEnabled() + " cdcDir=" + DatabaseDescriptor.getCDCLogLocation()
             + " segmentManager=" + CommitLog.instance.segmentManager.getClass().getSimpleName());
        assertEquals("commitlog_segment_size took effect", MIB, S);
        assertEquals("cdc_total_space took effect", s * MIB, A);
        assertEquals("cdc_block_writes took effect", blocking, DatabaseDescriptor.getCDCBlockWrites());
        assertTrue("segment manager is the CDC one", CommitLog.instance.segmentManager instanceof CommitLogSegmentManagerCDC);

        if ("helper".equals(scenario))
        {
            helper();
            return;
        }

        boolean cdc = !"ctl-plain".equals(scenario);
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob) WITH cdc=" + cdc);
        TableMetadata table = Keyspace.open(keyspace()).getColumnFamilyStore(currentTable()).metadata();
        CommitLogSegmentManagerCDC mgr = (CommitLogSegmentManagerCDC) CommitLog.instance.segmentManager;
        mgr.awaitManagementTasksCompletion();

        long limitBytes = "ctl-1024".equals(scenario) ? 128 * MIB : 4L * s * MIB;
        long maxRows = limitBytes / ROW;
        Sample idle = new Sample(null);
        emit("idle " + idle);

        Set<String> prev = idle.names;
        Set<String> deleted = new HashSet<>();
        long maxLinkBytes = idle.linkBytes, maxLinks = idle.links, maxIdxBytes = idle.idxBytes;
        long accepted = 0, rejected = 0;
        String firstReject = null;
        for (long i = 0; i < maxRows; i++)
        {
            try
            {
                write(table, (int) i);
                accepted++;
                CommitLog.instance.sync(true);
            }
            catch (CDCWriteException e)
            {
                rejected++;
                if (firstReject == null)
                {
                    Sample at = new Sample(prev);
                    Matcher m = COUNTER.matcher(e.getMessage());
                    firstReject = "acceptedRows=" + accepted + " acceptedBytes=" + accepted * ROW + " links=" + at.links
                                  + " linkBytes=" + at.linkBytes + " idxBytes=" + at.idxBytes
                                  + " counterInMessage=" + (m.find() ? m.group(1) : "?");
                    emit("firstReject " + firstReject);
                    maxLinkBytes = Math.max(maxLinkBytes, at.linkBytes);
                    maxLinks = Math.max(maxLinks, at.links);
                    maxIdxBytes = Math.max(maxIdxBytes, at.idxBytes);
                }
                if (blocking)
                    break;   // B2c: blocking stops at the first exception
            }
            Sample now = new Sample(prev);
            for (String n : prev)
                if (!now.names.contains(n))
                {
                    deleted.add(n);
                    emit("linkDeleted row=" + i + " name=" + n);
                }
            prev = now.names;
            maxLinkBytes = Math.max(maxLinkBytes, now.linkBytes);
            maxLinks = Math.max(maxLinks, now.links);
            maxIdxBytes = Math.max(maxIdxBytes, now.idxBytes);
            emit("row " + i + " accepted=" + accepted + " " + now);
            if ((i + 1) % 16 == 0)
                emit("mib written=" + ((i + 1) * ROW / MIB) + " " + now + " counter=" + mgr.updateCDCTotalSize());
        }
        Sample end = new Sample(prev);
        emit("end " + end);
        String after = "";
        if ("ctl-plain".equals(scenario))
        {
            CommitLog.instance.forceRecycleAllSegments();
            mgr.awaitManagementTasksCompletion();
            Sample r = new Sample(null);
            after = " afterRecycleLinks=" + r.links + " afterRecycleLinkBytes=" + r.linkBytes;
            emit("afterRecycle " + r);
        }
        emit("RESULT scenario=" + scenario + " s=" + s + " blocking=" + blocking + " S=" + S + " A=" + A
             + " rowsTried=" + (accepted + rejected) + " accepted=" + accepted + " acceptedBytes=" + accepted * ROW
             + " rejected=" + rejected + " firstReject=" + (firstReject == null ? "none" : "[" + firstReject + "]")
             + " maxLinks=" + maxLinks + " maxLinkBytes=" + maxLinkBytes + " maxIdxBytes=" + maxIdxBytes
             + " linksDeleted=" + deleted.size() + " endLinks=" + end.links + " endLinkBytes=" + end.linkBytes + after);
    }

    private void helper() throws Exception
    {
        Method m = DatabaseDescriptor.class.getDeclaredMethod("calculateDefaultSpaceInMiB", String.class, String.class, String.class,
                                                              int.class, long.class, long.class, long.class);
        m.setAccessible(true);
        long[] totals = { 4L << 30, 100L << 30 };
        for (long t : totals)
        {
            int r = (Integer) m.invoke(null, "cdc", "/x", "cdc_total_space", 4096, t, 1L, 8L);
            emit("RESULT helper totalBytes=" + t + " result=" + r + " expected=" + Math.min(4096L, (t / MIB) / 8));
        }
    }

    private static void write(TableMetadata table, int k) throws Throwable
    {
        byte[] v = new byte[ROW];
        random.nextBytes(v);
        try
        {
            new RowUpdateBuilder(table, 0, k).add("v", ByteBuffer.wrap(v)).build().applyFuture().get();
        }
        catch (ExecutionException e)
        {
            if (e.getCause() instanceof CDCWriteException)
                throw e.getCause();
            throw e;
        }
    }

    private static File[] cdcFiles()
    {
        File[] f = new File(DatabaseDescriptor.getCDCLogLocation()).tryList();
        return f == null ? new File[0] : f;
    }

    private static final class Sample
    {
        long links, linkBytes, idx, idxBytes;
        final Set<String> names = new HashSet<>();

        Sample(Set<String> unused)
        {
            for (File f : cdcFiles())
            {
                if (CommitLogDescriptor.isValid(f.name()))
                {
                    links++;
                    linkBytes += f.length();
                    names.add(f.name());
                }
                else if (f.name().endsWith("_cdc.idx"))
                {
                    idx++;
                    idxBytes += f.length();
                }
            }
        }

        public String toString()
        {
            return "links=" + links + " linkBytes=" + linkBytes + " idx=" + idx + " idxBytes=" + idxBytes;
        }
    }

    private static void emit(String line)
    {
        String l = "STAGE4 " + System.currentTimeMillis() + " " + line;
        System.out.println(l);
        if (out != null)
            out.println(l);
    }
}
