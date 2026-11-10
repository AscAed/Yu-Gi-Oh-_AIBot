# L1中文数据人工复核：第三批3卡

日期：2026-11-02。复核固定mycard `zh-CN` 候选源中的禁忌的一滴、幻影骑士团 破洞鳞甲和幻影雾剑，并与Konami官方OCG简体中文卡片详情页对照。本批覆盖速攻魔法、怪兽及永续陷阱。

## 输入与结果

- 固定来源：`mycard-zh-CN-217ae165`，上游提交`217ae165c1886af2fc36b823fc08f9fc3ec13185`；zh-CN CDB SHA-256=`ff52f585de24a762a4e613ac37654b1a7fb15a58990c14f5eada85f28c3be152`。
- 冻结C1报告：`data/runtime/c1-language-review-offline-2026-10-28/language-review.json`，SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`。
- 字段哈希按[`language_review.py`](../../../python/ygo_data/language_review.py)的`_canonical_hash`计算：先将字段值序列化为紧凑UTF-8 JSON，再取SHA-256；它不是对CDB列的原始UTF-8字节直接求哈希。复核时报告与CDB整体哈希相符，三张卡六个zh-CN字段哈希均可由冻结CDB重算复现。
- 逐项对照卡名、卡种/召唤条件、发动条件、处理结果和限制。未复制官方页面正文；在线页面可能变化，字段哈希绑定本地冻结报告，不构成网页快照。

| 卡号 | 官方简中页面 | C1候选名称 SHA-256 | C1候选正文 SHA-256 | 人工对照结果 |
|---:|---|---|---|---|
| 24299458 | [禁忌的一滴](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=15299&ope=2&request_locale=cn) | `350e26a2f52a15f2df41cb68948c014523d01874744495684f59e15ef4b7a536` | `59f2fb4f243de0b7f6c49ab9c268ed1b5f8ca3aa5dd10ad8a39b36b94d228ebd` | 名称一致；送墓代价、对方连锁限制、选取数量及无效/攻击力处理一致 |
| 25538345 | [魅影骑士团裂鳞甲](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=15482&ope=2&request_locale=cn) | `80457bd4dc49f674924222ad55194c223bfc78f4a9597dbcf96a629c150e0ade` | `2977dc612ba89de8c6ea25bdbc356c676918998bb8f73f0c59736f8724ee8394` | 候选名“幻影骑士团 破洞鳞甲”不同于官方标题；发动和处理步骤一致，但文本中的类别名称`幻影骑士团/幻影`与官方`魅影骑士团/魅影`不同，映射未确认 |
| 25542642 | [魅影雾剑](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=12205&ope=2&request_locale=cn) | `d4543fb41594efd8ff5dd639e4b052113860c97cc2d66eed799b0fb565f8c9d8` | `9d892a35e6b56f8362f839a51c02d3db5a47bfaff7d6e5fc600f400a76433e51` | 候选名“幻影雾剑”不同于官方标题；对象、无效/攻击限制及墓地特殊召唤步骤一致，但`幻影骑士团`类别名称映射未确认 |

## 状态与后续

- 本批人工对照补充离线证据；C1报告仍将三张卡名称/正文标为`candidate`、语义审阅标为`not_reviewed`，总状态保持`qualified=false`。不修改候选源、C1报告或工作台行为。
- 对“幻影”与“魅影”名称及类别引用的差异不推断为正式别名或已验证的本地化映射。别名、archetype字段、使用依据和再分发状态继续保持未知；`zh-SC`类别仍为`und`且未审阅。
- 截至第三批交接时，三批合计完成9/39张zh-CN候选的名称与效果对照；当时其余30张zh-CN、全部zh-SC和权利依据仍开放。后续批次继续使用字段哈希绑定及官方来源逐卡对照，任何名称或类别差异分别记录，不提升未验证字段。

此前批次见[批次1](2026-11-02-l1-card-review-batch-1.md)和[批次2](2026-11-02-l1-card-review-batch-2.md)；字段合同见[语言核验说明](../../LANGUAGE_REVIEW.md)，本批记录见[验证日志](../../TESTING.md#2026-11-02-l1第三批3卡人工来源与语义对照)。
