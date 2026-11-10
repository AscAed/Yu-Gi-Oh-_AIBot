# 项目评估与双轨路线（2026-11-04更新）

## 2026-11-10 PR #17审阅续接

当前事实以[TASKS](../../../TASKS.md)为准。PR #17仍为Open Draft，远端head为`c9455d577fc08c1e51663eed079f166d282ab61c`；CodeRabbit对该已发布head的第七轮远端Deep Review返回15项（7 major、8 minor）。15项均已逐条映射到隔离候选的代码或文档处置，但审阅结果不包含候选未提交改动。当前下一步是完成候选级代码复核和约定的离线回归，再据范围、兼容性与剩余证据决定如何集成；不自动合并或推送。

host-ack合成通道已在PR分支实现，但真实worker/ocgcore事件、源码与构建身份、报告producer来源、ResearchBatch消费及unknown消费仍开放。候选审阅不授予真实执行、研究或发布资格；普通启动仍`analysis_not_configured`，P4-R5继续开放。逐项审查和验证数字见[PR #17审阅交接](2026-11-09-pr17-review.md)与[TESTING](../../TESTING.md)。

## 2026-11-04 复核与小批安排

当前事实以[TASKS](../../../TASKS.md)为准。W1-C已完成隔离候选的单次Rabbit有限分析，160节点、165 engine_calls，`time_budget`截断；报告来源和底层FFI/消费未独立认证。普通启动仍`analysis_not_configured`。下文较早时点称W1-C尚未验收的段落仅是历史，不覆盖此结果。引用的实施对话曾在2b-2未完成时中断，后续汇总及日期化测试已记录限定窗口验收；不可用早期状态覆盖后续证据。

| 小批 | 依赖、交付与停止/退出条件 |
|---|---|
| H3本批复核与下一批 | `time_budget`报告只作为已有`budget_limited`保存后K点的原因分类补充，与`node_budget`共用同一物理检查点，不计为新逻辑窗口。随后完成独立的[显式mark_unknown终态保存后、队列结算前K](2026-11-04-unknown-terminal-persisted-before-queue-update.md)：`CompletionUncertain` revision 3落盘后强杀，真实锁重开两次稳定。此单点不关闭其他H3逻辑状态/调度、报告来源或syscall/断电/介质故障。工作台/研究下一批优先推进[W1-C分层执行回执与计量合同](2026-11-04-w1c-provenance-accounting-plan.md)；如继续H3，须再从[证据映射](2026-11-02-h3-evidence-gate-map.md)选一个不同的未覆盖提交点。 |
| 已完成：W1-C证据链复核 | 2026-11-04离线重算执行包56/56项及包/资产身份记录14/14项哈希；operation、job、result及11文件存储清单重开前后字节稳定。报告明确将report_origin_authenticated设为false；按当前源码165 engine_calls是应用层adapter调用计数，OS worker创建、FFI调用和消费仍未知。旧运行的3/5个未跟踪构建输入原字节无法从当前树或Git历史找回，tracked diff摘要也无法复算。单次有限分析验收保持不变；详见[TESTING审计](../../TESTING.md)。 |
| 已完成第一子批：W1-C源码字节包v1 | 当前工作树跟踪及非忽略未跟踪文件已进入版本化ZIP包，清单和每个成员可离线复核；Schema及全Python回归通过。包只保全路径/字节，不含Git index、模式、忽略资产、构建复现、执行或消费认证。记录与命令见[TESTING](../../TESTING.md)和[部署合同](../../DEPLOYMENT.md)。 |
| 已完成第二子批：W1-C观察式离线候选构建绑定v1 | 当前源码包绑定Cargo `dev` profile命令、工具链版本、CLI/worker候选哈希和9项固定输入/资产；隔离`--offline --locked`构建、实际记录Schema及产物/资产校验通过。记录身份与限制见[TESTING](../../TESTING.md)：这是观察式记录，不证明构建可重现，也不认证worker运行、报告来源或消费。精确workspace patch、Git index/模式仍开放。 |
| W1-C执行来源与计量合同 | 本行记录2026-11-04时的下一批计划：当时已有多attempt合成回执合同、job绑定host日志及合成FFI entered/returned事件，计划随后用假worker验收向后兼容的host-ack通道。该通道后来在PR #17分支实现；当前集成状态见[TASKS](../../../TASKS.md)和[PR #17审阅记录](2026-11-09-pr17-review.md)。真实worker/ocgcore事件、报告producer来源与ResearchBatch消费仍开放；普通分析仍另立scope，合成事件不认证原生执行、来源或消费。 |
| Ground/P1 | Ground候选保持hold；先复核固定请求、源码/资产身份与预算，形成准入决定，任何变化或来源缺口即停。另选一个动作、观察、概率或循环阻断项，交付可复现设计与失败判据；真实调用另行授权。 |
| R1b-3 | 旧run只完成一次Execution且不能续跑；先对齐修正后的对手牌组/手牌见证、输入、driver与worker身份，设计新的独立scope、暂停/重开及replay。身份不符或消费不确定即停；真实恢复须另授权。 |
| L1 | 已对照39张zh-CN及38张有值zh-SC候选；逐批解决名称/类别差异和别名映射，单独核实使用与再分发依据。缺字段或权利依据时保持unknown，不提升正式资格。 |
| W2 | 同机隔离包与迁移合同已有基础；取得独立Windows用户或虚拟机后核验启动、草稿、往返及升级/回滚。无真实旧profile或环境时记录阻塞，不以同机结果代替。 |
| P4-R2–R5 | R2先完成场景规则逐项认证；R3交付v6和v1–v5兼容；R4冻结人工基准并完成16+32手评估；R5绑定源码、产物、配置、双资产及可比账本。缺一项或预算截断即保留开放，不切换发布包。 |

以上每批先保存身份与证据、再复盘收益、成本和剩余门禁；合成、有限原生、账本与证明资格分别判定。

2026-11-01静态基线：本地main / `ae4a9ab`，工作区干净，本地跟踪引用领先9；未访问远端。目标以[PRODUCT_VISION](../../PRODUCT_VISION.md)为准，状态以[TASKS](../../../TASKS.md)为准，验证以[TESTING](../../TESTING.md)为准。

项目是具备草稿工作台的有限场景研究原型。P0/P1缺正式OCG发行分母、完整动作、条件概率、信息策略、循环和独立值界；P2/P3缺正式中文数据、真实分析流程和普通发布；P4真实恢复、独立原生重放及R2–R5开放；P5–P8通用知识、构筑反馈、全卡及可核查最优性证明尚未完成。全卡和最优性存在尚未证明可行的研究关口，不计算总完成比例或最终工期。

## 当前状态与下一批（2026-11-04）

当前状态以[TASKS](../../../TASKS.md)为准。W1-C已在隔离候选包和独立单次范围内完成一次Rabbit本机有限分析：160 nodes、165 `engine_calls`，以`time_budget`到达`budget_limited`；端到端观测83.776秒。报告schema与受控重开稳定性通过，但报告来源、底层FFI/消费未独立认证，搜索不完整且不证明全局最优。普通启动仍`analysis_not_configured`，P4-R5发布门禁开放。

H3现有四项票据返回后的细分强杀窗口：派发准入通过、假执行器调用前；测试专用假执行器进入后、返回前；假执行器返回`Ok(report)`后、`publish_report`开始前；以及报告临时文件同步后、正式hard link发布前。2026-11-03另补一个更早的独立领取边界：running修订已持久化且内存队列已更新、`claim_next`尚未返回票据。该点用真实目录锁重开，只追加一次unknown并在重复重开后保持稳定；事件计数确认假执行器未调用。已验收K点均不包含生产worker或真实引擎证据。报告临时文件窗口曾复现重开因遗留临时件失败，现已最小修复为保留精确命名的未发布临时文件。其他逻辑窗口/调度、真实执行器副作用、逐syscall、断电和介质故障仍开放。详细证据见[队列更新后、票据返回前交接](2026-11-03-running-queue-updated-before-ticket-return-handoff.md)、[票据返回后交接](2026-11-03-ticket-return-crash-handoff.md)、[执行器进入后交接](2026-11-03-running-executor-crash-handoff.md)、[返回后交接](2026-11-03-executor-return-crash-handoff.md)、[报告临时文件窗口图](2026-11-03-report-temp-crash-window-map.md)及[验证记录](../../TESTING.md)。

已完成[P4-R1b-3 scope只读复核与当前身份/零调用预检](2026-11-03-p4-r1b3-scope-review.md)：旧worker路径错配已在隔离驱动中修正，5项聚焦测试、workspace格式/Clippy/串行测试和prepare-only复核通过；scope、worker进程、native调用均为0。真实恢复/replay仍需独立授权，R1b-3保持开放。L1人偶之锤（44088353）来源复核完成，但本项目使用/再分发依据未确认，C1候选状态不变。W2离线源码CLI候选包通过空profile、catalog路径、草稿往返、同包重启及ZIP解压到含空格路径后的复核；另新增裸Deck JSON→V1兼容夹具/CLI失败不覆盖/schema回归并形成profile迁移与回滚合同，详见[W2包验收](2026-11-03-w2-offline-clean-environment-plan.md)和[W2迁移合同](2026-11-03-w2-draft-migration-contract.md)。下一步定位真实旧包/profile；若不存在，转做独立干净Windows用户或虚拟机启动验收。升级、迁移和回滚仍开放；P4-R1b-3真实恢复/replay仍保持独立授权边界。每批分别记录工作台、合成、原生、研究账本和发布证据。

### 2026-11-03 下一批复盘：P1观察投影与opcode24菜单

受限观察投影合成回归复验为29 passed、11 subtests passed；随后将固定opcode24合成帧与Python独立oracle生成的规范菜单夹具逐项对照Rust生产解码器，Rust 5项和Python 9项聚焦测试均通过。新交接见[P1 opcode24菜单交叉核验](2026-11-03-p1-opcode24-menu-crosscheck.md)。这一轮确认的是合成输入映射；真实隐藏状态、一般信息策略、opcode24真实提示/响应及P1完整证明仍未通过。随后只读复核固定候选与本地资产并形成[opcode24真实提示实验设计](2026-11-03-ground-collapse-opcode24-experiment-design.md)：候选案例和当前DLL/CDB/脚本/禁限/core pin吻合；历史Ground `preparation.json`在当前checkout缺失。独立重跑离线prepare在`latest_curry_delivery`首门禁失败，要求的`final-build/delivery-final.json`不存在，失败报告已保存在新的当前准备目录；不得从build record补造交付。下一批先恢复该精确来源或通过独立审阅定义新来源合同，再推进Ground收费驱动和合成测试。真实scope最多5个预算请求、1,800秒，须另行授权。当前没有创建scope或进行原生调用。

### 2026-11-03最新复盘：AssetMismatch K与Ground离线来源复验

H3恢复矩阵新增[AssetMismatch已持久化、队列结算前K](2026-11-03-asset-mismatch-persisted-before-queue-update-handoff.md)：测试子进程在冻结资产身份复核失败并保存failed/AssetMismatch revision后被终止；真实目录锁重开保留failed终态、没有报告或可领取任务，第二次重开文件字节稳定。该点不覆盖HTTP派发准入的另一条资产拒绝路径、真实执行或系统/介质故障。其他H3逻辑窗口、调度仍开放。

### 2026-11-03 HTTP派发准入AssetMismatch恢复窗口

H3.1映射确认`dispatch_pending`的派发准入失配与`claim_next`冻结资产复核失配是两条独立失败路径。新增子进程K位于HTTP服务持久追加failed/AssetMismatch之后、内存队列结算之前；父进程认证operation/job链、迁移、命令摘要和冻结输入绑定后终止。真实目录锁重开保留failed终态，无unknown、报告或执行器调用，队列无可领取工作，二次重开字节稳定。交接和证据见[本窗口记录](2026-11-03-dispatch-admission-asset-mismatch-crash-handoff.md)及[TESTING](../../TESTING.md)。该单点不认证生产worker、真实资产/引擎、其他调度或系统/介质故障；其他H3门禁仍开放。

Ground离线准备先前缺失的13份固定来源及V1–V5父链材料现已按私有归档索引哈希恢复并逐字节核验；Ground专用阶段driver、runner、协调器和测试绑定到19成员工具包后，当前报告通过六项来源检查及verify-only，SHA-256=`a238a2f114c7cb26b6f1e79d6ca34b3e5f01f33bdb57eab0b6d2f650c2bb8c99`。报告仍`execution_ready=false`，没有scope、账本、runner、worker或FFI调用；历史2026-10-27报告仍缺失。当前源码绑定候选清单已形成，覆盖HEAD/完整工作区、driver/runner/worker/build、固定输入、资产、stage 1请求、预算上限与停止条件；它保持hold，不是可执行scope manifest。该清单已通过独立只读审阅，下一步是单次窗口执行准入决策；真实opcode24实验仍需要独立scope授权。

W2路径已确认旧`dist/ygo-local`不含工作台入口，也未发现可供升级的旧工作台profile。当前主机无Windows Sandbox、VMware、VirtualBox或QEMU可用程序，独立Windows用户/虚拟机验收暂时无法在本机完成；W2仍只通过同机隔离profile测试。后续有独立Windows环境时再完成干净环境与升级/回滚门禁，不改变当前发布包。

[H3.2-2b-1交接](2026-11-01-w1h322b1-process-kill-handoff.md)仅认证冻结输入后/job前、queued后/accepted前、报告后/终态前、关联修复后/分类前四个逻辑窗口；2b-2另认证首次accepting保存后冻结前。其他窗口及调度、逐syscall、断电和介质故障开放；普通启动仍`analysis_not_configured`，W1-C与P4-R5开放。Rust workspace 444 passed、36 ignored和schema 16 passed为该批历史记录；更早Python全套不属于此批重跑。

16项愿景逐项差距与阶段见[需求矩阵](2026-11-01-post-w1h321-project-route.md#需求追踪)；矩阵的H3状态为历史时点，以本页及TASKS更新。覆盖UX-01、LANG-01/02、DATA-01/02、DECK-01、BUILD-01/02、KNOW-01/02、COMBO-01/02/03、LOOP-01、ENG-01、TRUST-01。

## 双轨小批

逐边界P/U/R/L/K证据与下一候选见[H3门禁映射](2026-11-02-h3-evidence-gate-map.md)；映射不代表H3或W1-C已通过。

2026-11-02复核：2b-1四个窗口及2b-2首次accepting保存后冻结前窗口已分别按合成范围验收。实施对话较早结束于未完成状态；后续汇总及[测试记录](../../TESTING.md)记录最终版本验收。其余窗口仍开放。

### 已验收：allocated保存后、协调器返回前

该边界此前已有逻辑故障和响应丢失证据；现已完成协调器持久提交后、返回前的限定合成强杀验收，详见[交接](2026-11-02-allocated-crash-handoff.md)。客户端未收到ID时不承诺找回；显式新分配只产生新操作。此证据不覆盖其他调度、syscall、断电或独立HTTP响应强杀窗口。

随后逐批补必要恢复和调度证据，再设计W1-C固定Rabbit输入、资产、预算、停止及结果验收；L1已完成十三批、39/39张zh-CN候选的名称/效果人工对照，并完成人工zh-SC前十三批38/38张有候选值记录的对照。zh-SC没有剩余有值候选待审阅，人偶之锤（44088353）字段缺失；来源/使用依据仍开放，见[zh-CN批次1](2026-11-02-l1-card-review-batch-1.md)至[zh-CN批次13](2026-11-02-l1-card-review-batch-13.md)和[zh-SC批次1](2026-11-02-l1-zh-sc-card-review-batch-1.md)至[zh-SC批次13](2026-11-02-l1-zh-sc-card-review-batch-13.md)。zh-CN中38张有官方简中详情页，1张目前只找到官方日文页（人偶之锤44088353）；91279700的简中页由同日补充复核发现。P1每批固定一个障碍，R1b-3另定真实恢复和独立重放。P4-R2完成规则资格，R3交付v6及兼容回归，R4冻结人工基准并完成16+32手评估，R5再验双资产及可比账本；W2独立验证干净环境启动、草稿往返和升级。

### 2026-11-02 执行顺序与门禁

工作台轨已按下方窗口映射完成首次accepting保存后、冻结前的独立进程终止验收；验收只关闭该逻辑窗口。2026-11-02又完成恢复中无任务accepting→unknown revision 3的P/U/R合成故障注入，并按预先形成的状态/证据映射通过一个混合unknown/accepted操作排序K场景。随后从H3.1矩阵筛出一次无自动重试分析所需的最小恢复门禁，并完成[W1-C固定Rabbit输入、快照、资产、预算和停止设计](2026-11-02-w1c-single-rabbit-local-analysis-design.md)。该设计不执行真实分析；W1-C执行须另立范围。L1十三批共完成人工对照39张zh-CN候选；其中38张有官方简中详情页，29张候选标题不同、21张正文类别称谓映射未确认；人偶之锤（44088353）目前仅找到官方日文页。zh-SC前十三批38/38张有候选值记录已对照，候选C1状态和`und`语言类别未改变；没有剩余有值候选待审阅，人偶之锤在该源字段缺失；别名及权利依据仍开放。

研究轨每批先选择动作完整性、观察、条件概率或循环中的一个阻断项，交付可复现实验设计与成功/失败判据；R1b-3单独定义scope、消费、暂停重开与独立重放。P4按R1→R2规则认证→R3正式v6兼容→R4独立基准评估→R5双资产发布的依赖推进；W2另验干净环境启动、草稿、往返与升级。每批复盘用户收益、信息增量、成本和缺口，决定下一批；不得把设计等同执行授权。

### 2026-11-02 W1-C生产调用路径复核

固定Rabbit输入、资产和预算设计已经完成。2026-11-02已接入默认关闭的显式`--analysis-config`入口与串行单任务生产执行器；普通启动仍返回`analysis_not_configured`。假执行器、持久化和工作台配置测试通过，但当前入口尚未强制固定Rabbit请求参数，也没有真实分析验收。下一代码批次先落实固定牌组/起手/seed/规则/快照/预算准入和运行包身份核对，再做独立只读审阅；之后另立W1-C执行scope，才决定是否启动真实引擎。源码依据：[workbench.rs](../../../crates/ygo-cli/src/workbench.rs)、[analysis_http.rs](../../../crates/ygo-cli/src/workbench/analysis_http.rs)及[本次验收](../../TESTING.md)。

### 2026-11-03 W1-C固定准入与隔离候选包（单次有限分析前置记录）

固定Rabbit命令/冻结输入、快照、资产及隔离包准入已实现；非固定命令在accept前拒绝，冻结身份不匹配不会生成任务，认领后包身份失败按执行前`AssetMismatch`持久化并停止派发。聚焦测试、workspace串行测试、Clippy、schema回归、隔离离线构建和静态身份采样见[TESTING](../../TESTING.md)。派发前与认领后的重复全树扫描已移除；现在显式配置启动时采样一次，每次claim在`running`持久化后完整核验冻结资产，认领后保留CLI/配置/worker/快照文件哈希复核。新候选首个/立即重复静态身份采样约65/22.6秒，此前冷采样约98秒。设计外层观察上限调整为240秒，为最慢已观察采样、60秒搜索和收尾留出余量；服务内端到端时间仍未测。这是单次有限分析前的准入快照；当时尚未启动doctor、worker、runner、FFI、ocgcore或真实分析。后续固定范围已执行一次Rabbit分析，结果见[TESTING](../../TESTING.md)顶部；调用/消费仍未独立计量，报告来源未认证，搜索不完整且不证明全局最优。

### H3.1逻辑窗口与现有证据

P/U/R为提交前失败、提交后不确定、写后复读失败；L为响应丢失，K为进程终止。H2.2-A覆盖其交接所列逻辑提交故障，并非每一行每个分支均已证明；H3.2-2a覆盖其交接列出的TCP响应场景。下表的K只指明确定位的子进程窗口，其他格不从相邻测试推断。

| H3.1边界 | 已有证据及剩余范围 |
|---|---|
| allocated | H2.2-A逻辑故障、2a分配响应丢失；协调器保存后返回前的限定合成K已验收，其他位置及调度未认证 |
| 首次accepting | 逻辑故障及2a响应丢失；2026-11-02新增保存后冻结前K：完整认证修订链后强杀，恢复仅追加一次unknown且不建任务；其他分支仍开放 |
| rejected（容量、配置、准备） | H2.2-A/B和2a覆盖指定拒绝及后台故障；容量、配置身份变化及合成opening_hand_invalid准备拒绝保存后返回前的K分别验收；其他准备错误和调度仍未认证，见[容量交接](2026-11-02-capacity-rejection-crash-handoff.md)、[配置交接](2026-11-02-context-rejection-crash-handoff.md)及[准备交接](2026-11-02-preparation-rejection-crash-handoff.md) |
| 冻结绑定 | H2.2-A逻辑故障；2b-1覆盖绑定已保存、任务未提交的K |
| queued任务 | H2.2-A逻辑故障；2b-1覆盖queued已保存、accepted前K |
| accepted关联 | H2.2-A逻辑故障及2a响应场景；关联保存后、内存队列更新前的合成K见[交接](2026-11-02-accepted-crash-handoff.md)；其他位置和调度仍开放 |
| running领取、cancelled | H2.2-A故障、H2.2-B指定取消/领取调度及2a取消响应；新增cancelled与running保存后内存队列更新前各一合成K，另有running队列已更新、票据返回前的单点K，见[取消交接](2026-11-02-cancelled-crash-handoff.md)、[领取交接](2026-11-02-running-crash-handoff.md)及[票据返回前交接](2026-11-03-running-queue-updated-before-ticket-return-handoff.md)；不代表其他跨链窗口及调度 |
| failed / unknown终态 | H2.2-A指定故障；合成`analysis_failed`保存后内存结算前的K见[交接](2026-11-02-failed-crash-handoff.md)；2026-11-04另验收显式`mark_unknown`写入`CompletionUncertain` revision 3后、队列内存结算前K，见[交接](2026-11-04-unknown-terminal-persisted-before-queue-update.md)。其他失败来源和恢复状态/排序组合仍未认证 |
| 报告文件、completed / budget_limited | H2.2-A指定故障、2a报告及结果读取；2b-1覆盖报告保存后终态提交前K；exhausted合成报告的completed和node_budget合成报告的budget_limited保存后内存结算前K分别见[完成交接](2026-11-02-completed-crash-handoff.md)及[预算交接](2026-11-02-budget-crash-handoff.md)。2026-11-04增加time_budget报告字节作为同一budget_limited K点的原因分类用例，不扩大逻辑窗口；其他预算原因及报告来源开放 |
| 恢复操作追加 | H3.2-1合成恢复；2b-1覆盖关联修复后、任务分类前K；两条手工构造的无任务accepting链中第一条unknown保存后、第二条分类前K见[交接](2026-11-02-partial-operation-recovery-handoff.md)；无任务accepting→unknown的revision 3追加已覆盖BeforePublish/AfterPublish/Reread，见[故障交接](2026-11-02-unknown-operation-fault-handoff.md)；混合unknown/accepted恢复第一条操作提交后的单一K见[交接](2026-11-02-mixed-operation-recovery-handoff.md)；其他状态组合、排序和窗口仍开放 |
| 恢复任务分类追加 | H3.2-1合成重复重开；手工构造的双queued及queued/running混合链中，第一分类保存后、第二分类前K分别见[双queued交接](2026-11-02-partial-task-recovery-handoff.md)及[混合交接](2026-11-02-mixed-task-recovery-handoff.md)；其他分类与顺序仍未认证 |

依据：[H3.1原矩阵](2026-11-01-w1h31-cross-chain-recovery-design.md)、[H2.2-A](2026-11-01-w1h22a-persistence-fault-handoff.md)、[H2.2-B](2026-11-01-w1h22b-concurrency-handoff.md)、[H3.2-1](2026-11-01-w1h321-recovery-handoff.md)、[2a](2026-11-01-w1h322a-response-loss-handoff.md)、[2b-1](2026-11-01-w1h322b1-process-kill-handoff.md)。逐syscall、断电、介质故障均另列开放。

### 2026-11-02 accepting保存后、冻结前进程终止验收

测试子进程在`accepting_persisted_before_freeze`检查点写完并同步原子握手后暂停。父进程认证revision 1/2的封套、前驱哈希、记录哈希、typed记录、命令摘要以及allocated→accepting迁移；另确认没有冻结输入、任务或报告。子进程事件日志确认freeze=0、claim=0后才强杀。该协调器路径不启动worker或引擎，因此本测试没有原生/FFI执行；合成event计数不替代外部系统调用或实际消费账本。

新协调器恢复为一次`unknown`，没有补建任务、冻结输入、报告、排队或可领取工作；第二次重开不增加修订，保存材料字节稳定。事件记录检测到测试路径直接调用的冻结闭包以及claim入口，避免仅依赖未覆盖直接冻结路径的旧计数器。2026-11-04在`main / 622546c`复核该挂点并重跑聚焦、CLI、workspace、格式、Clippy和schema回归，结果见[TESTING](../../TESTING.md)。这只关闭首次accepting窗口；其他逻辑窗口、调度、syscall、断电和介质故障继续开放。

### 2026-11-02 恢复操作unknown追加的P/U/R故障

对两条手工构造且无匹配任务的accepting操作链，在恢复追加unknown revision 3时分别注入发布前失败、发布后不确定和写后复读失败。每种情况下持锁重开都按磁盘提交点续做：未发布的修订只追加一次，已发布修订不重复追加；无任务、报告、冻结或派发。完整结果见[TESTING](../../TESTING.md)及[故障交接](2026-11-02-unknown-operation-fault-handoff.md)。混合unknown/accepted操作顺序已另经映射并完成一个独立K场景，详见[映射](2026-11-02-mixed-operation-recovery-map.md)和[交接](2026-11-02-mixed-operation-recovery-handoff.md)。这仍只覆盖各自限定的状态和提交点；下一批从剩余矩阵筛选W1-C前必要的恢复与调度门禁。

### 2026-11-02 混合unknown/accepted恢复顺序K

按先行映射直接构造两条操作链和一个queued任务，在第一条无任务操作已保存unknown revision 3、第二条带任务操作仍为accepting revision 3时执行子进程终止。父进程认证全部链和冻结输入绑定，确认freeze=0、claim=0；持锁重开只追加第二条accepted revision 4和任务interrupted revision 2，重复重开无新修订，九个恢复后材料文件字节稳定。完整证据和命令见[TESTING](../../TESTING.md)及[混合恢复交接](2026-11-02-mixed-operation-recovery-handoff.md)。该fixture不证明正常服务可以同时保有两条操作预占，也不关闭其他操作顺序、任务分类或调度门禁。

### W1-C单次Rabbit有限分析设计

基于固定Rabbit请求、当前catalog/banlist snapshot ID及CDB/core/script清单SHA，完成一次无自动重试的候选分析设计。执行前必须重新核验资产和隔离构建身份；任何差异均停止。预算固定为node 10000、beam 32、depth 64、top-k 5、60秒搜索时限，外层观察上限240秒；结果只能按实际终态和逐线路重放状态表述。没有启动workbench、worker或引擎，未创建研究scope；真实分析仍须另立执行范围，详见[W1-C设计](2026-11-02-w1c-single-rabbit-local-analysis-design.md)。

| 工作 | 退出条件 |
|---|---|
| 文档收敛 | 需求、四窗口、剩余门禁和部署身份均可追踪 |
| H3.2-2b余项梳理 | 将设计逻辑窗口及调度映射已有证据，选择一个未覆盖窗口，固定握手、预算和停止条件 |
| 后续H3.2-2b窗口 | 对照矩阵选择并独立覆盖剩余逻辑窗口及必要调度边界；逐syscall、断电和介质故障另列 |
| W1-C | 合成门禁后设计固定Rabbit输入、资产、预算和验收；真实执行另行安排 |
| L1 | 分批核验39卡语义、别名、语言及使用和再分发依据；未知保持未知，可并行 |
| R1b-3 | 设计独立scope、消费、暂停重开与独立重放，真实执行另行授权 |
| P4-R5/W2 | 确定可比账本和口径，干净环境核验双资产、启动与牌组往返，分别绑定源码、产物、资产 |
| P1/复盘 | 每批选择一个动作、观察、概率或循环阻断项，产出可复现实验，按成本复盘 |

逐卡人工建模适合定向认证但全卡维护成本高；完整引擎搜索保持执行权威但完整性和规模未解。推荐研究语义辅助排序、引擎执行、独立证明；证明性剪枝须有独立可核查安全依据。

## 证据与部署

旧普通包CLI和worker哈希本轮与清单匹配，不证明当前源码部署。历史`a21d587`候选双资产诊断受预算截断且缺可比账本，P4-R5开放。Tenki pin、Curry来源缺口和历史账本保留；已删除旧忽略配置的原哈希见TESTING，哈希清单不是备份。
### 2026-11-03 P1 Ground Collapse离线准备恢复

当前Ground opcode24实验设计中的固定来源门禁已从失败推进到通过。私有归档索引映射并逐字节校验后，将Curry交付及V1–V5来源链所需13份历史文件恢复到原忽略路径；归档副本保留。新离线报告通过Curry交付、历史来源、冻结候选、运行资产/core、输入稳定性和工具源码稳定性六项检查；独立verify-only复核138个文件输入及5个目录输入。报告`execution_ready=false`，旧实际消费仍`null`，未创建scope，native/runner/worker/FFI均为0。详细记录见[测试](../../TESTING.md)、[Ground实验设计](2026-11-03-ground-collapse-opcode24-experiment-design.md)和[证据保留清单](../../EVIDENCE_RETENTION.md)。

下一研究批实现隔离的Ground阶段driver和合成协议测试，随后独立审阅固定来源与输入绑定；真实scope继续另行授权。它只推进固定opcode24候选的局部到达与响应接受试验，不改变完整动作、概率、循环、全局最优或P4发布门禁。

### 2026-11-03 Ground Collapse阶段驱动与合成验证

已新增独立Rust收费batch和单阶段runner，以及Python协议复核与最多5次请求的顺序协调器。Rust adapter库56项单测、runner示例2项单测通过；Ground协议、准备和阶段协调器Python测试54 passed、19 subtests passed。workspace全目标Clippy和格式检查通过。直接opcode24路线按4次请求结束于响应接受及独立重放；若出现opcode18则使用第5次请求。异常或账本不确定时停止且不重试，所有广义资格仍为false。

这批只有合成验证：没有创建scope或账本，没有启动runner、worker、引擎或FFI；当前准备报告仍`execution_ready=false`。下一步独立复核driver、runner与冻结输入的身份绑定，并用新源码身份重跑离线准备。真实scope仍需单独授权，不改变全动作、概率、循环、全局最优或P4发布门禁。

### 2026-11-03 Ground阶段工具源码绑定复核

阶段driver、Rust runner、Python协调器及协调器测试现已纳入固定19成员工具包；v1 schema允许正整数结构计数，当前profile和ZIP校验仍要求精确19个成员。`tests.test_ground_collapse_preparation`为36 passed，schema回归为8 passed、2 skipped（跳过项要求显式启用真实v2报告或本机快照/报告）。最新离线报告位于`data/runtime/p1-ground-collapse-preparation-current-2026-11-03-driver-review-2/preparation.json`，SHA-256=`a238a2f114c7cb26b6f1e79d6ca34b3e5f01f33bdb57eab0b6d2f650c2bb8c99`；六项检查通过，CLI verify-only复核138个文件输入及5个目录输入。报告`execution_ready=false`，旧实际消费与历史累计仍`null`，本批native/runner/worker/FFI均为0，未建scope。原2026-10-27报告仍缺失；归档恢复及driver-review-1快照均保留。

当前源码绑定候选清单已完成独立只读审阅，身份绑定、自摘要和hold/0调用边界均通过。若继续该研究案例，下一步评估单次窗口执行准入；当前报告不授权scope。否则按路线复盘选择另一个独立小批，不改变工作台有限分析、全动作/概率/循环/最优性和P4发布门禁。

### 2026-11-03 Ground离线准备报告文档更新后身份复核

L1权利审计文档写入后，按固定路径重跑Ground准备报告`--verify-only`，返回`valid=true`、`preparation_successful=true`，native/runner/worker调用均为0。独立ZIP及当前源码核对确认19个profile成员全部匹配。完整当前源码身份在忽略文件`target/p1-ground-collapse-source-review-2026-11-03/source-identity.json`中；报告原先的710文件工作树摘要仍保留为历史捕获身份，不用作本次当前身份。旧报告六项来源检查及输入哈希仍稳定，报告SHA未变。

该复核没有填充新的scope、预算、worker、最终请求哈希或prompt ID；报告`execution_ready=false`，因此当前只关闭了文档更新后的离线来源再验真，不关闭原生提示/响应窗口。真实实验需要新manifest绑定最终build与请求，独立授权和窗口仍开放。

### 2026-11-03 Ground Collapse候选执行清单离线评审

根据上述下一步，在当前HEAD `672e5a823fcad60e9413d79cac810b68a2bb003c`上完成候选源码、隔离构建、冻结案例、stage 1请求、工具包及运行资产的只读绑定。准备报告`a238a2f114c7cb26b6f1e79d6ca34b3e5f01f33bdb57eab0b6d2f650c2bb8c99`的710文件身份仍是历史捕获元数据；当前完整源码身份在文档完成后另行采集并写入忽略机器清单。19成员ZIP/list、固定候选案例摘要、最终stage 1请求摘要、runner/worker产物和完整脚本目录树哈希均已绑定。详情见[候选清单离线评审](2026-11-03-ground-collapse-candidate-manifest-review.md)及[TESTING](../../TESTING.md)。

隔离`cargo build --offline --locked`成功；CLI `--verify-only`返回`valid=true`、`preparation_successful=true`。机器清单类型是`ground_collapse_candidate_manifest_review_v1`，状态为hold，`execution_ready=false`、`scope_created=false`、`scope_authorized=false`；最终原生请求与实际prompt ID仍为空。没有创建scope/账本/窗口，也没有启动runner、worker、引擎或FFI。路线文字校正后重新绑定了完整源码与最终build record，独立只读审阅确认当前清单字段一致；执行准入决策仍开放，scope执行仍需另行明确授权。
