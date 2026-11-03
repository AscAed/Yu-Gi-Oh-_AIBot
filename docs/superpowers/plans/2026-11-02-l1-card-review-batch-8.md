# L1中文数据人工复核：第八批3卡

日期：2026-11-02。按冻结报告中未审阅候选顺序，复核幻影骑士团 断碎剑、幻影骑士团 破手套和弧叛逆超量龙，并与Konami官方OCG简体中文详情页逐项对照。

## 输入与结果

- 固定来源：`mycard-zh-CN-217ae165`，上游提交`217ae165c1886af2fc36b823fc08f9fc3ec13185`；冻结zh-CN CDB SHA-256=`ff52f585de24a762a4e613ac37654b1a7fb15a58990c14f5eada85f28c3be152`。
- 冻结C1报告：`data/runtime/c1-language-review-offline-2026-10-28/language-review.json`，SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`。
- 字段哈希按[`language_review.py`](../../../python/ygo_data/language_review.py)的`_canonical_hash`计算；报告和CDB哈希与冻结记录相符，表中六个候选字段哈希可从CDB重算复现。
- 对照卡名、召唤素材、效果条件、处理结果、次数限制和类别词。官方页面只作在线对照，没有复制页面正文；页面可能变化。本记录不修改候选源、C1报告或语言记录。

| 卡号 | 官方简中页面 | zh-CN名称 SHA-256 | zh-CN正文 SHA-256 | 人工对照结果 |
|---:|---|---|---|---|
| 62709239 | [魅影骑士团断碎剑](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=12203&ope=2&request_locale=cn) | `819f5d68c484f937f43be267b6944099310b36011f26d292fbbeaa420c5188b3` | `07d0ec9c98e123c73a89756259e7d0f97f32785070c1b83a5aeeb274279936bd` | 候选标题“幻影骑士团 断碎剑”不同于官方标题；超量素材取除并破坏双方各1张、被破坏后复活墓地相同等级怪兽并提升等级、之后仅可特召暗属性怪兽的条件和处理一致；正文“幻影骑士团”与官方“魅影骑士团”类别词不同，映射未确认 |
| 63821877 | [魅影骑士团破手套](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=12200&ope=2&request_locale=cn) | `df5960cf56b058c1e00c8213b56ea2f1bb7ddf07bc65da164285e33d42b2ef10` | `b056090e81a2ded3a5fde5f3bd896d3f39f50e00274d090c2cd3a98c267c749b` | 候选标题“幻影骑士团 破手套”不同于官方标题；赋予暗属性超量怪兽的攻击力提升效果及墓地除外后送墓效果一致；正文“幻影骑士团/幻影”与官方“魅影骑士团/魅影”类别词不同，映射未确认 |
| 64276752 | [弧反叛超量龙](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=15520&ope=2&request_locale=cn) | `3c4c99872ffa205c48e1ff5ff7127d59480a75dd47188cdfb69aa58784b6e176` | `d887d0baa502a04a12e62b70ca457674b321a1fc6afc83d584489ca8d22e8f1b` | 候选标题“弧叛逆超量龙”与官方标题“弧反叛超量龙”一字不同；超量召唤破坏抗性、取素材提升攻击力、拥有暗属性超量素材时无效其他表侧怪兽并限制攻击的条件/处理一致 |

## 状态与后续

- 本批三张在审阅前均为C1 `not_reviewed`；审阅只补充人工对照记录。C1报告仍保持原始`not_reviewed`、字段`candidate`及总状态`qualified=false`。
- 截至第八批，八批累计对照24/39张zh-CN候选；其中16张候选标题与官方简中标题不同，11张文本内类别名称映射未确认。名称和类别差异不自动确认为别名或已验证本地化。
- 其余15张zh-CN候选、全部zh-SC、别名/类别映射及使用和再分发依据仍开放。不得将在线官方页面解释为第三方数据库授权，也不得将人工对照提升为C1资格。

此前批次见[批次1](2026-11-02-l1-card-review-batch-1.md)至[批次7](2026-11-02-l1-card-review-batch-7.md)；字段合同见[语言核验说明](../../LANGUAGE_REVIEW.md)，本批记录见[验证日志](../../TESTING.md#2026-11-02-l1第八批3卡人工来源与语义对照)。
