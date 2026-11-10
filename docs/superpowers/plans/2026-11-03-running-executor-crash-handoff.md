# H3 running后假执行器进入窗口交接

日期：2026-11-03

## 范围

按[H3证据门禁映射](2026-11-02-h3-evidence-gate-map.md)选择一个边界：operation已accepted，job `running` revision已持久化，派发已进入测试专用假执行器且调用尚未返回时，终止子进程。测试不调用生产worker、ocgcore、runner或FFI，不改变公开API、schema或自动重试语义。它覆盖一个合成逻辑K窗口，不关闭其他H3窗口。

## 通过证据

测试名为`workbench::analysis_http::tests::running_job_crash_after_executor_started_recovers_unknown_once`。父进程在杀进程前验证握手marker完整，operation及job修订封装、记录摘要和前驱哈希链有效，并核对跨链job ID与冻结输入绑定。事件为一次freeze、一次claim和一次`fake_executor_entered`；检查点标记`worker_spawned=false`及`engine_or_ffi_called=false`。

operation `9c00393f49ddce2d1f6e113688331fbc`终止前有4个有效revision，最终状态accepted；job `4dbf92a998974a486cec0334086e33b5`终止前有2个有效revision，最终状态running。父进程随后调用`DurableAnalysisCoordinator::open_operations`，由真实持久存储目录锁和跨链恢复路径重开。只追加job revision 3=`unknown`；operation保持4个revision，没有report，队列没有queued/running任务，`claim_next`不返回工作。第二次重开不增加revision，持久文件SHA-256映射与第一次恢复结果相同。

机器证据：[running-executor-crash-evidence.json](../../../target/h3-running-executor-kill/f1e819d9c6a28ae79af8afcbbac45942/running-executor-crash-evidence.json)。两次测试夹具初始化失败的原始日志和部分隔离存储仍保留，失败原因及修正见[失败索引](../../../target/h3-running-executor-kill/test-harness-failures.json)。失败运行未到目标marker，不计入强杀证据。

## 验证

- 聚焦强杀测试：1 passed。
- 完整`ygo-cli`测试：119 passed。
- `cargo fmt --all -- --check`：通过。
- workspace全目标Clippy，`-D warnings`：通过。
- 默认串行workspace测试：退出码0；显式opt-in的冻结资产、原生研究和人工准备案例仍忽略。
- operation/job/HTTP及通用Python schema回归：23 passed，2 skipped。跳过项是本机snapshot/report和实际v2 report的显式opt-in测试。

以上Rust构建与测试均用隔离`target/h3-running-executor-kill/cargo`和`--offline --locked`。完整命令记录在[TESTING](../../TESTING.md)。

## 未覆盖

此证据不证明真实执行器副作用的事务边界、真实引擎/FFI恢复、领取票据返回后的每个时点、取消与执行的全部竞争顺序、逐系统调用中断、断电或介质故障。其他H3窗口保持开放；本项也不构成W1-C、原生研究、部署或最优性资格。
