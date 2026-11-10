# W1-H1 分析任务HTTP合同设计

当前状态以[TASKS](../TASKS.md)和[TESTING](TESTING.md)为准：H3.2-2a、2b-1四个限定进程终止窗口及accepting保存后冻结前窗口已验收；其余2b窗口/调度及系统故障仍开放。W1-C单次Rabbit本机有限分析已按scope完成并在重开后稳定读取，结果为`budget_limited/time_budget`；报告来源未独立认证，FFI/消费未独立计量。普通启动保持`analysis_not_configured`。本文历史设计段落保留原时点。

H3.1仅设计交付：[跨链恢复与响应丢失设计](superpowers/plans/2026-11-01-w1h31-cross-chain-recovery-design.md)、[交接](superpowers/plans/2026-11-01-w1h31-recovery-design-handoff.md)。现有跨链认证/分类可复用；新增完整恢复与响应丢失矩阵尚未实现／尚未运行，留待H3.2。普通启动仍为`analysis_not_configured`。

当前状态：H2.1提供内部操作存储；H2.2已实现本文六个HTTP端点及状态/结果DTO；显式配置下的生产单任务执行器及W1-C固定Rabbit准入已接入。W1-C一次有限本机分析已到`budget_limited/time_budget`，报告来源独立认证仍开放。普通启动仍未配置分析服务；H3.2-2b其他窗口/调度及系统故障继续开放，详见[TASKS](../TASKS.md)和[TESTING](TESTING.md)。本文早期“拟议”描述保留设计时点，不代表当前接口未实现。

日期：2026-10-31；设计基线main / 577924b。本文接口及公开DTO为设计合同；H2.1后来实现了内部操作存储，但当前[工作台](WORKBENCH.md)没有任务HTTP，不能据此声称分析用户流程已接通。

## 1. 请求与端点 v1

所有JSON均UTF-8，固定schema_version=1及各端点的kind；递归拒绝重复键、未知/缺失字段及错误数字类型。整数拒绝bool、浮点和指数形式；评分仅接受服务配置的有限数值。路径ID为服务生成的32位小写十六进制，不接受路径片段、编码斜线或浏览器自选输出位置。下列六端点和无路径DTO是H2.2已实现的v1合同，不修改旧草稿API。

统一错误体为schema_version=1、kind=analysis_api_error、error对象；error含code、可空operation_id/job_id及可空field（固定字段定位符），不含原始异常。非JSON协议拒绝可沿用现有安全门禁错误体；业务错误使用此新合同。所有业务响应Cache-Control:no-store，不提供CORS放行。

| 方法/路径 | 必填输入及来源 | 成功响应（kind） | 失败与重试 |
|---|---|---|---|
| POST /api/analysis-operations | schema_version=1，kind=analysis_operation_allocate；无其他字段 | 201 analysis_operation：服务operation_id、revision、allocated状态、时间及可空指令/任务绑定 | 503配置/存储不可用；丢失分配响应可重新分配，旧空操作不产生任务 |
| PUT /api/analysis-operations/{id} | schema_version=1，kind=analysis_submit；draft_id、draft_revision、opening_hand、seed、rules、catalog_id（可空）、banlist_id、as_of、search | 首次有效提交先返回202 analysis_operation（accepting）；后台冻结后以GET观察accepted或rejected；已接受重复200，同一job_id | 400格式；409指令冲突/容量；422用于allocated阶段同步拒绝（如固定profile不符）；后台冻结失败保存在rejected及原错误码，后续GET返回状态，重复PUT重放已保存拒绝；503停派发/提交不确定。先查询原ID，不生成替代任务 |
| GET /api/analysis-operations/{id} | ID；无body | 200 analysis_operation：allocated/accepting/accepted/rejected/unknown及绑定 | 404明确不存在；503不能认证。404不推定旧调用消费为0 |
| GET /api/analysis-jobs/{id} | ID；无body | 200 analysis_job_status：已认证保存记录的白名单 | 404不存在；503存储不可认证，不能返回空成功 |
| GET /api/analysis-jobs/{id}/result | ID；无body | 200 analysis_job_result：完成或预算截断报告投影 | 409 job_result_unavailable（未完成或其他终态）；503报告损坏/不可认证 |
| DELETE /api/analysis-jobs/{id} | schema_version=1，kind=analysis_cancel，expected_revision整数 | 200 analysis_job_status：cancelled | 409 job_revision_conflict/cannot_cancel_running/job_terminal；404不存在；503停派发。重复请求查询原状态，不重复推进 |

命令字段映射：draft_id/revision由草稿保存响应取得；牌组由服务在同锁revision快照读取。其余分析参数映射AnalysisFreezeSpec，再由现有prepare验证五张起手、完整牌组、日期、预算及catalog/CDB。请求catalog_id必须显式存在，可为null；banlist_id可为latest-ocg。服务评分、本机引擎配置和快照根不由浏览器提交。

### 字段类型及错误映射（v1实现合同）

| 字段 | 类型/约束 | 当前映射 |
|---|---|---|
| draft_id / draft_revision | 服务草稿ID字符串 / 草稿内容SHA-256字符串；不是任务整数revision | AnalysisFreezeSpec.draft_id / expected_revision |
| opening_hand | 恰5项非零u32数组，保序保重复 | opening_hand及prepare多重集校验 |
| seed / rules | u64整数字面量 / 固定ocg-mr5字符串 | seed / rules |
| catalog_id / banlist_id | 必须出现的string或null / 非空string；允许现有latest-ocg | catalog_id / banlist_id；冻结后均为具体内容ID |
| as_of | YYYY-MM-DD合法日期string | as_of及禁限生效门禁 |
| search | 五字段全必填对象 | SearchBudget；不使用省略字段默认值 |
| expected_revision | u64整数，当前任务图仅1/2/3 | cancel的任务revision，不是draft_revision |

search逐项范围：top_k 1–100、node_budget 1–1,000,000、beam_width 1–1,024、max_depth 1–1,024、time_limit_ms 1–3,600,000。评分来自分配时服务ScoringConfig的board_interaction/resource_advantage/follow_up/complexity，全部有限，不接受客户端评分覆盖。

### W1-C显式配置准入（2026-11-03）

通用HTTP schema仍表达较宽的请求范围；生产显式W1-C配置另加固定profile。非固定手牌、seed、rules、snapshot、banlist/date或SearchBudget在`allocated`操作提交前返回422 `analysis_profile_mismatch`，操作保持allocated且不冻结、不建job。冻结后的完整牌组及运行身份再次校验；不匹配时操作持久拒绝且不产生job。派发前校验隔离CLI/worker、配置、快照和完整引擎资产身份；认领后的包身份漂移提交`AssetMismatch`执行前失败并停止派发。配置不启用该profile时的既有合同行为不变；普通工作台默认不配置分析。

格式/重复键/未知字段用400 analysis_request_invalid；未知操作/任务用404 analysis_operation_not_found/job_not_found。冻结的revision_conflict为409；其余已知AnalysisFreezeError原code为422（包括draft_not_found、deck_illegal、opening_hand_invalid、snapshot_unavailable、catalog_cdb_mismatch等），不携带原异常。容量拒绝409 analysis_queue_full，摘要冲突409 analysis_operation_conflict，提交不能认证503 analysis_commit_uncertain。GET操作总是以200返回可认证的保存状态；重复PUT对accepted返回200，对accepting返回202，对rejected重放保存的原409/422及error_code，对unknown返回503 analysis_commit_uncertain。语法错误在识别有效指令前不绑定/推进操作；基础设施错误503不伪造业务拒绝。

analysis_operation响应固定含schema_version、kind、operation_id、revision、created_at_ms、updated_at_ms、state、command_sha256、job_id、frozen_binding_sha256、error_code；未产生绑定的字段显式null。allocated不表示已提交分析，accepted只表示任务已持久接受，不表示运行成功。accepting建议客户端间隔1秒GET轮询；unknown停止自动重试并显示不确定性。

## 2. 创建幂等与跨文件提交

H1设计时提出新增独立AnalysisOperationRecordV1及严格schema、不可变操作修订链，保存在服务任务根operations/<operation_id>/revisions/。H2.1已实现该内部布局、根白名单和统一目录锁；不能通过另开第二写者访问同一任务根。旧任务封装与状态合同不改。本段后续HTTP与公开投影描述为H1设计时点，H2.2实现状态见本文开头。

操作记录内部必含schema_version/kind、operation_id、revision、created_at_ms/updated_at_ms、state、service_context（评分/默认catalog ID/配置摘要）、command及command_sha256、预分配job_id、可空frozen_input及frozen_binding_sha256、可空rejection（http_status/error_code）及可空error_code（unknown固定analysis_commit_uncertain）。未产生值显式null；frozen_input仅用B1无路径白名单，不序列化runtime。封装另含record_sha256和previous_sha256，采用B3同目录同步/独占发布/写后复读原语；操作修订与任务修订分别编号，不套用任务1/2/3上限。

| 操作前态 | 允许后态及条件 |
|---|---|
| 无 | allocated revision 1：上下文已保存，命令/任务绑定均null |
| allocated | accepting：容量预占且固定命令、摘要、job_id；或rejected：容量/可认证输入拒绝并保存指令及原HTTP错误 |
| accepting | accepting：仅追加已认证的冻结输入绑定；不能改变命令、job_id或上下文 |
| accepting | accepted：对应任务链已提交且绑定一致；rejected：冻结明确失败且未提交任务；unknown：重启后无法认证任务提交结局 |
| accepted / rejected / unknown | 不再变更；重复查询/提交不追加修订、不重新排队 |

每个真实转换revision加1且时间不倒退；任何链冲突/写后不确定停派发，不强行写unknown来掩盖不可认证存储。重启分类仅在链已认证时追加，重复重启不重复推进。allocated的容量拒绝无需冻结；语义准备拒绝发生在accepting后。服务内部配置变更必须拒绝旧操作首次提交并明确diagnostic，不能改写其已冻结上下文；已accepted读取不重查实时配置。

分配时保存allocated及服务冻结上下文：评分配置、可空catalog请求的具体默认catalog ID、非公开配置身份摘要。评分不得随配置热更新改变同一操作的含义；本机路径只在服务配置中，不写公开记录。未提交空操作只占登记空间，不占队列；首版不自动删除或复用操作ID，资源不足返回503 analysis_operation_capacity，不隐式驱逐历史记录。

指令摘要使用固定域workbench-analysis-command-v1与固定顺序的类型化紧凑JSON元组，依次含draft_id/revision、起手（保序）、seed、rules、catalog选择、banlist选择、as_of、search、分配时服务评分和默认catalog ID。JSON成员输入顺序不影响摘要。保存客户端选择（包括null和latest-ocg），不能先重新解析可变别名再判断重复。冻结后另存B1 binding_sha256及实际解析身份，不混用两种摘要。

提交流程：严格解码 → 读取同一操作原记录与上下文 → 比较指令摘要 → 已accepted/rejected/unknown直接返回保存结果，不冻结、不扫描、不入队 → 同一协调锁下检查容量并预占唯一待入队槽 → 保存accepting（含指令、摘要及预分配job_id），首次PUT立即返回202 → 后台锁外执行W1-A冻结 → 锁内复核操作与预占 → 保存已冻结输入绑定的操作修订 → 以预分配job_id持久提交queued任务 → 保存accepted操作修订并更新内存队列。后台冻结失败时保存rejected；客户端继续查询同一操作以读取最终状态。

预占不是queued或running，不产生可执行票据；冻结期间仍可查询/取消其他任务，其他创建不能抢该预占。本机请求线程断开不撤销已保存accepting。并发同ID：相同指令返回202 accepting或保存结果，不重复冻结；不同指令409 analysis_operation_conflict。不同ID继续受一运行一排队限制。容量拒绝和准备拒绝均保存rejected；同ID重试返回同一拒绝，用户调整后须明确新建操作。

accepting后的任何写入不确定或操作/任务绑定冲突都使整个协调器停派发。任务已提交、accepted尚未提交时仍不可领取该任务。重启先只读核对全部操作与任务，再进行现有queued/interrupted、running/unknown分类；能认证操作的预分配ID、指令、冻结绑定及任务链时可追加accepted绑定（任务可能已interrupted），不能恢复排队或重发。只有accepting而缺少可认证任务时操作归unknown，不据任务缺失重试提交。

allocated重启后仍可由明确PUT首次提交，不能自动执行；accepted重复请求不受草稿、默认快照或实时资产后续变化影响。时间倒退、链损坏和不可认证状态拒绝写入。没有跨文件原子事务承诺；操作链与任务链的恢复规则就是提交缺口处理，不用最后一个文件名猜结果。

设计基线上的`DurableAnalysisCoordinator::submit`自行生成job_id。H2.1现新增受控预分配ID提交与操作协调器，复用原B3提交钩子/状态验证；不允许浏览器传job_id、不修改模块全局值或复制整套队列。HTTP仍不得直接调用内部存储。

## 3. 状态、结果与安全投影

analysis_job_status固定字段：schema_version、kind、job_id、revision、created_at_ms、updated_at_ms、state、input、report、error_code、service_state。input使用已验证B1请求、draft_id/revision、身份、评分及binding_sha256白名单，不携带运行配置或catalog正文；report仅含B1报告引用或null。GET从持久链取得最新可认证修订，包含历史终态，不能只查活动snapshot。

analysis_job_result固定含schema_version、kind、job_id、revision、input_binding_sha256、report引用、budget、termination、scoring、stats、lines及evidence。stats白名单固定为nodes、engine_calls、cache_hits、pruned、failed_branches、elapsed_ms、replay_ms、peak_frontier、max_decision_depth、completed_lines及可空parent_peak_working_set_bytes/worker_peak_working_set_bytes；未来类型新增字段不自动公开。lines逐项只含id、decisions、evaluation、status（来源line.result.status）、replay_verified、coverage_gaps。evaluation只投影服务固定白名单的kind/profile_version及interaction/resources/follow_up/decisions/total有限数值（decisions为整数），省略explanations和内部coverage_gaps自由文本。coverage_gaps只映射已知稳定码，无法分类统一coverage_gap_unclassified，不透传原文。不复制DuelResult、EngineEvent原始文本、loaded_scripts、WorkerError.message或runtime_request。卡片以卡号和Choice展示，首版不返回card_names/名称正文；如未来接名称须另核来源与使用边界。

evidence固定区分report_contract_validated=true与report_origin_authenticated=false，并声明search_complete=false、global_optimality=false。合成接口验收只能标synthetic；W1-C之前没有production分析后端。投影不从客户端或报告自述推定来源，不生成运行凭证。空线路保留:no_verified_lines；exhausted不表示找到解或全局穷尽，预算截断保留原文原因。

沿用精确127.0.0.1:port Host、全部API的Bearer token、非GET的精确Origin。上限保持16KiB header、1MiB请求body及32连接；请求头和请求体共用从accept开始计算的15秒绝对读取期限，socket写超时为5秒；不新增浏览器本机路径入口。严格JSON业务解析必须补充现有parse_json的重复键门禁。

| 服务情形 | 允许 | 拒绝 |
|---|---|---|
| 正常且分析配置齐备 | 操作/任务查询、提交、排队取消 | 运行取消、终态再执行 |
| 分析未配置/后端未启用 | 原草稿功能 | 所有分析路由503 analysis_not_configured；不回退真实执行器 |
| 协调器因不确定提交停止 | 单独只读诊断；已启动服务中的操作/任务GET可读取认证保存链并标示service_state=stopped | 所有分析写操作503 analysis_coordinator_stopped |
| 根锁被其他进程占用 | 草稿和HTTP服务均未启动 | 配置分析服务时存储打开失败，HTTP listener启动前退出；不无锁读取 |
| 材料损坏或来源不可认证 | 固定逻辑角色诊断 | 相关GET/全部分析写入503 analysis_store_unverifiable，不返回旧缓存冒充当前 |

历史设计基线中的`coordinator.history`在stopped时拒绝。H2.1现提供`inspect_operation/inspect_job`纯只读查询；HTTP GET完整认证保存链与报告引用，但不持有调度互斥锁，也不追加重启分类。并发提交期间查询可观察到一个有效的已提交前缀。新状态不代表统计消费为0。原错误原文只保留私有诊断，所有公开值递归经过白名单；无法识别的评价profile、Choice/状态或非有限分数应拒绝投影，不把未知自由字符串作为标识直出。

## 4. 静态场景矩阵（不是已运行测试）

Rabbit走查采用tests/fixtures/rabbit.request.json：40/3/0、五张起手85138716/2964201/2964201/2964201/2971090、seed1、ocg-mr5、latest-ocg、2026-10-07，预算5/10000/32/64/60000（top_k/node/beam/depth/ms）。不表示当前资产下已准备或执行通过。

| 场景 | 保存状态与响应 | 客户端动作/禁止行为 |
|---|---|---|
| 首次有效提交 | 先持久保存accepting并立即返回202；后台随后冻结、创建queued任务并保存accepted，或保存rejected及冻结错误 | 继续轮询同一操作；只有观察到accepted及job_id后再查询任务，不声称执行成功；rejected后停止该操作并按已保存错误修正输入 |
| 同ID相同指令、默认快照已变化 | 返回原绑定200；无冻结/扫描 | 不生成新任务 |
| 同ID不同指令 | 原记录不变，409 conflict | 明确新建操作，不替换旧绑定 |
| 同ID并发 | 一个accepting，其他202同状态 | GET等待，不第二次冻结 |
| 不同ID容量满 | rejected，409 analysis_queue_full | 槽位空后明确新操作，不暗中排队 |
| accepting后发现草稿revision/起手/预算错误 | 初始PUT仍为202；后台保存rejected及409 revision或422 W1-A错误码，GET返回该状态 | 同ID重试会重放拒绝；修正输入后明确新操作 |
| accepting保存前失败 | 无任务，503 | GET确认；不据缺失推定收费0 |
| accepting后冻结中断 | 操作unknown，无新任务 | 停止自动提交；不换ID重发 |
| queued已存、accepted未存或回复丢失 | 保留同job_id；恢复认证后绑定原任务 | 查询原操作，不重新执行 |
| 报告先存但终态缺失 | running重启unknown，result409 | 不用孤立报告补认完成 |
| 完成/预算截断/空线路 | 按B1终态，result200原始原因 | 展示有限结果，不声称最优 |
| failed/interrupted/unknown | 状态GET200，result409 | 不显示空成功，不自动重发 |
| 取消胜出 | cancelled持久后200 | 不会派发 |
| 领取胜出/旧revision | 409 cannot_cancel_running/revision | 刷新状态，不重复推进 |
| queued/running重启 | interrupted/unknown，不重排 | 只读展示；重复重启不重复分类 |
| 报告损坏/根漂移/提交不确定 | 503、停写停派发 | 保留证据，不重试执行 |
| 错Host/token/Origin、超大、重复键 | 沿安全门禁400/403/413或业务400 | 不创建操作或任务 |
| 结果包含路径/令牌/原始异常 | 投影拒绝，503 analysis_projection_invalid | 不回退返回完整报告 |

## 5. H2/H3实施前置与本批验收

H2.1交付时状态（历史）：操作记录/schema、预分配任务ID的私有提交、容量预占、跨链认证和停止后的只读查询已完成。H2.2随后接入严格版本化HTTP和白名单DTO；测试使用专用合成执行边界，普通生产CLI不配置分析后端。完整验收剩余门禁见本文开头和[H2.2交接](superpowers/plans/2026-11-01-w1h22-analysis-http-handoff.md)。

H3覆盖响应丢失、并发重复、所有跨链发布缺口、停派发只读边界、报告损坏和重启分类；注入故障时断言后继执行为零。保留W1-A/B1/B2/B3合同回归。W1-C另定真实资产、输入、预算、调用及停止边界；运行中取消、细粒度进度和自动恢复不在首版。

本批只做源代码映射、设计走查、独立只读审阅、文档链接及git diff --check；不构建、不运行测试或引擎，不部署、提交或推送。认证研究子集40、政策预留7、规划47；全部历史实际累计未知。候选部署诊断不并入该认证子集。

## 6. 事实源与只读审阅

静态对照源码：[现有HTTP与安全门禁](../crates/ygo-cli/src/workbench.rs)、[W1-A冻结](../crates/ygo-cli/src/workbench_analysis.rs)、[任务合同](../crates/ygo-cli/src/workbench_analysis/jobs.rs)、[持久协调器](../crates/ygo-cli/src/workbench_analysis/durable.rs)、[存储/报告](../crates/ygo-cli/src/workbench_analysis/persistence.rs)、[分析合同校验](../crates/ygo-api/src/combo.rs)、[预算/评分/线路](../crates/ygo-search/src/combo.rs)、[Rabbit样例](../tests/fixtures/rabbit.request.json)。内部queue位于workbench_analysis/queue.rs（由workbench_analysis模块载入），不据模块声明推断HTTP已实现。

独立只读设计审阅已完成：核对上述实现、任务与持久化文档、Choice及Rabbit参数；未发现核心提交策略阻断。按审阅补齐草稿revision字符串与任务整数revision区别、操作状态边/重复拒绝语义、Evaluation自由文本隔离及固定统计白名单。该结论为静态设计审阅，未构建或运行接口、恢复、引擎测试。
# H2.2 实施补充（2026-11-01）

本文六端点现已有实现及测试专用合成服务，生产启动保持未配置；并非真实分析后端。接受阶段持久保存accepting后返回202，后续锁外冻结与完成提交复用H2.1核心；历史下文的“尚未实现”属于H1时点。当前测试证据与限制见[H2.2交接](superpowers/plans/2026-11-01-w1h22-analysis-http-handoff.md)。

## H2.2-A 逻辑持久故障验收（2026-11-01）

测试专用选择器按操作/任务/报告链、目标状态和 revision 定位提交，分别模拟发布前明确失败、发布后不确定和写后复读失败；生产参数、报告和公开HTTP合同不变。已发出的202只代表接受中记录已保存，后台故障通过后续保存状态和停派发状态反映，不能修改原响应。同步提交失败必须为503，不能套用原业务拒绝。

提交结果不确定时保留正式文件和内存槽位并停止派发；queued已保存而accepted未保存时不能领取。报告已保存而终态缺失时保留孤立报告，GET不据此补认完成。停止后GET仍完整认证操作/任务链及引用报告，不持有调度互斥锁、不追加重启分类、不返回缓存成功；健康历史可读、明确不存在404，无法认证503。

该矩阵只覆盖列出的逻辑提交点，不代表每条文件系统调用、断电、OS崩溃或响应丢失验收。H2.2-B重复提交、容量及取消/领取调度见[并发交接](superpowers/plans/2026-11-01-w1h22b-concurrency-handoff.md)。H2.2-A/B合成门禁通过；H3和W1-C仍需独立完成。
