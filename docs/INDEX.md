# AI 文档入口

本页是导航，不维护项目状态。开始前先读仓库根目录的 `AGENTS.md`、本页和 [TASKS.md](../TASKS.md)。历史计划与聊天用于追溯背景；实现状态以当前源码、schema 和日期化验证记录为准。

## 唯一事实源

| 问题 | 事实源 | 阅读规则 |
|---|---|---|
| 当前能力、开放任务、验收门槛 | [TASKS.md](../TASKS.md) | 当前状态只在此维护 |
| 某次验证的范围、结果和限制 | [TESTING.md](TESTING.md)；较早批次的详细归档见[TESTING_HISTORY.md](TESTING_HISTORY.md) | 按日期、commit、资产和执行范围读取 |
| 当前部署与本机环境 | [DEPLOYMENT.md](DEPLOYMENT.md)、[ENVIRONMENT_AUDIT.md](ENVIRONMENT_AUDIT.md) | 区分源码、隔离候选、旧发布包和冻结资产 |
| 本机证据是否可清理 | [EVIDENCE_RETENTION.md](EVIDENCE_RETENTION.md) | 被忽略或有哈希清单不代表可删除或已备份 |
| 产品目标、阶段依赖、完成差距 | [PRODUCT_VISION.md](PRODUCT_VISION.md)、[ROADMAP.md](ROADMAP.md)、[PROJECT_ASSESSMENT.md](PROJECT_ASSESSMENT.md) | 目标与计划不等于已实现能力 |
| 模块、接口和数据流 | [ARCHITECTURE.md](ARCHITECTURE.md)、[API.md](API.md) | 源码与版本化合同优先 |
| 研究副作用、预算、证据资格 | [RESEARCH_OPERATIONS.md](RESEARCH_OPERATIONS.md)、[EVIDENCE_CONTRACTS.md](EVIDENCE_CONTRACTS.md) | 准备材料不授予执行资格 |
| 历史批次和交接 | [HISTORY_INDEX.md](HISTORY_INDEX.md)、[TASKS_HISTORY.md](../TASKS_HISTORY.md)、[TESTING_HISTORY.md](TESTING_HISTORY.md) | 由索引定位原记录，不把旧计划当成当前指令 |

## 子系统导航

| 子系统 | 入口 | 当前边界 |
|---|---|---|
| 牌组草稿工作台 | [DECK_DRAFTS.md](DECK_DRAFTS.md)、[WORKBENCH.md](WORKBENCH.md) | 离线编辑、保存、导入与导出；不认证卡片语义或牌组效果 |
| 分析 HTTP 与任务 | [WORKBENCH_ANALYSIS_HTTP.md](WORKBENCH_ANALYSIS_HTTP.md)、[WORKBENCH_ANALYSIS_JOBS.md](WORKBENCH_ANALYSIS_JOBS.md)、[WORKBENCH_ANALYSIS_PERSISTENCE.md](WORKBENCH_ANALYSIS_PERSISTENCE.md) | 显式配置才启用串行分析；普通启动保持 `analysis_not_configured` |
| 引擎、提示与恢复 | [ENGINE_PROTOCOL.md](ENGINE_PROTOCOL.md)、[EXECUTION_RECOVERY.md](EXECUTION_RECOVERY.md)、[FIRST_TURN_VERIFICATION.md](FIRST_TURN_VERIFICATION.md) | ocgcore 执行效果；合成故障证据不替代真实执行证据 |
| 卡片数据与语言 | [DATA_SOURCES.md](DATA_SOURCES.md)、[LANGUAGE_REVIEW.md](LANGUAGE_REVIEW.md) | 来源、语义、许可、字段完整度分别判定 |
| 搜索、规划与最优性 | [OPTIMALITY_RESEARCH.md](OPTIMALITY_RESEARCH.md)、[BASELINE_AUDIT.md](BASELINE_AUDIT.md) | 局部搜索或重放不证明完整性、全局最优或全卡适用 |
| 部署与本机证据 | [DEPLOYMENT.md](DEPLOYMENT.md)、[EVIDENCE_RETENTION.md](EVIDENCE_RETENTION.md) | 发布包身份、运行资格和清理资格分别核验 |

## 推荐追踪路径

1. 从 TASKS 选定当前开放项和它的退出条件。
2. 回到源码、schema、配置和数据流确认实现位置。
3. 从 TESTING 找到对应日期与源码/资产身份的验证记录。
4. 需要历史脉络时，通过 HISTORY_INDEX 找原始计划、审计或交接。
5. 涉及本机资产时，再核对 DEPLOYMENT、ENVIRONMENT_AUDIT 和 EVIDENCE_RETENTION。

## 历史资料分组

HISTORY_INDEX 按日期和主题索引 H3 恢复窗口、L1 卡片复核批次、P1/P4 研究交接、W1 工作台分析和 W2 草稿迁移。`TASKS.md`维护当前状态，历史任务快照在`TASKS_HISTORY.md`；`TESTING.md`维护近期验证，较早批次的详细正文在`TESTING_HISTORY.md`。为保持既有链接，当前页中部分旧标题只保留跳转锚点，阅读时应继续到归档页；历史结果不覆盖当前源码、TASKS状态或更新的验证记录。
