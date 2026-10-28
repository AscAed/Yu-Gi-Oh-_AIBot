# P4-R1b：执行循环离线接入交接

## 结果

在A3单调用检查点之上新增独立 `ResumablePartialExecutionV1` 外层状态机。新入口从已收费且结果完整的初始Execution调用开始；每次推进只处理一个由实际提示绑定的动作，语义阶段复用原同步循环的 `observed`、`successors`、`same_action`、`bind_start`、`follow_choice`、资源比较、实例映射及预测工具。旧 `execute_partial_v2` 和报告没有改写。

外层记录包含语义步骤、当前转换及before-state、事件边界、已用选择、预测、动作证据、实例映射、中断诊断、待处理调用和逐次查询审计状态。调用意图在收费前保存；执行结果从journal认证后推进。独立审计使用 `Witness` purpose 及reservation，逐一重放查询前缀与最终根结果；这不构造 `AuditedQueries` 或 `PartialExecutionV2` 成功凭证。

恢复先只读验证外层checkpoint、账本统计、预留、父结果及已完成审计调用，再释放只读句柄并严格独占重开比对。唯一允许协调的尾部是已保存意图对应的一次调用；完成结果按原请求/用途复用，未决或未知消费拒绝继续。外层状态与journal保存值不一致时，在adapter调用前拒绝。

## 当前合成覆盖

- End Phase命令7：初始已收费调用之后只推进一个Execution请求。
- 独立审计：一条QueryWitness前缀和一个终端根调用分别记账；在两者之间关闭journal、恢复状态，再完成第二次审计。
- 账本收费序列为初始1次、结束阶段1次、查询审计2次；reservation最终释放，unknown为0。
- 篡改外层语义步骤时，收费前拒绝，消费数仍为1。
- schema对版本化状态正例、伪造凭证和错误版本负例通过。

## 未覆盖与限制

此次红测及实现没有在真实OCG进程中暂停/重开，也未完成多动作连续提示端到端对照、进程终止故障注入矩阵、外部并发写入竞争测试或独立原生重放。A3既有测试仍分别覆盖低层完成尾调用复用和未决消费阻断。以上离线结果不得推断为真实R1b资格。

本批新增native research、runner、worker及FFI调用0；不创建scope、窗口或收费账本。会计维持认证子集40、政策预留7、规划47，全部历史实际累计未知。C1已记录的Tenki保护哈希失败保持不变。

## 本批验证结果

- `cargo fmt --all -- --check`通过。
- `cargo test -p ygo-planner --offline --locked --target-dir target/p4-r1b -- --test-threads=1`通过：22个单元测试、66个集成测试通过，10个既有opt-in用例忽略。
- `cargo test -p ygo-engine-adapter --offline --locked --target-dir target/p4-r1b -- --test-threads=1`通过：54个单元测试、91个集成测试通过，2个既有资产opt-in用例忽略。
- `cargo clippy --workspace --all-targets --offline --locked --target-dir target/p4-r1b -- -D warnings`通过。
- `cargo test --workspace --offline --locked --target-dir target/p4-r1b -- --test-threads=1`通过：358 passed、36 ignored、0 failed；91条test-result记录。完整日志及格式/Clippy记录在[`target/p4-r1b/logs`](../../../target/p4-r1b/logs/)。
- `PYTHONPATH=python py -m pytest tests/test_schemas.py -k resumable_execution_loop -ra --tb=short`通过：1 passed、8 deselected。未运行完整Python套件；C1既有Tenki保护哈希失败保持记录且未修改锚点。
- 总检曾发现意图与认证调用边界的语义快照顺序问题及一个Clippy警告；修复后以上最终复验通过。工作区中的C1、B2和A3未提交修改均予以保留。

## 尚未认证

本文件末尾的2026-10-28续接附录记录后续完成的多动作等价与中断门禁；上面的原始交接保留其当时“尚未覆盖”的历史状态。真实OCG进程暂停/重开、操作系统级跨文件系统边界崩溃注入及独立原生重放仍未认证。后续真实实验须另定scope、预算和窗口；本交接不授权原生执行。

## 2026-10-28续接：P4-R1b多动作恢复等价与中断门禁

### 结果

- 新增`nonempty_two_action_plan_matches_continuous_and_every_prompt_boundary_reopen`。固定计划包含trace夹具中的两暗属性三级怪兽XYZ procedure和后续normal summon。第一步跨越多个连续提示，第二步进入End Phase，再完成独立query audit。合成适配器下连续与每个语义调用边界暂停、重开的决策证据、前缀、实例映射、选择、预测、查询和reservation逐项一致；最终账本26次完成消费、unknown 0，其中Execution 12次、Witness 14次。End Phase/query audit的恢复边界由原独立回归继续覆盖。
- 红测确认完成尾调用恢复缺少decision evidence；正常和恢复路径现在共享`record_execution_decision`校验和记录。另修复语义推进未先同步A3检查点的问题，避免外层状态前进后内层快照落后。
- 新测试专用故障钩子验证语义快照保存与外层意图发布失败时adapter调用0；两种失败后状态均可恢复且没有虚构消费。另在调用结果已完整进入账本、执行进度检查点尚未发布时中断；恢复按原请求/用途认证并复用尾调用，adapter总调用保持1，不重复收费。未决调用拒绝推进。只读检查后的竞争测试在窗口间写入另一条有效合成账本记录，恢复保留该记录并在发现未绑定消费后拒绝继续；持有独占writer也会阻止恢复。

### 验证

- `cargo fmt --all -- --check`通过。
- planner串行测试：**70 passed、10 ignored、0 failed**；engine-adapter串行测试：**145 passed、2 ignored、0 failed**。
- `cargo clippy --workspace --all-targets --offline --locked --target-dir target/p4-r1b-followup -- -D warnings`通过；`cargo test --workspace --offline --locked --target-dir target/p4-r1b-followup -- --test-threads=1`：**362 passed、36 ignored、0 failed**，91条test-result摘要。
- `py -m pytest tests/test_schemas.py -k resumable_execution_loop -ra --tb=short`：**1 passed、8 deselected**。未运行完整Python套件；C1的Tenki历史保护哈希失败和原pin未更改。最终日志在`target/p4-r1b-followup/logs/`。

### 限制及交付边界

本轮新增原生研究、runner、worker、FFI调用0。合成结果不产生正式凭证。验证了测试钩子模拟的进程边界失败、CallJournal完成/未决尾部和确定性账本竞争，不等于操作系统级进程终止或逐次文件系统写入故障覆盖。真实OCG暂停、重开、未知收费恢复及独立原生重放继续开放，须另定scope、预算和窗口。会计保持认证消费子集40、政策预留7、规划47，全部历史实际累计未知。
