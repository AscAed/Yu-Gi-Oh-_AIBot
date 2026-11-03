# H3 running中假执行器返回后的进程终止交接

日期：2026-11-03

## 窗口映射与范围

按[H3.1证据门禁映射](2026-11-02-h3-evidence-gate-map.md)先核对了相邻证据：既有`running_job_crash_after_executor_started_recovers_unknown_once`在假执行器内部、调用返回前终止；2b-1的“报告后终态前”K则发生在报告文件已持久化后。生产`dispatch_pending`先等待执行器返回，再处理结果并调用`publish_report`。本批单独覆盖中间的边界：假执行器已经返回`Ok(report)`，`publish_report`尚未开始。

测试钩子只在`cfg(test)`编译路径中，于`catch_unwind`返回后、结果匹配分支前发布临时文件、`sync_all`并原子重命名的握手，然后等待父进程终止子进程。它不改变公开API、schema或自动重试语义，不启动生产worker、ocgcore、runner或FFI。

## 通过证据

测试名为`workbench::analysis_http::tests::running_job_crash_after_executor_return_before_report_publish_recovers_unknown_once`。父进程只在读取完整marker后继续，并认证operation/job所有revision封套、记录摘要和前驱哈希链，核对accepted operation与running job的跨链ID、命令摘要、冻结输入绑定、运行revision 2及无报告状态。事件顺序为各一次`freeze`、`claim`、`fake_executor_entered`、`fake_executor_returned`；marker记录`executor_result=ok_report`、`report_persisted=false`、`worker_spawned=false`及`engine_or_ffi_called=false`。握手等待上限为20秒，失败日志与子进程材料留在隔离target目录。

workspace串行复验的operation `641db2385f295d9c9a401946a609d02d`在终止前有4个有效revision，状态为`accepted`；job `1fff0f583e0692553efaaa6687239d83`终止前有2个有效revision，状态为`running`。父进程调用`DurableAnalysisCoordinator::open_operations`，使用真实存储目录锁和跨链恢复路径重开。job只追加revision 3=`unknown`；operation仍为4个revision，没有报告文件，queued/running槽为空且`claim_next`无工作。第二次重开不产生新revision，持久材料哈希与第一次恢复相同。

机器证据：[executor-return-crash-evidence.json](../../../target/h3-executor-return-kill/b1c9198daca4c34e5b943e2ba3717d71/executor-return-crash-evidence.json)。相同聚焦测试及完整CLI套件也独立通过；其余测试生成的隔离证据均保留在`target/h3-executor-return-kill/`。

随后为完整握手再加了marker PID与实际子进程PID相等的父进程断言。最终聚焦复跑通过，记录的operation为`705375129a5c33f20d49e99dbabc7c4a`、job为`18dfd095e19ec1e6421cd65a833217a3`，PID核验后的机器证据见[`最终聚焦证据`](../../../target/h3-executor-return-kill/4416203ed30fe3949bd16db6e6d24942/executor-return-crash-evidence.json)。

## 验证

- 聚焦进程终止测试：1 passed；格式化后复跑通过，完整CLI及workspace运行中也重复通过。
- 完整`ygo-cli`测试：121 passed，0 failed，0 ignored。
- `cargo fmt --all -- --check`：通过。
- workspace全目标Clippy，`-D warnings`：通过。
- 默认串行workspace测试：退出码0。仓库声明的冻结资产、引擎、原生研究和人工准备opt-in用例保持默认忽略。
- operation/job/HTTP与通用Python schema回归：24 passed、2 skipped。两项skip为本机snapshot/report和实际v2 report的显式opt-in。禁用pytest缓存插件后，项目`cache_dir`配置产生一条未知配置警告，不影响结果。

workspace与完整CLI套件结束后，为marker增加PID对应断言；随后最终源码的聚焦测试1 passed、格式检查和workspace Clippy再次通过。workspace完整串行套件及Python schema回归没有因这项仅增强父进程握手认证的断言重复运行。

```text
cargo test -p ygo-cli --offline --locked --target-dir target/h3-executor-return-kill/cargo --lib workbench::analysis_http::tests::running_job_crash_after_executor_return_before_report_publish_recovers_unknown_once -- --exact --nocapture --test-threads=1
cargo test -p ygo-cli --offline --locked --target-dir target/h3-executor-return-kill/cargo -- --test-threads=1
cargo clippy --workspace --all-targets --offline --locked --target-dir target/h3-executor-return-kill/cargo -- -D warnings
cargo test --workspace --offline --locked --target-dir target/h3-executor-return-kill/cargo -- --test-threads=1
cargo fmt --all -- --check
$env:PYTHONDONTWRITEBYTECODE='1'; py -m pytest -p no:cacheprovider -q -ra --basetemp target/h3-executor-return-kill/pytest-tmp tests/test_workbench_analysis_operation_schema.py tests/test_workbench_analysis_job_schema.py tests/test_workbench_analysis_http_schema.py tests/test_schemas.py
```

以上构建与Rust测试使用隔离target和`--offline --locked`；没有联网构建。没有运行doctor、真实引擎、runner、worker、FFI、研究scope或部署。

## 未覆盖

这只认证测试假执行器已返回报告但报告尚未发布时的合成恢复。真实执行器副作用、报告序列化/写入中的每个故障点、领取后其他调度顺序、取消竞争、逐syscall强杀、断电及介质故障仍开放。W1-C报告来源、独立FFI/消费计量、完整搜索、P4-R5部署与全局最优门槛不受此证据影响；普通启动仍为`analysis_not_configured`。
