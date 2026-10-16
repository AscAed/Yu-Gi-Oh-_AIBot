# 首回合规则验真（实施中）

`knowledge validate --knowledge knowledge/tournament-2026.knowledge.json`只检查结构、来源和冻结引用。它不执行效果，也不读取某条成功线路来提升知识包状态。

新包的`knowledge verify --knowledge … --cases … --output … --store …`按独立原生案例执行。每例明确完整合法牌组、五张起手、seed1、人工准备决策、被测选择、预期断言、观察窗口和覆盖限制；当前案例固定标为`independent_rule_verification`，不能计入赛事样本或人工赛事基准。

本机开发配置须指向当前编译的worker与独立2026资产组。旧部署worker不支持v6；不得仅更换卡库后直接使用旧worker。

```powershell
cargo build -p ygo-cli -p ygo-engine-adapter --offline --locked
$env:YGO_ENGINE_CONFIG='data/runtime/tournament-2026/engine-development.toml'
target/debug/ygo-cli.exe knowledge validate --knowledge knowledge/tournament-2026.knowledge.json
target/debug/ygo-cli.exe knowledge verify --knowledge knowledge/tournament-2026.knowledge.json --cases tests/fixtures/tournament-2026.rules-resource.json --output data/runtime/tournament-2026/resource-verification.json --store data/runtime/tournament-2026/snapshots
```

开发配置是本机文件，需使用已有冻结资产的实际路径，并将worker指向`target/debug/ygo-engine-worker.exe`。本轮不覆盖旧部署目录；最终双资产部署仍待实现。

每例512次调用上限，输出旁的`.calls`目录保存独立账本及内容寻址证据。调用前落盘扣费，结果不明仍计费；再次运行同一目录复用安全检查点。原生失败结果也保留，worker内容哈希改变后使用不同核算身份。崩溃的不明调用可以披露后继续，但不退款，重试再次收费。

正例必须在实际提示中绑定源实例；可发动效果还须出现对应的真实发动、连锁处理与结算，且未被无效。通用确认码221只表示待确认触发，案例先声明预期，随后用真实连锁登记核实；它不能单独证明效果编号。费用和效果移动分别断言，素材多重集绑定到同一宿主，等级／阶级和状态直接取实际查询。

负例检查声明窗口内没有相应合法动作，同时保存资源／事件断言和具体条件。后续空闲窗口没有召唤触发，只证明该窗口不能发动，不能扩大为所有条件或所有时点都已验证。

每个成功案例分别重放发动前见证和执行结果。Rust `verify_report`进一步校验导入报告的源、引用、预算和原始证据，并在独立审计目录重新执行；审计不使用原执行缓存，每轮新增调用单独收费。JSON Schema检查形状，Rust合同重新计算身份、覆盖、调用角色和状态。

合同使用`first-turn-cases.schema.json`、`first-turn-runtime.schema.json`及`first-turn-verification.schema.json`；旧协议不变。新合同对旧共享类型的嵌套字段额外收紧，不修改旧请求的序列化与身份。

当前12个案例覆盖6项规则，报告仍列出80项缺少成对案例。`rules-resource.contract.json`是删去本机绝对路径的合同夹具，不提供真实日志，不替代本机验真报告。原生案例通过也不代表规划器转移已实现；知识包维持未完成验真的状态，v6自主规划与48手评估继续实施。

## 首批因果模型对照

`ygo-planner::first_turn`目前仅注册上述6项规则。转移保存费用后的资源和假定结算后的资源，不把牌库送墓、取除素材或成为素材混为一类。未知等级或召唤限制不生成有效候选；可选触发放弃不消耗次数，目标已耗尽不凭空创建触发。

本机专项`cargo test -p ygo-planner --test first_turn --offline --locked -- --ignored --nocapture`从公开初态生成预测，先保存到持久账本，再执行独立人工准备步骤，分别检查资源和重放。它是转移模型的对照实验，不是规划器自行选择的路线；没有做出默认目标，也不提供恢复状态验收。当前还需扩展其他规则、完整事件／限制重建、自动搜索与提示绑定。
