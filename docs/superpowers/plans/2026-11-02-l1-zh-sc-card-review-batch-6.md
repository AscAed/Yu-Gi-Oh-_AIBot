# L1 zh-SC候选：第六批3卡（含1项源缺失）

日期：2026-11-02。按第五批之后冻结报告顺序，核对卡号42141493、44088353和46072770。两张存在zh-SC字段候选的卡与Konami官方OCG简体中文详情页对照；44088353在冻结zh-SC CDB中缺少记录，本批不为缺失字段推断名称或正文。

## 输入与结果

- 冻结C1报告SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`；zh-SC CDB SHA-256=`5382e8dcdfaae6c582533d70670e34fb4390b9ef20eccbd5cae338327ae517d4`。
- 两张有候选字段卡的名称和正文哈希遵循[`language_review.py`](../../../python/ygo_data/language_review.py)的`_canonical_hash`，与报告记录和冻结CDB逐项相符。

| 卡号 | 官方简中页面 | zh-SC候选名称 SHA-256 | zh-SC候选正文 SHA-256 | 人工对照结果 |
|---:|---|---|---|---|
| 42141493 | [多多迷宝・软绵雀精](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=20500&ope=2&request_locale=cn) | `a512df16d7f134bf2de4d5e066d307c04823f721d38e1522897a4e8e01226d56` | `95bbe80ff094482a00beeab69fc83abd6c6510e74f4d9004566c716908f3239b` | 候选名称与官方标题一致；空场时从手牌发动、对方从牌组/额外牌组特召后的抽牌和结束阶段手牌处理语义一致 |
| 44088353 | 无zh-SC页面可供对照 | — | — | 冻结zh-SC CDB无此卡记录；C1报告名称和正文均为`missing`/`candidate_value_absent`。不计为已审阅候选，也不推断本地化名称 |
| 46072770 | [魅影骑士团衰朽斗篷](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=22967&ope=2&request_locale=cn) | `917d8384c19b2d146f335c5dad27959df01012bf4b7bb1d0a8bd6fea17a55729` | `5eb9164c482e0b375cc21957e160214d4f347d5c167ec7c05c53257dd02a39a6` | 候选名称与官方标题一致；展示类别卡后特召、召唤时检索类别怪兽、墓地除外后改变超量素材适用等级的条件和处理语义一致；“魅影骑士团”类别称谓与官方一致 |

## 状态与后续

- 两张有候选值的卡在C1报告中仍为`not_reviewed`，名称和正文状态仍为`candidate`；`language_category=und`、类别状态`unknown`，报告总状态仍为`qualified=false`。44088353对应字段仍为`missing`。人工对照不回写结构化状态。
- zh-SC目前累计17/39张有候选字段的卡完成人工对照。39卡样本中38张有候选记录，44088353字段缺失；其余21张有候选值但未人工审阅。全部别名/本地化类别映射、语言类别资格和来源使用及再分发依据仍开放。
- 下批继续按冻结报告顺序复核卡号52159691、58699500和62104532；缺值或页面不可得时保持未知。

此前盘点与结果见[zh-SC批次1](2026-11-02-l1-zh-sc-card-review-batch-1.md)至[zh-SC批次5](2026-11-02-l1-zh-sc-card-review-batch-5.md)；zh-CN对照见[批次1](2026-11-02-l1-card-review-batch-1.md)至[批次13](2026-11-02-l1-card-review-batch-13.md)。
