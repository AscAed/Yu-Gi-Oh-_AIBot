# 数据与运行来源

首版从本机 Project Ignis expansions/cards.cdb 只读导入 OCG 卡片。只接受 cards.cdb，不导入 Rush、Skill 或 unofficial 数据库；card kind 为 monster/spell/trap，Fusion/Synchro/Xyz/Link 使用 type_flags 分类。alias、setcodes、等级／种族／属性、攻守、刻度及 link_marker 同步 Rust/Python/Schema。

OCG LFLists 固定提交 1051a65ab853fd84521aa919d1859f9468816c56，首次导入 2026.10 OCG，2026-10-01 生效。原文内容哈希、来源、提交、日期和 normalizer-v1 进入 JSON 快照。ID 为规范化内容和来源元数据的 SHA-256，load 时重算。latest-ocg 在开始请求时解析；找不到适用完整列表则报错。

运行目录冻结 CDB 与官方 Lua 文件。CDB、DLL、script manifest 和实际加载文件哈希附随结果。外部资产和个人路径保持忽略；来源文件的授权信息以各自项目 notices 为准，不能把项目自身许可视为外部数据库或引擎许可。
