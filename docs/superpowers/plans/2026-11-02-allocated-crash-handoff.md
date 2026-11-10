# allocated持久化后、协调器返回前的进程终止交接

测试专用检查点位于操作首次allocated修订持久化成功之后、`allocate_operation`返回之前。父进程等待同步原子握手，核验操作标识、记录与前驱哈希、状态及空任务/报告，确认冻结和领取事件为零后终止子进程。新协调器持锁认证后保留原allocated操作；连续两次重开不追加修订，持久材料逐字节稳定，无queued/running任务、冻结或可领取工作。显式再次分配产生不同ID且不创建任务或报告。

最终聚焦测试1 passed；fmt和workspace全目标Clippy通过；相关Python schema 16 passed。workspace离线串行回归为444 passed、36 ignored、0 failed，日志见`target/h3-2b-2-cargo/allocated-workspace-final.log`。该回归早于补充证据输出和running为空的显式测试断言；这些后续测试修改已由最终聚焦测试、fmt和Clippy验证，不宣称它们经过同一次workspace回归。

最终聚焦测试的握手、子进程事件和证据文件位于`target/w1h21-analysis-operation-tests/f0723fbe71f7c12c360512b4e159ce5a/`。原修订现存哈希与强杀前记录一致，父进程记录终止结果和两次重开断言；这不是逐阶段完整字节快照。客户端未收到操作ID时不承诺找回；检查点不是HTTP响应传输期间的强杀。真实执行、其他逻辑窗口和调度、逐syscall、断电及介质故障均未认证，普通启动仍为`analysis_not_configured`。下一批依据窗口映射重新选择，W1-C真实分析另定范围。
