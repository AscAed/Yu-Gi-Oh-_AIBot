# W1-H2.2-B 并发与容量验收交接

日期：2026-11-01。测试基于本地 `main / 8d8c492` 及同一工作区的 H2.2-A 测试改动；此时本批代码和文档尚未提交。命令使用隔离 Cargo 目录 `target/w1h22a-persistence-fault-tests/cargo`，并发观察保存在 `target/w1h22b-concurrency-tests/`。

## 验收结果

- 将一个相同的已分配操作以16个并发TCP PUT重复提交。全部响应均返回同一 `accepting` 记录；只有一个后台任务；冻结屏障释放后只调用一次W1-A输入冻结，操作进入accepted。不同输入仍按原合同拒绝。
- 同ID不同内容的重放保持409冲突。另一个操作在唯一等待槽已预占时得到并持久保存 `analysis_queue_full`；GET读取同一rejected结果，重复PUT重放相同409，不隐式排队或改绑。
- 16轮同时启动HTTP取消和协调器claim。当前实现的accept线程/锁调度中，16轮均由claim赢得：job进入running，取消以409 `job_revision_conflict`返回，随后任务被明确fail并通过GET确认。该结果证明这些实跑竞争轮次具有单一合法状态，不证明线程调度公平或已经观察到两种同时竞争的赢家。
- 取消先持久完成后不再claim的顺序分支，由既有TCP集成用例覆盖：取消返回200，后续claim为空。队列/容量、停止后只读查询及其文件不变断言另见H2.2-A及既有queue测试。

本批没有修改生产HTTP、协调器或DTO行为。新增代码仅为 `#[cfg(test)]` 用例与本机忽略目录证据输出。代表性证据：`concurrent-duplicate-submissions.json` 记录16次重复、单后台任务、单次冻结；`cancel-claim-races.json` 记录16轮claim胜出及保存状态。两者不含原生调用。

## 验证范围和剩余限制

最终验证：定向HTTP组12 passed；workspace 437 passed、0 failed、36 ignored；HTTP/operation/job Python schema 16 passed；Clippy、fmt、Markdown 137份文档的1,043个本地目标及`git diff --check`均通过。最终源码差异与保留限制见[TESTING](../../TESTING.md)。H2.2-A/B只覆盖列出的合成请求与逻辑提交/调度；不认证每种操作系统调度、客户端响应丢失、HTTP进程崩溃、每条文件系统syscall、断电或介质损坏。早期TCP reset的根因仍未知。

H2.2合成接入验收关闭；H3跨链恢复与回复丢失、W1-C真实分析和报告来源验证仍开放。普通 `workbench serve` 仍为 `analysis_not_configured`，本批无真实引擎、runner、worker、FFI或研究账本调用。
