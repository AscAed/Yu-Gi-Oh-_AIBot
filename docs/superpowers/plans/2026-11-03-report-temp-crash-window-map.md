# H3 报告临时文件发布前窗口映射

## 批次状态

先完成源码窗口与已有证据映射，再实施测试并记录结果。它不创建研究scope，不调用worker、引擎或FFI，也不关闭其他H3窗口。

## 当前实现顺序

`AnalysisHttpService::dispatch_pending`在假执行器返回报告后，将报告编码并调用`DurableAnalysisCoordinator::publish_report`。协调器先调用`PersistentAnalysisJobStore::persist_report`，再复读并验证正式报告，随后才追加终态job revision并结算内存队列。

报告保存调用`ygo_storage::publish_exclusive_file`。当前写入顺序是：在`reports`目录创建`.ygo-draft-<32位小写十六进制>.tmp`，写完并`sync_all`，然后以hard link发布为`<report-id>.json`，最后移除临时文件。目标文件发布前进程终止时，临时文件会留在`reports`目录。

## 与已有K证据的精确关系

| 源码位置 | 已有证据 | 覆盖内容 |
|---|---|---|
| 假执行器返回前 | [执行器进入后强杀](2026-11-03-running-executor-crash-handoff.md) | 假执行器尚未返回报告时终止；恢复将running job分类为unknown |
| 执行器返回后、`persist_report`开始前 | [执行器返回后强杀](2026-11-03-executor-return-crash-handoff.md) | 报告已由假执行器返回，但存储函数尚未调用；reports目录为空 |
| 临时报告写入并同步后、正式hard link发布前 | 本批目标 | 目录内存在完整但未正式发布的临时报告；此前没有该窗口的进程终止证据 |
| 正式报告发布并复读后、终态revision前 | [2b-1四窗口交接](2026-11-01-w1h322b1-process-kill-handoff.md) | 报告已正式发布；job仍非终态；与本批文件系统阶段相邻但不同 |

首次复现确认，`PersistentAnalysisJobStore::validate_root_layout`原先只接受`reports`下以`.json`结尾的正式报告名；遗留的存储临时名使重开返回`Persistence(ReportInvalid)`。失败前后的操作、任务、报告临时文件逐字节SHA-256保存在`target/h3-report-temp-kill/3b711ceb347db39f67138adf6b5a305e/report-temp-crash-reproduction.json`，终端失败日志保存在`target/h3-report-temp-kill/pre-fix-focused.log`。

## 验收边界

测试子进程通过真实workbench dispatch与持久存储路径，使用测试专用假执行器返回schema合法的合成报告；存储层检查点只在测试构建中启用。父进程须认证握手PID、临时文件名/长度/哈希、operation/job revision链、命令摘要和冻结输入绑定，确认freeze、claim及假执行器调用各一次且无正式报告后，才终止子进程。

重开须持真实目录锁。若临时报告阻断重开，先保存错误、握手和所有文件哈希；确认后只做最小恢复修复。最终验收要求operation链不变、running job只追加一次unknown、临时报告原字节保留、正式报告缺席、队列为空、无可领取工作，且第二次重开材料稳定。未知临时内容不得当作已发布报告或报告来源证据。

本窗口不覆盖写入中的逐syscall终止、断电、介质损坏、真实执行器副作用、其他调度竞态或完整H3矩阵。

## 修复与验收结果

只读正式报告文件名仍按严格报告schema校验；对reports目录中的存储临时名增加精确识别：必须是`.ygo-draft-`前缀、32位小写十六进制ID和`.tmp`后缀，必须是普通文件且大小不超过报告上限。重开保留这些字节但不把它们解析为报告、加入报告索引或删除。由此恢复可以继续按既有规则把running任务分类为unknown。

修复后，`cargo test -p ygo-cli --offline --locked --target-dir target/h3-report-temp-kill/rust workbench::analysis_http::tests::running_job_crash_after_report_temp_sync_before_publish_recovers_unknown_once -- --exact --nocapture --test-threads=1`通过（1 passed）。任务只追加unknown revision 3，operation维持4个revision，临时报告字节稳定，无正式报告、queued/running任务或可领取工作；第二次重开材料稳定。成功材料位于`target/h3-report-temp-kill/450f3b94d97b49c232d73b907930f54f/report-temp-crash-evidence.json`。

该合成K只关闭这个精确临时文件窗口。它不认证生产执行器、报告来源或引擎，不覆盖部分写入系统调用、断电、介质损坏、其他调度和完整H3矩阵。
