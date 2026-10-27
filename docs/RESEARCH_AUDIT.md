# 研究输入与动作响应审计 v1

## 受限信息研究入口

洗手牌后结束另用独立`rabbit-shuffle-end-observation-v1`，不改变下述旧配置或旧观察键：

```powershell
$env:PYTHONPATH='python'
py -m ygo_eval.research audit-information-route --contract <route-contract.json> --samples tests/fixtures/information-route-policy-samples.json --evidence ROLE=<原始文件> --cdb <冻结cards.cdb> --runner <已保存terminal-evaluate.exe> --output <新的忽略报告.json>
```

ROLE固定为parent-acceptance、parent-contract、terminal-shuffle-end、frozen-input、source-request、core-processor及core-constants，每项单独传入。对应独立合同为information-route-study，报告为information-route-audit。它从原始菜单核对己方命令8/7及已解决决策，将己方动作加入可见历史；已核对的对手HINT和空连锁只记录于外层审计，不进入观察键，也不生成“对手不响应”公开历史。未知或额外变化停止适配。

每个历史run产生两个决策视图和一个无后继终止视图。终止点phase未知，结束阶段512仅保留在历史中；14项查询、处理批及冻结CDB经现存纯数据runner独立校验后，才允许计数及效用0。策略样本不能指向终止视图。该入口不运行worker，不产生新原生重放，不将固定线路闭合外推为其他分支或完整概率/动作资格。

`information-study.schema.json`独立绑定冻结Rabbit来源、规则/资产、终场目标、公开初始声明及历史语料；不改变旧case/problem或产品评分。运行：

```powershell
$env:PYTHONPATH='python'
py -m ygo_eval.research audit-information --contract <contract.json> --samples tests/fixtures/information-policy-samples.json --evidence frozen-input=<frozen-cases.json> --evidence rabbit-empty=<rabbit-empty.json> --evidence rabbit-shuffle=<rabbit-shuffle.json> --evidence terminal-shuffle-end=<terminal-shuffle-end.json> --evidence rabbit-full=<terminal-rabbit.json> --evidence tournament-full=<terminal-tournament.json> --evidence core-field=<field.cpp> --evidence core-random=<duel.cpp> --evidence core-menu=<playerop.cpp> --output <新的忽略目录报告.json>
```

首版固定`rabbit-idle-observation-v1`，仅投影己方初始化后的首次idle和命令8后的下一idle。原始消息独立解析，公开阶段来自NEW_PHASE；未知/额外场面消息停止适配并保留范围缺口。终场报告只提取早期原始前缀，不用最终checkpoint回填。策略视图保留有序手牌、可见历史、菜单坐标/索引/Choice/字节，来源和prompt路由留在视图外；完整checkpoint中的双方精确牌库顺序不能交给合法信息策略。

策略样本为数据：按policy_id和观察键比较精确有理分布，不执行用户代码。不同策略可以作不同选择；有限样本一致不等于任意策略实现无信息泄漏。`tests/fixtures/information-policy-samples.json`是合成示范策略选择，不冒充历史实际决策。

概率部分是五个标签实例的独立均匀索引Fisher–Yates合成模型：120个标签排列及20个卡号顺序的质量分别为1。冻结核心静态源码仅登记版本/哈希；真实PRNG状态、条件分布、拒绝采样与后续随机性仍有缺口，native_probability_verified固定false。顺序夹具仅说明不同位置/选择顺序在数据及编码上可区分，不认证未触达反向响应的原生合法性或顺序等价。

该入口只读且新增原生调用固定0，不创建窗口或账本。版本化报告分别记录工具、受限观察、策略样本、理想数学模型及历史范围缺口；成功也不提升proof_ready、complete_action_coverage或global_optimality。实跑结果见TESTING，当前状态见TASKS。

本工具实现P0.3的结构合同和P1.1的有界协议审计。它不实现最优性证明；`proof_input`只表示输入用途声明，不能进入现有原生审计执行器。`validate`返回`proof_ready=false`，概率状态映射与合法信息策略仍未验证。

## 冻结输入

`schemas/research-case.schema.json`和`python/ygo_eval/research.py`共同定义v1。每例固定完整40–60张主卡、至多15额外/副卡、从主卡取出的五张手牌、seed、DLL/CDB/脚本清单内容哈希、OCG禁限版本及原始禁限文件哈希。目标只有`terminal_utility`：正常终场、提前获胜、失败和平局分别定义整数效用，v1没有未定义的第二排序指标。

可见信息区分自己、对手、隐藏字段。自己不能看到对手手牌或双方牌库顺序；对手不能看到自己的手牌。记录对手资源不意味着策略可以读取其隐藏信息。概率记录使用精确分子/分母、唯一outcome ID且总和为1；seed仅用于复现。分布outcome还没有绑定完整机会状态，因此不能当作概率问题已经数学冻结。

`validate`仅检查结构及语义，不验证来源、合法性或引擎支持：

```powershell
$env:PYTHONPATH='python'
py -m ygo_eval.research validate --case <case.json>
```

`run`执行前额外核对禁限原始文件哈希及版本、实际DLL/CDB/脚本清单哈希、request版本、牌组/手牌/seed。只读CDB检查OCG标记、Token、主/额外区域及alias合并后的跨区三张/禁限上限；这不替代P0.1的正式发行分母。只接受标准MR5、无interruption/first_turn/scenario的`frozen_scenario`协议案例。对手实际资源必须等于worker默认：复制自己的主卡组、初始手牌为空、`fixed-opponent-v1`。报告不会把空手对手改写成实战对手。

## 顺序执行与总预算

先离线构建工具，再通过Python入口运行；包安装或在线构建必须遵守根AGENTS代理要求。

```powershell
$env:CARGO_NET_OFFLINE='true'
cargo build -p ygo-engine-adapter --example research-audit
$env:PYTHONPATH='python'
py -m ygo_eval.research run --cases <frozen-cases.json> --runner target/debug/examples/research-audit.exe --ledger <calls.jsonl> --output <evidence-directory>
```

批输入是`{context,cases:[{case,request,banlist_path}]}`。`case`采用上述合同，`request`采用既有`RunDuelRequest`。Python将全部冻结输入的规范JSON哈希作为账本context，写出低层batch意图，再调用Rust example。低层入口用于复核已冻结的批，不替代Python的来源/案例验证。

`ResearchBatch`使用单个排他锁`CallJournal`。最多8个case ID、每例512、合计4096次原生请求。执行、独立重放以及调用失败同样预扣费；今后加入query/audit时也必须使用同一入口。已收费未知调用或持久意图尚未收费时，重开拒绝继续。每例绑定完整请求哈希，不允许更换牌组/资产/seed后沿用case ID；调用预算不会因重开恢复。

首次打开保存真实UTC秒，重开沿用。超过两小时或时钟回退拒绝新增请求；为30秒worker留出时间，起点后7170秒即停止新增。存储及终止开销仍须在实际耗时中报告，这不是硬实时进程杀限。预算达到上限时保存局部证据，停止新case和重放，不改写成无解或最优。不要通过新建账本绕过本批总预算。

Rust example在每组执行前后采集实际双次资产身份，要求一致、匹配request版本并未发生前后变化；这些扫描也计入本批墙钟。它执行原请求及独立重放，保存完整raw帧、请求、返回错误/状态、生产响应编码与独立oracle比较、账本序列及未触达opcode。原始账本和内容寻址blobs共同保留，不只保存成功摘要。

## 支持矩阵与资格边界

oracle直接读取独立字节游标，不调用生产`parse_prompt`生成期望集合。生产解析只提供被比较的实际动作编码。选择集合由独立include/exclude遍历产生，超过4096组合返回缺口。

| opcode | 行为 | 审计编码/边界 |
|---|---|---|
| 11 | idle command | 索引高16位、命令低16位；battle/end/shuffle标志分别控制6/7/8；旧生产battle及共同shuffle遗漏已由离线回归修复 |
| 12/13 | effect yes/no | 32位0/1；12含卡号及完整位置 |
| 14 | option | 32位选项索引 |
| 15 | select card | `[0,count,indices...]`；可取消时`-1`；min/max和组合上限 |
| 16 | chain | 32位索引；只有非强制可`-1` |
| 18/24 | place/disfield | 每区player/location/sequence三字节；mask可用区与所需数 |
| 19 | position | mask中1/2/4/8的32位单选；未允许位置被拒绝 |
| 26 | select/unselect | `[1,index]`；finish/cancel可用时`-1` |

每项`matches`只表示`canonical_response_comparison`。响应顺序等价性、idle的shuffle控制含义、完整协议集合与实际效果语义均未证明。`complete_action_coverage`和`global_optimality`始终为false。未触达、未知、无法响应、超组合上限以及搜索choices_per_parent/前沿/节点/墙钟裁剪均是缺口。不能用十类提示都可解析或canonical匹配授予完整动作资格。

聚焦测试对十类提示检查合法、删除、增添和截断；另覆盖强制连锁禁止pass、位置mask、组合超限、battle缺口和未知opcode。预算测试使用合成失败调用，覆盖512/4096/8例边界、重开、时钟、未完成意图和请求绑定，不消耗原生预算。合成测试不冒充原生触达。

## 2026-10-19本机首批证据

本机冻结输入、账本和各例完整输出位于忽略目录`data/runtime/baseline-2026-10-19/research/`。Rabbit使用既有xyz线路；Phantom只冻结既有初始手牌提示；赛事使用既有manual兼容线路。每例执行加独立重放，计划6次请求，不运行搜索或48手评估。真实状态、计数、耗时和二进制身份以`docs/TESTING.md`当前条目为准。

初批运行的example二进制SHA-256为`f43440addbab877b7634a95a3a5106cd31726764c7484e766a21798a7d7843d1`。运行期间增加了不可覆盖case哈希绑定回归及summary文件持久化；不得将早先二进制的证据说成最终工作区的完整复验。最终构建关联记录和同账本复验另行保存。

初批赛事执行/独立重放已各收费一次且均为`engine_verified`，共64个提示canonical比较一致；但后置身份采集实际返回`assets changed during identity capture`并退出1。赛事开发worker位于`target/debug`，并发构建改变该二进制，未授予资产一致性结论。原6次费用和结果均在账本保留；该故障不是注入测试。

可零新增原生请求恢复已收费结果：低层batch只保留原赛事case，context仍用原完整Python输入的哈希，然后执行：

```powershell
& target/debug/examples/research-audit.exe <tournament-existing-context.json> --recover 5
```

此模式从同一账本读取并验证第5/6次结果，恢复raw帧、编码比较和重放对照；不执行worker，不重新计算原时点资产身份，故`assets_unchanged=false`。恢复报告与原始失败元数据分别保留于忽略目录。后续对最终构建的赛事复验仍须在同一账本新增执行/重放两次，并在预检、运行、后检期间暂停其他构建。

输出只允许仓库忽略的`data/runtime/**/research/`专用目录；拒绝tracked文件、symlink/junction及与输入或资产树重叠的目标。证据和summary使用带attempt标识的`create_new`文件，预算零新增消费、重开和失败报告也不会覆写旧证据。

## 用户授权的断点续办窗口

2026-10-19原窗口到期后，用户明确允许“新的2小时时间窗，仅补执行和重放2次”。低层入口使用同一账本、context和赛事case，显式传入`--authorized-window user-resume-20261019`。该模式追加不可覆盖的窗口记录，冻结起点、原累计消费和case；保留原`research/start`及全部历史。窗口仅允许指定case执行一次、重放一次，仍受原4096总量、512单例、未知消费和30秒worker限制。重开相同ID不重置时间或消费；新ID必须另有用户授权，参数本身不是人类授权证明。当前命令运行后不得自行再开窗口。

续办结果：用户授权的新窗口只新增第8/9次，赛事执行/重放一致且资产稳定；最终runner重开同窗口零新增消费。重开已消费前缀由账本恢复，恢复报告不授予原时点资产连续性。此入口按单worker顺序运行，不支持并发预算调用。当前账本及具体构建/资产身份见TESTING最新条目与本机acceptance清单。

## P1离线历史帧审计 v1

`python -m ygo_eval.research audit-corpus --evidence ROLE=PATH [可重复] --runner <prompt-corpus-audit.exe> --output <新JSON>`读取既有报告的prompt_audits，不启动worker、不读取原生账本、不重新执行旧线路。Rust example只收stdin帧并输出stdout JSON；完整报告合同为`schemas/prompt-corpus-audit.schema.json`。它不能替代原生独立重放。

每次报告绑定原文件SHA、请求内容SHA、每个帧序号及raw SHA、本轮源码和auditor哈希。相同raw保留所有出现位置；origin仅区分historical_report和synthetic_fixture，不自签历史报告的引擎资格。历史响应和当前解析分别对照独立oracle：matched、mismatch、error、unavailable分开。早期Rabbit/Phantom没有保存完整actual_response_bytes，报告unavailable，不从旧matches或新oracle反推旧动作集合；旧解析器Err另记historical_parser_failed。

退出0表示本语料的两组canonical比较均无缺口；退出1表示已保存差异/错误/不可得报告；退出2表示输入、runner、输出或一致性检查失败，不发布成功报告。未知提示和截断帧保留逐帧诊断。输出必须为忽略的data/runtime/**/research下新文件，禁止覆盖；采集前后检查来源、源码及runner。报告无个人绝对路径，native_calls固定0，complete_action_coverage及global_optimality固定false。

本轮idle修复按冻结core提交38d04c9feb1a26617407091380634c87262fe3f8的playerop/processor约定：6进入战斗、7结束、8洗切手牌；手写8种标志组合测试分别约束生产解析器与oracle。洗切后实例顺序、机会状态、信息与循环等价性仍未证明，不删除8或据此裁剪。新增合法动作可能改变有界推荐及旧协议单动作自动响应，旧Choice和bytes仍可读取/编码，不承诺候选逐字不变。

子集额度为4096，取消不计额度。生产先饱和计数，再按原字典序迭代枚举，拒绝第4097项且不交付部分集合；迭代避免选择4096张时递归栈过深。oracle仍为独立include/exclude算法。当前parse匹配不证明顺序响应完整、随机语义或未触达opcode。

P1.2候选定义见[P1_MICROCASE](P1_MICROCASE.md)。本批仅冻结候选与缺口，不扩展旧research-case v1，不实现求解器或安排新的原生消费。

### 旧报告的精确派生字段兼容

新decode_frame会在fields.prompt.actions中包含6/8，旧报告没有。读取验证使用frame_matches_raw/recorded_prompt：只接受完整当前结果或opcode11删除6/8后仍非空的精确旧投影，sequence/opcode/raw/supported/其余fields及旧动作标签、Choice和bytes均需相等。prompt_matches_raw提供对应只读校验。组合超限及其他opcode不作宽容。历史自动响应的单选证明按已验证的记录prompt检查，新worker按当前完整菜单决定是否自动响应。

这项兼容只能识别已知旧派生形式，不能单凭该形式证明文件生成时间或原生真实性；历史文件哈希、账本和独立来源仍须另行验证。不能据此授予完整动作资格或声称新worker已经原生重放了旧线路。

## 快照评价与终场诊断 v1

`python -m ygo_eval.research evaluate-snapshot --evidence <原报告> --cdb <冻结CDB> --runner <snapshot-evaluate.exe> --output <新JSON>`只读输入，通过stdin/stdout调用纯Rust评价器，不启动worker。目标固定为`rabbit-own-face-up-xyz-v1`：己方控制、怪兽区域、表侧超量数0–7。查询记录与CDB均须支持判断；缺失、类型矛盾、重复位置或越界保留未知。叠放素材不计为独立怪兽。

执行与重放分别报告快照值、终止诊断和效用。原始WIN消息按冻结core协议在研究模块独立解析，不改变生产decoder。未知胜方、损坏/冲突消息、自然结束后游戏后继和执行失败均阻断确定效用。只有观察到下一回合消息仍不足以将旧checkpoint绑定到该边界；本批正常效用始终不凭固定`turn=1/turn_player=0/phase=512`标签获得，明确保留`checkpoint_not_bound_to_terminal_boundary`。

来源、冻结CDB、目标、源码与auditor哈希各自记录。报告自声明不能认证来源真实性或原生独立重放；离线评价新增原生调用为0，proof_ready、complete_action_coverage、global_optimality保持false。独立报告不改变research-case v1固定normal值或产品评分。

## 独立小批原生回归

`native-regression`使用专用runner与新scope/账本，不能复用历史追加窗口。入口冻结`--cases`、`--runner`、`--worker`、`--build-record`、候选配置重复采集的`--identity`、`--window-start`、`--old-ledger`和新的`--output`目录；`--prepare-only`只冻结输入，不执行worker。先完成构建和测试，以独占新建方式保存`window-start`起点，再采集候选身份，令身份扫描计入实验墙钟。证据及原始请求仅写忽略目录。候选普通/赛事配置只改worker路径，冻结两套资产不得混用。

独立上限16次、最多8例、2小时；本次只编排5例，每例执行与独立重放各一次。起点在首次实时资产预检前持久化，重开不重置。具体请求首次调用前写入不可覆盖意图；完成结果从账本恢复，未决消费阻断。30秒超时、失败与额外查询/探针同样须经统一扣费包装层；未授权额外目的直接拒绝，不存在免费worker入口。

恢复既有报告时，专用runner的`--verify-recorded`模式核对账本内不可覆盖证据收据、已收费结果和重算响应审计，新增原生调用为0。报告文件自行填写的重放/资产/消费字段不能替代此检查；该验证不重新授予原生时点资产连续性。

顺序为Rabbit完整线路、隔离赛事完整线路、Rabbit空决策前缀、父菜单公开命令8、父菜单公开命令7。后两者只从父结果的实际可见合法菜单取prompt ID及Choice，不从seed或隐藏牌序决定。洗切验证自己的消息、手牌多重集及随后菜单关闭该次shuffle，不要求顺序变化。命令7只诊断结束阶段及下一回合，不授予精确终场查询绑定。

子请求返回完整历史，洗手牌检查先要求父事件为子事件的精确前缀，再只检查新增后缀的一条己方shuffle消息；初始化历史中的同类消息不重复计为命令8结果。前缀被改写或额外增量消息均拒绝。实际观察器故障、停止和离线修正记录见TESTING，不据修正自动继续原生请求。

每组保留完整原始帧、响应编码集合、错误、前后身份、父子引用、账本及重放差异。引擎错误、重放差异、资产漂移或未知消费立即停止，剩余6次不自动使用。调用达到预算或时间不足只记未完成。后续精确终场捕获、剩余提示与P1.2独立合同另设门禁；本批不运行完整树搜索。

## 显式终场绑定及研究问题 v1

协议2普通固定五张起手请求可显式设置`research_capture`，其schema_version为1，objective为`rabbit-own-face-up-xyz-v1`，boundary为`first-next-turn-process-return-v1`。默认省略，不改变旧请求身份。其他协议、probe及特殊情景拒绝。正常边界是核心首次发出下一回合NEW_TURN的处理返回点，包含已进行的新回合初始化；phase保持未知。观察保存完整批次、原始查询、目标投影及各哈希，查询失败保留部分证据，不将空值当作0。

`evaluate-snapshot --report-version 2`须配合纯数据`terminal-evaluate.exe`；默认v1仍用`snapshot-evaluate.exe`。v2独立重解消息批和14个怪兽区查询，并核对请求、事件前缀、坐标、类型与冻结CDB；只有结构绑定通过才允许正常效用等于0–7计数。结构绑定、来源真实性和账本独立重放分别记录，报告自声明不授予后两项。旧报告缺少观察记录时仍未知。

`validate-problem --problem <JSON>`读取独立`research-problem-v1`候选：绑定旧案例及来源哈希，声明状态目标、精确边界、提前胜8/负−2/平−1及自然结束无后继。seed仅复现。隐藏信息、概率、动作顺序、循环、树规模和必要动作各自给出状态与阻断原因；候选有效不代表证明实验就绪，不修改旧research-case v1的固定normal语义。

`terminal-regression`使用独立固定6次scope，要求原9次及上批8次账本、父输入/报告及原runner，并冻结普通/赛事身份、构建、源码和请求。窗口文件kind为`terminal_regression_window_start`，首次候选扫描前独占保存，2小时起点不可重置。仅执行Rabbit、赛事、由原prompt9公开命令7派生的洗手牌后结束线路，各执行/重放一次。首个绑定、执行、重放或资产异常即停止；内部FFI查询次数与收费worker请求分别记录。所有证明、完整动作及最优性标志保持false。

冻结核心会无条件附带QUERY_IS_PUBLIC；两个目标查询解析器分别允许该可选布尔TLV，严格拒绝重复、错误长度和非法布尔，不将公开状态用于目标计数。查询类型与冻结CDB完整类型不一致时返回未知，未建立动态类型变换模型。独立校验覆盖原始批次分帧、边界消息和目标查询字段，不授予全部消息语义或全游戏树资格。工具修复后的源码与原生时点证据必须分别记录，不能改写已收费失败。

## Rabbit单例验真 terminal-smoke v1

`terminal-smoke --cases <冻结案例> --baseline-dir <上批终场交付目录> --runner <terminal-regression.exe> --worker <新worker> --build-record <构建记录> --identity <双资产身份> --window-start <新窗口> --output <新research目录> [--prepare-only]`使用独立terminal-smoke-v1 scope，仅允许terminal-rabbit执行和重放各一次，总上限2次、2小时。窗口kind为terminal_smoke_window_start，首次候选身份扫描前独占保存。重开不得重置；历史18次和旧窗口剩余5次保持原义。

基线检查固定上批acceptance及三份旧账本保护哈希，旧失败收据使用保存的原生时点runner并带verify-recorded零调用复核。新请求逐字段匹配原Rabbit请求，仅替换worker路径；manifest冻结CDB类型表哈希、源码/构建/双资产、具体请求和输出位置，调用使用预先保存的input SHA，不根据调用时变化重新接受哈希。

Rust runner可选batch_kind值terminal-smoke-v1启用新模式，缺省仍为原6次模式；旧16/4096入口不变。重放前需完整决策、无错误或待提示、14查询及精确边界绑定、计数和正常效用1、实际响应集合审计、重新扫描后的资产和剩余时间全部通过。失败或未知消费保存已有结果并停止，不重试或改线路。内部目标查询计数与收费worker请求分别记录，legacy查询总数未统计时保持null。

独立terminal-smoke.schema.json含manifest、pair及summary三类。成功必须有两次完整结果、重放一致、资产稳定且消费全部完成；失败和消费未知可单独表达，不填成0或成功。报告的proof_ready、complete_action_coverage、global_optimality始终false；仅一条冻结线路可以获得终场绑定与重放证据。只读历史恢复不重新授予原时点资产连续性。

## 赛事与洗手牌后结束 terminal-followup v1

`terminal-followup --cases <冻结案例> --baseline-dir <Rabbit交付目录> --historical-audit <独立历史核验报告> --parent-input <原洗手牌输入> --parent-evidence <原报告> --parent-runner <原生时点runner> --runner <新runner> --worker <新worker> --build-record <构建记录> --identity <双资产身份> --window-start <新窗口> --output <新research目录> [--prepare-only]`使用独立terminal-followup-v1 scope，总上限4次、2小时。固定先terminal-tournament，再terminal-shuffle-end，各执行/重放一次；每次必须完整14查询，计数/正常效用0。完整零值和缺失/失败查询严格区分。

最新Rabbit交付及四份历史账本绑定原20次；历史收据只用各自已固定哈希的原生时点runner零调用复核。普通/赛事CDB类型表分别绑定，父公开prompt9的命令7派生与原模板核对。首次收费前冻结两份具体请求及所有输入；第一组未通过不调用第二组。prepare-only不产生原生请求。

历史来源门禁在创建新manifest前执行。2026-10-20版本因最早9次原runner缺失而拒绝，旧证据保留。2026-10-21用户明确接受独立历史完整性核验作为后续消费及输入依据：新增必需`--historical-audit <报告>`，入口现场重算并比较全报告，不能仅信任valid标志。报告哈希加入manifest输入集合，参与context身份。原runner来源、历史重新执行和新的原生重放资格均不因此获得。缺少或伪造报告、来源变化仍在新请求和收费前拒绝。

runner的batch_kind=terminal-followup-v1启用新模式，其余模式不变。重放前门禁与Rabbit单例相同，但期望值固定0。第一组收据保留消费2次时的前缀；后续总计达到4次不改写前组收据，恢复汇总使用账本当前总计。失败、部分完成和消费未知分别保存，不能将未知填0。proof_ready、complete_action_coverage、global_optimality均false，旧Rabbit资格继续绑定原产物。具体实施边界见[四次验真计划](superpowers/plans/2026-10-20-terminal-followup.md)。

## 独立历史完整性核验 audit-history v1

`python -m ygo_eval.research audit-history --baseline-dir <四次入口离线交付目录> --output <新JSON>`只读固定验收链及最早9次的账本、请求、报告和blob。它使用Python标准库，不启动进程，不打开会创建/恢复的账本，不访问引擎资产；只向新的忽略输出文件写报告。

核验独立重算冻结v1编码下的序号/链哈希/状态转换、案例借记、检查点预算及收费前缀，逐次校验结果内容地址、事件块、原始及归一化哈希和请求/报告绑定。首版只支持该固定历史实际出现的header/checkpoint/begin/complete，未知记录或损坏内容不修复。采集前后比较来源文件及目录清单。核验器源码内容身份与整工作区构建身份分开记录；前者仅通过固定源码文件字节计算，无git进程。

完整性核验与原二进制来源是不同证据：原runner不可得继续记录，native_calls=0，不将单次未配对记录变成重放成功，不改写旧调用或旧失败。核验失败可保存诊断后非零退出；输出路径错误或覆盖拒绝。新门禁调整及原生停止条件见[历史核验与续办计划](superpowers/plans/2026-10-21-history-followup.md)。


## 剩余提示静态准备 v1

`python -m ygo_eval.research prepare-prompt-probes --cases <冻结案例> --baseline-dir <最新洗手牌线路验收目录> --core-source <冻结核心目录> --output <新的准备目录>`只做文件系统和只读SQLite检查，不启动进程、worker或可写账本。输出目录必须位于本批固定忽略目录内并独占新建；来源重复键、哈希失配、目录变化和输出覆盖会拒绝。

`prepared-cases.json`保存三个完整research-case、原请求与派生案例内容哈希、唯一激活项选择条件及合成响应夹具；`report.json`按prompt-probe-preparation-v1报告静态来源和未决项。选择器只在己方idle中接受对应卡号的唯一command5激活项，保留原Choice、索引和响应字节。没有或多个匹配即停止，不猜实际prompt编号。

后续冻结案例分别为Tenki opcode13、Mooyan Curry opcode14提供了局部分支响应和独立重放证据；它们不代表Rabbit完整动作树覆盖。Ground Collapse opcode24仍未原生触达，实际提示、掩码、prompt ID及响应接受保持未知。本批新增的FIELD_DISABLED56生产decoder只证明5字节帧可严格解析；RECOVER92/FIELD_DISABLED56在Ground Collapse线路中的出现顺序、后继消息及响应均未验证。命令6仍受首回合战斗规则及worker下一回合停止边界阻断，未生成可执行案例。正式发行依据保持unknown。

准备合同不是RunDuelRequest。未来worker、实际prompt、完整请求哈希和新预算仍须冻结；execution_ready与所有原生/证明资格保持false。部分失败可保留已核对前缀，来源漂移撤销全部候选结论。本工具新增原生调用固定0，后续探索、查询、失败、重试及重放必须另行制定预算。


## 天玑六槽位原生提示实验 v1

`native-prompt-probe --preparation <上批research-final> --cases <冻结案例> --baseline-dir <上批交付根目录> --runner <专用runner> --worker <候选worker> --build-record <构建记录> --identity <双资产身份> --window-start <窗口收据> --output <本批research> [--prepare-only]`只接受冻结天玑候选，使用独立tenki-prompt-probe-v1 scope，最多6次、2小时，每worker30秒。旧窗口不续用。

六槽位为：Probe首次己方idle、Probe唯一command5激活至13、Execution false、Replay false、Execution true、Replay true。13原始帧严格10字节，player0、description59877851398144，0/1小端响应；false预期下一己方idle，true预期15单选两张69247929，不继续选检索对象。decision_required是合格暂停状态，不能套终场无提示门禁。

每阶段请求从父resolved_decisions和实际菜单派生、收费前不可覆盖保存。Rust独立检查顺序/用途/父收据/请求身份，Python检查来源/源码及构建。仅完整合格才后继；任何额外提示、未知消费、执行/资产/重放错误即停止，不重试。天玑发动可能先有18区域提示；出现则保存真实结果并终止此批，不选区域绕过。

prepare-only新增原生0且不创建收费账本；六次整体成功不授予完整动作或最优性。发现两次没有独立重放，不能包装为重放证据。窗口在首次候选资产扫描前持久化，原生期间源码/产物冻结；恢复同一账本，已收费未知不得重发，旧阶段收据消费前缀不改写。未统计内部查询保持未知。
