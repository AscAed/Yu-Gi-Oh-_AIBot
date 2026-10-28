# CLI 与库接口

当前交付面包括本机 CLI/Rust库，以及仅绑定`127.0.0.1`的本机草稿工作台。解析器与JSON schema是规范性合同；工作台接口只用于本机草稿，不是通用远程API。

## CLI

- `engine doctor`, `engine smoke`：运行时资产/ABI 诊断与真实引擎 smoke。
- `engine identity --config <toml> [--output <json>]`：只读资产身份及脚本清单差异；不运行决斗，不授予构建或规则资格。
- `catalog`、`banlist`、`deck validate`：本地快照导入/查询和牌组合法性校验。
- `deck draft create|show|edit|import|export`：独立可保存草稿工具；允许残缺草稿，YDK/JSON仅承诺卡号、分区及数量往返，不替代`deck validate`。
- `workbench serve`：启动本机中文草稿网页，默认使用系统分配端口及`data/runtime/workbench/drafts`；可通过`--language-status FILE`加载只读C1字段状态，不返回候选正文。参数、端点、令牌和限制见[WORKBENCH](WORKBENCH.md)。
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
- 首批审计合同：`engine-identity`、`workspace-identity`、`build-record`、`release-evidence`、`coverage-inventory`、`language-audit`、`research-case`、`response-audit`各自为独立v1 schema。结构合法不等于来源可信、原生认证、完整性或最优性；命令和语义边界见[基线审计](BASELINE_AUDIT.md)。

`ApiService` 是库层的薄封装，不代表服务器进程或稳定 Web API。通用 `combo plan` 当前只接 v1–v5，不从 first-turn 内部模块自动推断版本。

First-turn 的 A3 可恢复进度接口见[`EXECUTION_RECOVERY.md`](EXECUTION_RECOVERY.md)。它从已收费且完成的起始调用开始，逐个公开提示动作推进，并将意图写入 `CallJournal` 后才调用适配器；它是内部库能力，不扩展当前 CLI/API 的正式分析合同，也不创建查询审计凭证。真实引擎暂停/重开尚未验收。

## 已有研究入口与副作用边界

`python -m ygo_eval.research`分派案例/问题结构验证、公开信息与终场审计、固定提示准备、原生批次和历史恢复等版本化入口。`prepare-ground-collapse-probe`的固定准备和`--verify-only`属于离线来源/协议合同，不构造可执行worker请求；Curry与Tenki原生批次则各自拥有scope、runner和持久账本，不能互相借用预算或资格。名称相同的`verify-only`、`prepare-only`在不同入口的进程及资产副作用可能不同，须按[研究运行规范](RESEARCH_OPERATIONS.md)和对应版本合同检查，不因名字推断安全。

已存在的研究schema只规定各自请求/报告形状，不授予可达性、响应接受、完整性或最优性资格。报告、源码归档、构建、runner和实际执行身份分开绑定，详见[证据合同](EVIDENCE_CONTRACTS.md)。具体CLI命令和输入仍以[RESEARCH_AUDIT](RESEARCH_AUDIT.md)、对应历史交接和解析器为准；历史示例不是自动执行授权。

## 工作台边界

当前HTTP接口仅服务工作台：草稿列表/新建/读取/条件更新、导入解析、导出、可选本地catalog检索，以及`GET /api/language-status?ids=...`只读字段状态。状态接口仅返回卡号、固定来源ID、候选/缺失/冲突/未知状态、稳定原因及候选哈希，不返回候选文字；状态文件缺失/损坏时返回未核验且不影响草稿编辑。草稿更新使用内容revision，过期revision返回冲突；浏览器不能传入文件路径。服务不执行shell、worker、FFI、分析或研究入口。中文语义、使用和再分发资格仍未核验。

## 其他拟议能力接口

以下仅定义[产品愿景](PRODUCT_VISION.md)所需能力，尚无HTTP地址、wire shape或新增schema；具体小任务设计须先读现有类型，避免复制不兼容结构。

| 能力边界 | 输入/产出意图 | 失败与兼容约束 |
|---|---|---|
| 卡牌查询/显示 | 语言、中文检索、字段过滤 → 稳定卡号、显示文本、版本/来源、覆盖 | 歧义或缺译明确；显示语言不改变引擎身份 |
| 牌组草稿 | 已实现`DeckDocumentV1`、CLI和本机工作台，可保存残缺草稿并导入/导出YDK/JSON | 不代表完整合法；见[DECK_DRAFTS](DECK_DRAFTS.md)和[WORKBENCH](WORKBENCH.md) |
| 牌组锁定/完整校验编排 | 拟议：主/额外/Side、锁定约束 → 修改候选及分析前校验 | 保持完整牌组合法性门禁；不得静默修改锁定卡 |
| 构筑候选/互动 | 指定卡、主题/字段、草稿/完整牌组 → 候选、关系、条件与证据 | 不覆盖原稿；未知/假设不变成认证；不违背锁定约束 |
| 牌组识别 | 卡组及目录/知识版本 → 多主题/字段、玩法假设、互动依据及未知 | setcode事实与玩法推断分开；混合/未知牌组不强制单标签 |
| 分析任务/评估 | 牌组、目标、情景、预算、版本 → 进度、报告、对照及恢复入口 | 失败/取消/未知消费保留；不泄露隐藏牌序；不保证所有版本可安全续跑 |
| 数据更新 | 来源和候选版本 → 差异、校验结果、启用/回滚状态 | 未来生效日、离线及证据失效独立处理；既有报告版本不变 |
| 最优性结果 | 精确问题、信息/随机模型 → 策略、值界、完整性及校验证据 | 分类见研究定义；未完成证明不改标为已证明 |

未来本机服务优先调用正式库接口，不解析人类摘要代替机器合同。v1–v5身份/重放路径保持不变；正式v6和证明能力分别版本化。可信知识、可执行线路、搜索完整性、最优性四个维度不得压为现有VerificationLevel的一个状态。

近期实施入口为[2026-10-28项目现状与路线](superpowers/plans/2026-10-28-project-status-and-next-steps.md)，完整目标任务分解见[产品演进计划](superpowers/plans/2026-10-19-product-evolution.md)，研究问题见[最优性定义](OPTIMALITY_RESEARCH.md)。


P1离线入口：`python -m ygo_eval.research audit-corpus --evidence ROLE=PATH [可重复] --runner PATH --output PATH`；独立报告合同为`schemas/prompt-corpus-audit.schema.json`，不会执行worker或写原生账本。退出0/1/2、来源与资格边界见[研究审计](RESEARCH_AUDIT.md)。
