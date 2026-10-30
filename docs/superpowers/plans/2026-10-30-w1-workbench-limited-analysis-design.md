# W1 工作台受限分析接入设计

## 状态与范围

本文是待实现的接口与用户流程设计，不描述已经存在的工作台能力。本批只完成设计和静态核对：不启动引擎、runner、worker、FFI，也不创建研究收费记录。实施需要另开 W1 批次，并分别验证合成任务路径与本机引擎资产。

当前工作台只管理 `DeckDocumentV1` 草稿，并提供可选 catalog 查询和只读语言字段状态。它不调用分析库。`combo analyze` 目前通过同步 `ygo_api::combo::analyze` 运行搜索，搜索内部调用 `ProcessEngineAdapter`；尚无工作台任务队列、运行状态查询或取消接口。

## W1.1 输入与分析边界

### 冻结输入

用户从工作台选定草稿及其当前 `revision`，再提供五张起手、随机种子、规则、catalog、禁限及日期和搜索预算。服务收到请求后先读取该草稿，确认 revision 仍匹配，然后将草稿内容和显式分析参数组合成不可变任务输入。之后草稿修改不改变已经创建的任务。

浏览器只提交服务生成的草稿 ID、内容 revision 和结构化值；它不提交文件路径、引擎路径、CDB 路径或可执行文件路径。引擎、快照根和资产路径继续来自服务启动时的本机配置。任务记录保留规范化后的完整请求及解析出的 snapshot ID，便于显示版本和审计输入身份。

### 与现有请求类型的映射

任务输入复用 `ygo_api::combo::ComboAnalyzeRequest`，草稿引用与 revision 是工作台任务层的外部绑定，不添加到该既有请求合同中。

| 工作台输入 | `ComboAnalyzeRequest` 字段 | 约束 |
|---|---|---|
| 已保存草稿的 `deck` | `deck` | 必须使用请求所指 revision 的内容；验证完整牌组和所有分区 |
| 五张起手 | `opening_hand` | 恰好五张；按卡号和牌组中的可用数量逐张验证。同名卡按多重集合消费，不赋予可区分的物理副本身份 |
| 随机种子 | `seed` | `u64`；Rabbit 走查值为 `1` |
| 规则 | `rules` | 首版只接受当前支持的 `ocg-mr5` |
| catalog 选择 | `catalog_id` | 首版必须明确解析为可读取的已导入 snapshot；服务从本机 `SnapshotStore` 读取，不接受浏览器路径 |
| 禁限表 | `banlist_id` | 传入固定 ID 或 `latest-ocg`；由现有 `prepare` 解析为实际 ID |
| 生效日期 | `as_of` | ISO 日期；禁限表须在该日生效 |
| 搜索预算 | `search` | 复用 `top_k`、`node_budget`、`beam_width`、`max_depth`、`time_limit_ms`，由 `SearchBudget::validate` 校验范围 |

服务在入队之前调用现有分析准备校验：要求规则受支持、预算有效、日期有效、banlist 对日期有效、完整牌组符合该 snapshot 的卡片支持与禁限限制、起手与主卡组匹配，并确认 catalog 的 CDB 哈希与引擎身份一致。校验失败时创建请求返回结构化错误，不产生排队任务。

当前 `prepare` 将缺省 catalog 解析到 active catalog，并把 `latest-ocg` 解析成具体快照 ID。W1 首版设计要求任务明确记录最终解析的 catalog/banlist 身份；不得只保存 `latest-ocg` 这类可变别名作为重跑依据。

### Rabbit 样例走查

`tests/fixtures/rabbit.request.json` 对应以下冻结输入：40 张主卡、3 张额外卡、空 side，起手为 `85138716`、三张 `2964201` 和一张 `2971090`，seed `1`，规则 `ocg-mr5`，banlist 请求值 `latest-ocg`，日期 `2026-10-07`。预算为 `top_k=5`、`node_budget=10000`、`beam_width=32`、`max_depth=64`、`time_limit_ms=60000`。

该样例用来检查字段映射和校验顺序，不代表它在当前资产下通过分析，也不把样例中的日期扩展为当前禁限表结论。任务只有在服务配置的 catalog、CDB 和禁限 snapshot 实际存在且通过现有校验时才可排队。

## W1.2 任务交互与结果展示

### 首版任务接口草案

以下是建议的工作台本机 HTTP 接口，尚未实现；实现时应新增明确版本的请求/响应合同，并保持现有草稿端点不变。

| 方法与路径 | 行为 |
|---|---|
| `POST /api/analysis-jobs` | 以草稿 ID、revision 和结构化分析参数创建任务；完成输入冻结及分析准备校验后入队，返回任务 ID 和初始状态 |
| `GET /api/analysis-jobs/{id}` | 返回任务状态、已确认阶段、冻结版本摘要，以及任务完成后可读取的报告 |
| `DELETE /api/analysis-jobs/{id}` | 仅取消仍处于 `queued` 的任务；已经开始的任务返回明确的 `cannot_cancel_running` 状态错误 |

任务请求继续使用现有工作台的本机 Host、Bearer token、同源 Origin、请求体大小和本机路径边界。客户端不能选择任意输出路径、worker 或资产目录。

实现前置安全条件：当前HTTP入口只对 `POST` 和 `PUT` 强制校验Origin。新增 `DELETE /api/analysis-jobs/{id}` 前，必须把同源Origin校验扩展到所有状态变更方法（至少 `POST`、`PUT`、`DELETE`），并为 `DELETE` 补充跨站请求拒绝回归覆盖；不能只依赖Bearer token后直接加入DELETE路由。GET仍为只读，继续要求Bearer token。

### 排队、状态与重启

默认并发策略为最多一个运行任务和一个等待任务。队列已满时拒绝新任务并说明容量，不在内存中静默丢弃。队列取消只移除等待任务；返回取消结果后不会再启动该任务。

任务状态建议为 `queued`、`running`、`completed`、`budget_limited`、`failed`、`cancelled`、`interrupted` 和 `unknown`。全部准备校验在创建请求中同步完成，失败不生成任务，所以`validating`不是可轮询的任务状态。现有`analyze`没有搜索进度回调；任务只持久化记录`queued`和`running`等状态时，界面分别显示“排队中”和“分析中”，不能伪造“正在验证线路”等内部阶段，也不承诺节点数、当前分支或实时百分比。现有 `analyze` 是同步调用，不能可靠中断正在执行的搜索，因此 UI 对运行任务不显示可立即生效的取消按钮。若未来增加运行中取消，须另行定义协作式停止及费用/进程收尾语义。

首版可采用进程内队列，但返回创建成功前必须持久化冻结请求和 `queued` 状态；出队后须先持久化 `running`，再调用同步分析；报告持久化成功后才可发布 `completed`。进程重启后，仍为 `queued` 或 `running` 且没有可认证完成报告的任务标为 `interrupted` 或 `unknown`；服务不得自动重发分析。若后续要恢复执行，须新增具备账本与恢复合同的实现及独立验收，不由本设计推定。

### 结果与错误呈现

- `completed` 表示报告已通过现有报告合同，且返回线路具有当前 `AnalysisReport` 所要求的逐线路重放标记；它不表示搜索空间完整或全局最优。
- `budget_limited` 表示搜索因 `node_budget`、`time_budget` 或 `depth_budget` 等边界停止。界面展示 `SearchReport.termination`、各项预算、搜索统计和已返回线路，并明确这些线路来自有限搜索。
- `failed` 展示稳定错误码、阶段和可安全显示的说明。输入/资产校验失败发生在入队前；搜索或worker错误则成为任务失败。错误文本不得泄露本机绝对路径。
- `interrupted` 或 `unknown` 表示无法认证任务是否完整结束或是否有可用报告；不推测为零耗时、零worker调用或成功结果，也不自动重跑。
- 结果保留 `AnalysisReport.request`、`runtime_request.versions`、catalog/banlist/CDB、规则与协议版本、预算、终止原因及搜索统计。界面可显示线路的动作、评价与逐线路验证状态，但必须同时显示覆盖缺口和截断状态。
- 有限beam、固定预算、启发式评分、单条成功线路或逐线路重放均不能称为全局最优证明。

### 用户流程验收案例

| 场景 | 预期行为 |
|---|---|
| Rabbit 样例和合法冻结草稿 | revision、起手、seed、规则、资产和预算映射正确；校验完成后进入队列 |
| 空草稿或残缺牌组 | 可继续保存草稿；创建分析任务时被完整牌组校验拒绝，不启动分析 |
| 起手不是五张或超出主卡组可用数量 | 返回字段级校验错误，不入队 |
| catalog/CDB、禁限快照缺失或身份不一致 | 返回来源/资产错误，不猜测或回退到其他路径 |
| 草稿在创建请求前已改变 revision | 返回 `revision_conflict`，不创建任务 |
| 队列已满 | 返回容量错误，当前任务状态不变 |
| 排队时取消 | 任务变为 `cancelled`，永不启动 |
| 搜索预算截断 | 返回 `budget_limited` 和实际终止原因，展示可用报告并标注不完整 |
| 服务在任务运行时重启 | 未能认证完成的任务显示 `interrupted` 或 `unknown`；不自动重发 |

本表是待实现的预期行为，不是已运行测试或本机真实分析结果。

## 实施关口

下一批 W1 实现先用合成适配器和临时 snapshot 验证草稿 revision 冻结、队列容量、取消排队任务、重启诊断及报告呈现。只有这些通过后，另行制定本机资产验收：记录当次 CLI、worker、引擎、CDB、catalog、禁限与源码身份，明确调用和停止边界。真实引擎分析、运行中取消、细粒度进度、跨进程恢复及新增研究预算不包含在本设计的验收中。
