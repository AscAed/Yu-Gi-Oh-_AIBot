# W1-C 单次 Rabbit 本机有限分析设计

状态：分析设计完成；2026-11-03按独立scope完成一次Rabbit本机有限分析，结果为`budget_limited/time_budget`。本文固定输入、资产、预算和结果边界；实际单次运行记录见[W1-C执行scope](2026-11-03-w1c-single-rabbit-execution-scope.md)和[TESTING](../../TESTING.md)。普通工作台启动状态未改变。

## 进入条件

W1-C只使用当前H3证据中与一次操作、一个任务及重启后不自动续跑直接相关的最小恢复门禁：

| 门禁 | 已有证据 | W1-C要求 |
|---|---|---|
| 修复前认证完整操作/任务链及跨链绑定 | H3.2-1全链认证；H3.2-2b-1跨链窗口 | 任一封套、前驱、记录摘要或绑定不一致时保持只读并停止 |
| accepting无任务的结果及重复提交 | 首次accepting保存后冻结前K；unknown revision 3的BeforePublish/AfterPublish/Reread；[混合恢复K](2026-11-02-mixed-operation-recovery-handoff.md) | 只能得到已保存结果或unknown；不创建替代任务、不冻结、不自动重试 |
| accepting有queued任务的恢复顺序 | [混合恢复K](2026-11-02-mixed-operation-recovery-handoff.md) | 接受操作修复之后将queued任务分类为interrupted；不重新入队或派发 |
| queued/running重启分类 | [H3窗口映射](2026-11-02-h3-evidence-gate-map.md)中的双queued、queued/running及running/queued强杀证据 | queued→interrupted、running→unknown；没有自动恢复执行 |
| 回复丢失与同ID查询 | H3.2-2a响应丢失与受控重开交接 | 用原操作ID查询；不能因客户端超时换ID再次提交 |
| 报告、预算终态及来源声明 | H2.2合同和H3报告/终态K窗口 | 只接受经过合同验证的报告；记录实际终止原因，不提升为完整搜索或最优性 |

这些证据只证明已列出的合成逻辑窗口。剩余H3逻辑窗口/调度、逐系统调用故障、断电和介质故障继续开放；若真实调用发生不确定结果，保留该状态并停止本批。选择这一门禁子集不是H3整体关闭，也不授予自动恢复或重试资格。

## 固定输入

基准是现有Rabbit走查 `tests/fixtures/rabbit.request.json`，文件SHA-256为`BD5F0427DBD68583B203702A9C8950E2263791C3A62B2685CA89773EA1631378`。牌组另有YDK导入源`tests/fixtures/rabbit.ydk`，SHA-256为`028760778E47D46C3F366F0345957F597EE820774641E6E2800A718763BBD9FA`。导入工作台草稿后，记录实际`draft_id`及整数`revision`；分析请求必须冻结该revision，不从工作区文件重新读取或覆盖草稿。

基准参数固定如下：主卡40张、额外卡3张、Side 0张；起手`85138716,2964201,2964201,2964201,2971090`；seed `1`；规则`ocg-mr5`；日期`2026-10-07`；预算`top_k=5`、`node_budget=10000`、`beam_width=32`、`max_depth=64`、`time_limit_ms=60000`。请求必须显式传入catalog和banlist快照ID，不保留`latest-ocg`别名。冻结记录另保存服务实际解析出的所有版本、评分、CDB绑定和`binding_sha256`。

## 2026-11-02 本机快照与资产基线

下表来自文件内容和SHA-256只读采样。它固定设计候选，不等于运行前身份检查、ABI探测、牌组合法性验收或引擎就绪证明。

| 角色 | 固定路径/ID | SHA-256或版本 |
|---|---|---|
| active快照指针（仅供核对） | `data/snapshots/active.json` | `81824634073C0BC515D4716DB477B40103C974A649DCDB196C5FBBF801F72879` |
| catalog快照 | `catalog-1b0564fd61eec4730828fea1d48391aa1598bca3157c255454a8dcf487485d6d` | JSON SHA-256 `3C0FA6249F4E5172488BF325F8D659070CFEFB3D93115B7EC690E0486DA4CBF7` |
| banlist快照 | `banlist-c98f770b366fed87be0fb23357a63d704db58b31508fbb88133fda66575f3783`，effective date `2026-10-01` | JSON SHA-256 `A6344CD77C4DB6DCFAB02D03110954FA1C2717422F71DA302970F427564506C9` |
| 分析CDB | `data/runtime/cards.cdb` | SHA-256 `C49A077285E1D999F32056CB65303B75E311E859B4486C48F41772A193069225` |
| core | `data/runtime/engine/ocgcore.dll` | SHA-256 `446F26DF7A2FB35D94374D74F5F5A5EF200D5454322D372B325E46B4E083D7A9` |
| core清单 | `data/runtime/engine/manifest.json` | SHA-256 `3FADB68CD22E9E01D8083C581FFD442F64E6AF65A6C2827544B19E5BAB14AA00`；core commit `38d04c9feb1a26617407091380634c87262fe3f8`，Lua commit `6e22fedb74cf0c9b6656e9fce8b7331db847c605`，x64/API 11.0 |
| Lua脚本清单 | `data/runtime/scripts.json` | SHA-256 `69BF6F9D3FE444FD53890C60BDE877F97B753F8D3E218A6349615D09F6740D91` |

请求传入上表两个具体快照ID；实际调用前必须重新核对所有文件仍与本设计一致，并确认catalog、banlist、CDB、core和脚本清单能由同一配置解析。任何差异、缺失或身份不一致都在提交任务前停止，不能回退到active别名或其他目录。当前`dist/ygo-local`是2026-10-19旧包，且没有workbench命令；不作为本W1-C实现运行包。运行候选必须由当前源码在隔离`target`目录离线构建，并记录源码基线、差异清单、CLI/worker哈希和配置哈希。上述清单没有被doctor或引擎调用验证。

## 预算与停止条件

一次人工发起的分析操作、最多一个任务；不并发提交第二个任务。搜索只用前述固定预算。当前搜索实现把单次adapter超时压到剩余搜索时间，并在总搜索时限内执行返回线路复核；报告中的`engine_calls`是搜索和逐线路复核的总调用数，不能把`node_budget`直接当作引擎调用数。报告提供`replay_ms`，不单独给出重放调用次数；没有独立计数来源时不推算该次数。配置中的单次引擎超时保持`30000 ms`，运行记录保存节点、总engine_calls、`replay_ms`和总耗时。

从提交时起设置`240000 ms`外层观察上限。`capture_engine_identity`的双遍全树采样在当前候选上测得首个约65秒、立即重复约22.6秒；此前冷缓存约98秒。240秒为已观察最慢采样加60秒搜索预算预留82秒收尾余量；这是范围设计值，不是服务端到端实测保证。出现终态即停止；超时、服务断开、调用失败或持久化提交不确定时，保留原操作/任务ID和所有证据，不生成新ID，不重放、不再次提交，也不推断零消费。等待超过上限时先停止本地服务并用受控重开读取已持久化状态；若不能认证则维持unknown并结束本批。运行期间不允许切换资产、配置或部署包。

本设计没有研究scope或可比研究账本。若执行环境要求预先收费、调用授权或独立消费核算，必须另行定义R1b-3范围、窗口和预算；本W1-C设计不能替代它们。

## 验收记录

执行时保存一份只读运行包，至少包括：

- 源码基线与本地差异身份、构建CLI/worker哈希、配置哈希；
- 上表所有输入和资产哈希，draft ID/revision、operation ID、job ID、请求摘要及冻结`binding_sha256`；
- 任务状态每次revision、报告摘要、版本、规则/快照ID、全部预算、终止原因、搜索统计和实际engine_calls；
- 操作/任务查询和最终复开结果；发生错误时保存完整错误类别及提交点，不把unknown写成零调用或零消费。

只有以下情况可报告为“单次有限分析已验收”：冻结输入与固定值相同，操作和任务链通过认证；任务到达`completed`或有效的`budget_limited`终态；报告满足现有schema/合同并暴露实际终止原因和统计；任何返回线路只按报告中的逐线路重放状态描述。若终止为`no_verified_lines`、`failed`、`interrupted`或`unknown`，照实记录为未得到可用分析结果，不重试。无论何种结果，均不声称全卡覆盖、搜索穷尽、一般策略、研究账本等价或全局最优。

## 2026-11-03 固定准入实现与候选包复核

当前生产显式入口已按本设计限制为固定Rabbit请求。`W1cAdmission`校验请求与YDK夹具哈希、牌组/起手/seed/rules/catalog/banlist/date/完整搜索预算、快照ID/内容哈希/禁限卡表生效日、引擎/CDB/脚本清单哈希、30秒engine timeout，以及CLI和worker位于同一隔离target目录。冻结后再次检查完整请求及运行身份；非固定命令在accept前拒绝，冻结输入不匹配会保存Rejected操作但不创建任务，认领后身份不匹配会记录`AssetMismatch`执行前失败并停止派发。

聚焦回归覆盖固定值准入、冻结拒绝及认领后身份失败持久化。当前HEAD `672e5a823fcad60e9413d79cac810b68a2bb003c`的未提交工作树已在`target/w1c-executor/cargo`离线构建CLI和worker；包、配置、冻结快照及资产身份哈希见[TESTING](../../TESTING.md)。只读身份采样报告`consistent=true`，但它不是doctor、worker、引擎或分析执行证据；普通启动仍为`analysis_not_configured`。

身份采样会对脚本目录做两次完整内容扫描。此前CLI静态身份命令冷缓存/立即重复约98/21秒；2026-11-03候选重建后首个/立即重复静态采样约65/22.6秒。每次真实任务派发由`claim_next`在持久化`running`后、返回票据前对worker、core、CDB、脚本及清单做完整双遍核验；认领后另复核CLI、配置、worker及快照文件哈希，不锁定外部资产。本次单次分析在提交后83.776秒得到终态，报告搜索耗时55.775秒，较240秒上限短；这是本scope观测值，不推广为其他环境的端到端保证。操作/任务/报告重开材料稳定，报告schema通过；FFI、OS层worker创建和消费未独立计量。具体值和边界见执行scope。普通启动仍`analysis_not_configured`；未运行doctor/runner、未切换部署，W2、P4和R1b-3另行推进。

## 当前交付与未执行项

静态输入/资产基线、最小恢复门禁、默认关闭的显式配置、持久协调器、串行单任务派发、失败分类和Rabbit固定准入均已实现并完成各自记录中的聚焦验证。单次真实Rabbit分析已按独立scope执行并以`budget_limited/time_budget`验收；FFI/消费计量、报告来源独立认证、独立原生重放、完整搜索和其他H3门禁仍未完成。W2干净环境/草稿往返、P4发布门禁和R1b-3另行推进。

## 2026-11-02 生产调用路径复核

当前源码中，`WorkbenchServer::start`默认设置`analysis: None`；只有显式给出`--analysis-config FILE`才打开持久任务服务和生产执行器。无配置时仍不可提交分析。启动只解析配置并恢复存储，不初始化或调用worker；成功冻结后一次派发最多领取一个任务。上述实现没有固定Rabbit参数准入，也没有真实分析运行证据。

显式配置和单任务有界派发批次已实现，并通过不调用原生引擎的测试验证默认关闭、报告先持久化再提交终态、不确定结果转unknown、停派发和重开不重发。下一代码批次应落实Rabbit固定参数准入，验证配置与快照/CDB身份绑定，再对最终差异做独立审阅。之后另立W1-C执行scope、运行包身份和调用/消费边界；本文不授权启动worker或引擎。源码依据：[workbench.rs](../../../crates/ygo-cli/src/workbench.rs)与[analysis_http.rs](../../../crates/ygo-cli/src/workbench/analysis_http.rs)。
