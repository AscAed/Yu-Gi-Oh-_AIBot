# 通用目标与有界收益规划

范围提示：本页是v3目标合同与当时验收边界，不代表通用卡效或全局最优证明；文末下一阶段为历史安排。当前产品目标和执行顺序见[PRODUCT_VISION](PRODUCT_VISION.md)、[ROADMAP](ROADMAP.md)。

## 已确认的交付合同

当前规划 profile 为 `phantom-goal-v2`，请求/报告仍为 v3。旧 `phantom-goal-v1` 本地报告含已知历史证据缺陷，仅保留诊断用途；新入口明确要求重新生成。旧规划 v1/v2 的身份和重放算法不变。

本阶段在 `fc4ff57` 的十二卡、16项支持效果和 Break Sword 验真底座上增加独立目标层。新规划请求/报告为 v3，内嵌分析v3、运行协议v3；不升级冻结 core、Lua、CDB 或禁限表。旧规划v1/v2、Rabbit 与 Phantom 报告继续按原版本读取与重放。

目标表达式决定候选生成、优先级、实际终场检查和报告重放。默认目标示例为 Rusty＋盖放 Fog Blade，第二目标为 Cherubini＋盖放 Fog Blade，使用相同完整牌组与五张起手。其余边界仍是 OCG/MR5、先攻首回合、无主动对手响应；Ryu-Ran 是合成验证场景。

## 使用

```powershell
./scripts/deploy-local.ps1 -Offline -FrozenRuntime
./dist/ygo-local/ygo.cmd combo plan --input tests/fixtures/goal-cherubini.request.json --output data/runtime/goal-cherubini-report.json
./dist/ygo-local/ygo.cmd combo plan-replay --input data/runtime/goal-cherubini-report.json
./dist/ygo-local/ygo.cmd combo plan --input tests/fixtures/goal-continuation.request.json --output data/runtime/goal-continuation-report.json
```

输入继续使用 `analysis` 保存合法完整牌组、五张起手、seed、规则、快照与预算。v3 必须提供结构化 `goal`，例如：

```json
{
  "version": 1,
  "expr": {
    "op": "all",
    "args": [
      {"op": "count", "filter": {"codes": [58699500], "locations": [4], "position_mask": 5}, "min": 1},
      {"op": "count", "filter": {"codes": [25542642], "locations": [8], "position_mask": 10}, "min": 1}
    ]
  },
  "continuation_steps": 4,
  "max_aux_candidates": 8,
  "gain_order": []
}
```

配置优先级为 `--scoring`、`YGO_SCORING_CONFIG`、内置默认值；v2 和 v3 均应用实际配置。该配置仅控制内嵌旧诊断分数，仍标为启发式，不替代目标、真实收益或推荐排序。

## 表达式与事实口径

- `all.args`、`any.args`、`not.arg`：三值逻辑；`not(unknown)` 为 unknown。空布尔组合拒绝。
- `count`：`filter`、`min`、可选 `max`；按符合条件的实例计数。筛选可指定卡号集合、控制者、区域、表示掩码、实例、实际等级/阶级、当前超量历史、宿主素材数量及素材卡号多重集。
- `history`：`kind`、筛选、可选 `effect_id`/`reason_mask`、数量范围。种类为 normal_summon、special_summon、link_summon、xyz_summon、destroyed、sent_to_grave、effect_resolved。
- `available`：`effect_id`、`filter`、`window`；首版真实探测窗口仅为 `main_end`。未知窗口、未支持效果、不入连锁的 Boots 召唤手续返回 unknown，不冒充“不能发动”。
- `continuation`：事实/历史 `goal`、`gains` 和可选 `max_steps`。每个 gain 提供唯一 `id`、资源 `filter` 和有符号 `min_delta`；`gain_order` 必须按优先顺序列出所有 gain ID。

区域使用原协议数值：1牌库、2手牌、4怪兽区、8魔陷区、16墓地、32除外、64额外。`player` 默认0。未指定区域表示全部查询区域，叠放素材单独归宿主，不计为独立区域卡片；墓地存在不等于可发动。素材多重集保留同名数量。

事实条件检查实际终场。发动探测和后续分支从结束主阶段前、己方回合1/Main1、连锁已结算的 idle 提示取样。它们证明该窗口的机会，不能表述为结束阶段或对手回合仍能发动。

同名卡的等级、素材与历史不能跨实例拼接。身份无法连续追踪时，显式实例条件返回 unknown。Link/XYZ 不具有普通怪兽等级；非XYZ不具有阶级。历史属性只有证据足够才满足：召唤记录采用成功召唤时点；破坏记录采用原区域；送墓采用到达区域；效果结算绑定实际链解算及发动来源。历史等级等属性缺少当时查询时返回 unknown。

表达式最多64节点、8层；后续深度默认4、允许1—8步，必需触发计入步数。后续目标不能递归包含发动探测或另一个后续目标。Schema 校验结构及局部界限，Rust 合同另检查跨字段、总节点数、来源、身份和证据。

## 规划、收益与证据

规划复用已支持效果转移与原始提示绑定，按目标缺口安排候选，不通过目标名称添加卡号线路。历史上已经发生且不能撤销的约束冲突会剪枝；当前资源不足仍允许通过后续动作补足。不按可见场面合并不同历史；保留实例、次数、epoch、完整步骤和版本。

`forecasts` 在首次执行对应方案之前生成，标为 symbolic_prediction，记录每步之前的事实、目标缺口、预计贡献/损失、后续用途和分支收益预测。`executions` 保存实际提示、选择、响应字节、事件与检查点。`assessments` 保留每个已执行主方案的逐节点结果，包括失败与未知；`recommendations` 只引用已有完整独立见证的达标方案。

`catalog_projection` 是请求所用卡片的目录字段投影，不是新快照；重放须与原目录快照逐项一致。合同重新生成主方案、辅助方案和预测，检查理由与引用。辅助方案身份包含主阶段起点的完整前缀以及目标节点，不能把同一可见场面的不同历史混用。

召唤历史按原始召唤帧绑定每个实例，并在成功帧批量提交；同名实例不能互相替代。缺少成功帧或身份不明不会证明历史未发生。破坏历史保存 MOVE 前的区域和剩余素材；送墓历史保存目的状态，离场宿主不再持有素材。`effect_resolved.card` 是发动源快照：实例在费用前绑定，区域使用 CHAINING 帧的实际发动位置（手牌魔法不能仍写作手牌），素材在支付费用和选择对象后的 CHAINED 帧重建；`event` 则引用实际完成结算的帧。该快照不表示结算时源卡仍在发动区域。历史等级等未记录属性继续返回 unknown。

贡献及损失按条件节点披露：`not` 保留自身真值，不把其正向操作数当作目标；双重否定同样按整个否定条件求值。OR 的某个分支失去可以单独列出，但整体目标是否失去仍以完整表达式评估为准；unknown 不是确认满足或确认损失。

发动正例须完成实际合法费用、对象与结算，不能只看按钮名称。否定证据仅限完整、已支持窗口没有相应合法发动。未找到后续见证通常为 unknown，不是全局无解。

后续分支可以消费主终场资源。收益是从该分支起点到实际结果的卡片数量净变化，费用和素材损失不会忽略。报告列出失去的主目标节点；不把该分支的终场当作原主线路终场。一个 continuation 的所有子目标和收益阈值必须由同一个分支满足；多个 continuation 是分别存在的机会，其收益不相加。

推荐依次比较：目标成立、请求顺序的已验证收益向量、主终场手牌/场上资源数量、主线路与所选分支的决策成本、稳定ID。未知收益单列，排在有证据的收益之后，不视为零。收益及排序都是搜索范围内的已验证下界，不保证全局最优或实战战略价值。

## 预算、兼容与验收

固定验收为 seed1、512次共享引擎调用、最多8个主方案和每案32语义步。主规划与后续探索共用5000符号展开、frontier32；每请求最多8个辅助候选。预留独立前缀/分支重放以及外部 plan-replay 的调用，避免执行用尽预算后发布无法重放的推荐。后续失败或预算耗尽保留已完成的推荐及分类；有界未找到方案不代表无解。

`goal_id` 对目标、后续限制和收益顺序规范化；集合筛选排序去重，素材多重集不去重。新方案/推荐绑定目标和规划版本，底层执行ID继续使用协议v3的完整输入/决策身份。旧版本算法、原因文本和ID不重算；修改已发布的目标解释或规划政策时须增加语义/规划版本。

真实验收覆盖两个终场、发动与后续收益、初态满足、费用不足、牌库无目标、同名次数、Break Sword历史和未知窗口/预算降级。继续运行原16效果矩阵、16固定起手、旧报告重放及干净 checkout 部署。详细结果以 TESTING.md 的本轮最终记录为准。

Greaves 可选增级、保护/战斗、主动对手交互、未来回合、任意卡效解析、构筑优化和网页不在本轮。下一阶段为单次指定手坑与恢复，随后固定样本评估、构筑诊断。
