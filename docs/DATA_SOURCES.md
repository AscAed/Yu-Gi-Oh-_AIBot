# 数据与运行来源

首版从本机 Project Ignis expansions/cards.cdb 只读导入 OCG 卡片。只接受 cards.cdb，不导入 Rush、Skill 或 unofficial 数据库；card kind 为 monster/spell/trap，Fusion/Synchro/Xyz/Link 使用 type_flags 分类。alias、setcodes、等级／种族／属性、攻守、刻度及 link_marker 同步 Rust/Python/Schema。

上述是当前实现限制，不是全部正式OCG发行完整性的证明。[BabelCDB](https://github.com/ProjectIgnis/BabelCDB)还维护独立发行库和预发行库；未来全卡范围须按[PRODUCT_VISION](PRODUCT_VISION.md)和P0清单核对区域、发行日、卡号迁移、别名及脚本。中文名称/正文/别名/字段数据的可信来源和授权尚待P2落实，不默认英文CDB或WindBot中文对白已经满足。启动/每小时/手动检查、候选更新与回滚属于未来计划，当前仍仅本地导入。

OCG LFLists 固定提交 1051a65ab853fd84521aa919d1859f9468816c56，首次导入 2026.10 OCG，2026-10-01 生效。原文内容哈希、来源、提交、日期和 normalizer-v1 进入 JSON 快照。ID 为规范化内容和来源元数据的 SHA-256，load 时重算。latest-ocg 在开始请求时解析；找不到适用完整列表则报错。

运行目录冻结 CDB 与官方 Lua 文件。CDB、DLL、script manifest 和实际加载文件哈希附随结果。外部资产和个人路径保持忽略；来源文件的授权信息以各自项目 notices 为准，不能把项目自身许可视为外部数据库或引擎许可。

## 分发边界

本地部署依赖 Project Ignis、BabelCDB、CardScripts、ocgcore/Lua 与 LFLists 的固定上游版本。各数据/代码资产有各自来源与许可；本仓库目前未维护可供发布审查的一项一行许可及再分发清单。`dist/` 是本机部署产物，不可因它成功构建就推断可公开分发。任何对外二进制/数据发布前，需逐资产记录来源 URL、精确版本、文件哈希、许可证/notice、修改方式及再分发权限；不能确认的资产不打包发布。
