# L1中文数据人工复核：第二批3卡

日期：2026-11-02。复核固定mycard `zh-CN` 候选源中的灰流丽、暗叛逆超量龙、增殖的G，并与Konami官方OCG简体中文详情页对照。此批覆盖手坑、XYZ战斗效果和对方特殊召唤响应三类效果。记录绑定冻结C1报告中的字段哈希，不修改源数据、C1报告或工作台。

## 输入与结果

- 固定来源：`mycard-zh-CN-217ae165`，上游提交`217ae165c1886af2fc36b823fc08f9fc3ec13185`，zh-CN CDB SHA-256=`ff52f585de24a762a4e613ac37654b1a7fb15a58990c14f5eada85f28c3be152`。
- 冻结C1报告：`data/runtime/c1-language-review-offline-2026-10-28/language-review.json`，SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`。
- 字段哈希按[`language_review.py`](../../../python/ygo_data/language_review.py)的`_canonical_hash`计算：先将字段值序列化为紧凑UTF-8 JSON，再取SHA-256；它不是对CDB列的原始UTF-8字节直接求哈希。复核时报告与CDB整体哈希相符，三张卡六个zh-CN字段哈希均可由冻结CDB重算复现。
- 对照名称、卡种/召唤条件及效果发动条件、处理结果和限制。三张候选正文的效果语义均与官方页一致；两张卡的候选名称与官方简中标题不同，不能仅凭本次对照认定为正式别名。

| 卡号 | 官方简中页面 | C1候选名称 SHA-256 | C1候选正文 SHA-256 | 人工对照结果 |
|---:|---|---|---|---|
| 14558127 | [灰流丽](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=12950&ope=2&request_locale=cn) | `cd9c67cc7b690ac646232b535bfa5d90cca2b81435d4d7d889350fc659515d79` | `9f64da4e58382e85f0eb749ed6c1de8a8945f504dd9d108235179269600789b3` | 名称相同；发动代价、适用效果类别和无效处理语义一致 |
| 16195942 | [暗反叛超量龙](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=11385&ope=2&request_locale=cn) | `b3ecb909a68c509b380f47286b25d4ab142c6893bbafd95cf31291f557be4244` | `c908af820656793090bbf0088c5e5825ca2c97cc5e9852e65c25248b9181000c` | 候选名“暗叛逆超量龙”与官方标题不同；素材、取除数量、对象及攻击力处理语义一致 |
| 23434538 | [增殖的Z](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=9455&ope=2&request_locale=cn) | `496fb51169d21047280939d06158d13d1192fc48e4850c63a99ed1b8521ddfac` | `f91f8fcb5eaa97d0da32888db08e3041811729e181cff54fd0e0d505b7ebb0f8` | 候选名“增殖的G”与官方标题不同；送墓条件、适用时段及对方特召后的抽牌处理语义一致 |

本次没有将官方页面正文复制到仓库。在线页面是复核依据，链接和页面内容可能变化；哈希绑定的是本地冻结C1报告字段，不是网页快照。

## 状态与后续

- C1报告仍把三张卡的名称/正文标为`candidate`、语义审阅标为`not_reviewed`，报告总状态仍为`qualified=false`。此人工记录是补充审阅证据，不替代C1合同，也不提升正式数据资格。
- 暗叛逆超量龙、增殖的G的名字差异先记为未解决名称映射；在取得明确的官方别名/本地化映射依据前，不把候选名称写入正式别名字段。灰流丽的标题一致也只证明本次页面对照结果。
- 本批仅审阅`zh-CN`候选。`zh-SC`语言类别仍为`und`且未审阅；全部别名和本地化archetype映射保持未知；来源的使用依据与再分发权保持`unknown`，仍仅限本地调查。
- 截至第二批交接时，前两批累计完成6/39张zh-CN候选的名称和效果人工对照。下一批优先选取仍有官方简中详情页且能覆盖不同字段/效果形态的候选；如官方标题或文本存在差异，分别记录名称映射和效果语义，不以一个结论覆盖另一个字段。

首批结果见[批次1](2026-11-02-l1-card-review-batch-1.md)；字段合同和总体限制见[语言核验说明](../../LANGUAGE_REVIEW.md)及[验证记录](../../TESTING.md#2026-11-02-l1第二批3卡人工来源与语义对照)。
