# H3到W1-C的证据门禁映射

2026-11-02工作区静态核对；当前状态以[TASKS](../../../TASKS.md)、具体测试日期和版本以[TESTING](../../TESTING.md)为准。P/U/R分别为发布前失败、发布后不确定、写后复读失败；L为HTTP响应丢失，K为指定逻辑点子进程终止。标记的是对应材料的有限范围，不推断同一行全部分支、调度或系统调用均覆盖。

H3.1拟议矩阵要求各边界P/U/R/K，有HTTP回复的线路另有L；因此单个K通过不等于整行或H3完成。H2.2-A的42项对应13种提交场景各P/U/R和重启unknown三项，实际fixture清单可在`crates/ygo-cli/src/workbench/fault_matrix_tests.rs`的`logical_publish_fault_matrix_stops_before_followup_and_preserves_reads`及`unknown_restart_classification_faults_preserve_certifiable_bytes`核对。恢复追加P/U/R另有`recovery_publish_faults_resume_only_remaining_revisions`，仅覆盖accepted/4及interrupted/2，不扩展到全部恢复转换。H2.2-B的16轮同时取消/领取仅观察到领取胜出；取消先完成是顺序用例，不证明两个并发赢家或调度公平。

| 边界 | 已有P/U/R与L | K进程终止已覆盖的具体点 | 仍需验证或判定 |
|---|---|---|---|
| allocated | H2.2-A三故障；2a分配201零字节/截断 | [保存后协调器返回前](2026-11-02-allocated-crash-handoff.md) | HTTP传输中强杀及其他时点不由该K覆盖；丢失ID不承诺找回 |
| 首次accepting | H2.2-A三故障；2a接受202丢失 | [保存后冻结前](2026-11-01-post-w1h322b1-project-route.md#2026-11-02-accepting保存后冻结前进程终止验收) | 其他调度及真实工作服务崩溃 |
| rejected | H2.2-A容量、配置、草稿修订失败各三故障；2a后台旧revision拒绝 | [容量](2026-11-02-capacity-rejection-crash-handoff.md)、[配置身份](2026-11-02-context-rejection-crash-handoff.md)、[合成手牌错误](2026-11-02-preparation-rejection-crash-handoff.md)保存后 | 其他准备错误/路径及其K不能从合成闭包推广 |
| 冻结绑定 / queued / accepted | H2.2-A三故障；2a接受与后续查询 | 绑定后job前、queued后accepted前见[2b-1](2026-11-01-w1h322b1-process-kill-handoff.md)；[accepted后队列更新前](2026-11-02-accepted-crash-handoff.md) | 其他中断点和调度；并非真实执行确认 |
| running / cancelled | H2.2-A三故障；2a取消响应丢失；H2.2-B有限竞争 | [running提交后队列更新前](2026-11-02-running-crash-handoff.md)、[队列更新后、票据返回前](2026-11-03-running-queue-updated-before-ticket-return-handoff.md)、[`claim_next` AssetMismatch已保存、队列结算前](2026-11-03-asset-mismatch-persisted-before-queue-update-handoff.md)、[HTTP派发准入AssetMismatch已保存、队列结算前](2026-11-03-dispatch-admission-asset-mismatch-crash-handoff.md)、[cancelled提交后队列更新前](2026-11-02-cancelled-crash-handoff.md)、[票据返回后、执行器调用前](2026-11-03-ticket-return-crash-handoff.md)、[假执行器进入、返回前](2026-11-03-running-executor-crash-handoff.md)、[假执行器返回、报告发布前](2026-11-03-executor-return-crash-handoff.md) | 其他调度竞态和dispatch准入拒绝原因、真实执行器副作用、report写入中故障和其他实际调度 |
| failed / unknown | H2.2-A failed/3及恢复unknown/3三故障 | [合成analysis_failed提交后](2026-11-02-failed-crash-handoff.md)；[running→unknown已保存、后续queued未分类](2026-11-02-unknown-first-recovery-handoff.md)；[queued/running混合恢复](2026-11-02-mixed-task-recovery-handoff.md) | 其他失败来源、unknown终态提交及恢复状态组合 |
| 报告及终态 | H2.2-A报告文件与completed/3三故障；2a完成/预算报告及读取 | [报告临时文件同步后、正式发布前](2026-11-03-report-temp-crash-window-map.md)、[报告发布后终态前](2026-11-01-w1h322b1-process-kill-handoff.md)、[合成completed后](2026-11-02-completed-crash-handoff.md)、[合成node_budget后](2026-11-02-budget-crash-handoff.md) | 其他budget原因及报告来源，合成报告不证明真实来源 |
| 恢复操作追加 | H3.2-1 accepted/4三故障；[无任务accepting→unknown revision 3的BeforePublish/AfterPublish/Reread](2026-11-02-unknown-operation-fault-handoff.md) | [关联修复后分类前](2026-11-01-w1h322b1-process-kill-handoff.md)、[第一无任务操作unknown后第二前](2026-11-02-partial-operation-recovery-handoff.md)、[混合unknown/accepted第一操作提交后](2026-11-02-mixed-operation-recovery-handoff.md) | 其他操作状态组合、ID排序及提交窗口；单一混合K不扩展为全恢复顺序证明 |
| 恢复任务分类追加 | H3.2-1 interrupted/2三故障；H2.2-A unknown/3三故障 | [双queued](2026-11-02-partial-task-recovery-handoff.md)、[queued/running](2026-11-02-mixed-task-recovery-handoff.md)、[running/queued](2026-11-02-unknown-first-recovery-handoff.md)中第一任务分类后、第二分类前 | 其他顺序及调度仍开放 |

## 2026-11-03 running执行器返回后的补充映射

实施前先把相邻边界与现有证据分开：`running_job_crash_after_executor_started_recovers_unknown_once` 在测试假执行器内部写完握手后、函数返回前终止；H3.2-2b-1 的“报告后终态前”K则要求报告文件已经持久化。生产 `dispatch_pending` 的顺序为持久领取为running、调用并等待执行器返回、处理返回值、再调用 `publish_report`。因此“假执行器已返回成功报告、`publish_report` 尚未开始”是两者之间的独立逻辑窗口；此前没有对应子进程K证据。

| 本批边界 | 现有相邻证据 | 本批验收点 | 保持开放 |
|---|---|---|---|
| running / 报告发布前 | [执行器返回前](2026-11-03-running-executor-crash-handoff.md)；[报告持久化后、终态前](2026-11-01-w1h322b1-process-kill-handoff.md) | 子进程在假执行器返回`Ok(report)`、生产结果分支尚未运行时原子发布握手；父进程认证operation/job链、命令摘要、accepted与running revision及输入绑定，核对唯一claim/executor调用和无报告后终止，再用真实目录锁恢复 | 真实执行器副作用、report写入中故障、所有其他调度次序、逐syscall、断电和介质故障均不由该窗口覆盖 |

2026-11-03该K窗口已按上述边界通过；详细测试结果及机器证据见[交接](2026-11-03-executor-return-crash-handoff.md)和[TESTING](../../TESTING.md)。它只证明测试假执行器返回至报告发布前的合成恢复，不授予真实分析、引擎/FFI、研究账本、部署或最优性资格。

## 下一步与停止条件

原定running→unknown已保存、后续queued尚未分类的合成强杀已按限定范围验收，见[交接](2026-11-02-unknown-first-recovery-handoff.md)。无任务accepting操作追加unknown的P/U/R由[限定故障交接](2026-11-02-unknown-operation-fault-handoff.md)覆盖；混合unknown/accepted顺序也已先完成证据映射，再通过[单一K窗口](2026-11-02-mixed-operation-recovery-handoff.md)。两条操作链和任务直接构造，不能据此声称正常队列并发容量或真实执行。基于这些结果，已将全矩阵筛为一次无自动重试分析所需的最小门禁，并完成[W1-C固定Rabbit输入与资产设计](2026-11-02-w1c-single-rabbit-local-analysis-design.md)；其他H3逻辑窗口、调度与系统/介质故障仍开放。

W1-C默认关闭的显式执行路径和一次只领取一个任务的派发已实现。普通启动仍保持`analysis_not_configured`；假执行器验证配置绑定、报告/终态持久顺序、不确定结果停止派发和重开不重发。2026-11-03另通过running持久化后假执行器已进入、返回前的一次合成强杀，见[交接](2026-11-03-running-executor-crash-handoff.md)；真实执行副作用、其他逻辑窗口/调度与系统/介质故障仍开放。报告合同绑定不认证原生来源。逐syscall、断电及介质故障单列，不因逻辑K通过自动关闭。与研究轨并行的合成观察结果不授予原生、概率或最优性资格。

2026-11-03状态补记：固定Rabbit本机有限分析已按[独立scope](2026-11-03-w1c-single-rabbit-execution-scope.md)执行一次并以`budget_limited/time_budget`结束；用例结果、报告标记和未计量项见[TESTING](../../TESTING.md)。W1-C这一有限运行窗口已关闭，报告来源认证、独立消费/FFI计量、完整搜索和最优性没有关闭。后续研究批次按项目路线复核R1b-3恢复/消费/独立重放scope；不从本页的合成K证据推导原生执行资格。

## 2026-11-03 领取票据返回、假执行器调用前的补充映射

实施前对照当前源码和相邻证据：`DurableAnalysisCoordinator::claim_next`先持久化`running`、更新队列并返回票据；`AnalysisHttpService::dispatch_pending`随后完成准入核对，再调用执行器。现有`running_persisted_before_queue_update`窗口位于`claim_next`内部、票据尚未返回；`running_job_crash_after_executor_started_recovers_unknown_once`则在假执行器已经进入后终止。二者都没有在“票据已返回、执行器尚未调用”这一间隙设置子进程K握手。

| 本批边界 | 现有相邻证据 | 本批验收点 | 保持开放 |
|---|---|---|---|
| running / 票据返回后、执行器调用前 | [running修订保存后、票据返回前](2026-11-02-running-crash-handoff.md)；[假执行器进入后、返回前](2026-11-03-running-executor-crash-handoff.md) | 在成功`claim_next`返回并完成准入核对后、调用假执行器前以原子握手停住；父进程认证operation/job链、运行修订和输入绑定，确认无执行器调用与报告后终止，再以真实目录锁恢复并重复重开 | 真实执行器副作用、其他调度竞态、report写入中故障、逐syscall、断电和介质故障不由该窗口覆盖 |

2026-11-03该窗口按映射通过：子进程在持久领取票据已返回、准入核对完成后，以原子握手停在假执行器调用前；父进程认证完整operation/job链、命令摘要及冻结输入绑定后终止。重开仅追加一次`unknown`，二次重开保持文件字节稳定。详细断点、命令与机器证据见[交接](2026-11-03-ticket-return-crash-handoff.md)及[TESTING](../../TESTING.md)。这只关闭该票据返回后的单一执行器前窗口；本表其余开放项不变。

## 2026-11-03 running队列更新后、领取票据返回前窗口映射

实施前对照`DurableAnalysisCoordinator::claim_next`与`AnalysisJobQueue::claim_next_with_persist`：现有`running_persisted_before_queue_update`在running修订持久化回调内终止，发生于内存队列从queued切换为running之前；[票据返回后交接](2026-11-03-ticket-return-crash-handoff.md)在`claim_next`完整返回并完成派发准入之后、假执行器调用之前终止。两者之间还有一段独立边界：running修订已持久化、内存队列已移除queued并设置running、资产身份核对成功，但`claim_next`尚未把`DispatchTicket`返回给调用方。此前没有在此点发布子进程握手或认证该瞬间的队列状态。

| 本批边界 | 已有相邻证据 | 验收点 | 保持开放 |
|---|---|---|---|
| running / 队列已更新、领取票据返回前 | [running修订持久化后、队列更新前](2026-11-02-running-crash-handoff.md)；[票据返回后、执行器调用前](2026-11-03-ticket-return-crash-handoff.md) | 资产核对成功后、`claim_next`返回`Some(ticket)`前启用测试专用原子握手；父进程认证operation/job修订链及输入绑定，事件为`freeze → claim → queue_updated`，报告/执行器为0；真实目录锁恢复只追加一次`unknown`，队列空且不可领取，第二次重开字节稳定。通过范围见[交接](2026-11-03-running-queue-updated-before-ticket-return-handoff.md) | 其他队列调度竞态、真实执行器副作用、报告写入中故障、逐syscall、断电和介质故障不由该窗口覆盖 |

该窗口是相邻两个K点之间的独立函数返回边界；不覆盖资产身份失败分支，因为失败分支会提交`AssetMismatch`并返回错误。该正向路径已通过子进程握手、父进程完整认证和重复重开检查，详见[本批交接](2026-11-03-running-queue-updated-before-ticket-return-handoff.md)。这只关闭此单点K证据，不能据此关闭running整行或H3.2。

## 2026-11-03 AssetMismatch持久化后、队列结算前窗口映射

实施前先对照两个不同的资产拒绝路径。`DurableAnalysisCoordinator::claim_next`在running revision持久化并更新队列后复核冻结资产；若身份不符，会在同一调用内通过`settle_with_persist`追加`failed/AssetMismatch` revision，然后才把终态应用到内存队列并返回错误。`AnalysisHttpService::dispatch_pending`另有派发准入不符路径，会拿到ticket后调用`fail_asset_mismatch`、停止派发并返回错误。此次只选择前一条路径中的一个K点。

已有`post_claim_package_mismatch_is_a_durable_pre_execution_failure`和`failed_asset_mismatch_settlement_stops_coordinator_after_running_commit`分别验证普通终态失败及失败持久提交故障后重开分类为unknown；H2.2-A故障矩阵覆盖提交故障，不覆盖干净failed revision已保存后进程终止。`running_queue_updated_before_ticket_return`只覆盖资产核对成功的正向路径。现有证据因此未覆盖`AssetMismatch` revision已持久化、而`settle_with_persist`尚未更新内存队列的进程终止点。

| 本批边界 | 现有相邻证据 | 拟验收点 | 保持开放 |
|---|---|---|---|
| running → failed/AssetMismatch | [队列已更新、票据返回前](2026-11-03-running-queue-updated-before-ticket-return-handoff.md)仅为资产身份成功；`failed_asset_mismatch_settlement_stops_coordinator_after_running_commit`覆盖提交不确定并恢复为unknown | 在测试子进程中使冻结资产身份失配；父进程先认证operation/job链、命令摘要及冻结输入绑定，确认job修订为queued→running→failed/AssetMismatch、无报告且无ticket返回，再终止。真实目录锁重开应保留唯一failed终态，队列空且不可领取，第二次重开材料字节稳定 | 派发准入失败的另一分支、其他终态/调度、真实执行器副作用、逐syscall、断电和介质故障不由该K覆盖 |

该映射只针对预执行资产复核失败，不证明调用执行器的HTTP服务路径、真实资产加载或引擎行为。按该映射新增子进程检查点后，聚焦测试通过：父进程看到operation accepted、job queued→running→failed/AssetMismatch，事件为`freeze → claim → asset_mismatch_persisted`，无报告且`claim_next`未返回；终止后真实锁重开保留failed revision，不追加unknown，队列空且不可领取，第二次重开文件哈希稳定。详细结果见[本批交接](2026-11-03-asset-mismatch-persisted-before-queue-update-handoff.md)与[TESTING](../../TESTING.md)。该K仅关闭此单点，不覆盖dispatch准入失败分支或其他系统故障。

## 2026-11-03 HTTP派发准入AssetMismatch持久化后、队列结算前窗口映射

前一节只覆盖`claim_next`内部冻结资产复核失败。另一路由在`AnalysisHttpService::dispatch_pending`拿到`DispatchTicket`后执行派发准入；若固定profile/包身份不匹配，会调用`fail_asset_mismatch`、停止派发并返回错误。需单独检查`failed/AssetMismatch` revision保存与内存队列结算之间的进程终止点，不能由前一K或正常失败回归推断。

| 本批边界 | 现有相邻证据 | 验收点 | 保持开放 |
|---|---|---|---|
| HTTP dispatch准入 → failed/AssetMismatch | 前一节只覆盖`claim_next`冻结资产复核失败；HTTP admission成功路径和ordinary failure不能证明此提交间隙 | 子进程经真实`dispatch_pending`进入fixture准入失配；failed revision已追加后、队列内存结算前发布同步原子握手。父进程认证operation/job链、迁移、命令摘要和冻结输入绑定后终止；真实锁恢复保留failed，无unknown/报告/执行器调用；队列无可领取任务，第二次重开材料稳定 | 其他拒绝原因、调度、真实执行器/资产、逐syscall、断电和介质故障不由此K覆盖 |

2026-11-03该窗口通过。事件严格为`freeze → claim → dispatch_asset_mismatch_persisted`，job状态为queued→running→failed/AssetMismatch；证据文件、SHA-256、命令和完整边界见[本批交接](2026-11-03-dispatch-admission-asset-mismatch-crash-handoff.md)及[TESTING](../../TESTING.md)。这只关闭HTTP dispatch admission中的单一K点；前一节的`claim_next`K和本K不合并为全路径认证。
