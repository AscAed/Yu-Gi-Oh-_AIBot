# 本机环境与资产审计

## 当前现场（2026-11-03）

本轮可执行代码审计基线为`main` / `50c279b0605c55f8e1f05240078700d63c01dd9d`；该验证时点工作树干净，较`origin/main`领先13个本地提交。后续仅补充审计文档，未改变可执行代码。Codex Security差异扫描 `e230fb47-c1cf-4f21-a4d6-edd97e12c61e`关闭25/25审阅项，覆盖范围明确为diff/partial。全仓Deep Scan原执行句柄`214`于2026-11-03恢复时返回`not found`。用户随后提供的界面截图显示条目“Yu-Gi-Oh!_AIBot · 11月3日 16:10”针对提交`50c279b`扫描全仓715个文件；截图时处于第8轮汇总，9项已完成、4项进行中。该截图只证明当时仍在运行；没有提供该扫描的`scanId`/handoff token或最终报告，用户确认没有续接凭据，因此当前状态和最终结果无法核验，不记为完成或通过。按扫描协议，不以新扫描替换缺少恢复上下文的任务。差异扫描记录1项低严重度本机权限问题。`dist/ygo-local`仍为2026-10-19旧包，`build-hashes.json`只记录CLI与worker哈希且与当前文件匹配；包内没有`manifest.json`，该结果只证明旧包文件与自身清单一致。W1-C隔离候选另完成一次固定Rabbit有限分析，结果为`budget_limited/time_budget`；它没有部署进普通包，P4-R5仍开放。

只读ACL复查把权限来源追到`D:\`根目录：`NT AUTHORITY\Authenticated Users`在该卷根上有直接`Modify` ACE，并继承到`D:\PUBLIC`及下层项目文件。`D:\PUBLIC\Program\AI\Yu-Gi-Oh!_AIBot`父目录还有两个无法映射到当前本机账户名的显式Modify SID；工作区再有两个此类显式SID，另继承父目录的两个SID。当前令牌是标准用户`LAPTOP-7SAI5TBV\AscAed`；本机账户枚举受拒，且四个SID在ProfileList中均无账户配置文件记录，无法确认对应主体。`.git`对这四个SID另有显式写入/删除Deny ACE，同时继承Authenticated Users的Modify；未评估任一具体账户令牌的有效访问结果。项目父目录含两个兄弟工作区，因此修改父级ACL会影响兄弟目录；删除卷根ACE则会影响D盘其他内容。配置仍指向包内worker及`data/runtime`中的引擎资产。源码hash只绑定所选文件，不证明文件由可信主体发布。普通工作台保持`analysis_not_configured`，检查时没有观察到`ygo`进程。用户于2026-11-03选择保留当前ACL并记录风险，本轮未调整权限。详细部署界限见[DEPLOYMENT](DEPLOYMENT.md)。

### 组件与依赖复核

- 没有发现可依据源码消费者和历史证据安全删除的源码模块、运行组件或兼容路径。2026-11-03只清理了11个逐一核验、仅含可重建Cargo `debug`构建输出且不含日志、状态、manifest、研究证据或资产的缓存目录：118,131个文件、81,243,791,398字节（75.664 GiB逻辑大小）。保留其余`target/`内容、`data/runtime/`、`dist/`、release产物和兼容路径；Markdown中的忽略路径和缺失目标集中登记于[EVIDENCE_RETENTION](#ignored-evidence-links)。
- 清理后可访问的`target/`文件清点为1,086,097个文件、36,348,084,528字节（33.852 GiB逻辑大小）；排除了1个目录联接，受ACL保护的Python依赖子树无法枚举且未触碰。逻辑大小不等于NTFS实际占用或可回收空间。该批清理期间D盘可用空间增加77,289,877,504字节；记录和11个精确路径见忽略文件`data/runtime/cleanup-audit/target-build-cache-cleanup-20261103-220156.json`。
- 对9个Rust crate逐项扫描直接依赖的crate标识符，覆盖该crate下的Rust源码、测试和示例；每个直接依赖至少有一个文本引用，没有发现零引用候选。该词法筛查不证明运行时实际使用，也不替代专用未用依赖分析器。`cargo-machete`、`cargo-audit`和`cargo-deny`未安装。
- `cargo tree --workspace --duplicates --offline --locked`显示两个`hashbrown`版本：`0.14.5`经`rusqlite 0.32.1`/`hashlink`引入，`0.17.1`经`toml 0.8.23`/`toml_edit`引入。它们来自不同传递依赖约束；未作强制覆盖或升级。
- Python的`pyproject.toml`只声明`jsonschema`运行依赖及可选`pytest`测试依赖。文件名盘点未发现`setup.py`、`setup.cfg`、`requirements*.txt`、`Pipfile`、Poetry、tox或Travis旧式配置；`pip-audit`、`bandit`、`semgrep`和`ruff`未安装，因此未完成外部漏洞库扫描或这些工具的专项检查。

## 历史现场（2026-11-02）

2026-11-01 WinDirStat截图估算项目约312.3 GB，其中`target/`约199.2 GB、`data/runtime/`约112.6 GB。`target/p4-r5-current-a21d587/data/runtime`是指向主`data/runtime/`的目录联接，清理扫描排除此联接，避免重复计量。保留当前P4-R5候选、全部release目录、`dist/ygo-local`、可执行文件、引擎与卡库资产、报告、账本、脚本和图片。2026-11-02流式只读扫描显示`target/`逻辑大小20,237,986,969字节（889,994个文件）、`data/runtime/`为11,462,519,359字节（98,514个文件）、`data/tmp/`为190,719,560字节（5,756个文件）。扫描排除1个已知目录联接；`target/`有28个、`data/tmp/`有14个受保护目录无法枚举，均属于保留的Python/pip依赖临时目录，故这些逻辑体积是可访问文件统计。WinDirStat仍开着原D盘视图，但本次桌面截图通道超时，未能用同一工具完成清理后复测；以上是流式文件扫描结果，不等同NTFS去重后的可回收空间，也不应冒充WinDirStat结果。D盘当前可用307,274,039,296字节；相对清理前21,336,346,624字节的卷级净变化为+285,937,692,672字节，期间可能包含其他卷活动，不能单独归因于项目清理。

按SHA-256清单移除了441,183个可访问的Cargo编译缓存路径（逻辑大小303,919,886,861字节）：`debug/incremental`内容，以及debug树中的`.pdb`、`.o`、`.rlib`和`.rmeta`。候选哈希无计算错误；66个访问拒绝路径未纳入首轮清理。清理前记录D盘可用21,336,346,624字节，完成后304,439,128,064字节，净增加283,102,781,440字节。该数字是期间D盘卷级净变化，包含审计清单占用，也可能包含其他卷活动；不能单独归因于清理或视为精确回收量。逻辑候选文件大小303,919,886,861字节，去重文件身份后为177,647,380,688字节，二者范围不同。逐文件清单、摘要、失败路径和操作日志位于忽略目录`data/runtime/cleanup-audit/`。删除脚本末尾因读取旧摘要字段报错；随后逐项检查441,183条路径均已不存在，并将核对结果写入审计日志。

同日清理`data/tmp/`中由测试源码按随机ID/进程ID/时间戳生成的日志、journal与blob：逐项检查源码生成方式、未发现运行中的测试进程、哈希清单记录95,295个候选文件（233,006,654字节），预检元数据和哈希一致后逐文件删除；另非递归移除9,585个空目录。随后对遗留的1,847个`journal-test-*`目录树作只读递归复查，确认7,281个子目录为空且无重解析点后，另非递归移除共9,128个空目录。删除清单及SHA-256、操作计数保存在忽略审计目录。`data/tmp/`仍有5,756个文件（190,719,560字节），包括离线构建依赖、源码和历史输出，均保留。

首轮受ACL保护的66个目录路径在只读提升权限复查后，39个为空且无重解析点的目录已逐个移除，27个Python测试依赖目录（约16 MB）保留；未改ACL。另对`target/curry-recovery-synthetic-e2e-tests/`中643个由测试按UUID创建的临时根目录进行逐文件SHA-256清单核验。清单含763,059个文件、1,817,135,459字节、120,072个子目录，SHA-256为`60F8911BE425F0AEACD508C4E0B3348E224EBF06636888FD58A53A00FB7A2567`，扫描无错误/重解析点。首轮删除762,444个文件后，615个只读`.git/objects`因ReadOnly属性未删；逐项复核哈希、大小和时间戳后清除这615个文件的ReadOnly属性并删除，未改ACL；合计1,817,135,459字节文件均已删除。共移除120,072个清单目录及643个已确认空的UUID根目录，最终UUID根目录残留为0。命名证据目录和根级日志保留。逐文件清单、删除回执和操作事件在忽略审计目录。

证据保留清单中的54个唯一源文件中，51个非空文件（750,733字节）已上传至仅所有者可访问的Google Drive归档并逐个回读校验字节数及SHA-256，随后删除本机原件；3个零字节日志保留原位。5份重试产生的重复云端副本已清除。映射索引在忽略目录`data/runtime/cleanup-audit/drive-archive-index.json`；没有向公开GitHub仓库上传文件。完整处置见[证据保留清单](EVIDENCE_RETENTION.md)。

## 当前现场（2026-11-01）

当前checkout为本机`main / 2f690d5`，工作区有未提交修改；本批没有部署。普通`dist/ygo-local`仍是2026-10-19旧包；`target/release`对应CLI/worker与dist二进制为相同哈希的Windows硬链接，不证明当前HEAD已构建。隔离候选`a21d587`及更早`e684f4e`各自的验收不等同当前部署；smoke受预算截断且缺少可比账本，P4-R5仍开放。历史证据按用户决定不迁移，仅保留哈希清单，不代表已有备份。现场和历史证据见[TESTING](TESTING.md)、[DEPLOYMENT](DEPLOYMENT.md)和[TASKS](../TASKS.md)。

2026-11-01清理：删除被忽略的`configs/engine.toml.legacy`（258 bytes，SHA-256 `D2F51D7C826A35F8A2B595C063045500C903F69B7DE25E2B82FF2BC9BFB0876D`）。它使用旧EDOPro进程字段；当前`ProcessEngineConfig`启用`deny_unknown_fields`且要求worker/ocgcore等字段，既有`config_round_trip_and_legacy_gui_config_rejected`测试确认旧`engine_path`配置会被拒绝。源码与脚本中无消费者，文件命中忽略规则`/configs/engine.toml.*`。当前`configs/engine.toml`保留不变。此为本机失效配置清理，不涉及运行资产、兼容协议或历史研究证据。

以下段落记录各日期/提交的审计快照；其中的“当前”“本轮”均指原记录时点，不覆盖上面的现场摘要。

### 历史快照（2026-11-01，main / 8d8c492）

当时主工作区为`D:\PUBLIC\Program\AI\Yu-Gi-Oh!_AIBot\Yu-Gi-Oh!_AIBot`本地`main`；`C:\Users\AscAed\.codex\worktrees\p4-r5-audit\Yu-Gi-Oh!_AIBot`是仍保留的`e684f4e`隔离候选worktree，PR审查worktree也单独保留。两者不应当作当时主源码。GitHub连接器在2026-11-01确认远端`main`为`577924b`；当时本地主分支基线`8d8c492`领先6个提交。历史证据不迁移，原SHA-256清单保留且不代表已有备份。

### 历史快照（2026-11-01，main / a21d587源码与普通dist核对）

本轮源码位于本机`main / a21d587`，仓库提交后干净；普通`dist/ygo-local`中的`ygo.exe`、`ygo-engine-worker.exe`、`ygo.cmd`、`build-hashes.json`及包内测试/配置文档时间均为2026-10-19。H2.2源码提交晚于该包且没有部署重建，因此当前checkout包含的HTTP源码不能推断为已部署能力。未运行旧包doctor、smoke或真实分析，也未改写dist；既有旧包诊断和候选部署证据按其历史提交/资产身份保留在下文和[TESTING](TESTING.md)。

依赖复查仍未证明存在可安全删除的重复直接依赖或未用crate：9个workspace成员保留，两个`hashbrown`版本属于不同传递链；本机没有`cargo-machete`。忽略的`configs/engine.toml.legacy`不是运行配置，含机器路径且没有代码/文档消费者；因其可能承担人工回滚用途，暂保留并在[TESTING](TESTING.md)记录。没有删除crate、兼容解析或历史证据。

2026-11-01提交`e684f4e`已在隔离worktree离线构建并完成普通/赛事资产doctor、身份和诊断smoke/replay；smoke受30秒预算限制，P4-R5发布验收仍开放。普通主工作区dist仍为2026-10-19旧包，未切换。历史证据按用户决定不迁移，仅保留原哈希清单；清单不等于备份。当前候选证据见[TESTING](TESTING.md)。

早期2026-10-31本地环境审计快照基于`main / 8526c1f`：普通旧包和赛事配置doctor均ready；`dist/ygo-local`仍为2026-10-19包。之后的候选源码部署复核见本页补记及[TESTING](TESTING.md)。赛事配置worker路径复用普通dist worker。历史证据哈希清单不是备份；Windows目录符号链接实测仍受系统策略限制。

2026-10-31 W1-B3内部持久协调、claim资产哈希门禁及故障矩阵仅在当前开发工作区验证；未部署、未在最新源码上运行doctor或smoke，也未改变环境资产。最新源码双资产验收仍按P4-R5开放项跟踪，见[TASKS](../TASKS.md)及[TESTING](TESTING.md)。

2026-10-30静态核对的历史基线为`main / d3bc212`；旧普通包CLI/worker哈希与清单一致、主要配置路径存在，当时未运行程序。2026-10-31普通包及赛事资产配置doctor在较早的`main / a8d6356`源码时点分别返回ready；随后文档与CI触发范围更新随PR #14合入`main / 4869393`，合并检查全绿。PR #14未重建或切换部署资产，因此这些doctor结果不代表当前源码已部署。P4-R5最新源码双资产发布验收仍开放。此前`8315232`为W1设计阶段历史基线，见[W1-A后路线](superpowers/plans/2026-10-30-post-w1a-project-route.md)。

原目录体积审计日期：2026-10-19；这些数值会随实验和构建变化。2026-10-27自检分别对普通包和赛事开发配置运行doctor，并清理经逐项确认的空测试目录。2026-10-30仅对保存的部署/CI证据及源码实现作静态复核，没有重跑运行时命令。下方日期段落保留各自时点的环境状态；2026-10-28已由开发CLI交付本机loopback草稿工作台，不能再将旧段落的“尚无前端/HTTP”当作当前状态。本页不包含卡库或引擎资产本体，精确证据见[TESTING](TESTING.md)。

后续首批基线实施新增忽略目录`data/runtime/baseline-2026-10-19/`，包含固定上游数据调查、双资产清点、中文候选、原生批账本/blobs和身份/构建记录。这些是证据，不是纯缓存；旧版或损坏的中间报告也保留，当前使用的报告文件由TESTING明确指定。开发构建与原生运行已分开执行，普通dist及active快照不在本批切换范围。上文旧体积不代表新增后的总占用。

## 当前目录分层

| 路径 | 观察到的内容 | 处理原则 |
|---|---|---|
| `crates/`, `python/`, `schemas/`, `scripts/`, `tests/`, `knowledge/`, `configs/` | 源码、数据工具、合同、构建脚本、夹具和知识包 | Git 管理；禁止混入本地运行产物或机器绝对路径 |
| `data/runtime/` | 2026-11-02可访问逻辑统计11,462,519,359字节、98,514个文件；含CDB、ocgcore/Lua、清单、历史原生报告、快照及实验输出 | 本机忽略数据。不是纯缓存；删改前查验收报告/内容寻址账本引用并先备份 |
| `data/tmp/` | 2026-11-02可访问逻辑统计190,719,560字节、5,756个文件；另有14个受保护pip临时目录无法枚举。保留LFLists/core源码和Python构建工具缓存 | 忽略目录但混合了离线构建依赖和诊断证据。只允许按测试生命周期清理可确认临时项；保留固定上游checkout和构建缓存供离线构建 |
| `data/snapshots/` | active 指针与内容寻址的卡库/禁限表 JSON 快照 | 本机数据；不可与版本库快照混淆，不应在一般清理中移除 |
| `data/raw/`, `data/normalized/` | 目前只有 `.gitkeep` | 可再生成工作区，不代表受许可卡库可公开提交 |
| `target/` | Rust 编译缓存及独立测试目录；其中还保存原始日志、源码归档、清单和交付证据 | Cargo 编译缓存可重建；历史日志、归档和交付证据不能靠重编译恢复。禁止整体清除，先核对各批引用与保留需求 |
| `dist/ygo-local/` | 本机CLI/worker/fixture/schema和绝对路径配置；2026-10-19重建 | 2026-10-27包内二进制与清单哈希一致，doctor就绪；不证明最新工作区的干净构建，不含独立赛事资产 |
| `.venv/` | 本地 Python 3.14.7 环境，可启动解释器，但检查时未安装 pip 或 pytest | 保留原位；不能假定该环境可执行完整测试。系统Python及独立3.12测试环境分别记录 |

本节`data/runtime/`和`data/tmp/`体积为2026-11-02流式扫描可访问文件的逻辑大小；`target/`、`data/tmp/`存在ACL保护目录跳过，且逻辑字节未折算NTFS硬链接/稀疏文件占用。不要将逻辑统计当作卷级实际回收量或精确配额。

## 2026-10-30 pytest默认收集边界

`pyproject.toml` 将默认 `testpaths` 固定为 `tests/`，缓存仍写到忽略的 `target/pytest-cache`。修复前从仓库根目录直接运行 `py -m pytest` 会继续递归扫描忽略的 `data/runtime/`，在受ACL保护的测试临时目录触发512个collection权限错误并停止；不是512个断言失败。修复后默认collect-only只发现`tests/`的767项，未进入runtime。完整用例仍须单独查看[TESTING](TESTING.md)的本轮结果；被保护的历史材料保持原位。

## 2026-10-31 普通包现场诊断

当时源码基线为`main / a8d6356`，普通`dist/ygo-local`仍是2026-10-19本地包。普通包及`data/runtime/tournament-2026/engine.toml`赛事配置的现场doctor均退出0并返回`ready=true`、`abi_ok=true`、`assets_ok=true`、`issues=[]`、`smoke_ok=null`。普通包CLI/worker哈希匹配清单，六项路径存在。两次doctor调用worker的ABI探针；未运行决斗smoke、未重新部署或切换资产。输出和CI复验见[TESTING](TESTING.md#2026-10-31-合并ci与普通包现场复核)。

## 2026-10-31 依赖与工具清点

Rust workspace依赖树存在两个`hashbrown`版本：0.14.5由`hashlink/rusqlite`路径使用，0.17.1由`indexmap/toml_edit`路径使用；是不同的传递依赖链，没有从当前图证明可安全统一或删除。`cargo-machete`未安装，因此本轮没有声称完成机器化未用依赖扫描。仓库没有Node/npm、Go或独立requirements/poetry/pipenv清单；Rust以workspace Cargo清单为准，Python依赖集中在`pyproject.toml`。未发现可由包清单安全确认的弃用模块，故保留兼容路径和历史证据。

## 构建与发布状态

- 构建/部署脚本：`scripts/build-engine.ps1`、`scripts/deploy-local.ps1`。支持 `-Offline`；部署使用 `-FrozenRuntime` 时不从 Project Ignis 覆盖已冻结资产。
- 引擎资产由 `data/runtime/engine/manifest.json` 绑定 core、Lua、API、ABI 与哈希；牌库和脚本来自本机准备流程。禁止把 DLL、Lua 脚本、完整 CDB、图片或绝对路径提交到 Git。
- `dist/ygo-local/configs/engine.toml` 和忽略的 `configs/engine.toml` 将 worker 与资产路径写成当前仓库/机器的绝对路径。移动仓库或运行时资产后必须重新部署；该目录不是可任意转发的通用分发包。
- 本地构建包含 Project Ignis/ocgcore 产物，但仓库尚无完整、逐资产的第三方许可/再分发清单。任何公开分发前，先核查上游许可证和每项资产的再分发权限；本地隔离部署不构成可再分发授权。

### 两套运行资产与后续产品前提

- 普通发布wrapper引用普通runtime、普通快照和Phantom知识。赛事开发配置引用 `data/runtime/tournament-2026/frozen` 下的CDB/Lua/core，但其`worker_path`复用普通`dist/ygo-local/ygo-engine-worker.exe`；2026-10-27两套配置的doctor均就绪，`smoke_ok=null`；随后普通包单独smoke和replay通过，赛事开发配置的固定案例和重放也在独立账本通过；这仍不是统一双资产发布验收。
- 2026-10-19赛事知识来源校验通过但完整语义覆盖仍false；静态包的灰响应声明与运行时独立认证不是同一状态，详见[首回合验真](FIRST_TURN_VERIFICATION.md)。2026-10-27没有重复该业务校验。
- （截至2026-10-27自检）Rust/Python和现有离线资产可用于继续迭代；Node/npm入口存在，但当时尚无前端工程/HTTP服务。已抽查英文卡名，尚未落实中文名称/正文的完整可信来源；不把WindBot中文对白当中文卡库。
- 硬件CIM读取在规划调研时权限受限，未取得全卡求解的资源容量证据。完整证明、前端依赖、中文数据与干净机器部署均须各自验证；不能由doctor推出足够算力或可分发性。
- 更新与引擎更换的未来要求见[产品愿景](PRODUCT_VISION.md)及[路线图](ROADMAP.md)；本次未执行资产更新或安装。

## 2026-10-28开发CLI工作台补记

截至2026-10-28，开发源码中的`ygo-cli workbench serve`提供绑定`127.0.0.1`的草稿网页及本机HTTP端点，支持草稿列表/读写、YDK/JSON导入导出，以及可选本地catalog名称和39卡字段状态读取。页面通过集成测试和隔离浏览器完成草稿编辑、保存、刷新后重开验收；浏览器下载事件未在工具时限内返回，本地文件选择受扩展访问限制，因此浏览器手工操作不等同完整文件选择/下载用户验收，导入导出由HTTP集成测试覆盖。

该入口只管理草稿，不提供牌组分析、自动构筑、研究任务或证明服务。标准库HTTP/1.1实现采用固定loopback与请求限制；新增外部HTTP库的下载因TLS客户端凭据错误`SEC_E_NO_CREDENTIALS`未成功，故需要持续审阅协议边界和维护成本。工作台尚未进入`dist/ygo-local`普通旧包；本节不证明可分发、许可证充分、干净环境安装或当前源码部署通过。历史段落中“尚无前端/HTTP”只描述2026-10-27状态。

## 2026-10-30部署与CI证据界限

保存的2026-10-29记录显示，旧普通包CLI和worker哈希匹配其`build-hashes.json`，主要配置资产路径存在，包内doctor返回ready；包仍是2026-10-19版本且没有workbench命令。PR #8的干净Windows CI在修复提交上通过Python 740/21/0。上述结果各自只覆盖对应包或提交，不能证明当前源码已进入普通包，也不能替代P4-R5独立干净双资产验收。

当前源码`engine doctor`经`crates/ygo-engine-adapter/src/process.rs`中的ABI探针路径调用worker。旧普通包doctor曾执行且有结果记录，但没有足够的同版本运行日志证明其具体内部进程副作用；仅将该次行为标为未知。此处不把“未运行决斗smoke”写成“未启动worker”。

最新Ground Collapse离线准备将证据和测试材料保存在独立runtime及target目录；其交付体积清单约7.33GB且记录一项ACL访问失败，不能当作全工作区或所有证据的完整体积。本次未重新统计，也未调整ACL或删除这些材料。

## 2026-10-30 W1设计后工作区复核（历史时点）

当次核对基线为分支`codex/w1-workbench-analysis-design-20261030`、HEAD `8315232`，工作区起始干净。该分支包含W1受限分析接入设计，任务接口尚未实现。普通`dist/ygo-local`的CLI/worker SHA-256与其`build-hashes.json`相符；engine.toml列出的worker、core、catalog、scripts、script manifest及engine manifest六个路径均存在。该核对没有运行包内程序、没有重新检查所有资产内容，也不能证明后续源码已部署或发布包可移植。

历史普通包doctor内部进程行为仍未知。当前源码doctor经worker执行ABI探针，但不将该源码行为推断为旧包行为。W1接口设计不能视为普通包具备分析功能；部署与工作台边界见[DEPLOYMENT](DEPLOYMENT.md)、[WORKBENCH](WORKBENCH.md)及[W1后路线](superpowers/plans/2026-10-30-post-w1-project-route.md)。

## 2026-10-27 接续容量清点

只读扫描可读取普通文件的逻辑大小：`target/`约106.64 GiB、1,498,674个文件，`data/`约112.86 GiB、307,115个文件，其中`data/runtime/`约112.59 GiB。共有85处访问错误，扫描不跟随reparse点、不去重硬链接，且期间有并发写入；这些是有盲区的时点逻辑大小，不是精确磁盘占用。机器D盘当时可用约95.1 GiB。 恢复后以提升权限对这85个路径逐项执行lstat及直接子项枚举：均可读取，58个当前为空，27个非空项属于隔离Python依赖目录；没有递归复测容量，初次统计仍是有盲区的时点数值。详情见`target/workspace-audit-2026-10-27-codex/capacity-errors-recheck.json`。复核后只非递归移除本轮中断pip留下的5个已确认空目录，逐项核对父目录、名称和非链接状态，记录为`pip-empty-cleanup.json`；其他53个空目录及27个非空目录保持原位。原始范围、分组和错误列表见`target/workspace-audit-2026-10-27-codex/capacity-inventory.json`。

较大分组包括`target/curry-option-validation-tests`约17.09 GiB、`target/debug`约12.90 GiB，以及多个6–12 GiB历史runtime批次。`target/debug/ygo-engine-worker.exe`、`target/release`和若干研究目录仍有配置、部署脚本或证据消费者；大小本身不足以证明可删除。`target/pytest-cache`为可重建缓存，本轮检查时只有875字节。分类、保留引用和迁移方案尚未全面完成，禁止按顶层目录批量清除。 本次仅移除新建的`target/workspace-audit-2026-10-27-codex/cargo`编译缓存：清理前核查精确解析路径、无reparse和无运行中的编译进程；估算可释放约5.76 GiB分配量，日志及其他审计材料在父目录保留。详见`target/workspace-audit-2026-10-27-codex/cargo-cache-cleanup.json`。容量扫描发生在清理之前。

## 2026-10-27 环境自检与缓存处理

- 检查了根目录222个`pytest-cache-files-*`、四个`.v5-package-test-*`及`tests/`下三个`tmp*`目录；各项均可在提升权限后读取、没有子项、不是链接。逐项复核解析路径及空目录状态后非递归删除，共229个；未调整ACL。检查与删除清单位于`target/workspace-audit-2026-10-27-codex/`。
- `pyproject.toml` 将pytest缓存放在被忽略的 `target/pytest-cache`。Windows权限受限时先运行 `New-Item -ItemType Directory -Force -Path target/pytest-cache | Out-Null`；未预建时pytest仍可能留下受限临时目录，但位置在被忽略的`target/`下。
- 最近Ground源码归档包含 `tests/.tenki-*` 下53个文件和 `crates/ygo-engine-adapter/data/tmp/` 下8个文件；这些是合成测试产物，但也是已冻结归档成员，现保留原路径。`.gitignore` 是Ground固定工具包成员，未为清理而改写。
- v1–v5规划、旧提示匹配及历史研究入口均有现用路由、公开接口或证据消费者，未按名称删除。只移除 `ygo-cli` 未直接使用的`toml`及 `ygo-search` 未直接使用的`sha2`依赖声明，其他crate继续依赖对应库。

## 2026-10-27 提交前复核补充

- `.gitignore` 将crate内`data/tmp/`、`data/runtime/`与可中断测试目录`tests/.tenki-*/`纳入本机产物忽略范围；crate runtime仍含历史验证材料，不能据忽略规则推断可删除。
- 再核对冻结603项归档时，确认五个`tests/.tenki-*`临时目录中的53个文件本身是归档成员；这些文件从归档按清单逐项哈希恢复。此处历史内容保持在原路径，忽略规则只避免误纳入后续提交。
- `crates/ygo-engine-adapter/data/tmp/`中的两个随机确认ledger与`data/runtime/tenki-confirmation-tests-target/`共196个文件，仅看到110个header与86个checkpoint记录、未见收费记录；源码未找到该测试目录的精确字符串引用。考虑历史保留用途尚未完全确证，本轮不删除。文件级清单和保留结论见`target/workspace-audit-2026-10-27-codex/nested-synthetic-cleanup.json`；v3验证基线`data/runtime/p1-tenki-placement-validation-native-2026-10-23/`原位保留。

## Windows深路径诊断

Python 3.12隔离全套的首次副本位于本仓库深层`target/`，部分合成测试又在副本内创建嵌套Git仓库，导致Git的`-C`工作目录超过本机路径限制；`git check-ignore`退出128，调用层将其报告为`output must be ignored`。两个相同源码的端到端测试在`C:/ProjectIgnis/codex-ci-audit-20261027`短路径独立副本通过。深路径全套在28%时主动停止，不能算完整测试结果；日志及对照见`target/workspace-audit-2026-10-27-codex/ci-e2e-repro.log`和`ci-short-e2e.log`。

后续`checked_output`已改为只接受两个Git检查的退出码0/1，其他退出码失败关闭，不再把Git错误解释为正常忽略或未跟踪状态；聚焦回归见[TESTING](TESTING.md)。遇到类似错误先检查实际Git退出码、stderr与路径长度；不要只根据上层错误判定忽略规则错误。短路径只是验证环境调整，不改变保存报告或原生scope的身份要求，也不保证其他机器的Git长路径配置。

## 清理决策

除上述明确记录的隔离Cargo缓存和本轮5个空pip临时目录外，本轮没有删除 `data/runtime/`、`data/tmp/`、`dist/`、`target/` 或 `.venv/` 中的其他内容。较大的旧 ash/goal/v5 报告可能是当前文档数字的原始证据，测试账本 blob 可能被重放引用，离线构建 checkout 也有价值。下一次清理应先：

1. 列出受版本控制文档引用的本机报告、报告 ID 和哈希；把长期保留证据与临时工作文件分开。
2. 为 Rust 测试创建的随机 `journal-test-*`、`*.jsonl.blobs` 目录定义成功/失败两种退出清理及保留期限；保留失败时可复现所需条目。
3. 对历史大报告生成摘要与 SHA-256 清单后再决定压缩/迁移，迁移后更新证据路径。
4. 仅当旧部署报告已归档且新部署完成验证后覆盖 `dist/ygo-local`。

禁止用宽泛递归删除命令清理这些混合用途目录。
