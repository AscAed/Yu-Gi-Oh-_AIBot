# L1 zh-SC候选：第九批3卡人工对照

日期：2026-11-02。按冻结报告顺序复核卡号65192027、65741786和77675029的zh-SC名称及正文候选，并与Konami官方OCG简体中文详情页对照。卡号77675029首轮此前只找到日文页；本次直接重查其官方简中详情页后完成对照。

## 输入与结果

- 冻结C1报告SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`；zh-SC CDB SHA-256=`5382e8dcdfaae6c582533d70670e34fb4390b9ef20eccbd5cae338327ae517d4`。
- 名称和正文哈希遵循[`language_review.py`](../../../python/ygo_data/language_review.py)的`_canonical_hash`；报告中的六个候选字段哈希均与只读打开的冻结CDB逐项匹配。
- 对照卡名、召唤素材、条件、处理、次数限制及类别词。官方页面只作人工比对；不复制页面正文，不修改候选源、C1报告或语言记录。

| 卡号 | 官方简中页面 | zh-SC候选名称 SHA-256 | zh-SC候选正文 SHA-256 | 人工对照结果 |
|---:|---|---|---|---|
| 65192027 | [暗黑武装龙](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=7421&ope=2&request_locale=cn) | `04fc9ab64246c7c46b66600cef6064cc779ae4180aa73abe722e3296cc716bde` | `79044f224a8f203ac71e7f06843cc424789c56029759438df46391f5ebf2d1b6` | 候选标题与官方标题一致；不能通常召唤、墓地暗属性怪兽恰为3只时特殊召唤，以及除外墓地暗属性怪兽后取对象破坏场上卡的条件和处理语义一致。候选正文“可以场上的1张卡为对象发动”与官方“以场上的1张卡为对象可以发动”措辞/语序不同，保留为文本质量差异 |
| 65741786 | [I：P百变莱娜](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=14676&ope=2&request_locale=cn) | `dd1c545ac5f05e0b4d4c47cfb0e36f56e0da6de1d5cbebde9aa0fffe8cbb260a` | `778df63695872add39366ea32ad98813e49877485e38d08bb43743f9af38173c` | 候选标题与官方标题一致；非连接怪兽素材限制、对手主要阶段以此卡参与连接召唤的一回合一次效果，以及作为素材的连接怪兽不被对手效果破坏，条件和处理一致 |
| 77675029 | [驱魔姐妹・卡尔玛尔](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=22147&ope=2&request_locale=cn) | `e9104c3edccbd0b6bf3d3016e9783d97d5c199f36fa17adcdf7ef60959aae1f2` | `1d44a8e73ae7c34202e46bf421aacf84dab5dd6f00494b933c09a36ab689a897` | 候选标题与官方标题一致；等级4“驱魔姐妹”素材、超量召唤后结束阶段盖放相关魔陷、对手发动指定卡片类别时取除全部素材并改写效果的条件和处理一致；类别称谓与官方简中页一致 |

## 状态与后续

- 本批三张在C1报告中仍为`not_reviewed`，名称和正文状态仍为`candidate`；语言类别仍为`und`/`unknown`，报告总状态仍为`qualified=false`。人工对照证据不回写结构化状态。
- zh-SC累计完成26/38张有候选值记录的人工对照；39卡样本中卡号44088353在此源缺少字段，另12张有候选值但未人工审阅。别名/本地化映射、语言类别资格和来源使用及再分发依据仍开放。
- 本次补充发现卡号77675029存在官方简中页面。zh-CN候选对照见[对应批次9修订](2026-11-02-l1-card-review-batch-9.md)：其中文标题及类别称谓不同，映射未确认。
- 下批按冻结报告顺序复核卡号78449284、81439173和83566725；缺失或无官方简中页面时将相应结论保持未知。

此前盘点与结果见[zh-SC批次1](2026-11-02-l1-zh-sc-card-review-batch-1.md)至[zh-SC批次8](2026-11-02-l1-zh-sc-card-review-batch-8.md)；zh-CN对照见[批次1](2026-11-02-l1-card-review-batch-1.md)至[批次13](2026-11-02-l1-card-review-batch-13.md)。
