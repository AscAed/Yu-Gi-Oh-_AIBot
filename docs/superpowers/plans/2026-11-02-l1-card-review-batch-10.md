# L1中文数据人工复核：第十批3卡

日期：2026-11-02。按前九批之后冻结报告中的未审阅候选顺序，复核幻影骑士团 敌意死镰、愚蠢的埋葬和幻影骑士团 厄运钢甲靴，并与Konami官方OCG简体中文详情页逐项对照。本批三张均找到官方简中详情页。

## 输入与结果

- 固定来源：`mycard-zh-CN-217ae165`，上游提交`217ae165c1886af2fc36b823fc08f9fc3ec13185`；冻结zh-CN CDB SHA-256=`ff52f585de24a762a4e613ac37654b1a7fb15a58990c14f5eada85f28c3be152`。
- 冻结C1报告：`data/runtime/c1-language-review-offline-2026-10-28/language-review.json`，SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`。本次重新计算的报告和CDB哈希与冻结值相符；表中六个候选字段哈希均可由冻结CDB重算复现。
- 字段哈希遵循[`language_review.py`](../../../python/ygo_data/language_review.py)的`_canonical_hash`：将字段值序列化为紧凑UTF-8 JSON后取SHA-256，不是直接对CDB列原始字节求哈希。
- 对照标题、卡种或召唤素材、效果条件、处理、次数限制和类别称谓。未复制官方页面正文；页面可能变化。本记录不修改候选源、C1报告或工作台行为。

| 卡号 | 官方简中页面 | zh-CN候选名称 SHA-256 | zh-CN候选正文 SHA-256 | 人工对照结果 |
|---:|---|---|---|---|
| 78449284 | [魅影骑士团凶恶之镰](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=22986&ope=2&request_locale=cn) | `1a03f3c2b5b19cda42723767a11e9ec29474344b7560d4f326a962c28fe2df76` | `e5451a4ba571c5d67448a24dbd53b5459569b316206de0a2c9c04ef6d9157f5f` | 候选标题“幻影骑士团 敌意死镰”与官方标题不同；暗属性等级3素材、取除后从牌组特召、超量召唤“超量龙”时检索升阶魔法、被破坏后回收除外卡的条件与处理一致；候选正文“幻影骑士团”与官方“魅影骑士团”类别称谓不同，映射未确认 |
| 81439173 | [愚蠢埋葬](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=5236&ope=2&request_locale=cn) | `b897c98a938c0cb04c002197fdcc8cc8b0db31465a0388c6fbd93e21c51a2638` | `00ea94f68b2bb1c6ad8d5f41a9f5a102274312c724874e31c864227fc9c93d3f` | 候选标题“愚蠢的埋葬”多“的”字；从牌组将1只怪兽送至墓地的效果一致 |
| 83566725 | [魅影骑士团末日护胫](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=22968&ope=2&request_locale=cn) | `6c6a613b0ff19fd08644ecfb7d156aa737a0433c0f66b3298bfbd96f6b2e5808` | `450902c90f5ac7ec680ad0c884b4c2f3faf121ce0dc91c5286dcfd03f5843287` | 候选标题“幻影骑士团 厄运钢甲靴”与官方标题不同；无怪兽时从手牌特召、召唤后盖放类别魔陷、墓地除外后提升最多2只暗属性3星/3阶怪兽等级或阶级的条件和处理一致；候选正文“幻影骑士团”与官方“魅影骑士团”类别称谓不同，映射未确认 |

## 状态与后续

- 本批三张在C1报告中仍为`not_reviewed`，名称和正文状态仍为`candidate`；报告总状态继续为`qualified=false`。人工对照未修改报告或候选材料。
- 截至第十批，累计对照30/39张zh-CN候选。其中29张有官方简中详情页，1张目前仅找到官方日文详情页（人偶之锤）。在29张可直接与简中页面比较的卡中，20张候选标题不同，14张正文类别称谓映射未确认。本批增加3个标题差异和2个正文类别称谓映射缺口；卡号77675029的官方简中页由后续同日复核补入统计。
- 其余9张zh-CN候选、全部zh-SC、别名/本地化类别映射及来源使用和再分发依据仍未通过。名称或类别差异不自动确认为别名或正式本地化；官方页面可访问也不证明第三方数据库获得授权。

此前批次见[批次1](2026-11-02-l1-card-review-batch-1.md)至[批次9](2026-11-02-l1-card-review-batch-9.md)；字段合同见[语言核验说明](../../LANGUAGE_REVIEW.md)，本批记录见[验证日志](../../TESTING.md#2026-11-02-l1第十批3卡人工来源与语义对照)。
