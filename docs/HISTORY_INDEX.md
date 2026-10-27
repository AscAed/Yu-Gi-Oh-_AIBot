# 历史文档与证据索引

本文件承接[文档入口](INDEX.md)中的历史计划、交接与批次导航。**以下全部是历史资料，不是当前执行指令，也不授予运行旧命令、重试、续用窗口或新增调用的权限。** 当前状态与开放任务只看[任务表](../TASKS.md)，验证范围只看[TESTING](TESTING.md)对应记录；全卡与全局最优验收门槛以[产品愿景](PRODUCT_VISION.md)为准。

2026-10-27环境自检将原任务表与验证记录的完整正文分别逐字保存为[任务历史快照](../TASKS_HISTORY.md)和[验证历史快照](TESTING_HISTORY.md)。原入口保留原有历史标题及锚点，并链接到快照；快照是拆分时的工作区副本，不是先前原生源码归档。拆分清单和哈希见[TESTING](TESTING.md)。

## 历史资料的读取边界

- 表中“本批”“最近验证”“待续”等原标签均属于原记录的时间点；链接目标保持原样，不表示它仍是当前批次。
- 消费、完成、unknown、预留和规划值按各自日期、scope及固定账本分别解释。早期“累计24”等当时口径不能当作当前总消费，也不能与不同账本的数字直接相加；当前可认证口径见TASKS顶部和对应TESTING来源，未知值仍保留为`null`。
- 原交接、报告、账本、源码归档、来源manifest、原始进程输出和固定窗口是历史证据的组成部分。2026-10-27项目再规划只调整导航，不移动、不重写、不删除原材料；后续自检另行拆分入口并保留原文快照，也不扩大旧窗口或预算。
- “离线/合成/只读通过”与“原生可达/响应接受/独立重放/完整性/概率/最优性”分别取证，不能由前者推定后者。规范分别见[研究操作规范](RESEARCH_OPERATIONS.md)与[证据合同](EVIDENCE_CONTRACTS.md)。
- 最近已暂停的Ground Collapse批次入口留在[INDEX](INDEX.md)；它仅完成离线准备，旧准备报告不能直接用来启动原生实验。

## 2026-10-19：产品计划、基线审计与暂停快照

这些计划和暂停交接记录各自成文时的安排、原7次消费与固定时间窗。暂停快照中的待续顺序不是当前任务队列。

| 历史条目 | 原链接（保持原目标） | 当时状态与消费边界 |
|---|---|---|
| 历史：各阶段具体任务、输入/产出及验收 | [`产品演进计划`](superpowers/plans/2026-10-19-product-evolution.md) | 未来任务分解；完成状态仍只维护于TASKS |
| 历史：首批基线及可行性审计的实施边界 | [`基线审计实施计划`](superpowers/plans/2026-10-19-baseline-audit.md) | P0身份/清点/输入和P1.1/P2.1；不授予最优性或全卡资格 |
| 历史：用户暂停后的续接入口 | [`基线审计断点交接`](superpowers/plans/2026-10-19-baseline-audit-handoff.md) | 暂停时点快照、原7次消费、时间窗门禁和待续顺序；状态仍以TASKS为准 |

## 2026-10-19—2026-10-21：离线动作、Rabbit与终场研究

按准备、终场绑定、单例验真、首次阻断与续办的时间顺序阅读。独立scope、2次/4次/6次预算和零调用边界分别保留；旧窗口不延长、不续用。

| 历史条目 | 原链接（保持原目标） | 当时状态与消费边界 |
|---|---|---|
| 历史：P1离线动作修复和小问题准备 | [`P1实施计划`](superpowers/plans/2026-10-19-p1-actions-offline.md)、[`候选问题`](P1_MICROCASE.md) | 本批不新增原生调用，不实现求解器；当前状态仍在TASKS |
| 历史：快照目标、终场诊断和独立小批回归 | [`快照与原生计划`](superpowers/plans/2026-10-20-snapshot-native.md)、[`研究工具`](RESEARCH_AUDIT.md) | 快照计数、终场绑定与原生线路资格分别验收；状态仍在TASKS |
| 历史：精确终场查询绑定及候选研究合同 | [`终场绑定计划`](superpowers/plans/2026-10-20-terminal-binding.md)、[`本批断点`](superpowers/plans/2026-10-20-terminal-binding-handoff.md) | 显式研究采集与6次独立预算；不提升完整性或最优性 |
| 历史：Rabbit修复后的单例验真 | [`两次验真计划`](superpowers/plans/2026-10-20-terminal-smoke.md)、[`本批断点`](superpowers/plans/2026-10-20-terminal-smoke-handoff.md) | 独立2次scope，执行通过完整门禁后才重放；旧窗口不续用 |
| 历史：赛事/洗手牌后结束的初次入口 | [`四次计划`](superpowers/plans/2026-10-20-terminal-followup.md)、[`历史断点`](superpowers/plans/2026-10-20-terminal-followup-handoff.md) | 首次离线交付和零消费阻断保留；后续续办见下行 |
| 历史：独立历史核验及四次续办 | [`核验与续办计划`](superpowers/plans/2026-10-21-history-followup.md)、[`本批断点`](superpowers/plans/2026-10-21-history-followup-handoff.md) | 用户明确接受只读完整性核验；原runner来源不补签，实际验真结果见TASKS/TESTING |
| 历史：受限可见信息、理想洗手牌概率及顺序审计 | [`离线实施计划`](superpowers/plans/2026-10-21-information-offline.md)、[`研究工具`](RESEARCH_AUDIT.md) | 两个Rabbit idle前缀；数学模型与原生概率资格分离，零新增原生调用 |
| 历史：洗手牌后结束线路观察与终场衔接 | [`线路实施计划`](superpowers/plans/2026-10-21-shuffle-route-offline.md)、[`本批断点`](superpowers/plans/2026-10-21-shuffle-route-offline-handoff.md)、[`研究工具`](RESEARCH_AUDIT.md) | 独立配置，两个己方决策与无后继终止视图；不扩展其他分支 |
| 历史：剩余提示的静态候选与阻断 | [`准备计划`](superpowers/plans/2026-10-21-prompt-probes-offline.md)、[`本批断点`](superpowers/plans/2026-10-21-prompt-probes-offline-handoff.md)、[`研究工具`](RESEARCH_AUDIT.md) | 三个候选仅静态准备，命令6阻断；不含原生执行入口或新预算 |

## 2026-10-21—2026-10-23：天玑提示与runner故障链

按初次opcode13、placement、历史锚点诊断、confirmation超时、runner修复、独立validation scope顺序阅读。后续新scope通过不改写前次失败、零消费或剩余槽位封存结论。

| 历史条目 | 原链接（保持原目标） | 当时状态与消费边界 |
|---|---|---|
| 历史：天玑opcode13验真与离线合同收尾 | [`实施计划`](superpowers/plans/2026-10-21-tenki-prompt-probe.md)、[`历史暂停断点`](superpowers/plans/2026-10-22-tenki-prompt-probe-handoff.md)、[`收尾断点`](superpowers/plans/2026-10-22-tenki-prompt-probe-recovery.md) | 实际2次停在区域18；空标签schema兼容修复及原证据零调用复验完成，余4槽封存 |
| 历史：天玑公开区域选择、opcode13两分支及重放 | [`本批实施计划`](superpowers/plans/2026-10-22-tenki-placement-native.md)、[`原暂停断点`](superpowers/plans/2026-10-22-tenki-placement-native-handoff.md)、[`恢复断点`](superpowers/plans/2026-10-22-tenki-placement-native-recovery-handoff.md)、[`v2执行断点`](superpowers/plans/2026-10-22-tenki-placement-native-v2-handoff.md) | v2单文件迁移和离线准备通过；stage 1 runner在收费前失败，新增消费0，六阶段未通过 |
| 历史：天玑历史锚点修复与stage 1只读预检 | [`零调用诊断断点`](superpowers/plans/2026-10-22-tenki-placement-diagnostics-handoff.md)、[`原生v2执行断点`](superpowers/plans/2026-10-22-tenki-placement-native-v2-handoff.md) | 66位历史常量根因已修复，冻结stage 1预检通过且native_calls=0；不改变原生失败结论或资格 |
| 历史：天玑placement confirmation新scope六阶段验真 | [`本批断点`](superpowers/plans/2026-10-23-tenki-placement-confirmation-handoff.md) | prepare-only及离线验收通过；stage 1 runner超时且输出为预检格式，账本零消费，停止且不续用剩余槽 |
| 历史：天玑runner单JSON输出、剩余窗口超时与零调用审计 | [`本批断点`](superpowers/plans/2026-10-23-tenki-runner-repair-handoff.md)、[`最近验证`](TESTING.md) | 8项只读审计检查通过；原normal结果仍为`runner_timeout`，本批仅运行预检，native_calls=0 |
| 历史：天玑完整路径六阶段新scope验真 | [`实施计划`](superpowers/plans/2026-10-23-tenki-placement-validation.md)、[`本批断点`](superpowers/plans/2026-10-23-tenki-placement-validation-handoff.md) | 冻结天玑前缀的六阶段提示/响应与两分支独立重放已通过；不代表完成检索/终场或全局完整性 |

## 2026-10-24—2026-10-25：Curry冻结输入、风险预留与首次原生验证

先读合成恢复及风险预留，再读原生verification scope。合成通过不授予真实消费认证；历史实际累计和旧confirmation消费未知的状态不能用规划或预留值替代。

| 历史条目 | 原链接（保持原目标） | 当时状态与消费边界 |
|---|---|---|
| 历史：Curry v2冻结输入恢复审计与公共合成验收（历史） | [`合成验收交接`](superpowers/plans/2026-10-24-curry-recovery-synthetic-e2e-handoff.md)、[`完成记录`](superpowers/plans/2026-10-24-curry-recovery-synthetic-e2e-complete.md) | 合成审计路径已通过；不等于本轮风险预留成功，也不改变旧confirmation消费未知状态 |
| 历史：Curry V2风险预留恢复与零调用验收（历史） | [`本批续接断点`](superpowers/plans/2026-10-25-curry-consumption-reservation-v2-handoff.md)、[`最近验证`](TESTING.md) | V2合成恢复与全量Python通过；唯一真实只读审计在`independent_review_invalid`停止，预留未记录、全部实际累计仍未知，native_calls=0；V1失败原件保留 |
| 历史：Curry V3材料兼容与零调用风险预留验收 | [`本批续接断点`](superpowers/plans/2026-10-25-curry-consumption-reservation-v3-handoff.md)、[`最近验证`](TESTING.md)、[`交付验收`](../data/runtime/p1-curry-consumption-reservation-v3-offline-2026-10-25/delivery/acceptance.json) | V3真实只读审计与verify通过，预留7、规划39；历史实际累计和旧confirmation消费仍为null，native_calls=0；旧V1/V2失败件保留 |
| 历史：Curry V3预留绑定的Curry七阶段验证（原生历史） | [`本批断点`](superpowers/plans/2026-10-25-curry-option-verification-handoff.md)、[`最近验证`](TESTING.md) | stage 1消费1次通过；stage 2在收费前因Windows共享冲突退出，新增消费1、未知0；verify-only为不完整报告，余6槽封存、不重试 |

## 2026-10-25—2026-10-26：Curry账本交接失败与恢复链

按V1→V2→V3→V4→V5交接，再按首次恢复→恢复V2→恢复V3阅读。各报告、源码归档、固定来源角色和账本均保留自身身份；后来的修复不覆盖前一失败报告。原scope stage 2收据缺失、一次尝试及不重试约束随各自交接保留。

| 历史条目 | 原链接（保持原目标） | 当时状态与消费边界 |
|---|---|---|
| 历史：Curry V1账本交接恢复审计（历史） | [`原断点`](superpowers/plans/2026-10-25-curry-ledger-handoff-handoff.md)、[`历史验证`](TESTING.md) | 原V1报告仍为`acceptance_delivery`失败；保留其原报告、源码和证据绑定，不由V2状态覆盖 |
| 历史：Curry V2账本交接恢复审计（历史） | [`本批断点`](superpowers/plans/2026-10-25-curry-ledger-handoff-v2-handoff.md)、[`最近验证`](TESTING.md) | 离线总检和审阅通过；唯一真实只读审计在`previous_failed_source`因V1 runner角色路径不符而停止，runner未启动、native_calls=0；V1归档根因状态另有静态不一致，原scope仍stage 1消费1、stage 2收据缺失 |
| 历史：Curry V3来源角色修复与只读验收（历史） | [`本批断点`](superpowers/plans/2026-10-26-curry-ledger-handoff-v3-handoff.md)、[`历史验证`](TESTING.md) | 来源链与离线总检通过；唯一真实只读审计在`stage1_parent_receipt`因真实V3 stdout附加会计字段不被旧三字段比较接受而停止，saved-input runner未启动、native_calls=0；禁止该目录重试 |
| 历史：Curry V4精确输出合同与零调用验收（历史） | [`本批断点`](superpowers/plans/2026-10-26-curry-ledger-handoff-v4-handoff.md)、[`历史验证`](TESTING.md) | V4真实审计在`previous_v3_failed_source`因固定根额外文件停止，runner未启动；报告与原目录保持原样 |
| 历史：Curry V5干净交付与单次零调用验收（历史） | [`本批断点`](superpowers/plans/2026-10-26-curry-ledger-handoff-v5-handoff.md)、[`历史验证`](TESTING.md) | V5原报告仍缺失；旧外层退出2的具体内部异常未认证，旧runner只读输出与本轮恢复结果分开记录 |
| 历史：Curry V5已存证据恢复与报告发布诊断（历史） | [`恢复交接`](superpowers/plans/2026-10-26-curry-ledger-handoff-recovery-handoff.md)、[`最近验证`](TESTING.md) | 离线恢复器、合成路径、全套Python及独立审阅通过；唯一真实纯Python恢复在`v5_delivery_and_archives`以`recovery_v5_source_delta_invalid`失败，报告通过schema；未执行verify-only、不重试，runner/native/worker/FFI均0 |
| 历史：Curry V2精确来源恢复与零runner验收（历史） | [`本批恢复交接`](superpowers/plans/2026-10-26-curry-ledger-handoff-recovery-v2-handoff.md)、[`历史验证`](TESTING.md) | V2唯一真实恢复在`scope_ledger_semantics`因V3来源角色名不匹配失败，失败报告保留；后续V3版本修复并重新认证来源 |
| 历史：Curry V3真实来源角色适配与零runner恢复（历史） | [`本批恢复交接`](superpowers/plans/2026-10-26-curry-ledger-handoff-recovery-v3-handoff.md)、[`最近验证`](TESTING.md)、[`最终交付`](../data/runtime/p1-curry-ledger-handoff-recovery-v3-offline-2026-10-26/final-build/delivery-final.json) | V3恢复及只读verify通过；9/9检查、187项来源、原scope消费1/完成1/未知0；本批native/runner/worker/FFI均0，stage 2收据仍缺失 |

## 2026-10-27：Curry独立七阶段再验真

这是新scope的历史结果，不能补签旧confirmation消费或补造旧scope stage 2收据。认证子集与规划值仅按该批交接解释。

| 历史条目 | 原链接（保持原目标） | 当时状态与消费边界 |
|---|---|---|
| 历史：Curry V3恢复证据绑定的Curry七阶段再验真（历史） | [`本批交接`](superpowers/plans/2026-10-27-curry-option-revalidation-handoff.md)、[`历史验证`](TESTING.md)、[`最终交付`](../data/runtime/p1-curry-option-revalidation-native-2026-10-26/final-build/delivery-final.json) | 新scope七阶段及两个独立重放通过，7/7消费、unknown 0；认证子集40、规划47；历史实际总消费仍未知，四项资格为false |

## 更早设计与验证的追溯

原实现取舍见[IMPLEMENTATION_NOTES](IMPLEMENTATION_NOTES.md)，更早规则、规划与恢复证据见[TESTING](TESTING.md)的对应日期记录及[计划目录](superpowers/plans/)。目录中的旧计划同样只作历史背景；不得从旧命令、旧验收数字或旧handoff推断当前实现。
