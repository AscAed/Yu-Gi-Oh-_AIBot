# P4-R1b：执行循环离线接入交接

## 结果

在A3单调用检查点之上新增独立 `ResumablePartialExecutionV1` 外层状态机。新入口从已收费且结果完整的初始Execution调用开始；每次推进只处理一个由实际提示绑定的动作，语义阶段复用原同步循环的 `observed`、`successors`、`same_action`、`bind_start`、`follow_choice`、资源比较、实例映射及预测工具。旧 `execute_partial_v2` 和报告没有改写。

外层记录包含语义步骤、当前转换及before-state、事件边界、已用选择、预测、动作证据、实例映射、中断诊断、待处理调用和逐次查询审计状态。调用意图在收费前保存；执行结果从journal认证后推进。独立审计使用 `Witness` purpose 及reservation，逐一重放查询前缀与最终根结果；这不构造 `AuditedQueries` 或 `PartialExecutionV2` 成功凭证。

恢复先只读验证外层checkpoint、账本统计、预留、父结果及已完成审计调用，再释放只读句柄并严格独占重开比对。唯一允许协调的尾部是已保存意图对应的一次调用；完成结果按原请求/用途复用，未决或未知消费拒绝继续。外层状态与journal保存值不一致时，在adapter调用前拒绝。

## 当前合成覆盖

- 非空恢复初始化：赛事查询夹具经`propose_partial`生成三步有效计划，并由`validate_forecast`复核；以已收费初始调用建立状态，关闭/重开后仍在Semantic阶段、游标0，账本消费保持1。测试`resumable_loop_reopens_with_valid_nonempty_semantic_plan`只覆盖计划绑定与初始化恢复，不执行任何动作。
- 单动作恢复与安全停止：同一计划执行一步后到达opcode12提示；连续路径和关闭/重开路径都在下一计划动作不可用时返回`original_plan_blocked`，消费不变且状态相同。红测发现resume协调内层状态后未同步外层journal检查点；恢复流程现会持久化协调后的外层快照。测试`unsupported_trigger_boundary_blocks_without_charging_after_reopen`通过。此结果覆盖一次执行后的恢复边界，但提示opcode12的后续处理与成功的多动作等价仍开放。
- End Phase命令7：初始已收费调用之后只推进一个Execution请求。
- 独立审计：一条QueryWitness前缀和一个终端根调用分别记账；在两者之间关闭journal、恢复状态，再完成第二次审计。
- 账本收费序列为初始1次、结束阶段1次、查询审计2次；reservation最终释放，unknown为0。
- 篡改外层语义步骤时，收费前拒绝，消费数仍为1。
- schema对版本化状态正例、伪造凭证和错误版本负例通过。

## 未覆盖与限制

此次红测及实现没有在真实OCG进程中暂停/重开，也未完成跨提示成功推进的多动作连续端到端对照、每个动作调用边界的成功暂停/重开比较、进程终止故障注入矩阵、外部并发写入竞争测试或独立原生重放。当前查询夹具第一动作后到达opcode12，而下一计划动作在该窗口不可用；实现会在不收费的情况下安全停止。这需要明确建模或选择能完整匹配提示序列的有效计划/夹具，不能靠放宽`validate_forecast`或伪造动作继续。A3既有测试仍分别覆盖低层完成尾调用复用和未决消费阻断。以上离线结果不得推断为真实R1b资格。

本批新增native research、runner、worker及FFI调用0；不创建scope、窗口或收费账本。会计维持认证子集40、政策预留7、规划47，全部历史实际累计未知。C1已记录的Tenki保护哈希失败保持不变。

## 本批验证结果

- 恢复游标同步修复后追加复验：`cargo fmt --all -- --check`与workspace全目标Clippy通过；planner串行套件为68 passed、9 ignored、0 failed；workspace串行总检为360 passed、36 ignored、0 failed（91条test-result记录）。原始日志保存在本机忽略目录`target/p4-r1b/planner-final.log`及`target/p4-r1b/workspace-resume-fix.log`。
- `cargo fmt --all -- --check`通过。
- `cargo test -p ygo-planner --offline --locked --target-dir target/p4-r1b -- --test-threads=1`通过：22个单元测试、66个集成测试通过，10个既有opt-in用例忽略。
- `cargo test -p ygo-engine-adapter --offline --locked --target-dir target/p4-r1b -- --test-threads=1`通过：54个单元测试、91个集成测试通过，2个既有资产opt-in用例忽略。
- `cargo clippy --workspace --all-targets --offline --locked --target-dir target/p4-r1b -- -D warnings`通过。
- `cargo test --workspace --offline --locked --target-dir target/p4-r1b -- --test-threads=1`通过：358 passed、36 ignored、0 failed；91条test-result记录。完整日志及格式/Clippy记录在[`target/p4-r1b/logs`](../../../target/p4-r1b/logs/)。
- `PYTHONPATH=python py -m pytest tests/test_schemas.py -k resumable_execution_loop -ra --tb=short`通过：1 passed、8 deselected。未运行完整Python套件；C1既有Tenki保护哈希失败保持记录且未修改锚点。
- 总检曾发现意图与认证调用边界的语义快照顺序问题及一个Clippy警告；修复后以上最终复验通过。工作区中的C1、B2和A3未提交修改均予以保留。

## 尚未认证

目前集成测试覆盖End Phase及逐次QueryWitness/终端根审计的合成暂停重开，但没有完成非空语义计划下多动作连续提示与逐边界恢复的等价测试。真实OCG进程暂停/重开、跨文件系统边界崩溃注入、外部并发进程竞争及独立原生重放仍未认证。后续真实实验须另定scope、预算和窗口；本交接不授权原生执行。
