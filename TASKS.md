# 实施任务与验收状态

当前实施路线：[2026-11-09项目现状评估与双轨路线](docs/superpowers/plans/2026-11-09-project-status-and-dual-track-route.md)。本文件后续表格是当前任务与开放门禁的唯一清单；每次验证的范围和结果见[TESTING](docs/TESTING.md)。

## 当前状态（2026-11-12）：PR #18审计文档已合入；产品与执行资格仍开放

远端`main`当前为PR #18的合并提交`1698e4ab4b76e512fbcda4298a72e3c3e6ce7f58`（2026-11-11 16:57:08 UTC）。PR #17于2026-11-10 12:28:44 UTC合入，合并前head为`6dbae6ceb39f3fd7265cb0ead8ecf084960ae6e1`；其`contracts`工作流通过，但CodeRabbit最终检查因PR关闭而取消，GitHub无正式review记录。PR #18合入14份审计文档；其合并后`contracts` run `43062300211`发现两项Windows `deck_draft`测试的临时目录竞争，后续修复见[验证记录](docs/TESTING.md#2026-11-12-pr-18合并后临时目录竞争修复)。当前本地候选已加唯一目录分配和并发回归，聚焦测试通过；PR #19完整CI仍待验证。PR合并和测试记录不等于真实执行认证或部署验收。

只读GitHub API检查显示`main`分支保护返回404、仓库rulesets为空；PR #18 contracts失败后仍被合并。没有更改仓库设置。是否要求main强制通过`contracts`和PR审阅是待决的仓库治理事项；PR #19在全部检查成功前不自动合并。

PR #17的worker宿主确认流现已在main源码中；`dist/ygo-local`仍是2026-10-19旧包，当前源码未因此发布。W1-C来源与计量合同仍开放：部分结果/消费记录、report producer来源、ResearchBatch消费单位及unknown消费仍未解决。普通启动保持`analysis_not_configured`；不将合成测试或CI结果外推为真实worker、ocgcore/FFI执行、研究消费或部署资格。

2026-11-09在隔离worktree实施W1-C worker FFI宿主确认流；协议实现与合成worker矩阵通过，完整提交前验证及其资产过滤项见[本次验证记录](docs/TESTING.md#2026-11-09-w1-c-worker-ffi-宿主确认流)。此结果不认证真实worker/ocgcore/FFI、报告来源、消费或发布。更早HEAD默认离线自检仍见[记录](docs/TESTING.md#2026-11-09-head默认离线自检)。

发布前历史记录：2026-11-10 CodeRabbit对PR #17当时已发布head `c9455d577fc08c1e51663eed079f166d282ab61c`的远端Deep Review返回15项（7 major、8 minor）。逐项核对后，15项均已映射到隔离候选中的代码修正或合同/文档修正；workspace串行测试、Clippy、格式和相关schema回归已通过。候选级独立审阅与当时28提交范围/兼容性集成决定仍开放。该记录早于候选推送；审查结果不覆盖候选工作树。逐项处置和验证范围见[PR #17第七轮审阅记录](docs/superpowers/plans/2026-11-09-pr17-review.md)及[TESTING](docs/TESTING.md)。

发布前历史记录：2026-11-10 PR #17隔离候选移除attempt receipt总事件数硬上限：新写入按每段4096条分目录，兼容读取旧版最多20000条平铺历史；单事件256 KiB限制及完整历史内存校验保留。旧格式20,000条读取并追加到新分段的回归通过。CodeRabbit第六轮远端审阅针对原发布head返回12项（5 major、7 minor），候选11项已有对应修复，剩余固定W1-C启动示例已在`docs/WORKBENCH.md`改为隔离target构建与启动。CLI本地审阅仍因`No Git repository found`在开始前失败；该候选当时未提交，未有自动审阅结果。聚焦回归和审阅边界见[TESTING](docs/TESTING.md)。

2026-11-10文档同步前快照：PR #17 head为`887e3430cff88704e8b8e183a3df1b94dfbb6960`，GitHub Actions `contracts` run `42767483602`通过；PR当时为Open Draft。最终head的CodeRabbit check因Draft被跳过，GitHub reviews列表为空，因此尚无PR review。该快照的远端比较为30个提交、190个文件；后续分支提交会改变head和比较统计，完整范围/兼容性审阅仍开放。先前关于`c9455d5`、28提交和189文件的文字是更早的推送前快照。详见[PR审阅记录](docs/superpowers/plans/2026-11-09-pr17-review.md)。

历史验证记录（2026-11-09代码基线）：默认离线Rust/Python回归和格式/Clippy复核对应`8c7afe6`；随后`ec83bad`仅补记审计文档。默认测试结果不认证生产worker、ocgcore/FFI、报告来源、消费或部署。关于当时PR #17分支状态，见[项目路线历史快照](docs/superpowers/plans/2026-11-09-project-status-and-dual-track-route.md)；当前集成状态见本文件顶部。

较早记录（2026-11-10，推送修复前）：隔离PR候选修复attempt receipt 20,000事件硬上限，并逐项核验CodeRabbit远端审阅；远端第六轮针对原始head返回12项（5 major、7 minor），候选源码/文档对照发现1项启动示例仍用普通target，已在隔离候选补充W1-C隔离target构建与启动说明。远端`contracts`失败起因是准入测试依赖被`.gitignore`排除的snapshot，候选测试已改用自包含快照夹具；候选离线workspace串行测试92组、524 passed、39 ignored，仅过滤doctor诊断1项；workspace Clippy、fmt、diff及相关Python schema/receipt测试通过。远端失败检查未重跑；CLI本地复审仍返回`No Git repository found`。进一步诊断发现CodeRabbit 0.9.3的doctor报告Git不可用，但同一进程中PowerShell可执行Git 2.40.0；自更新确认该CLI已是最新，矛盾原因未明。远端审阅不覆盖当时未提交候选。后续推送及CI状态见本文件顶部更新和[PR #17审阅记录](docs/superpowers/plans/2026-11-09-pr17-review.md)。

较早记录（2026-11-10，推送修复前）：经本地代理安装用户级CodeRabbit CLI 0.9.3；Authenticode状态为Valid，签名主体为CodeRabbit Inc.，安装二进制SHA-256为`9853E9A9BE139D1782BE0AF244937B6C82418C9EEFCC7A88FB2EF5EC5C120F59`。安装后改用CLI绝对路径及显式`--dir`、`AGENTS.md`和base commit重试，并从候选仓库根目录直接运行不带`--dir`的命令，均立即失败于`No Git repository found`；候选和主工作树的`coderabbit doctor`都报告Git不可用，但PowerShell中的Git 2.40.0可正常识别仓库。GitHub只读复核当时确认PR #17仍为Open Draft，base/head分别为`577924bc0c2af06044b77c065eea769c465ff2fe`和`c9455d577fc08c1e51663eed079f166d282ab61c`。CLI问题在后续再次复现，PR head和CI后来更新，当前状态见本文件顶部。凭据有效；常见密钥模式扫描为0命中（不等于完整秘密审计）。

H3恢复的逻辑窗口、证据层级和未覆盖边界见[H3.1证据门禁映射](docs/superpowers/plans/2026-11-02-h3-evidence-gate-map.md)及[HISTORY_INDEX](docs/HISTORY_INDEX.md)。所有窗口验收均按具体提交点限定；它们不关闭其他调度、逐syscall、断电或介质故障门禁。

部署身份、隔离候选和本机资产权限见[DEPLOYMENT](docs/DEPLOYMENT.md)与[ENVIRONMENT_AUDIT](docs/ENVIRONMENT_AUDIT.md)。普通启动保持`analysis_not_configured`；局部测试或预算截断运行不表示完整搜索、全局最优或发布通过。


## 历史状态快照（2026-11-10）：PR #17尚未合并

下方任务表维护当前能力与开放门禁；具体验证证据统一见[TESTING](docs/TESTING.md)。截至该快照日期，本地main为`ec83bad`，较本地`origin/main`领先27个提交；PR #17仍为Draft且未合并。该段为历史状态，不代表当前分支。旧dist身份、未决ACL风险和安全扫描范围见[DEPLOYMENT](docs/DEPLOYMENT.md)与[SECURITY_AUDIT](docs/SECURITY_AUDIT.md)。

E1 只读诊断已完成：Tenki 归档的 `codec.rs` pin 为 `224…`；`e8…` 可认证到 Ground Collapse 工具包，但未认证为 Curry scope 的实际执行源码。当前 `6233…` 与 HEAD 内容按 CRLF→LF 规范化后相同。原失败和 pin 保留；后续 pin 处置需独立建立 Curry 来源链。详见[E1诊断](docs/superpowers/plans/2026-10-30-e1-tenki-codec-anchor-diagnostic.md)和[本轮记录](docs/TESTING.md#2026-10-30-e1-tenki历史保护锚点只读诊断)。

这是当前状态和开放任务的唯一入口。产品目标、研究定义及阶段依赖分别见[产品愿景](docs/PRODUCT_VISION.md)、[最优性研究](docs/OPTIMALITY_RESEARCH.md)和[路线图](docs/ROADMAP.md)；历史实施顺序由[HISTORY_INDEX](docs/HISTORY_INDEX.md)导航。下方各批历史数字仅适用于其日期和范围，不覆盖本节。

| 阶段 | 当前能力与未完成门禁 |
|---|---|
| P0 | 首批身份、构建记录、清点与输入工具已交付；全正式OCG发行分母及依赖证据未完成 |
| P1 | P1.1协议、观察、局部原生案例和证据工具已推进；受限观察边界合成实验及opcode24生产菜单映射核对已通过；固定Ground候选与当前本地资产已只读复核并完成真实opcode24实验设计。2026-11-03从私有归档按索引哈希恢复13份固定来源后，离线准备及verify-only通过；随后将阶段driver、runner和测试纳入19成员工具包并重建当前报告，来源稳定复核通过，报告`execution_ready=false`。另完成当前源码、隔离构建、冻结输入、最终stage 1请求和资产身份的离线候选清单评审；清单保持hold、未授权，不是runner可执行manifest。没有创建Ground scope或启动Ground runner/worker/FFI。真实提示、响应接受、完整动作、概率、循环和独立值界仍未认证 |
| P2 | 39卡字段存在性、来源绑定及缺口已离线登记；L1十三批完成39/39张zh-CN候选名称/效果人工对照，zh-SC前十三批38/38张有候选值记录完成人工对照；zh-SC没有剩余有值候选待审阅，卡号44088353在该源缺少字段，全部语言类别、别名映射及使用/再分发依据仍未通过；在38张有官方简中详情页可直接比较的卡中，29张候选标题不同、21张正文类别称谓映射未确认；2026-11-03单卡来源审计再次确认人偶之锤仅有可用官方日文详情页，MyCard上游权利依据仍未知；正式中文检索/更新服务未交付 |
| P3 | P3.1草稿CLI、B2本机工作台、只读C1字段状态接口及分析HTTP操作/任务接口已交付；分析接口需显式配置，普通启动仍未配置；固定Rabbit单次有限分析已执行一次，通用分析/构筑能力及分析任务网页界面未交付 |
| P4 | R1a首次失败诊断及R1b可恢复执行循环已实现；非空两动作、连续提示逐边界合成暂停/重开及中断/竞争门禁通过；R1b-3首轮只完成1次Execution调用，在event-49完整结果比较处暂停前中止；后续只读审计还发现旧固定见证重建漏掉对手牌组/手牌计数（旧manifest为0/0，冻结trace为39/1），离线修正已通过聚焦检查；该run未做Witness审计、暂停、恢复或独立重放，真实恢复与独立重放未认证，R2–R5门禁均未通过 |
| P5–P6 | 指定profile知识和有限关联已有；通用知识、主题识别、自动构筑与评估反馈未交付 |
| P7–P8 | 指定灰流丽场景有局部证据；通用干扰、全卡覆盖、最优性证明及可分发产品未交付 |

最近Ground Collapse opcode24批次完成离线协议、合成oracle、固定来源准备、真实提示实验设计及Ground专用收费驱动。Python协议/准备/阶段驱动测试为54 passed、19 subtests passed；Rust adapter库56项及runner示例2项合成测试通过；格式检查和workspace全目标Clippy通过。新增native/runner/worker/FFI调用均为0，没有创建scope。2026-11-03从私有归档逐项恢复13份哈希匹配的固定历史来源后，当前独立离线准备通过六项来源检查；verify-only复核138个文件输入及5个目录输入通过。历史Ground准备报告仍缺失，当前报告不替代旧报告及其37成员历史声明；会计值为认证消费子集40、政策预留7、规划47，旧实际消费与全部历史实际累计继续为`null`。`execution_ready`、原生可达、响应接受及完整性/概率/最优性资格均保持false。13/14既有各自冻结案例的局部原生分支与重放不延伸到Ground；24实际提示、掩码及响应接受仍未知，见[历史准备交接](docs/superpowers/plans/2026-10-27-ground-collapse-preparation-handoff.md)、[当前实验设计](docs/superpowers/plans/2026-11-03-ground-collapse-opcode24-experiment-design.md)和[测试记录](docs/TESTING.md)。

随后独立复核固定工具源码绑定：当前profile固定19个成员，含Rust阶段模块/runner、Python协调器及其合成测试；v1 schema保留正整数结构兼容，Python profile和ZIP成员校验严格绑定当前19个文件。最新报告位于`data/runtime/p1-ground-collapse-preparation-current-2026-11-03-driver-review-2/preparation.json`，SHA-256=`a238a2f114c7cb26b6f1e79d6ca34b3e5f01f33bdb57eab0b6d2f650c2bb8c99`；六项来源检查和CLI verify-only均通过。此前两份当前来源报告保留为历史快照；本报告不替代缺失的2026-10-27历史报告或归档恢复报告，scope仍未创建。

最新可认证会计口径为**认证消费子集40、政策预留7、规划47**；旧confirmation实际消费和全部历史实际累计仍为`null`。旧窗口和槽位依各自scope封存；新增原生实验必须另定范围、预算和窗口，不能直接执行既有准备报告。

2026-11-03 L1文档更新后对Ground准备报告重跑只读verify-only：`valid=true`，固定19个工具源码成员逐项复核无差异；当前完整源码身份另存于忽略文件`target/p1-ground-collapse-source-review-2026-11-03/source-identity.json`。准备报告仍`execution_ready=false`且新scope/预算/最终请求/worker绑定均为空，真实提示实验尚未准入。详情见[TESTING](docs/TESTING.md)。

2026-11-03随后完成Ground Collapse候选执行清单离线评审：隔离runner/worker构建成功，冻结案例、stage 1请求、19成员工具包、资产、完整脚本树和文档定稿后的完整工作区源码身份均记录在忽略机器清单中；独立只读审阅确认清单自摘要、源码/build前后身份、请求、资产及调用边界一致。准备报告和候选清单均保持未准入，最终原生请求、实际prompt ID、scope及授权为空。未执行Ground runner/worker/引擎/FFI。评审细节见[候选清单评审记录](docs/superpowers/plans/2026-11-03-ground-collapse-candidate-manifest-review.md)和[验证记录](docs/TESTING.md)。

本批A1首次失败诊断、B1牌组草稿基础及B2本机中文浏览器工作台已完成。B2只提供本机草稿编辑、YDK/JSON导入导出和可选本地卡表查询；不表示中文译文、牌组合法性或引擎行为已核验。说明见[工作台文档](docs/WORKBENCH.md)，交接见[B2交接](docs/superpowers/plans/2026-10-28-b2-workbench-handoff.md)，实跑范围见[TESTING](docs/TESTING.md)。

W1设计后的A阶段已交付：工作台所有API非GET请求在路由前均须通过本机Host、Bearer令牌和同源Origin门禁；Rust库新增内部`freeze_analysis_input`，在同一草稿存储锁内核对ID/revision并复制草稿，再通过现有`prepare`冻结搜索请求、已解析catalog/banlist及引擎资产身份。它不增加HTTP分析入口、队列或任务，也不运行适配器。见[W1-A交接](docs/superpowers/plans/2026-10-30-w1a-input-freeze-handoff.md)与[实测记录](docs/TESTING.md#2026-10-30-w1-a工作台同源保护与分析输入冻结)。

历史交付（W1-B1至B3）：完成无路径`AnalysisJobRecordV1`、严格JSON、纯状态核心、进程内合成队列、任务revision、报告私有存储、报告引用启动核验、持久协调器及内部合成故障矩阵。领取时先持久化running，再核对冻结期资产哈希；不匹配或提交结果不确定时停止协调器，重开时按已提交revision分类。H2.2随后接入任务HTTP及无路径DTO；H3.2各批再覆盖限定的认证、并发、响应丢失和进程终止场景。余下H3.2-2b窗口、报告来源、真实执行、逐syscall崩溃和断电/介质持久性仍未认证。最新验证见[TESTING](docs/TESTING.md)。

C1离线字段核验已完成：冻结39卡逐项记录zh-CN/zh-SC名称、正文、别名及字段状态和候选哈希；候选正文不进入报告或工作台接口。zh-SC继续为`und`，语义审阅、使用依据和再分发资格未通过。报告、统计与限制见[LANGUAGE_REVIEW](docs/LANGUAGE_REVIEW.md)、[DATA_SOURCES](docs/DATA_SOURCES.md)和[TESTING](docs/TESTING.md)。

A3及P4-R1b离线实现现包含planner单次调用检查点和可恢复语义循环。两动作合成路线覆盖多次连续提示、End Phase及逐次QueryWitness审计；连续执行与每个语义调用边界暂停/重开结果相等，收费前保存失败与只读检查后的账本竞争均拒绝继续。合成适配器测试没有生成正式凭证；真实进程暂停、操作系统级崩溃矩阵及独立重放仍未认证。状态转移及限制见[执行恢复合同](docs/EXECUTION_RECOVERY.md)、[A3交接](docs/superpowers/plans/2026-10-28-a3-execution-recovery-handoff.md)和[P4-R1b交接](docs/superpowers/plans/2026-10-28-p4-r1b-resumable-execution-loop-handoff.md)。

### 当前开放任务

- [ ] 仓库治理：决定是否为`main`配置必需的`contracts`状态检查和PR review门槛。当前无保护规则；本轮不擅自改变仓库策略。
- [x] W1-H3.1：跨链恢复与响应丢失设计已交付；仅静态审阅，不代表H3运行验收通过。
- [x] W1-H3.2-1：共享认证、完整候选清单、关联修复/分类及重复重开通过合成验收，具体范围见本批TESTING。
- [x] W1-H3.2-2a：真实TCP零字节丢失、正文截断、幂等查询及受控重开通过合成验收；workspace 442通过、36忽略，范围见本批交接。
- [x] W1-H3.2-2b-1：四个跨链提交窗口的子进程强杀、完整认证恢复、重复重开稳定和绑定冲突负例通过；workspace 444通过、36忽略，见本批交接和TESTING。
- [x] W1-H3.2-2b-2（accepting保存后、冻结前）：子进程在原子握手点终止；父进程认证完整操作修订链、命令摘要、前驱与记录哈希及状态迁移后确认freeze/claim均为0。恢复仅追加一次unknown，无任务、报告、冻结或可领取工作；再次重开字节和修订稳定。2026-11-02验收为workspace 445通过、36忽略；2026-11-04按当前HEAD复核聚焦用例1通过、workspace 480通过、36忽略；2026-11-10确认性复核为聚焦1通过、CLI 136通过、workspace 495通过/36忽略/1过滤、schema 16通过，格式及Clippy通过，详见[TESTING](docs/TESTING.md)。忽略项为默认关闭的冻结资产/原生研究/人工准备opt-in，逐项原因见[TESTING](docs/TESTING.md)。这是合成协调器窗口，不是原生引擎、系统故障或全矩阵认证。
- [x] W1-H3 allocated保存后、协调器响应返回前：限定合成子进程强杀后，两次重开材料字节稳定；显式再次分配生成新ID，不承诺找回客户端未收到的ID。该检查点不模拟独立HTTP响应传输强杀；详情见[TESTING](docs/TESTING.md#2026-11-02-allocated保存后协调器返回前限定合成验收)。
- [x] W1-H3补充K窗口（假执行器进入后、返回前）：合成进程强杀后真实目录锁重开只追加一次`unknown`；操作/报告/队列/领取及第二次重开稳定。见[交接](docs/superpowers/plans/2026-11-03-running-executor-crash-handoff.md)。
- [x] W1-H3补充K窗口（假执行器返回`Ok(report)`后、报告发布前）：父进程认证operation/job修订链、命令摘要和输入绑定后终止子进程；恢复仅追加job revision 3=`unknown`，无报告/队列/可领取工作，第二次重开稳定。聚焦1 passed，完整ygo-cli 121 passed，workspace默认串行测试退出码0；Python schema 24 passed、2 skipped。机器证据及范围见[交接](docs/superpowers/plans/2026-11-03-executor-return-crash-handoff.md)与[TESTING](docs/TESTING.md)。
- [x] W1-H3补充K窗口（running修订已持久化、内存队列已更新、领取票据尚未返回）：父进程认证operation/job链和冻结输入绑定后终止子进程；事件为`freeze → claim → queue_updated`，报告和假执行器调用均为0。恢复仅追加一次`unknown`，队列无活动或可领取任务，重复重开字节稳定。聚焦及workspace、Clippy、格式和相关schema回归通过，见[交接](docs/superpowers/plans/2026-11-03-running-queue-updated-before-ticket-return-handoff.md)与[TESTING](docs/TESTING.md)。
- [x] W1-H3补充K窗口（AssetMismatch已持久化、队列内存结算前）：子进程在冻结资产复核失败并保存failed/AssetMismatch revision后终止；父进程认证operation/job链与状态迁移，无报告且`claim_next`未返回。真实目录锁重开保留唯一failed终态、不追加unknown，队列无可领取任务，第二次重开七个revision文件字节稳定。聚焦测试1 passed；此点不覆盖HTTP派发准入拒绝路径或真实资产/引擎。见[交接](docs/superpowers/plans/2026-11-03-asset-mismatch-persisted-before-queue-update-handoff.md)与[TESTING](docs/TESTING.md)。
- [x] W1-H3补充K窗口（HTTP派发准入AssetMismatch已持久化、内存队列结算前）：子进程经真实`dispatch_pending`进入准入拒绝分支，在`failed/AssetMismatch`修订保存后、内存队列结算前握手并终止；父进程认证operation/job完整修订链、迁移、命令摘要及输入绑定。真实目录锁重开保留failed终态，不追加unknown、报告或执行器调用；队列无可领取工作，第二次重开材料字节稳定。聚焦1 passed；工作区默认串行测试（过滤doctor适配器诊断用例）退出码0，`ygo-cli` 101 passed；schema 8 passed、2 skipped。该合成窗口不认证真实执行或引擎。见[交接](docs/superpowers/plans/2026-11-03-dispatch-admission-asset-mismatch-crash-handoff.md)与[TESTING](docs/TESTING.md)。
- [ ] W1-H3.2-2b余项：其他逻辑窗口/调度仍开放；逐系统调用故障、断电和介质故障未认证，不自动授权真实分析。

- [x] D2：更新项目定位、双轨计划、研究经验与文档导航；交叉核对记录见[TESTING](docs/TESTING.md)顶部。
- [x] 2026-10-27环境自检：区分部署包与开发资产，清理229个已确认空测试目录和本轮隔离Cargo缓存，整理pytest缓存及冗余直接依赖；范围和验证见[TESTING](docs/TESTING.md)。
- [x] 本轮环境自检：Python 3.12干净快照、隔离部署文档复制、普通部署smoke与replay、离线验真及文档检查；覆盖、跳过项和后续保留边界见[工作区自检](docs/WORKSPACE_REVIEW.md)及[验证记录](docs/TESTING.md)。
- [x] 环境后续：历史证据保留清单与SHA-256清点已建立；2026-11-02按独立授权将清单内54个唯一文件中的51个非空文件归档到Google Drive私有目录并逐项回读验哈希，3个零字节文件留本机。其他历史证据和运行资产仍未迁移，哈希清单不代表备份。旧目录写入测试已改为target隔离仓库并验证不触碰原D盘证据；Windows目录符号链接实测仍受系统策略限制（对应用例跳过），最新源码双资产发布验收P4-R5仍开放；当前未授予任何研究scope。详情见[环境审计](docs/ENVIRONMENT_AUDIT.md)和[证据保留清单](docs/EVIDENCE_RETENTION.md)。
- [x] 2026-11-01配置清理：移除无消费者且与严格当前schema不兼容的忽略文件`configs/engine.toml.legacy`；记录原哈希并保留有效本机配置。证据见[环境审计](docs/ENVIRONMENT_AUDIT.md)。
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
- [x] W1-H3.2-1/2a限定门禁：跨链认证恢复、幂等重复、响应丢失、受控重开及停止后只读查询已按各自记录的范围验收；不自动重发，也不等同目标进程强杀。
- [x] W1-H3.2-2b-1四个指定提交窗口：子进程终止后的认证恢复、重复重开字节稳定和跨链绑定冲突负例通过；不包含真实工作服务。
- [x] W1-H3报告终态原因分类补充：在既有`budget_limited`保存后K检查点增加`time_budget`报告字节用例；它与`node_budget`共用同一物理提交点，不作为新的H3逻辑窗口。报告原因在持久化和重开后保持稳定，其他预算原因及报告来源仍开放。
- [x] W1-H3显式`mark_unknown`终态保存后、内存队列结算前K：子进程终止前认证operation/job完整链和`CompletionUncertain` revision 3；无报告，freeze/claim各一次且无执行器调用。真实目录锁重开两次保留原unknown修订，队列空、不可领取且材料字节稳定。聚焦1 passed、CLI 127 passed、workspace 480 passed/36 ignored；其他H3状态组合与系统故障仍开放，见[交接](docs/superpowers/plans/2026-11-04-unknown-terminal-persisted-before-queue-update.md)及[TESTING](docs/TESTING.md)。
- [x] W1-H3恢复操作unknown修订追加P/U/R：提交前失败、提交后不确定、写后复读失败后均由重开按提交点继续；只覆盖无任务accepting操作的revision 3合成故障注入，见[交接](docs/superpowers/plans/2026-11-02-unknown-operation-fault-handoff.md)。
- [ ] W1-H3.2-2b其余逻辑窗口/调度门禁；running报告临时文件同步后、正式发布前的单一K窗口已通过[限定合成强杀](docs/superpowers/plans/2026-11-03-report-temp-crash-window-map.md)，逐syscall故障、断电和介质故障继续单独开放。
- [x] W1-H3混合恢复顺序K：第一条无任务accepting操作按ID先修复为unknown，第二条带queued任务的accepting操作随后修复为accepted，再将任务分类为interrupted；单一合成子进程终止场景通过，见[映射](docs/superpowers/plans/2026-11-02-mixed-operation-recovery-map.md)、[交接](docs/superpowers/plans/2026-11-02-mixed-operation-recovery-handoff.md)和[TESTING](docs/TESTING.md)。其他操作/任务状态组合、排序、调度及H3窗口仍开放。
- [x] W1-C单次Rabbit本机有限分析：固定profile、隔离候选包及单次执行范围已按固定输入和停止条件验收；2026-11-03唯一operation `d9c94519880097bb0ef5213580f14e68` / job `70e9a8f132e88ff2334b269603363ab6`以`time_budget`得到`budget_limited`，报告Schema与受控重开稳定性通过。160 nodes、165 engine_calls、5条报告线路均标记engine_verified/replay_verified；该状态不代表独立原生重放、来源认证、完整搜索或全局最优。FFI调用及消费未独立计量，未知不等于0。2026-11-04只读审计确认运行产物与资产哈希清单相符，但历史构建输入未能完整重建；详见[TESTING](docs/TESTING.md)及[单次范围](docs/superpowers/plans/2026-11-03-w1c-single-rabbit-execution-scope.md)。普通启动仍`analysis_not_configured`；H3余项、R1b-3及P4发布门禁继续分别开放。
- [x] W1-C源码来源字节包v1：新增Schema、自摘要清单、确定性ZIP、原子目录发布及离线逐成员校验；源树范围限HEAD工作树的跟踪/非忽略文件字节。Python全套790 passed、9 skipped、219 subtests passed；真实当前树来源包存于忽略目录`target/w1c-provenance-20261104/source-bundle`。该工具不提供构建重现、资产归档或执行/报告/消费认证，见[部署合同](docs/DEPLOYMENT.md)与[验证记录](docs/TESTING.md)。
- [x] W1-C当前源码离线构建绑定v1：在新来源包上记录Cargo命令/profile与Python/Rust工具链，离线构建CLI和worker产物，并绑定固定Rabbit请求、牌组、配置、快照、CDB、core及两份资产manifest的9项哈希。隔离构建和记录校验通过，来源包/记录身份及产物哈希见[TESTING](docs/TESTING.md)；只证明观测到的构建输入和字节身份，`reproducible_build_proven=false`，不表示执行worker或认证分析。
- [ ] W1-C执行来源与计量合同：workspace-state-bundle、观察式构建记录、host attempt日志和合成FFI事件已交付main。worker宿主确认流随PR #17合入（合并提交`1197976`；合并前head `6dbae6c`）；该PR的`contracts` CI通过，但CodeRabbit最终检查因PR关闭而取消，GitHub无正式review，完整独立审阅仍开放。此任务仍未完成：部分结果/消费记录、report producer来源、ResearchBatch消费单位和unknown消费未解决。合成测试不认证生产worker、ocgcore/FFI执行、研究消费或部署。详见[PR审阅记录](docs/superpowers/plans/2026-11-09-pr17-review.md)和[TESTING](docs/TESTING.md)。
- [x] W1-H3补充K窗口：父进程认证operation/job revision链后，在子进程已持久化`running`并进入测试专用假执行器、尚未返回时终止进程。持真实目录锁重开后仅将job追加一次`unknown`；operation、报告、队列、领取与第二次重开均稳定。该合成窗口不认证真实执行器/引擎；其余调度和系统/介质故障继续开放。证据见[交接](docs/superpowers/plans/2026-11-03-running-executor-crash-handoff.md)及[TESTING](docs/TESTING.md)。
- [x] W1-H3补充K窗口：持久`running`领取票据返回并通过准入核对后、调用假执行器前终止子进程。父进程认证operation/job链、命令摘要与冻结输入绑定；真实目录锁重开只追加一次`unknown`，第二次重开和文件字节稳定，假执行器调用数为0。该K仅覆盖单一派发间隙，不代表其他调度、生产worker、真实引擎或消费证据。见[交接](docs/superpowers/plans/2026-11-03-ticket-return-crash-handoff.md)和[TESTING](docs/TESTING.md)。
- [ ] L1中文数据复核：逐批审阅39卡候选名称/正文语义、别名、字段、语言类别及来源/使用/再分发依据；截至2026-11-02已人工对照39/39张zh-CN候选，其中38张有官方简中详情页可直接比较：29张候选标题不同，21张正文类别称谓映射未确认；人偶之锤（44088353）目前仅有可用官方日文详情页。2026-11-03单卡来源审计定位到MyCard上游提交，但未发现本项目使用/再分发许可，C1状态继续unknown；zh-SC已人工对照38/38张有候选值的记录，卡号44088353缺字段。全部语言类别、别名/本地化映射和权利依据仍开放，未知项不提升为正式数据资格。见[单卡来源与使用依据复核](docs/superpowers/plans/2026-11-03-l1-44088353-source-basis-review.md)、[双locale来源权利复核](docs/superpowers/plans/2026-11-03-l1-mycards-locale-source-rights-review.md)、[zh-CN批次1](docs/superpowers/plans/2026-11-02-l1-card-review-batch-1.md)至[zh-CN批次13](docs/superpowers/plans/2026-11-02-l1-card-review-batch-13.md)、[zh-SC批次1](docs/superpowers/plans/2026-11-02-l1-zh-sc-card-review-batch-1.md)至[zh-SC批次13](docs/superpowers/plans/2026-11-02-l1-zh-sc-card-review-batch-13.md)及[字段核验说明](docs/LANGUAGE_REVIEW.md)。
- [ ] P4-R1b-3固定场景真实恢复与独立原生重放：隔离驱动、当前工作树身份快照和prepare-only零调用预检已完成。2026-11-03首次预检发现驱动固定指向旧worker，失败的零调用记录保存在`target/p4-r1b3-current-20261103/preflight-attempt-01-mismatch.json`；驱动现从自身Cargo profile目录解析worker，并以当前`current_exe`绑定driver身份。新预检run `p4-r1b3-1793644408613378500-32336`绑定隔离worker `d50ac8ae796380e29d79f796170efea772cc2dad907923b499af5a47513c2cc1`和驱动`076d2a2ebf6b252688d687e2194829c0ed21e93b039ec4eb8df69bba4724d11c`；scope、worker进程、native calls均为0。完整HEAD、tracked diff、参与源码、`Cargo.lock`与产物身份见`target/p4-r1b3-current-20261103/source-identity.json`，固定输入仍与设计基线匹配。5项聚焦测试、workspace全目标Clippy、格式检查及workspace默认串行测试通过；opt-in冻结/原生测试保持忽略。旧run `p4-r1b3-1793625696606077800-54284`只有1次已完成Execution，旧见证对手牌组/手牌计数为0/0、冻结trace为39/1，保存输入/计划/source/driver身份不匹配，不能续跑；无Witness审计、marker、恢复重开或replay。真实scope仍需独立授权，窗口保持开放。详见[身份和零调用预检](docs/superpowers/plans/2026-11-03-p4-r1b3-scope-review.md)、[只读审计 `data/runtime/p4-r1b3/p4-r1b3-1793625696606077800-54284/read-only-journal-audit.json`](docs/EVIDENCE_RETENTION.md#ignored-evidence-links-checked-2026-11-03)及[实验设计](docs/superpowers/plans/2026-11-02-p4-r1b3-native-resume-experiment-design.md)。
- [ ] W2普通用户发布准备：2026-11-03已在隔离target构建源码CLI并完成候选包空profile启动、本地catalog路径/检索、草稿保存重开、JSON/YDK往返、同包重启及ZIP解压空格路径复核；另补裸Deck JSON到V1的兼容夹具、CLI失败不覆盖与schema回归，并定义profile升级/回滚合同。候选产物身份见[W2包验收](docs/superpowers/plans/2026-11-03-w2-offline-clean-environment-plan.md)，兼容边界及测试见[W2迁移合同](docs/superpowers/plans/2026-11-03-w2-draft-migration-contract.md)。旧dist不含workbench，真实profile升级、干净Windows环境和回滚仍开放，未切换部署。
- [x] A2 / P1（观察投影候选）：已形成受限外层私有元数据边界实验设计，覆盖不变性、公开菜单变化传播、未知输入失败关闭及输入稳定性；只适用于冻结合成fixtures，见[实验设计](docs/superpowers/plans/2026-11-02-p1-observation-boundary-experiment.md)。
- [x] A4 / P1（上述观察投影候选）：2026-11-03复验为29 passed、11 subtests passed；只验收该候选的合成边界，不代表真实隐藏状态等价或通用信息策略无泄漏。
- [x] P1 opcode24规范菜单合成交叉核验：Rust生产解码器与独立Python oracle在固定掩码上45个规范菜单动作逐项一致；90种有序编码仅为语法排列数。原生提示可达性、响应接受、反序等价与全动作资格保持未知，见[交接](docs/superpowers/plans/2026-11-03-p1-opcode24-menu-crosscheck.md)。
- [x] P1 Ground Collapse opcode24真实提示/响应接受实验设计及离线准备：固定案例、预算、分阶段重放、成功判据和停止条件已写明。私有归档中精确交付及父链材料逐项通过索引SHA恢复；归档恢复报告通过六项来源检查和verify-only（138个文件、5个目录），SHA-256=`0571114833868488b6213997ad085cb82acf6db3eac036fe9869808189f02278`。随后将阶段driver源码和测试绑定进19成员工具包；v1 schema保留正整数计数兼容，当前profile仍严格绑定19个成员。最新来源检查和verify-only通过，报告SHA-256=`a238a2f114c7cb26b6f1e79d6ca34b3e5f01f33bdb57eab0b6d2f650c2bb8c99`。准备报告仍`execution_ready=false`，没有创建scope或启动runner/worker/FFI。真实提示和响应接受仍开放；此前报告与历史失败材料保留。详见[实验设计](docs/superpowers/plans/2026-11-03-ground-collapse-opcode24-experiment-design.md)、[测试记录](docs/TESTING.md)、[归档恢复报告 `data/runtime/p1-ground-collapse-preparation-current-2026-11-03-archive-recovered-2/preparation.json`](docs/EVIDENCE_RETENTION.md#ignored-evidence-links-checked-2026-11-03)、[前一版源码绑定报告 `data/runtime/p1-ground-collapse-preparation-current-2026-11-03-driver-review-1/preparation.json`](docs/EVIDENCE_RETENTION.md#ignored-evidence-links-checked-2026-11-03)和[当前源码绑定报告 `data/runtime/p1-ground-collapse-preparation-current-2026-11-03-driver-review-2/preparation.json`](docs/EVIDENCE_RETENTION.md#ignored-evidence-links-checked-2026-11-03)。
- [ ] P4-R2：86项场景内规则完整语义与逐项原生认证；现有12项成对规则、1项实际Scythe灰点，仍缺74项规则资格。
- [ ] P4-R3：正式v6规划/报告/CLI及v1–v5完整兼容回归。
- [ ] P4-R4：冻结独立人工基准，完成16+32手可续跑评估及汇总验真。
- [ ] P4-R5：历史隔离候选`a21d587`的普通/赛事doctor、身份及smoke/replay诊断仅适用于该源码和资产；smoke因30秒`time_budget`截断，且没有可比研究账本。当前main源码合入PR #17，但`dist/ygo-local`仍为2026-10-19旧包，未完成最新源码双资产验收或发布切换；门禁保持开放，见[部署记录](docs/DEPLOYMENT.md)和[TESTING](docs/TESTING.md)。
- [ ] P0/P1/P5–P8：全卡发行分母、完整信息/概率与证明、通用知识/构筑反馈及最终产品验收，按阶段依赖继续。
- [ ] M1：比较研究关口与工作台用户流程的实际改善，按成本与证据选择下一个独立小批。

上述排序、依赖和停止条件见[当前双轨路线](docs/superpowers/plans/2026-11-01-post-w1h322b1-project-route.md)。本次文档更新不改变scope、窗口、预算或部署授权。

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
