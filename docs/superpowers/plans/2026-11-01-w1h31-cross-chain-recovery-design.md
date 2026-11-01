# W1-H3.1 跨链恢复与响应丢失设计

日期：2026-11-01。事实基线：main / 6b523f273943caed671ae5d151225e716c8e31b3；保留11份已有文档修改及新增路线文档。本批仅设计，H3.2新增接口、故障钩子和验收均尚未实现／尚未运行。普通工作台仍为 `analysis_not_configured`。

## 1. 已有实现与证据边界

源码事实源为 `crates/ygo-cli/src/workbench_analysis/durable.rs`、`operation_store.rs`、`persistence.rs` 和 `crates/ygo-cli/src/workbench/analysis_http.rs`。合同见[持久化](../../WORKBENCH_ANALYSIS_PERSISTENCE.md)、[HTTP](../../WORKBENCH_ANALYSIS_HTTP.md)和[任务](../../WORKBENCH_ANALYSIS_JOBS.md)。

已有 `open_operations` 持锁打开未分类存储；`from_operation_store` 先扫描全部操作、任务及报告引用，再检查任务ID唯一绑定、冻结输入一致和accepted关联，收集accepting修复后逐条追加，最后 `classify_restart`。返回的活动队列为空，不重建可执行冻结对象。旧无操作任务根仍可读取；旧入口拒绝操作根，不能忽略操作目录。任务无操作关联不一概视为损坏，保留B3旧根兼容。

已有测试（本批仅静态核对名称，未复跑）：

| 测试 | 已覆盖的有限边界 |
|---|---|
| `task_commit_before_accepted_is_repaired_without_requeue` | queued已存、accepted未存，重开补关联，不再冻结或入队 |
| `accepting_without_job_becomes_unknown_without_adapter` | 无匹配任务的accepting转unknown |
| `operation_actual_freeze_duplicate_and_restart_do_not_resubmit` | 合成真实冻结、重复指令和重开 |
| `killed_store_process_reopens_queued_as_interrupted_and_running_as_unknown` | 已提交任务状态后的测试子进程终止；不覆盖完整HTTP跨链窗口 |
| `uncertain_report_file_publish_stops_coordinator_and_reopens_as_unknown`、`failed_report_terminal_publish_stops_coordinator_and_reopens_as_unknown`、`uncertain_persistent_claim_stops_coordinator_and_reopens_as_unknown` | 指定存储不确定与重开分类 |

H2.2-A/B的437通过、36忽略是历史结果，不是本批复验。B的16次同时取消/领取均由领取胜出；另有顺序取消先完成用例，不能宣称并发两种胜者均已观察。Windows TCP重置根因仍未认证。

## 2. 恢复协调与提交顺序

H3.2拟增加私有职责边界（尚未实现，不是公开API）：`authenticate`返回持锁、完整认证的保存快照；`plan_recovery`纯计算期望前驱和下一修订；`apply_recovery`逐项核对前驱并提交；`inspect`只读重新认证保存材料。不得让描述或快照携带成功回调，不能把缓存当作再次读取的替代品。复用v1封装及原始前驱字节哈希，不改HTTP或schema。

固定顺序：根目录独占锁 → 全部布局/链/报告读取认证 → 跨链绑定认证 → 制定完整修复清单 → 依操作ID顺序提交关联修复 → 依任务ID顺序提交分类 → 开放认证后的查询。全量认证失败前不得写分类。每条追加均复核期望revision、前驱原始哈希和候选转换；写后按原存储规则复读。任何失败停止后继追加，不回滚已发布修订。

| 保存状态 | 允许恢复写入 | 再次重开的追加数 |
|---|---|---|
| allocated | 无，不自动提交 | 0 |
| accepting，无可认证匹配任务 | unknown操作修订；不补建任务 | 首次1，之后0 |
| accepting，冻结绑定及任务初始输入完整一致 | accepted操作修订，再分类任务 | 关联首次1；每个非终态任务首次1，之后0 |
| accepted缺任务、ID复用、冻结绑定冲突 | 无，阻断整个根 | 0 |
| queued / running | interrupted / unknown任务修订 | 首次各1，之后0 |
| 合格终态 | 重新认证引用，无追加 | 0 |
| 有效孤立报告 | 保留，不提升任务 | 报告0；running仍分类1次 |

部分恢复已发布后中断，下次从保存链重新制定剩余清单；不得重复推进终态。操作修复沿用原更新时间，任务分类使用当前Unix毫秒；时间倒退不改时间、不退款，停止剩余恢复。提交结果不确定须退出恢复，不在同次启动补交。内存仅在对应提交确认后更新；恢复完成也不注册旧任务派发。

损坏链、报告缺失/摘要错误、非法布局、链接或冲突材料保留原位。合法专用临时名不参与选状态；有效孤立报告不授予完成，损坏孤立报告按现有全根扫描规则拒绝，不能自动删除绕过门禁。锁防并发正常写者，不证明恶意本机写者无法整体重写历史。

## 3. 查询与回复丢失

已有锁所有者停派发后仍可使用同锁纯读取检查接口；每次读取重新认证相关链、绑定及报告，不调用会分类的open。健康历史可查，明确不存在为404；材料无法认证为503。启动全根认证失败或锁占用时不得构造可用协调器，分析业务返回不可用503；草稿服务可保持可用。不提供另开无锁查询或缓存成功的回退。

| 回复丢失位置 | 保存状态与客户端动作 | 禁止行为 |
|---|---|---|
| 分配已提交、客户端未获ID | 可能存在孤立allocated；不承诺找回。客户端可显式新分配，仅产生ID | 自动查找并代提交、自动创建替代任务 |
| accepting已提交、202未收到 | 已知ID先GET操作；同指令提交只复用保存状态，不重复冻结 | 因断连取消后台、换ID重交 |
| 已返回202、后台失败 | 后续GET显示可认证状态或503；无法修改原202 | 把失败改成成功或推定零调用 |
| queued已存、accepted未存 | 本进程停派发；重开认证后补关联并分类interrupted | 内存直接领取已存queued |
| 取消已存、响应丢失 | GET任务revision，终态保持只读 | 重复取消推进revision |
| 报告/终态已存、响应丢失 | GET任务及认证结果；无终态时报告不公开为完成 | 以孤立报告补认完成、重新执行 |
| GET响应丢失 | 重复GET只读认证，前后目录快照不变 | GET触发分类或资产扫描 |

GET不认证实时引擎资产；报告合同通过、保存来源绑定、原生来源及全局最优资格分别判断。对外只返回现有无路径DTO与稳定码，不透传异常、令牌或本机路径。

## 4. H3.2逐提交矩阵（拟议验收，尚未运行）

故障模型：P=最终名出现前明确失败；U=发布后返回不确定；R=写后复读失败；L=提交确认后响应丢失；K=目标逻辑窗口进程终止。每行均实施P/U/R/K；有HTTP回复的行另实施L。不声称覆盖每个syscall、介质故障或断电。

| 边界 | P保存状态；U/R/K按保存字节判定 | 内存/HTTP与后续动作 | 重开追加预期 |
|---|---|---|---|
| allocated | P无操作；发布后allocated可能存在 | 同步故障503；不自动替换ID | 0 |
| 首次accepting | P仍allocated；发布后accepting可能存在 | 同步503或202回复丢失；不再次冻结 | 无任务时unknown 1 |
| 容量/配置拒绝、准备失败rejected | P保留前态；发布后rejected可能存在 | 持久故障503，不能伪装业务拒绝；202后台失败靠GET表达 | allocated 0；rejected 0；accepting无任务unknown 1 |
| 冻结绑定 | P仍accepting未绑定；发布后绑定可能存在 | 停止派发，不释放不确定预占供抢槽 | 无任务unknown 1 |
| queued任务 | P无任务；发布后queued可能存在 | accepted前不登记可派发输入 | 有任务补accepted 1及interrupted 1；无任务unknown 1 |
| accepted关联 | P已有queued且操作accepting；发布后accepted可能存在 | 停派发；不能重复冻结 | 缺关联补1；queued分类1 |
| running领取 | P queued；发布后running可能存在 | 无确认票据不执行；同步故障503 | queued→interrupted或running→unknown各1 |
| cancelled | P queued；发布后cancelled可能存在 | 取消和领取同锁；L后查revision | queued分类1或cancelled 0 |
| failed / unknown终态 | P running；发布后终态可能存在 | 停派发，不重试 | running分类1或终态0 |
| 报告文件 | P无报告；发布后可有孤立报告 | 不发布完成；查询依据任务，损坏报告503 | running→unknown 1 |
| completed / budget_limited | P报告孤立且running；发布后终态可能存在 | 引用认证成功才开放结果 | running分类1或合格终态0 |
| 恢复accepted / unknown操作追加 | P旧操作；发布后新修订可能存在 | 不开放派发；停止剩余恢复 | 仅补未完成关联/分类 |
| 恢复interrupted / unknown任务追加 | P旧任务；发布后终态可能存在 | 不开放派发；停止剩余恢复 | 仅未分类任务各1 |

稳定诊断复用现有分类：存储写失败、提交不确定、链无效、revision冲突、报告完整性失败、目录锁/路径无效及时间无效；HTTP固定沿用现有映射：CommitUncertain为503 / analysis_commit_uncertain，Stopped为503 / analysis_coordinator_stopped，其他Persistence错误为503 / analysis_store_unverifiable；独立诊断保留PersistenceError::code()及逻辑边界与P/U/R/L/K，不新增自由文本路径回退。

H3.2案例须保存目标边界握手、磁盘原始字节/快照、操作与任务revision、报告引用、内存槽位、HTTP已收字节及后继调用计数。用屏障或IPC确认目标提交再终止测试子进程，不用sleep判断窗口；实际TCP按Content-Length读取，不自动重试。完整请求断连不取消已接受工作。

交叉负例包含错误前驱、重复键、身份/评分/请求/预算绑定冲突、报告缺失、目录漂移、时间倒退、锁占用、恢复途中再次中断及重复重开。全部使用真实冻结、存储及报告解析；只替换测试时钟、调度和合成执行边界。禁止性断言保证恢复、查询及拒绝后均不启动真实runner/worker/FFI或研究账本。下阶段先复用第1节测试，再补跨操作/任务/报告及HTTP响应丢失窗口，不能把已有局部kill测试称为完整H3验收。

## 5. 设计验收与边界

本批仅检查事实源、本地链接、diff空白和独立只读设计审阅；没有运行以上矩阵或历史测试。提交策略、链合同和接口不变；H3.2实现、W1-C真实分析分别另立批次。Windows当前文件同步/独占发布与Unix父目录同步能力不同，进程中断恢复不等于断电保证。

会计保持认证消费子集40、政策预留7、规划47；旧confirmation及全部历史实际累计未知。新增原生研究、runner、worker、FFI调用均0；四项证明/完整性/概率资格均false。不改Tenki pin、不部署、不提交或推送。设计交付后暂停。
