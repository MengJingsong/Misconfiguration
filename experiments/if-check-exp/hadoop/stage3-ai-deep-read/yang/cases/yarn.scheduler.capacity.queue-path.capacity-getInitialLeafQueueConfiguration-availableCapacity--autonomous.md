# yarn.scheduler.capacity.&lt;queue-path&gt;.capacity (managed parent queue's guaranteed capacity, compared against the summed guarantees of auto-created leaf queues) — verification solution  <!-- file: cases/yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`GuaranteedOrZeroCapacityOverTimePolicy.java:719`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/main/java/org/apache/hadoop/yarn/server/resourcemanager/scheduler/capacity/queuemanagement/GuaranteedOrZeroCapacityOverTimePolicy.java#L719-L720): `if (availableCapacity >= leafQueueTemplateCapacities.getAbsoluteCapacity(nodeLabel))`, in `getInitialLeafQueueConfiguration` |
| Pinned source | `rel/release-3.4.2` |
| Session / date | Claude Code autonomous agent, 2026-11-06 |
| Estimate | `negative`. The check decides only whether a new auto-created leaf queue gets the template's **guaranteed (minimum)** capacity or 0. The sum of those guarantees stays within the parent's capacity. The leaf queue's **maximum** capacity, which is what limits how much container memory it can hold, is copied from the template in both branches. A leaf that gets 0 can still start an application and grow it up to that maximum. |
| Ground | (1) This check limits a sum of guarantees, which are floors, not ceilings. The leaf's ceiling is `leaf-queue-template.maximum-capacity` × the parent's absolute max capacity. Both branches set it: `GuaranteedOrZeroCapacityOverTimePolicy.java:738-739` and `:748-749`, recomputed in `CSQueueUtils.java:319-323`, enforced in `AbstractCSQueue.java:788-802,831-857`. (2) A zero-guarantee leaf still runs work. Its AM limit falls back to the queue's current limit (`AbstractLeafQueue.java:812-814`). The first AM is always admitted (`AbstractLeafQueue.java:876-883`). Its user limit falls back to the queue's effective max when the guarantee is 0 (`UsersManager.java:790-798`). (3) The in-tree test asserts that the zero-capacity leaf USER3 keeps a non-zero effective max resource (`TestCapacitySchedulerAutoQueueCreation.java:842-867`). (4) The quantity involved is the scheduler's logical share of cluster container memory (NodeManager memory handed to containers). It is not a daemon's heap or disk. The check does not bound how many leaf queues exist, so it does not bound ResourceManager heap either; `auto-create-child-queue.max-queues` does that (`ManagedParentQueue.java:298-307`). |

> **File-name note.** The constraint name is the configuration key `yarn.scheduler.capacity.<queue-path>.capacity`.
> In the file stem it is written `yarn.scheduler.capacity.queue-path.capacity`, without the angle brackets,
> because `<` and `>` are not portable in file names. Hadoop keys already contain hyphens, so the stem's
> hyphen separators are ambiguous for this system. The three parts are:
> constraint = `yarn.scheduler.capacity.queue-path.capacity`, function = `getInitialLeafQueueConfiguration`,
> operand = `availableCapacity`.

## A. Constraint trace

**A1. The constraint.**

- **Name:** `yarn.scheduler.capacity.<queue-path>.capacity`, the guaranteed capacity of the parent queue that has legacy auto-creation enabled (a `ManagedParentQueue`).
- **Kind:** configuration entry in `capacity-scheduler.xml`.
- **Declaration:** the key is assembled from `PREFIX = "yarn.scheduler.capacity."` (`CapacitySchedulerConfiguration.java:89`) + queue path + `CAPACITY = "capacity"`. The suffix is declared at [`CapacitySchedulerConfiguration.java:114`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/main/java/org/apache/hadoop/yarn/server/resourcemanager/scheduler/capacity/CapacitySchedulerConfiguration.java#L114).
- **Read path:**
  - `getNonLabeledQueueCapacity` reads it (`CapacitySchedulerConfiguration.java:587-616`) as a percentage float in [0,100] (`:204`, `:207`, check at `:607-611`).
  - It is stored as a fraction (`/100`) in `CSQueueUtils.loadCapacitiesByLabelsFromConf` (`CSQueueUtils.java:75-76`; labelled partitions at `:85-86`).
  - It is turned into an absolute fraction of the cluster: `absCapacity = capacity × parent.absCapacity` (`CSQueueUtils.java:286-317`).
  - The policy reads it as `managedParentQueue.getQueueCapacities().getAbsoluteCapacity(nodeLabel)` (`GuaranteedOrZeroCapacityOverTimePolicy.java:715-716`).
- **Default:** 0 if unset for a non-root queue (`CapacitySchedulerConfiguration.java:602-606`). In percentage mode the siblings at each level must sum to 100. Absolute-resource (`[memory=..,vcores=..]`) and weight forms also exist; for those, the percentage returned is 0 and the absolute capacity is derived later (`:589-600`).
- **Other sources of the comparison:**
  - The demand side: `yarn.scheduler.capacity.<queue-path>.leaf-queue-template.capacity`. It is loaded in `ManagedParentQueue.initializeLeafQueueConfigs` (`ManagedParentQueue.java:174-184`), and its absolute value is re-derived from the parent in `updateTemplateAbsoluteCapacities` (`GuaranteedOrZeroCapacityOverTimePolicy.java:412-425`).
  - The constant `EPSILON = 0.001f` (`CSQueueUtils.java:33`).
- **How to set it:** edit `capacity-scheduler.xml`, then run `yarn rmadmin -refreshQueues`. No restart is needed: `ManagedParentQueue.reinitialize` (`ManagedParentQueue.java:77-131`) re-reads it, clears the policy state (`GuaranteedOrZeroCapacityOverTimePolicy.java:680-682`) and recomputes entitlements. A ResourceManager restart also works and gives a clean state. When the queue configuration store is mutable, the scheduler-conf REST API can also set it.

**A2. What it caps.**

- **Resource:** the scheduler's **guaranteed share** of cluster container resources (memory MB and vcores, as `absoluteCapacity`, a fraction of the cluster). It is not ResourceManager heap, NodeManager heap or disk.
- **Compared quantity:**
  - The left operand `availableCapacity` = parent absolute capacity − `parentQueueState.getAbsoluteActivatedChildQueueCapacity(label)` + `EPSILON` (`GuaranteedOrZeroCapacityOverTimePolicy.java:715-717`). The middle term is the sum of the template absolute capacities of the currently *activated* leaf queues.
  - It is compared with the template's absolute capacity for that label (`:719-720`).
  - The invariant is: Σ(guarantees of activated leaves) + one more template guarantee ≤ parent absolute capacity (+0.001).
- **What it limits:** the count and sum of **guarantees**. It does not limit the memory the leaves actually hold.

**A3. Mechanism.**

1. A user's app is placed by a queue mapping such as `u:%user:root.parent.%user`. `CapacitySchedulerQueueManager.createLegacyAutoQueue` builds an `AutoCreatedLeafQueue` (`CapacitySchedulerQueueManager.java:693-705`). Its constructor first sets the capacity to 0 and the max to the template max (`AutoCreatedLeafQueue.java:51`, `:163-175`). It then calls `parent.addChildQueue` (`CapacitySchedulerQueueManager.java:493`).
2. `ManagedParentQueue.addChildQueue` (`ManagedParentQueue.java:278-348`):
   - It checks `max-queues` (`:298-307`).
   - It optionally fails creation when `auto-create-child-queue.fail-on-exceeding-parent-capacity=true` (`:309-318`; default false at `CapacitySchedulerConfiguration.java:2396-2401`).
   - It refreshes the template absolute capacities (`:320-321`) and calls `queueManagementPolicy.getInitialLeafQueueConfiguration(leafQueue)` (`:337-338`).
3. In `getInitialLeafQueueConfiguration` (`GuaranteedOrZeroCapacityOverTimePolicy.java:691-733`), for each template node label:
   - The policy computes `availableCapacity` (`:715-717`).
   - **The check** is [`GuaranteedOrZeroCapacityOverTimePolicy.java:719-720`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/main/java/org/apache/hadoop/yarn/server/resourcemanager/scheduler/capacity/queuemanagement/GuaranteedOrZeroCapacityOverTimePolicy.java#L719-L720).
     - **Pass branch:** `updateCapacityFromTemplate` copies the template capacity, max capacity, abs capacity and abs max capacity (`:744-754`). `activate` marks the leaf active and adds its template absolute capacity to the parent's activated sum (`:632-642`, `:204-220`).
     - **Fail branch (limit reached):** `updateToZeroCapacity` sets capacity 0 and **max capacity = template max capacity**, and sets configured min resource to 0 (`:735-742`). The leaf is *not* activated. No exception, no rejection, and the app is still accepted into the leaf.
4. `leafQueue.reinitializeFromTemplate` applies the result (`ManagedParentQueue.java:339`, `AutoCreatedLeafQueue.java:76-124`). The following `updateClusterResource` (`ManagedParentQueue.java:343-344`) recomputes the absolute max from max-capacity × parent abs max (`AbstractLeafQueue.java:2027-2035` → `AbstractCSQueue.java:1231-1240` → `CSQueueUtils.java:319-323`). So a zero-guarantee leaf ends with effective max resource = template max × parent max × cluster.
5. Container allocation is limited by the queue max (`AbstractCSQueue.getCurrentLimitResource` `:788-802`, `canAssignToThisQueue` `:831-857`) and by the user limit (`AbstractLeafQueue.canAssignToUser` `:1655-1680`). Neither uses the guarantee as a ceiling:
   - AM limit: with guarantee 0, `queuePartitionUsableResource` falls back to `queueCurrentLimit` (`AbstractLeafQueue.java:812-814`).
   - The first AM is admitted even over the limit (`:876-883`, `:909-916`).
   - User limit: `maxUserLimit` = effective max capacity when the queue's capacity is `none` (`UsersManager.java:790-798`).
6. **Later re-evaluation** (other check sites for the same decision): with `QueueManagementDynamicEditPolicy` in `yarn.resourcemanager.scheduler.monitor.policies` (default interval 1500 ms, `CapacitySchedulerConfiguration.java:2484-2489`), `computeQueueManagementChanges` runs (`GuaranteedOrZeroCapacityOverTimePolicy.java:310-348`):
   - It deactivates active leaves with no apps (`:536-557`).
   - It activates zero-guarantee leaves in FIFO order when `DeactivatedLeafQueuesByLabel.canActivateLeafQueues()` (`DeactivatedLeafQueuesByLabel.java:94-96`), up to `floor(availableCapacity / templateAbs)` (`:85-92`, availableCapacity at `:56-57`).
   - Changes are committed in `commitQueueManagementChanges` (`:576-630`).
   - `ManagedParentQueue.reinitialize` also runs this on every queue refresh (`ManagedParentQueue.java:112-119`).
7. **Bypass or overshoot:**
   - `EPSILON` lets the sum of guarantees exceed the parent by up to 0.001 of the cluster.
   - The check is per node label (`:706`).
   - A refresh clears `parentQueueState` (`:680-682`) and recomputes from scratch.
   - The check has no effect on usage, because a zero-guarantee leaf is elastic up to its max (step 5).

**A4. Other consumers.** Other things use the same container memory outside this check's control:

- sibling queues of the parent (e.g. `root.default`);
- other leaves under the parent, and their AM containers;
- reserved containers;
- for real host memory: the NodeManager and ResourceManager JVMs, the DataNode and NameNode if co-located, page cache and the OS.

The guarantee set here matters only under contention. It is used by queue ordering (`policy/PriorityUtilizationQueueOrderingPolicy.java`) and, if preemption is enabled, as the level that preemption will not go below. That makes it a floor, not a ceiling. The ResourceManager heap used by queue objects is bounded by `max-queues` (default 1000, `CapacitySchedulerConfiguration.java:2333-2337,2438-2442`), not by this check.

**A5. Evidence beyond the source.**

- `hadoop-yarn-project/hadoop-yarn/hadoop-yarn-site/src/site/markdown/CapacityScheduler.md:133`: queue capacity is a guarantee, and "Applications in the queue may consume more resources than the queue's capacity if there are free resources, providing elasticity".
- `CapacityScheduler.md:687`: the management policy "allots either configured or zero capacity on a best-effort basis".
- `CapacityScheduler.md:698-699`: `leaf-queue-template.capacity` is the "minimum guaranteed capacity", and `maximum-capacity` is the maximum.
- `CapacityScheduler.md:761-766`: `QueueManagementDynamicEditPolicy`.
- Published at https://hadoop.apache.org/docs/r3.4.2/hadoop-yarn/hadoop-yarn-site/CapacityScheduler.html.
- Tests:
  - `TestCapacitySchedulerAutoQueueCreation.java:719-806` (`testAutoCreatedQueueActivationDeactivation`: the third leaf gets capacity 0 while the activated sum stays at 0.2).
  - `TestCapacitySchedulerAutoQueueCreation.java:808-907` (`testClusterResourceUpdationOnAutoCreatedLeafQueues`: the zero-capacity USER3 has `EffectiveMinResource == none` but `EffectiveMaxResource == MAX_RES`).
  - Test fixture: `TestCapacitySchedulerAutoCreatedQueueBase.java:131-134,406-441`.

## B. Verification solution

**B1. Claim under test.** In the claim, *the check* means the if statement at `GuaranteedOrZeroCapacityOverTimePolicy.java:719`. *The template max* means `leaf-queue-template.maximum-capacity`.

- **Claim:** how much container memory an auto-created leaf queue is allocated, and how much its containers actually hold resident, does **not** follow the check or its limit. Changing the check's outcome for a given leaf (zero guarantee vs. template guarantee), or changing the parent's `capacity`, leaves the leaf's peak memory unchanged within one container. The peak is set by the demand and by the template max.
- **What would refute it:** a zero-guarantee leaf that cannot run, or that is held near its guarantee, while the same leaf with a guarantee grows.

### B2. Unit tier

Drive a `CapacityScheduler` inside `MockRM`/`MockNM`: an in-JVM ResourceManager with simulated nodes, so no daemons and no real containers. Measure two things for each leaf:

- the check's own operand (`availableCapacity`) and its outcome (leaf absolute capacity, the policy's activated sum);
- the scheduler-side memory allocated to the leaf (`getQueueResourceUsage().getUsed()`).

**B2a. Environment and build.**

- **Requirements:** Linux, JDK 8 (or 11), Maven 3.6+, at least 25 GB free on a **local** disk.
- **Environment variables:**
  - `export SCRATCH=/tmp/ifchk-$USER` (verify with `df -h /tmp` that it is local, not NFS).
  - `export MAVEN_OPTS="-Xmx2g"`.
- **Build:**
  ```
  mkdir -p $SCRATCH && rsync -a --exclude .git ~/hadoop-3.4.2/ $SCRATCH/src/
  cd $SCRATCH/src
  mvn -Dmaven.repo.local=$SCRATCH/m2 -DskipTests -Dmaven.javadoc.skip=true install \
      -pl hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager -am
  ```
- **Test source:** new file `$SCRATCH/src/hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/test/java/org/apache/hadoop/yarn/server/resourcemanager/scheduler/capacity/TestIfCheckAutoQueueGuaranteeVsUsage.java`. It goes in the copy only, never in `~/hadoop-3.4.2`. It uses the same package as the policy so it can reach package-private helpers.
- **JVM options:** surefire defaults from the module pom.

> *Amended 2026-11-06 (D, A1):* on the stage-4 node there is no `~/hadoop-3.4.2` and no per-case Maven repository. `SCRATCH=/mydata/yang-s4/<stem>-run1` (local disk; `/tmp` is not used). The source copy is made with `experiments/if-check-exp/hadoop/stage4-runtime-verification/yang/copy-source.sh $SCRATCH/src` (the repository's pinned `systems/hadoop/source/`, tag `rel/release-3.4.2`). `JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64`. The `-am install` build and `-Dmaven.repo.local` are dropped: every 3.4.2 module is already installed in the node's `~/.m2` (stage-4 `environment.md` §3), so step B2e.2 runs `mvn -B test -Dtest=TestIfCheckAutoQueueGuaranteeVsUsage` in the ResourceManager module of `$SCRATCH/src` against those artifacts. The measurement is unchanged.

**B2b. Knobs.** Each run is a fresh `MockRM` with these `CapacitySchedulerConfiguration` values. `P` = `root.parent.capacity`, with `root.default.capacity = 100−P`; `T` = `root.parent.leaf-queue-template.capacity`; `M` = `root.parent.leaf-queue-template.maximum-capacity`.

| Run | `P` | `T` | `M` | Why |
|---|---|---|---|---|
| U1 | 20 | 50 | 100 | Baseline: leaf abs = 0.10, at most 2 activated, so leaf u3 gets **0** |
| U2 | 20 | 25 | 100 | Flips the check for u3: leaf abs = 0.05, at most 4 activated, so u3 is **activated** |
| U3 | 40 | 50 | 100 | Changes the limit itself (parent abs 0.4); u3 still gets 0, but the activated leaves' guarantee doubles |
| U4 | 20 | 50 | 25 | **Positive control:** a known binding cap (leaf abs max = 0.25), same workload |

Fixed in every run:

- `leaf-queue-template.user-limit-factor=100`, so the user-limit factor does not interfere.
- `yarn.scheduler.capacity.queue-mappings=u:%user:root.parent.%user` and `yarn.scheduler.capacity.queue-mappings-override.enable=true`.
- `yarn.scheduler.minimum-allocation-mb=1024`.
- Default `DefaultResourceCalculator` (memory only).
- One `MockNM` with 102400 MB and 100 vcores.

**B2c. Workload.**

- **Users and queues:** users `u1`, `u2`, `u3` submit one app each, in order, each with a 1024 MB AM; this auto-creates `root.parent.u1..u3`. In U2, users `u4` and `u5` also submit apps afterwards, to confirm that the fifth leaf is the first one refused.
- **Load:** u3's AM is then launched and registered, and asks for **40 × 1024 MB** containers. The NM heartbeats 80 times.
- **Arithmetic:**
  - U1: u3's guarantee is 0 and the activated leaves' guarantee is 0.1 × 102400 = 10240 MB. u3's demand of 41 × 1024 = 41984 MB is far above both.
  - Its max (`M`=100 × parent max 1.0) is 102400 MB. Free memory is 102400 − 3 AMs = 99328 MB, so neither the max nor the cluster limits the demand.
  - U4: max = 0.25 × 102400 = 25600 MB < 41984 MB, so the cap must bind.

**B2d. Observables and instruments.** All are read from Java inside the test and printed as one tab-separated line per sample, prefixed `IFCHK`.

- **The operand, sampled before each submission:** `availableCapacity` recomputed as
  - `cs.getQueue("root.parent").getQueueCapacities().getAbsoluteCapacity("")`
  - − `policy.getAbsoluteActivatedChildQueueCapacity("")`
  - \+ `CSQueueUtils.EPSILON`
  
  where `policy = (GuaranteedOrZeroCapacityOverTimePolicy) ((ManagedParentQueue) cs.getQueue("root.parent")).getAutoCreatedQueueManagementPolicy()`. This is the same expression as `:715-717`. No hook is placed inside the method.
- **The outcome, after each submission:**
  - the leaf's `getQueueCapacities().getAbsoluteCapacity()`;
  - `policy.isActive((AutoCreatedLeafQueue) leaf, "")`;
  - `policy.getAbsoluteActivatedChildQueueCapacity("")`;
  - `leaf.getQueueResourceQuotas().getEffectiveMaxResource().getMemorySize()`.
- **The usage, after every 10 heartbeats and at the end:**
  - `leaf.getQueueResourceUsage().getUsed().getMemorySize()` for u1..u3;
  - `cs.getQueue("root.parent").getQueueResourceUsage().getUsed()`;
  - u3's app state (`rm.getRMContext().getRMApps().get(appId).getState()`).
- **Not observable here:** real process memory. Containers in `MockNM` are not processes, so the unit tier measures only the scheduler's allocated memory.

> *Amended 2026-11-06 (D, A2):* the outline in B2e omits two observables listed here; the harness adds them as print lines and nothing else: (a) after the 80th heartbeat, one `IFCHK <id> end` line with u3's app state and the used memory of u1..u5 that exist; (b) in U2 the `usage` lines also cover u4 and u5. U4's "≥ 15 requests unsatisfied" has no separate instrument: it is derived as `40 − (u3 used − 1024) / 1024`.

**B2e. Procedure.**

1. Write the test class. Its outline is below. Each run is one `@Test` method calling `runCase(P, T, M, users)`.
   ```java
   package org.apache.hadoop.yarn.server.resourcemanager.scheduler.capacity;
   // imports: MockRM, MockNM, MockAM, MockRMAppSubmitter, MockRMAppSubmissionData, RMApp,
   //   QueueMetrics, YarnConfiguration, ResourceScheduler, GuaranteedOrZeroCapacityOverTimePolicy, org.junit.*
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
         MockAM am = MockRM.launchAndRegisterAM(u3App, rm, nm);
         am.allocate("*", GB, 40, new java.util.ArrayList<>());
         for (int i = 1; i <= 80; i++) {
           nm.nodeHeartbeat(true);
           Thread.sleep(50);
           if (i % 10 == 0) for (String u : new String[]{"u1", "u2", "u3"})
             System.out.printf("IFCHK\t%s\tusage\thb=%d\t%s\tusedMB=%d\tparentUsedMB=%d%n", id, i, u,
                 cs.getQueue("root.parent." + u).getQueueResourceUsage().getUsed().getMemorySize(),
                 parent.getQueueResourceUsage().getUsed().getMemorySize());
         }
       } finally { rm.stop(); }
     }
     @Test public void u1() throws Exception { runCase("U1", 20, 50, 100, new String[]{"u1","u2","u3"}); }
     @Test public void u2() throws Exception { runCase("U2", 20, 25, 100, new String[]{"u1","u2","u3","u4","u5"}); }
     @Test public void u3() throws Exception { runCase("U3", 40, 50, 100, new String[]{"u1","u2","u3"}); }
     @Test public void u4() throws Exception { runCase("U4", 20, 50, 25, new String[]{"u1","u2","u3"}); }
   }
   ```
   If a helper signature differs at this tag, use the identical calls in `TestCapacitySchedulerAutoQueueCreation.java` / `TestCapacitySchedulerAutoCreatedQueueBase.java:528-553` as the reference. That is an adaptation of the calls, not of the measurement.

   > *Amended 2026-11-06 (D, A9; runbook defect 1 of the stage-4 run 1, unit tier):* `MockRM.launchAndRegisterAM(u3App, rm, nm)` cannot run as written. `MockRM.launchAM` (`MockRM.java:915-927`) sends exactly two node heartbeats, and the scheduler assigns one container per heartbeat here, so those two heartbeats go to u1's and u2's AMs (submitted first) and u3's attempt stays `SCHEDULED`; the call fails with "Attempt state is not correct (timeout). expected:<ALLOCATED> but was:<SCHEDULED>" in all four runs, including U2 where u3 is activated. Replacement, using the sequence `MockRM.sendAMLaunched` documents (`:665-669`): `RMAppAttempt att = MockRM.waitForAttemptScheduled(u3App, rm);` then `nm.nodeHeartbeat(true); rm.drainEvents();` up to 20 times until `att.getAppAttemptState() == ALLOCATED` (the count is printed as an `IFCHK <id> amAlloc` line); then `MockAM am = rm.sendAMLaunched(att.getAppAttemptId()); am.registerAppAttempt(); rm.waitForState(u3App.getApplicationId(), RMAppState.RUNNING);`. The extra heartbeats also place the other users' AMs (1024 MB each, as B2f expects for u1 and u2). The workload, observables, predictions (B2f) and readings (B2g) are unchanged; the unit tier restarts from its beginning.
2. Run it:
   ```
   cd $SCRATCH/src/hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager
   mvn -Dmaven.repo.local=$SCRATCH/m2 test -Dtest=TestIfCheckAutoQueueGuaranteeVsUsage 2>&1 | tee $SCRATCH/unit.log
   ```
3. Extract the results: `grep IFCHK $SCRATCH/unit.log` and also `target/surefire-reports/*TestIfCheck*-output.txt`.
4. Repeat the whole run twice more, three runs in total, to check the results are deterministic.

**B2f. Predictions** (stated before any run). `avail` is printed before each creation. Allocated memory includes the AM.

| Run | `avail` before u1, u2, u3 (u4, u5) | u3 leaf abs cap / active | activated sum after u3 (after u5) | u3 effective max (MB) | u3 used after 80 heartbeats (MB) |
|---|---|---|---|---|---|
| U1 | 0.201, 0.101, 0.001 | 0.0 / false | 0.200 | 102400 | **41984** (= 1 AM + 40 × 1024) |
| U2 | 0.201, 0.151, 0.101 (0.051, 0.001) | 0.05 / true; u5: 0.0 / false | 0.150 (0.200) | 102400 | **41984** |
| U3 | 0.401, 0.201, 0.001 | 0.0 / false | 0.400 | 102400 | **41984** |
| U4 (control) | 0.201, 0.101, 0.001 | 0.0 / false | 0.200 | 25600 | **≤ 25600** (at most 1 container over: ≤ 26624), and ≥ 15 requests unsatisfied |

- u1 and u2 stay at 1024 MB each (their AMs) in all runs.
- The claim is wrong if u3's used memory in U1 or U3 (zero guarantee) stays ≤ 1024 MB, or plateaus near a guarantee-derived value, while in U2 (activated) it reaches 41984 MB. Specifically, the claim is wrong if U1 and U2 differ by more than 1024 MB.
- The trace is wrong if `avail` or the u3 abs cap differs from the table.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `avail`/abs cap/activated sum as predicted; u3 used ≈ 41984 MB in U1, U2 and U3; U4 ≤ 26624 MB | Claim **confirmed**. The check sets guarantees as traced, usage does not follow the check or the parent's capacity, and the positive control shows the same workload is capped where a cap binds. |
| u3 used in U1/U3 ≈ 1024 MB or 0 (app not activated, or no containers), while U2 ≈ 41984 MB | Claim **refuted**: usage follows the check (estimate should be positive). |
| u3 used in U1 is near a guarantee-derived value (e.g. ≈ 10240 MB) and differs from U2 | Claim **refuted**: the guarantee acts as a ceiling. |
| U1 ≈ U2 ≈ U3, but U4 also reaches ≈ 41984 MB | **Not confirmed**: the positive control did not move. The harness is not enforcing max capacity (check that `M` was applied: U4 effective max should print 25600). |
| u3 used stays low in **all** runs, including U2 | **Not confirmed**: the demand never reached the limit (AM not registered, or heartbeats too few). Raise the heartbeat count to 200 and re-check. |
| `avail` sequence or abs cap differs from the prediction | The trace in A3 is wrong. Record it and re-derive before reading usage. |

> *Amended 2026-11-06 (D, A3), before any run:* (a) "≈ X" in B2f/B2g means within ±1024 MB of X (one container, the B1 tolerance). (b) The last row's verdict is **Not confirmed** (the runs no longer isolate the check's outcome); usage is reported but no claim verdict is drawn from it. (c) New row: u3 used in U1 or U3 differs from U2 by more than 1024 MB, and neither of the two **refuted** patterns above fits → Claim **refuted** (B2f: "the claim is wrong if U1 and U2 differ by more than 1024 MB"). (d) New row: U1 ≈ U2 ≈ U3 ≈ 41984 MB, U4's effective max prints 25600, but U4's u3 used is between 26625 and 41983 MB → **Not confirmed** (the control only partly bound). (e) New row: the three repeats of B2e step 4 disagree (any `avail`, abs cap, `active` or effective-max value differs, or a usage value differs by more than 1024 MB) → **Not confirmed** (not deterministic). The verdict is read from repeat 1 when the three agree.

**B2h. Controls.**

- U4 is the positive control: same demand, a binding max.
- U2 versus U1 changes only the check's outcome for u3.
- U3 versus U1 changes only the limit.
- Printing `effMaxMB` rules out a misapplied template.
- Printing `avail` confirms that the check was evaluated with the predicted operand.
- Printing u1 and u2 usage confirms that no other leaf's demand interferes.
- A fresh `MockRM` and `QueueMetrics.clearQueueMetrics()` per run rule out carry-over.
- The cluster is 100 GB, far above the demand in U1–U3, so the cluster size cannot be what limits u3.

### B3. Cluster tier

A pseudo-distributed Hadoop on one Linux host: HDFS NameNode and DataNode for the staging directories of the distributed-shell client, one ResourceManager, and one NodeManager. Three users submit distributed-shell apps whose containers hold about 600 MiB resident each. Measure:

- the memory the ResourceManager allocates to each leaf queue (REST);
- the actual resident memory of each user's container processes (`ps`).

**B3a. Environment and build.**

- **Host:** one Linux host with at least 16 GB free RAM and 4+ cores, at least 10 GB free local disk, `python3`, `jq`, `curl`, and JDK 8 or 11.
- **Build:**
  ```
  cd $SCRATCH/src
  mvn -Dmaven.repo.local=$SCRATCH/m2 package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true
  tar -xzf hadoop-dist/target/hadoop-3.4.2.tar.gz -C $SCRATCH
  export HADOOP_HOME=$SCRATCH/hadoop-3.4.2 HADOOP_CONF_DIR=$SCRATCH/conf PATH=$SCRATCH/hadoop-3.4.2/bin:$PATH
  mkdir -p $SCRATCH/conf $SCRATCH/data $SCRATCH/logs && cp $HADOOP_HOME/etc/hadoop/* $SCRATCH/conf/
  export HADOOP_LOG_DIR=$SCRATCH/logs HADOOP_PID_DIR=$SCRATCH/pids
  ```
- **JVM options:** `HADOOP_HEAPSIZE_MAX=1g` in `$SCRATCH/conf/hadoop-env.sh`, so the daemon heaps are small and known.
- **`core-site.xml`:**
  - `fs.defaultFS=hdfs://localhost:9000`
  - `hadoop.tmp.dir=$SCRATCH/data/tmp`
- **`hdfs-site.xml`:**
  - `dfs.replication=1`
  - `dfs.namenode.name.dir=$SCRATCH/data/nn`
  - `dfs.datanode.data.dir=$SCRATCH/data/dn`
  - `dfs.permissions.enabled=false`
- **`yarn-site.xml`:**
  - `yarn.resourcemanager.scheduler.class=org.apache.hadoop.yarn.server.resourcemanager.scheduler.capacity.CapacityScheduler`
  - `yarn.nodemanager.resource.memory-mb=12288`
  - `yarn.nodemanager.resource.cpu-vcores=12`
  - `yarn.scheduler.minimum-allocation-mb=1024`
  - `yarn.scheduler.maximum-allocation-mb=4096`
  - `yarn.nodemanager.vmem-check-enabled=false` (pmem check left on)
  - `yarn.nodemanager.local-dirs=$SCRATCH/data/nm-local`
  - `yarn.nodemanager.log-dirs=$SCRATCH/data/nm-logs`
  - `yarn.resourcemanager.scheduler.monitor.enable=true`
  - `yarn.resourcemanager.scheduler.monitor.policies=org.apache.hadoop.yarn.server.resourcemanager.scheduler.capacity.QueueManagementDynamicEditPolicy`
  - `yarn.resourcemanager.recovery.enabled=false`
- **`capacity-scheduler.xml`** (replace the file): `root.queues=default,parent`, plus the values of B3b and the fixed values in B2b (`user-limit-factor=100`, mapping, override). `root.parent.maximum-capacity` and `root.default.maximum-capacity` are left at their defaults (100).

> *Amended 2026-11-06 (D, A4):* environment on the stage-4 node. `SCRATCH=/mydata/yang-s4/<stem>-run1` (as A1). No tarball build: the node's built distribution is copied, `cp -a /mydata/yang-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2 $SCRATCH/hadoop`, and `HADOOP_HOME=$SCRATCH/hadoop`. That distribution's `share/hadoop/yarn/` has no YARN module jars (its `lib/` is complete; the resumed base build's assembly left them out), so the 3.4.2 main jars of the YARN modules (`hadoop-yarn-{api,client,common,registry,server-common,server-nodemanager,server-resourcemanager,server-web-proxy,server-applicationhistoryservice,server-router,server-sharedcachemanager,server-timeline-pluginstorage,server-globalpolicygenerator,services-core,services-api,applications-distributedshell,applications-unmanaged-am-launcher}-3.4.2.jar`) are copied from the node's `~/.m2` into the copy's `share/hadoop/yarn/`. `JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64` is set in `$SCRATCH/conf/hadoop-env.sh` next to `HADOOP_HEAPSIZE_MAX=1g`. `jq` is not installed: the B3d REST selection is done by a `python3 -I` filter that selects the same objects and prints the same five fields. Ports checked free before start: 9000, 9870, 9864, 9866, 9867, 8088, 8030–8033, 8040, 8042.

> *Amended 2026-11-06 (D, A10; runbook defect 2 of the stage-4 run 1, cluster tier):* `cp $HADOOP_HOME/etc/hadoop/* $SCRATCH/conf/` exits 1 ("-r not specified; omitting directory … shellprofile.d"), because `etc/hadoop` holds the directory `shellprofile.d`. It is `cp -r $HADOOP_HOME/etc/hadoop/* $SCRATCH/conf/`. Nothing had started (no daemon, no workload); the cluster tier restarted from its beginning.

**B3b. Knobs.** The same runs as the unit tier, renamed C1–C4. The cluster is 12288 MB.

| Run | `P` | `T` | `M` | Leaf guarantee (MB) | u3 outcome at the check | u3 max (MB) |
|---|---|---|---|---|---|---|
| C1 | 20 | 50 | 100 | 1228.8 | 0 | 12288 |
| C2 | 20 | 25 | 100 | 614.4 | activated (614.4) | 12288 |
| C3 | 40 | 50 | 100 | 2457.6 | 0 | 12288 |
| C4 (control) | 20 | 50 | 25 | 1228.8 | 0 | 3072 |

Set the knobs by editing `$SCRATCH/conf/capacity-scheduler.xml` and **restarting the ResourceManager** between runs (`yarn --daemon stop resourcemanager; yarn --daemon start resourcemanager`). The restart drops the auto-created leaves and the policy state, so each run starts clean.

**B3c. Workload.**

- **Container payload:** `$SCRATCH/hog.py`:
  ```
  import sys,time
  b=bytearray(600*1024*1024)
  for i in range(0,len(b),4096): b[i]=1
  time.sleep(1800)
  ```
  `$SCRATCH/hog.sh` is `#!/bin/bash` followed by `exec python3 $SCRATCH/hog.py "$@"`, with `$SCRATCH` written out literally.
- **Submit helper:**
  ```
  DS=$HADOOP_HOME/share/hadoop/yarn/hadoop-yarn-applications-distributedshell-3.4.2.jar
  sub(){ HADOOP_USER_NAME=$1 nohup yarn jar $DS -jar $DS -shell_script $SCRATCH/hog.sh \
      -shell_args ifchk-$1 -num_containers $2 -container_memory 1024 -master_memory 1024 \
      -queue default -timeout 1800000 > $SCRATCH/logs/client-$1.log 2>&1 & }
  ```
- **Submissions, in order:** `sub u1 1`, then `sub u2 1`, each 2048 MB in total. Then `sub u3 6`: 1024 + 6 × 1024 = 7168 MB.
- **Arithmetic:**
  - Total demand is 4096 + 7168 = 11264 MB ≤ 12288, so the cluster size does not limit u3.
  - u3's demand of 7168 MB is greater than every guarantee involved (0, 614.4, 1228.8, 2457.6 MB) and less than its max in C1–C3 (12288 MB).
  - In C4 it is greater than its max of 3072 MB.
  - Resident memory per hog container is ≈ 600 MiB + about 10 MiB of interpreter, which is under the 1024 MB pmem limit.
- **Duration:** 120 s of sampling after u3's app is RUNNING, for each run.

> *Amended 2026-11-06 (D, A5):* the distributed-shell jar is not in the distribution's `share/`; `DS=~/.m2/repository/org/apache/hadoop/hadoop-yarn-applications-distributedshell/3.4.2/hadoop-yarn-applications-distributedshell-3.4.2.jar` (stage-4 `environment.md` §3).

**B3d. Observables and instruments.** Sample every 2 s for 120 s with `$SCRATCH/sample.sh`, which appends to `$SCRATCH/run-$RUN.tsv`:

- **Allocated memory:**
  ```
  curl -s http://localhost:8088/ws/v1/cluster/scheduler \
    | jq -r '.. | objects | select((.queuePath? // "") | startswith("root.parent.")) | [.queuePath,.absoluteCapacity,.absoluteMaxCapacity,.resourcesUsed.memory,.numApplications] | @tsv'
  ```
  The `absoluteCapacity` and `absoluteMaxCapacity` fields are in percent.
- **Resident memory:** for each user `u`, `ps -o rss= -p $(pgrep -d, -f "hog.py ifchk-$u") | awk '{s+=$1} END {print s/1024}'` gives MiB, and `pgrep -c -f "hog.py ifchk-$u"` gives the container count.
- **Context:** `yarn application -list -appStates ALL` (app states), once per run.
- **Host:** `free -m`, once per run.
- **Not observable directly:** the ResourceManager's internal `availableCapacity`. Infer it from each leaf's `absoluteCapacity` (100 × leaf abs cap), or enable `log4j.logger.org.apache.hadoop.yarn.server.resourcemanager.scheduler.capacity.queuemanagement=DEBUG` to see `DeactivatedLeafQueuesByLabel.printToDebug` lines (`DeactivatedLeafQueuesByLabel.java:73-82`) from the monitor policy.
- **Memory outside the hog containers:** the AM JVM's resident memory is not separated out. Report it from `ps` on the `ApplicationMaster` process if wanted.

**B3e. Procedure.**

1. Format and start HDFS:
   ```
   hdfs namenode -format -nonInteractive
   hdfs --daemon start namenode
   hdfs --daemon start datanode
   ```
   Wait until `hdfs dfsadmin -report` shows 1 live node.
2. For RUN in C1..C4:
   1. Write `capacity-scheduler.xml` for RUN.
   2. Start or restart YARN: `yarn --daemon start resourcemanager; yarn --daemon start nodemanager`. Wait until `yarn node -list` shows 1 RUNNING node with 12288 MB.
   3. Run `sub u1 1`. Wait until the REST output shows `root.parent.u1` with `resourcesUsed.memory=2048`.
   4. Run `sub u2 1` and wait in the same way.
   5. Run `sub u3 6`.
   6. When u3's app is RUNNING, start `sample.sh` for 120 s.
   7. Record the u1, u2, u3 `absoluteCapacity` (expected: C1 10/10/0, C2 5/5/5, C3 20/20/0, C4 10/10/0) and `absoluteMaxCapacity`.
   8. Kill the apps: `yarn application -list | awk '/application_/{print $1}' | xargs -r -n1 yarn application -kill`.
   9. Run `pgrep -f hog.py` and confirm it is empty within 30 s.
3. Stop everything:
   ```
   yarn --daemon stop nodemanager
   yarn --daemon stop resourcemanager
   hdfs --daemon stop datanode
   hdfs --daemon stop namenode
   ```

> *Amended 2026-11-06 (D, A6):* (a) Step 2.2: the ResourceManager is stopped and started for every run (as B3b says); the NodeManager is started once and re-registers after each ResourceManager restart. "1 RUNNING node with 12288 MB" is read from `http://localhost:8088/ws/v1/cluster/nodes` (`state`, `totalResource.memory`), because `yarn node -list` does not print memory. (b) Before step 2.2 of C2–C4 the previous run's apps are killed and `pgrep -f hog.py` is empty (step 2.8–2.9 of the previous run). (c) Every wait has a timeout of 180 s; a timeout is a runbook stop: every daemon is stopped and the defect recorded. The first-trigger check is step 2.3: if `root.parent.u1` does not appear in the REST output, the run stops there. (d) The 120 s window of step 2.6 starts when u3's app reports RUNNING and its allocation has not changed for 10 s, or 60 s after RUNNING, whichever comes first (so container start-up is not inside the window).

**B3f. Predictions** (stated before any run). Values are steady-state over the 120 s.

| Run | u3 `absoluteCapacity` (%) | u3 `absoluteMaxCapacity` (%) | u3 `resourcesUsed.memory` (MB) | u3 hog processes | u3 hog RSS (MiB) |
|---|---|---|---|---|---|
| C1 | 0 | 100 | **7168** | 6 | ≈ 3650 (6 × ~610, ±10%) |
| C2 | 5 | 100 | **7168** | 6 | ≈ 3650 |
| C3 | 0 | 100 | **7168** | 6 | ≈ 3650 |
| C4 (control) | 0 | 25 | **≤ 3072** (AM + 2) | ≤ 2 | ≤ ≈ 1220 |

- u1 and u2 hold 2048 MB and about 610 MiB RSS each in every run.
- Relation tested: C1 = C2 = C3 within ±1024 MB allocated and ±10% RSS. C4 < C1 by at least 4096 MB allocated.
- The claim is wrong if u3 in C1/C3 has 0 hog processes, or stays ACCEPTED, or is held below 7168 MB while C2 reaches 7168.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| C1 ≈ C2 ≈ C3 ≈ 7168 MB and ≈ 3650 MiB RSS for u3; C4 ≤ 3072 MB | Claim **confirmed**: actual memory does not follow the check or the parent's capacity, while a binding cap moves the same workload (positive control). |
| u3 in C1/C3 stays ACCEPTED or has ≤ 1024 MB (AM only), while C2 reaches 7168 MB | Claim **refuted**: usage follows the check, so it acts as an admission or usage cap (estimate should be positive). |
| u3 in C1/C3 plateaus clearly below 7168 MB with requests pending and free cluster memory, while C2 does not | Claim **refuted** (partial cap tied to the guarantee). Inspect the `UsersManager` user-limit debug output. |
| C1–C3 all low (e.g. < 4096 MB), including C2 | **Not confirmed**: something other than the check (pmem kills, node memory, AM failures) prevented reaching the limit. Check the NodeManager log for "is running beyond physical memory limits" and the client logs. |
| C1 ≈ C2 ≈ C3 but C4 also ≈ 7168 MB | **Not confirmed**: the positive control did not move. The template max was not applied (C4's `absoluteMaxCapacity` should read 25). |
| u3's `absoluteCapacity` not as listed (e.g. 10 in C1) | The trace or the creation order is off (e.g. u3 created before u2). Redo with strict ordering before reading usage. |

> *Amended 2026-11-06 (D, A7, A8), before any run:* (a) "Steady-state" in B3f is the median of the 2-s samples in the 120 s window (min and max are reported with it); "≈" means within ±1024 MB allocated and ±10 % RSS (the B3f relation). (b) Last row: if the leaves were created out of order (an execution problem, seen in the client logs and REST timestamps), that run is repeated once with strict ordering; if the order was right and `absoluteCapacity` still differs, the verdict is **Not confirmed** (the runs no longer isolate the check's outcome). (c) New row: u3 allocated memory in C1 or C3 differs from C2 by more than 1024 MB, or u3 RSS by more than 10 %, and neither **refuted** pattern above fits → Claim **refuted** (B3f relation). (d) New row: u3 allocated memory ≈ 7168 MB in C1–C3 but u3's hog count is not 6 or its RSS is outside 3650 MiB ± 10 % in any of them → **Not confirmed** (allocated and resident memory disagree; check the NodeManager log for pmem kills). (e) New row: C1 ≈ C2 ≈ C3 as predicted, C4's `absoluteMaxCapacity` reads 25, but C4's u3 allocation is between 3073 and 7167 MB → **Not confirmed** (the control only partly bound). (f) B3h's "discard the run" means: repeat that run once; if u3's `absoluteCapacity` changes during sampling again, the cluster tier is **Not confirmed**.

**B3h. Controls.**

- C4 is the positive control: the same three submissions with a known binding cap.
- C2 versus C1 isolates the check's outcome.
- C3 versus C1 isolates the limit.
- `absoluteCapacity` per leaf, read in the same sample, confirms the check's outcome for each run.
- u1 and u2 apps are kept running throughout, so the monitor policy does not deactivate them and re-activate u3 mid-run (`:536-557`, `:350-376`). If u3's `absoluteCapacity` changes during sampling, discard the run.
- The total demand is kept below the cluster size, so contention cannot explain any difference.
- `root.default` is kept idle.
- A ResourceManager restart per run gives a clean policy state.
- RSS is counted only for processes tagged `ifchk-<user>`.

**B4. Risks and cleanup.**

- **Disk:**
  - Everything goes in `$SCRATCH` on local disk: source copy, Maven repo, tarball, HDFS, NodeManager dirs, logs. That is about 20 GB for the build and under 1 GB for the run.
  - Nothing is written to `~/hadoop-3.4.2`, NFS or shared storage.
  - The Maven repo is redirected with `-Dmaven.repo.local`.
- **Memory:** about 11 GB of containers plus about 3 GB of daemons. Check `free -m` before starting and use a host with at least 16 GB available.
- **Ports:** 8088, 9000 and 9870 must be free, so the run does not collide with another user's daemons. Check with `ss -ltn` first.
- **Leftover processes:** after each tier, run:
  ```
  yarn --daemon stop nodemanager; yarn --daemon stop resourcemanager
  hdfs --daemon stop datanode; hdfs --daemon stop namenode
  pkill -u $USER -f hog.py; pkill -u $USER -f distributedshell
  ```
  Then confirm that `jps` lists no `ResourceManager`, `NodeManager`, `NameNode`, `DataNode` or `ApplicationMaster` processes. The unit tier's surefire JVM exits by itself; check with `jps` for a leftover `surefirebooter`.
- **Final cleanup:** `rm -rf $SCRATCH`.

## C. Sources read

- /users/jason92/if-check-brief/playbook-autonomous.md
- /users/jason92/if-check-brief/SYSTEM-NOTE.md
- /users/jason92/if-check-brief/_TEMPLATE-autonomous.md
- /users/jason92/if-check-brief/naming-6.1.md
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/main/java/org/apache/hadoop/yarn/server/resourcemanager/scheduler/capacity/queuemanagement/GuaranteedOrZeroCapacityOverTimePolicy.java
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/main/java/org/apache/hadoop/yarn/server/resourcemanager/scheduler/capacity/queuemanagement/DeactivatedLeafQueuesByLabel.java
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/main/java/org/apache/hadoop/yarn/server/resourcemanager/scheduler/capacity/ManagedParentQueue.java
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/main/java/org/apache/hadoop/yarn/server/resourcemanager/scheduler/capacity/AutoCreatedLeafQueue.java
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/main/java/org/apache/hadoop/yarn/server/resourcemanager/scheduler/capacity/CapacitySchedulerConfiguration.java
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/main/java/org/apache/hadoop/yarn/server/resourcemanager/scheduler/capacity/CapacitySchedulerQueueManager.java
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/main/java/org/apache/hadoop/yarn/server/resourcemanager/scheduler/capacity/CSQueueUtils.java
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/main/java/org/apache/hadoop/yarn/server/resourcemanager/scheduler/capacity/QueueCapacities.java
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/main/java/org/apache/hadoop/yarn/server/resourcemanager/scheduler/capacity/AbstractLeafQueue.java
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/main/java/org/apache/hadoop/yarn/server/resourcemanager/scheduler/capacity/AbstractCSQueue.java
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/main/java/org/apache/hadoop/yarn/server/resourcemanager/scheduler/capacity/UsersManager.java
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/main/java/org/apache/hadoop/yarn/server/resourcemanager/scheduler/capacity/QueueManagementDynamicEditPolicy.java (grep only)
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/main/java/org/apache/hadoop/yarn/server/resourcemanager/webapp/dao/CapacitySchedulerQueueInfo.java (grep only)
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/test/java/org/apache/hadoop/yarn/server/resourcemanager/scheduler/capacity/TestCapacitySchedulerAutoQueueCreation.java
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/test/java/org/apache/hadoop/yarn/server/resourcemanager/scheduler/capacity/TestCapacitySchedulerAutoCreatedQueueBase.java
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/test/java/org/apache/hadoop/yarn/server/resourcemanager/MockRM.java (grep only)
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/test/java/org/apache/hadoop/yarn/server/resourcemanager/MockAM.java (grep only)
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-applications/hadoop-yarn-applications-distributedshell/src/main/java/org/apache/hadoop/yarn/applications/distributedshell/Client.java (grep only)
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-site/src/site/markdown/CapacityScheduler.md
- https://hadoop.apache.org/docs/r3.4.2/hadoop-yarn/hadoop-yarn-site/CapacityScheduler.html (published form of the same doc; cited, not fetched)

## D. Stage-4 feedback

### D1. Step-0 amendments, 2026-11-06 (before any harness run or reading)

Made by the stage-4 audit ([results file](../../../stage4-runtime-verification/yang/results/yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous.md) section 1). None depends on a reading. The claim (B1), every filed prediction (B2f, B3f) and every filed conclusion row are unchanged; the amendments adapt paths to the stage-4 node, add print lines the observables already listed, define tolerances, and add rows for outcomes the tables did not cover.

| # | Where | Amendment | Reason |
|---|---|---|---|
| A1 | B2a | `SCRATCH` on `/mydata`, source from `copy-source.sh`, JDK 8, the node's `~/.m2` instead of a per-case repo and `-am` build | the filed paths (`~/hadoop-3.4.2`, `$SCRATCH/m2`) do not exist on the node |
| A2 | B2d | print u3's app state at the end and u4/u5 usage in U2; U4's unsatisfied requests derived from used memory | B2d lists them, the B2e outline omits them |
| A3 | B2g | "≈" = ±1024 MB; trace-mismatch row → Not confirmed; rows for a general U1/U3 vs U2 difference (Refuted), a partly binding control and disagreeing repeats (Not confirmed) | outcomes without a row; B2f already states the refuting relation |
| A4 | B3a | copy the built distribution and add the YARN module jars from `~/.m2`; JDK 8 in `hadoop-env.sh`; a `python3` filter for the REST selection; port list | the base distribution lacks the YARN jars; `jq` is not installed |
| A5 | B3c | distributed-shell jar from `~/.m2` | not in the distribution's `share/` |
| A6 | B3e | ResourceManager restarted per run, NodeManager once; node memory from REST; 180 s wait timeouts; first-trigger check at step 2.3; when the 120 s window starts | `yarn node -list` prints no memory; the filed steps had no stop conditions |
| A7 | B3g | creation-order rule; rows for a general C1/C3 vs C2 difference (Refuted), allocated vs resident disagreement and a partly binding control (Not confirmed); B3h's discard rule | outcomes without a row |
| A8 | B3f | "steady-state" = median of the 2-s samples in the window; "≈" = ±1024 MB / ±10 % RSS | the filed text did not say how the window is summarized |

**Runbook-defect amendment after the freeze (2026-11-06).** A9, B2e step 1: u3's AM is launched by heartbeating until its attempt is ALLOCATED instead of `MockRM.launchAndRegisterAM` (which sends two heartbeats that go to u1's and u2's AMs). Results file §3, defect 1. B1, B2f, B2g, B3f and B3g are unchanged (their text hashes in results §1 still hold); the unit tier restarted. A10, B3a: `cp -r` for the configuration copy (results §3, defect 2); the cluster tier restarted before any daemon had started.

### D2. Stage-4 result, 2026-11-06

[Results file](../../../stage4-runtime-verification/yang/results/yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous.md). Run 1 against the file at sha256 `1afc50c92ada184b083f1c6a176db4665ae5a04c8cfdc20dd530e0c09126280a` (A1–A10; uncommitted, repository HEAD `bd784dba`), node0, JDK 8, Hadoop 3.4.2.

- **Unit tier: Confirmed — does not cap** (B2g row 1). Every `avail`, abs cap, `active` flag, activated sum and effective max as in B2f. u3 held 41984 MB in U1, U2 and U3 (guarantee 0, 0.05, 0; limit 0.2, 0.2, 0.4); the positive control U4 held it at 25600 MB. Three repeats identical.
- **Cluster tier: Confirmed — does not cap** (B3g row 1). u3 7168 MB allocated, 6 hog containers, 3648.0 / 3647.9 / 3647.5 MiB RSS in C1 / C2 / C3 (`absoluteCapacity` 0 / 5 / 0); the control C4 held it at 3072 MB, 2 containers, 1215.8 MiB. The policy's own `availableCapacity` during the windows was 0.001 / 0.051 / 0.001 / 0.001, as traced.
- **Outcome class: true negative.** No run 2 (exact, observed readings; the control moved).
- **Runbook defects:** (1) B2e step 1, `MockRM.launchAndRegisterAM` sends two heartbeats, which go to the earlier users' AMs → A9; (2) B3a, `cp` of `etc/hadoop/*` needs `-r` → A10. Each tier restarted; no prediction or conclusions row changed.
- **For stage 3:** the knob's default (P unset = 0) is not covered (results §1, R1); the distributed-shell AM's RSS is not separated (R6). Neither affects the verdict.
