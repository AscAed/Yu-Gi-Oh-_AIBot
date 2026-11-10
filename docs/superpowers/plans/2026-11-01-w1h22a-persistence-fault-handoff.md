# W1-H2.2-A 持久故障与停止后只读交接

日期：2026-11-01。实施基线 `main / 8d8c492`；保留原有未提交文档。日志及合成材料统一保存在忽略目录 `target/w1h22a-persistence-fault-tests/`。

## 范围与证据

本批只验证逻辑提交边界。`BeforePublish` 模拟正式文件发布前明确失败；`AfterPublish` 模拟正式文件已保存但返回不确定；`Reread` 模拟写后复核读失败，保留已发布字节。三类故障不代表逐文件系统调用、断电或介质故障。选择器绑定链类型、目标状态及 revision，命中一次即消耗；仅在 `cfg(test)` 中存在。

停止后查询使用真实 TCP、同一目录锁所有者和实际持久校验，覆盖健康历史、明确不存在的404、报告缺失/哈希错误、请求/身份/评分/预算绑定，以及操作链和任务链损坏。语义负例同时更新引用哈希，使错误准确抵达绑定门禁，不能用格式错误冒充绑定验证。GET前后比较目录和文件快照；Windows持有的锁文件保留存在与长度，查询矩阵另记录修改时间，其他材料比较内容哈希，不释放锁绕过限制。

## 覆盖映射

| 逻辑提交点 | 链与目标修订 | 三类故障的保存/内存及读取规则 |
|---|---|---|
| allocated | operation allocated/1 | 发布前目标缺失，发布后目标保留；不安排冻结 |
| 首次accepting | operation accepting/2 | 原allocated或新accepting可认证；无queued任务 |
| 容量拒绝、配置拒绝 | operation rejected/2，各一组 | 拒绝记录写入失败本身为503，不冒充409业务拒绝 |
| 冻结绑定 | operation accepting/3 | 发布前保留未绑定状态，发布后保留绑定；无可派发任务 |
| 准备失败rejected | operation rejected/3 | 发布前仍accepting，发布后rejected；后台原202保持历史含义 |
| queued任务 | job queued/1 | 后置故障可留queued文件，但accepted关联未完成，不登记可领取内存任务 |
| accepted关联 | operation accepted/4 | 任务文件保留；关联提交未确认不能派发 |
| running | job running/2 | 发布前保留queued；发布后running文件存在，但不返回有效派发票据 |
| cancelled | job cancelled/2 | 原queued内存槽保留到提交确认；不确定时停派发 |
| failed | job failed/3 | 原running内存槽保留；保存failed不确定不释放槽位 |
| unknown | job unknown/3 | 真实重启分类路径；发布前running、发布后unknown，打开失败不返回协调器 |
| 报告文件 | report file | 发布前无报告，发布后保留孤立报告；不据文件存在认定完成 |
| 报告终态 | job completed/3 | 报告已存，终态发布前仍running；发布后可认证终态可读，内存未确认时停派发 |

每行均覆盖BeforePublish、AfterPublish、Reread；容量/配置各一组，因此共42个逻辑组合（主矩阵39、unknown3）。另有真实TCP同步15项、202后后台12项，以及9类停止后查询。逻辑矩阵调用实际存储/协调器及GET路由；不把它描述为每行都通过TCP提交。运行中故障的明确发布前失败可保留原状态并拒绝本次操作；所有提交不确定均须停止，不能统一写成“任何失败都停派发”。

机器可读入口：`target/w1h22a-persistence-fault-tests/coverage-matrix.json`。各组原始结果为`logical-matrix-results.json`、`unknown-matrix-results.json`、`tcp-sync-matrix.json`、`tcp-background-matrix.json`和`query-matrix.json`。这些是合成测试观察，不是原生账本或研究消费证据。

## 实测记录

关口结论：H2.2-A通过并暂停。CLI最终72通过；workspace串行435通过、36忽略；fmt、workspace全目标Clippy及Python schema16项通过。全量启动后仅补充测试冻结计数，随后复验全部CLI、fmt和Clippy；其他crate未变。最终测试与矩阵见本批 TESTING 记录及外部日志。

命令、忽略原因见`test-summary.json`；最终日志为`cli-counter-final.log`、`workspace-final.log`、`clippy-final.log`、`fmt.log`、`python.log`。独立只读审阅保存为`review.md`，区分作者自审和交叉审阅。后台冻结计数器紧贴实际W1-A调用，仅测试编译可用；同步请求增量0、后台完成1、后继读取/拒绝领取不增加。首次查询测试先暴露测试快照直接读取Windows已锁文件的问题；修正快照后，又发现请求负例改变seed但未同步runtime导致先被报告合同拒绝。修正合成材料后精确命中绑定门禁。没有据这些夹具问题修改生产验证器。曾怀疑状态GET会对损坏引用返回成功，强化用例实际通过；既有scan已经认证报告，反证保存在`query-status-red.log`。

## 后续边界

在本A批交接时，H2.2-B重复并发矩阵仍需单独完成；后续状态见[H2.2-B交接](2026-11-01-w1h22b-concurrency-handoff.md)和当前[TESTING](../../TESTING.md)。H3进程崩溃、回复丢失和完整跨链重启恢复，以及W1-C真实资产分析继续后置。普通 `workbench serve` 仍为 `analysis_not_configured`。本批没有新增端点、CLI参数、界面或生产执行器。

原生研究、真实runner、worker和引擎FFI调用均为0；认证消费子集40、政策预留7、规划47，旧confirmation与全部历史实际累计仍未知。Tenki历史pin、旧证据、部署及active资产保持原样，不提交或推送。交付后暂停。
