# 39卡中文候选字段离线核验

此工具核对冻结候选的字段存在性、记录与CDB候选值是否一致，并报告来源哈希。它不判断翻译是否准确，不授予语言资格，也不确定数据库的授权或再分发权。

## 执行与报告

在仓库根目录运行：

```powershell
py -m ygo_data.language_review audit --output data/runtime/c1-language-review-offline-2026-10-28/language-review.json
```

输入路径固定为`configs/language-sources-2026-10-19.json`、冻结的39卡发行样本、`language-records.json`和两份固定mycard CDB。工具以只读模式打开SQLite，核对来源清单所载CDB哈希，并在读取前后比较所有输入字节哈希。输出必须独占创建；存在时拒绝覆盖。

报告使用`language-field-review-v1`合同。名称和正文候选只保存逐字段SHA256，不包含候选文字。每一字段状态为`candidate`、`missing`、`conflict`或`unknown`，并包含来源ID和原因。引擎`alias`与`setcode`以结构元数据记录，不当作中文名称别名或本地化字段。

## 本次冻结材料结果

- 样本为39个唯一卡号；来源清单最后核对日期为2026-10-19，候选上游提交固定为`217ae165c1886af2fc36b823fc08f9fc3ec13185`。
- zh-CN来源类别为候选`zh-Hans`。39卡均有候选名称和正文，与冻结语言记录一致；别名和本地化字段映射39卡均为未知。
- zh-SC的官方语言类别保持`und`。38卡有名称和正文候选，1卡缺失；别名和本地化字段映射39卡均为未知。
- 未发现同源候选名称冲突；这不等于证明名称唯一或语义正确。
- 两份来源的语义审阅、使用依据和再分发状态均未通过；数据库仍限本地调查，不向工作台传递正文。

实际报告位于忽略目录`data/runtime/c1-language-review-offline-2026-10-28/language-review.json`，并通过`schemas/language-field-review-v1.schema.json`校验。旧的`language-audit`入口和合同保持原义。

报告SHA-256为`6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`，大小136,708字节。报告绑定的输入SHA-256如下：

| 输入 | SHA-256 |
|---|---|
| 来源清单 `configs/language-sources-2026-10-19.json` | `c8f2512501f4563c1821e275824193ee67bdad5938db13cd867c26952eed8cbe` |
| 39卡样本 `releases.json` | `7d813f8962eb46c3f66e61bb2c146af38f497cb2f6075a34a5eb8f3d2d7f0e7a` |
| `language-records.json` | `6dead940fe22beb6a876992fce2c935d6e5e9172f7b6f1d0bc51f48c5cb25b75` |
| zh-CN CDB | `ff52f585de24a762a4e613ac37654b1a7fb15a58990c14f5eada85f28c3be152` |
| zh-SC CDB | `5382e8dcdfaae6c582533d70670e34fb4390b9ef20eccbd5cae338327ae517d4` |

## 工作台状态接口

可用报告时启动工作台并指定只读文件：

```powershell
cargo run -p ygo-cli --offline --locked -- workbench serve --language-status data/runtime/c1-language-review-offline-2026-10-28/language-review.json
```

`GET /api/language-status?ids=...`只返回卡号、来源ID、字段状态、稳定原因和候选哈希，不返回候选文字。缺少、损坏或格式不受支持的状态文件会退化为未核验状态，不阻止草稿编辑。工作台始终提示候选未经语义核验。

39卡的候选仍不能作为正式中文搜索、自动选择或卡片效果知识。完成语义准确性、语言类别及使用/分发依据核验后，才可另行评估有限字段资格。

2026-11-03对人偶之锤（44088353）单独复核来源与使用依据：Konami官方日文页和本地日文收录归档哈希相符；同卡号官方简中查询仍返回无卡片信息。冻结C1中zh-CN名称/正文仍为`candidate`、语义`not_reviewed`，使用依据和再分发均为`unknown`。上游`mycard/ygopro-database`来源链已定位，但未发现覆盖本项目使用/再分发的许可文本；不改C1或候选状态。详见[单卡来源与使用依据复核](superpowers/plans/2026-11-03-l1-44088353-source-basis-review.md)。

2026-11-03将来源身份与权利线索复核扩展到冻结清单中的zh-CN和zh-SC两份CDB：本地字节数、SHA-256及Git blob身份均与同一MyCard固定提交对象匹配；检查的固定提交根目录和locale目录未列出许可文件，README只称数据库用于测试。此次未找到覆盖本项目使用或再分发的明确授权，两个来源的使用依据和再分发状态继续为`unknown`；没有修改冻结配置、C1报告、候选数据或资格。详情见[双locale来源与使用依据复核](superpowers/plans/2026-11-03-l1-mycards-locale-source-rights-review.md)。

2026-11-02 L1已完成十三批共39张zh-CN名称/效果人工对照；其中38张找到官方简中详情页，1张目前仅找到官方日文详情页（人偶之锤44088353）。在38张可直接与简中页面比较的卡中，29张候选标题不同，另有21张正文类别称谓映射未确认；名称/类别映射仍需依据，不能直接确认为别名或正式本地化映射。卡号91279700的官方简中页标题为“邪蚀俄菲翁”，页面列出简中收录LOCR-SC067（2026-04-18）；zh-CN候选“入魔龙主 俄菲翁”与官方标题不同，正文“入魔/邪蚀”类别映射仍未确认。另已完成zh-SC前十三批38/38张有候选值记录的人工对照；39卡样本中zh-SC源有38行，人偶之锤（44088353）字段缺失。在38张两源都有行的卡中，29张名称字符串、38张正文字符串与zh-CN不同；字符串差异统计不等于语义差异。38张有字段的人工对照记录仍为C1 `candidate`、`not_reviewed`和`und`/`unknown`；报告仍为`qualified=false`，没有改动候选源或工作台行为。zh-SC全部38张有值候选均有人工对照记录，别名、语言类别及权利依据均仍开放。逐卡字段哈希和边界见[zh-CN批次1](superpowers/plans/2026-11-02-l1-card-review-batch-1.md)至[zh-CN批次13](superpowers/plans/2026-11-02-l1-card-review-batch-13.md)、[zh-SC批次1](superpowers/plans/2026-11-02-l1-zh-sc-card-review-batch-1.md)至[zh-SC批次13](superpowers/plans/2026-11-02-l1-zh-sc-card-review-batch-13.md)。
