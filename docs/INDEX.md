# 文档入口

## 当前事实源

遇到状态冲突时按下表处理。实现事实以代码、schema 与可复现产物为准；历史对话和旧计划只提供背景。

| 问题 | 事实源 | 规则 |
|---|---|---|
| 用户最终想要什么、什么才算产品完成 | [`PRODUCT_VISION.md`](PRODUCT_VISION.md) | 目标唯一事实源；预览成果不替代全卡/最优性验收 |
| 全局最优究竟要证明什么 | [`OPTIMALITY_RESEARCH.md`](OPTIMALITY_RESEARCH.md) | 研究定义与可行性关口，不代表现有能力或已发布接口 |
| 现在做到哪一步、哪些工作未完成 | [`../TASKS.md`](../TASKS.md) | 只在顶部维护当前状态和开放任务；完成情况附验证来源 |
| 最近一次验证了什么 | [`TESTING.md`](TESTING.md) | 顶部是最新证据；旧阶段记录只作历史，不代表当前源码复验 |
| 能力范围、不可声称的能力 | [`PROJECT_ASSESSMENT.md`](PROJECT_ASSESSMENT.md) | 用“已验证/局部/未实现”区分能力，不把计划写成实现 |
| 紧接着的开发顺序 | [`ROADMAP.md`](ROADMAP.md) | 与任务表的开放项保持一致，不复制历史待办 |
| 各阶段具体任务、输入/产出及验收 | [`产品演进计划`](superpowers/plans/2026-10-19-product-evolution.md) | 未来任务分解；完成状态仍只维护于TASKS |
| 模块边界和数据流 | [`ARCHITECTURE.md`](ARCHITECTURE.md) | 以 crate 与调用路径为准 |
| 本机准备、构建、部署、诊断 | [`DEPLOYMENT.md`](DEPLOYMENT.md) 与 `scripts/` | 资产版本以 manifest 和部署配置为准 |
| JSON/CLI/worker 合同 | `schemas/`、[`ENGINE_PROTOCOL.md`](ENGINE_PROTOCOL.md)、[`API.md`](API.md) | schema 和解析器是规范性定义 |
| 规则分类与认证 | [`RULES_SCOPE.md`](RULES_SCOPE.md)、[`FIRST_TURN_VERIFICATION.md`](FIRST_TURN_VERIFICATION.md) | 规则资格只能由独立原生案例提升 |
| 数据来源、版本、许可边界 | [`DATA_SOURCES.md`](DATA_SOURCES.md) | 不提交外部卡库、脚本、图像或个人资产 |

## 阅读路径

1. 新加入的编码代理：本文件 → 根目录 `AGENTS.md` → `TASKS.md` → `PROJECT_ASSESSMENT.md` → 相关模块文档。
2. 运行或部署：`DEPLOYMENT.md` → 运行后查看 `TESTING.md` 和实际报告。
3. 修改规则/规划：`FIRST_TURN_VERIFICATION.md`、`FIRST_TURN_PILOT.md`、具体 profile 文档及对应 Rust 测试。
4. 追溯历史取舍：`IMPLEMENTATION_NOTES.md`、`docs/superpowers/plans/` 和 `TESTING.md` 中明确标注的历史条目。
5. 产品规划：`PRODUCT_VISION.md` → `PROJECT_ASSESSMENT.md` → `ROADMAP.md` → `superpowers/plans/2026-10-19-product-evolution.md`；最优性工作另先读 `OPTIMALITY_RESEARCH.md`。

## 文档地图

- **现状与工作：** `TASKS.md`、`PROJECT_ASSESSMENT.md`、`ROADMAP.md`、`TESTING.md`
- **目标与未来实施：** `PRODUCT_VISION.md`、`OPTIMALITY_RESEARCH.md`、`superpowers/plans/2026-10-19-product-evolution.md`
- **实现设计：** `ARCHITECTURE.md`、`DOMAIN_MODEL.md`、`ENGINE_ADAPTERS.md`、`ENGINE_PROTOCOL.md`、`SEARCH_AND_SCORING.md`、`API.md`
- **规则、目标与实验：** `RULES_SCOPE.md`、`FIRST_TURN_VERIFICATION.md`、`FIRST_TURN_PILOT.md`、`SEMANTIC_PLANNING.md`、`GOAL_PLANNING.md`、`BREAK_SWORD_VERIFICATION.md`、`RECOVERY_PLANNING.md`、`ASH_STRATEGY_PLANNING.md`
- **运行与来源：** `DEPLOYMENT.md`、`ENVIRONMENT_AUDIT.md`、`DATA_SOURCES.md`、`TOURNAMENT_RESELECTION.md`、`TOURNAMENT_SOURCE_GATE.md`

## 维护约定

- 当前状态只维护一份：`TASKS.md`；`ROADMAP.md` 仅列开放工作的依赖顺序，详细任务不重复勾选。
- 目标先改 `PRODUCT_VISION.md`，再同步研究定义和实施计划。未来接口明确标注“拟议”，不能把研究结果分类写成现有schema。
- 每次可复验验证追加到 `TESTING.md` 顶部，写明提交、命令、计数、资产版本及限制。历史结果不覆盖、不推断为当前结果。
- 功能说明写支持条件、失败/未知行为、CLI 和证据；不复制长测试日志或另一个文档的待办清单。
- 实验计划完成后标为历史计划；如果实现或合同发生变化，更新规范文档并链接旧计划。
- 日期使用 ISO `YYYY-MM-DD`；固定版本用完整 commit/hash；状态词固定为“已验证”“局部验证”“未验证”“未实现”。
- 每份文档应能独立说明其范围；跨文档链接使用仓库相对路径。
