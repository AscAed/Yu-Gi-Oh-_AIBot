# accepted关联保存后内存队列更新前：限定强杀验收

合成冻结输入、queued任务和accepted关联依次持久提交后、内存队列更新前，子进程通过`cfg(test)`检查点同步握手。父进程逐条认证操作及任务修订封套、前驱和记录哈希、状态转换和输入绑定，确认freeze一次、claim零次及无报告后终止子进程。新协调器持锁完整认证后，accepted保持原修订，queued任务仅追加一次interrupted；第二次重开不再写入，不排队、运行或重新领取。

红测因检查点缺失失败；加入挂点后聚焦测试1 passed、durable操作组19 passed，fmt与workspace全目标Clippy通过；本批未重跑workspace全套。`target/w1h21-analysis-operation-tests/c3933e2360937e2a83a452b8d8d6b1c2/`保存握手、事件、终止状态及前后哈希；六项恢复后哈希与磁盘一致，新任务修订为interrupted。哈希和父进程断言不是逐阶段原始字节备份。

此测试只认证该合成提交窗口，不认证HTTP传输期间强杀、其他调度、逐syscall、断电或介质故障。未启动真实runner、worker、FFI或原生研究，不推断真实消费；普通启动仍为`analysis_not_configured`，W1-C和P4-R5开放。
