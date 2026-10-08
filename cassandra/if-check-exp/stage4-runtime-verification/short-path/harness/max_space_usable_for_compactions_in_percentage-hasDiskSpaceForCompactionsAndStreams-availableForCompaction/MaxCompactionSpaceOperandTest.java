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
package org.apache.cassandra.db;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.file.FileStore;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.junit.BeforeClass;
import org.junit.Test;
import org.slf4j.LoggerFactory;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.io.util.FileUtils;

import static org.junit.Assert.assertTrue;

/**
 * Stage-4 short-path unit tier (B2) for max_space_usable_for_compactions_in_percentage.
 * Drives Directories.getAvailableSpaceForCompactions / hasDiskSpaceForCompactionsAndStreams with a
 * DirectoriesTest.FakeFileStore of fixed usableSpace, minFree=0, pct in {1.0, 0.95, 0.5, 0.0} (B2b/B2c),
 * plus the B2h control with a second usableSpace (10,000,000). Every reading is written as a READING line to
 * System.out and to the file named by env READINGS_OUT; mismatches are collected and asserted at the end so
 * that one wrong value does not hide the others.
 */
public class MaxCompactionSpaceOperandTest
{
    private static final double[] PCTS = { 1.0, 0.95, 0.5, 0.0 };
    private static final List<String> mismatches = new ArrayList<>();
    private static PrintWriter out;

    @BeforeClass
    public static void beforeClass() throws IOException
    {
        DatabaseDescriptor.daemonInitialization();
        String path = System.getenv("READINGS_OUT");
        if (path != null)
            out = new PrintWriter(new FileWriter(path, true), true);
    }

    private static void reading(String line)
    {
        System.out.println("READING " + line);
        if (out != null)
            out.println("READING " + line);
    }

    private static void check(boolean ok, String what)
    {
        reading((ok ? "OK " : "MISMATCH ") + what);
        if (!ok)
            mismatches.add(what);
    }

    @Test
    public void budgetAndGateAcrossPercentages()
    {
        runSeries(1_000_000_000L);
        // B2h control: a second usableSpace; the budget must scale linearly with it.
        runSeries(10_000_000L);
        assertTrue("mismatches: " + mismatches, mismatches.isEmpty());
    }

    private void runSeries(long usableSpace)
    {
        double oldPct = DatabaseDescriptor.getMaxSpaceForCompactionsPerDrive();
        long oldFreeMiB = DatabaseDescriptor.getMinFreeSpacePerDriveInMebibytes();
        Logger logger = (Logger) LoggerFactory.getLogger(Directories.class);
        Level oldLevel = logger.getLevel();
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        logger.setLevel(Level.DEBUG);
        try
        {
            DatabaseDescriptor.setMinFreeSpacePerDriveInMebibytes(0);
            reading("minFreeBytes=" + DatabaseDescriptor.getMinFreeSpacePerDriveInBytes());
            DirectoriesTest.FakeFileStore fs = new DirectoriesTest.FakeFileStore();
            fs.usableSpace = usableSpace;
            for (double pct : PCTS)
            {
                DatabaseDescriptor.setMaxSpaceForCompactionsPerDrive(pct);
                long expected = Math.round(usableSpace * pct);
                long budget = Directories.getAvailableSpaceForCompactions(fs);
                reading(String.format("usable=%d pct=%s expected=%d budget=%d", usableSpace, pct, expected, budget));
                check(budget == expected, String.format("usable=%d pct=%s budget==round(usable*pct)", usableSpace, pct));

                // pct=0: request -1 is meaningless; B2f says use request 0 (must be true) and 1 (must be false).
                long under = expected > 0 ? expected - 1 : 0;
                long over = expected + 1;

                appender.list.clear();
                boolean underResult = Directories.hasDiskSpaceForCompactionsAndStreams(Map.of((FileStore) fs, under));
                List<ILoggingEvent> underLog = new ArrayList<>(appender.list);
                appender.list.clear();
                boolean overResult = Directories.hasDiskSpaceForCompactionsAndStreams(Map.of((FileStore) fs, over));
                List<ILoggingEvent> overLog = new ArrayList<>(appender.list);

                reading(String.format("usable=%d pct=%s request=%d hasSpace=%s", usableSpace, pct, under, underResult));
                reading(String.format("usable=%d pct=%s request=%d hasSpace=%s", usableSpace, pct, over, overResult));
                check(underResult, String.format("usable=%d pct=%s hasSpace(%d)==true", usableSpace, pct, under));
                check(!overResult, String.format("usable=%d pct=%s hasSpace(%d)==false", usableSpace, pct, over));

                for (ILoggingEvent e : underLog)
                    reading(String.format("usable=%d pct=%s request=%d LOG %s %s", usableSpace, pct, under, e.getLevel(), e.getFormattedMessage()));
                for (ILoggingEvent e : overLog)
                    reading(String.format("usable=%d pct=%s request=%d LOG %s %s", usableSpace, pct, over, e.getLevel(), e.getFormattedMessage()));

                // Log corroboration (B2d(3)): DEBUG carries the exact budget in bytes; WARN fires only over budget,
                // with the stringified budget and request.
                String debugUnder = "FileStore MockFileStore has " + expected + " bytes available, checking if we can write " + under + " bytes";
                String debugOver = "FileStore MockFileStore has " + expected + " bytes available, checking if we can write " + over + " bytes";
                String warnOver = "FileStore MockFileStore has only " + FileUtils.stringifyFileSize(expected) + " available, but "
                                  + FileUtils.stringifyFileSize(over) + " is needed";
                check(count(underLog, Level.DEBUG, debugUnder) == 1, String.format("usable=%d pct=%s DEBUG line for request %d shows budget %d", usableSpace, pct, under, expected));
                check(count(underLog, Level.WARN, null) == 0, String.format("usable=%d pct=%s no WARN for request %d", usableSpace, pct, under));
                check(count(overLog, Level.DEBUG, debugOver) == 1, String.format("usable=%d pct=%s DEBUG line for request %d shows budget %d", usableSpace, pct, over, expected));
                check(count(overLog, Level.WARN, warnOver) == 1, String.format("usable=%d pct=%s WARN line for request %d shows budget %s", usableSpace, pct, over, FileUtils.stringifyFileSize(expected)));
            }
        }
        finally
        {
            logger.detachAppender(appender);
            logger.setLevel(oldLevel);
            DatabaseDescriptor.setMaxSpaceForCompactionsPerDrive(oldPct);
            DatabaseDescriptor.setMinFreeSpacePerDriveInMebibytes(oldFreeMiB);
        }
    }

    private static int count(List<ILoggingEvent> log, Level level, String message)
    {
        int n = 0;
        for (ILoggingEvent e : log)
            if (e.getLevel() == level && (message == null || e.getFormattedMessage().equals(message)))
                n++;
        return n;
    }
}
