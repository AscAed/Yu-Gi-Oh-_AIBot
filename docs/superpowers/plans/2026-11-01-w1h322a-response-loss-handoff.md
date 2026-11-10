# W1-H3.2-2a HTTP响应丢失与幂等查询交接

日期：2026-11-01。基线 main / 6b523f2，保留工作区已有源码和文档修改。本批新增响应传输测试控制与合成验收，不修改生产业务合同。

## 实现与证据边界

`workbench/response_loss.rs` 仅在 cfg(test) 编译；按服务实例、方法、路径和匹配次数选择，在真实分析路由返回后、写响应前握手。两种控制分别为零字节关闭、保留完整 Content-Length 的正文截断。响应和冻结握手均有10秒期限；测试客户端完整发送并半关闭写方向，按 Content-Length 读取，保存原始字节、响应头、已收正文长度及传输错误，不自动重试。

门禁不替换安全校验、冻结、修订链、报告认证或历史查询。响应丢失不证明提交失败；已知操作ID须显式查询保存结果，不能更换ID自动补交。分配响应丢失且ID未知时，本批不提供客户端发现功能。未知状态不解释为零调用。本批零原生调用来自测试装配没有真实执行器这一边界，不从丢失响应或unknown状态反推。

## 本轮验收

实际结果及机器可读矩阵见仓库忽略目录 `target/w1h322a-response-loss-tests/`。`commands.json`记录命令；`review.md`保存独立只读审阅；每次用例运行使用随机隔离子目录，含`matrix.json`、原始`.bytes`及传输`.json`。最终汇总见`coverage-summary.json`。

以下每行均覆盖零字节关闭和正文截断，使用真实本机TCP。合成适配边界只构造报告，再调用已有内部publish_report，未虚构报告HTTP接口。

| 线路 | 关键断言 |
|---|---|
| 分配201丢失 | 仅一项allocated，无任务、冻结或替代分配；ID由测试内部读取 |
| 接受202丢失 | 客户端读到丢失后仍accepting，再释放冻结；同ID同指令202且只冻结一次，不同指令409；另一操作容量409 |
| 后台完成/拒绝 | 连接关闭不取消后台；有效输入accepted，旧草稿revision rejected；错误不修改已丢失响应 |
| 取消响应丢失 | cancelled/revision2；重复取消409且修订不变；claim无可执行任务 |
| 操作/任务/结果GET丢失 | 显式再次GET认证保存材料；文件、目录及锁元数据快照不变 |
| 完成和预算截断 | completed及budget_limited分别发布一份合成报告，均为空线路；再读不重复发布 |
| 停止/损坏 | 停派发后健康历史200；报告原字节损坏、独立引用哈希错误分别503，不返回缓存成功 |
| 受控重开 | 正常停服、释放锁后queued→interrupted、running→unknown，活动队列为空；再次重开不追加、零冻结，终态报告保留 |

首轮快照遇到Windows锁文件不可读，改为记录锁路径、长度及只读属性；不尝试读取被本协调器独占的锁字节。其余文件仍逐字节保护。调试期间冻结计数断言和后台拒绝夹具也曾失败：门禁前实际冻结次数0；空起手会被HTTP同步拒绝，后台失败用例改为格式正确但不匹配的草稿revision。全部原日志保留。这些是测试修正，不是已证明的生产业务缺陷。

独立审阅要求将冻结释放延后到实际读到丢失响应之后，并补另一操作的预占拒绝；均已落实。没有为制造红测修改生产业务规则。首次稳定响应丢失矩阵通过后，追加独立报告引用错误用例并复验。首轮workspace随后在路由完成握手前超时，补充诊断又捕获零字节ConnectionReset，操作仍为allocated；保留`workspace.log`、`focused-diagnostic.log`及该次原始诊断，不把它们计为通过。

独立无载荷本机实验`socket-mode.log`发现Windows accepted socket继承listener的非阻塞模式：首次read立即WouldBlock，显式blocking后按200ms超时。生产助手`configure_connection`的Windows回归先在`socket-mode-red-1.log`实红（WouldBlock而非TimedOut），随后仅增加`set_nonblocking(false)`，保留非阻塞listener、原5秒读写超时和连接上限。最终聚焦两项通过，包含完整TCP矩阵和模式回归。这里证明的是当前平台配置缺陷，不单独追认每条历史或本轮重置的具体原因。

`socket-mode-red.log`最初过滤0项，不能作为红测；原辅助编辑脚本错误也不算行为证据。最终workspace串行测试442通过、0失败、36忽略（CLI库79通过）；最终聚焦2通过，相关Python/schema16通过，fmt及全目标Clippy通过。详见[TESTING](../../TESTING.md)、隔离目录的`test-summary.json`和`skipped.json`。本批H3.2-2a限定关口关闭，交付后暂停。

文档收尾静态检查：8份文档415项本地文件链接缺失0；`git diff --check`通过，仅检查目标文件，不校验标题锚点。

## 后续与暂停

本批范围仅为响应丢失和受控停止/重开。H3.2-2b目标窗口进程强杀、逐系统调用故障、断电及介质故障未覆盖；Windows既有TCP重置的历史根因仍未认证。普通启动保持 `analysis_not_configured`，没有新增HTTP端点、CLI参数、schema、依赖、界面或生产分析后端。

新增原生研究、真实runner、worker及引擎FFI调用0。认证消费子集40、政策预留7、规划47不变；旧confirmation及全部历史实际累计未知。保留Tenki pin、旧窗口和历史材料；本批未运行doctor或部署。H3.2-2a阶段验收后暂停；其后上层项目自检将相关源码和文档纳入本地提交，未推送或合并远端。
