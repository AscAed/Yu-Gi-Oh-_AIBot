# 幻影骑士团语义规划首版

范围提示：本页保留v1合同及其阶段取舍，文末“后续顺序”仅是当时安排。当前产品目标见[PRODUCT_VISION](PRODUCT_VISION.md)，跨阶段依赖见[ROADMAP](ROADMAP.md)；中文工作台不再统一延期到所有研究之后。

本版在真实引擎底座上加入人工效果知识和有限因果规划。范围为 OCG/MR5、完整合法牌组、固定五张起手、先攻首回合及惰性对手。默认目标是 Rusty Bardiche 在场、Fog Blade 已盖放。规则仍由固定 ocgcore 执行。

本页描述 v1 范围，Break Sword 的最新 v2 支持、真实效果验真及合成对方场景见 [BREAK_SWORD_VERIFICATION.md](BREAK_SWORD_VERIFICATION.md)。下文的 Break Sword 未支持说明仅适用于 v1。

## 使用

已有冻结资产时，在仓库根目录运行：

```powershell
./scripts/deploy-local.ps1 -Offline -FrozenRuntime
./dist/ygo-local/ygo.cmd knowledge validate
./dist/ygo-local/ygo.cmd card explain --id 58699500 --output data/runtime/cherubini-explain.json
./dist/ygo-local/ygo.cmd combo plan --input tests/fixtures/phantom.request.json --output data/runtime/phantom-plan-report.json
./dist/ygo-local/ygo.cmd combo plan-replay --input data/runtime/phantom-plan-report.json
```

`--knowledge` 可指定知识文件，部署 wrapper 使用包内文件；`card explain` 输出目录过滤候选和条件联动，实际对象仍须存在于当前区域并满足引擎限制。牌库候选排除额外怪兽；阶级和连接值不当作等级。

规划输入在旧 Combo 请求外增加 v1 包装、目标、知识 ID、最多 8 个方案及最多 32 个语义步骤。示例牌组的普通怪兽是合法性填充，不是实战构筑推荐。请求、结果和知识合同分别为 `plan-request`、`plan-result`、`knowledge` Schema。

## 工作方式与证据

`ygo-knowledge` 保存十二张卡的人工解释、逐效果范围、CDB 效果正文哈希、正式 Lua 文件哈希及测试案例引用。正文只从本机冻结 CDB 读取，不随源码分发。14 个可规划的主要效果有符号资源案例；来源校验成功不等于全部知识获得真实引擎证明。

`ygo-planner` 使用区域、卡片实例、资源消耗、次数及触发窗口构造方案。未知卡效保持缺口，未知元数据不能满足条件；准确祖先循环停止，历史不同的状态不合并。启发式 frontier 最多 32，符号状态展开最多 5000；这些限制可能漏掉方案。

引擎调用前保存方案和每个选择的局面、前缀哈希、候选比较及后续资源使用。引擎提示的效果描述编号与位置从原始帧旁路解码，按实际合法响应绑定；费用送墓、效果送墓、主动墓地效果和事件触发分别处理。预测失败切换到预先生成的有限备选，保留反例，不静默改为无依据穷举。

报告分为 `proposals`、`attempts` 和内嵌的旧 v2 `analysis`。未观察到执行结果的选择明确标为 `unobserved`，例如预算耗尽或 worker 错误；它不能成为成功线路的证据。成功线路必须满足实际目标、完整解码且独立重放一致。

`plan-replay` 重新生成符号方案，重建动作与语义步骤的绑定，重放终场，并独立执行去重后的决策前缀以核对执行前局面。整条重放流程共享节点/时间限额。手牌洗牌会更新唯一实例的位置；同名实例无法恢复身份时停止并标出未绑定，而非猜测。

推荐顺序是目标达成、手牌/场上卡片资源、实际决策数、稳定线路 ID。墓地可用资源单列。内嵌 v2 的 rabbit-v1 分数仅保留旧合同与重放兼容性；`--scoring` 不改变目标规划的排序规则。评分不是胜率，盖放 Fog Blade 不证明已经验证了对手回合无效能力。

## 范围与已知限制

十二张卡含 Torn Scales、Silent Boots、Ancient Cloak、Ragged Gloves、Stained Greaves、Shade Brigandine、Fog Blade、ROTA、Foolish Burial、Cherubini、Break Sword、Rusty Bardiche。支持范围按效果而非整张卡声明：Break Sword 超量/破坏复活规划、Fog Blade 对手回合效果、部分攻守/保护/破坏效果保留条件说明并标为 unsupported。首版不提供手坑策略、残缺牌组补全或全局最优保证。

新报告顶层、预测与知识合同有结构约束；旧 v2 和部分观察消息的嵌套 Schema 仍较宽松。Rust 合同、原始提示核对、语义绑定重建和真实重放承担更严格的验证。进一步收紧嵌套 Schema 是后续小项。

## 验证与对照

```powershell
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --offline --locked -- -D warnings
cargo test --workspace --offline --locked
cargo test -p ygo-engine-adapter --test live_engine --offline -- --ignored
cargo test -p ygo-planner --test live_planner --offline -- --ignored
cargo test -p ygo-api --test planning --offline -- --ignored
$env:PYTHONPATH='python'; $env:YGO_LIVE_ENGINE='1'
py -m unittest discover -s tests -p 'test_*.py'
```

同一固定起手、seed、版本和 512 节点配置下，对比 `combo plan` 与旧 `combo analyze`，记录目标达成和含重放的总引擎调用。旧 beam 的 rabbit-v1 排序没有本版目标，因此这个对照证明新增目标闭环的能力，不证明在相同目标评分下算法全面优于 beam。旧 beam 节点预算不含最终候选重放，规划器将执行与重放调用一起计入预算。

后续顺序为指定单次手坑及恢复、多起手验证、残缺构筑诊断与优化，最后服务/API 与网页。每一步沿用来源版本和独立重放证据。
