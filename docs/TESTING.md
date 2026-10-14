# 本机验证记录

## 2026-10-14 第二阶段：逐效果验真与 Break Sword v2

实现提交 `51a62a4`，审查修复提交 `ffaa1e5`。Windows x64、Python 3.14.7；复用原冻结 core、Lua、CDB、禁限表。没有升级资产，没有重新编译 ocgcore；独立 checkout 重新编译 Rust CLI/worker。本机结果不代表远程 CI。

| 本轮检查 | 结果 |
|---|---|
| Rust fmt / Clippy（offline、locked、warnings denied） | 通过 |
| 默认 Rust workspace | 67 passed、0 failed、9 ignored |
| 显式真实引擎 workspace `--ignored` | 9 passed、0 failed |
| Python 全量 `YGO_LIVE_ENGINE=1` | 9 passed、0 skipped |
| Python 默认 | 6 passed、3 skipped（本机资产/报告用例） |
| `knowledge verify` | 16个支持效果逐例通过，含结算后反例及独立重放 |
| 固定16起手 | 8个正例达标并重放；4个受限未找到方案；4个覆盖/预算降级分类正确 |
| 原生同名素材专项 | 两张 Boots 叠 Break、取除、自毁、复活并继续达标及重放通过 |
| 报告篡改 | 场景、等级、阶级、素材宿主、超量历史拒绝；嵌套 runtime/deck/stats/decisions/versions 损坏拒绝 |

默认测试不要求本机引擎/数据库。显式测试前需 `cargo build --release --workspace --offline --locked`，提供当前 worker；案例使用完整合法牌组、固定起手和实际引擎准备过程，不直接注入己方墓地、次数或召唤历史。

知识 profile：`knowledge-c2c93bf5222e30a45cb600e3b2cc120a4c83a5162d8e37ce28eef4ad3e41cc43`。12张卡、21条效果中16条支持范围内的效果有真实操作案例。符号假设、来源哈希、逐案例证据和完整线路证明分开保存。Greaves 可选增级分支仍不在规划范围；反例覆盖所列条件，不等于所有条件组合验证。

受控 Ryu-Ran 场景、无 Cherubini 额外牌组的默认请求产生8个方案、224次引擎调用、2条独立目标线路。其中完整 Break Sword 链为：

- `cb4cd1cb331628addc375d0589e44528300ca62bc8bf0cb9be214495b6444617`：超量、取除、双方破坏、自身复活触发、两体等级增加、继续做出 Rusty 并盖放 Fog。
- `4fefaaf4236ebdf1edd52fb745eed36f1cb2c1a9fa9be8b970be8be0e7b0bbe8`：直接 Rusty 路线，作为同一场景的候选对照。

再次 `plan-replay` 检查2条线路与42个去重前缀见证，共44次调用。固定起手的人工基准、规划和外部重放合计均不超过512次：正例213–303次，深度截断16次，其他无方案/覆盖/符号深度案例0次。有限搜索未找到方案不是证明无解；本轮没有用墙钟变化声称性能改善。

一次独立整分支审查发现并修复三项重要问题：同名 overlay MOVE 丢失 position、v3关键嵌套 Schema 过宽、worker异常误归为预测不符。每项均先复现失败再通过回归，修复后全量测试通过；未发起第二轮审查。预算截止导致的 timeout 与 worker 自身 timeout 也分别测试。

保留小项：v2 CLI 接受 `--scoring` 但使用默认旧诊断评分；它不改变目标/资源排序。基准步骤由实施代理手工整理、独立于规划器生成，尚无人类决斗专家策略审阅。

独立干净 checkout 在 `ffaa1e5` 上重新构建并部署，67项默认 Rust、9项显式引擎、Python9项全量、fmt/Clippy 全部通过。重新执行验真 CLI、v2规划/重放；16个效果案例、16个起手结果通过，知识 ID、两条线路 ID 与原工作区一致，CDB/脚本 manifest/DLL 哈希一致。Rabbit 固定512节点重新分析返回5条可重放线路；另外重放既有 Rabbit v2与 Phantom v1报告均通过。临时副本仅携带明确冻结前提和兼容性参考报告，没有复用原 target/dist；验收后清理。使用方法与约束见 [BREAK_SWORD_VERIFICATION.md](BREAK_SWORD_VERIFICATION.md)。详细运行报告保持在忽略的 data/runtime/，数据库、Lua、DLL、个人配置及报告均不进入 Git。

## 首版验收记录（历史）


最后复验：2026-10-14，Windows x64，Python 3.14.7。以下为实际本机与独立 checkout 结果，不代表远程 CI。2026-10-07 的 Python 依赖阻塞已解决，不再是当前阻塞。

## 源码、测试与审查

源码基线提交 `1db8cd8`；语义规划实现提交 `e43ab7594aa4e8b8d4be612e26344e6ab0b93950`。源码、锁文件、脚本、Schema、CI、文档和可分发夹具进入 Git；本机配置、数据库、Lua、DLL、快照、部署包和运行报告仍忽略。

| 检查 | 结果 |
|---|---|
| `cargo fmt --all -- --check` | 通过 |
| `cargo clippy --workspace --all-targets --offline --locked -- -D warnings` | 通过 |
| `cargo test --workspace --offline --locked` | 58 passed、0 failed、4 ignored |
| opt-in `live_engine` / `live_planner` / API `planning` | 分别 1 / 1 / 2 passed |
| Python 默认 unittest discovery | 7 项：5 passed、2 skipped |
| `YGO_LIVE_ENGINE=1` Python 全量 | 7 passed、0 skipped |
| Python 卡片夹具 validate | 2 张通过 |
| 新知识、请求及实际规划报告 Schema | 通过；缺理由、缺事前局面、伪造 outcome 三项负例拒绝 |

默认 Rust/Python 测试不携带本机资产；真实引擎和实际快照/报告检查必须显式启用。Python 环境需要项目 test extra 中的 jsonschema；本轮使用已安装依赖，未升级冻结引擎或数据。

回归覆盖：检索/送墓过滤及剩余资源、等级与阶级/连接区别、费用与效果送墓、墓地主动与事件触发、次数共享、Shade 墓地限制、素材消耗、Rusty 素材限制及复活后离场除外；同卡效果编号/实例位置、费用与对象提示、洗牌身份不确定、安全降级；v2 请求/预算/版本/验证状态和决策一致性，v1 原始选择与语义标签/事前证据绑定。

一次独立审查发现四项重要问题：预算或 worker 失败丢失未观察预测、线路重放绕过共享限额、语义标签未严格绑定实际动作、手牌洗牌位置过期。四项均先复现失败，再修复并通过回归。部分嵌套观察消息与旧 v2 Schema 较宽松这一小项保留后续处理，Rust 合同与实际重放提供更严格检查。修复后执行者复验全部检查，没有再进行第二轮审查。

## 冻结版本与独立干净 checkout

在独立目录本地 clone 实现提交，确认 tracked 工作树干净。仅准备这些明确的外部前提：冻结 `cards.cdb`、`scripts.json`、`script/`、x64 `engine/` 及固定 LFLists Git 缓存。未复制旧 target、dist、个人配置或快照。随后独立执行默认测试、格式/Clippy、`deploy-local.ps1 -Offline -FrozenRuntime`，重新生成 release CLI/worker、本机配置和数据快照。

这次验证重新编译了 Rust CLI/worker，复用了冻结 DLL；没有声称从零编译 ocgcore 或在无资产/无 Cargo 缓存的机器上完成联网安装。首次 engine 编译和联网准备前提见 [DEPLOYMENT.md](DEPLOYMENT.md)。复制尚未结束时部署拒绝缺少 manifest；资产就绪后完整重跑成功。

| 资产/检查 | 固定值或结果 |
|---|---|
| core / Lua | `38d04c9feb1a26617407091380634c87262fe3f8` / `6e22fedb74cf0c9b6656e9fce8b7331db847c605` |
| core ABI | API 11.0、x64；doctor assets_ok=true、abi_ok=true、ready=true、issues=[] |
| LFLists | `1051a65ab853fd84521aa919d1859f9468816c56`；OCG 2026-10-01 |
| catalog | 13,665 张；`catalog-1b0564fd61eec4730828fea1d48391aa1598bca3157c255454a8dcf487485d6d` |
| banlist | 203 项；`banlist-c98f770b366fed87be0fb23357a63d704db58b31508fbb88133fda66575f3783` |
| knowledge | 12 张、21 条效果、14 支持；`knowledge-f6b43abb829ce5f6b25e1a77d5840604edd1afeb837b04a9bfaaf799750e4f73` |
| 独立来源校验 | CDB、脚本 manifest、DLL 哈希与原工作区一致；12 张效果正文/脚本引用校验通过 |
| 独立 engine smoke | 3 条完整重放线路；墙钟截断，只作为可用性检查 |
| Rabbit 固定 512 节点分析 | 512 节点、517 次调用、5 条线路独立 replay 通过，终止 node_budget |
| Phantom 固定 512 调用预算 | 8 个事前方案、224 次调用、2 条目标达成且独立重放线路 |
| Phantom 再次 plan-replay | 2 条线路、29 个去重前缀见证、31 次共享预算调用，通过 |

独立 checkout 的 Phantom 知识/快照及线路 ID 与原工作区相同：

- `3f2695617463042fffe688ac4eb568a63874a8f6848e3af50752d07e2fcac3d5`
- `939ce100f739993ba3831f3e45064e4d41a8b2d274d0b36c43798ca18bfc7817`

原工作区既有 Rabbit v2 报告的五条线路也再次重放通过。独立 checkout 同样通过 58 项默认 Rust、4 项 opt-in Rust 和 Python 7 项全量检查。临时 checkout 验收后清理；当前工作区运行报告保存于忽略的 `data/runtime/`。

## 固定预算对照

同一 Phantom 输入、seed=1、冻结版本和配置 node_budget=512：

| 入口 | 返回的验证线路 | Rusty 在场且 Fog 盖放 | 总引擎调用 |
|---|---:|---:|---:|
| `combo plan` | 2 | 2 | 224 |
| 旧 `combo analyze` beam | 5 | 0 | 517 |

旧 beam 的 rabbit-v1 评分没有该终场目标，且其节点预算不含最终重放；新规划预算含执行和重放。这是目标闭环能力对照，不是相同目标评分下的算法优劣证明。未把墙钟耗时波动当作性能改善。有限方案/frontier/符号展开可能遗漏有效线路，不保证全局最优。

## 复验命令

```powershell
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --offline --locked -- -D warnings
cargo test --workspace --offline --locked
cargo test -p ygo-engine-adapter --test live_engine --offline --locked -- --ignored
cargo test -p ygo-planner --test live_planner --offline --locked -- --ignored
cargo test -p ygo-api --test planning --offline --locked -- --ignored
$env:PYTHONPATH='python'
py -m unittest discover -s tests -p 'test_*.py'
$env:YGO_LIVE_ENGINE='1'
py -m unittest discover -s tests -p 'test_*.py'
./scripts/deploy-local.ps1 -Offline -FrozenRuntime
./dist/ygo-local/ygo.cmd knowledge validate
./dist/ygo-local/ygo.cmd combo plan --input tests/fixtures/phantom.request.json --output data/runtime/phantom-plan-report.json
./dist/ygo-local/ygo.cmd combo plan-replay --input data/runtime/phantom-plan-report.json
```

首版范围、未支持效果及报告证据区别见 [SEMANTIC_PLANNING.md](SEMANTIC_PLANNING.md)。实际执行成功不能证明全部人工语义条目正确，固定起手验收也不代表所有合法起手、对手回合或手坑处理。
