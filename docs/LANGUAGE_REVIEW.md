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
