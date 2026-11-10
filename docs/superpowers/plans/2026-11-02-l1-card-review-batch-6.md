# L1中文数据人工复核：第六批3卡

日期：2026-11-02。复核固定mycard `zh-CN` 候选源中的人偶之锤、幻影骑士团 衰亡斗篷和袭击队飞翼，并与Konami官方卡片资料对照。本批两张使用官方OCG简体中文详情页；人偶之锤的官方简中详情页返回“Card information not found”，因此仅用官方日文页对照效果结构，不确认其中文标题。

## 输入与结果

- 固定来源：`mycard-zh-CN-217ae165`，上游提交`217ae165c1886af2fc36b823fc08f9fc3ec13185`；冻结zh-CN CDB SHA-256=`ff52f585de24a762a4e613ac37654b1a7fb15a58990c14f5eada85f28c3be152`。
- 冻结C1报告：`data/runtime/c1-language-review-offline-2026-10-28/language-review.json`，SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`。
- 字段哈希按[`language_review.py`](../../../python/ygo_data/language_review.py)的`_canonical_hash`计算；报告和CDB哈希与冻结记录相符，表中六个候选字段哈希可从CDB重算复现。
- 逐项比较名称、效果条件、处理结果、次数限制和类别词。官方页面只作在线对照，没有复制页面正文；页面可能变化。本记录不修改候选源、C1报告或语言记录。

| 卡号 | 官方卡片页 | zh-CN名称 SHA-256 | zh-CN正文 SHA-256 | 人工对照结果 |
|---:|---|---|---|---|
| 44088353 | [官方简中页查询](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=23148&ope=2&request_locale=cn)；[官方日文页：ドールハンマー](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=23148&ope=2&request_locale=ja) | `baa089fba0bf15400fcaa8dddff76e6d7e1c33a03f058d1342986281f1049ba2` | `91b80347dce11e1d8377719706c3ca43f920fe424da113fc652a80aedb3f98c3` | 官方简中查询页无卡片信息；候选名“人偶之锤”及中文本地化未确认。与官方日文页比较，两项效果的对象/发动条件、破坏并抽2张后可改变对方怪兽表示形式，以及墓地特召后回收此卡的处理结构一致；这不构成官方中文译文核验 |
| 46072770 | [魅影骑士团衰朽斗篷](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=22967&ope=2&request_locale=cn) | `47d174e8ed2a4b12969fbd544d00adf32f57b7b77662a7542ace5a53a5c3a9f0` | `112838aaa5f8ef179cbd28d3ae5d8df88d7c122d10222be55a5af516dc5cdbb9` | 候选标题“幻影骑士团 衰亡斗篷”不同于官方标题；三项效果的条件、检索/特召和超量素材处理一致。正文“幻影骑士团”与官方“魅影骑士团”类别词不同，映射未确认 |
| 52159691 | [急袭者之翼](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=15480&ope=2&request_locale=cn) | `d85ce5f242b7d0ebb4d26af2e911957fe9ad7ecda9571d4aae03a26088fe77af` | `79d831dda4e5dd1d0a9560b2b5613b8ec1e0dec1ad44d6b8294e8cf9d7cb87d0` | 候选标题“袭击队飞翼”不同于官方标题；规则上的类别处理、暗属性超量怪兽取素材后特召及离场除外、赋予素材怪兽不被对方效果取对象的处理一致。正文“幻影骑士团”与官方“魅影骑士团”类别词不同；“急袭猛禽”一致 |

## 状态与后续

- 本批三张在审阅前均为C1 `not_reviewed`；审阅只补充人工对照记录。C1报告仍保持原始`not_reviewed`、字段`candidate`及总状态`qualified=false`。
- 截至第六批，六批累计对照18/39张zh-CN候选；其中11张候选标题与可用的官方简中标题不同，8张文本内类别名称映射未确认。人偶之锤因没有可用官方简中详情页，不计入官方中文标题差异统计，其中文标题和类别映射保持未知。
- 其余21张zh-CN候选、全部zh-SC、别名/类别映射及使用和再分发依据仍开放。不得将在线官方页面解释为第三方数据库授权，也不得将人工对照提升为C1资格。

此前批次见[批次1](2026-11-02-l1-card-review-batch-1.md)、[批次2](2026-11-02-l1-card-review-batch-2.md)、[批次3](2026-11-02-l1-card-review-batch-3.md)、[批次4](2026-11-02-l1-card-review-batch-4.md)和[批次5](2026-11-02-l1-card-review-batch-5.md)；字段合同见[语言核验说明](../../LANGUAGE_REVIEW.md)，本批记录见[验证日志](../../TESTING.md#2026-11-02-l1第六批3卡人工来源与语义对照)。
