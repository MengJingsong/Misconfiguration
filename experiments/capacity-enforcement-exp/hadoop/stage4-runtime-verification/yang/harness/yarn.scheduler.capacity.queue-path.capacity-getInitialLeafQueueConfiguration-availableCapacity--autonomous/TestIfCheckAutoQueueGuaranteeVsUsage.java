/*
 * Stage-4 harness, if-check-exp (Hadoop, Yang's share).
 * Case: yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous
 * The test of case-file B2e step 1, as filed, plus the print lines of amendment A2 (u3's app state
 * and the used memory of every created leaf at the end; u4/u5 usage in U2). Copied into the
 * per-case source copy only, never into the repository's systems/hadoop/source/.
 */
package org.apache.hadoop.yarn.server.resourcemanager.scheduler.capacity;

import java.util.ArrayList;

import org.apache.hadoop.yarn.conf.YarnConfiguration;
import org.apache.hadoop.yarn.server.resourcemanager.MockAM;
import org.apache.hadoop.yarn.server.resourcemanager.MockNM;
import org.apache.hadoop.yarn.server.resourcemanager.MockRM;
import org.apache.hadoop.yarn.server.resourcemanager.MockRMAppSubmissionData;
import org.apache.hadoop.yarn.server.resourcemanager.MockRMAppSubmitter;
import org.apache.hadoop.yarn.server.resourcemanager.rmapp.RMApp;
import org.apache.hadoop.yarn.server.resourcemanager.rmapp.RMAppState;
import org.apache.hadoop.yarn.server.resourcemanager.rmapp.attempt.RMAppAttempt;
import org.apache.hadoop.yarn.server.resourcemanager.rmapp.attempt.RMAppAttemptState;
import org.apache.hadoop.yarn.server.resourcemanager.scheduler.QueueMetrics;
import org.apache.hadoop.yarn.server.resourcemanager.scheduler.ResourceScheduler;
import org.apache.hadoop.yarn.server.resourcemanager.scheduler.capacity.queuemanagement.GuaranteedOrZeroCapacityOverTimePolicy;
import org.junit.Test;

public class TestIfCheckAutoQueueGuaranteeVsUsage {
  static final int GB = 1024;

  void runCase(String id, float P, float T, float M, String[] users) throws Exception {
    QueueMetrics.clearQueueMetrics();
    CapacitySchedulerConfiguration conf = new CapacitySchedulerConfiguration();
    conf.setClass(YarnConfiguration.RM_SCHEDULER, CapacityScheduler.class, ResourceScheduler.class);
    conf.set("yarn.scheduler.capacity.root.queues", "default,parent");
    conf.set("yarn.scheduler.capacity.root.default.capacity", Float.toString(100f - P));
    conf.set("yarn.scheduler.capacity.root.parent.capacity", Float.toString(P));
    conf.set("yarn.scheduler.capacity.root.parent.auto-create-child-queue.enabled", "true");
    conf.set("yarn.scheduler.capacity.root.parent.leaf-queue-template.capacity", Float.toString(T));
    conf.set("yarn.scheduler.capacity.root.parent.leaf-queue-template.maximum-capacity", Float.toString(M));
    conf.set("yarn.scheduler.capacity.root.parent.leaf-queue-template.user-limit-factor", "100");
    conf.set("yarn.scheduler.capacity.queue-mappings", "u:%user:root.parent.%user");
    conf.setBoolean("yarn.scheduler.capacity.queue-mappings-override.enable", true);
    conf.setInt(YarnConfiguration.RM_SCHEDULER_MINIMUM_ALLOCATION_MB, GB);
    MockRM rm = new MockRM(conf);
    try {
      rm.start();
      MockNM nm = rm.registerNode("h1:1234", 100 * GB, 100);
      CapacityScheduler cs = (CapacityScheduler) rm.getResourceScheduler();
      ManagedParentQueue parent = (ManagedParentQueue) cs.getQueue("root.parent");
      GuaranteedOrZeroCapacityOverTimePolicy pol =
          (GuaranteedOrZeroCapacityOverTimePolicy) parent.getAutoCreatedQueueManagementPolicy();
      RMApp u3App = null;
      for (String u : users) {
        float avail = parent.getQueueCapacities().getAbsoluteCapacity("")
            - pol.getAbsoluteActivatedChildQueueCapacity("") + CSQueueUtils.EPSILON;
        RMApp app = MockRMAppSubmitter.submit(rm, MockRMAppSubmissionData.Builder
            .createWithMemory(GB, rm).withUser(u).withQueue("default").withAcls(null).build());
        AutoCreatedLeafQueue leaf = (AutoCreatedLeafQueue) cs.getQueue("root.parent." + u);
        System.out.printf("IFCHK\t%s\tcreate\t%s\tavail=%.4f\tleafAbsCap=%.4f\tactive=%b\tactSum=%.4f\teffMaxMB=%d%n",
            id, u, avail, leaf.getQueueCapacities().getAbsoluteCapacity(), pol.isActive(leaf, ""),
            pol.getAbsoluteActivatedChildQueueCapacity(""),
            leaf.getQueueResourceQuotas().getEffectiveMaxResource().getMemorySize());
        if (u.equals("u3")) u3App = app;
      }
      // A9 (runbook defect 1): MockRM.launchAndRegisterAM sends two heartbeats, which go to u1's and
      // u2's AMs; heartbeat until u3's attempt is ALLOCATED, then launch and register it.
      RMAppAttempt att = MockRM.waitForAttemptScheduled(u3App, rm);
      int amHb = 0;
      while (att.getAppAttemptState() != RMAppAttemptState.ALLOCATED && amHb < 20) {
        nm.nodeHeartbeat(true);
        rm.drainEvents();
        amHb++;
      }
      System.out.printf("IFCHK\t%s\tamAlloc\theartbeats=%d\tu3AttemptState=%s%n", id, amHb,
          att.getAppAttemptState());
      MockAM am = rm.sendAMLaunched(att.getAppAttemptId());
      am.registerAppAttempt();
      rm.waitForState(u3App.getApplicationId(), RMAppState.RUNNING);
      am.allocate("*", GB, 40, new ArrayList<>());
      for (int i = 1; i <= 80; i++) {
        nm.nodeHeartbeat(true);
        Thread.sleep(50);
        if (i % 10 == 0) for (String u : users)   // A2: all created leaves (u1..u3; u1..u5 in U2)
          System.out.printf("IFCHK\t%s\tusage\thb=%d\t%s\tusedMB=%d\tparentUsedMB=%d%n", id, i, u,
              cs.getQueue("root.parent." + u).getQueueResourceUsage().getUsed().getMemorySize(),
              parent.getQueueResourceUsage().getUsed().getMemorySize());
      }
      // A2: u3's app state and every leaf's used memory at the end.
      StringBuilder end = new StringBuilder();
      for (String u : users)
        end.append(String.format("\t%s=%d", u,
            cs.getQueue("root.parent." + u).getQueueResourceUsage().getUsed().getMemorySize()));
      System.out.printf("IFCHK\t%s\tend\tu3AppState=%s\tparentUsedMB=%d%s%n", id,
          rm.getRMContext().getRMApps().get(u3App.getApplicationId()).getState(),
          parent.getQueueResourceUsage().getUsed().getMemorySize(), end);
    } finally {
      rm.stop();
    }
  }

  @Test public void u1() throws Exception { runCase("U1", 20, 50, 100, new String[]{"u1", "u2", "u3"}); }
  @Test public void u2() throws Exception { runCase("U2", 20, 25, 100, new String[]{"u1", "u2", "u3", "u4", "u5"}); }
  @Test public void u3() throws Exception { runCase("U3", 40, 50, 100, new String[]{"u1", "u2", "u3"}); }
  @Test public void u4() throws Exception { runCase("U4", 20, 50, 25, new String[]{"u1", "u2", "u3"}); }
}
