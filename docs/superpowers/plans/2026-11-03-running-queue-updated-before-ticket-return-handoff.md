# W1-H3补充K窗口：running队列更新后、领取票据返回前

2026-11-03按[H3.1窗口映射](2026-11-02-h3-evidence-gate-map.md)完成一个独立子进程终止点。原计划中的首次`accepting`保存后、冻结前窗口已在2026-11-02验收；本交接记录的是另一个尚未覆盖的running领取边界，不重复计算前项证据。

## 窗口与测试挂点

`DurableAnalysisCoordinator::claim_next`先持久化job的`running`修订，随后由队列应用状态更新、移除`queued`并设置`running`，再核验冻结资产身份，最后才返回`Some(DispatchTicket)`。本测试在资产身份核验成功后、返回票据前触发`#[cfg(test)]`检查点。

它填补两个相邻K点之间的空白：[running修订持久化后、内存队列更新前](2026-11-02-running-crash-handoff.md)和[票据已返回、执行器调用前](2026-11-03-ticket-return-crash-handoff.md)。新事件只在目标测试阶段记录，避免改变其他测试的既有事件序列。该挂点不覆盖资产身份核验失败分支。

测试子进程将目标checkpoint marker写入临时文件、调用`sync_all`后原子重命名。父进程在20秒期限内等待marker，核对其内容与请求stage完全相同，再认证持久状态后终止子进程；超时或认证不符会使测试失败，`ChildGuard`负责杀死并回收未退出子进程。生产构建不包含该检查点。

## 强杀前认证

父进程核对operation/job修订封套、前驱哈希、记录摘要、命令和冻结输入交叉绑定，并确认事件顺序恰为`freeze → claim → queue_updated`。当时operation仍为`accepted`；job为`running` revision 2。报告数和假执行器调用数均为0，随后才强制终止子进程（证据记录`exit code: 1`）。

强杀后以真实目录锁重开并执行完整认证。恢复只追加一次job `unknown`修订；operation保持原状态。活动队列为空，`claim_next`无可领取工作。第二次重新打开不再增加修订，持久材料逐字节稳定。

最终机器证据为[`running-evidence.json`](../../../target/w1h21-analysis-operation-tests/63de9d5c0b61a69652659cef2c305fa2/running-evidence.json)，1,298字节，SHA-256=`b679034cfed0091aef1cc7d611a8e965aea9bc52f167f20a23f1ddb726a2a39c`。operation ID为`deb96b9ce7177d28aec9b2c58d494f6f`，job ID为`83a99600cbdfe64849c2df08bf124612`；事件为`freeze, claim, queue_updated`，报告和执行器调用均为0，稳定重开次数为2。

## 验证

最终聚焦强杀测试1 passed；相邻HTTP running强杀回归4 passed。operation parent认证补强后，首次重跑发现现有测试辅助函数的状态白名单漏掉`Accepted`，尽管函数已有revision 4转换校验分支；已修正该测试辅助函数，并保留[首次失败日志](../../../target/h3-queue-updated-ticket-return/pre-auth-chain-focused.log)。离线、锁文件固定的workspace串行测试命令退出码为0，workspace全目标Clippy（`-D warnings`）、`cargo fmt --all -- --check`通过。操作、任务、HTTP及通用Python schema回归24 passed、2 skipped；两个skip是显式opt-in的本机快照/报告及实际v2报告用例。pytest另报告项目配置中的未知`cache_dir`选项警告。

完整命令、隔离target位置及失败修正记录见[验证记录](../../TESTING.md)。

## 范围限制

这是测试专用协调器路径的合成K证据。它不覆盖其他队列调度竞态、真实执行器副作用、报告写入故障、逐系统调用、断电或介质故障；也不认证原生引擎、worker、runner、FFI、消费账本、真实分析、部署或最优性。job恢复为`unknown`不解释为零消费。其他H3窗口继续开放。
