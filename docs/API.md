# CLI 与库接口

当前交付面是本机 CLI 和 Rust 库，没有 HTTP/网页服务。解析器与 JSON schema 是规范性合同，本页只索引入口和版本边界。

## CLI

- `engine doctor`, `engine smoke`：运行时资产/ABI 诊断与真实引擎 smoke。
- `catalog`、`banlist`、`deck validate`：本地快照导入/查询和牌组合法性校验。
- `combo analyze`、`combo replay`：通用引擎前缀搜索和独立重放。
- `combo plan`、`combo plan-replay`：读取并分派规划合同 v1–v5；旧报告按各自版本验证。
- `knowledge validate`、`knowledge verify`：知识来源/合同检查、独立原生规则案例验真。
- `card explain`：有限知识profile中的卡片解释和条件关联，不是全卡中文检索或通用互动认证。

实际参数以 `crates/ygo-cli/src/lib.rs` 命令解析、`crates/ygo-cli/src/main.rs` 执行路由为准。`catalog sync`、`deck optimize`、`eval run`虽有解析枚举，当前执行返回不支持；不能因名称存在就称已有功能。当前也没有通用 `--help` 分派，不能把它当已实现帮助入口。

## 合同位置

- 请求/报告：`schemas/`；请求字段和约束还由 `crates/ygo-api` 中相应版本 Rust 类型校验。
- 引擎 worker：[`ENGINE_PROTOCOL.md`](ENGINE_PROTOCOL.md)。
- 数据/牌组：领域类型与 snapshot schema；不把本地机器路径当成可移植合同。
- planning v1–v5 的版本分派在 `crates/ygo-cli/src/main.rs`；first-turn v6 尚没有正式规划 CLI。

`ApiService` 是库层的薄封装，不代表服务器进程或稳定 Web API。通用 `combo plan` 当前只接 v1–v5，不从 first-turn 内部模块自动推断版本。

## 拟议能力接口（未发布）

以下仅定义[产品愿景](PRODUCT_VISION.md)所需能力，尚无HTTP地址、wire shape或新增schema；具体小任务设计须先读现有类型，避免复制不兼容结构。

| 能力边界 | 输入/产出意图 | 失败与兼容约束 |
|---|---|---|
| 卡牌查询/显示 | 语言、中文检索、字段过滤 → 稳定卡号、显示文本、版本/来源、覆盖 | 歧义或缺译明确；显示语言不改变引擎身份 |
| 牌组草稿/校验 | 主/额外/Side、锁定约束 → 可保存草稿或指定版本完整校验 | 草稿可残缺；完整分析沿用合法性门禁；导入导出数量往返 |
| 构筑候选/互动 | 指定卡、主题/字段、草稿/完整牌组 → 候选、关系、条件与证据 | 不覆盖原稿；未知/假设不变成认证；不违背锁定约束 |
| 牌组识别 | 卡组及目录/知识版本 → 多主题/字段、玩法假设、互动依据及未知 | setcode事实与玩法推断分开；混合/未知牌组不强制单标签 |
| 分析任务/评估 | 牌组、目标、情景、预算、版本 → 进度、报告、对照及恢复入口 | 失败/取消/未知消费保留；不泄露隐藏牌序；不保证所有版本可安全续跑 |
| 数据更新 | 来源和候选版本 → 差异、校验结果、启用/回滚状态 | 未来生效日、离线及证据失效独立处理；既有报告版本不变 |
| 最优性结果 | 精确问题、信息/随机模型 → 策略、值界、完整性及校验证据 | 分类见研究定义；未完成证明不改标为已证明 |

未来本机服务优先调用正式库接口，不解析人类摘要代替机器合同。v1–v5身份/重放路径保持不变；正式v6和证明能力分别版本化。可信知识、可执行线路、搜索完整性、最优性四个维度不得压为现有VerificationLevel的一个状态。

实施入口为[产品演进计划](superpowers/plans/2026-10-19-product-evolution.md)，研究合同见[最优性定义](OPTIMALITY_RESEARCH.md)。
