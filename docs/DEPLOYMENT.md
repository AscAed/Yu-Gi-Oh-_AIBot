# Windows 本机部署与验收

2026-10-14：新增知识/规划 CLI，见 [SEMANTIC_PLANNING.md](SEMANTIC_PLANNING.md)。已有冻结资产使用 `./scripts/deploy-local.ps1 -Offline -FrozenRuntime`，保留 CDB、Lua、core 版本，重新构建 CLI/worker 并验证知识来源。普通部署会从 Ignis 准备资产；冻结部署不会覆盖资产。包内新增 knowledge 与 Phantom 请求 fixture，wrapper 设置知识路径。

运行范围：OCG/MR5，双方 8000 LP，先攻首回合，固定五张手牌、seed 初始化剩余牌库，无对手干扰。对手使用相同主卡组作为惰性占位库、初始手牌为空，只在可选响应窗口选择不响应；尚不支持指定对手卡组、手坑、后攻或构筑。

## 环境准备

需要 Windows x64、Rust stable、Python 3.10+、Git、Visual Studio 2022 C++ x64 工具。本机 Project Ignis 的官方 `expansions/cards.cdb`、`script` 公共库与 `script/official` 是数据来源。首次外网命令要求本地 Clash Verge 代理监听 `127.0.0.1:7897`；所有提供的安装脚本会在同一调用中设置代理。

```powershell
./scripts/build-engine.ps1
./scripts/deploy-local.ps1 -Ignis C:/ProjectIgnis
```

`build-engine.ps1` 固定 core `38d04c9feb1a26617407091380634c87262fe3f8`、Lua `6e22fedb74cf0c9b6656e9fce8b7331db847c605`，用 Meson/Ninja Release、MSVC x64 构建，并运行结构布局与 API 11.0 探针。Windows 上只把 Lua 的 cmd 拼接生成器替换为 Python 拼接，记录在 manifest；核心和 Lua 源文件保持固定版本。构建拒绝其它源码改动或未跟踪文件，只允许精确已知的 Meson 转换，并记录源码树与适配哈希。

`deploy-local.ps1` 冻结官方资产、构建 CLI/worker、固定 LFLists `1051a65ab853fd84521aa919d1859f9468816c56`、导入 `2026.10 OCG`（2026-10-01 生效），生成 `dist/ygo-local` 本机包。已有缓存时两个脚本都支持 `-Offline`。公共 utility.lua 会加载 proc_unofficial.lua，因此只复制这个公共辅助库到脚本根目录；不导入 unofficial 卡片脚本、Rush 或 Skill 数据库。

包包含 `ygo.exe`、worker、配置示例、配置、评分文件、请求 fixture、说明和二进制哈希。`ygo.cmd` 设置本机资产、快照及评分路径，可从任意工作目录启动。外部 DLL、CDB、卡片脚本、个人路径不会进入 Git，也不随可公开分享的源码包分发。本机包的路径绑定当前安装，移动资产后需重新部署。

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

JSON 完整报告写入 `--output`，未给输出路径则写 stdout；中文摘要写 stderr。程序失败返回 exit 2 和 JSON 错误。`doctor` 分开检查资产和 ABI，`smoke_ok=null` 表示尚未执行真实 smoke。`engine smoke` 执行小预算搜索与重放；完整 golden 验收还需运行以下 opt-in 测试。

## 验证

```powershell
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --offline -- -D warnings
cargo test --workspace --offline
$env:http_proxy='http://127.0.0.1:7897'; $env:https_proxy='http://127.0.0.1:7897'; py -m pip install -e '.[test]'
$env:PYTHONPATH='python'
py -m unittest discover -s tests -p 'test_*.py'
py -m ygo_data.cli validate --input tests/fixtures/cards.sample.json
cargo test -p ygo-engine-adapter --test live_engine --offline -- --ignored --nocapture
$env:YGO_LIVE_ENGINE='1'
py -m unittest discover -s tests -p 'test_runtime_build.py'
```

CI 不携带真实资产，Rust live_engine 被明确标记 ignored，Python 引擎用例明确 skipped。真实黄金线路 fixture 验证救援兔未使用怪兽的结束阶段破坏、霍普两张超量素材、LAN 连接终场，以及提示编号不匹配失败。

首版未知决策停止分支，未知信息帧保留原始字节、结果为 partial；只有完全解码、终场已结算且独立重放一致的线路才能标记 engine_verified。评分总为 heuristic。默认只覆盖救援兔、霍普、宝石骑士珍珠及 LAN 的小型验收场景；其余卡效强度列为覆盖缺口、计零，不代表实际弱度。
