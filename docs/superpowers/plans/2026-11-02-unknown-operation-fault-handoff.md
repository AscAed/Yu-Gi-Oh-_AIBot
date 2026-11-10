# 无任务accepting操作恢复为unknown：P/U/R限定验收

新增测试`recovery_unknown_operation_publish_faults_preserve_later_work_and_resume_once`，直接建立两条完整、已认证且无匹配任务的accepting操作链，在重开分类追加unknown revision 3时注入`BeforePublish`、`AfterPublish`和`Reread`三种持久故障。

`BeforePublish`留下4条原始修订；其余两种故障留下5条，第一条操作的unknown已发布而第二条仍为accepting。真实持锁重开后，两条操作各有3条修订并到达unknown。恢复不会生成任务、报告或冻结输入；队列无queued/running工作，重复begin复用已有unknown且不返回ticket，`claim_next`为空。再重开一次后所有持久材料逐字节稳定。

最近一次完整workspace运行产生的三阶段证据文件：

- `target/w1h21-analysis-operation-tests/e8016d25f4012681e65f31487d820447/unknown-operation-fault-evidence.json`：BeforePublish，4→4→6项。
- `target/w1h21-analysis-operation-tests/7cad216aaf6fd51b3b3b1b3b0025d12a/unknown-operation-fault-evidence.json`：AfterPublish，4→5→6项。
- `target/w1h21-analysis-operation-tests/e057382a0eddcb6efc923969608d635b/unknown-operation-fault-evidence.json`：Reread，4→5→6项。

三份证据的fault hit均为1，六个恢复后文件的SHA-256已与各证据目录下`store/`材料逐项复核，重复重开稳定标记均为true。这些哈希只核验当前保存文件和测试断言，不是每个中间状态的逐字节备份。

验证结果：

- 聚焦测试：1 passed，测试内部覆盖三种故障阶段。
- `durable::operation_tests`：20 passed。
- CLI全套：104 passed。
- workspace默认串行测试：91组，445 passed、0 failed、36 ignored，退出0；忽略项维持默认选择。
- `cargo fmt --all -- --check`、workspace全目标Clippy（offline/locked，`-D warnings`）通过。
- 工作台HTTP、operation、job三个schema测试：16 passed。
- workspace日志为`target/h3-2b-2-cargo/workspace-final.log`，SHA-256为`7A10F5AC0F713D806D6BA9FF0F233F2298714DE76C89368E595B1527D88D2DDB`。

本验收是合成逻辑持久故障注入，不是子进程终止、逐syscall、断电或介质故障测试。两条accepting链直接在存储层构造，不证明正常服务允许同时持有两个预占；没有调用worker、runner、ocgcore或FFI。unknown不推定零消费。混合accepted/unknown操作修复顺序随后由独立K场景覆盖，其他H3恢复和调度窗口仍开放；普通启动保持`analysis_not_configured`，W1-C和P4-R5未改变。参见[混合恢复交接](2026-11-02-mixed-operation-recovery-handoff.md)。
