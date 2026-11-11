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
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;

/** Stage-4 harness, B2e step 3 (amended 2026-10-24): memtable_heap_space: 0MiB at daemonInitialization, own JVM. */
public class MemtableHeapSpaceZeroTest
{
    static void out(String s) throws IOException
    {
        System.out.println("STAGE4 " + s);
        String f = System.getProperty("stage4.out");
        if (f != null) try (FileWriter w = new FileWriter(f, true)) { w.write("STAGE4 " + s + "\n"); }
    }

    @Test
    public void zero() throws Exception
    {
        Config c = DatabaseDescriptor.loadConfig();
        out("zero yamlValueBefore=" + c.memtable_heap_space);
        c.memtable_heap_space = new DataStorageSpec.IntMebibytesBound("0MiB");
        try
        {
            DatabaseDescriptor.daemonInitialization(() -> c);
            out("zero accepted getMemtableHeapSpaceInMiB=" + DatabaseDescriptor.getMemtableHeapSpaceInMiB());
        }
        catch (Throwable t)
        {
            for (Throwable e = t; e != null; e = e.getCause())
                out("zero exception class=" + e.getClass().getName() + " message=" + e.getMessage());
        }
    }
}
