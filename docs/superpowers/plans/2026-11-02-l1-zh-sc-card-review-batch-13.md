# L1 zh-SC候选：第十三批3卡人工对照

日期：2026-11-02。按冻结报告顺序复核卡号94145021、98431356和99745551的zh-SC名称及正文候选，并与Konami官方OCG简体中文详情页对照。本批完成zh-SC全部38张有候选值记录的人工对照。

## 输入与结果

- 冻结C1报告SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`；zh-SC CDB SHA-256=`5382e8dcdfaae6c582533d70670e34fb4390b9ef20eccbd5cae338327ae517d4`。
- 名称和正文哈希遵循[`language_review.py`](../../../python/ygo_data/language_review.py)的`_canonical_hash`；报告中的六个候选字段哈希均与只读打开的冻结CDB逐项匹配。
- 对照卡名、卡种、效果条件、处理、次数限制和类别称谓。官方页面仅用于人工比对；不复制页面正文，不修改候选源、C1报告或语言记录。

| 卡号 | 官方简中页面 | zh-SC候选名称 SHA-256 | zh-SC候选正文 SHA-256 | 人工对照结果 |
|---:|---|---|---|---|
| 94145021 | [抽牌小丑与封锁鸟](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=9279&ope=2&request_locale=cn) | `2757b1fb1a9641d2b8b0f52f392ee6ee689aff784768f48774cf66636fead4e9` | `b0ba5106de8dbecd1bec1abc5b5a5c35edc07e4f50062b973d988c5891c6adb1` | 候选标题与官方标题一致；对手在抽牌阶段外从牌组把卡加入手牌时从手牌送墓、限制双方当回合从牌组加入手牌的条件和处理一致 |
| 98431356 | [魅影翼](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=12207&ope=2&request_locale=cn) | `f5b862bf5047aec9e85ccce8db604a71daea76061d34e10e56c0de29e7329bad` | `66ca977a0b35ccd646315bd650cda5c1f5a844329d138213fb8fb0fc73ae73f2` | 候选标题与官方标题一致；提升表侧怪兽攻击力并提供一次战斗/效果破坏保护、墓地除外后特召类别怪兽且离场除外的条件和处理一致；“魅影骑士团”称谓与官方一致 |
| 99745551 | [未界域之土龙](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=14070&ope=2&request_locale=cn) | `bd3fad62dc7b02d314919732ab45c92d6fd26a323e14c6b27ed2ec3d8659663d` | `04439b8ea10e353994fe49cc45289e8844248382e7ff95c19b13f02e00f79879` | 候选标题与官方标题一致；公开手牌后由对手随机选弃、弃掉同名以外的卡后从手牌特召并抽卡，以及此卡从手牌被弃后特召的条件和处理一致 |

## 状态与后续

- 本批三张在C1报告中仍为`not_reviewed`，名称和正文状态仍为`candidate`；语言类别仍为`und`/`unknown`，报告总状态仍为`qualified=false`。人工对照证据不回写结构化状态。
- zh-SC全部38张有候选值记录均已人工对照；39卡样本中卡号44088353在此源缺少字段。名称/类别映射、语言类别资格及来源使用和再分发依据仍开放，因此本批完成候选对照不等于L1或正式中文数据资格完成。
- 下一步应依据复盘选择一个独立小批，继续处理差异项的别名/本地化证据、语言分类或来源权利证据；不把本批结果提升为真实分析或部署资格。

此前盘点与结果见[zh-SC批次1](2026-11-02-l1-zh-sc-card-review-batch-1.md)至[zh-SC批次12](2026-11-02-l1-zh-sc-card-review-batch-12.md)；zh-CN对照见[批次1](2026-11-02-l1-card-review-batch-1.md)至[批次13](2026-11-02-l1-card-review-batch-13.md)。
