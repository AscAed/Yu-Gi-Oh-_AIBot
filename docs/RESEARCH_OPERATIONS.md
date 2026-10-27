# 研究运行规范与副作用边界

本文整理现有研究工具的运行边界，不新增命令、授权或预算。当前任务和累计会计唯一入口是[TASKS](../TASKS.md)，逐次执行与成本见[TESTING](TESTING.md)；命令参数及旧批合同见[RESEARCH_AUDIT](RESEARCH_AUDIT.md)和[BASELINE_AUDIT](BASELINE_AUDIT.md)。证据身份、版本兼容和发布状态见[EVIDENCE_CONTRACTS](EVIDENCE_CONTRACTS.md)。

本文使用三种适用标记：**已验证·指定版本**表示代码、schema和对应记录共同支持；**仅历史scope**表示只约束所链接实验；**拟议改善**表示尚无通用实现，不能作为已有保证。旧工具仍存在不等于旧窗口可续用；历史通过也不等于当前工作区已重新运行。

## 模式与副作用矩阵

计数必须逐轴记录。`native_calls`在这些研究合同中按受预算约束的请求记账，不能解读成底层C函数调用次数。runner是外层审计/调度可执行程序；worker是引擎请求子进程；FFI是worker内部的原生库边界。启动runner不必启动worker；读取DLL字节也不等于加载DLL。没有单独计数证据时应写“未独立计量”，不得从其中一列推算其他列。

下表中的“0”只来自所列模式及记录。“读/写账本”专指收费账本及关联blob/检查点，另列的报告、打包与进程侧车仍可能写文件。

| 适用范围及模式 | 新native请求 | runner启动 | worker请求 | FFI执行 | 资产读取/扫描 | 收费账本读 | 收费账本写 | 其他写入 |
|---|---|---|---|---|---|---|---|---|
| 已验证·Ground Collapse preparation v1：prepare | 0 | 0 | 0 | 0 | 读取固定CDB、脚本/禁限/核心源码与历史产物；不运行live engine identity扫描 | 是，核验历史链及blob | 否 | 独占新建准备报告、工具包或失败诊断 |
| 已验证·Ground Collapse preparation v1：verify-only | 0 | 0 | 0 | 0 | 重读固定来源、保存工具包及历史证据；不扫描实时部署资产 | 是 | 否 | 不改保存报告；调用者可另存stdout/stderr |
| 已验证·Curry ledger recovery v3：recover及verify-only | 0 | 0 | 0 | 0 | 静态文件/归档核验；无live asset scan | 是，纯Python核验已存链及blob | 否 | recover新建报告/工具包/诊断；verify不改原报告 |
| 仅历史scope·Curry handoff audit V5保存输入审计 | 0 | **1** | 0 | 0 | **有**保存输入runner的只读live资产扫描 | 是 | 无新增收费记录；不据此声称所有临时锁操作均无副作用 | runner进程侧车；外层正式报告未发布 |
| 已验证·离线prompt-corpus审计v1 | 0 | 有，纯数据Rust auditor | 0 | 0 | 读取报告、源码和auditor字节；无引擎资产执行 | 否 | 否 | 新语料报告 |
| 已验证·identity v1采集 | 0 | 不启动研究runner；Python capture会调用CLI | 0 | 0 | **有**双采样，含worker/DLL/CDB/清单/脚本树字节 | 否 | 否 | 显式输出身份文件时独占创建 |
| 仅历史scope·Curry revalidation v1 normal | 7次预算请求 | normal调度runner；总进程数依进程证据 | 7 | 经过原生执行路径，底层FFI次数未独立计量 | 每阶段门禁核验原生资产 | 是 | 是，意图、收费及完成前缀 | 请求、seal、收据、报告、进程诊断 |
| 仅历史scope·Curry revalidation v1 verify-only | 0 | 是，核验保存收据的runner模式；不等于零runner恢复 | 0 | 0 | 不扫描实时资产，核验保存证据及来源 | 是 | 不追加原生请求 | 不改原生收据；外层可保存核验输出 |

矩阵依据：[Ground交接](superpowers/plans/2026-10-27-ground-collapse-preparation-handoff.md)、[V3恢复交接](superpowers/plans/2026-10-26-curry-ledger-handoff-recovery-v3-handoff.md)、[V5失败交接](superpowers/plans/2026-10-26-curry-ledger-handoff-v5-handoff.md)、[Curry再验真交接](superpowers/plans/2026-10-27-curry-option-revalidation-handoff.md)；实现分别为[准备器](../python/ygo_eval/ground_collapse_preparation.py)、[恢复器](../python/ygo_eval/curry_ledger_handoff_recovery.py)、[审计版本表](../python/ygo_eval/curry_ledger_handoff_audit.py)、[Curry编排器](../python/ygo_eval/native_curry_option_validation.py)和[资产身份采集](../crates/ygo-engine-adapter/src/identity.rs)。合成fixture中的替代runner只证明测试路径，不能记为真实原生执行。

`prepare-only`、`verify-only`、`audit-saved-input-only`不是全仓库统一副作用等级。Ground准备器和Curry恢复器可完全不启动runner；V5保存输入检查启动过runner并扫描资产。判断新入口时先看实际分支、子进程argv、账本打开方式和目标路径，再引用相应版本的已验证记录。`doctor`涉及本机资产/ABI诊断，是否运行取决于当前任务授权及具体范围，并应记录实际副作用；它不是阅读文档或验证来源的必要步骤。

## 预算、窗口与费用语义

**已验证·研究批v1：**[ResearchBatch](../crates/ygo-engine-adapter/src/research.rs)及[CallJournal](../crates/ygo-engine-adapter/src/journal.rs)实现单账本、请求绑定和持久消费。首批上限为8例、每例512请求、总4096请求和两小时；执行、独立重放及失败调用均受扣费包装约束。新query/audit路径若涉及worker请求也必须经过预算入口，不能凭用途名称当作免费请求。

**仅历史scope：**首批总上限不自动授予后续小批额度。Curry再验真为自己的七次请求与窗口；其他批次的16次、6次或追加两次均只属于各自冻结合同。同一追加窗口重开不重置该窗口起点或消费。只有对同一账本、context和指定case另获用户明确批准，才可用新ID建立一个新的、最多两次请求的追加窗口；它有自己的起点，但不会重置原账本消费、未知调用、单case上限或总预算。CLI记录的ID只是授权引用，不证明授权本身；自动流程不得自行生成新ID或开启窗口。具体历史范围见[研究审计的窗口记录](RESEARCH_AUDIT.md)和各批handoff，当前累计数字只查[TASKS](../TASKS.md)。

**已验证·有窗口的原生批：**先持久化窗口起点，再首次候选资产扫描；扫描、输入核验、子进程和收尾均消耗实际墙钟。worker超时30秒不等于整个Python/runner命令只有30秒。首次批在起点后7170秒停止新增请求；Curry批要求严格多于30秒剩余时间，细节以[阶段批实现](../crates/ygo-engine-adapter/src/curry_option_batch.rs)为准。时钟回退、窗口到期或剩余不足均拒绝新收费；墙钟门禁不是硬实时杀限，存储和终止耗时仍需记录。

**已验证·会计边界：**区分已认证消费子集、已完成、已收费未知、政策预留和规划量。预留不是实际执行，完成数不是消费总数；未找到可信账本或未认证历史退出状态时，实际累计保持`null`。旧confirmation的实际消费及全部历史实际总量仍未知，不能用已认证子集加预留反推，也不能把本批`native_calls=0`改写为历史累计0。V3恢复只重新认证有完整证据的原scope；stage 2收据缺失仍保留，见[V3恢复报告合同](../schemas/curry-ledger-handoff-recovery-v3.schema.json)。

## 停止条件与可恢复范围

**已验证·具体执行器：**资产漂移、未决收费/持久意图、请求或seal不匹配、窗口失效、无法识别提示、公开选项缺失/重复、响应oracle失配、额外消息、执行错误或独立重放差异均阻断相应后续阶段。达到预算、枚举上限或时间上限只代表局部未完成；不得写成无解、完整或最优。停止时保留已收费前缀、失败收据、raw帧和诊断，不静默补发请求。

**仅历史scope·单次规则：**V1–V5固定审计目录、V3恢复真实尝试和Ground固定准备目录各有独占输出及不重试约束。Curry原生阶段已有持久意图时也禁止重试worker调用。这些规则约束所链接材料；不能推广成“所有本地读文件、文档检查和离线测试只能执行一次”。通用可重做操作仍须遵守输出碰撞与输入保护；已封存实验若需新增执行，另定scope、预算、窗口及输出合同。

**已验证·恢复的局限：**从保存账本恢复已收费结果可为零新增native，但不重新证明原时点资产连续性；纯Python恢复成功也不填补缺失的原生收据。Ground的准备报告`execution_ready=false`，不能直接交给worker。下一次opcode24原生发现需要新合同及预算；真实提示、mask、prompt ID和响应接受仍未知，见[Ground准备schema](../schemas/ground-collapse-preparation-v1.schema.json)。

## Windows锁与同次输入快照

**已验证·CallJournal：**Windows打开账本使用`share_mode(0)`，Unix使用非阻塞排他锁；其他进程不能同时共享这份预算。只读恢复器应读取保存材料，不在活跃writer持锁期间另开可写账本。已发生的Curry stage 2共享冲突属于该历史尝试：收费前失败没有新增消费，但不因此证明所有共享冲突都发生在收费前，见[原Curry失败交接](superpowers/plans/2026-10-25-curry-option-verification-handoff.md)。

**已验证·Curry runner锁修复，非全局保证：**[当前runner](../crates/ygo-engine-adapter/examples/curry-option-validation.rs)的`verify_parent_request`返回前显式释放同进程父账本`ReadOnlyJournal`；收费前统计的读视图也限定在局部作用域内，随后才打开独占batch。持有writer锁后，`batch.validate_request`重新认证父收据、公开派生及已保存账本证据；锁前双采样核验的资产身份由`save_assets_before`写入不可覆盖检查点，`batch.run`再次检查请求、窗口、收费槽位和既有意图。固定input/request/seal路径、字节及链接检查在前置门禁完成，不代表writer锁同时锁住这些外部文件或锁内重新扫描live资产。历史合成TOCTOU用例证明父账本变更在独占复验时被拒绝；[锁修复记录](TESTING.md#2026-10-25-curry父账本锁释放修复与stage-2只读验收)及[原交接](superpowers/plans/2026-10-25-curry-ledger-handoff-handoff.md)保留适用版本和日志。只读audit分支则在writer/adapter之前返回，不能混写为相同执行路径。

**已验证·Ground preparation v1：**请求哈希校验使用本次已验证并缓存的七个stage request原始字节；其余来源仍逐路径/哈希核验，最终再次检查输入稳定性。这样避免已验证路径在第二次读取期间短暂替换再恢复导致检查阶段使用不同内容。缓存仅覆盖必要请求，不是把所有历史文件装入内存，也不取消前后稳定性门禁。竞态修复与回归结果见[Ground交接](superpowers/plans/2026-10-27-ground-collapse-preparation-handoff.md)及[TESTING](TESTING.md)的对应历史记录和[准备器](../python/ygo_eval/ground_collapse_preparation.py)。

**拟议改善：**将这种“同次已核验字节贯穿后续解析”的模式抽成可复用只读采集层；为锁冲突、临时替换、权限拒绝和发布后复验统一保留阶段化诊断。当前不能宣称全仓库已具备该保证。遇到ACL拒绝应记录访问失败范围，不能删目录或改ACL来制造完整扫描结论；Ground旧受限临时目录仍保留。

## 失败诊断与验证成本分层

**已验证·发布分层：**先区分输入读取/固定来源、runner启动、worker收费、响应/重放及报告发布。保留原始stdout/stderr字节、长度、SHA256、退出/超时状态和阶段记录。V5中runner成功但外层退出2且正式报告缺失，准确内部异常当时未认证；不得猜测为引擎失败、消费未知或整批成功。恢复器新增的稳定错误码和发布诊断只解释其自身版本，不能倒签旧进程结论，详见[证据规范](EVIDENCE_CONTRACTS.md)。

| 验证层级 | 成本及副作用 | 能支持的结论与使用条件 |
|---|---|---|
| 文档/静态路径审阅 | 本地读文件、链接与diff；无业务执行 | 文档是否符合现有代码及记录；不能新增运行认证 |
| schema/纯离线聚焦回归 | 可能写合成材料和调用纯数据runner | 输入、负例、编码与失败路径；先确认不启用真实资产opt-in |
| 已存材料恢复或verify | 仍可能递归读大量归档、CDB和账本；不同版本可能启动runner | 保存证据的绑定与一致性；并非免费、瞬时或统一零runner |
| 全套Python/Rust离线验证 | 可耗数十分钟、生成大量证据并发生构建争用 | 对应源码范围的回归；逐项记录skip/ignore，不据此认证未运行资产测试 |
| 资产扫描、doctor及原生请求 | live扫描、子进程、锁和预算/窗口成本 | 必须依具体范围、授权和合同执行，不能混入纯文档验收 |

**仅历史成本示例：**Ground准备和verify各需数分钟，V5保存输入资产扫描也超过两分钟，Curry再验真全套Python及Rust验证另有日志。因此“零native”不等于零耗时；成本应按本次实际阶段报告，不能照抄旧耗时作为保证。完整日志入口见[Ground交接](superpowers/plans/2026-10-27-ground-collapse-preparation-handoff.md)及[Curry交接](superpowers/plans/2026-10-27-curry-option-revalidation-handoff.md)。

**拟议改善·后续选择原则：**先用最便宜、无原生副作用的证据定位单一阻断；聚焦回归足以覆盖变更时不默认重复全套。只有源码范围、失败或未决风险需要时再扩展验证。本文本身不触发构建、恢复、verify、资产扫描或原生实验。
