# W1-H2.2 分析 HTTP 实施交接

本批基线为 main / 26756c3，保留既有 IMPLEMENTATION_NOTES、PROJECT_ASSESSMENT、TESTING 文档修改。不增加 CLI 参数、界面或真实分析后端；普通工作台分析保持未配置。

## 实现边界

新增严格 HTTP v1 合同及无路径投影，六个端点沿用 [HTTP 合同](../../WORKBENCH_ANALYSIS_HTTP.md)。异步提交先持久保存 accepting，再返回 202；一次性内部票据绑定操作与预占，冻结在锁外完成。原同步提交继续共用核心。

历史报告读取复用保存字节、引用、请求、身份、评分和预算校验，无需重新构造运行时冻结对象或扫描资产。GET 不调用存储 open/restart 分类。合成执行器仅用于测试，不认证来源或原生资格。

## 验证记录入口

日志位于忽略目录 `target/w1h22-analysis-http-tests/`。routes-red.log 保存原路由 404 与预期 503 的行为失败。合同接口缺失的编译失败不能称为行为红测；异步核心初次命令因冷编译期间实现已推进，未观察到失败，不作为红测证据。

初次实现验收workspace为426通过/36忽略；最新CLI为85通过，Python schema为16通过，fmt及Clippy通过。2026-11-01续接新增HTTP层检查后，定向HTTP用例3通过（含草稿revision冲突稳定拒绝、HTTP取消与claim竞争、operation/job写入失败行为）；详见[TESTING](../../TESTING.md)。两次Rust数量不相加；本次新增测试后需以续接复验取代旧workspace数字。

H2.2完整验收尚不关闭：本续接补了operation/job预写失败映射及保守状态行为、取消后领取和一个HTTP取消/claim并发竞态；新增HTTP端点全部持久故障点及重复并发调度的完整矩阵仍未穷尽。全量测试曾复现Windows 10054，并观测服务开始返回400但响应头被RST截断，错误码未认证；测试端改用完整写入与半关闭后，关键TCP回归连续3次通过。需以修复后的workspace结果作为最终复验。当前复验见[TESTING](../../TESTING.md)；不进入真实分析。

## 后续边界

H3 完整跨链崩溃/响应丢失、界面以及 W1-C 真实分析独立推进。认证消费子集40、政策预留7、规划47；旧 confirmation 及全部历史实际累计仍未知。保留 Tenki 历史 pin。新增原生研究、真实 runner、worker、引擎 FFI 调用均为0，不部署、不提交或推送。
