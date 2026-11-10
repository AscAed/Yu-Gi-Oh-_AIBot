# L1中文数据人工复核：首批3卡

日期：2026-11-02。范围仅为固定mycard `zh-CN` 候选源中3张卡的名称及效果语义，与Konami官方OCG简体中文卡片页逐项对照。此记录是人工来源交叉核对，不改写C1报告、语言记录、CDB或工作台状态。

## 输入与复核方法

- 固定来源：`mycard-zh-CN-217ae165`，上游提交`217ae165c1886af2fc36b823fc08f9fc3ec13185`；本地来源清单记录该数据库SHA-256为`ff52f585de24a762a4e613ac37654b1a7fb15a58990c14f5eada85f28c3be152`。
- 冻结C1报告：`data/runtime/c1-language-review-offline-2026-10-28/language-review.json`，SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`。以下列出该报告中对应zh-CN候选字段哈希，供复核对象绑定；不复制候选正文。
- 每张卡在官方OCG简体中文详情页核对卡名、卡种/召唤素材条件及效果的发动条件、处理结果和附加限制。三张卡均未发现会改变效果含义的差异；词语选择及排版存在差别。本结果不等于官方对mycard文本的认证，也不覆盖其他语言或全39卡。

| 卡号 | 官方页面 | zh-CN名称 SHA-256 | zh-CN正文 SHA-256 | 本批结果 |
|---:|---|---|---|---|
| 1621413 | [暗镇魂超量龙](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=12639&ope=2&request_locale=cn) | `03f5d805fe6fed8ae25bb8e8f4805d7f621f22724054aac86663bf3bcb0f716b` | `1cd4fc662dbec341c6b184c83575720b4a0cb93e60aa34dc6ce84c5fe13105a3` | 名称及效果语义对齐 |
| 4993187 | [W：P变幻舞夜](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=22715&ope=2&request_locale=cn) | `bc39f760faa6260c3b95dc7b362c1d56aada69fa9e81ea53c62e617ec0599256` | `71eed8eb6aade576761088ec05b07e48d9650e82e20c41ed919dac253fd3acdd` | 名称及效果语义对齐 |
| 10045474 | [无限泡影](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=13631&ope=2&request_locale=cn) | `86d14f3c905b10bc7bf78b220b040bfe18d914b6d56136f84b3c5a06fbab3f90` | `bf5f81f886ea7c4bdf8c786006d4de9f41113e6abf1a7458a6d18a44459d5e4a` | 名称及效果语义对齐 |

官方详情页显示简体字版本。网页是在线证据，本仓库没有保存或复制页面正文；链接及页面内容可能随时间变化。

## 未解决项与后续

- C1结构化报告仍将这3张卡的名称/正文标为`candidate`、语义审阅标为`not_reviewed`，原因仍是`candidate_not_semantically_reviewed`；本次人工记录不提升C1状态。报告总状态仍为`qualified=false`。
- 本次只审阅`zh-CN`候选；对应`zh-SC`候选未审阅，且其语言类别仍为`und`。中文别名和本地化archetype映射仍未知。
- 来源使用依据及再分发状态仍为`unknown`；上游树中缺少可确认许可依据，候选继续仅限本地调查。没有把官方页面可访问性解释为第三方数据库授权。
- 截至本批交接时，L1仍开放：当时其余36张卡的zh-CN候选、全部39张zh-SC候选，以及别名、类别和权利依据均需分批处理。后续批次先沿用同一字段哈希绑定和逐卡官方页面对照；若发现差异，记录复现材料并保持原状态，待独立审阅后再决定是否更新正式数据。

与C1离线字段报告的关系见[语言核验说明](../../LANGUAGE_REVIEW.md)及[验证记录](../../TESTING.md#2026-11-02-l1首批3卡人工来源与语义对照)。
