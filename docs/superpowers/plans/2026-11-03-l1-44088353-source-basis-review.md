# L1 人偶之锤（44088353）来源与使用依据复核

日期：2026-11-03。只读核验单卡来源、语言字段和使用/再分发依据；不修改CDB候选值、C1报告、卡片状态或工作台行为。

## 证据与结论

| 项目 | 证据 | 结论 |
|---|---|---|
| 官方卡号和日文收录 | [Konami官方OCG卡片页](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=23148&ope=2&request_locale=ja)显示卡号对应日文名“ドールハンマー”，收录编号`LPG2-JP008`，日期为2026-07-25。本地归档`data/runtime/tournament-2026/reselection/releases/44088353.html`的SHA-256为`96b9414eaa30d2aecd1fed2d2d0aa96136d853d8615729b31b78123a2afc76a7`，与`configs/tournament-2026.source.json`记录一致。 | 支持当前OCG日文卡号和日文收录日期；不证明中文标题、中文正文或第三方数据库的使用权。 |
| 官方简中卡页 | [同卡号的Konami简体中文查询](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=23148&ope=2&request_locale=cn)于本次复核返回“Card information not found”；2026-11-02 zh-CN人工对照记录也观察到相同结果。 | 当前没有可用的官方简中页面对照中文候选；不据此推断没有简中印刷或译文。 |
| zh-CN候选与C1状态 | 冻结C1报告SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`。`mycard-zh-CN-217ae165`记录名字段哈希`baa089fba0bf15400fcaa8dddff76e6d7e1c33a03f058d1342986281f1049ba2`、正文哈希`91b80347dce11e1d8377719706c3ca43f920fe424da113fc652a80aedb3f98c3`；名称和正文状态均为`candidate`，语义审阅为`not_reviewed`，语言类别为`zh-Hans`/`candidate`。 | 不把候选名“人偶之锤”或正文提升为官方中文翻译/正式数据。 |
| 上游与使用依据 | 冻结源标识对应`mycard/ygopro-database`上游提交[`217ae165c1886af2fc36b823fc08f9fc3ec13185`](https://github.com/mycard/ygopro-database/commit/217ae165c1886af2fc36b823fc08f9fc3ec13185)，该提交变更`locales/zh-CN/cards.cdb`和`strings.conf`。[上游仓库根目录](https://github.com/mycard/ygopro-database)当前README将数据库描述为测试用途；根目录文件列表未显示许可文件。 | 找到候选来源链，但没有发现覆盖本项目使用和再分发的许可/书面授权证据。公开可访问和“用于测试”的说明都不等于授予再分发权。 |

`configs/tournament-2026.source.json`只把官方日文收录作为OCG发布日期及当前CDB卡号的依据，不是zh-CN字段来源或授权凭证。冻结C1对zh-CN的`usage_basis.status`和`redistribution`仍为`unknown`；别名和类别映射也仍为`unknown`。zh-SC缺少44088353记录，不从日文资料补造简中/繁中字段。

因此本批没有改变任何结构化状态。要评估有限中文字段资格，仍需可核验的中文语义依据和覆盖数据库字段用途/再分发的明确权利依据；在此之前候选仅供受限离线研究，不作为正式中文检索、自动选择或可分发数据。

本次只读核验结果也见[本机验证记录](../../TESTING.md#2026-11-03-l1-44088353来源与使用依据复核)、[语言字段核验说明](../../LANGUAGE_REVIEW.md)和[旧批次6人工对照](2026-11-02-l1-card-review-batch-6.md)。
