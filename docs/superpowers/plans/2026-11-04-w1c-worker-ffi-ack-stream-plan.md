# W1-C worker FFI 宿主确认流实施计划（2026-11-04）

状态：下一独立实现批次，未接入生产worker。当前attempt日志已经能保存合成FFI entered/returned事件；Rust磁盘验证器和Python离线验证器都要求同一attempt内LIFO返回，并拒绝job范围的重复call ID。两边的事件由合成executor提供，尚不能证明worker或ocgcore实际调用。

## 当前缺口

worker当前从stdin读取一行`RunDuelRequest`，然后向stdout写一行`DuelResult`；stderr仅用于诊断。worker内部的ocgcore FFI调用和反向C callback均在请求执行期间发生。若worker在完成后才输出调用清单，host无法在每个调用之前先持久化entered事件、等host确认后才允许调用，也无法在返回后先持久化returned事件再允许下一次FFI。因此不能把post-hoc stderr日志作为真实FFI receipt。

当前已审阅的FFI调用点包括`OCG_GetVersion`、`OCG_CreateDuel`、`OCG_DestroyDuel`、`OCG_DuelNewCard`、`OCG_StartDuel`、`OCG_DuelProcess`、`OCG_DuelGetMessage`、`OCG_DuelSetResponse`、`OCG_LoadScript`、`OCG_DuelQuery`、`OCG_DuelQueryCount`、`OCG_DuelQueryField`，以及callbacks `card_reader`、`card_done`、`logger`和`script_reader`。一次`DuelProcess`会同步触发0到多个callback，事件顺序必须保留真实嵌套关系；单个worker请求不等于单个FFI调用。

## 目标协议

增加明确opt-in的`ffi-receipt-stream-v1` worker模式，旧版单行request/response路径保持兼容。新模式使用stdin/stdout双向行协议：

1. Host发送版本化request frame，含attempt ID和原有`RunDuelRequest`。
2. 每个FFI entry前，worker向stdout发送`ffi_entered` frame并flush；frame含attempt ID、稳定的attempt内call ID、方向、name、连续ordinal。
3. Host严格检查frame与当前job/attempt绑定，先把entered追加至job私有hash链；只有持久发布并复读成功后，才通过stdin发送匹配sequence/call ID的ack。worker收到精确匹配的accepted ack后才调用目标FFI。
4. FFI返回后，worker发送`ffi_returned` frame并等待host对returned事件持久提交的ack。若host写入失败、提交不确定、ack错绑、连接中断或超过同一operation deadline，host立即终止并回收worker；不允许调用下一个FFI、自动重试或补造returned事件，现存entered证据保留，job在重开时为unknown。
5. 普通完成后worker发送一个versioned result frame；stderr继续只承载诊断。host将最终protocol/exit observation和attempt结果写入现有日志链。

call ID须由attempt ID和单调FFI entry序号以域分离摘要确定性生成，避免依赖worker随机源；唯一性由host journal再次验证。每个输入/输出frame有严格字节上限、字段白名单、序号单调性、attempt绑定、deadline及child exit/pipe错误规则。协议状态与旧模式隔离：flag缺失时不得等待ack或改变既有worker语义。

## 实施与验收顺序

1. **线协议合同：**先为worker event/ack/result frame建立严格serde合同和正负样本；拒绝未知字段、错误attempt/sequence/call ID、重复ack、缺失ack、越界frame和旧模式误入stream parser。
2. **worker调用层：**封装全部上述主动FFI入口和callbacks。entry必须在目标函数前被host确认；return必须在目标函数返回后被host确认。保留原函数指针和ABI布局，不在测试中加载ocgcore。
3. **host supervisor：**以可并发处理的stdout event reader和stdin ack writer连接持久journal sink；先写日志再ack。日志或ack失败必须杀进程，并明确区分未创建、已entered未returned、returned已持久和最终protocol响应状态。
4. **合成进程矩阵：**使用假worker子进程覆盖成功嵌套回调、entry ack延迟、entry写失败、return写失败、坏ack、重复/乱序frame、进程在entry后退出、deadline超时及无事件的普通result。检查adapter调用数、事件数、revision、unknown分类、空claim queue和重复重开的byte stability。
5. **兼容与记录：**验证现有legacy fixture未改变；Rust聚焦、CLI/workspace默认串行、schema和Python receipt regression、fmt与全目标Clippy均离线通过后更新TASKS/TESTING/DEPLOYMENT/交接。生成并验证新的source/state bundle及manifest identity。

## 边界

只实现协议和合成worker回归；不运行doctor、生产worker、ocgcore、真实FFI、真实分析、runner或研究scope，不切换部署、不提交或推送。即使stream实现通过假worker验证，也只证明host与该协议实现按约定交换并持久化事件，不认证操作系统实际映像、宿主外部事实、卡片语义或ResearchBatch消费。消费字段继续unknown/null，`report_origin_authenticated`继续false，除非后续单独完成来源、报告和账本证据链。
