# C1 牌组中文字段离线核验交接

## 交付范围

本批仅对冻结39卡样本核对候选字段存在性、卡号关联、声明来源和输入稳定性，并让B2工作台读取字段状态。候选名称/正文只在忽略目录的原始CDB与语言记录中；报告仅保存候选哈希。没有翻译语义、正式语言类别、别名/字段映射、使用依据或再分发权认证。

固定报告：`data/runtime/c1-language-review-offline-2026-10-28/language-review.json`，SHA-256 `6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`，136,708字节。合同：`schemas/language-field-review-v1.schema.json`。输出为独占创建；真实材料本批仅生成一次，后续不得覆盖或重签。

## 来源冻结

| 来源 | SHA-256 | 说明 |
|---|---|---|
| `configs/language-sources-2026-10-19.json` | `c8f2512501f4563c1821e275824193ee67bdad5938db13cd867c26952eed8cbe` | 两个固定来源声明 |
| `data/runtime/baseline-2026-10-19/data/releases.json` | `7d813f8962eb46c3f66e61bb2c146af38f497cb2f6075a34a5eb8f3d2d7f0e7a` | 39个唯一卡号发行样本 |
| `data/runtime/baseline-2026-10-19/data/language-records.json` | `6dead940fe22beb6a876992fce2c935d6e5e9172f7b6f1d0bc51f48c5cb25b75` | 冻结语言记录 |
| zh-CN CDB | `ff52f585de24a762a4e613ac37654b1a7fb15a58990c14f5eada85f28c3be152` | `zh-Hans`候选来源 |
| zh-SC CDB | `5382e8dcdfaae6c582533d70670e34fb4390b9ef20eccbd5cae338327ae517d4` | 语言类别`und` |

两份CDB使用SQLite只读模式。候选上游提交固定为`217ae165c1886af2fc36b823fc08f9fc3ec13185`，取得日期2026-10-19。来源树未发现LICENSE，现有说明仍将使用及再分发状态保留为unknown。

## 字段结果与使用边界

- 样本39卡、两个来源；zh-CN候选名称与正文各39项，zh-SC候选各38项且名称/正文各缺1项。
- 两来源的中文别名与本地化字段映射均为unknown，各字段每来源39项；没有同源候选名称冲突。
- zh-SC语言类别仍为`und`；所有来源的语义审阅均为`not_reviewed`，使用依据/再分发仍unknown；`qualified=false`。
- 引擎`alias`和`setcode`是结构元数据，不解释为中文别名或本地化主题。
- 旧`language-audit`有197条未解决项；本批不修改其报告或合同。

工作台通过`--language-status`和`GET /api/language-status?ids=...`显示候选、缺失、冲突或未知状态及来源/哈希。它不返回候选文本；状态文件缺失、损坏或不受支持时退回未核验，草稿仍可编辑。

## 下一步与资格

完整Python、Rust、schema和本机浏览器验收结果以`docs/TESTING.md`中的2026-10-28 C1记录为准。认证消费子集40、政策预留7、规划47；旧confirmation与全部历史实际累计仍为unknown。本批新增原生研究、runner、worker和FFI调用0。

后续如要开放正式中文检索或分发，需另行取得并审查语义、语言类别及使用/再分发证据。本交接不授权联网核验、复制正文、运行研究worker或改动部署。
