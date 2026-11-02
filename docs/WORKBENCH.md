# 本机牌组草稿工作台

当前工作台状态与分析恢复门禁见[TASKS](../TASKS.md)和[TESTING](TESTING.md)。H3.2-2a、2b-1四个限定进程终止窗口及2b-2 accepting保存后冻结前窗口已验收；其余2b窗口/调度、syscall/断电/介质故障及W1-C真实分析仍开放。普通启动保持`analysis_not_configured`。以下历史段落保留原时点。

历史状态（H3.2-1交付时）：已实现共享跨链认证、全候选验证后提交及重复重开；当时H3.2-2响应丢失和目标窗口强杀仍开放。后续2a和当前开放门禁见本文顶部与[当前任务](../TASKS.md)。验收范围见[H3.2-1交接](superpowers/plans/2026-11-01-w1h321-recovery-handoff.md)。

H3.1仅设计交付：[跨链恢复与响应丢失设计](superpowers/plans/2026-11-01-w1h31-cross-chain-recovery-design.md)、[交接](superpowers/plans/2026-11-01-w1h31-recovery-design-handoff.md)。现有跨链认证/分类可复用；新增完整恢复与响应丢失矩阵尚未实现／尚未运行，留待H3.2。普通启动仍为`analysis_not_configured`。

H2.2-A/B所列合成HTTP验收已关闭，但普通启动仍未配置分析后端，真实分析与H3开放。取消先完成的顺序分支有既有用例，16轮并发竞争均由claim获胜；早期TCP重置根因未知。

当前HTTP v1源码包含六个分析端点及无路径DTO；H2.2-A/B及H3.2-2a、2b-1、2b-2 accepting-before-freeze限定合成验收已通过。普通`workbench serve`未配置分析后端，分析请求返回`analysis_not_configured`，网页没有任务操作界面。H3.2-2b其他窗口/调度、W1-C真实分析和P4-R5仍开放；接口见[HTTP合同](WORKBENCH_ANALYSIS_HTTP.md)，实现与证据见[H2.2交接](superpowers/plans/2026-11-01-w1h22-analysis-http-handoff.md)、[TESTING](TESTING.md)及[2b-1交接](superpowers/plans/2026-11-01-w1h322b1-process-kill-handoff.md)。

工作台提供离线的中文单页界面，用于新建、编辑、保存、重开和导入/导出牌组草稿。它消费`DeckDocumentV1`，允许空/残缺牌组、重复卡号和有序分区；不替代完整牌组合法性检查，也不调用引擎、worker或研究入口。

W1-A冻结对象仍仅驻留内存，包含本机路径及完整catalog，不实现序列化；B1持久化的是独立无路径任务记录。B3另有内部任务revision存储、私有报告文件和持久先行协调器，并在claim时核对冻结资产角色哈希。草稿目录存储与分析任务存储是不同子系统；实际执行接入仍需在调用边界再次核验资产。

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

API仅为内嵌单页服务。浏览器获得启动令牌后通过Bearer令牌访问API；所有API非GET请求（包括分析任务DELETE）在路由分派前都要求精确同源Origin。服务检查Host为当前`127.0.0.1:port`，不设置跨域许可。请求体上限1 MiB，头部上限16 KiB，读写超时5秒，最多并发处理32个连接。不接受chunked请求。草稿和分析任务由服务生成的随机标识寻址，浏览器不能指定本机路径。

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

文件JSON导入支持`DeckDocumentV1`和既有裸`Deck`。YDK只表达分区、卡号和数量，不保留标题。未知卡号及无译文不丢弃；没有catalog时显示名称未核验，检索到本地原始名称时显示来源和中文未核验。自动构筑和已认证中文搜索也未提供。

分析端点完整请求/响应合同见[分析HTTP v1合同](WORKBENCH_ANALYSIS_HTTP.md)。

## 分析 HTTP 接入与运行状态

H2.2源码实现六个端点：分配/提交/查询操作、查询任务、读取结果及取消排队任务。提交先持久保存`accepting`再返回202，后台锁外完成W1-A冻结；结果经无路径白名单投影，历史读取使用已认证的持久记录。完整请求/响应合同见[WORKBENCH_ANALYSIS_HTTP.md](WORKBENCH_ANALYSIS_HTTP.md)。

当前普通启动没有配置分析协调器，以上端点返回`analysis_not_configured`；测试专用合成服务不构成生产分析后端。真实分析、报告来源认证及H3.2-2b其他窗口/调度仍开放；逐syscall、断电和介质故障未认证。H2.2-A/B、H3.2-2a、2b-1与accepting-before-freeze已覆盖范围见[验收记录](TESTING.md)。任务进程内冻结对象含本机路径与完整catalog，不可直接序列化；报告引用和合成状态也不表示真实执行。部署包状态见[DEPLOYMENT.md](DEPLOYMENT.md)。

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
