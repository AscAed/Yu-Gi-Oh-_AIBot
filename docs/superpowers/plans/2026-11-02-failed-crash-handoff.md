# 合成analysis_failed保存后内存结算前：限定强杀验收

accepted合成任务从queued领取至running后调用失败结算；`analysis_failed`终态修订持久提交后、内存running槽位更新前发布测试专用同步原子握手。父进程检查三条任务修订封套、前驱和记录哈希、queued→running→failed转换，以及与操作冻结输入的一致性。强杀前freeze和claim各一次，无报告。新协调器持锁完整认证后，两次重开均保留failed、三条任务修订及原有材料，无排队、运行或可领取任务。

红测因挂点缺失失败；增加`cfg(test)`挂点后聚焦测试1 passed、durable操作组19 passed，fmt与workspace全目标Clippy通过；本批未重跑workspace全套。`target/w1h21-analysis-operation-tests/8f35423fcca5b0bd0580dd436c03d96a/`保留握手、事件、子进程终止状态与七项强杀前哈希；只读复核哈希、failed状态和`analysis_failed`错误。哈希清单及父进程断言不是逐阶段原始字节备份，原操作完整跨链认证在重开时进行。

仅认证该合成失败终态窗口，不认证其他失败来源、unknown终态、HTTP传输期间强杀、其他调度、逐syscall、断电或介质故障；未运行真实runner、worker、FFI或原生研究，不能推断真实消费。普通启动仍为`analysis_not_configured`，W1-C和P4-R5开放。
