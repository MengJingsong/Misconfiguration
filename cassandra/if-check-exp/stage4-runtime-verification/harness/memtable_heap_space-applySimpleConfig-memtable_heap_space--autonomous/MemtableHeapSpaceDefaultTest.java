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

import org.apache.cassandra.config.DatabaseDescriptor;

/** Stage-4 harness, B2e step 4 (amended 2026-10-24): memtable_heap_space unset, junit fork -Xmx1024m, own JVM. */
public class MemtableHeapSpaceDefaultTest
{
    static void out(String s) throws IOException
    {
        System.out.println("STAGE4 " + s);
        String f = System.getProperty("stage4.out");
        if (f != null) try (FileWriter w = new FileWriter(f, true)) { w.write("STAGE4 " + s + "\n"); }
    }

    @Test
    public void unset() throws Exception
    {
        long max = Runtime.getRuntime().maxMemory();
        DatabaseDescriptor.daemonInitialization();
        out("default maxMemory=" + max + " maxMemoryDiv4MiB=" + (max / (4 * 1048576L))
            + " getMemtableHeapSpaceInMiB=" + DatabaseDescriptor.getMemtableHeapSpaceInMiB());
    }
}
