# 安全审计与整改记录

本页是本机安全扫描发现及其处置状态的当前事实源。逐次执行证据见[TESTING](TESTING.md)；主机ACL和部署现场见[ENVIRONMENT_AUDIT](ENVIRONMENT_AUDIT.md)与[DEPLOYMENT](DEPLOYMENT.md)。

## 2026-11-11 PR #17限定差异扫描（未完成）

启动Codex Security Diff Scan `613608ec-6e91-4e6e-babc-49afe0bc55e1`，范围固定为`577924bc0c2af06044b77c065eea769c465ff2fe..119797620b42815d7c3e55f4b16f8e0e1be8e3df`，即PR #17最终合并差异，不是全仓Deep Scan。差异共191个文件；按扩展名含44个Rust、15个Python、16个JSON、3个TOML文件，JSON计数包含合同/数据/夹具，不代表源文件审阅数。

只读配置preflight返回`ready`，3项能力检查通过；已保存初步架构模型，覆盖仍为`partial`。`prepare_codex_security_review_items`三次均在读取合并提交blob时失败，错误指向`configs/w1c-analysis.example.toml`；同一仓库中的`git cat-file`和`git show <merge>:configs/w1c-analysis.example.toml`可成功读取该对象。失败发生在变更文件清单生成阶段，尚未开始源代码发现；扫描器当前`findingCount=0`不代表已审查或无发现。保留原scanId和提交范围，不创建替代扫描。若工具恢复，须续接同一扫描；否则将此项作为未完成的独立审阅缺口。

扫描只针对PR差异，不读取或执行部署包，不运行真实worker/ocgcore/FFI，也不验证当前主机ACL。未启动Deep Scan。该状态及调用证据见[2026-11-11验证记录](TESTING.md#2026-11-11-增量工具可用性与旧包探针)。

2026-11-11续查成功读取同一scanId的Codex Security上下文；状态仍为`running / discovery`，未产生发现阶段进度或报告。先前的变更清单生成错误仍是未解决阻塞；此状态读取只证明安全扫描控制面可达，不代表扫描完成或无发现。没有重试清单生成，也未创建新扫描。

## 2026-11-11 ACL只读复核与保留决定

当前`icacls`读数再次确认`D:\`根有直接`Authenticated Users: Modify`并继承到项目；`scripts/deploy-local.ps1`还继承四个未映射SID的Modify ACE。第36–37行复制CLI/worker到旧部署包路径。既有用户决定为保留ACL，本轮遵循该决定，没有修改权限。分诊结论为`needs_review`（medium confidence）：宽泛写权限本身已由当前ACL确认，但其他低权限账户能否访问以及这些账户是否会在更高权限上下文执行该包尚未建立；跨账户影响仍是证明缺口。仓库未找到适用的`SECURITY.md`，边界参考当前部署文档、此前ACL记录和用户的保留决定。复核命令及完整限制见[TESTING](TESTING.md#2026-11-11-acl只读复核与保留决定)；此项不是PR代码Diff Scan的审阅结果。

## 2026-11-11 FFI/HostAck有界源码核对

因扫描器未能生成PR变更清单，另对关键回执路径作只读、定向源码核对：worker端`ffi_call_shared`先发送入口事件并等待绑定attempt/sequence/call ID的HostAck，返回事件使用LIFO栈；host限制帧大小并验证attempt/序号/方向/名称，调用持久回执回调成功后才写HostAck，回执失败、超时或非法帧时终止worker（`crates/ygo-engine-adapter/src/stream_protocol.rs:77-95`、`:197-234`、`crates/ygo-engine-adapter/src/process.rs:458-540`）。workbench回调先追加attempt receipt，再交给adapter继续；result到达时要求没有未决FFI入口且之后不能再有数据（`crates/ygo-cli/src/workbench/analysis_http.rs:218-232`、`crates/ygo-engine-adapter/src/process.rs:609-645`）。该有界源码切片未确认实现漏洞；没有本地重跑测试或运行worker。GitHub `contracts` CI对同一tree的Rust tests/Clippy通过，也不等同完整安全审阅。此核对不替代191文件差异审查；其他文件和调用路径仍未完成扫描。

## 2026-11-11 历史research journal链接发现静态分诊

输入为2026-11-03部分Deep Scan `ec88f465-70e1-478a-a555-f8087bc8a567`及用户截图中“Research journal follows a pre-existing link in its derived …”的低危主张；截图未保留完整标题/occurrence ID。当前静态分诊为`needs_review`、medium confidence，而不是确认当前可利用漏洞。

在已交付的`research-audit`示例路径中，入口从操作员提供的JSON读取账本路径后，先调用`safe_output`；该函数限制目标位于工作区`data/runtime`下，拒绝`..`并检查每个现存路径组件的symlink/reparse属性，再调用`ResearchBatch::open`（`crates/ygo-engine-adapter/examples/research-audit.rs:46-59,259-292`）。`CallJournal::open`也检查账本文件最终组件及派生`.blobs`根和已知子目录；已有测试拒绝预先存在的直接sidecar链接和非目录sidecar（`crates/ygo-engine-adapter/src/journal.rs:204-297,642-645,784-821`；`crates/ygo-engine-adapter/tests/journal.rs:63-108`）。安全策略解析未找到适用`SECURITY.md`；既有扫描威胁模型把独立研究示例视为操作员控制的本机表面，未发现远程入口。

剩余证明缺口：`CallJournal::open`是公开库API，本身不把调用者给定的账本路径限制到`data/runtime/research`或检查全部祖先；其他消费者是否允许低信任主体提供路径尚未确立。静态代码也不能证明目录链接测试在当前Windows账户可运行。并发路径替换的TOCTOU是独立的历史候选，不并入“预先存在链接”主张。下一步应明确公共库调用者的信任边界；在边界确定前，不把示例CLI上的防护外推为所有API调用都安全。

## 2026-11-11 历史Deep Scan五项发现当前源码分诊

对2026-11-03部分Deep Scan `ec88f465-70e1-478a-a555-f8087bc8a567`及用户截图所列五项作有限静态复核；报告目标为`50c279b`且coverage为partial，当前源码为`1197976`。该工作只重验这些历史候选，不是全仓或PR #17完整差异审阅；未运行测试、PoC或应用。截图中前四个标题被截断，未根据标题补造occurrence ID。

| 原始候选（按截图顺序） | 当前静态分诊 | 当前证据与边界 |
|---|---|---|
| 未认证慢速读取可占满workbench连接槽 | `needs_review`，medium，队列排名2 | `workbench.rs`在读HTTP头前计入32槽；绝对期限为15秒，Bearer/Origin在完整头后、body前校验。一个本机进程可以暂时占满所有槽至期限，单连接受限但重复饱和及多用户威胁边界未验证。旧表中的“修复”仅表示加了有界等待，不表示消除槽饱和。 |
| 继承的`Authenticated Users: Modify`暴露可执行文件 | `needs_review`，medium，队列排名1 | 当前ACL复核确认D盘根直接Modify并继承；其他低权限账户能否访问及是否存在更高权限运行场景未证实。用户选择保留，详见本页ACL小节。 |
| caller-controlled Banlist版本可越出快照目录 | `not_actionable`，high | `JsonSnapshotStore::path`将版本限制为单段ASCII标识，不能包含路径分隔符；读写均从固定前缀文件名构造。现有回归夹具覆盖`x/../../…`并验证外部哨兵不变（`crates/ygo-storage/src/lib.rs:53-112`、`crates/ygo-storage/tests/snapshot.rs:19-50`）。根目录配置和独立文件替换竞态不属于此版本穿越主张；本轮未重跑该测试。 |
| Research journal跟随其派生路径中的预存链接 | `needs_review`，medium，队列排名3 | `research-audit`入口对ledger路径逐组件拒绝链接/reparse；`CallJournal`检查直接ledger、`.blobs`及已知子目录。公开库API的调用者信任和路径范围仍未定义，见上一节。 |
| 导入卡名向终端注入控制序列 | `not_actionable`，high | 当前人类可读CLI路径在卡名和步骤标签的报告输出处调用`escape_terminal_controls`；实现把控制字符变成可见转义，现有测试覆盖ESC/BEL/换行及中文（`crates/ygo-cli/src/main.rs:731-769,790-833`）。本轮未执行终端运行时测试。 |

本表是对历史结果的逐项当前源码分诊，不将原扫描的部分覆盖升级为完整安全认证。需要产品/环境边界判断的两项保留为`needs_review`；本机 ACL 的保留决定不等同于认定跨账户风险不存在。

## 2026-11-09 状态复核

本次只读项目路线复核没有运行或启动新的安全扫描。11月5日quota-limited Deep Scan未完成；最近差异扫描为partial，三项本地路径竞态候选仍deferred。D盘ACL仍按用户既有决定保留。默认离线workspace测试通过不覆盖这些安全边界；当前风险与项目路线见[TESTING](TESTING.md)及[路线快照](superpowers/plans/2026-11-09-project-status-and-dual-track-route.md)。

11月5日最终Diff Scan早于main上的W1-C来源/回执代码及Draft PR #17，因此不覆盖这些后续差异。PR集成前按其实际源码变更和路径/进程边界做定向审阅；本记录不把旧扫描结论外推到新代码。

## 2026-11-05 全仓扫描重试未完成

用户提供的扫描界面截图显示：以`622546c`为目标、覆盖731个文件的Deep Scan因Responses API返回HTTP 403 `insufficient_user_quota`，连续3个discovery worker失败后停止；结果为0项。该结果表示扫描未完成，不表示无发现，也没有可恢复的scanId/handoff token。用户要求后续仅在必要时使用Deep Scan，以减少耗时和token开销。

同一改动批次另有最终Diff Scan `c8484c40-59c5-440f-a758-6ad8f94daa01`：17个源码/schema条目审阅完成、0项确认可报告发现，覆盖为`partial`，三项本地路径竞态仍deferred。它与已完成的`50c279b`基线Deep Scan及其修复后定向验证共同构成现有证据；不因Deep Scan配额失败自动重试。若后续代码或部署发生实质性安全相关变化，再按变更风险选择定向审查或扫描。

## 2026-11-05 当前工作树差异审查

Codex Security Diff Scan `08cd98e2-89e5-4903-9544-212440640450`完成了`622546c`之后工作树差异快照`codex-security-snapshot/v1:sha256:7066e237e5b6940d462847261d8c44928b0b64c2f2fd470c9e9c6d5e52047bf5`中17个源码/schema条目的审阅，结果为0项确认可报告发现，覆盖为`partial`。候选验证保留三项待补证路径竞态：

- `attempt_receipts.rs`的路径元数据检查与后续读取/发布之间的本地竞态；
- `process.rs`在worker路径哈希和进程spawn之间的映像身份竞态；
- `identity.py`在来源包构建前后检查之间的bundle路径竞态。

三项均缺少已证明的低权限本地写入者、有效跨账户权限或敏感权限边界影响，因此不升级为已确认漏洞。扫描最终化返回一条可选coverage receipt引用缺失警告；canonical coverage仍保留三项deferred，结论限于部分覆盖，不称为完整认证。当前工作树验证同时修复了Rust回执门禁字符串误分类、Python非字符串枚举/状态异常和`source_bundle_changed`记录验收问题。报告、覆盖和候选验证保存在Codex Security扫描目录中；当前ACL按用户决定保持原样，旧`dist/ygo-local`仍未切换。

最终工作树复核使用Diff Scan `c8484c40-59c5-440f-a758-6ad8f94daa01`，快照摘要`codex-security-snapshot/v1:sha256:6b616d69ff48052c4654288ae6ac762b1f60d7df9a153b102959a1ed8efe610c`。17个源码/schema条目审阅完成，0项确认可报告发现；覆盖标记为`partial`，三项未决候选保持deferred。此次最终化没有coverage receipt警告。它检查了最终差异，但不替代全仓Deep Scan、运行时验收或主机有效ACL审计。

## 2026-11-04 修复后差异复核

Codex Security Diff Scan `cd684777-42da-4fea-ba6c-09a0c54e17b4`于2026-11-04 02:10:50 CST（2026-11-03 18:10:50 UTC）完成，基线为`b35b12dec226b3b71eb36896e27452ec7fd12015`，目标快照摘要为`codex-security-snapshot/v1:sha256:075ae28ff5f8d695acbbdfd151ec8dfb47b1b2ecb91bed516ba7fb90aff461e9`。它检查工作区差异，紧凑代码审阅覆盖4个实现文件，另检查支持测试和选定架构/部署/工作台文档；716是仓库文件清单数，不是逐文件审阅数。扫描没有确认可报告发现，整体覆盖标记为`partial`，不是“全仓无问题”。六个候选中，Banlist路径穿越、HTTP慢请求与终端控制注入因当前整改控制而关闭；另三项保留为未决本地文件系统路径竞态：journal祖先/sidecar路径、Banlist保存前检查与写入之间、Banlist读取前检查与读取之间。尚未证明有低权限本地攻击者能利用这些竞态访问更高权限文件。Windows目录链接测试因错误1314跳过，且没有验证跨账户ACL的有效权限。报告和结构化覆盖清单保存在Codex Security扫描目录中；逐项验证见该报告。

文档校正后又完成Codex Security Diff Scan `4ee4dc69-03f9-4bec-ba82-69dc68ba1db3`，于2026-11-04 02:25:52 CST（2026-11-03 18:25:52 UTC）结束，目标摘要为`codex-security-snapshot/v1:sha256:b4d849be4cf2aeeb294e01251119351d6af8eaeb91eece4dc21e9d7ddde2a0b5`。本次仍为`partial`，没有确认可报告发现，并保留同三项未证实的本地路径竞态候选。扫描纳入工作台/部署文档校正；本扫描结果的记录是在快照封存后追加，代码差异未变。它是本轮最终差异复核，不构成完整仓库安全认证。证据及覆盖限制见对应扫描报告和[本轮测试记录](TESTING.md)。

## 2026-11-04 当前审计

Codex Security Deep Scan `ec88f465-70e1-478a-a555-f8087bc8a567`于2026-11-03 16:19:59 UTC完成，目标为提交`50c279b0605c55f8e1f05240078700d63c01dd9d`，枚举715个非忽略文件。12个独立审阅完成，报告列出5项发现：2项中危、3项低危。扫描只做静态审阅和只读主机ACL检查；报告同时列出未覆盖文件、目录、数据和审计限制。因此以**部分覆盖**记录，不把coverage字段中的`complete`标签解释为逐文件完整审查。

该扫描没有覆盖2026-11-04针对其发现所作的代码改动；修复后的定向及workspace验证见[本轮测试记录](TESTING.md#2026-11-04安全审计整改与workspace复核)。本轮未执行engine、worker、FFI、doctor、研究runner、原生研究或部署；workspace测试可能运行测试专用fixture进程。

| 发现 | 严重度 | 处置 | 边界与证据 |
|---|---|---|---|
| D盘继承的可写引擎/运行资产 | 中 | **保留并记录，未修改ACL** | `D:\`根目录存在`NT AUTHORITY\Authenticated Users: Modify`，继承到项目与本地运行路径；项目父目录/工作区另有四个未映射SID。用户于2026-11-04选择保留现状。账户身份和跨账户有效访问仍未验证。 |
| banlist版本路径穿越 | 低 | 已修复 | `JsonSnapshotStore`现在只接受单段ASCII版本标识，并拒绝符号链接/非普通文件目标。回归确认恶意版本不能越出快照目录，外部哨兵字节不变。 |
| 本机HTTP慢速请求占满连接槽 | 中 | 已修复为有界等待 | 请求头和请求体共用连接接受时建立的15秒绝对deadline；API的Host、Bearer和Origin门禁在读取请求体前完成。32个并发槽仍是固定上限，最多可被慢速合规请求占用至deadline。 |
| 研究账本sidecar跟随链接 | 低 | 已加路径检查 | journal及派生`.blobs`目录、已知子目录和证据文件在打开、创建、读写时检查符号链接/reparse point。相同账户并发替换路径的TOCTOU竞态尚未由句柄级隔离消除。当前Windows账户不具备创建目录链接的权限（错误1314），故动态链接用例跳过；非目录sidecar拒绝测试通过。 |
| 导入卡名终端控制序列 | 低 | 已修复输出编码 | CLI人类可读输出对卡名和步骤标签中的控制字符使用可见转义；机器JSON保持JSON序列化路径。单元测试覆盖ESC、BEL、换行和可打印中文。 |

## 验收边界

- 扫描针对`50c279b`；后续代码修复以当前工作树为准，完整workspace测试、格式和Clippy结果见[TESTING](TESTING.md)。
- Deep Scan和本轮差异复核均不能证明所有被忽略文件、历史运行数据、二进制内容、主机主体或部署资产都安全。未知主体、ACL风险和未做句柄级防替换的journal路径仍需单独处理。
- `dist/ygo-local`仍是旧部署包；源码修复不会自动更新该包。普通工作台仍保持`analysis_not_configured`，产品、研究和发布门禁状态由[TASKS](../TASKS.md)维护。
