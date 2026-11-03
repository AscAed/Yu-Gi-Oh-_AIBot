# HTTP派发准入AssetMismatch保存后、队列结算前进程终止交接

日期：2026-11-03

## 目标与基线

本批按[H3.1逻辑窗口映射](2026-11-02-h3-evidence-gate-map.md)继续检查尚未覆盖的恢复边界。已通过的`claim_next` AssetMismatch K覆盖冻结资产复核失败并保存failed修订后的队列结算窗口；它不覆盖HTTP `AnalysisHttpService::dispatch_pending`取得票据后执行派发准入、再调用`fail_asset_mismatch`的独立路径。该路径原来只有常规失败和持久化故障证据，没有“failed revision成功保存、内存队列尚未结算”时的子进程终止证据。

## 实施与认证

在`DurableAnalysisCoordinator::fail_asset_mismatch`的持久追加回调内增加测试专用检查点。检查点位于`append_expected`成功之后、队列内存状态应用之前，并复用既有子进程握手机制：临时marker写入后`sync_all`，再原子重命名。检查点常量与调用均受`cfg(test)`限制；公开API、schema、生产重试语义和正常启动路径未变。

新增`dispatch_admission_asset_mismatch_crash_keeps_terminal_failure`子进程测试，经真实`dispatch_pending`进入fixture admission policy失配路径。父进程在20秒内等待完整握手；超时会报告子进程日志并失败，不继续推定窗口已命中。终止前父进程认证operation/job完整修订链与哈希、状态迁移、命令摘要、冻结输入绑定，并检查没有报告或执行器调用。事件严格为`freeze → claim → dispatch_asset_mismatch_persisted`，任务迁移为queued→running→failed/AssetMismatch。父进程据此终止子进程。

恢复使用真实目录锁、持久store和完整跨链认证。第一次重开保留唯一failed/AssetMismatch终态，不追加unknown，不创建报告，不留活动或可领取任务；第二次重开不增加修订，操作、任务和报告材料逐字节稳定。测试记录的恢复前后材料SHA-256相等，executor invocation、worker process、engine/FFI均为0。

## 证据与验证

最终机器证据：[`dispatch-asset-mismatch-crash-evidence.json`](../../../target/h3-dispatch-asset-mismatch-kill/2de1a1bedd82a42e93f13d8ba3c64a47/dispatch-asset-mismatch-crash-evidence.json)，2,832字节，SHA-256=`bcad7b64506516d3af291e0b196d4740c25005f33a4134533cf7891fabf7ca86`。operation=`166e02cf42af7c3589b64df17c0c8ddb`；job=`bcf3c7bbdb9725dfec406c549dffcffe`。机器证据中的`child_exit`记录为被父进程终止后的退出状态。

聚焦测试1 passed、0 failed、100 filtered；workspace默认串行测试显式跳过`doctor_reports_missing_worker_and_assets`后退出码0，`ygo-cli`库测试101 passed。workspace全目标Clippy、格式检查和`git diff --check`通过；Python `tests/test_schemas.py`为8 passed、2 skipped。一次初始未过滤workspace尝试启动了`doctor_reports_missing_worker_and_assets`，该测试调用`ProcessEngineAdapter::doctor()`检查不存在的worker和资产；发现超出本批边界后停止了该次运行。它未启动worker、引擎或FFI。最终增加父进程链认证断言后，重新运行聚焦测试及Clippy、格式和差异检查；完整workspace串行测试在补强后以显式skip命令通过。

```powershell
cargo test --offline --locked --target-dir target/h3-dispatch-asset-mismatch-kill/cargo -p ygo-cli --lib workbench::analysis_http::tests::dispatch_admission_asset_mismatch_crash_keeps_terminal_failure -- --exact --test-threads=1
cargo test --workspace --offline --locked --target-dir target/h3-dispatch-asset-mismatch-kill/cargo -- --test-threads=1 --skip doctor_reports_missing_worker_and_assets
cargo clippy --workspace --all-targets --offline --locked --target-dir target/h3-dispatch-asset-mismatch-kill/cargo -- -D warnings
cargo fmt --all -- --check
py -m pytest tests/test_schemas.py -q
git diff --check
```

## 关闭范围与后续

本批只关闭HTTP dispatch admission中的这一单一合成K窗口。它不认证真实资产加载、worker或引擎执行，不覆盖其他AssetMismatch来源、调度竞态、逐系统调用崩溃、断电或介质故障，也不改变普通启动`analysis_not_configured`状态。H3.2-2b余项继续开放。首次未过滤workspace尝试误纳入适配器`doctor()`诊断用例，发现后停止并在最终测试中显式跳过；未运行CLI `engine doctor`命令，也未启动真实引擎、runner、worker、FFI、研究scope或部署。

当前状态和剩余工作以[TASKS](../../../TASKS.md)为准，逐次运行结果以[TESTING](../../TESTING.md)为准。
