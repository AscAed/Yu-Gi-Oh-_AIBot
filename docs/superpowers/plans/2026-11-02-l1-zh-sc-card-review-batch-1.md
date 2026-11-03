# L1 zh-SC候选：只读差异盘点与首批3卡对照

日期：2026-11-02。完成39卡冻结样本中`zh-SC`字段的只读覆盖盘点，并按报告顺序人工对照前3张；本记录不修改C1报告或候选CDB。

## 冻结来源与覆盖盘点

- C1报告`data/runtime/c1-language-review-offline-2026-10-28/language-review.json` SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`。
- zh-CN CDB SHA-256=`ff52f585de24a762a4e613ac37654b1a7fb15a58990c14f5eada85f28c3be152`；zh-SC CDB SHA-256=`5382e8dcdfaae6c582533d70670e34fb4390b9ef20eccbd5cae338327ae517d4`。两份哈希均与报告冻结来源一致。
- 在39张样本中，zh-SC CDB有38张名称/正文记录；卡号44088353（人偶之锤）缺少该来源行，报告对应字段为`missing`/`candidate_value_absent`。对38张两源都有行的卡做精确字符串比较，29张名称不同、38张正文不同。此盘点只说明字段字符串相异，不代表效果语义差异，也不判定语言类别。
- 三个来源候选字段哈希遵循[`language_review.py`](../../../python/ygo_data/language_review.py)的`_canonical_hash`，并逐项与C1报告及冻结zh-SC CDB复算值相符。

## 首批人工对照

| 卡号 | 官方简中页面 | zh-SC候选名称 SHA-256 | zh-SC候选正文 SHA-256 | 人工对照结果 |
|---:|---|---|---|---|
| 1621413 | [暗镇魂超量龙](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=12639&ope=2&request_locale=cn) | `03f5d805fe6fed8ae25bb8e8f4805d7f621f22724054aac86663bf3bcb0f716b` | `be2907ff9b475ef8e07a4d635683869e974450a182dd210a6733dfb6c105d67e` | 名称与官方标题一致；素材条件、攻击力处理、对方怪兽效果响应及墓地超量怪兽特召的条件和处理语义一致；文本与zh-CN候选用词及标点不同 |
| 4993187 | [W：P变幻舞夜](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=22715&ope=2&request_locale=cn) | `bc39f760faa6260c3b95dc7b362c1d56aada69fa9e81ea53c62e617ec0599256` | `3e04f1e68ce22d9abde46a5d8e5acea42c3dd0af3909d15d0741fbd2ae3cca25` | 名称与官方标题一致；特殊召唤后临时除外以无效并除外怪兽效果、对方主要阶段进行连接召唤及可使用对方低LINK值素材的条件和处理语义一致 |
| 10045474 | [无限泡影](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=13631&ope=2&request_locale=cn) | `86d14f3c905b10bc7bf78b220b040bfe18d914b6d56136f84b3c5a06fbab3f90` | `82713bdca797b486dc70bd1902312638c38b2de55425e1bd7274ab87ee7881d7` | 名称与官方标题一致；空场手牌发动、无效对象怪兽效果及盖放后同纵列魔陷效果无效的条件和处理语义一致 |

## 状态与后续

- 本批三张在C1报告中仍为`not_reviewed`，名称和正文状态仍为`candidate`；`language_category=und`、类别状态`unknown`，报告总状态仍为`qualified=false`。人工对照证据不回写结构化状态。
- 至此，zh-CN 39/39张名称/效果已有人工对照；zh-SC仅此3张完成首批人工对照。余下35张有候选值但未人工审阅，卡号44088353缺少zh-SC候选字段。全部别名/本地化类别映射、语言类别资格和来源使用及再分发依据仍开放。
- 下批继续按冻结报告顺序选取卡号14558127、16195942和23434538；若遇源字段缺失或官方简中页不可得，记录缺口并保持未知。

此人工记录不构成C1资格验收，也不证明第三方数据库获得使用或再分发授权；此前zh-CN逐卡结果见[批次1](2026-11-02-l1-card-review-batch-1.md)至[批次13](2026-11-02-l1-card-review-batch-13.md)。
