# L1 zh-SC候选：第五批3卡人工对照

日期：2026-11-02。按第四批之后冻结报告顺序，复核卡号32807846、36426778和40366667的zh-SC名称及正文候选，并与Konami官方OCG简体中文详情页对照。

## 输入与结果

- 冻结C1报告SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`；zh-SC CDB SHA-256=`5382e8dcdfaae6c582533d70670e34fb4390b9ef20eccbd5cae338327ae517d4`。
- 以下名称和正文哈希遵循[`language_review.py`](../../../python/ygo_data/language_review.py)的`_canonical_hash`，与报告记录和冻结CDB逐项相符。

| 卡号 | 官方简中页面 | zh-SC候选名称 SHA-256 | zh-SC候选正文 SHA-256 | 人工对照结果 |
|---:|---|---|---|---|
| 32807846 | [增援](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=5328&ope=2&request_locale=cn) | `ebf8a3db48cd1984d4d50632b9bc2d663b1394d2ed9b8c73940054fa479cc897` | `b389abea0e284bb93ae090cbfbcaeab9562d3de480b42ef02db4bb10d4297635` | 候选名称与官方标题一致；从牌组将等级4以下战士族怪兽加入手牌的条件和处理语义一致 |
| 36426778 | [魅影骑士团无声靴](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=12199&ope=2&request_locale=cn) | `fae878c700b9f3662fe7cbbdc391f905671677677f61fccd916f8fb50eaa54f3` | `df56480edc406c8d01d627e04596f2aebbe14ef25f6a7d0dd715b3d01539cfa3` | 候选名称与官方标题一致；类别怪兽存在时从手牌特召、墓地除外后检索类别魔陷的条件和处理语义一致 |
| 40366667 | [灵主王之波动](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=20555&ope=2&request_locale=cn) | `a4bd309154ef4d20597d569615d1a3961484973638f01c34913a6bb7149d1c8b` | `ac25aa3a3afcf234c14f8b8bcfbf22d29d099c649fd617c7518b4c0108c48fb0` | 候选名称与官方标题一致；对手场上有卡时手牌发动、无效特召效果、有墓地陷阱时破坏及后续光/地/风属性效果限制的条件和处理语义一致 |

## 状态与后续

- 本批三张在C1报告中仍为`not_reviewed`，名称和正文状态仍为`candidate`；`language_category=und`、类别状态`unknown`，报告总状态仍为`qualified=false`。人工对照证据不回写结构化状态。
- zh-SC目前累计15/39张完成人工对照。39卡样本中38张有候选记录，卡号44088353字段缺失；其余23张有候选值但未人工审阅。全部别名/本地化类别映射、语言类别资格和来源使用及再分发依据仍开放。
- 下批继续按冻结报告顺序复核卡号42141493、44088353和46072770；卡号44088353缺少zh-SC字段，需记录为缺失并继续审阅其他候选。

此前盘点与结果见[zh-SC批次1](2026-11-02-l1-zh-sc-card-review-batch-1.md)至[zh-SC批次4](2026-11-02-l1-zh-sc-card-review-batch-4.md)；zh-CN对照见[批次1](2026-11-02-l1-card-review-batch-1.md)至[批次13](2026-11-02-l1-card-review-batch-13.md)。
