# L1中文数据人工复核：第七批3卡

日期：2026-11-02。按冻结报告中未审阅候选的顺序，复核增援、彼岸的黑天使 基路伯和升阶魔法-幻影骑士团的镇魂歌，并与Konami官方OCG简体中文详情页逐项对照。本批三张均有官方简中页面。

## 输入与结果

- 固定来源：`mycard-zh-CN-217ae165`，上游提交`217ae165c1886af2fc36b823fc08f9fc3ec13185`；冻结zh-CN CDB SHA-256=`ff52f585de24a762a4e613ac37654b1a7fb15a58990c14f5eada85f28c3be152`。
- 冻结C1报告：`data/runtime/c1-language-review-offline-2026-10-28/language-review.json`，SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`。
- 字段哈希按[`language_review.py`](../../../python/ygo_data/language_review.py)的`_canonical_hash`计算；报告和CDB哈希与冻结记录相符，表中六个候选字段哈希可从CDB重算复现。
- 对照卡名、效果条件、处理结果、次数限制和类别词。官方页面只作在线对照，没有复制页面正文；页面可能变化。本记录不修改候选源、C1报告或语言记录。

| 卡号 | 官方简中页面 | zh-CN名称 SHA-256 | zh-CN正文 SHA-256 | 人工对照结果 |
|---:|---|---|---|---|
| 32807846 | [增援](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=5328&ope=2&request_locale=cn) | `ebf8a3db48cd1984d4d50632b9bc2d663b1394d2ed9b8c73940054fa479cc897` | `ad615a6dc4c4c4bdf2654d25fb82c0a3fa0c09cd5bc36f46ba937b50a57d2e3f` | 名称一致；从牌组将等级4以下战士族怪兽加入手牌的效果一致 |
| 58699500 | [彼岸之黑天使 凯鲁比尼](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=13506&ope=2&request_locale=cn) | `dd4daa90f0d526391cf7b7c6b3935dc090f9a1df50ff35fa8f3eb1ea41b9088c` | `51e67f1b5b160339948ce9311465c0abf2011853330be7b7112f07e5546e3e0c` | 候选标题“彼岸的黑天使 基路伯”不同于官方标题；连接素材、连接端保护、代替破坏处理、送墓等级3并提升“彼岸”怪兽数值的条件和处理一致；类别词“彼岸”一致，名称映射未确认 |
| 62104532 | [升阶魔法－魅影骑士团镇魂曲](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=23006&ope=2&request_locale=cn) | `63aa12f3710ee8694c25e385a48ba6f06b6e0a6240038bc676159f63380598bc` | `e1ea086b241098689aba27911c13111bf79aa732311f6065cb602ce5bbeae1d7` | 候选标题“升阶魔法-幻影骑士团的镇魂歌”不同于官方标题；一回合发动限制、从墓地/除外状态复活并无效的对象条件及后续高1阶超量召唤处理一致；正文“幻影骑士团”与官方“魅影骑士团”类别词不同，映射未确认，“超量龙”用词一致 |

## 状态与后续

- 本批三张在审阅前均为C1 `not_reviewed`；审阅只补充人工对照记录。C1报告仍保持原始`not_reviewed`、字段`candidate`及总状态`qualified=false`。
- 截至第七批，七批累计对照21/39张zh-CN候选；其中13张候选标题与官方简中标题不同，9张文本内类别名称映射未确认。标题差异不自动确认为别名或已验证本地化。
- 其余18张zh-CN候选、全部zh-SC、别名/类别映射及使用和再分发依据仍开放。不得将在线官方页面解释为第三方数据库授权，也不得将人工对照提升为C1资格。

此前批次见[批次1](2026-11-02-l1-card-review-batch-1.md)至[批次6](2026-11-02-l1-card-review-batch-6.md)；字段合同见[语言核验说明](../../LANGUAGE_REVIEW.md)，本批记录见[验证日志](../../TESTING.md#2026-11-02-l1第七批3卡人工来源与语义对照)。
