# 天玑 runner 输出与期限修复断点（2026-10-23）

## 继承的历史事实与勘误

- 上一批confirmation scope有1次normal runner进程尝试，但账本消费为0/6；六个未消费槽全部封存。本批不会调用normal、worker或账本收费入口，也不恢复旧窗口。
- 上一断点将原进程诊断误记在`research/process-diagnostics/`。实际原始诊断位于confirmation批根目录`data/runtime/p1-tenki-placement-confirmation-native-2026-10-22/process-diagnostics/`；旧断点原件保留为历史，不回填或改写。
- 既有交付将证据体积标为不完整，原因包含ACL拒绝读取的`test-data\tmpl3hi9n25`。保留该材料和“不完整”状态；不删除材料、不修改ACL，也不据此声称体积统计完整。

## 本批实现与验收

本批完成runner输出/期限离线修复及固定stage 1的只读验收，没有进行normal调用、worker调用或收费请求。Rust把共享预检函数改成返回JSON数据，由唯一输出路由按模式写入一份JSON；`--trace-stderr`输出阶段JSONL且默认关闭。Python normal runner timeout取被冻结`started_at + 7200 - now`，启动前要求现在不早于窗口起点且剩余时间严格大于30秒；worker自身30秒限制和Rust收费门禁不变。统计/核验/preflight模式不因窗口过期被拒绝。

新增`audit-tenki-confirmation-runner`在忽略目录运行。源码/合同、请求/input/seal、普通资产身份、两份源码归档、构建、旧七份账本及本scope账本/检查点均通过核验。审计报告状态`passed`，8个检查全通过，`native_calls=0`、`execution_ready=false`；原confirmation stage 1 `runner_timeout`保持不变。新runner只以`--preflight-only --trace-stderr`启动一次，退出码0，stdout严格为215字节单JSON，stderr 224字节，追踪只有`input_validation`与`shared_preflight`两阶段。审计总耗时188.068秒，其中共享预检阶段157.106秒；这证明预检本身会超过旧60秒外层timeout，但不推断导致原normal失败的具体阻塞函数或死锁。

固定路径及身份：目录`data/runtime/p1-tenki-runner-repair-offline-2026-10-23/`；审计源码身份`5ccaa25c19b6b53cf6759c7ebe63481a108ddc8029cdf570c25b1119633e762d`、534文件；runner SHA256 `96a1ad1b0a8c3374e2ef158b7c569cf4ae1aa0daee362f08e1d47c74249ec46c`；build-record identity `23ddae17e7e417af83d0d198edc824cd2e516a02811ddd993131fd94df64da53`；`source-native.zip` SHA256 `8e0565d8ea474198e6a76d839b7b50324891128fc20ce8c0f4e2d8cc7a6f302a`，file-list SHA256 `108aa3ccd29ab9117ad568a403dcdb3f01b97747f8a1b2ba830c95745f5d4bb7`。过程原始输出保存在批根`process-diagnostics/`。报告最初暴露schema不接受历史账本角色的连字符；只扩展角色schema字符集并加入回归，报告现通过该schema和运行时校验。该合同修正未重跑runner，不改报告内容、runner二进制或历史输入；因此报告保留其真实审计时源码身份，文档/schema收尾身份由独立`final-build/`记录。

测试：`cargo fmt --all -- --check`和workspace全目标Clippy通过；默认串行workspace 300通过/36忽略，examples 28通过；Python全套295通过/7跳过（156.699秒）。七项Python跳过均为已有opt-in报告或外部本机资产案例；列表和Rust忽略项保存在本批测试日志。第一次Python全套暴露旧断言误以为当前confirmation账本不存在，现改为核对已存在ledger固定哈希后重新全套通过。真实asset opt-in、doctor、worker及48手未运行。

八份账本仍累计26次、未知0，confirmation ledger消费0/6；原进程诊断依旧为`runner_timeout`，stage1–6均未完成。此前唯一normal runner尝试和六个未消费槽封存，不恢复或重置窗口。保护文件、历史报告及普通部署保持原值；四项资格均false，不提交或推送。

体积遍历结果在忽略目录`evidence-size.json`。之前confirmation交付记录的ACL拒绝路径`test-data/tmpl3hi9n25`仍无法读取，保持旧`evidence_size_complete=false`；本批不删除或改ACL。新断点交接完成后暂停，不启动新scope或预算。
