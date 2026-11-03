# L1 zh-SC候选：第七批3卡人工对照

日期：2026-11-02。按第六批之后冻结报告顺序，复核卡号52159691、58699500和62104532的zh-SC名称及正文候选，并与Konami官方OCG简体中文详情页对照。

## 输入与结果

- 冻结C1报告SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`；zh-SC CDB SHA-256=`5382e8dcdfaae6c582533d70670e34fb4390b9ef20eccbd5cae338327ae517d4`。
- 以下名称和正文哈希遵循[`language_review.py`](../../../python/ygo_data/language_review.py)的`_canonical_hash`，与报告记录和冻结CDB逐项相符。

| 卡号 | 官方简中页面 | zh-SC候选名称 SHA-256 | zh-SC候选正文 SHA-256 | 人工对照结果 |
|---:|---|---|---|---|
| 52159691 | [急袭者之翼](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=15480&ope=2&request_locale=cn) | `74dc91795a06b30dfe057e3ca0896a669e21a8b26a9e24200e204b0a710966af` | `778413fedc1db7cea7782826b742b673fadd153aa27231e28465455e63d6cdc3` | 候选名称与官方标题一致；规则类别标记、从手牌/墓地特召并在离场时除外、赋予暗属性超量怪兽不成为对方效果对象的处理语义一致 |
| 58699500 | [彼岸之黑天使 凯鲁比尼](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=13506&ope=2&request_locale=cn) | `04c5c02bbe5d751cea43d7311698fca4fc22f689af47e7c4289df416cadfe8fe` | `29bdb09f1279711d7925b01039be90414f57f39ee3a0ef27257e11fb68f9b3f8` | 候选名称与官方标题一致；连接素材、连接端保护、代替破坏、送墓等级3怪兽并提升彼岸怪兽数值的条件和处理语义一致 |
| 62104532 | [升阶魔法－魅影骑士团镇魂曲](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=23006&ope=2&request_locale=cn) | `255b1e49ad2a360a36689b067812cd228d980a92752019744ac1a4f4713711af` | `d5333eba5ede7c0a75c5c2b469794fc4a739de66355ced450fe6cb3bd264b87b` | 候选名称与官方标题一致；墓地/除外对象复活并无效、之后叠放高1阶类别或超量龙怪兽的条件和处理语义一致；类别称谓与官方一致 |

## 状态与后续

- 本批三张在C1报告中仍为`not_reviewed`，名称和正文状态仍为`candidate`；`language_category=und`、类别状态`unknown`，报告总状态仍为`qualified=false`。人工对照证据不回写结构化状态。
- zh-SC目前累计20/39张有候选值的卡完成人工对照。39卡样本中38张有候选记录，44088353字段缺失；其余18张有候选值但未人工审阅。全部别名/本地化类别映射、语言类别资格和来源使用及再分发依据仍开放。
- 下批继续按冻结报告顺序复核卡号62709239、63821877和64276752；缺值或官方页面不可得时保持未知。

此前盘点与结果见[zh-SC批次1](2026-11-02-l1-zh-sc-card-review-batch-1.md)至[zh-SC批次6](2026-11-02-l1-zh-sc-card-review-batch-6.md)；zh-CN对照见[批次1](2026-11-02-l1-card-review-batch-1.md)至[批次13](2026-11-02-l1-card-review-batch-13.md)。
