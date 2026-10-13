# 本机验证记录

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
