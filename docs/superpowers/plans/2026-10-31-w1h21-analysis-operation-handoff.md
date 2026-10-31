# W1-H2.1 内部操作提交交接

基线：main / 577924b；保留既有未提交文档。本批新增操作合同、不可变操作修订链与内部幂等提交，不接HTTP、界面或真实分析。

## 合同与提交边界

操作与任务ID分开。指令摘要保留客户端选择，冻结绑定认证实际解析身份；重复提交不重新冻结。操作和任务共用目录锁，冻结期间预占唯一等待槽，accepted发布前不允许派发。重开先认证操作/任务绑定，再分类queued/interrupted及running/unknown，不自动重发。

旧无操作根保持原接口；含操作根必须通过操作感知入口打开。停止后的查询仅读取并认证保存链，不运行初始化分类。正式HTTP及结果投影留给H2.2，完整响应丢失/操作系统故障矩阵留给H3。

## 验证记录

H2.1内部合成关口通过，HTTP仍未实现。最终fmt/Clippy退出0；workspace串行415通过、36忽略，随后CLI最终修改回归77通过。合同4项、协调器11项、存储负例2项均通过；具体时点及排除项以TESTING为准。相关Python回归30 passed、2 skipped、4 subtests；跳过为真实本机报告opt-in。原始日志在target/w1h21-analysis-operation-tests。

本批新增原生研究、真实runner、worker及引擎FFI调用0；认证子集40、政策预留7、规划47不变，全部历史实际累计未知。不部署、提交或推送。


独立审阅与基本故障门禁通过；Unix链接测试在Windows未执行，H3完整响应丢失/进程崩溃矩阵未运行。新增schema3项测试通过；共享36例。行为红测为unknown修订不一致与持久竞争错误不停止，早期编译阻断单独保留。源码接口入口为workbench_analysis::{operations,durable,persistence}；旧任务合同不变，旧无操作根可用，含操作根须用open_operations。

下一批H2.2只接合成HTTP与无路径投影；H3故障恢复与W1-C真实分析分别另定。完整日志、忽略原因与审阅记录在target/w1h21-analysis-operation-tests，不写正式历史证据目录。本批交付后暂停。

文档收尾核对544个本地链接目标，缺失0；git diff --check退出0。检查覆盖当前已有及本批Markdown，不认证历史证据内容。明细见忽略目录document-check.json。
