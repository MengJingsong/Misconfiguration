/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
package org.apache.cassandra.utils.memory;

import java.io.FileWriter;
import java.io.IOException;

import org.junit.Test;

import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.memtable.AbstractAllocatorMemtable;

/**
 * Stage-4 harness, unit tier B2b config-path case (amended 2026-10-24) of
 * memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous: memtable_cleanup_threshold = 0.995
 * through DatabaseDescriptor.daemonInitialization, in its own JVM (own ant testsome). Records; never fails on a mismatch.
 */
public class CleanupThresholdHighTest
{
    static final float VALUE = 0.995f;

    static synchronized void out(String s)
    {
        String line = "STAGE4 " + s;
        System.out.println(line);
        String f = System.getProperty("stage4.out");
        if (f != null)
            try (FileWriter w = new FileWriter(f, true)) { w.write(line + "\n"); }
            catch (IOException e) { throw new RuntimeException(e); }
    }

    @Test
    public void configPath()
    {
        String label = "config/" + VALUE;
        try
        {
            DatabaseDescriptor.daemonInitialization(() -> {
                Config c = DatabaseDescriptor.loadConfig();
                c.memtable_cleanup_threshold = VALUE;
                return c;
            });
        }
        catch (Throwable t)
        {
            out(label + " result=threw class=" + t.getClass().getName() + " message=" + t.getMessage());
            return;
        }
        out(label + " result=initialised getMemtableCleanupThreshold=" + DatabaseDescriptor.getMemtableCleanupThreshold());
        MemtablePool p = AbstractAllocatorMemtable.MEMORY_POOL;
        out(label + " MEMORY_POOL=" + p.getClass().getSimpleName() + " onHeap.cleanThreshold=" + p.onHeap.cleanThreshold
            + " offHeap.cleanThreshold=" + p.offHeap.cleanThreshold + " onHeap.limit=" + p.onHeap.limit);
    }
}
