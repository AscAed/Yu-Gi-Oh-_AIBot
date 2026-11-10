# P4-R1b-3：真实暂停/重开与独立原生重放实验计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` task by task only after the user separately authorizes live execution. This document is a design; it does not create a scope or authorize native calls.

**目标：** 用一个冻结的 `tournament-2026` 首回合片段，验证可恢复执行在已完成收费调用后的真实进程终止、重开和继续，与独立同步执行及原生查询重放是否一致。

**方案：** 在隔离的 Rust 示例驱动中使用生产 `ProcessEngineAdapter`、`CallJournal` 和公开可恢复 API。恢复运行和连续重放使用两个全新账本；只在第一个语义步骤已持久化、没有调用进行中时终止协调进程。

**技术栈：** Rust workspace、Windows 子进程、`CallJournal`、ProjectIgnis 冻结资产；Cargo 使用 `--offline --locked` 和隔离 `target`。

**依据：** [执行恢复合同](../../EXECUTION_RECOVERY.md)、[P4-R1b 交接](2026-10-28-p4-r1b-resumable-execution-loop-handoff.md)、`crates/ygo-planner/src/first_turn/execution.rs` 中的 `nonempty_two_action_plan_matches_continuous_and_every_prompt_boundary_reopen` 合成用例。

## 全局约束

- 本计划只定义实验；真实 scope、构建后原生调用、runner、worker、FFI 及重放均须用户另行授权。
- 普通工作台启动保持 `analysis_not_configured`；不改变公开 API、schema、普通 CLI 或部署。
- 使用生产 `begin_resumable_partial_execution_v1`，并先取得绑定真实结果的 `AuditedQueries`；不得使用 `cfg(test)` 下省略该能力的别名或合成 adapter。
- `ProcessEngineAdapter::doctor()` 会执行 probe；不用于本实验的静态预检。
- 消费未知、失败或超时均保留在账本中，不退款、不自动重试、不新建 scope 接续；未知不解释为零消费。
- 全部研究材料写入新的 `data/runtime/p4-r1b3/<run_id>/` 子目录，使用 `create_new`，拒绝已有目录、链接及输入/资产重叠；绝不覆盖历史账本或研究材料。
- 结论限于一个冻结起点和两个语义动作的恢复等价；不授予动作完整、原生通用资格、概率、全局最优、P4-R2–R5 或产品发布资格。

## 五个关键失败条件

1. 固定输入、资产、构建或 `ForecastPlan` 哈希有任何差异：在新建 scope 和首次原生调用前停止。
2. 首次运行的提示、实际前缀、观察或两个规则 ID 不匹配：保留已发生的调用及结果，不继续调整计划或换线路。
3. 暂停标记缺失/不完整，或存在 pending intent、运行中的 worker、未知/未决消费：不强杀后声称安全恢复；保留现场并结束本批。
4. 只读检查与独占重开之间账本变化、链认证失败或重复重开增加字节/修订：拒绝继续，保留冲突证据。
5. 独立重放与恢复运行有任何语义差异：保留两个账本和原始结果，不自动重跑以“修复”差异。

## 固定场景与本机基线

使用 `tests/fixtures/tournament-2026.rules-resource.contract.json` 的 `cases[0]`（`soleret-empty-positive`，协议 v6，主卡 41、额外卡 15、固定起手与 seed 1），以及 `tests/fixtures/tournament-2026.trace-resource.json`。这些文件提供可重复的起点和预期语义路线；fixture 中的 `passed=true` 和现有 trace 不算作本轮真实执行证据。

起始 `RunDuelRequest` 的重建规则固定为：复制 `cases[0].runtime_request`，先清空 `decisions`，再填入 trace `result.resolved_decisions` 中 `prompt_id < 49` 的决定（共 16 条）。只允许将 `engine.worker_path` 指向本批隔离重建的 worker；其他请求字段、双资产版本和 first-turn 上下文保持原值。起始实际结果必须在事件 49 返回可认证提示。复用现有回归的三个初始查询见证（事件 8、17、49），并在恢复运行 scope 内用真实 `ProcessEngineAdapter` 重放，取得不可序列化、不能从 JSON 伪造的 `AuditedQueries` 后，才能调用生产 `begin_resumable_partial_execution_v1`。

使用真实冻结 CDB、`FirstTurnKnowledge::builtin()`，以及一个固定的双条件 Goal：目标场上至少有一张 `78449284` 和一张 `25538345`（两者均为 location 4）。旧的“任意可见卡至少一张”目标在起点就已满足，公开规划器只会返回空计划，因此本次改用能区分固定两步终态的条件。由 `propose_partial` 生成计划；离线准备阶段必须把前两个规则固定为 `78449284:two_dark_level_three` 和 `25538345:normal_summon_and_set`，保存规范化计划、`SearchLimits`、起始观察、Catalog、Knowledge、Goal 和最终请求的 SHA-256。若公开规划 API 无法在不修改计划的情况下生成并验证这两个步骤，或生成的规则顺序不同，就在创建 scope 前停止并返回重新设计；不得手工拼造凭证或临场换计划。该 Goal 只是恢复接口的固定输入，不是对牌局价值的研究结论。

本机只读身份核对基线（2026-11-02）：

| 材料 | SHA-256 / 标识 |
|---|---|
| `configs/tournament-2026.assets.json` | `25ac37254b4f04336320f621d8f010e4a7cbfa90026407b1a376718e15ea05ad` |
| `configs/tournament-2026.source.json` | `d458804dce80c01fc27f5863c0b0ec821624627a61c0fd982dded04f41bc6aff` |
| `tests/fixtures/tournament-2026.rules-resource.contract.json` | `db79e2f51a7c724bc3c72a78e96e0c7f6f544ceb59ffbd61a4a6ef9084ec5a87` |
| `tests/fixtures/tournament-2026.trace-resource.json` | `cc98145d68dd560863c40b4ac218220ebb0ee4e5069c26e91a572beee1d3032d` |
| 资产组 ID | `asset-group-228cca96b5cf16a5e8d8f397cb30db073b483e75ddb0536d7d5f6f28783af340` |
| Catalog / banlist ID | `catalog-de71e6b4683795a9cb83c44ba85bf1cc43d635ce8da032fff9f8b055b60e31b9` / `banlist-c98f770b366fed87be0fb23357a63d704db58b31508fbb88133fda66575f3783` |
| `data/runtime/tournament-2026/frozen/manifest.json` | `2131d85669dc307a2cb0a82096b6460acba3ecbd63eca3852bf0158f450d1a2c` |
| 冻结 `cards.cdb` / `engine/ocgcore.dll` | `3530f406ba92b0f8d5699aa107e95158a1f1b4816f8f5ca2dd82c490301ef632` / `446f26df7a2fb35d94374d74f5f5a5ef200d5454322d372b325e46b4e083d7a9` |
| `engine/manifest.json` / `scripts.json` | `2028d6b7d5bf6878c11107760e73f33cf8dcfcf977d312c86ff98640c736e457` / `26c44946c7aba56900ededc5358e163fce71d5b99182f0d0fa910739bc3d9c94` |

上述文件在检查时存在，CDB、core 和脚本清单与请求/配置声明一致；检查没有调用引擎或验证当前 ABI。`target/debug/ygo-engine-worker.exe` 当时存在，SHA-256 为 `0cb8547fb9b302802dff81e986efa854ee7c27b74c37af834b5c384b9323db68`，但没有绑定到本批源码，故不作为候选运行包。当前 HEAD 为 `672e5a823fcad60e9413d79cac810b68a2bb003c`，工作区有既存改动；实际执行前必须记录源码 HEAD、完整 tracked diff、参与构建的 untracked 源文件、`Cargo.lock` 与构建产物哈希。资产/fixture 只读哈希是设计基线，执行前必须重验。

当前 planner 暴露了可恢复 API 与 `ProcessEngineAdapter`，但 `ygo-cli` 没有调用 R1b 循环的命令。实现真实实验需要新增仅供研究的 `crates/ygo-planner/examples/p4-r1b3-native-resume.rs` 驱动；它必须通过生产公开 API 工作，不接入普通 CLI。worker 在隔离目录离线构建：

```powershell
cargo build -p ygo-engine-adapter --bin ygo-engine-worker --offline --locked --target-dir target/p4-r1b3/cargo
cargo build -p ygo-planner --example p4-r1b3-native-resume --offline --locked --target-dir target/p4-r1b3/cargo
```

## Scope、预算与窗口

- 生成一次唯一 `<run_id>`；分别建立 `<run_id>-resume` 和 `<run_id>-replay` 两个全新 `CallJournal` scope，scope/context/limit 不可变。
- 每个 scope 上限 64 次 `EngineAdapter::run` 请求，`Execution`、`Witness`、失败和未知均计入；配对实验合计最多 128 次请求。worker 单次 timeout 固定 30,000 ms。
- 共用一个 7,200 秒窗口。先完成离线 build 和默认关闭的非原生预检；创建只写一次的 `window-start` 后、再进行最后资产扫描和首次原生调用。重开不重置起点，时钟倒退、到时、预算满、worker 失败、资产漂移或账本 unknown 均停止；不得新建窗口续跑。
- 账本统计的是适配器 worker 请求，不等于 worker 内部 FFI/opcode 查询数。内部计数若没有独立来源就记录为 unavailable，不从适配器请求数推算。新 scope 的数字不得并入或替代历史实际消费 `null`。
- 实验目录只保存输入/资产/计划清单、构建身份、两个 scope 的完整 `calls.jsonl` 与 blob、检查点、marker、最终投影、差异和停止原因；使用 `create_new`，不覆盖旧证据。

## 执行步骤

### Task 1：实现隔离驱动和零调用预检

**文件：** 创建 `crates/ygo-planner/examples/p4-r1b3-native-resume.rs`；创建 `crates/ygo-planner/tests/p4_r1b3_harness.rs`。不改生产 API、schema 或普通 CLI。

- [x] `prepare-only` 从上述 fixture 构造请求、起点与计划，校验固定规则顺序、资产目录和内容哈希；其验收断言是未创建 scope/ledger、worker 和 native call 计数为 0。
- [x] 增加 `prepare_only_rejects_changed_fixture_assets_or_route` 和 `production_begin_requires_live_audited_queries`；后者确保没有使用测试专用 begin alias。
- [x] 用 `cargo test -p ygo-planner --offline --locked --target-dir target/p4-r1b3/cargo --test p4_r1b3_harness -- --test-threads=1` 验证纯离线预检，再按上方命令在隔离 target 构建 worker 和实验驱动。

### 2026-11-03：隔离产物身份复核

新隔离target预检发现，旧驱动把`RunDuelRequest.engine.worker_path`固定指向历史`target/p4-r1b3/cargo/debug`，会使新target构建仍引用旧worker。现在worker路径从驱动`current_exe()`的Cargo profile目录派生；driver摘要及恢复运行校验也绑定当前`current_exe()`。回归断言验证测试二进制profile目录下的worker路径。修正后的离线聚焦测试、workspace检查和prepare-only零调用结果见[当前身份/预检记录](2026-11-03-p4-r1b3-scope-review.md)及[验证记录](../../TESTING.md)。此项只修复构建身份绑定，不启动worker、不创建scope，也不扩大Task 2/3授权。

### Task 2：运行恢复 scope 并在安全边界终止

- [ ] 只有用户另行授权后，才在 `<run_id>-resume` 中先执行固定前缀的初始 `Execution` 调用，再对事件 8、17、49 查询见证执行真实 `Witness` 重放、生成 `AuditedQueries` 并开始 R1b 循环。
- [ ] 通过公开可恢复 API 推进到第一语义动作完成处。只有状态满足 `phase=semantic`、`semantic_step=1`、`pending=null`、最后一次调用完成、`unknown=0`、`reserved=0`，且 worker 已退出时，子进程才写暂停 marker。
- [ ] marker 先写临时文件、`sync_all`、原子重命名；内容绑定 run/scope/context/request/plan/worker/资产哈希、checkpoint 摘要、账本序号和统计。父进程设置 600 秒等待上限，并用只读 journal 检查重新认证 marker 和状态；握手超时或认证失败即停止并留存，不依据不完整 marker 强杀。
- [ ] 父进程仅在认证完整 marker 且确认没有调用在途时强杀协调器。新进程用相同 scope/context/limit 调用 `resume_resumable_partial_execution_v1`；先断言重开自身没有增加 journal 字节、revision、调用数或预留，再继续第二动作及独立 QueryWitness audit。
- [ ] 完成后关闭所有句柄，再重开一次；要求输出状态、操作账本和报告投影逐字节稳定，`consumed=completed`、`unknown=0`、`reserved=0`，不新增调用。任何失败都不自动启动 replay scope。

### Task 3：使用独立 scope 做连续执行与原生重放

- [ ] 仅当恢复 scope 完成且无 unknown 时，创建全新 `<run_id>-replay` scope，重新执行同一固定起始请求和计划；通过既有同步 `execute_partial` 连续推进，不复用恢复 scope 的结果、journal、checkpoint 或任何充值/授权状态。
- [ ] 通过 `replay_partial_execution` 对该 scope 的完整 query 前缀执行独立原生 Witness 重放。任何超时、失败、差异或未决消费都保留并停止，不重复尝试。
- [ ] 比较两条运行的 ForecastPlan、语义步骤/选择/预测、实例映射、QueryWitness 序列和最终 `DuelResult`。`DuelResult` 使用现有 `same_native` 语义：所有字段完全相同，只在副本中把 `peak_working_set_bytes` 设为 null；不得另行忽略版本、事件、状态或错误差异。两本 ledger 分开验证，不要求调用序列因审计时机不同而相同。

### Task 4：交接与事实源

- [ ] 只有两条 scope 都完成认证且比较一致，才把本窗口记为“此固定场景通过”；更新 `TASKS.md`、`docs/TESTING.md`、[执行恢复合同](../../EXECUTION_RECOVERY.md)和路线交接，列出真实计数、两个 scope、marker、重开稳定性、哈希及未覆盖故障窗口。
- [ ] 任一门槛失败时保留原始复现和账本，将 R1b-3 执行保持开放；不得将部分输出写为通过。

## 验收解释与明确缺口

成功只表示：在这一份协议 v6 输入、一个进程间已提交安全边界、两条语义动作和受限预算下，重开后没有重复收费，最终观察与独立连续执行/原生查询重放一致。这里的 worker-request 计数不能代表全部内部 FFI 消耗或历史总账本；单一安全边界终止也不覆盖调用进行中强杀、逐文件系统 syscall 故障、断电或介质损坏。任何此类问题都需另立场景与范围。

## 2026-11-02 实施与首轮运行记录

已创建隔离研究驱动和离线测试；普通 CLI、生产 API 与 schema 未改。驱动提供默认 `prepare-only` 和显式 `--run-native`，固定两步由公开 `propose_partial` 生成，输入/资产/计划身份在建scope前绑定，恢复与replay账本分别隔离。修复Windows路径检查及trace见证重建后，最终离线验证为：聚焦测试5 passed、`cargo fmt --all -- --check`通过、planner全目标Clippy（offline/locked，`-D warnings`）通过、隔离worker及example构建通过；最终 `prepare-only` run `p4-r1b3-1793628179040738600-50668`显示 `scope_created=false`、`worker_processes_started=0`、`native_calls=0`。

按用户授权启动的首次原生尝试使用run `p4-r1b3-1793625696606077800-54284`，恢复scope上限64、窗口7200秒、worker timeout 30000 ms。唯一一次初始Execution调用已完成并保存；旧驱动以完整 `same_native` 比较native `DuelResult` 与fixture重建结果，因私有checkpoint表示不同而停止。后续只读复核进一步发现，`result_at`在重建trace查询时只还原了可见卡和我方牌组，遗漏了对手牌组/手牌数量：冻结trace的event-49见证为39/1，而旧run的`query-witnesses.json`及manifest记录为0/0。故不能称旧manifest的公开观察完整匹配；仅原始49帧、16条决定、可见状态及我方牌组计数匹配。修正后的重建器从固定trace恢复39/1，并逐事件校验生成见证与trace。当前只读审计验证：保存的native结果通过修正后的event-49见证，但旧run的输入/计划身份不同于当前修正版本；它不可续跑。该run仍是暂停前批次中止，不能记为恢复或规则失败，也不能记为实验通过。

原始材料保存在`data/runtime/p4-r1b3/p4-r1b3-1793625696606077800-54284/`；早先的[停止后诊断](../../../data/runtime/p4-r1b3/p4-r1b3-1793625696606077800-54284/implementation-gate-diagnosis.json)保留不改；[追加只读账本审计](../../../data/runtime/p4-r1b3/p4-r1b3-1793625696606077800-54284/read-only-journal-audit.json)记录了准确的固定见证差异及核验结果。账本包含header、Execution call 1的begin及complete三条记录，1097字节，SHA-256=`d2db98bd25dcdfc9e71ca8c51dbd3a17afee8916efdea493573cf014d932e803`；仅1个已完成Execution，`unknown=0`、`reserved=0`、`abandoned=0`。没有Witness调用、暂停marker、协调器强杀、恢复重开或replay scope。原始scope及失败记录保持不变。

已修正后续运行的trace见证重建和event-49门禁：它比较认证提示、原始前缀、决定及包含对手隐藏区计数的完整公开QueryWitness，同时保留私有checkpoint编码差异回归。新增只读模式核验旧账本链和blob，并将当前正确固定见证与保存结果比较；报告明确标出旧输入/计划/source/driver身份差异，不让旧run续跑。修正只经过离线测试、构建和零调用预检，未用于追加原生调用。P4-R1b-3仍开放；本次没有达到进程暂停/重开或独立原生重放验收。未运行doctor、部署、提交或推送。
