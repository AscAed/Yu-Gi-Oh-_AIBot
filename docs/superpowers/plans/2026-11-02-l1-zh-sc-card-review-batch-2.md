# L1 zh-SC候选：第二批3卡人工对照

日期：2026-11-02。按首批之后冻结报告顺序，复核卡号14558127、16195942和23434538的zh-SC名称及正文候选，并与Konami官方OCG简体中文详情页对照。

## 输入与结果

- 冻结C1报告SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`；zh-SC CDB SHA-256=`5382e8dcdfaae6c582533d70670e34fb4390b9ef20eccbd5cae338327ae517d4`。
- 以下名称和正文哈希遵循[`language_review.py`](../../../python/ygo_data/language_review.py)的`_canonical_hash`，与报告记录和冻结CDB逐项相符。

| 卡号 | 官方简中页面 | zh-SC候选名称 SHA-256 | zh-SC候选正文 SHA-256 | 人工对照结果 |
|---:|---|---|---|---|
| 14558127 | [灰流丽](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=12950&ope=2&request_locale=cn) | `cd9c67cc7b690ac646232b535bfa5d90cca2b81435d4d7d889350fc659515d79` | `5ac5bcda748a557a81ea75b6d93af0bffc863554d8ecfccdb28a28c3692b0e76` | 候选名称与官方标题一致；手牌送墓的发动代价、对应的三类效果和无效处理语义一致 |
| 16195942 | [暗反叛超量龙](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=11385&ope=2&request_locale=cn) | `6b3bb800f08d32fce44bfc2b6658d364d3a59c55a2295ec37b16e224e2f4a566` | `2f11ca2cea03d07b2b1db711b699c54db7e9bb1c212d43b89e92a532727d28a1` | 候选名称与官方标题一致；2个素材的取除代价、对象怪兽攻击力减半及自身攻击力增加的处理语义一致 |
| 23434538 | [增殖的Z](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=9455&ope=2&request_locale=cn) | `1bd200fdfac562a242c05fc7e7ed4876d8e8d885f162124867bc710045b1f7e9` | `e18e47998c12f1c1e33dcae9dcdb69eb6fdec06c3958dd9fdd710a09a5921fb8` | 候选名称与官方标题一致；任一方回合从手牌送墓并在当回合对方每次特殊召唤后抽1张的处理语义一致 |

## 状态与后续

- 本批三张在C1报告中仍为`not_reviewed`，名称和正文状态仍为`candidate`；`language_category=und`、类别状态`unknown`，报告总状态仍为`qualified=false`。人工对照证据不回写结构化状态。
- zh-SC目前累计6/39张完成人工对照。39卡样本中38张有候选记录，卡号44088353字段缺失；其余32张有候选值但未人工审阅。全部别名/本地化类别映射、语言类别资格和来源使用及再分发依据仍开放。
- 下批继续按冻结报告顺序复核卡号24299458、25538345和25542642；若遇字段缺失或页面不可得，记录缺口并保持未知。

此前首批盘点与结果见[zh-SC批次1](2026-11-02-l1-zh-sc-card-review-batch-1.md)，zh-CN对照见[批次1](2026-11-02-l1-card-review-batch-1.md)至[批次13](2026-11-02-l1-card-review-batch-13.md)。
