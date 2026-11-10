# Windows 本机部署与验收

2026-11-10文档同步前状态快照：本地`main`为`ec83bad`，较本地`origin/main`的`577924b`领先27个提交；最近默认离线代码验证对应`8c7afe6`，之后main仅增加审计文档。PR #17当时为Open Draft，head `887e3430cff88704e8b8e183a3df1b94dfbb6960`、base `577924bc0c2af06044b77c065eea769c465ff2fe`，共30个提交/190个文件，尚未合入main；contracts CI通过，最终head CodeRabbit因Draft被跳过，GitHub reviews列表为空。该PR统计是同步前快照，后续分支提交会改变head和比较结果。现有`dist/ygo-local`仍是2026-10-19包；CLI/worker各自SHA-256匹配`build-hashes.json`，但包没有完整manifest或workbench入口。本轮未运行包内程序、doctor或部署，因此文件身份不表示当前源码已发布。详情见[项目路线快照](superpowers/plans/2026-11-09-project-status-and-dual-track-route.md)、[PR审阅记录](superpowers/plans/2026-11-09-pr17-review.md)与[验证记录](TESTING.md)。

历史状态（2026-11-09）：W1-C `ffi-receipt-stream-v1`在隔离worktree完成验证并提交；未部署。`dist/ygo-local`未切换，其既有2026-10-19身份记录继续适用。合成worker协议测试不证明发布包包含新代码、生产worker映像身份或真实ocgcore/FFI执行。完整范围见[本次验证](TESTING.md#2026-11-09-w1-c-worker-ffi-宿主确认流)。

2026-11-04路线复核基线为`main / 622546c`，开始时工作区干净；本轮沿用同日旧包只读哈希记录，不重跑包内程序。旧包清单只绑定CLI/worker，缺完整manifest及workbench入口；隔离候选与旧包均不证明该HEAD已部署，P4-R5仍开放。

2026-11-04只读复核：检查时HEAD为`main / b35b12dec226b3b71eb36896e27452ec7fd12015`；代码与文档整改尚未部署。`dist/ygo-local`中的`ygo.exe`和`ygo-engine-worker.exe`时间戳为2026-10-19，SHA-256分别为`54804730B3A507C0143C627D5E5C61B2ACC03964C9A7CDA7C803B6101432A89F`和`AD4A592981535144190EC44E0DD8C4ACA951EC21C0206A1346961484F37FD11C`，与包内只列这两个文件的`build-hashes.json`一致。包内没有`manifest.json`或`workbench/`；只读检查未运行任何包内程序。因此这些哈希只确认旧包与自身清单一致，不能证明当前源码已部署。ACL于2026-11-04再次只读复核；用户选择保留当前ACL，本轮未改权限。默认工作台仍返回`analysis_not_configured`；只有源码CLI显式传入`--analysis-config`才构造固定Rabbit分析执行器并调用worker。旧发布包不含该工作台入口。

2026-11-03现场：本轮可执行代码自检基线为`main / 50c279b0605c55f8e1f05240078700d63c01dd9d`；该验证时点工作树干净，较`origin/main`领先13个本地提交。后续仅补充审计文档，未改变可执行代码。本次文档续审开始时，HEAD为`87e6d57`，main较origin/main领先21个本地提交且工作区干净；`crates/`、`python/`、Cargo清单、`schemas/`、`scripts/`相对`50c279b`无可执行代码差异。`dist/ygo-local`仍是2026-10-19旧包；CLI和worker分别匹配包内`build-hashes.json`，但该清单只绑定这两个文件，当前包无`manifest.json`，也不能证明当前源码已部署。2026-11-03续审通过包内`configs/engine.toml`对普通包执行`ygo.exe engine doctor`，结果为`ready=true`、`assets_ok=true`、`abi_ok=true`、`issues=[]`、`smoke_ok=null`；此项启动包内worker执行`probe_only=true`的ABI探针，不是决斗smoke或P4-R5验收。隔离W1-C候选已构建并用于一次独立Rabbit有限分析，结果为`budget_limited/time_budget`；没有部署到`dist/ygo-local`。P4-R5仍开放。只读ACL复查发现`Authenticated Users: Modify`直接设置在`D:\`根并继承到项目；项目父目录和工作区另有四个无法映射到当前账户名的Modify SID。修改卷根ACL可能影响D盘其他数据，修改项目父目录ACL可能影响两个兄弟工作区，用户于2026-11-03选择保留现状并记录ACL风险，本轮未变更权限。普通工作台仍关闭分析。安全影响和未决环境条件见[环境审计](ENVIRONMENT_AUDIT.md)。

2026-11-03 W2隔离候选包：源码CLI已用`--offline --locked`构建并放入`target/w2-clean-20261103/package-candidate-02`，通过空profile启动、包内catalog读取/检索、牌组草稿保存重开、JSON/YDK往返和同包重启检查。源码/产物/catalog身份与机器验收见[TESTING](TESTING.md)及[W2批次计划](superpowers/plans/2026-11-03-w2-offline-clean-environment-plan.md)。候选仅在target目录，未切换部署。旧dist没有workbench，故升级兼容和旧草稿迁移未验收；同一主机隔离目录不等于干净Windows环境验收。

## 历史现场（2026-11-01）

当前checkout为`main / 2f690d5`，工作区有未提交修改；本批没有构建或部署当前工作区。`dist/ygo-local`仍为2026-10-19旧包，CLI/worker哈希与包内清单一致；`target/release`中的对应可执行文件与dist为同一Windows硬链接，不能作为当前HEAD构建证据。部署配置绑定本机绝对路径，不可直接搬移。

隔离候选`a21d587`曾完成普通/赛事doctor、身份和smoke/replay；smoke在30秒预算截断且没有可比研究账本，因此P4-R5仍开放。该候选及更早`e684f4e`只代表各自历史源码和资产身份，未切换为当前部署。详细命令、哈希和范围见[TESTING](TESTING.md)；当前门禁见[TASKS](../TASKS.md)。

历史快照（2026-10-31，`main / 8526c1f`）：当时普通旧包和赛事配置doctor均ready；检查对象是2026-10-19的`dist/ygo-local`。后续较早候选的结果见[验证记录](TESTING.md)，不覆盖本页当前部署状态。

历史记录（2026-10-31）：当轮完成W1-B3.3内部合成故障矩阵并通过Rust/Python离线验证；未重建或切换部署包，也未在当时源码构建上运行doctor、smoke或研究流程。部署状态仍以[TASKS](../TASKS.md)中的P4-R5门禁为准。

## 当前代码与本机包

### W1-C源码输入字节包

Python身份工具提供离线源码字节包及校验命令：

```powershell
py -m ygo_data.identity source-bundle --repo . --output-dir target/w1c-provenance-20261105/source-bundle-v20
py -m ygo_data.identity verify-source-bundle --bundle-dir target/w1c-provenance-20261105/source-bundle-v20
```

包归档HEAD对应工作树中的Git跟踪文件和非忽略未跟踪文件，清单逐路径绑定SHA-256；已删除的跟踪路径保留为`null`，忽略文件不归档。版本化合同见[workspace-source-bundle schema](../schemas/workspace-source-bundle.schema.json)。校验器离线重算清单、压缩包和成员字节，并拒绝路径异常、缺失/重复成员和内容不匹配；发布通过同一忽略父目录内的暂存目录重命名完成。该格式只保存路径和文件字节，不保存Git index、文件模式、时间戳或ACL；忽略的运行资产仍须单独冻结身份。自摘要可发现不一致，但不认证制作者，不证明构建可复现，也不认证worker、FFI、报告来源或研究消费。

需要保存精确工作区状态时，可在来源字节包之后生成配套Git状态包：

```powershell
py -m ygo_data.identity workspace-state-bundle --repo . --source-bundle-dir target/w1c-provenance-20261105/source-bundle-v20 --output-dir target/w1c-provenance-20261105/workspace-state-v20
py -m ygo_data.identity verify-workspace-state-bundle --bundle-dir target/w1c-provenance-20261105/workspace-state-v20 --source-bundle-dir target/w1c-provenance-20261105/source-bundle-v20
```

[workspace-state-bundle schema](../schemas/workspace-state-bundle.schema.json)将原始Git index字节及SHA-256、`ls-files --stage -z`、porcelain v2状态、二进制暂存/未暂存patch和来源包内每个现存文件的`stat.S_IMODE`绑定到该来源包。采集期间Git子进程使用`GIT_OPTIONAL_LOCKS=0`，发现`index.lock`或来源不一致时拒绝生成；状态包在Git忽略目录内暂存并原子重命名，校验离线核对每个成员、计数和来源身份。未跟踪文件的内容由来源包归档，Git patch只描述Git可见差异。状态包不记录ACL、NTFS安全描述符或文件时间戳；自摘要与本机回读不认证操作者，也不证明之后执行了相同源码。

2026-11-04合成FFI日志事件实现与验证记录更新后，曾生成`source-bundle-v19`及配套`workspace-state-v19`；两者均在忽略目录`target/w1c-provenance-20261104/`中。2026-11-05离线复核确认来源包自身有效（identity=`a6f969fb5fd99cb2ba35040db2d3f17052dbeb9bdbd83b7706978ffd4b6630e4`，source identity=`ae573b7d97089485cdbae5d5af4ca717a6aa2007e2bdd418a04ed4e23cdf4c03`），配套状态包也有效（identity=`a096cfd8218d5dc2aa2cb6cf28deb8944da8f915d69b68ce5226142b909524f9`）；但来源内容与当前工作树不一致，差异包括`crates/ygo-search/src/combo.rs`、`crates/ygo-search/tests/beam_execution.rs`、`python/ygo_data/identity.py`、`python/ygo_eval/execution_receipts.py`、`tests/test_execution_receipts.py`和`tests/test_identity.py`。因此v19及更早快照均标为历史材料，不能作为本次最终工作树身份；稳定后应重新生成新的来源/状态包。此次只保存源码与Git状态，没有构建Rust发布产物；`rebuild-v3/build-record.json`仍绑定更早的source/state v3，不是本轮源码构建证明。

要封存最终提交后的源码和Git状态，使用上方命令生成忽略目录`target/w1c-provenance-20261105/source-bundle-v20`及配套`workspace-state-v20`并离线复核；manifest记录精确提交源码字节及Git状态，但不含忽略运行资产、ACL、构建产物或部署状态。生成的manifest携带该快照的identity；源码/状态包不替代构建来源记录或`dist/ygo-local`部署验收。当前`v19`已经确认为历史快照。

### 来源绑定构建记录v1

`build-provenance-record`将已验证来源包与一次观察到的构建命令、工具链版本、候选产物SHA-256及调用者指定的资产role/hash绑定；合同见[source-bound-build-record schema](../schemas/source-bound-build-record.schema.json)，嵌套的旧[build-record schema](../schemas/build-record.schema.json)保持不变。构建前检查输出路径不存在且位于Git忽略目录，构建前后复核来源包和资产；`verify-source-bound-build-record`离线核验来源包、记录摘要、产物和资产字节。记录保存role及hash/bytes，不嵌入本机绝对路径；复核时须再次提供对应`ROLE=PATH`映射。命令摘要只展示安全参数，完整argv由摘要绑定，任意路径或未列入白名单的参数不会明文写入摘要字段。

2026-11-04的隔离候选构建使用`target/w1c-provenance-20261104/source-build-bundle`、`target/w1c-provenance-20261104/isolated-target`和`target/w1c-provenance-20261104/build-record.json`。CLI及worker以`--offline --locked --profile dev`构建，构建记录验证成功，且显式标记`provenance=observed_command_only`、`reproducible_build_proven=false`。编译worker不代表启动worker；该候选没有运行doctor、引擎、runner、worker或FFI，也没有部署或新分析。配套工作区状态包补充Git index与patch/mode快照，但仍不认证进程执行、报告来源或研究消费。

本批修正后的来源身份工具另生成`target/w1c-provenance-20261104/source-bundle-v4`和`workspace-state-v4`；二者分别绑定当前源文件字节以及精确Git工作区状态。最近的Rust构建记录仍是`rebuild-v3/build-record.json`，绑定此前的source/state bundle v3；本批只增加Python离线校验器、schema、fixture和文档，没有为v4源码生成新Rust产物或部署包。v3构建记录不代表v4源码构建身份，具体记录与验证范围见[TESTING](TESTING.md)。

### W1-C合成执行回执合同v1

`schemas/w1c-execution-receipt-chain-v1.schema.json`定义adapter尝试、worker spawn、请求/响应字节、双向FFI事件、报告写入/回读及固定为unknown的消费字段。所有整数型字段遵循JSON Schema语义，接受有限且数学上为整数的JSON数值表示；进程退出码保留有符号值，负数可表示信号终止。离线校验器只验证输入记录的schema语义、事件顺序和SHA-256前驱链；可用`--report`提供报告原始字节，可用`--expected-head-sha256`与独立保存的链尾摘要比对：

```powershell
$env:PYTHONPATH='python'
py -m ygo_eval.execution_receipts verify --input tests/fixtures/w1c-execution-receipt-v1.json --report tests/fixtures/w1c-execution-report-v1.json
```

成功结果中的`status=complete`表示该合成链、报告字节与operation/job/input投影相符；`report_origin_authenticated`仍为false，消费仍为unknown。若FFI回执为partial/unknown，`ffi_total_count`为null，只报告已观察到的entered/returned子集。单靠可重算的哈希链不能认证producer、OS进程或硬件执行。该模块和fixture尚未接入adapter、worker、FFI或HTTP生产路径，也不改变现有HTTP schema、普通启动或执行范围。当前批次范围和覆盖项见[TESTING](TESTING.md)及[W1-C来源与计量计划](superpowers/plans/2026-11-04-w1c-provenance-accounting-plan.md)。

历史部署复核（2026-10-31，`main / 8526c1f`）：普通包仍是2026-10-19构建，CLI/worker哈希匹配自身清单；当时对旧包分别运行普通配置与赛事配置doctor均返回ready。它验证旧二进制和当时所指资产，不证明当前源码已部署。赛事配置中的`worker_path`指向普通包worker，同时使用赛事冻结CDB/Lua/core。详见[部署与CI证据](TESTING.md#2026-10-31-合并ci与普通包现场复核)。

当前 Rust 源码包含 v1–v5 正式 Combo 规划分派，以及未开放为正式规划入口的 first-turn 内部预测/局部执行与知识验真。部署脚本会把当前 workspace CLI 和 worker 复制到 `dist/ygo-local`，但不因此使尚未通过完整语义关口的 first-turn 成为正式 v6。部署包绑定当前仓库路径，不能直接搬到另一台机器。

当前 `deploy-local.ps1` 只打包 Phantom v1/v2 知识和普通运行资产；不会复制赛事 `tournament-2026` 知识包或其隔离 CDB/Lua/core。赛事规则验真须按 `FIRST_TURN_VERIFICATION.md` 使用独立开发配置，不可通过替换普通包中的 CDB 来混用两套资产。

普通D盘`dist/ygo-local`于2026-10-19按冻结资产重建。2026-10-27对该旧包运行预算受限决斗smoke和独立replay；2026-10-29保存记录随后核对CLI/worker与`build-hashes.json`一致、主要配置资产路径存在，旧包doctor返回ready且`smoke_ok=null`；旧包没有`workbench`命令。上述运行与静态检查分别适用于其日期和范围；哈希与路径检查不证明当前源码已经部署。

2026-10-28在隔离worktree以D盘冻结资产副本、干净提交构建的包，doctor返回`ready/abi_ok/assets_ok=true`。预算受限smoke的两次独立运行分别产生318节点/27,288ms和340节点/27,310ms，均以`time_budget`终止且有3条`EngineVerified`线路；独立`combo replay`验证3/3线路。最终文档提交`d1e94b2`的包内`TESTING.md`与源码文档SHA-256相同，CLI哈希仍与此前smoke/replay使用的二进制一致。旧版CLI自身不支持`engine identity`，但当前CLI只读采样器以旧包配置读取资产后，两包均`consistent=true`；CDB、core DLL、engine/script manifest及12,727个脚本哈希一致，CLI和worker哈希不同。旧包catalog/banlist状态及Rabbit合法性检查通过。没有可比研究账本，不代表账本等价或原生研究资格。完整证据和失败/修复经过见[TESTING](TESTING.md)。

本次隔离部署包已在干净提交上复建并完成smoke/replay；原D盘旧包没有覆盖。当前采样器已用旧包配置比较两代资产身份。逐文件盘点显示新旧包分别含127和67个文件，均无`.jsonl`研究账本文件；新包ledger相关文件仅为schema。P4-R5不从包内样本推断包外正式scope账本等价，资产身份验收范围见[TESTING](TESTING.md)。

普通发布包、赛事资产配置和最终干净双资产包是不同状态：赛事配置引用独立冻结CDB/Lua/core，但当前`worker_path`复用普通`dist/ygo-local` worker；固定案例及独立重放属于各自历史账本，不是正式v6发布包或P4-R5验收。环境资产和保留/清理边界见 [`ENVIRONMENT_AUDIT.md`](ENVIRONMENT_AUDIT.md)。

后续研究使用独立开发构建或冻结runner，并分别记录构建/原生时点/文档后源码身份；没有因此刷新dist。新增`engine identity`须使用包含该功能的开发CLI，旧dist不能自动获得新命令。研究期间使用独立 `CARGO_TARGET_DIR` 与匹配的 `--target-dir`，构建与实验分时；从资产冻结到后检不得并行构建或覆盖被绑定worker。相同哈希及构建记录不单独证明可复现构建。预算、证据和副作用见[研究运行规范](RESEARCH_OPERATIONS.md)与[证据合同](EVIDENCE_CONTRACTS.md)。

使用已有冻结运行资产离线更新本机发布目录：

```powershell
./scripts/deploy-local.ps1 -Offline -FrozenRuntime
```

此命令会重建整个 Rust workspace 并覆盖 `dist/ygo-local` 的同名发布文件。先确保旧包所引用的验收报告已保留；脚本不会清理 data/runtime 或 data/tmp。

2026-10-14：新增知识/规划 CLI，见 [SEMANTIC_PLANNING.md](SEMANTIC_PLANNING.md)。已有冻结资产使用 `./scripts/deploy-local.ps1 -Offline -FrozenRuntime`，保留 CDB、Lua、core 版本，重新构建 CLI/worker 并验证知识来源。普通部署会从 Ignis 准备资产；冻结部署不会覆盖资产。包内新增 knowledge 与 Phantom 请求 fixture，wrapper 设置知识路径。

通用 `combo analyze` 的基线范围：OCG/MR5，双方8000 LP，先攻首回合，固定五张手牌、seed初始化剩余牌库、无对手干扰；对手相同主卡组作惰性占位库，初始手牌为空，只选择可选不响应。另有版本化规划v4/v5的指定单灰合成场景，见[恢复规划](RECOVERY_PLANNING.md)及[灰流丽策略](ASH_STRATEGY_PLANNING.md)。这不提供任意对手、通用手坑、后攻或构筑能力。

本机草稿浏览器由开发CLI命令`ygo workbench serve`提供，运行方式见[WORKBENCH](WORKBENCH.md)。它不在当前`dist/ygo-local`发布包内。默认启动提供草稿操作且不启动引擎；源码显式配置`--analysis-config`可运行固定Rabbit分析并调用worker。它不是可迁移安装包。一键发布启动、路径迁移、分析界面和引擎切换仍是后续P3/P8任务。

## 环境准备

需要 Windows x64、Rust stable、Python 3.10+、Git、Visual Studio 2022 C++ x64 工具。本机 Project Ignis 的官方 `expansions/cards.cdb`、`script` 公共库与 `script/official` 是数据来源。首次外网命令要求本地 Clash Verge 代理监听 `127.0.0.1:7897`；所有提供的安装脚本会在同一调用中设置代理。

```powershell
./scripts/build-engine.ps1
./scripts/deploy-local.ps1 -Ignis C:/ProjectIgnis
```

`build-engine.ps1` 固定 core `38d04c9feb1a26617407091380634c87262fe3f8`、Lua `6e22fedb74cf0c9b6656e9fce8b7331db847c605`，用 Meson/Ninja Release、MSVC x64 构建，并运行结构布局与 API 11.0 探针。Windows 上只把 Lua 的 cmd 拼接生成器替换为 Python 拼接，记录在 manifest；核心和 Lua 源文件保持固定版本。构建拒绝其它源码改动或未跟踪文件，只允许精确已知的 Meson 转换，并记录源码树与适配哈希。

`deploy-local.ps1` 冻结官方资产、构建 CLI/worker、固定 LFLists `1051a65ab853fd84521aa919d1859f9468816c56`、导入 `2026.10 OCG`（2026-10-01 生效），生成 `dist/ygo-local` 本机包。已有缓存时两个脚本都支持 `-Offline`。公共 utility.lua 会加载 proc_unofficial.lua，因此只复制这个公共辅助库到脚本根目录；不导入 unofficial 卡片脚本、Rush 或 Skill 数据库。

部署脚本将若干文档扁平复制到包根目录；其中相对链接仍按原仓库布局编写，不能保证在包内解析。应从仓库的[文档入口](INDEX.md)阅读完整体系及本机证据；包不包含完整历史数据。脚本现会同时复制TESTING入口和历史快照，并生成指向当前仓库文档的包内README；这些指向工作区的链接不代表包构建时的冻结文档。现有2026-10-19包尚未重建，不能假定其包含这些文件。

包包含 `ygo.exe`、worker、配置示例、配置、评分文件、请求 fixture、说明和二进制哈希。`ygo.cmd` 设置本机资产、快照及评分路径，可从任意工作目录启动。外部 DLL、CDB、卡片脚本、个人路径不会进入 Git，也不随可公开分享的源码包分发。本机包的路径绑定当前安装，移动资产后需重新部署。

新增逐效果验真和 Break Sword v2 命令见 [BREAK_SWORD_VERIFICATION.md](BREAK_SWORD_VERIFICATION.md)。包内提供 phantom-v1/v2 两个知识 profile，以及 Break 请求、真实效果案例和固定起手夹具；wrapper分别设置两个知识路径。协议v2与v3由当前 worker 同时处理。

## CLI

```powershell
./dist/ygo-local/ygo.cmd engine doctor
./dist/ygo-local/ygo.cmd catalog status
./dist/ygo-local/ygo.cmd banlist status
./dist/ygo-local/ygo.cmd deck validate --input tests/fixtures/rabbit.ydk --as-of 2026-10-07
./dist/ygo-local/ygo.cmd engine smoke --output data/runtime/smoke.json
./dist/ygo-local/ygo.cmd combo analyze --input tests/fixtures/rabbit.request.json --output data/runtime/report.json
./dist/ygo-local/ygo.cmd combo replay --input data/runtime/report.json
```

重新导入：`catalog import --input <cards.cdb>`；`banlist import --input <OCG.lflist.conf> --commit <40位源码提交>`。指定已有快照可用 status 的 `--id`；所有数据命令支持 `--store`。显式快照 ID 可跳过 active 指针；`--store` 导入的指针保存在该 store 内，不修改其它 store。分析请求字段见 `schemas/combo-request.schema.json`。`latest-ocg` 在请求开始时解析为不晚于 `as_of` 的不可变快照 ID。

JSON 完整报告写入 `--output`，未给输出路径则写 stdout；中文摘要写 stderr。程序失败返回 exit 2 和 JSON 错误。当前源码的`doctor`检查资产并通过worker执行ABI探针；`smoke_ok=null`表示doctor没有执行真实决斗smoke，不代表没有启动worker。旧部署包的具体内部行为应按其二进制版本和日志判定。后续独立smoke的结果须另查报告。`engine smoke`执行小预算搜索与重放；完整golden验收还需运行以下opt-in测试。

## 验证

```powershell
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --offline --locked -- -D warnings
cargo test --workspace --offline --locked
cargo test -p ygo-engine-adapter --examples --offline --locked
$env:http_proxy='http://127.0.0.1:7897'; $env:https_proxy='http://127.0.0.1:7897'; py -m pip install -e '.[test]'
$env:PYTHONPATH='python'
New-Item -ItemType Directory -Force -Path target/pytest-cache | Out-Null
$testFiles = @(Get-ChildItem -LiteralPath tests -File -Filter 'test_*.py' | Sort-Object Name | ForEach-Object { $_.FullName })
py -m pytest @testFiles
py -m ygo_data.cli validate --input tests/fixtures/cards.sample.json
```

以下是依赖本机引擎和资产的显式验收，会启动原生引擎；运行前须确认适用范围及资产，不属于常规离线自检：

```powershell
cargo test -p ygo-engine-adapter --test live_engine --offline --locked -- --ignored --nocapture
$env:YGO_LIVE_ENGINE='1'
py -m pytest tests/test_runtime_build.py
```

Python套件显式枚举顶层测试文件，以免递归发现证据树及不可读临时目录。CI不携带真实资产；依赖冻结资产/账本报告的Rust测试为显式opt-in，Python引擎和本机报告用例默认skipped。历史“四项”不是当前测试数量，最新完整套件计数见[TESTING](TESTING.md)。真实黄金线路fixture验证救援兔未使用怪兽的结束阶段破坏、霍普两张超量素材、LAN连接终场及提示编号不匹配；规划测试验证Phantom目标、来源与报告伪造拒绝和预算降级。

首版未知决策停止分支，未知信息帧保留原始字节、结果为 partial；只有完全解码、终场已结算且独立重放一致的线路才能标记 engine_verified。评分总为 heuristic。旧 rabbit-v1 评分只覆盖救援兔、霍普、宝石骑士珍珠及 LAN 的小型验收场景；其余卡效强度列为覆盖缺口、计零，不代表实际弱度。新规划入口使用 rusty-fog 目标和资源/决策排序，逐效果范围见 SEMANTIC_PLANNING.md。
