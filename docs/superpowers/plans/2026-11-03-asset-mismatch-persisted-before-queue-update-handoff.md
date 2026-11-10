# H3：AssetMismatch保存后、内存队列结算前进程终止交接

日期：2026-11-03

## 目标边界

先按[H3.1证据映射](2026-11-02-h3-evidence-gate-map.md)区分相邻路径：running revision保存、内存队列更新、资产复核成功、`claim_next`返回票据是正向路径；资产复核失败时，协调器会将job转为`failed/AssetMismatch`。既有普通回归验证该终态，持久化故障注入验证failed提交不确定后重开分类为unknown；此前没有覆盖failed revision已成功保存、内存队列尚未应用该终态时的进程终止。

本批只验证该单一逻辑窗口。没有修改公开API、schema、自动重试或生产状态转换；新增检查点仅在`cfg(test)`下工作。

## 实施与认证

在`claim_next`资产复核失败分支的`append_expected`成功后、`settle_with_persist`返回并更新队列内存状态前发布同步临时marker，再原子重命名。子进程先接受冻结输入，再只修改自身临时fixture中的engine文件以触发资产哈希失配。父进程等待握手，认证operation/job revision封套、前驱和记录哈希、操作命令与冻结输入绑定，以及queued→running→failed/AssetMismatch转换后才终止子进程。

强杀前事件为`freeze → claim → asset_mismatch_persisted`；operation保持accepted，job revision 1/2/3分别为queued/running/failed，错误码为`asset_mismatch`。没有报告，`claim_next`未返回ticket。测试停在协调器领取路径，未创建执行器，也没有真实worker、FFI或引擎调用。

恢复通过真实目录锁与持久存储重开。唯一failed revision保持终态，不追加unknown或其他revision；活动队列为空，`claim_next`无可领取任务。第二次重开后operation/job材料字节不变，测试逐项比较七个持久修订文件的SHA-256。

机器证据[`asset-mismatch-evidence.json`](../../../target/w1h21-analysis-operation-tests/b18041661f155e62909e0758302405f7/asset-mismatch-evidence.json)为2,499字节，SHA-256=`db8751b6c610be995309691bd39b77f136bbbfa1579f1cbca5108c336a1a86fd`。其中operation为`a08b458a48f8790b9e935559b1a6c73d`，job为`9f720f64d38b7dcbbbbabbe739119779`。证据记录子进程被终止、零报告/执行器调用、false ticket-return状态、两次稳定重开，以及强杀前与恢复后相同的文件哈希。

## 验证与范围

```powershell
cargo test -p ygo-cli --offline --locked --target-dir target/asset-mismatch-crash-window/cargo --lib workbench_analysis::durable::operation_tests::h3_2b_cross_chain_windows_recover_after_process_kill -- --exact --test-threads=1
```

聚焦子进程矩阵 **1 passed、0 failed、99 filtered**。首次编译发现测试夹具拿到的是不含运行时路径的path-free job输入；将fixture资产路径在提交前保存后，最终测试通过。测试使用`--offline --locked`和隔离Cargo target。

该结果只关闭预执行资产复核失败时的这一处K点。它不覆盖HTTP派发准入的另一条AssetMismatch路径、真实资产加载或执行，也不覆盖其他逻辑窗口、调度竞态、逐syscall、断电或介质故障。普通启动仍为`analysis_not_configured`；H3其余门禁和P4-R5保持开放。
