# L1 MyCard 中文 CDB 来源与使用依据复核

日期：2026-11-03。对冻结语言来源中的 `zh-CN` 与 `zh-SC` 两份 CDB 做只读来源身份及上游权利线索复核。不修改候选数据、来源配置、C1报告、工作台行为或语言资格状态。

## 固定来源与本地文件身份

两条来源记录均指向 `mycard/ygopro-database` 提交 `217ae165c1886af2fc36b823fc08f9fc3ec13185`。冻结配置 `configs/language-sources-2026-10-19.json` 的 SHA-256 为 `c8f2512501f4563c1821e275824193ee67bdad5938db13cd867c26952eed8cbe`，与既有 C1 报告绑定的输入身份一致。

| 来源 | 本地冻结文件 | 字节数 | SHA-256 | 本地 Git blob SHA-1 | 冻结语言状态 |
|---|---|---:|---|---|---|
| `mycard-zh-CN-217ae165` | `data/runtime/baseline-2026-10-19/data/ygopro-database-locales-zh-CN-cards.cdb` | 8,164,352 | `ff52f585de24a762a4e613ac37654b1a7fb15a58990c14f5eada85f28c3be152` | `2f3b012db0ca4c48b64a5854f058a339811b89c2` | `zh-Hans`候选 |
| `mycard-zh-SC-217ae165` | `data/runtime/baseline-2026-10-19/data/ygopro-database-locales-zh-SC-cards.cdb` | 6,520,832 | `5382e8dcdfaae6c582533d70670e34fb4390b9ef20eccbd5cae338327ae517d4` | `df1c6180deec99ebd1ba4a23af20468530889fa1` | `und` |

两份本地文件的字节数、SHA-256 与冻结配置相符；本地 `git hash-object` 结果也分别与该固定提交的上游 CDB Git blob SHA-1 相同。这证明本机冻结文件与所指向的上游对象一致，不证明字段准确、来源授权或再分发权。

## 上游目录与授权线索

只读检查了[固定提交](https://github.com/mycard/ygopro-database/tree/217ae165c1886af2fc36b823fc08f9fc3ec13185)的根目录、[README](https://github.com/mycard/ygopro-database/blob/217ae165c1886af2fc36b823fc08f9fc3ec13185/README.md)、[`locales/zh-CN`](https://github.com/mycard/ygopro-database/tree/217ae165c1886af2fc36b823fc08f9fc3ec13185/locales/zh-CN)和[`locales/zh-SC`](https://github.com/mycard/ygopro-database/tree/217ae165c1886af2fc36b823fc08f9fc3ec13185/locales/zh-SC)：

- 根目录列出`.github`、`.gitignore`、`.gitlab-ci.yml`、`README.md`和`locales`；固定提交的`LICENSE`路径查询返回Not Found。
- 两个locale目录各列出`cards.cdb`与`strings.conf`，未列出目录级许可或授权说明。
- README blob `b6cfd4a9aa885691b977d7f804428ea89779e00a`（58字节）写明这些数据库“for now just for test”。这是用途描述，不构成本项目可复用或再分发的许可文本。

以上是对指定提交和列出路径的检查结果，不证明不存在仓库外协议、另行授权或其他版本中的许可。此次没有找到覆盖本项目使用范围的明确许可或书面授权证据，也不据此作出“已授权”或“未授权”的法律结论。

## 状态与后续门槛

冻结配置中两个来源的 `license.redistribution` 均继续为`unknown`，限制仍是仅供本地调查、未经官方中文翻译认证。C1报告仍为136,708字节、SHA-256 `6d28d32b878790bfc0c9dc86cb3676053f296d9c68a5791e4203aa4aaab79d65`，总资格仍为`qualified=false`；没有更新候选CDB、语言记录或报告。

后续若要改变使用或发布状态，须取得并归档可核验的上游许可文本或书面授权，且其范围明确覆盖相关数据、locale、本地使用方式和拟议的分发方式；语义、别名及语言类别仍需独立核验。权利依据未补齐前，候选维持受限本地研究，不进入正式中文检索、自动选择或可分发数据。

本次是来源溯源和状态核对，不是代码测试、翻译审校或法律意见。原单卡审计仍见[44088353来源与使用依据复核](2026-11-03-l1-44088353-source-basis-review.md)。
