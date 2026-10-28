# Windows 本机部署与验收

## 当前代码与本机包

当前 Rust 源码包含 v1–v5 正式 Combo 规划分派，以及未开放为正式规划入口的 first-turn 内部预测/局部执行与知识验真。部署脚本会把当前 workspace CLI 和 worker 复制到 `dist/ygo-local`，但不因此使尚未通过完整语义关口的 first-turn 成为正式 v6。部署包绑定当前仓库路径，不能直接搬到另一台机器。

当前 `deploy-local.ps1` 只打包 Phantom v1/v2 知识和普通运行资产；不会复制赛事 `tournament-2026` 知识包或其隔离 CDB/Lua/core。赛事规则验真须按 `FIRST_TURN_VERIFICATION.md` 使用独立开发配置，不可通过替换普通包中的 CDB 来混用两套资产。

普通D盘`dist/ygo-local`于2026-10-19按冻结资产重建。2026-10-27自检核对该旧包的CLI/worker与`build-hashes.json`一致，普通包与赛事开发配置的doctor均返回就绪、`smoke_ok=null`；之后旧包的预算受限决斗smoke和独立replay通过，详见[TESTING](TESTING.md)。

2026-10-28在隔离worktree以D盘冻结资产副本、干净提交`27ab161`构建的包，doctor返回`ready/abi_ok/assets_ok=true`。补齐公共Lua脚本根目录后，预算受限smoke产生3条`EngineVerified`线路（318节点、27,288ms、`time_budget`终止），独立`combo replay`验证3/3线路；包内`TESTING.md`与源码文档SHA-256相同。D盘旧包CLI不支持`engine identity`；旧包与新包的CLI/worker哈希不同，但核心DLL、引擎manifest、脚本manifest、CDB/LFLists、catalog及banlist的共用资产字段一致。旧包catalog/banlist状态及Rabbit合法性检查通过。没有可比研究账本，不代表账本等价或原生研究资格。完整证据和失败/修复经过见[TESTING](TESTING.md)。

本次隔离部署包已在干净提交上复建并完成smoke/replay；原D盘旧包没有覆盖。P4-R5仍因旧CLI缺少完整身份接口、旧包CLI/worker哈希不同及缺少可比研究账本而保留跨版本等价性未知项。

普通发布包、赛事开发配置和最终干净双资产包是三种不同状态：赛事当前引用独立冻结资产及debug worker；固定案例及独立重放通过本轮独立账本的两次请求，不是正式v6发布包。环境资产和保留/清理边界见 [`ENVIRONMENT_AUDIT.md`](ENVIRONMENT_AUDIT.md)。

后续研究使用独立开发构建或冻结runner，并分别记录构建/原生时点/文档后源码身份；没有因此刷新dist。新增`engine identity`须使用包含该功能的开发CLI，旧dist不能自动获得新命令。研究期间使用独立 `CARGO_TARGET_DIR` 与匹配的 `--target-dir`，构建与实验分时；从资产冻结到后检不得并行构建或覆盖被绑定worker。相同哈希及构建记录不单独证明可复现构建。预算、证据和副作用见[研究运行规范](RESEARCH_OPERATIONS.md)与[证据合同](EVIDENCE_CONTRACTS.md)。

使用已有冻结运行资产离线更新本机发布目录：

```powershell
./scripts/deploy-local.ps1 -Offline -FrozenRuntime
```

此命令会重建整个 Rust workspace 并覆盖 `dist/ygo-local` 的同名发布文件。先确保旧包所引用的验收报告已保留；脚本不会清理 data/runtime 或 data/tmp。

2026-10-14：新增知识/规划 CLI，见 [SEMANTIC_PLANNING.md](SEMANTIC_PLANNING.md)。已有冻结资产使用 `./scripts/deploy-local.ps1 -Offline -FrozenRuntime`，保留 CDB、Lua、core 版本，重新构建 CLI/worker 并验证知识来源。普通部署会从 Ignis 准备资产；冻结部署不会覆盖资产。包内新增 knowledge 与 Phantom 请求 fixture，wrapper 设置知识路径。

通用 `combo analyze` 的基线范围：OCG/MR5，双方8000 LP，先攻首回合，固定五张手牌、seed初始化剩余牌库、无对手干扰；对手相同主卡组作惰性占位库，初始手牌为空，只选择可选不响应。另有版本化规划v4/v5的指定单灰合成场景，见[恢复规划](RECOVERY_PLANNING.md)及[灰流丽策略](ASH_STRATEGY_PLANNING.md)。这不提供任意对手、通用手坑、后攻或构筑能力。

本机草稿浏览器由开发CLI命令`ygo workbench serve`提供，运行方式见[WORKBENCH](WORKBENCH.md)。它不在当前`dist/ygo-local`发布包内，不分析牌组、不启动引擎，也不是可迁移安装包。一键发布启动、路径迁移、分析界面和引擎切换仍是后续P3/P8任务。

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

JSON 完整报告写入 `--output`，未给输出路径则写 stdout；中文摘要写 stderr。程序失败返回 exit 2 和 JSON 错误。`doctor` 分开检查资产和 ABI，`smoke_ok=null` 表示该次doctor本身没有执行真实smoke；后续独立smoke的结果须另查报告。`engine smoke` 执行小预算搜索与重放；完整 golden 验收还需运行以下 opt-in 测试。

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
