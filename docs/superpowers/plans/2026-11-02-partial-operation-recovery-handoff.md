# 多操作恢复中第一条unknown提交后强杀：限定验收

测试直接建立两条无匹配任务的accepting操作链；恢复中第一条unknown修订已保存、第二条仍accepting时通过`cfg(test)`检查点同步握手。父进程逐条认证两条操作修订封套、前驱和记录哈希、命令摘要及状态转换后强杀。新协调器持锁完整认证后，仅为第二条追加一次unknown；第一条和原文件不变，第二次重开不再写入，无冻结、任务、报告或可领取工作。

红测因检查点缺失失败；增加挂点后聚焦测试1 passed、durable操作组19 passed，fmt与workspace全目标Clippy通过；本批未重跑workspace全套。`target/w1h21-analysis-operation-tests/747962844c88c22fbd6c08ed77680451/`保留握手、终止状态及强杀前/恢复后哈希；六项恢复后文件哈希及两条unknown状态已只读核对。哈希和父进程断言不是逐阶段原始字节备份。

两条accepting链为存储层合成构造，不证明正常单队列可同时持有两个预占；不认证其他关联修复组合、调度、HTTP传输期间强杀、逐syscall、断电或介质故障。没有真实runner、worker、FFI或原生研究调用；unknown不解释为零消费。普通启动仍为`analysis_not_configured`，W1-C和P4-R5开放。
