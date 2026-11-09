# 2026-11-04 `unknown`终态保存后、队列结算前窗口

## 目标与基线

H3证据映射仍把`unknown`终态提交和其他恢复状态组合列为开放。已覆盖的相邻场景包括：进程在执行仍处于running时被终止，重开时将running分类为unknown；以及恢复时追加operation/job分类修订。当前`DurableAnalysisCoordinator::mark_unknown`会持久化`CompletionUncertain`导致的unknown终态，再清除内存running槽，但这个显式终态提交与内存队列结算之间没有子进程K证据。

本批增加一个不同于time_budget场景补充的H3逻辑窗口：显式`mark_unknown`已将job revision 3=`unknown`持久化、`settle_with_persist`尚未清除队列running槽时终止测试子进程。它只验证合成协调器，不代表真实worker或不确定消费已被认证。

## 实施与验收

1. 先扩展现有子进程矩阵，使其调用真实`mark_unknown`持久化路径，并观察红测：无匹配测试检查点时，父进程不得收到该窗口的完整握手。
2. 在`mark_unknown`持久追加revision之后、返回`settle_with_persist`前增加`cfg(test)`检查点；复用带超时的临时标记、`sync_all`和原子重命名机制。
3. 父进程只在marker完整后终止子进程。终止前认证operation链、job三修订封套/前驱/记录哈希、accepted→queued→running→unknown迁移、`CompletionUncertain`、零报告、恰好一次冻结/领取及零执行器调用。
4. 使用真实目录锁重开两次，确认显式unknown修订保留，不追加revision，不派发、不领取任务，队列为空且持久材料字节稳定。
5. 运行新增聚焦子进程测试、CLI测试、fmt、workspace全目标Clippy、默认串行workspace测试及相关schema回归；全部Cargo调用使用隔离target和`--offline --locked`。失败时保留失败材料，不关闭本窗口。

本批不改公开API、schema、生产恢复/自动重试语义；不运行doctor、引擎、runner、worker、FFI、真实分析或部署；不创建研究scope，不提交或推送。

## 当前状态

已完成一个合成H3逻辑窗口。无挂点时，聚焦矩阵子进程执行到保护性panic、exit 101，父进程没有收到marker，红测符合预期。加入`#[cfg(test)]`检查点后，聚焦矩阵**1 passed**（最终运行22.88秒）。父进程在终止前认证操作修订链、job三修订封套/前驱/记录哈希、accepted→queued→running→unknown迁移及`CompletionUncertain`；报告为0，freeze/claim各1，事件日志仅有`freeze`和`claim`。真实锁重开两次后job仍为revision 3 `unknown`，未追加修订，没有队列或可领取工作，持久文件字节稳定。

最终验证均使用隔离目录`target/h3-time-budget-recovery`和Cargo `--offline --locked`：聚焦测试1 passed；CLI默认串行测试127 passed、0 failed、0 ignored；workspace默认串行测试92个结果组，480 passed、0 failed、36 ignored，完整日志SHA-256=`BFFE89CF15FA9B196A8D42E4D3BAA9B2B3CFAC16504F16EEA8FEDEF44EA007A`；fmt与workspace全目标Clippy通过；相关schema回归16 passed，pytest有一条既有`cache_dir`未知配置警告。完整范围和36个opt-in忽略项见[TESTING](../../TESTING.md)。

此结果只关闭“显式`mark_unknown` revision持久化后、内存队列结算前”这个点。报告来源、真实执行/worker、FFI、消费、其他H3状态组合/调度及syscall/断电/介质故障仍开放。公开API、schema和生产重试语义没有修改；未运行doctor、runner、worker、引擎、FFI、真实分析或部署，未创建scope，未提交或推送。当前开放清单见[TASKS](../../../TASKS.md)和[证据映射](2026-11-02-h3-evidence-gate-map.md)。
