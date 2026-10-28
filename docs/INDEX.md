# 文档入口

## 当前事实源

实现事实以代码、schema与可复现产物为准。当前状态、验证证据、产品目标和研究定义分别按下表读取；历史计划与对话只作背景。

| 问题 | 事实源 | 阅读边界 |
|---|---|---|
| 产品目标与完成门槛 | [PRODUCT_VISION.md](PRODUCT_VISION.md) | 用户全卡与全局最优目标的唯一事实源；局部预览不替代验收 |
| 全局最优的定义与证明关口 | [OPTIMALITY_RESEARCH.md](OPTIMALITY_RESEARCH.md) | 研究定义与可行性门禁，不代表现有能力或接口 |
| 当前状态与开放任务 | [TASKS.md](../TASKS.md) | 当前状态的唯一入口；各批次历史数字不覆盖顶部 |
| 验证结果与限制 | [TESTING.md](TESTING.md) | 按日期、源码与范围读取；旧结果不代表当前源码已复验 |
| 能力与差距 | [PROJECT_ASSESSMENT.md](PROJECT_ASSESSMENT.md) | 区分已验证、局部验证、未验证、未实现 |
| 依赖顺序与本轮任务 | [ROADMAP.md](ROADMAP.md)、[项目再规划](superpowers/plans/2026-10-27-project-realignment.md) | 研究与产品工作台双轨推进；完成状态仍只维护于TASKS |
| 研究运行、scope、预算、窗口及停止条件 | [RESEARCH_OPERATIONS.md](RESEARCH_OPERATIONS.md) | 研究操作规范；旧批次准备不构成新执行授权 |
| 报告、来源、会计和资格绑定 | [EVIDENCE_CONTRACTS.md](EVIDENCE_CONTRACTS.md) | 证据合同；来源身份、实际消费和资格分别核验 |
| 基线及研究工具用法 | [BASELINE_AUDIT.md](BASELINE_AUDIT.md)、[RESEARCH_AUDIT.md](RESEARCH_AUDIT.md) | 工具及合同说明；实跑状态和限制仍见TASKS/TESTING |
| 模块边界与数据流 | [ARCHITECTURE.md](ARCHITECTURE.md) | 以crate依赖和调用路径为准 |
| 环境自检范围、证据及未完成项 | [WORKSPACE_REVIEW.md](WORKSPACE_REVIEW.md) | 按方面记录检查范围、限制和后续工作，不覆盖TASKS或TESTING |
| 本机准备、构建、部署与诊断 | [DEPLOYMENT.md](DEPLOYMENT.md)、[scripts/](../scripts/) | 资产版本以manifest与部署配置为准；不由导航授予运行权限 |
| JSON、CLI与worker合同 | [schemas/](../schemas/)、[ENGINE_PROTOCOL.md](ENGINE_PROTOCOL.md)、[API.md](API.md)、[WORKBENCH.md](WORKBENCH.md)、[EXECUTION_RECOVERY.md](EXECUTION_RECOVERY.md) | schema和解析器为规范性定义；WORKBENCH记录当前本机HTTP界面与安全边界；执行恢复仅描述可恢复进度，不授予成功资格 |
| 规则分类与认证 | [RULES_SCOPE.md](RULES_SCOPE.md)、[FIRST_TURN_VERIFICATION.md](FIRST_TURN_VERIFICATION.md) | 规则资格只能由独立原生案例提升 |
| 数据来源、版本与许可 | [DATA_SOURCES.md](DATA_SOURCES.md) | 不提交外部卡库、脚本、图像或个人资产 |
| 历史计划、交接及故障链 | [HISTORY_INDEX.md](HISTORY_INDEX.md)、[任务历史快照](../TASKS_HISTORY.md)、[验证历史快照](TESTING_HISTORY.md) | 原入口保留历史标题锚点；快照是拆分前正文，不替代原报告、源码、账本及固定窗口边界 |

## 最近研究批次：Ground Collapse离线准备（已完成并暂停）

[本批交接](superpowers/plans/2026-10-27-ground-collapse-preparation-handoff.md)、[验证记录](TESTING.md)、[准备报告](../data/runtime/p1-ground-collapse-preparation-offline-2026-10-27/preparation.json)。本批完成FIELD_DISABLED56解析、独立opcode24/HINT_ZONE oracle、固定公开选区和合成来源链准备；准备及verify通过，新增native/runner/worker/FFI均为0。`execution_ready=false`，实际opcode24提示、掩码、原生可达、响应接受及完整性/概率/最优性资格仍未获得。

下一研究实验由TASKS开放项决定，须另定scope、预算和窗口；本准备报告不能直接启动原生实验。当前会计口径及未知值以TASKS顶部与对应TESTING证据为准，不在导航中复制累计数字。

## 最近产品工作台批次：首次失败诊断、草稿基础与本机界面（已完成）

[B2交接](superpowers/plans/2026-10-28-b2-workbench-handoff.md)、[工作台运行说明](WORKBENCH.md)、[牌组草稿CLI与合同](DECK_DRAFTS.md)。A1首次结果级错误及查询捕获失败回归通过；B1/B2提供版本化草稿、三分区编辑、本机浏览器操作和YDK/JSON往返，不赋予完整合法性或中文资格。实测范围见[TESTING](TESTING.md)。

## 最近执行恢复批次：P4-R1b可恢复循环接入（实现已接入，等价验证待补）

[执行恢复合同](EXECUTION_RECOVERY.md)、[P4-R1b交接](superpowers/plans/2026-10-28-p4-r1b-resumable-execution-loop-handoff.md)、[验证记录](TESTING.md)。新增版本化执行循环入口，保存语义阶段、End Phase和逐次查询审计游标；合成测试覆盖逐提示单动作暂停/重开、收费后未知消费拒绝重试，以及内层结果完成而外层快照未发布时的恢复对账。当前workspace串行总检为362 passed、36 ignored，详见TESTING的2026-10-28增补记录。连续语义多动作恢复等价、真实进程崩溃恢复和独立原生重放仍未认证；本批原生调用为0。

## 最近语言数据批次：39卡中文字段离线核验（完成并暂停）

[字段核验说明](LANGUAGE_REVIEW.md)、[数据来源说明](DATA_SOURCES.md)、[C1交接](superpowers/plans/2026-10-28-c1-language-review-handoff.md)。固定39卡样本与两份本地CDB完成只读字段存在性/来源核对；报告不含候选正文，工作台只读接口显示状态。语义、zh-SC类别、使用与再分发依据仍未知，未授予中文资格。实跑和限制见[TESTING](TESTING.md)。

## 最近执行器批次：A3离线执行检查点（已实现；真实运行未认证）

[执行恢复合同](EXECUTION_RECOVERY.md)、[A3交接](superpowers/plans/2026-10-28-a3-execution-recovery-handoff.md)和[验证记录](TESTING.md)。planner提供绑定输入的版本化检查点、调用前意图保存、单步推进及只读后重开；合成适配器证明暂停/重开与连续调用一致，并证明已完成尾部调用可复用、未决消费会阻断。本批没有原生、runner、worker或FFI调用。真实引擎持久化、暂停/重开和独立重放仍开放。

## 阅读路径

1. 新加入的代理：本文件 → [AGENTS.md](../AGENTS.md) → [TASKS](../TASKS.md) → [PROJECT_ASSESSMENT](PROJECT_ASSESSMENT.md) → 相关模块文档。
2. 产品与双轨任务：[PRODUCT_VISION](PRODUCT_VISION.md) → [ROADMAP](ROADMAP.md) → [项目再规划](superpowers/plans/2026-10-27-project-realignment.md)。最优性工作先读[OPTIMALITY_RESEARCH](OPTIMALITY_RESEARCH.md)。
3. 研究与证据：[RESEARCH_OPERATIONS](RESEARCH_OPERATIONS.md) → [EVIDENCE_CONTRACTS](EVIDENCE_CONTRACTS.md) → 对应工具文档、当前交接与TESTING；具体运行须遵守该次授权和停止条件。
4. 运行与来源：[DEPLOYMENT](DEPLOYMENT.md) → [ENVIRONMENT_AUDIT](ENVIRONMENT_AUDIT.md)、[DATA_SOURCES](DATA_SOURCES.md)、[TOURNAMENT_RESELECTION](TOURNAMENT_RESELECTION.md)、[TOURNAMENT_SOURCE_GATE](TOURNAMENT_SOURCE_GATE.md) → 对应日期验证和实际报告。
5. 实现设计：[ARCHITECTURE](ARCHITECTURE.md) → [DOMAIN_MODEL](DOMAIN_MODEL.md)、[ENGINE_ADAPTERS](ENGINE_ADAPTERS.md)、[ENGINE_PROTOCOL](ENGINE_PROTOCOL.md)、[SEARCH_AND_SCORING](SEARCH_AND_SCORING.md)、[API](API.md)。规则与规划另见[FIRST_TURN_PILOT](FIRST_TURN_PILOT.md)、[SEMANTIC_PLANNING](SEMANTIC_PLANNING.md)、[GOAL_PLANNING](GOAL_PLANNING.md)、[BREAK_SWORD_VERIFICATION](BREAK_SWORD_VERIFICATION.md)、[RECOVERY_PLANNING](RECOVERY_PLANNING.md)、[ASH_STRATEGY_PLANNING](ASH_STRATEGY_PLANNING.md)及对应Rust测试。
6. 历史追溯：[HISTORY_INDEX](HISTORY_INDEX.md) → 指定日期交接、TESTING及[IMPLEMENTATION_NOTES](IMPLEMENTATION_NOTES.md)。历史命令和待办不能直接作为当前执行指令。

维护时只在TASKS更新当前状态，在TESTING追加对应范围的验证；ROADMAP保留依赖顺序。目标变化先改PRODUCT_VISION，再同步研究定义和计划。每份文档应独立说明范围，使用仓库相对链接；历史资料保留其来源、未知值与资格边界。
