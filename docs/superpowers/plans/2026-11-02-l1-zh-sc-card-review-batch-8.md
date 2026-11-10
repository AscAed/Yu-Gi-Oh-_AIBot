# L1 zh-SC候选：第八批3卡人工对照

日期：2026-11-02。按冻结报告中未审阅候选顺序，复核卡号62709239、63821877和64276752的zh-SC名称及正文候选，并与Konami官方OCG简体中文详情页对照。

## 输入与结果

- 冻结C1报告SHA-256=`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`；zh-SC CDB SHA-256=`5382e8dcdfaae6c582533d70670e34fb4390b9ef20eccbd5cae338327ae517d4`。
- 名称和正文哈希按[`language_review.py`](../../../python/ygo_data/language_review.py)的`_canonical_hash`计算；报告中的六个候选字段哈希均与只读打开的冻结CDB逐项匹配。
- 对照官方卡名、召唤素材、效果条件、处理结果、次数限制及类别词。官方页面仅用于人工比对；本记录不复制页面正文，不修改候选源、C1报告或语言记录。

| 卡号 | 官方简中页面 | zh-SC候选名称 SHA-256 | zh-SC候选正文 SHA-256 | 人工对照结果 |
|---:|---|---|---|---|
| 62709239 | [魅影骑士团断碎剑](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=12203&ope=2&request_locale=cn) | `075bd6946609391629a4725268b96ba03a9e842084cced7e3fde49658c8f3683` | `d323b033d5012053f7e8bc65c1c53c3cf0b6ae86decefdc3a74931b7648bb329` | 候选标题与官方标题一致；取除超量素材破坏双方各1张、被破坏后复活墓地同等级“魅影骑士团”怪兽并提升等级，以及之后仅可特殊召唤暗属性怪兽的条件和处理一致 |
| 63821877 | [魅影骑士团破手套](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=12200&ope=2&request_locale=cn) | `cda08a0b88e7c89e1ab8f6a13d8c50af747b280cd43b102c52e45c2952ec3933` | `ae38818e599914d6f309a7f9469715b44c5b7a2a7f28d4e7f70cec1cc67196af` | 候选标题与官方标题一致；以此卡为素材超量召唤的暗属性怪兽获得攻击力提升效果，以及墓地除外自身后送墓指定类别卡的处理一致；效果句中“超量召唤成功”与官方“超量召唤”措辞略异，未见条件语义差异 |
| 64276752 | [弧反叛超量龙](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=15520&ope=2&request_locale=cn) | `dde3dc8d0a87a866e1bf8ff50b8b0f6c1772befce1ce3e42c956eba88d901133` | `2c9e03e8542e1f56bf8a0e6c9301a926a9d1ead412db02d7e6636e508d436c32` | 候选标题与官方标题一致；超量召唤破坏抗性、取素材提升攻击力、拥有暗属性超量素材时无效其他表侧怪兽并限制攻击的条件和处理一致 |

## 状态与后续

- 本批三张在C1报告中仍为`not_reviewed`，名称和正文字段状态仍为`candidate`；语言类别仍为`und`/`unknown`，报告总状态仍为`qualified=false`。人工对照证据不回写结构化状态。
- zh-SC目前累计完成23/38张有候选值记录的人工对照；39卡样本中的卡号44088353在此源缺少字段，另15张有候选值但未人工审阅。别名/本地化映射、语言类别资格及来源使用和再分发依据仍开放。
- 下批按冻结报告顺序复核卡号65192027、65741786和77675029；如仅有官方日文页面或无可核对的官方简中页面，中文标题/类别映射保持未知。

此前盘点与结果见[zh-SC批次1](2026-11-02-l1-zh-sc-card-review-batch-1.md)至[zh-SC批次7](2026-11-02-l1-zh-sc-card-review-batch-7.md)；zh-CN对照见[批次1](2026-11-02-l1-card-review-batch-1.md)至[批次13](2026-11-02-l1-card-review-batch-13.md)。
