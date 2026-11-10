# H3 running：领取票据返回后、假执行器调用前的合成强杀

## 目标边界

补充一个仍开放的H3.1逻辑窗口：`claim_next`已持久提交`running`、更新内存队列并返回票据，派发准入核对完成，但测试专用假执行器尚未调用。该证据仅验收此单一进程终止点，不关闭H3.2-2b其余逻辑窗口、调度竞态、逐syscall、断电或介质故障。

## 通过证据

`AnalysisHttpService::dispatch_pending`在成功领取并通过准入核对后、调用执行器前设置`cfg(test)`检查点。子进程使用临时文件、`sync_all`和原子重命名发布握手；父进程设20秒超时，检查marker PID与实际子进程PID相同，并验证完整operation/job修订链、前驱摘要、accepted/running绑定、命令摘要和冻结输入绑定后才终止子进程。子进程事件严格为`freeze → claim → ticket_returned_before_executor`，没有执行器调用、报告或生产worker。

证据中的operation `7efc61fbb022679c646660872ca0954b`保持4个revision和`accepted`；job `c2bdd132cb6b09bc884f7361dffd9926`终止前为revision 2=`running`。父进程以真实存储目录锁重开，认证后仅追加revision 3=`unknown`；没有报告，queued/running槽为空，`claim_next`无可领取工作。operation修订数不变，第二次重开不追加revision，所有持久材料字节稳定。`unknown`不解释为零消费；此处执行器调用为零只由测试专用事件确认。

机器证据：[ticket-return-crash-evidence.json](../../../target/h3-ticket-return-kill/d1189be0e6adc48b2070a728b2ce70f8/ticket-return-crash-evidence.json)。

## 验证

- 新增聚焦进程终止测试：1 passed。
- 完整`ygo-cli`套件：122 passed、0 failed、0 ignored。
- Workspace串行套件：命令退出码0；独立测试枚举为506项，其中470项执行并通过、36项按opt-in标记忽略。忽略项需要冻结引擎/资产、原生提示、人工基准或显式本地报告输入；没有为本批解除opt-in。
- Workspace全目标Clippy（`-D warnings`）和`cargo fmt --all -- --check`通过。
- Python operation/job/HTTP/通用schema回归：24 passed、2 skipped。skip分别需要本地snapshot/report和实际v2 report；pytest报告`cache_dir`为未知配置的一条警告。
- Workspace套件包含适配器的`doctor_reports_missing_worker_and_assets`负例测试，该用例只传入不存在的worker和资产路径；没有运行CLI doctor、生产worker、真实引擎或FFI。

构建与Cargo测试均使用隔离`target/h3-ticket-return-kill/cargo`、`--offline --locked`；没有联网构建。完整CLI和workspace命令、schema命令及枚举清单见[TESTING](../../TESTING.md)与`target/h3-ticket-return-kill/`。本批没有创建研究scope、运行真实引擎/runner/worker/FFI、部署、提交或推送。
