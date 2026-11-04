// B2e of cases/repair_state_size-setRepairStateSize-size--autonomous.md as amended 2026-10-26 (step-0 audit):
// the filed skeleton, with System.out.printf replaced by one System.out.println per reading (the unit JVM routes stdout to the
// logger, which splits a printf into pieces), each line prefixed "RSS ", plus the B2e amendment's two extra setter calls
// (a repeated value, to exercise the false branch of line 5070) and the count of registrations per arm.
package org.apache.cassandra.service;

import java.util.*;
import org.junit.*;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.repair.state.CoordinatorState;
import org.apache.cassandra.repair.messages.RepairOption;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.utils.Clock;
import org.apache.cassandra.utils.ObjectSizes;

public class RepairStateSizeTest {
  @BeforeClass public static void init() { org.apache.cassandra.ServerTestUtils.daemonInitialization(); }
  static long retained(ActiveRepairService s) throws Exception {
    java.lang.reflect.Field f = ActiveRepairService.class.getDeclaredField("repairs"); f.setAccessible(true);
    ((com.google.common.cache.Cache<?, ?>) f.get(s)).cleanUp(); return s.coordinators().size();
  }
  @Test public void size() throws Exception {
    System.out.println("RSS start getter=" + DatabaseDescriptor.getRepairStateSize());
    for (int S : new int[]{10, 100, 1000, 100000}) {
      DatabaseDescriptor.setRepairStateSize(S);
      ActiveRepairService svc = new ActiveRepairService();
      int n = 0;
      for (int i = 0; i < 5000; i++) {
        svc.register(new CoordinatorState(Clock.Global.clock(), i, "ks", RepairOption.parse(new HashMap<>(), Murmur3Partitioner.instance)));
        n++;
      }
      System.out.println(String.format("RSS S=%d registered=%d retained=%d bytes=%d", S, n, retained(svc), ObjectSizes.measureDeep(new ArrayList<>(svc.coordinators()))));
    }
    DatabaseDescriptor.setRepairStateSize(100);
    ActiveRepairService svc = new ActiveRepairService();
    DatabaseDescriptor.setRepairStateSize(100000);
    for (int i = 0; i < 5000; i++)
      svc.register(new CoordinatorState(Clock.Global.clock(), i, "ks", RepairOption.parse(new HashMap<>(), Murmur3Partitioner.instance)));
    System.out.println(String.format("RSS postConstructionSet retained=%d getter=%d", retained(svc), DatabaseDescriptor.getRepairStateSize()));
    DatabaseDescriptor.setRepairStateSize(100000);   // same value: line 5070 false, no "Setting repair_state_size" line
    System.out.println("RSS sameValueSet getter=" + DatabaseDescriptor.getRepairStateSize());
  }
}
