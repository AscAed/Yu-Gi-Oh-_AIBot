# 2026赛事原表重选与独立资产组

实施起点为 `a2929f8`。本次已通过来源、主卡组／额外合法性、离线资产重建及脚本加载关口。第二阶段首回合语义、v6和第三阶段48手评估尚未完成；不能将本页作为整轮验收记录。

## 选定原表

[T_NANKOKU_TCG 原始发布](https://x.com/T_NANKOKU_TCG/status/2089313186457780709)：2026年8月17日公认排名赛，6人参加，冠军「たまもん」，构筑名「幻影騎士団」。原始帖子、官方嵌入JSON和4096×2377原图关联一致。不是大型赛事成绩证明，也不声称该赛事采用10月规则；本项目重新按冻结10月规则检查。

原图：[HP67QpnbIAAT-Yd.jpg](https://pbs.twimg.com/media/HP67QpnbIAAT-Yd.jpg?name=orig)，SHA256 `1e8369a35fe3e67b2fcad4d3d880335cc2d5d1f0b2ee19e914aa0e538aabac13`。

主卡组41张、额外15张，39个不同卡号；Side未公开，未完成其合法性检查。执行夹具的 `side: []` 只表示本场景不使用Side。完整原表见 `tests/fixtures/tournament-2026.deck.json`，字节SHA256 `5533c9f0aae115e9a408a26acb6d037d38c9505c1e78970431ffc19ab92cdb88`。转录独立复核，修正了土龙与角兔、两张一滴、Karmael与Kaspitell、Four Heavenly Dragons与Supreme King Dragon的初始识别歧义。

检索窗口为2026-01-01至2026-10-16。15条取得原始材料的候选、18张照片及逐项理由保存于 `configs/tournament-2026.source.json`。聚合页只用于发现；没有声称穷尽全网赛事。资料完整度优先，再按赛事日期和规范化URL筛选。选定来源是本次候选中最新且完整、可准确转录并通过冻结规则的原表，没有按规划器表现选表。

- 9月11日原表的No.67、8月29日原表的Ouroboros在冻结表中禁止。
- 8月25日只展示三张卡；8月10日照片有奖品遮住陷阱区域，保留数量未知，不认定其违规。
- 10月3日poi赛事的转发照片含两张冻结表限制1张的过早的埋葬，且额外／原始发布关联不全。
- 其余候选的已确认禁卡与未解决身份分别记录，未将未确认的Droll数量写成确定违规。
- 10月4日旧来源保留在 `TOURNAMENT_SOURCE_GATE.md`，未覆盖其诊断材料。

## 规则与发行

[官方10月名单](https://www.yugioh-card.com/japan/event/limitregulation/?list=202610)取得并解析207行：禁止94、限制95、准限制13、新解除5。映射到卡号后与原冻结快照无差异、无未解析项。203个限制键包含202个规范卡号及一张同名异图别名，不将207行误称为207张受限制卡。

冻结LFLists提交 `1051a65ab853fd84521aa919d1859f9468816c56`、源SHA256 `e85912d33eaada6817477c3a8fac0ef0c3e77b6ca25de924826e7f5cbc7e25ab` 和原banlist身份保持不变。Rust CLI实际检查主41＋额外15合法。无已公开Side，不能推断主／额外加未知Side的总量合法。

30个旧卡号在2025-12-07的历史BabelCDB中已有规范OCG记录，其内容哈希和提交另行冻结；其余9张按官方日本产品发行页核对，最晚为2026-07-25的Doll Hammer，均早于原赛事日期。`ocg_released_by` 是有证据的发行时间上界，历史数据库日期不冒充首发日。当前CDB中的规范卡号、OCG区域位及原图日文实体卡共同交叉核对，未使用预发行占位编号。

## 独立资产组

配方 `configs/tournament-2026.assets.json`，组身份：

`asset-group-228cca96b5cf16a5e8d8f397cb30db073b483e75ddb0536d7d5f6f28783af340`

| 组件 | 冻结来源 | 内容SHA256 |
|---|---|---|
| BabelCDB | `b20871e24ec0edda78f42f7e115d4deef0184889` | `3530f406ba92b0f8d5699aa107e95158a1f1b4816f8f5ca2dd82c490301ef632` |
| CardScripts | `7e5ae6d089bde91471436b9c4ce192b61332f3ff` | scripts.json `26c44946c7aba56900ededc5358e163fce71d5b99182f0d0fa910739bc3d9c94` |
| 原core／Lua | `38d04c9feb1a26617407091380634c87262fe3f8`／`6e22fedb74cf0c9b6656e9fce8b7331db847c605` | DLL `446f26df7a2fb35d94374d74f5f5a5ef200d5454322d372b325e46b4e083d7a9` |

没有升级core。13,567个Lua及CDB／core／清单共13,571文件，从固定脚本ZIP离线重建后的组身份和全部文件哈希一致。ZIP中的根目录辅助脚本、official目录和被依赖的proc_unofficial.lua有明确选择规则；路径穿越、额外未登记文件和缺少的字面LoadScript依赖被拒绝。动态依赖仍需引擎执行检查，不宣称静态扫描证明所有运行分支。

新目录为忽略的 `data/runtime/tournament-2026/frozen`，旧 `data/runtime` 资产未覆盖。新快照存放于独立 `snapshots`，目录身份为 `catalog-de71e6b4683795a9cb83c44ba85bf1cc43d635ce8da032fff9f8b055b60e31b9`。CDB14731条记录。实际ABI/doctor通过，完整原表脚本可加载。

人工兼容线路：Soleret特召→盖Veil并发动→叠Scythe→取除Soleret、从牌库特召Decayed→检索Boots并特召→连接Rusty→送墓Gloves、盖Fog→结束回合。原始MOVE直接断言费用取除、效果送墓及实际终场；48决策、160事件的独立重放一致。这是资产兼容探针，不替代逐效果正反例，也不算v6人工评估基准。

## 离线复核

原始照片、数据库、Lua、DLL与运行报告因分发边界继续忽略。离线重建的前提是已取得并按配方哈希核对的CDB、脚本ZIP和原core；不能仅靠源码恢复受分发限制的数据。所需源码、官方发行页及原始帖子URL和哈希均在源记录／配方内。

```powershell
$env:PYTHONPATH='python'
py -m ygo_data.assets freeze --cdb <固定CDB> --scripts <固定CardScripts.zip> --core <原ocgcore.dll> --recipe configs/tournament-2026.assets.json --output <新目录>
py -m ygo_data.assets verify --input <新目录>
py -m ygo_data.tournament --source configs/tournament-2026.source.json --deck tests/fixtures/tournament-2026.deck.json --coverage knowledge/tournament-2026.coverage.json --assets <新目录> --receipts <reselection原始材料目录> --banlist <冻结快照JSON>
$env:PYTHONPATH='python;tests'
$env:YGO_TOURNAMENT_ENGINE='<独立engine.toml>'
py -m unittest test_tournament_gate -v
```

外网获取时必须在同一终端调用注入127.0.0.1:7897代理。上述命令自身离线。设置独立engine配置后运行doctor，不能运行默认prepare-runtime.py覆盖旧资产。

效果清单 `knowledge/tournament-2026.coverage.json` 已分类102项：86项场景内、16项有依据排除。**当前86项均未作为完整实现／验真交付**。首回合正常召唤、触发、即时响应、必要结束阶段处理均在清单范围；后续必须逐项实现、验真后再进入样本评估。
