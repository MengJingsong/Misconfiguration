# C1 第三轮实验计划：快副本确认、慢 victim 排队

日期：2026-11-10。状态：设计建议，尚未执行；本文保存本次讨论的计划，不表示已有第三轮结果。保留同目录 `C1-design-v3.md` 原草案，本文补充其验证条件、归因限制和实验顺序。

## 1. 目标与已有证据

研究问题：在各连接私有额度 Q、endpoint reserve E 和 global reserve G 均遵守其合同的情况下，增加实际活跃发送连接能否增加同时存活的物理内存，并导致固定预算下的 OOM？

参考记录：

- [第一轮：default Q](../internode_application_receive_queue_capacity--multiplicity--run1-defaultQ.md)：副本扇出下发送端 heap OOM；队列占用大幅涨落；未建立 multiplicity-OOM 归因。
- [第二轮：custom Q](../internode_application_receive_queue_capacity--multiplicity--run2-customQ.md)：RF=1、victim 为唯一副本，8 个协调实例存活，堆约 336–384/1024 MiB；队列占用波动约 ±8–10 MiB。总队列约 266 MiB，改变 Q 主要改变 exclusive/reserve 的分摊，总占用不随 Q 增长。384 MiB direct budget 下确有负载触发的 OOM，但 Q=4 和 Q=64 都失败，不能归因为私有额度叠加。
- [共同验证协议](../../../../../verification-protocol.md)。

上述波动数字是记录中的队列占用波动，不是整个进程物理内存的误差范围。第二轮的闭环负载解释是有证据的工作假设，尚不能由 800/1500 客户端线程的两点比较推断所有负载条件下都不可突破。

第三轮先回答“能否稳定到达 admission ceiling，同时发送端不持续积压”，再决定是否进行 OOM 边界测试。增加机器或压低 victim 预算不是第一步。

## 2. 先补齐发送端 OOM 归因

优先使用第一轮已有日志和 dump；若原始材料不存在，明确记录缺失，不把推测写成确认结论。必要的新诊断运行应单独标记。

1. 按时间定位最早失败：Java heap OOM、direct OOM、kernel/cgroup kill，还是 Cassandra 失败处理中的后续 OOM。保留原始错误栈和 GC 时间线。
2. 若有 heap dump，检查 dominator/retained size 和引用链，区分待确认 mutation、请求 callback、出站队列、复制/序列化临时对象及其他对象。累计分配量不能替代存活量。
3. 对齐 offered/completed writes、outbound pending/sent/expired/dropped、响应等待时间、heap/GC 和每主机 cgroup 使用量。记录指标的具体含义，避免不同计数口径直接相减。
4. 第二轮拓扑变化后存活说明拓扑很重要，但不足以单独证明第一轮的具体对象根因。第三轮也不能预设“快副本确认后所有协调端对象马上释放”。

产物：一页证据表，列出首次错误、主要存活对象、积压位置、释放/过期路径、支持证据与仍未知部分。

## 3. 固定拓扑，分离副本数与发送实例数

- 一个慢 victim：唯一测量和 exhaustion 目标。
- 一个快副本：与 victim 一起持有所有测试 key 的副本；正常处理写请求。
- N 个 coordinator-only 实例：不持有测试数据副本；成员数量保持不变，通过负载路由选择实际活跃实例。
- 使用 NTS 将副本固定为 victim DC 的 1 个及 fast DC 的 1 个，CL=ONE。验证实际路由和确认行为，不能仅凭配置认定快副本满足了请求。
- 客户端/控制器和快副本尽量避免与 victim 争用资源；记录实例到物理主机的映射和共享资源。
- 固定消息形状，例如约 1 MiB 的 LARGE mutation；验证每个 peer 实际活跃的连接类型 k。本文主设计 k=1。
- 保持 E=128 MiB、G=512 MiB；Q 的 custom/default 标签独立记录。victim 的 apply-delay、concurrent_writes 和 timeout 均属于支持性偏离，逐项保存配置差异。

快副本确认只是解除客户端对慢 victim 的直接等待；它是否会让 victim 队列达到上限，以及发送端是否安全回收积压，都是待验证假设。

## 4. 测量与控制波动

各组从干净进程和等价的数据状态启动；固定预热程序、消息大小、总发送速率/总并发预算、数据分布、后台任务策略和测试时长。预先创建 schema，避免并发压测中建表失败。

同步采集以下量：

| 层次 | 测量内容 | 用途 |
|---|---|---|
| 客户端 | offered、accepted/completed、错误、延迟、实际 outstanding | 确认负载和有效完成，不以线程数代替实际并发 |
| coordinator/快副本 | heap/GC、direct、进程/cgroup 内存、outbound pending/expiry/drop、处理率 | 判断是否转移了瓶颈及是否持续积压 |
| victim admission | 每连接 using/exclusive/reserve、全局和 endpoint reserve、throttle 增量、received/processed/expired | 验证额度合同、实际活跃 N 和饱和状态 |
| victim 物理内存 | JVM direct、BufferPool、heap/GC、RSS/RssAnon、cgroup current/events；必要时 NMT | 将计费字节与物理占用联系起来，避免只看 counter |

先用约 250 ms–1 s 的采样验证开销和峰值可见性，再固定采样方法。顺序读取各连接不是原子快照，需记录采样跨度；精确的瞬时总量若无法取得，应报告误差和归因限制。

区分队列涨落、GC、buffer pool 保留、消息过期和后台维护。不要把机制本身的排空周期简单滤掉。对稳定窗口报告中位数、分位数和峰值；对 OOM 保留失败前时间线。强制 GC、heap histogram/dump 等侵入式手段用于单独诊断或失败后，不在正式性能组中反复执行。

## 5. 分阶段执行及进入条件

### 阶段 A：拓扑与低负载检查

验证多个 key 的副本确实为 victim 和 fast，协调节点不存储副本；确认活跃 inbound handlers 和连接类型。验证快副本的健康状态及延迟，在 victim 变慢时观察完成率是否仍高于 victim 的处理率。先有无注入的基线，再测试声明过的延迟注入条件。

### 阶段 B：饱和与发送端稳定性校准

使用宽裕的 victim 诊断预算，固定 N（建议先 N=4，再 N=8）、Q=4 MiB，分级提高总发送速率，每级保持足够长以覆盖实际配置的请求超时/积压过期周期。记录 offered 与实际到达速率。

进入下一阶段必须同时满足：

1. 快副本维持有效完成；慢 victim 不再决定客户端主要完成速率。
2. victim 队列接近模型上限，G 与各连接 exclusive 的占用得到观测支持，并出现对应 admission throttling。不能仅凭累计 throttle 非零声称当前持续饱和。
3. coordinator、客户端和快副本的 outstanding 及物理内存不持续增长；发送端没有 OOM，能够停止负载并排空。
4. 清楚分离计费占用和物理内存，测量信号足以超过重复组的波动。

若不满足，定位限制来自发送窗口、outbound admission、超时/过期、快副本处理率还是 victim 排空。记录保护效果及测试范围；不通过无限加压或直接降低 victim 预算绕过该阶段。

### 阶段 C：额度与 multiplicity 的非破坏性对照

模型（k=1）：`A_max = N*Q + min(G, N*E)`，它是可准入计费字节的上限，不是必然达到的队列占用，更不是物理内存大小。

- S1：固定 N=8，比较 Q=4/16/64 MiB。在可持续负载下验证总计费占用及物理内存是否随 Q 增长，而不只是 exclusive/reserve 重新分摊。
- S2：固定一个经校准选定的 Q，优先比较 N=4 与 N=8，匹配总负载和总 outstanding 上限。确认两组 G 都实际饱和。
- N=1 可作辅助基线，但其 reserve 最多为 E=128 MiB。N=1→4 同时增加可用共享 reserve，不能用 `G+N*Q` 描述全部各组，也不能把全部增长归为 private allowance。
- reduced-Q：固定 N、预算、负载等，将 Q 降低；Q=1 MiB 是否合适须验证消息边界和实际合同。观察总内存是否降低，不仅观察 exclusive counter。

如果 S1 仍只重分摊，总内存不随 Q 变化，则本负载范围不支持 Q 因果归因。若增加 N 只提高实际输入吞吐，也需与“私有额度增加”分开解释。

### 阶段 D：固定预算下的边界与因果干预

只有阶段 C 支持物理内存增量后，才根据独立校准选择并冻结 victim direct budget。应覆盖正常启动和参考负载，不能靠启动 OOM 建立实验结论。cgroup 作为外层隔离预算，避免先于目标 direct budget 触发。

在固定预算、构建及匹配负载下寻找低 Q/N 存活与高 Q/N 失败的邻近边界；几何步进后细化，不把 3072 MiB 存活直接称为 384 MiB 失败的“最近存活点”。至少各 3 次干净启动重复，报告 n/N 及峰值分布。

在失败点降低 Q 或限制实际活跃 N，检验 OOM 是否消失，同时报告完成率、拒绝率和延迟。干预靠停止所有有效工作获得存活，不算充分的保护证据。

## 6. 判定与停止条件

支持 C1 的证据链：本地合同仍成立 → 可达同时占用随私有额度叠加增加 → 独立物理指标支持相应增量 → 固定预算下可重复失败 → 降低该增量的干预可消除失败且保留有效工作。

分别报告机制和终局：机制成立/不支持/未解决；direct OOM、heap OOM、kernel kill、GC 服务损失、保护性限流或测试范围内无失败。发送端/快副本失败不算 victim 的 C1 正例。

第三轮未达 ceiling，只能得到该拓扑、消息、速率和超时范围内的负面或受限结论；不能因为做满三轮就证明 C1 在所有条件下不成立。可以停止本批并 parked，明确重新开启需要什么新证据。

建议本批预算：环境就绪后总计不超过 3 小时；每个校准负载窗口最多 5 分钟；若规定时间内不足以完成边界与重复，则保存进度并结束本批，不降低证据标准。发生 sender/fast OOM、持续无界积压、控制器受压或错误目标耗尽时停止该组。每个预期 victim OOM 后保存首次错误并恢复，不自动扩大规模。

## 7. 产物及执行边界

仅使用已分配且研究者控制的节点；victim 每次只运行一个测量实验。完整日志、数据和 dump 位于本地磁盘，仓库只保存小型证据摘录。保护控制器，清理时仅删除本次创建的进程、网络别名、规则和数据，核验清理结果。

第三轮案例应包含：冻结的运行设计、源代码/构建版本、完整配置差异、可执行 harness、每组实际 N/吞吐/占用/物理内存、原始日志位置、重复结果、干预、失败及归因限制。更新索引时保留前两轮证据，不重写旧预测。

本次请求仅保存计划：没有启动节点或压测，没有修改原 v3 草案，没有 commit/push。
