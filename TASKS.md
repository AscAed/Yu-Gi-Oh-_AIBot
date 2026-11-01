# 实施任务与验收状态

## 当前状态（2026-11-01）：W1-H2.2合成HTTP验收通过；H3与真实分析仍开放

本阶段合成HTTP故障与并发验收均已通过；分别见[H2.2-A交接](docs/superpowers/plans/2026-11-01-w1h22a-persistence-fault-handoff.md)、[H2.2-B交接](docs/superpowers/plans/2026-11-01-w1h22b-concurrency-handoff.md)和[TESTING](docs/TESTING.md)。六端点仍只在测试服务装配分析协调器；普通工作台启动返回`analysis_not_configured`，没有生产执行器。下一步转到H3响应丢失/跨链恢复设计，真实分析仍另定scope。

上批实施见[H2.2交接](docs/superpowers/plans/2026-11-01-w1h22-analysis-http-handoff.md)。六端点、异步接受、严格HTTP合同及无路径结果投影已有实现；普通启动分析保持未配置，不提供生产执行器。历史下文“HTTP未接入”描述保留其原时点；当前验收及剩余项见TESTING，本批不自动关闭H3或真实分析门禁。

H2.1内部操作合同和持久提交为H2.2提供核心，见[H2.1交接](docs/superpowers/plans/2026-10-31-w1h21-analysis-operation-handoff.md)。

历史设计见[W1-H1 HTTP合同](docs/WORKBENCH_ANALYSIS_HTTP.md)，续接见[H1交接](docs/superpowers/plans/2026-10-31-w1h1-analysis-http-handoff.md)。H1时点仅设计；H2.1实现内部操作ID、双摘要和跨链提交/只读查询；H2.2 HTTP及公开DTO的合成验收已关闭。H3跨链恢复与真实分析仍开放；范围见[TESTING](docs/TESTING.md)。

历史路线见[W1-H2.1后路线](docs/superpowers/plans/2026-11-01-post-w1h21-project-route.md)；W1-H1及W1-B3路线保留为历史时点。H2.2 HTTP实现、合成投影及A/B门禁已完成；H3跨链故障恢复仍开放，均不自动授权真实执行。

持久化实现见[W1-B3持久化与发布](docs/WORKBENCH_ANALYSIS_PERSISTENCE.md)。[W1-B2后路线](docs/superpowers/plans/2026-10-31-post-w1b2-project-route.md)及更早路线保留历史时点。

E1 只读诊断已完成：Tenki 归档的 `codec.rs` pin 为 `224…`；`e8…` 可认证到 Ground Collapse 工具包，但未认证为 Curry scope 的实际执行源码。当前 `6233…` 与 HEAD 内容按 CRLF→LF 规范化后相同。原失败和 pin 保留；后续 pin 处置需独立建立 Curry 来源链。详见[E1诊断](docs/superpowers/plans/2026-10-30-e1-tenki-codec-anchor-diagnostic.md)和[本轮记录](docs/TESTING.md#2026-10-30-e1-tenki历史保护锚点只读诊断)。

这是当前状态和开放任务的唯一入口。产品目标、研究定义及阶段依赖分别见[产品愿景](docs/PRODUCT_VISION.md)、[最优性研究](docs/OPTIMALITY_RESEARCH.md)和[路线图](docs/ROADMAP.md)；当前实施顺序以本节H2.2-A交接及[W1-H2.2后路线](docs/superpowers/plans/2026-11-01-post-w1h22-project-route.md)为准，其他路线保留各自历史时点。下方各批历史数字仅适用于其日期和范围，不覆盖本节。

| 阶段 | 当前能力与未完成门禁 |
|---|---|
| P0 | 首批身份、构建记录、清点与输入工具已交付；全正式OCG发行分母及依赖证据未完成 |
| P1 | P1.1协议、观察、局部原生案例和证据工具已推进；P1.2完整小问题尚不可进入证明，完整动作、真实概率、循环和独立值界仍缺 |
| P2 | 39卡字段存在性、来源绑定及缺口已离线登记；语义、zh-SC语言类别、别名映射、使用与再分发依据仍未通过，正式中文检索/更新服务未交付 |
| P3 | P3.1草稿CLI、B2本机工作台及只读C1字段状态接口已交付；分析/构筑未提供 |
| P4 | R1a首次失败诊断及R1b可恢复执行循环已实现；非空两动作、连续提示逐边界合成暂停/重开及中断/竞争门禁通过；真实执行和独立重放未认证，R2–R5门禁均未通过 |
| P5–P6 | 指定profile知识和有限关联已有；通用知识、主题识别、自动构筑与评估反馈未交付 |
| P7–P8 | 指定灰流丽场景有局部证据；通用干扰、全卡覆盖、最优性证明及可分发产品未交付 |

最近Ground Collapse opcode24批次只完成离线协议、合成oracle和固定来源准备，**新增native/runner/worker/FFI调用均为0**；`execution_ready`、原生可达、响应接受及完整性/概率/最优性资格均为false。13/14已有各自冻结案例的部分原生分支和独立重放；24实际提示、掩码及响应接受仍未知，详见[本批交接](docs/superpowers/plans/2026-10-27-ground-collapse-preparation-handoff.md)。

最新可认证会计口径为**认证消费子集40、政策预留7、规划47**；旧confirmation实际消费和全部历史实际累计仍为`null`。旧窗口和槽位依各自scope封存；新增原生实验必须另定范围、预算和窗口，不能直接执行既有准备报告。

本批A1首次失败诊断、B1牌组草稿基础及B2本机中文浏览器工作台已完成。B2只提供本机草稿编辑、YDK/JSON导入导出和可选本地卡表查询；不表示中文译文、牌组合法性或引擎行为已核验。说明见[工作台文档](docs/WORKBENCH.md)，交接见[B2交接](docs/superpowers/plans/2026-10-28-b2-workbench-handoff.md)，实跑范围见[TESTING](docs/TESTING.md)。

W1设计后的A阶段已交付：工作台所有API非GET请求在路由前均须通过本机Host、Bearer令牌和同源Origin门禁；Rust库新增内部`freeze_analysis_input`，在同一草稿存储锁内核对ID/revision并复制草稿，再通过现有`prepare`冻结搜索请求、已解析catalog/banlist及引擎资产身份。它不增加HTTP分析入口、队列或任务，也不运行适配器。见[W1-A交接](docs/superpowers/plans/2026-10-30-w1a-input-freeze-handoff.md)与[实测记录](docs/TESTING.md#2026-10-30-w1-a工作台同源保护与分析输入冻结)。

历史交付（W1-B1至B3）：完成无路径`AnalysisJobRecordV1`、严格JSON、纯状态核心、进程内合成队列、任务revision、报告私有存储、报告引用启动核验、持久协调器及内部合成故障矩阵。领取时先持久化running，再核对冻结期资产哈希；不匹配或提交结果不确定时停止协调器，重开时按已提交revision分类。H2.2随后接入任务HTTP及无路径DTO；当前剩余HTTP验收矩阵列于下方独立任务。报告来源、真实执行、逐syscall崩溃和断电持久性仍未认证。最新验证见[TESTING](docs/TESTING.md)。

C1离线字段核验已完成：冻结39卡逐项记录zh-CN/zh-SC名称、正文、别名及字段状态和候选哈希；候选正文不进入报告或工作台接口。zh-SC继续为`und`，语义审阅、使用依据和再分发资格未通过。报告、统计与限制见[LANGUAGE_REVIEW](docs/LANGUAGE_REVIEW.md)、[DATA_SOURCES](docs/DATA_SOURCES.md)和[TESTING](docs/TESTING.md)。

A3及P4-R1b离线实现现包含planner单次调用检查点和可恢复语义循环。两动作合成路线覆盖多次连续提示、End Phase及逐次QueryWitness审计；连续执行与每个语义调用边界暂停/重开结果相等，收费前保存失败与只读检查后的账本竞争均拒绝继续。合成适配器测试没有生成正式凭证；真实进程暂停、操作系统级崩溃矩阵及独立重放仍未认证。状态转移及限制见[执行恢复合同](docs/EXECUTION_RECOVERY.md)、[A3交接](docs/superpowers/plans/2026-10-28-a3-execution-recovery-handoff.md)和[P4-R1b交接](docs/superpowers/plans/2026-10-28-p4-r1b-resumable-execution-loop-handoff.md)。

### 当前开放任务

- [x] D2：更新项目定位、双轨计划、研究经验与文档导航；交叉核对记录见[TESTING](docs/TESTING.md)顶部。
- [x] 2026-10-27环境自检：区分部署包与开发资产，清理229个已确认空测试目录和本轮隔离Cargo缓存，整理pytest缓存及冗余直接依赖；范围和验证见[TESTING](docs/TESTING.md)。
- [x] 本轮环境自检：Python 3.12干净快照、隔离部署文档复制、普通部署smoke与replay、离线验真及文档检查；覆盖、跳过项和后续保留边界见[工作区自检](docs/WORKSPACE_REVIEW.md)及[验证记录](docs/TESTING.md)。
- [x] 环境后续：历史证据保留清单与SHA-256清点已建立；按用户决定暂不迁移，仅保留现有哈希清单，不表示证据已有备份。旧目录写入测试已改为target隔离仓库并验证不触碰原D盘证据；Windows目录符号链接实测仍受系统策略限制（对应用例跳过），最新源码双资产发布验收P4-R5仍开放；当前未授予任何研究scope。
- [x] A1 / P4-R1a：首次`DuelResult.error`与`QueryWitness::capture`失败均先由合成收费账本红测复现，再修复诊断验证器；没有可信查询、成功资格、收据或可恢复前缀。测试证据见[TESTING](docs/TESTING.md)与[交接](docs/superpowers/plans/2026-10-28-first-failure-and-deck-draft-handoff.md)。
- [x] B1 / P3.1：完成空/部分草稿、主/额外/Side编辑及YDK/JSON导入导出；草稿不等于完整合法牌组。CLI说明见[DECK_DRAFTS](docs/DECK_DRAFTS.md)。
- [x] B2 / P3：交付本机中文单页工作台，支持草稿新建/编辑/保存/重开、YDK/JSON往返及可选本地卡表查询；名称/译文仍明确标为未核验。服务与边界见[WORKBENCH](docs/WORKBENCH.md)，验收见[TESTING](docs/TESTING.md)。
- [x] C1 / P2.1 离线盘点：39卡字段存在性、来源哈希、冲突/缺失和状态接口已交付；未确认的语义、语言类别、使用与再分发依据保持未知。见[字段核验说明](docs/LANGUAGE_REVIEW.md)。
- [x] A3离线关口：版本化执行检查点、意图先写、单步推进、完成尾部调用复用和未决消费阻断已通过合成测试；未创建原生scope或调用引擎。
- [x] P4-R1b实现关口：新增独立可恢复语义执行入口，复用同步循环动作绑定/预测/结束阶段规则，逐收费调用持久化状态，并为查询审计单独保存进度；API和schema已实现，仍不产生正式凭证。
- [x] R1b-1离线多动作等价：非空两动作计划、多次连续提示的合成路线在每个语义调用边界暂停重开；动作证据、实际前缀、映射、选择、预测、查询及26条收费用途序列与连续执行一致。
- [x] R1b-2合成中断与竞争门禁：已验证完成尾调用复用、未知/未决消费阻断、语义及外层检查点发布失败时收费前零调用，以及只读检查后账本变化被拒绝；不代表操作系统级进程崩溃验证。
- [x] E1历史保护锚点只读诊断：确认Tenki归档`224…`与Ground Collapse工具包`e8…`的成员字节及代码差异；未找到证据把`e8…`绑定为Curry实际执行源码。诊断完成，历史材料和pin保留。
- [x] E1历史迁移处置：按用户决定不迁移，只保留哈希清单，不改pin或原始证据；保护测试验证缺少来源链时拒绝迁移且ledger/runtime哈希不变。
- [ ] E1七份历史ledger成功重审：仍缺少可把Ground Collapse源码版本绑定到Curry实际执行scope的来源链；因此不生成或宣称成功重审报告。此项不阻止按当前决策保留历史材料，但若未来需重审/迁移，必须先补来源证据。
- [x] W1工作台受限分析接入设计：已按Rabbit请求核对输入映射、完整牌组/资产门禁、任务状态、排队取消和有限搜索结果边界；仅为设计，未实现分析接口。见[W1设计](docs/superpowers/plans/2026-10-30-w1-workbench-limited-analysis-design.md)及[本轮静态记录](docs/TESTING.md#2026-10-30-w1工作台受限分析接入设计)。
- [x] D3：以W1设计分支为文档基线，记录当前定位、部署交叉核对和后续双轨路线；链接、差异及文件范围检查见[2026-10-30 W1后路线文档核对](docs/TESTING.md#2026-10-30-w1设计完成后的路线文档核对)。
- [x] W1-A工作台同源保护与分析输入冻结：API非GET请求统一执行Host/token/Origin门禁；同锁读取草稿revision，以现有`prepare`验证牌组、手牌、禁限日期、预算及snapshot/CDB身份，并返回拥有独立数据的冻结对象。合成测试未启动adapter、worker或研究账本；不提供分析HTTP端点。见[交接](docs/superpowers/plans/2026-10-30-w1a-input-freeze-handoff.md)和[TESTING](docs/TESTING.md#2026-10-30-w1-a工作台同源保护与分析输入冻结)。
- [x] D4：更新W1-A后评估、部署身份及双轨路线；静态核对见[TESTING](docs/TESTING.md#2026-10-30-w1-a后路线文档复核)。
- [x] W1-B1任务合同及纯状态核心：独立无路径白名单、双摘要、严格JSON、状态矩阵与合成兼容验收通过；不序列化进程内冻结对象，不提供任务存储、HTTP或队列。见[交接](docs/superpowers/plans/2026-10-30-w1b1-analysis-job-handoff.md)。
- [x] W1-B2内部合成队列与取消：单运行加单排队、排队取消、容量拒绝及票据结算；无HTTP、持久化或真实执行。见[交接](docs/superpowers/plans/2026-10-31-w1b2-analysis-queue-handoff.md)。
- [x] W1-B3.1/B3.2存储基础：不可变任务修订、严格链校验、排他锁、重启分类，以及报告严格读取/冻结输入绑定/私有落盘/哈希重读已实现；定向测试为合成合同测试，不认证报告来源。见[持久化设计与实现状态](docs/WORKBENCH_ANALYSIS_PERSISTENCE.md)。
- [x] W1-B3.3内部持久协调故障矩阵：覆盖submit/claim/cancel/fail/report文件与终态提交前失败、提交后不确定、停派发、孤立报告、重复终态请求、全部冻结资产角色/脚本路径漂移、进程强杀后的queued/interrupted与running/unknown分类。队列锁内持久提交后的状态更新没有可返回的错误分支；Rust操作系统进程强杀覆盖已完成，但文件系统每条syscall间强杀、断电/介质故障未认证。HTTP创建幂等标识与真实执行结果确认另在后续接口/执行器批次定义。
- [x] W1-H1分析任务HTTP合同设计：操作ID/幂等、提交顺序、状态与结果DTO、安全及失败矩阵完成静态走查和独立只读审阅；无生产修改或运行测试。见[设计](docs/WORKBENCH_ANALYSIS_HTTP.md)。
- [x] W1-H2.1内部操作存储：严格合同、36例共享语料、容量预占、幂等提交、跨链重开和停止后只读查询已合成验证；在H2.1交付时HTTP尚未实现。见[交接](docs/superpowers/plans/2026-10-31-w1h21-analysis-operation-handoff.md)。
- [x] W1-H2.2 HTTP投影实现：六端点、严格合同及无路径投影已接入；普通生产启动未配置分析后端。实现与定向验收见[交接](docs/superpowers/plans/2026-11-01-w1h22-analysis-http-handoff.md)。
- [x] W1-H2.2-A持久故障关口：42个逻辑提交故障、15个同步TCP503、12个202后后台故障及9类停止后查询通过；持久字节、内存槽位、实际后台冻结次数及只读稳定性均有断言。未复现需修改生产逻辑的缺陷；实测与边界见[本批交接](docs/superpowers/plans/2026-11-01-w1h22a-persistence-fault-handoff.md)。
- [x] W1-H2.2合成HTTP验收：六端点/无路径投影、逻辑持久故障、停止后只读认证、同ID并发重复、容量拒绝与重复读取、取消/领取线性化均有回归。限制为合成服务与已覆盖调度；不认证进程崩溃、客户端响应丢失或真实分析。见[H2.2-A](docs/superpowers/plans/2026-11-01-w1h22a-persistence-fault-handoff.md)、[H2.2-B](docs/superpowers/plans/2026-11-01-w1h22b-concurrency-handoff.md)及[TESTING](docs/TESTING.md)。
- [ ] W1-H3故障恢复：验证跨链提交缺口、响应丢失、并发重复与停止状态的只读查询；不自动重发。
- [ ] W1-C本机分析验收设计：合成门禁通过后固定Rabbit输入、资产身份、调用和停止边界；真实分析另行安排并单独记录。
- [ ] L1中文数据复核：逐批审阅39卡候选名称/正文语义、别名、字段、语言类别及来源/使用/再分发依据；未知项不提升为正式数据资格。
- [ ] P4-R1b-3真实恢复实验设计：定义固定场景、独立scope、预算、窗口、暂停/重开及独立原生重放标准；设计完成后真实执行另行授权。
- [ ] W2普通用户发布准备：独立干净环境验证启动、资源路径、草稿、导入导出和升级兼容；分别绑定源码、构建产物及资产身份。
- [ ] A2 / P1：从动作完整性、观察投影、条件概率、自然结束或循环中选一个阻断项，形成可复现实验设计；Ground Collapse仅为候选，任何收费/原生执行须另定scope和授权。
- [ ] A4 / P1：按已批准的单一研究设计验证所选缺口；不能只增加成功线路或从局部结果宣称完整小问题已证明。
- [ ] P4-R2：86项场景内规则完整语义与逐项原生认证；现有12项成对规则、1项实际Scythe灰点，仍缺74项规则资格。
- [ ] P4-R3：正式v6规划/报告/CLI及v1–v5完整兼容回归。
- [ ] P4-R4：冻结独立人工基准，完成16+32手可续跑评估及汇总验真。
- [ ] P4-R5：已在隔离目录从`a21d587`重建当前源码候选；普通/赛事doctor、身份均通过，smoke及独立replay各3/3通过。主工作区普通dist未切换。smoke均因30秒`time_budget`截断，且未找到可比研究账本，故发布门禁仍开放；完整哈希、资产身份和边界见[TESTING](docs/TESTING.md)。
- [ ] P0/P1/P5–P8：全卡发行分母、完整信息/概率与证明、通用知识/构筑反馈及最终产品验收，按阶段依赖继续。
- [ ] M1：比较研究关口与工作台用户流程的实际改善，按成本与证据选择下一个独立小批。

上述排序、依赖和停止条件见[W1-H2.1后路线](docs/superpowers/plans/2026-11-01-post-w1h21-project-route.md)。本次文档更新不改变scope、窗口、预算或部署授权。

前次交付后的603项源码归档身份、原生时点身份和普通dist是不同对象；后续文档、pytest配置和Cargo依赖整理已改变工作区，不再声称其与该归档完整逐字一致。实跑与静态核对分别见[TESTING](docs/TESTING.md)，历史导航见[HISTORY_INDEX](docs/HISTORY_INDEX.md)。


以下保留历史标题及原锚点；完整记录见同目录历史快照。

## 历史状态（2026-10-27）：Ground Collapse opcode24离线准备通过

[历史原文](TASKS_HISTORY.md#历史状态2026-10-27ground-collapse-opcode24离线准备通过)

## 历史状态（2026-10-27）：绑定V3恢复证据的Curry七阶段再验真

[历史原文](TASKS_HISTORY.md#历史状态2026-10-27绑定v3恢复证据的curry七阶段再验真)

## 历史状态（2026-10-26）：Curry V3真实来源角色适配与零runner恢复

[历史原文](TASKS_HISTORY.md#历史状态2026-10-26curry-v3真实来源角色适配与零runner恢复)

## 历史状态（2026-10-26）：Curry V2精确来源恢复与零runner验收

[历史原文](TASKS_HISTORY.md#历史状态2026-10-26curry-v2精确来源恢复与零runner验收)

## 历史状态（2026-10-26）：Curry V5已存证据恢复与报告发布诊断

[历史原文](TASKS_HISTORY.md#历史状态2026-10-26curry-v5已存证据恢复与报告发布诊断)

## 历史状态（2026-10-26）：Curry V5干净交付与单次零调用验收

[历史原文](TASKS_HISTORY.md#历史状态2026-10-26curry-v5干净交付与单次零调用验收)

## 历史状态（2026-10-26）：Curry V4精确输出合同与单次零调用验收

[历史原文](TASKS_HISTORY.md#历史状态2026-10-26curry-v4精确输出合同与单次零调用验收)

## 历史状态（2026-10-26）：Curry V3来源角色修复与只读验收

[历史原文](TASKS_HISTORY.md#历史状态2026-10-26curry-v3来源角色修复与只读验收)

## 历史状态（2026-10-25）：Curry V2账本交接恢复审计

[历史原文](TASKS_HISTORY.md#历史状态2026-10-25curry-v2账本交接恢复审计)

## 历史状态（2026-10-25）：Curry V1账本交接恢复审计

[历史原文](TASKS_HISTORY.md#历史状态2026-10-25curry-v1账本交接恢复审计)

## 历史状态：Curry V3预留绑定的七阶段验证（2026-10-25）

[历史原文](TASKS_HISTORY.md#历史状态curry-v3预留绑定的七阶段验证2026-10-25)

## 历史状态：Curry V3材料兼容与风险预留（2026-10-25）

[历史原文](TASKS_HISTORY.md#历史状态curry-v3材料兼容与风险预留2026-10-25)

## 历史状态：Curry V2风险预留（2026-10-25）

[历史原文](TASKS_HISTORY.md#历史状态curry-v2风险预留2026-10-25)

## 历史状态（2026-10-24）

[历史原文](TASKS_HISTORY.md#历史状态2026-10-24)

## 历史断点（额度不足时；2026-10-24）

[历史原文](TASKS_HISTORY.md#历史断点额度不足时2026-10-24)

## 历史状态快照（Curry v2审计后；2026-10-24）

[历史原文](TASKS_HISTORY.md#历史状态快照curry-v2审计后2026-10-24)

### 2026-10-21前后产品路线入口（历史）

[历史原文](TASKS_HISTORY.md#2026-10-21前后产品路线入口历史)

### 当时的既有v6专项门禁（历史；当前开放项见顶部）

[历史原文](TASKS_HISTORY.md#当时的既有v6专项门禁历史当前开放项见顶部)

## 阶段历史（时间点记录；不是当前任务清单）

[历史原文](TASKS_HISTORY.md#阶段历史时间点记录不是当前任务清单)

### 2026-10-18 从73414c6继续（整轮未完成）

[历史原文](TASKS_HISTORY.md#2026-10-18-从73414c6继续整轮未完成)

## v6收尾实施：基础集成

[历史原文](TASKS_HISTORY.md#v6收尾实施基础集成)

## 2026-10-16 重新选定赛事原表（三阶段实施中）

[历史原文](TASKS_HISTORY.md#2026-10-16-重新选定赛事原表三阶段实施中)

## 2026-10-16 赛事构筑来源关口（未通过）

[历史原文](TASKS_HISTORY.md#2026-10-16-赛事构筑来源关口未通过)

## 2026-10-16 多响应点与稳健展开顺序

[历史原文](TASKS_HISTORY.md#2026-10-16-多响应点与稳健展开顺序)

## 2026-10-16 单次灰流丽中断与恢复

[历史原文](TASKS_HISTORY.md#2026-10-16-单次灰流丽中断与恢复)

## 2026-10-15 通用目标与有界收益（已完成本轮验收）

[历史原文](TASKS_HISTORY.md#2026-10-15-通用目标与有界收益已完成本轮验收)

## 2026-10-14 Break Sword v2 与效果验真

[历史原文](TASKS_HISTORY.md#2026-10-14-break-sword-v2-与效果验真)

## 2026-10-14 语义规划首版交付（历史）

[历史原文](TASKS_HISTORY.md#2026-10-14-语义规划首版交付历史)

## 已交付：M0–M4

[历史原文](TASKS_HISTORY.md#已交付m0m4)

## 历史验证状态（2026-10-07）

[历史原文](TASKS_HISTORY.md#历史验证状态2026-10-07)

## 历史待办：M4.1 可复现交付（已由本轮完成）

[历史原文](TASKS_HISTORY.md#历史待办m41-可复现交付已由本轮完成)

## 待办：后续产品能力

[历史原文](TASKS_HISTORY.md#待办后续产品能力)
