# 合成准备失败拒绝保存后协调器返回前：限定强杀验收

测试冻结闭包返回`OpeningHandInvalid`，操作从allocated经accepting进入rejected；保存拒绝修订后、协调器返回前发布同步原子握手。父进程认证三条操作修订、前驱和记录哈希、命令摘要及状态转换，检查一次合成冻结尝试和零领取后终止进程。重开持锁认证后拒绝保持三条修订，两次重开及重复提交材料字节稳定，不返回新冻结票据，也不创建任务、报告或活动队列。

红测因缺少检查点失败；实现测试专用挂点后，聚焦测试1 passed，durable操作组19 passed，fmt及workspace全目标Clippy通过，相关Python schema 16 passed。本批没有重跑workspace全套。测试证据在`target/w1h21-analysis-operation-tests/b891b956e5e3d1207aa1e0b555846ad8/`，父进程记录终止状态和三个原修订哈希；只读复核哈希与磁盘匹配、错误为`opening_hand_invalid`、事件仅freeze。证据不是各阶段原始字节备份。

仅覆盖闭包返回这一错误的合成场景，不认证真实手牌校验、其他准备错误、HTTP传输期间强杀、其他调度、逐syscall、断电或介质故障。无真实runner、worker、FFI或原生研究调用；普通启动仍为`analysis_not_configured`，W1-C和P4-R5继续开放。
