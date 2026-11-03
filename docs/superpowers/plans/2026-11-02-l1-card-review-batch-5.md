# L1中文数据人工复核：第五批3卡

日期：2026-11-02。复核固定mycard `zh-CN` 候选源中的幻影骑士团 无声靴、灵王的波动和欢聚友伴·茸茸长尾山雀，并与Konami官方OCG简体中文卡片详情页逐项对照。本批覆盖主题特召/检索怪兽、手牌发动的无效陷阱及抽牌型手坑。

## 输入与结果

- 固定来源：`mycard-zh-CN-217ae165`，上游提交`217ae165c1886af2fc36b823fc08f9fc3ec13185`；zh-CN CDB SHA-256=`ff52f585de24a762a4e613ac37654b1a7fb15a58990c14f5eada85f28c3be152`。
- 冻结C1报告：`data/runtime/c1-language-review-offline-2026-10-28/language-review.json`，SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`。
- 字段哈希按[`language_review.py`](../../../python/ygo_data/language_review.py)的`_canonical_hash`计算：先将字段值序列化为紧凑UTF-8 JSON，再取SHA-256。复核时报告与CDB整体哈希相符，三张卡六个zh-CN字段哈希均可由冻结CDB重算复现。
- 对照卡名、卡种/召唤条件、发动条件、处理结果和限制。未复制官方页面正文；网页可能变化，字段哈希绑定本地冻结报告，不构成网页快照。

| 卡号 | 官方简中页面 | C1候选名称 SHA-256 | C1候选正文 SHA-256 | 人工对照结果 |
|---:|---|---|---|---|
| 36426778 | [魅影骑士团无声靴](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=12199&ope=2&request_locale=cn) | `1c8381873ae67b5eea6acb674ed8dd8585042b4009f4320a2b74cfe5b48a318e` | `ffc8758615258fca7405c27fe4ecc0d946e8ac83bc9478a052c8d5187601cb85` | 候选名“幻影骑士团 无声靴”不同于官方标题；手牌特殊召唤和墓地除外检索的步骤一致，但正文类别词`幻影骑士团/幻影`与官方`魅影骑士团/魅影`不同，映射未确认 |
| 40366667 | [灵主王之波动](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=20555&ope=2&request_locale=cn) | `c71d3c2f7277f0a759ac3517ecdac7e0878cd798320c78dc214b6077ad50e31a` | `92e332fa900fd06b0ac635e77412a0aa1f9f8de5bba8e293da4bcccb611e29e5` | 候选名“灵王的波动”不同于官方标题；从手牌发动条件、无效与有墓地陷阱时破坏、后续属性发动限制一致 |
| 42141493 | [多多迷宝・软绵雀精](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=20500&ope=2&request_locale=cn) | `9ea9d0562284217757edd34c614d970b5d5c41e1a77ecaf1485d0ed4124cc90d` | `8426d58bacc0d3bff96b3e42d51787635361814603974d98373b77b4beef6861` | 候选名“欢聚友伴·茸茸长尾山雀”不同于官方标题；手牌发动条件、对方从卡组/额外卡组特召后的抽牌及结束阶段手牌处理一致，但文本内类别词`欢聚友伴`与官方`多多迷宝`不同，映射未确认 |

## 状态与后续

- 本批人工对照补充离线证据；C1报告仍将三张卡名称/正文标为`candidate`、语义审阅标为`not_reviewed`，总状态保持`qualified=false`。不修改候选源、C1报告或工作台行为。
- 对“幻影/魅影”及“欢聚友伴/多多迷宝”的名称和类别差异不推断为正式别名或已验证的本地化映射。别名、archetype字段、使用依据和再分发状态继续保持未知；`zh-SC`类别仍为`und`且未审阅。
- 截至第五批交接时，五批累计完成15/39张zh-CN候选的名称与效果对照；其余24张zh-CN、全部zh-SC和权利依据仍开放。后续批次继续使用字段哈希绑定及官方来源逐卡对照，名称、类别和效果分别记录，不提升未验证字段。

此前批次见[批次1](2026-11-02-l1-card-review-batch-1.md)、[批次2](2026-11-02-l1-card-review-batch-2.md)、[批次3](2026-11-02-l1-card-review-batch-3.md)和[批次4](2026-11-02-l1-card-review-batch-4.md)；字段合同见[语言核验说明](../../LANGUAGE_REVIEW.md)，本批记录见[验证日志](../../TESTING.md#2026-11-02-l1第五批3卡人工来源与语义对照)。
