# L1中文数据人工复核：第四批3卡

日期：2026-11-02。复核固定mycard `zh-CN` 候选源中的幻影骑士团 锈蚀月刃斧、袭击队骑士和S：P小夜骑士，并与Konami官方OCG简体中文卡片详情页逐项对照。本批覆盖主题连接怪兽、阶级进化超量怪兽及泛用连接怪兽。

## 输入与结果

- 固定来源：`mycard-zh-CN-217ae165`，上游提交`217ae165c1886af2fc36b823fc08f9fc3ec13185`；zh-CN CDB SHA-256=`ff52f585de24a762a4e613ac37654b1a7fb15a58990c14f5eada85f28c3be152`。
- 冻结C1报告：`data/runtime/c1-language-review-offline-2026-10-28/language-review.json`，SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`。
- 字段哈希按[`language_review.py`](../../../python/ygo_data/language_review.py)的`_canonical_hash`计算：先将字段值序列化为紧凑UTF-8 JSON，再取SHA-256。复核时报告与CDB整体哈希相符，三张卡六个zh-CN字段哈希均可由冻结CDB重算复现。
- 对照卡名、卡种/召唤条件、发动条件、处理结果和限制。未复制官方页面正文；网页可能变化，字段哈希绑定本地冻结报告，不构成网页快照。

| 卡号 | 官方简中页面 | C1候选名称 SHA-256 | C1候选正文 SHA-256 | 人工对照结果 |
|---:|---|---|---|---|
| 26692769 | [魅影骑士团锈蚀月刃斧](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=14054&ope=2&request_locale=cn) | `6e992a9eee1aac3b97ae941ab7762bd861cdcaade1ec4e068870e1e8d1cdf29c` | `ed2da15b8bfa3842cc66df84962a88933912d60c6c37dfd62bac089a8c5f185e` | 候选名“幻影骑士团 锈蚀月刃斧”不同于官方标题；送墓后盖放、连接端特召后破坏的操作一致，但正文类别词`幻影骑士团/幻影`与官方`魅影骑士团/魅影`不同，映射未确认 |
| 28781003 | [急袭者骑士](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=15519&ope=2&request_locale=cn) | `7ff10c9b00afbb7f0720062bcda9902fbaec0407af077dba85c149bdc500f8cf` | `206d1bd618433ce6f7e2c6464ef42652a1c39d2d1af90d0ec4f9bc6663184643` | 候选名“袭击队骑士”不同于官方标题；规则视为类别、取除素材及升降1阶叠放特召步骤一致，但`幻影骑士团`与官方`魅影骑士团`映射未确认 |
| 29301450 | [S：P小夜骑士](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=19188&ope=2&request_locale=cn) | `17168a0574b2c1dd76f6f43c0ce2fbe2b8add170aafb2ae5b684c268cf4f6963` | `a160ab6c38e96e91efc4cc2e937da10649a01ded5a0b6c9ba16ebb3c9b41437e` | 名称一致；素材条件、除外对象、直接攻击限制及对方效果响应的除外处理一致 |

## 状态与后续

- 本批人工对照补充离线证据；C1报告仍将三张卡名称/正文标为`candidate`、语义审阅标为`not_reviewed`，总状态保持`qualified=false`。不修改候选源、C1报告或工作台行为。
- 对“幻影”与“魅影”名称及类别引用的差异不推断为正式别名或已验证的本地化映射。别名、archetype字段、使用依据和再分发状态继续保持未知；`zh-SC`类别仍为`und`且未审阅。
- 截至第四批交接时，四批累计完成12/39张zh-CN候选的名称与效果对照；其余27张zh-CN、全部zh-SC和权利依据仍开放。后续批次继续使用字段哈希绑定及官方来源逐卡对照，名称、类别和效果分别记录，不提升未验证字段。

此前批次见[批次1](2026-11-02-l1-card-review-batch-1.md)、[批次2](2026-11-02-l1-card-review-batch-2.md)和[批次3](2026-11-02-l1-card-review-batch-3.md)；字段合同见[语言核验说明](../../LANGUAGE_REVIEW.md)，本批记录见[验证日志](../../TESTING.md#2026-11-02-l1第四批3卡人工来源与语义对照)。
