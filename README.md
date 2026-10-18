# Yu-Gi-Oh! AI

本仓库是 Windows 本机的 Yu-Gi-Oh! OCG/MR5 Combo 研究工具。当前包含真实 ocgcore 执行、固定起手的有限搜索、版本化知识/目标规划、报告重放，以及一个仍在内部集成阶段的新本家首回合规划器。

**能力边界：**当前不是自动构筑器，也不支持任意卡效、任意手坑、后攻或完整对局。新首回合模块的局部实验不代表正式 v6；符合规则的行为仍以真实引擎和独立重放为准。评分是启发式；有界搜索不能证明全局最优。

产品方向是中文本机浏览器卡组工作台，以及构筑与Combo评估反馈闭环。基础功能离线、大模型可选；最终AI要求冻结版本全部正式OCG与明确首回合情景的全局最优证明，该研究可行性尚未建立。详见[产品愿景](docs/PRODUCT_VISION.md)、[差距评估](docs/PROJECT_ASSESSMENT.md)和[分阶段实施计划](docs/superpowers/plans/2026-10-19-product-evolution.md)。编辑器等预览成果不能替代最终验收。

## 本机快速运行

需要 Windows x64、Rust stable、Python 3.10+、Git、Visual Studio 2022 C++ x64 工具及本机 Project Ignis 资产。配置和数据为本机路径，不进入源码库。

```powershell
./scripts/build-engine.ps1 -Offline
./scripts/deploy-local.ps1 -Offline -FrozenRuntime
./dist/ygo-local/ygo.cmd engine doctor
./dist/ygo-local/ygo.cmd combo analyze --input tests/fixtures/rabbit.request.json --output data/runtime/report.json
./dist/ygo-local/ygo.cmd combo replay --input data/runtime/report.json
```

首次准备引擎或依赖需要联网时，仓库脚本会在同一进程设置本机代理；细节与资产要求见 [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)。当前正式规划 v1–v5 示例、知识验真和特定 profile 的使用方式见对应功能文档。

## 开发验证

```powershell
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --offline -- -D warnings
cargo test --workspace --offline --locked
$env:PYTHONPATH='python'
py -m unittest discover -s tests -p 'test_*.py'
```

资产依赖测试需显式启用；所有测试状态和可复验命令集中记录在 [`docs/TESTING.md`](docs/TESTING.md)。

## 项目文档

从 [`docs/INDEX.md`](docs/INDEX.md) 开始。当前任务和功能门禁以 [`TASKS.md`](TASKS.md) 为准；模块能力和限制见 [`docs/PROJECT_ASSESSMENT.md`](docs/PROJECT_ASSESSMENT.md)，工作顺序见 [`docs/ROADMAP.md`](docs/ROADMAP.md)。
