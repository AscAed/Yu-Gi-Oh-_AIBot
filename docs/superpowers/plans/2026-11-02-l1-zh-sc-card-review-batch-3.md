# L1 zh-SC候选：第三批3卡人工对照

日期：2026-11-02。按第二批之后冻结报告顺序，复核卡号24299458、25538345和25542642的zh-SC名称及正文候选，并与Konami官方OCG简体中文详情页对照。

## 输入与结果

- 冻结C1报告SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`；zh-SC CDB SHA-256=`5382e8dcdfaae6c582533d70670e34fb4390b9ef20eccbd5cae338327ae517d4`。
- 以下名称和正文哈希遵循[`language_review.py`](../../../python/ygo_data/language_review.py)的`_canonical_hash`，与报告记录和冻结CDB逐项相符。

| 卡号 | 官方简中页面 | zh-SC候选名称 SHA-256 | zh-SC候选正文 SHA-256 | 人工对照结果 |
|---:|---|---|---|---|
| 24299458 | [禁忌的一滴](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=15299&ope=2&request_locale=cn) | `350e26a2f52a15f2df41cb68948c014523d01874744495684f59e15ef4b7a536` | `227ca4c413fc4efb7abafdc1b6e93e5f91c675594933224c4d8bbf456239faa5` | 候选名称与官方标题一致；送墓代价、对方连锁限制、选取数量以及攻击力减半和效果无效处理语义一致 |
| 25538345 | [魅影骑士团裂鳞甲](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=15482&ope=2&request_locale=cn) | `be51cbeb38661c0381ddeb24c2fe0b0fa7f4babb16d73313efb6a9541bfce24d` | `550cc89d2f46214e448a044ca777ee74817e31f75d259bc68cd933653f954265` | 候选名称与官方标题一致；舍弃手牌后送墓类别卡、类别卡从墓地除外后自身特召及离场除外的条件和处理语义一致；“魅影骑士团/魅影”类别称谓与官方一致 |
| 25542642 | [魅影雾剑](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=12205&ope=2&request_locale=cn) | `393894d6123db871cba38dfe0dd1a2d8dbb42e399c04092cb30f290672646f9f` | `1e8d1e5bf5575a123309e8bf1a6837f6d79ee023c3c28be68f8dc1e32b073291` | 候选名称与官方标题一致；对象怪兽攻击/效果限制、离场后破坏以及墓地特召和离场除外的条件和处理语义一致；“魅影骑士团”类别称谓与官方一致 |

## 状态与后续

- 本批三张在C1报告中仍为`not_reviewed`，名称和正文状态仍为`candidate`；`language_category=und`、类别状态`unknown`，报告总状态仍为`qualified=false`。人工对照证据不回写结构化状态。
- zh-SC目前累计9/39张完成人工对照。39卡样本中38张有候选记录，卡号44088353字段缺失；其余29张有候选值但未人工审阅。全部别名/本地化类别映射、语言类别资格和来源使用及再分发依据仍开放。
- 下批继续按冻结报告顺序复核卡号26692769、28781003和29301450；若遇字段缺失或页面不可得，记录缺口并保持未知。

此前盘点与结果见[zh-SC批次1](2026-11-02-l1-zh-sc-card-review-batch-1.md)、[zh-SC批次2](2026-11-02-l1-zh-sc-card-review-batch-2.md)；zh-CN对照见[批次1](2026-11-02-l1-card-review-batch-1.md)至[批次13](2026-11-02-l1-card-review-batch-13.md)。
