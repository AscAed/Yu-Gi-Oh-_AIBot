# running保存后队列更新及票据返回前：限定进程终止验收

accepted合成任务的queued→running修订持久提交后、队列内存更新及领取票据返回前，测试子进程通过同步原子握手暂停。父进程核验任务修订封套、前驱和记录哈希、状态转换及与操作冻结输入绑定，确认freeze和claim各一次后终止子进程。新协调器持锁完整认证后，running恰好追加一次unknown；两次重开均无运行、排队或可领取任务，既有文件不变，第二次重开全部字节稳定。

红测因检查点缺失失败；增加`cfg(test)`挂点后聚焦强杀测试1 passed、durable操作组19 passed，fmt及workspace全目标Clippy通过；本批未重跑workspace全套。证据目录`target/w1h21-analysis-operation-tests/d2f6ed602b83325f6ecef6400ab45d58/`保留握手、事件、终止状态和强杀前文件哈希；六项原文件哈希及恢复后的unknown修订已只读核对。哈希和父进程断言不是逐阶段原始字节备份。

该挂点在队列更新、资产身份校验和票据返回之前，不代表真实执行或零消费；也不认证其他领取窗口、调度、HTTP传输期间强杀、逐syscall、断电或介质故障。无真实runner、worker、FFI或原生研究调用，普通启动仍为`analysis_not_configured`，W1-C和P4-R5开放。
