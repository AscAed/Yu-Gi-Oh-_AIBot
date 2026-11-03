# 混合unknown/accepted操作恢复顺序：限定K验收

按[先行映射](2026-11-02-mixed-operation-recovery-map.md)完成一个混合恢复提交窗口。恢复器先认证所有操作与任务跨链材料，再按操作ID排序构造修复；该测试在首条操作修复落盘后、下一条操作修复前强杀子进程。

Fixture由存储层直接构造：操作`a…a`为allocated→accepting且没有匹配任务；操作`c…c`为allocated→accepting→accepting并绑定冻结输入，任务`d…d`为queued revision 1。测试挂点处第一条已提交unknown revision 3，第二条仍为accepting revision 3。父进程在终止前验证两条操作修订链、queued任务链、封套/前驱/记录摘要及冻结输入交叉绑定，另核对排序和子进程事件日志中的freeze=0、claim=0。

子进程终止后，真实目录锁和持久存储重开恢复第二条操作为accepted revision 4，再把queued任务分类为interrupted revision 2。操作、任务及报告材料均完成认证；无新任务、报告、冻结、排队或可领取工作。重复重开不增加修订，队列为空，持久材料字节稳定。该fixture不表示正常HTTP协调器可同时持有两条预占。

完整workspace证据保存在忽略目录：

- `target/w1h21-analysis-operation-tests/52d4f1e5727a65f5ebc88ad4b680c587/mixed-operation-recovery-evidence.json`
- evidence JSON SHA-256：`C7DD3EF97FA52736AF108C5D844138E849B8CF4B0E36B90741D56B4AD78C2963`
- 文件记录的强杀前7个存储材料哈希和恢复后9个材料哈希均与该目录下`store/`逐项相符；`repeat_reopen_stable=true`，子进程退出记录为`exit code: 1`。

聚焦命令：

```text
cargo test -p ygo-cli --offline --locked --target-dir target/h3-2b-2-cargo --lib workbench_analysis::durable::operation_tests::h3_2b_cross_chain_windows_recover_after_process_kill -- --exact --nocapture --test-threads=1
```

聚焦测试1 passed。随后CLI串行测试104 passed、0 failed；workspace串行测试91组，445 passed、0 failed、36 ignored，退出码0。workspace日志`target/h3-2b-2-cargo/workspace-final.log`的SHA-256为`7A10F5AC0F713D806D6BA9FF0F233F2298714DE76C89368E595B1527D88D2DDB`。`cargo fmt --all -- --check`、workspace全目标Clippy（offline/locked，`-D warnings`）和工作台HTTP/operation/job schema回归（16 passed）通过。完整验证记录见[TESTING](../../TESTING.md)。

本项关闭的只有该ID排序和该状态组合的逻辑K窗口。它不覆盖混合路径的P/U/R、其他操作/任务状态组合、其他排序与调度、逐系统调用故障、断电或介质故障。未调用worker、runner、ocgcore或FFI；没有生成消费证据，不提升为真实分析、原生执行、发布或最优性资格。普通启动保持`analysis_not_configured`，W1-C与P4-R5继续开放。下一批先从[H3证据门禁映射](2026-11-02-h3-evidence-gate-map.md)筛选W1-C前必需的恢复和调度门禁，再编写W1-C固定输入与停止边界设计。
