# W1-H3.2-2b-1：跨链关键窗口进程终止验收

日期：2026-11-01。基线为本地 `main / 2f690d5`，保留先前两处未提交的静态路线复核文档。本批只验证四个真实持久化提交窗口的子进程终止及认证恢复；其他 H3.2-2b 窗口和产品门禁仍开放。

## 实现

`durable_crash_window_tests.rs` 在同一测试函数中以 `current_exe --exact` 启动隔离子进程。父进程通过子进程专属环境值指定阶段和握手文件；子进程只在对应持久化边界完成后写入并同步握手标记，随后停驻。父进程有 20 秒有界握手等待，先读原始修订文件核对阶段，再终止并回收该测试子进程。失败退出会保留 child-output 日志；RAII 清理器确保断言失败时仍尝试终止子进程。

所有提交边界钩子仅在 `cfg(test)` 编译，环境控制只传给子进程；没有生产配置项、HTTP/CLI/schema变更或额外依赖。恢复使用新协调器和实际目录锁；先认证完整跨链材料，再按现有恢复规则分类。每个案例都执行第二次重开，并逐字节比较 operations/jobs/reports 文件（排除锁元数据）以证明修订和报告稳定。

## 四个窗口和恢复结果

| 握手点 | 强杀前已核实的持久状态 | 首次新进程恢复后的状态 |
|---|---|---|
| 冻结输入修订已提交，job尚未提交 | accepting含冻结输入和job ID；job目录不存在 | operation变为unknown；不创建job，不派发 |
| queued job已提交，accepted关联尚未提交 | operation仍accepting；job为queued | operation补为accepted；job分类为interrupted，不重新排队 |
| 报告已保存并重读验证，终态job修订尚未提交 | operation accepted；job running；reports中恰有孤立报告 | job分类为unknown且不带report引用；孤立报告保留，不宣称完成 |
| 重开时association repair已提交，job分类尚未提交 | operation accepted；job仍queued | job只补为interrupted；重复重开不再追加 |

每例在恢复后均确认活动队列为空，`claim_next`无可派发任务，第二次重开后修订文件字节及报告集合完全稳定。没有启动worker或引擎执行器；本批新增native research、真实runner/worker和引擎FFI调用均为0。没有推断真实收费调用为零。

## 负例与限制

新增有效但不匹配的跨链冻结输入/job绑定负例：完整恢复认证拒绝打开，operation/job修订字节不变，既无operation revision 4也无job revision 2。既有回归还覆盖损坏的后续operation修订阻止较早修复、非法job转换阻止association修复，以及损坏/错误引用报告拒绝查询；这些分别保留其测试来源，不伪称由新进程矩阵重复覆盖。

本批仅覆盖四个声明的逻辑提交点，不覆盖其它任务/operation状态组合、所有调度排列、逐文件系统syscall强杀、断电、介质损坏、网络文件系统或真实报告来源。进程强杀测试用的是当前CLI测试二进制的子进程，不是正在使用的工作服务。普通工作台继续 `analysis_not_configured`。

## 验证

所有构建使用忽略目录 `target/w1h322b-process-kill/cargo` 和 `--offline --locked`：

- `cargo test -p ygo-cli --offline --locked --target-dir target/w1h322b-process-kill/cargo -- --test-threads=1`：unit及integration合计103 passed、0 failed；其中durable operation测试19 passed。
- `cargo test --workspace --offline --locked --target-dir target/w1h322b-process-kill/cargo -- --test-threads=1`：444 passed、0 failed、36 ignored，共91个结果组。完整输出在 `target/w1h322b-process-kill/workspace.log`。
- HTTP/job/operation Python schema：16 passed。
- workspace all-target Clippy `-D warnings`与`cargo fmt --all -- --check`通过。

定向子进程测试没有访问外网、部署、doctor、修改dist或真实资产，也没有触碰旧研究材料、Tenki pin或历史SHA清单。下一步仍需单独收敛H3.2-2b余下逻辑窗口和调度范围；完成本批不表示整个H3.2、W1-C或P4-R5关闭。
