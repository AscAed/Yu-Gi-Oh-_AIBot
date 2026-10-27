# Worker JSONL v2

每次引擎调用启动隔离 x64 worker，stdin 一个 RunDuelRequest JSON 行，stdout 一个 DuelResult JSON 行，stderr 诊断。父进程并行读两条输出管道、写请求，限制输出大小；deadline 到期 kill、wait 和 join 回收。GUI 不参与执行。

请求包含 protocol_version=2、engine 路径配置、deck、opening_hand、seed、versions、完整 decisions 前缀及 probe_only。versions 绑定规则、catalog/banlist ID、core 提交、DLL/CDB/script manifest SHA-256。运行前复核哈希与 engine manifest/API/结构布局；每个加载的 Lua 文件再核对 manifest 并记录内容哈希。

决策使用 prompt_id、player、choice。choice 是带 kind 的类型：command、cards、toggle、finish、yes_no、option、place、position、chain。worker 只编码当前提示广告的合法 choice，使用 pinned API 的字节缓冲区响应。Cards 使用全宽索引；同卡号的重复实例仍由当前提示索引区分。

核心消息先读取 u32 小端长度前缀，再按 opcode 解码。当前提示支持 11-16、18、19、24、26；其他选择操作停止分支。信息事件保留原始 bytes 和解码 fields；未知信息产生 coverage_gaps/partial。DuelResult 返回 status、events、prompt、checkpoint、steps、resolved_decisions、loaded_scripts、versions 和 error(code/stage/message)。single-action 提示可在同一调用内自动执行并记入 resolved_decisions，仍逐步由真实引擎响应。

固定起手先移除相应主卡组实例，用 seed 经 SHA-256 派生的独立 SplitMix64/Fisher-Yates 初始化剩余牌库顺序（initializer=fixed-hand-shuffle-v1），再预置手牌与剩余主卡组；后续洗切与随机性仍交由核心。双方初始自动抽卡为 0、后续正常抽牌为 1。默认兼容路径检测到下一回合NEW_TURN后查询，但checkpoint仍带固定旧标签1/0/512；这些标签不能独立证明精确终场查询绑定。无干扰模式对手只选择可选不响应；强制响应明确失败。

## 显式研究终场采集 v1

普通协议2请求可显式携带research_capture，固定schema_version=1、objective=rabbit-own-face-up-xyz-v1、boundary=first-next-turn-process-return-v1；只接受五张固定起手、无scenario/interruption/first_turn且非probe的请求。缺省不序列化该字段，默认协议2–6语义与旧身份不变。结果可携带独立terminal_observation，旧请求省略。

观察点是固定核心发出首个下一回合NEW_TURN的那次OCG_DuelProcess返回点；此时核心已做部分新回合初始化，不是初始化前上一回合最后状态。研究采集记录完整原始处理批、返回状态和事件绑定，要求结束阶段历史成立、边界为批末且没有待响应提示或自然结束冲突。在后续process/response之前查询双方各7个怪兽位置，保留查询参数及原始返回，并生成目标投影；这是该次worker请求内部工作，另报FFI查询统计，不另启动worker。

turn信息来自原始NEW_TURN历史，phase不能由查询ABI独立观察时保持null。legacy checkpoint仅作兼容投影，不作为新终场目标的绑定依据。边界不成立、查询失败与正常绑定分别保留诊断；部分查询及原始事件不因失败抹去，不以空列表冒充数量0。

纯数据验证独立拆分原始批和查询TLV并核对CDB，不能通过重新调用生产查询解析器自证。哈希与结构通过只表示输入内部绑定成立；来源真实性、账本结果和独立原生重放仍需另行验证，不授予动作完整性或最优性。

FFI 定义依据 [固定头文件](https://github.com/edo9300/ygopro-core/blob/38d04c9feb1a26617407091380634c87262fe3f8/ocgapi.h) 与 ocgapi_types.h。CardData=64、Options=136、NewCard=24、Query=20 字节；构建探针和 Rust 测试核对必要偏移。Lua 回调上下文及 setcodes 内存在句柄销毁前存活；RAII 销毁决斗后才卸载库。
