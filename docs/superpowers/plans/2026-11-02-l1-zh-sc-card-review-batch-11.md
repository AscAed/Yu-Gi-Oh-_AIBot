# L1 zh-SC候选：第十一批3卡人工对照

日期：2026-11-02。按冻结报告顺序复核卡号85257384、88504133和88544390的zh-SC名称及正文候选，并与Konami官方OCG简体中文详情页对照。

## 输入与结果

- 冻结C1报告SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`；zh-SC CDB SHA-256=`5382e8dcdfaae6c582533d70670e34fb4390b9ef20eccbd5cae338327ae517d4`。
- 名称和正文哈希遵循[`language_review.py`](../../../python/ygo_data/language_review.py)的`_canonical_hash`；报告中的六个候选字段哈希均与只读打开的冻结CDB逐项匹配。
- 对照卡名、卡种、效果条件、处理、次数限制及类别称谓。官方页面仅用于人工比对；不复制页面正文，不修改候选源、C1报告或语言记录。

| 卡号 | 官方简中页面 | zh-SC候选名称 SHA-256 | zh-SC候选正文 SHA-256 | 人工对照结果 |
|---:|---|---|---|---|
| 85257384 | [魅影骑士团愤恨披幕](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=23022&ope=2&request_locale=cn) | `75ba878f10c819b7e19ef02d4f5bec1f1e29d07cac30ae83f3d3a68e71f49309` | `0e54a8b8d2994fe2ccc18a7292c48a870059df464e8b7488558cd316343e7f2f` | 候选标题与官方标题一致；同名回合限制、放置回合发动条件、陷阱怪兽化、改变攻击表示，以及墓地除外后进行暗属性超量召唤的条件和处理一致；类别称谓与官方一致 |
| 88504133 | [升阶魔法－魅影之力](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=15530&ope=2&request_locale=cn) | `631b5ce5369352589ee8bad37fc630cdc21601988a6dc799057b6cfead74f0cd` | `ca4511297c27f7dc0cc1e0d82607a5d398a8a64c65edab539741a6b9b914750e` | 候选标题与官方标题一致；主要阶段从墓地除外暗属性怪兽、按数量选择更高阶“魅影骑士团/急袭猛禽/超量龙”怪兽叠放召唤，以及本回合额外牌组召唤限制均一致 |
| 88544390 | [魅影骑士团脏胫甲](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=15481&ope=2&request_locale=cn) | `1872d067c19c78b7963c109d7bdfc571daca55d58db354156cd22a8c135cfaa4` | `75f6ff27024cd466c230e05dd5dab6b4beb056154144d8f08ed5a3fd72ca5ad9` | 候选标题与官方标题一致；类别怪兽特召后从手牌特召此卡并可升星、墓地除外后特召另一类别怪兽并可升星的条件和处理一致；类别称谓与官方一致 |

## 状态与后续

- 本批三张在C1报告中仍为`not_reviewed`，名称和正文状态仍为`candidate`；语言类别仍为`und`/`unknown`，报告总状态仍为`qualified=false`。人工对照证据不回写结构化状态。
- zh-SC累计完成32/38张有候选值记录的人工对照；39卡样本中卡号44088353在此源缺少字段，另6张有候选值但未人工审阅。别名/本地化映射、语言类别资格及来源使用和再分发依据仍开放。
- 下批按冻结报告顺序复核卡号90091224、90432163和91279700；对最后一张先核对官方简中页面是否可用，若仅有日文依据则保持中文名称和类别映射未知。

此前盘点与结果见[zh-SC批次1](2026-11-02-l1-zh-sc-card-review-batch-1.md)至[zh-SC批次10](2026-11-02-l1-zh-sc-card-review-batch-10.md)；zh-CN对照见[批次1](2026-11-02-l1-card-review-batch-1.md)至[批次13](2026-11-02-l1-card-review-batch-13.md)。
