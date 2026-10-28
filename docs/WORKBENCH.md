# 本机牌组草稿工作台

工作台提供离线的中文单页界面，用于新建、编辑、保存、重开和导入/导出牌组草稿。它消费`DeckDocumentV1`，允许空/残缺牌组、重复卡号和有序分区；不替代完整牌组合法性检查，也不调用引擎、worker或研究入口。

## 启动与停止

在仓库根目录执行：

```powershell
cargo run -p ygo-cli --offline --locked -- workbench serve
```

服务只绑定`127.0.0.1`，默认使用系统分配的端口。终端输出包含带短期访问令牌的完整URL；在本机浏览器打开该URL。按`Ctrl+C`停止服务。启动实例独占锁定草稿目录；同一目录已有工作台实例时，新实例启动失败。

可选参数：

```text
--drafts DIR      草稿目录，默认 data/runtime/workbench/drafts
--store DIR       快照根目录，默认 data/snapshots
--catalog-id ID   已导入本地catalog快照ID；不提供时卡名未核验
--language-status FILE  C1字段状态报告；只读取状态和哈希，不读取候选正文
--port PORT       固定本机端口；不提供时由系统分配
```

指定catalog时，启动过程通过`SnapshotStore`读取并验证快照。检索只使用该快照的卡号和原始名称；界面始终标示中文译文未核验。未指定catalog也可编辑任意非零u32卡号。

## HTTP接口

API仅为内嵌单页服务。浏览器获得启动令牌后通过Bearer令牌访问API；状态修改还要求同源Origin。服务检查Host为当前`127.0.0.1:port`，不设置跨域许可。请求体上限1 MiB，头部上限16 KiB，读写超时5秒，最多并发处理32个连接。不接受chunked请求。草稿由生成的随机标识寻址，浏览器不能指定本机路径。

| 方法与路径 | 用途 |
|---|---|
| `GET /api/drafts` | 列出草稿ID、标题、分区计数及当前catalog |
| `POST /api/drafts` | 创建空草稿，可提供标题 |
| `GET /api/drafts/{id}` | 读取草稿和内容revision |
| `PUT /api/drafts/{id}` | 以revision做条件更新；陈旧revision返回409 |
| `POST /api/import?format=json\|ydk` | 解析导入内容，返回未保存草稿 |
| `POST /api/export?format=json\|ydk` | 按当前页面内容生成下载，不要求先保存 |
| `GET /api/cards?q=...` | 可选catalog中的卡号或原始名称检索 |
| `GET /api/language-status?ids=...` | 可选C1报告中的逐字段状态；不返回候选译文 |

文件JSON导入支持`DeckDocumentV1`和既有裸`Deck`。YDK只表达分区、卡号和数量，不保留标题。未知卡号及无译文不丢弃；没有catalog时显示名称未核验，检索到本地原始名称时显示来源和中文未核验。工作台不提供分析、自动构筑或已认证中文搜索。

## 保存与本机数据

CLI和工作台复用`ygo-storage`的草稿读写能力。草稿目录含服务锁文件和每个生成ID对应的JSON文档。服务启动时拒绝目录中无法归属到生成ID的JSON文件；ID路径不接受分隔符、点段或任意用户路径。草稿记录内容revision，更新使用进程内互斥及目录单写者锁避免并发覆盖。

新文件以同目录临时文件写入并同步，使用独占发布；目标已存在时不覆盖。替换路径先准备/同步新内容，Windows上保留备份并在失败时尝试回滚；不能确认回滚时返回诊断并保留备份。工作台不提供任意文件覆盖接口。

草稿默认位于忽略的运行目录`data/runtime/workbench/drafts`；需要备份时请停止服务后自行复制该目录。快照仍由已有`data/snapshots`管理。本服务不会修改active快照或部署资产。

## 当前限制

- 中文卡名、别名及正文没有通过C1语义/来源核验；本地snapshot名称不能作为中文资格。
- 可通过`--language-status`显示C1冻结候选的字段状态；状态文件缺失/损坏时继续按未核验显示。报告和使用边界见[LANGUAGE_REVIEW](LANGUAGE_REVIEW.md)。
- 草稿不做禁限、主卡组张数、额外卡组、卡片支持或脚本语义检查。
- 工作台不启动游戏引擎，不规划线路，不自动构筑，也不写研究账本。
- B2验收只覆盖本机工作台流程和合成卡表。它不是通用远程服务或发布部署包。
