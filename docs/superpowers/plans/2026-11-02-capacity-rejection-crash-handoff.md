# 容量拒绝持久化后协调器返回前：限定强杀验收

已有accepting操作占用容量时，第二操作保存`analysis_queue_full`拒绝；测试子进程在保存后、协调器返回前原子发布握手并暂停。父进程认证两条操作链、摘要及转换，确认无冻结、领取、任务和报告后终止子进程。重开持锁完整认证后，首个accepting仅追加一次unknown，拒绝操作维持两条修订；无活动队列或可领取任务，第二次重开字节稳定。重启后同指令再次提交被拒绝操作返回原拒绝，不获得冻结票据、不更改持久材料。

最终聚焦测试1 passed，fmt和workspace全目标Clippy通过。workspace离线串行回归91组、444 passed、0 failed、36 ignored；日志为`target/w1h322b-process-kill/capacity-rejected-workspace.log`。该回归早于新增测试证据输出和重复提交断言；后两项由最终聚焦测试验证，不能称为同一版本的全量回归。

最终聚焦证据位于`target/w1h21-analysis-operation-tests/dcb58e5a7320499b583a6abf53ee1b3d/`；握手和事件日志、终止结果、前后哈希清单与持久材料保留，恢复后5项文件哈希已与磁盘核对。哈希记录不构成逐阶段原始字节备份。

仅关闭容量拒绝保存后、协调器返回前的此一合成窗口；配置变更、准备失败、其他调度、HTTP传输期间强杀、逐syscall、断电和介质故障继续开放。没有真实runner、worker、FFI、原生研究或消费账本调用；普通启动继续`analysis_not_configured`，W1-C与P4-R5保持开放。
