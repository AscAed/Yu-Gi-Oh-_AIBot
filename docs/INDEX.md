# 文档导航

## 信息优先级

最新实施见[H2.2交接](superpowers/plans/2026-11-01-w1h22-analysis-http-handoff.md)：六个分析HTTP端点和无路径投影已接入；普通启动仍未配置分析后端。最终合成验收状态回到TASKS与TESTING。

H2.1为H2.2提供持久操作提交核心，见[H2.1交接](superpowers/plans/2026-10-31-w1h21-analysis-operation-handoff.md)。H2.2已有六端点实现、严格合同和合成测试；完整验收仍有故障矩阵等门禁开放。接口细节见[HTTP合同](WORKBENCH_ANALYSIS_HTTP.md)，实施与证据状态以[TASKS](../TASKS.md)、[TESTING](TESTING.md)及[H2.2交接](superpowers/plans/2026-11-01-w1h22-analysis-http-handoff.md)为准。当前路线见[W1-H2.1后路线](superpowers/plans/2026-11-01-post-w1h21-project-route.md)。

实现事实以当前源码、schema和可复现产物为准。按职责读取以下唯一事实源；历史计划和聊天仅作背景。

| 需要回答 | 权威入口 | 使用规则 |
|---|---|---|
| 当前状态、开放项、提交/部署门槛 | [TASKS.md](../TASKS.md) | 唯一当前状态入口 |
| 某次验证做了什么、结果与限制 | [TESTING.md](TESTING.md) | 按日期、commit、资产和运行范围判读；旧记录不等于当前复验 |
| 产品目标和验收愿景 | [PRODUCT_VISION.md](PRODUCT_VISION.md) | 目标唯一来源；局部样例不代表达成 |
| 全局最优定义与证明门槛 | [OPTIMALITY_RESEARCH.md](OPTIMALITY_RESEARCH.md) | 研究定义，不代表当前能力或可行性已证 |
| 阶段依赖及退出条件 | [ROADMAP.md](ROADMAP.md) | 不维护阶段完成状态；进度回到TASKS |
| 已有能力及差距矩阵 | [PROJECT_ASSESSMENT.md](PROJECT_ASSESSMENT.md) | 引用TASKS/TESTING，不覆盖其状态 |
| 模块边界和数据流 | [ARCHITECTURE.md](ARCHITECTURE.md) | crate依赖与调用路径为准 |
| 环境清点、证据保留和清理约束 | [ENVIRONMENT_AUDIT.md](ENVIRONMENT_AUDIT.md)、[EVIDENCE_RETENTION.md](EVIDENCE_RETENTION.md) | 哈希清单不等于备份；保留策略优先于清理便利 |
| 研究scope、预算、窗口和副作用 | [RESEARCH_OPERATIONS.md](RESEARCH_OPERATIONS.md)、[EVIDENCE_CONTRACTS.md](EVIDENCE_CONTRACTS.md) | 准备文档不授予执行权限 |
| 本机构建、包身份和部署边界 | [DEPLOYMENT.md](DEPLOYMENT.md) | 区分当前checkout、构建产物、冻结资产和历史记录 |
| 历史文档/批次定位 | [HISTORY_INDEX.md](HISTORY_INDEX.md)、[TASKS_HISTORY.md](../TASKS_HISTORY.md)、[TESTING_HISTORY.md](TESTING_HISTORY.md) | 保留原证据和来源，不视作当前状态 |

## 推荐阅读顺序

1. 新任务先读仓库根目录的`AGENTS.md`、本页和[TASKS.md](../TASKS.md)。
2. 涉及能力判断时再读[PROJECT_ASSESSMENT.md](PROJECT_ASSESSMENT.md)和[ROADMAP.md](ROADMAP.md)。
3. 根据模块进入对应接口/合同文档；运行或部署主张必须回到[TESTING.md](TESTING.md)的具体证据。
4. 需要历史上下文时用[HISTORY_INDEX.md](HISTORY_INDEX.md)定位原记录；不要把旧计划当作当前命令或授权。

## 子系统入口

| 子系统 | 设计与合同 | 当前界面/操作边界 |
|---|---|---|
| 工作台草稿 | [DECK_DRAFTS.md](DECK_DRAFTS.md)、[WORKBENCH.md](WORKBENCH.md)、[schemas](../schemas/) | 仅本机草稿编辑/导入导出；中文候选仍按其证据状态展示 |
| 受限分析接入 | [WORKBENCH_ANALYSIS_HTTP.md](WORKBENCH_ANALYSIS_HTTP.md)、[WORKBENCH_ANALYSIS_JOBS.md](WORKBENCH_ANALYSIS_JOBS.md)、[WORKBENCH_ANALYSIS_PERSISTENCE.md](WORKBENCH_ANALYSIS_PERSISTENCE.md)、[API.md](API.md) | B3内部协调器未连接工作台分析HTTP；真实分析未交付 |
| 引擎与报告 | [ENGINE_PROTOCOL.md](ENGINE_PROTOCOL.md)、[EXECUTION_RECOVERY.md](EXECUTION_RECOVERY.md)、[FIRST_TURN_VERIFICATION.md](FIRST_TURN_VERIFICATION.md) | ocgcore为效果执行权威；证据等级不能互相替代 |
| 数据与语言 | [DATA_SOURCES.md](DATA_SOURCES.md)、[LANGUAGE_REVIEW.md](LANGUAGE_REVIEW.md) | 来源、语义、许可及字段覆盖分别核验 |
| 研究工作流 | [BASELINE_AUDIT.md](BASELINE_AUDIT.md)、[RESEARCH_AUDIT.md](RESEARCH_AUDIT.md)、[P1_MICROCASE.md](P1_MICROCASE.md) | 使用单独scope与预算；保存的准备材料不自动启动实验 |

历史快照、交接及故障链的清单见[历史索引](HISTORY_INDEX.md)。本页只负责导航，不复制任务状态、验证数字或阶段历史。
