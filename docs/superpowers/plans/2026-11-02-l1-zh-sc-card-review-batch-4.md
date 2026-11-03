# L1 zh-SC候选：第四批3卡人工对照

日期：2026-11-02。按第三批之后冻结报告顺序，复核卡号26692769、28781003和29301450的zh-SC名称及正文候选，并与Konami官方OCG简体中文详情页对照。

## 输入与结果

- 冻结C1报告SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`；zh-SC CDB SHA-256=`5382e8dcdfaae6c582533d70670e34fb4390b9ef20eccbd5cae338327ae517d4`。
- 以下名称和正文哈希遵循[`language_review.py`](../../../python/ygo_data/language_review.py)的`_canonical_hash`，与报告记录和冻结CDB逐项相符。

| 卡号 | 官方简中页面 | zh-SC候选名称 SHA-256 | zh-SC候选正文 SHA-256 | 人工对照结果 |
|---:|---|---|---|---|
| 26692769 | [魅影骑士团锈蚀月刃斧](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=14054&ope=2&request_locale=cn) | `569d96da0a5450b0376d8028910972132eb56a7fb9a385d0dce7774b508ee2e8` | `c24d554868f3236c6f6b6f4b9161707baa0e4e367d6379043b67fcfce900d9cc` | 候选名称与官方标题一致；从牌组送墓并放置魔陷、连接端有暗属性超量怪兽特召后破坏场上卡的条件和处理语义一致；“魅影骑士团/魅影”类别词与官方一致 |
| 28781003 | [急袭者骑士](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=15519&ope=2&request_locale=cn) | `1d5b6193d62a3d95e59bfe4ce1da4d5a1276fca4dbd5da2b8166f7959ba2d735` | `b4eeb760d6ea2d1f30e6c6e8107ccd38a29ed5e18fa1656e9179abeb58eb5746` | 候选名称与官方标题一致；规则类别标记、取除素材后升或降1阶叠放特召及下个对手结束阶段破坏的条件和处理语义一致 |
| 29301450 | [S：P小夜骑士](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=19188&ope=2&request_locale=cn) | `17168a0574b2c1dd76f6f43c0ce2fbe2b8add170aafb2ae5b684c268cf4f6963` | `9125981f11049a70413e78118847d0634d0890fe2a7529ec5233b7d62d86348d` | 候选名称与官方标题一致；指定素材连接召唤后的除外及直接攻击限制、对方效果发动时暂时除外两只表侧怪兽的条件和处理语义一致 |

## 状态与后续

- 本批三张在C1报告中仍为`not_reviewed`，名称和正文状态仍为`candidate`；`language_category=und`、类别状态`unknown`，报告总状态仍为`qualified=false`。人工对照证据不回写结构化状态。
- zh-SC目前累计12/39张完成人工对照。39卡样本中38张有候选记录，卡号44088353字段缺失；其余26张有候选值但未人工审阅。全部别名/本地化类别映射、语言类别资格和来源使用及再分发依据仍开放。
- 下批继续按冻结报告顺序复核卡号32807846、36426778和40366667；若遇字段缺失或页面不可得，记录缺口并保持未知。

此前盘点与结果见[zh-SC批次1](2026-11-02-l1-zh-sc-card-review-batch-1.md)至[zh-SC批次3](2026-11-02-l1-zh-sc-card-review-batch-3.md)；zh-CN对照见[批次1](2026-11-02-l1-card-review-batch-1.md)至[批次13](2026-11-02-l1-card-review-batch-13.md)。
