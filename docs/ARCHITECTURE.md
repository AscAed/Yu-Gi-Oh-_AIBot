# 架构与模块边界

## 执行路径

```text
ygo-cli
  ├─ combo analyze/replay → ygo-api::combo → ygo-search::combo → ygo-engine-adapter
  ├─ combo plan/plan-replay → ygo-api planning v1–v5 → planner/goal/knowledge + engine adapter
  └─ knowledge validate/verify → ygo-knowledge → 独立原生案例 + ygo-storage 账本

ygo-engine-adapter → 子进程 worker → 固定 ocgcore ABI → 卡库/Lua 回调
```

本机 worker 隔离核心崩溃，父进程负责预算、报告和重放。`ocgcore`是效果结算权威；未知/不支持提示不得转成推测成功。

基线工具另提供只读`engine identity`及Python身份/覆盖/语言审计入口。研究入口使用独立协议oracle核对响应，涉及原生调用的批次按各自scope通过持久调用账本留证；纯离线审计不因此创建账本。这些模块不是正式v6或证明求解器。使用边界见[BASELINE_AUDIT](BASELINE_AUDIT.md)和[研究运行规范](RESEARCH_OPERATIONS.md)。

## Rust workspace

| crate | 边界 |
|---|---|
| `ygo-domain` | 卡、牌组、禁限规则、数据模型和引擎事件类型 |
| `ygo-storage` | 只读导入、内容寻址数据快照和本地持久化账本/证据 |
| `ygo-engine-adapter` | worker 协议、core ABI、卡片/Lua 回调、事件与提示转换、失败隔离 |
| `ygo-search` | `combo` 模块执行真实引擎前缀的有界 beam 搜索和评分；根模块另保留静态候选排序原型 |
| `ygo-knowledge` | 可追溯的结构化知识、来源/覆盖合同及原生规则案例验真 |
| `ygo-goal` | 目标表达式、实际状态事实和有界后续收益判断 |
| `ygo-planner` | 连接因果预测、局部观察/执行、独立重放、可恢复符号前沿及caller-driven first-turn执行游标；恢复游标仅保存进度，不构成v6资格或报告凭证，first-turn仍是内部集成 |
| `ygo-api` | 版本化请求/报告的库层编排；当前没有 HTTP 服务 |
| `ygo-cli` | 本机命令和 v1–v5 合同版本路由 |

workspace 成员列表和依赖方向以根 `Cargo.toml` 为准。

## Python、数据和知识

`python/ygo_data`提供身份、覆盖和规范化资料工具；`python/ygo_eval`已有研究案例、终场评价、公开观察投影、提示协议oracle、固定原生批次编排与历史来源恢复工具。它们服务于有限案例；16+32手赛事评估编排、构筑候选比较和留出评估闭环仍未交付。

研究数据流为：冻结案例与资产身份 → 版本化输入/来源校验 → 纯协议或公开观察审计 → 有明确scope的原生执行及账本/收据 → 独立重放和报告。不同入口并非都经过所有步骤：Ground Collapse准备只做纯Python离线校验，Curry的固定原生批次则使用独立runner与账本。报告发布、归档和运行时身份各有版本化合同，不能因报告结构正确而扩大资格。详细副作用见[研究运行规范](RESEARCH_OPERATIONS.md)，身份/发布见[证据合同](EVIDENCE_CONTRACTS.md)。

JSON schema在 `schemas/`，部署和实验fixture在 `tests/fixtures/`，人工知识包在 `knowledge/`。本机CDB、Lua、DLL、快照、账本和原生报告位于忽略目录 `data/`，身份信息在相关manifest/报告中。

## 可信度层级

1. 知识/规划器只能提出预测与候选，不能自行声称规则正确。
2. 当前状态从真实事件、查询、提示和已支持的规则映射建立；未知约束必须阻断依赖。
3. 执行证据和预测证据分开保存。故障注入只验证故障合同，不增加规则资格。
4. 推荐要通过独立重放和合同重算。`engine_verified`不等于评分高；评分 `heuristic` 不等于胜率。
5. first-turn 报告 v2、搜索前沿续跑和执行恢复游标是局部内部组件。执行恢复只完成End Phase/查询审计合成暂停重开路径；连续语义多动作等价与真实进程恢复仍未验收。正式 `combo plan` 仍只路由 v1–v5；完整 v6 门禁未通过。合同见[EXECUTION_RECOVERY](EXECUTION_RECOVERY.md)。

每个状态都应绑定规则、牌表、CDB、引擎、Lua、知识、合同和预算身份，具体字段以 schema/serde 验证代码为准。

## 拟议产品架构（尚未实现）

依据[产品愿景](PRODUCT_VISION.md)，未来本机浏览器通过本机服务调用库层编排，重型任务继续隔离worker执行；服务和界面不直接重写游戏规则或将中文指令拼成shell。中文显示/检索映射、用户牌组草稿、任务编排和候选更新各有独立边界，使用稳定卡号和不可变资产版本连接现有领域/存储。

构筑层消费知识关系与版本化评估报告，产生有约束候选；Combo层执行/比较候选，数据回到构筑评估。知识候选、原生执行、搜索完整性及最优性证明分别留证；拟议证明层不能借用engine_verified代替其资格。具体研究定义见[OPTIMALITY_RESEARCH](OPTIMALITY_RESEARCH.md)。

替代引擎必须适配提示、事件、信息边界和能力合同，经真实行为及证明兼容验收；现有EngineAdapter trait不自动提供任意引擎兼容。接口及实现任务见[API规划边界](API.md)与[实施计划](superpowers/plans/2026-10-19-product-evolution.md)，本节不声明已有HTTP、UI、构筑器或证明服务。
