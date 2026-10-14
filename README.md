# Yu-Gi-Oh! AI

Windows 本机 Combo CLI：固定完整卡组与五张起手，使用固定 API 11.0 的 x64 ocgcore 执行先攻首回合、无干扰展开。新增幻影骑士团人工效果知识与因果规划：先提出带资源依据的目标方案，再绑定真实提示执行并独立重放。自动构筑、手坑和 HTTP 接口列入后续范围。

## Break Sword 与逐效果验真

新增 v2 规划与真实效果案例验真：16个支持效果分别记录符号预测、原生提示、结算后反例和独立重放；受控对方场面支持 Break Sword 超量、破坏、复活后继续达成目标。旧 v1 入口与报告仍可重放。使用、场景含义及范围见 [逐效果验真说明](docs/BREAK_SWORD_VERIFICATION.md)。

## 本机运行

在仓库根目录执行：

    ./scripts/build-engine.ps1
    ./scripts/deploy-local.ps1
    ./dist/ygo-local/ygo.cmd engine doctor
    ./dist/ygo-local/ygo.cmd combo analyze --input tests/fixtures/rabbit.request.json --output data/runtime/report.json
    ./dist/ygo-local/ygo.cmd combo replay --input data/runtime/report.json

已有冻结资产的语义规划入口：

    ./scripts/deploy-local.ps1 -Offline -FrozenRuntime
    ./dist/ygo-local/ygo.cmd knowledge validate
    ./dist/ygo-local/ygo.cmd combo plan --input tests/fixtures/phantom.request.json --output data/runtime/phantom-plan-report.json
    ./dist/ygo-local/ygo.cmd combo plan-replay --input data/runtime/phantom-plan-report.json

效果范围、决策依据、合同和限制见 [语义规划说明](docs/SEMANTIC_PLANNING.md)。

首次构建需要 Rust、Python 与 Visual Studio 2022 C++ x64 工具。构建脚本会在同一进程注入本地 Clash Verge 代理 127.0.0.1:7897；有缓存时可使用 -Offline。数据库、脚本、DLL、快照和个人配置保持在忽略目录；发布目录配置引用当前机器上的外部资产，部署包需要按本机路径重新生成。

完整安装步骤、命令及运行边界见 [部署说明](docs/DEPLOYMENT.md)。[任务表](TASKS.md)、[协议](docs/ENGINE_PROTOCOL.md)、[搜索与评分](docs/SEARCH_AND_SCORING.md)描述当前实现。[现状审查](docs/PROJECT_ASSESSMENT.md)、[验证记录](docs/TESTING.md)、[路线图](docs/ROADMAP.md)总结部署状态和后续计划。
