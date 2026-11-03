# L1 zh-SC候选：第十二批3卡人工对照

日期：2026-11-02。按冻结报告顺序复核卡号90091224、90432163和91279700的zh-SC名称及正文候选，并与Konami官方OCG简体中文详情页对照。

## 输入与结果

- 冻结C1报告SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`；zh-SC CDB SHA-256=`5382e8dcdfaae6c582533d70670e34fb4390b9ef20eccbd5cae338327ae517d4`。
- 名称和正文哈希遵循[`language_review.py`](../../../python/ygo_data/language_review.py)的`_canonical_hash`；报告中的六个候选字段哈希均与只读打开的冻结CDB逐项匹配。
- 对照卡名、卡种、效果条件、处理、次数限制和类别称谓。官方页面仅用于人工比对；不复制页面正文，不修改候选源、C1报告或语言记录。

| 卡号 | 官方简中页面 | zh-SC候选名称 SHA-256 | zh-SC候选正文 SHA-256 | 人工对照结果 |
|---:|---|---|---|---|
| 90091224 | [四天之龙 暗反叛超量龙](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=22730&ope=2&request_locale=cn) | `109ae543b941b4a2a2811dca08695990c41ec590c15788cb42e81fd51f933dba` | `2193380fcef2a50c1910589626e219eb0e81c1abb7c8ff4e1fec3dc89ad0e8a8` | 候选标题与官方标题一致；规则上视为“魅影骑士团”卡、特殊召唤时等量取对象破坏、对手发动效果后叠放暗属性4阶超量怪兽及各效果每回合使用限制均一致；类别称谓一致 |
| 90432163 | [魅影骑士团沾尘袍](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=12198&ope=2&request_locale=cn) | `561e3ded8fc115aa7633cb31a0d82374ef0f02bd344c1bb0de4e457d055e3aeb` | `e9f5b1d2a189c1500a2f157847c6df485d55e2f384223f60d1258571ec725fff` | 候选标题与官方标题一致；攻击表示下以暗属性怪兽为对象、转守备并提升攻击/守备、墓地除外后检索其他“魅影骑士团”卡的条件、处理及次数限制一致；类别称谓一致 |
| 91279700 | [邪蚀俄菲翁](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=10006&ope=2&request_locale=cn) | `f8cc0a402cbb266ccee712b5a7dead7611366119d7706411a7f0d89ee808075e` | `55440b565d2a1e9196b0e21981ed0915b6f525336a3e74188df2b375e4b959a3` | 候选标题“邪蚀・俄菲翁”与官方“邪蚀俄菲翁”仅有间隔符差异；全角数字/符号格式不同，素材、特殊召唤限制及取除素材检索效果的语义一致；“邪蚀”和“侵略的”称谓与官方一致 |

## 状态与后续

- 本批三张在C1报告中仍为`not_reviewed`，名称和正文状态仍为`candidate`；语言类别仍为`und`/`unknown`，报告总状态仍为`qualified=false`。人工对照证据不回写结构化状态。
- zh-SC累计完成35/38张有候选值记录的人工对照；39卡样本中卡号44088353在此源缺少字段，另3张候选值未人工审阅。
- 下批按冻结报告顺序复核卡号94145021、98431356和99745551。全部候选别名/本地化映射、语言类别资格及来源使用和再分发依据仍开放。

此前盘点与结果见[zh-SC批次1](2026-11-02-l1-zh-sc-card-review-batch-1.md)至[zh-SC批次11](2026-11-02-l1-zh-sc-card-review-batch-11.md)；zh-CN对照见[批次1](2026-11-02-l1-card-review-batch-1.md)至[批次13](2026-11-02-l1-card-review-batch-13.md)。
