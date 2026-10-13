# 领域模型

CardId(u32) 识别原始卡片；Card 记录小写 monster/spell/trap、alias、type_flags、setcodes、等级／种族／属性、攻守、刻度及 link_marker。额外分类由类型位表示，别名合并用于同名数量与禁限上限，原始卡号用于引擎脚本和实例。

Deck 保存 main/extra/side。验证完整目录存在、字段一致、未知卡／别名环、额外分类、Token/Skill 排除、40–60 主卡与至多15额外/side、跨三副牌的同名上限。固定起手使用原始主卡组实例逐个移除，要求恰好五张且不能超出已有数量。

DataSnapshot v2 固定数据与来源哈希、版本和生效日期。Checkpoint 是核心查询的回合、阶段、LP 与所有区域卡片/位置/超量素材。它只用于展示和评分；完整隐藏状态由决策历史与真实核心重建，不能据此做状态合并。

CoreEventFrame 保留序号、opcode、原始字节及 fields，Prompt/Decision/Choice 使用类型化响应。AnalysisReport 区分引擎验证等级与启发式强度，绑定完整版本和前缀，保留脚本哈希、终场、步骤和重放结果。
