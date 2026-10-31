# W1-B3 任务持久化、报告保存与队列协调设计

历史交付记录（H2.1）：新增内部操作合同及持久幂等提交；操作感知入口`DurableAnalysisCoordinator::open_operations`先认证跨链再分类；`allocate_operation/submit_operation`使用服务预分配ID、锁外真实W1-A冻结和等待槽预占。重复指令复用保存结果，任务与accepted提交后才注册派发。`inspect_operation/inspect_job`供同锁所有者只读查询；旧无操作根接口保留，旧入口拒绝含操作根。H2.2随后接入HTTP与结果投影；普通启动未配置分析后端，真实分析未交付。验收与限制见[H2.1交接](superpowers/plans/2026-10-31-w1h21-analysis-operation-handoff.md)及[当前HTTP合同](WORKBENCH_ANALYSIS_HTTP.md)。

[W1-H1 HTTP设计](WORKBENCH_ANALYSIS_HTTP.md)定义了操作修订链与任务链的提交顺序、容量预占、只读历史查询和回复丢失处理。H2.1已实现内部预分配ID提交、同锁只读查询及跨链认证；H2.2仍需接入严格HTTP和公开DTO。原B3任务合同不变；不能把内部存储能力表述为HTTP已交付或真实分析。

日期：2026-10-31；基础实现提交：main / 8091362。任务revision格式、严格链校验、重启分类、严格报告合同/冻结输入绑定/私有落盘/摘要重读和持久先行协调器已实现。claim在返回票据前重新采集worker、DLL、CDB、脚本和引擎manifest身份；不匹配时提交failed/asset_mismatch，不调用执行器。若该终态或报告发布后的终态提交失败/不确定，协调器停止，重开时按持久状态归类。内部合成故障矩阵及冻结资产角色/路径漂移覆盖已实现；不覆盖逐syscall强杀、断电/介质故障，不连接HTTP或真实执行器。报告来源/真实执行仍未认证。已有记录合同见[任务合同](WORKBENCH_ANALYSIS_JOBS.md)，队列现状见[W1-B2交接](superpowers/plans/2026-10-31-w1b2-analysis-queue-handoff.md)。

## 1. 存储合同和提交点

当前实现采用不可变JSON修订；保留AnalysisJobRecordV1及其revision 1/2/3状态图。存储封装schema_version=1、kind=workbench_analysis_job_revision；字段为job_id、revision、previous_sha256、record_sha256、record。record是现有无路径记录，ID/revision须与封装相等；首修订previous_sha256为null，后继指向前一封装文件的原始字节SHA-256。

严格读取必须从原始字节递归覆盖整个封装与嵌套record，拒绝重复键、未知/缺失字段和错误数字类型；不得先用宽松Value解析丢掉重复键。

record_sha256固定为现有record.encode_json()字节的SHA-256；验证时先用正式严格读取器验证record，再重编码比较。每条后继必须由前条经现有transition产生，输入、创建时间及job_id不变；不能只检查revision连续。摘要检查完整性，不认证可信来源，不能抵抗拥有目录写权限者整体重写历史。

实际布局（相对服务配置的独立任务根）：

```text
.ygo-analysis.lock
jobs/<job_id>/revisions/1.json  # 后继为2.json、3.json
reports/<report_id>.json
```

job/report ID均为服务生成的32位小写十六进制；不接受浏览器路径。没有可变HEAD文件：读取连续完整链，而非取文件名数值最大者。任务根规范化后拒绝任何祖先或子成员的链接/Windows reparse point；仅接受普通文件、预定目录和专用临时文件。目录锁采用平台独占锁；第二写者拒绝，锁文件存在本身不表示锁仍被占用。锁不防御恶意本机管理员，设计不作该承诺。

冻结运行对象、ProcessEngineConfig、RunDuelRequest和完整catalog不进入任务封装。报告是独立服务私有材料，可包含既有AnalysisReport的运行路径；报告路径和正文不得直接作为公开任务JSON返回。任务存储读取只验证保存身份，不扫描实时引擎资产。

写入步骤：同目录随机临时名create_new → 写完整UTF-8 → sync_all → 关闭 → 独占发布最终名 → 重读并校验字节及合同 → 返回提交回执。最终名的出现是逻辑提交点，写后检查失败视为提交不确定，不能当成未提交再试。

最终文件不得替换或先删后写。优先使用现有独占hard_link发布原语，发布后移除临时名；不支持安全发布的文件系统返回错误，不退回可能覆盖目标的rename。目标已存在且字节相同只可作为同一操作的已提交确认，字节不同为冲突。有效孤立临时文件不参与状态选择，保留供诊断；不自动清理历史材料。

当前实现先同步临时文件，再以硬链接独占发布；Unix还同步父目录，Windows使用已验证的存储发布/文件同步原语，但没有目录项刷新保证。发布后会重读完整链；Unix目录刷新失败或重读失败返回提交不确定。当前Windows测试只证明drop/reopen可恢复，不承诺断电、介质故障或远程文件系统持久性。

## 2. 内部存储与队列协调

记录存储能力：`PersistentAnalysisJobStore::open/append_initial/append_expected/history`已实现；全程持有操作系统排他锁，append_expected以预期revision校验前驱状态并追加不可变revision，提交成功后复读完整链。`persist_report/read_verified_report`严格拒绝重复键、未知/缺失字段及不匹配的冻结请求、运行请求、评分或预算；保存私有报告原始字节并在引用中绑定SHA-256，重读时重新校验。重开扫描会把终态记录引用与磁盘文件、摘要和保存输入重新核对。`DurableAnalysisCoordinator`已实现持久先行的submit/claim/cancel/fail/report发布入口；claim先持久化running，再核验资产身份，仅匹配时返回票据；失败状态持久化后不派发。一般事务先持久化候选revision，再更新内存队列；CommitUncertain会停用协调器。合成测试不认证报告来源或真实执行。

旧queue.enqueue/claim_next/cancel/settle保留B2内存语义；`DurableAnalysisCoordinator`通过同一队列状态/绑定核心的私有提交钩子执行持久先行事务，不在锁外拼装第二套状态转换。

存储钩子为私有实现，不允许用户回调重入队列；锁顺序固定为任务根独占锁（进程生命周期）→ 协调互斥锁 → 存储操作锁。磁盘提交可能短时阻塞状态查询，首版接受此成本；实际搜索、报告解析和昂贵计算在队列锁外。领取已提交后、构造适配器或实际调用前必须重新核对实时资产与冻结身份；不得用新扫描结果改写期望。资产复核失败且可认证尚未启动时提交failed，不调用适配器；无法认证是否启动时保留unknown。最终发布前在协调锁内再次核对票据、revision及摘要。

| 操作 | 必须先提交 | 然后允许 |
|---|---|---|
| submit | queued revision 1 | 注册排队槽、返回任务创建成功 |
| claim | running revision 2，再核验冻结worker/DLL/CDB/script/manifest哈希 | 全部匹配才移交派发票据；不匹配则追加failed/asset_mismatch，不调用执行器 |
| cancel | cancelled revision 2 | 移除等待任务、确认取消 |
| publish_result | 已认证报告及completed/budget_limited revision 3 | 释放运行槽、确认完成 |
| fail/uncertain | 合格failed/unknown修订 | 释放运行槽；不自动重发 |

一运行一排队及首任务占唯一等待槽保持不变；取消/领取由同一锁决定胜负。提交前失败保留原状态；任何写后不确定均使整个协调器进入停派发模式，不能继续领取、取消或发布。持久提交与内存应用之间若进程终止，重开时按已提交记录分类。只读诊断可用，须关停并重新认证存储后才能恢复服务。调用已开始时不能声称立即停止或零调用。

丢失回复不能触发新任务自动创建：后续请求协议必须使用创建前分配的服务操作标识查询同一提交结果。内部实现保留候选job_id及提交回执；同一ID及相同字节确认幂等，冲突拒绝。未来HTTP幂等协议须在HTTP实施批次定义，本批不假设浏览器已有该能力。

## 3. 报告认证和发布

已存在的ygo_api::combo::validate_report_contract验证报告内部请求、预算、逐线路结果和评价关系，但不认证来源、文件发布或真实引擎运行；read_report当前不是严格重复键读取器，不能原样用作新存储门禁。

持久协调器的报告发布路径已增加严格重复键/字段/数字读取，并依次核对：报告规范化请求与冻结请求逐字段一致；runtime的牌组、起手、seed、协议和版本身份一致；运行配置只与本次派发的内部冻结配置比较，不允许报告选择资产路径；search.scoring与冻结评分一致；budget一致；终止原因只接受B1四类及零线路后缀规则；线路数不超过top_k。复用原校验器检查线路，不从反序列化报告生成任何运行时凭证。`ygo_api::combo::read_report`仍不是严格重复键入口；新存储只通过专用strict_report读取路径处理报告。

发布顺序固定：锁外校验报告并准备字节 → 协调锁内重核运行票据 → 独占保存报告并同步 → 重读报告和哈希 → 构造ReportPublished并验证终态 → 提交终态修订 → 更新内存。报告引用SHA-256绑定保存的原始字节，不是解析对象摘要。

报告保存成功而终态未提交时形成孤立报告，保留但不展示为已完成；终态若存在则必须有可验证的报告。completed不等于找到解，空线路保留:no_verified_lines；budget_limited展示有限搜索原因，不授予完整性或全局最优。

合成测试材料使用独立测试根，并在测试证据中显式标为synthetic；不把来源标记写入旧AnalysisReport合同，也不因replay_verified布尔值授予真实资格。未来公开结果须使用独立白名单DTO，排除runtime.engine路径、原始错误和未经核验的正文；本批只定义边界，不实现投影或界面。

## 4. 启动分类和失败矩阵

任一任务链、报告引用或预定目录布局无法认证时，整个任务根进入只读诊断模式，禁止创建、取消、分类写入和派发；不能忽略坏任务继续接受新任务。

持锁扫描全部修订，严格验证封装、链、合法转换和报告引用；不得用缺失文件推定未执行。queued通过ClassifyRestart追加interrupted；running通过ClassifyRestart追加unknown。重启不重建可执行冻结对象、不重新入队、不启动旧程序；草稿或默认快照改变不重写保存身份。时间倒退使分类拒绝并保留原状态，不能静默校时。

已有可认证终态只读保留。分类提交中断后下次仍按提交点判断，重复重启不会重复推进终态。running旁的孤立报告不能代替缺失终态。链/报告损坏时保存独立存储诊断，原件不移动、不修复、不伪造v1任务终态；无法认证的统计保持未知。

| 走查边界（非运行验收） | 持久/内存预期 | 后继与稳定诊断 |
|---|---|---|
| 容量已满、旧revision、取消/领取竞争失败 | 两者不变 | 拒绝；复用B1/B2错误码 |
| 临时写入/同步失败，最终名不存在 | 旧修订/旧状态 | 停止本操作；job_store_write_failed |
| 发布后复读或刷新失败 | 新修订可能存在/内存未确认 | 停派发；job_store_commit_uncertain |
| 提交成功后、内存应用前进程终止 | 新修订存在/内存状态消失 | 重开按已提交状态分类；queued→interrupted、running→unknown |
| 提交完成、回复丢失 | 同一提交已存在 | 查询同一ID，不重发；job_commit_already_present |
| 同revision字节冲突/错误前驱 | 原件保留/不推进 | 停派发；job_store_revision_conflict |
| 执行前资产漂移且可认证未启动 | running转failed/不调用适配器 | 不改冻结期望；job_execution_asset_mismatch |
| 资产漂移后failed修订发布前确定失败 | running修订可能已提交/无派发票据，协调器停止 | 重开时running转unknown；不得在本进程重试领取 |
| 报告请求/评分/身份不匹配 | running保留/不结算 | 拒绝；job_report_binding_mismatch |
| 报告写入失败 | 无终态/运行槽保留 | 停止发布；job_report_write_failed |
| 报告已存、终态缺失 | 孤立报告/running | 重启unknown，不续跑；completion_uncertain |
| 完成引用缺失/报告损坏 | 原件保留/不加载为完成 | 独立诊断；job_report_integrity_failed |
| 有效queued重启 | 新interrupted/不入队 | service_restarted |
| 有效running重启 | 新unknown/不入队 | completion_uncertain |
| 已有有效终态再次重启 | 两者只读 | 不追加、不重发 |
| 重复键、链断裂、非法转换 | 材料保留/不构造可信状态 | job_store_chain_invalid |
| 目录锁占用、链接或越界 | 不写任务/无派发 | job_store_locked/job_store_path_invalid |
| 时钟倒退 | 原状态保留 | job_time_invalid |

独立诊断含逻辑角色、阶段、稳定码和必要哈希；原始异常仅留服务私有诊断目录，不把本机路径直接返回。未知状态不退款、不推定零执行或零消费。

## 5. 实施映射和后续关口

| 事实源 | 已有可复用 | 当前状态 |
|---|---|---|
| workbench_analysis::freeze_analysis_input | 同锁草稿revision及输入绑定 | 持久协调器claim复核冻结资产哈希；各冻结角色及脚本路径漂移已有合成覆盖 |
| workbench_analysis::jobs | 严格合同、转换和报告引用 | 存储封装schema及修订链认证 |
| workbench_analysis::queue | 容量、票据及绑定规则 | 持久提交及冻结资产复核已接入；内部提交边界、重开和漂移合成矩阵已覆盖 |
| ygo_api::combo | validate_report_contract | 严格读取、冻结绑定、报告先保存后提交终态已接入 |
| ygo-storage deck_drafts | 随机ID、独占发布及平台锁思路 | 抽取通用安全发布/锁；不套用草稿替换分支 |

队列锁内的持久提交后状态应用由受互斥锁保护的赋值/移除操作完成，没有可返回错误分支可供注入；进程panic或资源耗尽属于进程终止场景，不能以虚构的可恢复错误测试代替。当前矩阵验证操作前提交失败、提交后不确定、重开分类及操作系统子进程强杀（发生在已提交revision之后）。未认证文件系统每条syscall间强杀、断电/介质故障、网络文件系统或真实执行。HTTP创建幂等标识、预算截断和公开DTO属于后续接口/执行器批次；旧W1-A/B1/B2回归必须保留。

任务/报告存储和持久协调器定向合成测试共23项通过。覆盖revision链/重启分类/陈旧写入/锁/损坏链、报告绑定/保存重读/篡改拒绝/重复键/评分漂移拒绝/孤立报告，以及submit/claim/cancel/fail/report文件与终态发布的提交前失败、提交后不确定、重试、停派发和重开分类；并覆盖重复终态请求、冻结资产各角色/路径漂移及已提交revision后的子进程强杀恢复。文件系统逐syscall中断、断电/介质故障、HTTP、真实引擎和报告来源仍未认证。W1-C真实本机分析须独立验收。认证消费40、预留7、规划47保持不变，全部历史实际累计未知。
# H2.2 读取与提交扩展（2026-11-01）

持久协调器新增接受/完成两阶段及一次性冻结票据，原同步接口共用核心。历史报告读取复用启动时的纯字节/引用/请求绑定校验，不依赖运行时冻结对象或实时资产。HTTP状态读取使用同一锁所有者，不调用会写分类的open。见[H2.2交接](superpowers/plans/2026-11-01-w1h22-analysis-http-handoff.md)。
