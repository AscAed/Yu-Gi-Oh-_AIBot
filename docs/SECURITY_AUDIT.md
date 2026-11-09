# 安全审计与整改记录

本页是本机安全扫描发现及其处置状态的当前事实源。逐次执行证据见[TESTING](TESTING.md)；主机ACL和部署现场见[ENVIRONMENT_AUDIT](ENVIRONMENT_AUDIT.md)与[DEPLOYMENT](DEPLOYMENT.md)。

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
