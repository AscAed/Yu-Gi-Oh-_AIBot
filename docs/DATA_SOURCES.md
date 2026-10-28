# 数据与运行来源

首版从本机 Project Ignis expansions/cards.cdb 只读导入 OCG 卡片。只接受 cards.cdb，不导入 Rush、Skill 或 unofficial 数据库；card kind 为 monster/spell/trap，Fusion/Synchro/Xyz/Link 使用 type_flags 分类。alias、setcodes、等级／种族／属性、攻守、刻度及 link_marker 同步 Rust/Python/Schema。

上述是当前实现限制，不是全部正式OCG发行完整性的证明。[BabelCDB](https://github.com/ProjectIgnis/BabelCDB)还维护独立发行库和预发行库；未来全卡范围须按[PRODUCT_VISION](PRODUCT_VISION.md)和P0清单核对区域、发行日、卡号迁移、别名及脚本。中文名称/正文/别名/字段数据的可信来源和授权尚待P2落实，不默认英文CDB或WindBot中文对白已经满足。启动/每小时/手动检查、候选更新与回滚属于未来计划，当前仍仅本地导入。

OCG LFLists 固定提交 1051a65ab853fd84521aa919d1859f9468816c56，首次导入 2026.10 OCG，2026-10-01 生效。原文内容哈希、来源、提交、日期和 normalizer-v1 进入 JSON 快照。ID 为规范化内容和来源元数据的 SHA-256，load 时重算。latest-ocg 在开始请求时解析；找不到适用完整列表则报错。

运行目录冻结 CDB 与官方 Lua 文件。CDB、DLL、script manifest 和实际加载文件哈希附随结果。外部资产和个人路径保持忽略；来源文件的授权信息以各自项目 notices 为准，不能把项目自身许可视为外部数据库或引擎许可。

## 分发边界

本地部署依赖 Project Ignis、BabelCDB、CardScripts、ocgcore/Lua 与 LFLists 的固定上游版本。各数据/代码资产有各自来源与许可；本仓库目前未维护可供发布审查的一项一行许可及再分发清单。`dist/` 是本机部署产物，不可因它成功构建就推断可公开分发。任何对外二进制/数据发布前，需逐资产记录来源 URL、精确版本、文件哈希、许可证/notice、修改方式及再分发权限；不能确认的资产不打包发布。


## P0/P2 只读清点与语言调查工具（2026-10-19）

`python -m ygo_data.coverage tournament-evidence --source configs/tournament-2026.source.json --output <release-evidence.json>` 将既有39卡来源转成独立发行证据输入。`released_by` 保留有证据的发行上界，`release_date: null` 不伪造首发日期。

`python -m ygo_data.coverage inventory --cdb <cards.cdb> --scripts <scripts.json> --script-root <script目录> --evidence <release-evidence.json> --evidence-root <原始凭据根目录> --output <report.json>` 使用 SQLite `mode=ro` 并核对扫描前后CDB/manifest身份。`--script-root` 缺省时脚本只有声明，状态为unknown；提供时核对实际字节。`--evidence-root` 缺省只登记发行声明，提供时拒绝缺失、越界和哈希不符的凭据。报告的`provided_evidence_bytes_checked`仅覆盖提供的凭据，`source_verified`仍为false，不代表全卡发行或来源语义获独立认证。清单不删除alias原号，保留缺失、环及多跳；优先原卡号专用脚本，仅alias目标存在脚本时保留unknown/alias_script_reuse_unverified，不能用同名/替代图的假定授予效果覆盖；OT预发行位与发行声明冲突保持诊断。

清点报告始终`complete: false`、`denominator_status: unresolved`、`dynamic_dependencies_verified: false`。脚本covered仅表示专用脚本与manifest字节匹配，不表示动态依赖或效果语义完整；不对Lua正则扫描授予资格。全卡发行分母须补充完整独立发行证据，CDB行数和上游差集仅用于发现缺口。JSON合同见`schemas/coverage-inventory.schema.json`及`schemas/release-evidence.schema.json`。

`python -m ygo_data.language audit --sources configs/language-sources-2026-10-19.json --sample <release-evidence.json> [--records <local-language-records.json>] --output <report.json>`逐字段绑定name/text/alias/archetypes来源、语言和核对状态。简繁各有独立记录，同名多ID公开歧义，不猜卡号；没有输入的语言/字段保持缺失。报告始终`qualified: false`，独立语义审阅门禁尚未实现；provenance_checks_passed只说明声明结构无已知缺口。合同见`schemas/language-audit.schema.json`。

来源登记见`configs/language-sources-2026-10-19.json`。本轮代理联网取得mycard固定提交的zh-CN和zh-SC数据库；39卡zh-CN均可按既有卡号找到，但中文名/正文仅为未人工核对的候选，不扩展到alias/字段可信资格。zh-SC路径含义未确认，不能据此自动当作繁体。取得的树未发现LICENSE，GitHub license端点404、README仅称测试数据库，因此再分发权限未知；这不是对不存在任何许可的法律结论。全部外部原始文字/库和本机报告仅置于忽略的`data/runtime/baseline-2026-10-19/data/`，不提交正文。

## C1离线字段核验（2026-10-28）

新增`python -m ygo_data.language_review audit --output <独占报告路径>`，固定读取上述来源清单、39卡冻结发行样本、语言记录和两份CDB；SQLite只读，采集前后核对输入哈希。报告合同为`schemas/language-field-review-v1.schema.json`，实跑产物位于忽略目录`data/runtime/c1-language-review-offline-2026-10-28/language-review.json`。来源清单、样本、记录和CDB哈希、字段数量及其限制集中见[LANGUAGE_REVIEW](LANGUAGE_REVIEW.md)。

此核验只确认字段是否存在、来源记录/卡号映射以及候选值摘要；不判断翻译语义、zh-SC语言类别、别名映射、使用权或再分发权。报告仅存名称/正文候选哈希，不存文字；工作台状态接口也不返回正文。正式语言资格仍未通过，原始CDB和语言记录继续留在忽略目录。
