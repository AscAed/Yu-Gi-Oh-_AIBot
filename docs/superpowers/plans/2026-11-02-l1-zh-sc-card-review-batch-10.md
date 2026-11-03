# L1 zh-SC候选：第十批3卡人工对照

日期：2026-11-02。按冻结报告中未审阅候选顺序，复核卡号78449284、81439173和83566725的zh-SC名称及正文候选，并与Konami官方OCG简体中文详情页对照。

## 输入与结果

- 冻结C1报告SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`；zh-SC CDB SHA-256=`5382e8dcdfaae6c582533d70670e34fb4390b9ef20eccbd5cae338327ae517d4`。
- 名称和正文哈希遵循[`language_review.py`](../../../python/ygo_data/language_review.py)的`_canonical_hash`；报告中的六个候选字段哈希均与只读打开的冻结CDB逐项匹配。
- 对照卡名、召唤素材、效果条件、处理、次数限制及类别词。官方页面只用于人工比对；本记录不复制页面正文，不修改候选源、C1报告或语言记录。

| 卡号 | 官方简中页面 | zh-SC候选名称 SHA-256 | zh-SC候选正文 SHA-256 | 人工对照结果 |
|---:|---|---|---|---|
| 78449284 | [魅影骑士团凶恶之镰](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=22986&ope=2&request_locale=cn) | `99656fb9e510f86b541c1338ab742fa87c35d9d975e4b7568c0e2077a476abc0` | `b529c3aa641b1dc5883e2f0252e253fbc14bf68bc5b31c3476a477bf3c349b36` | 候选标题与官方标题一致；去除素材特召“魅影骑士团”怪兽、超量召唤“超量龙”后检索升阶魔法、被破坏后回收除外卡的条件和处理一致；“魅影骑士团”类别称谓与官方一致 |
| 81439173 | [愚蠢埋葬](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=5236&ope=2&request_locale=cn) | `9b2eb815a615121d471a1fed64277a632554d47d5ce3d773b49b0a47c6038b8e` | `bb143341df8fc5b72bb10c01cec14aded309b7b0733bdac4d8633de28b990c42` | 候选标题与官方标题一致；从牌组将1只怪兽送至墓地的效果一致 |
| 83566725 | [魅影骑士团末日护胫](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=22968&ope=2&request_locale=cn) | `b7ca68e98211a7879e7ab25cb0db809d230e261c18ecbad0bd6c4d30cefafa1f` | `c214c847e1403e06da09177f9d065d03f8dd4ae9cec4d49f8530173222282935` | 候选标题与官方标题一致；无怪兽时从手牌特召、召唤后盖放类别魔陷、墓地除外后提升最多2只暗属性等级3/阶级3怪兽的条件和处理一致；类别称谓与官方一致 |

## 状态与后续

- 本批三张在C1报告中仍为`not_reviewed`，名称和正文状态仍为`candidate`；语言类别仍为`und`/`unknown`，报告总状态仍为`qualified=false`。人工对照证据不回写结构化状态。
- zh-SC累计完成29/38张有候选值记录的人工对照；39卡样本中卡号44088353在此源缺少字段，另9张有候选值但未人工审阅。别名/本地化映射、语言类别资格及来源使用和再分发依据仍开放。
- 下批按冻结报告顺序复核卡号85257384、88504133和88544390。

此前盘点与结果见[zh-SC批次1](2026-11-02-l1-zh-sc-card-review-batch-1.md)至[zh-SC批次9](2026-11-02-l1-zh-sc-card-review-batch-9.md)；zh-CN对照见[批次1](2026-11-02-l1-card-review-batch-1.md)至[批次13](2026-11-02-l1-card-review-batch-13.md)。
