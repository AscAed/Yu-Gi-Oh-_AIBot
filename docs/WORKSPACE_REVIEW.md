# 工作区自检与维护矩阵

本文件记录2026-10-27及后续接续时的自检范围、证据入口和未完成项，便于代理定位下一步；它不替代[TASKS](../TASKS.md)的当前状态、[TESTING](TESTING.md)的具体验证或[部署说明](DEPLOYMENT.md)。工作区和机器状态会变化；实际操作前应重新核查。

## 对话依据与当前事实

| 对话 | 可复用的信息 | 当前核验及边界 |
|---|---|---|
| 游戏王AI项目具体实施 `01a15239-4096-7ae3-83c0-e7c1e09f365d` | Ground Collapse离线准备完成；实际opcode24提示及响应尚未原生验证 | 当前见TASKS、TESTING和[批次交接](superpowers/plans/2026-10-27-ground-collapse-preparation-handoff.md)；不得据准备报告启动旧scope |
| 游戏王AI总体计划 `01a1502b-111b-7593-b46f-01d00d1e2497` | 局部研究和产品工作台可并行；全卡及全局最优是最终目标 | 当前阶段和依赖见TASKS、[路线图](ROADMAP.md)、[产品愿景](PRODUCT_VISION.md)；旧对话的源码身份不代表当前工作区 |
| 自审1 `01a13678-28ce-7d01-97a1-e7604586db35`、后续计划 `01a1368b-b384-7622-9272-57e20238f6a5` | 已有局部异常报告和符号前沿恢复；真实执行续跑、规则资格和部署验收仍缺 | 旧对话的提交与测试数只属于当时；R1–R5当前状态以TASKS为准 |
| 项目进展汇总 `01a1127d-c3bb-7dc1-985c-def17da10e06`、项目部署 `01a11293-c3bc-7cd2-a372-a3fcccddb106` | M0–M4固定场景的本机搜索、引擎和重放证据；启发式评分、beam和预算有边界 | 现有普通包与开发配置分别核查，不能将早期MVP证据扩展为全卡、通用构筑或最优性 |
| 游戏玩法 `01a08447-1aff-7d20-8b4e-368b6e32658d` | 早期游戏规则、引擎适配与实现背景 | 历史讨论不是当前协议或需求的唯一事实源；以代码、schema与产品愿景核对 |

历史聊天内容可能继续变化；上述读取只覆盖可用的相关近期记录，若需要具体旧决定应按对话分页查原文。

## 自检覆盖与剩余工作

| 方面 | 已取得证据 | 尚缺或限制 | 下一步 |
|---|---|---|---|
| 源码和工作区 | 本轮Git状态可枚举，旧修改和未跟踪文件保留；初始Ground归档603成员及15个引用已核对 | HEAD不代表完整工作区；归档不再等于当前源码，部分必要源码、schema和测试未跟踪 | 保留原改动；交付或提交前按消费者、许可和生成物归属审阅完整状态 |
| 部署与资产 | 普通包与赛事开发配置各一次doctor；普通包的预算受限smoke及独立replay通过，CLI/worker哈希匹配原清单；赛事开发配置固定案例与重放经独立两次请求通过 | doctor自身的`smoke_ok=null`；后续smoke仅针对旧普通包且时间预算截断，赛事为独立开发配置；未验证当前源码的干净双资产部署 | 按P4-R5单独实施并记录资产、构建、重放与身份；不得直接覆盖证据 |
| Rust | 最新工作区fmt、全目标Clippy、串行workspace（331 passed/36 ignored）及adapter examples（52 passed/1 ignored）均通过，日志见TESTING | ignored项和本机资产用例仍不由默认测试证明；未做最新源码部署 | 提交前确认暂存内容与已验证源码一致；生产引擎实验遵守新scope和预算 |
| Python和CI | Python 3.12.13隔离干净源码副本全套729 passed/24 skipped；CLI样例校验通过。语言审计边界聚焦13 passed/4 subtests | 24项因Windows符号链接、本机历史材料/基线缺失和显式资产/报告opt-in跳过；忽略的本机证据不会出现在干净checkout | 提交前确认Python代码、测试和配置未偏离快照；保留跳过项与所需证据说明 |
| 清理和兼容 | 删除229个空临时目录和本轮隔离Cargo缓存；两项冗余直接依赖移除；交付前复核修复语言审计schema输入边界和v1–v5事件兼容 | 有85处访问错误、未去重硬链接，扫描时存在并发写入；crate内历史测试ledger保留待迁移清单；`.venv`缺少pip/pytest | 对后续候选先查引用、内容和保留用途；完善证据保留清单和临时产物生命周期 |
| 文档 | INDEX提供单一事实源导航；TASKS和TESTING原文按字节保存历史快照，入口保留历史锚点 | 历史文件及忽略目录证据不能视为干净checkout自动具备；当前链接检查不证明语义或远端可用 | 保持历史快照原样；核对内容一致性、包装链接和新证据的可获取性 |
| 产品和研究 | 当前P0–P8、R1–R5、研究资格和未知消费分别有事实源 | 未交付通用工作台、全部规则资格、全卡覆盖及最优性证明 | 按TASKS的独立任务推进；研究、产品交付和资格分别验收 |

## 操作和证据约束

- `data/runtime/`、`target/` 中的报告、归档、账本、日志可能是不可重建证据；删除或迁移前必须确认引用、保存策略和身份。历史失败不由后续成功覆盖。
- 已暂停批次的窗口及预算不自动复用；doctor的worker ABI探针与研究scope调用分别记录。实际部署、smoke、原生研究与纯静态检查的副作用不同。
- 每次验证注明源码或包身份、命令、环境、结果、跳过原因和实际覆盖。相对链接可用不证明链接内容正确，也不证明被忽略的本机资产在其他checkout存在。
- 网络命令在同一次终端调用内设置项目要求的本机代理；当前步骤及人类决策遵循[AGENTS.md](../AGENTS.md)和用户指令。

接续检查点见[暂停交接](HANDOFF_2026-10-27_WORKSPACE_AUDIT.md)。该交接是暂停时快照；执行前以本文件与TASKS/TESTING及实际工作区交叉核对。

## 2026-10-28 PR #3合并后的整合自检

- 起点为PR #3已合入的`main` `fc7b177`。保留D盘原工作区不动，在独立工作树移植C1/A3已有修改并重跑Rust格式、Clippy及全workspace测试：357 passed、36 ignored、0 failed；Python语言/schema聚焦为23 passed、2 skipped。完整证据和解释器边界见[TESTING](TESTING.md)顶部。此次没有运行本机引擎、doctor、正式部署或研究scope。
- 实际普通包`dist/ygo-local`中的CLI与worker时间戳为2026-10-19；`build-hashes.json`与包文件一致，但包明显早于当前源码。保留包和历史验收报告，没有重建或覆盖；最新源码的双资产干净部署门禁仍未通过。
- 本轮没有发现可以在不破坏兼容合同、历史追溯或忽略目录证据的前提下安全删除的旧模块。版本化v1–v5路径、历史计划/报告及被忽略的账本/运行证据有明确消费者或保留用途；Cargo未安装`cargo-machete`，没有联网安装依赖。后续若清理，应先建立文档中的证据迁移清单并逐项验证消费者。
- 旧Tenki保护源哈希失败仍为已知未解决项；未改保护哈希或关闭校验。新添文档、schema和报告链接应继续区分仓库内源码目标与不会进入干净checkout的本地`target/`、`data/runtime/`证据路径。

## 2026-10-28 PR #4合并后续接与P4-R1b变更自检

- 远端`origin/main`已刷新并确认PR #4合并提交`84c8c5567968bf2dcb8cc2c0b2140f4490c6ea01`。在该基线建立独立审计分支；原D盘工作树存在多组未提交改动且分支落后于main。逐文件比较后仅移植R1b planner、schema、交接及状态文档；没有覆盖原工作树，也没有把其中移除`state.loading`互斥的旧版工作台文件带回，因此保留PR #3的导入期间编辑锁定修复。
- R1b新增版本化外层执行游标及逐步推进/查询审计API。最新离线复验为`cargo fmt --all -- --check`通过、workspace全目标Clippy通过、串行workspace测试**358 passed、36 ignored、0 failed**；Python语言/schema聚焦**24 passed、2 skipped**。测试使用隔离`target/full-project-audit-20261028`，日志只在本机忽略目录内，不是干净checkout中的永久证据。pytest有一个Windows临时缓存目录访问警告；测试退出码为0。
- 当前D盘`dist/ygo-local`中`ygo.exe`与`ygo-engine-worker.exe`时间戳为2026-10-19，实际SHA-256分别匹配同目录manifest；这确认包体与清单一致，但不证明包由2026-10-28源码构建。未覆盖冻结包或重建引擎。最新源码干净checkout双资产部署、进程级暂停/重开、非空多动作恢复等价测试和独立原生重放仍未通过/完成，继续按TASKS开放项处理。
- CI的`actions/checkout@v4`与`actions/setup-python@v5`曾触发Node 20弃用迁移提示；workflow现升级到官方Node 24兼容的[checkout v7](https://github.com/actions/checkout/releases)和[setup-python v7](https://github.com/actions/setup-python/releases)。托管runner实跑留给PR CI确认，未把本地Rust/Python结果当作GitHub Actions结果。
- 对112篇已跟踪Markdown作相对路径存在性扫描：676个仓库源码目标无缺失；另有69条`target/`、`data/runtime/`或`data/tmp/`本机证据路径不属于干净checkout源码目标，扫描未验证锚点或目标内容。`cargo tree --workspace --duplicates --offline --locked`仅见由`rusqlite/hashlink`与`toml/indexmap`依赖路径带入的`hashbrown` 0.14/0.17并存；未发现可直接删除的重复crate，`cargo-machete`当前未安装。
- 本次静态核对未发现可以安全移除且无兼容/历史证据消费者的模块。v1–v5协议路径及本机历史账本、报告和日志按现行合同保留；本轮新增隔离Cargo构建目录和日志承担验证证据用途。清理候选仍需先核对消费者、来源和保留策略，不把忽略目录当作垃圾目录批量删除。

## 2026-10-28 恢复修复提交后的自检续记

- 本次续接起点为隔离分支`codex/r1b-semantic-resume-tests-20261028`上的`30c1018`，相对`origin/main`领先1提交且工作区干净。该提交修复重开后内外层恢复检查点未同步，并已完成本地格式、Clippy、planner及workspace验证，结果见上方TESTING与P4-R1b交接；由于跨提示多动作恢复和收费边界中断注入仍开放，未创建PR或声称本阶段验收完毕。
- 再次读取普通发布包的`ygo.exe`与`ygo-engine-worker.exe`，两者SHA-256仍匹配`build-hashes.json`，包内二进制时间戳仍为2026-10-19。未覆盖或运行旧包；它与自身manifest一致不证明由最新源码构建。
- 对D盘旧工作树只读复核发现分支落后于`origin/main`且存在大量本地修改。相较当前主线，其中工作台脚本移除了`state.loading`期间的互斥，CI将checkout/setup-python action降回旧版本，语言测试也删除输入变化回归。该目录保持原样；这些变更不应直接并入或提交，当前隔离分支已保留主线的导入锁定行为。
- Windows消费预留路径保护测试文件全套为11 passed、1 skipped、17 subtests passed；系统策略不允许创建目录符号链接，故对应负例跳过。Git身份路径测试为11 passed、4 subtests passed。pytest缓存改放系统临时目录后无缓存权限警告。`cargo tree --workspace --duplicates --offline`复查仍只显示上文所列的传递依赖版本并存，未发现可直接删除的重复依赖；`cargo-machete`不可用，未安装额外工具。

## 2026-10-28 恢复边界复验与历史证据链接盘点

- 本轮起点为提交`b26e4a8`（基于`origin/main`的`2389906`），工作树干净。恢复循环合成故障注入覆盖意图已持久化但尚未收费的恢复清理，以及Execution结果已写入journal/内层检查点、外层pending快照尚未发布时的认证对账；后者恢复到QueryAudit且消费仍为2。planner套件70 passed/9 ignored；workspace串行总检362 passed/36 ignored；workspace全目标Clippy、fmt及`git diff --check`通过。新增测试不运行引擎、worker、doctor或研究scope。
- 工作台异步边界静态复核：保存时控件锁定；`openDraft()`和`importFile()`在首个await前设置`loading`并在`finally`释放；`changed()`先同步重绘再异步查卡，避免移除按钮沿用旧数组索引；导出API显式请求Blob。`node --check crates/ygo-cli/src/workbench/app.js`通过，workspace中的4个`workbench_http`集成测试通过。没有运行真实浏览器交错时序测试；此检查不能证明浏览器层全部竞态已排除。
- 最新隔离源码Release构建使用`cargo build --release --workspace --offline --locked --target-dir target/p4-r1b`通过。HEAD `c34a505042a634c71c2969239af404d825a7bfe2`产物CLI/worker哈希分别为`366956120B0C7DBBE951847ACA297FB7AD0E03496143C3A87335A749404FCBD3`和`CF2B235DE7897727EE1BFACE24BCCABF293E986ED2BB69120CD47BCB50E02DDD`。隔离工作树没有冻结运行资产，故本批只证明Release可构建，不运行doctor/worker/决斗，不构成部署验收；原D盘旧包保持不变。
- 对112篇跟踪Markdown重新扫描本地相对链接：当前隔离worktree内有68个目标缺失，其中19条指向`data/runtime/`证据，49条指向`target/`日志/产物；逐项映射到原D盘工作区后，68/68目标仍存在。此结果表明隔离worktree不是这些历史证据的自包含副本，不代表原工作区证据丢失。当前没有迁移、复制或删除它们；下一步须按消费者、身份绑定、重建性与保留策略逐项建立可恢复归档，再调整链接。
- 该扫描只检查Markdown链接目标存在性，不验证锚点、内容哈希、证据是否过期或目标是否应公开；之前记载的源码目标数和分组统计来自不同扫描快照，应以对应日期范围理解，不把这次结果外推为全部证据验真。
- 随后修正证据保留清单中的分组标题笔误：实际为`data/runtime/` 11项、`target/` 35项，共46个目标。只读重查原D盘工作区后46/46存在且被Git忽略；目录展开并去重为54个文件、750,733字节。逐文件哈希清单写入当前隔离worktree的忽略文件`target/evidence-retention-source-20261028.json`，回读重算54/54大小和SHA-256均匹配。用户选择暂不迁移，因此没有复制或移动历史证据；哈希文件不属于提交内容。
- 路径相关复验：`tests/test_curry_consumption_reservation.py`为11 passed、1 skipped、17 subtests passed；跳过仅因当前Windows策略禁止创建目录符号链接，不能据此声称特权链接负例通过。`tests/test_prepare_curry_ledger_handoff_v5.py`为5 passed。两者pytest缓存目录均遇到访问拒绝警告，测试退出码为0。
- 历史审计`test_writer_is_exclusive_and_does_not_start_processes`尚未运行。该用例会在原D盘`recovery-2026-10-21`目录创建后删除测试报告；对其父历史树的递归枚举至少见约12.3GB文件，但因临时子目录访问拒绝，此数值不完整。为避免向原证据树写入，也遵从用户暂不迁移的选择，本轮未运行此用例或复制该历史材料；需有安全隔离的最小输入或用户另定方案后再验。
- 续接分支的本地修复/文档提交未推送：终端Git推送缺少GitHub凭据，GitHub连接器创建分支也返回Authentication Failed。当前离线提交和测试状态保留在隔离worktree；没有创建新PR或合并。真实进程/最新源码部署门禁继续以[TASKS](../TASKS.md)为准。
- 随后在提交`27ab161`的干净worktree上重建隔离包，重新smoke/replay仍为318节点及3/3通过，包内TESTING文档哈希匹配源码。初次部署遗漏的25个公共Lua脚本已补齐，源/目标共12,727个脚本SHA-256一致。旧CLI不支持identity命令；共用核心/DLL/script/CDB/LFLists资产、catalog/banlist状态及Rabbit合法性只读比较一致，但CLI/worker哈希不同且没有可比研究账本，完整跨版本等价继续未知。原D盘旧包保持2026-10-19且未改。完整命令、失败修复经过和限制见[TESTING](TESTING.md)。
