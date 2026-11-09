# 2026-11-04 H3 `time_budget`原因分类补充

## 目标与基线

继续细化H3报告原因分类。源码复核确认`completed_persisted_before_queue_update`、`budget_persisted_before_queue_update`和`time_budget_persisted_before_queue_update`位于`publish_report`同一个持久化后结算回调；`time_budget`与`node_budget`都会形成`BudgetLimited`。因此这批检验实际W1-C已出现的`time_budget`报告字节如何通过同一个已覆盖K点，不构成独立H3逻辑窗口。

本批只增加原因分类场景：在相同报告保存后结算位置使用`time_budget`合成报告，经过既有持久化路径和相同的原子握手认证、强杀与恢复断言。只增加测试专用检查点/回归材料，不改变公开API、schema、生产终态或重试语义。

## 实施步骤

1. 扩展现有`h3_2b_cross_chain_windows_recover_after_process_kill`矩阵，新增`time_budget_persisted_before_queue_update`原因分类案例。子进程合成报告必须是`time_budget`，并经过既有`publish_report`持久化路径；父进程确认完整operation/job修订链、报告引用和报告哈希、`budget_limited`终态、无执行器调用及冻结/领取计数后才终止。
2. 恢复重开后确认operation仍accepted、job仍是同一`budget_limited`终态、报告仍标记`time_budget`且字节摘要一致；队列无queued/running项，`claim_next`为空。再开第二次，文件字节和revision数保持稳定。
3. 先观察新增聚焦测试失败，再实现测试专用检查点；聚焦测试通过后运行CLI测试、Rust格式检查、workspace全目标Clippy、默认串行workspace测试和相关Python schema回归。Cargo命令全部使用独立target及`--offline --locked`。
4. 把当前任务表、H3证据映射、验证记录、路线及本交接更新到实测结果；刷新当前源码包和Git工作区状态包。旧构建记录仍按其原source/state身份解释。

## 验收与停止条件

握手须有超时并认证完整marker；不完整marker、超时、交叉链不匹配或报告绑定失败时停止，保留测试目录和日志。该原因分类用例只说明`time_budget`字节在已覆盖的budget_limited提交点后保留稳定，不关闭新的逻辑点；其他预算原因、报告来源、真实执行副作用、其他调度、逐syscall故障、断电和介质故障继续单独开放。

本批不运行doctor、生产引擎、runner、worker、FFI、真实分析或部署；不创建研究scope，不提交或推送。执行器调用和研究消费不从该回归推断。

## 验证记录

- 先运行新增矩阵用例，观察到无`time_budget`挂点时子进程退出101且父进程未见marker；加入测试挂点后，聚焦强杀矩阵**1 passed**。
- CLI：`cargo test -p ygo-cli --offline --locked --target-dir target/h3-time-budget-recovery -- --test-threads=1`，**127 passed**。
- Rust workspace：默认串行，`--offline --locked`，**480 passed、36 ignored、0 failed**；完整日志见[TESTING](../../TESTING.md)。
- `cargo fmt --all -- --check`、workspace全目标Clippy及相关schema **16 passed**；Python pytest有一条既有`cache_dir`未知配置警告。

最终复核确认这是报告终态已覆盖K点上的原因分类补充，不新增H3逻辑窗口。来源包/工作区状态包在最后所有源码和文档修改后统一刷新；现有旧build record仍绑定原source/state身份。
