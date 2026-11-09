# W1-C来源与调用计量合同设计（2026-11-04）

状态：分批实施中。2026-11-03单次Rabbit分析仍按原scope验收；2026-11-04已完成来源字节包、workspace-state-bundle、观察式构建记录、合成执行回执合同v1、`ProcessEngineAdapter` host观察、搜索调用attempt收集、job绑定持久attempt日志及合成FFI entered/returned事件。每次adapter调用前保存`Started`、FFI事件按attempt和call ID配对、返回后保存host结果；写入失败会停止后续调用，受控进程终止后重开将running job分类为unknown。Rust与Python验证器均执行LIFO和跨attempt唯一性检查；事件仍不是真实worker/ocgcore证明，报告producer认证或消费证据仍开放，source/build身份在workbench事件中为null。本计划不授权或执行新分析。

## 当前审计依据

[2026-11-04证据链审计](../../TESTING.md)确认，忽略目录中56项运行材料及package manifest内14条CLI/worker/config、输入/资产和身份报告记录的当前哈希均符合各自清单。操作、任务、结果和11文件存储清单在受控重开前后逐字节稳定。固定Rabbit输入、catalog/banlist快照、CDB、ocgcore、脚本/engine清单、CLI和worker都能按记录重新核对。

报告投影仍明确标记report_origin_authenticated=false。当前HTTP结果合同只验证持久报告结构、冻结输入绑定和哈希，不认证报告生产者。当前搜索源码在adapter.run之前递增engine_calls；ProcessEngineAdapter正常路径随后尝试创建worker进程，但既有执行记录没有OS进程审计或逐次FFI函数回执。没有ResearchBatch账本，本次真实消费未知。

源码记录的HEAD 672e5a823fcad60e9413d79cac810b68a2bb003c是当前审计HEAD的祖先，但package manifest所记5个未跟踪构建输入有3个原字节既不在当前工作树，也未在本地Git历史找到；tracked Cargo/crates diff摘要无法由现存提交复算。不得从当前源码补造原运行源码包，也不据此推翻已验收的单次有限分析。

## 当前源码路径复核（2026-11-04）

- `crates/ygo-search/src/combo.rs`在`EngineAdapter::run`前递增`SearchStats.engine_calls`。它表示适配器调用尝试，不表示worker进程创建、协议往返、FFI调用或研究消费。
- `crates/ygo-engine-adapter/src/process.rs`先序列化请求，再调用`Command::spawn`创建一个worker；之后分别写stdin请求行、读取stdout/stderr、等待退出并解析单份`DuelResult`。spawn失败、写入失败、进程退出、超时、输出解析和版本不匹配目前收敛为`WorkerError`类别；当前代码没有把`child.id()`或逐阶段字节摘要写入持久回执。
- `crates/ygo-engine-adapter/src/worker.rs::run_worker`仅读取一条最多16 MiB的JSON行，执行请求后输出一份JSON结果及换行并flush。该协议边界可从宿主实际序列化/读回字节计算摘要；worker目前不产出带attempt ID的独立receipt。
- `crates/ygo-engine-adapter/src/ffi.rs::Api::load`加载版本、create/destroy、new-card、start/process、message/response、load-script、query/query-count/field等ocgcore函数指针；实际调用分布在`worker.rs`，`Guard::drop`负责destroy。卡片读取、脚本读取、日志及完成回调是反向进入Rust的另一类边界，必须与Rust主动调用ocgcore分别计数。
- `crates/ygo-cli/src/workbench_analysis/persistence.rs`对待写报告算SHA-256、落盘后回读并复核摘要及结构；`http_contract.rs`仍明确输出`report_origin_authenticated=false`。该路径证明文件持久性和job/input绑定检查，不给producer来源背书。当前W1-C没有ResearchBatch消费账本。

这些是当前源文件的调用点审查，不是进程或FFI实测；本批未启动这些路径。

## 目标和边界

为下一次固定场景运行建立可重建、可离线验证的证据链，分别记录构建来源、adapter尝试、worker进程、worker协议往返、FFI入口调用、报告持久化和明确定义的消费单位。所有计数使用独立字段和身份，不从engine_calls推导其他层计数。观察不完整、回执丢失、崩溃或存储结果不确定时写unknown，不写0，不自动重试。

报告合同应区分“结构及冻结输入绑定有效”和“来源链经验证”。只有完整证据链通过验证时，版本化证据合同才能给出来源已验证；旧HTTP字段保持false，直到新合同和兼容策略经过审查及测试。来源链证明本地执行记录的一致性，不宣称硬件级远程证明或卡片语义正确。

研究消费与技术调用分开定义。先确认是否采用每次FFI入口、每个worker请求或其他单位作为记账单位，并说明失败、超时、未知和重开如何结算；没有明确定义的账本时，消费字段保持null/unknown。W1-C记录不替代R1b-3真实恢复、独立重放或可比ResearchBatch资格。

## 分批实施

1. **冻结来源清单与绑定候选构建。** 来源字节包v1已离线保存HEAD工作树中跟踪/非忽略未跟踪文件的字节，并逐路径绑定SHA-256及删除路径；版本合同见`schemas/workspace-source-bundle.schema.json`。2026-11-04又完成窄范围的来源绑定构建记录v1：新包绑定Cargo命令、`dev` profile、Python/Rust工具链、CLI/worker产物哈希，以及固定Rabbit输入、配置、快照、CDB、core与asset manifest的9项role/hash；离线来源包验证、CLI/worker构建、实际记录Schema和产物/资产复核均通过。证据见[部署工具合同](../../DEPLOYMENT.md)及[测试记录](../../TESTING.md)。这仍是`observed_command_only`且`reproducible_build_proven=false`；来源字节包本身不保存Git index、文件模式、ACL或精确patch；配套workspace-state-bundle v1现补充原始index、stage/unstage二进制patch、porcelain v2、index entries和来源文件模式，并绑定来源包身份。该状态包不记录ACL或时间戳，构建记录的role/path映射仍由验证者再次提供。
2. **定义执行回执。** 每次adapter尝试分配attempt id，并绑定operation/job、冻结输入、命令摘要、请求字节摘要、CLI/worker/engine资产。单独记录worker启动是否成功、OS PID与可执行文件身份、协议请求/响应摘要、退出码和时间。spawn失败也要有明确失败记录。
3. **定义FFI事件。** 在所有相关FFI入口记录attempt id、入口序号、调用种类、进入状态和可观察返回状态；区分“已尝试”“已进入”“已返回”和“结果未知”。先盘点实际调用点，再确定计数覆盖范围；不得把一条worker请求固定等同于一次FFI调用。
4. **绑定报告和账本。** 报告应绑定唯一执行attempt集合、冻结输入摘要、回执链末端摘要和精确报告字节哈希。确定消费单位和账本提交顺序；若无法验证完整收费记录，消费保持unknown。报告来源状态由离线验证器计算，不由producer自报。
5. **先做合成验收。** 覆盖spawn失败、worker在请求前/请求后崩溃、超时、FFI中断、响应丢失、重复或缺失回执、摘要/身份篡改、报告与job错绑、账本写前/写后不确定、重开和重复读取。要求失败关闭、无自动重试、第二次重开稳定，且各计数层能独立判定。
6. **形成新scope草案。** 使用可重建的新源码候选、固定Rabbit请求与资产、最多一个operation/job、既定预算及240秒外层停止界限。scope列出允许启动的服务/worker/FFI进程、所有输出目录、过程回执和停止条件。评审通过后仍需单独决定是否执行；本计划不创建scope、不运行分析。

## 下一批合成回执合同

状态：多attempt合成回执已实现并通过聚焦验收；ProcessEngineAdapter host观察现已接入opt-in搜索调用收集。job绑定的持久回执、worker FFI、报告producer及HTTP兼容策略仍开放。

- 采用同一operation/job下可链接的分层事件：host观察到的adapter尝试、spawn成功/失败与PID/worker哈希、实际写入的协议请求和读回响应字节摘要、worker报告的逐FFI边界事件、host复核的报告落盘字节。每项携带递增序号、attempt ID、前驱摘要和规范化事件摘要。
- 分开保存Rust主动进入ocgcore的调用与ocgcore回调进入Rust的事件；每个FFI调用需有`entered`和可观察的`returned`记录。只有`entered`没有`returned`时保留该入口尝试，并把返回状态标成unknown。receipt写入本身失败时，在下一次FFI调用前停止；已经进入调用但未能持久化返回事件时不得重试。
- 报告receipt引用job/input绑定、已验证receipt链末端、精确报告字节SHA-256及持久化后回读结果。离线校验器重新计算来源状态；producer字段不能自行将`report_origin_authenticated`置true。纯hash链只说明记录内部一致，不能宣称硬件级远程证明。
- 消费子对象暂保留`status=unknown`、`unit=null`、`count=null`。只有确定ResearchBatch实际收费单位并独立验证完整收费记录后才能填写；adapter、worker、协议和FFI计数都不能推导消费。
- 合成矩阵至少覆盖spawn失败、请求前/请求后进程退出、超时、协议缺失/重复、FFI entered后无returned、事件重复/篡改/错绑、报告hash错误、存储提交不确定、重开稳定及unknown消费。所有样本使用假adapter/假worker事件，不加载ocgcore或启动真实分析。
- 该合同先以版本化schema、离线验证器和测试夹具实现；通过后再决定生产观察点和兼容策略。默认服务行为、现有HTTP schema与真实执行范围不随合成测试自动改变。

实现落点为`schemas/w1c-execution-receipt-chain-v1.schema.json`、`python/ygo_eval/execution_receipts.py`及`tests/fixtures/w1c-execution-receipt-v1.json`/`w1c-execution-report-v1.json`。同一job可以顺序记录多个adapter attempt；每次attempt使用唯一ID，且只有前一worker请求已写入并收到完整响应后，才可开始下一次调用。transport结果缺失或未决后不得继续attempt。每个FFI序号在各自attempt内连续，调用ID在job内唯一；job级`report_persisted`事件关联最后一次attempt。replay调用失败后仍可能提交部分搜索报告，合同允许记录其精确字节，但总体状态保持`incomplete`且`report_origin_authenticated=false`。所有事件使用连续序号、attempt ID、前驱哈希和规范化事件哈希；消费保持unknown/null。既有schema整数语义与Python精确整数检查不一致的问题仍由有限且数学上为整数的JSON数字兼容处理。新增多attempt、未决后拒绝继续和失败replay后报告记录三项行为回归后，回执聚焦测试为17项；完整验证见[TESTING](../../TESTING.md)。该合同只检查记录内部一致性，不认证OS进程、producer或硬件执行。

## 退出条件

- 源码与构建输入可从归档字节完整重建，候选产物和固定资产哈希可独立复核。
- adapter尝试、worker创建、协议完成、FFI调用和研究消费使用不同计数，并有定义明确的失效语义。
- 每个报告都能离线验证输入绑定、执行回执链和报告字节；任一必要证据缺失时来源状态为unknown/false。
- 合成故障矩阵覆盖关键缺失、重复、损坏、超时和重开路径；不启动生产引擎。
- 新真实运行scope独立列出预算、身份、数据保留和退出条件；没有scope时不执行。

P4-R5部署、R1b-3恢复/replay、L1数据权利、全卡覆盖及全局最优证明继续分别管理。本计划通过不代表这些资格通过。

## 2026-11-04实施边界

来源字节包、观察式构建绑定、workspace-state-bundle v1及合成回执schema/离线验证器均已实现；状态包聚焦回归通过4项，回执合同原始聚焦回归14项。本次校正后回执聚焦测试17项通过；完整Python套件结果见[TESTING](../../TESTING.md)。生产worker/FFI观察、报告来源认证、消费口径及新scope仍开放；新真实运行须另立scope。

## 2026-11-04 单job多adapter调用合同复核

当前`combo::search`在初始探索、节点扩展和top-k replay中会多次调用`EngineAdapter::run`；已验收Rabbit分析记录为165次应用层`engine_calls`。原合成schema允许多个事件attempt ID，但Python验证器只接受一个attempt，无法表示实际搜索调用序列。现修正为每个job容纳多个顺序attempt；唯一ID不能复用，只有前一adapter请求已写入且收到完整协议响应后才允许下一次调用。spawn、请求或响应不完整时，后续attempt会被拒绝。

replay阶段出现worker传输失败时，当前搜索代码会记diagnostic并返回已完成线路组成的部分report。因此验证器允许在missing/invalid响应之后记录终态报告落盘；即使报告字节与输入绑定正确，整个执行receipt仍为`incomplete`且不认证报告来源。新增三项行为回归先观察到对应红测后通过；生产观察、持久回执写入、worker/FFI计量与ResearchBatch消费仍未接入或认证。

## 2026-11-04 ProcessEngineAdapter host观察

`ProcessEngineAdapter::run_observed`使用同一进程调用路径并返回单次调用的内存观察：spawn结果、PID、spawn前从配置路径读取的worker文件SHA-256、实际完整写入stdin的请求字节摘要/长度、读至EOF的stdout字节摘要/长度、JSON/协议/运行版本校验结果、退出/超时状态、退出码和耗时。请求写操作失败时不把预期请求摘要记成已写入；spawn失败时request/response均保持`not_attempted`。超时后stdout被排空的`complete`仅表示host完成pipe读取，终止字段仍为`timed_out`。

该观察不持久化、不分配job或attempt ID、不认证OS实际映像，不证明worker读入请求，也不包含worker FFI、报告落盘或消费。常规`EngineAdapter::run`仍返回原始`Result`，不计算worker文件与请求哈希；`combo::search`还未连接此观察接口。因此它是生产适配器能力上的host观察点回归，不是W1-C端到端来源认证。

在`tests/process_failures.rs`中扩展假worker覆盖成功响应、spawn失败、非零退出、超时、无效JSON和协议版本不匹配。聚焦`process_failures`：**8 passed、0 failed**；先以缺失`run_observed`方法得到预期编译红测。随后隔离的workspace串行回归共**92个结果组，483 passed、0 failed、36 ignored**；36项是默认关闭的本机资产、原生执行或人工准备opt-in。`cargo fmt --all -- --check`与workspace全目标Clippy通过。日志及SHA-256见[TESTING](../../TESTING.md)。

搜索调用attempt收集、job绑定持久attempt日志和合成FFI事件均已实施。后者覆盖嵌套entered/returned LIFO配对、job级唯一call ID、连续序号、HostResult前未返回拒绝、孤立entered重开unknown、FFI事件写前失败、磁盘历史重复call ID负例及字节稳定。外层先返回与磁盘历史重复ID回归均先RED后GREEN；Python执行回执验证器的嵌套LIFO回归也先RED后GREEN。下一批应设计worker transport如何向host确认通道提交这些事件，再分别为报告producer来源和ResearchBatch消费单位建立可审阅合同。此次未运行doctor、生产worker、ocgcore/FFI或真实分析，也未创建scope、部署或构建发布产物。

## 2026-11-04 搜索调用attempt收集

新增`ProcessObservedAdapter` opt-in扩展，不改变原`EngineAdapter` trait或默认`combo::search`路径。`search_with_observations`将搜索执行阶段标记为initial、baseline、exploration和replay；调用adapter前生成并校验唯一32位小写hex ID，返回后按顺序记录DuelStatus/WorkerError及`ProcessRunObservation`。ID生成失败、格式不符或同一次搜索中复用ID都会在后续adapter调用前失败关闭。观察式workbench executor使用16随机字节生成attempt ID，并将结果与report一起交给内部dispatch边界。

合成测试证明探索adapter错误后后续replay仍被单独记录、顺序与阶段一致；重复ID阻止第二次adapter调用。搜索聚焦8 passed，包含ygo-cli在内的workspace串行回归485 passed、36 ignored；全目标Clippy及格式检查通过，具体命令、忽略原因和日志hash见[TESTING](../../TESTING.md)。

历史说明：在持久attempt日志接入前，观察只在内存中保留到report发布或unknown结算；成功报告仍按既有合同序列化，attempt数组不会进入HTTP或持久report。该段保留用于说明前一批边界；当前状态和证据以本页“job绑定的持久attempt日志”及[TESTING](../../TESTING.md)为准。

## 2026-11-04 job绑定的持久attempt日志

新增`jobs/<job_id>/attempt_receipts/<sequence>.json`私有追加链。固定上下文包含operation/job ID、running修订、command摘要、job input binding、input摘要和冻结资产摘要；由于当前workbench不掌握来源包或构建记录身份，`source_bundle_identity`与`build_record_identity`显式为null。每次adapter调用前先追加`Started`，只有存储层确认发布并复读事件后，搜索才会进入adapter；adapter返回后再追加带host result与`ProcessRunObservation`的事件。事件含序列号、前驱摘要及上下文/事件摘要，跨链重开验证accepted operation和历史running修订。

持久化失败与写后提交不确定都会停止协调器派发。四种合成故障分别覆盖attempt-start写前失败、attempt-start已落盘但调用前提交不确定、host-result写前失败、host-result已落盘但调用后提交不确定；adapter调用数与剩余receipt事件数逐项核对。子进程握手点位于真实搜索attempt-start已落盘、fake adapter入口之前；父进程校验完整原子标记、operation/job/input与receipt哈希后才终止。带真实目录锁的恢复仅追加一次unknown，不生成报告、不保留claimable work，第二次重开逐字节稳定。聚焦search 5 passed、CLI FFI/回执7 passed、Python receipt验证18 passed、Python schema 12 passed/2 opt-in skipped；workspace串行回归92个结果组、494 passed、0 failed、36 ignored，全目标Clippy与Rust格式通过。workspace唯一额外过滤项为doctor诊断测试，完整命令和日志SHA-256见[验证记录](../../TESTING.md)。

该日志不是完整执行回执：它记录host侧尝试、进程/pipe观察及合成FFI事件，不认证OS worker映像、worker是否消费请求、真实ocgcore入口/返回、报告生产者或研究消费。attempt列表不进入现有报告或HTTP schema，unknown不映射为零消费。FFI合成矩阵已覆盖LIFO配对、跨attempt重复call ID、未返回入口、HostResult误关闭和FFI事件写前失败；生产worker仍没有逐FFI宿主确认通道。单次Rabbit分析scope没有重跑，W1-C来源/计量、R1b-3、P4和全局最优门禁各自保持原状态。
