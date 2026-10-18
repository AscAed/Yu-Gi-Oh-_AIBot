# 幻影骑士团逐效果验真与 Break Sword v2

范围提示：本页保留v2专项及当时限制，不覆盖后续v3–v5能力或现行待办。当前任务见[TASKS](../TASKS.md)，产品顺序见[ROADMAP](ROADMAP.md)；历史延期不阻止中文工作台独立实施。

本轮保留人工语义和有界规划，目标仍为 Rusty Bardiche 在场、Fog Blade 盖放。未加入手坑、完整后攻策略、自动构筑或通用目标。知识 profile `phantom-v2` 的16个支持效果，各有人工编写的真实操作案例；实际证据单独输出，不把源码中的假设自动改为已证明规则。

## 场景与兼容

新规划请求/报告为 v2，内嵌分析为 v3，worker 协议为 v3；知识 JSON 结构版本仍为1，profile区分 v1/v2。原规划 v1、分析 v2、worker v2 的读取与重放保留，旧线路身份不迁移。新版线路哈希包含初始化版本及场景。

`scenario=null` 保留对方空场。`scenario="ryu-ran"` 将对方占位牌库的一张 Ryu-Ran 放到对方怪兽区0、表侧攻击表示，对方无手牌且不主动响应。它是合成局面，不代表完整后攻对局；牌库缺少该卡时拒绝。不同场景不共享线路身份。

## 运行

```powershell
./scripts/deploy-local.ps1 -Offline -FrozenRuntime
./dist/ygo-local/ygo.cmd knowledge verify --cases tests/fixtures/phantom.engine-cases.json --output data/runtime/effect-verification.json
./dist/ygo-local/ygo.cmd combo plan --input tests/fixtures/break-sword.request.json --output data/runtime/break-sword-report.json
./dist/ygo-local/ygo.cmd combo plan-replay --input data/runtime/break-sword-report.json
```

`knowledge validate` 只验证结构、来源和引用；`knowledge verify` 在冻结引擎中执行给定案例并独立重放。自定义案例通过只代表那些案例，不能推出全部16个效果均已通过。完整矩阵为 `phantom.engine-cases.json`，八个人工终场基准与另外八个受限/降级案例为 `phantom.fixed-hands.json`。二进制测试前先离线 release build，以提供当前 worker。

```powershell
cargo build --release --workspace --offline --locked
cargo test -p ygo-api --test effect_verification --offline --locked -- --ignored
cargo test -p ygo-api --test break_sword_live --offline --locked -- --ignored
cargo test -p ygo-api --test fixed_hands --offline --locked -- --ignored
```

## 证据与边界

验真操作步骤独立于规划器编写；准备过程由引擎执行。发动前从实际检查点生成符号操作预测，再检查结算后的资源投影及人工断言，并重放整段决策和发动前缀。结算后反例检查次数、来源区域或触发窗口已不满足时，不再提供相同发动。反例只覆盖明确列出的条件，不宣称穷尽全部条件组合。

超量素材有实例和宿主，取除费用与破坏事件分开；宿主离场后素材送墓。Break Sword 必须实际超量召唤后在怪兽区被破坏，才能产生复活窗口。复活两张同等级幻影骑士团、等级各增加1、此后只可特殊召唤暗属性怪兽。素材成为叠放状态不当作送墓；复活后的离场除外不直接套用于叠放。v3 查询真实等级/阶级并核对素材，破坏对象及玩家限制提示由冻结协议帧解析。

受控场景为超量历史保留部分 frontier 与候选配额，避免直接 Rusty 捷径占满8个方案；仍最多32个 frontier、5000次符号展开和32个语义步骤。此项取舍减少其它分支的搜索空间，不保证最优。对方空场时不提高无法发动破坏效果的 Break Sword 路线优先级。

Greaves 的可选增级分支仍只采用“不增加等级”的规划选择；对手中断、对象在连锁中失效、保护/战斗及其余五个未支持效果未覆盖。实际线路成功不等于所有语义分支正确。

失败分类区分规则拒绝、覆盖缺口、预测不符、提示未绑定、预算耗尽、引擎失败与未找到方案。未找到方案不是全局不可行证明。每个执行请求的执行与独立重放共享预算；固定起手验收另外记录人工基准和外部重放调用，并检查每例合计不超过512次。

## 审查取舍

基准步骤由实施代理手工整理，独立于规划器生成；尚未经过另一位人类决斗专家的策略审阅。它们用于检查可执行性和目标达成，不证明策略最优。

已修复审查发现的同名素材移动、嵌套 Schema 和 worker 异常分类问题，并以失败回归及真实同名 Boots 素材完整链复验。修复后不再进行第二轮审查，执行者负责全量及干净 checkout 验收。

保留的小项：v2 `combo plan` 当前接受 `--scoring`，但内嵌旧评分仍使用默认权重；目标/资源/决策排序不受该参数影响。自定义旧评分配置的应用留待后续，当前不要依赖此参数改变 v2 内嵌分数。
